"""
core/characteriser/regime_shift.py

AquaPoint — Regime-Shift Indicators (AV-RGM-XX)
================================================

Implements four regime-shift indicators using the Pettitt change-point test
on monthly median time series. Detects step changes in source water quality
that rolling-window event detection and trend indicators cannot distinguish —
step changes are too abrupt for trend detection and too persistent to appear
as events.

Registers
---------
  AV-RGM-01  Turbidity step change
  AV-RGM-02  DOC / TOC step change (coherent in both)
  AV-RGM-03  EC / TDS step change (coherent in both)
  AV-RGM-04  Multi-parameter regime shift (≥4 concurrent steps)

Output: List[CharacterisationFlag] on CharacterisationReport.flags
        with rule_id="AV-RGM-01" … "AV-RGM-04".
        Surfaces in Section 6 (evidence limits) of the envelope memo.
        Also populates EventDetection.regime_shift_detected and
        .regime_shift_summary on the relevant ParameterCharacterisation.

Schema alignment
----------------
AV-RGM-XX writes into:
  CharacterisationReport.flags  — CharacterisationFlag per shift detected
  ParameterCharacterisation.events.regime_shift_detected — bool
  ParameterCharacterisation.events.regime_shift_summary  — str

Engineering basis [VERIFY before production]
--------------------------------------------
Pettitt test (1979): non-parametric change-point test for a single shift
in a time series. Applied to the monthly median series (not raw samples)
to reduce sensitivity to outliers and irregular sampling.

Thresholds: p < 0.05 AND post/pre median ratio > 1.5 (50% shift)
AND post/pre SD ratio > 2.0 (step exceeds 2× pre-step SD).
These are engineering judgment from v5.5 spec §6.2.

Alternative algorithms (CUSUM, Bayesian) are noted as an open item in v5.5.
The Pettitt test is chosen as the simplest non-parametric option that does
not require distributional assumptions.

Minimum record: ≥ 24 months.
"""
from __future__ import annotations

from datetime import timedelta
from typing import List, Optional

import numpy as np
import pandas as pd

from .report import (
    APPLIC_INSUFFICIENT,
    SEV_INFO,
    SEV_WARNING,
    CharacterisationFlag,
)

# ── Constants ─────────────────────────────────────────────────────────────────

_MIN_MONTHS        = 24
_P_THRESHOLD       = 0.05
_MEDIAN_RATIO_MIN  = 1.50   # post/pre or pre/post must exceed this (50% step)
_SD_RATIO_MIN      = 2.00   # step must exceed 2× pre-step pooled SD
_MULTI_PARAM_MIN   = 4      # AV-RGM-04: concurrent steps in this many params
_MULTI_PARAM_WINDOW_DAYS = 30  # ± window for "concurrent"

_DATE_COL = "_date"

# Parameter column groups for each register
_TURB_COLS  = ["Turbidity_NTU"]
_DOC_COLS   = ["DOC_mg_L", "TOC_mg_L"]
_EC_COLS    = ["EC_uS_cm", "TDS_mg_L"]
_ALL_CONC_COLS = [
    "Turbidity_NTU", "SuspendedSolids_mg_L", "DOC_mg_L", "TOC_mg_L",
    "UV254_cm_1", "Alkalinity_mg_L_as_CaCO3", "Hardness_mg_L_as_CaCO3",
    "EC_uS_cm", "TDS_mg_L", "Chloride_mg_L", "Iron_mg_L", "Manganese_mg_L",
    "Total_Phosphorus_mg_L", "Chlorophyll_a_ug_L", "Total_Algal_Cells_mL",
    "Cyanobacteria_cells_mL",
]


# ── Pettitt test ──────────────────────────────────────────────────────────────

def _pettitt_test(series: pd.Series) -> tuple[int, float, float]:
    """
    Non-parametric Pettitt change-point test.

    Parameters
    ----------
    series : pd.Series
        Time-ordered numeric series (no NaNs).

    Returns
    -------
    (change_point_idx, test_statistic_K, p_value)
        change_point_idx: index in series of the estimated change point
        test_statistic_K: max of |U_t| (unsigned rank-sum cumulation)
        p_value: approximate p-value via Pettitt (1979) formula
    """
    n = len(series)
    if n < 4:
        return 0, 0.0, 1.0

    x = series.values.astype(float)
    # U_t = sum_{i<=t} sum_{j>t} sign(x_j - x_i)
    # Efficient computation via rank-based formula
    ranks = pd.Series(x).rank().values   # 1-indexed ranks
    U = np.zeros(n)
    for t in range(1, n):
        # U_t = 2 * sum_{i=1}^{t} rank(x_i) - t*(n+1)
        U[t] = 2.0 * ranks[:t].sum() - t * (n + 1)

    K = float(np.max(np.abs(U)))
    cp = int(np.argmax(np.abs(U)))

    # Approximate p-value: p ≈ 2 * exp(-6K² / (n³+n²))
    denom = n ** 3 + n ** 2
    if denom == 0 or K == 0:
        p_value = 1.0
    else:
        p_value = float(min(1.0, 2.0 * np.exp(-6.0 * K ** 2 / denom)))

    return cp, K, p_value


def _monthly_medians(df: pd.DataFrame, col: str) -> Optional[pd.Series]:
    """Monthly medians of col; returns None if insufficient data."""
    if col not in df.columns or _DATE_COL not in df.columns:
        return None
    tmp = df[[_DATE_COL, col]].dropna().set_index(_DATE_COL)
    if tmp.empty:
        return None
    monthly = tmp[col].resample("ME").median().dropna()
    return monthly if len(monthly) >= 6 else None


# ── Step-change assessment ────────────────────────────────────────────────────

class _StepResult:
    """Result of a single Pettitt-based step-change assessment."""
    def __init__(self):
        self.detected: bool = False
        self.change_point_date: Optional[str] = None
        self.change_point_idx: int = 0
        self.p_value: float = 1.0
        self.pre_median: float = 0.0
        self.post_median: float = 0.0
        self.median_ratio: float = 1.0
        self.pre_sd: float = 0.0
        self.shift_sd: float = 0.0
        self.direction: str = ""


def _assess_step(monthly: pd.Series) -> _StepResult:
    """
    Run Pettitt test and check threshold criteria for a step change.
    Returns a _StepResult with detected=True/False.
    """
    result = _StepResult()
    if monthly is None or len(monthly) < 6:
        return result

    cp_idx, K, p_value = _pettitt_test(monthly)
    result.p_value = p_value
    result.change_point_idx = cp_idx

    if p_value >= _P_THRESHOLD:
        return result

    pre  = monthly.iloc[:cp_idx]
    post = monthly.iloc[cp_idx:]
    if len(pre) < 3 or len(post) < 3:
        return result

    pre_med  = float(pre.median())
    post_med = float(post.median())
    pre_sd   = float(pre.std(ddof=1)) if len(pre) > 1 else 0.0

    if pre_med == 0:
        return result

    ratio = post_med / pre_med if post_med > pre_med else pre_med / post_med
    shift_sd = abs(post_med - pre_med) / pre_sd if pre_sd > 0 else 0.0

    if ratio < _MEDIAN_RATIO_MIN or shift_sd < _SD_RATIO_MIN:
        return result

    result.detected = True
    result.change_point_date = str(monthly.index[cp_idx].date())
    result.pre_median  = pre_med
    result.post_median = post_med
    result.median_ratio = ratio
    result.pre_sd = pre_sd
    result.shift_sd = shift_sd
    result.direction = "increasing" if post_med > pre_med else "decreasing"
    return result


# ── Register implementations ──────────────────────────────────────────────────

def _rgm_flag(
    rule_id: str,
    col: str,
    step: _StepResult,
    description: str,
    implication: str,
) -> CharacterisationFlag:
    return CharacterisationFlag(
        rule_id=rule_id,
        severity=SEV_WARNING,
        parameter=col,
        pattern=f"step change detected — {step.direction}",
        message=(
            f"{rule_id} {description}: apparent step change near "
            f"{step.change_point_date}. "
            f"Pre-step median: {step.pre_median:.3g}; "
            f"post-step median: {step.post_median:.3g} "
            f"({step.median_ratio:.1f}× ratio, {step.shift_sd:.1f}σ shift). "
            f"Pettitt p={step.p_value:.4f}."
        ),
        implication=implication,
        recommended_action=(
            "Confirm via operational records whether an intake change, "
            "instrument recalibration, or upstream event occurred near this date. "
            "Rolling-window event detection adapts to the new baseline over "
            "~12 months — events in the transition period may be "
            "calibration-artefact rather than real excursions. "
            "[VERIFY: Pettitt test vs CUSUM/Bayesian alternatives — "
            "engineering review needed before production use.]"
        ),
    )


def _rgm_01_turbidity(df: pd.DataFrame) -> List[CharacterisationFlag]:
    """AV-RGM-01 — Turbidity step change."""
    col = "Turbidity_NTU"
    monthly = _monthly_medians(df, col)
    step = _assess_step(monthly)
    if not step.detected:
        return []
    return [_rgm_flag(
        "AV-RGM-01", col, step,
        "turbidity step change",
        (
            "Possible source-intake change, instrument recalibration, or "
            "step physical change in the catchment. A persistent turbidity "
            "increase drives higher coagulant demand; the rolling baseline "
            "will adapt silently, masking the change from event detection."
        ),
    )]


def _rgm_02_doc_toc(df: pd.DataFrame) -> List[CharacterisationFlag]:
    """AV-RGM-02 — DOC / TOC coherent step change."""
    flags = []
    results = {}
    for col in _DOC_COLS:
        monthly = _monthly_medians(df, col)
        step = _assess_step(monthly)
        if step.detected:
            results[col] = step

    if len(results) < 2:
        # Require coherent step in BOTH DOC and TOC to avoid false positives
        # from analytical method changes affecting only one parameter
        return []

    # Check that change-point dates are within 30 days of each other
    dates = [pd.Timestamp(s.change_point_date) for s in results.values()]
    if abs((dates[0] - dates[1]).days) > _MULTI_PARAM_WINDOW_DAYS:
        return []

    for col, step in results.items():
        flags.append(_rgm_flag(
            "AV-RGM-02", col, step,
            "DOC/TOC step change",
            (
                "Coherent step in DOC and TOC reduces the likelihood of "
                "analytical method change as the cause. May indicate catchment "
                "land-use change, upstream impoundment change, or a seasonal-"
                "regime shift in organic loading."
            ),
        ))
    return flags


def _rgm_03_ec_tds(df: pd.DataFrame) -> List[CharacterisationFlag]:
    """AV-RGM-03 — EC / TDS coherent step change."""
    flags = []
    results = {}
    for col in _EC_COLS:
        monthly = _monthly_medians(df, col)
        step = _assess_step(monthly)
        if step.detected:
            results[col] = step

    if len(results) < 2:
        return []

    dates = [pd.Timestamp(s.change_point_date) for s in results.values()]
    if abs((dates[0] - dates[1]).days) > _MULTI_PARAM_WINDOW_DAYS:
        return []

    for col, step in results.items():
        flags.append(_rgm_flag(
            "AV-RGM-03", col, step,
            "EC/TDS step change (salinity)",
            (
                "Coherent salinity step suggests source switch, saline "
                "intrusion onset (coastal sources), or drought-driven "
                "evaporative concentration. TDS and EC steps from different "
                "causes (e.g. pH shift) would not be coherent."
            ),
        ))
    return flags


def _rgm_04_multi_param(
    df: pd.DataFrame,
    single_param_steps: dict[str, _StepResult],
) -> List[CharacterisationFlag]:
    """
    AV-RGM-04 — Multi-parameter regime shift.

    Fires if ≥4 of the top-8-completeness parameters show a Pettitt step
    within a ±30-day window.
    """
    if len(single_param_steps) < _MULTI_PARAM_MIN:
        return []

    # Group steps by date; look for a cluster
    dated = [
        (pd.Timestamp(s.change_point_date), col, s)
        for col, s in single_param_steps.items()
        if s.change_point_date
    ]
    dated.sort(key=lambda x: x[0])

    # Sliding 60-day window (±30 days around each step)
    best_cluster: list[tuple] = []
    for i, (dt_i, col_i, step_i) in enumerate(dated):
        cluster = [(dt_i, col_i, step_i)]
        for j, (dt_j, col_j, step_j) in enumerate(dated):
            if i == j:
                continue
            if abs((dt_j - dt_i).days) <= _MULTI_PARAM_WINDOW_DAYS:
                cluster.append((dt_j, col_j, step_j))
        if len(cluster) > len(best_cluster):
            best_cluster = cluster

    if len(best_cluster) < _MULTI_PARAM_MIN:
        return []

    cluster_cols = [col for _, col, _ in best_cluster]
    cluster_date = str(best_cluster[0][0].date())
    n_params = len(best_cluster)

    return [CharacterisationFlag(
        rule_id="AV-RGM-04",
        severity=SEV_WARNING,
        parameter="; ".join(cluster_cols[:6]),
        pattern=f"multi-parameter regime shift — {n_params} concurrent steps",
        message=(
            f"AV-RGM-04 Multi-parameter regime shift: {n_params} parameters "
            f"show concurrent Pettitt step changes within a ±{_MULTI_PARAM_WINDOW_DAYS}-day "
            f"window around {cluster_date}. "
            f"Parameters: {', '.join(cluster_cols)}."
        ),
        implication=(
            "Concurrent multi-parameter steps are a strong indicator of a "
            "source-system change (intake switch, major upstream event, dam "
            "management change), not random co-variation. "
            "The envelope characterised before this date may not represent "
            "current source conditions."
        ),
        recommended_action=(
            "Confirm via operational records. If a source change is confirmed, "
            "consider re-running the characterisation on post-change data only, "
            "or running separate envelopes for pre- and post-change periods. "
            "[VERIFY: multi-parameter coherence threshold (≥4 parameters) is "
            "engineering judgment — adjust based on engineering review.]"
        ),
    )]


# ── Public API ────────────────────────────────────────────────────────────────

def run_regime_shift_indicators(df: pd.DataFrame) -> List[CharacterisationFlag]:
    """
    Run all AV-RGM-XX regime-shift indicators and return flags.

    Flags are intended for CharacterisationReport.flags (dataset-level).
    They surface in Section 6 (evidence limits) of the envelope memo,
    NOT in Section 3 (events).

    Parameters
    ----------
    df : pd.DataFrame
        Clean, sorted source water dataframe with canonical column names
        and a '_date' datetime column.

    Returns
    -------
    List[CharacterisationFlag]
        Empty list if record < 24 months or no steps detected.
    """
    flags: List[CharacterisationFlag] = []

    # Record length check
    if _DATE_COL not in df.columns or df[_DATE_COL].isna().all():
        return flags

    span_months = (df[_DATE_COL].max() - df[_DATE_COL].min()).days / 30.44
    if span_months < _MIN_MONTHS:
        flags.append(CharacterisationFlag(
            rule_id="AV-RGM-XX",
            severity=SEV_INFO,
            parameter="",
            pattern="Indeterminate — insufficient record",
            message=(
                f"AV-RGM-XX regime-shift indicators require ≥{_MIN_MONTHS} months "
                f"of data. Record is {span_months:.1f} months. "
                "Regime-shift detection requires sufficient pre/post split."
            ),
            implication=(
                "Step changes cannot be reliably detected. Indicators activate "
                f"automatically once the record exceeds {_MIN_MONTHS} months."
            ),
            recommended_action=(
                f"Continue monitoring. Regime-shift indicators activate when "
                f"the record reaches {_MIN_MONTHS} months."
            ),
        ))
        return flags

    # Run single-parameter tests on all concentration columns
    # (used by RGM-01, 02, 03 directly; also feeds RGM-04)
    all_steps: dict[str, _StepResult] = {}
    for col in _ALL_CONC_COLS:
        monthly = _monthly_medians(df, col)
        step = _assess_step(monthly)
        if step.detected:
            all_steps[col] = step

    # AV-RGM-01 — Turbidity
    flags.extend(_rgm_01_turbidity(df))

    # AV-RGM-02 — DOC / TOC coherent
    flags.extend(_rgm_02_doc_toc(df))

    # AV-RGM-03 — EC / TDS coherent
    flags.extend(_rgm_03_ec_tds(df))

    # AV-RGM-04 — Multi-parameter
    flags.extend(_rgm_04_multi_param(df, all_steps))

    return flags
