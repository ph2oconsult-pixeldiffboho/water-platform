"""
BioPoint V1 — Inevitability Engine.
Evaluates which pathway outcomes are forced by hard constraints,
regardless of cost or preference.

Three inevitability drivers:
  1. PFAS presence    → forces incineration (or equivalent thermal destruction)
  2. Disposal market  → forces thermal (as disposal routes close)
  3. Energy deficit   → forces wet pathway (drying not viable without external input)

Output: Three-state pathway classification per flowsheet:
  - PREFERRED       — best option under current conditions
  - CONDITIONAL     — viable if specific conditions are met
  - INEVITABLE      — forced outcome regardless of preference

Plus board-ready three-pathway summary:
  - Best current option
  - Best future option (conditioned on preconditioning)
  - Fallback under constraint

ph2o Consulting — BioPoint V1
"""

from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# INEVITABILITY DRIVERS
# ---------------------------------------------------------------------------

class InvDriver:
    """Enumeration of inevitability drivers."""
    PFAS           = "PFAS_PRESENCE"
    DISPOSAL_CLOSE = "DISPOSAL_MARKET_CLOSURE"
    ENERGY_DEFICIT = "ENERGY_DEFICIT"
    REGULATORY     = "REGULATORY_TIGHTENING"
    CAPACITY       = "CAPACITY_CONSTRAINT"


# ---------------------------------------------------------------------------
# DATACLASSES
# ---------------------------------------------------------------------------

@dataclass
class PathwayClassification:
    """Classification of a single flowsheet under inevitability logic."""
    flowsheet_id: str = ""
    flowsheet_name: str = ""
    pathway_type: str = ""

    classification: str = ""       # "PREFERRED" / "CONDITIONAL" / "INEVITABLE" / "EXCLUDED"
    classification_basis: str = "" # Why this classification was assigned

    # Conditions that must be true for CONDITIONAL to hold
    conditions: list = field(default_factory=list)

    # Drivers forcing this outcome (for INEVITABLE)
    forced_by: list = field(default_factory=list)

    # What makes this pathway fail (for EXCLUDED)
    exclusion_reason: str = ""

    # Time horizon
    horizon: str = ""  # "NOW" / "NEAR_TERM" / "FUTURE"


@dataclass
class InevitabilityAssessment:
    """Full inevitability assessment across all flowsheets."""

    # Active inevitability drivers
    pfas_driver_active: bool = False
    disposal_driver_active: bool = False
    energy_deficit_driver_active: bool = False
    regulatory_driver_active: bool = False

    # Driver narratives
    pfas_narrative: str = ""
    disposal_narrative: str = ""
    energy_narrative: str = ""
    regulatory_narrative: str = ""

    # Classified flowsheets
    classifications: list = field(default_factory=list)   # List[PathwayClassification]

    # Three-pathway board summary
    best_current: Optional[PathwayClassification] = None
    best_future: Optional[PathwayClassification] = None
    inevitable_fallback: Optional[PathwayClassification] = None

    # Board output
    board_summary: str = ""
    board_preferred: str = ""
    board_conditional: str = ""
    board_inevitable: str = ""

    # What changes the outcome
    outcome_change_triggers: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# MAIN ENGINE
# ---------------------------------------------------------------------------

def run_inevitability(all_flowsheets: list, feedstock, assets, strategic,
                       preconditioning=None, energy_systems: dict = None) -> InevitabilityAssessment:
    """
    Evaluate inevitability constraints across all flowsheets.
    energy_systems: dict {flowsheet_id: EnergySystemResult}
    """
    fs_in = feedstock
    pfas = fs_in.pfas_present       # "yes" / "no" / "unknown"
    reg  = strategic.regulatory_pressure  # "low" / "moderate" / "high"

    # -----------------------------------------------------------------------
    # 1. IDENTIFY ACTIVE DRIVERS
    # -----------------------------------------------------------------------

    # PFAS driver
    pfas_active = pfas == "yes"
    pfas_uncertain = pfas == "unknown"
    if pfas_active:
        pfas_narrative = (
            "PFAS is confirmed present. Land application and most product reuse routes are CLOSED. "
            "Thermal destruction (incineration >850°C) is the only regulatory-defensible disposal route. "
            "This is a hard constraint — it cannot be overcome by economics or optimization preference."
        )
    elif pfas_uncertain:
        pfas_narrative = (
            "PFAS status is unknown. If confirmed present, land application will close and "
            "incineration becomes the inevitable fallback. Characterisation is urgent."
        )
    else:
        pfas_narrative = "PFAS not flagged. Land application routes remain open."

    # Disposal market driver
    disposal_active = (
        reg == "high" or
        assets.disposal_cost_per_tds > 350 or
        strategic.optimisation_priority == "lowest_disposal_dependency"
    )
    if disposal_active:
        disposal_narrative = (
            f"Disposal constraint is active: cost ${assets.disposal_cost_per_tds:.0f}/tDS "
            f"and regulatory pressure is {reg}. "
            "As disposal markets tighten, thermal routes that eliminate disposal dependency "
            "become inevitable — the question is timing and pathway choice, not whether."
        )
    else:
        disposal_narrative = "Disposal market constraints are not yet binding."

    # Energy deficit driver — are most thermal routes non-viable without external energy?
    non_viable_count = 0
    if energy_systems:
        non_viable_count = sum(
            1 for esys in energy_systems.values()
            if esys.energy_viability_flag == "ENERGY NON-VIABLE WITHOUT EXTERNAL INPUT"
        )
    energy_driver_active = non_viable_count >= 3
    if energy_driver_active:
        energy_narrative = (
            f"{non_viable_count} of 9 pathways flagged ENERGY NON-VIABLE WITHOUT EXTERNAL INPUT. "
            "At current feed DS%, drying energy exceeds available internal heat for most thermal routes. "
            "Wet pathways (HTC, AD without drying) are forced by this constraint until "
            "feed DS% improves through preconditioning."
        )
    else:
        energy_narrative = "Energy deficit does not force pathway selection — multiple viable options exist."

    # Regulatory driver
    reg_active = reg == "high"
    if reg_active:
        regulatory_narrative = (
            "High regulatory pressure: pathways without a clear stabilisation class outcome "
            "(Class A or B) or with unresolved PFAS risk face increasing regulatory exposure. "
            "This progressively narrows viable options toward compliant thermal or land-application routes."
        )
    else:
        regulatory_narrative = f"Regulatory pressure is {reg} — not yet a forcing constraint."

    # -----------------------------------------------------------------------
    # 2. CLASSIFY EACH FLOWSHEET
    # -----------------------------------------------------------------------
    classifications = []
    for fs in all_flowsheets:
        cls = _classify_flowsheet(
            fs, pfas_active, pfas_uncertain, disposal_active,
            energy_driver_active, reg_active,
            energy_systems, preconditioning
        )
        classifications.append(cls)

    # -----------------------------------------------------------------------
    # 3. IDENTIFY THREE-PATHWAY BOARD SUMMARY
    # -----------------------------------------------------------------------
    preferred_cls   = [c for c in classifications if c.classification == "PREFERRED"]
    conditional_cls = [c for c in classifications if c.classification == "CONDITIONAL"]
    inevitable_cls  = [c for c in classifications if c.classification == "INEVITABLE"]
    excluded_cls    = [c for c in classifications if c.classification == "EXCLUDED"]

    best_current  = preferred_cls[0]  if preferred_cls  else (conditional_cls[0] if conditional_cls else None)
    best_future   = conditional_cls[0] if conditional_cls else None
    inevitable_fb = inevitable_cls[0]  if inevitable_cls  else None

    # If PFAS active, incineration is the inevitable fallback
    if pfas_active:
        incin_cls = next((c for c in classifications if c.pathway_type == "incineration"), None)
        if incin_cls:
            incin_cls.classification = "INEVITABLE"
            incin_cls.forced_by = [InvDriver.PFAS]
            incin_cls.classification_basis = (
                "PFAS confirmed — incineration is the only thermal destruction route "
                "with verified PFAS elimination at operating temperatures. "
                "This outcome is independent of cost or strategic preference."
            )
            inevitable_fb = incin_cls

    # -----------------------------------------------------------------------
    # 4. BOARD SUMMARY
    # -----------------------------------------------------------------------
    board_pref = (
        f"Best current option: {best_current.flowsheet_name}. "
        f"{best_current.classification_basis}"
        if best_current else "No preferred pathway identified under current conditions."
    )
    board_cond = (
        f"Best future option: {best_future.flowsheet_name} — conditional on: "
        f"{'; '.join(best_future.conditions[:2])}."
        if best_future else "No conditional pathway improvement identified."
    )
    board_inev = (
        f"Inevitable fallback: {inevitable_fb.flowsheet_name}. "
        f"Forced by: {', '.join(inevitable_fb.forced_by)}. "
        f"{inevitable_fb.classification_basis}"
        if inevitable_fb else "No inevitable outcome identified under current constraints."
    )

    board_summary = _build_board_summary(
        best_current, best_future, inevitable_fb,
        pfas_active, pfas_uncertain, disposal_active, energy_driver_active
    )

    # What changes the outcome
    triggers = _outcome_change_triggers(
        pfas_active, pfas_uncertain, disposal_active,
        energy_driver_active, preconditioning, fs_in
    )

    return InevitabilityAssessment(
        pfas_driver_active=pfas_active,
        disposal_driver_active=disposal_active,
        energy_deficit_driver_active=energy_driver_active,
        regulatory_driver_active=reg_active,
        pfas_narrative=pfas_narrative,
        disposal_narrative=disposal_narrative,
        energy_narrative=energy_narrative,
        regulatory_narrative=regulatory_narrative,
        classifications=classifications,
        best_current=best_current,
        best_future=best_future,
        inevitable_fallback=inevitable_fb,
        board_summary=board_summary,
        board_preferred=board_pref,
        board_conditional=board_cond,
        board_inevitable=board_inev,
        outcome_change_triggers=triggers,
    )


# ---------------------------------------------------------------------------
# FLOWSHEET CLASSIFIER
# ---------------------------------------------------------------------------

def _classify_flowsheet(fs, pfas_active, pfas_uncertain, disposal_active,
                          energy_driver_active, reg_active,
                          energy_systems, preconditioning) -> PathwayClassification:
    ptype = fs.pathway_type
    esys  = energy_systems.get(fs.flowsheet_id) if energy_systems else None
    viable_flag = esys.energy_viability_flag if esys else "VIABLE"

    # --- INCINERATION ---
    if ptype == "incineration":
        if pfas_active:
            return PathwayClassification(
                flowsheet_id=fs.flowsheet_id,
                flowsheet_name=fs.name,
                pathway_type=ptype,
                classification="INEVITABLE",
                classification_basis=(
                    "PFAS confirmed — incineration is the only verifiable destruction route. "
                    "This is a regulatory requirement, not a preference."
                ),
                forced_by=[InvDriver.PFAS],
                horizon="NOW",
            )
        elif disposal_active and viable_flag != "ENERGY NON-VIABLE WITHOUT EXTERNAL INPUT":
            return PathwayClassification(
                flowsheet_id=fs.flowsheet_id,
                flowsheet_name=fs.name,
                pathway_type=ptype,
                classification="CONDITIONAL",
                classification_basis=(
                    "Incineration becomes inevitable as disposal markets close. "
                    "Currently conditional on feed DS% improvement and CAPEX approval."
                ),
                conditions=[
                    "Feed DS% reaches 28–30% (upstream thickening or THP)",
                    "CAPEX is approved and permitted",
                    "Co-treatment at regional facility evaluated to reduce own-asset risk",
                ],
                horizon="NEAR_TERM",
            )
        elif viable_flag == "ENERGY NON-VIABLE WITHOUT EXTERNAL INPUT":
            return PathwayClassification(
                flowsheet_id=fs.flowsheet_id,
                flowsheet_name=fs.name,
                pathway_type=ptype,
                classification="CONDITIONAL",
                classification_basis=(
                    "Incineration is not energy-viable at current feed DS%. "
                    "Becomes viable with preconditioning to 28–30% DS."
                ),
                conditions=[
                    "Feed DS% reaches ≥28% (upstream thickening, THP, or filter press)",
                    "Auxiliary fuel confirmed and costed for residual drying gap",
                ],
                horizon="FUTURE",
            )
        else:
            return PathwayClassification(
                flowsheet_id=fs.flowsheet_id,
                flowsheet_name=fs.name,
                pathway_type=ptype,
                classification="CONDITIONAL",
                classification_basis="Incineration viable but not preferred under current economics.",
                conditions=["CAPEX justified", "Disposal cost escalation confirmed"],
                horizon="FUTURE",
            )

    # --- HTC ---
    if ptype == "HTC":
        if energy_driver_active:
            return PathwayClassification(
                flowsheet_id=fs.flowsheet_id,
                flowsheet_name=fs.name,
                pathway_type=ptype,
                classification="PREFERRED",
                classification_basis=(
                    "HTC avoids the drying energy constraint that makes all combustion-based "
                    "routes non-viable at current feed DS%. Preferred under energy deficit conditions."
                ),
                horizon="NOW",
            )
        else:
            return PathwayClassification(
                flowsheet_id=fs.flowsheet_id,
                flowsheet_name=fs.name,
                pathway_type=ptype,
                classification="PREFERRED",
                classification_basis=(
                    "HTC offers mass reduction without drying burden. "
                    "Highest economics under current conditions."
                ),
                horizon="NOW",
            )

    # --- AD ---
    if ptype == "AD":
        return PathwayClassification(
            flowsheet_id=fs.flowsheet_id,
            flowsheet_name=fs.name,
            pathway_type=ptype,
            classification="PREFERRED",
            classification_basis=(
                "AD is viable now where infrastructure exists and provides near-term "
                "positive economics while strategic pathway is resolved."
            ),
            horizon="NOW",
        )

    # --- BASELINE ---
    if ptype == "baseline":
        if disposal_active or pfas_active:
            return PathwayClassification(
                flowsheet_id=fs.flowsheet_id,
                flowsheet_name=fs.name,
                pathway_type=ptype,
                classification="EXCLUDED",
                exclusion_reason=(
                    "Baseline disposal is not tenable under active disposal constraint or PFAS driver. "
                    "Full disposal cost retained with no mass reduction or regulatory compliance."
                ),
                horizon="NOW",
            )
        return PathwayClassification(
            flowsheet_id=fs.flowsheet_id,
            flowsheet_name=fs.name,
            pathway_type=ptype,
            classification="CONDITIONAL",
            classification_basis="Acceptable short-term only. Disposal cost trajectory makes this untenable.",
            conditions=["Disposal market remains available", "Regulatory pressure does not escalate"],
            horizon="NOW",
        )

    # --- PYROLYSIS / GASIFICATION ---
    if ptype in ("pyrolysis", "gasification"):
        if viable_flag == "ENERGY NON-VIABLE WITHOUT EXTERNAL INPUT":
            return PathwayClassification(
                flowsheet_id=fs.flowsheet_id,
                flowsheet_name=fs.name,
                pathway_type=ptype,
                classification="CONDITIONAL",
                classification_basis=(
                    f"{ptype.title()} is energy non-viable at current feed DS%. "
                    "Conditional on preconditioning to adequate DS% and energy closure confirmation."
                ),
                conditions=[
                    f"Feed DS% reaches ≥{'87' if ptype == 'pyrolysis' else '90'}% "
                    f"(requires drying — itself energy constrained at current DS%)",
                    "Process heat self-supply confirmed with vendor at this GCV",
                    "Product market (biochar/syngas) confirmed",
                ],
                horizon="FUTURE",
            )

    # --- HTC, DRYING ONLY, CENTRALISED, DECENTRALISED ---
    if viable_flag == "ENERGY NON-VIABLE WITHOUT EXTERNAL INPUT":
        return PathwayClassification(
            flowsheet_id=fs.flowsheet_id,
            flowsheet_name=fs.name,
            pathway_type=ptype,
            classification="CONDITIONAL",
            classification_basis=f"Energy non-viable at current DS%. External energy source required.",
            conditions=["Waste heat or low-cost energy source confirmed", "Feed DS% improved"],
            horizon="FUTURE",
        )

    return PathwayClassification(
        flowsheet_id=fs.flowsheet_id,
        flowsheet_name=fs.name,
        pathway_type=ptype,
        classification="CONDITIONAL",
        classification_basis=f"{fs.name}: viable under specific conditions.",
        horizon="NEAR_TERM",
    )


# ---------------------------------------------------------------------------
# BOARD SUMMARY BUILDER
# ---------------------------------------------------------------------------

def _build_board_summary(best_current, best_future, inevitable_fb,
                          pfas_active, pfas_uncertain,
                          disposal_active, energy_driver_active) -> str:
    parts = []

    if best_current:
        parts.append(
            f"Best current option: {best_current.flowsheet_name}. "
            f"{best_current.classification_basis}"
        )

    if energy_driver_active:
        parts.append(
            "The drying energy constraint is the primary forcing condition: "
            "at current feed DS%, all combustion-based pathways are non-viable without "
            "external energy. This forces wet-pathway options (HTC, AD) in the near term."
        )

    if best_future and best_future != best_current:
        parts.append(
            f"Best future option: {best_future.flowsheet_name}. "
            f"Conditional on: {'; '.join(best_future.conditions[:2]) if best_future.conditions else 'preconditioning'}."
        )

    if pfas_active and inevitable_fb:
        parts.append(
            f"Inevitable outcome: {inevitable_fb.flowsheet_name} is forced by PFAS. "
            "This is non-negotiable — begin permitting and CAPEX planning now."
        )
    elif pfas_uncertain:
        parts.append(
            "PFAS status unknown — if confirmed, incineration becomes inevitable. "
            "PFAS characterisation is the single highest-priority validation action."
        )
    elif disposal_active and inevitable_fb:
        parts.append(
            f"Eventual outcome: {inevitable_fb.flowsheet_name} is the inevitable direction "
            "as disposal markets tighten. Timing depends on disposal cost trajectory."
        )

    return " ".join(parts)


def _outcome_change_triggers(pfas_active, pfas_uncertain, disposal_active,
                              energy_driver_active, preconditioning, fs_in) -> list:
    triggers = []

    if energy_driver_active:
        current_ds = fs_in.dewatered_ds_percent
        if preconditioning and preconditioning.any_scenario_reaches_28pct:
            triggers.append(
                f"Feed DS% reaching 28% through {preconditioning.best_for_ds_threshold.scenario_name}: "
                "opens incineration energy closure, unlocks thermal pathway viability."
            )
        else:
            triggers.append(
                f"Feed DS% improvement from {current_ds:.0f}% to 28–30% "
                "(requires upstream thickening and/or THP): "
                "changes energy balance for all thermal routes."
            )

    if pfas_uncertain:
        triggers.append(
            "PFAS characterisation result: if positive → incineration mandatory; "
            "if negative → full pathway choice remains open."
        )

    if disposal_active:
        triggers.append(
            "Disposal cost crossing $400/tDS: justifies incineration CAPEX on lifecycle cost basis alone."
        )

    triggers.append(
        "Electricity price: every $0.05/kWh increase in electricity cost "
        "adds ~$6–17M/yr to drying-based pathway OPEX at this scale, "
        "making wet pathways (HTC) more attractive."
    )

    triggers.append(
        "Hydrochar/biochar market development: confirmed offtake at >$100/t "
        "shifts economics decisively toward HTC or pyrolysis."
    )

    return triggers
