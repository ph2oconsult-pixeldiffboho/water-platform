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



def _render_tech_config(code: str, existing_params: dict, tech_params: dict, existing_sequence: list) -> None:
    """Render inline configuration panel for a technology immediately below its selection card."""
    import streamlit as st

    # Map of code → config label
    labels = {
        "bnr": "⚙️ BNR Configuration",
        "bnr_mbr": "⚙️ BNR + MBR Hybrid Configuration",
        "mabr_bnr": "⚙️ MABR + BNR Configuration",
        "granular_sludge": "⚙️ Aerobic Granular Sludge Configuration",
        "ifas_mbbr": "⚙️ IFAS / MBBR Configuration",
        "anmbr": "⚙️ AnMBR Configuration",
        "sidestream_pna": "⚙️ Sidestream PN/A Configuration",
        "mob": "⚙️ MOB Configuration",
        "ad_chp": "⚙️ AD + CHP Configuration",
        "thermal_biosolids": "⚙️ Thermal Biosolids Configuration",
        "cpr": "⚙️ Chemical P Removal Configuration",
        "tertiary_filt": "⚙️ Tertiary Filtration Configuration",
        "adv_reuse": "⚙️ Advanced Reuse Configuration",
    }
    label = labels.get(code, f"⚙️ {code} Configuration")

    with st.expander(label, expanded=True):

        if code == "bnr":
            eb = existing_params.get("bnr", {})
            c1, c2 = st.columns(2)
            with c1:
                config = st.selectbox("Configuration", ["a2o","bardenpho_5stage","uct","modified_uct"],
                    index=["a2o","bardenpho_5stage","uct","modified_uct"].index(eb.get("process_configuration","a2o")), key="bnr_config")
                srt  = st.slider("SRT (days)", 5, 30, int(eb.get("srt_days", 12)), key="bnr_srt")
                mlss = st.select_slider("MLSS (mg/L)", [2000,2500,3000,3500,4000,4500,5000],
                    value=int(eb.get("mlss_mg_l", 4000)), key="bnr_mlss")
            with c2:
                supp_c = st.checkbox("Supplemental carbon", value=bool(eb.get("supplemental_carbon", False)), key="bnr_suppc")
                chem_p = st.checkbox("Chemical P removal",  value=bool(eb.get("chemical_p_removal", False)), key="bnr_chemp")
            st.divider()
            prim_clar = st.checkbox(
                "🔵 Include primary clarifier (with AD + CHP energy credit)",
                value=bool(eb.get("include_primary_clarifier", False)), key="bnr_primclar",
                help="Adds PC upstream. Routes ~35% BOD to AD for biogas credit (~91 kWh/ML). "
                     "Reduces bioreactor size ~37%. COD/TKN drops — may need supplemental carbon."
            )
            if prim_clar:
                st.info("**Primary clarifier enabled.** Check C:N warning in Results after calculation.")
            tech_params["bnr"] = {"process_configuration": config, "srt_days": float(srt),
                                   "mlss_mg_l": float(mlss), "supplemental_carbon": supp_c,
                                   "chemical_p_removal": chem_p, "include_primary_clarifier": prim_clar}

        elif code == "bnr_mbr":
            eb = existing_params.get("bnr_mbr", {})
            st.info("BNR zone handles biology at conventional MLSS. Membrane tank provides final separation.")
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**BNR Zone**")
                bm_srt  = st.slider("BNR SRT (days)", 5, 20, int(eb.get("srt_days", 12)), key="bnrmbr_srt")
                bm_mlss = st.select_slider("BNR MLSS (mg/L)", [2000,3000,4000,5000,6000],
                    value=int(eb.get("mlss_bnr_mg_l", 4000)), key="bnrmbr_mlss")
                bm_anox = st.slider("Anoxic fraction", 0.20, 0.50, float(eb.get("anoxic_fraction", 0.35)), 0.05, key="bnrmbr_anox")
            with c2:
                st.markdown("**Membrane Separation Tank**")
                bm_flux = st.slider("Membrane flux (LMH)", 10, 35, int(eb.get("design_flux_lmh", 20)), key="bnrmbr_flux")
                bm_mem_mlss = st.select_slider("Membrane tank MLSS (mg/L)", [6000,7000,8000,9000,10000,12000],
                    value=int(eb.get("mlss_membrane_tank_mg_l", 8000)), key="bnrmbr_memmlss")
                bm_retain_clar = st.checkbox("Retain 1 standby clarifier", value=bool(eb.get("retain_one_clarifier", True)),
                    help="Keep one clarifier for bypass during membrane maintenance", key="bnrmbr_clar")
            tech_params["bnr_mbr"] = {"srt_days": float(bm_srt), "mlss_bnr_mg_l": float(bm_mlss),
                                       "anoxic_fraction": float(bm_anox), "design_flux_lmh": float(bm_flux),
                                       "mlss_membrane_tank_mg_l": float(bm_mem_mlss), "retain_one_clarifier": bm_retain_clar}

        elif code == "mabr_bnr":
            em = existing_params.get("mabr_bnr", {})
            st.info("MABR modules retrofit into the BNR aerobic zone. Conventional blowers retained for 50% of O₂. "
                    "Provides 30% NH₄ capacity uplift. Full BNR ancillary (RAS, MLR, WAS) unchanged.")
            c1, c2 = st.columns(2)
            with c1:
                mabr_mode = st.selectbox("Configuration", ["new_build","retrofit"],
                    index=0 if em.get("mode","new_build")=="new_build" else 1,
                    format_func=lambda x: "New-Build" if x=="new_build" else "Retrofit (into existing basin)",
                    key="mabr_mode")
                mabr_loading = st.select_slider("NH₄ surface loading (g/m²/day)", [1.0,1.5,2.0,2.5,3.0],
                    value=float(em.get("nh4_surface_loading_g_m2_day", 2.0)), key="mabr_loading")
                mabr_srt = st.slider("SRT (days)", 5, 20, int(em.get("srt_days", 12)), key="mabr_srt")
            with c2:
                mabr_mlss = st.select_slider("MLSS (mg/L)", [2000,2500,3000,3500,4000,5000],
                    value=int(em.get("mlss_mg_l", 3500)), key="mabr_mlss")
                mabr_pure_o2 = st.checkbox("Pure O₂ supply", value=bool(em.get("use_pure_oxygen", False)), key="mabr_o2")
                mabr_chem_p  = st.checkbox("Chemical P removal", value=bool(em.get("chemical_p_removal", False)), key="mabr_chemp")
            st.divider()
            mabr_prim_clar = st.checkbox(
                "🔵 Include primary clarifier (with AD + CHP energy credit)",
                value=bool(em.get("include_primary_clarifier", False)), key="mabr_primclar",
                help="Adds primary clarifier upstream of MABR+BNR bioreactor. "
                     "Routes ~35% BOD to AD for biogas/CHP credit (~91 kWh/ML). "
                     "Reduces bioreactor volume ~37%. COD/TKN check applied — may need supplemental carbon."
            )
            if mabr_prim_clar:
                st.info("**Primary clarifier enabled.** Check C:N warning in Results after calculation.")
            tech_params["mabr_bnr"] = {"mode": mabr_mode,
                "nh4_surface_loading_g_m2_day": float(mabr_loading), "srt_days": float(mabr_srt),
                "mlss_mg_l": float(mabr_mlss), "use_pure_oxygen": mabr_pure_o2,
                "chemical_p_removal": mabr_chem_p, "include_primary_clarifier": mabr_prim_clar}

        elif code == "granular_sludge":
            eg = existing_params.get("granular_sludge", {})
            c1, c2 = st.columns(2)
            with c1:
                gs_srt = st.slider("SRT (days)", 10, 35, int(eg.get("srt_days", 20)), key="ags_srt")
                cycle  = st.slider("SBR Cycle Time (hours)", 3, 8, int(eg.get("cycle_time_hours", 4)), key="ags_cycle")
            with c2:
                gran_d = st.number_input("Target Granule Diameter (mm)", 1.0, 5.0, float(eg.get("granule_diameter_mm", 2.0)), 0.5, key="ags_diam")
                fbt = st.checkbox("Include flow balance tank", value=bool(eg.get("include_flow_balance_tank", True)), key="ags_fbt",
                    help="Buffers continuous influent during SBR react/settle/decant phases. Sized for 1 cycle time.")
            tech_params["granular_sludge"] = {"srt_days": float(gs_srt), "cycle_time_hours": float(cycle),
                                               "granule_diameter_mm": gran_d, "include_flow_balance_tank": fbt}

        elif code == "ifas_mbbr":
            ei = existing_params.get("ifas_mbbr", {})
            c1, c2 = st.columns(2)
            with c1:
                ifas_mode = st.selectbox("Mode", ["ifas","mbbr"],
                    index=0 if ei.get("mode","ifas")=="ifas" else 1,
                    format_func=lambda x: "IFAS (retrofit into existing tank)" if x=="ifas" else "MBBR (standalone)", key="ifas_mode")
                ifas_srt  = st.slider("SRT (days)", 5, 25, int(ei.get("srt_days", 12)), key="ifas_srt")
                ifas_mlss = st.select_slider("MLSS (mg/L)", [2000,2500,3000,3500,4000],
                    value=int(ei.get("mlss_mg_l", 3000)), key="ifas_mlss")
            with c2:
                ifas_fill = st.slider("Media fill ratio", 0.20, 0.50, float(ei.get("media_fill_ratio", 0.35)), 0.05, key="ifas_fill")
                ifas_chem_p = st.checkbox("Chemical P removal", value=bool(ei.get("chemical_p_removal", True)), key="ifas_chemp")
            tech_params["ifas_mbbr"] = {"mode": ifas_mode, "srt_days": float(ifas_srt),
                                         "mlss_mg_l": float(ifas_mlss), "media_fill_ratio": float(ifas_fill),
                                         "chemical_p_removal": ifas_chem_p}

        elif code == "ad_chp":
            ea = existing_params.get("ad_chp", {})
            c1, c2 = st.columns(2)
            with c1:
                ad_hrt  = st.slider("HRT (days)", 15, 35, int(ea.get("hrt_days", 20)), key="adchp_hrt")
                ad_temp = st.selectbox("Digestion Temperature", ["mesophilic","thermophilic"],
                    index=0 if ea.get("digestion_temperature","mesophilic")=="mesophilic" else 1, key="adchp_temp")
            with c2:
                ad_flare = st.slider("Flare fraction", 0.0, 0.30, float(ea.get("flare_fraction", 0.05)), 0.05, key="adchp_flare")
                ad_chp_on = st.checkbox("Enable CHP", value=bool(ea.get("chp_enabled", True)), key="adchp_on")
            tech_params["ad_chp"] = {"hrt_days": float(ad_hrt), "digestion_temperature": ad_temp,
                                      "flare_fraction": float(ad_flare), "chp_enabled": ad_chp_on}

        elif code == "cpr":
            ec = existing_params.get("cpr", {})
            c1, c2 = st.columns(2)
            with c1:
                cpr_coag = st.selectbox("Coagulant", ["ferric_chloride","alum"],
                    index=0 if ec.get("coagulant","ferric_chloride")=="ferric_chloride" else 1, key="cpr_coag")
                cpr_sep  = st.selectbox("Separator", ["lamella","conventional_clarifier","daf"],
                    index=["lamella","conventional_clarifier","daf"].index(ec.get("separator_type","lamella")), key="cpr_sep")
            with c2:
                cpr_tp = st.number_input("Target TP (mg/L)", 0.05, 0.5, float(ec.get("target_tp_mg_l", 0.1)), 0.05, key="cpr_tp")
                cpr_poly = st.checkbox("Include polymer", value=bool(ec.get("include_polymer", False)), key="cpr_poly")
            tech_params["cpr"] = {"target_tp_mg_l": float(cpr_tp), "coagulant": cpr_coag,
                                   "separator_type": cpr_sep, "include_polymer": cpr_poly}

        elif code == "tertiary_filt":
            ef = existing_params.get("tertiary_filt", {})
            c1, c2 = st.columns(2)
            with c1:
                tf_type = st.selectbox("Filter Type", ["rsf","deep_bed","cloth_disc"],
                    index=["rsf","deep_bed","cloth_disc"].index(ef.get("filter_type","rsf")), key="tf_type")
                tf_inf  = st.number_input("Influent TSS (mg/L)", 2.0, 40.0, float(ef.get("influent_tss_mg_l", 12.0)), 1.0, key="tf_inf")
            with c2:
                tf_tgt = st.number_input("Target TSS (mg/L)", 1.0, 15.0, float(ef.get("target_tss_mg_l", 5.0)), 0.5, key="tf_tgt")
                tf_uv  = st.checkbox("Include UV", value=bool(ef.get("include_uv_disinfection", False)), key="tf_uv")
            tech_params["tertiary_filt"] = {"filter_type": tf_type, "influent_tss_mg_l": float(tf_inf),
                                             "target_tss_mg_l": float(tf_tgt), "include_uv_disinfection": tf_uv}

        elif code == "adv_reuse":
            er = existing_params.get("adv_reuse", {})
            c1, c2 = st.columns(2)
            with c1:
                reus_cls = st.selectbox("Reuse Class", ["non_potable","ipr","dpr"],
                    index=["non_potable","ipr","dpr"].index(er.get("reuse_class","non_potable")),
                    format_func=lambda x: {"non_potable":"Non-potable","ipr":"Indirect potable","dpr":"Direct potable"}.get(x,x), key="reuse_cls")
                reus_rec = st.slider("RO Recovery", 0.65, 0.88, float(er.get("ro_recovery", 0.80)), 0.01, key="reuse_rec")
            with c2:
                reus_tds  = st.number_input("Feed TDS (mg/L)", 200.0, 3000.0, float(er.get("influent_tds_mg_l", 800.0)), 50.0, key="reuse_tds")
                reus_conc = st.selectbox("Concentrate Disposal", ["sewer","brine_concentrator","evaporation_pond"],
                    index=["sewer","brine_concentrator","evaporation_pond"].index(er.get("concentrate_disposal","sewer")), key="reuse_conc")
            tech_params["adv_reuse"] = {"reuse_class": reus_cls, "ro_recovery": float(reus_rec),
                                         "influent_tds_mg_l": float(reus_tds), "concentrate_disposal": reus_conc}
        # Other techs (anmbr, sidestream_pna, mob, thermal_biosolids) use defaults — no config required

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

    # ── Two-column layout: card selection + inline config ────────────────
    # Selecting a technology immediately shows its config panel below the card.
    # No more scrolling to the bottom of the page.
    selected_techs = []
    tech_params    = {}

    # Group into biological treatment and add-on processes
    PRIMARY_CODES = ["bnr", "bnr_mbr", "mabr_bnr", "granular_sludge", "ifas_mbbr",
                     "anmbr", "sidestream_pna", "mob"]
    ADDON_CODES   = ["ad_chp", "thermal_biosolids", "cpr", "tertiary_filt", "adv_reuse"]

    st.markdown("#### Biological Treatment")

    primary_options = {code: TECHNOLOGIES[code]["icon"] + "  " + TECHNOLOGIES[code]["name"]
                       for code in PRIMARY_CODES if code in TECHNOLOGIES}
    primary_options_list = list(primary_options.keys())
    primary_labels = list(primary_options.values())

    # Use radio for primary selection — enforces one primary tech, avoids double-scroll
    current_primary = next((c for c in existing_sequence if c in PRIMARY_CODES), None)
    current_idx = primary_options_list.index(current_primary) if current_primary in primary_options_list else 0

    selected_primary = st.radio(
        "Select primary biological treatment process",
        options=primary_options_list,
        index=current_idx,
        format_func=lambda c: primary_options[c],
        horizontal=False,
        label_visibility="collapsed",
    )
    selected_techs.append(selected_primary)

    # Show description + inline config for selected primary tech
    if selected_primary in TECHNOLOGIES:
        info = TECHNOLOGIES[selected_primary]
        with st.container(border=True):
            col_s, col_l = st.columns(2)
            col_s.markdown("✅ " + " · ".join(info["strengths"]))
            col_l.markdown("⚠️ " + " · ".join(info["limitations"]))
        _render_tech_config(selected_primary, existing_params, tech_params, existing_sequence)

    st.markdown("#### Add-on Processes")
    for code in ADDON_CODES:
        if code not in TECHNOLOGIES:
            continue
        info = TECHNOLOGIES[code]
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
                _render_tech_config(code, existing_params, tech_params, existing_sequence)

    if not selected_techs:
        st.info("Select at least one treatment technology above.")
        return

    # ── Auto-save on every render ──────────────────────────────────────────
    # No save button needed — selection is persisted immediately so the user
    # can navigate straight to 04 Results without scrolling to the bottom.
    auto_name = " + ".join(TECHNOLOGIES[t]["name"].split("(")[0].strip() for t in selected_techs)
    pathway_name = existing_pathway.pathway_name if existing_pathway else auto_name

    new_pathway = TreatmentPathway(
        pathway_name=pathway_name,
        technology_sequence=selected_techs,
        technology_parameters=tech_params,
    )
    # Only save if something actually changed (avoids unnecessary disk writes)
    changed = (
        not existing_pathway
        or existing_pathway.technology_sequence != selected_techs
        or existing_pathway.technology_parameters != tech_params
    )
    if changed:
        scenario.treatment_pathway = new_pathway
        mark_scenario_stale()
        update_current_project(project)
        pm.save(project)

    st.divider()
    st.success(f"✅ **{pathway_name}** selected — proceed to **04 Results** to run calculations.")
