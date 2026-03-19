"""
domains/wastewater/brownfield/retrofit_generator.py

Brownfield Scenario Generator
==============================
Converts constraint failures and compliance gaps into new comparable scenarios
by applying retrofit options from the library.

Design rules
------------
- Does NOT modify base scenarios
- Does NOT call technology models — costs are deltas only
- Does NOT touch scoring, QA, carbon, or reporting engines
- Max 2 generated scenarios per base scenario (deterministic, priority-ordered)
- Generated scenarios are valid ScenarioModel objects — they enter the existing
  pipeline unchanged

Generation logic
----------------
For each base scenario:
  1. If brownfield constraint status == PASS AND compliance_status == "Compliant"
     AND no performance gaps → skip (no retrofit needed)
  2. Otherwise: collect applicable retrofit options, ranked by priority
  3. Take top 2, generate one new scenario per option

Retrofit priority order (within a scenario):
  Priority 1  BF-01  Ferric dosing   — compliance gap is a hard gate
  Priority 2  BF-04  Clarifier       — hydraulic FAIL blocks the scenario
  Priority 3  BF-05  SBR reactor     — hydraulic FAIL for AGS
  Priority 4  BF-02  IFAS            — capacity improvement (WARNING)
  Priority 5  BF-03  MABR            — capacity improvement (higher cost)

Scenario naming convention:
  "{base_name} + {retrofit_short_name}"
  e.g. "Base Case + Ferric Dosing", "NEREDA + 4th Reactor"

Integration
-----------
Called after base scenarios are calculated:

    if mode == "brownfield":
        constraints = evaluate_all(scenarios, brownfield, inputs)
        result      = generate(scenarios, brownfield, constraints, inputs)
        all_scenarios = result.base_scenarios + result.generated_scenarios
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field, replace
from typing import Any, Dict, List, Optional, Tuple

from domains.wastewater.brownfield.brownfield_context import BrownfieldContext
from domains.wastewater.brownfield.constraint_engine import evaluate, evaluate_all
from domains.wastewater.brownfield.retrofit_library import (
    get_all_options,
    evaluate_retrofit_applicability,
)
from domains.wastewater.brownfield.retrofit_models import (
    RetrofitApplicationResult,
    RetrofitOption,
)


# ── Constants ─────────────────────────────────────────────────────────────────

MAX_RETROFITS_PER_BASE = 2   # hard cap — keeps scenario count manageable

# Priority order for selecting which retrofits to generate first.
# Lower index = higher priority.
_RETROFIT_PRIORITY = ["BF-01", "BF-04", "BF-05", "BF-02", "BF-03"]


# ── Output dataclass ──────────────────────────────────────────────────────────

@dataclass
class GeneratedScenario:
    """
    A new scenario produced by applying one retrofit to one base scenario.
    Wraps the ScenarioModel with provenance metadata.
    """
    scenario:            Any               # ScenarioModel — identical interface to base
    base_scenario_name:  str               # which base scenario this came from
    retrofit_code:       str               # e.g. "BF-01"
    retrofit_name:       str               # human-readable name
    application_result:  RetrofitApplicationResult
    constraint_result:   Any               # BrownfieldConstraintResult after retrofit


@dataclass
class BrownfieldScenarioSet:
    """
    Complete output from the generator.

    Attributes
    ----------
    base_scenarios
        The original scenarios, unmodified.
    generated_scenarios
        New scenarios produced by applying retrofits.
        Each is a GeneratedScenario wrapper around a full ScenarioModel.
    all_scenario_models
        Flat list of ScenarioModel objects: base + generated.
        Ready for scoring, QA, and reporting.
    generation_log
        One entry per base scenario describing what was generated and why.
    """
    base_scenarios:      List[Any]                = field(default_factory=list)
    generated_scenarios: List[GeneratedScenario]  = field(default_factory=list)
    generation_log:      List[Dict[str, Any]]     = field(default_factory=list)

    @property
    def all_scenario_models(self) -> List[Any]:
        """Flat list of all ScenarioModel objects: base then generated."""
        return list(self.base_scenarios) + [g.scenario for g in self.generated_scenarios]

    @property
    def total_count(self) -> int:
        return len(self.base_scenarios) + len(self.generated_scenarios)


# ── Main entry point ──────────────────────────────────────────────────────────

def generate(
    base_scenarios:    List[Any],           # List[ScenarioModel]
    brownfield:        BrownfieldContext,
    constraint_results: Optional[Dict[str, Any]] = None,  # pre-computed or None
    inputs:            Any = None,          # WastewaterInputs
) -> BrownfieldScenarioSet:
    """
    Generate brownfield retrofit scenarios for all base scenarios.

    Parameters
    ----------
    base_scenarios
        Calculated ScenarioModel objects.  Must have cost_result populated.
    brownfield
        Existing plant asset inventory and constraints.
    constraint_results
        Pre-computed Dict[scenario_name → BrownfieldConstraintResult].
        If None, constraints are computed internally.
    inputs
        WastewaterInputs.  Required for cost estimation and constraint checks.

    Returns
    -------
    BrownfieldScenarioSet
    """
    result = BrownfieldScenarioSet(base_scenarios=list(base_scenarios))

    # Compute constraints if not pre-supplied
    if constraint_results is None:
        constraint_results = evaluate_all(base_scenarios, brownfield, inputs)

    lib = get_all_options()

    for base in base_scenarios:
        if not base.cost_result:
            result.generation_log.append({
                "base": base.scenario_name,
                "action": "skipped",
                "reason": "No cost_result — scenario not calculated.",
                "generated": [],
            })
            continue

        tc          = _get_tech_code(base)
        cr_base     = constraint_results.get(base.scenario_name)
        dso         = getattr(base, "domain_specific_outputs", None) or {}

        # Determine if any retrofits are needed
        needs_retrofit, reasons = _needs_retrofit(base, cr_base, inputs)

        if not needs_retrofit:
            result.generation_log.append({
                "base":      base.scenario_name,
                "action":    "skipped",
                "reason":    "All constraints PASS and no compliance gaps.",
                "generated": [],
            })
            continue

        # Find all applicable retrofits, ordered by priority
        candidates = _find_applicable_retrofits(
            tech_code=tc,
            scenario_dso=dso,
            constraint_result=cr_base,
            inputs=inputs,
            brownfield=brownfield,
            lib=lib,
        )

        if not candidates:
            result.generation_log.append({
                "base":      base.scenario_name,
                "action":    "no_retrofits",
                "reason":    f"Retrofit needed ({'; '.join(reasons)}) but no applicable option found.",
                "generated": [],
            })
            continue

        # Take up to MAX_RETROFITS_PER_BASE
        selected   = candidates[:MAX_RETROFITS_PER_BASE]
        log_entry  = {
            "base":      base.scenario_name,
            "action":    "generated",
            "reasons":   reasons,
            "generated": [],
        }

        for retrofit_option, app_result in selected:
            generated = _build_scenario(
                base         = base,
                retrofit     = retrofit_option,
                app_result   = app_result,
                brownfield   = brownfield,
                inputs       = inputs,
            )
            if generated is None:
                continue

            result.generated_scenarios.append(generated)
            log_entry["generated"].append({
                "name":         generated.scenario.scenario_name,
                "retrofit":     retrofit_option.code,
                "capex_delta_m":  app_result.capex_delta_m,
                "opex_delta_kyr": app_result.opex_delta_kyr,
                "constraint_after": generated.constraint_result.status,
            })

        result.generation_log.append(log_entry)

    return result


# ── Decision: does this scenario need retrofitting? ───────────────────────────

def _needs_retrofit(
    scenario:   Any,
    constraint: Any,   # BrownfieldConstraintResult | None
    inputs:     Any,
) -> Tuple[bool, List[str]]:
    """
    Return (needs_retrofit, [list of reasons]).

    A scenario needs retrofitting when ANY of:
    1. Constraint status is FAIL or WARNING
    2. Effluent TP exceeds target (compliance gap)
    3. Effluent TN exceeds target (compliance gap)
    4. SBR fill ratio ≥ 0.85 (hydraulic margin issue, even if no FAIL)
    """
    reasons = []

    # Constraint failure
    if constraint and constraint.status in ("FAIL", "WARNING"):
        reasons.append(f"Constraint {constraint.status}: {constraint.summary_line()[:60]}")

    # Performance gaps from domain_specific_outputs
    dso = getattr(scenario, "domain_specific_outputs", None) or {}
    tc  = _get_tech_code(scenario)
    po  = (dso.get("technology_performance") or {}).get(tc, {})

    tp_actual = po.get("effluent_tp_mg_l")
    tn_actual = po.get("effluent_tn_mg_l")
    tp_target = getattr(inputs, "effluent_tp_mg_l", None) if inputs else None
    tn_target = getattr(inputs, "effluent_tn_mg_l", None) if inputs else None

    if tp_actual is not None and tp_target is not None:
        if tp_actual > tp_target * 1.05:
            reasons.append(
                f"TP gap: {tp_actual:.2f} mg/L > target {tp_target:.2f} mg/L"
            )

    if tn_actual is not None and tn_target is not None:
        if tn_actual > tn_target * 1.05:
            reasons.append(
                f"TN gap: {tn_actual:.2f} mg/L > target {tn_target:.2f} mg/L"
            )

    # SBR fill ratio — performance gap even if constraint PASS
    fill_ratio = po.get("peak_fill_ratio", 0.0) or 0.0
    if fill_ratio >= 0.85:
        reasons.append(f"SBR fill ratio {fill_ratio:.2f} ≥ 0.85 (marginal/failing)")

    return bool(reasons), reasons


# ── Find and prioritise applicable retrofits ──────────────────────────────────

def _find_applicable_retrofits(
    tech_code:        str,
    scenario_dso:     Dict,
    constraint_result: Any,
    inputs:           Any,
    brownfield:       BrownfieldContext,
    lib:              Dict[str, RetrofitOption],
) -> List[Tuple[RetrofitOption, RetrofitApplicationResult]]:
    """
    Return a priority-ordered list of (RetrofitOption, RetrofitApplicationResult)
    for all applicable retrofits.
    """
    results = []

    # Evaluate each retrofit in priority order
    for code in _RETROFIT_PRIORITY:
        option = lib.get(code)
        if option is None:
            continue

        # Technology filter
        if option.applicable_to_technologies:
            if tech_code not in option.applicable_to_technologies:
                continue

        app_result = evaluate_retrofit_applicability(
            retrofit           = option,
            technology_code    = tech_code,
            scenario_result    = scenario_dso,
            constraint_result  = constraint_result,
            inputs             = inputs,
            brownfield_context = brownfield,
        )

        if app_result.applicable:
            results.append((option, app_result))

    return results


# ── Build a new ScenarioModel for one retrofit ─────────────────────────────────

def _build_scenario(
    base:       Any,                    # ScenarioModel
    retrofit:   RetrofitOption,
    app_result: RetrofitApplicationResult,
    brownfield: BrownfieldContext,
    inputs:     Any,
) -> Optional[GeneratedScenario]:
    """
    Create one new ScenarioModel by applying a retrofit to a base scenario.

    Steps:
    1. Build new name
    2. Clone and update CostResult (CAPEX + OPEX delta + LCC recalculation)
    3. Clone and update RiskResult (implementation + operational deltas)
    4. Clone and patch domain_specific_outputs (performance effects)
    5. Create new ScenarioModel
    6. Re-evaluate constraints against brownfield context
    7. Return GeneratedScenario
    """
    new_name = _make_name(base.scenario_name, retrofit)
    new_id   = f"{base.scenario_id}_{retrofit.code.lower()}"

    # ── Step 1: Updated CostResult ────────────────────────────────────────
    new_cr = _apply_cost_delta(
        base_cr        = base.cost_result,
        capex_delta_m  = app_result.capex_delta_m,
        opex_delta_kyr = app_result.opex_delta_kyr,
        retrofit_name  = retrofit.name,
    )
    if new_cr is None:
        return None

    # ── Step 2: Updated RiskResult ────────────────────────────────────────
    new_rr = _apply_risk_delta(
        base_rr      = base.risk_result,
        risk_effects = app_result.updated_risk,
    )

    # ── Step 3: Patched domain_specific_outputs ───────────────────────────
    new_dso = _apply_performance_effects(
        base_dso         = base.domain_specific_outputs,
        tech_code        = _get_tech_code(base),
        updated_perf     = app_result.updated_performance,
    )

    # ── Step 4: Build ScenarioModel ───────────────────────────────────────
    from core.project.project_model import ScenarioModel

    new_sc = ScenarioModel(
        scenario_id             = new_id,
        scenario_name           = new_name,
        cost_result             = new_cr,
        carbon_result           = base.carbon_result,   # unchanged
        risk_result             = new_rr,
        domain_specific_outputs = new_dso,
        treatment_pathway       = base.treatment_pathway,
        domain_inputs           = base.domain_inputs,
        is_compliant            = base.is_compliant,
        compliance_status       = base.compliance_status,
        compliance_issues       = base.compliance_issues,
        description             = (
            f"Brownfield retrofit of {base.scenario_name}: {retrofit.name}. "
            f"+${app_result.capex_delta_m:.2f}M CAPEX, "
            f"+${app_result.opex_delta_kyr:.0f}k/yr OPEX."
        ),
    )

    # ── Step 5: Re-evaluate constraints ──────────────────────────────────
    new_constraint = _re_evaluate_constraints(
        scenario   = new_sc,
        brownfield = brownfield,
        inputs     = inputs,
    )
    new_sc.brownfield_constraints = new_constraint

    # ── Step 6: Mark as brownfield-generated ─────────────────────────────
    new_sc.is_brownfield_generated  = True
    new_sc.brownfield_base_scenario = base.scenario_name
    new_sc.brownfield_retrofit_code = retrofit.code

    return GeneratedScenario(
        scenario           = new_sc,
        base_scenario_name = base.scenario_name,
        retrofit_code      = retrofit.code,
        retrofit_name      = retrofit.name,
        application_result = app_result,
        constraint_result  = new_constraint,
    )


# ── Helper: scenario name ─────────────────────────────────────────────────────

_RETROFIT_SHORT_NAMES = {
    "BF-01": "Ferric Dosing",
    "BF-02": "IFAS Retrofit",
    "BF-03": "MABR Retrofit",
    "BF-04": "Clarifier Expansion",
    "BF-05": "4th Reactor",
}


def _make_name(base_name: str, retrofit: RetrofitOption) -> str:
    short = _RETROFIT_SHORT_NAMES.get(retrofit.code, retrofit.name)
    return f"{base_name} + {short}"


# ── Helper: cost delta ────────────────────────────────────────────────────────

def _apply_cost_delta(
    base_cr:        Any,
    capex_delta_m:  float,
    opex_delta_kyr: float,
    retrofit_name:  str,
) -> Optional[Any]:
    """
    Apply CAPEX and OPEX deltas to produce a new CostResult.
    LCC is recalculated using the same CRF as the base scenario.
    """
    if base_cr is None:
        return None

    try:
        dr  = getattr(base_cr, "discount_rate", 0.07)
        n   = getattr(base_cr, "analysis_period_years", 30)
        crf = dr * (1 + dr) ** n / ((1 + dr) ** n - 1) if n > 0 else 0

        capex_delta_abs = capex_delta_m * 1e6
        opex_delta_abs  = opex_delta_kyr * 1e3

        new_capex = base_cr.capex_total + capex_delta_abs
        new_opex  = base_cr.opex_annual + opex_delta_abs
        new_lcc   = new_capex * crf + new_opex

        # Update CAPEX breakdown
        new_capex_bd = dict(getattr(base_cr, "capex_breakdown", {}) or {})
        new_capex_bd[f"Brownfield retrofit — {retrofit_name}"] = round(capex_delta_abs)

        # Update OPEX breakdown
        new_opex_bd = dict(getattr(base_cr, "opex_breakdown", {}) or {})
        if opex_delta_abs > 0:
            new_opex_bd[f"Brownfield retrofit — {retrofit_name}"] = round(opex_delta_abs)

        return replace(
            base_cr,
            capex_total          = round(new_capex),
            capex_breakdown      = new_capex_bd,
            opex_annual          = round(new_opex),
            opex_breakdown       = new_opex_bd,
            lifecycle_cost_annual = round(new_lcc),
            lifecycle_cost_total = round(new_lcc * n),
            cost_confidence      = "Concept (±40%) — brownfield retrofit cost",
        )

    except Exception:
        return base_cr   # fallback: return unchanged rather than None


# ── Helper: risk delta ────────────────────────────────────────────────────────

def _apply_risk_delta(
    base_rr:     Any,
    risk_effects: Dict[str, float],
) -> Any:
    """
    Apply implementation and operational risk adjustments.
    Returns a new RiskResult with adjusted scores.
    """
    if base_rr is None:
        return None

    impl_adj = risk_effects.get("implementation_risk_adj", 0.0)
    ops_adj  = risk_effects.get("operational_risk_adj", 0.0)

    if impl_adj == 0.0 and ops_adj == 0.0:
        return base_rr

    try:
        new_impl = round(min(100.0, max(0.0, base_rr.implementation_score + impl_adj)), 1)
        new_ops  = round(min(100.0, max(0.0, base_rr.operational_score  + ops_adj)),  1)

        # Recalculate overall as weighted average of components
        # Weights match risk_engine.py: technical 30%, implementation 25%,
        # operational 30%, regulatory 15%
        new_overall = round(
            base_rr.technical_score  * 0.30 +
            new_impl                 * 0.25 +
            new_ops                  * 0.30 +
            base_rr.regulatory_score * 0.15,
            1
        )

        return replace(
            base_rr,
            implementation_score = new_impl,
            operational_score    = new_ops,
            overall_score        = new_overall,
        )

    except Exception:
        return base_rr


# ── Helper: performance effects ───────────────────────────────────────────────

def _apply_performance_effects(
    base_dso:      Dict,
    tech_code:     str,
    updated_perf:  Dict,
) -> Dict:
    """
    Shallow-copy domain_specific_outputs and apply performance effect overrides.

    Only keys explicitly listed in updated_perf are changed.
    Values that are strings like "+5%" are not applied (narrative only).
    Only numeric values and "target" strings are applied.
    """
    if not updated_perf or not base_dso:
        return base_dso

    # Shallow copy top level — deep copy technology_performance dict only
    new_dso = dict(base_dso)
    tp_all  = dict(base_dso.get("technology_performance") or {})
    tp_tech = dict(tp_all.get(tech_code) or {})

    for key, value in updated_perf.items():
        # Skip narrative strings ("+30%", "below_limit" etc.)
        # Only apply concrete numeric values
        if isinstance(value, (int, float)):
            tp_tech[key] = value

    tp_all[tech_code]               = tp_tech
    new_dso["technology_performance"] = tp_all
    return new_dso


# ── Helper: re-evaluate constraints ──────────────────────────────────────────

def _re_evaluate_constraints(
    scenario:   Any,
    brownfield: BrownfieldContext,
    inputs:     Any,
) -> Any:
    """
    Re-run constraint_engine.evaluate() for the new scenario.
    Uses the patched domain_specific_outputs (which may have updated perf values).
    """
    tc  = _get_tech_code(scenario)
    dso = getattr(scenario, "domain_specific_outputs", None) or {}
    po  = (dso.get("technology_performance") or {}).get(tc, {})

    class _TRProxy:
        performance_outputs = po
        footprint_m2        = po.get("footprint_m2")
        volume_m3           = po.get("reactor_volume_m3")

    return evaluate(
        scenario_name  = scenario.scenario_name,
        tech_code      = tc,
        tech_result    = _TRProxy(),
        inputs         = inputs,
        brownfield     = brownfield,
    )


# ── Helper: extract tech_code ─────────────────────────────────────────────────

def _get_tech_code(scenario: Any) -> str:
    tp = getattr(scenario, "treatment_pathway", None)
    if tp and getattr(tp, "technology_sequence", None):
        return tp.technology_sequence[0]
    return ""
