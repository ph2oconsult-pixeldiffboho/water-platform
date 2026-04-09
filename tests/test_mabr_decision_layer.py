"""
tests/test_mabr_decision_layer.py

MABR Decision Layer — regression test suite
============================================

6 engineering-calibrated cases covering the full MABR decision pipeline:

  Case 1: Metro BNR, carbon-capture + aeration constrained, instrumentation capable
          → Conditionally preferred / Retrofit intensification module
  Case 2: Greenfield metro, carbon-capture + aeration constrained
          → Strategically preferred / Core mainstream nitrogen module
  Case 3: NP-1 — brownfield, no carbon strategy, aeration constrained
          → Not preferred / Not preferred (NP-1 triggered)
  Case 4: NP-2 — remote small plant, no instrumentation
          → Not preferred / Not preferred (NP-2 triggered)
  Case 5: NP-3 — metro BNR, aeration headroom 20%
          → Not preferred / Not preferred (NP-3 triggered)
  Case 6: Polishing / cold-climate — tight NH₃ target, no carbon strategy
          → Situationally useful / Polishing module

Each case asserts:
  - Correct WaterPoint decision label
  - Correct role classification
  - NP guard triggers as expected
  - Comparison table always produced (4 rows)
  - Structural completeness (all narrative fields populated)
  - Carbon strategy score in range 0–2
  - Complexity/risk score in range 0–8
  - No runtime exceptions
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pytest

from apps.wastewater_app.mabr_decision_layer import (
    assess_mabr,
    MABR_ROLE_CORE, MABR_ROLE_RETROFIT, MABR_ROLE_POLISH,
    MABR_ROLE_NICHE, MABR_ROLE_NP,
    MABR_DEC_STRATEGIC, MABR_DEC_CONDITIONAL,
    MABR_DEC_SITUATIONAL, MABR_DEC_NP,
    CS_ABSENT, CS_PARTIAL, CS_CONFIRMED,
    ENERGY_POSITIVE, ENERGY_NEUTRAL, ENERGY_NEGATIVE,
)


# ── Structural assertion (shared) ─────────────────────────────────────────────

def _assert_structure(m) -> None:
    """Structural completeness assertions common to all cases."""
    # Role and decision are always one of the known constants
    assert m.role in (
        MABR_ROLE_CORE, MABR_ROLE_RETROFIT, MABR_ROLE_POLISH,
        MABR_ROLE_NICHE, MABR_ROLE_NP,
    ), f"Unknown role: {m.role}"

    assert m.decision in (
        MABR_DEC_STRATEGIC, MABR_DEC_CONDITIONAL,
        MABR_DEC_SITUATIONAL, MABR_DEC_NP,
    ), f"Unknown decision: {m.decision}"

    # Carbon strategy score is 0, 1, or 2
    assert m.carbon_strategy_score in (CS_ABSENT, CS_PARTIAL, CS_CONFIRMED), (
        f"Carbon strategy score out of range: {m.carbon_strategy_score}"
    )
    assert m.carbon_strategy_label in ("Absent", "Partial", "Confirmed"), (
        f"Unexpected carbon strategy label: {m.carbon_strategy_label}"
    )

    # Complexity score is 0–8
    assert 0 <= m.complexity_risk_score <= 8, (
        f"Complexity score out of range: {m.complexity_risk_score}"
    )

    # Energy verdict is one of the known strings
    assert m.net_energy_verdict in (ENERGY_POSITIVE, ENERGY_NEUTRAL, ENERGY_NEGATIVE), (
        f"Unknown energy verdict: {m.net_energy_verdict}"
    )

    # Comparison table always has exactly 4 rows
    assert len(m.comparison_table) == 4, (
        f"Comparison table should have 4 rows, got {len(m.comparison_table)}"
    )
    tech_names = [r.technology for r in m.comparison_table]
    assert "MABR (OxyFAS)" in tech_names,     "MABR row missing from comparison table"
    assert "Conventional BNR" in tech_names,  "BNR row missing from comparison table"
    assert "IFAS / MBBR" in tech_names,       "IFAS row missing from comparison table"
    assert "AGS (Nereda)" in tech_names,      "AGS row missing from comparison table"

    # All comparison table rows have non-empty key fields
    for row in m.comparison_table:
        assert row.system_role,       f"Empty system_role for {row.technology}"
        assert row.carbon_alignment,  f"Empty carbon_alignment for {row.technology}"
        assert row.waterpoint_view,   f"Empty waterpoint_view for {row.technology}"

    # WPV lists are populated
    assert len(m.wpv_passes) >= 1, "WPV passes list is empty"
    assert len(m.wpv_fails)  >= 0, "WPV fails list is None"

    # All narrative fields are non-empty strings
    assert m.best_fit_role_in_plant, "best_fit_role_in_plant is empty"
    assert m.what_it_replaces,       "what_it_replaces is empty"
    assert m.what_it_enables,        "what_it_enables is empty"
    assert m.risks_introduced,       "risks_introduced is empty"
    assert m.conclusion,             "conclusion is empty"
    assert m.np_reason is not None,  "np_reason is None (should be empty string if no guards)"


# ── Case 1: Conditionally preferred — brownfield C-strategy + aer constrained ─

def test_mabr_conditionally_preferred_brownfield():
    """
    Metro BNR, carbon-capture upstream, aeration constrained, instrumentation capable.
    Expected: Conditionally preferred / Retrofit intensification module.
    NP guards: all False.
    Energy: Positive.
    Carbon strategy: Confirmed.
    """
    ctx = dict(
        plant_type="BNR", plant_size_mld=20., location_type="metro",
        aeration_constrained=True, carbon_capture_upstream=True,
        instrumentation_capable=True, aeration_headroom_pct=5.,
        tn_target_mg_l=8., greenfield=False, footprint_constrained=False,
    )
    m = assess_mabr(ctx)
    _assert_structure(m)

    assert m.decision == MABR_DEC_CONDITIONAL, (
        f"Expected Conditionally preferred, got {m.decision}"
    )
    assert m.role == MABR_ROLE_RETROFIT, (
        f"Expected Retrofit intensification module, got {m.role}"
    )
    assert not m.np1_triggered, "NP-1 should not trigger with carbon strategy confirmed"
    assert not m.np2_triggered, "NP-2 should not trigger for metro 20 MLD"
    assert not m.np3_triggered, "NP-3 should not trigger at 5% headroom"

    assert m.carbon_strategy_score == CS_CONFIRMED
    assert m.net_energy_verdict == ENERGY_POSITIVE

    # Whole-plant value test: aeration constraint and carbon strategy should pass
    pass_text = " ".join(m.wpv_passes)
    assert "aeration" in pass_text.lower() or "carbon" in pass_text.lower(), (
        "Neither aeration nor carbon appear in WPV passes"
    )


# ── Case 2: Strategically preferred — greenfield C-strategy + aer constrained ─

def test_mabr_strategically_preferred_greenfield():
    """
    Greenfield metro, carbon-capture upstream, aeration constrained.
    Expected: Strategically preferred / Core mainstream nitrogen module.
    """
    ctx = dict(
        plant_type="BNR", plant_size_mld=50., location_type="metro",
        aeration_constrained=True, carbon_capture_upstream=True,
        instrumentation_capable=True, aeration_headroom_pct=0.,
        tn_target_mg_l=6., greenfield=True, footprint_constrained=True,
    )
    m = assess_mabr(ctx)
    _assert_structure(m)

    assert m.decision == MABR_DEC_STRATEGIC, (
        f"Expected Strategically preferred, got {m.decision}"
    )
    assert m.role == MABR_ROLE_CORE, (
        f"Expected Core mainstream nitrogen module, got {m.role}"
    )
    assert not m.np1_triggered
    assert not m.np2_triggered
    assert not m.np3_triggered
    assert m.carbon_strategy_score == CS_CONFIRMED
    assert m.net_energy_verdict == ENERGY_POSITIVE


# ── Case 3: NP-1 — no carbon strategy ─────────────────────────────────────────

def test_mabr_np1_no_carbon_strategy():
    """
    Metro BNR, aeration constrained, but NO carbon-capture strategy.
    Expected: Not preferred / Not preferred.
    NP-1 triggered. NP-2 and NP-3 False.
    Energy: Neutral (aeration constrained but no C-strategy).
    """
    ctx = dict(
        plant_type="BNR", plant_size_mld=15., location_type="metro",
        aeration_constrained=True, carbon_capture_upstream=False,
        aaa_upstream=False, enhanced_primary=False,
        instrumentation_capable=True, aeration_headroom_pct=5.,
        tn_target_mg_l=10., greenfield=False,
    )
    m = assess_mabr(ctx)
    _assert_structure(m)

    assert m.decision == MABR_DEC_NP, (
        f"Expected Not preferred (NP-1), got {m.decision}"
    )
    assert m.role == MABR_ROLE_NP
    assert m.np1_triggered, "NP-1 should trigger with no carbon strategy"
    assert not m.np2_triggered
    assert not m.np3_triggered

    assert m.carbon_strategy_score == CS_ABSENT
    assert "NP-1" in m.np_reason

    # Conclusion should mention IFAS as alternative
    assert "IFAS" in m.conclusion or "not preferred" in m.conclusion.lower()


# ── Case 4: NP-2 — remote small plant, no instrumentation ────────────────────

def test_mabr_np2_remote_no_instrumentation():
    """
    Remote plant 3 MLD, no instrumentation capability.
    Expected: Not preferred / Not preferred.
    NP-2 triggered even with carbon strategy present.
    """
    ctx = dict(
        plant_type="BNR", plant_size_mld=3., location_type="remote",
        aeration_constrained=True, carbon_capture_upstream=True,
        instrumentation_capable=False, aeration_headroom_pct=0.,
        tn_target_mg_l=10., greenfield=False,
    )
    m = assess_mabr(ctx)
    _assert_structure(m)

    assert m.decision == MABR_DEC_NP, (
        f"Expected Not preferred (NP-2), got {m.decision}"
    )
    assert m.role == MABR_ROLE_NP
    assert m.np2_triggered, "NP-2 should trigger for remote 3 MLD without instrumentation"
    assert "NP-2" in m.np_reason


# ── Case 5: NP-3 — aeration headroom confirmed ───────────────────────────────

def test_mabr_np3_aeration_headroom():
    """
    Metro BNR, carbon strategy confirmed, but aeration headroom 20% (≥ 15%).
    Expected: Not preferred / Not preferred.
    NP-3 triggered.
    """
    ctx = dict(
        plant_type="BNR", plant_size_mld=20., location_type="metro",
        aeration_constrained=False, carbon_capture_upstream=True,
        instrumentation_capable=True, aeration_headroom_pct=20.,
        tn_target_mg_l=10., greenfield=False,
    )
    m = assess_mabr(ctx)
    _assert_structure(m)

    assert m.decision == MABR_DEC_NP, (
        f"Expected Not preferred (NP-3), got {m.decision}"
    )
    assert m.role == MABR_ROLE_NP
    assert m.np3_triggered, "NP-3 should trigger at 20% aeration headroom"
    assert not m.np2_triggered
    assert "NP-3" in m.np_reason

    # Energy verdict: not positive when aeration is not constrained
    assert m.net_energy_verdict != ENERGY_POSITIVE


# ── Case 6: Situationally useful — polishing / cold climate ──────────────────

def test_mabr_situationally_useful_polishing():
    """
    Metro BNR, no carbon strategy, tight NH₃ target (tn_target ≤ 5), cold climate risk.
    NP guards suppressed by cold_climate_risk pathway → polishing role.
    Expected: Situationally useful / Polishing module.
    """
    # To reach polishing: NP-1 must be suppressed — we set greenfield=True
    # (greenfield suppresses NP-1 in the guard logic) but keep no carbon strategy
    # so CS score stays Absent. Tight TN target pushes to polishing.
    ctx = dict(
        plant_type="BNR", plant_size_mld=12., location_type="metro",
        aeration_constrained=False, carbon_capture_upstream=False,
        instrumentation_capable=True, aeration_headroom_pct=5.,
        tn_target_mg_l=4., greenfield=True,  # suppresses NP-1 on greenfield
        cold_climate_risk=True, footprint_constrained=False,
    )
    m = assess_mabr(ctx)
    _assert_structure(m)

    assert m.decision == MABR_DEC_SITUATIONAL, (
        f"Expected Situationally useful (polishing), got {m.decision}"
    )
    assert m.role == MABR_ROLE_POLISH, (
        f"Expected Polishing / ammonia compliance module, got {m.role}"
    )
    assert not m.np1_triggered  # greenfield suppresses NP-1
    assert not m.np2_triggered
    # NP-3 not triggered at 5% headroom
    assert not m.np3_triggered
