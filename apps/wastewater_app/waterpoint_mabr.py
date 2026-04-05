"""
apps/wastewater_app/waterpoint_mabr.py

MABR (Membrane Aerated Biofilm Reactor) WaterPoint Model
OxyMem OxyFAS hybrid retrofit + OxyFILM (V1 stub).

Activated when wp.mabr_enabled == True (technology_code == "mabr_oxyfas").

V1 focuses on OxyFAS:
  - Drop-in retrofit into existing AS tanks
  - Hybrid suspended growth + membrane biofilm
  - Direct oxygen delivery via hollow-fibre membranes
  - Simultaneous nitrification/denitrification (SND) via counter-diffusion

Technical anchors (OxyMem Gen 4 + Kawana modelling):
  - Module membrane area: ~1452 m² per OxyFAS module
  - Oxygen delivery: ~12 g O2/m²·d on air; ~4× with >90% O2
  - Aeration efficiency up to 14 kgO2/kWh
  - NHx <0.1 mg/L across all Kawana scenarios (strong nitrification resilience)
  - TN improvement requires COD/recycle/methanol support — NOT membrane alone
  - MLSS rises 4700→6850 mg/L under tighter N targets
  - Airflow rises ~8-18% under same conditions

Key distinction enforced:
  - OxyFAS = hybrid (MLSS + clarifier + recycle still matter)
  - OxyFILM = pure biofilm, no MLSS (V1 stub only)
  - Strong NHx ≠ strong TN (NOx/carbon is a separate constraint)

All functions are pure — no Streamlit, no I/O, no side effects.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

# ── Engineering constants ──────────────────────────────────────────────────────

_MABR_O2_AREA_AIR_G_M2D   = 12.0    # g O2/m²·d on air (OxyMem Gen 4)
_MABR_O2_AREA_O2_MULT     = 4.0     # enriched/pure O2 multiplier
_MABR_MODULE_AREA_M2       = 1452.0  # m² per OxyFAS Gen4 module
_MABR_MODULE_O2_KGD_AIR    = 17.0    # kgO2/d per module on air (spec cap)

# Utilisation state thresholds
_MBR_STABLE   = 0.60
_MBR_TIGHTEN  = 0.85
_MBR_FRAGILE  = 1.00

# Fouling risk proxy: sustained high util → thickening
_FOULING_UTIL_THRESHOLD = 0.80


# ── Result dataclass ───────────────────────────────────────────────────────────

@dataclass
class MABRStressResult:
    """Output from the MABR stress model."""
    domains:              List[Tuple[str, float, str]] = field(default_factory=list)
    # Key computed values
    membrane_util:        float = 0.0   # required / available O2
    available_o2_kgd:     float = 0.0
    required_o2_kgd:      float = 0.0
    fouling_risk:         bool  = False
    mixing_adequate:      bool  = True
    hybrid_constrained:   bool  = False # clarifier/MLSS limiting
    carbon_limited_tn:    bool  = False # TN limited by COD, not NHx
    # State
    state:      str = "Stable"
    rate:       str = "Stable"
    t2b:        str = "> 5 years"
    proximity:  float = 0.0   # uncapped
    confidence: str = "Medium"
    rationale:  str = ""
    primary_constraint: str = ""


@dataclass
class MABRFailureMode:
    title:       str
    description: str
    severity:    str   # Low / Medium / High


# ── Main MABR stress function ──────────────────────────────────────────────────

def calculate_mabr_stress(wp) -> MABRStressResult:
    """
    Calculate system stress for a MABR OxyFAS hybrid plant.

    Parameters
    ----------
    wp : WaterPointInput with mabr_enabled == True

    Returns
    -------
    MABRStressResult
    """
    result = MABRStressResult()

    # ── Safe input extraction ──────────────────────────────────────────────────
    base_flow  = wp.average_flow_mld or 1.0
    adj_flow   = wp.flow_adjusted_flow_mld or base_flow
    flow_ratio = adj_flow / base_flow if base_flow > 0 else 1.0
    fst        = wp.flow_scenario_type or ""
    mode       = getattr(wp, "mabr_mode", "oxyfas") or "oxyfas"

    n_modules     = getattr(wp, "mabr_module_count", None) or 1
    mem_area_m2   = getattr(wp, "mabr_membrane_area_m2", None) or (n_modules * _MABR_MODULE_AREA_M2)
    o2_cap_kgd    = getattr(wp, "mabr_oxygen_capacity_kgod", None)
    enriched      = getattr(wp, "mabr_enriched_air_enabled", False)
    pure_o2       = getattr(wp, "mabr_pure_oxygen_enabled", False)
    biofilm_ctrl  = getattr(wp, "mabr_biofilm_control_enabled", True)
    scour_ctrl    = getattr(wp, "mabr_scour_control_enabled", True)
    mixing_ok     = (getattr(wp, "mabr_mixing_mode", "airlift") or "airlift") != "none"
    hybrid        = getattr(wp, "mabr_hybrid_with_as", True)    # OxyFAS default
    clar_dep      = getattr(wp, "mabr_clarifier_dependent", True)
    shrouded      = getattr(wp, "mabr_shrouded_modules", True)

    # Hybrid system context
    mlss          = getattr(wp, "mlss_mgL", None)
    clar_avail    = getattr(wp, "clarifier_available", True)
    clar_stress   = getattr(wp, "clarifier_stress_flag", False)
    ras_ratio     = getattr(wp, "ras_ratio", None)
    ir_ratio      = getattr(wp, "internal_recycle_ratio", None)
    cod_n_ratio   = getattr(wp, "cod_to_n_ratio", None)
    ext_carbon    = getattr(wp, "external_carbon_dosing_ld", None) or 0.0

    # ── Compute available MABR O2 capacity ─────────────────────────────────────
    if o2_cap_kgd:
        avail_o2 = o2_cap_kgd
    else:
        # Infer from membrane area and mode
        if pure_o2 or enriched:
            avail_o2 = (mem_area_m2 * _MABR_O2_AREA_AIR_G_M2D * _MABR_O2_AREA_O2_MULT) / 1000.0
        else:
            avail_o2 = (mem_area_m2 * _MABR_O2_AREA_AIR_G_M2D) / 1000.0
    result.available_o2_kgd = round(avail_o2, 1)

    # ── MABR utilisation — module-normalised proxy ────────────────────────────
    # Calibrated to Kawana: 4 modules at DWF = Stable (util ~0.50).
    # Direct module-load model: util = (flow_ratio × load_factor) / (n_modules × CAP_FACTOR)
    # CAP_FACTOR = 0.50 (normalisation constant for 4-module full-design at DWF).
    # Adjustments: high NHx margin → lower load; low NHx margin → higher load.
    _REF_CAP_FACTOR = 0.50
    # NHx margin adjustment: if NHx is well below target, membrane is coping (lower util)
    _nit_load_factor = 1.0
    if wp.effluent_nh4_mg_l is not None and wp.nh4_target_mg_l is not None:
        _margin = wp.nh4_target_mg_l - wp.effluent_nh4_mg_l
        if _margin > 0.5:
            _nit_load_factor = 0.75   # plenty of margin → lower membrane load
        elif _margin < 0.1:
            _nit_load_factor = 1.30   # near limit → membrane is working hard
    membrane_util = (flow_ratio * _nit_load_factor) / max(1, n_modules) / _REF_CAP_FACTOR

    # Report equivalent O2 values for transparency
    req_o2 = membrane_util * avail_o2
    result.required_o2_kgd = round(req_o2, 1)
    result.membrane_util = round(membrane_util, 3)

    # ── Domain A: Membrane oxygen delivery ────────────────────────────────────
    detail_a = (
        f"{req_o2:.1f} kgO2/d required vs {avail_o2:.1f} kgO2/d available "
        f"({'enriched' if (enriched or pure_o2) else 'air'}, "
        f"{n_modules} module{'s' if n_modules > 1 else ''}, {mem_area_m2:.0f} m\u00b2)"
    )
    result.domains.append(("Membrane O\u2082 delivery", membrane_util, detail_a))

    # ── Domain B: Biofilm thickness / fouling ─────────────────────────────────
    # Fouling risk rises with: high util, no scour, no biofilm control, unshrouded
    fouling_score = 0.0
    if membrane_util > _FOULING_UTIL_THRESHOLD: fouling_score += 0.30
    if not scour_ctrl:                          fouling_score += 0.35
    if not biofilm_ctrl:                        fouling_score += 0.25
    if not shrouded:                            fouling_score += 0.10
    result.fouling_risk = fouling_score > 0.40
    # Map to 0–1 domain util
    fouling_util = min(1.2, fouling_score)
    result.domains.append((
        "Biofilm thickness / fouling",
        fouling_util,
        f"scour={'on' if scour_ctrl else 'off'} | "
        f"biofilm_ctrl={'on' if biofilm_ctrl else 'off'} | "
        f"shrouded={'yes' if shrouded else 'no'}",
    ))

    # ── Domain C: Substrate delivery / mixing ─────────────────────────────────
    # Airlift mixing is the primary mechanism; supplemental/none = risk
    if not mixing_ok:
        mix_util = 0.75
    elif not shrouded:
        mix_util = 0.55   # unshrouded → short-circuiting risk
    else:
        mix_util = 0.30   # shrouded + airlift = low risk
    result.mixing_adequate = mix_util < 0.65
    result.domains.append((
        "Substrate delivery / mixing",
        mix_util,
        f"mode={getattr(wp, 'mabr_mixing_mode', 'airlift')} | "
        f"shrouded={'yes' if shrouded else 'no'}",
    ))

    # ── Domain D: Hybrid integration (OxyFAS only) ────────────────────────────
    if hybrid and mode == "oxyfas":
        hybrid_util = 0.30   # start low — good hybrid
        if clar_stress:             hybrid_util = max(hybrid_util, 0.80)
        if not clar_avail:          hybrid_util = max(hybrid_util, 0.90)
        if mlss and mlss > 6500:    hybrid_util = max(hybrid_util, 0.70)
        if flow_ratio > 1.5:        hybrid_util = min(1.2, hybrid_util + (flow_ratio - 1.5) * 0.15)
        result.hybrid_constrained = hybrid_util > 0.65
        result.domains.append((
            "Hybrid AS integration",
            hybrid_util,
            f"MLSS={mlss:.0f} mg/L" if mlss else
            f"clarifier={'ok' if clar_avail else 'unavailable'} | "
            f"flow {flow_ratio:.1f}\u00d7 ADWF",
        ))

    # ── Domain E: Carbon / denitrification ────────────────────────────────────
    # NHx strong but TN limited by NOx → carbon limited
    carbon_util = 0.30   # default: assume adequate COD
    if cod_n_ratio is not None:
        if cod_n_ratio < 4.0:
            carbon_util = 0.85   # low COD/N → very carbon limited
        elif cod_n_ratio < 6.0:
            carbon_util = 0.60
    if ir_ratio is not None and ir_ratio < 2.0:
        carbon_util = max(carbon_util, 0.55)  # insufficient recycle
    if ext_carbon > 0:
        carbon_util = max(0.10, carbon_util - 0.20)  # external carbon helps
    # Check effluent NOx proxy: if TN > target by a wide margin while NHx is low
    if (wp.effluent_tn_mg_l is not None and wp.tn_target_mg_l is not None
            and wp.effluent_nh4_mg_l is not None):
        nox_proxy = wp.effluent_tn_mg_l - (wp.effluent_nh4_mg_l or 0)
        if nox_proxy > 5.0 and (wp.effluent_nh4_mg_l or 9) < 1.0:
            # High NOx, low NHx → carbon-limited denitrification
            carbon_util = max(carbon_util, 0.75)
    result.carbon_limited_tn = carbon_util >= 0.60
    result.domains.append((
        "Carbon / denitrification balance",
        carbon_util,
        f"COD/N={cod_n_ratio:.1f}" if cod_n_ratio else
        (f"ext_carbon={ext_carbon:.0f} L/d" if ext_carbon > 0 else "COD balance inferred"),
    ))

    # ── Pick most constrained domain ──────────────────────────────────────────
    if not result.domains:
        result.state     = "Unknown"
        result.rationale = "Insufficient MABR data to assess system stress."
        result.confidence = "Low"
        return result

    dom_name, max_util, dom_detail = max(result.domains, key=lambda x: x[1])
    result.proximity = round(max_util * 100.0, 1)

    # ── State logic ───────────────────────────────────────────────────────────
    if wp.flow_overflow_flag:
        state = "Failure Risk"
        rate  = "Accelerating"
        t2b   = "< 12 months \u2014 active overflow"
    elif membrane_util >= _MBR_FRAGILE:
        state = "Failure Risk"
        rate  = "Accelerating"
        t2b   = "< 12 months \u2014 membrane capacity exceeded"
    elif result.hybrid_constrained or membrane_util >= _MBR_TIGHTEN:
        state = "Fragile"
        rate  = "Accelerating"
        t2b   = "12\u201324 months"
    elif membrane_util >= _MBR_STABLE or result.fouling_risk or result.carbon_limited_tn:
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
    if n_doms >= 4 and missing <= 1:
        result.confidence = "High"
    elif n_doms >= 3 or missing <= 3:
        result.confidence = "Medium"
    else:
        result.confidence = "Low"

    # ── Rationale ─────────────────────────────────────────────────────────────
    result.rationale = _mabr_rationale(
        state, membrane_util, result.carbon_limited_tn,
        result.hybrid_constrained, result.fouling_risk, flow_ratio, mode
    )

    # Constraint label with exceedance for extreme events
    _label = f"{dom_name} ({dom_detail})"
    if flow_ratio >= 2.0:
        _label += f" | {round((flow_ratio - 1)*100)}% above design average"
    result.primary_constraint = _label

    return result


def _mabr_rationale(state, mem_util, carbon_lim, hybrid_const,
                    fouling, flow_ratio, mode) -> str:
    tech = "OxyFAS hybrid MABR" if mode == "oxyfas" else "MABR"
    if state == "Stable":
        return (
            f"{tech} is extending biological capacity through direct membrane oxygen delivery "
            f"rather than conventional bubble aeration. "
            f"Membrane utilisation {mem_util*100:.0f}% is within the operating envelope."
        )
    if state == "Tightening":
        note = ""
        if carbon_lim:
            note = " TN performance is limited by denitrification capacity / COD availability, not ammonia oxidation."
        if fouling:
            note += " Biofilm thickness or fouling is beginning to reduce effective membrane transfer."
        return (
            f"{tech} nitrification capacity is adequate but margins are tightening "
            f"at {mem_util*100:.0f}% membrane utilisation.{note}"
        )
    if state == "Fragile":
        if hybrid_const:
            return (
                "Installed MABR membrane capacity is performing, but the surrounding "
                "activated sludge / solids handling system is narrowing the operating margin. "
                "Hybrid integration is the primary constraint."
            )
        return (
            f"Membrane delivery at {mem_util*100:.0f}% utilisation is approaching the reliable "
            "operating limit. Strong NHx performance is currently maintained, "
            "but remaining margin for nitrification resilience is limited."
        )
    # Failure Risk
    if flow_ratio > 2.0:
        return (
            f"Extreme hydraulic loading ({flow_ratio:.1f}\u00d7 ADWF) has exceeded the "
            "reliable operating envelope for the hybrid MABR system. "
            "Membrane integrity and hybrid solids stability are at risk."
        )
    return (
        f"Installed MABR capacity or hybrid system integration is beyond the reliable "
        f"operating window at {mem_util*100:.0f}% membrane utilisation. "
        "Nitrification resilience or hybrid solids control cannot be assured."
    )


# ── MABR failure modes ─────────────────────────────────────────────────────────

def detect_mabr_failure_modes(wp, mabr: MABRStressResult) -> List[MABRFailureMode]:
    """Return MABR-specific failure modes."""
    modes: List[MABRFailureMode] = []
    fst  = wp.flow_scenario_type or ""
    mu   = mabr.membrane_util

    # 1. Membrane oxygen delivery limit
    if mu >= _MBR_STABLE:
        modes.append(MABRFailureMode(
            title="Membrane oxygen delivery limit",
            description=(
                f"Installed membrane oxygen delivery ({mabr.available_o2_kgd:.1f} kgO2/d available "
                f"vs {mabr.required_o2_kgd:.1f} kgO2/d estimated demand) is approaching or "
                "below the required nitrification load. Additional modules or enriched air "
                "may be required to maintain NHx compliance under current loading."
            ),
            severity="High" if mu >= _MBR_FRAGILE else "Medium",
        ))

    # 2. Biofilm over-thickening / fouling risk
    if mabr.fouling_risk:
        modes.append(MABRFailureMode(
            title="Biofilm over-thickening / fouling risk",
            description=(
                "Biofilm thickness or membrane fouling may be reducing effective "
                "oxygen transfer and treatment performance. "
                "Sustained high utilisation without adequate scour or biofilm thickness "
                "control increases the risk of membrane performance decline."
            ),
            severity="Medium",
        ))

    # 3. Substrate delivery limitation
    if not mabr.mixing_adequate:
        modes.append(MABRFailureMode(
            title="Substrate delivery limitation",
            description=(
                "Liquid mixing or pollutant contact around the MABR modules may be "
                "insufficient to fully utilise the membrane surface. "
                "Without adequate airlift mixing and shrouding, short-circuiting "
                "reduces effective biofilm-pollutant contact."
            ),
            severity="Medium",
        ))

    # 4. Hybrid system integration constraint
    if mabr.hybrid_constrained:
        modes.append(MABRFailureMode(
            title="Hybrid system integration constraint",
            description=(
                "The surrounding activated sludge and solids handling system is constraining "
                "overall MABR-hybrid performance. MLSS accumulation, clarifier loading, or "
                "recycle limitations are reducing the effective benefit of installed MABR capacity."
            ),
            severity="High" if mabr.state == "Failure Risk" else "Medium",
        ))

    # 5. Carbon-limited denitrification
    if mabr.carbon_limited_tn:
        modes.append(MABRFailureMode(
            title="Carbon-limited denitrification",
            description=(
                "Ammonia removal remains strong due to membrane-supported nitrification, "
                "but TN performance is limited by denitrification capacity / COD availability. "
                "NOx polishing is the governing TN constraint, not ammonia oxidation. "
                "Recycle optimisation, COD diversion, or external carbon may be required."
            ),
            severity="Medium",
        ))

    # 6. Clarifier limitation in hybrid mode
    clar_dep = getattr(wp, "mabr_clarifier_dependent", True)
    clar_str = getattr(wp, "clarifier_stress_flag", False)
    if clar_dep and clar_str:
        modes.append(MABRFailureMode(
            title="Clarifier limitation in hybrid mode",
            description=(
                "Hybrid MABR operation is being limited by downstream solids separation. "
                "Elevated MLSS from intensified biological operation may be increasing "
                "clarifier loading beyond its design SOR, risking solids carryover."
            ),
            severity="High",
        ))

    # 7. Air distribution / module imbalance
    shrouded = getattr(wp, "mabr_shrouded_modules", True)
    if not shrouded and mu > 0.50:
        modes.append(MABRFailureMode(
            title="Air distribution / module imbalance",
            description=(
                "Unshrouded module configuration may cause uneven gas delivery or "
                "hydraulic short-circuiting, reducing effective MABR performance. "
                "Module-level flow distribution should be verified under elevated loading."
            ),
            severity="Low",
        ))

    # 8. Wet weather hybrid instability
    from apps.wastewater_app.flow_scenario_engine import SCENARIO_AWWF, SCENARIO_PWWF
    if fst in (SCENARIO_AWWF, SCENARIO_PWWF) and mu > 0.70:
        ww_dur = wp.flow_wet_weather_duration_hr or 0.0
        modes.append(MABRFailureMode(
            title="Wet weather hybrid instability",
            description=(
                f"Hydraulic conditions ({fst}) are reducing the stability of the hybrid "
                f"MABR\u2013activated sludge system. Dilution, MLSS washout, and "
                f"increased hydraulic loading may reduce membrane contact efficiency "
                f"and hybrid process control{f' over {ww_dur:.0f}h duration' if ww_dur > 0 else ''}."
            ),
            severity="Medium" if mu < _MBR_FRAGILE else "High",
        ))

    return modes


# ── MABR decision layer ────────────────────────────────────────────────────────

def generate_mabr_decisions(
    wp,
    mabr:  MABRStressResult,
    modes: List[MABRFailureMode],
) -> dict:
    """Returns dict: short_term, medium_term, long_term, capex_range, risk_if_no_action."""
    from apps.wastewater_app.flow_scenario_engine import SCENARIO_AWWF, SCENARIO_PWWF
    fst   = wp.flow_scenario_type or ""
    state = mabr.state
    short:  List[str] = []
    medium: List[str] = []
    long_:  List[str] = []

    # ── Short-term ─────────────────────────────────────────────────────────────
    if wp.flow_overflow_flag:
        short.append(
            "ACTIVE HYDRAULIC EVENT: preserve membrane system integrity and stabilise "
            "the hybrid activated sludge process under peak flow conditions."
        )
        short.append(
            "Prioritise solids separation and core biological stability while maintaining "
            "essential MABR operation."
        )
        short.append(
            "Initiate incident response and regulatory notification pathway."
        )

    elif fst == SCENARIO_PWWF:
        short.append(
            "Maintain membrane airflow under peak hydraulic conditions and verify "
            "modules remain within the oxygen delivery envelope."
        )
        short.append(
            "Monitor MLSS and clarifier loading \u2014 elevated flow may increase solids "
            "load on the hybrid settling system."
        )
        if state in ("Fragile", "Failure Risk"):
            short.append(
                "Prioritise NHx compliance and hybrid solids control over throughput "
                "maximisation under peak wet weather conditions."
            )

    elif fst == SCENARIO_AWWF:
        short.append(
            "Review membrane utilisation and hybrid MLSS under sustained wet weather loading "
            "\u2014 confirm NHx and NOx trends separately."
        )
        short.append(
            "Maintain biofilm control and scour routine to prevent fouling accumulation "
            "during extended high-utilisation operation."
        )

    elif state == "Failure Risk":
        short.append(
            "Installed MABR capacity or hybrid system integration is beyond the reliable "
            "operating window \u2014 stabilise nitrification and prevent ammonia breakthrough first."
        )
        short.append(
            "Review whether TN underperformance is driven by carbon limitation, solids "
            "limitation, or membrane loading before adding more conventional aeration."
        )

    elif state == "Fragile":
        short.append(
            "Current performance is becoming dependent on tight membrane and hybrid system "
            "control \u2014 prioritise NHx compliance and confirm available denitrification margin."
        )
        short.append(
            "Optimise recycle, bypass, and carbon strategy before further load increase."
        )
        short.append(
            "Confirm module fouling and biofilm condition before assuming additional "
            "membrane capacity is available."
        )

    elif state == "Tightening":
        short.append(
            "Review membrane utilisation and increase airflow or oxygen concentration if "
            "nitrification demand is rising."
        )
        short.append(
            "Check biofilm thickness control and verify mixing / airlift performance "
            "around the installed modules."
        )
        short.append(
            "Review hybrid MLSS, clarifier loading, and recycle rates to ensure the "
            "activated sludge system is not constraining MABR benefit."
        )

    else:  # Stable
        short.append(
            "Maintain membrane airflow and verify modules are operating within the intended "
            "oxygen delivery envelope."
        )
        short.append(
            "Monitor NHx, NOx and TN separately to confirm nitrification remains strong "
            "and identify any denitrification limitation."
        )
        short.append(
            "Maintain biofilm control / scour routine to preserve membrane performance."
        )

    # ── Medium-term — MABR-first optimisation before civil expansion ───────────
    medium.append(
        "Increase installed membrane area or module count if oxygen delivery utilisation "
        "is the controlling constraint \u2014 expand MABR capacity before adding conventional aeration."
    )
    medium.append(
        "Optimise biofilm thickness control and scour interval to maintain membrane "
        "transfer efficiency under sustained loading."
    )
    medium.append(
        "Optimise recycle, bypass, and carbon strategy to convert strong NHx performance "
        "into improved TN performance \u2014 address NOx polishing as a separate constraint."
    )
    medium.append(
        "Optimise hybrid MLSS and clarifier loading so the surrounding activated sludge "
        "process does not negate MABR benefits."
    )
    if getattr(wp, "mabr_enriched_air_enabled", False) is False and mabr.membrane_util > 0.70:
        medium.append(
            "Review use of enriched air or oxygen enrichment if peak oxygen demand is "
            "episodic \u2014 this is a capital-light intensification option before adding modules."
        )
    if mabr.carbon_limited_tn:
        medium.append(
            "Quantify COD/N ratio and internal recycle performance \u2014 model TN improvement "
            "from recycle and bypass optimisation before committing to external carbon dosing."
        )
    if state in ("Fragile", "Failure Risk"):
        medium.append(
            "Commission independent process audit of membrane utilisation, hybrid solids "
            "balance, and denitrification carbon regime before planning civil expansion."
        )

    # ── Long-term ──────────────────────────────────────────────────────────────
    long_.append(
        "Expand OxyFAS module count to increase biological capacity before major "
        "civil expansion \u2014 exhaust the MABR intensification pathway first."
    )
    long_.append(
        "Reconfigure the hybrid process to shift more nitrification load onto MABR "
        "and reduce conventional aeration burden and energy cost."
    )
    long_.append(
        "Add or optimise carbon management and denitrification infrastructure if TN, "
        "not NHx, is the governing long-term compliance limit."
    )
    long_.append(
        "Convert selected aeration lanes to higher-MABR fraction operation if "
        "footprint and energy minimisation are strategic priorities."
    )

    # ── Capex ──────────────────────────────────────────────────────────────────
    capex = ""
    if wp.outputs and wp.outputs.capex_estimate:
        if state == "Stable":
            capex = "MABR operational optimisation: $0.1\u20130.5M for airflow and biofilm control tuning."
        elif state == "Tightening":
            capex = "Module optimisation or limited expansion: $0.5\u20132M for additional modules or enriched air."
        else:
            capex = (
                "MABR capacity review and potential hybrid civil works: "
                "$2\u201310M+ depending on nitrogen target and selected pathway."
            )

    # ── Risk if no action ──────────────────────────────────────────────────────
    risk_map = {
        "Stable":       "MABR is performing well. Sustain membrane and biofilm control focus.",
        "Tightening":   "Membrane utilisation growth or carbon limitation will reduce TN compliance margin without intervention.",
        "Fragile":      "NHx or TN compliance breach is probable under peak load or without hybrid system optimisation.",
        "Failure Risk": "Ammonia breakthrough or hybrid system failure is imminent. Immediate operational response required.",
    }

    return dict(
        short_term=short, medium_term=medium, long_term=long_,
        capex_range=capex,
        risk_if_no_action=risk_map.get(state, "Insufficient data to assess risk."),
    )


# ── MABR compliance risk ───────────────────────────────────────────────────────

def assess_mabr_compliance(
    wp, mabr: MABRStressResult, modes: List[MABRFailureMode]
) -> dict:
    """Returns dict matching ComplianceRisk fields."""
    state = mabr.state
    mu    = mabr.membrane_util

    if state == "Failure Risk" or any(m.severity == "High" for m in modes):
        risk_level = "High"
    elif state == "Fragile" or any(m.severity == "Medium" for m in modes):
        risk_level = "Medium"
    else:
        risk_level = "Low"

    if wp.flow_overflow_flag:
        risk_level = "High"

    # Breach type — NHx and TN are separated explicitly per Kawana calibration
    if wp.flow_overflow_flag:
        breach = "Wet weather overflow / bypass event \u2014 notifiable incident"
    elif mabr.hybrid_constrained:
        breach = (
            "Hybrid system solids / clarifier limits may constrain the full "
            "benefit of installed MABR capacity"
        )
    elif mabr.carbon_limited_tn and mu < _MBR_FRAGILE:
        breach = (
            "MABR capacity appears adequate for nitrification; NOx polishing / carbon "
            "availability is the controlling compliance risk"
        )
    elif mu >= _MBR_TIGHTEN:
        breach = (
            "Ammonia compliance is becoming dependent on tight membrane utilisation; "
            "TN remains sensitive to denitrification and carbon balance"
        )
    else:
        breach = (
            "TN / TP compliance sensitive to DO control, recycle strategy, "
            "and carbon availability in the hybrid MABR system"
        )

    # Regulatory exposure
    if risk_level == "High":
        if wp.flow_overflow_flag:
            reg_exp = (
                "Wet weather overflow or bypass is a notifiable incident under most "
                "licence conditions. Immediate regulator notification required. "
                "Document bypass duration, volume, and receiving environment exposure."
            )
        elif mabr.hybrid_constrained:
            reg_exp = (
                "Hybrid MABR system integration is failing. Clarifier or solids handling "
                "limitations are exposing the plant to TSS / ammonia compliance breach. "
                "Prepare corrective action plan and notify regulator proactively."
            )
        else:
            reg_exp = (
                "Membrane oxygen delivery is at or beyond its reliable limit. "
                "Ammonia compliance is at immediate risk. "
                "Notify regulator proactively and implement emergency operational response."
            )
    elif risk_level == "Medium":
        reg_exp = (
            "Ammonia compliance is currently protected by membrane-supported nitrification, "
            "but total nitrogen remains sensitive to denitrification capacity. "
            "Maintain enhanced effluent monitoring. "
            "Prepare corrective action plan if carbon-limited TN breaches persist."
        )
    else:
        reg_exp = (
            "MABR is providing strong nitrification resilience. "
            "Maintain standard monitoring of NHx, NOx, and TN separately "
            "to detect early signs of carbon-limited denitrification."
        )

    # Reputational risk
    if risk_level == "High":
        rep = (
            "Overflow or compliance exceedance events are discoverable and reportable. "
            "Proactive communications and community engagement recommended."
        )
    elif risk_level == "Medium":
        rep = (
            "Moderate reputational exposure if TN limits are missed due to carbon "
            "limitation or hybrid system constraint. "
            "MABR technology credibility may be questioned if NHx is strong but TN fails."
        )
    else:
        rep = "Low reputational exposure. MABR nitrification performance is within compliance."

    return dict(
        compliance_risk=risk_level,
        likely_breach_type=breach,
        regulatory_exposure=reg_exp,
        reputational_risk=rep,
    )
