"""
apps/wastewater_app/pages/page_04c_biosolids.py

Biosolids and Sludge Management page.
Sits in the workflow between Aeration System (04b) and Comparison (05).
Covers sludge mass balance, digestion, methane recovery, and whole-plant carbon.
"""

from __future__ import annotations
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd

from apps.ui.session_state import (
    require_project, get_current_project, update_current_project,
    get_active_scenario, set_active_scenario,
)
from apps.ui.ui_components import render_page_header, render_scenario_selector
from core.project.project_manager import ProjectManager
from domains.wastewater.biosolids_orchestrator import (
    BiosolidsOrchestrator, biosolids_inputs_from_scenario, WholePlantCarbon,
)

DISPOSAL_OPTIONS = {
    "land_application": "Land Application",
    "landfill":         "Landfill",
    "composting":       "Composting",
    "incineration":     "Incineration",
    "pyrolysis":        "Pyrolysis / Thermal",
    "gasification":     "Gasification",
}
DEWATERING_OPTIONS = {
    "centrifuge":  "Centrifuge",
    "belt_press":  "Belt Filter Press",
    "screw_press": "Screw Press",
}


def render() -> None:
    render_page_header(
        "04c Biosolids & Sludge",
        "Mass balance, digestion, methane recovery, and whole-of-plant carbon footprint.",
    )
    require_project()

    project = get_current_project()
    pm = ProjectManager()

    selected_id = render_scenario_selector(project)
    if selected_id and selected_id != project.active_scenario_id:
        set_active_scenario(selected_id)
        project = get_current_project()

    scenario = get_active_scenario()
    if not scenario:
        return

    if not scenario.domain_inputs:
        st.warning("⚠️ Complete 02 Plant Inputs first.")
        return

    # Check that results have been calculated (need sludge production data)
    eng_summary = scenario.domain_specific_outputs.get("engineering_summary", {})
    sludge_kg_ds_day = eng_summary.get("total_sludge_kgds_day", 0.0)

    if sludge_kg_ds_day <= 0:
        st.warning(
            "⚠️ Run 04 Results first to calculate sludge production, "
            "then return here for biosolids modelling."
        )
        return

    # ── Load / init overrides ──────────────────────────────────────────────
    bio_key = f"biosolids_overrides_{scenario.scenario_id}"
    if bio_key not in st.session_state:
        st.session_state[bio_key] = {}
    overrides = st.session_state[bio_key]

    # Build inputs and run model
    bio_inputs = biosolids_inputs_from_scenario(
        domain_inputs=scenario.domain_inputs,
        tech_results_summary={"total_sludge_kgds_day": sludge_kg_ds_day},
        biosolids_overrides=overrides,
    )
    orchestrator = BiosolidsOrchestrator()
    bio_result   = orchestrator.run(bio_inputs)

    # Build whole-plant carbon
    wpc = orchestrator.aggregate_whole_plant(
        biosolids_result=bio_result,
        liquid_carbon_result=scenario.carbon_result,
        design_flow_mld=scenario.design_flow_mld or 1.0,
    )

    # Store results
    scenario.domain_specific_outputs["biosolids"] = bio_result.to_domain_outputs_dict()
    scenario.domain_specific_outputs["whole_plant_carbon"] = wpc.to_summary_dict()
    update_current_project(project)

    st.subheader(f"Biosolids: {scenario.scenario_name}")
    st.caption(
        f"Sludge production: **{sludge_kg_ds_day:,.0f} kg DS/day** "
        f"({sludge_kg_ds_day * 365 / 1000:.0f} t DS/yr) from biological treatment."
    )

    # ── Summary KPIs ──────────────────────────────────────────────────────
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Wet Cake",    f"{bio_result.sludge.cake_wet_t_yr:,.0f} t/yr")
    c2.metric("Methane Gen", f"{bio_result.digestion.biogas.ch4_m3_yr/1000:.0f}k m³/yr")
    c3.metric("CHP Output",  f"{bio_result.digestion.energy_recovery.electricity_kwh_yr/1000:.0f} MWh/yr")
    c4.metric("Sludge Cost", f"${bio_result.sludge.total_sludge_cost_yr/1000:.0f}k/yr")
    c5.metric("Net Solids Carbon", f"{bio_result.carbon.net_tco2e_yr:.0f} tCO₂e/yr")

    # ── Tabs ──────────────────────────────────────────────────────────────
    tab_mass, tab_dig, tab_methane, tab_carbon, tab_wpc, tab_config = st.tabs([
        "⚖️ Mass Balance", "🔬 Digestion", "🔥 Methane & CHP",
        "🌿 Solids Carbon", "🌍 Whole-Plant", "⚙️ Configuration"
    ])

    with tab_mass:
        _render_mass_balance(bio_result)

    with tab_dig:
        _render_digestion(bio_result)

    with tab_methane:
        _render_methane(bio_result)

    with tab_carbon:
        _render_solids_carbon(bio_result)

    with tab_wpc:
        _render_whole_plant_carbon(wpc, scenario)

    with tab_config:
        _render_config(overrides, bio_key, sludge_kg_ds_day)


# ── TAB RENDERERS ─────────────────────────────────────────────────────────────

def _render_mass_balance(r) -> None:
    st.subheader("Sludge Mass Balance")
    sl = r.sludge

    c1, c2 = st.columns(2)
    with c1:
        df = pd.DataFrame([
            {"Stage": "Raw sludge (DS)",    "t DS/yr": f"{sl.total_raw_ds_t_yr:,.0f}"},
            {"Stage": "Raw sludge (VS)",    "t DS/yr": f"{sl.total_raw_vs_t_yr:,.0f}"},
            {"Stage": "Thickened (wet)",    "t DS/yr": f"{sl.thickened_wet_t_yr:,.0f} t wet"},
            {"Stage": "VS destroyed",       "t DS/yr": f"{sl.vs_destroyed_t_yr:,.0f}"},
            {"Stage": "Digested (DS)",      "t DS/yr": f"{sl.digested_ds_t_yr:,.0f}"},
            {"Stage": f"Cake ({sl.dewatering_type})", "t DS/yr": f"{sl.cake_wet_t_yr:,.0f} t wet @ {sl.cake_ts_pct:.0f}% TS"},
        ])
        st.dataframe(df, use_container_width=True, hide_index=True)

    with c2:
        # Sankey-style bar showing mass reduction
        stages = ["Raw DS", "After Digestion", "Cake (DS)"]
        values = [sl.total_raw_ds_t_yr, sl.digested_ds_t_yr, sl.cake_ds_t_yr]
        fig = go.Figure(go.Bar(
            x=stages, y=values, marker_color=["#1f6aa5","#ff7f0e","#2ca02c"],
            text=[f"{v:,.0f}" for v in values], textposition="auto",
        ))
        fig.update_layout(yaxis_title="t DS/yr", plot_bgcolor="white", height=300,
                          title="Dry Solids — Mass Reduction Through Treatment")
        st.plotly_chart(fig, use_container_width=True)

    # Disposal summary
    st.divider()
    c3, c4 = st.columns(2)
    with c3:
        cost_df = pd.DataFrame([
            {"Item": "Disposal cost",    "Value": f"${sl.disposal_cost_yr:,.0f}/yr"},
            {"Item": "Transport cost",   "Value": f"${sl.transport_cost_yr:,.0f}/yr"},
            {"Item": "Total sludge cost","Value": f"${sl.total_sludge_cost_yr:,.0f}/yr"},
            {"Item": "Polymer use",      "Value": f"{sl.polymer_kg_yr/1000:.1f} t/yr"},
            {"Item": "Truck trips",      "Value": f"{sl.truck_trips_per_year:,.0f}/yr"},
        ])
        st.dataframe(cost_df, use_container_width=True, hide_index=True)
    with c4:
        st.markdown("**Calculation notes**")
        for note in sl.notes:
            st.caption(note)


def _render_digestion(r) -> None:
    if not r.sludge.digestion_included:
        st.info("Digestion not selected. Configure in the ⚙️ Configuration tab.")
        return

    st.subheader("Anaerobic Digestion Performance")
    dig = r.digestion

    c1, c2 = st.columns(2)
    with c1:
        df = pd.DataFrame([
            {"Parameter": "Feed DS",             "Value": f"{dig.inputs_used.get('feed_ds_t_yr',0):,.0f} t DS/yr"},
            {"Parameter": "Feed VS",             "Value": f"{dig.inputs_used.get('feed_vs_t_yr',0):,.0f} t VS/yr"},
            {"Parameter": "VS destruction",      "Value": f"{dig.vs_destruction_pct:.0f}%"},
            {"Parameter": "VS destroyed",        "Value": f"{dig.vs_destroyed_t_yr:,.0f} t VS/yr"},
            {"Parameter": "Digested DS",         "Value": f"{dig.digested_ds_t_yr:,.0f} t DS/yr"},
            {"Parameter": "Biogas yield",        "Value": f"{dig.inputs_used.get('biogas_yield_m3_per_kg_vs',0):.2f} m³/kg VS"},
            {"Parameter": "CH₄ fraction",        "Value": f"{dig.inputs_used.get('biogas_ch4_fraction',0)*100:.0f}%"},
            {"Parameter": "Total biogas",        "Value": f"{dig.biogas.biogas_m3_yr/1000:.0f}k m³/yr"},
            {"Parameter": "CH₄ generated",       "Value": f"{dig.biogas.ch4_m3_yr/1000:.0f}k m³/yr"},
            {"Parameter": "CH₄ energy content",  "Value": f"{dig.biogas.ch4_energy_kwh_yr/1000:.0f} MWh/yr"},
        ])
        st.dataframe(df, use_container_width=True, hide_index=True)
    with c2:
        for note in dig.notes[:5]:
            st.caption(note)


def _render_methane(r) -> None:
    if not r.sludge.digestion_included:
        st.info("Digestion not selected.")
        return

    st.subheader("Methane Pathways and Energy Recovery")
    mp = r.digestion.methane_pathways
    er = r.digestion.energy_recovery

    # Pathway pie chart
    col1, col2 = st.columns(2)
    with col1:
        labels = ["To CHP", "Flared", "Fugitive"]
        values = [mp.ch4_to_chp_m3_yr, mp.ch4_to_flare_m3_yr, mp.ch4_total_fugitive_m3_yr]
        colours = ["#2ca02c", "#ff7f0e", "#d62728"]
        fig = go.Figure(go.Pie(
            labels=labels, values=values, marker_colors=colours,
            textinfo="label+percent",
        ))
        fig.update_layout(title="CH₄ Pathway Allocation", height=300)
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        energy_df = pd.DataFrame([
            {"Metric": "CH₄ to CHP",              "Value": f"{mp.ch4_to_chp_m3_yr/1000:.0f}k m³/yr"},
            {"Metric": "Electricity generated",   "Value": f"{er.electricity_kwh_yr/1000:.0f} MWh/yr"},
            {"Metric": "Heat recovered",          "Value": f"{er.heat_kwh_yr/1000:.0f} MWh/yr"},
            {"Metric": "Average CHP output",      "Value": f"{er.electricity_kw_avg:.0f} kW"},
            {"Metric": "CHP installed capacity",  "Value": f"{er.chp_capacity_kw:.0f} kW"},
            {"Metric": "Avoided grid emissions",  "Value": f"{er.avoided_grid_co2e_t_yr:.0f} tCO₂e/yr"},
            {"Metric": "CH₄ flared",              "Value": f"{mp.ch4_to_flare_m3_yr/1000:.1f}k m³/yr"},
            {"Metric": "CH₄ fugitive",            "Value": f"{mp.ch4_total_fugitive_m3_yr/1000:.1f}k m³/yr"},
            {"Metric": "Fugitive emissions",      "Value": f"{r.digestion.fugitive_ch4_tco2e_yr:.1f} tCO₂e/yr"},
        ])
        st.dataframe(energy_df, use_container_width=True, hide_index=True)


def _render_solids_carbon(r) -> None:
    st.subheader("Biosolids Carbon Footprint")
    bc = r.carbon

    # Stacked bar: gross emissions and avoided
    c1, c2 = st.columns(2)
    with c1:
        sources = list(bc.emission_source_breakdown.keys())
        values  = list(bc.emission_source_breakdown.values())
        colours = ["#2ca02c" if v < 0 else "#d62728" for v in values]
        fig = go.Figure(go.Bar(
            x=values, y=sources, orientation="h",
            marker_color=colours,
            text=[f"{v:+.1f}" for v in values], textposition="auto",
        ))
        fig.add_vline(x=0, line_color="black", line_width=1)
        fig.update_layout(yaxis_title="", xaxis_title="tCO₂e/yr",
                          title="Emission Sources (red=emissions, green=credits)",
                          plot_bgcolor="white", height=max(300, 35*len(sources)))
        st.plotly_chart(fig, use_container_width=True)

    with c2:
        summary_df = pd.DataFrame([
            {"Category": "Scope 1 (direct)",     "tCO₂e/yr": f"{bc.total_scope1_tco2e_yr:,.1f}"},
            {"Category": "Scope 2 (electricity)","tCO₂e/yr": f"{bc.total_scope2_tco2e_yr:,.1f}"},
            {"Category": "Scope 3 (upstream)",   "tCO₂e/yr": f"{bc.total_scope3_tco2e_yr:,.1f}"},
            {"Category": "GROSS TOTAL",           "tCO₂e/yr": f"{bc.total_gross_tco2e_yr:,.1f}"},
            {"Category": "Avoided (all)",         "tCO₂e/yr": f"−{bc.total_avoided_tco2e_yr:,.1f}"},
            {"Category": "NET TOTAL",             "tCO₂e/yr": f"{bc.net_tco2e_yr:,.1f}"},
            {"Category": "NET 30-year",           "tCO₂e/yr": f"{bc.net_tco2e_30yr:,.0f} total"},
        ])
        st.dataframe(summary_df, use_container_width=True, hide_index=True)
        st.caption(
            "⚠️ Screening-level estimates. Emission factors are default IPCC/EPA values. "
            "Site-specific data should be used at detailed design stage."
        )


def _render_whole_plant_carbon(wpc: WholePlantCarbon, scenario) -> None:
    st.subheader("Whole-of-Plant Carbon Footprint")
    st.markdown("Liquid line + solids line combined.")

    c1, c2 = st.columns(2)
    with c1:
        # Stacked bar: liquid vs solids contribution
        fig = go.Figure()
        for label, ll_val, sl_val, colour in [
            ("Scope 1", wpc.ll_scope1_tco2e_yr, wpc.sl_scope1_tco2e_yr, ["#d62728","#ff7f0e"]),
            ("Scope 2", wpc.ll_scope2_tco2e_yr, wpc.sl_scope2_tco2e_yr, ["#1f6aa5","#aec7e8"]),
            ("Scope 3", wpc.ll_scope3_tco2e_yr, wpc.sl_scope3_tco2e_yr, ["#9467bd","#c5b0d5"]),
        ]:
            fig.add_trace(go.Bar(name=f"{label} Liquid", x=[label], y=[ll_val], marker_color=colour[0]))
            fig.add_trace(go.Bar(name=f"{label} Solids", x=[label], y=[sl_val], marker_color=colour[1]))

        fig.update_layout(barmode="stack", yaxis_title="tCO₂e/yr",
                          plot_bgcolor="white", height=350,
                          title="Gross Emissions: Liquid vs Solids Line",
                          legend=dict(orientation="h", y=-0.3))
        st.plotly_chart(fig, use_container_width=True)

    with c2:
        wpc_df = pd.DataFrame([
            {"Item": "Liquid line gross",     "tCO₂e/yr": f"{wpc.ll_scope1_tco2e_yr+wpc.ll_scope2_tco2e_yr+wpc.ll_scope3_tco2e_yr:,.0f}"},
            {"Item": "Solids line gross",     "tCO₂e/yr": f"{wpc.sl_scope1_tco2e_yr+wpc.sl_scope2_tco2e_yr+wpc.sl_scope3_tco2e_yr:,.0f}"},
            {"Item": "TOTAL GROSS",           "tCO₂e/yr": f"{wpc.total_gross_tco2e_yr:,.0f}"},
            {"Item": "Liquid avoided",        "tCO₂e/yr": f"−{wpc.ll_avoided_tco2e_yr:,.0f}"},
            {"Item": "Solids avoided (CHP)",  "tCO₂e/yr": f"−{wpc.sl_avoided_tco2e_yr:,.0f}"},
            {"Item": "TOTAL AVOIDED",         "tCO₂e/yr": f"−{wpc.total_avoided_tco2e_yr:,.0f}"},
            {"Item": "NET TOTAL",             "tCO₂e/yr": f"{wpc.total_net_tco2e_yr:,.0f}"},
            {"Item": "NET 30-year",           "tCO₂e/yr": f"{wpc.net_tco2e_30yr:,.0f} total"},
            {"Item": "kg CO₂e / ML (net)",   "tCO₂e/yr": f"{wpc.kg_co2e_per_ml_net:.1f}"},
        ])
        st.dataframe(wpc_df, use_container_width=True, hide_index=True)

    if not scenario.carbon_result:
        st.info("💡 Run 04 Results first to populate the liquid line emissions.")


def _render_config(overrides: dict, key: str, sludge_kg_ds_day: float) -> None:
    st.subheader("Biosolids Configuration")
    st.markdown(
        "Configure sludge treatment assumptions. Changes are applied immediately."
    )

    with st.form("biosolids_config_form"):
        st.markdown("#### Sludge treatment train")
        c1, c2 = st.columns(2)
        with c1:
            digestion = st.checkbox("Include anaerobic digestion",
                value=overrides.get("digestion_included", True))
            chp = st.checkbox("Include CHP (biogas to electricity)",
                value=overrides.get("chp_enabled", True))
            vs_dest = st.slider("VS destruction (%)", 40, 75,
                int(overrides.get("vs_destruction_pct", 58)))
            vs_frac = st.slider("Volatile solids fraction (%)", 65, 90,
                int(overrides.get("secondary_vs_fraction", 0.80) * 100)) / 100
        with c2:
            dewatering = st.selectbox("Dewatering type",
                list(DEWATERING_OPTIONS.keys()),
                format_func=lambda x: DEWATERING_OPTIONS[x],
                index=list(DEWATERING_OPTIONS.keys()).index(
                    overrides.get("dewatering_type", "centrifuge")))
            disposal = st.selectbox("Disposal pathway",
                list(DISPOSAL_OPTIONS.keys()),
                format_func=lambda x: DISPOSAL_OPTIONS[x],
                index=list(DISPOSAL_OPTIONS.keys()).index(
                    overrides.get("disposal_pathway", "land_application")))
            transport_km = st.number_input("Transport distance (km)",
                10.0, 500.0, float(overrides.get("transport_distance_km", 50.0)), 10.0)

        st.markdown("#### Methane and CHP parameters")
        c3, c4 = st.columns(2)
        with c3:
            capture_eff = st.slider("Methane capture efficiency (%)", 70, 99,
                int(overrides.get("methane_capture_efficiency", 0.95) * 100)) / 100
            flare_frac  = st.slider("Flare fraction of captured gas (%)", 0, 30,
                int(overrides.get("flare_fraction", 0.05) * 100)) / 100
        with c4:
            fugitive    = st.slider("Fugitive CH₄ loss (%)", 0, 10,
                int(overrides.get("cover_fugitive_fraction", 0.015) * 100)) / 100
            chp_eff     = st.slider("CHP electrical efficiency (%)", 25, 50,
                int(overrides.get("chp_electrical_efficiency", 0.38) * 100)) / 100

        st.markdown("#### Carbon accounting options")
        c5, c6 = st.columns(2)
        with c5:
            incl_n2o   = st.checkbox("Include land application N₂O",
                value=overrides.get("include_land_application_n2o", True))
            incl_lfch4 = st.checkbox("Include landfill CH₄",
                value=overrides.get("include_landfill_ch4", True))
        with c6:
            incl_chp   = st.checkbox("Credit CHP electricity (avoided grid)",
                value=overrides.get("include_chp_electricity_credit", True))
            incl_bio   = st.checkbox("Include biochar sequestration credit (pyrolysis only)",
                value=overrides.get("include_biochar_credit", False))

        save = st.form_submit_button("Apply Configuration", type="primary", use_container_width=True)

    if save:
        st.session_state[key] = {
            "digestion_included":            digestion,
            "chp_enabled":                   chp,
            "vs_destruction_pct":            float(vs_dest),
            "secondary_vs_fraction":         vs_frac,
            "dewatering_type":               dewatering,
            "disposal_pathway":              disposal,
            "transport_distance_km":         transport_km,
            "methane_capture_efficiency":    capture_eff,
            "flare_fraction":                flare_frac,
            "cover_fugitive_fraction":       fugitive,
            "chp_electrical_efficiency":     chp_eff,
            "include_land_application_n2o":  incl_n2o,
            "include_landfill_ch4":          incl_lfch4,
            "include_biochar_credit":        incl_bio,
        }
        st.success("✅ Configuration applied.")
        st.rerun()
