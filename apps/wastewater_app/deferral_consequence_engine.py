"""
deferral_consequence_engine.py  —  WaterPoint v24Z75
Deferral Consequence Engine: Delay Impact and Risk Trajectory

Answers: "If we do nothing, what happens next?"

Produces:
- Consequence timeline (0-2 yr, 2-5 yr, 5-10 yr, >10 yr)
- Risk trajectory classification
- Qualitative cost exposure
- Point of no return
- Deferral decision frame per stage
- Board-level "Consequence of Delay" bullets

NOT financial modelling.
NOT capital cost calculation.
Risk trajectory and consequence logic only.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional

# ── Trajectory constants ───────────────────────────────────────────────────────
TRAJ_STABLE       = "Stable"
TRAJ_INCREASING   = "Increasing"
TRAJ_ACCELERATING = "Accelerating"
TRAJ_CRITICAL     = "Critical"

# ── Cost exposure constants ───────────────────────────────────────────────────
COST_LOW      = "Low"
COST_MODERATE = "Moderate"
COST_HIGH     = "High"
COST_SEVERE   = "Severe"


# ── Dataclasses ───────────────────────────────────────────────────────────────

@dataclass
class ConsequenceHorizon:
    """One time-horizon slice in the deferral consequence timeline."""
    horizon:            str   # "Immediate (0–2 years)", etc.
    primary_failure:    str   # what fails first
    system_impact:      str   # physical/process impact
    regulatory_impact:  str   # consent/compliance risk
    operational_impact: str   # operational burden


@dataclass
class StageDefferalFrame:
    """Per-stage deferral decision frame (Part 8)."""
    stage_label:     str
    avoids:          str   # what deferral avoids
    introduces_risk: str   # what risk it introduces
    failure_mode:    str   # likely manifest failure mode
    time_horizon:    str   # when failure likely emerges


@dataclass
class DeferralConsequenceResult:
    """Full deferral consequence analysis output."""
    is_active:              bool
    consequence_timeline:   List[ConsequenceHorizon]
    risk_trajectory:        str   # TRAJ_* constant
    risk_trajectory_reason: str
    cost_exposure:          str   # COST_* constant
    cost_exposure_reason:   str
    point_of_no_return:     str   # "If X, then full upgrade unavoidable"
    escalation_pathway:     List[str]   # ordered failure chain
    stage_frames:           List[StageDefferalFrame]
    board_delay_bullets:    List[str]   # 3-4 board-level bullets
    deferral_summary:       str   # one-paragraph summary


# ── Signal extraction ─────────────────────────────────────────────────────────

def _sig(ctx: Dict, key: str, default=None):
    return ctx.get(key, default)


def _is_failure_risk(pathway) -> bool:
    return "Failure Risk" in str(getattr(pathway, "system_state", ""))


def _proximity(pathway) -> float:
    return float(getattr(pathway, "proximity_pct", 0.) or 0.)


def _growth_ratio(ctx: Dict) -> float:
    rate  = float(ctx.get("growth_rate_percent", 0.) or 0.)
    years = float(ctx.get("planning_horizon_years", 20.) or 20.)
    if rate > 0 and years > 0:
        return (1 + rate / 100.) ** years
    return 1.0


# ── Risk trajectory ────────────────────────────────────────────────────────────

def _classify_trajectory(ctx: Dict, pathway, co) -> tuple[str, str]:
    """Return (trajectory_class, reason_string)."""
    prox        = _proximity(pathway)
    carbon_lim  = bool(ctx.get("carbon_limited_tn", False))
    gap         = bool(getattr(co, "stack_compliance_gap", False) or
                        ctx.get("stack_compliance_gap", False))
    gr          = _growth_ratio(ctx)
    flow_ratio  = float(ctx.get("flow_ratio", 1.5) or 1.5)
    cl_over     = bool(ctx.get("clarifier_overloaded", False))
    aer_con     = bool(ctx.get("aeration_constrained", False))
    thp         = bool(ctx.get("thp_present", False))
    thp_pct     = float(ctx.get("thp_nh4_inc_pct", 0.) or 0.)
    conf        = int(getattr(co, "confidence_score", 100) or
                      ctx.get("confidence_score", 100))
    eff_codn    = float(ctx.get("eff_codn_val") or
                        getattr(co, "effective_cod_tn_val", 999.) or 999.)

    reasons = []
    score = 0

    if prox >= 300.: score += 3; reasons.append(f"system at {prox:.0f}% of design capacity")
    elif prox >= 150.: score += 2; reasons.append(f"system at {prox:.0f}% of design capacity")
    elif prox >= 120.: score += 1; reasons.append(f"system approaching capacity ({prox:.0f}%)")

    if carbon_lim and gap: score += 3; reasons.append("carbon-limited denitrification with compliance gap")
    elif carbon_lim:       score += 2; reasons.append("carbon-limited denitrification (eff COD:TN below threshold)")
    elif gap:              score += 2; reasons.append("compliance gap identified")

    if gr >= 2.0: score += 2; reasons.append(f"growth will double load over planning horizon ({gr:.1f}x)")
    elif gr >= 1.5: score += 1; reasons.append(f"load growing to {gr:.1f}x current over horizon")

    if cl_over and flow_ratio >= 4.: score += 2; reasons.append("clarifier overloaded under peak flow")
    elif cl_over:                     score += 1; reasons.append("clarifier capacity constrained")

    if thp and thp_pct >= 50.: score += 1; reasons.append(f"THP NH4 surge +{thp_pct:.0f}% planned")
    if conf < 20:              score += 2; reasons.append("confidence very low — compliance not credible")
    elif conf < 40:            score += 1; reasons.append("confidence low — compliance at risk")
    if eff_codn < 3.5:         score += 1; reasons.append(f"eff COD:TN {eff_codn:.2f} — severely carbon-limited")

    if score >= 8:    traj = TRAJ_CRITICAL;       prefix = "Non-linear risk escalation: "
    elif score >= 5:  traj = TRAJ_ACCELERATING;   prefix = "Compounding risk: "
    elif score >= 3:  traj = TRAJ_INCREASING;     prefix = "Manageable but growing risk: "
    else:             traj = TRAJ_STABLE;          prefix = "Risk is stable: "

    reason = prefix + "; ".join(reasons[:3]) + "." if reasons else prefix + "no acute triggers."
    return traj, reason


# ── Cost exposure ─────────────────────────────────────────────────────────────

def _classify_cost_exposure(ctx: Dict, pathway, co, traj: str) -> tuple[str, str]:
    """Return (cost_exposure_class, reason)."""
    gap  = bool(getattr(co, "stack_compliance_gap", False) or ctx.get("stack_compliance_gap", False))
    prox = _proximity(pathway)
    cl   = bool(ctx.get("clarifier_overloaded", False))
    aer  = bool(ctx.get("aeration_constrained", False))
    thp  = bool(ctx.get("thp_present", False)) and float(ctx.get("thp_nh4_inc_pct", 0.) or 0.) >= 50.
    gf   = bool(ctx.get("greenfield", False))
    conf = int(getattr(co, "confidence_score", 100) or ctx.get("confidence_score", 100))

    drivers = []
    if traj == TRAJ_CRITICAL:
        drivers.append("emergency capital works become likely under reactive scenario")
    if gap:
        drivers.append("compliance gap will require tertiary closure investment regardless of timing")
    if cl and prox >= 200.:
        drivers.append("clarifier failure under peak flow leads to costly emergency bypass or shutdown")
    if aer:
        drivers.append("aeration constraint increases energy cost per unit of nitrogen removed")
    if thp:
        drivers.append("THP NH4 surge without sidestream treatment increases chemical dosing demand")
    if conf < 20:
        drivers.append("very low confidence indicates structural rework is likely")
    if not gf:
        drivers.append("brownfield retrofit costs compound with each deferred stage")

    if traj in (TRAJ_CRITICAL,) or (gap and prox >= 300.):
        cost, prefix = COST_SEVERE, "Severe cost exposure: "
    elif traj == TRAJ_ACCELERATING or (gap and len(drivers) >= 3):
        cost, prefix = COST_HIGH, "High cost exposure: "
    elif traj == TRAJ_INCREASING or len(drivers) >= 2:
        cost, prefix = COST_MODERATE, "Moderate cost exposure: "
    else:
        cost, prefix = COST_LOW, "Low cost exposure: "

    reason = prefix + "; ".join(drivers[:3]) + "." if drivers else prefix + "no acute drivers."
    return cost, reason


# ── Consequence timeline ───────────────────────────────────────────────────────

def _build_timeline(ctx: Dict, pathway, co) -> List[ConsequenceHorizon]:
    """Build the four-horizon consequence timeline using cause→consequence logic."""
    prox       = _proximity(pathway)
    fr         = float(ctx.get("flow_ratio", 1.5) or 1.5)
    cl_over    = bool(ctx.get("clarifier_overloaded", False))
    aer_con    = bool(ctx.get("aeration_constrained", False))
    carbon_lim = bool(ctx.get("carbon_limited_tn", False))
    eff_codn   = float(ctx.get("eff_codn_val") or
                       getattr(co, "effective_cod_tn_val", 999.) or 999.)
    gap        = bool(getattr(co, "stack_compliance_gap", False) or ctx.get("stack_compliance_gap", False))
    thp        = bool(ctx.get("thp_present", False))
    thp_pct    = float(ctx.get("thp_nh4_inc_pct", 0.) or 0.)
    svi        = float(ctx.get("svi_ml_g", 0.) or ctx.get("svi_design", 0.) or 0.)
    temp       = float(ctx.get("temp_celsius", 20.) or 20.)
    cold_zone  = temp <= 15.
    gf         = bool(ctx.get("greenfield", False))
    gr         = _growth_ratio(ctx)
    growth_rate= float(ctx.get("growth_rate_percent", 0.) or 0.)

    # ── Horizon 0–2 years ─────────────────────────────────────────────────────
    if not gf and cl_over and fr >= 3.:
        h0_fail  = "Clarifier hydraulic overload under peak wet weather flow"
        h0_sys   = ("Solids carryover leads to loss of MLSS and biological process instability. "
                    "Each washout event requires days of MLSS rebuilding before nitrification "
                    "is re-established.")
        h0_reg   = ("TN and NH4 exceedances during and after peak flow events. "
                    "Consent exceedances are not avoidable under current configuration.")
        h0_ops   = ("Emergency interventions — chemical dosing, reduced loading, bypass. "
                    "Increased operator workload and reactive maintenance.")
    elif not gf and aer_con:
        h0_fail  = "Nitrification failure under peak load or THP-driven NH4 surge"
        h0_sys   = ("Blowers at or near capacity before THP load accounting. "
                    "Any additional NH4 load from sidestream dewatering pushes "
                    "nitrification below reliable operating window.")
        h0_reg   = ("NH4 and TN exceedances during THP dewatering cycles. "
                    "Seasonal non-compliance risk is elevated.")
        h0_ops   = ("Increased aeration costs, dewatering cycle management, "
                    "and manual intervention during high-load periods.")
    elif carbon_lim and gap:
        h0_fail  = "Carbon-limited denitrification — TN compliance gap immediate"
        h0_sys   = (f"Eff COD:TN {eff_codn:.2f} is below the 4.5 biological closure threshold. "
                    "Biological denitrification cannot achieve TN compliance at P95 "
                    "regardless of other constraint relief.")
        h0_reg   = ("TN at P95 is not achievable under current configuration. "
                    "Tertiary nitrogen closure is required before compliance is credible.")
        h0_ops   = "Ongoing compliance monitoring, chemical dosing as interim measure."
    else:
        h0_fail  = "Performance risk under peak or seasonal conditions"
        h0_sys   = "System operates within limits under average conditions but compliance margin is narrow."
        h0_reg   = "Consent exceedances possible under peak flow or winter conditions."
        h0_ops   = "Increased monitoring and operational vigilance required."

    # ── Horizon 2–5 years ────────────────────────────────────────────────────
    if thp and thp_pct >= 50.:
        h1_fail  = "THP NH4 surge compounds nitrification and biological performance failures"
        h1_sys   = (f"THP NH4 increase of +{thp_pct:.0f}% without sidestream treatment "
                    "adds directly to mainstream nitrification load. "
                    "Combined with aeration constraint, this pushes nitrification "
                    "below reliable operating window during dewatering cycles.")
        h1_reg   = ("NH4 and TN non-compliance during THP dewatering events. "
                    "If sidestream PN/A is not in place by THP commissioning, "
                    "compliance breaches are a design certainty, not a risk.")
        h1_ops   = ("Significant increase in chemical dosing, operational complexity, "
                    "and emergency response requirements.")
    elif cold_zone:
        h1_fail  = "Winter kinetic constraint compounds biological compliance risk"
        h1_sys   = (f"At {temp:.0f}°C, nitrification rates are reduced ~25–35% below "
                    "warm-weather baseline. Combined with growth-driven load increase, "
                    "seasonal compliance windows narrow further.")
        h1_reg   = "Seasonal TN and NH4 exceedances become more frequent as load increases."
        h1_ops   = "Cold-season monitoring intensified; operational headroom reduced."
    elif carbon_lim:
        h1_fail  = "Carbon-limited denitrification constrains all biological compliance pathways"
        h1_sys   = ("No biological process optimisation can overcome eff COD:TN < 4.5. "
                    "As load grows, the carbon deficit widens and tertiary closure "
                    "becomes the only credible compliance pathway.")
        h1_reg   = "TN compliance gap widens as TKN load increases with growth."
        h1_ops   = "Increased methanol or carbon dosing costs as interim measure."
    else:
        h1_fail  = "Growth-driven load increase begins to erode compliance headroom"
        h1_sys   = (f"At {growth_rate:.1f}%/yr, load reaches ~{1 + growth_rate/100 * 3:.2f}x "
                    "current within 3 years. Biological and hydraulic margins tighten.")
        h1_reg   = "P95 compliance becomes harder to maintain without process upgrades."
        h1_ops   = "Increased monitoring, chemical costs, and operational interventions."

    # ── Horizon 5–10 years ───────────────────────────────────────────────────
    if gr >= 1.5 and not gf:
        h2_fail  = "Growth-driven capacity breach — in-situ intensification is exhausted"
        h2_sys   = (f"At {growth_rate:.1f}%/yr, flow approaches {min(gr, 1.6):.1f}x current "
                    "ADWF within this window. In-situ intensification reaches its structural "
                    "limit; process renewal becomes necessary.")
        h2_reg   = ("Sustained consent exceedances under average conditions. "
                    "Regulatory enforcement action likely if growth is not addressed.")
        h2_ops   = ("Reactive capital works, emergency procurement, and extended "
                    "non-compliance management. Programme risk is high if not planned ahead.")
    elif gap and carbon_lim:
        h2_fail  = "Sustained carbon-limited TN non-compliance drives regulatory action"
        h2_sys   = ("Without tertiary nitrogen closure, TN compliance remains not credible "
                    "at P95 throughout this window. Biological optimisation cannot close the gap.")
        h2_reg   = ("Regulatory enforcement action likely. Abatement notice or consent "
                    "review possible if compliance is not demonstrated.")
        h2_ops   = ("Reactive capital — emergency DNF/PdNA procurement at higher cost "
                    "and longer lead time than planned programme.")
    else:
        h2_fail  = "Deferred upgrades now unavoidable under consent tightening trajectory"
        h2_sys   = ("Consent tightening (TN ≤ 3 mg/L expected) requires tertiary "
                    "closure to be operational before this window closes. "
                    "Footprint and procurement lead time constrain options.")
        h2_reg   = ("Future consent conditions require infrastructure not yet in design. "
                    "Commission lag means investment decisions must be made now.")
        h2_ops   = ("Programme compression increases cost and delivery risk. "
                    "Less time for community consultation and planning approvals.")

    # ── Horizon >10 years ────────────────────────────────────────────────────
    if gf:
        h3_fail  = "Stage 3 capacity constraint if footprint not reserved in masterplan"
        h3_sys   = ("If Stage 3 civil footprint (PdNA/Anammox, advanced P, UV) is not "
                    "reserved at Stage 1 design, later expansion becomes a brownfield "
                    "problem with existing Stage 1 infrastructure as the constraint.")
        h3_reg   = ("TN ≤ 3 mg/L and TP ≤ 0.1 mg/L consent conditions expected. "
                    "Recycled water standard likely within this window.")
        h3_ops   = ("Stage 3 retrofit within Stage 1 footprint is expensive and disruptive. "
                    "Reserve footprint now to avoid this outcome.")
    else:
        h3_fail  = "Full process renewal unavoidable — site reaches end of intensification capacity"
        h3_sys   = (f"At {gr:.1f}x growth, no further in-situ intensification can meet "
                    "design ADWF. Process renewal (MBR, AGS, or greenfield equivalent) "
                    "is the only viable path.")
        h3_reg   = ("Sustained non-compliance under future consent conditions. "
                    "Asset replacement programme must be underway within this window.")
        h3_ops   = ("Transition management: simultaneous operation of existing and new "
                    "process during commissioning. Operational complexity peak.")

    return [
        ConsequenceHorizon("Immediate (0–2 years)", h0_fail, h0_sys, h0_reg, h0_ops),
        ConsequenceHorizon("Short-term (2–5 years)", h1_fail, h1_sys, h1_reg, h1_ops),
        ConsequenceHorizon("Medium-term (5–10 years)", h2_fail, h2_sys, h2_reg, h2_ops),
        ConsequenceHorizon("Long-term (>10 years)", h3_fail, h3_sys, h3_reg, h3_ops),
    ]


# ── Escalation pathway ─────────────────────────────────────────────────────────

def _build_escalation_pathway(ctx: Dict, pathway, co) -> List[str]:
    """Ordered failure chain — each step builds from the previous."""
    fr         = float(ctx.get("flow_ratio", 1.5) or 1.5)
    cl_over    = bool(ctx.get("clarifier_overloaded", False))
    aer_con    = bool(ctx.get("aeration_constrained", False))
    carbon_lim = bool(ctx.get("carbon_limited_tn", False))
    gap        = bool(getattr(co, "stack_compliance_gap", False) or ctx.get("stack_compliance_gap", False))
    thp        = bool(ctx.get("thp_present", False)) and float(ctx.get("thp_nh4_inc_pct", 0.) or 0.) >= 50.
    gf         = bool(ctx.get("greenfield", False))

    chain = []

    # Step 1: Hydraulic instability (if present)
    if not gf and cl_over and fr >= 3.:
        chain.append(
            "Hydraulic instability: clarifier overflow under peak wet weather flow "
            "leads to solids carryover and MLSS loss."
        )

    # Step 2: Biological performance loss
    if aer_con or thp:
        chain.append(
            "Biological performance loss: aeration constraint and/or THP NH4 surge "
            "leads to nitrification failure during peak load or dewatering cycles."
        )
    else:
        chain.append(
            "Biological performance loss: compliance headroom narrows as load grows "
            "and seasonal kinetic constraints tighten."
        )

    # Step 3: Carbon limitation exposure
    if carbon_lim:
        chain.append(
            "Carbon limitation exposure: eff COD:TN below 4.5 means biological "
            "denitrification is unreliable at P95 regardless of other improvements. "
            "Tertiary nitrogen closure becomes the only credible compliance pathway."
        )
    else:
        chain.append(
            "Carbon limitation exposure: as load grows and COD:TN ratio declines "
            "under wet weather dilution, denitrification reliability deteriorates "
            "further without external carbon or tertiary closure."
        )

    # Step 4: Chemical dependency increase
    chain.append(
        "Chemical dependency increase: interim measures (methanol dosing, "
        "chemical P removal, pH adjustment) are commissioned as reactive measures, "
        "increasing OPEX without addressing root causes."
    )

    # Step 5: System-wide instability
    chain.append(
        "System-wide instability: multiple simultaneous failure modes interact. "
        "Hydraulic, biological, and carbon constraints compound, making "
        "compliance management increasingly reactive and unreliable."
    )

    # Step 6: Regulatory breach
    if gap:
        chain.append(
            "Regulatory breach: sustained TN and/or NH4 exceedances under "
            "average and peak conditions lead to consent enforcement action."
        )

    # Step 7: Reputational / compliance risk
    chain.append(
        "Reputational and compliance risk: enforcement action, abatement notices, "
        "and public reporting obligations increase stakeholder and board exposure. "
        "Emergency capital procurement at higher cost and longer lead time."
    )

    return chain


# ── Point of no return ────────────────────────────────────────────────────────

def _build_point_of_no_return(ctx: Dict, pathway, co) -> str:
    """Define the structural threshold beyond which incremental fixes are insufficient."""
    prox       = _proximity(pathway)
    fr         = float(ctx.get("flow_ratio", 1.5) or 1.5)
    gr         = _growth_ratio(ctx)
    cl_over    = bool(ctx.get("clarifier_overloaded", False))
    carbon_lim = bool(ctx.get("carbon_limited_tn", False))
    gap        = bool(getattr(co, "stack_compliance_gap", False) or ctx.get("stack_compliance_gap", False))
    gf         = bool(ctx.get("greenfield", False))
    rate       = float(ctx.get("growth_rate_percent", 0.) or 0.)
    eff_codn   = float(ctx.get("eff_codn_val") or
                       getattr(co, "effective_cod_tn_val", 999.) or 999.)

    if not gf and cl_over and fr >= 4. and prox >= 300.:
        return (
            f"If peak flow exceeds hydraulic relief capacity under {rate:.1f}%/yr growth "
            "conditions, incremental constraint relief will no longer prevent washout "
            "and full hydraulic infrastructure replacement becomes unavoidable."
        )
    if carbon_lim and gap and eff_codn < 3.5:
        return (
            f"If tertiary nitrogen closure (DNF or PdNA) is not operational before "
            "consent tightening to TN ≤ 3 mg/L, biological optimisation alone cannot "
            "close the gap and full nitrogen removal infrastructure renewal becomes unavoidable."
        )
    if gr >= 2.0 and not gf:
        return (
            f"If ADWF grows to {gr:.1f}x current load without process renewal decision, "
            "in-situ intensification reaches its structural limit and full process "
            "replacement or new greenfield plant becomes unavoidable."
        )
    if gf:
        return (
            "If Stage 3 civil footprint is not reserved in the Stage 1 masterplan, "
            "expansion to TN ≤ 3 mg/L and reuse standard becomes a brownfield "
            "retrofit within existing infrastructure, compressing options and "
            "significantly increasing cost."
        )
    return (
        "If compliance gap persists beyond consent review period without committed "
        "upgrade programme, regulatory enforcement will require emergency capital "
        "procurement at higher cost and compressed timeline."
    )


# ── Stage deferral frames ─────────────────────────────────────────────────────

def _build_stage_frames(ap, ctx: Dict, co) -> List[StageDefferalFrame]:
    """Per-stage deferral decision frame (Part 8)."""
    frames = []
    stages = getattr(ap, "future_stages", []) or []
    gap    = bool(getattr(co, "stack_compliance_gap", False) or ctx.get("stack_compliance_gap", False))
    cl     = bool(ctx.get("clarifier_overloaded", False))
    thp    = bool(ctx.get("thp_present", False)) and float(ctx.get("thp_nh4_inc_pct", 0.) or 0.) >= 50.

    urgency_map = {
        0: ("immediate capital expenditure", "hydraulic failure risk", "0–2 years"),
        1: ("Stage 2 capital commitment", "nitrogen compliance gap and growth-driven hydraulic exposure", "2–5 years"),
        2: ("process renewal commitment", "sustained non-compliance and consent enforcement", ">5 years"),
    }

    for i, stage in enumerate(stages[:3]):
        avoids, risk, horizon = urgency_map.get(i, ("capital expenditure", "performance risk", "2–5 years"))

        if i == 0:
            if cl and not bool(ctx.get("greenfield", False)):
                failure = ("clarifier overflow and MLSS loss leading to TN and NH4 "
                           "consent exceedances during peak flow events")
            elif thp:
                failure = ("THP NH4 surge without sidestream treatment leading to "
                           "nitrification failure during dewatering cycles")
            else:
                failure = ("biological compliance risk increasing under seasonal "
                           "and peak load conditions")
        elif i == 1:
            failure = ("growth-driven hydraulic and nitrogen compliance breach — "
                       "carbon-limited TN gap becomes persistent")
        else:
            failure = ("process renewal becomes unavoidable under growth and "
                       "tightening consent trajectory — options and timeline compress")

        frames.append(StageDefferalFrame(
            stage_label     = stage.stage,
            avoids          = avoids,
            introduces_risk = risk,
            failure_mode    = failure,
            time_horizon    = horizon,
        ))

    return frames


# ── Board delay bullets ───────────────────────────────────────────────────────

def _build_board_delay_bullets(
    timeline: List[ConsequenceHorizon],
    traj: str, cost: str,
    ponr: str,
) -> List[str]:
    """3–4 board-level bullets (Part 10)."""
    bullets = []

    # First failure
    if timeline:
        bullets.append(
            f"First failure if deferred: {timeline[0].primary_failure}. "
            f"Regulatory impact: {timeline[0].regulatory_impact.split('.')[0]}."
        )

    # Escalation risk
    if len(timeline) >= 2:
        bullets.append(
            f"Escalation risk: {timeline[1].primary_failure}. "
            f"Trajectory: {traj}."
        )

    # Cost exposure
    bullets.append(
        f"Cost exposure from deferral: {cost}. "
        "Reactive procurement, emergency interventions, and chemical cost "
        "increases are the primary drivers."
    )

    # Point of no return (truncated for board)
    ponr_short = ponr.split(",")[0].rstrip(".") if ponr else ""
    if ponr_short:
        bullets.append(f"Point of no return: {ponr_short}, full system upgrade becomes unavoidable.")

    return bullets


# ── Deferral summary ───────────────────────────────────────────────────────────

def _build_deferral_summary(
    traj: str, cost: str, ponr: str,
    timeline: List[ConsequenceHorizon], ctx: Dict,
) -> str:
    """One-paragraph plain-language deferral summary."""
    prox = float(ctx.get("stack_compliance_gap", False) and 100 or 0)
    thp  = bool(ctx.get("thp_present", False))
    immediate = timeline[0].primary_failure if timeline else "process failure"
    short_term = timeline[1].primary_failure if len(timeline) > 1 else "further degradation"

    return (
        f"Risk trajectory is {traj}. "
        f"Without investment, the most immediate consequence is {immediate}. "
        f"Within 2–5 years, {short_term} emerges as the primary risk. "
        f"Cost exposure from deferral is {cost}. "
        f"{ponr.rstrip('.')}. "
        "Each deferred stage compresses the time and options available for the next, "
        "converting a planned programme into a reactive procurement exercise."
    )


# ── Main entry point ──────────────────────────────────────────────────────────

def build_deferral_consequence(
    pathway,
    compliance_report,
    adaptive_pathways,
    ctx: Dict,
) -> DeferralConsequenceResult:
    """
    Build the deferral consequence analysis.

    Activation: fires when:
    - system_state = Failure Risk, OR
    - confidence_score < 60, OR
    - compliance gap exists, OR
    - multi-stage upgrade pathway present

    Parameters
    ----------
    pathway : UpgradePathway
    compliance_report : ComplianceReport
    adaptive_pathways : AdaptivePathwaysResult
    ctx : Dict  — engine context
    """
    co  = compliance_report
    ap  = adaptive_pathways
    prox = _proximity(pathway)
    gap  = bool(getattr(co, "stack_compliance_gap", False) or ctx.get("stack_compliance_gap", False))
    conf = int(getattr(co, "confidence_score", 100) or ctx.get("confidence_score", 100))
    n_stages = len(getattr(ap, "future_stages", []) or [])

    is_active = (
        "Failure Risk" in str(getattr(pathway, "system_state", ""))
        or conf < 60
        or gap
        or n_stages >= 2
        or prox >= 150.
    )

    if not is_active:
        return DeferralConsequenceResult(
            is_active=False,
            consequence_timeline=[], risk_trajectory=TRAJ_STABLE,
            risk_trajectory_reason="No acute deferral triggers identified.",
            cost_exposure=COST_LOW, cost_exposure_reason="",
            point_of_no_return="", escalation_pathway=[],
            stage_frames=[], board_delay_bullets=[],
            deferral_summary="",
        )

    traj, traj_reason = _classify_trajectory(ctx, pathway, co)
    cost, cost_reason = _classify_cost_exposure(ctx, pathway, co, traj)
    timeline          = _build_timeline(ctx, pathway, co)
    escalation        = _build_escalation_pathway(ctx, pathway, co)
    ponr              = _build_point_of_no_return(ctx, pathway, co)
    stage_frames      = _build_stage_frames(ap, ctx, co)
    board_bullets     = _build_board_delay_bullets(timeline, traj, cost, ponr)
    summary           = _build_deferral_summary(traj, cost, ponr, timeline, ctx)

    return DeferralConsequenceResult(
        is_active              = True,
        consequence_timeline   = timeline,
        risk_trajectory        = traj,
        risk_trajectory_reason = traj_reason,
        cost_exposure          = cost,
        cost_exposure_reason   = cost_reason,
        point_of_no_return     = ponr,
        escalation_pathway     = escalation,
        stage_frames           = stage_frames,
        board_delay_bullets    = board_bullets,
        deferral_summary       = summary,
    )
