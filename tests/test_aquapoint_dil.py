"""
tests/test_aquapoint_dil.py

AquaPoint Decision Intelligence Layer — regression test suite
=============================================================

5 engineering-calibrated cases:
  Case 1: High-risk surface water, PFAS detected but unquantified
          → High criticality, Not Decision-Ready (PFAS blocks selection)
  Case 2: Low-risk groundwater, clean
          → Low criticality, Proceed with Conditions (single-barrier condition)
  Case 3: Large metro reservoir, algae, cyanotoxin, extreme variability
          → High criticality, Not Decision-Ready (event characterisation blocks)
  Case 4: Small remote plant
          → Medium criticality (remote floor), Proceed with Conditions
  Case 5: Arsenic-affected groundwater
          → Medium/High criticality, residuals disposal High VOI
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from apps.drinking_water_app.engine.reasoning.classifier import SourceWaterInputs
from apps.drinking_water_app.engine.reasoning.engine import run_reasoning_engine
from apps.drinking_water_app.engine.dil_aquapoint import (
    build_aquapoint_dil,
    CRIT_LOW, CRIT_MEDIUM, CRIT_HIGH,
    DR_READY, DR_CONDITIONS, DR_NOT_READY,
)


def _run(inputs: SourceWaterInputs):
    reasoning = run_reasoning_engine(inputs)
    return build_aquapoint_dil(inputs, reasoning)


def _assert_structure(di) -> None:
    assert di.closing_statement.startswith("WaterPoint does not seek"), (
        f"Wrong closing statement: {di.closing_statement[:60]}"
    )
    assert di.criticality.level in (CRIT_LOW, CRIT_MEDIUM, CRIT_HIGH)
    assert di.readiness.status in (DR_READY, DR_CONDITIONS, DR_NOT_READY)
    assert di.data_confidence.overall_confidence in ("High", "Acceptable", "Low", "Very Low")
    assert len(di.voi.dimensions) >= 1, "No VOI dimensions"
    assert len(di.risk_ownership.dimensions) >= 5, (
        f"Only {len(di.risk_ownership.dimensions)} risk dims"
    )
    assert di.risk_ownership.utility_accountability_statement
    assert di.risk_ownership.residual_risk_statement
    assert len(di.decision_boundary.monitoring_requirements) >= 4
    assert len(di.decision_boundary.critical_assumptions) >= 4
    assert len(di.decision_boundary.intervention_triggers) >= 3
    assert di.decision_boundary.fallback_position
    assert di.readiness.basis
    assert di.readiness.strategic_implication


# ── Case 1: PFAS detected unquantified — Not Decision-Ready ──────────────────

def test_aq_dil_high_risk_pfas_unquantified():
    """
    50 ML/d surface water. PFAS detected, concentration unknown.
    High catchment risk, high variability.
    Expected: High criticality, Not Decision-Ready.
    PFAS speciation must be High VOI.
    """
    inputs = SourceWaterInputs(
        source_type="river", turbidity_median_ntu=8.0, turbidity_p95_ntu=40.0,
        turbidity_p99_ntu=120.0, toc_median_mg_l=8.0, toc_p95_mg_l=15.0,
        colour_median_hu=25.0, algae_risk="moderate", catchment_risk="high",
        variability_class="high", pfas_detected=True, pfas_concentration_ng_l=0.0,
        hardness_median_mg_l=80.0, alkalinity_median_mg_l=60.0,
        iron_median_mg_l=0.2, manganese_median_mg_l=0.05, arsenic_ug_l=0.0,
        tds_median_mg_l=200.0, ph_median=7.2, ph_min=6.8,
        pathogen_lrv_required_protozoa=5.0, pathogen_lrv_required_bacteria=7.0,
        pathogen_lrv_required_virus=7.0, design_flow_ML_d=50.0,
        is_retrofit=False, land_constrained=False, remote_operation=False,
        treatment_objective="potable",
    )
    di = _run(inputs)
    _assert_structure(di)

    assert di.criticality.level == CRIT_HIGH, (
        f"Expected High for PFAS unquantified high-risk surface water, got {di.criticality.level}"
    )
    assert di.readiness.status in (DR_NOT_READY, DR_CONDITIONS), (
        f"PFAS unquantified should block or condition, got {di.readiness.status}"
    )
    assert "PFAS speciation and concentration" in di.voi.high_voi_items, (
        f"PFAS must be High VOI when unquantified, got {di.voi.high_voi_items}"
    )
    # Utility must own public health risk
    risk_owners = {d.risk_category: d.primary_owner for d in di.risk_ownership.dimensions}
    assert risk_owners.get("Public health and regulatory compliance") == "Utility"


# ── Case 2: Low-risk groundwater — Proceed with Conditions ───────────────────

def test_aq_dil_low_risk_groundwater():
    """
    5 ML/d clean groundwater. Low catchment risk, low variability, no contaminants.
    Expected: Low criticality. Ready or Proceed with Conditions.
    DBP monitoring must be Low VOI.
    """
    inputs = SourceWaterInputs(
        source_type="groundwater", turbidity_median_ntu=0.5, turbidity_p95_ntu=1.0,
        turbidity_p99_ntu=2.0, toc_median_mg_l=1.5, toc_p95_mg_l=2.5,
        colour_median_hu=5.0, algae_risk="low", catchment_risk="low",
        variability_class="low", pfas_detected=False, pfas_concentration_ng_l=0.0,
        hardness_median_mg_l=200.0, alkalinity_median_mg_l=180.0,
        iron_median_mg_l=0.05, manganese_median_mg_l=0.01, arsenic_ug_l=0.0,
        tds_median_mg_l=400.0, ph_median=7.8, ph_min=7.5,
        pathogen_lrv_required_protozoa=4.0, pathogen_lrv_required_bacteria=6.0,
        pathogen_lrv_required_virus=6.0, design_flow_ML_d=5.0,
        is_retrofit=False, land_constrained=False, remote_operation=False,
        treatment_objective="potable",
    )
    di = _run(inputs)
    _assert_structure(di)

    assert di.criticality.level in (CRIT_LOW, CRIT_MEDIUM), (
        f"Expected Low/Medium for clean groundwater, got {di.criticality.level}"
    )
    assert di.readiness.status in (DR_READY, DR_CONDITIONS), (
        f"Expected Ready or Conditions for clean groundwater, got {di.readiness.status}"
    )
    assert "Disinfection by-product (DBP) formation monitoring" in di.voi.low_voi_items, (
        f"DBP must be Low VOI, got {di.voi.low_voi_items}"
    )


# ── Case 3: Large metro algal reservoir — Not Decision-Ready ──────────────────

def test_aq_dil_large_metro_algal():
    """
    200 ML/d metro reservoir. Cyanobacteria confirmed, cyanotoxin detected.
    Very high catchment risk, extreme variability.
    Expected: High criticality, Not Decision-Ready.
    Event characterisation must be High VOI.
    """
    inputs = SourceWaterInputs(
        source_type="reservoir", turbidity_median_ntu=5.0, turbidity_p95_ntu=30.0,
        turbidity_p99_ntu=150.0, toc_median_mg_l=10.0, toc_p95_mg_l=18.0,
        colour_median_hu=30.0, algae_risk="high", cyanobacteria_confirmed=True,
        cyanotoxin_detected=True, mib_geosmin_issue=True,
        catchment_risk="very_high", variability_class="extreme",
        pfas_detected=False, pfas_concentration_ng_l=0.0,
        hardness_median_mg_l=60.0, alkalinity_median_mg_l=40.0,
        iron_median_mg_l=0.3, manganese_median_mg_l=0.1, arsenic_ug_l=0.0,
        tds_median_mg_l=150.0, ph_median=7.0, ph_min=6.5,
        pathogen_lrv_required_protozoa=6.0, pathogen_lrv_required_bacteria=8.0,
        pathogen_lrv_required_virus=8.0, design_flow_ML_d=200.0,
        is_retrofit=False, land_constrained=True, remote_operation=False,
        treatment_objective="potable",
    )
    di = _run(inputs)
    _assert_structure(di)

    assert di.criticality.level == CRIT_HIGH, (
        f"Expected High for large metro algal reservoir, got {di.criticality.level}"
    )
    assert di.readiness.status in (DR_NOT_READY, DR_CONDITIONS), (
        f"Expected Not Ready or Conditions for extreme variability, got {di.readiness.status}"
    )
    assert "Event-based source water characterisation (P99+ conditions)" in di.voi.high_voi_items, (
        f"Event characterisation must be High VOI for extreme variability"
    )
    # Utility owns source/catchment risk
    risk_categories = [d.risk_category for d in di.risk_ownership.dimensions]
    assert "Source water quality and catchment risk" in risk_categories


# ── Case 4: Small remote plant — Medium criticality floor ────────────────────

def test_aq_dil_small_remote():
    """
    2 ML/d remote plant. Moderate catchment risk, moderate variability.
    Expected: Medium or High criticality — remote operation floors to Medium.
    Readiness: Proceed with Conditions.
    """
    inputs = SourceWaterInputs(
        source_type="river", turbidity_median_ntu=3.0, turbidity_p95_ntu=15.0,
        turbidity_p99_ntu=50.0, toc_median_mg_l=4.0, toc_p95_mg_l=8.0,
        colour_median_hu=12.0, algae_risk="low", catchment_risk="moderate",
        variability_class="moderate", pfas_detected=False, pfas_concentration_ng_l=0.0,
        hardness_median_mg_l=100.0, alkalinity_median_mg_l=80.0,
        iron_median_mg_l=0.1, manganese_median_mg_l=0.02, arsenic_ug_l=0.0,
        tds_median_mg_l=250.0, ph_median=7.5, ph_min=7.0,
        pathogen_lrv_required_protozoa=4.0, pathogen_lrv_required_bacteria=6.0,
        pathogen_lrv_required_virus=6.0, design_flow_ML_d=2.0,
        is_retrofit=False, land_constrained=False, remote_operation=True,
        treatment_objective="potable",
    )
    di = _run(inputs)
    _assert_structure(di)

    assert di.criticality.level in (CRIT_MEDIUM, CRIT_HIGH), (
        f"Remote operation must floor to Medium criticality, got {di.criticality.level}"
    )
    assert di.readiness.status in (DR_CONDITIONS, DR_NOT_READY), (
        f"Expected Conditions or Not Ready for remote plant, got {di.readiness.status}"
    )


# ── Case 5: Arsenic-affected groundwater — classified waste VOI ───────────────

def test_aq_dil_arsenic_groundwater():
    """
    8 ML/d groundwater with arsenic 25 µg/L (above ADWG 10 µg/L).
    Expected: Medium/High criticality (regulatory exposure + classified waste).
    Residuals disposal must be High VOI (arsenic-bearing classified waste).
    """
    inputs = SourceWaterInputs(
        source_type="groundwater", turbidity_median_ntu=0.3, turbidity_p95_ntu=0.8,
        turbidity_p99_ntu=1.5, toc_median_mg_l=1.0, toc_p95_mg_l=2.0,
        colour_median_hu=3.0, algae_risk="low", catchment_risk="low",
        variability_class="low", pfas_detected=False, pfas_concentration_ng_l=0.0,
        hardness_median_mg_l=300.0, alkalinity_median_mg_l=250.0,
        iron_median_mg_l=0.3, manganese_median_mg_l=0.05,
        arsenic_ug_l=25.0, tds_median_mg_l=600.0, ph_median=7.5, ph_min=7.2,
        pathogen_lrv_required_protozoa=4.0, pathogen_lrv_required_bacteria=6.0,
        pathogen_lrv_required_virus=6.0, design_flow_ML_d=8.0,
        is_retrofit=False, land_constrained=False, remote_operation=False,
        treatment_objective="potable",
    )
    di = _run(inputs)
    _assert_structure(di)

    assert di.criticality.level in (CRIT_MEDIUM, CRIT_HIGH), (
        f"Arsenic above ADWG should elevate criticality, got {di.criticality.level}"
    )
    assert "Residuals classification and disposal pathway confirmation" in di.voi.high_voi_items, (
        f"Residuals disposal must be High VOI for arsenic-bearing classified waste"
    )
    # Utility owns contaminant/residuals risk
    risk_categories = [d.risk_category for d in di.risk_ownership.dimensions]
    assert "Contaminant management and residuals" in risk_categories


# ── Standalone runner ─────────────────────────────────────────────────────────

def _run_all() -> bool:
    tests = [
        test_aq_dil_high_risk_pfas_unquantified,
        test_aq_dil_low_risk_groundwater,
        test_aq_dil_large_metro_algal,
        test_aq_dil_small_remote,
        test_aq_dil_arsenic_groundwater,
    ]
    passed = failed = 0
    print("\nAquaPoint DIL — Test Suite")
    print("=" * 55)
    for fn in tests:
        try:
            fn()
            print(f"  PASS  {fn.__name__}")
            passed += 1
        except Exception as exc:
            print(f"  FAIL  {fn.__name__}: {exc}")
            failed += 1
    print(f"\n  {passed} passed, {failed} failed")
    if failed == 0:
        print("  ✅ ALL AQUAPOINT DIL TESTS PASSED")
    else:
        print("  ❌ FAILURES DETECTED")
    return failed == 0


if __name__ == "__main__":
    success = _run_all()
    sys.exit(0 if success else 1)
