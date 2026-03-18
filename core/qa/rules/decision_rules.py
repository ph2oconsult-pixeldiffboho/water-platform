"""
core/qa/rules/decision_rules.py
Decision logic consistency — recommendation text, trade-off completeness,
non-compliant labelling. Runs at project level across all scenarios.
"""
from __future__ import annotations
from typing import List, Any
from core.qa.qa_model import QAFinding, QAResult, Severity


def run(decision: Any, scenarios: List[Any]) -> QAResult:
    """
    decision: ScenarioDecision from decision_engine.evaluate_scenario()
    scenarios: list of ScenarioModel
    """
    findings = []
    if decision is None:
        return QAResult()

    def f(code, sev, msg, scenario=None, metric=None, expected=None, actual=None, rec=None):
        findings.append(QAFinding(
            code=code, category="Decision", severity=sev, message=msg,
            scenario=scenario, metric=metric, expected=expected, actual=actual,
            recommendation=rec,
        ))

    # ── D1: No contradictory recommendation text ──────────────────────────
    rec_label   = getattr(decision, "recommended_label", "") or ""
    why         = " ".join(getattr(decision, "why_recommended", []))
    trade_offs  = " ".join(getattr(decision, "trade_offs", []))
    selection   = getattr(decision, "selection_basis", "")

    # Check for old contradiction: "offset by lower risk" when recommended
    # has higher risk
    if "offset by lower risk" in why.lower():
        rec_sc = next((s for s in scenarios if s.scenario_name == rec_label), None)
        if rec_sc:
            for other in scenarios:
                if other.scenario_name != rec_label:
                    if (rec_sc.risk_result and other.risk_result and
                            rec_sc.risk_result.overall_score > other.risk_result.overall_score):
                        f("D1", Severity.FAIL,
                          f"Recommendation text says 'offset by lower risk' but "
                          f"{rec_label} has HIGHER risk than {other.scenario_name}.",
                          metric="why_recommended",
                          rec="Update recommendation text to reflect actual risk comparison")

    # ── D2: Sole-compliant recommendation correctly labelled ──────────────
    non_viable = getattr(decision, "non_viable", [])
    alt_paths  = getattr(decision, "alternative_pathways", [])
    compliant_alts = [p for p in alt_paths if getattr(p, "achieves_compliance", False)]

    if non_viable and len(non_viable) >= len(scenarios) - 1:
        # Only one scenario passes compliance
        if "sole compliant" in selection.lower() and compliant_alts:
            f("D2", Severity.WARN,
              f"Selection basis says 'sole compliant option' but "
              f"{len(compliant_alts)} alternative pathway(s) also achieve compliance. "
              "Selection basis should reflect two compliant pathways.",
              metric="selection_basis",
              expected="Two compliant pathways identified",
              actual=selection[:80],
              rec="Update selection_basis to acknowledge both pathways")

    # ── D3: Non-compliant base case labelled correctly ────────────────────
    for sc_name in non_viable:
        # Check if there's a matching intervention that makes it viable
        matching_path = next(
            (p for p in alt_paths
             if getattr(p, "tech_label", "") == sc_name
             and getattr(p, "achieves_compliance", False)),
            None
        )
        if matching_path:
            # There IS an intervention — make sure label says "without intervention"
            # (We check the trade_offs text as a proxy)
            if sc_name in trade_offs and "without intervention" not in trade_offs.lower():
                f("D3", Severity.INFO,
                  f"{sc_name} is non-compliant as a base case but becomes compliant "
                  "with engineering intervention. Labels should clarify this.",
                  scenario=sc_name,
                  rec='Use label "non-compliant without intervention" rather than simply "non-compliant"')

    # ── D4: Trade-off completeness when two pathways exist ────────────────
    if compliant_alts and non_viable:
        trade_off_text = " ".join(getattr(decision, "trade_offs", []))
        required_topics = ["capex", "opex", "deliver", "regulat"]
        missing = [t for t in required_topics if t not in trade_off_text.lower()]
        if missing:
            f("D4", Severity.WARN,
              f"Two compliant pathways exist but trade-off section does not address: "
              f"{', '.join(missing)}.",
              metric="trade_offs",
              rec="Add CAPEX, OPEX, delivery, and regulatory trade-offs for both pathways")

    return QAResult(findings=findings)


def run_guidance_check(decision) -> "QAResult":
    """
    D5 — Conditional decision guidance exists.
    The decision section must tell the reader WHEN to choose each option,
    not just list trade-offs. Avoids the neutral cop-out.
    """
    from core.qa.qa_model import QAResult, QAFinding, Severity
    findings = []

    if decision is None:
        return QAResult()

    conclusion = getattr(decision, "conclusion", "") or ""
    trade_offs = " ".join(getattr(decision, "trade_offs", []) or [])
    rec_approach = getattr(decision, "recommended_approach", []) or []
    rec_text = " ".join(rec_approach)

    # Check for conditional language ("if", "when", "where", "→")
    conditional_words = ["if ", "when ", "where ", "prefer", "→", "lowest capex",
                         "lowest opex", "lowest risk", "footprint"]
    has_conditional = any(w in (conclusion + trade_offs + rec_text).lower()
                          for w in conditional_words)

    # Check for neutral cop-out phrases
    cop_out_phrases = [
        "depends on site-specific factors",
        "subject to further investigation",
        "requires further assessment",
        "cannot be determined at this stage",
    ]
    has_cop_out = any(p in (conclusion + trade_offs).lower() for p in cop_out_phrases)

    if not has_conditional:
        findings.append(QAFinding(
            code="D5", category="Decision", severity=Severity.WARN,
            message=(
                "Decision framework lacks conditional guidance. "
                "The report should state which option is preferred "
                "under specific conditions (e.g. 'if footprint is constrained → AGS; "
                "if lowest delivery risk → BNR')."
            ),
            recommendation="Add 'if X then Y' conditional statements to the recommendation "
                           "section so the reader can apply the analysis to their specific context."
        ))

    if has_cop_out:
        findings.append(QAFinding(
            code="D5", category="Decision", severity=Severity.WARN,
            message=(
                "Decision framework contains neutral cop-out language. "
                "Replace 'depends on site-specific factors' with specific "
                "conditional guidance tied to measurable criteria."
            ),
            recommendation="Replace vague language with: 'Choose X if [criterion]; "
                           "Choose Y if [criterion]'"
        ))

    if has_conditional and not has_cop_out:
        findings.append(QAFinding(
            code="D5", category="Decision", severity=Severity.INFO,
            message="Decision framework includes conditional guidance ✅"
        ))

    return QAResult(findings=findings)
