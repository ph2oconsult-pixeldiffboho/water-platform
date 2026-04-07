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
class RegulatoryDriver:
    """An additional regulatory, environmental, or system-level trigger."""
    name:           str    # driver label
    classification: str    # 'compliance' | 'strategic' | 'system'
    implication:    str    # plain-language consequence
    priority:       int    # 1 = highest (see Part 5 priority order)


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

    # Part (new) — Regulatory and strategic drivers
    regulatory_drivers:   List["RegulatoryDriver"] = None

    # Mode flag
    is_greenfield:        bool = False

    def __post_init__(self):
        if self.regulatory_drivers is None:
            object.__setattr__(self, 'regulatory_drivers', [])


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
    svi_p95    = float(ctx.get("svi_p95",          0.) or
                       ctx.get("svi_design",       0.) or svi)
    svi_range  = bool(ctx.get("svi_range_known",  False))
    ss_material= bool(ctx.get("sidestream_material", False))
    ss_nh4_pct = float(ctx.get("ss_nh4_pct",       0.) or 0.)
    thp        = bool(ctx.get("thp_present",      False))
    thp_nh4_inc= float(ctx.get("thp_nh4_inc_pct",  0.) or 0.)
    ss_treat   = bool(ctx.get("ss_treatment_present", False))
    # SF-03: existing hydraulic relief
    ehr        = ctx.get("existing_hydraulic_relief", "None") or "None"
    # SF-04: THP high-severity flag (defined here so it is in scope for both GF and BF branches)
    _thp_high  = thp and thp_nh4_inc >= 50. and tn_tgt <= 5.
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
    _svi_design_ap = svi_p95 if svi_p95 > 0 else svi
    if _svi_design_ap >= 100. or svi >= 100. or cl_over:
        _svi_above = _svi_design_ap >= 140. or svi >= 140.
        _svi_extra = " SVI variability is high; P95 design case used." if svi_range else ""
        tipping_points.append(TippingPoint(
            name    = "Clarifier settling tipping point",
            trigger = (f"When average SVI rises above 140 mL/g "
                       f"(currently {'above' if _svi_above else 'approaching'} threshold)"
                       + _svi_extra),
            consequence = ("Clarifier overflow risk emerges under peak flow. "
                           "Sludge blanket management becomes operationally critical."),
        ))
    # SVI P95 / variability tipping point
    if svi_range or svi_p95 >= 180.:
        tipping_points.append(TippingPoint(
            name    = "SVI variability tipping point",
            trigger = f"High-SVI tail events (P95 SVI {svi_p95:.0f} mL/g) at design peak flow",
            consequence = ("Clarifier risk driven by SVI tail, not median. "
                           "Conservative design case understates peak-flow clarifier stress."),
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
            trigger = ("When effective COD:TN ratio falls below 4.5 or licence "
                       "tightens to TN ≤ 5 mg/L due to catchment change or dilution"),
            consequence = ("Biological denitrification cannot reliably close the gap. "
                           "Tertiary nitrogen closure (DNF or PdNA) becomes required."),
        ))
    # Sidestream / THP tipping point
    if ss_material or thp:
        tipping_points.append(TippingPoint(
            name    = "Return liquor / sidestream tipping point",
            trigger = (f"Return liquor NH₄ contributes {ss_nh4_pct:.0f}% of mainstream TKN load"
                       + ("; THP amplifies this further" if thp else "")),
            consequence = ("Mainstream nitrification load is materially increased. "
                           "Nitrification capacity sizing must reflect sidestream load. "
                           "Sidestream treatment (PN/A or equivalent) should be evaluated."),
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

    # (Cap is applied by the extended trigger engine at end of function)

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
        # SF-03: CoMag label depends on existing hydraulic relief
        _comag_label = (
            "CoMag (enhanced hydraulic capacity beyond existing CAS)"
            if ehr == "CAS" else "CoMag (peak flow ballasted clarification)"
        )
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
        # SF-04: promote sidestream PN/A to Stage 1 when THP ≥50% and TN≤5
        if _thp_high:
            s1_stack.append("Sidestream PN/A evaluation (Stage 1 priority — THP NH₄ surge ≥50%)")
            s1_solves = s1_solves + (
                " Sidestream PN/A must be evaluated at Stage 1: THP-driven NH₄ "
                "increase of ≥50% is a compliance event under TN ≤ 5 mg/L."
            )
        s1_trigger = ("Triggered when: current performance is within 85% of licence limit, "
                      "seasonal compliance risk is identified, or hydraulic headroom is exhausted.")

        # Stage 2: secondary intensification or hydraulic relief
        s2_stack = []
        if storm or fr >= 2.5:
            s2_stack.append(_comag_label)
        if tn_tgt <= 5. and not gap:
            s2_stack.append("Denitrification Filter or PdNA")
        # SF-04: sidestream PN/A already in Stage 1 if THP ≥50%; add at Stage 2 otherwise
        if (ss_material or thp) and not _thp_high:
            s2_stack.append("Sidestream ammonia treatment (PN/A — evaluate feasibility)")
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

    # SF-03: CAS vs CoMag transition decision point
    if ehr == "CAS" and (storm or fr >= 2.5):
        decision_points.append(DecisionPoint(
            issue  = "evaluate upgrade of existing CAS system vs transition to CoMag ballasted clarification",
            before = "Stage 1 — before committing to hydraulic relief capital expenditure",
        ))
    # SF-04 + original: Sidestream / THP decision points
    if ss_material or thp:
        decision_points.append(DecisionPoint(
            issue  = "confirm sidestream TKN load and THP ammonia surge through return liquor monitoring",
            before = "Stage 1 — before finalising nitrification capacity sizing",
        ))
        if _thp_high and not ss_treat:
            decision_points.append(DecisionPoint(
                issue  = "sidestream ammonia treatment must be evaluated prior to mainstream upgrade "
                         "(THP NH₄ surge ≥50% is a compliance event under TN ≤ 5 mg/L)",
                before = "Stage 1 — before committing to mainstream nitrification capital",
            ))
        elif not ss_treat and tn_tgt <= 5.:
            decision_points.append(DecisionPoint(
                issue  = "evaluate sidestream ammonia treatment (PN/A or equivalent) "
                         "to reduce mainstream nitrogen load",
                before = "Stage 2 or Stage 3 — where TN compliance is tight",
            ))
    # Licence trajectory DP (moved after sidestream to preserve slot priority)
    if tn_tgt <= 5. and gap:
        decision_points.append(DecisionPoint(
            issue  = "confirm future licence trajectory with the regulator",
            before = "Stage 2 or 3 — to determine whether TN ≤ 5 or TN ≤ 3 is the design target",
        ))
    # Carbon characterisation decision point
    if carbon_lim and not any("carbon" in dp.issue.lower() for dp in decision_points):
        decision_points.append(DecisionPoint(
            issue  = "confirm tertiary nitrogen closure technology (DNF vs PdNA) through "
                     "influent carbon fractionation and temperature feasibility assessment",
            before = "Stage 2 — before committing to methanol dosing infrastructure",
        ))

    if not decision_points:
        decision_points.append(DecisionPoint(
            issue  = "confirm future licence requirements and catchment growth projections",
            before = "Stage 2 — to calibrate the timing and scale of the next pathway stage",
        ))

    # Cap at 4
    decision_points = decision_points[:6]

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
    if ss_material or thp:
        _thp_note = "; THP increases this significantly" if thp else ""
        monitoring.append(
            f"Return liquor ammonia — daily during dewatering; currently {ss_nh4_pct:.0f}% of "
            f"mainstream TKN load{_thp_note}; alert if load exceeds 15%"
        )
        if _thp_high:
            monitoring.append(
                f"THP-driven NH₄ load during dewatering cycle — log peak NH₄ mass per event; "
                f"THP NH₄ increase of {thp_nh4_inc:.0f}% requires dedicated sidestream monitoring"
            )
    else:
        monitoring.append(
            "Return liquor ammonia — daily during dewatering; alert if sidestream TKN load "
            "exceeds 10% of mainstream TKN load"
        )
    # SVI variability monitoring
    if svi_range or svi_p95 >= 150.:
        monitoring.append(
            f"SVI distribution — track P95 SVI trend; current design case "
            f"{svi_p95:.0f} mL/g; re-assess inDENSE relevance if P95 exceeds 180 mL/g"
        )
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


    # ─────────────────────────────────────────────────────────────────────────
    # Extended Trigger Engine (Parts 1–5 of the trigger spec)
    # ─────────────────────────────────────────────────────────────────────────
    regulatory_drivers: List[RegulatoryDriver] = []

    # Read new ctx flags
    tp_tgt_v2   = float(ctx.get("tp_target_mg_l",  1.0) or 1.0)
    reuse_flag  = bool(ctx.get("reuse_flag",        False))
    ecoli_tight = bool(ctx.get("ecoli_tight",       False) or reuse_flag)
    pfas_flag   = bool(ctx.get("pfas_flag",         False))
    micro_flag  = bool(ctx.get("microplastics_flag",False))
    ec_flag     = bool(ctx.get("emerging_contaminants_flag", False))
    growth_rate = float(ctx.get("growth_rate_percent",   0.) or 0.)
    horizon_yr  = float(ctx.get("planning_horizon_years", 20.) or 20.)
    disposal_c  = ctx.get("biosolids_disposal_constraint", "none") or "none"
    sludge_c    = disposal_c in ("cost", "capacity") or bool(ctx.get("high_load", False))

    existing_techs = set(stack_labels)

    # ── Part 1: Hard Compliance Triggers ─────────────────────────────────────

    # 1a. Total Phosphorus
    if tp_tgt_v2 <= 0.1:
        regulatory_drivers.append(RegulatoryDriver(
            name           = "TP ≤ 0.1 mg/L licence",
            classification = "compliance",
            implication    = ("Strong TP compliance trigger — chemical P removal, "
                              "enhanced clarification (CoMag or equivalent), and tertiary "
                              "filtration are mandatory. Biological P alone is insufficient."),
            priority       = 4,
        ))
        # Add to tipping points if not already present
        if not any("phosphorus" in t.name.lower() for t in tipping_points):
            tipping_points.append(TippingPoint(
                name    = "Phosphorus limit tipping point",
                trigger = "TP licence ≤ 0.1 mg/L (currently active)",
                consequence = ("Biological P removal is insufficient. Chemical dosing, "
                               "enhanced clarification, and tertiary filtration are required."),
            ))
        # Add tertiary filtration to Stage 3 if not present
        for s in future_stages:
            if "Stage 3" in s.stage and "filtration" not in " ".join(s.stack).lower():
                s.stack.append("Tertiary filtration (TP polishing)")

    elif tp_tgt_v2 <= 0.5:
        regulatory_drivers.append(RegulatoryDriver(
            name           = "TP ≤ 0.5 mg/L licence",
            classification = "compliance",
            implication    = ("Moderate TP compliance trigger — chemical P removal is likely "
                              "required. Biological P removal alone is unreliable at this target."),
            priority       = 4,
        ))

    # 1b. E. coli / Disinfection
    if ecoli_tight:
        regulatory_drivers.append(RegulatoryDriver(
            name           = "Disinfection / E. coli limit",
            classification = "compliance",
            implication    = ("Reuse or stringent E. coli limits require UV or membrane "
                              "disinfection. Tertiary filtration is a prerequisite if "
                              "effluent solids risk is present."),
            priority       = 4,
        ))
        # Ensure disinfection appears in Stage 3
        for s in future_stages:
            if "Stage 3" in s.stage and "UV" not in " ".join(s.stack):
                s.stack.append("UV disinfection (E. coli / reuse compliance)")

    # 1c. Reuse
    if reuse_flag:
        regulatory_drivers.append(RegulatoryDriver(
            name           = "Recycled water / reuse requirement",
            classification = "compliance",
            implication    = ("Reuse pathway mandates: tertiary filtration, nutrient polishing "
                              "(DNF if TN critical), and disinfection upgrade. "
                              "Advanced treatment train required for Class A+."),
            priority       = 4,
        ))
        if not any("reuse" in s.purpose.lower() or "reuse" in " ".join(s.stack).lower()
                   for s in future_stages):
            # Replace Stage 3 or append if only 2 stages exist
            if len(future_stages) >= 3:
                s3 = future_stages[2]
                if "filtration" not in " ".join(s3.stack).lower():
                    s3.stack.append("Tertiary filtration (reuse pre-treatment)")
                if "UV" not in " ".join(s3.stack):
                    s3.stack.append("UV / AOP disinfection")
                s3.purpose = s3.purpose + " Reuse pathway confirmed."
        decision_points.append(DecisionPoint(
            issue  = "confirm recycled water class and pathogen log-reduction requirements",
            before = "Stage 3 — before committing to advanced treatment train selection",
        ))
        monitoring.append(
            "Effluent TSS and turbidity — daily for reuse pre-treatment compliance"
        )

    # ── Part 2: Strategic / Emerging Triggers ────────────────────────────────

    # 2a. PFAS
    if pfas_flag:
        regulatory_drivers.append(RegulatoryDriver(
            name           = "PFAS regulatory risk",
            classification = "strategic",
            implication    = ("Future PFAS removal stage likely required — GAC, IX, or "
                              "NF/RO membrane. Does not alter biological or hydraulic stack. "
                              "Biosolids PFAS may constrain land application."),
            priority       = 6,
        ))
        # Add future pathway stage — does NOT modify biological stack
        future_stages.append(PathwayStageAP(
            stage   = "Stage 4 — PFAS management (future)",
            purpose = "Address PFAS removal from liquid and biosolids streams as regulation tightens.",
            stack   = ["GAC (granular activated carbon) or IX (ion exchange)",
                       "NF/RO membrane (if required for reuse or stringent limits)",
                       "PFAS-compliant biosolids management pathway"],
            solves  = ("PFAS removal from treated effluent and management of PFAS-affected "
                       "biosolids. Avoids regulatory non-compliance as limits are set."),
            trigger = ("Triggered when: PFAS licence values are set, biosolids land "
                       "application is restricted, or reuse pathway requires PFAS removal."),
        ))
        tipping_points.append(TippingPoint(
            name    = "PFAS regulatory tipping point",
            trigger = "When PFAS licence limits are established or biosolids land application is restricted",
            consequence = ("Advanced adsorption or membrane treatment required. Biosolids "
                           "disposal pathway must be reviewed."),
        ))
        decision_points.append(DecisionPoint(
            issue  = "confirm PFAS concentrations in influent and biosolids through targeted sampling",
            before = "Stage 4 — before selecting GAC, IX, or membrane technology",
        ))
        monitoring.append(
            "PFAS influent concentration — quarterly sampling until regulatory limits are set"
        )

    # 2b. Microplastics
    if micro_flag:
        regulatory_drivers.append(RegulatoryDriver(
            name           = "Microplastics",
            classification = "strategic",
            implication    = ("Tertiary filtration and enhanced clarification are favoured — "
                              "these provide incidental microplastic removal. "
                              "No dedicated process required at current regulatory maturity."),
            priority       = 6,
        ))
        monitoring.append(
            "Microplastic removal performance — periodic monitoring as regulatory framework develops"
        )

    # 2c. Emerging contaminants
    if ec_flag:
        regulatory_drivers.append(RegulatoryDriver(
            name           = "Emerging contaminants",
            classification = "strategic",
            implication    = ("Future advanced oxidation or adsorption stage may be required "
                              "as limits are established. Core BNR logic is unaffected."),
            priority       = 6,
        ))
        future_stages.append(PathwayStageAP(
            stage   = "Stage 4 — Emerging contaminants (future)",
            purpose = "Address trace organic contaminants (pharmaceuticals, hormones, etc.) as regulation develops.",
            stack   = ["Advanced oxidation (O₃/H₂O₂ or UV/AOP)",
                       "Activated carbon adsorption (GAC or PAC)"],
            solves  = ("Removal of trace organics, EDCs, and pharmaceuticals not addressed "
                       "by conventional biological treatment."),
            trigger = ("Triggered when: regulatory limits are set for specific compounds, "
                       "receiving water sensitivity is identified, or reuse pathway requires "
                       "trace organic removal."),
        ))

    # ── Part 3: System / External Triggers ───────────────────────────────────

    # 3a. Population growth
    if growth_rate > 0 and horizon_yr > 0:
        projected_ratio = (1 + growth_rate / 100.) ** horizon_yr
        if projected_ratio >= 2.0:
            regulatory_drivers.append(RegulatoryDriver(
                name           = f"Population growth ({growth_rate:.1f}%/yr × {int(horizon_yr)} yr)",
                classification = "system",
                implication    = (f"Projected flow ≥ {projected_ratio:.1f}× current ADWF over "
                                  f"{int(horizon_yr)} years. Stage 2 and Stage 3 upgrades "
                                  "required within planning horizon. Stage 3 is a major "
                                  "capacity expansion or process replacement."),
                priority       = 5,
            ))
            tipping_points.append(TippingPoint(
                name    = "Growth-driven capacity tipping point",
                trigger = (f"When ADWF reaches {min(projected_ratio, 1.5):.1f}× current flow "
                           f"(Stage 2) or {min(projected_ratio, 2.0):.1f}× (Stage 3)"),
                consequence = ("Hydraulic and biological capacity is exceeded. Major "
                               "process augmentation or replacement is required."),
            ))
        elif projected_ratio >= 1.4:  # ~2%/yr × 20yr = 1.49× — catch moderate growth
            regulatory_drivers.append(RegulatoryDriver(
                name           = f"Population growth ({growth_rate:.1f}%/yr × {int(horizon_yr)} yr)",
                classification = "system",
                implication    = (f"Projected flow ≥ {projected_ratio:.1f}× current ADWF — "
                                  "Stage 2 upgrade required within planning horizon."),
                priority       = 5,
            ))
        if projected_ratio >= 1.4:
            monitoring.append(
                f"ADWF trend — annual flow reconciliation against {growth_rate:.1f}%/yr growth projection"
            )

    # 3b. Biosolids disposal constraint
    if sludge_c:
        regulatory_drivers.append(RegulatoryDriver(
            name           = "Biosolids disposal constraint",
            classification = "system",
            implication    = ("Sludge disposal pathway is cost- or capacity-constrained. "
                              "High-sludge processes are penalised. Sludge minimisation, "
                              "thermal hydrolysis, enhanced digestion, or drying are favoured."),
            priority       = 5,
        ))
        for s in future_stages:
            if "Stage 2" in s.stage or "Stage 3" in s.stage:
                if not any("sludge" in t.lower() or "biosolids" in t.lower()
                           for t in s.stack):
                    s.stack.append("Sludge minimisation / enhanced digestion (biosolids pathway)")
                break
        decision_points.append(DecisionPoint(
            issue  = "confirm long-term biosolids disposal pathway and gate cost",
            before = "Stage 1 — before selecting high-yield biological processes",
        ))
        monitoring.append(
            "Sludge production and dewatering performance — monthly mass balance against disposal capacity"
        )

    # ── Part 5: Sort regulatory_drivers by priority ───────────────────────────
    regulatory_drivers.sort(key=lambda d: d.priority)

    # ── Re-cap lists after trigger engine additions ───────────────────────────
    tipping_points  = tipping_points[:7]   # extended cap for richer scenarios
    future_stages   = future_stages[:5]    # allow up to 5 with PFAS/EC stages
    decision_points = decision_points[:5]
    monitoring      = monitoring[:8]

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
        regulatory_drivers   = regulatory_drivers,
        is_greenfield        = gf,
    )
