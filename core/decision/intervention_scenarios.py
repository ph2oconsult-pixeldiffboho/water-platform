"""
core/decision/intervention_scenarios.py

Intervention scenario generator.

For scenarios that fail compliance as modelled, this module generates
"with intervention" variants that estimate the additional cost and
engineering impact of making them compliant.

Current interventions implemented
----------------------------------
1. Chemical phosphorus removal (ferric chloride dosing)
   - Applies to: any scenario where TP > target
   - Effect: achieves TP target, adds ferric OPEX
   - Relevant for: BNR, MABR-BNR (TP=0.7-0.8 failing 0.5 target)

2. Supplemental carbon (methanol dosing)
   - Applies to: scenarios where TN > target due to insufficient C:N
   - Effect: achieves TN target, adds methanol OPEX
   - Relevant for: scenarios with COD/TKN < 10 at tight TN targets

The intervention variants are ScenarioModel objects with:
  - modified OPEX (additional chemical cost)
  - updated compliance_status = "Compliant" (if intervention achieves target)
  - scenario_name = original + " + Intervention"
  - intervention_note field describing what was added
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Any, Dict
import copy


@dataclass
class InterventionResult:
    """Describes an intervention applied to a non-compliant scenario."""
    base_scenario_name:  str
    intervention_type:   str          # "ferric_dosing" | "methanol_dosing" | "combined"
    intervention_label:  str          # human-readable
    opex_delta_k_yr:     float        # additional OPEX k$/yr
    capex_delta_m:       float        # additional CAPEX $M (dosing system)
    achieves_compliance: bool
    notes:               str
    modified_scenario:   Optional[Any] = None   # ScenarioModel with updated costs


def _estimate_ferric_opex(
    tp_actual_mg_l: float,
    tp_target_mg_l: float,
    flow_mld: float,
    ferric_price_per_kg: float = 0.72,
) -> tuple[float, float]:
    """
    Estimate additional OPEX and CAPEX for ferric chloride dosing to achieve TP target.

    Returns (opex_k_yr, capex_m)

    Ferric dose: ~3-5 mol FeCl3 per mol P removed
    FeCl3 MW = 162.2, P MW = 31
    Dose assumption: 4 mol FeCl3 / mol P = 4 * 162.2/31 = ~20.9 g FeCl3/g P removed
    """
    tp_removal_needed = max(0.0, tp_actual_mg_l - tp_target_mg_l)  # mg/L
    # Convert to kg/day
    tp_removal_kg_day = tp_removal_needed * flow_mld * 1000 / 1e6 * 1e3  # mg/L * ML/d * 1e6 L/ML / 1e6 = kg/d
    tp_removal_kg_day = tp_removal_needed * flow_mld  # simplified: mg/L * MLD ≈ g/d / 1000 → kg/d
    # More careful: mg/L * m3/d = mg/d / 1000 = g/d; * MLD * 1000 m3/MLD = mg/d / 1e6 kg
    tp_removal_kg_day = tp_removal_needed * flow_mld * 1000 / 1e6 * 1000  # = mg/L * ML/d * 1000 L/m3 / 1e6 mg/kg * 1000
    # Simplified: 1 mg/L in 10 MLD = 10 kg/day
    tp_removal_kg_day = tp_removal_needed * flow_mld

    # FeCl3 dose: ~20 g FeCl3 per g P (molar: 4 × 162.2 / 31 = 20.9)
    ferric_kg_day = tp_removal_kg_day * 20.9
    ferric_opex_yr = ferric_kg_day * 365 * ferric_price_per_kg
    opex_k_yr = ferric_opex_yr / 1e3

    # Dosing system CAPEX: ~$0.3-0.5M for a chemical dosing skid at 10 MLD
    capex_m = 0.3 + flow_mld * 0.02  # base $0.3M + $0.02M per MLD

    return round(opex_k_yr, 1), round(capex_m, 2)


def _estimate_methanol_opex(
    tn_removal_needed_mg_l: float,
    flow_mld: float,
    methanol_price_per_kg: float = 0.65,
) -> tuple[float, float]:
    """
    Estimate OPEX for methanol dosing to achieve additional TN removal.

    Methanol dose: 4 kg methanol per kg NO3-N removed (standard design value)
    """
    tn_removal_kg_day = tn_removal_needed_mg_l * flow_mld  # kg/day (simplified)
    methanol_kg_day   = tn_removal_kg_day * 4.0
    methanol_opex_yr  = methanol_kg_day * 365 * methanol_price_per_kg
    opex_k_yr = methanol_opex_yr / 1e3

    # Methanol storage CAPEX: tanks + dosing pumps ~ $0.15M base
    capex_m = 0.15 + flow_mld * 0.01

    return round(opex_k_yr, 1), round(capex_m, 2)


def generate_interventions(
    scenarios:    List[Any],
    assumptions:  Any,          # AssumptionsManager result
    ref_inputs:   Dict[str, float],
) -> List[InterventionResult]:
    """
    For each non-compliant scenario, generate intervention variants.

    Returns a list of InterventionResult — one per applicable intervention.
    """
    results: List[InterventionResult] = []
    flow_mld = ref_inputs.get("design_flow_mld", 10.0)
    tp_target = ref_inputs.get("effluent_tp_mg_l", 1.0)
    tn_target = ref_inputs.get("effluent_tn_mg_l", 10.0)

    # Cost assumptions
    ferric_price  = (assumptions.cost_assumptions.get("ferric_chloride_per_kg", 0.72)
                     if assumptions and hasattr(assumptions, "cost_assumptions") else 0.72)
    methanol_price = (assumptions.cost_assumptions.get("methanol_per_kg", 0.65)
                      if assumptions and hasattr(assumptions, "cost_assumptions") else 0.65)

    for s in scenarios:
        if getattr(s, "is_compliant", True):
            continue  # already compliant — no intervention needed

        tc  = (s.treatment_pathway.technology_sequence[0]
               if s.treatment_pathway and s.treatment_pathway.technology_sequence else "")
        dso = getattr(s, "domain_specific_outputs", None) or {}
        tp  = dso.get("technology_performance", {}).get(tc, {})

        tp_actual = tp.get("effluent_tp_mg_l")
        tn_actual = tp.get("effluent_tn_mg_l")
        issues    = (getattr(s, "compliance_issues", "") or "").lower()

        interventions_applied = []
        total_opex_delta = 0.0
        total_capex_delta = 0.0
        achieves = True

        # ── Ferric dosing for TP failure ─────────────────────────────────
        tp_fail = (tp_actual is not None and tp_actual > tp_target * 1.05)
        if tp_fail:
            opex_k, capex_m = _estimate_ferric_opex(
                tp_actual, tp_target, flow_mld, ferric_price
            )
            interventions_applied.append(
                f"Ferric chloride dosing (TP: {tp_actual:.1f}→{tp_target:.1f} mg/L, "
                f"+${opex_k:.0f}k/yr OPEX, +${capex_m:.2f}M CAPEX)"
            )
            total_opex_delta  += opex_k
            total_capex_delta += capex_m

        # ── Methanol dosing for TN failure ───────────────────────────────
        tn_fail = (tn_actual is not None and tn_actual > tn_target * 1.05)
        if tn_fail:
            tn_removal_needed = max(0.0, tn_actual - tn_target)
            opex_k, capex_m = _estimate_methanol_opex(
                tn_removal_needed, flow_mld, methanol_price
            )
            interventions_applied.append(
                f"Methanol dosing (TN: {tn_actual:.1f}→{tn_target:.1f} mg/L, "
                f"+${opex_k:.0f}k/yr OPEX, +${capex_m:.2f}M CAPEX)"
            )
            total_opex_delta  += opex_k
            total_capex_delta += capex_m

        if not interventions_applied:
            # Has compliance_issues but no specific remediable failure found
            achieves = False
            interventions_applied.append("Intervention type unclear — specialist assessment required")

        # Build label
        if tp_fail and tn_fail:
            itype = "combined"
            label = f"{s.scenario_name} + Ferric + Methanol dosing"
        elif tp_fail:
            itype = "ferric_dosing"
            label = f"{s.scenario_name} + Ferric chloride (TP removal)"
        elif tn_fail:
            itype = "methanol_dosing"
            label = f"{s.scenario_name} + Methanol (TN removal)"
        else:
            itype = "unknown"
            label = f"{s.scenario_name} + Engineering intervention"

        # Build a modified scenario with updated cost
        mod_scenario = _build_modified_scenario(
            s, label, total_opex_delta * 1e3, total_capex_delta * 1e6,
            achieves, interventions_applied
        )

        results.append(InterventionResult(
            base_scenario_name  = s.scenario_name,
            intervention_type   = itype,
            intervention_label  = label,
            opex_delta_k_yr     = total_opex_delta,
            capex_delta_m       = total_capex_delta,
            achieves_compliance = achieves,
            notes               = "; ".join(interventions_applied),
            modified_scenario   = mod_scenario,
        ))

    return results


def _build_modified_scenario(
    base: Any,
    new_name: str,
    opex_delta_yr: float,
    capex_delta: float,
    achieves: bool,
    intervention_notes: List[str],
) -> Any:
    """
    Return a lightweight modified ScenarioModel with updated costs.
    Does NOT re-run the engineering model — adjusts cost_result directly.
    """
    from core.project.project_model import ScenarioModel

    # Shallow copy
    mod = ScenarioModel(
        scenario_id          = base.scenario_id + "_intervention",
        scenario_name        = new_name,
        cost_result          = _adjusted_cost_result(base.cost_result, opex_delta_yr, capex_delta)
                               if base.cost_result else None,
        carbon_result        = base.carbon_result,
        risk_result          = base.risk_result,
        domain_specific_outputs = base.domain_specific_outputs,
        treatment_pathway    = base.treatment_pathway,
        domain_inputs        = base.domain_inputs,
        is_compliant         = achieves,
        compliance_status    = "Compliant" if achieves else "Non-compliant",
        compliance_issues    = "" if achieves else "Intervention insufficient — specialist assessment required",
    )
    # Tag as intervention scenario
    mod.description = "Intervention: " + "; ".join(intervention_notes[:2])
    return mod


def _adjusted_cost_result(cr: Any, opex_delta_yr: float, capex_delta: float) -> Any:
    """
    Return an adjusted CostResult with modified OPEX and CAPEX.
    Creates a new object with updated totals without modifying the original.
    """
    if cr is None:
        return None

    from dataclasses import replace
    try:
        new_opex_annual = cr.opex_annual + opex_delta_yr
        new_capex_total = cr.capex_total + capex_delta
        # Recalculate LCC: annualised CAPEX + OPEX
        dr = getattr(cr, "discount_rate", 0.07)
        n  = getattr(cr, "analysis_period_years", 30)
        crf = dr * (1 + dr)**n / ((1 + dr)**n - 1) if n > 0 else 0
        new_lcc = new_capex_total * crf + new_opex_annual

        new_breakdown = dict(getattr(cr, "opex_breakdown", {}))
        new_breakdown["Intervention (chemical dosing)"] = round(opex_delta_yr)

        # Use dataclass replace if available, otherwise build a simple wrapper
        return replace(
            cr,
            opex_annual=round(new_opex_annual),
            capex_total=round(new_capex_total),
            lifecycle_cost_annual=round(new_lcc),
            specific_cost_per_kl=round(new_lcc / (getattr(cr, "specific_cost_per_kl", 1) *
                                                    cr.lifecycle_cost_annual / new_lcc
                                                    if cr.lifecycle_cost_annual > 0 else 1), 3),
            opex_breakdown=new_breakdown,
        )
    except Exception:
        # If replace fails (e.g. non-dataclass), return original unchanged
        return cr
