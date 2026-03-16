"""
apps/wastewater_app/pages/page_04_results.py

04 Results — full engineering, cost, carbon, energy and risk results.
Planning scenario highlights the most relevant metrics.
"""

from __future__ import annotations
import streamlit as st
import plotly.graph_objects as go

from apps.ui.session_state import (
    require_project, get_current_project, update_current_project,
    get_active_scenario, cache_calculation_result,
)
from apps.ui.ui_components import (
    render_page_header, render_scenario_selector,
    render_validation_banner, render_cost_summary_card,
    render_carbon_summary_card, render_risk_matrix, stale_warning,
)
from core.project.project_manager import ProjectManager
from core.assumptions.assumptions_manager import AssumptionsManager
from core.project.project_model import DomainType, PlanningScenario
from domains.wastewater.domain_interface import WastewaterDomainInterface
from domains.wastewater.input_model import WastewaterInputs


def render() -> None:
    render_page_header("04 Results", "Engineering, cost, carbon, energy and risk outputs.")
    require_project()

    project  = get_current_project()
    pm       = ProjectManager()
    render_scenario_selector(project)
    scenario = get_active_scenario()

    if not scenario:
        return
    if not scenario.domain_inputs:
        st.warning("⚠️ Complete 02 Plant Inputs first.")
        return
    if not scenario.treatment_pathway:
        st.warning("⚠️ Complete 03 Treatment Options first.")
        return

    # ── Calibration toggle ────────────────────────────────────────────────
    cal_applied = bool((scenario.domain_inputs or {}).get("_calibration_applied"))
    use_calibrated = False
    if cal_applied:
        col_tog, col_info = st.columns([1, 4])
        with col_tog:
            use_calibrated = st.toggle(
                "Use calibrated model",
                value=True,
                help="Switch between default model assumptions and plant-calibrated assumptions",
            )
        with col_info:
            n_factors = (scenario.domain_inputs or {}).get("_n_factors_calibrated", "?")
            if use_calibrated:
                st.success(
                    f"🔬 **Calibrated model active** — "
                    f"{n_factors} factor(s) from plant data override default assumptions. "
                    "Results reflect actual plant behaviour."
                )
            else:
                st.info("📐 **Default model** — using standard screening-level assumptions.")

    # ── Planning scenario highlight banner ─────────────────────────────────
    ps_val = project.metadata.planning_scenario
    ps_highlight = None
    if ps_val:
        try:
            ps_highlight = PlanningScenario(ps_val)
            highlight_map = {
                PlanningScenario.CAPACITY_EXPANSION:        "💰 Cost metrics are highlighted for this Capacity Expansion study.",
                PlanningScenario.NUTRIENT_LIMIT_TIGHTENING: "🔬 Effluent quality and nitrogen removal are highlighted.",
                PlanningScenario.ENERGY_OPTIMISATION:       "⚡ Energy metrics are highlighted for this Energy Optimisation study.",
                PlanningScenario.CARBON_REDUCTION:          "🌿 Carbon emissions are highlighted for this Carbon Reduction study.",
                PlanningScenario.BIOSOLIDS_CONSTRAINTS:     "♻️ Sludge production and disposal cost are highlighted.",
                PlanningScenario.REUSE_PRW_INTEGRATION:     "💧 Effluent quality metrics are highlighted for reuse planning.",
            }
            st.info(highlight_map.get(ps_highlight, ""))
        except ValueError:
            pass

    # ── Calculate button ───────────────────────────────────────────────────
    if scenario.is_stale:
        stale_warning()
        if st.button("▶ Run Calculations", type="primary"):
            _run_calculations(project, scenario, pm, use_calibrated=use_calibrated if cal_applied else True)

    if not scenario.cost_result:
        if not scenario.is_stale:
            _run_calculations(project, scenario, pm)
        else:
            st.info("Run calculations to see results.")
            return

    if scenario.validation_result:
        render_validation_banner(scenario.validation_result)

    st.subheader(f"Results: {scenario.scenario_name}")

    # ── Tab layout ─────────────────────────────────────────────────────────
    tab_eng, tab_cost, tab_carbon, tab_risk = st.tabs(
        ["⚙️ Engineering", "💰 Cost", "🌿 Carbon & Energy", "⚠️ Risk"]
    )

    with tab_eng:
        _render_engineering_tab(scenario, ps_highlight)

    with tab_cost:
        render_cost_summary_card(scenario.cost_result)

    with tab_carbon:
        render_carbon_summary_card(scenario.carbon_result)

    with tab_risk:
        if scenario.risk_result:
            render_risk_matrix(scenario.risk_result)


def _render_engineering_tab(scenario, ps_highlight) -> None:
    eng = scenario.domain_specific_outputs.get("engineering_summary", {})
    if not eng:
        st.info("Engineering summary not available.")
        return

    flow = eng.get("design_flow_mld", 0)

    # ── Primary KPI row ────────────────────────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)

    # Highlight the metric most relevant to the planning scenario
    energy_delta = None
    carbon_delta = None

    with c1:
        spec_e = eng.get("specific_energy_kwh_kl")
        label  = "⚡ Specific Energy" if ps_highlight and ps_highlight.primary_metric == "energy" else "Specific Energy"
        st.metric(label, f"{spec_e:.3f} kWh/kL" if spec_e else "—")

    with c2:
        total_e = eng.get("total_energy_kwh_day", 0)
        st.metric("Total Energy", f"{total_e:,.0f} kWh/day")

    with c3:
        sludge = eng.get("total_sludge_kgds_day", 0)
        label  = "♻️ Sludge Production" if ps_highlight and ps_highlight.primary_metric == "sludge" else "Sludge Production"
        st.metric(label, f"{sludge:,.0f} kg DS/day" if sludge else "—")

    with c4:
        techs = eng.get("technology_sequence", [])
        st.metric("Technologies", " + ".join(t.upper() for t in techs) if techs else "—")

    # ── Energy breakdown chart ─────────────────────────────────────────────
    tech_perf = scenario.domain_specific_outputs.get("technology_performance", {})
    energy_by_tech = {code: perf.get("specific_energy_kwh_kl", 0) or 0
                      for code, perf in tech_perf.items()}
    if energy_by_tech:
        st.subheader("Specific Energy by Technology (kWh/kL)")
        fig = go.Figure(go.Bar(
            x=list(energy_by_tech.keys()),
            y=list(energy_by_tech.values()),
            marker_color="#1f6aa5",
            text=[f"{v:.3f}" for v in energy_by_tech.values()],
            textposition="auto",
        ))
        fig.update_layout(yaxis_title="kWh/kL", plot_bgcolor="white", height=280)
        st.plotly_chart(fig, use_container_width=True)

    # ── Per-technology performance tables ──────────────────────────────────
    for tech_code, perf in tech_perf.items():
        if not perf:
            continue
        st.divider()

        # Get the full TechnologyResult if available for richer display
        tech_result = None
        if hasattr(scenario, "domain_specific_outputs"):
            tech_results = scenario.domain_specific_outputs.get("technology_results_full", {})
            tech_result  = tech_results.get(tech_code)

        # Title with category badge
        tech_cat = perf.get("technology_category", "")
        cat_badge = f" · *{tech_cat}*" if tech_cat else ""
        st.subheader(f"{tech_code.replace('_',' ').title()} — Performance{cat_badge}")

        # ── Key metrics row ────────────────────────────────────────────────
        m1, m2, m3, m4 = st.columns(4)

        # Removal percentages from new typed sub-results
        tn_rem  = perf.get("tn_removal_pct")
        bod_rem = perf.get("bod_removal_pct")
        sludge_yr = perf.get("sludge_production_tds_yr")
        total_co2 = perf.get("total_tco2e_yr")

        with m1:
            if tn_rem is not None:
                st.metric("TN Removal", f"{tn_rem:.0f}%")
            elif bod_rem is not None:
                st.metric("BOD Removal", f"{bod_rem:.0f}%")
        with m2:
            if perf.get("effluent_tn_mg_l") is not None:
                st.metric("Effluent TN", f"{perf['effluent_tn_mg_l']:.1f} mg/L")
            elif perf.get("effluent_tss_mg_l") is not None:
                st.metric("Effluent TSS", f"{perf['effluent_tss_mg_l']:.1f} mg/L")
        with m3:
            if sludge_yr is not None and sludge_yr > 0:
                st.metric("Sludge (annual)", f"{sludge_yr:,.0f} t DS/yr")
            elif perf.get("sludge_production_kgds_day"):
                st.metric("Sludge (daily)", f"{perf['sludge_production_kgds_day']:,.0f} kg DS/d")
        with m4:
            if total_co2 is not None:
                st.metric("Total GHG", f"{total_co2:,.0f} tCO₂e/yr")
            elif perf.get("scope2_tco2e_yr") is not None:
                st.metric("Scope 2 GHG", f"{perf['scope2_tco2e_yr']:,.0f} tCO₂e/yr")

        # ── Carbon detail row ──────────────────────────────────────────────
        s1 = perf.get("scope1_tco2e_yr")
        s2 = perf.get("scope2_tco2e_yr")
        c_cost = perf.get("carbon_cost_yr")
        if s1 is not None or s2 is not None:
            cc1, cc2, cc3 = st.columns(3)
            with cc1:
                st.metric("Scope 1 (process)", f"{s1:,.0f} tCO₂e/yr" if s1 is not None else "—")
            with cc2:
                st.metric("Scope 2 (electricity)", f"{s2:,.0f} tCO₂e/yr" if s2 is not None else "—")
            with cc3:
                st.metric("Carbon Cost", f"${c_cost:,.0f}/yr" if c_cost else "—")

        # ── Effluent compliance check ──────────────────────────────────────
        compliance_flag = perf.get("compliance_flag")
        compliance_issues = perf.get("compliance_issues", "")
        if compliance_flag == "Meets Targets":
            st.success(f"✅ **{tech_code.replace('_',' ').title()}** — Effluent targets met")
        elif compliance_flag == "Review Required":
            st.warning(
                f"⚠️ **{tech_code.replace('_',' ').title()} — Compliance review required**\n\n"
                + "\n\n".join(f"- {issue}" for issue in compliance_issues.split("; ") if issue)
            )

        # ── Engineering details (collapsible) ──────────────────────────────
        SKIP_KEYS = {"technology_category", "effluent_bod_mg_l", "effluent_tss_mg_l",
                     "effluent_tn_mg_l", "effluent_nh4_mg_l", "effluent_tp_mg_l",
                     "sludge_production_kgds_day", "sludge_production_tds_yr",
                     "energy_intensity_kwh_kl", "net_energy_kwh_day",
                     "scope1_tco2e_yr", "scope2_tco2e_yr", "total_tco2e_yr",
                     "carbon_cost_yr", "risk_score",
                     "bod_removal_pct", "nh4_removal_pct", "tn_removal_pct", "tp_removal_pct",
                     "_notes"}

        detail_items = {k: v for k, v in perf.items()
                        if k not in SKIP_KEYS and v is not None and v != ""}
        if detail_items:
            with st.expander(f"Engineering details — {tech_code}", expanded=False):
                cols = st.columns(3)
                for idx, (key, val) in enumerate(detail_items.items()):
                    with cols[idx % 3]:
                        label = key.replace("_", " ").title()
                        if isinstance(val, float):
                            st.metric(label, f"{val:,.3f}" if val < 10 else f"{val:,.1f}")
                        elif isinstance(val, int):
                            st.metric(label, f"{val:,}")
                        else:
                            st.metric(label, str(val))

        # ── Notes/assumptions (collapsible) ───────────────────────────────
        notes_data = perf.get("_notes")  # written by domain_interface if present
        if notes_data and isinstance(notes_data, dict):
            assumptions = notes_data.get("assumptions", [])
            limitations = notes_data.get("limitations", [])
            warnings    = notes_data.get("warnings", [])
            if assumptions or limitations or warnings:
                with st.expander(f"Assumptions & notes — {tech_code}", expanded=False):
                    if warnings:
                        for w in warnings:
                            st.warning(w)
                    if assumptions:
                        st.markdown("**Assumptions used:**")
                        for a in assumptions:
                            st.markdown(f"- {a}")
                    if limitations:
                        st.markdown("**Limitations:**")
                        for lim in limitations:
                            st.markdown(f"- {lim}")


def _run_calculations(project, scenario, pm: ProjectManager, use_calibrated: bool = True) -> None:
    with st.spinner("Running calculations..."):
        try:
            mgr   = AssumptionsManager()
            if not use_calibrated:
                # Use default (non-calibrated) assumptions regardless of what's stored
                assumptions = mgr.load_defaults(DomainType.WASTEWATER)
            else:
                assumptions = scenario.assumptions or mgr.load_defaults(DomainType.WASTEWATER)

            # Override assumptions with user-entered economic values from inputs
            econ = scenario.domain_inputs or {}
            if econ.get("electricity_price_per_kwh"):
                assumptions = mgr.apply_override(
                    assumptions, "cost", "electricity_per_kwh",
                    econ["electricity_price_per_kwh"], "From plant inputs", "User"
                )
            if econ.get("carbon_price_per_tonne"):
                assumptions = mgr.apply_override(
                    assumptions, "carbon", "carbon_price_per_tonne",
                    econ["carbon_price_per_tonne"], "From plant inputs", "User"
                )
            # Also update engineering defaults for influent quality
            for eng_key, inp_key in [
                ("influent_bod_mg_l", "influent_bod_mg_l"),
                ("influent_tn_mg_l",  "influent_tkn_mg_l"),
                ("influent_tp_mg_l",  "influent_tp_mg_l"),
            ]:
                if econ.get(inp_key):
                    assumptions = mgr.apply_override(
                        assumptions, "engineering", eng_key, econ[inp_key], "From plant inputs", "User"
                    )

            scenario.assumptions = assumptions

            # Deserialise inputs
            known = {f for f in WastewaterInputs.__dataclass_fields__ if not f.startswith("_")}
            clean = {k: v for k, v in (scenario.domain_inputs or {}).items() if k in known}
            inputs = WastewaterInputs(**clean)

            iface = WastewaterDomainInterface(assumptions)
            calc  = iface.run_scenario(
                inputs=inputs,
                technology_sequence=scenario.treatment_pathway.technology_sequence,
                technology_parameters=scenario.treatment_pathway.technology_parameters,
            )

            iface.update_scenario_model(scenario, calc)
            update_current_project(project)
            pm.save(project)
            cache_calculation_result(calc)

            if calc.is_valid:
                st.success("✅ Calculations complete.")
            else:
                st.error("Calculation errors — check validation messages.")
            st.rerun()

        except Exception as e:
            st.error(f"Calculation error: {e}")
            import traceback
            st.code(traceback.format_exc())
