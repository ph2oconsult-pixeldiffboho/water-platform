"""
apps/wastewater_app/waterpoint_mob.py

MOB Intensified SBR WaterPoint Model
miGRATE™ migrating biofilm carriers + inDENSE® gravimetric selection.

Activated when wp.mob_enabled == True (technology_code == "migrate_indense").

This is a process-intensified hybrid biomass system:
  - Existing SBR tanks retained (no new reactor volume)
  - Capacity increase via biofilm carriers (miGRATE) and densified sludge (inDENSE)
  - Three interacting biomass domains: suspended growth, biofilm, densified AS

Design anchors from Lang Lang STP process modelling report:
  - ADWF 2.50 MLD, PWWF 4.82 MLD
  - 2 × SBRs, 840 m³ each, 191 m³ fill volume each
  - Normal cycle 3.0 hr, Storm cycle 2.5 hr
  - miGRATE: 3.34 mm carriers, 1.3% fill, 228 m²/m³ added surface area
  - inDENSE: 35 psig, overflow WAS 70–80% flow / 60–65% solids

All functions are pure — no Streamlit, no I/O, no side effects.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

# ── Constants ──────────────────────────────────────────────────────────────────

# Lang Lang defaults
_LL_ADWF_MLD         = 2.50
_LL_PWWF_MLD         = 4.82
_LL_SBR_COUNT        = 2
_LL_SBR_VOL_M3       = 840.0
_LL_FILL_VOL_M3      = 191.0
_LL_CYCLE_NORMAL_HR  = 3.0
_LL_CYCLE_STORM_HR   = 2.5

# Throughput thresholds (utilisation fractions)
_TIGHTEN_UTIL = 0.80
_FRAGILE_UTIL = 0.92
_FAIL_UTIL    = 1.00


# ── Result dataclass ───────────────────────────────────────────────────────────

@dataclass
class MOBStressResult:
    """Output from the MOB intensified SBR stress model."""
    domains:                List[Tuple[str, float, str]] = field(default_factory=list)
    # Key computed values
    throughput_util:        float = 0.0    # daily throughput / intensified capacity
    intensified_capacity_mld: float = 0.0
    normal_capacity_mld:    float = 0.0
    storm_capacity_mld:     float = 0.0
    storm_cycle_required:   bool  = False  # adj_flow > normal capacity
    migrate_active:         bool  = False
    indense_active:         bool  = False
    selector_operational:   bool  = True
    # State
    state:      str = "Stable"
    rate:       str = "Stable"
    t2b:        str = "> 5 years"
    proximity:  float = 0.0   # uncapped
    confidence: str = "Medium"
    rationale:  str = ""
    primary_constraint: str = ""


@dataclass
class MOBFailureMode:
    title:       str
    description: str
    severity:    str   # Low / Medium / High


# ── Main MOB stress function ───────────────────────────────────────────────────

def calculate_mob_stress(wp) -> MOBStressResult:
    """
    Calculate system stress for a MOB intensified SBR plant.

    Parameters
    ----------
    wp : WaterPointInput with mob_enabled=True

    Returns
    -------
    MOBStressResult
    """
    result = MOBStressResult()

    # ── Pull inputs with safe defaults ────────────────────────────────────────
    base_flow    = wp.average_flow_mld or _LL_ADWF_MLD
    adj_flow     = wp.flow_adjusted_flow_mld or base_flow
    flow_ratio   = adj_flow / base_flow if base_flow > 0 else 1.0
    fst          = wp.flow_scenario_type or ""

    sbr_count    = getattr(wp, "sbr_count", None) or _LL_SBR_COUNT
    fill_vol_m3  = getattr(wp, "sbr_fill_volume_m3", None) or _LL_FILL_VOL_M3
    sbr_vol_m3   = getattr(wp, "sbr_volume_m3", None) or _LL_SBR_VOL_M3

    cycle_normal = getattr(wp, "cycle_time_normal_hr", None) or _LL_CYCLE_NORMAL_HR
    cycle_storm  = getattr(wp, "cycle_time_storm_hr",  None) or _LL_CYCLE_STORM_HR

    migrate_on   = getattr(wp, "migrate_enabled", False)
    indense_on   = getattr(wp, "indense_enabled", False)
    selector_ok  = getattr(wp, "selector_operational", True)
    screening_ok = getattr(wp, "carrier_screening_available", True)

    result.migrate_active      = migrate_on
    result.indense_active      = indense_on
    result.selector_operational= selector_ok

    # ── Domain A: Cycle throughput ─────────────────────────────────────────────
    # Achievable daily throughput = (fill_vol × sbr_count × fills_per_day)
    # fills_per_day = 24 / cycle_time
    fills_normal = 24.0 / cycle_normal
    fills_storm  = 24.0 / cycle_storm
    cap_normal_m3d = fill_vol_m3 * sbr_count * fills_normal
    cap_storm_m3d  = fill_vol_m3 * sbr_count * fills_storm

    cap_normal_mld = cap_normal_m3d / 1000.0
    cap_storm_mld  = cap_storm_m3d  / 1000.0

    result.normal_capacity_mld = round(cap_normal_mld, 2)
    result.storm_capacity_mld  = round(cap_storm_mld, 2)

    # Intensified capacity: inDENSE improves solids retention → allows ~10% more throughput
    # miGRATE alone → nitrification uplift, not hydraulic
    # Combined: ~12–15% throughput gain; use 12% as conservative anchor
    if indense_on and selector_ok:
        intensification_factor = 1.12
    elif migrate_on and not indense_on:
        intensification_factor = 1.05   # miGRATE alone: modest hydraulic benefit
    else:
        intensification_factor = 1.00   # baseline SBR, no intensification

    cap_intensified_mld = cap_storm_mld * intensification_factor
    result.intensified_capacity_mld = round(cap_intensified_mld, 2)

    # Storm cycle required when adj_flow > normal capacity
    storm_required = adj_flow > cap_normal_mld
    result.storm_cycle_required = storm_required

    # Throughput utilisation: compare adj_flow to intensified capacity
    throughput_util = adj_flow / cap_intensified_mld if cap_intensified_mld > 0 else 1.0
    result.throughput_util = round(throughput_util, 3)

    detail_thru = (
        f"{adj_flow:.2f} MLD vs intensified cap {cap_intensified_mld:.2f} MLD "
        f"({'storm cycle' if storm_required else 'normal cycle'})"
    )
    result.domains.append(("Cycle throughput", throughput_util, detail_thru))

    # ── Domain B: Settling / solids retention ─────────────────────────────────
    # inDENSE = strong settling improvement; miGRATE alone = minimal SVI improvement
    if indense_on and selector_ok:
        settling_util = 0.35   # well-controlled: low stress
    elif indense_on and not selector_ok:
        settling_util = 0.75   # selector down: reduced benefit
    elif migrate_on and not indense_on:
        settling_util = 0.65   # miGRATE only: modest, settling NOT consistently improved
    else:
        settling_util = 0.55   # baseline SBR (reasonable for well-operated plant)

    # Elevated flow increases settling stress
    if flow_ratio > 2.0:
        settling_util = min(1.2, settling_util + (flow_ratio - 1.0) * 0.15)
    elif flow_ratio > 1.5:
        settling_util = min(1.0, settling_util + (flow_ratio - 1.5) * 0.10)

    result.domains.append((
        "Settling / solids retention",
        settling_util,
        f"inDENSE={'on' if indense_on else 'off'} | "
        f"selector={'ok' if selector_ok else 'degraded'} | "
        f"flow {flow_ratio:.1f}x ADWF",
    ))

    # ── Domain C: Biofilm nitrification ───────────────────────────────────────
    # miGRATE carriers boost nitrification resilience
    if migrate_on and screening_ok:
        nit_util = max(0.20, 0.60 - 0.10 * flow_ratio)   # more resilient under load
    else:
        nit_util = max(0.30, 0.75 - 0.08 * flow_ratio)   # baseline SBR nitrification

    # Check effluent ammonia margin
    if wp.effluent_nh4_mg_l is not None and wp.nh4_target_mg_l is not None:
        margin = wp.nh4_target_mg_l - wp.effluent_nh4_mg_l
        if margin < 0.2:
            nit_util = max(nit_util, 0.90)
        elif margin < 0.5:
            nit_util = max(nit_util, 0.70)

    result.domains.append((
        "Biofilm nitrification resilience",
        nit_util,
        f"miGRATE={'on' if migrate_on else 'off'} | "
        f"screening={'ok' if screening_ok else 'risk'} | "
        f"flow {flow_ratio:.1f}x ADWF",
    ))

    # ── Domain D: Selector / inDENSE ─────────────────────────────────────────
    if indense_on:
        if selector_ok:
            sel_util = 0.30   # operational: low stress
        else:
            sel_util = 0.90   # selector down: near limit
    else:
        sel_util = 0.0    # no selector — not a stress domain
    if sel_util > 0:
        result.domains.append((
            "Selector / inDENSE operation",
            sel_util,
            f"pressure={'nominal' if selector_ok else 'degraded'} | "
            f"inDENSE={'active' if indense_on else 'absent'}",
        ))

    # ── Pick most constrained domain ──────────────────────────────────────────
    if not result.domains:
        result.state     = "Unknown"
        result.rationale = "Insufficient MOB data to assess system stress."
        result.confidence = "Low"
        return result

    dom_name, max_util, dom_detail = max(result.domains, key=lambda x: x[1])
    result.proximity = round(max_util * 100.0, 1)

    # ── State logic ───────────────────────────────────────────────────────────
    if wp.flow_overflow_flag:
        state = "Failure Risk"
        rate  = "Accelerating"
        t2b   = "< 12 months \u2014 overflow active"
    elif throughput_util >= _FAIL_UTIL:
        state = "Failure Risk"
        rate  = "Accelerating"
        t2b   = "< 12 months \u2014 intensified capacity exceeded"
    elif (not selector_ok and indense_on) or throughput_util >= _FRAGILE_UTIL:
        state = "Fragile"
        rate  = "Accelerating"
        t2b   = "12\u201324 months"
    elif storm_required or throughput_util >= _TIGHTEN_UTIL:
        state = "Tightening"
        rate  = "Tightening"
        t2b   = "3\u20135 years"
    else:
        state = "Stable"
        rate  = "Stable"
        t2b   = "> 5 years"

    # AWWF without overflow → chronic planning language
    from apps.wastewater_app.flow_scenario_engine import SCENARIO_AWWF
    if fst == SCENARIO_AWWF and not wp.flow_overflow_flag and state not in ("Failure Risk",):
        t2b = "Chronic planning condition \u2014 address within 1\u20133 year capital programme"

    result.state = state
    result.rate  = rate
    result.t2b   = t2b

    # ── Confidence ────────────────────────────────────────────────────────────
    missing  = len(wp.missing_fields) if wp.missing_fields else 0
    n_doms   = len(result.domains)
    if n_doms >= 3 and missing <= 1:
        result.confidence = "High"
    elif n_doms >= 2 or missing <= 3:
        result.confidence = "Medium"
    else:
        result.confidence = "Low"

    # ── Rationale ─────────────────────────────────────────────────────────────
    result.rationale = _mob_rationale(
        state, throughput_util, migrate_on, indense_on, selector_ok,
        storm_required, flow_ratio
    )

    # Constraint label
    _label = f"{dom_name} ({dom_detail})"
    if flow_ratio >= 2.0:
        _label += f" | {round((flow_ratio-1)*100)}% above design average"
    result.primary_constraint = _label

    return result


def _mob_rationale(state, thru_util, migrate, indense, selector_ok,
                   storm, flow_ratio) -> str:
    tech = []
    if migrate: tech.append("miGRATE biofilm")
    if indense: tech.append("inDENSE gravimetric selection")
    tech_str = " and ".join(tech) if tech else "baseline SBR"

    if state == "Stable":
        return (
            f"Capacity is being extended through {tech_str} rather than additional tank volume. "
            f"Throughput utilisation {thru_util*100:.0f}% is within the intensified operating envelope."
        )
    if state == "Tightening":
        extra = " Storm cycle operation is now required." if storm else ""
        return (
            f"Throughput at {thru_util*100:.0f}% of intensified capacity.{extra} "
            f"{tech_str} is maintaining compliance but margin is reducing."
        )
    if state == "Fragile":
        sel_note = " Selector underperformance is reducing the inDENSE benefit." if (indense and not selector_ok) else ""
        return (
            f"Intensified SBR is under pressure at {thru_util*100:.0f}% throughput utilisation.{sel_note} "
            f"Storm cycle compression is reducing treatment margin."
        )
    # Failure Risk
    if flow_ratio > 2.0:
        return (
            f"Extreme hydraulic loading ({flow_ratio:.1f}\u00d7 ADWF) has exceeded the intensified "
            f"SBR envelope. Overflow and treatment instability are immediate risks."
        )
    return (
        f"Required throughput at {thru_util*100:.0f}% of intensified capacity. "
        f"Reliable compliance under current loading is no longer assured."
    )


# ── MOB failure modes ──────────────────────────────────────────────────────────

def detect_mob_failure_modes(wp, mob: MOBStressResult) -> List[MOBFailureMode]:
    """Return MOB-specific failure modes (technology-specific, no clarifier language)."""
    modes: List[MOBFailureMode] = []
    fst   = wp.flow_scenario_type or ""
    state = mob.state
    tu    = mob.throughput_util

    # 1. Cycle throughput saturation
    if tu >= 0.92:
        modes.append(MOBFailureMode(
            title="Cycle throughput saturation",
            description=(
                f"Required daily throughput ({tu*100:.0f}% of intensified capacity) "
                "is approaching or exceeding the intensified SBR cycle envelope. "
                "Further throughput increase risks treatment compliance and solids control."
            ),
            severity="High" if tu >= _FAIL_UTIL else "Medium",
        ))

    # 2. Selector underperformance
    if mob.indense_active and not mob.selector_operational:
        modes.append(MOBFailureMode(
            title="Selector underperformance",
            description=(
                "inDENSE selective wasting and return is not operating within design parameters. "
                "Dense biomass inventory may be eroding, reducing settling improvement "
                "and the capacity uplift attributed to inDENSE."
            ),
            severity="High",
        ))

    # 3. Settling capacity limitation
    # miGRATE alone — settling NOT consistently improved (Lang Lang finding)
    if mob.migrate_active and not mob.indense_active:
        modes.append(MOBFailureMode(
            title="Settling capacity limitation",
            description=(
                "miGRATE biofilm carriers are active but inDENSE gravimetric selection is absent. "
                "The Lang Lang process modelling report found that miGRATE alone does not "
                "consistently improve SVI. Settling and solids retention improvement "
                "cannot be assumed without inDENSE."
            ),
            severity="Medium",
        ))
    elif mob.indense_active and not mob.selector_operational and tu > 0.8:
        modes.append(MOBFailureMode(
            title="Settling capacity limitation",
            description=(
                "Selector underperformance means settling improvement from inDENSE "
                "is partially compromised. Solids retention is at risk under current loading."
            ),
            severity="Medium",
        ))

    # 4. Carrier retention / screening risk
    if mob.migrate_active and not getattr(wp, "carrier_screening_available", True):
        modes.append(MOBFailureMode(
            title="Carrier retention / screening risk",
            description=(
                "Carrier separation and retention performance may be insufficient. "
                "Loss of migrating media reduces biofilm contribution to nitrification "
                "and capacity, and may cause downstream screening issues."
            ),
            severity="High",
        ))

    # 5. Nitrification resilience under load
    if not mob.migrate_active and tu > 0.85:
        modes.append(MOBFailureMode(
            title="Nitrification resilience under load",
            description=(
                "Ammonia oxidation capacity is under pressure without biofilm augmentation. "
                "miGRATE carriers have not been activated to supplement suspended growth "
                "nitrification resilience."
            ),
            severity="Medium",
        ))
    elif mob.migrate_active and tu > 0.95:
        modes.append(MOBFailureMode(
            title="Nitrification resilience under load",
            description=(
                "Even with miGRATE biofilm augmentation, ammonia oxidation capacity "
                "is under extreme throughput pressure. "
                "Ammonia compliance risk is elevated."
            ),
            severity="High",
        ))

    # 6. Wet weather cycle compression
    from apps.wastewater_app.flow_scenario_engine import SCENARIO_AWWF, SCENARIO_PWWF
    if fst in (SCENARIO_AWWF, SCENARIO_PWWF) and mob.storm_cycle_required:
        ww_dur = wp.flow_wet_weather_duration_hr or 0.0
        modes.append(MOBFailureMode(
            title="Wet weather cycle compression",
            description=(
                f"Storm operation ({_LL_CYCLE_STORM_HR:.1f}h cycle) is compressing react, settle, "
                f"and decant timing. Sustained compression ({ww_dur:.0f}h) reduces treatment "
                "stability and increases risk of solids carryover."
            ),
            severity="Medium" if tu < _FAIL_UTIL else "High",
        ))

    # 7. High TP trimming dependency
    if wp.effluent_tp_mg_l is not None and wp.tp_target_mg_l is not None:
        if wp.effluent_tp_mg_l > wp.tp_target_mg_l * 0.8:
            modes.append(MOBFailureMode(
                title="High TP trimming dependency",
                description=(
                    f"Effluent TP {wp.effluent_tp_mg_l:.2f} mg/L is approaching the "
                    f"target ({wp.tp_target_mg_l:.2f} mg/L). "
                    "Chemical phosphorus trimming remains critical under intensified operation. "
                    "Optimise DO and carbon partitioning to reduce dependency."
                ),
                severity="Medium",
            ))

    # 8. DO / aeration limitation
    if wp.o2_demand_kg_day and wp.aeration_kwh_day:
        blower_kw = (wp.aeration_kwh_day / 24) * 1.30
        max_o2    = blower_kw * 1.8 * 24
        if max_o2 > 0 and wp.o2_demand_kg_day / max_o2 > 0.85:
            modes.append(MOBFailureMode(
                title="DO / aeration optimisation limitation",
                description=(
                    "Oxygen delivery is approaching blower capacity. "
                    "This limits nutrient removal optimisation and intensified performance. "
                    "Aeration control upgrade may be required before further load increase."
                ),
                severity="Medium",
            ))

    return modes


# ── MOB decision layer ────────────────────────────────────────────────────────

def generate_mob_decisions(
    wp,
    mob:   MOBStressResult,
    modes: List[MOBFailureMode],
) -> dict:
    """Returns dict: short_term, medium_term, long_term, capex_range, risk_if_no_action."""
    from apps.wastewater_app.flow_scenario_engine import SCENARIO_AWWF, SCENARIO_PWWF
    fst   = wp.flow_scenario_type or ""
    state = mob.state
    short: List[str] = []
    medium: List[str] = []
    long_: List[str] = []

    # ── Short-term ────────────────────────────────────────────────────────────
    if wp.flow_overflow_flag:
        short.append(
            "ACTIVE OVERFLOW: divert excess flow and protect biomass retention "
            "within the intensified SBR system."
        )
        short.append(
            "Initiate incident response and regulatory notification pathway."
        )
        short.append(
            "Preserve core treatment train stability while handling peak hydraulic exceedance. "
            "Do not sacrifice solids inventory to throughput."
        )
    elif fst == SCENARIO_PWWF:
        short.append(
            "Prepare for peak hydraulic event: verify cycle timing is set to storm mode "
            "and confirm inDENSE pressure and flow split are within design range."
        )
        short.append(
            "Confirm carrier screening and return performance before peak flow arrival."
        )
        if state in ("Fragile", "Failure Risk"):
            short.append(
                "Prioritise solids retention and ammonia compliance over throughput maximisation. "
                "Reduce cycle compression if treatment stability is at risk."
            )
    elif fst == SCENARIO_AWWF:
        short.append(
            "Monitor cycle throughput utilisation and inDENSE selector performance "
            "under sustained wet weather loading."
        )
        short.append(
            "Verify DO control and wasting strategy to maintain dense biomass "
            "and biofilm performance through the event duration."
        )
    elif state == "Failure Risk":
        short.append(
            "Current load is beyond reliable intensified capacity. "
            "Reduce cycle compression and preserve treatment stability."
        )
        short.append(
            "Prioritise solids retention and ammonia compliance over throughput maximisation."
        )
    elif state == "Fragile":
        short.append(
            "Shift to storm cycle operation and prioritise solids retention "
            "and ammonia stability."
        )
        short.append(
            "Tighten control of DO and wasting strategy to preserve dense biomass "
            "and biofilm performance."
        )
        short.append(
            "Verify selector pressure, flow split, and screen performance before "
            "further load increase."
        )
    elif state == "Tightening":
        short.append(
            "Review cycle timing and fill/decant utilisation against the intensified "
            "throughput envelope."
        )
        short.append(
            "Verify inDENSE pressure and flow split are within design range."
        )
        short.append(
            "Confirm carrier screening and return performance."
        )
    else:  # Stable
        short.append(
            "Maintain standard SBR cycle timing and verify carrier retention "
            "and selector operation."
        )
        short.append(
            "Monitor DO, ammonia, and sludge settleability under intensified operation."
        )

    # ── Medium-term — intensify before expand ─────────────────────────────────
    medium.append(
        "Optimise inDENSE pressure, underflow split, and wasting strategy "
        "to improve solids retention and maximise densified biomass benefit."
    )
    medium.append(
        "Review carrier inventory and retention screen performance to maintain "
        "biofilm contribution to nitrification and capacity."
    )
    medium.append(
        "Validate storm cycle timing against real diurnal and wet weather fill "
        "patterns — confirm 2.5h cycle is achievable without treatment compromise."
    )
    medium.append(
        "Optimise DO control to reduce over-aeration and improve TN/TP removal "
        "under intensified mixed liquor conditions."
    )
    if state in ("Fragile", "Failure Risk"):
        medium.append(
            "Commission independent review of the intensified SBR operating envelope "
            "to confirm maximum reliable throughput before considering civil expansion."
        )
    if not mob.migrate_active:
        medium.append(
            "Evaluate activation of miGRATE carrier programme to augment nitrification "
            "resilience and support further capacity increase within existing tank volume."
        )
    if not mob.indense_active:
        medium.append(
            "Evaluate inDENSE installation to achieve settling improvement and "
            "solids retention benefit not available from miGRATE alone."
        )

    # ── Long-term — intensify first, build later ──────────────────────────────
    long_.append(
        "Extend intensified SBR capacity with additional selector or carrier stages "
        "before adding new reactor volume — exhaust the intensification envelope first."
    )
    long_.append(
        "Add balancing storage to reduce peak fill rate and protect intensified "
        "cycle operation under PWWF conditions."
    )
    long_.append(
        "Expand to a third SBR only if the intensified envelope is demonstrably "
        "exhausted and alternative process intensification options are unavailable."
    )

    # ── Capex ─────────────────────────────────────────────────────────────────
    capex = ""
    if wp.outputs and wp.outputs.capex_estimate:
        if state == "Stable":
            capex = "Operational optimisation: $0.1\u20130.5M for selector and carrier tuning."
        elif state == "Tightening":
            capex = "Process control upgrades: $0.5\u20132M for DO, inDENSE and carrier optimisation."
        else:
            capex = ("Intensification review and potential civil works: "
                     "$2\u201310M+ depending on capacity gap and selected pathway.")

    # ── Risk if no action ─────────────────────────────────────────────────────
    risk_map = {
        "Stable":       "Intensified SBR is performing within design parameters. Sustain current operational focus.",
        "Tightening":   "Throughput growth will exhaust the intensified envelope without operational optimisation.",
        "Fragile":      "Compliance breach risk is elevated under storm or peak conditions without intervention.",
        "Failure Risk": "Overflow and licence breach are imminent. Immediate operational response required.",
    }

    return dict(
        short_term=short, medium_term=medium, long_term=long_,
        capex_range=capex,
        risk_if_no_action=risk_map.get(state, "Insufficient data to assess risk."),
    )


# ── MOB compliance risk ───────────────────────────────────────────────────────

def assess_mob_compliance(wp, mob: MOBStressResult, modes: List[MOBFailureMode]) -> dict:
    """Returns dict matching ComplianceRisk fields."""
    state = mob.state
    tu    = mob.throughput_util

    if state == "Failure Risk" or any(m.severity == "High" for m in modes):
        risk_level = "High"
    elif state == "Fragile" or any(m.severity == "Medium" for m in modes):
        risk_level = "Medium"
    else:
        risk_level = "Low"

    if wp.flow_overflow_flag:
        risk_level = "High"

    # Breach type
    if wp.flow_overflow_flag:
        breach = "Wet weather overflow or bypass event \u2014 notifiable incident"
    elif any(m.title == "Cycle throughput saturation" for m in modes):
        breach = "Compliance risk from cycle throughput saturation and solids retention limit"
    elif any("Selector" in m.title for m in modes):
        breach = "Settling and solids retention risk from selector underperformance"
    elif any("Nitrification" in m.title for m in modes):
        breach = "Ammonia / TN compliance risk from nitrification resilience under load"
    elif any("Settling" in m.title for m in modes):
        breach = "TSS / settling compliance risk without inDENSE solids selection"
    else:
        breach = "TN / TP compliance sensitive to DO and solids selection under intensified operation"

    # Regulatory exposure
    if risk_level == "High":
        if wp.flow_overflow_flag:
            reg_exp = (
                "Overflow or bypass is a notifiable incident under most licence conditions. "
                "Immediate regulator notification required. "
                "Document bypass duration, volume, and receiving environment exposure."
            )
        elif tu >= _FAIL_UTIL:
            reg_exp = (
                "Intensified cycle throughput is saturated. "
                "Compliance with effluent limits for ammonia, TN, and TSS is at immediate risk. "
                "Prepare corrective action plan and notify regulator proactively."
            )
        else:
            reg_exp = (
                "Selector underperformance or settling limitation is creating elevated compliance risk. "
                "Ammonia compliance remains protected by biofilm capacity but "
                "settling resilience depends on selector performance. "
                "Engage regulator if performance margins are persistently narrow."
            )
    elif risk_level == "Medium":
        reg_exp = (
            "Compliance risk is increasing because intensified cycle throughput "
            "is approaching the solids-retention limit. "
            "TN/TP compliance is sensitive to DO control and solids selection. "
            "Maintain enhanced effluent monitoring and prepare contingency cycle programme."
        )
    else:
        reg_exp = (
            "Intensified SBR is operating within the design envelope. "
            "Ammonia compliance is protected by biofilm capacity. "
            "Maintain standard monitoring and selector / carrier performance tracking."
        )

    # Reputational
    if risk_level == "High":
        rep = (
            "Overflow or compliance exceedance events are discoverable and reportable. "
            "Proactive communications strategy and community engagement plan recommended."
        )
    elif risk_level == "Medium":
        rep = (
            "Moderate reputational exposure if effluent limits are missed under storm conditions. "
            "Demonstrates system is operating near the intensified design limit."
        )
    else:
        rep = "Low reputational exposure under current operating conditions."

    return dict(
        compliance_risk=risk_level,
        likely_breach_type=breach,
        regulatory_exposure=reg_exp,
        reputational_risk=rep,
    )
