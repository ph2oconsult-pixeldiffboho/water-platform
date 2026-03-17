"""
core/qa/rules/mass_energy_rules.py

Post-run mass and energy consistency checks.
These would have caught the O2/energy mismatch in the uploaded report.
"""
from __future__ import annotations
from typing import Any, Dict, Optional
from core.qa.qa_model import QAFinding, QAResult, Severity

# Technology-specific energy benchmarks (kWh/ML)
ENERGY_BENCHMARKS = {
    "bnr":             (250, 450),
    "granular_sludge": (220, 420),
    "ifas_mbbr":       (280, 500),
    "bnr_mbr":         (450, 800),
    "mabr_bnr":        (180, 380),
}

def run(scenario, tech_code: str = None) -> QAResult:
    """
    scenario: ScenarioModel with cost_result, carbon_result, domain_specific_outputs
    tech_code: primary technology code string
    """
    findings = []
    sn = getattr(scenario, "scenario_name", None)
    di = scenario.domain_inputs or {}
    eng = (scenario.domain_specific_outputs or {}).get("engineering_summary", {})
    tp  = (scenario.domain_specific_outputs or {}).get("technology_performance", {})
    tech_perf = tp.get(tech_code, {}) if tech_code else {}

    def f(code, sev, msg, metric=None, expected=None, actual=None, rec=None):
        findings.append(QAFinding(
            code=code, category="Energy", severity=sev, message=msg,
            scenario=sn, metric=metric, expected=expected, actual=actual,
            recommendation=rec,
        ))

    # ── E1: O2 demand vs aeration energy consistency ───────────────────────
    o2_kg_day = tech_perf.get("o2_demand_kg_day") or 0
    total_kwh_day = eng.get("total_energy_kwh_day") or 0
    flow_mld = di.get("design_flow_mld") or 0

    if o2_kg_day > 0 and total_kwh_day > 0:
        # SAE_process ≈ 1.8 × alpha (alpha=0.55 typical) ≈ 0.99 kg O2/kWh
        # Aeration fraction of total energy: typically 50-75%
        sae_proc = 1.8 * 0.55  # conservative process SAE
        aeration_kwh_implied = o2_kg_day / sae_proc
        aeration_kwh_actual  = total_kwh_day * 0.65  # assume 65% of total is aeration

        ratio = aeration_kwh_implied / max(aeration_kwh_actual, 1)
        if ratio > 1.5 or ratio < 0.4:
            sev = Severity.FAIL if (ratio > 2.0 or ratio < 0.25) else Severity.WARN
            f("E1", sev,
              f"O₂ demand ({o2_kg_day:.0f} kg/d) and aeration energy "
              f"({aeration_kwh_actual:.0f} kWh/d estimated from total) are inconsistent "
              f"(implied aeration = {aeration_kwh_implied:.0f} kWh/d, ratio={ratio:.1f}×).",
              metric="o2_demand_kg_day",
              expected=f"Aeration kWh/d within 50% of O₂-implied value",
              actual=f"O₂-implied {aeration_kwh_implied:.0f} vs reported ~{aeration_kwh_actual:.0f}",
              rec="Verify aeration energy calculation — check SAE factor and O₂ demand formula")

    # ── E2: Specific energy plausibility ──────────────────────────────────
    kwh_kl = eng.get("specific_energy_kwh_kl") or 0
    kwh_ml = kwh_kl * 1000

    if kwh_ml > 0 and tech_code:
        lo, hi = ENERGY_BENCHMARKS.get(tech_code, (200, 900))
        if kwh_ml < lo:
            sev = Severity.FAIL if kwh_ml < lo * 0.6 else Severity.WARN
            f("E2", sev,
              f"Specific energy {kwh_ml:.0f} kWh/ML is below benchmark range for "
              f"{tech_code} ({lo}–{hi} kWh/ML). Likely underestimate.",
              metric="specific_energy_kwh_kl",
              expected=f"{lo}–{hi} kWh/ML",
              actual=f"{kwh_ml:.0f} kWh/ML",
              rec="Check aeration, pumping, and ancillary energy components are all included")
        elif kwh_ml > hi:
            f("E2", Severity.WARN,
              f"Specific energy {kwh_ml:.0f} kWh/ML is above benchmark range for "
              f"{tech_code} ({lo}–{hi} kWh/ML). Verify inputs.",
              metric="specific_energy_kwh_kl",
              expected=f"{lo}–{hi} kWh/ML",
              actual=f"{kwh_ml:.0f} kWh/ML",
              rec="Check for unusually high oxygen demand or aeration inefficiency")

    # ── E3: Energy and CAPEX both non-zero ────────────────────────────────
    cr = scenario.cost_result
    if cr:
        if cr.capex_total <= 0:
            f("E3", Severity.FAIL,
              "CAPEX is zero or negative for an active scenario.",
              metric="capex_total",
              expected="> 0",
              actual=str(cr.capex_total),
              rec="Check that technology cost items are correctly defined")
        if cr.opex_annual <= 0:
            f("E3", Severity.FAIL,
              "OPEX is zero or negative — energy, sludge, and labour costs missing.",
              metric="opex_annual",
              expected="> 0",
              actual=str(cr.opex_annual),
              rec="Check electricity, sludge disposal, and labour cost items")

    return QAResult(findings=findings)
