"""
BioPoint V1 — System Coupling Classification Engine.
Explicitly classifies each biosolids pathway by its degree of interaction
with the liquid-side wastewater treatment plant.

Three coupling tiers (v24Z78):

  TIER 1 — FULLY DECOUPLED
    No significant return load to mainstream.
    Solid residual (ash, char) goes off-site.
    Examples: incineration, pyrolysis, gasification.
    Mainstream plant operates independently of biosolids pathway.

  TIER 2 — PARTIALLY COUPLED
    Moderate centrate/condensate return — manageable at plant scale.
    Examples: AD, THP+incineration, drying, decentralised drying.
    Standard design practice; return scheduling reduces peak impact.

  TIER 3 — FULLY COUPLED
    Significant process liquor return — strong interaction with mainstream.
    Examples: HTC (high-strength liquor), raw HTC without sidestream.
    Cannot be selected without explicit assessment of mainstream capacity.

Decision rules:
  - Capacity constrained plant: penalise Tier 3; prefer Tier 1
  - Resilience priority HIGH: favour Tier 1 (decoupled = operationally independent)
  - Compliance risk exists: require mitigation plan before Tier 3 selection

Critical rule:
  HTC must NEVER be recommended without explicit coupling evaluation.
  This engine enforces that rule structurally.

ph2o Consulting — BioPoint V1
"""

from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# COUPLING TIER DEFINITIONS
# ---------------------------------------------------------------------------

COUPLING_TIER_LABELS = {
    1: "Fully Decoupled",
    2: "Partially Coupled",
    3: "Fully Coupled",
}

COUPLING_TIER_DESCRIPTIONS = {
    1: (
        "No significant process liquor return to the mainstream treatment plant. "
        "The biosolids pathway operates independently of liquid-side capacity. "
        "Solid residual (ash, char, dried product) is removed off-site."
    ),
    2: (
        "Moderate centrate or condensate return to works headworks or secondary treatment. "
        "Return load is manageable at typical plant scale with scheduling controls. "
        "Standard design practice — no capacity constraints implied."
    ),
    3: (
        "Significant high-strength process liquor returned to the mainstream plant. "
        "COD, NH₄-N and TP loads require explicit capacity assessment before pathway selection. "
        "May require dedicated sidestream treatment to prevent compliance failure."
    ),
}

# Tier assignment by pathway type
COUPLING_TIER_BY_PATHWAY = {
    "baseline":        1,   # No treatment — no return liquor
    "incineration":    1,   # Scrubber water only — negligible load
    "thp_incineration":2,   # THP condensate + centrate — manageable
    "gasification":    1,   # Syngas scrubber water — low load
    "pyrolysis":       1,   # Condensate only
    "drying_only":     2,   # Condensate — moderate
    "decentralised":   2,   # Condensate
    "AD":              2,   # Centrate — standard; manageable
    "centralised":     2,   # Centrate + condensate
    "HTC":             3,   # HIGH-STRENGTH liquor — fully coupled
    "HTC_sidestream":  2,   # Sidestream removes the coupling — downgraded to Tier 2
}

# Compliance risk levels by coupling tier (default — refined by impact rating)
COMPLIANCE_RISK_BY_TIER = {
    1: "Low",
    2: "Low to Moderate",
    3: "Moderate to High",
}


# ---------------------------------------------------------------------------
# DATACLASSES
# ---------------------------------------------------------------------------

@dataclass
class CouplingClassification:
    """
    Coupling classification for one flowsheet.
    Produced by the coupling classification engine.
    """
    flowsheet_id: str = ""
    flowsheet_name: str = ""
    pathway_type: str = ""

    # --- TIER ---
    coupling_tier: int = 1
    coupling_tier_label: str = "Fully Decoupled"
    coupling_tier_description: str = ""

    # --- LOADS (from mainstream coupling engine) ---
    return_nh4_kg_d: float = 0.0
    return_cod_kg_d: float = 0.0
    return_tp_kg_d: float = 0.0
    return_as_pct_of_plant_nh4: float = 0.0
    additional_aeration_kwh_d: float = 0.0

    # --- MAINSTREAM IMPACT ---
    mainstream_impact: str = "Low"     # Low / Moderate / High
    compliance_risk: str = "Low"       # Low / Moderate / High

    # --- COMPLIANCE RISK STATEMENT ---
    compliance_risk_statement: str = ""

    # --- DECISION MODIFIERS ---
    capacity_constraint_penalty: float = 0.0   # Score penalty if plant capacity constrained
    resilience_priority_bonus: float = 0.0     # Score bonus if resilience priority
    net_coupling_score_adjustment: float = 0.0

    # --- MITIGATION ---
    mitigation_required: bool = False
    mitigation_summary: str = ""
    sidestream_required: bool = False
    sidestream_capex_m: float = 0.0

    # --- DISPLAY ---
    display_badge: str = ""   # Short badge for UI: "✓ Decoupled" / "⚡ Coupled" / "⚠ Full Coupled"
    display_colour: str = ""  # "green" / "amber" / "red"


@dataclass
class CouplingClassificationSystem:
    """System-level coupling classification across all flowsheets."""
    classifications: list = field(default_factory=list)  # List[CouplingClassification]

    # Counts by tier
    tier1_count: int = 0
    tier2_count: int = 0
    tier3_count: int = 0

    # Plant context
    plant_capacity_constrained: bool = False
    resilience_priority: bool = False
    plant_flow_ML_d: float = 0.0

    # System-level flags
    htc_requires_evaluation: bool = False    # Always True when HTC present
    htc_evaluation_complete: bool = False    # True when coupling evaluated

    # Narrative
    system_coupling_narrative: str = ""

    # Lookup
    _by_id: dict = field(default_factory=dict)

    def get(self, flowsheet_id: str) -> Optional[CouplingClassification]:
        return self._by_id.get(flowsheet_id)


# ---------------------------------------------------------------------------
# MAIN ENGINE
# ---------------------------------------------------------------------------

def run_coupling_classification(
    flowsheets: list,
    ds_tpd: float,
    plant_flow_ML_d: Optional[float] = None,
    plant_capacity_constrained: bool = False,
    resilience_priority: bool = False,
) -> CouplingClassificationSystem:
    """
    Classify all flowsheets by coupling tier and compute scoring adjustments.

    Parameters
    ----------
    flowsheets               : list of evaluated Flowsheet objects
    ds_tpd                   : dry solids throughput (tDS/day)
    plant_flow_ML_d          : influent flow (ML/d) — if None, estimated from DS
    plant_capacity_constrained: True if mainstream plant is near capacity
    resilience_priority      : True if optimisation priority is highest_resilience
    """
    if plant_flow_ML_d is None:
        ep = ds_tpd * 1_000_000 / 35.0
        plant_flow_ML_d = ep * 250 / 1_000_000

    classifications = []
    by_id = {}
    htc_present = any(fs.pathway_type in ("HTC", "HTC_sidestream") for fs in flowsheets)

    for fs in flowsheets:
        cc = _classify_flowsheet(
            fs, plant_flow_ML_d,
            plant_capacity_constrained, resilience_priority
        )
        classifications.append(cc)
        by_id[fs.flowsheet_id] = cc
        # Attach to flowsheet
        fs.coupling_classification = cc

    tier_counts = {1: 0, 2: 0, 3: 0}
    for cc in classifications:
        tier_counts[cc.coupling_tier] = tier_counts.get(cc.coupling_tier, 0) + 1

    narrative = _system_narrative(
        classifications, plant_capacity_constrained,
        resilience_priority, htc_present, tier_counts
    )

    sys = CouplingClassificationSystem(
        classifications=classifications,
        tier1_count=tier_counts[1],
        tier2_count=tier_counts[2],
        tier3_count=tier_counts[3],
        plant_capacity_constrained=plant_capacity_constrained,
        resilience_priority=resilience_priority,
        plant_flow_ML_d=round(plant_flow_ML_d, 1),
        htc_requires_evaluation=htc_present,
        htc_evaluation_complete=htc_present,   # Evaluation is mandatory and always run
        system_coupling_narrative=narrative,
        _by_id=by_id,
    )
    return sys


def _classify_flowsheet(fs, plant_flow_ML_d: float,
                         capacity_constrained: bool,
                         resilience_priority: bool) -> CouplingClassification:
    """Produce CouplingClassification for one flowsheet."""
    ptype = fs.pathway_type
    mc    = fs.mainstream_coupling  # MainstreamCouplingResult — may be None

    # Tier from lookup
    tier = COUPLING_TIER_BY_PATHWAY.get(ptype, 2)
    tier_label = COUPLING_TIER_LABELS[tier]
    tier_desc  = COUPLING_TIER_DESCRIPTIONS[tier]

    # Loads from coupling engine
    nh4 = mc.return_nh4_kg_d    if mc else 0.0
    cod = mc.return_cod_kg_d    if mc else 0.0
    tp  = mc.return_tp_kg_d     if mc else 0.0
    pct = mc.return_as_pct_of_plant_nh4 if mc else 0.0
    aer = mc.additional_aeration_kwh_d  if mc else 0.0
    impact = mc.mainstream_impact if mc else "Low"

    # Compliance risk — refine by impact rating
    compliance_risk_map = {
        ("Low",      1): "Low",
        ("Low",      2): "Low",
        ("Low",      3): "Low",          # HTC_sidestream treated
        ("Moderate", 1): "Low",
        ("Moderate", 2): "Low to Moderate",
        ("Moderate", 3): "Moderate",
        ("High",     1): "Low",
        ("High",     2): "Moderate",
        ("High",     3): "High",
    }
    compliance_risk = compliance_risk_map.get((impact, tier), "Low to Moderate")

    # Tier 3 floor: Fully Coupled pathways always carry at least Moderate compliance risk
    # regardless of plant size, because the structural coupling hazard exists even
    # when the current load appears small relative to a large plant.
    if tier == 3 and ptype != "HTC_sidestream":
        if compliance_risk == "Low":
            compliance_risk = "Moderate"

    # Compliance risk statement
    if compliance_risk == "High":
        risk_stmt = (
            f"HIGH compliance risk. Return NH₄-N ({nh4:.0f} kgN/d = {pct:.0f}% of influent) "
            "may trigger nitrogen effluent limit exceedance. "
            "Do not select this pathway without confirmed mainstream plant capacity "
            "and a sidestream treatment plan."
        )
    elif compliance_risk == "Moderate":
        risk_stmt = (
            f"MODERATE compliance risk. Return NH₄-N ({nh4:.0f} kgN/d = {pct:.1f}% of influent) "
            "requires scheduling controls and effluent N monitoring. "
            "Confirm available nitrification capacity before final design."
        )
    elif compliance_risk == "Low to Moderate":
        risk_stmt = (
            f"LOW to MODERATE compliance risk. Return NH₄-N ({nh4:.0f} kgN/d = {pct:.1f}% of influent). "
            "Manageable with standard return scheduling. Review during detailed design."
        )
    else:
        risk_stmt = (
            f"LOW compliance risk. Return NH₄-N ({nh4:.0f} kgN/d = {pct:.1f}% of influent) "
            "is within routine recycle tolerance for a plant of this scale."
        )

    # HTC-specific override — must explicitly state coupling regardless of tier
    if ptype == "HTC":
        risk_stmt = (
            "CRITICAL — HTC FULLY COUPLED: Raw HTC process liquor is high-strength "
            f"(COD ~{cod/max(nh4/35,1):.0f} mg/L, NH₄-N ~{nh4/max(cod/120,1):.0f} mg/L). "
            "Direct return to works WILL impact nitrogen removal and aeration. "
            f"Return load = {pct:.0f}% of plant influent N. "
            "This pathway CANNOT be recommended without sidestream treatment or "
            "confirmed excess mainstream capacity."
        )

    # --- SCORING ADJUSTMENTS ---
    # Capacity constraint penalty: Tier 3 penalised more severely when plant is full
    capacity_penalty = 0.0
    if capacity_constrained:
        penalty_by_tier = {1: 0.0, 2: -3.0, 3: -15.0}
        capacity_penalty = penalty_by_tier.get(tier, 0.0)
        if impact == "High":
            capacity_penalty -= 5.0

    # Resilience priority bonus: Tier 1 (decoupled) is more resilient
    resilience_bonus = 0.0
    if resilience_priority:
        bonus_by_tier = {1: 8.0, 2: 2.0, 3: -5.0}
        resilience_bonus = bonus_by_tier.get(tier, 0.0)

    # Tier 3 structural baseline penalty: Fully Coupled pathways carry inherent
    # risk from mainstream interaction regardless of current impact rating.
    # Applies always for raw Tier 3 (not HTC_sidestream which has mitigated).
    tier3_baseline_penalty = 0.0
    if tier == 3 and ptype != "HTC_sidestream":
        # Moderate impact: −5; High impact: −10 (High impact also triggers ranking_downgrade)
        if impact == "High":
            tier3_baseline_penalty = -10.0
        else:
            tier3_baseline_penalty = -5.0   # Moderate or Low impact Tier 3

    net_adj = capacity_penalty + resilience_bonus + tier3_baseline_penalty

    # Badge and colour
    if tier == 1:
        badge = "✓ Decoupled"
        colour = "green"
    elif tier == 2:
        badge = "~ Partial"
        colour = "amber"
    else:
        badge = "⚠ Coupled"
        colour = "red"

    # Mitigation
    mit_required = bool(mc and mc.mitigation_required) if mc else False
    mit_summary  = "; ".join(mc.mitigation_actions[:2]) if (mc and mc.mitigation_actions) else ""
    ss_required  = bool(mc and mc.sidestream_treatment_required) if mc else False
    ss_capex     = mc.sidestream_capex_estimate_m if mc else 0.0

    return CouplingClassification(
        flowsheet_id=fs.flowsheet_id,
        flowsheet_name=fs.name,
        pathway_type=ptype,
        coupling_tier=tier,
        coupling_tier_label=tier_label,
        coupling_tier_description=tier_desc,
        return_nh4_kg_d=round(nh4, 1),
        return_cod_kg_d=round(cod, 1),
        return_tp_kg_d=round(tp, 1),
        return_as_pct_of_plant_nh4=round(pct, 1),
        additional_aeration_kwh_d=round(aer, 0),
        mainstream_impact=impact,
        compliance_risk=compliance_risk,
        compliance_risk_statement=risk_stmt,
        capacity_constraint_penalty=round(capacity_penalty, 1),
        resilience_priority_bonus=round(resilience_bonus, 1),
        net_coupling_score_adjustment=round(net_adj, 1),
        mitigation_required=mit_required,
        mitigation_summary=mit_summary,
        sidestream_required=ss_required,
        sidestream_capex_m=round(ss_capex, 2),
        display_badge=badge,
        display_colour=colour,
    )


def _system_narrative(classifications, capacity_constrained, resilience_priority,
                       htc_present, tier_counts) -> str:
    parts = []
    parts.append(
        f"Coupling profile: {tier_counts[1]} Fully Decoupled, "
        f"{tier_counts[2]} Partially Coupled, {tier_counts[3]} Fully Coupled pathways."
    )
    if htc_present:
        htc_cls = next((c for c in classifications if c.pathway_type == "HTC"), None)
        if htc_cls:
            parts.append(
                f"HTC is Fully Coupled (Tier 3): {htc_cls.compliance_risk_statement[:120]}..."
            )
    if capacity_constrained:
        parts.append(
            "Plant capacity constrained: Tier 3 pathways penalised. "
            "Fully Decoupled pathways preferred."
        )
    if resilience_priority:
        parts.append(
            "Resilience priority active: Tier 1 (Decoupled) pathways receive +8 score bonus. "
            "Tier 3 pathways receive −5 penalty."
        )
    tier1_names = [c.flowsheet_name for c in classifications if c.coupling_tier == 1]
    if tier1_names:
        parts.append(
            f"Decoupled pathways (Tier 1): {', '.join(tier1_names[:4])}."
        )
    return " ".join(parts)
