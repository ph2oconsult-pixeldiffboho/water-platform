"""
apps/wastewater_app/waterpoint_adapter.py

Adapter layer between the Water Utility Planning Platform and WaterPoint.

Reads existing ScenarioModel outputs — never recalculates.
All field extractions are defensive: missing data yields None.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ── Data structure ────────────────────────────────────────────────────────────

@dataclass
class WPLoad:
    bod_kg_d:  Optional[float] = None
    tss_kg_d:  Optional[float] = None
    tn_kg_d:   Optional[float] = None
    tp_kg_d:   Optional[float] = None
    nh4_kg_d:  Optional[float] = None


@dataclass
class WPDesignCapacity:
    hydraulic_mld:     Optional[float] = None
    biological_kg_d:   Optional[float] = None  # BOD design load
    solids_kg_d:       Optional[float] = None


@dataclass
class WPProcessLimits:
    aeration_capacity:         Optional[float] = None   # kW installed
    clarifier_capacity_m2:     Optional[float] = None   # m²
    solids_handling_kg_d:      Optional[float] = None
    nutrient_removal_capacity: Optional[str]   = None   # descriptive
    biosolids_capacity:        Optional[str]   = None   # descriptive


@dataclass
class WPOutputs:
    capex_estimate:   Optional[float] = None   # $M
    opex_estimate:    Optional[float] = None   # k$/yr
    carbon_estimate:  Optional[float] = None   # tCO₂e/yr


@dataclass
class WaterPointInput:
    scenario_name:    str = ""
    plant_name:       str = ""
    location:         str = ""
    average_flow_mld: Optional[float] = None
    peak_flow_mld:    Optional[float] = None
    technology_code:  str = ""
    technology_name:  str = ""
    current_load:     WPLoad              = field(default_factory=WPLoad)
    design_capacity:  WPDesignCapacity    = field(default_factory=WPDesignCapacity)
    process_limits:   WPProcessLimits     = field(default_factory=WPProcessLimits)
    outputs:          WPOutputs           = field(default_factory=WPOutputs)
    # Raw effluent values for compliance checks
    effluent_tn_mg_l:  Optional[float] = None
    effluent_tp_mg_l:  Optional[float] = None
    effluent_nh4_mg_l: Optional[float] = None
    # Targets from domain_inputs
    tn_target_mg_l:  Optional[float] = None
    tp_target_mg_l:  Optional[float] = None
    nh4_target_mg_l: Optional[float] = None
    # Stress proxies
    aeration_kwh_day:   Optional[float] = None
    o2_demand_kg_day:   Optional[float] = None
    sludge_kgds_day:    Optional[float] = None
    reactor_volume_m3:  Optional[float] = None
    clarifier_area_m2:  Optional[float] = None
    # Flow scenario (from page_02b)
    flow_scenario_type:       Optional[str]  = None
    flow_adjusted_flow_mld:   Optional[float]= None
    flow_adjusted_bod_kg_d:   Optional[float]= None
    flow_hydraulic_capacity:  Optional[float]= None
    flow_overflow_flag:       bool           = False
    flow_clarifier_stress:    bool           = False
    flow_bypass_risk:         bool           = False
    flow_first_flush_enabled: bool           = False
    flow_first_flush_duration_hr: Optional[float] = None
    flow_wet_weather_duration_hr: Optional[float] = None
    flow_wet_weather_profile: Optional[str]  = None
    # MABR OxyFAS/OxyFILM fields (technology_code == "mabr_oxyfas" / "mabr_oxyfilm")
    mabr_enabled:               bool           = False
    mabr_mode:                  Optional[str]   = None   # "oxyfas" or "oxyfilm"
    mabr_module_count:          Optional[int]   = None
    mabr_membrane_area_m2:      Optional[float] = None
    mabr_oxygen_capacity_kgod:  Optional[float] = None
    mabr_airflow_nm3h:          Optional[float] = None
    mabr_enriched_air_enabled:  bool           = False
    mabr_pure_oxygen_enabled:   bool           = False
    mabr_blowers_pressure_mbar: Optional[float] = None
    mabr_biofilm_control_enabled: bool         = True
    mabr_scour_control_enabled: bool           = True
    mabr_mixing_mode:           Optional[str]   = None   # "airlift" / "supplemental" / "none"
    mabr_hybrid_with_as:        bool           = True    # OxyFAS = hybrid
    mabr_clarifier_dependent:   bool           = True
    mabr_shrouded_modules:      bool           = True
    # Hybrid system context (shared by MABR, MOB, future technologies)
    mlss_mgL:                   Optional[float] = None
    clarifier_available:        bool           = True
    clarifier_stress_flag:      bool           = False
    ras_ratio:                  Optional[float] = None
    internal_recycle_ratio:     Optional[float] = None
    cod_to_n_ratio:             Optional[float] = None
    external_carbon_dosing_ld:  Optional[float] = None
    # MOB Intensified SBR fields (technology_code == "migrate_indense")
    mob_enabled:          bool           = False
    migrate_enabled:      bool           = False
    indense_enabled:      bool           = False
    sbr_count:            Optional[int]   = None
    sbr_volume_m3:        Optional[float] = None
    sbr_fill_volume_m3:   Optional[float] = None
    cycle_time_normal_hr: Optional[float] = None
    cycle_time_storm_hr:  Optional[float] = None
    migrate_fill_fraction_pct:          Optional[float] = None
    migrate_surface_area_addition_m2_per_m3: Optional[float] = None
    migrate_total_surface_area_m2:      Optional[float] = None
    indense_pressure_psig:              Optional[float] = None
    indense_overflow_flow_pct:          Optional[float] = None
    indense_underflow_flow_pct:         Optional[float] = None
    indense_overflow_solids_pct:        Optional[float] = None
    indense_underflow_solids_pct:       Optional[float] = None
    carrier_screening_available:        bool           = True
    selector_operational:               bool           = True
    # Nereda-specific fields (populated when technology_code == "granular_sludge")
    nereda_enabled:      bool           = False
    nereda_fbt_m3:       Optional[float] = None   # balance tank volume
    nereda_dwf_cycle_min: Optional[float]= None   # DWF cycle time (minutes)
    nereda_n_reactors:   Optional[int]   = None   # number of reactors
    # Data quality tracker
    missing_fields: List[str] = field(default_factory=list)


# ── Adapter function ──────────────────────────────────────────────────────────

def build_waterpoint_input(
    scenario:  Any,   # ScenarioModel
    project:   Any = None,
) -> WaterPointInput:
    """
    Map one ScenarioModel's outputs into a WaterPointInput.

    Never raises.  Missing data is recorded in missing_fields.
    """
    inp = WaterPointInput()
    missing: List[str] = []

    # ── Metadata ──────────────────────────────────────────────────────────
    inp.scenario_name = getattr(scenario, "scenario_name", "") or ""

    if project:
        meta = getattr(project, "metadata", None)
        if meta:
            inp.plant_name = getattr(meta, "plant_name", "") or ""
            inp.location   = getattr(meta, "author", "")  # best proxy available

    # ── Flows ─────────────────────────────────────────────────────────────
    di = getattr(scenario, "domain_inputs", None) or {}
    inp.average_flow_mld = _g(di, "design_flow_mld") or _g(scenario, "design_flow_mld")
    inp.peak_flow_mld    = _g(di, "peak_flow_mld") or _g(scenario, "peak_flow_mld")
    if inp.peak_flow_mld is None and inp.average_flow_mld:
        pf = _g(di, "peak_flow_factor") or 1.5
        inp.peak_flow_mld = round(inp.average_flow_mld * pf, 2)

    # ── Technology ────────────────────────────────────────────────────────
    tp = getattr(scenario, "treatment_pathway", None)
    if tp and getattr(tp, "technology_sequence", None):
        inp.technology_code = tp.technology_sequence[0]

    dso = getattr(scenario, "domain_specific_outputs", None) or {}
    eng = dso.get("engineering_summary", {}) or {}
    perf_all = dso.get("technology_performance", {}) or {}
    tc  = inp.technology_code
    tp_sc = perf_all.get(tc, {}) or {}

    # ── Influent loads (kg/d) — derive from flow × concentration ─────────
    flow = inp.average_flow_mld or 0.0
    ea   = getattr(getattr(scenario, "assumptions", None), "engineering_assumptions", {}) or {}

    def _load_kg_d(param_key: str, ea_key: str) -> Optional[float]:
        """mg/L × MLD → kg/d (= mg/L × m³/MLD × 1000 L/m³ / 1e6 → simplified to mg/L × MLD)."""
        conc = _g(ea, ea_key) or _g(di, ea_key)
        if conc and flow:
            return round(conc * flow, 1)
        return None

    inp.current_load = WPLoad(
        bod_kg_d  = _load_kg_d("influent_bod_mg_l", "influent_bod_mg_l"),
        tss_kg_d  = _load_kg_d("influent_tss_mg_l", "influent_tss_mg_l"),
        tn_kg_d   = _load_kg_d("influent_tkn_mg_l", "influent_tkn_mg_l"),
        tp_kg_d   = _load_kg_d("influent_tp_mg_l",  "influent_tp_mg_l"),
        nh4_kg_d  = _load_kg_d("influent_nh4_mg_l", "influent_nh4_mg_l"),
    )

    # ── Design capacity ───────────────────────────────────────────────────
    inp.design_capacity = WPDesignCapacity(
        hydraulic_mld   = inp.average_flow_mld,
        biological_kg_d = inp.current_load.bod_kg_d,
        solids_kg_d     = _g(eng, "total_sludge_kgds_day") or _g(tp_sc, "sludge_production_kgds_day"),
    )

    # ── Process limits (from technology performance outputs) ──────────────
    aer_kw = _g(tp_sc, "aeration_energy_kwh_day")
    if aer_kw:
        aer_kw = round(aer_kw / 24 * 1.30, 1)   # operational → installed kW
    inp.process_limits = WPProcessLimits(
        aeration_capacity        = aer_kw,
        clarifier_capacity_m2    = _g(tp_sc, "clarifier_area_m2"),
        solids_handling_kg_d     = _g(eng, "total_sludge_kgds_day"),
        nutrient_removal_capacity = (
            "BNR — biological N and P removal" if "bnr" in tc or "mabr" in tc
            else "IFAS/MBBR — partial N removal" if "ifas" in tc
            else "MBR — enhanced N removal" if "mbr" in tc
            else "AGS — integrated N and P removal" if "granular" in tc
            else "Standard biological"
        ),
        biosolids_capacity = (
            f"{round(_g(tp_sc,'sludge_production_tds_yr') or 0,0):.0f} tDS/yr"
            if _g(tp_sc, "sludge_production_tds_yr") else None
        ),
    )

    # ── Cost / carbon outputs ─────────────────────────────────────────────
    cr = getattr(scenario, "cost_result", None)
    car = getattr(scenario, "carbon_result", None)
    inp.outputs = WPOutputs(
        capex_estimate  = round(cr.capex_total / 1e6, 2)       if cr  else None,
        opex_estimate   = round(cr.opex_annual / 1e3, 1)        if cr  else None,
        carbon_estimate = round(getattr(car, "net_tco2e_yr", 0) or 0) if car else None,
    )

    # ── Effluent performance ──────────────────────────────────────────────
    inp.effluent_tn_mg_l  = _g(tp_sc, "effluent_tn_mg_l")
    inp.effluent_tp_mg_l  = _g(tp_sc, "effluent_tp_mg_l")
    inp.effluent_nh4_mg_l = _g(tp_sc, "effluent_nh4_mg_l")

    # ── Targets ───────────────────────────────────────────────────────────
    inp.tn_target_mg_l  = _g(di, "effluent_tn_mg_l")
    inp.tp_target_mg_l  = _g(di, "effluent_tp_mg_l")
    inp.nh4_target_mg_l = _g(di, "effluent_nh4_mg_l")

    # ── Stress proxies ────────────────────────────────────────────────────
    inp.aeration_kwh_day  = _g(tp_sc, "aeration_energy_kwh_day") or _g(eng, "total_energy_kwh_day")
    inp.o2_demand_kg_day  = _g(tp_sc, "o2_demand_kg_day")
    inp.sludge_kgds_day   = _g(tp_sc, "sludge_production_kgds_day") or _g(eng, "total_sludge_kgds_day")
    inp.reactor_volume_m3 = _g(tp_sc, "reactor_volume_m3")
    inp.clarifier_area_m2 = _g(tp_sc, "clarifier_area_m2")

    # ── Missing fields audit ──────────────────────────────────────────────
    if not inp.average_flow_mld:  missing.append("design_flow_mld")
    if not inp.current_load.bod_kg_d: missing.append("influent_bod_mg_l")
    if not inp.reactor_volume_m3: missing.append("reactor_volume_m3")
    if not inp.effluent_tn_mg_l:  missing.append("effluent_tn_mg_l")
    if not inp.outputs.capex_estimate: missing.append("capex")

    # ── Nereda-specific fields ────────────────────────────────────────────
    if inp.technology_code == "granular_sludge":
        inp.nereda_enabled      = True
        inp.nereda_fbt_m3       = _g(tp_sc, "fbt_volume_m3") or _g(tp_sc, "fbt_provided_m3")
        inp.nereda_dwf_cycle_min = (_g(tp_sc, "cycle_time_hours") or 5.0) * 60.0
        inp.nereda_n_reactors   = int(tp_sc.get("n_reactors") or 2)

    # ── Flow scenario overlay ─────────────────────────────────────────────
    fs_stored = di.get("flow_scenario") or {}
    if fs_stored:
        try:
            from apps.wastewater_app.flow_scenario_engine import (
                FlowScenarioInputs, from_domain_inputs_dict, calculate
            )
            fsi = FlowScenarioInputs(
                base_flow_mld  = inp.average_flow_mld or 10.0,
                base_bod_mg_l  = _g(di, "influent_bod_mg_l") or 250.0,
                base_tss_mg_l  = _g(di, "influent_tss_mg_l") or 280.0,
                base_tn_mg_l   = _g(di, "influent_tkn_mg_l") or 45.0,
                base_tp_mg_l   = _g(di, "influent_tp_mg_l")  or 7.0,
                base_nh4_mg_l  = _g(di, "influent_nh4_mg_l") or 35.0,
                hydraulic_capacity_mld = inp.average_flow_mld,
                clarifier_area_m2      = inp.clarifier_area_m2,
            )
            fsi = from_domain_inputs_dict(fs_stored, fsi)
            fsr = calculate(fsi)
            inp.flow_scenario_type       = fsr.scenario_type
            inp.flow_adjusted_flow_mld   = fsr.adjusted_flow_mld
            inp.flow_adjusted_bod_kg_d   = fsr.adjusted_bod_kg_d
            inp.flow_hydraulic_capacity  = fsr.hydraulic_capacity_mld
            inp.flow_overflow_flag       = fsr.overflow_flag
            inp.flow_clarifier_stress    = fsr.clarifier_stress_flag
            inp.flow_bypass_risk         = fsr.bypass_risk_flag
            inp.flow_first_flush_enabled = fsr.first_flush_enabled
            inp.flow_first_flush_duration_hr = fsr.first_flush_duration_hr
            inp.flow_wet_weather_duration_hr = fsr.wet_weather_duration_hr
            inp.flow_wet_weather_profile     = fsr.wet_weather_profile
        except Exception:
            pass   # flow scenario enrichment must never break WaterPoint

    inp.missing_fields = missing
    return inp


def _g(obj: Any, key: str) -> Optional[float]:
    """Safely get a numeric value from a dict or object attribute."""
    if obj is None:
        return None
    if isinstance(obj, dict):
        v = obj.get(key)
    else:
        v = getattr(obj, key, None)
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
