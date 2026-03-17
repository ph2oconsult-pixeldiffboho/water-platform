"""
apps/wastewater_app/pages/page_09_assumptions.py

Phase 5: Assumptions Viewer
============================
Displays all key assumptions used in calculations in a structured,
auditable format. Users can see defaults, overrides, and scenario values.
Improves credibility and transparency for concept planning work.
"""
from __future__ import annotations
import streamlit as st
import pandas as pd
from apps.ui.session_state import require_project, get_current_project
from apps.ui.ui_components import render_page_header
from core.assumptions.assumptions_manager import AssumptionsManager
from core.project.project_model import DomainType


def render() -> None:
    render_page_header(
        "📋 Assumptions Viewer",
        subtitle="All key assumptions used in this project's calculations",
    )

    project = require_project()
    if not project:
        return

    # Load assumptions
    active_scenario = None
    if project.active_scenario_id and project.active_scenario_id in project.scenarios:
        active_scenario = project.scenarios[project.active_scenario_id]

    # Try to get scenario assumptions, fall back to defaults
    a = getattr(active_scenario, "assumptions", None) if active_scenario else None
    if a is None:
        a = AssumptionsManager().load_defaults(DomainType.WASTEWATER)

    cost    = a.cost_assumptions   if hasattr(a, "cost_assumptions")   else {}
    eng     = a.engineering_assumptions if hasattr(a, "engineering_assumptions") else {}
    carbon  = a.carbon_assumptions  if hasattr(a, "carbon_assumptions") else {}
    risk    = a.risk_assumptions    if hasattr(a, "risk_assumptions")   else {}
    overrides = a.user_overrides    if hasattr(a, "user_overrides")     else {}
    opex_rates = cost.get("opex_unit_rates", {})
    capex_costs = cost.get("capex_unit_costs", {})

    # Scenario-specific values
    di = (active_scenario.domain_inputs or {}) if active_scenario else {}

    def _flag(key: str, source: dict = None) -> str:
        """Return override flag if key is overridden."""
        if key in overrides:
            return " ✎ **overridden**"
        return ""

    def _val(key: str, default, source: dict = None) -> str:
        src = source or cost
        val = src.get(key, default)
        flag = _flag(key)
        return f"{val}{flag}"

    st.info(
        "✎ = value has been overridden from default. "
        "Defaults based on: WEF Cost Estimating Manual 2018 (costs), "
        "AUS NEM 2024 (grid), IPCC 2019 (N₂O), Metcalf 5th Ed (engineering)."
    )

    # ── Tab layout ──────────────────────────────────────────────────────────
    tab_econ, tab_eng, tab_carbon, tab_risk_a, tab_capex = st.tabs([
        "💰 Economic", "⚙️ Engineering", "🌿 Carbon", "⚠️ Risk", "🏗️ CAPEX Unit Rates"
    ])

    # ── Economic assumptions ────────────────────────────────────────────────
    with tab_econ:
        st.subheader("Economic Assumptions")
        st.caption("These drive OPEX, LCC, and $/kL calculations.")

        econ_rows = [
            ("Electricity price",        f"${opex_rates.get('electricity_per_kwh', 0.14):.3f}/kWh",
             "AUD 2024 average commercial/industrial",
             "opex_unit_rates.electricity_per_kwh"),
            ("Sludge disposal",          f"${opex_rates.get('sludge_disposal_per_tds', 280):.0f}/t DS",
             "Metropolitan AU landfill/compost (2024)",
             "opex_unit_rates.sludge_disposal_per_tds"),
            ("Carbon price",             f"${carbon.get('carbon_price_per_tonne_co2e', 35):.0f}/tCO₂e",
             "AUS safeguard mechanism proxy (2024)",
             "carbon_price_per_tonne_co2e"),
            ("Discount rate",            f"{cost.get('discount_rate', 0.07)*100:.0f}%",
             "Real discount rate (pre-inflation) for LCC",
             "discount_rate"),
            ("Analysis period",          f"{cost.get('analysis_period_years', 30)} years",
             "Typical infrastructure planning horizon",
             "analysis_period_years"),
            ("Design contingency",       f"{cost.get('design_contingency_pct', 0.20)*100:.0f}%",
             "Concept-level estimate allowance",
             "design_contingency_pct"),
            ("Contractor margin",        f"{cost.get('contractor_margin_pct', 0.12)*100:.0f}%",
             "Typical AU contractor overhead + profit",
             "contractor_margin_pct"),
            ("Client on-costs",          f"{cost.get('client_oncosts_pct', 0.15)*100:.0f}%",
             "Design, PM, approvals, commissioning",
             "client_oncosts_pct"),
            ("Labour (FTE/10 MLD)",      f"{opex_rates.get('labour_fte_per_10mld', 2.5):.1f} FTE",
             "AU utility benchmark — operators + maintenance",
             "opex_unit_rates.labour_fte_per_10mld"),
            ("Labour rate",              f"${opex_rates.get('labour_cost_per_fte', 105000)/1e3:.0f}k/yr/FTE",
             "Fully loaded AU wages 2024",
             "opex_unit_rates.labour_cost_per_fte"),
            ("Maintenance (BNR/IFAS)",   "1.5% CAPEX/yr",
             "WEF Cost Estimating Manual 2018, Table 6-3",
             "—"),
            ("Maintenance (MBR/AGS)",    "2.0% CAPEX/yr",
             "Novel tech: higher O&M complexity",
             "—"),
            ("Cost confidence",          cost.get("cost_confidence", "±30%"),
             "Concept-level — not for procurement",
             "cost_confidence"),
            ("Currency",                 cost.get("currency", "AUD"),
             "Australian dollars",
             "currency"),
            ("Price base year",          str(cost.get("price_base_year", 2024)),
             "",
             "price_base_year"),
        ]

        df = pd.DataFrame(econ_rows, columns=["Parameter", "Value", "Basis / Notes", "_key"])
        df = df.drop(columns=["_key"])
        st.dataframe(df, use_container_width=True, hide_index=True)

    # ── Engineering assumptions ─────────────────────────────────────────────
    with tab_eng:
        st.subheader("Engineering Assumptions")
        st.caption("These drive oxygen demand, sludge, reactor sizing, and energy calculations.")

        # Influent defaults
        st.markdown("**Influent quality defaults** (overridden by scenario inputs when set)")
        inf_rows = [
            ("BOD",     f"{eng.get('influent_bod_mg_l', 250):.0f} mg/L",     "Typical municipal WW"),
            ("COD",     f"{eng.get('influent_cod_mg_l', 500):.0f} mg/L",     "BOD × 2.0 (typical)"),
            ("TKN",     f"{eng.get('influent_tkn_mg_l', 45):.0f} mg/L",      "Metcalf Table 3-15"),
            ("NH₄-N",   f"{eng.get('influent_nh4_mg_l', 35):.0f} mg/L",      "NH₄/TKN = 0.78"),
            ("TSS",     f"{eng.get('influent_tss_mg_l', 280):.0f} mg/L",     ""),
            ("TP",      f"{eng.get('influent_tp_mg_l', 7):.0f} mg/L",        ""),
            ("Temperature", f"{eng.get('influent_temperature_celsius', 20):.0f} °C", "Default 20°C"),
        ]
        st.dataframe(pd.DataFrame(inf_rows, columns=["Parameter","Value","Notes"]),
                     use_container_width=True, hide_index=True)

        st.markdown("**Process design defaults**")
        bio_rows = [
            ("BNR SRT",            f"{eng.get('srt_days', 12):.0f} days",           "Metcalf Table 7-20"),
            ("MLSS",               f"{eng.get('mlss_mg_l', 4000):.0f} mg/L",        "BNR design point"),
            ("Y_true (BOD)",       "0.60 kgVSS/kgBOD",                              "Metcalf Table 7-15"),
            ("kd (decay, 20°C)",   "0.08 /day",                                     "Metcalf Table 7-15"),
            ("VSS/TSS ratio",      f"{eng.get('vss_to_tss_ratio', 0.80):.2f}",      "Typical municipal"),
            ("SAE_std (blowers)",  f"{eng.get('standard_aeration_efficiency_kg_o2_kwh', 1.8):.1f} kgO₂/kWh", "Fine bubble"),
            ("alpha (BNR)",        "0.55",                                           "Metcalf Table 8-15"),
            ("alpha (AGS)",        "0.65",                                           "de Kreuk 2007"),
            ("BNR anaerobic frac", f"{eng.get('anaerobic_fraction', 0.10)*100:.0f}%", "Bio-P zone"),
            ("BNR anoxic frac",    f"{eng.get('anoxic_fraction', 0.30)*100:.0f}%",  "Denitrification zone"),
            ("Clarifier SOR",      "1.5 m/hr",                                      "At peak flow"),
            ("Peak flow factor",   f"{eng.get('peak_flow_factor', 2.5):.1f}×",      "Scenario input"),
            ("Ancillary energy",   "70 kWh/MLD",                                    "WEF MOP 35"),
            ("RAS flow",           "1.0×Q, 3 m head",                               "Standard"),
            ("MLR flow",           "4.0×Q, 0.5 m head",                             "WEF MOP 35"),
        ]
        st.dataframe(pd.DataFrame(bio_rows, columns=["Parameter","Value","Reference"]),
                     use_container_width=True, hide_index=True)

    # ── Carbon assumptions ─────────────────────────────────────────────────
    with tab_carbon:
        st.subheader("Carbon & Emissions Assumptions")
        st.caption("These drive Scope 1, Scope 2, and net carbon calculations.")

        carbon_rows = [
            ("Grid emission factor",   f"{carbon.get('grid_emission_factor_kg_co2e_per_kwh', 0.79):.3f} kgCO₂e/kWh",
             "AUS NEM 2024 average (DCCEW)"),
            ("N₂O EF (central)",       "0.016 kg N₂O/kg N removed",
             "IPCC 2019 Tier 1, Table 6.8 (range: 0.005–0.050)"),
            ("N₂O GWP",                f"{carbon.get('n2o_gwp', 273)}",
             "IPCC AR6 (100-yr GWP)"),
            ("CH₄ fugitive EF",        f"{carbon.get('ch4_emission_factor_g_ch4_per_g_bod_influent', 0.0025):.4f} kg/kg BOD",
             "IPCC 2019 Tier 1"),
            ("CH₄ GWP",                f"{carbon.get('ch4_gwp', 28)}",
             "IPCC AR6"),
            ("Carbon price",           f"${carbon.get('carbon_price_per_tonne_co2e', 35):.0f}/tCO₂e",
             "AUS safeguard mechanism proxy"),
            ("N₂O uncertainty",        "×3–10 range",
             "Site measurement strongly recommended"),
            ("Embodied carbon scope",  "Not included",
             "Concept stage — add in detailed design"),
        ]
        st.dataframe(pd.DataFrame(carbon_rows, columns=["Parameter","Value","Reference"]),
                     use_container_width=True, hide_index=True)

        st.warning(
            "⚠️ **N₂O is the dominant carbon uncertainty** at concept stage. "
            "The IPCC 2019 Tier 1 EF has a ×10 range (0.005–0.050). "
            "Net carbon estimates should be presented as a range, not a single value."
        )

    # ── Risk assumptions ────────────────────────────────────────────────────
    with tab_risk_a:
        st.subheader("Risk Scoring Assumptions")
        st.caption("Technology maturity and scenario modifiers used in risk scoring (WEF MOP 35 framework).")

        risk_rows = [
            ("Risk matrix",         "5×5 likelihood × consequence",   "WEF MOP 35 Appendix B"),
            ("Scoring range",       "1–25 per item → 0–100 normalised",""),
            ("Category weights",    "Technical 30%, Implementation 25%, Operational 25%, Regulatory 20%", ""),
            ("BNR maturity",        "Low risk (>5,000 plants globally)", "IWA 2022"),
            ("AGS maturity",        "Moderate (~200 full-scale, 2024)", "de Kreuk 2007, Pronk 2015"),
            ("MABR maturity",       "Moderate-High (<50 full-scale, 2024)", "GE/Ovivo 2017"),
            ("MBR maturity",        "Low-Moderate (established, high ops)", "WEF MBR Manual"),
            ("Cold climate adj.",   "+1 likelihood to ops risk if T < 15°C", "Metcalf Fig 7-42"),
            ("High peak adj.",      "+1 likelihood to impl. risk if peak > 3×", ""),
            ("Tight TN adj.",       "+1 likelihood to reg. risk if TN < 8 mg/L", ""),
        ]
        st.dataframe(pd.DataFrame(risk_rows, columns=["Parameter","Value","Reference"]),
                     use_container_width=True, hide_index=True)

    # ── CAPEX unit rates ────────────────────────────────────────────────────
    with tab_capex:
        st.subheader("CAPEX Unit Rates")
        st.caption(
            "Unit rates used for CAPEX estimation. Economy of scale (Six-Tenths Rule) "
            "applied to civil tankage above 2,750 m³. All rates AUD 2024 ± 40%."
        )

        capex_rows = []
        display_map = {
            "aeration_tank_per_m3":           ("Aeration/SBR tankage",       "/m³",    "Civil + fitout"),
            "secondary_clarifier_per_m2":     ("Secondary clarifier",        "/m²",    "Including mechanism"),
            "mbr_membrane_per_m2":            ("MBR membrane (HF)",         "/m²",    "Installed"),
            "mbr_membrane_flat_sheet_per_m2": ("MBR membrane (flat sheet)", "/m²",    ""),
            "blower_per_kw":                  ("Blower/aeration system",     "/kW",    "Fine bubble"),
            "pump_per_kw":                    ("Pumps (RAS/WAS/MLR)",        "/kW",    "Installed"),
            "ifas_media_per_m2":              ("IFAS carrier media",         "/m²",    "Protected surface area"),
            "fine_screen_per_unit":           ("Fine screen",                "/unit",  "Pre-MBR"),
            "digester_per_m3":                ("Mesophilic digester",        "/m³",    "CSTR"),
            "chp_per_kw_installed":           ("CHP engine",                 "/kWe",   "Gas engine"),
            "uf_membrane_per_m2":             ("UF membrane (reuse)",        "/m²",    ""),
            "ro_membrane_per_m2":             ("RO membrane (reuse)",        "/m²",    ""),
            "rsf_per_m2_filter":              ("Rapid sand filter",          "/m²",    "Tertiary"),
        }
        for key, (label, unit, notes) in display_map.items():
            val = capex_costs.get(key)
            if val is not None:
                capex_rows.append((label, f"${val:,.0f}{unit}", notes))

        st.dataframe(pd.DataFrame(capex_rows, columns=["Item", "Rate", "Notes"]),
                     use_container_width=True, hide_index=True)

        st.caption(
            "Economy of scale: civil tankage uses Six-Tenths Rule "
            "(Cost × (V/V_base)^0.6 where V_base = 2,750 m³). "
            "Mechanical and electrical items scale linearly."
        )
