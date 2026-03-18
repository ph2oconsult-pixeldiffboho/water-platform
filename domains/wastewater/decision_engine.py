"""
domains/wastewater/decision_engine.py

Capital Planning Decision Engine
==================================
Transforms engineering outputs into structured investment decision content
aligned with how water utilities conduct options studies.

All content is:
  - Deterministic (rule-based on engineering inputs and outputs)
  - Explainable (every rating has a one-line reason)
  - Engineering-based (no probabilistic modelling, no AI)

The module produces a DecisionPackage per scenario comparison that
feeds directly into the UI (page_11_decision.py) and the report.

References:
  - Infrastructure Australia, Options Analysis Guidance (2021)
  - WEF Manual of Practice 35 — Technology Risk Framework
  - IWA Technology Maturity Review (2022)
  - AS/NZS ISO 31000:2018
  - Typical utility procurement frameworks (D&C, DBOM, Alliance)
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any


# ── Rating scales ─────────────────────────────────────────────────────────────

class Rating(Enum):
    HIGH        = "High"
    MODERATE    = "Moderate"
    LOW         = "Low"
    NOT_SUITED  = "Not suited"

    @property
    def icon(self) -> str:
        return {"High": "🟢", "Moderate": "🟡", "Low": "🔴",
                "Not suited": "⛔"}[self.value]


class Complexity(Enum):
    LOW          = "Low"
    MODERATE     = "Moderate"
    MODERATE_HIGH = "Moderate–High"
    HIGH         = "High"

    @property
    def icon(self) -> str:
        return {"Low": "🟢", "Moderate": "🟡",
                "Moderate–High": "🟠", "High": "🔴"}[self.value]


# ── Data structures ───────────────────────────────────────────────────────────

@dataclass
class DeliveryModelAssessment:
    """Suitability of a technology for each procurement model."""
    dnc:      Rating        # Design & Construct
    dnc_note: str
    dbom:     Rating        # Design Build Operate Maintain
    dbom_note: str
    alliance: Rating        # Alliance / ECI (Early Contractor Involvement)
    alliance_note: str
    recommended_model: str  # e.g. "D&C" or "DBOM / Alliance"
    procurement_note: str


@dataclass
class ConstructabilityAssessment:
    """Brownfield integration and civil construction risk."""
    overall:             Complexity
    footprint_flag:      str        # e.g. "Compact — favourable for constrained sites"
    tie_in_risk:         str        # e.g. "Moderate — parallel operation required"
    shutdown_risk:       str        # e.g. "Low — new build alongside live plant"
    civil_complexity:    str
    mechanical_complexity: str
    brownfield_note:     str        # Integrating into existing plant summary


@dataclass
class StagingPathway:
    """Whether and how a technology can be staged or upgraded."""
    can_stage:      bool
    stage_note:     str
    stages:         List[str]       # ["Stage 1: ...", "Stage 2: ..."]
    upgrade_from:   List[str]       # Technologies this can upgrade from
    upgrade_to:     List[str]       # Technologies this can upgrade to
    flexibility_note: str


@dataclass
class OperationalComplexity:
    """Day-to-day operational burden — separate from risk."""
    overall:          Complexity
    automation_need:  str    # "Low / standard SCADA" etc.
    operator_skill:   str    # "Level 2 operator" etc.
    process_sensitivity: str # "Low — robust to load variations" etc.
    maintenance_note: str
    training_note:    str


@dataclass
class FailureMode:
    """A single failure mode entry."""
    name:       str
    likelihood: str   # "Low" / "Moderate" / "High"
    consequence: str  # "Low" / "Moderate" / "High" / "Severe"
    mitigation: str


@dataclass
class FailureModeProfile:
    """All key failure modes for a technology."""
    modes: List[FailureMode]
    critical_note: str   # The one thing that can go catastrophically wrong


@dataclass
class RegulatoryConfidence:
    """Regulator familiarity and approval likelihood."""
    overall:       Rating
    familiarity:   str    # "Well understood — >30yr of data in AUS"
    approval_risk: str    # "Low — standard secondary treatment"
    epa_precedent: str    # "Many approved AUS plants"
    public_acceptance: str
    note:          str


@dataclass
class TechnologyDecisionProfile:
    """Complete decision profile for one treatment technology."""
    tech_code:       str
    tech_label:      str
    delivery:        DeliveryModelAssessment
    constructability: ConstructabilityAssessment
    staging:         StagingPathway
    ops_complexity:  OperationalComplexity
    failure_modes:   FailureModeProfile
    regulatory:      RegulatoryConfidence


@dataclass
class AlternativePathway:
    """An engineered intervention that makes a non-viable technology viable."""
    tech_code:       str
    tech_label:      str
    intervention:    str          # e.g. "Extended SRT + thermal management + supplemental carbon"
    capex_delta_m:   float        # incremental CAPEX vs base technology ($M)
    opex_delta_k:    float        # incremental OPEX vs base technology ($k/yr)
    lcc_total_k:     float        # total LCC of this pathway ($k/yr)
    achieves_compliance: bool
    residual_risks:  List[str]
    procurement:     str          # e.g. "D&C viable"
    regulatory:      str          # e.g. "High confidence"
    summary:         str          # one-paragraph narrative
    base_capex_m:    float = 0.0  # base technology CAPEX without intervention ($M)


@dataclass
class ClientDecisionFraming:
    """Two-option framing for executive/board presentation."""
    option_a_label:  str
    option_a_bullets: List[str]   # what client gets
    option_a_risks:  List[str]
    option_b_label:  str
    option_b_bullets: List[str]
    option_b_risks:  List[str]
    deciding_factors: List[str]   # "Decision depends on:"
    framing_note:    str


@dataclass
class RecommendationConfidence:
    """How confident the tool is in the recommendation."""
    level:           str          # "High" | "Moderate" | "Low"
    drivers:         List[str]    # reasons for confidence level
    caveats:         List[str]    # what could change the recommendation


@dataclass
class ScenarioDecision:
    """
    Complete decision output for a scenario comparison.
    Produced by evaluate_scenario() and consumed by the UI and report.
    """
    # Selection hierarchy: compliance → cost → risk (explicit)
    selection_basis:    str       # "Sole compliant option" | "Lowest LCC" | "Risk-adjusted LCC"
    recommended_tech:   str
    recommended_label:  str
    display_recommended_label: str  # UI/report label — may include qualifier
    non_viable:         List[str]   # scenarios that fail compliance
    why_recommended:    List[str]   # precise bullets aligned with selection_basis
    key_risks:          List[str]
    regulatory_note:    str         # explicit note on regulatory vs compliance tension
    alternative_tech:   Optional[str]
    alternative_label:  Optional[str]
    alternative_note:   str
    alternative_pathways: List[AlternativePathway]   # interventions for non-viable options
    client_framing:     Optional[ClientDecisionFraming]
    confidence:         Optional[RecommendationConfidence]
    conclusion:         str
    trade_offs:         List[str]   # decision-driving, not descriptive
    profiles:           Dict[str, TechnologyDecisionProfile]
    strategic_insight:  str = ""   # process intensification vs robustness framing
    recommended_approach: List[str] = field(default_factory=list)  # parallel eval steps
    weighted_decision:  Optional[Any] = None  # DecisionResult from ScoringEngine


# ── Technology knowledge base ─────────────────────────────────────────────────

_TECH_LABELS = {
    "bnr":             "BNR (Activated Sludge)",
    "granular_sludge": "Aerobic Granular Sludge",
    "mabr_bnr":        "MABR + BNR",
    "bnr_mbr":         "BNR + MBR",
    "ifas_mbbr":       "IFAS / MBBR",
    "anmbr":           "Anaerobic MBR",
    "adv_reuse":       "Advanced Reuse (UF+RO+UV)",
    "sidestream_pna":  "Sidestream PN/A (Anammox)",
    "thermal_biosolids": "Thermal Biosolids Treatment",
    "tertiary_filt":   "Tertiary Filtration",
    "cpr":             "Chemical P Removal",
    "ad_chp":          "Anaerobic Digestion + CHP",
    "mob":             "Mobile Organic Biofilm",
}


def _delivery(tech_code: str, flow_mld: float) -> DeliveryModelAssessment:
    """Delivery model suitability based on technology maturity and complexity."""

    if tech_code == "bnr":
        return DeliveryModelAssessment(
            dnc=Rating.HIGH,
            dnc_note="Mature technology — well-understood scope, bankable cost estimates, "
                     "many experienced D&C contractors in AUS market.",
            dbom=Rating.MODERATE,
            dbom_note="DBOM viable but O&M cost certainty limits operator interest "
                      "at flows <10 MLD; more attractive at larger scale.",
            alliance=Rating.HIGH,
            alliance_note="Alliance appropriate for complex brownfield upgrades or "
                          "where tight programme requires early contractor involvement.",
            recommended_model="D&C",
            procurement_note="D&C preferred for standard BNR. DBOM for large-scale "
                             "(>20 MLD) with long-term O&M certainty required.",
        )

    elif tech_code == "granular_sludge":
        return DeliveryModelAssessment(
            dnc=Rating.MODERATE,
            dnc_note="Proprietary process (Nereda/similar) — single-vendor dependency "
                     "limits competitive D&C tension. Contractor must be vendor-aligned.",
            dbom=Rating.HIGH,
            dbom_note="DBOM strongly preferred: vendor accountability for granule "
                      "commissioning risk, long-term process guarantees, and "
                      "performance-based payment structures.",
            alliance=Rating.HIGH,
            alliance_note="Alliance/ECI highly suitable — allows early vendor "
                          "involvement in design to manage granule seeding logistics "
                          "and commissioning programme.",
            recommended_model="DBOM / Alliance",
            procurement_note="DBOM strongly recommended. Requires performance "
                             "guarantees covering granule formation period (6–18 months). "
                             "D&C acceptable only with specialist contractor.",
        )

    elif tech_code == "mabr_bnr":
        return DeliveryModelAssessment(
            dnc=Rating.LOW,
            dnc_note="Very limited reference base (<50 plants globally, 2024). "
                     "Standard D&C inappropriate — insufficient cost certainty "
                     "and contractor capability.",
            dbom=Rating.HIGH,
            dbom_note="DBOM essential: vendor must carry process performance risk. "
                      "Long-term O&M by vendor maintains membrane system integrity "
                      "and process knowledge.",
            alliance=Rating.HIGH,
            alliance_note="Alliance/ECI preferred for first-of-kind applications — "
                          "allows design development alongside vendor and management "
                          "of emerging technology risk.",
            recommended_model="DBOM / Alliance",
            procurement_note="Do not procure MABR via standard D&C. Vendor must "
                             "be engaged under DBOM or ECI. Pilot or demonstration "
                             "plant data required before full commitment.",
        )

    elif tech_code == "bnr_mbr":
        return DeliveryModelAssessment(
            dnc=Rating.MODERATE,
            dnc_note="BNR component is standard D&C. MBR membrane system requires "
                     "vendor-specific scope — limits open competition.",
            dbom=Rating.HIGH,
            dbom_note="DBOM preferred for membrane system: lifecycle guarantee, "
                      "membrane replacement schedule, and cleaning regime "
                      "managed by operator with vendor accountability.",
            alliance=Rating.MODERATE,
            alliance_note="Alliance appropriate for integrated reuse schemes where "
                          "MBR is part of a broader AWT system.",
            recommended_model="DBOM",
            procurement_note="DBOM preferred for membrane component. Consider "
                             "separating civil/structural (D&C) from membrane system "
                             "(DBOM) in procurement structure.",
        )

    elif tech_code == "ifas_mbbr":
        return DeliveryModelAssessment(
            dnc=Rating.HIGH,
            dnc_note="Media system is a well-established retrofit — D&C contractors "
                     "can competitively supply and install IFAS/MBBR carriers.",
            dbom=Rating.MODERATE,
            dbom_note="DBOM viable where capacity upgrade is part of wider O&M contract.",
            alliance=Rating.HIGH,
            alliance_note="Alliance well-suited for brownfield upgrade to existing "
                          "aeration tanks — complex tie-ins benefit from ECI.",
            recommended_model="D&C",
            procurement_note="D&C standard. Alliance appropriate for brownfield "
                             "retrofit with complex existing infrastructure.",
        )

    else:
        return DeliveryModelAssessment(
            dnc=Rating.MODERATE,
            dnc_note="Specialist technology — verify contractor capability.",
            dbom=Rating.MODERATE,
            dbom_note="DBOM viable where vendor accountability is important.",
            alliance=Rating.MODERATE,
            alliance_note="Alliance appropriate for novel or complex applications.",
            recommended_model="Assess case by case",
            procurement_note="Procurement model should be confirmed with specialist "
                             "input based on local market capability.",
        )


def _constructability(tech_code: str, flow_mld: float, footprint_m2: float,
                      is_brownfield: bool = True) -> ConstructabilityAssessment:
    """Brownfield integration and construction risk assessment."""

    if tech_code == "bnr":
        bf = ("Existing activated sludge plant: moderate tie-in complexity. "
              "New BNR requires additional anoxic zones — can be retrofitted "
              "into existing aeration lanes with zone baffling."
              if is_brownfield else
              "Greenfield: standard construction sequence, no tie-in risk.")
        return ConstructabilityAssessment(
            overall=Complexity.MODERATE,
            footprint_flag=f"{footprint_m2:.0f} m² — standard footprint for conventional BNR",
            tie_in_risk="Moderate — existing clarifiers can typically be retained; "
                        "parallel operation required during cutover.",
            shutdown_risk="Low–Moderate — phased upgrade possible; "
                          "flow diversion to existing treatment during construction.",
            civil_complexity="Standard reinforced concrete basins. "
                             "Well-understood construction methodology.",
            mechanical_complexity="Standard blowers, mixers, RAS/WAS pumps. "
                                  "Wide contractor base in AUS.",
            brownfield_note=bf,
        )

    elif tech_code == "granular_sludge":
        return ConstructabilityAssessment(
            overall=Complexity.MODERATE,
            footprint_flag=f"{footprint_m2:.0f} m² — 30–40% smaller than equivalent BNR. "
                           "Favourable for constrained sites.",
            tie_in_risk="Moderate — SBR cycle timing requires dedicated inlet flow "
                        "control. Existing clarifiers typically decommissioned.",
            shutdown_risk="Moderate — full-plant conversion typically required. "
                          "Granule seeding requires controlled startup; existing "
                          "treatment must remain online during transition.",
            civil_complexity="SBR basins: standard RC construction but requires "
                             "high-precision flow distribution and decanting systems.",
            mechanical_complexity="Moderate–High — proprietary decanting mechanism, "
                                  "precise flow distribution, granule seeding logistics.",
            brownfield_note="Challenging brownfield fit: existing circular clarifiers "
                            "cannot be reused as AGS reactors. New SBR basins required. "
                            "Best suited for plants with available greenfield area.",
        )

    elif tech_code == "mabr_bnr":
        return ConstructabilityAssessment(
            overall=Complexity.HIGH,
            footprint_flag=f"{footprint_m2:.0f} m² — larger than BNR due to membrane "
                           "cassette installation space requirements.",
            tie_in_risk="High — membrane modules require factory assembly and careful "
                        "site installation. Limited contractor experience in AUS.",
            shutdown_risk="Low (construction) / High (commissioning) — new tanks built "
                          "alongside existing plant but biofilm establishment requires "
                          "12–24 months controlled operating period.",
            civil_complexity="Standard RC tanks but membrane support structures require "
                             "precision tolerancing. Vendor-specific civil design.",
            mechanical_complexity="High — membrane cassettes, gas-side pressure control, "
                                  "automated backwash/maintenance cycle systems. "
                                  "Vendor-supplied and installed.",
            brownfield_note="Limited brownfield reuse possible. MABR cassettes cannot "
                            "be installed into existing aeration tanks without structural "
                            "modifications. Vendor pilot data required for this site.",
        )

    elif tech_code == "bnr_mbr":
        return ConstructabilityAssessment(
            overall=Complexity.HIGH,
            footprint_flag=f"{footprint_m2:.0f} m² — compact biological zone but "
                           "membrane hall adds significant footprint.",
            tie_in_risk="High — membrane system requires independent hydraulic circuit, "
                        "permeate pumping, and chemical dosing systems. Complex P&ID.",
            shutdown_risk="Moderate — BNR zone can be commissioned first; membrane "
                          "system added in Stage 2 if staged approach adopted.",
            civil_complexity="High — membrane tank requires specific depth and geometry "
                             "for submerged modules. Significant structural design input.",
            mechanical_complexity="Very High — membrane modules, vacuum permeate pumps, "
                                  "CIP chemical systems, backpulse systems, "
                                  "fine screens (3–6 mm pre-screening mandatory).",
            brownfield_note="Significant brownfield challenge: existing secondary "
                            "clarifiers cannot be converted to MBR tanks without major "
                            "structural work. Preferred as new build alongside existing plant.",
        )

    elif tech_code == "ifas_mbbr":
        return ConstructabilityAssessment(
            overall=Complexity.LOW,
            footprint_flag=f"{footprint_m2:.0f} m² — similar to BNR; media fills "
                           "existing aeration volume.",
            tie_in_risk="Low — media can be installed into existing aeration tanks "
                        "without significant civil modification.",
            shutdown_risk="Low — media installation can be done in individual tank "
                          "compartments while others remain in service.",
            civil_complexity="Low — existing RC tanks retained. Media retention screens "
                             "at tank outlets are the primary civil addition.",
            mechanical_complexity="Moderate — media retention screens, carrier media "
                                  "installation, possible aeration system upgrade for "
                                  "higher O₂ demand.",
            brownfield_note="Excellent brownfield fit — lowest tie-in risk of all "
                            "upgrade technologies. Preferred for capacity augmentation "
                            "of existing activated sludge plants without civil works.",
        )

    else:
        fp_flag = f"{footprint_m2:.0f} m²" if footprint_m2 > 0 else "Not calculated"
        return ConstructabilityAssessment(
            overall=Complexity.MODERATE,
            footprint_flag=fp_flag,
            tie_in_risk="Verify with specialist — integration complexity depends "
                        "on existing plant configuration.",
            shutdown_risk="Assess on site-specific basis.",
            civil_complexity="Specialist input required.",
            mechanical_complexity="Specialist input required.",
            brownfield_note="No standard brownfield guidance available — "
                            "site-specific assessment required.",
        )


def _staging(tech_code: str, flow_mld: float) -> StagingPathway:
    """Staging flexibility and upgrade pathway definition."""

    if tech_code == "bnr":
        return StagingPathway(
            can_stage=True,
            stage_note="BNR is the most flexible technology for staged delivery. "
                       "Capacity can be added module by module.",
            stages=[
                "Stage 1: Conventional BNR — BOD/TSS/NH₄ compliance",
                "Stage 2: Optimise anoxic zones — improve TN removal",
                "Stage 3: Add IFAS carriers — increase capacity without new basins",
                "Stage 4: Add MABR or tertiary polishing — for tighter TN/TP targets",
            ],
            upgrade_from=["extended_aeration", "conventional_as", "facultative_ponds"],
            upgrade_to=["ifas_mbbr", "mabr_bnr", "bnr_mbr", "tertiary_filt"],
            flexibility_note="Highest upgrade flexibility of all technologies. "
                             "Incremental investment possible as catchment grows.",
        )

    elif tech_code == "granular_sludge":
        return StagingPathway(
            can_stage=False,
            stage_note="AGS is typically a full-conversion technology. "
                       "Partial implementation creates mixed sludge that destabilises "
                       "granule formation.",
            stages=[
                "Stage 1: Full AGS installation — all-or-nothing conversion",
                "Stage 2 (optional): Add ferric P removal system if TP target tightens",
                "Stage 3 (optional): Add tertiary filtration for TSS polishing",
            ],
            upgrade_from=["bnr"],
            upgrade_to=["tertiary_filt", "cpr"],
            flexibility_note="Limited staging flexibility. Commit to full AGS capacity "
                             "upfront. Best suited where full-site conversion is acceptable "
                             "and long-term capacity is known.",
        )

    elif tech_code == "mabr_bnr":
        return StagingPathway(
            can_stage=True,
            stage_note="MABR cassettes can be added to existing BNR tanks in stages. "
                       "Stage 1 typically retrofits one train while others remain BNR.",
            stages=[
                "Stage 1: Install MABR cassettes in first BNR train (pilot validation)",
                "Stage 2: Extend MABR to remaining trains if Stage 1 performance confirmed",
                "Stage 3: Full MABR operation with optimised gas-side pressure control",
            ],
            upgrade_from=["bnr"],
            upgrade_to=["full_mabr"],
            flexibility_note="Moderate staging flexibility — allows progressive "
                             "de-risking of novel technology before full commitment. "
                             "Stage 1 serves as a full-scale pilot.",
        )

    elif tech_code == "bnr_mbr":
        return StagingPathway(
            can_stage=True,
            stage_note="BNR and MBR components can be staged: BNR first for "
                       "BOD/NH₄ compliance, MBR added when reuse pathway confirmed.",
            stages=[
                "Stage 1: BNR installation — secondary treatment compliance",
                "Stage 2: Add membrane hall and permeate system — upgrade to MBR",
                "Stage 3: Connect to advanced water treatment train (UF/RO/UV) "
                          "for full reuse pathway",
            ],
            upgrade_from=["bnr"],
            upgrade_to=["adv_reuse"],
            flexibility_note="Designed for staged investment — avoid committing to "
                             "full MBR CAPEX until reuse pathway is confirmed by "
                             "regulator and utility strategy.",
        )

    elif tech_code == "ifas_mbbr":
        return StagingPathway(
            can_stage=True,
            stage_note="IFAS media fill fraction can be increased progressively "
                       "to expand nitrification capacity without new basins.",
            stages=[
                "Stage 1: Install media in first aeration zone (30% fill) — "
                          "capacity augmentation",
                "Stage 2: Increase fill fraction to 50% — further capacity",
                "Stage 3: Add second-stage IFAS for dedicated nitrification if needed",
            ],
            upgrade_from=["conventional_as", "bnr"],
            upgrade_to=["bnr", "mabr_bnr"],
            flexibility_note="Most incremental upgrade path available. "
                             "Ideal for utilities needing capacity today with "
                             "flexibility to upgrade further.",
        )

    else:
        return StagingPathway(
            can_stage=None,
            stage_note="Staging flexibility not assessed for this technology — "
                       "specialist input required.",
            stages=["Specialist assessment required"],
            upgrade_from=[],
            upgrade_to=[],
            flexibility_note="Contact technology specialist for staging guidance.",
        )


def _ops_complexity(tech_code: str, flow_mld: float) -> OperationalComplexity:
    """Day-to-day operational complexity — distinct from risk."""

    if tech_code == "bnr":
        return OperationalComplexity(
            overall=Complexity.LOW,
            automation_need="Standard SCADA with DO/ORP control. "
                            "No specialist automation required.",
            operator_skill="Level 2 licensed operator. "
                           "Available from general activated sludge skill pool.",
            process_sensitivity="Low — robust to influent variation. "
                                "Tolerates ±20% load variation without process upset.",
            maintenance_note="Standard: blower service, pump maintenance, "
                             "clarifier mechanism servicing. "
                             "Mature supply chain for all components.",
            training_note="Standard activated sludge training applies. "
                          "No specialist vendor training required.",
        )

    elif tech_code == "granular_sludge":
        return OperationalComplexity(
            overall=Complexity.HIGH,
            automation_need="Advanced SCADA with cycle-time optimisation, "
                            "granule size monitoring, and automated feast/famine control. "
                            "Vendor-specific process control software.",
            operator_skill="Specialist operator training required. "
                           "Granule stability requires understanding of feast/famine "
                           "dynamics — not available from standard AS training.",
            process_sensitivity="High — granule formation sensitive to: "
                                "high-frequency flow variation, seeding sludge quality, "
                                "temperature change >5°C/week, and toxic slug loads.",
            maintenance_note="Moderate civil maintenance. "
                             "Decanting mechanism is proprietary — single-source spare parts. "
                             "Allow 12–18 months for stable granule bed establishment.",
            training_note="Vendor-delivered training essential. "
                          "Recommend operator secondment to reference plant before startup.",
        )

    elif tech_code == "mabr_bnr":
        return OperationalComplexity(
            overall=Complexity.MODERATE_HIGH,
            automation_need="Advanced: gas-side pressure control, "
                            "biofilm thickness monitoring, automated backwash scheduling. "
                            "Vendor control system with remote monitoring.",
            operator_skill="Moderate–High: biofilm management plus standard BNR operation. "
                           "Membrane cassette maintenance requires trained technician.",
            process_sensitivity="Moderate — biofilm more robust than granules but "
                                "sensitive to gas-side fouling and oxygen transfer decline. "
                                "Quarterly membrane inspection recommended.",
            maintenance_note="High: membrane cassette inspection and cleaning, "
                             "gas distribution system maintenance, "
                             "biofilm thickness management. "
                             "Vendor service contract strongly recommended.",
            training_note="Vendor training mandatory. "
                          "Pilot plant operation experience preferred. "
                          "Limited AUS operator experience pool currently.",
        )

    elif tech_code == "bnr_mbr":
        return OperationalComplexity(
            overall=Complexity.HIGH,
            automation_need="High: membrane flux monitoring, TMP trending, "
                            "automated CIP scheduling, permeate quality monitoring. "
                            "Vendor SCADA integration required.",
            operator_skill="High: membrane operation, CIP chemical handling, "
                           "fine screen management, permeate quality monitoring. "
                           "Dedicated MBR operator role at flows >5 MLD.",
            process_sensitivity="Moderate–High — membrane fouling sensitive to: "
                                "high TSS loads, grease/oil slugs, chemical dosing errors, "
                                "and insufficient pre-screening.",
            maintenance_note="High: membrane replacement programme ($300–500k/10yr at 10 MLD), "
                             "CIP chemical costs, fine screen maintenance, "
                             "permeate pump servicing.",
            training_note="Membrane manufacturer training required. "
                          "CIP safety training (acid/caustic) mandatory. "
                          "Annual vendor support visit recommended.",
        )

    elif tech_code == "ifas_mbbr":
        return OperationalComplexity(
            overall=Complexity.MODERATE,
            automation_need="Standard SCADA plus media loss monitoring "
                            "(screen differential pressure). "
                            "Minor addition to standard BNR automation.",
            operator_skill="Level 2 plus IFAS-specific training (1–2 days). "
                           "Media management and screen cleaning added to routine.",
            process_sensitivity="Low–Moderate — biofilm more robust than "
                                "suspended growth but media retention screens "
                                "require regular inspection.",
            maintenance_note="Low incremental: "
                             "media retention screen cleaning (weekly), "
                             "media loss monitoring, "
                             "standard BNR equipment maintenance unchanged.",
            training_note="Short vendor training sufficient. "
                          "Existing BNR operators can be upskilled rapidly.",
        )

    else:
        return OperationalComplexity(
            overall=Complexity.MODERATE,
            automation_need="Specialist assessment required.",
            operator_skill="Specialist assessment required.",
            process_sensitivity="Specialist assessment required.",
            maintenance_note="Specialist assessment required.",
            training_note="Specialist assessment required.",
        )


def _failure_modes(tech_code: str) -> FailureModeProfile:
    """Key failure modes that planners and utilities must understand."""

    if tech_code == "bnr":
        return FailureModeProfile(
            modes=[
                FailureMode(
                    name="Loss of nitrification — cold temperature",
                    likelihood="Moderate (seasonal)", consequence="High",
                    mitigation="Design SRT for minimum temperature; provide thermal lag "
                               "through covered tanks or supplemental heating in cold climates.",
                ),
                FailureMode(
                    name="Sludge bulking / poor settling",
                    likelihood="Moderate", consequence="Moderate",
                    mitigation="Selector zone design, DO management, chlorination of return "
                               "sludge, polymer dosing. Well-understood management protocols.",
                ),
                FailureMode(
                    name="Foaming events (Nocardia/Microthrix)",
                    likelihood="Low–Moderate", consequence="Moderate",
                    mitigation="SRT control, fat/oil screening, chlorination. "
                               "Seasonal risk in warmer climates.",
                ),
                FailureMode(
                    name="Phosphorus release under anaerobic conditions",
                    likelihood="Low", consequence="Moderate",
                    mitigation="Maintain aerobic conditions in secondary clarifiers, "
                               "avoid sludge blanket build-up.",
                ),
            ],
            critical_note="Nitrification failure in cold weather is the primary critical "
                          "failure mode — design SRT conservatively for minimum temperature.",
        )

    elif tech_code == "granular_sludge":
        return FailureModeProfile(
            modes=[
                FailureMode(
                    name="Granule washout / bed instability",
                    likelihood="Moderate (commissioning)", consequence="Severe",
                    mitigation="Use active seeding sludge, controlled feast/famine cycle, "
                               "commissioning performance guarantees from vendor.",
                ),
                FailureMode(
                    name="Granule fragmentation — cold temperature",
                    likelihood="High (<10°C)", consequence="High",
                    mitigation="Not recommended below 10°C. Thermal management required "
                               "in cold climates. Covered reactors for <12°C sites.",
                ),
                FailureMode(
                    name="Settling instability — toxic or shock loads",
                    likelihood="Low", consequence="High",
                    mitigation="Influent screening and flow equalisation. "
                               "Industrial trade waste agreements essential.",
                ),
                FailureMode(
                    name="Decanting mechanism failure",
                    likelihood="Low", consequence="Moderate",
                    mitigation="Proprietary component — single-source supply. "
                               "Maintain critical spare parts on site.",
                ),
            ],
            critical_note="Granule bed failure during commissioning is the single most "
                          "critical risk — vendor performance guarantees and seeding "
                          "protocol are non-negotiable.",
        )

    elif tech_code == "mabr_bnr":
        return FailureModeProfile(
            modes=[
                FailureMode(
                    name="Membrane fouling — gas-side blockage",
                    likelihood="Moderate", consequence="High",
                    mitigation="Automated backpulse protocol, regular chemical cleaning, "
                               "vendor monitoring programme.",
                ),
                FailureMode(
                    name="Oxygen transfer decline — biofilm overgrowth",
                    likelihood="Moderate", consequence="High",
                    mitigation="Biofilm thickness monitoring, periodic chemical clean, "
                               "vendor service agreement.",
                ),
                FailureMode(
                    name="Biofilm loss — shock or toxic load",
                    likelihood="Low", consequence="Severe",
                    mitigation="Biofilm re-establishment takes 3–6 months. "
                               "Industrial trade waste management critical.",
                ),
                FailureMode(
                    name="Membrane integrity failure — fibre breakage",
                    likelihood="Low", consequence="Moderate",
                    mitigation="Integrity testing programme, spare cassettes on site, "
                               "vendor repair service.",
                ),
            ],
            critical_note="Biofilm loss after toxic shock is the critical failure mode. "
                          "Recovery requires 3–6 months — compliance breach during recovery "
                          "is unavoidable without bypass/emergency treatment capacity.",
        )

    elif tech_code == "bnr_mbr":
        return FailureModeProfile(
            modes=[
                FailureMode(
                    name="Membrane fouling — irreversible",
                    likelihood="Moderate", consequence="High",
                    mitigation="Regular CIP, flux management, pre-screening maintenance, "
                               "avoid oil/grease bypass to membrane zone.",
                ),
                FailureMode(
                    name="Fine screen failure — membrane damage",
                    likelihood="Low", consequence="Severe",
                    mitigation="Redundant screening (2×100%), immediate alarm and isolation "
                               "of membrane zone on screen failure.",
                ),
                FailureMode(
                    name="TMP exceedance — loss of flux",
                    likelihood="Moderate", consequence="Moderate",
                    mitigation="Automated TMP monitoring, reduced flux operation during "
                               "high-load periods.",
                ),
                FailureMode(
                    name="Permeate pump failure — loss of production",
                    likelihood="Low", consequence="High",
                    mitigation="N+1 pump configuration standard. Duty/standby operation.",
                ),
            ],
            critical_note="Fine screen failure leading to membrane damage is the most "
                          "severe failure mode — potential for complete membrane "
                          "replacement ($1–3M) if coarse solids reach membrane zone.",
        )

    elif tech_code == "ifas_mbbr":
        return FailureModeProfile(
            modes=[
                FailureMode(
                    name="Media retention screen failure — media loss",
                    likelihood="Low", consequence="High",
                    mitigation="Regular screen inspection, downstream strainer, "
                               "media inventory monitoring.",
                ),
                FailureMode(
                    name="Biofilm wash-off — nitrification loss",
                    likelihood="Low", consequence="Moderate",
                    mitigation="Gradual load increase during commissioning, "
                               "avoid hydraulic shock loads.",
                ),
                FailureMode(
                    name="Aeration system fouling — media clumping",
                    likelihood="Low", consequence="Low",
                    mitigation="Regular aeration system inspection, diffuser cleaning.",
                ),
            ],
            critical_note="Media loss through screen failure is the most costly failure — "
                          "replacement media lead times can be 8–16 weeks. "
                          "Maintain minimum 10% media inventory on site.",
        )

    else:
        return FailureModeProfile(
            modes=[
                FailureMode(
                    name="Technology-specific failure",
                    likelihood="Unknown", consequence="Unknown",
                    mitigation="Specialist assessment required.",
                ),
            ],
            critical_note="No standard failure mode profile — specialist input required.",
        )


def _regulatory(tech_code: str) -> RegulatoryConfidence:
    """Regulator familiarity and approval likelihood in Australia."""

    if tech_code == "bnr":
        return RegulatoryConfidence(
            overall=Rating.HIGH,
            familiarity="Highest — BNR secondary treatment has 30+ year regulatory "
                        "history in Australia. Well-understood by all state EPAs.",
            approval_risk="Low — standard secondary treatment approval pathway. "
                          "No novel technology assessment required.",
            epa_precedent="Hundreds of approved plants across Australia. "
                          "EPA assessment officers familiar with technology.",
            public_acceptance="High — well-established, no public concern issues.",
            note="No regulatory barriers to BNR. Standard environmental "
                 "assessment pathway applies.",
        )

    elif tech_code == "granular_sludge":
        return RegulatoryConfidence(
            overall=Rating.MODERATE,
            familiarity="Moderate — growing AUS experience (10+ full-scale plants). "
                        "State EPAs increasingly familiar but individual officer "
                        "knowledge varies.",
            approval_risk="Moderate — novel technology assessment may be required "
                          "in some jurisdictions. Allow 3–6 months additional approval time.",
            epa_precedent="Full-scale Nereda plants in Netherlands and Belgium. "
                          "Several AUS installations (VIC, NSW, QLD).",
            public_acceptance="High — compact footprint and lower sludge are "
                              "positively perceived.",
            note="Pre-application meeting with EPA recommended to confirm "
                 "approval pathway and monitoring requirements.",
        )

    elif tech_code == "mabr_bnr":
        return RegulatoryConfidence(
            overall=Rating.LOW,
            familiarity="Low — very limited AUS regulatory experience. "
                        "<5 full-scale installations in AUS (2024). "
                        "Novel technology assessment certain.",
            approval_risk="High — regulator will likely require demonstration "
                          "period, enhanced monitoring, and contingency plan. "
                          "Allow 6–12 months additional approval time.",
            epa_precedent="Full-scale reference plants in North America and Europe. "
                          "No significant AUS EPA precedent.",
            public_acceptance="Moderate — 'membrane' technology perceived positively "
                              "but limited public awareness.",
            note="Early regulator engagement essential — BEFORE procurement. "
                 "Consider pilot plant requirement. Novel technology risk "
                 "assessment under EPL/works approval likely required.",
        )

    elif tech_code == "bnr_mbr":
        return RegulatoryConfidence(
            overall=Rating.MODERATE,
            familiarity="Moderate–High — MBR for reuse is established in AUS "
                        "(several reference plants). BNR component is standard.",
            approval_risk="Low–Moderate for secondary treatment. "
                          "Higher for reuse pathway — requires recycled water guidelines "
                          "(ADWG 2011, AGWR 2008) compliance.",
            epa_precedent="MBR for reuse well-established in AUS — Sydney Water, "
                          "Queensland Urban Utilities, SA Water reference plants.",
            public_acceptance="Moderate — reuse pathway requires community "
                              "engagement programme.",
            note="Reuse pathway requires recycled water scheme approval separate "
                 "from works approval. Allow additional 6–12 months for "
                 "recycled water licence if applicable.",
        )

    elif tech_code == "ifas_mbbr":
        return RegulatoryConfidence(
            overall=Rating.HIGH,
            familiarity="High — IFAS/MBBR is considered a variant of activated sludge "
                        "by most regulators. No novel technology assessment.",
            approval_risk="Low — treated as activated sludge upgrade. "
                          "Standard secondary treatment approval pathway.",
            epa_precedent="Wide AUS precedent — upgrade technology used at many "
                          "existing plants.",
            public_acceptance="High — no visible change to plant appearance.",
            note="No regulatory barriers. Confirm with EPA that upgrade "
                 "approval covers new treatment capacity (not just efficiency).",
        )

    else:
        return RegulatoryConfidence(
            overall=Rating.MODERATE,
            familiarity="Unknown — specialist regulatory advice required.",
            approval_risk="Unknown — early regulator engagement recommended.",
            epa_precedent="Unknown.",
            public_acceptance="Assess based on specific technology.",
            note="Specialist regulatory input required for this technology.",
        )


def _build_profile(tech_code: str, flow_mld: float,
                   footprint_m2: float) -> TechnologyDecisionProfile:
    """Assemble complete decision profile for one technology."""
    return TechnologyDecisionProfile(
        tech_code=tech_code,
        tech_label=_TECH_LABELS.get(tech_code, tech_code.upper()),
        delivery=_delivery(tech_code, flow_mld),
        constructability=_constructability(tech_code, flow_mld, footprint_m2),
        staging=_staging(tech_code, flow_mld),
        ops_complexity=_ops_complexity(tech_code, flow_mld),
        failure_modes=_failure_modes(tech_code),
        regulatory=_regulatory(tech_code),
    )


# ── Alternative pathway library ──────────────────────────────────────────────
# Known interventions that can make non-viable technologies viable.
# Keyed by tech_code. Each entry is a function(inputs) → AlternativePathway | None

def _alternative_pathway_bnr(inputs: Any) -> "AlternativePathway":
    """
    BNR cold climate intervention: extended SRT + thermal management + supplemental carbon.

    At design temperatures <15°C, BNR nitrification requires either:
      - Biofilm augmentation (IFAS/MABR) — changes technology
      - Thermal management (covering + heating) — maintains technology, adds OPEX
      - Extended SRT — increases reactor volume, addresses TN but not cold NH4 alone

    This pathway: BNR + thermal management to maintain 15°C + supplemental carbon for TN.
    Achieves NH4<3 and TN<10 at a lower LCC than MABR.
    """
    T = getattr(inputs, "influent_temperature_celsius", 20) or 20
    flow = getattr(inputs, "design_flow_mld", 10) or 10
    eff_nh4 = getattr(inputs, "effluent_nh4_mg_l", 5) or 5

    if T >= 15:
        return None  # no intervention needed

    # Thermal management cost scales with flow and temperature delta
    temp_delta = max(0, 15 - T)
    # Heating system CAPEX: covered reactor + heat exchanger
    thermal_capex_m = 0.5 + (flow / 8.0) * 0.25 * (temp_delta / 3)
    # Heating energy OPEX: approx 50 kWh/MLD/°C/day
    heating_kwh_day = flow * 50 * temp_delta
    heating_opex_k = heating_kwh_day * 365 * 0.14 / 1000

    # Supplemental carbon (methanol) for TN: ~30 kg/MLD/day at COD/TKN<10
    methanol_kg_day = flow * 30
    methanol_opex_k = methanol_kg_day * 365 * 0.45 / 1000

    # SRT extension increases reactor volume ~30% at 12°C vs 20°C
    # Absorbed into base BNR CAPEX (already computed by BNRTechnology at the cold temp)
    # Additional civil CAPEX for heating system
    capex_delta_m = round(thermal_capex_m, 2)
    opex_delta_k = round(heating_opex_k + methanol_opex_k, 0)

    # Approximate LCC for this pathway
    # BNR base at cold T ≈ $7.3M CAPEX, $573k OPEX for 8 MLD
    # Scale to actual flow
    base_capex = 7.31 * (flow / 8.0) ** 0.6
    base_opex  = 573  * (flow / 8.0) ** 0.7
    total_capex = (base_capex + capex_delta_m) * 1e6
    total_opex  = (base_opex + opex_delta_k) * 1e3
    dr, n = 0.07, 30
    crf = dr * (1 + dr)**n / ((1 + dr)**n - 1)
    lcc_total_k = round((total_capex * crf + total_opex) / 1e3, 0)

    nh4_achievable = eff_nh4 <= 3.0  # at 15°C, BNR achieves NH4<3 with proper SRT

    base_capex_m = round(7.31 * (flow / 8.0) ** 0.6, 2)  # scaled from 8 MLD calibration

    return AlternativePathway(
        tech_code="bnr",
        tech_label="BNR (Activated Sludge)",
        intervention=(
            f"Extended SRT (15–20 days) + thermal management (reactor covering + heating "
            f"to maintain ≥15°C) + supplemental carbon (methanol) for TN compliance"
        ),
        capex_delta_m=capex_delta_m,
        base_capex_m=base_capex_m,
        opex_delta_k=opex_delta_k,
        lcc_total_k=lcc_total_k,
        achieves_compliance=nh4_achievable,
        residual_risks=[
            f"Heating system must maintain ≥15°C continuously — compliance breach "
            f"within days of thermal failure (no inertia buffer)",
            "Methanol dosing: chemical handling, storage, dose control, supply security",
            "Higher operational complexity than standard BNR — two additional systems",
        ],
        procurement="D&C viable — standard construction scope, no proprietary systems",
        regulatory="High regulatory confidence — standard activated sludge technology",
        summary=(
            f"BNR + thermal management represents a conventional engineering solution "
            f"using proven process principles. By maintaining reactor temperature at ≥15°C "
            f"through covered tanks and supplemental heating, full nitrification is restored. "
            f"Supplemental carbon (methanol) addresses the marginal COD/TKN = "
            f"{(220*2/48):.1f} for reliable TN compliance. "
            f"This pathway avoids novel technology risk, vendor lock-in, and extended "
            f"regulatory approval — but introduces ongoing chemical dependency and energy "
            f"cost exposure from continuous heating. "
            f"Total CAPEX: ~${base_capex_m + capex_delta_m:.1f}M "
            f"(${base_capex_m:.1f}M base BNR + ${capex_delta_m:.1f}M thermal/carbon system)."
        ),
    )


def _alternative_pathway_ags(inputs: Any) -> "AlternativePathway":
    """AGS cold climate: thermal management + ferric P polish."""
    T = getattr(inputs, "influent_temperature_celsius", 20) or 20
    flow = getattr(inputs, "design_flow_mld", 10) or 10
    if T >= 12:
        return None  # granule instability is < 10°C critical

    thermal_capex_m = 0.6 + (flow / 8.0) * 0.3
    opex_delta_k = 80.0 + flow * 10  # heating + ferric
    base_lcc = 1079 * (flow / 8.0) ** 0.7
    lcc_total_k = round(base_lcc + thermal_capex_m * 0.0806 * 1000 + opex_delta_k, 0)

    return AlternativePathway(
        tech_code="granular_sludge",
        tech_label="Aerobic Granular Sludge",
        intervention="Covered reactors + thermal management to maintain ≥12°C + ferric P polish",
        capex_delta_m=round(thermal_capex_m, 2),
        opex_delta_k=round(opex_delta_k, 0),
        lcc_total_k=lcc_total_k,
        achieves_compliance=True,
        residual_risks=[
            "Granule stability still marginal at 12°C even with heating",
            "Commissioning risk remains: 12–18 months for stable granule bed",
            "Thermal system adds operational complexity",
        ],
        procurement="DBOM / Alliance — proprietary process still requires vendor",
        regulatory="Moderate regulatory confidence",
        summary=(
            "AGS can be made viable at 12°C with covered reactors maintaining ≥12°C. "
            "Ferric chloride polishing addresses TP compliance. "
            "However, granule stability risk at 12°C remains elevated — this pathway "
            "carries higher commissioning risk than BNR+thermal."
        ),
    )


# ── Executive summary engine ──────────────────────────────────────────────────

def _build_alternative_pathways(
    non_viable: list, inputs: Any
) -> "List[AlternativePathway]":
    """Generate alternative pathway assessments for all non-viable technologies."""
    pathways = []
    pathway_builders = {
        "bnr":             _alternative_pathway_bnr,
        "granular_sludge": _alternative_pathway_ags,
    }
    for nv_name in non_viable:
        # Find tech_code from scenario name — reverse lookup
        # nv_name is the scenario_name (=tech label), find the tech_code
        tech_code = next(
            (tc for tc, lbl in _TECH_LABELS.items() if lbl == nv_name),
            None
        )
        if tech_code and tech_code in pathway_builders:
            pathway = pathway_builders[tech_code](inputs)
            if pathway is not None:
                pathways.append(pathway)
    return pathways


def _build_recommendation_confidence(
    recommended_tech: str,
    is_sole_compliant: bool,
    valid_count: int,
    inputs: Any,
) -> "RecommendationConfidence":
    """Rate confidence in the recommendation."""
    T = getattr(inputs, "influent_temperature_celsius", 20) or 20
    drivers = []
    caveats = []

    if is_sole_compliant:
        # Confidence in sole-compliant option depends on technology maturity
        if recommended_tech == "mabr_bnr":
            level = "Moderate"
            drivers = [
                "Strong compliance modelling — MABR + BNR meets NH₄<3 without external intervention; alternative pathway achieves compliance with thermal and carbon support",
                "Compliance requirement defines the solution space — only compliant technologies can be recommended",
            ]
            caveats = [
                "Limited full-scale AUS precedent for MABR (<5 plants, 2024)",
                "Biofilm performance at 12°C extrapolated from limited cold-climate data",
                "Alternative pathway (BNR+thermal) is viable and cheaper — client should "
                "evaluate both before committing to MABR procurement",
            ]
        elif recommended_tech == "bnr_mbr":
            level = "High"
            drivers = [
                "MBR provides absolute TSS/BOD barrier — compliance is deterministic",
                "Well-established technology with AUS precedent",
            ]
            caveats = [
                "Membrane replacement cost introduces LCC uncertainty (±15%)",
            ]
        else:
            level = "Moderate"
            drivers = ["Sole compliant option under scenario conditions"]
            caveats = ["Detailed design should confirm performance"]
    else:
        # Competitive selection — confidence in LCC ranking
        level = "High"
        drivers = [
            "Multiple compliant options — recommendation based on quantified LCC comparison",
            f"Technology maturity and risk profile consistent with recommendation",
        ]
        caveats = [
            "CAPEX ±40% at concept stage — LCC ranking could change at detailed design",
        ]
        if valid_count == 1:
            level = "Moderate"

    if T < 14:
        caveats.append(
            f"Cold climate modelling ({T:.0f}°C) applies temperature correction factors "
            "with limited cold-climate reference data — verify with detailed thermal design"
        )

    return RecommendationConfidence(
        level=level,
        drivers=drivers,
        caveats=caveats,
    )


def _build_client_framing(
    recommended_tech: str,
    recommended_label: str,
    alternative_pathways: "List[AlternativePathway]",
    recommended_lcc_k: float,
    recommended_capex_m: float,
    recommended_risk: float,
    inputs: Any,
) -> "Optional[ClientDecisionFraming]":
    """Frame the decision as two options for executive presentation."""
    if not alternative_pathways:
        return None

    best_alt = alternative_pathways[0]  # use first (best) alternative pathway

    # Option A = recommended (e.g. MABR)
    opt_a_bullets = [
        f"Lifecycle cost: ${recommended_lcc_k:.0f}k/yr",
        f"CAPEX: ${recommended_capex_m:.1f}M",
        "Meets all effluent targets without process modification",
        f"Delivery: {_delivery(recommended_tech, 10).recommended_model}",
    ]
    opt_a_risks = [
        f"Risk score: {recommended_risk:.0f}/100 (higher than conventional alternative)",
        f"Regulatory: {_regulatory(recommended_tech).overall.value} confidence",
        "Novel technology procurement — limited AUS delivery partners",
    ]

    # Option B = alternative pathway (e.g. BNR+thermal)
    # CAPEX: base BNR + thermal/carbon delta (NOT related to MABR CAPEX)
    b_base = getattr(best_alt, "base_capex_m", 0) or (best_alt.lcc_total_k * 0)
    b_total_capex = b_base + best_alt.capex_delta_m if b_base else None
    b_capex_str = (
        f"~${b_total_capex:.1f}M (${b_base:.1f}M base + ${best_alt.capex_delta_m:.1f}M thermal/carbon)"
        if b_total_capex else f"Base technology + ${best_alt.capex_delta_m:.1f}M intervention"
    )
    lcc_saving = recommended_lcc_k - best_alt.lcc_total_k
    opt_b_bullets = [
        f"Lifecycle cost: ${best_alt.lcc_total_k:.0f}k/yr "
        f"(saves ${lcc_saving:.0f}k/yr vs Option A)",
        f"CAPEX: {b_capex_str}",
        f"Delivery: {best_alt.procurement}",
        f"Regulatory: {best_alt.regulatory}",
    ]
    opt_b_risks = best_alt.residual_risks[:3]

    # Compute real capital saving
    cap_a = recommended_capex_m
    cap_b_total = (getattr(best_alt, "base_capex_m", 0) or 0) + best_alt.capex_delta_m
    cap_saving = cap_a - cap_b_total if cap_b_total > 0 else 0
    cap_saving_str = f"${cap_saving:.1f}M" if cap_saving > 0 else "significant"

    deciding_factors = [
        f"Capital budget constraint — Option B saves ~{cap_saving_str} upfront CAPEX",
        "Long-term asset strategy: process intensification (MABR) vs process robustness (BNR+thermal)",
        "Operational capability: continuous thermal management vs biofilm process control",
        "Regulatory timeline: Option B approved faster; Option A needs early EPA engagement",
        "Availability of experienced MABR delivery partners in local market",
        "Utility preference for proven technology vs emerging technology",
    ]

    framing_note = (
        f"Both options achieve compliance — the decision is HOW compliance is achieved "
        f"and at what cost, risk, and operational complexity. "
        f"Option A achieves compliance through process intensification (MABR biofilm). "
        f"Option B achieves compliance through conventional biology with thermal support. "
        f"Neither is inherently superior — the right choice depends on the utility's "
        f"capital position, risk appetite, and long-term asset strategy."
    )

    return ClientDecisionFraming(
        option_a_label=f"Option A: {recommended_label} (as-modelled)",
        option_a_bullets=opt_a_bullets,
        option_a_risks=opt_a_risks,
        option_b_label=f"Option B: {best_alt.tech_label} + {best_alt.intervention.split('+')[0].strip()}",
        option_b_bullets=opt_b_bullets,
        option_b_risks=opt_b_risks,
        deciding_factors=deciding_factors,
        framing_note=framing_note,
    )


def evaluate_scenario(
    scenarios: list,
    inputs: Any = None,
) -> "ScenarioDecision":
    """
    Produce a complete, internally consistent decision package.

    SELECTION HIERARCHY (enforced strictly):
      1. COMPLIANCE — mandatory. Non-compliant options are excluded first.
      2. COST       — among compliant options, lowest LCC wins.
      3. RISK       — tiebreaker only; does not override cost.

    If only one option is compliant, it is recommended regardless of cost or risk.
    This is the correct utility decision framework: compliance is non-negotiable.
    """
    valid = [s for s in scenarios
             if s.cost_result and s.risk_result and s.domain_specific_outputs]

    if not valid:
        return ScenarioDecision(
            selection_basis="Insufficient data",
            recommended_tech="", recommended_label="Insufficient data",
            display_recommended_label="Insufficient data",
            non_viable=[], why_recommended=["No valid scenario results to evaluate."],
            key_risks=[], regulatory_note="",
            alternative_tech=None, alternative_label=None, alternative_note="",
            alternative_pathways=[], client_framing=None, confidence=None,
            conclusion="Run calculations before generating decision.",
            trade_offs=[], profiles={},
        )

    flow_mld = (getattr(inputs, "design_flow_mld", 10) if inputs else 10) or 10

    # ── Step 1: Build profiles ─────────────────────────────────────────────────
    profiles: Dict[str, TechnologyDecisionProfile] = {}
    for s in valid:
        tc = (s.treatment_pathway.technology_sequence[0]
              if s.treatment_pathway and s.treatment_pathway.technology_sequence else "")
        if not tc:
            continue
        tp_data = (s.domain_specific_outputs.get("technology_performance", {}).get(tc, {})
                   if s.domain_specific_outputs else {})
        fp = float(tp_data.get("footprint_m2", 0) or 0)
        profiles[s.scenario_name] = _build_profile(tc, flow_mld, fp)

    # ── Step 2: Separate compliant from non-compliant (HIERARCHY STEP 1) ──────
    non_viable: List[str] = []
    viable: List = []
    for s in valid:
        tc = (s.treatment_pathway.technology_sequence[0]
              if s.treatment_pathway and s.treatment_pathway.technology_sequence else "")
        tp_data = (s.domain_specific_outputs.get("technology_performance", {}).get(tc, {})
                   if s.domain_specific_outputs else {})
        compliance = tp_data.get("compliance_flag", "")
        issues = tp_data.get("compliance_issues", [])
        # Non-viable = has compliance flag AND actual issues
        has_issues = bool(issues) if isinstance(issues, list) else bool(issues)
        if compliance in ("Review Required",) and has_issues:
            non_viable.append(s.scenario_name)
        else:
            viable.append(s)

    all_non_viable = not viable
    if all_non_viable:
        viable = valid  # all have issues — rank anyway, but flag clearly

    # ── Step 3: Select recommended by LCC (HIERARCHY STEP 2) ─────────────────
    ranked = sorted(viable, key=lambda s: s.cost_result.lifecycle_cost_annual)
    recommended = ranked[0]
    rec_tc = (recommended.treatment_pathway.technology_sequence[0]
              if recommended.treatment_pathway else "")
    rec_label = _TECH_LABELS.get(rec_tc, rec_tc)

    is_sole_compliant = len(viable) == 1 and not all_non_viable

    # Determine selection basis (for report transparency)
    if all_non_viable:
        selection_basis = (
            "No compliant option — all technologies fail compliance as modelled. "
            "Engineering intervention or target relaxation required. "
            "Lowest-LCC option shown for reference only."
        )
    elif is_sole_compliant and non_viable:
        selection_basis = "Sole compliant option — compliance constraint forces selection"
    elif len(viable) > 1:
        # Check if there's a risk tiebreak
        lcc_gap = ranked[1].cost_result.lifecycle_cost_annual - ranked[0].cost_result.lifecycle_cost_annual
        if lcc_gap < ranked[0].cost_result.lifecycle_cost_annual * 0.03:
            selection_basis = "Risk-adjusted LCC (costs within 3% — risk tiebreaker applied)"
        else:
            selection_basis = "Lowest lifecycle cost among compliant options"
    else:
        selection_basis = "Lowest lifecycle cost"

    # ── Step 4: Build honest why_recommended bullets ──────────────────────────
    why = []

    if is_sole_compliant and non_viable:
        # Be explicit: this is compliance-forced, not cost-preferred
        why.append(
            f"ONLY compliant option at these conditions — {non_viable[0].split(',')[0]} "
            f"and others fail compliance targets."
        )
        why.append(
            f"Lifecycle cost: ${recommended.cost_result.lifecycle_cost_annual/1e3:.0f}k/yr "
            f"(${recommended.cost_result.specific_cost_per_kl:.3f}/kL) — higher than "
            f"non-compliant alternatives but compliance is non-negotiable."
        )
        why.append(
            "Note: Alternative pathways exist (see Section) that make lower-cost "
            "technologies compliant. Evaluate before committing to procurement."
        )
    else:
        # Competitive selection
        why.append(
            f"Lowest lifecycle cost among compliant options: "
            f"${recommended.cost_result.lifecycle_cost_annual/1e3:.0f}k/yr "
            f"(${recommended.cost_result.specific_cost_per_kl:.3f}/kL)."
        )
        if len(ranked) > 1:
            next_lcc = ranked[1].cost_result.lifecycle_cost_annual
            saving = next_lcc - recommended.cost_result.lifecycle_cost_annual
            why.append(
                f"${saving/1e3:.0f}k/yr cheaper LCC than next-best option "
                f"({ranked[1].scenario_name})."
            )
        why.append("Meets all effluent compliance targets.")

    # ── Step 5: Regulatory note — explicit framing ────────────────────────────
    reg = profiles.get(recommended.scenario_name)
    reg_conf = reg.regulatory.overall if reg else None

    if reg_conf and reg_conf == Rating.LOW:
        regulatory_note = (
            f"Regulatory confidence is {reg_conf.value.lower()} for {rec_label}. "
            "This does not prevent the recommendation — compliance with effluent targets "
            "takes precedence over regulatory complexity. However: "
            "early regulator engagement is mandatory BEFORE procurement. "
            "Allow 6–12 months additional approval time. "
            "Novel technology assessment under EPL/works approval likely required."
        )
    elif reg_conf and reg_conf == Rating.MODERATE:
        regulatory_note = (
            f"Regulatory confidence is moderate for {rec_label}. "
            "Pre-application meeting with EPA recommended before procurement. "
            "Approval pathway is established but officer-level familiarity varies."
        )
    else:
        regulatory_note = (
            f"Regulatory confidence is {reg_conf.value.lower() if reg_conf else 'standard'} "
            f"for {rec_label}. Standard approval pathway applies."
        )

    # ── Step 6: Key risks ──────────────────────────────────────────────────────
    key_risks = []
    if rec_tc == "mabr_bnr":
        key_risks = [
            "Novel technology: limited AUS regulatory precedent — early EPA engagement mandatory",
            "Single-vendor dependency for membrane system",
            "Biofilm loss after toxic shock: 3–6 month recovery → compliance breach",
            "Limited AUS delivery partners — DBOM/Alliance procurement required",
        ]
    elif rec_tc == "granular_sludge":
        key_risks = [
            "Commissioning complexity: granule bed establishment 6–18 months",
            "Operator capability: specialist training required, limited AUS experience pool",
            "Proprietary decanting mechanism: single-source spare parts",
        ]
    elif rec_tc == "bnr_mbr":
        key_risks = [
            "Membrane replacement cost: $300–500k over 10-year lifecycle",
            "Fine screen failure → membrane damage risk (potential $1–3M replacement)",
            "High operational complexity — dedicated MBR operator capability required",
        ]
    elif rec_tc == "bnr":
        T = getattr(inputs, "influent_temperature_celsius", 20) if inputs else 20
        if T and T < 15:
            key_risks = [
                f"Nitrification marginal at {T:.0f}°C — SRT design must be verified by detailed design",
            ]
        key_risks.append("Standard activated sludge operational risks — well-managed with conventional protocols")
    else:
        key_risks = [f"See risk register for {rec_label}"]

    # ── Step 7: Trade-off statements (decision-driving, not descriptive) ──────
    # When two compliant pathways exist, the primary trade-off is MABR vs BNR+thermal.
    # Non-compliant base technologies are noted but not the focus of comparison.
    trade_offs = []
    compliant_alt_check = [p for p in _build_alternative_pathways(non_viable, inputs)
                           if p.achieves_compliance]

    if compliant_alt_check and is_sole_compliant:
        # Two-pathway scenario: lead with MABR vs BNR+thermal (both compliant)
        a = compliant_alt_check[0]
        lcc_a = recommended.cost_result.lifecycle_cost_annual / 1e3
        lcc_b = a.lcc_total_k
        capex_a = recommended.cost_result.capex_total / 1e6
        capex_b = (getattr(a, "base_capex_m", 0) or 0) + a.capex_delta_m
        risk_a = recommended.risk_result.overall_score

        trade_offs.append(
            f"{recommended.scenario_name} vs {a.tech_label} + thermal management "
            f"(both achieve compliance): "
            f"MABR LCC ${lcc_a:.0f}k/yr vs BNR+thermal ${lcc_b:.0f}k/yr "
            f"— BNR+thermal saves ${abs(lcc_a - lcc_b):.0f}k/yr LCC "
            f"and ${abs(capex_a - capex_b):.1f}M CAPEX, "
            f"but introduces continuous thermal and chemical operational dependency."
        )
        trade_offs.append(
            f"Regulatory risk: {recommended.scenario_name} carries low regulatory "
            f"confidence (novel technology, <5 AUS plants). {a.tech_label} + thermal "
            f"carries high confidence (standard activated sludge approval pathway). "
            f"Option B reduces approval timeline by 6–12 months."
        )
        trade_offs.append(
            f"Delivery risk: {recommended.scenario_name} requires DBOM/Alliance — "
            f"limited AUS delivery partners. {a.tech_label} + thermal is D&C viable "
            f"with broad contractor market."
        )
        # Note non-compliant base options for context only
        nv_labels = [s.scenario_name for s in valid if s.scenario_name in non_viable]
        if nv_labels:
            trade_offs.append(
                f"Note: {', '.join(nv_labels)} evaluated as base technologies but fail "
                f"compliance at 12°C without engineering intervention. "
                f"Not viable as standalone options."
            )
    else:
        # Standard competitive trade-offs vs all scenarios
        for s in valid:
            if s.scenario_name == recommended.scenario_name:
                continue
            lcc_d = (s.cost_result.lifecycle_cost_annual
                     - recommended.cost_result.lifecycle_cost_annual)
            risk_d = s.risk_result.overall_score - recommended.risk_result.overall_score
            is_nv = s.scenario_name in non_viable
            nv_tag = " [non-compliant as modelled]" if is_nv else ""

            if lcc_d > 0:
                trade_offs.append(
                    f"{recommended.scenario_name} vs {s.scenario_name}: "
                    f"saves ${lcc_d/1e3:.0f}k/yr LCC"
                    + (f", carries {abs(risk_d):.0f} points higher risk" if risk_d < -1 else "")
                    + nv_tag
                )
            else:
                trade_offs.append(
                    f"{recommended.scenario_name} costs ${abs(lcc_d)/1e3:.0f}k/yr more "
                    f"than {s.scenario_name}"
                    + (" — cost driven by compliance requirement" if is_sole_compliant and is_nv else "")
                    + nv_tag
                )

    # ── Step 8: Alternative option ─────────────────────────────────────────────
    alt = ranked[1] if len(ranked) > 1 else None
    alt_tc = (alt.treatment_pathway.technology_sequence[0]
              if alt and alt.treatment_pathway else None)
    alt_label = _TECH_LABELS.get(alt_tc, alt_tc) if alt_tc else None
    alt_note = ""
    if alt and not is_sole_compliant:
        lcc_diff = alt.cost_result.lifecycle_cost_annual - recommended.cost_result.lifecycle_cost_annual
        risk_diff = alt.risk_result.overall_score - recommended.risk_result.overall_score
        alt_note = (
            f"{alt_label}: ${abs(lcc_diff)/1e3:.0f}k/yr "
            f"{'more' if lcc_diff > 0 else 'less'} expensive. "
            f"Risk score: {alt.risk_result.overall_score:.0f} "
            f"({'lower' if risk_diff < 0 else 'higher'} risk than recommended). "
            "Viable alternative where delivery risk is the primary concern."
        )

    # ── Step 9: Alternative pathways for non-viable options ───────────────────
    alt_pathways = _build_alternative_pathways(non_viable, inputs)

    # ── Step 10: Client decision framing ──────────────────────────────────────
    client_framing = None
    if alt_pathways and is_sole_compliant:
        client_framing = _build_client_framing(
            rec_tc, rec_label, alt_pathways,
            recommended.cost_result.lifecycle_cost_annual / 1e3,
            recommended.cost_result.capex_total / 1e6,
            recommended.risk_result.overall_score,
            inputs,
        )

    # ── Step 11: Recommendation confidence ────────────────────────────────────
    confidence = _build_recommendation_confidence(
        rec_tc, is_sole_compliant, len(valid), inputs
    )

    # ── Step 12: Check for two-pathway situation and update logic ───────────────
    compliant_alt_paths = [p for p in alt_pathways if p.achieves_compliance]
    two_pathways = is_sole_compliant and bool(compliant_alt_paths)

    # When TWO compliant pathways exist, update selection_basis and why_recommended
    if two_pathways:
        a = compliant_alt_paths[0]
        lcc_diff = recommended.cost_result.lifecycle_cost_annual / 1e3 - a.lcc_total_k
        b_capex = (getattr(a, "base_capex_m", 0) or 0) + a.capex_delta_m
        selection_basis = (
            "Two compliant pathways identified — technology selection depends on "
            "risk, cost, delivery strategy, and long-term asset approach"
        )
        why = [
            f"{rec_label} selected as the process-intensified solution: "
            f"achieves compliance within existing footprint and energy parameters "
            f"without external thermal or chemical inputs.",
            f"Lifecycle cost: ${recommended.cost_result.lifecycle_cost_annual/1e3:.0f}k/yr "
            f"(${recommended.cost_result.specific_cost_per_kl:.3f}/kL) — "
            f"${abs(lcc_diff):.0f}k/yr {'more' if lcc_diff > 0 else 'less'} than BNR+thermal pathway.",
            f"Alternative pathway ({a.tech_label} + thermal management) is cheaper "
            f"(${a.lcc_total_k:.0f}k/yr, ~${b_capex:.1f}M CAPEX) but requires "
            f"continuous thermal management as a critical operational dependency.",
            "Both pathways meet all effluent compliance targets — parallel evaluation recommended.",
        ]

    # ── Step 13: Strategic insight ────────────────────────────────────────────
    if two_pathways:
        a = compliant_alt_paths[0]
        strategic_insight = (
            "This decision is fundamentally: process intensification vs process robustness. "
            + "\n\n"
            + f"{rec_label}: intensifies biology (MABR biofilm) to achieve compliance "
            "within footprint and energy constraints — no external inputs required. "
            "Higher procurement complexity and regulatory risk, but operationally self-contained."
            + "\n\n"
            + f"{a.tech_label} + thermal management: supports conventional biology with "
            "external inputs (heat, carbon) to restore compliance at cold temperature. "
            "Lower technology risk and regulatory confidence, but introduces ongoing "
            "chemical dependency and energy cost exposure from continuous heating."
            + "\n\n"
            + "This distinction should guide long-term asset strategy: "
            "utilities prioritising operational simplicity and technology familiarity "
            "should favour Option B; utilities prioritising process efficiency and "
            "future-proofing for tighter limits should favour Option A."
        )
    else:
        strategic_insight = ""

    # ── Step 14: Recommended approach (parallel evaluation) ──────────────────
    if two_pathways:
        a = compliant_alt_paths[0]
        recommended_approach = [
            "Proceed with parallel concept design validation of both pathways:",
            f"  Option A — {rec_label}: vendor pre-qualification, pilot data review, "
            f"early EPA engagement",
            f"  Option B — {a.tech_label} + thermal management: thermal feasibility study, "
            f"heating system concept design, carbon dose optimisation",
            "Undertake procurement market sounding for MABR delivery partners in AUS",
            "Engage regulator early on Option A novel technology pathway",
            "Final selection following: regulator engagement, thermal feasibility "
            "confirmation, and procurement market sounding — target decision within "
            "3–6 months of concept design completion",
        ]
    else:
        recommended_approach = []

    # ── Step 15: Conclusion ────────────────────────────────────────────────────
    if two_pathways:
        a = compliant_alt_paths[0]
        lcc_diff = recommended.cost_result.lifecycle_cost_annual / 1e3 - a.lcc_total_k
        b_capex = (getattr(a, "base_capex_m", 0) or 0) + a.capex_delta_m
        conclusion = (
            f"Two compliant pathways have been identified for this scenario. "
            f"{rec_label} achieves compliance through process intensification at "
            f"${recommended.cost_result.lifecycle_cost_annual/1e3:.0f}k/yr LCC "
            f"(${recommended.cost_result.capex_total/1e6:.1f}M CAPEX). "
            f"{a.tech_label} with thermal management achieves compliance through "
            f"conventional biology at ${a.lcc_total_k:.0f}k/yr LCC "
            f"(~${b_capex:.1f}M CAPEX) — "
            f"${abs(lcc_diff):.0f}k/yr cheaper but with ongoing operational dependencies. "
            f"Parallel concept design validation of both pathways is recommended before "
            f"technology lock-in. Final selection should follow regulator engagement, "
            f"thermal feasibility confirmation, and procurement market sounding."
        )
    elif is_sole_compliant and non_viable:
        conclusion = (
            f"{rec_label} is recommended as the sole compliant option as modelled. "
            f"Regulatory confidence is {reg_conf.value.lower() if reg_conf else 'to be confirmed'} — "
            f"early EPA engagement mandatory before procurement. "
            f"Note: {len(non_viable)} option(s) fail compliance as modelled — "
            f"engineering interventions may make them viable (see alternative pathways)."
        )
    else:
        if all_non_viable:
            conclusion = (
                f"No technology meets compliance targets as modelled. "
                f"{rec_label} has the lowest lifecycle cost (${recommended.cost_result.lifecycle_cost_annual/1e3:.0f}k/yr) "
                f"and is shown for reference, but is not a compliant recommendation. "
                f"Engineering interventions are required to achieve compliance: "
                f"supplemental carbon dosing, SRT extension, or technology change. "
                f"Do not proceed to procurement without resolving compliance."
            )
        else:
            # Build a substantive conclusion that explicitly states the trade-offs
            # and when each option is preferred — this is what clients need.
            rec_cr  = recommended.cost_result
            rec_rr  = recommended.risk_result
            alt_scenarios = [s for s in viable if s != recommended]

            _cost_line = (
                f"{rec_label} has the lowest lifecycle cost "
                f"(${rec_cr.lifecycle_cost_annual/1e3:.0f}k/yr, "
                f"${rec_cr.specific_cost_per_kl:.3f}/kL treated)"
                if rec_cr else f"{rec_label} is the preferred option"
            )

            # Build "preferred where" guidance for each scenario
            _preferred_where = []
            for s in viable:
                cr = s.cost_result
                rr = s.risk_result
                eng = (s.domain_specific_outputs or {}).get("engineering_summary", {})
                flow = eng.get("design_flow_mld") or 1
                footprint = eng.get("footprint_m2") or 0
                specific_fp = footprint / flow if flow else 0
                sludge = eng.get("total_sludge_kgds_day") or 0
                is_novel = any(tc in {"granular_sludge", "mabr_bnr", "bnr_mbr", "anmbr"}
                               for tc in (s.treatment_pathway.technology_sequence if s.treatment_pathway else []))
                is_rec = (s == recommended)

                attrs = []
                if is_rec:
                    attrs.append("lowest lifecycle cost")
                if rr and rr.overall_level == "Low":
                    attrs.append("lowest operational risk")
                elif rr and rr.overall_level == "High":
                    attrs.append("higher operational complexity")
                if specific_fp > 0 and specific_fp < 120:
                    attrs.append(f"compact footprint ({specific_fp:.0f} m²/MLD)")
                elif specific_fp >= 120:
                    attrs.append(f"larger footprint ({specific_fp:.0f} m²/MLD)")
                if cr and rec_cr and cr.opex_annual < rec_cr.opex_annual * 0.85:
                    attrs.append("significantly lower OPEX")
                if is_novel:
                    attrs.append("requires specialist startup and vendor engagement")
                else:
                    attrs.append("uses established procurement and O&M pathways")

                if attrs:
                    _preferred_where.append(
                        f"**{s.scenario_name}** is preferred where: {'; '.join(attrs)}."
                    )

            _where_text = " ".join(_preferred_where) if _preferred_where else ""

            conclusion = (
                f"{_cost_line}. "
                f"Recommended procurement model: {reg.delivery.recommended_model if reg else 'D&C'}. "
                f"Regulatory confidence is {reg_conf.value.lower() if reg_conf else 'standard'}. "
                + (f"\n\nTechnology selection guidance: {_where_text}" if _where_text else "") +
                f"\n\nA detailed feasibility study with site-specific cost estimation (±15–20%) "
                f"is recommended before proceeding to detailed design or procurement."
            )

    # Build display label — qualified when two pathways exist
    if two_pathways:
        display_rec_label = f"Preferred option (subject to validation): {rec_label}"
    elif all_non_viable:
        display_rec_label = f"Reference option (non-compliant as modelled): {rec_label}"
    else:
        display_rec_label = rec_label

    # ── Weighted multi-criteria scoring ──────────────────────────────────────
    # Run the scoring engine with Balanced profile as the default.
    # The UI can re-run with alternative profiles without re-running engineering.
    weighted_decision = None
    try:
        from core.decision.scoring_engine import ScoringEngine, WeightProfile
        compliance_map = {}
        for s in scenarios:
            if s.scenario_name in non_viable:
                compliance_map[s.scenario_name] = "Non-compliant"
            else:
                compliance_map[s.scenario_name] = "Compliant"
        se = ScoringEngine()
        weighted_decision = se.score(
            scenarios,
            weight_profile=WeightProfile.BALANCED,
            compliance_map=compliance_map,
        )
    except Exception:
        pass   # scoring is additive — never block the primary decision

    return ScenarioDecision(
        selection_basis=selection_basis,
        recommended_tech=rec_tc,
        recommended_label=rec_label,
        display_recommended_label=display_rec_label,
        non_viable=non_viable,
        why_recommended=why,
        key_risks=key_risks,
        regulatory_note=regulatory_note,
        alternative_tech=alt_tc,
        alternative_label=alt_label,
        alternative_note=alt_note,
        alternative_pathways=alt_pathways,
        client_framing=client_framing,
        confidence=confidence,
        conclusion=conclusion,
        trade_offs=trade_offs,
        profiles=profiles,
        strategic_insight=strategic_insight,
        recommended_approach=recommended_approach,
        weighted_decision=weighted_decision,
    )
