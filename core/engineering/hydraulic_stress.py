"""
core/engineering/hydraulic_stress.py

Hydraulic Stress Testing Engine
================================
Evaluates each scenario's hydraulic performance under peak wet weather flow (PWWF).

For each technology type, checks:
  - HRT at peak flow vs minimum acceptable HRT
  - Secondary clarifier surface overflow rate (SOR) at peak
  - SBR cycle constraints (NEREDA/granular sludge fill-time ratio)
  - MBR flux at peak flow

Outputs a HydraulicStressResult per scenario with:
  - per-check PASS / WARNING / FAIL status
  - overall status (worst of all checks)
  - narrative summary
  - raw values for report table

References:
  Metcalf & Eddy 5th Ed, Table 7-21 (clarifier loading rates)
  WEF MOP 35 — Peak flow design criteria
  Nereda design guidelines (Royal HaskoningDHV)
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any


# ── Design limits ─────────────────────────────────────────────────────────────
# Clarifier SOR limits (m³/m²/d = m/d):
#   Normal:  15–25 m/d (WEF MOP 35)
#   Peak:    40–50 m/d (M&E 5th Ed Table 7-21)
CLARIFIER_SOR_PEAK_WARN  = 35.0   # m/d — above this, flag warning
CLARIFIER_SOR_PEAK_FAIL  = 48.0   # m/d — above this, fail

# Minimum HRT at peak flow (hours):
HRT_MIN: Dict[str, float] = {
    "bnr":             2.0,    # M&E Table 8-15: BNR min HRT ~2-3 hr at peak
    "granular_sludge": 1.5,    # AGS SBR: fill-limited, not HRT-limited
    "mabr_bnr":        2.0,    # same as BNR (same clarifier train)
    "bnr_mbr":         1.5,    # MBR: higher biomass density, lower HRT acceptable
    "ifas_mbbr":       2.5,    # IFAS: fixed film needs more contact time at peak
    "anmbr":           3.0,    # anaerobic: more sensitive to hydraulic surges
    "mob":             3.0,
    "default":         2.0,
}

# SBR fill ratio limits (NEREDA):
#   fill_vol / reactor_vol per reactor at peak
SBR_FILL_RATIO_WARN = 0.85   # >85% fill → marginal, plan additional capacity
SBR_FILL_RATIO_FAIL = 0.95   # ≥95% fill → insufficient operating margin, FAIL
# Engineering basis: fill ratio should not exceed 0.95 to allow for cycle timing
# variation, granule settling time, and safety margin (Nereda design guidelines)

# MBR flux limits (LMH — litres per m² per hour):
MBR_FLUX_PEAK_WARN = 25.0    # LMH at peak
MBR_FLUX_PEAK_FAIL = 35.0    # LMH at peak (above this = fouling/TMP exceedance)


@dataclass
class HydraulicCheck:
    name:    str
    value:   float
    unit:    str
    limit:   float
    status:  str         # "PASS" | "WARNING" | "FAIL"
    note:    str


@dataclass
class HydraulicStressResult:
    scenario_name:  str
    tech_code:      str
    peak_flow_mld:  float
    peak_flow_factor: float
    checks:         List[HydraulicCheck] = field(default_factory=list)
    overall_status: str = "PASS"    # worst of all checks
    narrative:      str = ""
    # Raw values for report table
    peak_hrt_hr:     Optional[float] = None
    sor_peak_m_d:    Optional[float] = None
    fill_ratio_peak: Optional[float] = None
    mbr_flux_peak:   Optional[float] = None

    def add(self, check: HydraulicCheck) -> None:
        self.checks.append(check)
        if check.status == "FAIL":
            self.overall_status = "FAIL"
        elif check.status == "WARNING" and self.overall_status == "PASS":
            self.overall_status = "WARNING"

    def build_narrative(self) -> None:
        fails   = [c for c in self.checks if c.status == "FAIL"]
        warns   = [c for c in self.checks if c.status == "WARNING"]
        passes  = [c for c in self.checks if c.status == "PASS"]
        parts   = []
        if fails:
            parts.append(
                f"FAIL: {'; '.join(c.note for c in fails)}"
            )
        if warns:
            parts.append(
                f"Warning: {'; '.join(c.note for c in warns)}"
            )
        if not fails and not warns:
            parts.append(
                f"All hydraulic checks pass at {self.peak_flow_factor:.1f}× peak flow "
                f"({self.peak_flow_mld:.1f} MLD)."
            )
        self.narrative = " | ".join(parts)


def run_hydraulic_stress(
    scenario_name:  str,
    tech_code:      str,
    domain_outputs: Dict[str, Any],
    design_flow_mld: float,
    peak_flow_factor: float = 1.5,
) -> HydraulicStressResult:
    """
    Run hydraulic stress test for one scenario.

    Parameters
    ----------
    scenario_name    : display name for the scenario
    tech_code        : technology code (e.g. "bnr", "granular_sludge")
    domain_outputs   : from ScenarioModel.domain_specific_outputs
    design_flow_mld  : average design flow (MLD)
    peak_flow_factor : PWWF / ADF ratio (default 1.5)
    """
    tp         = (domain_outputs.get("technology_performance", {}) or {}).get(tech_code, {})
    peak_mld   = design_flow_mld * peak_flow_factor
    peak_m3_hr = peak_mld * 1000 / 24   # m³/hr

    result = HydraulicStressResult(
        scenario_name    = scenario_name,
        tech_code        = tech_code,
        peak_flow_mld    = peak_mld,
        peak_flow_factor = peak_flow_factor,
    )

    # ── 1. HRT at peak ───────────────────────────────────────────────────
    v_reactor = tp.get("reactor_volume_m3") or tp.get("volume_m3") or 0.0
    if v_reactor > 0 and tech_code != "granular_sludge":
        peak_hrt = v_reactor / (peak_m3_hr)
        result.peak_hrt_hr = round(peak_hrt, 2)
        min_hrt = HRT_MIN.get(tech_code, HRT_MIN["default"])
        if peak_hrt < min_hrt * 0.8:
            status = "FAIL"
            note   = (f"HRT at peak flow {peak_hrt:.1f} hr < minimum {min_hrt:.1f} hr "
                      "— biological performance at risk under PWWF")
        elif peak_hrt < min_hrt:
            status = "WARNING"
            note   = (f"HRT at peak flow {peak_hrt:.1f} hr approaches minimum {min_hrt:.1f} hr "
                      "— confirm with hydraulic modelling")
        else:
            status = "PASS"
            note   = f"HRT at peak {peak_hrt:.1f} hr ≥ minimum {min_hrt:.1f} hr"
        result.add(HydraulicCheck("Peak HRT", peak_hrt, "hr", min_hrt, status, note))

    # ── 2. Secondary clarifier SOR at peak ───────────────────────────────
    clarifier_area = tp.get("clarifier_area_m2") or tp.get("primary_clarifier_area_m2") or 0.0
    has_clarifiers = (
        tech_code in ("bnr", "mabr_bnr", "ifas_mbbr")
        or (tech_code == "bnr_mbr" and tp.get("retain_one_clarifier"))
    )
    if clarifier_area > 0 and has_clarifiers:
        sor_peak = peak_mld * 1000 / clarifier_area   # m/d
        result.sor_peak_m_d = round(sor_peak, 1)
        if sor_peak > CLARIFIER_SOR_PEAK_FAIL:
            status = "FAIL"
            note   = (f"Clarifier SOR at peak {sor_peak:.0f} m/d > limit {CLARIFIER_SOR_PEAK_FAIL:.0f} m/d "
                      "— clarifier capacity insufficient under PWWF")
        elif sor_peak > CLARIFIER_SOR_PEAK_WARN:
            status = "WARNING"
            note   = (f"Clarifier SOR at peak {sor_peak:.0f} m/d — "
                      "approaching design limit, confirm with settling velocity testing")
        else:
            status = "PASS"
            note   = f"Clarifier SOR {sor_peak:.0f} m/d ≤ limit {CLARIFIER_SOR_PEAK_WARN:.0f} m/d"
        result.add(HydraulicCheck("Clarifier SOR", sor_peak, "m/d", CLARIFIER_SOR_PEAK_WARN, status, note))

    # ── 3. SBR / AGS fill ratio at peak ──────────────────────────────────
    if tech_code == "granular_sludge":
        fill_ratio = tp.get("peak_fill_ratio")
        if fill_ratio is None:
            # recalculate from first principles
            vol_per_reactor = tp.get("vol_per_reactor_m3") or tp.get("working_vol_per_reactor_m3") or 0.0
            fbt_vol         = tp.get("fbt_volume_m3") or tp.get("fbt_required_at_peak_m3") or 0.0
            cycle_hr        = tp.get("cycle_time_hours") or 4.0
            n_reactors      = tp.get("n_reactors") or 3
            # fill volume per reactor per cycle at peak
            fill_vol = (peak_mld * 1000 / 24) * cycle_hr / n_reactors
            fill_ratio = fill_vol / vol_per_reactor if vol_per_reactor > 0 else 0.0

        result.fill_ratio_peak = round(fill_ratio, 3)
        if fill_ratio >= SBR_FILL_RATIO_FAIL:
            status = "FAIL"
            note   = (f"SBR fill ratio at peak {fill_ratio:.2f} > 1.0 — "
                      "reactor volume insufficient, cycle cannot complete under PWWF")
        elif fill_ratio > SBR_FILL_RATIO_WARN:
            status = "WARNING"
            note   = (f"SBR fill ratio at peak {fill_ratio:.2f} — "
                      "marginal capacity, consider additional reactor or flow balancing")
        else:
            status = "PASS"
            note   = f"SBR fill ratio {fill_ratio:.2f} ≤ limit {SBR_FILL_RATIO_WARN:.2f}"
        result.add(HydraulicCheck("SBR Fill Ratio", fill_ratio, "—", SBR_FILL_RATIO_WARN, status, note))

        # SBR cycle time check — can 4-hr cycle accommodate peak fill at equal decant rate?
        cycle_hr = tp.get("cycle_time_hours") or 4.0
        fill_min = tp.get("fill_time_min_at_peak") or 0.0
        if fill_min > 0 and fill_min > cycle_hr * 60 * 0.4:
            status = "WARNING"
            note   = (f"Fill time at peak {fill_min:.0f} min = "
                      f"{fill_min/cycle_hr/60*100:.0f}% of cycle — "
                      "leaves limited time for reaction/settle/decant phases")
            result.add(HydraulicCheck("SBR Cycle Balance", fill_min/60, "hr", cycle_hr*0.4, status, note))

    # ── 4. MBR flux at peak ───────────────────────────────────────────────
    if "mbr" in tech_code and tech_code != "mabr_bnr":
        # membrane area from capex/opex data or estimate
        # MBR: packing density ~150 m²/m³ of membrane tank
        mem_tank_vol = tp.get("membrane_tank_volume_m3") or 0.0
        packing      = 150.0   # m²/m³ (typical submerged flat sheet)
        mem_area_m2  = mem_tank_vol * packing * tp.get("mbr_net_to_gross", 0.9)
        if mem_area_m2 > 0:
            flux_lmh = (peak_m3_hr * 1000) / mem_area_m2
            result.mbr_flux_peak = round(flux_lmh, 1)
            if flux_lmh > MBR_FLUX_PEAK_FAIL:
                status = "FAIL"
                note   = (f"MBR flux at peak {flux_lmh:.1f} LMH > limit {MBR_FLUX_PEAK_FAIL:.0f} LMH "
                          "— membrane TMP exceedance, fouling risk")
            elif flux_lmh > MBR_FLUX_PEAK_WARN:
                status = "WARNING"
                note   = (f"MBR flux at peak {flux_lmh:.1f} LMH — "
                          "approaching design flux, confirm membrane area with vendor")
            else:
                status = "PASS"
                note   = f"MBR flux {flux_lmh:.1f} LMH ≤ limit {MBR_FLUX_PEAK_WARN:.0f} LMH"
            result.add(HydraulicCheck("MBR Peak Flux", flux_lmh, "LMH", MBR_FLUX_PEAK_WARN, status, note))

    # ── 5. Flow balance tank check (AGS / SBR) ────────────────────────────
    if tech_code == "granular_sludge":
        fbt_vol = tp.get("fbt_volume_m3") or tp.get("fbt_required_at_peak_m3") or 0.0
        if fbt_vol > 0:
            # FBT should be sized for peak flow to equalise feed to reactors
            # Rule: FBT ≥ 2 × (peak - average) flow per cycle period
            cycle_hr = tp.get("cycle_time_hours") or 4.0
            avg_vol_per_cycle = (design_flow_mld * 1000 / 24) * cycle_hr
            peak_vol_per_cycle = (peak_mld * 1000 / 24) * cycle_hr
            surplus = peak_vol_per_cycle - avg_vol_per_cycle
            adequacy = fbt_vol / surplus if surplus > 0 else 99.0
            if adequacy < 0.8:
                status = "WARNING"
                note   = (f"Flow balance tank ({fbt_vol:.0f} m³) may be undersized for peak surge "
                          f"({surplus:.0f} m³/cycle) — consider increasing FBT volume")
            else:
                status = "PASS"
                note   = f"FBT ({fbt_vol:.0f} m³) adequate for peak flow equalisation"
            result.add(HydraulicCheck("FBT Adequacy", fbt_vol, "m³", surplus, status, note))

    result.build_narrative()
    return result


def run_all_hydraulic_stress(
    scenarios: List[Any],
    peak_flow_factor: float = 1.5,
) -> Dict[str, HydraulicStressResult]:
    """
    Run hydraulic stress test for all scenarios.
    Returns dict of scenario_name -> HydraulicStressResult.
    """
    results = {}
    for s in scenarios:
        tc = (s.treatment_pathway.technology_sequence[0]
              if s.treatment_pathway and s.treatment_pathway.technology_sequence else "")
        dso  = getattr(s, "domain_specific_outputs", None) or {}
        dinp = getattr(s, "domain_inputs", None) or {}
        flow = dinp.get("design_flow_mld") or getattr(s, "design_flow_mld", 10.0) or 10.0
        results[s.scenario_name] = run_hydraulic_stress(
            scenario_name    = s.scenario_name,
            tech_code        = tc,
            domain_outputs   = dso,
            design_flow_mld  = flow,
            peak_flow_factor = peak_flow_factor,
        )
    return results
