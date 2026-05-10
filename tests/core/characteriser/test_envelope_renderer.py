"""
tests/test_envelope_renderer.py

Tests for the markdown renderer. We check structural elements (section
headers, mandatory phrases) rather than exact wording, so cosmetic changes
don't break tests; what matters is that the produced markdown carries the
right information.
"""
from __future__ import annotations
import pytest

from core.characteriser.design_envelope import build_design_envelope
from core.characteriser.envelope_renderer import render_envelope_markdown
from core.characteriser.report import (
    Event, EventAnalysis,
)


# Helpers ────────────────────────────────────────────────────────────────────

def _read(path) -> str:
    return path.read_text(encoding="utf-8")


def _build_event(eid, etype, start, end, conf="Strong"):
    import pandas as pd
    return Event(
        event_id=eid, event_type=etype,
        start_date=start, end_date=end,
        duration_days=(pd.Timestamp(end) - pd.Timestamp(start)).days + 1,
        confidence=conf,
        confidence_rationale="test",
        detection_rule="test rule",
    )


# ── Six-section structure ───────────────────────────────────────────────────

class TestSixSections:

    def test_all_six_headers_present(self, clean_df, tmp_path):
        env = build_design_envelope(
            df=clean_df, condition_spec={"flow_mld": ">P75"}, label="Test envelope"
        )
        out = tmp_path / "envelope.md"
        render_envelope_markdown(env, str(out))
        md = _read(out)

        for header in [
            "## 1. Framing",
            "## 2. Observed envelope (population-level)",
            "## 3. Observed events (event-level)",
            "## 4. Over-design comparison",
            "## 5. Integrity check on the matched subset",
            "## 6. Limits of this envelope",
        ]:
            assert header in md, f"Missing section header: {header!r}"

    def test_label_appears_as_title(self, clean_df, tmp_path):
        env = build_design_envelope(
            df=clean_df, condition_spec={"flow_mld": ">P75"},
            label="My distinctive label string",
        )
        out = tmp_path / "envelope.md"
        render_envelope_markdown(env, str(out))
        md = _read(out)
        assert "My distinctive label string" in md
        # H1 with the label
        assert "# Design envelope:" in md


# ── Addition A: aggregation-scope disclaimer ────────────────────────────────

class TestAdditionADisclaimer:

    def test_disclaimer_renders_in_section_2(self, clean_df, tmp_path):
        env = build_design_envelope(
            df=clean_df, condition_spec={"flow_mld": ">P75"}, label="Test"
        )
        out = tmp_path / "envelope.md"
        render_envelope_markdown(env, str(out))
        md = _read(out)
        # The disclaimer is rendered as a blockquote
        assert "Aggregation-scope note" in md
        # Renderer uses '> ' blockquote prefix for the disclaimer body
        assert "> " in md.split("## 2.")[1].split("## 3.")[0]


# ── Addition B: ratio prioritisation rendered ───────────────────────────────

class TestAdditionBRendering:

    def test_diagnostic_ratios_bolded(self, clean_df, tmp_path):
        env = build_design_envelope(
            df=clean_df, condition_spec={"flow_mld": ">P75"},
            label="Test", concern="bnr_nitrification_stress",
        )
        out = tmp_path / "envelope.md"
        render_envelope_markdown(env, str(out))
        md = _read(out)
        # Diagnostic ratios should be marked **diagnostic** in the table
        assert "**diagnostic**" in md

    def test_priority_note_rendered(self, clean_df, tmp_path):
        env = build_design_envelope(
            df=clean_df, condition_spec={"flow_mld": ">P75"},
            label="Test", concern="bnr_nitrification_stress",
        )
        out = tmp_path / "envelope.md"
        render_envelope_markdown(env, str(out))
        md = _read(out)
        # Some text explaining diagnostic-primary vs informational-secondary
        assert "diagnostic" in md.lower()


# ── Addition C: integrity-aware secondary medians rendered ──────────────────

class TestAdditionCRendering:

    def test_extra_column_when_integrity_active(self, dirty_df, characterisation_report_factory, tmp_path):
        """When integrity_exclusions is non-empty, the concentration table
        should include the 'Cond. median (excl. flagged)' column."""
        report = characterisation_report_factory(dirty_df)
        env = build_design_envelope(
            df=dirty_df,
            condition_spec={"flow_mld": ">0"},  # everything
            label="Test", report=report,
        )
        assert env.population.integrity_exclusion_active is True

        out = tmp_path / "envelope.md"
        render_envelope_markdown(env, str(out))
        md = _read(out)
        # The extra column header
        assert "Cond. median (excl. flagged)" in md
        # The 'n−X' suffix should appear with the exclusion count
        assert "n−" in md or "n-" in md

    def test_extra_column_absent_when_clean(self, clean_df, tmp_path):
        env = build_design_envelope(
            df=clean_df, condition_spec={"flow_mld": ">P75"}, label="Test"
        )
        out = tmp_path / "envelope.md"
        render_envelope_markdown(env, str(out))
        md = _read(out)
        # The extra column should not appear when integrity is clean
        assert "Cond. median (excl. flagged)" not in md


# ── Addition D: repeatability indicators rendered ───────────────────────────

class TestAdditionDRendering:

    def test_repeatability_caveat_present(self, clean_df, tmp_path):
        """The renderer must explicitly mark repeatability as
        'evidence-of-recurrence, not a ranking of importance'."""
        ea = EventAnalysis(events=[
            _build_event("E1", "First-flush", "2023-06-01", "2023-12-31"),
            _build_event("E2", "First-flush", "2024-06-01", "2024-06-05"),
        ])
        env = build_design_envelope(
            df=clean_df,
            condition_spec={"flow_mld": ">P25"},
            label="Test", event_analysis=ea,
        )
        out = tmp_path / "envelope.md"
        render_envelope_markdown(env, str(out))
        md = _read(out)
        # Must include the caveat
        assert "evidence-of-recurrence" in md.lower()
        assert "not a ranking" in md.lower()

    def test_repeatability_column_in_inventory(self, clean_df, tmp_path):
        ea = EventAnalysis(events=[
            _build_event("E1", "First-flush", "2023-06-01", "2023-12-31"),
        ])
        env = build_design_envelope(
            df=clean_df, condition_spec={"flow_mld": ">P25"},
            label="Test", event_analysis=ea,
        )
        out = tmp_path / "envelope.md"
        render_envelope_markdown(env, str(out))
        md = _read(out)
        # Event inventory table should have a Repeatability column
        assert "Repeatability" in md


# ── No-events handling ──────────────────────────────────────────────────────

class TestNoEvents:

    def test_no_events_note_rendered(self, clean_df, tmp_path):
        env = build_design_envelope(
            df=clean_df, condition_spec={"flow_mld": ">P95"},
            label="Test", event_analysis=None,
        )
        out = tmp_path / "envelope.md"
        render_envelope_markdown(env, str(out))
        md = _read(out)
        # Section 3 should not be empty even with no events
        section_3 = md.split("## 3.")[1].split("## 4.")[0]
        assert section_3.strip() != ""


# ── Insufficient confidence collapses Section 2 ─────────────────────────────

class TestInsufficient:

    def test_insufficient_envelope_renders_without_crash(self, clean_df, tmp_path):
        env = build_design_envelope(
            df=clean_df,
            condition_spec={"flow_mld": ">P99.7"},  # ~1 match
            label="Test",
        )
        assert env.population.sample_confidence == "Insufficient"

        out = tmp_path / "envelope.md"
        render_envelope_markdown(env, str(out))
        md = _read(out)

        # Section 2 should explicitly say "Not characterisable" or similar
        section_2 = md.split("## 2.")[1].split("## 3.")[0]
        assert ("not characterisable" in section_2.lower()
                or "insufficient" in section_2.lower())


# ── Numeric formatting ──────────────────────────────────────────────────────

class TestNumericFormatting:

    def test_no_raw_python_object_strings(self, clean_df, tmp_path):
        """The markdown must not contain 'None', '<' on raw objects, etc."""
        env = build_design_envelope(
            df=clean_df, condition_spec={"flow_mld": ">P75"}, label="Test"
        )
        out = tmp_path / "envelope.md"
        render_envelope_markdown(env, str(out))
        md = _read(out)

        # Common bad signs of unconverted Python objects
        assert "ConditionalParameterStat(" not in md
        assert "<dataclass" not in md
        # 'None' alone in a table cell looks bad; we render '—' instead
        # (Section 6 may legitimately use 'None' in prose, so we don't ban it
        # globally.)
        section_2 = md.split("## 2.")[1].split("## 3.")[0]
        # Inside a table row '| None |' would be a bug
        assert "| None |" not in section_2

    def test_percentage_signs_present(self, clean_df, tmp_path):
        """The matching percentage should be rendered with % sign."""
        env = build_design_envelope(
            df=clean_df, condition_spec={"flow_mld": ">P75"}, label="Test"
        )
        out = tmp_path / "envelope.md"
        render_envelope_markdown(env, str(out))
        md = _read(out)
        assert "%" in md


# ── File system ─────────────────────────────────────────────────────────────

class TestFileSystemBehaviour:

    def test_returns_absolute_path(self, clean_df, tmp_path):
        env = build_design_envelope(
            df=clean_df, condition_spec={"flow_mld": ">P75"}, label="Test"
        )
        out = tmp_path / "envelope.md"
        result = render_envelope_markdown(env, str(out))
        import os
        assert os.path.isabs(result)

    def test_creates_parent_directory_if_missing(self, clean_df, tmp_path):
        env = build_design_envelope(
            df=clean_df, condition_spec={"flow_mld": ">P75"}, label="Test"
        )
        out = tmp_path / "newdir" / "subdir" / "envelope.md"
        render_envelope_markdown(env, str(out))
        assert out.exists()
