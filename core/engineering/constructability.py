"""
core/engineering/constructability.py

Constructability & Staging Engine
===================================
Scores 0–100 based on:
  - Brownfield vs greenfield (site context)
  - Retrofit complexity (existing civil reuse)
  - Temporary works / shutdown requirements
  - Staging options (can the plant be built in stages?)
  - Construction programme duration
  - Local contractor capability

Score directly adjusts implementation_risk in the scoring engine.

References:
  AS/NZS 4360 Risk Management (implementation risk context)
  Metcalf & Eddy 5th Ed, Chapter 11 (Plant Design)
  Water Industry Reference Group — Brownfield Upgrade Guidelines (2021)
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any


# ── Constructability profiles ─────────────────────────────────────────────────
# Per technology: base implementation difficulty 0-100
# 0 = drop-in replacement, 100 = complete greenfield at a live plant
_CONSTRUCTABILITY_PROFILES: Dict[str, Dict[str, float]] = {
    "bnr": {
        "retrofit_complexity":    20,   # standard civil, existing plant layouts familiar
        "temp_works_shutdown":    25,   # phased tankage possible; limited live shutdowns
        "staging_options":        20,   # easily staged: reactor by reactor
        "programme_months":       18,   # typical BNR upgrade
        "contractor_capability":  15,   # well understood by AU contractors
    },
    "granular_sludge": {
        "retrofit_complexity":    45,   # new SBR infrastructure; often different footprint
        "temp_works_shutdown":    50,   # flow balancing tank adds complexity; FBT construction
        "staging_options":        40,   # can stage reactor by reactor but FBT needed upfront
        "programme_months":       24,   # longer: new reactor types, commissioning period
        "contractor_capability":  55,   # limited AU contractor experience with Nereda
    },
    "mabr_bnr": {
        "retrofit_complexity":    50,   # MABR modules inserted into existing aerobic zone
        "temp_works_shutdown":    45,   # aerobic zone needs shutdown to install modules
        "staging_options":        35,   # can retrofit zone by zone
        "programme_months":       20,
        "contractor_capability":  65,   # MABR novel — limited contractor familiarity
    },
    "bnr_mbr": {
        "retrofit_complexity":    55,   # new membrane tanks, significant additional civil
        "temp_works_shutdown":    50,   # significant shutdown for membrane infrastructure
        "staging_options":        45,   # membrane trains can be staged
        "programme_months":       24,
        "contractor_capability":  45,   # MBR contractors available in AU
    },
    "ifas_mbbr": {
        "retrofit_complexity":    30,   # media carriers into existing basins — minimal new civil
        "temp_works_shutdown":    25,   # aeration upgrade + screens; modest shutdown
        "staging_options":        25,   # retrofit zone by zone
        "programme_months":       14,   # typically fastest — reuses existing infrastructure
        "contractor_capability":  35,   # IFAS contractors established in AU
    },
    "anmbr": {
        "retrofit_complexity":    70,
        "temp_works_shutdown":    65,
        "staging_options":        55,
        "programme_months":       30,
        "contractor_capability":  75,
    },
    "mob": {
        "retrofit_complexity":    55,
        "temp_works_shutdown":    50,
        "staging_options":        45,
        "programme_months":       24,
        "contractor_capability":  70,
    },
}

_DEFAULT_PROFILE: Dict[str, float] = {
    "retrofit_complexity": 50,
    "temp_works_shutdown": 50,
    "staging_options":     50,
    "programme_months":    24,
    "contractor_capability": 50,
}

_FACTOR_WEIGHTS: Dict[str, float] = {
    "retrofit_complexity":   0.30,   # biggest driver of implementation risk
    "temp_works_shutdown":   0.25,
    "staging_options":       0.15,   # mitigant — good staging reduces risk
    "programme_months":      0.15,   # longer = more exposure
    "contractor_capability": 0.15,
}

_FACTOR_LABELS: Dict[str, str] = {
    "retrofit_complexity":   "Retrofit / civil complexity",
    "temp_works_shutdown":   "Temporary works & shutdown requirements",
    "staging_options":       "Staging flexibility",
    "programme_months":      "Estimated construction programme",
    "contractor_capability": "Local contractor capability",
}

# Site context adjustments
_BROWNFIELD_PENALTY   = 10.0   # +10 retrofit complexity for constrained brownfield
_GREENFIELD_BONUS     = -15.0  # -15 retrofit for clear greenfield (no existing plant)
_LARGE_PLANT_PENALTY  = 8.0    # temp_works +8 for design flow > 50 MLD
_SMALL_PLANT_BONUS    = -8.0   # -8 programme for flow < 2 MLD


@dataclass
class ConstructabilityFactor:
    name:   str
    score:  float
    weight: float
    note:   str


@dataclass
class ConstructabilityResult:
    scenario_name:          str
    tech_code:              str
    constructability_score: float       # 0-100 (100 = hardest to build)
    factors:                List[ConstructabilityFactor] = field(default_factory=list)
    narrative:              str = ""
    estimated_programme_months: Optional[float] = None
    can_stage:              bool = True
    # Adjustment to implementation_risk
    impl_risk_adjustment:   float = 0.0


    def build_narrative(self) -> None:
        pm = self.estimated_programme_months
        score = self.constructability_score
        if score >= 65:
            level = "High construction complexity"
            outlook = "Significant temporary works and contractor management required."
        elif score >= 40:
            level = "Moderate construction complexity"
            outlook = "Staged construction feasible with standard project management."
        else:
            level = "Low construction complexity"
            outlook = "Straightforward delivery with standard civil contractor."
        stage_txt = "Can be staged" if self.can_stage else "Limited staging options"
        prog_txt  = f"Estimated programme: {pm:.0f} months." if pm else ""
        self.narrative = f"{level} ({score:.0f}/100). {stage_txt}. {prog_txt} {outlook}".strip()


def score_constructability(
    scenario_name:    str,
    tech_code:        str,
    design_flow_mld:  float = 10.0,
    site_type:        str   = "brownfield",   # "brownfield" | "greenfield"
) -> ConstructabilityResult:
    """
    Score constructability for one scenario.

    Parameters
    ----------
    scenario_name   : display name
    tech_code       : technology code
    design_flow_mld : design average flow
    site_type       : "brownfield" or "greenfield"
    """
    profile = dict(_CONSTRUCTABILITY_PROFILES.get(tech_code, _DEFAULT_PROFILE))

    # ── Site-context adjustments ──────────────────────────────────────────
    if site_type == "brownfield":
        profile["retrofit_complexity"] = min(100,
            profile["retrofit_complexity"] + _BROWNFIELD_PENALTY)
    elif site_type == "greenfield":
        profile["retrofit_complexity"] = max(0,
            profile["retrofit_complexity"] + _GREENFIELD_BONUS)

    if design_flow_mld > 50:
        profile["temp_works_shutdown"] = min(100,
            profile["temp_works_shutdown"] + _LARGE_PLANT_PENALTY)
    elif design_flow_mld < 2:
        profile["programme_months"] = max(0,
            profile["programme_months"] + _SMALL_PLANT_BONUS)

    # ── Build factors ─────────────────────────────────────────────────────
    factors   = []
    composite = 0.0
    programme = profile.get("programme_months", 24)

    for key, weight in _FACTOR_WEIGHTS.items():
        score = profile.get(key, 50.0)
        if key == "programme_months":
            # Normalise months to 0-100 (12 months = 0, 36 months = 100)
            score_norm = max(0.0, min(100.0, (score - 12) / 24 * 100))
            score = score_norm
        note = _constructability_note(key, score)
        factors.append(ConstructabilityFactor(
            name   = _FACTOR_LABELS[key],
            score  = score,
            weight = weight,
            note   = note,
        ))
        composite += score * weight

    composite = round(min(100.0, max(0.0, composite)), 1)

    # Can stage?
    staging_score = profile.get("staging_options", 50.0)
    can_stage     = staging_score < 65   # low score = good staging options

    # impl_risk_adjustment: ±10 pts max
    adjustment = (composite - 50.0) * 0.15
    adjustment = round(max(-10.0, min(10.0, adjustment)), 1)

    result = ConstructabilityResult(
        scenario_name           = scenario_name,
        tech_code               = tech_code,
        constructability_score  = composite,
        factors                 = factors,
        estimated_programme_months = programme,
        can_stage               = can_stage,
        impl_risk_adjustment    = adjustment,
    )
    result.build_narrative()
    return result


def _constructability_note(key: str, score: float) -> str:
    level = "Low" if score < 35 else ("Moderate" if score < 65 else "High")
    notes = {
        "retrofit_complexity":   f"{level} — {'standard civil, familiar configurations' if score < 35 else 'significant new infrastructure on live plant' if score >= 65 else 'some new civil works required'}",
        "temp_works_shutdown":   f"{level} — {'minimal shutdowns, phased delivery' if score < 35 else 'major temporary works and process shutdowns' if score >= 65 else 'planned shutdowns during low-demand periods'}",
        "staging_options":       f"{level} — {'highly stageable, flexible delivery' if score < 35 else 'limited staging, mostly one-pass construction' if score >= 65 else 'staged delivery feasible with careful planning'}",
        "programme_months":      f"~{score/100*24+12:.0f} months estimated construction",
        "contractor_capability": f"{level} — {'established local capability' if score < 35 else 'specialist contractors, limited local market' if score >= 65 else 'contractor capability available with vendor support'}",
    }
    return notes.get(key, f"{level}")


def score_all_constructability(
    scenarios: List[Any],
    site_type: str = "brownfield",
) -> Dict[str, ConstructabilityResult]:
    """Score constructability for all scenarios."""
    results = {}
    for s in scenarios:
        tc   = (s.treatment_pathway.technology_sequence[0]
                if s.treatment_pathway and s.treatment_pathway.technology_sequence else "")
        dinp = getattr(s, "domain_inputs", None) or {}
        can_s = getattr(s, "can_stage", None)
        cr = score_constructability(
            scenario_name   = s.scenario_name,
            tech_code       = tc,
            design_flow_mld = dinp.get("design_flow_mld", 10.0),
            site_type       = site_type,
        )
        # Write can_stage back to scenario if not already set
        if can_s is None:
            try: s.can_stage = cr.can_stage
            except Exception: pass
        results[s.scenario_name] = cr
    return results
