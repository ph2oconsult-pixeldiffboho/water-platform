"""
core/decision/platform_qa.py

Platform-level QA layer.

Validates consistency across ALL decision surfaces:
  - compliance flags (ScenarioModel vs technology_performance vs scoring engine)
  - decision logic (compliance -> cost -> scoring -> recommendation)
  - scoring (no non-compliant option ranked, no contradictions)
  - engineering assumptions (achievability warnings flagged)

Called by the report engine before report generation.
Results surfaced in the report and in the app Decision Scoring page.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Any


@dataclass
class PlatformQAResult:
    passed:   bool
    errors:   List[str] = field(default_factory=list)   # fail-the-report level
    warnings: List[str] = field(default_factory=list)   # show-in-report level
    notes:    List[str] = field(default_factory=list)   # informational

    def fail(self, msg: str) -> None:
        self.errors.append(msg)
        self.passed = False

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    def note(self, msg: str) -> None:
        self.notes.append(msg)


def run_platform_qa(
    scenarios:      List[Any],           # List[ScenarioModel]
    scoring_result: Optional[Any],       # DecisionResult | None
    decision:       Optional[Any],       # WastewaterDecisionResult | None
) -> PlatformQAResult:
    """
    Run all QA checks and return a PlatformQAResult.

    Parameters
    ----------
    scenarios       : scenario objects with .compliance_status, .cost_result etc.
    scoring_result  : output of ScoringEngine.score()
    decision        : output of evaluate_scenario()
    """
    qa = PlatformQAResult(passed=True)

    if not scenarios:
        qa.fail("QA-E01: No scenarios provided — cannot validate.")
        return qa

    # ── QA-1: Compliance consistency ─────────────────────────────────────
    # Each scenario must have a compliance_status stamped.
    # Scoring engine excluded list must match domain engine non_viable list.
    for s in scenarios:
        status = getattr(s, "compliance_status", "")
        if not status:
            qa.warn(
                f"QA-W01: {s.scenario_name} has no compliance_status stamp. "
                "Run populate_scenario_from_calc to set this."
            )

    if scoring_result and decision:
        sr_excl  = {o.scenario_name for o in scoring_result.excluded}
        dom_nv   = set(getattr(decision, "non_viable", []) or [])
        if sr_excl != dom_nv:
            qa.fail(
                f"QA-E02: Compliance mismatch between scoring engine and domain engine. "
                f"Scoring excluded: {sorted(sr_excl)}. "
                f"Domain non-viable: {sorted(dom_nv)}. "
                "All report surfaces must use the same compliance determination."
            )

    # ── QA-2: Non-compliant options must not appear in ranking ───────────
    if scoring_result:
        for opt in scoring_result.scored_options:
            if not opt.is_eligible and opt.rank > 0:
                qa.fail(
                    f"QA-E03: {opt.scenario_name} is non-compliant but has rank={opt.rank}. "
                    "Non-compliant options must not be ranked."
                )
        # Runner-up must be eligible
        if scoring_result.runner_up and not scoring_result.runner_up.is_eligible:
            qa.fail(
                f"QA-E04: Runner-up ({scoring_result.runner_up.scenario_name}) "
                "is not eligible (non-compliant or CWI without sufficient score). "
                "Runner-up must be a fully compliant option."
            )

    # ── QA-3: Decision recommendation must match scoring preferred ────────
    if scoring_result and decision:
        sr_pref  = scoring_result.preferred.scenario_name if scoring_result.preferred else None
        dom_tech = getattr(decision, "recommended_tech", None)

        # Map scenario_name back to tech_code for comparison
        tech_map = {}
        for s in scenarios:
            tp_seq = (s.treatment_pathway.technology_sequence
                      if s.treatment_pathway and s.treatment_pathway.technology_sequence
                      else [])
            if tp_seq:
                tech_map[s.scenario_name] = tp_seq[0]

        sr_tech = tech_map.get(sr_pref) if sr_pref else None
        if sr_tech and dom_tech and sr_tech != dom_tech:
            qa.warn(
                f"QA-W02: Scoring engine prefers {sr_pref} ({sr_tech}) but "
                f"domain engine recommends {decision.recommended_label} ({dom_tech}). "
                "Decision Summary uses scoring engine result. "
                "Investigate if this gap is material."
            )

    # ── QA-4: Engineering assumption checks ──────────────────────────────
    for s in scenarios:
        tc = (s.treatment_pathway.technology_sequence[0]
              if s.treatment_pathway and s.treatment_pathway.technology_sequence else "")
        dso = getattr(s, "domain_specific_outputs", None) or {}
        tp  = dso.get("technology_performance", {}).get(tc, {})

        ach = tp.get("achievability_warnings", "") or ""
        if ach:
            qa.note(
                f"QA-N01: {s.scenario_name} — achievability note: {ach[:80]}"
            )

        # Flag if TN achievability warning is present AND the technology actually requires
        # supplemental carbon (COD/TKN < 10) but no methanol appears in OPEX.
        # Do NOT fire if the model achieves TN naturally — the achievability warning
        # is then a site-investigation caution, not a cost omission.
        if "supplemental carbon" in ach.lower() or "methanol" in ach.lower():
            tc_code = (s.treatment_pathway.technology_sequence[0]
                       if s.treatment_pathway and s.treatment_pathway.technology_sequence else "")
            dso2    = getattr(s, "domain_specific_outputs", None) or {}
            tp2     = dso2.get("technology_performance", {}).get(tc_code, {})
            # Only warn if the engineering summary explicitly says methanol is REQUIRED
            # (not just mentioned as a possibility)
            eng_notes = str(tp2.get("notes", "")) + str(tp2.get("engineering_notes", ""))
            methanol_required = (
                "methanol dose required" in eng_notes.lower() or
                "methanol: " in eng_notes.lower()
            )
            if methanol_required:
                cr = getattr(s, "cost_result", None)
                opex_keys = list(cr.opex_breakdown.keys()) if cr and hasattr(cr, "opex_breakdown") else []
                has_methanol_opex = any("methanol" in k.lower() for k in opex_keys)
                if not has_methanol_opex:
                    qa.warn(
                        f"QA-W03: {s.scenario_name} — engineering notes indicate methanol dosing "
                        f"is required for reliable TN compliance, but no methanol cost is included "
                        "in OPEX. Lifecycle cost may be understated — confirm carbon availability "
                        "on site before relying on this cost estimate."
                    )

    # ── QA-5: Cost result present for all scenarios ───────────────────────
    for s in scenarios:
        if not getattr(s, "cost_result", None):
            qa.fail(f"QA-E05: {s.scenario_name} has no cost_result — cannot be scored or ranked.")

    # ── QA-6: Close-decision flag present in scoring ──────────────────────
    if scoring_result and scoring_result.close_decision:
        qa.note(
            f"QA-N02: Close decision detected "
            f"(gap {scoring_result.preferred.total_score - scoring_result.runner_up.total_score:.1f} pts, "
            f"threshold {scoring_result.close_decision_threshold:.1f} pts). "
            "Do not commit to preferred option without site-specific validation."
        )

    # ── QA-7: All scenarios have compliance_status consistent with scoring ─
    if scoring_result:
        sc_compliance = {s.scenario_name: getattr(s, "compliance_status", "") for s in scenarios}
        for opt in scoring_result.scored_options:
            sc_status  = sc_compliance.get(opt.scenario_name, "")
            opt_status = opt.compliance_status
            if sc_status and opt_status:
                sc_eligible = sc_status in ("Compliant", "Compliant with intervention")
                opt_eligible = opt.is_eligible
                if sc_eligible != opt_eligible:
                    qa.fail(
                        f"QA-E06: Compliance mismatch for {opt.scenario_name}: "
                        f"ScenarioModel.compliance_status='{sc_status}' "
                        f"but scoring engine eligible={opt_eligible}. "
                        "Single source of truth violated."
                    )

    return qa
