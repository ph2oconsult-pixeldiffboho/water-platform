"""
apps/wastewater_app/bf_gf_layer.py

Brownfield vs Greenfield Strategic Assessment Layer — Production V1
====================================================================

Evaluates whether the recommended solution should be:
  → Brownfield upgrade (retain and intensify existing assets)
  → Greenfield / replacement (new process architecture)

This is a strategic interpretation layer. It reads already-generated
outputs from the Stack Generator, Feasibility Layer, and Credibility Layer.
It does NOT change any selection, constraint, or calculation.

Decision categories
-------------------
STRONG_BROWNFIELD  — isolated constraint; upgrade simple and staged
BALANCED           — multiple constraints; brownfield feasible but complex;
                     replacement offers simplification benefit
STRONG_REPLACEMENT — multiple interacting constraints; footprint exhausted;
                     upgrade highly complex; long-term performance risk high

Scoring model
-------------
Each dimension contributes penalty points. Total determines category:
  0–3  → Strong Brownfield
  4–7  → Balanced
  8+   → Strong Replacement

Penalty sources (each 0–3 points):
  constraint_count     number of active High/Medium constraints
  constraint_severity  whether constraints interact and amplify
  stack_complexity     number of specialist technologies in primary stack
  tn_tp_stringency     future licence targets (TN <5 / <3 mg/L, TP <1 / <0.1 mg/L)
  feasibility_overhead feasibility layer overall + confidence_change
  flow_ratio           peak wet weather severity
  footprint            tight_footprint flag from context

Design principles
-----------------
- Nereda appears only in replacement pathway (never primary stack recommendation)
- MBR appears only when effluent quality explicitly drives the decision
- Brownfield path mirrors the actual recommended stack
- No bias toward rebuild unless objective scoring justifies it
- All replacement pathway risks stated explicitly

Main entry point
----------------
  build_bf_gf_assessment(pathway, feasibility, credible, plant_context)
      -> BFGFAssessment
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from apps.wastewater_app.stack_generator import (
    UpgradePathway,
    CT_HYDRAULIC, CT_SETTLING, CT_NITRIFICATION,
    CT_TN_POLISH, CT_TP_POLISH, CT_BIOLOGICAL,
    CT_MEMBRANE, CT_WET_WEATHER,
    TI_COMAG, TI_BIOMAG, TI_EQ_BASIN, TI_STORM_STORE,
    TI_INDENSE, TI_MIGINDENSE, TI_MEMDENSE,
    TI_HYBAS, TI_IFAS, TI_MBBR, TI_MABR,
    TI_BARDENPHO, TI_RECYCLE_OPT, TI_ZONE_RECONF,
    TI_DENFILTER, TI_TERT_P,
)
from apps.wastewater_app.feasibility_layer import FeasibilityReport
from apps.wastewater_app.credibility_layer import CredibleOutput

# ── Category constants ────────────────────────────────────────────────────────
STRONG_BROWNFIELD  = "Strong Brownfield"
BALANCED           = "Balanced"
STRONG_REPLACEMENT = "Strong Replacement"

# ── Specialist technologies that add stack complexity ─────────────────────────
_SPECIALIST = {TI_COMAG, TI_BIOMAG, TI_MABR, TI_MIGINDENSE, TI_MEMDENSE, TI_DENFILTER}

# Constraints that interact and compound each other
_INTERACTING_PAIRS = {
    frozenset({CT_HYDRAULIC, CT_SETTLING}),
    frozenset({CT_SETTLING,   CT_NITRIFICATION}),
    frozenset({CT_HYDRAULIC,  CT_NITRIFICATION}),
    frozenset({CT_NITRIFICATION, CT_TN_POLISH}),
    frozenset({CT_TN_POLISH,  CT_TP_POLISH}),
}


# ── Dataclasses ────────────────────────────────────────────────────────────────

@dataclass
class PathwaySummary:
    """Summary of one strategic pathway (brownfield or replacement)."""
    label:          str
    key_technologies: List[str]
    benefits:       List[str]
    risks:          List[str]
    capex_class:    str     # "Low–Medium" / "Medium–High" / "High"
    disruption:     str     # "Low" / "Medium" / "High"
    timeline_years: str     # indicative delivery horizon


@dataclass
class TippingPoint:
    """Conditions that would shift the decision from one category to another."""
    from_category:  str
    to_category:    str
    triggers:       List[str]


@dataclass
class BFGFAssessment:
    """Full Brownfield vs Greenfield strategic assessment."""
    # Scoring
    total_score:        int
    dimension_scores:   Dict[str, int]   # dimension name → score
    dimension_notes:    Dict[str, str]   # dimension name → explanation

    # Decision
    recommendation:     str   # STRONG_BROWNFIELD / BALANCED / STRONG_REPLACEMENT
    rationale:          str   # 2-3 sentence explanation

    # Pathways
    brownfield_pathway: PathwaySummary
    replacement_pathway: PathwaySummary

    # Tipping point
    tipping_point:      TippingPoint

    # Standard decision tension
    decision_tension:   str

    # Validation flags
    nereda_in_replacement_only: bool
    mbr_appropriately_positioned: bool
    brownfield_reflects_stack:  bool


# ── Scoring model ──────────────────────────────────────────────────────────────

def _score_constraint_count(pathway: UpgradePathway) -> Tuple[int, str]:
    """0–3: number of active High/Medium constraints."""
    high_med = sum(1 for c in pathway.constraints
                   if c.severity in ("High", "Medium"))
    if high_med <= 1:
        return 0, f"{high_med} active constraint — isolated, targeted upgrade appropriate."
    if high_med == 2:
        return 1, f"{high_med} active constraints — manageable with staged intensification."
    if high_med == 3:
        return 2, f"{high_med} active constraints — multi-mechanism upgrade required."
    return 3, f"{high_med} active constraints — complex multi-front programme; "         \
               "brownfield viability depends on footprint and staging."


def _score_constraint_severity(pathway: UpgradePathway) -> Tuple[int, str]:
    """0–3: whether constraints interact and amplify each other."""
    ct_set = {c.constraint_type for c in pathway.constraints}
    n_interacting = sum(
        1 for pair in _INTERACTING_PAIRS if pair.issubset(ct_set)
    )
    if n_interacting == 0:
        return 0, "Constraints are independent — each addressable by a distinct mechanism."
    if n_interacting == 1:
        return 1, "One interacting constraint pair — stacked upgrade adds moderate complexity."
    if n_interacting == 2:
        return 2, "Two interacting pairs — constraint amplification increases complexity and risk."
    return 3, f"{n_interacting} interacting constraint pairs — constraints are deeply coupled; "  \
               "brownfield stacking risk is high."


def _score_stack_complexity(pathway: UpgradePathway,
                             feasibility: FeasibilityReport) -> Tuple[int, str]:
    """0–3: specialist technology count and feasibility overhead."""
    tech_set = {s.technology for s in pathway.stages}
    n_specialist = len(_SPECIALIST & tech_set)
    n_stages     = len(pathway.stages)

    if n_specialist == 0 and n_stages <= 2:
        return 0, f"{n_stages}-stage stack, no specialist supply dependency."
    if n_specialist <= 1 and n_stages <= 3:
        return 1, f"{n_stages}-stage stack with {n_specialist} specialist technology."
    if n_specialist <= 2 and n_stages <= 4:
        return 2, (f"{n_stages}-stage stack with {n_specialist} specialist technologies — delivery complexity is material.")
    return 3, (f"{n_stages}-stage stack with {n_specialist} specialist technologies — risk stacking is significant; replacement simplifies delivery.")


def _score_tn_tp_stringency(pathway: UpgradePathway,
                              ctx: Dict) -> Tuple[int, str]:
    """0–3: future licence stringency for TN and TP."""
    tn_tgt = ctx.get("tn_out_upgraded_mg_l") or ctx.get("tn_target_mg_l", 10.)
    tp_tgt = ctx.get("tp_target_mg_l", 1.)
    ct_set = {c.constraint_type for c in pathway.constraints}
    score  = 0
    notes  = []

    if CT_TN_POLISH in ct_set or CT_TP_POLISH in ct_set:
        if tn_tgt is not None and float(tn_tgt) <= 3.:
            score += 2
            notes.append(f"TN target ≤ 3 mg/L requires tertiary denitrification (DNF) — adds chemical dependency and operational complexity.")
        elif tn_tgt is not None and float(tn_tgt) <= 5.:
            score += 1
            notes.append(f"TN target ≤ 5 mg/L requires Bardenpho + potential external carbon.")
        if tp_tgt is not None and float(tp_tgt) <= 0.1:
            score += 1
            notes.append(f"TP target ≤ 0.1 mg/L requires tertiary chemical polishing.")

    score = min(score, 3)
    return score, " ".join(notes) if notes else "Licence targets achievable with primary stack."


def _score_feasibility(feasibility: FeasibilityReport) -> Tuple[int, str]:
    """0–3: feasibility layer overall rating and confidence change."""
    score = 0
    notes = []
    if feasibility.overall_feasibility == "Low":
        score += 2
        notes.append("Feasibility rated Low — brownfield stack faces significant delivery barriers.")
    elif feasibility.overall_feasibility == "Medium":
        score += 1
        notes.append("Feasibility rated Medium — manageable with proactive planning.")
    if feasibility.confidence_change == "Downgraded":
        score += 1
        notes.append(f"Confidence was downgraded ({feasibility.confidence_reason[:80]}).")
    score = min(score, 3)
    return score, " ".join(notes) if notes else "Feasibility is High — delivery risk is low."


def _score_flow_ratio(ctx: Dict) -> Tuple[int, str]:
    """0–3: peak wet weather flow ratio severity."""
    fr = ctx.get("flow_ratio", 1.0) or 1.0
    if fr >= 3.5:
        return 3, (f"Peak flow {fr:.1f}× ADWF — extreme hydraulic events require infrastructure-grade  attenuation; brownfield intensification alone is insufficient.")
    if fr >= 3.0:
        return 2, (f"Peak flow {fr:.1f}× ADWF — above the threshold where hydraulic  attenuation infrastructure is required alongside process intensification.")
    if fr >= 2.5:
        return 1, (f"Peak flow {fr:.1f}× ADWF — wet weather performance is a material concern  but manageable with CoMag or equivalent.")
    return 0, f"Peak flow {fr:.1f}× ADWF — within manageable brownfield intensification range."


def _score_footprint(ctx: Dict) -> Tuple[int, str]:
    """0–3: site footprint constraint."""
    tight     = bool(ctx.get("tight_footprint", False))
    constrained = bool(ctx.get("footprint_constrained", False))
    urban     = ctx.get("location_type", "") == "metro"
    # Infer from context signals
    if tight or (constrained and urban):
        return 3, ("Footprint severely constrained — civil expansion or EQ basin is not viable;  limits long-term brownfield envelope.")
    if constrained or urban:
        return 1, ("Footprint is constrained — expansion options limited but brownfield  intensification within tanks is feasible.")
    return 0, "Adequate footprint — brownfield and greenfield both viable from a site perspective."


# ── Pathway builders ───────────────────────────────────────────────────────────

def _brownfield_pathway(
    pathway: UpgradePathway,
    feasibility: FeasibilityReport,
    recommendation: str,
) -> PathwaySummary:
    """Build the brownfield pathway summary from the actual recommended stack."""
    tech_set    = {s.technology for s in pathway.stages}
    tech_labels = [s.tech_display.split("(")[0].strip() for s in pathway.stages]
    n_stages    = len(pathway.stages)
    n_spec      = len(_SPECIALIST & tech_set)

    benefits = [
        "Retains existing civil infrastructure and bioreactor volume — lower total CAPEX.",
        "Plant remains operational throughout the staged upgrade programme.",
        f"Sequenced {n_stages}-stage delivery allows performance confirmation before next stage is committed.",
        "Reversible commitment — each stage gate can be reviewed before proceeding.",
    ]
    if TI_MABR in tech_set:
        benefits.append(
            "MABR provides energy-efficient nitrification and N₂O reduction as a co-benefit.")
    if TI_COMAG in tech_set or TI_BIOMAG in tech_set:
        benefits.append(
            "High-rate clarification addresses peak hydraulic events without new secondary tanks.")

    risks = [
        f"{n_stages}-stage upgrade programme increases operational complexity — each stage must be commissioned and verified before the next is procured.",
    ]
    if n_spec >= 2:
        risks.append(
            f"{n_spec} specialist technologies introduce supply chain and OEM dependency that must be actively managed.")
    if feasibility.chemical_dependency in ("Medium", "High"):
        risks.append(
            "Chemical dependency (ongoing) adds supply chain risk and OPEX sensitivity.")
    if recommendation == STRONG_REPLACEMENT:
        risks.append(
            "At this level of constraint interaction, brownfield stacking risk is high — each added layer increases the probability of a performance shortfall.")

    capex = "Medium–High" if n_stages >= 4 else "Low–Medium" if n_stages <= 2 else "Medium"
    disruption = "Low" if n_stages <= 2 else "Medium" if n_stages <= 4 else "Medium–High"
    timeline   = "3–7 years" if n_stages <= 3 else "7–15 years (staged)"

    return PathwaySummary(
        label            = "Brownfield intensification (recommended stack)",
        key_technologies = tech_labels,
        benefits         = benefits,
        risks            = risks,
        capex_class      = capex,
        disruption       = disruption,
        timeline_years   = timeline,
    )


def _replacement_pathway(
    pathway: UpgradePathway,
    ctx: Dict,
    recommendation: str,
) -> PathwaySummary:
    """Build the replacement pathway summary. Nereda always primary; MBR only if quality-driven."""
    ct_set     = {c.constraint_type for c in pathway.constraints}
    tp_tgt     = ctx.get("tp_target_mg_l", 1.)
    tn_tgt     = ctx.get("tn_out_upgraded_mg_l") or ctx.get("tn_target_mg_l", 10.)
    reuse_flag = bool(ctx.get("reuse_quality", False))
    is_mbr_plant = bool(ctx.get("is_mbr", False))

    # Core replacement technology: Nereda for BNR replacement
    techs = ["Nereda® AGS (replaces secondary biological treatment entirely)"]
    if tp_tgt is not None and float(tp_tgt) <= 0.2:
        techs.append("Tertiary phosphorus removal (chemical dosing + filtration)")
    if tn_tgt is not None and float(tn_tgt) <= 3.:
        techs.append("Denitrification filter (tertiary TN polishing if Nereda cannot achieve target)")
    # MBR only if reuse quality explicitly needed, not as a default
    if reuse_flag:
        techs.append("Tertiary MBR or UF polishing (if reuse-grade effluent required)")

    benefits = [
        "Compact footprint: Nereda AGS typically 30–50% smaller than conventional BNR.",
        "Integrated simultaneous nitrification-denitrification and P removal in one vessel.",
        "Eliminates secondary clarifiers — settling integrated within the AGS reactor.",
        "Single process architecture — no stacked specialist technologies or layered O&M.",
        "Positions plant for next 25–30 year asset life without further intensification upgrades.",
    ]
    if recommendation == STRONG_REPLACEMENT:
        benefits.insert(0,
            "Resolves all active constraints simultaneously through a single process conversion rather than sequencing five individual upgrades.")

    risks = [
        "High CAPEX: full civil decommissioning of existing secondary treatment required plus new reactor and ancillary construction.",
        "Operational disruption: cannot commission incrementally — plant must be taken out of service or an interim bypass strategy implemented.",
        "Granule stability risk: performance depends on maintaining stable aerobic granules. Recovery from upset is slower than conventional AS. Site-specific influent and temperature assessment required (particularly relevant at cold temperatures).",
        "Proprietary single-source process: supplier dependency for design, commissioning, and long-term support. Limited procurement flexibility.",
        "Startup risk: extended commissioning to establish stable granules. Seeding may be required. Full performance not immediate.",
    ]
    if not recommendation == STRONG_REPLACEMENT:
        risks.insert(0,
            "Full replacement is not necessary to achieve compliance targets — brownfield intensification remains viable at this level of constraint complexity.")

    capex      = "High"
    disruption = "High"
    timeline   = "5–10 years (planning, procurement, construction, commissioning)"

    return PathwaySummary(
        label            = "Greenfield / full process replacement",
        key_technologies = techs,
        benefits         = benefits,
        risks            = risks,
        capex_class      = capex,
        disruption       = disruption,
        timeline_years   = timeline,
    )


# ── Tipping point ─────────────────────────────────────────────────────────────

def _build_tipping_point(
    recommendation: str,
    pathway: UpgradePathway,
    ctx: Dict,
    total_score: int,
) -> TippingPoint:
    """Define what would shift the decision to the adjacent category."""
    ct_set = {c.constraint_type for c in pathway.constraints}
    fr     = ctx.get("flow_ratio", 1.0) or 1.0
    n_stages = len(pathway.stages)

    if recommendation == STRONG_BROWNFIELD:
        return TippingPoint(
            from_category = STRONG_BROWNFIELD,
            to_category   = BALANCED,
            triggers      = [
                "Addition of a second High-severity constraint (e.g. TN polishing alongside existing nitrification limitation) would shift to Balanced.",
                f"If peak flow ratio increases above 2.5× ADWF, hydraulic infrastructure investment would be required alongside biological upgrade.",
                "If the TN or TP licence target tightens below 5 mg/L or 0.5 mg/L respectively, tertiary treatment stages would be required.",
                "If aeration capacity is confirmed fully exhausted (blower audit), MABR replaces IFAS, adding specialist OEM dependency.",
            ],
        )
    elif recommendation == BALANCED:
        return TippingPoint(
            from_category = BALANCED,
            to_category   = STRONG_REPLACEMENT,
            triggers      = [
                f"If a sixth constraint emerges (e.g. membrane fouling, sludge handling failure), the brownfield stack would exceed manageable complexity.",
                f"If the footprint constraint prevents CoMag or EQ basin installation, the hydraulic failure mode becomes unresolvable through intensification.",
                "If the TN target tightens to < 3 mg/L while nitrification is currently failing, DNF cannot be installed without a preceding MABR upgrade — the prerequisite chain becomes too long to be deliverable in the required timeframe.",
                f"If peak flow ratio increases above 3.5× ADWF on a site where neither CoMag nor EQ basin can be installed, the primary constraint becomes unmanageable.",
                "If brownfield feasibility drops to Low (e.g. specialist supply chain failure in a critical technology), the risk-adjusted case for replacement improves materially.",
            ],
        )
    else:  # STRONG_REPLACEMENT
        return TippingPoint(
            from_category = STRONG_REPLACEMENT,
            to_category   = BALANCED,
            triggers      = [
                "If a proven short-term I/I reduction programme reduces peak flow to < 3× ADWF, the hydraulic constraint moves from infrastructure-grade to manageable via CoMag.",
                "If the future licence target is confirmed as TN < 5 mg/L (not 3 mg/L), the DNF stage is removed — reducing stack complexity materially.",
                "If site footprint is expanded through adjacent land acquisition, EQ basin becomes viable and hydraulic risk is substantially reduced.",
                f"If the plant has < 5 years of remaining asset life regardless of upgrade, replacement becomes preferable on lifecycle cost grounds irrespective of score.",
            ],
        )


# ── Rationale text ────────────────────────────────────────────────────────────

def _build_rationale(
    recommendation: str,
    total_score: int,
    dim_scores: Dict[str, int],
    pathway: UpgradePathway,
    ctx: Dict,
) -> str:
    ct_set   = {c.constraint_type for c in pathway.constraints}
    n_ct     = len(pathway.constraints)
    n_stages = len(pathway.stages)
    fr       = ctx.get("flow_ratio", 1.0) or 1.0
    tech_names = ", ".join(
        s.tech_display.split("(")[0].strip() for s in pathway.stages[:3])

    if recommendation == STRONG_BROWNFIELD:
        return (
            f"This plant has {n_ct} active constraint(s) addressable through a targeted "
            f"{n_stages}-stage brownfield upgrade ({tech_names}). The existing civil infrastructure retains its value and the upgrade can be staged and sequenced without major disruption. Full process replacement would over-invest relative to the performance gap — brownfield intensification is the engineering-appropriate response."
        )
    elif recommendation == BALANCED:
        dominant = ", ".join(
            c.constraint_type.replace("_limitation", "").replace("_", " ")
            for c in pathway.constraints[:3])
        return (
            f"This plant has {n_ct} interacting constraints ({dominant}) requiring a "
            f"{n_stages}-stage brownfield programme. The upgrade is feasible and delivers compliance within the existing plant envelope, but the combination of constraints and specialist technologies introduces delivery complexity that warrants serious evaluation of the replacement pathway on a whole-of-life cost basis. Brownfield is recommended for the current planning horizon; replacement should be included in the 15–20 year asset management plan."
        )
    else:
        return (
            f"This plant has {n_ct} interacting constraints at {fr:.1f}× ADWF peak, requiring "
            f"a {n_stages}-stage specialist upgrade stack to achieve compliance. The combination of extreme hydraulic loading, aeration capacity exhaustion, and licence targets at TN < 3 mg/L and TP < 0.1 mg/L creates a brownfield programme of exceptional complexity, where each added stage increases delivery risk and operational burden. While brownfield remains technically viable, replacement through Nereda AGS conversion warrants serious evaluation on a whole-of-life TOTEX basis, particularly if catchment flows are forecast to grow further."
        )


_DECISION_TENSION = (
    "The decision is between staged intensification of existing assets and full process replacement, trading delivery risk and disruption against long-term simplicity and performance. Brownfield preserves capital flexibility and keeps the plant operational throughout; replacement commits higher capital upfront in exchange for a simpler, consolidated process architecture and a clean 25–30 year asset horizon."
)


# ── Main entry point ───────────────────────────────────────────────────────────

def build_bf_gf_assessment(
    pathway: UpgradePathway,
    feasibility: FeasibilityReport,
    credible: CredibleOutput,
    plant_context: Optional[Dict] = None,
) -> BFGFAssessment:
    """
    Build the Brownfield vs Greenfield strategic assessment.

    Parameters
    ----------
    pathway     : UpgradePathway   — output of build_upgrade_pathway()
    feasibility : FeasibilityReport — output of assess_feasibility()
    credible    : CredibleOutput    — output of build_credible_output()
    plant_context : dict, optional  — same context dict passed to other layers

    Returns
    -------
    BFGFAssessment
        Does NOT modify any input object.
    """
    ctx = plant_context or {}

    # ── Score each dimension ───────────────────────────────────────────────────
    s_ct,    n_ct    = _score_constraint_count(pathway)
    s_sev,   n_sev   = _score_constraint_severity(pathway)
    s_stack, n_stack = _score_stack_complexity(pathway, feasibility)
    s_lic,   n_lic   = _score_tn_tp_stringency(pathway, ctx)
    s_feas,  n_feas  = _score_feasibility(feasibility)
    s_flow,  n_flow  = _score_flow_ratio(ctx)
    s_foot,  n_foot  = _score_footprint(ctx)

    dim_scores = {
        "Constraint count"    : s_ct,
        "Constraint severity" : s_sev,
        "Stack complexity"    : s_stack,
        "Licence stringency"  : s_lic,
        "Feasibility overhead": s_feas,
        "Flow ratio"          : s_flow,
        "Footprint"           : s_foot,
    }
    dim_notes = {
        "Constraint count"    : n_ct,
        "Constraint severity" : n_sev,
        "Stack complexity"    : n_stack,
        "Licence stringency"  : n_lic,
        "Feasibility overhead": n_feas,
        "Flow ratio"          : n_flow,
        "Footprint"           : n_foot,
    }
    total = sum(dim_scores.values())

    # Fix 4: Greenfield mode — reduce hydraulic/footprint penalty,
    # reframe as design optimisation not brownfield intensification
    _gf_mode = bool(ctx.get('greenfield', False))
    _gf_bonus = 0
    if _gf_mode:
        # On a new plant, hydraulic and footprint constraints are design variables
        # — they do not drive toward replacement. Reduce their contribution.
        _gf_bonus = min(s_foot + s_flow, 4)   # remove up to 4 pts of footprint/flow penalty
        total = max(0, total - _gf_bonus)
        dim_notes['Flow ratio'] = (
            '[Greenfield] Hydraulic sizing is a design variable on a new plant. '
            + dim_notes.get('Flow ratio', '')
        )
        dim_notes['Footprint'] = (
            '[Greenfield] Footprint is a design variable on a new plant. '
            + dim_notes.get('Footprint', '')
        )

    # ── Classify ─────────────────────────────────────────────────────────
    # Fix 4: escalate when compliance gap is proven (gap_in_ctx + TN median not credible)
    _gap_ctx = bool(ctx.get("stack_compliance_gap", False))
    _tn_med_nc = ctx.get("tn_median_not_credible", False)
    if _gap_ctx and _tn_med_nc:
        total = total + 4
        dim_notes["Compliance"] = (
            "Stack compliance gap confirmed: TN cannot be met under average conditions. "
            "Replacement pressure elevated."
        )

    if total <= 4:
        recommendation = STRONG_BROWNFIELD
    elif total <= 9:
        recommendation = BALANCED
    else:
        recommendation = STRONG_REPLACEMENT

    # ── Build pathways ─────────────────────────────────────────────────────────
    bf = _brownfield_pathway(pathway, feasibility, recommendation)
    gf = _replacement_pathway(pathway, ctx, recommendation)
    tp = _build_tipping_point(recommendation, pathway, ctx, total)

    rationale = _build_rationale(recommendation, total, dim_scores, pathway, ctx)

    # ── Validation flags ───────────────────────────────────────────────────────
    # Nereda must not appear in brownfield pathway
    nereda_bf_ok = not any("nereda" in t.lower() for t in bf.key_technologies)
    # Nereda must appear in replacement pathway
    nereda_gf_ok = any("nereda" in t.lower() for t in gf.key_technologies)
    nereda_ok    = nereda_bf_ok and nereda_gf_ok

    # MBR: only in replacement pathway, only when reuse_quality or explicit MBR flag
    reuse = bool(ctx.get("reuse_quality", False)) or bool(ctx.get("is_mbr", False))
    mbr_in_gf = any("mbr" in t.lower() for t in gf.key_technologies)
    mbr_ok = (not mbr_in_gf) or reuse   # MBR in GF only when quality-driven

    # Brownfield key_technologies must reflect actual stack stages
    stack_names_lower = {s.tech_display.split("(")[0].strip().lower()
                         for s in pathway.stages}
    bf_names_lower    = {t.lower() for t in bf.key_technologies}
    bf_reflects = bool(stack_names_lower & bf_names_lower)   # at least partial overlap

    return BFGFAssessment(
        total_score              = total,
        dimension_scores         = dim_scores,
        dimension_notes          = dim_notes,
        recommendation           = recommendation,
        rationale                = rationale,
        brownfield_pathway       = bf,
        replacement_pathway      = gf,
        tipping_point            = tp,
        decision_tension         = _DECISION_TENSION,
        nereda_in_replacement_only = nereda_ok,
        mbr_appropriately_positioned = mbr_ok,
        brownfield_reflects_stack    = bf_reflects,
    )
