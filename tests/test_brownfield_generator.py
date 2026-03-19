"""
tests/test_brownfield_generator.py

Mandatory test cases for the Brownfield Scenario Generator.

Tests:
  1. NEREDA fail → generates reactor expansion scenario
  2. BNR TP issue → generates ferric dosing scenario
  3. BNR capacity issue → generates IFAS scenario
  4. MBBR fully feasible → generates no new scenarios
  5. BNR with multiple issues → max 2 retrofit scenarios generated
"""
from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dataclasses import replace
from domains.wastewater.brownfield.brownfield_context import BrownfieldContext
from domains.wastewater.brownfield.constraint_engine import evaluate_all
from domains.wastewater.brownfield.retrofit_generator import (
    generate, BrownfieldScenarioSet, MAX_RETROFITS_PER_BASE,
)


# ── Shared helpers ────────────────────────────────────────────────────────────

def _make_inputs(flow=10.0, tp=0.5, tn=5.0):
    class _I:
        design_flow_mld   = flow
        peak_flow_factor  = 1.5
        peak_flow_mld     = None
    _I.effluent_tp_mg_l = tp
    _I.effluent_tn_mg_l = tn
    return _I()


def _make_cost_result(capex_m=6.6, opex_kyr=669.0, lcc_kyr=1201.0):
    """Minimal CostResult for testing."""
    from core.costing.costing_engine import CostResult
    return CostResult(
        capex_total           = capex_m * 1e6,
        capex_breakdown       = {"Civil": capex_m * 1e6},
        opex_annual           = opex_kyr * 1e3,
        opex_breakdown        = {"Energy": opex_kyr * 1e3},
        lifecycle_cost_annual = lcc_kyr * 1e3,
        lifecycle_cost_total  = lcc_kyr * 1e3 * 30,
        discount_rate         = 0.07,
        analysis_period_years = 30,
        cost_confidence       = "Concept (±40%)",
    )


def _make_risk_result(impl=14.7, ops=20.0):
    from core.risk.risk_engine import RiskResult
    overall = impl * 0.25 + ops * 0.30 + 20.0 * 0.30 + 25.0 * 0.15
    return RiskResult(
        technical_score      = 20.0,
        implementation_score = impl,
        operational_score    = ops,
        regulatory_score     = 25.0,
        overall_score        = round(overall, 1),
    )


def _make_scenario(
    scenario_id, name, tech_code,
    po: dict,
    capex_m=6.6, opex_kyr=669.0, lcc_kyr=1201.0,
    impl=14.7, ops=20.0,
    is_compliant=True, compliance_status="Compliant",
):
    """Build a minimal ScenarioModel for testing."""
    from core.project.project_model import ScenarioModel, TreatmentPathway
    sc = ScenarioModel(
        scenario_id     = scenario_id,
        scenario_name   = name,
        cost_result     = _make_cost_result(capex_m, opex_kyr, lcc_kyr),
        risk_result     = _make_risk_result(impl, ops),
        treatment_pathway = TreatmentPathway(
            technology_sequence=[tech_code], technology_parameters={}
        ),
        domain_specific_outputs = {
            "technology_performance": {tech_code: po}
        },
        domain_inputs   = {"design_flow_mld": 10.0,
                           "effluent_tp_mg_l": 0.5,
                           "effluent_tn_mg_l": 5.0},
        is_compliant      = is_compliant,
        compliance_status = compliance_status,
        compliance_issues = "" if is_compliant else "TP: model output > target",
    )
    return sc


# ── Test 1: NEREDA fail → reactor expansion ───────────────────────────────────

def test_nereda_fail_generates_reactor():
    """
    NEREDA with fill ratio = 1.00 (SBR hydraulic issue).
    Generator must produce 'NEREDA + 4th Reactor'.
    """
    po = {
        "effluent_tp_mg_l":        0.5,
        "effluent_tn_mg_l":        5.0,
        "compliance_flag":         "Meets Targets",
        "reactor_volume_m3":       2083.0,
        "vol_per_reactor_m3":      694.0,
        "n_reactors":              3,
        "peak_fill_ratio":         1.00,     # ← at limit → needs 4th reactor
        "peak_flow_factor":        1.5,
        "aeration_energy_kwh_day": 2054.2,
        "footprint_m2":            949.0,
    }
    nereda = _make_scenario("nereda", "NEREDA", "granular_sludge", po,
                             capex_m=7.0, opex_kyr=647.0, lcc_kyr=1211.0)
    inp = _make_inputs()
    bf  = BrownfieldContext(
        anaerobic_volume_m3=0, anoxic_volume_m3=0, aerobic_volume_m3=2083.0,
        clarifier_area_m2=0.0, clarifier_count=0,
        blower_capacity_kw=200.0, ras_capacity_m3_d=0.0, mlr_capacity_m3_d=0.0,
        available_footprint_m2=2000.0, can_add_new_tank=True, max_shutdown_days=30,
    )

    result = generate([nereda], bf, inputs=inp)

    assert result.total_count >= 2, \
        f"Expected ≥2 scenarios (1 base + ≥1 generated), got {result.total_count}"

    generated_names = [g.scenario.scenario_name for g in result.generated_scenarios]
    print(f"\nTest 1 generated: {generated_names}")
    assert any("NEREDA" in n and "Reactor" in n for n in generated_names), \
        f"Expected 'NEREDA + 4th Reactor', got {generated_names}"

    # Verify the generated scenario's cost is higher than base
    gen_sc = result.generated_scenarios[0].scenario
    assert gen_sc.cost_result.capex_total > nereda.cost_result.capex_total, \
        "Generated scenario must have higher CAPEX"
    assert gen_sc.cost_result.lifecycle_cost_annual > nereda.cost_result.lifecycle_cost_annual, \
        "Generated scenario must have higher LCC"

    # Check constraint result after retrofit
    gen_cr = result.generated_scenarios[0].constraint_result
    print(f"  Constraint after: {gen_cr.status}")

    # Verify brownfield metadata
    assert getattr(gen_sc, "is_brownfield_generated", False), \
        "Generated scenario must be marked as brownfield-generated"
    assert gen_sc.brownfield_base_scenario == "NEREDA"
    assert gen_sc.brownfield_retrofit_code == "BF-05"

    print(f"  Generated: {gen_sc.scenario_name}")
    print(f"  CAPEX: ${gen_sc.cost_result.capex_total/1e6:.2f}M")
    print(f"  LCC:   ${gen_sc.cost_result.lifecycle_cost_annual/1e3:.0f}k/yr")
    print("Test 1 PASS ✅")


# ── Test 2: BNR TP issue → ferric dosing ──────────────────────────────────────

def test_bnr_tp_issue_generates_ferric():
    """
    BNR where effluent TP = 0.8 mg/L > target 0.5 mg/L.
    Generator must produce 'Base Case + Ferric Dosing'.
    """
    po = {
        "effluent_tp_mg_l":          0.8,   # ← exceeds target
        "effluent_tn_mg_l":          5.0,
        "compliance_flag":           "Review Required",
        "compliance_issues":         "TP: model output 0.8 mg/L > target 0.5 mg/L",
        "reactor_volume_m3":         3011.0,
        "v_aerobic_m3":              1656.0,
        "clarifier_area_m2":         417.0,
        "n_clarifiers":              2,
        "aeration_energy_kwh_day":   2109.7,
        "footprint_m2":              1086.0,
        "sludge_production_kgds_day": 1396.4,
        "peak_flow_factor":          1.5,
    }
    bnr = _make_scenario("bnr", "Base Case", "bnr", po,
                          is_compliant=False, compliance_status="Non-compliant")
    inp = _make_inputs(tp=0.5)
    bf  = BrownfieldContext(
        anaerobic_volume_m3=276.0, anoxic_volume_m3=827.0, aerobic_volume_m3=1656.0,
        clarifier_area_m2=417.0, clarifier_count=2,
        blower_capacity_kw=150.0, ras_capacity_m3_d=12000.0, mlr_capacity_m3_d=40000.0,
        available_footprint_m2=2000.0, can_add_new_tank=True, max_shutdown_days=30,
    )

    result = generate([bnr], bf, inputs=inp)

    generated_names = [g.scenario.scenario_name for g in result.generated_scenarios]
    print(f"\nTest 2 generated: {generated_names}")

    assert any("Ferric" in n for n in generated_names), \
        f"Expected a Ferric Dosing scenario, got {generated_names}"

    ferric_sc = next(
        g.scenario for g in result.generated_scenarios if "Ferric" in g.scenario.scenario_name
    )

    # Ferric retrofit should have increased OPEX
    assert ferric_sc.cost_result.opex_annual > bnr.cost_result.opex_annual, \
        "Ferric scenario must have higher OPEX (chemical cost)"

    # TP should be updated to target in performance outputs
    tc = "bnr"
    po_gen = (ferric_sc.domain_specific_outputs.get("technology_performance") or {}).get(tc, {})
    assert po_gen.get("effluent_tp_mg_l") == 0.5, \
        f"TP should be updated to target 0.5, got {po_gen.get('effluent_tp_mg_l')}"

    print(f"  Generated: {ferric_sc.scenario_name}")
    print(f"  OPEX delta: +${(ferric_sc.cost_result.opex_annual - bnr.cost_result.opex_annual)/1e3:.0f}k/yr")
    print(f"  TP after:   {po_gen.get('effluent_tp_mg_l')} mg/L")
    print("Test 2 PASS ✅")


# ── Test 3: BNR capacity issue → IFAS scenario ────────────────────────────────

def test_bnr_capacity_generates_ifas():
    """
    BNR where existing bioreactor is undersized (volume constraint WARNING).
    Generator must produce an IFAS retrofit scenario.
    """
    po = {
        "effluent_tp_mg_l":        0.5,
        "effluent_tn_mg_l":        5.0,
        "compliance_flag":         "Meets Targets",
        "reactor_volume_m3":       3011.0,
        "v_aerobic_m3":            1656.0,
        "clarifier_area_m2":       417.0,
        "n_clarifiers":            2,
        "aeration_energy_kwh_day": 2109.7,
        "footprint_m2":            1086.0,
        "peak_flow_factor":        1.5,
    }
    bnr = _make_scenario("bnr", "Base Case", "bnr", po)
    inp = _make_inputs()
    # Existing bioreactor only 1800 m³ — less than required 3011 m³
    bf  = BrownfieldContext(
        anaerobic_volume_m3=150.0, anoxic_volume_m3=450.0, aerobic_volume_m3=1200.0,
        clarifier_area_m2=600.0, clarifier_count=2,
        blower_capacity_kw=200.0, ras_capacity_m3_d=15000.0, mlr_capacity_m3_d=45000.0,
        available_footprint_m2=3000.0, can_add_new_tank=True, max_shutdown_days=30,
    )

    result = generate([bnr], bf, inputs=inp)

    generated_names = [g.scenario.scenario_name for g in result.generated_scenarios]
    print(f"\nTest 3 generated: {generated_names}")

    assert any("IFAS" in n for n in generated_names), \
        f"Expected an IFAS retrofit scenario, got {generated_names}"

    # Verify CAPEX is higher for IFAS scenario
    ifas_sc = next(
        g.scenario for g in result.generated_scenarios if "IFAS" in g.scenario.scenario_name
    )
    assert ifas_sc.cost_result.capex_total > bnr.cost_result.capex_total
    assert getattr(ifas_sc, "brownfield_retrofit_code") == "BF-02"

    print(f"  Generated: {ifas_sc.scenario_name}")
    print(f"  CAPEX:  ${ifas_sc.cost_result.capex_total/1e6:.2f}M")
    print("Test 3 PASS ✅")


# ── Test 4: MBBR fully feasible → no new scenarios ───────────────────────────

def test_mbbr_feasible_no_generated():
    """
    MBBR (ifas_mbbr) with all constraints PASS and TP/TN compliant.
    Generator must produce NO new scenarios.
    """
    po = {
        "effluent_tp_mg_l":        0.5,
        "effluent_tn_mg_l":        5.0,
        "compliance_flag":         "Meets Targets",
        "reactor_volume_m3":       3360.0,
        "aeration_energy_kwh_day": 1921.1,
        "footprint_m2":            1163.0,
        "peak_flow_factor":        1.5,
        "peak_fill_ratio":         0.0,   # not an SBR — no fill ratio concern
    }
    mbbr = _make_scenario("mbbr", "MBBR", "ifas_mbbr", po, capex_m=8.5, opex_kyr=720.0)
    inp  = _make_inputs()
    bf   = BrownfieldContext(
        anaerobic_volume_m3=0, anoxic_volume_m3=1000.0, aerobic_volume_m3=2500.0,
        clarifier_area_m2=700.0, clarifier_count=2,
        blower_capacity_kw=250.0, ras_capacity_m3_d=15000.0, mlr_capacity_m3_d=0.0,
        available_footprint_m2=3000.0, can_add_new_tank=True, max_shutdown_days=30,
    )

    result = generate([mbbr], bf, inputs=inp)

    print(f"\nTest 4 generated: {[g.scenario.scenario_name for g in result.generated_scenarios]}")
    assert result.total_count == 1, \
        f"Expected 1 scenario (base only), got {result.total_count}"
    assert len(result.generated_scenarios) == 0, \
        f"Expected 0 generated, got {len(result.generated_scenarios)}"

    log = result.generation_log[0]
    print(f"  Log action: {log['action']} — {log['reason']}")
    assert log["action"] in ("skipped", "no_retrofits"), \
        f"Expected skipped or no_retrofits, got {log['action']}"

    print("Test 4 PASS ✅")


# ── Test 5: Multiple issues → max 2 retrofit scenarios ───────────────────────

def test_multiple_issues_max_two():
    """
    BNR with TP non-compliance AND clarifier SOR overload.
    Multiple retrofits applicable — generator must cap at MAX_RETROFITS_PER_BASE = 2.
    """
    po = {
        "effluent_tp_mg_l":          0.8,   # TP non-compliant
        "effluent_tn_mg_l":          5.0,
        "compliance_flag":           "Review Required",
        "reactor_volume_m3":         3011.0,
        "v_aerobic_m3":              1656.0,
        "clarifier_area_m2":         417.0,
        "n_clarifiers":              2,
        "aeration_energy_kwh_day":   2109.7,
        "footprint_m2":              1086.0,
        "sludge_production_kgds_day": 1396.4,
        "peak_flow_factor":          1.5,
    }
    bnr = _make_scenario("bnr", "Base Case", "bnr", po,
                          is_compliant=False, compliance_status="Non-compliant")
    inp = _make_inputs(tp=0.5)
    bf  = BrownfieldContext(
        anaerobic_volume_m3=150.0, anoxic_volume_m3=450.0, aerobic_volume_m3=1200.0,
        clarifier_area_m2=100.0, clarifier_count=1,   # ← tiny clarifier → FAIL
        blower_capacity_kw=200.0, ras_capacity_m3_d=15000.0, mlr_capacity_m3_d=45000.0,
        available_footprint_m2=3000.0, can_add_new_tank=True, max_shutdown_days=30,
    )

    result = generate([bnr], bf, inputs=inp)

    generated_names = [g.scenario.scenario_name for g in result.generated_scenarios]
    print(f"\nTest 5 generated ({len(result.generated_scenarios)}): {generated_names}")

    # Must not exceed max cap
    assert len(result.generated_scenarios) <= MAX_RETROFITS_PER_BASE, \
        f"Generator must not produce more than {MAX_RETROFITS_PER_BASE} per base. Got {len(result.generated_scenarios)}"

    # Must have produced at least 1
    assert len(result.generated_scenarios) >= 1, \
        "Generator must produce at least one scenario for a scenario with issues"

    # Priority: ferric (BF-01) must be first since TP is the hardest gate
    first_code = result.generated_scenarios[0].retrofit_code   # on GeneratedScenario
    assert first_code == "BF-01", \
        f"First generated scenario must be BF-01 (ferric). Got {first_code}"

    print(f"  First: {result.generated_scenarios[0].scenario.scenario_name} [{first_code}]")
    if len(result.generated_scenarios) > 1:
        second_code = result.generated_scenarios[1].retrofit_code
        print(f"  Second: {result.generated_scenarios[1].scenario.scenario_name} [{second_code}]")

    print("Test 5 PASS ✅")


# ── Bonus: all_scenario_models convenience property ───────────────────────────

def test_all_scenario_models_property():
    """all_scenario_models returns base + generated as a flat ScenarioModel list."""
    po = {
        "effluent_tp_mg_l":    0.8,
        "effluent_tn_mg_l":    5.0,
        "compliance_flag":     "Review Required",
        "reactor_volume_m3":   3011.0,
        "v_aerobic_m3":        1656.0,
        "clarifier_area_m2":   417.0,
        "n_clarifiers":        2,
        "aeration_energy_kwh_day": 2109.7,
        "peak_flow_factor":    1.5,
    }
    bnr = _make_scenario("bnr", "Base Case", "bnr", po,
                          is_compliant=False, compliance_status="Non-compliant")
    inp = _make_inputs(tp=0.5)
    bf  = BrownfieldContext(
        anaerobic_volume_m3=276.0, anoxic_volume_m3=827.0, aerobic_volume_m3=1656.0,
        clarifier_area_m2=417.0, clarifier_count=2,
        blower_capacity_kw=150.0, ras_capacity_m3_d=12000.0, mlr_capacity_m3_d=40000.0,
        available_footprint_m2=2000.0, can_add_new_tank=True, max_shutdown_days=30,
    )
    result = generate([bnr], bf, inputs=inp)

    all_sc = result.all_scenario_models
    assert len(all_sc) == result.total_count
    assert all(hasattr(s, "cost_result") for s in all_sc), \
        "All scenario models must have cost_result"
    assert all(hasattr(s, "scenario_name") for s in all_sc)
    print(f"\nBonus: all_scenario_models = {[s.scenario_name for s in all_sc]}")
    print("Bonus test PASS ✅")


# ── Runner ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    tests = [
        test_nereda_fail_generates_reactor,
        test_bnr_tp_issue_generates_ferric,
        test_bnr_capacity_generates_ifas,
        test_mbbr_feasible_no_generated,
        test_multiple_issues_max_two,
        test_all_scenario_models_property,
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
    print(f"\n{'='*60}")
    print(f"  {passed}/{passed+failed} tests passed")
    if failed:
        raise SystemExit(1)
