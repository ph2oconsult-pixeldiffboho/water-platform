"""
Sludge Character Engine.
Characterises sludge from per-capita generation basis and sludge type.
Outputs four indices used for pathway selection:
  - Volume intensity (m³/t DS — how much water to move)
  - Energy potential (relative biogas yield tier)
  - Handling difficulty (physical manageability)
  - Variability risk (process stability exposure)

These indices feed directly into the Adaptive Pathway Engine
to weight pathway stage selection.

Reference: M&E 5th ed.; WEF MOP 8; WSAA biosolids guidance.
ph2o Consulting — BioPoint v1
"""

from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# SLUDGE TYPE REFERENCE PROPERTIES
# M&E Table 13-5 — typical ranges
# ---------------------------------------------------------------------------

SLUDGE_TYPE_REFERENCE = {
    "WAS": {
        "gDS_EP_d_typical": 35.0,       # g DS / equivalent person / day
        "gDS_EP_d_range": (20, 55),
        "ts_pct_typical": 1.5,
        "ts_pct_range": (0.6, 3.0),
        "vs_ts_ratio": 0.80,
        "biogas_yield_m3_kgVSd": 0.48,  # operational mid — 190-240 Nm3/tODM ref
        "methane_pct": 62.0,
        "dewaterability": "POOR",        # EPS matrix — centrifuge intensive
        "variability": "HIGH",           # Bulking, foaming, seasonal variation
        "pathogen_load": "HIGH",
        "odour_risk": "MODERATE",
        "description": "Waste Activated Sludge — high water content, poor dewaterability, "
                       "variable composition, high pathogen load.",
    },
    "PS": {
        "gDS_EP_d_typical": 55.0,
        "gDS_EP_d_range": (40, 75),
        "ts_pct_typical": 4.5,
        "ts_pct_range": (3.0, 6.0),
        "vs_ts_ratio": 0.78,
        "biogas_yield_m3_kgVSd": 0.63,  # operational mid — 315-400 Nm3/tODM ref
        "methane_pct": 67.0,
        "dewaterability": "GOOD",        # Gravity thickens well
        "variability": "LOW",
        "pathogen_load": "HIGH",
        "odour_risk": "HIGH",            # Fresh PS — rapid septicity
        "description": "Primary Sludge — higher VS content, good dewaterability, "
                       "higher biogas yield, septicity risk if stored.",
    },
    "PS_WAS": {
        "gDS_EP_d_typical": 90.0,       # Combined
        "gDS_EP_d_range": (60, 130),
        "ts_pct_typical": 3.0,
        "ts_pct_range": (1.5, 5.0),
        "vs_ts_ratio": 0.79,
        "biogas_yield_m3_kgVSd": 0.55,  # blend mid of PS(0.63) and WAS(0.48) at 50:50
        "methane_pct": 64.5,
        "dewaterability": "MODERATE",
        "variability": "MODERATE",
        "pathogen_load": "HIGH",
        "odour_risk": "MODERATE",
        "description": "Primary + WAS blend — intermediate properties; "
                       "blend ratio is the key operating variable.",
    },
    "DIGESTED": {
        "gDS_EP_d_typical": 50.0,       # Post-MAD (VS reduction ~45-57%)
        "gDS_EP_d_range": (30, 70),
        "ts_pct_typical": 2.5,
        "ts_pct_range": (1.5, 4.0),
        "vs_ts_ratio": 0.55,            # Post-digestion VS/TS lower
        "biogas_yield_m3_kgVSd": 0.0,   # Already digested
        "methane_pct": 0.0,
        "dewaterability": "MODERATE",
        "variability": "LOW",            # Digestion buffers variability
        "pathogen_load": "LOW",          # Class B stabilised
        "odour_risk": "LOW",
        "description": "Digested sludge — stabilised, reduced VS, lower pathogen load, "
                       "suitable for land application subject to regulatory class.",
    },
    "AGS": {
        "gDS_EP_d_typical": 25.0,       # AGS inherently low sludge yield
        "gDS_EP_d_range": (15, 40),
        "ts_pct_typical": 2.5,
        "ts_pct_range": (1.0, 4.0),
        "vs_ts_ratio": 0.75,
        "biogas_yield_m3_kgVSd": 0.55,  # Denser granules — slightly lower yield
        "methane_pct": 62.0,
        "dewaterability": "GOOD",        # Dense granules settle and dewater well
        "variability": "LOW",            # Stable granular structure
        "pathogen_load": "HIGH",
        "odour_risk": "LOW",
        "description": "Aerobic Granular Sludge — compact, good settleability, "
                       "lower sludge production than CAS. Emerging data set.",
    },
}

# ---------------------------------------------------------------------------
# INDEX THRESHOLDS
# ---------------------------------------------------------------------------

VOLUME_INTENSITY_BANDS = [
    (0,    50,  "LOW",      "Dense sludge — manageable volume per tonne DS."),
    (50,   150, "MODERATE", "Moderate water content — standard handling."),
    (150,  400, "HIGH",     "High water content — large volumes to move and treat."),
    (400,  1e9, "CRITICAL", "Very dilute — pumping and storage dominate cost."),
]

# ---------------------------------------------------------------------------
# DATACLASS
# ---------------------------------------------------------------------------

@dataclass
class SludgeCharacter:
    """Sludge characterisation output — indices and narrative."""

    # --- INPUTS ---
    sludge_type: str = ""
    gDS_EP_d: float = 0.0              # g DS / equivalent person / day
    population_EP: Optional[float] = None
    ds_pct: float = 0.0                # Current DS %
    vs_ts_ratio: float = 0.0

    # --- DERIVED PRODUCTION ---
    ts_kg_d: float = 0.0               # kg DS/d
    ts_t_yr: float = 0.0
    volume_m3_d: float = 0.0           # Sludge volume at given DS%
    volume_intensity_m3_per_tDS: float = 0.0

    # --- INDICES (all rated LOW/MODERATE/HIGH/CRITICAL) ---
    volume_intensity: str = ""
    volume_intensity_note: str = ""
    energy_potential: str = ""         # "NONE" | "LOW" | "MODERATE" | "HIGH"
    energy_potential_note: str = ""
    handling_difficulty: str = ""
    handling_difficulty_note: str = ""
    variability_risk: str = ""
    variability_risk_note: str = ""

    # --- PATHWAY AFFINITY ---
    # Which stages are strongly indicated by sludge character
    stage_affinities: dict = field(default_factory=dict)
    # {stage: "ESSENTIAL"|"BENEFICIAL"|"OPTIONAL"|"NOT_INDICATED"}

    # --- REFERENCE ---
    type_description: str = ""
    odour_risk: str = ""
    pathogen_load: str = ""
    dewaterability: str = ""
    gDS_EP_d_typical: float = 0.0
    gDS_EP_d_range: tuple = field(default_factory=tuple)
    per_capita_assessment: str = ""    # Is gDS/EP/d within expected range?


# ---------------------------------------------------------------------------
# MAIN ENGINE
# ---------------------------------------------------------------------------

def characterise_sludge(
    sludge_type: str,
    ds_pct: float,
    gDS_EP_d: Optional[float] = None,
    population_EP: Optional[float] = None,
    ts_kg_d_direct: Optional[float] = None,
) -> SludgeCharacter:
    """
    Characterise sludge from type + DS% + per-capita or direct load.
    At least one of (gDS_EP_d + population_EP) or ts_kg_d_direct must be provided.
    """
    ref = SLUDGE_TYPE_REFERENCE.get(sludge_type, SLUDGE_TYPE_REFERENCE["PS_WAS"])

    # --- RESOLVE TS LOAD ---
    if ts_kg_d_direct and ts_kg_d_direct > 0:
        ts_kg_d = ts_kg_d_direct
        # Back-calculate gDS/EP/d if population known
        if population_EP and population_EP > 0:
            gDS_EP_d_calc = ts_kg_d * 1000.0 / population_EP
        else:
            gDS_EP_d_calc = gDS_EP_d or ref["gDS_EP_d_typical"]
        pop = population_EP
    elif gDS_EP_d and population_EP:
        ts_kg_d = gDS_EP_d * population_EP / 1000.0  # g/EP/d × EP / 1000 = kg/d
        gDS_EP_d_calc = gDS_EP_d
        pop = population_EP
    else:
        # Fall back to typical with no population — return reference profile only
        ts_kg_d = 0.0
        gDS_EP_d_calc = gDS_EP_d or ref["gDS_EP_d_typical"]
        pop = population_EP

    ts_t_yr = ts_kg_d * 365.0 / 1000.0

    # --- VOLUME ---
    ds_frac = ds_pct / 100.0 if ds_pct > 0 else 0.01
    density = 1010.0  # kg/m³ wet sludge
    wet_mass_kg_d = ts_kg_d / ds_frac if ds_frac > 0 else 0.0
    volume_m3_d = wet_mass_kg_d / density

    # Volume intensity: m³ per tonne DS
    vol_intensity = (volume_m3_d / (ts_kg_d / 1000.0)) if ts_kg_d > 0 else (1000.0 / ds_pct) if ds_pct > 0 else 0.0

    # --- INDEX: VOLUME INTENSITY ---
    vi_label, vi_note = _classify_band(vol_intensity, VOLUME_INTENSITY_BANDS)

    # --- INDEX: ENERGY POTENTIAL ---
    ep_label, ep_note = _energy_potential(sludge_type, ref)

    # --- INDEX: HANDLING DIFFICULTY ---
    hd_label, hd_note = _handling_difficulty(sludge_type, ds_pct, ref)

    # --- INDEX: VARIABILITY RISK ---
    vr_label, vr_note = _variability_risk(sludge_type, ref)

    # --- PATHWAY AFFINITIES ---
    affinities = _pathway_affinities(sludge_type, vi_label, ep_label, hd_label, vr_label)

    # --- PER-CAPITA ASSESSMENT ---
    lo, hi = ref["gDS_EP_d_range"]
    if gDS_EP_d_calc < lo * 0.8:
        pc_note = f"⚠️ Low: {gDS_EP_d_calc:.0f} gDS/EP/d below expected range ({lo:.0f}–{hi:.0f}). Check measurement basis."
    elif gDS_EP_d_calc > hi * 1.2:
        pc_note = f"⚠️ High: {gDS_EP_d_calc:.0f} gDS/EP/d above expected range ({lo:.0f}–{hi:.0f}). Verify — may indicate infiltration or industrial load."
    else:
        pc_note = f"✓ Within expected range ({lo:.0f}–{hi:.0f} gDS/EP/d) for {sludge_type}."

    return SludgeCharacter(
        sludge_type=sludge_type,
        gDS_EP_d=gDS_EP_d_calc,
        population_EP=pop,
        ds_pct=ds_pct,
        vs_ts_ratio=ref["vs_ts_ratio"],
        ts_kg_d=round(ts_kg_d, 1),
        ts_t_yr=round(ts_t_yr, 1),
        volume_m3_d=round(volume_m3_d, 1),
        volume_intensity_m3_per_tDS=round(vol_intensity, 1),
        volume_intensity=vi_label,
        volume_intensity_note=vi_note,
        energy_potential=ep_label,
        energy_potential_note=ep_note,
        handling_difficulty=hd_label,
        handling_difficulty_note=hd_note,
        variability_risk=vr_label,
        variability_risk_note=vr_note,
        stage_affinities=affinities,
        type_description=ref["description"],
        odour_risk=ref["odour_risk"],
        pathogen_load=ref["pathogen_load"],
        dewaterability=ref["dewaterability"],
        gDS_EP_d_typical=ref["gDS_EP_d_typical"],
        gDS_EP_d_range=ref["gDS_EP_d_range"],
        per_capita_assessment=pc_note,
    )


# ---------------------------------------------------------------------------
# INDEX CLASSIFIERS
# ---------------------------------------------------------------------------

def _classify_band(value: float, bands: list) -> tuple:
    for lo, hi, label, note in bands:
        if lo <= value < hi:
            return label, note
    return "LOW", ""


def _energy_potential(sludge_type: str, ref: dict) -> tuple:
    yield_val = ref["biogas_yield_m3_kgVSd"]
    ch4 = ref["methane_pct"]
    if sludge_type == "DIGESTED":
        return "NONE", "Already digested — no further anaerobic energy potential."
    if yield_val >= 0.72:
        return "HIGH",     f"High biogas yield ({yield_val:.2f} m³/kgVS, {ch4:.0f}% CH₄) — strong CHP basis."
    elif yield_val >= 0.58:
        return "MODERATE", f"Moderate biogas yield ({yield_val:.2f} m³/kgVS, {ch4:.0f}% CH₄) — viable CHP."
    elif yield_val >= 0.40:
        return "LOW",      f"Low biogas yield ({yield_val:.2f} m³/kgVS) — CHP marginal at small scale."
    else:
        return "NONE",     "Negligible biogas potential — thermal route may be more appropriate."


def _handling_difficulty(sludge_type: str, ds_pct: float, ref: dict) -> tuple:
    dew = ref["dewaterability"]
    base = {"GOOD": 0, "MODERATE": 1, "POOR": 2}.get(dew, 1)
    # DS% adjusts — very low DS increases difficulty
    ds_penalty = 2 if ds_pct < 1.0 else (1 if ds_pct < 2.0 else 0)
    total = base + ds_penalty
    if total >= 3:
        return "HIGH",     f"Difficult — {dew.lower()} dewaterability at {ds_pct:.1f}% DS. Polymer conditioning essential."
    elif total >= 1:
        return "MODERATE", f"Moderate — {dew.lower()} dewaterability. Standard centrifuge/belt press applicable."
    else:
        return "LOW",      f"Good dewaterability at {ds_pct:.1f}% DS — gravity thickening viable."


def _variability_risk(sludge_type: str, ref: dict) -> tuple:
    var = ref["variability"]
    notes = {
        "HIGH":     "High variability — WAS quality responds to load changes, temperature, and process upsets. "
                    "Design for peak load; digester buffering is important.",
        "MODERATE": "Moderate variability — blend ratio is the key variable. "
                    "Consistent PS quality but WAS fraction introduces seasonal variation.",
        "LOW":      "Low variability — stable sludge character. Digestion or AGS granular structure buffers fluctuations.",
    }
    return var, notes.get(var, "")


def _pathway_affinities(sludge_type: str, vi: str, ep: str, hd: str, vr: str) -> dict:
    """
    Return stage affinities for the 4-stage pathway stack.
    ESSENTIAL / BENEFICIAL / OPTIONAL / NOT_INDICATED
    """
    affinities = {}

    # Stage 1: Stabilisation (AD)
    if sludge_type == "DIGESTED":
        affinities["stabilisation"] = "NOT_INDICATED"
    elif ep in ["HIGH", "MODERATE"]:
        affinities["stabilisation"] = "ESSENTIAL"
    else:
        affinities["stabilisation"] = "BENEFICIAL"

    # Stage 2: Enhancement (THP)
    if sludge_type in ["WAS", "PS_WAS"] and hd in ["HIGH", "MODERATE"]:
        affinities["enhancement_thp"] = "BENEFICIAL"    # THP breaks EPS → better dewatering
    elif sludge_type == "PS":
        affinities["enhancement_thp"] = "OPTIONAL"      # PS already dewaters reasonably
    elif sludge_type == "DIGESTED":
        affinities["enhancement_thp"] = "NOT_INDICATED"
    else:
        affinities["enhancement_thp"] = "OPTIONAL"

    # Stage 3: Volume reduction (drying)
    if vi in ["HIGH", "CRITICAL"]:
        affinities["drying"] = "ESSENTIAL"
    elif vi == "MODERATE":
        affinities["drying"] = "BENEFICIAL"
    else:
        affinities["drying"] = "OPTIONAL"

    # Stage 4: Final thermal treatment
    if vr == "HIGH" or hd == "HIGH":
        affinities["thermal"] = "BENEFICIAL"    # High variability → thermal more robust
    elif ep == "NONE":
        affinities["thermal"] = "BENEFICIAL"    # No energy potential → thermal makes sense
    else:
        affinities["thermal"] = "OPTIONAL"

    return affinities
