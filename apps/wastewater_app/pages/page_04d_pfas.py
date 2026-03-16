"""
apps/wastewater_app/pages/page_04d_pfas.py

PFAS and Biosolids Risk Assessment page.
Sits in the workflow after Biosolids (04c).

⚠ IMPORTANT DISCLAIMER — DISPLAYED TO USERS:
This page provides screening-level PFAS assessment for biosolids strategy
planning only. It is NOT a quantitative risk assessment and does not
replace professional environmental risk assessment, contaminated land
assessment, or regulatory advice. All PFAS assumptions are indicative
and highly uncertain. Regulatory requirements are subject to rapid change.
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
from domains.wastewater.pfas_model import (
    PFASModel, PFASInputs, PFASRiskTier, PFASCompoundClass,
    PFAS_PATHWAY_ASSUMPTIONS, PFAS_REGULATORY_REFS,
    pfas_inputs_from_scenario,
)
from domains.wastewater.pfas_risk_model import (
    PFASRiskModel, RiskLevel, BASE_PATHWAY_RISK_PROFILES,
)

RISK_COLOURS = {
    "Low":       "#2ca02c",
    "Moderate":  "#ff7f0e",
    "High":      "#d62728",
    "Very High": "#7b0000",
}

PATHWAY_DISPLAY = {
    "land_application": "Land Application",
    "composting":       "Composting",
    "landfill":         "Landfill",
    "incineration":     "Incineration",
    "pyrolysis":        "Pyrolysis",
    "gasification":     "Gasification",
}


def render() -> None:
    render_page_header(
        "04d PFAS & Biosolids Risk",
        "Screening-level PFAS assessment and biosolids pathway risk comparison.",
    )

    # ── Mandatory disclaimer ───────────────────────────────────────────────
    st.warning(
        "⚠️ **SCREENING-LEVEL PLANNING TOOL ONLY.** "
        "This assessment is NOT a quantitative PFAS risk assessment. "
        "Results are indicative only. PFAS concentrations, fate assumptions, and risk scores "
        "are highly uncertain. Do not use for regulatory submissions, remediation planning, "
        "or land application approvals. Obtain site-specific PFAS data and professional "
        "environmental advice before making biosolids management decisions.",
        icon="⚠️",
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

    # Need sludge mass balance data
    bio_outputs = scenario.domain_specific_outputs.get("biosolids", {})
    sludge_data = bio_outputs.get("sludge", {})

    if not sludge_data:
        st.info("⚠️ Run 04 Results and 04c Biosolids & Sludge first to populate sludge data.")
        return

    raw_ds_t_yr    = sludge_data.get("Raw DS (t/yr)", 548.0)
    cake_ds_t_yr   = sludge_data.get("Digested DS (t/yr)", 293.0) or sludge_data.get("Raw DS (t/yr)", 548.0)
    cake_wet_t_yr  = sludge_data.get("Wet Cake (t/yr)", 1334.0)
    disposal_path  = sludge_data.get("Disposal Pathway", "landfill")

    # ── Load overrides ─────────────────────────────────────────────────────
    pfas_key = f"pfas_overrides_{scenario.scenario_id}"
    if pfas_key not in st.session_state:
        st.session_state[pfas_key] = {"disposal_pathway": disposal_path}
    overrides = st.session_state[pfas_key]
    overrides.setdefault("disposal_pathway", disposal_path)

    # ── PFAS inputs panel ──────────────────────────────────────────────────
    st.subheader("PFAS Data Input")

    with st.expander("Configure PFAS inputs", expanded=True):
        with st.form("pfas_input_form"):
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("**PFAS concentration data**")
                data_type = st.radio(
                    "Data availability",
                    ["Use risk tier (no measured data)", "Enter measured concentration"],
                    index=0 if overrides.get("pfas_concentration_ug_kg") is None else 1,
                )
                if data_type == "Use risk tier (no measured data)":
                    tier_options = {
                        PFASRiskTier.LOW.value:      "Low risk (rural, no known PFAS sources)",
                        PFASRiskTier.MODERATE.value: "Moderate risk (mixed urban/industrial)",
                        PFASRiskTier.HIGH.value:     "High risk (industrial, AFFF history)",
                    }
                    tier = st.selectbox("PFAS risk tier",
                        list(tier_options.keys()),
                        format_func=lambda x: tier_options[x],
                        index=list(tier_options.keys()).index(
                            overrides.get("pfas_risk_tier", PFASRiskTier.MODERATE.value)
                        ))
                    measured_conc = None
                    unc_factor = st.number_input("Uncertainty factor (×)",
                        1.0, 10.0, float(overrides.get("pfas_uncertainty_factor", 3.0)), 0.5,
                        help="Range = central estimate ÷ factor to × factor. Use 3–5 for limited data.")
                else:
                    tier = PFASRiskTier.MODERATE.value
                    measured_conc = st.number_input(
                        "∑PFAS concentration in biosolids (µg/kg DS)",
                        0.0, 200000.0,
                        float(overrides.get("pfas_concentration_ug_kg") or 500.0), 10.0,
                        help="Enter measured ∑PFAS in dewatered biosolids cake",
                    )
                    unc_factor = 1.0

                compound_class = st.selectbox(
                    "Compound class reported",
                    [c.value for c in PFASCompoundClass],
                    format_func=lambda x: PFASCompoundClass(x).display_name,
                    index=[c.value for c in PFASCompoundClass].index(
                        overrides.get("pfas_compound_class", PFASCompoundClass.TOTAL_PFAS.value)
                    ),
                    help="Specify which PFAS compounds the concentration represents",
                )

            with col2:
                st.markdown("**Catchment context**")
                known_source = st.checkbox(
                    "Known PFAS source in catchment",
                    value=bool(overrides.get("known_pfas_source_in_catchment", False)),
                    help="Industrial discharge, stormwater from PFAS-using industry",
                )
                afff_history = st.checkbox(
                    "AFFF (firefighting foam) use history",
                    value=bool(overrides.get("afff_use_history", False)),
                    help="Airport, military, industrial fire training in catchment",
                )
                industrial_pfas = st.checkbox(
                    "Industrial PFAS dischargers in catchment",
                    value=bool(overrides.get("industrial_pfas_dischargers", False)),
                )

                st.markdown("**Biosolids management pathway**")
                selected_pathway = st.selectbox(
                    "Selected disposal/management pathway",
                    list(PATHWAY_DISPLAY.keys()),
                    format_func=lambda x: PATHWAY_DISPLAY[x],
                    index=list(PATHWAY_DISPLAY.keys()).index(
                        overrides.get("disposal_pathway", "landfill")
                    ),
                )

            save_pfas = st.form_submit_button("Apply PFAS inputs", type="primary",
                                               use_container_width=True)

        if save_pfas:
            new_ov = {
                "pfas_risk_tier":                tier,
                "pfas_concentration_ug_kg":       measured_conc,
                "pfas_compound_class":            compound_class,
                "pfas_uncertainty_factor":        unc_factor,
                "known_pfas_source_in_catchment": known_source,
                "afff_use_history":               afff_history,
                "industrial_pfas_dischargers":    industrial_pfas,
                "disposal_pathway":               selected_pathway,
            }
            st.session_state[pfas_key] = new_ov
            overrides = new_ov
            st.success("✅ PFAS inputs applied.")
            st.rerun()

    # ── Run models ─────────────────────────────────────────────────────────
    pfas_inp = pfas_inputs_from_scenario(scenario.domain_inputs or {}, overrides)
    pfas_inp.disposal_pathway = overrides.get("disposal_pathway", disposal_path)

    pfas_model  = PFASModel()
    pfas_result = pfas_model.calculate(pfas_inp, raw_ds_t_yr, cake_ds_t_yr, cake_wet_t_yr)

    risk_model = PFASRiskModel()
    all_scores = risk_model.score_all_pathways(pfas_result, pfas_inp)
    selected_score = all_scores.get(overrides.get("disposal_pathway", "landfill"))

    # Store for comparison page
    scenario.domain_specific_outputs["pfas"] = {
        "mass_balance": pfas_result.to_summary_dict(),
        "selected_pathway_risk": selected_score.to_summary_dict() if selected_score else {},
        "pathway_scores": {k: v.to_summary_dict() for k, v in all_scores.items()},
    }
    update_current_project(project)

    # ── Tabs ──────────────────────────────────────────────────────────────
    tab_mass, tab_pathway, tab_comparison, tab_regulatory, tab_notes = st.tabs([
        "⚖️ Mass Balance", "🔍 Selected Pathway", "📊 All Pathways",
        "⚖️ Regulatory Context", "📋 Assumptions"
    ])

    with tab_mass:
        _render_mass_balance(pfas_result, pfas_inp)

    with tab_pathway:
        _render_selected_pathway(pfas_result, selected_score, pfas_inp)

    with tab_comparison:
        _render_pathway_comparison(all_scores, pfas_result)

    with tab_regulatory:
        _render_regulatory_context(pfas_result, pfas_inp)

    with tab_notes:
        _render_assumptions(pfas_result)


def _render_mass_balance(pfas_result, pfas_inp) -> None:
    st.subheader("PFAS Mass Balance")

    # Warnings first — most important information
    for w in pfas_result.warnings:
        st.error(w) if "⚠" in w else st.warning(w)

    # KPI row
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("PFAS in feed sludge",
              f"{pfas_result.pfas_concentration_feed_ug_kg:,.0f} µg/kg DS",
              help=f"Compound class: {pfas_inp.pfas_compound_class}")
    c2.metric("PFAS after digestion",
              f"{pfas_result.pfas_concentration_digested_ug_kg:,.0f} µg/kg DS",
              help="Concentration rises as VS is destroyed — same PFAS mass in fewer kg DS")
    c3.metric("PFAS in dewatered cake",
              f"{pfas_result.pfas_concentration_cake_ug_kg:,.0f} µg/kg DS",
              help="The concentration in the product applied/disposed. "
                   "Cake DS is the same as digested DS — dewatering removes water only.")
    c4.metric("Annual PFAS in feed",
              f"{pfas_result.pfas_mass_in_feed_g_yr:,.0f} g/yr",
              help=f"= {pfas_result.pfas_mass_in_feed_g_yr/1e6:.4f} kg/yr")

    # Regulatory comparison
    st.divider()
    st.markdown("**Regulatory comparison — NSW EPA and EPA Victoria (2024): 100 µg/kg ∑PFAS**")
    reg_colour = "red" if pfas_result.pfas_exceeds_nsw_trigger else "green"
    status     = "⛔ EXCEEDS" if pfas_result.pfas_exceeds_nsw_trigger else "✅ Below"
    st.markdown(
        f"Cake concentration **{pfas_result.pfas_concentration_cake_ug_kg:,.0f} µg/kg DS** — "
        f"<span style='color:{reg_colour}; font-weight:bold'>"
        f"{status} the NSW EPA / EPA Victoria land application trigger "
        f"({pfas_result.regulatory_trigger_nsw_ug_kg:.0f} µg/kg ∑PFAS, 10 named compounds)</span>",
        unsafe_allow_html=True,
    )
    st.caption(
        "Regulatory values are 2024–2025 and subject to change. Verify current requirements in your jurisdiction."
    )

    # Uncertainty range (when using tier)
    if pfas_inp.pfas_concentration_ug_kg is None and pfas_result.pfas_concentration_lo_ug_kg > 0:
        st.caption(
            f"Concentration uncertainty range (÷/× {pfas_inp.pfas_uncertainty_factor:.0f}): "
            f"{pfas_result.pfas_concentration_lo_ug_kg:,.0f} – "
            f"{pfas_result.pfas_concentration_hi_ug_kg:,.0f} µg/kg DS"
        )

    st.divider()

    # Two-column: mass balance table + liquid line highlight
    col_left, col_right = st.columns([3, 2])
    with col_left:
        st.markdown("**PFAS mass through treatment train**")
        ls = pfas_result.liquid_streams
        mass_rows = [
            {"Stage": "1. Raw feed sludge",
             "PFAS mass (g/yr)": f"{pfas_result.pfas_mass_in_feed_g_yr:,.1f}",
             "Notes": "Measured or tier estimate"},
            {"Stage": "   → To reject water (digestion)",
             "PFAS mass (g/yr)": f"{ls.reject_water_g_yr:,.1f}",
             "Notes": "~10% to liquid line, returns to headworks"},
            {"Stage": "2. After digestion (in solids)",
             "PFAS mass (g/yr)": f"{pfas_result.pfas_mass_after_digestion_g_yr:,.1f}",
             "Notes": f"{pfas_result.pfas_concentration_digested_ug_kg:,.0f} µg/kg DS — concentration ↑"},
            {"Stage": "   → To filtrate (dewatering)",
             "PFAS mass (g/yr)": f"{ls.filtrate_g_yr:,.1f}",
             "Notes": "~10% to liquid line, returns to headworks"},
            {"Stage": "3. Dewatered cake",
             "PFAS mass (g/yr)": f"{pfas_result.pfas_mass_in_cake_g_yr:,.1f}",
             "Notes": f"{pfas_result.pfas_concentration_cake_ug_kg:,.0f} µg/kg DS"},
            {"Stage": "   Destroyed by pathway",
             "PFAS mass (g/yr)": f"{pfas_result.pfas_mass_destroyed_g_yr:,.1f}",
             "Notes": "Thermal pathways only"},
            {"Stage": "4. Final solid output",
             "PFAS mass (g/yr)": f"{pfas_result.pfas_mass_in_final_solid_g_yr:,.1f}",
             "Notes": f"{pfas_result.pfas_concentration_after_pathway_ug_kg:,.0f} µg/kg DS"},
        ]
        st.dataframe(pd.DataFrame(mass_rows), use_container_width=True, hide_index=True)

    with col_right:
        st.markdown("**⚠ PFAS returned to liquid treatment line**")
        st.metric("Total to liquid line",
                  f"{ls.total_to_liquid_line_g_yr:,.1f} g/yr",
                  help=ls.note)
        st.metric("As % of feed",
                  f"{ls.pct_of_feed:.0f}%")
        st.caption(
            "Reject water (digestion): " + f"{ls.reject_water_g_yr:,.1f}" + " g/yr  |  "
            + "Dewatering filtrate: " + f"{ls.filtrate_g_yr:,.1f}" + " g/yr"
        )
        st.caption(ls.note)
        # Land loading (if applicable)
        if pfas_result.pfas_loading_g_ha_yr is not None:
            st.metric(
                f"PFAS loading to land",
                f"{pfas_result.pfas_loading_g_ha_yr:,.0f} mg/ha/yr",
                help=f"At {pfas_result.application_rate_t_ds_ha} t DS/ha/yr application rate"
            )

    st.caption(
        "⚠ PFAS mass balance is indicative only. Partitioning between sludge and liquid "
        "streams varies by compound class (short-chain PFAS partition more to water), "
        "temperature, pH, and sludge characteristics. "
        "The 90% solids retention factor is a central screening estimate."
    )


def _render_selected_pathway(pfas_result, score, pfas_inp) -> None:
    if not score:
        st.info("Select a disposal pathway in the configuration panel above.")
        return

    st.subheader(f"Selected Pathway: {score.display_name}")

    # Overall risk badge
    c = RISK_COLOURS[score.composite_level.value]
    st.markdown(
        f"<div style='background:{c}; color:white; padding:12px; border-radius:8px; "
        f"font-size:1.2rem; font-weight:bold; text-align:center'>"
        f"Overall PFAS Risk: {score.composite_level.value} "
        f"(composite score {score.composite_score:.1f}/4.0)</div>",
        unsafe_allow_html=True,
    )
    st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)

    # Four-dimension table
    dims = [
        ("Environmental Risk", score.environmental_risk, score.environmental_rationale),
        ("Regulatory Risk", score.regulatory_risk, score.regulatory_rationale),
        ("Public Perception Risk", score.public_perception_risk, score.public_perception_rationale),
        ("Long-term Liability Risk", score.long_term_liability_risk, score.long_term_liability_rationale),
    ]
    for dim_name, level, rationale in dims:
        col_badge, col_text = st.columns([1, 4])
        with col_badge:
            c = RISK_COLOURS[level.value]
            st.markdown(
                f"<div style='background:{c}; color:white; padding:8px; border-radius:6px; "
                f"text-align:center; font-weight:bold'>{level.value}</div>",
                unsafe_allow_html=True,
            )
        with col_text:
            st.markdown(f"**{dim_name}**: {rationale}")

    # PFAS fate in this pathway
    st.divider()
    fate = PFAS_PATHWAY_ASSUMPTIONS.get(score.pathway)
    if fate:
        st.markdown("**PFAS fate assumptions for this pathway**")
        fate_df = pd.DataFrame([
            {"Parameter": "Destruction efficiency",   "Value": f"{fate.pfas_destruction_efficiency*100:.0f}%"},
            {"Parameter": "PFAS retained in solid output", "Value": f"{fate.pfas_fraction_in_solid_output*100:.0f}%"},
            {"Parameter": "Leachate pathway fraction", "Value": f"{fate.leachate_pathway_fraction*100:.0f}%"},
            {"Parameter": "Concentration in solid output",  "Value": f"{pfas_result.pfas_concentration_after_pathway_ug_kg:,.0f} µg/kg DS"},
        ])
        st.dataframe(fate_df, use_container_width=True, hide_index=True)
        st.caption("⚠ All PFAS fate values are screening-level estimates. Thermal destruction efficiencies depend on specific operating conditions.")


def _render_pathway_comparison(all_scores, pfas_result) -> None:
    st.subheader("All Pathway Risk Comparison")
    st.caption(
        "Qualitative risk comparison for informing biosolids strategy. "
        "Lower scores indicate lower PFAS-related risk. "
        "This comparison does not include cost or carbon — see 05 Comparison for multi-criteria view."
    )

    # Radar/spider chart
    pathways = list(all_scores.keys())
    dims_keys = ["environmental_risk","regulatory_risk","public_perception_risk","long_term_liability_risk"]
    dims_display = ["Environmental", "Regulatory", "Public Perception", "Long-term Liability"]

    fig = go.Figure()
    colours = ["#1f6aa5","#ff7f0e","#2ca02c","#d62728","#9467bd","#8c564b"]
    for i, (pway, score) in enumerate(all_scores.items()):
        vals = [getattr(score, d).score for d in dims_keys]
        vals_closed = vals + [vals[0]]
        dims_closed = dims_display + [dims_display[0]]
        fig.add_trace(go.Scatterpolar(
            r=vals_closed, theta=dims_closed,
            name=PATHWAY_DISPLAY.get(pway, pway),
            line_color=colours[i % len(colours)],
            fill="none",
        ))

    fig.update_layout(
        polar=dict(radialaxis=dict(visible=True, range=[0,4],
                                    tickvals=[1,2,3,4],
                                    ticktext=["Low","Mod","High","V.High"])),
        height=450, title="PFAS Risk by Pathway and Dimension",
        legend=dict(orientation="h", y=-0.15),
    )
    st.plotly_chart(fig, use_container_width=True)

    # Comparison table
    rows = []
    for pway, score in all_scores.items():
        viable = PFAS_PATHWAY_ASSUMPTIONS[pway].pfas_viable
        rows.append({
            "Pathway":          score.display_name,
            "Environmental":    score.environmental_risk.value,
            "Regulatory":       score.regulatory_risk.value,
            "Public":           score.public_perception_risk.value,
            "Liability":        score.long_term_liability_risk.value,
            "Composite (1–4)":  score.composite_score,
            "Overall":          score.composite_level.value,
            "PFAS-viable?":     "✅ Yes" if viable else "⛔ Not recommended",
        })
    df = pd.DataFrame(rows)

    def colour_risk(val):
        c = RISK_COLOURS.get(val)
        return f"background-color:{c}; color:white; font-weight:bold" if c else ""

    try:
        styled = df.style.map(colour_risk, subset=["Environmental","Regulatory","Public","Liability","Overall"])
        st.dataframe(styled, use_container_width=True, hide_index=True)
    except Exception:
        st.dataframe(df, use_container_width=True, hide_index=True)

    st.info(
        "💡 **Key insight:** For biosolids with detectable PFAS, the two viable pathways that "
        "avoid environmental release are **Incineration** (highest destruction, most established) "
        "and **Gasification/Pyrolysis** (emerging, temperature-dependent). "
        "Land application and composting are not recommended where PFAS exceeds regulatory triggers."
    )


def _render_regulatory_context(pfas_result, pfas_inp) -> None:
    st.subheader("Regulatory Context")
    st.warning(
        "Regulatory values below are indicative as of 2024–2025 and are subject to rapid change. "
        "Users MUST verify current requirements in their jurisdiction."
    )

    reg_df = pd.DataFrame([
        {"Framework": "NSW EPA Interim Guidance (2023)",
         "Value": "100 µg/kg ∑PFAS (10 compounds)",
         "Applies to": "Land application of biosolids"},
        {"Framework": "EPA Victoria Guidance (2024)",
         "Value": "100 µg/kg ∑PFAS (10 compounds)",
         "Applies to": "Land application of biosolids"},
        {"Framework": "HEPA NEMP 2.0",
         "Value": "5 µg/kg PFOS+PFOA",
         "Applies to": "⚠ Drinking water source protection — NOT a biosolids limit"},
        {"Framework": "US EPA Proposed Rule (2023)",
         "Value": "0.071 µg/kg PFOS+PFOA",
         "Applies to": "Proposed US sewage sludge limit — not in force in Australia"},
        {"Framework": "EU Sludge Directive (under review)",
         "Value": "Not yet finalised",
         "Applies to": "EU — indicative of international regulatory direction"},
    ])
    st.dataframe(reg_df, use_container_width=True, hide_index=True)

    conc = pfas_result.pfas_concentration_cake_ug_kg
    compound = pfas_inp.pfas_compound_class
    st.markdown(f"**Your scenario:** {conc:,.0f} µg/kg DS ({compound})")

    if pfas_result.pfas_exceeds_nsw_trigger:
        st.error(
            f"⛔ Concentration ({conc:,.0f} µg/kg DS) EXCEEDS the NSW EPA and EPA Victoria "
            f"interim trigger for land application ({pfas_result.regulatory_trigger_nsw_ug_kg:.0f} µg/kg ∑PFAS). "
            "Land application is likely prohibited under current guidance."
        )
    else:
        st.success(
            f"✅ Concentration ({conc:,.0f} µg/kg DS) is below the NSW/VIC trigger. "
            "However, verify current requirements and confirm compound class matches the trigger basis."
        )

    st.info(
        "**Trend direction:** All Australian state EPAs and HEPA are moving toward "
        "stricter PFAS limits for biosolids. The US EPA proposed near-zero limits (2023) "
        "signal the likely long-term direction. Biosolids strategy planning should consider "
        "the trajectory of regulation, not just current values."
    )


def _render_assumptions(pfas_result) -> None:
    st.subheader("Assumptions and Calculation Notes")
    st.markdown(
        "The following assumptions and notes underpin this PFAS assessment. "
        "Review carefully before using results in any planning or reporting context."
    )
    for i, note in enumerate(pfas_result.notes, 1):
        if note.startswith("⚠"):
            st.warning(note)
        else:
            st.markdown(f"**{i}.** {note}")

    st.divider()
    st.markdown("**Version 1 limitations and suggested improvements for Version 2:**")
    improvements = [
        "**PFAS compound speciation:** Model uses a single ∑PFAS number. V2 should accept "
        "compound-specific data (PFOS, PFOA, PFBS, PFHxS, etc.) as these have different "
        "fate characteristics and regulatory thresholds.",
        "**Liquid stream fate:** The model assumes 10% of PFAS to liquid streams. "
        "V2 should include fate of PFAS in centrate/reject water returned to liquid line, "
        "and in treated effluent discharged to receiving water.",
        "**Site-specific receptor modelling:** V2 should allow input of groundwater depth, "
        "soil type, and distance to receptors to move from mass-based to pathway-specific "
        "exposure modelling (not a full risk assessment but better than mass balance only).",
        "**Concentration in digestion outputs:** Digestion concentrates PFAS in reject water. "
        "PFAS in reject water (centrate) returned to liquid line increases effluent PFAS load. "
        "This pathway is not currently modelled.",
        "**Temporal concentration change:** PFAS in biosolids from some catchments is declining "
        "as industrial sources are regulated. V2 should allow trend input.",
        "**Short-chain PFAS:** Short-chain PFAS (C4–C6) are increasingly replacing long-chain "
        "compounds. They have different mobility and treatment characteristics. "
        "V2 should distinguish compound class in fate calculations.",
    ]
    for imp in improvements:
        st.markdown(f"- {imp}")
