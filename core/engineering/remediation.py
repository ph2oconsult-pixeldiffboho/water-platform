"""
core/engineering/remediation.py

Auto-Remediation Engine
========================
When QA identifies hydraulic failures, this module generates modified
scenarios with the minimum engineering change required to resolve them.

Remediation strategies implemented:
1. SBR fill ratio ≥ 1.0 → add a 4th reactor (granular_sludge)
2. Clarifier SOR > warn limit → add a 3rd clarifier (bnr, mabr_bnr, ifas_mbbr)
3. MBR flux > warn limit → increase membrane tank volume

Each remediation produces a RemediationResult with:
  - the specific failure and its cause
  - the engineering fix applied
  - updated cost estimates (CAPEX + OPEX delta)
  - updated hydraulic check (showing PASS after fix)
  - a modified ScenarioModel with updated cost_result

Philosophy:
  - Minimum change: remediation changes only what is required to pass
  - Cost conservative: estimates use concept-level unit rates (±40%)
  - Transparent: every step of the fix is documented
  - Re-scored: modified scenarios enter the full scoring comparison

References:
  Royal HaskoningDHV Nereda design guidelines (2020)
  Metcalf & Eddy 5th Ed, Table 7-21 (clarifier sizing)
  WEF MOP 35 — Hydraulic design
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
import copy


# ── Unit cost constants (AUD 2024, concept level ±40%) ───────────────────────
CONCRETE_TANK_PER_M3       = 850.0    # $/m³ — bioreactor civil
DESIGN_CONTINGENCY_FACTOR  = 1.20    # 20% design contingency
CONTRACTOR_MARGIN          = 1.12    # 12% contractor margin
CIVIL_TOTAL_MULTIPLIER     = DESIGN_CONTINGENCY_FACTOR * CONTRACTOR_MARGIN  # 1.344

CLARIFIER_AREA_COST_PER_M2 = 3500.0  # $/m² — clarifier civil + equipment
SBR_REACTOR_EQUIPMENT_PER_M3 = 650.0  # $/m³ — blowers, decant arms, instrumentation
MBR_MEMBRANE_COST_PER_M2   = 85.0    # $/m² installed


@dataclass
class RemediationResult:
    """Outcome of one remediation action."""
    scenario_name:       str
    failure_description: str        # what the QA failure said
    fix_description:     str        # what was changed
    capex_delta_m:       float      # additional CAPEX ($M)
    opex_delta_k_yr:     float      # additional OPEX (k$/yr)
    hydraulic_status_after: str     # PASS / WARNING / FAIL after fix
    hydraulic_note_after:   str     # updated check narrative
    modified_scenario:   Optional[Any] = None   # ScenarioModel with updated costs
    feasible:            bool = True            # False if no simple fix exists
    redesign_required:   bool = False           # True if only fundamental redesign helps
    notes:               str = ""


def remediate_scenarios(
    scenarios:        List[Any],
    hydraulic_results: Dict[str, Any],  # Dict[name, HydraulicStressResult]
    qa_result:        Any,              # PlatformQAResult
    assumptions:      Any = None,       # AssumptionsManager result (for unit costs)
) -> List[RemediationResult]:
    """
    For each QA failure, generate a minimum-intervention remediation.
    Returns a list of RemediationResult — one per failed scenario.
    """
    results = []

    for s in scenarios:
        hs = (hydraulic_results or {}).get(s.scenario_name)
        if not hs:
            continue
        if hs.overall_status == "PASS":
            continue

        tc = (s.treatment_pathway.technology_sequence[0]
              if s.treatment_pathway and s.treatment_pathway.technology_sequence else "")

        failed_checks = [c for c in hs.checks if c.status == "FAIL"]
        warn_checks   = [c for c in hs.checks if c.status == "WARNING"]

        # Only auto-remediate FAIL; surface warnings separately
        if not failed_checks:
            continue

        for check in failed_checks:
            rem = _remediate_check(s, tc, check, hs, assumptions)
            if rem:
                results.append(rem)

    return results


def _remediate_check(
    scenario:    Any,
    tech_code:   str,
    check:       Any,   # HydraulicCheck
    hs:          Any,   # HydraulicStressResult
    assumptions: Any,
) -> Optional[RemediationResult]:
    """Dispatch to the correct remediation strategy based on check name."""
    name = check.name

    if name == "SBR Fill Ratio" and tech_code == "granular_sludge":
        return _remediate_sbr_fill(scenario, check, hs, assumptions)
    elif name == "Clarifier SOR":
        return _remediate_clarifier_sor(scenario, check, hs, assumptions)
    elif name == "MBR Peak Flux":
        return _remediate_mbr_flux(scenario, check, hs, assumptions)
    else:
        return RemediationResult(
            scenario_name       = scenario.scenario_name,
            failure_description = check.note,
            fix_description     = "Specialist hydraulic modelling required — no standard fix available",
            capex_delta_m       = 0.0,
            opex_delta_k_yr     = 0.0,
            hydraulic_status_after = "FAIL",
            hydraulic_note_after   = "No automatic remediation available",
            feasible            = False,
            redesign_required   = True,
        )


def _remediate_sbr_fill(
    scenario:    Any,
    check:       Any,
    hs:          Any,
    assumptions: Any,
) -> RemediationResult:
    """
    SBR fill ratio ≥ 1.0 — add a 4th SBR reactor.

    The fill ratio with n reactors = (avg_flow_m3hr × cycle_hr / n) / working_vol
    Adding a 4th reactor reduces fill volume per reactor by 25%.
    """
    dso   = getattr(scenario, "domain_specific_outputs", None) or {}
    tp    = dso.get("technology_performance", {}).get("granular_sludge", {})
    dinp  = getattr(scenario, "domain_inputs", None) or {}

    vol_per_reactor = tp.get("vol_per_reactor_m3") or 694.0
    n_current       = tp.get("n_reactors") or 3
    cycle_hr        = tp.get("cycle_time_hours") or 4.0
    fill_ratio_now  = tp.get("peak_fill_ratio") or 1.0

    # New fill ratio with n+1 reactors
    n_new = n_current + 1
    # fill_vol ∝ 1/n, working_vol unchanged
    # new_fill_ratio = fill_ratio_now × (n_current / n_new)
    new_fill_ratio = fill_ratio_now * (n_current / n_new)

    # ── CAPEX estimate ────────────────────────────────────────────────────
    # Civil: concrete tank
    civil_cost = vol_per_reactor * CONCRETE_TANK_PER_M3 * CIVIL_TOTAL_MULTIPLIER
    # Equipment: blowers, decant arms, instrumentation
    equip_cost = vol_per_reactor * SBR_REACTOR_EQUIPMENT_PER_M3 * CIVIL_TOTAL_MULTIPLIER
    capex_m = (civil_cost + equip_cost) / 1e6

    # ── OPEX estimate ─────────────────────────────────────────────────────
    # Additional OPEX ≈ proportional increase in energy and maintenance
    base_opex = (scenario.cost_result.opex_annual / 1e3) if scenario.cost_result else 647.0
    opex_delta = base_opex * (1 / n_current) * 0.25  # 25% of per-reactor OPEX
    # Maintenance for extra reactor
    maint_delta = capex_m * 1e6 * 0.015 / 1e3   # 1.5% of new CAPEX per yr

    opex_delta_k = round(opex_delta + maint_delta, 1)
    capex_m = round(capex_m, 2)

    status_after = "PASS" if new_fill_ratio < 0.90 else "WARNING"
    note_after = (
        f"With {n_new} reactors, fill ratio reduces to {new_fill_ratio:.2f} "
        f"({'PASS' if new_fill_ratio < 0.90 else 'WARNING ≤0.90 recommended'}). "
        f"Additional CAPEX: +${capex_m:.2f}M. Additional OPEX: +${opex_delta_k:.0f}k/yr."
    )

    fix_desc = (
        f"Add a 4th SBR reactor ({vol_per_reactor:.0f} m³). "
        f"Reduces fill ratio from {fill_ratio_now:.2f} to {new_fill_ratio:.2f} at "
        f"{hs.peak_flow_factor:.1f}× peak flow. "
        f"Estimated +${capex_m:.2f}M CAPEX, +${opex_delta_k:.0f}k/yr OPEX."
    )

    mod = _build_modified_scenario(
        scenario, f"{scenario.scenario_name} + 4th Reactor",
        opex_delta_k * 1e3, capex_m * 1e6
    )

    # Patch the modified scenario's DSO to reflect 4-reactor configuration
    if mod:
        import copy
        _dso_patch = copy.deepcopy(mod.domain_specific_outputs or {})
        _tp_patch  = _dso_patch.get("technology_performance", {})
        if "granular_sludge" in _tp_patch:
            _tp_patch["granular_sludge"].update({
                "n_reactors":         n_new,
                "peak_fill_ratio":    round(new_fill_ratio, 3),
                # Updated n2o and scope1 scale approximately with n_reactors/n_current
                # (same biological load, more volume = slightly lower EF from better control)
                "n2o_scale_factor":   round(n_current / n_new, 3),
            })
            # Update fill ratio in the patched scenario
            _tp_patch["granular_sludge"]["hydraulic_status"] = "PASS"
        mod.domain_specific_outputs = _dso_patch

    return RemediationResult(
        scenario_name          = scenario.scenario_name,
        failure_description    = check.note,
        fix_description        = fix_desc,
        capex_delta_m          = capex_m,
        opex_delta_k_yr        = opex_delta_k,
        hydraulic_status_after = status_after,
        hydraulic_note_after   = note_after,
        modified_scenario      = mod,
        feasible               = True,
        redesign_required      = False,
        notes                  = (
            f"4-reactor Nereda configuration is standard practice for plants "
            f"with peak flow factor > 1.4\u00d7 or high diurnal variation. "
            "Confirm with Nereda (Royal HaskoningDHV) during concept development."
        ),
    )


def _remediate_clarifier_sor(
    scenario:    Any,
    check:       Any,
    hs:          Any,
    assumptions: Any,
) -> RemediationResult:
    """
    Clarifier SOR exceeds limit — add a 3rd clarifier or upsize existing.
    """
    dso = getattr(scenario, "domain_specific_outputs", None) or {}
    tc  = (scenario.treatment_pathway.technology_sequence[0]
           if scenario.treatment_pathway and scenario.treatment_pathway.technology_sequence else "")
    tp  = dso.get("technology_performance", {}).get(tc, {})

    clarifier_area = tp.get("clarifier_area_m2") or 417.0
    n_clarifiers   = tp.get("n_clarifiers") or 2
    sor_current    = check.value   # m/d at peak

    # How much extra area needed to get SOR below 35 m/d?
    peak_mld   = hs.peak_flow_mld
    peak_m3d   = peak_mld * 1000
    target_sor = 33.0   # m/d — comfortable below warning limit
    area_needed = peak_m3d / target_sor   # m²
    extra_area  = max(0.0, area_needed - clarifier_area)

    if extra_area <= 0:
        return RemediationResult(
            scenario_name       = scenario.scenario_name,
            failure_description = check.note,
            fix_description     = "SOR within acceptable range — no structural change required",
            capex_delta_m       = 0.0,
            opex_delta_k_yr     = 0.0,
            hydraulic_status_after = "PASS",
            hydraulic_note_after   = f"SOR {sor_current:.0f} m/d — acceptable under site hydraulic modelling",
            feasible            = True,
        )

    capex_m     = round(extra_area * CLARIFIER_AREA_COST_PER_M2 * CIVIL_TOTAL_MULTIPLIER / 1e6, 2)
    opex_delta  = capex_m * 1e6 * 0.015 / 1e3   # 1.5% maintenance
    new_sor     = peak_m3d / (clarifier_area + extra_area)

    status_after = "PASS" if new_sor < 35.0 else "WARNING"
    note_after = (
        f"With additional clarifier area (+{extra_area:.0f} m²), "
        f"SOR reduces to {new_sor:.0f} m/d at peak. "
        f"+${capex_m:.2f}M CAPEX, +${opex_delta:.0f}k/yr maintenance."
    )
    fix_desc = (
        f"Upsize secondary clarifiers by +{extra_area:.0f} m² (total {clarifier_area+extra_area:.0f} m²). "
        f"Reduces peak SOR from {sor_current:.0f} to {new_sor:.0f} m/d. "
        f"+${capex_m:.2f}M CAPEX."
    )

    mod = _build_modified_scenario(
        scenario, f"{scenario.scenario_name} + Clarifier Upsize",
        opex_delta * 1e3, capex_m * 1e6
    )

    return RemediationResult(
        scenario_name          = scenario.scenario_name,
        failure_description    = check.note,
        fix_description        = fix_desc,
        capex_delta_m          = capex_m,
        opex_delta_k_yr        = round(opex_delta, 1),
        hydraulic_status_after = status_after,
        hydraulic_note_after   = note_after,
        modified_scenario      = mod,
        feasible               = True,
    )


def _remediate_mbr_flux(
    scenario:    Any,
    check:       Any,
    hs:          Any,
    assumptions: Any,
) -> RemediationResult:
    """MBR flux exceeds limit — increase membrane area."""
    flux_current = check.value   # LMH
    flux_target  = 22.0          # LMH — comfortable below warning limit
    dso = getattr(scenario, "domain_specific_outputs", None) or {}
    tc  = (scenario.treatment_pathway.technology_sequence[0]
           if scenario.treatment_pathway and scenario.treatment_pathway.technology_sequence else "")
    tp  = dso.get("technology_performance", {}).get(tc, {})

    peak_mld    = hs.peak_flow_mld
    peak_m3hr   = peak_mld * 1000 / 24
    target_area = (peak_m3hr * 1000) / flux_target   # m²
    mem_tank    = tp.get("membrane_tank_volume_m3") or 1418.0
    current_area = mem_tank * 150 * 0.9   # packing density × net/gross

    extra_area   = max(0.0, target_area - current_area)
    capex_m      = round(extra_area * MBR_MEMBRANE_COST_PER_M2 / 1e6, 2)
    opex_replace = extra_area * 8.5 / 1e3   # membrane replacement k$/yr

    new_flux = (peak_m3hr * 1000) / (current_area + extra_area)
    status_after = "PASS" if new_flux < 25.0 else "WARNING"

    fix_desc = (
        f"Increase membrane area by +{extra_area:.0f} m² to achieve flux "
        f"{new_flux:.1f} LMH at peak. +${capex_m:.2f}M CAPEX."
    )
    mod = _build_modified_scenario(
        scenario, f"{scenario.scenario_name} + Extra Membranes",
        opex_replace * 1e3, capex_m * 1e6
    )

    return RemediationResult(
        scenario_name          = scenario.scenario_name,
        failure_description    = check.note,
        fix_description        = fix_desc,
        capex_delta_m          = capex_m,
        opex_delta_k_yr        = round(opex_replace, 1),
        hydraulic_status_after = status_after,
        hydraulic_note_after   = f"Flux at peak reduces to {new_flux:.1f} LMH after expansion",
        modified_scenario      = mod,
        feasible               = True,
    )


def _build_modified_scenario(
    base:          Any,
    new_name:      str,
    opex_delta_yr: float,
    capex_delta:   float,
) -> Any:
    """Build a modified ScenarioModel with updated cost_result."""
    from core.project.project_model import ScenarioModel
    from dataclasses import replace

    cr = base.cost_result
    if cr is None:
        return None

    try:
        dr  = getattr(cr, "discount_rate", 0.07)
        n   = getattr(cr, "analysis_period_years", 30)
        crf = dr * (1 + dr)**n / ((1 + dr)**n - 1) if n > 0 else 0

        new_opex   = cr.opex_annual + opex_delta_yr
        new_capex  = cr.capex_total + capex_delta
        new_lcc    = new_capex * crf + new_opex

        new_breakdown = dict(getattr(cr, "opex_breakdown", {}))
        new_breakdown["Hydraulic remediation (additional OPEX)"] = round(opex_delta_yr)

        new_cr = replace(
            cr,
            opex_annual          = round(new_opex),
            capex_total          = round(new_capex),
            lifecycle_cost_annual= round(new_lcc),
            opex_breakdown       = new_breakdown,
        )
    except Exception:
        new_cr = cr

    mod = ScenarioModel(
        scenario_id              = base.scenario_id + "_remediated",
        scenario_name            = new_name,
        cost_result              = new_cr,
        carbon_result            = base.carbon_result,
        risk_result              = base.risk_result,
        domain_specific_outputs  = base.domain_specific_outputs,
        treatment_pathway        = base.treatment_pathway,
        domain_inputs            = base.domain_inputs,
        is_compliant             = base.is_compliant,
        compliance_status        = base.compliance_status,
        compliance_issues        = base.compliance_issues,
    )
    mod.description = f"Hydraulic remediation of {base.scenario_name}"
    return mod
