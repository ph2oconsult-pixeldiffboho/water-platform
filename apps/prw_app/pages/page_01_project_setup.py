"""page_01_project_setup.py"""
import streamlit as st
from ..ui_helpers import section_header, info_box
from ..engine import EFFLUENT_PRESETS, CLASSES


def render_project_setup():
    st.markdown("## Project Setup")
    st.markdown("Define the project context and target reuse classes before entering effluent quality data.")

    section_header("Project identification", "🏗️")
    col1, col2 = st.columns(2)
    with col1:
        st.text_input("Project name", key="pp_project_name",
                      placeholder="e.g. Western Treatment Plant PRW Upgrade")
    with col2:
        st.text_input("WaterPoint plant / scheme name", key="pp_plant_name",
                      placeholder="e.g. Western Treatment Plant")

    st.markdown("---")
    section_header("Effluent source", "💧")

    preset_options = {k: v["label"] for k, v in EFFLUENT_PRESETS.items()}
    effluent_type = st.selectbox(
        "WaterPoint effluent type",
        options=list(preset_options.keys()),
        format_func=lambda k: preset_options[k],
        key="pp_effluent_type",
        help="Selecting a preset pre-fills effluent quality defaults on the next page.",
    )

    # WaterPoint session state import hook
    if "waterpoint_result" in st.session_state:
        info_box(
            "WaterPoint session detected. Effluent quality values can be "
            "imported from WaterPoint on the Effluent Quality page."
        )

    st.markdown("---")
    section_header("Target reuse classes", "🎯")
    st.markdown("Select all classes to be assessed. Assessment runs in parallel for all selected classes.")

    col_c, col_a, col_aplus, col_prw = st.columns(4)
    with col_c:
        st.checkbox("Class C", value=True, key="pp_class_C")
    with col_a:
        st.checkbox("Class A", value=True, key="pp_class_A")
    with col_aplus:
        st.checkbox("Class A+", value=True, key="pp_class_Aplus")
    with col_prw:
        st.checkbox("PRW", value=True, key="pp_class_PRW")

    st.markdown("---")
    section_header("Notes", "📝")
    st.text_area(
        "Project notes / context",
        key="pp_notes",
        height=100,
        placeholder="Catchment characteristics, intended reuse application, regulatory context...",
    )

    if st.button("→ Continue to Effluent Quality", type="primary"):
        st.session_state["pp_page"] = "effluent_quality"
        st.rerun()
