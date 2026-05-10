"""
tests/test_end_to_end.py

Full pipeline tests: orchestrator → charts → markdown rendering, against
both a clean dataset and a dirty dataset (with integrity violations).

These tests are the closest analogue in the test suite to a user running
the engine on a real dataset. They confirm that the modules cooperate
correctly and the produced artefacts are coherent.
"""
from __future__ import annotations
import pandas as pd
import pytest

from core.characteriser.design_envelope import build_design_envelope
from core.characteriser.envelope_charts import render_envelope_charts
from core.characteriser.envelope_renderer import render_envelope_markdown
from core.characteriser.report import Event, EventAnalysis


def _make_event(eid, etype, start, end, conf="Strong"):
    return Event(
        event_id=eid, event_type=etype,
        start_date=start, end_date=end,
        duration_days=(pd.Timestamp(end) - pd.Timestamp(start)).days + 1,
        confidence=conf,
        confidence_rationale="end-to-end test event",
        detection_rule="end-to-end test rule",
    )


class TestCleanDatasetEndToEnd:
    """Full pipeline on a clean synthetic dataset with simulated events."""

    def test_full_pipeline_clean(self, clean_df, characterisation_report_factory, tmp_path):
        report = characterisation_report_factory(clean_df)
        ea = EventAnalysis(events=[
            _make_event("E001", "First-flush", "2023-03-15", "2023-03-18"),
            _make_event("E002", "First-flush", "2023-09-10", "2023-09-12"),
            _make_event("E003", "Low-carbon nitrification stress",
                        "2023-08-22", "2023-08-25"),
        ])

        # Build envelope
        envelope = build_design_envelope(
            df=clean_df,
            condition_spec={"flow_mld": ">P75"},
            label="Peak hydraulic — end-to-end clean test",
            concern="peak_hydraulic",
            report=report,
            event_analysis=ea,
            dataset_filename="clean.csv",
        )

        # Render charts and markdown
        out_dir = tmp_path / "clean_envelope"
        render_envelope_charts(clean_df, envelope, str(out_dir))
        render_envelope_markdown(envelope, str(out_dir / "envelope.md"))

        # All artefacts exist
        artefacts = [
            "envelope.md",
            "figure_2_1_heatmap.png",
            "figure_2_2_scatters.png",
            "figure_3_1_timeseries.png",
            "figure_4_1_overdesign.png",
        ]
        for fname in artefacts:
            f = out_dir / fname
            assert f.exists(), f"Missing artefact: {fname}"
            assert f.stat().st_size > 100, f"Suspiciously small artefact: {fname}"

        # Spot-check markdown content
        md = (out_dir / "envelope.md").read_text(encoding="utf-8")
        assert "Peak hydraulic" in md
        assert "## 1. Framing" in md
        assert "## 6. Limits" in md

        # Section 5 should be clean (no INT flags on clean fixture)
        assert envelope.integrity.is_clean is True


class TestDirtyDatasetEndToEnd:
    """Full pipeline on a dirty dataset (10 integrity flags) — verify the
    integrity-aware features kick in."""

    def test_full_pipeline_dirty(self, dirty_df, characterisation_report_factory, tmp_path):
        report = characterisation_report_factory(dirty_df)
        assert len(report.flags) > 0, "Dirty fixture must produce flags"

        envelope = build_design_envelope(
            df=dirty_df,
            condition_spec={"flow_mld": ">P25"},  # broad subset so flags land inside
            label="Stress test — end-to-end dirty",
            concern="peak_hydraulic",
            report=report,
            event_analysis=None,
            dataset_filename="dirty.csv",
        )

        out_dir = tmp_path / "dirty_envelope"
        render_envelope_charts(dirty_df, envelope, str(out_dir))
        render_envelope_markdown(envelope, str(out_dir / "envelope.md"))

        # Section 5: not clean
        assert envelope.integrity.is_clean is False
        assert len(envelope.integrity.flags_affecting_subset) > 0

        # Section 2: integrity-aware secondary medians active
        assert envelope.population.integrity_exclusion_active is True

        md = (out_dir / "envelope.md").read_text(encoding="utf-8")
        # The extra column should be rendered in the concentration table
        assert "Cond. median (excl. flagged)" in md
        # Section 5 should list the affected flags
        section_5 = md.split("## 5.")[1].split("## 6.")[0]
        assert "INT-" in section_5


class TestConcernDifferentiation:
    """Same dataset run against different concerns should produce different
    envelopes (different ratio priorities, different event filtering)."""

    def test_envelopes_differ_by_concern(self, clean_df, tmp_path):
        ea = EventAnalysis(events=[
            _make_event("E_FF", "First-flush", "2023-06-01", "2023-12-31"),
            _make_event("E_SEPTIC", "Septic episode", "2023-06-01", "2023-12-31"),
            _make_event("E_BNR", "Low-carbon nitrification stress",
                        "2023-06-01", "2023-12-31"),
        ])

        envs = {}
        for concern in ["peak_hydraulic", "bnr_nitrification_stress",
                        "septicity", "first_flush_solids"]:
            envs[concern] = build_design_envelope(
                df=clean_df,
                condition_spec={"flow_mld": ">P25"},
                label=f"{concern} test",
                concern=concern,
                event_analysis=ea,
            )

        # Ratio priority differs
        bod_to_tkn_priorities = {
            c: envs[c].population.ratio_priority_map.get("bod_to_tkn", "")
            for c in envs
        }
        assert bod_to_tkn_priorities["bnr_nitrification_stress"] == "diagnostic"
        assert bod_to_tkn_priorities["peak_hydraulic"] == "informational"

        # Event filtering differs by concern's relevant event types
        for concern, env in envs.items():
            event_types = {e.event_type for e in env.events.events}
            if concern == "septicity":
                # Only septic events should survive
                assert event_types <= {"Septic episode"}
            elif concern == "first_flush_solids":
                # Only first-flush events
                assert event_types <= {"First-flush"}
            elif concern == "bnr_nitrification_stress":
                assert event_types <= {"Low-carbon nitrification stress"}


class TestPerformance:
    """Smoke check that the full pipeline runs in under a few seconds even
    on a 3-year dataset. Not a strict performance test — just a check that
    no accidental O(n^2) algorithms have been introduced."""

    def test_3_year_dataset_completes_quickly(self, tmp_path):
        import time
        import numpy as np

        # Build a 3-year synthetic dataset (~1100 rows)
        rng = np.random.default_rng(123)
        n = 1095
        dates = pd.date_range("2023-01-01", periods=n, freq="D")
        flow = 22.0 + rng.gamma(0.5, 2.0, n) + 1.5 * np.sin(2 * np.pi * np.arange(n) / 365.25)
        df = pd.DataFrame({
            "_date":         dates,
            "flow_mld":      flow,
            "bod_mg_l":      240 - 4.0 * (flow - 22.0) + rng.normal(0, 18, n),
            "cod_mg_l":      540 + rng.normal(0, 50, n),
            "tss_mg_l":      255 + rng.normal(0, 25, n),
            "tkn_mg_l":      45 + rng.normal(0, 2.5, n),
            "nh4_mg_l":      31.5 + rng.normal(0, 1.5, n),
            "tp_mg_l":       7.5 + rng.normal(0, 0.5, n),
            "temperature_c": 18 + 6 * np.sin(2 * np.pi * np.arange(n) / 365.25),
            "rainfall_mm":   np.clip(rng.gamma(0.5, 1.0, n), 0, None),
        })
        for c in ["bod", "cod", "tss", "tkn", "nh4", "tp"]:
            df[f"{c}_load_kg_d"] = df[f"{c}_mg_l"] * df["flow_mld"]

        start = time.perf_counter()
        envelope = build_design_envelope(
            df=df,
            condition_spec={"flow_mld": ">P95"},
            label="Performance test",
            concern="peak_hydraulic",
        )
        render_envelope_charts(df, envelope, str(tmp_path / "perf"))
        render_envelope_markdown(envelope, str(tmp_path / "perf" / "envelope.md"))
        elapsed = time.perf_counter() - start

        # 1095 rows × 4 charts shouldn't take more than 10 seconds even on
        # slow CI. Generous bound; tighten if it ever creeps up.
        assert elapsed < 10.0, (
            f"3-year pipeline took {elapsed:.2f}s — investigate before merging"
        )
