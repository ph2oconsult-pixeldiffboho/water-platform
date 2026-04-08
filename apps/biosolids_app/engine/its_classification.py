"""
BioPoint V1 — Integrated Thermal System Classification (v24Z87).

Replaces technology-based PFAS classification with system-based classification.

Core principle: PFAS destruction is determined by full system design —
not by the reactor type label (pyrolysis, gasification, incineration).

Four classification levels:

  LEVEL 1 — TRANSFER SYSTEM
    No thermal conversion. PFAS transfers from sludge to product.
    Example: HTC, drying only, land application.
    PFAS outcome: TRANSFER — PFAS concentration in product, not destroyed.
    Status: NOT ACCEPTABLE where PFAS disposal is regulated.

  LEVEL 2 — PARTIAL THERMAL SYSTEM
    Thermal conversion but without validated high-temperature oxidation stage.
    Example: low-temperature pyrolysis (<700°C), unvalidated systems.
    PFAS outcome: UNCERTAIN / REDISTRIBUTION between char, gas, and condensate.
    Status: CONDITIONAL — requires PFAS destruction validation.

  LEVEL 3 — INTEGRATED THERMAL SYSTEM (ITS)
    Primary reactor (pyrolysis/gasification) PLUS secondary thermal oxidation
    at >850–1100°C with controlled residence time and emissions control.
    Example: PYREG advanced configuration, Ecoremedy, Earthcare, BiogenCon.
    PFAS outcome: DESTRUCTION — design-capable or validated.
    Status: ACCEPTABLE where ITS configuration is confirmed and validated.

  LEVEL 4 — DEDICATED INCINERATION
    Fluidised bed or grate incinerator with full APC.
    Operating temperature consistently >850°C throughout combustion zone.
    PFAS outcome: DESTRUCTION — highest confidence, most regulatory precedent.
    Status: HIGH CONFIDENCE — gold standard for PFAS destruction.

Critical rule:
  Do NOT classify systems as "pyrolysis" or "gasification" and assume a
  PFAS outcome. Evaluate: secondary oxidation stage, temperature, residence
  time, and emissions control.

References:
  - US EPA PFAS Destruction and Disposal Guidance (2022)
  - OECD PFAS guidance on disposal methods
  - Interstate Technology & Regulatory Council (ITRC) PFAS Technical
    and Regulatory Guidance (2023)
  - Australian PFAS National Environmental Management Plan v2.0 (2020)
  - Hogue (2021) — pyrolysis PFAS destruction variability
  - UK Environment Agency — incineration as PFAS BAT (2021)

ph2o Consulting — BioPoint V1
"""

from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# SYSTEM DESIGN FACTORS — what determines PFAS classification
# ---------------------------------------------------------------------------

@dataclass
class ThermalSystemDesign:
    """
    Describes the design of a thermal system's PFAS-relevant features.
    These are the inputs the classification engine evaluates — not the
    reactor type label.
    """
    system_name: str = ""
    reactor_type: str = ""              # pyrolysis / gasification / incineration / HTC / other

    # Primary reactor
    primary_temp_c_min: float = 0.0     # Min primary reactor temperature (°C)
    primary_temp_c_max: float = 0.0     # Max primary reactor temperature (°C)
    primary_residence_time_s: float = 0.0   # Gas/solid residence time (seconds)

    # Secondary oxidation stage
    has_secondary_oxidation: bool = False
    secondary_temp_c: float = 0.0       # Temperature of secondary combustion chamber (°C)
    secondary_residence_time_s: float = 0.0  # Gas residence time in secondary zone (seconds)

    # Emissions control
    has_apc: bool = False               # Air pollution control system
    apc_type: str = ""                  # e.g. "baghouse + scrubber", "SNCR + ESP"

    # PFAS evidence
    pfas_evidence_type: str = ""        # "demonstrated" / "design-based" / "assumed" / "none"
    pfas_test_reference: str = ""       # Reference to test data or standard

    # Notes
    system_notes: str = ""


# ---------------------------------------------------------------------------
# CLASSIFICATION LEVELS
# ---------------------------------------------------------------------------

LEVEL_DEFINITIONS = {
    1: {
        "label":       "TRANSFER SYSTEM",
        "short":       "L1 — Transfer",
        "pfas_outcome":"TRANSFER",
        "status":      "NOT ACCEPTABLE",
        "colour":      "red",
        "description": (
            "No thermal conversion. PFAS transfers from sludge feed into the output "
            "product (hydrochar, dried sludge, or land-applied cake) in concentrated form. "
            "Does not destroy PFAS. Where PFAS is present in sludge, this level is "
            "NOT ACCEPTABLE as a compliant disposal route in any jurisdiction "
            "with PFAS land application restrictions."
        ),
    },
    2: {
        "label":       "PARTIAL THERMAL SYSTEM",
        "short":       "L2 — Partial Thermal",
        "pfas_outcome":"UNCERTAIN / REDISTRIBUTION",
        "status":      "CONDITIONAL",
        "colour":      "amber",
        "description": (
            "Thermal conversion occurs but without a validated high-temperature "
            "secondary oxidation stage. PFAS may redistribute between char, "
            "process gas, and condensate rather than being destroyed. "
            "Destruction efficiency is highly variable and compound-specific. "
            "Status is CONDITIONAL — system must demonstrate PFAS destruction "
            "through independent testing before use where PFAS is a concern."
        ),
    },
    3: {
        "label":       "INTEGRATED THERMAL SYSTEM (ITS)",
        "short":       "L3 — ITS",
        "pfas_outcome":"DESTRUCTION (validated or design-capable)",
        "status":      "ACCEPTABLE",
        "colour":      "green",
        "description": (
            "Primary reactor (pyrolysis or gasification) coupled with a secondary "
            "thermal oxidation stage at ≥850°C with ≥2 seconds gas residence time "
            "and full emissions control. This configuration is designed and capable "
            "of PFAS destruction. Validation testing is required to confirm "
            "destruction efficiency for the specific PFAS compound classes present. "
            "Status: ACCEPTABLE where ITS configuration is confirmed and validated."
        ),
    },
    4: {
        "label":       "DEDICATED INCINERATION",
        "short":       "L4 — Incineration",
        "pfas_outcome":"DESTRUCTION",
        "status":      "HIGH CONFIDENCE",
        "colour":      "green",
        "description": (
            "Fluidised bed or grate furnace operating continuously at >850°C "
            "throughout the combustion zone, with full APC (scrubber, bag filter, "
            "SNCR/SCR). Highest regulatory confidence for PFAS destruction. "
            "Destruction efficiency >99.999% demonstrated at full scale for most "
            "PFAS compound classes. The gold standard under US EPA, UK EA, "
            "Australian NEMP, and OECD guidance."
        ),
    },
}

# Key thresholds (based on EPA/ITRC/OECD guidance)
TEMP_THRESHOLD_ITS_C         = 850.0    # Secondary oxidation minimum for PFAS destruction
TEMP_THRESHOLD_OPTIMAL_C     = 1100.0   # Optimal for complete destruction (longer-chain)
RESIDENCE_TIME_ITS_S         = 2.0      # Gas residence time minimum (seconds)
TEMP_THRESHOLD_PYROLYSIS_MIN = 600.0    # Below this: insufficient for even partial destruction

# Standard system configurations for known pathway types
# These represent default assumptions — user can override with actual design specs
_DEFAULT_DESIGNS: dict[str, ThermalSystemDesign] = {

    "HTC": ThermalSystemDesign(
        system_name="Hydrothermal Carbonisation",
        reactor_type="HTC",
        primary_temp_c_min=180, primary_temp_c_max=260,
        primary_residence_time_s=0,
        has_secondary_oxidation=False, secondary_temp_c=0,
        has_apc=False,
        pfas_evidence_type="demonstrated",
        pfas_test_reference=(
            "Multiple studies confirm PFAS concentration in hydrochar. "
            "Lester et al. (2020); Lassen et al. (2021). "
            "HTC does not destroy PFAS."
        ),
        system_notes=(
            "HTC operates at 180–260°C — far below PFAS destruction thresholds. "
            "PFAS partitions between hydrochar and process liquor. "
            "Where PFAS is present, hydrochar land application route is precluded."
        ),
    ),

    "HTC_sidestream": ThermalSystemDesign(
        system_name="HTC + Sidestream Treatment",
        reactor_type="HTC",
        primary_temp_c_min=180, primary_temp_c_max=260,
        has_secondary_oxidation=False, secondary_temp_c=0,
        has_apc=False,
        pfas_evidence_type="demonstrated",
        pfas_test_reference="Same as HTC — sidestream treats N, not PFAS.",
        system_notes=(
            "Sidestream treatment (SHARON/ANAMMOX) removes nitrogen from process liquor "
            "but does NOT destroy PFAS. PFAS in liquor may pass through to effluent. "
            "PFAS classification is Level 1 — unchanged from raw HTC."
        ),
    ),

    "drying_only": ThermalSystemDesign(
        system_name="Thermal Drying",
        reactor_type="drying",
        primary_temp_c_min=80, primary_temp_c_max=200,
        has_secondary_oxidation=False,
        pfas_evidence_type="demonstrated",
        pfas_test_reference="Drying concentrates PFAS in dried product. No destruction.",
        system_notes="Drying does not destroy PFAS. Concentrates PFAS in dried cake.",
    ),

    "decentralised": ThermalSystemDesign(
        system_name="Decentralised Site Drying",
        reactor_type="drying",
        primary_temp_c_min=80, primary_temp_c_max=200,
        has_secondary_oxidation=False,
        pfas_evidence_type="assumed",
        system_notes="Same as drying only — PFAS concentrated in product.",
    ),

    "baseline": ThermalSystemDesign(
        system_name="Baseline Disposal (Land Application)",
        reactor_type="none",
        primary_temp_c_min=0, primary_temp_c_max=0,
        has_secondary_oxidation=False,
        pfas_evidence_type="demonstrated",
        pfas_test_reference="PFAS transfers directly to soil via land application.",
        system_notes=(
            "No treatment. PFAS in sludge is applied directly to agricultural land. "
            "This is the primary regulatory concern driving PFAS restrictions globally."
        ),
    ),

    "AD": ThermalSystemDesign(
        system_name="Anaerobic Digestion",
        reactor_type="biological",
        primary_temp_c_min=35, primary_temp_c_max=55,
        has_secondary_oxidation=False,
        pfas_evidence_type="demonstrated",
        pfas_test_reference=(
            "AD does not destroy PFAS. Soares et al. (2021); "
            "Sörengård et al. (2022) — PFAS persists through digestion."
        ),
        system_notes=(
            "AD operates at mesophilic (35°C) or thermophilic (55°C) temperatures — "
            "far below PFAS destruction thresholds. "
            "PFAS concentration in digestate may be similar to or higher than feed."
        ),
    ),

    "pyrolysis": ThermalSystemDesign(
        system_name="Pyrolysis (standard configuration)",
        reactor_type="pyrolysis",
        primary_temp_c_min=450, primary_temp_c_max=700,
        primary_residence_time_s=1800,   # Solid residence — variable
        has_secondary_oxidation=False,   # Standard pyrolysis has no secondary stage
        secondary_temp_c=0,
        has_apc=True,
        apc_type="scrubber + bag filter (typical)",
        pfas_evidence_type="assumed",
        pfas_test_reference=(
            "Hogue (2021) C&EN — pyrolysis PFAS destruction highly variable. "
            "Wang et al. (2022) — incomplete destruction at <700°C for long-chain PFAS. "
            "Standard pyrolysis WITHOUT secondary oxidation is NOT equivalent to ITS."
        ),
        system_notes=(
            "Standard pyrolysis at 450–700°C: PFAS destruction is uncertain and "
            "compound-specific. Short-chain PFAS may survive. Gas-phase PFAS may "
            "recondense in char or condensate. Without a secondary oxidation stage "
            "at >850°C, this system is Level 2 — CONDITIONAL."
        ),
    ),

    "gasification": ThermalSystemDesign(
        system_name="Gasification (standard configuration)",
        reactor_type="gasification",
        primary_temp_c_min=700, primary_temp_c_max=900,
        primary_residence_time_s=3,     # Gas residence time
        has_secondary_oxidation=False,
        secondary_temp_c=0,
        has_apc=True,
        apc_type="syngas scrubber + tar removal",
        pfas_evidence_type="assumed",
        pfas_test_reference=(
            "Limited PFAS-specific data for sludge gasification. "
            "Primary zone at 700–900°C may partially destroy PFAS but "
            "without secondary oxidation, condensate and tar may contain PFAS."
        ),
        system_notes=(
            "Standard gasification: primary zone temperatures are in the right range "
            "but syngas cooling and tar condensation may allow PFAS reformation. "
            "Without a dedicated secondary combustion chamber at >850°C, "
            "classified as Level 2 — requires validation."
        ),
    ),

    "incineration": ThermalSystemDesign(
        system_name="Fluidised Bed Incineration (FBF)",
        reactor_type="incineration",
        primary_temp_c_min=850, primary_temp_c_max=950,
        primary_residence_time_s=3,
        has_secondary_oxidation=True,
        secondary_temp_c=950,
        secondary_residence_time_s=2.0,
        has_apc=True,
        apc_type="scrubber + bag filter + SNCR (standard FBF specification)",
        pfas_evidence_type="demonstrated",
        pfas_test_reference=(
            "US EPA (2022) — FBF at >850°C achieves >99.999% destruction. "
            "UK EA BAT conclusion — incineration preferred for PFAS biosolids. "
            "Australian NEMP v2.0 — incineration accepted disposal route for PFAS sludge."
        ),
        system_notes=(
            "FBF maintains >850°C throughout the combustion zone with 2+ seconds "
            "residence time. Full APC captures remaining compounds. "
            "This is the reference technology for PFAS destruction in regulatory guidance globally."
        ),
    ),

    "thp_incineration": ThermalSystemDesign(
        system_name="THP + Fluidised Bed Incineration",
        reactor_type="incineration",
        primary_temp_c_min=850, primary_temp_c_max=950,
        primary_residence_time_s=3,
        has_secondary_oxidation=True,
        secondary_temp_c=950,
        secondary_residence_time_s=2.0,
        has_apc=True,
        apc_type="scrubber + bag filter + SNCR",
        pfas_evidence_type="demonstrated",
        pfas_test_reference="Same as incineration — THP upstream does not affect destruction.",
        system_notes=(
            "THP upstream pre-treatment does not affect PFAS destruction in the FBF — "
            "the incineration stage operates identically. Level 4 classification unchanged."
        ),
    ),

    "centralised": ThermalSystemDesign(
        system_name="Centralised Hub (assumed pyrolysis)",
        reactor_type="pyrolysis",
        primary_temp_c_min=450, primary_temp_c_max=700,
        has_secondary_oxidation=False,
        pfas_evidence_type="assumed",
        system_notes=(
            "Centralised hub defaults to pyrolysis assumptions. If hub technology "
            "includes secondary oxidation (ITS configuration), reclassify as Level 3. "
            "Technology selection determines final PFAS level."
        ),
    ),
}

# Vendor-specific ITS configurations that achieve Level 3 classification
# These have secondary oxidation stages and are design-capable of PFAS destruction
ITS_VENDORS = {
    "PYREG_advanced": ThermalSystemDesign(
        system_name="PYREG Advanced (with secondary combustion)",
        reactor_type="pyrolysis+oxidation",
        primary_temp_c_min=500, primary_temp_c_max=700,
        primary_residence_time_s=1800,
        has_secondary_oxidation=True,
        secondary_temp_c=950,    # Secondary combustion chamber >850°C
        secondary_residence_time_s=2.5,
        has_apc=True,
        apc_type="thermal oxidiser + catalytic filter",
        pfas_evidence_type="design-based",
        pfas_test_reference=(
            "PYREG secondary combustion chamber design: >900°C, >2s residence. "
            "Design-based PFAS destruction — independent validation recommended."
        ),
        system_notes=(
            "PYREG advanced configuration with secondary thermal oxidation stage "
            "meets ITS criteria. Design-based PFAS destruction capability. "
            "Validate with site-specific PFAS stack testing before regulatory acceptance."
        ),
    ),
    "Ecoremedy": ThermalSystemDesign(
        system_name="Ecoremedy (Integrated Thermal System)",
        reactor_type="gasification+oxidation",
        primary_temp_c_min=700, primary_temp_c_max=850,
        primary_residence_time_s=3,
        has_secondary_oxidation=True,
        secondary_temp_c=1100,
        secondary_residence_time_s=2.0,
        has_apc=True,
        apc_type="cyclone + wet scrubber",
        pfas_evidence_type="design-based",
        pfas_test_reference=(
            "Ecoremedy secondary oxidation chamber: 1,000–1,100°C. "
            "Mineral product output. Design-based PFAS destruction."
        ),
        system_notes=(
            "Ecoremedy gasification + high-temperature secondary oxidation. "
            "Secondary zone at 1,000–1,100°C significantly exceeds minimum threshold. "
            "Design-capable of PFAS destruction. Independent testing required for validation."
        ),
    ),
    "Earthcare": ThermalSystemDesign(
        system_name="Earthcare (Thermal System)",
        reactor_type="pyrolysis+oxidation",
        primary_temp_c_min=550, primary_temp_c_max=700,
        has_secondary_oxidation=True,
        secondary_temp_c=900,
        secondary_residence_time_s=2.0,
        has_apc=True,
        apc_type="bag filter + scrubber",
        pfas_evidence_type="design-based",
        pfas_test_reference="Secondary combustion design: >850°C. Validation testing in progress.",
        system_notes="ITS configuration with secondary oxidation stage. Level 3 classification.",
    ),
}


# ---------------------------------------------------------------------------
# CLASSIFICATION RESULT
# ---------------------------------------------------------------------------

@dataclass
class ITSClassificationResult:
    """Classification result for one system."""
    system_name: str = ""
    pathway_type: str = ""
    flowsheet_id: str = ""

    # Classification
    its_level: int = 1
    its_level_label: str = ""
    its_level_short: str = ""

    # PFAS outcome
    pfas_outcome: str = ""
    pfas_status: str = ""
    pfas_evidence_type: str = ""        # demonstrated / design-based / assumed / none
    pfas_test_reference: str = ""

    # System design factors
    has_secondary_oxidation: bool = False
    secondary_temp_c: float = 0.0
    secondary_residence_time_s: float = 0.0
    meets_temp_threshold: bool = False
    meets_residence_threshold: bool = False
    has_apc: bool = False

    # Classification basis
    classification_basis: str = ""
    classification_notes: str = ""

    # Upgrade path
    upgrade_to_l3: str = ""             # What would upgrade this system to Level 3
    upgrade_to_l4: str = ""             # What would upgrade to Level 4

    # Colour for display
    colour: str = "red"


@dataclass
class ITSSystemAssessment:
    """System-level ITS assessment across all flowsheets."""
    classifications: list = field(default_factory=list)   # List[ITSClassificationResult]

    # Level counts
    level1_count: int = 0
    level2_count: int = 0
    level3_count: int = 0
    level4_count: int = 0

    # Key findings
    acceptable_pathways: list = field(default_factory=list)    # L3 + L4
    not_acceptable_pathways: list = field(default_factory=list) # L1
    conditional_pathways: list = field(default_factory=list)    # L2

    # Impact on ranking (if PFAS is confirmed)
    pfas_forced_pathways: list = field(default_factory=list)   # L3 + L4 only
    pfas_excluded_pathways: list = field(default_factory=list)  # L1 + L2 (conditional)

    # System statement (per spec)
    system_statement: str = ""
    assessment_narrative: str = ""

    # Lookup
    _by_id: dict = field(default_factory=dict)
    _by_type: dict = field(default_factory=dict)

    def get_by_flowsheet_id(self, fid: str) -> Optional[ITSClassificationResult]:
        return self._by_id.get(fid)

    def get_by_pathway_type(self, ptype: str) -> Optional[ITSClassificationResult]:
        return self._by_type.get(ptype)


# ---------------------------------------------------------------------------
# CLASSIFICATION ENGINE
# ---------------------------------------------------------------------------

def classify_system(design: ThermalSystemDesign) -> int:
    """
    Classify a thermal system into Level 1–4 based on design factors.
    This is the core classification logic — technology-label-independent.
    """
    reactor = design.reactor_type.lower()

    # Level 1: No thermal conversion
    if reactor in ("none", "biological", "htc", "drying"):
        return 1

    # Level 4: Dedicated incineration with full APC
    if reactor == "incineration":
        if (design.primary_temp_c_min >= 850 and
                design.has_secondary_oxidation and
                design.has_apc):
            return 4
        elif design.primary_temp_c_min >= 850:
            return 4  # Still Level 4 even if secondary is the primary zone itself

    # Level 3: Primary reactor + secondary oxidation at >=850°C + APC
    if (design.has_secondary_oxidation and
            design.secondary_temp_c >= TEMP_THRESHOLD_ITS_C and
            design.secondary_residence_time_s >= RESIDENCE_TIME_ITS_S and
            design.has_apc):
        return 3

    # Level 2: Thermal conversion without validated secondary oxidation
    if reactor in ("pyrolysis", "gasification", "pyrolysis+oxidation",
                   "gasification+oxidation"):
        # Has secondary but below threshold → still Level 2
        if design.has_secondary_oxidation and design.secondary_temp_c < TEMP_THRESHOLD_ITS_C:
            return 2
        # No secondary at all
        return 2

    return 2  # Default for unknown thermal types


def _build_classification_result(
    flowsheet_id: str,
    pathway_type: str,
    design: ThermalSystemDesign,
) -> ITSClassificationResult:
    """Build a full ITSClassificationResult from a system design."""

    level = classify_system(design)
    level_def = LEVEL_DEFINITIONS[level]

    meets_temp = (design.has_secondary_oxidation and
                  design.secondary_temp_c >= TEMP_THRESHOLD_ITS_C)
    meets_res  = (design.has_secondary_oxidation and
                  design.secondary_residence_time_s >= RESIDENCE_TIME_ITS_S)

    # Classification basis narrative
    if level == 1:
        basis = (
            f"No thermal conversion. Operating temperature {design.primary_temp_c_max:.0f}°C — "
            f"far below PFAS destruction threshold ({TEMP_THRESHOLD_ITS_C:.0f}°C). "
            "PFAS transfers into output product."
        )
    elif level == 2:
        basis = (
            f"Thermal conversion at {design.primary_temp_c_min:.0f}–{design.primary_temp_c_max:.0f}°C "
            "but WITHOUT a validated secondary oxidation stage at >850°C. "
            "PFAS destruction is uncertain and compound-specific. "
            "Independent testing required before acceptance where PFAS is a concern."
        )
    elif level == 3:
        basis = (
            f"Primary reactor ({design.primary_temp_c_min:.0f}–{design.primary_temp_c_max:.0f}°C) "
            f"PLUS secondary oxidation at {design.secondary_temp_c:.0f}°C "
            f"({design.secondary_residence_time_s:.1f}s residence) with emissions control. "
            "ITS configuration meets design criteria for PFAS destruction. "
            "Validation testing required to confirm site-specific compound destruction."
        )
    else:  # Level 4
        basis = (
            f"Dedicated incineration at {design.primary_temp_c_min:.0f}–{design.primary_temp_c_max:.0f}°C "
            "with full APC. Highest regulatory confidence for PFAS destruction. "
            "This is the reference technology under US EPA, UK EA, and Australian NEMP guidance."
        )

    # Upgrade paths — v25A30: ITS is the MINIMUM VIABLE CONFIGURATION, not an optional upgrade
    if level == 1:
        upgrade_l3 = (
            "Add a primary thermal reactor (pyrolysis/gasification) with secondary "
            f"oxidation chamber at ≥{TEMP_THRESHOLD_ITS_C:.0f}°C and ≥{RESIDENCE_TIME_ITS_S:.0f}s "
            "residence time, plus full APC. "
            "An ITS configuration is the minimum viable thermal system for regulated biosolids — "
            "not an optional upgrade."
        )
        upgrade_l4 = (
            "Replace with a fluidised bed incinerator operating at ≥850°C with full APC. "
            "Level 4 provides the highest regulatory confidence for PFAS destruction."
        )
    elif level == 2:
        upgrade_l3 = (
            f"Add secondary combustion chamber at ≥{TEMP_THRESHOLD_ITS_C:.0f}°C with "
            f"≥{RESIDENCE_TIME_ITS_S:.0f}s gas residence time and full APC. "
            "This is not an optional upgrade — it is the minimum viable configuration "
            "for pyrolysis or gasification treating PFAS-risk biosolids. "
            "Standard pyrolysis without secondary oxidation should not be treated as a "
            "compliant disposal route where PFAS is unknown or confirmed."
        )
        upgrade_l4 = (
            "Replace with dedicated incineration for highest PFAS confidence. "
            "Or add secondary oxidation at ≥850°C to reach Level 3 (ITS) — "
            "this provides design-based PFAS destruction without full incineration capital."
        )
    elif level == 3:
        upgrade_l3 = "Already Level 3 — ITS minimum viable configuration met."
        upgrade_l4 = (
            "Increase secondary oxidation temperature to ≥950°C for additional "
            "safety margin on shorter-chain PFAS compounds. Alternatively, consider "
            "dedicated incineration for the highest regulatory certainty."
        )
    else:
        upgrade_l3 = upgrade_l4 = "Already Level 4 — highest classification."

    return ITSClassificationResult(
        system_name=design.system_name,
        pathway_type=pathway_type,
        flowsheet_id=flowsheet_id,
        its_level=level,
        its_level_label=level_def["label"],
        its_level_short=level_def["short"],
        pfas_outcome=level_def["pfas_outcome"],
        pfas_status=level_def["status"],
        pfas_evidence_type=design.pfas_evidence_type,
        pfas_test_reference=design.pfas_test_reference,
        has_secondary_oxidation=design.has_secondary_oxidation,
        secondary_temp_c=design.secondary_temp_c,
        secondary_residence_time_s=design.secondary_residence_time_s,
        meets_temp_threshold=meets_temp,
        meets_residence_threshold=meets_res,
        has_apc=design.has_apc,
        classification_basis=basis,
        classification_notes=design.system_notes,
        upgrade_to_l3=upgrade_l3,
        upgrade_to_l4=upgrade_l4,
        colour=level_def["colour"],
    )


# ---------------------------------------------------------------------------
# MAIN ENGINE
# ---------------------------------------------------------------------------

def run_its_classification(
    flowsheets: list,
    custom_designs: Optional[dict] = None,
) -> ITSSystemAssessment:
    """
    Run ITS classification for all flowsheets.

    Parameters
    ----------
    flowsheets     : evaluated Flowsheet objects
    custom_designs : optional dict {pathway_type: ThermalSystemDesign}
                     to override default designs with actual vendor specs
    """
    results = []
    by_id   = {}
    by_type = {}
    counts  = {1: 0, 2: 0, 3: 0, 4: 0}
    acceptable = []
    not_acceptable = []
    conditional = []
    pfas_forced = []
    pfas_excluded = []

    for fs in flowsheets:
        ptype = fs.pathway_type
        fid   = fs.flowsheet_id

        # Use custom design if provided, else default
        if custom_designs and ptype in custom_designs:
            design = custom_designs[ptype]
        elif ptype in _DEFAULT_DESIGNS:
            design = _DEFAULT_DESIGNS[ptype]
        else:
            # Unknown pathway — conservative default (Level 2)
            design = ThermalSystemDesign(
                system_name=fs.name,
                reactor_type="unknown",
                primary_temp_c_min=0, primary_temp_c_max=0,
                has_secondary_oxidation=False,
                pfas_evidence_type="none",
                system_notes="Classification based on insufficient design information.",
            )

        result = _build_classification_result(fid, ptype, design)
        results.append(result)
        by_id[fid]    = result
        by_type[ptype] = result
        counts[result.its_level] += 1

        # Attach to flowsheet
        fs.its_classification = result

        level = result.its_level
        if level >= 3:
            acceptable.append(fs.name)
            pfas_forced.append(fs.name)
        elif level == 1:
            not_acceptable.append(fs.name)
            pfas_excluded.append(fs.name)
        else:
            conditional.append(fs.name)
            pfas_excluded.append(fs.name)  # Level 2 conditional — not accepted without validation

    # System statement (per spec requirement)
    system_statement = (
        "Modern engineered thermal systems — including advanced gasification and "
        "pyrolysis configurations — can achieve PFAS destruction where high-temperature "
        "oxidation stages are integrated and validated. "
        "Classification depends on system design, not on the reactor type label. "
        "Standard pyrolysis or gasification WITHOUT a secondary oxidation stage at "
        "≥850°C remains at Level 2 (Conditional) and cannot be accepted as a PFAS "
        "destruction route without independent validation."
    )

    narrative = _build_narrative(results, counts, acceptable, not_acceptable, conditional)

    return ITSSystemAssessment(
        classifications=results,
        level1_count=counts[1],
        level2_count=counts[2],
        level3_count=counts[3],
        level4_count=counts[4],
        acceptable_pathways=acceptable,
        not_acceptable_pathways=not_acceptable,
        conditional_pathways=conditional,
        pfas_forced_pathways=pfas_forced,
        pfas_excluded_pathways=pfas_excluded,
        system_statement=system_statement,
        assessment_narrative=narrative,
        _by_id=by_id,
        _by_type=by_type,
    )


def _build_narrative(results, counts, acceptable, not_acceptable, conditional) -> str:
    parts = [
        f"ITS Classification: {counts[4]} Level 4 (Incineration), "
        f"{counts[3]} Level 3 (ITS), {counts[2]} Level 2 (Partial Thermal), "
        f"{counts[1]} Level 1 (Transfer)."
    ]
    if acceptable:
        parts.append(
            f"PFAS-acceptable pathways (L3+L4): {', '.join(acceptable)}. "
            "These can proceed where PFAS is confirmed, subject to validation testing."
        )
    if not_acceptable:
        parts.append(
            f"NOT ACCEPTABLE where PFAS confirmed (L1 Transfer): "
            f"{', '.join(not_acceptable)}. "
            "PFAS is transferred to the output product, not destroyed."
        )
    if conditional:
        parts.append(
            f"CONDITIONAL (L2 — require validation): {', '.join(conditional[:4])}. "
            "Standard pyrolysis/gasification without secondary oxidation. "
            "Must demonstrate PFAS destruction before regulatory acceptance."
        )
    return " ".join(parts)


# ---------------------------------------------------------------------------
# CONVENIENCE — classify a specific vendor system
# ---------------------------------------------------------------------------

def classify_vendor_system(vendor_name: str) -> Optional[ThermalSystemDesign]:
    """Return design spec for a known vendor ITS system, if in library."""
    return ITS_VENDORS.get(vendor_name)


def get_all_its_vendors() -> list:
    """Return list of known ITS vendors in the library."""
    return list(ITS_VENDORS.keys())
