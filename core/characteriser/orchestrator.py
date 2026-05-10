"""
core/characteriser/orchestrator.py

Top-level orchestrator integration for the design envelope engine.

This module provides the ONE function that downstream callers (WaterPoint UI,
test harness, batch scripts) use to produce a complete design envelope
artefact: envelope object + 4 PNG charts + markdown memo.

Why this exists separately from build_design_envelope
-----------------------------------------------------
build_design_envelope (in design_envelope.py) is the PURE orchestrator. It
takes a cleaned dataframe + condition + optional report and returns a
DesignEnvelope object. It writes no files; charts paths remain None.

This module wires together the three pure-but-side-effectful steps:
    build_design_envelope(...)           → DesignEnvelope (pure)
    render_envelope_charts(...)          → writes 4 PNGs, mutates envelope
    render_envelope_markdown(...)        → writes envelope.md

It also adds:
  - input validation (rejects malformed inputs with clear errors before
    they reach the deeper layers, where errors are harder to diagnose)
  - structured error handling (no UI-breaking unhandled exceptions; every
    failure mode produces a useful EnvelopeBuildResult)
  - a one-call API: `generate_envelope_artefact(...)`

This is the function the Streamlit UI should call. It is also the function
that batch scripts producing a multi-concern dashboard view should call
once per concern.
"""
from __future__ import annotations

import logging
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Union

import pandas as pd

from .design_envelope import build_design_envelope
from .envelope_charts import render_envelope_charts
from .envelope_renderer import render_envelope_markdown
from .report import (
    CharacterisationReport, DesignEnvelope, EventAnalysis,
)


logger = logging.getLogger(__name__)


# ── Pre-built concern catalogue ─────────────────────────────────────────────
#
# The six concerns Phase 5 ships with. The catalogue is exposed here so the
# UI layer (Streamlit) can populate a dropdown without importing the
# orchestrator's internals.

KNOWN_CONCERNS = {
    "peak_hydraulic":          "Peak hydraulic conditions",
    "bnr_nitrification_stress": "BNR / nitrification stress",
    "p_removal_stress":        "P-removal stress",
    "septicity":               "Septicity exposure",
    "biodegradability":        "Biodegradability / carbon limitation",
    "first_flush_solids":      "First-flush solids mobilisation",
}


# ── Result type ─────────────────────────────────────────────────────────────

@dataclass
class EnvelopeBuildResult:
    """
    Outcome of a generate_envelope_artefact call.

    success=True means: envelope object built, charts written, markdown
    written. The caller can present markdown_path and chart_paths to the user.

    success=False means: something went wrong; envelope may still be partly
    populated (e.g. Section 1 framing built before a later section failed).
    The caller should display `errors` to the user, not raise.

    `warnings` is for non-fatal conditions worth surfacing — e.g. "events
    were filtered to zero by concern relevance", "dataset has < 1 complete
    year", "matched subset is Insufficient". These are not errors; they
    are information the engineer should see.
    """
    success: bool
    envelope: Optional[DesignEnvelope] = None
    output_directory: Optional[str] = None
    markdown_path: Optional[str] = None
    chart_paths: Dict[str, Optional[str]] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


# ── Input validation ────────────────────────────────────────────────────────

def _validate_inputs(df: pd.DataFrame,
                     condition_spec: Dict,
                     label: str,
                     concern: Optional[str],
                     output_directory: Union[str, Path]) -> List[str]:
    """
    Validate caller inputs. Returns list of error strings; empty list means
    inputs are acceptable.

    Validation philosophy
    ---------------------
    Reject the obvious mistakes the UI shouldn't even allow but might.
    Don't try to be clever — if the user wants to point a condition at a
    column that contains only NaN, that's a downstream concern (the
    coincidence layer will return Insufficient confidence).

    The point here is to fail FAST and CLEARLY when the call shape is
    wrong, rather than letting an unhandled exception bubble up from a
    deep layer.
    """
    errors: List[str] = []

    # df
    if df is None:
        errors.append("df is None — pass a cleaned pandas DataFrame.")
        return errors  # nothing else makes sense to check

    if not isinstance(df, pd.DataFrame):
        errors.append(f"df must be a pandas DataFrame, got {type(df).__name__}.")
        return errors

    if len(df) == 0:
        errors.append("df is empty — cannot characterise an envelope.")
        return errors

    # condition_spec
    if not isinstance(condition_spec, dict):
        errors.append(
            f"condition_spec must be a dict, got {type(condition_spec).__name__}."
        )
    elif not condition_spec:
        errors.append("condition_spec is empty — provide at least one condition.")
    else:
        for col, expr in condition_spec.items():
            if not isinstance(col, str):
                errors.append(
                    f"condition_spec keys must be column names (str); got {col!r}."
                )
                continue
            if col not in df.columns:
                errors.append(
                    f"condition_spec references column '{col}' which is not in "
                    f"df.columns (available: {list(df.columns)[:10]}...)."
                )
            elif not pd.api.types.is_numeric_dtype(df[col]) and not isinstance(expr, bool):
                # boolean expressions on a boolean column are fine; numeric
                # expressions on a non-numeric column are not
                errors.append(
                    f"condition_spec column '{col}' must be numeric "
                    f"for non-boolean expressions, got {df[col].dtype}."
                )

    # label
    if not isinstance(label, str) or not label.strip():
        errors.append("label must be a non-empty string.")

    # concern (None is fine for user-defined)
    if concern is not None and not isinstance(concern, str):
        errors.append(f"concern must be a string or None, got {type(concern).__name__}.")

    # output_directory
    if not isinstance(output_directory, (str, Path)):
        errors.append(
            f"output_directory must be a str or Path, got {type(output_directory).__name__}."
        )

    return errors


# ── Public entry point ──────────────────────────────────────────────────────

def generate_envelope_artefact(
    df: pd.DataFrame,
    condition_spec: Dict[str, Union[str, bool, int, float]],
    label: str,
    output_directory: Union[str, Path],
    concern: Optional[str] = None,
    focus_parameters: Optional[List[str]] = None,
    report: Optional[CharacterisationReport] = None,
    event_analysis: Optional[EventAnalysis] = None,
    dataset_filename: str = "",
    correlation_threshold: float = 0.6,
) -> EnvelopeBuildResult:
    """
    Produce a complete design envelope artefact at output_directory.

    On success, the directory will contain:
      envelope.md
      figure_2_1_heatmap.png
      figure_2_2_scatters.png
      figure_3_1_timeseries.png
      figure_4_1_overdesign.png

    Parameters
    ----------
    df : DataFrame
        Cleaned engineering dataset. Must contain a '_date' column for full
        functionality; missing date is tolerated but limits Section 3 (events)
        and Section 1 (period coverage).
    condition_spec : dict
        Condition in coincidence-engine format. E.g. {"flow_mld": ">P95"}.
    label : str
        Free-text label for the envelope (appears as title in the markdown).
    output_directory : str or Path
        Directory to write the envelope.md and chart PNGs into. Created if
        missing.
    concern : str, optional
        One of KNOWN_CONCERNS or a user-defined string. Drives ratio
        prioritisation (Section 2 Addition B) and event-type filtering
        (Section 3). None = user-defined / no prioritisation.
    focus_parameters : list of str, optional
        Parameters to include in the envelope. None = default focus list
        filtered to what's present in df.
    report : CharacterisationReport, optional
        Required for Section 5 (integrity flags filtered to subset) and
        Addition C (integrity-aware secondary medians in Section 2).
    event_analysis : EventAnalysis, optional
        Required for Section 3 (event-level detail) and Addition D
        (repeatability indicators).
    dataset_filename : str, optional
        Source filename for Section 1 framing. Cosmetic only.
    correlation_threshold : float, optional
        Threshold for Figure 2.1 / 2.2 (|ρ| ≥ threshold). Defaults to 0.6.

    Returns
    -------
    EnvelopeBuildResult — see class docstring. Caller should check `.success`
    and present `.errors`/`.warnings`/`.markdown_path` accordingly. This
    function NEVER raises in normal operation; all expected failure modes
    are captured in the result.
    """
    result = EnvelopeBuildResult(success=False)

    # Stage 1: validate inputs
    input_errors = _validate_inputs(df, condition_spec, label, concern, output_directory)
    if input_errors:
        result.errors.extend(input_errors)
        logger.warning("Input validation rejected envelope build: %s", input_errors)
        return result

    # Unknown but well-formed concern → warn but continue (user-defined fallback)
    if concern is not None and concern not in KNOWN_CONCERNS:
        result.warnings.append(
            f"Concern '{concern}' is not one of the pre-built concerns "
            f"({sorted(KNOWN_CONCERNS.keys())}); ratio prioritisation will "
            "fall back to alphabetical."
        )

    if "_date" not in df.columns:
        result.warnings.append(
            "df has no '_date' column; Section 1 period coverage and "
            "Section 3 event filtering will be limited."
        )

    # Stage 2: build envelope object (pure)
    try:
        envelope = build_design_envelope(
            df=df,
            condition_spec=condition_spec,
            label=label,
            focus_parameters=focus_parameters,
            concern=concern,
            report=report,
            event_analysis=event_analysis,
            dataset_filename=dataset_filename,
        )
        result.envelope = envelope
    except Exception as exc:
        msg = f"build_design_envelope raised: {type(exc).__name__}: {exc}"
        logger.exception(msg)
        result.errors.append(msg)
        result.errors.append(traceback.format_exc(limit=10))
        return result

    # Warn on Insufficient (the user should know)
    if envelope.population.sample_confidence == "Insufficient":
        result.warnings.append(
            f"The matched subset has only {envelope.population.n_matching} "
            f"observation(s) (need ≥10). Sections 2–4 will be collapsed in "
            "the rendered memo. Consider broadening the condition or "
            "collecting more data."
        )

    # Stage 3: render charts (mutates envelope)
    out_dir = Path(output_directory)
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        result.errors.append(
            f"Could not create output directory '{out_dir}': {exc}"
        )
        return result

    try:
        render_envelope_charts(df, envelope, str(out_dir),
                               threshold=correlation_threshold)
        result.chart_paths = {
            "heatmap":        envelope.population.heatmap_path,
            "scatters":       envelope.population.scatters_path,
            "timeseries":     envelope.events.time_series_path,
            "overdesign":     envelope.over_design.over_design_chart_path,
        }
    except Exception as exc:
        msg = f"render_envelope_charts raised: {type(exc).__name__}: {exc}"
        logger.exception(msg)
        result.errors.append(msg)
        # Continue — the markdown is still valuable without charts

    # Stage 4: render markdown
    md_path = out_dir / "envelope.md"
    try:
        render_envelope_markdown(envelope, str(md_path))
        result.markdown_path = str(md_path.resolve())
    except Exception as exc:
        msg = f"render_envelope_markdown raised: {type(exc).__name__}: {exc}"
        logger.exception(msg)
        result.errors.append(msg)
        return result

    result.output_directory = str(out_dir.resolve())
    result.success = True
    return result


# ── Convenience: multi-concern dashboard helper ─────────────────────────────

def generate_concern_dashboard(
    df: pd.DataFrame,
    condition_spec: Dict[str, Union[str, bool, int, float]],
    output_directory_root: Union[str, Path],
    concerns: Optional[List[str]] = None,
    report: Optional[CharacterisationReport] = None,
    event_analysis: Optional[EventAnalysis] = None,
    dataset_filename: str = "",
) -> Dict[str, EnvelopeBuildResult]:
    """
    Build envelope artefacts for multiple concerns against the same condition.

    This is the dashboard-view caller — the WaterPoint UI's "show me all
    concerns side-by-side" entry point. Each concern's envelope is written
    to a subdirectory `<output_directory_root>/<concern>/`.

    Returns a dict mapping concern → EnvelopeBuildResult. The caller can
    inspect which envelopes succeeded and present them accordingly.
    """
    if concerns is None:
        concerns = list(KNOWN_CONCERNS.keys())

    root = Path(output_directory_root)
    results: Dict[str, EnvelopeBuildResult] = {}

    for concern in concerns:
        concern_dir = root / concern
        concern_label = KNOWN_CONCERNS.get(concern, concern)
        label = f"{concern_label} — condition: {next(iter(condition_spec.items()))}"

        results[concern] = generate_envelope_artefact(
            df=df,
            condition_spec=condition_spec,
            label=label,
            output_directory=concern_dir,
            concern=concern,
            report=report,
            event_analysis=event_analysis,
            dataset_filename=dataset_filename,
        )

    return results
