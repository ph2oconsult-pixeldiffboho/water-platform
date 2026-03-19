"""
domains/wastewater/brownfield/constraint_engine.py

Brownfield Constraint Engine
==============================
Evaluates whether a technology scenario is feasible within the constraints
of an existing plant.

Design rules
------------
- Reads from TechnologyResult (already produced — not re-calculated)
- Reads from BrownfieldContext (existing asset inventory)
- Reads from WastewaterInputs (flow, peak factor)
- Returns BrownfieldConstraintResult — a standalone assessment object
- Does NOT modify TechnologyResult, CostResult, or any other engine output
- Does NOT touch costing, carbon, scoring, or QA engines

Six constraint checks (in order of priority):
  1. Biological volume      — can existing tanks accommodate the process?
  2. Clarifier SOR          — does peak flow overload existing clarifiers?
  3. Aeration capacity      — do existing blowers have enough installed kW?
  4. Footprint              — is there room for net-new civil works?
  5. Hydraulic recycle      — can existing RAS/MLR pumps handle the duty?
  6. Constructability       — is the required shutdown window acceptable?

References
----------
  WEF MOP 35 — Risk-Based Decision Making in Water Infrastructure
  Metcalf & Eddy 5th Ed, Ch 7 (clarifier loading), Ch 8 (biological design)
  WEF Energy Conservation in WWTFs (2010) — blower sizing guidance
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from domains.wastewater.brownfield.brownfield_context import BrownfieldContext


# ── Design limits ─────────────────────────────────────────────────────────────

# Clarifier Surface Overflow Rate (SOR) limits at PEAK flow
# Reference: M&E 5th Ed Table 7-21
_SOR_WARN_M_PER_HR  = 1.2    # m/hr — approaching design limit
_SOR_FAIL_M_PER_HR  = 1.5    # m/hr — exceeds peak design SOR

# Blower capacity headroom — installed kW must exceed operational demand by this margin.
# The 1.20 factor accounts for: altitude derating, fouling, future load growth.
_BLOWER_CAPACITY_FACTOR = 1.20   # required kW = operational kW × 1.20

# RAS ratio — return sludge as fraction of average daily flow (m³/d)
# Technology-specific defaults used when tech-code is known.
_RAS_RATIO_DEFAULT = 1.0     # Q × 1.0 — conservative default for all technologies
_RAS_RATIO_BY_TECH: Dict[str, float] = {
    "bnr":             1.0,
    "granular_sludge": 0.0,   # AGS: no external RAS — internal recirculation
    "bnr_mbr":         0.5,   # MBR: lower RAS (MLSS controls at membrane)
    "ifas_mbbr":       1.0,
    "mabr_bnr":        1.0,
    "anmbr":           0.5,
}

# MLR (Mixed Liquor Recirculation) ratio — as fraction of average daily flow
_MLR_RATIO_BY_TECH: Dict[str, float] = {
    "bnr":             4.0,   # pre-DN requires high MLR
    "granular_sludge": 0.0,   # no separate MLR train
    "bnr_mbr":         4.0,
    "ifas_mbbr":       0.0,   # MBBR / IFAS: no discrete MLR
    "mabr_bnr":        3.0,
    "anmbr":           0.0,
}

# Programme duration required for major upgrade (days)
# Used for constructability check against max_shutdown_days
_UPGRADE_SHUTDOWN_DAYS_BY_TECH: Dict[str, int] = {
    "bnr":             0,     # typically no shutdown — existing process continues
    "granular_sludge": 30,    # SBR conversion needs bypass period
    "bnr_mbr":         21,    # membrane installation requires aeration zone shutdown
    "ifas_mbbr":       7,     # media installation — short zone-by-zone shutdown
    "mabr_bnr":        14,    # module insertion into aerobic zone
    "anmbr":           30,
}


# ── Result dataclasses ────────────────────────────────────────────────────────

@dataclass
class ConstraintCheck:
    """
    Result of a single constraint check.
    """
    name:       str
    status:     str          # "PASS" | "WARNING" | "FAIL" | "SKIP"
    required:   Optional[float]   # what the technology needs
    available:  Optional[float]   # what the existing plant provides
    unit:       str
    utilisation_pct: Optional[float]   # required / available × 100
    message:    str          # one-sentence explanation

    @property
    def is_fail(self) -> bool:
        return self.status == "FAIL"

    @property
    def is_warning(self) -> bool:
        return self.status == "WARNING"


@dataclass
class BrownfieldConstraintResult:
    """
    Full constraint assessment for one scenario against one BrownfieldContext.

    Attached to ScenarioModel as: scenario.brownfield_constraints = result
    """
    scenario_name: str
    tech_code:     str

    # Individual check results (populated by evaluate())
    checks: List[ConstraintCheck] = field(default_factory=list)

    # ── Aggregate status ──────────────────────────────────────────────────
    @property
    def feasible(self) -> bool:
        """True only when no check returns FAIL."""
        return not any(c.is_fail for c in self.checks)

    @property
    def status(self) -> str:
        """
        Worst status across all checks.
        FAIL > WARNING > PASS.  SKIP checks are ignored.
        """
        statuses = {c.status for c in self.checks if c.status != "SKIP"}
        if "FAIL" in statuses:
            return "FAIL"
        if "WARNING" in statuses:
            return "WARNING"
        return "PASS"

    @property
    def violations(self) -> List[str]:
        """FAIL check messages — must be resolved before recommendation."""
        return [c.message for c in self.checks if c.is_fail]

    @property
    def warnings(self) -> List[str]:
        """WARNING check messages — flag but do not block recommendation."""
        return [c.message for c in self.checks if c.is_warning]

    @property
    def utilisation_summary(self) -> Dict[str, Optional[float]]:
        """
        Percentage utilisation of each constrained resource.
        Keys: aeration_utilisation_pct, clarifier_utilisation_pct,
              volume_utilisation_pct, ras_utilisation_pct.
        None where the check was skipped (asset inventory not provided).
        """
        def _get(name: str) -> Optional[float]:
            for c in self.checks:
                if c.name == name:
                    return c.utilisation_pct
            return None

        return {
            "volume_utilisation_pct":    _get("Biological Volume"),
            "clarifier_utilisation_pct": _get("Clarifier SOR"),
            "aeration_utilisation_pct":  _get("Aeration Capacity"),
            "ras_utilisation_pct":       _get("Hydraulic Recycle"),
        }

    def summary_line(self) -> str:
        """One-line narrative for UI badges and report tables."""
        if self.status == "PASS":
            return f"{self.scenario_name}: all constraints satisfied."
        if self.status == "WARNING":
            return (
                f"{self.scenario_name}: {len(self.warnings)} warning(s) — "
                + "; ".join(self.warnings[:2])
            )
        return (
            f"{self.scenario_name}: {len(self.violations)} failure(s) — "
            + "; ".join(self.violations[:2])
        )


# ── Constraint engine ─────────────────────────────────────────────────────────

def evaluate(
    scenario_name:   str,
    tech_code:       str,
    tech_result:     Any,          # TechnologyResult — read-only
    inputs:          Any,          # WastewaterInputs — read-only
    brownfield:      BrownfieldContext,
) -> BrownfieldConstraintResult:
    """
    Run all six constraint checks for one scenario.

    Parameters
    ----------
    scenario_name : display name of the scenario
    tech_code     : technology code string (e.g. "bnr", "granular_sludge")
    tech_result   : TechnologyResult produced by the existing technology model
    inputs        : WastewaterInputs (flow, peak factor etc.)
    brownfield    : BrownfieldContext (existing asset inventory)

    Returns
    -------
    BrownfieldConstraintResult — attach to scenario.brownfield_constraints
    """
    result = BrownfieldConstraintResult(
        scenario_name=scenario_name,
        tech_code=tech_code,
    )

    # Convenient shorthand for performance_outputs (populated by finalise())
    po = getattr(tech_result, "performance_outputs", {}) or {}

    # Flow values
    avg_flow_m3d  = (inputs.design_flow_mld or 0.0) * 1000.0
    peak_factor   = po.get("peak_flow_factor") or getattr(inputs, "peak_flow_factor", 1.5) or 1.5
    peak_flow_m3d = avg_flow_m3d * peak_factor
    peak_flow_m3h = peak_flow_m3d / 24.0

    # ── Check 1: Biological volume ────────────────────────────────────────
    result.checks.append(
        _check_volume(tech_code, po, brownfield, avg_flow_m3d)
    )

    # ── Check 2: Clarifier SOR at peak ───────────────────────────────────
    result.checks.append(
        _check_clarifier(tech_code, po, brownfield, peak_flow_m3h)
    )

    # ── Check 3: Aeration capacity ────────────────────────────────────────
    result.checks.append(
        _check_aeration(po, brownfield)
    )

    # ── Check 4: Footprint ────────────────────────────────────────────────
    result.checks.append(
        _check_footprint(tech_result, po, brownfield)
    )

    # ── Check 5: Hydraulic recycle (RAS + MLR) ───────────────────────────
    result.checks.append(
        _check_hydraulic_recycle(tech_code, brownfield, avg_flow_m3d)
    )

    # ── Check 6: Constructability (shutdown window) ───────────────────────
    result.checks.append(
        _check_constructability(tech_code, brownfield)
    )

    return result


# ── Individual check functions ────────────────────────────────────────────────

def _check_volume(
    tech_code:   str,
    po:          Dict,
    bf:          BrownfieldContext,
    avg_flow_m3d: float,
) -> ConstraintCheck:
    """
    Check 1: Can existing bioreactor volume support the new technology?

    Rule:
      required_volume = technology model reactor_volume_m3
      existing_volume = bf.total_bioreactor_volume_m3
      If required > existing AND can_add_new_tank == False → FAIL
      If required > existing AND can_add_new_tank == True  → WARNING
                                                              (new tank needed)
      If required <= existing                              → PASS
    """
    required = po.get("reactor_volume_m3") or 0.0

    # AGS/Nereda has a different volume key
    if not required and tech_code == "granular_sludge":
        required = po.get("volume_m3") or 0.0

    existing = bf.total_bioreactor_volume_m3

    if required <= 0.0:
        return ConstraintCheck(
            name="Biological Volume", status="SKIP",
            required=None, available=existing, unit="m³",
            utilisation_pct=None,
            message="Required volume not available from technology model — check skipped.",
        )

    utilisation = (required / existing * 100) if existing > 0 else 999.0

    if existing <= 0:
        # No existing volume recorded — can't assess
        return ConstraintCheck(
            name="Biological Volume", status="SKIP",
            required=required, available=existing, unit="m³",
            utilisation_pct=None,
            message="Existing bioreactor volume not specified in brownfield context.",
        )

    deficit_m3 = max(0.0, required - existing)

    if deficit_m3 <= 0:
        return ConstraintCheck(
            name="Biological Volume", status="PASS",
            required=round(required), available=round(existing), unit="m³",
            utilisation_pct=round(utilisation, 1),
            message=(
                f"Existing bioreactor volume {existing:.0f} m³ accommodates "
                f"required {required:.0f} m³ ({utilisation:.0f}% utilised)."
            ),
        )

    if bf.can_add_new_tank:
        return ConstraintCheck(
            name="Biological Volume", status="WARNING",
            required=round(required), available=round(existing), unit="m³",
            utilisation_pct=round(utilisation, 1),
            message=(
                f"Required volume {required:.0f} m³ exceeds existing {existing:.0f} m³ "
                f"(deficit {deficit_m3:.0f} m³). New tank construction required — "
                f"confirm available footprint and planning approval."
            ),
        )

    return ConstraintCheck(
        name="Biological Volume", status="FAIL",
        required=round(required), available=round(existing), unit="m³",
        utilisation_pct=round(utilisation, 1),
        message=(
            f"Required volume {required:.0f} m³ exceeds existing {existing:.0f} m³ "
            f"(deficit {deficit_m3:.0f} m³). can_add_new_tank = False — "
            f"this technology cannot be accommodated without new civil works."
        ),
    )


def _check_clarifier(
    tech_code:    str,
    po:           Dict,
    bf:           BrownfieldContext,
    peak_flow_m3h: float,
) -> ConstraintCheck:
    """
    Check 2: Clarifier Surface Overflow Rate at peak flow.

    SOR = peak_flow (m³/hr) / total clarifier area (m²)
    Limits (Metcalf & Eddy Table 7-21):
      > 1.5 m/hr → FAIL
      > 1.2 m/hr → WARNING
      ≤ 1.2 m/hr → PASS

    Technologies without secondary clarifiers (MBR, AGS) → SKIP.
    """
    # Technologies that do not use conventional secondary clarifiers
    _no_clarifier_techs = {"granular_sludge", "bnr_mbr", "anmbr"}
    if tech_code in _no_clarifier_techs:
        return ConstraintCheck(
            name="Clarifier SOR", status="SKIP",
            required=None, available=None, unit="m/hr",
            utilisation_pct=None,
            message=f"{tech_code} does not use conventional secondary clarifiers — SOR check skipped.",
        )

    clarifier_area  = bf.clarifier_area_m2
    clarifier_count = bf.clarifier_count or 1

    if not clarifier_area or clarifier_area <= 0:
        return ConstraintCheck(
            name="Clarifier SOR", status="SKIP",
            required=None, available=None, unit="m/hr",
            utilisation_pct=None,
            message="Existing clarifier area not specified — SOR check skipped.",
        )

    total_area = clarifier_area * clarifier_count
    sor_m_hr   = peak_flow_m3h / total_area if total_area > 0 else 999.0
    utilisation = (sor_m_hr / _SOR_FAIL_M_PER_HR) * 100

    if sor_m_hr > _SOR_FAIL_M_PER_HR:
        return ConstraintCheck(
            name="Clarifier SOR", status="FAIL",
            required=round(sor_m_hr, 2), available=_SOR_FAIL_M_PER_HR, unit="m/hr",
            utilisation_pct=round(utilisation, 1),
            message=(
                f"Clarifier SOR at peak flow = {sor_m_hr:.2f} m/hr exceeds limit "
                f"{_SOR_FAIL_M_PER_HR} m/hr. Clarifier capacity insufficient — "
                f"expansion or flow attenuation required."
            ),
        )

    if sor_m_hr > _SOR_WARN_M_PER_HR:
        return ConstraintCheck(
            name="Clarifier SOR", status="WARNING",
            required=round(sor_m_hr, 2), available=_SOR_FAIL_M_PER_HR, unit="m/hr",
            utilisation_pct=round(utilisation, 1),
            message=(
                f"Clarifier SOR at peak flow = {sor_m_hr:.2f} m/hr is approaching "
                f"design limit ({_SOR_FAIL_M_PER_HR} m/hr). "
                f"Confirm with settling velocity testing before proceeding."
            ),
        )

    return ConstraintCheck(
        name="Clarifier SOR", status="PASS",
        required=round(sor_m_hr, 2), available=_SOR_FAIL_M_PER_HR, unit="m/hr",
        utilisation_pct=round(utilisation, 1),
        message=(
            f"Clarifier SOR {sor_m_hr:.2f} m/hr ≤ limit {_SOR_FAIL_M_PER_HR} m/hr "
            f"({utilisation:.0f}% of limit)."
        ),
    )


def _check_aeration(
    po:  Dict,
    bf:  BrownfieldContext,
) -> ConstraintCheck:
    """
    Check 3: Installed blower capacity vs required aeration demand.

    Required kW is taken from technology model aeration_energy_kwh_day / 24
    (operational kW) multiplied by the capacity factor (installed headroom).

    Rule:
      required_installed_kw = aeration_kwh_day / 24 × 1.20
      If required > available → FAIL
    """
    aeration_kwh_day = po.get("aeration_energy_kwh_day") or 0.0
    available_kw     = bf.blower_capacity_kw

    if aeration_kwh_day <= 0:
        return ConstraintCheck(
            name="Aeration Capacity", status="SKIP",
            required=None, available=available_kw, unit="kW",
            utilisation_pct=None,
            message="Aeration demand not available from technology model — check skipped.",
        )

    if available_kw is None or available_kw <= 0:
        return ConstraintCheck(
            name="Aeration Capacity", status="SKIP",
            required=None, available=None, unit="kW",
            utilisation_pct=None,
            message="Existing blower capacity not specified — aeration check skipped.",
        )

    operational_kw = aeration_kwh_day / 24.0
    required_kw    = operational_kw * _BLOWER_CAPACITY_FACTOR
    utilisation    = (required_kw / available_kw) * 100

    if required_kw > available_kw:
        deficit_kw = required_kw - available_kw
        return ConstraintCheck(
            name="Aeration Capacity", status="FAIL",
            required=round(required_kw, 1), available=round(available_kw, 1), unit="kW",
            utilisation_pct=round(utilisation, 1),
            message=(
                f"Required installed blower capacity {required_kw:.0f} kW exceeds "
                f"available {available_kw:.0f} kW (deficit {deficit_kw:.0f} kW). "
                f"Blower augmentation required."
            ),
        )

    return ConstraintCheck(
        name="Aeration Capacity", status="PASS",
        required=round(required_kw, 1), available=round(available_kw, 1), unit="kW",
        utilisation_pct=round(utilisation, 1),
        message=(
            f"Required {required_kw:.0f} kW ≤ available {available_kw:.0f} kW "
            f"({utilisation:.0f}% utilised)."
        ),
    )


def _check_footprint(
    tech_result: Any,
    po:          Dict,
    bf:          BrownfieldContext,
) -> ConstraintCheck:
    """
    Check 4: Footprint constraint.

    Required footprint = technology model footprint_m2.
    Existing footprint occupied by existing tanks is assumed fully reused.
    Net-new footprint = required - existing bioreactor footprint estimate.

    Conservative heuristic: existing tank footprint ≈ existing_volume / 4.5 m depth.
    If net-new > available_footprint_m2 → FAIL.
    """
    required_footprint = (
        po.get("footprint_m2")
        or getattr(tech_result, "footprint_m2", None)
        or 0.0
    )
    available = bf.available_footprint_m2

    if required_footprint <= 0:
        return ConstraintCheck(
            name="Footprint", status="SKIP",
            required=None, available=available, unit="m²",
            utilisation_pct=None,
            message="Required footprint not available from technology model — check skipped.",
        )

    if available is None:
        return ConstraintCheck(
            name="Footprint", status="SKIP",
            required=round(required_footprint), available=None, unit="m²",
            utilisation_pct=None,
            message="Available footprint not specified in brownfield context — check skipped.",
        )

    # Estimate footprint already occupied by existing bioreactor tanks
    # (not available for new works, but reusable by the upgraded process)
    existing_vol  = bf.total_bioreactor_volume_m3
    existing_fp   = existing_vol / 4.5 if existing_vol > 0 else 0.0  # assume 4.5 m average depth

    net_new_fp = max(0.0, required_footprint - existing_fp)
    utilisation = (net_new_fp / available * 100) if available > 0 else 999.0

    if net_new_fp > available:
        deficit = net_new_fp - available
        return ConstraintCheck(
            name="Footprint", status="FAIL",
            required=round(net_new_fp), available=round(available), unit="m²",
            utilisation_pct=round(utilisation, 1),
            message=(
                f"Net-new footprint required {net_new_fp:.0f} m² exceeds "
                f"available {available:.0f} m² (deficit {deficit:.0f} m²). "
                f"Site cannot accommodate this technology without acquiring additional land."
            ),
        )

    return ConstraintCheck(
        name="Footprint", status="PASS",
        required=round(net_new_fp), available=round(available), unit="m²",
        utilisation_pct=round(utilisation, 1),
        message=(
            f"Net-new footprint {net_new_fp:.0f} m² within available "
            f"{available:.0f} m² ({utilisation:.0f}% utilised)."
        ),
    )


def _check_hydraulic_recycle(
    tech_code:    str,
    bf:           BrownfieldContext,
    avg_flow_m3d: float,
) -> ConstraintCheck:
    """
    Check 5: RAS + MLR pump capacity vs technology demand.

    RAS demand  = avg_flow × RAS ratio (technology-specific)
    MLR demand  = avg_flow × MLR ratio (technology-specific, 0 if not required)
    Total recycle demand = RAS + MLR

    Available  = bf.ras_capacity_m3_d + bf.mlr_capacity_m3_d

    If total demand > total available → FAIL
    """
    ras_ratio = _RAS_RATIO_BY_TECH.get(tech_code, _RAS_RATIO_DEFAULT)
    mlr_ratio = _MLR_RATIO_BY_TECH.get(tech_code, 0.0)

    ras_demand = avg_flow_m3d * ras_ratio
    mlr_demand = avg_flow_m3d * mlr_ratio
    total_demand = ras_demand + mlr_demand

    ras_avail = bf.ras_capacity_m3_d or 0.0
    mlr_avail = bf.mlr_capacity_m3_d or 0.0
    total_avail = ras_avail + mlr_avail

    # If no recycle required (e.g. AGS) → auto-pass
    if total_demand <= 0:
        return ConstraintCheck(
            name="Hydraulic Recycle", status="PASS",
            required=0.0, available=total_avail, unit="m³/d",
            utilisation_pct=0.0,
            message=f"{tech_code}: no RAS/MLR recycle required.",
        )

    if total_avail <= 0:
        return ConstraintCheck(
            name="Hydraulic Recycle", status="SKIP",
            required=round(total_demand), available=None, unit="m³/d",
            utilisation_pct=None,
            message="RAS/MLR capacity not specified in brownfield context — check skipped.",
        )

    utilisation = (total_demand / total_avail) * 100

    if total_demand > total_avail:
        deficit = total_demand - total_avail
        return ConstraintCheck(
            name="Hydraulic Recycle", status="FAIL",
            required=round(total_demand), available=round(total_avail), unit="m³/d",
            utilisation_pct=round(utilisation, 1),
            message=(
                f"Recycle demand {total_demand:.0f} m³/d (RAS {ras_demand:.0f} + "
                f"MLR {mlr_demand:.0f}) exceeds available {total_avail:.0f} m³/d "
                f"(deficit {deficit:.0f} m³/d). Pump augmentation required."
            ),
        )

    return ConstraintCheck(
        name="Hydraulic Recycle", status="PASS",
        required=round(total_demand), available=round(total_avail), unit="m³/d",
        utilisation_pct=round(utilisation, 1),
        message=(
            f"Recycle demand {total_demand:.0f} m³/d ≤ available "
            f"{total_avail:.0f} m³/d ({utilisation:.0f}% utilised)."
        ),
    )


def _check_constructability(
    tech_code: str,
    bf:        BrownfieldContext,
) -> ConstraintCheck:
    """
    Check 6: Required shutdown window vs maximum acceptable downtime.

    This check does NOT produce FAIL — constructability risk is flagged as
    WARNING or HIGH RISK for information only.  The utility decides whether
    to accept the constraint; it is not an engineering impossibility.

    Rule:
      required_shutdown = technology-specific estimate (days)
      If required > max_shutdown_days → WARNING (HIGH RISK)
      Else                            → PASS
    """
    required_shutdown = _UPGRADE_SHUTDOWN_DAYS_BY_TECH.get(tech_code, 14)
    max_allowed       = bf.max_shutdown_days

    utilisation = (
        (required_shutdown / max_allowed * 100)
        if max_allowed > 0 else
        (0.0 if required_shutdown == 0 else 999.0)
    )

    if required_shutdown == 0:
        return ConstraintCheck(
            name="Constructability", status="PASS",
            required=0, available=max_allowed, unit="days",
            utilisation_pct=0.0,
            message=f"{tech_code}: no continuous shutdown required during construction.",
        )

    if required_shutdown > max_allowed:
        return ConstraintCheck(
            name="Constructability", status="WARNING",
            required=required_shutdown, available=max_allowed, unit="days",
            utilisation_pct=round(utilisation, 1),
            message=(
                f"Estimated shutdown {required_shutdown}d exceeds maximum acceptable "
                f"{max_allowed}d. HIGH CONSTRUCTION RISK — bypass or phased staging "
                f"strategy must be confirmed before commitment."
            ),
        )

    return ConstraintCheck(
        name="Constructability", status="PASS",
        required=required_shutdown, available=max_allowed, unit="days",
        utilisation_pct=round(utilisation, 1),
        message=(
            f"Estimated shutdown {required_shutdown}d within allowed "
            f"{max_allowed}d window."
        ),
    )


# ── Batch evaluation ──────────────────────────────────────────────────────────

def evaluate_all(
    scenarios:  List[Any],             # List[ScenarioModel]
    brownfield: BrownfieldContext,
    inputs:     Any,                   # WastewaterInputs
) -> Dict[str, BrownfieldConstraintResult]:
    """
    Evaluate constraints for all scenarios and return a dict keyed by scenario_name.

    Parameters
    ----------
    scenarios  : List of ScenarioModel objects with cost_result populated
    brownfield : Single BrownfieldContext (the existing plant being upgraded)
    inputs     : WastewaterInputs (flow, peak factor)

    Returns
    -------
    Dict[scenario_name → BrownfieldConstraintResult]
    """
    from domains.wastewater.result_model import TechnologyResult   # local import — no circular

    results: Dict[str, BrownfieldConstraintResult] = {}

    for sc in scenarios:
        # Extract tech_code and TechnologyResult from domain_specific_outputs
        tp   = sc.treatment_pathway
        tc   = (tp.technology_sequence[0]
                if tp and tp.technology_sequence else "")

        # TechnologyResult is not stored on ScenarioModel directly — reconstruct
        # a lightweight proxy from performance_outputs for the constraint checks
        dso  = getattr(sc, "domain_specific_outputs", None) or {}
        po   = (dso.get("technology_performance") or {}).get(tc, {})

        # Build a minimal proxy object that satisfies the constraint engine API
        class _TRProxy:
            performance_outputs = po
            footprint_m2        = po.get("footprint_m2")
            volume_m3           = po.get("reactor_volume_m3")

        results[sc.scenario_name] = evaluate(
            scenario_name=sc.scenario_name,
            tech_code=tc,
            tech_result=_TRProxy(),
            inputs=inputs,
            brownfield=brownfield,
        )

    return results
