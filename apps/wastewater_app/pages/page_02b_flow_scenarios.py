"""
apps/wastewater_app/pages/page_02b_flow_scenarios.py

Flow Scenario Framework — Streamlit UI.

A standalone page inserted after 02 Inputs.
Reads base values from domain_inputs (never modifies core engineering).
Writes scenario parameters back to domain_inputs["flow_scenario"] for persistence.
"""
from __future__ import annotations
import streamlit as st

from apps.ui.session_state import (
    require_project, get_current_project, update_current_project,
    get_active_scenario, mark_scenario_stale,
)
from apps.ui.ui_components import render_page_header, render_scenario_selector
from core.project.project_manager import ProjectManager
from apps.wastewater_app.flow_scenario_engine import (
    FlowScenarioInputs, WetWeatherProfile, calculate,
    to_domain_inputs_dict, from_domain_inputs_dict,
    FLOW_SCENARIO_TYPES, SCENARIO_DWA, SCENARIO_DWP, SCENARIO_AWWF, SCENARIO_PWWF,
)


def render() -> None:
    render_page_header(
        "02b Flow Scenarios",
        "Define hydraulic loading scenario: DWA, DWP, AWWF, or PWWF.",
    )
    require_project()
    project  = get_current_project()
    pm       = ProjectManager()

    render_scenario_selector(project)
    scenario = get_active_scenario()
    if not scenario:
        st.info("Create and select a scenario on 01 Project Setup first.")
        return

    di = scenario.domain_inputs or {}
    if not di.get("design_flow_mld"):
        st.warning("⚠️ Complete **02 Plant Inputs** first — design flow is required.")
        return

    # ── Restore stored flow scenario parameters ───────────────────────────
    stored = di.get("flow_scenario") or {}
    base_flow = float(di.get("design_flow_mld", 10.0))
    hyd_cap   = base_flow   # for a sized plant, design capacity == base flow

    # Read clarifier area from last calculated results if available
    dso = getattr(scenario, "domain_specific_outputs", None) or {}
    tc  = ""
    tp_p = getattr(getattr(scenario, "treatment_pathway", None), "technology_sequence", None)
    if tp_p:
        tc = tp_p[0]
    clar_area = (dso.get("technology_performance", {}) or {}).get(tc, {}).get("clarifier_area_m2")

    fsi = FlowScenarioInputs(
        base_flow_mld           = base_flow,
        base_bod_mg_l           = float(di.get("influent_bod_mg_l", 250.0)),
        base_tss_mg_l           = float(di.get("influent_tss_mg_l", 280.0)),
        base_tn_mg_l            = float(di.get("influent_tkn_mg_l", 45.0)),
        base_tp_mg_l            = float(di.get("influent_tp_mg_l",  7.0)),
        base_nh4_mg_l           = float(di.get("influent_nh4_mg_l", 35.0)),
        hydraulic_capacity_mld  = hyd_cap,
        clarifier_area_m2       = clar_area,
    )
    fsi = from_domain_inputs_dict(stored, fsi)

    st.subheader(f"Flow Scenario: {scenario.scenario_name}")

    # ── A. SCENARIO SELECTOR ──────────────────────────────────────────────
    st.markdown("### 1 — Scenario Type")
    col_sel, col_desc = st.columns([1, 2])
    with col_sel:
        scenario_type = st.selectbox(
            "Flow Scenario",
            FLOW_SCENARIO_TYPES,
            index=FLOW_SCENARIO_TYPES.index(fsi.scenario_type)
            if fsi.scenario_type in FLOW_SCENARIO_TYPES else 0,
            help="Select the hydraulic loading condition to model.",
        )
    with col_desc:
        _desc = {
            SCENARIO_DWA:  "Average dry weather flow. No peaking, no I/I. Base condition.",
            SCENARIO_DWP:  "Diurnal peak within a dry weather day. Applies peaking factor to DWA. No wet weather.",
            SCENARIO_AWWF: "Sustained wet weather event. I/I dominates, concentrations are diluted.",
            SCENARIO_PWWF: "Extreme wet weather peak. Maximum I/I, maximum dilution, short duration.",
        }
        st.info(_desc.get(scenario_type, ""))

    fsi.scenario_type = scenario_type
    is_ww = scenario_type in (SCENARIO_AWWF, SCENARIO_PWWF)
    is_dwp = scenario_type == SCENARIO_DWP

    # ── B. DWP INPUTS ─────────────────────────────────────────────────────
    if is_dwp:
        st.markdown("### 2 — Dry Weather Peak Parameters")
        fsi.dwp_factor = st.slider(
            "Diurnal Peaking Factor",
            min_value=1.2, max_value=3.0, value=float(fsi.dwp_factor), step=0.1,
            help="Ratio of peak hourly flow to average daily flow. Typical AU/NZ range: 1.5–2.5.",
        )

    # ── C. WET WEATHER INPUTS ─────────────────────────────────────────────
    if is_ww:
        st.markdown("### 2 — Wet Weather Parameters")
        _is_awwf = scenario_type == SCENARIO_AWWF

        tab_flow, tab_conc, tab_profile = st.tabs(
            ["📊 Flow & I/I", "💧 Concentration & Dilution", "⏱ Duration & Profile"]
        )

        with tab_flow:
            c1, c2 = st.columns(2)
            with c1:
                if _is_awwf:
                    fsi.awwf_factor = st.number_input(
                        "AWWF Factor (× DWA)", min_value=1.5, max_value=10.0,
                        value=float(fsi.awwf_factor), step=0.5,
                        help="Ratio of AWWF to average dry weather flow. Typical AU/NZ: 2–4×.",
                    )
                    fsi.awwf_ii_contribution_pct = st.slider(
                        "I/I Contribution (%)", 0, 100,
                        int(fsi.awwf_ii_contribution_pct), step=5,
                        help="Percentage of total AWWF volume contributed by infiltration and inflow.",
                    )
                else:
                    fsi.pwwf_factor = st.number_input(
                        "PWWF Factor (× DWA)", min_value=2.0, max_value=20.0,
                        value=float(fsi.pwwf_factor), step=0.5,
                        help="Ratio of PWWF to average dry weather flow. Typical AU/NZ: 4–8×.",
                    )
                    fsi.pwwf_ii_contribution_pct = st.slider(
                        "I/I Contribution (%)", 0, 100,
                        int(fsi.pwwf_ii_contribution_pct), step=5,
                    )
            with c2:
                if _is_awwf:
                    fsi.awwf_constant_mass_load = st.checkbox(
                        "Assume constant mass load during AWWF",
                        value=fsi.awwf_constant_mass_load,
                        help="If checked, mass load (kg/d) stays at DWA level; only hydraulic flow increases.",
                    )
                else:
                    fsi.pwwf_constant_mass_load = st.checkbox(
                        "Assume constant mass load during PWWF",
                        value=fsi.pwwf_constant_mass_load,
                    )

        with tab_conc:
            c1, c2 = st.columns(2)
            with c1:
                if _is_awwf:
                    fsi.awwf_dilution_factor = st.slider(
                        "Concentration Dilution Factor",
                        min_value=0.1, max_value=1.0,
                        value=float(fsi.awwf_dilution_factor), step=0.05,
                        help="Multiplier applied to DWA concentrations during AWWF. "
                             "1.0 = no dilution. Typical AWWF: 0.5–0.7.",
                    )
                else:
                    fsi.pwwf_dilution_factor = st.slider(
                        "Concentration Dilution Factor",
                        min_value=0.1, max_value=1.0,
                        value=float(fsi.pwwf_dilution_factor), step=0.05,
                        help="Multiplier applied to DWA concentrations during PWWF. "
                             "Typical PWWF: 0.2–0.5.",
                    )
            with c2:
                _dil = fsi.awwf_dilution_factor if _is_awwf else fsi.pwwf_dilution_factor
                st.metric("BOD at this dilution",
                          f"{fsi.base_bod_mg_l * _dil:.0f} mg/L",
                          delta=f"{(fsi.base_bod_mg_l * _dil) - fsi.base_bod_mg_l:.0f} mg/L vs DWA")
                st.metric("TN at this dilution",
                          f"{fsi.base_tn_mg_l * _dil:.1f} mg/L",
                          delta=f"{(fsi.base_tn_mg_l * _dil) - fsi.base_tn_mg_l:.1f} mg/L vs DWA")

        with tab_profile:
            c1, c2 = st.columns(2)
            with c1:
                if _is_awwf:
                    fsi.awwf_duration_hr = st.number_input(
                        "Total AWWF Duration (hours)", min_value=6.0, max_value=168.0,
                        value=float(fsi.awwf_duration_hr), step=4.0,
                    )
                    st.markdown("**Hydrograph shape:**")
                    fsi.awwf_profile.rise_hr     = st.number_input("Rise (hr)",     min_value=0.5, max_value=24.0, value=fsi.awwf_profile.rise_hr,     step=0.5)
                    fsi.awwf_profile.plateau_hr  = st.number_input("Plateau (hr)",  min_value=0.5, max_value=48.0, value=fsi.awwf_profile.plateau_hr,  step=0.5)
                    fsi.awwf_profile.recession_hr= st.number_input("Recession (hr)",min_value=0.5, max_value=48.0, value=fsi.awwf_profile.recession_hr, step=0.5)
                else:
                    fsi.pwwf_duration_hr = st.number_input(
                        "Total PWWF Duration (hours)", min_value=2.0, max_value=72.0,
                        value=float(fsi.pwwf_duration_hr), step=2.0,
                    )
                    st.markdown("**Hydrograph shape:**")
                    fsi.pwwf_profile.rise_hr     = st.number_input("Rise (hr)",     min_value=0.5, max_value=12.0, value=fsi.pwwf_profile.rise_hr,     step=0.5)
                    fsi.pwwf_profile.plateau_hr  = st.number_input("Peak (hr)",     min_value=0.5, max_value=24.0, value=fsi.pwwf_profile.plateau_hr,  step=0.5)
                    fsi.pwwf_profile.recession_hr= st.number_input("Recession (hr)",min_value=0.5, max_value=24.0, value=fsi.pwwf_profile.recession_hr, step=0.5)
            with c2:
                _prof = fsi.awwf_profile if _is_awwf else fsi.pwwf_profile
                st.metric("Total event duration",
                          f"{_prof.total_duration_hr:.0f} hours",
                          help="Sum of rise + plateau/peak + recession phases")
                st.caption(_prof.summary())

        # ── D. FIRST FLUSH ─────────────────────────────────────────────────
        st.markdown("---")
        st.markdown("### 3 — First Flush")
        fsi.first_flush_enabled = st.checkbox(
            "Include first flush effect",
            value=fsi.first_flush_enabled,
            help="Models the initial high-concentration pulse at the start of a wet weather event "
                 "before dilution becomes dominant.",
        )
        if fsi.first_flush_enabled:
            c1, c2 = st.columns(2)
            with c1:
                fsi.first_flush_duration_hr = st.number_input(
                    "First flush duration (hours)", min_value=0.25, max_value=6.0,
                    value=float(fsi.first_flush_duration_hr), step=0.25,
                )
            with c2:
                fsi.first_flush_conc_mult = st.slider(
                    "Concentration multiplier (vs DWA)",
                    min_value=1.0, max_value=3.0, value=float(fsi.first_flush_conc_mult), step=0.05,
                    help="First flush concentrations are typically 1.2–1.5× the DWA base.",
                )
            st.caption(
                f"During first flush: BOD = {fsi.base_bod_mg_l * fsi.first_flush_conc_mult:.0f} mg/L, "
                f"TN = {fsi.base_tn_mg_l * fsi.first_flush_conc_mult:.1f} mg/L, "
                f"TSS = {fsi.base_tss_mg_l * fsi.first_flush_conc_mult:.0f} mg/L"
            )

    # ── E. SAVE ───────────────────────────────────────────────────────────
    if st.button("💾 Save Flow Scenario", type="primary"):
        di_copy = dict(di)
        di_copy["flow_scenario"] = to_domain_inputs_dict(fsi)
        scenario.domain_inputs = di_copy
        mark_scenario_stale()
        update_current_project(project)
        pm.save(project)
        st.success(f"✅ Flow scenario **{scenario_type}** saved for {scenario.scenario_name}.")

    # ── F. RESULTS ────────────────────────────────────────────────────────
    st.divider()
    st.markdown("### 4 — Results: Wet Weather Interpretation")
    _render_results(fsi, clar_area, base_flow, hyd_cap)


# ── Results renderer ──────────────────────────────────────────────────────────

def _render_results(
    fsi: FlowScenarioInputs,
    clar_area,
    base_flow: float,
    hyd_cap: float,
) -> None:
    """Compute and render the flow scenario results panel."""
    result = calculate(fsi)
    st = __import__("streamlit")

    # ── Scenario summary banner ────────────────────────────────────────────
    scenario_colours = {
        SCENARIO_DWA:  "#1a6e1a",
        SCENARIO_DWP:  "#1a4e8e",
        SCENARIO_AWWF: "#8e6a1a",
        SCENARIO_PWWF: "#8e1a1a",
    }
    col = scenario_colours.get(result.scenario_type, "#555")
    st.markdown(
        f'<div style="border-left:5px solid {col};padding:10px 16px;'
        f'background:#f4f4f4;border-radius:4px;margin-bottom:12px;">'
        f'<b style="color:{col};font-size:1.1rem;">{result.scenario_type}</b><br>'
        f'<span style="color:#333;">Flow: <b>{result.adjusted_flow_mld:.1f} MLD</b> '
        f'({result.flow_factor:.1f}× DWA {base_flow:.1f} MLD) &nbsp;|&nbsp; '
        f'Dilution: {result.dilution_factor:.2f}× &nbsp;|&nbsp; '
        f'Load assumption: <i>{result.load_assumption}</i></span>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # ── KPI metrics row ───────────────────────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Adjusted Flow",   f"{result.adjusted_flow_mld:.1f} MLD",
              delta=f"{result.adjusted_flow_mld - base_flow:+.1f} vs DWA")
    c2.metric("BOD",  f"{result.adjusted_bod_mg_l:.0f} mg/L",
              delta=f"{result.adjusted_bod_mg_l - fsi.base_bod_mg_l:+.0f} vs DWA")
    c3.metric("TN",   f"{result.adjusted_tn_mg_l:.1f} mg/L",
              delta=f"{result.adjusted_tn_mg_l - fsi.base_tn_mg_l:+.1f} vs DWA")
    c4.metric("BOD Load",  f"{result.adjusted_bod_kg_d:.0f} kg/d",
              delta=f"{result.adjusted_bod_kg_d - result.base_biological_load_kg_d:+.0f} vs DWA")

    # ── Stress indicators ─────────────────────────────────────────────────
    st.markdown("**Stress Indicators**")
    s_cols = st.columns(3)

    def _badge(label, status, flag=False):
        col_ok = "#1a7a1a"; col_warn = "#8e6a1a"; col_fail = "#8e1a1a"
        if "OK" in status or "PASS" in status.upper():
            colour = col_ok; icon = "✅"
        elif "WARNING" in status.upper() or "Tightening" in status or "Elevated" in status:
            colour = col_warn; icon = "⚠️"
        else:
            colour = col_fail; icon = "🔴" if flag else "⚠️"
        return (
            f'<div style="border:1px solid {colour};border-radius:6px;padding:8px;'
            f'text-align:center;background:#fafafa;">'
            f'<div style="font-size:0.8rem;color:#555;">{label}</div>'
            f'<div style="font-weight:700;color:{colour};">{icon} {status}</div>'
            f'</div>'
        )

    with s_cols[0]:
        hyd_pct = f"{result.hydraulic_utilisation_pct:.0f}%" if result.hydraulic_utilisation_pct is not None else "—"
        st.markdown(
            _badge("Hydraulic Stress",
                   f"{result.hydraulic_stress_status} ({hyd_pct} capacity)",
                   result.overflow_flag),
            unsafe_allow_html=True,
        )

    with s_cols[1]:
        st.markdown(
            _badge("Biological Stress",
                   f"{result.biological_stress_status} (load ratio {result.biological_load_ratio:.2f}×)"),
            unsafe_allow_html=True,
        )

    with s_cols[2]:
        if result.clarifier_area_m2:
            st.markdown(
                _badge("Clarifier Stress",
                       result.clarifier_stress_status,
                       result.clarifier_stress_flag),
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<div style="border:1px solid #ccc;border-radius:6px;padding:8px;text-align:center;">'
                '<div style="font-size:0.8rem;color:#555;">Clarifier Stress</div>'
                '<div style="color:#999;">⚪ Run calculations for clarifier area</div>'
                '</div>',
                unsafe_allow_html=True,
            )

    # Overflow / bypass flags
    if result.overflow_flag or result.bypass_risk_flag:
        st.warning(
            ("🔴 **Overflow risk** — adjusted flow exceeds hydraulic capacity. "
             "Overflow or bypass event probable. " if result.overflow_flag else "") +
            ("⚠️ **Bypass risk** — flow exceeds capacity by >10%. "
             "Emergency bypass or flow diversion required." if result.bypass_risk_flag else "")
        )

    # ── Load table ────────────────────────────────────────────────────────
    with st.expander("📊 Adjusted Loads and Concentrations", expanded=True):
        import pandas as pd
        rows = [
            {"Parameter": "Flow",        "DWA",
             f"{result.scenario_type}": result.adjusted_flow_mld,
             "Unit": "MLD"},
            {"Parameter": "BOD",
             "DWA": fsi.base_bod_mg_l,
             f"{result.scenario_type}": result.adjusted_bod_mg_l,
             "Unit": "mg/L"},
            {"Parameter": "TSS",
             "DWA": fsi.base_tss_mg_l,
             f"{result.scenario_type}": result.adjusted_tss_mg_l,
             "Unit": "mg/L"},
            {"Parameter": "TN",
             "DWA": fsi.base_tn_mg_l,
             f"{result.scenario_type}": result.adjusted_tn_mg_l,
             "Unit": "mg/L"},
            {"Parameter": "TP",
             "DWA": fsi.base_tp_mg_l,
             f"{result.scenario_type}": result.adjusted_tp_mg_l,
             "Unit": "mg/L"},
            {"Parameter": "NH₄-N",
             "DWA": fsi.base_nh4_mg_l,
             f"{result.scenario_type}": result.adjusted_nh4_mg_l,
             "Unit": "mg/L"},
            {"Parameter": "BOD Load",
             "DWA": result.base_biological_load_kg_d,
             f"{result.scenario_type}": result.adjusted_bod_kg_d,
             "Unit": "kg/d"},
            {"Parameter": "TN Load",
             "DWA": round(fsi.base_tn_mg_l * base_flow, 1),
             f"{result.scenario_type}": result.adjusted_tn_kg_d,
             "Unit": "kg/d"},
        ]
        # Fix Flow DWA value
        rows[0]["DWA"] = base_flow
        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True, hide_index=True)

    # ── Wet weather profile ───────────────────────────────────────────────
    if result.wet_weather_duration_hr:
        with st.expander("⏱ Wet Weather Profile", expanded=False):
            c1, c2, c3 = st.columns(3)
            c1.metric("Total Duration", f"{result.wet_weather_duration_hr:.0f} hours")
            c2.metric("First Flush",
                      f"{result.first_flush_duration_hr:.1f}h" if result.first_flush_enabled else "Not modelled")
            c3.metric("I/I Contribution",
                      f"{result.ii_contribution_pct:.0f}%" if result.ii_contribution_pct is not None else "—")
            if result.wet_weather_profile:
                st.caption(f"📉 Hydrograph: {result.wet_weather_profile}")

            if result.phases:
                import pandas as pd
                phase_rows = []
                for ph in result.phases:
                    phase_rows.append({
                        "Phase":     ph.name,
                        "Duration (hr)": ph.duration_hr,
                        "Flow (MLD)": ph.flow_mld,
                        "BOD (mg/L)": ph.bod_mg_l,
                        "TSS (mg/L)": ph.tss_mg_l,
                        "TN (mg/L)":  ph.tn_mg_l,
                        "TP (mg/L)":  ph.tp_mg_l,
                    })
                st.dataframe(pd.DataFrame(phase_rows),
                             use_container_width=True, hide_index=True)
