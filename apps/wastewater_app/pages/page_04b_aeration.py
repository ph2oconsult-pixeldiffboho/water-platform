"""
apps/wastewater_app/pages/page_04b_aeration.py

Aeration System Design page.
Sits between Results (04) and Comparison (05) in the workflow.
Provides detailed aeration modelling, blower sizing, and sensitivity analysis.
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
from domains.wastewater.aeration_model import (
    AerationModel, AerationInputs, AerationModelResult,
    run_sensitivity, aeration_inputs_from_scenario,
)


def render() -> None:
    render_page_header(
        "04b Aeration System",
        "Oxygen demand, blower sizing, energy intensity and sensitivity analysis.",
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
        st.warning("⚠️ Complete 02 Plant Inputs before running the aeration model.")
        return

    # ── Technology-specific guidance ──────────────────────────────────────
    tech_seq = scenario.treatment_pathway.technology_sequence if scenario.treatment_pathway else []
    anaerobic_only = all(c in {"anmbr", "ad_chp", "thermal_biosolids"} for c in tech_seq)
    has_mabr = "mabr_bnr" in tech_seq

    if anaerobic_only:
        st.info(
            "ℹ️ **Anaerobic process selected.** This scenario does not use diffused aeration. "
            "The aeration model below shows what would be required if the process were aerobic — "
            "for reference only. For energy outputs of anaerobic processes, see the Results page."
        )
    elif has_mabr:
        st.info(
            "ℹ️ **MABR scenario:** The MABR uses bubble-free O₂ delivery through hollow-fibre "
            "membranes — not conventional blowers. The model below shows the equivalent O₂ demand "
            "and gas supply energy, but blower sizing does not apply. "
            "MABR aeration energy is ~88% lower than conventional BNR for the same O₂ demand."
        )

    # Load aeration overrides from session state (not saved to project — live UI)
    aeration_key = f"aeration_overrides_{scenario.scenario_id}"
    if aeration_key not in st.session_state:
        st.session_state[aeration_key] = {}

    overrides = st.session_state[aeration_key]

    # ── Always inject fresh O₂ from the technology module ────────────────
    # Never trust stored domain_specific_outputs — they may be stale from a
    # previous technology selection (e.g. old mbr returning 3,657 kg/d).
    # Run the module directly every render using the current treatment pathway.
    tech_o2 = 0.0
    if scenario.treatment_pathway and scenario.domain_inputs:
        try:
            from core.assumptions.assumptions_manager import AssumptionsManager
            from core.project.project_model import DomainType
            from domains.wastewater.domain_interface import (
                TECHNOLOGY_REGISTRY, TECHNOLOGY_INPUT_CLASSES,
            )
            _a = AssumptionsManager().load_defaults(DomainType.WASTEWATER)
            _flow = scenario.domain_inputs.get("design_flow_mld", 10.0)
            for tc in scenario.treatment_pathway.technology_sequence:
                if tc in TECHNOLOGY_REGISTRY:
                    _r = TECHNOLOGY_REGISTRY[tc](_a).calculate(
                        _flow, TECHNOLOGY_INPUT_CLASSES[tc](),
                    )
                    tech_o2 += _r.performance.additional.get("o2_demand_kg_day", 0) or 0
        except Exception:
            pass  # Fall through to aeration model's own O₂ calculation

    if tech_o2 > 0:
        overrides["o2_demand_override_kg_day"] = tech_o2

    # ── Technology-specific SAE overrides ────────────────────────────────
    # MABR: effective SAE = 1.8 × (OTE_MABR 0.95 / OTE_conv 0.20) = 8.55
    # Always set/clear based on current technology — never leave stale values.
    if "mabr_bnr" in tech_seq:
        overrides["standard_aeration_efficiency_kg_o2_kwh"] = 8.55
        overrides["alpha_factor"] = 1.0
    else:
        overrides.pop("standard_aeration_efficiency_kg_o2_kwh", None)
        overrides.pop("alpha_factor", None)

    # ── Build AerationInputs from scenario ───────────────────────────────
    tech_params = {}
    if scenario.treatment_pathway:
        for code in scenario.treatment_pathway.technology_sequence:
            tech_params.update(
                scenario.treatment_pathway.technology_parameters.get(code, {})
            )

    aeration_inp = aeration_inputs_from_scenario(
        scenario.domain_inputs, tech_params, overrides
    )

    # ── Run the model ─────────────────────────────────────────────────────
    model = AerationModel()
    result = model.calculate(aeration_inp)

    # Store in domain_specific_outputs for comparison page
    scenario.domain_specific_outputs["aeration"] = result.to_summary_dict()
    update_current_project(project)

    st.subheader(f"Aeration: {scenario.scenario_name}")

    # ── SUMMARY METRICS ROW ───────────────────────────────────────────────
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("O₂ Demand (avg)", f"{result.oxygen_demand.o2_total_avg_kg_day:,.0f} kg/d")
    c2.metric("Peak Airflow",    f"{result.airflow.peak_airflow_nm3_hr:,.0f} Nm³/h")
    c3.metric("Blower Power",    f"{result.blower.total_duty_power_avg_kw:,.0f} kW",
              help="Average duty blower power")
    c4.metric("Blower kWh/ML",  f"{result.energy_intensity.kwh_per_ml_treated:,.0f}",
              help="Blower (aeration) energy only — not total plant. See Results page for total plant kWh/ML.")
    c5.metric("kWh/kg NH₄",     f"{result.energy_intensity.kwh_per_kg_nh4_removed:.2f}",
              help="Blower energy per kg NH₄-N removed")

    # ── Total plant energy cross-reference ────────────────────────────────
    total_kwh_ml = scenario.domain_specific_outputs.get(
        "engineering_summary", {}
    ).get("specific_energy_kwh_kl", 0) or 0
    if total_kwh_ml > 0:
        blower_kwh_ml = result.energy_intensity.kwh_per_ml_treated / 1000  # convert to kWh/kL
        blower_frac = blower_kwh_ml / total_kwh_ml * 100 if total_kwh_ml > 0 else 0
        st.caption(
            f"ℹ️ **Blower energy = {result.energy_intensity.kwh_per_ml_treated:,.0f} kWh/ML** "
            f"({blower_frac:.0f}% of total plant {total_kwh_ml*1000:,.0f} kWh/ML). "
            "Difference = mixing, RAS, screening, and other auxiliaries. "
            "See **Results page** for total plant energy breakdown."
        )

    # Config warning
    if not result.blower.configuration_adequate:
        st.error(f"⚠️ Blower configuration issue: {result.blower.configuration_warning}")
    else:
        st.success(
            f"✅ Blower configuration adequate: **{result.blower.configuration_description}**  |  "
            f"Performance: **{result.energy_intensity.performance_band}**"
        )

    # ── TABS ──────────────────────────────────────────────────────────────
    tab_loads, tab_o2, tab_blower, tab_energy, tab_sensitivity, tab_config, tab_notes = st.tabs([
        "📊 Loads", "🫧 O₂ Demand", "💨 Blower Sizing",
        "⚡ Energy Intensity", "🔄 Sensitivity", "⚙️ Configuration", "📋 Notes"
    ])

    with tab_loads:
        _render_loads_tab(result)

    with tab_o2:
        _render_o2_tab(result)

    with tab_blower:
        _render_blower_tab(result, aeration_inp)

    with tab_energy:
        _render_energy_tab(result)

    with tab_sensitivity:
        _render_sensitivity_tab(aeration_inp)

    with tab_config:
        _render_config_tab(aeration_inp, overrides, aeration_key, st.session_state)

    with tab_notes:
        st.subheader("Calculation Notes (Engineering Transparency)")
        for i, note in enumerate(result.notes, 1):
            st.markdown(f"**{i}.** {note}")
        st.divider()
        st.subheader("Assumptions Used")
        st.dataframe(
            pd.DataFrame([
                {"Parameter": k, "Value": v}
                for k, v in result.inputs_used.items()
            ]),
            use_container_width=True, hide_index=True
        )


# ── TAB RENDERERS ─────────────────────────────────────────────────────────────

def _render_loads_tab(r: AerationModelResult) -> None:
    st.subheader("Influent Loads")

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Average (design) loads**")
        loads_df = pd.DataFrame([
            {"Parameter": "Design Flow", "Value": f"{r.loads.design_flow_mld:.1f} ML/day"},
            {"Parameter": "BOD Load",    "Value": f"{r.loads.bod_load_kg_day:,.0f} kg/day"},
            {"Parameter": "NH₄-N Load",  "Value": f"{r.loads.nh4_load_kg_day:,.0f} kg/day"},
            {"Parameter": "TKN Load",    "Value": f"{r.loads.tkn_load_kg_day:,.0f} kg/day"},
            {"Parameter": "BOD Removed", "Value": f"{r.loads.bod_removed_kg_day:,.0f} kg/day"},
            {"Parameter": "NH₄-N Removed","Value": f"{r.loads.nh4_removed_kg_day:,.0f} kg/day"},
        ])
        st.dataframe(loads_df, use_container_width=True, hide_index=True)

    with c2:
        st.markdown("**Peak loads (for blower sizing)**")
        peak_df = pd.DataFrame([
            {"Parameter": "Peak Flow",        "Value": f"{r.loads.peak_flow_mld:.1f} ML/day"},
            {"Parameter": "Peak BOD Load",    "Value": f"{r.loads.peak_bod_load_kg_day:,.0f} kg/day"},
            {"Parameter": "Peak NH₄-N Load",  "Value": f"{r.loads.peak_nh4_load_kg_day:,.0f} kg/day"},
        ])
        st.dataframe(peak_df, use_container_width=True, hide_index=True)

    # Load bar chart
    fig = go.Figure(go.Bar(
        x=["BOD Load", "NH₄-N Load", "TKN Load"],
        y=[r.loads.bod_load_kg_day, r.loads.nh4_load_kg_day, r.loads.tkn_load_kg_day],
        marker_color=["#1f6aa5", "#ff7f0e", "#2ca02c"],
        text=[f"{v:,.0f}" for v in [r.loads.bod_load_kg_day, r.loads.nh4_load_kg_day, r.loads.tkn_load_kg_day]],
        textposition="auto",
    ))
    fig.update_layout(yaxis_title="kg/day", plot_bgcolor="white", height=280,
                      title="Average Daily Influent Loads")
    st.plotly_chart(fig, use_container_width=True)


def _render_o2_tab(r: AerationModelResult) -> None:
    st.subheader("Oxygen Demand Breakdown")

    c1, c2 = st.columns(2)
    with c1:
        o2_df = pd.DataFrame([
            {"Component": "BOD removal (1.1 × BOD_removed)",            "kg O₂/day": f"{r.oxygen_demand.o2_bod_kg_day:,.0f}"},
            {"Component": "Nitrification (4.57 × NH₄_removed)",         "kg O₂/day": f"{r.oxygen_demand.o2_nitrification_kg_day:,.0f}"},
            {"Component": "Denitrification credit (−2.86 × NO₃_denit)", "kg O₂/day": f"−{r.oxygen_demand.o2_denitrification_credit_kg_day:,.0f}"},
            {"Component": "Total — average",                             "kg O₂/day": f"{r.oxygen_demand.o2_total_avg_kg_day:,.0f}"},
            {"Component": "Total — peak",                                "kg O₂/day": f"{r.oxygen_demand.o2_total_peak_kg_day:,.0f}"},
        ])
        st.dataframe(o2_df, use_container_width=True, hide_index=True)

        st.markdown("**O₂ transfer correction**")
        transfer_df = pd.DataFrame([
            {"Parameter": "SOTE",                           "Value": f"{r.transfer.sote*100:.1f}%"},
            {"Parameter": "α (alpha factor)",               "Value": f"{r.inputs_used.get('alpha_factor', '—'):.2f}"},
            {"Parameter": "F (fouling factor)",             "Value": f"{r.inputs_used.get('fouling_factor', '—'):.2f}"},
            {"Parameter": "β (beta factor)",                "Value": f"{r.inputs_used.get('beta_factor', '—'):.2f}"},
            {"Parameter": "DO deficit correction",          "Value": f"{r.transfer.do_deficit_correction:.3f}"},
            {"Parameter": "Temperature correction θᵀ⁻²⁰",  "Value": f"{r.transfer.temperature_correction:.3f}"},
            {"Parameter": "Overall correction factor",      "Value": f"{r.transfer.correction_factor:.3f}"},
        ])
        st.dataframe(transfer_df, use_container_width=True, hide_index=True)

    with c2:
        # Waterfall chart
        labels = ["BOD\nRemoval", "Nitrification", "Denitrification\nCredit", "Net O₂\nDemand (avg)", "Net O₂\nDemand (peak)"]
        values = [
            r.oxygen_demand.o2_bod_kg_day,
            r.oxygen_demand.o2_nitrification_kg_day,
            -r.oxygen_demand.o2_denitrification_credit_kg_day,
            r.oxygen_demand.o2_total_avg_kg_day,
            r.oxygen_demand.o2_total_peak_kg_day,
        ]
        colours = ["#1f6aa5", "#ff7f0e", "#2ca02c", "#7f7f7f", "#d62728"]
        fig = go.Figure(go.Bar(
            x=labels, y=values, marker_color=colours,
            text=[f"{abs(v):,.0f}" for v in values], textposition="auto",
        ))
        fig.update_layout(yaxis_title="kg O₂/day", plot_bgcolor="white", height=380,
                          title="Oxygen Demand Breakdown")
        st.plotly_chart(fig, use_container_width=True)


def _render_blower_tab(r: AerationModelResult, inp: AerationInputs) -> None:
    st.subheader("Blower Sizing")

    c1, c2 = st.columns(2)
    with c1:
        airflow_df = pd.DataFrame([
            {"Parameter": "Average airflow",          "Value": f"{r.airflow.avg_airflow_nm3_hr:,.0f} Nm³/h"},
            {"Parameter": "Peak airflow",             "Value": f"{r.airflow.peak_airflow_nm3_hr:,.0f} Nm³/h"},
            {"Parameter": "Avg airflow (per blower)", "Value": f"{r.airflow.avg_airflow_nm3_hr/inp.num_duty_blowers:,.0f} Nm³/h"},
            {"Parameter": "Specific air rate",        "Value": f"{r.airflow.sair_ratio:.1f} Nm³/m³ treated"},
        ])
        st.dataframe(airflow_df, use_container_width=True, hide_index=True)

    with c2:
        pressure_df = pd.DataFrame([
            {"Parameter": "Inlet pressure",           "Value": f"{r.blower.inlet_pressure_kpa:.1f} kPa"},
            {"Parameter": "Discharge pressure",       "Value": f"{r.blower.discharge_pressure_kpa:.1f} kPa"},
            {"Parameter": "Pressure ratio P₂/P₁",    "Value": f"{r.blower.pressure_ratio:.3f}"},
        ])
        st.dataframe(pressure_df, use_container_width=True, hide_index=True)

    st.divider()
    st.markdown("**Blower power and configuration**")

    blower_df = pd.DataFrame([
        {"Parameter": "Avg power per duty blower",    "Value": f"{r.blower.avg_power_per_blower_kw:.1f} kW"},
        {"Parameter": "Peak power per duty blower",   "Value": f"{r.blower.peak_power_per_blower_kw:.1f} kW"},
        {"Parameter": "Total avg duty power",         "Value": f"{r.blower.total_duty_power_avg_kw:.1f} kW"},
        {"Parameter": "Total peak duty power",        "Value": f"{r.blower.total_duty_power_peak_kw:.1f} kW"},
        {"Parameter": "Recommended motor size",       "Value": f"{r.blower.recommended_motor_kw:.0f} kW"},
        {"Parameter": "Configuration",                "Value": r.blower.configuration_description},
        {"Parameter": "Total installed power",        "Value": f"{r.blower.total_installed_power_kw:.0f} kW"},
        {"Parameter": "Annual aeration energy",       "Value": f"{r.blower.annual_aeration_energy_mwh:.0f} MWh/yr"},
        {"Parameter": "Configuration adequate",       "Value": "✅ Yes" if r.blower.configuration_adequate else "❌ No"},
    ])
    st.dataframe(blower_df, use_container_width=True, hide_index=True)

    # Power bar chart
    fig = go.Figure()
    fig.add_trace(go.Bar(
        name="Avg duty power", x=["Blower configuration"],
        y=[r.blower.total_duty_power_avg_kw], marker_color="#1f6aa5",
    ))
    fig.add_trace(go.Bar(
        name="Peak duty power", x=["Blower configuration"],
        y=[r.blower.total_duty_power_peak_kw], marker_color="#ff7f0e",
    ))
    fig.add_trace(go.Bar(
        name="Total installed", x=["Blower configuration"],
        y=[r.blower.total_installed_power_kw], marker_color="#7f7f7f",
    ))
    fig.update_layout(barmode="group", yaxis_title="kW",
                      plot_bgcolor="white", height=320, title="Blower Power Summary")
    st.plotly_chart(fig, use_container_width=True)


def _render_energy_tab(r: AerationModelResult) -> None:
    st.subheader("Energy Intensity Metrics")

    c1, c2 = st.columns([2, 1])
    with c1:
        energy_df = pd.DataFrame([
            {"Metric": "kWh/ML treated",               "Value": f"{r.energy_intensity.kwh_per_ml_treated:,.0f}", "Unit": "kWh/ML"},
            {"Metric": "kWh/kg NH₄-N removed",         "Value": f"{r.energy_intensity.kwh_per_kg_nh4_removed:.2f}", "Unit": "kWh/kg N"},
            {"Metric": "kWh/kg BOD removed",            "Value": f"{r.energy_intensity.kwh_per_kg_bod_removed:.3f}", "Unit": "kWh/kg BOD"},
            {"Metric": "kWh/kg O₂ transferred",        "Value": f"{r.energy_intensity.kwh_per_kg_o2_transferred:.3f}", "Unit": "kWh/kg O₂"},
            {"Metric": "Energy guarantee (peak NH₄)",  "Value": f"{r.energy_intensity.kwh_per_kg_nh4_peak:.2f}", "Unit": "kWh/kg N"},
            {"Metric": "Performance band",             "Value": r.energy_intensity.performance_band, "Unit": ""},
        ])
        st.dataframe(energy_df, use_container_width=True, hide_index=True)

    with c2:
        # Gauge chart for kWh/ML
        kwh_ml = r.energy_intensity.kwh_per_ml_treated
        fig = go.Figure(go.Indicator(
            mode="gauge+number",
            value=kwh_ml,
            title={"text": "kWh/ML Treated"},
            gauge={
                "axis": {"range": [0, 1000]},
                "bar":  {"color": "#1f6aa5"},
                "steps": [
                    {"range": [0,   200], "color": "#2ca02c"},
                    {"range": [200, 400], "color": "#90d575"},
                    {"range": [400, 600], "color": "#ffdd57"},
                    {"range": [600, 900], "color": "#ff7f0e"},
                    {"range": [900,1000], "color": "#d62728"},
                ],
                "threshold": {"line": {"color": "black", "width": 3}, "value": kwh_ml},
            },
        ))
        fig.update_layout(height=280, margin=dict(l=20, r=20, t=40, b=20))
        st.plotly_chart(fig, use_container_width=True)

    # Benchmark reference table
    st.markdown("**Industry benchmark reference**")
    bench_df = pd.DataFrame([
        {"Band": "Excellent",     "kWh/ML Range": "< 200",    "Context": "Top 10% of plants globally"},
        {"Band": "Good",          "kWh/ML Range": "200–400",  "Context": "Modern, well-operated BNR/MBR"},
        {"Band": "Average",       "kWh/ML Range": "400–600",  "Context": "Typical municipal activated sludge"},
        {"Band": "Below average", "kWh/ML Range": "600–900",  "Context": "Older plants, limited VFDs"},
        {"Band": "Poor",          "kWh/ML Range": "> 900",    "Context": "Energy optimisation recommended"},
    ])
    st.dataframe(bench_df, use_container_width=True, hide_index=True)
    st.caption("Source: WEF Energy Conservation in Water and Wastewater Facilities (2009); "
               "Australian Water Association benchmarking data.")


def _render_sensitivity_tab(base_inp: AerationInputs) -> None:
    st.subheader("Sensitivity Analysis")
    st.markdown(
        "Adjust one parameter at a time to see how it affects blower power and energy intensity. "
        "All other parameters are held at base case values."
    )

    col1, col2 = st.columns(2)
    with col1:
        param = st.selectbox("Parameter to vary", [
            "influent_nh4_mg_l",
            "design_flow_mld",
            "alpha_factor",
            "diffuser_submergence_m",
            "blower_efficiency",
            "sote_per_metre_submergence",
            "denitrification_fraction",
        ], format_func=lambda x: {
            "influent_nh4_mg_l":          "Influent NH₄-N (mg/L)",
            "design_flow_mld":            "Design Flow (ML/day)",
            "alpha_factor":               "Alpha factor (α)",
            "diffuser_submergence_m":     "Diffuser submergence (m)",
            "blower_efficiency":          "Blower efficiency",
            "sote_per_metre_submergence": "SOTE per metre (%/m)",
            "denitrification_fraction":   "Denitrification fraction",
        }.get(x, x))

    with col2:
        param_ranges = {
            "influent_nh4_mg_l":          (10.0,  60.0,  10.0),
            "design_flow_mld":            (2.0,   50.0,  5.0),
            "alpha_factor":               (0.35,  0.75,  0.05),
            "diffuser_submergence_m":     (3.0,   7.0,   0.5),
            "blower_efficiency":          (0.55,  0.85,  0.05),
            "sote_per_metre_submergence": (0.030, 0.070, 0.005),
            "denitrification_fraction":   (0.0,   0.8,   0.1),
        }
        lo, hi, step = param_ranges[param]
        rng = st.slider(
            "Range", min_value=float(lo), max_value=float(hi),
            value=(float(lo), float(hi)), step=float(step),
        )

    import numpy as np
    n_steps = 8
    values = list(np.linspace(rng[0], rng[1], n_steps))
    sens = run_sensitivity(base_inp, param, values)

    # Two-panel chart
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=sens["values"], y=sens["blower_power_kw"],
        name="Avg Blower Power (kW)", line=dict(color="#1f6aa5", width=2),
        yaxis="y1",
    ))
    fig.add_trace(go.Scatter(
        x=sens["values"], y=sens["kwh_per_ml"],
        name="kWh/ML Treated", line=dict(color="#ff7f0e", width=2, dash="dot"),
        yaxis="y2",
    ))
    # Mark base case
    base_val = getattr(base_inp, param)
    fig.add_vline(x=base_val, line_dash="dash", line_color="grey",
                  annotation_text="Base case")

    fig.update_layout(
        title=f"Sensitivity: {param}",
        xaxis_title=param.replace("_", " "),
        yaxis=dict(title=dict(text="Blower Power (kW)", font=dict(color="#1f6aa5"))),
        yaxis2=dict(title=dict(text="kWh/ML", font=dict(color="#ff7f0e")),
                    overlaying="y", side="right"),
        plot_bgcolor="white", height=380,
        showlegend=True,
        legend=dict(orientation="h", y=-0.2),
    )
    st.plotly_chart(fig, use_container_width=True)

    # Table
    sens_df = pd.DataFrame({
        param.replace("_"," "): [round(v, 4) for v in sens["values"]],
        "O₂ Demand (kg/d)":     [round(v, 0) for v in sens["o2_demand_kg_day"]],
        "Blower Power (kW)":    [round(v, 1) for v in sens["blower_power_kw"]],
        "kWh/ML":               [round(v, 0) for v in sens["kwh_per_ml"]],
        "kWh/kg NH₄":           [round(v, 2) for v in sens["kwh_per_kg_nh4"]],
        "Annual Energy (MWh)":  [round(v, 0) for v in sens["annual_energy_mwh"]],
    })
    st.dataframe(sens_df, use_container_width=True, hide_index=True)


def _render_config_tab(
    inp: AerationInputs, overrides: dict, key: str, session: dict
) -> None:
    st.subheader("Aeration System Configuration")
    st.markdown(
        "Override default aeration parameters for this scenario. "
        "Changes are applied immediately and reflected in all tabs above."
    )

    with st.form("aeration_config_form"):
        st.markdown("#### Oxygen transfer parameters")
        c1, c2, c3 = st.columns(3)
        with c1:
            alpha = st.number_input("Alpha factor (α)", 0.30, 0.90,
                overrides.get("alpha_factor", inp.alpha_factor), 0.01,
                help="Process water vs clean water O₂ transfer ratio. "
                     "Typical fine bubble municipal: 0.45–0.65")
            beta  = st.number_input("Beta factor (β)", 0.85, 1.00,
                overrides.get("beta_factor", inp.beta_factor), 0.01,
                help="Process water vs clean water O₂ saturation ratio. Typical: 0.95–0.99")
        with c2:
            fouling = st.number_input("Fouling factor (F)", 0.50, 1.00,
                overrides.get("fouling_factor", inp.fouling_factor), 0.05,
                help="Diffuser fouling correction. New: 0.90–1.00; aged: 0.65–0.80")
            _sote_raw = overrides.get("sote_per_metre_submergence", inp.sote_per_metre_submergence)
            _sote_pct = float(_sote_raw) * 100 if float(_sote_raw) <= 1.0 else float(_sote_raw)
            _sote_pct = max(1.0, min(8.0, _sote_pct))
            sote_m  = st.number_input("SOTE per metre (%/m)", 1.0, 8.0,
                _sote_pct, 0.2,
                help="Standard O₂ transfer efficiency per metre of diffuser submergence. "
                     "Fine bubble: 3.5–6%/m") / 100
        with c3:
            submergence = st.number_input("Diffuser submergence (m)", 2.0, 8.0,
                overrides.get("diffuser_submergence_m", inp.diffuser_submergence_m), 0.25)
            peak_factor = st.number_input("Peak O₂ factor", 1.1, 2.5,
                overrides.get("peak_to_average_o2_factor", inp.peak_to_average_o2_factor), 0.1,
                help="Ratio of peak to average O₂ demand. Use 1.4–1.6 for design.")

        st.markdown("#### Removal efficiencies")
        c1, c2, c3 = st.columns(3)
        with c1:
            bod_eff  = st.slider("BOD removal efficiency (%)", 70, 99,
                int(overrides.get("bod_removal_efficiency", inp.bod_removal_efficiency) * 100)) / 100
        with c2:
            nh4_eff  = st.slider("NH₄ removal efficiency (%)", 60, 99,
                int(overrides.get("nh4_removal_efficiency", inp.nh4_removal_efficiency) * 100)) / 100
        with c3:
            denitfrac = st.slider("Denitrification fraction (%)", 0, 80,
                int(overrides.get("denitrification_fraction", inp.denitrification_fraction) * 100)) / 100

        st.markdown("#### Blower parameters")
        c1, c2, c3 = st.columns(3)
        with c1:
            blower_eff = st.number_input("Blower efficiency", 0.55, 0.85,
                overrides.get("blower_efficiency", inp.blower_efficiency), 0.01)
            motor_eff  = st.number_input("Motor efficiency", 0.85, 0.98,
                overrides.get("motor_efficiency", inp.motor_efficiency), 0.01)
        with c2:
            sys_press  = st.number_input("System pressure loss (kPa)", 5.0, 50.0,
                overrides.get("system_pressure_loss_kpa", inp.system_pressure_loss_kpa), 1.0)
            num_duty   = st.number_input("Duty blowers", 1, 6,
                int(overrides.get("num_duty_blowers", inp.num_duty_blowers)))
        with c3:
            num_standby = st.number_input("Standby blowers", 0, 3,
                int(overrides.get("num_standby_blowers", inp.num_standby_blowers)))
            motor_kw    = st.number_input("Motor kW (0 = auto-size)", 0.0, 2000.0,
                float(overrides.get("blower_motor_kw") or 0.0), 11.0)

        save_config = st.form_submit_button("Apply Configuration", type="primary",
                                             use_container_width=True)

    if save_config:
        new_overrides = {
            "alpha_factor":                       alpha,
            "beta_factor":                        beta,
            "fouling_factor":                     fouling,
            "sote_per_metre_submergence":         sote_m,
            "diffuser_submergence_m":             submergence,
            "peak_to_average_o2_factor":          peak_factor,
            "bod_removal_efficiency":             bod_eff,
            "nh4_removal_efficiency":             nh4_eff,
            "denitrification_fraction":           denitfrac,
            "blower_efficiency":                  blower_eff,
            "motor_efficiency":                   motor_eff,
            "system_pressure_loss_kpa":           sys_press,
            "num_duty_blowers":                   int(num_duty),
            "num_standby_blowers":                int(num_standby),
            "blower_motor_kw":                    motor_kw if motor_kw > 0 else None,
        }
        session[key] = new_overrides
        st.success("✅ Configuration applied.")
        st.rerun()
