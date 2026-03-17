"""
core/qa/rules/compliance_rules.py
Effluent compliance, preferred-option logic, and decision consistency checks.
"""
from __future__ import annotations
from core.qa.qa_model import QAFinding, QAResult, Severity


def run(scenario, tech_code: str = None) -> QAResult:
    findings = []
    sn = getattr(scenario, "scenario_name", None)
    di = scenario.domain_inputs or {}
    tp = (scenario.domain_specific_outputs or {}).get("technology_performance", {})
    tech_perf = tp.get(tech_code, {}) if tech_code else {}

    def f(code, sev, msg, metric=None, expected=None, actual=None, rec=None):
        findings.append(QAFinding(
            code=code, category="Compliance", severity=sev, message=msg,
            scenario=sn, metric=metric, expected=expected, actual=actual,
            recommendation=rec,
        ))

    # Targets
    target_tn  = di.get("effluent_tn_mg_l")  or 0
    target_nh4 = di.get("effluent_nh4_mg_l") or 0
    target_tp  = di.get("effluent_tp_mg_l")  or 0

    # Actual effluent
    eff_tn  = tech_perf.get("effluent_tn_mg_l")
    eff_nh4 = tech_perf.get("effluent_nh4_mg_l")
    eff_tp  = tech_perf.get("effluent_tp_mg_l")

    # ── C1: Compliance vs preferred status ────────────────────────────────
    is_preferred = getattr(scenario, "is_preferred", False)
    compliance_flag = tech_perf.get("compliance_flag", "")
    compliance_issues = tech_perf.get("compliance_issues", [])
    has_issues = bool(compliance_issues) if isinstance(compliance_issues, list) else bool(compliance_issues)

    if is_preferred and has_issues and "Review Required" in compliance_flag:
        f("C1", Severity.FAIL,
          f"Scenario is marked 'Preferred' but fails compliance targets: "
          f"{compliance_issues if isinstance(compliance_issues, str) else '; '.join(str(x) for x in compliance_issues)}. "
          "A non-compliant scenario cannot be the preferred option.",
          metric="compliance_flag",
          expected="Preferred option must meet all effluent targets",
          actual=f"{compliance_flag}: {compliance_issues}",
          rec="Either remove preferred status or re-engineer to meet targets before recommending")

    # ── C2: Effluent target vs result coherence ───────────────────────────
    checks = [
        ("effluent_tn_mg_l",  eff_tn,  target_tn,  "TN"),
        ("effluent_nh4_mg_l", eff_nh4, target_nh4, "NH₄"),
        ("effluent_tp_mg_l",  eff_tp,  target_tp,  "TP"),
    ]
    for metric, actual, target, label in checks:
        if actual is not None and target and actual > target * 1.05:
            # More than 5% above target — note it
            f("C2", Severity.WARN,
              f"Effluent {label} = {actual:.1f} mg/L exceeds target {target:.1f} mg/L "
              f"({(actual-target)/target*100:.0f}% above target).",
              metric=metric,
              expected=f"≤ {target:.1f} mg/L",
              actual=f"{actual:.1f} mg/L",
              rec=f"Review {label} removal pathway — SRT, configuration, or supplemental process may be needed")

    # ── C3: Temperature vs nitrification result ───────────────────────────
    temp = di.get("influent_temperature_celsius") or 20.0
    if temp >= 18.0 and eff_nh4 is not None and target_nh4:
        # At warm temperature, NH4 result should equal target
        if eff_nh4 > target_nh4 * 1.1:
            f("C3", Severity.WARN,
              f"At {temp}°C, nitrification should be reliable but effluent NH₄ "
              f"= {eff_nh4:.1f} mg/L (target {target_nh4:.1f} mg/L). "
              "Check SRT and process configuration.",
              metric="effluent_nh4_mg_l",
              rec="Verify SRT ≥ 8d at 20°C for reliable nitrification")

    return QAResult(findings=findings)
