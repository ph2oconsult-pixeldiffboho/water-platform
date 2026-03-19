"""
domains/wastewater/brownfield/retrofit_models.py

Data models for brownfield retrofit options and applicability results.

Design rules
------------
- Pure data — no calculation logic in this file
- All cost fields in consistent units: CAPEX in $M, OPEX in k$/yr
- performance_effects and risk_effects use additive deltas where possible
  so callers can apply them without knowing the base value
- Optional fields default to None so the library can indicate
  "not applicable" vs "zero" cleanly
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class RetrofitOption:
    """
    Descriptor for one type of brownfield upgrade intervention.

    Each instance describes WHAT can be done, not the specific outcome
    for a particular scenario.  The library holds one RetrofitOption per
    retrofit type; evaluate_retrofit_applicability() produces a
    RetrofitApplicationResult for a specific scenario.

    Parameters
    ----------
    code : str
        Short unique identifier.  Convention: BF-XX.
        Must match keys in the library dict.
    name : str
        Human-readable name for UI and reports.
    description : str
        One-paragraph engineering description.
    applicable_to_technologies : list[str]
        Technology codes this retrofit can be applied to.
        Empty list means applicable to all.
    trigger_conditions : list[str]
        Plain-English descriptions of when this retrofit is relevant.
        Used in reporting and QA narrative.
    modifies_assets : list[str]
        Which existing assets are affected.
        One of: "bioreactor", "clarifier", "blower", "dosing_system",
                "sbr_reactor", "flow_balance_tank"
    capex_delta_basis_key : str | None
        Key into sizing parameters for variable CAPEX calculation.
        e.g. "aerobic_volume_m3" → CAPEX scales with aerobic zone size.
        None means fixed_capex_delta_m is the only CAPEX component.
    opex_delta_basis_key : str | None
        Key into sizing parameters for variable OPEX calculation.
        None means fixed_opex_delta_kyr is the only OPEX component.
    fixed_capex_delta_m : float | None
        Fixed CAPEX component ($M) independent of plant size.
        Added to any variable component.
    fixed_opex_delta_kyr : float | None
        Fixed OPEX delta (k$/yr) independent of plant size.
    unit_capex_per_basis : float | None
        Unit rate for variable CAPEX ($/unit of capex_delta_basis_key).
        e.g. 180.0 $/m³ of aerobic volume for IFAS media.
    unit_opex_per_basis_kyr : float | None
        Unit rate for variable OPEX delta (k$/yr per unit of basis).
    performance_effects : dict
        Expected changes to performance outputs.
        Keys match performance_outputs dict keys.
        Values are deltas (additive) or targets (str "target").
        e.g. {"effluent_tp_mg_l": "target"} means achieve the TP target.
             {"sludge_production_kgds_day": +0.05}  means +5% sludge.
    risk_effects : dict
        Expected changes to risk scores.
        Keys: "operational_risk_adj", "implementation_risk_adj"
        Values: float delta applied to the raw risk score.
    shutdown_days : int
        Estimated continuous shutdown required for installation.
        0 = no shutdown required.
    can_stage : bool
        True if the retrofit can be delivered in phases without
        requiring a single continuous shutdown.
    notes : list[str]
        Engineering caveats, reference sources, and assumptions.
    """

    # ── Identity ──────────────────────────────────────────────────────────
    code:        str
    name:        str
    description: str

    # ── Applicability ─────────────────────────────────────────────────────
    applicable_to_technologies: List[str] = field(default_factory=list)
    trigger_conditions:         List[str] = field(default_factory=list)
    modifies_assets:            List[str] = field(default_factory=list)

    # ── Cost structure ────────────────────────────────────────────────────
    capex_delta_basis_key:   Optional[str]   = None
    opex_delta_basis_key:    Optional[str]   = None
    fixed_capex_delta_m:     Optional[float] = None
    fixed_opex_delta_kyr:    Optional[float] = None
    unit_capex_per_basis:    Optional[float] = None
    unit_opex_per_basis_kyr: Optional[float] = None

    # ── Engineering effects ───────────────────────────────────────────────
    performance_effects: Dict[str, Any] = field(default_factory=dict)
    risk_effects:        Dict[str, Any] = field(default_factory=dict)

    # ── Constructability ──────────────────────────────────────────────────
    shutdown_days: int  = 0
    can_stage:     bool = True

    # ── Notes ─────────────────────────────────────────────────────────────
    notes: List[str] = field(default_factory=list)

    def __repr__(self) -> str:
        return f"RetrofitOption({self.code}: {self.name})"


@dataclass
class RetrofitApplicationResult:
    """
    Result of applying one RetrofitOption to a specific scenario.

    Produced by evaluate_retrofit_applicability().
    This is the "does it fit THIS scenario" answer.

    Parameters
    ----------
    retrofit_code : str
        The RetrofitOption.code this result belongs to.
    retrofit_name : str
        Human-readable name for display.
    applicable : bool
        True if the retrofit addresses a real problem in this scenario.
        False if the retrofit is not relevant (e.g. no TP problem for ferric).
    reason : str
        One sentence explaining why applicable=True or False.
    capex_delta_m : float
        Estimated additional CAPEX ($M).  0.0 if not applicable.
    opex_delta_kyr : float
        Estimated additional OPEX (k$/yr).  0.0 if not applicable.
    updated_constraints : dict
        Predicted constraint check statuses AFTER retrofit is applied.
        Keyed by constraint name (e.g. "Clarifier SOR").
        Values: "PASS" | "WARNING" | "FAIL" (predicted, not recalculated).
    updated_performance : dict
        Predicted performance output values AFTER retrofit.
        Only includes fields that the retrofit modifies.
        e.g. {"effluent_tp_mg_l": 0.5, "sludge_production_kgds_day": 1450}
    updated_risk : dict
        Predicted risk score deltas AFTER retrofit.
        e.g. {"operational_risk_adj": +2.0, "implementation_risk_adj": +3.0}
    notes : list[str]
        Engineering caveats specific to this scenario-retrofit combination.
    trade_off : str
        One sentence describing the key cost/performance trade-off.
    """

    retrofit_code:       str
    retrofit_name:       str
    applicable:          bool
    reason:              str
    capex_delta_m:       float                = 0.0
    opex_delta_kyr:      float                = 0.0
    updated_constraints: Dict[str, str]       = field(default_factory=dict)
    updated_performance: Dict[str, Any]       = field(default_factory=dict)
    updated_risk:        Dict[str, float]     = field(default_factory=dict)
    notes:               List[str]            = field(default_factory=list)
    trade_off:           str                  = ""

    def summary(self) -> str:
        """One-line summary for tables and logging."""
        if not self.applicable:
            return f"{self.retrofit_name}: not applicable — {self.reason}"
        return (
            f"{self.retrofit_name}: applicable — "
            f"+${self.capex_delta_m:.2f}M CAPEX, +${self.opex_delta_kyr:.0f}k/yr OPEX. "
            f"{self.reason}"
        )
