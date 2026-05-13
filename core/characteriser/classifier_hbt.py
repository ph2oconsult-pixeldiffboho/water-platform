"""
core/characteriser/classifier_hbt.py

AquaPoint — Source Water Classification (AV-CLS-XX)
====================================================

Implements the two source-water classification registers:

  AV-CLS-01  ADWG Health-Based Targets — Source-Water Category
             (E. coli at WTP inlet → C1 / C2 / C3 / C4 / Indeterminate)

  AV-CLS-02  ADWG Cyanobacteria Alert Levels Framework
             (cell count, cyanobacterial biovolume, microcystin-LR →
              Below Detection / Detection / Alert Level 1 / Alert Level 2 /
              Indeterminate)

Output: List[CharacterisationFlag] written to CharacterisationReport.flags
        with rule_id="AV-CLS-01" or "AV-CLS-02".

The classification value (e.g. "C3 Poorly protected") goes into
CharacterisationFlag.pattern. The triggering statistic and window
coverage go into CharacterisationFlag.message.

Schema alignment
----------------
Uses existing report.py types only — no new dataclasses.
Per the v5.5 schema reconciliation (May 2026):
  classification → CharacterisationFlag(rule_id="AV-CLS-XX", pattern=<value>)
  Indeterminate  → CharacterisationFlag with pattern="Indeterminate" and
                   Statistic.applicability=APPLIC_INSUFFICIENT on the
                   triggering statistic.

Engineering basis [VERIFY against current editions before production]
---------------------------------------------------------------------
AV-CLS-01:
  WSAA Manual for Application of HBT for Drinking Water Safety (2015).
  Band boundaries: ≤1 → C1; >1 to ≤20 → C2; >20 to ≤2000 → C3; >2000 → C4.
  Statistic: P95 of E. coli over the last 24 months (or full record if shorter).
  Minimum data: ≥12 months OR ≥50 samples.

AV-CLS-02:
  ADWG (NHMRC, v3.7 2022) Cyanobacteria Information Sheet.
  Thresholds (cyanobacterial-specific — NOT total algal):
    Cells:     >500 → AL1; >6500 → AL2
    Biovolume: >0.04 mm³/L → AL1; >0.6 mm³/L → AL2  (cyanobacterial only)
    Toxin:     >1.3 µg/L microcystin-LR → AL2
  Look-back window: 24 months (engineering judgment; ADWG specifies thresholds,
  not window).
  Minimum data: ≥12 months.
"""
from __future__ import annotations

import warnings
from datetime import timedelta
from typing import List, Optional

import numpy as np
import pandas as pd

from .report import (
    APPLIC_INSUFFICIENT,
    APPLIC_LIMITED,
    APPLIC_OK,
    SEV_CRITICAL,
    SEV_INFO,
    SEV_WARNING,
    CharacterisationFlag,
)

# ── Constants ─────────────────────────────────────────────────────────────────

# AV-CLS-01 — HBT band boundaries (E. coli P95, organisms/100 mL)
_HBT_BANDS = [
    (0.0,    1.0,    "C1", "Well protected"),
    (1.0,   20.0,    "C2", "Moderately protected"),
    (20.0, 2000.0,   "C3", "Poorly protected"),
    (2000.0, np.inf, "C4", "Unprotected"),
]
_HBT_MIN_MONTHS = 12
_HBT_MIN_SAMPLES = 50
_HBT_WINDOW_MONTHS = 24

# AV-CLS-02 — Cyanobacteria Alert Levels
_AL_CELLS_1    =    500.0   # cells/mL → AL1
_AL_CELLS_2    =  6_500.0   # cells/mL → AL2
_AL_BV_1       =      0.04  # mm³/L cyanobacterial → AL1
_AL_BV_2       =      0.6   # mm³/L cyanobacterial → AL2
_AL_TOXIN_2    =      1.3   # µg/L microcystin-LR → AL2 (not AL1)
_AL_MIN_MONTHS = 12
_AL_WINDOW_MONTHS = 24

# Column names (canonical, post alias-resolution)
_ECOLI_COL   = "E_coli_MPN_100mL"
_CYANO_COL   = "Cyanobacteria_cells_mL"
_CYABV_COL   = "Cyanobacterial_Biovolume_mm3_L"
_MCST_COL    = "Microcystin_LR_ug_L"
_DATE_COL    = "_date"


# ── Internal helpers ──────────────────────────────────────────────────────────

def _record_months(df: pd.DataFrame) -> float:
    """Approximate record length in months."""
    if _DATE_COL not in df.columns or df[_DATE_COL].isna().all():
        return 0.0
    span_days = (df[_DATE_COL].max() - df[_DATE_COL].min()).days
    return span_days / 30.44


def _window_df(df: pd.DataFrame, months: int) -> tuple[pd.DataFrame, str]:
    """
    Return the subset of df within the last `months` months,
    and a coverage note string.
    """
    if _DATE_COL not in df.columns:
        return df, "date column unavailable"
    cutoff = df[_DATE_COL].max() - timedelta(days=months * 30.44)
    subset = df[df[_DATE_COL] >= cutoff]
    total_months = _record_months(df)
    if total_months >= months:
        note = f"{months}-month window — full"
    else:
        note = f"[partial window — only {total_months:.1f} months of data available]"
    return subset, note


def _p95(series: pd.Series) -> Optional[float]:
    """95th percentile of non-null values, or None."""
    valid = series.dropna()
    if len(valid) == 0:
        return None
    return float(np.percentile(valid, 95))


def _hbt_category(p95_value: float) -> tuple[str, str]:
    """Return (code, label) for a given E.coli P95 value."""
    for lo, hi, code, label in _HBT_BANDS:
        if lo < p95_value <= hi or (lo == 0.0 and p95_value <= hi):
            return code, label
    return "C4", "Unprotected"


def _al_level_from_channels(
    max_cells: Optional[float],
    max_bv: Optional[float],
    max_toxin: Optional[float],
    bv_is_cyanobacterial: bool,
) -> tuple[str, list[str]]:
    """
    Return (level_string, list_of_triggering_parameters).
    level_string ∈ {"Below Detection", "Detection", "Alert Level 1", "Alert Level 2"}
    """
    level = "Below Detection"
    triggers: list[str] = []

    # AL2 (escalation — check first)
    if max_cells is not None and max_cells > _AL_CELLS_2:
        level = "Alert Level 2"
        triggers.append(f"cells={max_cells:.0f} cells/mL (>{_AL_CELLS_2:.0f})")
    if bv_is_cyanobacterial and max_bv is not None and max_bv > _AL_BV_2:
        level = "Alert Level 2"
        triggers.append(f"cyanobacterial biovolume={max_bv:.3f} mm³/L (>{_AL_BV_2})")
    if max_toxin is not None and max_toxin > _AL_TOXIN_2:
        level = "Alert Level 2"
        triggers.append(f"microcystin-LR={max_toxin:.2f} µg/L (>{_AL_TOXIN_2})")

    if level == "Alert Level 2":
        return level, triggers

    # AL1
    if max_cells is not None and max_cells > _AL_CELLS_1:
        level = "Alert Level 1"
        triggers.append(f"cells={max_cells:.0f} cells/mL (>{_AL_CELLS_1:.0f})")
    if bv_is_cyanobacterial and max_bv is not None and max_bv > _AL_BV_1:
        level = "Alert Level 1"
        triggers.append(f"cyanobacterial biovolume={max_bv:.3f} mm³/L (>{_AL_BV_1})")

    if level == "Alert Level 1":
        return level, triggers

    # Detection (any cyano above LoD)
    if max_cells is not None and max_cells > 0:
        level = "Detection"
        triggers.append(f"cells={max_cells:.0f} cells/mL (above LoD)")

    return level, triggers


# ── Public API ────────────────────────────────────────────────────────────────

def classify_hbt(df: pd.DataFrame) -> List[CharacterisationFlag]:
    """
    AV-CLS-01: ADWG Health-Based Targets — Source-Water Category.

    Computes the P95 of E. coli over the last 24 months (or full record
    if shorter) and maps it to C1–C4. Returns a list with one flag,
    or an Indeterminate flag if data are insufficient.

    Parameters
    ----------
    df : pd.DataFrame
        Clean, sorted source water dataframe with canonical column names.
        Must contain '_date' and ideally 'E_coli_MPN_100mL'.

    Returns
    -------
    List[CharacterisationFlag]
        One flag with rule_id="AV-CLS-01".
    """
    flags: List[CharacterisationFlag] = []

    if _ECOLI_COL not in df.columns:
        flags.append(CharacterisationFlag(
            rule_id="AV-CLS-01",
            severity=SEV_INFO,
            parameter=_ECOLI_COL,
            pattern="Indeterminate",
            message=(
                "E. coli column not present in dataset. "
                "AV-CLS-01 (HBT Source-Water Category) cannot be computed. "
                "Upload a dataset containing E. coli measurements at the WTP inlet."
            ),
            implication=(
                "The ADWG HBT Source-Water Category cannot be assigned without "
                "E. coli data. This is required input for the multi-barrier "
                "log reduction credit framework."
            ),
            recommended_action="Include E. coli at WTP inlet in the dataset.",
        ))
        return flags

    record_months = _record_months(df)
    subset, window_note = _window_df(df, _HBT_WINDOW_MONTHS)
    ecoli = subset[_ECOLI_COL].dropna()
    n = len(ecoli)

    # Minimum data check
    sufficient = record_months >= _HBT_MIN_MONTHS and n >= _HBT_MIN_SAMPLES
    if not sufficient:
        reason_parts = []
        if record_months < _HBT_MIN_MONTHS:
            reason_parts.append(
                f"record is {record_months:.1f} months (minimum {_HBT_MIN_MONTHS} months required)"
            )
        if n < _HBT_MIN_SAMPLES:
            reason_parts.append(
                f"only {n} E. coli samples in window (minimum {_HBT_MIN_SAMPLES} required)"
            )
        flags.append(CharacterisationFlag(
            rule_id="AV-CLS-01",
            severity=SEV_WARNING,
            parameter=_ECOLI_COL,
            pattern="Indeterminate",
            message=(
                f"AV-CLS-01 Indeterminate — {'; '.join(reason_parts)}. "
                f"Window: {window_note}."
            ),
            implication=(
                "P95 E. coli from insufficient data is unreliable as a "
                "source-category anchor."
            ),
            recommended_action=(
                f"Collect at least {_HBT_MIN_MONTHS} months and "
                f"{_HBT_MIN_SAMPLES} E. coli samples before assigning HBT category."
            ),
        ))
        return flags

    p95_val = _p95(ecoli)
    if p95_val is None:
        flags.append(CharacterisationFlag(
            rule_id="AV-CLS-01",
            severity=SEV_WARNING,
            parameter=_ECOLI_COL,
            pattern="Indeterminate",
            message="All E. coli values are null in the window.",
            implication="Cannot assign HBT category.",
            recommended_action="Check E. coli data for completeness.",
        ))
        return flags

    code, label = _hbt_category(p95_val)
    severity = SEV_INFO if code in ("C1", "C2") else SEV_WARNING

    flags.append(CharacterisationFlag(
        rule_id="AV-CLS-01",
        severity=severity,
        parameter=_ECOLI_COL,
        pattern=f"{code} {label}",
        message=(
            f"ADWG HBT Source-Water Category: {code} — {label}. "
            f"P95 E. coli = {p95_val:.1f} organisms/100 mL "
            f"(n={n} samples). Window: {window_note}."
        ),
        implication=(
            f"Category {code} ({label}) determines the minimum log-reduction "
            "credit required from the multi-barrier treatment train under the "
            "ADWG HBT framework."
        ),
        recommended_action=(
            "Use this category as input to the treatment train LRV assessment. "
            "[VERIFY band boundaries against current WSAA HBT Manual edition.]"
        ),
    ))
    return flags


def classify_cyanobacteria_alert(
    df: pd.DataFrame,
    biovolume_is_cyanobacterial: bool = True,
) -> List[CharacterisationFlag]:
    """
    AV-CLS-02: ADWG Cyanobacteria Alert Levels Framework.

    Evaluates the highest alert level reached in the last 24 months
    across three channels: cell count, cyanobacterial biovolume, and
    microcystin-LR. Returns a list with one flag per channel assessed,
    plus a summary flag with the highest level reached.

    Parameters
    ----------
    df : pd.DataFrame
        Clean, sorted source water dataframe with canonical column names.
    biovolume_is_cyanobacterial : bool
        If True (default), the biovolume column is cyanobacterial-specific
        and the AL thresholds apply. If False (total algal biovolume was
        supplied), the biovolume channel is Indeterminate.

    Returns
    -------
    List[CharacterisationFlag]
        Flags with rule_id="AV-CLS-02". One summary flag plus channel-level
        Indeterminate flags where applicable.
    """
    flags: List[CharacterisationFlag] = []

    record_months = _record_months(df)
    if record_months < _AL_MIN_MONTHS:
        flags.append(CharacterisationFlag(
            rule_id="AV-CLS-02",
            severity=SEV_WARNING,
            parameter="",
            pattern="Indeterminate",
            message=(
                f"AV-CLS-02 Indeterminate — record is {record_months:.1f} months "
                f"(minimum {_AL_MIN_MONTHS} months required for cyanobacteria alert "
                "classification; algal blooms are seasonal and a shorter record may "
                "miss the peak-risk window)."
            ),
            implication=(
                "Cyanobacterial alert level cannot be reliably assigned. "
                "A full annual cycle is the minimum for bloom risk characterisation."
            ),
            recommended_action=(
                f"Continue monitoring until at least {_AL_MIN_MONTHS} months "
                "of data are available."
            ),
        ))
        return flags

    subset, window_note = _window_df(df, _AL_WINDOW_MONTHS)

    # ── Channel 1: cell count ─────────────────────────────────────────────────
    max_cells: Optional[float] = None
    if _CYANO_COL in subset.columns:
        valid = subset[_CYANO_COL].dropna()
        if len(valid) > 0:
            max_cells = float(valid.max())
    else:
        flags.append(CharacterisationFlag(
            rule_id="AV-CLS-02",
            severity=SEV_INFO,
            parameter=_CYANO_COL,
            pattern="Indeterminate — channel absent",
            message=(
                "Cyanobacterial cell count column not present. "
                "Cell-count channel of AV-CLS-02 not assessed."
            ),
            implication="Alert level assessment relies on biovolume and toxin channels only.",
            recommended_action="Include cyanobacterial cell count in the dataset.",
        ))

    # ── Channel 2: cyanobacterial biovolume ───────────────────────────────────
    max_bv: Optional[float] = None
    if not biovolume_is_cyanobacterial:
        flags.append(CharacterisationFlag(
            rule_id="AV-CLS-02",
            severity=SEV_WARNING,
            parameter=_CYABV_COL,
            pattern="Indeterminate — total algal biovolume supplied",
            message=(
                "The biovolume column contains total algal biovolume, not "
                "cyanobacterial-specific biovolume. ADWG Alert Level thresholds "
                "(0.04 / 0.6 mm³/L) apply to cyanobacterial biovolume only. "
                "Applying them to total algal biovolume would produce false "
                "positives in most temperate reservoirs. Biovolume channel skipped."
            ),
            implication=(
                "Alert Level 1/2 classification by biovolume is not possible. "
                "Cell count and toxin channels are still assessed."
            ),
            recommended_action=(
                "Commission cyanobacterial-specific biovolume (microscopy with "
                "species enumeration) to enable biovolume-channel classification."
            ),
        ))
    elif _CYABV_COL in subset.columns:
        valid = subset[_CYABV_COL].dropna()
        if len(valid) > 0:
            max_bv = float(valid.max())

    # ── Channel 3: microcystin-LR ─────────────────────────────────────────────
    max_toxin: Optional[float] = None
    if _MCST_COL in subset.columns:
        valid = subset[_MCST_COL].dropna()
        # Exclude zero-substituted values from max (all zeros = below LoD)
        above_lod = valid[valid > 0]
        if len(above_lod) > 0:
            max_toxin = float(above_lod.max())
    else:
        flags.append(CharacterisationFlag(
            rule_id="AV-CLS-02",
            severity=SEV_INFO,
            parameter=_MCST_COL,
            pattern="Indeterminate — channel absent",
            message=(
                "Microcystin-LR column not present. "
                "Toxin channel of AV-CLS-02 not assessed."
            ),
            implication="AL2 toxin-trigger cannot be evaluated.",
            recommended_action=(
                "Include microcystin-LR measurements during algal bloom periods."
            ),
        ))

    # If no channels have data, return Indeterminate
    if max_cells is None and max_bv is None and max_toxin is None:
        flags.append(CharacterisationFlag(
            rule_id="AV-CLS-02",
            severity=SEV_WARNING,
            parameter="",
            pattern="Indeterminate",
            message=(
                "No cyanobacteria parameters present in dataset. "
                "AV-CLS-02 cannot be assessed."
            ),
            implication="Cyanobacterial risk cannot be characterised.",
            recommended_action=(
                "Include cyanobacterial cell count, biovolume, or microcystin-LR "
                "in the dataset."
            ),
        ))
        return flags

    # ── Summary flag ──────────────────────────────────────────────────────────
    level, triggers = _al_level_from_channels(
        max_cells, max_bv, max_toxin,
        bv_is_cyanobacterial=biovolume_is_cyanobacterial,
    )

    severity = {
        "Below Detection": SEV_INFO,
        "Detection":       SEV_INFO,
        "Alert Level 1":   SEV_WARNING,
        "Alert Level 2":   SEV_CRITICAL,
    }.get(level, SEV_WARNING)

    trigger_str = "; ".join(triggers) if triggers else "no threshold exceeded"

    flags.append(CharacterisationFlag(
        rule_id="AV-CLS-02",
        severity=severity,
        parameter="",
        pattern=level,
        message=(
            f"ADWG Cyanobacteria Alert Level: {level}. "
            f"Highest level reached in window ({window_note}). "
            f"Triggers: {trigger_str}."
        ),
        implication=(
            f"Alert Level {level} reached in the 24-month look-back window. "
            + (
                "Ozone sequencing must follow cell removal (DAF or sedimentation "
                "before ozone) to avoid toxin and T&O compound release. "
                if level in ("Alert Level 1", "Alert Level 2") else ""
            )
        ),
        recommended_action=(
            "Review the events table (EV-03) for specific bloom episode dates. "
            "[VERIFY thresholds against current ADWG v3.7 2022 Cyanobacteria "
            "Information Sheet.]"
        ),
    ))
    return flags


def run_cls_classification(
    df: pd.DataFrame,
    biovolume_is_cyanobacterial: bool = True,
) -> List[CharacterisationFlag]:
    """
    Run both AV-CLS-01 and AV-CLS-02 and return combined flags.

    This is the single entry point for the orchestrator or page_02 to call.
    Results are added to CharacterisationReport.flags by the caller.
    """
    flags: List[CharacterisationFlag] = []
    flags.extend(classify_hbt(df))
    flags.extend(classify_cyanobacteria_alert(df, biovolume_is_cyanobacterial))
    flags.extend(classify_suva(df))
    return flags


# ══════════════════════════════════════════════════════════════════════════════
# AV-CLS-03: SUVA Source-Water Classification
# ══════════════════════════════════════════════════════════════════════════════
#
# Classifies raw source water organic character using Specific UV Absorbance
# (SUVA) bands. Reports classification on both the median (source character)
# and P90 (high-end condition) of the record window.
#
# SUVA bands (engineering judgment — see §2 classification registry):
#   S1  SUVA <2 L/mg/m  — non-humic, hydrophilic DOC, low aromatic character
#   S2  SUVA 2–4 L/mg/m — mixed / moderate humic character
#   S3  SUVA 4–6 L/mg/m — high humic, aromatic DOC, elevated DBP precursor
#   S4  SUVA >6 L/mg/m  — very high humic / tannin-stained, high DBP precursor
#
# Engineering basis [VERIFY]:
#   Edzwald & Tobiason (1999) J. AWWA — SUVA as coagulation and NOM
#   characterisation parameter.
#   Weishaar et al. (2003) ES&T — SUVA as predictor of DBP precursor potential.
#   AWWA (2011) Coagulation and Flocculation manual.
#   Band boundaries are engineering convention, not regulatory specification.
#
# Output: List[CharacterisationFlag] with rule_id="AV-CLS-03"
#   - One summary flag (median classification + P90 flag if P90 in higher band)
#   - One Indeterminate flag if SUVA not available or insufficient data

_SUVA_COL = "SUVA"
_SUVA_MIN_N = 30
_SUVA_WINDOW_MONTHS = 24

_SUVA_BANDS = [
    (0.0,  2.0, "S1", "Non-humic / hydrophilic",
     "Low aromatic character. DOC is predominantly hydrophilic and non-humic. "
     "DBP precursor potential is generally low relative to humic sources."),
    (2.0,  4.0, "S2", "Moderate humic character",
     "Mixed hydrophilic and humic DOC fractions. Moderate aromatic character. "
     "DBP precursor potential is moderate."),
    (4.0,  6.0, "S3", "High humic / aromatic",
     "DOC is predominantly humic and aromatic. Elevated DBP precursor potential. "
     "Consistent with catchments with significant organic soil or riparian organic inputs."),
    (6.0, 99.0, "S4", "Very high humic / tannin-stained",
     "Very high aromatic character. Consistent with highly humic, tannin-stained "
     "catchment water (e.g. upland peat, tea-coloured highland streams). "
     "High DBP precursor potential across the full record."),
]


def _suva_band(value: float) -> tuple[str, str, str]:
    """Return (code, label, description) for a SUVA value."""
    for lo, hi, code, label, desc in _SUVA_BANDS:
        if lo <= value < hi:
            return code, label, desc
    return "S4", "Very high humic / tannin-stained", _SUVA_BANDS[-1][4]


def classify_suva(df: pd.DataFrame) -> List[CharacterisationFlag]:
    """
    AV-CLS-03: SUVA Source-Water Classification.

    Classifies the source's organic character on the record median and P90
    of SUVA. SUVA must be present as a pre-computed column (canonical name
    'SUVA') or will be computed from UV254_cm_1 and DOC_mg_L if both are
    available.

    Parameters
    ----------
    df : pd.DataFrame
        Clean, sorted source water dataframe with canonical column names.

    Returns
    -------
    List[CharacterisationFlag]
        One or two flags with rule_id="AV-CLS-03".
    """
    import numpy as _np
    flags: List[CharacterisationFlag] = []

    # Resolve SUVA — use stored column or compute from components
    if _SUVA_COL in df.columns and df[_SUVA_COL].notna().sum() >= _SUVA_MIN_N:
        suva_series = df[_SUVA_COL].dropna()
        source_note = "SUVA column present in dataset"
    elif "UV254_cm_1" in df.columns and "DOC_mg_L" in df.columns:
        raw = (df["UV254_cm_1"] * 100.0) / df["DOC_mg_L"]
        suva_series = raw.replace([_np.inf, -_np.inf], _np.nan).dropna()
        source_note = "SUVA computed from UV254_cm_1 × 100 / DOC_mg_L"
        if len(suva_series) < _SUVA_MIN_N:
            flags.append(CharacterisationFlag(
                rule_id="AV-CLS-03",
                severity=SEV_INFO,
                parameter=_SUVA_COL,
                pattern="Indeterminate",
                message=(
                    f"AV-CLS-03 Indeterminate — insufficient paired UV254/DOC observations "
                    f"to compute SUVA (n={len(suva_series)}, minimum {_SUVA_MIN_N} required)."
                ),
                implication="SUVA organic character classification cannot be assigned.",
                recommended_action=(
                    "Ensure UV254 and DOC are measured concurrently and consistently."
                ),
            ))
            return flags
    else:
        flags.append(CharacterisationFlag(
            rule_id="AV-CLS-03",
            severity=SEV_INFO,
            parameter=_SUVA_COL,
            pattern="Indeterminate",
            message=(
                "AV-CLS-03 Indeterminate — SUVA column not present and UV254/DOC "
                "columns not both available for computation."
            ),
            implication="Organic character classification cannot be assigned.",
            recommended_action=(
                "Include UV254 and DOC measurements in the dataset to enable "
                "SUVA-based organic character classification."
            ),
        ))
        return flags

    # Windowed statistics
    subset, window_note = _window_df(df, _SUVA_WINDOW_MONTHS)
    if _SUVA_COL in subset.columns:
        suva_window = subset[_SUVA_COL].dropna()
    elif "UV254_cm_1" in subset.columns and "DOC_mg_L" in subset.columns:
        raw = (subset["UV254_cm_1"] * 100.0) / subset["DOC_mg_L"]
        suva_window = raw.replace([_np.inf, -_np.inf], _np.nan).dropna()
    else:
        suva_window = suva_series

    if len(suva_window) < _SUVA_MIN_N:
        suva_window = suva_series  # fall back to full record

    suva_median = float(suva_window.median())
    suva_p90    = float(_np.percentile(suva_window, 90))
    suva_p10    = float(_np.percentile(suva_window, 10))
    n           = len(suva_window)

    med_code, med_label, med_desc = _suva_band(suva_median)
    p90_code, p90_label, _       = _suva_band(suva_p90)

    severity = SEV_INFO if med_code in ("S1", "S2") else SEV_WARNING

    flags.append(CharacterisationFlag(
        rule_id="AV-CLS-03",
        severity=severity,
        parameter=_SUVA_COL,
        pattern=f"{med_code} {med_label}",
        message=(
            f"AV-CLS-03 SUVA Organic Character: {med_code} — {med_label}. "
            f"Median SUVA = {suva_median:.2f} L/mg/m (P10 = {suva_p10:.2f}, "
            f"P90 = {suva_p90:.2f}, n = {n}). "
            f"Window: {window_note}. Source: {source_note}."
        ),
        implication=med_desc,
        recommended_action=(
            "SUVA classification is an observed characterisation of organic matter "
            "type. Its implications for coagulation strategy, DBP precursor management, "
            "and activated carbon sizing are matters for engineering assessment. "
            "[VERIFY band boundaries against current Edzwald & Tobiason (1999) "
            "and AWWA Coagulation Manual guidance.]"
        ),
    ))

    # P90 flag — if P90 is in a higher band than the median classification
    if p90_code != med_code:
        flags.append(CharacterisationFlag(
            rule_id="AV-CLS-03",
            severity=SEV_WARNING,
            parameter=_SUVA_COL,
            pattern=f"P90 in higher band: {p90_code} {p90_label}",
            message=(
                f"AV-CLS-03 SUVA P90 ({suva_p90:.2f} L/mg/m) falls in a higher band "
                f"({p90_code} — {p90_label}) than the median classification "
                f"({med_code} — {med_label}). "
                f"High-end organic loading events are characteristically more aromatic "
                f"than the source's typical condition."
            ),
            implication=(
                "The high-end organic loading condition presents a more challenging "
                "aromatic DOC profile than the median classification indicates. "
                "This is typically associated with storm or wet-season flushing events."
            ),
            recommended_action=(
                "Consider the P90 SUVA condition in addition to the median when "
                "characterising the source's DBP precursor loading envelope."
            ),
        ))

    return flags
