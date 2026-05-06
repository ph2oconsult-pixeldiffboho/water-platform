"""
engine/mad.py

Mesophilic Anaerobic Digestion (MAD) model with recuperative thickening,
THP coupling, and reactor-type-aware mixing.

Screening-grade decision support model derived from BioPoint's
RecupModelV3 (post red-team verification). Computes the steady-state
operating point of separate-stream PS/WAS digestion, identifies binding
constraints, and flags geometric infeasibility.

Confidence: 85-91/100 for screening-grade decision support.
NOT appropriate for guaranteed equipment sizing, CFD replacement,
transient upset modelling, or detailed sidestream design.

Entry point:
    result = run_mad(inputs: MADInputs) -> MADResult

Calibration anchors:
    Hydrolysis rates: Pavlostathis & Giraldo-Gomez 1991, Brown 2018
    VSmax: Brown 2018, Metcalf & Eddy 2014
    K_I (acclimated 0.7, conservative 0.4, THP 0.85): Hansen 1998, Wu 2010
    pKa NH4/NH3: 8.95 at 35C
    f_diff TS coefficient (0.15): Abbassi-Guendouz 2012
    f_mix gas anchor (P_crit(4%) = 10 W/m3): Wu 2010, Sajjadi 2016 (CFD)
    Bingham ty(TS) = 0.19 x (TS - 1.17)^1.89: Baudez 2011

Verified against regression-baseline.json (22 scenarios).
ph2o Consulting — BioPoint V1
"""

import math
from dataclasses import dataclass, field, asdict
from typing import Optional, Literal, Dict, Any

# ============================================================
# PHYSICS CONSTANTS — calibrated (do not change without
# regression-test review)
# ============================================================

PKA_NH4_NH3 = 8.95              # pKa of NH4+/NH3 at 35°C
F_DIFF_TS_COEFF = 0.15          # exp(-0.15 × max(0, TS-4)) — Abbassi-Guendouz 2012
F_DIFF_TS_THRESHOLD = 4.0       # below this TS, no diffusion limit
N_RELEASE_FRACTION = 0.70       # fraction of feed N solubilised at full VS dest
BIOGAS_YIELD_M3_PER_KG_VSD = 0.65   # m³ biogas per kg VS destroyed
CHP_HHV_BIOGAS_MJ_PER_M3 = 23.0     # higher heating value
F_MIX_CEILING = 0.95                # ideal CSTR is unreachable
WAS_SRT_KINETIC_CAP_DAYS = 35       # beyond this gives no kinetic benefit
NH3_ITERATION_COUNT = 8             # iterations for NH3 ↔ kinetics convergence

# Mixing system parameters: (P_crit anchor at TS=4%, floor f_mix, exponent)
MIXING_SYSTEM_PARAMS: Dict[str, Dict[str, float]] = {
    "gas":        {"anchor": 10.0, "floor": 0.30, "exp": 1.5},
    "mechanical": {"anchor": 7.0,  "floor": 0.40, "exp": 1.5},
    "draftTube":  {"anchor": 5.0,  "floor": 0.50, "exp": 2.0},
    "staged":     {"anchor": 4.0,  "floor": 0.55, "exp": 2.0},
}

# Minimum stable SRT by acclimation regime
MIN_STABLE_SRT_DAYS: Dict[str, float] = {
    "conservative": 22.0,
    "acclimated":   20.0,
    "thp":          18.0,
    "custom":       20.0,
}

# K_I (g NH3-N/L) by acclimation regime
KI_NH3_DEFAULTS: Dict[str, float] = {
    "conservative": 0.40,
    "acclimated":   0.70,
    "thp":          0.85,
    "custom":       0.70,
}

# Status classification thresholds
STATUS_FAILURE_INHIB_PCT = 25.0
STATUS_FAILURE_FEFF = 0.60
STATUS_FAILURE_SRT = 20.0
STATUS_LIMITING_INHIB_PCT = 20.0
STATUS_LIMITING_FEFF = 0.70
STATUS_LIMITING_SRT = 22.0
STATUS_WATCH_INHIB_PCT = 15.0


# ============================================================
# INPUT SCHEMA
# ============================================================

ReactorType     = Literal["conventional", "advanced"]
MixingSystemType = Literal["gas", "mechanical", "draftTube", "staged"]
NH3Mode         = Literal["conservative", "acclimated", "thp", "custom"]
DigestionMode   = Literal["combined", "separate"]
PretreatmentType = Literal["none", "thp"]
TradeWasteType  = Literal["normal", "industrial"]
PHControl       = Literal["off", "on"]


@dataclass
class MADInputs:
    """
    Inputs to the MAD model.

    All TS, VS, N, and capture values are PERCENTAGES (e.g. 4.0 for 4% TS).
    Volumes are m³, flows are m³/d, masses are tDS/d, kinetic constants are 1/d.
    """

    # Plant geometry
    psV: float                          # PS digester total working volume, m³
    wasV: float                         # WAS digester total working volume, m³

    # Feed mass balance
    psDS: float                         # PS dry solids load, tDS/d
    wasDS: float                        # WAS dry solids load, tDS/d
    psTS: float = 4.0                   # PS feed TS, % (typical 3–5%)
    wasTS: float = 4.0                  # WAS feed TS, % (typical 3–5%)
    psVS: float = 75.0                  # PS volatile solids, % of TS
    wasVS: float = 70.0                 # WAS volatile solids, % of TS
    psN: float = 3.0                    # PS N content, % of DS
    wasN: float = 8.5                   # WAS N content, % of DS

    # Operating mode
    mode: DigestionMode = "separate"
    sepBenefit: float = 1.10            # biogas multiplier for separate mode
    pretreatment: PretreatmentType = "none"
    reactorType: ReactorType = "conventional"

    # Recuperative thickening
    recup: bool = True
    psCap: float = 85.0                 # PS recup-loop centrifuge capture, %
    wasCap: float = 85.0                # WAS recup-loop centrifuge capture, %
    psBeta: float = 1.5                 # PS recirculation ratio
    wasBeta: float = 2.5                # WAS recirculation ratio

    # Final dewatering (separate from recup loop)
    finalDewateringCap: float = 92.0    # final dewatering centrifuge capture, %

    # Mixing
    mixingSystemType: MixingSystemType = "mechanical"
    mixingPower: float = 15.0           # W/m³
    mixingScale: float = 1.00           # P_crit curve-shift

    # Chemistry
    digester_pH: float = 7.25
    pHControl: PHControl = "off"
    nh3Mode: NH3Mode = "acclimated"
    KI_NH3: Optional[float] = None      # custom K_I; if None, derived from nh3Mode
    n_NH3: float = 1.0                  # Hill coefficient
    tradeWaste: TradeWasteType = "normal"

    # Kinetics (literature defaults)
    psK: float = 0.25                   # PS hydrolysis rate, 1/d
    wasK: float = 0.15                  # WAS hydrolysis rate, 1/d
    psVSmax: float = 70.0               # PS max VS destruction, %
    wasVSmax: float = 60.0              # WAS max VS destruction, %

    # Energy parameters
    chpE: float = 40.0                  # CHP electrical efficiency, %
    chpAvail: float = 88.0              # CHP availability, %


# ============================================================
# OUTPUT SCHEMA
# ============================================================

StatusLiteral      = Literal["SAFE", "WATCH", "LIMITING", "FAILURE"]
FeasibilityLiteral = Literal["FEASIBLE", "MARGINAL", "INFEASIBLE"]


@dataclass
class StreamResult:
    """Per-stream (PS or WAS) physics outputs."""
    f_mix: float
    f_diff_base: float
    f_diff_eff: float
    f_eff: float
    HRT_nominal_d: float
    SRT_nominal_d: float
    SRT_eff_d: float
    VS_destruction_pct: float
    NH4_g_per_L: float
    NH3_g_per_L: float
    inhibition_pct: float
    status: StatusLiteral
    primary_constraint: str


@dataclass
class FeasibilityResult:
    """Geometric feasibility check."""
    overall: FeasibilityLiteral
    psFeasibility: FeasibilityLiteral
    wasFeasibility: FeasibilityLiteral
    minStableSRT_d: float
    maxAchievablePsSRT_d: float
    maxAchievableWasSRT_d: float
    typicalCap: float
    typicalBeta: float
    typicalFeff: float


@dataclass
class MADResult:
    """Result of run_mad(inputs)."""

    # Headline status
    status: StatusLiteral
    primary_constraint: str
    feasibility_warning: bool
    confidence_grade: str

    # Per-stream results
    ps: StreamResult
    was: StreamResult

    # Geometric feasibility
    feasibility: FeasibilityResult

    # Energy & gas
    biogas_m3_per_d: float
    biogas_GJ_per_d: float
    elecGross_kW: float
    mixingParasitic_kW: float
    netElec_kW: float

    # Sidestream nitrogen
    centrate_N_kg_per_d: float
    cake_N_kg_per_d: float
    totalN_released_kg_per_d: float

    # Solved operating values
    effective_pH: float
    effective_KI: float

    # Diagnostic flags
    diagnostic_flags: Dict[str, Any] = field(default_factory=dict)

    # BioPoint integration: overrides for energy_system.py
    @property
    def biogas_yield_m3_per_tVS(self) -> float:
        """Convenience: biogas yield in m³/tVS destroyed (for energy_system override)."""
        return BIOGAS_YIELD_M3_PER_KG_VSD * 1000.0


# ============================================================
# PHYSICS — pure functions, no side effects
# ============================================================

def _f_diff_base(ts_pct: float) -> float:
    """
    Baseline diffusion factor. At TS ≤ 4%: exactly 1.0 (Finding 3).
    At TS > 4%: exponential attenuation per Abbassi-Guendouz 2012.
    """
    return math.exp(-F_DIFF_TS_COEFF * max(0.0, ts_pct - F_DIFF_TS_THRESHOLD))


def _f_diff_effective(f_diff_base_val: float, f_mix_val: float) -> float:
    """
    Mixing-coupled diffusion factor.
    f_diff_eff = 1 - (1 - f_diff_base) × (1.7 - 0.7 × f_mix)
    Correctly gives f_diff_eff = 1.0 when f_diff_base = 1.0.
    """
    return max(0.0, 1.0 - (1.0 - f_diff_base_val) * (1.7 - 0.7 * f_mix_val))


def _R_THP(ts_pct: float, thp_active: bool) -> float:
    """THP rheology benefit factor — reduces P_crit at higher TS."""
    if not thp_active:
        return 1.0
    return 0.30 + 0.50 * min(1.0, max(0.0, ts_pct - 2.0) / 8.0)


def _f_mix(
    ts_pct: float,
    power_W_per_m3: float,
    sys_type: str,
    scale: float,
    thp_active: bool,
) -> float:
    """Mixing-derived active volume fraction."""
    sys_p = MIXING_SYSTEM_PARAMS.get(sys_type, MIXING_SYSTEM_PARAMS["mechanical"])
    floor = sys_p["floor"]
    if power_W_per_m3 <= 0.1:
        return floor
    P_crit = (scale * sys_p["anchor"]
               * math.exp(0.55 * (ts_pct - 4.0))
               * _R_THP(ts_pct, thp_active))
    f = floor + (F_MIX_CEILING - floor) / (1.0 + (P_crit / power_W_per_m3) ** sys_p["exp"])
    return min(F_MIX_CEILING, f)


def _NH3_fraction(pH: float) -> float:
    """Free ammonia fraction at given pH and 35°C."""
    return 1.0 / (1.0 + 10.0 ** (PKA_NH4_NH3 - pH))


def _classify_status(inhib_pct: float, f_eff: float, srt_d: float) -> str:
    """Per-stream status classification."""
    if (inhib_pct >= STATUS_FAILURE_INHIB_PCT
            or f_eff < STATUS_FAILURE_FEFF
            or srt_d < STATUS_FAILURE_SRT):
        return "FAILURE"
    if (inhib_pct >= STATUS_LIMITING_INHIB_PCT
            or f_eff < STATUS_LIMITING_FEFF
            or srt_d < STATUS_LIMITING_SRT):
        return "LIMITING"
    if inhib_pct >= STATUS_WATCH_INHIB_PCT:
        return "WATCH"
    return "SAFE"


def _primary_constraint(inhib_pct: float, f_eff: float, srt_d: float) -> str:
    """Identify which constraint axis has smallest margin to failure."""
    candidates = [
        ("FAN/NH3",    STATUS_FAILURE_INHIB_PCT - inhib_pct),
        ("Mixing/f_eff", (f_eff - STATUS_FAILURE_FEFF) * 100),
        ("SRT",         srt_d - STATUS_FAILURE_SRT),
    ]
    candidates.sort(key=lambda x: x[1])
    return candidates[0][0]


def _resolve_pH_and_KI(inputs: MADInputs):
    """Resolve effective pH and K_I after mode and control logic."""
    KI = inputs.KI_NH3 if inputs.KI_NH3 is not None else KI_NH3_DEFAULTS.get(
        inputs.nh3Mode, KI_NH3_DEFAULTS["acclimated"])
    pH = inputs.digester_pH
    if inputs.pHControl == "on" and 7.30 < pH <= 7.55:
        pH = 7.30
    return pH, KI


def _resolve_wasN(inputs: MADInputs) -> float:
    """Apply trade waste uplift if industrial."""
    if inputs.tradeWaste == "industrial" and inputs.wasN < 11.0:
        return max(inputs.wasN, 11.0)
    return inputs.wasN


def _compute_stream(
    *,
    DS_t_per_d: float,
    TS_pct: float,
    VS_pct: float,
    N_pct: float,
    V_m3: float,
    cap_pct: float,
    beta: float,
    K_hyd: float,
    VSmax_pct: float,
    pH: float,
    KI: float,
    n_NH3: float,
    f_mix_val: float,
    f_diff_eff_val: float,
    f_eff: float,
    cap_srt: bool = False,
) -> Dict[str, float]:
    """Compute steady-state for one digester stream with iterative NH3 coupling."""
    feed_flow_m3_per_d = DS_t_per_d * 1000.0 / (TS_pct * 10.0) if TS_pct > 0 else 0.0
    HRT_nominal = V_m3 / feed_flow_m3_per_d if feed_flow_m3_per_d > 0 else 0.0
    srt_mult = 1.0 / max(0.01, (1.0 - cap_pct / 100.0) * beta)
    SRT_nominal = HRT_nominal * srt_mult
    SRT_eff_uncapped = SRT_nominal * f_eff
    SRT_eff = min(WAS_SRT_KINETIC_CAP_DAYS, SRT_eff_uncapped) if cap_srt else SRT_eff_uncapped

    NH3_frac = _NH3_fraction(pH)
    VSmax_frac = VSmax_pct / 100.0
    N_load_t_per_d = DS_t_per_d * N_pct / 100.0

    # Initial guess — no inhibition
    VS_dest_frac = VSmax_frac * (1.0 - math.exp(-K_hyd * SRT_eff))
    NH4 = 0.0
    NH3 = 0.0
    inhib_factor = 1.0
    N_released_t_per_d = 0.0

    for _ in range(NH3_ITERATION_COUNT):
        N_released_t_per_d = N_load_t_per_d * N_RELEASE_FRACTION * (
            VS_dest_frac / VSmax_frac if VSmax_frac > 0 else 0.0)
        active_vol_m3 = V_m3 * f_eff
        if active_vol_m3 > 0:
            NH4 = N_released_t_per_d * 1000.0 * SRT_eff / active_vol_m3
        NH3 = NH4 * NH3_frac
        inhib_factor = 1.0 / (1.0 + (NH3 / KI) ** n_NH3) if KI > 0 else 1.0
        VS_dest_frac = VSmax_frac * (1.0 - math.exp(-K_hyd * inhib_factor * SRT_eff))

    return {
        "feed_flow_m3_per_d": feed_flow_m3_per_d,
        "HRT_nominal":       HRT_nominal,
        "srt_mult":          srt_mult,
        "SRT_nominal":       SRT_nominal,
        "SRT_eff":           SRT_eff,
        "SRT_eff_uncapped":  SRT_eff_uncapped,
        "VS_dest_pct":       VS_dest_frac * 100.0,
        "NH4":               NH4,
        "NH3":               NH3,
        "inhib_pct":         (1.0 - inhib_factor) * 100.0,
        "N_released_t_per_d": N_released_t_per_d,
    }


# ============================================================
# GEOMETRIC FEASIBILITY
# ============================================================

def _geometric_feasibility(
    psHRT_nom: float, wasHRT_nom: float, nh3_mode: str
) -> FeasibilityResult:
    """
    Test whether digester volumes can reach stable SRT under typical operating values.
    Typical: capture 85%, β 2.0, f_eff 0.85.
    """
    typical_cap  = 0.85
    typical_beta = 2.0
    typical_srt_mult = 1.0 / ((1.0 - typical_cap) * typical_beta)
    typical_feff = 0.85
    min_stable = MIN_STABLE_SRT_DAYS.get(nh3_mode, MIN_STABLE_SRT_DAYS["acclimated"])

    max_was_srt = min(WAS_SRT_KINETIC_CAP_DAYS,
                      wasHRT_nom * typical_srt_mult * typical_feff)
    max_ps_srt  = min(WAS_SRT_KINETIC_CAP_DAYS,
                      psHRT_nom  * typical_srt_mult * typical_feff)
    marginal_ratio = 1.20

    def classify(max_srt: float) -> FeasibilityLiteral:
        if max_srt < min_stable:
            return "INFEASIBLE"
        if max_srt < min_stable * marginal_ratio:
            return "MARGINAL"
        return "FEASIBLE"

    ws: FeasibilityLiteral = classify(max_was_srt)
    ps: FeasibilityLiteral = classify(max_ps_srt)
    if ws == "INFEASIBLE" or ps == "INFEASIBLE":
        overall: FeasibilityLiteral = "INFEASIBLE"
    elif ws == "MARGINAL" or ps == "MARGINAL":
        overall = "MARGINAL"
    else:
        overall = "FEASIBLE"

    return FeasibilityResult(
        overall=overall,
        psFeasibility=ps,
        wasFeasibility=ws,
        minStableSRT_d=min_stable,
        maxAchievablePsSRT_d=max_ps_srt,
        maxAchievableWasSRT_d=max_was_srt,
        typicalCap=typical_cap,
        typicalBeta=typical_beta,
        typicalFeff=typical_feff,
    )


# ============================================================
# ENTRY POINT
# ============================================================

def run_mad(inputs: MADInputs) -> MADResult:
    """
    Run the MAD model. Returns MADResult with headline status, per-stream
    physics, geometric feasibility, energy outputs, and sidestream N.
    """
    pH, KI = _resolve_pH_and_KI(inputs)
    wasN_eff = _resolve_wasN(inputs)
    thp_active = inputs.pretreatment == "thp"

    # THP kinetic boost
    psK_eff  = inputs.psK  * 1.35 if thp_active else inputs.psK
    wasK_eff = inputs.wasK * 1.35 if thp_active else inputs.wasK
    psN_eff  = inputs.psN  * 1.15 if thp_active else inputs.psN
    wasN_eff = wasN_eff    * 1.15 if thp_active else wasN_eff

    # Mixing & diffusion
    psFmix  = _f_mix(inputs.psTS,  inputs.mixingPower, inputs.mixingSystemType,
                     inputs.mixingScale, thp_active)
    wasFmix = _f_mix(inputs.wasTS, inputs.mixingPower, inputs.mixingSystemType,
                     inputs.mixingScale, thp_active)
    psFdb  = _f_diff_base(inputs.psTS)
    wasFdb = _f_diff_base(inputs.wasTS)
    if thp_active:
        psFdb  = min(1.0, psFdb  * min(1.15, 1.0 + 0.15 * max(0, inputs.psTS  - 4) / 10))
        wasFdb = min(1.0, wasFdb * min(1.15, 1.0 + 0.15 * max(0, inputs.wasTS - 4) / 10))
    psFdiff  = _f_diff_effective(psFdb, psFmix)
    wasFdiff = _f_diff_effective(wasFdb, wasFmix)
    psFeff  = psFmix  * psFdiff
    wasFeff = wasFmix * wasFdiff

    # Per-stream physics
    ps_phys = _compute_stream(
        DS_t_per_d=inputs.psDS, TS_pct=inputs.psTS, VS_pct=inputs.psVS,
        N_pct=psN_eff, V_m3=inputs.psV,
        cap_pct=inputs.psCap, beta=inputs.psBeta,
        K_hyd=psK_eff, VSmax_pct=inputs.psVSmax,
        pH=pH, KI=KI, n_NH3=inputs.n_NH3,
        f_mix_val=psFmix, f_diff_eff_val=psFdiff, f_eff=psFeff,
        cap_srt=False,
    )
    was_phys = _compute_stream(
        DS_t_per_d=inputs.wasDS, TS_pct=inputs.wasTS, VS_pct=inputs.wasVS,
        N_pct=wasN_eff, V_m3=inputs.wasV,
        cap_pct=inputs.wasCap, beta=inputs.wasBeta,
        K_hyd=wasK_eff, VSmax_pct=inputs.wasVSmax,
        pH=pH, KI=KI, n_NH3=inputs.n_NH3,
        f_mix_val=wasFmix, f_diff_eff_val=wasFdiff, f_eff=wasFeff,
        cap_srt=True,
    )

    # Per-stream status
    ps_status  = _classify_status(ps_phys["inhib_pct"],  psFeff,  ps_phys["SRT_eff"])
    was_status = _classify_status(was_phys["inhib_pct"], wasFeff, was_phys["SRT_eff"])
    ps_primary  = _primary_constraint(ps_phys["inhib_pct"],  psFeff,  ps_phys["SRT_eff"])
    was_primary = _primary_constraint(was_phys["inhib_pct"], wasFeff, was_phys["SRT_eff"])

    ps_result = StreamResult(
        f_mix=psFmix, f_diff_base=psFdb, f_diff_eff=psFdiff, f_eff=psFeff,
        HRT_nominal_d=ps_phys["HRT_nominal"], SRT_nominal_d=ps_phys["SRT_nominal"],
        SRT_eff_d=ps_phys["SRT_eff"], VS_destruction_pct=ps_phys["VS_dest_pct"],
        NH4_g_per_L=ps_phys["NH4"], NH3_g_per_L=ps_phys["NH3"],
        inhibition_pct=ps_phys["inhib_pct"], status=ps_status,
        primary_constraint=ps_primary,
    )
    was_result = StreamResult(
        f_mix=wasFmix, f_diff_base=wasFdb, f_diff_eff=wasFdiff, f_eff=wasFeff,
        HRT_nominal_d=was_phys["HRT_nominal"], SRT_nominal_d=was_phys["SRT_nominal"],
        SRT_eff_d=was_phys["SRT_eff"], VS_destruction_pct=was_phys["VS_dest_pct"],
        NH4_g_per_L=was_phys["NH4"], NH3_g_per_L=was_phys["NH3"],
        inhibition_pct=was_phys["inhib_pct"], status=was_status,
        primary_constraint=was_primary,
    )

    # Overall status
    status_order = {"SAFE": 0, "WATCH": 1, "LIMITING": 2, "FAILURE": 3}
    if status_order[was_status] >= status_order[ps_status]:
        overall_status: StatusLiteral = was_status
        overall_primary = was_primary
    else:
        overall_status = ps_status
        overall_primary = ps_primary

    # Geometric feasibility
    feasibility = _geometric_feasibility(
        ps_phys["HRT_nominal"], was_phys["HRT_nominal"], inputs.nh3Mode)

    # Biogas & energy
    sep_mult = inputs.sepBenefit if inputs.mode == "separate" else 1.0
    biogas_m3_per_d = (
        inputs.psDS  * (inputs.psVS  / 100.0) * (ps_phys["VS_dest_pct"]  / 100.0)
        + inputs.wasDS * (inputs.wasVS / 100.0) * (was_phys["VS_dest_pct"] / 100.0)
    ) * 1000.0 * BIOGAS_YIELD_M3_PER_KG_VSD * sep_mult

    biogas_GJ_per_d  = biogas_m3_per_d * CHP_HHV_BIOGAS_MJ_PER_M3 / 1000.0
    elec_gross_kW    = (biogas_GJ_per_d * 1000.0 / 86.4) * (inputs.chpE / 100.0) * (inputs.chpAvail / 100.0)
    mixing_kW        = inputs.mixingPower * (inputs.psV + inputs.wasV) / 1000.0
    net_elec_kW      = elec_gross_kW - mixing_kW

    # Sidestream N
    psN_load  = inputs.psDS  * psN_eff  / 100.0
    wasN_load = inputs.wasDS * wasN_eff / 100.0
    psN_released  = ps_phys["N_released_t_per_d"]
    wasN_released = was_phys["N_released_t_per_d"]
    total_N_released    = psN_released + wasN_released
    total_N_particulate = (psN_load + wasN_load) * (1.0 - N_RELEASE_FRACTION)

    final_dewatering_frac = inputs.finalDewateringCap / 100.0
    centrate_N_t_per_d = (total_N_released    * (1.0 - final_dewatering_frac)
                           + total_N_particulate * 0.10)
    cake_N_t_per_d     = (total_N_released    * final_dewatering_frac
                           + total_N_particulate * 0.90)

    # Diagnostic flags
    diagnostic_flags = {
        "geometric_infeasibility": feasibility.overall == "INFEASIBLE",
        "geometric_marginal":      feasibility.overall == "MARGINAL",
        "biogas_blind_warning":    was_phys["SRT_eff"] > 30.0,
        "high_TS_diffusion_active": inputs.psTS > 4.0 or inputs.wasTS > 4.0,
        "thp_active":              thp_active,
        "pH_control_engaged":      (inputs.pHControl == "on"
                                    and inputs.digester_pH > 7.30
                                    and inputs.digester_pH <= 7.55),
        "industrial_trade_waste":  inputs.tradeWaste == "industrial",
    }

    return MADResult(
        status=overall_status,
        primary_constraint=overall_primary,
        feasibility_warning=(feasibility.overall == "INFEASIBLE"),
        confidence_grade="screening-grade",
        ps=ps_result,
        was=was_result,
        feasibility=feasibility,
        biogas_m3_per_d=biogas_m3_per_d,
        biogas_GJ_per_d=biogas_GJ_per_d,
        elecGross_kW=elec_gross_kW,
        mixingParasitic_kW=mixing_kW,
        netElec_kW=net_elec_kW,
        centrate_N_kg_per_d=centrate_N_t_per_d * 1000.0,
        cake_N_kg_per_d=cake_N_t_per_d * 1000.0,
        totalN_released_kg_per_d=total_N_released * 1000.0,
        effective_pH=pH,
        effective_KI=KI,
        diagnostic_flags=diagnostic_flags,
    )


def run_mad_dict(inputs_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Dict-in, dict-out wrapper for orchestrators."""
    inputs = MADInputs(**inputs_dict)
    result = run_mad(inputs)
    return asdict(result)
