"""
apps/wastewater_app/stack_generator.py

Technology Stack Generator — Production V1
==========================================

Converts WaterPoint diagnostics (WaterPointResult) directly into
engineering-grade, sequenced multi-technology upgrade pathways.

This is a synthesis layer only. It does NOT modify any existing
calculation engine, stress model, or failure mode engine.

Design principles
-----------------
- Deterministic and explainable — every output has a traceable reason
- Reads WaterPointResult + optional plant_context dict
- Produces UpgradePathway: a consultant-grade concept design recommendation
- Failure mode titles and severity drive constraint classification
- Strict priority ordering: hydraulic → settling → nitrification → TN → TP → optimisation
- Engineering guardrails enforced before any stage is emitted

New technologies added here (not in prior modules):
  TI_DENFILTER  — denitrification filter (methanol-dosed tertiary denitrification)
  TI_TERT_P     — tertiary phosphorus removal (chemical dosing + filtration)
  MECH_TERT_DN  — tertiary denitrification
  MECH_TERT_P   — tertiary phosphorus removal
  MECH_AER_INT  — aeration intensification

All other constants re-imported from intensification_intelligence.py.

Main entry point
----------------
  build_upgrade_pathway(wp_result, plant_context) -> UpgradePathway
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


# ── Re-use constants from intelligence layer ───────────────────────────────────
from apps.wastewater_app.intensification_intelligence import (
    CT_SETTLING, CT_NITRIFICATION, CT_BIOLOGICAL, CT_MEMBRANE,
    CT_HYDRAULIC, CT_WET_WEATHER, CT_MULTI, CT_UNKNOWN,
    MECH_BIOMASS_SEL, MECH_BIOFILM_RET, MECH_PROC_OPT,
    MECH_MEMBRANE_SEL, MECH_HYD_EXP, MECH_BALLASTED,
    TI_INDENSE, TI_MEMDENSE, TI_HYBAS, TI_MBBR, TI_IFAS,
    TI_BARDENPHO, TI_RECYCLE_OPT, TI_ZONE_RECONF,
    TI_EQ_BASIN, TI_STORM_STORE, TI_MIGINDENSE,
    TI_COMAG, TI_BIOMAG,
)

# ── New constants for Production V1 ───────────────────────────────────────────
CT_TN_POLISH    = "tn_polishing_limitation"
CT_TP_POLISH    = "tp_polishing_limitation"

MECH_TERT_DN    = "tertiary_denitrification"
MECH_TERT_P     = "tertiary_phosphorus_removal"
MECH_AER_INT    = "aeration_intensification"

TI_DENFILTER    = "Denitrification Filter"
TI_PDNA         = "PdNA (Partial Denitrification-Anammox)"
TI_TERT_P       = "Tertiary P removal"
TI_MABR         = "MABR (OxyFAS retrofit)"

_CT_LABELS_V1 = {
    CT_HYDRAULIC:    "Hydraulic / throughput limitation",
    CT_WET_WEATHER:  "Wet weather peak / overflow",
    CT_SETTLING:     "Settling / solids separation",
    CT_NITRIFICATION:"Nitrification / SRT limitation",
    CT_TN_POLISH:    "TN polishing (NOx / carbon-limited denitrification)",
    CT_TP_POLISH:    "TP polishing (tertiary P removal required)",
    CT_BIOLOGICAL:   "Biological performance (TN/TP/EBPR)",
    CT_MEMBRANE:     "Membrane performance limitation",
    CT_MULTI:        "Multi-constraint",
    CT_UNKNOWN:      "Unknown",
}

_MECH_LABELS_V1 = {
    MECH_BALLASTED:  "Ballasted settling / high-rate clarification",
    MECH_HYD_EXP:   "Hydraulic expansion / attenuation storage",
    MECH_BIOMASS_SEL:"Biomass selection",
    MECH_BIOFILM_RET:"Biofilm retention (SRT decoupling)",
    MECH_AER_INT:    "Aeration intensification (membrane O₂ delivery)",
    MECH_TERT_DN:    "Tertiary denitrification",
    MECH_TERT_P:     "Tertiary phosphorus removal",
    MECH_PROC_OPT:   "Process optimisation",
    MECH_MEMBRANE_SEL:"Membrane biomass selection",
}

_PRIORITY = {
    CT_HYDRAULIC:    1,
    CT_WET_WEATHER:  1,
    CT_SETTLING:     2,
    CT_NITRIFICATION:3,
    CT_TN_POLISH:    4,
    CT_TP_POLISH:    5,
    CT_BIOLOGICAL:   4,
    CT_MEMBRANE:     5,
    CT_MULTI:        3,
    CT_UNKNOWN:      9,
}

_SEV_WEIGHT = {"High": 0, "Medium": 1, "Low": 2}

_CAPEX = {
    TI_COMAG: "Medium", TI_BIOMAG: "Medium", TI_EQ_BASIN: "High",
    TI_STORM_STORE: "High", TI_INDENSE: "Low", TI_MIGINDENSE: "Medium",
    TI_MEMDENSE: "Low", TI_HYBAS: "Medium", TI_IFAS: "Low",
    TI_MBBR: "Medium", TI_MABR: "Medium", TI_BARDENPHO: "Low",
    TI_RECYCLE_OPT: "Low", TI_ZONE_RECONF: "Low",
    TI_DENFILTER: "High", TI_PDNA: "High", TI_TERT_P: "Medium",
}
_COMPLEXITY = {
    TI_COMAG: "Medium", TI_BIOMAG: "High", TI_EQ_BASIN: "Medium",
    TI_STORM_STORE: "Medium", TI_INDENSE: "Low", TI_MIGINDENSE: "Medium",
    TI_MEMDENSE: "Low", TI_HYBAS: "Medium", TI_IFAS: "Low",
    TI_MBBR: "Medium", TI_MABR: "Medium", TI_BARDENPHO: "Low",
    TI_RECYCLE_OPT: "Low", TI_ZONE_RECONF: "Medium",
    TI_DENFILTER: "High", TI_PDNA: "High", TI_TERT_P: "Medium",
}
_TECH_DISPLAY = {
    TI_COMAG:      "CoMag® (high-rate magnetic ballasted clarification)",
    TI_BIOMAG:     "BioMag® (ballasted MBBR-activated sludge hybrid)",
    TI_EQ_BASIN:   "Equalisation / flow balancing basin",
    TI_STORM_STORE:"Storm storage / attenuation infrastructure",
    TI_INDENSE:    "inDENSE® (gravimetric biomass selection)",
    TI_MIGINDENSE: "MOB (miGRATE™ + inDENSE®) — SBR intensification",
    TI_MEMDENSE:   "memDENSE® (MBR biomass selection)",
    TI_HYBAS:      "Hybas™ (IFAS / integrated biofilm)",
    TI_IFAS:       "IFAS (integrated fixed-film activated sludge)",
    TI_MBBR:       "MBBR / MBBR-Bardenpho",
    TI_MABR:       "MABR OxyFAS® (membrane-aerated biofilm reactor)",
    TI_BARDENPHO:  "Bardenpho / process zone optimisation",
    TI_RECYCLE_OPT:"Recycle ratio optimisation",
    TI_ZONE_RECONF:"Zone reconfiguration / EBPR optimisation",
    TI_DENFILTER:  "Denitrification filter (methanol-dosed tertiary denitrification)",
    TI_PDNA:       "PdNA — Partial Denitrification-Anammox (IFAS/MBBR/MABR retained)",
    TI_TERT_P:     "Tertiary phosphorus removal (chemical dosing + filtration)",
}


# ── Result dataclasses ─────────────────────────────────────────────────────────

@dataclass
class Constraint:
    """A classified active constraint derived from WaterPoint failure modes."""
    constraint_type: str
    label:          str
    severity:       str    # High / Medium / Low
    priority:       int
    source_modes:   List[str] = field(default_factory=list)  # failure mode titles that triggered this

    def __lt__(self, other: "Constraint") -> bool:
        if self.priority != other.priority:
            return self.priority < other.priority
        return _SEV_WEIGHT.get(self.severity, 1) < _SEV_WEIGHT.get(other.severity, 1)


@dataclass
class PathwayStage:
    """One stage in an upgrade pathway."""
    stage_number:  int
    technology:    str          # TI_* code
    tech_display:  str          # human-readable
    mechanism:     str          # MECH_* code
    mechanism_label: str
    purpose:       str          # what this stage does
    engineering_basis: str      # why this technology, quantified where possible
    addresses:     List[str]    # constraint types resolved
    prerequisite:  str  = ""
    capex_class:   str  = "Medium"
    complexity:    str  = "Medium"
    # ── Biological hierarchy traceability (v24Z38) ──────────────────────────
    bio_hierarchy_level:     int = 0   # 0=non-bio, 1=process opt, 2=biofilm, 3=aeration, 4=tertiary
    bio_hierarchy_rationale: str = ""  # why this level was selected


@dataclass
class AlternativePathway:
    """An alternative to the primary stack."""
    label:          str    # e.g. "Option A — Lower CAPEX"
    stages:         List[str]   # technology display names in order
    rationale:      str
    when_preferred: str
    capex_class:    str  = "Medium"


@dataclass
class GreenfieldConceptPath:
    """One concept design philosophy for a greenfield site."""
    label:           str          # "Conventional" or "Intensified"
    stack:           List[str]    # display names of representative technologies
    confidence:      int          # adjusted 0–100
    confidence_label: str         # High / Moderate / Low / Very Low
    footprint:       str          # High / Moderate / Low
    complexity:      str          # Low / Moderate / High
    credible:        bool         # False = shown but labelled non-credible
    non_credible_reason: str = "" # why it is non-credible if credible=False
    tradeoffs:       List[str] = field(default_factory=list)   # 2–3 trade-off bullets
    strategic_note:  str = ""     # one-sentence framing


@dataclass
class UpgradePathway:
    """
    Full consultant-grade upgrade pathway recommendation.

    Produced by build_upgrade_pathway() from a WaterPointResult.
    """
    # Inputs summary
    system_state:       str    # Stable / Tightening / Fragile / Failure Risk
    proximity_pct:      float
    plant_type:         str
    flow_scenario:      str

    # Classified constraints
    constraints:        List[Constraint]   # sorted by priority + severity
    primary_constraint: Constraint
    secondary_constraints: List[Constraint]

    # Recommended pathway
    stages:             List[PathwayStage]
    alternatives:       List[AlternativePathway]

    # Narrative
    pathway_narrative:  str    # "Why this stack works" — engineering linkage
    constraint_summary: str    # one paragraph constraint diagnosis
    residual_risks:     List[str]
    confidence:         str    # High / Medium / Low

    # Metadata
    multi_constraint:   bool = False
    guardrail_notes:    List[str] = field(default_factory=list)  # engineering rules applied
    system_state_type:  str = "Hydraulic / operating stress"  # Fix5: separate from compliance

    # Constraint priority override
    # compliance_primary_ct: the constraint that determines licence compliance
    # stabilisation_cts:     constraints that must be managed but do not alone achieve compliance
    compliance_primary_ct:  str = ""       # e.g. CT_NITRIFICATION
    stabilisation_cts:      List[str] = field(default_factory=list)  # e.g. [CT_HYDRAULIC]
    footprint_constraint: str = "abundant"  # abundant / constrained / severely_constrained
    footprint_bfgf_boost: int = 0            # boost to apply to BF/GF score
    greenfield_pathways: List["GreenfieldConceptPath"] = field(default_factory=list)


# ── Step 1: Classify constraints from WaterPoint failure modes ─────────────────

# Keyword mappings from failure mode titles → constraint type
_TITLE_MAP: List[Tuple[List[str], str, str]] = [
    # (keywords_any, constraint_type, severity_override_or_"use_mode")
    (["overflow", "bypass", "wet weather overflow", "active overflow"],
     CT_HYDRAULIC, "High"),
    (["hydraulic overload", "recycle", "ras_utilisation"],
     CT_HYDRAULIC, "use_mode"),
    (["cycle throughput saturation", "cycle compression", "cycle instability"],
     CT_SETTLING, "use_mode"),
    (["settling", "solids carryover", "clarifier", "svi", "washout", "carry-over",
      "indense required", "solids carry-over", "no upstream buffer"],
     CT_SETTLING, "use_mode"),
    (["nitrification", "ammonia", "nh4", "nh3", "srt compression",
      "biological optimisation not yet installed"],
     CT_NITRIFICATION, "use_mode"),
    (["total nitrogen", "tn ", "nox", "denitrification", "carbon-limited",
      "tightening cap", "tn/tp"],
     CT_TN_POLISH, "use_mode"),
    (["phosphorus", "tp ", " tp", "ebpr", "bio-p", "bio p", "p removal"],
     CT_TP_POLISH, "use_mode"),
    (["membrane", "fouling", "permeability", "cleaning frequency", "memdense"],
     CT_MEMBRANE, "use_mode"),
    (["biological", "biological performance", "do /", "aeration optimisation",
      "carbon dosing", "volatile"],
     CT_BIOLOGICAL, "use_mode"),
    (["peak-flow attenuation", "wet weather", "storm", "peak wet weather"],
     CT_WET_WEATHER, "use_mode"),
    (["selector underperformance", "carrier retention", "cycle compression without"],
     CT_SETTLING, "use_mode"),
]


def _classify_from_failure_modes(
    failure_modes,       # FailureModes dataclass
    wp_state: str,
    flow_scenario: str,
    plant_context: Dict,
) -> List[Constraint]:
    """
    Classify failure mode list into structured Constraint objects.
    Returns sorted list (priority ascending, severity ascending).
    """
    found: Dict[str, Constraint] = {}

    def _sev_int(s: str) -> int:
        return {"High": 3, "Medium": 2, "Low": 1}.get(s, 1)

    # ── Clarifier utilisation guard (Fix 1 + 2) ──────────────────────────────
    # context signals that confirm a real settling problem exists
    _ctx_settling_signals = (
        plant_context.get("high_mlss", False)
        or plant_context.get("svi_elevated", False)
        or plant_context.get("svi_unknown", False)
        or plant_context.get("solids_carryover", False)
        or (plant_context.get("clarifier_util", 0.0) or 0.0) >= 1.0
    )
    # is_sbr is always a real settling context
    _is_sbr = bool(plant_context.get("is_sbr", False))

    for mode in (failure_modes.items if failure_modes else []):
        title_lower = mode.title.lower()
        desc_lower  = (mode.description or "").lower()
        combined    = title_lower + " " + desc_lower

        for keywords, ct, sev_rule in _TITLE_MAP:
            if any(kw in combined for kw in keywords):
                sev = mode.severity if sev_rule == "use_mode" else sev_rule

                # ── Fix 2: Low-severity suppression ───────────────────────
                # Low-severity signals inform; they do NOT drive design.
                # Suppress CT_SETTLING entirely when severity is Low and no
                # context signal confirms a real settling problem.
                if ct == CT_SETTLING and sev == "Low" and not (_ctx_settling_signals or _is_sbr):
                    break  # skip — informational only, not a design constraint

                # ── Fix 1: Clarifier utilisation guard ────────────────────
                # "Clarifier overload" fires when SOR > advisory threshold,
                # which happens under PWWF even when clarifiers are healthy.
                # When no context signal confirms actual overload:
                #   - High severity → suppress entirely (not a real constraint)
                #   - Medium/Low severity → suppress (SOR advisory, not clinical)
                # This prevents SOR-based settling from outranking genuine
                # nitrification or TN constraints in the stack generator.
                if ct == CT_SETTLING and not (_ctx_settling_signals or _is_sbr):
                    break   # suppress — no confirmed overload from context signals

                if ct not in found:
                    found[ct] = Constraint(
                        constraint_type = ct,
                        label           = _CT_LABELS_V1.get(ct, ct),
                        severity        = sev,
                        priority        = _PRIORITY.get(ct, 9),
                        source_modes    = [mode.title],
                    )
                else:
                    existing = found[ct]
                    if _sev_int(sev) > _sev_int(existing.severity):
                        existing.severity = sev
                    if mode.title not in existing.source_modes:
                        existing.source_modes.append(mode.title)
                break  # first match wins per mode

    # Context-based supplemental flags
    if plant_context.get("is_mbr") and CT_MEMBRANE not in found:
        if plant_context.get("membrane_fouling") or plant_context.get("high_cleaning_frequency"):
            found[CT_MEMBRANE] = Constraint(CT_MEMBRANE,
                _CT_LABELS_V1[CT_MEMBRANE], "Medium", _PRIORITY[CT_MEMBRANE], ["Context flag"])

    if wp_state == "Failure Risk" and not found:
        found[CT_BIOLOGICAL] = Constraint(CT_BIOLOGICAL,
            _CT_LABELS_V1[CT_BIOLOGICAL], "High", _PRIORITY[CT_BIOLOGICAL], ["Failure Risk state"])

    # Flow scenario escalation
    if flow_scenario in ("Average Wet Weather Flow (AWWF)", "Peak Wet Weather Flow (PWWF)"):
        if CT_HYDRAULIC not in found and CT_WET_WEATHER not in found:
            if plant_context.get("flow_ratio", 1.0) >= 1.5:
                found[CT_WET_WEATHER] = Constraint(CT_WET_WEATHER,
                    _CT_LABELS_V1[CT_WET_WEATHER], "Medium", _PRIORITY[CT_WET_WEATHER], ["Flow scenario"])

    result = sorted(found.values())
    return result


# ── Engineering guardrails ─────────────────────────────────────────────────────

def _apply_guardrails(
    stages: List[PathwayStage],
    constraints: List[Constraint],
    notes: List[str],
) -> List[PathwayStage]:
    """
    Enforce engineering rules. Remove or flag stages that violate them.
    Returns cleaned stage list.
    """
    ct_set    = {c.constraint_type for c in constraints}
    tech_set  = {s.technology for s in stages}
    to_remove = set()

    # Rule 1: Do not recommend Denitrification Filter if nitrification not controlled
    if TI_DENFILTER in tech_set and CT_NITRIFICATION in ct_set:
        # Check if nitrification is resolved by an earlier stage
        nit_resolved = any(s.technology in (TI_IFAS, TI_HYBAS, TI_MBBR, TI_MABR, TI_MIGINDENSE)
                           for s in stages)
        if not nit_resolved:
            to_remove.add(TI_DENFILTER)
            notes.append(
                "Guardrail: Denitrification filter removed — nitrification must be controlled "
                "before tertiary denitrification is effective."
            )

    # Rule 2: Do not recommend IFAS if hydraulic limitation is unresolved
    if TI_IFAS in tech_set and CT_HYDRAULIC in ct_set:
        hyd_resolved = any(s.technology in (TI_COMAG, TI_EQ_BASIN, TI_STORM_STORE)
                           for s in stages
                           if s.stage_number < next(
                               (s2.stage_number for s2 in stages if s2.technology == TI_IFAS),
                               999))
        if not hyd_resolved:
            to_remove.add(TI_IFAS)
            notes.append(
                "Guardrail: IFAS removed — hydraulic limitation must be stabilised "
                "before biofilm installation is effective."
            )

    # Rule 3: Do not recommend CoMag if purely nitrification-limited
    if TI_COMAG in tech_set and ct_set == {CT_NITRIFICATION}:
        to_remove.add(TI_COMAG)
        notes.append(
            "Guardrail: CoMag removed — ballasted clarification is not appropriate "
            "for a purely nitrification-limited plant with no hydraulic or settling constraint."
        )

    # Rule 4: Do not recommend miGRATE before settling is stabilised
    if TI_MIGINDENSE in tech_set:
        mob_stage = next((s for s in stages if s.technology == TI_MIGINDENSE), None)
        settling_stage = next((s for s in stages if s.technology in (TI_INDENSE, TI_COMAG, TI_BIOMAG)
                               and s.stage_number < (mob_stage.stage_number if mob_stage else 999)), None)
        if not settling_stage and mob_stage:
            # If MOB is the only settling tech (SBR case), it is self-contained — keep it
            if CT_SETTLING in ct_set and mob_stage.stage_number == 1:
                pass  # MOB in Stage 1 is the settling remedy for SBR
            else:
                notes.append(
                    "Note: MOB (miGRATE + inDENSE) is self-contained — inDENSE provides "
                    "settling stabilisation before miGRATE contributes biological optimisation."
                )

    stages = [s for s in stages if s.technology not in to_remove]
    return stages


# ── Stage builders ─────────────────────────────────────────────────────────────

def _make_stage(
    num: int, tech: str, mechanism: str,
    purpose: str, basis: str,
    addresses: List[str], prereq: str = "",
    bio_level: int = 0, bio_rationale: str = "",
) -> PathwayStage:
    return PathwayStage(
        stage_number    = num,
        technology      = tech,
        tech_display    = _TECH_DISPLAY.get(tech, tech),
        mechanism       = mechanism,
        mechanism_label = _MECH_LABELS_V1.get(mechanism, mechanism),
        purpose         = purpose,
        engineering_basis = basis,
        addresses       = addresses,
        prerequisite    = prereq,
        capex_class     = _CAPEX.get(tech, "Medium"),
        complexity      = _COMPLEXITY.get(tech, "Medium"),
        bio_hierarchy_level     = bio_level,
        bio_hierarchy_rationale = bio_rationale,
    )


def _build_pathway_stages(
    constraints: List[Constraint],
    plant_context: Dict,
) -> List[PathwayStage]:
    """Build ordered stages from prioritised constraints."""
    is_sbr  = bool(plant_context.get("is_sbr", False))
    is_mbr  = bool(plant_context.get("is_mbr", False))
    overflow= bool(plant_context.get("overflow_risk", False))
    ww_peak = bool(plant_context.get("wet_weather_peak", False))
    aer_constrained = bool(plant_context.get("aeration_constrained", False))
    high_load= bool(plant_context.get("high_load", False))
    flow_ratio = plant_context.get("flow_ratio", 1.0) or 1.0

    ct_set  = {c.constraint_type for c in constraints}
    stages: List[PathwayStage] = []
    used:   set = set()
    stage_n = [1]

    def emit(tech: str, mech: str, purpose: str, basis: str,
             addresses: List[str], prereq: str = "",
             bio_level: int = 0, bio_rationale: str = "") -> None:
        if tech in used: return
        used.add(tech)
        stages.append(_make_stage(
            stage_n[0], tech, mech, purpose, basis, addresses, prereq,
            bio_level=bio_level, bio_rationale=bio_rationale))
        stage_n[0] += 1

    # ── Stage 1: Hydraulic stabilisation ──────────────────────────────────────
    _gf_mode_sg = bool(plant_context.get("greenfield", False))
    if (CT_HYDRAULIC in ct_set or CT_WET_WEATHER in ct_set) and not _gf_mode_sg:
        hyd = next((c for c in constraints if c.constraint_type in
                    (CT_HYDRAULIC, CT_WET_WEATHER)), None)
        # Classify hydraulic sub-type:
        # Peak-driven: storm events, PWWF spikes, overflow risk, flow_ratio ≥ 3
        # Steady-state: sustained clarifier SOR/SVI limitation, not storm-dominated
        _svi_high      = (plant_context.get("svi_ml_g") or 0.) > 120.
        _cl_util       = plant_context.get("clarifier_util", 0.) or 0.
        _cl_overloaded = _cl_util >= 1.0 or bool(plant_context.get("clarifier_overloaded", False))
        _steady_state  = (_cl_overloaded or _svi_high) and not overflow and not ww_peak
        _peak_driven   = overflow or ww_peak or flow_ratio >= 3.0
        # Hybrid: clarifier/SVI issue present AND confirmed high peak flow,
        # even if overflow_risk/ww_peak flags are not set
        _both          = (_cl_overloaded or _svi_high) and _peak_driven

        if _both:
            # Rule 4: hybrid — CoMag first (acute storm safety), then inDENSE (sustained settling)
            emit(TI_COMAG, MECH_BALLASTED,
                "CoMag provides peak storm protection as Stage 1 priority. "
                "InDENSE follows to address the steady-state settling deficit once storm "
                "protection is established.",
                "CoMag treats flows of 3–5× DWA without new secondary tanks. "
                "Commissioned first; inDENSE improves baseline settling in parallel once "
                "storm capacity is confirmed. Together they address both constraint types.",
                [CT_HYDRAULIC, CT_WET_WEATHER])
            emit(TI_INDENSE, MECH_BIOMASS_SEL,
                "inDENSE improves sludge settleability and increases clarifier throughput "
                "under steady-state conditions, but does not provide instantaneous "
                "protection against peak storm flows.",
                "inDENSE selectively wastes light and filamentous biomass via hydrocyclone, "
                "densifying the retained sludge and recovering SOR headroom. "
                "Effective where SVI > 120 mL/g or clarifier SOR is persistently exceeded "
                "under average flow. Commissioned after CoMag establishes storm protection.",
                [CT_HYDRAULIC, CT_SETTLING])

        elif _steady_state:
            # Rule 2: steady-state clarifier limitation, no dominant storm risk
            emit(TI_INDENSE, MECH_BIOMASS_SEL,
                "inDENSE improves sludge settleability and increases clarifier throughput "
                "under steady-state conditions, but does not provide instantaneous "
                "protection against peak storm flows.",
                "inDENSE selectively wastes light and filamentous biomass via hydrocyclone, "
                "densifying the retained sludge and recovering SOR headroom under sustained "
                "average or high-dry-weather flow. SVI reduction of 20–40% is typical. "
                "Where MABR is also selected, inDENSE complements the increased biomass "
                "concentration by improving retention of the denser carrier-associated fraction.",
                [CT_HYDRAULIC, CT_SETTLING])

        elif _peak_driven:
            # Rule 3: peak-driven — CoMag or EQ basin
            if flow_ratio >= 3.0 and not overflow and not ww_peak:
                emit(TI_EQ_BASIN, MECH_HYD_EXP,
                    "Equalisation basin attenuates sustained peak inflows before secondary "
                    "treatment, protecting biological process stability.",
                    "Target attenuation to ≤ 2× DWA at secondary inlet. EQ basin capacity "
                    "sized to peak event duration and return rate.",
                    [CT_HYDRAULIC, CT_WET_WEATHER])
            else:
                emit(TI_COMAG, MECH_BALLASTED,
                    "High-rate magnetic ballasted clarification provides rapid solids removal "
                    "under peak wet weather flows, protecting the downstream biological process "
                    "from hydraulic and solids shock.",
                    "CoMag treats flows of 3–5× DWA without new secondary tanks. Magnetic "
                    "microspheres ballast the floc, enabling surface overflow rates of "
                    "10–20 m/h vs 1–2 m/h for conventional secondary settling. "
                    "Ballast is recovered and recycled magnetically.",
                    [CT_HYDRAULIC, CT_WET_WEATHER])

        else:
            # Default: hydraulic constraint flagged, no clear sub-type — use severity
            use_comag = (hyd and hyd.severity == "High") or flow_ratio >= 2.0
            if use_comag:
                emit(TI_COMAG, MECH_BALLASTED,
                    "High-rate magnetic ballasted clarification provides rapid solids removal "
                    "under peak wet weather flows, protecting the downstream biological process "
                    "from hydraulic and solids shock.",
                    "CoMag treats flows of 3–5× DWA without new secondary tanks. Magnetic "
                    "microspheres ballast the floc, enabling surface overflow rates of "
                    "10–20 m/h vs 1–2 m/h for conventional secondary settling. "
                    "Ballast is recovered and recycled magnetically.",
                    [CT_HYDRAULIC, CT_WET_WEATHER])
            else:
                emit(TI_EQ_BASIN, MECH_HYD_EXP,
                    "Equalisation basin smooths diurnal and wet weather flow peaks, "
                    "reducing hydraulic stress on clarifiers and biological zones.",
                    "Target ≤ 2× DWA at secondary inlet. EQ basin is the primary "
                    "hydraulic mitigation before any biological upgrade is considered.",
                    [CT_HYDRAULIC, CT_WET_WEATHER])

    # ── Stage 2: Settling stabilisation ───────────────────────────────────────
    if CT_SETTLING in ct_set:
        set_con = next((c for c in constraints if c.constraint_type == CT_SETTLING), None)
        severe  = set_con and set_con.severity == "High"
        if is_sbr:
            emit(TI_MIGINDENSE, MECH_BIOMASS_SEL,
                "MOB (inDENSE + miGRATE) stabilises settling in the existing SBR and unlocks "
                "cycle capacity without new reactor volume. inDENSE is the settling prerequisite; "
                "miGRATE is the biological optimisation layer that follows.",
                "inDENSE gravimetric selection reduces SVI and enables cycle compression to 3h. "
                "miGRATE biofilm carriers then reduce TN and aerobic mass fraction. "
                "Upgrade sequence: inDENSE commissioned and stable \u2192 then activate miGRATE. "
                "miGRATE alone does not consistently improve SVI (Lang Lang + Army Bay). "
                "MOB does not solve hydraulic overload; stable operation is required throughout. "
                "MOB is differentiated from IFAS (SRT only) and MABR (oxygen transfer) by its "
                "combined settling + SRT + SND mechanism.",
                [CT_SETTLING, CT_NITRIFICATION],
                prereq="SBR operational, feed characteristics stable",
                bio_level=2,
                bio_rationale=(
                    "MOB is selected at Level 2 (biomass retention) because both settling "
                    "instability and SRT limitation are present in the SBR. "
                    "This differentiates MOB from IFAS (SRT only) and MABR (oxygen transfer). "
                    "MOB addresses the combined settling + biological constraint in a single staged deployment."
                ))
        elif is_mbr:
            emit(TI_MEMDENSE, MECH_MEMBRANE_SEL,
                "memDENSE selective wasting removes filamentous and low-density biomass "
                "from MBR mixed liquor, directly reducing clarifier/membrane loading.",
                "memDENSE improves settling velocity of the retained fraction, reduces SVI, "
                "and lowers membrane fouling rate. PAO retention is enhanced, "
                "improving biological P removal.",
                [CT_SETTLING, CT_MEMBRANE])
        elif severe or high_load:
            # BioMag requires confirmed hydraulic overload (clarifier_util >= 1.0) AND high load.
            # Without actual clarifier overload, inDENSE addresses settling more precisely.
            # This prevents BioMag from firing when SVI is elevated but clarifier is not overloaded.
            _cl_util     = plant_context.get("clarifier_util", 0.0) or 0.0
            _use_biomag  = high_load and (_cl_util >= 1.0 or
                           plant_context.get("overflow_risk", False) or
                           plant_context.get("wet_weather_peak", False))
            if _use_biomag:
                emit(TI_BIOMAG, MECH_BALLASTED,
                    "BioMag combines ballasted settling with integrated biological treatment, "
                    "improving both hydraulic throughput and solids management under elevated load.",
                    "Magnetic microspheres improve mixed liquor density and settling velocity. "
                    "At high MLSS and elevated loading, BioMag provides more robust settling "
                    "improvement than inDENSE alone. Suitable when clarifier SOR is critically exceeded.",
                    [CT_SETTLING],
                    prereq="Ballast recovery and recycling infrastructure available")
            else:
                # Settling present but clarifier not in confirmed overload — inDENSE is appropriate.
                # The nitrification stage will follow with IFAS/Hybas to address the SRT constraint.
                emit(TI_INDENSE, MECH_BIOMASS_SEL,
                    "inDENSE gravimetric selection removes light and filamentous biomass, "
                    "improving settling velocity and SVI without adding tank volume.",
                    "inDENSE selectively wastes the low-density fraction of mixed liquor. "
                    "The retained sludge is denser, settles faster, and occupies less clarifier volume. "
                    "SOR headroom recovers without clarifier expansion. "
                    "Where SRT is simultaneously limiting, a biofilm retention stage (IFAS/Hybas) "
                    "follows as Stage 2 to address nitrification capacity.",
                    [CT_SETTLING])
        else:
            emit(TI_INDENSE, MECH_BIOMASS_SEL,
                "inDENSE gravimetric selection removes light and filamentous biomass, "
                "improving settling velocity and SVI without adding tank volume.",
                "inDENSE selectively wastes the low-density fraction of mixed liquor. "
                "The retained sludge is denser, settles faster, and occupies less clarifier volume. "
                "SOR headroom recovers without clarifier expansion.",
                [CT_SETTLING])

    # ── Stage 3: Nitrification unlock — biological hierarchy Levels 2 and 3 ──────
    # Level 2 (biomass retention): use when SRT is the bottleneck and aeration has headroom
    # Level 3 (aeration intensification): use only when blower is the binding constraint
    if CT_NITRIFICATION in ct_set and TI_MIGINDENSE not in used:
        settling_present = any(s.technology in (TI_INDENSE, TI_BIOMAG, TI_COMAG, TI_MEMDENSE)
                               for s in stages)
        if aer_constrained:
            # Level 3: Aeration is the binding constraint — MABR bypasses blower limitation
            emit(TI_MABR, MECH_AER_INT,
                "MABR (OxyFAS) delivers oxygen directly to the biofilm via gas-permeable "
                "hollow-fibre membranes, providing nitrification capacity without blower expansion.",
                "OxyFAS drops into existing AS tanks. Oxygen transfer efficiency up to 14 kgO₂/kWh "
                "vs 1–2 kgO₂/kWh for conventional diffused aeration. "
                "NHx resilience is maintained even when blower capacity is near maximum. "
                "Calibrated to Kawana modelling: NHx <0.1 mg/L across all load scenarios.",
                [CT_NITRIFICATION],
                prereq="Stage 2 settling stabilisation complete" if settling_present else "",
                bio_level=3,
                bio_rationale=(
                    "MABR is selected at Level 3 (aeration intensification) because the aeration "
                    "system is near maximum capacity. IFAS or Hybas would not resolve the oxygen "
                    "delivery limitation — blower headroom is the binding constraint, not SRT alone."
                ))
        elif settling_present:
            # Level 2: SRT is the bottleneck; settling is already addressed; Hybas unlocks nitrification
            emit(TI_HYBAS, MECH_BIOFILM_RET,
                "Hybas biofilm carriers decouple nitrification SRT from hydraulic SRT. "
                "Nitrifiers accumulate on carriers independent of the WAS rate, providing "
                "stable ammonia oxidation capacity in the existing tank volume.",
                "Hybas increases effective sludge age for nitrification without increasing "
                "reactor volume. Suspended MLSS decreases (less clarifier loading). "
                "Carriers are retained by screens at zone outlets.",
                [CT_NITRIFICATION],
                prereq="Stage 2 settling stabilisation complete",
                bio_level=2,
                bio_rationale=(
                    "Hybas is selected at Level 2 (biomass retention) because settling is already "
                    "addressed and SRT is the controlling nitrification constraint. Biofilm "
                    "retention provides the additional effective sludge age without blower expansion."
                ))
        else:
            # Level 2: SRT is the bottleneck; aeration has headroom; IFAS is the most direct match
            emit(TI_IFAS, MECH_BIOFILM_RET,
                "IFAS carriers retain nitrifying biofilm in the existing aeration zone, "
                "decoupling nitrification SRT from the hydraulic SRT of the tank.",
                "No new tank volume required. Media retention screens installed at zone outlets. "
                "Effective nitrification SRT can exceed 15 days even at short hydraulic SRT. "
                "MLSS may decrease as biofilm carries more of the nitrification load.",
                [CT_NITRIFICATION],
                bio_level=2,
                bio_rationale=(
                    "IFAS is selected at Level 2 (biomass retention) because the nitrification "
                    "constraint is driven by insufficient SRT / effective sludge age, not by oxygen "
                    "delivery limitation. Aeration headroom exists; MABR is not required."
                ))

    # ── Stage 4: TN polishing — biological hierarchy Level 1 ─────────────────
    # Level 1: Suspended growth / process optimisation is ALWAYS the first response
    # to TN exceedance. Biofilm or tertiary (Levels 2–4) only follow when Level 1
    # is explicitly exhausted or inapplicable.
    if CT_TN_POLISH in ct_set or (CT_BIOLOGICAL in ct_set and CT_NITRIFICATION not in ct_set):
        biofilm_present = any(s.technology in (TI_IFAS, TI_HYBAS, TI_MBBR, TI_MABR, TI_MIGINDENSE)
                              for s in stages)
        if biofilm_present:
            # Level 1 after biofilm: Bardenpho zone optimisation uses the elevated nitrate
            # substrate produced by biofilm nitrification — still process optimisation
            emit(TI_BARDENPHO, MECH_PROC_OPT,
                "Bardenpho zone optimisation maximises denitrification using the elevated "
                "nitrate load produced by biofilm nitrification.",
                "Second anoxic zone (Bardenpho 5-stage) significantly reduces effluent TN. "
                "Optimal internal recycle R ≈ 2; anaerobic HRT 2–2.5h for EBPR. "
                "Carbon availability for denitrification should be assessed — "
                "external carbon may be needed if COD/N < 4.",
                [CT_TN_POLISH, CT_BIOLOGICAL],
                prereq="Stage 3 biofilm commissioned and stable",
                bio_level=1,
                bio_rationale=(
                    "Biological optimisation is the first-line TN response. Bardenpho zone "
                    "optimisation is selected because nitrification is already active via biofilm "
                    "and TN exceedance is driven by denitrification limitation in the existing "
                    "process configuration."
                ))
        else:
            # Level 1: NH4 compliant / TN-only — suspended growth optimisation first
            emit(TI_RECYCLE_OPT, MECH_PROC_OPT,
                "Internal recycle ratio optimisation improves denitrification efficiency "
                "without capital expenditure.",
                "MLR ratio R ≈ 2 recovers ~67% of nitrate; R=4 recovers ~80%. "
                "Diminishing returns above R=4 due to dissolved oxygen carry-over. "
                "RAS optimisation protects clarifier SOR.",
                [CT_TN_POLISH, CT_BIOLOGICAL],
                bio_level=1,
                bio_rationale=(
                    "Biological optimisation is the first-line TN response because nitrification "
                    "is already stable and TN exceedance is driven by denitrification limitation. "
                    "Recycle optimisation is the lowest-cost and fastest intervention."
                ))
            # Add Bardenpho if zone reconfiguration is feasible
            emit(TI_BARDENPHO, MECH_PROC_OPT,
                "Bardenpho zone reconfiguration extracts more TN removal from existing "
                "tank volume by establishing a second anoxic zone.",
                "5-stage Bardenpho: anaerobic → anoxic → aerobic → post-anoxic → reaeration. "
                "Anaerobic zone HRT 2–2.5h optimal for PAO selection. "
                "External carbon dosing to the post-anoxic zone if carbon-limited.",
                [CT_TN_POLISH, CT_BIOLOGICAL],
                prereq="Recycle optimisation complete",
                bio_level=1,
                bio_rationale=(
                    "Bardenpho zone reconfiguration is Level 1 process optimisation — it uses "
                    "existing tank volume and carbon to improve denitrification without biofilm "
                    "or tertiary intervention."
                ))

    # ── Stage 4b: Conditional DNF — LOT / TN <3 mg/L tertiary polishing ─────────
    # Fix 3 (v24Z39): DNF surfaces in primary stack only when ALL conditions are met:
    #   (a) TN target <= 3.0 mg/L
    #   (b) NH4 is stable (not nh4_near_limit)
    #   (c) Level 1 biological optimisation is already in the stack
    #   (d) Nitrification is not actively broken (CT_NITRIFICATION absent or resolved by biofilm)
    #   (e) DNF not already emitted
    # This prevents DNF appearing before Level 1 and prevents it appearing when NH4 is unstable.

    # ── PdNA: Partial Denitrification-Anammox ─────────────────────────────────
    # Trigger conditions:
    #   (a) TN target <= 5.0 mg/L  (strict TN compliance)
    #   (b) Carbon-limited (cod_tn_ratio < 5 or carbon_limited_tn flag)
    #   (c) Biomass retention available (IFAS, MBBR, or MABR in stack or context)
    #   (d) NH4 not near limit (nitrification must be stable)
    #   (e) Not already emitting DNF (PdNA and DNF are mutually exclusive pathways)
    #   (f) Not SBR (SBR batch cycle is incompatible with mainstream PdNA)
    _pdna_tn_tgt    = plant_context.get("tn_target_mg_l", 10.) or 10.
    _pdna_carbon_lim = (
        bool(plant_context.get("carbon_limited_tn", False)) or
        (plant_context.get("cod_tn_ratio") is not None and
         float(plant_context.get("cod_tn_ratio", 10.)) < 5.)
    )
    _pdna_biofilm = (
        bool(plant_context.get("has_ifas", False)) or
        bool(plant_context.get("has_mabr", False)) or
        any(s.technology in (TI_IFAS, TI_HYBAS, TI_MBBR, TI_MABR) for s in stages)
    )
    _pdna_nh4_ok   = not bool(plant_context.get("nh4_near_limit", False))
    _pdna_not_sbr  = not bool(plant_context.get("is_sbr", False))
    _pdna_not_dnf  = TI_DENFILTER not in used and TI_PDNA not in used
    _pdna_conditions = (
        _pdna_tn_tgt <= 5.0
        and _pdna_carbon_lim
        and _pdna_biofilm
        and _pdna_nh4_ok
        and _pdna_not_sbr
        and _pdna_not_dnf
    )
    if _pdna_conditions:
        emit(TI_PDNA, MECH_TERT_DN,
            "PdNA uses controlled partial denitrification to produce NO\u2082 as a "
            "substrate for Anammox, which then removes NH\u2084 and NO\u2082 together "
            "without requiring full carbon dosing for denitrification. Aeration savings of "
            "50\u201360% and carbon savings of up to 80% vs conventional denitrification.",
            "Requires biomass retention (IFAS, MBBR, or MABR) for Anammox protection. "
            "COD:NO\u2083 target: 2.4\u20133.0 gCOD/gNO\u2083-N for partial denitrification. "
            "Operating temperature must be above 10\u00b0C for Anammox activity. "
            "NO\u2082 operating window: 0.5\u20135 mg/L (above 5 mg/L risks FNA inhibition). "
            "Must not be commissioned before nitrification is stable (NH\u2084 < 1 mg/L).",
            [CT_TN_POLISH, CT_BIOLOGICAL],
            prereq="Biomass retention technology (IFAS/MBBR/MABR) commissioned and stable. "
                   "NH\u2084 stably controlled. COD:NO\u2083 dosing system in place.",
            bio_level=4,
            bio_rationale=(
                "PdNA is an advanced Level 4 nitrogen removal pathway. It delivers higher "
                "efficiency than conventional DNF where carbon is limiting, but requires "
                "Anammox biomass retention and precise stoichiometric dosing control. "
                "Biomass protection via fixed-film retention is non-negotiable."
            ))

    _tn_tgt    = plant_context.get("tn_target_mg_l", 10.) or 10.
    _nh4_stable= not bool(plant_context.get("nh4_near_limit", False))
    _l1_in     = any(s.technology in (TI_RECYCLE_OPT, TI_BARDENPHO) for s in stages)
    _nit_unresolved = (CT_NITRIFICATION in ct_set and
                       not any(s.technology in (TI_IFAS, TI_HYBAS, TI_MBBR, TI_MABR, TI_MIGINDENSE)
                               for s in stages))
    _dnf_conditions = (
        _tn_tgt <= 3.0
        and _nh4_stable
        and _l1_in
        and not _nit_unresolved
        and TI_DENFILTER not in used
        and TI_PDNA not in used
    )
    if _dnf_conditions:
        emit(TI_DENFILTER, MECH_TERT_DN,
            "Denitrification filter provides tertiary TN polishing where biological "
            "optimisation alone cannot reliably achieve TN < 3 mg/L.",
            "Methanol-dosed tertiary denitrification: ~2.5–3.0 mg MeOH per mg NO₃-N removed. "
            "DO at filter inlet must be < 0.5 mg/L. "
            "Filter is positioned after Bardenpho optimisation (Level 1) — it polishes the "
            "residual TN gap that biological denitrification cannot close reliably. "
            "DNF must NOT be commissioned before upstream NH₄ is stably controlled.",
            [CT_TN_POLISH, CT_BIOLOGICAL],
            prereq="Level 1 biological optimisation (Bardenpho / recycle) complete and "
                   "NH₄ stably controlled",
            bio_level=4,
            bio_rationale=(
                "DNF is Level 4 (tertiary denitrification) — the final escalation step. "
                "It is surfaced here because TN target ≤ 3 mg/L cannot be reliably achieved by "
                "biological optimisation alone, NH₄ is stable, and Level 1 is already in the "
                "stack. DO not commission before upstream nitrification is confirmed stable."
            ))


    # ── Stage 5: TP polishing ──────────────────────────────────────────────────
    if CT_TP_POLISH in ct_set:
        emit(TI_TERT_P, MECH_TERT_P,
            "Tertiary phosphorus removal via chemical dosing (ferric/alum) and "
            "downstream filtration achieves tight TP targets (<0.5 mg/L).",
            "Chemical P precipitation requires 20–25 g FeCl₃ per g P removed. "
            "Filter polishing achieves TSS <5 mg/L and TP <0.2 mg/L where required. "
            "Alternatively, CoMag can provide combined hydraulic relief and P polishing "
            "if both constraints are active.",
            [CT_TP_POLISH])

    # ── Stage 5b: Membrane polishing (if membrane and not already addressed) ──
    if CT_MEMBRANE in ct_set and TI_MEMDENSE not in used:
        emit(TI_MEMDENSE, MECH_MEMBRANE_SEL,
            "memDENSE selective wasting removes filamentous and low-density organisms "
            "from MBR mixed liquor, improving membrane permeability and reducing fouling.",
            "memDENSE removes the fraction responsible for membrane fouling and cake formation. "
            "Permeability typically improves within 4–8 weeks of commissioning. "
            "PAO retention is enhanced, supporting biological P removal recovery.",
            [CT_MEMBRANE])

    return stages


# ── Alternative pathways ───────────────────────────────────────────────────────

def _build_pathway_alternatives(
    constraints: List[Constraint],
    stages: List[PathwayStage],
    plant_context: Dict,
) -> List[AlternativePathway]:
    alts: List[AlternativePathway] = []
    ct_set = {c.constraint_type for c in constraints}
    tech_codes = [s.technology for s in stages]

    # Option A — Lower CAPEX
    if len(stages) >= 2:
        low_capex_stages = [
            _TECH_DISPLAY.get(s.technology, s.technology)
            for s in stages if _CAPEX.get(s.technology, "High") in ("Low", "Medium")
        ]
        if not low_capex_stages:
            low_capex_stages = [_TECH_DISPLAY.get(stages[0].technology, stages[0].technology)]
        alts.append(AlternativePathway(
            label="Option A — Lower CAPEX (staged intensification only)",
            stages=low_capex_stages[:3],
            rationale=(
                "Defer high-CAPEX civil infrastructure (EQ basin, tertiary filters) "
                "and focus on process intensification technologies that can be installed "
                "within existing tank volume. Accept a narrower operating margin in the "
                "short term while monitoring performance before committing to civil works."
            ),
            when_preferred=(
                "When immediate capital is constrained and the plant is Tightening rather "
                "than Fragile or Failure Risk. Suitable as a 2–5 year interim strategy."
            ),
            capex_class="Low",
        ))

    # Option B — Higher performance / future-proof
    high_perf: List[str] = []
    nh4_stable   = not plant_context.get("nh4_near_limit", False)
    tn_target_val= plant_context.get("tn_target_mg_l", 10.) or 10.
    lot_case     = tn_target_val <= 3.0 and nh4_stable  # licence-of-the-future DNF case

    if CT_NITRIFICATION in ct_set and TI_MABR not in tech_codes:
        high_perf.append(_TECH_DISPLAY[TI_MABR])
    if CT_TN_POLISH in ct_set or CT_BIOLOGICAL in ct_set:
        high_perf.append(_TECH_DISPLAY[TI_DENFILTER])
    if not high_perf:
        high_perf = [_TECH_DISPLAY.get(s.technology, s.technology) for s in stages]

    if lot_case:
        # LOT pathway: Bardenpho first, DNF only after biological optimisation is exhausted
        # Guardrail: DNF must not appear until NH4 is stably controlled
        lot_stages = [_TECH_DISPLAY[TI_BARDENPHO], _TECH_DISPLAY[TI_DENFILTER]]
        if TI_MABR not in tech_codes and CT_NITRIFICATION in ct_set:
            lot_stages = [_TECH_DISPLAY[TI_MABR]] + lot_stages
        alts.append(AlternativePathway(
            label="Option B — Licence-of-the-future pathway (TN < 3 mg/L)",
            stages=lot_stages[:4],
            rationale=(
                "Level 1 (Bardenpho optimisation) is the prerequisite before Level 4 (DNF). "
                "A denitrification filter achieves TN < 3 mg/L reliably but must only be "
                "commissioned after nitrification is stably controlled (NH4 < 1 mg/L) and "
                "biological optimisation is exhausted. "
                "Methanol dose: ~2.5–3.0 mg/mg NO3-N removed. DO at filter inlet must be < 0.5 mg/L. "
                "This is Level 4 in the biological escalation hierarchy — not a substitute for "
                "incomplete biological treatment."
            ),
            when_preferred=(
                "When TN target < 3 mg/L is required and biological optimisation cannot close "
                "the residual gap. Always implement Level 1 (Bardenpho) before commissioning DNF."
            ),
            capex_class="High",
        ))
    else:
        alts.append(AlternativePathway(
            label="Option B — Higher performance (licence-of-the-future compliant)",
            stages=high_perf[:4],
            rationale=(
                "Select technologies that provide headroom beyond the current licence limits. "
                "MABR and denitrification filtration achieve NH4 <0.5 mg/L and TN <3 mg/L, "
                "positioning the plant for future tightening without further civil works."
            ),
            when_preferred=(
                "When the utility anticipates licence tightening within 10 years, footprint "
                "is constrained, or energy minimisation is a strategic priority."
            ),
            capex_class="High",
        ))

    # ── Option C — Nereda (AGS) replacement pathway (Section 5) ───────────────
    # Nereda NEVER appears in primary stack — it is a full process replacement.
    # Surface as an alternative when greenfield / footprint-constrained / multi-constraint.
    # Weak fit: brownfield staged, high variability, low operator capability.
    _footprint_const = bool(plant_context.get("footprint_constrained", False))
    _greenfield      = bool(plant_context.get("greenfield", False))
    _n_constraints   = len(constraints)
    _multi_severe    = sum(1 for c in constraints if c.severity == "High") >= 3
    _nereda_trigger  = _footprint_const or _greenfield or _multi_severe

    if _nereda_trigger:
        _nereda_weak = []
        _is_brownfield_staged = (
            not _greenfield
            and not _footprint_const
            and len(stages) >= 2   # staged upgrade already in primary
        )
        if _is_brownfield_staged:
            _nereda_weak.append("brownfield staged upgrade is already the primary recommendation")
        if plant_context.get("location_type","") == "remote":
            _nereda_weak.append("remote location limits OEM support")
        if plant_context.get("high_diurnal", False):
            _nereda_weak.append("high influent variability increases granule stability risk")

        _nereda_rationale = (
            "Nereda® Aerobic Granular Sludge (AGS) delivers BNR in a compact footprint "
            "(30–50% smaller than conventional activated sludge) with integrated "
            "nitrification, denitrification, and biological P removal in a single vessel. "
            "It eliminates secondary clarifiers and achieves TN < 10 mg/L and TP < 1 mg/L routinely. "
            "Nereda is a full process replacement, not a retrofit addition — it requires "
            "decommissioning of the existing biological process. "
            "Startup complexity, granule stability risk, and proprietary technology dependency "
            "must be assessed before commitment. "
            + (f"Potential weaknesses for this plant: {'; '.join(_nereda_weak)}. " if _nereda_weak else "")
            + "Decision tension: staged brownfield intensification vs full process replacement. "
            "The recommended primary stack delivers compliance within existing assets; "
            "Nereda is the long-term strategic alternative if civil expansion is required."
        )
        _nereda_when = (
            "When the plant requires a major rebuild or is being replaced at end-of-life, "
            "footprint is severely constrained and civil expansion is not viable, "
            "or the utility is prepared to accept the disruption and CAPEX of full process conversion."
            + (" Strong fit here: footprint constraint identified." if _footprint_const else "")
            + (" Strong fit here: greenfield site." if _greenfield else "")
        )
        alts.append(AlternativePathway(
            label="Option C — Nereda® AGS (full process replacement)",
            stages=["Nereda® Aerobic Granular Sludge reactor (replaces secondary treatment)",
                    "Tertiary P removal if TP < 0.5 mg/L required"],
            rationale=_nereda_rationale,
            when_preferred=_nereda_when,
            capex_class="High",
        ))

    # ── memDENSE optional enhancement for new MBR designs (v24Z42) ────────────
    # Rule 2: surface memDENSE as optional enhanced configuration when is_mbr=True.
    # NOT as default — only as an explicitly labelled optional alternative.
    # Not triggered for existing MBR with fouling (memDENSE already in primary stack).
    _is_mbr        = bool(plant_context.get("is_mbr", False))
    _mbr_fouling   = bool(plant_context.get("membrane_fouling", False))
    _memdense_in_primary = TI_MEMDENSE in tech_codes

    if _is_mbr and not _mbr_fouling and not _memdense_in_primary:
        alts.append(AlternativePathway(
            label="Option — memDENSE Enhanced MBR Configuration (optional)",
            stages=[
                "Standard MBR bioreactor (as primary recommendation)",
                "memDENSE® hydrocyclone selective wasting (optional enhancement)",
            ],
            rationale=(
                "memDENSE is an optional enhancement to a standard MBR configuration, not a "
                "default inclusion. It improves biomass quality through hydrocyclone-based "
                "selective wasting of low-density organisms, targeting the biomass fraction "
                "that drives membrane fouling. "
                "Benefits: improved permeability (CIP interval may increase 20–40%), "
                "reduced fouling rate, potential aeration demand reduction, and improved "
                "TOTEX through extended membrane lifecycle. "
                "Risks: introduces additional technology dependency; supplier-specific "
                "implementation may limit procurement flexibility; higher technical complexity "
                "than standard MBR; application track record is more limited than conventional MBR. "
                "Commission hydrocyclone split ratio calibration to site-specific MLSS characteristics. "
                "Decision tension: standard MBR configuration vs enhanced MBR with memDENSE, "
                "trading increased complexity and supplier dependency against potential "
                "improvements in membrane performance and lifecycle cost (TOTEX)."
            ),
            when_preferred=(
                "When membrane fouling is anticipated to be a lifecycle cost driver, "
                "the utility has the operational capability to manage hydrocyclone "
                "equipment, and a specialist supplier relationship can be established. "
                "Evaluate against TOTEX model before committing. "
                "Do not select memDENSE as default — a compliant standard MBR "
                "installation does not require it."
            ),
            capex_class="Medium",
        ))

    return alts


# ── Narrative generators ───────────────────────────────────────────────────────

def _compliance_primary_constraint(
    constraints: List[Constraint],
    stages: List[PathwayStage],
    plant_context: Dict,
) -> tuple:
    """
    Identify which constraint is compliance-limiting vs which is stabilisation-only.

    Returns
    -------
    (compliance_primary_ct, stabilisation_cts)
        compliance_primary_ct : str   — constraint type that determines licence compliance
        stabilisation_cts     : list  — constraint types that are risk-mitigation only

    Engineering logic
    -----------------
    A constraint is compliance-primary if resolving it is necessary AND sufficient
    to achieve the licence target for the parameter it governs.

    A constraint is stabilisation-only if:
    - Resolving it alone does NOT achieve compliance (other constraints remain)
    - OR it is a risk-management measure protecting process stability rather than
      directly determining effluent quality (e.g. hydraulic protection)

    Key rule: when hydraulic and biological constraints coexist,
    the biological constraint is compliance-primary because:
    - CoMag alone does not fix NH4, TN, or TP
    - MABR alone does fix NH4 (the compliance parameter)
    - Hydraulic stabilisation is a prerequisite for MABR, but it is
      not itself the source of the compliance gap

    Exception: if the ONLY compliance failure is solids carryover during
    peak flows (TSS), then hydraulic is the compliance-primary constraint.
    """
    ct_set   = {c.constraint_type for c in constraints}
    tech_set = {s.technology for s in stages}

    has_hydraulic    = CT_HYDRAULIC in ct_set or CT_WET_WEATHER in ct_set
    has_nitrification= CT_NITRIFICATION in ct_set
    has_tn           = CT_TN_POLISH in ct_set
    has_tp           = CT_TP_POLISH in ct_set
    has_settling     = CT_SETTLING in ct_set
    has_biological   = CT_BIOLOGICAL in ct_set

    # Biological compliance constraints — these determine effluent quality directly
    biological_cts = [ct for ct in [CT_NITRIFICATION, CT_TN_POLISH,
                                     CT_TP_POLISH, CT_BIOLOGICAL]
                      if ct in ct_set]

    # If biological constraints exist, they are compliance-primary
    # Hydraulic is stabilisation (protects the process, does not fix effluent quality)
    if biological_cts and has_hydraulic:
        compliance_primary = biological_cts[0]   # highest-priority biological ct
        stabilisation      = [ct for ct in ct_set
                              if ct in (CT_HYDRAULIC, CT_WET_WEATHER)]
        return compliance_primary, stabilisation

    # If settling + biological coexist, settling is stabilisation, biological is primary
    if biological_cts and has_settling:
        compliance_primary = biological_cts[0]
        stabilisation      = [CT_SETTLING] if CT_SETTLING in ct_set else []
        return compliance_primary, stabilisation

    # Pure hydraulic (no biological compliance gap) — hydraulic IS compliance-primary
    # (only if the compliance failure is TSS/solids carryover during peak flows)
    if has_hydraulic and not biological_cts:
        return CT_HYDRAULIC, []

    # Pure settling — settling is compliance-primary
    if has_settling and not biological_cts:
        return CT_SETTLING, []

    # Default: the first (highest-priority) constraint is compliance-primary
    if constraints:
        return constraints[0].constraint_type, []
    return CT_UNKNOWN, []


def _pathway_narrative(
    constraints: List[Constraint],
    stages: List[PathwayStage],
    compliance_primary_ct: str = "",
    stabilisation_cts: List[str] = None,
) -> str:
    if not stages:
        return "Insufficient constraint data to generate upgrade pathway."
    stabilisation_cts = stabilisation_cts or []
    ct_label_map = _CT_LABELS_V1
    cp_label = ct_label_map.get(compliance_primary_ct, "")

    # Identify which stages are stabilisation vs compliance-primary
    stab_tech_set = set()
    if stabilisation_cts:
        for st in stages:
            if any(addr in stabilisation_cts for addr in st.addresses):
                stab_tech_set.add(st.technology)

    if compliance_primary_ct and stabilisation_cts and stab_tech_set:
        lines = [
            f"This upgrade pathway applies a constraint priority override. "
            f"The compliance-primary constraint is {cp_label}: resolving this is necessary "
            f"to achieve effluent licence compliance. "
            f"Stabilisation infrastructure is deployed first to protect process integrity "
            f"during the biological upgrade, but it is not the primary engineering response. "
        ]
    else:
        lines = [
            "This upgrade pathway is sequenced to address the highest-priority constraint first, "
            "with each stage unlocking the next. "
        ]

    for st in stages:
        role = ""
        if stabilisation_cts and any(addr in stabilisation_cts for addr in st.addresses):
            role = " [System Stabilisation]"
        elif compliance_primary_ct and compliance_primary_ct in st.addresses:
            role = " [Primary Constraint Resolution]"
        lines.append(
            f"Stage {st.stage_number} ({st.tech_display.split('(')[0].strip()}){role} "
            f"addresses {', '.join(c.replace('_limitation','').replace('_',' ') for c in st.addresses)} "
            f"via {st.mechanism_label.lower()}."
        )
    lines.append(
        "Technologies are selected to avoid functional overlap, "
        "exhaust intensification options before civil expansion, "
        "and produce a stack that reads as a coherent concept design."
    )
    return " ".join(lines)


def _constraint_summary(
    constraints: List[Constraint],
    wp_state: str,
    proximity: float,
    compliance_primary_ct: str = "",
    stabilisation_cts: List[str] = None,
) -> str:
    if not constraints:
        return f"System is {wp_state} at {proximity:.0f}% proximity with no dominant constraint identified."
    stabilisation_cts = stabilisation_cts or []
    primary = constraints[0]
    secondaries = constraints[1:]

    # If a constraint priority override is active, surface it explicitly
    if compliance_primary_ct and stabilisation_cts:
        ct_label_map = _CT_LABELS_V1
        cp_label  = ct_label_map.get(compliance_primary_ct, compliance_primary_ct)
        stab_labels = [ct_label_map.get(ct, ct) for ct in stabilisation_cts]
        parts = [
            f"The plant is {wp_state} at {proximity:.0f}% proximity. "
            f"Constraint priority analysis: the compliance-limiting constraint is "
            f"{cp_label} — resolving this is necessary to achieve effluent licence compliance. "
            f"The following constraints require system stabilisation but do not alone determine "
            f"compliance: {', '.join(stab_labels)}. "
            f"The upgrade sequence addresses stabilisation first (to protect process integrity) "
            f"before the compliance-primary constraint."
        ]
    else:
        parts = [
            f"The plant is {wp_state} at {proximity:.0f}% proximity. "
            f"The dominant constraint is {primary.label} [{primary.severity}], "
            f"originating from: {', '.join(primary.source_modes[:3])}."
        ]
        if secondaries:
            parts.append(
                f"Secondary constraints: {', '.join(c.label for c in secondaries[:3])}."
            )
    return " ".join(parts)


def _residual_risks(
    constraints: List[Constraint],
    stages: List[PathwayStage],
    plant_context: Dict,
) -> List[str]:
    risks = []
    ct_set   = {c.constraint_type for c in constraints}
    tech_set = {s.technology for s in stages}

    # Always: wet weather hydraulic
    risks.append(
        "Extreme wet weather events (> 3× DWA) may still require upstream "
        "sewer attenuation or storm storage even after process intensification."
    )

    # Carbon limitation
    if (CT_TN_POLISH in ct_set or CT_BIOLOGICAL in ct_set) and TI_DENFILTER not in tech_set:
        risks.append(
            "TN compliance may require external carbon dosing (methanol or acetate) "
            "if COD/N ratio is below 4 after recycle optimisation."
        )

    # Operational complexity
    if len(stages) >= 3:
        risks.append(
            f"A {len(stages)}-stage upgrade increases operational complexity. "
            "Staged commissioning with effluent monitoring between stages is essential "
            "before proceeding to the next."
        )

    # Energy / sludge
    if TI_IFAS in tech_set or TI_HYBAS in tech_set or TI_MBBR in tech_set:
        risks.append(
            "Biofilm addition changes the mixed liquor MLSS profile. "
            "Aeration control loops and wasting strategy must be recalibrated "
            "after biofilm stage commissioning."
        )

    if TI_MEMDENSE in tech_set or TI_INDENSE in tech_set or TI_MIGINDENSE in tech_set:
        risks.append(
            "Selective wasting (inDENSE / memDENSE) increases wasted sludge density. "
            "Sludge dewatering performance should be re-assessed after commissioning."
        )

    if TI_DENFILTER in tech_set:
        risks.append(
            "Denitrification filter requires continuous methanol dosing and "
            "filter backwash management — increases chemical OPEX and operator attention."
        )

    return risks


def _confidence(failure_modes, plant_context: Dict) -> str:
    n_modes = len(failure_modes.items) if failure_modes else 0
    missing = plant_context.get("missing_fields_count", 0) or 0
    if n_modes >= 3 and missing <= 2:
        return "High"
    if n_modes >= 1 or missing <= 5:
        return "Medium"
    return "Low"


# ── Main entry point ───────────────────────────────────────────────────────────

def build_upgrade_pathway(
    wp_result,
    plant_context: Optional[Dict] = None,
) -> UpgradePathway:
    """
    Build a consultant-grade upgrade pathway from a WaterPointResult.

    Parameters
    ----------
    wp_result : WaterPointResult
        Full output from apps.wastewater_app.waterpoint_engine.analyse().

    plant_context : dict, optional
        Supplemental signals not in WaterPointResult:
          plant_type       str   "CAS" / "BNR" / "SBR" / "MBR" / "Nereda"
          is_sbr           bool
          is_mbr           bool
          overflow_risk    bool
          wet_weather_peak bool
          aeration_constrained bool
          high_load        bool
          flow_ratio       float
          missing_fields_count int

    Returns
    -------
    UpgradePathway
    """
    ctx = dict(plant_context or {})
    # Fix 5: greenfield mode — read from context (callers inject via plant_context)
    # Also accept greenfield_mode key as an alias
    if ctx.get('greenfield_mode') and not ctx.get('greenfield'):
        ctx['greenfield'] = True

    s  = wp_result.system_stress
    fm = wp_result.failure_modes
    fst= getattr(wp_result.system_stress, "flow_scenario", "") or ctx.get("flow_scenario", "")

    # ── Step 1: Classify constraints ───────────────────────────────────────────
    constraints = _classify_from_failure_modes(fm, s.state, fst, ctx)

    # Supplement from primary_constraint string if no modes found
    if not constraints:
        pc_lower = s.primary_constraint.lower()
        if "clarifier" in pc_lower or "settling" in pc_lower:
            constraints = [Constraint(CT_SETTLING, _CT_LABELS_V1[CT_SETTLING],
                                      "Medium", _PRIORITY[CT_SETTLING], [s.primary_constraint])]
        elif "aeration" in pc_lower or "oxygen" in pc_lower:
            constraints = [Constraint(CT_NITRIFICATION, _CT_LABELS_V1[CT_NITRIFICATION],
                                      "Medium", _PRIORITY[CT_NITRIFICATION], [s.primary_constraint])]
        elif "throughput" in pc_lower or "hydraulic" in pc_lower:
            constraints = [Constraint(CT_HYDRAULIC, _CT_LABELS_V1[CT_HYDRAULIC],
                                      "Medium", _PRIORITY[CT_HYDRAULIC], [s.primary_constraint])]
        elif "cycle" in pc_lower:
            constraints = [Constraint(CT_SETTLING, _CT_LABELS_V1[CT_SETTLING],
                                      "Medium", _PRIORITY[CT_SETTLING], [s.primary_constraint])]

    # ── Step 2: Priority sort (already done in _classify) ──────────────────────
    # ── Step 3-4: Build stages ─────────────────────────────────────────────────
    # Inject CT_HYDRAULIC when steady-state clarifier signals are present in context
    # (clarifier_overloaded or SVI > 120) but not already classified.
    _ctx_cl_over = bool(ctx.get("clarifier_overloaded", False))
    _ctx_svi_hi  = (ctx.get("svi_ml_g") or 0.) > 120.
    _ct_types    = {c.constraint_type for c in constraints}
    if (_ctx_cl_over or _ctx_svi_hi) and CT_HYDRAULIC not in _ct_types:
        constraints = [Constraint(
            CT_HYDRAULIC, _CT_LABELS_V1[CT_HYDRAULIC],
            "High" if _ctx_cl_over else "Medium",
            _PRIORITY[CT_HYDRAULIC],
            ["Steady-state clarifier limitation (SOR overloaded or SVI > 120 mL/g)"]
        )] + constraints

    guardrail_notes: List[str] = []
    stages = _build_pathway_stages(constraints, ctx)

    # ── Step 5: Apply engineering guardrails ────────────────────────────────────
    stages = _apply_guardrails(stages, constraints, guardrail_notes)

    # Greenfield hydraulic note (CoMag/BioMag suppressed — design sizing instead)
    if bool(ctx.get("greenfield", False)):
        _gf_hyd_needed = any(
            c.constraint_type in (CT_HYDRAULIC, CT_WET_WEATHER)
            for c in constraints
        )
        if _gf_hyd_needed and not any("Hydraulic capacity" in n for n in guardrail_notes):
            guardrail_notes.append(
                "Hydraulic capacity to be addressed through sizing of clarifiers, "
                "reactors, and hydraulic pathways in the design phase. "
                "No retrofit hydraulic relief technology is required on a new plant."
            )

    # Guardrail: always add wet weather note
    if not any("wet weather" in n.lower() for n in guardrail_notes):
        guardrail_notes.append(
            "Note: Extreme wet weather may still require storage or sewer attenuation "
            "even after process upgrades are complete."
        )

    # ── Biological hierarchy traceability notes (v24Z38) ──────────────────────
    bio_stages  = [s for s in stages if s.bio_hierarchy_level > 0]
    ct_set_g    = {c.constraint_type for c in constraints}
    nh4_stable  = not ctx.get("nh4_near_limit", False)
    aer_const   = bool(ctx.get("aeration_constrained", False))

    if bio_stages:
        levels_used = sorted({s.bio_hierarchy_level for s in bio_stages})
        level_map   = {1:"Level 1 (process optimisation)",
                       2:"Level 2 (biomass retention)",
                       3:"Level 3 (aeration intensification)",
                       4:"Level 4 (tertiary denitrification)"}
        levels_str  = " → ".join(level_map.get(l,"") for l in levels_used)
        guardrail_notes.append(
            f"Biological hierarchy: {levels_str}. "
            "This sequence reflects the expert escalation principle: optimise suspended "
            "growth first, add biomass retention only when SRT is limiting, add aeration "
            "intensification only when blowers are the binding constraint, and apply "
            "tertiary denitrification only when biological optimisation is exhausted."
        )

    # If TN-only case: confirm no level-skipping occurred
    if (CT_TN_POLISH in ct_set_g or CT_BIOLOGICAL in ct_set_g) and CT_NITRIFICATION not in ct_set_g:
        has_l1 = any(s.bio_hierarchy_level == 1 for s in bio_stages)
        has_l2_plus = any(s.bio_hierarchy_level >= 2 for s in bio_stages)
        if has_l2_plus and not has_l1:
            guardrail_notes.append(
                "WARNING: TN-only case — Level 2+ technology selected without Level 1 "
                "(process optimisation). Review constraint classification."
            )
        elif has_l1:
            guardrail_notes.append(
                "TN exceedance addressed via Level 1 (process optimisation) — correct "
                "hierarchy entry point for nitrogen-compliant plant."
            )

    # If nitrification case: confirm MABR is justified by aeration constraint
    if CT_NITRIFICATION in ct_set_g:
        mabr_in = any(s.technology == TI_MABR for s in stages)
        if mabr_in and not aer_const:
            guardrail_notes.append(
                "Note: MABR selected without confirmed aeration constraint. "
                "Verify blower capacity audit confirms headroom is insufficient before "
                "detailed design commitment. IFAS may be preferred if headroom exists."
            )
        elif mabr_in and aer_const:
            guardrail_notes.append(
                "MABR justified at Level 3: aeration system is near maximum capacity. "
                "IFAS alone would not resolve the oxygen delivery constraint. "
                "MABR applicability notes: "
                "Strong fit — aeration constrained, footprint constrained, or cold-climate nitrification. "
                "Membrane lifecycle 8–10 years; FOG/scaling fouling risk requires management. "
                "Decision tension: compact energy-efficient solution vs lower-CAPEX conventional expansion."
            )

    # ── DNF stack escalation guardrail ────────────────────────────────────────
    # When TN target ≤ 3 mg/L and no advanced nitrogen removal (DNF or PdNA) is
    # in the stack, the compliance layer will return stack_compliance_gap = True.
    # Act on it here: add DNF to the primary stack so the recommendation and the
    # compliance assessment are internally consistent.
    _tn_tgt_esc   = float(ctx.get("tn_target_mg_l") or 10.)
    _tn_basis_esc = ctx.get("tn_target_basis", "") or ""
    _is_p95_esc   = "95" in _tn_basis_esc or _tn_tgt_esc <= 3.0
    _tech_set_esc = {s.technology for s in stages}
    _has_adv_esc  = TI_DENFILTER in _tech_set_esc or TI_PDNA in _tech_set_esc
    _nh4_ok_esc   = not bool(ctx.get("nh4_near_limit", False))
    _not_sbr_esc  = not bool(ctx.get("is_sbr", False))

    _nh4_nl_esc = bool(ctx.get("nh4_near_limit", False))
    if (_tn_tgt_esc <= 3.0
            and _is_p95_esc
            and not _has_adv_esc
            and _not_sbr_esc):

        # Determine insertion position: DNF goes after Bardenpho if present,
        # otherwise after the last biological stage, before Tertiary P.
        _bard_idx  = next((i for i,s in enumerate(stages)
                           if s.technology in (TI_BARDENPHO, TI_RECYCLE_OPT)), None)
        _tert_p_idx = next((i for i,s in enumerate(stages)
                            if s.technology == TI_TERT_P), None)

        if _tert_p_idx is not None:
            _insert_pos = _tert_p_idx   # before Tertiary P
        elif _bard_idx is not None:
            _insert_pos = _bard_idx + 1
        else:
            _insert_pos = len(stages)   # append at end

        _dnf_prereq = (
            "Methanol dosing system and filter backwash system procured."
            + (" NOTE: nitrification is currently near its limit — "
               "establish stable NH₄ control before commissioning DNF."
               if _nh4_nl_esc else " NH₄ stably controlled.")
        )
        _dnf_basis = (
            "Methanol-dosed tertiary denitrification: ~2.5–3.0 mg MeOH per mg NO₃-N. "
            "DO at filter inlet must be < 0.5 mg/L. Required to close the "
            "TN ≤3 mg/L compliance gap that biological optimisation alone cannot close."
            + (" Commissioning prerequisite: establish stable NH₄ control first."
               if _nh4_nl_esc else "")
        )
        _dnf_num = max((s.stage_number for s in stages), default=0) + 1
        _dnf_stage = PathwayStage(
            stage_number        = _dnf_num,
            technology          = TI_DENFILTER,
            tech_display        = _TECH_DISPLAY.get(TI_DENFILTER, TI_DENFILTER),
            mechanism           = MECH_TERT_DN,
            mechanism_label     = _MECH_LABELS_V1.get(MECH_TERT_DN, MECH_TERT_DN),
            purpose             = (
                "Denitrification filter provides tertiary TN polishing to close the "
                "TN ≤3 mg/L compliance gap that biological optimisation alone cannot close."
            ),
            engineering_basis   = _dnf_basis,
            addresses           = [CT_TN_POLISH],
            prerequisite        = _dnf_prereq,
            capex_class         = "High",
            bio_hierarchy_level = 4,
            bio_hierarchy_rationale = (
                "DNF is Level 4 — tertiary denitrification. Required because TN ≤3 mg/L "
                "at 95th percentile cannot be reliably achieved by biological "
                "optimisation alone on this stack."
            ),
        )
        stages = stages[:_insert_pos] + [_dnf_stage] + stages[_insert_pos:]
        guardrail_notes.append(
            "DNF added to primary stack: TN ≤{:.0f} mg/L at 95th percentile basis "
            "requires tertiary denitrification. Biological optimisation alone is "
            "insufficient to close this gap reliably.".format(_tn_tgt_esc)
        )

    # ── Unified Process–Hydraulic Escalation ──────────────────────────────────
    # Triggered when: stack_compliance_gap=True, stringent target (TN≤3 or TP≤0.1),
    # and the system is in confirmed extreme failure (confidence proxy: gap + target).
    # Adds tertiary closure elements that are absent from the current stack.
    _esc_gap    = bool(ctx.get("stack_compliance_gap", False))
    _esc_tn_tgt = float(ctx.get("tn_target_mg_l") or 99.)
    _esc_tp_tgt = float(ctx.get("tp_target_mg_l") or 99.)
    _esc_strict = (_esc_tn_tgt <= 3.0 or _esc_tp_tgt <= 0.1)
    _esc_cs     = int(ctx.get("confidence_score", 100))   # injected by caller if available
    _esc_low_cs = _esc_cs < 20

    # Only escalate when gap is confirmed AND target is stringent AND (low score or extreme state)
    _esc_active = _esc_gap and _esc_strict and (_esc_low_cs or s.proximity_percent >= 250.)
    _esc_gf     = bool(ctx.get("greenfield", False))
    _esc_sbr    = bool(ctx.get("is_sbr", False))

    if _esc_active and not _esc_sbr:
        _esc_tech  = {st.technology for st in stages}
        _esc_notes: list = []
        _esc_nh4_nl = bool(ctx.get("nh4_near_limit", False))
        _esc_fr     = float(ctx.get("flow_ratio", 1.) or 1.)
        # Part 3: CoMag escalation guard — requires genuine storm risk
        _esc_storm  = (bool(ctx.get("overflow_risk", False))
                       or bool(ctx.get("wet_weather_peak", False)))
        _esc_hyd    = (_esc_storm or _esc_fr >= 3.)  # CT_HYDRAULIC alone insufficient

        # 1. DNF closure for TN ≤3 mg/L
        if (_esc_tn_tgt <= 3.0
                and TI_DENFILTER not in _esc_tech
                and TI_PDNA not in _esc_tech):
            _esc_dnf_prereq = (
                "Methanol dosing system and filter backwash system procured."
                + (" DNF performance depends on stable nitrification and may require "
                   "staged commissioning." if _esc_nh4_nl else " NH₄ stably controlled.")
            )
            _esc_dnf_num = max((st.stage_number for st in stages), default=0) + 1
            _esc_tert_idx = next(
                (i for i, st in enumerate(stages) if st.technology == TI_TERT_P), None)
            _esc_insert = _esc_tert_idx if _esc_tert_idx is not None else len(stages)
            _esc_dnf_stage = PathwayStage(
                stage_number        = _esc_dnf_num,
                technology          = TI_DENFILTER,
                tech_display        = _TECH_DISPLAY.get(TI_DENFILTER, TI_DENFILTER),
                mechanism           = MECH_TERT_DN,
                mechanism_label     = _MECH_LABELS_V1.get(MECH_TERT_DN, MECH_TERT_DN),
                purpose             = (
                    "Tertiary denitrification filter included as closure layer to ensure "
                    "TN ≤3 mg/L compliance under constrained upstream conditions."
                ),
                engineering_basis   = (
                    "Methanol-dosed tertiary denitrification: ~2.5–3.0 mg MeOH per mg NO₃-N. "
                    "DO at filter inlet < 0.5 mg/L. Provides robustness during peak loading "
                    "and upstream process variability."
                    + (" DNF performance depends on stable nitrification and may require "
                       "staged commissioning." if _esc_nh4_nl else "")
                ),
                addresses           = [CT_TN_POLISH],
                prerequisite        = _esc_dnf_prereq,
                capex_class         = "High",
                bio_hierarchy_level = 4,
                bio_hierarchy_rationale = (
                    "DNF is Level 4 — tertiary denitrification. Included as closure layer "
                    "because TN ≤3 mg/L cannot be reliably achieved on the current stack."
                ),
            )
            stages = stages[:_esc_insert] + [_esc_dnf_stage] + stages[_esc_insert:]
            _esc_tech = {st.technology for st in stages}
            _esc_notes.append(
                "DNF added as tertiary closure layer: TN ≤3 mg/L target cannot be met "
                "on the current biological stack under peak loading conditions."
            )

        # 2. CoMag closure for hydraulic constraint (brownfield only)
        if _esc_hyd and not _esc_gf and TI_COMAG not in _esc_tech:
            _esc_comag_num = max((st.stage_number for st in stages), default=0) + 1
            # CoMag goes at Stage 1 (before biological stages)
            _esc_comag_stage = PathwayStage(
                stage_number        = _esc_comag_num,
                technology          = TI_COMAG,
                tech_display        = _TECH_DISPLAY.get(TI_COMAG, TI_COMAG),
                mechanism           = MECH_BALLASTED,
                mechanism_label     = _MECH_LABELS_V1.get(MECH_BALLASTED, MECH_BALLASTED),
                purpose             = (
                    "CoMag ballasted clarification included as hydraulic closure layer. "
                    "Provides peak flow protection and enhances phosphorus removal and "
                    "solids capture under peak flow conditions."
                ),
                engineering_basis   = (
                    "CoMag treats flows of 3–5× DWA without new secondary tanks. "
                    "Surface overflow rates of 10–20 m/h vs 1–2 m/h conventional. "
                    "CoMag also enhances phosphorus removal and improves solids capture "
                    "under peak flow conditions."
                ),
                addresses           = [CT_HYDRAULIC, CT_WET_WEATHER],
                prerequisite        = "Ballast recovery system installed.",
                capex_class         = "Medium",
            )
            # Insert at front (Stage 1 position)
            stages = [_esc_comag_stage] + stages
            _esc_notes.append(
                "CoMag added as hydraulic closure layer: peak flow protection and "
                "phosphorus removal enhancement under peak loading conditions."
            )
        elif _esc_hyd and _esc_gf:
            _esc_notes.append(
                "Hydraulic and solids capacity to be addressed through design sizing. "
                "Tertiary clarification technologies should only be considered if "
                "required after sizing."
            )
        elif not _esc_hyd and not _esc_gf and CT_HYDRAULIC in {c.constraint_type for c in constraints}:
            # Hydraulic constraint present but peak ratio < 3 and no storm flag —
            # CoMag suppressed; conventional management is appropriate
            _esc_notes.append(
                "Hydraulic capacity can be managed through conventional design "
                "without ballasted clarification at this peak flow ratio."
            )

        # 3. Escalation header note — always emitted when escalation fires
        _esc_final_tech = {st.technology for st in stages}
        if not any("Escalation Mode" in n for n in guardrail_notes):
            guardrail_notes.insert(0,
                "Escalation Mode Activated — Tertiary Closure Strategy Applied: "
                "Tertiary processes included to ensure compliance under constrained "
                "upstream conditions. These systems provide robustness during peak "
                "loading and process variability."
            )
        if _esc_notes:
            guardrail_notes.extend(_esc_notes)
        # CoMag co-benefit note — emit if CoMag is in final stack
        if (TI_COMAG in _esc_final_tech
                and not any("CoMag also enhances" in n for n in guardrail_notes)):
            guardrail_notes.append(
                "CoMag also enhances phosphorus removal and improves solids capture "
                "under peak flow conditions."
            )

    # ── Step 6-7: Build alternatives and narrative ─────────────────────────────
    alternatives  = _build_pathway_alternatives(constraints, stages, ctx)

    # ── Constraint priority override ────────────────────────────────────────
    comp_primary_ct, stab_cts = _compliance_primary_constraint(constraints, stages, ctx)

    narrative     = _pathway_narrative(constraints, stages, comp_primary_ct, stab_cts)
    # Fix 5: surface greenfield mode in pathway narrative and guardrail notes
    _gf_active = bool(ctx.get('greenfield', False))
    if _gf_active:
        narrative = (
            '[Greenfield design mode] Optimal process configuration for target compliance. '
            'Brownfield-first logic is disabled — constraint hierarchy reflects new plant design. '
            + narrative
        )
        guardrail_notes = [
            'Greenfield mode active: existing asset constraints do not apply. '
            'Technology selection is optimised for the compliance target, not existing infrastructure.'
        ] + guardrail_notes
    con_summary   = _constraint_summary(constraints, s.state, s.proximity_percent,
                                        comp_primary_ct, stab_cts)
    residuals     = _residual_risks(constraints, stages, ctx)
    conf          = _confidence(fm, ctx)

    primary_con   = constraints[0] if constraints else Constraint(
        CT_UNKNOWN, "Unknown", "Low", 9, [])
    secondary_con = constraints[1:] if len(constraints) > 1 else []

    # Fix 5: greenfield mode — reclassify hydraulic 'Failure Risk' as design variable
    _state_label = s.state
    _gf_active   = bool(ctx.get('greenfield', False))
    if _gf_active and s.state == 'Failure Risk':
        # On a new plant, sizing for peak flow is a design choice, not a failure
        _state_label = 'Design load — size for compliance in design phase'

    # ── Footprint constraint + dual greenfield pathway generation ──────────────
    _fp = ctx.get("footprint_constraint", "abundant") or "abundant"
    _gf = bool(ctx.get("greenfield", False))
    _gf_concept_paths: List[GreenfieldConceptPath] = []

    # BF: footprint pressure escalates BF/GF score (via guardrail note; BF/GF layer reads ctx)
    _fp_bfgf_boost = 0
    if not _gf and _fp in ("constrained", "severely_constrained"):
        _fp_bfgf_boost = 2 if _fp == "constrained" else 4
        if _fp == "severely_constrained":
            guardrail_notes.append(
                "Site footprint materially limits conventional expansion and strengthens "
                "the case for compact intensification or replacement."
            )

    # GF: build dual concept pathways
    if _gf:
        _tn_tgt_fp   = float(ctx.get("tn_target_mg_l") or 10.)
        _tp_tgt_fp   = float(ctx.get("tp_target_mg_l") or 1.)
        _temp_fp     = float(ctx.get("temp_celsius") or 20.)
        _efcodn_fp   = float(ctx.get("cod_tn_ratio") or 10.) * 0.6
        _nh4nl_fp    = bool(ctx.get("nh4_near_limit", False))
        _cold_fp     = _temp_fp <= 12.
        _c_lim_fp    = _efcodn_fp < 5.
        _tight_fp    = _tn_tgt_fp <= 5. or _tp_tgt_fp <= 0.5
        _ultra_fp    = _tn_tgt_fp <= 3. or _tp_tgt_fp <= 0.1

        # ── Conventional path ────────────────────────────────────────────────
        _conv_stack = ["Conventional BNR", "Pre-anoxic + aerobic zones",
                       "Secondary clarifiers (design-sized)"]
        if _tight_fp:
            _conv_stack.append("Tertiary filtration")
        if _ultra_fp:
            _conv_stack.append("Denitrification Filter (if required by compliance)")
        if _tp_tgt_fp <= 0.5:
            _conv_stack.append("Chemical phosphorus removal")

        # Conventional credibility: feasible unless ultra-tight + cold + carbon-limited
        _conv_credible = not (_ultra_fp and _cold_fp and _c_lim_fp)
        _conv_reason   = ""
        if not _conv_credible:
            _conv_reason = (
                "TN ≤3 mg/L at 95th percentile with cold temperature and carbon limitation "
                "cannot be reliably achieved by conventional BNR sizing alone. "
                "Tertiary denitrification and external carbon are required regardless of footprint."
            )

        # Conventional base confidence: physical compliance proxy
        if _ultra_fp and (_cold_fp or _c_lim_fp):   _conv_base = 15
        elif _ultra_fp:                               _conv_base = 30
        elif _tight_fp and _cold_fp:                 _conv_base = 45
        elif _tight_fp:                              _conv_base = 60
        else:                                        _conv_base = 75

        # Footprint adjustment
        if _fp == "abundant":           _conv_base = min(100, _conv_base + 5)
        elif _fp == "severely_constrained": _conv_base = max(0, _conv_base - 10)

        # Part 4: Operator context — conventional benefits from lower-capability contexts
        _loc = ctx.get("location_type", "metro") or "metro"
        _op_remote = _loc in ("remote", "regional")
        if _op_remote:
            _conv_base = min(100, _conv_base + 5)  # simpler operation — more credible remotely
        _conv_base = max(0, min(100, _conv_base))

        def _band(s):
            if s >= 80: return "High"
            if s >= 60: return "Moderate"
            if s >= 40: return "Low"
            return "Very Low"

        _conv_tradeoffs = [
            "Higher footprint — requires adequate site area for conventional sizing",
            "Lower operational complexity — familiar operating model, lower specialist dependency",
            "Greater passive resilience through larger hydraulic and biological volumes",
        ]
        _conv_strategic = (
            "Preferred for remote or lower-capability utilities — more compatible with available operator expertise."
            if _op_remote else
            ("Preferred where land is available and utility capability favours simplicity and resilience."
             if _fp == "abundant" else
             "Viable but land-intensive; confirm site envelope can accommodate full conventional sizing.")
        )

        _gf_concept_paths.append(GreenfieldConceptPath(
            label             = "Conventional",
            stack             = _conv_stack,
            confidence        = _conv_base,
            confidence_label  = _band(_conv_base),
            footprint         = "High",
            complexity        = "Low",
            credible          = _conv_credible,
            non_credible_reason = _conv_reason,
            tradeoffs         = _conv_tradeoffs,
            strategic_note    = _conv_strategic,
        ))

        # ── Intensified path ─────────────────────────────────────────────────
        _int_stack = ["MABR (aeration intensification)"]
        if _tight_fp or _ultra_fp:
            _int_stack.append("Bardenpho process optimisation")
        if _ultra_fp and not _c_lim_fp:
            _int_stack.append("Denitrification Filter (TN closure)")
        elif _ultra_fp and _c_lim_fp:
            _int_stack.append("PdNA (carbon-free nitrogen removal — if nitrification stable)")
        if _tp_tgt_fp <= 0.5:
            _int_stack.append("Tertiary phosphorus removal")

        # Intensified credibility
        _int_credible = True
        _int_reason   = ""
        if _ultra_fp and _cold_fp and _c_lim_fp and _nh4nl_fp:
            _int_credible = False
            _int_reason   = (
                "At ≤12°C with severe carbon limitation and unstable nitrification, "
                "even intensified pathways cannot reliably achieve TN ≤3 mg/L without confirmed "
                "external carbon supply and nitrification stabilisation."
            )

        # Intensified base confidence: same physical proxy as conventional, adjusted for compactness
        if _ultra_fp and (_cold_fp or _c_lim_fp):   _int_base = 20
        elif _ultra_fp:                               _int_base = 40
        elif _tight_fp and _cold_fp:                 _int_base = 50
        elif _tight_fp:                              _int_base = 65
        else:                                        _int_base = 70

        # Footprint bonus
        if _fp == "constrained":            _int_base = min(100, _int_base + 5)
        elif _fp == "severely_constrained":  _int_base = min(100, _int_base + 10)

        # Part 4: Operator context — intensified requires capable operators
        if _op_remote:
            _int_base = max(0, _int_base - 5)  # specialist O&M harder in remote context
        else:
            _int_base = min(100, _int_base + 5)  # metro / strong capability supports intensified
        if not _int_credible: _int_base = min(_int_base, 20)
        _int_base = max(0, min(100, _int_base))

        _int_tradeoffs = [
            "Lower footprint — compact process reduces civil area and cost where land is scarce",
            "Higher specialist dependency — requires experienced operators and supply chain",
            "Tighter process control — less hydraulic buffering; more sensitive to upsets",
        ]
        _int_strategic = (
            "Requires specialist operational expertise; most credible where operator capability is strong."
            if _op_remote else
            ("Most credible where land is scarce and operator capability is strong."
             if _fp in ("constrained", "severely_constrained") else
             "Viable where technical performance demands compactness and specialist expertise is available.")
        )

        _gf_concept_paths.append(GreenfieldConceptPath(
            label             = "Intensified",
            stack             = _int_stack,
            confidence        = _int_base,
            confidence_label  = _band(_int_base),
            footprint         = "Low" if _fp == "severely_constrained" else "Moderate",
            complexity        = "High",
            credible          = _int_credible,
            non_credible_reason = _int_reason,
            tradeoffs         = _int_tradeoffs,
            strategic_note    = _int_strategic,
        ))

    return UpgradePathway(
        system_state         = _state_label,
        system_state_type    = "Hydraulic / operating stress",
        proximity_pct        = s.proximity_percent,
        plant_type           = ctx.get("plant_type", "Unknown"),
        flow_scenario        = fst or "DWA",
        constraints          = constraints,
        primary_constraint   = primary_con,
        secondary_constraints= secondary_con,
        stages               = stages,
        alternatives         = alternatives,
        pathway_narrative    = narrative,
        constraint_summary   = con_summary,
        residual_risks       = residuals,
        confidence           = conf,
        multi_constraint     = len(constraints) >= 2,
        guardrail_notes      = guardrail_notes,
        compliance_primary_ct= comp_primary_ct,
        stabilisation_cts    = stab_cts,
        footprint_constraint = ctx.get("footprint_constraint", "abundant") or "abundant",
        footprint_bfgf_boost = _fp_bfgf_boost,
        greenfield_pathways  = _gf_concept_paths,
    )
