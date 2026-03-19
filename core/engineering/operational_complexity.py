"""
core/engineering/operational_complexity.py

Operational Complexity Engine
==============================
Scores 0–100 based on:
  - Number of active control loops
  - Automation dependency (fail-safe vs fail-unsafe modes)
  - Process sensitivity (temperature, DO, SRT)
  - Operator skill requirement
  - Failure consequence magnitude

Output feeds directly into the operational_risk criterion in the scoring engine.

References:
  WEF MOP 35 — Operational Risk Assessment
  IWA Specialist Group on Activated Sludge Process Design
  Metcalf & Eddy 5th Ed, Chapter 10
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any


@dataclass
class ComplexityFactor:
    name:         str
    score:        float    # 0 (simple/robust) to 100 (complex/fragile)
    weight:       float    # weighting in composite score
    note:         str


# ── Technology baseline profiles ──────────────────────────────────────────────
# Each entry: (control_loops, automation_dep, process_sensitivity, operator_skill, failure_consequence)
# Scale 0-100 for each factor.
_COMPLEXITY_PROFILES: Dict[str, Dict[str, float]] = {
    "bnr": {
        "control_loops":          35,   # DO control, RAS, WAS, anoxic selector
        "automation_dependency":  30,   # can run manually; aerators have local controls
        "process_sensitivity":    40,   # TN sensitive to carbon, SRT; robust on BOD/TSS
        "operator_skill":         35,   # well-understood by Aus operators
        "failure_consequence":    30,   # clarifier failure = TSS spike; recoverable in hours-days
    },
    "granular_sludge": {
        "control_loops":          65,   # DO, feed rate, decant timing, SV30 monitoring
        "automation_dependency":  75,   # SBR cycle must be automated; manual override risky
        "process_sensitivity":    70,   # granule stability sensitive to feast/famine ratio, toxic shock
        "operator_skill":         65,   # limited AU operator familiarity; vendor support critical
        "failure_consequence":    55,   # granule loss = weeks to re-establish; significant cost
    },
    "mabr_bnr": {
        "control_loops":          60,   # plus gas pressure control, gas-side monitoring
        "automation_dependency":  55,   # MABR modules can be isolated; BNR train continues
        "process_sensitivity":    55,   # MABR sensitive to biofilm detachment, gas pressure
        "operator_skill":         70,   # novel technology; vendor-specific expertise required
        "failure_consequence":    50,   # MABR bypass to BNR mode; performance degraded not failed
    },
    "bnr_mbr": {
        "control_loops":          70,   # DO, TMP, flux, RAS, WAS, CIP, scour air
        "automation_dependency":  80,   # membrane fouling control requires SCADA automation
        "process_sensitivity":    60,   # membrane TMP response; sludge rheology sensitive
        "operator_skill":         65,   # MBR specific skills; CIP chemistry management
        "failure_consequence":    65,   # membrane damage = major cost; recovery weeks
    },
    "ifas_mbbr": {
        "control_loops":          45,   # DO, RAS, media retention screens
        "automation_dependency":  40,   # similar to BNR plus media monitoring
        "process_sensitivity":    45,   # media biofilm relatively robust
        "operator_skill":         45,   # IFAS well understood in AU retrofit context
        "failure_consequence":    35,   # media loss or clogging; moderate recovery
    },
    "anmbr": {
        "control_loops":          75,
        "automation_dependency":  85,
        "process_sensitivity":    80,
        "operator_skill":         80,
        "failure_consequence":    75,
    },
    "mob": {
        "control_loops":          60,
        "automation_dependency":  55,
        "process_sensitivity":    65,
        "operator_skill":         70,
        "failure_consequence":    55,
    },
}

_DEFAULT_PROFILE: Dict[str, float] = {
    "control_loops":          50,
    "automation_dependency":  50,
    "process_sensitivity":    50,
    "operator_skill":         50,
    "failure_consequence":    50,
}

_FACTOR_WEIGHTS: Dict[str, float] = {
    "control_loops":          0.20,
    "automation_dependency":  0.25,   # highest weight — automation failure is primary ops risk
    "process_sensitivity":    0.25,
    "operator_skill":         0.20,
    "failure_consequence":    0.10,
}

_FACTOR_LABELS: Dict[str, str] = {
    "control_loops":          "Active control loops",
    "automation_dependency":  "Automation dependency",
    "process_sensitivity":    "Process sensitivity (DO/SRT/temp)",
    "operator_skill":         "Operator skill requirement",
    "failure_consequence":    "Failure consequence magnitude",
}

# Adjustments based on actual design conditions
_COLD_TEMP_PENALTY   = 8.0    # process sensitivity +8 if design temp < 15°C
_TIGHT_TN_PENALTY    = 6.0    # process sensitivity +6 if TN target < 6 mg/L
_HIGH_FLOW_PENALTY   = 5.0    # control loops +5 if peak_flow_factor > 2.0
_SMALL_PLANT_BONUS   = -5.0   # automation dep -5 if design_flow < 2 MLD (simpler)
_LARGE_PLANT_PENALTY = 5.0    # failure consequence +5 if design_flow > 50 MLD


@dataclass
class OperationalComplexityResult:
    scenario_name:    str
    tech_code:        str
    complexity_score: float     # 0–100 composite
    factors:          List[ComplexityFactor] = field(default_factory=list)
    narrative:        str = ""
    # How much this adjusts the operational_risk raw score
    ops_risk_adjustment: float = 0.0   # added to existing ops_risk raw score

    def build_narrative(self) -> None:
        drivers = sorted(self.factors, key=lambda f: f.score * f.weight, reverse=True)
        top = drivers[:2]
        if self.complexity_score >= 70:
            level = "High"
            outlook = "requires dedicated specialist operator support and robust SCADA."
        elif self.complexity_score >= 50:
            level = "Moderate"
            outlook = "manageable with trained operators and vendor commissioning support."
        else:
            level = "Low"
            outlook = "within the capability of standard water utility operations."
        driver_txt = " and ".join(f.name.lower() for f in top)
        self.narrative = (
            f"{level} operational complexity ({self.complexity_score:.0f}/100), "
            f"driven by {driver_txt}. {outlook}"
        )


def score_operational_complexity(
    scenario_name:   str,
    tech_code:       str,
    design_flow_mld: float = 10.0,
    eff_tn_target:   float = 10.0,
    temperature_c:   float = 20.0,
    peak_flow_factor: float = 1.5,
) -> OperationalComplexityResult:
    """
    Score operational complexity for one scenario.
    """
    profile = dict(_COMPLEXITY_PROFILES.get(tech_code, _DEFAULT_PROFILE))

    # ── Condition-based adjustments ───────────────────────────────────────
    if temperature_c < 15.0:
        profile["process_sensitivity"] = min(100, profile["process_sensitivity"] + _COLD_TEMP_PENALTY)
    if eff_tn_target < 6.0:
        profile["process_sensitivity"] = min(100, profile["process_sensitivity"] + _TIGHT_TN_PENALTY)
    if peak_flow_factor > 2.0:
        profile["control_loops"] = min(100, profile["control_loops"] + _HIGH_FLOW_PENALTY)
    if design_flow_mld < 2.0:
        profile["automation_dependency"] = max(0, profile["automation_dependency"] + _SMALL_PLANT_BONUS)
    if design_flow_mld > 50.0:
        profile["failure_consequence"] = min(100, profile["failure_consequence"] + _LARGE_PLANT_PENALTY)

    # ── Build factors ─────────────────────────────────────────────────────
    factors   = []
    composite = 0.0
    for key, weight in _FACTOR_WEIGHTS.items():
        score = profile.get(key, 50.0)
        note  = _factor_note(key, score)
        factors.append(ComplexityFactor(
            name   = _FACTOR_LABELS[key],
            score  = score,
            weight = weight,
            note   = note,
        ))
        composite += score * weight

    composite = round(min(100.0, max(0.0, composite)), 1)

    # ── ops_risk_adjustment: how much to modify the risk engine's ops score ─
    # The risk engine already computes an ops_score from risk_items.
    # This adjustment nudges it based on the complexity analysis.
    # Scale: ±10 points max, proportional to deviation from 50 (neutral)
    adjustment = (composite - 50.0) * 0.15   # 50 pts above neutral → +7.5 pts

    result = OperationalComplexityResult(
        scenario_name     = scenario_name,
        tech_code         = tech_code,
        complexity_score  = composite,
        factors           = factors,
        ops_risk_adjustment = round(adjustment, 1),
    )
    result.build_narrative()
    return result


def _factor_note(key: str, score: float) -> str:
    level = "Low" if score < 35 else ("Moderate" if score < 65 else "High")
    notes = {
        "control_loops":          f"{level} — {'few simple loops' if score < 35 else 'multiple interdependent loops' if score >= 65 else 'standard control complexity'}",
        "automation_dependency":  f"{level} — {'can be operated manually' if score < 35 else 'SCADA-dependent, limited manual fallback' if score >= 65 else 'automation assists but not critical'}",
        "process_sensitivity":    f"{level} — {'robust to operational variation' if score < 35 else 'sensitive to DO/SRT/temperature fluctuations' if score >= 65 else 'moderate sensitivity to key parameters'}",
        "operator_skill":         f"{level} — {'standard utility skills' if score < 35 else 'specialist skills required' if score >= 65 else 'above-average training needed'}",
        "failure_consequence":    f"{level} — {'recoverable in hours' if score < 35 else 'major impact, weeks to recover' if score >= 65 else 'significant but manageable impact'}",
    }
    return notes.get(key, f"{level}")


def score_all_complexity(
    scenarios: List[Any],
) -> Dict[str, OperationalComplexityResult]:
    """Score operational complexity for all scenarios."""
    results = {}
    for s in scenarios:
        tc   = (s.treatment_pathway.technology_sequence[0]
                if s.treatment_pathway and s.treatment_pathway.technology_sequence else "")
        dinp = getattr(s, "domain_inputs", None) or {}
        dso  = getattr(s, "domain_specific_outputs", None) or {}
        tp   = (dso.get("technology_performance", {}) or {}).get(tc, {})
        results[s.scenario_name] = score_operational_complexity(
            scenario_name    = s.scenario_name,
            tech_code        = tc,
            design_flow_mld  = dinp.get("design_flow_mld", 10.0),
            eff_tn_target    = dinp.get("effluent_tn_mg_l", 10.0),
            temperature_c    = tp.get("influent_temperature_celsius", 20.0),
            peak_flow_factor = tp.get("peak_flow_factor", 1.5),
        )
    return results
