"""
core/engineering/feasibility_status.py

Unified Engineering Feasibility Status
========================================
Combines compliance gate (effluent targets) and hydraulic stress
into a single "Engineering Feasibility Status" used consistently
across scoring, ranking, and all report surfaces.

Status values
-------------
PASS          All targets met, all hydraulic checks pass. Rankable as-is.
CONDITIONAL   Target met but hydraulic check warns, OR non-compliant but
              a defined remediation exists that resolves the issue.
              Rankable ONLY with remediation costs included.
FAIL          Hydraulic FAIL with no defined remediation, OR non-compliant
              with no fix path. Cannot be ranked.

Decision logic
--------------
  is_compliant=True  + hydraulic PASS     → PASS
  is_compliant=True  + hydraulic WARNING  → CONDITIONAL (hydraulic caution)
  is_compliant=True  + hydraulic FAIL     → CONDITIONAL (has remediation) | FAIL (no fix)
  is_compliant=False + remediation exists → CONDITIONAL (compliance intervention)
  is_compliant=False + no remediation     → FAIL

Confidence penalties
--------------------
PASS:        0 pts  (full confidence in cost/score)
CONDITIONAL: 10 pts (±40% already, intervention adds uncertainty)
FAIL:        excluded from ranking

This is surfaced in the report as a "Decision Pathway" showing:
  raw result → QA/hydraulic outcome → remediation → re-evaluated result
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any


FEASIBILITY_PASS        = "PASS"
FEASIBILITY_CONDITIONAL = "CONDITIONAL"
FEASIBILITY_FAIL        = "FAIL"


@dataclass
class FeasibilityStatus:
    scenario_name:      str
    status:             str            # PASS | CONDITIONAL | FAIL
    compliance_gate:    str            # "Met" | "Requires intervention" | "Failed"
    hydraulic_gate:     str            # "PASS" | "WARNING" | "FAIL"
    remediation_label:  Optional[str]  # name of fixed scenario, if any
    confidence_penalty: float          # pts to subtract from score (0 / 10)
    rationale:          str            # one-sentence explanation
    # For CONDITIONAL — the specific intervention required
    intervention_note:  str = ""


def compute_feasibility(
    scenarios:         List[Any],                  # List[ScenarioModel]
    hydraulic_results: Dict[str, Any],             # Dict[name, HydraulicStressResult]
    remediation_results: List[Any],                # List[RemediationResult]
) -> Dict[str, FeasibilityStatus]:
    """
    Compute the Unified Engineering Feasibility Status for every scenario.

    Returns dict of scenario_name → FeasibilityStatus.
    """
    # Build remediation lookup: base_scenario_name → RemediationResult
    rem_by_base: Dict[str, Any] = {}
    for rem in (remediation_results or []):
        rem_by_base[rem.scenario_name] = rem

    results: Dict[str, FeasibilityStatus] = {}

    for s in scenarios:
        name           = s.scenario_name
        is_compliant   = getattr(s, "is_compliant", True)
        comp_status    = getattr(s, "compliance_status", "")
        hs             = hydraulic_results.get(name) if hydraulic_results else None
        hs_status      = hs.overall_status if hs else "PASS"
        rem            = rem_by_base.get(name)
        rem_label      = rem.modified_scenario.scenario_name if (rem and rem.modified_scenario) else None

        # ── Determine unified status ──────────────────────────────────────
        if is_compliant and hs_status == "PASS":
            status  = FEASIBILITY_PASS
            c_gate  = "Met"
            h_gate  = "PASS"
            penalty = 0.0
            reason  = "Meets all effluent targets and passes hydraulic stress testing."
            note    = ""

        elif is_compliant and hs_status == "WARNING":
            status  = FEASIBILITY_CONDITIONAL
            c_gate  = "Met"
            h_gate  = "WARNING"
            penalty = 10.0
            reason  = ("Meets effluent targets. Hydraulic check warns at peak flow — "
                       "confirm with site-specific hydraulic modelling.")
            note    = hs.narrative if hs else ""

        elif is_compliant and hs_status == "FAIL":
            if rem and rem.feasible:
                status  = FEASIBILITY_CONDITIONAL
                c_gate  = "Met"
                h_gate  = "FAIL → fix available"
                penalty = 10.0
                reason  = (f"Meets effluent targets but fails hydraulic check at peak flow. "
                           f"Remediation available: {rem.fix_description[:60]}.")
                note    = rem.fix_description
            else:
                status  = FEASIBILITY_FAIL
                c_gate  = "Met"
                h_gate  = "FAIL — no fix"
                penalty = 0.0   # excluded entirely
                reason  = ("Meets effluent targets but fails hydraulic check. "
                           "No standard remediation available — specialist redesign required.")
                note    = ""

        elif not is_compliant:
            if rem and rem.feasible:
                status  = FEASIBILITY_CONDITIONAL
                c_gate  = "Requires intervention"
                h_gate  = hs_status
                penalty = 10.0
                reason  = (f"Does not meet effluent targets as modelled. "
                           f"Compliance achievable with: {rem.fix_description[:60]}.")
                note    = rem.fix_description
            else:
                status  = FEASIBILITY_FAIL
                c_gate  = "Failed"
                h_gate  = hs_status
                penalty = 0.0
                reason  = ("Does not meet effluent targets as modelled. "
                           "No standard remediation available.")
                note    = ""
        else:
            status  = FEASIBILITY_PASS
            c_gate  = "Met"
            h_gate  = hs_status
            penalty = 0.0
            reason  = "Engineering feasibility confirmed."
            note    = ""

        results[name] = FeasibilityStatus(
            scenario_name      = name,
            status             = status,
            compliance_gate    = c_gate,
            hydraulic_gate     = h_gate,
            remediation_label  = rem_label,
            confidence_penalty = penalty,
            rationale          = reason,
            intervention_note  = note,
        )

    return results


def apply_confidence_penalties(
    scored_options:    List[Any],        # List[ScoredOption] from ScoringEngine
    feasibility:       Dict[str, FeasibilityStatus],
) -> List[Any]:
    """
    Apply confidence penalties to scored options based on feasibility status.
    Returns the same list with .total_score adjusted.

    This is applied AFTER normalisation — it is a transparent penalty,
    not a distortion of the normalisation. The adjustment is shown in the
    report alongside the base score so reviewers can see both values.
    """
    for opt in scored_options:
        fs = feasibility.get(opt.scenario_name)
        if fs and fs.confidence_penalty > 0 and opt.is_eligible:
            # Store original for transparency
            opt.base_score     = opt.total_score
            opt.confidence_adj = -fs.confidence_penalty
            opt.total_score    = round(opt.total_score - fs.confidence_penalty, 1)
    return scored_options
