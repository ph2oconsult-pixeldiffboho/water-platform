"""
core/qa/rules/sludge_rules.py

Sludge production consistency checks.
Rule S2 would have caught the Table1/PFD discrepancy in the uploaded report.
"""
from __future__ import annotations
from core.qa.qa_model import QAFinding, QAResult, Severity


def run(scenario, tech_code: str = None) -> QAResult:
    findings = []
    sn = getattr(scenario, "scenario_name", None)
    di = scenario.domain_inputs or {}
    eng = (scenario.domain_specific_outputs or {}).get("engineering_summary", {})
    tp  = (scenario.domain_specific_outputs or {}).get("technology_performance", {})
    tech_perf = tp.get(tech_code, {}) if tech_code else {}

    def f(code, sev, msg, metric=None, expected=None, actual=None, rec=None):
        findings.append(QAFinding(
            code=code, category="Sludge", severity=sev, message=msg,
            scenario=sn, metric=metric, expected=expected, actual=actual,
            recommendation=rec,
        ))

    # ── S1: Sludge yield plausibility ─────────────────────────────────────
    sludge_kgds = tech_perf.get("sludge_production_kgds_day") or 0
    bod_in  = di.get("influent_bod_mg_l") or 0
    bod_eff = di.get("effluent_bod_mg_l") or 10
    flow    = di.get("design_flow_mld") or 0
    bod_removed = (bod_in - bod_eff) * flow * 1000 / 1000 if (bod_in and flow) else 0

    if sludge_kgds > 0 and bod_removed > 0:
        sludge_yield = sludge_kgds / bod_removed  # kgDS/kgBOD
        if sludge_yield < 0.25 or sludge_yield > 1.20:
            sev = Severity.FAIL if (sludge_yield < 0.15 or sludge_yield > 1.80) else Severity.WARN
            f("S1", sev,
              f"Sludge yield = {sludge_yield:.2f} kgDS/kgBOD — outside plausible range [0.25–1.20]. "
              f"({sludge_kgds:.0f} kgDS/d from {bod_removed:.0f} kgBOD/d removed)",
              metric="sludge_production_kgds_day",
              expected="0.25–1.20 kgDS/kgBOD removed",
              actual=f"{sludge_yield:.2f} kgDS/kgBOD",
              rec="Check observed yield (Yobs), VSS/TSS ratio, and inorganic TSS contribution")

    # ── S2: Summary vs detail reconciliation ──────────────────────────────
    # The engineering_summary has total_sludge_kgds_day
    # The technology_performance has sludge_production_kgds_day
    # These must agree within ±5%
    summary_sludge = eng.get("total_sludge_kgds_day") or 0
    detail_sludge  = sludge_kgds

    if summary_sludge > 0 and detail_sludge > 0:
        delta = abs(summary_sludge - detail_sludge) / max(summary_sludge, 1)
        if delta > 0.05:
            sev = Severity.FAIL if delta > 0.15 else Severity.WARN
            f("S2", sev,
              f"Sludge inconsistency: summary table = {summary_sludge:.0f} kgDS/d, "
              f"detail table = {detail_sludge:.0f} kgDS/d "
              f"(discrepancy = {delta*100:.0f}%). "
              "These must match within ±5% for a credible report.",
              metric="sludge_production_kgds_day",
              expected=f"Summary ≈ detail (within 5%)",
              actual=f"Summary {summary_sludge:.0f} vs detail {detail_sludge:.0f} "
                     f"({delta*100:.0f}% gap)",
              rec="Identify which code path produces each value and ensure single source of truth")

    return QAResult(findings=findings)
