"""
domains/wastewater/aeration_model.py

Aeration Engineering Model
===========================
Standalone, reusable module for concept-stage aeration system design.
Called by the domain interface, Streamlit pages, and sensitivity analysis.

All equations are documented with references.  No Streamlit imports — pure
engineering Python so the module can be used in isolation for testing.

Calculation chain
-----------------
  1. Influent loads  (kg/d)
  2. Oxygen demand   (kg O₂/d) — BOD removal + nitrification − denitrification credit
  3. Standard O₂ transfer rate (SOTR, kg O₂/h)
  4. Actual O₂ transfer rate   (AOTR, kg O₂/h) via alpha/beta/SOTE corrections
  5. Required airflow (Nm³/h)
  6. Blower power (kW) via adiabatic compression formula
  7. Energy intensity metrics  (kWh/ML, kWh/kg NH₄-N)
  8. Blower configuration check (duty/standby)
  9. Energy guarantee metric   (kWh/kg NH₄-N at peak conditions)

References
----------
  - Metcalf & Eddy, Wastewater Engineering 5th ed. (2014) — Chapters 5, 7, 10
  - WEF MOP 8, Design of Municipal WWTP
  - ASCE Standard 2-06, Measurement of O₂ Transfer in Clean Water
  - Tchobanoglous et al. (2014) — Oxygen transfer and aeration energy
  - Henkel (2010) — O₂ transfer and blower sizing in activated sludge
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
import math


# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────

OXYGEN_DENSITY_KG_NM3     = 1.331   # kg O₂ per Nm³ of pure oxygen at 0°C, 101.325 kPa
AIR_OXYGEN_FRACTION       = 0.2095  # Volume fraction of O₂ in dry air
AIR_DENSITY_KG_NM3        = 1.293   # kg/Nm³ dry air at 0°C, 101.325 kPa
GAMMA_AIR                 = 1.4     # Ratio of specific heats for air (Cp/Cv)
R_AIR_J_KG_K              = 287.0   # Specific gas constant for air (J/kg·K)
STD_TEMP_K                = 273.15  # Standard temperature (K) = 0°C
O2_SOLUBILITY_20C_MG_L    = 9.09    # DO saturation in clean water at 20°C, 1 atm (mg/L)
# Temperature correction base for O₂ transfer (Arrhenius, θ = 1.024)
THETA_O2_TRANSFER         = 1.024


# ─────────────────────────────────────────────────────────────────────────────
# INPUT DATACLASSES
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class AerationInputs:
    """
    All parameters required to run the aeration model.
    Populated from plant inputs, technology parameters, and assumptions.
    """

    # ── Process loads ──────────────────────────────────────────────────────
    design_flow_mld: float = 10.0          # Average dry weather flow (ML/d)
    peak_flow_factor: float = 2.5          # Peak flow / average flow ratio
    influent_bod_mg_l: float = 250.0       # Influent BOD (mg/L)
    influent_nh4_mg_l: float = 35.0        # Influent NH₄-N (mg/L)
    influent_tkn_mg_l: float = 45.0        # Influent TKN (mg/L)

    # Target removals
    bod_removal_efficiency: float = 0.95   # Fraction of BOD removed (0–1)
    nh4_removal_efficiency: float = 0.95   # Fraction of NH₄-N removed (0–1)
    # Denitrification as fraction of nitrified N returned to N₂
    denitrification_fraction: float = 0.50

    # ── Oxygen transfer parameters ─────────────────────────────────────────
    # Standard aeration efficiency: kg O₂/kWh in clean water (fine bubble diffusers)
    # Typical range: 1.6–2.4 kg O₂/kWh (fine bubble); 0.9–1.2 (coarse bubble)
    standard_aeration_efficiency_kg_o2_kwh: float = 2.0

    # Alpha factor: process water O₂ transfer / clean water O₂ transfer
    # Accounts for surfactants, MLSS, and diffuser fouling
    # Typical: 0.45–0.65 for municipal WW with fine bubble diffusers
    alpha_factor: float = 0.55

    # Beta factor: process water O₂ saturation / clean water O₂ saturation
    # Accounts for dissolved solids and contaminants
    # Typical: 0.95–0.99 for municipal wastewater
    beta_factor: float = 0.97

    # Fouling factor for diffuser systems (F)
    # New diffusers: 0.90–1.00; aged diffusers: 0.65–0.80
    fouling_factor: float = 0.90

    # Standard O₂ transfer efficiency (SOTE) — fraction of O₂ transferred per pass
    # Fine bubble: 0.20–0.35; Coarse bubble: 0.06–0.12
    # Increases ~0.4%/m submergence for fine bubble
    sote_per_metre_submergence: float = 0.049  # SOTE per metre of diffuser submergence
    # 4.9%/m → 22% at 4.5m depth (fine bubble ceramic disc, Mueller et al. 2002)
    # Typical range: 3–6%/m for fine bubble; 1–2%/m for coarse bubble

    # ── Diffuser and tank geometry ─────────────────────────────────────────
    diffuser_submergence_m: float = 4.5    # Depth of diffusers below water surface (m)
    # Oxygen demand safety factor (peak to average)
    peak_to_average_o2_factor: float = 1.4  # Ratio of peak to average O₂ demand

    # ── Blower parameters ──────────────────────────────────────────────────
    blower_efficiency: float = 0.70        # Isentropic efficiency of blower (0–1)
    motor_efficiency: float = 0.95         # Motor/transmission efficiency (0–1)
    vsd_efficiency: float = 0.97           # VSD (variable speed drive) efficiency (0–1)
    system_pressure_loss_kpa: float = 15.0 # Duct/pipework pressure loss (kPa)
    inlet_temperature_celsius: float = 20.0
    inlet_pressure_kpa: float = 101.325    # Atmospheric pressure at inlet (kPa)

    # ── Blower configuration ───────────────────────────────────────────────
    num_duty_blowers: int = 2
    num_standby_blowers: int = 1
    blower_motor_kw: Optional[float] = None  # If None, sized automatically

    # ── Technology O₂ override ─────────────────────────────────────────────
    o2_demand_override_kg_day: Optional[float] = None
    # If set, bypasses the internal O₂ demand calculation and uses this value
    # directly. Used by the aeration page to carry over O₂ demand from the
    # technology module (which accounts for technology-specific yields,
    # denitrification fractions, and SND credits).

    # ── NH₄:TKN ratio (used if TKN not supplied) ─────────────────────────
    nh4_to_tkn_ratio: float = 0.75         # Typical: 0.70–0.80 for domestic WW


# ─────────────────────────────────────────────────────────────────────────────
# OUTPUT DATACLASSES
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class LoadResult:
    """Influent loading calculations."""
    design_flow_mld: float = 0.0
    peak_flow_mld: float = 0.0
    bod_load_kg_day: float = 0.0
    nh4_load_kg_day: float = 0.0
    tkn_load_kg_day: float = 0.0
    bod_removed_kg_day: float = 0.0
    nh4_removed_kg_day: float = 0.0
    tkn_removed_kg_day: float = 0.0
    # Peak loads
    peak_bod_load_kg_day: float = 0.0
    peak_nh4_load_kg_day: float = 0.0


@dataclass
class OxygenDemandResult:
    """Oxygen demand breakdown."""
    # Average conditions
    o2_bod_kg_day: float = 0.0           # O₂ for BOD removal (kg O₂/d)
    o2_nitrification_kg_day: float = 0.0 # O₂ for nitrification (kg O₂/d)
    o2_denitrification_credit_kg_day: float = 0.0  # O₂ credit from denitrification
    o2_total_avg_kg_day: float = 0.0     # Total average O₂ demand (kg O₂/d)
    # Peak conditions (for blower sizing)
    o2_total_peak_kg_day: float = 0.0    # Total peak O₂ demand (kg O₂/d)
    o2_avg_kg_hr: float = 0.0            # Average O₂ demand rate (kg O₂/h)
    o2_peak_kg_hr: float = 0.0           # Peak O₂ demand rate (kg O₂/h)


@dataclass
class TransferResult:
    """
    Oxygen transfer calculations — converts SOTR to AOTR.

    SOTR (Standard O₂ Transfer Rate): O₂ transferred in clean water
          at 20°C, 0 mg/L DO, 1 atm.  Used for blower sizing.

    AOTR (Actual O₂ Transfer Rate): O₂ transferred under actual process
          conditions.  Used to confirm delivery meets demand.

    Relationship (Metcalf & Eddy Eq. 5-58):
        AOTR = SOTR × α × F × (β·Cs_T - C_L) / (Cs_20) × θ^(T-20)

    Where:
        α   = alpha factor (process/clean water transfer ratio)
        F   = fouling factor
        β   = beta factor (process/clean water saturation ratio)
        Cs_T = O₂ saturation at operating temperature (mg/L)
        C_L  = operating DO concentration (mg/L)
        Cs_20 = O₂ saturation in clean water at 20°C (mg/L)
        θ   = Arrhenius temperature correction (1.024)
        T   = operating temperature (°C)
    """
    sote: float = 0.0                    # Standard O₂ transfer efficiency (fraction)
    sotr_kg_hr: float = 0.0             # Standard O₂ transfer rate (kg O₂/h)
    aotr_kg_hr: float = 0.0             # Actual O₂ transfer rate (kg O₂/h)
    aote: float = 0.0                   # Actual O₂ transfer efficiency (fraction)
    correction_factor: float = 0.0      # Combined α·F·(β·Cs-CL)/Cs_20·θ^(T-20)
    do_deficit_correction: float = 0.0  # (β·Cs_T - C_L) / Cs_20
    temperature_correction: float = 0.0 # θ^(T-20)


@dataclass
class AirflowResult:
    """Required airflow calculations."""
    avg_airflow_nm3_hr: float = 0.0     # Average airflow (Nm³/h)
    peak_airflow_nm3_hr: float = 0.0    # Peak airflow for blower sizing (Nm³/h)
    avg_airflow_nm3_min: float = 0.0    # Average airflow (Nm³/min)
    peak_airflow_nm3_min: float = 0.0   # Peak airflow (Nm³/min)
    # Specific airflow
    airflow_per_m3_reactor: Optional[float] = None  # Nm³/h per m³ reactor volume
    sair_ratio: float = 0.0             # Specific air rate (Nm³ air / m³ wastewater)


@dataclass
class BlowerResult:
    """
    Blower sizing and power calculations.

    Uses the adiabatic compression formula (Metcalf & Eddy Eq. 5-74):

        P_shaft = (w × R × T₁) / (n × η_b) × [(P₂/P₁)^((n-1)/n) - 1]

    Where:
        w    = mass flow rate of air (kg/s)
        R    = specific gas constant for air (287 J/kg·K)
        T₁   = inlet absolute temperature (K)
        n    = (γ-1)/γ = 0.283 for air (γ = Cp/Cv = 1.4)
        η_b  = blower isentropic efficiency (0–1)
        P₂   = discharge absolute pressure (kPa)
        P₁   = inlet absolute pressure (kPa)
    """
    # Pressure
    inlet_pressure_kpa: float = 0.0
    discharge_pressure_kpa: float = 0.0
    pressure_ratio: float = 0.0

    # Per-blower at average and peak
    avg_power_per_blower_kw: float = 0.0
    peak_power_per_blower_kw: float = 0.0

    # Total installed blower power
    total_duty_power_avg_kw: float = 0.0
    total_duty_power_peak_kw: float = 0.0
    total_installed_power_kw: float = 0.0  # Including standby

    # Blower motor sizing
    recommended_motor_kw: float = 0.0
    num_duty: int = 0
    num_standby: int = 0
    configuration_description: str = ""

    # Configuration check
    configuration_adequate: bool = True
    configuration_warning: str = ""

    # Annual energy
    annual_aeration_energy_kwh: float = 0.0
    annual_aeration_energy_mwh: float = 0.0


@dataclass
class EnergyIntensityResult:
    """Energy intensity benchmarking metrics."""
    kwh_per_ml_treated: float = 0.0          # kWh / ML treated
    kwh_per_kg_nh4_removed: float = 0.0      # kWh / kg NH₄-N removed
    kwh_per_kg_bod_removed: float = 0.0      # kWh / kg BOD removed
    kwh_per_kg_o2_transferred: float = 0.0   # kWh / kg O₂ (overall aeration efficiency)
    # Energy guarantee metric (at peak conditions)
    kwh_per_kg_nh4_peak: float = 0.0         # Energy guarantee at peak ammonia load
    # Benchmark comparison
    benchmark_kwh_per_ml: Dict[str, float] = field(default_factory=lambda: {
        "excellent": 200,    # Top performers
        "good":      400,    # Typical efficient plants
        "average":   600,    # Industry average
        "poor":      900,    # Inefficient plants
    })
    performance_band: str = ""               # excellent / good / average / poor


@dataclass
class AerationModelResult:
    """Complete result from the aeration model."""
    # Component results
    loads: LoadResult = field(default_factory=LoadResult)
    oxygen_demand: OxygenDemandResult = field(default_factory=OxygenDemandResult)
    transfer: TransferResult = field(default_factory=TransferResult)
    airflow: AirflowResult = field(default_factory=AirflowResult)
    blower: BlowerResult = field(default_factory=BlowerResult)
    energy_intensity: EnergyIntensityResult = field(default_factory=EnergyIntensityResult)

    # Input echo for transparency
    inputs_used: Dict[str, Any] = field(default_factory=dict)

    # Calculation notes (engineering transparency)
    notes: List[str] = field(default_factory=list)

    # Sensitivity analysis results (populated separately)
    sensitivity: Optional[Dict[str, Any]] = None

    def note(self, msg: str) -> None:
        self.notes.append(msg)

    def to_summary_dict(self) -> Dict[str, Any]:
        """Flat dict for display tables and comparison pages."""
        return {
            "BOD Load (kg/d)":              round(self.loads.bod_load_kg_day, 0),
            "NH₄ Load (kg/d)":              round(self.loads.nh4_load_kg_day, 0),
            "TKN Load (kg/d)":              round(self.loads.tkn_load_kg_day, 0),
            "Avg O₂ Demand (kg/d)":         round(self.oxygen_demand.o2_total_avg_kg_day, 0),
            "Peak O₂ Demand (kg/d)":        round(self.oxygen_demand.o2_total_peak_kg_day, 0),
            "SOTE (%)":                     round(self.transfer.sote * 100, 1),
            "Avg Airflow (Nm³/h)":          round(self.airflow.avg_airflow_nm3_hr, 0),
            "Peak Airflow (Nm³/h)":         round(self.airflow.peak_airflow_nm3_hr, 0),
            "Avg Blower Power (kW)":        round(self.blower.total_duty_power_avg_kw, 1),
            "Peak Blower Power (kW)":       round(self.blower.total_duty_power_peak_kw, 1),
            "Installed Power (kW)":         round(self.blower.total_installed_power_kw, 1),
            "Annual Aeration Energy (MWh)": round(self.blower.annual_aeration_energy_mwh, 0),
            "kWh/ML Treated":               round(self.energy_intensity.kwh_per_ml_treated, 0),
            "kWh/kg NH₄-N Removed":         round(self.energy_intensity.kwh_per_kg_nh4_removed, 2),
            "kWh/kg BOD Removed":           round(self.energy_intensity.kwh_per_kg_bod_removed, 3),
            "Energy Guarantee (kWh/kg NH₄)": round(self.energy_intensity.kwh_per_kg_nh4_peak, 2),
            "Performance Band":             self.energy_intensity.performance_band,
            "Blower Config":                self.blower.configuration_description,
            "Config Adequate":              self.blower.configuration_adequate,
        }


# ─────────────────────────────────────────────────────────────────────────────
# AERATION MODEL — MAIN CALCULATOR
# ─────────────────────────────────────────────────────────────────────────────

class AerationModel:
    """
    Aeration engineering model for concept-stage design.

    Usage
    -----
    >>> model = AerationModel()
    >>> inputs = AerationInputs(design_flow_mld=10.0, influent_nh4_mg_l=35.0)
    >>> result = model.calculate(inputs)
    >>> print(result.blower.total_duty_power_avg_kw)
    """

    def calculate(self, inputs: AerationInputs) -> AerationModelResult:
        """
        Run the full aeration calculation chain.
        Returns an AerationModelResult with all intermediate and final outputs.
        """
        result = AerationModelResult()
        result.inputs_used = self._echo_inputs(inputs)

        # Ensure TKN is set (derive from NH₄ if needed)
        if inputs.influent_tkn_mg_l <= inputs.influent_nh4_mg_l:
            tkn = inputs.influent_nh4_mg_l / inputs.nh4_to_tkn_ratio
            result.note(
                f"TKN derived from NH₄-N using ratio {inputs.nh4_to_tkn_ratio}: "
                f"TKN = {inputs.influent_nh4_mg_l:.1f} / {inputs.nh4_to_tkn_ratio} = {tkn:.1f} mg/L"
            )
        else:
            tkn = inputs.influent_tkn_mg_l

        # Step 1 — Influent loads
        result.loads = self._calculate_loads(inputs, tkn)
        result.note(
            f"BOD load: {result.loads.bod_load_kg_day:.0f} kg/d  |  "
            f"NH₄ load: {result.loads.nh4_load_kg_day:.0f} kg/d  |  "
            f"TKN load: {result.loads.tkn_load_kg_day:.0f} kg/d"
        )

        # Step 2 — Oxygen demand
        result.oxygen_demand = self._calculate_oxygen_demand(inputs, result.loads)
        result.note(
            f"O₂ demand: BOD {result.oxygen_demand.o2_bod_kg_day:.0f} + "
            f"Nitrification {result.oxygen_demand.o2_nitrification_kg_day:.0f} - "
            f"Denitrification credit {result.oxygen_demand.o2_denitrification_credit_kg_day:.0f} = "
            f"{result.oxygen_demand.o2_total_avg_kg_day:.0f} kg O₂/d (avg)"
        )
        result.note(f"Peak O₂ demand: {result.oxygen_demand.o2_total_peak_kg_day:.0f} kg O₂/d "
                    f"(factor {inputs.peak_to_average_o2_factor})")

        # Step 3 — O₂ transfer (SOTR → AOTR correction)
        result.transfer = self._calculate_transfer(inputs)
        result.note(
            f"SOTE: {result.transfer.sote*100:.1f}%  |  "
            f"Correction factor (α·F·ΔCs/Cs20·θᵀ): {result.transfer.correction_factor:.3f}  |  "
            f"AOTR/SOTR ratio: {result.transfer.correction_factor:.3f}"
        )

        # Step 4 — Airflow
        result.airflow = self._calculate_airflow(inputs, result.oxygen_demand, result.transfer)
        result.note(
            f"Required airflow: avg {result.airflow.avg_airflow_nm3_hr:.0f} Nm³/h | "
            f"peak {result.airflow.peak_airflow_nm3_hr:.0f} Nm³/h"
        )

        # Step 5 — Blower sizing
        result.blower = self._calculate_blower(inputs, result.airflow)
        result.note(
            f"Blower: {result.blower.configuration_description} | "
            f"avg {result.blower.total_duty_power_avg_kw:.1f} kW | "
            f"peak {result.blower.total_duty_power_peak_kw:.1f} kW"
        )
        if not result.blower.configuration_adequate:
            result.note(f"⚠️ WARNING: {result.blower.configuration_warning}")

        # Step 6 — Energy intensity
        result.energy_intensity = self._calculate_energy_intensity(inputs, result.loads, result.blower)
        result.note(
            f"Energy: {result.energy_intensity.kwh_per_ml_treated:.0f} kWh/ML | "
            f"{result.energy_intensity.kwh_per_kg_nh4_removed:.2f} kWh/kg NH₄-N | "
            f"Band: {result.energy_intensity.performance_band}"
        )

        return result

    # ── Step 1: Influent loads ─────────────────────────────────────────────

    def _calculate_loads(self, inp: AerationInputs, tkn_mg_l: float) -> LoadResult:
        """
        Calculate daily mass loads from flow and concentration.
        Load (kg/d) = Flow (ML/d) × 1000 m³/ML × Concentration (mg/L) × 10⁻³ kg/g × 10³ L/m³
                    = Flow (ML/d) × Concentration (mg/L)
        """
        r = LoadResult()
        r.design_flow_mld = inp.design_flow_mld
        r.peak_flow_mld   = inp.design_flow_mld * inp.peak_flow_factor

        # Average loads (kg/d)
        r.bod_load_kg_day = inp.design_flow_mld * inp.influent_bod_mg_l
        r.nh4_load_kg_day = inp.design_flow_mld * inp.influent_nh4_mg_l
        r.tkn_load_kg_day = inp.design_flow_mld * tkn_mg_l

        # Removed loads (kg/d)
        r.bod_removed_kg_day = r.bod_load_kg_day * inp.bod_removal_efficiency
        r.nh4_removed_kg_day = r.nh4_load_kg_day * inp.nh4_removal_efficiency
        r.tkn_removed_kg_day = r.tkn_load_kg_day * inp.nh4_removal_efficiency

        # Peak loads (kg/d) — used for blower sizing
        r.peak_bod_load_kg_day = r.bod_load_kg_day * inp.peak_flow_factor
        r.peak_nh4_load_kg_day = r.nh4_load_kg_day * inp.peak_flow_factor

        return r

    # ── Step 2: Oxygen demand ──────────────────────────────────────────────

    def _calculate_oxygen_demand(
        self, inp: AerationInputs, loads: LoadResult
    ) -> OxygenDemandResult:
        """
        Total oxygen demand for biological treatment.

        BOD removal (Metcalf & Eddy Eq. 7-63):
            O₂_BOD = 1.1 × BOD_removed (kg O₂/d)
            Note: coefficient of 1.1 accounts for endogenous respiration
            and cell synthesis.  Some designs use 1.0–1.2.

        Nitrification (stoichiometric, ASCE 2-06):
            O₂_N = 4.57 × NH₄_removed (kg O₂/d)
            Based on: NH₄⁺ + 2O₂ → NO₃⁻ + H₂O + 2H⁺
            4.57 = MW of O₂ consumed per mol NH₄-N = (2×32)/14

        Denitrification credit (stoichiometric):
            O₂_credit = 2.86 × NO₃_denitrified (kg O₂/d)
            Based on: NO₃⁻ → N₂ + 2.5 H₂O − 2H⁺, releasing 2.86 g O₂/g NO₃-N
        """
        r = OxygenDemandResult()

        # If technology module provided an O₂ demand, use it directly
        # (accounts for technology-specific yield, SND credit, etc.)
        if inp.o2_demand_override_kg_day and inp.o2_demand_override_kg_day > 0:
            r.o2_bod_kg_day = inp.o2_demand_override_kg_day * 0.60   # approx split
            r.o2_nitrification_kg_day = inp.o2_demand_override_kg_day * 0.55
            r.o2_denitrification_credit_kg_day = inp.o2_demand_override_kg_day * 0.15
            r.o2_total_avg_kg_day = inp.o2_demand_override_kg_day
            r.o2_total_peak_kg_day = r.o2_total_avg_kg_day * inp.peak_to_average_o2_factor
            r.o2_avg_kg_hr  = r.o2_total_avg_kg_day / 24.0
            r.o2_peak_kg_hr = r.o2_total_peak_kg_day / 24.0
            return r

        # Carbonaceous O₂ demand
        r.o2_bod_kg_day = 1.1 * loads.bod_removed_kg_day

        # Nitrification O₂ demand
        r.o2_nitrification_kg_day = 4.57 * loads.nh4_removed_kg_day

        # Denitrification O₂ credit
        no3_denitrified_kg_day = (
            loads.nh4_removed_kg_day * inp.denitrification_fraction
        )
        r.o2_denitrification_credit_kg_day = 2.86 * no3_denitrified_kg_day

        # Total average O₂ demand
        r.o2_total_avg_kg_day = max(
            0.0,
            r.o2_bod_kg_day + r.o2_nitrification_kg_day - r.o2_denitrification_credit_kg_day
        )

        # Peak O₂ demand — apply peak factor for blower sizing
        r.o2_total_peak_kg_day = r.o2_total_avg_kg_day * inp.peak_to_average_o2_factor

        # Hourly rates
        r.o2_avg_kg_hr  = r.o2_total_avg_kg_day  / 24.0
        r.o2_peak_kg_hr = r.o2_total_peak_kg_day / 24.0

        return r

    # ── Step 3: O₂ transfer correction ────────────────────────────────────

    def _calculate_transfer(self, inp: AerationInputs) -> TransferResult:
        """
        Convert between standard and actual O₂ transfer conditions.

        SOTE (Standard O₂ Transfer Efficiency):
            SOTE = sote_per_metre × submergence
            Typical fine bubble: 0.4%/m → 1.8% at 4.5m; often 1.5–2.0%/m
            Practical SOTE: 25–35% (fine bubble at 4–6m depth)

        Correction from SOTR to AOTR (Metcalf & Eddy Eq. 5-58):
            AOTR/SOTR = α × F × (β × Cs_T - C_L) / Cs_20 × θ^(T-20)

            Where:
              α    = alpha factor (typically 0.45–0.65 for fine bubble, municipal WW)
              F    = fouling factor (0.65–1.00; use 0.90 for design)
              β    = beta factor (0.95–0.99 for municipal WW)
              Cs_T = saturation DO at operating temperature, corrected for submergence
              C_L  = target operating DO (mg/L) — use 2.0 mg/L for design
              Cs_20 = 9.09 mg/L (clean water, sea level)
              θ    = 1.024 (Arrhenius temperature coefficient)
              T    = operating temperature (°C)
        """
        r = TransferResult()

        # SOTE: increases with diffuser submergence
        # Fine bubble SOTE ≈ 4–5%/m submergence (Mueller et al. 2002)
        r.sote = inp.sote_per_metre_submergence * inp.diffuser_submergence_m
        r.sote = min(r.sote, 0.40)  # Cap at 40% — physically reasonable maximum

        # DO saturation at operating temperature (empirical formula, ASCE)
        # Cs_T = 14.65 − 0.41T + 0.0079T² − 0.0000789T³  (mg/L)
        T = inp.inlet_temperature_celsius
        cs_t_surface = 14.65 - 0.41*T + 0.0079*T**2 - 0.0000789*T**3

        # Pressure correction for mid-depth of diffuser
        # Cs at depth ≈ Cs_surface × (1 + depth/(2×10.33)) — simplified
        depth_correction = 1.0 + inp.diffuser_submergence_m / (2.0 * 10.33)
        cs_t = cs_t_surface * depth_correction

        # Operating DO setpoint (typically 2.0 mg/L in aerobic zone)
        c_operating_do = 2.0

        # Temperature correction θ^(T-20)
        r.temperature_correction = THETA_O2_TRANSFER ** (T - 20.0)

        # DO deficit correction: (β·Cs_T − C_L) / Cs_20
        r.do_deficit_correction = (
            (inp.beta_factor * cs_t - c_operating_do) / O2_SOLUBILITY_20C_MG_L
        )
        r.do_deficit_correction = max(r.do_deficit_correction, 0.01)

        # Combined correction factor (AOTR / SOTR)
        r.correction_factor = (
            inp.alpha_factor *
            inp.fouling_factor *
            r.do_deficit_correction *
            r.temperature_correction
        )

        return r

    # ── Step 4: Airflow ───────────────────────────────────────────────────

    def _calculate_airflow(
        self,
        inp: AerationInputs,
        o2: OxygenDemandResult,
        transfer: TransferResult,
    ) -> AirflowResult:
        """
        Calculate required airflow from O₂ demand and SOTE.

        SOTR = O₂ demand / correction_factor  (converts actual to standard conditions)
        Airflow (Nm³/h) = SOTR (kg O₂/h) / (SOTE × O₂ density × air O₂ fraction)

        Where:
            O₂ density in air = 1.293 kg air/Nm³ × 0.2095 fraction = 0.271 kg O₂/Nm³
        """
        r = AirflowResult()

        o2_density_in_air_kg_nm3 = AIR_DENSITY_KG_NM3 * AIR_OXYGEN_FRACTION
        # = 1.293 × 0.2095 = 0.2709 kg O₂/Nm³

        # SOTR at average and peak conditions (kg O₂/h in clean water standard)
        sotr_avg_kg_hr  = o2.o2_avg_kg_hr  / transfer.correction_factor
        sotr_peak_kg_hr = o2.o2_peak_kg_hr / transfer.correction_factor

        # Airflow to deliver required SOTR through the diffuser system
        # Airflow = SOTR / (SOTE × O₂ density in air)
        if transfer.sote > 0:
            r.avg_airflow_nm3_hr  = sotr_avg_kg_hr  / (transfer.sote * o2_density_in_air_kg_nm3)
            r.peak_airflow_nm3_hr = sotr_peak_kg_hr / (transfer.sote * o2_density_in_air_kg_nm3)
        else:
            r.avg_airflow_nm3_hr  = sotr_avg_kg_hr  / o2_density_in_air_kg_nm3
            r.peak_airflow_nm3_hr = sotr_peak_kg_hr / o2_density_in_air_kg_nm3

        r.avg_airflow_nm3_min  = r.avg_airflow_nm3_hr  / 60.0
        r.peak_airflow_nm3_min = r.peak_airflow_nm3_hr / 60.0

        # Specific air rate: Nm³ air per m³ wastewater treated
        flow_m3_day = inp.design_flow_mld * 1000.0
        r.sair_ratio = (r.avg_airflow_nm3_hr * 24.0) / flow_m3_day if flow_m3_day > 0 else 0.0

        return r

    # ── Step 5: Blower sizing ─────────────────────────────────────────────

    def _calculate_blower(
        self, inp: AerationInputs, airflow: AirflowResult
    ) -> BlowerResult:
        """
        Blower power using the adiabatic compression formula.

        Shaft power (Metcalf & Eddy Eq. 5-74):
            P_shaft = (ṁ × R × T₁) / (n × η_b) × [(P₂/P₁)^n - 1]

            Where:
              ṁ    = mass flow rate of air (kg/s)
              R    = 287 J/kg·K (specific gas constant for air)
              T₁   = inlet temperature (K)
              n    = (γ−1)/γ = (1.4−1)/1.4 = 0.2857
              η_b  = blower isentropic efficiency (0–1)
              P₂   = discharge pressure = P₁ + diffuser depth pressure
                     + system losses (kPa absolute)
              P₁   = inlet absolute pressure (kPa)

        Total brake power including motor and VSD:
            P_brake = P_shaft / (η_motor × η_VSD)
        """
        r = BlowerResult()
        r.num_duty    = inp.num_duty_blowers
        r.num_standby = inp.num_standby_blowers

        # Pressure calculation
        # Discharge pressure = atmospheric + water column above diffusers + losses
        water_column_kpa = inp.diffuser_submergence_m * 9.81  # kPa (ρ·g·h / 1000)
        r.inlet_pressure_kpa     = inp.inlet_pressure_kpa
        r.discharge_pressure_kpa = (
            inp.inlet_pressure_kpa +
            water_column_kpa +
            inp.system_pressure_loss_kpa
        )
        r.pressure_ratio = r.discharge_pressure_kpa / r.inlet_pressure_kpa

        # Adiabatic exponent
        n_exp = (GAMMA_AIR - 1.0) / GAMMA_AIR  # = 0.2857 for air

        # Inlet temperature in Kelvin
        T1_K = inp.inlet_temperature_celsius + STD_TEMP_K

        def blower_shaft_power_kw(airflow_nm3_hr: float) -> float:
            """
            Calculate shaft power for a given airflow using adiabatic compression.
            Returns power in kW.
            """
            # Mass flow rate (kg/s)
            mass_flow_kg_s = (airflow_nm3_hr * AIR_DENSITY_KG_NM3) / 3600.0

            # Shaft power (W) — adiabatic compression formula
            shaft_power_w = (
                (mass_flow_kg_s * R_AIR_J_KG_K * T1_K) /
                (n_exp * inp.blower_efficiency)
            ) * (r.pressure_ratio ** n_exp - 1.0)

            return shaft_power_w / 1000.0  # Convert W → kW

        def total_brake_power_kw(shaft_kw: float) -> float:
            """Total power at motor terminals including motor and VSD losses."""
            return shaft_kw / (inp.motor_efficiency * inp.vsd_efficiency)

        # Airflow per duty blower
        avg_airflow_per_blower  = airflow.avg_airflow_nm3_hr  / inp.num_duty_blowers
        peak_airflow_per_blower = airflow.peak_airflow_nm3_hr / inp.num_duty_blowers

        # Power per blower
        r.avg_power_per_blower_kw  = total_brake_power_kw(blower_shaft_power_kw(avg_airflow_per_blower))
        r.peak_power_per_blower_kw = total_brake_power_kw(blower_shaft_power_kw(peak_airflow_per_blower))

        # Total duty power
        r.total_duty_power_avg_kw  = r.avg_power_per_blower_kw  * inp.num_duty_blowers
        r.total_duty_power_peak_kw = r.peak_power_per_blower_kw * inp.num_duty_blowers

        # Motor sizing: round up to next standard motor size at peak
        standard_motors_kw = [
            7.5, 11, 15, 18.5, 22, 30, 37, 45, 55, 75, 90,
            110, 132, 160, 200, 250, 315, 400, 500, 630, 800, 1000
        ]
        if inp.blower_motor_kw:
            r.recommended_motor_kw = inp.blower_motor_kw
        else:
            # Select smallest standard motor that exceeds peak power per blower
            motor_required = r.peak_power_per_blower_kw * 1.10  # 10% service factor
            r.recommended_motor_kw = next(
                (m for m in standard_motors_kw if m >= motor_required),
                standard_motors_kw[-1]
            )

        # Total installed power (duty + standby)
        total_blowers = inp.num_duty_blowers + inp.num_standby_blowers
        r.total_installed_power_kw = r.recommended_motor_kw * total_blowers

        # Configuration description
        r.configuration_description = (
            f"{inp.num_duty_blowers}D+{inp.num_standby_blowers}S × {r.recommended_motor_kw:.0f} kW"
        )

        # Configuration adequacy check
        # Each duty blower must be able to meet peak demand with all duty blowers running
        if r.peak_power_per_blower_kw > r.recommended_motor_kw:
            r.configuration_adequate = False
            r.configuration_warning = (
                f"Selected motor ({r.recommended_motor_kw:.0f} kW) is insufficient for peak demand "
                f"({r.peak_power_per_blower_kw:.0f} kW per blower). "
                f"Consider increasing motor size or adding duty blowers."
            )
        else:
            r.configuration_adequate = True

        # Annual energy: based on average duty power, 8760 hours/year
        r.annual_aeration_energy_kwh = r.total_duty_power_avg_kw * 8760.0
        r.annual_aeration_energy_mwh = r.annual_aeration_energy_kwh / 1000.0

        return r

    # ── Step 6: Energy intensity ──────────────────────────────────────────

    def _calculate_energy_intensity(
        self,
        inp: AerationInputs,
        loads: LoadResult,
        blower: BlowerResult,
    ) -> EnergyIntensityResult:
        """
        Energy intensity benchmarking metrics.
        These are the primary metrics for design comparison and energy guarantees.
        """
        r = EnergyIntensityResult()

        annual_kwh = blower.annual_aeration_energy_kwh

        # kWh / ML treated (based on average flow, 365 days)
        annual_ml = inp.design_flow_mld * 365.0
        r.kwh_per_ml_treated = annual_kwh / annual_ml if annual_ml > 0 else 0.0

        # kWh / kg NH₄-N removed
        annual_nh4_removed_kg = loads.nh4_removed_kg_day * 365.0
        r.kwh_per_kg_nh4_removed = (
            annual_kwh / annual_nh4_removed_kg if annual_nh4_removed_kg > 0 else 0.0
        )

        # kWh / kg BOD removed
        annual_bod_removed_kg = loads.bod_removed_kg_day * 365.0
        r.kwh_per_kg_bod_removed = (
            annual_kwh / annual_bod_removed_kg if annual_bod_removed_kg > 0 else 0.0
        )

        # kWh / kg O₂ transferred (overall system aeration efficiency)
        annual_o2_kg = loads.nh4_removed_kg_day * 4.57 * 365.0
        r.kwh_per_kg_o2_transferred = annual_kwh / annual_o2_kg if annual_o2_kg > 0 else 0.0

        # Energy guarantee metric: kWh/kg NH₄-N at PEAK conditions
        # This is the worst-case metric used for energy guarantees in contracts
        peak_nh4_removed_kg_day = loads.peak_nh4_load_kg_day * inp.nh4_removal_efficiency
        peak_annual_nh4_kg = peak_nh4_removed_kg_day * 365.0
        r.kwh_per_kg_nh4_peak = (
            annual_kwh / peak_annual_nh4_kg if peak_annual_nh4_kg > 0 else 0.0
        )

        # Performance band classification
        r.performance_band = self._classify_performance(r.kwh_per_ml_treated)

        return r

    @staticmethod
    def _classify_performance(kwh_per_ml: float) -> str:
        """
        Classify aeration energy performance (BLOWER energy only).
        Based on WEF Energy Conservation in Water and Wastewater Facilities (2009).
        Note: these are BLOWER-only benchmarks, not whole-plant.
        Whole-plant total is typically 1.5–2.5× the blower-only figure.

        Blower-only benchmarks (aeration zone):
          Excellent: < 100 kWh/ML (MABR, AGS with high SND credit)
          Good:      100–200 kWh/ML (well-tuned BNR, DO control)
          Average:   200–350 kWh/ML (conventional BNR)
          Below avg: 350–500 kWh/ML (over-aerated or high nitrification demand)
          Poor:      > 500 kWh/ML (requires investigation)
        """
        if kwh_per_ml < 100:
            return "Excellent — top decile (MABR / high-efficiency)"
        elif kwh_per_ml < 200:
            return "Good — above average"
        elif kwh_per_ml < 350:
            return "Average — conventional BNR"
        elif kwh_per_ml < 500:
            return "Below average — review DO control"
        else:
            return "Poor — requires energy optimisation"

    @staticmethod
    def _echo_inputs(inp: AerationInputs) -> Dict[str, Any]:
        """Record key inputs for engineering transparency."""
        return {
            "design_flow_mld":                    inp.design_flow_mld,
            "peak_flow_factor":                   inp.peak_flow_factor,
            "influent_bod_mg_l":                  inp.influent_bod_mg_l,
            "influent_nh4_mg_l":                  inp.influent_nh4_mg_l,
            "influent_tkn_mg_l":                  inp.influent_tkn_mg_l,
            "bod_removal_efficiency":             inp.bod_removal_efficiency,
            "nh4_removal_efficiency":             inp.nh4_removal_efficiency,
            "denitrification_fraction":           inp.denitrification_fraction,
            "standard_aeration_efficiency":       inp.standard_aeration_efficiency_kg_o2_kwh,
            "alpha_factor":                       inp.alpha_factor,
            "beta_factor":                        inp.beta_factor,
            "fouling_factor":                     inp.fouling_factor,
            "sote_per_metre":                     inp.sote_per_metre_submergence,
            "diffuser_submergence_m":             inp.diffuser_submergence_m,
            "peak_o2_factor":                     inp.peak_to_average_o2_factor,
            "blower_efficiency":                  inp.blower_efficiency,
            "motor_efficiency":                   inp.motor_efficiency,
            "vsd_efficiency":                     inp.vsd_efficiency,
            "system_pressure_loss_kpa":           inp.system_pressure_loss_kpa,
            "inlet_temperature_celsius":          inp.inlet_temperature_celsius,
            "num_duty_blowers":                   inp.num_duty_blowers,
            "num_standby_blowers":                inp.num_standby_blowers,
        }


# ─────────────────────────────────────────────────────────────────────────────
# SENSITIVITY ANALYSIS
# ─────────────────────────────────────────────────────────────────────────────

def run_sensitivity(
    base_inputs: AerationInputs,
    parameter: str,
    values: List[float],
) -> Dict[str, List]:
    """
    Run the aeration model across a range of values for one parameter.
    Returns a dict of lists for charting.

    Parameters
    ----------
    base_inputs : AerationInputs
        Base case inputs (unchanged parameters)
    parameter : str
        Name of the AerationInputs field to vary
        e.g. "influent_nh4_mg_l", "alpha_factor", "design_flow_mld"
    values : list of float
        Values to test for the given parameter

    Returns
    -------
    dict with keys:
        "values"              — the input values tested
        "o2_demand_kg_day"    — resulting avg O₂ demand
        "blower_power_kw"     — resulting total duty blower power
        "kwh_per_ml"          — resulting energy intensity
        "kwh_per_kg_nh4"      — resulting energy per kg NH₄ removed
        "annual_energy_mwh"   — resulting annual energy
    """
    model = AerationModel()
    out: Dict[str, List] = {
        "values":            [],
        "o2_demand_kg_day":  [],
        "blower_power_kw":   [],
        "kwh_per_ml":        [],
        "kwh_per_kg_nh4":    [],
        "annual_energy_mwh": [],
    }

    import dataclasses

    for val in values:
        # Build modified inputs
        modified = dataclasses.replace(base_inputs, **{parameter: val})
        result = model.calculate(modified)
        out["values"].append(val)
        out["o2_demand_kg_day"].append(result.oxygen_demand.o2_total_avg_kg_day)
        out["blower_power_kw"].append(result.blower.total_duty_power_avg_kw)
        out["kwh_per_ml"].append(result.energy_intensity.kwh_per_ml_treated)
        out["kwh_per_kg_nh4"].append(result.energy_intensity.kwh_per_kg_nh4_removed)
        out["annual_energy_mwh"].append(result.blower.annual_aeration_energy_mwh)

    return out


# ─────────────────────────────────────────────────────────────────────────────
# HELPER: Build AerationInputs from platform domain inputs
# ─────────────────────────────────────────────────────────────────────────────

def aeration_inputs_from_scenario(
    domain_inputs: dict,
    technology_params: dict,
    aeration_overrides: dict = None,
) -> AerationInputs:
    """
    Build an AerationInputs object from a scenario's domain_inputs dict
    and optional technology parameters.  Used by the domain interface and
    Streamlit pages to avoid duplicating field mapping logic.

    Parameters
    ----------
    domain_inputs : dict
        ScenarioModel.domain_inputs (plant flows and water quality)
    technology_params : dict
        ScenarioModel.treatment_pathway.technology_parameters.get("bnr", {})
    aeration_overrides : dict, optional
        Any additional user overrides from the aeration configuration UI
    """
    overrides = aeration_overrides or {}

    return AerationInputs(
        design_flow_mld           = domain_inputs.get("design_flow_mld", 10.0),
        peak_flow_factor          = domain_inputs.get("peak_flow_factor", 2.5),
        influent_bod_mg_l         = domain_inputs.get("influent_bod_mg_l", 250.0),
        influent_nh4_mg_l         = domain_inputs.get("influent_nh4_mg_l", 35.0),
        influent_tkn_mg_l         = domain_inputs.get("influent_tkn_mg_l", 45.0),
        bod_removal_efficiency    = overrides.get("bod_removal_efficiency", 0.95),
        nh4_removal_efficiency    = overrides.get("nh4_removal_efficiency", 0.95),
        denitrification_fraction  = overrides.get("denitrification_fraction", 0.50),
        alpha_factor              = overrides.get("alpha_factor",
                                        technology_params.get("alpha_factor", 0.55)),
        beta_factor               = overrides.get("beta_factor", 0.97),
        fouling_factor            = overrides.get("fouling_factor", 0.90),
        sote_per_metre_submergence = overrides.get("sote_per_metre_submergence", 0.049),
        diffuser_submergence_m    = overrides.get("diffuser_submergence_m", 4.5),
        peak_to_average_o2_factor = overrides.get("peak_to_average_o2_factor", 1.4),
        blower_efficiency         = overrides.get("blower_efficiency", 0.70),
        motor_efficiency          = overrides.get("motor_efficiency", 0.95),
        vsd_efficiency            = overrides.get("vsd_efficiency", 0.97),
        system_pressure_loss_kpa  = overrides.get("system_pressure_loss_kpa", 15.0),
        inlet_temperature_celsius = domain_inputs.get("influent_temperature_celsius", 20.0),
        num_duty_blowers          = int(overrides.get("num_duty_blowers", 2)),
        num_standby_blowers       = int(overrides.get("num_standby_blowers", 1)),
        blower_motor_kw           = overrides.get("blower_motor_kw"),
        o2_demand_override_kg_day = overrides.get("o2_demand_override_kg_day"),
        standard_aeration_efficiency_kg_o2_kwh = overrides.get(
            "standard_aeration_efficiency_kg_o2_kwh", 2.0
        ),
    )
