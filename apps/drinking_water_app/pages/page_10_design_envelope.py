"""
apps/drinking_water_app/pages/page_10_design_envelope.py

AquaPoint — Design Envelope
============================

Surfaces the core/characteriser/ design envelope engine for source water
characterisation. Mirrors the WaterPoint Design Envelope page (page_15)
structure exactly — four tabs (Setup, Envelope, Charts, About) — using
AQUAPOINT_CONCERNS instead of KNOWN_CONCERNS.

Data source: uploaded CSV/Excel source water dataset (AquaPoint does not
have a calibration page equivalent to WaterPoint's page_07; upload is the
primary data path).

Engineering boundaries respected (per orchestrator contract):
  - source-water evidence only; no treatment-process claims
  - no extrapolation beyond observed conditions
  - no prioritisation across envelopes; engineer reads memo and decides

Everything wraps in try/except per the platform's "fail gracefully" rule.

ph2o Consulting | Water Utility Planning Platform
"""
from __future__ import annotations

import io
import tempfile
import traceback
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

try:
    from core.characteriser.orchestrator import generate_envelope_artefact
    from apps.drinking_water_app.characteriser_config import AQUAPOINT_CONCERNS
    CHARACTERISER_AVAILABLE = True
except Exception as _e:
    CHARACTERISER_AVAILABLE = False
    _IMPORT_ERROR = str(_e)
    AQUAPOINT_CONCERNS = {}
    def generate_envelope_artefact(*a, **kw): pass


# ── Session state keys (namespaced "aq_env_") ──────────────────────────────

KEY_CONDITION_PARAM = "aq_env_condition_param"
KEY_CONDITION_OP    = "aq_env_condition_op"
KEY_CONDITION_VALUE = "aq_env_condition_value"
KEY_CONCERN         = "aq_env_concern"
KEY_LABEL           = "aq_env_label"
KEY_RESULT          = "aq_env_last_result"
KEY_OUTPUT_DIR      = "aq_env_output_dir"
KEY_DF              = "aq_env_df"


# ── Drop columns not useful for characterisation ───────────────────────────

_DROP_COLS = [
    "Source_Type", "Dominant_Algal_Group", "Antecedent_Wetness_Index",
    "Reservoir_Level_pct", "UV254_DOC_ratio", "Cyanobacteria_fraction",
    "Ca_Mg_molar_ratio", "Colour_DOC_ratio", "Turbidity_DOC_ratio",
    "Event_Label",
]


# ── Data helpers ───────────────────────────────────────────────────────────

def _coerce_lod(series: pd.Series) -> pd.Series:
    """Replace <LOD strings with half-LoD numeric value."""
    def _parse(v):
        if isinstance(v, str):
            v = v.strip()
            if v.startswith("<"):
                try:
                    return float(v[1:]) * 0.5
                except ValueError:
                    return np.nan
        try:
            return float(v)
        except (ValueError, TypeError):
            return np.nan
    return series.apply(_parse)


def _load_dataframe(uploaded_file) -> pd.DataFrame | None:
    """
    Parse an uploaded file into a clean dataframe.
    Returns None and surfaces errors via st.error on failure.
    """
    name = uploaded_file.name.lower()
    try:
        if name.endswith(".csv"):
            df = pd.read_csv(uploaded_file)
        elif name.endswith((".xlsx", ".xls")):
            df = pd.read_excel(uploaded_file)
        else:
            st.error(f"Unsupported format: {uploaded_file.name}. Use CSV or Excel.")
            return None
    except Exception as e:
        st.error(f"Could not read file: {e}")
        return None

    if df.empty:
        st.error("File contains no data rows.")
        return None

    # Detect date column
    date_col = next(
        (c for c in df.columns if "date" in c.lower() or c.lower() == "date"),
        None,
    )
    if date_col is None:
        st.error(
            "No date column detected. The file must contain a column named "
            "'Date', 'date', 'SampleDate', or similar."
        )
        return None

    df[date_col] = pd.to_datetime(df[date_col], dayfirst=True, errors="coerce")
    n_bad = df[date_col].isna().sum()
    if n_bad > 0:
        st.error(
            f"{n_bad} rows have unparseable dates in '{date_col}'. "
            "Ensure all dates are in a consistent format (YYYY-MM-DD or DD/MM/YYYY)."
        )
        return None

    df = df.rename(columns={date_col: "_date"})
    df = df.drop(columns=[c for c in _DROP_COLS if c in df.columns], errors="ignore")

    # Coerce <LOD string columns to numeric
    for col in df.columns:
        if df[col].dtype == object and col != "_date":
            df[col] = _coerce_lod(df[col])

    df = df.sort_values("_date").reset_index(drop=True)

    # Compute SUVA if UV254 and DOC are both present
    if (
        "UV254_cm_1" in df.columns
        and "DOC_mg_L" in df.columns
        and "SUVA" not in df.columns
    ):
        raw = (df["UV254_cm_1"] * 100.0) / df["DOC_mg_L"]
        df["SUVA"] = raw.replace([np.inf, -np.inf], np.nan)

    # Alias resolution
    try:
        from core.characteriser.alias_map import resolve_columns
        param_cols = [c for c in df.columns if c != "_date"]
        rename_map, _ = resolve_columns(param_cols)
        df = df.rename(columns=rename_map)
    except ImportError:
        pass  # alias_map not available — use columns as-is

    return df


def _candidate_condition_parameters(df: pd.DataFrame) -> list[str]:
    """
    Numeric columns the user can condition on.
    Prioritise parameters that have pre-built concern envelopes.
    """
    priority = [
        "Cyanobacteria_cells_mL", "Turbidity_NTU", "TrueColour_HU",
        "Hardness_mg_L_as_CaCO3", "Geosmin_ng_L", "Bromide_mg_L",
        "DOC_mg_L", "TOC_mg_L", "Flow_MLd", "Rainfall_mm",
        "Temperature_C", "EC_uS_cm", "E_coli_MPN_100mL",
        "Chlorophyll_a_ug_L", "Microcystin_LR_ug_L",
    ]
    available_priority = [c for c in priority if c in df.columns]
    other_numeric = sorted(
        c for c in df.columns
        if c not in priority
        and c != "_date"
        and pd.api.types.is_numeric_dtype(df[c])
    )
    return available_priority + other_numeric


# ── Tab renderers ──────────────────────────────────────────────────────────

def _render_setup_tab(df: pd.DataFrame) -> None:
    """Configure concern, condition, label — then run."""

    # ── Step 1: Concern ──────────────────────────────────────────────────
    st.subheader("Step 1 — Choose a source water concern")

    concern_options = [("(none — user-defined)", None)] + [
        (cfg["label"], key)
        for key, cfg in AQUAPOINT_CONCERNS.items()
    ]
    concern_labels = [label for label, _ in concern_options]

    current_concern = st.session_state.get(KEY_CONCERN)
    current_idx = next(
        (i for i, (_, k) in enumerate(concern_options) if k == current_concern),
        0,
    )
    selected_label = st.selectbox(
        "Source water concern",
        concern_labels,
        index=current_idx,
        help=(
            "Selects the framing of the envelope: which parameters are "
            "diagnostic vs informational. Choose (none) for a user-defined "
            "condition with no pre-set focus parameters."
        ),
    )
    selected_concern_key = next(
        k for label, k in concern_options if label == selected_label
    )
    st.session_state[KEY_CONCERN] = selected_concern_key

    # Show concern description if a pre-built one is selected
    if selected_concern_key and selected_concern_key in AQUAPOINT_CONCERNS:
        cfg = AQUAPOINT_CONCERNS[selected_concern_key]
        st.info(cfg["description"])
        # Pre-fill condition from concern spec
        cond_col = list(cfg["condition_spec"].keys())[0]
        cond_op_val = list(cfg["condition_spec"].values())[0]
        # Parse operator and value from e.g. ">2000" or ">P90"
        if cond_op_val.startswith(">="):
            default_op, default_val = ">=", cond_op_val[2:]
        elif cond_op_val.startswith(">"):
            default_op, default_val = ">", cond_op_val[1:]
        elif cond_op_val.startswith("<="):
            default_op, default_val = "<=", cond_op_val[2:]
        elif cond_op_val.startswith("<"):
            default_op, default_val = "<", cond_op_val[1:]
        else:
            default_op, default_val = ">", cond_op_val
    else:
        cond_col    = st.session_state.get(KEY_CONDITION_PARAM, "Turbidity_NTU")
        default_op  = st.session_state.get(KEY_CONDITION_OP, ">")
        default_val = st.session_state.get(KEY_CONDITION_VALUE, "P90")

    # ── Step 2: Condition ────────────────────────────────────────────────
    st.subheader("Step 2 — Define the condition")

    candidates = _candidate_condition_parameters(df)
    if not candidates:
        st.error("No numeric columns available to condition on.")
        return

    col_p, col_o, col_v = st.columns([2, 1, 2])

    with col_p:
        default_param_idx = (
            candidates.index(cond_col)
            if cond_col in candidates
            else 0
        )
        param = st.selectbox("Parameter", candidates, index=default_param_idx)
        st.session_state[KEY_CONDITION_PARAM] = param

    with col_o:
        op_options = [">", ">=", "<", "<="]
        default_op_idx = (
            op_options.index(default_op)
            if default_op in op_options else 0
        )
        op = st.selectbox("Operator", op_options, index=default_op_idx)
        st.session_state[KEY_CONDITION_OP] = op

    with col_v:
        value_str = st.text_input(
            "Threshold",
            value=default_val,
            help=(
                "Percentile (e.g. P90, P95, P99) or a numeric threshold "
                "(e.g. 2000 for cells/mL, 0.05 for bromide mg/L). "
                "Percentile adapts to the dataset's actual distribution."
            ),
        )
        st.session_state[KEY_CONDITION_VALUE] = value_str

    condition_spec = {param: f"{op}{value_str}"}
    st.caption(
        f"**Resolved condition:** `{param} {op}{value_str}` — "
        "the envelope will characterise source water conditions on rows "
        "where this is true."
    )

    # ── Step 3: Label and run ────────────────────────────────────────────
    st.subheader("Step 3 — Label and run")

    concern_label = (
        AQUAPOINT_CONCERNS[selected_concern_key]["label"]
        if selected_concern_key
        else "Design"
    )
    default_label = (
        st.session_state.get(KEY_LABEL)
        or f"{concern_label} envelope ({param} {op}{value_str})"
    )
    label = st.text_input(
        "Envelope label",
        value=default_label,
        help="Appears as the title of the rendered memo.",
    )
    st.session_state[KEY_LABEL] = label

    if st.button("🚀 Generate envelope", type="primary"):
        _run_envelope(df, condition_spec, label)


def _run_envelope(df: pd.DataFrame, condition_spec: dict, label: str) -> None:
    """Invoke the orchestrator and store result in session state."""
    output_dir = Path(tempfile.mkdtemp(prefix="aq_design_envelope_"))
    st.session_state[KEY_OUTPUT_DIR] = str(output_dir)

    with st.spinner("Building envelope, rendering charts, writing memo…"):
        try:
            result = generate_envelope_artefact(
                df=df,
                condition_spec=condition_spec,
                label=label,
                output_directory=output_dir,
                concern=st.session_state.get(KEY_CONCERN),
                dataset_filename=st.session_state.get("aq_env_filename", "source_water.csv"),
            )
        except Exception as exc:
            st.error(
                "Envelope generation raised an unexpected exception. "
                "This is an internal bug — the orchestrator should capture "
                "all failures in its result object."
            )
            st.exception(exc)
            return

    st.session_state[KEY_RESULT] = result

    if result.success:
        st.success("Envelope generated. See the **Envelope** and **Charts** tabs.")
    else:
        st.error("Envelope generation failed. See the **Envelope** tab for details.")


def _render_result_tab() -> None:
    """Show success/failure, warnings, and the rendered markdown memo."""
    result = st.session_state.get(KEY_RESULT)
    if result is None:
        st.info(
            "No envelope has been generated yet. "
            "Use the **Setup** tab to configure and run."
        )
        return

    for w in (result.warnings or []):
        st.warning(w)

    if not result.success:
        st.error("Envelope did not complete successfully.")
        for e in (result.errors or []):
            st.markdown(f"- {e}")
        return

    if result.markdown_path:
        md_path = Path(result.markdown_path)
        if md_path.exists():
            md_text = md_path.read_text(encoding="utf-8")
            cleaned = _clean_markdown_for_inline(md_text)
            st.markdown(cleaned, unsafe_allow_html=False)
            st.caption(
                "Figures referenced above are rendered in the **Charts** tab "
                "and embedded by file path in the downloaded memo."
            )
            st.download_button(
                "📥 Download envelope.md",
                data=md_text,
                file_name="aq_envelope.md",
                mime="text/markdown",
            )
        else:
            st.warning(f"Markdown file not found at {md_path}.")


def _clean_markdown_for_inline(md_text: str) -> str:
    """
    Adapt memo for inline Streamlit rendering:
      - Drop H1 (page already has a title)
      - Drop image references (shown in Charts tab)
      - Drop horizontal rules (visual noise in Streamlit)
    """
    lines = md_text.split("\n")
    out: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not out and stripped.startswith("# "):
            continue
        if stripped.startswith("![") and "](" in stripped:
            continue
        if stripped == "---":
            continue
        out.append(line)
    return "\n".join(out)


def _render_charts_tab() -> None:
    """Render the four PNG charts from the envelope result."""
    result = st.session_state.get(KEY_RESULT)
    if result is None or not result.success:
        st.info(
            "Charts appear here after a successful envelope generation. "
            "Use the **Setup** tab to run."
        )
        return

    chart_info = [
        (
            "heatmap",
            "Figure 2.1 — Correlation heatmap",
            "Spearman correlation matrix. Coefficients labelled where |ρ| ≥ 0.6. "
            "Structural relationships (e.g. UV254↔UVT) are hatched; "
            "derived-via-structural relationships are diagonally hatched; "
            "grey cells indicate insufficient paired observations.",
        ),
        (
            "scatters",
            "Figure 2.2 — Pairwise scatters",
            "Parameter pairs with |ρ| ≥ 0.6. Matched-subset points highlighted "
            "in red. Pairs marked 'expected coupling' are physically or "
            "chemically expected relationships.",
        ),
        (
            "timeseries",
            "Figure 3.1 — Focus parameters over time",
            "Full record of focus parameters with detected events shaded by type. "
            "Strong-confidence events are labelled at the top.",
        ),
        (
            "overdesign",
            "Figure 4.1 — Over-design margin",
            "Naive independent-P95 minus observed joint-conditional median, "
            "per parameter. Positive = naive stacking over-designs; "
            "negative = naive stacking under-designs for that parameter.",
        ),
    ]

    for key, title, caption in chart_info:
        chart_path = (result.chart_paths or {}).get(key)
        if not chart_path:
            continue
        full_path = Path(chart_path)
        if not full_path.is_absolute() and hasattr(result, "output_directory") and result.output_directory:
            full_path = Path(result.output_directory) / full_path.name
        if not full_path.exists():
            st.caption(f"({title} — file not found)")
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

A **design envelope memo** for one named source water concern against one
condition. The memo has six sections:

1. **Framing** — what is being characterised, on what data, for what reason.
2. **Observed envelope (population-level)** — conditional medians,
   percentiles, and shifts vs the full-record statistics for every focus
   parameter.
3. **Observed events (event-level)** — discrete episodes within the matched
   subset (storm events, bloom escalations, high-colour periods).
4. **Over-design comparison** — naive independent-P95 stacking vs the observed
   joint conditional median, parameter by parameter.
5. **Integrity check on the matched subset** — which integrity flags affect
   rows inside the matched subset, and the effect on each table.
6. **Limits of this envelope** — period covered, what is under-represented,
   what this envelope does NOT address.

### Engineering boundaries (built into the engine)

- **Source-water evidence only.** No treatment-process claims and no
  engineering recommendations.
- **No statistical extrapolation.** All numbers come from observations in
  the uploaded dataset — no fitted distributions, no return-period estimates
  beyond the record length.
- **No prioritisation across envelopes.** Multiple concerns may produce
  different envelopes; which governs design is engineering judgement.

### Pre-built source water concerns

| Concern | Condition | Focus |
|---|---|---|
| Algal bloom risk | Cyanobacteria >2,000 cells/mL | Cell counts, toxins, T&O |
| High turbidity event | Turbidity >P90 | Turbidity, SS, rainfall, Fe/Mn |
| Colour/TOC event | True Colour >P80 | DOC, TOC, UV254, SUVA, bromide |
| Hardness/scaling | Hardness >200 mg/L CaCO₃ | Hardness, alkalinity, EC, TDS |
| Taste & odour | Geosmin >4 ng/L | Geosmin, MIB, cyanobacteria, temperature |
| DBP precursor | Bromide >0.05 mg/L | Bromide, DOC, TOC, UV254, pH |

> **Scope statement:** This page characterises the observed source water
> record. It does not recommend a treatment process, establish a design
> basis, or constitute engineering advice. Treatment selection and process
> design require site-specific assessment by a qualified practitioner.
"""
    )


# ── Main entry point ───────────────────────────────────────────────────────

def render() -> None:
    """Streamlit entry point. Wrapped in try/except per platform rule."""
    try:
        _render_inner()
    except Exception as exc:
        st.error("The Design Envelope page encountered an internal error.")
        st.exception(exc)
        st.caption(
            "Please report this with the traceback above. "
            "The error has been captured here so the rest of the app continues."
        )


def _render_inner() -> None:
    st.title("📐 Design Envelope")
    st.markdown(
        "*Evidence-grounded source water characterisation memo for a named "
        "concern under a specified condition.*"
    )
    st.divider()

    # ── Data source ──────────────────────────────────────────────────────
    # AquaPoint doesn't have a calibration page — upload is the primary path.
    # Cache the loaded df in session state so switching tabs doesn't re-parse.

    df = st.session_state.get(KEY_DF)

    with st.expander(
        "📂 Source water dataset"
        + (" (loaded ✓)" if df is not None else " — upload required"),
        expanded=(df is None),
    ):
        uploaded = st.file_uploader(
            "Upload CSV or Excel source water dataset",
            type=["csv", "xlsx", "xls"],
            key="de_upload",
            label_visibility="collapsed",
        )
        if uploaded is not None:
            loaded = _load_dataframe(uploaded)
            if loaded is not None:
                st.session_state[KEY_DF] = loaded
                st.session_state["aq_env_filename"] = uploaded.name
                df = loaded
                # Clear any prior result when a new file is uploaded
                st.session_state.pop(KEY_RESULT, None)

    if df is None:
        st.warning(
            "Upload a source water dataset above to begin. "
            "Accepted formats: CSV (.csv) or Excel (.xlsx / .xls)."
        )
        _render_about_tab()
        return

    # Dataset summary strip
    n_rows = len(df)
    if "_date" in df.columns and df["_date"].notna().any():
        date_min = df["_date"].min().strftime("%Y-%m-%d")
        date_max = df["_date"].max().strftime("%Y-%m-%d")
        record_months = (df["_date"].max() - df["_date"].min()).days / 30.44
        st.caption(
            f"Dataset: **{n_rows:,} rows** | "
            f"{date_min} → {date_max} | "
            f"{record_months:.1f} months | "
            f"{len([c for c in df.columns if c != '_date'])} parameters"
        )

    # ── Tabs ─────────────────────────────────────────────────────────────
    tab_setup, tab_envelope, tab_charts, tab_about = st.tabs(
        ["⚙️ Setup", "📄 Envelope", "📊 Charts", "ℹ️ About"]
    )

    with tab_setup:
        _render_setup_tab(df)

    with tab_envelope:
        _render_result_tab()

    with tab_charts:
        _render_charts_tab()

    with tab_about:
        _render_about_tab()
