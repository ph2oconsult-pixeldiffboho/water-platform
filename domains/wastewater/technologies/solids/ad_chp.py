"""
domains/wastewater/technologies/solids/ad_chp.py

Anaerobic Digestion + Combined Heat and Power (AD+CHP)
=======================================================
Mesophilic anaerobic digestion of wastewater biosolids with biogas
capture and electricity + heat recovery via a CHP engine.

This is a solids-side module. The design_flow_mld parameter is used only
for normalising energy intensity per ML treated. Primary sizing is based
on the sludge feed rate (feed_kgds_day).

Process description
-------------------
1. Raw or thickened sludge feeds a covered anaerobic digester (35–37°C).
2. Volatile solids are destroyed by methanogenesis; biogas (60–70% CH4) is produced.
3. Biogas is combusted in a CHP engine producing electricity + recoverable heat.
4. CHP heat is used to maintain digester temperature; surplus is available for export.
5. Digested sludge is dewatered and disposed (land application, landfill, or thermal).

Key outcomes
------------
• 55–65% VS destruction → 35–45% reduction in sludge mass to dispose
• Net electricity production: ~0.2–0.4 kWh per kg VS destroyed
• Avoided grid electricity → significant carbon credit
• Scope 1 fugitive CH4 is the main carbon liability (cover integrity critical)

Design basis
------------
• Biogas yield:    0.75 m³ biogas / kg VS destroyed (mesophilic municipal, MIDPOINT)
                   Range: 0.60–0.85. Use higher values only for FOG co-digestion.
• CH4 fraction:    65% vol (dry basis)
• CHP efficiency:  38% electrical, 45% thermal (gas engine, Jenbacher/Rolls-Royce class)
• Fugitive CH4:    2% of generated methane (combined cover + handling losses)
• Digester HRT:    20 days minimum (mesophilic); achieves ~58% VS destruction
• Heating demand:  Q = ṁ × Cp × ΔT × 1.10 (10% losses)

References
----------
  - Metcalf & Eddy (2014) Ch. 10 — Anaerobic Treatment and Biogas
  - WEF MOP 36 (2012) — Biogas Production and Use
  - IEA Bioenergy (2020) — Biomethane: Key to Decarbonise Gas Grids
  - Foley et al. (2010) — Fugitive emissions from anaerobic digesters
  - IPCC (2019) Refinement Vol.5 Ch. 6 — Methane from anaerobic digesters
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Type

from domains.wastewater.technologies.base_technology import (
    BaseTechnology, CostItem, TechnologyResult,
)

# Physical constants
CH4_LHV_MJ_M3   = 35.8    # Lower heating value methane (MJ/Nm³)
CH4_DENSITY_KG_M3 = 0.716  # kg/Nm³ at standard conditions
N2O_GWP         = 273.0    # AR6 GWP100
CH4_GWP         = 28.0     # AR6 GWP100


@dataclass
class ADCHPInputs:
    """Design parameters for the Anaerobic Digestion + CHP process."""

    # ── Feed characterisation ──────────────────────────────────────────────
    feed_kgds_day: float = 1500.0
    # Sludge feed rate (kg dry solids/day). Set from upstream sludge model.

    feed_ts_pct: float = 5.0
    # Total solids % of thickened sludge feed (typical: 4–6% for gravity thickened WAS)

    feed_vs_fraction: float = 0.80
    # VS/DS ratio in feed (raw WAS: 0.75–0.85; primary: 0.65–0.75)

    # ── Digestion performance ─────────────────────────────────────────────
    vs_destruction_pct: float = 58.0
    # VS destruction (%). Mesophilic 35°C, 20d HRT: 50–62%.

    biogas_yield_m3_per_kg_vs: float = 0.75
    # m³ biogas / kg VS destroyed. Municipal mesophilic midpoint.
    # IMPORTANT: 0.75 is correct for municipal sludge.
    # Use 0.85–1.0 ONLY if FOG or food waste co-digestion is confirmed.

    biogas_ch4_fraction: float = 0.65
    # CH4 volume fraction in biogas (0.60–0.70 typical)

    digester_temp_celsius: float = 37.0
    # Mesophilic: 35–38°C. Thermophilic: 52–55°C.

    feed_temp_celsius: float = 18.0
    # Temperature of sludge feed (°C). Affects digester heating demand.

    # ── Methane capture and utilisation ───────────────────────────────────
    methane_capture_efficiency: float = 0.95
    # Fraction of generated methane captured in the gas collection system.

    cover_fugitive_fraction: float = 0.015
    # Fugitive losses at digester cover/seals: 1.5% of generated (Foley 2010)

    handling_fugitive_fraction: float = 0.005
    # Losses from maintenance events, valve releases: 0.5%

    flare_fraction: float = 0.05
    # Fraction of captured gas sent to flare (standby/maintenance: ~5%)

    # ── CHP parameters ────────────────────────────────────────────────────
    chp_electrical_efficiency: float = 0.38
    # Electrical efficiency of gas CHP engine (35–42% for modern units)

    chp_thermal_efficiency: float = 0.45
    # Recoverable heat from CHP jacket water + exhaust (40–50%)

    # ── Dewatered cake ────────────────────────────────────────────────────
    cake_ts_pct: float = 22.0
    # Dewatered cake TS% (centrifuge: 18–25%)

    # ── Field bounds ──────────────────────────────────────────────────────
    _field_bounds: dict = field(default_factory=lambda: {
        "vs_destruction_pct":       (40.0, 75.0),
        "biogas_yield_m3_per_kg_vs": (0.50, 1.10),
        "biogas_ch4_fraction":      (0.55, 0.72),
        "digester_temp_celsius":    (30.0, 58.0),
        "feed_ts_pct":              (2.0, 12.0),
        "cake_ts_pct":              (12.0, 35.0),
    }, repr=False)


class ADCHPTechnology(BaseTechnology):
    """
    Anaerobic Digestion + Combined Heat and Power — screening-level planning model.

    Advantages
    ----------
    - Net energy producer: reduces plant electricity bill by 30–60%
    - Significant sludge mass reduction (35–45% of DS)
    - Established technology with 50+ years of operating data
    - Reduces PFAS concentration in sludge (not destroyed — mass transfer to gas/liquid)

    Limitations
    -----------
    - Requires long SRT (≥20 days) and temperature control — capital intensive
    - CHP electrical output depends heavily on sludge VS fraction and yield
    - Fugitive CH4 is the dominant Scope 1 risk if covers are poorly maintained
    - Digested sludge still requires disposal — PFAS not destroyed
    """

    @property
    def technology_code(self) -> str:
        return "ad_chp"

    @property
    def technology_name(self) -> str:
        return "Anaerobic Digestion + CHP"

    @property
    def technology_category(self) -> str:
        return "Solids / Energy Recovery"

    @property
    def requires_upstream(self):
        return ["bnr", "mbr", "granular_sludge", "anmbr"]

    @classmethod
    def input_class(cls) -> Type:
        return ADCHPInputs

    def calculate(self, design_flow_mld: float, inputs: ADCHPInputs) -> TechnologyResult:
        r = TechnologyResult(
            technology_name=self.technology_name,
            technology_code=self.technology_code,
            technology_category=self.technology_category,
            description=(
                "Mesophilic anaerobic digestion of wastewater biosolids "
                "with biogas recovery and CHP electricity generation."
            ),
        )

        # ── 1. Feed characterisation ───────────────────────────────────────
        feed_ds_t_yr  = inputs.feed_kgds_day * 365 / 1000.0
        feed_ts_frac  = inputs.feed_ts_pct / 100.0
        feed_wet_kg_day = inputs.feed_kgds_day / feed_ts_frac
        feed_vs_kg_day  = inputs.feed_kgds_day * inputs.feed_vs_fraction

        r.notes.add_assumption(
            f"Feed: {inputs.feed_kgds_day:.0f} kg DS/day "
            f"({feed_wet_kg_day:.0f} kg wet/day at {inputs.feed_ts_pct:.0f}% TS), "
            f"VS fraction = {inputs.feed_vs_fraction:.2f}"
        )

        # ── 2. VS destruction and digested sludge ─────────────────────────
        vs_dest_frac     = inputs.vs_destruction_pct / 100.0
        vs_destroyed_kg  = feed_vs_kg_day * vs_dest_frac
        vs_remaining_kg  = feed_vs_kg_day * (1.0 - vs_dest_frac)

        # Digested DS = feed DS - VS destroyed
        digested_ds_kg_day = inputs.feed_kgds_day - vs_destroyed_kg
        # Post-digestion VS/DS ratio (lower than feed)
        dig_vs_frac = vs_remaining_kg / digested_ds_kg_day if digested_ds_kg_day > 0 else 0.60

        # Dewatered cake mass
        cake_frac   = inputs.cake_ts_pct / 100.0
        cake_wet_kg_day = digested_ds_kg_day / cake_frac

        r.sludge.biological_sludge_kgds_day = round(digested_ds_kg_day, 1)
        r.sludge.vs_fraction  = round(dig_vs_frac, 3)
        r.sludge.feed_ts_pct  = inputs.cake_ts_pct
        r.performance.additional.update({
            "feed_ds_kgday":           round(inputs.feed_kgds_day, 0),
            "feed_vs_kgday":           round(feed_vs_kg_day, 0),
            "vs_destroyed_kgday":      round(vs_destroyed_kg, 0),
            "vs_destruction_pct":      inputs.vs_destruction_pct,
            "digested_ds_kgday":       round(digested_ds_kg_day, 0),
            "digested_ds_tyr":         round(digested_ds_kg_day * 365 / 1000, 0),
            "cake_wet_kgday":          round(cake_wet_kg_day, 0),
            "cake_wet_tyr":            round(cake_wet_kg_day * 365 / 1000, 0),
            "sludge_mass_reduction_pct": round((1 - digested_ds_kg_day / inputs.feed_kgds_day) * 100, 1),
        })

        r.notes.add_assumption(
            f"VS destruction: {inputs.vs_destruction_pct:.0f}% "
            f"(mesophilic 35°C, 20d HRT) → "
            f"{vs_destroyed_kg:.0f} kg VS/day destroyed"
        )

        # ── 3. Biogas production ───────────────────────────────────────────
        biogas_m3_day = vs_destroyed_kg * inputs.biogas_yield_m3_per_kg_vs
        ch4_m3_day    = biogas_m3_day * inputs.biogas_ch4_fraction
        ch4_kg_day    = ch4_m3_day * CH4_DENSITY_KG_M3

        # Specific biogas check
        spec_biogas = biogas_m3_day / inputs.feed_kgds_day * 1000  # m³/t DS
        if spec_biogas > 400:   # >400 m³/t DS is high for municipal — flag for review
            r.notes.warn(
                f"Specific biogas yield ({spec_biogas:.0f} m³/t DS) is high for municipal sludge. "
                "Confirm FOG co-digestion or elevated VS fraction before accepting this value."
            )

        r.energy.biogas_m3_day = round(biogas_m3_day, 0)
        r.energy.ch4_m3_day    = round(ch4_m3_day, 0)
        r.performance.additional.update({
            "biogas_m3_day":             round(biogas_m3_day, 0),
            "biogas_m3_yr":              round(biogas_m3_day * 365, 0),
            "ch4_m3_day":                round(ch4_m3_day, 0),
            "biogas_yield_m3_per_kg_vs": inputs.biogas_yield_m3_per_kg_vs,
        })

        r.notes.add_assumption(
            f"Biogas yield: {inputs.biogas_yield_m3_per_kg_vs} m³/kg VS destroyed "
            f"(municipal mesophilic midpoint; range 0.60–0.85) — WEF MOP 36"
        )

        # ── 4. Methane pathway allocation ─────────────────────────────────
        # generated = captured (→CHP + flare) + cover_fugitive + handling_fugitive
        ch4_cover    = ch4_m3_day * inputs.cover_fugitive_fraction
        ch4_handling = ch4_m3_day * inputs.handling_fugitive_fraction
        ch4_available = ch4_m3_day - ch4_cover - ch4_handling
        ch4_captured  = ch4_available * inputs.methane_capture_efficiency
        ch4_uncoll    = ch4_available * (1.0 - inputs.methane_capture_efficiency)
        ch4_to_flare  = ch4_captured * inputs.flare_fraction
        ch4_to_chp    = ch4_captured * (1.0 - inputs.flare_fraction)

        # All non-combusted CH4 is Scope 1 at GWP28
        ch4_fugitive_total_m3 = ch4_cover + ch4_handling + ch4_uncoll
        ch4_fugitive_kg       = ch4_fugitive_total_m3 * CH4_DENSITY_KG_M3

        r.notes.add_assumption(
            f"CH4 pathways: to CHP {ch4_to_chp:.0f} m³/day, "
            f"flared {ch4_to_flare:.0f}, "
            f"fugitive (all sources) {ch4_fugitive_total_m3:.0f} m³/day "
            f"({ch4_fugitive_total_m3/ch4_m3_day*100:.1f}% of generated)"
        )

        # ── 5. CHP energy production ───────────────────────────────────────
        chp_thermal_kw_mj_day = ch4_to_chp * CH4_LHV_MJ_M3
        chp_elec_kwh_day = chp_thermal_kw_mj_day * inputs.chp_electrical_efficiency / 3.6
        chp_heat_kwh_day = chp_thermal_kw_mj_day * inputs.chp_thermal_efficiency / 3.6

        r.energy.generation_kwh_day = round(chp_elec_kwh_day, 1)
        r.performance.additional.update({
            "chp_electricity_kwh_day": round(chp_elec_kwh_day, 0),
            "chp_electricity_kwh_yr":  round(chp_elec_kwh_day * 365, 0),
            "chp_heat_kwh_day":        round(chp_heat_kwh_day, 0),
            "chp_capacity_kw_avg":     round(chp_elec_kwh_day / 24.0, 1),
        })

        r.notes.add_assumption(
            f"CHP: {inputs.chp_electrical_efficiency*100:.0f}% electrical, "
            f"{inputs.chp_thermal_efficiency*100:.0f}% thermal (gas engine)"
        )

        # ── 6. Digester heating demand ────────────────────────────────────
        # Q = ṁ_wet × Cp_water × ΔT × loss_factor
        delta_T = inputs.digester_temp_celsius - inputs.feed_temp_celsius
        heat_kj_day = feed_wet_kg_day * 4.18 * delta_T * 1.10   # 10% losses
        heat_kwh_day = heat_kj_day / 3600.0

        heat_from_chp = min(chp_heat_kwh_day, heat_kwh_day)
        heat_deficit  = max(0.0, heat_kwh_day - heat_from_chp)

        r.performance.additional.update({
            "digester_heat_demand_kwh_day":  round(heat_kwh_day, 0),
            "heat_from_chp_kwh_day":         round(heat_from_chp, 0),
            "heat_deficit_kwh_day":          round(heat_deficit, 0),
        })

        # Supplemental gas boiler for deficit (Scope 2 via natural gas)
        gas_boiler_kwh = heat_deficit / 0.90  # 90% boiler efficiency
        r.energy.other_kwh_day = round(gas_boiler_kwh, 1)   # Auxiliary consumption

        r.notes.add_assumption(
            f"Digester heating: ΔT = {delta_T:.0f}°C, demand = {heat_kwh_day:.0f} kWh/day, "
            f"met by CHP: {heat_from_chp:.0f} kWh/day"
        )
        if heat_deficit > 0:
            r.notes.warn(
                f"CHP heat ({chp_heat_kwh_day:.0f} kWh/day) insufficient for digester heating "
                f"({heat_kwh_day:.0f} kWh/day). Supplemental gas boiler needed: "
                f"{heat_deficit:.0f} kWh/day."
            )

        # ── 7. Reject water (centrate) ────────────────────────────────────
        # ~70% of feed TKN is released to reject water (Metcalf Table 10-14)
        feed_tkn_frac = 0.055   # ~5.5% TKN of DS for raw WAS
        feed_tkn_kg   = inputs.feed_kgds_day * feed_tkn_frac
        reject_nh4_kgday = feed_tkn_kg * 0.70
        centrate_m3day   = feed_wet_kg_day * 0.18 / 1000.0   # 18% of feed as centrate
        centrate_nh4_mgl = reject_nh4_kgday / centrate_m3day if centrate_m3day > 0 else 0

        r.performance.additional.update({
            "reject_water_nh4_kgday":   round(reject_nh4_kgday, 1),
            "centrate_flow_m3day":      round(centrate_m3day, 1),
            "centrate_nh4_mgl":         round(centrate_nh4_mgl, 0),
        })
        r.notes.warn(
            f"Reject water returns {reject_nh4_kgday:.1f} kg NH4-N/day to liquid line "
            f"({centrate_nh4_mgl:.0f} mg/L NH4). This increases aeration demand in the "
            f"liquid treatment train."
        )

        # ── 8. Scope 1 emissions ──────────────────────────────────────────
        # All non-combusted CH4 is Scope 1 at GWP28
        r.carbon.ch4_fugitive_tco2e_yr = round(
            ch4_fugitive_kg * 365 * CH4_GWP / 1000.0, 1
        )

        # N2O from land application of biosolids (if applicable)
        # N in digested biosolids: ~3.5% of DS (lower than raw WAS ~5.5%)
        biosolids_n_kg_yr = digested_ds_kg_day * 0.035 * 365
        n2o_ef_land = 0.008   # NGER Class B incorporated: 0.8% of N applied
        n2o_land_kg_yr = biosolids_n_kg_yr * n2o_ef_land * (44.0/28.0)
        # NOTE: Included as indicative. Remove if biosolids go to landfill/incineration.
        r.carbon.other_scope1_tco2e_yr = round(n2o_land_kg_yr * N2O_GWP / 1000.0, 1)

        r.notes.add_assumption(
            f"Fugitive CH4: cover {inputs.cover_fugitive_fraction*100:.1f}% + "
            f"handling {inputs.handling_fugitive_fraction*100:.1f}% = "
            f"{ch4_fugitive_total_m3:.0f} m³/day total (Foley et al. 2010)"
        )
        r.notes.add_assumption(
            "Land application N2O EF: 0.8% of N applied (NGER Class B incorporated). "
            "Remove this if biosolids go to landfill or thermal treatment."
        )
        r.notes.add_limitation(
            "Avoided Scope 2 from CHP electricity is credited in the whole-plant carbon account, "
            "not in this module, to prevent double-counting."
        )

        # Avoided grid electricity (for reference; credited at whole-plant level)
        grid_ef = self._get_carbon("grid_emission_factor_kg_co2e_per_kwh", 0.79)
        avoided_tco2e_yr = chp_elec_kwh_day * 365 * grid_ef / 1000.0
        r.performance.additional["avoided_scope2_tco2e_yr_reference"] = round(avoided_tco2e_yr, 0)

        # ── 9. Risk ───────────────────────────────────────────────────────
        r.risk.reliability_risk       = "Low"          # Well-proven digestion technology
        r.risk.regulatory_risk        = "Low"          # Standard permits
        r.risk.technology_maturity    = "Established"
        r.risk.operational_complexity = "Moderate"     # Temperature, gas management
        r.risk.site_constraint_risk   = "Moderate"     # Digesters are large
        r.risk.implementation_risk    = "Low"

        r.risk.additional_flags["fugitive_ch4_management_risk"] = "Moderate"
        # Cover integrity, pressure relief valves, gas detection are critical
        r.risk.additional_flags["biosolids_disposal_risk"] = (
            "High" if r.performance.additional.get("digested_ds_tyr", 0) > 5000 else "Moderate"
        )

        # ── 10. CAPEX ─────────────────────────────────────────────────────
        digester_m3 = feed_wet_kg_day / 1000.0 * 20.0   # 20-day HRT at ~50 g/L feed
        chp_kw      = chp_elec_kwh_day / 24.0

        r.capex_items = [
            CostItem(
                "Anaerobic digester (concrete, covered)",
                "digester_per_m3", digester_m3, "m³",
                notes="Includes cover, gas collection, heating coils",
            ),
            CostItem(
                "CHP engine(s)",
                "chp_per_kw_installed", chp_kw, "kW installed",
                notes="Gas engine + generator; heat recovery circuit",
            ),
            CostItem(
                "Gas handling (compressor, flare, analyser)",
                "gas_handling_per_m3_biogas_day", biogas_m3_day, "m³/day",
            ),
            CostItem(
                "Sludge feed & dewatering",
                "sludge_handling_per_kgds_day", inputs.feed_kgds_day, "kg DS/day",
            ),
            CostItem(
                "Instrumentation & control",
                "digester_instrumentation_per_m3", digester_m3, "m³",
            ),
        ]

        # ── 11. OPEX ──────────────────────────────────────────────────────
        cake_disposal_tday = cake_wet_kg_day / 1000.0   # t wet cake/day

        r.opex_items = [
            CostItem(
                "Biosolids disposal (cake to landfill/land app)",
                "sludge_disposal_per_tds",
                digested_ds_kg_day / 1000.0, "t DS/day",
                notes="Includes transport; rate depends on disposal pathway",
            ),
            CostItem(
                "Electricity — auxiliary (pumps, fans, controls)",
                "electricity_per_kwh",
                gas_boiler_kwh + digester_m3 * 0.5 / 24.0,  # aux ~0.5 W/m³ digester
                "kWh/day",
            ),
            CostItem(
                "Maintenance — digesters and CHP",
                "digestion_maintenance_per_kgds_day",
                inputs.feed_kgds_day, "kg DS/day",
                notes="~3% of CAPEX/yr for digestion; 4–6% for CHP",
            ),
        ]

        r.notes.add_limitation(
            "CAPEX excludes: land, piping, electrical, PFAS characterisation of biosolids, "
            "and any CHP grid connection upgrade."
        )
        r.notes.add_limitation(
            "OPEX electricity credit from CHP is netted at whole-plant level."
        )

        # ── 12. Assumptions log ───────────────────────────────────────────
        r.assumptions_used = {
            "feed_kgds_day":             inputs.feed_kgds_day,
            "feed_vs_fraction":          inputs.feed_vs_fraction,
            "vs_destruction_pct":        inputs.vs_destruction_pct,
            "biogas_yield_m3_per_kg_vs": inputs.biogas_yield_m3_per_kg_vs,
            "biogas_ch4_fraction":       inputs.biogas_ch4_fraction,
            "chp_electrical_efficiency": inputs.chp_electrical_efficiency,
            "chp_thermal_efficiency":    inputs.chp_thermal_efficiency,
            "cover_fugitive_fraction":   inputs.cover_fugitive_fraction,
            "handling_fugitive_fraction": inputs.handling_fugitive_fraction,
            "methane_capture_efficiency": inputs.methane_capture_efficiency,
            "digester_temp_celsius":     inputs.digester_temp_celsius,
            "feed_temp_celsius":         inputs.feed_temp_celsius,
        }

        # ── 13. Finalise (ALWAYS last) ─────────────────────────────────────
        return r.finalise(design_flow_mld)
