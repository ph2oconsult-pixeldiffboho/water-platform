"""
domains/wastewater/biosolids_orchestrator.py

Biosolids Orchestrator
=======================
Integrates SludgeModel, DigestionModel, and BiosolidsCarbonModel into a
single callable interface.  The Streamlit biosolids page calls this class;
it handles all model interconnection logic.

Also provides:
  - WholePlantCarbon: aggregates liquid line + solids line into a unified total
  - helper to build biosolids inputs from an existing ScenarioModel
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from domains.wastewater.sludge_model import SludgeInputs, SludgeMassBalance, SludgeModel
from domains.wastewater.digestion_model import DigestionInputs, DigestionResult, DigestionModel
from domains.wastewater.biosolids_carbon_model import (
    BiosolidsCarbonInputs, BiosolidsCarbonResult, BiosolidsCarbonModel,
)


# ─────────────────────────────────────────────────────────────────────────────
# COMBINED INPUT / RESULT
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class BiosolidsInputs:
    """Single combined input structure for the biosolids orchestrator."""
    sludge: SludgeInputs = field(default_factory=SludgeInputs)
    digestion: DigestionInputs = field(default_factory=DigestionInputs)
    carbon: BiosolidsCarbonInputs = field(default_factory=BiosolidsCarbonInputs)


@dataclass
class BiosolidsResult:
    """Combined result from the full biosolids model chain."""
    sludge: SludgeMassBalance = field(default_factory=SludgeMassBalance)
    digestion: DigestionResult = field(default_factory=DigestionResult)
    carbon: BiosolidsCarbonResult = field(default_factory=BiosolidsCarbonResult)

    def to_domain_outputs_dict(self) -> Dict[str, Any]:
        """Serialise for storage in ScenarioModel.domain_specific_outputs."""
        return {
            "sludge": self.sludge.to_summary_dict(),
            "digestion": self.digestion.to_summary_dict(),
            "biosolids_carbon": self.carbon.to_summary_dict(),
        }

    def to_flat_summary(self) -> Dict[str, Any]:
        """Flat dict for the comparison page."""
        d = {}
        d.update({f"[Sludge] {k}": v for k, v in self.sludge.to_summary_dict().items()})
        d.update({f"[Digestion] {k}": v for k, v in self.digestion.to_summary_dict().items()})
        d.update({f"[Carbon] {k}": v for k, v in self.carbon.to_summary_dict().items()})
        return d


@dataclass
class WholePlantCarbon:
    """
    Aggregates liquid line and solids line GHG into a single whole-of-plant result.
    Designed to replace or extend the existing ScenarioModel.carbon_result.
    """

    # ── Liquid line (from existing CarbonEngine output) ───────────────────
    ll_scope1_tco2e_yr: float = 0.0     # N₂O, CH₄ from biological treatment
    ll_scope2_tco2e_yr: float = 0.0     # Electricity for liquid treatment
    ll_scope3_tco2e_yr: float = 0.0     # Chemicals
    ll_avoided_tco2e_yr: float = 0.0

    # ── Solids line (from BiosolidsCarbonResult) ──────────────────────────
    sl_scope1_tco2e_yr: float = 0.0     # Digester fugitive, land app N₂O, landfill CH₄
    sl_scope2_tco2e_yr: float = 0.0     # Dewatering electricity
    sl_scope3_tco2e_yr: float = 0.0     # Polymer, transport
    sl_avoided_tco2e_yr: float = 0.0    # CHP electricity, biochar

    # ── Totals ────────────────────────────────────────────────────────────
    total_scope1_tco2e_yr: float = 0.0
    total_scope2_tco2e_yr: float = 0.0
    total_scope3_tco2e_yr: float = 0.0
    total_gross_tco2e_yr: float = 0.0
    total_avoided_tco2e_yr: float = 0.0
    total_net_tco2e_yr: float = 0.0

    # 30-year
    net_tco2e_30yr: float = 0.0
    gross_tco2e_30yr: float = 0.0

    # Per ML treated
    kg_co2e_per_ml_net: float = 0.0

    def to_summary_dict(self) -> Dict[str, Any]:
        return {
            "Liquid line gross (tCO₂e/yr)":   round(self.ll_scope1_tco2e_yr + self.ll_scope2_tco2e_yr + self.ll_scope3_tco2e_yr, 0),
            "Solids line gross (tCO₂e/yr)":   round(self.sl_scope1_tco2e_yr + self.sl_scope2_tco2e_yr + self.sl_scope3_tco2e_yr, 0),
            "Total gross (tCO₂e/yr)":         round(self.total_gross_tco2e_yr, 0),
            "Total avoided (tCO₂e/yr)":       round(self.total_avoided_tco2e_yr, 0),
            "Net emissions (tCO₂e/yr)":       round(self.total_net_tco2e_yr, 0),
            "Net 30yr (tCO₂e)":               round(self.net_tco2e_30yr, 0),
            "kg CO₂e/ML net":                 round(self.kg_co2e_per_ml_net, 1),
        }


# ─────────────────────────────────────────────────────────────────────────────
# ORCHESTRATOR
# ─────────────────────────────────────────────────────────────────────────────

class BiosolidsOrchestrator:
    """
    Runs the full biosolids calculation chain.
    Handles model interconnection: SludgeModel → DigestionModel → BiosolidsCarbonModel.
    """

    def __init__(self):
        self._sludge_model  = SludgeModel()
        self._digestion_model = DigestionModel()
        self._carbon_model  = BiosolidsCarbonModel()

    def run(self, inputs: BiosolidsInputs) -> BiosolidsResult:
        """
        Execute the full biosolids model chain.

        Flow
        ----
        1. SludgeModel → mass balance (raw → thickened → digested → cake)
        2. Bridge: pass sludge mass balance to DigestionInputs
        3. DigestionModel → biogas, CH4, CHP energy, fugitive emissions
        4. BiosolidsCarbonModel → full carbon account
        """
        result = BiosolidsResult()

        # Step 1: Sludge mass balance
        result.sludge = self._sludge_model.calculate(inputs.sludge)

        # Step 2: Bridge SludgeMassBalance → DigestionInputs
        # The digestion model needs feed VS and DS from the sludge model
        dig_inp = inputs.digestion
        dig_inp.feed_ds_t_yr       = result.sludge.thickened_ds_t_yr
        dig_inp.feed_vs_t_yr       = result.sludge.total_raw_vs_t_yr
        dig_inp.vs_destruction_pct = inputs.sludge.vs_destruction_pct
        dig_inp.digestion_enabled  = inputs.sludge.digestion_included
        # Feed temperature from plant inputs (if set)
        if hasattr(inputs, "_feed_temp_celsius"):
            dig_inp.feed_temp_celsius = inputs._feed_temp_celsius

        # Step 3: Digestion model
        result.digestion = self._digestion_model.calculate(dig_inp)

        # Step 4: Biosolids carbon model
        result.carbon = self._carbon_model.calculate(
            inp=inputs.carbon,
            sludge=result.sludge,
            digestion=result.digestion,
        )

        return result

    def aggregate_whole_plant(
        self,
        biosolids_result: BiosolidsResult,
        liquid_carbon_result: Any,   # CarbonResult from existing carbon engine
        design_flow_mld: float = 0.0,
        lifecycle_years: int = 30,
    ) -> WholePlantCarbon:
        """
        Aggregate liquid line (existing CarbonResult) + solids line into
        a single whole-of-plant carbon total.
        """
        wpc = WholePlantCarbon()

        # Liquid line from existing CarbonResult object
        if liquid_carbon_result:
            wpc.ll_scope1_tco2e_yr  = getattr(liquid_carbon_result, "scope_1_tco2e_yr", 0.0)
            wpc.ll_scope2_tco2e_yr  = getattr(liquid_carbon_result, "scope_2_tco2e_yr", 0.0)
            wpc.ll_scope3_tco2e_yr  = getattr(liquid_carbon_result, "scope_3_tco2e_yr", 0.0)
            wpc.ll_avoided_tco2e_yr = getattr(liquid_carbon_result, "avoided_tco2e_yr", 0.0)

        # Solids line from BiosolidsCarbonResult
        bc = biosolids_result.carbon
        wpc.sl_scope1_tco2e_yr  = bc.total_scope1_tco2e_yr
        wpc.sl_scope2_tco2e_yr  = bc.total_scope2_tco2e_yr
        wpc.sl_scope3_tco2e_yr  = bc.total_scope3_tco2e_yr
        # FIXED: CHP electricity credit belongs here only — applied once against total Scope 2
        # It reduces total plant grid purchases, not the solids-line gross emissions
        chp_credit = biosolids_result.digestion.energy_recovery.avoided_grid_co2e_t_yr
        wpc.sl_avoided_tco2e_yr = bc.total_avoided_tco2e_yr + chp_credit

        # Totals
        wpc.total_scope1_tco2e_yr = wpc.ll_scope1_tco2e_yr + wpc.sl_scope1_tco2e_yr
        wpc.total_scope2_tco2e_yr = wpc.ll_scope2_tco2e_yr + wpc.sl_scope2_tco2e_yr
        wpc.total_scope3_tco2e_yr = wpc.ll_scope3_tco2e_yr + wpc.sl_scope3_tco2e_yr
        wpc.total_gross_tco2e_yr  = (
            wpc.total_scope1_tco2e_yr +
            wpc.total_scope2_tco2e_yr +
            wpc.total_scope3_tco2e_yr
        )
        wpc.total_avoided_tco2e_yr = wpc.ll_avoided_tco2e_yr + wpc.sl_avoided_tco2e_yr
        wpc.total_net_tco2e_yr     = wpc.total_gross_tco2e_yr - wpc.total_avoided_tco2e_yr

        # Lifecycle
        wpc.net_tco2e_30yr   = wpc.total_net_tco2e_yr * lifecycle_years
        wpc.gross_tco2e_30yr = wpc.total_gross_tco2e_yr * lifecycle_years

        # Intensity per ML treated
        if design_flow_mld > 0:
            annual_ml = design_flow_mld * 365
            wpc.kg_co2e_per_ml_net = wpc.total_net_tco2e_yr * 1000 / annual_ml

        return wpc


# ─────────────────────────────────────────────────────────────────────────────
# HELPER: Build BiosolidsInputs from a ScenarioModel
# ─────────────────────────────────────────────────────────────────────────────

def biosolids_inputs_from_scenario(
    domain_inputs: dict,
    tech_results_summary: dict,
    biosolids_overrides: dict = None,
) -> BiosolidsInputs:
    """
    Construct a BiosolidsInputs object from a scenario's stored data.

    Parameters
    ----------
    domain_inputs : dict
        ScenarioModel.domain_inputs (plant flows and water quality)
    tech_results_summary : dict
        Aggregated technology results — expects 'total_sludge_kgds_day'
    biosolids_overrides : dict, optional
        User overrides from the biosolids configuration UI
    """
    ov = biosolids_overrides or {}

    sludge_kg_ds_day = tech_results_summary.get("total_sludge_kgds_day", 1500.0)

    sludge_inp = SludgeInputs(
        secondary_sludge_kg_ds_day    = sludge_kg_ds_day,
        secondary_vs_fraction         = ov.get("secondary_vs_fraction", 0.80),
        digestion_included            = ov.get("digestion_included", True),
        vs_destruction_pct            = ov.get("vs_destruction_pct", 58.0),
        dewatering_type               = ov.get("dewatering_type", "centrifuge"),
        disposal_pathway              = ov.get("disposal_pathway", "land_application"),
        transport_distance_km         = ov.get("transport_distance_km", 50.0),
        thickened_ts_pct              = ov.get("thickened_ts_pct", 5.0),
        land_application_cost_per_t_ds= ov.get("land_application_cost_per_t_ds", 45.0),
        landfill_cost_per_t_ds        = ov.get("landfill_cost_per_t_ds", 280.0),
    )

    dig_inp = DigestionInputs(
        vs_destruction_pct                     = ov.get("vs_destruction_pct", 58.0),
        biogas_yield_m3_per_kg_vs_destroyed    = ov.get("biogas_yield_m3_per_kg_vs_destroyed", 0.75),
        biogas_ch4_fraction                    = ov.get("biogas_ch4_fraction", 0.65),
        methane_capture_efficiency             = ov.get("methane_capture_efficiency", 0.95),
        flare_fraction                         = ov.get("flare_fraction", 0.05),
        cover_fugitive_fraction                = ov.get("cover_fugitive_fraction", 0.015),
        handling_fugitive_fraction             = ov.get("handling_fugitive_fraction", 0.005),
        chp_electrical_efficiency              = ov.get("chp_electrical_efficiency", 0.38),
        chp_thermal_efficiency                 = ov.get("chp_thermal_efficiency", 0.45),
        grid_emission_factor_kg_co2e_per_kwh   = ov.get("grid_emission_factor", 0.79),
        digestion_enabled                      = ov.get("digestion_included", True),
        chp_enabled                            = ov.get("chp_enabled", True),
    )

    carbon_inp = BiosolidsCarbonInputs(
        include_land_application_n2o   = ov.get("include_land_application_n2o", True),
        include_landfill_ch4           = ov.get("include_landfill_ch4", True),
        include_biochar_credit         = ov.get("include_biochar_credit", False),
        grid_emission_factor_kg_co2e_per_kwh = ov.get("grid_emission_factor", 0.79),
        biochar_included               = ov.get("include_biochar_credit", False),
    )

    return BiosolidsInputs(sludge=sludge_inp, digestion=dig_inp, carbon=carbon_inp)
