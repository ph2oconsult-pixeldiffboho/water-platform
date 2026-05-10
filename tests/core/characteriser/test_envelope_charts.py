"""
tests/test_envelope_charts.py

Tests for the chart renderer. The renderer writes PNG files to disk and
populates path fields on the envelope object. We test that files are
produced where expected, that absent inputs are handled gracefully, and
that the auto-redundancy logic excludes the right pairs from scatter
rendering.
"""
from __future__ import annotations
import pandas as pd
import pytest

from core.characteriser.design_envelope import build_design_envelope
from core.characteriser.envelope_charts import (
    render_envelope_charts,
    _should_exclude_pair, _is_expected_coupling,
    _is_concentration_vs_its_load,
    _find_significant_pairs, _compute_correlation_matrix,
)


# ── Auto-redundancy logic ───────────────────────────────────────────────────

class TestAutoRedundancy:

    def test_self_pair_excluded(self):
        assert _should_exclude_pair("bod_mg_l", "bod_mg_l") is True

    def test_concentration_vs_its_own_load_excluded(self):
        """BOD_mg_L vs BOD_load_kg_d is arithmetic — not informative."""
        assert _is_concentration_vs_its_load("bod_mg_l", "bod_load_kg_d") is True
        assert _is_concentration_vs_its_load("cod_mg_l", "cod_load_kg_d") is True
        # Either order
        assert _is_concentration_vs_its_load("bod_load_kg_d", "bod_mg_l") is True

    def test_concentration_vs_different_load_not_excluded(self):
        """BOD vs COD_load is a real relationship, not redundant."""
        assert _is_concentration_vs_its_load("bod_mg_l", "cod_load_kg_d") is False

    def test_expected_coupling_identified(self):
        """Component pairs (BOD-COD, NH4-TKN, VSS-TSS) are coupled by definition."""
        assert _is_expected_coupling("cod_mg_l", "scod_mg_l") is True
        assert _is_expected_coupling("scod_mg_l", "cod_mg_l") is True  # order independent
        assert _is_expected_coupling("tkn_mg_l", "nh4_mg_l") is True
        assert _is_expected_coupling("tss_mg_l", "vss_mg_l") is True

    def test_unrelated_pair_not_coupled(self):
        assert _is_expected_coupling("flow_mld", "tp_mg_l") is False


# ── Correlation matrix ──────────────────────────────────────────────────────

class TestCorrelationMatrix:

    def test_matrix_is_square_and_symmetric(self, clean_df):
        corr = _compute_correlation_matrix(
            clean_df, ["bod_mg_l", "cod_mg_l", "tss_mg_l"],
        )
        assert corr.shape == (3, 3)
        # Spearman correlation matrix is symmetric
        assert corr.equals(corr.T)
        # Diagonal is 1
        for i in range(3):
            assert corr.iloc[i, i] == pytest.approx(1.0)

    def test_skips_missing_columns(self, clean_df):
        """With only one valid column, the function returns an empty matrix
        (correlation needs at least two)."""
        corr = _compute_correlation_matrix(
            clean_df, ["bod_mg_l", "nonexistent_column"],
        )
        assert corr.empty

    def test_includes_present_columns_drops_missing(self, clean_df):
        """With ≥2 present columns and 1 missing, matrix covers the present ones."""
        corr = _compute_correlation_matrix(
            clean_df, ["bod_mg_l", "cod_mg_l", "nonexistent_column"],
        )
        assert corr.shape == (2, 2)
        assert "bod_mg_l" in corr.columns
        assert "cod_mg_l" in corr.columns
        assert "nonexistent_column" not in corr.columns

    def test_returns_empty_when_too_few_columns(self, clean_df):
        corr = _compute_correlation_matrix(clean_df, ["only_one"])
        assert corr.empty

    def test_find_significant_pairs_respects_threshold(self, clean_df):
        corr = _compute_correlation_matrix(
            clean_df,
            ["bod_mg_l", "cod_mg_l", "tss_mg_l", "tkn_mg_l", "tp_mg_l", "temperature_c"],
        )
        # At 0.6 we should get some pairs (BOD-COD, BOD-TSS are tightly coupled in the
        # synthetic data); at 0.99 we should get none.
        pairs_06 = _find_significant_pairs(corr, threshold=0.6)
        pairs_99 = _find_significant_pairs(corr, threshold=0.99)
        assert len(pairs_06) > len(pairs_99)
        # All returned correlations meet the threshold
        for a, b, rho in pairs_06:
            assert abs(rho) >= 0.6

    def test_find_significant_pairs_sorted_by_abs_corr(self, clean_df):
        corr = _compute_correlation_matrix(
            clean_df,
            ["bod_mg_l", "cod_mg_l", "tss_mg_l", "tkn_mg_l", "tp_mg_l"],
        )
        pairs = _find_significant_pairs(corr, threshold=0.0)  # everything
        # Pairs sorted descending by |rho|
        for i in range(len(pairs) - 1):
            assert abs(pairs[i][2]) >= abs(pairs[i + 1][2])


# ── Chart rendering ─────────────────────────────────────────────────────────

class TestRenderCharts:

    def test_all_four_charts_written(self, clean_df, tmp_path):
        env = build_design_envelope(
            df=clean_df, condition_spec={"flow_mld": ">P75"}, label="Test"
        )
        out_dir = tmp_path / "charts"
        render_envelope_charts(clean_df, env, str(out_dir))

        # All four PNGs present
        expected = [
            "figure_2_1_heatmap.png",
            "figure_2_2_scatters.png",
            "figure_3_1_timeseries.png",
            "figure_4_1_overdesign.png",
        ]
        for fname in expected:
            assert (out_dir / fname).exists(), f"Missing {fname}"
            # Non-trivial size
            assert (out_dir / fname).stat().st_size > 1000

    def test_chart_paths_populated_on_envelope(self, clean_df, tmp_path):
        env = build_design_envelope(
            df=clean_df, condition_spec={"flow_mld": ">P75"}, label="Test"
        )
        # Before rendering, all paths None
        assert env.population.heatmap_path is None

        render_envelope_charts(clean_df, env, str(tmp_path / "charts"))

        # After rendering, paths populated
        assert env.population.heatmap_path is not None
        assert env.population.scatters_path is not None
        assert env.events.time_series_path is not None
        assert env.over_design.over_design_chart_path is not None
        assert env.charts_directory is not None

    def test_insufficient_envelope_skips_charts(self, clean_df, tmp_path):
        """When sample_confidence is Insufficient, no charts should be written."""
        env = build_design_envelope(
            df=clean_df,
            condition_spec={"flow_mld": ">P99.7"},  # ~1 match
            label="Test",
        )
        assert env.population.sample_confidence == "Insufficient"

        out_dir = tmp_path / "charts"
        render_envelope_charts(clean_df, env, str(out_dir))
        # Out dir is created but no chart files
        charts = list(out_dir.glob("figure_*.png"))
        assert charts == [], (
            f"Expected no charts on Insufficient envelope, got {charts}"
        )

    def test_scatters_pair_count_recorded(self, clean_df, tmp_path):
        """The number of pairs rendered must be set on the population section."""
        env = build_design_envelope(
            df=clean_df, condition_spec={"flow_mld": ">P75"}, label="Test"
        )
        render_envelope_charts(clean_df, env, str(tmp_path / "charts"))
        # Should be set, even if zero
        assert isinstance(env.population.scatters_pair_count, int)
        assert env.population.scatters_pair_count >= 0

    def test_charts_directory_is_absolute(self, clean_df, tmp_path):
        env = build_design_envelope(
            df=clean_df, condition_spec={"flow_mld": ">P75"}, label="Test"
        )
        render_envelope_charts(clean_df, env, str(tmp_path / "charts"))
        import os
        assert os.path.isabs(env.charts_directory)

    def test_dirty_dataset_charts_still_render(self, dirty_df, characterisation_report_factory, tmp_path):
        """Integrity issues must not prevent chart rendering."""
        report = characterisation_report_factory(dirty_df)
        env = build_design_envelope(
            df=dirty_df, condition_spec={"flow_mld": ">P75"},
            label="Dirty test", report=report,
        )
        out_dir = tmp_path / "charts"
        # Should not raise
        render_envelope_charts(dirty_df, env, str(out_dir))
        assert (out_dir / "figure_2_1_heatmap.png").exists()
