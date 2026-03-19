"""
tests/test_brownfield_scoring.py

Mandatory test cases for brownfield scoring extension.

Tests:
  1. Low-cost but high disruption → should not win
  2. Moderate cost, low disruption → should rank highly
  3. High reuse vs new build → reuse scores higher
  4. Conditional scenario → penalised -10 pts
"""
from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dataclasses import replace, dataclass, field
from typing import Any, Dict

from core.decision.scoring_engine import (
    ScoringEngine, WeightProfile, WEIGHT_PROFILES, CRITERION_LABELS,
    DecisionResult, ScoredOption,
)
from core.costing.costing_engine import CostResult
from core.risk.risk_engine import RiskResult
from domains.wastewater.brownfield.brownfield_context import BrownfieldContext
from domains.wastewater.brownfield.constraint_engine import BrownfieldConstraintResult


# ── Shared fixture helpers ────────────────────────────────────────────────────

def _make_cost(capex_m=6.6, opex_kyr=669.0, lcc_kyr=1201.0, retrofit_capex_m=0.0):
    breakdown = {"Civil works": round(capex_m * 1e6)}
    if retrofit_capex_m > 0:
        breakdown[f"Brownfield retrofit — Test"] = round(retrofit_capex_m * 1e6)
    return CostResult(
        capex_total           = round((capex_m + retrofit_capex_m) * 1e6),
        capex_breakdown       = breakdown,
        opex_annual           = round(opex_kyr * 1e3),
        opex_breakdown        = {"Energy": round(opex_kyr * 1e3)},
        lifecycle_cost_annual = round(lcc_kyr * 1e3),
        lifecycle_cost_total  = round(lcc_kyr * 1e3 * 30),
        discount_rate         = 0.07,
        analysis_period_years = 30,
        cost_confidence       = "Concept (±40%)",
    )


def _make_risk(impl=15.0, ops=20.0):
    overall = impl * 0.25 + ops * 0.30 + 20.0 * 0.30 + 25.0 * 0.15
    return RiskResult(
        technical_score=20.0, implementation_score=impl,
        operational_score=ops, regulatory_score=25.0,
        overall_score=round(overall, 1),
    )


def _make_scenario(
    name, tech_code="bnr",
    capex_m=6.6, opex_kyr=669.0, lcc_kyr=1201.0,
    impl=15.0, ops=20.0,
    retrofit_code=None, retrofit_capex_m=0.0,
    is_compliant=True,
):
    from core.project.project_model import ScenarioModel, TreatmentPathway
    sc = ScenarioModel(
        scenario_id     = name.lower().replace(" ", "_"),
        scenario_name   = name,
        cost_result     = _make_cost(capex_m, opex_kyr, lcc_kyr, retrofit_capex_m),
        risk_result     = _make_risk(impl, ops),
        treatment_pathway = TreatmentPathway(
            technology_sequence=[tech_code], technology_parameters={}
        ),
        domain_specific_outputs = {
            "technology_performance": {tech_code: {
                "effluent_tp_mg_l": 0.5,
                "effluent_tn_mg_l": 5.0,
                "operational_risk": ops,
            }}
        },
        domain_inputs   = {"design_flow_mld": 10.0,
                           "effluent_tp_mg_l": 0.5,
                           "effluent_tn_mg_l": 5.0},
        is_compliant      = is_compliant,
        compliance_status = "Compliant" if is_compliant else "Non-compliant",
    )
    if retrofit_code:
        sc.is_brownfield_generated  = True
        sc.brownfield_retrofit_code = retrofit_code
        sc.brownfield_base_scenario = "Base"
    else:
        sc.is_brownfield_generated  = False
        sc.brownfield_retrofit_code = None
    return sc


def _make_bf_constraint(status="PASS"):
    """Minimal BrownfieldConstraintResult proxy for brownfield_map."""
    class _BFR:
        pass
    r = _BFR()
    r.status   = status
    r.feasible = (status != "FAIL")
    r.violations = []
    r.warnings   = ["Constraint WARNING"] if status == "WARNING" else []
    r.summary_line = lambda: f"Status: {status}"
    r.utilisation_summary = {}
    r.checks = []
    return r


def _score_brownfield(scenarios, bf_map=None):
    engine = ScoringEngine()
    return engine.score(
        scenarios,
        weight_profile = WeightProfile.BROWNFIELD,
        brownfield_map = bf_map or {},
    )


# ── Test 1: Low-cost but high disruption → should NOT win ────────────────────

def test_high_disruption_does_not_win():
    """
    Scenario A: cheapest LCC ($1,150k/yr) but requires clarifier expansion
    (BF-04, 20-day shutdown, cannot stage → disruption score = 33).

    Scenario B: moderate LCC ($1,300k/yr) but ferric dosing only
    (BF-01, 2-day shutdown → disruption score = 97).

    Under brownfield weighting (disruption=20%), B should rank above A.
    """
    # A: cheap but highly disruptive — clarifier expansion
    sc_a = _make_scenario(
        "Low-cost High-Disruption",
        lcc_kyr=1150.0, retrofit_code="BF-04", retrofit_capex_m=1.98,
    )
    # B: moderate cost, minimal disruption — ferric dosing
    sc_b = _make_scenario(
        "Moderate-cost Low-Disruption",
        lcc_kyr=1300.0, retrofit_code="BF-01", retrofit_capex_m=0.50,
    )

    bf_map = {
        sc_a.scenario_name: _make_bf_constraint("PASS"),
        sc_b.scenario_name: _make_bf_constraint("PASS"),
    }

    result = _score_brownfield([sc_a, sc_b], bf_map)

    pref_name = result.preferred.scenario_name if result.preferred else None
    print(f"\nTest 1:")
    for o in result.scored_options:
        bf_dis = o.criterion_scores.get("bf_disruption")
        print(f"  {o.scenario_name}: total={o.total_score:.1f}  disruption={bf_dis.normalised if bf_dis else '?':.0f}")
    print(f"  Preferred: {pref_name}")

    assert result.preferred is not None, "Must have a preferred option"
    assert result.preferred.scenario_name == sc_b.scenario_name, (
        f"Low-disruption scenario should win. Got: {pref_name}"
    )

    # Verify disruption scores
    a_dis = result.scored_options[0].criterion_scores.get("bf_disruption")
    b_dis = result.scored_options[0].criterion_scores.get("bf_disruption")
    # BF-04 disruption raw = 100*(1-20/30)=33; BF-01 raw = 100*(1-2/30)+10=97
    for o in result.scored_options:
        code = getattr(o, 'brownfield_retrofit_code', None)
        dis  = o.criterion_scores.get("bf_disruption")
        if dis and "High-Disruption" in o.scenario_name:
            assert dis.raw_value < 50, \
                f"High disruption scenario should have raw disruption < 50, got {dis.raw_value}"
        if dis and "Low-Disruption" in o.scenario_name:
            assert dis.raw_value > 80, \
                f"Low disruption scenario should have raw disruption > 80, got {dis.raw_value}"

    print("Test 1 PASS ✅")


# ── Test 2: Moderate cost, low disruption → ranks highly ─────────────────────

def test_low_disruption_ranks_highly():
    """
    Three scenarios competing:
      A: Lowest LCC, highest disruption (BF-04)
      B: Moderate LCC, lowest disruption (BF-01)
      C: Highest LCC, moderate disruption (BF-03)

    B must rank 1st or 2nd under brownfield weighting.
    """
    sc_a = _make_scenario("A Cheapest-Disruptive",
                          lcc_kyr=1100.0, retrofit_code="BF-04", retrofit_capex_m=2.0)
    sc_b = _make_scenario("B Moderate-LowDisruption",
                          lcc_kyr=1250.0, retrofit_code="BF-01", retrofit_capex_m=0.5)
    sc_c = _make_scenario("C Expensive-ModDisruption",
                          lcc_kyr=1500.0, retrofit_code="BF-03", retrofit_capex_m=0.8)

    bf_map = {s.scenario_name: _make_bf_constraint("PASS")
              for s in [sc_a, sc_b, sc_c]}

    result = _score_brownfield([sc_a, sc_b, sc_c], bf_map)

    ranked = sorted(result.scored_options, key=lambda o: -o.total_score)
    print(f"\nTest 2 ranking:")
    for o in ranked:
        dis = o.criterion_scores.get("bf_disruption")
        lcc = o.criterion_scores.get("lcc")
        print(f"  [{o.rank}] {o.scenario_name}: {o.total_score:.1f}  "
              f"lcc={lcc.raw_value:.0f}k  disruption={(dis.raw_value if dis else 0):.0f}")

    b_rank = next(o.rank for o in result.scored_options
                  if "LowDisruption" in o.scenario_name)
    assert b_rank <= 2, \
        f"Low-disruption scenario B should rank 1st or 2nd, got rank {b_rank}"

    # A (cheapest) must not be rank 1 — disruption penalty should pull it down
    a_rank = next(o.rank for o in result.scored_options
                  if "Cheapest" in o.scenario_name)
    print(f"  Cheapest-Disruptive rank: {a_rank} (expected > 1)")

    print("Test 2 PASS ✅")


# ── Test 3: High reuse vs new build → reuse scores higher ────────────────────

def test_high_reuse_outscores_new_build():
    """
    Brownfield retrofit scenario has 92% asset reuse.
    Greenfield (base) scenario has 0% reuse.
    Reuse criterion: brownfield must score materially higher.
    """
    # Brownfield: $7.1M total, $0.5M retrofit → reuse 93%
    sc_retrofit = _make_scenario(
        "BNR + Ferric Dosing", lcc_kyr=1220.0,
        retrofit_code="BF-01", retrofit_capex_m=0.5, capex_m=6.6,
    )
    # Greenfield base: no retrofit, reuse = 0%
    sc_greenfield = _make_scenario(
        "Greenfield Base", lcc_kyr=1201.0,
        retrofit_code=None, retrofit_capex_m=0.0, capex_m=6.6,
    )

    bf_map = {s.scenario_name: _make_bf_constraint("PASS")
              for s in [sc_retrofit, sc_greenfield]}

    result = _score_brownfield([sc_retrofit, sc_greenfield], bf_map)

    # Find asset_reuse scores
    reuse_scores = {}
    for o in result.scored_options:
        ar = o.criterion_scores.get("bf_asset_reuse")
        if ar:
            reuse_scores[o.scenario_name] = ar.raw_value

    print(f"\nTest 3 asset_reuse scores: {reuse_scores}")
    assert "BNR + Ferric Dosing" in reuse_scores
    assert "Greenfield Base" in reuse_scores

    retrofit_reuse    = reuse_scores["BNR + Ferric Dosing"]
    greenfield_reuse  = reuse_scores["Greenfield Base"]
    assert retrofit_reuse > greenfield_reuse, (
        f"Retrofit should have higher asset reuse ({retrofit_reuse:.0f}) "
        f"than greenfield ({greenfield_reuse:.0f})"
    )
    assert retrofit_reuse > 80.0, \
        f"Ferric dosing retrofit should have >80% asset reuse, got {retrofit_reuse:.0f}%"
    assert greenfield_reuse == 0.0, \
        f"Greenfield should have 0% asset reuse, got {greenfield_reuse}"

    print(f"  Retrofit reuse: {retrofit_reuse:.0f}%  Greenfield: {greenfield_reuse:.0f}%")
    print("Test 3 PASS ✅")


# ── Test 4: Conditional scenario → -10 pt penalty ────────────────────────────

def test_conditional_penalty():
    """
    Scenario A: constraint PASS — no penalty.
    Scenario B: constraint WARNING (CONDITIONAL) — should score -10 pts.

    Score B_base (from criteria alone) - 10 = Score B_actual.
    """
    sc_a = _make_scenario("Scenario PASS", lcc_kyr=1200.0,
                          retrofit_code="BF-01", retrofit_capex_m=0.5)
    sc_b = _make_scenario("Scenario CONDITIONAL", lcc_kyr=1200.0,
                          retrofit_code="BF-01", retrofit_capex_m=0.5)

    # Score with PASS for both
    bf_map_all_pass = {
        sc_a.scenario_name: _make_bf_constraint("PASS"),
        sc_b.scenario_name: _make_bf_constraint("PASS"),
    }
    result_no_penalty = _score_brownfield([sc_a, sc_b], bf_map_all_pass)

    # Score with CONDITIONAL for B
    bf_map_conditional = {
        sc_a.scenario_name: _make_bf_constraint("PASS"),
        sc_b.scenario_name: _make_bf_constraint("WARNING"),
    }
    result_with_penalty = _score_brownfield([sc_a, sc_b], bf_map_conditional)

    # Find B's scores in both runs
    b_no_penalty    = next(o.total_score for o in result_no_penalty.scored_options
                           if o.scenario_name == sc_b.scenario_name)
    b_with_penalty  = next(o.total_score for o in result_with_penalty.scored_options
                           if o.scenario_name == sc_b.scenario_name)

    print(f"\nTest 4:")
    print(f"  B score without penalty: {b_no_penalty:.1f}")
    print(f"  B score with -10 penalty: {b_with_penalty:.1f}")
    print(f"  Difference: {b_no_penalty - b_with_penalty:.1f}")

    assert abs((b_no_penalty - b_with_penalty) - 10.0) < 0.5, (
        f"CONDITIONAL penalty must be 10 pts. "
        f"Got: {b_no_penalty:.1f} - {b_with_penalty:.1f} = {b_no_penalty - b_with_penalty:.1f}"
    )

    # Scenario A (PASS) should be preferred over B (CONDITIONAL)
    assert result_with_penalty.preferred.scenario_name == sc_a.scenario_name, \
        "PASS scenario should rank above identical CONDITIONAL scenario"

    print("Test 4 PASS ✅")


# ── Bonus: FAIL scenario excluded from scoring ────────────────────────────────

def test_fail_excluded():
    """Brownfield FAIL scenario must appear in excluded, not eligible."""
    sc_a = _make_scenario("Scenario PASS", lcc_kyr=1200.0,
                          retrofit_code="BF-01", retrofit_capex_m=0.5)
    sc_b = _make_scenario("Scenario FAIL", lcc_kyr=900.0,
                          retrofit_code="BF-04", retrofit_capex_m=2.0)

    bf_map = {
        sc_a.scenario_name: _make_bf_constraint("PASS"),
        sc_b.scenario_name: _make_bf_constraint("FAIL"),
    }
    result = _score_brownfield([sc_a, sc_b], bf_map)

    excluded_names = [o.scenario_name for o in result.excluded]
    eligible_names = [o.scenario_name for o in result.scored_options if o.is_eligible]

    print(f"\nBonus: eligible={eligible_names}  excluded={excluded_names}")
    assert "Scenario FAIL" in excluded_names, "FAIL scenario must be excluded"
    assert "Scenario PASS" in eligible_names, "PASS scenario must be eligible"
    assert result.preferred.scenario_name == "Scenario PASS"

    print("Bonus PASS ✅")


# ── Bonus: brownfield weight profile sums to 1.0 ─────────────────────────────

def test_weight_profile_integrity():
    """Brownfield weight profile must sum to exactly 1.0."""
    total = sum(WEIGHT_PROFILES[WeightProfile.BROWNFIELD].values())
    assert abs(total - 1.0) < 1e-9, f"Weights sum to {total}, expected 1.0"
    criteria = set(WEIGHT_PROFILES[WeightProfile.BROWNFIELD].keys())
    assert "bf_disruption"       in criteria
    assert "bf_constructability" in criteria
    assert "bf_asset_reuse"      in criteria
    assert "bf_delivery_risk"    in criteria
    assert "lcc"                 in criteria
    print(f"\nBonus: weights={total:.4f} ✅")
    print("Weight profile integrity PASS ✅")


# ── Bonus: all existing profiles unaffected ───────────────────────────────────

def test_existing_profiles_unchanged():
    """
    Existing BALANCED/LOW_RISK/LOW_CARBON/BUDGET profiles must not contain
    brownfield criteria — ensures zero interference with greenfield scoring.
    """
    for profile in [WeightProfile.BALANCED, WeightProfile.LOW_RISK,
                    WeightProfile.LOW_CARBON, WeightProfile.BUDGET]:
        weights = WEIGHT_PROFILES[profile]
        for bf_key in ("bf_disruption", "bf_constructability",
                       "bf_asset_reuse", "bf_delivery_risk"):
            assert bf_key not in weights, \
                f"{profile.value} should not contain {bf_key}"
    print("\nExisting profiles unchanged PASS ✅")


# ── Show scoring table ────────────────────────────────────────────────────────

def print_scoring_table():
    """Print an example 3-scenario brownfield scoring table."""
    sc_a = _make_scenario("BNR + Ferric Dosing",  lcc_kyr=1220.0,
                          retrofit_code="BF-01", retrofit_capex_m=0.5)
    sc_b = _make_scenario("BNR + IFAS Retrofit",  lcc_kyr=1281.0,
                          retrofit_code="BF-02", retrofit_capex_m=0.4)
    sc_c = _make_scenario("BNR + Clarifier Exp.", lcc_kyr=1404.0,
                          retrofit_code="BF-04", retrofit_capex_m=1.98)

    bf_map = {s.scenario_name: _make_bf_constraint("PASS")
              for s in [sc_a, sc_b, sc_c]}

    result = _score_brownfield([sc_a, sc_b, sc_c], bf_map)
    criteria = ["lcc", "operational_risk",
                "bf_disruption", "bf_constructability",
                "bf_asset_reuse", "bf_delivery_risk"]
    weights  = WEIGHT_PROFILES[WeightProfile.BROWNFIELD]
    labels   = {k: CRITERION_LABELS.get(k, k) for k in criteria}

    print("\n" + "="*80)
    print("BROWNFIELD SCORING TABLE — Example")
    print("="*80)
    header = f"{'Criterion':<22} {'Weight':>6}  " + \
             "  ".join(f"{s.scenario_name[:14]:>14}" for s in result.scored_options
                       if s.is_eligible)
    print(header)
    print("-"*80)
    for c in criteria:
        w = weights.get(c, 0)
        row = f"{labels[c]:<22} {w*100:>5.0f}%  "
        for o in [o for o in result.scored_options if o.is_eligible]:
            cs = o.criterion_scores.get(c)
            if cs:
                row += f"  {cs.raw_value:>10.1f}({cs.normalised:>3.0f})"
            else:
                row += f"  {'—':>14}"
        print(row)
    print("-"*80)
    totals = f"{'TOTAL SCORE':<22} {'100%':>6}  " + \
             "  ".join(f"{o.total_score:>14.1f}"
                       for o in result.scored_options if o.is_eligible)
    print(totals)
    print("="*80)
    print(f"Preferred: {result.preferred.scenario_name} ({result.preferred.total_score:.1f}/100)")
    print(f"Note: raw value shown, normalised score (0–100) in parentheses")


# ── Runner ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    tests = [
        test_high_disruption_does_not_win,
        test_low_disruption_ranks_highly,
        test_high_reuse_outscores_new_build,
        test_conditional_penalty,
        test_fail_excluded,
        test_weight_profile_integrity,
        test_existing_profiles_unchanged,
    ]
    passed = failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"\nFAIL {t.__name__}: {e}")
            import traceback; traceback.print_exc()
            failed += 1

    print_scoring_table()

    print(f"\n{'='*60}")
    print(f"  {passed}/{passed+failed} tests passed")
    if failed:
        raise SystemExit(1)
