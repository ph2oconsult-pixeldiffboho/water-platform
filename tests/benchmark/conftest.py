"""
tests/benchmark/conftest.py

Shared pytest fixtures and helpers for the benchmark test suite.
"""
from __future__ import annotations
import copy
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.assumptions.assumptions_manager import AssumptionsManager
from core.project.project_model import DomainType
from domains.wastewater.domain_interface import WastewaterDomainInterface
from domains.wastewater.input_model import WastewaterInputs
from tests.benchmark.scenarios import Scenario, to_inputs_dict


# ── Base assumptions fixture ───────────────────────────────────────────────────

def base_assumptions():
    """Default wastewater assumptions loaded once per test session."""
    return AssumptionsManager().load_defaults(DomainType.WASTEWATER)


# ── Run helper ─────────────────────────────────────────────────────────────────

def run_scenario_tech(scenario: Scenario, tech: str, base_assumptions):
    """
    Run a single technology against a scenario.

    Applies economic overrides from the scenario definition, then runs the
    domain interface and returns the raw CalculationResult.
    """
    a = copy.deepcopy(base_assumptions)

    # Apply any scenario-level economic overrides
    if scenario.electricity_price_per_kwh != 0.14:
        a.cost_assumptions["opex_unit_rates"]["electricity_per_kwh"] = (
            scenario.electricity_price_per_kwh
        )
    if scenario.sludge_disposal_per_tds != 280.0:
        a.cost_assumptions["opex_unit_rates"]["sludge_disposal_per_tds"] = (
            scenario.sludge_disposal_per_tds
        )
    if scenario.carbon_price_per_tco2e != 35.0:
        a.carbon_assumptions["carbon_price_per_tonne_co2e"] = (
            scenario.carbon_price_per_tco2e
        )
    if scenario.discount_rate != 0.07:
        a.cost_assumptions["discount_rate"] = scenario.discount_rate

    iface = WastewaterDomainInterface(a)
    inp   = WastewaterInputs(**to_inputs_dict(scenario))
    return iface.run_scenario(inp, [tech], {})



def _calc_kwh_kg_nh4(tp: dict, eng: dict, result) -> float:
    """kWh per kg NH4 removed. Uses direct field if available, else computes from totals."""
    direct = float(tp.get("kwh_per_kg_nh4_removed", 0) or 0)
    if direct > 0:
        return direct
    # Fallback: total plant energy / NH4 mass removed per day
    nh4_in  = 35.0   # default if not in aggregated
    nh4_out = float(tp.get("effluent_nh4_mg_l", 1) or 1)
    flow    = float(eng.get("design_flow_mld", 10) or 10)
    nh4_rem = max(0.001, (nh4_in - nh4_out) * flow * 1000 / 1000)  # kg/day
    kwh_day = eng.get("total_energy_kwh_day", 0) or 0
    return kwh_day / nh4_rem if nh4_rem > 0 else 0.0


def extract_metrics(result, tech: str) -> dict:
    """
    Extract a flat dictionary of named metrics from a CalculationResult.

    Keys must exactly match the metric names used in scenarios.py Range definitions.
    """
    eng = result.to_domain_outputs_dict().get("engineering_summary", {})
    tp  = result.to_domain_outputs_dict().get("technology_performance", {}).get(tech, {})
    cr  = result.cost_result
    car = result.carbon_result

    return {
        # Cost metrics
        "capex_m":      cr.capex_total / 1e6            if cr else 0,
        "opex_k":       cr.opex_annual / 1e3             if cr else 0,
        "lcc_k":        cr.lifecycle_cost_annual / 1e3   if cr else 0,
        "cost_kl":      cr.specific_cost_per_kl or 0     if cr else 0,

        # Energy
        "kwh_ml":       (eng.get("specific_energy_kwh_kl", 0) or 0) * 1000,

        # Sludge
        "sludge":       eng.get("total_sludge_kgds_day", 0) or 0,

        # Carbon
        "net_co2":      car.net_tco2e_yr if car else 0,

        # Physical
        "footprint_m2": float(tp.get("footprint_m2",   0) or 0),
        "reactor_m3":   float(tp.get("reactor_volume_m3", 0) or 0),

        # Effluent quality
        "eff_bod":  float(tp.get("effluent_bod_mg_l",  0) or 0),
        "eff_tss":  float(tp.get("effluent_tss_mg_l",  0) or 0),
        "eff_tn":   float(tp.get("effluent_tn_mg_l",   0) or 0),
        "eff_nh4":  float(tp.get("effluent_nh4_mg_l",  0) or 0),
        "eff_tp":   float(tp.get("effluent_tp_mg_l",   0) or 0),

        # Risk
        "risk_score": result.risk_result.overall_score if result.risk_result else 0,

        # Carbon — split so Scope 2 (deterministic) can be checked tightly
        # and Scope 1 (N2O model) checked moderately
        "scope2_co2":   car.scope_2_tco2e_yr if car else 0,
        "scope1_co2":   car.scope_1_tco2e_yr if car else 0,

        "kwh_kg_nh4":   _calc_kwh_kg_nh4(tp, eng, result),

        # Sludge disposal OPEX component ($k/yr)
        "sludge_opex_k": sum(
            v for k, v in (result.cost_result.opex_breakdown.items()
                           if result.cost_result else {})
            if "sludge" in k.lower()
        ) / 1e3,
    }
