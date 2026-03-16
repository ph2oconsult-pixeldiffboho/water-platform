"""
domains/wastewater/biosolids_carbon_model.py

Biosolids Carbon Footprint Model (v1.1)
=========================================
AUDIT FIXES:
  - CRITICAL: Removed CHP avoided credit from solids-line result.
    The CHP electricity credit now belongs ONLY in WholePlantCarbon
    to prevent double-counting against the liquid-line Scope 2.
  - SIGNIFICANT: Separate digested vs undigested biosolids N content
  - SIGNIFICANT: N2O emission factor differentiated by biosolids class
  - SIGNIFICANT: Post-digestion VS/DS ratio used for landfill CH4
  - SIGNIFICANT: Thickening energy added as Scope 2
  - SIGNIFICANT: Composting process N2O emissions added
  - SIGNIFICANT: Incineration N2O separated from biogenic CO2
  - MINOR: Polymer EF corrected from 3.80 → 2.5 kg CO2e/kg

References
----------
  - IPCC (2019) — Refinement Vol.5 Waste, Ch.6 Wastewater treatment
  - Australian NGER Technical Guidelines (2023) — Biosolids
  - Yoshida et al. (2015) — N2O emissions from biosolids land application
  - US EPA (2016) — GHG Emission Factors Hub
  - Ecoinvent 3.9 — Polyacrylamide upstream emissions
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional

from domains.wastewater.sludge_model import SludgeMassBalance
from domains.wastewater.digestion_model import DigestionResult

N2O_GWP_100  = 273.0
CH4_GWP_100  = 28.0
DIESEL_EF    = 2.68      # kg CO2e/litre diesel
TRUCK_L_100KM = 35.0     # Litres/100km (heavy rigid truck)


@dataclass
class BiosolidsCarbonInputs:
    """
    User-configurable emission factors for the biosolids carbon model.
    NOTE: CHP electricity credit has been removed from this class.
    It is now applied only in WholePlantCarbon.aggregate_whole_plant().
    """

    # ── Land application N2O ─────────────────────────────────────────────
    # FIXED: Differentiated by biosolids class and application method
    biosolids_class: str = "class_b"
    # class_a | class_b | raw_undigested
    # N2O emission factors (kg N2O-N per kg N applied):
    n2o_ef_class_a: float = 0.005        # Class A granular/pelletised: lower volatilisation
    n2o_ef_class_b_incorporated: float = 0.008   # NGER: 0.8%
    n2o_ef_class_b_surface: float = 0.010        # IPCC Tier 1 default: 1.0%
    n2o_ef_raw_undigested: float = 0.015         # Higher for unstabilised material

    land_application_method: str = "incorporated"  # incorporated | surface

    # N content of biosolids (fraction of DS)
    # FIXED: Differentiated by digestion status
    digested_biosolids_n_fraction: float = 0.035     # Digested: lower (N lost as NH4 in reject)
    undigested_biosolids_n_fraction: float = 0.055   # Raw/undigested WAS

    # ── Landfill CH4 ─────────────────────────────────────────────────────
    # FIXED: Use digested VS fraction (lower after VS destruction)
    landfill_ch4_kg_per_t_vs_landfilled: float = 20.0
    landfill_ch4_capture_efficiency: float = 0.50

    # ── Composting process emissions (NEW) ───────────────────────────────
    composting_n2o_kg_per_kg_n_composted: float = 0.015  # Windrow: 0.5-3%; in-vessel: 0.3-0.5%
    composting_ch4_kg_per_t_wet_composted: float = 1.5   # Windrow composting CH4 kg/t wet

    # ── Thermal pathway emissions (FIXED) ────────────────────────────────
    # Incineration: N2O is the counted emission (biogenic CO2 = zero net)
    # N2O from sludge incineration: ~0.3-0.8 kg N2O/t DS
    incineration_n2o_kg_per_t_ds: float = 0.5     # → 137 kg CO2e/t DS at GWP273
    incineration_fossil_co2_kg_per_t_ds: float = 10.0  # Plastics/lubricants in sludge (fossil)
    # Pyrolysis: lower N2O due to lower combustion temperature
    pyrolysis_n2o_kg_per_t_ds: float = 0.05
    pyrolysis_fossil_co2_kg_per_t_ds: float = 5.0
    gasification_n2o_kg_per_t_ds: float = 0.08
    gasification_fossil_co2_kg_per_t_ds: float = 8.0

    # ── Pyrolysis biochar sequestration ──────────────────────────────────
    biochar_included: bool = False
    biochar_yield_kg_per_kg_ds: float = 0.35
    biochar_carbon_fraction: float = 0.70
    biochar_stability_factor: float = 0.80

    # ── Thickening electricity (NEW) ─────────────────────────────────────
    thickening_type: str = "gravity"
    # gravity = 0; gravity_belt_thickener = 20; daf_thickening = 65 kWh/t DS
    thickening_kwh_per_t_ds: Dict[str, float] = field(default_factory=lambda: {
        "gravity":              0.0,
        "gravity_belt_thickener": 20.0,
        "daf_thickening":       65.0,
        "centrifuge_thickening": 55.0,
    })

    # ── Dewatering electricity ────────────────────────────────────────────
    centrifuge_kwh_per_t_ds: float = 60.0
    belt_press_kwh_per_t_ds: float = 20.0
    screw_press_kwh_per_t_ds: float = 30.0

    # ── Digester supplemental heating ────────────────────────────────────
    # If CHP heat does not cover digester demand, additional gas is required
    gas_boiler_efficiency: float = 0.90      # Gas boiler efficiency for supplemental heat
    gas_emission_factor_kg_co2e_per_kwh: float = 0.20  # Natural gas: ~0.20 kg CO2e/kWh thermal

    # ── Polymer ──────────────────────────────────────────────────────────
    polymer_ef_kg_co2e_per_kg: float = 2.5
    # FIXED: corrected from 3.80 → 2.5 (Ecoinvent 3.9 polyacrylamide)

    # ── Grid and transport ────────────────────────────────────────────────
    grid_emission_factor_kg_co2e_per_kwh: float = 0.79

    # ── Enable/disable flags ──────────────────────────────────────────────
    include_land_application_n2o: bool = True
    include_landfill_ch4: bool = True
    include_thermal_process_emissions: bool = True
    include_thickening_electricity: bool = True
    include_dewatering_electricity: bool = True
    include_polymer_upstream: bool = True
    include_transport_emissions: bool = True
    include_composting_emissions: bool = True
    include_biochar_credit: bool = False
    include_supplemental_heat_emissions: bool = True


@dataclass
class BiosolidsCarbonResult:
    """
    Complete biosolids carbon footprint.
    NOTE: CHP electricity avoided credit is NOT included here.
    It belongs only in WholePlantCarbon to prevent double-counting.
    """
    # Scope 1
    s1_fugitive_ch4_digester_tco2e_yr: float = 0.0
    s1_land_application_n2o_tco2e_yr: float = 0.0
    s1_landfill_ch4_tco2e_yr: float = 0.0
    s1_thermal_process_tco2e_yr: float = 0.0
    s1_composting_tco2e_yr: float = 0.0
    total_scope1_tco2e_yr: float = 0.0

    # Scope 2
    s2_thickening_electricity_tco2e_yr: float = 0.0
    s2_dewatering_electricity_tco2e_yr: float = 0.0
    s2_dewatering_kwh_yr: float = 0.0
    s2_thickening_kwh_yr: float = 0.0
    s2_supplemental_heat_tco2e_yr: float = 0.0
    total_scope2_tco2e_yr: float = 0.0

    # Scope 3
    s3_polymer_upstream_tco2e_yr: float = 0.0
    s3_transport_tco2e_yr: float = 0.0
    s3_lime_upstream_tco2e_yr: float = 0.0
    total_scope3_tco2e_yr: float = 0.0

    # Total gross
    total_gross_tco2e_yr: float = 0.0

    # Avoided (solids-line only — NOT CHP electricity, which is in WholePlantCarbon)
    avoided_biochar_sequestration_tco2e_yr: float = 0.0
    total_avoided_tco2e_yr: float = 0.0

    # Net
    net_tco2e_yr: float = 0.0

    # 30-year
    lifecycle_years: int = 30
    gross_tco2e_30yr: float = 0.0
    net_tco2e_30yr: float = 0.0

    # Intensities
    kg_co2e_per_t_ds_gross: float = 0.0
    kg_co2e_per_t_ds_net: float = 0.0

    # Reference: CHP avoided credit (for display only — applied in WholePlantCarbon)
    chp_electricity_credit_reference_tco2e_yr: float = 0.0

    emission_source_breakdown: Dict[str, float] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def note(self, s: str) -> None: self.notes.append(s)
    def warn(self, s: str) -> None: self.warnings.append(s)

    def to_summary_dict(self) -> Dict[str, Any]:
        return {
            "S1: Digester fugitive CH₄ (tCO₂e/yr)":    round(self.s1_fugitive_ch4_digester_tco2e_yr, 1),
            "S1: Land application N₂O (tCO₂e/yr)":     round(self.s1_land_application_n2o_tco2e_yr, 1),
            "S1: Landfill CH₄ (tCO₂e/yr)":             round(self.s1_landfill_ch4_tco2e_yr, 1),
            "S1: Composting (tCO₂e/yr)":               round(self.s1_composting_tco2e_yr, 1),
            "S1: Thermal process (tCO₂e/yr)":          round(self.s1_thermal_process_tco2e_yr, 1),
            "S2: Thickening electricity (tCO₂e/yr)":   round(self.s2_thickening_electricity_tco2e_yr, 1),
            "S2: Dewatering electricity (tCO₂e/yr)":   round(self.s2_dewatering_electricity_tco2e_yr, 1),
            "S2: Supplemental heat (tCO₂e/yr)":        round(self.s2_supplemental_heat_tco2e_yr, 1),
            "S3: Polymer upstream (tCO₂e/yr)":         round(self.s3_polymer_upstream_tco2e_yr, 1),
            "S3: Transport (tCO₂e/yr)":                round(self.s3_transport_tco2e_yr, 1),
            "Gross emissions (tCO₂e/yr)":              round(self.total_gross_tco2e_yr, 1),
            "Avoided (solids-line only) (tCO₂e/yr)":   round(self.total_avoided_tco2e_yr, 1),
            "Net emissions (tCO₂e/yr)":                round(self.net_tco2e_yr, 1),
            "NOTE – CHP credit applied in whole-plant": round(self.chp_electricity_credit_reference_tco2e_yr, 1),
        }


class BiosolidsCarbonModel:

    def calculate(
        self,
        inp: BiosolidsCarbonInputs,
        sludge: SludgeMassBalance,
        digestion: DigestionResult,
    ) -> BiosolidsCarbonResult:
        r = BiosolidsCarbonResult()
        breakdown: Dict[str, float] = {}

        # Determine if sludge is digested for property selection
        is_digested = sludge.digestion_included

        # ── Scope 1 ────────────────────────────────────────────────────────

        # 1a. Fugitive CH4 from digester (all sources, from DigestionModel)
        r.s1_fugitive_ch4_digester_tco2e_yr = digestion.fugitive_ch4_tco2e_yr
        breakdown["Digester fugitive CH₄"] = r.s1_fugitive_ch4_digester_tco2e_yr

        # 1b. Land application N2O (FIXED: class and method differentiated)
        if inp.include_land_application_n2o and sludge.disposal_pathway == "land_application":
            n_fraction = (inp.digested_biosolids_n_fraction if is_digested
                          else inp.undigested_biosolids_n_fraction)
            n_applied_kg_yr = sludge.cake_ds_t_yr * 1000 * n_fraction

            # Select N2O EF by class and application method
            if inp.biosolids_class == "class_a":
                n2o_ef = inp.n2o_ef_class_a
            elif inp.biosolids_class == "class_b" and inp.land_application_method == "incorporated":
                n2o_ef = inp.n2o_ef_class_b_incorporated
            elif inp.biosolids_class == "class_b":
                n2o_ef = inp.n2o_ef_class_b_surface
            else:
                n2o_ef = inp.n2o_ef_raw_undigested

            n2o_n_kg_yr = n_applied_kg_yr * n2o_ef
            n2o_kg_yr   = n2o_n_kg_yr * (44.0 / 28.0)
            r.s1_land_application_n2o_tco2e_yr = n2o_kg_yr * N2O_GWP_100 / 1000.0
            r.note(
                f"Land application N₂O ({inp.biosolids_class}, {inp.land_application_method}): "
                f"EF={n2o_ef*100:.1f}% | N applied: {n_applied_kg_yr:.0f} kg/yr | "
                f"{r.s1_land_application_n2o_tco2e_yr:.1f} tCO₂e/yr"
            )
            r.warn(
                "⚠ Land application N₂O is highly uncertain (±50%). "
                "Site-specific factors (soil type, climate, application rate) dominate. "
                "N₂O EF range: 0.005–0.02 kg N₂O-N/kg N applied."
            )
            breakdown["Land application N₂O"] = r.s1_land_application_n2o_tco2e_yr

        # 1c. Landfill residual CH4 — FIXED: use digested VS/DS
        if inp.include_landfill_ch4 and sludge.disposal_pathway == "landfill":
            digested_vs_frac = (getattr(digestion, "digested_vs_fraction", None)
                                or (sludge.digested_vs_t_yr / sludge.digested_ds_t_yr
                                    if sludge.digested_ds_t_yr > 0 else 0.65))
            vs_in_cake_t_yr = sludge.disposal_quantity_t_ds_yr * digested_vs_frac
            ch4_generated_kg_yr = vs_in_cake_t_yr * inp.landfill_ch4_kg_per_t_vs_landfilled
            ch4_escaped_kg_yr   = ch4_generated_kg_yr * (1.0 - inp.landfill_ch4_capture_efficiency)
            r.s1_landfill_ch4_tco2e_yr = ch4_escaped_kg_yr * CH4_GWP_100 / 1000.0
            r.note(
                f"Landfill: VS in cake {vs_in_cake_t_yr:.0f} t VS/yr (VS/DS={digested_vs_frac:.2f}) | "
                f"escaped CH₄ {ch4_escaped_kg_yr:.0f} kg/yr | "
                f"{r.s1_landfill_ch4_tco2e_yr:.1f} tCO₂e/yr"
            )
            breakdown["Landfill CH₄"] = r.s1_landfill_ch4_tco2e_yr

        # 1d. Composting process emissions (NEW)
        if inp.include_composting_emissions and sludge.disposal_pathway == "composting":
            n_fraction_compost = (inp.digested_biosolids_n_fraction if is_digested
                                  else inp.undigested_biosolids_n_fraction)
            n_composted_kg_yr = sludge.cake_ds_t_yr * 1000 * n_fraction_compost
            n2o_compost_kg_yr = n_composted_kg_yr * inp.composting_n2o_kg_per_kg_n_composted * (44/28)
            compost_n2o_tco2e = n2o_compost_kg_yr * N2O_GWP_100 / 1000.0
            ch4_compost_kg_yr = sludge.cake_wet_t_yr * inp.composting_ch4_kg_per_t_wet_composted
            compost_ch4_tco2e = ch4_compost_kg_yr * CH4_GWP_100 / 1000.0
            r.s1_composting_tco2e_yr = compost_n2o_tco2e + compost_ch4_tco2e
            r.note(
                f"Composting: N₂O {compost_n2o_tco2e:.1f} + CH₄ {compost_ch4_tco2e:.1f} = "
                f"{r.s1_composting_tco2e_yr:.1f} tCO₂e/yr"
            )
            breakdown["Composting N₂O+CH₄"] = r.s1_composting_tco2e_yr

        # 1e. Thermal pathway emissions (FIXED: N2O + fossil CO2 only, no biogenic CO2)
        if inp.include_thermal_process_emissions and sludge.disposal_pathway in (
            "incineration", "pyrolysis", "gasification"
        ):
            pathway = sludge.disposal_pathway
            n2o_ef_map = {
                "incineration": inp.incineration_n2o_kg_per_t_ds,
                "pyrolysis":    inp.pyrolysis_n2o_kg_per_t_ds,
                "gasification": inp.gasification_n2o_kg_per_t_ds,
            }
            fossil_ef_map = {
                "incineration": inp.incineration_fossil_co2_kg_per_t_ds,
                "pyrolysis":    inp.pyrolysis_fossil_co2_kg_per_t_ds,
                "gasification": inp.gasification_fossil_co2_kg_per_t_ds,
            }
            n2o_kg = sludge.disposal_quantity_t_ds_yr * n2o_ef_map[pathway]
            n2o_tco2e = n2o_kg * N2O_GWP_100 / 1000.0
            fossil_tco2e = sludge.disposal_quantity_t_ds_yr * fossil_ef_map[pathway] / 1000.0
            r.s1_thermal_process_tco2e_yr = n2o_tco2e + fossil_tco2e
            r.note(
                f"Thermal ({pathway}): N₂O {n2o_tco2e:.1f} + fossil CO₂ {fossil_tco2e:.1f} = "
                f"{r.s1_thermal_process_tco2e_yr:.1f} tCO₂e/yr "
                f"(biogenic CO₂ from VS combustion excluded — not a counted emission)"
            )
            breakdown["Thermal process"] = r.s1_thermal_process_tco2e_yr

        r.total_scope1_tco2e_yr = (
            r.s1_fugitive_ch4_digester_tco2e_yr + r.s1_land_application_n2o_tco2e_yr +
            r.s1_landfill_ch4_tco2e_yr + r.s1_thermal_process_tco2e_yr +
            r.s1_composting_tco2e_yr
        )

        # ── Scope 2 ────────────────────────────────────────────────────────

        # 2a. Thickening electricity (NEW)
        if inp.include_thickening_electricity:
            kwh_per_t = inp.thickening_kwh_per_t_ds.get(inp.thickening_type, 0.0)
            r.s2_thickening_kwh_yr = sludge.total_raw_ds_t_yr * kwh_per_t
            r.s2_thickening_electricity_tco2e_yr = (
                r.s2_thickening_kwh_yr * inp.grid_emission_factor_kg_co2e_per_kwh / 1000.0
            )
            if r.s2_thickening_kwh_yr > 0:
                breakdown["Thickening electricity"] = r.s2_thickening_electricity_tco2e_yr

        # 2b. Dewatering electricity
        if inp.include_dewatering_electricity:
            kwh_t = {"centrifuge": inp.centrifuge_kwh_per_t_ds,
                     "belt_press": inp.belt_press_kwh_per_t_ds,
                     "screw_press": inp.screw_press_kwh_per_t_ds}
            kwh_per_t_ds = kwh_t.get(sludge.dewatering_type, inp.centrifuge_kwh_per_t_ds)
            r.s2_dewatering_kwh_yr = sludge.cake_ds_t_yr * kwh_per_t_ds
            r.s2_dewatering_electricity_tco2e_yr = (
                r.s2_dewatering_kwh_yr * inp.grid_emission_factor_kg_co2e_per_kwh / 1000.0
            )
            breakdown["Dewatering electricity"] = r.s2_dewatering_electricity_tco2e_yr

        # 2c. Supplemental digester heating (gas boiler for CHP heat deficit)
        if inp.include_supplemental_heat_emissions:
            heat_deficit = getattr(digestion.energy_recovery, "digester_heat_deficit_kwh_yr", 0.0)
            if heat_deficit > 0:
                gas_kwh_consumed = heat_deficit / inp.gas_boiler_efficiency
                r.s2_supplemental_heat_tco2e_yr = (
                    gas_kwh_consumed * inp.gas_emission_factor_kg_co2e_per_kwh / 1000.0
                )
                r.note(
                    f"Supplemental heating: {heat_deficit/1000:.0f} MWh/yr heat deficit | "
                    f"{r.s2_supplemental_heat_tco2e_yr:.1f} tCO₂e/yr (natural gas)"
                )
                breakdown["Supplemental digester heat"] = r.s2_supplemental_heat_tco2e_yr

        r.total_scope2_tco2e_yr = (
            r.s2_thickening_electricity_tco2e_yr +
            r.s2_dewatering_electricity_tco2e_yr +
            r.s2_supplemental_heat_tco2e_yr
        )

        # ── Scope 3 ────────────────────────────────────────────────────────

        if inp.include_polymer_upstream:
            r.s3_polymer_upstream_tco2e_yr = (
                sludge.polymer_kg_yr * inp.polymer_ef_kg_co2e_per_kg / 1000.0
            )
            breakdown["Polymer upstream"] = r.s3_polymer_upstream_tco2e_yr

        if inp.include_transport_emissions:
            total_km = sludge.truck_trips_per_year * sludge.transport_distance_km * 2
            litres = total_km * TRUCK_L_100KM / 100.0
            r.s3_transport_tco2e_yr = litres * DIESEL_EF / 1000.0
            breakdown["Transport (diesel)"] = r.s3_transport_tco2e_yr

        # Lime upstream (from lime stabilisation)
        if digestion.lime_upstream_tco2e_yr > 0:
            r.s3_lime_upstream_tco2e_yr = digestion.lime_upstream_tco2e_yr
            breakdown["Lime upstream"] = r.s3_lime_upstream_tco2e_yr

        r.total_scope3_tco2e_yr = (
            r.s3_polymer_upstream_tco2e_yr +
            r.s3_transport_tco2e_yr +
            r.s3_lime_upstream_tco2e_yr
        )

        # ── Gross total ────────────────────────────────────────────────────
        r.total_gross_tco2e_yr = (
            r.total_scope1_tco2e_yr +
            r.total_scope2_tco2e_yr +
            r.total_scope3_tco2e_yr
        )

        # ── Avoided (solids-line only) ─────────────────────────────────────
        if inp.include_biochar_credit and sludge.disposal_pathway == "pyrolysis":
            biochar_t_yr = sludge.disposal_quantity_t_ds_yr * inp.biochar_yield_kg_per_kg_ds
            c_seq = biochar_t_yr * inp.biochar_carbon_fraction * inp.biochar_stability_factor
            r.avoided_biochar_sequestration_tco2e_yr = c_seq * (44.0 / 12.0)
            breakdown["Avoided: Biochar sequestration"] = -r.avoided_biochar_sequestration_tco2e_yr

        r.total_avoided_tco2e_yr = r.avoided_biochar_sequestration_tco2e_yr

        # ── Net ────────────────────────────────────────────────────────────
        r.net_tco2e_yr = r.total_gross_tco2e_yr - r.total_avoided_tco2e_yr

        # Store CHP credit for reference display ONLY — not applied to net
        r.chp_electricity_credit_reference_tco2e_yr = digestion.energy_recovery.avoided_grid_co2e_t_yr

        # ── Lifecycle ─────────────────────────────────────────────────────
        r.gross_tco2e_30yr = r.total_gross_tco2e_yr * r.lifecycle_years
        r.net_tco2e_30yr   = r.net_tco2e_yr * r.lifecycle_years

        # ── Intensities ───────────────────────────────────────────────────
        # Intensity on RAW DS input basis (standard for sludge treatment GHG reporting)
        # Using cake DS (post-digestion) would falsely inflate intensity as VS is destroyed
        raw_ds = sludge.total_raw_ds_t_yr if sludge.total_raw_ds_t_yr > 0 else sludge.cake_ds_t_yr
        if raw_ds > 0:
            r.kg_co2e_per_t_ds_gross = r.total_gross_tco2e_yr * 1000 / raw_ds
            r.kg_co2e_per_t_ds_net   = r.net_tco2e_yr * 1000 / raw_ds

        r.emission_source_breakdown = {k: round(v, 2) for k, v in breakdown.items()}

        r.note(
            f"Biosolids carbon: gross {r.total_gross_tco2e_yr:.0f} | "
            f"avoided (solids only) {r.total_avoided_tco2e_yr:.0f} | "
            f"net {r.net_tco2e_yr:.0f} tCO₂e/yr | "
            f"intensity {r.kg_co2e_per_t_ds_gross:.0f} kg CO₂e/t DS gross"
        )
        r.note(
            f"CHP electricity credit of {r.chp_electricity_credit_reference_tco2e_yr:.0f} tCO₂e/yr "
            f"is applied in the Whole-Plant carbon calculation, NOT here, "
            f"to prevent double-counting with the liquid-line Scope 2."
        )

        return r
