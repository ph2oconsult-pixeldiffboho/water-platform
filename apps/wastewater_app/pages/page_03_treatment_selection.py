"""
apps/wastewater_app/pages/page_03_treatment_selection.py

03 Treatment Options — all six treatment pathways with configuration panels.
"""

from __future__ import annotations
import streamlit as st
from apps.ui.session_state import (
    require_project, get_current_project, update_current_project,
    get_active_scenario, mark_scenario_stale,
)
from apps.ui.ui_components import render_page_header, render_scenario_selector
from core.project.project_model import TreatmentPathway, PlanningScenario
from core.project.project_manager import ProjectManager

TECHNOLOGIES = {
    "bnr": {
        "name": "BNR with Secondary Clarifiers",
        "icon": "🔵",
        "description": "Biological N and P removal via A2O/Bardenpho/UCT with gravity secondary clarifiers. The standard proven configuration for municipal BNR.",
        "strengths":  ["Low capital cost", "Widely proven (10,000+ plants)", "Flexible configuration", "Simple O&M"],
        "limitations": ["Largest footprint (clarifiers required)", "Settling-dependent effluent quality", "TSS typically 10–15 mg/L"],
        "best_for": ["capacity_expansion", "nutrient_limit_tightening"],
    },
    "bnr_mbr": {
        "name": "BNR + MBR Hybrid (BNR Basins + Membrane Separation)",
        "icon": "🔵🟣",
        "description": "Conventional BNR basins at moderate MLSS (4,000 mg/L) feeding a separate membrane separation tank. Replaces clarifiers while retaining BNR biology. Good upgrade/retrofit path and reuse precursor.",
        "strengths":  ["Lower energy than integrated MBR", "Retains BNR basin investment", "Optional clarifier standby", "TSS < 1 mg/L", "Reuse pathway"],
        "limitations": ["Larger footprint than integrated MBR", "More complex inter-zone piping", "Two-zone O&M"],
        "best_for": ["reuse_prw_integration", "capacity_expansion", "nutrient_limit_tightening"],
    },
    "mabr_bnr": {
        "name": "MABR + BNR (Membrane Aerated Biofilm Reactor in Anoxic Zone)",
        "icon": "🟤",
        "description": "MABR modules in the primary anoxic zone deliver O₂ bubble-free into a biofilm at ~95% OTE. Biofilm nitrifies 30% of NH₄ load; bulk anoxic liquid denitrifies simultaneously. Aerobic zone reduced 30%. Conventional blowers retained for remaining 70% of NH₄ + BOD. ~15-20% net energy saving vs BNR.",
        "strengths":  ["~15-20% aeration energy saving", "30% smaller aerobic zone", "Retrofit into existing anoxic zone", "No new tankage (retrofit)", "SND reduces external carbon need"],
        "limitations": ["Emerging technology (<50 full-scale plants)", "Clarifiers still required", "Membrane replacement costs uncertain", "Limited vendor base"],
        "best_for": ["energy_optimisation", "carbon_reduction", "capacity_expansion"],
    },
    "granular_sludge": {
        "name": "Aerobic Granular Sludge (Nereda®)",
        "icon": "🟢",
        "description": "Granule-based sequencing batch reactor. Simultaneous N and P removal in a compact footprint. Very low sludge production.",
        "strengths":  ["Low energy vs CAS", "Compact", "Simultaneous N+P removal", "Low sludge"],
        "limitations": ["Fewer references than CAS/MBR", "SBR cycle management"],
        "best_for": ["energy_optimisation", "carbon_reduction", "biosolids_constraints"],
    },
    "ifas_mbbr": {
        "name": "IFAS / MBBR Retrofit",
        "icon": "🟡",
        "description": "Media carriers added to existing tanks to boost nitrification capacity without new tankage. Ideal for upgrades under land constraints.",
        "strengths":  ["Retrofit friendly", "No new tanks required", "Low disruption"],
        "limitations": ["Lower TN removal than full BNR", "Media management"],
        "best_for": ["capacity_expansion", "nutrient_limit_tightening"],
    },
    "anmbr": {
        "name": "Anaerobic Treatment (AnMBR / UASB)",
        "icon": "🔴",
        "description": "Anaerobic digestion of wastewater with membrane polishing. Net energy producer. Very low sludge yield. Requires post-treatment for nutrient removal.",
        "strengths":  ["Energy positive", "Very low sludge", "Low footprint"],
        "limitations": ["Temperature sensitive", "Requires aerobic polishing", "Higher CAPEX"],
        "best_for": ["energy_optimisation", "carbon_reduction", "biosolids_constraints"],
    },
    "sidestream_pna": {
        "name": "Sidestream PN/A (Anammox)",
        "icon": "🟠",
        "description": "Partial nitritation-Anammox on sludge reject water. Removes 20–30% of plant-wide nitrogen load with minimal energy and no external carbon.",
        "strengths":  ["Very low energy", "No external carbon", "Reduces main plant N load"],
        "limitations": ["Sidestream only", "Temperature sensitive", "Complex microbiology"],
        "best_for": ["energy_optimisation", "nutrient_limit_tightening"],
    },
    "mob": {
        "name": "Mobile Organic Biofilm (MOB)",
        "icon": "🔵",
        "description": "Suspended biodegradable carrier process. Sludge yield 40–60% lower than CAS. Can retrofit into existing aeration basins with no new concrete.",
        "strengths":  ["40–60% sludge reduction", "Retrofit into existing basins", "No media replacement"],
        "limitations": ["Carrier replenishment ongoing cost", "Emerging technology", "Limited large-scale references"],
        "best_for": ["biosolids_constraints", "capacity_expansion", "carbon_reduction"],
    },
    "ad_chp": {
        "name": "Anaerobic Digestion + CHP",
        "icon": "⚡",
        "description": "Mesophilic anaerobic digestion with biogas CHP. Reduces sludge by 35–45% and can offset 30–60% of plant electricity. Established technology (50+ years).",
        "strengths":  ["Net energy producer", "35–45% sludge reduction", "Offsets electricity"],
        "limitations": ["High capital cost", "Reject water increases liquid train load", "Fugitive CH4 risk"],
        "best_for": ["energy_optimisation", "biosolids_constraints", "carbon_reduction"],
    },
    "thermal_biosolids": {
        "name": "Thermal Biosolids Treatment",
        "icon": "🔥",
        "description": "Incineration, pyrolysis, or gasification of dewatered biosolids. Destroys PFAS (>99% at ≥850°C). Eliminates land application requirements.",
        "strengths":  [">99% PFAS destruction", "No land application needed", "Stable ash for landfill"],
        "limitations": ["Highest CAPEX/OPEX", "Air permit required", "Supplemental fuel if low TS"],
        "best_for": ["biosolids_constraints", "carbon_reduction"],
    },
    "cpr": {
        "name": "Chemical Phosphorus Removal",
        "icon": "🧪",
        "description": "FeCl3 or alum dosing with lamella settler for TP polishing to <0.1 mg/L. Tertiary step for strict TP licence compliance.",
        "strengths":  ["Achieves <0.1 mg/L TP", "Low capital cost", "Simple operation"],
        "limitations": ["Chemical sludge for disposal", "Ongoing chemical OPEX", "Does not remove dissolved organic P"],
        "best_for": ["nutrient_limit_tightening", "reuse_prw_integration"],
    },
    "tertiary_filt": {
        "name": "Tertiary Filtration",
        "icon": "🔧",
        "description": "RSF, deep bed, or cloth/disc filter polishing TSS to 5 mg/L. Enables UV disinfection and reuse pathways.",
        "strengths":  ["Simple and reliable", "Enables UV/reuse", "Low energy"],
        "limitations": ["Does not remove dissolved constituents", "Backwash recycles to headworks"],
        "best_for": ["reuse_prw_integration", "nutrient_limit_tightening"],
    },
    "adv_reuse": {
        "name": "Advanced Reuse (MF/UF + RO + UV/AOP)",
        "icon": "💧",
        "description": "Full advanced treatment train for Class A+ non-potable reuse or indirect potable reuse. Removes PFAS, TDS, and trace organics.",
        "strengths":  [">4 log pathogen removal", "PFAS removed via RO", "Enables IPR"],
        "limitations": ["Highest energy cost", "RO concentrate management", "IPR needs regulatory approval"],
        "best_for": ["reuse_prw_integration"],
    },
}


def render() -> None:
    render_page_header("03 Treatment Options", "Select and configure treatment technologies for this scenario.")
    require_project()

    project = get_current_project()
    pm = ProjectManager()
    render_scenario_selector(project)
    scenario = get_active_scenario()
    if not scenario:
        return
    if not scenario.domain_inputs:
        st.warning("⚠️ Complete 02 Plant Inputs before selecting treatment technologies.")
        return

    existing_pathway = scenario.treatment_pathway
    existing_sequence = existing_pathway.technology_sequence if existing_pathway else []
    existing_params   = existing_pathway.technology_parameters if existing_pathway else {}

    # ── Planning scenario recommendation banner ────────────────────────────
    ps_val = project.metadata.planning_scenario
    if ps_val:
        try:
            ps = PlanningScenario(ps_val)
            recommended = [code for code, info in TECHNOLOGIES.items()
                           if ps_val in info.get("best_for", [])]
            if recommended:
                names = " | ".join(TECHNOLOGIES[c]["icon"] + " " + TECHNOLOGIES[c]["name"].split("(")[0].strip()
                                   for c in recommended)
                st.info(f"💡 **{ps.display_name}** — recommended technologies: {names}")
        except ValueError:
            pass

    st.subheader(f"Treatment for: {scenario.scenario_name}")
    st.markdown("#### Step 1 — Select technologies")

    selected_techs = []
    for code, info in TECHNOLOGIES.items():
        with st.container(border=True):
            c_check, c_icon, c_info = st.columns([0.5, 0.5, 8])
            selected = c_check.checkbox("", value=code in existing_sequence, key=f"sel_{code}")
            c_icon.markdown(f"## {info['icon']}")
            with c_info:
                st.markdown(f"**{info['name']}**")
                st.caption(info["description"])
                col_s, col_l = st.columns(2)
                col_s.markdown("✅ " + " · ".join(info["strengths"]))
                col_l.markdown("⚠️ " + " · ".join(info["limitations"]))
        if selected:
            selected_techs.append(code)

    if not selected_techs:
        st.info("Select at least one treatment technology above.")
        return

    st.divider()
    st.markdown("#### Step 2 — Configure parameters")
    tech_params = {}

    if "bnr" in selected_techs:
        with st.expander("⚙️ BNR Configuration", expanded="bnr" in existing_sequence):
            eb = existing_params.get("bnr", {})
            c1, c2 = st.columns(2)
            with c1:
                config = st.selectbox("Configuration", ["a2o","bardenpho_5stage","uct","modified_uct"],
                    index=["a2o","bardenpho_5stage","uct","modified_uct"].index(eb.get("process_configuration","a2o")))
                srt = st.slider("SRT (days)", 5, 30, int(eb.get("srt_days", 12)))
                mlss = st.select_slider("MLSS (mg/L)", [2000,2500,3000,3500,4000,4500,5000],
                    value=int(eb.get("mlss_mg_l", 4000)))
            with c2:
                supp_c   = st.checkbox("Supplemental carbon", value=bool(eb.get("supplemental_carbon", False)))
                chem_p   = st.checkbox("Chemical P removal",  value=bool(eb.get("chemical_p_removal", False)))
                prim_clar = st.checkbox(
                    "Include primary clarifier",
                    value=bool(eb.get("include_primary_clarifier", False)),
                    help="Adds a primary clarifier upstream of the bioreactor. "
                         "Redirects ~35% BOD as primary sludge to AD for biogas uplift and reduces O₂ demand. "
                         "May reduce BOD/TN ratio — check C:N warning in results."
                )
            tech_params["bnr"] = {"process_configuration": config, "srt_days": float(srt),
                                   "mlss_mg_l": float(mlss), "supplemental_carbon": supp_c,
                                   "chemical_p_removal": chem_p,
                                   "include_primary_clarifier": prim_clar}

    if "mabr_bnr" in selected_techs:
        with st.expander("⚙️ MABR + BNR Configuration", expanded="mabr_bnr" in existing_sequence):
            em = existing_params.get("mabr_bnr", {})
            st.info(
                "**MABR** delivers O₂ bubble-free through hollow-fibre membranes into a biofilm "
                "at ~95% transfer efficiency — replacing conventional blowers. "
                "Clarifiers are still required. Available as **new-build** or **retrofit** "
                "into existing aeration basins."
            )
            c1, c2 = st.columns(2)
            with c1:
                mabr_mode = st.selectbox(
                    "Configuration",
                    ["new_build", "retrofit"],
                    index=0 if em.get("mode", "new_build") == "new_build" else 1,
                    format_func=lambda x: "New-Build" if x == "new_build" else "Retrofit (into existing basin)",
                    key="mabr_mode"
                )
                mabr_loading = st.select_slider(
                    "NH₄ surface loading (g/m²/day)",
                    options=[1.0, 1.5, 2.0, 2.5, 3.0],
                    value=float(em.get("nh4_surface_loading_g_m2_day", 2.0)),
                    key="mabr_loading",
                    help="Lower = more conservative / more membrane area. Higher = less area but more risk."
                )
                mabr_srt = st.slider("SRT (days)", 5, 20, int(em.get("srt_days", 12)), key="mabr_srt")
            with c2:
                mabr_mlss = st.select_slider(
                    "MLSS (mg/L)",
                    options=[2000, 2500, 3000, 3500, 4000, 5000],
                    value=int(em.get("mlss_mg_l", 3500)),
                    key="mabr_mlss"
                )
                mabr_pure_o2 = st.checkbox(
                    "Pure O₂ supply",
                    value=bool(em.get("use_pure_oxygen", False)),
                    key="mabr_pure_o2",
                    help="Pure O₂ increases transfer further but requires on-site generation or bulk delivery"
                )
                mabr_chem_p = st.checkbox(
                    "Chemical P removal",
                    value=bool(em.get("chemical_p_removal", False)),
                    key="mabr_chem_p"
                )
            tech_params["mabr_bnr"] = {
                "mode": mabr_mode,
                "nh4_surface_loading_g_m2_day": float(mabr_loading),
                "srt_days": float(mabr_srt),
                "mlss_mg_l": float(mabr_mlss),
                "use_pure_oxygen": mabr_pure_o2,
                "chemical_p_removal": mabr_chem_p,
            }

    if "bnr_mbr" in selected_techs:
        with st.expander("⚙️ BNR + MBR Hybrid Configuration", expanded="bnr_mbr" in existing_sequence):
            eb = existing_params.get("bnr_mbr", {})
            st.info(
                "**BNR zone** handles all the biology at conventional MLSS. "
                "**Membrane tank** provides final separation — replacing or supplementing clarifiers. "
                "Suitable as new-build or upgrade of existing BNR plant."
            )
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**BNR Zone**")
                bm_srt  = st.slider("BNR SRT (days)", 5, 20, int(eb.get("srt_days", 12)), key="bnr_mbr_srt")
                bm_mlss = st.select_slider("BNR MLSS (mg/L)", [2000,3000,4000,5000,6000],
                    value=int(eb.get("mlss_bnr_mg_l", 4000)), key="bnr_mbr_mlss")
                bm_anox = st.slider("Anoxic fraction", 0.20, 0.50, float(eb.get("anoxic_fraction", 0.35)), 0.05, key="bnr_mbr_anox")
            with c2:
                st.markdown("**Membrane Separation Tank**")
                bm_flux = st.slider("Membrane flux (LMH)", 10, 35, int(eb.get("design_flux_lmh", 20)), key="bnr_mbr_flux")
                bm_mem_mlss = st.select_slider("Membrane tank MLSS (mg/L)", [6000,7000,8000,9000,10000,12000],
                    value=int(eb.get("mlss_membrane_tank_mg_l", 8000)), key="bnr_mbr_mem_mlss")
                bm_retain_clar = st.checkbox(
                    "Retain 1 standby clarifier",
                    value=bool(eb.get("retain_one_clarifier", True)),
                    help="Keep one secondary clarifier for bypass during membrane maintenance",
                    key="bnr_mbr_clar"
                )
            tech_params["bnr_mbr"] = {
                "srt_days": float(bm_srt),
                "mlss_bnr_mg_l": float(bm_mlss),
                "anoxic_fraction": float(bm_anox),
                "design_flux_lmh": float(bm_flux),
                "mlss_membrane_tank_mg_l": float(bm_mem_mlss),
                "retain_one_clarifier": bm_retain_clar,
            }

    if "granular_sludge" in selected_techs:
        with st.expander("⚙️ Aerobic Granular Sludge Configuration", expanded="granular_sludge" in existing_sequence):
            eg = existing_params.get("granular_sludge", {})
            c1, c2 = st.columns(2)
            with c1:
                gs_srt = st.slider("SRT (days)", 10, 35, int(eg.get("srt_days", 20)))
                cycle  = st.slider("SBR Cycle Time (hours)", 3, 8, int(eg.get("cycle_time_hours", 4)))
            with c2:
                gran_d = st.number_input("Target Granule Diameter (mm)", 1.0, 5.0,
                    float(eg.get("granule_diameter_mm", 2.0)), 0.5)
                fbt = st.checkbox(
                    "Include flow balance tank",
                    value=bool(eg.get("include_flow_balance_tank", True)),
                    help=(
                        "AGS SBR receives flow intermittently during fill phase only. "
                        "A flow balance tank buffers continuous influent during "
                        "react/settle/decant phases. Sized for 1 full cycle time. "
                        "Required for all practical continuous-flow installations."
                    ),
                )
            tech_params["granular_sludge"] = {
                "srt_days": float(gs_srt),
                "cycle_time_hours": float(cycle),
                "granule_diameter_mm": gran_d,
                "include_flow_balance_tank": fbt,
            }

    if "ifas_mbbr" in selected_techs:
        with st.expander("⚙️ IFAS / MBBR Configuration", expanded="ifas_mbbr" in existing_sequence):
            ei = existing_params.get("ifas_mbbr", {})
            c1, c2 = st.columns(2)
            with c1:
                mode   = st.selectbox("Mode", ["ifas","mbbr_standalone"],
                    index=0 if ei.get("mode","ifas")=="ifas" else 1,
                    help="IFAS = retrofit into existing tanks | MBBR = standalone reactor")
                fill   = st.slider("Media Fill Ratio", 0.10, 0.60, float(ei.get("media_fill_ratio", 0.35)), 0.05)
            with c2:
                sa     = st.select_slider("Media Surface Area (m²/m³)", [350,500,600,800],
                    value=int(ei.get("media_surface_area_m2_per_m3", 500)))
                ifas_chem_p = st.checkbox("Chemical P removal", value=bool(ei.get("chemical_p_removal", True)))
            tech_params["ifas_mbbr"] = {"mode": mode, "media_fill_ratio": fill,
                                         "media_surface_area_m2_per_m3": float(sa),
                                         "chemical_p_removal": ifas_chem_p}

    if "anmbr" in selected_techs:
        with st.expander("⚙️ Anaerobic Treatment Configuration", expanded="anmbr" in existing_sequence):
            ea = existing_params.get("anmbr", {})
            c1, c2 = st.columns(2)
            with c1:
                an_mode = st.selectbox("Mode", ["anmbr","uasb"],
                    index=0 if ea.get("mode","anmbr")=="anmbr" else 1)
                an_temp = st.slider("Operating Temperature (°C)", 20, 40, int(ea.get("temperature_celsius", 30)))
            with c2:
                vs_dest = st.slider("VS Destruction (%)", 40, 75, int(ea.get("vs_destruction_pct", 0.55) * 100))
                post_tx = st.checkbox("Include aerobic post-treatment", value=bool(ea.get("include_post_treatment", True)))
            tech_params["anmbr"] = {"mode": an_mode, "temperature_celsius": float(an_temp),
                                     "vs_destruction_pct": vs_dest / 100.0,
                                     "include_post_treatment": post_tx}

    if "sidestream_pna" in selected_techs:
        with st.expander("⚙️ Sidestream PN/A Configuration", expanded="sidestream_pna" in existing_sequence):
            es = existing_params.get("sidestream_pna", {})
            c1, c2 = st.columns(2)
            with c1:
                pna_mode = st.selectbox("Mode", ["demon","sharon_anammox","mainstream"],
                    index=["demon","sharon_anammox","mainstream"].index(es.get("mode","demon")))
                ss_nh4  = st.number_input("Sidestream NH₄-N (mg/L)", 100.0, 2000.0,
                    float(es.get("sidestream_nh4_mg_l", 800.0)), 50.0)
            with c2:
                ss_frac = st.slider("Sidestream Flow (% of main)", 0.1, 5.0,
                    float(es.get("sidestream_flow_fraction", 0.01)) * 100, 0.1) / 100.0
            tech_params["sidestream_pna"] = {"mode": pna_mode, "sidestream_nh4_mg_l": ss_nh4,
                                              "sidestream_flow_fraction": ss_frac}

    if "mob" in selected_techs:
        with st.expander("⚙️ Mobile Organic Biofilm Configuration", expanded="mob" in existing_sequence):
            em = existing_params.get("mob", {})
            c1, c2 = st.columns(2)
            with c1:
                mob_fill = st.slider("Carrier Fill Ratio", 0.15, 0.50,
                    float(em.get("carrier_fill_ratio", 0.30)), 0.05)
                mob_load = st.slider("BOD Surface Loading (g BOD/m²/day)", 3.0, 20.0,
                    float(em.get("bod_surface_loading_g_m2_day", 8.0)), 1.0)
                mob_upgrade = st.checkbox("Retrofit existing tanks",
                    value=bool(em.get("upgrade_existing", True)))
            with c2:
                mob_yield = st.slider("Observed Yield (kgVSS/kgBOD)", 0.05, 0.30,
                    float(em.get("y_obs_kg_vss_kg_bod", 0.15)), 0.01,
                    help="MOB typical: 0.10–0.20 (vs CAS 0.35–0.45)")
                mob_temp = st.slider("Design Temperature (°C)", 10, 30,
                    int(em.get("design_temperature_celsius", 20)))
                mob_p    = st.checkbox("Chemical P polish", value=bool(em.get("chemical_p_polish", False)))
            tech_params["mob"] = {
                "carrier_fill_ratio": mob_fill,
                "bod_surface_loading_g_m2_day": mob_load,
                "upgrade_existing": mob_upgrade,
                "y_obs_kg_vss_kg_bod": mob_yield,
                "design_temperature_celsius": float(mob_temp),
                "chemical_p_polish": mob_p,
            }

    if "ad_chp" in selected_techs:
        with st.expander("⚙️ Anaerobic Digestion + CHP Configuration", expanded="ad_chp" in existing_sequence):
            ea = existing_params.get("ad_chp", {})
            c1, c2 = st.columns(2)
            with c1:
                ad_feed = st.number_input("Sludge Feed (kg DS/day)", 100.0, 50000.0,
                    float(ea.get("feed_kgds_day", 1500.0)), 100.0)
                ad_vs   = st.slider("Feed VS Fraction", 0.55, 0.90,
                    float(ea.get("feed_vs_fraction", 0.80)), 0.01)
                ad_dest = st.slider("VS Destruction (%)", 40, 70,
                    int(ea.get("vs_destruction_pct", 58.0)))
            with c2:
                ad_bgyr = st.slider("Biogas Yield (m³/kg VS)", 0.55, 0.90,
                    float(ea.get("biogas_yield_m3_per_kg_vs", 0.75)), 0.01,
                    help="Municipal mesophilic: 0.65–0.80. Only use >0.80 for FOG co-digestion.")
                ad_chp_eff = st.slider("CHP Electrical Efficiency", 0.30, 0.42,
                    float(ea.get("chp_electrical_efficiency", 0.38)), 0.01)
            tech_params["ad_chp"] = {
                "feed_kgds_day": float(ad_feed),
                "feed_vs_fraction": float(ad_vs),
                "vs_destruction_pct": float(ad_dest),
                "biogas_yield_m3_per_kg_vs": float(ad_bgyr),
                "chp_electrical_efficiency": float(ad_chp_eff),
            }

    if "thermal_biosolids" in selected_techs:
        with st.expander("⚙️ Thermal Biosolids Configuration", expanded="thermal_biosolids" in existing_sequence):
            et = existing_params.get("thermal_biosolids", {})
            c1, c2 = st.columns(2)
            with c1:
                th_route = st.selectbox("Treatment Route",
                    ["incineration", "pyrolysis", "gasification"],
                    index=["incineration","pyrolysis","gasification"].index(
                        et.get("route", "incineration")))
                th_feed  = st.number_input("Feed (kg DS/day)", 100.0, 50000.0,
                    float(et.get("feed_kgds_day", 1500.0)), 100.0)
                th_ts    = st.slider("Feed TS%", 12, 35, int(et.get("feed_ts_pct", 22)))
            with c2:
                default_temps = {"incineration": 900, "pyrolysis": 550, "gasification": 850}
                th_temp  = st.number_input("Operating Temperature (°C)", 400.0, 1200.0,
                    float(et.get("operating_temperature_celsius",
                                 default_temps.get(th_route, 900))), 50.0)
                th_rec   = st.checkbox("Energy Recovery (CHP/steam)",
                    value=bool(et.get("energy_recovery_enabled", True)))
            tech_params["thermal_biosolids"] = {
                "route": th_route, "feed_kgds_day": float(th_feed),
                "feed_ts_pct": float(th_ts),
                "operating_temperature_celsius": float(th_temp),
                "energy_recovery_enabled": th_rec,
            }

    if "cpr" in selected_techs:
        with st.expander("⚙️ Chemical P Removal Configuration", expanded="cpr" in existing_sequence):
            ec = existing_params.get("cpr", {})
            c1, c2 = st.columns(2)
            with c1:
                cpr_inf_tp = st.number_input("Influent TP (mg/L)", 0.1, 10.0,
                    float(ec.get("influent_tp_mg_l", 1.0)), 0.1,
                    help="TP entering the CPR unit after biological treatment")
                cpr_tgt    = st.number_input("Target Effluent TP (mg/L)", 0.02, 1.0,
                    float(ec.get("target_effluent_tp_mg_l", 0.10)), 0.01)
            with c2:
                cpr_coag   = st.selectbox("Coagulant", ["ferric_chloride","alum"],
                    index=0 if ec.get("coagulant","ferric_chloride")=="ferric_chloride" else 1)
                cpr_sep    = st.selectbox("Separator", ["lamella","rsf","daf"],
                    index=["lamella","rsf","daf"].index(ec.get("separator_type","lamella")))
                cpr_poly   = st.checkbox("Polymer aid", value=bool(ec.get("include_polymer", True)))
            tech_params["cpr"] = {
                "influent_tp_mg_l": float(cpr_inf_tp),
                "target_effluent_tp_mg_l": float(cpr_tgt),
                "coagulant": cpr_coag, "separator_type": cpr_sep,
                "include_polymer": cpr_poly,
            }

    if "tertiary_filt" in selected_techs:
        with st.expander("⚙️ Tertiary Filtration Configuration", expanded="tertiary_filt" in existing_sequence):
            ef = existing_params.get("tertiary_filt", {})
            c1, c2 = st.columns(2)
            with c1:
                tf_type  = st.selectbox("Filter Type", ["rsf","deep_bed","cloth_disc"],
                    index=["rsf","deep_bed","cloth_disc"].index(ef.get("filter_type","rsf")))
                tf_inf   = st.number_input("Influent TSS (mg/L)", 2.0, 40.0,
                    float(ef.get("influent_tss_mg_l", 12.0)), 1.0)
            with c2:
                tf_tgt   = st.number_input("Target Effluent TSS (mg/L)", 1.0, 15.0,
                    float(ef.get("target_tss_mg_l", 5.0)), 0.5)
                tf_uv    = st.checkbox("Include UV Disinfection",
                    value=bool(ef.get("include_uv_disinfection", False)))
            tech_params["tertiary_filt"] = {
                "filter_type": tf_type, "influent_tss_mg_l": float(tf_inf),
                "target_tss_mg_l": float(tf_tgt), "include_uv_disinfection": tf_uv,
            }

    if "adv_reuse" in selected_techs:
        with st.expander("⚙️ Advanced Reuse Configuration", expanded="adv_reuse" in existing_sequence):
            er = existing_params.get("adv_reuse", {})
            c1, c2 = st.columns(2)
            with c1:
                reus_cls = st.selectbox("Reuse Class",
                    ["non_potable","ipr","dpr"],
                    index=["non_potable","ipr","dpr"].index(er.get("reuse_class","non_potable")),
                    format_func=lambda x: {
                        "non_potable": "Non-potable reuse", "ipr": "Indirect potable reuse",
                        "dpr": "Direct potable reuse"}.get(x, x))
                reus_rec = st.slider("RO Recovery", 0.65, 0.88,
                    float(er.get("ro_recovery", 0.80)), 0.01)
            with c2:
                reus_tds = st.number_input("Feed TDS (mg/L)", 200.0, 3000.0,
                    float(er.get("influent_tds_mg_l", 800.0)), 50.0)
                reus_conc = st.selectbox("Concentrate Disposal",
                    ["sewer","brine_concentrator","evaporation_pond"],
                    index=["sewer","brine_concentrator","evaporation_pond"].index(
                        er.get("concentrate_disposal","sewer")))
            tech_params["adv_reuse"] = {
                "reuse_class": reus_cls, "ro_recovery": float(reus_rec),
                "influent_tds_mg_l": float(reus_tds),
                "concentrate_disposal": reus_conc,
            }

    st.divider()
    pathway_name = st.text_input("Pathway Name",
        value=existing_pathway.pathway_name if existing_pathway else
              " + ".join(TECHNOLOGIES[t]["name"].split("(")[0].strip() for t in selected_techs))

    if st.button("Save Treatment Selection ✓", type="primary", use_container_width=True):
        scenario.treatment_pathway = TreatmentPathway(
            pathway_name=pathway_name,
            technology_sequence=selected_techs,
            technology_parameters=tech_params,
        )
        mark_scenario_stale()
        update_current_project(project)
        pm.save(project)
        st.success(f"✅ Saved: **{pathway_name}** — {', '.join(selected_techs)}. Proceed to 04 Results.")
