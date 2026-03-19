"""
tests/test_brownfield_retrofits.py

Mandatory test cases for the Brownfield Retrofit Library.

Tests:
  1. Base Case with TP non-compliance → ferric applicable
  2. Base Case with clarifier overload → clarifier expansion applicable
  3. Base Case with biological capacity issue → IFAS and MABR applicable
  4. NEREDA with fill ratio fail → additional SBR reactor applicable
  5. MBBR with no clarifier issue → clarifier expansion NOT applicable

Also tests get_brownfield_retrofit_options() filtering behaviour.
"""
from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from domains.wastewater.brownfield.brownfield_context import BrownfieldContext
from domains.wastewater.brownfield.constraint_engine import evaluate
from domains.wastewater.brownfield.retrofit_library import (
    get_brownfield_retrofit_options,
    evaluate_retrofit_applicability,
    get_all_options,
)
from domains.wastewater.brownfield.retrofit_models import RetrofitOption, RetrofitApplicationResult


# ── Shared fixture helpers ────────────────────────────────────────────────────

def _make_inputs(
    flow_mld=10.0, peak_factor=1.5,
    effluent_tp_mg_l=0.5, effluent_tn_mg_l=5.0,
):
    class _Inp:
        design_flow_mld     = flow_mld
        peak_flow_factor    = peak_factor
        peak_flow_mld       = None
        effluent_tp_mg_l_v  = effluent_tp_mg_l
        effluent_tn_mg_l_v  = effluent_tn_mg_l
    _Inp.effluent_tp_mg_l = effluent_tp_mg_l
    _Inp.effluent_tn_mg_l = effluent_tn_mg_l
    return _Inp()


def _make_dso(tech_code: str, po: dict) -> dict:
    """Wrap performance_outputs in domain_specific_outputs structure."""
    return {"technology_performance": {tech_code: po}}


def _make_tech_result(po: dict, footprint=1029.0, volume=2755.0):
    class _TR:
        performance_outputs = po
        footprint_m2        = footprint
        volume_m3           = volume
    return _TR()


def _make_bf(
    anaerobic=276.0, anoxic=827.0, aerobic=1653.0,
    clarifier_area=417.0, clarifier_count=2,
    blower_kw=150.0, ras_m3d=12000.0, mlr_m3d=40000.0,
    footprint=1500.0, can_add=True, shutdown=30,
) -> BrownfieldContext:
    return BrownfieldContext(
        anaerobic_volume_m3     = anaerobic,
        anoxic_volume_m3        = anoxic,
        aerobic_volume_m3       = aerobic,
        clarifier_area_m2       = clarifier_area,
        clarifier_count         = clarifier_count,
        blower_capacity_kw      = blower_kw,
        ras_capacity_m3_d       = ras_m3d,
        mlr_capacity_m3_d       = mlr_m3d,
        available_footprint_m2  = footprint,
        can_add_new_tank        = can_add,
        max_shutdown_days       = shutdown,
    )


# ── Test 1: Base Case with TP non-compliance → ferric applicable ──────────────

def test_tp_noncompliance_ferric_applicable():
    """
    BNR scenario where effluent TP = 0.8 mg/L > target 0.5 mg/L.
    Ferric dosing (BF-01) must be returned as applicable.
    Clarifier expansion (BF-04) must NOT be returned (no SOR issue).
    """
    po = {
        "effluent_tp_mg_l":          0.8,
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
    dso    = _make_dso("bnr", po)
    inputs = _make_inputs(effluent_tp_mg_l=0.5)
    bf     = _make_bf()

    # Run constraint check (clarifier OK here — area 417 m² × 2 = 834 m²)
    tr_proxy = _make_tech_result(po)
    constraint = evaluate("Base Case", "bnr", tr_proxy, inputs, bf)

    # Get candidate retrofits
    options = get_brownfield_retrofit_options("bnr", dso, constraint, inputs, bf)
    codes   = [o.code for o in options]
    print(f"\nTest 1 options returned: {codes}")
    assert "BF-01" in codes, "Ferric (BF-01) must be a candidate for TP non-compliance"

    # Evaluate ferric applicability
    ferric  = get_all_options()["BF-01"]
    result  = evaluate_retrofit_applicability(ferric, "bnr", dso, constraint, inputs, bf)

    assert result.applicable,                      f"Ferric must be applicable. Reason: {result.reason}"
    assert result.capex_delta_m > 0,               "Ferric must have positive CAPEX delta"
    assert result.opex_delta_kyr > 0,              "Ferric must have positive OPEX delta"
    assert result.updated_performance.get("effluent_tp_mg_l") == 0.5, \
        "Updated TP must equal target"
    assert "updated_constraints" in result.__dict__
    assert result.updated_constraints.get("TP compliance") == "PASS"

    print(f"  Ferric result: {result.summary()}")
    print(f"  CAPEX: ${result.capex_delta_m:.2f}M  OPEX: ${result.opex_delta_kyr:.0f}k/yr")
    print(f"  Trade-off: {result.trade_off[:80]}")
    print("Test 1 PASS ✅")


# ── Test 2: Base Case with clarifier overload → clarifier expansion applicable ─

def test_clarifier_overload_expansion_applicable():
    """
    BNR with single small clarifier — SOR exceeds limit at peak.
    Clarifier expansion (BF-04) must be applicable.
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
    dso    = _make_dso("bnr", po)
    inputs = _make_inputs(effluent_tp_mg_l=0.5)
    # Existing plant has one tiny clarifier → SOR >> 1.5 m/hr
    bf = _make_bf(clarifier_area=100.0, clarifier_count=1)

    tr_proxy   = _make_tech_result(po)
    constraint = evaluate("Base Case", "bnr", tr_proxy, inputs, bf)

    # SOR check should FAIL
    sor_check = next(c for c in constraint.checks if c.name == "Clarifier SOR")
    assert sor_check.status == "FAIL", \
        f"Expected clarifier SOR FAIL, got {sor_check.status}"

    options = get_brownfield_retrofit_options("bnr", dso, constraint, inputs, bf)
    codes   = [o.code for o in options]
    print(f"\nTest 2 options returned: {codes}")
    assert "BF-04" in codes, "Clarifier expansion (BF-04) must be a candidate"

    clarifier_ret = get_all_options()["BF-04"]
    result        = evaluate_retrofit_applicability(
        clarifier_ret, "bnr", dso, constraint, inputs, bf
    )

    assert result.applicable,          f"Clarifier expansion must be applicable. {result.reason}"
    assert result.capex_delta_m > 0,   "Must have positive CAPEX"
    assert result.updated_constraints.get("Clarifier SOR") == "PASS"

    print(f"  Clarifier result: {result.summary()}")
    print(f"  CAPEX: ${result.capex_delta_m:.2f}M")
    print("Test 2 PASS ✅")


# ── Test 3: BNR with biological capacity shortfall → IFAS and MABR applicable ─

def test_volume_shortfall_ifas_mabr_applicable():
    """
    BNR where existing bioreactor volume is 40% short of required.
    Both IFAS (BF-02) and MABR (BF-03) must be applicable.
    Ferric (BF-01) not applicable (TP is compliant).
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
    dso    = _make_dso("bnr", po)
    inputs = _make_inputs(effluent_tp_mg_l=0.5)
    # Existing bioreactor only 1800 m³ — far less than required 3011 m³
    bf = _make_bf(anaerobic=150.0, anoxic=450.0, aerobic=1200.0,  # total 1800
                  can_add=True, footprint=2000.0, shutdown=30)

    tr_proxy   = _make_tech_result(po)
    constraint = evaluate("Base Case", "bnr", tr_proxy, inputs, bf)

    # Volume check should be WARNING (can_add=True)
    vol_check = next(c for c in constraint.checks if c.name == "Biological Volume")
    assert vol_check.status in ("WARNING", "FAIL"), \
        f"Expected volume WARNING or FAIL, got {vol_check.status}"

    options = get_brownfield_retrofit_options("bnr", dso, constraint, inputs, bf)
    codes   = [o.code for o in options]
    print(f"\nTest 3 options returned: {codes}")
    assert "BF-02" in codes, "IFAS (BF-02) must be a candidate for volume shortfall"
    assert "BF-03" in codes, "MABR (BF-03) must be a candidate for volume shortfall"

    # Evaluate both
    lib = get_all_options()
    for code in ["BF-02", "BF-03"]:
        result = evaluate_retrofit_applicability(lib[code], "bnr", dso, constraint, inputs, bf)
        assert result.applicable, f"{code} must be applicable. {result.reason}"
        assert result.capex_delta_m > 0
        print(f"  {code}: {result.summary()}")

    # Ferric should NOT be applicable (TP is compliant)
    ferric_result = evaluate_retrofit_applicability(lib["BF-01"], "bnr", dso, constraint, inputs, bf)
    assert not ferric_result.applicable, \
        f"Ferric must NOT be applicable when TP is compliant. Got: {ferric_result.reason}"

    print("Test 3 PASS ✅")


# ── Test 4: NEREDA fill ratio fail → additional SBR reactor applicable ────────

def test_nereda_fill_ratio_sbr_applicable():
    """
    Nereda (granular_sludge) with peak_fill_ratio = 1.00 (at limit → FAIL).
    BF-05 (additional SBR reactor) must be applicable.
    BF-04 (clarifier expansion) must NOT be applicable (AGS has no clarifiers).
    """
    po = {
        "effluent_tp_mg_l":        0.5,
        "effluent_tn_mg_l":        5.0,
        "compliance_flag":         "Meets Targets",
        "reactor_volume_m3":       2083.0,
        "vol_per_reactor_m3":      694.0,
        "n_reactors":              3,
        "peak_fill_ratio":         1.00,
        "peak_flow_factor":        1.5,
        "aeration_energy_kwh_day": 2054.2,
        "footprint_m2":            949.0,
    }
    dso    = _make_dso("granular_sludge", po)
    inputs = _make_inputs(effluent_tp_mg_l=0.5)
    bf     = _make_bf(
        anaerobic=0, anoxic=0, aerobic=2083.0,
        clarifier_area=0.0, clarifier_count=0,
        ras_m3d=0.0, mlr_m3d=0.0,
        can_add=True, footprint=2000.0,
    )

    tr_proxy   = _make_tech_result(po, footprint=949.0, volume=2083.0)
    constraint = evaluate("NEREDA", "granular_sludge", tr_proxy, inputs, bf)

    # The brownfield constraint engine does not check SBR fill ratio directly —
    # that is handled by hydraulic_stress.py which runs separately.
    # The retrofit library checks po["peak_fill_ratio"] >= 0.85 to determine applicability.
    # Verify the constraint result itself doesn't block this test:
    assert constraint is not None, "Constraint result must be produced"
    # Fill ratio ≥ 0.95 → BF-05 should be triggered by get_brownfield_retrofit_options

    options = get_brownfield_retrofit_options("granular_sludge", dso, constraint, inputs, bf)
    codes   = [o.code for o in options]
    print(f"\nTest 4 options returned: {codes}")
    assert "BF-05" in codes, "Additional SBR reactor (BF-05) must be a candidate"

    sbr_ret = get_all_options()["BF-05"]
    result  = evaluate_retrofit_applicability(
        sbr_ret, "granular_sludge", dso, constraint, inputs, bf
    )

    assert result.applicable, f"BF-05 must be applicable. {result.reason}"
    assert result.capex_delta_m > 0
    assert "peak_fill_ratio" in result.updated_performance
    assert result.updated_performance["peak_fill_ratio"] < 0.90, \
        "Fill ratio after retrofit must be below 0.90"
    assert result.updated_performance["n_reactors"] == 4

    # Clarifier expansion must NOT be applicable (AGS has no clarifiers)
    clarifier_ret  = get_all_options()["BF-04"]
    clarifier_result = evaluate_retrofit_applicability(
        clarifier_ret, "granular_sludge", dso, constraint, inputs, bf
    )
    assert not clarifier_result.applicable, \
        f"Clarifier expansion must NOT be applicable for AGS. Got: {clarifier_result.reason}"

    print(f"  SBR reactor result: {result.summary()}")
    print(f"  Fill ratio: {result.updated_performance['peak_fill_ratio']:.2f}")
    print(f"  N reactors: {result.updated_performance['n_reactors']}")
    print("Test 4 PASS ✅")


# ── Test 5: MBBR with no clarifier issue → clarifier expansion not applicable ─

def test_mbbr_no_clarifier_issue_expansion_not_applicable():
    """
    IFAS/MBBR scenario where clarifier SOR is within limits.
    Clarifier expansion (BF-04) must NOT be applicable.
    """
    po = {
        "effluent_tp_mg_l":        0.5,
        "effluent_tn_mg_l":        5.0,
        "compliance_flag":         "Meets Targets",
        "reactor_volume_m3":       3360.0,
        "aeration_energy_kwh_day": 1921.1,
        "footprint_m2":            1163.0,
        "peak_flow_factor":        1.5,
    }
    dso    = _make_dso("ifas_mbbr", po)
    inputs = _make_inputs(effluent_tp_mg_l=0.5)
    # Generous clarifiers — SOR well within limits
    bf = _make_bf(
        anaerobic=0.0, anoxic=1000.0, aerobic=2400.0,
        clarifier_area=600.0, clarifier_count=2,  # total 1200 m²
        blower_kw=200.0, ras_m3d=12000.0, mlr_m3d=0.0,
        footprint=3000.0, can_add=True, shutdown=30,
    )

    tr_proxy   = _make_tech_result(po, footprint=1163.0, volume=3360.0)
    constraint = evaluate("MBBR", "ifas_mbbr", tr_proxy, inputs, bf)

    # Clarifier check: SOR = 15000/24 / (1200) = 0.52 m/hr → well within 1.5
    sor_check = next((c for c in constraint.checks if c.name == "Clarifier SOR"), None)
    # Note: ifas_mbbr has clarifier_area_m2=None in perf_outputs (no clarifier in model)
    # The constraint engine skips SOR for ifas_mbbr — confirm SKIP or PASS
    if sor_check:
        assert sor_check.status in ("PASS", "SKIP"), \
            f"Expected PASS/SKIP for SOR, got {sor_check.status}"

    options = get_brownfield_retrofit_options("ifas_mbbr", dso, constraint, inputs, bf)
    codes   = [o.code for o in options]
    print(f"\nTest 5 options returned: {codes}")

    clarifier_ret  = get_all_options()["BF-04"]
    clarifier_result = evaluate_retrofit_applicability(
        clarifier_ret, "ifas_mbbr", dso, constraint, inputs, bf
    )

    # IFAS/MBBR: clarifier expansion not applicable (tech has no conventional clarifiers)
    assert not clarifier_result.applicable, (
        f"Clarifier expansion must NOT be applicable for ifas_mbbr. "
        f"Got: {clarifier_result.reason}"
    )

    print(f"  Clarifier expansion result: {clarifier_result.reason}")
    print("Test 5 PASS ✅")


# ── Bonus test: library integrity ─────────────────────────────────────────────

def test_library_integrity():
    """All 5 options are present, all required fields are populated."""
    lib = get_all_options()
    expected_codes = {"BF-01", "BF-02", "BF-03", "BF-04", "BF-05"}
    assert set(lib.keys()) == expected_codes, \
        f"Library codes mismatch. Got: {set(lib.keys())}"

    for code, opt in lib.items():
        assert opt.code    == code,   f"{code}: code field mismatch"
        assert opt.name,              f"{code}: name is empty"
        assert opt.description,       f"{code}: description is empty"
        assert len(opt.notes) > 0,    f"{code}: notes list is empty"
        assert opt.shutdown_days >= 0, f"{code}: negative shutdown_days"
        assert isinstance(opt.can_stage, bool), f"{code}: can_stage not bool"

    print("Library integrity PASS ✅")


# ── Runner ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    tests = [
        test_tp_noncompliance_ferric_applicable,
        test_clarifier_overload_expansion_applicable,
        test_volume_shortfall_ifas_mabr_applicable,
        test_nereda_fill_ratio_sbr_applicable,
        test_mbbr_no_clarifier_issue_expansion_not_applicable,
        test_library_integrity,
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
