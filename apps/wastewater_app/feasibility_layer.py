"""
apps/wastewater_app/feasibility_layer.py

Feasibility Layer — Production V1
===================================

Evaluates whether a recommended Technology Stack (UpgradePathway) is:
  → deliverable   (supply chain, availability)
  → operable      (operational complexity, skill requirements)
  → economically credible (OPEX intensity, chemical/energy dependency)

This layer annotates, scores, and adjusts confidence.
It does NOT modify the original stack or change selected technologies.

Design principles
-----------------
- Pure functions — no Streamlit, no I/O, no side effects.
- Reads UpgradePathway from stack_generator.py.
- Returns FeasibilityReport with full scoring and optional lower-risk alternative.
- All rules are explicit, deterministic, and traceable.
- Language reads like a consultant's technical risk register.

Key technology rules embedded
------------------------------
- CoMag / BioMag: continuous magnetite supply; recovery efficiency drives whole-of-life cost.
- Denitrification Filter: methanol 2.5–3.0 mg/mg NO₃-N; DO carryover suppresses performance.
- MABR: specialist hollow-fibre modules; performance dependent on membrane integrity.
- IFAS / MBBR / Hybas: media retention screens; retrofit complexity low.
- MOB (inDENSE + miGRATE): mechanical + hydraulic integration; biomass selection stability.
- memDENSE: hydrocyclone operation critical; permeability improvement within 4–8 weeks.
- EQ basin / storm storage: footprint + capital; most robust hydraulic solution.

Main entry point
----------------
  assess_feasibility(pathway, plant_context) -> FeasibilityReport
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from apps.wastewater_app.stack_generator import (
    UpgradePathway, PathwayStage,
    TI_COMAG, TI_BIOMAG, TI_EQ_BASIN, TI_STORM_STORE,
    TI_INDENSE, TI_MIGINDENSE, TI_MEMDENSE,
    TI_HYBAS, TI_IFAS, TI_MBBR, TI_MABR,
    TI_BARDENPHO, TI_RECYCLE_OPT, TI_ZONE_RECONF,
    TI_DENFILTER, TI_TERT_P,
)

# ── Feasibility score constants ────────────────────────────────────────────────
FS_HIGH   = "High"
FS_MEDIUM = "Medium"
FS_LOW    = "Low"

_FS_ORDER = {FS_HIGH: 2, FS_MEDIUM: 1, FS_LOW: 0}

# ── Location type constants ────────────────────────────────────────────────────
LOC_METRO    = "metro"
LOC_REGIONAL = "regional"
LOC_REMOTE   = "remote"


# ── Result dataclasses ─────────────────────────────────────────────────────────

@dataclass
class DimensionScore:
    """Feasibility score for one evaluation dimension."""
    dimension:   str    # e.g. "Supply Chain"
    score:       str    # High / Medium / Low
    notes:       List[str] = field(default_factory=list)


@dataclass
class StageFeasibility:
    """Feasibility assessment for one stage of the stack."""
    stage_number:  int
    technology:    str
    tech_display:  str
    feasibility:   str    # High / Medium / Low
    supply_risk:   str    # High / Medium / Low
    opex_impact:   str    # Low / Medium / High
    complexity:    str    # Low / Medium / High
    chemical_dep:  str    # None / Low / Medium / High
    specialist:    bool   # requires specialist supplier / expertise
    notes:         List[str] = field(default_factory=list)
    risks:         List[str] = field(default_factory=list)


@dataclass
class LowerRiskAlternative:
    """A lower-risk substitute stack when overall feasibility is Low or Medium-Low."""
    label:          str
    stage_changes:  List[str]    # "Replace X → Y" descriptions
    trade_offs:     List[str]    # what is given up
    feasibility:    str
    capex_impact:   str          # "Higher" / "Similar" / "Lower"
    rationale:      str


@dataclass
class FeasibilityReport:
    """Full feasibility assessment for an UpgradePathway."""
    # Overall
    overall_feasibility:   str    # High / Medium / Low
    adjusted_confidence:   str    # High / Medium / Low (may differ from pathway.confidence)
    confidence_change:     str    # "Maintained" / "Downgraded" / "Upgraded"
    confidence_reason:     str

    # Dimension breakdown
    dimensions:            List[DimensionScore]

    # Stage-level
    stage_feasibility:     List[StageFeasibility]

    # Risk register
    supply_chain_risk:     str    # High / Medium / Low
    operational_complexity:str    # High / Medium / Low
    chemical_dependency:   str    # None / Low / Medium / High
    energy_impact:         str    # Low / Medium / High
    integration_risk:      str    # Low / Medium / High
    sludge_residuals_impact: str  # Low / Medium / High

    # Narrative
    feasibility_summary:   str    # one paragraph
    key_risks:             List[str]
    key_mitigations:       List[str]

    # Optional alternative
    lower_risk_alternative: Optional[LowerRiskAlternative] = None


# ── Technology feasibility profiles ───────────────────────────────────────────

@dataclass
class _TechProfile:
    supply_risk_base:  str   # base supply risk before location adjustment
    opex_impact:       str
    complexity:        str
    chemical_dep:      str   # None / Low / Medium / High
    specialist:        bool
    energy_class:      str   # Low / Medium / High
    sludge_impact:     str   # Low / Medium / High
    base_feasibility:  str
    notes:             List[str]
    risks:             List[str]


_PROFILES: Dict[str, _TechProfile] = {

    TI_COMAG: _TechProfile(
        supply_risk_base="High",
        opex_impact="Medium",
        complexity="Medium",
        chemical_dep="Medium",   # magnetite
        specialist=True,
        energy_class="Medium",
        sludge_impact="Low",
        base_feasibility="Medium",
        notes=[
            "Requires continuous water-grade magnetite with controlled particle size distribution (PSD ~10–30 μm). "
            "Oversized particles increase abrasion and equipment wear; undersized particles reduce "
            "magnetic recovery efficiency and increase ballast loss rate and OPEX.",
            "Recovery efficiency (>99.5% at correct PSD) determines whole-of-life cost. "
            "Pre-qualify magnetite suppliers against PSD specification before commitment.",
            "Monitor ballast loss as an operating KPI from commissioning. "
            "Logistics risk increases sharply at remote sites — dual-sourcing and \u226530-day contingency stock are essential.",
        ],
        risks=[
            "Supply chain disruption to water-grade magnetite (controlled PSD) halts operation. "
            "Pre-qualify \u22652 suppliers against PSD specification.",
            "Incorrect PSD (oversized) causes abrasion; undersized reduces recovery efficiency "
            "and increases ballast loss OPEX.",
            "Whole-of-life cost sensitive to recovery efficiency, ballast loss rate, "
            "and logistics distance — conduct TOTEX sensitivity at \u00b120% recovery.",
        ],
    ),

    TI_BIOMAG: _TechProfile(
        supply_risk_base="High",
        opex_impact="Medium",
        complexity="High",
        chemical_dep="Medium",
        specialist=True,
        energy_class="Medium",
        sludge_impact="Low",
        base_feasibility="Medium",
        notes=[
            "Secondary-stage settling and biomass-concentration technology — not a "
            "substitute for aeration intensification. Selected when settling and biomass "
            "inventory are jointly limiting, not when aeration or oxygen is the bottleneck.",
            "Requires water-grade magnetite with controlled particle size distribution "
            "(PSD ~10–30 μm). Incorrect PSD increases abrasion risk and reduces "
            "magnetic recovery efficiency. Pre-qualify supplier against PSD specification.",
            "Dual supply dependency: magnetite (controlled PSD) and carrier media must "
            "both be managed concurrently. Logistics risk increases at remote sites.",
            "Carrier retention screens required at zone outlets — combined with "
            "magnetite recovery, operational complexity is the highest in this technology class.",
        ],
        risks=[
            "Incorrect magnetite PSD (oversized) causes abrasion; undersized reduces "
            "recovery efficiency and increases ballast loss OPEX.",
            "If aeration or nitrification is the sole binding constraint, BioMag will not "
            "resolve the primary issue — MABR or IFAS are the correct technologies.",
            "Higher operational complexity than single-mechanism alternatives (inDENSE, IFAS). "
            "Both magnetite recovery and carrier retention must be maintained simultaneously.",
            "Whole-of-life cost sensitive to magnetite loss rate, recovery efficiency, "
            "and logistics distance — evaluate against simpler alternatives on TOTEX.",
        ],
    ),

    TI_EQ_BASIN: _TechProfile(
        supply_risk_base="Low",
        opex_impact="Low",
        complexity="Low",
        chemical_dep="None",
        specialist=False,
        energy_class="Low",
        sludge_impact="Low",
        base_feasibility="High",
        notes=[
            "Simplest and most robust hydraulic solution — concrete and pumps.",
            "No specialist supply chain dependency.",
            "Requires footprint and civil capital, but lowest operational risk.",
        ],
        risks=[
            "Requires available site footprint.",
            "Capital-intensive — may not be viable on constrained brownfield sites.",
        ],
    ),

    TI_STORM_STORE: _TechProfile(
        supply_risk_base="Low",
        opex_impact="Low",
        complexity="Low",
        chemical_dep="None",
        specialist=False,
        energy_class="Low",
        sludge_impact="Low",
        base_feasibility="High",
        notes=[
            "Standard civil infrastructure — robust and low-dependency.",
            "Operational simplicity: fill and return pump control.",
        ],
        risks=[
            "Site footprint required.",
            "Requires sewer-level flow characterisation for correct sizing.",
        ],
    ),

    TI_INDENSE: _TechProfile(
        supply_risk_base="Low",
        opex_impact="Low",
        complexity="Low",
        chemical_dep="None",
        specialist=True,
        energy_class="Low",
        sludge_impact="Medium",   # wasted sludge is denser
        base_feasibility="High",
        notes=[
            "Hydrocyclone-based unit process — compact, low energy.",
            "Specialist supplier required for design and commissioning.",
            "Denser wasted sludge improves dewatering performance.",
        ],
        risks=[
            "Correct hydrocyclone split ratio is critical — requires commissioning support.",
            "Biomass selection may take 4–8 weeks to stabilise after installation.",
        ],
    ),

    TI_MIGINDENSE: _TechProfile(
        supply_risk_base="Low",
        opex_impact="Low",
        complexity="Medium",
        chemical_dep="None",
        specialist=True,
        energy_class="Low",
        sludge_impact="Medium",
        base_feasibility="Medium",
        notes=[
            "Dual-component system: inDENSE (settling) + miGRATE (biofilm carriers).",
            "inDENSE must be commissioned and stable before miGRATE is activated.",
            "Does not remove the need for hydraulic attenuation under extreme wet weather.",
            "Carrier screening required to retain miGRATE media.",
        ],
        risks=[
            "Requires stable biological operation to maintain biomass selection.",
            "Dual specialist supplier dependency (inDENSE + carrier systems).",
        ],
    ),

    TI_MEMDENSE: _TechProfile(
        supply_risk_base="Low",
        opex_impact="Low",
        complexity="Low",
        chemical_dep="None",
        specialist=True,
        energy_class="Low",
        sludge_impact="Medium",
        base_feasibility="High",
        notes=[
            "Selective wasting via hydrocyclone — compact addition to MBR process.",
            "Permeability improvement typically visible within 4–8 weeks of commissioning.",
            "Dependent on correct hydrocyclone operation and split ratio control.",
            # ── MBR architecture context (v24Z41) ───────────────────────────────
            "MBR architecture energy note: membrane scouring and permeate pumping add "
            "0.3–0.8 kWh/m³ vs conventional BNR — the dominant OPEX driver for MBR plants.",
            "MBR operations: regular CIP cleaning (weekly maintenance + biannual intensive), "
            "fouling monitoring, and permeate flux management are ongoing requirements.",
            "MBR membrane lifecycle: replacement typically required every 8–10 years "
            "— OEM supply continuity must be verified before procurement.",
        ],
        risks=[
            "Hydrocyclone split ratio must be calibrated to mixed liquor characteristics.",
            "Specialist supplier required for hydrocyclone sizing and commissioning.",
            "MBR energy penalty: higher operating cost than conventional BNR — "
            "energy-constrained plants should evaluate the OPEX trade-off explicitly.",
        ],
    ),

    TI_HYBAS: _TechProfile(
        supply_risk_base="Low",
        opex_impact="Low",
        complexity="Medium",
        chemical_dep="None",
        specialist=True,
        energy_class="Low",
        sludge_impact="Low",
        base_feasibility="High",
        notes=[
            "Hybas™ is an IFAS variant — hybrid attached-growth retrofit retaining clarifier "
            "and RAS system. Same blower headroom prerequisite as IFAS applies.",
            "Media engineering constraints apply: specific gravity ~0.95–0.98 g/cm³, "
            "PSA for biofilm stability, screen gap matched to media size, FOG tolerance check.",
            "Aeration distribution audit required to confirm uniform carrier fluidisation "
            "across the zone before media installation.",
        ],
        risks=[
            "Aeration headroom prerequisite: if blowers near maximum, MABR is preferred.",
            "Media degradation and microplastic generation risk as per IFAS — carrier "
            "fragmentation, screen escape, and downstream microplastic release are real risks. "
            "Specify durable media and maintain screen integrity monitoring.",
            "Screen fouling or failure causes carrier loss — weekly inspection in first 3 months.",
        ],
    ),

    TI_IFAS: _TechProfile(
        supply_risk_base="Low",
        opex_impact="Low",
        complexity="Low",
        chemical_dep="None",
        specialist=True,
        energy_class="Low",
        sludge_impact="Low",
        base_feasibility="High",
        notes=[
            "Hybrid attached-growth retrofit for municipal BNR nitrification intensification. "
            "Retains clarifier and RAS system — IFAS is a hybrid, not a pure biofilm process.",
            "Only appropriate when aeration blowers have confirmed headroom (≥15% spare). "
            "If blowers are near maximum, MABR is the correct technology.",
            "Media engineering constraints: carrier specific gravity ~0.95–0.98 g/cm³ "
            "for suspension; internal protected surface area (PSA) required for biofilm stability; "
            "media size must match wedge-wire screen gap. FOG-tolerant media required "
            "in high-lipid influent environments.",
            "Supplier strategy: Tier 1 (integrated OEM — bundled process + media, lower "
            "technical risk) vs Tier 2 (commodity media — lower CAPEX, variable durability). "
            "Media selection is a first-class engineering decision, not a procurement afterthought.",
        ],
        risks=[
            "Aeration constraint misidentification: if blowers are at capacity, IFAS will not "
            "resolve nitrification failure. Blower audit is mandatory before IFAS selection.",
            "Media degradation and microplastic generation: mechanical collision and shear can "
            "fragment carriers over time. Plastic slivers may escape retention screens and enter "
            "the effluent stream. Specify robust media with verified durability; monitor screen "
            "integrity as an operating KPI. Consider tertiary capture where microplastic "
            "discharge sensitivity is high.",
            "Retention screen failure causes immediate carrier loss — screen gap and media "
            "size must be matched at design; inspect screens weekly for first 3 months.",
            "Tier 2 commodity media risk: variable quality and durability; supplier performance "
            "must be validated against Tier 1 reference data before deployment at scale.",
        ],
    ),

    TI_MBBR: _TechProfile(
        supply_risk_base="Low",
        opex_impact="Low",
        complexity="Medium",
        chemical_dep="None",
        specialist=True,
        energy_class="Low",
        sludge_impact="Low",
        base_feasibility="High",
        notes=[
            "Pure attached-growth biofilm system — no RAS. Suited to industrial / high-strength "
            "pre-treatment or standalone biological stage, not municipal BNR intensification "
            "(prefer IFAS where clarifier and RAS are retained).",
            "Downstream solids separation is mandatory — MBBR does not clarify; clarifier "
            "loading must be recalculated to account for biofilm solids carryover.",
            "Media engineering constraints: carrier specific gravity, PSA, screen gap matching, "
            "and FOG tolerance apply as per IFAS. Modular capacity addition is a strength.",
            "Supplier strategy: Tier 1 OEM (bundled process + media) vs Tier 2 commodity "
            "(lower cost, variable durability). Tier 3 advanced / organic media (e.g. plant-based "
            "carriers) offers reduced microplastic risk with emerging performance profile. "
            "Media selection represents a trade-off between cost, durability, "
            "environmental impact, and supplier support.",
        ],
        risks=[
            "Media degradation and microplastic generation: mechanical collision generates "
            "plastic slivers that may escape retention screens and enter downstream processes. "
            "Biofilm shear also contributes to particulate microplastic release. "
            "Specify robust media; consider tertiary capture where discharge sensitivity is high.",
            "Downstream clarifier loading increases post-commissioning — verify clarifier "
            "SOR and solids loading capacity with updated biofilm solids estimate.",
            "Tier 2 commodity media quality variability: validate against Tier 1 reference "
            "data for durability and specific gravity stability over time.",
            "Screen gap / media size mismatch causes loss or blinding — specify at design "
            "stage and inspect at weekly intervals for first 3 months.",
        ],
    ),

    TI_MABR: _TechProfile(
        supply_risk_base="Medium",
        opex_impact="Low",
        complexity="Medium",
        chemical_dep="None",
        specialist=True,
        energy_class="Low",   # 14 kgO2/kWh vs 1-2 for diffused aeration
        sludge_impact="Low",
        base_feasibility="Medium",
        notes=[
            "Specialist hollow-fibre membrane modules — OEM supply dependency.",
            "Aeration efficiency up to 14 kgO₂/kWh vs 1–2 for conventional diffused aeration.",
            "Performance dependent on membrane integrity — integrity testing required.",
            "Biofilm thickness control and scour maintenance required.",
        ],
        risks=[
            "Membrane module failure reduces oxygen delivery capacity.",
            "Specialist OEM required for module replacement and performance support.",
        ],
    ),

    TI_BARDENPHO: _TechProfile(
        supply_risk_base="Low",
        opex_impact="Low",
        complexity="Low",
        chemical_dep="Low",   # possible external carbon
        specialist=False,
        energy_class="Low",
        sludge_impact="Low",
        base_feasibility="High",
        notes=[
            "Zone reconfiguration within existing tank — no new civil works.",
            "Internal recycle optimisation: R ≈ 2 is the engineering optimum.",
            "External carbon may be needed if COD/N < 4 — assess before committing.",
        ],
        risks=[
            "Performance depends on carbon availability — low COD/N limits denitrification.",
            "Anaerobic zone must be protected from nitrate return to maintain EBPR.",
        ],
    ),

    TI_RECYCLE_OPT: _TechProfile(
        supply_risk_base="Low",
        opex_impact="Low",
        complexity="Low",
        chemical_dep="None",
        specialist=False,
        energy_class="Low",
        sludge_impact="Low",
        base_feasibility="High",
        notes=[
            "Control system adjustment — no capital spend.",
            "MLR pump capacity must be verified at target recycle ratio.",
        ],
        risks=[
            "DO carry-over at high recycle ratios (R > 4) suppresses denitrification.",
        ],
    ),

    TI_ZONE_RECONF: _TechProfile(
        supply_risk_base="Low",
        opex_impact="Low",
        complexity="Medium",
        chemical_dep="None",
        specialist=False,
        energy_class="Low",
        sludge_impact="Low",
        base_feasibility="High",
        notes=[
            "Baffle installation and diffuser reconfiguration within existing tank.",
            "Modest civil works — no new tank volume.",
        ],
        risks=[
            "Zone sizing must be verified against current and future loads.",
        ],
    ),

    TI_DENFILTER: _TechProfile(
        supply_risk_base="Medium",
        opex_impact="High",
        complexity="High",
        chemical_dep="High",   # methanol
        specialist=True,
        energy_class="Medium",
        sludge_impact="Medium",
        base_feasibility="Medium",
        notes=[
            "Requires continuous methanol (or acetate) dosing: ≈2.5–3.0 mg MeOH per mg NO₃-N removed.",
            "DO carryover from secondary treatment suppresses denitrification — tertiary DO < 0.5 mg/L required.",
            "Requires filter backwash infrastructure and waste management.",
            "Methanol storage, handling, and safety management adds OPEX and regulatory obligation.",
        ],
        risks=[
            "Carbon supply disruption halts tertiary denitrification.",
            "Elevated DO carryover from secondaries will negate filter performance.",
            "High chemical OPEX — methanol cost dominates total operating cost.",
        ],
    ),

    TI_TERT_P: _TechProfile(
        supply_risk_base="Low",
        opex_impact="Medium",
        complexity="Medium",
        chemical_dep="Medium",   # ferric / alum
        specialist=False,
        energy_class="Low",
        sludge_impact="High",   # chemical sludge
        base_feasibility="High",
        notes=[
            "Chemical precipitation (FeCl₃ or alum) is well-established — broad supply base.",
            "Generates additional chemical sludge — dewatering and disposal capacity must be verified.",
            "Dosing rate: 20–25 g FeCl₃ per g P removed at typical wastewater P/alkalinity.",
        ],
        risks=[
            "Chemical sludge volume increases — solids handling capacity must accommodate.",
            "Over-dosing risk: excess ferric can elevate effluent colour and TSS.",
        ],
    ),
}


# ── Location adjustment ────────────────────────────────────────────────────────

def _adjust_supply_risk(base: str, tech: str, location: str, size_mld: float) -> str:
    """Adjust supply risk based on location and plant size."""
    specialist_techs = {TI_COMAG, TI_BIOMAG, TI_MABR, TI_MIGINDENSE, TI_MEMDENSE,
                        TI_HYBAS, TI_IFAS, TI_MBBR, TI_DENFILTER}
    order = {FS_LOW: 0, FS_MEDIUM: 1, FS_HIGH: 2}
    risk  = order.get(base, 1)

    if location == LOC_REMOTE and tech in specialist_techs:
        risk = min(2, risk + 2)     # remote + specialist = always High
    elif location == LOC_REMOTE:
        risk = min(2, risk + 1)
    elif location == LOC_REGIONAL and tech in {TI_COMAG, TI_BIOMAG, TI_MABR, TI_DENFILTER}:
        risk = min(2, risk + 1)

    if size_mld < 5.0 and tech in {TI_COMAG, TI_BIOMAG}:
        risk = min(2, risk + 1)     # magnetite recovery harder at small scale
    elif size_mld < 10.0 and tech in {TI_COMAG, TI_BIOMAG}:
        risk = min(2, max(risk, 1)) # at least Medium for <10 MLD

    return [FS_LOW, FS_MEDIUM, FS_HIGH][risk]


def _stage_feasibility(
    stage: PathwayStage,
    location: str,
    size_mld: float,
) -> StageFeasibility:
    """Evaluate feasibility of a single stage."""
    prof = _PROFILES.get(stage.technology)
    if prof is None:
        return StageFeasibility(
            stage_number=stage.stage_number, technology=stage.technology,
            tech_display=stage.tech_display, feasibility=FS_MEDIUM,
            supply_risk=FS_LOW, opex_impact="Low", complexity="Low",
            chemical_dep="None", specialist=False,
            notes=["Technology not in feasibility library — assessment is indicative."],
            risks=[],
        )

    supply_risk = _adjust_supply_risk(prof.supply_risk_base, stage.technology, location, size_mld)

    # Overall stage feasibility
    order  = _FS_ORDER
    fscore = order[prof.base_feasibility]
    if supply_risk == FS_HIGH:        fscore = min(fscore, 1)   # cap at Medium
    if prof.chemical_dep == "High":   fscore = min(fscore, 1)
    if prof.complexity == "High":     fscore = min(fscore, 1)
    if supply_risk == FS_LOW and prof.chemical_dep in ("None", "Low") and prof.complexity == "Low":
        fscore = max(fscore, 2)       # floor at High for simple techs

    feasibility = [FS_LOW, FS_MEDIUM, FS_HIGH][fscore]

    return StageFeasibility(
        stage_number  = stage.stage_number,
        technology    = stage.technology,
        tech_display  = stage.tech_display,
        feasibility   = feasibility,
        supply_risk   = supply_risk,
        opex_impact   = prof.opex_impact,
        complexity    = prof.complexity,
        chemical_dep  = prof.chemical_dep,
        specialist    = prof.specialist,
        notes         = list(prof.notes),
        risks         = list(prof.risks),
    )


# ── Aggregate feasibility ──────────────────────────────────────────────────────

def _aggregate(stage_list: List[StageFeasibility]) -> Tuple[str, str, str, str, str, str]:
    """
    Aggregate dimension scores from stage list.
    Returns (supply_chain, op_complexity, chem_dep, energy, integration, sludge).
    """
    order = {FS_HIGH: 2, FS_MEDIUM: 1, FS_LOW: 0}
    hi_ord = {"None": 0, "Low": 1, "Medium": 2, "High": 3}

    supply = max((order[s.supply_risk] for s in stage_list), default=0)
    chem   = max((hi_ord.get(s.chemical_dep, 0) for s in stage_list), default=0)
    n_high_complex = sum(1 for s in stage_list if s.complexity == "High")
    n_medium_complex = sum(1 for s in stage_list if s.complexity in ("High", "Medium"))
    op_complexity = (FS_HIGH if n_high_complex >= 2 else
                     FS_MEDIUM if n_medium_complex >= 2 or n_high_complex >= 1 else FS_HIGH)
    energy = max((order.get(s.opex_impact, 1) for s in stage_list), default=1)
    integ  = (FS_HIGH if len(stage_list) >= 4 else
              FS_MEDIUM if len(stage_list) >= 2 else FS_HIGH)
    sludge_hi = any(p.sludge_impact == "High" for t in [s.technology for s in stage_list]
                    for p in [_PROFILES.get(t)] if p)
    sludge = FS_HIGH if sludge_hi else FS_MEDIUM if len(stage_list) >= 3 else FS_HIGH

    supply_str = [FS_LOW, FS_MEDIUM, FS_HIGH][min(supply, 2)]
    chem_str   = ["None", "Low", "Medium", "High"][min(chem, 3)]
    energy_str = [FS_LOW, FS_MEDIUM, FS_HIGH][min(energy, 2)]

    return supply_str, op_complexity, chem_str, energy_str, integ, sludge


def _overall_feasibility(stage_list: List[StageFeasibility]) -> str:
    """Aggregate stage feasibilities to overall."""
    if not stage_list:
        return FS_MEDIUM
    n_low    = sum(1 for s in stage_list if s.feasibility == FS_LOW)
    n_medium = sum(1 for s in stage_list if s.feasibility == FS_MEDIUM)
    has_high_chem  = any(s.chemical_dep == "High" for s in stage_list)
    has_high_supply= any(s.supply_risk == FS_HIGH for s in stage_list)
    if n_low >= 1:
        return FS_LOW
    if n_medium >= 2 or (n_medium >= 1 and len(stage_list) >= 3):
        return FS_MEDIUM
    # High chemical dependency or high supply risk caps overall at Medium
    if has_high_chem or has_high_supply:
        return FS_MEDIUM
    return FS_HIGH


# ── Confidence adjustment ──────────────────────────────────────────────────────

def _adjust_confidence(
    base_confidence: str,
    overall_feasibility: str,
    supply_risk: str,
    n_stages: int,
    n_specialist: int,
    chem_dep: str,
) -> Tuple[str, str, str]:
    """
    Returns (adjusted_confidence, change_label, reason).
    """
    order   = {FS_HIGH: 2, FS_MEDIUM: 1, FS_LOW: 0}
    score   = order.get(base_confidence, 1)
    reasons = []

    if supply_risk == FS_HIGH:
        score -= 1
        reasons.append("high supply chain risk")
    if overall_feasibility == FS_LOW:
        score -= 1
        reasons.append("one or more stages has Low feasibility")
    if n_specialist >= 3:
        score -= 1
        reasons.append(f"{n_specialist} specialist technologies in stack")
    if chem_dep == "High":
        score -= 1
        reasons.append("high chemical dependency (methanol dosing)")

    if n_stages == 1 and supply_risk == FS_LOW:
        score = min(score + 1, 2)
        reasons.append("simple single-stage stack with low supply risk")
    if overall_feasibility == FS_HIGH and n_stages <= 2:
        score = min(score + 1, 2)
        reasons.append("high feasibility compact stack")

    score = max(0, min(2, score))
    adj   = [FS_LOW, FS_MEDIUM, FS_HIGH][score]

    base_score = order.get(base_confidence, 1)
    if score > base_score:     change = "Upgraded"
    elif score < base_score:   change = "Downgraded"
    else:                      change = "Maintained"

    reason = (f"Confidence {change.lower()} because: {'; '.join(reasons)}."
              if reasons else f"Confidence maintained at {adj}.")
    return adj, change, reason


# ── Lower-risk alternative ─────────────────────────────────────────────────────

def _lower_risk_alternative(
    pathway: UpgradePathway,
    stage_list: List[StageFeasibility],
    overall: str,
) -> Optional[LowerRiskAlternative]:
    """Generate a lower-risk alternative when feasibility is Low or has High supply risk."""
    high_risk_stages = [s for s in stage_list
                        if s.feasibility in (FS_LOW, FS_MEDIUM) and s.supply_risk == FS_HIGH]
    if overall == FS_HIGH and not high_risk_stages:
        return None

    changes = []
    trade_offs = []
    new_stages = []

    for sf in stage_list:
        tech = sf.technology
        if tech == TI_COMAG:
            changes.append(f"Replace {sf.tech_display} → Equalisation basin")
            trade_offs.append("Higher CAPEX and footprint requirement for EQ basin vs CoMag.")
            trade_offs.append("EQ basin provides attenuation without magnetite supply dependency.")
            new_stages.append("Equalisation / flow balancing basin")
        elif tech == TI_BIOMAG:
            changes.append(f"Replace {sf.tech_display} → inDENSE® (gravimetric biomass selection)")
            trade_offs.append("inDENSE addresses settling without magnetite supply chain.")
            trade_offs.append("Lower hydraulic relief than BioMag — hydraulic constraint may remain partially.")
            new_stages.append("inDENSE® (gravimetric biomass selection)")
        elif tech == TI_DENFILTER:
            changes.append(f"Replace {sf.tech_display} → Bardenpho zone optimisation + carbon management")
            trade_offs.append("Biological denitrification may not achieve TN < 3 mg/L without external carbon.")
            trade_offs.append("Eliminates methanol dependency and high chemical OPEX.")
            new_stages.append("Bardenpho / process zone optimisation + external carbon assessment")
        else:
            new_stages.append(sf.tech_display)

    if not changes:
        return None

    return LowerRiskAlternative(
        label="Lower-risk alternative stack (reduced specialist supply dependency)",
        stage_changes=changes,
        trade_offs=trade_offs,
        feasibility=FS_MEDIUM,
        capex_impact="Higher" if any("EQ basin" in c for c in changes) else "Similar",
        rationale=(
            "This alternative replaces high-supply-risk or high-chemical-dependency technologies "
            "with more conventional options that have broader supply chains and lower operational "
            "dependency. The trade-off is typically higher footprint or capital cost in exchange "
            "for reduced whole-of-life risk."
        ),
    )


# ── Narrative generators ───────────────────────────────────────────────────────

def _feasibility_summary(
    overall: str,
    supply_risk: str,
    op_complexity: str,
    chem_dep: str,
    n_stages: int,
    location: str,
    pathway: UpgradePathway,
) -> str:
    parts = [
        f"The recommended {n_stages}-stage upgrade pathway for a {pathway.plant_type} plant "
        f"({pathway.plant_size_mld if hasattr(pathway, 'plant_size_mld') else 'unknown size'} MLD) "
        f"has been assessed as {overall.upper()} feasibility overall."
    ]
    if overall == FS_HIGH:
        parts.append(
            "Technologies are well-established with broad supply chains and low operational dependency. "
            "This solution is technically robust and operationally straightforward to implement and sustain."
        )
    elif overall == FS_MEDIUM:
        drivers = []
        if supply_risk == FS_HIGH: drivers.append("specialist supply chain requirements")
        if chem_dep in ("High", "Medium"): drivers.append("chemical dosing dependency")
        if op_complexity in (FS_HIGH, FS_MEDIUM): drivers.append("operational complexity")
        d = " and ".join(drivers) if drivers else "moderate complexity"
        parts.append(
            f"Feasibility is constrained by {d}. "
            "This solution is technically credible but introduces dependencies that require "
            "active management and contingency planning."
        )
    else:
        parts.append(
            "One or more stages introduces high supply chain, operational, or chemical dependency. "
            "A lower-risk alternative stack is recommended for consideration."
        )
    if location == LOC_REMOTE:
        parts.append(
            "Location risk is elevated — remote location increases supply chain exposure "
            "for specialist materials and services."
        )
    return " ".join(parts)


def _key_risks(stage_list: List[StageFeasibility], chem_dep: str) -> List[str]:
    risks = []
    seen  = set()
    for sf in stage_list:
        for r in sf.risks:
            if r not in seen:
                risks.append(r)
                seen.add(r)
    if chem_dep == "High" and not any("carbon" in r.lower() or "methanol" in r.lower() for r in risks):
        risks.insert(0, "High chemical OPEX — methanol supply and dosing control critical.")
    return risks[:6]   # max 6 risks


def _key_mitigations(stage_list: List[StageFeasibility]) -> List[str]:
    mits = []
    has_specialist = any(s.specialist for s in stage_list)
    has_chem = any(s.chemical_dep == "High" for s in stage_list)
    has_mag  = any(s.technology in (TI_COMAG, TI_BIOMAG) for s in stage_list)
    has_biofilm = any(s.technology in (TI_IFAS, TI_HYBAS, TI_MBBR) for s in stage_list)
    has_selective = any(s.technology in (TI_INDENSE, TI_MEMDENSE, TI_MIGINDENSE) for s in stage_list)

    if has_mag:
        mits.append("Pre-qualify magnetite supply and establish local stock before commissioning.")
    if has_specialist:
        mits.append("Engage specialist technology suppliers early in detailed design phase.")
    if has_chem:
        mits.append("Establish dual-supply agreements for methanol and design DO control loop upstream of denitrification filter.")
    if has_biofilm:
        mits.append("Plan 4–8 week biofilm establishment period with adjusted effluent monitoring triggers.")
    if has_selective:
        mits.append("Validate hydrocyclone split ratios during commissioning with biomass characterisation.")
    if len(stage_list) >= 3:
        mits.append("Commission stages sequentially with effluent performance verification before proceeding to next stage.")
    mits.append("Confirm insurance coverage and O&M contract provisions for specialist equipment.")
    return mits[:5]


# ── Dimension scoring ──────────────────────────────────────────────────────────

def _build_dimensions(
    supply_risk: str, op_complexity: str, chem_dep: str,
    energy: str, integ: str, sludge: str,
) -> List[DimensionScore]:
    _inv = {FS_HIGH: FS_HIGH, FS_MEDIUM: FS_MEDIUM, FS_LOW: FS_LOW}
    chem_score = {FS_HIGH: FS_LOW, FS_MEDIUM: FS_MEDIUM, FS_LOW: FS_HIGH,
                  "None": FS_HIGH, "Low": FS_HIGH, "High": FS_LOW}.get(chem_dep, FS_MEDIUM)
    energy_score = {"Low": FS_HIGH, "Medium": FS_MEDIUM, "High": FS_LOW}.get(energy, FS_MEDIUM)

    return [
        DimensionScore("Supply Chain",
                       {"High": FS_LOW, "Medium": FS_MEDIUM, "Low": FS_HIGH}[supply_risk],
                       [f"Supply chain risk: {supply_risk}"]),
        DimensionScore("Operational Complexity",
                       {"High": FS_LOW, "Medium": FS_MEDIUM, "Low": FS_HIGH}[op_complexity],
                       [f"Operational complexity: {op_complexity}"]),
        DimensionScore("Chemical Dependency",
                       chem_score,
                       [f"Chemical dependency level: {chem_dep}"]),
        DimensionScore("Energy / OPEX",
                       energy_score,
                       [f"Energy / OPEX impact: {energy}"]),
        DimensionScore("Integration Risk",
                       {"High": FS_LOW, "Medium": FS_MEDIUM, "Low": FS_HIGH}[integ],
                       [f"Integration complexity: {integ}"]),
        DimensionScore("Sludge / Residuals",
                       {"High": FS_LOW, "Medium": FS_MEDIUM, "Low": FS_HIGH}[sludge],
                       [f"Sludge / residuals impact: {sludge}"]),
    ]


# ── Main entry point ───────────────────────────────────────────────────────────

def assess_feasibility(
    pathway: UpgradePathway,
    plant_context: Optional[Dict] = None,
) -> FeasibilityReport:
    """
    Assess the feasibility of a recommended UpgradePathway.

    Parameters
    ----------
    pathway : UpgradePathway
        Output of build_upgrade_pathway() from stack_generator.py.

    plant_context : dict, optional
        Supplemental context:
          plant_size_mld   float   actual plant flow in MLD
          location_type    str     "metro" / "regional" / "remote"

    Returns
    -------
    FeasibilityReport
        Does NOT modify the pathway object.
    """
    ctx      = plant_context or {}
    size_mld = float(ctx.get("plant_size_mld", pathway.proximity_pct / 50.0) or 10.0)
    location = ctx.get("location_type", LOC_METRO) or LOC_METRO

    # ── Step 1-3: Stage-level scoring ─────────────────────────────────────────
    stage_list = [_stage_feasibility(s, location, size_mld) for s in pathway.stages]

    # ── Step 4: Stack-level aggregation ───────────────────────────────────────
    supply_risk, op_complexity, chem_dep, energy, integ, sludge = _aggregate(stage_list)
    overall = _overall_feasibility(stage_list)

    # ── Step 5: Confidence adjustment ─────────────────────────────────────────
    n_specialist = sum(1 for s in stage_list if s.specialist)
    adj_conf, conf_change, conf_reason = _adjust_confidence(
        pathway.confidence, overall, supply_risk,
        len(stage_list), n_specialist, chem_dep)

    # ── Step 6: Dimensions ────────────────────────────────────────────────────
    dimensions = _build_dimensions(supply_risk, op_complexity, chem_dep, energy, integ, sludge)

    # ── Step 7: Lower-risk alternative ────────────────────────────────────────
    alt = _lower_risk_alternative(pathway, stage_list, overall)

    # ── Step 8: Narrative ─────────────────────────────────────────────────────
    summary = _feasibility_summary(overall, supply_risk, op_complexity,
                                   chem_dep, len(stage_list), location, pathway)
    k_risks = _key_risks(stage_list, chem_dep)
    k_mits  = _key_mitigations(stage_list)

    return FeasibilityReport(
        overall_feasibility    = overall,
        adjusted_confidence    = adj_conf,
        confidence_change      = conf_change,
        confidence_reason      = conf_reason,
        dimensions             = dimensions,
        stage_feasibility      = stage_list,
        supply_chain_risk      = supply_risk,
        operational_complexity = op_complexity,
        chemical_dependency    = chem_dep,
        energy_impact          = energy,
        integration_risk       = integ,
        sludge_residuals_impact= sludge,
        feasibility_summary    = summary,
        key_risks              = k_risks,
        key_mitigations        = k_mits,
        lower_risk_alternative = alt,
    )
