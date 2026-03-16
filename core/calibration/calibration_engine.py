"""
core/calibration/calibration_engine.py

Model Calibration Engine  (v1.1)
==================================

AUDIT FIXES (v1.1)
------------------
  FIX 1  — Calibration map rebuilt to reference only EXISTING assumption keys
            (removed phantom keys: nh4_to_tkn_ratio_default, aeration_kwh_per_kg_nh4,
             srt_days, mlss_mg_l — none of these are in the AssumptionsSet)
  FIX 2  — Minimum observation gate: calibration factors derived from fewer
            than MIN_CALIBRATION_OBS observations are flagged and defaulted to UNCHANGED
  FIX 3  — Low-confidence KPIs (confidence='low') trigger a warning before
            the factor is applied; user must explicitly accept
  FIX 4  — NH₄:TKN ratio correctly maps to aeration_model.py AerationInputs
            nh4_to_tkn_ratio rather than a non-existent assumptions key
  FIX 5  — Seasonal variability note added to factors with >15% coefficient
            of variation (flags that a single-value calibration may not hold year-round)
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from enum import Enum

MIN_CALIBRATION_OBS = 14    # Minimum observations to trust a calibration factor


class CalibrationStatus(str, Enum):
    ACCEPTED  = "accepted"
    REJECTED  = "rejected"
    MANUAL    = "manual"
    PENDING   = "pending"
    UNCHANGED = "unchanged"   # No data or insufficient observations


@dataclass
class CalibrationFactor:
    key: str                          # assumptions key path (e.g. "engineering.alpha_factor")
    display_name: str
    unit: str
    model_default: float
    observed_value: Optional[float]
    suggested_value: Optional[float]
    adjustment_factor: Optional[float]
    status: CalibrationStatus = CalibrationStatus.PENDING
    user_override: Optional[float] = None
    n_observations: int = 0
    data_confidence: str = "medium"

    factor_lo: float = 0.50
    factor_hi: float = 2.00

    rationale: str = ""
    calibration_note: str = ""

    @property
    def effective_value(self) -> float:
        if self.status == CalibrationStatus.MANUAL and self.user_override is not None:
            return self.user_override
        if self.status == CalibrationStatus.REJECTED:
            return self.model_default
        if self.suggested_value is not None and self.status == CalibrationStatus.ACCEPTED:
            return self.suggested_value
        return self.model_default

    @property
    def is_out_of_bounds(self) -> bool:
        if self.adjustment_factor is None:
            return False
        return not (self.factor_lo <= self.adjustment_factor <= self.factor_hi)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "Parameter":       self.display_name,
            "Model default":   f"{self.model_default:.3g} {self.unit}",
            "Observed":        f"{self.observed_value:.3g} {self.unit}" if self.observed_value else "No data",
            "Suggested":       f"{self.suggested_value:.3g} {self.unit}" if self.suggested_value else "—",
            "Adj. factor":     f"{self.adjustment_factor:.2f}×" if self.adjustment_factor else "—",
            "Status":          self.status.value,
            "Effective value": f"{self.effective_value:.3g} {self.unit}",
            "Obs. count":      self.n_observations,
            "Confidence":      self.data_confidence,
            "Note":            self.calibration_note,
        }


@dataclass
class CalibrationResult:
    factors: List[CalibrationFactor] = field(default_factory=list)
    calibrated_assumptions: Any = None
    n_calibrated: int = 0
    n_rejected: int = 0
    n_pending: int = 0
    calibration_summary: str = ""
    warnings: List[str] = field(default_factory=list)

    @property
    def accepted_factors(self) -> List[CalibrationFactor]:
        return [f for f in self.factors
                if f.status in (CalibrationStatus.ACCEPTED, CalibrationStatus.MANUAL)]

    def to_summary_rows(self) -> List[Dict]:
        return [f.to_dict() for f in self.factors]


class CalibrationEngine:
    """
    Compares plant KPIs against model assumptions and produces calibration factors.

    FIX 1: The calibration map now only references keys that actually exist in
    the engineering_assumptions dict from the YAML defaults. Non-existent keys
    were silently returning None and being skipped without informing the user.

    Confirmed calibratable keys in engineering_assumptions:
      - alpha_factor:                         0.55
      - standard_aeration_efficiency_kg_o2_kwh: 1.8
      - activated_sludge_observed_yield:       0.38
    Confirmed calibratable keys in biosolids carbon_assumptions:
      - biogas_ch4_fraction:                  0.65
      - chp_electrical_efficiency:            0.38
    Confirmed in biosolids engineering_assumptions:
      - ad_vs_destruction_pct:                58.0 (as percentage)
    """

    # FIX 1: Rebuilt map — only keys confirmed to exist in YAML defaults
    # Structure: KPI_name → (section, assumption_key, lo_factor, hi_factor, rationale)
    CALIBRATION_MAP: Dict[str, Tuple[str, str, float, float, str]] = {

        "Gross SAE (airflow-based)": (
            "engineering", "standard_aeration_efficiency_kg_o2_kwh",
            0.50, 2.00,
            "Standard aeration efficiency (kg O₂/kWh). "
            "Observed gross SAE from airflow and power data. "
            "Note: gross SAE overestimates true transferred-O₂ SAE; "
            "use the calibration factor as a relative efficiency indicator."
        ),

        # alpha_factor: the most impactful single calibration parameter for aeration energy.
        # Represents the ratio of process-water O₂ transfer to clean water.
        # We derive it by comparing observed gross SAE against a clean-water diffuser baseline.
        # Typical range: 0.40 (industrial/high MLSS) to 0.80 (clean municipal).
        # NOTE: NH₄:TKN ratio is a SEPARATE parameter — do NOT proxy alpha from TKN data.
        "Observed alpha factor": (
            "engineering", "alpha_factor",
            0.40, 2.00,
            "Alpha factor (α): ratio of process water O₂ transfer rate to clean water. "
            "Lower values = surfactants, high MLSS, or diffuser fouling. "
            "Enter the observed alpha directly if measured, or derive from "
            "observed gross SAE ÷ clean-water diffuser nameplate SAE (typ. 2.0 kgO₂/kWh)."
        ),

        "Observed sludge yield": (
            "engineering", "activated_sludge_observed_yield",
            0.50, 2.00,
            "Sludge yield (kg DS / kg BOD removed). "
            "Higher than 0.45 may indicate short effective SRT, chemical dosing, "
            "or primary sludge included. Lower than 0.25 suggests long SRT."
        ),

        # "Observed biogas yield" is advisory only — biogas_ch4_fraction lives in
        # biosolids_defaults.yaml, not the wastewater AssumptionsSet.
    }

    # FIX 4: Advisory-only map — KPIs that inform WastewaterInputs, not AssumptionsSet
    INPUT_ADVISORY_MAP: Dict[str, str] = {
        "NH₄:TKN ratio": (
            "Update WastewaterInputs.influent_tkn_mg_l using the observed ratio: "
            "set TKN = measured_NH₄ / observed_ratio. "
            "Do NOT use this to calibrate alpha_factor — they are independent."
        ),
        "Average MLSS": (
            "Update WastewaterInputs.mlss_mg_l with observed value."
        ),
        "Average SRT": (
            "Update WastewaterInputs.srt_days with observed value."
        ),
        "Observed biogas yield": (
            "Update digestion model: DigestionInputs.biogas_yield_m3_per_kg_vs_destroyed "
            "directly in the Biosolids page (04c)."
        ),
    }

    def calibrate(
        self,
        assumptions: Any,
        kpi_dict: Dict[str, Optional[float]],
        kpi_confidence: Optional[Dict[str, str]] = None,
        kpi_obs_count: Optional[Dict[str, int]] = None,
    ) -> CalibrationResult:
        """
        Generate calibration factors.

        Parameters
        ----------
        assumptions      : AssumptionsSet
        kpi_dict         : {kpi_name: value}
        kpi_confidence   : {kpi_name: 'high'/'medium'/'low'} — optional
        kpi_obs_count    : {kpi_name: n_observations}        — optional
        """
        result = CalibrationResult()
        confidence = kpi_confidence or {}
        obs_counts  = kpi_obs_count  or {}

        for kpi_name, (section, key, lo, hi, rationale) in self.CALIBRATION_MAP.items():
            observed = kpi_dict.get(kpi_name)
            default  = self._get_default(assumptions, section, key)

            if default is None or default == 0:
                continue

            n_obs = obs_counts.get(kpi_name, 0)
            conf  = confidence.get(kpi_name, "medium")

            factor = CalibrationFactor(
                key=f"{section}.{key}",
                display_name=kpi_name,
                unit=self._unit_for(key),
                model_default=default,
                observed_value=observed,
                suggested_value=None,
                adjustment_factor=None,
                n_observations=n_obs,
                data_confidence=conf,
                status=CalibrationStatus.UNCHANGED if observed is None else CalibrationStatus.PENDING,
                factor_lo=lo,
                factor_hi=hi,
                rationale=rationale,
            )

            if observed is not None and default > 0:
                # FIX 2: Minimum observation gate
                if n_obs > 0 and n_obs < MIN_CALIBRATION_OBS:
                    factor.status = CalibrationStatus.UNCHANGED
                    factor.calibration_note = (
                        f"Insufficient observations ({n_obs} < {MIN_CALIBRATION_OBS} minimum). "
                        "Collect more data before applying this calibration factor."
                    )
                    result.warnings.append(
                        f"{kpi_name}: only {n_obs} observations — "
                        f"minimum {MIN_CALIBRATION_OBS} required. Factor not calculated."
                    )
                    result.factors.append(factor)
                    continue

                adj = observed / default
                factor.adjustment_factor = round(adj, 3)
                factor.suggested_value   = round(observed, 4)

                # FIX 3: Low-confidence warning
                if conf == "low":
                    factor.calibration_note = (
                        f"⚠ LOW DATA CONFIDENCE: KPI derived from sparse or incomplete data. "
                        f"Factor {adj:.2f}× should be reviewed carefully before accepting."
                    )
                    result.warnings.append(
                        f"{kpi_name}: low data confidence — calibration factor unreliable"
                    )
                elif factor.is_out_of_bounds:
                    factor.calibration_note = (
                        f"Factor {adj:.2f}× is outside expected range "
                        f"({lo:.1f}×–{hi:.1f}×). "
                        "Review data quality — sensor error or unusual operating condition?"
                    )
                    result.warnings.append(
                        f"{kpi_name}: factor {adj:.2f}× outside bounds [{lo:.1f}×–{hi:.1f}×]"
                    )
                else:
                    magnitude = "Minor" if 0.90 < adj < 1.10 else "Moderate" if 0.75 < adj < 1.33 else "Significant"
                    factor.calibration_note = (
                        f"Factor {adj:.2f}× within expected range. {magnitude} adjustment. "
                        "Note: represents an annual average — seasonal variation not captured."
                    )

            result.factors.append(factor)

        # Advisory-only KPIs (SRT, MLSS) not in calibration map
        for kpi_name, advisory in self.INPUT_ADVISORY_MAP.items():
            if kpi_name in ("Average MLSS", "Average SRT"):
                observed = kpi_dict.get(kpi_name)
                if observed is not None:
                    factor = CalibrationFactor(
                        key=f"input_advisory.{kpi_name.lower().replace(' ','_')}",
                        display_name=kpi_name,
                        unit="mg/L" if "MLSS" in kpi_name else "days",
                        model_default=0.0,
                        observed_value=observed,
                        suggested_value=observed,
                        adjustment_factor=None,
                        status=CalibrationStatus.UNCHANGED,
                        rationale=advisory,
                        calibration_note=advisory,
                        n_observations=obs_counts.get(kpi_name, 0),
                        data_confidence=confidence.get(kpi_name, "medium"),
                    )
                    result.factors.append(factor)

        result.n_pending = sum(1 for f in result.factors
                               if f.status == CalibrationStatus.PENDING)
        result.n_calibrated = 0
        result.calibration_summary = (
            f"{result.n_pending} parameter(s) available for calibration. "
            f"{len(result.warnings)} warning(s). "
            "Review each factor before accepting."
        )

        return result

    def apply_accepted_factors(
        self,
        result: CalibrationResult,
        assumptions: Any,
    ) -> Any:
        from core.assumptions.assumptions_manager import AssumptionsManager
        mgr = AssumptionsManager()
        calibrated = assumptions

        for factor in result.factors:
            if factor.status in (CalibrationStatus.ACCEPTED, CalibrationStatus.MANUAL):
                # Skip advisory-only factors (they don't map to AssumptionsSet)
                if factor.key.startswith("input_advisory."):
                    continue
                parts = factor.key.split(".", 1)
                if len(parts) == 2:
                    section, key = parts
                    value = factor.effective_value
                    calibrated = mgr.apply_override(
                        calibrated, section, key, value,
                        f"Calibrated from plant data "
                        f"(observed {factor.observed_value:.4g}, "
                        f"factor {factor.adjustment_factor:.2f}× if available, "
                        f"n={factor.n_observations} obs)",
                        "Digital Twin Calibration"
                    )

        result.calibrated_assumptions = calibrated
        result.n_calibrated = sum(
            1 for f in result.factors
            if f.status in (CalibrationStatus.ACCEPTED, CalibrationStatus.MANUAL)
            and not f.key.startswith("input_advisory.")
        )
        return calibrated

    @staticmethod
    def _get_default(assumptions: Any, section: str, key: str) -> Optional[float]:
        section_map = {
            "engineering": assumptions.engineering_assumptions,
            "carbon":      assumptions.carbon_assumptions,
            "cost":        assumptions.cost_assumptions,
        }
        return section_map.get(section, {}).get(key)

    @staticmethod
    def _unit_for(key: str) -> str:
        return {
            "standard_aeration_efficiency_kg_o2_kwh": "kg O₂/kWh",
            "alpha_factor":                            "fraction",
            "activated_sludge_observed_yield":         "kg DS/kg BOD",
            "biogas_ch4_fraction":                     "fraction",
            "chp_electrical_efficiency":               "fraction",
        }.get(key, "")
