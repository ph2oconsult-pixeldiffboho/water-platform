"""
domains/wastewater/technologies/solids/thermal_biosolids.py

Thermal Biosolids Treatment Module
=====================================
Covers three thermal treatment routes for biosolids:

  1. Incineration (mono-incineration / co-incineration)
  2. Pyrolysis (low/mid-temperature, produces biochar)
  3. Gasification (high-temperature, syngas + slag)

Each route eliminates or significantly reduces the need for biosolids
land application, destroys PFAS at adequate operating conditions, and
produces an ash/char/slag residual requiring further management.

Key differences
---------------
Incineration  : >850°C, high O2 — complete oxidation, ash residual (~25% DS)
                PFAS destruction: >99% at >850°C / 2s (EPA Aus 2023)
                Energy: net consumer (moisture-dependent)
                Scope 1: N2O from combustion, fossil CO2 (plastics fraction)
                Biogenic CO2: NOT counted (GHG Protocol, NGER)

Pyrolysis     : 400–700°C, O2-free — biochar + pyrolysis oil + syngas
                PFAS destruction: 50–90% temperature-dependent
                Energy: potentially net zero to net positive at high temp
                Scope 1: trace N2O, fossil CH4 in syngas

Gasification  : 700–1100°C, partial O2 — syngas + slag
                PFAS destruction: 75–95%
                Energy: syngas CHP potential

Design basis
------------
Feed: dewatered biosolids cake (15–30% TS)
Throughput: t DS/year
Key sizing parameter: thermal input = wet cake mass × calorific value

References
----------
- USEPA (2023) — Thermal Treatment of PFAS in Wastewater and Biosolids
- NSW EPA (2023) — PFAS in Biosolids — Interim Guidance
- WEF (2012) — Biosolids Management MOP 36, Chapter 15
- Fonts et al. (2012) — Sewage sludge pyrolysis for liquid production, Fuel
- Rulkens (2008) — Sewage sludge as a biomass resource, Energy & Fuels
- Atkins & de Paula (2014) — Physical Chemistry — combustion thermodynamics
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
class ThermalBiosolidsInputs:
    """
    Design parameters for thermal biosolids treatment.

    Feed is characterised at the cake inlet (post-dewatering).
    """
    # ── Treatment route ────────────────────────────────────────────────────
    route: str = "incineration"
    # "incineration" | "pyrolysis" | "gasification"

    # ── Feed characterisation ──────────────────────────────────────────────
    feed_ts_pct: float = 22.0
    # Dewatered cake TS% (typical centrifuge: 18–25%)

    feed_vs_fraction: float = 0.62
    # VS/DS ratio of dewatered cake (digested: 0.55–0.65, undigested: 0.75–0.85)

    feed_kgds_day: float = 1500.0
    # Input dry solids (kg DS/day). For sizing only — set from biosolids model.

    # ── Operating conditions ───────────────────────────────────────────────
    operating_temperature_celsius: float = 900.0
    # Design combustion / pyrolysis / gasification temperature
    # Incineration: 850–1000°C  |  Pyrolysis: 400–700°C  |  Gasification: 700–1100°C

    residence_time_seconds: float = 2.5
    # Gas residence time at operating temperature
    # PFAS destruction: minimum 2.0 s at >850°C (EPA Aus 2023)

    # ── Energy recovery ────────────────────────────────────────────────────
    energy_recovery_enabled: bool = True
    # True: heat/syngas recovery for electricity/heat production

    chp_electrical_efficiency: float = 0.35
    # For syngas CHP (gasification/pyrolysis) or steam turbine (incineration)

    # ── Pyrolysis / gasification char ─────────────────────────────────────
    biochar_yield_fraction: float = 0.35
    # Fraction of input DS that becomes char (pyrolysis): typical 0.25–0.45

    # ── Residual management ────────────────────────────────────────────────
    ash_to_landfill: bool = True
    # True: ash/slag disposed to engineered landfill

    ash_pfas_characterisation_required: bool = True
    # PFAS testing of ash/char required before disposal

    # ── Auxiliary systems ──────────────────────────────────────────────────
    scrubber_enabled: bool = True
    # Wet scrubber for flue gas / syngas treatment

    # ── PFAS context ──────────────────────────────────────────────────────
    pfas_sum_ug_kg_feed: float = 500.0
    # ∑PFAS in feed cake (µg/kg DS) — affects residual PFAS in ash/char

    # ── Field bounds ──────────────────────────────────────────────────────
    _field_bounds: dict = field(default_factory=lambda: {
        "feed_ts_pct":               (12.0, 40.0),
        "feed_vs_fraction":          (0.40, 0.90),
        "operating_temperature_celsius": (400.0, 1200.0),
        "residence_time_seconds":    (0.5, 10.0),
        "chp_electrical_efficiency": (0.25, 0.45),
    }, repr=False)


# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTS (engineering defaults with source citations)
# ─────────────────────────────────────────────────────────────────────────────

# Calorific values (MJ/kg DS)
# Biosolids HHV ~11–16 MJ/kg VS; LHV used for energy calcs
CV_VS_MJ_KG_LHV = 13.0    # Lower heating value of VS fraction (Rulkens 2008)
CV_MOISTURE_PENALTY_MJ_KG = 2.5  # Energy penalty per 10% moisture above 20% TS

# Ash yield fractions (kg ash / kg DS input)
ASH_YIELD = {
    "incineration": 0.25,   # ~25% ash (fixed inorganic fraction)
    "pyrolysis":    0.35,   # Char yield at ~600°C (Fonts et al. 2012)
    "gasification": 0.20,   # Slag/char at >800°C
}

# PFAS destruction efficiencies (fraction destroyed) — temperature-dependent
# References: US EPA 2023, NSW EPA 2023, Crimi et al. 2022
def pfas_destruction_efficiency(route: str, T_celsius: float, residence_s: float) -> float:
    if route == "incineration":
        if T_celsius >= 850 and residence_s >= 2.0:
            return 0.99    # >99% at EPA-recommended conditions
        elif T_celsius >= 700:
            return 0.90
        else:
            return 0.60
    elif route == "gasification":
        return min(0.95, 0.60 + (T_celsius - 700) / 1000)
    elif route == "pyrolysis":
        if T_celsius >= 700:
            return 0.85
        elif T_celsius >= 500:
            return 0.55
        else:
            return 0.30
    return 0.0

# N2O emission factors for thermal processes (kg N2O / t DS)
# Biosolids incineration N2O: 0.3–0.8 kg/t DS (biogenic CO2 excluded)
N2O_INCINERATION_KG_PER_T_DS = 0.50   # (IPCC 2019 Refinement Vol.5)
N2O_PYROLYSIS_KG_PER_T_DS    = 0.05   # Much lower in O2-depleted environment
N2O_GASIFICATION_KG_PER_T_DS = 0.08

# Fossil CO2: small fraction from plastics/lubricants in sludge
FOSSIL_CO2_KG_PER_T_DS = 10.0    # ~1% of total carbon is fossil (IPCC 2019)

N2O_GWP_100 = 273.0   # AR6


# ─────────────────────────────────────────────────────────────────────────────
# TECHNOLOGY CLASS
# ─────────────────────────────────────────────────────────────────────────────

class ThermalBiosolidsTechnology(BaseTechnology):
    """
    Thermal biosolids treatment pathway module.

    Covers incineration, pyrolysis, and gasification.
    Designed as a solids-side module — it does not process liquid streams.

    The design_flow_mld parameter is used only for energy intensity
    per ML treated (normalised metric). The primary sizing basis is
    feed_kgds_day.
    """

    @property
    def technology_code(self) -> str:
        return "thermal_biosolids"

    @property
    def technology_name(self) -> str:
        return "Thermal Biosolids Treatment"

    @property
    def technology_category(self) -> str:
        return "solids"

    @property
    def requires_upstream(self):
        return ["bnr", "mbr", "granular_sludge", "anmbr"]  # Needs a solids source

    @classmethod
    def input_class(cls) -> Type:
        return ThermalBiosolidsInputs

    # ─────────────────────────────────────────────────────────────────────
    # CALCULATE
    # ─────────────────────────────────────────────────────────────────────

    def calculate(
        self,
        design_flow_mld: float,
        inputs: ThermalBiosolidsInputs,
    ) -> TechnologyResult:
        r = TechnologyResult(
            technology_name=f"Thermal Biosolids — {inputs.route.title()}",
            technology_code=self.technology_code,
            technology_category="Solids / Thermal",
            description=f"Thermal {inputs.route} of dewatered biosolids with ash/char residual management.",
        )

        route = inputs.route.lower()
        if route not in ("incineration", "pyrolysis", "gasification"):
            r.note(f"⚠ Unknown route '{route}' — defaulting to incineration.")
            route = "incineration"

        # ── 1. Feed characterisation ──────────────────────────────────────
        feed_ds_t_yr   = inputs.feed_kgds_day * 365 / 1000.0
        feed_ts_frac   = inputs.feed_ts_pct / 100.0
        feed_wet_t_yr  = feed_ds_t_yr / feed_ts_frac
        feed_wet_kg_day = inputs.feed_kgds_day / feed_ts_frac

        vs_kg_day = inputs.feed_kgds_day * inputs.feed_vs_fraction

        r.note(
            f"Feed: {inputs.feed_kgds_day:.0f} kg DS/day "
            f"({feed_wet_kg_day:.0f} kg wet/day at {inputs.feed_ts_pct:.0f}% TS) | "
            f"VS fraction: {inputs.feed_vs_fraction:.2f} | "
            f"Route: {route}"
        )
        r.notes.add_assumption(
            f"Feed: {inputs.feed_kgds_day:.0f} kg DS/day at {inputs.feed_ts_pct:.0f}% TS, "
            f"VS fraction {inputs.feed_vs_fraction:.2f}. Route: {route}."
        )
        r.notes.add_assumption(
            f"Operating temperature: {inputs.operating_temperature_celsius:.0f}°C, "
            f"residence time: {inputs.residence_time_seconds:.1f} s. "
            f"PFAS destruction efficiency per EPA Aus 2023 conditions."
        )

        # ── 2. Calorific value and energy balance ─────────────────────────
        # LHV of cake (MJ/kg wet) — accounts for moisture evaporation penalty
        # Higher moisture = more energy to evaporate = lower net energy
        moisture_pct = 100.0 - inputs.feed_ts_pct
        cv_wet_mj_kg = (
            CV_VS_MJ_KG_LHV * inputs.feed_vs_fraction * feed_ts_frac
            - CV_MOISTURE_PENALTY_MJ_KG * (moisture_pct / 10.0)
        )
        cv_wet_mj_kg = max(cv_wet_mj_kg, 0.5)  # Minimum for stable combustion

        thermal_input_mj_day = feed_wet_kg_day * cv_wet_mj_kg
        thermal_input_kwh_day = thermal_input_mj_day / 3.6

        r.note(
            f"Calorific value: {cv_wet_mj_kg:.1f} MJ/kg wet "
            f"(moisture {moisture_pct:.0f}%) | "
            f"Thermal input: {thermal_input_kwh_day:,.0f} kWh/day"
        )

        # Supplemental fuel needed if cv_wet < 5 MJ/kg (wet cake too moist)
        MINIMUM_SELF_SUSTAINING_CV = 5.0   # MJ/kg wet — rule of thumb
        supplemental_fuel_required = cv_wet_mj_kg < MINIMUM_SELF_SUSTAINING_CV
        if supplemental_fuel_required:
            r.note(
                f"⚠ Cake CV ({cv_wet_mj_kg:.1f} MJ/kg wet) is below self-sustaining "
                f"threshold ({MINIMUM_SELF_SUSTAINING_CV} MJ/kg). "
                "Supplemental fuel or pre-drying will be required. "
                "Increase dewatering TS to >20% to improve."
            )

        # Energy recovery estimate
        electrical_generation_kwh_day = 0.0
        if inputs.energy_recovery_enabled:
            # Gross electrical generation from CHP on recovered heat/syngas
            # Incineration: steam from heat recovery → turbine (~15% electrical eff)
            # Pyrolysis/gasification: syngas → CHP (30–40% electrical eff)
            recovery_eff = {
                "incineration": 0.15,
                "pyrolysis":    inputs.chp_electrical_efficiency,
                "gasification": inputs.chp_electrical_efficiency,
            }[route]
            electrical_generation_kwh_day = thermal_input_kwh_day * recovery_eff
            r.note(
                f"Energy recovery: {recovery_eff*100:.0f}% electrical efficiency → "
                f"{electrical_generation_kwh_day:,.0f} kWh/day generated"
            )

        # Auxiliary power demand (fans, pumps, scrubber, instrumentation)
        auxiliary_factor = {
            "incineration": 0.12,   # 12% of thermal input as auxiliary
            "pyrolysis":    0.08,
            "gasification": 0.10,
        }[route]
        auxiliary_kwh_day = thermal_input_kwh_day * auxiliary_factor
        scrubber_kwh_day = thermal_input_kwh_day * 0.03 if inputs.scrubber_enabled else 0.0

        r.energy.other_kwh_day   = round(auxiliary_kwh_day + scrubber_kwh_day, 1)
        r.energy.generation_kwh_day = round(electrical_generation_kwh_day, 1)
        r.energy.biogas_m3_day = 0.0   # Discrete syngas — not reported as biogas

        # ── 3. Residual solids (ash / char / slag) ────────────────────────
        ash_yield = ASH_YIELD[route]
        ash_t_yr  = feed_ds_t_yr * ash_yield

        # No biological sludge — this is a solids-processing-only module
        r.sludge.biological_sludge_kgds_day = 0.0
        r.sludge.chemical_sludge_kgds_day   = inputs.feed_kgds_day * ash_yield
        r.sludge.vs_fraction                 = 0.05   # Ash is almost entirely inorganic

        r.note(
            f"Residual {route} ash/char: {ash_t_yr:.0f} t DS/yr "
            f"({ash_yield*100:.0f}% of feed DS). "
            "Must be characterised for PFAS and metals before disposal."
        )

        # ── 4. PFAS fate ──────────────────────────────────────────────────
        pfas_dest_eff = pfas_destruction_efficiency(
            route, inputs.operating_temperature_celsius, inputs.residence_time_seconds
        )
        pfas_remaining_ug_kg_ash = (
            inputs.pfas_sum_ug_kg_feed
            * (1.0 - pfas_dest_eff)
            / ash_yield  # Concentrates in smaller ash mass
        )

        r.note(
            f"PFAS: feed {inputs.pfas_sum_ug_kg_feed:,.0f} µg/kg DS | "
            f"Destruction {pfas_dest_eff*100:.0f}% at {inputs.operating_temperature_celsius:.0f}°C / "
            f"{inputs.residence_time_seconds:.1f}s | "
            f"Residual in ash: {pfas_remaining_ug_kg_ash:,.0f} µg/kg DS"
        )
        if pfas_dest_eff < 0.99:
            r.note(
                f"⚠ PFAS destruction < 99% at these operating conditions. "
                f"For {route}: recommend T > 850°C and residence time > 2s "
                f"to achieve EPA-recommended >99% destruction."
            )

        r.performance.additional.update({
            "route":                              route,
            "operating_temperature_celsius":      inputs.operating_temperature_celsius,
            "feed_ds_t_yr":                       round(feed_ds_t_yr, 0),
            "feed_wet_t_yr":                      round(feed_wet_t_yr, 0),
            "ash_t_yr":                           round(ash_t_yr, 0),
            "ash_yield_fraction":                 ash_yield,
            "cv_wet_mj_kg":                       round(cv_wet_mj_kg, 2),
            "pfas_destruction_efficiency":        pfas_dest_eff,
            "pfas_residual_ash_ug_kg":            round(pfas_remaining_ug_kg_ash, 0),
            "supplemental_fuel_required":         supplemental_fuel_required,
            "electrical_generation_kwh_day":      round(electrical_generation_kwh_day, 0),
        })

        # ── 5. Scope 1 emissions ──────────────────────────────────────────
        n2o_ef_map = {
            "incineration": N2O_INCINERATION_KG_PER_T_DS,
            "pyrolysis":    N2O_PYROLYSIS_KG_PER_T_DS,
            "gasification": N2O_GASIFICATION_KG_PER_T_DS,
        }
        n2o_kg_yr = feed_ds_t_yr * n2o_ef_map[route]
        r.carbon.other_scope1_tco2e_yr = round(n2o_kg_yr * N2O_GWP_100 / 1000.0, 1)

        # Fossil CO2 from plastics/lubricants fraction
        # Biogenic CO2 from VS combustion is NOT counted (GHG Protocol, NGER)
        fossil_co2_t_yr = feed_ds_t_yr * FOSSIL_CO2_KG_PER_T_DS / 1000.0
        r.carbon.process_co2_tco2e_yr = round(fossil_co2_t_yr, 2)

        r.note(
            f"Scope 1: N2O {r.carbon.other_scope1_tco2e_yr:.1f} tCO2e/yr + "
            f"fossil CO2 {r.carbon.process_co2_tco2e_yr:.1f} tCO2e/yr. "
            "Biogenic CO2 from VS combustion excluded (not a counted emission)."
        )

        # ── 6. Risk flags ─────────────────────────────────────────────────
        r.risk.reliability_risk       = "Moderate"   # Moving parts, high T
        r.risk.regulatory_risk        = (
            "Low" if pfas_dest_eff >= 0.99 else "Moderate"
        )
        r.risk.technology_maturity    = {
            "incineration": "Established",
            "pyrolysis":    "Emerging",
            "gasification": "Emerging",
        }[route]
        r.risk.operational_complexity = "High"       # High-temperature process
        r.risk.site_constraint_risk   = "High"       # Air permit, buffer distances

        r.risk.additional_flags["pfas_destruction_risk"] = (
            "Low" if pfas_dest_eff >= 0.99 else
            "Moderate" if pfas_dest_eff >= 0.90 else "High"
        )
        r.risk.additional_flags["ash_disposal_risk"] = (
            "Moderate" if pfas_remaining_ug_kg_ash > 100 else "Low"
        )
        r.risk.additional_flags["supplemental_fuel_risk"] = (
            "High" if supplemental_fuel_required else "Low"
        )
        r.risk.additional_flags["air_emission_permit_risk"] = "Moderate"

        # ── 7. CAPEX ──────────────────────────────────────────────────────
        # Sizing basis: peak throughput = feed_wet_t_yr × load_factor / 8760
        # Using t wet/hr as the size metric (standard for thermal plant sizing)
        peak_wet_t_hr = (feed_wet_t_yr * 1.25) / (8760 * 0.85)  # 25% peak, 85% availability

        r.capex_items = [
            CostItem(
                name=f"Thermal treatment unit ({route})",
                cost_basis_key=f"thermal_biosolids_{route}_per_kwh_thermal",
                quantity=thermal_input_kwh_day,
                unit="kWh/day thermal input",
                notes=f"{inputs.operating_temperature_celsius:.0f}°C operating temperature",
            ),
            CostItem(
                name="Feed handling & dewatering connection",
                cost_basis_key="biosolids_feed_handling_per_t_ds_yr",
                quantity=feed_ds_t_yr,
                unit="t DS/yr",
            ),
        ]
        if inputs.scrubber_enabled:
            r.capex_items.append(CostItem(
                name="Flue gas / syngas scrubbing system",
                cost_basis_key="scrubber_per_kwh_thermal",
                quantity=thermal_input_kwh_day,
                unit="kWh/day thermal input",
                notes="Wet scrubber for acid gas, PFAS, and particulate removal",
            ))
        if inputs.energy_recovery_enabled:
            r.capex_items.append(CostItem(
                name="Energy recovery system (heat exchanger / CHP)",
                cost_basis_key="thermal_recovery_per_kw_electrical",
                quantity=electrical_generation_kwh_day / 24.0,
                unit="kW electrical",
            ))

        # ── 8. OPEX ───────────────────────────────────────────────────────
        r.opex_items = [
            CostItem(
                name="Electricity — auxiliary systems",
                cost_basis_key="electricity_per_kwh",
                quantity=auxiliary_kwh_day + scrubber_kwh_day,
                unit="kWh/day",
            ),
            CostItem(
                name="Ash / char disposal to landfill",
                cost_basis_key="ash_disposal_per_tonne",
                quantity=ash_t_yr / 365.0,
                unit="t/day",
                notes="PFAS-characterised ash to engineered landfill",
            ),
            CostItem(
                name="Maintenance — thermal equipment",
                cost_basis_key="thermal_maintenance_per_t_ds_yr",
                quantity=feed_ds_t_yr,
                unit="t DS/yr",
            ),
        ]
        if supplemental_fuel_required:
            r.opex_items.append(CostItem(
                name="Supplemental fuel (natural gas)",
                cost_basis_key="natural_gas_per_kwh",
                quantity=thermal_input_kwh_day * 0.10,  # Estimate 10% supplemental
                unit="kWh/day",
                notes="Required when cake CV < 5 MJ/kg wet",
            ))

        # ── 9. Assumptions log ────────────────────────────────────────────
        r.assumptions_used = {
            "route":                          route,
            "feed_ts_pct":                    inputs.feed_ts_pct,
            "feed_vs_fraction":               inputs.feed_vs_fraction,
            "operating_temperature_celsius":  inputs.operating_temperature_celsius,
            "residence_time_seconds":         inputs.residence_time_seconds,
            "ash_yield_fraction":             ash_yield,
            "cv_wet_mj_kg":                   round(cv_wet_mj_kg, 2),
            "pfas_destruction_efficiency":    pfas_dest_eff,
            "n2o_ef_kg_per_t_ds":            n2o_ef_map[route],
            "fossil_co2_kg_per_t_ds":         FOSSIL_CO2_KG_PER_T_DS,
            "chp_electrical_efficiency":      inputs.chp_electrical_efficiency,
        }

        # ── 10. Finalise ──────────────────────────────────────────────────
        return r.finalise(design_flow_mld)
