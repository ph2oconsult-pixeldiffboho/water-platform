"""
AquaPoint — Drinking Water Treatment Decision-Support App
Main application entry point.
ph2o Consulting | Water Utility Planning Platform

Routing via: apps/main_app.py → apps/drinking_water_app/app.py
"""
import streamlit as st
from .engine.constants import APP_NAME, APP_VERSION, PLANT_TYPES
from .pages import (
    render_project_setup,
    render_source_water,
    render_technology_selection,
    render_treatment_philosophy,
    render_results,
    render_report,
)

# ─── Page Definitions ─────────────────────────────────────────────────────────────
PAGES = {
    "project_setup": {
        "label": "Project Setup",
        "icon": "📋",
        "render": render_project_setup,
        "number": 1,
    },
    "source_water": {
        "label": "Source Water Quality",
        "icon": "💧",
        "render": render_source_water,
        "number": 2,
    },
    "technology_selection": {
        "label": "Technology Selection",
        "icon": "🔧",
        "render": render_technology_selection,
        "number": 3,
    },
    "treatment_philosophy": {
        "label": "Treatment Philosophy",
        "icon": "🏗️",
        "render": render_treatment_philosophy,
        "number": 4,
    },
    "results": {
        "label": "Analysis Results",
        "icon": "📊",
        "render": render_results,
        "number": 5,
    },
    "report": {
        "label": "Export Report",
        "icon": "📄",
        "render": render_report,
        "number": 6,
    },
}


def render_sidebar():
    """Render the AquaPoint sidebar with navigation."""
    with st.sidebar:
        st.markdown(f"""
        <div class="sb-header">
            <div class="sb-app-icon">🚰</div>
            <div class="sb-app-name">AquaPoint</div>
            <div class="sb-app-sub">Drinking Water Treatment</div>
        </div>
        """, unsafe_allow_html=True)

        if st.button("⬅  Platform Home", key="aq_home", use_container_width=True):
            for _k in ("active_app", "page", "_app_context"):
                st.session_state.pop(_k, None)
            st.rerun()

        st.markdown("<div class='sb-section'>Navigate</div>", unsafe_allow_html=True)

        current_page = st.session_state.get("current_page", "project_setup")

        for page_key, page_data in PAGES.items():
            is_active = page_key == current_page
            btn_type = "primary" if is_active else "secondary"
            label = f"{page_data['icon']}  {page_data['number']}. {page_data['label']}"
            if st.button(label, key=f"nav_{page_key}", type=btn_type, use_container_width=True):
                st.session_state["current_page"] = page_key
                st.rerun()

        # Project summary
        project_name = st.session_state.get("project_name", "")
        plant_type = st.session_state.get("plant_type", "conventional")
        flow = st.session_state.get("flow_ML_d", None)
        selected_techs = st.session_state.get("selected_technologies", [])

        if project_name or flow:
            st.markdown("<div class='sb-section'>Current Project</div>", unsafe_allow_html=True)
            if project_name:
                st.caption(f"📁 {project_name}")
            plant_label = PLANT_TYPES.get(plant_type, {}).get("label", plant_type)
            st.caption(f"🏭 {plant_label}")
            if flow:
                st.caption(f"💧 {flow:.1f} ML/d design flow")
            if selected_techs:
                st.caption(f"⚙️ {len(selected_techs)} technologies selected")
            last_results = st.session_state.get("last_results")
            if last_results:
                mca_score = last_results.get("mca", {}).get("total_score", 0)
                colour = "#0d9e7a" if mca_score >= 75 else "#f39c12" if mca_score >= 50 else "#e74c3c"
                st.markdown(f"""
                <div style="margin-top:0.4rem;background:#e8f4f0;border-radius:6px;
                            padding:0.4rem;text-align:center;border:1px solid #b2d8cc">
                    <div style="font-size:0.65rem;color:#7a8499">MCA Score</div>
                    <div style="font-size:1.3rem;font-weight:800;color:{colour}">{mca_score:.0f}</div>
                    <div style="font-size:0.62rem;color:#7a8499">/ 100</div>
                </div>
                """, unsafe_allow_html=True)

        st.markdown(f"<div class='sb-footer'>AquaPoint {APP_VERSION}<br>ph2o Consulting</div>", unsafe_allow_html=True)


def run():
    """Main AquaPoint application entry point."""
    # ── Page config (set at top level in main_app.py, not here) ────────────────

    # Initialise session state defaults
    if "current_page" not in st.session_state:
        st.session_state["current_page"] = "project_setup"
    if "plant_type" not in st.session_state:
        st.session_state["plant_type"] = "conventional"
    if "flow_ML_d" not in st.session_state:
        st.session_state["flow_ML_d"] = 10.0
    if "source_water" not in st.session_state:
        st.session_state["source_water"] = {
            "turbidity_ntu": 5.0, "toc_mg_l": 5.0, "tds_mg_l": 300.0,
            "hardness_mg_l": 150.0, "iron_mg_l": 0.1, "manganese_mg_l": 0.02,
            "colour_hu": 10.0, "algal_cells_ml": 500.0,
        }
    if "selected_technologies" not in st.session_state:
        st.session_state["selected_technologies"] = []

    # Layout CSS
    st.markdown("""
        <style>
            .main .block-container { padding-top: 1.5rem; max-width: 1100px; }
            .stButton > button { border-radius: 6px; font-weight: 500; transition: all 0.15s ease; }
        </style>
    """, unsafe_allow_html=True)

    # Render sidebar
    render_sidebar()

    # Render current page
    current_page = st.session_state.get("current_page", "project_setup")
    page_data = PAGES.get(current_page, PAGES["project_setup"])
    page_data["render"]()
