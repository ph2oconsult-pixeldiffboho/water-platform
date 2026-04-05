"""
apps/wastewater_app/mbr_layer.py

MBR Applicability & Architecture Layer — Production V1
=======================================================

Positions MBR as a primary treatment architecture and produces
structured applicability, feasibility, and credibility notes
for use by downstream layers.

MBR role
--------
MBR is a solids separation system that replaces secondary clarifiers
with hollow-fibre or flat-sheet membranes. It is a full process
architecture — not an aeration technology (unlike MABR) and not a
polishing step (unlike DNF). It operates at high MLSS (8,000–15,000
mg/L), produces high-quality permeate (TSS <1 mg/L), and requires
significant energy for membrane scouring and permeate pumping.

Applicability
-------------
Strong fit: reuse applications, extreme footprint constraint,
  high effluent quality, clarifier instability, high-strength influent.
Moderate fit: failing clarifiers needing upgrade + effluent improvement.
Weak fit: energy-constrained plants, low OPEX tolerance, land available.

Differentiation from MABR
--------------------------
MBR  = filtration + solids separation (replaces clarifier)
MABR = oxygen delivery + biological intensification (augments process)
They address different problems and can co-exist: MABR enhances
biological performance within an MBR plant's bioreactor.

Design principles
-----------------
- Pure functions, no side effects, no Streamlit
- Does NOT modify stack selection logic
- Adds explanatory and credibility content only
- Reads plant_context dict; never modifies it

Main entry point
----------------
  assess_mbr_applicability(plant_context) -> MbrApplicabilityReport
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


# ── Fit level constants ───────────────────────────────────────────────────────
MBR_STRONG   = "Strong"
MBR_MODERATE = "Moderate"
MBR_WEAK     = "Weak"
MBR_NA       = "Not applicable"


# ── Dataclass ─────────────────────────────────────────────────────────────────

@dataclass
class MbrApplicabilityReport:
    """
    Architecture-level applicability assessment for MBR as a treatment solution.
    Produced regardless of whether MBR is in the current recommended stack.
    """
    # ── Applicability ──────────────────────────────────────────────────────────
    fit_level:          str   # MBR_STRONG / MBR_MODERATE / MBR_WEAK / MBR_NA
    fit_factors:        List[str]   # reasons driving the fit level
    weak_fit_factors:   List[str]   # reasons against MBR for this scenario

    # ── Architecture role ──────────────────────────────────────────────────────
    architecture_role:  str   # one-sentence role description
    not_a:              List[str]   # explicit "MBR is NOT X" statements

    # ── Engineering notes ──────────────────────────────────────────────────────
    energy_note:        str
    operations_note:    str
    lifecycle_note:     str

    # ── Differentiation ───────────────────────────────────────────────────────
    mabr_differentiation: Optional[str]   # only populated if MABR is relevant
    decision_tension:   str

    # ── Credibility statements ────────────────────────────────────────────────
    credibility_notes:  List[str]

    # ── Existing MBR optimisation ─────────────────────────────────────────────
    existing_mbr:       bool          # True if plant is already MBR
    existing_mbr_note:  Optional[str] # guidance for existing MBR plants

    # ── memDENSE dual-role (v24Z42) ───────────────────────────────────────────
    memdense_role:      str     # "existing_optimisation" / "new_enhancement" / "not_applicable"
    memdense_benefits:  List[str]
    memdense_risks:     List[str]
    memdense_decision_tension: str
    memdense_note:      Optional[str]  # surfaced in credibility output


# ── Applicability assessment ──────────────────────────────────────────────────

def assess_mbr_applicability(
    plant_context: Optional[dict] = None,
) -> MbrApplicabilityReport:
    """
    Assess MBR applicability for this plant scenario.

    Parameters
    ----------
    plant_context : dict, optional
        Standard plant context dict (same as passed to other layers).
        Reads: is_mbr, reuse_application, footprint_constrained,
               energy_constrained, clarifier_util, high_mlss,
               solids_carryover, membrane_fouling, plant_size_mld,
               location_type, is_sbr.

    Returns
    -------
    MbrApplicabilityReport
        Purely informational. Does NOT modify plant_context.
    """
    ctx = plant_context or {}

    # ── Context signals ───────────────────────────────────────────────────────
    is_mbr             = bool(ctx.get("is_mbr", False))
    reuse              = bool(ctx.get("reuse_application", False))
    footprint_const    = bool(ctx.get("footprint_constrained", False))
    energy_const       = bool(ctx.get("energy_constrained", False))
    high_effluent_req  = bool(ctx.get("high_effluent_quality", False)) or reuse
    clarifier_util     = float(ctx.get("clarifier_util", 0.0) or 0.0)
    high_mlss          = bool(ctx.get("high_mlss", False))
    solids_carryover   = bool(ctx.get("solids_carryover", False))
    membrane_fouling   = bool(ctx.get("membrane_fouling", False))
    is_sbr             = bool(ctx.get("is_sbr", False))
    location           = ctx.get("location_type", "metro") or "metro"
    greenfield         = bool(ctx.get("greenfield", False))
    industrial_influent= bool(ctx.get("industrial_influent", False))
    overflow_risk      = bool(ctx.get("overflow_risk", False))
    size_mld           = float(ctx.get("plant_size_mld", 10.0) or 10.0)

    # ── Strong fit factors ────────────────────────────────────────────────────
    strong = []
    if reuse:
        strong.append(
            "Reuse application: MBR produces TSS <1 mg/L permeate suitable for "
            "direct reuse without tertiary filtration."
        )
    if footprint_const:
        strong.append(
            "Footprint constrained: MBR operates at 8,000\u201315,000 mg/L MLSS, "
            "eliminating secondary clarifiers and reducing process footprint by "
            "30\u201350% relative to conventional activated sludge."
        )
    if high_effluent_req and not reuse:
        strong.append(
            "High effluent quality required: MBR consistently achieves TSS <1 mg/L, "
            "BOD <5 mg/L, and turbidity <1 NTU — superior to conventional clarification."
        )
    if clarifier_util >= 1.2 or (solids_carryover and high_mlss):
        strong.append(
            "Clarifier instability: MBR eliminates the secondary clarifier constraint "
            "entirely, replacing it with membrane separation at high MLSS."
        )
    if industrial_influent:
        strong.append(
            "High-strength or variable influent: MBR high-MLSS operation provides "
            "greater biological resilience to load variability."
        )

    # ── Weak fit factors ──────────────────────────────────────────────────────
    weak = []
    if energy_const:
        weak.append(
            "Energy constrained: MBR consumes 0.3\u20130.8 kWh/m\u00b3 more than "
            "conventional BNR due to membrane scouring and permeate pumping. "
            "This is a material OPEX penalty for energy-sensitive plants."
        )
    if location == "remote":
        weak.append(
            "Remote location: membrane replacement (every 8\u201310 years) and CIP "
            "chemicals require reliable specialist supply chain access."
        )
    if size_mld < 2.0:
        weak.append(
            "Small plant size (<2 MLD): membrane system unit costs are disproportionately "
            "high at this scale; conventional BNR with good sludge management is likely "
            "more cost-effective."
        )
    if is_sbr:
        weak.append(
            "SBR plant: MBR retrofits require significant reconfiguration of the batch "
            "cycle and decant system — not a straightforward upgrade pathway."
        )

    # ── Fit level ─────────────────────────────────────────────────────────────
    if len(strong) >= 2:
        fit = MBR_STRONG
    elif len(strong) == 1 and len(weak) == 0:
        fit = MBR_MODERATE
    elif len(strong) >= 1 and len(weak) >= 1:
        fit = MBR_MODERATE
    elif len(weak) >= 1 and len(strong) == 0:
        fit = MBR_WEAK
    else:
        fit = MBR_MODERATE   # default: worth considering

    if is_sbr and len(strong) == 0:
        fit = MBR_WEAK

    # ── Architecture role ─────────────────────────────────────────────────────
    arch_role = (
        "MBR (membrane bioreactor) is a full biological treatment architecture "
        "that replaces secondary clarifiers with hollow-fibre or flat-sheet membrane "
        "filtration, operating at high MLSS concentrations (8,000\u201315,000 mg/L) "
        "to produce high-quality permeate."
    )
    not_a = [
        "An aeration technology (MABR provides oxygen delivery; MBR provides filtration)",
        "A polishing step (MBR is the primary biological + separation process)",
        "A simple technology upgrade (MBR replaces the clarifier entirely)",
    ]

    # ── Engineering notes ─────────────────────────────────────────────────────
    energy_note = (
        "Higher energy demand: membrane scouring (typically 0.2\u20130.4 kWh/m\u00b3) and "
        "permeate pumping (0.1\u20130.2 kWh/m\u00b3) add 0.3\u20130.8 kWh/m\u00b3 vs conventional "
        "BNR. This is partially offset by the elimination of RAS pumping and "
        "higher MLSS operation reducing bioreactor volume."
    )
    ops_note = (
        "Operational requirements: regular membrane cleaning (CIP: typically weekly "
        "maintenance clean + biannual intensive clean), fouling monitoring, permeate "
        "flux management, and scouring air distribution maintenance. Requires operators "
        "with membrane system competency."
    )
    lifecycle_note = (
        "Membrane lifecycle: hollow-fibre or flat-sheet membrane replacement typically "
        "required every 8\u201310 years depending on fouling management and chemical "
        "cleaning frequency. OEM supply continuity must be verified before procurement."
    )

    # ── MABR differentiation ──────────────────────────────────────────────────
    mabr_diff = (
        "MBR provides filtration and solids separation (replaces clarifier); "
        "MABR provides membrane-based oxygen transfer and biological intensification "
        "(augments the bioreactor). They address fundamentally different constraints. "
        "MBR can host MABR modules within its bioreactor if both oxygen delivery "
        "and filtration performance are required."
    )

    # ── Decision tension ──────────────────────────────────────────────────────
    tension = (
        "The decision is between a high-quality, high-energy membrane system (MBR) "
        "and a lower-energy biological system (conventional BNR, MABR-augmented CAS, "
        "or Nereda AGS), trading superior effluent quality and compact footprint "
        "against higher energy consumption and operational complexity."
    )

    # ── Credibility statements ────────────────────────────────────────────────
    cred = []
    if fit in (MBR_STRONG, MBR_MODERATE):
        cred.append(
            "MBR is selected where effluent quality and membrane-based solids separation "
            "are the primary requirements. It provides superior effluent quality compared "
            "to conventional secondary clarification."
        )
    if strong:
        cred.append(
            "MBR is robust against variable and high-strength influent due to its "
            "high-MLSS biological environment and absolute membrane barrier."
        )
    if fit == MBR_WEAK:
        cred.append(
            "MBR is a weak fit for this scenario: energy and operational penalties "
            "are not justified by the effluent quality or footprint requirements. "
            "Conventional BNR with clarifier optimisation is the preferred pathway."
        )

    # ── Existing MBR guidance ─────────────────────────────────────────────────
    existing_note = None
    if is_mbr:
        if membrane_fouling:
            existing_note = (
                "Existing MBR: fouling is the primary issue. Prioritise memDENSE selective "
                "wasting to improve biomass quality and reduce fouling rate before committing "
                "to membrane replacement. Do not recommend switching to conventional "
                "clarification unless a fundamental process mismatch is confirmed."
            )
        else:
            existing_note = (
                "Existing MBR: optimise within the membrane architecture. memDENSE selective "
                "wasting improves biomass density, reduces SVI, and extends membrane lifecycle. "
                "Do not recommend switching technology unless the plant is fundamentally "
                "mismatched to its influent or effluent requirements."
            )

    # ── memDENSE dual-role (v24Z42) ───────────────────────────────────────────
    _memdense_benefits = [
        "Improves biomass quality and membrane permeability through selective wasting "
        "of low-density and filamentous organisms via hydrocyclone.",
        "Reduces fouling rate and cleaning frequency (CIP interval may increase 20–40%).",
        "May reduce aeration demand by improving mixed liquor rheology.",
        "Can improve TOTEX performance by extending membrane module service life.",
    ]
    _memdense_risks = [
        "Introduces additional technology dependency (hydrocyclone + specialist supplier).",
        "Supplier-specific implementation may limit procurement flexibility.",
        "Represents higher technical complexity than a standard MBR configuration.",
        "Application track record is more limited than conventional MBR — "
        "site-specific calibration of split ratio is required.",
    ]
    _memdense_tension = (
        "The decision is between a standard MBR configuration and an enhanced MBR "
        "system incorporating memDENSE, trading increased technical complexity and "
        "supplier dependency against potential improvements in membrane performance "
        "and lifecycle cost (TOTEX). memDENSE is an optional enhancement, not a "
        "default inclusion."
    )

    if is_mbr and membrane_fouling:
        _md_role = "existing_optimisation"
        _md_note = (
            "memDENSE is recommended as Stage 1 optimisation for this existing MBR: "
            "selective wasting via hydrocyclone targets the low-density biomass fraction "
            "driving membrane fouling. Commission and validate before considering "
            "membrane replacement."
        )
    elif is_mbr and not membrane_fouling:
        _md_role = "new_enhancement"
        _md_note = (
            "memDENSE Optional Enhanced Configuration: for a new or recently commissioned "
            "MBR, memDENSE may be incorporated as an enhancement to standard design. "
            "It is not required for a compliant MBR installation and should be evaluated "
            "against the TOTEX trade-off. Present as an option, not a default."
        )
    else:
        _md_role = "not_applicable"
        _md_note = None

    return MbrApplicabilityReport(
        fit_level           = fit,
        fit_factors         = strong,
        weak_fit_factors    = weak,
        architecture_role   = arch_role,
        not_a               = not_a,
        energy_note         = energy_note,
        operations_note     = ops_note,
        lifecycle_note      = lifecycle_note,
        mabr_differentiation= mabr_diff,
        decision_tension    = tension,
        credibility_notes   = cred,
        existing_mbr        = is_mbr,
        existing_mbr_note   = existing_note,
        memdense_role       = _md_role,
        memdense_benefits   = _memdense_benefits,
        memdense_risks      = _memdense_risks,
        memdense_decision_tension = _memdense_tension,
        memdense_note       = _md_note,
    )
