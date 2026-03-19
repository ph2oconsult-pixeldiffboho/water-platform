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
    "granular_sludge": 72,   # Nereda: 100+ plants globally, 15+ years commercial, AU reference sites
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
        # Note: carbon intensity and implementation_risk are anti-correlated (r=-0.95).
        # Lower-carbon technologies tend to be newer and harder to deliver.
        # This profile intentionally accepts higher delivery risk in exchange for
        # lower carbon — that tension is correct engineering policy.
        "lcc":                  0.15,
        "capex":                0.10,
        "footprint":            0.10,
        "carbon":               0.25,
        "sludge":               0.10,   # restored from headroom redistribution
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
    # "headroom" omitted from display: always 0.0 under current model
    # (biological models target exactly the specified TN, no margin below).
    # Extraction function kept for future use. Remove this comment when
    # models return conservative effluent predictions.
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

# Normalised score clamping — prevents 0/100 binary extremes that mislead clients.
# No technology scores "perfect" (100) or "completely unacceptable" (0) on any criterion
# at concept stage — these represent unfounded certainty.
# Range 20–85: reflects the practical range of concept-level discrimination.
SCORE_CLAMP_MIN = 20.0
SCORE_CLAMP_MAX = 85.0


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
    correlated_pairs:   List[str] = field(default_factory=list)  # high-correlation warnings
    below_uncertainty:  List[str] = field(default_factory=list)  # criteria within ±40% noise
    result_invariant:   bool = False   # True if same winner across all standard profiles
    binary_comparison:  bool = False   # True if only 2 scenarios — scores are 0/100 binary


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
        sludge = eng.get("total_sludge_kgds_day") or 0
        tds_yr = sludge * 365.0 / 1000.0
        return tds_yr, "tDS/yr"

    if criterion == "headroom":
        # Effluent TN headroom: margin below TN target only.
        # TN is the operationally critical parameter — it reflects biological
        # process stability under load variation, temperature, and influent fluctuation.
        # TP headroom via chemical dosing is a procurement signal, not a robustness signal.
        # Higher TN headroom = more buffer before licence exceedance.
        # Range 0-100%. A process achieving TN=5 against TN=10 target scores 50%.
        dinp = getattr(scenario, "domain_inputs", None) or {}
        tn_target = dinp.get("effluent_tn_mg_l", 10.0) or 10.0
        margins = []
        for tech_perf in tp.values():
            tn_actual = tech_perf.get("effluent_tn_mg_l")
            if tn_actual is not None and tn_actual < tn_target:
                margins.append((tn_target - tn_actual) / tn_target * 100)
        v = margins[0] if margins else 0.0
        return round(v, 1), "% TN margin"

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
                # Spread too small — treat as tied, score midpoint
                for name in values:
                    norm[name] = (SCORE_CLAMP_MIN + SCORE_CLAMP_MAX) / 2  # midpoint for ties
                if len(values) > 1:
                    tied_criteria.append(criterion)
            else:
                for name, v in values.items():
                    if lower_better:
                        norm[name] = max(SCORE_CLAMP_MIN, min(SCORE_CLAMP_MAX, 100.0 * (1 - (v - lo) / rng)))
                    else:
                        norm[name] = max(SCORE_CLAMP_MIN, min(SCORE_CLAMP_MAX, 100.0 * (v - lo) / rng))
            normalised[criterion] = norm

        # ── Post-normalisation: maturity-adjusted implementation floor ─────────
        # Technologies with high maturity (≥65) have demonstrated global implementation.
        # The normalised implementation score should not drop below 30 purely because
        # a more conventional option is in the same comparison field.
        if "implementation_risk" in normalised and "maturity" in normalised:
            for name in list(normalised["implementation_risk"].keys()):
                mat_score = normalised["maturity"].get(name, 0)
                if mat_score >= 50:   # materially mature technology
                    floor = 20 + (mat_score - 50) * 0.4   # scales from 20 at mat=50 to 36 at mat=90
                    floor = min(floor, 40.0)               # never exceed 40 as a floor
                    normalised["implementation_risk"][name] = max(
                        normalised["implementation_risk"][name], floor
                    )

        # ── Step 2b: Detect correlation and uncertainty issues ──────────────
        # IMPORTANT: correlation detection requires >= 3 scenarios.
        # With exactly 2 scenarios, any two criteria correlate at r=+/-1.0
        # by mathematical necessity (two points always fit a line).
        # Generating 36 warnings for a standard 2-option comparison produces noise
        # that drowns the signal — suppress and use a single structural note instead.
        correlated_pairs: List[str] = []
        below_uncertainty: List[str] = []
        n_eligible_scenarios = sum(1 for s in scenarios
                                   if getattr(s, "cost_result", None))
        binary_comparison = (n_eligible_scenarios == 2)

        if n_eligible_scenarios >= 3:
            crit_keys_list = [c for c in weights if raw.get(c)]
            for i, c1 in enumerate(crit_keys_list):
                vals1 = list(raw[c1].values())
                if len(vals1) < 3: continue
                m1 = sum(vals1)/len(vals1)
                lo1, hi1 = min(vals1), max(vals1)
                mid1 = (lo1+hi1)/2 if (lo1+hi1) > 0 else 1
                if mid1 > 0 and (hi1-lo1)/mid1 < 0.40 and c1 not in below_uncertainty:
                    below_uncertainty.append(c1)
                for j, c2 in enumerate(crit_keys_list):
                    if j <= i: continue
                    vals2 = list(raw[c2].values())
                    if len(vals2) < 3: continue
                    m2 = sum(vals2)/len(vals2)
                    num = sum((vals1[k]-m1)*(vals2[k]-m2) for k in range(len(vals1)))
                    d1  = sum((v-m1)**2 for v in vals1)
                    d2  = sum((v-m2)**2 for v in vals2)
                    r_val = num/(d1*d2)**0.5 if d1*d2 > 0 else 0
                    if abs(r_val) > 0.85:
                        w1 = weights.get(c1, 0)
                        w2 = weights.get(c2, 0)
                        label1 = CRITERION_LABELS.get(c1, c1)
                        label2 = CRITERION_LABELS.get(c2, c2)
                        correlated_pairs.append(
                            f"{label1} x {label2}: r={r_val:+.2f}, "
                            f"combined weight={(w1+w2)*100:.0f}% - "
                            "these criteria may measure the same underlying property"
                        )

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

        # ── Step 4: Apply CWI ranking constraint then rank ───────────────
        # CWI options must rank BELOW fully compliant options.
        # Compliant options whose targets require intervention are not yet meeting
        # the licence — their cost advantage is pre-intervention and therefore
        # overstated. Cap CWI score to just below the lowest fully-compliant score.
        compliant_scores = [o.total_score for o in eligible
                            if o.compliance_status == "Compliant"]
        if compliant_scores:
            lowest_compliant = min(compliant_scores)
            effective_cwi_cap = min(CWI_SCORE_CAP, lowest_compliant - 1.0)
            for opt in eligible:
                if (opt.compliance_status == "Compliant with intervention"
                        and opt.total_score >= lowest_compliant):
                    opt.total_score = round(max(0.0, effective_cwi_cap), 1)

        eligible.sort(key=lambda o: o.total_score, reverse=True)
        for i, opt in enumerate(eligible):
            opt.rank = i + 1

        preferred = eligible[0] if eligible else None
        runner_up = eligible[1] if len(eligible) > 1 else None

        # Close-decision threshold: 15% of winning score (not a fixed 5 points)
        # This scales with the magnitude of the score and reflects concept-stage uncertainty.
        # Minimum threshold of 2 points prevents any non-zero gap from declaring close.
        # Minimum 8 points regardless of winning score magnitude.
        # Prevents very low scoring comparisons (e.g. 50 vs 43) from being
        # labelled "not close" when the gap is a small fraction of the score.
        close_threshold = max(8.0, preferred.total_score * 0.15) if preferred else 8.0
        gap = abs(preferred.total_score - runner_up.total_score) if (preferred and runner_up) else 0
        exact_tie = (gap == 0.0)   # gap = 0 means genuinely identical scores
        close = (gap <= close_threshold) if (preferred and runner_up) else False

        # ── Step 5: Build narrative ───────────────────────────────────────
        recommendation, trade_off, rationale = self._build_narrative(
            preferred, runner_up, eligible, close, weights, tied_criteria,
            binary_comparison=binary_comparison,
            below_uncertainty=below_uncertainty,
            weight_profile_name=weight_profile.value if hasattr(weight_profile, "value") else str(weight_profile),
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
            correlated_pairs=correlated_pairs,
            below_uncertainty=below_uncertainty,
            binary_comparison=binary_comparison,
        )

    # ── Narrative builder ────────────────────────────────────────────────

    def _build_narrative(
        self,
        preferred:          Optional[ScoredOption],
        runner_up:          Optional[ScoredOption],
        eligible:           List[ScoredOption],
        close:              bool,
        weights:            Dict[str, float],
        tied_criteria:      List[str],
        binary_comparison:  bool = False,
        below_uncertainty:  Optional[List[str]] = None,
        weight_profile_name: str = "selected",
    ) -> Tuple[str, str, List[str]]:

        if not preferred:
            return (
                "No compliant option available. Engineering intervention required before recommendation.",
                "Resolve compliance failures before proceeding to procurement.",
                [],
            )

        pname = preferred.scenario_name
        # Low-score disclosure: flag any eligible option scoring < 30/100
        low_score_notes = []
        for opt in eligible:
            if opt.total_score < 30 and opt != preferred:
                # Identify primary reason for low score
                worst_crit = min(
                    (cs for cs in opt.criterion_scores.values()
                     if cs.weight > 0 and not cs.tied),
                    key=lambda cs: cs.normalised,
                    default=None
                )
                reason = (f"principally due to {worst_crit.label.lower()} "
                          f"({worst_crit.raw_value:.0f} {worst_crit.raw_unit})"
                          if worst_crit else "across multiple criteria")
                low_score_notes.append(
                    f"Note: {opt.scenario_name} scores {opt.total_score:.0f}/100 "
                    f"under this profile, {reason}. "
                    "This option is included for completeness but is not "
                    "competitively ranked under these weights."
                )

        # Structural note for binary comparisons
        binary_note = (
            " (Two-scenario comparison: criterion scores are binary 0/100 -- "
            "results show which option wins each criterion, not by how much. "
            "Scores would differ if additional scenarios were included.)"
            if binary_comparison else ""
        )

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
                ru_cs = runner_up.criterion_scores[cs.criterion]
                raw_diff = abs(cs.raw_value - ru_cs.raw_value)
                if cs.lower_is_better:
                    # Report raw difference, not normalised advantage
                    # "100-point normalised advantage" is technically correct but
                    # overstates the margin to a non-technical client.
                    pct_diff = raw_diff / ru_cs.raw_value * 100 if ru_cs.raw_value > 0 else 0
                    diff_str = (f"{raw_diff:.1f} {cs.raw_unit} lower"
                                f" ({pct_diff:.0f}% better)")
                    rationale.append(
                        f"Lower {cs.label.lower()}: {cs.raw_value:.1f} {cs.raw_unit} "
                        f"vs {ru_cs.raw_value:.1f} {cs.raw_unit} "
                        f"(difference: {diff_str}, weight {cs.weight*100:.0f}%)"
                    )
                else:
                    raw_diff_pts = cs.raw_value - ru_cs.raw_value
                    rationale.append(
                        f"Higher {cs.label.lower()}: {cs.raw_value:.0f}/100 "
                        f"vs {ru_cs.raw_value:.0f}/100 "
                        f"(difference: {abs(raw_diff_pts):.0f} points, weight {cs.weight*100:.0f}%)"
                    )

        # Append low-score disclosure notes to rationale
        rationale.extend(low_score_notes)

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
            exact_tie = (gap == 0.0)
            if exact_tie:
                recommendation = (
                    f"No preference: {pname} and {runner_up.scenario_name} score identically "
                    f"({preferred.total_score:.0f}/100 each) under this weight profile. "
                    "Selection must be based on site-specific factors, not this scoring. "
                    "Consider a site investigation or sensitivity test with additional criteria."
                )
            else:
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
            # Check if significant weight sits on below-uncertainty criteria
            # Use below_uncertainty (spread < 40% of midpoint) for the uncertainty note.
            # Do NOT use tied_criteria (spread < 15%) — tied means the two options are
            # similar on this criterion, which is different from the measurement being uncertain.
            _below_unc = below_uncertainty or []
            below_unc_weight = sum(weights.get(c, 0) for c in _below_unc)
            tied_weight = sum(weights.get(c, 0) for c in tied_criteria)
            uncertainty_note = ""
            if below_unc_weight >= 0.60:
                uncertainty_note = (
                    f" CAUTION: {below_unc_weight*100:.0f}% of the score weight falls on criteria "
                    "within concept-stage estimate uncertainty. The score margin cannot "
                    "reliably discriminate between these options under current inputs. "
                    "Consider site investigation or additional scenario differentiation "
                    "before using this score to select a technology."
                )
            elif below_unc_weight >= 0.25:
                uncertainty_note = (
                    f" Note: {below_unc_weight*100:.0f}% of the score weight falls on criteria "
                    "within concept-stage estimate uncertainty -- treat the score margin as "
                    "indicative, not definitive."
                )
            # Build structured recommendation: decision / basis / caveats separated
            tied_labels = [CRITERION_LABELS.get(c,c) for c in tied_criteria
                           if weights.get(c,0) > 0]
            tied_note = ""
            if tied_labels:
                tied_note = (
                    f" The following criteria are indistinguishable between the options "
                    f"at concept stage: {', '.join(tied_labels)}."
                )
            recommendation = (
                f"{pname} is preferred under the {weight_profile_name} profile "
                f"({preferred.total_score:.0f}/100 vs {runner_up.total_score:.0f}/100)."
                f"{tied_note}"
                f"{uncertainty_note}"
                f"{binary_note}"
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
                        # Only report trade-off if raw difference >= 5% of scale midpoint
                    # Prevents reporting "Regulatory Risk (26.7 vs 24.0)" as a material trade-off
                    raw_diff = abs(pref_cs.raw_value - ru_cs.raw_value)
                    raw_mid  = (pref_cs.raw_value + ru_cs.raw_value) / 2 if (pref_cs.raw_value + ru_cs.raw_value) > 0 else 1
                    if raw_diff / raw_mid < 0.05:
                        trade_off_parts.append(f"{crit_label} (marginal difference — within estimate noise)")
                    elif pref_cs.lower_is_better:
                        diff = raw_diff
                        fmt = ".3f" if diff < 0.05 else ".2f" if diff < 0.5 else ".1f"
                        trade_off_parts.append(
                            f"{crit_label} "
                            f"({pref_cs.raw_value:{fmt}} vs "
                            f"{ru_cs.raw_value:{fmt}} {unit})"
                        )
                    else:
                        trade_off_parts.append(
                            f"{crit_label} ({pref_cs.raw_value:.0f} vs "
                            f"{ru_cs.raw_value:.0f} {unit})"
                        )
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
