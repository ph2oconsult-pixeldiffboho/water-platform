"""
tests/test_orchestrator.py

Tests for the top-level orchestrator (core/characteriser/orchestrator.py).
The orchestrator wraps build_design_envelope + chart rendering + markdown
rendering into one call with structured error handling.

These tests cover:
  - happy path: clean inputs produce success=True with all artefacts
  - input validation: malformed inputs return success=False with clear errors
  - failure modes: nothing raises, everything returns a populated result
  - multi-concern dashboard helper
"""
from __future__ import annotations
import pandas as pd
import pytest

from core.characteriser.orchestrator import (
    generate_envelope_artefact,
    generate_concern_dashboard,
    KNOWN_CONCERNS,
    EnvelopeBuildResult,
)


class TestHappyPath:

    def test_clean_inputs_produce_full_artefact(self, clean_df, tmp_path):
        result = generate_envelope_artefact(
            df=clean_df,
            condition_spec={"flow_mld": ">P75"},
            label="Happy path test",
            output_directory=tmp_path / "envelope",
            concern="peak_hydraulic",
            dataset_filename="test.csv",
        )

        assert result.success is True
        assert result.errors == []
        assert result.envelope is not None
        assert result.markdown_path is not None
        assert (tmp_path / "envelope" / "envelope.md").exists()
        # All four chart paths populated
        for k in ["heatmap", "scatters", "timeseries", "overdesign"]:
            assert result.chart_paths.get(k) is not None, f"Missing chart: {k}"

    def test_warnings_on_unknown_concern(self, clean_df, tmp_path):
        result = generate_envelope_artefact(
            df=clean_df,
            condition_spec={"flow_mld": ">P75"},
            label="Unknown concern test",
            output_directory=tmp_path / "envelope",
            concern="my_custom_concern",
        )
        assert result.success is True
        # Warned about the unknown concern
        assert any("not one of the pre-built" in w for w in result.warnings)

    def test_warnings_on_insufficient_subset(self, clean_df, tmp_path):
        result = generate_envelope_artefact(
            df=clean_df,
            condition_spec={"flow_mld": ">P99.7"},  # ~1 match
            label="Insufficient test",
            output_directory=tmp_path / "envelope",
        )
        # Still succeeds (renders Section 1 + scope notice + Section 6)
        assert result.success is True
        assert any("Insufficient" in w or "matched subset" in w
                   for w in result.warnings)


class TestInputValidation:

    def test_rejects_none_df(self, tmp_path):
        result = generate_envelope_artefact(
            df=None,
            condition_spec={"flow_mld": ">P75"},
            label="Test",
            output_directory=tmp_path,
        )
        assert result.success is False
        assert any("df is None" in e for e in result.errors)
        assert result.envelope is None

    def test_rejects_non_dataframe(self, tmp_path):
        result = generate_envelope_artefact(
            df=[1, 2, 3],
            condition_spec={"flow_mld": ">P75"},
            label="Test",
            output_directory=tmp_path,
        )
        assert result.success is False
        assert any("DataFrame" in e for e in result.errors)

    def test_rejects_empty_dataframe(self, tmp_path):
        result = generate_envelope_artefact(
            df=pd.DataFrame(),
            condition_spec={"flow_mld": ">P75"},
            label="Test",
            output_directory=tmp_path,
        )
        assert result.success is False
        assert any("empty" in e for e in result.errors)

    def test_rejects_empty_condition(self, clean_df, tmp_path):
        result = generate_envelope_artefact(
            df=clean_df,
            condition_spec={},
            label="Test",
            output_directory=tmp_path,
        )
        assert result.success is False
        assert any("condition_spec is empty" in e for e in result.errors)

    def test_rejects_condition_on_missing_column(self, clean_df, tmp_path):
        result = generate_envelope_artefact(
            df=clean_df,
            condition_spec={"nonexistent_column": ">P75"},
            label="Test",
            output_directory=tmp_path,
        )
        assert result.success is False
        assert any("nonexistent_column" in e and "not in" in e
                   for e in result.errors)

    def test_rejects_empty_label(self, clean_df, tmp_path):
        result = generate_envelope_artefact(
            df=clean_df,
            condition_spec={"flow_mld": ">P75"},
            label="",
            output_directory=tmp_path,
        )
        assert result.success is False
        assert any("label" in e.lower() for e in result.errors)

    def test_rejects_non_numeric_condition_column(self, tmp_path):
        df = pd.DataFrame({
            "_date": pd.date_range("2023-01-01", periods=50),
            "flow_mld": range(50),
            "site_name": ["A"] * 50,  # string column
        })
        result = generate_envelope_artefact(
            df=df,
            condition_spec={"site_name": ">P75"},
            label="Test",
            output_directory=tmp_path,
        )
        assert result.success is False
        assert any("numeric" in e.lower() for e in result.errors)


class TestKnownConcernsCatalogue:

    def test_six_concerns_in_catalogue(self):
        """Documented concerns count from the README."""
        assert len(KNOWN_CONCERNS) == 6

    def test_all_documented_concerns_present(self):
        for c in ["peak_hydraulic", "bnr_nitrification_stress",
                  "p_removal_stress", "septicity",
                  "biodegradability", "first_flush_solids"]:
            assert c in KNOWN_CONCERNS


class TestDashboardHelper:

    def test_runs_all_known_concerns_by_default(self, clean_df, tmp_path):
        results = generate_concern_dashboard(
            df=clean_df,
            condition_spec={"flow_mld": ">P75"},
            output_directory_root=tmp_path / "dashboard",
        )
        assert set(results.keys()) == set(KNOWN_CONCERNS.keys())
        for concern, result in results.items():
            assert result.success is True, (
                f"Concern {concern} failed: {result.errors}"
            )
            # Each concern has its own subdir
            assert (tmp_path / "dashboard" / concern / "envelope.md").exists()

    def test_can_select_subset_of_concerns(self, clean_df, tmp_path):
        results = generate_concern_dashboard(
            df=clean_df,
            condition_spec={"flow_mld": ">P75"},
            output_directory_root=tmp_path / "dashboard",
            concerns=["peak_hydraulic", "septicity"],
        )
        assert set(results.keys()) == {"peak_hydraulic", "septicity"}


class TestErrorHandling:

    def test_never_raises_on_bad_inputs(self, tmp_path):
        """The orchestrator must never raise — even pathological inputs."""
        bad_inputs_list = [
            dict(df=None, condition_spec={}, label=""),
            dict(df=pd.DataFrame(), condition_spec={}, label=""),
            dict(df="not a dataframe", condition_spec=None, label=None),
            dict(df=pd.DataFrame({"a": [1]}), condition_spec="nope", label=123),
        ]
        for bad in bad_inputs_list:
            # Should not raise — should return failure result
            result = generate_envelope_artefact(
                output_directory=tmp_path / "shouldnotbecreated",
                **bad,
            )
            assert isinstance(result, EnvelopeBuildResult)
            assert result.success is False
            assert len(result.errors) > 0

    def test_output_directory_created(self, clean_df, tmp_path):
        deep_path = tmp_path / "deep" / "nested" / "path" / "envelope"
        result = generate_envelope_artefact(
            df=clean_df,
            condition_spec={"flow_mld": ">P75"},
            label="Deep path test",
            output_directory=deep_path,
        )
        assert result.success is True
        assert deep_path.exists()
