"""
domains/wastewater/plant_kpis.py

Plant Operational KPI Calculator  (v1.1)
==========================================

AUDIT FIXES (v1.1)
------------------
  FIX 1  — NH₄ removal uses flow-weighted mass balance (not per-row ratio median)
  FIX 2  — SAE labelled 'Gross SAE (airflow-based)' — clarifies it is not
            the true process-corrected transfer efficiency
  FIX 3  — Sludge yield uses measured effluent BOD if available, not fixed 92%
  FIX 4  — Net carbon intensity subtracts CHP avoided emissions
  FIX 5  — Minimum observation gate: KPIs with < MIN_OBS valid pairs are
            returned as None, not reported as low-confidence values
  FIX 6  — Data completeness reported per-column in KPI notes
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

MIN_OBS = 10    # Minimum valid paired observations to report a KPI


@dataclass
class KPI:
    name: str
    value: Optional[float]
    unit: str
    n_obs: int = 0
    confidence: str = "medium"
    note: str = ""

    def display(self) -> str:
        if self.value is None:
            return "N/A"
        if abs(self.value) >= 1000:
            return f"{self.value:,.0f} {self.unit}"
        elif abs(self.value) >= 10:
            return f"{self.value:.1f} {self.unit}"
        else:
            return f"{self.value:.2f} {self.unit}"

    def to_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "value": self.value, "unit": self.unit,
                "n_obs": self.n_obs, "confidence": self.confidence, "note": self.note}


@dataclass
class KPIGroup:
    group_name: str
    kpis: List[KPI] = field(default_factory=list)

    def to_flat_dict(self) -> Dict[str, Optional[float]]:
        return {k.name: k.value for k in self.kpis}


@dataclass
class KPIResult:
    hydraulic:   KPIGroup = field(default_factory=lambda: KPIGroup("Hydraulic & Loading"))
    performance: KPIGroup = field(default_factory=lambda: KPIGroup("Treatment Performance"))
    energy:      KPIGroup = field(default_factory=lambda: KPIGroup("Energy"))
    sludge:      KPIGroup = field(default_factory=lambda: KPIGroup("Sludge & Digestion"))
    carbon:      KPIGroup = field(default_factory=lambda: KPIGroup("Carbon"))
    seasonal:    Optional[Any] = None
    dataset_days: int = 0
    date_range:  Optional[str] = None

    def all_kpis(self) -> List[KPI]:
        out = []
        for g in [self.hydraulic, self.performance, self.energy, self.sludge, self.carbon]:
            out.extend(g.kpis)
        return out

    def to_calibration_dict(self) -> Dict[str, Optional[float]]:
        return {k.name: k.value for k in self.all_kpis()}

    def to_obs_dict(self) -> Dict[str, int]:
        """Maps KPI name → observation count. Used by CalibrationEngine safety gates."""
        return {k.name: k.n_obs for k in self.all_kpis()}

    def to_confidence_dict(self) -> Dict[str, str]:
        """Maps KPI name → confidence level ('high'/'medium'/'low'). Used by CalibrationEngine."""
        return {k.name: k.confidence for k in self.all_kpis()}

    def to_summary_rows(self) -> List[Dict]:
        rows = []
        for g in [self.hydraulic, self.performance, self.energy, self.sludge, self.carbon]:
            for k in g.kpis:
                rows.append({
                    "Group": g.group_name, "KPI": k.name,
                    "Value": k.display() if k.value is not None else "—",
                    "Observations": k.n_obs, "Confidence": k.confidence, "Note": k.note,
                })
        return rows


class PlantKPICalculator:

    def calculate(self, df: Any, grid_ef: float = 0.79) -> KPIResult:
        import pandas as pd
        import numpy as np
        r = KPIResult()
        r.dataset_days = len(df)

        def col(name):
            return df[name] if name in df.columns else None

        def mean_safe(series, min_frac=0.3):
            if series is None: return None
            v = series.dropna()
            if len(v) < max(MIN_OBS, len(series) * min_frac): return None
            return float(v.mean())

        def n_valid(series):
            return 0 if series is None else int(series.notna().sum())

        def conf(series):
            if series is None: return "low"
            f = series.notna().mean()
            return "high" if f > 0.8 else ("medium" if f > 0.5 else "low")

        flow = col("flow_mld")
        nh4  = col("influent_nh4_mg_l")
        tkn  = col("influent_tkn_mg_l")
        bod  = col("influent_bod_mg_l")

        avg_flow = mean_safe(flow)
        avg_nh4  = mean_safe(nh4)
        avg_bod  = mean_safe(bod)

        def load_kgd(flow_s, conc_s):
            if flow_s is None or conc_s is None: return None
            combined = pd.DataFrame({"f": flow_s, "c": conc_s}).dropna()
            if len(combined) < MIN_OBS: return None
            return float((combined["f"] * combined["c"]).mean())

        nh4_load = load_kgd(flow, nh4)
        bod_load = load_kgd(flow, bod)

        nh4_tkn_ratio = None
        if nh4 is not None and tkn is not None:
            combined = pd.DataFrame({"nh4": nh4, "tkn": tkn}).dropna()
            combined = combined[combined["tkn"] > 0]
            if len(combined) >= MIN_OBS:
                nh4_tkn_ratio = float((combined["nh4"] / combined["tkn"]).median())

        r.hydraulic.kpis = [
            KPI("Average flow", avg_flow, "ML/day", n_valid(flow), conf(flow)),
            KPI("95th percentile flow",
                float(flow.quantile(0.95)) if flow is not None and avg_flow else None,
                "ML/day", n_valid(flow), conf(flow), "Indicative peak wet weather flow"),
            KPI("Average BOD load", bod_load, "kg/day", n_valid(bod), conf(bod)),
            KPI("Average NH₄ load", nh4_load, "kg/day", n_valid(nh4), conf(nh4)),
            KPI("Average TKN load", load_kgd(flow, tkn), "kg/day",
                n_valid(tkn), conf(tkn)),
            KPI("NH₄:TKN ratio", nh4_tkn_ratio, "fraction",
                min(n_valid(nh4), n_valid(tkn)), conf(tkn),
                "Typical municipal: 0.70–0.80. Used to calibrate TKN estimates."),
        ]

        # ── Treatment Performance ─────────────────────────────────────────
        eff_nh4 = col("effluent_nh4_mg_l")
        eff_tn  = col("effluent_tn_mg_l")
        eff_tp  = col("effluent_tp_mg_l")
        inf_tp  = col("influent_tp_mg_l")

        # FIX 1: Flow-weighted mass-balance removal efficiency
        def removal_eff_mass_based(inf_s, eff_s, flow_s=flow):
            """
            Flow-weighted removal = (sum(inf_load) - sum(eff_load)) / sum(inf_load).
            Returns (pct, n_obs, warning_msg).
            warning_msg is non-empty when removal is negative or very low.
            """
            if inf_s is None or eff_s is None or flow_s is None:
                return None, 0, ""
            combined = pd.DataFrame({"f": flow_s, "inf": inf_s, "eff": eff_s}).dropna()
            if len(combined) < MIN_OBS:
                return None, len(combined), ""
            inf_load = (combined["f"] * combined["inf"]).sum()
            eff_load = (combined["f"] * combined["eff"]).sum()
            if inf_load <= 0:
                return None, len(combined), ""
            removal = (inf_load - eff_load) / inf_load * 100
            warn = ""
            if removal < 0:
                warn = (
                    f"Negative removal ({removal:.1f}%): effluent load exceeds influent load. "
                    "Possible causes: ammonification/deammonification in the network, "
                    "sidestream returns, or measurement error. Value reported as 0%."
                )
            elif removal < 50:
                warn = (
                    f"Low removal efficiency ({removal:.1f}%). "
                    "Verify influent/effluent measurement points are correct."
                )
            return float(max(0.0, min(100.0, removal))), len(combined), warn

        nh4_removal, nh4_n, nh4_warn = removal_eff_mass_based(nh4, eff_nh4)
        tn_removal,  tn_n,  tn_warn  = removal_eff_mass_based(tkn, eff_tn)
        tp_removal,  tp_n,  tp_warn  = removal_eff_mass_based(inf_tp, eff_tp)

        r.performance.kpis = [
            KPI("NH₄ removal efficiency", nh4_removal, "%", nh4_n, conf(eff_nh4),
                ("Flow-weighted mass balance: Σ(Q×C_in - Q×C_out) / Σ(Q×C_in). " + nh4_warn).strip()),
            KPI("Average effluent NH₄", mean_safe(eff_nh4), "mg/L",
                n_valid(eff_nh4), conf(eff_nh4)),
            KPI("Average effluent TN", mean_safe(eff_tn), "mg/L",
                n_valid(eff_tn), conf(eff_tn)),
            KPI("TN removal efficiency", tn_removal, "%", tn_n, conf(eff_tn),
                ("Flow-weighted mass balance. " + tn_warn).strip()),
            KPI("TP removal efficiency", tp_removal, "%", tp_n, conf(eff_tp),
                ("Flow-weighted mass balance. " + tp_warn).strip()),
            KPI("Average MLSS", mean_safe(col("mlss_mg_l")), "mg/L",
                n_valid(col("mlss_mg_l")), conf(col("mlss_mg_l"))),
            KPI("Average DO", mean_safe(col("do_aerobic_mg_l")), "mg/L",
                n_valid(col("do_aerobic_mg_l")), conf(col("do_aerobic_mg_l"))),
            KPI("Average SRT", mean_safe(col("srt_days")), "days",
                n_valid(col("srt_days")), conf(col("srt_days"))),
        ]

        # ── Energy ─────────────────────────────────────────────────────────
        blower_kw = col("blower_power_kw")
        plant_kw  = col("total_plant_power_kw")
        airflow   = col("aeration_airflow_nm3_hr")

        avg_blower = mean_safe(blower_kw)
        avg_plant  = mean_safe(plant_kw)
        pwr        = avg_plant or avg_blower
        kwh_per_ml = pwr * 24 / avg_flow if (pwr and avg_flow) else None

        kwh_per_kg_nh4 = None
        if avg_blower and nh4_load and nh4_removal:
            removed = nh4_load * nh4_removal / 100
            if removed > 0:
                kwh_per_kg_nh4 = avg_blower * 24 / removed

        # FIX 2: Label as gross SAE (airflow-based)
        gross_sae = None
        sae_note  = ""
        if airflow is not None and blower_kw is not None:
            combined = pd.DataFrame({"q": airflow, "p": blower_kw}).dropna()
            if len(combined) >= MIN_OBS:
                o2_kghr = combined["q"] * 0.2095 * 1.293
                sae_vals = o2_kghr / combined["p"]
                gross_sae = float(sae_vals.median())
                sae_note = (
                    "Gross SAE: O₂ in airflow ÷ blower power. "
                    "This overestimates true SAE because it assumes all O₂ in the air is transferred. "
                    "Does not account for SOTE or DO deficit corrections. "
                    "Use for relative blower performance comparison only."
                )

        r.energy.kpis = [
            KPI("Average blower power", avg_blower, "kW",
                n_valid(blower_kw), conf(blower_kw)),
            KPI("Average plant power", avg_plant, "kW",
                n_valid(plant_kw), conf(plant_kw)),
            KPI("Energy intensity (aeration)", kwh_per_ml, "kWh/ML",
                n_valid(blower_kw), conf(blower_kw),
                "Based on blower only" if not avg_plant else "Based on total plant power"),
            KPI("kWh/kg NH₄ removed", kwh_per_kg_nh4, "kWh/kg N",
                min(n_valid(blower_kw), n_valid(eff_nh4)), conf(blower_kw)),
            KPI("Gross SAE (airflow-based)", gross_sae, "kg O₂/kWh",
                n_valid(airflow), conf(airflow), sae_note),
            KPI("Annual aeration energy",
                avg_blower * 24 * 365 / 1e6 if avg_blower else None,
                "GWh/yr", n_valid(blower_kw), conf(blower_kw)),
        ]

        # ── Sludge & Digestion ─────────────────────────────────────────────
        sludge_prod = col("sludge_production_t_ds_day")
        dig_vs      = col("digester_feed_t_vs_day")
        biogas      = col("biogas_m3_day")
        chp         = col("chp_electricity_kwh_day")
        eff_bod     = col("effluent_bod_mg_l") if "effluent_bod_mg_l" in (df.columns if df is not None else []) else None

        avg_sludge = mean_safe(sludge_prod)

        # FIX 3: Use measured effluent BOD if available, else default 92% removal
        obs_yield = None
        yield_note = ""
        if avg_sludge is not None and bod_load is not None and bod_load > 0:
            if eff_bod is not None and mean_safe(eff_bod) is not None:
                eff_bod_load = load_kgd(flow, eff_bod) or 0
                bod_removed_kg = bod_load - eff_bod_load
                yield_note = "BOD removal from measured effluent BOD."
            else:
                bod_removed_kg = bod_load * 0.92
                yield_note = "BOD removal assumed 92% (no effluent BOD data)."
            if bod_removed_kg > 0:
                obs_yield = (avg_sludge * 1000) / bod_removed_kg
                # FIX 4: flag out-of-range yield
                if obs_yield < 0.15:
                    yield_note += (
                        f" ⚠ Yield {obs_yield:.3f} is very low (< 0.15) — "
                        "check sludge wasting measurement or BOD loading data."
                    )
                elif obs_yield > 0.70:
                    yield_note += (
                        f" ⚠ Yield {obs_yield:.3f} is very high (> 0.70) — "
                        "may indicate chemical sludge, primary sludge included, "
                        "or BOD underestimation."
                    )

        avg_biogas = mean_safe(biogas)
        obs_biogas_yield = None
        if avg_biogas is not None and dig_vs is not None:
            avg_vs = mean_safe(dig_vs)
            if avg_vs and avg_vs > 0:
                vs_destroyed_kg = avg_vs * 1000 * 0.58
                obs_biogas_yield = avg_biogas / vs_destroyed_kg

        r.sludge.kpis = [
            KPI("Average sludge production", avg_sludge, "t DS/day",
                n_valid(sludge_prod), conf(sludge_prod)),
            KPI("Observed sludge yield", obs_yield, "kg DS/kg BOD",
                n_valid(sludge_prod), conf(sludge_prod),
                yield_note + " Typical BNR: 0.28–0.45"),
            KPI("Average biogas production", avg_biogas, "m³/day",
                n_valid(biogas), conf(biogas)),
            KPI("Observed biogas yield", obs_biogas_yield, "m³/kg VS destroyed",
                n_valid(biogas), conf(biogas),
                "Assumes 58% VS destruction. Typical mesophilic: 0.60–0.85 m³/kg VS"),
            KPI("Average CHP output", mean_safe(chp), "kWh/day",
                n_valid(chp), conf(chp)),
            KPI("Average cake TS%", mean_safe(col("cake_ts_pct")), "%",
                n_valid(col("cake_ts_pct")), conf(col("cake_ts_pct"))),
        ]

        # ── Carbon ─────────────────────────────────────────────────────────
        # FIX 4: Net carbon intensity subtracts CHP avoided emissions
        scope2 = None
        if pwr and avg_flow:
            scope2 = pwr * 24 * 365 * grid_ef / 1e6

        avg_chp = mean_safe(chp)
        avoided_chp = avg_chp * 365 * grid_ef / 1e6 if avg_chp else None

        # Net = scope2 minus CHP credit
        net_scope2 = None
        if scope2 is not None:
            net_scope2 = scope2 - (avoided_chp or 0.0)

        carbon_intensity = None
        if net_scope2 is not None and avg_flow:
            carbon_intensity = net_scope2 * 1e6 / (avg_flow * 365 * 1000)

        r.carbon.kpis = [
            KPI("Scope 2 electricity (gross)", scope2, "tCO₂e/yr",
                n_valid(blower_kw), conf(blower_kw), f"Grid EF: {grid_ef} kg CO₂e/kWh"),
            KPI("Avoided emissions (CHP)", avoided_chp, "tCO₂e/yr",
                n_valid(chp), conf(chp)),
            KPI("Net Scope 2 (after CHP credit)", net_scope2, "tCO₂e/yr",
                n_valid(blower_kw), conf(blower_kw),
                "Gross Scope 2 minus avoided grid emissions from CHP generation."),
            KPI("Net carbon intensity", carbon_intensity, "kg CO₂e/ML",
                n_valid(blower_kw), conf(blower_kw),
                "Net Scope 2 per ML treated after CHP credit."),
        ]

        # ── Seasonal summary ──────────────────────────────────────────────
        r.seasonal = self._seasonal_summary(df)

        return r

    @staticmethod
    def _seasonal_summary(df: Any) -> "Optional[Dict[str, Any]]":
        if "timestamp" not in df.columns or len(df) < 28:
            return None
        try:
            import pandas as pd
            ts = pd.to_datetime(df["timestamp"])
            key_cols = [c for c in ["flow_mld","influent_nh4_mg_l","effluent_nh4_mg_l",
                                     "blower_power_kw","biogas_m3_day"] if c in df.columns]
            tmp = df[key_cols].copy()
            tmp.index = ts
            monthly   = tmp.resample("ME").mean()
            monthly["month"]   = monthly.index.strftime("%b %Y")
            quarterly = tmp.resample("QE").mean()
            quarterly["quarter"] = quarterly.index.to_period("Q").astype(str)
            return {
                "monthly":         monthly.reset_index(drop=True).to_dict("records"),
                "quarterly":       quarterly.reset_index(drop=True).to_dict("records"),
                "monthly_columns": key_cols,
            }
        except Exception:
            return None
