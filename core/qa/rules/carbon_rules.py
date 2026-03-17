"""
core/qa/rules/carbon_rules.py
Carbon/energy consistency checks.
"""
from __future__ import annotations
from core.qa.qa_model import QAFinding, QAResult, Severity


def run(scenario, tech_code: str = None) -> QAResult:
    findings = []
    sn = getattr(scenario, "scenario_name", None)
    cr = scenario.carbon_result
    di = scenario.domain_inputs or {}
    eng = (scenario.domain_specific_outputs or {}).get("engineering_summary", {})

    if not cr:
        return QAResult()

    def f(code, sev, msg, metric=None, expected=None, actual=None, rec=None):
        findings.append(QAFinding(
            code=code, category="Carbon", severity=sev, message=msg,
            scenario=sn, metric=metric, expected=expected, actual=actual,
            recommendation=rec,
        ))

    flow = di.get("design_flow_mld") or 0
    grid_ef = di.get("grid_emission_factor") or 0.79  # kg CO2e/kWh default AU
    elec_price = di.get("electricity_price_per_kwh") or 0.14
    kwh_kl = eng.get("specific_energy_kwh_kl") or 0

    # ── G1: Scope 2 consistency ───────────────────────────────────────────
    if kwh_kl > 0 and flow > 0 and cr.scope_2_tco2e_yr > 0:
        kwh_yr = kwh_kl * flow * 1000 * 365
        scope2_expected = kwh_yr * grid_ef / 1000  # tCO2e/yr
        scope2_reported = cr.scope_2_tco2e_yr
        delta = abs(scope2_reported - scope2_expected) / max(scope2_expected, 1)
        if delta > 0.08:   # >8% discrepancy
            sev = Severity.FAIL if delta > 0.20 else Severity.WARN
            f("G1", sev,
              f"Scope 2 inconsistency: reported {scope2_reported:.0f} tCO₂e/yr, "
              f"calculated from energy = {scope2_expected:.0f} tCO₂e/yr "
              f"({delta*100:.0f}% discrepancy).",
              metric="scope_2_tco2e_yr",
              expected=f"~{scope2_expected:.0f} tCO₂e/yr",
              actual=f"{scope2_reported:.0f} tCO₂e/yr",
              rec=f"Check grid emission factor ({grid_ef} kg CO₂e/kWh) and energy calculation")

    # ── G2: Carbon directionality ─────────────────────────────────────────
    # If scenario has higher energy but lower Scope 2 vs another — can't check
    # cross-scenario here; done at project level in qa_engine

    # ── G3: N2O uncertainty warning ───────────────────────────────────────
    if cr.scope_1_tco2e_yr > 0:
        f("G3", Severity.INFO,
          f"Scope 1 carbon ({cr.scope_1_tco2e_yr:.0f} tCO₂e/yr) includes N₂O from biological "
          "nitrogen removal. N₂O carries ±3× uncertainty (IPCC EF range 0.005–0.05). "
          "Site measurement recommended for detailed assessments.",
          metric="scope_1_tco2e_yr",
          rec="Treat Scope 1 carbon as order-of-magnitude only at concept stage")

    return QAResult(findings=findings)
