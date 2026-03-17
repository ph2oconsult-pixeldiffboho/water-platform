"""
core/qa/qa_engine.py

Central QA orchestrator for the wastewater planning platform.

Three entry points:
  validate_inputs(inputs_dict, scenario_name)   → QAResult  (pre-run)
  validate_scenario(scenario, tech_code)         → QAResult  (post-run)
  validate_report(report, project, decision,
                  scenarios)                     → QAResult  (pre-export)
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional

from core.qa.qa_model import QAFinding, QAResult, Severity
from core.qa.rules import (
    input_rules,
    mass_energy_rules,
    sludge_rules,
    compliance_rules,
    cost_rules,
    carbon_rules,
    decision_rules,
    report_rules,
    differentiation_rules,
)


def validate_inputs(
    inputs: Dict[str, Any],
    scenario_name: str = None,
) -> QAResult:
    """
    Pre-run validation.
    Call before running engineering calculations.
    Returns FAIL if required fields missing or physically impossible.
    """
    return input_rules.run(inputs, scenario_name)


def validate_scenario(
    scenario: Any,
    tech_code: str = None,
) -> QAResult:
    """
    Post-run scenario validation.
    Call after engineering calculations are complete on a ScenarioModel.
    Checks mass/energy, sludge, compliance, cost, and carbon.
    """
    if tech_code is None:
        # Infer from treatment pathway
        tp = getattr(scenario, "treatment_pathway", None)
        if tp and getattr(tp, "technology_sequence", None):
            tech_code = tp.technology_sequence[0]

    result = QAResult()
    result = result.merge(mass_energy_rules.run(scenario, tech_code))
    result = result.merge(sludge_rules.run(scenario, tech_code))
    result = result.merge(compliance_rules.run(scenario, tech_code))
    result = result.merge(cost_rules.run(scenario))
    result = result.merge(carbon_rules.run(scenario, tech_code))
    return result


def validate_project(
    scenarios: List[Any],
    decision: Any = None,
) -> QAResult:
    """
    Project-level validation across all scenarios.
    Checks cross-scenario consistency and decision logic.
    """
    result = QAResult()

    # Per-scenario checks
    for sc in scenarios:
        tp = getattr(sc, "treatment_pathway", None)
        tech_code = (tp.technology_sequence[0]
                     if tp and getattr(tp, "technology_sequence", None) else None)
        result = result.merge(validate_scenario(sc, tech_code))

    # Technology differentiation checks (T1-T4)
    result = result.merge(differentiation_rules.run(scenarios))

    # Decision logic checks
    if decision:
        result = result.merge(decision_rules.run(decision, scenarios))

    # Cross-scenario energy directionality
    result = result.merge(_cross_scenario_checks(scenarios))

    return result


def validate_report(
    report: Any,
    project: Any = None,
    decision: Any = None,
    scenarios: List[Any] = None,
) -> QAResult:
    """
    Pre-export validation. Blocks export if FAIL findings present.
    """
    result = QAResult()
    result = result.merge(report_rules.run(report, project))
    if scenarios and decision:
        result = result.merge(decision_rules.run(decision, scenarios))
    return result


def _cross_scenario_checks(scenarios: List[Any]) -> QAResult:
    """
    Cross-scenario checks that can't be done on individual scenarios.
    Currently: energy directionality between technologies.
    """
    findings = []

    # Identify tech codes and energies
    tech_energies = {}
    for sc in scenarios:
        eng = (sc.domain_specific_outputs or {}).get("engineering_summary", {}) if sc.domain_specific_outputs else {}
        kwh_kl = eng.get("specific_energy_kwh_kl") or 0
        scope2  = sc.carbon_result.scope_2_tco2e_yr if sc.carbon_result else 0
        tp = getattr(sc, "treatment_pathway", None)
        tc = (tp.technology_sequence[0]
              if tp and getattr(tp, "technology_sequence", None) else None)
        if tc:
            tech_energies[tc] = {
                "kwh_ml": kwh_kl * 1000,
                "scope2": scope2,
                "name": sc.scenario_name,
            }

    # G2: If energy A > energy B but scope2 A < scope2 B → mismatch
    techs = list(tech_energies.items())
    for i in range(len(techs)):
        for j in range(i + 1, len(techs)):
            tc_a, a = techs[i]
            tc_b, b = techs[j]
            if a["kwh_ml"] > 0 and b["kwh_ml"] > 0 and a["scope2"] > 0 and b["scope2"] > 0:
                # A has more energy but less scope2 than B → inconsistent
                if a["kwh_ml"] > b["kwh_ml"] * 1.10 and a["scope2"] < b["scope2"] * 0.90:
                    findings.append(QAFinding(
                        code="G2", category="Carbon", severity=Severity.WARN,
                        message=(
                            f"{a['name']} uses more energy ({a['kwh_ml']:.0f} kWh/ML) "
                            f"than {b['name']} ({b['kwh_ml']:.0f} kWh/ML) but has "
                            f"lower Scope 2 emissions ({a['scope2']:.0f} vs {b['scope2']:.0f} tCO₂e/yr). "
                            "Carbon and energy results are inconsistent."
                        ),
                        metric="scope_2_tco2e_yr",
                        rec="Check grid emission factor is applied consistently to both scenarios",
                    ))

    return QAResult(findings=findings)
