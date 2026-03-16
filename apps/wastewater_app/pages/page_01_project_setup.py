"""
apps/wastewater_app/pages/page_01_project_setup.py

01 Project Setup — project creation, planning scenario, scenario management.
"""

from __future__ import annotations
import streamlit as st
from core.project.project_model import DomainType, PlanningScenario
from core.project.project_manager import ProjectManager, ScenarioManager
from apps.ui.session_state import (
    get_current_project, set_current_project, update_current_project, has_project,
)
from apps.ui.ui_components import render_page_header


def render() -> None:
    render_page_header("01 Project Setup", "Create or load a project and define the planning scenario.")

    tab_new, tab_load, tab_manage = st.tabs(["➕ New Project", "📂 Load Project", "⚙️ Manage Scenarios"])

    # ── NEW PROJECT ────────────────────────────────────────────────────────
    with tab_new:
        st.subheader("Create New Project")

        with st.form("new_project_form"):
            col1, col2 = st.columns(2)
            with col1:
                project_name   = st.text_input("Project Name *", placeholder="e.g. Northside WWTP Upgrade")
                plant_name     = st.text_input("Plant / Facility Name", placeholder="e.g. Northside WRRF")
                plant_location = st.text_input("Location", placeholder="e.g. Brisbane, QLD")
            with col2:
                client_name    = st.text_input("Client / Utility")
                project_number = st.text_input("Project Number")
                author         = st.text_input("Prepared By")

            st.markdown("#### Planning Scenario")
            planning_scenario = st.selectbox(
                "Select the primary planning objective for this study",
                options=[p.display_name for p in PlanningScenario],
                help=(
                    "The planning scenario influences recommended treatment pathways, "
                    "highlighted metrics in results, and risk weightings in comparisons."
                ),
            )
            scenario_descriptions = {
                "Capacity Expansion":           "📈 Increase plant hydraulic or organic load capacity.",
                "Nutrient Limit Tightening":    "🔬 Meet tighter effluent TN / TP licence conditions.",
                "Energy Optimisation":          "⚡ Reduce energy consumption and energy costs.",
                "Carbon Reduction":             "🌿 Minimise Scope 1, 2 and 3 carbon emissions.",
                "Biosolids Constraints":        "♻️ Address biosolids quantity, quality or disposal pathway.",
                "Reuse / Future PRW Integration": "💧 Enable effluent reuse or future indirect potable reuse.",
            }
            st.info(scenario_descriptions.get(planning_scenario, ""))

            notes = st.text_area("Study Description / Notes", height=70)
            submitted = st.form_submit_button("Create Project", type="primary", use_container_width=True)

        if submitted:
            if not project_name.strip():
                st.error("Please enter a project name.")
            else:
                name_to_enum = {p.display_name: p for p in PlanningScenario}
                ps_enum = name_to_enum.get(planning_scenario, PlanningScenario.CAPACITY_EXPANSION)

                pm = ProjectManager()
                project = pm.create_project(
                    project_name=project_name.strip(),
                    domain=DomainType.WASTEWATER,
                    plant_name=plant_name.strip(),
                    plant_location=plant_location.strip(),
                    author=author.strip(),
                    client_name=client_name.strip(),
                    project_number=project_number.strip(),
                    notes=notes.strip(),
                )
                project.metadata.planning_scenario = ps_enum.value
                pm.save(project)
                set_current_project(project)
                st.success(f"✅ Project **{project_name}** created. Planning scenario: **{planning_scenario}**.")
                st.rerun()

    # ── LOAD PROJECT ───────────────────────────────────────────────────────
    with tab_load:
        st.subheader("Load Saved Project")
        pm = ProjectManager()
        saved = [p for p in pm.list_projects() if p.get("domain") == "wastewater"]

        if not saved:
            st.info("No saved wastewater projects found. Create a new project above.")
        else:
            import pandas as pd
            df = pd.DataFrame(saved)[["project_name","plant_name","client_name","author","last_modified","scenario_count"]]
            df.columns = ["Project","Plant","Client","Author","Last Modified","Scenarios"]
            st.dataframe(df, use_container_width=True, hide_index=True)

            names = [p["project_name"] for p in saved]
            sel   = st.selectbox("Select project", options=names)
            match = next(p for p in saved if p["project_name"] == sel)

            if st.button("Load Selected Project", type="primary"):
                project = pm.load(match["project_id"])
                set_current_project(project)
                st.success(f"✅ Loaded: **{project.metadata.project_name}**")
                st.rerun()

    # ── MANAGE SCENARIOS ───────────────────────────────────────────────────
    with tab_manage:
        if not has_project():
            st.info("Create or load a project first.")
            return

        project = get_current_project()
        meta    = project.metadata
        pm      = ProjectManager()
        sm      = ScenarioManager()

        col1, col2 = st.columns(2)
        with col1:
            st.markdown(f"**Project:** {meta.project_name}")
            st.markdown(f"**Plant:** {meta.plant_name or '—'}")
            ps_val = meta.planning_scenario
            if ps_val:
                try:
                    ps_display = PlanningScenario(ps_val).display_name
                except ValueError:
                    ps_display = ps_val
                st.markdown(f"**Planning Scenario:** {ps_display}")
        with col2:
            st.markdown(f"**Client:** {meta.client_name or '—'}")
            st.markdown(f"**Author:** {meta.author or '—'}")
            st.markdown(f"**Scenarios:** {len(project.scenarios)}")

        st.divider()
        st.subheader("Scenarios")

        for sid, scenario in list(project.scenarios.items()):
            c1, c2, c3, c4, c5, c6 = st.columns([3, 2, 1, 1, 1, 1])
            c1.write(scenario.scenario_name)
            c2.caption(scenario.scenario_type.display_name)
            c3.markdown("⭐" if scenario.is_preferred else "")
            c4.markdown("✅" if not scenario.is_stale else "⏳")
            if c5.button("📋", key=f"dup_{sid}", help="Duplicate"):
                cloned = sm.clone_scenario(project, sid, f"{scenario.scenario_name} (copy)")
                update_current_project(project)
                pm.save(project)
                st.rerun()
            if len(project.scenarios) > 1:
                if c6.button("🗑️", key=f"del_{sid}", help="Delete"):
                    try:
                        sm.delete_scenario(project, sid)
                        update_current_project(project)
                        pm.save(project)
                        st.rerun()
                    except ValueError as e:
                        st.error(str(e))

        st.divider()
        with st.expander("➕ Add New Scenario"):
            with st.form("add_scenario"):
                from core.project.project_model import ScenarioType
                new_name = st.text_input("Scenario Name", placeholder="e.g. Option B — MBR")
                new_type = st.selectbox("Type", [t.display_name for t in ScenarioType])
                copy_from = st.selectbox("Copy inputs from",
                    ["Blank"] + [s.scenario_name for s in project.get_all_scenarios()])
                add_ok = st.form_submit_button("Add Scenario")
            if add_ok and new_name.strip():
                type_map = {t.display_name: t for t in ScenarioType}
                copy_id  = next((sid for sid, s in project.scenarios.items()
                                 if s.scenario_name == copy_from), None) if copy_from != "Blank" else None
                sm.add_scenario(project, new_name.strip(), type_map.get(new_type), copy_from_id=copy_id)
                update_current_project(project)
                pm.save(project)
                st.success(f"Scenario '{new_name}' added.")
                st.rerun()
