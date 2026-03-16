"""
apps/wastewater_app/pages/page_05_comparison.py

05 Scenario Comparison — full comparison table, bar charts, scatter plots.
"""

from __future__ import annotations
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd

from apps.ui.session_state import require_project, get_current_project
from apps.ui.ui_components import render_page_header, render_comparison_table
from core.project.project_manager import ProjectManager, ScenarioManager


def _get_compliance_summary(tech_perf_data: dict) -> str:
    """Summarise compliance status across all technologies in a scenario."""
    if not tech_perf_data:
        return "—"
    flags = [v.get("compliance_flag", "") for v in tech_perf_data.values()]
    if all(f == "Meets Targets" for f in flags if f):
        return "✅ Meets Targets"
    elif any(f == "Review Required" for f in flags):
        return "⚠️ Review Required"
    return "—"


def render() -> None:
    render_page_header("05 Scenario Comparison", "Side-by-side comparison across all calculated scenarios.")
    require_project()

    project   = get_current_project()
    scenarios = project.get_all_scenarios()
    calc      = [s for s in scenarios if s.cost_result]

    if len(calc) < 2:
        remaining = 2 - len(calc)
        st.info(
            f"At least 2 calculated scenarios are needed for comparison. "
            f"You currently have {len(calc)} — add {remaining} more and run calculations."
        )
        return

    sm = ScenarioManager()
    pm = ProjectManager()

    # ── Summary table ──────────────────────────────────────────────────────
    st.subheader("Multi-Criteria Comparison")
    rows = []
    for s in calc:
        aeration = s.domain_specific_outputs.get("aeration", {})
        # Pull energy metrics from technology_performance if aeration page not visited
        tech_perf_data = s.domain_specific_outputs.get("technology_performance", {})
        # Aggregate across all technologies in this scenario
        _kwh_kl   = s.domain_specific_outputs.get("engineering_summary", {}).get("specific_energy_kwh_kl", 0) or 0
        _kwh_nh4  = next((v.get("kwh_per_kg_nh4_removed") for v in tech_perf_data.values()
                          if v.get("kwh_per_kg_nh4_removed")), None)
        _o2_kg    = sum(v.get("o2_demand_kg_day", 0) or 0 for v in tech_perf_data.values())
        # Total footprint = sum of all technology footprints in this scenario
        _footprint = sum(v.get("footprint_m2", 0) or 0 for v in tech_perf_data.values())
        row = {
            "Scenario": s.scenario_name,
            "Technologies": (
                " + ".join(s.treatment_pathway.technology_sequence).upper()
                if s.treatment_pathway else "—"
            ),
            "CAPEX ($M)": round(s.cost_result.capex_total / 1e6, 2) if s.cost_result else None,
            "OPEX (k$/yr)": round(s.cost_result.opex_annual / 1e3, 0) if s.cost_result else None,
            "Lifecycle (k$/yr)": round(s.cost_result.lifecycle_cost_annual / 1e3, 0) if s.cost_result else None,
            "Footprint (m²)": round(_footprint, 0) if _footprint else "—",
            "Spec. Cost ($/kL)": round(s.cost_result.specific_cost_per_kl, 3) if s.cost_result and s.cost_result.specific_cost_per_kl else None,
            "Net Carbon (t/yr)": round(s.carbon_result.net_tco2e_yr, 0) if s.carbon_result else None,
            "Energy (kWh/kL)": round(_kwh_kl, 3),
            "kWh/ML (aeration)": aeration.get("kWh/ML Treated") or round(_kwh_kl * 1000, 0),
            "kWh/kg NH₄":        aeration.get("kWh/kg NH₄-N Removed") or (round(_kwh_nh4, 1) if _kwh_nh4 else "—"),
            "Blower Power (kW)": aeration.get("Avg Blower Power (kW)", "—"),
            "Annual Aerat. (MWh)": aeration.get("Annual Aeration Energy (MWh)") or round(_kwh_kl * 1000 * (s.domain_inputs.get("design_flow_mld", 10) if s.domain_inputs else 10) * 365 / 1000, 0),
            "Risk Level": s.risk_result.overall_level if s.risk_result else "—",
            "Risk Score": round(s.risk_result.overall_score, 0) if s.risk_result else None,
            "Compliance": _get_compliance_summary(tech_perf_data),
            "⭐ Preferred": "Yes" if s.is_preferred else "",
            "🔬 Calibrated": "Yes" if (s.domain_inputs or {}).get("_calibration_applied") else "",
        }
        # Add biosolids data
        bio = s.domain_specific_outputs.get("biosolids", {})
        sludge_data = bio.get("sludge", {})
        dig_data    = bio.get("digestion", {})
        wpc_data    = s.domain_specific_outputs.get("whole_plant_carbon", {})
        if sludge_data:
            row["Wet Cake (t/yr)"]        = sludge_data.get("Wet Cake (t/yr)", "—")
            row["Sludge Cost (k$/yr)"]    = round(sludge_data.get("Total Sludge Cost ($/yr)", 0) / 1000, 0) if sludge_data.get("Total Sludge Cost ($/yr)") else "—"
            row["Disposal Pathway"]       = sludge_data.get("Disposal Pathway", "—")
        if dig_data:
            row["CH₄ Gen (k m³/yr)"]      = round(dig_data.get("CH₄ Generated (m³/yr)", 0) / 1000, 0) if dig_data.get("CH₄ Generated (m³/yr)") else "—"
            row["CHP Output (MWh/yr)"]    = dig_data.get("Electricity Generated (MWh/yr)", "—")
        if wpc_data:
            row["Whole-plant Net (t/yr)"] = wpc_data.get("Net emissions (tCO₂e/yr)", "—")
            row["Whole-plant 30yr (t)"]   = wpc_data.get("Net 30yr (tCO₂e)", "—")
        # PFAS data
        pfas_data = s.domain_specific_outputs.get("pfas", {})
        if pfas_data:
            mb = pfas_data.get("mass_balance", {})
            rs = pfas_data.get("selected_pathway_risk", {})
            row["PFAS conc (µg/kg DS)"] = mb.get("PFAS conc. in cake (µg/kg DS)", "—")
            row["PFAS Risk Level"]       = rs.get("Overall Risk Level", "—")
            row["PFAS Score (1–4)"]      = rs.get("Composite Score (1–4)", "—")
        rows.append(row)

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)

    # ── Physical sizing comparison ─────────────────────────────────────────
    st.divider()
    st.subheader("📐 Physical Sizing Comparison")
    st.caption(
        "Bioreactor volume and footprint are the most reliable indicators of "
        "relative scale and civil cost at concept stage. These are derived from "
        "first-principles calculations (biomass loading, HRT, MLSS) and are more "
        "comparable across technologies than dollar estimates."
    )

    flow_mld = calc[0].domain_inputs.get("design_flow_mld", 10) if calc[0].domain_inputs else 10

    sizing_rows = []
    for s in calc:
        tp = s.domain_specific_outputs.get("technology_performance", {})
        tech_code = (s.treatment_pathway.technology_sequence[0]
                     if s.treatment_pathway else "")
        perf = tp.get(tech_code, {})
        vol  = perf.get("reactor_volume_m3", 0) or 0
        fp   = perf.get("footprint_m2", 0) or 0
        sizing_rows.append({
            "Scenario":               s.scenario_name,
            "Technology":             tech_code.upper().replace("_", "+"),
            "Bioreactor Vol (m³)":    round(vol, 0) if vol else "—",
            "m³ per MLD":             round(vol / flow_mld, 0) if vol and flow_mld else "—",
            "Footprint (m²)":         round(fp, 0) if fp else "—",
            "m² per MLD":             round(fp / flow_mld, 0) if fp and flow_mld else "—",
        })

    sizing_df = pd.DataFrame(sizing_rows)
    st.dataframe(sizing_df, use_container_width=True, hide_index=True)

    # Volume bar chart
    vol_names = [r["Scenario"] for r in sizing_rows]
    vol_vals  = [r["Bioreactor Vol (m³)"] for r in sizing_rows if isinstance(r["Bioreactor Vol (m³)"], (int, float))]
    if len(vol_vals) == len(vol_names):
        col_v1, col_v2 = st.columns(2)
        with col_v1:
            fig_vol = go.Figure(go.Bar(
                x=vol_names, y=vol_vals, marker_color="#1f6aa5",
                text=[f"{v:,.0f} m³" for v in vol_vals], textposition="auto",
            ))
            fig_vol.update_layout(yaxis_title="Bioreactor Volume (m³)",
                                  plot_bgcolor="white", height=300, showlegend=False,
                                  title="Bioreactor Volume (m³)")
            st.plotly_chart(fig_vol, use_container_width=True)
        with col_v2:
            vpm = [round(v / flow_mld, 0) for v in vol_vals]
            fig_vpm = go.Figure(go.Bar(
                x=vol_names, y=vpm, marker_color="#17becf",
                text=[f"{v:,.0f}" for v in vpm], textposition="auto",
            ))
            fig_vpm.update_layout(yaxis_title="m³ per MLD",
                                  plot_bgcolor="white", height=300, showlegend=False,
                                  title="Bioreactor Volume per MLD (m³/MLD)")
            st.plotly_chart(fig_vpm, use_container_width=True)

    st.caption(
        "ℹ️ **Interpretation:** Lower m³/MLD = more compact biological treatment. "
        "High MLSS (MBR, BNR+MBR) reduces volume; AGS SBR cycle management allows "
        "smaller reactors. Volume does not capture clarifier or membrane civil cost."
    )

    # ── CAPEX disclaimer ──────────────────────────────────────────────────
    st.divider()
    st.warning(
        "⚠️ **CAPEX figures are concept-level estimates (±40%) for relative comparison only.** "
        "They should NOT be used for procurement, funding approval, or detailed feasibility "
        "without site-specific cost estimation by a qualified cost estimator. "
        "Unit rates are indicative 2024 AUD and do not include: land, connections, "
        "electrical reticulation, buildings, or owner's costs. "
        "Use bioreactor volume and footprint above for more reliable technology comparison at this stage."
    )

    st.divider()

    # ── Calibration vs default annotation ─────────────────────────────────
    calibrated_scens = [s for s in calc if (s.domain_inputs or {}).get("_calibration_applied")]
    if calibrated_scens:
        st.info(
            f"🔬 **Calibrated scenarios detected:** "
            + ", ".join(f"**{s.scenario_name}**" for s in calibrated_scens)
            + " — results reflect plant-calibrated assumptions. "
            "Compare against uncalibrated scenarios to see the effect of calibration on cost, "
            "energy, and carbon estimates."
        )

    # ── Chart row 1: CAPEX bars + OPEX bars ───────────────────────────────
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("CAPEX Comparison ($M)")
        names  = [s.scenario_name for s in calc]
        capex  = [s.cost_result.capex_total / 1e6 for s in calc]
        fig = go.Figure(go.Bar(
            x=names, y=capex, marker_color="#1f6aa5",
            text=[f"${v:.2f}M" for v in capex], textposition="auto",
        ))
        fig.update_layout(yaxis_title="CAPEX ($M)", plot_bgcolor="white", height=320, showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.subheader("Annual OPEX (k$/yr)")
        opex = [s.cost_result.opex_annual / 1e3 for s in calc]
        colours = ["#2ca02c" if s.is_preferred else "#aec7e8" for s in calc]
        fig2 = go.Figure(go.Bar(
            x=names, y=opex, marker_color=colours,
            text=[f"${v:,.0f}k" for v in opex], textposition="auto",
        ))
        fig2.update_layout(yaxis_title="OPEX (k$/yr)", plot_bgcolor="white", height=320, showlegend=False)
        st.plotly_chart(fig2, use_container_width=True)

    # ── Chart row 1b: Footprint + Lifecycle cost ───────────────────────────
    col_fp, col_lc = st.columns(2)

    with col_fp:
        st.subheader("Footprint Comparison (m²)")
        footprints = []
        for s in calc:
            tp = s.domain_specific_outputs.get("technology_performance", {})
            fp = sum(v.get("footprint_m2", 0) or 0 for v in tp.values())
            footprints.append(round(fp, 0))
        if any(f > 0 for f in footprints):
            fp_colours = ["#17becf" if f == min(f for f in footprints if f > 0) else "#aec7e8"
                         for f in footprints]
            fig_fp = go.Figure(go.Bar(
                x=names, y=footprints, marker_color=fp_colours,
                text=[f"{v:,.0f} m²" for v in footprints], textposition="auto",
            ))
            fig_fp.update_layout(
                yaxis_title="Footprint (m²)", plot_bgcolor="white", height=320,
                showlegend=False,
                annotations=[dict(
                    text="🔵 Smallest footprint", x=0.01, y=1.05,
                    xref="paper", yref="paper", showarrow=False,
                    font=dict(size=11, color="#17becf")
                )]
            )
            st.plotly_chart(fig_fp, use_container_width=True)
            flow = calc[0].domain_inputs.get("design_flow_mld", 10) if calc[0].domain_inputs else 10
            fp_per_ml = [f / flow if f and flow else 0 for f in footprints]
            st.caption(
                "Footprint per MLD: " +
                " | ".join(f"{s.scenario_name}: **{fp:.0f} m²/MLD**"
                           for s, fp in zip(calc, fp_per_ml))
            )
            st.caption(
                "ℹ️ **Footprint basis:** biological reactor + clarifiers (BNR) or "
                "bioreactor only (MBR — no clarifier needed). "
                "MBR compact volume driven by high MLSS (10,000 mg/L). "
                "Excludes: screening, chemical dosing, sludge handling, access roads."
            )
        else:
            st.info("Footprint data not available — run calculations on Page 04 first.")

    with col_lc:
        st.subheader("Lifecycle Cost (k$/yr)")
        lc = [s.cost_result.lifecycle_cost_annual / 1e3 for s in calc]
        lc_colours = ["#2ca02c" if v == min(lc) else "#aec7e8" for v in lc]
        fig_lc = go.Figure(go.Bar(
            x=names, y=lc, marker_color=lc_colours,
            text=[f"${v:,.0f}k" for v in lc], textposition="auto",
        ))
        fig_lc.update_layout(
            yaxis_title="k$/yr (NPV annualised)", plot_bgcolor="white", height=320,
            showlegend=False,
        )
        st.plotly_chart(fig_lc, use_container_width=True)

    # ── Chart row 2: Carbon stacked + Energy bars ─────────────────────────
    carbon_scens = [s for s in calc if s.carbon_result]
    if carbon_scens:
        col3, col4 = st.columns(2)

        with col3:
            st.subheader("Carbon Breakdown (tCO₂e/yr)")
            fig3 = go.Figure()
            scopes = [
                ("Scope 1", [s.carbon_result.scope_1_tco2e_yr for s in carbon_scens], "#d62728"),
                ("Scope 2", [s.carbon_result.scope_2_tco2e_yr for s in carbon_scens], "#ff7f0e"),
                ("Scope 3", [s.carbon_result.scope_3_tco2e_yr for s in carbon_scens], "#9467bd"),
                ("Avoided", [-s.carbon_result.avoided_tco2e_yr for s in carbon_scens], "#2ca02c"),
            ]
            cnames = [s.scenario_name for s in carbon_scens]
            for scope_name, vals, colour in scopes:
                fig3.add_trace(go.Bar(name=scope_name, x=cnames, y=vals, marker_color=colour))
            fig3.update_layout(barmode="relative", yaxis_title="tCO₂e/yr",
                               plot_bgcolor="white", height=320, legend=dict(orientation="h"))
            st.plotly_chart(fig3, use_container_width=True)

        with col4:
            st.subheader("Net Carbon vs CAPEX")
            # Scatter: CAPEX vs risk — key comparison for capital planning
            scatter_data = {
                "Scenario":    [s.scenario_name for s in calc if s.risk_result],
                "CAPEX ($M)":  [s.cost_result.capex_total / 1e6 for s in calc if s.risk_result],
                "Risk Score":  [s.risk_result.overall_score for s in calc if s.risk_result],
                "Carbon (t/yr)": [s.carbon_result.net_tco2e_yr if s.carbon_result else 0
                                   for s in calc if s.risk_result],
            }
            if scatter_data["Scenario"]:
                fig4 = px.scatter(
                    scatter_data,
                    x="CAPEX ($M)", y="Risk Score",
                    text="Scenario",
                    size="Carbon (t/yr)" if any(v > 0 for v in scatter_data["Carbon (t/yr)"]) else None,
                    color="Scenario",
                    title="CAPEX vs Risk",
                    height=320,
                )
                fig4.update_traces(textposition="top center")
                fig4.update_layout(plot_bgcolor="white", showlegend=False)
                st.plotly_chart(fig4, use_container_width=True)

    # ── Chart row 3: Carbon vs Cost scatter ───────────────────────────────
    if len(carbon_scens) >= 2:
        st.subheader("Carbon vs Lifecycle Cost")
        carbon_cost_data = {
            "Scenario":         [s.scenario_name for s in carbon_scens],
            "Lifecycle (k$/yr)":[s.cost_result.lifecycle_cost_annual / 1e3 for s in carbon_scens],
            "Net Carbon (t/yr)":[s.carbon_result.net_tco2e_yr for s in carbon_scens],
            "Risk":             [s.risk_result.overall_score if s.risk_result else 10 for s in carbon_scens],
        }
        fig5 = px.scatter(
            carbon_cost_data,
            x="Lifecycle (k$/yr)", y="Net Carbon (t/yr)",
            text="Scenario", size="Risk", color="Scenario",
            title="Lifecycle Cost vs Net Carbon Emissions (bubble size = risk score)",
            height=380,
        )
        fig5.update_traces(textposition="top center")
        fig5.update_layout(plot_bgcolor="white", showlegend=False)
        st.plotly_chart(fig5, use_container_width=True)
        st.caption("Preferred options are towards the bottom-left — lower cost AND lower carbon.")

    # ── Aeration energy comparison ───────────────────────────────────────────
    # Use technology_performance data (always available) rather than aeration page data
    st.subheader("Energy Comparison")
    col_a, col_b = st.columns(2)

    with col_a:
        aer_names = [s.scenario_name for s in calc]
        kwh_ml_vals = [
            round((s.domain_specific_outputs.get("engineering_summary", {}).get("specific_energy_kwh_kl", 0) or 0) * 1000, 0)
            for s in calc
        ]
        fig_aer = go.Figure(go.Bar(
            x=aer_names, y=kwh_ml_vals, marker_color="#9467bd",
            text=[f"{v:,.0f}" for v in kwh_ml_vals], textposition="auto",
        ))
        fig_aer.update_layout(yaxis_title="kWh/ML", plot_bgcolor="white",
                              height=300, title="Total Energy Intensity (kWh/ML)")
        st.plotly_chart(fig_aer, use_container_width=True)

    with col_b:
        kwh_nh4_vals = []
        for s in calc:
            tech_perf = s.domain_specific_outputs.get("technology_performance", {})
            val = next((v.get("kwh_per_kg_nh4_removed") for v in tech_perf.values()
                       if v.get("kwh_per_kg_nh4_removed")), 0) or 0
            kwh_nh4_vals.append(round(val, 1))
        fig_nh4 = go.Figure(go.Bar(
            x=aer_names, y=kwh_nh4_vals, marker_color="#8c564b",
            text=[f"{v:.1f}" for v in kwh_nh4_vals], textposition="auto",
        ))
        fig_nh4.update_layout(yaxis_title="kWh/kg NH₄-N", plot_bgcolor="white",
                               height=300, title="Energy per kg NH₄-N Removed")
        st.plotly_chart(fig_nh4, use_container_width=True)

    # ── Biosolids comparison ─────────────────────────────────────────────────
    bio_data = [(s.scenario_name, s.domain_specific_outputs.get("biosolids",{}),
                 s.domain_specific_outputs.get("whole_plant_carbon",{})) for s in calc]
    bio_with_data = [(n,b,w) for n,b,w in bio_data if b]

    if len(bio_with_data) >= 2:
        st.subheader("Biosolids & Whole-Plant Carbon Comparison")
        col_a, col_b = st.columns(2)
        with col_a:
            b_names = [d[0] for d in bio_with_data]
            wet_cake = [d[1].get("sludge",{}).get("Wet Cake (t/yr)",0) for d in bio_with_data]
            fig_bw = go.Figure(go.Bar(x=b_names, y=wet_cake, marker_color="#8c564b",
                text=[f"{v:,.0f}" for v in wet_cake], textposition="auto"))
            fig_bw.update_layout(yaxis_title="t wet/yr", plot_bgcolor="white", height=300,
                                  title="Wet Cake Production (t/yr)")
            st.plotly_chart(fig_bw, use_container_width=True)
        with col_b:
            wpc_net = [d[2].get("Net emissions (tCO₂e/yr)", 0) for d in bio_with_data]
            colours_wpc = ["#2ca02c" if v < 0 else "#d62728" for v in wpc_net]
            fig_wpc = go.Figure(go.Bar(x=b_names, y=wpc_net, marker_color=colours_wpc,
                text=[f"{v:,.0f}" for v in wpc_net], textposition="auto"))
            fig_wpc.update_layout(yaxis_title="tCO₂e/yr", plot_bgcolor="white", height=300,
                                   title="Whole-Plant Net Emissions (tCO₂e/yr)")
            st.plotly_chart(fig_wpc, use_container_width=True)

        # Methane recovery chart
        chp_vals = [d[1].get("digestion",{}).get("Electricity Generated (MWh/yr)",0) for d in bio_with_data]
        if any(v for v in chp_vals):
            fig_chp = go.Figure(go.Bar(x=b_names, y=chp_vals, marker_color="#17becf",
                text=[f"{v:,.0f}" for v in chp_vals], textposition="auto"))
            fig_chp.update_layout(yaxis_title="MWh/yr", plot_bgcolor="white", height=280,
                                   title="CHP Electricity Generation (MWh/yr)")
            st.plotly_chart(fig_chp, use_container_width=True)

    # ── PFAS risk comparison ─────────────────────────────────────────────────
    pfas_data_list = [(s.scenario_name, s.domain_specific_outputs.get("pfas",{})) for s in calc]
    pfas_scenarios = [(n,d) for n,d in pfas_data_list if d.get("selected_pathway_risk")]

    if len(pfas_scenarios) >= 2:
        st.subheader("PFAS Risk Comparison")
        pfas_names  = [d[0] for d in pfas_scenarios]
        pfas_scores = [d[1]["selected_pathway_risk"].get("Composite Score (1–4)", 0) for d in pfas_scenarios]
        pfas_levels = [d[1]["selected_pathway_risk"].get("Overall Risk Level","") for d in pfas_scenarios]
        pfas_colours = [{"Low":"#2ca02c","Moderate":"#ff7f0e","High":"#d62728","Very High":"#7b0000"}.get(l,"#aaa") for l in pfas_levels]

        col_pf1, col_pf2 = st.columns(2)
        with col_pf1:
            fig_pf = go.Figure(go.Bar(
                x=pfas_names, y=pfas_scores, marker_color=pfas_colours,
                text=[f"{v:.1f} ({l})" for v,l in zip(pfas_scores,pfas_levels)],
                textposition="auto",
            ))
            fig_pf.update_layout(yaxis_title="PFAS Risk Score (1=Low, 4=Very High)",
                                  yaxis=dict(range=[0,4.5]),
                                  plot_bgcolor="white", height=300,
                                  title="PFAS Risk Score by Scenario")
            st.plotly_chart(fig_pf, use_container_width=True)
        with col_pf2:
            # Cost vs PFAS risk scatter
            cost_vals = [s.cost_result.lifecycle_cost_annual/1e3 if s.cost_result else None for s in calc]
            scatter_names = [s.scenario_name for s in calc]
            scatter_pfas  = [s.domain_specific_outputs.get("pfas",{}).get("selected_pathway_risk",{}).get("Composite Score (1–4)", None) for s in calc]
            valid = [(n, c, p) for n,c,p in zip(scatter_names,cost_vals,scatter_pfas) if c and p]
            if len(valid) >= 2:
                fig_sc = go.Figure(go.Scatter(
                    x=[v[1] for v in valid], y=[v[2] for v in valid],
                    mode="markers+text", text=[v[0] for v in valid],
                    textposition="top center",
                    marker=dict(size=14, color=[v[2] for v in valid],
                               colorscale=[[0,"#2ca02c"],[0.33,"#ff7f0e"],[0.67,"#d62728"],[1,"#7b0000"]]),
                ))
                fig_sc.update_layout(xaxis_title="Lifecycle Cost (k$/yr)",
                                      yaxis_title="PFAS Risk Score",
                                      yaxis=dict(range=[0,4.5]),
                                      plot_bgcolor="white", height=300,
                                      title="Cost vs PFAS Risk")
                st.plotly_chart(fig_sc, use_container_width=True)
        st.caption(
            "⚠ PFAS risk scores are qualitative and screening-level only. "
            "They reflect relative risk between pathways, not absolute risk magnitude."
        )

    # ── Set preferred ──────────────────────────────────────────────────────
    st.divider()
    st.subheader("⭐ Set Preferred Option")
    names_all = [s.scenario_name for s in scenarios]
    preferred = next((s for s in scenarios if s.is_preferred), None)
    sel = st.selectbox("Select preferred scenario",
        names_all, index=names_all.index(preferred.scenario_name) if preferred else 0)

    if st.button("Set as Preferred ⭐", type="primary"):
        sel_id = next((sid for sid, s in project.scenarios.items() if s.scenario_name == sel), None)
        if sel_id:
            sm.set_preferred(project, sel_id)
            pm.save(project)
            st.success(f"⭐ **{sel}** set as preferred option.")
            st.rerun()
