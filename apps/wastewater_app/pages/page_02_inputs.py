"""
apps/wastewater_app/pages/page_02_inputs.py

02 Plant Inputs — organised into four sections with full validation.
"""

from __future__ import annotations
import streamlit as st
from apps.ui.session_state import (
    require_project, get_current_project, update_current_project,
    get_active_scenario, set_active_scenario, mark_scenario_stale,
)
from apps.ui.ui_components import render_page_header, render_scenario_selector, render_validation_banner
from core.project.project_manager import ProjectManager
from core.validation.validation_engine import ValidationEngine
from domains.wastewater.input_model import WastewaterInputs
from domains.wastewater.validation_rules import register_wastewater_validators


def render() -> None:
    render_page_header("02 Plant Inputs", "Define flow conditions, water quality, operating conditions, and economic assumptions.")
    require_project()

    project = get_current_project()
    pm = ProjectManager()

    selected_id = render_scenario_selector(project)
    if selected_id and selected_id != project.active_scenario_id:
        set_active_scenario(selected_id)
        project = get_current_project()

    scenario = get_active_scenario()
    if not scenario:
        st.error("No active scenario found.")
        return

    ex = scenario.domain_inputs or {}
    eco = scenario.economic_inputs if hasattr(scenario, 'economic_inputs') else {}

    st.subheader(f"Inputs: {scenario.scenario_name}")

    with st.form("inputs_form"):

        # ── SECTION 1: Flow conditions ─────────────────────────────────────
        st.markdown("### 1 — Flow Conditions")
        c1, c2, c3 = st.columns(3)
        with c1:
            design_flow = st.number_input("Average Dry Weather Flow (ML/day) *",
                min_value=0.01, max_value=5000.0,
                value=float(ex.get("design_flow_mld", 10.0)), step=0.5,
                help="Average dry weather flow at design year")
        with c2:
            peak_flow = st.number_input("Peak Wet Weather Flow (ML/day)",
                min_value=0.0, max_value=50000.0,
                value=float(ex.get("peak_flow_mld") or 0.0), step=0.5,
                help="If blank, peak flow = average × peak factor")
        with c3:
            peak_factor = st.number_input("Peak Flow Factor",
                min_value=1.2, max_value=6.0,
                value=float(ex.get("peak_flow_factor", 2.5)), step=0.1,
                help="Used only if peak wet weather flow is not set above")
        pop_ep = st.number_input("Design Population (EP)", min_value=0,
            value=int(ex.get("design_population_ep") or 0), step=500)

        st.divider()

        # ── SECTION 2: Influent water quality ─────────────────────────────
        st.markdown("### 2 — Influent Water Quality")
        c1, c2, c3 = st.columns(3)
        with c1:
            bod = st.number_input("BOD (mg/L)",  min_value=0.0, value=float(ex.get("influent_bod_mg_l", 250.0)), step=10.0)
            cod = st.number_input("COD (mg/L)",  min_value=0.0, value=float(ex.get("influent_cod_mg_l", 500.0)), step=10.0,
                                  help="Must be ≥ BOD")
            tss = st.number_input("TSS (mg/L)",  min_value=0.0, value=float(ex.get("influent_tss_mg_l", 280.0)), step=10.0)
        with c2:
            nh4 = st.number_input("NH₄-N (mg/L)", min_value=0.0, value=float(ex.get("influent_nh4_mg_l", 35.0)), step=1.0)
            tkn = st.number_input("TKN (mg/L)",   min_value=0.0, value=float(ex.get("influent_tkn_mg_l", 45.0)), step=1.0,
                                  help="Total Kjeldahl Nitrogen — must be ≥ NH₄-N")
            tp  = st.number_input("Total P (mg/L)", min_value=0.0, value=float(ex.get("influent_tp_mg_l", 7.0)), step=0.5)
        with c3:
            temp = st.number_input("Temperature (°C)", min_value=5.0, max_value=35.0,
                                   value=float(ex.get("influent_temperature_celsius", 20.0)), step=0.5)

        st.markdown("**Effluent Quality Targets**")
        c1, c2, c3 = st.columns(3)
        with c1:
            eff_bod = st.number_input("Effluent BOD (mg/L)", min_value=0.0, value=float(ex.get("effluent_bod_mg_l", 10.0)), step=1.0)
            eff_tss = st.number_input("Effluent TSS (mg/L)", min_value=0.0, value=float(ex.get("effluent_tss_mg_l", 10.0)), step=1.0)
        with c2:
            eff_tn  = st.number_input("Effluent TN (mg/L)",  min_value=0.0, value=float(ex.get("effluent_tn_mg_l", 10.0)), step=1.0)
            eff_tp  = st.number_input("Effluent TP (mg/L)",  min_value=0.0, value=float(ex.get("effluent_tp_mg_l", 0.5)),  step=0.1, format="%.2f")
        with c3:
            eff_nh4 = st.number_input("Effluent NH₄-N (mg/L)", min_value=0.0, value=float(ex.get("effluent_nh4_mg_l", 1.0)), step=0.5)

        st.divider()

        # ── SECTION 3: Operating conditions ───────────────────────────────
        st.markdown("### 3 — Operating Conditions")
        c1, c2, c3 = st.columns(3)
        with c1:
            mlss   = st.number_input("MLSS (mg/L)", min_value=1500, max_value=12000,
                                     value=int(ex.get("mlss_mg_l", 4000)), step=500)
        with c2:
            srt    = st.number_input("SRT (days)", min_value=3.0, max_value=40.0,
                                     value=float(ex.get("srt_days", 12.0)), step=1.0,
                                     help="Sludge retention time in biological reactors")
        with c3:
            do_sp  = st.number_input("DO Setpoint (mg/L)", min_value=0.5, max_value=4.0,
                                     value=float(ex.get("do_setpoint_mg_l", 2.0)), step=0.5)
        site     = st.text_input("Site Location", value=ex.get("site_location", ""))
        odour    = st.checkbox("Odour-sensitive location", value=bool(ex.get("odour_sensitive", False)))
        sludge_tx = st.checkbox("Include sludge treatment costs", value=bool(ex.get("include_sludge_treatment", True)))

        st.divider()

        # ── SECTION 4: Economic assumptions ───────────────────────────────
        st.markdown("### 4 — Economic Assumptions")
        c1, c2, c3 = st.columns(3)
        with c1:
            electricity = st.number_input("Electricity Price ($/kWh)",
                min_value=0.05, max_value=0.50,
                value=float(ex.get("electricity_price_per_kwh", 0.14)), step=0.01, format="%.3f")
        with c2:
            sludge_cost = st.number_input("Sludge Disposal ($/t DS)",
                min_value=0.0, max_value=2000.0,
                value=float(ex.get("sludge_disposal_cost_per_tonne_ds", 280.0)), step=10.0)
        with c3:
            carbon_price = st.number_input("Carbon Price ($/t CO₂e)",
                min_value=0.0, max_value=200.0,
                value=float(ex.get("carbon_price_per_tonne", 35.0)), step=5.0)

        submitted = st.form_submit_button("Save Inputs ✓", type="primary", use_container_width=True)

    # ── Live cross-validation (outside form, using current values) ─────────
    if submitted:
        inputs_dict = {
            "design_flow_mld": design_flow,
            "peak_flow_mld": peak_flow if peak_flow > 0 else None,
            "peak_flow_factor": peak_factor,
            "design_population_ep": pop_ep if pop_ep > 0 else None,
            "influent_bod_mg_l": bod, "influent_cod_mg_l": cod,
            "influent_tss_mg_l": tss, "influent_nh4_mg_l": nh4,
            "influent_tkn_mg_l": tkn, "influent_tp_mg_l": tp,
            "influent_temperature_celsius": temp,
            "effluent_bod_mg_l": eff_bod, "effluent_tss_mg_l": eff_tss,
            "effluent_tn_mg_l": eff_tn, "effluent_tp_mg_l": eff_tp,
            "effluent_nh4_mg_l": eff_nh4,
            "mlss_mg_l": float(mlss), "srt_days": srt, "do_setpoint_mg_l": do_sp,
            "site_location": site, "odour_sensitive": odour,
            "include_sludge_treatment": sludge_tx,
            "electricity_price_per_kwh": electricity,
            "sludge_disposal_cost_per_tonne_ds": sludge_cost,
            "carbon_price_per_tonne": carbon_price,
        }

        # Run validation immediately on save
        known = {f for f in WastewaterInputs.__dataclass_fields__ if not f.startswith("_")}
        clean = {k: v for k, v in inputs_dict.items() if k in known}
        ww_inputs = WastewaterInputs(**clean)

        val_engine = ValidationEngine()
        register_wastewater_validators(val_engine)
        val_result = val_engine.validate(ww_inputs)

        # Show any critical errors before saving
        render_validation_banner(val_result)

        if val_result.is_valid:
            scenario.domain_inputs = inputs_dict
            scenario.design_flow_mld = design_flow
            mark_scenario_stale()
            update_current_project(project)
            pm.save(project)
            st.success("✅ Inputs saved. Proceed to 03 Treatment Options.")
        else:
            st.error("❌ Please fix the errors above before saving.")
