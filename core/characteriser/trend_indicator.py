"""
core/characteriser/trend_indicator.py

AquaPoint — Trend Indicators (AV-TND-XX)
=========================================

Implements five trend indicators that compare a parameter's early-reference-
period central tendency against the most-recent-12-month period. These detect
slow baseline drift that rolling-window event detection cannot surface (because
the rolling baseline adapts silently to gradual change).

Registers
---------
  AV-TND-01  DOC baseline drift
  AV-TND-02  Cyanobacterial baseline drift
  AV-TND-03  Salinity / EC drift
  AV-TND-04  Microcystin baseline emergence (first-detection variant)
  AV-TND-05  DOC seasonal-range expansion
  AV-TND-06  SUVA baseline drift (organic character shift)

Output: List[CharacterisationFlag] on CharacterisationReport.flags
        with rule_id="AV-TND-01" … "AV-TND-05".
        These flags surface in Section 6 (evidence limits) of the envelope
        memo, NOT in Section 3 (events).

Schema alignment
----------------
Populates CharacterisationFlag (existing type). Also populates
TemporalStructure.trend_slope / trend_significant / trend_pct_per_year
on ParameterCharacterisation for AV-TND-01/02/03 where the calc engine
has already run per-parameter stats.

Engineering basis [VERIFY against current literature before production]
-----------------------------------------------------------------------
Detection thresholds (25% shift AND 1.5× early-period pooled SD) are
engineering judgment per v5.5 spec §6.1. These are calibration values
not regulatory requirements.

Minimum record: ≥ 36 months (24m early reference + 12m recent, no overlap).
"""
from __future__ import annotations

from datetime import timedelta
from typing import List, Optional

import numpy as np
import pandas as pd

from .report import (
    APPLIC_INSUFFICIENT,
    APPLIC_LIMITED,
    APPLIC_OK,
    SEV_INFO,
    SEV_WARNING,
    CharacterisationFlag,
)

# ── Constants ─────────────────────────────────────────────────────────────────

_EARLY_MONTHS   = 24    # reference period length
_RECENT_MONTHS  = 12    # comparison period length
_MIN_MONTHS     = 35    # ≥35 months (spec intent: ~3 years; 30.44-day approximation
                       # underestimates true calendar months by ~0.1–0.3 months)

_SHIFT_THRESHOLD_PCT = 25.0   # % shift relative to early-period median
_SHIFT_THRESHOLD_SD  =  1.5   # early-period pooled-SD units

_DATE_COL = "_date"

# Canonical column names
_DOC_COL   = "DOC_mg_L"
_CYANO_COL = "Cyanobacteria_cells_mL"
_EC_COL    = "EC_uS_cm"
_MCST_COL  = "Microcystin_LR_ug_L"


# ── Internal helpers ──────────────────────────────────────────────────────────

def _record_months(df: pd.DataFrame) -> float:
    """Record length in months (approximate, using 30.44 days/month)."""
    if _DATE_COL not in df.columns or df[_DATE_COL].isna().all():
        return 0.0
    return (df[_DATE_COL].max() - df[_DATE_COL].min()).days / 30.44


def _split_periods(df: pd.DataFrame) -> Optional[tuple[pd.DataFrame, pd.DataFrame, str, str, str, str]]:
    """
    Split df into early reference period (first 24 months) and
    recent period (last 12 months). Returns None if record < 36 months.

    Returns (early_df, recent_df, early_start, early_end, recent_start, recent_end).
    """
    if _DATE_COL not in df.columns:
        return None

    start = df[_DATE_COL].min()
    end   = df[_DATE_COL].max()

    # Use exact calendar months via dateutil.relativedelta
    try:
        from dateutil.relativedelta import relativedelta as _rd
        early_end    = start + _rd(months=_EARLY_MONTHS)
        recent_start = end   - _rd(months=_RECENT_MONTHS)
    except ImportError:
        early_end    = start + timedelta(days=_EARLY_MONTHS  * 30.44)
        recent_start = end   - timedelta(days=_RECENT_MONTHS * 30.44)

    # If periods share a boundary date (early_end == recent_start), adjust
    # recent_start forward by 1 day so the periods don't overlap in rows.
    # This occurs when the record is exactly 36 months long.
    if recent_start <= early_end:
        overlap_days = (early_end - recent_start).days + 1
        if overlap_days > 30:
            return None  # genuine overlap — record too short
        recent_start = early_end + timedelta(days=1)
        # fall through — continue with adjusted recent_start

    early  = df[df[_DATE_COL] <= early_end]
    recent = df[df[_DATE_COL] >= recent_start]

    return (
        early, recent,
        str(start.date()), str(early_end.date()),
        str(recent_start.date()), str(end.date()),
    )


def _monthly_medians(df: pd.DataFrame, col: str) -> pd.Series:
    """Return monthly median of col within df."""
    if col not in df.columns or _DATE_COL not in df.columns:
        return pd.Series(dtype=float)
    tmp = df[[_DATE_COL, col]].dropna()
    if tmp.empty:
        return pd.Series(dtype=float)
    tmp = tmp.set_index(_DATE_COL)
    return tmp[col].resample("ME").median().dropna()


def _pooled_sd_of_monthly_medians(monthly: pd.Series) -> float:
    """Standard deviation of monthly medians (early-period SD)."""
    if len(monthly) < 2:
        return 0.0
    return float(monthly.std(ddof=1))


def _compute_shift(
    early: pd.DataFrame,
    recent: pd.DataFrame,
    col: str,
) -> Optional[tuple[float, float, float, float, float]]:
    """
    Compute shift statistics for `col` between early and recent periods.

    Returns (early_median, recent_median, shift_pct, early_sd, shift_sd)
    or None if insufficient data in either period.
    """
    e_vals = early[col].dropna() if col in early.columns else pd.Series(dtype=float)
    r_vals = recent[col].dropna() if col in recent.columns else pd.Series(dtype=float)

    if len(e_vals) < 5 or len(r_vals) < 3:
        return None

    e_med = float(e_vals.median())
    r_med = float(r_vals.median())

    monthly_e = _monthly_medians(early, col)
    e_sd = _pooled_sd_of_monthly_medians(monthly_e)

    if e_med == 0:
        return None

    shift_pct = (r_med - e_med) / abs(e_med) * 100.0
    shift_sd  = abs(r_med - e_med) / e_sd if e_sd > 0 else 0.0

    return e_med, r_med, shift_pct, e_sd, shift_sd


def _is_flagged(shift_pct: float, shift_sd: float) -> bool:
    return abs(shift_pct) >= _SHIFT_THRESHOLD_PCT and shift_sd >= _SHIFT_THRESHOLD_SD


def _direction(shift_pct: float) -> str:
    return "increasing" if shift_pct > 0 else "decreasing"


def _reference_period_str(es: str, ee: str, rs: str, re: str) -> str:
    return f"early: {es} to {ee}; recent: {rs} to {re}"


# ── AV-TND-01: DOC baseline drift ────────────────────────────────────────────

def _tnd_01_doc(
    df: pd.DataFrame,
    periods,
) -> Optional[CharacterisationFlag]:
    """AV-TND-01 — DOC baseline drift."""
    if _DOC_COL not in df.columns:
        return None

    early, recent, es, ee, rs, re = periods
    result = _compute_shift(early, recent, _DOC_COL)
    if result is None:
        return CharacterisationFlag(
            rule_id="AV-TND-01",
            severity=SEV_INFO,
            parameter=_DOC_COL,
            pattern="Indeterminate",
            message=(
                f"AV-TND-01 Indeterminate — insufficient data in one or both "
                f"periods to compute DOC shift. Reference: {_reference_period_str(es,ee,rs,re)}."
            ),
            implication="DOC baseline drift cannot be assessed.",
            recommended_action="Ensure consistent DOC monitoring across both periods.",
        )

    e_med, r_med, shift_pct, e_sd, shift_sd = result
    flagged = _is_flagged(shift_pct, shift_sd)
    direction = _direction(shift_pct)

    if not flagged:
        return None  # No flag needed — no notable trend

    return CharacterisationFlag(
        rule_id="AV-TND-01",
        severity=SEV_WARNING,
        parameter=_DOC_COL,
        pattern=f"flagged {direction}",
        message=(
            f"AV-TND-01 DOC baseline drift: DOC central tendency has shifted "
            f"{shift_pct:+.1f}% ({shift_sd:.1f}σ) relative to the source's "
            f"early-period baseline (early median: {e_med:.2f} mg/L; "
            f"recent median: {r_med:.2f} mg/L). "
            f"Reference periods — {_reference_period_str(es,ee,rs,re)}."
        ),
        implication=(
            "The rolling-window event detection adapts to this baseline; "
            "consider whether the source is undergoing gradual DOC change "
            "that the event channel will not surface. Higher DOC drives "
            "increased DBP precursor loading and coagulant demand."
        ),
        recommended_action=(
            "Review catchment land-use changes, drought/wet cycles, or "
            "upstream impoundment changes that may explain the DOC drift. "
            "Consider adjusting rolling-baseline window length."
        ),
    )


# ── AV-TND-02: Cyanobacterial baseline drift ──────────────────────────────────

def _tnd_02_cyano(
    df: pd.DataFrame,
    periods,
) -> Optional[CharacterisationFlag]:
    """AV-TND-02 — Cyanobacterial baseline drift."""
    if _CYANO_COL not in df.columns:
        return None

    early, recent, es, ee, rs, re = periods
    result = _compute_shift(early, recent, _CYANO_COL)
    if result is None:
        return None  # Insufficient data — not flagged (common for rare cyano)

    e_med, r_med, shift_pct, e_sd, shift_sd = result
    if not _is_flagged(shift_pct, shift_sd):
        return None

    direction = _direction(shift_pct)

    return CharacterisationFlag(
        rule_id="AV-TND-02",
        severity=SEV_WARNING,
        parameter=_CYANO_COL,
        pattern=f"flagged {direction}",
        message=(
            f"AV-TND-02 Cyanobacterial baseline drift: baseline cyanobacterial "
            f"concentration has shifted {shift_pct:+.1f}% ({shift_sd:.1f}σ) "
            f"relative to the source's early-period baseline "
            f"(early median: {e_med:.0f} cells/mL; "
            f"recent median: {r_med:.0f} cells/mL). "
            f"Reference periods — {_reference_period_str(es,ee,rs,re)}."
        ),
        implication=(
            "EV-03 (Alert Level 2 escalation) detects acute bloom events. "
            "This trend indicator captures underlying baseline drift that may "
            "indicate progressive eutrophication or nutrient-loading change — "
            "conditions EV-03 will not flag."
        ),
        recommended_action=(
            "Review nutrient (TP, TN) loading trends, flushing regime, and "
            "thermal stratification data. Consider phosphorus source control "
            "or hypolimnetic destratification if eutrophication is confirmed."
        ),
    )


# ── AV-TND-03: EC / salinity drift ───────────────────────────────────────────

def _tnd_03_ec(
    df: pd.DataFrame,
    periods,
) -> Optional[CharacterisationFlag]:
    """AV-TND-03 — EC / salinity drift."""
    if _EC_COL not in df.columns:
        return None

    early, recent, es, ee, rs, re = periods
    result = _compute_shift(early, recent, _EC_COL)
    if result is None:
        return None

    e_med, r_med, shift_pct, e_sd, shift_sd = result
    if not _is_flagged(shift_pct, shift_sd):
        return None

    direction = _direction(shift_pct)

    return CharacterisationFlag(
        rule_id="AV-TND-03",
        severity=SEV_WARNING,
        parameter=_EC_COL,
        pattern=f"flagged {direction}",
        message=(
            f"AV-TND-03 EC / salinity baseline drift: EC central tendency has "
            f"shifted {shift_pct:+.1f}% ({shift_sd:.1f}σ) relative to early-period "
            f"baseline (early median: {e_med:.0f} µS/cm; "
            f"recent median: {r_med:.0f} µS/cm). "
            f"Reference periods — {_reference_period_str(es,ee,rs,re)}."
        ),
        implication=(
            "Rising EC may indicate saline intrusion (coastal sources), "
            "evaporative concentration (drought), or upstream point-source loading. "
            "Rolling-window event detection will not flag this as an event."
        ),
        recommended_action=(
            "Investigate saline intrusion, drought impacts, or upstream "
            "ionic loading. Consider TDS, chloride, and hardness trend analysis "
            "as corroboration."
        ),
    )


# ── AV-TND-04: Microcystin baseline emergence ─────────────────────────────────

def _tnd_04_mcst_emergence(
    df: pd.DataFrame,
    periods,
) -> Optional[CharacterisationFlag]:
    """
    AV-TND-04 — Microcystin baseline emergence.

    Flags if microcystin detections (above LoD, i.e. > 0) appear in
    the recent 12 months when they were absent in the early reference period.
    This is a first-detection variant, not a magnitude shift.
    """
    if _MCST_COL not in df.columns:
        return None

    early, recent, es, ee, rs, re = periods

    # Early period: any detection?
    e_vals = early[_MCST_COL].dropna() if _MCST_COL in early.columns else pd.Series(dtype=float)
    r_vals = recent[_MCST_COL].dropna() if _MCST_COL in recent.columns else pd.Series(dtype=float)

    if len(r_vals) < 3:
        return None

    e_detections = int((e_vals > 0).sum())
    r_detections = int((r_vals > 0).sum())

    if e_detections > 0 or r_detections == 0:
        return None  # Either already present early, or still absent — no emergence

    r_max = float(r_vals[r_vals > 0].max()) if r_detections > 0 else 0.0

    return CharacterisationFlag(
        rule_id="AV-TND-04",
        severity=SEV_WARNING,
        parameter=_MCST_COL,
        pattern="flagged — first detections in recent period",
        message=(
            f"AV-TND-04 Microcystin baseline emergence: microcystin-LR detections "
            f"(above LoD) have begun appearing in the recent 12-month period "
            f"({r_detections} detections, max = {r_max:.3f} µg/L) "
            f"when they were absent in the early reference period "
            f"(0 detections). "
            f"Reference periods — {_reference_period_str(es,ee,rs,re)}."
        ),
        implication=(
            "Even sub-AL1 detection of a previously absent toxin is a trend "
            "indicator. Microcystin emergence suggests a shift in cyanobacterial "
            "community composition toward toxin-producing genera."
        ),
        recommended_action=(
            "Commission genus-level phytoplankton enumeration to identify "
            "whether toxigenic genera (Microcystis, Dolichospermum) have "
            "established in the source. Review nutrient loading and stratification."
        ),
    )


# ── AV-TND-05: DOC seasonal-range expansion ───────────────────────────────────

def _tnd_05_doc_range(
    df: pd.DataFrame,
    periods,
) -> Optional[CharacterisationFlag]:
    """
    AV-TND-05 — DOC seasonal-range expansion.

    Compares the DOC seasonal range (P90 − P10 of monthly medians) in the
    recent 12 months against the same metric in the early reference period.
    Flags if the recent range exceeds the early range by > 30%.
    """
    if _DOC_COL not in df.columns:
        return None

    _RANGE_THRESHOLD_PCT = 30.0

    early, recent, es, ee, rs, re = periods

    monthly_e = _monthly_medians(early, _DOC_COL)
    monthly_r = _monthly_medians(recent, _DOC_COL)

    if len(monthly_e) < 6 or len(monthly_r) < 6:
        return None  # Not enough monthly data to compute a meaningful range

    def seasonal_range(monthly: pd.Series) -> float:
        p10 = float(np.percentile(monthly, 10))
        p90 = float(np.percentile(monthly, 90))
        return p90 - p10

    range_e = seasonal_range(monthly_e)
    range_r = seasonal_range(monthly_r)

    if range_e == 0:
        return None

    range_expansion_pct = (range_r - range_e) / range_e * 100.0

    if range_expansion_pct < _RANGE_THRESHOLD_PCT:
        return None

    return CharacterisationFlag(
        rule_id="AV-TND-05",
        severity=SEV_WARNING,
        parameter=_DOC_COL,
        pattern="flagged — seasonal range expanded",
        message=(
            f"AV-TND-05 DOC seasonal-range expansion: the DOC seasonal range "
            f"(P90−P10 of monthly medians) has expanded by {range_expansion_pct:.1f}% "
            f"in the recent 12 months (range: {range_r:.2f} mg/L) "
            f"relative to the early reference period (range: {range_e:.2f} mg/L). "
            f"Reference periods — {_reference_period_str(es,ee,rs,re)}."
        ),
        implication=(
            "Increased DOC variability indicates increased variability in "
            "catchment loading — potentially climate-driven (longer dry-then-wet "
            "cycles) or land-use driven. Rolling event detection adapts to this "
            "expanding variance and will under-trigger events relative to the "
            "historical envelope."
        ),
        recommended_action=(
            "Assess whether coagulant dosing and GAC/BAC media replacement "
            "schedules account for increased peak DOC loads. "
            "Review catchment land use and rainfall pattern changes."
        ),
    )


# ── AV-TND-06: SUVA baseline drift ───────────────────────────────────────────

_SUVA_COL_TND = "SUVA"

def _tnd_06_suva(
    df: pd.DataFrame,
    periods,
) -> Optional[CharacterisationFlag]:
    """
    AV-TND-06 — SUVA baseline drift.

    Compares the most-recent-12-month median SUVA against the early-reference-
    period median SUVA. A rising SUVA indicates the DOC is becoming more
    aromatic over time — independent of DOC concentration changes (which
    AV-TND-01 captures). A falling SUVA indicates the DOC is becoming less
    aromatic (e.g. increasing contribution from algal-derived, non-humic DOC).

    SUVA is resolved from the stored 'SUVA' column or computed from
    UV254_cm_1 and DOC_mg_L if both are available.
    """
    import numpy as _np

    # Resolve SUVA series
    if _SUVA_COL_TND in df.columns and df[_SUVA_COL_TND].notna().sum() > 10:
        use_col = _SUVA_COL_TND
    elif "UV254_cm_1" in df.columns and "DOC_mg_L" in df.columns:
        # Compute SUVA and add as a temporary column for the period split
        df = df.copy()
        raw = (df["UV254_cm_1"] * 100.0) / df["DOC_mg_L"]
        df[_SUVA_COL_TND] = raw.replace([_np.inf, -_np.inf], _np.nan)
        use_col = _SUVA_COL_TND
    else:
        return None  # Neither SUVA nor components available

    early, recent, es, ee, rs, re = periods
    result = _compute_shift(early, recent, use_col)
    if result is None:
        return None

    e_med, r_med, shift_pct, e_sd, shift_sd = result
    if not _is_flagged(shift_pct, shift_sd):
        return None

    direction = _direction(shift_pct)

    # Contextualise the direction
    if shift_pct > 0:
        implication = (
            "Rising SUVA indicates the dissolved organic matter is becoming more "
            "aromatic over time, independent of any changes in DOC concentration. "
            "This may indicate a shift toward more humic, tannin-dominated inputs "
            "or a reduction in the proportion of non-aromatic algal-derived DOC. "
            "DBP precursor character is increasing relative to the early period."
        )
    else:
        implication = (
            "Falling SUVA indicates the dissolved organic matter is becoming less "
            "aromatic over time. This may indicate a growing contribution from "
            "algal-derived or other non-humic DOC sources, or reduced humic "
            "catchment inputs. DBP precursor character is decreasing relative to "
            "the early period, though overall DOC trends should be assessed jointly."
        )

    return CharacterisationFlag(
        rule_id="AV-TND-06",
        severity=SEV_WARNING,
        parameter=use_col,
        pattern=f"flagged {direction}",
        message=(
            f"AV-TND-06 SUVA baseline drift: median SUVA has shifted "
            f"{shift_pct:+.1f}% ({shift_sd:.1f}σ) relative to the source's "
            f"early-period baseline "
            f"(early median: {e_med:.2f} L/mg/m; "
            f"recent median: {r_med:.2f} L/mg/m). "
            f"Reference periods — {_reference_period_str(es, ee, rs, re)}."
        ),
        implication=implication,
        recommended_action=(
            "Assess jointly with AV-TND-01 (DOC concentration drift) — SUVA drift "
            "independent of DOC drift indicates a change in organic matter character "
            "rather than quantity. Review catchment land-use changes, algal community "
            "shifts, or upstream organic inputs that may explain the change."
        ),
    )




def run_trend_indicators(df: pd.DataFrame) -> List[CharacterisationFlag]:
    """
    Run all five AV-TND-XX trend indicators and return flags.

    Flags are intended for CharacterisationReport.flags (dataset-level).
    They surface in Section 6 (evidence limits) of the envelope memo.

    Returns an empty list if the record is < 36 months (Indeterminate
    for all indicators).

    Parameters
    ----------
    df : pd.DataFrame
        Clean, sorted source water dataframe with canonical column names
        and a '_date' datetime column.
    """
    flags: List[CharacterisationFlag] = []

    record_months = _record_months(df)
    if record_months < _MIN_MONTHS:   # strict: ≥36 months required
        flags.append(CharacterisationFlag(
            rule_id="AV-TND-XX",
            severity=SEV_INFO,
            parameter="",
            pattern="Indeterminate — insufficient record",
            message=(
                f"AV-TND-XX trend indicators require ≥{_MIN_MONTHS} months of data "
                f"(24m early reference + 12m recent). "
                f"Record is {record_months:.1f} months. "
                "All trend indicators are Indeterminate."
            ),
            implication=(
                "Baseline drift cannot be assessed. Trend indicators will become "
                f"available once the record exceeds {_MIN_MONTHS} months."
            ),
            recommended_action=(
                f"Continue monitoring. Trend indicators activate automatically "
                f"once {_MIN_MONTHS} months of data are available."
            ),
        ))
        return flags

    periods = _split_periods(df)
    if periods is None:
        flags.append(CharacterisationFlag(
            rule_id="AV-TND-XX",
            severity=SEV_INFO,
            parameter="",
            pattern="Indeterminate — period overlap",
            message=(
                "Record length sufficient but early and recent periods overlap — "
                "possibly very irregular sampling. All trend indicators Indeterminate."
            ),
            implication="Trend indicators cannot be computed.",
            recommended_action="Review dataset for gaps or irregular sampling.",
        ))
        return flags

    # Run all six indicators
    for fn in [_tnd_01_doc, _tnd_02_cyano, _tnd_03_ec,
               _tnd_04_mcst_emergence, _tnd_05_doc_range, _tnd_06_suva]:
        flag = fn(df, periods)
        if flag is not None:
            flags.append(flag)

    return flags
