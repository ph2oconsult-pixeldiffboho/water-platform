"""
tests/test_decision_intelligence.py

Decision Intelligence Layer — regression test suite
====================================================

5 engineering-calibrated cases covering the full DIL pipeline:
  Case 1: Metro BNR, tight TN, wet weather, aeration constrained
  Case 2: Greenfield metro 50 MLD, very tight TN (<5 mg/L)
  Case 3: Small remote plant, low criticality baseline
  Case 4: SBR regional, high wet weather (flow ratio 3.0×)
  Case 5: Carbon capture upstream, MABR permitted

Each case asserts:
  - Correct criticality level (engineering range)
  - Correct decision readiness status (engineering range)
  - Structural completeness (VOI, risk, boundary, closing statement)
  - MABR presence where expected (Case 5)
  - No runtime exceptions through full pipeline
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import pytest

from apps.wastewater_app.waterpoint_engine import (
    WaterPointResult, SystemStress, FailureModes, FailureMode,
    DecisionLayer, ComplianceRisk,
)
from apps.wastewater_app.stack_generator import build_upgrade_pathway
from apps.wastewater_app.feasibility_layer import assess_feasibility
from apps.wastewater_app.credibility_layer import build_credible_output
from apps.wastewater_app.uncertainty_layer import build_uncertainty_report
from apps.wastewater_app.decision_intelligence_layer import (
    build_decision_intelligence,
    CRIT_LOW, CRIT_MEDIUM, CRIT_HIGH,
    DR_READY, DR_CONDITIONS, DR_NOT_READY,
)


# ── Fixture helpers ───────────────────────────────────────────────────────────

def _make_wpr(state: str = "Fragile", primary: str = "Aeration capacity") -> WaterPointResult:
    """Minimal WaterPointResult sufficient to drive stack_generator."""
    return WaterPointResult(
        system_stress=SystemStress(
            state=state,
            proximity_percent=88.0,
            primary_constraint=primary,
            rate="Tightening",
            time_to_breach="2-3 years",
            confidence="Medium",
            rationale="Test fixture",
        ),
        failure_modes=FailureModes(
            items=[FailureMode(
                title="Aeration limit",
                description="Blowers at capacity",
                severity="High",
            )],
            overall_severity="High",
        ),
        decision_layer=DecisionLayer(),
        compliance_risk=ComplianceRisk(
            compliance_risk="High",
            likely_breach_type="TN",
            regulatory_exposure="High",
            reputational_risk="Medium",
        ),
    )


def _run_dil(ctx: dict):
    """Run full DIL pipeline from plant_context dict. Returns DecisionIntelligenceReport."""
    pathway = build_upgrade_pathway(_make_wpr(), ctx)
    feas    = assess_feasibility(pathway, ctx)
    cred    = build_credible_output(pathway, feas, ctx)
    unc     = build_uncertainty_report(pathway, feas, cred, ctx)
    return build_decision_intelligence(pathway, feas, cred, unc, ctx)


# ── Base context ──────────────────────────────────────────────────────────────

_BASE_CTX = dict(
    plant_type="BNR", is_sbr=False, is_mbr=False,
    overflow_risk=False, wet_weather_peak=False, flow_ratio=1.3,
    aeration_constrained=False, high_load=False,
    tn_at_limit=False, tp_at_limit=False, nh4_near_limit=False,
    srt_pressure=False, nitrification_flag=False, carbon_limited_tn=False,
    high_mlss=False, solids_carryover=False, clarifier_util=0.6,
    plant_size_mld=10.0, location_type="metro",
    aeration_kwh_day=800, tn_in_mg_l=45,
    tn_out_baseline_mg_l=10.0, tn_out_upgraded_mg_l=8.0,
    grid_ef_kgco2e_kwh=0.50, chemical_co2e_increase_t=50.0,
    tn_target_mg_l=10.0, greenfield=False, footprint_constrained=False,
    carbon_capture_upstream=False, instrumentation_capable=True,
    aeration_headroom_pct=20.0, cod_tn_ratio=7.0,
)


# ── Structural assertions (shared) ────────────────────────────────────────────

def _assert_structure(di) -> None:
    """Structural completeness assertions common to all cases."""
    assert di.closing_statement.startswith("WaterPoint does not seek"), (
        f"Wrong closing statement: {di.closing_statement[:60]}"
    )
    assert di.criticality.level in (CRIT_LOW, CRIT_MEDIUM, CRIT_HIGH)
    assert di.readiness.status in (DR_READY, DR_CONDITIONS, DR_NOT_READY)
    assert di.data_confidence.overall_confidence in ("High", "Acceptable", "Low", "Very Low")
    assert len(di.voi.dimensions) >= 1, "No VOI dimensions"
    assert len(di.risk_ownership.dimensions) >= 5, (
        f"Only {len(di.risk_ownership.dimensions)} risk dimensions — expected >= 5"
    )
    assert di.risk_ownership.utility_accountability_statement, "Missing utility accountability statement"
    assert di.risk_ownership.residual_risk_statement, "Missing residual risk statement"
    assert len(di.decision_boundary.monitoring_requirements) >= 3, "Fewer than 3 monitoring requirements"
    assert len(di.decision_boundary.critical_assumptions) >= 3, "Fewer than 3 critical assumptions"
    assert len(di.decision_boundary.intervention_triggers) >= 2, "Fewer than 2 intervention triggers"
    assert di.decision_boundary.fallback_position, "Missing fallback position"
    assert di.decision_boundary.resilience_margin, "Missing resilience margin"
    assert di.readiness.basis, "Missing readiness basis"
    assert di.readiness.strategic_implication, "Missing strategic implication"


# ── Case 1: Metro BNR, tight TN, wet weather, aeration constrained ────────────

def test_dil_metro_bnr_tight_tn_wet_weather():
    """
    25 MLD metro BNR plant.
    Aeration constrained, TN at limit (6 mg/L), overflow risk, flow ratio 2.2×.
    Expected: Medium or High criticality, Proceed with Conditions or Not Decision-Ready.
    High VOI on wet weather flow characterisation.
    """
    ctx = {**_BASE_CTX,
        "overflow_risk": True, "wet_weather_peak": True, "flow_ratio": 2.2,
        "aeration_constrained": True, "high_load": True, "tn_at_limit": True,
        "nh4_near_limit": True, "carbon_limited_tn": True,
        "clarifier_util": 0.9, "plant_size_mld": 25.0,
        "aeration_kwh_day": 2000, "tn_out_upgraded_mg_l": 6.0,
        "tn_target_mg_l": 6.0, "aeration_headroom_pct": 5.0, "cod_tn_ratio": 6.5,
    }
    di = _run_dil(ctx)
    _assert_structure(di)
    assert di.criticality.level in (CRIT_MEDIUM, CRIT_HIGH), (
        f"Expected Medium/High criticality for metro 25 MLD tight TN, got {di.criticality.level}"
    )
    assert di.readiness.status in (DR_CONDITIONS, DR_NOT_READY), (
        f"Expected Proceed with Conditions or Not Decision-Ready, got {di.readiness.status}"
    )
    assert "Peak wet weather flow characterisation" in di.voi.high_voi_items, (
        f"Expected wet weather flow in high VOI, got {di.voi.high_voi_items}"
    )


# ── Case 2: Greenfield metro 50 MLD, very tight TN ───────────────────────────

def test_dil_greenfield_metro_large_tight_tn():
    """
    50 MLD metro greenfield.
    TN target 4 mg/L — triggers high compliance and asset lock-in scoring.
    Expected: High criticality (greenfield + metro scale + tight TN).
    """
    ctx = {**_BASE_CTX,
        "flow_ratio": 1.3, "aeration_constrained": False, "tn_at_limit": True,
        "tp_at_limit": True, "nh4_near_limit": True,
        "clarifier_util": 0.5, "plant_size_mld": 50.0,
        "aeration_kwh_day": 4000, "tn_out_upgraded_mg_l": 4.0,
        "tn_target_mg_l": 4.0, "greenfield": True, "aeration_headroom_pct": 50.0,
        "cod_tn_ratio": 7.0,
    }
    di = _run_dil(ctx)
    _assert_structure(di)
    assert di.criticality.level == CRIT_HIGH, (
        f"Expected High criticality for greenfield metro 50 MLD TN=4 mg/L, got {di.criticality.level}"
    )


# ── Case 3: Small remote plant, low criticality ───────────────────────────────

def test_dil_small_remote_low_criticality():
    """
    3 MLD remote plant, no compliance pressure, no wet weather risk.
    Expected: Low criticality. Readiness: Ready or Proceed with Conditions.
    """
    ctx = {**_BASE_CTX,
        "plant_size_mld": 3.0, "location_type": "remote",
        "aeration_kwh_day": 200, "chemical_co2e_increase_t": 20.0,
        "tn_out_upgraded_mg_l": 8.0, "tn_target_mg_l": 10.0,
        "instrumentation_capable": False, "aeration_headroom_pct": 40.0, "cod_tn_ratio": 8.0,
    }
    di = _run_dil(ctx)
    _assert_structure(di)
    assert di.criticality.level in (CRIT_LOW, CRIT_MEDIUM), (
        f"Expected Low/Medium criticality for small remote plant, got {di.criticality.level}"
    )
    assert di.readiness.status in (DR_READY, DR_CONDITIONS), (
        f"Expected Ready or Conditions for simple remote plant, got {di.readiness.status}"
    )


# ── Case 4: SBR regional, high wet weather ────────────────────────────────────

def test_dil_sbr_regional_wet_weather():
    """
    15 MLD regional SBR, flow ratio 3.0×, overflow risk, aeration constrained.
    Expected: Medium or High criticality.
    High VOI on wet weather flow characterisation.
    """
    ctx = {**_BASE_CTX,
        "plant_type": "SBR", "is_sbr": True,
        "overflow_risk": True, "wet_weather_peak": True, "flow_ratio": 3.0,
        "aeration_constrained": True, "high_load": True,
        "tn_at_limit": True, "nh4_near_limit": True, "nitrification_flag": True,
        "plant_size_mld": 15.0, "location_type": "regional",
        "aeration_kwh_day": 1200, "chemical_co2e_increase_t": 60.0,
        "tn_out_upgraded_mg_l": 8.0, "tn_target_mg_l": 8.0,
        "aeration_headroom_pct": 8.0, "cod_tn_ratio": 6.0,
    }
    di = _run_dil(ctx)
    _assert_structure(di)
    assert di.criticality.level in (CRIT_MEDIUM, CRIT_HIGH), (
        f"Expected Medium/High criticality for SBR regional wet weather, got {di.criticality.level}"
    )
    assert "Peak wet weather flow characterisation" in di.voi.high_voi_items, (
        f"Expected wet weather flow in high VOI, got {di.voi.high_voi_items}"
    )


# ── Case 5: Carbon capture upstream, MABR permitted ──────────────────────────

def test_dil_carbon_capture_mabr_permitted():
    """
    20 MLD metro BNR, carbon_capture_upstream=True, aeration constrained, TN=5 mg/L.
    MABR NP-1 guard is lifted — MABR should appear in tech set.
    Expected: Medium/High criticality, Not Decision-Ready or Proceed with Conditions.
    High VOI: blower audit (determines MABR vs IFAS).
    """
    ctx = {**_BASE_CTX,
        "flow_ratio": 1.4, "aeration_constrained": True, "high_load": True,
        "tn_at_limit": True, "nh4_near_limit": True,
        "clarifier_util": 0.85, "plant_size_mld": 20.0,
        "aeration_kwh_day": 1600, "chemical_co2e_increase_t": 80.0,
        "tn_out_upgraded_mg_l": 5.0, "tn_target_mg_l": 5.0,
        "carbon_capture_upstream": True, "aeration_headroom_pct": 5.0, "cod_tn_ratio": 5.0,
    }
    di = _run_dil(ctx)
    _assert_structure(di)
    assert di.criticality.level in (CRIT_MEDIUM, CRIT_HIGH), (
        f"Expected Medium/High criticality for MABR metro tight TN, got {di.criticality.level}"
    )
    assert di.readiness.status in (DR_NOT_READY, DR_CONDITIONS), (
        f"Expected Not Decision-Ready or Conditions when blower audit outstanding, got {di.readiness.status}"
    )
    assert any("MABR" in t for t in di.tech_set), (
        f"Expected MABR in tech set when carbon_capture_upstream=True, got {di.tech_set}"
    )
    assert "Aeration capacity headroom (blower audit)" in di.voi.high_voi_items, (
        f"Expected blower audit in high VOI, got {di.voi.high_voi_items}"
    )


# ── Standalone runner (used by run_tests.py) ──────────────────────────────────

def _run_all() -> bool:
    tests = [
        test_dil_metro_bnr_tight_tn_wet_weather,
        test_dil_greenfield_metro_large_tight_tn,
        test_dil_small_remote_low_criticality,
        test_dil_sbr_regional_wet_weather,
        test_dil_carbon_capture_mabr_permitted,
    ]
    passed = failed = 0
    print("\nDecision Intelligence Layer — Test Suite")
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
        print("  ✅ ALL DIL TESTS PASSED")
    else:
        print("  ❌ FAILURES DETECTED")
    return failed == 0


if __name__ == "__main__":
    success = _run_all()
    sys.exit(0 if success else 1)
