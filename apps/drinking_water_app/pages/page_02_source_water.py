"""
AquaPoint — Page 2: Source Water Quality
"""
import streamlit as st
from ..engine.constants import SOURCE_WATER_QUALITY_PARAMS, ADWG_GUIDELINES, PLANT_TYPES
from ..ui_helpers import section_header, warning_box, info_box, success_box


# Preset source water profiles
SOURCE_WATER_PRESETS = {
    "custom": {"label": "Custom / Manual Entry", "icon": "✏️"},
    "lowland_river": {
        "label": "Lowland River (high turbidity/TOC)",
        "icon": "🌊",
        "values": {"turbidity_ntu": 50, "toc_mg_l": 12, "tds_mg_l": 250, "hardness_mg_l": 120,
                   "iron_mg_l": 0.5, "manganese_mg_l": 0.05, "colour_hu": 30, "algal_cells_ml": 3000},
    },
    "highland_reservoir": {
        "label": "Highland Reservoir (low turbidity/colour)",
        "icon": "🏔️",
        "values": {"turbidity_ntu": 2, "toc_mg_l": 6, "tds_mg_l": 80, "hardness_mg_l": 30,
                   "iron_mg_l": 0.05, "manganese_mg_l": 0.01, "colour_hu": 20, "algal_cells_ml": 800},
    },
    "groundwater_hard": {
        "label": "Hard Groundwater (iron/manganese)",
        "icon": "🪨",
        "values": {"turbidity_ntu": 0.5, "toc_mg_l": 2, "tds_mg_l": 600, "hardness_mg_l": 350,
                   "iron_mg_l": 3.0, "manganese_mg_l": 0.4, "colour_hu": 5, "algal_cells_ml": 0},
    },
    "brackish_groundwater": {
        "label": "Brackish Groundwater",
        "icon": "💧",
        "values": {"turbidity_ntu": 0.3, "toc_mg_l": 3, "tds_mg_l": 3500, "hardness_mg_l": 500,
                   "iron_mg_l": 0.2, "manganese_mg_l": 0.05, "colour_hu": 3, "algal_cells_ml": 0},
    },
    "seawater": {
        "label": "Seawater",
        "icon": "🌊",
        "values": {"turbidity_ntu": 1, "toc_mg_l": 2, "tds_mg_l": 35000, "hardness_mg_l": 6500,
                   "iron_mg_l": 0.02, "manganese_mg_l": 0.001, "colour_hu": 5, "algal_cells_ml": 500},
    },
    "eutrophic_reservoir": {
        "label": "Eutrophic Reservoir (algae/cyanobacteria)",
        "icon": "🦠",
        "values": {"turbidity_ntu": 15, "toc_mg_l": 15, "tds_mg_l": 300, "hardness_mg_l": 180,
                   "iron_mg_l": 0.3, "manganese_mg_l": 0.15, "colour_hu": 40, "algal_cells_ml": 50000},
    },
}


def render():
    st.markdown("""
        <div style="margin-bottom:1.5rem">
            <h2 style="color:#1a1a2e;font-size:1.4rem;font-weight:600;margin-bottom:0.3rem">
                Source Water Quality
            </h2>
            <p style="color:#555;font-size:0.9rem;margin:0">
                Characterise source water to inform treatment train selection and performance prediction.
            </p>
        </div>
    """, unsafe_allow_html=True)

    # ── Preset Selector ──────────────────────────────────────────────────────────
    section_header("Source Water Profile", "📍")

    preset_keys = list(SOURCE_WATER_PRESETS.keys())
    preset_labels = [f"{v['icon']} {v['label']}" for v in SOURCE_WATER_PRESETS.values()]
    current_preset = st.session_state.get("source_preset", "custom")
    current_preset_idx = preset_keys.index(current_preset) if current_preset in preset_keys else 0

    selected_preset_idx = st.selectbox(
        "Load a preset source water profile",
        range(len(preset_keys)),
        format_func=lambda i: preset_labels[i],
        index=current_preset_idx,
        label_visibility="collapsed",
    )
    selected_preset_key = preset_keys[selected_preset_idx]

    if selected_preset_key != st.session_state.get("source_preset"):
        st.session_state["source_preset"] = selected_preset_key
        if selected_preset_key != "custom" and "values" in SOURCE_WATER_PRESETS[selected_preset_key]:
            st.session_state["source_water"] = dict(SOURCE_WATER_PRESETS[selected_preset_key]["values"])
        st.rerun()

    # ── Parameter Inputs ──────────────────────────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    section_header("Water Quality Parameters", "🧪")

    source_water = dict(st.session_state.get("source_water", {}))

    # Display in 2-column grid
    params = list(SOURCE_WATER_QUALITY_PARAMS.items())
    left_params = params[:4]
    right_params = params[4:]

    col1, col2 = st.columns(2)

    def render_param(param_key, param_meta, container):
        with container:
            default_val = source_water.get(param_key, param_meta["default"])
            low, high = param_meta["typical_range"]
            val = st.number_input(
                f"{param_meta['label']}",
                min_value=float(low) * 0,
                max_value=float(high) * 2,
                value=float(default_val),
                step=float((high - low) / 100) if (high - low) > 10 else 0.01,
                format="%.2f" if high < 10 else "%.1f",
                key=f"sw_{param_key}",
            )
            source_water[param_key] = val

            # Treatment challenge indicator
            # ADWG limits apply to TREATED water only — not raw water.
            # Per-parameter thresholds calibrated to engineering significance.
            _CHALLENGE_THRESHOLDS = {
                "turbidity_ntu":  (20,  100),
                "iron_mg_l":      (5,   17),
                "manganese_mg_l": (3,   10),
                "colour_hu":      (3,   10),
                "tds_mg_l":       (1.5, 3),
                "hardness_mg_l":  (2,   5),
            }
            guideline = ADWG_GUIDELINES.get(param_key)
            thresholds = _CHALLENGE_THRESHOLDS.get(param_key)
            if guideline and guideline.get("limit") and thresholds:
                limit = guideline["limit"]
                multiple = val / limit if limit else 0
                mod_thresh, high_thresh = thresholds
                if multiple > high_thresh:
                    st.markdown(
                        f'<span style="font-size:0.75rem;color:#e74c3c">'
                        f'⚠ High treatment load ({val:.1f} {param_meta["unit"]} — {multiple:.0f}× treated water target)</span>',
                        unsafe_allow_html=True
                    )
                elif multiple > mod_thresh:
                    st.markdown(
                        f'<span style="font-size:0.75rem;color:#f39c12">'
                        f'⚡ Moderate treatment load ({val:.1f} {param_meta["unit"]} — {multiple:.0f}× treated water target)</span>',
                        unsafe_allow_html=True
                    )

    for param_key, param_meta in left_params:
        render_param(param_key, param_meta, col1)

    for param_key, param_meta in right_params:
        render_param(param_key, param_meta, col2)

    st.session_state["source_water"] = source_water

    # ── Adverse / P95 Hardness + Alkalinity (optional) ───────────────────────────
    with st.expander("Adverse / P95 water quality (optional — improves softening analysis)", expanded=False):
        st.markdown(
            "<div style='font-size:0.82rem;color:#555;margin-bottom:0.5rem'>"
            "Enter P95 or adverse design hardness and alkalinity if known. Used to trigger "
            "softening analysis and size the softening stage correctly. If not entered, "
            "median × 1.5 is used as a proxy."
            "</div>",
            unsafe_allow_html=True
        )
        col_p1, col_p2 = st.columns(2)
        with col_p1:
            h_p95 = st.number_input(
                "Hardness P95 / Adverse (mg/L as CaCO\u2083)",
                min_value=0.0, max_value=2000.0,
                value=float(source_water.get("hardness_p95_mg_l", -1) if source_water.get("hardness_p95_mg_l", -1) > 0 else 0.0),
                step=10.0, format="%.0f",
                key="sw_hardness_p95",
                help="P95 or adverse design hardness. Leave 0 if not measured."
            )
            source_water["hardness_p95_mg_l"] = h_p95 if h_p95 > 0 else -1.0
            st.caption(f"Proxy if not entered: {source_water.get('hardness_mg_l',150)*1.5:.0f} mg/L (median × 1.5)")
        with col_p2:
            a_p95 = st.number_input(
                "Alkalinity P95 / Adverse (mg/L as CaCO\u2083)",
                min_value=0.0, max_value=2000.0,
                value=float(source_water.get("alkalinity_p95_mg_l", -1) if source_water.get("alkalinity_p95_mg_l", -1) > 0 else 0.0),
                step=10.0, format="%.0f",
                key="sw_alkalinity_p95",
                help="P95 or adverse design alkalinity. Leave 0 if not measured."
            )
            source_water["alkalinity_p95_mg_l"] = a_p95 if a_p95 > 0 else -1.0
    st.session_state["source_water"] = source_water

    # ── Source Water Summary & Risk Flags ─────────────────────────────────────────

    st.markdown("<br>", unsafe_allow_html=True)
    section_header("Water Quality Assessment", "📊")

    flags = []
    turb = source_water.get("turbidity_ntu", 5)
    toc = source_water.get("toc_mg_l", 5)
    tds = source_water.get("tds_mg_l", 300)
    fe = source_water.get("iron_mg_l", 0.1)
    mn = source_water.get("manganese_mg_l", 0.02)
    algae = source_water.get("algal_cells_ml", 500)
    colour = source_water.get("colour_hu", 10)

    # Complexity rating
    complexity_score = 0
    if turb > 50: complexity_score += 2
    elif turb > 10: complexity_score += 1
    if toc > 10: complexity_score += 2
    elif toc > 5: complexity_score += 1
    if tds > 2000: complexity_score += 3
    elif tds > 500: complexity_score += 1
    if fe > 1: complexity_score += 2
    elif fe > 0.3: complexity_score += 1
    if mn > 0.3: complexity_score += 2
    elif mn > 0.1: complexity_score += 1
    if algae > 20000: complexity_score += 3
    elif algae > 5000: complexity_score += 2
    elif algae > 2000: complexity_score += 1

    if complexity_score <= 3:
        complexity_label = "Low"
        complexity_colour = "#2ecc71"
    elif complexity_score <= 7:
        complexity_label = "Moderate"
        complexity_colour = "#f39c12"
    else:
        complexity_label = "High"
        complexity_colour = "#e74c3c"

    col_c1, col_c2, col_c3 = st.columns(3)
    with col_c1:
        st.markdown(f"""
            <div style="text-align:center;background:#f0f4f8;border-radius:8px;padding:1rem;border:1px solid #e2e8f0">
                <div style="font-size:0.75rem;color:#8899aa;margin-bottom:0.3rem">TREATMENT COMPLEXITY</div>
                <div style="font-size:1.6rem;font-weight:700;color:{complexity_colour}">{complexity_label}</div>
            </div>
        """, unsafe_allow_html=True)

    # Specific concerns
    concerns = []
    if turb > 50: concerns.append("High turbidity events")
    if toc > 10: concerns.append("High TOC / DBP precursors")
    if tds > 2000: concerns.append("Elevated TDS / salinity")
    if fe > 0.3: concerns.append("Iron removal required")
    if mn > 0.1: concerns.append("Manganese removal required")
    if algae > 5000: concerns.append("Algal bloom risk")
    if colour > 30: concerns.append("High colour / DOC")

    with col_c2:
        st.markdown(f"""
            <div style="background:#f0f4f8;border-radius:8px;padding:1rem;border:1px solid #e2e8f0">
                <div style="font-size:0.75rem;color:#8899aa;margin-bottom:0.5rem">KEY CONCERNS</div>
                {''.join(f'<div style="font-size:0.8rem;color:#f39c12;margin:0.15rem 0">⚠ {c}</div>' for c in concerns) if concerns else '<div style="font-size:0.8rem;color:#2ecc71">✓ No major concerns</div>'}
            </div>
        """, unsafe_allow_html=True)

    # Treatment drivers — which raw water parameters require significant removal
    # ADWG limits apply to TREATED water at the tap, not raw water.
    # Only flag parameters that are genuinely above typical raw water ranges.
    _DRIVER_THRESHOLDS = {
        "turbidity_ntu":  20,   # >20 NTU is a treatment driver
        "iron_mg_l":      5,    # >1.5 mg/L requires specific Fe removal
        "manganese_mg_l": 3,    # >0.3 mg/L requires Mn-specific treatment
        "colour_hu":      3,    # >45 HU is a significant colour load
        "tds_mg_l":       1.5,  # >900 mg/L approaching membrane territory
        "hardness_mg_l":  2,    # >400 mg/L warrants softening consideration
    }
    treatment_drivers = []
    for param_key, meta in SOURCE_WATER_QUALITY_PARAMS.items():
        guideline = ADWG_GUIDELINES.get(param_key)
        min_multiple = _DRIVER_THRESHOLDS.get(param_key)
        if guideline and guideline.get("limit") and min_multiple:
            val = source_water.get(param_key, meta["default"])
            limit = guideline["limit"]
            multiple = val / limit if limit else 0
            if multiple > min_multiple:
                treatment_drivers.append(
                    f"{meta['label']}: {val:.2f} {meta['unit']} "
                    f"({multiple:.0f}× treated water target of {limit} {meta['unit']})"
                )

    with col_c3:
        driver_html = ''.join(
            f'<div style="font-size:0.8rem;color:#e67e22;margin:0.15rem 0">'
            f'→ {d}</div>' for d in treatment_drivers
        )
        no_driver_html = '<div style="font-size:0.8rem;color:#2ecc71">'\
            '✓ All parameters within treated water targets</div>'
        st.markdown(f"""
            <div style="background:#f0f4f8;border-radius:8px;padding:1rem;border:1px solid #e2e8f0">
                <div style="font-size:0.75rem;color:#8899aa;margin-bottom:0.3rem">TREATMENT DRIVERS</div>
                <div style="font-size:0.68rem;color:#aaa;margin-bottom:0.4rem;font-style:italic">
                    ADWG limits apply to treated product water, not raw water source</div>
                {driver_html if treatment_drivers else no_driver_html}
            </div>
        """, unsafe_allow_html=True)


    # ── Navigation ────────────────────────────────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    left, right = st.columns([1, 1])
    with left:
        if st.button("← Project Setup", use_container_width=True):
            st.session_state["current_page"] = "project_setup"
            st.rerun()
    with right:
        if st.button("Next → Technology Selection →", type="primary", use_container_width=True):
            st.session_state["current_page"] = "technology_selection"
            st.rerun()
