"""
domains/wastewater/result_model.py

Result objects returned by the WastewaterDomainInterface.
These carry both the standardised core engine outputs and
wastewater-specific engineering outputs for display.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from core.project.project_model import (
    CostResult, CarbonResult, RiskResult, ValidationResult,
)
from domains.wastewater.technologies.base_technology import TechnologyResult


@dataclass
class WastewaterCalculationResult:
    """
    Full calculation result for a wastewater scenario.
    Returned by WastewaterDomainInterface.run_scenario().
    The Streamlit app and report engine read from this object.
    """

    is_valid: bool = True

    # Per-technology results (keyed by technology code)
    technology_results: Dict[str, TechnologyResult] = field(default_factory=dict)

    # Aggregated mass and energy balance
    aggregated: Dict[str, Any] = field(default_factory=dict)
    # Keys: total_energy_kwh_day, total_chemical_consumption,
    #       total_sludge_kgds_day, all_capex_items, all_opex_items,
    #       process_emissions_tco2e_yr

    # Standardised core engine outputs
    cost_result: Optional[CostResult] = None
    carbon_result: Optional[CarbonResult] = None
    risk_result: Optional[RiskResult] = None
    validation_result: Optional[ValidationResult] = None

    # Wastewater-specific engineering summary (for display and reports)
    engineering_summary: Dict[str, Any] = field(default_factory=dict)
    # Keys: reactor_volume_m3, sludge_production_kgds_day,
    #       total_energy_kwh_day, specific_energy_kwh_kl, etc.

    def to_domain_outputs_dict(self) -> Dict[str, Any]:
        """
        Serialise domain-specific outputs for storage in ScenarioModel.domain_specific_outputs.
        Includes the enriched performance_outputs dict from finalise() plus notes.
        """
        tech_perf = {}
        for code, result in self.technology_results.items():
            perf = dict(result.performance_outputs)   # already enriched by finalise()
            # Add technology_category for UI badge display
            perf["technology_category"] = result.technology_category
            # Embed notes as a nested dict for the results page
            perf["_notes"] = {
                "assumptions": result.notes.assumptions,
                "limitations": result.notes.limitations,
                "warnings":    result.notes.warnings,
            }
            tech_perf[code] = perf

        return {
            "engineering_summary": self.engineering_summary,
            "aggregated": {
                k: v for k, v in self.aggregated.items()
                if k not in ("all_capex_items", "all_opex_items")
            },
            "technology_performance": tech_perf,
        }
