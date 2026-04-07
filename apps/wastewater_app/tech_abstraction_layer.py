"""
tech_abstraction_layer.py  —  WaterPoint v24Z76
Technology Abstraction, Availability and MOB Classification Layer

Purpose:
- Process-class (capability-first) language
- Technology availability and delivery risk
- Equivalent alternatives
- MOB as a distinct process class

Does NOT modify:
- physics, technology selection, confidence scoring, pathways, timing
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional

# ── Availability / Delivery risk constants ────────────────────────────────────
AVAIL_HIGH   = "High"
AVAIL_MEDIUM = "Medium"
AVAIL_LOW    = "Low"

DELRISK_LOW       = "Low"
DELRISK_MEDIUM    = "Medium"
DELRISK_HIGH      = "High"
DELRISK_MED_HIGH  = "Medium–High"


# ── MOB definition (mandatory per spec Part 3) ────────────────────────────────
MOB_DEFINITION = (
    "Engineered mobile biofilm systems designed for high-rate biological treatment, "
    "characterised by controlled biofilm structure, enhanced microbial activity, "
    "and improved treatment efficiency compared to conventional carrier-based systems."
)


# ── Dataclasses ───────────────────────────────────────────────────────────────

@dataclass
class TechProfile:
    """Technology profile for a single process class."""
    ti_code:          str          # TI_* constant
    process_class:    str          # capability-first label (e.g. "Ballasted clarification")
    mechanism:        str          # clear process mechanism description
    availability:     str          # AVAIL_* constant
    delivery_risk:    str          # DELRISK_* constant
    alternatives:     List[str]    # equivalent process classes
    vendor_examples:  str          # optional vendor note (never primary)
    is_mob:           bool = False  # True for MOB class
    mob_note:         str  = ""    # MOB definition when is_mob=True


@dataclass
class TechAbstractionResult:
    """Output from the tech abstraction layer for a given pathway."""
    profiles:               List[TechProfile]
    has_mob:                bool
    has_vendor_dependent:   List[str]   # labels with Medium/High delivery risk
    delivery_context:       str         # board summary addition (Part 9)
    consistency_flags:      List[str]   # any issues found (Part 10)


# ── Technology registry ───────────────────────────────────────────────────────
# Keyed by technology string as it appears in pathway.stages[].technology
# These match the TI_* values in stack_generator.py

_REGISTRY: Dict[str, TechProfile] = {}


def _reg(ti_code: str, process_class: str, mechanism: str,
         availability: str, delivery_risk: str, alternatives: List[str],
         vendor_examples: str = "", is_mob: bool = False) -> None:
    _REGISTRY[ti_code] = TechProfile(
        ti_code       = ti_code,
        process_class = process_class,
        mechanism     = mechanism,
        availability  = availability,
        delivery_risk = delivery_risk,
        alternatives  = alternatives,
        vendor_examples = vendor_examples,
        is_mob        = is_mob,
        mob_note      = MOB_DEFINITION if is_mob else "",
    )


# ── Hydraulic / Solids ────────────────────────────────────────────────────────
_reg("CoMag", "Ballasted clarification (high-rate solids separation)",
     "Magnetic or ballast microspheres are dosed to activated sludge, increasing "
     "settling velocity 10–20× beyond conventional clarification. Provides hydraulic "
     "protection under peak wet weather flow without additional civil tankage.",
     AVAIL_MEDIUM, DELRISK_MEDIUM,
     ["Lamella clarification with polymer",
      "High-rate conventional clarification with polymer dosing",
      "Parallel storm treatment train"],
     "e.g. CoMag, BioMag or equivalent ballasted clarification system")

_reg("inDENSE",
     "Hydrocyclone-based sludge densification",
     "Hydrocyclone separates light, slow-settling biomass fraction and returns "
     "the dense, fast-settling fraction to the bioreactor. Improves SVI and "
     "recovers clarifier SOR headroom without new tankage.",
     AVAIL_MEDIUM, DELRISK_MEDIUM,
     ["Selector reactor optimisation",
      "Biological process control for SVI reduction",
      "Additional secondary clarifier capacity"],
     "e.g. inDENSE or equivalent hydrocyclone densification system")

# ── Biological — Conventional ─────────────────────────────────────────────────
_reg("Bardenpho optimisation",
     "Multi-stage biological nutrient removal (Bardenpho-type)",
     "Sequential anoxic and aerobic zones provide conditions for biological "
     "nitrogen and phosphorus removal. Anoxic zone sizing and internal recycle "
     "ratios are optimised for the specific carbon:nitrogen ratio and load.",
     AVAIL_HIGH, DELRISK_LOW,
     ["Modified Ludzack-Ettinger (MLE)",
      "JHB process",
      "UCT process"],
     "")

_reg("Conventional BNR",
     "Conventional biological nutrient removal",
     "Conventional activated sludge with pre-anoxic and aerobic zones providing "
     "biological nitrogen and phosphorus removal. Large hydraulic volume provides "
     "resilience to load variability.",
     AVAIL_HIGH, DELRISK_LOW,
     ["Bardenpho process", "MLE process", "A2O process"], "")

# ── Biological — Attached Growth ─────────────────────────────────────────────
_reg("MBBR",
     "Moving Bed Biofilm Reactor (MBBR)",
     "Plastic carriers (media) in aerated or anoxic zones provide surface "
     "for biofilm growth. Biofilm retains biomass independent of clarifier "
     "performance, decoupling SRT from HRT.",
     AVAIL_HIGH, DELRISK_LOW,
     ["IFAS (Integrated Fixed-Film Activated Sludge)",
      "Conventional BNR with longer SRT",
      "MBBR-Bardenpho hybrid"],
     "Multiple global suppliers")

_reg("IFAS (integrated fixed-film activated sludge)",
     "Integrated Fixed-Film Activated Sludge (IFAS)",
     "Fixed or floating media added to existing activated sludge tanks. "
     "Biofilm on media supplements suspended growth, increasing nitrification "
     "capacity without additional tankage.",
     AVAIL_HIGH, DELRISK_LOW,
     ["MBBR",
      "MABR (for constrained aeration)",
      "Extended aeration SRT"],
     "Multiple global suppliers")

_reg("IFAS",
     "Integrated Fixed-Film Activated Sludge (IFAS)",
     "Fixed or floating media added to existing activated sludge tanks. "
     "Biofilm on media supplements suspended growth, increasing nitrification "
     "capacity without additional tankage.",
     AVAIL_HIGH, DELRISK_LOW,
     ["MBBR", "MABR (for constrained aeration)", "Extended aeration SRT"],
     "Multiple global suppliers")

# ── Biological — Intensification ─────────────────────────────────────────────
_reg("MABR (OxyFAS retrofit)",
     "Membrane-aerated biofilm reactor (MABR)",
     "Gas-permeable membranes deliver oxygen directly to a biofilm, bypassing "
     "bulk liquid transfer. Provides kinetic protection at high MLSS and low "
     "temperature; maintains nitrification when bulk dissolved oxygen is limiting.",
     AVAIL_MEDIUM, DELRISK_MEDIUM,
     ["IFAS",
      "Mobile Organic Biofilm (MOB)",
      "Expanded aeration with fine-bubble diffuser replacement"],
     "e.g. OxyFAS, GS3 MABR or equivalent membrane-aerated biofilm system")

_reg("MABR",
     "Membrane-aerated biofilm reactor (MABR)",
     "Gas-permeable membranes deliver oxygen directly to a biofilm, bypassing "
     "bulk liquid transfer. Provides kinetic protection at high MLSS and low "
     "temperature; maintains nitrification when bulk dissolved oxygen is limiting.",
     AVAIL_MEDIUM, DELRISK_MEDIUM,
     ["IFAS", "Mobile Organic Biofilm (MOB)", "Expanded aeration"],
     "e.g. OxyFAS, GS3 MABR or equivalent")

_reg("MABR (intensified BNR)",
     "Membrane-aerated biofilm reactor (MABR) — intensified BNR configuration",
     "MABR used as the primary aeration system in an intensified BNR design. "
     "Compact footprint with high volumetric nitrification rate.",
     AVAIL_MEDIUM, DELRISK_MEDIUM,
     ["IFAS", "Mobile Organic Biofilm (MOB)", "Conventional BNR with expanded volume"],
     "e.g. OxyFAS, GS3 MABR or equivalent")

# ── Biological — AGS ─────────────────────────────────────────────────────────
_reg("Aerobic Granular Sludge (AGS)",
     "Aerobic Granular Sludge (AGS)",
     "Sequential batch reactor process producing dense granular bioaggregates "
     "that settle rapidly. Simultaneous nitrogen and phosphorus removal in a "
     "compact footprint with no secondary clarifiers required.",
     AVAIL_MEDIUM, DELRISK_MEDIUM,
     ["IFAS or MBBR",
      "Conventional BNR (lower footprint)",
      "MBR"],
     "e.g. Nereda or equivalent AGS system")

# ── MOB — Mobile Organic Biofilm (distinct class) ─────────────────────────────
_reg("Mobile Organic Biofilm (MOB)",
     "Mobile Organic Biofilm (MOB)",
     MOB_DEFINITION + " Suited to constrained footprint and biological capacity "
     "intensification where conventional carrier-based biofilm (MBBR/IFAS) "
     "is insufficient.",
     AVAIL_MEDIUM, DELRISK_MED_HIGH,
     ["MBBR", "IFAS", "MABR"],
     "e.g. MIGRATE, Nuvoda or equivalent engineered biofilm system",
     is_mob=True)

_reg("MOB (miGRATE + inDENSE) — SBR intensification",
     "Mobile Organic Biofilm (MOB) with sludge densification",
     MOB_DEFINITION + " Combined with hydrocyclone sludge densification for "
     "simultaneous biological intensification and settling improvement.",
     AVAIL_MEDIUM, DELRISK_MED_HIGH,
     ["MBBR + inDENSE", "IFAS + densification", "MABR"],
     "e.g. miGRATE + inDENSE or equivalent engineered biofilm + densification system",
     is_mob=True)

# ── Tertiary — N and P ────────────────────────────────────────────────────────
_reg("Denitrification Filter",
     "Denitrification filter (tertiary nitrogen polishing)",
     "Fixed-bed or floating-bed filter dosed with external carbon (typically methanol). "
     "Removes residual nitrate independent of influent carbon availability. "
     "Required when eff COD:TN < 4.5.",
     AVAIL_HIGH, DELRISK_LOW,
     ["PdNA (lower carbon demand at TN ≤ 3 mg/L)",
      "Biological carbon addition to mainstream",
      "Increased internal recycle"],
     "Multiple global suppliers — standard tertiary technology")

_reg("PdNA (Partial Denitrification-Anammox)",
     "Partial Denitrification-Anammox (PdNA)",
     "Two-stage process converting partial denitrification products to Anammox "
     "substrate. Removes nitrogen with minimal external carbon, suited to "
     "low COD:TN and consent targets ≤ 3 mg/L.",
     AVAIL_MEDIUM, DELRISK_MEDIUM,
     ["Denitrification Filter (DNF) — higher carbon demand",
      "Full Anammox",
      "DEMON process"],
     "Multiple suppliers including AnoxKaldnes, Veolia, and equivalents")

_reg("Tertiary P removal",
     "Tertiary phosphorus removal (chemical dosing and filtration)",
     "Chemical precipitation using metal salts (alum, ferric) followed by "
     "filtration or clarification. Required for TP ≤ 0.5 mg/L targets. "
     "Enhanced coagulation for TP ≤ 0.1 mg/L.",
     AVAIL_HIGH, DELRISK_LOW,
     ["Enhanced biological phosphorus removal (EBPR)",
      "Struvite crystallisation (if phosphorus recovery required)",
      "Membrane filtration for very low TP targets"],
     "Commodity chemicals — no vendor dependency")

# ── MBR ──────────────────────────────────────────────────────────────────────
_reg("MBR",
     "Membrane Bioreactor (MBR)",
     "Ultrafiltration membranes replace secondary clarifiers, producing "
     "consistently high-quality effluent suitable for reuse. "
     "High footprint efficiency.",
     AVAIL_HIGH, DELRISK_MEDIUM,
     ["Conventional BNR + tertiary filtration",
      "AGS",
      "Conventional BNR + UV"],
     "Multiple global suppliers — Toray, Kubota, Suez, Veolia and equivalents")

# ── Full process conversion ───────────────────────────────────────────────────
_reg("Full process conversion (MBR or AGS replacement)",
     "Full process renewal (MBR, AGS, or equivalent)",
     "Complete replacement of biological process train with a new high-rate "
     "or high-quality technology. Provides step-change in capacity, compliance, "
     "and footprint efficiency.",
     AVAIL_MEDIUM, DELRISK_MEDIUM,
     ["MBR", "Aerobic Granular Sludge (AGS)", "Conventional BNR on new site"],
     "")

_reg("PdNA or Anammox",
     "Partial Denitrification-Anammox / Anammox (tertiary nitrogen closure)",
     "Low-carbon tertiary nitrogen removal pathway suited to TN ≤ 3 mg/L. "
     "PdNA uses partial denitrification; full Anammox uses NH4 and NO2 directly.",
     AVAIL_MEDIUM, DELRISK_MEDIUM,
     ["Denitrification Filter (higher carbon demand)",
      "DEMON process",
      "SHARON-Anammox"],
     "Multiple suppliers")

_reg("Advanced P removal",
     "Advanced phosphorus removal (TP ≤ 0.1 mg/L)",
     "Enhanced chemical dosing with membrane filtration or cloth media "
     "filtration to achieve very low TP targets for coastal consent "
     "or reuse standard.",
     AVAIL_HIGH, DELRISK_LOW,
     ["Struvite crystallisation",
      "Enhanced coagulation + lamella clarification",
      "Biofilter P polishing"],
     "")

_reg("Tertiary filtration + UV (if reuse required)",
     "Tertiary filtration and UV disinfection (reuse standard)",
     "Dual-media or membrane filtration followed by UV irradiation. "
     "Achieves Class A recycled water standard for non-potable reuse.",
     AVAIL_HIGH, DELRISK_LOW,
     ["MF/UF membrane filtration",
      "Ozone + BAC (for advanced reuse)",
      "Reverse osmosis (for indirect potable reuse)"],
     "")

_reg("Sidestream PN/A evaluation (Stage 1 priority — THP NH\u2084 surge \u226550%)",
     "Sidestream partial nitritation-Anammox (PN/A)",
     "Sidestream treatment of dewatering centrate to remove NH4 before "
     "it recycles to the mainstream. Reduces mainstream nitrification "
     "load by 15–25% when THP is present.",
     AVAIL_MEDIUM, DELRISK_MEDIUM,
     ["Mainstream nitrification capacity upgrade",
      "Sidestream stripping and absorption",
      "SBR-based DEMON process"],
     "e.g. SHARON, ANAMMOX DEMON or equivalent sidestream treatment")

_reg("CoMag (peak flow ballasted clarification)",
     "Ballasted clarification (peak flow hydraulic protection)",
     "Same mechanism as primary CoMag entry — enhanced capacity position "
     "for Stage 2 upgrade beyond existing CAS relief.",
     AVAIL_MEDIUM, DELRISK_MEDIUM,
     ["Lamella clarification", "High-rate clarifier retrofit", "Parallel CAS capacity"],
     "e.g. CoMag, BioMag or equivalent")

_reg("CoMag (enhanced hydraulic capacity beyond existing CAS)",
     "Ballasted clarification (enhanced hydraulic capacity)",
     "Same mechanism as primary entry — installed to augment or replace "
     "existing CAS hydraulic relief at higher design PWWF.",
     AVAIL_MEDIUM, DELRISK_MEDIUM,
     ["Lamella clarification", "Additional secondary clarifier", "Parallel CAS train"],
     "e.g. CoMag, BioMag or equivalent")

_reg("Sludge minimisation / enhanced digestion (biosolids pathway)",
     "Biosolids minimisation and enhanced digestion",
     "Thermal hydrolysis or advanced anaerobic digestion to reduce sludge "
     "volume and improve dewatering. Reduces disposal cost and land requirement.",
     AVAIL_MEDIUM, DELRISK_MEDIUM,
     ["Conventional anaerobic digestion",
      "Aerobic digestion",
      "Lime stabilisation"],
     "")

_reg("PdNA integration",
     "Partial Denitrification-Anammox integration",
     "Staged integration of PdNA into existing BNR process. "
     "First step toward eliminating external carbon dependency.",
     AVAIL_MEDIUM, DELRISK_MEDIUM,
     ["DNF (methanol-dosed)",
      "Full Anammox",
      "Enhanced biological carbon utilisation"],
     "")

_reg("Enhanced carbon dosing (if required)",
     "External carbon dosing (supplemental)",
     "Methanol or acetate addition to support denitrification when "
     "influent biodegradable carbon is insufficient. Interim measure "
     "pending tertiary nitrogen closure.",
     AVAIL_HIGH, DELRISK_LOW,
     ["Internal carbon sources (fermented primary sludge)",
      "Glycerol addition",
      "Molasses or equivalent"],
     "Commodity carbon source — no vendor dependency")

_reg("Full PdNA or Anammox",
     "Full Partial Denitrification-Anammox or Anammox (Stage 3 tertiary)",
     "Full tertiary nitrogen closure at TN ≤ 3 mg/L. "
     "No external carbon dependency at design throughput.",
     AVAIL_MEDIUM, DELRISK_MEDIUM,
     ["Denitrification Filter (DNF)",
      "DEMON process",
      "SHARON-Anammox"],
     "")

_reg("MABR (aeration intensification)",
     "Membrane-aerated biofilm reactor (MABR) — aeration intensification",
     "MABR retrofitted into existing tanks to increase nitrification "
     "capacity without additional aeration blowers.",
     AVAIL_MEDIUM, DELRISK_MEDIUM,
     ["IFAS", "Fine-bubble diffuser replacement", "Blower capacity expansion"],
     "e.g. OxyFAS, GS3 MABR or equivalent")

_reg("Bardenpho process optimisation",
     "Multi-stage biological nutrient removal (Bardenpho-type)",
     "Sequential anoxic/aerobic zone optimisation for improved BNR performance.",
     AVAIL_HIGH, DELRISK_LOW,
     ["MLE", "UCT", "JHB process"], "")

_reg("Tertiary phosphorus removal",
     "Tertiary phosphorus removal (chemical dosing and filtration)",
     "Chemical P removal as standalone tertiary stage.",
     AVAIL_HIGH, DELRISK_LOW,
     ["Enhanced biological P removal", "Struvite crystallisation"], "")


# ── Fallback for unknown technologies ─────────────────────────────────────────
def _unknown_profile(tech_label: str) -> TechProfile:
    return TechProfile(
        ti_code       = tech_label,
        process_class = tech_label,
        mechanism     = "Process mechanism not yet registered in WaterPoint technology library.",
        availability  = AVAIL_MEDIUM,
        delivery_risk = DELRISK_MEDIUM,
        alternatives  = [],
        vendor_examples = "",
    )


def get_profile(tech_label: str) -> TechProfile:
    """Lookup a technology profile by its display label or TI code."""
    # Direct match
    if tech_label in _REGISTRY:
        return _REGISTRY[tech_label]
    # Partial match — try prefix
    for key, prof in _REGISTRY.items():
        if key and tech_label.lower().startswith(key.lower()[:12]):
            return prof
        if tech_label.lower() in key.lower():
            return prof
    return _unknown_profile(tech_label)


# ── Main entry point ──────────────────────────────────────────────────────────

def build_tech_abstraction(pathway, ctx: Dict) -> TechAbstractionResult:
    """
    Build technology abstraction output for a pathway.

    Parameters
    ----------
    pathway : UpgradePathway
    ctx : Dict — engine context
    """
    stages = getattr(pathway, "stages", []) or []
    profiles: List[TechProfile] = []
    consistency_flags: List[str] = []

    for stage in stages:
        tech = getattr(stage, "technology", "") or ""
        disp = getattr(stage, "tech_display", tech) or tech
        # Try TI code (technology field) first — most reliable key
        # Fall back to display label if TI code not in registry
        if tech in _REGISTRY:
            prof = _REGISTRY[tech]
        else:
            prof = get_profile(disp)
            if not prof.alternatives:  # fallback produced empty profile
                prof = get_profile(tech)
        profiles.append(prof)

    # Check for MOB
    has_mob = any(p.is_mob for p in profiles)

    # Vendor-dependent techs (Medium or higher delivery risk)
    vendor_dep = [p.process_class for p in profiles
                  if p.delivery_risk in (DELRISK_MEDIUM, DELRISK_HIGH, DELRISK_MED_HIGH)]

    # Part 10: Consistency check
    for p in profiles:
        # MOB must never be equated to MBBR
        if p.is_mob and any("MBBR" in alt and "equivalent" not in alt.lower()
                             for alt in p.alternatives):
            consistency_flags.append(
                f"MOB ({p.process_class}) listed with MBBR as direct equivalent — "
                "these are distinct process classes."
            )

    # Part 9: Delivery context board addition
    n_vendor = len(vendor_dep)
    if n_vendor == 0:
        delivery_ctx = (
            "All recommended technologies have high global availability and "
            "low supply chain risk. Standard procurement applies."
        )
    elif n_vendor <= 2:
        delivery_ctx = (
            f"The recommended stack includes {n_vendor} technology class(es) with "
            "moderate availability and supplier dependency. Alternative implementations "
            "should be evaluated based on regional availability and procurement timeline: "
            + ", ".join(vendor_dep[:2]) + "."
        )
    else:
        delivery_ctx = (
            f"The recommended stack includes {n_vendor} technology classes with "
            "moderate to high supplier dependency. Regional procurement assessment "
            "is required for: " + ", ".join(vendor_dep[:3]) + " and equivalents. "
            "Conventional alternatives are available for each where delivery risk "
            "is unacceptable."
        )
    if has_mob:
        delivery_ctx += (
            " Note: Mobile Organic Biofilm (MOB) systems are vendor-dependent "
            "(Medium–High delivery risk). Confirm regional availability before "
            "committing to this process class."
        )

    return TechAbstractionResult(
        profiles             = profiles,
        has_mob              = has_mob,
        has_vendor_dependent = vendor_dep,
        delivery_context     = delivery_ctx,
        consistency_flags    = consistency_flags,
    )
