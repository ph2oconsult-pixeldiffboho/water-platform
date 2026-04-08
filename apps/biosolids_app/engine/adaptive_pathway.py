"""
Adaptive Pathway Stack Engine.
Builds a time-phased 4-stage pathway sequence that evolves as triggers fire.
Models: current state → next trigger → next upgrade → long-term end state.

Stage sequence:
  Stage 1: Stabilisation (AD / none)
  Stage 2: Enhancement   (THP / none)
  Stage 3: Volume reduction (drying / none)
  Stage 4: Final treatment (thermal / land / compost)

Each time phase shows:
  - Active stages
  - Performance (VSR, cake DS, energy position)
  - What breaks at the end of this phase
  - What triggers the next step

ph2o Consulting — BioPoint v1
"""

from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# DATACLASSES
# ---------------------------------------------------------------------------

@dataclass
class PathwayStage:
    """A single active stage in the pathway stack."""
    stage_number: int = 0
    stage_name: str = ""            # "STABILISATION" | "ENHANCEMENT" | "DRYING" | "FINAL"
    technology: str = ""            # e.g. "MAD 30d HRT", "THP + MAD", "Thermal drying"
    status: str = ""                # "ACTIVE" | "PENDING" | "NOT_REQUIRED" | "FUTURE"
    performance_note: str = ""
    affinity: str = ""              # From SludgeCharacter — ESSENTIAL / BENEFICIAL / OPTIONAL


@dataclass
class PathwayPhase:
    """A time-bounded phase of the adaptive pathway."""
    phase_id: str = ""              # "CURRENT" | "NEXT" | "MEDIUM" | "ENDSTATE"
    label: str = ""                 # e.g. "Current state (0–3 yr)"
    horizon_years: str = ""         # e.g. "0–3" | "3–8" | "8–15" | "15+"
    stages: list = field(default_factory=list)          # List[PathwayStage]
    active_technology_stack: str = "" # Human-readable stack e.g. "MAD → Dewatering → Land"

    # Performance at this phase
    vsr_pct: float = 0.0
    cake_ds_pct: float = 0.0
    energy_position: str = ""       # "SURPLUS" | "NEUTRAL" | "DEFICIT"
    logistics_burden: str = ""
    disposal_cost_band: str = ""

    # What breaks / what triggers next phase
    breaking_point: str = ""        # What deteriorates at end of this phase
    trigger_event: str = ""         # What fires the transition
    trigger_years: Optional[float] = None  # Estimated years to trigger

    # Cost signal (qualitative)
    capex_signal: str = ""          # "NONE" | "LOW" | "MEDIUM" | "HIGH" | "VERY_HIGH"
    opex_trend: str = ""            # "STABLE" | "RISING" | "FALLING"

    phase_narrative: str = ""


@dataclass
class AdaptivePathway:
    """Full adaptive pathway — four phases from current to end state."""
    current:   Optional[PathwayPhase] = None
    next_step: Optional[PathwayPhase] = None
    medium:    Optional[PathwayPhase] = None
    end_state: Optional[PathwayPhase] = None

    # Summary
    total_phases: int = 4
    pathway_label: str = ""         # e.g. "MAD → THP → Thermal drying → Incineration"
    pathway_logic: str = ""         # Why this sequence was selected
    constraint_type: str = ""       # Primary constraint driving the pathway

    # Key outputs for UI
    what_works_now: str = ""
    what_breaks_next: str = ""
    what_triggers_change: str = ""
    what_to_do_then: str = ""


# ---------------------------------------------------------------------------
# MAIN ENGINE
# ---------------------------------------------------------------------------

def build_adaptive_pathway(
    pathway_result,
    production_result,
    logistics_result,
    trigger_assessment,
    sludge_character=None,
    constraint_classification=None,
) -> AdaptivePathway:
    """
    Build time-phased adaptive pathway from engine outputs.
    """
    inputs = pathway_result.inputs
    mad    = pathway_result.mad_outputs
    thp    = pathway_result.thp_delta
    eb     = pathway_result.energy_balance
    hb     = pathway_result.heat_balance
    pfas   = pathway_result.pfas_constraint
    drying = pathway_result.drying_result
    thermal = pathway_result.thermal_result
    prod   = production_result
    log    = logistics_result
    ta     = trigger_assessment
    cc     = constraint_classification

    stab   = inputs.stabilisation.stabilisation if inputs else "NONE"
    ctx    = inputs.context if inputs else None
    drying_route  = ctx.drying_route  if ctx else "NONE"
    thermal_route = ctx.thermal_route if ctx else "NONE"
    pfas_closed   = pfas and pfas.route_status == "CLOSED"
    primary_ct    = cc.primary.constraint_type if cc else "MASS"

    # -----------------------------------------------------------------------
    # PHASE 1 — CURRENT STATE
    # -----------------------------------------------------------------------
    current = _build_current_phase(
        stab, mad, thp, eb, hb, drying, thermal, log, ta, pfas_closed
    )

    # -----------------------------------------------------------------------
    # PHASE 2 — NEXT STEP (triggered by nearest active/approaching trigger)
    # -----------------------------------------------------------------------
    next_step = _build_next_phase(
        stab, mad, thp, eb, hb, log, ta, pfas_closed, primary_ct, prod
    )

    # -----------------------------------------------------------------------
    # PHASE 3 — MEDIUM TERM
    # -----------------------------------------------------------------------
    medium = _build_medium_phase(
        stab, mad, thp, drying_route, thermal_route, pfas_closed, primary_ct, prod, log
    )

    # -----------------------------------------------------------------------
    # PHASE 4 — END STATE
    # -----------------------------------------------------------------------
    end_state = _build_end_state(pfas_closed, primary_ct, thermal_route, prod)

    # -----------------------------------------------------------------------
    # PATHWAY SUMMARY
    # -----------------------------------------------------------------------
    pathway_label = _build_pathway_label(stab, thp, drying_route, thermal_route, pfas_closed)
    pathway_logic = _build_pathway_logic(primary_ct, pfas_closed, stab, mad)

    what_works_now     = current.phase_narrative
    what_breaks_next   = current.breaking_point
    what_triggers      = current.trigger_event
    what_to_do_then    = next_step.phase_narrative if next_step else "No immediate change required."

    return AdaptivePathway(
        current=current,
        next_step=next_step,
        medium=medium,
        end_state=end_state,
        total_phases=4,
        pathway_label=pathway_label,
        pathway_logic=pathway_logic,
        constraint_type=primary_ct,
        what_works_now=what_works_now,
        what_breaks_next=what_breaks_next,
        what_triggers_change=what_triggers,
        what_to_do_then=what_to_do_then,
    )


# ---------------------------------------------------------------------------
# PHASE BUILDERS
# ---------------------------------------------------------------------------

def _build_current_phase(stab, mad, thp, eb, hb, drying, thermal,
                          log, ta, pfas_closed) -> PathwayPhase:
    # Build active stage list
    stages = []

    # Stage 1
    if stab == "NONE":
        stages.append(PathwayStage(1, "Stabilisation", "None — raw sludge", "ACTIVE",
                                   "No VS reduction, no biogas, no energy recovery.", "ESSENTIAL"))
    elif stab == "MAD":
        vsr = mad.vsr_pct if mad else 0
        stages.append(PathwayStage(1, "Stabilisation", f"MAD {mad.hrt_days:.0f}d HRT" if mad else "MAD",
                                   "ACTIVE", f"VSR {vsr:.0f}%", "ESSENTIAL"))
    else:  # MAD_THP
        vsr = mad.vsr_pct if mad else 0
        hrt = mad.hrt_days if mad else 0
        stages.append(PathwayStage(1, "Stabilisation", f"THP + MAD {hrt:.0f}d HRT",
                                   "ACTIVE", f"VSR {vsr:.0f}%", "ESSENTIAL"))
        stages.append(PathwayStage(2, "Enhancement", "THP", "ACTIVE",
                                   f"+{thp.delta_vsr_pct:.0f}pp VSR, +{thp.delta_cake_ds_pct:.0f}pp DS" if thp else "",
                                   "BENEFICIAL"))

    # Stage 3: Drying
    if drying:
        stages.append(PathwayStage(3, "Volume reduction", f"{drying.drying_route.title()} drying",
                                   "ACTIVE", f"{drying.cake_ds_in_pct:.0f}% → {drying.cake_ds_out_pct:.0f}% DS",
                                   "BENEFICIAL"))
    else:
        stages.append(PathwayStage(3, "Volume reduction", "None", "NOT_REQUIRED",
                                   "Dewatered cake direct to disposal.", "OPTIONAL"))

    # Stage 4: Final treatment
    if thermal:
        stages.append(PathwayStage(4, "Final treatment", thermal.route.title(),
                                   "ACTIVE" if thermal.ds_adequate else "PENDING",
                                   "Viable" if thermal.route_viable else
                                   f"Not viable — DS gap {thermal.ds_gap_pp:.0f}pp",
                                   "ESSENTIAL" if pfas_closed else "BENEFICIAL"))
    else:
        stages.append(PathwayStage(4, "Final treatment", "Land application",
                                   "ACTIVE", "Class B (or better) pathway.", "OPTIONAL"))

    # Performance
    vsr    = mad.vsr_pct if mad else 0.0
    ds     = mad.cake_ds_pct if mad else 0.0
    e_pos  = ("SURPLUS" if eb and eb.energy_self_sufficient else
              "DEFICIT" if eb and not eb.energy_self_sufficient else "NEUTRAL")
    log_b  = log.handling_complexity if log else "MODERATE"
    disp   = log.disposal_cost_band if log else "MEDIUM"

    # Breaking point
    bp, trigger, trigger_yrs = _current_breaking_point(ta, mad, stab, pfas_closed, log)

    # Narrative
    stack = _stack_label(stab, thp, drying, thermal)
    narrative = (
        f"Current configuration: {stack}. "
        + (f"VSR {vsr:.0f}%, cake DS {ds:.0f}%. " if mad else "No stabilisation. ")
        + (f"Energy {'self-sufficient' if e_pos == 'SURPLUS' else 'importing from grid'}. " if eb else "")
        + (f"Logistics: {log_b.lower()} complexity, {log.truck_loads_per_day:.1f} loads/day." if log else "")
    )

    return PathwayPhase(
        phase_id="CURRENT", label="Current State",
        horizon_years="Now",
        stages=stages,
        active_technology_stack=stack,
        vsr_pct=vsr, cake_ds_pct=ds,
        energy_position=e_pos,
        logistics_burden=log_b,
        disposal_cost_band=disp,
        breaking_point=bp,
        trigger_event=trigger,
        trigger_years=trigger_yrs,
        capex_signal="NONE",
        opex_trend="RISING" if pfas_closed or disp in ("HIGH","VERY_HIGH") else "STABLE",
        phase_narrative=narrative,
    )


def _build_next_phase(stab, mad, thp, eb, hb, log, ta,
                       pfas_closed, primary_ct, prod) -> PathwayPhase:
    """Next step — driven by nearest trigger."""
    nearest = ta.nearest_trigger_name if ta else ""
    yrs     = ta.nearest_trigger_years if ta else None
    horizon = f"0–{int(yrs)+1} yr" if yrs is not None else "Near-term"

    # What technology gets added at this step?
    stages = []
    if stab == "NONE":
        action = "Implement MAD"
        stack  = "MAD → Dewatering → Land application"
        vsr_next = 45.0
        ds_next  = 22.0
        ep_next  = "SURPLUS"
        capex    = "HIGH"
        narrative = (
            "Implement mesophilic anaerobic digestion. "
            "This is the minimum viable step — delivers Class B stabilisation, "
            "biogas for energy recovery, and enables land application."
        )
        bp = "Digester capacity will be consumed by growth — THP or volume expansion triggered."
        trigger = "Effective HRT drops below 20d as volume grows."

    elif stab == "MAD" and not (thp and thp.applied):
        # THP is the logical next step
        vsr_now  = mad.vsr_pct if mad else 45.0
        ds_now   = mad.cake_ds_pct if mad else 22.0
        action = "Add THP upstream of existing MAD"
        stack  = "THP + MAD → Dewatering → Land application"
        vsr_next = min(vsr_now + 10.0, 68.0)
        ds_next  = ds_now + 6.0
        ep_next  = "SURPLUS"
        capex    = "HIGH"
        narrative = (
            f"Add THP pre-treatment to existing MAD. "
            f"VSR improves from {vsr_now:.0f}% to ~{vsr_next:.0f}%. "
            f"Cake DS improves by ~6pp. "
            f"HRT can be reduced — effective digester capacity increases without new tanks. "
            f"Biogas uplift improves energy position."
        )
        bp = ("Disposal route becomes binding — PFAS or cost escalation forces route change."
              if pfas_closed else "Volume growth will eventually require further drying or route change.")
        trigger = "PFAS regulatory tightening or disposal cost threshold." if pfas_closed else \
                  "Disposal cost doubles or land market saturation."

    elif pfas_closed and log:
        # PFAS closed → thermal route is the next forced step
        action = "Add thermal drying + commission thermal disposal"
        stack  = "THP + MAD → Thermal drying → Incineration"
        vsr_next = mad.vsr_pct if mad else 55.0
        ds_next  = 90.0
        ep_next  = "SURPLUS"
        capex    = "VERY_HIGH"
        narrative = (
            "PFAS has closed land application — thermal pathway must be commissioned. "
            "Thermal drying to 90%+ DS, then incineration. "
            "Full PFAS destruction at incineration temperatures. "
            "Disposal market dependency eliminated."
        )
        bp = "End state reached — thermal route eliminates route risk."
        trigger = "Capital procurement and permitting — typically 5–8 years lead time."

    else:
        # Optimise existing — drying or route upgrade
        vsr_next = mad.vsr_pct if mad else 50.0
        ds_next  = (mad.cake_ds_pct + 8.0) if mad else 30.0
        action   = "Add solar or thermal drying"
        stack    = "MAD/THP + MAD → Drying → Land application"
        ep_next  = "SURPLUS"
        capex    = "MEDIUM"
        narrative = (
            "Add drying to increase cake DS and reduce transport burden. "
            "This extends the viability of the land application route "
            "and reduces logistics cost before a full thermal route is required."
        )
        bp = "Disposal route risk or volume growth eventually forces full thermal pathway."
        trigger = "Disposal cost escalation or PFAS regulatory change."

    stages.append(PathwayStage(0, "Action", action, "PENDING",
                               f"Triggered by: {nearest}", "ESSENTIAL"))

    return PathwayPhase(
        phase_id="NEXT", label=f"Next Step",
        horizon_years=horizon,
        stages=stages,
        active_technology_stack=stack,
        vsr_pct=vsr_next, cake_ds_pct=ds_next,
        energy_position=ep_next,
        logistics_burden="LOW" if ds_next > 30 else "MODERATE",
        disposal_cost_band="LOW" if not pfas_closed else "VERY_HIGH",
        breaking_point=bp,
        trigger_event=trigger,
        trigger_years=None,
        capex_signal=capex,
        opex_trend="FALLING",
        phase_narrative=narrative,
    )


def _build_medium_phase(stab, mad, thp, drying_route, thermal_route,
                         pfas_closed, primary_ct, prod, log) -> PathwayPhase:
    """Medium term — 5–15yr — typically the full stack."""
    vsr   = (mad.vsr_pct if mad else 0) + (10 if not (thp and thp.applied) else 0)
    vsr   = min(vsr, 68.0)
    ds    = 28.0 if not (thp and thp.applied) else 30.0
    gf    = prod.growth_factor if prod else 1.0

    if pfas_closed:
        stack   = "THP + MAD → Thermal drying → Incineration"
        disp    = "VERY_HIGH"
        ep      = "SURPLUS"
        narrative = (
            "Full thermal pathway operational. PFAS destruction achieved. "
            "Disposal market dependency eliminated. "
            f"System handles {prod.future_ts_t_yr:,.0f} t DS/yr ({gf:.1f}× current volume)." if prod else ""
        )
        bp = "Incineration capacity — if volume growth continues, second line or upsizing required."
        trigger = f"Volume growth beyond thermal capacity: ~{prod.current_ts_t_yr * 1.8:,.0f} t DS/yr." if prod else "Volume growth."
    elif primary_ct == "LOGISTICS":
        stack   = "MAD + THP → Thermal drying → Land application / compost"
        disp    = "LOW"
        ep      = "SURPLUS"
        ds      = 75.0
        narrative = (
            "Thermal drying reduces wet cake volume significantly. "
            "Transport burden falls from current levels. "
            "Dry product (pellets) has broader market options — compost, fertiliser, fuel."
        )
        bp = "Market acceptance of dried product — volume or quality rejection risk."
        trigger = "Loss of offtake market or regulatory change on land application."
    else:
        stack   = "THP + MAD → Solar/thermal drying → Land application"
        disp    = "LOW"
        ep      = "SURPLUS"
        narrative = (
            "Full stack operational: THP + MAD with drying. "
            "High VSR, improved cake DS, reduced transport burden. "
            "Land application viable with Class B or Class A stabilisation class."
        )
        bp = "Disposal route risk from PFAS tightening or agronomic land availability."
        trigger = "PFAS regulatory change or disposal cost escalation above threshold."

    return PathwayPhase(
        phase_id="MEDIUM", label="Medium Term",
        horizon_years="5–15 yr",
        stages=[],
        active_technology_stack=stack,
        vsr_pct=vsr, cake_ds_pct=ds,
        energy_position=ep,
        logistics_burden="LOW",
        disposal_cost_band=disp,
        breaking_point=bp,
        trigger_event=trigger,
        trigger_years=None,
        capex_signal="NONE",   # Capital spent in NEXT phase
        opex_trend="STABLE",
        phase_narrative=narrative,
    )


def _build_end_state(pfas_closed, primary_ct, thermal_route, prod) -> PathwayPhase:
    """Long-term end state — 15+ years."""
    if pfas_closed or thermal_route != "NONE":
        stack = "THP + MAD → Thermal drying → Incineration / Gasification"
        narrative = (
            "Thermal end-state: maximum VS destruction, full PFAS compliance, "
            "zero disposal market dependency. Energy recovery from incineration/gasification "
            "offsets operational cost. Ash residual managed to landfill or construction use."
        )
        disp = "VERY_HIGH"
        vsr  = 65.0
        ds   = 92.0
    elif primary_ct == "LOGISTICS":
        stack = "THP + MAD → Thermal drying → Pellet product / energy"
        narrative = (
            "Dried pellet product as the primary output — "
            "soil amendment, co-fuel, or agricultural use. "
            "Transport burden minimised. Circular economy end-state."
        )
        disp = "LOW"
        vsr  = 62.0
        ds   = 90.0
    else:
        stack = "THP + MAD → Solar/thermal drying → Land application / Class A reuse"
        narrative = (
            "Class A stabilised biosolids as the primary output. "
            "Highest-value land application pathway with lowest regulatory risk. "
            "Energy recovery from CHP covers process demand with export surplus."
        )
        disp = "LOW"
        vsr  = 62.0
        ds   = 35.0

    return PathwayPhase(
        phase_id="ENDSTATE", label="Long-Term End State",
        horizon_years="15+ yr",
        stages=[],
        active_technology_stack=stack,
        vsr_pct=vsr, cake_ds_pct=ds,
        energy_position="SURPLUS",
        logistics_burden="LOW",
        disposal_cost_band=disp,
        breaking_point="Long-term population growth — further capacity expansion.",
        trigger_event="Volume growth beyond end-state design capacity.",
        trigger_years=None,
        capex_signal="NONE",
        opex_trend="STABLE",
        phase_narrative=narrative,
    )


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def _current_breaking_point(ta, mad, stab, pfas_closed, log):
    """Identify what breaks first in the current configuration."""
    if ta and ta.active_triggers:
        t = ta.active_triggers[0]
        return t.description, t.escalation_action, None
    if ta and ta.approaching_triggers:
        t = ta.approaching_triggers[0]
        return t.description, t.escalation_action, t.years_to_trigger
    if stab == "NONE":
        return ("No stabilisation — disposal cost and regulatory pressure will force action.",
                "Implement MAD immediately.", None)
    if pfas_closed:
        return ("PFAS has closed land application — thermal route required.",
                "Commission thermal drying and incineration.", None)
    if mad and mad.vsr_pct < 40:
        return (f"VSR of {mad.vsr_pct:.0f}% is sub-optimal — biogas and mass reduction limited.",
                "Add THP or extend HRT.", 5.0)
    if log and log.disposal_cost_band in ("HIGH", "VERY_HIGH"):
        return ("Disposal cost is already high — escalation will force route review.",
                "Evaluate alternative disposal routes.", 3.0)
    return ("Current configuration is functional — monitor growth and disposal cost.",
            "Proactive review in 3–5 years.", 5.0)


def _stack_label(stab, thp, drying, thermal) -> str:
    parts = []
    if stab == "NONE":
        parts.append("No stabilisation")
    elif stab == "MAD_THP" or (thp and thp.applied):
        parts.append("THP + MAD")
    else:
        parts.append("MAD")
    parts.append("Dewatering")
    if drying:
        parts.append(f"{drying.drying_route.title()} drying")
    if thermal:
        parts.append(thermal.route.title())
    else:
        parts.append("Land application")
    return " → ".join(parts)


def _build_pathway_label(stab, thp, drying_route, thermal_route, pfas_closed) -> str:
    parts = []
    if stab == "NONE":
        parts.append("No stabilisation")
    elif stab == "MAD_THP" or (thp and thp and thp.applied):
        parts.append("THP + MAD")
    else:
        parts.append("MAD")
    if drying_route != "NONE":
        parts.append(f"{drying_route.title()} drying")
    if thermal_route != "NONE":
        parts.append(thermal_route.title())
    else:
        parts.append("Land application")
    return " → ".join(parts)


def _build_pathway_logic(primary_ct, pfas_closed, stab, mad) -> str:
    if pfas_closed:
        return (
            "Thermal pathway is mandatory — PFAS has closed land application. "
            "Pathway is driven by regulatory compliance, not cost optimisation."
        )
    if primary_ct == "MASS":
        return (
            "Mass constraint drives pathway selection — maximum VS reduction "
            "and mass transformation before disposal. Digestion and THP are priority stages."
        )
    if primary_ct == "DISPOSAL":
        return (
            "Disposal constraint drives pathway — route security is the primary objective. "
            "Thermal route development reduces dependency on land application market."
        )
    if primary_ct == "LOGISTICS":
        return (
            "Logistics constraint drives pathway — increasing cake DS is the highest-leverage action. "
            "Drying is a priority stage to reduce transport burden."
        )
    return (
        "Cost constraint drives pathway — energy recovery and disposal cost reduction "
        "are the primary objectives. Biogas maximisation and route optimisation are priority."
    )
