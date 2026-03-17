"""
core/qa/rules/report_rules.py
Pre-export report quality checks. Blocks export if FAIL found.
"""
from __future__ import annotations
from typing import Any
from core.qa.qa_model import QAFinding, QAResult, Severity

PLACEHOLDER_STRINGS = ["test", "placeholder", "todo", "tbd", "xxx", "n/a", "—"]


def run(report: Any, project: Any = None) -> QAResult:
    """
    report: ReportObject from ReportEngine.build_report()
    project: ProjectModel (for metadata checks)
    """
    findings = []

    def f(code, sev, msg, metric=None, expected=None, actual=None, rec=None):
        findings.append(QAFinding(
            code=code, category="Report", severity=sev, message=msg,
            metric=metric, expected=expected, actual=actual,
            recommendation=rec,
        ))

    if report is None:
        f("R0", Severity.FAIL, "Report object is None — run build_report() first.",
          rec="Generate report before attempting export")
        return QAResult(findings=findings)

    # ── R1: Project name not placeholder ──────────────────────────────────
    proj_name = getattr(report, "project_name", "") or ""
    if not proj_name:
        f("R1", Severity.FAIL, "Project name is empty.",
          metric="project_name", rec="Enter a project name before exporting")
    elif proj_name.lower().strip() in PLACEHOLDER_STRINGS:
        f("R1", Severity.WARN,
          f"Project name appears to be a placeholder: '{proj_name}'.",
          metric="project_name",
          rec="Replace placeholder project name with the real project name")

    # ── R2: Required sections present ─────────────────────────────────────
    sections = [s.title for s in getattr(report, "sections", [])]
    required_sections = [
        "Cost Summary",
        "Risk Summary",
        "Scenario Definitions",
    ]
    for req in required_sections:
        if not any(req.lower() in s.lower() for s in sections):
            f("R2", Severity.FAIL,
              f"Required report section missing: '{req}'.",
              metric="sections",
              rec=f"Ensure '{req}' section is populated before export")

    # ── R3: Executive summary populated ───────────────────────────────────
    exec_sum = getattr(report, "executive_summary", "") or ""
    if len(exec_sum.strip()) < 50:
        f("R3", Severity.FAIL,
          "Executive summary is empty or too short.",
          metric="executive_summary",
          rec="Run calculations and generate report before exporting")

    # ── R4: No placeholder text in executive summary ───────────────────────
    for ph in PLACEHOLDER_STRINGS:
        # Check for standalone placeholder words (not substrings of real words)
        import re
        if re.search(rf'\b{re.escape(ph)}\b', exec_sum.lower()):
            if ph not in ("n/a", "—"):  # these are acceptable
                f("R4", Severity.WARN,
                  f"Possible placeholder text '{ph}' found in executive summary.",
                  rec="Review and replace all placeholder text before issuing report")
                break

    # ── R5: No duplicate conclusion sections ──────────────────────────────
    conclusion_sections = [s for s in sections
                           if "conclusion" in s.lower() or "recommend" in s.lower()]
    if len(conclusion_sections) > 1:
        f("R5", Severity.WARN,
          f"Multiple conclusion/recommendation sections found: {conclusion_sections}. "
          "Report should have a single conclusion.",
          metric="sections",
          rec="Remove duplicate conclusion — keep only 'Conclusions and Recommendations'")

    # ── R6: Cost table populated ───────────────────────────────────────────
    cost_table = getattr(report, "cost_table", None)
    if not cost_table:
        f("R6", Severity.FAIL,
          "Cost summary table is empty — CAPEX/OPEX/LCC not populated.",
          metric="cost_table",
          rec="Run cost calculations before exporting")

    # ── R7: Zero CAPEX in cost table ──────────────────────────────────────
    if cost_table and isinstance(cost_table, (list, dict)):
        rows = cost_table if isinstance(cost_table, list) else cost_table.get("rows", [])
        for row in rows:
            capex = row.get("CAPEX ($M)") or row.get("capex_m") or 0
            scen  = row.get("Scenario") or row.get("scenario_name") or "unknown"
            try:
                if float(str(capex).replace("$","").replace("M","").strip() or 0) == 0:
                    f("R7", Severity.FAIL,
                      f"Scenario '{scen}' has zero CAPEX in cost table.",
                      rec="Ensure all active scenarios have non-zero CAPEX")
            except (ValueError, TypeError):
                pass

    # ── R8: Decision section present (if multi-scenario) ──────────────────
    scenario_count = len(getattr(report, "scenario_names", []))
    has_decision = any("Decision" in s for s in sections)
    if scenario_count > 1 and not has_decision:
        f("R8", Severity.WARN,
          "Multi-scenario report has no Decision Framework section.",
          metric="sections",
          rec="Run decision engine analysis to add recommendation section")

    # ── R9: Assumptions appendix ──────────────────────────────────────────
    assumptions = getattr(report, "assumptions_appendix", None)
    if not assumptions:
        f("R9", Severity.INFO,
          "Assumptions appendix not included in report.",
          rec="Enable 'Include assumptions appendix' for a complete report")

    return QAResult(findings=findings)
