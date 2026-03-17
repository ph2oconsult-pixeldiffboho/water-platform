"""
tests/core/test_qa_engine.py

QA Engine test suite — verifies that each rule fires correctly
on both passing and failing inputs.

Run: python3 tests/core/test_qa_engine.py
"""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.qa.qa_model import QAFinding, QAResult, Severity
from core.qa.qa_engine import validate_inputs, validate_scenario, validate_project, validate_report
from core.qa.rules import input_rules, mass_energy_rules, cost_rules, sludge_rules

passed = failed = 0
failures = []

def chk(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  ✅ {name}")
    else:
        failed += 1
        failures.append((name, detail))
        print(f"  ❌ {name}" + (f"  [{detail[:80]}]" if detail else ""))


def _make_scenario(tech="bnr", flow=10.0, bod=250, tkn=45, nh4=35, tss=280,
                   eff_tn=10, eff_nh4=1, eff_tp=0.5, elec=0.14, sludge_cost=280):
    from tests.benchmark.conftest import base_assumptions as mk_a
    from domains.wastewater.domain_interface import WastewaterDomainInterface
    from domains.wastewater.input_model import WastewaterInputs
    from core.project.project_model import ScenarioModel, TreatmentPathway
    from domains.wastewater.decision_engine import _TECH_LABELS

    base_a = mk_a()
    iface = WastewaterDomainInterface(base_a)
    inp = WastewaterInputs(
        design_flow_mld=flow, influent_bod_mg_l=bod, influent_tkn_mg_l=tkn,
        influent_nh4_mg_l=nh4, influent_tss_mg_l=tss,
        effluent_tn_mg_l=eff_tn, effluent_nh4_mg_l=eff_nh4, effluent_tp_mg_l=eff_tp,
        electricity_price_per_kwh=elec,
        sludge_disposal_cost_per_tonne_ds=sludge_cost,
    )
    calc = iface.run_scenario(inp, [tech], {})
    label = _TECH_LABELS.get(tech, tech)
    sc = ScenarioModel(scenario_name=label)
    sc.treatment_pathway = TreatmentPathway(
        pathway_name=tech, technology_sequence=[tech], technology_parameters={})
    sc.domain_inputs = {k: getattr(inp, k)
                        for k in inp.__dataclass_fields__ if not k.startswith("_")}
    iface.update_scenario_model(sc, calc)
    return sc, inp


# ── QAModel tests ─────────────────────────────────────────────────────────────

class TestQAModel:

    def test_qafinding_str(self):
        f = QAFinding("E1", "Energy", Severity.FAIL, "Test message", scenario="BNR")
        chk("QAFinding str includes icon and code",
            "❌" in str(f) and "E1" in str(f) and "BNR" in str(f))

    def test_qaresult_counts(self):
        r = QAResult(findings=[
            QAFinding("X1", "Test", Severity.FAIL, "fail"),
            QAFinding("X2", "Test", Severity.WARN, "warn"),
            QAFinding("X3", "Test", Severity.INFO, "info"),
        ])
        chk("fail_count=1", r.fail_count == 1)
        chk("warn_count=1", r.warn_count == 1)
        chk("info_count=1", r.info_count == 1)
        chk("passed=False when FAIL exists", not r.passed)
        chk("export_ready=False when FAIL exists", not r.export_ready)

    def test_qaresult_passed(self):
        r = QAResult(findings=[QAFinding("X1","T",Severity.WARN,"w")])
        chk("passed=True when only WARN", r.passed)
        chk("export_ready=True when only WARN", r.export_ready)

    def test_qaresult_merge(self):
        r1 = QAResult(findings=[QAFinding("X1","T",Severity.FAIL,"f")])
        r2 = QAResult(findings=[QAFinding("X2","T",Severity.WARN,"w")])
        merged = r1.merge(r2)
        chk("merge combines findings", len(merged.findings) == 2)
        chk("merge: fail_count correct", merged.fail_count == 1)

    def test_by_scenario(self):
        r = QAResult(findings=[
            QAFinding("X1","T",Severity.FAIL,"f", scenario="BNR"),
            QAFinding("X2","T",Severity.WARN,"w", scenario="AGS"),
        ])
        bnr = r.by_scenario("BNR")
        chk("by_scenario filters correctly", len(bnr.findings) == 1)
        chk("by_scenario: correct scenario", bnr.findings[0].scenario == "BNR")


# ── Input rules ───────────────────────────────────────────────────────────────

class TestInputRules:

    def test_valid_inputs_pass(self):
        inputs = dict(design_flow_mld=10, influent_bod_mg_l=250, influent_tkn_mg_l=45,
                      influent_nh4_mg_l=35, influent_tss_mg_l=280, effluent_tn_mg_l=10,
                      effluent_nh4_mg_l=1, effluent_tp_mg_l=0.5,
                      electricity_price_per_kwh=0.14, influent_temperature_celsius=20.0)
        r = validate_inputs(inputs, "Test")
        chk("Valid inputs: no FAIL", r.fail_count == 0,
            f"fails={[str(f) for f in r.fails()]}")

    def test_missing_flow_fails(self):
        r = validate_inputs({"influent_bod_mg_l": 250}, "Test")
        chk("Missing flow → FAIL", r.fail_count > 0)

    def test_cod_less_than_bod_fails(self):
        r = validate_inputs(dict(
            design_flow_mld=10, influent_bod_mg_l=250, influent_cod_mg_l=100,
            influent_tkn_mg_l=45, influent_nh4_mg_l=35, influent_tss_mg_l=280,
            effluent_tn_mg_l=10, effluent_nh4_mg_l=1, effluent_tp_mg_l=0.5,
            electricity_price_per_kwh=0.14,
        ), "Test")
        chk("COD < BOD → FAIL [I1]",
            any(f.code == "I1" and f.severity == Severity.FAIL for f in r.findings))

    def test_nh4_greater_than_tkn_fails(self):
        r = validate_inputs(dict(
            design_flow_mld=10, influent_bod_mg_l=250, influent_tkn_mg_l=30,
            influent_nh4_mg_l=40, influent_tss_mg_l=280,
            effluent_tn_mg_l=10, effluent_nh4_mg_l=1, effluent_tp_mg_l=0.5,
            electricity_price_per_kwh=0.14,
        ), "Test")
        chk("NH4 > TKN → FAIL [I2]",
            any(f.code == "I2" and f.severity == Severity.FAIL for f in r.findings))

    def test_cold_temperature_warns(self):
        r = validate_inputs(dict(
            design_flow_mld=10, influent_bod_mg_l=250, influent_tkn_mg_l=45,
            influent_nh4_mg_l=35, influent_tss_mg_l=280,
            effluent_tn_mg_l=10, effluent_nh4_mg_l=1, effluent_tp_mg_l=0.5,
            electricity_price_per_kwh=0.14,
            influent_temperature_celsius=11.0,
        ), "Test")
        chk("Temperature 11°C → WARN [I5]",
            any(f.code == "I5" and f.severity == Severity.WARN for f in r.findings))

    def test_low_cod_tkn_warns(self):
        r = validate_inputs(dict(
            design_flow_mld=10, influent_bod_mg_l=120, influent_cod_mg_l=240,
            influent_tkn_mg_l=60, influent_nh4_mg_l=48, influent_tss_mg_l=200,
            effluent_tn_mg_l=10, effluent_nh4_mg_l=1, effluent_tp_mg_l=0.5,
            electricity_price_per_kwh=0.14, influent_temperature_celsius=20.0,
        ), "Test")
        chk("COD:TKN=4.0 < 4.5 → WARN [I4]",
            any(f.code == "I4" for f in r.findings))


# ── Cost rules ────────────────────────────────────────────────────────────────

class TestCostRules:

    def test_normal_scenario_passes_k2(self):
        sc, _ = _make_scenario()
        r = validate_scenario(sc, "bnr")
        k2_fails = [f for f in r.findings if f.code == "K2"]
        chk("Normal BNR scenario: LCC formula correct (K2 passes)",
            len(k2_fails) == 0,
            f"K2 findings: {[str(f) for f in k2_fails]}")

    def test_opex_capex_ratio_detected(self):
        """Manufacture a scenario with absurd OPEX to test K4"""
        sc, _ = _make_scenario()
        # Inject broken OPEX
        from core.project.project_model import CostResult
        original = sc.cost_result
        sc.cost_result = CostResult(
            capex_total=original.capex_total,
            opex_annual=original.capex_total * 0.50,  # 50% of CAPEX/yr — impossible
            lifecycle_cost_annual=original.lifecycle_cost_annual,
            specific_cost_per_kl=original.specific_cost_per_kl,
            cost_confidence=original.cost_confidence,
        )
        r = cost_rules.run(sc)
        chk("OPEX=50% of CAPEX/yr → FAIL [K4]",
            any(f.code == "K4" and f.severity == Severity.FAIL for f in r.findings))
        sc.cost_result = original  # restore

    def test_zero_capex_fails(self):
        sc, _ = _make_scenario()
        from core.project.project_model import CostResult
        original = sc.cost_result
        sc.cost_result = CostResult(capex_total=0, opex_annual=500000,
            lifecycle_cost_annual=500000, specific_cost_per_kl=0.15,
            cost_confidence="±40%")
        r = cost_rules.run(sc)
        chk("Zero CAPEX → FAIL [K1]",
            any(f.code == "K1" and f.severity == Severity.FAIL for f in r.findings))
        sc.cost_result = original


# ── Sludge rules ──────────────────────────────────────────────────────────────

class TestSludgeRules:

    def test_normal_sludge_passes(self):
        sc, _ = _make_scenario()
        r = sludge_rules.run(sc, "bnr")
        s2_fails = [f for f in r.findings if f.code == "S2" and f.severity == Severity.FAIL]
        chk("Normal BNR: no S2 sludge mismatch FAIL",
            len(s2_fails) == 0,
            f"S2 fails: {[str(f) for f in s2_fails]}")

    def test_sludge_mismatch_detected(self):
        """Inject a mismatch between summary and detail sludge values"""
        sc, _ = _make_scenario()
        # Inject discrepancy into engineering_summary
        original_outputs = sc.domain_specific_outputs.copy()
        sc.domain_specific_outputs = dict(sc.domain_specific_outputs)
        eng = dict(sc.domain_specific_outputs.get("engineering_summary", {}))
        tp = dict(sc.domain_specific_outputs.get("technology_performance", {}))
        bnr_tp = dict(tp.get("bnr", {}))
        bnr_tp["sludge_production_kgds_day"] = 1478  # detail
        eng["total_sludge_kgds_day"] = 3598          # summary 2.4× different → FAIL
        tp["bnr"] = bnr_tp
        sc.domain_specific_outputs["engineering_summary"] = eng
        sc.domain_specific_outputs["technology_performance"] = tp

        r = sludge_rules.run(sc, "bnr")
        chk("Sludge mismatch 1478 vs 3598 → FAIL [S2]",
            any(f.code == "S2" and f.severity == Severity.FAIL for f in r.findings),
            f"findings: {[str(f) for f in r.findings]}")
        sc.domain_specific_outputs = original_outputs


# ── Energy rules ──────────────────────────────────────────────────────────────

class TestEnergyRules:

    def test_normal_energy_passes_e2(self):
        sc, _ = _make_scenario()
        r = mass_energy_rules.run(sc, "bnr")
        e2_fails = [f for f in r.findings if f.code == "E2" and f.severity == Severity.FAIL]
        chk("Normal BNR energy within benchmark (E2 no FAIL)",
            len(e2_fails) == 0,
            f"E2 findings: {[str(f) for f in r.fails()]}")

    def test_mbr_energy_in_range(self):
        sc, _ = _make_scenario(tech="bnr_mbr")
        r = mass_energy_rules.run(sc, "bnr_mbr")
        e2_fails = [f for f in r.findings if f.code == "E2" and f.severity == Severity.FAIL]
        chk("MBR energy within benchmark (E2 no FAIL)",
            len(e2_fails) == 0,
            f"E2 findings: {[str(f) for f in e2_fails]}")


# ── Project-level QA ──────────────────────────────────────────────────────────

class TestProjectQA:

    def test_two_compliant_scenarios_pass(self):
        sc1, _ = _make_scenario("bnr")
        sc2, _ = _make_scenario("granular_sludge")
        from domains.wastewater.decision_engine import evaluate_scenario
        dec = evaluate_scenario([sc1, sc2])
        r = validate_project([sc1, sc2], dec)
        chk("Two normal scenarios: project QA passes",
            r.passed, f"fails: {[str(f) for f in r.fails()]}")

    def test_preferred_noncompliant_fails(self):
        """Mark a non-compliant scenario as preferred → should FAIL"""
        sc, _ = _make_scenario("bnr", eff_tp=0.5)  # BNR gives TP=0.8, target 0.5
        sc.is_preferred = True
        # Manually set compliance issues to simulate the flag
        tp = sc.domain_specific_outputs.get("technology_performance", {}).get("bnr", {})
        tp["compliance_flag"] = "Review Required"
        tp["compliance_issues"] = ["TP: 0.8 > target 0.5"]
        r = validate_project([sc])
        chk("Preferred non-compliant scenario → FAIL [C1]",
            any(f.code == "C1" and f.severity == Severity.FAIL for f in r.findings),
            f"findings: {[str(f) for f in r.findings]}")
        sc.is_preferred = False  # restore


# ── Report QA ─────────────────────────────────────────────────────────────────

class TestReportQA:

    def test_report_none_fails(self):
        r = validate_report(None)
        chk("None report → FAIL", r.fail_count > 0)

    def test_placeholder_name_warns(self):
        """Project name 'Test' should trigger R1 WARN"""
        from core.reporting.report_engine import ReportEngine
        from core.project.project_model import DomainType, ProjectModel, ProjectMetadata
        from tests.benchmark.conftest import base_assumptions as mk_a
        from domains.wastewater.domain_interface import WastewaterDomainInterface
        from domains.wastewater.input_model import WastewaterInputs
        from core.project.project_model import ScenarioModel, TreatmentPathway
        from domains.wastewater.decision_engine import _TECH_LABELS

        base_a = mk_a()
        iface = WastewaterDomainInterface(base_a)
        inp = WastewaterInputs(design_flow_mld=10, influent_bod_mg_l=250,
                               influent_tkn_mg_l=45, influent_nh4_mg_l=35)
        project = ProjectModel(metadata=ProjectMetadata(
            project_name="TEST", domain=DomainType.WASTEWATER))
        calc = iface.run_scenario(inp, ["bnr"], {})
        sc = ScenarioModel(scenario_name="BNR")
        sc.treatment_pathway = TreatmentPathway(pathway_name="bnr",
            technology_sequence=["bnr"], technology_parameters={})
        sc.domain_inputs = {k: getattr(inp, k)
                            for k in inp.__dataclass_fields__ if not k.startswith("_")}
        iface.update_scenario_model(sc, calc)
        project.scenarios["BNR"] = sc

        report = ReportEngine().build_report(project)
        r = validate_report(report, project)
        chk("Project name 'TEST' → WARN [R1]",
            any(f.code == "R1" and f.severity == Severity.WARN for f in r.findings),
            f"R1 findings: {[f for f in r.findings if f.code == 'R1']}")

    def test_good_report_passes(self):
        from core.reporting.report_engine import ReportEngine
        from core.project.project_model import DomainType, ProjectModel, ProjectMetadata
        from tests.benchmark.conftest import base_assumptions as mk_a
        from domains.wastewater.domain_interface import WastewaterDomainInterface
        from domains.wastewater.input_model import WastewaterInputs
        from core.project.project_model import ScenarioModel, TreatmentPathway

        base_a = mk_a()
        iface = WastewaterDomainInterface(base_a)
        inp = WastewaterInputs(design_flow_mld=10, influent_bod_mg_l=250,
                               influent_tkn_mg_l=45, influent_nh4_mg_l=35)
        project = ProjectModel(metadata=ProjectMetadata(
            project_name="Werribee WWTP Upgrade 2025",
            domain=DomainType.WASTEWATER, plant_name="Werribee"))
        calc = iface.run_scenario(inp, ["bnr"], {})
        sc = ScenarioModel(scenario_name="BNR Baseline")
        sc.treatment_pathway = TreatmentPathway(pathway_name="bnr",
            technology_sequence=["bnr"], technology_parameters={})
        sc.domain_inputs = {k: getattr(inp, k)
                            for k in inp.__dataclass_fields__ if not k.startswith("_")}
        iface.update_scenario_model(sc, calc)
        project.scenarios["BNR"] = sc

        report = ReportEngine().build_report(project)
        r = validate_report(report, project)
        chk("Good report: no FAIL findings",
            r.fail_count == 0,
            f"fails: {[str(f) for f in r.fails()]}")


# ── Runner ────────────────────────────────────────────────────────────────────

def run_all():
    for cls in [TestQAModel, TestInputRules, TestCostRules,
                TestSludgeRules, TestEnergyRules,
                TestProjectQA, TestReportQA]:
        print(f"\n  {cls.__name__}")
        obj = cls()
        for name in [m for m in dir(obj) if m.startswith("test_")]:
            try:
                getattr(obj, name)()
            except Exception as e:
                failed_count = globals()["failed"]
                globals()["failed"] = failed_count + 1
                failures.append((f"{cls.__name__}.{name}", str(e)))
                print(f"  ❌ {name}  [EXCEPTION: {str(e)[:80]}]")
                import traceback; traceback.print_exc()


if __name__ == "__main__":
    print("=" * 60)
    print("  QA ENGINE TEST SUITE")
    print("=" * 60)
    run_all()
    print()
    print("=" * 60)
    total = passed + failed
    print(f"  RESULTS: {passed}/{total} passed  ({failed} failed)")
    if failures:
        print("\n  FAILURES:")
        for name, detail in failures:
            print(f"    ❌ {name}")
            if detail: print(f"       {detail[:100]}")
    else:
        print("  ✅ ALL QA ENGINE TESTS PASSED")
    print("=" * 60)
    import sys; sys.exit(0 if failed == 0 else 1)
