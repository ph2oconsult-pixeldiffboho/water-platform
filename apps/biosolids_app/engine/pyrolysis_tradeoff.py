"""
BioPoint V1 — Pyrolysis Trade-Off Curve Engine (v25A20).

Quantifies the financial trade-offs across the pyrolysis operating envelope.
Extends v25A12 (PyrolysisOperatingEnvelope) by adding:

  - Biochar calorific value as function of temperature
  - Energy value ($/tDS) from pyrogas recovery
  - Biochar market value ($/tDS) by market grade
  - Carbon credit value ($/tDS) from stable carbon fraction
  - Total value ($/tDS) at each temperature point
  - Optimisation output: optimal temp per objective with financials
  - Board message: no single optimal temperature

Biochar CV function calibrated to:
  Lehmann & Joseph (2015) — ~17 MJ/kg at 300°C, ~24 MJ/kg at 800°C for pure carbon,
  but sludge biochar has high ash (35-45% ash) so effective GCV is lower:
  effective ~8–14 MJ/kg across the typical range.
  Spec states 17→11 MJ/kg — this refers to the USABLE fraction after ash dilution.

Energy conversion: pyrogas → electrical:
  CHP electrical efficiency 33%, OR
  direct gas combustion → electricity via gas engine / boiler → steam turbine ~28%.
  Model uses 30% combined electrical conversion as conservative mid-range.

ph2o Consulting — BioPoint V1
"""

from dataclasses import dataclass, field
from typing import Optional
from engine.pyrolysis_envelope import (
    run_pyrolysis_envelope, PyrolysisPoint,
    pyrogas_energy_fraction, biochar_yield_pct, fixed_carbon_pct,
    carbon_stability_index, N_retention_fraction, P_retention_fraction,
    pyrogas_calorific_value_mj_per_m3, pfas_confidence,
)


# ---------------------------------------------------------------------------
# BIOCHAR CALORIFIC VALUE FUNCTION
# ---------------------------------------------------------------------------

def biochar_cv_mj_per_kg(temp_c: float, feedstock: str = "biosolids") -> float:
    """
    Effective (usable) calorific value of sludge biochar (MJ/kg of biochar).

    Pure carbon: ~32 MJ/kg.
    Sludge biochar: high ash content (35–50%) dilutes GCV significantly.
    At low temperatures: more volatile matter → higher apparent GCV but unstable.
    At high temperatures: higher fixed carbon % but ash dilutes overall GCV.

    Net result for biosolids biochar (spec: ~17 MJ/kg at 300°C → ~11 MJ/kg at 800°C):
    This reflects that lower-temperature biochar retains more volatiles
    (higher immediate GCV) while higher-temperature biochar has higher
    fixed carbon but ash dilution reduces bulk GCV.

    Literature:
      Zhao et al. (2013) — sludge pyrolysis biochar GCV 8–18 MJ/kg
      IBI Standard — biochar with >15% ash often <15 MJ/kg bulk GCV
    """
    # Linear decline from ~17 MJ/kg at 300°C to ~11 MJ/kg at 800°C
    # Reflects: volatile matter loss at high temp offsets fixed carbon gains in bulk GCV
    cv = 17.0 - (temp_c - 300) * (6.0 / 500)
    cv = max(8.0, min(18.0, cv))

    # Biomass biochar has less ash → higher GCV per kg
    fs_adj = {"biosolids": 1.0, "biomass": 1.25, "mixed_waste": 1.10}
    cv *= fs_adj.get(feedstock, 1.0)

    return round(cv, 2)


# ---------------------------------------------------------------------------
# MARKET PRICE TABLES
# ---------------------------------------------------------------------------

# Biochar market prices ($/tonne of biochar) by market grade
# These are mid-case estimates; actual markets vary widely
BIOCHAR_MARKET_PRICES = {
    "low_grade": {
        "label":       "Low-Grade (fuel / soil carbon)",
        "price_low":    30,
        "price_mid":    70,
        "price_high":  120,
        "temp_range":  "300–500°C",
        "note": "Fuel or basic soil carbon input. No certification required.",
    },
    "soil_amendment": {
        "label":       "Soil Amendment",
        "price_low":   100,
        "price_mid":   200,
        "price_high":  400,
        "temp_range":  "450–650°C",
        "note": "Certified biochar for agricultural use. Requires IBI/EBC standard.",
    },
    "engineered_carbon": {
        "label":       "Engineered Carbon (industrial)",
        "price_low":   250,
        "price_mid":   600,
        "price_high": 1400,
        "temp_range":  "600–800°C",
        "note": "Water treatment, construction, high-value industrial. Niche market.",
    },
}

# Carbon credit price ranges ($/tCO2e)
CARBON_PRICE_DEFAULTS = {
    "low":    25.0,
    "medium": 60.0,
    "high":  150.0,
}

# Electrical conversion efficiency (pyrogas → electricity)
PYROGAS_ELECTRICAL_EFF = 0.30   # 30% gas → electricity (CHP or gas engine)


# ---------------------------------------------------------------------------
# VALUE POINT (one temperature)
# ---------------------------------------------------------------------------

@dataclass
class TradeOffPoint:
    """Financial aggregation at one operating temperature."""
    temp_c: float = 0.0
    heating_rate: str = "medium"
    feedstock: str = "biosolids"

    # Physical outputs (from envelope)
    biochar_yield_pct: float = 0.0        # % of DS input
    biochar_yield_t_per_day: float = 0.0
    biochar_cv_mj_per_kg: float = 0.0     # Effective GCV of biochar
    fixed_carbon_pct: float = 0.0
    carbon_stability_r50: float = 0.0
    stable_carbon_fraction: float = 0.0   # Fraction eligible for carbon credits
    N_retention_pct: float = 0.0
    P_retention_pct: float = 0.0
    pyrogas_energy_fraction: float = 0.0
    pyrogas_energy_kwh_d: float = 0.0
    pfas_confidence: str = ""

    # Energy value
    pyrogas_electricity_kwh_d: float = 0.0  # After conversion efficiency
    energy_value_per_tds: float = 0.0        # $/tDS

    # Biochar value
    biochar_market_grade: str = ""
    biochar_price_per_tonne: float = 0.0     # $/t biochar
    biochar_value_per_tds: float = 0.0       # $/tDS

    # Carbon credit value
    stable_carbon_t_per_tds: float = 0.0     # tC/tDS eligible for credits
    co2e_per_tds: float = 0.0                # tCO2e/tDS
    carbon_credit_per_tds: float = 0.0       # $/tDS

    # Total value
    total_value_per_tds: float = 0.0         # $/tDS
    total_value_per_day: float = 0.0         # $/day

    # Operating mode
    operating_mode: str = ""                 # LOW TEMP / MID TEMP / HIGH TEMP


# ---------------------------------------------------------------------------
# TRADE-OFF CURVE RESULT
# ---------------------------------------------------------------------------

@dataclass
class TradeOffCurve:
    """
    Full trade-off curve: value at every temperature from 300 to 800°C.
    Financial aggregation of the pyrolysis operating envelope.
    """
    # Inputs
    ds_tpd: float = 0.0
    feedstock_type: str = "biosolids"
    heating_rate: str = "medium"
    feedstock_gcv_mj_per_kg_ds: float = 12.0
    electricity_price_per_mwh: float = 180.0
    electricity_price_per_kwh: float = 0.18
    biochar_market_type: str = "soil_amendment"
    carbon_price_per_tco2e: float = 60.0

    # Curve data (21 points, 300-800°C step 25)
    points: list = field(default_factory=list)   # List[TradeOffPoint]

    # Three reference modes (450 / 575 / 700°C)
    low_temp_point: Optional[TradeOffPoint] = None
    mid_temp_point: Optional[TradeOffPoint] = None
    high_temp_point: Optional[TradeOffPoint] = None

    # Optima per objective
    optimal_energy_temp: float = 0.0
    optimal_energy_value: float = 0.0      # $/tDS
    optimal_product_temp: float = 0.0
    optimal_product_value: float = 0.0
    optimal_balanced_temp: float = 0.0
    optimal_balanced_value: float = 0.0

    # Comparison table (three modes side by side)
    comparison_table: dict = field(default_factory=dict)

    # Recommended mode for current inputs
    recommended_mode: str = ""
    recommended_temp: float = 0.0
    recommended_value_per_tds: float = 0.0
    recommendation_rationale: str = ""

    # Board message (verbatim from spec requirement)
    board_message: str = ""

    # Value breakdown at recommended temp
    energy_component_pct: float = 0.0
    biochar_component_pct: float = 0.0
    carbon_component_pct: float = 0.0

    # Chart-ready data (lists for direct use by UI)
    chart_temps: list = field(default_factory=list)
    chart_total_value: list = field(default_factory=list)
    chart_energy_value: list = field(default_factory=list)
    chart_biochar_value: list = field(default_factory=list)
    chart_carbon_value: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# MAIN ENGINE
# ---------------------------------------------------------------------------

def run_trade_off_curve(
    ds_tpd: float,
    feedstock_type: str = "biosolids",
    heating_rate: str = "medium",
    feedstock_gcv_mj_per_kg_ds: float = 12.0,
    feedstock_vs_pct: float = 72.0,
    electricity_price_per_mwh: float = 180.0,
    biochar_market_type: str = "soil_amendment",
    carbon_price_per_tco2e: float = 60.0,
    pfas_present: str = "unknown",
    has_secondary_oxidation: bool = False,
    secondary_temp_c: float = 0.0,
    temp_step: int = 25,
) -> TradeOffCurve:
    """
    Compute the full financial trade-off curve for pyrolysis.

    Parameters
    ----------
    ds_tpd                    : Dry solids throughput (tDS/day)
    feedstock_type            : 'biosolids' / 'biomass' / 'mixed_waste'
    heating_rate              : 'slow' / 'medium' / 'fast'
    feedstock_gcv_mj_per_kg_ds: GCV of dry feed (MJ/kgDS)
    feedstock_vs_pct          : Volatile solids % of DS
    electricity_price_per_mwh : Electricity price ($/MWh)
    biochar_market_type       : 'low_grade' / 'soil_amendment' / 'engineered_carbon'
    carbon_price_per_tco2e    : Carbon credit price ($/tCO2e)
    pfas_present              : 'unknown' / 'confirmed' / 'negative'
    has_secondary_oxidation   : True if secondary combustion chamber present
    secondary_temp_c          : Secondary chamber temperature (°C)
    temp_step                 : Step size for curve (°C)
    """
    el_price_kwh = electricity_price_per_mwh / 1000.0
    market_def   = BIOCHAR_MARKET_PRICES.get(biochar_market_type,
                                              BIOCHAR_MARKET_PRICES["soil_amendment"])
    biochar_price_per_t = market_def["price_mid"]
    feedstock_kwh_d     = ds_tpd * 1000 * feedstock_gcv_mj_per_kg_ds / 3.6

    curve = TradeOffCurve(
        ds_tpd=ds_tpd,
        feedstock_type=feedstock_type,
        heating_rate=heating_rate,
        feedstock_gcv_mj_per_kg_ds=feedstock_gcv_mj_per_kg_ds,
        electricity_price_per_mwh=electricity_price_per_mwh,
        electricity_price_per_kwh=el_price_kwh,
        biochar_market_type=biochar_market_type,
        carbon_price_per_tco2e=carbon_price_per_tco2e,
    )

    temps = list(range(300, 801, temp_step))
    points = []
    for t in temps:
        pt = _compute_value_point(
            t, heating_rate, feedstock_type,
            ds_tpd, feedstock_kwh_d,
            el_price_kwh, biochar_price_per_t,
            carbon_price_per_tco2e,
            has_secondary_oxidation, secondary_temp_c,
        )
        points.append(pt)

    curve.points = points

    # Reference modes
    curve.low_temp_point  = _compute_value_point(450, heating_rate, feedstock_type, ds_tpd, feedstock_kwh_d, el_price_kwh, biochar_price_per_t, carbon_price_per_tco2e, has_secondary_oxidation, secondary_temp_c)
    curve.mid_temp_point  = _compute_value_point(575, heating_rate, feedstock_type, ds_tpd, feedstock_kwh_d, el_price_kwh, biochar_price_per_t, carbon_price_per_tco2e, has_secondary_oxidation, secondary_temp_c)
    curve.high_temp_point = _compute_value_point(700, heating_rate, feedstock_type, ds_tpd, feedstock_kwh_d, el_price_kwh, biochar_price_per_t, carbon_price_per_tco2e, has_secondary_oxidation, secondary_temp_c)

    # Optima
    curve.optimal_energy_temp, curve.optimal_energy_value   = _find_optimal(points, "energy")
    curve.optimal_product_temp, curve.optimal_product_value = _find_optimal(points, "product")
    curve.optimal_balanced_temp, curve.optimal_balanced_value = _find_optimal(points, "balanced")

    # Comparison table
    curve.comparison_table = _build_comparison_table(
        curve.low_temp_point, curve.mid_temp_point, curve.high_temp_point,
        market_def
    )

    # Recommended mode (based on which value component dominates at mid-temp)
    curve.recommended_mode, curve.recommended_temp = _recommend_mode(
        curve.mid_temp_point, pfas_present, has_secondary_oxidation
    )
    rec_pt = _compute_value_point(
        int(curve.recommended_temp), heating_rate, feedstock_type,
        ds_tpd, feedstock_kwh_d, el_price_kwh, biochar_price_per_t,
        carbon_price_per_tco2e, has_secondary_oxidation, secondary_temp_c
    )
    curve.recommended_value_per_tds = rec_pt.total_value_per_tds
    curve.recommendation_rationale = _rationale(
        curve.recommended_mode, rec_pt, ds_tpd, market_def, carbon_price_per_tco2e
    )

    # Value breakdown at recommended temp
    total = rec_pt.total_value_per_tds
    if total > 0:
        curve.energy_component_pct  = round(rec_pt.energy_value_per_tds  / total * 100, 1)
        curve.biochar_component_pct = round(rec_pt.biochar_value_per_tds / total * 100, 1)
        curve.carbon_component_pct  = round(rec_pt.carbon_credit_per_tds / total * 100, 1)

    # Board message (verbatim from spec)
    curve.board_message = (
        "There is no single optimal temperature. "
        "The optimal operating point depends on whether the system is optimised "
        "for energy, product value, or compliance."
    )

    # Chart-ready lists
    curve.chart_temps        = [pt.temp_c for pt in points]
    curve.chart_total_value  = [pt.total_value_per_tds for pt in points]
    curve.chart_energy_value = [pt.energy_value_per_tds for pt in points]
    curve.chart_biochar_value= [pt.biochar_value_per_tds for pt in points]
    curve.chart_carbon_value = [pt.carbon_credit_per_tds for pt in points]

    return curve


# ---------------------------------------------------------------------------
# POINT CALCULATOR
# ---------------------------------------------------------------------------

def _compute_value_point(
    temp_c: int,
    heating_rate: str,
    feedstock: str,
    ds_tpd: float,
    feedstock_kwh_d: float,
    el_price_kwh: float,
    biochar_price_per_t: float,
    carbon_price_per_tco2e: float,
    has_secondary_oxidation: bool,
    secondary_temp_c: float,
) -> TradeOffPoint:

    pt = TradeOffPoint(
        temp_c=float(temp_c),
        heating_rate=heating_rate,
        feedstock=feedstock,
    )

    # --- PHYSICAL OUTPUTS ---
    pt.biochar_yield_pct       = biochar_yield_pct(temp_c, heating_rate, feedstock)
    pt.biochar_yield_t_per_day = ds_tpd * pt.biochar_yield_pct / 100
    pt.biochar_cv_mj_per_kg    = biochar_cv_mj_per_kg(temp_c, feedstock)
    pt.fixed_carbon_pct        = fixed_carbon_pct(temp_c, feedstock)
    pt.carbon_stability_r50    = carbon_stability_index(temp_c)
    pt.N_retention_pct         = round(N_retention_fraction(temp_c) * 100, 1)
    pt.P_retention_pct         = round(P_retention_fraction(temp_c) * 100, 1)
    pt.pyrogas_energy_fraction = pyrogas_energy_fraction(temp_c, heating_rate, feedstock)
    pt.pyrogas_energy_kwh_d    = round(feedstock_kwh_d * pt.pyrogas_energy_fraction, 0)

    pfas_lev, _, _ = pfas_confidence(temp_c, has_secondary_oxidation, secondary_temp_c)
    pt.pfas_confidence = pfas_lev

    # Stable carbon fraction (eligible for carbon credits)
    # R50 > 0.55 → stable; use R50 as weight on fixed carbon fraction
    r50 = pt.carbon_stability_r50
    if r50 >= 0.55:
        stability_weight = (r50 - 0.55) / (0.85 - 0.55)  # 0 at R50=0.55, 1 at R50=0.85
        pt.stable_carbon_fraction = pt.fixed_carbon_pct / 100 * (0.50 + 0.50 * stability_weight)
    else:
        pt.stable_carbon_fraction = 0.0   # Below threshold — not creditable

    # Stable C per tDS
    biochar_yield_frac = pt.biochar_yield_pct / 100
    pt.stable_carbon_t_per_tds = biochar_yield_frac * pt.stable_carbon_fraction
    pt.co2e_per_tds = pt.stable_carbon_t_per_tds * (44 / 12)  # C → CO2e

    # --- ENERGY VALUE ---
    # Pyrogas → electricity at PYROGAS_ELECTRICAL_EFF
    electricity_kwh_d = pt.pyrogas_energy_kwh_d * PYROGAS_ELECTRICAL_EFF
    pt.pyrogas_electricity_kwh_d = round(electricity_kwh_d, 0)
    energy_revenue_d = electricity_kwh_d * el_price_kwh
    pt.energy_value_per_tds = round(energy_revenue_d / ds_tpd, 2) if ds_tpd > 0 else 0

    # --- BIOCHAR VALUE ---
    # Market price applied to biochar yield (t/tDS)
    biochar_revenue_per_tds = (pt.biochar_yield_pct / 100) * biochar_price_per_t
    pt.biochar_market_grade   = _grade_for_temp(temp_c)
    pt.biochar_price_per_tonne = biochar_price_per_t
    pt.biochar_value_per_tds  = round(biochar_revenue_per_tds, 2)

    # --- CARBON CREDIT VALUE ---
    carbon_revenue_per_tds = pt.co2e_per_tds * carbon_price_per_tco2e
    pt.carbon_credit_per_tds = round(carbon_revenue_per_tds, 2)

    # --- TOTAL VALUE ---
    pt.total_value_per_tds = round(
        pt.energy_value_per_tds + pt.biochar_value_per_tds + pt.carbon_credit_per_tds, 2
    )
    pt.total_value_per_day = round(pt.total_value_per_tds * ds_tpd, 0)

    # Mode label
    if temp_c < 500:
        pt.operating_mode = "LOW TEMP MODE"
    elif temp_c <= 650:
        pt.operating_mode = "MID TEMP MODE"
    else:
        pt.operating_mode = "HIGH TEMP MODE"

    return pt


def _grade_for_temp(temp_c: float) -> str:
    if temp_c < 500:
        return "low_grade"
    elif temp_c <= 650:
        return "soil_amendment"
    else:
        return "engineered_carbon"


# ---------------------------------------------------------------------------
# OPTIMISATION
# ---------------------------------------------------------------------------

def _find_optimal(points: list, objective: str) -> tuple:
    """Return (optimal_temp, value_at_optimal) for a given objective."""
    if objective == "energy":
        best = max(points, key=lambda p: p.energy_value_per_tds)
    elif objective == "product":
        best = max(points, key=lambda p: p.biochar_value_per_tds)
    else:  # balanced — maximise total
        best = max(points, key=lambda p: p.total_value_per_tds)
    return (best.temp_c, best.total_value_per_tds)


def _recommend_mode(mid_pt: TradeOffPoint,
                     pfas_present: str,
                     has_secondary_oxidation: bool) -> tuple:
    """Return (mode_label, recommended_temp_c)."""
    if pfas_present == "confirmed":
        return ("COMPLIANCE-LED", 720.0)

    # Determine which component dominates at mid-temp
    e = mid_pt.energy_value_per_tds
    b = mid_pt.biochar_value_per_tds
    c = mid_pt.carbon_credit_per_tds
    total = e + b + c

    if total <= 0:
        return ("BALANCED", 575.0)

    e_pct = e / total
    b_pct = b / total
    c_pct = c / total

    if e_pct > 0.60:
        return ("ENERGY-LED", 700.0)
    elif b_pct > 0.60:
        return ("PRODUCT-LED", 450.0)
    elif c_pct > 0.40:
        return ("PRODUCT-LED", 650.0)  # Carbon-led → high temp for stability
    else:
        return ("BALANCED", 575.0)


def _rationale(mode: str, pt: TradeOffPoint, ds_tpd: float,
                market_def: dict, carbon_price: float) -> str:
    total = pt.total_value_per_tds
    e_pct = pt.energy_value_per_tds  / total * 100 if total > 0 else 0
    b_pct = pt.biochar_value_per_tds / total * 100 if total > 0 else 0
    c_pct = pt.carbon_credit_per_tds / total * 100 if total > 0 else 0

    rationale = {
        "ENERGY-LED": (
            f"At {pt.temp_c:.0f}°C, energy recovery from pyrogas dominates "
            f"({e_pct:.0f}% of total value = ${pt.energy_value_per_tds:.0f}/tDS). "
            f"Biochar yield is {pt.biochar_yield_pct:.0f}% DS but the market value "
            f"is secondary to energy recovery at this operating mode. "
            "Recommended when electricity price is high and product market is uncertain."
        ),
        "PRODUCT-LED": (
            f"At {pt.temp_c:.0f}°C, biochar value dominates "
            f"({b_pct:.0f}% of total = ${pt.biochar_value_per_tds:.0f}/tDS). "
            f"Yield = {pt.biochar_yield_pct:.0f}% DS at ${market_def['price_mid']:.0f}/t "
            f"({market_def['label']}). "
            "Recommended when a confirmed biochar offtake agreement is in place."
        ),
        "BALANCED": (
            f"At {pt.temp_c:.0f}°C, value is distributed: "
            f"energy {e_pct:.0f}% (${pt.energy_value_per_tds:.0f}/tDS), "
            f"biochar {b_pct:.0f}% (${pt.biochar_value_per_tds:.0f}/tDS), "
            f"carbon credits {c_pct:.0f}% (${pt.carbon_credit_per_tds:.0f}/tDS). "
            "Total: ${:.0f}/tDS. Recommended when no single market is confirmed.".format(
                pt.total_value_per_tds)
        ),
        "COMPLIANCE-LED": (
            f"PFAS confirmed: compliance drives operating mode. "
            f"At {pt.temp_c:.0f}°C with secondary oxidation, ITS PFAS destruction "
            "is achievable. Energy and product value are secondary to "
            "regulatory compliance."
        ),
    }
    return rationale.get(mode, rationale["BALANCED"])


def _build_comparison_table(low: TradeOffPoint, mid: TradeOffPoint,
                              high: TradeOffPoint, market_def: dict) -> dict:
    """Build comparison table for display."""
    def row(pt: TradeOffPoint) -> dict:
        return {
            "temp_c":            pt.temp_c,
            "mode":              pt.operating_mode,
            "biochar_yield_pct": pt.biochar_yield_pct,
            "biochar_cv_mj_kg":  pt.biochar_cv_mj_per_kg,
            "fixed_carbon_pct":  pt.fixed_carbon_pct,
            "stability_r50":     pt.carbon_stability_r50,
            "N_retention_pct":   pt.N_retention_pct,
            "pfas_confidence":   pt.pfas_confidence,
            "energy_val_per_tds": pt.energy_value_per_tds,
            "biochar_val_per_tds": pt.biochar_value_per_tds,
            "carbon_val_per_tds":  pt.carbon_credit_per_tds,
            "total_val_per_tds":   pt.total_value_per_tds,
            "best_for": (
                "Soil amendment, nutrient recovery, maximum yield" if pt.temp_c <= 500 else
                "Balanced: soil amendment, flexible market" if pt.temp_c <= 650 else
                "Carbon credits, engineered carbon, PFAS compliance"
            ),
        }
    return {
        "LOW_TEMP  (450°C)": row(low),
        "MID_TEMP  (575°C)": row(mid),
        "HIGH_TEMP (700°C)": row(high),
    }
