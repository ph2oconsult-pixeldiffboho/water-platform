"""
BioPoint V1 — Pyrolysis Operating Envelope Engine (v25A12).

Models pyrolysis as a continuously tunable process with explicit trade-offs
between energy recovery, carbon product value, and contaminant destruction.

Core principle: there is no single optimal pyrolysis condition.
The recommended operating mode depends on the stated objective.

Temperature response functions derived from:
  - Lehmann & Joseph (2015) Biochar for Environmental Management
  - IBI Biochar Standards v2.1 (2015)
  - Zhao et al. (2013) — pyrolysis of sewage sludge
  - Tomczyk et al. (2020) — biochar yield and properties review
  - Hogue (2021) — PFAS destruction in pyrolysis
  - US EPA (2022) — PFAS thermal treatment guidance
  - Woolf et al. (2010) — carbon stability (R50 index)
  - Garcia-Nunez et al. (2017) — fast vs slow pyrolysis comparison

Heating rate reference:
  Slow pyrolysis:    1–10°C/min   → maximises char yield
  Medium pyrolysis:  10–100°C/min → balanced char + gas
  Fast pyrolysis:    >100°C/min   → maximises bio-oil/gas, minimises char

ph2o Consulting — BioPoint V1
"""

from dataclasses import dataclass, field
from typing import Optional
import math


# ---------------------------------------------------------------------------
# TEMPERATURE RESPONSE FUNCTIONS
# ---------------------------------------------------------------------------
# All functions take temperature in °C and return values on a 0-1 or % scale.
# Based on published response curves fitted to sludge pyrolysis literature.

def biochar_yield_pct(temp_c: float, heating_rate: str = "medium",
                       feedstock: str = "biosolids") -> float:
    """
    Biochar yield as % of dry feed mass.
    Decreases with temperature. Strongly affected by heating rate.
    Feedstock type shifts the baseline yield.

    Literature range (sludge, slow pyrolysis):
      300°C → ~55-65% yield
      500°C → ~35-45%
      700°C → ~22-30%
      800°C → ~18-25%
    """
    # Base curve for biosolids slow pyrolysis (Zhao et al., 2013)
    base = 72.0 * math.exp(-0.0022 * temp_c) + 10.0
    base = max(12.0, min(65.0, base))

    # Heating rate adjustment
    hr_adj = {"slow": 1.0, "medium": 0.88, "fast": 0.72}
    base *= hr_adj.get(heating_rate, 0.88)

    # Feedstock adjustment
    fs_adj = {"biosolids": 1.0, "biomass": 0.85, "mixed_waste": 0.93}
    base *= fs_adj.get(feedstock, 1.0)

    return round(max(10.0, min(65.0, base)), 1)


def fixed_carbon_pct(temp_c: float, feedstock: str = "biosolids") -> float:
    """
    Fixed carbon content of biochar (% of biochar mass).
    Increases with temperature as volatiles are driven off.
    Biosolids have inherently lower fixed carbon due to high ash content.

    Literature range (sludge biochar):
      300°C → 20-30% fixed C
      500°C → 35-50%
      700°C → 50-65%
      800°C → 60-70%
    """
    # Logistic growth with temperature
    fc = 70.0 / (1.0 + math.exp(-0.007 * (temp_c - 550))) + 15.0

    # Biosolids have high ash content — lower fixed C than biomass
    fs_adj = {"biosolids": 0.75, "biomass": 1.0, "mixed_waste": 0.88}
    fc *= fs_adj.get(feedstock, 0.75)

    return round(max(15.0, min(70.0, fc)), 1)


def volatile_matter_pct(temp_c: float, heating_rate: str = "medium") -> float:
    """
    Volatile matter in biochar (% of biochar mass).
    Decreases with temperature and heating rate.
    VM = 100 - fixed_carbon - ash (simplified; ash varies by feedstock).

    Literature: VM inversely related to stability and fixed C content.
    """
    # Exponential decay
    vm = 60.0 * math.exp(-0.004 * temp_c) + 5.0

    # Fast pyrolysis leaves more uncracked volatiles in char
    hr_adj = {"slow": 0.9, "medium": 1.0, "fast": 1.15}
    vm *= hr_adj.get(heating_rate, 1.0)

    return round(max(5.0, min(60.0, vm)), 1)


def carbon_stability_index(temp_c: float) -> float:
    """
    Carbon stability proxy (R50 index, 0-1 scale).
    R50 represents resistance to oxidative degradation — proxy for
    mean residence time (MRT) in soil.

    Literature:
      R50 < 0.50 → labile carbon (MRT years to decades)
      R50 0.50-0.70 → stable (MRT decades-centuries)
      R50 > 0.70 → highly stable (MRT centuries+)

    Biochar from sludge at >600°C typically R50 > 0.55 (Woolf et al., 2010).
    """
    # Logistic function — stability increases with temperature, plateaus
    r50 = 0.80 / (1.0 + math.exp(-0.008 * (temp_c - 520))) + 0.15
    return round(max(0.15, min(0.85, r50)), 3)


def pyrogas_energy_fraction(temp_c: float, heating_rate: str = "medium",
                              feedstock: str = "biosolids") -> float:
    """
    Fraction of feedstock energy recovered in pyrogas/syngas (0-1 scale).
    Increases with temperature (more volatile release, more combustibles in gas).
    Also increases with heating rate (fast pyrolysis → more oil/gas, less char).

    The complement (1 - gas_fraction) stays in char as chemical energy + sensible heat.
    """
    # Base: sigmoid increase with temperature
    gas_f = 0.55 / (1.0 + math.exp(-0.008 * (temp_c - 500))) + 0.10

    # Heating rate boost (fast pyrolysis produces more oil+gas)
    hr_adj = {"slow": 0.85, "medium": 1.0, "fast": 1.20}
    gas_f *= hr_adj.get(heating_rate, 1.0)

    # Biosolids have more inorganics — slightly lower gas energy fraction
    fs_adj = {"biosolids": 0.90, "biomass": 1.0, "mixed_waste": 0.95}
    gas_f *= fs_adj.get(feedstock, 0.90)

    return round(max(0.10, min(0.70, gas_f)), 3)


def pyrogas_calorific_value_mj_per_m3(temp_c: float,
                                        heating_rate: str = "medium") -> float:
    """
    Calorific value of pyrogas (MJ/Nm³).
    Increases with temperature as H2 and CH4 content rises.
    Decreases with fast pyrolysis at very high temps (dilution by inerts).

    Literature range:
      300°C → 5-8 MJ/Nm³
      500°C → 10-14 MJ/Nm³
      700°C → 13-18 MJ/Nm³
      800°C → 14-20 MJ/Nm³
    """
    # Piecewise linear approximation
    if temp_c <= 400:
        gcv = 5.0 + (temp_c - 300) * 0.030
    elif temp_c <= 600:
        gcv = 8.0 + (temp_c - 400) * 0.030
    else:
        gcv = 14.0 + (temp_c - 600) * 0.020
    gcv = max(5.0, min(20.0, gcv))

    # Fast pyrolysis: bio-oil dominates rather than non-condensable gas
    hr_adj = {"slow": 1.05, "medium": 1.0, "fast": 0.85}
    return round(gcv * hr_adj.get(heating_rate, 1.0), 1)


def N_retention_fraction(temp_c: float) -> float:
    """
    Fraction of feed nitrogen retained in biochar (vs volatilised as NH3/HCN).
    Decreases with temperature.

    Literature (sludge):
      300°C → 55-70% retained (lower than biomass due to high protein-N)
      500°C → 40-55%
      650°C → 25-40%
      800°C → 15-25%

    Note: Sludge biosolids have lower N retention than wood biomass because
    proteinaceous N is more labile and begins volatilising from ~250°C.
    """
    # Adjusted for biosolids — starts lower, declines more rapidly
    n_ret = 0.72 * math.exp(-0.00150 * temp_c) + 0.05
    return round(max(0.05, min(0.80, n_ret)), 3)


def P_retention_fraction(temp_c: float) -> float:
    """
    Fraction of feed phosphorus retained in biochar.
    P is less volatile than N — stays mostly in ash/char.

    Literature: P retention 80-95% across typical pyrolysis range.
    Slight decrease at high temperatures due to volatilisation as P2O5.
    """
    p_ret = 0.98 - (max(0, temp_c - 400) * 0.00025)
    return round(max(0.70, min(0.98, p_ret)), 3)


def K_retention_fraction(temp_c: float) -> float:
    """
    Fraction of feed potassium retained in biochar.
    More volatile than P at high temperatures.
    """
    k_ret = 0.92 - (max(0, temp_c - 400) * 0.0005)
    return round(max(0.40, min(0.95, k_ret)), 3)


# ---------------------------------------------------------------------------
# PFAS RESPONSE
# ---------------------------------------------------------------------------

def pfas_confidence(temp_c: float,
                     has_secondary_oxidation: bool = False,
                     secondary_temp_c: float = 0.0) -> tuple:
    """
    Return (confidence_level, rationale) for PFAS outcome.

    Thresholds (per EPA/ITRC/OECD guidance):
      <500°C: LOW — insufficient temperature for C-F bond cleavage
      500-700°C: MODERATE — partial destruction; compound-specific; redistribution risk
      >700°C primary + secondary oxidation ≥850°C: HIGH — ITS configuration

    Returns: (level: str, rationale: str, its_upgrade_needed: bool)
    """
    if temp_c < 500:
        return (
            "LOW",
            f"Primary reactor at {temp_c:.0f}°C is below the minimum threshold for "
            "reliable C-F bond cleavage (~500°C). PFAS redistribution between char, "
            "condensate, and gas-phase is the likely outcome. Not acceptable as a "
            "PFAS disposal route.",
            True,
        )
    elif temp_c < 700:
        return (
            "MODERATE",
            f"Primary reactor at {temp_c:.0f}°C achieves partial C-F bond cleavage. "
            "Destruction efficiency is compound-specific and uncertain — longer-chain PFAS "
            "(PFOA, PFOS) may survive in char or condense in bio-oil. "
            "CONDITIONAL: requires secondary oxidation stage at ≥850°C for reliable destruction.",
            True,
        )
    else:
        if has_secondary_oxidation and secondary_temp_c >= 850:
            return (
                "HIGH",
                f"Primary reactor at {temp_c:.0f}°C with secondary oxidation at "
                f"{secondary_temp_c:.0f}°C. This is an Integrated Thermal System (ITS) "
                "configuration. Design-based PFAS destruction — independent testing "
                "required to confirm site-specific compound classes.",
                False,
            )
        else:
            return (
                "MODERATE",
                f"Primary reactor at {temp_c:.0f}°C achieves substantial C-F bond cleavage "
                "for most PFAS compounds. However, without a secondary oxidation stage at "
                "≥850°C, gas-phase PFAS recombination or condensation in downstream "
                "equipment remains a risk. Add secondary oxidation to achieve HIGH confidence.",
                True,
            )


# ---------------------------------------------------------------------------
# OPERATING MODE CLASSIFICATION
# ---------------------------------------------------------------------------

def classify_operating_mode(temp_c: float,
                              heating_rate: str,
                              objective: str) -> tuple:
    """
    Classify into LOW / MID / HIGH TEMP MODE and name the best mode
    for the stated objective.

    Returns: (mode_label, mode_description, is_best_for_objective)
    """
    if temp_c < 500:
        mode = "LOW TEMP MODE"
        desc = (
            f"Low temperature ({temp_c:.0f}°C): maximises biochar yield and nutrient retention. "
            "High char mass output with moderate fixed carbon. "
            "Best for: soil amendment, nutrient recovery, agricultural markets. "
            "Not suitable for PFAS compliance. Energy recovery from pyrogas is modest."
        )
    elif temp_c <= 650:
        mode = "MID TEMP MODE"
        desc = (
            f"Mid temperature ({temp_c:.0f}°C): balanced biochar yield, fixed carbon, "
            "and pyrogas energy. Reasonable nutrient retention. "
            "Best for: soil amendment grade biochar, moderate energy recovery, "
            "general biosolids management. Suitable where PFAS is not confirmed."
        )
    else:
        mode = "HIGH TEMP MODE"
        desc = (
            f"High temperature ({temp_c:.0f}°C): maximises fixed carbon content and "
            "carbon stability. Lower biochar yield but higher quality per tonne. "
            "Pyrogas energy recovery is highest. Improved PFAS performance (with secondary oxidation). "
            "Best for: carbon credit markets, engineered carbon, compliance-driven operations."
        )

    # Is this the best mode for the stated objective?
    best_mode_for = {
        "energy":      "HIGH TEMP MODE",
        "product":     "LOW TEMP MODE",
        "compliance":  "HIGH TEMP MODE",
        "balanced":    "MID TEMP MODE",
        "carbon_credit": "HIGH TEMP MODE",
    }
    is_best = mode == best_mode_for.get(objective, "MID TEMP MODE")

    return mode, desc, is_best


# ---------------------------------------------------------------------------
# PRODUCT VALUE PATHWAY
# ---------------------------------------------------------------------------

def classify_product_pathway(temp_c: float,
                               stability: float,
                               yield_pct: float,
                               pfas_conf: str,
                               market_conf: str = "low") -> dict:
    """
    Classify the biochar product value pathway and estimate revenue range.

    Returns dict with pathway label, value range, and confidence.
    """
    if pfas_conf == "HIGH" or pfas_conf == "LOW":
        # High: PFAS destroyed — clean product
        # Low: PFAS not destroyed — land application precluded
        pass

    pathways = []

    # Energy fuel (pyrogas, not biochar — but biochar can be used as fuel at low stability)
    if stability < 0.45 or temp_c < 450:
        pathways.append({
            "pathway": "Energy Fuel (pyrogas recovery)",
            "value_range": "$5–25/GJ (pyrogas)",
            "confidence": "high" if yield_pct > 30 else "moderate",
            "note": "Low-stability char may also be used as supplementary fuel.",
            "primary": temp_c < 450,
        })

    # Soil amendment
    if stability >= 0.40 and pfas_conf != "LOW":
        value_low  = 50  if market_conf == "low"      else 80
        value_high = 200 if market_conf == "low"      else 400
        pathways.append({
            "pathway": "Soil Amendment",
            "value_range": f"${value_low}–${value_high}/tonne biochar",
            "confidence": market_conf,
            "note": (
                "Requires: PFAS negative or destruction confirmed, metal leaching test, "
                "nutrient analysis. Agricultural approval varies by jurisdiction."
            ),
            "primary": 450 <= temp_c <= 650,
        })

    # Carbon credit asset
    if stability >= 0.55:
        credit_value = 60 if market_conf == "low" else 150
        pathways.append({
            "pathway": "Carbon Credit Asset",
            "value_range": f"${credit_value}–${credit_value*3}/tonne CO₂e sequestered",
            "confidence": "low" if stability < 0.65 else "moderate",
            "note": (
                "Requires: stable R50 > 0.55, third-party verification, "
                "approved carbon methodology (e.g. Verra VM0044, Gold Standard). "
                f"Stability index at {temp_c:.0f}°C: R50 = {stability:.2f}."
            ),
            "primary": temp_c >= 600,
        })

    # Engineered carbon (high stability, low contamination)
    if stability >= 0.70 and pfas_conf != "LOW":
        pathways.append({
            "pathway": "Engineered Carbon (industrial)",
            "value_range": "$200–800/tonne",
            "confidence": "low",
            "note": (
                "Niche markets: water treatment, cement co-fuel, construction. "
                "Requires consistent product specification and scale."
            ),
            "primary": False,
        })

    if not pathways:
        pathways.append({
            "pathway": "Regulated Disposal",
            "value_range": "-$50 to -$200/tonne (cost)",
            "confidence": "high",
            "note": "PFAS present and not destroyed — biochar is a regulated waste.",
            "primary": True,
        })

    return pathways


# ---------------------------------------------------------------------------
# CONTINUOUS OPERATING ENVELOPE
# ---------------------------------------------------------------------------

@dataclass
class PyrolysisPoint:
    """One point on the operating envelope curve."""
    temp_c: float = 0.0
    heating_rate: str = "medium"
    feedstock: str = "biosolids"

    biochar_yield_pct: float = 0.0
    fixed_carbon_pct: float = 0.0
    volatile_matter_pct: float = 0.0
    carbon_stability_r50: float = 0.0
    N_retention_pct: float = 0.0
    P_retention_pct: float = 0.0
    K_retention_pct: float = 0.0
    pyrogas_energy_fraction: float = 0.0
    pyrogas_gcv_mj_per_m3: float = 0.0
    pfas_confidence: str = ""

    # Derived (needs ds_tpd to compute)
    biochar_t_per_day: float = 0.0
    pyrogas_energy_kwh_d: float = 0.0


@dataclass
class PyrolysisOperatingEnvelope:
    """
    Full operating envelope: continuous curve from 300 to 800°C.
    Plus objective-specific mode recommendations.
    """
    # Inputs
    ds_tpd: float = 0.0
    feedstock_type: str = "biosolids"
    heating_rate: str = "medium"
    feedstock_gcv_mj_per_kg_ds: float = 12.0
    feedstock_vs_pct: float = 72.0
    pfas_present: str = "unknown"
    has_secondary_oxidation: bool = False
    secondary_temp_c: float = 0.0
    objective: str = "balanced"          # energy / product / compliance / balanced / carbon_credit

    # Continuous curve (step: 25°C from 300 to 800°C)
    curve: list = field(default_factory=list)   # List[PyrolysisPoint]

    # Three recommended operating modes
    low_temp_mode: Optional[PyrolysisPoint] = None    # ~450°C
    mid_temp_mode: Optional[PyrolysisPoint] = None    # ~575°C
    high_temp_mode: Optional[PyrolysisPoint] = None   # ~700°C

    # Objective-specific recommendation
    recommended_temp_c: float = 0.0
    recommended_mode: str = ""
    recommended_range: str = ""
    recommended_rationale: str = ""

    # PFAS assessment at recommended temp
    pfas_confidence_level: str = ""
    pfas_confidence_rationale: str = ""
    pfas_its_upgrade_needed: bool = False

    # Product pathways at recommended temp
    product_pathways: list = field(default_factory=list)

    # Trade-off narrative
    yield_energy_tradeoff_narrative: str = ""

    # Per-mode summary (for board display)
    mode_summaries: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# MAIN ENGINE FUNCTION
# ---------------------------------------------------------------------------

def run_pyrolysis_envelope(
    ds_tpd: float,
    feedstock_type: str = "biosolids",
    heating_rate: str = "medium",
    feedstock_gcv_mj_per_kg_ds: float = 12.0,
    feedstock_vs_pct: float = 72.0,
    pfas_present: str = "unknown",
    has_secondary_oxidation: bool = False,
    secondary_temp_c: float = 0.0,
    objective: str = "balanced",
    temp_step: int = 25,
) -> PyrolysisOperatingEnvelope:
    """
    Compute the full pyrolysis operating envelope from 300 to 800°C.

    Parameters
    ----------
    ds_tpd                   : Dry solids throughput (tDS/day)
    feedstock_type           : 'biosolids' / 'biomass' / 'mixed_waste'
    heating_rate             : 'slow' / 'medium' / 'fast'
    feedstock_gcv_mj_per_kg_ds : GCV of dry feed
    feedstock_vs_pct         : Volatile solids % of DS
    pfas_present             : 'unknown' / 'confirmed' / 'negative'
    has_secondary_oxidation  : True if secondary combustion chamber present
    secondary_temp_c         : Temperature of secondary chamber (°C)
    objective                : 'energy' / 'product' / 'compliance' / 'balanced' / 'carbon_credit'
    temp_step                : Step size for the operating curve (°C)
    """
    feedstock_kwh_d = ds_tpd * 1000 * feedstock_gcv_mj_per_kg_ds / 3.6

    env = PyrolysisOperatingEnvelope(
        ds_tpd=ds_tpd,
        feedstock_type=feedstock_type,
        heating_rate=heating_rate,
        feedstock_gcv_mj_per_kg_ds=feedstock_gcv_mj_per_kg_ds,
        feedstock_vs_pct=feedstock_vs_pct,
        pfas_present=pfas_present,
        has_secondary_oxidation=has_secondary_oxidation,
        secondary_temp_c=secondary_temp_c,
        objective=objective,
    )

    # --- GENERATE CONTINUOUS CURVE ---
    temps = list(range(300, 801, temp_step))
    curve = []
    for t in temps:
        pt = _compute_point(
            t, heating_rate, feedstock_type,
            ds_tpd, feedstock_kwh_d,
            has_secondary_oxidation, secondary_temp_c
        )
        curve.append(pt)
    env.curve = curve

    # --- THREE MODE REFERENCE POINTS ---
    env.low_temp_mode  = _compute_point(450, heating_rate, feedstock_type, ds_tpd, feedstock_kwh_d, has_secondary_oxidation, secondary_temp_c)
    env.mid_temp_mode  = _compute_point(575, heating_rate, feedstock_type, ds_tpd, feedstock_kwh_d, has_secondary_oxidation, secondary_temp_c)
    env.high_temp_mode = _compute_point(700, heating_rate, feedstock_type, ds_tpd, feedstock_kwh_d, has_secondary_oxidation, secondary_temp_c)

    # --- OBJECTIVE-SPECIFIC RECOMMENDATION ---
    rec_temp = _recommend_temp(objective, pfas_present, has_secondary_oxidation)
    env.recommended_temp_c = rec_temp
    env.recommended_mode, _, _ = classify_operating_mode(rec_temp, heating_rate, objective)
    env.recommended_range = _recommend_range(objective)
    env.recommended_rationale = _recommend_rationale(
        objective, rec_temp, heating_rate, feedstock_type, pfas_present, has_secondary_oxidation
    )

    # --- PFAS AT RECOMMENDED TEMP ---
    pfas_lev, pfas_rat, pfas_upg = pfas_confidence(
        rec_temp, has_secondary_oxidation, secondary_temp_c
    )
    env.pfas_confidence_level    = pfas_lev
    env.pfas_confidence_rationale = pfas_rat
    env.pfas_its_upgrade_needed  = pfas_upg

    # --- PRODUCT PATHWAYS AT RECOMMENDED TEMP ---
    rec_pt = _compute_point(rec_temp, heating_rate, feedstock_type, ds_tpd, feedstock_kwh_d, has_secondary_oxidation, secondary_temp_c)
    env.product_pathways = classify_product_pathway(
        rec_temp, rec_pt.carbon_stability_r50,
        rec_pt.biochar_yield_pct, pfas_lev, "low"
    )

    # --- TRADE-OFF NARRATIVE ---
    env.yield_energy_tradeoff_narrative = _tradeoff_narrative(
        env.low_temp_mode, env.mid_temp_mode, env.high_temp_mode,
        ds_tpd, feedstock_kwh_d, heating_rate
    )

    # --- MODE SUMMARIES ---
    env.mode_summaries = _build_mode_summaries(
        env.low_temp_mode, env.mid_temp_mode, env.high_temp_mode,
        ds_tpd, feedstock_kwh_d, has_secondary_oxidation, secondary_temp_c
    )

    return env


# ---------------------------------------------------------------------------
# POINT CALCULATOR
# ---------------------------------------------------------------------------

def _compute_point(temp_c, heating_rate, feedstock, ds_tpd,
                    feedstock_kwh_d, has_secondary_oxidation, secondary_temp_c
                    ) -> PyrolysisPoint:
    pt = PyrolysisPoint(
        temp_c=temp_c,
        heating_rate=heating_rate,
        feedstock=feedstock,
    )
    pt.biochar_yield_pct       = biochar_yield_pct(temp_c, heating_rate, feedstock)
    pt.fixed_carbon_pct        = fixed_carbon_pct(temp_c, feedstock)
    pt.volatile_matter_pct     = volatile_matter_pct(temp_c, heating_rate)
    pt.carbon_stability_r50    = carbon_stability_index(temp_c)
    pt.N_retention_pct         = round(N_retention_fraction(temp_c) * 100, 1)
    pt.P_retention_pct         = round(P_retention_fraction(temp_c) * 100, 1)
    pt.K_retention_pct         = round(K_retention_fraction(temp_c) * 100, 1)
    pt.pyrogas_energy_fraction = pyrogas_energy_fraction(temp_c, heating_rate, feedstock)
    pt.pyrogas_gcv_mj_per_m3   = pyrogas_calorific_value_mj_per_m3(temp_c, heating_rate)

    pfas_lev, _, _ = pfas_confidence(temp_c, has_secondary_oxidation, secondary_temp_c)
    pt.pfas_confidence = pfas_lev

    # Derived quantities
    pt.biochar_t_per_day = round(ds_tpd * pt.biochar_yield_pct / 100, 2)
    pt.pyrogas_energy_kwh_d = round(feedstock_kwh_d * pt.pyrogas_energy_fraction, 0)

    return pt


# ---------------------------------------------------------------------------
# OBJECTIVE-SPECIFIC RECOMMENDATION
# ---------------------------------------------------------------------------

_OBJECTIVE_TEMPS = {
    "energy":        700,   # Maximise pyrogas energy
    "product":       450,   # Maximise biochar yield and nutrients
    "compliance":    720,   # PFAS destruction (needs secondary oxidation)
    "balanced":      575,   # Balanced across all outputs
    "carbon_credit": 650,   # Stability index > 0.60 for reliable credits
}

def _recommend_temp(objective: str, pfas_present: str,
                     has_secondary_oxidation: bool) -> float:
    t = _OBJECTIVE_TEMPS.get(objective, 575)
    # If PFAS confirmed and no secondary oxidation, push higher to minimum useful temp
    if pfas_present == "confirmed" and not has_secondary_oxidation and t < 700:
        t = 700  # At least attempt partial destruction
    return t


def _recommend_range(objective: str) -> str:
    ranges = {
        "energy":        "650–800°C",
        "product":       "400–500°C",
        "compliance":    "700–800°C (primary) + ≥850°C secondary oxidation",
        "balanced":      "550–650°C",
        "carbon_credit": "600–700°C",
    }
    return ranges.get(objective, "550–650°C")


def _recommend_rationale(objective: str, temp_c: float, heating_rate: str,
                           feedstock: str, pfas_present: str,
                           has_secondary_oxidation: bool) -> str:
    pt = PyrolysisPoint()
    pt.biochar_yield_pct    = biochar_yield_pct(temp_c, heating_rate, feedstock)
    pt.carbon_stability_r50 = carbon_stability_index(temp_c)
    gas_frac = pyrogas_energy_fraction(temp_c, heating_rate, feedstock)

    rationales = {
        "energy": (
            f"At {temp_c:.0f}°C, pyrogas energy fraction is {gas_frac:.0%} of feedstock energy. "
            f"Biochar yield is {pt.biochar_yield_pct:.0f}% DS — reduced relative to lower temperatures, "
            "but the operating objective is energy recovery, not char mass. "
            "Pyrogas with GCV 14–18 MJ/Nm³ drives maximum electrical output. "
            f"Carbon stability R50 = {pt.carbon_stability_r50:.2f} (high quality if char is also marketed)."
        ),
        "product": (
            f"At {temp_c:.0f}°C, biochar yield is {pt.biochar_yield_pct:.0f}% DS — maximum for this feedstock. "
            f"Nitrogen retention is highest (~{N_retention_fraction(temp_c)*100:.0f}%), "
            "making this a nutrient-dense soil amendment grade product. "
            "Carbon stability is lower at this temperature — appropriate for agricultural application "
            "but not for carbon credit programmes without verification of R50."
        ),
        "compliance": (
            f"At {temp_c:.0f}°C, primary reactor temperature approaches the upper pyrolysis range. "
            "Combined with secondary oxidation at ≥850°C, this achieves ITS (Level 3) "
            "PFAS destruction capability. "
            "Compliance-driven operation accepts lower biochar yield in exchange for "
            "regulatory certainty on the product."
            + (" NOTE: No secondary oxidation detected — partial destruction only. "
               "Add secondary combustion chamber to achieve HIGH PFAS confidence."
               if not has_secondary_oxidation else "")
        ),
        "balanced": (
            f"At {temp_c:.0f}°C, the system delivers a balanced output: "
            f"biochar yield {pt.biochar_yield_pct:.0f}% DS, "
            f"pyrogas energy fraction {gas_frac:.0%}, "
            f"carbon stability R50 = {pt.carbon_stability_r50:.2f}. "
            "This is the recommended starting point when the product market is not yet "
            "confirmed and flexibility is valued. "
            "System can be tuned toward energy (raise temp) or product (lower temp) "
            "as market conditions become clear."
        ),
        "carbon_credit": (
            f"At {temp_c:.0f}°C, carbon stability index R50 = {pt.carbon_stability_r50:.2f}. "
            "R50 > 0.55 is the minimum threshold for most carbon credit methodologies. "
            "Biochar yield is {:.0f}% DS — smaller quantity but higher stability per tonne. ".format(
                pt.biochar_yield_pct) +
            "Carbon credit revenue depends on third-party verification and approved methodology. "
            "Treat as upside until offtake agreement is confirmed."
        ),
    }
    return rationales.get(objective, rationales["balanced"])


# ---------------------------------------------------------------------------
# NARRATIVE BUILDERS
# ---------------------------------------------------------------------------

def _tradeoff_narrative(low: PyrolysisPoint, mid: PyrolysisPoint,
                          high: PyrolysisPoint, ds_tpd: float,
                          feedstock_kwh_d: float, heating_rate: str) -> str:
    return (
        f"YIELD vs ENERGY TRADE-OFF ({heating_rate} pyrolysis, {ds_tpd:.0f} tDS/d):\n"
        f"\n"
        f"  Low temp ({low.temp_c:.0f}°C):  "
        f"biochar {low.biochar_yield_pct:.0f}% DS = {low.biochar_t_per_day:.1f} t/d | "
        f"fixed C {low.fixed_carbon_pct:.0f}% | "
        f"pyrogas {low.pyrogas_energy_fraction:.0%} of feedstock energy "
        f"({low.pyrogas_energy_kwh_d:,.0f} kWh/d) | "
        f"R50 = {low.carbon_stability_r50:.2f} | "
        f"N retention {low.N_retention_pct:.0f}%\n"
        f"\n"
        f"  Mid temp ({mid.temp_c:.0f}°C):  "
        f"biochar {mid.biochar_yield_pct:.0f}% DS = {mid.biochar_t_per_day:.1f} t/d | "
        f"fixed C {mid.fixed_carbon_pct:.0f}% | "
        f"pyrogas {mid.pyrogas_energy_fraction:.0%} of feedstock energy "
        f"({mid.pyrogas_energy_kwh_d:,.0f} kWh/d) | "
        f"R50 = {mid.carbon_stability_r50:.2f} | "
        f"N retention {mid.N_retention_pct:.0f}%\n"
        f"\n"
        f"  High temp ({high.temp_c:.0f}°C): "
        f"biochar {high.biochar_yield_pct:.0f}% DS = {high.biochar_t_per_day:.1f} t/d | "
        f"fixed C {high.fixed_carbon_pct:.0f}% | "
        f"pyrogas {high.pyrogas_energy_fraction:.0%} of feedstock energy "
        f"({high.pyrogas_energy_kwh_d:,.0f} kWh/d) | "
        f"R50 = {high.carbon_stability_r50:.2f} | "
        f"N retention {high.N_retention_pct:.0f}%\n"
        f"\n"
        "Moving from low to high temperature: biochar yield falls "
        f"from {low.biochar_yield_pct:.0f}% to {high.biochar_yield_pct:.0f}% DS "
        f"(-{low.biochar_yield_pct - high.biochar_yield_pct:.0f} %DS), "
        "pyrogas energy rises "
        f"from {low.pyrogas_energy_fraction:.0%} to {high.pyrogas_energy_fraction:.0%} of feedstock energy "
        f"(+{(high.pyrogas_energy_fraction - low.pyrogas_energy_fraction)*100:.0f}%), "
        "carbon stability rises "
        f"from R50 {low.carbon_stability_r50:.2f} to {high.carbon_stability_r50:.2f}."
    )


def _build_mode_summaries(low, mid, high, ds_tpd, feedstock_kwh_d,
                            has_secondary_oxidation, secondary_temp_c) -> dict:
    def pfas_lev(pt):
        lev, _, _ = pfas_confidence(pt.temp_c, has_secondary_oxidation, secondary_temp_c)
        return lev

    return {
        "LOW TEMP MODE": {
            "temp_c": low.temp_c,
            "label": f"{low.temp_c:.0f}°C | ENERGY + YIELD FOCUSED",
            "biochar_yield_pct": low.biochar_yield_pct,
            "biochar_t_d": low.biochar_t_per_day,
            "fixed_carbon_pct": low.fixed_carbon_pct,
            "stability_r50": low.carbon_stability_r50,
            "N_retention_pct": low.N_retention_pct,
            "pyrogas_fraction": low.pyrogas_energy_fraction,
            "pyrogas_kwh_d": low.pyrogas_energy_kwh_d,
            "pfas_confidence": pfas_lev(low),
            "best_for": "Soil amendment, nutrient-rich product, agricultural market",
            "not_for": "PFAS compliance, carbon credit programmes",
        },
        "MID TEMP MODE": {
            "temp_c": mid.temp_c,
            "label": f"{mid.temp_c:.0f}°C | BALANCED SYSTEM",
            "biochar_yield_pct": mid.biochar_yield_pct,
            "biochar_t_d": mid.biochar_t_per_day,
            "fixed_carbon_pct": mid.fixed_carbon_pct,
            "stability_r50": mid.carbon_stability_r50,
            "N_retention_pct": mid.N_retention_pct,
            "pyrogas_fraction": mid.pyrogas_energy_fraction,
            "pyrogas_kwh_d": mid.pyrogas_energy_kwh_d,
            "pfas_confidence": pfas_lev(mid),
            "best_for": "Soil amendment, flexible market positioning, first-of-kind systems",
            "not_for": "Definitive PFAS compliance without secondary oxidation",
        },
        "HIGH TEMP MODE": {
            "temp_c": high.temp_c,
            "label": f"{high.temp_c:.0f}°C | COMPLIANCE + CARBON STABILITY",
            "biochar_yield_pct": high.biochar_yield_pct,
            "biochar_t_d": high.biochar_t_per_day,
            "fixed_carbon_pct": high.fixed_carbon_pct,
            "stability_r50": high.carbon_stability_r50,
            "N_retention_pct": high.N_retention_pct,
            "pyrogas_fraction": high.pyrogas_energy_fraction,
            "pyrogas_kwh_d": high.pyrogas_energy_kwh_d,
            "pfas_confidence": pfas_lev(high),
            "best_for": "Carbon credits, engineered carbon, compliance-driven operations",
            "not_for": "Maximum biochar mass output, nutrient recovery",
        },
    }
