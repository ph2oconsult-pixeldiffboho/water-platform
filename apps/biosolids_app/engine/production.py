"""
Production layer.
COD-based sludge production model with population/flow growth projection.
Feeds into the full 5-layer lifecycle model.

References: M&E 5th ed. Tables 8-14, 10-8, 13-5.
ph2o Consulting — BioPoint v1
"""

from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# DATACLASSES
# ---------------------------------------------------------------------------

@dataclass
class ProductionInputs:
    """Sludge production inputs — two modes: direct or COD-derived."""
    # --- MODE ---
    production_mode: str = "DIRECT"      # "DIRECT" | "COD"

    # --- DIRECT MODE ---
    # User supplies sludge production directly (already in sizing inputs)
    # Production layer uses this for growth projection only

    # --- COD MODE ---
    flow_ML_d: Optional[float] = None           # Influent flow ML/d
    cod_influent_mg_L: Optional[float] = None   # Influent COD mg/L
    cod_removal_pct: float = 90.0               # COD removal efficiency %
    bod_cod_ratio: float = 0.55                 # BOD/COD ratio (typical municipal)

    # Sludge yield coefficients (M&E Table 8-14)
    # Primary: ~0.6 kg DS / kg COD removed in primary treatment
    # Secondary (WAS): ~0.3–0.4 kg DS / kg COD removed in biological treatment
    primary_yield_kg_DS_per_kgCOD: float = 0.60
    secondary_yield_kg_DS_per_kgCOD: float = 0.35

    # --- GROWTH ---
    growth_rate_pct_yr: float = 2.0             # Annual growth rate %
    projection_years: int = 20                  # Projection horizon

    # --- CURRENT BASELINE (always required) ---
    current_ts_kg_d: Optional[float] = None     # Current TS production kg/d


@dataclass
class ProductionResult:
    """Sludge production baseline and growth projection."""

    # --- CURRENT ---
    current_ts_kg_d: float = 0.0
    current_ts_t_yr: float = 0.0
    current_vs_kg_d: float = 0.0

    # --- COD-DERIVED (if COD mode) ---
    cod_load_kg_d: float = 0.0
    cod_removed_kg_d: float = 0.0
    ps_production_kg_d: float = 0.0         # Primary sludge from COD removal
    was_production_kg_d: float = 0.0        # WAS from biological treatment
    cod_derived: bool = False

    # --- GROWTH PROJECTION ---
    growth_rate_pct_yr: float = 2.0
    projection_years: int = 20
    future_ts_kg_d: float = 0.0             # At end of projection horizon
    future_ts_t_yr: float = 0.0
    growth_factor: float = 1.0              # future / current
    growth_pressure: str = ""               # "LOW" | "MODERATE" | "HIGH" | "CRITICAL"

    # Year-by-year projection (list of (year, t_yr))
    projection: list = field(default_factory=list)

    # --- CONFIDENCE ---
    input_confidence: str = ""              # "HIGH" | "MEDIUM" | "LOW"
    confidence_note: str = ""


# ---------------------------------------------------------------------------
# MAIN ENGINE
# ---------------------------------------------------------------------------

def run_production(inputs: ProductionInputs, vs_ts_ratio: float = 0.78) -> ProductionResult:
    """
    Compute sludge production baseline and growth projection.
    vs_ts_ratio: from feedstock profile.
    """
    # --- CURRENT TS ---
    if inputs.production_mode == "COD" and inputs.flow_ML_d and inputs.cod_influent_mg_L:
        result = _cod_mode(inputs, vs_ts_ratio)
    else:
        result = _direct_mode(inputs, vs_ts_ratio)

    # --- GROWTH PROJECTION ---
    r = inputs.growth_rate_pct_yr / 100.0
    n = inputs.projection_years
    future_kg_d = result.current_ts_kg_d * ((1 + r) ** n)
    growth_factor = future_kg_d / result.current_ts_kg_d if result.current_ts_kg_d > 0 else 1.0

    # Year-by-year
    projection = []
    for yr in range(0, n + 1, 5):
        ts_t_yr = result.current_ts_kg_d * ((1 + r) ** yr) * 365 / 1000
        projection.append((yr, round(ts_t_yr, 0)))

    # Growth pressure classification
    if growth_factor >= 2.0:
        pressure = "CRITICAL"
    elif growth_factor >= 1.5:
        pressure = "HIGH"
    elif growth_factor >= 1.25:
        pressure = "MODERATE"
    else:
        pressure = "LOW"

    result.future_ts_kg_d = round(future_kg_d, 0)
    result.future_ts_t_yr = round(future_kg_d * 365 / 1000, 0)
    result.growth_factor = round(growth_factor, 2)
    result.growth_rate_pct_yr = inputs.growth_rate_pct_yr
    result.projection_years = n
    result.growth_pressure = pressure
    result.projection = projection

    return result


def _cod_mode(inputs: ProductionInputs, vs_ts_ratio: float) -> ProductionResult:
    """COD-based sludge production estimate."""
    flow_L_d = inputs.flow_ML_d * 1e6
    cod_load = flow_L_d * inputs.cod_influent_mg_L / 1e6    # kg COD/d
    cod_removed = cod_load * inputs.cod_removal_pct / 100.0

    # Split: primary removes ~35% of COD as PS; remainder is biological
    primary_cod_removed = cod_removed * 0.35
    secondary_cod_removed = cod_removed * 0.65

    ps_kg_d = primary_cod_removed * inputs.primary_yield_kg_DS_per_kgCOD
    was_kg_d = secondary_cod_removed * inputs.secondary_yield_kg_DS_per_kgCOD
    total_ts = ps_kg_d + was_kg_d

    return ProductionResult(
        current_ts_kg_d=round(total_ts, 0),
        current_ts_t_yr=round(total_ts * 365 / 1000, 0),
        current_vs_kg_d=round(total_ts * vs_ts_ratio, 0),
        cod_load_kg_d=round(cod_load, 0),
        cod_removed_kg_d=round(cod_removed, 0),
        ps_production_kg_d=round(ps_kg_d, 0),
        was_production_kg_d=round(was_kg_d, 0),
        cod_derived=True,
        input_confidence="MEDIUM",
        confidence_note=(
            f"Sludge production estimated from COD load ({inputs.cod_influent_mg_L:.0f} mg/L) "
            f"at {inputs.flow_ML_d:.1f} ML/d. Yield coefficients: PS {inputs.primary_yield_kg_DS_per_kgCOD} "
            f"kg DS/kg COD, WAS {inputs.secondary_yield_kg_DS_per_kgCOD} kg DS/kg COD (M&E Table 8-14). "
            f"Validate against plant records."
        ),
    )


def _direct_mode(inputs: ProductionInputs, vs_ts_ratio: float) -> ProductionResult:
    """Direct TS input — user supplies current production."""
    ts = inputs.current_ts_kg_d or 0.0
    return ProductionResult(
        current_ts_kg_d=round(ts, 0),
        current_ts_t_yr=round(ts * 365 / 1000, 0),
        current_vs_kg_d=round(ts * vs_ts_ratio, 0),
        cod_derived=False,
        input_confidence="HIGH",
        confidence_note="Sludge production from direct plant measurement.",
    )
