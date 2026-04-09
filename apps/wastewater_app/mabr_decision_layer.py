"""
apps/wastewater_app/mabr_decision_layer.py

MABR Decision Layer — WaterPoint v24Z37
=======================================

Produces a structured MABRAssessment dataclass covering:
  1. Role classification     — one of five WaterPoint MABR roles
  2. Carbon strategy score   — 0 (absent) / 1 (partial) / 2 (confirmed)
  3. Whole-plant value test  — passes / fails, with reasoning
  4. Net energy test         — qualitative (positive / neutral / negative)
  5. Complexity / risk score — 0–8 integer (number of active risk factors)
  6. System comparison table — MABR vs BNR vs IFAS vs AGS
  7. WaterPoint decision     — strategically preferred / conditionally preferred /
                               situationally useful / not preferred
  8. Narrative sections      — role, enables, replaces, risks, conclusion

Design principles
-----------------
- Pure functions, deterministic, fully explainable
- All outputs driven by plant_context dict — no side effects
- NP-1 / NP-2 / NP-3 guards mirror stack_generator and credibility_layer exactly
- Comparison table is always produced regardless of MABR preference
- Never praises MABR generically — local vs whole-plant benefit is always distinguished

Called by credibility_layer.build_credible_output().
Rendered by waterpoint_ui.py in expander E_MABR (after E7b).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


# ── Role constants ─────────────────────────────────────────────────────────────

MABR_ROLE_CORE      = "Core mainstream nitrogen module"
MABR_ROLE_RETROFIT  = "Retrofit intensification module"
MABR_ROLE_POLISH    = "Polishing / ammonia compliance module"
MABR_ROLE_NICHE     = "Niche constrained-site solution"
MABR_ROLE_NP        = "Not preferred"

# WaterPoint decision labels
MABR_DEC_STRATEGIC    = "Strategically preferred"
MABR_DEC_CONDITIONAL  = "Conditionally preferred"
MABR_DEC_SITUATIONAL  = "Situationally useful"
MABR_DEC_NP           = "Not preferred"

# Carbon strategy score labels
CS_ABSENT    = 0   # No upstream carbon capture identified
CS_PARTIAL   = 1   # Some carbon capture element present but not confirmed system-wide
CS_CONFIRMED = 2   # Front-end carbon-capture-first architecture confirmed

# Net energy verdict
ENERGY_POSITIVE  = "Positive — net whole-plant aeration reduction expected"
ENERGY_NEUTRAL   = "Neutral — marginal net benefit; confirm with site energy audit"
ENERGY_NEGATIVE  = "Negative / unclear — auxiliary loads may offset local OTE gain"


# ── Result dataclasses ─────────────────────────────────────────────────────────

@dataclass
class MABRComparisonRow:
    """One row of the system-level technology comparison table."""
    technology:       str
    system_role:      str
    carbon_alignment: str
    aeration_energy:  str
    retrofit_fit:     str
    complexity:       str
    best_application: str
    waterpoint_view:  str


@dataclass
class MABRAssessment:
    """
    Complete WaterPoint MABR decision assessment for a single plant scenario.

    Produced by assess_mabr() and stored on CredibleOutput.
    Rendered as a dedicated UI expander in waterpoint_ui.py.
    """
    # ── Classification ─────────────────────────────────────────────────────────
    role:                str    # one of MABR_ROLE_* constants
    decision:            str    # one of MABR_DEC_* constants

    # ── Scored inputs ──────────────────────────────────────────────────────────
    carbon_strategy_score:    int    # 0 / 1 / 2
    carbon_strategy_label:    str    # "Absent" / "Partial" / "Confirmed"
    complexity_risk_score:    int    # 0–8 (number of active risk factors)
    active_risk_factors:      List[str]
    net_energy_verdict:       str    # ENERGY_* constant

    # ── NP guard evaluation ───────────────────────────────────────────────────
    np1_triggered: bool
    np2_triggered: bool
    np3_triggered: bool
    np_reason:     str   # blank if no guard triggered

    # ── Whole-plant value test ────────────────────────────────────────────────
    wpv_passes:  List[str]   # criteria that support MABR
    wpv_fails:   List[str]   # criteria that undermine MABR

    # ── Narrative sections ────────────────────────────────────────────────────
    best_fit_role_in_plant:  str   # where MABR sits in the plant sequence
    what_it_replaces:        str   # what MABR actually displaces
    what_it_enables:         str   # plant-level benefits
    risks_introduced:        str   # hidden complexity, dependencies
    conclusion:              str   # final strategic conclusion

    # ── Comparison table ──────────────────────────────────────────────────────
    comparison_table: List[MABRComparisonRow]   # always 4 rows: MABR, BNR, IFAS, AGS


# ── Internal helpers ───────────────────────────────────────────────────────────

def _carbon_strategy_score(ctx: Dict) -> Tuple[int, str]:
    """
    Score the carbon-capture strategy from plant_context.
    Returns (score: 0/1/2, label: str).

    CS_CONFIRMED (2): explicit carbon-capture-first architecture flag set
                      (carbon_capture_upstream, aaa_upstream, or enhanced_primary)
    CS_PARTIAL   (1): a partial carbon strategy signal present
                      (high_rate_primary or carbon_diversion flag, but not full system)
    CS_ABSENT    (0): no carbon strategy signal detected

    Note: aeration_constrained alone is NOT a carbon strategy signal — it is an
    operational constraint that makes MABR more attractive, but it does not imply
    upstream carbon capture exists.
    """
    has_confirmed = bool(
        ctx.get("carbon_capture_upstream")
        or ctx.get("aaa_upstream")
        or ctx.get("enhanced_primary")
    )
    has_partial = bool(
        ctx.get("high_rate_primary")
        or ctx.get("carbon_diversion")
    )
    if has_confirmed:
        return CS_CONFIRMED, "Confirmed"
    if has_partial:
        return CS_PARTIAL, "Partial"
    return CS_ABSENT, "Absent"


def _np_guards(ctx: Dict) -> Tuple[bool, bool, bool, str]:
    """
    Evaluate NP-1 / NP-2 / NP-3 guards.
    Returns (np1, np2, np3, reason_string).
    """
    has_c_strategy = bool(
        ctx.get("carbon_capture_upstream")
        or ctx.get("aaa_upstream")
        or ctx.get("enhanced_primary")
    )
    greenfield    = bool(ctx.get("greenfield", False))
    location      = ctx.get("location_type", "metro") or "metro"
    size_mld      = float(ctx.get("plant_size_mld", 10.) or 10.)
    instr_capable = bool(ctx.get("instrumentation_capable", True))
    aer_headroom  = float(ctx.get("aeration_headroom_pct", 0.) or 0.)

    np1 = not has_c_strategy and not greenfield
    np2 = (location == "remote" or size_mld < 5.0) and not instr_capable
    np3 = aer_headroom >= 15.0

    reasons = []
    if np1:
        reasons.append(
            "NP-1: No carbon-capture-first architecture identified. MABR without upstream "
            "carbon strategy delivers marginal whole-plant benefit at real auxiliary system "
            "complexity cost. IFAS is preferred."
        )
    if np2:
        site_desc = "Remote location" if location == "remote" else f"Small plant ({size_mld:.1f} MLD)"
        reasons.append(
            f"NP-2: {site_desc} without confirmed instrumentation capability. MABR requires "
            "dual blower, 10 µm air filtration, condensate management, exhaust O₂ and NH₄ "
            "monitoring — disproportionate dependency for this operating environment."
        )
    if np3:
        reasons.append(
            f"NP-3: Aeration headroom {aer_headroom:.0f}% ≥ 15% confirmed. IFAS delivers "
            "equivalent nitrification SRT intensification at lower auxiliary system burden. "
            "MABR is not required when the blower is not the binding constraint."
        )

    return np1, np2, np3, " ".join(reasons)


def _complexity_risk(ctx: Dict) -> Tuple[int, List[str]]:
    """
    Score MABR complexity / risk factors for this plant context.
    Returns (score: 0–8, active_factors: List[str]).
    """
    factors: List[str] = []

    # Factor 1: dual blower system — always required for MABR
    factors.append(
        "Dual blower system required (process air + separate scour/mixing air circuit)."
    )

    # Factor 2: fine air filtration
    factors.append(
        "Fine air filtration (10 µm) required on process air supply — adds maintenance dependency."
    )

    # Factor 3: condensate management
    factors.append(
        "Condensate removal system required — ongoing inspection and drain management."
    )

    # Factor 4: instrumentation dependency
    factors.append(
        "Instrumentation required: inlet air pressure, inlet flow, ambient temperature, "
        "exhaust O₂ concentration, ammonia concentration."
    )

    # Factor 5: supplemental mixing — risk elevated if tank not fully occupied
    footprint_constrained = bool(ctx.get("footprint_constrained", False))
    if not footprint_constrained:
        factors.append(
            "Supplemental mixing likely required if existing tank volume is not fully "
            "occupied by MABR cassettes — erodes apparent simplicity advantage."
        )

    # Factor 6: biofilm management
    factors.append(
        "Periodic air isolation required to disrupt higher life forms on membranes. "
        "Periodic cassette inspection and asset maintenance programme needed."
    )

    # Factor 7: operator skill dependency
    location = ctx.get("location_type", "metro") or "metro"
    size_mld = float(ctx.get("plant_size_mld", 10.) or 10.)
    if location in ("regional", "remote") or size_mld < 10.:
        factors.append(
            "Elevated operator skill dependency for this plant size / location. Specialist "
            "OEM support agreements and trained on-site operators required at commissioning."
        )

    # Factor 8: net energy balance not confirmed
    aer_constrained = bool(ctx.get("aeration_constrained", False))
    if not aer_constrained:
        factors.append(
            "Net whole-plant energy balance not confirmed by aeration constraint signal — "
            "auxiliary blower loads (process air + scour + mixing) may partially offset OTE gain."
        )

    return len(factors), factors


def _net_energy_verdict(ctx: Dict) -> str:
    """
    Qualitative net energy verdict based on plant context.
    """
    aer_constrained   = bool(ctx.get("aeration_constrained", False))
    has_c_strategy    = bool(
        ctx.get("carbon_capture_upstream") or ctx.get("aaa_upstream")
        or ctx.get("enhanced_primary")
    )
    footprint_constrained = bool(ctx.get("footprint_constrained", False))

    if aer_constrained and has_c_strategy:
        return ENERGY_POSITIVE
    if aer_constrained and not has_c_strategy:
        return ENERGY_NEUTRAL
    return ENERGY_NEGATIVE


def _wpv_test(ctx: Dict) -> Tuple[List[str], List[str]]:
    """
    Whole-plant value test — returns (passes, fails).
    """
    passes: List[str] = []
    fails:  List[str] = []

    aer_constrained   = bool(ctx.get("aeration_constrained", False))
    has_c_strategy    = bool(
        ctx.get("carbon_capture_upstream") or ctx.get("aaa_upstream")
        or ctx.get("enhanced_primary")
    )
    instr_capable     = bool(ctx.get("instrumentation_capable", True))
    footprint_const   = bool(ctx.get("footprint_constrained", False))
    greenfield        = bool(ctx.get("greenfield", False))
    size_mld          = float(ctx.get("plant_size_mld", 10.) or 10.)
    tn_target         = float(ctx.get("tn_target_mg_l", 10.) or 10.)
    aer_headroom      = float(ctx.get("aeration_headroom_pct", 0.) or 0.)
    location          = ctx.get("location_type", "metro") or "metro"

    # Aeration burden
    if aer_constrained:
        passes.append("Reduces total plant aeration burden — blower is the confirmed binding constraint.")
    else:
        fails.append("Aeration constraint not confirmed — bulk aeration burden reduction is not assured.")

    # Carbon strategy
    if has_c_strategy:
        passes.append("Supports carbon preservation upstream — reduces reliance on conventional bulk aeration "
                      "that would otherwise oxidise influent rbCOD.")
    else:
        fails.append("No upstream carbon capture strategy — MABR improves one reactor without changing "
                     "the plant-wide carbon oxidation philosophy.")

    # Tank volume / civil works
    if footprint_const or greenfield is False:
        passes.append("Reduces need for new tank volume — cassette installation into existing tankage "
                      "is the key retrofit value proposition.")
    else:
        passes.append("Greenfield application — MABR creates a more sensor-driven, low-footprint "
                      "nitrogen conversion architecture.")

    # Nitrogen pathway efficiency
    if tn_target <= 10.:
        passes.append(f"Stringent TN target ({tn_target:.0f} mg/L) — efficient biofilm nitrification "
                      "reduces aeration-driven nitrification bottleneck.")
    else:
        fails.append(f"TN target ({tn_target:.0f} mg/L) is not particularly stringent — aeration "
                     "efficiency gains may not justify auxiliary complexity.")

    # AI/ML compatibility
    if instr_capable:
        passes.append("Instrumentation capability confirmed — MABR sensor architecture (exhaust O₂, NH₄) "
                      "creates a better platform for AI/ML aeration control.")
    else:
        fails.append("Instrumentation capability not confirmed — MABR sensor dependency creates "
                     "operational risk without corresponding control benefit.")

    # Lifecycle complexity
    _, factors = _complexity_risk(ctx)
    if len(factors) <= 4:
        passes.append("Auxiliary system complexity is manageable — complexity/risk score within "
                      "acceptable range for this plant context.")
    else:
        fails.append(f"Auxiliary system complexity elevated — {len(factors)} active risk factors "
                     "identified. Confirm net whole-plant gain exceeds operational burden.")

    # Headroom
    if aer_headroom >= 15.:
        fails.append(f"Aeration headroom {aer_headroom:.0f}% ≥ 15% — IFAS achieves equivalent "
                     "nitrification intensification at lower complexity.")

    return passes, fails


def _classify_role(ctx: Dict, np1: bool, np2: bool, np3: bool) -> str:
    """
    Classify MABR into one of five WaterPoint roles.
    """
    if np1 or np2 or np3:
        return MABR_ROLE_NP

    aer_constrained = bool(ctx.get("aeration_constrained", False))
    has_c_strategy  = bool(
        ctx.get("carbon_capture_upstream") or ctx.get("aaa_upstream")
        or ctx.get("enhanced_primary")
    )
    greenfield      = bool(ctx.get("greenfield", False))
    footprint_const = bool(ctx.get("footprint_constrained", False))
    tn_target       = float(ctx.get("tn_target_mg_l", 10.) or 10.)

    if has_c_strategy and aer_constrained:
        if greenfield:
            return MABR_ROLE_CORE
        return MABR_ROLE_RETROFIT

    if aer_constrained and footprint_const:
        return MABR_ROLE_RETROFIT

    if tn_target <= 5. or ctx.get("cold_climate_risk"):
        return MABR_ROLE_POLISH

    if footprint_const and not aer_constrained:
        return MABR_ROLE_NICHE

    return MABR_ROLE_RETROFIT


def _decision_label(role: str, cs_score: int, np1: bool, np2: bool, np3: bool) -> str:
    """
    Map role + carbon strategy score to WaterPoint decision label.
    """
    if role == MABR_ROLE_NP:
        return MABR_DEC_NP
    if role == MABR_ROLE_CORE and cs_score == CS_CONFIRMED:
        return MABR_DEC_STRATEGIC
    if role in (MABR_ROLE_CORE, MABR_ROLE_RETROFIT) and cs_score >= CS_PARTIAL:
        return MABR_DEC_CONDITIONAL
    if role in (MABR_ROLE_POLISH, MABR_ROLE_NICHE):
        return MABR_DEC_SITUATIONAL
    return MABR_DEC_CONDITIONAL


# ── Narrative builders ─────────────────────────────────────────────────────────

def _narrative_role_in_plant(role: str, ctx: Dict) -> str:
    has_c = bool(ctx.get("carbon_capture_upstream") or ctx.get("aaa_upstream")
                 or ctx.get("enhanced_primary"))
    if role == MABR_ROLE_CORE:
        return (
            "MABR sits downstream of front-end carbon capture (AAA / high-rate clarification). "
            "It receives carbon-limited, pre-settled flow and delivers efficient mainstream "
            "nitrification via membrane oxygen transfer without bulk aeration of the full liquid "
            "volume. This is its strongest architectural position — the carbon strategy creates "
            "the oxygen-efficiency gap that MABR is designed to fill."
        )
    if role == MABR_ROLE_RETROFIT:
        return (
            "MABR cassettes are installed into existing aeration or anoxic tank volume, "
            "providing nitrification intensification without new civil works. "
            + ("With upstream carbon capture confirmed, MABR reduces the bulk aeration demand "
               "on the remainder of the bioreactor train. "
               if has_c else
               "Aeration constraint is the primary justification — MABR bypasses the blower "
               "ceiling by delivering oxygen directly to the biofilm. ")
            + "No hydraulic grade-line modification is required."
        )
    if role == MABR_ROLE_POLISH:
        return (
            "MABR is positioned as a polishing module downstream of secondary treatment — "
            "targeting final effluent NH₃ compliance, cold-climate nitrification resilience, "
            "or ammonia-peak attenuation. It does not carry the primary nitrogen removal load "
            "in this configuration."
        )
    if role == MABR_ROLE_NICHE:
        return (
            "MABR is deployed as a niche solution to an extreme footprint or site constraint "
            "where no alternative intensification technology can be physically accommodated. "
            "The decision is driven by constraint, not by strategic preference."
        )
    return (
        "MABR is not selected for this plant architecture. IFAS or conventional BNR is "
        "the appropriate nitrogen management approach given the plant context."
    )


def _narrative_replaces(role: str, ctx: Dict) -> str:
    if role == MABR_ROLE_NP:
        return "MABR replaces nothing in this configuration — it is not selected."
    if role == MABR_ROLE_CORE:
        return (
            "MABR replaces new aeration basin volume that would otherwise be required to "
            "achieve mainstream nitrogen conversion in a carbon-limited post-capture flow stream. "
            "It also displaces the need for expanded blower capacity by delivering oxygen "
            "at 7–10× the efficiency of conventional diffused aeration."
        )
    if role == MABR_ROLE_RETROFIT:
        return (
            "MABR replaces the need for new aeration basin civil works to address the nitrification "
            "constraint. It displaces a blower capacity upgrade by providing biofilm-based "
            "nitrification that is independent of bulk aeration headroom."
        )
    if role == MABR_ROLE_POLISH:
        return (
            "MABR replaces a conventional polishing aeration stage or UV/chemical ammonia "
            "management where the primary concern is final effluent NH₃ rather than bulk "
            "nitrogen removal."
        )
    return (
        "MABR replaces a more complex or space-intensive intensification alternative that "
        "cannot be physically accommodated at this constrained site."
    )


def _narrative_enables(role: str, ctx: Dict) -> str:
    has_c = bool(ctx.get("carbon_capture_upstream") or ctx.get("aaa_upstream")
                 or ctx.get("enhanced_primary"))
    instr = bool(ctx.get("instrumentation_capable", True))
    lines: List[str] = []

    if role == MABR_ROLE_CORE and has_c:
        lines.append("Carbon preservation — upstream rbCOD is directed to energy recovery rather than oxidised.")
    if role in (MABR_ROLE_CORE, MABR_ROLE_RETROFIT):
        lines.append("Capacity expansion without new tank volume — cassette count scales with flow growth.")
    lines.append("Footprint savings relative to conventional nitrification tank expansion.")
    if instr:
        lines.append(
            "AI/ML control platform — exhaust O₂ and NH₄ sensors create real-time nitrification "
            "feedback that is not available with conventional diffused aeration."
        )
    if role == MABR_ROLE_POLISH:
        lines.append("Cold-climate nitrification robustness — biofilm maintains nitrification at "
                     "temperatures that suppress suspended growth nitrifiers.")
    lines.append("Staged retrofit upgrade pathway — cassette addition is modular and phased.")

    return " ".join(f"• {l}" for l in lines)


def _narrative_risks(ctx: Dict, factors: List[str]) -> str:
    return (
        "The following operational dependencies and risks apply to this configuration:\n"
        + "\n".join(f"  {i+1}. {f}" for i, f in enumerate(factors))
    )


def _narrative_conclusion(decision: str, role: str, ctx: Dict, cs_score: int) -> str:
    has_c = bool(ctx.get("carbon_capture_upstream") or ctx.get("aaa_upstream")
                 or ctx.get("enhanced_primary"))
    aer   = bool(ctx.get("aeration_constrained", False))
    instr = bool(ctx.get("instrumentation_capable", True))

    if decision == MABR_DEC_STRATEGIC:
        return (
            "MABR is strategically preferred for this configuration. The carbon-capture-first "
            "architecture upstream, confirmed aeration constraint, and instrumentation capability "
            "all align to create the conditions where MABR delivers genuine whole-plant benefit — "
            "not just local reactor improvement. It should be treated as a core architecture "
            "element, not a bolt-on."
        )
    if decision == MABR_DEC_CONDITIONAL:
        reason = (
            "carbon-capture architecture is confirmed" if has_c else
            "aeration constraint is confirmed"
        )
        return (
            f"MABR is conditionally preferred — {reason}. "
            "It should be taken to detailed engineering assessment with explicit evaluation of: "
            "(1) net whole-plant energy balance, (2) auxiliary system CAPEX and OPEX, "
            "(3) operator capability confirmation. IFAS remains a valid alternative if "
            "the detailed assessment reveals that auxiliary complexity does not justify the "
            "oxygen transfer efficiency gain."
        )
    if decision == MABR_DEC_SITUATIONAL:
        return (
            "MABR is situationally useful — it addresses a specific constraint (polishing, "
            "cold climate, extreme footprint) where its characteristics are genuinely helpful. "
            "It is not a system-wide architecture choice in this configuration. Evaluate "
            "against simpler polishing alternatives before committing to MABR's auxiliary "
            "system requirements."
        )
    # Not preferred
    return (
        "MABR is not preferred for this plant configuration. The WaterPoint whole-plant value "
        "test identifies that the auxiliary system complexity and operational dependency are "
        "not justified by the available whole-plant benefit. "
        + ("IFAS is the appropriate nitrification intensification alternative — lower complexity, "
           "broader operator skill base, and adequate SRT decoupling for this scenario."
           if not has_c else
           "Confirm whether a more complete carbon-capture strategy would shift this assessment "
           "before dismissing MABR entirely.")
    )


# ── Comparison table builder ───────────────────────────────────────────────────

def _build_comparison_table() -> List[MABRComparisonRow]:
    """
    Produce the four-technology system-level comparison table.
    Always generated regardless of MABR preference — the table is context-independent.
    """
    return [
        MABRComparisonRow(
            technology       = "MABR (OxyFAS)",
            system_role      = "Controlled-oxygen biofilm nitrogen module",
            carbon_alignment = "Strong — supports carbon-capture-first architecture by reducing bulk aeration demand",
            aeration_energy  = "Low to moderate — high OTE (25–50%) but blower + scour + mixing overhead reduces net gain",
            retrofit_fit     = "High — cassette installation in existing tanks; no hydraulic grade-line impact",
            complexity       = "Moderate–High — dual blower, condensate, 10 µm filtration, exhaust O₂ and NH₄ instrumentation",
            best_application = "Carbon-capture-first architecture; aeration-constrained retrofit; cold-climate NH₃ compliance; footprint-constrained upgrades with instrumentation capability",
            waterpoint_view  = "Conditionally preferred where carbon strategy + aeration constraint + instrumentation capability all confirmed",
        ),
        MABRComparisonRow(
            technology       = "Conventional BNR",
            system_role      = "Full-volume suspended growth nitrification / denitrification",
            carbon_alignment = "Poor — oxidises influent rbCOD in bulk aeration volume",
            aeration_energy  = "High — full tank volume aerated; bulk blower capacity scales with load",
            retrofit_fit     = "Low — capacity upgrade requires new basin volume or blower expansion",
            complexity       = "Low to Moderate — well-understood; broad operator skill base; standard OEM support",
            best_application = "Greenfield conventional plants; low-complexity operating environments; risk-averse clients without instrumentation maturity",
            waterpoint_view  = "Default for low-complexity environments; appropriate where carbon strategy is absent and simplicity is a priority",
        ),
        MABRComparisonRow(
            technology       = "IFAS / MBBR",
            system_role      = "Suspended growth + attached growth intensification (SRT decoupling)",
            carbon_alignment = "Moderate — compatible with upstream carbon capture; does not actively compete with it",
            aeration_energy  = "Moderate — partially reduced; relies on existing blower with media augmentation",
            retrofit_fit     = "High — media drops into existing aeration zone; retention screens at zone outlets",
            complexity       = "Moderate — media management, retention screen maintenance; no blower or condensate dependency",
            best_application = "Brownfield intensification where aeration headroom ≥ 15%; capacity expansion without new civil; environments where MABR auxiliary complexity is not justified",
            waterpoint_view  = "Preferred retrofit intensification where NP-3 applies (headroom confirmed) or carbon strategy is absent — lower complexity than MABR for equivalent SRT benefit",
        ),
        MABRComparisonRow(
            technology       = "AGS (Nereda)",
            system_role      = "Granular SBR — complete N and P removal in single compact vessel",
            carbon_alignment = "Strong — internal carbon storage within granule; efficient simultaneous N and P",
            aeration_energy  = "Low — highly efficient O₂ use within granule; no scour or supplemental blower systems",
            retrofit_fit     = "Moderate — SBR batch cycle format; compact footprint but operationally distinct from conventional CAS",
            complexity       = "Moderate–High — granule stability management; selective pressure maintenance; cycle control sophistication",
            best_application = "Greenfield or major brownfield with strong footprint constraints; clients accepting operational maturity investment for long-term energy and chemical efficiency",
            waterpoint_view  = "Preferred greenfield option where footprint, energy efficiency, and operational maturity all align — competes with MABR at greenfield; MABR preferred only when carbon-capture architecture is the primary system driver",
        ),
    ]


# ── Primary entry point ────────────────────────────────────────────────────────

def assess_mabr(plant_context: Optional[Dict] = None) -> MABRAssessment:
    """
    Produce a complete MABRAssessment for the given plant_context.

    Parameters
    ----------
    plant_context : dict, optional
        Same dict used by stack_generator and credibility_layer.
        Relevant keys:
          carbon_capture_upstream, aaa_upstream, enhanced_primary
          aeration_constrained, aeration_headroom_pct
          instrumentation_capable
          location_type, plant_size_mld
          footprint_constrained, greenfield
          tn_target_mg_l, cold_climate_risk

    Returns
    -------
    MABRAssessment
        Structured assessment — always produced, regardless of MABR preference.
    """
    ctx = plant_context or {}

    # Scored inputs
    cs_score, cs_label = _carbon_strategy_score(ctx)
    np1, np2, np3, np_reason = _np_guards(ctx)
    complexity_score, active_factors = _complexity_risk(ctx)
    energy_verdict = _net_energy_verdict(ctx)
    wpv_passes, wpv_fails = _wpv_test(ctx)

    # Classification
    role     = _classify_role(ctx, np1, np2, np3)
    decision = _decision_label(role, cs_score, np1, np2, np3)

    # Narratives
    role_in_plant  = _narrative_role_in_plant(role, ctx)
    what_replaces  = _narrative_replaces(role, ctx)
    what_enables   = _narrative_enables(role, ctx)
    risks          = _narrative_risks(ctx, active_factors)
    conclusion     = _narrative_conclusion(decision, role, ctx, cs_score)

    # Comparison table — always built
    comparison = _build_comparison_table()

    return MABRAssessment(
        role                  = role,
        decision              = decision,
        carbon_strategy_score = cs_score,
        carbon_strategy_label = cs_label,
        complexity_risk_score = complexity_score,
        active_risk_factors   = active_factors,
        net_energy_verdict    = energy_verdict,
        np1_triggered         = np1,
        np2_triggered         = np2,
        np3_triggered         = np3,
        np_reason             = np_reason,
        wpv_passes            = wpv_passes,
        wpv_fails             = wpv_fails,
        best_fit_role_in_plant= role_in_plant,
        what_it_replaces      = what_replaces,
        what_it_enables       = what_enables,
        risks_introduced      = risks,
        conclusion            = conclusion,
        comparison_table      = comparison,
    )
