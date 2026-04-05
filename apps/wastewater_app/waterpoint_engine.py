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

# Wet weather scenario type constants (imported lazily to avoid circular import)
_SCENARIO_AWWF = "Average Wet Weather Flow (AWWF)"
_SCENARIO_PWWF = "Peak Wet Weather Flow (PWWF)"
_SCENARIO_DWP  = "Dry Weather Peak (Diurnal)"


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
    Routes to Nereda-specific model when wp.nereda_enabled == True.
    Returns WaterPointResult.  Never raises.
    """
    # ── Nereda pathway ────────────────────────────────────────────────
    if getattr(wp, "nereda_enabled", False):
        return _analyse_nereda(wp)

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


def _analyse_nereda(wp: WaterPointInput) -> WaterPointResult:
    """Nereda AGS analysis pipeline — replaces clarifier logic with FBT + cycle domains."""
    try:
        from apps.wastewater_app.waterpoint_nereda import (
            calculate_nereda_stress, detect_nereda_failure_modes,
            generate_nereda_decisions, assess_nereda_compliance,
            NeredaFailureMode,
        )

        nereda   = calculate_nereda_stress(wp)
        n_modes  = detect_nereda_failure_modes(wp, nereda)
        n_dec    = generate_nereda_decisions(wp, nereda, n_modes)
        n_comp   = assess_nereda_compliance(wp, nereda, n_modes)

        # Convert NeredaFailureMode list → FailureModes dataclass
        fm_items = [FailureMode(title=m.title, description=m.description,
                                severity=m.severity) for m in n_modes]
        if any(m.severity == "High"   for m in fm_items):  overall = "High"
        elif any(m.severity == "Medium" for m in fm_items): overall = "Medium"
        elif fm_items:                                       overall = "Low"
        else:                                                overall = "Low"
        failure = FailureModes(items=fm_items, overall_severity=overall)

        stress = SystemStress(
            state              = nereda.state,
            proximity_percent  = nereda.proximity,
            primary_constraint = nereda.primary_constraint,
            rate               = nereda.rate,
            time_to_breach     = nereda.t2b,
            confidence         = nereda.confidence,
            rationale          = nereda.rationale,
        )

        decision = DecisionLayer(
            short_term        = n_dec["short_term"],
            medium_term       = n_dec["medium_term"],
            long_term         = n_dec["long_term"],
            capex_range       = n_dec["capex_range"],
            risk_if_no_action = n_dec["risk_if_no_action"],
        )

        compliance = ComplianceRisk(
            compliance_risk     = n_comp["compliance_risk"],
            likely_breach_type  = n_comp["likely_breach_type"],
            regulatory_exposure = n_comp["regulatory_exposure"],
            reputational_risk   = n_comp["reputational_risk"],
        )

        return WaterPointResult(
            system_stress   = stress,
            failure_modes   = failure,
            decision_layer  = decision,
            compliance_risk = compliance,
        )

    except Exception as _nereda_exc:
        # Fallback: run standard pipeline if Nereda model fails
        _fb_stress = _fallback_stress()
        _fb_stress = SystemStress(
            state="Unknown", proximity_percent=0., primary_constraint="Nereda model error",
            rate="Unknown", time_to_breach="Not available", confidence="Low",
            rationale=f"Nereda analysis failed: {_nereda_exc}",
        )
        return WaterPointResult(
            system_stress   = _fb_stress,
            failure_modes   = FailureModes(),
            decision_layer  = DecisionLayer(risk_if_no_action="Nereda analysis error."),
            compliance_risk = _fallback_compliance(),
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

    # ── Wet weather hydraulic domain ─────────────────────────────────────
    # Only meaningful when flow_scenario is active (not a circular ratio like DWA).
    fst = wp.flow_scenario_type or ""
    hydraulic_pre_stress = False   # set inside wet weather block; read in escalation section
    flow_ratio           = 1.0     # default for dry weather
    if fst in (_SCENARIO_AWWF, _SCENARIO_PWWF, _SCENARIO_DWP):
        adj_flow = wp.flow_adjusted_flow_mld or 0.0
        base_flow = wp.average_flow_mld or 0.0
        if adj_flow > 0 and base_flow > 0:
            flow_ratio = adj_flow / base_flow
            # Map flow_ratio to utilisation: ≤1.5 = Normal, 1.5–2.0 = Elevated, >2.0 = Overload
            # Normalise so that ratio=2.0 → util=1.0 (capacity boundary)
            ww_util = min(flow_ratio / 2.0, 1.2)   # cap at 1.2 so it can show Failure Risk

            # ── Pre-stress narrative band (1.3–1.5) ──────────────────
            # Does NOT activate the stress domain or change state.
            # Carries a soft warning into the rationale / escalation note only.
            hydraulic_pre_stress = (1.3 < flow_ratio <= 1.5)

            if flow_ratio > 1.5:   # only add as stress domain if genuinely elevated
                band = ("Elevated Hydraulic Stress" if flow_ratio <= 2.0
                        else "Hydraulic Overload")
                domains.append((
                    f"Wet weather hydraulic loading ({band})",
                    ww_util,
                    f"{adj_flow:.1f} MLD ({flow_ratio:.1f}× DWA)",
                ))
        else:
            hydraulic_pre_stress = False
            flow_ratio = 1.0

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

    rationale = _stress_rationale(domain_name, state, wp,
                                      hydraulic_pre_stress=hydraulic_pre_stress,
                                      flow_ratio=flow_ratio)

    # ── Wet weather state escalation ──────────────────────────────────────
    fst = wp.flow_scenario_type or ""
    _escalation_note = ""
    # overflow_flag forces Failure Risk regardless of domains
    if wp.flow_overflow_flag:
        state = "Failure Risk"
        rate  = "Accelerating"
        t2b   = "< 12 months — action required"
        _escalation_note = " [Overflow flag: Failure Risk forced]"
    elif fst == _SCENARIO_PWWF and state not in ("Failure Risk",):
        # PWWF biases state up one level
        _escalation_map = {
            "Stable":       ("Tightening", "Tightening",   "3–5 years"),
            "Tightening":   ("Fragile",    "Accelerating", "12–24 months"),
            "Fragile":      ("Failure Risk","Accelerating","< 12 months — action required"),
        }
        if state in _escalation_map:
            state, rate, t2b = _escalation_map[state]
            _escalation_note = " [PWWF: state escalated one level]"
    # AWWF without overflow: soften time-to-breach to chronic planning language
    if fst == _SCENARIO_AWWF and not wp.flow_overflow_flag and not wp.flow_bypass_risk:
        ww_dur_w4 = wp.flow_wet_weather_duration_hr or 24.0
        if ww_dur_w4 > 48:
            t2b = "Sustained resilience pressure — planning horizon 6–24 months"
        else:
            t2b = "Chronic planning condition — address within 1–3 year capital programme"

    # clarifier_stress_flag adds to rationale but not state (already captured in SOR domain)
    if wp.flow_clarifier_stress and _escalation_note == "":
        _escalation_note = " [Clarifier SOR elevated under wet weather flow]"

    if _escalation_note:
        rationale = rationale.rstrip(".") + "." + _escalation_note

    # W8: Add exceedance gradient detail when flow_ratio is extreme
    _constraint_label = f"{domain_name} ({domain_detail})"
    if flow_ratio >= 3.0 and fst in (_SCENARIO_AWWF, _SCENARIO_PWWF):
        _exceedance_pct = round((flow_ratio - 1.0) * 100)
        if flow_ratio >= 5.0:
            _band = "Catastrophic exceedance"
        elif flow_ratio >= 3.0:
            _band = "Extreme exceedance"
        else:
            _band = ""
        if _band:
            _constraint_label += f" | {_band}: {_exceedance_pct}% above design average"

    return SystemStress(
        state              = state,
        proximity_percent  = proximity,
        primary_constraint = _constraint_label,
        rate               = rate,
        time_to_breach     = t2b,
        confidence         = confidence,
        rationale          = rationale,
    )


def _stress_rationale(domain: str, state: str, wp: WaterPointInput,
                      hydraulic_pre_stress: bool = False,
                      flow_ratio: float = 1.0) -> str:
    """
    Build the rationale sentence for system stress.
    AWWF → sustained biological/process language.
    PWWF → acute hydraulic/compliance language.
    Pre-stress band (1.3–1.5) appends a soft hydraulic note without changing state.
    Dry weather → generic domain-based language (unchanged).
    """
    fst = (wp.flow_scenario_type or "") if wp else ""

    # AWWF — sustained process stress framing
    if fst == _SCENARIO_AWWF:
        if state == "Stable":
            base = ("Sustained wet weather loading is within current process capacity. "
                    "Monitor biological performance and clarifier stability throughout the event.")
        elif state == "Tightening":
            base = ("Sustained wet weather loading is reducing biological and clarifier resilience. "
                    "Extended elevated flow is increasing process stress over the event duration.")
        elif state == "Fragile":
            base = ("Prolonged wet weather conditions are approaching process limits. "
                    "Nitrification stability and SRT maintenance are at risk over the event duration.")
        else:
            base = ("Sustained AWWF loading has exceeded process resilience. "
                    "Biological performance degradation and nutrient compliance drift are probable.")

    # PWWF — acute hydraulic/compliance framing
    elif fst == _SCENARIO_PWWF:
        if state == "Stable":
            base = ("Peak wet weather flow is within hydraulic capacity for this event. "
                    "Clarifier and biological process monitoring required during the event.")
        elif state == "Tightening":
            base = ("Peak wet weather conditions are elevating acute hydraulic and compliance risk. "
                    "Short-duration extreme flow is creating bypass and washout exposure.")
        elif state == "Fragile":
            base = ("PWWF conditions are driving acute process stress. "
                    "Bypass, washout and solids carryover risk are present — pre-event preparation is critical.")
        else:
            base = ("Peak wet weather conditions represent an acute hydraulic and compliance event. "
                    "Overflow, bypass and licence exceedance risk are immediate.")

    # Dry weather or DWP — generic domain-based language (unchanged from original)
    else:
        if state == "Stable":
            base = f"{domain} has adequate headroom under current loading conditions."
        elif state == "Tightening":
            base = (f"{domain} is consuming available design capacity — "
                    "capacity constraints are likely to materialise within the planning horizon.")
        elif state == "Fragile":
            base = (f"{domain} is approaching its design limit. "
                    "Process exceedances are probable under peak load or growth conditions.")
        else:
            base = (f"{domain} is at or beyond design limit. "
                    "Immediate intervention is required to maintain compliance and service continuity.")

    # Append pre-stress soft note (1.3–1.5 band only, does not change state)
    if hydraulic_pre_stress and fst not in (_SCENARIO_AWWF, _SCENARIO_PWWF):
        # For dry weather / DWP scenarios in pre-stress band
        base = (base.rstrip(".") +
                ". Flow is approaching the dry-weather hydraulic design peak envelope — "
                "wet weather I/I ingress is the principal risk to monitor.")
    elif hydraulic_pre_stress and fst in (_SCENARIO_AWWF, _SCENARIO_PWWF):
        # For AWWF/PWWF scenarios: the main text already covers this
        base = (base.rstrip(".") +
                ". Wet weather flow is elevated but not yet in overload territory — "
                "event management and monitoring remain the priority.")

    return base


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
            # Distinguish design operating point from genuine overload
            _is_dry_wx_baseline = not (wp.flow_scenario_type or "")
            # W-NEW-2: also treat DWP at its exact design factor as design-point
            _is_dwp_at_design = False
            if wp.flow_scenario_type == _SCENARIO_DWP and wp.average_flow_mld:
                _adj = wp.flow_adjusted_flow_mld or 0.0
                _dwp_ratio = _adj / wp.average_flow_mld if wp.average_flow_mld else 0.0
                # Within 5% of design peak factor (e.g. 1.5 ± 0.075)
                _is_dwp_at_design = (0.95 <= _dwp_ratio <= 1.05 * 1.5 + 0.01)
            _at_design_point = ((_is_dry_wx_baseline or _is_dwp_at_design) and
                                _SOR_WARN_M_HR < sor <= _SOR_LIMIT_M_HR)
            if _at_design_point:
                modes.append(FailureMode(
                    title       = "Clarifier at design operating point",
                    description = (
                        f"Secondary clarifier SOR {sor:.2f} m/hr at peak flow is at the "
                        f"design operating point (advisory threshold {_SOR_WARN_M_HR} m/hr). "
                        "No immediate action required — monitor under growth or wet weather conditions."
                    ),
                    severity = "Low",
                ))
            else:
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
        if wp.effluent_tn_mg_l > wp.tn_target_mg_l:  # genuinely above limit
            modes.append(FailureMode(
                title       = "Total nitrogen — licence exceedance",
                description = (
                    f"Effluent TN {wp.effluent_tn_mg_l:.1f} mg/L exceeds the licence limit "
                    f"({wp.tn_target_mg_l:.1f} mg/L). Immediate process investigation required."
                ),
                severity = "High",
            ))
        elif wp.effluent_tn_mg_l == wp.tn_target_mg_l:  # exactly at limit
            modes.append(FailureMode(
                title       = "Total nitrogen — limited compliance margin",
                description = (
                    f"Effluent TN {wp.effluent_tn_mg_l:.1f} mg/L is at the regulatory limit "
                    f"({wp.tn_target_mg_l:.1f} mg/L) — at regulatory limit by design. "
                    "Any load increase or seasonal effect may trigger a breach."
                ),
                severity = "Medium",
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

    # ── Wet weather failure modes ─────────────────────────────────────────
    fst = wp.flow_scenario_type or ""
    adj_flow  = wp.flow_adjusted_flow_mld or 0.0
    base_flow = wp.average_flow_mld or 1.0
    flow_ratio = adj_flow / base_flow if base_flow > 0 else 1.0

    if fst in (_SCENARIO_AWWF, _SCENARIO_PWWF, _SCENARIO_DWP):

        # Hydraulic overload / bypass risk
        if wp.flow_overflow_flag or flow_ratio > 2.0:
            modes.append(FailureMode(
                title       = "Hydraulic overload / bypass risk",
                description = (
                    f"Adjusted flow {adj_flow:.1f} MLD ({flow_ratio:.1f}× DWA) exceeds hydraulic capacity. "
                    "Bypass event or uncontrolled overflow is probable. "
                    "Emergency flow management protocol required."
                ),
                severity = "High",
            ))

        # Clarifier washout risk
        if wp.flow_clarifier_stress or flow_ratio > 1.8:
            modes.append(FailureMode(
                title       = "Clarifier washout risk",
                description = (
                    f"High hydraulic loading ({flow_ratio:.1f}× DWA) creates risk of sludge blanket rise "
                    "and activated sludge washout from secondary clarifiers. "
                    "RAS rate and blanket depth must be pre-adjusted before the event."
                ),
                severity = "High" if wp.flow_clarifier_stress else "Medium",
            ))

        # Sludge blanket instability
        if flow_ratio > 1.5:
            modes.append(FailureMode(
                title       = "Sludge blanket instability",
                description = (
                    f"Rapid hydraulic loading increase ({flow_ratio:.1f}× DWA) compresses sludge blanket. "
                    "Secondary clarifier solids carryover risk is elevated. "
                    "Increase WAS rate before event to reduce MLSS and improve settling."
                ),
                severity = "Medium" if flow_ratio < 2.0 else "High",
            ))

        # First flush shock loading
        if wp.flow_first_flush_enabled:
            ff_hr = wp.flow_first_flush_duration_hr or 2.0
            modes.append(FailureMode(
                title       = "First flush shock loading",
                description = (
                    f"First flush phase ({ff_hr:.0f}h) delivers elevated pollutant concentrations "
                    "before dilution dominates. BOD and TSS loads are transiently higher than steady-state wet weather. "
                    "Biological process and clarifier performance may be transiently impaired."
                ),
                severity = "Medium",
            ))

        # Wet weather duration — long events increase biological impact
        ww_dur = wp.flow_wet_weather_duration_hr or 0.0
        if ww_dur > 24 and fst == _SCENARIO_AWWF:
            modes.append(FailureMode(
                title       = "Extended wet weather biological impact",
                description = (
                    f"AWWF event duration {ww_dur:.0f}h exceeds 24 hours. "
                    "Sustained dilution reduces biological loading but protracts hydraulic stress. "
                    "Monitor SRT closely — extended high flows may cause inadvertent sludge loss."
                ),
                severity = "Medium",
            ))

        # SRT compression risk — materially different for AWWF > 48h
        if ww_dur > 48 and fst == _SCENARIO_AWWF:
            # Determine severity: High if biological stress is already elevated
            srt_sev = "High" if any(m.severity == "High" for m in modes
                                     if "nitrogen" in m.title.lower()
                                     or "nitrification" in m.title.lower()) else "Medium"
            modes.append(FailureMode(
                title       = "SRT compression risk",
                description = (
                    f"Sustained wet weather flow over {ww_dur:.0f}h may increase sludge losses "
                    "and compress SRT below nitrification resilience thresholds. "
                    "Multi-day AWWF events require active WAS management to prevent "
                    "biological process deterioration."
                ),
                severity = srt_sev,
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


    # ── Scenario-specific severity emphasis ───────────────────────────
    # AWWF: promote biological/sustained modes; PWWF: promote acute/hydraulic modes.
    fst_fm = wp.flow_scenario_type or ""
    for m in modes:
        if fst_fm == _SCENARIO_AWWF:
            if m.title in ("Extended wet weather biological impact",
                           "Nitrification margin — low",
                           "Total nitrogen compliance — marginal",
                           "Total nitrogen — at licence limit") and m.severity == "Low":
                m.severity = "Medium"
            # AWWF washout risk is lower severity than PWWF (sustained, not acute)
            if m.title == "Clarifier washout risk" and not wp.flow_clarifier_stress:
                m.severity = "Low"
        elif fst_fm == _SCENARIO_PWWF:
            # PWWF: acute hydraulic modes promoted
            if m.title in ("Hydraulic overload / bypass risk",
                           "Clarifier washout risk",
                           "Sludge blanket instability",
                           "First flush shock loading") and m.severity == "Medium":
                m.severity = "High"
            if m.title == "Aeration energy intensity" and m.severity == "Medium":
                m.severity = "Low"

    # Sort: High first, then Medium, then Low
    _sev_order = {"High": 0, "Medium": 1, "Low": 2}
    modes.sort(key=lambda m: _sev_order.get(m.severity, 3))

    # ── Overall severity ──────────────────────────────────────────────────
    if any(m.severity == "High"   for m in modes):
        overall = "High"
    elif any(m.severity == "Medium" for m in modes):
        overall = "Medium"
    elif modes:
        overall = "Low"
    else:
        overall = "Low"

    # First flush increases overall severity by one notch (biological stress weighting)
    if wp.flow_first_flush_enabled and overall == "Medium":
        overall = "High"
    elif wp.flow_first_flush_enabled and overall == "Low" and modes:
        overall = "Medium"

    # ── W-NEW-3: Suppress Low-severity modes when dominated by High-severity ──
    # Run AFTER all severity promotions so High count is final before filtering.
    _high_count_final = sum(1 for m in modes if m.severity == "High")
    if _high_count_final >= 3:
        modes = [m for m in modes if m.severity != "Low"]

    return FailureModes(items=modes, overall_severity=overall)


# ── 3. Decision layer ─────────────────────────────────────────────────────────

def generate_decision_layer(
    wp:      WaterPointInput,
    stress:  SystemStress,
    failure: FailureModes,
) -> DecisionLayer:

    # ── W10: Suppress all generic actions when data is insufficient ───────
    _missing = len(wp.missing_fields) if wp.missing_fields else 0
    _no_flow = not wp.average_flow_mld
    _no_load = not (wp.current_load.bod_kg_d or wp.o2_demand_kg_day)
    _no_cap  = not (wp.clarifier_area_m2 or wp.aeration_kwh_day)
    if stress.state == "Unknown" or (_missing > 4) or (_no_flow and _no_load and _no_cap):
        return DecisionLayer(
            short_term=["Complete plant inputs (flow, influent quality, treatment pathway)"
                        " to activate decision recommendations."],
            medium_term=[], long_term=[],
            capex_range="",
            risk_if_no_action="Insufficient data to assess risk.",
        )

    state   = stress.state
    tc      = wp.technology_code
    titles  = {m.title for m in failure.items}
    short:  List[str] = []
    medium: List[str] = []
    long:   List[str] = []

    # ── Wet weather short-term actions — scenario-specific ───────────────
    fst = wp.flow_scenario_type or ""
    adj_flow  = wp.flow_adjusted_flow_mld or 0.0
    base_flow = wp.average_flow_mld or 1.0
    flow_ratio = adj_flow / base_flow if base_flow > 0 else 1.0

    # ── W6 / W-NEW-5: First flush actions — pre-event or active depending on overflow ─
    if wp.flow_first_flush_enabled and fst in (_SCENARIO_AWWF, _SCENARIO_PWWF):
        if wp.flow_overflow_flag:
            # W-NEW-5: overflow active — use present-tense active-event wording
            short.append(
                "Manage ongoing first flush shock load under active overflow conditions —"
                " confirm coagulant dosing response is active and chemical feed is adequate."
            )
            short.append(
                "Confirm dosing response and solids capture performance"
                " during active overflow / first flush conditions."
            )
            short.append(
                "Stabilise treatment response during current first flush / overflow event —"
                " increase TSS and TP monitoring frequency at influent and effluent."
            )
        else:
            # Pre-event preparation (no confirmed overflow)
            short.append(
                "Pre-dose coagulant / ferric before first flush arrival"
                " to manage shock TSS and TP load — confirm chemical feed rate and injection point."
            )
            short.append(
                "Confirm dosing system availability and chemical inventory before event."
            )
            short.append(
                "Prepare primary treatment assets for elevated solids and phosphorus load"
                " during the first flush phase."
            )
            short.append(
                "Increase influent monitoring frequency for TSS and TP"
                " during the first flush phase."
            )

    if fst == _SCENARIO_AWWF:
        # AWWF: process stability through sustained event
        ww_dur_awwf = wp.flow_wet_weather_duration_hr or 24.0
        short.append(
            f"AWWF ({adj_flow:.1f} MLD, {flow_ratio:.1f}× DWA, {ww_dur_awwf:.0f}h):"
            " monitor aeration DO and nitrification continuously."
            " Sustained biological loading requires proactive process control."
        )
        short.append(
            "Adjust WAS rate to maintain target SRT throughout the event —"
            " sustained high flow can cause inadvertent sludge loss."
        )
        short.append(
            "Monitor secondary clarifier sludge blanket depth at 2-hour intervals."
        )

    elif fst == _SCENARIO_PWWF:
        # PWWF: branch on whether overflow is already active (W9)
        ww_dur_pwwf = wp.flow_wet_weather_duration_hr or 12.0
        if wp.flow_overflow_flag:
            # W9: active incident — no pre-event language
            short.append(
                f"PWWF ACTIVE OVERFLOW — current overflow condition"
                f" ({adj_flow:.1f} MLD, {flow_ratio:.1f}× DWA)."
                " Implement emergency response protocol immediately."
            )
            short.append(
                "Stabilise sludge blanket and manage solids carryover"
                " risk under active overflow conditions."
            )
            short.append(
                "Confirm regulator notification / incident escalation pathway."
                " Notify regulator — wet weather bypass is a notifiable incident."
            )
            short.append(
                "Document bypass duration, flow extent, and receiving environment exposure."
            )
        else:
            # Pre-event preparation (no confirmed overflow)
            short.append(
                f"PWWF STORM MODE — pre-adjust RAS and reduce sludge blanket depth"
                f" before event ({adj_flow:.1f} MLD, {flow_ratio:.1f}× DWA, {ww_dur_pwwf:.0f}h)."
            )
            short.append(
                "Increase WAS rate 12–24 hours before event"
                " to reduce MLSS and maximise clarifier surge capacity."
            )
            if flow_ratio > 2.0:
                short.append(
                    "Prepare overflow pathway for potential activation."
                    " Confirm regulator notification procedure is ready."
                )

    elif fst == _SCENARIO_DWP:
        short.append(
            f"Diurnal peak ({adj_flow:.1f} MLD, {flow_ratio:.1f}× DWA):"
            " check RAS and secondary clarifier blanket depth ahead of morning peak."
        )

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

    # ── Medium-term: scenario-specific first, then generic ───────────────
    # W3: AWWF leads with process resilience; PWWF leads with hydraulic capital.
    # Generic clarifier/biological items follow the scenario-specific lead.

    if fst == _SCENARIO_AWWF:
        # AWWF: resilience and process debottlenecking first
        medium.append(
            "Evaluate process intensification (IFAS, MABR) to increase biological"
            " resilience under sustained wet weather loading —"
            " buffer nitrification stability without new tank volume."
        )
        medium.append(
            "Commission a wet weather performance audit:"
            " review SRT, MLSS, and nitrification data from previous AWWF events."
        )
        if "aeration" in tc.lower() or "Aeration" in str(titles):
            medium.append("Upgrade or augment blower capacity and install dissolved oxygen control loops.")
        # W7b: WAS setpoint review for multi-day AWWF
        ww_dur_med = wp.flow_wet_weather_duration_hr or 0.0
        if ww_dur_med > 48:
            medium.append(
                "Review WAS setpoint strategy for multi-day AWWF events"
                " to prevent SRT crash below nitrification threshold."
            )
        if wp.flow_clarifier_stress or flow_ratio > 1.8:
            medium.append(
                "Assess clarifier capacity for sustained AWWF SOR —"
                " prolonged overload is more damaging than a short PWWF peak event."
            )
        if "Nitrification" in str(titles) or "nitrogen" in str(titles).lower():
            medium.append("Consider IFAS media addition to existing aerobic zone to increase biological volume and nitrification capacity without new civil works.")
        if state in ("Tightening", "Fragile", "Failure Risk"):
            medium.append("Commission concept-level capacity expansion study with 20-year demand projections.")

    elif fst == _SCENARIO_PWWF:
        # PWWF: hydraulic capital and storm management first
        medium.append(
            "Evaluate flow equalisation basin or storm storage tank"
            " to attenuate PWWF peak before secondary treatment —"
            " target attenuation to < 2× DWA at inlet to secondaries."
        )
        if wp.flow_clarifier_stress or flow_ratio > 1.8:
            medium.append(
                "Assess secondary clarifier hydraulic capacity upgrade or parallel unit"
                " to handle PWWF SOR without sludge washout risk."
            )
        medium.append(
            "Review storm tank capacity adequacy:"
            " confirm volume is sufficient for modelled PWWF duration and peak flow."
        )
        if "Clarifier" in str(titles) or "Hydraulic" in str(titles):
            medium.append("Evaluate secondary clarifier expansion or parallel clarifier to restore SOR headroom.")
        if "Nitrification" in str(titles) or "nitrogen" in str(titles).lower():
            medium.append("Consider IFAS media addition to existing aerobic zone to increase biological volume and nitrification capacity without new civil works.")
        if state in ("Tightening", "Fragile", "Failure Risk"):
            medium.append("Commission concept-level capacity expansion study with 20-year demand projections.")

    else:
        # Dry weather / DWP: original generic ordering
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

    # Wet weather long-term actions — scenario-specific
    if fst == _SCENARIO_AWWF:
        long.append(
            "Develop a wet weather process resilience strategy:"
            " include biological buffer capacity, clarifier redundancy,"
            " and real-time DO/SRT control as design criteria for future capital works."
        )
        long.append(
            "Evaluate real-time control (RTC) for sustained wet weather management:"
            " dynamic aeration, WAS, and RAS response calibrated to AWWF flow profiles."
        )
    elif fst == _SCENARIO_PWWF:
        long.append(
            "Plan hydraulic expansion to accommodate growth in peak wet weather I/I:"
            " confirm catchment I/I reduction programme and residual PWWF design factor."
        )
        long.append(
            "Develop a wet weather emergency response plan:"
            " pre-defined decision rules for overflow activation,"
            " regulator notification, and post-event monitoring."
        )

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

    # ── W-NEW-7: Unknown state / sparse data → return Unknown compliance ──
    _missing_count = len(wp.missing_fields) if wp.missing_fields else 0
    if state == "Unknown" or _missing_count > 4:
        return ComplianceRisk(
            compliance_risk     = "Unknown",
            likely_breach_type  = "Insufficient data",
            regulatory_exposure = "Insufficient data to assess compliance risk.",
            reputational_risk   = "Unknown — insufficient data.",
        )


    # ── Overall compliance risk ───────────────────────────────────────────
    if state in ("Failure Risk",) or sev == "High":
        risk_level = "High"
    elif state in ("Fragile",) or sev == "Medium":
        risk_level = "Medium"
    else:
        risk_level = "Low"

    # ── Wet weather compliance escalation ────────────────────────────────
    fst = wp.flow_scenario_type or ""
    is_ww = fst in (_SCENARIO_AWWF, _SCENARIO_PWWF)
    is_pwwf = (fst == _SCENARIO_PWWF)
    is_awwf = (fst == _SCENARIO_AWWF)
    if is_ww and (wp.flow_overflow_flag or wp.flow_bypass_risk):
        # Overflow or bypass is a direct licence breach in most jurisdictions
        if risk_level != "High":
            risk_level = "High"

    # ── Likely breach type ────────────────────────────────────────────────
    breach_parts = []
    if "nitrogen" in str(titles).lower() or "Nitrification" in str(titles):
        breach_parts.append("TN / ammonia exceedance")
    if "Phosphorus" in str(titles):
        breach_parts.append("TP licence breach")
    # W-NEW-1: only add carryover when clarifier is genuinely overloaded (Medium+)
    # "Clarifier at design operating point" is Low — not a carryover condition
    _clarifier_genuinely_overloaded = any(
        ("Clarifier" in m.title or "Hydraulic" in m.title)
        and m.severity in ("Medium", "High")
        for m in failure.items
    )
    if _clarifier_genuinely_overloaded:
        breach_parts.append("suspended solids carryover at peak flow")
    # Wet weather specific breaches — scenario-differentiated
    if is_awwf:
        if not any("nitrogen" in b or "ammonia" in b for b in breach_parts):
            breach_parts.append("sustained nutrient performance degradation under AWWF loading")
        if not any("solids" in b for b in breach_parts):
            breach_parts.append("gradual solids or ammonia performance drift during extended wet weather")
    elif is_pwwf:
        if wp.flow_overflow_flag:
            breach_parts.append("wet weather discharge / bypass event (notifiable incident)")
        if "washout" in str(titles).lower() or "Clarifier washout" in str(titles):
            breach_parts.append("solids carryover risk during PWWF")
        if not any("carryover" in b or "bypass" in b for b in breach_parts):
            breach_parts.append("acute process exceedance under peak wet weather I/I loading")
    if not breach_parts:
        breach_parts = ["process performance deterioration under growth or peak load"]
    likely_breach = "; ".join(breach_parts)

    # ── Regulatory exposure ───────────────────────────────────────────────
    if risk_level == "High":
        if is_pwwf and wp.flow_overflow_flag:
            # W5: overflow has occurred — active incident language
            reg_exp = (
                "Active wet weather overflow / bypass event indicated — notifiable incident exposure elevated. "
                "Incident response and regulator notification required immediately. "
                "Discharge monitoring data must be collected and retained from first flow. "
                "Proactive community communication and post-event reporting required."
            )
        elif is_pwwf and not wp.flow_overflow_flag:
            # W5: overflow is a risk but has not occurred
            reg_exp = (
                "High risk of wet weather overflow / bypass under current PWWF assumptions. "
                "Potential notifiable incident exposure if event conditions worsen. "
                "Prepare regulator notification procedure and confirm overflow pathway readiness. "
                "Establish self-monitoring triggers before event arrival."
            )
        elif is_awwf and wp.flow_overflow_flag:
            reg_exp = (
                "Sustained AWWF overflow condition — regulatory exposure elevated. "
                "Notify regulator and document bypass duration and receiving environment exposure."
            )
        elif is_awwf and not wp.flow_overflow_flag:
            # C-NEW-1: AWWF without overflow — chronic planning language, not acute incident
            reg_exp = (
                "Sustained wet weather loading presents elevated risk of treatment performance "
                "exceedance over the event duration. "
                "Prepare a corrective action plan for nutrient and solids management "
                "under AWWF conditions. "
                "Regulator engagement is recommended if compliance margins are persistently narrow."
            )
        else:
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
        if is_pwwf and wp.flow_overflow_flag:
            rep_risk = (
                "Public and political risk elevated — overflow event is discoverable and reportable. "
                "Proactive community communication and transparent incident reporting "
                "are essential to managing reputational exposure."
            )
        elif is_pwwf and not wp.flow_overflow_flag:
            rep_risk = (
                "Moderate-to-high reputational exposure. Overflow risk under PWWF conditions "
                "may attract regulator and media scrutiny if event occurs without preparation. "
                "Demonstrating pre-event readiness is the key reputational management action."
            )
        else:
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
