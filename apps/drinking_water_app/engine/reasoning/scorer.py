"""
AquaPoint Reasoning Engine — Tier 1–4 Scoring Framework
Comparative scoring of viable treatment archetypes.

Tier 1: Compliance / safety (pass/fail)
Tier 2: Robustness and reliability (weighted, high influence)
Tier 3: Resource and environmental performance
Tier 4: Cost and flexibility
"""

from dataclasses import dataclass, field
from .archetypes import ARCHETYPES, ArchetypeSelectionResult
from .lrv import LRVResult, get_lrv_for_archetype
from .residuals import ResidualsResult
from .classifier import SourceWaterInputs


@dataclass
class ArchetypeScore:
    archetype_key: str = ""
    archetype_label: str = ""

    # Tier 1
    tier1_pass: bool = True
    tier1_issues: list = field(default_factory=list)

    # Tier 2 (0–10 each)
    variability_robustness: float = 0.0
    barrier_redundancy: float = 0.0
    event_response: float = 0.0
    operability: float = 0.0
    tier2_score: float = 0.0

    # Tier 3 (0–10 each)
    chemical_demand: float = 0.0
    energy_demand: float = 0.0
    residuals_burden: float = 0.0
    footprint: float = 0.0
    tier3_score: float = 0.0

    # Tier 4 (0–10 each)
    capex: float = 0.0
    opex: float = 0.0
    expandability: float = 0.0
    delivery_risk: float = 0.0
    tier4_score: float = 0.0

    # Overall (not used to override Tier 1)
    overall_score: float = 0.0
    recommendation_strength: str = ""  # strong / moderate / conditional / not_recommended


# ─── Scoring Tables ───────────────────────────────────────────────────────────

# Operability (lower = more complex = lower score)
OPERABILITY_SCORES = {
    "Low complexity — few moving parts, simple chemical programme": 9,
    "Moderate — requires coagulant control, sludge management": 7,
    "Moderate-high — mechanical systems require more maintenance": 6,
    "Moderate — pressurisation system, float removal": 6,
    "Moderate — biological system management required": 6,
    "High complexity — lime slaking, multiple pH control points, sludge handling": 3,
    "High — ozone system management, media monitoring, H₂O₂ if AOP": 4,
    "High — membrane integrity, CIP systems, concentrate management": 4,
    "Variable — depends on specific contaminant train": 5,
}

# Energy class scores (high energy = lower score)
ENERGY_SCORES = {
    "low": 9, "low_moderate": 7, "moderate": 6,
    "moderate_high": 4, "high": 3, "variable": 5,
}

# Chemical class scores
CHEMICAL_SCORES = {
    "low": 9, "moderate": 6, "moderate_high": 4, "high": 3, "variable": 5,
}

# Footprint scores (high footprint = lower score)
FOOTPRINT_SCORES = {
    "very_low": 10, "low_moderate": 8, "low": 9, "moderate": 6, "high": 4, "very_high": 2,
}

# Residuals complexity scores
RESIDUALS_SCORES = {
    "low": 9, "moderate": 6, "high": 3, "very_high": 1,
}

# Variability robustness (how well the archetype handles raw water variability)
VARIABILITY_ROBUSTNESS = {
    "A": 3,   # Direct filtration very sensitive to variability
    "B": 8,   # Conventional sedimentation — proven workhorse
    "C": 7,   # Intensified — comparable but less proven in extremes
    "D": 8,   # DAF — robust for algae/NOM but higher energy
    "E": 7,   # Enhanced coagulation — good but chemical-dependent
    "F": 6,   # Softening — robust for hardness but less so for variability
    "G": 6,   # Ozone+BAC — relies on upstream treatment being adequate
    "H": 7,   # Membrane — absolute barrier, but fouling risk in events
    "I": 5,   # Contaminant-specific — depends on primary train
}

# Event response (how quickly/safely the system responds to acute events)
EVENT_RESPONSE = {
    "A": 2,   # Very limited — filter overload risk
    "B": 7,   # Good — sedimentation provides buffer
    "C": 7,
    "D": 8,   # DAF responds well to algal events
    "E": 6,
    "F": 5,
    "G": 5,   # Ozone needs upstream clarification to function
    "H": 6,   # Membrane — physically robust but fouling events possible
    "I": 5,
}

# Barrier redundancy
BARRIER_REDUNDANCY = {
    "A": 3,   # Single main barrier — filter only
    "B": 7,
    "C": 7,
    "D": 8,   # DAF + filtration + disinfection
    "E": 7,
    "F": 5,   # Good hardness removal but fewer pathogen barriers
    "G": 8,   # Multiple barriers including advanced oxidation
    "H": 9,   # Multiple validated membrane barriers
    "I": 5,
}

# Capital cost relative scores (low CAPEX = high score)
CAPEX_SCORES = {
    "A": 9, "B": 5, "C": 6, "D": 6, "E": 5, "F": 4, "G": 5, "H": 4, "I": 6,
}

# Expandability
EXPANDABILITY_SCORES = {
    "A": 7, "B": 5, "C": 8, "D": 7, "E": 6, "F": 4, "G": 7, "H": 6, "I": 5,
}

# Delivery risk (technology maturity, supply chain)
DELIVERY_RISK_SCORES = {
    "A": 9, "B": 9, "C": 7, "D": 8, "E": 8, "F": 7, "G": 6, "H": 6, "I": 6,
}


# ─── Tier 1 Assessment ────────────────────────────────────────────────────────

def _assess_tier1(archetype_key: str, inputs: SourceWaterInputs,
                  lrv_result: LRVResult) -> tuple:
    """Returns (pass: bool, issues: list)."""
    issues = []

    # LRV deficit
    for pathogen in ["protozoa", "bacteria", "virus"]:
        if lrv_result.gap_high.get(pathogen, 0) > 0:
            issues.append(
                f"LRV deficit for {pathogen}: maximum achievable {lrv_result.total_credited_high.get(pathogen, 0):.1f} log "
                f"vs. required {lrv_result.required.get(pathogen, 0):.1f} log."
            )

    # No primary disinfection
    da = lrv_result.disinfection_assessment
    if not da.get("primary_disinfection"):
        issues.append("No primary disinfection barrier in archetype default train.")

    # No protozoan inactivation barrier
    if not da.get("protozoan_inactivation_barrier"):
        issues.append("No validated protozoan inactivation barrier (UV or ozone). Chlorine alone is insufficient for Cryptosporidium.")

    # Direct filtration with variability
    if archetype_key == "A" and inputs.variability_class in ["high", "extreme"]:
        issues.append("Direct filtration is not appropriate for high-variability source water.")

    # Ozone without cell removal for cyanobacteria
    if archetype_key == "G" and inputs.cyanobacteria_confirmed:
        issues.append(
            "Archetype G (ozone) requires clarification upstream to remove cyanobacterial cells before oxidation. "
            "Train must include cell removal before ozone contact."
        )

    return len(issues) == 0, issues


# ─── Main Scoring Function ────────────────────────────────────────────────────

def score_archetypes(
    viable_archetypes: list,    # list of ArchetypeAssessment
    inputs: SourceWaterInputs,
    residuals_assessments: dict,   # archetype_key → ResidualsResult
    required_lrv: dict,
) -> list:
    """
    Score all viable archetypes. Returns list of ArchetypeScore, sorted by overall score.
    """
    scores = []

    for aa in viable_archetypes:
        key = aa.key
        arch_data = ARCHETYPES.get(key, {})
        s = ArchetypeScore(archetype_key=key, archetype_label=aa.label)

        # LRV
        lrv_result = get_lrv_for_archetype(key, required_lrv)

        # Tier 1
        s.tier1_pass, s.tier1_issues = _assess_tier1(key, inputs, lrv_result)

        # Tier 2
        s.variability_robustness = VARIABILITY_ROBUSTNESS.get(key, 5)
        s.event_response = EVENT_RESPONSE.get(key, 5)
        s.barrier_redundancy = BARRIER_REDUNDANCY.get(key, 5)
        s.operability = OPERABILITY_SCORES.get(arch_data.get("operability", ""), 5)
        # Scale operability for remote/small sites
        if inputs.remote_operation and s.operability < 7:
            s.operability = max(1, s.operability - 2)

        s.tier2_score = round(
            (s.variability_robustness * 0.35 + s.event_response * 0.25 +
             s.barrier_redundancy * 0.25 + s.operability * 0.15), 1
        )

        # Tier 3
        s.energy_demand = ENERGY_SCORES.get(arch_data.get("energy_class", "moderate"), 5)
        s.chemical_demand = CHEMICAL_SCORES.get(arch_data.get("chemical_class", "moderate"), 5)
        s.footprint = FOOTPRINT_SCORES.get(arch_data.get("footprint_class", "moderate"), 5)
        residuals = residuals_assessments.get(key)
        s.residuals_burden = RESIDUALS_SCORES.get(
            residuals.complexity_rating if residuals else "moderate", 5
        )
        # Heavy penalty for classified wastes
        if residuals and residuals.classified_waste_streams:
            s.residuals_burden = max(1, s.residuals_burden - 2)

        s.tier3_score = round(
            (s.energy_demand * 0.25 + s.chemical_demand * 0.25 +
             s.residuals_burden * 0.30 + s.footprint * 0.20), 1
        )

        # Tier 4
        s.capex = CAPEX_SCORES.get(key, 5)
        s.opex = max(1, 10 - (10 - s.energy_demand) // 2 - (10 - s.chemical_demand) // 2)
        s.expandability = EXPANDABILITY_SCORES.get(key, 5)
        s.delivery_risk = DELIVERY_RISK_SCORES.get(key, 7)

        s.tier4_score = round(
            (s.capex * 0.35 + s.opex * 0.30 +
             s.expandability * 0.15 + s.delivery_risk * 0.20), 1
        )

        # Overall (Tier 1 gates, then weighted Tier 2–4)
        if not s.tier1_pass:
            s.overall_score = 0.0
            s.recommendation_strength = "not_recommended"
        else:
            s.overall_score = round(
                s.tier2_score * 0.50 + s.tier3_score * 0.30 + s.tier4_score * 0.20,
                1
            )
            if s.overall_score >= 7.5:
                s.recommendation_strength = "strong"
            elif s.overall_score >= 6.0:
                s.recommendation_strength = "moderate"
            elif s.overall_score >= 4.5:
                s.recommendation_strength = "conditional"
            else:
                s.recommendation_strength = "not_recommended"

        scores.append(s)

    # Sort: Tier 1 pass first, then by overall score
    scores.sort(key=lambda x: (0 if x.tier1_pass else 1, -x.overall_score))
    return scores
