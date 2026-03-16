"""
domains/wastewater/input_model.py

Structured input model for wastewater treatment scenarios.
Organised into four sections matching the UI:
  1. Flow conditions
  2. Influent water quality
  3. Operating conditions
  4. Economic assumptions
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class WastewaterInputs:
    """
    All engineering and economic inputs for a wastewater treatment scenario.
    """

    # ── 1. Flow conditions ────────────────────────────────────────────────
    design_flow_mld: Optional[float] = None        # Average dry weather flow (ML/day)
    peak_flow_mld: Optional[float] = None          # Peak wet weather flow (ML/day)
    peak_flow_factor: float = 2.5                  # Peak / average (used if peak not set)
    design_population_ep: Optional[float] = None   # Equivalent persons

    # ── 2. Influent water quality ─────────────────────────────────────────
    influent_bod_mg_l: float = 250.0               # Biochemical oxygen demand
    influent_cod_mg_l: float = 500.0               # COD (must be >= BOD)
    influent_tss_mg_l: float = 280.0               # Total suspended solids
    influent_nh4_mg_l: float = 35.0                # Ammonium-nitrogen
    influent_tkn_mg_l: float = 45.0                # Total Kjeldahl nitrogen (must be >= NH4)
    influent_tp_mg_l: float = 7.0                  # Total phosphorus
    influent_temperature_celsius: float = 20.0     # Wastewater temperature

    # ── Effluent quality targets ──────────────────────────────────────────
    effluent_bod_mg_l: float = 10.0
    effluent_tss_mg_l: float = 10.0
    effluent_tn_mg_l: float = 10.0
    effluent_tp_mg_l: float = 0.5
    effluent_nh4_mg_l: float = 1.0

    # ── 3. Operating conditions ───────────────────────────────────────────
    mlss_mg_l: float = 4000.0
    srt_days: float = 12.0
    hrt_hours: float = 6.0
    do_setpoint_mg_l: float = 2.0

    # ── 4. Economic assumptions ───────────────────────────────────────────
    electricity_price_per_kwh: float = 0.14
    sludge_disposal_cost_per_tonne_ds: float = 280.0
    carbon_price_per_tonne: float = 35.0
    analysis_period_years: int = 30

    # ── Site and planning ─────────────────────────────────────────────────
    site_location: str = ""
    available_land_m2: Optional[float] = None
    odour_sensitive: bool = False
    include_sludge_treatment: bool = True
    include_sidestream: bool = False
    planning_horizon_years: int = 30

    # ── Validation config ─────────────────────────────────────────────────
    _required_fields: list = field(default_factory=lambda: ["design_flow_mld"], repr=False)

    _positive_fields: list = field(default_factory=lambda: [
        "design_flow_mld", "influent_bod_mg_l", "influent_tkn_mg_l",
    ], repr=False)

    _field_bounds: dict = field(default_factory=lambda: {
        "design_flow_mld":              (0.01, 5000.0),
        "influent_bod_mg_l":            (50,   2000),
        "influent_cod_mg_l":            (80,   5000),
        "influent_tkn_mg_l":            (5,    500),
        "influent_tp_mg_l":             (0.1,  100),
        "influent_temperature_celsius": (5,    35),
        "effluent_tn_mg_l":             (1,    30),
        "effluent_tp_mg_l":             (0.01, 5.0),
        "peak_flow_factor":             (1.2,  6.0),
        "mlss_mg_l":                    (1500, 12000),
        "srt_days":                     (3,    40),
        "electricity_price_per_kwh":    (0.05, 0.50),
        "carbon_price_per_tonne":       (0,    200),
    }, repr=False)

    @property
    def effective_peak_flow_mld(self) -> float:
        if self.peak_flow_mld and self.peak_flow_mld > 0:
            return self.peak_flow_mld
        if self.design_flow_mld:
            return self.design_flow_mld * self.peak_flow_factor
        return 0.0

    @property
    def tn_in(self) -> float:
        return self.influent_tkn_mg_l
