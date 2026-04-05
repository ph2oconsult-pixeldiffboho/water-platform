"""
apps/wastewater_app/brownfield_upgrade_ranking.py

Brownfield Upgrade Pathway Ranking Engine
==========================================

Transforms WaterPoint from a technology selector into a constraint-matched
upgrade decision engine.

Evaluates and ranks the following upgrade pathways:
  - Nereda  (AGS conversion)
  - MOB     (miGRATE + inDENSE intensification)
  - MABR    (OxyFAS retrofit)
  - IFAS    (hybrid biofilm retrofit)
  - MBBR    (fixed-film expansion / conversion)

Design rules
------------
- Pure functions — no Streamlit, no I/O, no side effects.
- Does NOT modify existing technology engines (BNR, Nereda, MOB, MABR).
- Does NOT modify Greenfield scoring engine.
- Reads BrownfieldConstraintResult.utilisation_summary for input data.
- Derives constraint flags internally from utilisation + WaterPoint fields.
- Returns UpgradeRankingResult — self-contained, ready for UI rendering.

Calibration references
----------------------
- MOB: Lang Lang STP process modelling (miGRATE + inDENSE)
- MABR: OxyMem OxyFAS / Kawana modelling
- Nereda: Longwarry STP, v24Z23 WaterPoint model
- IFAS: standard IFAS retrofit assessment (Metcalf & Eddy 5th Ed)
- MBBR: WEF MOP 16, fixed-film retrofit practice

Scoring basis
-------------
+3  Technology directly resolves primary constraint
+2  Technology resolves a secondary constraint
+1  Technology partially improves constraint (indirect benefit)
-2  Technology mismatched with primary constraint
-3  Technology contradicts system limitation (makes things worse)

Data confidence adjustment:
  Low  → scores × 0.80
  High → scores × 1.00 (no adjustment)

Score is normalised to 0–10 after raw accumulation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


# ── Technology codes ────────────────────────────────────────────────────────────
TECH_NEREDA = "nereda"
TECH_MOB    = "mob"
TECH_MABR   = "mabr"
TECH_IFAS   = "ifas"
TECH_MBBR   = "mbbr"

_ALL_TECHS = [TECH_NEREDA, TECH_MOB, TECH_MABR, TECH_IFAS, TECH_MBBR]

_TECH_NAMES = {
    TECH_NEREDA: "Nereda® (AGS conversion)",
    TECH_MOB:    "MOB (miGRATE + inDENSE intensification)",
    TECH_MABR:   "MABR (OxyFAS retrofit)",
    TECH_IFAS:   "IFAS (hybrid biofilm retrofit)",
    TECH_MBBR:   "MBBR (fixed-film expansion)",
}

# ── Constraint flag names (derived internally) ─────────────────────────────────
_HYDRAULIC       = "hydraulic"
_AERATION        = "aeration"
_CLARIFIER       = "clarifier"
_NITRIFICATION   = "nitrification"
_DENITRIFICATION = "denitrification"
_CARBON          = "carbon_limitation"
_FOOTPRINT       = "footprint"
_BIOLOGICAL_VOL  = "biological_volume"
_SOLIDS          = "solids_retention"

# Utilisation thresholds for flag activation
_FLAG_THRESHOLD   = 0.80   # ≥80% → constraint flag active
_SEVERE_THRESHOLD = 1.00   # ≥100% → severe / FAIL

# ── Technology capability map ──────────────────────────────────────────────────
# For each technology: which constraints it SOLVES, HELPS, MISMATCHES, CONTRADICTS.
# Tuple structure: (solves, helps, mismatches, contradicts)
# Each list contains constraint flag names.

_CAPABILITY_MAP: Dict[str, Dict[str, List[str]]] = {

    TECH_NEREDA: {
        "solves":       [_CLARIFIER, _SOLIDS, _FOOTPRINT, _BIOLOGICAL_VOL],
        "helps":        [_NITRIFICATION, _DENITRIFICATION],
        "mismatches":   [],
        "contradicts":  [],
        # Qualitative notes
        "primary_benefit": "Eliminates clarifier constraint and improves footprint via AGS settling — "
                           "no secondary clarifier required after conversion.",
        "key_limitation":  "Requires full process conversion. Existing infrastructure utilisation "
                           "is limited. Capital-intensive and operationally complex to implement.",
        "residual":        "Requires careful startup and granule formation (3–6 months). "
                           "Nitrification / TN performance depends on system design.",
        "capex_class":     "High",
        "complexity":      "High",
    },

    TECH_MOB: {
        "solves":       [_SOLIDS, _NITRIFICATION, _BIOLOGICAL_VOL],
        "helps":        [_DENITRIFICATION, _AERATION],
        "mismatches":   [_HYDRAULIC],   # does not address hydraulic throughput
        "contradicts":  [],
        "primary_benefit": "Delivers a sequenced brownfield upgrade: inDENSE first stabilises "
                           "settling and enables cycle compression; miGRATE then improves TN, "
                           "reduces aerobic mass fraction, and lowers solids inventory. "
                           "No new reactor volume required. Practical capacity uplift is "
                           "achieved by unlocking the hydraulic potential already in the plant.",
        "key_limitation":  "MOB is a sequenced pathway, not a single binary option. "
                           "inDENSE must be installed first (settling gateway). "
                           "miGRATE alone does not solve settling (Lang Lang + Army Bay finding). "
                           "Extreme peak wet weather still requires balancing/storage attenuation "
                           "regardless of intensification level.",
        "residual":        "Hydraulic attenuation/storage still required under extreme peak wet weather. "
                           "Selector performance must be sustained for inDENSE benefit to persist. "
                           "Full MOB benefit requires both stages to be commissioned and stable.",
        "capex_class":     "Medium",
        "complexity":      "Medium",
    },

    TECH_MABR: {
        "solves":       [_AERATION, _NITRIFICATION],
        "helps":        [_BIOLOGICAL_VOL],
        "mismatches":   [_CLARIFIER, _SOLIDS],   # does NOT solve settling
        "contradicts":  [],
        "primary_benefit": "Provides additional oxygen transfer for nitrification through direct "
                           "membrane delivery — no new tanks required. Energy-efficient. "
                           "Strong NHx resilience (Kawana: NHx <0.1 mg/L across all scenarios).",
        "key_limitation":  "Does NOT address clarifier or solids separation constraints. "
                           "TN performance remains carbon-limited — strong NHx ≠ strong TN. "
                           "Hybrid activated sludge system constraints (MLSS, recycle) remain.",
        "residual":        "Clarifier limitation remains after upgrade. "
                           "TN/NOx polishing requires carbon strategy, not MABR expansion.",
        "capex_class":     "Medium",
        "complexity":      "Medium",
    },

    TECH_IFAS: {
        "solves":       [_BIOLOGICAL_VOL, _NITRIFICATION],
        "helps":        [_AERATION, _DENITRIFICATION],
        "mismatches":   [_CLARIFIER, _HYDRAULIC],  # still clarifier-dependent
        "contradicts":  [],
        "primary_benefit": "Incremental biological capacity increase in existing tanks "
                           "through suspended carrier media. Nitrification resilience improves. "
                           "Established technology with many reference plants.",
        "key_limitation":  "Still fully dependent on existing clarifier capacity. "
                           "MLSS and hydraulic constraints remain in the host activated sludge system. "
                           "Media retention screens add operational complexity.",
        "residual":        "Clarifier capacity remains the governing constraint under peak conditions. "
                           "Hydraulic throughput unchanged.",
        "capex_class":     "Low",
        "complexity":      "Medium",
    },

    TECH_MBBR: {
        "solves":       [_BIOLOGICAL_VOL, _NITRIFICATION, _AERATION],
        "helps":        [_DENITRIFICATION, _FOOTPRINT],
        "mismatches":   [_CLARIFIER],   # downstream separation still needed
        "contradicts":  [],
        "primary_benefit": "Robust fixed biofilm capacity with modular expansion. "
                           "High volumetric nitrification rates. Resilient to load fluctuations. "
                           "Can operate at lower MLSS, reducing clarifier load.",
        "key_limitation":  "Downstream solids separation constraint remains unless MBBR-CASS or "
                           "MBBR-MBBR configuration is adopted. Integration with existing activated "
                           "sludge can be complex.",
        "residual":        "Clarifier and solids separation constraints remain unless a "
                           "post-MBBR clarification upgrade is included.",
        "capex_class":     "Medium",
        "complexity":      "Medium",
    },
}


# ── Result dataclasses ─────────────────────────────────────────────────────────

@dataclass
class ConstraintProfile:
    """Derived constraint flags from brownfield utilisation data."""
    hydraulic_flag:       bool = False
    aeration_flag:        bool = False
    clarifier_flag:       bool = False
    nitrification_flag:   bool = False
    denitrification_flag: bool = False
    carbon_limit_flag:    bool = False
    footprint_flag:       bool = False
    biological_vol_flag:  bool = False
    solids_flag:          bool = False
    primary_constraint:   str  = "Unknown"
    secondary_constraints: List[str] = field(default_factory=list)
    data_confidence:      str  = "Medium"
    # Intelligence layer fields (populated by build_intensification_plan)
    constraint_type:      str  = "unknown"   # CT_* constant
    mechanism:            str  = ""           # MECH_* constant


@dataclass
class UpgradeOption:
    """Scored and ranked upgrade pathway."""
    tech_code:          str
    tech_name:          str
    raw_score:          float
    normalised_score:   float    # 0–10
    rank:               int
    primary_benefit:    str
    key_limitation:     str
    residual_constraint: str
    capex_class:        str      # Low / Medium / High
    complexity:         str      # Low / Medium / High
    score_breakdown:    List[str]   # list of scoring reasons
    excluded:           bool = False
    exclusion_reason:   str  = ""


@dataclass
class UpgradeRankingResult:
    """Full output of the ranking engine."""
    constraint_profile:     ConstraintProfile
    ranked_options:         List[UpgradeOption]   # sorted best→worst
    recommended:            Optional[UpgradeOption]
    secondary:              Optional[UpgradeOption]
    recommended_rationale:  str
    secondary_rationale:    str
    residual_warning:       str    # carbon limitation etc
    data_confidence_note:   str
    engineering_summary:    str    # one paragraph executive summary
    intensification_plan:   Optional[Any] = None   # IntensificationPlan (lazy import)


# ── Main ranking function ──────────────────────────────────────────────────────

def rank_upgrade_pathways(
    utilisation_summary:   Dict[str, Optional[float]],
    waterpoint_fields:     Optional[Dict] = None,
    data_confidence_level: str = "Medium",
    existing_tech_code:    str = "bnr",
) -> UpgradeRankingResult:
    """
    Evaluate and rank all upgrade pathways against the diagnosed plant constraints.

    Parameters
    ----------
    utilisation_summary : dict
        From BrownfieldConstraintResult.utilisation_summary.
        Keys: volume_utilisation_pct, clarifier_utilisation_pct,
              aeration_utilisation_pct, ras_utilisation_pct.
        Values: float (%) or None if not assessed.

    waterpoint_fields : dict, optional
        Additional signals from WaterPoint: state, failure modes, compliance.
        Keys: wp_state, carbon_limited_tn, hybrid_constrained,
              nitrification_flag, eff_tn_mg_l, eff_nh4_mg_l, tn_target_mg_l.

    data_confidence_level : str
        "Low" / "Medium" / "High"

    existing_tech_code : str
        Current technology (informs feasibility notes).

    Returns
    -------
    UpgradeRankingResult
    """
    wf = waterpoint_fields or {}

    # ── Step 1: Derive constraint profile ─────────────────────────────────────
    profile = _derive_constraint_profile(utilisation_summary, wf, data_confidence_level)

    # ── Step 2: Score each technology ─────────────────────────────────────────
    raw_scores: Dict[str, Tuple[float, List[str], bool, str]] = {}
    for tech in _ALL_TECHS:
        score, breakdown, excluded, excl_reason = _score_technology(
            tech, profile, wf
        )
        raw_scores[tech] = (score, breakdown, excluded, excl_reason)

    # ── Step 3: Confidence adjustment ─────────────────────────────────────────
    conf_multiplier = {"Low": 0.80, "Medium": 1.00, "High": 1.00}.get(
        data_confidence_level, 1.00
    )
    adjusted: Dict[str, float] = {
        t: max(0.0, raw_scores[t][0] * conf_multiplier)
        if not raw_scores[t][2] else 0.0    # excluded → score 0
        for t in _ALL_TECHS
    }

    # ── Step 4: Normalise to 0–10 ──────────────────────────────────────────────
    max_raw = max(adjusted.values()) if adjusted else 1.0
    if max_raw <= 0:
        max_raw = 1.0
    # Raw score range: theoretical max = +3+2+2+1 = 8; theoretical min = -3-2 = -5
    # Normalise relative to (−5 → 0, +8 → 10)
    _RAW_MIN = -5.0
    _RAW_MAX =  8.0
    _RAW_SPAN = _RAW_MAX - _RAW_MIN

    def _normalise(raw: float) -> float:
        clamped = max(_RAW_MIN, min(_RAW_MAX, raw))
        return round((clamped - _RAW_MIN) / _RAW_SPAN * 10.0, 1)

    # ── Step 5: Build UpgradeOption list ──────────────────────────────────────
    options: List[UpgradeOption] = []
    for tech in _ALL_TECHS:
        raw, breakdown, excluded, excl_reason = raw_scores[tech]
        adj_raw  = raw * conf_multiplier if not excluded else _RAW_MIN
        norm     = _normalise(adj_raw) if not excluded else 0.0
        cap      = _CAPABILITY_MAP[tech]
        options.append(UpgradeOption(
            tech_code         = tech,
            tech_name         = _TECH_NAMES[tech],
            raw_score         = round(raw, 1),
            normalised_score  = norm,
            rank              = 0,   # set below
            primary_benefit   = cap["primary_benefit"],
            key_limitation    = cap["key_limitation"],
            residual_constraint = cap["residual"],
            capex_class       = cap["capex_class"],
            complexity        = cap["complexity"],
            score_breakdown   = breakdown,
            excluded          = excluded,
            exclusion_reason  = excl_reason,
        ))

    # Sort: excluded last, then by normalised_score desc
    options.sort(key=lambda o: (o.excluded, -o.normalised_score))
    for i, opt in enumerate(options, 1):
        opt.rank = i

    # ── Step 6: Recommendation ────────────────────────────────────────────────
    viable = [o for o in options if not o.excluded]
    recommended = viable[0] if viable else None
    secondary   = viable[1] if len(viable) >= 2 else None

    # ── Step 7: Rationale text ────────────────────────────────────────────────
    rec_rat = _recommended_rationale(recommended, profile, wf)
    sec_rat = _secondary_rationale(secondary, recommended, profile)

    # ── Step 8: Residual warning ───────────────────────────────────────────────
    residual_warning = ""
    if profile.carbon_limit_flag:
        residual_warning = (
            "Carbon limitation is active — none of the biological upgrade pathways alone "
            "will resolve total nitrogen performance without carbon strategy optimisation. "
            "COD diversion, internal recycle, or external carbon dosing must be evaluated "
            "alongside any biological upgrade."
        )

    # ── Step 9: Confidence note ────────────────────────────────────────────────
    conf_note = ""
    if data_confidence_level == "Low":
        conf_note = (
            "Recommendation based on limited data — confirm with detailed site assessment "
            "and operating data review before committing to an upgrade pathway."
        )
    elif data_confidence_level == "High":
        conf_note = "High data confidence — scoring based on measured operating data."

    # ── Step 10: Engineering summary ──────────────────────────────────────────
    eng_summary = _engineering_summary(profile, recommended, secondary, residual_warning)

    # Build intensification plan (intelligence layer)
    try:
        from apps.wastewater_app.intensification_intelligence import build_intensification_plan
        _ii_plan = build_intensification_plan(profile, waterpoint_fields)
    except Exception:
        _ii_plan = None

    return UpgradeRankingResult(
        constraint_profile    = profile,
        ranked_options        = options,
        recommended           = recommended,
        secondary             = secondary,
        recommended_rationale = rec_rat,
        secondary_rationale   = sec_rat,
        residual_warning      = residual_warning,
        data_confidence_note  = conf_note,
        engineering_summary   = eng_summary,
        intensification_plan  = _ii_plan,
    )


# ── Constraint profile derivation ─────────────────────────────────────────────

def _derive_constraint_profile(
    util: Dict[str, Optional[float]],
    wf:   Dict,
    confidence: str,
) -> ConstraintProfile:
    """Derive constraint flags from utilisation summary + WaterPoint signals."""

    def _pct(key: str) -> Optional[float]:
        v = util.get(key)
        return v / 100.0 if v is not None else None   # convert % → fraction

    vol_u  = _pct("volume_utilisation_pct")
    clar_u = _pct("clarifier_utilisation_pct")
    aer_u  = _pct("aeration_utilisation_pct")
    ras_u  = _pct("ras_utilisation_pct")

    # Flags from utilisation
    aer_flag   = (aer_u  is not None and aer_u  >= _FLAG_THRESHOLD)
    clar_flag  = (clar_u is not None and clar_u >= _FLAG_THRESHOLD)
    vol_flag   = (vol_u  is not None and vol_u  >= _FLAG_THRESHOLD)
    ras_flag   = (ras_u  is not None and ras_u  >= _FLAG_THRESHOLD)

    # Flags from WaterPoint signals
    nit_flag   = bool(wf.get("nitrification_flag", False))
    carbon_lim = bool(wf.get("carbon_limited_tn", False))
    hybrid_c   = bool(wf.get("hybrid_constrained", False))
    wp_state   = wf.get("wp_state", "")

    # Hydraulic flag: RAS recycle saturated or WP state is Failure Risk from hydraulic cause
    hyd_flag   = ras_flag or (wp_state == "Failure Risk" and not aer_flag and not clar_flag)

    # Footprint: not directly from util, inferred if both vol and clarifier are constrained
    footprint_flag = vol_flag and clar_flag

    # Solids retention: clarifier saturated OR hybrid constrained
    solids_flag = clar_flag or hybrid_c

    # Denitrification: carbon limited → denitrification flag
    denit_flag = carbon_lim

    # Determine primary constraint (most constrained domain)
    severity: Dict[str, float] = {}
    if clar_u  is not None: severity[_CLARIFIER]      = clar_u
    if aer_u   is not None: severity[_AERATION]        = aer_u
    if vol_u   is not None: severity[_BIOLOGICAL_VOL]  = vol_u
    if ras_u   is not None: severity[_HYDRAULIC]       = ras_u
    if carbon_lim:          severity[_CARBON]          = 0.90   # soft signal

    primary = max(severity, key=severity.get) if severity else "Unknown"
    _primary_label = {
        _CLARIFIER:     "Clarifier / solids separation",
        _AERATION:      "Aeration / oxygen delivery",
        _BIOLOGICAL_VOL:"Biological volume / treatment capacity",
        _HYDRAULIC:     "Hydraulic recycle / throughput",
        _CARBON:        "Carbon-limited denitrification / TN",
    }.get(primary, primary.replace("_", " ").title())

    # Secondary constraints: everything ≥ _FLAG_THRESHOLD except primary
    secondaries = []
    _label_map = {
        _CLARIFIER:     "Clarifier loading",
        _AERATION:      "Aeration capacity",
        _BIOLOGICAL_VOL:"Biological volume",
        _HYDRAULIC:     "Hydraulic recycle",
        _CARBON:        "Carbon / TN limitation",
        _NITRIFICATION: "Nitrification resilience",
    }
    if nit_flag  and primary != _NITRIFICATION:  secondaries.append("Nitrification resilience")
    if carbon_lim and primary != _CARBON:         secondaries.append("Carbon / TN limitation")
    for k, v in severity.items():
        if k != primary and v >= _FLAG_THRESHOLD:
            label = _label_map.get(k, k.title())
            if label not in secondaries:
                secondaries.append(label)

    # Derive constraint_type + mechanism via intelligence layer
    from apps.wastewater_app.intensification_intelligence import (
        classify_constraint,
    )
    _cp_proto = ConstraintProfile(
        hydraulic_flag       = hyd_flag,
        aeration_flag        = aer_flag,
        clarifier_flag       = clar_flag,
        nitrification_flag   = nit_flag,
        denitrification_flag = denit_flag,
        carbon_limit_flag    = carbon_lim,
        footprint_flag       = footprint_flag,
        biological_vol_flag  = vol_flag,
        solids_flag          = solids_flag,
        primary_constraint   = _primary_label,
        secondary_constraints= secondaries,
        data_confidence      = confidence,
    )
    _ct, _mech, _ = classify_constraint(_cp_proto, wf)
    _cp_proto.constraint_type = _ct
    _cp_proto.mechanism       = _mech
    return _cp_proto


# ── Technology scoring ─────────────────────────────────────────────────────────

_CONSTRAINT_FLAG_MAP = {
    _HYDRAULIC:     "hydraulic_flag",
    _AERATION:      "aeration_flag",
    _CLARIFIER:     "clarifier_flag",
    _NITRIFICATION: "nitrification_flag",
    _DENITRIFICATION:"denitrification_flag",
    _CARBON:        "carbon_limit_flag",
    _FOOTPRINT:     "footprint_flag",
    _BIOLOGICAL_VOL:"biological_vol_flag",
    _SOLIDS:        "solids_flag",
}

_PRIMARY_CONSTRAINT_TO_FLAG = {
    "Clarifier / solids separation":    _CLARIFIER,
    "Aeration / oxygen delivery":       _AERATION,
    "Biological volume / treatment capacity": _BIOLOGICAL_VOL,
    "Hydraulic recycle / throughput":   _HYDRAULIC,
    "Carbon-limited denitrification / TN": _CARBON,
}


def _score_technology(
    tech: str,
    profile: ConstraintProfile,
    wf: Dict,
) -> Tuple[float, List[str], bool, str]:
    """
    Score a technology against the constraint profile.

    Returns (raw_score, breakdown_list, excluded_bool, exclusion_reason).
    """
    cap     = _CAPABILITY_MAP[tech]
    score   = 0.0
    reasons: List[str] = []

    # ── Hard exclusions ───────────────────────────────────────────────────────
    # Hydraulic constraint: biological-only solutions score low
    if profile.hydraulic_flag and tech in (TECH_MABR, TECH_IFAS):
        return (
            -2.0, [f"Hydraulic constraint active — {_TECH_NAMES[tech]} does not address throughput"],
            False,   # not excluded, just penalised
            "",
        )

    # ── Primary constraint matching ───────────────────────────────────────────
    primary_flag_key = _PRIMARY_CONSTRAINT_TO_FLAG.get(profile.primary_constraint)
    if primary_flag_key:
        if primary_flag_key in cap["solves"]:
            score += 3.0
            reasons.append(f"+3 Directly resolves primary constraint ({profile.primary_constraint})")
        elif primary_flag_key in cap["mismatches"]:
            score -= 2.0
            reasons.append(f"-2 Mismatch with primary constraint ({profile.primary_constraint})")
        elif primary_flag_key in cap["contradicts"]:
            score -= 3.0
            reasons.append(f"-3 Contradicts system limitation ({profile.primary_constraint})")
        elif primary_flag_key in cap["helps"]:
            score += 1.0
            reasons.append(f"+1 Partially improves primary constraint ({profile.primary_constraint})")

    # ── Secondary constraints ─────────────────────────────────────────────────
    secondary_hits = set()
    for constraint_key in cap["solves"]:
        flag_attr = _CONSTRAINT_FLAG_MAP.get(constraint_key)
        if flag_attr and getattr(profile, flag_attr, False):
            # Don't double-count the primary
            if constraint_key != primary_flag_key and constraint_key not in secondary_hits:
                score += 2.0
                label = constraint_key.replace("_", " ").title()
                reasons.append(f"+2 Resolves secondary constraint ({label})")
                secondary_hits.add(constraint_key)

    for constraint_key in cap["helps"]:
        flag_attr = _CONSTRAINT_FLAG_MAP.get(constraint_key)
        if flag_attr and getattr(profile, flag_attr, False):
            if constraint_key != primary_flag_key and constraint_key not in secondary_hits:
                score += 1.0
                label = constraint_key.replace("_", " ").title()
                reasons.append(f"+1 Partially improves ({label})")
                secondary_hits.add(constraint_key)

    for constraint_key in cap["mismatches"]:
        flag_attr = _CONSTRAINT_FLAG_MAP.get(constraint_key)
        if flag_attr and getattr(profile, flag_attr, False):
            if constraint_key != primary_flag_key:
                score -= 2.0
                label = constraint_key.replace("_", " ").title()
                reasons.append(f"-2 Mismatch ({label} active but not addressed)")

    # ── Footprint bonus ───────────────────────────────────────────────────────
    if profile.footprint_flag and constraint_key not in secondary_hits:
        if _FOOTPRINT in cap["solves"]:
            score += 1.0
            reasons.append("+1 Footprint constraint active — Nereda / MABR advantage")

    # ── Carbon limitation penalty ─────────────────────────────────────────────
    if profile.carbon_limit_flag:
        if _DENITRIFICATION not in cap["solves"] and _DENITRIFICATION not in cap["helps"]:
            score -= 1.0
            reasons.append("-1 Carbon limitation unresolved by this pathway alone")

    # ── Special: hydraulic mismatch penalty for solutions that ignore it ───────
    if profile.hydraulic_flag and _HYDRAULIC not in cap["solves"] and _HYDRAULIC not in cap["helps"]:
        score -= 1.0
        reasons.append("-1 Hydraulic constraint not addressed by this pathway")

    if not reasons:
        reasons.append("No active constraints matched to this technology's capability profile")

    return (score, reasons, False, "")


# ── Rationale text generators ──────────────────────────────────────────────────

def _recommended_rationale(
    opt: Optional[UpgradeOption],
    profile: ConstraintProfile,
    wf: Dict,
) -> str:
    if opt is None:
        return "Insufficient data to generate a recommendation."
    pc = profile.primary_constraint
    name = opt.tech_name
    # Constraint-matched sentences
    if "Clarifier" in pc or "solids" in pc.lower():
        if opt.tech_code == TECH_NEREDA:
            return (
                f"The plant is currently clarifier- or solids-limited. "
                f"{name} eliminates the secondary clarifier constraint entirely by replacing "
                f"conventional settling with aerobic granular sludge. "
                f"This is the most direct resolution of the primary constraint, albeit at "
                f"the cost of a full process conversion."
            )
        if opt.tech_code == TECH_MOB:
            return (
                f"The plant is currently clarifier- or solids-limited. "
                f"{name} directly increases solids retention through inDENSE gravimetric selection "
                f"and biofilm carrier augmentation, improving settling without new reactor volume. "
                f"This is the most practical near-term resolution of the primary constraint."
            )
    if "Aeration" in pc or "oxygen" in pc.lower():
        if opt.tech_code == TECH_MABR:
            return (
                f"Aeration capacity is the primary constraint. "
                f"{name} provides additional oxygen transfer through direct membrane delivery "
                f"without expanding tank volume or blower infrastructure. "
                f"This is the most targeted resolution of the aeration constraint."
            )
        if opt.tech_code == TECH_IFAS:
            return (
                f"Aeration capacity and biological volume are the primary constraints. "
                f"{name} increases biological treatment capacity in existing tanks, "
                f"reducing the volumetric oxygen demand per unit of treatment. "
                f"This is the lowest-cost pathway to biological capacity increase."
            )
    if "Biological" in pc or "volume" in pc.lower():
        return (
            f"Biological treatment capacity is the primary constraint. "
            f"{name} increases effective biological volume through biofilm augmentation, "
            f"enabling greater throughput within the existing tank footprint. "
            f"This pathway prioritises capacity intensification before civil expansion."
        )
    if "Carbon" in pc or "denitrification" in pc.lower():
        return (
            f"Total nitrogen performance is carbon-limited — the biological upgrade pathways "
            f"alone will not resolve this. {name} scores highest among the biological upgrade options "
            f"and should be implemented alongside a carbon strategy review to unlock TN improvement."
        )
    # Generic fallback
    return (
        f"{name} scores highest against the diagnosed plant constraints "
        f"({profile.primary_constraint}). "
        f"{opt.primary_benefit}"
    )


def _secondary_rationale(
    sec: Optional[UpgradeOption],
    rec: Optional[UpgradeOption],
    profile: ConstraintProfile,
) -> str:
    if sec is None:
        return ""
    rec_name = rec.tech_name if rec else "the recommended option"
    return (
        f"{sec.tech_name} would be preferred over {rec_name} when: "
        f"(a) capital cost is the primary decision driver (CAPEX class: {sec.capex_class}), "
        f"(b) process conversion complexity must be minimised (complexity: {sec.complexity}), "
        f"or (c) the constraint profile shifts toward {sec.primary_benefit[:60].lower()}."
    )


def _engineering_summary(
    profile: ConstraintProfile,
    rec: Optional[UpgradeOption],
    sec: Optional[UpgradeOption],
    residual: str,
) -> str:
    pc   = profile.primary_constraint
    rec_name = rec.tech_name if rec else "no clear pathway"
    sec_name = sec.tech_name if sec else None
    conf = profile.data_confidence

    lines = [
        f"The brownfield constraint diagnosis identifies {pc} as the primary upgrade driver.",
    ]
    if profile.secondary_constraints:
        lines.append(
            f"Secondary constraints include: {', '.join(profile.secondary_constraints[:3])}."
        )
    if rec:
        lines.append(
            f"The recommended upgrade pathway is {rec_name} (score {rec.normalised_score:.1f}/10), "
            f"which directly addresses the primary constraint. "
            f"{rec.primary_benefit}"
        )
    if sec:
        lines.append(
            f"The secondary pathway is {sec_name} (score {sec.normalised_score:.1f}/10), "
            f"suitable where {sec.key_limitation[:80].lower()}."
        )
    if residual:
        lines.append(
            "Note: Carbon limitation is active across all biological upgrade pathways — "
            "TN improvement requires a carbon strategy alongside any biological upgrade."
        )
    if conf == "Low":
        lines.append(
            "Data confidence is Low — this ranking should be treated as indicative only. "
            "Detailed site assessment and operating data collection are required before "
            "committing to an upgrade pathway."
        )
    return " ".join(lines)
