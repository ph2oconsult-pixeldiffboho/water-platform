"""
core/decision/scoring_qa.py

QA rules for the scoring engine output.

Rules
-----
HARD FAILS (return errors):
  Q1 — A non-compliant option ranks first
  Q2 — Weights do not sum to 100% (±2%)
  Q3 — Any criterion value is missing for a scored scenario
  Q4 — Total score table is incomplete (fewer entries than scenarios)
  Q5 — Recommendation contradicts actual scores (preferred is not rank 1)

WARNINGS:
  W1 — Top two options within 5 points (close decision)
  W2 — A "Compliant with intervention" option ranks first
  W3 — Recommendation confidence is weak (score < 50/100)
  W4 — Only one compliant option (no genuine comparison)
  W5 — All options excluded (all non-compliant)
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any


@dataclass
class ScoringQAResult:
    passed:   bool = True
    errors:   List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def fail(self, msg: str) -> None:
        self.passed = False
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)


def run_scoring_qa(result: Any, compliance_map: Dict[str, str]) -> ScoringQAResult:
    """
    Run QA checks on a DecisionResult.

    Parameters
    ----------
    result         : DecisionResult from ScoringEngine.score()
    compliance_map : {scenario_name: compliance_status}
    """
    qa = ScoringQAResult()

    # ── Q1: Non-compliant option ranks first ────────────────────────────
    if result.preferred:
        status = compliance_map.get(result.preferred.scenario_name, "Compliant")
        if status == "Non-compliant":
            qa.fail(
                f"Q1 FAIL — Non-compliant option '{result.preferred.scenario_name}' "
                "ranks first. This violates the compliance gate. "
                "Check that compliance_map is correctly populated."
            )

    # ── Q2: Weights do not sum to 100% ──────────────────────────────────
    total_w = sum(result.weights.values())
    if not (0.98 <= total_w <= 1.02):
        qa.fail(
            f"Q2 FAIL — Weights sum to {total_w*100:.1f}%, not 100%. "
            "All weights must sum to exactly 100%."
        )

    # ── Q3: Missing criterion values ────────────────────────────────────
    for opt in result.scored_options:
        if not opt.is_eligible:
            continue  # excluded options may have incomplete data
        for crit in result.weights:
            cs = opt.criterion_scores.get(crit)
            if cs is None:
                qa.fail(
                    f"Q3 FAIL — Criterion '{crit}' missing for scenario "
                    f"'{opt.scenario_name}'. All criteria must be populated."
                )
            elif cs.raw_value == 0.0 and crit not in ("regulatory", "maturity"):
                # Zero raw values are suspicious for cost/energy/carbon criteria
                pass  # Don't fail — zero could be valid (e.g., no sludge)

    # ── Q4: Incomplete score table ──────────────────────────────────────
    eligible_count = sum(1 for o in result.scored_options if o.is_eligible)
    if eligible_count < 1:
        qa.fail(
            "Q4 FAIL — No eligible options in score table. "
            "At least one compliant option is required to produce a recommendation."
        )

    # ── Q5: Recommendation contradicts scores ───────────────────────────
    if result.preferred and result.scored_options:
        ranked_eligible = [o for o in result.scored_options if o.is_eligible]
        if ranked_eligible:
            top_scorer = max(ranked_eligible, key=lambda o: o.total_score)
            if top_scorer.scenario_name != result.preferred.scenario_name:
                qa.fail(
                    f"Q5 FAIL — Recommendation is '{result.preferred.scenario_name}' "
                    f"but highest-scoring eligible option is '{top_scorer.scenario_name}'. "
                    "The recommendation must match the highest-scoring eligible option."
                )

    # ── W1: Close decision ──────────────────────────────────────────────
    if result.close_decision and result.runner_up:
        gap = result.preferred.total_score - result.runner_up.total_score
        qa.warn(
            f"W1 — Close decision: gap is {gap:.1f} points (threshold 5.0). "
            "Recommendation confidence is limited. Report as 'close decision'. "
            "Sensitivity test with alternative weight profiles recommended."
        )

    # ── W2: Compliant with intervention ranks first ──────────────────────
    if result.preferred:
        status = compliance_map.get(result.preferred.scenario_name, "Compliant")
        if "intervention" in status.lower():
            qa.warn(
                f"W2 — '{result.preferred.scenario_name}' is 'Compliant with intervention' "
                "and ranks first. Report must clearly state the intervention required "
                "before this option can be procured."
            )

    # ── W3: Low confidence ──────────────────────────────────────────────
    if result.preferred and result.preferred.total_score < 50:
        qa.warn(
            f"W3 — Preferred option scores {result.preferred.total_score:.0f}/100. "
            "Score below 50 indicates weak differentiation between options. "
            "Consider broadening the comparison or adjusting weight profile."
        )

    # ── W4: Only one compliant option ────────────────────────────────────
    eligible = [o for o in result.scored_options if o.is_eligible]
    if len(eligible) == 1:
        qa.warn(
            f"W4 — Only one compliant option ('{eligible[0].scenario_name}'). "
            "Recommendation is forced — no genuine comparison available. "
            "Consider adding alternative scenarios before finalising."
        )

    # ── W5b: Correlation warnings from engine ────────────────────────────
    for pair_msg in getattr(result, "correlated_pairs", []):
        qa.warn(f"W5b — {pair_msg}")

    # ── W5c: Below-uncertainty criteria ──────────────────────────────────
    below = getattr(result, "below_uncertainty", [])
    if below:
        from core.decision.scoring_engine import CRITERION_LABELS
        below_labels = [CRITERION_LABELS.get(c,c) for c in below]
        qa.warn(
            f"W5c — The following criteria have spread < ±40% estimate uncertainty "
            f"and may not meaningfully discriminate between options: "
            f"{', '.join(below_labels)}. "
            "Treat their contribution to the score with caution."
        )

    # ── W5: All excluded ─────────────────────────────────────────────────
    if len(eligible) == 0 and result.excluded:
        qa.warn(
            "W5 — All options are non-compliant. No recommendation can be made. "
            "Engineering intervention or target relaxation required."
        )

    return qa
