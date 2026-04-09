"""
tests/test_biosolids_dil.py

BioPoint Decision Intelligence Layer — regression test suite
============================================================

4 engineering-calibrated cases:
  Case 1: Metro 137 tDS/d, PFAS unknown, pyrolysis candidate
          → Not Decision-Ready (PFAS blocks commitment)
  Case 2: Regional 25 tDS/d, PFAS absent, balanced objective
          → Ready to Proceed or Proceed with Conditions
  Case 3: Large 80 tDS/d, PFAS confirmed, incineration
          → High criticality (PFAS + scale + thermal capital)
  Case 4: Small 8 tDS/d, 16% DS, high variability
          → Medium criticality (DS% constraint), dewatering VOI High
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "apps" / "biosolids_app"))

from engine.input_schema import (
    BioPointV1Inputs, FeedstockInputsV2, AssetInputs, StrategicInputs
)
from engine.biopoint_v1_runner import run_biopoint_v1
from engine.dil_biosolids import (
    build_biosolids_dil,
    CRIT_LOW, CRIT_MEDIUM, CRIT_HIGH,
    DR_READY, DR_CONDITIONS, DR_NOT_READY,
)


# ── Shared asset base ────────────────────────────────────────────────────────

_BASE_ASSETS = dict(
    anaerobic_digestion_present=True,
    thp_present=False,
    chp_present=True,
    drying_system_present=False,
    local_power_price_per_kwh=0.20,
    fuel_price_per_gj=15.0,
    disposal_cost_per_tds=180.0,
    transport_cost_per_tonne_km=0.25,
    average_transport_distance_km=60.0,
    waste_heat_available_kwh_per_day=0.0,
)


def _run(inputs: BioPointV1Inputs):
    results = run_biopoint_v1(inputs)
    return build_biosolids_dil(inputs, results)


def _assert_structure(di) -> None:
    """Structural completeness assertions common to all cases."""
    assert di.closing_statement.startswith("WaterPoint does not seek"), (
        f"Wrong closing statement: {di.closing_statement[:60]}"
    )
    assert di.criticality.level in (CRIT_LOW, CRIT_MEDIUM, CRIT_HIGH)
    assert di.readiness.status in (DR_READY, DR_CONDITIONS, DR_NOT_READY)
    assert di.data_confidence.overall_confidence in (
        "High", "Acceptable", "Low", "Very Low"
    )
    assert len(di.voi.dimensions) >= 1, "No VOI dimensions"
    assert len(di.risk_ownership.dimensions) >= 5, (
        f"Only {len(di.risk_ownership.dimensions)} risk dims — expected >= 5"
    )
    assert di.risk_ownership.utility_accountability_statement
    assert di.risk_ownership.residual_risk_statement
    assert len(di.decision_boundary.monitoring_requirements) >= 4
    assert len(di.decision_boundary.critical_assumptions) >= 4
    assert len(di.decision_boundary.intervention_triggers) >= 2
    assert di.decision_boundary.fallback_position
    assert di.readiness.basis
    assert di.readiness.strategic_implication


# ── Case 1: Metro PFAS unknown — Not Decision-Ready ──────────────────────────

def test_bp_dil_metro_pfas_unknown():
    """
    137 tDS/day metro plant. PFAS unknown. Pyrolysis candidate.
    PFAS unknown must block pathway commitment → Not Decision-Ready.
    High criticality (scale + regulatory pressure + unknown PFAS).
    PFAS characterisation must appear as High VOI.
    Carbon credit must appear as Low VOI.
    """
    inputs = BioPointV1Inputs(
        feedstock=FeedstockInputsV2(
            dry_solids_tpd=137.0, dewatered_ds_percent=22.0,
            volatile_solids_percent=58.0, gross_calorific_value_mj_per_kg_ds=10.5,
            ash_percent=42.0, sludge_type="digested", feedstock_variability="moderate",
            pfas_present="unknown", metals_risk="low",
        ),
        assets=AssetInputs(**_BASE_ASSETS),
        strategic=StrategicInputs(
            optimisation_priority="lowest_disposal_dependency",
            regulatory_pressure="high",
            carbon_credit_value_per_tco2e=50.0,
            biochar_market_confidence="low",
            land_constraint="moderate",
            social_licence_pressure="high",
        ),
    )
    di = _run(inputs)
    _assert_structure(di)

    assert di.criticality.level == CRIT_HIGH, (
        f"Expected High criticality for metro PFAS unknown, got {di.criticality.level}"
    )
    assert di.readiness.status == DR_NOT_READY, (
        f"PFAS unknown must produce Not Decision-Ready, got {di.readiness.status}"
    )
    assert "PFAS characterisation" in di.voi.high_voi_items, (
        f"PFAS characterisation must be High VOI, got {di.voi.high_voi_items}"
    )
    assert "Carbon credit market access and price" in di.voi.low_voi_items, (
        f"Carbon credit must be Low VOI, got {di.voi.low_voi_items}"
    )
    assert any(
        "PFAS" in c for c in di.readiness.conditions
    ), "PFAS condition must appear in readiness conditions"


# ── Case 2: Regional PFAS absent — Ready to Proceed ──────────────────────────

def test_bp_dil_regional_pfas_absent():
    """
    25 tDS/day regional plant. PFAS confirmed absent. Balanced objective.
    Expected: Low or Medium criticality. Ready or Proceed with Conditions.
    No PFAS-related High VOI items.
    """
    inputs = BioPointV1Inputs(
        feedstock=FeedstockInputsV2(
            dry_solids_tpd=25.0, dewatered_ds_percent=25.0,
            volatile_solids_percent=65.0, gross_calorific_value_mj_per_kg_ds=12.0,
            ash_percent=35.0, sludge_type="digested", feedstock_variability="low",
            pfas_present="no", metals_risk="low",
        ),
        assets=AssetInputs(**{**_BASE_ASSETS, "disposal_cost_per_tds": 120.0}),
        strategic=StrategicInputs(
            optimisation_priority="balanced",
            regulatory_pressure="low",
            carbon_credit_value_per_tco2e=35.0,
            biochar_market_confidence="low",
            land_constraint="low",
            social_licence_pressure="low",
        ),
    )
    di = _run(inputs)
    _assert_structure(di)

    assert di.criticality.level in (CRIT_LOW, CRIT_MEDIUM), (
        f"Expected Low/Medium for regional PFAS absent, got {di.criticality.level}"
    )
    assert di.readiness.status in (DR_READY, DR_CONDITIONS), (
        f"Expected Ready or Conditions for simple regional case, got {di.readiness.status}"
    )
    assert "PFAS characterisation" not in di.voi.high_voi_items, (
        "PFAS should not be High VOI when confirmed absent"
    )
    assert "Carbon credit market access and price" in di.voi.low_voi_items, (
        f"Carbon credit must be Low VOI, got {di.voi.low_voi_items}"
    )


# ── Case 3: Large PFAS confirmed — High criticality ──────────────────────────

def test_bp_dil_large_pfas_confirmed():
    """
    80 tDS/day plant. PFAS confirmed present. High regulatory pressure.
    Expected: High criticality — PFAS + scale + thermal capital + land constraint.
    Utility must own compliance risk.
    """
    inputs = BioPointV1Inputs(
        feedstock=FeedstockInputsV2(
            dry_solids_tpd=80.0, dewatered_ds_percent=28.0,
            volatile_solids_percent=55.0, gross_calorific_value_mj_per_kg_ds=10.0,
            ash_percent=45.0, sludge_type="digested", feedstock_variability="moderate",
            pfas_present="yes", metals_risk="moderate",
        ),
        assets=AssetInputs(**{**_BASE_ASSETS, "disposal_cost_per_tds": 250.0}),
        strategic=StrategicInputs(
            optimisation_priority="highest_resilience",
            regulatory_pressure="high",
            carbon_credit_value_per_tco2e=60.0,
            biochar_market_confidence="low",
            land_constraint="high",
            social_licence_pressure="high",
        ),
    )
    di = _run(inputs)
    _assert_structure(di)

    assert di.criticality.level == CRIT_HIGH, (
        f"Expected High criticality for large PFAS confirmed, got {di.criticality.level}"
    )
    risk_owners = {d.risk_category: d.primary_owner for d in di.risk_ownership.dimensions}
    assert risk_owners.get("Regulatory and compliance risk") == "Utility", (
        "Utility must own compliance risk"
    )
    assert risk_owners.get("Whole-of-life asset risk") == "Utility", (
        "Utility must own whole-of-life asset risk"
    )


# ── Case 4: Small low DS% — dewatering VOI high ───────────────────────────────

def test_bp_dil_small_low_ds():
    """
    8 tDS/day plant at 16% DS. High variability. PFAS absent.
    Expected: Medium or High criticality (DS% is water-removal constrained).
    Dewatering improvement potential must be High VOI.
    Readiness: Not Decision-Ready or Conditions.
    """
    inputs = BioPointV1Inputs(
        feedstock=FeedstockInputsV2(
            dry_solids_tpd=8.0, dewatered_ds_percent=16.0,
            volatile_solids_percent=70.0, gross_calorific_value_mj_per_kg_ds=13.0,
            ash_percent=30.0, sludge_type="secondary", feedstock_variability="high",
            pfas_present="no", metals_risk="low",
        ),
        assets=AssetInputs(**{
            **_BASE_ASSETS,
            "anaerobic_digestion_present": False,
            "disposal_cost_per_tds": 300.0,
        }),
        strategic=StrategicInputs(
            optimisation_priority="lowest_cost",
            regulatory_pressure="moderate",
            carbon_credit_value_per_tco2e=35.0,
            biochar_market_confidence="low",
            land_constraint="low",
            social_licence_pressure="low",
        ),
    )
    di = _run(inputs)
    _assert_structure(di)

    assert di.criticality.level in (CRIT_MEDIUM, CRIT_HIGH), (
        f"Expected Medium/High for 16% DS water-constrained plant, got {di.criticality.level}"
    )
    assert di.readiness.status in (DR_NOT_READY, DR_CONDITIONS), (
        f"Expected Not Ready or Conditions for marginal DS%, got {di.readiness.status}"
    )
    assert "Dewatering improvement potential" in di.voi.high_voi_items, (
        f"Dewatering must be High VOI at 16% DS, got {di.voi.high_voi_items}"
    )


# ── Standalone runner ─────────────────────────────────────────────────────────

def _run_all() -> bool:
    tests = [
        test_bp_dil_metro_pfas_unknown,
        test_bp_dil_regional_pfas_absent,
        test_bp_dil_large_pfas_confirmed,
        test_bp_dil_small_low_ds,
    ]
    passed = failed = 0
    print("\nBioPoint DIL — Test Suite")
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
        print("  ✅ ALL BIOPOINT DIL TESTS PASSED")
    else:
        print("  ❌ FAILURES DETECTED")
    return failed == 0


if __name__ == "__main__":
    success = _run_all()
    sys.exit(0 if success else 1)
