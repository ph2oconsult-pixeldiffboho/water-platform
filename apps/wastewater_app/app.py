"""
apps/wastewater_app/app.py

Wastewater Treatment Planning Application — main entry point.
Run with: streamlit run apps/wastewater_app/app.py
"""

import sys
from pathlib import Path

# Ensure the platform root is on the Python path
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st
from apps.ui.session_state import initialise_session_defaults

# ── Page configuration ─────────────────────────────────────────────────────
st.set_page_config(
    page_title="Wastewater Treatment Planner",
    page_icon="💧",
    layout="wide",
    initial_sidebar_state="expanded",
)

initialise_session_defaults()

# ── Sidebar navigation ─────────────────────────────────────────────────────
st.sidebar.title("💧 Wastewater Planner")
st.sidebar.markdown("*Water Utility Planning Platform*")
st.sidebar.divider()

PAGES = {
    "🏠 Project Setup": "01_project_setup",
    "📋 Inputs": "02_inputs",
    "⚙️ Treatment Selection": "03_treatment_selection",
    "📊 Results": "04_results",
    "🔁 Compare Scenarios": "05_comparison",
    "📄 Report": "06_report",
    "📖 User Manual": "08_manual",
}

# Use query params for navigation so browser back button works
if "page" not in st.session_state:
    st.session_state["page"] = "01_project_setup"

selected_page = st.sidebar.radio(
    "Navigate",
    options=list(PAGES.keys()),
    index=list(PAGES.values()).index(st.session_state["page"])
    if st.session_state["page"] in PAGES.values() else 0,
)
st.session_state["page"] = PAGES[selected_page]

# ── Route to selected page ─────────────────────────────────────────────────
page_key = st.session_state["page"]

if page_key == "01_project_setup":
    from apps.wastewater_app.pages import page_01_project_setup
    page_01_project_setup.render()

elif page_key == "02_inputs":
    from apps.wastewater_app.pages import page_02_inputs
    page_02_inputs.render()

elif page_key == "03_treatment_selection":
    from apps.wastewater_app.pages import page_03_treatment_selection
    page_03_treatment_selection.render()

elif page_key == "04_results":
    from apps.wastewater_app.pages import page_04_results
    page_04_results.render()

elif page_key == "05_comparison":
    from apps.wastewater_app.pages import page_05_comparison
    page_05_comparison.render()

elif page_key == "06_report":
    from apps.wastewater_app.pages import page_06_report
    page_06_report.render()

elif page_key == "08_manual":
    from apps.wastewater_app.pages import page_08_manual
    page_08_manual.render()

# ── Sidebar footer ─────────────────────────────────────────────────────────
st.sidebar.divider()
from apps.ui.session_state import has_project, has_unsaved_changes, get_current_project
from core.project.project_manager import ProjectManager

if has_project():
    project = get_current_project()
    st.sidebar.caption(f"📁 {project.metadata.project_name}")
    st.sidebar.caption(f"🏭 {project.metadata.plant_name or 'No plant set'}")

    if has_unsaved_changes():
        if st.sidebar.button("💾 Save Project", type="primary"):
            pm = ProjectManager()
            pm.save(project)
            st.session_state["has_unsaved_changes"] = False
            st.sidebar.success("Saved ✓")

st.sidebar.caption("v1.0.0 — Concept Stage Planning")
