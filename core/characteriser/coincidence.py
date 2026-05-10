"""
core/characteriser/coincidence.py
Minimal stub of the coincidence/joint-conditional analysis module.

Phase 5 (design_envelope.py and envelope_charts.py) consumes three names
from here:

  analyse_coincidence(df, condition_spec, condition_label,
                      parameters_to_report) -> CoincidenceAnalysis
  compare_to_naive_stacking(df, governing_parameter, governing_percentile,
                            coincident_parameters, design_concern)
                            -> OverDesignComparison
  _build_mask(df, condition_spec) -> (mask: pd.Series, label: str)

This stub provides real (not mocked) implementations sufficient for the
Phase 5 orchestrator to run end-to-end against synthetic data. The
production coincidence.py will likely carry more: weighted statistics,
event-coincidence overlays, etc. The contract surface here is what
Phase 5 commits to.

Condition spec language
-----------------------
Phase 5 passes conditions like {"flow_mld": ">P95"}. Supported forms:
  ">PXX"   : value strictly above the XX-th percentile of that column
  "<PXX"   : value strictly below the XX-th percentile
  ">=PXX"  : at or above
  "<=PXX"  : at or below
  ">N"     : numeric comparison
  "<N"
  ">=N"
  "<=N"
  "==N" or "=N"
  bool     : column is treated as truthy/falsy

A spec is a dict of column → expression; all expressions must be satisfied
(logical AND).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd

from .report import CoincidenceAnalysis, ConditionalParameterStat


# ── OverDesignComparison ─────────────────────────────────────────────────────
# Lives in this module (not report.py) because it is conceptually a coincidence-
# analysis output. Phase 5 imports it indirectly via the comparison object
# that compare_to_naive_stacking returns.

@dataclass
class OverDesignComparison:
    """
    Result of comparing naive-stacked P95 against observed joint medians
    under a governing condition.

    Consumed by envelope_renderer (section 4) and envelope_charts (figure 4.1).

    coincident_parameters: dict of parameter_name → (naive_p95, joint_median).
    """
    governing_parameter: str
    governing_percentile: float
    governing_value: float
    coincident_parameters: Dict[str, Tuple[float, float]] = field(default_factory=dict)
    design_concern: str = ""


# ── Expression parser ────────────────────────────────────────────────────────

_PCT_RE = re.compile(r"^\s*(>=|<=|>|<|==|=)\s*P(\d{1,3}(?:\.\d+)?)\s*$")
_NUM_RE = re.compile(r"^\s*(>=|<=|>|<|==|=)\s*([+-]?\d+(?:\.\d+)?)\s*$")


def _eval_expr(series: pd.Series, expr) -> Optional[pd.Series]:
    """
    Evaluate one condition expression against a series, returning a bool mask
    aligned to the series, or None if the expression can't be parsed.
    """
    if isinstance(expr, bool):
        return series.astype(bool) == expr

    if isinstance(expr, (int, float)) and not isinstance(expr, bool):
        return series == expr

    if not isinstance(expr, str):
        return None

    s = expr.strip()

    # Percentile form
    m = _PCT_RE.match(s)
    if m is not None:
        op = m.group(1)
        pct = float(m.group(2))
        if not (0.0 <= pct <= 100.0):
            return None
        try:
            threshold = float(series.dropna().quantile(pct / 100.0))
        except Exception:
            return None
        return _apply_op(series, op, threshold)

    # Numeric form
    m = _NUM_RE.match(s)
    if m is not None:
        op = m.group(1)
        val = float(m.group(2))
        return _apply_op(series, op, val)

    return None


def _apply_op(series: pd.Series, op: str, threshold: float) -> pd.Series:
    if op == ">":
        return series > threshold
    if op == "<":
        return series < threshold
    if op == ">=":
        return series >= threshold
    if op == "<=":
        return series <= threshold
    if op in ("==", "="):
        return series == threshold
    # Should never reach here given regexes above
    return pd.Series([False] * len(series), index=series.index)


# ── Public: _build_mask ─────────────────────────────────────────────────────

def _build_mask(df: pd.DataFrame,
                condition_spec: Dict[str, Union[str, bool, int, float]]
                ) -> Tuple[Optional[pd.Series], str]:
    """
    Build a boolean row-mask for the given condition.

    Returns (mask, label):
      mask  : boolean Series indexed like df, True for rows that match all
              conditions. NaN values in any conditioning column yield False
              for that row (NaN cannot be confirmed to satisfy the condition).
              Returns None if the spec is unparseable or no columns match.
      label : human-readable description of the condition (e.g.
              "flow_mld >P95 AND temperature_c <P10").
    """
    if not condition_spec:
        return (None, "")

    label_parts: List[str] = []
    mask: Optional[pd.Series] = None

    for col, expr in condition_spec.items():
        if col not in df.columns:
            # Column missing — condition cannot be evaluated
            return (None, f"column '{col}' not in dataframe")

        series = df[col]
        sub_mask = _eval_expr(series, expr)
        if sub_mask is None:
            return (None, f"unparseable expression: {col} {expr}")

        # NaN values cannot satisfy the condition
        sub_mask = sub_mask.fillna(False).astype(bool)

        mask = sub_mask if mask is None else (mask & sub_mask)
        label_parts.append(f"{col} {expr}")

    return (mask, " AND ".join(label_parts))


# ── Confidence ladder for sample size ───────────────────────────────────────

def _confidence_for_n(n: int) -> Tuple[str, str]:
    """Map matching-subset size to (confidence_label, rationale)."""
    if n < 10:
        return ("Insufficient",
                f"Only {n} matching observations; the conditional distribution "
                "cannot be estimated from this sample.")
    if n < 30:
        return ("Limited",
                f"{n} matching observations; the conditional distribution is "
                "estimated with low confidence. Suitable for orientation only.")
    if n < 100:
        return ("Acceptable",
                f"{n} matching observations; the conditional distribution is "
                "estimated with low-to-moderate confidence. Suitable for "
                "design-stage filtering but not for procurement commitments.")
    return ("Strong",
            f"{n} matching observations; the conditional distribution is "
            "well-estimated.")


# ── Public: analyse_coincidence ─────────────────────────────────────────────

def _classify_shift(overall_median: Optional[float],
                    conditional_median: Optional[float]
                    ) -> Tuple[str, Optional[float], str]:
    """
    Compare conditional vs overall median.

    Returns (direction, magnitude_pct, significance):
      direction       : "increased" | "decreased" | "stable"
      magnitude_pct   : signed % difference, or None if overall is zero
      significance    : "Strong" | "Moderate" | "Weak" | "None"
    """
    if overall_median is None or conditional_median is None:
        return ("", None, "")

    if overall_median == 0:
        if conditional_median == 0:
            return ("stable", 0.0, "None")
        return ("increased" if conditional_median > 0 else "decreased",
                None, "Strong")

    pct = 100.0 * (conditional_median - overall_median) / abs(overall_median)
    a = abs(pct)

    if a < 5.0:
        return ("stable", pct, "None")
    if a < 15.0:
        sig = "Weak"
    elif a < 30.0:
        sig = "Moderate"
    else:
        sig = "Strong"

    direction = "increased" if pct > 0 else "decreased"
    return (direction, pct, sig)


def analyse_coincidence(df: pd.DataFrame,
                        condition_spec: Dict,
                        condition_label: str = "",
                        parameters_to_report: Optional[List[str]] = None
                        ) -> CoincidenceAnalysis:
    """
    Compute conditional medians and percentiles for each parameter on rows
    that satisfy the condition.

    The returned CoincidenceAnalysis is consumed by Phase 5's
    _build_population_section.
    """
    out = CoincidenceAnalysis(
        condition_label=condition_label,
        condition_spec={k: str(v) for k, v in condition_spec.items()},
        n_total=len(df),
    )

    mask, label = _build_mask(df, condition_spec)
    if mask is None:
        out.confidence = "Insufficient"
        out.confidence_rationale = f"Condition could not be evaluated ({label})."
        return out

    n_matching = int(mask.sum())
    out.n_matching = n_matching
    out.matching_pct = (100.0 * n_matching / len(df)) if len(df) else 0.0

    conf, rationale = _confidence_for_n(n_matching)
    out.confidence = conf
    out.confidence_rationale = rationale

    # Matching dates (if available)
    if "_date" in df.columns:
        matching_dates = df.loc[mask, "_date"]
        out.matching_dates = matching_dates.dt.strftime("%Y-%m-%d").tolist()

    if conf == "Insufficient":
        return out

    # Per-parameter conditional stats
    if parameters_to_report is None:
        # Default: every numeric column
        parameters_to_report = [c for c in df.columns
                                if c != "_date"
                                and pd.api.types.is_numeric_dtype(df[c])]

    subset = df[mask]
    for param in parameters_to_report:
        if param not in df.columns:
            continue
        if not pd.api.types.is_numeric_dtype(df[param]):
            continue

        overall = df[param].dropna()
        cond = subset[param].dropna()
        if len(cond) == 0:
            continue

        overall_median = float(overall.median()) if len(overall) > 0 else None
        cond_median = float(cond.median())
        cond_mean = float(cond.mean())
        cond_std = float(cond.std()) if len(cond) > 1 else 0.0
        cond_p05 = float(cond.quantile(0.05)) if len(cond) >= 2 else cond_median
        cond_p95 = float(cond.quantile(0.95)) if len(cond) >= 2 else cond_median

        direction, magnitude, sig = _classify_shift(overall_median, cond_median)

        out.conditional_stats.append(ConditionalParameterStat(
            parameter=param,
            n=len(cond),
            overall_median=overall_median,
            conditional_median=cond_median,
            conditional_p05=cond_p05,
            conditional_p95=cond_p95,
            conditional_mean=cond_mean,
            conditional_std=cond_std,
            shift_direction=direction,
            shift_magnitude_pct=magnitude,
            significance=sig,
        ))

    return out


# ── Public: compare_to_naive_stacking ───────────────────────────────────────

def compare_to_naive_stacking(df: pd.DataFrame,
                              governing_parameter: str,
                              governing_percentile: float,
                              coincident_parameters: List[str],
                              design_concern: str = ""
                              ) -> OverDesignComparison:
    """
    Compute the over-design comparison: naive independent-P95 of every
    coincident parameter vs the joint median of that parameter on days
    where governing_parameter >= P(governing_percentile).

    Returns OverDesignComparison with coincident_parameters mapping each
    parameter to (naive_p95, joint_median).
    """
    out = OverDesignComparison(
        governing_parameter=governing_parameter,
        governing_percentile=governing_percentile,
        governing_value=0.0,
        design_concern=design_concern,
    )

    if governing_parameter not in df.columns:
        return out
    gov_series = df[governing_parameter].dropna()
    if len(gov_series) == 0:
        return out

    threshold = float(gov_series.quantile(governing_percentile / 100.0))
    out.governing_value = threshold

    mask = (df[governing_parameter] >= threshold).fillna(False)
    if mask.sum() == 0:
        return out

    subset = df[mask]

    for param in coincident_parameters:
        if param not in df.columns or not pd.api.types.is_numeric_dtype(df[param]):
            continue
        full_values = df[param].dropna()
        sub_values = subset[param].dropna()
        if len(full_values) < 2 or len(sub_values) == 0:
            continue

        naive_p95 = float(full_values.quantile(0.95))
        joint_median = float(sub_values.median())
        out.coincident_parameters[param] = (naive_p95, joint_median)

    return out
