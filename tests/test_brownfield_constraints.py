"""
tests/test_brownfield_constraints.py

Mandatory test cases for the Brownfield Constraint Engine.

Tests:
  1. Fully feasible plant — all checks PASS
  2. Clarifier overload — SOR FAIL
  3. Aeration limited — blower FAIL
  4. Volume deficit with can_add_new_tank=True — WARNING (not FAIL)
  5. Volume deficit with can_add_new_tank=False — FAIL
  6. No shutdown tolerance — constructability WARNING
  7. Technology without clarifier (AGS) — SOR check SKIP
  8. Missing context fields — graceful SKIP (never crash)
  9. Integration: evaluate_all() with ScenarioModel objects
"""
from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# import pytest  # optional
from dataclasses import dataclass
from typing import Any, Optional

from domains.wastewater.brownfield.brownfield_context import BrownfieldContext
from domains.wastewater.brownfield.constraint_engine import (
    evaluate,
    evaluate_all,
    BrownfieldConstraintResult,
)


# ── Test fixture helpers ──────────────────────────────────────────────────────

@dataclass
class _MockPerf:
    """Minimal performance_outputs proxy for tests."""
    reactor_volume_m3:      float = 2755.0
    footprint_m2:           float = 1029.0
    aeration_energy_kwh_day: float = 2116.8
    clarifier_area_m2:      float = 417.0
    n_clarifiers:           int   = 2
    v_anaerobic_m3:         float = 276.0
    v_anoxic_m3:            float = 827.0
    v_aerobic_m3:           float = 1653.0
    peak_flow_factor:       float = 1.5

    def get(self, key, default=None):
        return getattr(self, key, default)

    def items(self):
        return vars(self).items()


class _MockTechResult:
    """Minimal TechnologyResult proxy for tests."""
    def __init__(self, po: dict, footprint: float = 1029.0, volume: float = 2755.0):
        self.performance_outputs = po
        self.footprint_m2        = footprint
        self.volume_m3           = volume


def _make_inputs(flow_mld: float = 10.0, peak_factor: float = 1.5):
    """Minimal WastewaterInputs proxy."""
    class _Inp:
        design_flow_mld = flow_mld
        peak_flow_factor = peak_factor
        peak_flow_mld   = None
    return _Inp()


def _make_tech_result(
    volume_m3:               float = 2755.0,
    footprint_m2:            float = 1029.0,
    aeration_kwh_day:        float = 2116.8,
    clarifier_area_m2:       float = 417.0,
    n_clarifiers:            int   = 2,
    peak_flow_factor:        float = 1.5,
) -> _MockTechResult:
    po = {
        "reactor_volume_m3":       volume_m3,
        "footprint_m2":            footprint_m2,
        "aeration_energy_kwh_day": aeration_kwh_day,
        "clarifier_area_m2":       clarifier_area_m2,
        "n_clarifiers":            n_clarifiers,
        "peak_flow_factor":        peak_flow_factor,
    }
    return _MockTechResult(po, footprint_m2, volume_m3)


# ── Test 1: Fully feasible plant ─────────────────────────────────────────────

def test_fully_feasible():
    """
    Plant with ample capacity across all checks — all PASS.

    Scenario: 10 MLD BNR upgrade. Existing plant was designed for 12 MLD
    so volume, clarifiers, blower, and pumps all have headroom.
    """
    bf = BrownfieldContext(
        anaerobic_volume_m3    = 330.0,
        anoxic_volume_m3       = 990.0,
        aerobic_volume_m3      = 2000.0,    # total = 3320 > required 2755
        clarifier_area_m2      = 550.0,     # per clarifier
        clarifier_count        = 2,          # total = 1100 m²
        blower_capacity_kw     = 200.0,     # operational ~88 kW × 1.2 = 106 → OK
        ras_capacity_m3_d      = 15000.0,   # 1.5 × 10000
        mlr_capacity_m3_d      = 50000.0,   # 5 × 10000 — for MLR
        available_footprint_m2 = 2000.0,
        can_add_new_tank       = True,
        max_shutdown_days      = 60,
    )
    tr  = _make_tech_result()
    inp = _make_inputs()

    result = evaluate("BNR Upgrade", "bnr", tr, inp, bf)

    assert result.feasible,                  f"Expected feasible, got: {result.violations}"
    assert result.status == "PASS",          f"Expected PASS, got {result.status}"
    assert result.violations == [],          f"Expected no violations, got: {result.violations}"

    # Verify utilisation_summary populated
    us = result.utilisation_summary
    assert us["volume_utilisation_pct"] is not None
    assert us["volume_utilisation_pct"] < 100.0   # existing > required

    print(f"Test 1 PASS: {result.summary_line()}")


# ── Test 2: Clarifier overload ────────────────────────────────────────────────

def test_clarifier_overload():
    """
    Clarifiers are undersized for peak flow — SOR FAIL.

    At 10 MLD × 1.5 peak = 15 MLD = 625 m³/hr
    One clarifier @ 150 m²: SOR = 625 / 150 = 4.17 m/hr >> limit 1.5 m/hr
    """
    bf = BrownfieldContext(
        anaerobic_volume_m3    = 330.0,
        anoxic_volume_m3       = 990.0,
        aerobic_volume_m3      = 2000.0,
        clarifier_area_m2      = 150.0,    # ← too small
        clarifier_count        = 1,         # one small clarifier
        blower_capacity_kw     = 200.0,
        ras_capacity_m3_d      = 15000.0,
        mlr_capacity_m3_d      = 50000.0,
        available_footprint_m2 = 2000.0,
        can_add_new_tank       = True,
        max_shutdown_days      = 60,
    )
    tr  = _make_tech_result(clarifier_area_m2=417.0, n_clarifiers=2)
    inp = _make_inputs()

    result = evaluate("BNR Upgrade", "bnr", tr, inp, bf)

    assert not result.feasible,    "Expected infeasible due to clarifier overload"
    assert result.status == "FAIL"

    # Specifically the clarifier check must have failed
    clar_check = next(c for c in result.checks if c.name == "Clarifier SOR")
    assert clar_check.status == "FAIL", f"Expected FAIL, got {clar_check.status}"
    assert clar_check.utilisation_pct > 100.0

    us = result.utilisation_summary
    assert us["clarifier_utilisation_pct"] is not None
    assert us["clarifier_utilisation_pct"] > 100.0

    print(f"Test 2 PASS: {result.summary_line()}")


# ── Test 3: Aeration limited ──────────────────────────────────────────────────

def test_aeration_limited():
    """
    Blower capacity insufficient for required aeration demand — FAIL.

    BNR requires ~2117 kWh/day aeration → operational 88 kW → installed 106 kW
    Existing blower only 50 kW — FAIL.
    """
    bf = BrownfieldContext(
        anaerobic_volume_m3    = 330.0,
        anoxic_volume_m3       = 990.0,
        aerobic_volume_m3      = 2000.0,
        clarifier_area_m2      = 550.0,
        clarifier_count        = 2,
        blower_capacity_kw     = 50.0,      # ← far too small
        ras_capacity_m3_d      = 15000.0,
        mlr_capacity_m3_d      = 50000.0,
        available_footprint_m2 = 2000.0,
        can_add_new_tank       = True,
        max_shutdown_days      = 60,
    )
    tr  = _make_tech_result()   # aeration_kwh_day = 2116.8 → installed 106 kW needed
    inp = _make_inputs()

    result = evaluate("BNR Upgrade", "bnr", tr, inp, bf)

    assert not result.feasible, "Expected infeasible due to aeration limit"
    assert result.status == "FAIL"

    aer_check = next(c for c in result.checks if c.name == "Aeration Capacity")
    assert aer_check.status == "FAIL",       f"Expected FAIL, got {aer_check.status}"
    assert aer_check.utilisation_pct > 100.0

    us = result.utilisation_summary
    assert us["aeration_utilisation_pct"] is not None
    assert us["aeration_utilisation_pct"] > 100.0

    print(f"Test 3 PASS: {result.summary_line()}")


# ── Test 4: Volume deficit — can_add_new_tank=True → WARNING, not FAIL ───────

def test_volume_deficit_can_add_tank():
    """
    Required volume exceeds existing but new tank construction is permitted.
    Expect WARNING, NOT FAIL — feasible with condition.
    """
    bf = BrownfieldContext(
        anaerobic_volume_m3    = 200.0,
        anoxic_volume_m3       = 500.0,
        aerobic_volume_m3      = 1000.0,    # total = 1700 < required 2755
        clarifier_area_m2      = 550.0,
        clarifier_count        = 2,
        blower_capacity_kw     = 200.0,
        ras_capacity_m3_d      = 15000.0,
        mlr_capacity_m3_d      = 50000.0,
        available_footprint_m2 = 2000.0,
        can_add_new_tank       = True,      # ← key: allowed
        max_shutdown_days      = 60,
    )
    tr  = _make_tech_result()
    inp = _make_inputs()

    result = evaluate("BNR Upgrade", "bnr", tr, inp, bf)

    vol_check = next(c for c in result.checks if c.name == "Biological Volume")
    assert vol_check.status == "WARNING",    f"Expected WARNING, got {vol_check.status}"
    # Overall should be WARNING, not FAIL
    assert result.status == "WARNING",       f"Expected WARNING status, got {result.status}"
    # Still feasible — no hard FAIL
    assert result.feasible,                  f"Expected feasible (WARNING only)"

    print(f"Test 4 PASS: {result.summary_line()}")


# ── Test 5: Volume deficit — can_add_new_tank=False → FAIL ───────────────────

def test_volume_deficit_no_new_tank():
    """
    Required volume exceeds existing and new tank construction not permitted.
    Expect FAIL — technology cannot be accommodated.
    """
    bf = BrownfieldContext(
        anaerobic_volume_m3    = 200.0,
        anoxic_volume_m3       = 500.0,
        aerobic_volume_m3      = 1000.0,    # total = 1700 < required 2755
        clarifier_area_m2      = 550.0,
        clarifier_count        = 2,
        blower_capacity_kw     = 200.0,
        ras_capacity_m3_d      = 15000.0,
        mlr_capacity_m3_d      = 50000.0,
        available_footprint_m2 = 500.0,
        can_add_new_tank       = False,     # ← key: not allowed
        max_shutdown_days      = 60,
    )
    tr  = _make_tech_result()
    inp = _make_inputs()

    result = evaluate("BNR Upgrade", "bnr", tr, inp, bf)

    vol_check = next(c for c in result.checks if c.name == "Biological Volume")
    assert vol_check.status == "FAIL",       f"Expected FAIL, got {vol_check.status}"
    assert not result.feasible
    assert result.status == "FAIL"

    print(f"Test 5 PASS: {result.summary_line()}")


# ── Test 6: Constructability — shutdown exceeds max ───────────────────────────

def test_constructability_warning():
    """
    AGS conversion requires 30-day shutdown but utility allows only 7 days.
    Expect WARNING (not FAIL) — constructability is always informational.
    """
    bf = BrownfieldContext(
        anaerobic_volume_m3    = 330.0,
        anoxic_volume_m3       = 990.0,
        aerobic_volume_m3      = 2500.0,
        clarifier_area_m2      = 550.0,
        clarifier_count        = 2,
        blower_capacity_kw     = 250.0,
        ras_capacity_m3_d      = 15000.0,
        mlr_capacity_m3_d      = 0.0,       # AGS: no MLR
        available_footprint_m2 = 2000.0,
        can_add_new_tank       = True,
        max_shutdown_days      = 7,         # ← very tight window
    )
    tr  = _make_tech_result(
        volume_m3=2083.0,
        footprint_m2=949.0,
        aeration_kwh_day=2127.5,
        clarifier_area_m2=None,
        n_clarifiers=0,
    )
    inp = _make_inputs()

    result = evaluate("AGS Conversion", "granular_sludge", tr, inp, bf)

    con_check = next(c for c in result.checks if c.name == "Constructability")
    assert con_check.status == "WARNING",    f"Expected WARNING, got {con_check.status}"
    # Constructability WARNING does NOT make scenario infeasible
    # (other checks may pass)
    assert "HIGH CONSTRUCTION RISK" in con_check.message

    print(f"Test 6 PASS: {result.summary_line()}")


# ── Test 7: AGS — clarifier SOR skipped ──────────────────────────────────────

def test_ags_no_clarifier_check():
    """
    AGS (granular_sludge) does not use secondary clarifiers.
    Clarifier SOR check must be SKIP, not FAIL.
    """
    bf = BrownfieldContext(
        anaerobic_volume_m3    = 330.0,
        anoxic_volume_m3       = 990.0,
        aerobic_volume_m3      = 2500.0,
        clarifier_area_m2      = 50.0,      # tiny — would FAIL if checked
        clarifier_count        = 1,
        blower_capacity_kw     = 250.0,
        ras_capacity_m3_d      = 0.0,       # no RAS for AGS
        mlr_capacity_m3_d      = 0.0,
        available_footprint_m2 = 2000.0,
        can_add_new_tank       = True,
        max_shutdown_days      = 60,
    )
    tr  = _make_tech_result(
        volume_m3=2083.0, footprint_m2=949.0,
        aeration_kwh_day=2127.5, clarifier_area_m2=None, n_clarifiers=0,
    )
    inp = _make_inputs()

    result = evaluate("AGS", "granular_sludge", tr, inp, bf)

    clar_check = next(c for c in result.checks if c.name == "Clarifier SOR")
    assert clar_check.status == "SKIP",      f"Expected SKIP, got {clar_check.status}"

    print(f"Test 7 PASS: SOR check correctly SKIP for AGS")


# ── Test 8: Missing context fields — graceful SKIP ───────────────────────────

def test_missing_context_fields():
    """
    Incomplete BrownfieldContext — checks with missing data must SKIP,
    never raise an exception.
    """
    bf = BrownfieldContext()   # all None defaults
    tr  = _make_tech_result()
    inp = _make_inputs()

    # Must not raise
    result = evaluate("BNR", "bnr", tr, inp, bf)

    # Every check should be SKIP (no data to assess against)
    skip_count = sum(1 for c in result.checks if c.status == "SKIP")
    assert skip_count >= 3, f"Expected ≥3 SKIP checks with empty context, got {skip_count}"

    print(f"Test 8 PASS: {skip_count} checks correctly SKIP with empty context")


# ── Test 9: Integration — evaluate_all() with ScenarioModel-like objects ─────

def test_evaluate_all():
    """
    evaluate_all() processes a list of scenario proxies and returns a dict
    keyed by scenario_name.  Verifies integration without needing a live
    ScenarioModel.
    """
    from types import SimpleNamespace

    bf = BrownfieldContext(
        anaerobic_volume_m3    = 330.0,
        anoxic_volume_m3       = 990.0,
        aerobic_volume_m3      = 2000.0,
        clarifier_area_m2      = 550.0,
        clarifier_count        = 2,
        blower_capacity_kw     = 200.0,
        ras_capacity_m3_d      = 15000.0,
        mlr_capacity_m3_d      = 50000.0,
        available_footprint_m2 = 2000.0,
        can_add_new_tank       = True,
        max_shutdown_days      = 60,
    )
    inp = _make_inputs()

    # Build minimal scenario proxies matching ScenarioModel interface
    po_bnr = {
        "reactor_volume_m3":       2755.0,
        "footprint_m2":            1029.0,
        "aeration_energy_kwh_day": 2116.8,
        "clarifier_area_m2":       417.0,
        "n_clarifiers":            2,
        "peak_flow_factor":        1.5,
    }

    def _make_scenario(name, tc, po):
        tp = SimpleNamespace(technology_sequence=[tc])
        dso = {"technology_performance": {tc: po}}
        return SimpleNamespace(
            scenario_name=name,
            treatment_pathway=tp,
            domain_specific_outputs=dso,
        )

    scenarios = [
        _make_scenario("BNR Base",   "bnr", po_bnr),
        _make_scenario("IFAS Upg",   "ifas_mbbr", {**po_bnr, "reactor_volume_m3": 3360.0}),
    ]

    results = evaluate_all(scenarios, bf, inp)

    assert "BNR Base"  in results,  "BNR Base missing from results"
    assert "IFAS Upg"  in results,  "IFAS Upg missing from results"
    assert isinstance(results["BNR Base"],  BrownfieldConstraintResult)
    assert isinstance(results["IFAS Upg"],  BrownfieldConstraintResult)

    print(f"Test 9 PASS: evaluate_all returned {len(results)} results")
    for name, r in results.items():
        print(f"  {name}: {r.status}  — {r.summary_line()[:60]}")


# ── Run all tests ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    tests = [
        test_fully_feasible,
        test_clarifier_overload,
        test_aeration_limited,
        test_volume_deficit_can_add_tank,
        test_volume_deficit_no_new_tank,
        test_constructability_warning,
        test_ags_no_clarifier_check,
        test_missing_context_fields,
        test_evaluate_all,
    ]
    passed = failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"FAIL {t.__name__}: {e}")
            import traceback; traceback.print_exc()
            failed += 1
    print(f"\n{'='*60}")
    print(f"  {passed}/{passed+failed} tests passed")
    if failed:
        raise SystemExit(1)
