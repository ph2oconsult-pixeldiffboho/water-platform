"""
apps/wastewater_app/intensification_intelligence.py

Brownfield Intensification Intelligence Layer
==============================================

Transforms WaterPoint from a technology comparison tool into a
constraint-driven intensification engine.

Pipeline:
  1. Classify dominant constraint type
  2. Map constraint → intensification mechanism
  3. Map mechanism → ranked technologies (with stacking logic)
  4. Generate constraint-matched decision narrative
  5. Return IntensificationPlan for UI rendering

Design rules
------------
- Pure functions — no Streamlit, no I/O, no side effects.
- Reads ConstraintProfile (from brownfield_upgrade_ranking) + WaterPoint signals.
- Does NOT modify existing technology engines.
- Stacks multiple technologies when multiple constraints are active.
- Hydraulic limitation always redirects to storage/EQ, not process intensification alone.

Key engineering truths embedded
--------------------------------
- memDENSE: selective wasting removes filaments and light biomass; improves
  permeability, reduces fouling/aeration, enhances PAO retention.
- Hybas / IFAS: decouples SRT from HRT; increases nitrification capacity without
  volume increase; reduces MLSS and clarifier loading.
- MBBR-Bardenpho: biofilm ~80% nitrification; enables simultaneous nitrification-
  denitrification; optimal R ≈ 2; optimal anaerobic HRT ≈ 2–2.5h.
- inDENSE: biomass selection by density; reduces settling time; enables shorter
  cycles; prerequisite for miGRATE in SBR intensification.
- Extreme wet weather always requires balancing/storage regardless of intensification.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


# ── Constraint type constants ──────────────────────────────────────────────────
CT_SETTLING          = "settling_limitation"
CT_NITRIFICATION     = "nitrification_limitation"
CT_BIOLOGICAL        = "biological_performance_limitation"
CT_MEMBRANE          = "membrane_performance_limitation"
CT_HYDRAULIC         = "hydraulic_limitation"
CT_MULTI             = "multi_constraint"
CT_UNKNOWN           = "unknown"

# ── Mechanism constants ────────────────────────────────────────────────────────
MECH_BIOMASS_SEL     = "biomass_selection"
MECH_BIOFILM_RET     = "biofilm_retention"
MECH_PROC_OPT        = "process_optimisation"
MECH_MEMBRANE_SEL    = "membrane_biomass_selection"
MECH_HYD_EXP         = "hydraulic_expansion"
MECH_MULTI           = "multi_mechanism"

# ── Technology option codes ────────────────────────────────────────────────────
TI_INDENSE      = "inDENSE"
TI_MEMDENSE     = "memDENSE"
TI_HYBAS        = "Hybas (IFAS)"
TI_MBBR         = "MBBR"
TI_IFAS         = "IFAS"
TI_BARDENPHO    = "Bardenpho optimisation"
TI_RECYCLE_OPT  = "Recycle ratio optimisation"
TI_ZONE_RECONF  = "Zone reconfiguration / EBPR"
TI_EQ_BASIN     = "Equalisation basin"
TI_STORM_STORE  = "Storm storage / attenuation"
TI_PARALLEL     = "Parallel treatment train"
TI_MIGINDENSE   = "MOB (miGRATE + inDENSE)"


# ── Result dataclasses ─────────────────────────────────────────────────────────

@dataclass
class TechnologyOption:
    """A single ranked intensification technology."""
    code:           str
    name:           str            # display name
    rank:           int
    mechanism:      str            # which mechanism it serves
    primary_action: str            # one-line what it does
    key_truth:      str            # embedded engineering fact
    capex_class:    str            # Low / Medium / High
    complexity:     str            # Low / Medium / High
    can_stack_with: List[str] = field(default_factory=list)  # codes it combines well with
    notes:          str = ""


@dataclass
class IntensificationStack:
    """A multi-technology combination for multi-constraint plants."""
    label:          str            # e.g. "inDENSE + Hybas"
    technologies:   List[str]      # ordered list of codes
    rationale:      str
    constraint_resolved: List[str]
    residual:       str


@dataclass
class IntensificationPlan:
    """Full output of the intensification intelligence layer."""
    # Input summary
    constraint_type:    str            # CT_* constant
    constraint_label:   str            # human-readable
    mechanism:          str            # MECH_* constant
    mechanism_label:    str            # human-readable

    # Ranked technology options
    technologies:       List[TechnologyOption]
    preferred:          Optional[TechnologyOption]
    alternative:        Optional[TechnologyOption]

    # Stacking
    stack:              Optional[IntensificationStack]

    # Narrative
    constraint_rationale:  str    # why this constraint was identified
    mechanism_rationale:   str    # why this mechanism is recommended
    decision_narrative:    str    # full engineering explanation
    hydraulic_caveat:      str    # always present for wet weather / hydraulic cases

    # Flags
    hydraulic_expansion_required: bool = False
    multi_constraint:             bool = False


# ── Mechanism labels ───────────────────────────────────────────────────────────
_MECH_LABELS = {
    MECH_BIOMASS_SEL:  "Biomass selection",
    MECH_BIOFILM_RET:  "Biofilm retention",
    MECH_PROC_OPT:     "Process optimisation",
    MECH_MEMBRANE_SEL: "Membrane biomass selection",
    MECH_HYD_EXP:      "Hydraulic expansion / attenuation",
    MECH_MULTI:        "Multi-mechanism intensification",
}

_CT_LABELS = {
    CT_SETTLING:      "Settling / solids separation limitation",
    CT_NITRIFICATION: "Nitrification / SRT limitation",
    CT_BIOLOGICAL:    "Biological performance limitation (TN / TP / EBPR)",
    CT_MEMBRANE:      "Membrane performance limitation",
    CT_HYDRAULIC:     "Hydraulic / throughput limitation",
    CT_MULTI:         "Multi-constraint",
    CT_UNKNOWN:       "Unknown",
}


# ── Technology library ─────────────────────────────────────────────────────────
# Full engineering facts embedded as first-class attributes.

def _tech_library() -> Dict[str, TechnologyOption]:
    return {

        TI_INDENSE: TechnologyOption(
            code=TI_INDENSE, name="inDENSE® (gravimetric biomass selection)",
            rank=0, mechanism=MECH_BIOMASS_SEL,
            primary_action=(
                "Selectively wastes light and filamentous biomass by density, "
                "retaining the densest and most active fraction."
            ),
            key_truth=(
                "inDENSE improves settling velocity, reduces sludge volume index, "
                "and enables shorter or more productive cycle operation. "
                "It is the prerequisite for miGRATE in SBR intensification and a "
                "standalone settling remedy in CAS/BNR plants."
            ),
            capex_class="Low", complexity="Low",
            can_stack_with=[TI_MIGINDENSE, TI_HYBAS, TI_MBBR],
        ),

        TI_MEMDENSE: TechnologyOption(
            code=TI_MEMDENSE, name="memDENSE® (MBR biomass selection)",
            rank=0, mechanism=MECH_MEMBRANE_SEL,
            primary_action=(
                "Selective wasting in MBR systems removes filaments and light biomass, "
                "improving membrane permeability, reducing fouling, and enhancing PAO retention."
            ),
            key_truth=(
                "memDENSE removes filamentous organisms and low-density biomass from MBR mixed liquor. "
                "This directly improves membrane permeability and reduces cleaning frequency. "
                "It also enhances PAO retention, improving biological phosphorus removal. "
                "Aeration demand for membrane scouring can be reduced after installation."
            ),
            capex_class="Low", complexity="Low",
            can_stack_with=[TI_ZONE_RECONF],
        ),

        TI_HYBAS: TechnologyOption(
            code=TI_HYBAS, name="Hybas™ (IFAS / integrated biofilm)",
            rank=0, mechanism=MECH_BIOFILM_RET,
            primary_action=(
                "Adds suspended carrier media to existing aeration tanks, "
                "decoupling sludge age from hydraulic retention time."
            ),
            key_truth=(
                "Hybas decouples SRT from HRT, allowing longer effective sludge age "
                "for nitrification without increasing tank volume. "
                "MLSS in the bulk liquid decreases (less clarifier loading). "
                "The biofilm carriers retain slow-growing nitrifiers independently "
                "of the suspended growth WAS rate."
            ),
            capex_class="Medium", complexity="Medium",
            can_stack_with=[TI_BARDENPHO, TI_INDENSE, TI_ZONE_RECONF],
        ),

        TI_MBBR: TechnologyOption(
            code=TI_MBBR, name="MBBR / MBBR-Bardenpho",
            rank=0, mechanism=MECH_BIOFILM_RET,
            primary_action=(
                "Fixed biofilm on moving carriers provides robust nitrification and denitrification "
                "capacity with high volumetric loading rates."
            ),
            key_truth=(
                "MBBR biofilm contributes approximately 80% of nitrification in hybrid configurations. "
                "Enables simultaneous nitrification-denitrification within the biofilm. "
                "Optimal recycle ratio R ≈ 2. "
                "Anaerobic HRT of 2–2.5 hours is optimal for EBPR in Bardenpho configuration. "
                "Reduces suspended MLSS, lowering clarifier loading."
            ),
            capex_class="Medium", complexity="Medium",
            can_stack_with=[TI_BARDENPHO, TI_ZONE_RECONF, TI_INDENSE],
        ),

        TI_IFAS: TechnologyOption(
            code=TI_IFAS, name="IFAS (integrated fixed-film activated sludge)",
            rank=0, mechanism=MECH_BIOFILM_RET,
            primary_action=(
                "Carrier media retains nitrifying biofilm in existing aeration zones, "
                "increasing biological treatment capacity without new tanks."
            ),
            key_truth=(
                "IFAS decouples nitrification SRT from the hydraulic SRT of the tank. "
                "Nitrification capacity increases without additional reactor volume. "
                "Clarifier loading may be reduced if suspended MLSS decreases. "
                "Media screens are required at tank outlets to retain carriers."
            ),
            capex_class="Low", complexity="Low",
            can_stack_with=[TI_BARDENPHO, TI_INDENSE, TI_ZONE_RECONF],
        ),

        TI_BARDENPHO: TechnologyOption(
            code=TI_BARDENPHO, name="Bardenpho / process zone optimisation",
            rank=0, mechanism=MECH_PROC_OPT,
            primary_action=(
                "Optimise zone configuration, recycle ratios, and anaerobic HRT "
                "to improve TN and TP removal without new volume."
            ),
            key_truth=(
                "Anaerobic zone HRT of 2–2.5 hours is optimal for EBPR PAO selection. "
                "Internal recycle ratio R ≈ 2 gives near-optimal TN removal for most plants. "
                "Second anoxic zone (Bardenpho 5-stage) significantly reduces effluent TN. "
                "Zone reconfiguration can often be achieved within existing tank volume."
            ),
            capex_class="Low", complexity="Low",
            can_stack_with=[TI_HYBAS, TI_MBBR, TI_IFAS, TI_RECYCLE_OPT],
        ),

        TI_RECYCLE_OPT: TechnologyOption(
            code=TI_RECYCLE_OPT, name="Recycle ratio optimisation",
            rank=0, mechanism=MECH_PROC_OPT,
            primary_action=(
                "Optimise internal recycle (MLR) and return activated sludge (RAS) "
                "ratios to maximise denitrification and P removal without capital spend."
            ),
            key_truth=(
                "MLR ratio directly controls denitrification efficiency. "
                "At R=2 approximately 67% of nitrate is recycled; at R=4 approximately 80%. "
                "Diminishing returns occur above R=4 due to dissolved oxygen carry-over. "
                "RAS optimisation protects clarifier SOR and sludge blanket depth."
            ),
            capex_class="Low", complexity="Low",
            can_stack_with=[TI_BARDENPHO, TI_ZONE_RECONF],
        ),

        TI_ZONE_RECONF: TechnologyOption(
            code=TI_ZONE_RECONF, name="Zone reconfiguration / EBPR optimisation",
            rank=0, mechanism=MECH_PROC_OPT,
            primary_action=(
                "Reconfigure existing tank zones (anaerobic, anoxic, aerobic) "
                "to improve EBPR selection and denitrification."
            ),
            key_truth=(
                "EBPR requires a true anaerobic zone (no nitrate, no oxygen) with VFA availability. "
                "Anaerobic volume of 10–15% of total bioreactor volume is typically required. "
                "Nitrate return to the anaerobic zone inhibits PAO selection and must be minimised. "
                "Carbon partitioning optimisation (primary clarifier bypass) can improve EBPR."
            ),
            capex_class="Low", complexity="Medium",
            can_stack_with=[TI_BARDENPHO, TI_HYBAS, TI_MEMDENSE],
        ),

        TI_EQ_BASIN: TechnologyOption(
            code=TI_EQ_BASIN, name="Equalisation / flow balancing basin",
            rank=0, mechanism=MECH_HYD_EXP,
            primary_action=(
                "Attenuates peak wet weather inflows before secondary treatment, "
                "protecting biological process stability."
            ),
            key_truth=(
                "EQ basins reduce peak-to-average flow ratio entering secondary treatment. "
                "Target attenuation to ≤ 2× DWA at inlet to secondaries. "
                "No process intensification can substitute for hydraulic attenuation "
                "under extreme peak wet weather flows."
            ),
            capex_class="High", complexity="Medium",
            can_stack_with=[TI_STORM_STORE],
        ),

        TI_STORM_STORE: TechnologyOption(
            code=TI_STORM_STORE, name="Storm storage / attenuation infrastructure",
            rank=0, mechanism=MECH_HYD_EXP,
            primary_action=(
                "Provides upstream storage to capture peak inflow and release "
                "at controlled rates to protect plant hydraulics."
            ),
            key_truth=(
                "Extreme peak wet weather events (> 3× DWA) cannot be managed by "
                "process intensification alone. Balancing, storage, or sewer attenuation "
                "is required regardless of biological upgrade pathway. "
                "Process intensification and hydraulic attenuation are complementary, not alternatives."
            ),
            capex_class="High", complexity="Medium",
            can_stack_with=[TI_EQ_BASIN, TI_PARALLEL],
        ),

        TI_PARALLEL: TechnologyOption(
            code=TI_PARALLEL, name="Parallel treatment train",
            rank=0, mechanism=MECH_HYD_EXP,
            primary_action=(
                "Additional treatment train provides hydraulic capacity relief "
                "alongside the intensified primary train."
            ),
            key_truth=(
                "Parallel trains provide hydraulic relief when process intensification "
                "has been exhausted. Should only be considered after EQ basin and "
                "process intensification options are fully evaluated."
            ),
            capex_class="High", complexity="High",
            can_stack_with=[TI_EQ_BASIN],
        ),

        TI_MIGINDENSE: TechnologyOption(
            code=TI_MIGINDENSE, name="MOB (miGRATE™ + inDENSE®) — SBR intensification",
            rank=0, mechanism=MECH_BIOMASS_SEL,
            primary_action=(
                "Sequential SBR intensification: inDENSE stabilises settling and "
                "enables cycle compression; miGRATE then improves TN, reduces aerobic "
                "mass fraction, and lowers solids inventory."
            ),
            key_truth=(
                "The correct upgrade sequence is inDENSE first (settling prerequisite), "
                "then miGRATE (biological optimisation layer). "
                "miGRATE alone does not consistently improve SVI (Lang Lang + Army Bay finding). "
                "Full MOB can unlock the practical hydraulic capacity already in the plant "
                "without adding reactor volume."
            ),
            capex_class="Medium", complexity="Medium",
            can_stack_with=[TI_BARDENPHO, TI_EQ_BASIN],
        ),
    }


# ── Constraint classification ──────────────────────────────────────────────────

def classify_constraint(
    profile,                  # ConstraintProfile from brownfield_upgrade_ranking
    wf: Optional[Dict] = None,
) -> tuple:
    """
    Classify the dominant constraint type and derive the intensification mechanism.

    Returns (constraint_type, mechanism, active_count)
    """
    wf = wf or {}

    # Count active constraint categories
    active: List[str] = []

    # Settling / solids
    settling = (
        profile.clarifier_flag or profile.solids_flag
        or bool(wf.get("high_mlss", False))
        or bool(wf.get("solids_carryover", False))
        or "settling" in profile.primary_constraint.lower()
        or "clarifier" in profile.primary_constraint.lower()
    )
    if settling:
        active.append(CT_SETTLING)

    # Nitrification — use flag-based triggers only to avoid false positives
    # from primary_constraint label text (e.g. "Aeration" label can appear even
    # when aer_flag is False due to severity ordering)
    nitrification = (
        profile.nitrification_flag
        or profile.aeration_flag                         # flag above threshold
        or bool(wf.get("nh4_near_limit", False))
        or bool(wf.get("srt_pressure", False))
    )
    if nitrification:
        active.append(CT_NITRIFICATION)

    # Biological performance (TN / TP / EBPR)
    biological = (
        profile.carbon_limit_flag
        or profile.denitrification_flag
        or bool(wf.get("tn_at_limit", False))
        or bool(wf.get("tp_at_limit", False))
        or bool(wf.get("ebpr_poor", False))
        or "biological" in profile.primary_constraint.lower()
        or "carbon" in profile.primary_constraint.lower()
    )
    if biological:
        active.append(CT_BIOLOGICAL)

    # Membrane performance
    membrane = (
        bool(wf.get("membrane_fouling", False))
        or bool(wf.get("high_cleaning_frequency", False))
        or bool(wf.get("low_permeability", False))
        or "membrane" in profile.primary_constraint.lower()
    )
    if membrane:
        active.append(CT_MEMBRANE)

    # Hydraulic
    hydraulic = (
        profile.hydraulic_flag
        or bool(wf.get("flow_ratio_above_1p5", False))
        or bool(wf.get("overflow_risk", False))
        or "hydraulic" in profile.primary_constraint.lower()
    )
    if hydraulic:
        active.append(CT_HYDRAULIC)

    # Classify
    if len(active) >= 3:
        ct = CT_MULTI
    elif len(active) == 2:
        # If hydraulic is one of two, still flag it
        # If membrane is one of two (MBR system), prioritise membrane constraint
        if CT_MEMBRANE in active and len(active) == 2:
            ct = CT_MEMBRANE   # membrane is specific enough to be the primary type
        else:
            ct = CT_MULTI
    elif len(active) == 1:
        ct = active[0]
    else:
        ct = CT_UNKNOWN

    # Derive mechanism
    if ct == CT_MULTI:
        mech = MECH_MULTI
    elif ct == CT_SETTLING:
        mech = MECH_BIOMASS_SEL
    elif ct == CT_NITRIFICATION:
        mech = MECH_BIOFILM_RET
    elif ct == CT_BIOLOGICAL:
        mech = MECH_PROC_OPT
    elif ct == CT_MEMBRANE:
        mech = MECH_MEMBRANE_SEL
    elif ct == CT_HYDRAULIC:
        mech = MECH_HYD_EXP
    else:
        mech = MECH_PROC_OPT   # fallback

    return ct, mech, active


# ── Technology ranking by constraint type ──────────────────────────────────────

def _rank_technologies(
    ct: str,
    active_constraints: List[str],
    lib: Dict[str, TechnologyOption],
    wf: Dict,
    profile,
) -> List[TechnologyOption]:
    """Return ranked list of TechnologyOptions for the identified constraint."""

    # Is this an MBR system?
    is_mbr = bool(wf.get("is_mbr", False))
    # Is this an SBR system?
    is_sbr = bool(wf.get("is_sbr", False))

    if ct == CT_SETTLING:
        if is_sbr:
            ranking = [TI_MIGINDENSE, TI_INDENSE, TI_HYBAS, TI_MBBR]
        elif is_mbr:
            ranking = [TI_MEMDENSE, TI_INDENSE]
        else:
            ranking = [TI_INDENSE, TI_HYBAS, TI_MBBR, TI_MIGINDENSE]

    elif ct == CT_NITRIFICATION:
        ranking = [TI_HYBAS, TI_IFAS, TI_MBBR, TI_RECYCLE_OPT]

    elif ct == CT_BIOLOGICAL:
        if is_mbr:
            ranking = [TI_MEMDENSE, TI_ZONE_RECONF, TI_RECYCLE_OPT, TI_BARDENPHO]
        else:
            ranking = [TI_BARDENPHO, TI_RECYCLE_OPT, TI_ZONE_RECONF, TI_HYBAS]

    elif ct == CT_MEMBRANE:
        ranking = [TI_MEMDENSE, TI_ZONE_RECONF]

    elif ct == CT_HYDRAULIC:
        ranking = [TI_EQ_BASIN, TI_STORM_STORE, TI_PARALLEL]

    elif ct == CT_MULTI:
        # Build multi-constraint ranking by combining top options for each active constraint
        ranking = []
        priority_map = {
            CT_SETTLING:      [TI_INDENSE, TI_MIGINDENSE] if is_sbr else [TI_INDENSE, TI_HYBAS],
            CT_NITRIFICATION: [TI_HYBAS, TI_IFAS],
            CT_BIOLOGICAL:    [TI_BARDENPHO, TI_RECYCLE_OPT],
            CT_MEMBRANE:      [TI_MEMDENSE],
            CT_HYDRAULIC:     [TI_EQ_BASIN],
        }
        seen = set()
        for sub in active_constraints:
            for code in priority_map.get(sub, []):
                if code not in seen:
                    ranking.append(code)
                    seen.add(code)
        # Fill with remaining options
        for code in [TI_HYBAS, TI_BARDENPHO, TI_IFAS, TI_MBBR, TI_INDENSE,
                     TI_RECYCLE_OPT, TI_ZONE_RECONF, TI_EQ_BASIN]:
            if code not in seen:
                ranking.append(code)
                seen.add(code)
    else:
        ranking = [TI_BARDENPHO, TI_RECYCLE_OPT, TI_HYBAS]

    # Build ordered list with ranks
    result = []
    for rank, code in enumerate(ranking, 1):
        if code in lib:
            opt = lib[code]
            opt.rank = rank
            result.append(opt)
    return result


# ── Stacking logic ─────────────────────────────────────────────────────────────

def _build_stack(
    ct: str,
    active: List[str],
    technologies: List[TechnologyOption],
    wf: Dict,
) -> Optional[IntensificationStack]:
    """Build a multi-technology stack recommendation when multiple constraints are active."""
    if len(active) < 2:
        return None

    is_sbr = bool(wf.get("is_sbr", False))
    is_mbr = bool(wf.get("is_mbr", False))

    # Define named stack combinations
    if CT_SETTLING in active and CT_NITRIFICATION in active:
        if is_sbr:
            return IntensificationStack(
                label="MOB (inDENSE → miGRATE) + cycle optimisation",
                technologies=[TI_INDENSE, TI_MIGINDENSE, TI_RECYCLE_OPT],
                rationale=(
                    "Settling is the gateway constraint: install inDENSE first to stabilise "
                    "solids retention and enable cycle compression. "
                    "Add miGRATE (biological optimisation) to reduce TN, lower aerobic mass "
                    "fraction, and improve nitrification resilience. "
                    "The practical upgrade sequence is inDENSE first, then miGRATE, "
                    "then cycle intensification."
                ),
                constraint_resolved=["Settling", "Nitrification / SRT", "Cycle throughput"],
                residual=(
                    "Extreme peak wet weather still requires balancing or storage attenuation. "
                    "MOB does not substitute for hydraulic infrastructure."
                ),
            )
        else:
            return IntensificationStack(
                label="inDENSE + Hybas (IFAS)",
                technologies=[TI_INDENSE, TI_HYBAS],
                rationale=(
                    "Settling is the immediate constraint: inDENSE reduces SVI and clarifier "
                    "loading without new volume. "
                    "Once settling is stabilised, Hybas decouples nitrification SRT from HRT, "
                    "providing additional nitrification capacity within existing tanks. "
                    "These two mechanisms address different constraints and stack effectively."
                ),
                constraint_resolved=["Settling / solids retention", "Nitrification / SRT"],
                residual=(
                    "Clarifier loading should be re-assessed after inDENSE commissioning. "
                    "Verify media retention screen sizing for Hybas carriers."
                ),
            )

    if CT_NITRIFICATION in active and CT_BIOLOGICAL in active:
        return IntensificationStack(
            label="Hybas + Bardenpho optimisation",
            technologies=[TI_HYBAS, TI_BARDENPHO, TI_RECYCLE_OPT],
            rationale=(
                "Nitrification is constrained by SRT limitation: Hybas provides decoupled "
                "biofilm retention independent of WAS rate. "
                "TN/TP performance is limited by process configuration: Bardenpho zone "
                "optimisation and recycle ratio tuning improve denitrification and EBPR "
                "without adding volume. "
                "Optimal anaerobic HRT ≈ 2–2.5h; internal recycle R ≈ 2."
            ),
            constraint_resolved=["Nitrification / SRT", "TN limitation", "TP / EBPR"],
            residual=(
                "Carbon availability for denitrification should be assessed. "
                "External carbon may be needed if COD/N ratio < 4."
            ),
        )

    if CT_MEMBRANE in active and CT_BIOLOGICAL in active and is_mbr:
        return IntensificationStack(
            label="memDENSE + zone reconfiguration",
            technologies=[TI_MEMDENSE, TI_ZONE_RECONF],
            rationale=(
                "Membrane fouling is driven by biomass quality: memDENSE removes filamentous "
                "and low-density organisms, improving permeability and reducing cleaning "
                "frequency. PAO retention is enhanced, improving biological P removal. "
                "Zone reconfiguration optimises anaerobic selection for EBPR and reduces "
                "nitrate return that inhibits PAO activity."
            ),
            constraint_resolved=["Membrane fouling", "EBPR / TP performance"],
            residual=(
                "Membrane permeability should be monitored for 6–12 months after "
                "memDENSE commissioning to confirm fouling trend reversal."
            ),
        )

    if CT_HYDRAULIC in active:
        other = [c for c in active if c != CT_HYDRAULIC]
        other_label = " + ".join(o.replace("_", " ") for o in other) if other else "process"
        return IntensificationStack(
            label=f"EQ basin + {other_label} intensification",
            technologies=[TI_EQ_BASIN] + [TI_INDENSE if CT_SETTLING in other else TI_HYBAS],
            rationale=(
                "Hydraulic constraint must be addressed first by EQ basin or storm storage — "
                "no process intensification technology can substitute for hydraulic attenuation "
                "under extreme peak wet weather. "
                "Once hydraulic loads are attenuated, process intensification can address "
                f"the remaining {other_label} constraint."
            ),
            constraint_resolved=["Hydraulic / peak flow"],
            residual=(
                "Process intensification should be sized for the attenuated (post-EQ) flow. "
                "Do not size intensification for the unattenuated peak flow."
            ),
        )

    # Generic multi-constraint stack
    if len(technologies) >= 2:
        codes = [t.code for t in technologies[:2]]
        return IntensificationStack(
            label=" + ".join(codes),
            technologies=codes,
            rationale=(
                "Multiple constraints are active. The recommended pathway addresses the "
                "dominant constraint first, then layers the secondary mechanism once "
                "the primary upgrade is stable and commissioned."
            ),
            constraint_resolved=[_CT_LABELS.get(c, c) for c in active[:2]],
            residual=(
                "Confirm performance against each constraint after each stage is commissioned "
                "before proceeding to the next layer."
            ),
        )
    return None


# ── Narrative generators ───────────────────────────────────────────────────────

def _constraint_rationale(ct: str, profile, wf: Dict) -> str:
    pc = profile.primary_constraint
    if ct == CT_SETTLING:
        return (
            f"The plant is settling-limited rather than hydraulically limited. "
            f"The primary constraint ({pc}) indicates that clarifier loading, MLSS, or "
            f"solids retention is the active bottleneck. "
            f"Biomass selection — not tank volume — is the priority upgrade mechanism."
        )
    if ct == CT_NITRIFICATION:
        return (
            f"Nitrification capacity is constrained by insufficient biomass retention. "
            f"The primary constraint ({pc}) indicates that effective SRT is too short "
            f"for reliable nitrifier accumulation. "
            f"Biofilm addition provides a decoupled retention mechanism independent of WAS rate."
        )
    if ct == CT_BIOLOGICAL:
        return (
            f"Biological performance (TN / TP / EBPR) is the primary limitation ({pc}). "
            f"The plant has sufficient nitrification capacity but is limited by "
            f"denitrification, carbon availability, or EBPR zone configuration. "
            f"Process optimisation — not additional volume — is the priority mechanism."
        )
    if ct == CT_MEMBRANE:
        return (
            f"Membrane performance is constrained by biomass quality ({pc}). "
            f"Fouling, high cleaning frequency, or low permeability indicate that "
            f"filamentous or light biomass is the underlying driver. "
            f"Selective wasting (memDENSE) improves permeability and resilience "
            f"by removing the problematic biomass fraction."
        )
    if ct == CT_HYDRAULIC:
        return (
            f"Hydraulic throughput is the primary constraint ({pc}). "
            f"Process intensification alone cannot resolve extreme hydraulic overload. "
            f"Balancing, storage, or attenuation infrastructure is the primary mechanism. "
            f"Process upgrades are secondary and should be sized for attenuated flows."
        )
    if ct == CT_MULTI:
        secs = ", ".join(profile.secondary_constraints[:2]) if profile.secondary_constraints else "multiple domains"
        return (
            f"Multiple constraints are active: {pc} is dominant, with secondary pressure from {secs}. "
            f"A staged multi-technology pathway is required. "
            f"Address the settling or hydraulic constraint first before layering biological upgrades."
        )
    return f"Constraint type is uncertain — constraint profile indicates {pc}."


def _mechanism_rationale(mech: str, ct: str) -> str:
    m = {
        MECH_BIOMASS_SEL:  (
            "Biomass selection targets the quality and density of the sludge inventory "
            "rather than the quantity. Denser, more active biomass settles faster, "
            "occupies less clarifier volume, and supports higher MLSS without washout risk."
        ),
        MECH_BIOFILM_RET:  (
            "Biofilm retention adds a fixed biomass fraction that is independent of WAS rate. "
            "This decouples the effective nitrification SRT from the hydraulic SRT, "
            "allowing the plant to achieve longer biological SRT without increasing tank volume."
        ),
        MECH_PROC_OPT:     (
            "Process optimisation reconfigures existing zones and recycle streams to "
            "extract more performance from the same tank volume. "
            "Zone reconfiguration, recycle ratio tuning, and Bardenpho upgrading can "
            "significantly improve TN and TP without civil works."
        ),
        MECH_MEMBRANE_SEL: (
            "Membrane biomass selection removes the low-density and filamentous fraction "
            "of mixed liquor that causes fouling and reduces permeability. "
            "Retaining only the densest, most active biomass improves both filtration "
            "performance and biological treatment efficiency."
        ),
        MECH_HYD_EXP:      (
            "Hydraulic expansion addresses throughput constraints that process intensification "
            "cannot resolve. EQ basins, storm storage, and parallel trains attenuate "
            "peak flows before they stress the biological process."
        ),
        MECH_MULTI: (
            "A multi-mechanism approach is required because no single technology addresses "
            "all active constraints. The recommended pathway sequences mechanism by mechanism: "
            "resolve the settling or hydraulic bottleneck first, then layer biological upgrades."
        ),
    }
    return m.get(mech, "")


def _decision_narrative(
    ct: str, mech: str, preferred: Optional[TechnologyOption],
    stack: Optional[IntensificationStack], profile,
) -> str:
    pc = profile.primary_constraint
    if preferred is None:
        return f"Primary constraint: {pc}. Insufficient data for specific technology recommendation."

    if stack:
        return (
            f"Primary constraint: {pc}. "
            f"Recommended mechanism: {_MECH_LABELS.get(mech, mech)}. "
            f"Preferred upgrade pathway: {stack.label}. "
            f"{stack.rationale}"
        )
    return (
        f"Primary constraint is {_CT_LABELS.get(ct, ct).lower()} ({pc}). "
        f"Recommended mechanism: {_MECH_LABELS.get(mech, mech)}. "
        f"Preferred upgrade pathway: {preferred.name}. "
        f"{preferred.primary_action} "
        f"{preferred.key_truth}"
    )


# ── Main entry point ───────────────────────────────────────────────────────────

def build_intensification_plan(
    profile,                          # ConstraintProfile from brownfield_upgrade_ranking
    waterpoint_fields: Optional[Dict] = None,
) -> IntensificationPlan:
    """
    Build a full intensification plan from a ConstraintProfile.

    Parameters
    ----------
    profile : ConstraintProfile
        Output of _derive_constraint_profile() in brownfield_upgrade_ranking.

    waterpoint_fields : dict, optional
        Additional signals:
          is_sbr, is_mbr, is_mabr
          high_mlss, solids_carryover, nh4_near_limit, srt_pressure
          tn_at_limit, tp_at_limit, ebpr_poor
          membrane_fouling, high_cleaning_frequency, low_permeability
          flow_ratio_above_1p5, overflow_risk

    Returns
    -------
    IntensificationPlan
    """
    wf = waterpoint_fields or {}
    lib = _tech_library()

    # ── Step 1-2: Classify constraint + derive mechanism ──────────────────────
    ct, mech, active = classify_constraint(profile, wf)

    # ── Step 3: Rank technologies ──────────────────────────────────────────────
    technologies = _rank_technologies(ct, active, lib, wf, profile)

    preferred  = technologies[0] if technologies else None
    alternative= technologies[1] if len(technologies) >= 2 else None

    # ── Step 4: Stacking ───────────────────────────────────────────────────────
    stack = _build_stack(ct, active, technologies, wf)

    # ── Step 5: Hydraulic caveat ───────────────────────────────────────────────
    if ct == CT_HYDRAULIC or CT_HYDRAULIC in active:
        hyd_caveat = (
            "Hydraulic expansion (EQ basin / storm storage) is required as the primary "
            "intervention. Process intensification technologies are complementary to "
            "hydraulic attenuation, not substitutes for it. "
            "Extreme peak wet weather flows (> 3× DWA) cannot be managed by biological "
            "upgrading alone."
        )
        hyd_required = True
    else:
        hyd_caveat = (
            "Some flow attenuation or storage may still be necessary under extreme peak "
            "wet weather conditions, even after process intensification is complete."
        )
        hyd_required = False

    # ── Step 6: Narrative ──────────────────────────────────────────────────────
    con_rat  = _constraint_rationale(ct, profile, wf)
    mech_rat = _mechanism_rationale(mech, ct)
    dec_nar  = _decision_narrative(ct, mech, preferred, stack, profile)

    return IntensificationPlan(
        constraint_type    = ct,
        constraint_label   = _CT_LABELS.get(ct, ct),
        mechanism          = mech,
        mechanism_label    = _MECH_LABELS.get(mech, mech),
        technologies       = technologies,
        preferred          = preferred,
        alternative        = alternative,
        stack              = stack,
        constraint_rationale  = con_rat,
        mechanism_rationale   = mech_rat,
        decision_narrative    = dec_nar,
        hydraulic_caveat      = hyd_caveat,
        hydraulic_expansion_required = hyd_required,
        multi_constraint   = len(active) >= 2,
    )


# ══════════════════════════════════════════════════════════════════════════════
# TECHNOLOGY STACK GENERATOR
# ══════════════════════════════════════════════════════════════════════════════
# Produces sequenced multi-technology upgrade stacks from active constraints.
# Replaces single-technology recommendations with ordered stage-by-stage pathways.
#
# New constants added:
#   CT_WET_WEATHER    — peak wet weather / overflow event constraint
#   MECH_BALLASTED    — ballasted settling / high-rate clarification
#   TI_COMAG          — CoMag high-rate clarification
#   TI_BIOMAG         — BioMag ballasted-MBBR hybrid
#
# New dataclasses:
#   ActiveConstraint  — constraint with severity + priority
#   StackStage        — one stage in the upgrade sequence
#   TechnologyStack   — full ordered stack with rationale + alternatives
#
# Main entry point:
#   build_technology_stack(profile, waterpoint_fields) -> TechnologyStack
# ══════════════════════════════════════════════════════════════════════════════

# ── Additional constants ───────────────────────────────────────────────────────
CT_WET_WEATHER   = "wet_weather_peak"
MECH_BALLASTED   = "ballasted_settling"

TI_COMAG  = "CoMag"
TI_BIOMAG = "BioMag"

# Priority order — lower number = address first
_CONSTRAINT_PRIORITY: Dict[str, int] = {
    CT_HYDRAULIC:    1,
    CT_WET_WEATHER:  1,
    CT_SETTLING:     2,
    CT_NITRIFICATION:3,
    CT_BIOLOGICAL:   4,
    CT_MEMBRANE:     5,
    CT_MULTI:        3,
    CT_UNKNOWN:      9,
}

_SEVERITY_WEIGHT: Dict[str, int] = {"High": 0, "Medium": 1, "Low": 2}

# Stage label names
_STAGE_NAMES = {
    1: "Stage 1 — Hydraulic stabilisation",
    2: "Stage 2 — Settling stabilisation",
    3: "Stage 3 — Biological capacity unlock",
    4: "Stage 4 — Process optimisation",
    5: "Stage 5 — Advanced / polishing",
}


# ── New dataclasses ────────────────────────────────────────────────────────────

@dataclass
class ActiveConstraint:
    """A single active constraint with severity and resolved priority."""
    constraint_type: str       # CT_* constant
    label:           str       # human-readable label
    severity:        str       # High / Medium / Low
    priority:        int       # 1 = highest priority (address first)

    def __lt__(self, other: "ActiveConstraint") -> bool:
        if self.priority != other.priority:
            return self.priority < other.priority
        return _SEVERITY_WEIGHT.get(self.severity, 1) < _SEVERITY_WEIGHT.get(other.severity, 1)


@dataclass
class StackStage:
    """One ordered stage in a technology upgrade stack."""
    stage_number:  int
    stage_name:    str
    technology:    str          # TI_* code
    tech_display:  str          # human-readable name
    mechanism:     str          # MECH_* constant
    purpose:       str          # engineering reason (1–2 sentences)
    addresses:     List[str]    # constraint types this stage resolves
    capex_class:   str          # Low / Medium / High
    complexity:    str          # Low / Medium / High
    prerequisite:  str = ""     # what must be in place before this stage


@dataclass
class TechnologyStack:
    """Full ordered technology upgrade stack."""
    # Inputs
    active_constraints:  List[ActiveConstraint]   # sorted by priority + severity
    # Stack
    stages:              List[StackStage]         # ordered upgrade sequence
    # Narrative
    stack_rationale:     str    # "Why this stack works"
    constraint_to_mech:  str    # constraint → mechanism linkage explanation
    alternative_stacks:  List[Dict]  # list of {"label": str, "stages": list, "when": str}
    engineering_notes:   List[str]   # key engineering facts applied
    # Summary
    primary_driver:      str    # dominant constraint in plain English
    expected_outcome:    str    # what the plant achieves after full stack
    residual_risk:       str    # what remains after the stack is implemented
    capex_class_overall: str    # Low / Medium / High (worst stage)
    complexity_overall:  str    # Low / Medium / High (worst stage)


# ── Technology display names for new codes ─────────────────────────────────────
_NEW_TECH_NAMES = {
    TI_COMAG:  "CoMag® (high-rate magnetic ballasted clarification)",
    TI_BIOMAG: "BioMag® (ballasted MBBR-activated sludge hybrid)",
}

_ALL_TECH_NAMES = {
    TI_INDENSE:    "inDENSE® (gravimetric biomass selection)",
    TI_MEMDENSE:   "memDENSE® (MBR biomass selection)",
    TI_HYBAS:      "Hybas™ (IFAS / integrated biofilm)",
    TI_MBBR:       "MBBR / MBBR-Bardenpho",
    TI_IFAS:       "IFAS (integrated fixed-film activated sludge)",
    TI_BARDENPHO:  "Bardenpho / process zone optimisation",
    TI_RECYCLE_OPT:"Recycle ratio optimisation",
    TI_ZONE_RECONF:"Zone reconfiguration / EBPR optimisation",
    TI_EQ_BASIN:   "Equalisation / flow balancing basin",
    TI_STORM_STORE:"Storm storage / attenuation infrastructure",
    TI_PARALLEL:   "Parallel treatment train",
    TI_MIGINDENSE: "MOB (miGRATE™ + inDENSE®) — SBR intensification",
    TI_COMAG:      "CoMag® (high-rate magnetic ballasted clarification)",
    TI_BIOMAG:     "BioMag® (ballasted MBBR-activated sludge hybrid)",
}

_TECH_CAPEX   = {TI_INDENSE:"Low", TI_MEMDENSE:"Low", TI_HYBAS:"Medium", TI_MBBR:"Medium",
                 TI_IFAS:"Low", TI_BARDENPHO:"Low", TI_RECYCLE_OPT:"Low",
                 TI_ZONE_RECONF:"Low", TI_EQ_BASIN:"High", TI_STORM_STORE:"High",
                 TI_PARALLEL:"High", TI_MIGINDENSE:"Medium", TI_COMAG:"Medium", TI_BIOMAG:"Medium"}
_TECH_COMPLEX = {TI_INDENSE:"Low", TI_MEMDENSE:"Low", TI_HYBAS:"Medium", TI_MBBR:"Medium",
                 TI_IFAS:"Low", TI_BARDENPHO:"Low", TI_RECYCLE_OPT:"Low",
                 TI_ZONE_RECONF:"Medium", TI_EQ_BASIN:"Medium", TI_STORM_STORE:"Medium",
                 TI_PARALLEL:"High", TI_MIGINDENSE:"Medium", TI_COMAG:"Medium", TI_BIOMAG:"High"}

_SEVERITY_ORDER = {"High": 0, "Medium": 1, "Low": 2}
_CAPEX_ORDER    = {"Low": 0, "Medium": 1, "High": 2}


# ── Step 1-2: Collect and sort active constraints ──────────────────────────────

def _collect_active_constraints(
    profile, wf: Dict
) -> List[ActiveConstraint]:
    """
    Derive all active constraints with severity and priority.

    Returns list sorted by (priority asc, severity asc).
    """
    result: List[ActiveConstraint] = []

    def _add(ct: str, sev: str) -> None:
        result.append(ActiveConstraint(
            constraint_type = ct,
            label           = _CT_LABELS.get(ct, ct),
            severity        = sev,
            priority        = _CONSTRAINT_PRIORITY.get(ct, 9),
        ))

    # Hydraulic / overflow — highest priority
    if profile.hydraulic_flag or wf.get("overflow_risk") or wf.get("flow_ratio_above_1p5"):
        flow_ratio = wf.get("flow_ratio", 1.0) or 1.0
        sev = "High" if (wf.get("overflow_risk") or flow_ratio >= 2.0) else "Medium"
        _add(CT_HYDRAULIC, sev)

    # Wet weather peak (distinct from chronic hydraulic)
    if wf.get("wet_weather_peak") or wf.get("pwwf_active"):
        _add(CT_WET_WEATHER, "High" if wf.get("overflow_risk") else "Medium")

    # Settling
    if profile.clarifier_flag or profile.solids_flag or wf.get("high_mlss") or wf.get("solids_carryover"):
        clar_u = wf.get("clarifier_util", 0.0) or 0.0
        sev = "High" if clar_u >= 1.0 or wf.get("solids_carryover") else "Medium"
        _add(CT_SETTLING, sev)

    # Nitrification
    if profile.nitrification_flag or profile.aeration_flag or wf.get("nh4_near_limit") or wf.get("srt_pressure"):
        sev = "High" if wf.get("nh4_near_limit") else "Medium"
        _add(CT_NITRIFICATION, sev)

    # Biological performance (TN / TP / EBPR)
    if profile.carbon_limit_flag or profile.denitrification_flag or wf.get("tn_at_limit") or wf.get("tp_at_limit") or wf.get("ebpr_poor"):
        sev = "High" if wf.get("tn_at_limit") else "Medium"
        _add(CT_BIOLOGICAL, sev)

    # Membrane
    if wf.get("membrane_fouling") or wf.get("high_cleaning_frequency") or wf.get("low_permeability"):
        sev = "High" if wf.get("membrane_fouling") and wf.get("high_cleaning_frequency") else "Medium"
        _add(CT_MEMBRANE, sev)

    # Sort by priority then severity
    result.sort(key=lambda c: (c.priority, _SEVERITY_WEIGHT.get(c.severity, 1)))
    return result


# ── Step 3-4: Map constraints to stages ───────────────────────────────────────

def _build_stages(
    constraints: List[ActiveConstraint],
    wf: Dict,
) -> List[StackStage]:
    """
    Build the ordered stage sequence from prioritised constraints.

    Rules:
    - Stage 1: hydraulic/wet weather → CoMag or EQ basin (FIRST if present)
    - Stage 2: settling → inDENSE / BioMag / MOB
    - Stage 3: nitrification → IFAS / MBBR / Hybas
    - Stage 4: biological → Bardenpho / recycle optimisation
    - Stage 5: membrane → memDENSE (or advanced polishing)
    - No redundancies: IFAS and MBBR not combined; CoMag and BioMag not combined
    """
    is_sbr   = bool(wf.get("is_sbr", False))
    is_mbr   = bool(wf.get("is_mbr", False))
    is_mabr  = bool(wf.get("is_mabr", False))
    high_load= bool(wf.get("high_load", False))       # elevated load → favour BioMag over inDENSE
    ww_peak  = bool(wf.get("wet_weather_peak", False))
    overflow = bool(wf.get("overflow_risk", False))

    stages: List[StackStage] = []
    used_stage_numbers: set = set()
    used_tech_codes: set = set()

    def _add_stage(
        stage_num: int, tech: str, mech: str, purpose: str,
        addresses: List[str], prereq: str = ""
    ) -> None:
        if stage_num in used_stage_numbers: return
        if tech in used_tech_codes: return
        used_stage_numbers.add(stage_num)
        used_tech_codes.add(tech)
        stages.append(StackStage(
            stage_number = stage_num,
            stage_name   = _STAGE_NAMES.get(stage_num, f"Stage {stage_num}"),
            technology   = tech,
            tech_display = _ALL_TECH_NAMES.get(tech, tech),
            mechanism    = mech,
            purpose      = purpose,
            addresses    = addresses,
            capex_class  = _TECH_CAPEX.get(tech, "Medium"),
            complexity   = _TECH_COMPLEX.get(tech, "Medium"),
            prerequisite = prereq,
        ))

    constraint_types = {c.constraint_type for c in constraints}

    # ── Stage 1: Hydraulic / wet weather ──────────────────────────────────────
    if CT_HYDRAULIC in constraint_types or CT_WET_WEATHER in constraint_types:
        hyd_con = next((c for c in constraints
                        if c.constraint_type in (CT_HYDRAULIC, CT_WET_WEATHER)), None)
        if hyd_con and (overflow or ww_peak or hyd_con.severity == "High"):
            # CoMag for acute peak / overflow (high-rate clarification)
            _add_stage(1, TI_COMAG, MECH_BALLASTED,
                "High-rate magnetic ballasted clarification provides rapid solids removal "
                "under peak wet weather flows, protecting the downstream biological process "
                "from hydraulic and solids shock loads. "
                "CoMag is effective at 3–5× DWA without requiring new secondary tanks.",
                [CT_HYDRAULIC, CT_WET_WEATHER])
        else:
            # EQ basin for sustained hydraulic constraint
            _add_stage(1, TI_EQ_BASIN, MECH_HYD_EXP,
                "Equalisation basin attenuates peak inflow before secondary treatment. "
                "Target attenuation to ≤ 2× DWA at inlet to secondary process. "
                "No process intensification can substitute for hydraulic attenuation "
                "under extreme peak wet weather flows.",
                [CT_HYDRAULIC, CT_WET_WEATHER])

    # ── Stage 2: Settling ──────────────────────────────────────────────────────
    if CT_SETTLING in constraint_types:
        set_con = next((c for c in constraints if c.constraint_type == CT_SETTLING), None)
        if is_sbr:
            _add_stage(2, TI_MIGINDENSE, MECH_BIOMASS_SEL,
                "MOB (inDENSE + miGRATE) stabilises settling and unlocks cycle capacity "
                "in the existing SBR without new reactor volume. "
                "inDENSE is the settling prerequisite; miGRATE provides biological optimisation. "
                "Install inDENSE first, then miGRATE after settling is confirmed stable.",
                [CT_SETTLING, CT_NITRIFICATION],
                prereq="SBR operational with stable feed characteristics")
        elif is_mbr:
            _add_stage(2, TI_MEMDENSE, MECH_MEMBRANE_SEL,
                "memDENSE removes filamentous and light biomass from MBR mixed liquor, "
                "reducing clarifier/membrane loading and improving permeability. "
                "Dense, active biomass is selectively retained.",
                [CT_SETTLING, CT_MEMBRANE])
        elif high_load and CT_HYDRAULIC not in constraint_types:
            # BioMag preferred when settling + high biological load but no acute hydraulic
            _add_stage(2, TI_BIOMAG, MECH_BALLASTED,
                "BioMag combines ballasted settling with biofilm carriers, "
                "improving both hydraulic throughput and biological treatment capacity. "
                "Magnetic microspheres improve sludge density and settling velocity. "
                "Suitable where MLSS is elevated and conventional settling is marginal.",
                [CT_SETTLING, CT_NITRIFICATION],
                prereq="Ballast recovery and recycling infrastructure available")
        else:
            _add_stage(2, TI_INDENSE, MECH_BIOMASS_SEL,
                "inDENSE gravimetric selection removes light and filamentous biomass, "
                "improving settling velocity and reducing sludge volume index. "
                "Clarifier loading and overflow risk decrease without adding tank volume.",
                [CT_SETTLING])

    # ── Stage 3: Nitrification ─────────────────────────────────────────────────
    if CT_NITRIFICATION in constraint_types:
        # Skip if MOB already covers nitrification (SBR case above)
        if TI_MIGINDENSE not in used_tech_codes:
            if is_mabr:
                # MABR already handles nitrification — no additional biofilm needed
                pass
            elif TI_INDENSE in used_tech_codes or TI_BIOMAG in used_tech_codes:
                # Hybas pairs well with settling remediation
                _add_stage(3, TI_HYBAS, MECH_BIOFILM_RET,
                    "Hybas biofilm carriers decouple nitrification SRT from hydraulic SRT. "
                    "Nitrifying biofilm accumulates on carriers independent of WAS rate, "
                    "enabling longer effective sludge age without increasing tank volume. "
                    "Suspended MLSS decreases, further reducing clarifier loading.",
                    [CT_NITRIFICATION],
                    prereq="Stage 2 settling stabilisation complete")
            else:
                # IFAS for standalone nitrification — simpler than full Hybas
                _add_stage(3, TI_IFAS, MECH_BIOFILM_RET,
                    "IFAS carriers retain nitrifying biofilm in the existing aeration zone, "
                    "decoupling effective nitrification SRT from hydraulic SRT. "
                    "No new tank volume required. Media retention screens installed at zone outlets.",
                    [CT_NITRIFICATION])

    # ── Stage 4: Biological performance (TN / TP) ──────────────────────────────
    if CT_BIOLOGICAL in constraint_types:
        if TI_HYBAS in used_tech_codes or TI_IFAS in used_tech_codes or TI_MBBR in used_tech_codes:
            # Bardenpho pairs with biofilm — synergistic TN optimisation
            _add_stage(4, TI_BARDENPHO, MECH_PROC_OPT,
                "Bardenpho zone configuration maximises denitrification using the "
                "elevated nitrate load from biofilm nitrification. "
                "Second anoxic zone significantly reduces effluent TN. "
                "Optimal internal recycle R ≈ 2; anaerobic HRT 2–2.5h for EBPR.",
                [CT_BIOLOGICAL],
                prereq="Biofilm stage (Stage 3) commissioned and stable")
        else:
            # Process optimisation without biofilm — recycle + zone reconfiguration
            _add_stage(4, TI_RECYCLE_OPT, MECH_PROC_OPT,
                "Internal recycle ratio optimisation improves denitrification efficiency "
                "without capital spend. R ≈ 2 recovers ~67% of nitrate; R=4 recovers ~80%. "
                "Diminishing returns above R=4 due to dissolved oxygen carry-over.",
                [CT_BIOLOGICAL])
            # Add zone reconfiguration if EBPR is also an issue
            if wf.get("ebpr_poor") or wf.get("tp_at_limit"):
                _add_stage(5, TI_ZONE_RECONF, MECH_PROC_OPT,
                    "Zone reconfiguration establishes a true anaerobic zone (no nitrate, no O₂) "
                    "for PAO selection and EBPR. Anaerobic volume 10–15% of total bioreactor volume. "
                    "Minimise nitrate return to the anaerobic zone.",
                    [CT_BIOLOGICAL],
                    prereq="Recycle optimisation (Stage 4) complete")

    # ── Stage 5: Membrane ──────────────────────────────────────────────────────
    if CT_MEMBRANE in constraint_types and TI_MEMDENSE not in used_tech_codes:
        _add_stage(5, TI_MEMDENSE, MECH_MEMBRANE_SEL,
            "memDENSE removes filaments and light biomass from MBR mixed liquor. "
            "Membrane permeability improves, cleaning frequency reduces, "
            "and PAO retention is enhanced for improved biological P removal.",
            [CT_MEMBRANE])

    # Sort stages by stage number
    stages.sort(key=lambda s: s.stage_number)
    return stages


# ── Redundancy removal ─────────────────────────────────────────────────────────

def _remove_redundancies(stages: List[StackStage]) -> List[StackStage]:
    """
    Apply deduplication rules:
    - Not both CoMag AND BioMag
    - Not both IFAS AND MBBR
    - Prefer simplest viable combination
    """
    tech_codes = [s.technology for s in stages]

    # Rule 1: CoMag and BioMag — keep CoMag (hydraulic first)
    if TI_COMAG in tech_codes and TI_BIOMAG in tech_codes:
        stages = [s for s in stages if s.technology != TI_BIOMAG]

    # Rule 2: IFAS and MBBR — keep IFAS (simpler)
    if TI_IFAS in tech_codes and TI_MBBR in tech_codes:
        stages = [s for s in stages if s.technology != TI_MBBR]

    # Rule 3: MOB already covers both settling + nitrification in SBR
    if TI_MIGINDENSE in tech_codes:
        stages = [s for s in stages
                  if s.technology not in (TI_INDENSE, TI_IFAS, TI_MBBR, TI_HYBAS)
                  or s.technology == TI_MIGINDENSE]

    # Renumber stages sequentially
    for i, stage in enumerate(sorted(stages, key=lambda s: s.stage_number), 1):
        stage.stage_number = i
        stage.stage_name = _STAGE_NAMES.get(i, f"Stage {i}")

    return stages


# ── Alternative stack generator ────────────────────────────────────────────────

def _build_alternatives(
    constraints: List[ActiveConstraint],
    primary_stages: List[StackStage],
    wf: Dict,
) -> List[Dict]:
    """Generate 1–2 alternative pathways."""
    alts: List[Dict] = []
    ct_set = {c.constraint_type for c in constraints}
    primary_techs = [s.technology for s in primary_stages]
    is_sbr = bool(wf.get("is_sbr", False))

    # Alternative 1: Civil expansion (last resort)
    if len(primary_stages) >= 2:
        alts.append({
            "label": "Conventional civil expansion",
            "stages": ["Secondary clarifier expansion", "New bioreactor volume", "Additional blower capacity"],
            "when": (
                "When the intensification envelope is demonstrably exhausted and "
                "process optimisation has failed to achieve compliance targets. "
                "Should only be pursued after all intensification options are evaluated."
            ),
            "capex_class": "High",
            "notes": "Addresses capacity by volume addition rather than process efficiency.",
        })

    # Alternative 2: Simpler single-technology option
    if len(primary_stages) >= 3 and CT_NITRIFICATION in ct_set:
        bio_opt = TI_MBBR if TI_IFAS in primary_techs else TI_IFAS
        alts.append({
            "label": f"Simplified biofilm pathway ({_ALL_TECH_NAMES.get(bio_opt, bio_opt)})",
            "stages": [
                _ALL_TECH_NAMES.get(s.technology, s.technology)
                for s in primary_stages if s.technology not in (TI_IFAS, TI_HYBAS, TI_MBBR)
            ] + [_ALL_TECH_NAMES.get(bio_opt, bio_opt)],
            "when": (
                "When capital is constrained and a simpler technology pathway is preferred. "
                f"{_ALL_TECH_NAMES.get(bio_opt, bio_opt)} provides similar nitrification "
                "capacity to the primary stack with a different operational profile."
            ),
            "capex_class": "Medium",
            "notes": "Slightly different operational characteristics — confirm with site-specific modelling.",
        })

    # Alternative 3: Hydraulic-first only (defer biology)
    if CT_HYDRAULIC in ct_set and len(primary_stages) >= 2:
        alts.append({
            "label": "Hydraulic-only interim (defer biological upgrade)",
            "stages": [
                _ALL_TECH_NAMES.get(s.technology, s.technology)
                for s in primary_stages if s.mechanism in (MECH_HYD_EXP, MECH_BALLASTED)
            ] or ["EQ basin only"],
            "when": (
                "When hydraulic compliance is the immediate driver and biological "
                "performance is within tolerance. Defer the biological stage until "
                "hydraulic infrastructure is commissioned and flows are characterised."
            ),
            "capex_class": "High",
            "notes": "Biological stage must follow — hydraulic solution alone is not a complete upgrade.",
        })

    return alts[:2]   # return max 2 alternatives


# ── Narrative generators ───────────────────────────────────────────────────────

def _stack_rationale(
    constraints: List[ActiveConstraint],
    stages: List[StackStage],
    wf: Dict,
) -> str:
    """Generate 'Why this stack works' explanation."""
    if not stages:
        return "Insufficient constraint data to generate stack rationale."

    parts = []
    for stage in stages:
        mech_label = _MECH_LABELS.get(stage.mechanism, stage.mechanism)
        parts.append(
            f"Stage {stage.stage_number} ({stage.tech_display}) addresses "
            f"{', '.join(stage.addresses)} via {mech_label.lower()}."
        )

    return (
        "This stack is sequenced to address the highest-priority constraint first, "
        "with each stage unlocking the next. "
        + " ".join(parts)
        + " Technologies are selected to avoid functional overlap and to stack efficiently "
        "within existing tank volume wherever possible."
    )


def _constraint_to_mech_explanation(constraints: List[ActiveConstraint]) -> str:
    """Generate constraint → mechanism → solution linkage."""
    lines = []
    for c in constraints:
        mech = {
            CT_HYDRAULIC:    MECH_BALLASTED + " / " + MECH_HYD_EXP,
            CT_WET_WEATHER:  MECH_BALLASTED,
            CT_SETTLING:     MECH_BIOMASS_SEL,
            CT_NITRIFICATION:MECH_BIOFILM_RET,
            CT_BIOLOGICAL:   MECH_PROC_OPT,
            CT_MEMBRANE:     MECH_MEMBRANE_SEL,
        }.get(c.constraint_type, "process_optimisation")

        tech_label = {
            CT_HYDRAULIC:    "CoMag / EQ basin",
            CT_WET_WEATHER:  "CoMag",
            CT_SETTLING:     "inDENSE / MOB / BioMag",
            CT_NITRIFICATION:"Hybas / IFAS / MBBR",
            CT_BIOLOGICAL:   "Bardenpho / recycle optimisation",
            CT_MEMBRANE:     "memDENSE",
        }.get(c.constraint_type, "process optimisation")

        explanation = {
            CT_HYDRAULIC:    "Hydraulic constraint is the primary failure driver — high-rate clarification or storage is required before biological upgrades can be effective.",
            CT_WET_WEATHER:  "Peak wet weather flows exceed biological process capacity — high-rate clarification (CoMag) protects the downstream process without new secondary tanks.",
            CT_SETTLING:     "Settling limitation indicates biomass selection is required to stabilise MLSS and prevent solids washout.",
            CT_NITRIFICATION:"Nitrification is constrained by sludge age — biofilm systems decouple SRT from HRT, unlocking nitrification capacity within fixed volume.",
            CT_BIOLOGICAL:   "Biological performance is limited by zone configuration or carbon availability — process optimisation extracts more performance from existing volume.",
            CT_MEMBRANE:     "Membrane performance is constrained by biomass quality — selective wasting improves permeability and reduces fouling.",
        }.get(c.constraint_type, f"Constraint: {c.label}")

        lines.append(
            f"[{c.severity}] {c.label} → {_MECH_LABELS.get(mech.split('/')[0].strip(), mech)} ({tech_label}): {explanation}"
        )
    return "\n".join(lines)


def _engineering_notes_for_stack(stages: List[StackStage]) -> List[str]:
    """Return key engineering facts applied in this stack."""
    notes = []
    tech_codes = {s.technology for s in stages}
    if TI_COMAG in tech_codes:
        notes.append("CoMag can treat 3–5× DWA without new secondary tanks; requires ballast recovery and recycling infrastructure.")
    if TI_BIOMAG in tech_codes:
        notes.append("BioMag combines ballasted settling with attached growth; magnetic microspheres improve sludge density and settling velocity.")
    if TI_INDENSE in tech_codes or TI_MIGINDENSE in tech_codes:
        notes.append("inDENSE is the settling prerequisite before miGRATE; miGRATE alone does not consistently improve SVI (Lang Lang + Army Bay finding).")
    if TI_HYBAS in tech_codes or TI_IFAS in tech_codes:
        notes.append("Biofilm carriers decouple SRT from HRT — nitrifiers accumulate on media independent of WAS rate.")
    if TI_MBBR in tech_codes:
        notes.append("MBBR biofilm contributes ~80% of nitrification in hybrid configuration. Optimal R ≈ 2; anaerobic HRT 2–2.5h for EBPR.")
    if TI_BARDENPHO in tech_codes:
        notes.append("Bardenpho 5-stage: second anoxic zone significantly reduces effluent TN. Anaerobic HRT 2–2.5h optimal for PAO selection.")
    if TI_MEMDENSE in tech_codes:
        notes.append("memDENSE selective wasting removes filaments, improves permeability, reduces aeration demand, and enhances PAO retention.")
    if TI_EQ_BASIN in tech_codes:
        notes.append("EQ basin: target attenuation to ≤ 2× DWA at inlet to secondaries. No process intensification substitutes for hydraulic attenuation.")
    return notes


def _overall_class(stages: List[StackStage], attr: str) -> str:
    order = {"Low": 0, "Medium": 1, "High": 2}
    vals = [getattr(s, attr) for s in stages]
    if not vals: return "Low"
    return max(vals, key=lambda v: order.get(v, 0))


# ── Main entry point ───────────────────────────────────────────────────────────

def build_technology_stack(
    profile,
    waterpoint_fields: Optional[Dict] = None,
) -> TechnologyStack:
    """
    Build a sequenced multi-technology upgrade stack from a ConstraintProfile.

    Parameters
    ----------
    profile : ConstraintProfile
        Output of _derive_constraint_profile() from brownfield_upgrade_ranking.

    waterpoint_fields : dict, optional
        Additional signals:
          is_sbr, is_mbr, is_mabr, high_load
          overflow_risk, wet_weather_peak, pwwf_active, flow_ratio
          high_mlss, solids_carryover, clarifier_util
          nh4_near_limit, srt_pressure
          tn_at_limit, tp_at_limit, ebpr_poor
          membrane_fouling, high_cleaning_frequency, low_permeability

    Returns
    -------
    TechnologyStack
    """
    wf = waterpoint_fields or {}

    # ── Step 1-2: Collect and sort constraints ─────────────────────────────────
    constraints = _collect_active_constraints(profile, wf)

    # ── Steps 3-4: Map to stages ───────────────────────────────────────────────
    stages = _build_stages(constraints, wf)

    # ── Step 5: Remove redundancies ────────────────────────────────────────────
    stages = _remove_redundancies(stages)

    if not stages:
        # Fallback: at least one stage
        stages = [StackStage(
            stage_number=1,
            stage_name="Stage 1 — Process review",
            technology=TI_RECYCLE_OPT,
            tech_display=_ALL_TECH_NAMES[TI_RECYCLE_OPT],
            mechanism=MECH_PROC_OPT,
            purpose="No dominant constraint identified — review recycle ratios and zone configuration as first step.",
            addresses=[CT_BIOLOGICAL],
            capex_class="Low",
            complexity="Low",
        )]

    # ── Steps 6-7: Narrative ───────────────────────────────────────────────────
    alt_stacks     = _build_alternatives(constraints, stages, wf)
    stack_rat      = _stack_rationale(constraints, stages, wf)
    c2m            = _constraint_to_mech_explanation(constraints)
    eng_notes      = _engineering_notes_for_stack(stages)

    # Primary driver
    primary_driver = (
        constraints[0].label if constraints
        else "No dominant constraint identified"
    )

    # Expected outcome
    addressed = list({addr for s in stages for addr in s.addresses})
    expected = (
        f"After full stack implementation: {', '.join(a.replace('_limitation','').replace('_',' ') for a in addressed)} "
        f"constraints are addressed. Plant can operate within the intensified envelope "
        f"without major civil expansion."
    )

    # Residual risk
    residual_parts = []
    ct_set = {c.constraint_type for c in constraints}
    if CT_HYDRAULIC in ct_set or CT_WET_WEATHER in ct_set:
        residual_parts.append("Extreme wet weather (> 3× DWA) may still require additional storage or sewer-level attenuation.")
    if CT_BIOLOGICAL in ct_set and TI_BARDENPHO not in {s.technology for s in stages}:
        residual_parts.append("TN / TP compliance may require external carbon dosing if COD/N ratio is below 4.")
    residual_parts.append("Stack performance should be confirmed by staged commissioning and effluent monitoring before proceeding to next stage.")
    residual = " ".join(residual_parts)

    return TechnologyStack(
        active_constraints  = constraints,
        stages              = stages,
        stack_rationale     = stack_rat,
        constraint_to_mech  = c2m,
        alternative_stacks  = alt_stacks,
        engineering_notes   = eng_notes,
        primary_driver      = primary_driver,
        expected_outcome    = expected,
        residual_risk       = residual,
        capex_class_overall = _overall_class(stages, "capex_class"),
        complexity_overall  = _overall_class(stages, "complexity"),
    )
