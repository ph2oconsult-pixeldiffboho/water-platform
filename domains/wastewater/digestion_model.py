"""
domains/wastewater/digestion_model.py

Anaerobic Digestion and Methane Generation Model
=================================================
Screening-level model for biogas production, methane capture,
CHP energy recovery, fugitive emissions, and reject water characterisation.

AUDIT FIXES (v1.1)
------------------
  - Fixed methane mass balance: all non-combusted CH4 is now Scope 1 at GWP28
  - Corrected digester heating energy (first-principles heat balance)
  - Reduced default biogas yield from 0.90 → 0.75 m³/kg VS (mid-range municipal)
  - Added reject water (centrate) NH4 load estimation
  - Added post-digestion storage CH4 emissions
  - Added lime stabilisation as a digestion-type alternative
  - Updated documentation with IPCC 2019 and Metcalf & Eddy references

References
----------
  - Metcalf & Eddy 5th ed. Chapter 10 — Anaerobic treatment and biogas
  - IPCC (2019) — Refinement to 2006 Guidelines Vol.5 Waste, Chapter 6
  - WEF (2012) — Biogas Production and Use, MOP 36
  - IEA Bioenergy (2020) — Biomethane: the key to decarbonise gas grids
  - Foley et al. (2010) — Fugitive emissions from anaerobic sludge digesters
  - Yoshida et al. (2015) — N2O and CH4 from biosolids land application
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional

# Physical constants
CH4_ENERGY_DENSITY_MJ_M3  = 35.8    # MJ/Nm³ pure methane (lower heating value)
CH4_DENSITY_KG_M3          = 0.716   # kg/Nm³ at standard conditions
CH4_GWP_100                = 28.0    # AR6 GWP100 for CH4
CO2_GWP                    = 1.0
N2O_GWP_100                = 273.0   # AR6 GWP100 for N2O
WATER_SPECIFIC_HEAT_KJ_KG_K = 4.18   # kJ/kg·K
KJ_PER_KWH                 = 3600.0


@dataclass
class DigestionInputs:
    """Inputs to the anaerobic digestion and methane model."""

    # ── Feedstock ─────────────────────────────────────────────────────────
    feed_ds_t_yr: float = 550.0
    feed_vs_t_yr: float = 440.0
    feed_tkn_fraction: float = 0.055    # TKN as fraction of feed DS (raw WAS: 5-7%)

    # ── Digestion type ────────────────────────────────────────────────────
    digestion_type: str = "mesophilic_ad"
    # Options: mesophilic_ad | thermophilic_ad | lime_stabilisation | none

    # ── AD performance ────────────────────────────────────────────────────
    vs_destruction_pct: float = 58.0
    # Mesophilic (35°C, 20d SRT): 50-60%   Thermophilic (55°C, 12d SRT): 55-70%

    biogas_yield_m3_per_kg_vs_destroyed: float = 0.75
    # FIXED: default changed from 0.90 → 0.75 (mid-range municipal mesophilic)
    # Typical range: 0.60-0.80 municipal sludge; 0.80-1.0 with FOG co-digestion
    biogas_ch4_fraction: float = 0.65   # CH4 volume fraction (0.60-0.70 typical)
    biogas_co2_fraction: float = 0.34

    # ── Digester operating temperature ───────────────────────────────────
    digester_temp_celsius: float = 37.0     # Mesophilic
    feed_temp_celsius: float = 18.0         # Sludge feed temperature
    heat_loss_factor: float = 1.10          # 10% for cover/wall losses

    # ── Methane capture and utilisation ───────────────────────────────────
    methane_capture_efficiency: float = 0.95
    # Well-designed modern system: 0.92-0.97. 1990s systems: 0.85-0.92.
    # capture_efficiency applies inside the collection boundary (pipes, covers, seals)

    flare_fraction: float = 0.05            # Fraction of collected gas sent to flare
    # Flaring converts CH4 → CO2 (biogenic). Counted as zero net GWP.

    # FIXED: Separate fugitive sources
    cover_fugitive_fraction: float = 0.015
    # Losses from covers, membranes, joints: 1-2% of generated (Foley et al. 2010)
    handling_fugitive_fraction: float = 0.005
    # Maintenance events, relief valves, sludge handling: 0.5-1%

    # ── Post-digestion storage ────────────────────────────────────────────
    storage_ch4_fraction: float = 0.04
    # Residual CH4 from digested sludge in storage/holding tanks
    # IPCC 2019 Refinement recommends 3-7% of digester CH4 output
    storage_included: bool = True

    # ── CHP ───────────────────────────────────────────────────────────────
    chp_electrical_efficiency: float = 0.38  # 35-42% for gas engines
    chp_thermal_efficiency: float = 0.45     # Useful heat: 40-50%
    # Stack + radiation losses ≈ 17% (total = 100%)

    # ── Grid emission factor ──────────────────────────────────────────────
    grid_emission_factor_kg_co2e_per_kwh: float = 0.79

    # ── Enable flags ──────────────────────────────────────────────────────
    digestion_enabled: bool = True
    chp_enabled: bool = True


@dataclass
class BiogasResult:
    biogas_m3_yr: float = 0.0
    ch4_m3_yr: float = 0.0
    ch4_kg_yr: float = 0.0
    co2_m3_yr: float = 0.0
    ch4_energy_mj_yr: float = 0.0
    ch4_energy_kwh_yr: float = 0.0


@dataclass
class MethanePathwayResult:
    """
    FIXED mass balance:
      generated = to_CHP + to_flare + cover_fugitive + handling_fugitive + storage_ch4
      All non-combusted pathways are Scope 1 at GWP28.
    """
    ch4_generated_m3_yr: float = 0.0

    # Combustion pathways (CH4 → CO2, biogenic → zero net GWP)
    ch4_to_chp_m3_yr: float = 0.0
    ch4_to_flare_m3_yr: float = 0.0
    ch4_uncollected_m3_yr: float = 0.0   # Collection system losses (not fugitive cover)

    # Scope 1 fugitive (uncombusned CH4, GWP28)
    ch4_cover_fugitive_m3_yr: float = 0.0
    ch4_handling_fugitive_m3_yr: float = 0.0
    ch4_storage_m3_yr: float = 0.0
    ch4_total_fugitive_m3_yr: float = 0.0    # All Scope 1 CH4 combined
    ch4_total_fugitive_kg_yr: float = 0.0

    # Mass balance verification (should be ~0)
    mass_balance_discrepancy_pct: float = 0.0


@dataclass
class EnergyResult:
    electricity_kwh_yr: float = 0.0
    heat_kwh_yr: float = 0.0
    heat_used_for_digester_kwh_yr: float = 0.0  # From CHP heat to heat the digester
    electricity_kw_avg: float = 0.0
    chp_capacity_kw: float = 0.0
    avoided_grid_co2e_t_yr: float = 0.0
    # Digester heating demand
    digester_heat_demand_kwh_yr: float = 0.0
    digester_heat_deficit_kwh_yr: float = 0.0  # Additional heat needed (Scope 2 gas)


@dataclass
class RejectWaterResult:
    """
    Reject water (centrate/filtrate) characterisation.
    This NH4 load returns to the liquid treatment line.
    """
    nh4_kg_day: float = 0.0         # NH4-N returned to headworks
    flow_m3_day: float = 0.0        # Approximate reject water flow
    concentration_mg_l: float = 0.0
    pct_of_plant_tn_load: float = 0.0  # Indicative fraction of plant TN


@dataclass
class DigestionResult:
    biogas: BiogasResult = field(default_factory=BiogasResult)
    methane_pathways: MethanePathwayResult = field(default_factory=MethanePathwayResult)
    energy_recovery: EnergyResult = field(default_factory=EnergyResult)
    reject_water: RejectWaterResult = field(default_factory=RejectWaterResult)

    vs_destroyed_t_yr: float = 0.0
    vs_destruction_pct: float = 0.0
    digested_ds_t_yr: float = 0.0
    digested_vs_fraction: float = 0.0   # FIXED: updated post-digestion VS/DS

    # Scope 1 GHG from solids line (all non-combusted CH4)
    fugitive_ch4_tco2e_yr: float = 0.0  # Cover + handling + storage
    storage_ch4_tco2e_yr: float = 0.0

    # Lime stabilisation Scope 3 (if applicable)
    lime_kg_yr: float = 0.0
    lime_upstream_tco2e_yr: float = 0.0

    inputs_used: Dict[str, Any] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def note(self, msg: str) -> None:
        self.notes.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    def to_summary_dict(self) -> Dict[str, Any]:
        mp = self.methane_pathways
        er = self.energy_recovery
        return {
            "VS Destroyed (t/yr)":              round(self.vs_destroyed_t_yr, 0),
            "VS Destruction (%)":               round(self.vs_destruction_pct, 1),
            "Biogas (m³/yr)":                   round(self.biogas.biogas_m3_yr, 0),
            "CH₄ Generated (m³/yr)":            round(mp.ch4_generated_m3_yr, 0),
            "CH₄ to CHP (m³/yr)":               round(mp.ch4_to_chp_m3_yr, 0),
            "CH₄ Flared (m³/yr)":               round(mp.ch4_to_flare_m3_yr, 0),
            "CH₄ Fugitive – all sources (m³/yr)": round(mp.ch4_total_fugitive_m3_yr, 0),
            "Electricity Generated (MWh/yr)":   round(er.electricity_kwh_yr / 1000, 0),
            "Heat Recovered (MWh/yr)":          round(er.heat_kwh_yr / 1000, 0),
            "Digester Heat Demand (MWh/yr)":    round(er.digester_heat_demand_kwh_yr / 1000, 0),
            "CHP Capacity (kW)":                round(er.chp_capacity_kw, 0),
            "Avoided Grid Emissions (tCO₂e/yr)": round(er.avoided_grid_co2e_t_yr, 0),
            "Fugitive CH₄ Scope 1 (tCO₂e/yr)": round(self.fugitive_ch4_tco2e_yr, 1),
            "Reject Water NH₄ (kg/day)":        round(self.reject_water.nh4_kg_day, 1),
        }


class DigestionModel:
    """
    Anaerobic digestion performance and methane recovery model (v1.1).

    CRITICAL FIXES FROM ENGINEERING AUDIT:
    1. Methane mass balance now fully closed — all non-combusted CH4 is Scope 1
    2. Digester heating calculated from heat balance, not 5% parasitic
    3. Default biogas yield corrected to 0.75 m³/kg VS
    4. Reject water NH4 load estimated and flagged
    5. Post-digestion storage CH4 added
    6. Lime stabilisation pathway added
    """

    def calculate(self, inp: DigestionInputs) -> DigestionResult:
        r = DigestionResult()
        r.inputs_used = self._echo_inputs(inp)

        if inp.digestion_type == "none" or not inp.digestion_enabled:
            r.note("No sludge stabilisation selected.")
            return r

        if inp.digestion_type == "lime_stabilisation":
            return self._calculate_lime(inp, r)

        return self._calculate_ad(inp, r)

    def _calculate_ad(self, inp: DigestionInputs, r: DigestionResult) -> DigestionResult:
        """Anaerobic digestion calculation chain."""

        vs_dest = inp.vs_destruction_pct / 100.0 if inp.vs_destruction_pct > 1 else inp.vs_destruction_pct
        r.vs_destruction_pct = vs_dest * 100.0

        # ── Step 1: VS destruction ─────────────────────────────────────────
        r.vs_destroyed_t_yr = inp.feed_vs_t_yr * vs_dest
        r.digested_ds_t_yr  = inp.feed_ds_t_yr - r.vs_destroyed_t_yr

        # FIXED: Update VS/DS ratio after digestion
        digested_vs_t_yr = inp.feed_vs_t_yr - r.vs_destroyed_t_yr
        r.digested_vs_fraction = (
            digested_vs_t_yr / r.digested_ds_t_yr if r.digested_ds_t_yr > 0 else 0.60
        )
        r.note(
            f"Post-digestion VS/DS = {r.digested_vs_fraction:.2f} "
            f"(was {inp.feed_vs_t_yr/inp.feed_ds_t_yr:.2f} in feed)"
        )

        # Validate VS destruction range
        if vs_dest < 0.45 or vs_dest > 0.75:
            r.warn(
                f"VS destruction of {vs_dest*100:.0f}% is outside the expected screening range "
                f"(45–75%). Mesophilic AD: 50–60%. Thermophilic: 55–70%. THP+AD: 60–70%."
            )

        # ── Step 2: Biogas production ──────────────────────────────────────
        vs_destroyed_kg_yr = r.vs_destroyed_t_yr * 1000.0
        biogas_m3_yr = vs_destroyed_kg_yr * inp.biogas_yield_m3_per_kg_vs_destroyed

        r.biogas.biogas_m3_yr      = biogas_m3_yr
        r.biogas.ch4_m3_yr         = biogas_m3_yr * inp.biogas_ch4_fraction
        r.biogas.co2_m3_yr         = biogas_m3_yr * inp.biogas_co2_fraction
        r.biogas.ch4_kg_yr         = r.biogas.ch4_m3_yr * CH4_DENSITY_KG_M3
        r.biogas.ch4_energy_mj_yr  = r.biogas.ch4_m3_yr * CH4_ENERGY_DENSITY_MJ_M3
        r.biogas.ch4_energy_kwh_yr = r.biogas.ch4_energy_mj_yr / 3.6

        spec_biogas = biogas_m3_yr / (inp.feed_ds_t_yr * 1000) if inp.feed_ds_t_yr > 0 else 0
        r.note(
            f"Biogas: {biogas_m3_yr/1000:.0f}k m³/yr | "
            f"CH₄: {r.biogas.ch4_m3_yr/1000:.0f}k m³/yr | "
            f"Specific: {spec_biogas:.2f} m³/kg DS fed"
        )
        if spec_biogas > 0.50:
            r.warn(
                f"Specific biogas yield ({spec_biogas:.2f} m³/kg DS) is high for municipal sludge. "
                "Expected 0.25–0.45. Check if FOG co-digestion applies."
            )

        # ── Step 3: FIXED methane pathway allocation ───────────────────────
        mp = r.methane_pathways
        mp.ch4_generated_m3_yr = r.biogas.ch4_m3_yr

        # Fugitive losses at cover/collection boundary (fraction of GENERATED)
        mp.ch4_cover_fugitive_m3_yr    = mp.ch4_generated_m3_yr * inp.cover_fugitive_fraction
        mp.ch4_handling_fugitive_m3_yr = mp.ch4_generated_m3_yr * inp.handling_fugitive_fraction

        # Gas available for collection after fugitive losses
        ch4_available_for_collection = (
            mp.ch4_generated_m3_yr -
            mp.ch4_cover_fugitive_m3_yr -
            mp.ch4_handling_fugitive_m3_yr
        )

        # Capture efficiency loss within the collection/utilisation system
        ch4_collected = ch4_available_for_collection * inp.methane_capture_efficiency
        mp.ch4_uncollected_m3_yr = ch4_available_for_collection * (1.0 - inp.methane_capture_efficiency)
        # Uncollected gas inside the system boundary = Scope 1 at GWP28

        # Of collected gas: flare fraction vs CHP
        mp.ch4_to_flare_m3_yr = ch4_collected * inp.flare_fraction
        mp.ch4_to_chp_m3_yr   = ch4_collected * (1.0 - inp.flare_fraction)

        # Storage CH4 (from digested sludge in holding tanks)
        if inp.storage_included:
            mp.ch4_storage_m3_yr = mp.ch4_generated_m3_yr * inp.storage_ch4_fraction
        else:
            mp.ch4_storage_m3_yr = 0.0

        # All Scope 1 (non-combusted) CH4 combined
        mp.ch4_total_fugitive_m3_yr = (
            mp.ch4_cover_fugitive_m3_yr +
            mp.ch4_handling_fugitive_m3_yr +
            mp.ch4_uncollected_m3_yr +
            mp.ch4_storage_m3_yr
        )
        mp.ch4_total_fugitive_kg_yr = mp.ch4_total_fugitive_m3_yr * CH4_DENSITY_KG_M3

        # Mass balance check
        total_accounted = (
            mp.ch4_to_chp_m3_yr + mp.ch4_to_flare_m3_yr +
            mp.ch4_total_fugitive_m3_yr
        )
        # Note: storage CH4 comes from digested sludge organics, technically additional
        # to the primary digester gas stream. Mass balance check excludes storage.
        total_primary = (
            mp.ch4_to_chp_m3_yr + mp.ch4_to_flare_m3_yr +
            mp.ch4_cover_fugitive_m3_yr + mp.ch4_handling_fugitive_m3_yr +
            mp.ch4_uncollected_m3_yr
        )
        mp.mass_balance_discrepancy_pct = abs(
            (total_primary - mp.ch4_generated_m3_yr) / max(mp.ch4_generated_m3_yr, 1.0)
        ) * 100.0

        # Scope 1 GHG from all fugitive sources
        r.fugitive_ch4_tco2e_yr = mp.ch4_total_fugitive_kg_yr * CH4_GWP_100 / 1000.0
        r.storage_ch4_tco2e_yr  = mp.ch4_storage_m3_yr * CH4_DENSITY_KG_M3 * CH4_GWP_100 / 1000.0

        r.note(
            f"CH₄ pathways: CHP {mp.ch4_to_chp_m3_yr/1000:.1f}k | "
            f"Flare {mp.ch4_to_flare_m3_yr/1000:.1f}k | "
            f"All Scope 1 fugitive {mp.ch4_total_fugitive_m3_yr/1000:.1f}k m³/yr | "
            f"Balance error {mp.mass_balance_discrepancy_pct:.2f}%"
        )

        # ── Step 4: FIXED digester heating (first-principles heat balance) ─
        er = r.energy_recovery
        # Feed sludge heating: Q = ṁ × Cp × ΔT
        # Sludge ≈ water thermally (high water content)
        # Feed wet mass (t/yr) from DS and TS%
        feed_ts_pct = 5.0   # Thickened sludge feed TS% (from SludgeModel)
        feed_wet_t_yr = inp.feed_ds_t_yr / (feed_ts_pct / 100.0) if feed_ts_pct > 0 else inp.feed_ds_t_yr * 20
        feed_wet_kg_yr = feed_wet_t_yr * 1000.0

        delta_T = inp.digester_temp_celsius - inp.feed_temp_celsius
        heat_sludge_kj_yr = feed_wet_kg_yr * WATER_SPECIFIC_HEAT_KJ_KG_K * delta_T
        heat_with_losses_kj_yr = heat_sludge_kj_yr * inp.heat_loss_factor
        er.digester_heat_demand_kwh_yr = heat_with_losses_kj_yr / KJ_PER_KWH

        r.note(
            f"Digester heat demand: ΔT = {delta_T:.0f}°C | "
            f"Feed wet: {feed_wet_t_yr:.0f} t/yr | "
            f"Heat: {er.digester_heat_demand_kwh_yr/1000:.0f} MWh/yr"
        )

        # ── Step 5: CHP energy recovery ────────────────────────────────────
        if inp.chp_enabled and mp.ch4_to_chp_m3_yr > 0:
            chp_energy_mj_yr = mp.ch4_to_chp_m3_yr * CH4_ENERGY_DENSITY_MJ_M3
            er.electricity_kwh_yr = chp_energy_mj_yr * inp.chp_electrical_efficiency / 3.6
            er.heat_kwh_yr        = chp_energy_mj_yr * inp.chp_thermal_efficiency / 3.6

            # Use CHP heat to offset digester heating demand first
            er.heat_used_for_digester_kwh_yr = min(er.heat_kwh_yr, er.digester_heat_demand_kwh_yr)
            er.digester_heat_deficit_kwh_yr  = max(
                0.0, er.digester_heat_demand_kwh_yr - er.heat_used_for_digester_kwh_yr
            )

            er.electricity_kw_avg = er.electricity_kwh_yr / 8760.0
            er.chp_capacity_kw    = er.electricity_kw_avg * 1.15

            # NOTE: Avoided grid credit is NOT applied here.
            # It is applied in WholePlantCarbon.aggregate_whole_plant() to avoid double-counting.
            # We store it here for reference only.
            er.avoided_grid_co2e_t_yr = (
                er.electricity_kwh_yr * inp.grid_emission_factor_kg_co2e_per_kwh / 1000.0
            )

            if er.digester_heat_deficit_kwh_yr > 0:
                r.note(
                    f"CHP heat ({er.heat_kwh_yr/1000:.0f} MWh/yr) covers "
                    f"{er.heat_used_for_digester_kwh_yr/1000:.0f} MWh/yr of digester demand. "
                    f"Deficit: {er.digester_heat_deficit_kwh_yr/1000:.0f} MWh/yr "
                    f"(supplemental gas boiler or heat exchanger required)"
                )
            else:
                r.note(
                    f"CHP heat surplus: {(er.heat_kwh_yr - er.digester_heat_demand_kwh_yr)/1000:.0f} MWh/yr "
                    f"available for other uses after meeting digester heating demand."
                )

        # ── Step 6: Reject water (centrate) characterisation ──────────────
        # Digestion releases organic-N as NH4 into the liquid phase
        # Approximately 70% of feed TKN ends up in the centrate
        # (Metcalf & Eddy Table 10-14: 60-80% of TKN in centrate)
        feed_tkn_kg_yr = inp.feed_ds_t_yr * 1000 * inp.feed_tkn_fraction
        reject_nh4_kg_yr = feed_tkn_kg_yr * 0.70
        # Centrate volume: typically 15-25% of feed sludge volume
        # Approximate centrate flow from wet sludge (thickened at 5% TS)
        centrate_m3_yr = feed_wet_t_yr * 0.18   # 18% of feed volume as centrate
        centrate_conc  = (reject_nh4_kg_yr * 1000) / centrate_m3_yr if centrate_m3_yr > 0 else 0

        r.reject_water = RejectWaterResult(
            nh4_kg_day  = reject_nh4_kg_yr / 365.0,
            flow_m3_day = centrate_m3_yr / 365.0,
            concentration_mg_l = centrate_conc,
        )
        r.note(
            f"Reject water (centrate): {r.reject_water.nh4_kg_day:.1f} kg NH₄-N/day | "
            f"{r.reject_water.flow_m3_day:.0f} m³/day @ "
            f"{centrate_conc:.0f} mg/L NH₄-N"
        )
        r.warn(
            f"⚠ Reject water returns {r.reject_water.nh4_kg_day:.1f} kg NH₄-N/day to the liquid "
            f"treatment line — this increases aeration demand and N₂O emissions on the liquid side."
        )

        return r

    def _calculate_lime(self, inp: DigestionInputs, r: DigestionResult) -> DigestionResult:
        """
        Lime stabilisation pathway.
        No biogas production. Scope 1 = zero (no CH4). Scope 3 = lime upstream.
        VS destruction: ~15-20% (compared to 55-65% for AD).
        """
        r.note("Lime stabilisation selected — no biogas or methane produced.")

        # Lime dose: typically 0.25-0.40 kg CaO per kg DS to achieve Class B
        lime_dose_kg_per_kg_ds = 0.30
        r.lime_kg_yr = inp.feed_ds_t_yr * 1000 * lime_dose_kg_per_kg_ds

        # Lime upstream Scope 3: ~0.78 kg CO2e/kg CaO (calcination)
        r.lime_upstream_tco2e_yr = r.lime_kg_yr * 0.78 / 1000.0

        # Partial VS stabilisation from pH elevation (not true destruction)
        r.vs_destroyed_t_yr = inp.feed_vs_t_yr * 0.15
        r.vs_destruction_pct = 15.0
        r.digested_ds_t_yr  = inp.feed_ds_t_yr + r.lime_kg_yr / 1000.0  # Lime adds mass
        r.digested_vs_fraction = (
            (inp.feed_vs_t_yr - r.vs_destroyed_t_yr) / r.digested_ds_t_yr
            if r.digested_ds_t_yr > 0 else 0.70
        )

        r.note(
            f"Lime: {r.lime_kg_yr/1000:.0f} t CaO/yr | "
            f"Scope 3: {r.lime_upstream_tco2e_yr:.1f} tCO₂e/yr | "
            f"No biogas — N₂O from land application is lower than raw sludge."
        )
        return r

    @staticmethod
    def _echo_inputs(inp: DigestionInputs) -> Dict[str, Any]:
        return {
            "digestion_type":                    inp.digestion_type,
            "feed_ds_t_yr":                      inp.feed_ds_t_yr,
            "feed_vs_t_yr":                      inp.feed_vs_t_yr,
            "vs_destruction_pct":                inp.vs_destruction_pct,
            "biogas_yield_m3_per_kg_vs":         inp.biogas_yield_m3_per_kg_vs_destroyed,
            "biogas_ch4_fraction":               inp.biogas_ch4_fraction,
            "methane_capture_efficiency":        inp.methane_capture_efficiency,
            "cover_fugitive_fraction":           inp.cover_fugitive_fraction,
            "handling_fugitive_fraction":        inp.handling_fugitive_fraction,
            "storage_ch4_fraction":              inp.storage_ch4_fraction,
            "flare_fraction":                    inp.flare_fraction,
            "chp_electrical_efficiency":         inp.chp_electrical_efficiency,
            "chp_thermal_efficiency":            inp.chp_thermal_efficiency,
            "digester_temp_celsius":             inp.digester_temp_celsius,
            "feed_temp_celsius":                 inp.feed_temp_celsius,
            "grid_emission_factor":              inp.grid_emission_factor_kg_co2e_per_kwh,
        }
