"""
tests/test_coincidence.py

Contract tests for coincidence.py. The current implementation in Phase 5 is
a stub; these tests document the contract the real coincidence module must
honour for design_envelope to work correctly. When the real module replaces
the stub, these tests should still pass — they describe the interface, not
the stub's internals.
"""
from __future__ import annotations
import pandas as pd
import pytest

from core.characteriser.coincidence import (
    analyse_coincidence, compare_to_naive_stacking, _build_mask,
    OverDesignComparison,
)


# ── _build_mask ─────────────────────────────────────────────────────────────

def test_build_mask_percentile_above(clean_df):
    mask, label = _build_mask(clean_df, {"flow_mld": ">P95"})
    assert mask is not None
    # ~5% of rows should be above P95
    assert 12 <= mask.sum() <= 24, f"Expected ~18 matches at >P95, got {mask.sum()}"
    assert "flow_mld" in label


def test_build_mask_percentile_below(clean_df):
    mask, _ = _build_mask(clean_df, {"temperature_c": "<P10"})
    assert mask is not None
    assert 25 <= mask.sum() <= 50  # ~10% of rows


def test_build_mask_numeric_threshold(clean_df):
    mask, _ = _build_mask(clean_df, {"flow_mld": ">25"})
    expected = (clean_df["flow_mld"] > 25).sum()
    assert mask.sum() == expected


def test_build_mask_compound_condition(clean_df):
    """Multiple conditions are ANDed."""
    mask, label = _build_mask(clean_df, {
        "flow_mld": ">P75",
        "temperature_c": "<P50",
    })
    assert mask is not None
    assert "AND" in label
    # The intersection must be ≤ either single condition's count
    mask_flow, _ = _build_mask(clean_df, {"flow_mld": ">P75"})
    mask_temp, _ = _build_mask(clean_df, {"temperature_c": "<P50"})
    assert mask.sum() <= mask_flow.sum()
    assert mask.sum() <= mask_temp.sum()


def test_build_mask_returns_none_for_missing_column(clean_df):
    mask, label = _build_mask(clean_df, {"nonexistent": ">P95"})
    assert mask is None
    assert "nonexistent" in label


def test_build_mask_returns_none_for_unparseable(clean_df):
    mask, label = _build_mask(clean_df, {"flow_mld": "garbage"})
    assert mask is None
    assert "unparseable" in label.lower()


def test_build_mask_nan_yields_false(clean_df):
    """Rows where the conditioning column is NaN must not match."""
    import numpy as np
    df = clean_df.copy()
    df.loc[10, "flow_mld"] = np.nan
    mask, _ = _build_mask(df, {"flow_mld": ">0"})
    assert not mask.loc[10], "NaN row should not satisfy any condition"


# ── analyse_coincidence ─────────────────────────────────────────────────────

def test_analyse_coincidence_basic(clean_df):
    result = analyse_coincidence(
        clean_df, {"flow_mld": ">P95"},
        condition_label="Peak hydraulic",
        parameters_to_report=["bod_mg_l", "cod_mg_l", "tss_mg_l"],
    )
    assert result.n_total == len(clean_df)
    assert result.n_matching > 0
    assert 0 < result.matching_pct < 100
    assert result.confidence in ("Strong", "Acceptable", "Limited", "Insufficient")
    assert len(result.conditional_stats) == 3


def test_analyse_coincidence_insufficient_confidence(clean_df):
    """A condition matching <10 rows should be 'Insufficient'."""
    result = analyse_coincidence(
        clean_df, {"flow_mld": ">P99.5"},  # ~2 matches
        parameters_to_report=["bod_mg_l"],
    )
    assert result.confidence == "Insufficient"
    # No conditional stats should be returned when Insufficient
    assert result.conditional_stats == []


def test_analyse_coincidence_shift_classification(clean_df):
    """For flow >P95, flow itself should show clear upward shift (any non-None
    significance — the exact magnitude depends on the distribution shape)."""
    result = analyse_coincidence(
        clean_df, {"flow_mld": ">P95"},
        parameters_to_report=["flow_mld"],
    )
    assert len(result.conditional_stats) == 1
    s = result.conditional_stats[0]
    assert s.shift_direction == "increased"
    assert s.shift_magnitude_pct > 0
    assert s.significance in ("Weak", "Moderate", "Strong")


def test_analyse_coincidence_stable_when_uncorrelated(clean_df):
    """tp_mg_l in the clean fixture doesn't depend on flow → should be stable."""
    result = analyse_coincidence(
        clean_df, {"flow_mld": ">P95"},
        parameters_to_report=["tp_mg_l"],
    )
    s = result.conditional_stats[0]
    assert s.shift_direction == "stable"
    assert s.significance == "None"


def test_analyse_coincidence_records_matching_dates(clean_df):
    result = analyse_coincidence(
        clean_df, {"flow_mld": ">P90"},
    )
    # All matching dates should be ISO strings
    for d in result.matching_dates:
        assert len(d) == 10 and d[4] == "-" and d[7] == "-"


# ── compare_to_naive_stacking ───────────────────────────────────────────────

def test_compare_to_naive_stacking_basic(clean_df):
    result = compare_to_naive_stacking(
        clean_df,
        governing_parameter="flow_mld",
        governing_percentile=95.0,
        coincident_parameters=["bod_mg_l", "cod_mg_l", "tss_mg_l"],
    )
    assert isinstance(result, OverDesignComparison)
    assert result.governing_parameter == "flow_mld"
    assert result.governing_percentile == 95.0
    assert result.governing_value > 0
    assert len(result.coincident_parameters) == 3
    for param, (naive, joint) in result.coincident_parameters.items():
        assert naive > 0
        # On the clean fixture, BOD/COD dilute slightly under high flow
        # so joint should be <= naive in most cases — but we can't assert that
        # universally, so we just check both are positive numerics
        assert isinstance(naive, float)
        assert isinstance(joint, float)


def test_compare_to_naive_stacking_governing_value_matches_percentile(clean_df):
    """The reported governing_value should equal the percentile of the column."""
    result = compare_to_naive_stacking(
        clean_df,
        governing_parameter="flow_mld",
        governing_percentile=95.0,
        coincident_parameters=["bod_mg_l"],
    )
    expected = float(clean_df["flow_mld"].dropna().quantile(0.95))
    assert abs(result.governing_value - expected) < 1e-6


def test_compare_to_naive_stacking_skips_missing_columns(clean_df):
    """Coincident parameters not in the df should be silently skipped."""
    result = compare_to_naive_stacking(
        clean_df,
        governing_parameter="flow_mld",
        governing_percentile=95.0,
        coincident_parameters=["bod_mg_l", "totally_made_up_parameter"],
    )
    assert "bod_mg_l" in result.coincident_parameters
    assert "totally_made_up_parameter" not in result.coincident_parameters


def test_compare_to_naive_stacking_returns_empty_for_missing_governing(clean_df):
    result = compare_to_naive_stacking(
        clean_df,
        governing_parameter="nonexistent",
        governing_percentile=95.0,
        coincident_parameters=["bod_mg_l"],
    )
    assert result.coincident_parameters == {}
