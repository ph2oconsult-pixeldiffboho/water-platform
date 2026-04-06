"""
WaterPoint — Brownfield Asset Capture Module
=============================================
Validates, normalises, and derives engineering flags from raw brownfield
asset data before it reaches the decision engine.

Entry point:
    result = ingest_brownfield_asset(raw_dict)

Returns:
    BrownfieldAssetResult with:
        .status             "COMPLETE" | "PARTIAL" | "INSUFFICIENT"
        .ctx                plant_context dict (ready for build_upgrade_pathway)
        .data_confidence    0–100
        .errors             list of blocking error strings
        .warnings           list of advisory strings
        .missing_critical   list of missing critical field names
        .missing_secondary  list of missing secondary field names
        .assumptions        list of assumption strings applied
        .guidance           list of user-guidance strings
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ── Status constants ──────────────────────────────────────────────────────────
COMPLETE      = "COMPLETE"
PARTIAL       = "PARTIAL"
INSUFFICIENT  = "INSUFFICIENT"

# ── Result container ──────────────────────────────────────────────────────────

@dataclass
class BrownfieldAssetResult:
    status:             str                     # COMPLETE | PARTIAL | INSUFFICIENT
    ctx:                Dict[str, Any]          # plant_context for decision engine
    data_confidence:    int                     # 0–100
    errors:             List[str]  = field(default_factory=list)
    warnings:           List[str]  = field(default_factory=list)
    missing_critical:   List[str]  = field(default_factory=list)
    missing_secondary:  List[str]  = field(default_factory=list)
    assumptions:        List[str]  = field(default_factory=list)
    guidance:           List[str]  = field(default_factory=list)


# ── Helper ────────────────────────────────────────────────────────────────────

def _get(d: dict, *keys, default=None):
    """Safe nested dict get: _get(d, 'a', 'b') == d.get('a',{}).get('b')."""
    for k in keys:
        if not isinstance(d, dict):
            return default
        d = d.get(k, default)
        if d is None:
            return default
    return d


def _num(d: dict, *keys) -> Optional[float]:
    v = _get(d, *keys)
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# ── Main entry point ──────────────────────────────────────────────────────────

def ingest_brownfield_asset(raw: dict) -> BrownfieldAssetResult:
    """
    Validate, derive, and normalise a brownfield asset data dict.

    Parameters
    ----------
    raw : dict
        Matches the brownfield_asset_data schema documented in the spec.

    Returns
    -------
    BrownfieldAssetResult
        .status = INSUFFICIENT → analysis must be blocked
        .status = PARTIAL      → continue with warnings
        .status = COMPLETE     → all critical + secondary data present
    """
    errors:    List[str] = []
    warnings:  List[str] = []
    missing_c: List[str] = []   # critical
    missing_s: List[str] = []   # secondary
    assumptions: List[str] = []
    guidance:  List[str] = []
    confidence = 100

    # ── Extract plant_overview ─────────────────────────────────────────────────
    ov = raw.get("plant_overview") or {}

    avg_flow  = _num(ov, "average_flow_MLD")
    peak_flow = _num(ov, "peak_flow_MLD")
    design_flow = _num(ov, "design_flow_MLD")
    temp_typ  = _num(ov, "temperature_typical_C")
    temp_min  = _num(ov, "temperature_min_C")
    temp_max  = _num(ov, "temperature_max_C")
    tn_tgt    = _num(ov, "TN_target_mgL")
    tp_tgt    = _num(ov, "TP_target_mgL")
    footprint = ov.get("footprint_constraint", "abundant")
    op_ctx    = ov.get("operator_context", "metro")

    # ── Extract sub-sections ───────────────────────────────────────────────────
    proc = raw.get("process_configuration") or {}
    reactors = raw.get("biological_reactors") or []
    aer  = raw.get("aeration_system") or {}
    clar = raw.get("clarifiers") or {}
    hyd  = raw.get("hydraulics") or {}
    sludge = raw.get("sludge_system") or {}
    fp   = raw.get("footprint") or {}
    pain = raw.get("pain_points") or []

    # ── Part 2: Completeness — critical fields ─────────────────────────────────
    if avg_flow is None:
        missing_c.append("average_flow_MLD")
        guidance.append("Average flow (MLD) is required to size process and assess utilisation.")
    if peak_flow is None:
        missing_c.append("peak_flow_MLD")
        guidance.append("Peak flow (MLD) is required to assess hydraulic stress and storm risk.")
    if tn_tgt is None:
        missing_c.append("TN_target_mgL")
        guidance.append("TN licence target (mg/L) is required for compliance assessment.")
    if temp_typ is None:
        missing_c.append("temperature_typical_C")
        guidance.append("Typical process temperature (°C) is required for nitrification assessment.")

    if missing_c:
        return BrownfieldAssetResult(
            status=INSUFFICIENT,
            ctx={},
            data_confidence=0,
            errors=["Critical design inputs missing: flow, temperature, or licence targets"],
            warnings=warnings,
            missing_critical=missing_c,
            missing_secondary=missing_s,
            assumptions=assumptions,
            guidance=guidance,
        )

    # ── Part 2: Secondary fields ───────────────────────────────────────────────
    cl_limited    = _get(clar, "clarifier_limited")
    svi           = _num(clar, "average_SVI_mLg")
    aer_util_pct  = _num(aer,  "peak_utilisation_percent")
    blower_count  = _num(aer,  "blower_count")
    duty_blowers  = _num(aer,  "duty_blowers")

    if cl_limited is None:
        missing_s.append("clarifier_limited")
        guidance.append(
            "Clarifier performance unknown — provide SVI or indicate if settling is a constraint."
        )
        confidence -= 10
    if aer_util_pct is None:
        missing_s.append("peak_utilisation_percent")
        guidance.append(
            "Aeration utilisation unknown — provide peak blower load or indicate if aeration is constrained."
        )
        confidence -= 10
    if svi is None:
        missing_s.append("average_SVI_mLg")
        guidance.append(
            "SVI unknown — provide settling velocity data or flag if clarifier overflow has occurred."
        )
        confidence -= 10

    # ── Part 3: Consistency checks ─────────────────────────────────────────────
    if avg_flow and peak_flow and peak_flow < avg_flow:
        errors.append("Peak flow must be greater than average flow.")

    if temp_min is not None and temp_typ is not None and temp_min > temp_typ:
        errors.append("Temperature range is not logically ordered (min > typical).")
    if temp_typ is not None and temp_max is not None and temp_typ > temp_max:
        errors.append("Temperature range is not logically ordered (typical > max).")

    if (blower_count is not None and duty_blowers is not None
            and duty_blowers > blower_count):
        errors.append("Duty blowers cannot exceed total installed blowers.")

    if svi is not None and (svi < 50 or svi > 300):
        warnings.append("SVI value outside typical operational range (50–300 mL/g).")
        confidence -= 5

    # If blocking consistency errors, return INSUFFICIENT
    if errors:
        return BrownfieldAssetResult(
            status=INSUFFICIENT,
            ctx={},
            data_confidence=0,
            errors=errors,
            warnings=warnings,
            missing_critical=[],
            missing_secondary=missing_s,
            assumptions=assumptions,
            guidance=guidance,
        )

    # ── Part 4: Derived flags ──────────────────────────────────────────────────
    peak_flow_ratio = (peak_flow / avg_flow) if avg_flow > 0 else 1.0

    storm_flag = peak_flow_ratio >= 3.0
    aer_flag   = (aer_util_pct or 0.) >= 90.
    cl_flag    = (svi or 0.) >= 140.
    sludge_flag = (sludge.get("capacity_status") == "overloaded")

    # Clarifier overloaded — infer from svi or explicit flag
    cl_overloaded = bool(clar.get("clarifier_limited") or cl_flag)

    # ── Reactor volume ─────────────────────────────────────────────────────────
    reactor_volume_m3: Optional[float] = None
    if reactors:
        total_vol = sum(_num(r, "volume_m3") or 0. for r in reactors)
        if total_vol > 0:
            reactor_volume_m3 = total_vol
    if reactor_volume_m3 is None:
        assumptions.append("Reactor volume not provided; HRT-based checks not performed.")

    # ── Clarifier area ─────────────────────────────────────────────────────────
    clar_area_m2 = _num(clar, "total_surface_area_m2")
    if clar_area_m2 is None:
        assumptions.append(
            "Clarifier area not provided; assumed proportional to average flow for SOR checks."
        )
        clar_area_m2 = avg_flow * 35.  # 35 m²/MLD default
        confidence -= 15  # Part 5: -15 for estimated/default value

    # ── Aeration energy proxy ──────────────────────────────────────────────────
    # Use installed capacity × utilisation if available
    aer_kw = _num(aer, "installed_capacity_kW")
    aer_kwh_day: Optional[float] = None
    if aer_kw and aer_util_pct:
        aer_kwh_day = aer_kw * (aer_util_pct / 100.) * 24.

    # ── Influent characterisation ──────────────────────────────────────────────
    # WaterPointInput expects BOD kg/d and TN kg/d; these may not be in the schema
    # so we derive from standard assumptions if absent
    cod_tn_ratio: Optional[float] = None
    carbon_limited = False
    # COD availability check — only flag if truly absent from input
    _cod_raw_input = (
        raw.get("influent_characterisation", {}) or
        raw.get("plant_overview", {}).get("influent_COD_mg_L") or
        raw.get("plant_overview", {}).get("COD_mg_L")
    )
    if tn_tgt and avg_flow and not _cod_raw_input:
        # Without influent data we note the gap
        assumptions.append(
            "Influent COD not provided; carbon availability for denitrification is unconfirmed."
        )
        # Only penalise confidence when TN target is tight (carbon limitation materially
        # affects selection between pathways)
        if tn_tgt <= 5.:
            confidence -= 15  # Part 5: -15 for estimated/default value

    # ── COD fractionation note ─────────────────────────────────────────────────
    if tn_tgt and tn_tgt <= 5.:
        guidance.append(
            "Verification of biodegradable carbon availability is required to confirm the "
            "nitrogen removal strategy and operating assumptions."
        )

    # ── Footprint validation ───────────────────────────────────────────────────
    fp_constraint = footprint if footprint in (
        "abundant", "constrained", "severely_constrained") else "abundant"
    if footprint not in ("abundant", "constrained", "severely_constrained"):
        warnings.append(
            f"Unrecognised footprint_constraint value '{footprint}'; defaulting to 'abundant'."
        )
        confidence -= 5

    # ── Temperature cold flag ──────────────────────────────────────────────────
    cold = temp_typ <= 12.

    # ── Part 5: Data confidence score ─────────────────────────────────────────
    # Deductions already applied; cap 0–100
    confidence = max(0, min(100, confidence))

    # ── Part 6: Determine final status ────────────────────────────────────────
    status = COMPLETE if not missing_s else PARTIAL
    if status == PARTIAL:
        warnings.insert(0,
            "Key constraint indicators missing; results may be less reliable.")

    # ── Build plant_context dict ───────────────────────────────────────────────
    # This dict is the bridge to build_upgrade_pathway and compliance_layer
    ctx: Dict[str, Any] = {
        # Flow
        "plant_size_mld":        avg_flow,
        # Hydraulics extras from hydraulics sub-section
        "storm_impact":          hyd.get("storm_impact", "low"),
        "bottleneck_present":    bool(hyd.get("bottleneck_present", False)),
        "flow_ratio":            peak_flow_ratio,
        "overflow_risk":         storm_flag,
        "wet_weather_peak":      storm_flag,

        # Compliance targets
        "tn_target_mg_l":        tn_tgt,
        "tp_target_mg_l":        tp_tgt or 1.0,
        "nh4_target_mg_l":       1.0,          # default; refine if provided
        "tn_target_basis":       "95th percentile",

        # Temperature
        "temp_celsius":          temp_typ,
        "cold_temperature":      cold,

        # Aeration
        "aeration_constrained":  aer_flag,

        # Clarifier / settling
        "clarifier_overloaded":  cl_overloaded,
        "svi_ml_g":              svi or 0.,
        "clarifier_util":        (aer_util_pct or 0.) / 100.,

        # Hydraulics
        "tn_at_limit":           True,   # conservative default for BF
        "tp_at_limit":           tp_tgt is not None and tp_tgt <= 1.0,
        "nh4_near_limit":        aer_flag,
        "nitrification_flag":    aer_flag or cold,

        # Carbon
        "carbon_limited_tn":     carbon_limited,
        "cod_tn_ratio":          cod_tn_ratio or 10.,
        "cod_mg_l":              None,  # populated from influent characterisation if provided

        # Site
        "footprint_constraint":  fp_constraint,
        "location_type":         op_ctx,
        "greenfield":            False,

        # Process
        "is_sbr":                proc.get("process_type") == "SBR",
        "is_mbr":                proc.get("process_type") == "MBR",
        "has_ifas":              proc.get("process_type") == "IFAS",

        # Sludge
        "high_load":             sludge_flag,

        # Raw asset metadata — passed through for reference
        "_asset_pain_points":    pain,
        "_aer_limited":          aer_flag,
        "_cl_limited":           cl_flag,
        "_sludge_limited":       sludge_flag,
        "_data_confidence":      confidence,
        "_data_status":          status,
    }

    # Aeration energy if derivable
    if aer_kwh_day:
        ctx["aeration_kwh_day"] = aer_kwh_day

    # Reactor volume if known
    if reactor_volume_m3:
        ctx["reactor_volume_m3"] = reactor_volume_m3

    # Clarifier area
    ctx["clarifier_area_m2"] = clar_area_m2

    return BrownfieldAssetResult(
        status=status,
        ctx=ctx,
        data_confidence=confidence,
        errors=errors,
        warnings=warnings,
        missing_critical=[],
        missing_secondary=missing_s,
        assumptions=assumptions,
        guidance=guidance,
    )


# ── Convenience: format result for display ────────────────────────────────────

def format_asset_report(result: BrownfieldAssetResult) -> str:
    """Return a plain-text summary of the ingestion result."""
    lines = []
    status_label = {
        COMPLETE:     "✅ COMPLETE — ready for full analysis",
        PARTIAL:      "⚠️  PARTIAL — analysis will proceed with warnings",
        INSUFFICIENT: "🚫 INSUFFICIENT — analysis blocked",
    }.get(result.status, result.status)

    lines.append(f"Input Data Status:      {status_label}")
    lines.append(f"Input Data Confidence:  {result.data_confidence}/100")

    if result.errors:
        lines.append("\nBlocking Errors:")
        for e in result.errors:
            lines.append(f"  ✗  {e}")

    if result.missing_critical:
        lines.append("\nMissing Critical Fields:")
        for f in result.missing_critical:
            lines.append(f"  ✗  {f}")

    if result.missing_secondary:
        lines.append("\nMissing Secondary Fields:")
        for f in result.missing_secondary:
            lines.append(f"  ⚠  {f}")

    if result.warnings:
        lines.append("\nWarnings:")
        for w in result.warnings:
            lines.append(f"  ⚠  {w}")

    if result.assumptions:
        lines.append("\nAssumptions Applied:")
        for a in result.assumptions:
            lines.append(f"  ~  {a}")

    if result.guidance:
        lines.append("\nData Improvement Guidance:")
        for g in result.guidance:
            lines.append(f"  →  {g}")

    return "\n".join(lines)
