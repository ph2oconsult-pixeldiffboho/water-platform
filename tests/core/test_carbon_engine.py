"""
tests/core/test_carbon_engine.py
"""

import pytest
from core.project.project_model import AssumptionsSet, DomainType
from core.carbon.carbon_engine import CarbonEngine
from core.assumptions.assumptions_manager import AssumptionsManager


@pytest.fixture
def assumptions():
    return AssumptionsManager().load_defaults(DomainType.WASTEWATER)


@pytest.fixture
def engine(assumptions):
    return CarbonEngine(assumptions)


class TestCarbonEngine:

    def test_zero_inputs_returns_zero_emissions(self, engine):
        result = engine.calculate(
            energy_kwh_per_day=0,
            chemical_consumption={},
        )
        assert result.net_tco2e_yr == 0.0

    def test_electricity_scope2_correct(self, engine):
        # 1000 kWh/day × 0.79 kg/kWh × 365 / 1000 = 288.35 tCO2e/yr
        result = engine.calculate(
            energy_kwh_per_day=1000.0,
            chemical_consumption={},
        )
        assert result.scope_2_tco2e_yr == pytest.approx(288.35, rel=0.01)

    def test_chemical_emissions_sodium_hypochlorite(self, engine):
        result = engine.calculate(
            energy_kwh_per_day=0,
            chemical_consumption={"sodium_hypochlorite": 100.0},
        )
        # 100 kg/day × 2.10 kg CO2e/kg × 365 / 1000 = 76.65 tCO2e/yr
        assert result.scope_3_tco2e_yr == pytest.approx(76.65, rel=0.05)

    def test_avoided_reduces_net(self, engine):
        result_no_avoided = engine.calculate(energy_kwh_per_day=1000.0, chemical_consumption={})
        result_with_avoided = engine.calculate(
            energy_kwh_per_day=1000.0,
            chemical_consumption={},
            avoided_kwh_per_day=200.0,
        )
        assert result_with_avoided.net_tco2e_yr < result_no_avoided.net_tco2e_yr

    def test_specific_intensity_calculated(self, engine):
        result = engine.calculate(
            energy_kwh_per_day=500.0,
            chemical_consumption={},
            design_flow_mld=10.0,
        )
        assert result.specific_kg_co2e_per_kl is not None
        assert result.specific_kg_co2e_per_kl > 0

    def test_carbon_cost_calculated(self, engine):
        result = engine.calculate(energy_kwh_per_day=1000.0, chemical_consumption={})
        # $35/t CO2e
        assert result.carbon_cost_annual == pytest.approx(result.net_tco2e_yr * 35.0, rel=0.01)
