"""
tests/core/test_costing_engine.py

Unit tests for the shared CostingEngine.
These tests are domain-agnostic — no domain modules are imported.
"""

import pytest
from core.project.project_model import AssumptionsSet, CostItem, DomainType
from core.costing.costing_engine import CostingEngine
from core.assumptions.assumptions_manager import AssumptionsManager


@pytest.fixture
def wastewater_assumptions():
    mgr = AssumptionsManager()
    return mgr.load_defaults(DomainType.WASTEWATER)


@pytest.fixture
def engine(wastewater_assumptions):
    return CostingEngine(wastewater_assumptions)


class TestCostingEngineBasic:

    def test_empty_items_returns_zero_cost(self, engine):
        result = engine.calculate(capex_items=[], opex_items=[], design_flow_mld=10.0)
        assert result.capex_total == 0.0
        assert result.opex_annual == 0.0

    def test_capex_item_with_override(self, engine):
        items = [
            CostItem(
                name="Test Tank",
                cost_basis_key="some_key",
                quantity=100.0,
                unit="m³",
                unit_cost_override=1000.0,
            )
        ]
        result = engine.calculate(capex_items=items, opex_items=[], design_flow_mld=10.0)
        # 100 m³ × $1000/m³ × oncosts (~1.20 × 1.12 × 1.15 ≈ 1.547)
        assert result.capex_total > 100_000.0
        assert "Test Tank" in result.capex_breakdown

    def test_opex_item_with_override(self, engine):
        items = [
            CostItem(
                name="Electricity",
                cost_basis_key="electricity_per_kwh",
                quantity=1000.0,   # kWh/day
                unit="kWh/day",
            )
        ]
        result = engine.calculate(capex_items=[], opex_items=items, design_flow_mld=10.0)
        # 1000 kWh/day × $0.14/kWh × 365 = $51,100/yr
        assert result.opex_annual == pytest.approx(51_100.0, rel=0.05)

    def test_specific_cost_per_kl_calculated(self, engine):
        opex_items = [
            CostItem(
                name="Test OPEX",
                cost_basis_key="x",
                quantity=100.0,
                unit="unit/day",
                unit_cost_override=10.0,
            )
        ]
        result = engine.calculate(
            capex_items=[], opex_items=opex_items, design_flow_mld=10.0
        )
        assert result.specific_cost_per_kl is not None
        assert result.specific_cost_per_kl > 0

    def test_analysis_period_affects_lifecycle_cost(self, engine):
        capex_items = [
            CostItem(
                name="Big Asset",
                cost_basis_key="x",
                quantity=1.0,
                unit="lump",
                unit_cost_override=1_000_000.0,
            )
        ]
        result_30 = engine.calculate(capex_items=capex_items, opex_items=[], design_flow_mld=10, analysis_period_years=30, apply_oncosts=False)
        result_20 = engine.calculate(capex_items=capex_items, opex_items=[], design_flow_mld=10, analysis_period_years=20, apply_oncosts=False)
        assert result_20.lifecycle_cost_annual > result_30.lifecycle_cost_annual

    def test_currency_and_year_from_assumptions(self, engine):
        result = engine.calculate([], [], design_flow_mld=5.0)
        assert result.currency == "AUD"
        assert result.price_base_year == 2024


class TestCostingEngineLibraryLookup:

    def test_electricity_cost_looked_up_from_library(self, engine):
        items = [
            CostItem(
                name="Power",
                cost_basis_key="electricity_per_kwh",
                quantity=500.0,
                unit="kWh/day",
            )
        ]
        result = engine.calculate([], items, design_flow_mld=5.0)
        # $0.14/kWh × 500 × 365 = $25,550/yr
        assert result.opex_annual == pytest.approx(25_550.0, rel=0.05)

    def test_unknown_cost_key_returns_zero(self, engine):
        items = [
            CostItem(
                name="Unknown Widget",
                cost_basis_key="nonexistent_key_xyz",
                quantity=100.0,
                unit="unit",
            )
        ]
        result = engine.calculate(items, [], design_flow_mld=5.0)
        # Zero unit cost → zero item cost
        assert result.capex_breakdown.get("Unknown Widget", 0.0) == 0.0
