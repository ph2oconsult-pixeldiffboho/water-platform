"""
WaterPoint — Adaptive Pathways Mode
=====================================
Produces a staged, forward-looking planning output:

    Current Pathway → Tipping Points → Future Stages → Decision Points → Monitoring

Entry point:
    result = build_adaptive_pathways(pathway, compliance_report, ctx)

Returns:
    AdaptivePathwaysResult  — ready for rendering in waterpoint_ui.py (E9 section)

This module reads existing compliance and pathway outputs — it does not
re-run physics or alter scores.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ─────────────────────────────────────────────────────────────────────────────
# Dataclasses
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class TippingPoint:
    name:        str          # short label
    trigger:     str          # condition that fires it
    consequence: str          # what becomes non-credible


@dataclass
class PathwayStageAP:
    stage:    str             # "Stage 1 — Near-term", etc.
    purpose:  str
    stack:    List[str]       # technology labels
    solves:   str             # what problem it addresses
    trigger:  str             # why it fires


@dataclass
class DecisionPoint:
    issue:   str              # uncertainty requiring resolution
    before:  str              # which pathway stage it gates


@dataclass
class AdaptivePathwaysResult:
    # Part 3 — Baseline
    baseline_stack:       List[str]
    baseline_confidence:  int
    baseline_label:       str
    baseline_constraint:  str
    baseline_summary:     str

    # Part 4 — Tipping points
    tipping_points:       List[TippingPoint]

    # Part 5 — Future stages
    future_stages:        List[PathwayStageAP]

    # Part 6 — Decision points
    decision_points:      List[DecisionPoint]

    # Part 7 — Monitoring priorities
    monitoring:           List[str]

    # Mode flag
    is_greenfield:        bool = False


# ─────────────────────────────────────────────────────────────────────────────
# Main builder
# ─────────────────────────────────────────────────────────────────────────────

def build_adaptive_pathways(
    pathway,          # UpgradePathway
    co,               # ComplianceReport
    ctx: Dict[str, Any],
) -> AdaptivePathwaysResult:
    """
    Build an Adaptive Pathways planning output from existing WaterPoint results.

    Parameters
    ----------
    pathway  : UpgradePathway from build_upgrade_pathway()
    co       : ComplianceReport from build_compliance_report()
    ctx      : plant_context dict

    Returns
    -------
    AdaptivePathwaysResult
    """
    gf         = bool(ctx.get("greenfield", False))
    fr         = float(ctx.get("flow_ratio",      1.5) or 1.5)
    tn_tgt     = float(ctx.get("tn_target_mg_l",  10.) or 10.)
    tp_tgt     = float(ctx.get("tp_target_mg_l",  1.0) or 1.0)
    svi        = float(ctx.get("svi_ml_g",         0.) or 0.)
    cold       = bool(ctx.get("cold_temperature", False))
    aer_con    = bool(ctx.get("aeration_constrained", False))
    cl_over    = bool(ctx.get("clarifier_overloaded", False))
    carbon_lim = bool(ctx.get("carbon_limited_tn", False))
    storm      = bool(ctx.get("overflow_risk", False))
    op_remote  = ctx.get("location_type", "metro") in ("remote", "regional")
    fp         = ctx.get("footprint_constraint", "abundant")
    score      = co.confidence_score
    score_lbl  = co.confidence_label
    drivers    = co.confidence_drivers or []
    gap        = co.stack_compliance_gap
    diag       = co.diagnosis_statement or ""

    # ── Stack labels ────────────────────────────────────────────────────────
    stack_labels = [s.technology for s in pathway.stages]

    # ── Primary constraint description ──────────────────────────────────────
    pc = pathway.primary_constraint
    prim_label = pc.label if pc else "process performance"

    # ── Board summary — derive from diagnosis ────────────────────────────────
    if diag:
        baseline_summary = diag
    elif gap:
        baseline_summary = (
            "The baseline pathway cannot close the compliance gap under current assumptions. "
            "Tertiary intervention is required before the target can be credibly achieved."
        )
    else:
        baseline_summary = (
            "The baseline pathway is the minimum credible set of works required to maintain "
            "compliance and service under current assumptions."
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Part 4: Tipping Points
    # ─────────────────────────────────────────────────────────────────────────
    tipping_points: List[TippingPoint] = []

    # Hydraulic / storm
    if fr >= 2.5 or storm:
        if fr >= 3. or storm:
            tipping_points.append(TippingPoint(
                name    = "Peak flow tipping point",
                trigger = (f"When peak flow ratio exceeds {fr:.1f}× ADWF or storm "
                           "overflow events increase in frequency"),
                consequence = ("Storm stability becomes non-credible. Hydraulic bypass "
                               "risk undermines compliance at P95."),
            ))
        else:
            tipping_points.append(TippingPoint(
                name    = "Hydraulic headroom tipping point",
                trigger = f"When peak flow ratio rises above 3.0× (currently {fr:.1f}×)",
                consequence = ("Peak flow protection moves from adequate to marginal. "
                               "CoMag or equivalent ballasted clarification becomes necessary."),
            ))

    # Clarifier settling
    if svi >= 100. or cl_over:
        tipping_points.append(TippingPoint(
            name    = "Clarifier settling tipping point",
            trigger = (f"When average SVI rises above 140 mL/g "
                       f"(currently {'above' if svi>=140 else 'approaching'} threshold)"),
            consequence = ("Clarifier overflow risk emerges under peak flow. "
                           "Sludge blanket management becomes operationally critical."),
        ))

    # Aeration headroom
    if aer_con or not aer_con:  # always include — it's a universal tipping point
        tipping_points.append(TippingPoint(
            name    = "Aeration headroom tipping point",
            trigger = ("When blower utilisation exceeds 90% under peak conditions "
                       "or load increases tighten the DO margin"),
            consequence = ("Nitrification reliability under winter or peak conditions "
                           "deteriorates. MABR or blower augmentation becomes necessary."),
        ))

    # Carbon limitation
    if carbon_lim or tn_tgt <= 5.:
        tipping_points.append(TippingPoint(
            name    = "Carbon availability tipping point",
            trigger = ("When licence tightens to TN ≤ 5 mg/L or COD:TN ratio "
                       "falls below 5 due to catchment change or wet weather dilution"),
            consequence = ("Biological denitrification cannot reliably close the gap. "
                           "External carbon dosing or PdNA becomes necessary."),
        ))

    # TN tightening
    if tn_tgt > 5.:
        tipping_points.append(TippingPoint(
            name    = "Licence tightening tipping point",
            trigger = "When the regulatory TN target tightens below 5 mg/L",
            consequence = ("The current biological stack becomes insufficient "
                           "without a tertiary nitrogen closure step."),
        ))

    # Cold temperature
    if cold or float(ctx.get("temp_celsius", 18.) or 18.) <= 14.:
        tipping_points.append(TippingPoint(
            name    = "Cold-season performance tipping point",
            trigger = "When process temperature drops below 12°C for sustained periods",
            consequence = ("Nitrification rate reduces significantly. "
                           "Winter licence compliance risk increases without MABR or SRT extension."),
        ))

    # TP tightening
    if tp_tgt <= 0.5:
        tipping_points.append(TippingPoint(
            name    = "Phosphorus limit tipping point",
            trigger = "When the TP licence tightens below 0.5 mg/L",
            consequence = ("Biological P removal alone is insufficient. "
                           "Chemical dosing and tertiary filtration become necessary."),
        ))

    # Cap at 5 most relevant
    tipping_points = tipping_points[:5]

    # ─────────────────────────────────────────────────────────────────────────
    # Part 5: Future Pathway Stages
    # ─────────────────────────────────────────────────────────────────────────
    future_stages: List[PathwayStageAP] = []

    if gf:
        # ── Greenfield ────────────────────────────────────────────────────────
        conv_score = 0
        int_score  = 0
        for gp in pathway.greenfield_pathways:
            if gp.label == "Conventional": conv_score = gp.confidence
            if gp.label == "Intensified":  int_score  = gp.confidence

        if fp == "abundant" and conv_score >= int_score:
            stage1_stack = ["Conventional BNR (Bardenpho)", "Secondary clarifiers",
                            "Tertiary P removal"]
            stage1_purpose = "Establish a conventional BNR plant sized to current licence and design flow."
            stage1_solves  = "Baseline compliance for TN, TP, and BOD at average conditions."
            stage1_trigger = "Initial commissioning. Full design-flow operation."

            stage2_stack   = ["MABR intensification", "Anoxic zone expansion",
                              "Denitrification Filter (if TN tightens)"]
            stage2_purpose = "Intensify biological performance as flow or licence pressure increases."
            stage2_solves  = "Nitrogen polishing and nitrification reliability under peak conditions."
            stage2_trigger = ("Triggered when: flow reaches 80% design, licence tightens to "
                              "TN ≤ 5 mg/L, or winter nitrification failures are recorded.")
        else:
            stage1_stack   = ["MABR (intensified BNR)", "Bardenpho optimisation",
                              "Tertiary P removal"]
            stage1_purpose = "Establish an intensified BNR plant with reduced footprint."
            stage1_solves  = "Baseline compliance on a constrained site with capable operators."
            stage1_trigger = "Initial commissioning. Compact design justified by site constraints."

            stage2_stack   = ["PdNA integration" if tn_tgt <= 5. else "Denitrification Filter",
                             "Enhanced carbon dosing (if required)"]
            stage2_purpose = "Add tertiary nitrogen closure as licence tightens or carbon limits emerge."
            stage2_solves  = "TN ≤ 5 mg/L P95 compliance without full methanol dependency."
            stage2_trigger = ("Triggered when: TN licence tightens, carbon:TN ratio falls below 4, "
                              "or P95 compliance cannot be achieved by biological stage alone.")

        stage3_stack   = ["Full PdNA or Anammox", "Advanced P removal",
                         "Tertiary filtration + UV (if reuse required)"]
        stage3_purpose = "Close any remaining compliance gaps and enable reuse if required."
        stage3_solves  = "TN ≤ 3 mg/L, TP ≤ 0.1 mg/L, TSS ≤ 2 mg/L for Class A reuse."
        stage3_trigger = ("Triggered when: licence requires TN ≤ 3 mg/L, environmental "
                          "flows demand very low nutrient loads, or reuse pathway is confirmed.")

        future_stages = [
            PathwayStageAP("Stage 1 — Establish baseline", stage1_purpose,
                           stage1_stack, stage1_solves, stage1_trigger),
            PathwayStageAP("Stage 2 — Intensify performance", stage2_purpose,
                           stage2_stack, stage2_solves, stage2_trigger),
            PathwayStageAP("Stage 3 — Tertiary closure", stage3_purpose,
                           stage3_stack, stage3_solves, stage3_trigger),
        ]

    else:
        # ── Brownfield ────────────────────────────────────────────────────────

        # Stage 1: optimisation and constraint relief
        s1_stack   = list(stack_labels[:2]) if stack_labels else ["Process optimisation"]
        s1_stack   = s1_stack or ["Process optimisation"]
        s1_purpose = "Relieve the primary constraint and stabilise current performance."
        if aer_con:
            s1_stack.insert(0, "MABR (aeration intensification)")
            s1_solves  = ("Aeration headroom restored. Nitrification reliability "
                          "improved under peak and winter conditions.")
        elif cl_over or svi >= 120.:
            s1_stack.insert(0, "inDENSE (settling improvement)")
            s1_solves  = ("Clarifier loading reduced. SVI management improves stability "
                          "under sustained high solids conditions.")
        elif carbon_lim:
            s1_solves  = ("Carbon management enabled. Denitrification improved "
                          "without new tankage.")
        else:
            s1_solves  = ("Primary constraint relieved. Process stability improved "
                          "within existing asset envelope.")
        s1_trigger = ("Triggered when: current performance is within 85% of licence limit, "
                      "seasonal compliance risk is identified, or hydraulic headroom is exhausted.")

        # Stage 2: secondary intensification or hydraulic relief
        s2_stack = []
        if storm or fr >= 2.5:
            s2_stack.append("CoMag (peak flow ballasted clarification)")
        if tn_tgt <= 5. and not gap:
            s2_stack.append("Denitrification Filter or PdNA")
        if not s2_stack:
            s2_stack = ["Secondary clarifier upgrade or addition",
                        "Anoxic zone conversion or expansion"]
        s2_purpose = "Provide hydraulic relief and secondary nitrogen polishing."
        s2_solves  = ("Peak flow compliance protected. TN at P95 achievable with "
                      "tertiary polishing element.")
        s2_trigger = ("Triggered when: peak flow ratio exceeds 3.0×, TN P95 compliance "
                      "is not credible without tertiary element, or SVI deterioration "
                      "cannot be managed by Stage 1 alone.")

        # Stage 3: major conversion or replacement
        if gap or score < 30:
            s3_stack = ["Full process conversion (MBR or AGS replacement)",
                       "PdNA or Anammox", "Advanced P removal"]
            s3_purpose = "Replace or fundamentally restructure the biological process to close the compliance gap."
            s3_solves  = ("Compliance gap closed. Tertiary nitrogen and phosphorus "
                          "targets achievable at P95.")
            s3_trigger = ("Triggered when: compliance gap cannot be closed by constraint "
                          "relief alone, catchment load growth exceeds biological capacity, "
                          "or site renewal is required.")
        else:
            s3_stack = ["Tertiary filtration + UV",
                       "PdNA (if TN ≤ 3 mg/L required)",
                       "Sidestream treatment (if AD present)"]
            s3_purpose = "Achieve tertiary licence levels and enable reuse or environmental-flow compliance."
            s3_solves  = ("TN ≤ 3 mg/L, TP ≤ 0.1 mg/L, and TSS polishing for "
                          "reuse or sensitive receiving waters.")
            s3_trigger = ("Triggered when: licence tightens beyond current biological "
                          "capability, reuse pathway is confirmed, or environmental "
                          "flow obligations require near-zero nutrient loads.")

        future_stages = [
            PathwayStageAP("Stage 1 — Constraint relief and stabilisation",
                           s1_purpose, s1_stack, s1_solves, s1_trigger),
            PathwayStageAP("Stage 2 — Hydraulic relief and nitrogen polishing",
                           s2_purpose, s2_stack, s2_solves, s2_trigger),
            PathwayStageAP("Stage 3 — Tertiary closure or process renewal",
                           s3_purpose, s3_stack, s3_solves, s3_trigger),
        ]

    # ─────────────────────────────────────────────────────────────────────────
    # Part 6: Decision Points
    # ─────────────────────────────────────────────────────────────────────────
    decision_points: List[DecisionPoint] = []

    if carbon_lim or tn_tgt <= 5.:
        decision_points.append(DecisionPoint(
            issue  = "confirm biodegradable COD availability through influent carbon fractionation",
            before = "Stage 1 or 2 — before committing to denitrification or PdNA pathway",
        ))

    if svi >= 100. or cl_over:
        decision_points.append(DecisionPoint(
            issue  = "confirm clarifier SVI trend and peak blanket behaviour under storm conditions",
            before = "Stage 1 — before selecting inDENSE vs CoMag as the primary hydraulic intervention",
        ))

    if aer_con:
        decision_points.append(DecisionPoint(
            issue  = "verify actual blower headroom through an aeration demand audit",
            before = "Stage 1 — before sizing MABR or blower augmentation works",
        ))

    if op_remote:
        decision_points.append(DecisionPoint(
            issue  = "confirm operator capability and O&M support availability for intensified process",
            before = "Stage 2 — before committing to MABR, PdNA, or specialist technology selection",
        ))

    if tn_tgt <= 5. and gap:
        decision_points.append(DecisionPoint(
            issue  = "confirm future licence trajectory with the regulator",
            before = "Stage 2 or 3 — to determine whether TN ≤ 5 or TN ≤ 3 is the design target",
        ))

    if not decision_points:
        decision_points.append(DecisionPoint(
            issue  = "confirm future licence requirements and catchment growth projections",
            before = "Stage 2 — to calibrate the timing and scale of the next pathway stage",
        ))

    # Cap at 4
    decision_points = decision_points[:4]

    # ─────────────────────────────────────────────────────────────────────────
    # Part 7: Monitoring Priorities
    # ─────────────────────────────────────────────────────────────────────────
    monitoring: List[str] = []

    if svi >= 100. or cl_over:
        monitoring.append("SVI trend — weekly composite samples; flag if 4-week average exceeds 150 mL/g")
    if aer_con:
        monitoring.append("Blower loading — log peak blower utilisation daily; alert at 90%")
    if storm or fr >= 2.5:
        monitoring.append("Peak flow duration — log events exceeding 2.5× ADWF; record frequency and duration")
    if carbon_lim or tn_tgt <= 5.:
        monitoring.append("Biodegradable COD availability — quarterly fractionation; "
                          "flag if readily biodegradable COD:TN falls below 4")
    monitoring.append("Return liquor ammonia — daily during dewatering; alert if sidestream TKN load "
                      "exceeds 10% of mainstream TKN load")
    if cold or float(ctx.get("temp_celsius", 18.) or 18.) <= 16.:
        monitoring.append("Process temperature — log daily minimum; alert at 12°C for nitrification risk")
    monitoring.append("Effluent TN and NH₄ — weekly composites at minimum; "
                      "increase to daily during winter or post-storm")
    if cl_over or svi >= 100.:
        monitoring.append("Clarifier blanket depth — daily measurement under peak flow events")

    # Ensure at least 3 universal items
    universal = [
        "Effluent TN and NH₄ — weekly composites at minimum; "
        "increase to daily during winter or post-storm",
        "Peak flow duration — log events exceeding 2.5× ADWF; record frequency and duration",
        "Return liquor ammonia — daily during dewatering; alert if sidestream TKN load "
        "exceeds 10% of mainstream TKN load",
    ]
    for u in universal:
        if u not in monitoring:
            monitoring.append(u)
        if len(monitoring) >= 3:
            break

    # Cap at 6
    monitoring = monitoring[:6]

    return AdaptivePathwaysResult(
        baseline_stack       = stack_labels,
        baseline_confidence  = score,
        baseline_label       = score_lbl,
        baseline_constraint  = prim_label,
        baseline_summary     = baseline_summary,
        tipping_points       = tipping_points,
        future_stages        = future_stages,
        decision_points      = decision_points,
        monitoring           = monitoring,
        is_greenfield        = gf,
    )
