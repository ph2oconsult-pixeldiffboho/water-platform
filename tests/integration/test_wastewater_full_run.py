"""
tests/integration/test_wastewater_full_run.py

Integration tests: full scenario pipeline from inputs → domain interface
→ core engines → results.
"""

import pytest
from core.project.project_model import DomainType, ScenarioType
from core.project.project_manager import ProjectManager, ScenarioManager
from core.assumptions.assumptions_manager import AssumptionsManager
from domains.wastewater.domain_interface import WastewaterDomainInterface
from domains.wastewater.input_model import WastewaterInputs


@pytest.fixture
def assumptions():
    return AssumptionsManager().load_defaults(DomainType.WASTEWATER)


@pytest.fixture
def standard_inputs():
    return WastewaterInputs(
        design_flow_mld=10.0,
        influent_bod_mg_l=250.0,
        influent_tn_mg_l=45.0,
        influent_tp_mg_l=7.0,
        effluent_bod_mg_l=10.0,
        effluent_tn_mg_l=10.0,
        effluent_tp_mg_l=0.5,
    )


class TestBNRFullRun:

    def test_bnr_full_scenario_produces_all_results(self, assumptions, standard_inputs):
        interface = WastewaterDomainInterface(assumptions)
        result = interface.run_scenario(
            inputs=standard_inputs,
            technology_sequence=["bnr"],
            technology_parameters={"bnr": {"srt_days": 12.0, "mlss_mg_l": 4000.0}},
        )
        assert result.is_valid
        assert result.cost_result is not None
        assert result.carbon_result is not None
        assert result.risk_result is not None
        assert result.validation_result is not None

    def test_bnr_capex_in_reasonable_range_for_10mld(self, assumptions, standard_inputs):
        """CAPEX for a 10 ML/day BNR plant should be ~$10–80M at concept stage."""
        interface = WastewaterDomainInterface(assumptions)
        result = interface.run_scenario(
            inputs=standard_inputs,
            technology_sequence=["bnr"],
            technology_parameters={"bnr": {}},
        )
        capex = result.cost_result.capex_total
        assert 5_000_000 < capex < 150_000_000, f"Unexpected CAPEX: ${capex:,.0f}"

    def test_mbr_full_scenario(self, assumptions, standard_inputs):
        interface = WastewaterDomainInterface(assumptions)
        result = interface.run_scenario(
            inputs=standard_inputs,
            technology_sequence=["mbr"],
            technology_parameters={"mbr": {"design_flux_lmh": 25.0}},
        )
        assert result.is_valid
        assert result.cost_result.capex_total > 0
        assert result.carbon_result.net_tco2e_yr > 0

    def test_missing_design_flow_fails_validation(self, assumptions):
        bad_inputs = WastewaterInputs(design_flow_mld=None)
        interface = WastewaterDomainInterface(assumptions)
        result = interface.run_scenario(
            inputs=bad_inputs,
            technology_sequence=["bnr"],
            technology_parameters={},
        )
        assert not result.is_valid
        assert result.cost_result is None

    def test_invalid_effluent_target_fails_validation(self, assumptions):
        """Effluent TN > Influent TN should fail validation."""
        bad_inputs = WastewaterInputs(
            design_flow_mld=10.0,
            influent_tn_mg_l=10.0,
            effluent_tn_mg_l=15.0,  # Higher than influent — impossible
        )
        interface = WastewaterDomainInterface(assumptions)
        result = interface.run_scenario(
            inputs=bad_inputs,
            technology_sequence=["bnr"],
            technology_parameters={},
        )
        assert not result.is_valid

    def test_project_round_trip_with_results(self, assumptions, standard_inputs, tmp_path):
        """Full project save/load round trip preserving calculation results."""
        pm = ProjectManager(storage_path=tmp_path)
        project = pm.create_project(
            project_name="Test WWTP",
            domain=DomainType.WASTEWATER,
            plant_name="Test Plant",
            author="Test Engineer",
        )

        scenario = project.get_active_scenario()
        scenario.domain_inputs = {
            k: getattr(standard_inputs, k)
            for k in standard_inputs.__dataclass_fields__
            if not k.startswith("_")
        }
        scenario.design_flow_mld = standard_inputs.design_flow_mld
        scenario.assumptions = assumptions

        from core.project.project_model import TreatmentPathway
        scenario.treatment_pathway = TreatmentPathway(
            pathway_name="BNR",
            technology_sequence=["bnr"],
            technology_parameters={"bnr": {}},
        )

        interface = WastewaterDomainInterface(assumptions)
        calc_result = interface.run_scenario(
            inputs=standard_inputs,
            technology_sequence=["bnr"],
            technology_parameters={"bnr": {}},
        )
        interface.update_scenario_model(scenario, calc_result)

        # Save and reload
        pm.save(project)
        loaded_project = pm.load(project.metadata.project_id)
        loaded_scenario = loaded_project.get_active_scenario()

        assert loaded_scenario.cost_result is not None
        assert loaded_scenario.cost_result.capex_total == pytest.approx(
            scenario.cost_result.capex_total, rel=0.001
        )
        assert not loaded_scenario.is_stale
