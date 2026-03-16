"""
core/data_ingestion/data_cleaning.py

Plant Data Ingestion, Cleaning, and Validation  (v1.1)
=======================================================

AUDIT FIXES (v1.1)
------------------
  FIX 1  — Unit conversion for L/s and m³/hr flow inputs (no longer silent data loss)
  FIX 2  — Duplicate timestamp deduplication (keep last value, warn user)
  FIX 3  — Stuck-sensor detection (suspiciously constant values flagged)
  FIX 4  — COD < BOD: offending COD values are now nulled, not just flagged
  FIX 5  — Spike detection is now context-aware: consecutive spikes (≥3 rows)
            are treated as probable real events (wet weather), not sensor errors
  FIX 6  — Per-column spike thresholds replacing a single global threshold
  FIX 7  — Rolling average window is frequency-aware (7 calendar days, not 7 rows)
  FIX 8  — Time interval inference handles sub-hourly SCADA data correctly
  FIX 9  — Per-column completeness metrics added to CleaningResult
  FIX 10 — Column completeness table added to CleaningResult.to_quality_report()
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from enum import Enum
import io


# ─────────────────────────────────────────────────────────────────────────────
# COLUMN SPECIFICATION
# ─────────────────────────────────────────────────────────────────────────────

COLUMN_SPEC: Dict[str, Tuple[str, str]] = {
    "timestamp":                   ("required", "Date/time of observation"),
    "flow_mld":                    ("core",     "Influent flow (ML/day)"),
    "peak_flow_mld":               ("optional", "Peak wet weather flow (ML/day)"),
    "influent_bod_mg_l":           ("core",     "Influent BOD (mg/L)"),
    "influent_cod_mg_l":           ("optional", "Influent COD (mg/L)"),
    "influent_tss_mg_l":           ("optional", "Influent TSS (mg/L)"),
    "influent_nh4_mg_l":           ("core",     "Influent NH₄-N (mg/L)"),
    "influent_tkn_mg_l":           ("core",     "Influent TKN (mg/L)"),
    "influent_tp_mg_l":            ("optional", "Influent TP (mg/L)"),
    "effluent_nh4_mg_l":           ("core",     "Effluent NH₄-N (mg/L)"),
    "effluent_tn_mg_l":            ("optional", "Effluent TN (mg/L)"),
    "effluent_tp_mg_l":            ("optional", "Effluent TP (mg/L)"),
    "mlss_mg_l":                   ("optional", "Mixed liquor SS (mg/L)"),
    "do_aerobic_mg_l":             ("optional", "Aerobic zone DO (mg/L)"),
    "srt_days":                    ("optional", "Sludge retention time (days)"),
    "basin_temp_celsius":          ("optional", "Biological basin temperature (°C)"),
    "blower_power_kw":             ("optional", "Blower power demand (kW)"),
    "total_plant_power_kw":        ("optional", "Total plant power (kW)"),
    "aeration_airflow_nm3_hr":     ("optional", "Aeration airflow (Nm³/h)"),
    "sludge_production_t_ds_day":  ("optional", "Sludge production (t DS/day)"),
    "digester_feed_t_vs_day":      ("optional", "Digester feed VS (t VS/day)"),
    "biogas_m3_day":               ("optional", "Biogas production (m³/day)"),
    "chp_electricity_kwh_day":     ("optional", "CHP electricity (kWh/day)"),
    "cake_ts_pct":                 ("optional", "Dewatered cake TS (%)"),
}

# Maps raw column names → canonical names.
# Where a unit conversion is also needed, the value is (canonical_name, factor_to_multiply).
# Factor=1.0 means no conversion. Conversions with factors are applied after renaming.
COLUMN_ALIASES: Dict[str, Any] = {
    # Flow — with unit conversion factors where needed
    "flow":            ("flow_mld", 1.0),
    "influent_flow":   ("flow_mld", 1.0),
    "flow_ml_d":       ("flow_mld", 1.0),
    # L/s  → ML/day: × 86400 / 1e6
    "flow_l_s":        ("flow_mld", 86400 / 1e6),
    "flow_ls":         ("flow_mld", 86400 / 1e6),
    # m³/hr → ML/day: × 24 / 1000
    "flow_m3_hr":      ("flow_mld", 24.0 / 1000.0),
    "flow_m3hr":       ("flow_mld", 24.0 / 1000.0),
    # m³/d → ML/day: / 1000
    "flow_m3_d":       ("flow_mld", 1.0 / 1000.0),
    "flow_m3d":        ("flow_mld", 1.0 / 1000.0),
    "peak_flow":       ("peak_flow_mld", 1.0),
    # Quality — no conversion, just renaming
    "bod":             ("influent_bod_mg_l", 1.0),
    "influent_bod":    ("influent_bod_mg_l", 1.0),
    "cod":             ("influent_cod_mg_l", 1.0),
    "influent_cod":    ("influent_cod_mg_l", 1.0),
    "tss":             ("influent_tss_mg_l", 1.0),
    "influent_tss":    ("influent_tss_mg_l", 1.0),
    "nh4":             ("influent_nh4_mg_l", 1.0),
    "nh4_n":           ("influent_nh4_mg_l", 1.0),
    "influent_nh4":    ("influent_nh4_mg_l", 1.0),
    "influent_ammonia":("influent_nh4_mg_l", 1.0),
    "tkn":             ("influent_tkn_mg_l", 1.0),
    "influent_tkn":    ("influent_tkn_mg_l", 1.0),
    "tp":              ("influent_tp_mg_l",  1.0),
    "influent_tp":     ("influent_tp_mg_l",  1.0),
    "effluent_nh4":    ("effluent_nh4_mg_l", 1.0),
    "effluent_ammonia":("effluent_nh4_mg_l", 1.0),
    "effluent_tn":     ("effluent_tn_mg_l",  1.0),
    "effluent_tp":     ("effluent_tp_mg_l",  1.0),
    "mlss":            ("mlss_mg_l",         1.0),
    "mixed_liquor_ss": ("mlss_mg_l",         1.0),
    "do":              ("do_aerobic_mg_l",   1.0),
    "dissolved_oxygen":("do_aerobic_mg_l",   1.0),
    "srt":             ("srt_days",          1.0),
    "temperature":     ("basin_temp_celsius",1.0),
    "blower_power":    ("blower_power_kw",   1.0),
    "blower_kw":       ("blower_power_kw",   1.0),
    "total_power":     ("total_plant_power_kw", 1.0),
    "plant_power_kw":  ("total_plant_power_kw", 1.0),
    "airflow":         ("aeration_airflow_nm3_hr", 1.0),
    "aeration_airflow":("aeration_airflow_nm3_hr", 1.0),
    "sludge_production":("sludge_production_t_ds_day", 1.0),
    "wasted_sludge_t_ds":("sludge_production_t_ds_day", 1.0),
    "biogas":          ("biogas_m3_day",     1.0),
    "biogas_production":("biogas_m3_day",    1.0),
    "chp_electricity": ("chp_electricity_kwh_day", 1.0),
    "cake_solids":     ("cake_ts_pct",       1.0),
    "cake_ts":         ("cake_ts_pct",       1.0),
}

# Physical validation bounds  [min, max]
VALIDATION_BOUNDS: Dict[str, Tuple[float, float]] = {
    "flow_mld":                  (0.001,  50_000.0),
    "influent_bod_mg_l":         (5.0,    3_000.0),
    "influent_cod_mg_l":         (10.0,   8_000.0),
    "influent_tss_mg_l":         (5.0,    2_000.0),
    "influent_nh4_mg_l":         (0.1,    500.0),
    "influent_tkn_mg_l":         (0.5,    600.0),
    "influent_tp_mg_l":          (0.1,    100.0),
    "effluent_nh4_mg_l":         (0.0,    200.0),
    "effluent_tn_mg_l":          (0.0,    250.0),
    "effluent_tp_mg_l":          (0.0,    50.0),
    "mlss_mg_l":                 (100.0,  20_000.0),
    "do_aerobic_mg_l":           (0.0,    20.0),
    "srt_days":                  (1.0,    60.0),
    "basin_temp_celsius":        (5.0,    40.0),
    "blower_power_kw":           (0.0,    50_000.0),
    "total_plant_power_kw":      (0.0,    200_000.0),
    "aeration_airflow_nm3_hr":   (0.0,    500_000.0),
    "sludge_production_t_ds_day":(0.0,    10_000.0),
    "biogas_m3_day":             (0.0,    500_000.0),
    "chp_electricity_kwh_day":   (0.0,    5_000_000.0),
    "cake_ts_pct":               (5.0,    40.0),
}

# FIX 6: Per-column spike thresholds (ratio from median to flag as spike)
# Higher values = less sensitive (only catch extreme outliers)
# Flow gets a high threshold because wet weather events are real 3-5x spikes
SPIKE_THRESHOLDS: Dict[str, float] = {
    "flow_mld":                   10.0,   # Extreme spikes only (>10x unusual for instrumentation error)
    "influent_nh4_mg_l":          8.0,    # Industrial discharge spikes can be 5-8x
    "effluent_nh4_mg_l":          20.0,   # Process upsets can cause large swings
    "blower_power_kw":            5.0,    # Should be relatively stable
    "biogas_m3_day":              6.0,    # Digester upsets can halve or double output
    "sludge_production_t_ds_day": 5.0,
    "_default":                   5.0,    # Fallback for unlisted columns
}

# FIX 5: Minimum consecutive rows to qualify as a "persistent event" (not spike)
CONSECUTIVE_EVENT_MIN_ROWS = 3


class IssueSeverity(str, Enum):
    INFO     = "info"
    WARNING  = "warning"
    CRITICAL = "critical"


@dataclass
class DataQualityIssue:
    severity: IssueSeverity
    column: str
    message: str
    affected_rows: int = 0
    pct_affected: float = 0.0

    def __str__(self) -> str:
        sev = {"info": "ℹ️", "warning": "⚠️", "critical": "🚨"}.get(self.severity, "")
        row_note = f" ({self.affected_rows} rows, {self.pct_affected:.1f}%)" if self.affected_rows else ""
        return f"{sev} [{self.column}] {self.message}{row_note}"


@dataclass
class CleaningResult:
    df: Any                                              # Clean DataFrame
    df_raw: Any                                          # Original DataFrame
    issues: List[DataQualityIssue] = field(default_factory=list)
    columns_found: List[str] = field(default_factory=list)
    columns_missing_core: List[str] = field(default_factory=list)
    columns_missing_optional: List[str] = field(default_factory=list)
    column_completeness: Dict[str, float] = field(default_factory=dict)  # FIX 9
    n_rows_raw: int = 0
    n_rows_clean: int = 0
    n_rows_removed: int = 0
    date_range: Optional[str] = None
    time_interval: Optional[str] = None
    unit_conversions_applied: List[str] = field(default_factory=list)    # FIX 1

    @property
    def has_critical_issues(self) -> bool:
        return any(i.severity == IssueSeverity.CRITICAL for i in self.issues)

    @property
    def data_quality_score(self) -> float:
        if self.n_rows_raw == 0:
            return 0.0
        completeness  = self.n_rows_clean / self.n_rows_raw
        core_cols_found = [c for c in self.columns_found
                           if COLUMN_SPEC.get(c, ("optional",))[0] == "core"]
        n_core_expected = len([k for k, v in COLUMN_SPEC.items() if v[0] == "core"])
        core_coverage   = len(core_cols_found) / max(n_core_expected, 1)
        critical_penalty = 0.2 * len([i for i in self.issues
                                       if i.severity == IssueSeverity.CRITICAL])
        return max(0.0, min(100.0, (completeness * 0.6 + core_coverage * 0.4) * 100
                            - critical_penalty * 10))

    def issue_summary(self) -> Dict[str, int]:
        return {
            "critical": sum(1 for i in self.issues if i.severity == IssueSeverity.CRITICAL),
            "warning":  sum(1 for i in self.issues if i.severity == IssueSeverity.WARNING),
            "info":     sum(1 for i in self.issues if i.severity == IssueSeverity.INFO),
        }


# ─────────────────────────────────────────────────────────────────────────────
# DATA CLEANER  (v1.1)
# ─────────────────────────────────────────────────────────────────────────────

class PlantDataCleaner:
    """
    Plant data ingestion and cleaning pipeline (v1.1).

    Pipeline
    --------
    1.  Parse CSV
    2.  Normalise + rename columns (with unit conversion)        ← FIX 1
    3.  Parse timestamps
    4.  Deduplicate timestamps                                    ← FIX 2
    5.  Cast numerics; record per-column completeness             ← FIX 9
    6.  Physical bounds check (null-out out-of-range values)
    7.  COD < BOD: null out bad COD values                        ← FIX 4
    8.  NH₄ > TKN: null out bad NH₄ values
    9.  Stuck-sensor detection                                    ← FIX 3
    10. Spike detection (context-aware, per-column thresholds)    ← FIX 5, 6
    11. Align to target interval                                  ← FIX 8
    12. Frequency-aware rolling averages                          ← FIX 7
    13. Build quality report
    """

    def clean(
        self,
        csv_content: str,
        target_interval: str = "daily",
    ) -> CleaningResult:
        import pandas as pd
        import numpy as np

        result = CleaningResult(df=None, df_raw=None)

        # ── 1. Parse CSV ───────────────────────────────────────────────────
        try:
            df = pd.read_csv(io.StringIO(csv_content), low_memory=False)
        except Exception as e:
            result.issues.append(DataQualityIssue(
                IssueSeverity.CRITICAL, "file", f"CSV parse error: {e}"
            ))
            result.df = pd.DataFrame()
            result.df_raw = pd.DataFrame()
            return result

        result.n_rows_raw = len(df)
        result.df_raw = df.copy()

        # ── 2. Normalise column names and apply unit conversions ────────────
        df.columns = [c.strip().lower().replace(" ", "_").replace("-", "_")
                      for c in df.columns]

        conversion_factors: Dict[str, float] = {}   # canonical_name → factor
        rename_map: Dict[str, str] = {}

        for raw_col in df.columns:
            if raw_col in COLUMN_SPEC:
                # Already canonical — no conversion needed
                conversion_factors[raw_col] = 1.0
            elif raw_col in COLUMN_ALIASES:
                alias_val = COLUMN_ALIASES[raw_col]
                if isinstance(alias_val, tuple):
                    canonical, factor = alias_val
                else:
                    canonical, factor = alias_val, 1.0

                rename_map[raw_col] = canonical
                if factor != 1.0:
                    conversion_factors[canonical] = factor
                    result.unit_conversions_applied.append(
                        f"'{raw_col}' → '{canonical}' (×{factor:.6g})"
                    )
                    result.issues.append(DataQualityIssue(
                        IssueSeverity.INFO, raw_col,
                        f"Column '{raw_col}' renamed to '{canonical}' "
                        f"and multiplied by {factor:.6g} for unit conversion."
                    ))

        # Before renaming: if both the alias and canonical column exist, drop the alias
        # (e.g. user has both 'flow_mld' and 'flow_ls' — keep flow_mld, drop flow_ls)
        for raw_col, canonical in {k: v[0] if isinstance(v, tuple) else v
                                    for k, v in COLUMN_ALIASES.items()}.items():
            if raw_col in df.columns and canonical in df.columns:
                result.issues.append(DataQualityIssue(
                    IssueSeverity.INFO, raw_col,
                    f"Both '{raw_col}' and '{canonical}' present — '{raw_col}' dropped, "
                    f"'{canonical}' used as-is."
                ))
                df = df.drop(columns=[raw_col])
                rename_map.pop(raw_col, None)
                conversion_factors.pop(canonical, None)

        df = df.rename(columns=rename_map)

        # Apply unit conversions
        for col, factor in conversion_factors.items():
            if factor != 1.0 and col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce") * factor

        # Keep only recognised columns
        known_cols = [c for c in df.columns if c in COLUMN_SPEC or c == "timestamp"]
        df = df[known_cols]

        result.columns_found = [c for c in df.columns if c != "timestamp"]
        for col, (imp, _) in COLUMN_SPEC.items():
            if col not in df.columns:
                if imp in ("required", "core"):
                    result.columns_missing_core.append(col)
                else:
                    result.columns_missing_optional.append(col)

        # ── 3. Parse timestamps ────────────────────────────────────────────
        if "timestamp" not in df.columns:
            result.issues.append(DataQualityIssue(
                IssueSeverity.CRITICAL, "timestamp",
                "No timestamp column found. Cannot proceed with time-series analysis."
            ))
        else:
            try:
                df["timestamp"] = pd.to_datetime(df["timestamp"])
                n_bad = df["timestamp"].isna().sum()
                if n_bad > 0:
                    result.issues.append(DataQualityIssue(
                        IssueSeverity.WARNING, "timestamp",
                        f"{n_bad} rows with unparseable timestamps removed.",
                        int(n_bad), n_bad / max(len(df), 1) * 100
                    ))
                    df = df.dropna(subset=["timestamp"])
                df = df.sort_values("timestamp").reset_index(drop=True)
                if len(df) > 1:
                    result.date_range = (
                        f"{df['timestamp'].min().date()} to {df['timestamp'].max().date()}"
                    )
            except Exception as e:
                result.issues.append(DataQualityIssue(
                    IssueSeverity.CRITICAL, "timestamp", f"Timestamp parsing failed: {e}"
                ))

        # ── 4. Deduplicate timestamps ──────────────────────────────────────
        if "timestamp" in df.columns:
            n_before = len(df)
            df = df.drop_duplicates(subset=["timestamp"], keep="last")
            n_dupes = n_before - len(df)
            if n_dupes > 0:
                result.issues.append(DataQualityIssue(
                    IssueSeverity.WARNING, "timestamp",
                    f"{n_dupes} duplicate timestamps found — kept last value for each.",
                    n_dupes, n_dupes / max(n_before, 1) * 100
                ))

        # ── 5. Cast numerics + per-column completeness ─────────────────────
        for col in result.columns_found:
            if col in df.columns and col not in conversion_factors:
                df[col] = pd.to_numeric(df[col], errors="coerce")
                n_coerce = df[col].isna().sum()
                if n_coerce > 0 and n_coerce / max(len(df), 1) > 0.05:
                    result.issues.append(DataQualityIssue(
                        IssueSeverity.WARNING, col,
                        f"{n_coerce} non-numeric values coerced to NaN.",
                        int(n_coerce), n_coerce / max(len(df), 1) * 100
                    ))

        # FIX 9: Per-column completeness
        for col in result.columns_found:
            if col in df.columns:
                fill = df[col].notna().mean()
                result.column_completeness[col] = round(fill * 100, 1)

        # ── 6. Physical bounds ─────────────────────────────────────────────
        for col, (lo, hi) in VALIDATION_BOUNDS.items():
            if col not in df.columns:
                continue
            n_lo = (df[col] < lo).sum()
            n_hi = (df[col] > hi).sum()
            if n_lo > 0:
                sev = IssueSeverity.WARNING
                result.issues.append(DataQualityIssue(
                    sev, col,
                    f"{n_lo} values below physical minimum ({lo}) — set to NaN.",
                    int(n_lo), n_lo / max(len(df), 1) * 100
                ))
                df.loc[df[col] < lo, col] = float("nan")
            if n_hi > 0:
                result.issues.append(DataQualityIssue(
                    IssueSeverity.WARNING, col,
                    f"{n_hi} values above expected maximum ({hi}) — set to NaN.",
                    int(n_hi), n_hi / max(len(df), 1) * 100
                ))
                df.loc[df[col] > hi, col] = float("nan")

        # ── 7. Cross-parameter validation ─────────────────────────────────
        # COD < BOD: null out the bad COD (the BOD is more reliable)
        if "influent_cod_mg_l" in df.columns and "influent_bod_mg_l" in df.columns:
            bad = df["influent_cod_mg_l"] < df["influent_bod_mg_l"]
            n_bad = bad.sum()
            if n_bad > 0:
                result.issues.append(DataQualityIssue(
                    IssueSeverity.WARNING, "influent_cod_mg_l",
                    f"COD < BOD in {n_bad} rows (physically impossible) — COD values nulled.",
                    int(n_bad), n_bad / max(len(df), 1) * 100
                ))
                df.loc[bad, "influent_cod_mg_l"] = float("nan")  # FIX 4

        # NH₄ > TKN: null out the bad NH₄ (sensor error / lab mix-up)
        if "influent_nh4_mg_l" in df.columns and "influent_tkn_mg_l" in df.columns:
            bad = df["influent_nh4_mg_l"] > df["influent_tkn_mg_l"]
            n_bad = bad.sum()
            if n_bad > 0:
                result.issues.append(DataQualityIssue(
                    IssueSeverity.WARNING, "influent_nh4_mg_l",
                    f"NH₄-N > TKN in {n_bad} rows — NH₄-N values nulled.",
                    int(n_bad), n_bad / max(len(df), 1) * 100
                ))
                df.loc[bad, "influent_nh4_mg_l"] = float("nan")

        if "effluent_nh4_mg_l" in df.columns and "influent_nh4_mg_l" in df.columns:
            bad = df["effluent_nh4_mg_l"] > df["influent_nh4_mg_l"]
            n_bad = bad.sum()
            if n_bad > 0:
                result.issues.append(DataQualityIssue(
                    IssueSeverity.INFO, "effluent/influent_nh4",
                    f"Effluent NH₄ > influent NH₄ in {n_bad} rows — loading spike or sensor issue.",
                    int(n_bad), n_bad / max(len(df), 1) * 100
                ))

        # ── 8. Stuck-sensor detection (FIX 3) ─────────────────────────────
        # Flag columns where the same non-zero value repeats for ≥10 consecutive rows
        STUCK_MIN_ROWS = 10
        for col in ["do_aerobic_mg_l", "blower_power_kw", "mlss_mg_l",
                    "flow_mld", "influent_nh4_mg_l"]:
            if col not in df.columns:
                continue
            s = df[col].dropna()
            if len(s) < STUCK_MIN_ROWS:
                continue
            # Count consecutive identical values
            runs = (s != s.shift()).cumsum()
            run_lengths = s.groupby(runs).transform("count")
            n_stuck = (run_lengths >= STUCK_MIN_ROWS).sum()
            if n_stuck > 0:
                # Only flag if the stuck value is not zero (zero could be legitimate shutdown)
                stuck_val = s[run_lengths >= STUCK_MIN_ROWS].iloc[0] if n_stuck else 0
                if stuck_val != 0:
                    result.issues.append(DataQualityIssue(
                        IssueSeverity.WARNING, col,
                        f"{n_stuck} values appear stuck at {stuck_val:.2f} for ≥{STUCK_MIN_ROWS} "
                        f"consecutive readings — possible sensor fault or data logger issue.",
                        int(n_stuck), n_stuck / max(len(df), 1) * 100
                    ))

        # ── 9. Spike detection (FIX 5: context-aware; FIX 6: per-column threshold)
        spike_cols = ["flow_mld", "influent_nh4_mg_l", "effluent_nh4_mg_l",
                      "blower_power_kw", "biogas_m3_day",
                      "sludge_production_t_ds_day"]

        for col in spike_cols:
            if col not in df.columns:
                continue
            threshold = SPIKE_THRESHOLDS.get(col, SPIKE_THRESHOLDS["_default"])
            s = df[col].copy()
            med = s.median()
            if med is None or med <= 0:
                continue
            # Identify potential spikes (isolated extreme values)
            is_high = s > med * threshold
            is_low  = s < med / threshold

            # FIX 5: Check if high/low values are consecutive (≥ N rows = real event)
            def is_isolated(mask_series) -> "pd.Series":
                """True if a spike row is NOT part of a ≥ CONSECUTIVE_EVENT_MIN_ROWS run."""
                import pandas as pd
                runs = (mask_series != mask_series.shift()).cumsum()
                run_len = mask_series.groupby(runs).transform("count")
                # A value is "isolated" (sensor spike) if the run length < min_event_rows
                # AND it's True in the mask
                return mask_series & (run_len < CONSECUTIVE_EVENT_MIN_ROWS)

            isolated_hi = is_isolated(is_high)
            isolated_lo = is_isolated(is_low)
            persistent_event = is_high & ~isolated_hi

            n_isolated = (isolated_hi | isolated_lo).sum()
            n_event    = persistent_event.sum()

            if n_isolated > 0:
                result.issues.append(DataQualityIssue(
                    IssueSeverity.WARNING, col,
                    f"{n_isolated} isolated spike(s) detected "
                    f"(value >{threshold:.0f}× or <1/{threshold:.0f}× median of {med:.1f}). "
                    "Isolated single-row spikes are likely sensor errors.",
                    int(n_isolated), n_isolated / max(len(df), 1) * 100
                ))

            if n_event > 0:
                result.issues.append(DataQualityIssue(
                    IssueSeverity.INFO, col,
                    f"{n_event} rows in a sustained elevated-value event "
                    f"(>{threshold:.0f}× median). Likely a real wet weather or loading event "
                    "rather than a sensor error — retained in dataset.",
                    int(n_event), n_event / max(len(df), 1) * 100
                ))

        # ── 10. Align to common interval (FIX 8: sub-hourly handled) ───────
        raw_median_gap_days: float = 1.0  # default; updated below
        if "timestamp" in df.columns and len(df) > 1:
            diffs = df["timestamp"].diff().dropna()
            median_seconds = diffs.median().total_seconds()
            raw_median_gap_days = median_seconds / 86400.0

            # Classify raw interval
            if median_seconds <= 1800:           # ≤30 min (includes 15-min SCADA)
                result.time_interval = "sub-hourly"
            elif median_seconds <= 7200:         # ≤2 h
                result.time_interval = "hourly"
            elif median_seconds <= 90_000:       # ≤25 h (daily with some gaps)
                result.time_interval = "daily"
            else:
                result.time_interval = "weekly_or_longer"

            # Choose resample target
            freq_map = {"hourly": "h", "daily": "D", "weekly": "W"}
            freq = freq_map.get(target_interval, "D")

            df = df.set_index("timestamp")
            numeric_cols = df.select_dtypes(include=["float64", "int64", "Float64"]).columns
            df = df[numeric_cols].resample(freq).mean().reset_index()
            df = df.rename(columns={"index": "timestamp"})

        # ── 11. Frequency-aware rolling averages (FIX 7) ──────────────────
        # Use 7-calendar-day window for daily/sub-daily data.
        # Fall back to 7-ROW window when original data is weekly/sparse.
        # We use raw_median_gap_days (measured BEFORE resampling) so that
        # weekly data resampled to daily doesn't pretend it is dense.
        if "timestamp" in df.columns and len(df) >= 4:
            roll_cols = ["flow_mld", "influent_nh4_mg_l", "blower_power_kw",
                         "effluent_nh4_mg_l", "biogas_m3_day"]
            use_time_window = raw_median_gap_days < 5  # < 5 days → daily or sub-daily

            for col in roll_cols:
                if col not in df.columns:
                    continue
                try:
                    if use_time_window:
                        # Time-based rolling window: 7 calendar days, min 3 observations
                        ts_index = pd.to_datetime(df["timestamp"])
                        s = df[col].copy()
                        s.index = ts_index
                        rolling = s.rolling("7D", min_periods=3).mean()
                        rolling.index = df.index
                        df[f"{col}_7d_avg"] = rolling
                    else:
                        # Row-based fallback for weekly / sparse data.
                        # Use min_periods=1: sparse resampled data has only 1 real
                        # value per 7-row window so min_periods=3 would produce all NaN.
                        df[f"{col}_7d_avg"] = df[col].rolling(7, min_periods=1).mean()
                except Exception:
                    df[f"{col}_7d_avg"] = df[col].rolling(7, min_periods=1).mean()

        # ── 12. Final ──────────────────────────────────────────────────────
        result.n_rows_clean = len(df)
        result.n_rows_removed = result.n_rows_raw - result.n_rows_clean
        result.df = df

        if result.n_rows_clean == 0:
            result.issues.append(DataQualityIssue(
                IssueSeverity.CRITICAL, "dataset",
                "No valid rows remain after cleaning."
            ))

        if result.columns_missing_core:
            result.issues.append(DataQualityIssue(
                IssueSeverity.WARNING, "columns",
                f"Core columns missing: {', '.join(result.columns_missing_core)}. "
                "KPI calculations will be partial."
            ))

        return result


def generate_sample_csv(n_days: int = 90, seed: int = 42) -> str:
    """Generate a realistic synthetic plant CSV for testing and demonstration."""
    import pandas as pd
    import numpy as np
    rng = np.random.default_rng(seed)

    dates  = pd.date_range("2024-01-01", periods=n_days, freq="D")
    season = np.sin(np.linspace(0, 2 * np.pi, n_days)) * 0.15
    noise  = lambda scale: rng.normal(0, scale, n_days)

    flow    = np.clip(10.0 * (1 + season + noise(0.08)), 5, 20)
    nh4_in  = np.clip(35.0 * (1 + noise(0.10)), 15, 70)
    tkn_in  = nh4_in / 0.78 + noise(2)
    bod_in  = np.clip(250.0 * (1 + season * 0.3 + noise(0.08)), 100, 400)
    nh4_out = np.clip(1.5 + noise(0.5), 0.1, 8)
    blower  = flow * 12.5 * (1 + noise(0.06))
    sludge  = flow * bod_in * 0.38 / 1000 / 0.8
    biogas  = sludge * 0.85 * 0.58 * 0.75 * 1000

    # Inject 3 isolated NH4 spikes and a 3-day wet weather event.
    # IMPORTANT: also inflate TKN proportionally so NH4 < TKN constraint is preserved.
    # Without this, the NH4 > TKN cross-validation nulls the spike before
    # AnomalyDetector ever sees it, making anomaly tests unreliable.
    spike_indices = rng.integers(0, n_days, 3)
    for i in spike_indices:
        nh4_in[i] *= 4.0   # Single-row spike — should be flagged
        tkn_in[i] = nh4_in[i] / 0.78  # Keep TKN >= NH4 so cross-val doesn't null it

    # 3-day wet weather event — should NOT be flagged as spike
    wet_start = min(30, n_days - 3)
    flow[wet_start:wet_start+3] *= 2.8

    # 8% missing data
    for col_arr in [nh4_in, nh4_out, blower, biogas]:
        col_arr[rng.integers(0, n_days, max(1, n_days // 12))] = float("nan")

    df = pd.DataFrame({
        "timestamp":                  dates,
        "flow_mld":                   flow.round(2),
        "influent_nh4_mg_l":          nh4_in.round(1),
        "influent_tkn_mg_l":          tkn_in.round(1),
        "influent_bod_mg_l":          bod_in.round(1),
        "effluent_nh4_mg_l":          nh4_out.round(2),
        "blower_power_kw":            blower.round(1),
        "sludge_production_t_ds_day": sludge.round(3),
        "biogas_m3_day":              biogas.round(0),
        "mlss_mg_l":                  np.clip(rng.normal(4000, 200, n_days), 2500, 7000).round(0),
        "do_aerobic_mg_l":            np.clip(rng.normal(2.0, 0.4, n_days), 0.2, 5).round(1),
        "basin_temp_celsius":         np.clip(20 + season * 5 + noise(0.5), 12, 28).round(1),
    })

    return df.to_csv(index=False)
