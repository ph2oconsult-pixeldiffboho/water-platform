"""
apps/biosolids_app/pages/page_00_load_data.py
BioPoint V1 — Load Data from CSV or Excel.

Accepts CSV or .xlsx upload, maps column names flexibly to BioPoint
session state inputs, previews the mapping, and applies on confirmation.
"""
import streamlit as st
import pandas as pd
import io


# ---------------------------------------------------------------------------
# FLEXIBLE COLUMN MAP
# Each bp_ key maps to a list of accepted column name variants (case-insensitive)
# ---------------------------------------------------------------------------

COLUMN_MAP = {
    # Feedstock
    "bp_ds_tpd": [
        "dry_solids", "ds_tpd", "tds_day", "tds/day", "dry solids",
        "dry solids (tds/day)", "dry_solids_tpd", "solids_tpd",
    ],
    "bp_feed_ds_pct": [
        "feed_ds", "ds_pct", "ds%", "feed ds%", "dewatered_ds",
        "dewatered ds%", "feed_ds_pct", "solids concentration",
        "ds_percent", "ds percent", "feed solids",
    ],
    "bp_vs_pct": [
        "vs", "vs_pct", "volatile_solids", "volatile solids",
        "volatile solids (%)", "vs%", "vs_percent",
    ],
    "bp_gcv": [
        "gcv", "calorific_value", "calorific value", "gross_calorific_value",
        "gcv (mj/kgds)", "gcv_mj_kgds", "heating_value", "energy content",
    ],
    "bp_sludge_type": [
        "sludge_type", "sludge type", "sludge", "type",
        "feedstock_type", "feedstock type",
    ],
    "bp_variability": [
        "variability", "feed_variability", "feed variability",
        "variation", "consistency",
    ],
    "bp_pfas": [
        "pfas", "pfas_status", "pfas status", "pfas_present",
        "pfas present",
    ],
    # Economics
    "bp_disposal": [
        "disposal_cost", "disposal cost", "disposal", "disposal ($/tds)",
        "tipping_fee", "tipping fee", "gate_fee",
    ],
    "bp_electricity": [
        "electricity", "electricity_price", "electricity price",
        "power_price", "power price", "elec_price",
        "electricity ($/kwh)", "power ($/kwh)",
    ],
    "bp_fuel": [
        "fuel", "fuel_price", "fuel price", "fuel ($/gj)",
        "gas_price", "gas price", "natural_gas",
    ],
    "bp_transport": [
        "transport", "transport_cost", "transport cost",
        "haulage", "haulage_cost", "transport ($/t.km)",
        "transport_rate",
    ],
    "bp_avg_km": [
        "distance", "avg_km", "average_distance", "average distance",
        "transport_distance", "transport distance", "haul_distance",
        "avg transport distance", "km",
    ],
    "bp_carbon_price": [
        "carbon_price", "carbon price", "carbon", "co2_price",
        "carbon credit", "carbon_credit", "co2e_price",
        "carbon ($/tco2e)",
    ],
    "bp_disposal_cost": [  # alias
        "disposal_cost_per_tds",
    ],
    # Site
    "bp_waste_heat": [
        "waste_heat", "waste heat", "waste_heat_kwh", "waste heat (kwh/day)",
        "available_heat", "recovered_heat",
    ],
    # Strategy
    "bp_priority": [
        "priority", "optimisation_priority", "optimisation priority",
        "objective", "strategy",
    ],
    "bp_reg": [
        "regulatory_pressure", "regulatory pressure", "regulation",
        "regulatory", "reg_pressure",
    ],
    "bp_land": [
        "land_constraint", "land constraint", "land", "land availability",
    ],
    "bp_social": [
        "social_licence", "social licence", "community_sensitivity",
        "community sensitivity", "social",
    ],
    "bp_biochar_mkt": [
        "biochar_market", "biochar market", "biochar_confidence",
        "biochar market confidence", "biochar",
    ],
}

# Human-readable labels for display
KEY_LABELS = {
    "bp_ds_tpd":      "Dry solids (tDS/day)",
    "bp_feed_ds_pct": "Feed DS%",
    "bp_vs_pct":      "Volatile solids (%)",
    "bp_gcv":         "GCV (MJ/kgDS)",
    "bp_sludge_type": "Sludge type",
    "bp_variability": "Feed variability",
    "bp_pfas":        "PFAS status",
    "bp_disposal":    "Disposal cost ($/tDS)",
    "bp_electricity": "Electricity ($/kWh)",
    "bp_fuel":        "Fuel price ($/GJ)",
    "bp_transport":   "Transport ($/t·km)",
    "bp_avg_km":      "Avg transport distance (km)",
    "bp_carbon_price":"Carbon price ($/tCO₂e)",
    "bp_waste_heat":  "Waste heat (kWh/day)",
    "bp_priority":    "Optimisation priority",
    "bp_reg":         "Regulatory pressure",
    "bp_land":        "Land constraint",
    "bp_social":      "Social licence pressure",
    "bp_biochar_mkt": "Biochar market confidence",
}

# Numeric keys (will be cast to float)
NUMERIC_KEYS = {
    "bp_ds_tpd", "bp_feed_ds_pct", "bp_vs_pct", "bp_gcv",
    "bp_disposal", "bp_electricity", "bp_fuel", "bp_transport",
    "bp_avg_km", "bp_carbon_price", "bp_waste_heat",
}

# Valid options for categorical fields
CATEGORICAL_VALID = {
    "bp_sludge_type": ["blended", "digested", "primary", "secondary", "thp_digested"],
    "bp_variability": ["low", "moderate", "high"],
    "bp_pfas":        ["unknown", "negative", "confirmed"],
    "bp_priority":    ["balanced", "highest_resilience", "cost_minimisation", "carbon_optimised"],
    "bp_reg":         ["low", "moderate", "high"],
    "bp_land":        ["low", "moderate", "high"],
    "bp_social":      ["low", "moderate", "high"],
    "bp_biochar_mkt": ["low", "moderate", "high"],
}


# ---------------------------------------------------------------------------
# MAPPING LOGIC
# ---------------------------------------------------------------------------

def normalise(s: str) -> str:
    """Lowercase, strip, collapse whitespace and underscores."""
    return s.lower().strip().replace("_", " ").replace("-", " ")


def match_column(col_name: str) -> str | None:
    """Return the bp_ key that best matches a column name, or None."""
    col_norm = normalise(col_name)
    for bp_key, variants in COLUMN_MAP.items():
        for v in variants:
            if col_norm == normalise(v):
                return bp_key
    # Partial match fallback
    for bp_key, variants in COLUMN_MAP.items():
        for v in variants:
            if normalise(v) in col_norm or col_norm in normalise(v):
                return bp_key
    return None


def parse_file(uploaded_file) -> pd.DataFrame | None:
    """Parse uploaded CSV or Excel into a DataFrame."""
    name = uploaded_file.name.lower()
    try:
        if name.endswith(".csv"):
            return pd.read_csv(uploaded_file)
        elif name.endswith((".xlsx", ".xls")):
            return pd.read_excel(uploaded_file)
        else:
            st.error(f"Unsupported file type: {uploaded_file.name}")
            return None
    except Exception as e:
        st.error(f"Could not read file: {e}")
        return None


def extract_values(df: pd.DataFrame) -> tuple[dict, dict, list]:
    """
    Try to extract input values from the DataFrame.
    Returns:
      - matched: {bp_key: value} — successfully mapped
      - col_map: {col_name: bp_key} — which column mapped to which key
      - unmatched: [col_name] — columns not recognised
    """
    matched = {}
    col_map = {}
    unmatched = []

    # Strategy 1: columns are input fields, first data row has values
    # (most common: key-value pairs in a single row or column layout)
    if len(df) >= 1:
        for col in df.columns:
            bp_key = match_column(str(col))
            if bp_key:
                raw_val = df[col].iloc[0]
                col_map[col] = bp_key
                matched[bp_key] = raw_val
            else:
                unmatched.append(col)

    # Strategy 2: two-column layout (Parameter | Value)
    if len(df.columns) == 2 and len(matched) <= 1:
        matched = {}
        col_map = {}
        unmatched = []
        param_col, val_col = df.columns[0], df.columns[1]
        for _, row in df.iterrows():
            param = str(row[param_col])
            val   = row[val_col]
            bp_key = match_column(param)
            if bp_key:
                col_map[param] = bp_key
                matched[bp_key] = val
            else:
                unmatched.append(param)

    return matched, col_map, unmatched


def coerce_value(bp_key: str, raw_val):
    """Cast value to correct type, validate categoricals."""
    if pd.isna(raw_val):
        return None, "empty value"

    if bp_key in NUMERIC_KEYS:
        try:
            return float(str(raw_val).replace(",", "").strip()), None
        except ValueError:
            return None, f"could not convert '{raw_val}' to number"

    if bp_key in CATEGORICAL_VALID:
        val_str = str(raw_val).strip().lower()
        valid = CATEGORICAL_VALID[bp_key]
        if val_str in valid:
            return val_str, None
        # Fuzzy match
        for v in valid:
            if v in val_str or val_str in v:
                return v, None
        return None, f"'{raw_val}' not in {valid}"

    # Default: string
    return str(raw_val).strip(), None


# ---------------------------------------------------------------------------
# TEMPLATE DOWNLOAD
# ---------------------------------------------------------------------------

def build_template() -> bytes:
    """Build a CSV template with column headers and example values."""
    rows = {
        "dry_solids (tDS/day)":         [10.0],
        "feed_ds% (post-digestion)":    [20.0],
        "volatile_solids (%)":          [70.0],
        "gcv (MJ/kgDS)":                [12.0],
        "sludge_type":                  ["blended"],
        "variability":                  ["moderate"],
        "pfas_status":                  ["unknown"],
        "disposal_cost ($/tDS)":        [180.0],
        "electricity ($/kWh)":          [0.18],
        "fuel_price ($/GJ)":            [14.0],
        "transport ($/t.km)":           [0.25],
        "avg_transport_distance (km)":  [50.0],
        "carbon_price ($/tCO2e)":       [40.0],
        "waste_heat (kWh/day)":         [0.0],
        "optimisation_priority":        ["balanced"],
        "regulatory_pressure":          ["moderate"],
        "land_constraint":              ["low"],
        "social_licence":               ["low"],
        "biochar_market_confidence":    ["low"],
    }
    df = pd.DataFrame(rows)
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return buf.getvalue().encode()


# ---------------------------------------------------------------------------
# RENDER
# ---------------------------------------------------------------------------

def render():
    st.header("📂 Load Data")
    st.caption(
        "Upload a CSV or Excel file to pre-fill the inputs page. "
        "Column names are matched flexibly — exact names not required."
    )

    # Template download
    with st.expander("📥 Download input template"):
        st.markdown(
            "Download the template, fill in your values in row 2, "
            "then upload it below."
        )
        st.download_button(
            label="Download CSV template",
            data=build_template(),
            file_name="biopoint_inputs_template.csv",
            mime="text/csv",
        )

    st.divider()

    # File upload
    uploaded = st.file_uploader(
        "Upload your data file",
        type=["csv", "xlsx", "xls"],
        help="CSV or Excel. Column headers are matched to input fields automatically.",
    )

    if not uploaded:
        st.info("Upload a file to begin. Column names can be approximate — "
                "the matcher handles common variations.")
        return

    # Parse
    df = parse_file(uploaded)
    if df is None:
        return

    st.success(f"File loaded: **{uploaded.name}** — {len(df)} row(s), {len(df.columns)} column(s)")

    with st.expander("Preview raw data"):
        st.dataframe(df.head(5), use_container_width=True)

    # Extract and map
    matched_raw, col_map, unmatched = extract_values(df)

    # Coerce values
    coerced   = {}
    errors    = {}
    for bp_key, raw_val in matched_raw.items():
        val, err = coerce_value(bp_key, raw_val)
        if err:
            errors[bp_key] = err
        else:
            coerced[bp_key] = val

    # ── Mapping preview ───────────────────────────────────────────────────
    st.subheader("Column mapping")

    if coerced:
        st.markdown(f"**{len(coerced)} fields matched** and ready to apply:")
        preview_rows = []
        for bp_key, val in coerced.items():
            preview_rows.append({
                "Input field": KEY_LABELS.get(bp_key, bp_key),
                "Value": val,
                "Source column": next(
                    (col for col, k in col_map.items() if k == bp_key), "—"
                ),
            })
        st.dataframe(
            pd.DataFrame(preview_rows),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.warning("No input fields were recognised. Check your column names match the template.")

    if errors:
        with st.expander(f"⚠️ {len(errors)} field(s) could not be parsed"):
            for bp_key, err in errors.items():
                st.warning(f"**{KEY_LABELS.get(bp_key, bp_key)}**: {err}")

    if unmatched:
        with st.expander(f"{len(unmatched)} column(s) not recognised (ignored)"):
            for col in unmatched:
                st.caption(f"• {col}")

    # ── Apply button ──────────────────────────────────────────────────────
    st.divider()

    if not coerced:
        st.error("Nothing to apply — no fields were successfully matched.")
        return

    if st.button(
        f"✅ Apply {len(coerced)} field(s) to Inputs",
        type="primary",
        use_container_width=False,
    ):
        for bp_key, val in coerced.items():
            st.session_state[bp_key] = val

        st.success(
            f"Applied {len(coerced)} field(s) to the inputs page. "
            "Navigate to **⚙️ Inputs** to review and run the analysis."
        )
        st.balloons()
