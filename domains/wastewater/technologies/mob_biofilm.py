"""
domains/wastewater/technologies/mob_biofilm.py

Mobile Organic Biofilm (MOB) Technology Module
================================================
MOB is a suspended-carrier biofilm process in which a biodegradable carrier
material supports both attached and suspended growth. Unlike MBBR, the carrier
is eventually consumed, eliminating the need for media replacement and reducing
sludge production by 40–60% relative to conventional activated sludge.

Commercial examples: BioStar® (Veolia), AquaCarb® concepts.

Process description
-------------------
- Biodegradable carriers (e.g. starch-based, cellulose) inoculated with
  biomass are added at 20–40% fill ratio to aeration basins.
- Carriers function as micro-environment for SND (simultaneous nitrification-
  denitrification) and biofilm COD removal.
- Net sludge yield 0.10–0.20 kgVSS/kgBOD (vs 0.35–0.45 for CAS).
- Energy intensity similar to CAS, with slight savings from reduced WAS handling.
- Suitable as an upgrade to existing aeration tanks with minimal civil works.

Design basis
------------
- BOD surface loading rate: 5–15 g BOD/m²·day (carrier surface area)
- Hydraulic loading identical to upstream settler design
- Carrier fill ratio: 20–40% reactor volume
- Typical HRT: 4–8 hours

References
----------
- Ødegaard (2006) — Innovative and flexible MBBR design, Water Science & Technology
- Bassin et al. (2012) — Sludge reduction in suspended carrier processes
- WEF MOP No.35 (2012) — Biofilm Reactors, Chapter 6
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Type

from domains.wastewater.technologies.base_technology import (
    BaseTechnology,
    CostItem,
    TechnologyResult,
)


# ─────────────────────────────────────────────────────────────────────────────
# INPUTS DATACLASS
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class MOBInputs:
    """
    Design parameters for the Mobile Organic Biofilm process.

    All concentration values in mg/L unless noted.
    All volumetric values in m³ unless noted.
    """
    # ── Process configuration ──────────────────────────────────────────────
    upgrade_existing: bool = True
    # True  → retrofit into existing aeration basins (lower CAPEX, no new tankage)
    # False → greenfield (new concrete, full CAPEX)

    # ── Carrier parameters ─────────────────────────────────────────────────
    carrier_fill_ratio: float = 0.30
    # Volumetric fill ratio of carriers in aeration basin (0.20–0.40)

    carrier_specific_surface_area_m2_m3: float = 800.0
    # Carrier specific surface area (m² per m³ of carrier). Typical: 600–1000 m²/m³.

    bod_surface_loading_g_m2_day: float = 8.0
    # BOD surface loading rate on carrier (g BOD/m²·day). Design range: 5–15.

    # ── Biological performance ─────────────────────────────────────────────
    y_obs_kg_vss_kg_bod: float = 0.15
    # Observed sludge yield. MOB typical: 0.10–0.20 (vs CAS 0.35–0.45)

    nitrification_efficiency: float = 0.90
    # Fraction of influent NH4 nitrified (0.80–0.95 at adequate SRT and T)

    denitrification_efficiency: float = 0.70
    # Fraction of nitrified N denitrified via SND on carrier

    design_temperature_celsius: float = 20.0
    # Basin temperature. Nitrification rate halves at ~10°C.

    # ── Aeration ───────────────────────────────────────────────────────────
    do_aerobic_mg_l: float = 2.0
    # Dissolved oxygen setpoint in aeration zone

    # ── Effluent targets ───────────────────────────────────────────────────
    target_effluent_nh4_mg_l: float = 3.0
    target_effluent_tn_mg_l: float = 10.0
    target_effluent_tp_mg_l: float = 1.0

    # ── Tertiary P removal ─────────────────────────────────────────────────
    chemical_p_polish: bool = False
    # Add ferric chloride dose for final TP polishing below 1 mg/L

    # ── Field validation bounds (not displayed to user) ───────────────────
    _field_bounds: dict = field(default_factory=lambda: {
        "carrier_fill_ratio":                (0.15, 0.50),
        "bod_surface_loading_g_m2_day":       (3.0,  20.0),
        "y_obs_kg_vss_kg_bod":               (0.05, 0.30),
        "nitrification_efficiency":           (0.60, 0.98),
        "design_temperature_celsius":         (10.0, 30.0),
    }, repr=False)


# ─────────────────────────────────────────────────────────────────────────────
# TECHNOLOGY CLASS
# ─────────────────────────────────────────────────────────────────────────────

class MOBTechnology(BaseTechnology):
    """
    Mobile Organic Biofilm (MOB) treatment pathway module.

    Advantages
    ----------
    - Sludge reduction 40–60% vs conventional activated sludge
    - Retrofit into existing aeration basins (no new tankage for upgrades)
    - SND on carrier surface reduces aeration energy ~10–20%
    - No media replacement required (carrier is biodegraded)

    Limitations
    -----------
    - Limited full-scale references vs MBBR/IFAS
    - Carrier consumption adds a new supply/operational cost
    - N removal requires anoxic zones or SND control — less predictable
      than dedicated anoxic zones
    - Technology maturity: commercial but emerging at large scale
    """

    @property
    def technology_code(self) -> str:
        return "mob"

    @property
    def technology_name(self) -> str:
        return "Mobile Organic Biofilm (MOB)"

    @property
    def technology_category(self) -> str:
        return "biological"

    @property
    def applicable_scales(self):
        return ["small", "medium"]   # Limited large-scale references

    @classmethod
    def input_class(cls) -> Type:
        return MOBInputs

    # ─────────────────────────────────────────────────────────────────────
    # CALCULATE
    # ─────────────────────────────────────────────────────────────────────

    def calculate(
        self,
        design_flow_mld: float,
        inputs: MOBInputs,
    ) -> TechnologyResult:
        r = TechnologyResult(
            technology_name=self.technology_name,
            technology_code=self.technology_code,
            technology_category="Biological Treatment",
            description="Suspended-carrier biofilm process with low sludge yield.",
        )

        flow_m3_day = design_flow_mld * 1000.0

        # ── 1. Influent loads ─────────────────────────────────────────────
        inf = self._load_influent()
        bod_load_kg_day = flow_m3_day * inf["bod_mg_l"] / 1000.0
        nh4_load_kg_day = flow_m3_day * inf["tn_mg_l"] * 0.78 / 1000.0
        # Assume 78% of TN is NH4-N (typical municipal wastewater)

        r.note(
            f"Influent: BOD {inf['bod_mg_l']:.0f} mg/L, "
            f"TN {inf['tn_mg_l']:.0f} mg/L, TP {inf['tp_mg_l']:.0f} mg/L, "
            f"Q = {design_flow_mld:.1f} MLD"
        )
        r.notes.add_assumption(
            f"Influent: BOD {inf['bod_mg_l']:.0f}, TN {inf['tn_mg_l']:.0f}, "
            f"TP {inf['tp_mg_l']:.0f} mg/L at Q = {design_flow_mld:.1f} MLD"
        )
        r.notes.add_assumption(
            f"Carrier fill ratio: {inputs.carrier_fill_ratio:.0%}, "
            f"BOD surface loading: {inputs.bod_surface_loading_g_m2_day} g BOD/m²/day, "
            f"y_obs = {inputs.y_obs_kg_vss_kg_bod} kgVSS/kgBOD (low yield — key MOB advantage)"
        )

        # ── 2. Reactor volume from carrier surface loading ────────────────
        # Total carrier surface area required:
        #   A_carrier = BOD_load / bod_surface_loading
        carrier_area_m2 = bod_load_kg_day * 1000 / inputs.bod_surface_loading_g_m2_day
        # Carrier volume:
        #   V_carrier = A_carrier / specific_surface_area
        carrier_volume_m3 = carrier_area_m2 / inputs.carrier_specific_surface_area_m2_m3
        # Total reactor volume from fill ratio:
        reactor_volume_m3 = carrier_volume_m3 / inputs.carrier_fill_ratio

        hrt_hr = (reactor_volume_m3 / flow_m3_day) * 24.0

        r.note(
            f"Carrier surface area: {carrier_area_m2:,.0f} m² | "
            f"Reactor volume: {reactor_volume_m3:,.0f} m³ | "
            f"HRT: {hrt_hr:.1f} hr"
        )

        # ── 3. Temperature correction for nitrification ───────────────────
        # Nitrification rate halves for every ~10°C below 20°C (Arrhenius).
        # Theta factor for nitrification: ~1.07 (Metcalf & Eddy Table 9-7)
        theta_nit = 1.07
        T_correction = theta_nit ** (inputs.design_temperature_celsius - 20.0)
        eff_nitrification = inputs.nitrification_efficiency * T_correction
        eff_nitrification = min(eff_nitrification, 0.98)

        r.note(
            f"Temperature correction (T={inputs.design_temperature_celsius}°C): "
            f"nitrification efficiency = {eff_nitrification*100:.0f}% "
            f"(uncorrected: {inputs.nitrification_efficiency*100:.0f}%)"
        )

        # ── 4. Effluent quality ───────────────────────────────────────────
        eff_nh4 = max(
            inf["tn_mg_l"] * 0.78 * (1.0 - eff_nitrification),
            inputs.target_effluent_nh4_mg_l,
        )
        nh4_nitrified_kg_day = nh4_load_kg_day * eff_nitrification

        # TN: nitrified N partly denitrified via SND on carrier
        n_denitrified_kg_day = nh4_nitrified_kg_day * inputs.denitrification_efficiency
        tn_out_mg_l = max(
            inf["tn_mg_l"] - (n_denitrified_kg_day + (nh4_load_kg_day - nh4_nitrified_kg_day)) * 1000 / flow_m3_day,
            inputs.target_effluent_tn_mg_l,
        )

        # TP: biological removal is limited in MOB; chemical polish optional
        tp_bio_removal_pct = 0.20  # Biological uptake: ~15–25%
        tp_out_bio = inf["tp_mg_l"] * (1.0 - tp_bio_removal_pct)

        if inputs.chemical_p_polish:
            tp_out = min(tp_out_bio, inputs.target_effluent_tp_mg_l)
        else:
            tp_out = tp_out_bio

        # BOD and TSS
        eff_bod = 8.0   # Typical biofilm process effluent (mg/L)
        eff_tss = 12.0  # Slightly higher than MBR, lower than CAS secondary

        r.performance.effluent_nh4_mg_l = round(eff_nh4, 2)
        r.performance.effluent_tn_mg_l  = round(tn_out_mg_l, 1)
        r.performance.effluent_tp_mg_l  = round(tp_out, 2)
        r.performance.effluent_bod_mg_l = eff_bod
        r.performance.effluent_tss_mg_l = eff_tss
        r.performance.reactor_volume_m3 = round(reactor_volume_m3, 0)
        r.performance.hydraulic_retention_time_hr = round(hrt_hr, 1)
        r.performance.footprint_m2 = (
            reactor_volume_m3 * 0.28   # Approximate basin depth ~3.5 m
            + flow_m3_day / 24.0 * 1.5  # Rough secondary clarifier area
        )
        r.performance.additional.update({
            "carrier_fill_ratio":                inputs.carrier_fill_ratio,
            "carrier_surface_area_m2":           round(carrier_area_m2, 0),
            "carrier_specific_surface_area_m2_m3": inputs.carrier_specific_surface_area_m2_m3,
            "nitrification_efficiency_corrected": round(eff_nitrification, 3),
            "tn_removed_kg_day":                 round(n_denitrified_kg_day, 1),
        })

        # ── 5. Sludge production ──────────────────────────────────────────
        # KEY ADVANTAGE: Low yield due to endogenous respiration on carrier
        vss_production_kg_day = inputs.y_obs_kg_vss_kg_bod * bod_load_kg_day
        vss_to_tss = self._get_eng("vss_to_tss_ratio", 0.80)
        tss_production_kg_day = vss_production_kg_day / vss_to_tss

        # Inorganic TSS pass-through
        inorganic_kg_day = flow_m3_day * inf["tss_mg_l"] * (1.0 - vss_to_tss) / 1000.0
        total_sludge_kg_day = tss_production_kg_day + inorganic_kg_day

        r.sludge.biological_sludge_kgds_day = round(total_sludge_kg_day, 1)
        r.sludge.vs_fraction = 0.78
        r.sludge.feed_ts_pct = 1.2   # Slightly denser WAS from biofilm

        r.note(
            f"Sludge yield: {inputs.y_obs_kg_vss_kg_bod:.2f} kgVSS/kgBOD "
            f"(40–60% lower than CAS) | "
            f"Total WAS: {total_sludge_kg_day:.0f} kg DS/day"
        )

        # ── 6. Oxygen demand and aeration energy ──────────────────────────
        # Carbonaceous O2 demand (Metcalf & Eddy eq. 8-47)
        o2_carbonaceous = bod_load_kg_day * (1.0 - 1.42 * inputs.y_obs_kg_vss_kg_bod)   # carbonaceous (Metcalf Eq 7-57)

        # Nitrification O2: 4.57 kg O2 / kg NH4-N oxidised
        o2_nitrification = 4.57 * nh4_nitrified_kg_day

        # Denitrification credit: 2.86 kg O2 / kg NO3-N denitrified
        o2_credit_denitrification = 2.86 * n_denitrified_kg_day

        o2_total_kg_day = max(
            0.0,
            o2_carbonaceous + o2_nitrification - o2_credit_denitrification,
        )

        # Process-water aeration efficiency
        alpha = self._get_eng("alpha_factor", 0.55)
        # MOB biofilm processes typically have alpha 0.60–0.70 due to lower
        # MLSS (less surfactant effect) than high-MLSS CAS
        alpha_mob = alpha * 1.15   # +15% vs CAS default
        sae_clean = self._get_eng("standard_aeration_efficiency_kg_o2_kwh", 1.8)
        sae_process = sae_clean * alpha_mob

        aeration_kwh_day = o2_total_kg_day / sae_process

        # Mixing (carrier suspension requires gentle mixing ~5 W/m³)
        mixing_kw_per_m3 = 0.005   # 5 W/m³ for MOB (lower than CAS anoxic 8 W/m³)
        mixing_kwh_day = reactor_volume_m3 * mixing_kw_per_m3 * 24.0

        # RAS/WAS pumping
        pump_eff = self._get_eng("pump_efficiency", 0.72)
        ras_flow_m3_day = flow_m3_day * 0.75   # 75% RAS ratio
        ras_head_m = 2.5
        ras_kwh_day = (ras_flow_m3_day * ras_head_m * 9.81 * 1000) / (
            3600 * 1000 * pump_eff
        ) * 24.0

        r.energy.aeration_kwh_day = round(aeration_kwh_day, 1)
        r.energy.mixing_kwh_day   = round(mixing_kwh_day, 1)
        r.energy.pumping_kwh_day  = round(ras_kwh_day, 1)

        r.note(
            f"O2 demand: {o2_total_kg_day:.0f} kg/day "
            f"(carbonaceous {o2_carbonaceous:.0f} + nitrification {o2_nitrification:.0f} "
            f"- denitrification credit {o2_credit_denitrification:.0f}) | "
            f"SAE process: {sae_process:.2f} kg O2/kWh (alpha_mob = {alpha_mob:.2f})"
        )

        # ── 7. Chemical consumption ───────────────────────────────────────
        chemicals: Dict[str, float] = {}

        if inputs.chemical_p_polish:
            tp_to_remove_kg_day = (tp_out_bio - tp_out) * flow_m3_day / 1000.0
            tp_mol_day = tp_to_remove_kg_day * 1000.0 / 31.0
            # Ferric chloride dose: 2.5 mol FeCl3 per mol P (safety factor included)
            ferric_kg_day = tp_mol_day * 2.5 * 162.2 / 1000.0
            chemicals["ferric_chloride_kg_day"] = round(ferric_kg_day, 2)
            r.note(f"Chemical P polish: FeCl3 dose = {ferric_kg_day:.1f} kg/day")

        r.chemical_consumption = chemicals

        # ── 8. Scope 1 process emissions ──────────────────────────────────
        # N2O from biological nitrogen removal
        n2o_ef   = self._get_eng("n2o_emission_factor_g_n2o_per_g_n_removed", 0.016)
        n2o_gwp  = self._get_eng("n2o_gwp", 298)
        n_removed_kg_day = n_denitrified_kg_day + (nh4_load_kg_day - nh4_nitrified_kg_day)
        n2o_kg_day = n_removed_kg_day * 1000.0 * n2o_ef / 1000.0
        r.carbon.n2o_biological_tco2e_yr = round(n2o_kg_day * 365 * n2o_gwp / 1000.0, 2)

        # CH4 from residual anaerobic pockets in biofilm (very low)
        ch4_ef  = self._get_eng("ch4_emission_factor_g_ch4_per_g_bod_influent", 0.0025)
        ch4_gwp = self._get_eng("ch4_gwp", 28)
        ch4_kg_day = bod_load_kg_day * 1000.0 * ch4_ef / 1000.0 * 0.5
        # Factor 0.5: biofilm structure reduces methanogenesis vs free water
        r.carbon.ch4_fugitive_tco2e_yr = round(ch4_kg_day * 365 * ch4_gwp / 1000.0, 2)

        # ── 9. Risk flags ─────────────────────────────────────────────────
        r.risk.reliability_risk       = "Moderate"  # Carrier degradation rate variability
        r.risk.regulatory_risk        = "Low"        # Standard effluent limits achievable
        r.risk.technology_maturity    = "Emerging"   # Commercial but limited large-scale data
        r.risk.operational_complexity = "Moderate"   # Carrier management adds operator tasks
        r.risk.site_constraint_risk   = "Low" if inputs.upgrade_existing else "Moderate"
        r.risk.additional_flags["carrier_supply_chain_risk"] = "Moderate"
        r.risk.additional_flags["low_temperature_performance_risk"] = (
            "High" if inputs.design_temperature_celsius < 15.0 else "Low"
        )

        # ── 10. CAPEX ─────────────────────────────────────────────────────
        if inputs.upgrade_existing:
            # Retrofit: no new tankage, just carriers + aeration upgrades
            r.capex_items = [
                CostItem(
                    name="MOB carrier media (initial charge)",
                    cost_basis_key="mob_carrier_per_m3_reactor",
                    quantity=reactor_volume_m3 * inputs.carrier_fill_ratio,
                    unit="m³ carrier",
                    notes="Biodegradable carrier initial charge",
                ),
                CostItem(
                    name="Aeration system upgrade",
                    cost_basis_key="fine_bubble_diffuser_upgrade_per_m3",
                    quantity=reactor_volume_m3,
                    unit="m³ reactor",
                ),
                CostItem(
                    name="RAS/WAS pumping upgrade",
                    cost_basis_key="pump_per_kw",
                    quantity=ras_kwh_day / 24.0,
                    unit="kW",
                ),
            ]
        else:
            # Greenfield: full tankage
            r.capex_items = [
                CostItem(
                    name="MOB aeration basin (concrete)",
                    cost_basis_key="aeration_tank_per_m3",
                    quantity=reactor_volume_m3,
                    unit="m³",
                ),
                CostItem(
                    name="MOB carrier media (initial charge)",
                    cost_basis_key="mob_carrier_per_m3_reactor",
                    quantity=reactor_volume_m3 * inputs.carrier_fill_ratio,
                    unit="m³ carrier",
                ),
                CostItem(
                    name="Secondary clarifier",
                    cost_basis_key="secondary_clarifier_per_m2",
                    quantity=flow_m3_day / 24.0 / 1.5,  # m² at 1.5 m/hr SOR
                    unit="m²",
                ),
                CostItem(
                    name="Blower system",
                    cost_basis_key="blower_per_kw",
                    quantity=aeration_kwh_day / 24.0,
                    unit="kW",
                ),
                CostItem(
                    name="RAS/WAS pump systems",
                    cost_basis_key="pump_per_kw",
                    quantity=ras_kwh_day / 24.0,
                    unit="kW",
                ),
            ]

        # ── 11. OPEX ──────────────────────────────────────────────────────
        # Carrier replenishment: MOB carriers are consumed over time
        # Typical carrier consumption: 0.05–0.10 kg carrier per kg BOD removed
        # Cost included as a separate OPEX line
        carrier_consumption_kg_day = bod_load_kg_day * 0.07  # 70 g carrier / kg BOD

        r.opex_items = [
            CostItem(
                name="Electricity — aeration",
                cost_basis_key="electricity_per_kwh",
                quantity=aeration_kwh_day,
                unit="kWh/day",
            ),
            CostItem(
                name="Electricity — mixing & pumping",
                cost_basis_key="electricity_per_kwh",
                quantity=mixing_kwh_day + ras_kwh_day,
                unit="kWh/day",
            ),
            CostItem(
                name="MOB carrier replenishment",
                cost_basis_key="mob_carrier_per_kg",
                quantity=carrier_consumption_kg_day,
                unit="kg/day",
                notes="Biodegradable carrier ongoing consumption (0.07 kg/kg BOD removed)",
            ),
        ]

        if inputs.chemical_p_polish and "ferric_chloride_kg_day" in chemicals:
            r.opex_items.append(CostItem(
                name="Ferric chloride (P polish)",
                cost_basis_key="ferric_chloride_per_kg",
                quantity=chemicals["ferric_chloride_kg_day"],
                unit="kg/day",
            ))

        # ── 12. Assumptions log ───────────────────────────────────────────
        r.assumptions_used = {
            "carrier_fill_ratio":                inputs.carrier_fill_ratio,
            "carrier_specific_surface_area_m2_m3": inputs.carrier_specific_surface_area_m2_m3,
            "bod_surface_loading_g_m2_day":       inputs.bod_surface_loading_g_m2_day,
            "y_obs_kg_vss_kg_bod":               inputs.y_obs_kg_vss_kg_bod,
            "nitrification_efficiency_design":    inputs.nitrification_efficiency,
            "nitrification_efficiency_T_corrected": round(eff_nitrification, 3),
            "alpha_factor_base":                  alpha,
            "alpha_factor_mob":                   round(alpha_mob, 3),
            "sae_process_kg_o2_kwh":              round(sae_process, 2),
            "design_temperature_celsius":         inputs.design_temperature_celsius,
            "upgrade_existing":                   inputs.upgrade_existing,
        }

        # ── 13. Finalise ──────────────────────────────────────────────────
        return r.finalise(design_flow_mld)
