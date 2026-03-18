"""
core/decision/scoring_engine.py

Weighted multi-criteria decision scoring for technology options.

Design principles
-----------------
- Compliance gate first: non-compliant options are excluded before scoring
- Normalised 0–100 per criterion (lower-is-better inverted)
- Transparent: every score shows its raw value, normalised value, and weight
- Close-decision guardrail: within 5 points → "close decision" narrative
- Weight profiles: Balanced / Low-risk / Low-carbon / Budget-constrained / Custom

Architecture
------------
ScoringEngine.score(scenarios, weight_profile) -> List[ScoredOption]
  - filters compliant options
  - normalises each criterion across the field
  - applies weights
  - produces ranked ScoredOption list with rationale

References
----------
- WEF Decision Support Tools for Wastewater Treatment (2018)
- WSAA Capital Planning Decision Framework (2021)
- Australian Water Association Technology Assessment Guidelines
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any


# ─────────────────────────────────────────────────────────────────────────────
# WEIGHT PROFILES
# ─────────────────────────────────────────────────────────────────────────────

class WeightProfile(Enum):
    BALANCED       = "Balanced utility planning"
    LOW_RISK       = "Low-risk utility"
    LOW_CARBON     = "Low-carbon / future-focused"
    BUDGET         = "Budget-constrained utility"
    CUSTOM         = "Custom"


# Default weight sets (must sum to 1.0)
WEIGHT_PROFILES: Dict[WeightProfile, Dict[str, float]] = {

    WeightProfile.BALANCED: {
        "lcc":                  0.20,
        "capex":                0.15,
        "specific_cost":       0.0,
        "specific_energy":     0.0,
        "footprint":            0.10,
        "carbon":               0.10,
        "sludge":               0.10,
        "operational_risk":     0.15,
        "implementation_risk":  0.10,
        "regulatory":           0.05,
        "robustness":           0.05,
    },

    WeightProfile.LOW_RISK: {
        "lcc":                  0.15,
        "capex":                0.10,
        "specific_cost":       0.0,
        "specific_energy":     0.0,
        "footprint":            0.05,
        "carbon":               0.05,
        "sludge":               0.10,
        "operational_risk":     0.20,
        "implementation_risk":  0.15,
        "regulatory":           0.10,
        "robustness":           0.10,
    },

    WeightProfile.LOW_CARBON: {
        "lcc":                  0.15,
        "capex":                0.10,
        "specific_cost":       0.0,
        "specific_energy":     0.0,
        "footprint":            0.10,
        "carbon":               0.20,
        "sludge":               0.10,
        "operational_risk":     0.10,
        "implementation_risk":  0.05,
        "regulatory":           0.10,
        "robustness":           0.10,
    },

    WeightProfile.BUDGET: {
        "lcc":                  0.20,
        "capex":                0.25,
        "specific_cost":       0.0,
        "specific_energy":     0.0,
        "footprint":            0.10,
        "carbon":               0.05,
        "sludge":               0.05,
        "operational_risk":     0.10,
        "implementation_risk":  0.10,
        "regulatory":           0.05,
        "robustness":           0.10,
    },
}

CRITERION_LABELS: Dict[str, str] = {
    "lcc":                 "Lifecycle Cost",
    "capex":               "CAPEX",
    "specific_cost":       "Specific Cost ($/kL)",
    "specific_energy":     "Specific Energy",
    "footprint":           "Footprint",
    "carbon":              "Carbon Intensity",
    "sludge":              "Sludge Production",
    "operational_risk":    "Operational Risk",
    "implementation_risk": "Implementation Risk",
    "regulatory":          "Regulatory Confidence",
    "robustness":          "Performance Robustness",
}

# Direction: True = lower raw value is better (inverted to score)
#            False = higher raw value is better
CRITERION_LOWER_IS_BETTER: Dict[str, bool] = {
    "lcc":                 True,
    "capex":               True,
    "specific_cost":       True,
    "specific_energy":     True,
    "footprint":           True,
    "carbon":              True,
    "sludge":              True,
    "operational_risk":    True,
    "implementation_risk": True,
    "regulatory":          False,   # higher regulatory confidence = better
    "robustness":          False,   # higher robustness = better
}


# ─────────────────────────────────────────────────────────────────────────────
# DATA MODELS
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class CriterionScore:
    """Score for one criterion for one scenario."""
    criterion:       str
    label:           str
    raw_value:       float           # actual engineering value (e.g. $M, kgCO2e)
    raw_unit:        str             # display unit
    normalised:      float           # 0–100, higher is always better
    weight:          float           # 0.0–1.0
    weighted_score:  float           # normalised × weight × 100
    lower_is_better: bool


@dataclass
class ScoredOption:
    """Complete weighted decision score for one scenario."""
    scenario_name:      str
    compliance_status:  str          # "Compliant" | "Compliant with intervention" | "Non-compliant"
    is_eligible:        bool         # False if non-compliant
    total_score:        float        # 0–100 weighted sum
    criterion_scores:   Dict[str, CriterionScore] = field(default_factory=dict)
    rank:               int = 0
    excluded_reason:    str = ""     # set if is_eligible=False


@dataclass
class DecisionResult:
    """Full output of the scoring engine for a set of scenarios."""
    weight_profile:     str
    weights:            Dict[str, float]
    scored_options:     List[ScoredOption]       # all options, ranked eligible first
    preferred:          Optional[ScoredOption]
    runner_up:          Optional[ScoredOption]
    excluded:           List[ScoredOption]
    close_decision:     bool                     # True if top-2 within 5 points
    recommendation:     str                      # primary recommendation sentence
    trade_off:          str                      # what the client accepts
    rationale:          List[str]                # bullet reasons preferred won


# ─────────────────────────────────────────────────────────────────────────────
# RAW VALUE EXTRACTION
# ─────────────────────────────────────────────────────────────────────────────

def _extract_raw(scenario: Any, criterion: str) -> tuple[float, str]:
    """
    Extract a raw numeric value and unit from a ScenarioModel.
    Returns (value, unit_string).
    """
    cr  = getattr(scenario, "cost_result",   None)
    car = getattr(scenario, "carbon_result", None)
    rr  = getattr(scenario, "risk_result",   None)
    dso = getattr(scenario, "domain_specific_outputs", None) or {}
    eng = dso.get("engineering_summary", {})
    tp  = dso.get("technology_performance", {})

    flow_mld = eng.get("design_flow_mld") or 1.0
    flow_kl_yr = flow_mld * 1000 * 365

    if criterion == "lcc":
        v = cr.lifecycle_cost_annual / 1e3 if cr else 0
        return v, "k$/yr"

    if criterion == "capex":
        v = cr.capex_total / 1e6 if cr else 0
        return v, "$M"

    if criterion == "footprint":
        # Sum footprint across technologies
        fp = sum(v.get("footprint_m2", 0) or 0 for v in tp.values()) if tp else 0
        v = fp / flow_mld if flow_mld else 0
        return v, "m²/MLD"

    if criterion == "carbon":
        v = (car.net_tco2e_yr * 1000 / flow_kl_yr) if car and flow_kl_yr else 0
        return v, "kgCO2e/kL"

    if criterion == "specific_cost":
        lcc = cr.lifecycle_cost_annual if cr else 0
        v = lcc / (flow_kl_yr) if flow_kl_yr else 0
        return v, "$/kL"

    if criterion == "specific_energy":
        kwh_kl = eng.get("specific_energy_kwh_kl", 0) or 0
        return kwh_kl * 1000, "kWh/ML"

    if criterion == "sludge":
        sludge = eng.get("total_sludge_kgds_day") or 0
        v = sludge / flow_mld if flow_mld else 0
        return v, "kgDS/ML"

    if criterion == "operational_risk":
        v = rr.operational_score if rr else 50
        return v, "/100"

    if criterion == "implementation_risk":
        v = rr.implementation_score if rr else 50
        return v, "/100"

    if criterion == "regulatory":
        # Invert risk score — lower risk = higher regulatory confidence
        v = 100 - (rr.regulatory_score if rr else 50)
        return v, "/100"

    if criterion == "robustness":
        # Performance robustness: inverse of overall risk score
        v = 100 - (rr.overall_score if rr else 50)
        return v, "/100"

    return 0.0, ""


# ─────────────────────────────────────────────────────────────────────────────
# SCORING ENGINE
# ─────────────────────────────────────────────────────────────────────────────

class ScoringEngine:
    """
    Weighted multi-criteria decision scoring engine.

    Usage
    -----
    engine = ScoringEngine()
    result = engine.score(scenarios, weight_profile=WeightProfile.BALANCED)
    """

    def score(
        self,
        scenarios: List[Any],
        weight_profile: WeightProfile = WeightProfile.BALANCED,
        custom_weights: Optional[Dict[str, float]] = None,
        compliance_map: Optional[Dict[str, str]] = None,
    ) -> DecisionResult:
        """
        Score a list of ScenarioModel objects.

        Parameters
        ----------
        scenarios       : list of ScenarioModel (must have cost_result, carbon_result, risk_result)
        weight_profile  : which WeightProfile to use
        custom_weights  : if WeightProfile.CUSTOM, provide weights dict (must sum to ~1.0)
        compliance_map  : {scenario_name: "Compliant"|"Compliant with intervention"|"Non-compliant"}
                          if not provided, all scenarios with cost_result are assumed Compliant
        """
        weights = (
            custom_weights
            if weight_profile == WeightProfile.CUSTOM and custom_weights
            else WEIGHT_PROFILES.get(weight_profile, WEIGHT_PROFILES[WeightProfile.BALANCED])
        )

        # ── Step 1: Classify compliance ──────────────────────────────────────
        compliance = compliance_map or {}

        # ── Step 2: Collect raw values per criterion ──────────────────────────
        raw: Dict[str, Dict[str, float]] = {c: {} for c in weights}
        units: Dict[str, str] = {}

        for s in scenarios:
            if not getattr(s, "cost_result", None):
                continue
            name = s.scenario_name
            for criterion in weights:
                val, unit = _extract_raw(s, criterion)
                raw[criterion][name] = val
                units[criterion] = unit

        # ── Step 3: Normalise each criterion 0–100 ───────────────────────────
        normalised: Dict[str, Dict[str, float]] = {}
        for criterion, values in raw.items():
            if not values:
                normalised[criterion] = {}
                continue
            lo  = min(values.values())
            hi  = max(values.values())
            rng = hi - lo
            lower_better = CRITERION_LOWER_IS_BETTER.get(criterion, True)
            norm = {}
            for name, v in values.items():
                if rng < 1e-9:
                    norm[name] = 100.0   # all equal → all score 100
                elif lower_better:
                    norm[name] = 100.0 * (1 - (v - lo) / rng)   # invert: lower=100
                else:
                    norm[name] = 100.0 * (v - lo) / rng          # higher=100
            normalised[criterion] = norm

        # ── Step 4: Build ScoredOptions ──────────────────────────────────────
        eligible   = []
        ineligible = []

        for s in scenarios:
            if not getattr(s, "cost_result", None):
                continue
            name   = s.scenario_name
            status = compliance.get(name, "Compliant")
            is_ok  = status in ("Compliant", "Compliant with intervention")

            total = 0.0
            crit_scores: Dict[str, CriterionScore] = {}

            for criterion, w in weights.items():
                raw_val  = raw[criterion].get(name, 0)
                norm_val = normalised[criterion].get(name, 0)
                ws       = norm_val * w
                total   += ws
                crit_scores[criterion] = CriterionScore(
                    criterion=criterion,
                    label=CRITERION_LABELS.get(criterion, criterion),
                    raw_value=raw_val,
                    raw_unit=units.get(criterion, ""),
                    normalised=round(norm_val, 1),
                    weight=w,
                    weighted_score=round(ws, 1),
                    lower_is_better=CRITERION_LOWER_IS_BETTER.get(criterion, True),
                )

            opt = ScoredOption(
                scenario_name=name,
                compliance_status=status,
                is_eligible=is_ok,
                total_score=round(total, 1),
                criterion_scores=crit_scores,
                excluded_reason="" if is_ok else f"Excluded: {status}",
            )

            if is_ok:
                eligible.append(opt)
            else:
                ineligible.append(opt)

        # ── Step 5: Rank eligible options ─────────────────────────────────────
        eligible.sort(key=lambda o: o.total_score, reverse=True)
        for i, opt in enumerate(eligible):
            opt.rank = i + 1

        preferred  = eligible[0] if eligible else None
        runner_up  = eligible[1] if len(eligible) > 1 else None
        close      = (
            abs(preferred.total_score - runner_up.total_score) <= 5.0
            if preferred and runner_up else False
        )

        # ── Step 6: Recommendation narrative ──────────────────────────────────
        recommendation, trade_off, rationale = self._build_narrative(
            preferred, runner_up, eligible, close, weights
        )

        return DecisionResult(
            weight_profile=weight_profile.value,
            weights=weights,
            scored_options=eligible + ineligible,
            preferred=preferred,
            runner_up=runner_up,
            excluded=ineligible,
            close_decision=close,
            recommendation=recommendation,
            trade_off=trade_off,
            rationale=rationale,
        )

    # ── Narrative builder ────────────────────────────────────────────────────

    def _build_narrative(
        self,
        preferred:  Optional[ScoredOption],
        runner_up:  Optional[ScoredOption],
        eligible:   List[ScoredOption],
        close:      bool,
        weights:    Dict[str, float],
    ) -> tuple[str, str, List[str]]:

        if not preferred:
            return (
                "No compliant option available. Engineering intervention required before recommendation.",
                "Resolve compliance failures before proceeding to procurement.",
                [],
            )

        pname = preferred.scenario_name

        # What did the preferred option win on?
        rationale = []
        # Find criteria where preferred scores highest in the weighted contribution
        sorted_criteria = sorted(
            preferred.criterion_scores.values(),
            key=lambda c: c.weighted_score, reverse=True
        )
        for cs in sorted_criteria[:3]:   # top 3 contributing criteria
            if cs.weighted_score > 3.0:
                if cs.lower_is_better:
                    rationale.append(
                        f"Lowest {cs.label.lower()} "
                        f"({cs.raw_value:.1f} {cs.raw_unit}) — "
                        f"score {cs.normalised:.0f}/100 (weight {cs.weight*100:.0f}%)"
                    )
                else:
                    rationale.append(
                        f"Highest {cs.label.lower()} "
                        f"({cs.raw_value:.0f}/100) — "
                        f"score {cs.normalised:.0f}/100 (weight {cs.weight*100:.0f}%)"
                    )

        if close and runner_up:
            recommendation = (
                f"Close decision: {pname} is marginally preferred "
                f"({preferred.total_score:.0f} vs {runner_up.total_score:.0f} points). "
                f"Final selection depends on utility risk appetite and site-specific conditions."
            )
            trade_off = (
                f"{runner_up.scenario_name} remains a viable alternative — "
                f"the score difference is within concept-stage uncertainty. "
                f"Recommend parallel concept design validation before technology lock-in."
            )
        elif runner_up:
            gap = preferred.total_score - runner_up.total_score
            recommendation = (
                f"{pname} is the preferred option "
                f"({preferred.total_score:.0f}/100 weighted score, "
                f"{gap:.0f} points ahead of {runner_up.scenario_name})."
            )
            # Trade-off: where does the runner-up score better?
            runner_advantages = [
                cs.label
                for crit, cs in runner_up.criterion_scores.items()
                if cs.normalised > preferred.criterion_scores.get(crit, cs).normalised + 10
            ]
            if runner_advantages:
                trade_off = (
                    f"Selecting {pname} means accepting lower performance on: "
                    f"{', '.join(runner_advantages[:3])}. "
                    f"{runner_up.scenario_name} scores higher on these criteria."
                )
            else:
                trade_off = (
                    f"{pname} outperforms on all major criteria under the selected weight profile. "
                    f"Consider sensitivity testing with alternative weight profiles."
                )
        else:
            recommendation = (
                f"{pname} is the only compliant option and is recommended by default."
            )
            trade_off = "No alternative compliant option available for comparison."

        return recommendation, trade_off, rationale


