"""
AquaPoint — Page 3: Technology Selection
Reasoning engine hint banner guides selection; user retains full control.
ph2o Consulting | Water Utility Planning Platform
"""
import streamlit as st
from ..engine.constants import TECHNOLOGIES, PLANT_TYPES
from ..engine.calculations import screen_technology_feasibility
from ..engine.reasoning import SourceWaterInputs, run_reasoning_engine
from ..engine.reasoning.archetypes import ARCHETYPES
from ..ui_helpers import section_header, warning_box, info_box, error_box

CATEGORY_ORDER = [
    "Pretreatment", "Pre-Oxidation", "Primary Treatment", "Softening", "Filtration",
    "Membrane", "Advanced Treatment", "Disinfection", "Residuals",
]

ARCHETYPE_TECH_HINTS = {
    "A": ["screening", "coagulation_flocculation", "rapid_gravity_filtration",
          "uv_disinfection", "chlorination"],
    "B": ["screening", "coagulation_flocculation", "sedimentation",
          "rapid_gravity_filtration", "uv_disinfection", "chlorination", "sludge_thickening"],
    "C": ["screening", "actiflo_carb",
          "rapid_gravity_filtration", "uv_disinfection", "chlorination", "sludge_thickening"],
    "D": ["screening", "coagulation_flocculation", "daf",
          "rapid_gravity_filtration", "uv_disinfection", "chlorination", "sludge_thickening"],
    "E": ["screening", "coagulation_flocculation", "sedimentation",
          "rapid_gravity_filtration", "bac", "uv_disinfection", "chlorination", "sludge_thickening"],
    "F": ["coagulation_flocculation", "chemical_softening", "sedimentation",
          "rapid_gravity_filtration", "uv_disinfection", "chlorination", "sludge_thickening"],
    "G": ["screening", "coagulation_flocculation", "sedimentation",
          "rapid_gravity_filtration", "ozonation", "bac",
          "uv_disinfection", "chlorination", "sludge_thickening"],
    "H": ["screening", "coagulation_flocculation", "mf_uf", "ro",
          "uv_disinfection", "chloramination", "brine_management"],
    "I": ["screening", "coagulation_flocculation", "sedimentation",
          "rapid_gravity_filtration", "gac", "uv_disinfection", "chlorination", "sludge_thickening"],
}

PLANT_TO_SOURCE = {
    "conventional": "river", "membrane": "river",
    "groundwater": "groundwater", "desalination": "desalination",
}


def _get_hint(plant_type: str, source_water: dict):
    """Run reasoning engine silently. Returns result or None."""
    try:
        sw  = source_water
        algal = float(sw.get("algal_cells_ml", 0))
        algae_risk = ("high" if algal > 10000 else "moderate" if algal > 2000 else "low")
        turb = float(sw.get("turbidity_ntu", 5))
        inputs = SourceWaterInputs(
            source_type=PLANT_TO_SOURCE.get(plant_type, "river"),
            turbidity_median_ntu=turb,
            turbidity_p95_ntu=turb * 4,
            turbidity_p99_ntu=turb * 10,
            toc_median_mg_l=float(sw.get("toc_mg_l", 5)),
            toc_p95_mg_l=float(sw.get("toc_mg_l", 5)) * 1.5,
            colour_median_hu=float(sw.get("colour_hu", 10)),
            hardness_median_mg_l=float(sw.get("hardness_mg_l", 150)),
            hardness_p95_mg_l=float(sw.get("hardness_p95_mg_l", -1.0)),
            alkalinity_p95_mg_l=float(sw.get("alkalinity_p95_mg_l", -1.0)),
            iron_median_mg_l=float(sw.get("iron_mg_l", 0.1)),
            manganese_median_mg_l=float(sw.get("manganese_mg_l", 0.02)),
            tds_median_mg_l=float(sw.get("tds_mg_l", 300)),
            algae_risk=algae_risk,
            variability_class="moderate",
            catchment_risk="moderate",
            treatment_objective="potable",
        )
        return run_reasoning_engine(inputs)
    except Exception:
        return None


def render():
    st.markdown("""
        <div style="margin-bottom:1.5rem">
            <h2 style="color:#1a1a2e;font-size:1.4rem;font-weight:600;margin-bottom:0.3rem">
                Technology Selection
            </h2>
            <p style="color:#555;font-size:0.9rem;margin:0">
                Select technologies for the analysis. The reasoning engine suggests
                a preferred philosophy — you retain full control of the final selection.
            </p>
        </div>
    """, unsafe_allow_html=True)

    plant_type   = st.session_state.get("plant_type", "conventional")
    flow_ML_d    = st.session_state.get("flow_ML_d", 10.0)
    source_water = st.session_state.get("source_water", {})

    if not source_water:
        warning_box("Please complete Source Water Quality before selecting technologies.")

    selected_technologies = list(st.session_state.get("selected_technologies", []))

    # ── Reasoning hint banner ─────────────────────────────────────────────────
    if source_water:
        hint = _get_hint(plant_type, source_water)
        if hint:
            pkey = hint.preferred_archetype_key
            arch = ARCHETYPES.get(pkey, {})
            suggested = [
                t for t in ARCHETYPE_TECH_HINTS.get(pkey, [])
                if t in TECHNOLOGIES and
                   plant_type in TECHNOLOGIES[t].get("applicable_plants", [])
            ]
            train_str = " → ".join(TECHNOLOGIES[t]["label"] for t in suggested)

            st.markdown(f"""
                <div style="background:#eff6ff;border:1px solid #bfdbfe;
                            border-radius:10px;padding:0.9rem 1.2rem;margin-bottom:1rem">
                    <div style="font-size:0.68rem;color:#4a9eff;text-transform:uppercase;
                                letter-spacing:0.08em;margin-bottom:0.35rem">
                        🏗️ Reasoning Engine — Recommended Philosophy
                    </div>
                    <div style="font-size:0.92rem;font-weight:700;color:#e8f4fd;margin-bottom:0.25rem">
                        {pkey}. {hint.preferred_archetype_label}
                    </div>
                    <div style="font-size:0.81rem;color:#1a56a0;line-height:1.6;margin-bottom:0.55rem">
                        {arch.get('philosophy', '')}
                    </div>
                    <div style="font-size:0.77rem;color:#8899aa">
                        Suggested train:
                        <span style="color:#0284c7">{train_str}</span>
                    </div>
                </div>
            """, unsafe_allow_html=True)

            ca, _ = st.columns([1, 3])
            with ca:
                if st.button("↳ Apply Suggested Train", use_container_width=True):
                    st.session_state["selected_technologies"] = suggested
                    st.rerun()

            for w in hint.key_warnings[:2]:
                error_box(w) if "⚠" in w else warning_box(w)

    # ── Technology grid ───────────────────────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    section_header("Treatment Technologies", "🔧")

    all_keys = list(TECHNOLOGIES.keys())
    feasibility = (
        screen_technology_feasibility(plant_type, flow_ML_d, source_water, all_keys)
        if source_water else {k: {"feasible": True, "flags": []} for k in all_keys}
    )

    by_cat = {}
    for tk, td in TECHNOLOGIES.items():
        by_cat.setdefault(td["category"], []).append((tk, td))

    new_selected = []

    for category in CATEGORY_ORDER:
        if category not in by_cat:
            continue
        section_header(category, "▸")
        techs = by_cat[category]
        for row in [techs[i:i+2] for i in range(0, len(techs), 2)]:
            cols = st.columns(2)
            for ci, (tk, td) in enumerate(row):
                with cols[ci]:
                    feas    = feasibility.get(tk, {})
                    ok      = plant_type in td.get("applicable_plants", [])
                    checked = tk in selected_technologies
                    border  = "#4a9eff" if checked else ("#3a2a2a" if not ok else "#2a3a52")
                    bg      = "#0d1e30" if checked else "#111d2b"

                    st.markdown(
                        f'<div style="border:1px solid {border};border-radius:8px;'
                        f'padding:0.7rem;margin-bottom:0.3rem;background:{bg}">',
                        unsafe_allow_html=True,
                    )
                    if st.checkbox(f"**{td['label']}**", value=checked,
                                   key=f"tech_{tk}", disabled=not ok):
                        new_selected.append(tk)
                    st.markdown(
                        f'<div style="font-size:0.78rem;color:#8899aa;margin-top:-0.3rem">'
                        f'{td["description"]}</div>',
                        unsafe_allow_html=True,
                    )
                    for flag in feas.get("flags", []):
                        st.markdown(
                            f'<div style="font-size:0.72rem;color:#f39c12;margin-top:0.2rem">⚠ {flag}</div>',
                            unsafe_allow_html=True,
                        )
                    if not ok:
                        st.markdown(
                            f'<div style="font-size:0.72rem;color:#e74c3c;margin-top:0.2rem">'
                            f'✗ Not applicable for {PLANT_TYPES[plant_type]["label"]}</div>',
                            unsafe_allow_html=True,
                        )
                    st.markdown("</div>", unsafe_allow_html=True)

    st.session_state["selected_technologies"] = new_selected

    # ── Selected train summary ────────────────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    section_header("Selected Treatment Train", "✓")

    if new_selected:
        train_display = " → ".join(TECHNOLOGIES[t]["label"] for t in new_selected)
        st.markdown(f"""
            <div style="background:#eff6ff;border:1px solid #4a9eff;border-radius:8px;
                        padding:0.8rem 1rem;font-size:0.85rem;color:#1a56a0">
                <span style="color:#4a9eff;font-weight:600">Treatment Train: </span>
                {train_display}
            </div>
        """, unsafe_allow_html=True)
        if not any(t in new_selected for t in ["chlorination", "chloramination", "uv_disinfection"]):
            warning_box("No disinfection technology selected. ADWG requires demonstrated pathogen inactivation.")
        if "bac" in new_selected and "ozonation" not in new_selected:
            warning_box("BAC is most effective when preceded by ozonation.")
        if "ro" in new_selected and "mf_uf" not in new_selected:
            info_box("Consider MF/UF upstream of RO for membrane protection.")
        st.markdown(
            f"<br><span style='color:#8899aa;font-size:0.85rem'>{len(new_selected)} technologies selected</span>",
            unsafe_allow_html=True,
        )
    else:
        warning_box("No technologies selected. Select at least one technology to proceed.")

    # ── Navigation ────────────────────────────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    left, right = st.columns(2)
    with left:
        if st.button("← Source Water", use_container_width=True):
            st.session_state["current_page"] = "source_water"
            st.rerun()
    with right:
        if st.button("Next → Treatment Philosophy →", type="primary",
                     use_container_width=True, disabled=len(new_selected) == 0):
            st.session_state["current_page"] = "treatment_philosophy"
            st.rerun()
