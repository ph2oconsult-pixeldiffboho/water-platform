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
    # ── Detect stale zero-energy results ─────────────────────────────────
    # If energy is 0 (result from old module version), recalculate immediately.
    # Save cleared state to disk first so a worker restart can't cause a loop.
    _eng_check    = scenario.domain_specific_outputs.get("engineering_summary", {})
    _energy_check = _eng_check.get("total_energy_kwh_day", 0) or 0
    if _energy_check == 0 and scenario.cost_result and not scenario.is_stale:
        st.info("⚡ Results appear stale (0 kWh/day) — recalculating with updated modules...")
        scenario.cost_result             = None
        scenario.domain_specific_outputs = {}
        scenario.is_stale                = True
        update_current_project(project)
        pm.save(project)          # persist cleared state so worker restart is safe
        scenario.is_stale = False # flip in-memory so _run_calculations fires
        _run_calculations(project, scenario, pm)  # runs + calls st.rerun()
        return                    # never reached — st.rerun() above restarts render

    # ── Normal stale / unrun handling ─────────────────────────────────────
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
        _render_sensitivity_analysis(scenario)

    with tab_carbon:
        render_carbon_summary_card(scenario.carbon_result)

    with tab_risk:
        if scenario.risk_result:
            render_risk_matrix(scenario.risk_result)

    # ── Step 6: Key assumptions audit trail ────────────────────────────────
    _render_assumptions_panel(scenario)


def _render_sensitivity_analysis(scenario) -> None:
    """
    Step 10: Sensitivity sliders for electricity price, sludge disposal cost,
    and discount rate. Recalculates OPEX and LCC instantly without re-running
    the full engineering model.
    """
    import copy
    from core.costing.costing_engine import CostingEngine
    from core.assumptions.assumptions_manager import AssumptionsManager
    from core.project.project_model import DomainType

    if not scenario.cost_result:
        return

    cr = scenario.cost_result
    tech_codes = (scenario.treatment_pathway.technology_sequence
                  if scenario.treatment_pathway else [])

    with st.expander("📊 Sensitivity Analysis", expanded=False):
        st.caption(
            "Adjust key economic drivers to see how they affect lifecycle cost. "
            "Engineering outputs (energy, sludge, reactor sizing) are fixed at "
            "the calculated values — only the unit costs change."
        )

        col_s1, col_s2, col_s3 = st.columns(3)
        with col_s1:
            elec_base = 0.14
            elec_mult = st.slider(
                "Electricity price", 0.5, 2.0, 1.0, 0.1,
                format="×%.1f",
                help=f"Base: ${elec_base:.2f}/kWh (AUD 2024)",
                key=f"sens_elec_{scenario.scenario_name}",
            )
            st.caption(f"${elec_base*elec_mult:.3f}/kWh")

        with col_s2:
            sludge_base = 280.0
            sludge_mult = st.slider(
                "Sludge disposal cost", 0.5, 2.0, 1.0, 0.1,
                format="×%.1f",
                help=f"Base: ${sludge_base:.0f}/t DS",
                key=f"sens_sludge_{scenario.scenario_name}",
            )
            st.caption(f"${sludge_base*sludge_mult:.0f}/t DS")

        with col_s3:
            discount_rate = st.slider(
                "Discount rate (%)", 3, 10, 7, 1,
                help="Real discount rate for lifecycle cost calculation",
                key=f"sens_disc_{scenario.scenario_name}",
            )
            st.caption(f"{discount_rate}% per annum")

        # Only recalculate if sliders have moved from base
        needs_recalc = (abs(elec_mult - 1.0) > 0.05 or
                        abs(sludge_mult - 1.0) > 0.05 or
                        discount_rate != 7)

        try:
            base_a = getattr(scenario, "assumptions", None)
            if base_a is None:
                base_a = AssumptionsManager().load_defaults(DomainType.WASTEWATER)

            # Build modified assumptions
            import copy as _copy
            mod_a = _copy.deepcopy(base_a)
            mod_a.cost_assumptions["opex_unit_rates"]["electricity_per_kwh"] = elec_base * elec_mult
            mod_a.cost_assumptions["opex_unit_rates"]["sludge_disposal_per_tds"] = sludge_base * sludge_mult
            mod_a.cost_assumptions["discount_rate"] = discount_rate / 100.0

            # Re-run costing engine with modified assumptions
            mod_engine = CostingEngine(mod_a)
            flow = (scenario.domain_inputs or {}).get("design_flow_mld", 10.0)

            # Retrieve stored capex/opex items from scenario result
            capex_items = cr.capex_items if hasattr(cr, "capex_items") else []
            opex_items  = cr.opex_items  if hasattr(cr, "opex_items")  else []

            if capex_items or opex_items:
                mod_result = mod_engine.calculate(
                    capex_items=capex_items,
                    opex_items=opex_items,
                    design_flow_mld=flow,
                    tech_codes=tech_codes,
                )

                # Compare base vs modified
                import math
                i, n = discount_rate/100, cr.analysis_period_years
                crf = i*(1+i)**n / ((1+i)**n - 1)

                col_r1, col_r2, col_r3, col_r4 = st.columns(4)
                def _delta(new, base, fmt="{:.0f}"):
                    d = new - base
                    sign = "▲" if d > 0 else "▼"
                    return f"{sign} {fmt.format(abs(d))}"

                with col_r1:
                    st.metric("OPEX (modified)",
                              f"${mod_result.opex_annual/1e3:.0f}k/yr",
                              delta=_delta(mod_result.opex_annual/1e3,
                                           cr.opex_annual/1e3, "{:.0f}k"),
                              delta_color="inverse")
                with col_r2:
                    st.metric("LCC Annual (modified)",
                              f"${mod_result.lifecycle_cost_annual/1e3:.0f}k/yr",
                              delta=_delta(mod_result.lifecycle_cost_annual/1e3,
                                           cr.lifecycle_cost_annual/1e3, "{:.0f}k"),
                              delta_color="inverse")
                with col_r3:
                    if mod_result.specific_cost_per_kl:
                        st.metric("$/kL (modified)",
                                  f"${mod_result.specific_cost_per_kl:.3f}/kL",
                                  delta=_delta(mod_result.specific_cost_per_kl,
                                               cr.specific_cost_per_kl or 0, "{:.3f}"),
                                  delta_color="inverse")
                with col_r4:
                    pct_change = ((mod_result.lifecycle_cost_annual - cr.lifecycle_cost_annual)
                                  / cr.lifecycle_cost_annual * 100)
                    st.metric("LCC Change",
                              f"{pct_change:+.1f}%",
                              delta=None)
            else:
                # CostResult doesn't store raw items — show simplified recalc
                # using stored OPEX breakdown and modified unit rates
                bd = cr.opex_breakdown or {}
                elec_keys = [k for k in bd if "lectricit" in k.lower()]
                sludge_keys = [k for k in bd if "sludge" in k.lower()]

                base_elec   = sum(bd[k] for k in elec_keys)
                base_sludge = sum(bd[k] for k in sludge_keys)
                base_other  = cr.opex_annual - base_elec - base_sludge

                mod_elec   = base_elec   * elec_mult
                mod_sludge = base_sludge * sludge_mult
                mod_opex   = mod_elec + mod_sludge + base_other

                i, n = discount_rate/100, cr.analysis_period_years
                crf = i*(1+i)**n / ((1+i)**n - 1)
                mod_lcc = cr.capex_total * crf + mod_opex
                mod_kl  = mod_lcc / (flow * 1000 * 365) if flow > 0 else 0

                col_r1, col_r2, col_r3, col_r4 = st.columns(4)
                def _delta(new, base, fmt="{:.0f}"):
                    d = new - base
                    sign = "▲" if d > 0 else "▼"
                    return f"{sign} {fmt.format(abs(d))}"

                with col_r1:
                    st.metric("OPEX (modified)",
                              f"${mod_opex/1e3:.0f}k/yr",
                              delta=_delta(mod_opex/1e3, cr.opex_annual/1e3, "{:.0f}k"),
                              delta_color="inverse")
                with col_r2:
                    st.metric("LCC Annual (modified)",
                              f"${mod_lcc/1e3:.0f}k/yr",
                              delta=_delta(mod_lcc/1e3, cr.lifecycle_cost_annual/1e3, "{:.0f}k"),
                              delta_color="inverse")
                with col_r3:
                    base_kl = cr.specific_cost_per_kl or 0
                    st.metric("$/kL (modified)",
                              f"${mod_kl:.3f}/kL",
                              delta=_delta(mod_kl, base_kl, "{:.3f}"),
                              delta_color="inverse")
                with col_r4:
                    pct = (mod_lcc - cr.lifecycle_cost_annual) / cr.lifecycle_cost_annual * 100
                    st.metric("LCC Change", f"{pct:+.1f}%")

                st.caption(
                    "ⓘ Simplified sensitivity: electricity and sludge costs scaled; "
                    "other costs fixed. Run full recalculation for complete results."
                )

        except Exception as e:
            st.caption(f"Sensitivity calculation unavailable: {e}")


def _render_assumptions_panel(scenario) -> None:
    """Expandable panel showing key assumptions used in calculations."""
    from core.assumptions.assumptions_manager import AssumptionsManager
    from core.project.project_model import DomainType

    with st.expander("🔍 Key Assumptions Used in This Calculation", expanded=False):
        st.caption(
            "These are the economic, engineering, and carbon assumptions that drove the "
            "results above. Values marked ✎ have been overridden from defaults."
        )
        a = getattr(scenario, "assumptions", None)
        if a is None:
            a = AssumptionsManager().load_defaults(DomainType.WASTEWATER)

        cost   = a.cost_assumptions   if hasattr(a, "cost_assumptions")   else {}
        eng    = a.engineering_assumptions if hasattr(a, "engineering_assumptions") else {}
        carbon = a.carbon_assumptions  if hasattr(a, "carbon_assumptions") else {}
        overrides = a.user_overrides   if hasattr(a, "user_overrides")     else {}
        opex_rates = cost.get("opex_unit_rates", {})

        def _flag(key):
            return " ✎" if key in overrides else ""

        col_a, col_b, col_c = st.columns(3)
        with col_a:
            st.markdown("**Economic**")
            st.text(f"Electricity:       ${opex_rates.get('electricity_per_kwh', cost.get('electricity_per_kwh', 0.14)):.3f}/kWh{_flag('electricity_per_kwh')}")
            st.text(f"Sludge disposal:   ${opex_rates.get('sludge_disposal_per_tds', 280):.0f}/t DS{_flag('sludge_disposal_per_tds')}")
            st.text(f"Discount rate:     {cost.get('discount_rate', 0.07)*100:.0f}%{_flag('discount_rate')}")
            st.text(f"Analysis period:   {cost.get('analysis_period_years', 30)} yr{_flag('analysis_period_years')}")
            st.text(f"Labour:            {opex_rates.get('labour_fte_per_10mld', 2.5):.1f} FTE/10 MLD")
            st.text(f"Labour rate:       ${opex_rates.get('labour_cost_per_fte', 105000)/1e3:.0f}k/yr/FTE")
            st.text(f"Maintenance:       1.5–2.0% CAPEX/yr (tech-dependent)")

        with col_b:
            st.markdown("**Engineering**")
            st.text(f"Influent BOD:      {eng.get('influent_bod_mg_l', 250):.0f} mg/L")
            st.text(f"Influent TKN:      {eng.get('influent_tkn_mg_l', 45):.0f} mg/L")
            st.text(f"Influent NH₄:      {eng.get('influent_nh4_mg_l', 35):.0f} mg/L")
            st.text(f"Design temp:       {eng.get('influent_temperature_celsius', 20):.0f} °C")
            st.text(f"Peak flow factor:  {eng.get('peak_flow_factor', 2.5):.1f}×")
            st.text(f"MLSS (BNR):        {eng.get('mlss_mg_l', 4000):.0f} mg/L")
            st.text(f"SRT (BNR default): {eng.get('srt_days', 12):.0f} d")

        with col_c:
            st.markdown("**Carbon**")
            st.text(f"Grid emission:     {carbon.get('grid_emission_factor_kg_co2e_per_kwh', 0.79):.3f} kgCO₂e/kWh")
            st.text(f"N₂O EF:            {carbon.get('n2o_emission_factor_g_n2o_per_g_n_removed', 0.016):.3f} kg/kg N")
            st.text(f"N₂O GWP:           {carbon.get('n2o_gwp', 273)}")
            st.text(f"CH₄ GWP:           {carbon.get('ch4_gwp', 28)}")
            st.text(f"Carbon price:      ${carbon.get('carbon_price_per_tonne_co2e', 35):.0f}/tCO₂e")
            st.text(f"N₂O uncertainty:   ×3–10 (IPCC range 0.005–0.05)")

        if overrides:
            st.info(f"✎ {len(overrides)} user overrides active — see Assumptions page to review.")

        st.caption(
            "To change these assumptions, use page 02 Plant Inputs or the Assumptions page. "
            "All costs are AUD 2024. CAPEX ±40% concept estimate."
        )


def _render_engineering_tab(scenario, ps_highlight) -> None:
    _render_calculation_basis(scenario)


def _render_calculation_basis(scenario) -> None:
    """Phase 2: Transparent calculation basis — how results were derived."""
    do = scenario.domain_specific_outputs or {}
    eng = do.get("engineering_summary", {})
    tp  = do.get("technology_performance", {})
    tech_code = (scenario.treatment_pathway.technology_sequence[0]
                 if scenario.treatment_pathway and scenario.treatment_pathway.technology_sequence
                 else "")
    perf = tp.get(tech_code, {})
    di   = scenario.domain_inputs or {}

    # Only show if we have meaningful data
    if not perf.get("o2_demand_kg_day"):
        return

    flow    = di.get("design_flow_mld", 10)
    bod     = di.get("influent_bod_mg_l", 250)
    tkn     = di.get("influent_tkn_mg_l", 45)
    nh4     = di.get("influent_nh4_mg_l", 35)
    tss     = di.get("influent_tss_mg_l", 280)
    eff_tn  = di.get("effluent_tn_mg_l", 10)
    eff_nh4 = di.get("effluent_nh4_mg_l", 1)

    bod_load  = flow * 1000 * bod / 1000
    tkn_load  = flow * 1000 * tkn / 1000
    nh4_load  = flow * 1000 * nh4 / 1000
    tss_load  = flow * 1000 * tss / 1000
    eff_bod   = di.get("effluent_bod_mg_l", 10)
    bod_rem   = flow * 1000 * max(0, bod - eff_bod) / 1000
    tn_rem    = flow * 1000 * max(0, tkn - eff_tn) / 1000

    o2_total  = perf.get("o2_demand_kg_day", 0) or 0
    aer_kwh   = perf.get("aeration_energy_kwh_day", 0) or 0
    kwh_day   = eng.get("total_energy_kwh_day", 0) or 0
    sludge    = eng.get("total_sludge_kgds_day", 0) or 0
    cr        = scenario.cost_result

    with st.expander("🔬 Calculation Basis — How These Results Were Derived", expanded=False):
        st.caption(
            "This panel shows the engineering calculation chain behind the results above. "
            "Values are rounded for display. Full precision used in calculations."
        )

        col1, col2 = st.columns(2)

        with col1:
            # ── Influent loading ────────────────────────────────────────
            st.markdown("**📥 Influent Loading**")
            st.markdown(f"""
| Parameter | Value |
|---|---|
| Design flow | {flow:.1f} MLD = {flow*1000:.0f} m³/day |
| BOD load | {flow:.1f} × {bod:.0f} mg/L = **{bod_load:.0f} kg BOD/day** |
| TKN load | {flow:.1f} × {tkn:.0f} mg/L = **{tkn_load:.0f} kg TKN/day** |
| NH₄-N load | {flow:.1f} × {nh4:.0f} mg/L = **{nh4_load:.0f} kg NH₄/day** |
| TSS load | {flow:.1f} × {tss:.0f} mg/L = **{tss_load:.0f} kg TSS/day** |
| BOD removed | {bod:.0f} − {eff_bod:.0f} mg/L = **{bod_rem:.0f} kg/day** |
""")

            # ── Oxygen demand ────────────────────────────────────────────
            # Estimate components from total
            st.markdown("**⚗️ Oxygen Demand (Metcalf Eq. 7-57)**")
            # Rough split: O2_c ~ BOD_rem × 1.0, O2_n ~ NH4_rem × 4.57 × 0.9
            eff_nh4_actual = float(perf.get("effluent_nh4_mg_l") or eff_nh4)
            nh4_rem   = flow * 1000 * max(0, nh4 - eff_nh4_actual) / 1000
            o2_n_est  = round(4.57 * nh4_rem * 0.90, 0)
            dn_credit = round(2.86 * tn_rem * 0.70, 0)
            o2_c_est  = round(max(0, o2_total - o2_n_est + dn_credit), 0)
            st.markdown(f"""
| Component | Calculation | Value |
|---|---|---|
| Carbonaceous O₂ | BOD × y_obs × 1.42 × (1−1.42×y_obs) | ~{o2_c_est:.0f} kg/day |
| Nitrification O₂ | 4.57 × NH₄_rem × 0.90 | ~{o2_n_est:.0f} kg/day |
| Denitrification credit | 2.86 × TN_removed × 0.70 | −{dn_credit:.0f} kg/day |
| **Net O₂ demand** | Sum | **{o2_total:.0f} kg/day** |
""")

        with col2:
            # ── Energy ───────────────────────────────────────────────────
            pump_kwh = round(kwh_day - aer_kwh, 0) if kwh_day and aer_kwh else 0
            st.markdown("**⚡ Energy Calculation**")
            sae_proc = round(o2_total / aer_kwh, 3) if aer_kwh > 0 else 0
            st.markdown(f"""
| Component | Calculation | Value |
|---|---|---|
| Aeration | O₂ ÷ SAE_process ({sae_proc:.3f} kgO₂/kWh) | {aer_kwh:.0f} kWh/day |
| Pumping + ancillary | RAS + MLR + WAS + ancillary | {pump_kwh:.0f} kWh/day |
| **Total plant** | Sum | **{kwh_day:.0f} kWh/day** |
| **Specific energy** | {kwh_day:.0f} ÷ {flow*1000:.0f} m³/day | **{kwh_day/max(flow*1000,1)*1000:.0f} kWh/ML** |
""")

            # ── Sludge ───────────────────────────────────────────────────
            st.markdown("**💩 Sludge Calculation**")
            y_obs_est = round(sludge * 0.80 / max(bod_rem, 1), 3) if bod_rem > 0 else 0
            inorg_est = round(tss_load * 0.20, 0)
            bio_est   = round(sludge - inorg_est, 0)
            st.markdown(f"""
| Component | Basis | Value |
|---|---|---|
| Biological TSS | y_obs ≈ {y_obs_est:.3f} × BOD_removed ÷ VSS/TSS | ~{bio_est:.0f} kg DS/day |
| Inorganic TSS | Influent TSS × (1 − VSS/TSS) | ~{inorg_est:.0f} kg DS/day |
| **Total sludge** | Sum | **{sludge:.0f} kg DS/day = {sludge*365/1000:.0f} t DS/yr** |
""")

            # ── Cost ─────────────────────────────────────────────────────
            if cr:
                import math
                i, n = cr.discount_rate, cr.analysis_period_years
                crf = i*(1+i)**n/((1+i)**n-1)
                st.markdown("**💰 Lifecycle Cost**")
                st.markdown(f"""
| Component | Calculation | Value |
|---|---|---|
| CAPEX (annualised) | ${cr.capex_total/1e6:.2f}M × CRF({i*100:.0f}%,{n}yr)={crf:.4f} | ${cr.capex_total*crf/1e3:.0f}k/yr |
| OPEX annual | Electricity + sludge + maintenance + labour | ${cr.opex_annual/1e3:.0f}k/yr |
| **Lifecycle cost** | Sum | **${cr.lifecycle_cost_annual/1e3:.0f}k/yr** |
| **Specific cost** | LCC ÷ annual volume | **${cr.specific_cost_per_kl:.3f}/kL** |
""")

        # ── Carbon ──────────────────────────────────────────────────────
        if scenario.carbon_result:
            car = scenario.carbon_result
            st.markdown("**🌿 Carbon Sources**")
            col_c1, col_c2, col_c3 = st.columns(3)
            with col_c1:
                st.metric("Scope 1 — Process N₂O + CH₄",
                          f"{car.scope_1_tco2e_yr:.0f} tCO₂e/yr",
                          help="N₂O from denitrification (IPCC EF=0.016) + fugitive CH₄")
            with col_c2:
                st.metric("Scope 2 — Electricity",
                          f"{car.scope_2_tco2e_yr:.0f} tCO₂e/yr",
                          help=f"Total kWh/yr × {car.grid_emission_factor_used:.3f} kgCO₂e/kWh")
            with col_c3:
                st.metric("Net emissions",
                          f"{car.net_tco2e_yr:.0f} tCO₂e/yr",
                          help="Scope1 + Scope2 + Scope3 − Avoided")

        st.caption(
            "Ref: Metcalf & Eddy 5th Ed Eq. 7-57 (O₂), Table 7-15 (y_obs), "
            "WEF MOP 35 (pumping), IPCC 2019 Tier 1 (N₂O), AUS NEM 2024 (grid factor 0.79 kgCO₂e/kWh)"
        )
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
