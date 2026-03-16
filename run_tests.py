#!/usr/bin/env python3
"""
run_tests.py — Run the platform test suite without pytest.
Usage: python3 run_tests.py
"""

import sys, traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

results = []

def run(name, fn):
    try:
        fn()
        results.append(("PASS", name))
        print(f"  ✅  {name}")
    except Exception as e:
        results.append(("FAIL", name, str(e)))
        print(f"  ❌  {name}")
        print(f"       └─ {e}")

print("\n" + "="*72)
print("  WATER UTILITY PLANNING PLATFORM — TEST SUITE")
print("="*72)

# Import all test modules and collect test functions
from tests.core.test_costing_engine import TestCostingEngineBasic, TestCostingEngineLibraryLookup
from tests.core.test_carbon_engine import TestCarbonEngine
from tests.domains.wastewater.test_bnr_mbr import TestBNRTechnology, TestMBRTechnology
from tests.integration.test_wastewater_full_run import TestBNRFullRun

import pytest as _pytest

print("\nNote: For full pytest output, run: python3 -m pytest tests/ -v\n")
print("Quick verification that core imports and classes are healthy:\n")

def t_imports():
    from core.project.project_model import ProjectModel, DomainType, CostResult, CarbonResult, RiskResult
    from core.project.project_manager import ProjectManager, ScenarioManager
    from core.assumptions.assumptions_manager import AssumptionsManager
    from core.costing.costing_engine import CostingEngine
    from core.carbon.carbon_engine import CarbonEngine
    from core.risk.risk_engine import RiskEngine
    from core.validation.validation_engine import ValidationEngine
    from core.reporting.report_engine import ReportEngine
    from domains.wastewater.domain_interface import WastewaterDomainInterface
    from domains.wastewater.technologies.bnr import BNRTechnology
    from domains.wastewater.technologies.mbr import MBRTechnology
run("All core and domain modules import without error", t_imports)

def t_bnr_smoke():
    from core.project.project_model import DomainType
    from core.assumptions.assumptions_manager import AssumptionsManager
    from domains.wastewater.technologies.bnr import BNRTechnology, BNRInputs
    bnr = BNRTechnology(AssumptionsManager().load_defaults(DomainType.WASTEWATER))
    r = bnr.calculate(10.0, BNRInputs())
    assert r.energy_kwh_per_day > 0 and r.performance_outputs["sludge_production_kgds_day"] > 0
run("BNR technology smoke test (10 ML/day)", t_bnr_smoke)

def t_full_pipeline():
    from core.project.project_model import DomainType
    from core.assumptions.assumptions_manager import AssumptionsManager
    from domains.wastewater.domain_interface import WastewaterDomainInterface
    from domains.wastewater.input_model import WastewaterInputs
    iface = WastewaterDomainInterface(AssumptionsManager().load_defaults(DomainType.WASTEWATER))
    r = iface.run_scenario(WastewaterInputs(design_flow_mld=10.0), ["bnr"], {})
    assert r.is_valid
    assert r.cost_result.capex_total > 0
    assert r.carbon_result.net_tco2e_yr > 0
    assert r.risk_result.overall_level in ("Low","Medium","High","Very High")
run("Full BNR pipeline (inputs → cost → carbon → risk)", t_full_pipeline)

print("\n" + "="*72)
passed = sum(1 for r in results if r[0] == "PASS")
failed = sum(1 for r in results if r[0] == "FAIL")
print(f"  {passed} passed  |  {failed} failed  |  {len(results)} total")
print("="*72 + "\n")
sys.exit(0 if failed == 0 else 1)
