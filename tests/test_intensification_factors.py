"""
tests/test_intensification_factors.py

Intensification factor regression suite — WaterPoint v24Z39
============================================================

Verifies that intensification_factor and intensification_basis are correctly
populated on PathwayStage objects for InDENSE (1.3×) and IFAS/Hybas (1.5×)
across all emission paths.

Cases:
  1. InDENSE steady-state settling constraint
  2. InDENSE severe settling + nitrification (IFAS follows InDENSE)
  3. IFAS direct path (aeration headroom, SRT bottleneck)
  4. IFAS NP fallback (aeration constrained, NP-1 fires)
  5. Hybas (settling already addressed, SRT bottleneck)
  6. PathwayStage default — non-intensification stage has factor=0.0
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
from apps.wastewater_app.stack_generator import (
    build_upgrade_pathway, PathwayStage,
    TI_INDENSE, TI_IFAS, TI_HYBAS,
)


# ── Shared fixture helpers ─────────────────────────────────────────────────────

def _wpr_settling(severity: str = "High") -> WaterPointResult:
    return WaterPointResult(
        system_stress=SystemStress(
            state="Fragile", proximity_percent=85.,
            primary_constraint="Settling",
            rate="Tightening", time_to_breach="2-3 years",
            confidence="Medium", rationale="Test",
        ),
        failure_modes=FailureModes(
            items=[FailureMode(
                title="Settling limitation",
                description="SVI elevated, SOR exceeded", severity=severity,
            )],
            overall_severity=severity,
        ),
        decision_layer=DecisionLayer(),
        compliance_risk=ComplianceRisk(
            compliance_risk="Medium", likely_breach_type="TSS",
            regulatory_exposure="Medium", reputational_risk="Low",
        ),
    )


def _wpr_nitrif() -> WaterPointResult:
    return WaterPointResult(
        system_stress=SystemStress(
            state="Fragile", proximity_percent=88.,
            primary_constraint="Nitrification",
            rate="Tightening", time_to_breach="2-3 years",
            confidence="Medium", rationale="Test",
        ),
        failure_modes=FailureModes(
            items=[FailureMode(
                title="Nitrification limit",
                description="SRT insufficient", severity="High",
            )],
            overall_severity="High",
        ),
        decision_layer=DecisionLayer(),
        compliance_risk=ComplianceRisk(
            compliance_risk="High", likely_breach_type="NH4",
            regulatory_exposure="High", reputational_risk="Medium",
        ),
    )


def _wpr_settling_and_nitrif() -> WaterPointResult:
    return WaterPointResult(
        system_stress=SystemStress(
            state="Failure Risk", proximity_percent=96.,
            primary_constraint="Settling + Nitrification",
            rate="Accelerating", time_to_breach="< 12 months",
            confidence="High", rationale="Test",
        ),
        failure_modes=FailureModes(
            items=[
                FailureMode(title="Settling limitation",
                            description="SVI elevated", severity="High"),
                FailureMode(title="Nitrification limit",
                            description="SRT insufficient", severity="High"),
            ],
            overall_severity="High",
        ),
        decision_layer=DecisionLayer(),
        compliance_risk=ComplianceRisk(
            compliance_risk="High", likely_breach_type="NH4",
            regulatory_exposure="High", reputational_risk="High",
        ),
    )


def _factor_stages(pathway) -> list:
    return [s for s in pathway.stages if s.intensification_factor > 0.]


# ── Case 1: InDENSE steady-state settling ──────────────────────────────────────

def test_indense_steady_state_settling():
    """
    Plain settling constraint, BNR, no aeration constraint.
    Expects InDENSE stage with factor=1.3 and non-empty basis.
    """
    ctx = dict(
        plant_type="BNR", is_sbr=False, is_mbr=False,
        aeration_constrained=False, svi_elevated=True,
        flow_ratio=1.3, plant_size_mld=15., location_type="metro",
        carbon_capture_upstream=False, instrumentation_capable=True,
        aeration_headroom_pct=20., greenfield=False,
        overflow_risk=False, wet_weather_peak=False,
        high_load=False, clarifier_util=0.85,
    )
    pathway = build_upgrade_pathway(_wpr_settling("Medium"), ctx)
    fs = _factor_stages(pathway)

    assert fs, "No intensification stage found for settling constraint"

    indense = next((s for s in fs if TI_INDENSE in s.technology), None)
    assert indense is not None, f"InDENSE not in factor stages: {[s.technology for s in fs]}"
    assert indense.intensification_factor == pytest.approx(1.3), (
        f"Expected 1.3×, got {indense.intensification_factor}"
    )
    assert indense.intensification_basis, "intensification_basis is empty"
    assert "1.3" in indense.intensification_basis
    assert "EBPR" in indense.intensification_basis or "PAO" in indense.intensification_basis, (
        "EBPR/PAO benefit not mentioned in InDENSE basis"
    )
    assert "anaerobic" in indense.intensification_basis.lower(), (
        "Anaerobic selector prerequisite not mentioned in InDENSE basis"
    )


# ── Case 2: InDENSE + IFAS (settling + nitrification) ─────────────────────────

def test_indense_and_ifas_settling_plus_nitrification():
    """
    Settling + nitrification constraints, BNR, aeration has headroom.
    Expects InDENSE (1.3×) AND IFAS/Hybas (1.5×) both with factors.
    """
    ctx = dict(
        plant_type="BNR", is_sbr=False, is_mbr=False,
        aeration_constrained=False, svi_elevated=True,
        flow_ratio=1.4, plant_size_mld=20., location_type="metro",
        carbon_capture_upstream=False, instrumentation_capable=True,
        aeration_headroom_pct=18., greenfield=False,
        overflow_risk=False, wet_weather_peak=False,
        high_load=True, clarifier_util=0.9,
    )
    pathway = build_upgrade_pathway(_wpr_settling_and_nitrif(), ctx)
    fs = _factor_stages(pathway)

    assert len(fs) >= 2, (
        f"Expected at least 2 intensification stages, got {len(fs)}: "
        f"{[s.technology for s in fs]}"
    )

    techs = [s.technology for s in fs]
    assert TI_INDENSE in techs, f"InDENSE missing from {techs}"

    nitrif_stage = next(
        (s for s in fs if s.technology in (TI_IFAS, TI_HYBAS)), None
    )
    assert nitrif_stage is not None, (
        f"No IFAS/Hybas intensification stage found. Techs with factor: {techs}"
    )
    assert nitrif_stage.intensification_factor == pytest.approx(1.5), (
        f"Expected 1.5× on nitrification stage, got {nitrif_stage.intensification_factor}"
    )


# ── Case 3: IFAS direct (aeration headroom, SRT bottleneck) ───────────────────

def test_ifas_direct_aeration_headroom():
    """
    Nitrification constraint only, aeration headroom 20%.
    Expects IFAS with factor=1.5.
    """
    ctx = dict(
        plant_type="BNR", is_sbr=False, is_mbr=False,
        aeration_constrained=False, svi_elevated=False,
        flow_ratio=1.3, plant_size_mld=15., location_type="metro",
        carbon_capture_upstream=False, instrumentation_capable=True,
        aeration_headroom_pct=20., greenfield=False,
        overflow_risk=False, wet_weather_peak=False, high_load=False,
    )
    pathway = build_upgrade_pathway(_wpr_nitrif(), ctx)
    fs = _factor_stages(pathway)

    assert fs, "No intensification stage for nitrification constraint"
    ifas = next((s for s in fs if s.technology == TI_IFAS), None)
    assert ifas is not None, f"IFAS not found. Factor stages: {[s.technology for s in fs]}"
    assert ifas.intensification_factor == pytest.approx(1.5)
    assert "1.5" in ifas.intensification_basis
    assert "Metcalf" in ifas.intensification_basis or "MOP" in ifas.intensification_basis, (
        "Published reference missing from IFAS basis"
    )


# ── Case 4: IFAS NP fallback (NP-1 fires) ──────────────────────────────────────

def test_ifas_np_fallback_aeration_constrained():
    """
    Nitrification constraint, aeration constrained, no carbon strategy (NP-1).
    MABR suppressed → IFAS emitted with factor=1.5.
    """
    ctx = dict(
        plant_type="BNR", is_sbr=False, is_mbr=False,
        aeration_constrained=True, svi_elevated=False,
        flow_ratio=1.3, plant_size_mld=15., location_type="metro",
        carbon_capture_upstream=False, instrumentation_capable=True,
        aeration_headroom_pct=5., greenfield=False,
        overflow_risk=False, wet_weather_peak=False, high_load=False,
    )
    pathway = build_upgrade_pathway(_wpr_nitrif(), ctx)
    fs = _factor_stages(pathway)

    assert fs, "No intensification stage on NP fallback path"
    factor_techs = [s.technology for s in fs]
    # Should be IFAS (not MABR) since NP-1 fires
    assert TI_IFAS in factor_techs, (
        f"IFAS expected on NP-1 fallback, got: {factor_techs}"
    )
    ifas = next(s for s in fs if s.technology == TI_IFAS)
    assert ifas.intensification_factor == pytest.approx(1.5)


# ── Case 5: Hybas (settling present, SRT bottleneck) ──────────────────────────

def test_hybas_after_settling():
    """
    Settling + nitrification, SBR=False, settling already addressed in Stage 1.
    Hybas emitted with factor=1.5 when settling_present=True.
    """
    ctx = dict(
        plant_type="BNR", is_sbr=False, is_mbr=False,
        aeration_constrained=False, svi_elevated=True,
        flow_ratio=1.4, plant_size_mld=20., location_type="metro",
        carbon_capture_upstream=False, instrumentation_capable=True,
        aeration_headroom_pct=18., greenfield=False,
        overflow_risk=False, wet_weather_peak=False,
        high_load=True, clarifier_util=0.92,
        solids_carryover=True,   # triggers settling constraint
    )
    pathway = build_upgrade_pathway(_wpr_settling_and_nitrif(), ctx)
    fs = _factor_stages(pathway)

    nitrif = next(
        (s for s in fs if s.technology in (TI_IFAS, TI_HYBAS)), None
    )
    assert nitrif is not None, (
        f"No IFAS/Hybas in factor stages: {[s.technology for s in fs]}"
    )
    assert nitrif.intensification_factor == pytest.approx(1.5)
    assert nitrif.intensification_basis


# ── Case 6: Non-intensification stage has factor=0.0 ──────────────────────────

def test_non_intensification_stage_has_zero_factor():
    """
    A stage that is not IFAS/Hybas/InDENSE should have intensification_factor=0.0.
    This prevents false positives in UI rendering.
    """
    from apps.wastewater_app.stack_generator import PathwayStage

    stage = PathwayStage(
        stage_number=1,
        technology="EQ_BASIN",
        tech_display="Equalisation basin",
        mechanism="HYD_EXP",
        mechanism_label="Hydraulic expansion",
        purpose="Attenuate peak flows",
        engineering_basis="Size to 2× DWA.",
        addresses=["CT_HYDRAULIC"],
    )
    assert stage.intensification_factor == 0.0, (
        f"Default intensification_factor should be 0.0, got {stage.intensification_factor}"
    )
    assert stage.intensification_basis == "", (
        f"Default intensification_basis should be empty, got '{stage.intensification_basis}'"
    )
