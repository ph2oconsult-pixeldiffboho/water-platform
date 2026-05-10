"""
tests/core/characteriser/test_streamlit_page.py

Smoke tests for the Phase 5 Streamlit page (page_15_design_envelope).

We can't easily exercise Streamlit widgets from unit tests, but the
non-UI parts are testable:
  - _adapt_columns: WaterPoint convention → envelope-engine convention
  - _candidate_condition_parameters: returns sensible options
  - the full pipeline runs cleanly on a WaterPoint-conventions dataframe

This last point is the integration check that matters: does the page
correctly bridge the cleaner's output to the envelope engine?
"""
from __future__ import annotations
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest


def _import_page():
    try:
        from apps.wastewater_app.pages import page_15_design_envelope
        return page_15_design_envelope
    except ModuleNotFoundError as exc:
        pytest.skip(f"Page imports unavailable in this test environment: {exc}")


@pytest.fixture
def waterpoint_clean_df():
    """A dataframe in WaterPoint's cleaner conventions:
       timestamp + influent_<param>_mg_l."""
    rng = np.random.default_rng(42)
    n = 365
    df = pd.DataFrame({
        "timestamp":             pd.date_range("2024-01-01", periods=n, freq="D"),
        "flow_mld":              np.clip(22 + rng.normal(0, 3, n), 10, None),
        "influent_bod_mg_l":     np.clip(240 + rng.normal(0, 20, n), 50, None),
        "influent_cod_mg_l":     np.clip(540 + rng.normal(0, 40, n), 100, None),
        "influent_tss_mg_l":     np.clip(255 + rng.normal(0, 25, n), 50, None),
        "influent_tkn_mg_l":     np.clip(45 + rng.normal(0, 3, n), 20, None),
        "influent_nh4_mg_l":     np.clip(32 + rng.normal(0, 2, n), 10, None),
        "influent_tp_mg_l":      np.clip(7.5 + rng.normal(0, 0.5, n), 2, None),
        "basin_temp_celsius":    18 + 5 * np.sin(2 * np.pi * np.arange(n) / 365.25),
    })
    return df


class TestAdaptColumns:

    def test_timestamp_becomes_date(self, waterpoint_clean_df):
        page = _import_page()
        adapted = page._adapt_columns(waterpoint_clean_df)
        assert "_date" in adapted.columns
        assert "timestamp" not in adapted.columns
        assert pd.api.types.is_datetime64_any_dtype(adapted["_date"])

    def test_influent_prefix_stripped(self, waterpoint_clean_df):
        page = _import_page()
        adapted = page._adapt_columns(waterpoint_clean_df)
        for col in ["bod_mg_l", "cod_mg_l", "tss_mg_l",
                    "tkn_mg_l", "nh4_mg_l", "tp_mg_l"]:
            assert col in adapted.columns, f"Missing {col} after rename"

    def test_basin_temp_renamed(self, waterpoint_clean_df):
        page = _import_page()
        adapted = page._adapt_columns(waterpoint_clean_df)
        assert "temperature_c" in adapted.columns
        assert "basin_temp_celsius" not in adapted.columns

    def test_loads_derived(self, waterpoint_clean_df):
        page = _import_page()
        adapted = page._adapt_columns(waterpoint_clean_df)
        for nutrient in ["bod", "cod", "tss", "tkn", "nh4", "tp"]:
            assert f"{nutrient}_load_kg_d" in adapted.columns

    def test_loads_value_correct(self, waterpoint_clean_df):
        page = _import_page()
        adapted = page._adapt_columns(waterpoint_clean_df)
        expected = adapted["bod_mg_l"] * adapted["flow_mld"]
        assert np.allclose(adapted["bod_load_kg_d"], expected)

    def test_ratios_derived(self, waterpoint_clean_df):
        page = _import_page()
        adapted = page._adapt_columns(waterpoint_clean_df)
        for ratio in ["nh4_to_tkn", "cod_to_bod", "bod_to_tkn", "tp_to_cod"]:
            assert ratio in adapted.columns, f"Missing ratio {ratio}"

    def test_original_not_mutated(self, waterpoint_clean_df):
        page = _import_page()
        original_cols = set(waterpoint_clean_df.columns)
        _ = page._adapt_columns(waterpoint_clean_df)
        assert set(waterpoint_clean_df.columns) == original_cols
        assert "timestamp" in waterpoint_clean_df.columns
        assert "_date" not in waterpoint_clean_df.columns

    def test_unrecognised_columns_passed_through(self):
        page = _import_page()
        df = pd.DataFrame({
            "timestamp":       pd.date_range("2024-01-01", periods=10),
            "flow_mld":        [22.0] * 10,
            "my_custom_param": [1.0] * 10,
        })
        adapted = page._adapt_columns(df)
        assert "my_custom_param" in adapted.columns

    def test_empty_dataframe_does_not_crash(self):
        page = _import_page()
        df = pd.DataFrame()
        adapted = page._adapt_columns(df)
        assert isinstance(adapted, pd.DataFrame)


class TestCandidateParameters:

    def test_prioritises_flow(self, waterpoint_clean_df):
        page = _import_page()
        adapted = page._adapt_columns(waterpoint_clean_df)
        candidates = page._candidate_condition_parameters(adapted)
        assert candidates[0] == "flow_mld"

    def test_date_column_excluded(self, waterpoint_clean_df):
        page = _import_page()
        adapted = page._adapt_columns(waterpoint_clean_df)
        candidates = page._candidate_condition_parameters(adapted)
        assert "_date" not in candidates


class TestPipelineEndToEnd:

    def test_orchestrator_runs_on_adapted_df(self, waterpoint_clean_df, tmp_path):
        page = _import_page()
        from core.characteriser.orchestrator import generate_envelope_artefact
        adapted = page._adapt_columns(waterpoint_clean_df)
        result = generate_envelope_artefact(
            df=adapted,
            condition_spec={"flow_mld": ">P75"},
            label="Page-15 integration smoke",
            output_directory=tmp_path / "envelope",
            concern="peak_hydraulic",
            dataset_filename="waterpoint_clean.csv",
        )
        assert result.success, (
            f"Pipeline failed: errors={result.errors}, warnings={result.warnings}"
        )
        assert result.markdown_path is not None
        assert Path(result.markdown_path).exists()
        for k in ["heatmap", "scatters", "timeseries", "overdesign"]:
            assert result.chart_paths.get(k) is not None, f"Missing chart {k}"

    def test_orchestrator_runs_with_bnr_concern(self, waterpoint_clean_df, tmp_path):
        page = _import_page()
        from core.characteriser.orchestrator import generate_envelope_artefact
        adapted = page._adapt_columns(waterpoint_clean_df)
        result = generate_envelope_artefact(
            df=adapted,
            condition_spec={"temperature_c": "<P25"},
            label="BNR integration smoke",
            output_directory=tmp_path / "envelope_bnr",
            concern="bnr_nitrification_stress",
        )
        assert result.success, f"BNR pipeline failed: {result.errors}"
        env = result.envelope
        priority = env.population.ratio_priority_map.get("bod_to_tkn", "")
        assert priority == "diagnostic", (
            f"BNR concern should mark bod_to_tkn diagnostic, got '{priority}'"
        )
