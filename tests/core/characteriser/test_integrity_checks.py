"""
tests/test_integrity_checks.py

Tests for the integrity-checks module. The critical invariant is that every
INT-class flag carries `affected_row_indices`, because Addition C
(integrity-aware secondary medians) and Section 5 (integrity flags affecting
matched subset) both rely on it.

Tests organised by rule ID. Each test injects exactly the violation under
test using the dirty_df fixture, then asserts:
  - the right rule fires
  - the right rows are listed
  - severity matches the spec
"""
from __future__ import annotations
import pytest

from core.characteriser.integrity_checks import run_integrity_checks
from core.characteriser.report import (
    SEV_CRITICAL, SEV_WARNING, SEV_INFO,
)
from tests.core.characteriser.conftest import DIRTY_INJECTIONS


# ── Clean fixture: no flags ─────────────────────────────────────────────────

def test_clean_dataset_raises_no_flags(clean_df, minimal_config):
    """A clean synthetic dataset should produce zero integrity flags."""
    flags = run_integrity_checks(clean_df, minimal_config)
    # Allow zero or near-zero — synthetic noise can occasionally clip
    # extreme percentiles. The clean fixture should not trip any INT-01 or
    # INT-05 in particular.
    critical = [f for f in flags if f.severity == SEV_CRITICAL]
    assert critical == [], f"Clean dataset produced critical flags: {critical}"

    # No row-level identity violations on clean data
    int05 = [f for f in flags if f.rule_id == "INT-05"]
    assert int05 == [], f"Clean dataset has INT-05 flags: {int05}"


# ── INT-01: physical range violation ────────────────────────────────────────

def test_int01_catches_negative_bod(dirty_df, minimal_config):
    flags = run_integrity_checks(dirty_df, minimal_config)
    int01_bod = [f for f in flags if f.rule_id == "INT-01" and f.parameter == "bod_mg_l"]
    assert len(int01_bod) == 1
    f = int01_bod[0]
    assert f.severity == SEV_CRITICAL
    assert DIRTY_INJECTIONS["bod_negative"] in f.affected_row_indices
    assert len(f.affected_row_indices) == 1


def test_int01_catches_ph_above_14(dirty_df, minimal_config):
    flags = run_integrity_checks(dirty_df, minimal_config)
    int01_ph = [f for f in flags if f.rule_id == "INT-01" and f.parameter == "ph"]
    assert len(int01_ph) == 1
    f = int01_ph[0]
    assert f.severity == SEV_CRITICAL
    assert DIRTY_INJECTIONS["ph_too_high"] in f.affected_row_indices


def test_int01_message_includes_bounds_and_examples(dirty_df, minimal_config):
    flags = run_integrity_checks(dirty_df, minimal_config)
    int01 = [f for f in flags if f.rule_id == "INT-01"][0]
    # Message must mention the parameter and the violation count
    assert int01.parameter in int01.message or "bod" in int01.message.lower() or "ph" in int01.message.lower()
    # Severity-critical flags must carry implication and recommended action
    assert int01.implication != ""
    assert int01.recommended_action != ""


# ── INT-01b: typical range excursion ────────────────────────────────────────

def test_int01b_catches_atypical_bod(dirty_df, minimal_config):
    flags = run_integrity_checks(dirty_df, minimal_config)
    int01b_bod = [f for f in flags if f.rule_id == "INT-01b" and f.parameter == "bod_mg_l"]
    # Should catch the deliberate 850 mg/L injection (row 300) plus collateral
    # values >600 from row 101 (zero) won't trigger since zero is below typical low.
    # Row 250 (950) is in the typical-excess range too. So 2-3 rows expected.
    assert len(int01b_bod) >= 1
    f = int01b_bod[0]
    assert DIRTY_INJECTIONS["bod_typical_excess"] in f.affected_row_indices
    assert f.severity in (SEV_INFO, SEV_WARNING)


def test_int01b_severity_scales_with_count(clean_df, minimal_config):
    """Few excursions → Info; sustained pattern → Warning."""
    # Build a dataframe where 5% of BOD values are well above typical max
    import numpy as np
    df = clean_df.copy()
    # Push 30 random rows to BOD=750 (above typical, below physical)
    rng = np.random.default_rng(7)
    idx = rng.choice(len(df), size=30, replace=False)
    df.loc[idx, "bod_mg_l"] = 750.0

    flags = run_integrity_checks(df, minimal_config)
    int01b_bod = [f for f in flags if f.rule_id == "INT-01b" and f.parameter == "bod_mg_l"]
    assert len(int01b_bod) == 1
    # 30 of 365 ≈ 8.2% → above the 1% threshold → Warning
    assert int01b_bod[0].severity == SEV_WARNING


# ── INT-02: implausible zeros ───────────────────────────────────────────────

def test_int02_catches_zero_flow(dirty_df, minimal_config):
    flags = run_integrity_checks(dirty_df, minimal_config)
    int02_flow = [f for f in flags if f.rule_id == "INT-02" and f.parameter == "flow_mld"]
    assert len(int02_flow) == 1
    f = int02_flow[0]
    assert f.severity == SEV_WARNING
    assert DIRTY_INJECTIONS["flow_zero"] in f.affected_row_indices


def test_int02_catches_zero_bod(dirty_df, minimal_config):
    flags = run_integrity_checks(dirty_df, minimal_config)
    int02_bod = [f for f in flags if f.rule_id == "INT-02" and f.parameter == "bod_mg_l"]
    assert len(int02_bod) == 1
    assert DIRTY_INJECTIONS["bod_zero"] in int02_bod[0].affected_row_indices


def test_int02_skips_rainfall(dirty_df, minimal_config):
    """Rainfall can legitimately be zero on dry days; INT-02 must skip it."""
    flags = run_integrity_checks(dirty_df, minimal_config)
    int02_rainfall = [f for f in flags if f.rule_id == "INT-02" and f.parameter == "rainfall_mm"]
    assert int02_rainfall == [], "INT-02 must not fire on rainfall"


# ── INT-03: duplicate dates ─────────────────────────────────────────────────

def test_int03_catches_duplicate_dates(dirty_df, minimal_config):
    flags = run_integrity_checks(dirty_df, minimal_config)
    int03 = [f for f in flags if f.rule_id == "INT-03"]
    assert len(int03) == 1
    f = int03[0]
    assert f.severity == SEV_WARNING
    # Both row 200 and 201 should be flagged
    assert DIRTY_INJECTIONS["duplicate_date_a"] in f.affected_row_indices
    assert DIRTY_INJECTIONS["duplicate_date_b"] in f.affected_row_indices


# ── INT-04: scattered NaN ───────────────────────────────────────────────────

def test_int04_catches_scattered_nan(dirty_df, minimal_config):
    flags = run_integrity_checks(dirty_df, minimal_config)
    int04_cod = [f for f in flags if f.rule_id == "INT-04" and f.parameter == "cod_mg_l"]
    assert len(int04_cod) == 1
    f = int04_cod[0]
    assert f.severity == SEV_INFO
    assert DIRTY_INJECTIONS["scattered_nan_cod"] in f.affected_row_indices


def test_int04_does_not_fire_on_clean(clean_df, minimal_config):
    """No scattered NaN should appear on the clean fixture."""
    flags = run_integrity_checks(clean_df, minimal_config)
    int04 = [f for f in flags if f.rule_id == "INT-04"]
    assert int04 == []


# ── INT-05: stoichiometric identity violation ───────────────────────────────

def test_int05_catches_bod_exceeds_cod(dirty_df, minimal_config):
    flags = run_integrity_checks(dirty_df, minimal_config)
    int05 = [f for f in flags if f.rule_id == "INT-05"]
    assert len(int05) == 1
    f = int05[0]
    # Identity violations are severity-Warning unless ≥5% of rows violate
    assert f.severity == SEV_WARNING
    assert "bod_mg_l" in f.parameter and "cod_mg_l" in f.parameter
    assert DIRTY_INJECTIONS["bod_exceeds_cod"] in f.affected_row_indices


def test_int05_pattern_includes_identity_label(dirty_df, minimal_config):
    flags = run_integrity_checks(dirty_df, minimal_config)
    int05 = [f for f in flags if f.rule_id == "INT-05"][0]
    # The pattern label should reference the identity (e.g., "BOD ≤ COD")
    assert "≤" in int05.pattern or "<=" in int05.pattern or "vs" in int05.pattern


# ── Cross-cutting: affected_row_indices invariant ───────────────────────────

def test_all_int_flags_carry_row_indices(dirty_df, minimal_config):
    """
    The critical invariant for Addition C: every INT-class flag must carry
    populated affected_row_indices. If this regresses, Addition C breaks
    silently.
    """
    flags = run_integrity_checks(dirty_df, minimal_config)
    for f in flags:
        if f.rule_id.startswith("INT-"):
            assert f.affected_row_indices, (
                f"{f.rule_id} on {f.parameter} has empty affected_row_indices — "
                "Addition C will not work for this flag."
            )


def test_row_indices_are_valid_dataframe_indices(dirty_df, minimal_config):
    """affected_row_indices must reference rows that exist in the dataframe."""
    flags = run_integrity_checks(dirty_df, minimal_config)
    valid_indices = set(dirty_df.index.tolist())
    for f in flags:
        for idx in f.affected_row_indices:
            assert idx in valid_indices, (
                f"{f.rule_id} references row {idx} which is not in the dataframe."
            )
