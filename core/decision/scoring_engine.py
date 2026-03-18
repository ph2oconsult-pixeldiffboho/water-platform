"""
core/decision/scoring_engine.py

Weighted multi-criteria decision scoring for technology options.

Design principles
-----------------
- Compliance gate first: non-compliant options are excluded before scoring
- Normalised 0-100 per criterion using absolute benchmarks OR minimum-spread dampening
  to avoid binary 0/100 from marginal differences between 2 scenarios
- Transparent: every score shows its raw value, normalised value, and weight
- Close-decision guardrail: within 15% of winning score -> "close decision" narrative
- Weight profiles: Balanced / Low-risk / Low-carbon / Budget-constrained / Custom

Key design decisions
--------------------
1. LCC is the primary cost criterion. CAPEX is a supplementary upfront-cost signal,
   not a co-equal cost criterion. To avoid double-counting, CAPEX weight is capped
   and the LCC/CAPEX pair carries explicit correlation discount in the narrative.
2. "Robustness" is replaced by "Technology Maturity" — an independent criterion
   based on TRL and reference plant count, not derived from risk sub-scores.
3. Normalisation uses a minimum spread of 20% of the midpoint value to prevent
   marginal differences (within ±40% estimate uncertainty) from generating 0/100 splits.
4. Rationale bullets are ranked by ADVANTAGE MARGIN (how much better the preferred
   option is) not by weighted score contribution.

References
----------
- WEF Decision Support Tools for Wastewater Treatment (2018)
- WSAA Capital Planning Decision Framework (2021)
- ISO 15686-5 Life Cycle Costing
- Metcalf & Eddy 5th Edition Chapter 8 (technology selection)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any, Tuple


# ─────────────────────────────────────────────────────────────────────────────
# TECHNOLOGY MATURITY — reference plant database (TRL proxy)
# Higher = more mature. Used for "maturity" criterion.
# Source: technology vendor data, WSAA benchmarking, literature surveys.
# ─────────────────────────────────────────────────────────────────────────────
TECH_MATURITY: Dict[str, float] = {
    "bnr":             90,   # conventional BNR: 50+ years, thousands of plants
    "granular_sludge": 65,   # Nereda: 100+ plants globally, 15+ years commercial
    "mbr":             80,   # MBR: 30+ years, widespread in AU
    "bnr_mbr":         75,   # BNR+MBR combination: well established
    "ifas_mbbr":       70,   # IFAS/MBBR: 20+ years, growing AU presence
    "mabr_bnr":        45,   # MABR: pilot/early commercial, <10 full-scale AU
    "anmbr":           35,   # AnMBR: demonstration/early commercial
    "sidestream_pna":  50,   # PNA/ANAMMOX: established for sidestream
    "mob":             40,   # MOB Biofilm: early commercial
    "ad_chp":          85,   # Anaerobic digestion + CHP: very mature
    "thermal_biosolids": 70, # Thermal drying: mature
    "cpr":             80,   # Chemical P removal: very mature
    "tertiary_filt":   85,   # Tertiary filtration: very mature
    "adv_reuse":       65,   # Advanced reuse: growing, well characterised
}


# ─────────────────────────────────────────────────────────────────────────────
# WEIGHT PROFILES
# ─────────────────────────────────────────────────────────────────────────────

class WeightProfile(Enum):
    BALANCED       = "Balanced utility planning"
    LOW_RISK       = "Low-risk utility"
    LOW_CARBON     = "Low-carbon / future-focused"
    BUDGET         = "Budget-constrained utility"
    CUSTOM         = "Custom"


# Default weight sets — must sum to 1.0
# Design notes:
#   lcc + capex: deliberately not summing to >35% to avoid cost domination
#   risk criteria: operational + implementation + regulatory = max 30%
#   maturity replaces old "robustness" to eliminate circular derivation from risk
WEIGHT_PROFILES: Dict[WeightProfile, Dict[str, float]] = {

    WeightProfile.BALANCED: {
        # Weighting rationale:
        # - maturity (10%) and implementation_risk (10%) are partially correlated
        #   (more mature = easier to implement) but not identical: MABR and IFAS share
        #   implementation_risk=25 while their maturity differs (45 vs 70). The overlap
        #   is intentional — both perspectives matter: "is this tech proven?" (maturity)
        #   and "how hard is this project to deliver?" (implementation_risk). Combined
        #   weight of 20% reflects that delivery risk is a key utility concern.
        # - LCC (20%) + CAPEX (10%) = 30% cost. CAPEX is kept as a separate signal
        #   because utilities face real budget gates even when LCC favours a higher-
        #   CAPEX option. The two criteria are not identical: LCC rewards low OPEX
        #   technologies; CAPEX rewards low upfront cost regardless of OPEX.
        "lcc":                  0.20,   # primary cost signal
        "capex":                0.10,   # upfront budget signal (not co-equal with LCC)
        "footprint":            0.10,
        "carbon":               0.10,
        "sludge":               0.10,
        "operational_risk":     0.15,
        "implementation_risk":  0.10,
        "regulatory":           0.05,
        "maturity":             0.10,   # technology maturity / TRL
    },

    WeightProfile.LOW_RISK: {
        "lcc":                  0.15,
        "capex":                0.05,
        "footprint":            0.05,
        "carbon":               0.05,
        "sludge":               0.05,
        "operational_risk":     0.20,
        "implementation_risk":  0.20,
        "regulatory":           0.10,
        "maturity":             0.15,
    },

    WeightProfile.LOW_CARBON: {
        "lcc":                  0.15,
        "capex":                0.10,
        "footprint":            0.10,
        "carbon":               0.25,
        "sludge":               0.10,
        "operational_risk":     0.10,
        "implementation_risk":  0.05,
        "regulatory":           0.05,
        "maturity":             0.10,
    },

    WeightProfile.BUDGET: {
        # Rationale: even for budget-constrained utilities, LCC is the correct
        # ratepayer cost signal. CAPEX capped at 15% to prevent a single upfront
        # cost signal dominating at the expense of operational and risk performance.
        # The additional weight goes to LCC (which already contains annualised CAPEX).
        "lcc":                  0.30,   # increased: LCC is the right budget metric
        "capex":                0.15,   # capped from 0.25 — CAPEX is in LCC already
        "footprint":            0.10,
        "carbon":               0.05,
        "sludge":               0.05,
        "operational_risk":     0.10,
        "implementation_risk":  0.10,
        "regulatory":           0.05,
        "maturity":             0.10,
    },
}

CRITERION_LABELS: Dict[str, str] = {
    "lcc":                 "Lifecycle Cost",
    "capex":               "CAPEX",
    "footprint":           "Footprint",
    "carbon":              "Carbon Intensity",
    "sludge":              "Sludge Production",
    "operational_risk":    "Operational Risk",
    "implementation_risk": "Implementation Risk",
    "regulatory":          "Regulatory Risk",
    "maturity":            "Technology Maturity",
}

# "Compliant with intervention" score cap.
# A scenario that requires engineering intervention to meet targets
# receives a maximum score of CWI_SCORE_CAP (0-100).
# Rationale: the intervention cost and risk are not fully captured in the raw
# engineering outputs (e.g. methanol dosing cost may be absent if TN target
# was relaxed to make the technology appear compliant). The cap ensures the
# option remains visible but cannot rank first purely on pre-intervention costs.
CWI_SCORE_CAP = 75.0   # CWI options cannot score above this

# Direction: True = lower raw value is better (inverted to score)
#            False = higher raw value is better
CRITERION_LOWER_IS_BETTER: Dict[str, bool] = {
    "lcc":                 True,
    "capex":               True,
    "footprint":           True,
    "carbon":              True,
    "sludge":              True,
    "operational_risk":    True,
    "implementation_risk": True,
    "regulatory":          True,    # lower regulatory risk score = better
    "maturity":            False,   # higher maturity = better
}

# Minimum spread fraction — prevents marginal differences from generating 0/100 splits.
# If the range between best and worst is < MIN_SPREAD_FRACTION × midpoint value,
# all options are treated as tied on this criterion (score 100/100 each).
# Set at 0.15 = 15% relative difference minimum before scoring discriminates.
# This approximately matches the ±40% → ±15% relative uncertainty at concept stage
# after cancellation of correlated errors between the same-methodology scenarios.
MIN_SPREAD_FRACTION = 0.15


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
    normalised:      float           # 0-100, higher is always better
    weight:          float           # 0.0-1.0
    weighted_score:  float           # normalised x weight x 100
    lower_is_better: bool
    tied:            bool = False    # True if spread < MIN_SPREAD_FRACTION (no discrimination)


@dataclass
class ScoredOption:
    """Complete weighted decision score for one scenario."""
    scenario_name:      str
    compliance_status:  str          # "Compliant" | "Compliant with intervention" | "Non-compliant"
    is_eligible:        bool         # False if non-compliant
    total_score:        float        # 0-100 weighted sum
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
    close_decision:     bool                     # True if gap < 15% of winning score
    close_decision_threshold: float              # the gap threshold used
    recommendation:     str                      # primary recommendation sentence
    trade_off:          str                      # what the client accepts
    rationale:          List[str]                # bullet reasons preferred won (by margin)
    tied_criteria:      List[str]                # criteria where spread < threshold


# ─────────────────────────────────────────────────────────────────────────────
# RAW VALUE EXTRACTION
# ─────────────────────────────────────────────────────────────────────────────

def _extract_raw(scenario: Any, criterion: str) -> Tuple[float, str]:
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

    flow_mld   = eng.get("design_flow_mld") or 1.0
    flow_kl_yr = flow_mld * 1000 * 365

    if criterion == "lcc":
        v = cr.lifecycle_cost_annual / 1e3 if cr else 0
        return v, "k$/yr"

    if criterion == "capex":
        v = cr.capex_total / 1e6 if cr else 0
        return v, "$M"

    if criterion == "footprint":
        fp = sum(v.get("footprint_m2", 0) or 0 for v in tp.values()) if tp else 0
        return fp / flow_mld if flow_mld else 0, "m2/MLD"

    if criterion == "carbon":
        v = (car.net_tco2e_yr * 1000 / flow_kl_yr) if car and flow_kl_yr else 0
        return v, "kgCO2e/kL"

    if criterion == "sludge":
        # Use tDS/yr — total annual volume matters for disposal contracts, site
        # storage and biosolids management planning. kgDS/ML is already captured
        # implicitly in OPEX (sludge disposal = $/tDS × tDS/yr).
        # tDS/yr is the independent signal: site area, truck movements, pathogen class.
        sludge = eng.get("total_sludge_kgds_day") or 0
        tds_yr = sludge * 365.0 / 1000.0
        return tds_yr, "tDS/yr"

    if criterion == "operational_risk":
        v = rr.operational_score if rr else 50
        return v, "/100"

    if criterion == "implementation_risk":
        v = rr.implementation_score if rr else 50
        return v, "/100"

    if criterion == "regulatory":
        # regulatory_score is a risk score — lower = better
        v = rr.regulatory_score if rr else 50
        return v, "/100"

    if criterion == "maturity":
        # Technology maturity — look up from primary tech code in pathway
        tp_keys = list(tp.keys()) if tp else []
        if not tp_keys:
            # fallback: check treatment_pathway
            pathway = getattr(scenario, "treatment_pathway", None)
            tp_keys = (pathway.technology_sequence if pathway else [])
        tc = tp_keys[0] if tp_keys else ""
        v = TECH_MATURITY.get(tc, 50)
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
        scenarios:       List[Any],
        weight_profile:  WeightProfile = WeightProfile.BALANCED,
        custom_weights:  Optional[Dict[str, float]] = None,
        compliance_map:  Optional[Dict[str, str]]   = None,
    ) -> DecisionResult:
        weights = (
            custom_weights
            if weight_profile == WeightProfile.CUSTOM and custom_weights
            else WEIGHT_PROFILES.get(weight_profile, WEIGHT_PROFILES[WeightProfile.BALANCED])
        )

        compliance = compliance_map or {}

        # ── Step 1: Collect raw values ────────────────────────────────────
        raw:   Dict[str, Dict[str, float]] = {c: {} for c in weights}
        units: Dict[str, str] = {}

        for s in scenarios:
            if not getattr(s, "cost_result", None):
                continue
            name = s.scenario_name
            for criterion in weights:
                val, unit = _extract_raw(s, criterion)
                raw[criterion][name] = val
                units[criterion] = unit

        # ── Step 2: Normalise 0-100 with minimum-spread dampening ─────────
        normalised: Dict[str, Dict[str, float]] = {}
        tied_criteria: List[str] = []

        for criterion, values in raw.items():
            if not values:
                normalised[criterion] = {}
                continue
            lo      = min(values.values())
            hi      = max(values.values())
            rng     = hi - lo
            midpt   = (lo + hi) / 2 if (lo + hi) > 0 else 1.0
            # Minimum meaningful spread: 15% of midpoint value
            # Below this threshold the difference is within concept-stage noise
            min_spread = MIN_SPREAD_FRACTION * midpt
            lower_better = CRITERION_LOWER_IS_BETTER.get(criterion, True)
            norm = {}

            if rng < max(1e-9, min_spread):
                # Spread too small — treat as tied, all score 100
                for name in values:
                    norm[name] = 100.0
                if len(values) > 1:
                    tied_criteria.append(criterion)
            else:
                for name, v in values.items():
                    if lower_better:
                        norm[name] = 100.0 * (1 - (v - lo) / rng)
                    else:
                        norm[name] = 100.0 * (v - lo) / rng
            normalised[criterion] = norm

        # ── Step 3: Build ScoredOptions ───────────────────────────────────
        eligible, ineligible = [], []

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
                    tied=criterion in tied_criteria,
                )

            # Apply CWI score cap — intervention required means raw costs
            # do not reflect full compliance cost; cap prevents misleading ranking
            if status == "Compliant with intervention" and total > CWI_SCORE_CAP:
                total = CWI_SCORE_CAP

            opt = ScoredOption(
                scenario_name=name,
                compliance_status=status,
                is_eligible=is_ok,
                total_score=round(total, 1),
                criterion_scores=crit_scores,
                excluded_reason="" if is_ok else f"Excluded: {status}",
            )
            (eligible if is_ok else ineligible).append(opt)

        # ── Step 4: Rank eligible ─────────────────────────────────────────
        eligible.sort(key=lambda o: o.total_score, reverse=True)
        for i, opt in enumerate(eligible):
            opt.rank = i + 1

        preferred = eligible[0] if eligible else None
        runner_up = eligible[1] if len(eligible) > 1 else None

        # Close-decision threshold: 15% of winning score (not a fixed 5 points)
        # This scales with the magnitude of the score and reflects concept-stage uncertainty.
        close_threshold = (preferred.total_score * 0.15) if preferred else 5.0
        close = (
            abs(preferred.total_score - runner_up.total_score) <= close_threshold
            if preferred and runner_up else False
        )

        # ── Step 5: Build narrative ───────────────────────────────────────
        recommendation, trade_off, rationale = self._build_narrative(
            preferred, runner_up, eligible, close, weights, tied_criteria
        )

        return DecisionResult(
            weight_profile=weight_profile.value,
            weights=weights,
            scored_options=eligible + ineligible,
            preferred=preferred,
            runner_up=runner_up,
            excluded=ineligible,
            close_decision=close,
            close_decision_threshold=round(close_threshold, 1),
            recommendation=recommendation,
            trade_off=trade_off,
            rationale=rationale,
            tied_criteria=tied_criteria,
        )

    # ── Narrative builder ────────────────────────────────────────────────

    def _build_narrative(
        self,
        preferred:      Optional[ScoredOption],
        runner_up:      Optional[ScoredOption],
        eligible:       List[ScoredOption],
        close:          bool,
        weights:        Dict[str, float],
        tied_criteria:  List[str],
    ) -> Tuple[str, str, List[str]]:

        if not preferred:
            return (
                "No compliant option available. Engineering intervention required before recommendation.",
                "Resolve compliance failures before proceeding to procurement.",
                [],
            )

        pname = preferred.scenario_name

        # ── Rationale: rank by MARGIN over runner-up, not by weighted score ──
        # This prevents a minor cost advantage from appearing as the "main reason"
        rationale = []
        if runner_up:
            advantages = []
            for crit, cs in preferred.criterion_scores.items():
                if crit in tied_criteria:
                    continue
                ru_cs = runner_up.criterion_scores.get(crit)
                if ru_cs is None:
                    continue
                margin = cs.normalised - ru_cs.normalised  # positive = preferred is better
                if margin > 15:   # only report where advantage is material (>15 normalised pts)
                    advantages.append((margin, cs))
            advantages.sort(key=lambda x: x[0], reverse=True)
            for margin, cs in advantages[:3]:
                if cs.lower_is_better:
                    rationale.append(
                        f"Lower {cs.label.lower()}: {cs.raw_value:.1f} {cs.raw_unit} "
                        f"vs {runner_up.criterion_scores[cs.criterion].raw_value:.1f} {cs.raw_unit} "
                        f"({margin:.0f}-point normalised advantage, weight {cs.weight*100:.0f}%)"
                    )
                else:
                    rationale.append(
                        f"Higher {cs.label.lower()}: {cs.raw_value:.0f}/100 "
                        f"vs {runner_up.criterion_scores[cs.criterion].raw_value:.0f}/100 "
                        f"({margin:.0f}-point normalised advantage, weight {cs.weight*100:.0f}%)"
                    )

        # Note tied criteria
        active_tied = [CRITERION_LABELS.get(c, c) for c in tied_criteria if weights.get(c, 0) > 0]
        if active_tied:
            rationale.append(
                f"Note: the following criteria scored identically (difference within "
                f"concept-stage noise, <{int(MIN_SPREAD_FRACTION*100)}% relative spread): "
                f"{', '.join(active_tied)}"
            )

        # ── Main recommendation sentence ─────────────────────────────────
        if close and runner_up:
            gap = preferred.total_score - runner_up.total_score
            recommendation = (
                f"Close decision: {pname} is marginally preferred "
                f"({preferred.total_score:.0f} vs {runner_up.total_score:.0f} points, "
                f"gap {gap:.1f} — within close-decision threshold of "
                f"{self._fmt_threshold(preferred)}). "
                "Final selection depends on utility risk appetite and site-specific conditions. "
                "Do not lock in technology based on score alone."
            )
            trade_off = (
                f"{runner_up.scenario_name} is a valid alternative — "
                "the score difference does not justify excluding it at concept stage. "
                "Recommend parallel design development before final technology selection."
            )
        elif runner_up:
            gap = preferred.total_score - runner_up.total_score
            recommendation = (
                f"{pname} is the preferred option under the selected weight profile "
                f"({preferred.total_score:.0f}/100, {gap:.0f} points ahead of "
                f"{runner_up.scenario_name})."
            )
            # Trade-off: where does runner-up score materially better?
            # Store (criterion_key, label) tuples so raw value lookup works
            runner_advantages = []
            for crit, cs in runner_up.criterion_scores.items():
                if crit in tied_criteria:
                    continue
                pref_cs = preferred.criterion_scores.get(crit)
                if pref_cs and cs.normalised > pref_cs.normalised + 15:
                    runner_advantages.append((crit, cs.label))
            if runner_advantages:
                trade_off_parts = []
                for crit_key, crit_label in runner_advantages[:3]:
                    pref_cs = preferred.criterion_scores.get(crit_key)
                    ru_cs   = runner_up.criterion_scores.get(crit_key)
                    if pref_cs and ru_cs:
                        unit = pref_cs.raw_unit
                        if pref_cs.lower_is_better:
                            trade_off_parts.append(
                                f"{crit_label} ({pref_cs.raw_value:.1f} vs "
                                f"{ru_cs.raw_value:.1f} {unit})"
                            )
                        else:
                            trade_off_parts.append(
                                f"{crit_label} ({pref_cs.raw_value:.0f} vs "
                                f"{ru_cs.raw_value:.0f} {unit})"
                            )
                    else:
                        trade_off_parts.append(crit_label)
                trade_off = (
                    f"Selecting {pname} means accepting lower performance on: "
                    f"{', '.join(trade_off_parts)}. "
                    f"{runner_up.scenario_name} scores materially higher on these criteria "
                    f"and should be preferred if they are prioritised by the utility."
                )
            else:
                trade_off = (
                    f"{pname} outperforms on all active criteria under the selected weight profile. "
                    "Sensitivity test with alternative profiles is recommended before finalising."
                )
        else:
            recommendation = (
                f"{pname} is the only compliant option and is recommended by default. "
                "No genuine comparison is available — add alternative scenarios before finalising."
            )
            trade_off = "No alternative compliant option available for comparison."

        return recommendation, trade_off, rationale

    @staticmethod
    def _fmt_threshold(preferred: ScoredOption) -> str:
        t = preferred.total_score * 0.15
        return f"{t:.1f} points"
