"""
WaterPoint — Refinement Layer (Phase 1 → Phase 2 Upgrade Path)
==============================================================
Evaluates Phase 1 outputs and returns a structured prompt that guides
the user toward Phase 2 brownfield asset analysis.

This module is pure-Python (no Streamlit). Streamlit rendering is
handled by waterpoint_ui.py, which calls evaluate_refinement_trigger()
and passes the result to _render_refinement_section().

Entry point:
    trigger = evaluate_refinement_trigger(ctx, confidence_score)

Returns:
    RefinementTrigger — describes whether and how to prompt refinement.

Uplift:
    apply_refinement_uplift(confidence_score, data_confidence, ctx)
    → (refined_score, delta, cap_applied, reasons)
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Any, List, Tuple, Optional

# ── Severity constants ────────────────────────────────────────────────────────
SEV_HIGH   = "HIGH"
SEV_MEDIUM = "MEDIUM"
SEV_LOW    = "LOW"
SEV_NONE   = "NONE"   # no trigger

# ── Result containers ─────────────────────────────────────────────────────────

@dataclass
class RefinementTrigger:
    """Output of evaluate_refinement_trigger()."""
    triggered:      bool            # whether to show the refinement prompt
    severity:       str             # HIGH | MEDIUM | LOW | NONE
    reasons:        List[str]       # human-readable trigger reasons
    body_text:      str             # dynamic body copy based on severity
    input_scope:    List[str]       # what data to request in Phase 2
    cap_score:      int             # confidence cap for this scenario type
    # Trigger flags (individual, for display / logging)
    low_confidence:          bool = False
    brownfield_mode:         bool = False
    high_flow_ratio:         bool = False
    tight_tn:                bool = False
    clarifier_flag:          bool = False
    aeration_flag:           bool = False
    carbon_flag:             bool = False
    sludge_flag:             bool = False


@dataclass
class RefinementResult:
    """
    Comparison between Phase 1 and Phase 2 confidence.
    Produced after the user provides plant data and
    apply_refinement_uplift() is called.
    """
    original_score:  int
    refined_score:   int
    delta:           int
    cap_applied:     bool
    cap_value:       int
    uplift_reasons:  List[str]       # what data improved confidence
    display_text:    str             # e.g. "Refined Confidence: 75 (+15 from plant data)"


# ── Part 1: Trigger evaluation ────────────────────────────────────────────────

def evaluate_refinement_trigger(
    ctx: Dict[str, Any],
    confidence_score: int,
) -> RefinementTrigger:
    """
    Evaluate whether to prompt Phase 2 refinement and at what severity.

    Parameters
    ----------
    ctx             : plant_context dict from build_upgrade_pathway / _build_context
    confidence_score: integer 0–100 from build_compliance_report

    Returns
    -------
    RefinementTrigger
    """
    # ── Extract signals ───────────────────────────────────────────────────────
    flow_ratio    = float(ctx.get("flow_ratio",    1.0) or 1.0)
    tn_tgt        = float(ctx.get("tn_target_mg_l", 10.) or 10.)
    greenfield    = bool(ctx.get("greenfield",     False))
    brownfield    = not greenfield

    cl_flag  = bool(ctx.get("clarifier_overloaded", False) or
                    (ctx.get("svi_ml_g") or 0.) >= 140.)
    aer_flag = bool(ctx.get("aeration_constrained", False))
    c_flag   = bool(ctx.get("carbon_limited_tn",   False))
    sl_flag  = bool(ctx.get("high_load",           False) or
                    ctx.get("_sludge_limited",     False))

    # ── Part 1: Trigger conditions ────────────────────────────────────────────
    t_low_conf   = confidence_score < 70
    t_brownfield = brownfield
    t_flow       = flow_ratio >= 2.5
    t_tight_tn   = tn_tgt <= 5.
    t_constraint = cl_flag or aer_flag or c_flag or sl_flag

    triggered = t_low_conf or t_brownfield or t_flow or t_tight_tn or t_constraint

    if not triggered:
        return RefinementTrigger(
            triggered=False, severity=SEV_NONE, reasons=[],
            body_text="", input_scope=[], cap_score=85)

    # ── Collect human-readable reasons ───────────────────────────────────────
    reasons: List[str] = []
    if t_low_conf:
        reasons.append(f"Confidence is {confidence_score}/100 — below the 70-point threshold for high-reliability outputs.")
    if t_brownfield:
        reasons.append("Brownfield scenario — plant-specific data will improve accuracy.")
    if t_flow and not t_brownfield:
        reasons.append(f"Peak flow ratio {flow_ratio:.1f}× — hydraulic risk may be over- or under-estimated without plant data.")
    if t_tight_tn:
        reasons.append(f"TN target {tn_tgt:.0f} mg/L — tight compliance targets increase sensitivity to input assumptions.")
    if cl_flag:
        reasons.append("Clarifier constraint identified — settling performance needs site confirmation.")
    if aer_flag:
        reasons.append("Aeration system near capacity — actual blower headroom needs verification.")
    if c_flag:
        reasons.append("Carbon limitation flagged — influent COD fractionation not confirmed.")
    if sl_flag:
        reasons.append("Sludge system constraint — dewatering and disposal capacity needs verification.")

    # ── Part 1: Severity ──────────────────────────────────────────────────────
    if confidence_score < 50 or flow_ratio >= 3. or tn_tgt <= 3.:
        severity = SEV_HIGH
    elif confidence_score < 70 or t_constraint:
        severity = SEV_MEDIUM
    else:
        severity = SEV_LOW

    # ── Part 2: UI body copy ──────────────────────────────────────────────────
    body_map = {
        SEV_HIGH:   ("This solution carries significant uncertainty. "
                     "Add plant-specific data to confirm feasibility and reduce delivery risk."),
        SEV_MEDIUM: ("This assessment is based on typical assumptions. "
                     "Add plant data to improve accuracy and confidence."),
        SEV_LOW:    "Add plant-specific data to refine this solution for your site.",
    }
    body_text = body_map[severity]

    # ── Part 3: Input scope ───────────────────────────────────────────────────
    input_scope: List[str] = []
    if cl_flag or t_flow:
        input_scope.append("Clarifier performance — SVI or limitation flag")
    if aer_flag:
        input_scope.append("Blower capacity and utilisation")
    input_scope.append("Tank volumes and functions")
    if sl_flag:
        input_scope.append("Sludge handling capacity")
    if c_flag or tn_tgt <= 5.:
        input_scope.append("Known operational constraints (carbon, temperature, storm)")
    # Always include at least 4 items
    defaults = [
        "Tank volumes and functions",
        "Blower capacity and utilisation",
        "Clarifier performance (SVI or limitation flag)",
        "Sludge handling capacity",
        "Known operational constraints",
    ]
    for d in defaults:
        if d not in input_scope:
            input_scope.append(d)
        if len(input_scope) >= 5:
            break

    # ── Part 4: Confidence cap ────────────────────────────────────────────────
    if flow_ratio >= 3. or tn_tgt <= 3.:
        cap_score = 90   # complex brownfield
    else:
        cap_score = 85   # moderate scenarios

    return RefinementTrigger(
        triggered=True,
        severity=severity,
        reasons=reasons,
        body_text=body_text,
        input_scope=input_scope,
        cap_score=cap_score,
        low_confidence  = t_low_conf,
        brownfield_mode = t_brownfield,
        high_flow_ratio = t_flow,
        tight_tn        = t_tight_tn,
        clarifier_flag  = cl_flag,
        aeration_flag   = aer_flag,
        carbon_flag     = c_flag,
        sludge_flag     = sl_flag,
    )


# ── Part 4: Scoring uplift model ──────────────────────────────────────────────

def apply_refinement_uplift(
    confidence_score: int,
    data_confidence:  int,
    ctx: Dict[str, Any],
) -> RefinementResult:
    """
    Compute the confidence uplift that results from adding plant data.

    Parameters
    ----------
    confidence_score : Phase 1 confidence (0–100)
    data_confidence  : BrownfieldAssetResult.data_confidence (0–100)
    ctx              : plant_context dict

    Returns
    -------
    RefinementResult with refined score, delta, and explanatory text.
    """
    flow_ratio = float(ctx.get("flow_ratio", 1.0) or 1.0)
    tn_tgt     = float(ctx.get("tn_target_mg_l", 10.) or 10.)

    # ── Uplift from data completeness ─────────────────────────────────────────
    if data_confidence >= 85:
        uplift = 15
    elif data_confidence >= 70:
        uplift = 10
    elif data_confidence >= 50:
        uplift = 5
    else:
        uplift = 0

    # ── Cap ───────────────────────────────────────────────────────────────────
    if flow_ratio >= 3. or tn_tgt <= 3.:
        cap = 90
    else:
        cap = 85

    raw_refined   = confidence_score + uplift
    refined_score = min(raw_refined, cap)
    delta         = refined_score - confidence_score
    cap_applied   = raw_refined > cap

    # ── Uplift reason strings ─────────────────────────────────────────────────
    uplift_reasons: List[str] = []
    cl_flag  = bool(ctx.get("clarifier_overloaded") or (ctx.get("svi_ml_g") or 0.) >= 140.)
    aer_flag = bool(ctx.get("aeration_constrained"))
    sl_flag  = bool(ctx.get("high_load") or ctx.get("_sludge_limited"))
    c_flag   = bool(ctx.get("carbon_limited_tn"))

    if data_confidence >= 85:
        if cl_flag:
            uplift_reasons.append("confirmed clarifier capacity")
        if aer_flag:
            uplift_reasons.append("verified aeration headroom")
        if sl_flag:
            uplift_reasons.append("confirmed sludge handling capacity")
        if c_flag:
            uplift_reasons.append("influent carbon characterisation provided")
        if not uplift_reasons:
            uplift_reasons.append("reduced uncertainty in constraints")
    elif data_confidence >= 70:
        uplift_reasons.append("key constraints partially confirmed")
    elif data_confidence >= 50:
        uplift_reasons.append("some data provided — further detail would improve confidence")
    else:
        uplift_reasons.append("insufficient plant data — no uplift applied")

    # ── Display text ──────────────────────────────────────────────────────────
    if delta > 0 and cap_applied:
        display_text = (
            f"Refined Confidence: {refined_score} (+{delta} from plant data, "
            f"capped at {cap})"
        )
    elif delta > 0:
        display_text = f"Refined Confidence: {refined_score} (+{delta} from plant data)"
    elif delta == 0 and cap_applied:
        display_text = (
            f"Refined Confidence: {refined_score} "
            f"(capped at {cap} — complex scenario ceiling)"
        )
    else:
        display_text = (
            f"Refined Confidence: {refined_score} "
            f"(no uplift — additional data required)"
        )

    return RefinementResult(
        original_score  = confidence_score,
        refined_score   = refined_score,
        delta           = delta,
        cap_applied     = cap_applied,
        cap_value       = cap,
        uplift_reasons  = uplift_reasons,
        display_text    = display_text,
    )


# ── Comparison helper ─────────────────────────────────────────────────────────

def build_comparison_summary(
    phase1_drivers:  List[str],
    phase2_drivers:  List[str],
    phase1_stack:    List[str],
    phase2_stack:    List[str],
    refinement:      RefinementResult,
) -> Dict[str, Any]:
    """
    Part 7: Build the data structure for the Compare Initial vs Refined view.

    Returns a dict with score_change, stack_diff, and driver_changes.
    """
    added_drivers   = [d for d in phase2_drivers if d not in phase1_drivers]
    removed_drivers = [d for d in phase1_drivers  if d not in phase2_drivers]
    added_stages    = [s for s in phase2_stack    if s not in phase1_stack]
    removed_stages  = [s for s in phase1_stack    if s not in phase2_stack]

    return {
        "score_change":     refinement.delta,
        "original_score":   refinement.original_score,
        "refined_score":    refinement.refined_score,
        "cap_applied":      refinement.cap_applied,
        "cap_value":        refinement.cap_value,
        "added_drivers":    added_drivers,
        "removed_drivers":  removed_drivers,
        "added_stages":     added_stages,
        "removed_stages":   removed_stages,
        "stack_unchanged":  (phase1_stack == phase2_stack),
        "uplift_reasons":   refinement.uplift_reasons,
    }
