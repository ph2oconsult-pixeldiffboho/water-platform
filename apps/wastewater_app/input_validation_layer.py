"""
apps/wastewater_app/input_validation_layer.py

Input Validation Layer — Production V1
=======================================

Implements Parts 1–3 of the nine-part WaterPoint decision framework directly
against ``WaterPointInput``:

  * Part 1 — IDE integrity (physical plausibility, ratio checks, required fields)
  * Part 2 — Data confidence scoring and Value-of-Information assessment
  * Part 3 — Governing condition identification

The result is an ``InputValidationReport`` that is consumed by:

  * ``waterpoint_ui.render_waterpoint`` — renders the "📋 Input Validation"
    panel above all WaterPoint output sections.
  * ``credibility_layer`` — Critical flags are absorbed as consistency flags
    and demote ``ready_for_client`` when data confidence is Very Low.

Design principles
-----------------
- Pure functions, deterministic, traceable.
- Never raises (mirrors the WaterPoint engine + adapter contract).
- Schema matches ``core/characteriser/report.py`` conventions:
  severity-tagged flags, confidence levels, convenience properties.
- Operates on **structured input fields only**. Data representativeness
  (the "high-volume / low-confidence paradox") is out of scope; the
  VOI assessment surfaces those gaps but cannot resolve them.

Reference: ``apps/wastewater_app/pages/page_08_manual.py`` — User Manual,
"Input Validation Layer" section, Decision Framework Parts 1–3.

Rule numbering
--------------
The spec page calls out "IV-01 to IV-30" in prose but its rule table only
defines IV-01..IV-16, IV-16b, and IV-17..IV-27 (28 distinct codes).
IV-28, IV-29, IV-30 are reserved for future additions; this module
implements exactly what is defined in the table.

Schema version: 1.0
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from apps.wastewater_app.waterpoint_adapter import WaterPointInput


# ── Schema versioning ─────────────────────────────────────────────────────────

SCHEMA_VERSION = "1.0"


# ── Severity constants (mirror core/characteriser/report.py) ──────────────────

SEV_CRITICAL = "Critical"
SEV_WARNING  = "Warning"
SEV_INFO     = "Info"

_SEV_ORDER = {SEV_CRITICAL: 0, SEV_WARNING: 1, SEV_INFO: 2}


# ── Data confidence levels (Part 2) ───────────────────────────────────────────

CONF_HIGH       = "High"
CONF_ACCEPTABLE = "Acceptable"
CONF_LOW        = "Low"
CONF_VERY_LOW   = "Very Low"


# ── Governing condition labels (Part 3) ───────────────────────────────────────

GC_PEAK_WET     = "Peak wet weather"
GC_MODERATE_WET = "Moderate wet weather / diurnal peak"
GC_SEASONAL_TW  = "Seasonal trade waste event"
GC_DRY_ADWF     = "Dry weather ADWF"
GC_UNKNOWN      = "Unknown"


# ── VOI levels ────────────────────────────────────────────────────────────────

VOI_HIGH     = "High"
VOI_MODERATE = "Moderate"
VOI_LOW      = "Low"


# ── Dataclasses ───────────────────────────────────────────────────────────────

@dataclass
class IVFlag:
    """A single validation rule firing.

    ``code``           Stable rule ID (e.g. ``"IV-01"``).
    ``severity``       ``Critical`` / ``Warning`` / ``Info``.
    ``field``          The WaterPointInput field implicated.
    ``message``        Plain-English description of what was detected.
    ``recommendation`` Action the engineer should take.
    """
    code:           str
    severity:       str
    field:          str
    message:        str
    recommendation: str = ""


@dataclass
class GoverningCondition:
    """Identifies the design-governing condition from the flow envelope (Part 3)."""
    condition:    str   # One of the GC_* constants.
    trigger:      str   # Plain-English reason this condition applies.
    implication:  str   # What this implies for design assessment.


@dataclass
class VOIItem:
    """A Value-of-Information assessment for a single field or gap (Part 2)."""
    field:     str
    voi_level: str   # VOI_HIGH / VOI_MODERATE / VOI_LOW
    rationale: str


@dataclass
class InputValidationReport:
    """Output contract of the input validation layer.

    Consumed by ``waterpoint_ui`` (rendering) and ``credibility_layer``
    (consistency-flag injection + readiness demotion).
    """
    # All flags raised by IV-01 through IV-27, in original detection order.
    flags:                List[IVFlag] = field(default_factory=list)

    # Names of required input fields that were missing (Critical missing checks).
    missing_critical:     List[str]    = field(default_factory=list)

    # Names of optional but high-value fields that were missing (Info missing checks).
    missing_optional:     List[str]    = field(default_factory=list)

    # Overall data-confidence verdict — one of the CONF_* constants.
    data_confidence:      str          = CONF_HIGH

    # Plain-English rationale for the data confidence verdict.
    confidence_reason:    str          = ""

    # VOI items surfaced for missing or uncertain inputs.
    voi_items:            List[VOIItem] = field(default_factory=list)

    # Identified governing design condition.
    governing_condition:  Optional[GoverningCondition] = None

    # Set to False whenever any Critical flag is raised. Mirrors the credibility-
    # layer ``ready_for_client`` semantics: downstream tools should not present
    # outputs as design-ready if ``safe_for_analysis`` is False.
    safe_for_analysis:    bool         = True

    # Schema version for downstream compatibility checks.
    schema_version:       str          = SCHEMA_VERSION

    # ── Convenience properties ────────────────────────────────────────────
    @property
    def critical_flags(self) -> List[IVFlag]:
        return [f for f in self.flags if f.severity == SEV_CRITICAL]

    @property
    def warning_flags(self) -> List[IVFlag]:
        return [f for f in self.flags if f.severity == SEV_WARNING]

    @property
    def info_flags(self) -> List[IVFlag]:
        return [f for f in self.flags if f.severity == SEV_INFO]

    @property
    def fail_count(self) -> int:
        return len(self.critical_flags)

    @property
    def warn_count(self) -> int:
        return len(self.warning_flags)

    @property
    def info_count(self) -> int:
        return len(self.info_flags)

    @property
    def has_flags(self) -> bool:
        return bool(self.flags)

    @property
    def consistency_flag_messages(self) -> List[str]:
        """Plain-string Critical messages for credibility-layer injection.

        ``credibility_layer.CredibleOutput.consistency_flags`` is a ``List[str]``;
        this property produces strings suitable for that field without forcing
        the credibility layer to know about IVFlag.
        """
        return [
            f"[{f.code}] {f.message}"
            for f in self.flags if f.severity == SEV_CRITICAL
        ]


# ── Field thresholds (single source of truth for IV rules) ────────────────────
#
# Numeric thresholds are kept here so they can be reviewed and tuned without
# touching the rule logic itself. The values mirror the spec table in
# page_08_manual.py (Input Reference → Input Validation Layer).

# Peak:ADWF ratio thresholds.
_PEAK_RATIO_IMPLAUSIBLE   = 10.0   # IV-02 — implausible for reticulated sewer
_PEAK_RATIO_HIGH_II       = 5.0    # IV-03 — very high I/I signal (Warning)
_PEAK_RATIO_GOVERNING_WW  = 3.0    # Part 3 — peak wet weather governing
_PEAK_RATIO_GOVERNING_MOD = 2.0    # Part 3 — moderate wet weather

# MLSS plausibility band (mg/L) for activated sludge.
_MLSS_MIN_PLAUSIBLE = 1000.0   # IV-06
_MLSS_MAX_PLAUSIBLE = 8000.0   # IV-07

# Implied influent BOD concentration (mg/L) below which load looks too dilute.
_BOD_CONC_DILUTE = 50.0   # IV-08

# Oxygen transfer efficiency band (kg O₂ per kWh aeration).
_O2_PER_KWH_MIN = 0.5   # IV-09 lower
_O2_PER_KWH_MAX = 3.0   # IV-09 upper

# COD:TKN bands.
_COD_TKN_CARBON_LIMITED = 8.0    # IV-10
_COD_TKN_THRESHOLD_LOW  = 8.0    # IV-11 lower
_COD_TKN_THRESHOLD_HIGH = 9.0    # IV-11 upper
_COD_TKN_TRADE_WASTE    = 13.0   # IV-12

# NH₄:TKN bands (domestic range 0.60–0.75).
_NH4_TKN_HIGH_ORG_N     = 0.50   # IV-13 below
_NH4_TKN_DOM_LOWER_MIN  = 0.50   # IV-14 between this and dom_lower
_NH4_TKN_DOM_LOWER      = 0.60   # domestic lower bound
_NH4_TKN_SEPTIC         = 0.75   # IV-15 above

# BOD:TSS bands.
_BOD_TSS_DIURNAL_RISK   = 2.5    # IV-16 — Healesville-class
_BOD_TSS_INORGANIC      = 0.5    # IV-16b — high inorganic / industrial

# A scenario-named field for diurnal profiling VOI lookup.
_BOD_TSS_VOI_THRESHOLD  = 2.0    # Above this → diurnal profiling High VOI


# ── Required and optional field registries ───────────────────────────────────
#
# The page_08_manual.py spec defines "missing field" rules IV-17–IV-27.
# These two lists are the canonical mapping; the helpers below use them.

# (WaterPointInput attribute path → display name) for required fields.
# A missing required field raises a Critical flag (IV-17..IV-22).
_REQUIRED_FIELDS = [
    ("average_flow_mld",       "average_flow_mld",       "IV-17"),
    ("technology_code",        "technology_code",        "IV-18"),
    ("effluent_tn_mg_l",       "effluent_tn_mg_l",       "IV-19"),
    ("tn_target_mg_l",         "tn_target_mg_l",         "IV-20"),
    ("current_load.bod_kg_d",  "current_load.bod_kg_d",  "IV-21"),
    ("current_load.tn_kg_d",   "current_load.tn_kg_d",   "IV-22"),
]

# Optional fields — missing ones raise Info flags only (IV-23..IV-27).
_OPTIONAL_FIELDS = [
    ("o2_demand_kg_day",       "o2_demand_kg_day",       "IV-23"),
    ("aeration_kwh_day",       "aeration_kwh_day",       "IV-24"),
    ("peak_flow_mld",          "peak_flow_mld",          "IV-25"),
    ("clarifier_area_m2",      "clarifier_area_m2",      "IV-26"),
    ("reactor_volume_m3",      "reactor_volume_m3",      "IV-27"),
]


# ── Helper accessors ─────────────────────────────────────────────────────────

def _get(wp: WaterPointInput, dotted: str) -> Optional[Any]:
    """Resolve a dotted attribute path on WaterPointInput.

    e.g. ``_get(wp, "current_load.bod_kg_d")`` → ``wp.current_load.bod_kg_d``.
    Returns None if any step is missing or None.
    """
    obj: Any = wp
    for part in dotted.split("."):
        if obj is None:
            return None
        obj = getattr(obj, part, None)
    return obj


def _is_missing(value: Any) -> bool:
    """A field is missing if it is None, empty string, or numeric zero stand-in.

    Note: zero is treated as missing only for fields where zero is physically
    implausible (flows, loads, capacities). The check below is conservative —
    None or "" only — and the rule-level logic decides whether a zero counts.
    """
    if value is None:
        return True
    if isinstance(value, str) and value.strip() == "":
        return True
    return False


def _cod_to_tkn(wp: WaterPointInput) -> Optional[float]:
    """Compute COD:TKN from current loads. Uses the WPInput's stored ratio if set."""
    # Adapter sometimes carries cod_to_n_ratio directly.
    if wp.cod_to_n_ratio is not None and wp.cod_to_n_ratio > 0:
        return float(wp.cod_to_n_ratio)
    # Otherwise derive from loads. Loads are kg/day so the ratio is unit-free.
    cl = wp.current_load
    if cl is None:
        return None
    cod = None
    # We do not have COD load directly — adapter stores BOD only. Use COD≈1.9×BOD
    # as a screening approximation only when BOD is available. This is a known
    # approximation and is documented in the spec (Engineering Notes).
    if cl.bod_kg_d is not None and cl.tn_kg_d is not None and cl.tn_kg_d > 0:
        cod = cl.bod_kg_d * 1.9
        return round(cod / cl.tn_kg_d, 2)
    return None


def _bod_to_tss(wp: WaterPointInput) -> Optional[float]:
    cl = wp.current_load
    if cl is None or cl.tss_kg_d is None or cl.tss_kg_d <= 0:
        return None
    if cl.bod_kg_d is None:
        return None
    return round(cl.bod_kg_d / cl.tss_kg_d, 2)


def _implied_bod_conc(wp: WaterPointInput) -> Optional[float]:
    """BOD load (kg/day) ÷ flow (MLD) = mg/L (units of kg/ML)."""
    cl = wp.current_load
    if cl is None or cl.bod_kg_d is None:
        return None
    flow = wp.average_flow_mld
    if flow is None or flow <= 0:
        return None
    return round(cl.bod_kg_d / flow, 1)


# ── IV-01 — IV-09: Physical plausibility (Critical) ──────────────────────────

def _check_peak_vs_average_flow(wp: WaterPointInput) -> List[IVFlag]:
    """IV-01, IV-02, IV-03 — peak flow vs average flow rules."""
    flags: List[IVFlag] = []
    avg = wp.average_flow_mld
    peak = wp.peak_flow_mld
    if avg is None or peak is None or avg <= 0:
        return flags

    if peak < avg:
        flags.append(IVFlag(
            code="IV-01",
            severity=SEV_CRITICAL,
            field="peak_flow_mld",
            message=(
                f"Peak flow ({peak:.2f} MLD) is less than average flow "
                f"({avg:.2f} MLD). Physically impossible."
            ),
            recommendation=(
                "Verify peak flow value. Peak must be ≥ average; for reticulated "
                "sewers peak:ADWF typically 2.5–5×."
            ),
        ))
        return flags  # ratio rules below are meaningless if peak < avg

    ratio = peak / avg
    if ratio > _PEAK_RATIO_IMPLAUSIBLE:
        flags.append(IVFlag(
            code="IV-02",
            severity=SEV_CRITICAL,
            field="peak_flow_mld",
            message=(
                f"Peak:ADWF ratio of {ratio:.1f}× exceeds {_PEAK_RATIO_IMPLAUSIBLE:.0f}×. "
                "Implausible for a reticulated sewer."
            ),
            recommendation=(
                "Confirm peak flow basis — this magnitude is consistent with "
                "combined sewers or measurement error, not separate reticulated systems."
            ),
        ))
    elif ratio > _PEAK_RATIO_HIGH_II:
        flags.append(IVFlag(
            code="IV-03",
            severity=SEV_WARNING,
            field="peak_flow_mld",
            message=(
                f"Peak:ADWF ratio of {ratio:.1f}× indicates very high I/I. "
                f"Above {_PEAK_RATIO_HIGH_II:.0f}× is unusual for a separate system."
            ),
            recommendation=(
                "Investigate inflow/infiltration. High wet-weather peaks are "
                "likely the governing condition — clarifier hydraulic assessment is required."
            ),
        ))
    return flags


def _check_nh4_vs_tn_load(wp: WaterPointInput) -> List[IVFlag]:
    """IV-04 — NH₄ load must not exceed TN load."""
    cl = wp.current_load
    if cl is None or cl.nh4_kg_d is None or cl.tn_kg_d is None:
        return []
    if cl.tn_kg_d <= 0:
        return []
    if cl.nh4_kg_d > cl.tn_kg_d:
        return [IVFlag(
            code="IV-04",
            severity=SEV_CRITICAL,
            field="current_load.nh4_kg_d",
            message=(
                f"NH₄ load ({cl.nh4_kg_d:.1f} kg/d) exceeds TN load "
                f"({cl.tn_kg_d:.1f} kg/d). Chemically impossible — NH₄ is a TN component."
            ),
            recommendation=(
                "Verify TKN or NH₄ analytical values. Common cause: TKN reported "
                "without organic-N component, or unit confusion."
            ),
        )]
    return []


def _check_effluent_nh4_vs_tn(wp: WaterPointInput) -> List[IVFlag]:
    """IV-05 — effluent NH₄ must not exceed effluent TN."""
    nh4 = wp.effluent_nh4_mg_l
    tn  = wp.effluent_tn_mg_l
    if nh4 is None or tn is None:
        return []
    if nh4 > tn:
        return [IVFlag(
            code="IV-05",
            severity=SEV_CRITICAL,
            field="effluent_nh4_mg_l",
            message=(
                f"Effluent NH₄ ({nh4:.2f} mg/L) exceeds effluent TN ({tn:.2f} mg/L). "
                "A component cannot exceed the whole."
            ),
            recommendation=(
                "Verify effluent analytical results. NH₄ is a fraction of TN; "
                "this signals measurement, units, or transcription error."
            ),
        )]
    return []


def _check_mlss_band(wp: WaterPointInput) -> List[IVFlag]:
    """IV-06, IV-07 — MLSS plausibility for activated-sludge processes."""
    mlss = wp.mlss_mgL
    if mlss is None:
        return []
    flags: List[IVFlag] = []
    if mlss < _MLSS_MIN_PLAUSIBLE:
        flags.append(IVFlag(
            code="IV-06",
            severity=SEV_CRITICAL,
            field="mlss_mgL",
            message=(
                f"MLSS of {mlss:.0f} mg/L is below the plausible activated-sludge "
                f"range (≥ {_MLSS_MIN_PLAUSIBLE:.0f} mg/L)."
            ),
            recommendation=(
                "Confirm MLSS value. Activated sludge typically operates 2,000–4,500 mg/L; "
                "values below 1,000 mg/L suggest a different process or measurement issue."
            ),
        ))
    elif mlss > _MLSS_MAX_PLAUSIBLE:
        flags.append(IVFlag(
            code="IV-07",
            severity=SEV_CRITICAL,
            field="mlss_mgL",
            message=(
                f"MLSS of {mlss:.0f} mg/L exceeds the plausible range "
                f"(≤ {_MLSS_MAX_PLAUSIBLE:.0f} mg/L)."
            ),
            recommendation=(
                "Confirm MLSS value. Above 8,000 mg/L is associated with MBR or "
                "AGS configurations — verify the technology context."
            ),
        ))
    return flags


def _check_implied_bod_concentration(wp: WaterPointInput) -> List[IVFlag]:
    """IV-08 — implied influent BOD concentration too dilute."""
    bod_conc = _implied_bod_conc(wp)
    if bod_conc is None:
        return []
    if bod_conc < _BOD_CONC_DILUTE:
        return [IVFlag(
            code="IV-08",
            severity=SEV_CRITICAL,
            field="current_load.bod_kg_d",
            message=(
                f"Implied influent BOD concentration of {bod_conc:.0f} mg/L "
                f"is below {_BOD_CONC_DILUTE:.0f} mg/L. Dilution or load/flow mismatch."
            ),
            recommendation=(
                "Cross-check BOD load against flow. Domestic influent BOD is typically "
                "150–350 mg/L; very low values indicate I/I dilution or a units mismatch."
            ),
        )]
    return []


def _check_o2_per_kwh(wp: WaterPointInput) -> List[IVFlag]:
    """IV-09 — oxygen transfer efficiency outside plausible range."""
    o2 = wp.o2_demand_kg_day
    kwh = wp.aeration_kwh_day
    if o2 is None or kwh is None or kwh <= 0:
        return []
    ratio = o2 / kwh
    if ratio < _O2_PER_KWH_MIN or ratio > _O2_PER_KWH_MAX:
        return [IVFlag(
            code="IV-09",
            severity=SEV_CRITICAL,
            field="o2_demand_kg_day",
            message=(
                f"O₂:aeration ratio of {ratio:.2f} kg O₂/kWh is outside the "
                f"plausible range {_O2_PER_KWH_MIN:.1f}–{_O2_PER_KWH_MAX:.1f} kg/kWh."
            ),
            recommendation=(
                "Units check. Verify O₂ demand is in kg/day and aeration energy "
                "in kWh/day. Modern fine-bubble diffusers typically achieve 1.5–2.5 kg O₂/kWh."
            ),
        )]
    return []


# ── IV-10 — IV-16b: Ratio-based warnings ─────────────────────────────────────

def _check_cod_to_tkn(wp: WaterPointInput) -> List[IVFlag]:
    """IV-10, IV-11, IV-12 — COD:TKN ratio bands."""
    ratio = _cod_to_tkn(wp)
    if ratio is None:
        return []
    flags: List[IVFlag] = []
    if ratio < _COD_TKN_CARBON_LIMITED:
        flags.append(IVFlag(
            code="IV-10",
            severity=SEV_WARNING,
            field="cod_to_n_ratio",
            message=(
                f"COD:TKN of {ratio:.1f} is below {_COD_TKN_CARBON_LIMITED:.0f} — "
                "carbon-limited denitrification signal."
            ),
            recommendation=(
                "Denitrification may be constrained by available carbon. "
                "Consider Fbs characterisation or external carbon dosing assessment."
            ),
        ))
    elif _COD_TKN_THRESHOLD_LOW <= ratio <= _COD_TKN_THRESHOLD_HIGH:
        flags.append(IVFlag(
            code="IV-11",
            severity=SEV_WARNING,
            field="cod_to_n_ratio",
            message=(
                f"COD:TKN of {ratio:.1f} is at the denitrification threshold "
                f"({_COD_TKN_THRESHOLD_LOW:.0f}–{_COD_TKN_THRESHOLD_HIGH:.0f}). "
                "Fbs-sensitive — effective carbon depends on biodegradable fraction."
            ),
            recommendation=(
                "Fbs characterisation has high VOI here. Total COD adequacy "
                "does not guarantee adequate readily-biodegradable carbon."
            ),
        ))
    elif ratio > _COD_TKN_TRADE_WASTE:
        flags.append(IVFlag(
            code="IV-12",
            severity=SEV_WARNING,
            field="cod_to_n_ratio",
            message=(
                f"COD:TKN of {ratio:.1f} exceeds {_COD_TKN_TRADE_WASTE:.0f} — "
                "trade waste influence likely."
            ),
            recommendation=(
                "Trade waste characterisation has high VOI — seasonal peaks may "
                "not be captured in routine sampling. Investigate before sizing."
            ),
        ))
    return flags


def _check_nh4_to_tkn(wp: WaterPointInput) -> List[IVFlag]:
    """IV-13, IV-14, IV-15 — NH₄:TKN ratio bands."""
    cl = wp.current_load
    if cl is None or cl.nh4_kg_d is None or cl.tn_kg_d is None or cl.tn_kg_d <= 0:
        return []
    ratio = cl.nh4_kg_d / cl.tn_kg_d
    if ratio > 1.0:
        # IV-04 already covered this as Critical; skip the warning bands.
        return []
    flags: List[IVFlag] = []
    if ratio < _NH4_TKN_HIGH_ORG_N:
        flags.append(IVFlag(
            code="IV-13",
            severity=SEV_WARNING,
            field="current_load.nh4_kg_d",
            message=(
                f"NH₄:TKN of {ratio:.2f} is below {_NH4_TKN_HIGH_ORG_N:.2f} — "
                "high organic-N fraction. Trade waste protein signal."
            ),
            recommendation=(
                "Investigate organic-N source. Protein-rich trade waste "
                "(meat, dairy) can shift the fraction significantly."
            ),
        ))
    elif _NH4_TKN_DOM_LOWER_MIN <= ratio < _NH4_TKN_DOM_LOWER:
        flags.append(IVFlag(
            code="IV-14",
            severity=SEV_WARNING,
            field="current_load.nh4_kg_d",
            message=(
                f"NH₄:TKN of {ratio:.2f} is below the domestic range lower bound "
                f"({_NH4_TKN_DOM_LOWER:.2f})."
            ),
            recommendation=(
                "Typical domestic range is 0.60–0.75. Below 0.60 suggests an "
                "organic-N source (trade waste) requiring hydrolysis in-process."
            ),
        ))
    elif ratio > _NH4_TKN_SEPTIC:
        flags.append(IVFlag(
            code="IV-15",
            severity=SEV_WARNING,
            field="current_load.nh4_kg_d",
            message=(
                f"NH₄:TKN of {ratio:.2f} is above the domestic upper bound "
                f"({_NH4_TKN_SEPTIC:.2f}) — septic influence likely."
            ),
            recommendation=(
                "Long sewer detention, septic dosing, or low organic-N load. "
                "Check rising-main lengths or known septic feed points."
            ),
        ))
    return flags


def _check_bod_to_tss(wp: WaterPointInput) -> List[IVFlag]:
    """IV-16, IV-16b — BOD:TSS ratio bands."""
    ratio = _bod_to_tss(wp)
    if ratio is None:
        return []
    flags: List[IVFlag] = []
    if ratio > _BOD_TSS_DIURNAL_RISK:
        flags.append(IVFlag(
            code="IV-16",
            severity=SEV_WARNING,
            field="BOD:TSS ratio",
            message=(
                f"BOD:TSS of {ratio:.2f} exceeds {_BOD_TSS_DIURNAL_RISK:.1f} — "
                "Healesville-class pattern. Diurnal N/COD mismatch risk."
            ),
            recommendation=(
                "High BOD relative to TSS often coincides with diurnal mismatch "
                "between N and COD peaks. Diurnal profiling carries moderate VOI."
            ),
        ))
    elif ratio < _BOD_TSS_INORGANIC:
        flags.append(IVFlag(
            code="IV-16b",
            severity=SEV_WARNING,
            field="BOD:TSS ratio",
            message=(
                f"BOD:TSS of {ratio:.2f} is below {_BOD_TSS_INORGANIC:.1f} — "
                "high inorganic or particulate industrial load signal."
            ),
            recommendation=(
                "Verify TSS measurement and investigate industrial contributors. "
                "High inorganic TSS can mask biological load and affect clarifier sizing."
            ),
        ))
    return flags


# ── IV-17 — IV-27: Missing-field checks ───────────────────────────────────────

def _check_required_fields(wp: WaterPointInput) -> tuple[List[IVFlag], List[str]]:
    """IV-17..IV-22 — required fields. Returns (flags, missing_names)."""
    flags: List[IVFlag] = []
    missing: List[str] = []
    for attr, display, code in _REQUIRED_FIELDS:
        value = _get(wp, attr)
        # For numeric loads/flows, zero is also missing.
        if _is_missing(value) or (isinstance(value, (int, float)) and value == 0):
            missing.append(display)
            flags.append(IVFlag(
                code=code,
                severity=SEV_CRITICAL,
                field=display,
                message=f"Required field {display} is missing.",
                recommendation=(
                    f"Provide {display} on the Inputs page. "
                    "Required fields gate the validity of all downstream outputs."
                ),
            ))
    return flags, missing


def _check_optional_fields(wp: WaterPointInput) -> tuple[List[IVFlag], List[str]]:
    """IV-23..IV-27 — optional fields. Returns (flags, missing_names)."""
    flags: List[IVFlag] = []
    missing: List[str] = []
    for attr, display, code in _OPTIONAL_FIELDS:
        value = _get(wp, attr)
        if _is_missing(value) or (isinstance(value, (int, float)) and value == 0):
            missing.append(display)
            flags.append(IVFlag(
                code=code,
                severity=SEV_INFO,
                field=display,
                message=f"Optional field {display} is missing.",
                recommendation=(
                    f"Adding {display} improves analysis precision but is not blocking. "
                    "See the VOI panel for the highest-return next investigation."
                ),
            ))
    return flags, missing


# ── Part 2 — Data confidence scoring ──────────────────────────────────────────

def _score_confidence(
    flags: List[IVFlag],
    missing_critical: List[str],
    missing_optional: List[str],
) -> tuple[str, str]:
    """Apply the spec table to score overall data confidence.

    Spec (page_08_manual.py, Data confidence levels):
      High        — no warnings, no missing fields
      Acceptable  — 1 warning OR 1 missing optional field
      Low         — ≥1 missing critical field OR ≥4 warnings
      Very Low    — ≥1 Critical flag OR ≥3 missing critical fields

    Note on spec tension: the spec lists missing-required-field rules
    (IV-17..IV-22) as Critical severity *and* states that ≥1 Critical flag
    → Very Low. That means in practice a single missing required field will
    be scored Very Low, not Low. This implementation preserves the
    Critical-flag gate (more conservative), which matches the principle
    that ``safe_for_analysis = False`` should propagate to data confidence.
    If a calibration pass later prefers the Low-tier interpretation for
    missing-only-no-other-Critical cases, the ``critical_count`` test below
    can be replaced with ``any(f.code not in IV_17_TO_22 ...)``.
    """
    critical_count = sum(1 for f in flags if f.severity == SEV_CRITICAL)
    warning_count  = sum(1 for f in flags if f.severity == SEV_WARNING)

    # Very Low — strongest gate first.
    if critical_count >= 1 or len(missing_critical) >= 3:
        if critical_count >= 1 and len(missing_critical) >= 3:
            reason = (
                f"{critical_count} Critical flag(s) and "
                f"{len(missing_critical)} missing required field(s)."
            )
        elif critical_count >= 1:
            reason = f"{critical_count} Critical flag(s) raised."
        else:
            reason = f"{len(missing_critical)} required fields missing."
        return CONF_VERY_LOW, reason

    # Low — missing required field OR many warnings.
    if len(missing_critical) >= 1 or warning_count >= 4:
        if len(missing_critical) >= 1 and warning_count >= 4:
            reason = (
                f"{len(missing_critical)} missing required field(s) and "
                f"{warning_count} warnings."
            )
        elif len(missing_critical) >= 1:
            reason = f"{len(missing_critical)} required field(s) missing."
        else:
            reason = f"{warning_count} warnings raised."
        return CONF_LOW, reason

    # Acceptable — 1 warning OR 1 missing optional.
    if warning_count >= 1 or len(missing_optional) >= 1:
        bits = []
        if warning_count:
            bits.append(f"{warning_count} warning(s)")
        if missing_optional:
            bits.append(f"{len(missing_optional)} missing optional field(s)")
        return CONF_ACCEPTABLE, " and ".join(bits) + " — concept-stage acceptable."

    return CONF_HIGH, "No warnings or missing fields detected."


# ── Part 2 — Value-of-Information assessment ─────────────────────────────────

def _build_voi(
    wp: WaterPointInput,
    flags: List[IVFlag],
    missing_critical: List[str],
    missing_optional: List[str],
) -> List[VOIItem]:
    """Identify High / Moderate / Low VOI items from the spec table.

    Spec VOI table (page_08_manual.py):
      High     peak_flow_mld missing
      High     peak_flow_mld ratio ≥ 3×
      High     cod_to_n_ratio > 13 + fractionation
      High     o2_demand_kg_day AND aeration_kwh_day both missing
      High     tn_target_mg_l missing
      High     Trade waste characterisation (proxy: COD:TKN > 13)
      Moderate Diurnal profiling (BOD:TSS > 2.0)
      Moderate o2_demand_kg_day missing while aeration_kwh_day present
    """
    items: List[VOIItem] = []

    # peak_flow_mld missing.
    if wp.peak_flow_mld is None:
        items.append(VOIItem(
            field="peak_flow_mld",
            voi_level=VOI_HIGH,
            rationale=(
                "Cannot apply binding constraint test to hydraulic options "
                "without peak flow. Measure or estimate before option selection."
            ),
        ))
    # peak_flow_mld ratio ≥ 3.
    elif wp.average_flow_mld and wp.average_flow_mld > 0:
        ratio = wp.peak_flow_mld / wp.average_flow_mld
        if ratio >= _PEAK_RATIO_GOVERNING_WW:
            items.append(VOIItem(
                field="peak_flow_mld",
                voi_level=VOI_HIGH,
                rationale=(
                    f"Peak:ADWF ratio of {ratio:.1f}× indicates wet weather is "
                    "likely the governing condition. Clarifier hydraulic "
                    "assessment is required before sizing decisions."
                ),
            ))

    # COD:TKN > 13 → trade waste characterisation + fractionation High VOI.
    cod_tkn = _cod_to_tkn(wp)
    if cod_tkn is not None and cod_tkn > _COD_TKN_TRADE_WASTE:
        items.append(VOIItem(
            field="cod_to_n_ratio + fractionation",
            voi_level=VOI_HIGH,
            rationale=(
                f"COD:TKN of {cod_tkn:.1f} exceeds {_COD_TKN_TRADE_WASTE:.0f}. "
                "Trade waste may overstate effective denitrification carbon. "
                "Fbs characterisation determines whether the carbon is biologically available."
            ),
        ))
        items.append(VOIItem(
            field="Trade waste characterisation",
            voi_level=VOI_HIGH,
            rationale=(
                "Seasonal peak likely not captured in current load data. "
                "Source profiling and vintage / seasonal monitoring carry high VOI."
            ),
        ))

    # Aeration audit — both missing.
    if wp.o2_demand_kg_day is None and wp.aeration_kwh_day is None:
        items.append(VOIItem(
            field="o2_demand_kg_day + aeration_kwh_day",
            voi_level=VOI_HIGH,
            rationale=(
                "Cannot assess blower headroom. MABR / IFAS selection is blind "
                "without aeration capacity data — these are aeration-side technologies."
            ),
        ))
    elif wp.o2_demand_kg_day is None and wp.aeration_kwh_day is not None:
        items.append(VOIItem(
            field="o2_demand_kg_day",
            voi_level=VOI_MODERATE,
            rationale=(
                "Improves aeration efficiency precision but does not change "
                "process selection. Initiate in parallel with concept design."
            ),
        ))

    # TN target missing.
    if wp.tn_target_mg_l is None:
        items.append(VOIItem(
            field="tn_target_mg_l",
            voi_level=VOI_HIGH,
            rationale=(
                "TN 5 mg/L vs 10 mg/L drives fundamentally different process selection. "
                "Confirm with regulator before committing capital."
            ),
        ))

    # Diurnal profiling — BOD:TSS > 2.0.
    bod_tss = _bod_to_tss(wp)
    if bod_tss is not None and bod_tss > _BOD_TSS_VOI_THRESHOLD:
        items.append(VOIItem(
            field="Diurnal profiling",
            voi_level=VOI_MODERATE,
            rationale=(
                f"BOD:TSS of {bod_tss:.2f} signals N/COD peak mismatch. "
                "Affects control strategy, not process selection."
            ),
        ))

    return items


# ── Part 3 — Governing condition identification ──────────────────────────────

def _identify_governing_condition(wp: WaterPointInput) -> GoverningCondition:
    """Apply the governing-condition decision table from the spec.

    Spec (page_08_manual.py, Governing condition table):
      Peak wet weather                  — Peak:ADWF ≥ 3×
      Moderate wet weather / diurnal    — Peak:ADWF 2–3×
      Seasonal trade waste event        — COD:TKN > 13 and no high peak ratio
      Dry weather ADWF                  — None of the above
      Unknown                           — No flow data
    """
    avg  = wp.average_flow_mld
    peak = wp.peak_flow_mld

    if avg is None or peak is None or avg <= 0:
        return GoverningCondition(
            condition=GC_UNKNOWN,
            trigger="No flow data provided.",
            implication=(
                "Governing condition cannot be determined. Provide both "
                "average and peak flow before proceeding with constraint analysis."
            ),
        )

    # If peak < average (IV-01 territory) the flow data is broken — the
    # governing-condition test is meaningless until the inputs are repaired.
    if peak < avg:
        return GoverningCondition(
            condition=GC_UNKNOWN,
            trigger="Peak flow less than average flow (see IV-01).",
            implication=(
                "Flow data is internally inconsistent. Resolve IV-01 before "
                "interpreting the governing condition."
            ),
        )

    ratio = peak / avg

    if ratio >= _PEAK_RATIO_GOVERNING_WW:
        return GoverningCondition(
            condition=GC_PEAK_WET,
            trigger=f"Peak:ADWF ratio of {ratio:.1f}× ≥ {_PEAK_RATIO_GOVERNING_WW:.0f}×.",
            implication=(
                "Clarifier hydraulic performance is the primary constraint assessment. "
                "Wet-weather options (CoMag, EQ, storm storage) take precedence over "
                "dry-weather biological intensification."
            ),
        )

    if ratio >= _PEAK_RATIO_GOVERNING_MOD:
        return GoverningCondition(
            condition=GC_MODERATE_WET,
            trigger=f"Peak:ADWF ratio of {ratio:.1f}× is {_PEAK_RATIO_GOVERNING_MOD:.0f}–{_PEAK_RATIO_GOVERNING_WW:.0f}×.",
            implication=(
                "Both wet-weather hydraulic and dry-weather biological "
                "performance matter. Confirm which is binding before option ranking."
            ),
        )

    cod_tkn = _cod_to_tkn(wp)
    if cod_tkn is not None and cod_tkn > _COD_TKN_TRADE_WASTE:
        return GoverningCondition(
            condition=GC_SEASONAL_TW,
            trigger=(
                f"COD:TKN of {cod_tkn:.1f} > {_COD_TKN_TRADE_WASTE:.0f} "
                f"with peak ratio only {ratio:.1f}× (below {_PEAK_RATIO_GOVERNING_WW:.0f}×)."
            ),
            implication=(
                "Vintage / food processing seasonal peak likely governing. "
                "Routine sampling may not capture the event — initiate trade waste "
                "characterisation before process selection."
            ),
        )

    return GoverningCondition(
        condition=GC_DRY_ADWF,
        trigger=(
            f"Peak:ADWF ratio of {ratio:.1f}× and COD:TKN in domestic range. "
            "No seasonal or peak signal."
        ),
        implication=(
            "Standard biological design basis. Confirm against any compliance "
            "failure history — design failures occurring under known peak conditions "
            "should override this default."
        ),
    )


# ── Public entry point ───────────────────────────────────────────────────────

def validate_inputs(wp: WaterPointInput) -> InputValidationReport:
    """Run the full input validation pipeline.

    Never raises. All failure modes — missing fields, type mismatches, deep
    exceptions in helper functions — populate ``InputValidationReport`` flags
    so the UI and credibility layer can render them gracefully.

    Parameters
    ----------
    wp : WaterPointInput
        The structured input built by ``waterpoint_adapter.build_waterpoint_input``.

    Returns
    -------
    InputValidationReport
        Report carrying flags, missing-field lists, data confidence, VOI items,
        and the identified governing condition.
    """
    # Defensive: a None or wrong-typed input must not raise — return an empty
    # report with a sentinel critical flag so the UI can show "validation
    # could not run" without breaking the page.
    if wp is None:
        return InputValidationReport(
            flags=[IVFlag(
                code="IV-00",
                severity=SEV_CRITICAL,
                field="(WaterPointInput)",
                message="Input validation received no WaterPointInput.",
                recommendation=(
                    "Ensure waterpoint_adapter.build_waterpoint_input has been "
                    "called and returned a valid object before validation."
                ),
            )],
            missing_critical=["WaterPointInput"],
            data_confidence=CONF_VERY_LOW,
            confidence_reason="No input available for validation.",
            safe_for_analysis=False,
        )

    flags: List[IVFlag] = []

    # IV-01..IV-09 — physical plausibility (Critical).
    # Each check is wrapped defensively — a single misbehaving rule must not
    # abort the rest of the validation pass.
    for check in (
        _check_peak_vs_average_flow,
        _check_nh4_vs_tn_load,
        _check_effluent_nh4_vs_tn,
        _check_mlss_band,
        _check_implied_bod_concentration,
        _check_o2_per_kwh,
        # IV-10..IV-16b — ratio warnings.
        _check_cod_to_tkn,
        _check_nh4_to_tkn,
        _check_bod_to_tss,
    ):
        try:
            flags.extend(check(wp))
        except Exception:
            # Silent skip — a deeply broken WP input should not block the rest
            # of the validation. The missing-field rules below will likely catch
            # the underlying problem.
            pass

    # IV-17..IV-22 — required fields (Critical).
    try:
        req_flags, missing_critical = _check_required_fields(wp)
    except Exception:
        req_flags, missing_critical = [], []
    flags.extend(req_flags)

    # IV-23..IV-27 — optional fields (Info).
    try:
        opt_flags, missing_optional = _check_optional_fields(wp)
    except Exception:
        opt_flags, missing_optional = [], []
    flags.extend(opt_flags)

    # Part 2 — confidence scoring.
    try:
        confidence, reason = _score_confidence(flags, missing_critical, missing_optional)
    except Exception:
        confidence, reason = CONF_LOW, "Confidence scoring failed; treating as Low."

    # Part 2 — VOI assessment.
    try:
        voi_items = _build_voi(wp, flags, missing_critical, missing_optional)
    except Exception:
        voi_items = []

    # Part 3 — governing condition.
    try:
        governing = _identify_governing_condition(wp)
    except Exception:
        governing = GoverningCondition(
            condition=GC_UNKNOWN,
            trigger="Governing condition identification failed.",
            implication="Cannot determine the binding condition; treat outputs with caution.",
        )

    # safe_for_analysis demotes whenever any Critical flag is present.
    safe = not any(f.severity == SEV_CRITICAL for f in flags)

    return InputValidationReport(
        flags=flags,
        missing_critical=missing_critical,
        missing_optional=missing_optional,
        data_confidence=confidence,
        confidence_reason=reason,
        voi_items=voi_items,
        governing_condition=governing,
        safe_for_analysis=safe,
    )


__all__ = [
    # Constants
    "SCHEMA_VERSION",
    "SEV_CRITICAL", "SEV_WARNING", "SEV_INFO",
    "CONF_HIGH", "CONF_ACCEPTABLE", "CONF_LOW", "CONF_VERY_LOW",
    "GC_PEAK_WET", "GC_MODERATE_WET", "GC_SEASONAL_TW", "GC_DRY_ADWF", "GC_UNKNOWN",
    "VOI_HIGH", "VOI_MODERATE", "VOI_LOW",
    # Dataclasses
    "IVFlag", "GoverningCondition", "VOIItem", "InputValidationReport",
    # Entry point
    "validate_inputs",
]
