"""
core/carbon/carbon_engine.py

Domain-agnostic carbon and energy accounting engine.
Calculates Scope 1, 2, and 3 emissions from standardised inputs
produced by domain technology result objects.
"""

from __future__ import annotations
from typing import Dict, Optional, Any

from core.project.project_model import AssumptionsSet, CarbonResult
from core.assumptions.assumptions_manager import AssumptionsManager


class CarbonEngine:
    """
    Carbon and energy accounting engine.

    Scope classification
    --------------------
    Scope 1  — Direct process emissions (N2O from BNR, CH4 from digesters,
                CO2 from incineration / thermal treatment)
    Scope 2  — Indirect emissions from purchased electricity
    Scope 3  — Upstream chemical production, transport, embodied carbon
                (annualised over project life)
    Avoided  — Credits: biogas/solar electricity generation, avoided
                landfill emissions, etc.
    """

    def __init__(self, assumptions: AssumptionsSet):
        self.assumptions = assumptions
        self._mgr = AssumptionsManager()

    def calculate(
        self,
        energy_kwh_per_day: float,
        chemical_consumption: Dict[str, float],
        domain_specific_emissions: Optional[Dict[str, float]] = None,
        avoided_kwh_per_day: float = 0.0,
        other_avoided_tco2e_yr: float = 0.0,
        design_flow_mld: float = 0.0,
        throughput_tonne_ds_day: float = 0.0,
        embodied_carbon_tco2e: float = 0.0,
        analysis_period_years: int = 30,
    ) -> CarbonResult:
        """
        Calculate the carbon footprint for a scenario.

        Parameters
        ----------
        energy_kwh_per_day : float
            Total net electricity consumption (kWh/day)
        chemical_consumption : dict
            {chemical_name: kg/day} — names must match emission factor keys
        domain_specific_emissions : dict, optional
            {emission_source: tCO2e/year} — Scope 1 process emissions
            pre-calculated by the domain module (e.g. N2O from BNR,
            CH4 from digesters)
        avoided_kwh_per_day : float
            Electricity generated on-site (biogas CHP, solar) in kWh/day
        other_avoided_tco2e_yr : float
            Other avoided emissions (e.g. avoided landfill methane) tCO2e/yr
        design_flow_mld : float
            For specific emission intensity (kg CO2e/kL)
        throughput_tonne_ds_day : float
            For biosolids specific intensity (kg CO2e/t DS)
        embodied_carbon_tco2e : float
            Construction-phase embodied carbon (total, tCO2e)
        analysis_period_years : int
            For annualising embodied carbon
        """
        grid_ef = self._get("carbon", "grid_emission_factor_kg_co2e_per_kwh", 0.79)
        carbon_price = self._get("carbon", "carbon_price_per_tonne", 35.0)
        chemical_efs = self._get("carbon", "chemical_emissions", {})

        # ── Scope 2: Electricity ──────────────────────────────────────────
        scope_2_tco2e_yr = (energy_kwh_per_day * 365 * grid_ef) / 1000.0

        # ── Scope 1: Process emissions ────────────────────────────────────
        scope_1_tco2e_yr = 0.0
        if domain_specific_emissions:
            scope_1_tco2e_yr = sum(domain_specific_emissions.values())

        # ── Scope 3: Chemical upstream emissions ──────────────────────────
        scope_3_chemicals_tco2e_yr = 0.0
        for chem_name, kg_per_day in chemical_consumption.items():
            # Normalise chemical name for lookup
            lookup_key = chem_name.lower().replace(" ", "_").replace("-", "_")
            ef_kg_co2e_per_kg = chemical_efs.get(lookup_key, 0.0)
            scope_3_chemicals_tco2e_yr += (kg_per_day * 365 * ef_kg_co2e_per_kg) / 1000.0

        # Annualise embodied carbon over project life
        scope_3_embodied_yr = (
            embodied_carbon_tco2e / analysis_period_years
            if analysis_period_years > 0 else 0.0
        )

        scope_3_tco2e_yr = scope_3_chemicals_tco2e_yr + scope_3_embodied_yr

        # ── Avoided emissions ─────────────────────────────────────────────
        avoided_electricity_tco2e_yr = (avoided_kwh_per_day * 365 * grid_ef) / 1000.0
        avoided_tco2e_yr = avoided_electricity_tco2e_yr + other_avoided_tco2e_yr

        # ── Net emissions ─────────────────────────────────────────────────
        net_tco2e_yr = scope_1_tco2e_yr + scope_2_tco2e_yr + scope_3_tco2e_yr - avoided_tco2e_yr

        # ── Carbon cost ───────────────────────────────────────────────────
        carbon_cost_annual = net_tco2e_yr * carbon_price

        # ── Specific intensities ──────────────────────────────────────────
        specific_kg_per_kl = None
        if design_flow_mld > 0:
            annual_kl = design_flow_mld * 1000 * 365
            specific_kg_per_kl = (net_tco2e_yr * 1000) / annual_kl

        specific_kg_per_tds = None
        if throughput_tonne_ds_day > 0:
            annual_tds = throughput_tonne_ds_day * 365
            specific_kg_per_tds = (net_tco2e_yr * 1000) / annual_tds

        return CarbonResult(
            scope_1_tco2e_yr=round(scope_1_tco2e_yr, 2),
            scope_2_tco2e_yr=round(scope_2_tco2e_yr, 2),
            scope_3_tco2e_yr=round(scope_3_tco2e_yr, 2),
            avoided_tco2e_yr=round(avoided_tco2e_yr, 2),
            net_tco2e_yr=round(net_tco2e_yr, 2),
            embodied_carbon_tco2e=round(embodied_carbon_tco2e, 2),
            carbon_cost_annual=round(carbon_cost_annual, 2),
            specific_kg_co2e_per_kl=(
                round(specific_kg_per_kl, 4) if specific_kg_per_kl else None
            ),
            specific_kg_co2e_per_tonne_ds=(
                round(specific_kg_per_tds, 2) if specific_kg_per_tds else None
            ),
            grid_emission_factor_used=grid_ef,
        )

    def _get(self, category: str, key: str, default: Any = None) -> Any:
        return self._mgr.get(self.assumptions, category, key, default)
