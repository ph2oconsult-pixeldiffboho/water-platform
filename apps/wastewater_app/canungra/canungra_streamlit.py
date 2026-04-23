"""
canungra_streamlit.py — WaterPoint UI for Canungra STP intensification analysis

Follows the WaterPoint conventions established for Healesville and Regional WWTP 
MABR analyses. Drops into apps/wastewater_app/canungra/ and is imported by the 
main WaterPoint navigation.

Usage from main WaterPoint app:
    from apps.wastewater_app.canungra.canungra_streamlit import render_canungra_tab
    
    with canungra_tab:
        render_canungra_tab()
"""
import json
from pathlib import Path
import streamlit as st

try:
    from .canungra_runner import (
        BardenphoSolver, DiurnalSimulator, LicenceLimits,
        assess_compliance, run_scenario, sweep_EP,
    )
except ImportError:
    from canungra_runner import (
        BardenphoSolver, DiurnalSimulator, LicenceLimits,
        assess_compliance, run_scenario, sweep_EP,
    )


# ============================================================================
# PATH RESOLUTION — find input files regardless of install location
# ============================================================================
def _resolve_path(filename: str) -> Path:
    candidates = [
        Path(__file__).parent / filename,
        Path.cwd() / filename,
        Path.cwd() / "apps" / "wastewater_app" / "canungra" / filename,
    ]
    for p in candidates:
        if p.exists():
            return p
    raise FileNotFoundError(f"{filename} not found in {candidates}")


@st.cache_data
def load_scenarios():
    return json.loads(_resolve_path("canungra_scenarios.json").read_text())


@st.cache_data
def load_profile():
    return json.loads(_resolve_path("canungra_diurnal_profile.json").read_text())


# ============================================================================
# MAIN RENDER FUNCTION
# ============================================================================
def render_canungra_tab():
    """Main entry point called from WaterPoint navigation."""
    scenarios_data = load_scenarios()
    profile = load_profile()
    scenarios = scenarios_data["scenarios"]
    kinetics = scenarios_data["kinetic_parameters"]
    meta = scenarios_data["metadata"]
    
    st.title("Canungra STP — 5-Stage Bardenpho Intensification")
    st.caption(f"Plant: {meta['plant']} · Licensed EP: {meta['licensed_design_EP']:,} · "
               f"TN median limit: **{meta['licence_limits']['TN_mgL_median_50']} mg/L (HARD)**")
    
    # Warning box on Bardenpho modelling
    st.info(
        "**5-stage Bardenpho architecture:** This plant has TWO distinct "
        "denitrification zones (primary anoxic on influent COD + post-anoxic "
        "on endogenous/dosed carbon). Effluent TN is **not** given by MLE "
        "formulas — it requires full mass balance across both anoxic zones."
    )
    
    # ========================================================================
    # LICENCE INTERPRETATION TOGGLE (sidebar, affects all tabs)
    # ========================================================================
    with st.sidebar:
        st.header("Licence interpretation")
        st.caption(
            "The 607 kg TN/yr annual mass limit was derived from the 1,500 EP "
            "design (Rev B Table 2.1 fn 1). At re-licensing, two interpretations "
            "are possible."
        )
        interpretation = st.radio(
            "Mass load basis",
            options=["B", "A"],
            format_func=lambda x: {
                "B": "B — scales with EP (Rev 17 adopted)",
                "A": "A — 607 kg/yr hard cap (conservative)",
            }[x],
            index=0,
            help=(
                "B (default, Rev 16+): mass limit = 607 × (EP / 1500) kg/yr. "
                "The concentration limits (5/10/15 mg/L) remain fixed.\n\n"
                "A: mass limit stays 607 kg/yr regardless of EP. This forces "
                "lower effluent TN at higher EP and caps S2 around 4,000 EP."
            ),
        )
        st.session_state["licence_interpretation"] = interpretation
        
        if interpretation == "A":
            st.warning(
                "Interpretation A binds S2 at 4,000 EP via the 607 kg/yr cap. "
                "This is the conservative regulatory outcome."
            )
        else:
            st.success(
                "Interpretation B (Rev 17 design basis) allows S2 to reach "
                "~6,000 EP, bound by peak TN at 15 mg/L under MML loading."
            )
        
        st.divider()
        st.caption(
            "**RFC-10** (HIGH priority): confirm mass load basis with the "
            "regulator before Phase 2 pre-feasibility."
        )
    
    # ========================================================================
    # TAB STRUCTURE
    # ========================================================================
    tab_overview, tab_single, tab_sweep, tab_diurnal, tab_dil = st.tabs([
        "Overview",
        "Single-point Analysis",
        "EP Capacity Sweep",
        "Diurnal Compliance",
        "Decision Intelligence",
    ])
    
    with tab_overview:
        render_overview_tab(scenarios, meta)
    
    with tab_single:
        render_single_point_tab(scenarios, profile, kinetics)
    
    with tab_sweep:
        render_sweep_tab(scenarios, profile, kinetics)
    
    with tab_diurnal:
        render_diurnal_tab(scenarios, profile, kinetics)
    
    with tab_dil:
        render_dil_tab(scenarios, profile, kinetics, meta)


# ============================================================================
# TAB: OVERVIEW
# ============================================================================
def render_overview_tab(scenarios: dict, meta: dict):
    st.subheader("Intensification Scenarios")
    
    # Friendly display names for the 8 scenarios
    scenario_display_names = {
        "S0_rev_b_baseline": "S0",
        "S1A_controls_only": "S1A",
        "S1B_controls_plus_ifas": "S1B",
        "S2_A_combined": "S2-A",
        "S2_B_parallel": "S2-B",
        "S2_C3_series_parallel": "S2-C3 ★",
        "S2_D_parallel_only": "S2-D",
        "S2_E_aerobic_shifted": "S2-E ★",
        "S2_ifas_plus_postanox": "(legacy)",
    }
    
    scenario_table = []
    for name, scen in scenarios.items():
        if name == "S2_ifas_plus_postanox":
            continue  # Hide the legacy alias from overview
        scenario_table.append({
            "ID": scenario_display_names.get(name, name.split("_")[0].upper()),
            "Description": scen["description"][:70] + ("..." if len(scen["description"]) > 70 else ""),
            "Post-anoxic (kL)": scen["zone_volumes_kL"]["post_anoxic"],
            "MBR (kL)": scen["zone_volumes_kL"]["MBR_tanks"],
            "IFAS": "Yes" if scen["ifas"]["enabled"] else "No",
            "MBR type": scen["membrane"]["type"],
        })
    
    st.table(scenario_table)
    
    # Capacity ladder table (Rev 17 Interpretation B values)
    st.subheader("Capacity ladder under Interpretation B (Rev 17 design basis)")
    st.caption(
        "Maximum EP capacity for each scenario under the adopted Interpretation B "
        "licence basis (mass limit scales with EP). See sidebar to switch to "
        "Interpretation A for the conservative case."
    )
    
    capacity_rows = [
        {"Scenario": "S0 Rev B baseline", "Max EP": "1,500", "Capex (AUD)": "baseline",
         "Binding constraint": "Current licence (Rev B design)"},
        {"Scenario": "S1A Controls only", "Max EP": "1,900", "Capex (AUD)": "~280k",
         "Binding constraint": "Peak TN (MML)"},
        {"Scenario": "S1B S1A + IFAS", "Max EP": "2,100", "Capex (AUD)": "~900k",
         "Binding constraint": "Peak TN (MML)"},
        {"Scenario": "S2-D Parallel-only (118 kL)", "Max EP": "4,500", "Capex (AUD)": "~3.30M",
         "Binding constraint": "Peak TN (MML)"},
        {"Scenario": "S2-C3 ★ Recommended (142 kL)", "Max EP": "5,500", "Capex (AUD)": "~3.56M",
         "Binding constraint": "Peak TN (MML)"},
        {"Scenario": "S2-A/B (156 kL)", "Max EP": "6,000", "Capex (AUD)": "3.36M / 3.62M",
         "Binding constraint": "Peak TN (MML) at 14.7 mg/L"},
    ]
    st.table(capacity_rows)
    
    # Decision tree
    st.subheader("S2 variant decision tree")
    st.caption(
        "Preferred concepts for pre-feasibility development, by catchment growth horizon. "
        "Two preferred concepts sit alongside each other at 4,000-5,500 EP: "
        "S2-C3 (conservative post-anoxic) and S2-E (aerobic-shifted with flow balancing). "
        "Choice depends on RFC-04 (S2-C3 hydraulics) and RFC-12 (S2-E flow balancing simulation)."
    )
    
    decision_rows = [
        {"Growth horizon": "≤ 4,000 EP", "Wall removal?": "Either",
         "Preferred concept": "S2-D (lowest cost, 4,500 EP capacity)"},
        {"Growth horizon": "4,000 – 5,500 EP", "Wall removal?": "Either",
         "Preferred concept": "S2-C3 ★ or S2-E ★ (parallel preferred concepts)"},
        {"Growth horizon": "5,500 – 6,000 EP", "Wall removal?": "No (RFC-05 concern)",
         "Preferred concept": "S2-E ★ (flow balancing) or S2-B (parallel)"},
        {"Growth horizon": "5,500 – 6,000 EP", "Wall removal?": "Yes (RFC-05 safe)",
         "Preferred concept": "S2-A (combined, demolish wall) or S2-E"},
        {"Growth horizon": "> 6,000 EP", "Wall removal?": "Either",
         "Preferred concept": "S2 exceeded — external post-anoxic or new aerobic"},
    ]
    st.table(decision_rows)
    
    # ========================================================================
    # DISCHARGE LOAD — ENVIRONMENTAL CONTEXT (Rev 17 Section 5.4)
    # ========================================================================
    st.subheader("Annual TN discharge load — environmental context")
    st.caption(
        "The intensification scenarios deliver more EP capacity but at higher total "
        "annual TN discharge to the receiving waterway. S1A/S1B discharge essentially "
        "the same as S0 (~580 kg/yr). S2 variants step up 2-2.3× due to serving more "
        "people. Treatment efficiency (%TN removal) actually improves from 91% at S0 "
        "to 95% at S2-C3."
    )
    
    discharge_rows = [
        {"Scenario": "S0 Rev B baseline", "Design EP": "1,500",
         "TN discharge (kg/yr)": "578", "× vs S0": "1.00×",
         "% licence (Interp B)": "95% of 607"},
        {"Scenario": "S1A Controls only", "Design EP": "1,900",
         "TN discharge (kg/yr)": "587", "× vs S0": "1.02×",
         "% licence (Interp B)": "76% of 769"},
        {"Scenario": "S1B S1A + IFAS", "Design EP": "2,100",
         "TN discharge (kg/yr)": "583", "× vs S0": "1.01×",
         "% licence (Interp B)": "69% of 850"},
        {"Scenario": "S2-D Parallel-only", "Design EP": "4,500",
         "TN discharge (kg/yr)": "744", "× vs S0": "1.29×",
         "% licence (Interp B)": "41% of 1,821"},
        {"Scenario": "S2-C3 ★ Recommended", "Design EP": "5,500",
         "TN discharge (kg/yr)": "1,171", "× vs S0": "2.03×",
         "% licence (Interp B)": "53% of 2,226"},
        {"Scenario": "S2-A/B Full 156 kL", "Design EP": "6,000",
         "TN discharge (kg/yr)": "1,338", "× vs S0": "2.31×",
         "% licence (Interp B)": "55% of 2,428"},
    ]
    st.table(discharge_rows)
    
    st.warning(
        "**RFC-11 — receiving water assessment (MEDIUM-HIGH priority):** "
        "Doubling total TN discharge under S2 configurations requires catchment "
        "authority engagement. This Concept Study does NOT assess: receiving "
        "water assimilative capacity, catchment-wide cumulative nitrogen load, "
        "seasonal algal/DO effects, downstream beneficial use protection, or the "
        "Coomera River / Gold Coast Broadwater receiving environment status. "
        "Estimated cost AUD 40-80k; timeline 6-12 months."
    )
    
    st.subheader("Licence Limits")
    lim = meta["licence_limits"]
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("TN median", f"{lim['TN_mgL_median_50']} mg/L")
        st.metric("TN 80%ile", f"{lim['TN_mgL_80ile']} mg/L")
    with c2:
        st.metric("TN max", f"{lim['TN_mgL_max']} mg/L")
        st.metric("TN mass (1,500 EP)", f"{lim['TN_mass_kg_per_year']} kg/yr",
                  help="Rev B derivation: 5 mg/L × 300 kL/d × 365 × 1.10 ≈ 607 kg/yr")
    with c3:
        st.metric("TP median", f"{lim['TP_mgL_median_50']} mg/L")
        st.metric("NH3 max", f"{lim['NH3_mgL_max']} mg/L")
    
    st.subheader("Rev B Diurnal Profile (Figure 3.1)")
    st.caption("From the 2012 design report — 30-minute resolution")
    profile = load_profile()
    
    try:
        import pandas as pd
        df = pd.DataFrame(profile["data"])
        st.line_chart(df.set_index("t_h")[["flow", "tkn", "cod"]])
    except ImportError:
        st.write("Install pandas for profile visualisation")
    
    st.caption("Peak flow 2.26× ADWF at 08:30 · Peak TKN 1.30× at 10:00 · "
               "Combined peak LOAD 2.66× daily mean")


# ============================================================================
# TAB: SINGLE-POINT ANALYSIS
# ============================================================================
def render_single_point_tab(scenarios: dict, profile: dict, kinetics: dict):
    st.subheader("Single-Point Analysis")
    st.caption("Run one scenario at a specific EP, loading, temperature, and MeOH dose.")
    
    interpretation = st.session_state.get("licence_interpretation", "B")
    
    # Friendly scenario labels for the 8 variants
    scenario_labels = {
        "S0_rev_b_baseline": "S0 — Rev B baseline",
        "S1A_controls_only": "S1A — Controls only (no-regret)",
        "S1B_controls_plus_ifas": "S1B — S1A + IFAS aerobic",
        "S2_A_combined": "S2-A — Combined 156 kL (wall removed)",
        "S2_B_parallel": "S2-B — Parallel 38+59+59 (wall retained)",
        "S2_C3_series_parallel": "S2-C3 ★ — Series-parallel (preferred concept)",
        "S2_D_parallel_only": "S2-D — Parallel-only (38 kL decomm)",
        "S2_E_aerobic_shifted": "S2-E ★ — Aerobic-shifted with flow balancing (preferred concept)",
        "S2_ifas_plus_postanox": "(legacy alias — same as S2-A)",
    }
    # Display order: S0 → S1A → S1B → S2 variants in rough capacity order
    scenario_order = [
        "S0_rev_b_baseline", "S1A_controls_only", "S1B_controls_plus_ifas",
        "S2_D_parallel_only", "S2_C3_series_parallel", "S2_E_aerobic_shifted",
        "S2_A_combined", "S2_B_parallel",
    ]
    selectable = [k for k in scenario_order if k in scenarios]
    
    c1, c2, c3 = st.columns(3)
    with c1:
        scen_key = st.selectbox(
            "Scenario", selectable,
            index=selectable.index("S2_C3_series_parallel") if "S2_C3_series_parallel" in selectable else 0,
            format_func=lambda x: scenario_labels.get(x, x),
        )
        loading = st.selectbox("Loading", ["AAL", "MML"])
    with c2:
        EP = st.number_input("EP", 500, 7000, 1500, 250)
        T_C = st.slider("Temperature (°C)", 12, 30, 17)
    with c3:
        MeOH_mode = st.radio("MeOH dosing", ["Auto-find minimum", "Specify L/d"])
        if MeOH_mode == "Specify L/d":
            MeOH_Ld = st.number_input("MeOH (L/d)", 0, 400, 20, 5)
        else:
            MeOH_Ld = None
        flow_paced = st.checkbox("Flow-paced A-recycle", value=True,
                                  help="Recommended for intensified configs (S1A+)")
    
    # Show the scenario description and active interpretation
    st.caption(f"**Active scenario:** {scenarios[scen_key]['description']}")
    st.caption(f"**Licence interpretation:** {interpretation} — "
               f"mass limit at {EP:,} EP = "
               f"**{607 if interpretation == 'A' else 607 * EP / 1500:.0f} kg/yr**")
    
    if st.button("Run Analysis", type="primary"):
        with st.spinner("Solving..."):
            result = run_scenario(
                scen_key, scenarios, profile, kinetics,
                EP=EP, loading=loading, T_C=T_C,
                MeOH_Ld=MeOH_Ld, flow_paced_A=flow_paced,
                licence_interpretation=interpretation,
            )
        
        compl = result["compliance"]
        
        st.subheader("Results")
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.metric("Flow-weighted TN", f"{compl['flow_weighted_mean']:.2f} mg/L",
                      delta=f"{compl['flow_weighted_mean'] - 5:.2f} vs limit 5",
                      delta_color="inverse")
        with c2:
            st.metric("80%ile TN", f"{compl['p80']:.2f} mg/L",
                      delta=f"{compl['p80'] - 10:.2f} vs limit 10",
                      delta_color="inverse")
        with c3:
            st.metric("Peak TN", f"{compl['peak']:.2f} mg/L",
                      delta=f"{compl['peak'] - 15:.2f} vs limit 15",
                      delta_color="inverse")
        with c4:
            st.metric("MeOH", f"{result['MeOH_Ld']:.0f} L/d")
        
        if compl["overall_pass"]:
            st.success("✓ All TN limits met")
        else:
            fails = []
            if not compl["median_pass"]: fails.append("Median")
            if not compl["p80_pass"]: fails.append("80%ile")
            if not compl["max_pass"]: fails.append("Max")
            st.error(f"✗ Failed: {', '.join(fails)}")
        
        c1, c2 = st.columns(2)
        with c1:
            st.write(f"**MLSS bio:** {result['MLSS_bio']:.0f} mg/L")
            st.write(f"**MLSS MBR:** {result['MLSS_MBR']:.0f} mg/L")
        with c2:
            st.write(f"**Annual TN mass:** {compl['annual_mass_kg']:.0f} kg/yr "
                    f"(limit {607 if interpretation == 'A' else int(607 * EP / 1500)} "
                    f"under Interp {interpretation})")
            st.write(f"**A-recycle mode:** "
                    f"{'flow-paced' if result['flow_paced_A'] else 'fixed absolute'}")
        
        # Time-series plot
        try:
            import pandas as pd
            df = pd.DataFrame(result["series"])
            st.subheader("Diurnal TN Trace (MBR-buffered)")
            st.line_chart(df.set_index("t_h")[["TN_buffered", "NO3_unbuffered"]])
        except ImportError:
            pass


# ============================================================================
# TAB: EP CAPACITY SWEEP
# ============================================================================
def render_sweep_tab(scenarios: dict, profile: dict, kinetics: dict):
    st.subheader("EP Capacity Sweep")
    st.caption("Find the maximum EP each scenario supports while meeting all TN limits.")
    
    interpretation = st.session_state.get("licence_interpretation", "B")
    st.caption(f"**Active interpretation:** {interpretation} — see sidebar to change.")
    
    c1, c2 = st.columns(2)
    with c1:
        T_C = st.slider("Temperature (°C)", 12, 30, 17, key="sweep_T")
        ep_min = st.number_input("EP min", 500, 3000, 1500, 250)
    with c2:
        ep_max = st.number_input("EP max", 1500, 7000, 6500, 250)
        ep_step = st.number_input("EP step", 50, 500, 250, 50)
    
    compare_recycle = st.checkbox("Compare fixed vs flow-paced A-recycle", value=True)
    
    # Exclude the legacy alias from sweep default
    skip_legacy = st.checkbox("Skip legacy S2_ifas_plus_postanox alias (same as S2-A)", value=True)
    
    if st.button("Run Sweep", type="primary"):
        rows = []
        progress = st.progress(0)
        
        scenario_list = [k for k in scenarios.keys()
                          if not (skip_legacy and k == "S2_ifas_plus_postanox")]
        for i, scen_key in enumerate(scenario_list):
            with st.spinner(f"Running {scen_key}..."):
                # Fixed A-recycle
                sweep_fixed = sweep_EP(
                    scen_key, scenarios, profile, kinetics,
                    EP_range=range(ep_min, ep_max + 1, ep_step),
                    T_C=T_C, flow_paced_A=False,
                    licence_interpretation=interpretation,
                )
                max_EP_fixed = max((r["EP"] for r in sweep_fixed if r["pass_both"]),
                                    default=0)
                
                if compare_recycle:
                    sweep_paced = sweep_EP(
                        scen_key, scenarios, profile, kinetics,
                        EP_range=range(ep_min, ep_max + 1, ep_step),
                        T_C=T_C, flow_paced_A=True,
                        licence_interpretation=interpretation,
                    )
                    max_EP_paced = max((r["EP"] for r in sweep_paced if r["pass_both"]),
                                        default=0)
                    rows.append({
                        "Scenario": scen_key.replace("_", " ").title()[:20],
                        "Description": scenarios[scen_key]["description"][:50],
                        "Max EP (fixed A)": max_EP_fixed,
                        "Max EP (flow-paced A)": max_EP_paced,
                        "Gain from control": max_EP_paced - max_EP_fixed,
                    })
                else:
                    rows.append({
                        "Scenario": scen_key.split("_")[0].upper(),
                        "Description": scenarios[scen_key]["description"][:50],
                        "Max EP": max_EP_fixed,
                    })
            
            progress.progress((i + 1) / len(scenario_list))
        
        st.subheader("Capacity by Scenario")
        st.table(rows)
        
        try:
            import pandas as pd
            df = pd.DataFrame(rows)
            if "Max EP (flow-paced A)" in df.columns:
                chart_df = df.set_index("Scenario")[["Max EP (fixed A)", "Max EP (flow-paced A)"]]
                st.bar_chart(chart_df)
        except ImportError:
            pass


# ============================================================================
# TAB: DIURNAL COMPLIANCE
# ============================================================================
def render_diurnal_tab(scenarios: dict, profile: dict, kinetics: dict):
    st.subheader("Diurnal Compliance")
    st.caption("Visualise the full 24-hour TN trace through Rev B Figure 3.1 loading.")
    
    c1, c2, c3 = st.columns(3)
    with c1:
        # Exclude legacy alias from options
        selectable_keys = [k for k in scenarios.keys() if k != "S2_ifas_plus_postanox"]
        scen_keys = st.multiselect("Scenarios to compare",
                                    selectable_keys,
                                    default=["S0_rev_b_baseline", "S2_C3_series_parallel", "S2_E_aerobic_shifted"])
    with c2:
        EP = st.number_input("EP", 500, 7000, 4000, 250, key="diurnal_EP")
        T_C = st.slider("Temperature (°C)", 12, 30, 17, key="diurnal_T")
    with c3:
        loading = st.selectbox("Loading", ["AAL", "MML"], key="diurnal_load")
        flow_paced = st.checkbox("Flow-paced A-recycle", value=True, key="diurnal_fp")
    
    if st.button("Run Diurnal Simulation", type="primary"):
        interpretation = st.session_state.get("licence_interpretation", "B")
        try:
            import pandas as pd
        except ImportError:
            st.error("pandas required for this tab")
            return
        
        all_series = {}
        compliance_rows = []
        for scen_key in scen_keys:
            with st.spinner(f"{scen_key}..."):
                result = run_scenario(
                    scen_key, scenarios, profile, kinetics,
                    EP=EP, loading=loading, T_C=T_C,
                    flow_paced_A=flow_paced,
                    licence_interpretation=interpretation,
                )
                short = scen_key.replace("_", " ").title()[:15]
                all_series[short] = result["series"]
                compl = result["compliance"]
                compliance_rows.append({
                    "Scenario": short,
                    "FWM TN": round(compl["flow_weighted_mean"], 2),
                    "50%ile": round(compl["p50"], 2),
                    "80%ile": round(compl["p80"], 2),
                    "Peak": round(compl["peak"], 2),
                    "MeOH (L/d)": result["MeOH_Ld"],
                    "Pass": "✓" if compl["overall_pass"] else "✗",
                })
        
        st.subheader("Compliance Summary")
        st.table(compliance_rows)
        
        st.subheader("Permeate TN — 24-hour trace")
        plot_df = pd.DataFrame({"t_h": [p["t_h"] for p in all_series[list(all_series.keys())[0]]]})
        for short, series in all_series.items():
            plot_df[short] = [s["TN_buffered"] for s in series]
        st.line_chart(plot_df.set_index("t_h"))
        
        st.caption("Horizontal reference lines: 5 mg/L (median), 10 mg/L (80%ile), "
                    "15 mg/L (max)")


# ============================================================================
# TAB: DECISION INTELLIGENCE
# ============================================================================
def render_dil_tab(scenarios: dict, profile: dict, kinetics: dict, meta: dict):
    st.subheader("9-Part Decision Intelligence Framework")
    st.caption("Structured analysis output for investment decision memo.")
    
    with st.expander("1. Decision Question", expanded=True):
        st.write(
            "Should Canungra STP be **intensified** within existing tankage "
            "(IFAS + enlarged post-anoxic + optional HF MBR) to support ~3,000 EP, "
            "or should a **greenfield expansion** be planned instead?"
        )
        st.write(f"**Hard constraint:** TN median ≤ 5 mg/L")
    
    with st.expander("2. Options"):
        st.write("""
        - **Option A:** Status quo (Rev B baseline, max ~1,800 EP diurnal-derated)
        - **Option B (S1):** +IFAS only (~2,000 EP, ~$410k capex)
        - **Option C (S2):** +IFAS +PostAnox expansion (~3,000 EP, ~$710k)
        - **Option D (S3):** Full stack +HF MBR (~3,000 EP, ~$1.2M)
        - **Option E:** Greenfield expansion ($15-25M)
        """)
    
    with st.expander("3. Criteria (weighted)"):
        criteria = {
            "TN compliance reliability": 0.30,
            "EP capacity delivered": 0.25,
            "Capex": 0.15,
            "Annual OPEX": 0.10,
            "Operational complexity": 0.10,
            "Future flexibility": 0.10,
        }
        for k, v in criteria.items():
            st.write(f"- **{k}** (weight: {v:.0%})")
    
    with st.expander("4. Scoring (populate after simulation run)"):
        st.info("Scoring requires the full EP sweep and capex analysis — run the "
                 "'EP Capacity Sweep' tab first.")
    
    with st.expander("5. Key Uncertainties"):
        st.write("""
        - **K2 primary anoxic (20°C):** 0.050-0.090 (mid 0.072)
        - **IFAS biofilm nit flux (17°C):** 0.4-0.9 gN/m²/d (mid 0.70)
        - **Post-anoxic endogenous rate (17°C):** 0.012-0.028 gN/gVSS/d (mid 0.020)
        - **SBCOD hydrolysis boost:** 1.0-1.4 (mid 1.2)
        - **MeOH stoichiometry:** 3.0-4.5 gMeOH/gN (mid 3.5)
        - **Catchment growth rate:** 1500→2500 EP by 2035? or 1500→4000 by 2040?
        """)
    
    with st.expander("6. Sensitivity (tornado)"):
        st.info("Run sensitivity sweep via `python3 canungra_runner.py --sensitivity`")
    
    with st.expander("7. Feasibility"):
        st.write("""
        **S2 (+IFAS +PostAnox)** assessed as MOST FEASIBLE:
        - Uses existing tankage (no civils uplift required for most volume)
        - Kubota membranes retained → vendor support intact
        - IFAS retrofit is well-proven at this scale
        - Primary risk: carrier retention screen fouling with fine rags
        
        **S3 (+HF MBR)** adds complexity:
        - Membrane procurement lead time 6-9 months
        - Membrane changeover requires full plant shutdown or temp bypass
        - Hazardous area reclassification for MeOH storage
        
        **Licence approval risk:** LOW for both options if biology holds at
        5 mg/L TN. Regulator (EPA QLD) generally supports incremental
        optimisation of existing assets over greenfield expansion.
        """)
    
    with st.expander("8. Credibility"):
        st.write("""
        **Model calibration:**
        - Predictions validated against Rev B BioWIN (agreement ±30%)
        - Diurnal profile from Rev B Figure 3.1 directly
        - Kinetics need replacement with SE QLD calibrated values (see readme)
        
        **Uncertainty bands at this confidence level:** ±20-25% on EP capacity
        estimates. Commitment-grade numbers require:
        - BioWin dynamic simulation with calibrated kinetics
        - 10-day pilot or mass balance verification
        - Vendor membrane sizing confirmation
        """)
    
    with st.expander("9. Recommendation"):
        st.write("""
        **Preliminary recommendation:** Proceed to pre-feasibility design of
        **Scenario S2 with flow-paced A-recycle control**. This delivers:
        
        - ~3,000 EP capacity (2× current) for ~$710k capex
        - Preserves existing MBR investment
        - No-capex control improvement captures significant diurnal margin
        - Staged approach leaves HF MBR as future option if needed
        
        **Gate the decision on:**
        1. SE QLD kinetic calibration (replace defaults)
        2. Cold-snap robustness check (14°C winter with peak diurnal)
        3. Vendor quotes for IFAS carriers and retention screens
        4. QUU growth projection confirmation (2,500 vs 3,500 EP by 2035)
        """)


if __name__ == "__main__":
    render_canungra_tab()
