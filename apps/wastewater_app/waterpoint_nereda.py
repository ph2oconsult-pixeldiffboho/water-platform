"""
apps/wastewater_app/waterpoint_nereda.py

Nereda® (Aerobic Granular Sludge) WaterPoint model.

Activated when wp.nereda_enabled == True.
Replaces clarifier-based stress domains with balance-tank and cycle domains.
Design anchors from Longwarry STP: 3–3.6 MLD ADWF, 500–750 m³ FBT,
2 × 1650 m³ reactors, DWF cycle ≈ 300 min, RWF cycle ≈ 230–240 min.

All functions are pure — no Streamlit, no I/O, no side effects.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

# ── Nereda-specific result ─────────────────────────────────────────────────────

@dataclass
class NeredaStressResult:
    """Output from the Nereda stress model."""
    # Domains (name, utilisation 0–1.2+, detail string)
    domains:             List[Tuple[str, float, str]] = field(default_factory=list)
    # Key computed values
    balance_tank_util:   float = 0.0
    hours_to_fill:       Optional[float] = None   # None = inflow ≤ treatment rate
    compression_ratio:   float = 0.0              # 1 - (rwf_cycle / dwf_cycle)
    decant_risk_flag:    bool  = False
    cycle_rwf_hr:        Optional[float] = None   # estimated RWF cycle duration
    # State
    state:      str = "Stable"
    rate:       str = "Stable"
    t2b:        str = "> 5 years"
    proximity:  float = 0.0                       # uncapped
    confidence: str = "Medium"
    rationale:  str = ""
    primary_constraint: str = ""


@dataclass
class NeredaFailureMode:
    title:       str
    description: str
    severity:    str   # Low / Medium / High


# ── Default design parameters (Longwarry anchors) ─────────────────────────────
_DWF_CYCLE_MIN  = 300.0    # min — DWF cycle time
_RWF_CYCLE_MIN  = 235.0    # min — typical RWF cycle (range 230–240)
_COMPRESS_TIGHTEN = 0.20   # compression_ratio > this → Tightening
_COMPRESS_FRAGILE = 0.35   # compression_ratio > this → Fragile
_COMPRESS_FAIL    = 0.50   # compression_ratio > this → Failure Risk
_DECANT_RISK_CR   = 0.15   # compression_ratio > this (i.e. cycle < 85% of DWF) → decant risk
_BTK_FILL_HOURS_FAIL = 2.0 # hours_to_fill < this → Failure Risk

_NO_CLARIFIER_TECHS = {"granular_sludge", "bnr_mbr", "anmbr"}


# ── Main Nereda stress function ────────────────────────────────────────────────

def calculate_nereda_stress(wp) -> NeredaStressResult:
    """
    Calculate system stress for a Nereda AGS plant.

    Parameters
    ----------
    wp : WaterPointInput with nereda_enabled=True

    Returns
    -------
    NeredaStressResult
    """
    result = NeredaStressResult()

    # ── Pull inputs ────────────────────────────────────────────────────────
    base_flow_mld  = wp.average_flow_mld or 3.3       # ADWF
    adj_flow_mld   = wp.flow_adjusted_flow_mld or base_flow_mld
    flow_ratio     = adj_flow_mld / base_flow_mld if base_flow_mld > 0 else 1.0
    fbt_m3         = wp.nereda_fbt_m3 or 625.0        # default mid-range
    dwf_cycle_hr   = (wp.nereda_dwf_cycle_min or _DWF_CYCLE_MIN) / 60.0
    n_reactors     = wp.nereda_n_reactors or 2
    reactor_vol_m3 = wp.reactor_volume_m3 or (1650.0 * n_reactors)
    fst            = wp.flow_scenario_type or ""

    # ── Estimate RWF cycle time via compression ────────────────────────────
    # Calibrated to Longwarry: DWF≈300min, RWF≈235min at ~3× flow → cr≈0.22.
    # Linear compression: cr = 0.15 × (flow_ratio - 1), capped at 0.50
    # (cycle cannot compress to < 50% of DWF — settling becomes non-functional).
    # This gives: 1.5× → cr=0.075 (Stable), 3× → cr=0.30 (Tightening),
    #             5× → cr=0.50 (Failure Risk), 8× → cr=0.50 (capped).
    compression_ratio = min(0.50, max(0.0, 0.15 * (flow_ratio - 1.0)))
    rwf_cycle_hr      = dwf_cycle_hr * (1.0 - compression_ratio)
    result.cycle_rwf_hr = round(rwf_cycle_hr, 2)

    # compression_ratio = fraction compressed away (0 = no compression)
    result.compression_ratio = round(compression_ratio, 3)

    # Decant risk: cycle time < 85% of DWF → settling phase threatened
    decant_risk = compression_ratio > _DECANT_RISK_CR
    result.decant_risk_flag = decant_risk

    # ── Domain 1: Balance tank (FBT) ──────────────────────────────────────
    # Treatment capacity ≈ base_flow (the plant is designed for ADWF)
    # Net fill rate = inflow - treatment_capacity (m³/hr)
    inflow_m3hr     = adj_flow_mld * 1000.0 / 24.0
    treatment_m3hr  = base_flow_mld * 1000.0 / 24.0

    if inflow_m3hr > treatment_m3hr and fbt_m3 > 0:
        net_fill_rate   = inflow_m3hr - treatment_m3hr
        hours_to_fill   = fbt_m3 / net_fill_rate
        result.hours_to_fill = round(hours_to_fill, 2)
        # util: 1/hours maps 1h→1.0, 2h→0.5, 0.5h→2.0
        btk_util = min(1.4, 1.0 / max(0.1, hours_to_fill))
    else:
        hours_to_fill   = None
        result.hours_to_fill = None
        btk_util        = 0.3   # inflow ≤ treatment → no pressure

    result.balance_tank_util = round(btk_util, 3)
    detail_btk = (
        f"{hours_to_fill:.1f}h to fill {fbt_m3:.0f} m³ FBT"
        if hours_to_fill is not None
        else f"FBT {fbt_m3:.0f} m³ — no net inflow pressure"
    )
    result.domains.append(("Balance tank capacity", btk_util, detail_btk))

    # ── Domain 1b: Hydraulic overload (extreme events) ────────────────────
    # Adds a direct flow_ratio signal so extreme events (8× ADWF) show >200% proximity.
    # Fires when flow_ratio > 2×. Normalised to 4× as "design limit" (util=1.0 at 4×).
    if flow_ratio > 2.0:
        hyd_overload_util = (flow_ratio - 1.0) / 3.0
        result.domains.append((
            "Hydraulic overload",
            hyd_overload_util,
            f"{adj_flow_mld:.1f} MLD ({flow_ratio:.1f}\u00d7 ADWF — beyond FBT buffer capacity)",
        ))

    # ── Domain 2: Cycle compression ───────────────────────────────────────
    # Map compression_ratio to utilisation against Failure threshold
    cycle_util = compression_ratio / _COMPRESS_FAIL   # 0→0, 0.5→1.0
    result.domains.append((
        "Cycle compression",
        cycle_util,
        f"Compression {compression_ratio:.2f} "
        f"(DWF {dwf_cycle_hr*60:.0f} min → est. RWF {rwf_cycle_hr*60:.0f} min)",
    ))

    # ── Domain 3: Aeration (unchanged from standard WP) ──────────────────
    if wp.o2_demand_kg_day and wp.aeration_kwh_day:
        blower_kw = (wp.aeration_kwh_day / 24) * 1.30
        max_o2    = blower_kw * 1.8 * 24
        if max_o2 > 0:
            aer_util = wp.o2_demand_kg_day / max_o2
            result.domains.append((
                "Aeration capacity",
                aer_util,
                f"{wp.o2_demand_kg_day:.0f} kg O\u2082/d demand",
            ))

    # ── Pick most constrained domain ──────────────────────────────────────
    if not result.domains:
        result.state      = "Unknown"
        result.rationale  = "Insufficient Nereda data to assess system stress."
        result.confidence = "Low"
        return result

    dom_name, max_util, dom_detail = max(result.domains, key=lambda x: x[1])
    result.proximity = round(max_util * 100.0, 1)   # uncapped

    # ── State logic — Nereda-specific escalation (Rule 7) ─────────────────
    if wp.flow_overflow_flag:
        state = "Failure Risk"
        rate  = "Accelerating"
        t2b   = "< 12 months — overflow active"
    elif decant_risk and compression_ratio >= _COMPRESS_FAIL:
        state = "Failure Risk"
        rate  = "Accelerating"
        t2b   = "< 12 months — decant phase at risk"
    elif decant_risk:
        state = "Fragile"
        rate  = "Accelerating"
        t2b   = "12–24 months"
    elif btk_util > 0.7 or compression_ratio > _COMPRESS_TIGHTEN:
        state = "Tightening"
        rate  = "Tightening"
        t2b   = "3–5 years"
    else:
        state = "Stable"
        rate  = "Stable"
        t2b   = "> 5 years"

    # AWWF without overflow → chronic planning language
    from apps.wastewater_app.flow_scenario_engine import SCENARIO_AWWF
    if fst == SCENARIO_AWWF and not wp.flow_overflow_flag:
        ww_dur = wp.flow_wet_weather_duration_hr or 24.0
        if ww_dur > 48:
            t2b = "Sustained resilience pressure — planning horizon 6–24 months"
        elif state not in ("Failure Risk",):
            t2b = "Chronic planning condition — address within 1–3 year capital programme"

    result.state = state
    result.rate  = rate
    result.t2b   = t2b

    # ── Confidence ────────────────────────────────────────────────────────
    n_domains = len(result.domains)
    missing   = len(wp.missing_fields) if wp.missing_fields else 0
    if n_domains >= 3 and missing <= 1:
        result.confidence = "High"
    elif n_domains >= 2 or missing <= 3:
        result.confidence = "Medium"
    else:
        result.confidence = "Low"

    # ── Rationale ─────────────────────────────────────────────────────────
    result.rationale = _nereda_rationale(dom_name, state, compression_ratio,
                                          hours_to_fill, flow_ratio)

    # Exceedance label for extreme events
    _constraint_label = f"{dom_name} ({dom_detail})"
    if flow_ratio >= 5.0:
        _constraint_label += f" | Catastrophic exceedance: {round((flow_ratio-1)*100)}% above design"
    elif flow_ratio >= 3.0:
        _constraint_label += f" | Extreme exceedance: {round((flow_ratio-1)*100)}% above design"
    result.primary_constraint = _constraint_label

    return result


def _nereda_rationale(domain: str, state: str, cr: float,
                      htf: Optional[float], flow_ratio: float) -> str:
    if state == "Stable":
        return (f"Balance tank and cycle timing have adequate headroom "
                f"under current hydraulic loading ({flow_ratio:.1f}\u00d7 ADWF).")
    if state == "Tightening":
        return (f"Elevated flow ({flow_ratio:.1f}\u00d7 ADWF) is compressing cycle time "
                f"(compression ratio {cr:.2f}). Balance tank buffer is being consumed.")
    if state == "Fragile":
        if htf is not None and htf < 4:
            return (f"Balance tank fill estimated in {htf:.1f}h at current inflow. "
                    f"Cycle compression {cr:.2f} threatens settling phase integrity.")
        return (f"Cycle compression {cr:.2f} is approaching the decant risk threshold. "
                f"Granule settling and decant performance at risk under sustained loading.")
    # Failure Risk
    if htf is not None and htf < _BTK_FILL_HOURS_FAIL:
        return (f"Balance tank fill in < {htf:.1f}h — overflow imminent. "
                f"Cycle compression {cr:.2f} exceeds decant risk threshold.")
    return (f"Extreme hydraulic loading ({flow_ratio:.1f}\u00d7 ADWF) has exceeded "
            f"Nereda process capacity. Overflow and decant failure risk are immediate.")


# ── Nereda failure modes ───────────────────────────────────────────────────────

def detect_nereda_failure_modes(
    wp,
    nereda: NeredaStressResult,
) -> List[NeredaFailureMode]:
    """Return Nereda-specific failure modes (replaces clarifier modes)."""
    modes: List[NeredaFailureMode] = []
    fst = wp.flow_scenario_type or ""
    flow_ratio = (
        (wp.flow_adjusted_flow_mld or wp.average_flow_mld or 1.0) /
        max(0.01, wp.average_flow_mld or 1.0)
    )
    htf = nereda.hours_to_fill
    cr  = nereda.compression_ratio

    # 1. Balance tank overflow risk
    if htf is not None and htf < _BTK_FILL_HOURS_FAIL:
        modes.append(NeredaFailureMode(
            title       = "Balance tank overflow risk",
            description = (
                f"Balance tank estimated to fill in {htf:.1f}h at current inflow rate. "
                f"Overflow to equalisation or receiving environment is imminent. "
                "Immediate flow diversion or emergency bypass required."
            ),
            severity = "High",
        ))

    # 2. Decant solids carryover
    if nereda.decant_risk_flag:
        modes.append(NeredaFailureMode(
            title       = "Decant solids carryover risk",
            description = (
                f"Cycle compression ratio {cr:.2f} has reduced settling time below safe threshold. "
                "Granule settling is incomplete — decant phase may carry suspended solids to effluent. "
                "Reduce feed rate or extend cycle to restore settling phase."
            ),
            severity = "High" if cr > _COMPRESS_FRAGILE else "Medium",
        ))

    # 3. Cycle compression stress
    if cr > _COMPRESS_TIGHTEN:
        modes.append(NeredaFailureMode(
            title       = "Cycle compression stress",
            description = (
                f"Wet weather flow ({flow_ratio:.1f}\u00d7 ADWF) is compressing cycle time "
                f"(estimated {nereda.cycle_rwf_hr*60:.0f} min vs "
                f"{(wp.nereda_dwf_cycle_min or _DWF_CYCLE_MIN):.0f} min at DWF). "
                "Sustained compression degrades biological performance and granule stability."
            ),
            severity = "High" if cr > _COMPRESS_FRAGILE else "Medium",
        ))

    # 4. Granule instability (proxy)
    if wp.flow_first_flush_enabled or flow_ratio > 3.0:
        modes.append(NeredaFailureMode(
            title       = "Granule instability risk",
            description = (
                "High hydraulic loading or first flush shock may disrupt granule structure. "
                "AGS granules are sensitive to rapid concentration changes and high shear loading. "
                "Monitor effluent TSS closely and protect granule bed integrity."
            ),
            severity = "Medium",
        ))

    # 5. Extended biological stress (AWWF > 48h)
    from apps.wastewater_app.flow_scenario_engine import SCENARIO_AWWF
    ww_dur = wp.flow_wet_weather_duration_hr or 0.0
    if ww_dur > 48 and fst == SCENARIO_AWWF:
        modes.append(NeredaFailureMode(
            title       = "Extended wet weather biological stress",
            description = (
                f"Sustained AWWF loading over {ww_dur:.0f}h may reduce substrate selectivity "
                "and allow flocculent sludge to compete with granules. "
                "Monitor granule diameter and settleability. "
                "Consider reducing ADWF cycle feed fraction to maintain granule density."
            ),
            severity = "Medium",
        ))

    return modes


# ── Nereda decision layer ──────────────────────────────────────────────────────

def generate_nereda_decisions(
    wp,
    nereda: NeredaStressResult,
    modes:  List[NeredaFailureMode],
) -> dict:
    """
    Returns dict with keys: short_term, medium_term, long_term,
    capex_range, risk_if_no_action.
    """
    from apps.wastewater_app.flow_scenario_engine import SCENARIO_AWWF, SCENARIO_PWWF
    fst       = wp.flow_scenario_type or ""
    state     = nereda.state
    cr        = nereda.compression_ratio
    htf       = nereda.hours_to_fill
    flow_ratio= (
        (wp.flow_adjusted_flow_mld or wp.average_flow_mld or 1.0) /
        max(0.01, wp.average_flow_mld or 1.0)
    )
    short:  List[str] = []
    medium: List[str] = []
    long_:  List[str] = []

    # ── Short-term — P3/P4: scenario and state differentiated ───────────
    if wp.flow_overflow_flag:
        # P4: Active overflow — incident response language
        short.append(
            "ACTIVE OVERFLOW: divert flow to equalisation immediately."
        )
        short.append(
            "Initiate regulatory notification — wet weather overflow is a notifiable incident. "
            "Document bypass duration, volume, and receiving environment exposure."
        )
        short.append(
            "Prioritise plant stability: protect granule bed integrity over treatment completeness. "
            "Resume normal cycle programme once inflow returns to balance tank capacity."
        )
    elif fst == SCENARIO_AWWF:
        # P4: AWWF — sustained monitoring and biological stability
        short.append(
            "Monitor cycle compression and FBT fill rate continuously "
            "— adjust cycle timing to maintain settling integrity."
        )
        short.append(
            "Manage sludge age and biological stability under sustained loading conditions."
        )
        if cr > _COMPRESS_TIGHTEN:
            short.append(
                f"Cycle compression at {cr:.2f} — verify feed pump rate and confirm "
                "decant phase is completing fully before next fill cycle."
            )
    elif fst == SCENARIO_PWWF:
        # P4: PWWF — peak event preparation
        short.append(
            "Prepare FBT for peak buffering — confirm available volume and inflow control."
        )
        short.append(
            "Verify overflow pathway and equalisation basin availability before peak arrival."
        )
        if cr > _COMPRESS_TIGHTEN:
            short.append(
                f"Cycle compression at {cr:.2f} — verify feed pump rate and confirm "
                "decant phase is completing fully before next fill cycle."
            )
    else:
        # P3: DWA / DWP Stable — routine operational language, no wet-weather framing
        if state == "Stable" and flow_ratio <= 1.5:
            short.append(
                "Maintain standard cycle programme and monitor FBT level and cycle timing."
            )
            short.append(
                "Verify feed pump availability and confirm cycle parameters are within design range."
            )
        else:
            short.append(
                "Protect balance tank capacity — ensure FBT is as empty as possible before "
                "anticipated wet weather events to maximise buffer volume."
            )
            short.append(
                "Adjust cycle timing: extend settling phase to preserve granule integrity "
                "as inflow increases. Reduce feed rate if fill volume exceeds working volume."
            )
            if cr > _COMPRESS_TIGHTEN:
                short.append(
                    f"Cycle compression at {cr:.2f} — verify feed pump rate and confirm "
                    "decant phase is completing fully before next fill cycle."
                )
            short.append(
                "Verify feed pump availability and flow control valve response "
                "before anticipated wet weather event."
            )

    # First flush
    if wp.flow_first_flush_enabled:
        if wp.flow_overflow_flag:
            short.append(
                "Manage ongoing first flush shock load: confirm coagulant/ferric dosing is active "
                "and chemical feed is adequate for elevated TSS and TP."
            )
        else:
            short.append(
                "Pre-dose coagulant / ferric before first flush arrival "
                "to manage shock TSS and TP load — protect granule bed from sudden concentration change."
            )

    # ── Medium-term ───────────────────────────────────────────────────────
    if fst == SCENARIO_AWWF:
        medium.append(
            "Increase balance tank volume to extend hydraulic buffer for sustained "
            "wet weather loading — target minimum 4–6 hours of net inflow capacity."
        )
        medium.append(
            "Optimise wet weather cycle strategy: develop a dedicated wet weather cycle programme "
            "with shorter fill, extended settle, and protected decant phase."
        )
        medium.append(
            "Review carbon dosing strategy for extended wet weather loading — "
            "sustained dilution may reduce available VFAs for bio-P selectivity."
        )
    elif fst == SCENARIO_PWWF:
        medium.append(
            "Increase upstream stormwater attenuation capacity — "
            "reduce peak I/I inflow before it reaches the balance tank."
        )
        medium.append(
            "Improve peak flow diversion upstream: assess sewer overflow structures "
            "and real-time control to attenuate PWWF peak before balance tank."
        )
        medium.append(
            "Review FBT sizing for PWWF design factor — confirm volume is sufficient "
            "to buffer peak event without overflow in the modelled duration."
        )
    else:
        # DWA / DWP
        if state in ("Tightening", "Fragile", "Failure Risk"):
            medium.append(
                "Commission capacity review: assess whether balance tank and reactor volumes "
                "are adequate for current and projected design flows."
            )

    # ── Long-term ─────────────────────────────────────────────────────────
    long_.append(
        "Add additional Nereda reactor train to increase biological treatment capacity "
        "and provide operational redundancy for wet weather events."
    )
    long_.append(
        "Implement catchment-wide I/I reduction programme — "
        "reduce peak wet weather inflow factor to protect Nereda cycle integrity."
    )
    long_.append(
        "Assess polishing train (UF or tertiary filtration) for resilience under "
        "wet weather conditions when decant performance is under pressure."
    )

    # ── Capex ─────────────────────────────────────────────────────────────
    capex = ""
    if wp.outputs and wp.outputs.capex_estimate:
        if state == "Stable":
            capex = "Incremental capital $0.1–0.5M for operational optimisation and balance tank controls."
        elif state == "Tightening":
            capex = "Balance tank expansion or cycle programme upgrade estimated $0.5–2M."
        else:
            capex = "Additional reactor train or major FBT upgrade — concept range $5–15M+."

    # ── Risk if no action ─────────────────────────────────────────────────
    risk_map = {
        "Stable":       "Nereda performance is maintained. Monitor cycle times and FBT levels proactively.",
        "Tightening":   "Cycle compression will worsen with flow growth. Decant risk will materialise without intervention.",
        "Fragile":      "Decant solids carryover is probable under peak conditions. Licence exceedance risk is elevated.",
        "Failure Risk": "Overflow and decant failure are imminent. Regulatory incident and effluent licence breach likely.",
    }
    risk = risk_map.get(state, "Insufficient data to assess risk.")

    return dict(short_term=short, medium_term=medium, long_term=long_,
                capex_range=capex, risk_if_no_action=risk)


# ── Nereda compliance risk ─────────────────────────────────────────────────────

def assess_nereda_compliance(wp, nereda: NeredaStressResult, modes: List[NeredaFailureMode]) -> dict:
    """Returns dict matching ComplianceRisk fields."""
    state = nereda.state
    cr    = nereda.compression_ratio

    # Overall risk level
    if state in ("Failure Risk",) or any(m.severity == "High" for m in modes):
        risk_level = "High"
    elif state in ("Fragile",) or any(m.severity == "Medium" for m in modes):
        risk_level = "Medium"
    else:
        risk_level = "Low"

    # Escalate on overflow
    if wp.flow_overflow_flag:
        risk_level = "High"

    # Breach type
    if wp.flow_overflow_flag:
        breach = "Wet weather overflow or bypass event — notifiable incident"
    elif nereda.decant_risk_flag:
        breach = "Risk of decant solids carryover under wet weather cycle compression"
    elif cr > _COMPRESS_TIGHTEN:
        breach = "Cycle compression risk — effluent quality may degrade under sustained wet weather"
    else:
        breach = "Process performance within normal parameters"

    # Regulatory exposure
    if risk_level == "High":
        if wp.flow_overflow_flag:
            reg_exp = (
                "Overflow or bypass event is a notifiable incident under most licence conditions. "
                "Immediate regulator notification required. "
                "Discharge monitoring data must be collected and retained. "
                "Post-event root cause analysis required."
            )
        else:
            reg_exp = (
                "Elevated risk of decant solids carryover under compressed cycle conditions. "
                "Prepare corrective action plan and establish TSS self-monitoring triggers. "
                "Regulator engagement recommended if effluent quality is persistently affected."
            )
    elif risk_level == "Medium":
        reg_exp = (
            "Moderate risk of cycle compression affecting effluent quality under wet weather. "
            "Maintain enhanced effluent monitoring and prepare contingency cycle programme."
        )
    else:
        reg_exp = (
            "Nereda process is operating within design parameters. "
            "Maintain standard cycle monitoring and balance tank level tracking."
        )

    # Reputational risk
    if risk_level == "High":
        rep = (
            "Overflow or decant failure events are discoverable and reportable. "
            "Proactive communication with regulator and community is recommended."
        )
    elif risk_level == "Medium":
        rep = "Moderate exposure if effluent quality deteriorates — Nereda technology is under scrutiny."
    else:
        rep = "Low reputational exposure under current operating conditions."

    return dict(compliance_risk=risk_level, likely_breach_type=breach,
                regulatory_exposure=reg_exp, reputational_risk=rep)
