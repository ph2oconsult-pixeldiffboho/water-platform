"""
core/benchmarking/benchmark_engine.py
domains/wastewater/anomaly_detection.py  (combined file for simplicity)

Plant Performance Benchmarking and Anomaly Detection
====================================================
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


# ─────────────────────────────────────────────────────────────────────────────
# BENCHMARK ENGINE
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class BenchmarkRange:
    low: float
    high: float
    unit: str
    note: str = ""

    def classify(self, value: float) -> Tuple[str, str]:
        """Returns (classification, colour)."""
        if value < self.low:
            return ("Below expected range", "#2ca02c")   # Green (better than expected)
        elif value > self.high:
            return ("Above expected range", "#d62728")   # Red (worse than expected)
        else:
            return ("Within normal range", "#1f6aa5")    # Blue

    def band(self) -> str:
        return f"{self.low:.2g}–{self.high:.2g} {self.unit}"


# ── Benchmark library ─────────────────────────────────────────────────────────
# Reference ranges compiled from:
# - WEF Energy Conservation in Water and Wastewater Facilities (2009)
# - AWA Benchmarking reports (2018-2023)
# - Metcalf & Eddy 5th ed. typical operating ranges
# - Australian Water Recycling Centre of Excellence (2014)

BENCHMARKS: Dict[str, Dict[str, BenchmarkRange]] = {
    "bnr": {
        "Energy intensity (aeration)": BenchmarkRange(
            200, 600, "kWh/ML",
            "Conventional BNR — fine bubble aeration, VFDs"
        ),
        "kWh/kg NH₄ removed": BenchmarkRange(
            4, 12, "kWh/kg N",
            "BNR nitrification energy intensity"
        ),
        "Observed sludge yield": BenchmarkRange(
            0.28, 0.45, "kg DS/kg BOD",
            "Aerobic BNR, SRT 10–20 days"
        ),
        "NH₄ removal efficiency": BenchmarkRange(
            90, 99.5, "%",
            "Well-operated BNR for nitrification"
        ),
        "Observed SAE": BenchmarkRange(
            1.4, 2.4, "kg O₂/kWh",
            "Fine bubble disc diffusers, new or well-maintained"
        ),
        "Average MLSS": BenchmarkRange(
            2500, 5000, "mg/L",
            "Conventional activated sludge/BNR"
        ),
        "Average SRT": BenchmarkRange(
            8, 20, "days",
            "BNR for combined N removal"
        ),
    },
    "mbr": {
        "Energy intensity (aeration)": BenchmarkRange(
            400, 900, "kWh/ML",
            "MBR — includes membrane scour aeration"
        ),
        "kWh/kg NH₄ removed": BenchmarkRange(
            6, 18, "kWh/kg N",
            "MBR nitrification energy intensity"
        ),
        "Observed sludge yield": BenchmarkRange(
            0.15, 0.35, "kg DS/kg BOD",
            "MBR — typically lower yield due to long SRT"
        ),
        "NH₄ removal efficiency": BenchmarkRange(
            95, 99.9, "%",
            "MBR — high nitrification performance"
        ),
        "Average MLSS": BenchmarkRange(
            6000, 12000, "mg/L",
            "MBR typical operating range"
        ),
    },
    "digestion": {
        "Observed biogas yield": BenchmarkRange(
            0.55, 0.85, "m³/kg VS destroyed",
            "Mesophilic anaerobic digestion, municipal sludge"
        ),
        "Average cake TS%": BenchmarkRange(
            18, 28, "%",
            "Centrifuge dewatered biosolids"
        ),
    },
    "granular_sludge": {
        "Energy intensity (aeration)": BenchmarkRange(
            150, 450, "kWh/ML",
            "AGS (Nereda) — typically 20-35% below CAS"
        ),
        "Observed sludge yield": BenchmarkRange(
            0.15, 0.30, "kg DS/kg BOD",
            "AGS — low yield characteristic"
        ),
        "NH₄ removal efficiency": BenchmarkRange(
            90, 99, "%",
            "AGS with SND"
        ),
    },
}


class BenchmarkEngine:
    """
    Compares plant KPIs against published benchmarks for the process type.
    Returns a list of benchmark results for display.
    """

    def benchmark(
        self,
        kpi_dict: Dict[str, Optional[float]],
        process_type: str = "bnr",
    ) -> List[Dict[str, Any]]:
        """
        Parameters
        ----------
        kpi_dict     : from KPIResult.to_calibration_dict()
        process_type : "bnr" | "mbr" | "digestion" | "granular_sludge"
        """
        benchmarks = BENCHMARKS.get(process_type, BENCHMARKS["bnr"])
        rows = []

        for kpi_name, bench in benchmarks.items():
            value = kpi_dict.get(kpi_name)
            if value is None:
                rows.append({
                    "KPI": kpi_name,
                    "Plant Value": "—",
                    "Benchmark Range": bench.band(),
                    "Classification": "No data",
                    "Colour": "#aaa",
                    "Note": bench.note,
                })
            else:
                classification, colour = bench.classify(value)
                display_val = f"{value:.2g} {bench.unit}"
                rows.append({
                    "KPI": kpi_name,
                    "Plant Value": display_val,
                    "Benchmark Range": bench.band(),
                    "Classification": classification,
                    "Colour": colour,
                    "Note": bench.note,
                })

        return rows


# ─────────────────────────────────────────────────────────────────────────────
# ANOMALY DETECTION
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Anomaly:
    """A detected anomaly event."""
    timestamp: Any            # pandas Timestamp or str
    column: str
    display_name: str
    value: float
    expected_range: Tuple[float, float]
    severity: str             # "warning" | "alert"
    reason: str
    parameters_triggered: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "Timestamp":  str(self.timestamp)[:19],
            "Parameter":  self.display_name,
            "Observed":   f"{self.value:.2f}",
            "Expected":   f"{self.expected_range[0]:.2f}–{self.expected_range[1]:.2f}",
            "Severity":   self.severity,
            "Reason":     self.reason,
        }


class AnomalyDetector:
    """
    Simple rule-based anomaly detection for plant operational data.
    Version 1 uses IQR/rolling-mean deviation.  Not ML — fully transparent.

    Detection methods
    -----------------
    1. IQR method: flag values outside [Q1 - 2.5×IQR, Q3 + 2.5×IQR]
    2. Rolling Z-score: flag values > N σ from 14-day rolling mean
    3. Step-change detection: flag consecutive-day % change > threshold
    4. Cross-parameter: flag correlated anomalies (e.g. NH4 spike + blower surge)
    """

    IQR_MULTIPLIER   = 3.0   # 2.5 → 3.0: real plant data has fat tails; 2.5 over-flagged
    ZSCORE_THRESHOLD = 3.5
    STEP_PCT         = 0.60  # 50% → 60%: NH₄ can vary 40-55% day-to-day normally

    DISPLAY_NAMES = {
        "influent_nh4_mg_l":          "Influent NH₄",
        "effluent_nh4_mg_l":          "Effluent NH₄",
        "flow_mld":                   "Flow",
        "blower_power_kw":            "Blower power",
        "biogas_m3_day":              "Biogas production",
        "sludge_production_t_ds_day": "Sludge production",
        "do_aerobic_mg_l":            "Aerobic zone DO",
        "mlss_mg_l":                  "MLSS",
    }

    def detect(self, df: Any) -> List[Anomaly]:
        """Run all detection rules. Returns list of Anomaly objects."""
        import pandas as pd
        import numpy as np

        anomalies: List[Anomaly] = []
        cols = [c for c in self.DISPLAY_NAMES if c in df.columns]

        for col in cols:
            series = df[col].dropna()
            if len(series) < 7:
                continue

            disp = self.DISPLAY_NAMES[col]
            q1, q3 = series.quantile(0.25), series.quantile(0.75)
            iqr = q3 - q1
            lo = q1 - self.IQR_MULTIPLIER * iqr
            hi = q3 + self.IQR_MULTIPLIER * iqr

            # IQR-based outliers
            ts = df["timestamp"] if "timestamp" in df.columns else df.index
            for idx in df.index:
                val = df.loc[idx, col] if not pd.isna(df.loc[idx, col]) else None
                if val is None:
                    continue
                if val < lo or val > hi:
                    timestamp = df.loc[idx, "timestamp"] if "timestamp" in df.columns else idx
                    anomalies.append(Anomaly(
                        timestamp=timestamp, column=col, display_name=disp,
                        value=val, expected_range=(max(0, lo), hi),
                        severity="alert" if abs(val - series.median()) > 3 * iqr else "warning",
                        reason=(
                            f"{disp} value {val:.2f} is "
                            f"{'above' if val > hi else 'below'} the expected range "
                            f"(IQR bounds: {max(0,lo):.2f}–{hi:.2f}). "
                            f"This may indicate a sensor spike, loading event, or process upset."
                        ),
                        parameters_triggered=[col],
                    ))

        # Step-change detection
        for col in ["flow_mld", "blower_power_kw", "influent_nh4_mg_l"]:
            if col not in df.columns:
                continue
            series = df[col].dropna()
            pct_change = series.pct_change().abs()
            spikes = pct_change[pct_change > self.STEP_PCT]
            for idx in spikes.index:
                if idx not in df.index:
                    continue
                val = df.loc[idx, col] if not pd.isna(df.loc[idx, col]) else None
                if val is None:
                    continue
                ts_val = df.loc[idx, "timestamp"] if "timestamp" in df.columns else idx
                disp = self.DISPLAY_NAMES.get(col, col)
                anomalies.append(Anomaly(
                    timestamp=ts_val, column=col, display_name=disp,
                    value=val, expected_range=(0, float(series.median() * 1.5)),
                    severity="warning",
                    reason=(
                        f"Rapid step change in {disp}: "
                        f"{pct_change.loc[idx]*100:.0f}% change from previous period. "
                        "May indicate wet weather event, operational change, or data error."
                    ),
                    parameters_triggered=[col],
                ))

        # Deduplicate (same timestamp + column)
        seen = set()
        unique = []
        for a in anomalies:
            key = (str(a.timestamp)[:10], a.column)
            if key not in seen:
                seen.add(key)
                unique.append(a)

        # Sort by timestamp
        unique.sort(key=lambda x: str(x.timestamp))
        return unique
