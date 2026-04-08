"""
Trigger Engine.
Evaluates time-based triggers that force pathway evolution:
  1. Disposal cost escalation
  2. Regulatory pressure (PFAS tightening, class requirements)
  3. Capacity limits (digester, dewatering, transport)
  4. Contract renewal / infrastructure age

Each trigger has:
  - Current status (INACTIVE / APPROACHING / TRIGGERED / BREACHED)
  - Time horizon (years to trigger)
  - Escalation pathway (what the system must do when triggered)

ph2o Consulting — BioPoint v1
"""

from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# DATACLASSES
# ---------------------------------------------------------------------------

@dataclass
class Trigger:
    """Single trigger event."""
    trigger_id: str = ""
    name: str = ""
    category: str = ""              # "DISPOSAL" | "REGULATORY" | "CAPACITY" | "CONTRACT"
    status: str = "INACTIVE"        # "INACTIVE" | "APPROACHING" | "TRIGGERED" | "BREACHED"
    years_to_trigger: Optional[float] = None   # None = already triggered
    description: str = ""
    evidence: list = field(default_factory=list)
    escalation_action: str = ""     # What must happen when triggered
    escalation_urgency: str = ""    # "IMMEDIATE" | "NEAR-TERM" | "PLANNED"
    severity: str = "LOW"           # "LOW" | "MODERATE" | "HIGH" | "CRITICAL"


@dataclass
class TriggerAssessment:
    """Full trigger evaluation output."""
    triggers: list = field(default_factory=list)   # All Trigger objects

    # Rolled-up
    active_triggers: list = field(default_factory=list)    # TRIGGERED or BREACHED
    approaching_triggers: list = field(default_factory=list)  # APPROACHING
    critical_triggers: list = field(default_factory=list)  # severity == CRITICAL

    nearest_trigger_years: Optional[float] = None
    nearest_trigger_name: str = ""
    system_stability: str = ""      # "STABLE" | "APPROACHING_LIMIT" | "AT_LIMIT" | "BEYOND_LIMIT"
    overall_urgency: str = ""       # "MONITOR" | "PLAN" | "ACT" | "IMMEDIATE"
    trigger_narrative: str = ""


# ---------------------------------------------------------------------------
# MAIN ENGINE
# ---------------------------------------------------------------------------

def evaluate_triggers(
    pathway_result,
    production_result,
    logistics_result,
    sludge_character=None,
    contract_renewal_years: Optional[float] = None,
    infrastructure_age_years: Optional[float] = None,
    disposal_cost_escalation_pct_yr: float = 5.0,   # Assumed disposal cost escalation
) -> TriggerAssessment:
    """
    Evaluate all four trigger categories and return ranked assessment.
    """
    triggers = []

    triggers += _disposal_triggers(
        pathway_result, logistics_result, production_result,
        disposal_cost_escalation_pct_yr
    )
    triggers += _regulatory_triggers(pathway_result, production_result)
    triggers += _capacity_triggers(pathway_result, production_result, logistics_result)
    triggers += _contract_triggers(
        contract_renewal_years, infrastructure_age_years, pathway_result
    )

    # Classify
    active     = [t for t in triggers if t.status in ("TRIGGERED", "BREACHED")]
    approaching = [t for t in triggers if t.status == "APPROACHING"]
    critical   = [t for t in triggers if t.severity == "CRITICAL"]

    # Nearest trigger
    timed = [t for t in triggers if t.years_to_trigger is not None]
    nearest = min(timed, key=lambda t: t.years_to_trigger) if timed else None
    breached = [t for t in triggers if t.status == "BREACHED"]
    if breached:
        nearest_yr = 0.0
        nearest_name = breached[0].name
    elif nearest:
        nearest_yr = nearest.years_to_trigger
        nearest_name = nearest.name
    else:
        nearest_yr = None
        nearest_name = "None identified"

    # System stability
    if breached or len(active) >= 2:
        stability = "BEYOND_LIMIT"
        urgency = "IMMEDIATE"
    elif active:
        stability = "AT_LIMIT"
        urgency = "ACT"
    elif approaching:
        stability = "APPROACHING_LIMIT"
        urgency = "PLAN"
    else:
        stability = "STABLE"
        urgency = "MONITOR"

    narrative = _build_trigger_narrative(
        active, approaching, nearest_yr, nearest_name, stability
    )

    return TriggerAssessment(
        triggers=triggers,
        active_triggers=active,
        approaching_triggers=approaching,
        critical_triggers=critical,
        nearest_trigger_years=nearest_yr,
        nearest_trigger_name=nearest_name,
        system_stability=stability,
        overall_urgency=urgency,
        trigger_narrative=narrative,
    )


# ---------------------------------------------------------------------------
# TRIGGER EVALUATORS
# ---------------------------------------------------------------------------

def _disposal_triggers(pathway_result, logistics_result, production_result,
                        escalation_pct_yr: float) -> list:
    triggers = []
    pfas = pathway_result.pfas_constraint
    mad  = pathway_result.mad_outputs

    # T1: Disposal cost escalation
    if logistics_result:
        band = logistics_result.disposal_cost_band
        gf   = production_result.growth_factor if production_result else 1.0
        # Model cost doubling time under escalation + volume growth
        # Combined escalation rate: disposal_cost_pct + volume_growth
        vol_growth_pct = (production_result.growth_rate_pct_yr
                          if production_result else 2.0)
        combined_rate = escalation_pct_yr + vol_growth_pct
        # Years until cost doubles: rule of 72
        years_to_double = 72.0 / combined_rate if combined_rate > 0 else 99.0

        if band in ("HIGH", "VERY_HIGH"):
            status = "TRIGGERED"
            yrs = None
            sev = "HIGH"
            evidence = [
                f"Disposal cost band already {band}.",
                f"At {combined_rate:.0f}%/yr combined escalation, costs double in {years_to_double:.0f} years.",
            ]
        elif band == "MEDIUM" and years_to_double < 10:
            status = "APPROACHING"
            yrs = years_to_double * 0.6
            sev = "MODERATE"
            evidence = [f"Disposal cost escalating — trigger within ~{yrs:.0f} years."]
        else:
            status = "INACTIVE"
            yrs = years_to_double
            sev = "LOW"
            evidence = [f"Disposal cost manageable — monitor escalation rate."]

        triggers.append(Trigger(
            trigger_id="DISP_COST",
            name="Disposal cost escalation",
            category="DISPOSAL",
            status=status,
            years_to_trigger=yrs,
            description=f"Disposal costs escalating at ~{escalation_pct_yr:.0f}%/yr above CPI, "
                        f"compounded by {vol_growth_pct:.1f}%/yr volume growth.",
            evidence=evidence,
            escalation_action="Review disposal route — thermal or beneficial reuse reduces cost exposure.",
            escalation_urgency="NEAR-TERM" if status == "TRIGGERED" else "PLANNED",
            severity=sev,
        ))

    # T2: Land application market saturation
    # When cake volume grows, agronomic offtake may not scale proportionally
    if logistics_result and production_result:
        gf = production_result.growth_factor
        loads_now = logistics_result.truck_loads_per_day
        loads_future = logistics_result.future_truck_loads_per_day
        disposal_route = logistics_result.disposal_route

        if "LAND" in disposal_route.upper() and gf > 1.4:
            yrs = production_result.projection_years * 0.5  # Mid-point of growth horizon
            triggers.append(Trigger(
                trigger_id="DISP_LAND_SAT",
                name="Land application offtake saturation",
                category="DISPOSAL",
                status="APPROACHING",
                years_to_trigger=yrs,
                description="Growing biosolids volume may exceed available agronomic land within planning horizon.",
                evidence=[
                    f"Transport burden grows {loads_now:.1f} → {loads_future:.1f} loads/day.",
                    f"Growth factor: {gf:.2f}× over {production_result.projection_years} years.",
                    "Land application offtake is seasonally constrained — peak volume risk.",
                ],
                escalation_action="Develop secondary disposal route (compost or thermal) before land market saturates.",
                escalation_urgency="PLANNED",
                severity="MODERATE",
            ))

    return triggers


def _regulatory_triggers(pathway_result, production_result) -> list:
    triggers = []
    pfas = pathway_result.pfas_constraint
    stab = pathway_result.inputs.stabilisation.stabilisation if pathway_result.inputs else "NONE"
    mad  = pathway_result.mad_outputs

    # T3: PFAS regulatory tightening
    if pfas and pfas.flagged:
        if pfas.route_status == "CLOSED":
            triggers.append(Trigger(
                trigger_id="REG_PFAS_CLOSED",
                name="PFAS land application closed",
                category="REGULATORY",
                status="BREACHED",
                years_to_trigger=None,
                description="PFAS has already closed the land application route. Regulatory breach risk is current.",
                evidence=[
                    f"Risk tier: {pfas.risk_tier}.",
                    "Thermal destruction is the only compliant disposal pathway.",
                ],
                escalation_action="Commission incineration or equivalent thermal destruction — no deferral.",
                escalation_urgency="IMMEDIATE",
                severity="CRITICAL",
            ))
        elif pfas.route_status == "CONSTRAINED":
            triggers.append(Trigger(
                trigger_id="REG_PFAS_CONSTRAIN",
                name="PFAS regulatory tightening",
                category="REGULATORY",
                status="APPROACHING",
                years_to_trigger=3.0,   # Estimated: regulations typically move 2-5yr
                description="PFAS regulations are tightening globally. Current CONSTRAINED status "
                            "likely to move to CLOSED within 2–5 years in most jurisdictions.",
                evidence=[
                    "PFAS flagged at CONSTRAINED — land application under monitoring.",
                    "International trend: threshold limits tightening (US EPA, EU, AU).",
                ],
                escalation_action="Plan thermal route now — lead time for incineration is 5–8 years.",
                escalation_urgency="NEAR-TERM",
                severity="HIGH",
            ))

    # T4: Stabilisation class gap
    if stab == "NONE":
        triggers.append(Trigger(
            trigger_id="REG_CLASS_GAP",
            name="Stabilisation class not met",
            category="REGULATORY",
            status="BREACHED",
            years_to_trigger=None,
            description="No stabilisation in place — Class B minimum is not met. "
                        "Land application is precluded in most jurisdictions.",
            evidence=[
                "No anaerobic digestion or equivalent stabilisation process.",
                "Raw sludge disposal — regulatory and odour risk is current.",
            ],
            escalation_action="Implement MAD as minimum — Class B required before any land application.",
            escalation_urgency="IMMEDIATE",
            severity="CRITICAL",
        ))
    elif mad and mad.vsr_pct < 38.0 and not mad.thp_applied:
        triggers.append(Trigger(
            trigger_id="REG_CLASS_LOW",
            name="VSR approaching Class A threshold",
            category="REGULATORY",
            status="APPROACHING",
            years_to_trigger=5.0,
            description=f"VSR of {mad.vsr_pct:.0f}% is below the 38% Class A indicative threshold. "
                        f"Regulatory tightening may require Class A in future.",
            evidence=[
                f"Current VSR: {mad.vsr_pct:.0f}%.",
                "Class A typically requires VSR > 38% + pathogen reduction beyond Class B.",
                "THP pre-treatment is the standard Class A pathway.",
            ],
            escalation_action="Evaluate THP addition to achieve Class A stabilisation.",
            escalation_urgency="PLANNED",
            severity="MODERATE",
        ))

    return triggers


def _capacity_triggers(pathway_result, production_result, logistics_result) -> list:
    triggers = []
    hb   = pathway_result.heat_balance
    eb   = pathway_result.energy_balance
    mad  = pathway_result.mad_outputs
    prod = production_result

    # T5: Digester capacity
    if mad and hb and prod:
        # Volume growth will eventually exceed digester HRT
        # At growth factor G, HRT effectively reduces to HRT/G
        gf = prod.growth_factor
        effective_hrt_future = mad.hrt_days / gf if gf > 0 else mad.hrt_days
        if effective_hrt_future < 15.0:
            status = "TRIGGERED"
            yrs = None
            sev = "HIGH"
            evidence = [
                f"Growth factor {gf:.2f}× reduces effective HRT from {mad.hrt_days:.0f}d to {effective_hrt_future:.0f}d.",
                "HRT below 15d: VSR and biogas yield will deteriorate significantly.",
            ]
        elif effective_hrt_future < 20.0:
            status = "APPROACHING"
            # Estimate years to breach: when volume doubles enough to drop HRT below 18d
            yrs_to_breach = (
                (mad.hrt_days / 18.0 - 1) / (prod.growth_rate_pct_yr / 100.0)
                if prod.growth_rate_pct_yr > 0 else 99.0
            )
            yrs = max(0.5, yrs_to_breach)
            sev = "MODERATE"
            evidence = [
                f"At {prod.growth_rate_pct_yr:.1f}%/yr growth, effective HRT reaches 18d in ~{yrs:.0f} years.",
                "Digester capacity expansion or THP addition (HRT reduction) required.",
            ]
        else:
            status = "INACTIVE"
            yrs = prod.projection_years * 0.7
            sev = "LOW"
            evidence = [f"Digester capacity adequate for planning horizon at {gf:.2f}× growth."]

        triggers.append(Trigger(
            trigger_id="CAP_DIGESTER",
            name="Digester capacity limit",
            category="CAPACITY",
            status=status,
            years_to_trigger=yrs,
            description="Sludge volume growth will reduce effective HRT below viable threshold.",
            evidence=evidence,
            escalation_action="Add digester volume OR add THP (enables HRT reduction without new tanks).",
            escalation_urgency="NEAR-TERM" if status == "TRIGGERED" else "PLANNED",
            severity=sev,
        ))

    # T6: Dewatering / transport capacity
    if logistics_result and prod:
        loads_now = logistics_result.truck_loads_per_day
        loads_future = logistics_result.future_truck_loads_per_day
        gf = prod.growth_factor

        if loads_future > 10:
            status = "APPROACHING"
            yrs = prod.projection_years * 0.6
            sev = "HIGH"
            evidence = [
                f"Transport grows to {loads_future:.1f} loads/day over {prod.projection_years} years.",
                "Fleet availability and haul slot constraints become binding above 10 loads/day.",
            ]
            triggers.append(Trigger(
                trigger_id="CAP_TRANSPORT",
                name="Transport capacity ceiling",
                category="CAPACITY",
                status=status,
                years_to_trigger=yrs,
                description="Growing volume will strain transport logistics beyond practical capacity.",
                evidence=evidence,
                escalation_action="Thermal drying to reduce wet mass and truck frequency. "
                                  "Or centralisation to co-digestion hub.",
                escalation_urgency="PLANNED",
                severity=sev,
            ))

    # T7: CHP / energy capacity
    if eb:
        if not eb.energy_self_sufficient:
            triggers.append(Trigger(
                trigger_id="CAP_ENERGY",
                name="Energy self-sufficiency gap",
                category="CAPACITY",
                status="TRIGGERED",
                years_to_trigger=None,
                description=f"Plant imports {abs(eb.net_electrical_export_kWh_d):,.0f} kWh/d — "
                            f"CHP output insufficient to cover process demand.",
                evidence=[
                    f"Net electrical position: {eb.net_electrical_export_kWh_d:+,.0f} kWh/d.",
                    f"Self-sufficiency: {eb.electrical_self_sufficiency_pct:.0f}%.",
                ],
                escalation_action="Increase VS load to digester (blend in PS), improve VSR, or reduce process demand.",
                escalation_urgency="PLANNED",
                severity="MODERATE",
            ))

    return triggers


def _contract_triggers(contract_renewal_years, infrastructure_age_years,
                        pathway_result) -> list:
    triggers = []

    # T8: Contract renewal window
    if contract_renewal_years is not None:
        if contract_renewal_years <= 0:
            status, sev = "BREACHED", "HIGH"
            yrs = None
            desc = "Disposal contract has expired — renegotiation or route change required now."
        elif contract_renewal_years <= 2:
            status, sev = "TRIGGERED", "HIGH"
            yrs = contract_renewal_years
            desc = f"Disposal contract renews in {contract_renewal_years:.0f} years — "  \
                   f"negotiate now with full pathway context."
        elif contract_renewal_years <= 5:
            status, sev = "APPROACHING", "MODERATE"
            yrs = contract_renewal_years
            desc = f"Contract renewal in {contract_renewal_years:.0f} years — "  \
                   f"begin market review and pathway evaluation."
        else:
            status, sev = "INACTIVE", "LOW"
            yrs = contract_renewal_years
            desc = "Contract renewal outside near-term planning window."

        triggers.append(Trigger(
            trigger_id="CONTR_RENEWAL",
            name="Disposal contract renewal",
            category="CONTRACT",
            status=status,
            years_to_trigger=yrs,
            description=desc,
            evidence=[f"Contract renewal in {contract_renewal_years:.1f} years."],
            escalation_action="Use renewal window to negotiate improved terms or switch to alternative route.",
            escalation_urgency="NEAR-TERM" if status in ("TRIGGERED", "BREACHED") else "PLANNED",
            severity=sev,
        ))

    # T9: Infrastructure age / end-of-life
    if infrastructure_age_years is not None:
        remaining = max(0, 25 - infrastructure_age_years)   # Typical 25yr design life
        if remaining <= 0:
            status, sev = "BREACHED", "CRITICAL"
            yrs = None
            desc = "Infrastructure has exceeded design life — major refurbishment or replacement required."
        elif remaining <= 3:
            status, sev = "TRIGGERED", "HIGH"
            yrs = remaining
            desc = f"Infrastructure reaches end of design life in {remaining:.0f} years."
        elif remaining <= 7:
            status, sev = "APPROACHING", "MODERATE"
            yrs = remaining
            desc = f"Infrastructure end-of-life in {remaining:.0f} years — plan replacement."
        else:
            status, sev = "INACTIVE", "LOW"
            yrs = remaining
            desc = "Infrastructure within design life."

        triggers.append(Trigger(
            trigger_id="CONTR_EOL",
            name="Infrastructure end-of-life",
            category="CONTRACT",
            status=status,
            years_to_trigger=yrs,
            description=desc,
            evidence=[
                f"Infrastructure age: {infrastructure_age_years:.0f} years.",
                f"Estimated remaining life: {remaining:.0f} years (25yr design basis).",
            ],
            escalation_action="Plan replacement capital aligned with pathway upgrade — "
                              "avoid like-for-like replacement if technology pathway is changing.",
            escalation_urgency="IMMEDIATE" if status == "BREACHED" else
                               ("NEAR-TERM" if status == "TRIGGERED" else "PLANNED"),
            severity=sev,
        ))

    return triggers


# ---------------------------------------------------------------------------
# NARRATIVE
# ---------------------------------------------------------------------------

def _build_trigger_narrative(active, approaching, nearest_yr,
                              nearest_name, stability) -> str:
    parts = []
    if stability == "BEYOND_LIMIT":
        parts.append(
            f"{len(active)} trigger(s) already breached — immediate action required."
        )
    elif stability == "AT_LIMIT":
        names = ", ".join(t.name for t in active[:2])
        parts.append(f"System at limit: {names} triggered.")
    elif stability == "APPROACHING_LIMIT":
        if nearest_yr is not None:
            parts.append(
                f"Nearest trigger: '{nearest_name}' in ~{nearest_yr:.0f} years. "
                f"{len(approaching)} trigger(s) approaching."
            )
    else:
        parts.append("System stable — no triggers active or approaching within planning horizon.")

    return " ".join(parts)
