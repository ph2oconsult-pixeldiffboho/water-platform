"""
tests/domains/wastewater/test_bnr_technology.py

Unit tests for the BNR technology plugin.
Tests are against known engineering benchmarks.
"""

import pytest
from core.project.project_model import DomainType
from core.assumptions.assumptions_manager import AssumptionsManager
from domains.wastewater.technologies.bnr import BNRTechnology, BNRInputs


@pytest.fixture
def assumptions():
    return AssumptionsManager().load_defaults(DomainType.WASTEWATER)


@pytest.fixture
def bnr(assumptions):
    return BNRTechnology(assumptions)


@pytest.fixture
def default_inputs():
    return BNRInputs(
        process_configuration="a2o",
        srt_days=12.0,
        mlss_mg_l=4000.0,
        do_aerobic_mg_l=2.0,
    )


class TestBNRTechnology:

    def test_technology_code(self, bnr):
        assert bnr.technology_code == "bnr"

    def test_technology_name(self, bnr):
        assert "BNR" in bnr.technology_name or "Biological" in bnr.technology_name

    def test_returns_technology_result(self, bnr, default_inputs):
        result = bnr.calculate(design_flow_mld=10.0, inputs=default_inputs)
        assert result is not None
        assert result.technology_code == "bnr"

    def test_positive_energy_consumption(self, bnr, default_inputs):
        result = bnr.calculate(design_flow_mld=10.0, inputs=default_inputs)
        assert result.energy_kwh_per_day > 0

    def test_energy_scales_with_flow(self, bnr, default_inputs):
        result_10 = bnr.calculate(design_flow_mld=10.0, inputs=default_inputs)
        result_20 = bnr.calculate(design_flow_mld=20.0, inputs=default_inputs)
        assert result_20.energy_kwh_per_day > result_10.energy_kwh_per_day

    def test_sludge_production_positive(self, bnr, default_inputs):
        result = bnr.calculate(design_flow_mld=10.0, inputs=default_inputs)
        sludge = result.performance_outputs.get("sludge_production_kgds_day", 0)
        assert sludge > 0

    def test_longer_srt_reduces_sludge_yield(self, bnr):
        inputs_short = BNRInputs(srt_days=5.0)
        inputs_long = BNRInputs(srt_days=20.0)
        result_short = bnr.calculate(10.0, inputs_short)
        result_long = bnr.calculate(10.0, inputs_long)
        sludge_short = result_short.performance_outputs.get("sludge_production_kgds_day", 0)
        sludge_long = result_long.performance_outputs.get("sludge_production_kgds_day", 0)
        assert sludge_long < sludge_short

    def test_reactor_volume_positive(self, bnr, default_inputs):
        result = bnr.calculate(10.0, default_inputs)
        assert result.performance_outputs.get("reactor_volume_m3", 0) > 0

    def test_capex_items_populated(self, bnr, default_inputs):
        result = bnr.calculate(10.0, default_inputs)
        assert len(result.capex_items) > 0

    def test_opex_items_populated(self, bnr, default_inputs):
        result = bnr.calculate(10.0, default_inputs)
        assert len(result.opex_items) > 0

    def test_process_emissions_populated(self, bnr, default_inputs):
        result = bnr.calculate(10.0, default_inputs)
        assert len(result.process_emissions_tco2e_yr) > 0
        # N2O must be present
        assert any("n2o" in k.lower() for k in result.process_emissions_tco2e_yr)

    def test_supplemental_carbon_adds_methanol(self, bnr):
        inputs_no_c = BNRInputs(supplemental_carbon=False)
        inputs_with_c = BNRInputs(supplemental_carbon=True)
        result_no = bnr.calculate(10.0, inputs_no_c)
        result_with = bnr.calculate(10.0, inputs_with_c)
        assert "methanol_kg_day" not in result_no.chemical_consumption
        assert "methanol_kg_day" in result_with.chemical_consumption

    def test_chemical_p_removal_adds_coagulant(self, bnr):
        inputs = BNRInputs(chemical_p_removal=True, coagulant="ferric_chloride")
        result = bnr.calculate(10.0, inputs)
        assert "ferric_chloride_kg_day" in result.chemical_consumption

    def test_assumptions_used_recorded(self, bnr, default_inputs):
        result = bnr.calculate(10.0, default_inputs)
        assert "srt_days" in result.assumptions_used
        assert result.assumptions_used["srt_days"] == default_inputs.srt_days


class TestMBRTechnology:

    def test_mbr_basic_calculation(self, assumptions):
        from domains.wastewater.technologies.mbr import MBRTechnology, MBRInputs
        mbr = MBRTechnology(assumptions)
        inputs = MBRInputs(design_flux_lmh=25.0, srt_days=15.0, mlss_mg_l=10000.0)
        result = mbr.calculate(10.0, inputs)
        assert result.technology_code == "mbr"
        assert result.energy_kwh_per_day > 0
        mem_area = result.performance_outputs.get("membrane_area_m2", 0)
        assert mem_area > 0

    def test_lower_flux_increases_membrane_area(self, assumptions):
        from domains.wastewater.technologies.mbr import MBRTechnology, MBRInputs
        mbr = MBRTechnology(assumptions)
        high_flux = mbr.calculate(10.0, MBRInputs(design_flux_lmh=35.0))
        low_flux = mbr.calculate(10.0, MBRInputs(design_flux_lmh=15.0))
        assert (
            low_flux.performance_outputs["membrane_area_m2"]
            > high_flux.performance_outputs["membrane_area_m2"]
        )
