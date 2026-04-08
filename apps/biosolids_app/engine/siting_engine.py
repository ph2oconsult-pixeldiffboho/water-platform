"""
BioPoint V1 — Siting Engine.
Evaluates location flexibility as a core decision factor.

Key principle: treatment does NOT need to occur at the WWTP.
Many pathways — particularly thermal — are inherently flexible in location.

Classifies each pathway on four dimensions:
  1. Siting flexibility:   LOW / MEDIUM / HIGH
  2. Preferred location:   on-site / off-site / hybrid / co-location
  3. Planning risk:        LOW / MEDIUM / HIGH
  4. Footprint impact:     LOW / MEDIUM / HIGH

Two location archetypes:
  FIXED — Must be at the WWTP (wet-feed processes; return liquor to works)
    HTC: wet feed, process liquor returns to works headworks
    AD:  wet feed, centrate returns to liquid stream

  FLEXIBLE — Can be off-site (dry or inert feed; no liquid return)
    Incineration, pyrolysis, gasification: dried/dewatered cake hauled off-site
    Drying-only: dried cake hauled; dryer can be remote
    Centralised hub: explicitly designed for off-site

Decision modifiers:
  land_constraint HIGH        → favour FLEXIBLE pathways (+score)
  social_licence HIGH         → favour off-site / co-location (+score)
  multiple plants in system   → centralised/flexible hub preferred
  regulatory_pressure HIGH    → thermal off-site at industrial zone preferred

ph2o Consulting — BioPoint V1
"""

from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# SITING PROFILES — calibrated per pathway type
# ---------------------------------------------------------------------------

# (siting_flexibility, preferred_location, planning_risk, footprint_impact,
#  on_site_required, off_site_feasible, centralisation_potential,
#  odour_risk, noise_risk, stack_required, short_description)

_SITING_PROFILES = {
    "baseline": (
        "LOW", "on-site", "LOW", "LOW",
        True, False, False,
        True, False, False,
        "Dewatered cake stored and hauled on-site. Siting is constrained by WWTP boundary.",
    ),
    "AD": (
        "LOW", "on-site", "MEDIUM", "MEDIUM",
        True, False, False,
        True, True, False,
        "AD requires wet feed and centrate return. Must be at WWTP. "
        "Digesters have moderate footprint; biogas handling adds odour/noise risk.",
    ),
    "drying_only": (
        "MEDIUM", "on-site / off-site", "MEDIUM", "MEDIUM",
        False, True, False,
        True, True, False,
        "Dryer can be located on-site or at a nearby facility. "
        "Dried cake is road-transportable. Odour during drying is the primary constraint.",
    ),
    "pyrolysis": (
        "HIGH", "off-site / co-location", "MEDIUM", "LOW",
        False, True, True,
        False, True, True,
        "Pyrolysis reactor can be located at industrial park, brownfield, or waste facility. "
        "Dried cake is road-transportable. Low odour; stack requires air quality permit.",
    ),
    "gasification": (
        "HIGH", "off-site / co-location", "MEDIUM", "LOW",
        False, True, True,
        False, True, True,
        "Gasification plant is location-independent once feed is dried. "
        "Industrial park or waste facility siting preferred. "
        "Stack and syngas handling require environmental permitting.",
    ),
    "HTC": (
        "LOW", "on-site", "MEDIUM", "MEDIUM",
        True, False, False,
        True, True, False,
        "HTC requires wet sludge feed — must be at or adjacent to WWTP. "
        "Process liquor return adds further constraint. "
        "Moderate footprint; odour from process liquor handling.",
    ),
    "HTC_sidestream": (
        "LOW", "on-site", "MEDIUM", "MEDIUM",
        True, False, False,
        True, True, False,
        "HTC + sidestream: still requires wet feed at WWTP. "
        "Sidestream treatment adds footprint. On-site constraint unchanged.",
    ),
    "centralised": (
        "HIGH", "off-site hub", "HIGH", "MEDIUM",
        False, True, True,
        False, True, True,
        "Purpose-built off-site hub. Highest flexibility — site selected for access, "
        "planning, and co-location opportunity. "
        "Requires planning approval for new industrial facility.",
    ),
    "decentralised": (
        "MEDIUM", "on-site", "LOW", "LOW",
        False, False, False,
        True, True, False,
        "Site-based drying at each WWTP. Smaller footprint per site. "
        "No centralisation. Limited siting flexibility — constrained by WWTP boundary.",
    ),
    "incineration": (
        "HIGH", "off-site / co-location", "HIGH", "LOW",
        False, True, True,
        False, True, True,
        "FBF incineration is location-independent. Can co-locate with waste energy facility "
        "or industrial park. Stack requires significant air quality assessment and permitting. "
        "Off-site siting avoids WWTP community sensitivity.",
    ),
    "thp_incineration": (
        "MEDIUM", "on-site (THP) + off-site (incineration)", "HIGH", "MEDIUM",
        True, True, True,
        True, True, True,
        "THP must be at WWTP (wet feed). Incineration can be off-site. "
        "Split-siting: THP on-site, cake transported to off-site FBF. "
        "Highest planning complexity of all pathways.",
    ),
}

# Default for unknown pathway types
_DEFAULT_PROFILE = (
    "MEDIUM", "on-site / off-site", "MEDIUM", "MEDIUM",
    False, True, False,
    True, True, False,
    "Siting profile not fully characterised — assume moderate flexibility.",
)

# Score adjustment by siting flexibility (applied when siting is a key driver)
_SITING_FLEXIBILITY_BONUS = {"HIGH": 6, "MEDIUM": 2, "LOW": -4}

# Planning risk penalty (applied always — high planning risk penalises score)
_PLANNING_RISK_PENALTY = {"HIGH": -4, "MEDIUM": -2, "LOW": 0}


# ---------------------------------------------------------------------------
# DATACLASSES
# ---------------------------------------------------------------------------

@dataclass
class SitingProfile:
    """Siting assessment for one flowsheet."""
    flowsheet_id: str = ""
    flowsheet_name: str = ""
    pathway_type: str = ""

    # Core dimensions
    siting_flexibility: str = "MEDIUM"      # LOW / MEDIUM / HIGH
    preferred_location: str = "on-site"
    planning_risk: str = "MEDIUM"           # LOW / MEDIUM / HIGH
    footprint_impact: str = "MEDIUM"        # LOW / MEDIUM / HIGH

    # Location constraints
    on_site_required: bool = True
    off_site_feasible: bool = False
    centralisation_potential: bool = False

    # Neighbour impact factors
    odour_risk: bool = False
    noise_risk: bool = False
    stack_required: bool = False
    neighbour_impact_rating: str = "Low"    # Low / Moderate / High

    # Narrative
    siting_description: str = ""
    planning_narrative: str = ""

    # Score adjustment (context-dependent)
    siting_score_adjustment: float = 0.0
    adjustment_reason: str = ""

    # Flags for display
    flexibility_badge: str = ""    # "🟢 High" / "🟡 Medium" / "🔴 Low"
    location_badge: str = ""       # Short label for UI


@dataclass
class SitingAssessment:
    """System-level siting assessment across all flowsheets."""
    profiles: list = field(default_factory=list)        # List[SitingProfile]
    high_flexibility_pathways: list = field(default_factory=list)
    fixed_location_pathways: list = field(default_factory=list)
    off_site_feasible_pathways: list = field(default_factory=list)

    # Context flags
    land_constrained: bool = False
    social_licence_sensitive: bool = False
    multi_site_system: bool = False

    # Score modifiers applied
    modifiers_applied: bool = False

    # System narrative
    siting_narrative: str = ""

    # Lookup
    _by_id: dict = field(default_factory=dict)

    def get(self, flowsheet_id: str) -> Optional[SitingProfile]:
        return self._by_id.get(flowsheet_id)


# ---------------------------------------------------------------------------
# MAIN ENGINE
# ---------------------------------------------------------------------------

def run_siting_engine(
    flowsheets: list,
    land_constraint: str = "low",          # low / moderate / high
    social_licence_pressure: str = "low",  # low / moderate / high
    multi_site_system: bool = False,
    regulatory_pressure: str = "moderate",
) -> SitingAssessment:
    """
    Evaluate siting characteristics for all flowsheets.

    Parameters
    ----------
    flowsheets             : evaluated Flowsheet objects
    land_constraint        : from StrategicInputs — low/moderate/high
    social_licence_pressure: from StrategicInputs — low/moderate/high
    multi_site_system      : True if evaluating a regional multi-site context
    regulatory_pressure    : from StrategicInputs — low/moderate/high
    """
    land_high     = land_constraint in ("high", "moderate")
    social_high   = social_licence_pressure in ("high", "moderate")
    siting_matters = land_high or social_high or multi_site_system

    profiles = []
    by_id = {}
    high_flex = []
    fixed_loc = []
    off_site  = []

    for fs in flowsheets:
        sp = _build_siting_profile(
            fs, land_high, social_high, multi_site_system,
            regulatory_pressure, siting_matters
        )
        profiles.append(sp)
        by_id[fs.flowsheet_id] = sp
        fs.siting = sp    # Attach to flowsheet

        if sp.siting_flexibility == "HIGH":
            high_flex.append(fs.name)
        if sp.on_site_required and not sp.off_site_feasible:
            fixed_loc.append(fs.name)
        if sp.off_site_feasible:
            off_site.append(fs.name)

    # Apply score adjustments when siting is a key driver
    if siting_matters:
        for fs in flowsheets:
            sp = fs.siting
            if sp.siting_score_adjustment != 0.0:
                fs.score = max(0.0, fs.score + sp.siting_score_adjustment)

    narrative = _build_narrative(
        profiles, land_high, social_high, multi_site_system,
        high_flex, fixed_loc
    )

    return SitingAssessment(
        profiles=profiles,
        high_flexibility_pathways=high_flex,
        fixed_location_pathways=fixed_loc,
        off_site_feasible_pathways=off_site,
        land_constrained=land_high,
        social_licence_sensitive=social_high,
        multi_site_system=multi_site_system,
        modifiers_applied=siting_matters,
        siting_narrative=narrative,
        _by_id=by_id,
    )


# ---------------------------------------------------------------------------
# PROFILE BUILDER
# ---------------------------------------------------------------------------

def _build_siting_profile(
    fs, land_high: bool, social_high: bool,
    multi_site: bool, regulatory_pressure: str,
    siting_matters: bool,
) -> SitingProfile:
    ptype = fs.pathway_type
    raw = _SITING_PROFILES.get(ptype, _DEFAULT_PROFILE)

    (flex, pref_loc, plan_risk, foot_impact,
     on_site_req, off_site_feas, central_pot,
     odour, noise, stack, desc) = raw

    # Neighbour impact rating
    neighbour_factors = sum([odour, noise, stack])
    if neighbour_factors >= 2:
        neighbour = "High"
    elif neighbour_factors == 1:
        neighbour = "Moderate"
    else:
        neighbour = "Low"

    # Planning narrative
    plan_parts = []
    if plan_risk == "HIGH":
        plan_parts.append(
            "HIGH planning risk: new thermal facility or hub requires "
            "environmental impact assessment, air quality permit, "
            "and community consultation. Allow 2–4 year permitting timeline."
        )
    elif plan_risk == "MEDIUM":
        plan_parts.append(
            "MEDIUM planning risk: process upgrade or new unit within WWTP boundary "
            "typically requires consent but follows established permit pathways. "
            "Allow 12–24 months."
        )
    else:
        plan_parts.append(
            "LOW planning risk: no new facility or technology class — "
            "consent within existing WWTP discharge permit likely."
        )

    if stack:
        plan_parts.append(
            "Stack emissions require air quality dispersion modelling "
            "and may trigger Tier 2 air quality consent."
        )
    if social_high and neighbour == "High":
        plan_parts.append(
            "High social licence pressure + High neighbour impact: "
            "off-site industrial zone siting strongly preferred to "
            "reduce community opposition risk."
        )

    # Score adjustment — only applied when siting is a decision driver
    adj = 0.0
    adj_reason = ""
    if siting_matters:
        flex_adj   = _SITING_FLEXIBILITY_BONUS.get(flex, 0)
        plan_adj   = _PLANNING_RISK_PENALTY.get(plan_risk, 0)

        # Land constraint: high flexibility gets extra bonus
        if land_high and flex == "HIGH":
            flex_adj += 4
        elif land_high and flex == "LOW":
            flex_adj -= 3

        # Social licence: off-site siting reduces community risk → bonus
        if social_high and off_site_feas:
            flex_adj += 3
        elif social_high and on_site_req and not off_site_feas:
            flex_adj -= 2

        # Multi-site: centralisation potential is a positive
        if multi_site and central_pot:
            flex_adj += 4

        adj = flex_adj + plan_adj
        if adj != 0:
            adj_parts = []
            if flex_adj > 0:
                adj_parts.append(f"siting flexibility bonus +{flex_adj}")
            elif flex_adj < 0:
                adj_parts.append(f"siting flexibility penalty {flex_adj}")
            if plan_adj < 0:
                adj_parts.append(f"planning risk penalty {plan_adj}")
            adj_reason = "; ".join(adj_parts)

    # Badges
    flex_badges = {"HIGH": "🟢 High", "MEDIUM": "🟡 Medium", "LOW": "🔴 Low"}
    loc_badges = {
        "on-site": "On-site",
        "off-site / co-location": "Off-site",
        "off-site hub": "Hub",
        "on-site / off-site": "Flexible",
        "on-site (THP) + off-site (incineration)": "Split",
    }

    return SitingProfile(
        flowsheet_id=fs.flowsheet_id,
        flowsheet_name=fs.name,
        pathway_type=ptype,
        siting_flexibility=flex,
        preferred_location=pref_loc,
        planning_risk=plan_risk,
        footprint_impact=foot_impact,
        on_site_required=on_site_req,
        off_site_feasible=off_site_feas,
        centralisation_potential=central_pot,
        odour_risk=odour,
        noise_risk=noise,
        stack_required=stack,
        neighbour_impact_rating=neighbour,
        siting_description=desc,
        planning_narrative=" ".join(plan_parts),
        siting_score_adjustment=round(adj, 1),
        adjustment_reason=adj_reason,
        flexibility_badge=flex_badges.get(flex, flex),
        location_badge=loc_badges.get(pref_loc, pref_loc[:10]),
    )


# ---------------------------------------------------------------------------
# NARRATIVE BUILDER
# ---------------------------------------------------------------------------

def _build_narrative(profiles, land_high, social_high, multi_site,
                      high_flex, fixed_loc) -> str:
    parts = []

    if land_high or social_high or multi_site:
        drivers = []
        if land_high:        drivers.append("land constraint")
        if social_high:      drivers.append("community sensitivity")
        if multi_site:       drivers.append("multi-site system")
        parts.append(
            f"Siting is an active decision factor ({', '.join(drivers)}). "
            "Score adjustments applied."
        )

    if high_flex:
        parts.append(
            f"High flexibility pathways — can be sited off-site or at industrial hub: "
            f"{', '.join(high_flex[:4])}."
        )
    if fixed_loc:
        parts.append(
            f"Fixed-location pathways — must remain at WWTP: "
            f"{', '.join(fixed_loc[:4])}."
        )

    if social_high:
        parts.append(
            "High community sensitivity: thermal pathways (incineration, pyrolysis, gasification) "
            "are preferred off-site at industrial/waste zones — "
            "this removes them from the WWTP community interface entirely."
        )

    if multi_site:
        parts.append(
            "Multi-site system: flexible-location pathways enable hub siting "
            "at the most logistically efficient location rather than defaulting "
            "to the largest WWTP."
        )

    if not (land_high or social_high or multi_site):
        parts.append(
            "No active siting constraints — all pathways evaluated on their technical merit. "
            "Siting score adjustments not applied."
        )

    return " ".join(parts)
