"""
BioPoint V1 — System Transition Summary Engine (v25A30).

Produces the strategic framing outputs required by v25A30:

  Part 5: WWTP role shift declaration
    "The wastewater plant transitions from sludge processor to feedstock producer."

  Part 6: End-state declaration
    "The final system is a decoupled, industrial thermal processing platform
     (ITS or incineration), on-site or off-site."

  Part 7: Step-gate narrative
    - What must be done first
    - What becomes possible after each step
    - What the inevitable system configuration is

Draws on existing engine outputs (drying_dominance, preconditioning,
inevitability, its_classification) to generate the structured narrative.

ph2o Consulting — BioPoint V1
"""

from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# DATACLASS
# ---------------------------------------------------------------------------

@dataclass
class SystemTransitionSummary:
    """
    Strategic transition framing — role shift, end-state, step-gate narrative.
    v25A30 requirements: Parts 5, 6, and 7.
    """

    # Part 5 — Role shift declaration
    plant_role_shift_applies: bool = False
    plant_role_shift_statement: str = ""
    plant_role_shift_rationale: str = ""

    # Part 6 — End-state declaration
    end_state_declaration: str = ""
    end_state_on_site_or_off_site: str = ""  # "on-site" / "off-site" / "either"
    end_state_pathway: str = ""              # "ITS" / "incineration" / "ITS or incineration"
    end_state_rationale: str = ""

    # Part 7 — Step-gate narrative
    gates: list = field(default_factory=list)   # List[StepGate]

    # System classification
    system_classification: str = ""  # Water-removal constrained / Drying constrained / Viable
    system_classification_note: str = ""

    # Decision register (3-state)
    decide_now: list = field(default_factory=list)      # List[str]
    decide_next: list = field(default_factory=list)     # List[str] (0-24 months)
    decide_later: list = field(default_factory=list)    # List[str] (after gate conditions)


@dataclass
class StepGate:
    """One gate in the step-gate transition narrative."""
    gate_number: int = 0
    gate_name: str = ""
    gate_condition: str = ""         # What must be true to pass this gate
    current_status: str = ""         # "OPEN" / "BLOCKED" / "PASSED"
    what_is_blocked: list = field(default_factory=list)   # Pathways blocked until this gate
    what_becomes_possible: list = field(default_factory=list)   # What opens after this gate
    investment_required: str = ""
    timeline: str = ""


# ---------------------------------------------------------------------------
# MAIN ENGINE
# ---------------------------------------------------------------------------

def run_system_transition_summary(
    flowsheets: list,
    feedstock_inputs,
    strategic_inputs,
    drying_dominance_system,
    preconditioning,
    inevitability,
    its_assessment,
) -> SystemTransitionSummary:
    """
    Build the system transition summary from existing engine outputs.

    Parameters
    ----------
    flowsheets              : evaluated Flowsheet objects
    feedstock_inputs        : FeedstockInputsV2
    strategic_inputs        : StrategicInputs
    drying_dominance_system : DryingDominanceSystem
    preconditioning         : PreconditioningAssessment
    inevitability           : InevitabilityAssessment
    its_assessment          : ITSSystemAssessment
    """
    fs_in    = feedstock_inputs
    ds_tpd   = fs_in.dry_solids_tpd
    feed_ds  = fs_in.dewatered_ds_percent
    pfas_st  = fs_in.pfas_present
    dd_sys   = drying_dominance_system
    pc       = preconditioning

    summary = SystemTransitionSummary()

    # --- SYSTEM CLASSIFICATION ---
    if feed_ds < 20.0:
        summary.system_classification = "WATER-REMOVAL CONSTRAINED"
        summary.system_classification_note = (
            f"Feed DS {feed_ds:.0f}% is below 20%. "
            "All thermal pathways are blocked. "
            "The engineering priority is mechanical dewatering, not technology selection."
        )
    elif dd_sys.primary_constraint_is_drying:
        summary.system_classification = "DRYING CONSTRAINED"
        summary.system_classification_note = (
            f"Feed DS {feed_ds:.0f}% — drying is the primary system constraint. "
            "Multiple thermal pathways fail the feasibility gate. "
            "Preconditioning to higher DS% is required before thermal investment."
        )
    else:
        summary.system_classification = "THERMALLY VIABLE"
        summary.system_classification_note = (
            f"Feed DS {feed_ds:.0f}% — thermal pathways are accessible. "
            "Technology selection can proceed subject to PFAS characterisation "
            "and market confirmation."
        )

    # --- PART 5: ROLE SHIFT DECLARATION ---
    # Applies when dewatering or thermal hub is in the strategy
    # (i.e. the plant produces a solid product exported for treatment elsewhere)
    has_off_site = any(
        f.siting.off_site_feasible for f in flowsheets if f.siting
    )
    role_shift_applies = (
        has_off_site or
        ds_tpd >= 30.0 or        # Large plants benefit most
        feed_ds < 20.0           # Must dewater first → produces exportable solid
    )
    summary.plant_role_shift_applies = role_shift_applies

    if role_shift_applies:
        summary.plant_role_shift_statement = (
            "The wastewater plant transitions from sludge processor to feedstock producer."
        )
        summary.plant_role_shift_rationale = (
            "Once mechanical dewatering is installed, the plant's role changes: "
            "it digests, dewaters, and produces a concentrated solid feedstock "
            "for downstream thermal processing — on-site or off-site. "
            "The plant is no longer responsible for the final fate of its biosolids; "
            "it is responsible for producing a consistent, high-DS% feedstock "
            "that a thermal processor can receive. "
            "This reframing is not semantic — it changes procurement, risk allocation, "
            "and infrastructure planning fundamentally."
        )
    else:
        summary.plant_role_shift_statement = (
            "Plant-level strategy — on-site integrated processing."
        )

    # --- PART 6: END-STATE DECLARATION ---
    # Determine likely end-state from ITS and PFAS context
    l4_count = its_assessment.level4_count if its_assessment else 0
    l3_count = its_assessment.level3_count if its_assessment else 0
    off_site_paths = [f.name for f in flowsheets
                      if f.siting and f.siting.off_site_feasible
                      and f.its_classification and f.its_classification.its_level >= 3]

    if pfas_st == "confirmed":
        end_pathway = "incineration (mandatory)"
        end_rationale = "PFAS confirmed — incineration is the only validated destruction route."
    elif l3_count > 0 or l4_count > 0:
        end_pathway = "ITS or incineration"
        end_rationale = (
            "Thermal end-state determined by PFAS characterisation result and market conditions. "
            "ITS (Level 3) is acceptable where PFAS destruction is validated. "
            "Incineration (Level 4) provides highest regulatory certainty."
        )
    else:
        end_pathway = "thermal processing (ITS minimum viable configuration)"
        end_rationale = "Standard pyrolysis/gasification without ITS is not a credible end-state."

    siting = "off-site" if (
        strategic_inputs.land_constraint in ("high", "moderate") or
        strategic_inputs.social_licence_pressure in ("high", "moderate")
    ) else "either"

    summary.end_state_declaration = (
        "The final system is a decoupled, industrial thermal processing platform "
        f"({end_pathway}), {siting}."
    )
    summary.end_state_on_site_or_off_site = siting
    summary.end_state_pathway = end_pathway
    summary.end_state_rationale = end_rationale

    # --- PART 7: STEP-GATE NARRATIVE ---
    summary.gates = _build_step_gates(
        feed_ds, ds_tpd, pc, pfas_st, inevitability, flowsheets
    )

    # --- DECISION REGISTER ---
    summary.decide_now  = _decide_now(feed_ds, pfas_st, ds_tpd, inevitability)
    summary.decide_next = _decide_next(feed_ds, pc, pfas_st)
    summary.decide_later = _decide_later(feed_ds, pfas_st)

    return summary


# ---------------------------------------------------------------------------
# STEP-GATE BUILDER
# ---------------------------------------------------------------------------

def _build_step_gates(
    feed_ds: float, ds_tpd: float, pc,
    pfas_st: str, inv, flowsheets: list
) -> list:

    gates = []
    gate_n = 1

    # GATE 1 — Always first if DS < 20%
    if feed_ds < 20.0:
        g = StepGate(
            gate_number=gate_n,
            gate_name="Mechanical Dewatering Gate",
            gate_condition=(
                f"Install centrifuge/belt-press dewatering. "
                f"Achieve consistent DS% ≥ 20% (target: 22–26%)."
            ),
            current_status="BLOCKED",
            what_is_blocked=[
                "All thermal pathways (pyrolysis, gasification, incineration)",
                "Off-site hub transport (wet sludge is uneconomic to haul)",
                "Drying investment (drying at current DS% is physically impossible)",
            ],
            what_becomes_possible=[
                "Transport of dewatered cake to off-site hub (86-89% volume reduction)",
                "HTC + sidestream as near-term wet pathway option",
                "Drying feasibility assessment at 22% DS (incineration still requires more)",
                "Elimination of drying pans — permanent weather-independent outlet",
            ],
            investment_required=(
                f"Centrifuge trains for {ds_tpd:.0f} tDS/day throughput. "
                "Indicative CAPEX: $15–30M at this scale."
            ),
            timeline="0–18 months — prerequisite for all subsequent steps",
        )
        gates.append(g)
        gate_n += 1

    # GATE 2 — DS to 28-32% for incineration
    incin_viable_at_current = feed_ds >= 28.0
    g2 = StepGate(
        gate_number=gate_n,
        gate_name="DS% Uplift Gate (Incineration Threshold)",
        gate_condition=(
            "Achieve DS% ≥ 28–32% through THP, filter press, or polymer optimisation. "
            "Confirm at operating scale (not pilot) before thermal CAPEX commitment."
        ),
        current_status="PASSED" if incin_viable_at_current else "BLOCKED",
        what_is_blocked=(
            ["Incineration (FAIL at <28% DS — drying energy too high)"] if not incin_viable_at_current else []
        ),
        what_becomes_possible=[
            "Incineration passes the drying feasibility gate at 28–32% DS",
            "Drying energy burden reduced by 50-55% vs 20% DS baseline",
            "Off-site hub with incineration/FBF becomes viable",
            "Pyrolysis moves from NOT VIABLE to MARGINAL (still FAIL gate but approaching)",
        ],
        investment_required=(
            "Filter press addition: $10–20M. THP system: $30–50M. "
            "Polymer optimisation: $1–3M (highest ROI of any preconditioning step)."
        ),
        timeline="12–30 months after dewatering commissioned",
    )
    gates.append(g2)
    gate_n += 1

    # GATE 3 — PFAS characterisation (always required before product route)
    g3 = StepGate(
        gate_number=gate_n,
        gate_name="PFAS Characterisation Gate",
        gate_condition=(
            "Commission representative PFAS sampling across all sludge streams. "
            "Result determines which product routes and pathways remain open."
        ),
        current_status="BLOCKED" if pfas_st == "unknown" else (
            "PASSED (negative)" if pfas_st == "negative" else "PASSED (confirmed — pathway constrained)"
        ),
        what_is_blocked=[
            "Biochar / hydrochar product revenue business case (PFAS unknown = conditional only)",
            "Land application (risk if PFAS confirmed)",
            "Final thermal pathway selection (PFAS+ forces incineration)",
        ],
        what_becomes_possible=(
            ["All pathways remain open — proceed to thermal selection"] if pfas_st == "negative" else
            ["Incineration mandatory — immediately begin procurement"] if pfas_st == "confirmed" else
            ["Pathway selection pending — commission testing immediately"]
        ),
        investment_required="Modest — PFAS sampling and laboratory testing.",
        timeline="Commission immediately. Result available 3–6 months.",
    )
    gates.append(g3)
    gate_n += 1

    # GATE 4 — DS to 38-48% for pyrolysis (if product-led strategy chosen)
    pyr_viable_at_current = feed_ds >= 38.0
    if not pyr_viable_at_current:
        g4 = StepGate(
            gate_number=gate_n,
            gate_name="DS% Uplift Gate (Pyrolysis Threshold)",
            gate_condition=(
                "Achieve DS% ≥ 38–48% through THP + filter press (maximum preconditioning). "
                "Pyrolysis energy neutrality requires 42–48% DS for digested sludge "
                "at GCV 10–12 MJ/kgDS."
            ),
            current_status="BLOCKED",
            what_is_blocked=[
                "Pyrolysis as energy-neutral operation",
                "Pyrolysis biochar as primary revenue source",
                "ITS pyrolysis without significant external energy input",
            ],
            what_becomes_possible=[
                "Pyrolysis passes the drying feasibility gate (FAIL → PASS)",
                "Biochar production at 22–40% DS yield (temperature dependent)",
                "Carbon credit revenue from stable biochar (R50 > 0.55 at 600°C+)",
                "ITS configuration: pyrolysis + secondary oxidation → Level 3 PFAS",
            ],
            investment_required=(
                "THP + filter press to 38% DS: $40–70M combined. "
                "This is the critical path to product-led end-state."
            ),
            timeline="24–48 months. After Gate 2 confirmed and PFAS characterised.",
        )
        gates.append(g4)
        gate_n += 1

    # GATE 5 — Thermal CAPEX commitment
    g5 = StepGate(
        gate_number=gate_n,
        gate_name="Thermal CAPEX Commitment Gate",
        gate_condition=(
            "All prior gates passed: DS% confirmed at scale, PFAS characterised, "
            "product market or disposal route confirmed, hub site selected and "
            "planning pathway assessed."
        ),
        current_status="BLOCKED",
        what_is_blocked=["Thermal plant construction"],
        what_becomes_possible=[
            "Incineration: 90–94% mass elimination, validated PFAS destruction, P-recovery from ash",
            "Pyrolysis (ITS): 22–40% biochar yield, Level 3 PFAS, carbon credit revenue",
            "System transition complete — plant is a feedstock producer only",
        ],
        investment_required=(
            "Incineration: $120–220M (±30%). Pyrolysis (ITS): $60–100M. "
            "Off-site hub: shared capital — own share depends on consortium structure."
        ),
        timeline="Year 4–8 depending on preconditioning timeline and procurement.",
    )
    gates.append(g5)

    return gates


# ---------------------------------------------------------------------------
# DECISION REGISTER BUILDERS
# ---------------------------------------------------------------------------

def _decide_now(feed_ds, pfas_st, ds_tpd, inv) -> list:
    decisions = []
    if feed_ds < 20.0:
        decisions.append(
            "Install mechanical dewatering (centrifuge trains). "
            "This is the prerequisite for every option. Without it, no thermal pathway is available."
        )
    if pfas_st == "unknown":
        decisions.append(
            "Commission PFAS characterisation across all sludge streams. "
            "This single result determines which pathways remain open."
        )
    if pfas_st == "confirmed":
        decisions.append(
            "Begin incineration procurement immediately. "
            "PFAS is confirmed — incineration is mandatory, not a preference."
        )
    decisions.append(
        "Optimise existing AD and CHP to maximum rated output. "
        "This is immediately bankable and builds the energy infrastructure for future drying."
    )
    if ds_tpd >= 50.0:
        decisions.append(
            "Begin off-site hub site identification. "
            "Planning consent for a thermal facility takes 2–4 years — start the clock now."
        )
    return decisions


def _decide_next(feed_ds, pc, pfas_st) -> list:
    decisions = []
    if feed_ds < 30.0 and pc.any_scenario_reaches_28pct:
        decisions.append(
            "Commission THP feasibility study (18 months). "
            "THP + filter press is the critical path to 32–38% DS and thermal pathway viability."
        )
        decisions.append(
            "Pilot filter press at largest site to confirm achievable DS% at operating scale."
        )
    if pfas_st in ("unknown", "negative"):
        decisions.append(
            "Commission ITS vendor shortlist: identify pyrolysis/gasification vendors "
            "offering secondary oxidation at ≥850°C as standard configuration."
        )
    decisions.append(
        "Conduct off-site hub feasibility study: logistics, CAPEX sharing, "
        "industrial zone planning, transport cost modelling."
    )
    return decisions


def _decide_later(feed_ds, pfas_st) -> list:
    decisions = []
    decisions.append(
        "Thermal technology selection (ITS pyrolysis vs incineration): "
        "decide after PFAS result, DS% confirmed at scale, and product market assessed."
    )
    decisions.append(
        "Thermal CAPEX commitment ($60–220M): "
        "only when all gate conditions are met and detailed feasibility complete."
    )
    if pfas_st != "confirmed":
        decisions.append(
            "Pyrolysis temperature strategy (energy-led vs product-led vs compliance): "
            "decide at commissioning when market conditions and PFAS status are confirmed."
        )
    return decisions
