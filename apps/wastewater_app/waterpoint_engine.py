"""
apps/wastewater_app/waterpoint_engine.py

WaterPoint Intelligence Engine.

Reads WaterPointInput, produces WaterPointResult.
Pure functions — no Streamlit, no I/O, no side effects.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from apps.wastewater_app.waterpoint_adapter import WaterPointInput


# ── Result dataclasses ────────────────────────────────────────────────────────

@dataclass
class SystemStress:
    state:              str   # Stable / Tightening / Fragile / Failure Risk
    proximity_percent:  float  # % of capacity consumed by current load
    primary_constraint: str   # which domain is tightest
    rate:               str   # Stable / Tightening / Accelerating
    time_to_breach:     str   # soft planning range, e.g. "3–5 years"
    confidence:         str   # High / Medium / Low
    rationale:          str   # one sentence


@dataclass
class FailureMode:
    title:       str
    description: str
    severity:    str   # Low / Medium / High


@dataclass
class FailureModes:
    items:            List[FailureMode] = field(default_factory=list)
    overall_severity: str = "Low"


@dataclass
class DecisionLayer:
    short_term:      List[str] = field(default_factory=list)
    medium_term:     List[str] = field(default_factory=list)
    long_term:       List[str] = field(default_factory=list)
    capex_range:     str = ""
    risk_if_no_action: str = ""


@dataclass
class ComplianceRisk:
    compliance_risk:    str   # Low / Medium / High
    likely_breach_type: str
    regulatory_exposure: str
    reputational_risk:  str


@dataclass
class WaterPointResult:
    system_stress:   SystemStress
    failure_modes:   FailureModes
    decision_layer:  DecisionLayer
    compliance_risk: ComplianceRisk


# ── Thresholds ────────────────────────────────────────────────────────────────

_STABLE      = 0.25   # remaining capacity fraction above this → Stable
_TIGHTENING  = 0.10   # between _TIGHTENING and _STABLE → Tightening
_FRAGILE     = 0.05   # between _FRAGILE and _TIGHTENING → Fragile
# below _FRAGILE → Failure Risk

# Hydraulic: SOR benchmark (m/hr) at design flow
_SOR_WARN_M_HR  = 1.0
_SOR_LIMIT_M_HR = 1.5


# ── Public API ────────────────────────────────────────────────────────────────

def analyse(wp: WaterPointInput) -> WaterPointResult:
    """
    Run the full WaterPoint analysis pipeline.
    Returns WaterPointResult.  Never raises.
    """
    try:
        stress  = calculate_system_stress(wp)
    except Exception:
        stress  = _fallback_stress()
    try:
        failure = detect_failure_modes(wp, stress)
    except Exception:
        failure = FailureModes()
    try:
        decision = generate_decision_layer(wp, stress, failure)
    except Exception:
        decision = DecisionLayer(risk_if_no_action="Analysis incomplete — insufficient data.")
    try:
        compliance = assess_compliance_risk(wp, stress, failure)
    except Exception:
        compliance = _fallback_compliance()

    return WaterPointResult(
        system_stress   = stress,
        failure_modes   = failure,
        decision_layer  = decision,
        compliance_risk = compliance,
    )


# ── 1. System stress ──────────────────────────────────────────────────────────

def calculate_system_stress(wp: WaterPointInput) -> SystemStress:
    """
    Evaluate the most-constrained capacity domain and characterise system stress.
    """
    domains: List[Tuple[str, float, str]] = []   # (domain_name, utilisation_fraction, unit)
    missing_count = len(wp.missing_fields)

    # ── Hydraulic domain ─────────────────────────────────────────────────
    # Not included as a stress domain: the scenario model sizes the plant to the
    # design flow, so the ratio always equals 1.0 — not a stress signal.
    # Hydraulic risk at peak is captured by the Clarifier SOR domain below.

    # ── Aeration / oxygen demand ──────────────────────────────────────────
    if wp.o2_demand_kg_day and wp.aeration_kwh_day:
        # Installed blower kW → max O₂ delivery (kg/d): 1 kW ≈ 1.8 kg O₂/hr standard transfer
        blower_kw = (wp.aeration_kwh_day / 24) * 1.30   # operational → installed
        max_o2    = blower_kw * 1.8 * 24                 # kgO₂/d at standard conditions
        if max_o2 > 0:
            util = wp.o2_demand_kg_day / max_o2
            domains.append(("Aeration capacity", util, f"{wp.o2_demand_kg_day:.0f} kg O₂/d demand"))

    # ── Clarifier loading ─────────────────────────────────────────────────
    if wp.clarifier_area_m2 and wp.peak_flow_mld:
        peak_m3h = wp.peak_flow_mld * 1000 / 24
        sor      = peak_m3h / wp.clarifier_area_m2
        sor_util = sor / _SOR_LIMIT_M_HR
        if wp.technology_code not in ("granular_sludge", "bnr_mbr", "anmbr"):
            # Only include if SOR genuinely exceeds the design limit
            # (exactly at limit is the design point, not a stress signal)
            if sor > _SOR_LIMIT_M_HR:
                domains.append(("Clarifier capacity", sor_util, f"SOR {sor:.2f} m/hr at peak"))

    # ── Solids / biosolids loading ────────────────────────────────────────
    # Omitted from stress domains: the adapter sets solids_kg_d from the same
    # sludge production value as sludge_kgds_day, making the ratio always 1.0.
    # Solids risk is captured instead via the failure mode detector.

    # ── Biological loading (BOD) ──────────────────────────────────────────
    # Omitted: design_capacity.biological_kg_d mirrors current_load.bod_kg_d
    # from the adapter — the ratio is always 1.0. Not a meaningful stress signal.

    # ── Pick most constrained domain ──────────────────────────────────────
    if not domains:
        return _fallback_stress()

    domain_name, max_util, domain_detail = max(domains, key=lambda x: x[1])

    proximity   = round(max_util * 100, 1)
    remaining   = max(0.0, 1.0 - max_util)

    if remaining > _STABLE:
        state = "Stable"
        rate  = "Stable"
        t2b   = "> 5 years"
    elif remaining > _TIGHTENING:
        state = "Tightening"
        rate  = "Tightening"
        t2b   = "3–5 years"
    elif remaining > _FRAGILE:
        state = "Fragile"
        rate  = "Accelerating"
        t2b   = "12–24 months"
    else:
        state = "Failure Risk"
        rate  = "Accelerating"
        t2b   = "< 12 months — action required"

    # Confidence: based on how many domains we could assess and missing_count
    n_domains = len(domains)
    if n_domains >= 3 and missing_count <= 1:
        confidence = "High"
    elif n_domains >= 2 or missing_count <= 3:
        confidence = "Medium"
    else:
        confidence = "Low"

    rationale = _stress_rationale(domain_name, state, wp)

    return SystemStress(
        state              = state,
        proximity_percent  = proximity,
        primary_constraint = f"{domain_name} ({domain_detail})",
        rate               = rate,
        time_to_breach     = t2b,
        confidence         = confidence,
        rationale          = rationale,
    )


def _stress_rationale(domain: str, state: str, wp: WaterPointInput) -> str:
    if state == "Stable":
        return (f"{domain} has adequate headroom under current loading conditions.")
    if state == "Tightening":
        return (f"{domain} is consuming available design capacity — "
                "capacity constraints are likely to materialise within the planning horizon.")
    if state == "Fragile":
        return (f"{domain} is approaching its design limit. "
                "Process exceedances are probable under peak load or growth conditions.")
    return (f"{domain} is at or beyond design limit. "
            "Immediate intervention is required to maintain compliance and service continuity.")


def _fallback_stress() -> SystemStress:
    return SystemStress(
        state="Unknown", proximity_percent=0.0,
        primary_constraint="Insufficient data",
        rate="Unknown", time_to_breach="Not available",
        confidence="Low",
        rationale="Insufficient scenario data to assess system stress.",
    )


# ── 2. Failure modes ──────────────────────────────────────────────────────────

def detect_failure_modes(wp: WaterPointInput, stress: SystemStress) -> FailureModes:
    modes: List[FailureMode] = []

    prox  = stress.proximity_percent
    state = stress.state

    # ── Hydraulic overload — only flag when peak genuinely exceeds design ────
    if wp.peak_flow_mld and wp.design_capacity.hydraulic_mld:
        peak_ratio = wp.peak_flow_mld / wp.design_capacity.hydraulic_mld
        # Threshold: peak > 1.4× design suggests uncontrolled peak beyond diurnal norm
        if peak_ratio > 2.00:   # standard 1.5× peak factor is by design; >2× suggests I/I
            modes.append(FailureMode(
                title       = "Hydraulic overload risk",
                description = (
                    f"Peak flow ({wp.peak_flow_mld:.1f} MLD) is {peak_ratio:.1f}× the average design flow "
                    f"({wp.design_capacity.hydraulic_mld:.1f} MLD). "
                    "I/I ingress or demand growth may exceed hydraulic treatment capacity."
                ),
                severity = "High" if peak_ratio > 1.6 else "Medium",
            ))

    # ── Clarifier overload ────────────────────────────────────────────────
    if wp.clarifier_area_m2 and wp.peak_flow_mld and \
            wp.technology_code not in ("granular_sludge", "bnr_mbr", "anmbr"):
        peak_m3h = wp.peak_flow_mld * 1000 / 24
        sor      = peak_m3h / wp.clarifier_area_m2
        if sor > _SOR_WARN_M_HR:
            modes.append(FailureMode(
                title       = "Clarifier overload",
                description = (
                    f"Secondary clarifier SOR {sor:.2f} m/hr at peak flow exceeds advisory threshold "
                    f"({_SOR_WARN_M_HR} m/hr). Sludge blanket rise and solids carryover probable."
                ),
                severity = "High" if sor > _SOR_LIMIT_M_HR else "Medium",
            ))

    # ── Nitrification instability ─────────────────────────────────────────
    if wp.effluent_nh4_mg_l is not None and wp.nh4_target_mg_l is not None:
        nh4_margin = wp.nh4_target_mg_l - wp.effluent_nh4_mg_l
        if nh4_margin < 0.5:   # < 0.5 mg/L headroom
            modes.append(FailureMode(
                title       = "Nitrification margin — low",
                description = (
                    f"Effluent NH₄ {wp.effluent_nh4_mg_l:.1f} mg/L is within "
                    f"{nh4_margin:.1f} mg/L of licence limit {wp.nh4_target_mg_l:.1f} mg/L. "
                    "Temperature or load variation could trigger exceedance."
                ),
                severity = "High" if nh4_margin <= 0.2 else "Medium",
            ))

    # ── TN compliance risk ────────────────────────────────────────────────
    if wp.effluent_tn_mg_l is not None and wp.tn_target_mg_l is not None:
        tn_margin = wp.tn_target_mg_l - wp.effluent_tn_mg_l
        if 0 < tn_margin < 1.0:   # flag if within 1 mg/L; 0 margin = already at limit
            modes.append(FailureMode(
                title       = "Total nitrogen compliance — marginal",
                description = (
                    f"Effluent TN {wp.effluent_tn_mg_l:.1f} mg/L with only "
                    f"{tn_margin:.1f} mg/L headroom against target {wp.tn_target_mg_l:.1f} mg/L. "
                    "Carbon availability and seasonal SRT variation are key risks."
                ),
                severity = "High" if tn_margin <= 0 else "Medium",
            ))

    # ── TN at exact limit (zero margin) ──────────────────────────────────
    if wp.effluent_tn_mg_l is not None and wp.tn_target_mg_l is not None:
        if wp.effluent_tn_mg_l >= wp.tn_target_mg_l:  # at or exceeding limit
            modes.append(FailureMode(
                title       = "Total nitrogen — at licence limit",
                description = (
                    f"Effluent TN {wp.effluent_tn_mg_l:.1f} mg/L is at the licence limit "
                    f"({wp.tn_target_mg_l:.1f} mg/L) with zero headroom. "
                    "Any load increase or seasonal effect will trigger a breach."
                ),
                severity = "High" if wp.effluent_tn_mg_l > wp.tn_target_mg_l else "Medium",
            ))

    # ── TP compliance risk ────────────────────────────────────────────────
    if wp.effluent_tp_mg_l is not None and wp.tp_target_mg_l is not None:
        if wp.effluent_tp_mg_l > wp.tp_target_mg_l * 1.02:
            modes.append(FailureMode(
                title       = "Phosphorus compliance — not achieved",
                description = (
                    f"Biological P removal ({wp.effluent_tp_mg_l:.2f} mg/L) does not meet "
                    f"target ({wp.tp_target_mg_l:.2f} mg/L). "
                    "Chemical dosing or BioP optimisation required."
                ),
                severity = "High",
            ))

    # ── Aeration energy intensity ─────────────────────────────────────────
    if wp.aeration_kwh_day and wp.average_flow_mld:
        kwh_kl = (wp.aeration_kwh_day / (wp.average_flow_mld * 1000))
        if kwh_kl > 0.25:   # > 0.25 kWh/kL aeration-only is energy-intensive
            modes.append(FailureMode(
                title       = "Aeration energy intensity",
                description = (
                    f"Aeration consumes {kwh_kl:.3f} kWh/kL — above advisory threshold (0.25 kWh/kL). "
                    "Blower control optimisation or process intensification could reduce cost and carbon."
                ),
                severity = "Medium",
            ))

    # ── Biosolids handling ────────────────────────────────────────────────
    if wp.sludge_kgds_day and wp.sludge_kgds_day > 0:
        tds_yr = wp.sludge_kgds_day * 365 / 1000
        if tds_yr > 500:   # > 500 tDS/yr is a meaningful biosolids volume
            modes.append(FailureMode(
                title       = "Biosolids volume — planning required",
                description = (
                    f"Sludge production {tds_yr:.0f} tDS/yr. "
                    "Biosolids strategy, storage adequacy, and disposal pathway should be confirmed."
                ),
                severity = "Low",
            ))

    # ── Fragile / Failure Risk catch-all ──────────────────────────────────
    if state in ("Fragile", "Failure Risk") and not modes:
        modes.append(FailureMode(
            title       = "Process capacity exceedance imminent",
            description = (
                f"System is in '{state}' condition. "
                "Specific failure mode determination requires additional plant data."
            ),
            severity = "High" if state == "Failure Risk" else "Medium",
        ))

    # ── Overall severity ──────────────────────────────────────────────────
    if any(m.severity == "High"   for m in modes):
        overall = "High"
    elif any(m.severity == "Medium" for m in modes):
        overall = "Medium"
    elif modes:
        overall = "Low"
    else:
        overall = "Low"

    return FailureModes(items=modes, overall_severity=overall)


# ── 3. Decision layer ─────────────────────────────────────────────────────────

def generate_decision_layer(
    wp:      WaterPointInput,
    stress:  SystemStress,
    failure: FailureModes,
) -> DecisionLayer:

    state   = stress.state
    tc      = wp.technology_code
    titles  = {m.title for m in failure.items}
    short:  List[str] = []
    medium: List[str] = []
    long:   List[str] = []

    # ── Short-term: process control and operational optimisation ──────────
    short.append("Review and optimise aeration DO setpoints to reduce energy and improve nitrification stability.")
    if "Nitrification" in str(titles):
        short.append("Increase SRT by adjusting WAS rates — protect nitrifier population during cold-weather operations.")
    if "Phosphorus" in str(titles):
        short.append("Implement or optimise ferric chloride dosing for TP polishing — confirm chemical feed rate and injection point.")
    if "Clarifier" in str(titles):
        short.append("Adjust RAS rate and sludge blanket depth ahead of peak flow events.")
    if state in ("Fragile", "Failure Risk"):
        short.append("Activate emergency flow management protocols and notify regulator if design threshold is breached.")

    # ── Medium-term: debottlenecking and retrofit ─────────────────────────
    if "Clarifier" in str(titles) or "Hydraulic" in str(titles):
        medium.append("Evaluate secondary clarifier expansion or parallel clarifier to restore SOR headroom.")
    if "Nitrification" in str(titles) or "nitrogen" in str(titles).lower():
        medium.append("Consider IFAS media addition to existing aerobic zone to increase biological volume and nitrification capacity without new civil works.")
    if "aeration" in tc.lower() or "Aeration" in str(titles):
        medium.append("Upgrade or augment blower capacity and install dissolved oxygen control loops.")
    if "Phosphorus" in str(titles):
        medium.append("Assess BioP optimisation: anaerobic zone configuration, VFA availability, and recycle stream management.")
    if state in ("Tightening", "Fragile", "Failure Risk"):
        medium.append("Commission concept-level capacity expansion study with 20-year demand projections.")

    # ── Long-term: technology upgrade and major capital ───────────────────
    if tc in ("bnr", "ifas_mbbr"):
        long.append("Evaluate full process intensification — MABR retrofit or IFAS upgrade — for improved N removal at current footprint.")
    if tc == "granular_sludge":
        long.append("Plan FBT / balancing volume review to manage peak flow: confirm 4-reactor configuration is sized for growth.")
    long.append("Develop a 30-year capital investment plan aligned with population growth and tightening licence conditions.")
    long.append("Assess future water reuse potential — advanced treatment train to meet Class A+ requirements.")

    # ── Capex range (soft planning estimate) ─────────────────────────────
    capex_str = ""
    if wp.outputs.capex_estimate:
        base = wp.outputs.capex_estimate
        if state == "Stable":
            capex_str = f"Incremental capital requirement estimated $0.3–1.0M for process optimisation and minor upgrades."
        elif state == "Tightening":
            capex_str = f"Medium-term debottlenecking investment likely in range $1–5M (technology and site-dependent)."
        else:
            capex_str = f"Significant capital investment required — concept-stage planning range $5–20M+ depending on technology selection."

    # ── Risk if no action ─────────────────────────────────────────────────
    if state == "Stable":
        risk_msg = "Licence compliance is maintained under current conditions. Proactive monitoring is recommended to detect early deterioration."
    elif state == "Tightening":
        risk_msg = "Compliance breach probability increases materially within the planning horizon if current trajectory continues without intervention."
    elif state == "Fragile":
        risk_msg = "Exceedance of licence limits is probable under peak load or minor operational disruption. Regulator engagement recommended."
    else:
        risk_msg = "Current conditions present an elevated risk of immediate licence breach and operational failure. Urgent action is required."

    return DecisionLayer(
        short_term       = short,
        medium_term      = medium,
        long_term        = long,
        capex_range      = capex_str,
        risk_if_no_action = risk_msg,
    )


# ── 4. Compliance risk ────────────────────────────────────────────────────────

def assess_compliance_risk(
    wp:      WaterPointInput,
    stress:  SystemStress,
    failure: FailureModes,
) -> ComplianceRisk:

    state  = stress.state
    titles = {m.title for m in failure.items}
    sev    = failure.overall_severity

    # ── Overall compliance risk ───────────────────────────────────────────
    if state in ("Failure Risk",) or sev == "High":
        risk_level = "High"
    elif state in ("Fragile",) or sev == "Medium":
        risk_level = "Medium"
    else:
        risk_level = "Low"

    # ── Likely breach type ────────────────────────────────────────────────
    breach_parts = []
    if "nitrogen" in str(titles).lower() or "Nitrification" in str(titles):
        breach_parts.append("TN / ammonia exceedance")
    if "Phosphorus" in str(titles):
        breach_parts.append("TP licence breach")
    if "Clarifier" in str(titles) or "Hydraulic" in str(titles):
        breach_parts.append("suspended solids carryover at peak flow")
    if not breach_parts:
        breach_parts = ["process performance deterioration under growth or peak load"]
    likely_breach = "; ".join(breach_parts)

    # ── Regulatory exposure ───────────────────────────────────────────────
    if risk_level == "High":
        reg_exp = (
            "Non-compliant event with regulator notification obligation. "
            "Formal investigation and show-cause requirement likely. "
            "Proactive engagement with Environment Agency recommended before breach occurs."
        )
    elif risk_level == "Medium":
        reg_exp = (
            "Elevated risk of compliance margin exceedance during peak load or seasonal conditions. "
            "Prepare corrective action plan and establish self-monitoring triggers."
        )
    else:
        reg_exp = (
            "Current performance is within licence limits with adequate headroom. "
            "Maintain standard compliance monitoring programme."
        )

    # ── Reputational risk ─────────────────────────────────────────────────
    if risk_level == "High":
        rep_risk = (
            "Public and political risk elevated. Licence exceedances are reportable and discoverable. "
            "Proactive communications strategy and community engagement plan recommended."
        )
    elif risk_level == "Medium":
        rep_risk = (
            "Moderate reputational exposure if exceedances occur. "
            "Demonstrates system is operating near design limits — may attract regulator scrutiny."
        )
    else:
        rep_risk = "Low reputational exposure under current conditions."

    return ComplianceRisk(
        compliance_risk     = risk_level,
        likely_breach_type  = likely_breach,
        regulatory_exposure = reg_exp,
        reputational_risk   = rep_risk,
    )


def _fallback_compliance() -> ComplianceRisk:
    return ComplianceRisk(
        compliance_risk     = "Unknown",
        likely_breach_type  = "Not available",
        regulatory_exposure = "Insufficient data to assess regulatory exposure.",
        reputational_risk   = "Not available",
    )
