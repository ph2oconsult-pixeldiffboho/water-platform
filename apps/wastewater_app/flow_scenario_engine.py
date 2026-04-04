"""
apps/wastewater_app/flow_scenario_engine.py

Flow Scenario Framework — pure calculation engine.
No Streamlit, no I/O, no side effects.

Computes adjusted flow, concentration, and load for four scenario types:
  - Dry Weather Average (DWA)
  - Dry Weather Peak / Diurnal (DWP)
  - Average Wet Weather Flow (AWWF)
  - Peak Wet Weather Flow (PWWF)

Does NOT recalculate biological treatment model.
Reads base values from domain_inputs and computes overlays.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ── Scenario type constants ───────────────────────────────────────────────────

SCENARIO_DWA  = "Dry Weather Average"
SCENARIO_DWP  = "Dry Weather Peak (Diurnal)"
SCENARIO_AWWF = "Average Wet Weather Flow (AWWF)"
SCENARIO_PWWF = "Peak Wet Weather Flow (PWWF)"

FLOW_SCENARIO_TYPES = [SCENARIO_DWA, SCENARIO_DWP, SCENARIO_AWWF, SCENARIO_PWWF]


# ── Input dataclass ───────────────────────────────────────────────────────────

@dataclass
class WetWeatherProfile:
    rise_hr:     float = 4.0
    plateau_hr:  float = 12.0
    recession_hr: float = 8.0

    @property
    def total_duration_hr(self) -> float:
        return self.rise_hr + self.plateau_hr + self.recession_hr

    def summary(self) -> str:
        return (f"Rise {self.rise_hr:.0f}h → Plateau {self.plateau_hr:.0f}h → "
                f"Recession {self.recession_hr:.0f}h "
                f"(total {self.total_duration_hr:.0f}h)")


@dataclass
class FlowScenarioInputs:
    """
    All user-adjustable parameters for the flow scenario framework.
    Stored in domain_inputs under key "flow_scenario".
    """
    # Scenario selection
    scenario_type: str = SCENARIO_DWA

    # Base DWA values (read from domain_inputs — not overridden here)
    base_flow_mld:     float = 10.0
    base_bod_mg_l:     float = 250.0
    base_tss_mg_l:     float = 280.0
    base_tn_mg_l:      float = 45.0
    base_tp_mg_l:      float = 7.0
    base_nh4_mg_l:     float = 35.0

    # Hydraulic capacity (from engineering outputs or user-entered)
    hydraulic_capacity_mld: Optional[float] = None   # design flow (same as base for a sized plant)
    clarifier_area_m2:      Optional[float] = None   # from technology performance outputs

    # ── DWP ──────────────────────────────────────────────────────────────
    dwp_factor: float = 1.5

    # ── AWWF ─────────────────────────────────────────────────────────────
    awwf_factor:                 float = 3.0
    awwf_ii_contribution_pct:   float = 40.0   # % of flow from I/I
    awwf_dilution_factor:        float = 0.6    # concentration multiplier (dilution)
    awwf_duration_hr:            float = 24.0
    awwf_constant_mass_load:     bool  = False
    awwf_profile: WetWeatherProfile = field(default_factory=lambda: WetWeatherProfile(4, 12, 8))

    # ── PWWF ─────────────────────────────────────────────────────────────
    pwwf_factor:                 float = 5.0
    pwwf_ii_contribution_pct:   float = 70.0
    pwwf_dilution_factor:        float = 0.35
    pwwf_duration_hr:            float = 12.0
    pwwf_constant_mass_load:     bool  = False
    pwwf_profile: WetWeatherProfile = field(default_factory=lambda: WetWeatherProfile(2, 4, 6))

    # ── First flush (applies to AWWF and PWWF) ───────────────────────────
    first_flush_enabled:     bool  = False
    first_flush_duration_hr: float = 2.0
    first_flush_conc_mult:   float = 1.35   # concentration multiplier during first flush


# ── Result dataclass ──────────────────────────────────────────────────────────

@dataclass
class FlowPhase:
    """One phase of a wet weather event (first flush, main event)."""
    name:              str
    duration_hr:       float
    flow_mld:          float
    dilution_factor:   float
    bod_mg_l:          float
    tss_mg_l:          float
    tn_mg_l:           float
    tp_mg_l:           float
    nh4_mg_l:          float

    @property
    def bod_kg_d(self) -> float:
        return round(self.bod_mg_l * self.flow_mld, 1)

    @property
    def tn_kg_d(self) -> float:
        return round(self.tn_mg_l * self.flow_mld, 1)

    @property
    def tp_kg_d(self) -> float:
        return round(self.tp_mg_l * self.flow_mld, 1)


@dataclass
class FlowScenarioResult:
    """
    Complete output from the flow scenario engine.
    All fields needed for WaterPoint compatibility.
    """
    # ── Identity ──────────────────────────────────────────────────────────
    scenario_type:    str
    base_flow_mld:    float

    # ── Adjusted values ───────────────────────────────────────────────────
    adjusted_flow_mld:       float
    flow_factor:             float
    adjusted_bod_mg_l:       float
    adjusted_tss_mg_l:       float
    adjusted_tn_mg_l:        float
    adjusted_tp_mg_l:        float
    adjusted_nh4_mg_l:       float
    dilution_factor:         float

    # ── Loads (kg/d = mg/L × MLD) ────────────────────────────────────────
    adjusted_bod_kg_d:  float
    adjusted_tss_kg_d:  float
    adjusted_tn_kg_d:   float
    adjusted_tp_kg_d:   float

    # ── Load assumption ───────────────────────────────────────────────────
    load_assumption: str   # "constant load" | "diluted load" | "first flush then diluted"

    # ── Hydraulic stress ─────────────────────────────────────────────────
    hydraulic_capacity_mld:    Optional[float]
    hydraulic_utilisation_pct: Optional[float]
    hydraulic_stress_status:   str   # OK / Tightening / Overload
    overflow_flag:             bool
    bypass_risk_flag:          bool

    # ── Biological stress ─────────────────────────────────────────────────
    biological_load_kg_d:       float   # BOD kg/d as primary biological indicator
    base_biological_load_kg_d:  float
    biological_load_ratio:      float   # adjusted / base
    biological_stress_status:   str   # OK / Elevated / Critical

    # ── Clarifier stress ─────────────────────────────────────────────────
    clarifier_area_m2:         Optional[float]
    clarifier_sor_m_hr:        Optional[float]
    clarifier_stress_flag:     bool
    clarifier_stress_status:   str

    # ── Wet weather profile ───────────────────────────────────────────────
    wet_weather_duration_hr:   Optional[float]
    wet_weather_profile:       Optional[str]
    phases:                    list   # List[FlowPhase]

    # ── First flush ───────────────────────────────────────────────────────
    first_flush_enabled:   bool
    first_flush_duration_hr: Optional[float]

    # ── I/I ───────────────────────────────────────────────────────────────
    ii_contribution_pct:   Optional[float]


# ── Engine ────────────────────────────────────────────────────────────────────

def calculate(fsi: FlowScenarioInputs) -> FlowScenarioResult:
    """
    Calculate adjusted flow, concentration, load, and stress for one scenario.
    """
    st = fsi.scenario_type
    base_flow = fsi.base_flow_mld

    # ── 1. Adjusted flow and dilution factor ──────────────────────────────
    if st == SCENARIO_DWA:
        adj_flow      = base_flow
        flow_factor   = 1.0
        dil_factor    = 1.0
        const_mass    = False
        duration_hr   = None
        profile_str   = None
        phases        = []
        ii_pct        = None

    elif st == SCENARIO_DWP:
        adj_flow      = base_flow * fsi.dwp_factor
        flow_factor   = fsi.dwp_factor
        dil_factor    = 1.0   # diurnal peak — no dilution, same concentration
        const_mass    = False
        duration_hr   = None
        profile_str   = None
        phases        = []
        ii_pct        = None

    elif st == SCENARIO_AWWF:
        adj_flow    = base_flow * fsi.awwf_factor
        flow_factor = fsi.awwf_factor
        dil_factor  = 1.0 if fsi.awwf_constant_mass_load else fsi.awwf_dilution_factor
        const_mass  = fsi.awwf_constant_mass_load
        duration_hr = fsi.awwf_duration_hr
        profile_str = fsi.awwf_profile.summary()
        ii_pct      = fsi.awwf_ii_contribution_pct
        phases      = _build_wet_phases(fsi, adj_flow, dil_factor, is_pwwf=False)

    else:  # PWWF
        adj_flow    = base_flow * fsi.pwwf_factor
        flow_factor = fsi.pwwf_factor
        dil_factor  = 1.0 if fsi.pwwf_constant_mass_load else fsi.pwwf_dilution_factor
        const_mass  = fsi.pwwf_constant_mass_load
        duration_hr = fsi.pwwf_duration_hr
        profile_str = fsi.pwwf_profile.summary()
        ii_pct      = fsi.pwwf_ii_contribution_pct
        phases      = _build_wet_phases(fsi, adj_flow, dil_factor, is_pwwf=True)

    # ── 2. Adjusted concentrations ────────────────────────────────────────
    adj_bod  = round(fsi.base_bod_mg_l  * dil_factor, 1)
    adj_tss  = round(fsi.base_tss_mg_l  * dil_factor, 1)
    adj_tn   = round(fsi.base_tn_mg_l   * dil_factor, 1)
    adj_tp   = round(fsi.base_tp_mg_l   * dil_factor, 1)
    adj_nh4  = round(fsi.base_nh4_mg_l  * dil_factor, 1)

    # ── 3. Loads (kg/d) ───────────────────────────────────────────────────
    # Load = conc (mg/L) × flow (MLD) → kg/d
    adj_bod_kg  = round(adj_bod * adj_flow, 1)
    adj_tss_kg  = round(adj_tss * adj_flow, 1)
    adj_tn_kg   = round(adj_tn  * adj_flow, 1)
    adj_tp_kg   = round(adj_tp  * adj_flow, 1)
    base_bod_kg = round(fsi.base_bod_mg_l * base_flow, 1)

    # Load assumption label
    if st in (SCENARIO_DWA, SCENARIO_DWP):
        load_assumption = "constant load (dry weather)"
    elif const_mass:
        load_assumption = "constant mass load (hydraulic increase only)"
    elif fsi.first_flush_enabled and st in (SCENARIO_AWWF, SCENARIO_PWWF):
        load_assumption = "first flush then diluted load"
    else:
        load_assumption = "diluted load (I/I dominant)"

    # ── 4. Hydraulic stress ───────────────────────────────────────────────
    hyd_cap  = fsi.hydraulic_capacity_mld or base_flow
    hyd_util = (adj_flow / hyd_cap * 100) if hyd_cap > 0 else None
    if hyd_util is None:
        hyd_status = "Unknown"
    elif adj_flow <= hyd_cap * 1.05:
        hyd_status = "OK"
    elif adj_flow <= hyd_cap * 1.20:
        hyd_status = "Tightening"
    else:
        hyd_status = "Overload"

    overflow_flag   = adj_flow > hyd_cap * 1.0 if hyd_cap else False
    bypass_flag     = adj_flow > hyd_cap * 1.10 if hyd_cap else False

    # ── 5. Clarifier SOR ─────────────────────────────────────────────────
    clar_area = fsi.clarifier_area_m2
    sor = None
    clar_stress_flag   = False
    clar_stress_status = "Unknown"

    if clar_area and clar_area > 0:
        # SOR (m/hr) = flow (m³/hr) / area (m²)
        peak_m3hr = adj_flow * 1000 / 24
        sor = round(peak_m3hr / clar_area, 3)
        if sor > 1.5:
            clar_stress_flag   = True
            clar_stress_status = f"FAIL — SOR {sor:.2f} m/hr > 1.5 m/hr limit"
        elif sor > 1.2:
            clar_stress_flag   = True
            clar_stress_status = f"WARNING — SOR {sor:.2f} m/hr (limit 1.5 m/hr)"
        else:
            clar_stress_status = f"OK — SOR {sor:.2f} m/hr"

    # ── 6. Biological stress ──────────────────────────────────────────────
    bio_ratio = round(adj_bod_kg / base_bod_kg, 2) if base_bod_kg > 0 else 1.0
    if bio_ratio <= 1.10:
        bio_status = "OK"
    elif bio_ratio <= 1.40:
        bio_status = "Elevated"
    else:
        bio_status = "Critical"

    return FlowScenarioResult(
        scenario_type             = st,
        base_flow_mld             = base_flow,
        adjusted_flow_mld         = round(adj_flow, 2),
        flow_factor               = round(flow_factor, 2),
        adjusted_bod_mg_l         = adj_bod,
        adjusted_tss_mg_l         = adj_tss,
        adjusted_tn_mg_l          = adj_tn,
        adjusted_tp_mg_l          = adj_tp,
        adjusted_nh4_mg_l         = adj_nh4,
        dilution_factor           = round(dil_factor, 3),
        adjusted_bod_kg_d         = adj_bod_kg,
        adjusted_tss_kg_d         = adj_tss_kg,
        adjusted_tn_kg_d          = adj_tn_kg,
        adjusted_tp_kg_d          = adj_tp_kg,
        load_assumption           = load_assumption,
        hydraulic_capacity_mld    = hyd_cap,
        hydraulic_utilisation_pct = round(hyd_util, 1) if hyd_util is not None else None,
        hydraulic_stress_status   = hyd_status,
        overflow_flag             = overflow_flag,
        bypass_risk_flag          = bypass_flag,
        biological_load_kg_d      = adj_bod_kg,
        base_biological_load_kg_d = base_bod_kg,
        biological_load_ratio     = bio_ratio,
        biological_stress_status  = bio_status,
        clarifier_area_m2         = clar_area,
        clarifier_sor_m_hr        = sor,
        clarifier_stress_flag     = clar_stress_flag,
        clarifier_stress_status   = clar_stress_status,
        wet_weather_duration_hr   = duration_hr,
        wet_weather_profile       = profile_str,
        phases                    = phases,
        first_flush_enabled       = fsi.first_flush_enabled,
        first_flush_duration_hr   = fsi.first_flush_duration_hr if fsi.first_flush_enabled else None,
        ii_contribution_pct       = ii_pct,
    )


def _build_wet_phases(
    fsi: FlowScenarioInputs,
    adj_flow: float,
    main_dil: float,
    is_pwwf: bool,
) -> list:
    """Build FlowPhase list for wet weather events."""
    phases = []
    b = fsi   # shorthand

    def _conc(base, dil):
        return round(base * dil, 1)

    if b.first_flush_enabled:
        ff_dil = b.first_flush_conc_mult   # > 1: first flush is more concentrated
        phases.append(FlowPhase(
            name            = "First Flush",
            duration_hr     = b.first_flush_duration_hr,
            flow_mld        = adj_flow,
            dilution_factor = ff_dil,
            bod_mg_l        = _conc(b.base_bod_mg_l, ff_dil),
            tss_mg_l        = _conc(b.base_tss_mg_l, ff_dil),
            tn_mg_l         = _conc(b.base_tn_mg_l,  ff_dil),
            tp_mg_l         = _conc(b.base_tp_mg_l,  ff_dil),
            nh4_mg_l        = _conc(b.base_nh4_mg_l, ff_dil),
        ))
        main_duration = (b.pwwf_duration_hr if is_pwwf else b.awwf_duration_hr) - b.first_flush_duration_hr
    else:
        main_duration = b.pwwf_duration_hr if is_pwwf else b.awwf_duration_hr

    phases.append(FlowPhase(
        name            = "Main Wet Weather",
        duration_hr     = max(0.0, main_duration),
        flow_mld        = adj_flow,
        dilution_factor = main_dil,
        bod_mg_l        = _conc(b.base_bod_mg_l, main_dil),
        tss_mg_l        = _conc(b.base_tss_mg_l, main_dil),
        tn_mg_l         = _conc(b.base_tn_mg_l,  main_dil),
        tp_mg_l         = _conc(b.base_tp_mg_l,  main_dil),
        nh4_mg_l        = _conc(b.base_nh4_mg_l, main_dil),
    ))
    return phases


def to_domain_inputs_dict(fsi: FlowScenarioInputs) -> dict:
    """
    Serialise FlowScenarioInputs to a flat dict for storage in domain_inputs["flow_scenario"].
    """
    return {
        "scenario_type":           fsi.scenario_type,
        "dwp_factor":              fsi.dwp_factor,
        "awwf_factor":             fsi.awwf_factor,
        "awwf_ii_pct":             fsi.awwf_ii_contribution_pct,
        "awwf_dilution":           fsi.awwf_dilution_factor,
        "awwf_duration_hr":        fsi.awwf_duration_hr,
        "awwf_constant_mass":      fsi.awwf_constant_mass_load,
        "awwf_rise_hr":            fsi.awwf_profile.rise_hr,
        "awwf_plateau_hr":         fsi.awwf_profile.plateau_hr,
        "awwf_recession_hr":       fsi.awwf_profile.recession_hr,
        "pwwf_factor":             fsi.pwwf_factor,
        "pwwf_ii_pct":             fsi.pwwf_ii_contribution_pct,
        "pwwf_dilution":           fsi.pwwf_dilution_factor,
        "pwwf_duration_hr":        fsi.pwwf_duration_hr,
        "pwwf_constant_mass":      fsi.pwwf_constant_mass_load,
        "pwwf_rise_hr":            fsi.pwwf_profile.rise_hr,
        "pwwf_peak_hr":            fsi.pwwf_profile.plateau_hr,
        "pwwf_recession_hr":       fsi.pwwf_profile.recession_hr,
        "first_flush_enabled":     fsi.first_flush_enabled,
        "first_flush_duration_hr": fsi.first_flush_duration_hr,
        "first_flush_conc_mult":   fsi.first_flush_conc_mult,
    }


def from_domain_inputs_dict(d: dict, base: FlowScenarioInputs) -> FlowScenarioInputs:
    """
    Restore FlowScenarioInputs from a stored dict, falling back to base defaults.
    """
    def _g(key, default):
        v = d.get(key)
        return v if v is not None else default

    base.scenario_type               = _g("scenario_type",     base.scenario_type)
    base.dwp_factor                  = _g("dwp_factor",         base.dwp_factor)
    base.awwf_factor                 = _g("awwf_factor",        base.awwf_factor)
    base.awwf_ii_contribution_pct   = _g("awwf_ii_pct",        base.awwf_ii_contribution_pct)
    base.awwf_dilution_factor        = _g("awwf_dilution",      base.awwf_dilution_factor)
    base.awwf_duration_hr            = _g("awwf_duration_hr",   base.awwf_duration_hr)
    base.awwf_constant_mass_load     = _g("awwf_constant_mass", base.awwf_constant_mass_load)
    base.awwf_profile.rise_hr        = _g("awwf_rise_hr",       base.awwf_profile.rise_hr)
    base.awwf_profile.plateau_hr     = _g("awwf_plateau_hr",    base.awwf_profile.plateau_hr)
    base.awwf_profile.recession_hr   = _g("awwf_recession_hr",  base.awwf_profile.recession_hr)
    base.pwwf_factor                 = _g("pwwf_factor",        base.pwwf_factor)
    base.pwwf_ii_contribution_pct   = _g("pwwf_ii_pct",        base.pwwf_ii_contribution_pct)
    base.pwwf_dilution_factor        = _g("pwwf_dilution",      base.pwwf_dilution_factor)
    base.pwwf_duration_hr            = _g("pwwf_duration_hr",   base.pwwf_duration_hr)
    base.pwwf_constant_mass_load     = _g("pwwf_constant_mass", base.pwwf_constant_mass_load)
    base.pwwf_profile.rise_hr        = _g("pwwf_rise_hr",       base.pwwf_profile.rise_hr)
    base.pwwf_profile.plateau_hr     = _g("pwwf_peak_hr",       base.pwwf_profile.plateau_hr)
    base.pwwf_profile.recession_hr   = _g("pwwf_recession_hr",  base.pwwf_profile.recession_hr)
    base.first_flush_enabled         = _g("first_flush_enabled",     base.first_flush_enabled)
    base.first_flush_duration_hr     = _g("first_flush_duration_hr", base.first_flush_duration_hr)
    base.first_flush_conc_mult       = _g("first_flush_conc_mult",   base.first_flush_conc_mult)
    return base
