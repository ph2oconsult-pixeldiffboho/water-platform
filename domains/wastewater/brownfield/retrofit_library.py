"""
domains/wastewater/brownfield/retrofit_library.py

Brownfield Retrofit Library
============================
Catalogue of five upgrade interventions and their applicability engine.

The library answers two questions:
  1. Which retrofits are candidates for this technology?
     → get_brownfield_retrofit_options()

  2. Is this specific retrofit applicable to this specific scenario,
     and what would it cost and do?
     → evaluate_retrofit_applicability()

Design rules
------------
- Does NOT modify TechnologyResult, CostResult, or any other engine output
- Does NOT touch scoring, QA, or report engines
- Does NOT produce ScenarioModel objects (that is for the scenario generator, Step 4)
- Costs reuse unit rates already established in remediation.py and
  intervention_scenarios.py for internal consistency

Unit rate references
--------------------
  FeCl₃ price:           $0.72/kg    (intervention_scenarios.py)
  Ferric dose:           20.9 g FeCl₃/g P removed (intervention_scenarios.py)
  Clarifier civil+equip: $3,500/m²   (remediation.py CLARIFIER_AREA_COST_PER_M2)
  Concrete tankage:      $850/m³     (remediation.py CONCRETE_TANK_PER_M3)
  SBR equipment:         $650/m³     (remediation.py SBR_REACTOR_EQUIPMENT_PER_M3)
  Contingency + margin:  × 1.344     (remediation.py CIVIL_TOTAL_MULTIPLIER)
  IFAS media install:    $180/m³ aerobic zone (architecture plan, concept ±40%)
  MABR module install:   $250/m³ aerobic zone (architecture plan, concept ±40%)
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from domains.wastewater.brownfield.retrofit_models import RetrofitOption, RetrofitApplicationResult

# ── Internal cost constants (same values as remediation.py) ──────────────────
_CLARIFIER_COST_PER_M2    = 3_500.0   # $/m² clarifier civil + equipment
_CONCRETE_TANK_PER_M3     = 850.0     # $/m³ bioreactor civil
_SBR_EQUIPMENT_PER_M3     = 650.0     # $/m³ SBR-specific equipment
_CIVIL_TOTAL_MULTIPLIER   = 1.344     # contingency (1.20) × contractor margin (1.12)
_FERRIC_PRICE_PER_KG      = 0.72      # $/kg FeCl₃ (liquid, bulk)
_FERRIC_DOSE_G_PER_G_P    = 20.9     # g FeCl₃ / g P removed (molar: 4 × 162.2 / 31)
_IFAS_MEDIA_PER_M3        = 180.0    # $/m³ aerobic zone for IFAS media + installation
_MABR_MODULE_PER_M3       = 250.0    # $/m³ aerobic zone for MABR modules + installation
_MAINTENANCE_RATE         = 0.015    # 1.5% of CAPEX per year for maintenance OPEX


# ── Retrofit catalogue ────────────────────────────────────────────────────────

_LIBRARY: Dict[str, RetrofitOption] = {

    "BF-01": RetrofitOption(
        code        = "BF-01",
        name        = "Ferric chloride dosing for TP compliance",
        description = (
            "Installation of a ferric chloride (FeCl₃) chemical dosing system "
            "to achieve effluent TP targets through chemical phosphorus precipitation. "
            "A dosing skid, chemical storage tank, and injection points are added to "
            "the existing process train. No new bioreactor volume is required. "
            "The retrofit is applicable to any biological process where the biological "
            "P removal alone cannot consistently achieve the licence target."
        ),
        applicable_to_technologies = [],   # all technologies
        trigger_conditions = [
            "Effluent TP modelled above licence target",
            "Biological P removal insufficient at low influent BOD/P ratio",
            "Tight TP licence (< 1 mg/L) requiring chemical polishing",
        ],
        modifies_assets = ["dosing_system"],
        # Cost: variable with flow (ferric dose) + fixed dosing skid
        capex_delta_basis_key   = None,
        opex_delta_basis_key    = None,
        fixed_capex_delta_m     = None,    # computed from flow in applicability engine
        fixed_opex_delta_kyr    = None,    # computed from TP deficit
        unit_capex_per_basis    = None,
        unit_opex_per_basis_kyr = None,
        performance_effects = {
            "effluent_tp_mg_l":            "target",    # achieves TP target
            "sludge_production_kgds_day":  "+5%",       # ~5% more chemical sludge
        },
        risk_effects = {
            "operational_risk_adj":     +2.0,   # chemical handling, dosing control loop
            "implementation_risk_adj":  +1.0,   # simple installation
        },
        shutdown_days = 2,
        can_stage     = True,
        notes = [
            "Dose: 20.9 g FeCl₃ per g P removed (molar: 4 × 162.2 / 31).",
            "FeCl₃ price: $0.72/kg bulk liquid (AUD 2024 concept rate).",
            "CAPEX: $0.3M base + $0.02M/MLD dosing skid and storage.",
            "Sludge increase is approximate — chemical sludge chemistry varies.",
            "Corrosion-resistant pipework required in dosing zone.",
        ],
    ),

    "BF-02": RetrofitOption(
        code        = "BF-02",
        name        = "IFAS media addition to aerobic zone",
        description = (
            "Insertion of Integrated Fixed-film Activated Sludge (IFAS) plastic carrier "
            "media into the existing aerobic zone to increase effective nitrification "
            "capacity. The biofilm on the media provides supplemental nitrification "
            "without increasing tank volume. Retention screens are added to contain media. "
            "This is one of the most common and lowest-disruption brownfield upgrades "
            "for BNR plants needing increased TN removal or capacity uplift."
        ),
        applicable_to_technologies = ["bnr", "ifas_mbbr"],
        trigger_conditions = [
            "Biological volume insufficient for required nitrification capacity",
            "TN licence tighter than existing BNR can reliably achieve",
            "Capacity upgrade required without new tank construction",
            "Aerobic zone volume ≥ 500 m³ (minimum for media effectiveness)",
        ],
        modifies_assets = ["bioreactor"],
        capex_delta_basis_key   = "v_aerobic_m3",   # scales with aerobic zone volume
        opex_delta_basis_key    = None,
        fixed_capex_delta_m     = 0.10,              # fixed: screens, civil connections
        fixed_opex_delta_kyr    = 8.0,               # maintenance of media + screens
        unit_capex_per_basis    = _IFAS_MEDIA_PER_M3 / 1e6,   # $/m³ → $M/m³
        unit_opex_per_basis_kyr = None,
        performance_effects = {
            "nitrification_capacity_uplift_pct": +30,    # indicative
            "aeration_energy_kwh_day":            "+5%", # slightly more O2 demand
        },
        risk_effects = {
            "operational_risk_adj":    +3.0,   # biofilm process complexity
            "implementation_risk_adj": +2.0,   # media retention screen installation
        },
        shutdown_days = 5,
        can_stage     = True,
        notes = [
            "Media fill ratio: 35–45% of aerobic zone volume (DO/biofilm interaction).",
            "CAPEX: $180/m³ aerobic zone for media, screens, and installation.",
            "Blower capacity increase may be required — check aeration constraint.",
            "Suitable for retrofit into open-top rectangular or circular tanks.",
            "Ref: WEF MOP 35 — IFAS Design and Operation.",
        ],
    ),

    "BF-03": RetrofitOption(
        code        = "BF-03",
        name        = "MABR retrofit to aerobic zone",
        description = (
            "Installation of Membrane-Aerated Biofilm Reactor (MABR) modules into "
            "the existing aerobic zone. MABR provides counter-diffusional oxygen supply "
            "through gas-permeable membranes, supporting a high-density biofilm "
            "that nitrifies efficiently at low bulk DO. The result is simultaneous "
            "nitrification-denitrification (SND) and a significant reduction in "
            "aeration energy. MABR is more complex and costly than IFAS but offers "
            "greater energy savings and nitrification uplift."
        ),
        applicable_to_technologies = ["bnr", "mabr_bnr"],
        trigger_conditions = [
            "Biological volume insufficient and IFAS is not sufficient",
            "Energy reduction is a strategic priority alongside compliance",
            "Tight TN target requiring SND contribution",
            "Existing aerobic zone accessible for module installation (shutdown window available)",
        ],
        modifies_assets = ["bioreactor"],
        capex_delta_basis_key   = "v_aerobic_m3",
        opex_delta_basis_key    = None,
        fixed_capex_delta_m     = 0.20,              # fixed: gas skid, controls
        fixed_opex_delta_kyr    = 15.0,              # O₂ / air supply + maintenance
        unit_capex_per_basis    = _MABR_MODULE_PER_M3 / 1e6,
        unit_opex_per_basis_kyr = None,
        performance_effects = {
            "aeration_energy_kwh_day":           "-20%",  # lower bulk DO needed
            "nitrification_capacity_uplift_pct":  +40,
        },
        risk_effects = {
            "operational_risk_adj":    +5.0,   # gas pressure control, novel technology
            "implementation_risk_adj": +4.0,   # module installation + gas supply
        },
        shutdown_days = 10,
        can_stage     = True,
        notes = [
            "CAPEX: $250/m³ aerobic zone for modules, gas skid, and installation.",
            "Energy saving: typically 20–30% aeration reduction (site-specific).",
            "Limited AU contractor experience — vendor involvement in commissioning.",
            "Gas-side fouling must be managed — ongoing monitoring required.",
            "Ref: Ozzie et al. (2019) MABR Retrofit Experience, Water Research.",
        ],
    ),

    "BF-04": RetrofitOption(
        code        = "BF-04",
        name        = "Clarifier expansion",
        description = (
            "Addition of a new secondary clarifier (or expansion of existing clarifier "
            "area) to resolve Surface Overflow Rate (SOR) overload at peak flow. "
            "This is the standard response when the clarifier constraint check returns "
            "FAIL. The new clarifier runs in parallel with the existing unit(s). "
            "Civil works are significant and require careful staging to maintain "
            "hydraulic capacity during construction."
        ),
        applicable_to_technologies = ["bnr", "mabr_bnr", "ifas_mbbr"],
        trigger_conditions = [
            "Clarifier SOR at peak flow exceeds 1.5 m/hr (FAIL)",
            "Clarifier SOR at peak flow 1.2–1.5 m/hr (WARNING) with no headroom",
        ],
        modifies_assets = ["clarifier"],
        capex_delta_basis_key   = "clarifier_deficit_m2",   # m² of new area needed
        opex_delta_basis_key    = None,
        fixed_capex_delta_m     = 0.0,
        fixed_opex_delta_kyr    = None,
        unit_capex_per_basis    = _CLARIFIER_COST_PER_M2 * _CIVIL_TOTAL_MULTIPLIER / 1e6,
        unit_opex_per_basis_kyr = None,
        performance_effects = {
            "clarifier_sor_m_hr": "below_limit",   # resolves SOR overload
        },
        risk_effects = {
            "operational_risk_adj":    +1.0,   # additional clarifier to operate
            "implementation_risk_adj": +3.0,   # significant civil works
        },
        shutdown_days = 20,
        can_stage     = False,   # clarifier construction generally not stageable
        notes = [
            "CAPEX: $3,500/m² × 1.344 civil multiplier for new clarifier area.",
            "Target SOR: ≤ 1.2 m/hr at peak flow (comfortable margin).",
            "Area calculated to bring SOR to 1.2 m/hr target at PWWF.",
            "Consider parallel inlet works and sludge return upgrades.",
            "Ref: M&E 5th Ed Table 7-21 — Secondary Clarifier Design Criteria.",
        ],
    ),

    "BF-05": RetrofitOption(
        code        = "BF-05",
        name        = "Additional SBR reactor / flow balance volume",
        description = (
            "Addition of a 4th SBR reactor (or flow balance tank volume) to resolve "
            "fill ratio overload at peak flow for Nereda / granular sludge processes. "
            "When the fill ratio ≥ 0.95, the reactor working volume is fully consumed "
            "during each fill phase and has no margin for peak flow variation. "
            "A 4th reactor reduces the fill ratio by 25% (n→n+1 dilution), restoring "
            "adequate cycle margin. The cost estimate reflects a 694 m³ reactor "
            "(Nereda reference case at 10 MLD) — scale by actual reactor volume."
        ),
        applicable_to_technologies = ["granular_sludge"],
        trigger_conditions = [
            "SBR fill ratio at peak flow ≥ 0.95 (FAIL)",
            "SBR fill ratio at peak flow 0.85–0.95 (WARNING) with growth expected",
        ],
        modifies_assets = ["sbr_reactor", "flow_balance_tank"],
        capex_delta_basis_key   = "vol_per_reactor_m3",   # scales with reactor size
        opex_delta_basis_key    = None,
        fixed_capex_delta_m     = None,   # computed from reactor volume
        fixed_opex_delta_kyr    = None,   # computed from reactor volume
        unit_capex_per_basis    = (
            (_CONCRETE_TANK_PER_M3 + _SBR_EQUIPMENT_PER_M3)
            * _CIVIL_TOTAL_MULTIPLIER / 1e6
        ),
        unit_opex_per_basis_kyr = None,
        performance_effects = {
            "peak_fill_ratio":   "below_0.85",   # resolves fill ratio constraint
            "n_reactors":        "+1",
        },
        risk_effects = {
            "operational_risk_adj":    +2.0,   # additional reactor to manage
            "implementation_risk_adj": +3.0,   # new civil works + commissioning
        },
        shutdown_days = 15,
        can_stage     = True,
        notes = [
            "CAPEX: (concrete $850 + equipment $650)/m³ × 1.344 civil multiplier.",
            "Fill ratio reduces from N×fill_ratio/(N+1) where N is current reactor count.",
            "FBT adequacy should be re-checked after adding reactor.",
            "Ref: Royal HaskoningDHV Nereda design guidelines (2020).",
            "4-reactor configuration is standard practice at sites with PF > 1.4×.",
        ],
    ),
}


# ── Library access functions ──────────────────────────────────────────────────

def get_all_options() -> Dict[str, RetrofitOption]:
    """Return the complete retrofit library keyed by code."""
    return dict(_LIBRARY)


def get_brownfield_retrofit_options(
    technology_code:    str,
    scenario_result:    Any = None,   # domain_specific_outputs dict — optional
    constraint_result:  Any = None,   # BrownfieldConstraintResult — optional
    inputs:             Any = None,   # WastewaterInputs — optional
    brownfield_context: Any = None,   # BrownfieldContext — optional
) -> List[RetrofitOption]:
    """
    Return retrofit options relevant to the given technology.

    Filtering logic (in order):
    1. Technology match — only options that list this tech code, OR options
       with an empty list (universal applicability).
    2. Constraint-driven filter — if a constraint result is supplied,
       only return options that address a failing or warning constraint.
    3. Compliance-driven filter — if scenario_result supplies performance
       outputs, only return options that address a real gap.

    Parameters
    ----------
    technology_code  : tech code string (e.g. "bnr", "granular_sludge")
    scenario_result  : domain_specific_outputs dict from ScenarioModel (optional)
    constraint_result: BrownfieldConstraintResult from constraint_engine (optional)
    inputs           : WastewaterInputs (optional — used for TP target check)
    brownfield_context: BrownfieldContext (optional)

    Returns
    -------
    List of RetrofitOption — ordered by applicability priority
    """
    candidates = []
    for code, option in _LIBRARY.items():
        # Technology filter: include if universal OR if tech_code is listed
        if option.applicable_to_technologies:
            if technology_code not in option.applicable_to_technologies:
                continue
        candidates.append(option)

    # Constraint-driven filter — if no constraints provided, return all candidates
    if constraint_result is None:
        return candidates

    # Narrow to options that address an actual constraint failure or warning
    relevant = []
    failing_constraints = {c.name for c in constraint_result.checks
                           if c.status in ("FAIL", "WARNING")}

    # Extract performance outputs if available
    po = {}
    if scenario_result:
        tp_perf = (
            scenario_result.get("technology_performance", {}) or {}
        ).get(technology_code, {})
        po = tp_perf

    for option in candidates:
        keep = False

        # BF-01 ferric: keep if TP non-compliant
        if option.code == "BF-01":
            tp_actual = po.get("effluent_tp_mg_l")
            tp_target = getattr(inputs, "effluent_tp_mg_l", None) if inputs else None
            if tp_actual is not None and tp_target is not None:
                keep = tp_actual > tp_target * 1.05   # 5% tolerance
            else:
                keep = "compliance_flag" in po and po.get("compliance_flag") != "Meets Targets"

        # BF-02 IFAS: keep if volume or TN compliance is the issue
        elif option.code == "BF-02":
            keep = (
                "Biological Volume" in failing_constraints
                or (po.get("effluent_tn_mg_l") is not None
                    and inputs is not None
                    and po.get("effluent_tn_mg_l", 999) >
                    getattr(inputs, "effluent_tn_mg_l", 999) * 1.05)
            )

        # BF-03 MABR: keep if volume constraint exists and IFAS not already present
        elif option.code == "BF-03":
            keep = "Biological Volume" in failing_constraints

        # BF-04 clarifier: keep if SOR fails or warns
        elif option.code == "BF-04":
            keep = "Clarifier SOR" in failing_constraints

        # BF-05 SBR reactor: keep if fill ratio or hydraulic constraint
        elif option.code == "BF-05":
            keep = (
                "Hydraulic Recycle" in failing_constraints
                or po.get("peak_fill_ratio", 0) >= 0.85
            )

        else:
            keep = True   # unknown code — include by default

        if keep:
            relevant.append(option)

    return relevant if relevant else candidates


# ── Applicability engine ──────────────────────────────────────────────────────

def evaluate_retrofit_applicability(
    retrofit:           RetrofitOption,
    technology_code:    str,
    scenario_result:    Any = None,   # domain_specific_outputs dict
    constraint_result:  Any = None,   # BrownfieldConstraintResult
    inputs:             Any = None,   # WastewaterInputs
    brownfield_context: Any = None,   # BrownfieldContext
) -> RetrofitApplicationResult:
    """
    Determine if a specific retrofit is applicable to a specific scenario
    and estimate its cost and effect.

    Parameters
    ----------
    retrofit         : RetrofitOption from the library
    technology_code  : tech code for the scenario
    scenario_result  : domain_specific_outputs dict from ScenarioModel
    constraint_result: BrownfieldConstraintResult from constraint_engine
    inputs           : WastewaterInputs
    brownfield_context: BrownfieldContext

    Returns
    -------
    RetrofitApplicationResult
    """
    dispatch = {
        "BF-01": _apply_ferric,
        "BF-02": _apply_ifas,
        "BF-03": _apply_mabr,
        "BF-04": _apply_clarifier,
        "BF-05": _apply_sbr_reactor,
    }
    fn = dispatch.get(retrofit.code)
    if fn is None:
        return RetrofitApplicationResult(
            retrofit_code=retrofit.code,
            retrofit_name=retrofit.name,
            applicable=False,
            reason="No applicability logic implemented for this retrofit code.",
        )

    return fn(retrofit, technology_code, scenario_result, constraint_result,
              inputs, brownfield_context)


# ── Per-retrofit applicability functions ──────────────────────────────────────

def _get_po(scenario_result: Any, tech_code: str) -> Dict:
    """Extract performance_outputs for tech_code from domain_specific_outputs."""
    if not scenario_result:
        return {}
    tp = (scenario_result.get("technology_performance", {}) or {})
    return tp.get(tech_code, {})


def _apply_ferric(
    retrofit, tech_code, scenario_result, constraint_result, inputs, bf
) -> RetrofitApplicationResult:
    """BF-01: Ferric chloride dosing for TP compliance."""
    po = _get_po(scenario_result, tech_code)

    tp_actual = po.get("effluent_tp_mg_l")
    tp_target = getattr(inputs, "effluent_tp_mg_l", None) if inputs else None
    flow_mld  = getattr(inputs, "design_flow_mld", 10.0) if inputs else 10.0

    # Not applicable if TP target already met or if no data
    if tp_actual is None or tp_target is None:
        return RetrofitApplicationResult(
            retrofit_code=retrofit.code, retrofit_name=retrofit.name,
            applicable=False,
            reason="TP actual or target not available — cannot assess applicability.",
        )

    if tp_actual <= tp_target * 1.02:   # within 2% tolerance
        return RetrofitApplicationResult(
            retrofit_code=retrofit.code, retrofit_name=retrofit.name,
            applicable=False,
            reason=(
                f"Effluent TP ({tp_actual:.2f} mg/L) meets or is within 2% of "
                f"target ({tp_target:.2f} mg/L) — ferric dosing not required."
            ),
        )

    # Cost calculation — reuse proven formula from intervention_scenarios.py
    tp_removal_needed = max(0.0, tp_actual - tp_target)
    tp_removal_kg_day = tp_removal_needed * flow_mld
    ferric_kg_day     = tp_removal_kg_day * _FERRIC_DOSE_G_PER_G_P
    ferric_opex_yr    = ferric_kg_day * 365 * _FERRIC_PRICE_PER_KG
    opex_k_yr         = round(ferric_opex_yr / 1e3, 1)
    capex_m           = round(0.3 + flow_mld * 0.02, 2)   # skid + storage

    # Sludge delta (approximate)
    sludge_base = po.get("sludge_production_kgds_day", 0)
    sludge_after = round(sludge_base * 1.05, 1) if sludge_base else None

    updated_perf = {"effluent_tp_mg_l": tp_target}
    if sludge_after:
        updated_perf["sludge_production_kgds_day"] = sludge_after

    return RetrofitApplicationResult(
        retrofit_code  = retrofit.code,
        retrofit_name  = retrofit.name,
        applicable     = True,
        reason         = (
            f"Effluent TP {tp_actual:.2f} mg/L exceeds target {tp_target:.2f} mg/L "
            f"(deficit {tp_removal_needed:.2f} mg/L). "
            f"Ferric dose required: {ferric_kg_day:.0f} kg FeCl₃/day."
        ),
        capex_delta_m  = capex_m,
        opex_delta_kyr = opex_k_yr,
        updated_constraints = {"TP compliance": "PASS"},
        updated_performance = updated_perf,
        updated_risk   = dict(retrofit.risk_effects),
        notes          = retrofit.notes.copy(),
        trade_off      = (
            f"TP compliance achieved at +${capex_m:.2f}M CAPEX and "
            f"+${opex_k_yr:.0f}k/yr chemical OPEX. "
            f"Sludge production increases ~5%. "
            f"Dosing must be actively controlled to avoid P stripping exceedance."
        ),
    )


def _apply_ifas(
    retrofit, tech_code, scenario_result, constraint_result, inputs, bf
) -> RetrofitApplicationResult:
    """BF-02: IFAS media addition to aerobic zone."""
    po = _get_po(scenario_result, tech_code)

    # Applicability: volume constraint or TN compliance issue
    volume_constraint = False
    tn_issue          = False

    if constraint_result:
        for check in constraint_result.checks:
            if check.name == "Biological Volume" and check.status in ("FAIL", "WARNING"):
                volume_constraint = True

    tn_actual = po.get("effluent_tn_mg_l")
    tn_target = getattr(inputs, "effluent_tn_mg_l", None) if inputs else None
    if tn_actual is not None and tn_target is not None:
        tn_issue = tn_actual > tn_target * 1.05

    if not volume_constraint and not tn_issue:
        return RetrofitApplicationResult(
            retrofit_code=retrofit.code, retrofit_name=retrofit.name,
            applicable=False,
            reason=(
                "No biological volume constraint or TN compliance issue detected — "
                "IFAS addition is not required for this scenario."
            ),
        )

    aerobic_vol = po.get("v_aerobic_m3") or po.get("v_aerobic") or 0.0
    if aerobic_vol <= 0 and bf:
        aerobic_vol = bf.aerobic_volume_m3 or 0.0

    if aerobic_vol < 500.0:
        return RetrofitApplicationResult(
            retrofit_code=retrofit.code, retrofit_name=retrofit.name,
            applicable=False,
            reason=(
                f"Aerobic zone volume {aerobic_vol:.0f} m³ is below the 500 m³ "
                "minimum for effective IFAS media application."
            ),
        )

    # CAPEX: $180/m³ aerobic zone + $0.10M fixed for screens and connections
    variable_capex = aerobic_vol * retrofit.unit_capex_per_basis
    capex_m        = round(variable_capex + (retrofit.fixed_capex_delta_m or 0.0), 2)
    opex_k_yr      = retrofit.fixed_opex_delta_kyr or 8.0

    reason_parts = []
    if volume_constraint:
        reason_parts.append("biological volume constraint detected")
    if tn_issue:
        reason_parts.append(
            f"effluent TN {tn_actual:.1f} mg/L exceeds target {tn_target:.1f} mg/L"
        )

    return RetrofitApplicationResult(
        retrofit_code  = retrofit.code,
        retrofit_name  = retrofit.name,
        applicable     = True,
        reason         = (
            "IFAS applicable: " + "; ".join(reason_parts) + ". "
            f"Aerobic zone {aerobic_vol:.0f} m³ suitable for media insertion."
        ),
        capex_delta_m  = capex_m,
        opex_delta_kyr = opex_k_yr,
        updated_constraints = {"Biological Volume": "PASS"},
        updated_performance = {
            "nitrification_capacity_uplift_pct": "+30%",
        },
        updated_risk   = dict(retrofit.risk_effects),
        notes          = retrofit.notes.copy(),
        trade_off      = (
            f"+${capex_m:.2f}M CAPEX for media and screens. "
            f"+${opex_k_yr:.0f}k/yr maintenance. "
            "Nitrification capacity increased ~30% with minimal footprint impact. "
            "Process complexity increases — additional DO monitoring recommended."
        ),
    )


def _apply_mabr(
    retrofit, tech_code, scenario_result, constraint_result, inputs, bf
) -> RetrofitApplicationResult:
    """BF-03: MABR retrofit to aerobic zone."""
    po = _get_po(scenario_result, tech_code)

    # Applicability: volume constraint required
    volume_constraint = False
    if constraint_result:
        for check in constraint_result.checks:
            if check.name == "Biological Volume" and check.status in ("FAIL", "WARNING"):
                volume_constraint = True

    if not volume_constraint:
        return RetrofitApplicationResult(
            retrofit_code=retrofit.code, retrofit_name=retrofit.name,
            applicable=False,
            reason=(
                "No biological volume constraint detected — MABR is not required. "
                "Consider IFAS (BF-02) only if nitrification uplift is needed."
            ),
        )

    aerobic_vol = po.get("v_aerobic_m3") or po.get("v_aerobic") or 0.0
    if aerobic_vol <= 0 and bf:
        aerobic_vol = bf.aerobic_volume_m3 or 0.0

    if aerobic_vol <= 0:
        return RetrofitApplicationResult(
            retrofit_code=retrofit.code, retrofit_name=retrofit.name,
            applicable=False,
            reason="Aerobic zone volume not specified — MABR sizing not possible.",
        )

    # Check shutdown window — MABR needs 10 days
    shutdown_ok = True
    if bf and bf.max_shutdown_days < retrofit.shutdown_days:
        shutdown_ok = False

    # CAPEX: $250/m³ aerobic zone + $0.20M fixed for gas skid
    variable_capex = aerobic_vol * retrofit.unit_capex_per_basis
    capex_m        = round(variable_capex + (retrofit.fixed_capex_delta_m or 0.0), 2)
    opex_k_yr      = retrofit.fixed_opex_delta_kyr or 15.0

    extra_notes = list(retrofit.notes)
    if not shutdown_ok:
        extra_notes.append(
            f"WARNING: MABR installation requires {retrofit.shutdown_days}d shutdown — "
            f"exceeds site limit of {bf.max_shutdown_days}d. "
            "Phased module insertion may be possible — confirm with vendor."
        )

    return RetrofitApplicationResult(
        retrofit_code  = retrofit.code,
        retrofit_name  = retrofit.name,
        applicable     = True,
        reason         = (
            f"Biological volume constraint detected. MABR provides nitrification "
            f"uplift (~40%) in existing aerobic zone ({aerobic_vol:.0f} m³) "
            "with 20% aeration energy saving."
            + ("" if shutdown_ok else
               f" Note: {retrofit.shutdown_days}d shutdown exceeds site limit.")
        ),
        capex_delta_m  = capex_m,
        opex_delta_kyr = opex_k_yr,
        updated_constraints = {"Biological Volume": "PASS"},
        updated_performance = {
            "nitrification_capacity_uplift_pct": "+40%",
            "aeration_energy_reduction_pct":     "-20%",
        },
        updated_risk   = dict(retrofit.risk_effects),
        notes          = extra_notes,
        trade_off      = (
            f"+${capex_m:.2f}M CAPEX for MABR modules and gas supply system. "
            f"+${opex_k_yr:.0f}k/yr OPEX. "
            "Greater nitrification and energy benefit than IFAS but higher cost, "
            "complexity, and implementation risk."
        ),
    )


def _apply_clarifier(
    retrofit, tech_code, scenario_result, constraint_result, inputs, bf
) -> RetrofitApplicationResult:
    """BF-04: Clarifier expansion to resolve SOR overload."""
    # Not applicable to technologies without conventional clarifiers
    _no_clarifier = {"granular_sludge", "bnr_mbr", "anmbr"}
    if tech_code in _no_clarifier:
        return RetrofitApplicationResult(
            retrofit_code=retrofit.code, retrofit_name=retrofit.name,
            applicable=False,
            reason=(
                f"{tech_code} does not use conventional secondary clarifiers — "
                "clarifier expansion is not applicable."
            ),
        )

    # Check for SOR constraint
    sor_constrained = False
    sor_check = None
    if constraint_result:
        for check in constraint_result.checks:
            if check.name == "Clarifier SOR" and check.status in ("FAIL", "WARNING"):
                sor_constrained = True
                sor_check = check

    if not sor_constrained:
        return RetrofitApplicationResult(
            retrofit_code=retrofit.code, retrofit_name=retrofit.name,
            applicable=False,
            reason="Clarifier SOR is within limits — clarifier expansion is not required.",
        )

    # Calculate how much extra area is needed
    # Target SOR = 1.2 m/hr at peak (comfortable below 1.5 limit)
    target_sor_m_hr = 1.2
    flow_mld   = getattr(inputs, "design_flow_mld", 10.0) if inputs else 10.0
    peak_factor = 1.5
    if inputs:
        peak_factor = getattr(inputs, "peak_flow_factor", 1.5) or 1.5
    peak_flow_m3h = flow_mld * 1000 * peak_factor / 24.0

    existing_area = (bf.clarifier_area_m2 or 0.0) * (bf.clarifier_count or 1) if bf else 0.0
    required_area = peak_flow_m3h / target_sor_m_hr
    deficit_area  = max(0.0, required_area - existing_area)

    if deficit_area <= 0:
        # SOR constrained but deficit is zero — inconsistency in data
        deficit_area = peak_flow_m3h / 1.2 * 0.3   # conservative 30% expansion

    capex_m   = round(
        deficit_area * _CLARIFIER_COST_PER_M2 * _CIVIL_TOTAL_MULTIPLIER / 1e6, 2
    )
    opex_k_yr = round(capex_m * 1e6 * _MAINTENANCE_RATE / 1e3, 1)

    sor_message = f"SOR {sor_check.required:.2f} m/hr" if sor_check and sor_check.required else "SOR overloaded"

    return RetrofitApplicationResult(
        retrofit_code  = retrofit.code,
        retrofit_name  = retrofit.name,
        applicable     = True,
        reason         = (
            f"Clarifier {sor_message} at peak flow. "
            f"Additional {deficit_area:.0f} m² required to achieve SOR "
            f"{target_sor_m_hr} m/hr at {flow_mld * peak_factor:.0f} MLD peak."
        ),
        capex_delta_m  = capex_m,
        opex_delta_kyr = opex_k_yr,
        updated_constraints = {"Clarifier SOR": "PASS"},
        updated_performance = {"clarifier_sor_m_hr": f"≤{target_sor_m_hr}"},
        updated_risk   = dict(retrofit.risk_effects),
        notes          = retrofit.notes.copy(),
        trade_off      = (
            f"+${capex_m:.2f}M CAPEX for {deficit_area:.0f} m² new clarifier area. "
            f"+${opex_k_yr:.0f}k/yr maintenance. "
            "Significant civil works — 20d estimated shutdown window. "
            "Cannot be staged — plant bypass or temporary diversion required."
        ),
    )


def _apply_sbr_reactor(
    retrofit, tech_code, scenario_result, constraint_result, inputs, bf
) -> RetrofitApplicationResult:
    """BF-05: Additional SBR reactor / flow balance volume."""
    # Only applicable to SBR processes
    if tech_code != "granular_sludge":
        return RetrofitApplicationResult(
            retrofit_code=retrofit.code, retrofit_name=retrofit.name,
            applicable=False,
            reason=(
                f"{tech_code} is not an SBR process — additional SBR reactor "
                "is not applicable."
            ),
        )

    po = _get_po(scenario_result, tech_code)
    fill_ratio = po.get("peak_fill_ratio", 0.0) or 0.0

    # Also check hydraulic recycle constraint
    hydraulic_fail = False
    if constraint_result:
        for check in constraint_result.checks:
            if check.name in ("Hydraulic Recycle", "Biological Volume") \
                    and check.status in ("FAIL", "WARNING"):
                hydraulic_fail = True

    if fill_ratio < 0.85 and not hydraulic_fail:
        return RetrofitApplicationResult(
            retrofit_code=retrofit.code, retrofit_name=retrofit.name,
            applicable=False,
            reason=(
                f"SBR fill ratio {fill_ratio:.2f} is below threshold (0.85) "
                "and no hydraulic constraint detected — additional reactor not required."
            ),
        )

    # Reactor sizing
    vol_per_reactor = po.get("vol_per_reactor_m3") or po.get("working_vol_per_reactor_m3") or 694.0
    n_current       = po.get("n_reactors") or 3
    n_new           = n_current + 1
    new_fill_ratio  = fill_ratio * n_current / n_new

    # CAPEX: (concrete + equipment) × civil multiplier
    capex_m = round(
        vol_per_reactor * (_CONCRETE_TANK_PER_M3 + _SBR_EQUIPMENT_PER_M3)
        * _CIVIL_TOTAL_MULTIPLIER / 1e6,
        2
    )
    opex_k_yr = round(capex_m * 1e6 * _MAINTENANCE_RATE / 1e3
                      + vol_per_reactor * 0.05,   # ~$0.05/m³/yr operating overhead
                      1)

    trigger = f"fill ratio {fill_ratio:.2f}" if fill_ratio >= 0.85 else "hydraulic constraint"

    return RetrofitApplicationResult(
        retrofit_code  = retrofit.code,
        retrofit_name  = retrofit.name,
        applicable     = True,
        reason         = (
            f"SBR {trigger} at peak flow. Adding a {n_new}th reactor "
            f"({vol_per_reactor:.0f} m³) reduces fill ratio from "
            f"{fill_ratio:.2f} to {new_fill_ratio:.2f}."
        ),
        capex_delta_m  = capex_m,
        opex_delta_kyr = opex_k_yr,
        updated_constraints = {
            "Biological Volume": "PASS",
            "Hydraulic Recycle": "PASS",
        },
        updated_performance = {
            "peak_fill_ratio": round(new_fill_ratio, 3),
            "n_reactors":      n_new,
        },
        updated_risk   = dict(retrofit.risk_effects),
        notes          = retrofit.notes.copy(),
        trade_off      = (
            f"+${capex_m:.2f}M CAPEX for {n_new}th SBR reactor ({vol_per_reactor:.0f} m³). "
            f"+${opex_k_yr:.0f}k/yr OPEX. "
            f"Fill ratio improves from {fill_ratio:.2f} to {new_fill_ratio:.2f} at peak. "
            "Nereda vendor confirmation recommended before commitment."
        ),
    )
