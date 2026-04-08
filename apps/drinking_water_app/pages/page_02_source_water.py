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
            <h2 style="color:#e8f4fd;font-size:1.4rem;font-weight:600;margin-bottom:0.3rem">
                Source Water Quality
            </h2>
            <p style="color:#8899aa;font-size:0.9rem;margin:0">
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

            # ADWG guideline indicator
            guideline = ADWG_GUIDELINES.get(param_key)
            if guideline and guideline.get("limit"):
                limit = guideline["limit"]
                if val > limit:
                    st.markdown(
                        f'<span style="font-size:0.75rem;color:#e74c3c">⚠ Exceeds ADWG {limit} {param_meta["unit"]}</span>',
                        unsafe_allow_html=True
                    )
                elif val > limit * 0.8:
                    st.markdown(
                        f'<span style="font-size:0.75rem;color:#f39c12">⚡ Approaching ADWG limit ({limit} {param_meta["unit"]})</span>',
                        unsafe_allow_html=True
                    )

    for param_key, param_meta in left_params:
        render_param(param_key, param_meta, col1)

    for param_key, param_meta in right_params:
        render_param(param_key, param_meta, col2)

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
            <div style="text-align:center;background:#1a2332;border-radius:8px;padding:1rem;border:1px solid #2a3a52">
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
            <div style="background:#1a2332;border-radius:8px;padding:1rem;border:1px solid #2a3a52">
                <div style="font-size:0.75rem;color:#8899aa;margin-bottom:0.5rem">KEY CONCERNS</div>
                {''.join(f'<div style="font-size:0.8rem;color:#f39c12;margin:0.15rem 0">⚠ {c}</div>' for c in concerns) if concerns else '<div style="font-size:0.8rem;color:#2ecc71">✓ No major concerns</div>'}
            </div>
        """, unsafe_allow_html=True)

    # ADWG pre-treatment exceedances
    exceedances = []
    for param_key, meta in SOURCE_WATER_QUALITY_PARAMS.items():
        guideline = ADWG_GUIDELINES.get(param_key)
        if guideline and guideline.get("limit"):
            val = source_water.get(param_key, meta["default"])
            if val > guideline["limit"]:
                exceedances.append(f"{meta['label']}: {val:.2f} {meta['unit']} (limit: {guideline['limit']})")

    with col_c3:
        st.markdown(f"""
            <div style="background:#1a2332;border-radius:8px;padding:1rem;border:1px solid #2a3a52">
                <div style="font-size:0.75rem;color:#8899aa;margin-bottom:0.5rem">RAW WATER ADWG EXCEEDANCES</div>
                {''.join(f'<div style="font-size:0.8rem;color:#e74c3c;margin:0.15rem 0">✗ {e}</div>' for e in exceedances) if exceedances else '<div style="font-size:0.8rem;color:#2ecc71">✓ All within ADWG limits</div>'}
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
