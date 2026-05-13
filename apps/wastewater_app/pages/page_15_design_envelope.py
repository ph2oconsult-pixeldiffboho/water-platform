"""
apps/wastewater_app/pages/page_15_design_envelope.py

Design Envelope page — Phase 5 / item 4 of the deployment-readiness checklist.

Surfaces the core/characteriser/ design envelope engine to the user. Reads the
cleaned plant dataset produced by page_07_calibration (no separate upload),
adapts column conventions, runs build_design_envelope + chart + markdown
rendering via the orchestrator, and displays the resulting six-section memo
plus four PNG charts.

Engineering boundaries respected (per Phase 5 README and the orchestrator):
  - influent-side evidence only; no process-consequence claims
  - no extrapolation beyond observed conditions
  - no prioritisation across envelopes; engineer reads memo and decides

Everything wraps in try/except per the platform's "fail gracefully" rule.
"""
from __future__ import annotations
import io
import sys
import tempfile
import traceback
from pathlib import Path

import pandas as pd
import streamlit as st

from apps.ui.session_state import require_project, get_current_project
from apps.ui.ui_components import render_page_header
from core.characteriser.orchestrator import (
    generate_envelope_artefact, KNOWN_CONCERNS,
)


# Session state keys (namespaced "env_" to avoid collisions)
KEY_CONDITION_PARAM = "env_condition_param"
KEY_CONDITION_OP    = "env_condition_op"
KEY_CONDITION_VALUE = "env_condition_value"
KEY_CONCERN         = "env_concern"
KEY_LABEL           = "env_label"
KEY_RESULT          = "env_last_result"
KEY_OUTPUT_DIR      = "env_output_dir"


# ── Column adapter ──────────────────────────────────────────────────────────
#
# WaterPoint's cleaner uses `timestamp` + `influent_<param>_mg_l` conventions.
# Phase 5 uses `_date` + `<param>_mg_l`. The two are aliases of the same
# physical measurements; this adapter renames in place on a copy.
#
# Anything not recognised is left as-is — Phase 5's focus-parameter list will
# simply skip columns it doesn't know about.

_WP_TO_ENVELOPE = {
    "timestamp":            "_date",
    "influent_bod_mg_l":    "bod_mg_l",
    "influent_cod_mg_l":    "cod_mg_l",
    "influent_tss_mg_l":    "tss_mg_l",
    "influent_nh4_mg_l":    "nh4_mg_l",
    "influent_tkn_mg_l":    "tkn_mg_l",
    "influent_tp_mg_l":     "tp_mg_l",
    "basin_temp_celsius":   "temperature_c",
    # Effluent and process columns are left as-is — the envelope engine
    # is influent-side only; effluent columns will be passed through but
    # ignored by the default focus list.
}


def _adapt_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Rename WaterPoint columns to envelope-engine conventions."""
    renamed = df.rename(columns=_WP_TO_ENVELOPE).copy()

    # Phase 5 expects `_date` to be a datetime column
    if "_date" in renamed.columns:
        renamed["_date"] = pd.to_datetime(renamed["_date"], errors="coerce")

    # Add derived load columns if both concentration and flow are present
    # (the envelope engine treats them as separate focus parameters)
    if "flow_mld" in renamed.columns:
        for conc in ("bod", "cod", "tss", "tkn", "nh4", "tp"):
            col_c = f"{conc}_mg_l"
            col_l = f"{conc}_load_kg_d"
            if col_c in renamed.columns and col_l not in renamed.columns:
                renamed[col_l] = renamed[col_c] * renamed["flow_mld"]

    # Add common ratio columns
    if "nh4_mg_l" in renamed.columns and "tkn_mg_l" in renamed.columns:
        renamed["nh4_to_tkn"] = renamed["nh4_mg_l"] / renamed["tkn_mg_l"]
    if "cod_mg_l" in renamed.columns and "bod_mg_l" in renamed.columns:
        renamed["cod_to_bod"] = renamed["cod_mg_l"] / renamed["bod_mg_l"]
    if "bod_mg_l" in renamed.columns and "tkn_mg_l" in renamed.columns:
        renamed["bod_to_tkn"] = renamed["bod_mg_l"] / renamed["tkn_mg_l"]
    if "tp_mg_l" in renamed.columns and "cod_mg_l" in renamed.columns:
        renamed["tp_to_cod"] = renamed["tp_mg_l"] / renamed["cod_mg_l"]

    return renamed


def _candidate_condition_parameters(df: pd.DataFrame) -> list:
    """Numeric columns the user can condition on. Prioritise the obvious ones."""
    priority = [
        "flow_mld", "bod_mg_l", "cod_mg_l", "tss_mg_l",
        "tkn_mg_l", "nh4_mg_l", "tp_mg_l", "temperature_c",
        "bod_load_kg_d", "cod_load_kg_d", "tss_load_kg_d",
    ]
    available_priority = [c for c in priority if c in df.columns]
    other_numeric = [c for c in df.columns
                     if c not in priority
                     and c != "_date"
                     and pd.api.types.is_numeric_dtype(df[c])]
    return available_priority + sorted(other_numeric)


# ── Tab renderers ───────────────────────────────────────────────────────────

def _render_setup_tab(df: pd.DataFrame) -> None:
    """The form: pick a concern, build a condition, hit Run."""
    st.subheader("Step 1 — Choose a design concern")

    concern_options = [("(none — user-defined)", None)] + [
        (label, key) for key, label in KNOWN_CONCERNS.items()
    ]
    concern_labels = [label for label, _ in concern_options]

    current_concern = st.session_state.get(KEY_CONCERN)
    current_idx = next(
        (i for i, (_, k) in enumerate(concern_options) if k == current_concern),
        0,
    )
    selected_label = st.selectbox(
        "Design concern",
        concern_labels,
        index=current_idx,
        help=(
            "Picks the framing of the envelope: which ratios are diagnostic "
            "vs informational, which event types are surfaced. Choose "
            "(none) to apply no priority (ratios listed alphabetically)."
        ),
    )
    st.session_state[KEY_CONCERN] = next(
        k for label, k in concern_options if label == selected_label
    )

    st.subheader("Step 2 — Define the condition")

    candidates = _candidate_condition_parameters(df)
    if not candidates:
        st.error(
            "The cleaned dataset has no numeric columns to condition on. "
            "Check the data quality output on Plant Data & Calibration."
        )
        return

    col_p, col_o, col_v = st.columns([2, 1, 2])

    with col_p:
        default_param_idx = (
            candidates.index(st.session_state.get(KEY_CONDITION_PARAM, "flow_mld"))
            if st.session_state.get(KEY_CONDITION_PARAM) in candidates
            else 0
        )
        param = st.selectbox(
            "Parameter",
            candidates,
            index=default_param_idx,
        )
        st.session_state[KEY_CONDITION_PARAM] = param

    with col_o:
        op_options = [">", ">=", "<", "<="]
        default_op_idx = (
            op_options.index(st.session_state.get(KEY_CONDITION_OP, ">"))
            if st.session_state.get(KEY_CONDITION_OP) in op_options
            else 0
        )
        op = st.selectbox("Operator", op_options, index=default_op_idx)
        st.session_state[KEY_CONDITION_OP] = op

    with col_v:
        value_str = st.text_input(
            "Threshold",
            value=st.session_state.get(KEY_CONDITION_VALUE, "P95"),
            help=(
                "Percentile (e.g. P95, P99, P75) or a numeric threshold. "
                "Percentile is more common for design envelopes — it adapts "
                "to whatever the dataset's distribution actually is."
            ),
        )
        st.session_state[KEY_CONDITION_VALUE] = value_str

    condition_spec = {param: f"{op}{value_str}"}
    st.caption(
        f"**Resolved condition:** `{param} {op}{value_str}` — "
        "the envelope will describe what else is happening on rows where this is true."
    )

    st.subheader("Step 3 — Label and run")
    default_label = (
        st.session_state.get(KEY_LABEL)
        or f"{KNOWN_CONCERNS.get(st.session_state.get(KEY_CONCERN), 'Design')} envelope "
           f"({param} {op}{value_str})"
    )
    label = st.text_input(
        "Envelope label",
        value=default_label,
        help="Free text — appears as the H1 title of the rendered memo.",
    )
    st.session_state[KEY_LABEL] = label

    if st.button("🚀 Generate envelope", type="primary"):
        _run_envelope(df, condition_spec, label)


def _run_envelope(df: pd.DataFrame, condition_spec: dict, label: str) -> None:
    """Invoke the orchestrator and store the result in session state."""
    output_dir = Path(tempfile.mkdtemp(prefix="design_envelope_"))
    st.session_state[KEY_OUTPUT_DIR] = str(output_dir)

    with st.spinner("Building envelope, rendering charts, writing memo..."):
        try:
            result = generate_envelope_artefact(
                df=df,
                condition_spec=condition_spec,
                label=label,
                output_directory=output_dir,
                concern=st.session_state.get(KEY_CONCERN),
                dataset_filename="cleaned_plant_data.csv",
            )
        except Exception as exc:
            # Defensive: the orchestrator should never raise, but if a future
            # change regresses that, surface the failure here.
            st.error(
                "Envelope generation raised an exception. This is an internal "
                "bug — the orchestrator is supposed to capture all failures "
                "in its result object."
            )
            st.exception(exc)
            return

    st.session_state[KEY_RESULT] = result

    if result.success:
        st.success(
            f"Envelope generated in {output_dir}. "
            "See the **Envelope** and **Charts** tabs above."
        )
    else:
        st.error("Envelope generation failed. See the **Result** tab for details.")


def _render_result_tab() -> None:
    """Show success/failure, warnings, errors, and the markdown memo."""
    result = st.session_state.get(KEY_RESULT)
    if result is None:
        st.info(
            "No envelope has been generated yet. Use the **Setup** tab to "
            "configure and run."
        )
        return

    # Warnings
    if result.warnings:
        for w in result.warnings:
            st.warning(w)

    # Errors
    if not result.success:
        st.error("Envelope did not complete successfully.")
        for e in result.errors:
            st.markdown(f"- {e}")
        return

    # Success — render the markdown memo inline
    if result.markdown_path:
        md_path = Path(result.markdown_path)
        if md_path.exists():
            md_text = md_path.read_text(encoding="utf-8")
            cleaned = _clean_markdown_for_inline(md_text)
            st.markdown(cleaned, unsafe_allow_html=False)

            st.caption(
                "Note — figures referenced in the memo above are rendered "
                "in the **Charts** tab. They are also embedded by file path "
                "in the downloaded `envelope.md` (for offline viewing)."
            )

            # Download button — give the FULL markdown including image refs
            # and HRs, so an offline reader gets the proper memo structure.
            st.download_button(
                "📥 Download envelope.md",
                data=md_text,
                file_name="envelope.md",
                mime="text/markdown",
            )
        else:
            st.warning(f"Markdown file not found at {md_path}.")


def _clean_markdown_for_inline(md_text: str) -> str:
    """
    Adapt a memo for inline Streamlit rendering:

      - Drop the H1 (the page already has a title).
      - Drop image references — st.markdown cannot serve local files, so
        those render as broken-image icons. The Charts tab shows them
        properly via st.image. The downloaded .md keeps them.
      - Drop horizontal-rule lines ('---') that render as visible hairlines
        but interrupt the visual flow of Streamlit's section spacing.
    """
    lines = md_text.split("\n")
    out: list[str] = []
    for line in lines:
        stripped = line.strip()
        # Drop H1
        if not out and stripped.startswith("# "):
            continue
        # Drop image references — they're shown in Charts tab
        if stripped.startswith("![") and "](" in stripped:
            continue
        # Drop horizontal rules
        if stripped == "---":
            continue
        out.append(line)
    return "\n".join(out)


def _render_charts_tab() -> None:
    """Show the four PNG figures with caption explanations."""
    result = st.session_state.get(KEY_RESULT)
    if result is None or not result.success:
        st.info(
            "Charts appear here after a successful envelope generation. "
            "Use the **Setup** tab to run."
        )
        return

    chart_info = [
        ("heatmap",
         "Figure 2.1 — Correlation heatmap",
         "Spearman correlation matrix. Coefficients are labelled only where "
         "|ρ| ≥ 0.6 to reduce clutter."),
        ("scatters",
         "Figure 2.2 — Pairwise scatters",
         "Pairs of parameters with |ρ| ≥ 0.6. Matched-subset points are "
         "highlighted in red. Pairs marked 'expected coupling' are "
         "definitional relationships (e.g. BOD vs COD)."),
        ("timeseries",
         "Figure 3.1 — Focus parameters over time",
         "Full record of focus parameters with detected events shaded by "
         "type. Only Strong-confidence events carry top-of-chart labels."),
        ("overdesign",
         "Figure 4.1 — Over-design margin",
         "Naive independent-P95 minus observed joint median, per parameter. "
         "Positive (green) means naive stacking over-designs; negative (red) "
         "means it under-designs. The condition specified in Section 1 is the "
         "governing event."),
    ]

    for key, title, caption in chart_info:
        chart_path = result.chart_paths.get(key)
        if not chart_path:
            continue
        full_path = Path(chart_path)
        if not full_path.is_absolute() and result.output_directory:
            full_path = Path(result.output_directory) / full_path.name
        if not full_path.exists():
            st.caption(f"({title} — file not found at {full_path})")
            continue
        st.markdown(f"**{title}**")
        st.image(str(full_path), use_container_width=True)
        st.caption(caption)
        st.divider()


def _render_about_tab() -> None:
    """Engineering-facing explanation of what this page does and doesn't do."""
    st.markdown(
        """
### What this page produces

A **design envelope memo** for one named design concern against one
condition. The memo has six sections:

1. **Framing** — what is being characterised, on what data, for what reason.
2. **Observed envelope (population-level)** — conditional medians,
   percentiles, and shifts vs the catchment-wide statistics for every
   focus parameter. With integrity-aware secondary medians when applicable.
3. **Observed events (event-level)** — discrete episodes within the
   matched subset, when an event analysis is available.
4. **Over-design comparison** — naive independent-P95 stacking vs the
   observed joint median, parameter by parameter.
5. **Integrity check on the matched subset** — which INT-class flags
   (if any) affect rows inside the matched subset, and the effect on each
   table.
6. **Limits of this envelope** — period covered, what's under-represented,
   what this envelope does NOT address.

### Engineering boundaries (built into the engine)

- **Influent-side evidence only.** No process-consequence claims (e.g.
  "this stresses clarifiers first") and no plant-side recommendations.
- **No statistical extrapolation.** All numbers come from observations
  in the data as-loaded — no fitted distributions, no return-period
  estimates beyond the record length.
- **No prioritisation across envelopes.** Multiple concerns may produce
  different envelopes; which one should dominate design is engineering
  judgement, not an engine output. Event repeatability is labelled as
  evidence of recurrence, not as a ranking of importance.

### Where the data comes from

This page can use either the cleaned dataset from **Plant Data &
Calibration** (preferred — gives you KPIs and benchmarking too) or a
direct CSV upload on this page. If neither is loaded yet, the **Setup**
tab will guide you.

### How concerns differ

The six pre-built concerns shape two things:

| Concern | Diagnostic-primary ratios | Event types surfaced |
|---|---|---|
| Peak hydraulic | (none — loads vs concentrations is the story) | All |
| BNR / nitrification stress | alk/TKN, BOD/TKN, NH4/TKN | Low-carbon nitrification stress |
| P-removal stress | TP/COD | TP-rich coincident |
| Septicity | rbCOD/sCOD, sCOD/COD | Septic episode |
| Biodegradability | COD/BOD, rbCOD/COD | (no specific type) |
| First-flush solids | VSS/TSS | First-flush |

User-defined concerns (the "(none)" option) get alphabetical ratio
ordering and no event-type filtering — Section 3 will surface every
event type found in the matched subset.

### Status

The first user-visible deployment of Phase 5 — items 1 (unit tests),
2 (orchestrator integration), and now 4 (this page). Items 3 (input
validation layer), 5 (performance check on real data), 6 (end-user
docs), and 7 (deployment artefacts) remain.
"""
    )


# ── Main entry point ────────────────────────────────────────────────────────

def render() -> None:
    """Streamlit entry point. Wrapped in try/except per platform rule."""
    try:
        _render_inner()
    except Exception as exc:
        st.error("The Design Envelope page encountered an internal error.")
        st.exception(exc)
        st.caption(
            "Please report this with the traceback above. The error has been "
            "captured here so the rest of the app continues to work."
        )


def _render_inner() -> None:
    render_page_header(
        "15 Design Envelope",
        "Evidence-grounded design memo for a named design concern under a "
        "specified condition.",
    )
    require_project()

    # Try to load a cleaned dataframe. None means no data yet — we still
    # render the page, just with the data-dependent tabs showing prompts
    # instead of forms. The About tab is always reachable, so a first-time
    # visitor can read what the page does before being asked to upload.
    df_envelope = None
    df = _load_dataframe()
    if df is not None:
        df_envelope = _adapt_columns(df)
        # Small summary caption only when data is loaded
        n_rows = len(df_envelope)
        if "_date" in df_envelope.columns and df_envelope["_date"].notna().any():
            date_min = df_envelope["_date"].min().strftime("%Y-%m-%d")
            date_max = df_envelope["_date"].max().strftime("%Y-%m-%d")
            st.caption(
                f"📊 Dataset: **{n_rows} rows**, "
                f"period **{date_min} → {date_max}**."
            )
        else:
            st.caption(f"📊 Dataset: **{n_rows} rows**.")

    # Tabs — always render all four. About is reachable without data.
    tab_setup, tab_result, tab_charts, tab_about = st.tabs([
        "🛠️ Setup", "📋 Envelope", "📊 Charts", "ℹ️ About",
    ])

    with tab_setup:
        if df_envelope is not None:
            _render_setup_tab(df_envelope)
        else:
            st.info(
                "Load a dataset (banner above) to configure and generate an "
                "envelope. See the **About** tab for what this page does."
            )
    with tab_result:
        _render_result_tab()
    with tab_charts:
        _render_charts_tab()
    with tab_about:
        _render_about_tab()


def _load_dataframe():
    """
    Try to load a cleaned plant dataframe. Three paths, in priority order:
      1. cached clean_result, if present
      2. a CSV the user uploads on this page
      3. nothing — show an info banner and return None
    """
    # Path 1: cached session state
    clean_result = st.session_state.get("cal_clean_result")
    if clean_result is not None and getattr(clean_result, "df", None) is not None:
        df = clean_result.df
        if df is not None and len(df) > 0:
            st.success(
                "Using the cleaned dataset from **Plant Data & Calibration**. "
                "(Upload a different file below to override.)"
            )
            uploaded = st.file_uploader(
                "Override with a different file (CSV or Excel, optional)",
                type=["csv", "xlsx", "xls"],
                key="env_override_uploader",
            )
            if uploaded:
                return _read_uploaded_csv(uploaded)
            return df

    # Path 2: direct upload
    st.info(
        "📋 No cleaned dataset is loaded. Either:\n\n"
        "1. Go to **Plant Data & Calibration**, upload your CSV there, "
        "run the cleaner, and return to this page (recommended — you also "
        "get KPI and benchmarking analysis there), OR\n"
        "2. Upload a CSV or Excel file directly here for envelope analysis only."
    )
    uploaded = st.file_uploader(
        "Upload plant data (CSV or Excel)",
        type=["csv", "xlsx", "xls"],
        key="env_direct_uploader",
        help=(
            "Columns: timestamp (required), flow_mld, influent_<param>_mg_l "
            "for BOD/COD/TSS/TKN/NH4/TP, basin_temp_celsius. Common column "
            "aliases are accepted; see Plant Data & Calibration for the full spec."
        ),
    )
    if uploaded:
        return _read_uploaded_csv(uploaded)
    return None


def _read_uploaded_csv(uploaded_file):
    """Try to use the platform's cleaner for CSV; on any failure, fall back
    to a plain pandas read. Excel files go straight to pd.read_excel and
    bypass PlantDataCleaner (which only handles text/CSV input)."""
    filename = (uploaded_file.name or "").lower()
    is_excel = filename.endswith(".xlsx") or filename.endswith(".xls")

    if is_excel:
        try:
            uploaded_file.seek(0)
            df = pd.read_excel(uploaded_file)
            return df
        except Exception as exc:
            st.error(f"Could not read Excel file: {exc}")
            return None

    try:
        from core.data_ingestion.data_cleaning import PlantDataCleaner
        cleaner = PlantDataCleaner()
        text = uploaded_file.read().decode("utf-8", errors="replace")
        result = cleaner.clean(text, target_interval="daily")
        if result.df is not None and len(result.df) > 0:
            return result.df
        st.warning(
            "PlantDataCleaner produced no rows. Showing raw CSV instead — "
            "review the data quality issues on Plant Data & Calibration for diagnostics."
        )
    except Exception as exc:
        st.warning(
            f"PlantDataCleaner failed ({exc}). Falling back to plain CSV read."
        )

    try:
        uploaded_file.seek(0)
        df = pd.read_csv(uploaded_file)
        return df
    except Exception as exc:
        st.error(f"Could not read CSV: {exc}")
        return None
