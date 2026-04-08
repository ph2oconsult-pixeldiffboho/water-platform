"""
BioPoint V1 — Integrated Thermal & Biochar Decision Engine (v24Z89).

Integrates three outputs of thermal systems into a single decision framework:
  1. Energy recovery
  2. Carbon product (biochar / hydrochar / ash)
  3. Regulatory compliance (PFAS destruction)

Evaluates the explicit trade-off between energy maximisation and carbon
product retention, classifies the system's dominant value pathway, and
produces a 5-question board-ready output.

Parts per spec (v24Z89):
  Part 1: System validation (PFAS destruction capability)
  Part 2: Drying requirement assessment
  Part 3: Carbon product engine (yield, nutrients, marketability)
  Part 4: Trade-off engine (energy vs carbon retention)
  Part 5: Final system classification
  Part 6: Board output (5 binary/short questions)

ph2o Consulting — BioPoint V1
"""

from dataclasses import dataclass, field
from typing import Optional
import math


# ---------------------------------------------------------------------------
# PRODUCT DEFINITIONS
# ---------------------------------------------------------------------------

# Biochar / carbon product types and their market context
PRODUCT_TYPES = {
    "biochar_soil_amendment": {
        "label":       "Biochar — Soil Amendment",
        "value_low":    50,    # $/tonne
        "value_mid":   150,
        "value_high":  350,
        "market_size": "Established and growing (Australia, EU, US)",
        "barrier":     "PFAS contamination, regulatory approval, consistency",
        "esg_premium": True,
    },
    "biochar_fertiliser": {
        "label":       "Biochar — Fertiliser / Nutrient-Enhanced",
        "value_low":   100,
        "value_mid":   250,
        "value_high":  500,
        "market_size": "Developing — premium segment",
        "barrier":     "Nutrient loading, PFAS, regulatory classification",
        "esg_premium": True,
    },
    "biochar_engineered": {
        "label":       "Biochar — Engineered Carbon (industrial)",
        "value_low":   200,
        "value_mid":   500,
        "value_high":  1200,
        "market_size": "Niche — construction, water treatment, cement co-fuel",
        "barrier":     "Specification consistency, PFAS, metal leaching",
        "esg_premium": False,
    },
    "hydrochar_fuel": {
        "label":       "Hydrochar — Solid Fuel",
        "value_low":    30,
        "value_mid":    80,
        "value_high":  150,
        "market_size": "Industrial fuel markets; cement kilns",
        "barrier":     "Energy density consistency, PFAS, metals",
        "esg_premium": False,
    },
    "hydrochar_soil": {
        "label":       "Hydrochar — Soil Application",
        "value_low":    20,
        "value_mid":    60,
        "value_high":  120,
        "market_size": "Limited; regulatory uncertainty re PFAS",
        "barrier":     "PFAS concentration, stability lower than biochar",
        "esg_premium": True,
    },
    "ash_construction": {
        "label":       "Ash — Construction Aggregate",
        "value_low":     0,
        "value_mid":    20,
        "value_high":   50,
        "market_size": "Existing (cement, road base)",
        "barrier":     "P-content, metals, PFAS (if not destroyed)",
        "esg_premium": False,
    },
    "ash_pfas_landfill": {
        "label":       "Ash — Landfill (PFAS-classified)",
        "value_low":  -200,   # Disposal cost
        "value_mid":  -120,
        "value_high":  -50,
        "market_size": "Regulated disposal only",
        "barrier":     "Cost sink — not a value stream",
        "esg_premium": False,
    },
    "none": {
        "label":       "No Recoverable Product",
        "value_low":    0,
        "value_mid":    0,
        "value_high":   0,
        "market_size": "N/A",
        "barrier":      "No product",
        "esg_premium": False,
    },
}

# Pyrolysis temperature determines biochar carbon content and surface area
# Lower temp (400–550°C): lower fixed carbon, higher nutrient retention (N, P, K)
# Higher temp (600–750°C): higher fixed carbon, lower nutrient retention
# Reference: IBI Biochar Standards; Lehmann & Joseph (2015)
PYROLYSIS_TEMP_PROFILES = {
    "low":    {"temp_c": 450, "fixed_carbon_pct": 40, "N_ret": 0.70, "P_ret": 0.90, "K_ret": 0.85,
               "biochar_yield_pct_ds": 40, "product_type": "biochar_fertiliser"},
    "medium": {"temp_c": 600, "fixed_carbon_pct": 55, "N_ret": 0.45, "P_ret": 0.85, "K_ret": 0.80,
               "biochar_yield_pct_ds": 30, "product_type": "biochar_soil_amendment"},
    "high":   {"temp_c": 750, "fixed_carbon_pct": 70, "N_ret": 0.20, "P_ret": 0.75, "K_ret": 0.70,
               "biochar_yield_pct_ds": 22, "product_type": "biochar_engineered"},
}

# Gasification product profiles
GASIFICATION_PRODUCT = {
    "vitrified_mineral": {"fixed_carbon_pct": 5, "yield_pct_ds": 25, "product_type": "ash_construction"},
    "char_fines":        {"fixed_carbon_pct": 20, "yield_pct_ds": 10, "product_type": "biochar_engineered"},
}

# HTC hydrochar profile
HTC_HYDROCHAR = {
    "fixed_carbon_pct": 40,
    "N_ret": 0.60, "P_ret": 0.95, "K_ret": 0.80,
    "yield_pct_ds": 60,   # Higher yield as less volatile loss
    "product_type_pfas_negative": "hydrochar_soil",
    "product_type_pfas_positive": "hydrochar_fuel",  # Land application precluded
}

# Incineration ash
INCINERATION_ASH = {
    "fixed_carbon_pct": 2,
    "P_content_pct": 12,   # P concentrates in ash (~12% as P2O5)
    "yield_pct_ds": 35,    # Ash as % of DS input
    "product_type_no_pfas": "ash_construction",
    "product_type_pfas":    "ash_pfas_landfill",  # PFAS ash may need classified disposal
    # Note: At >850°C PFAS is destroyed IN the combustion zone
    # but ash characterisation still required
}

# Typical sludge nutrient fractions (% of DS)
SLUDGE_NUTRIENTS = {
    "N_pct_ds":  4.0,   # Total nitrogen in DS
    "P_pct_ds":  2.5,   # Total phosphorus
    "K_pct_ds":  0.4,   # Potassium
    "S_pct_ds":  1.2,   # Sulphur
}


# ---------------------------------------------------------------------------
# DATACLASSES
# ---------------------------------------------------------------------------

@dataclass
class CarbonProductAssessment:
    """
    Assessment of the carbon product (biochar, hydrochar, or ash) from one pathway.
    """
    pathway_type: str = ""
    product_label: str = ""
    product_type_key: str = "none"

    # Yield
    biochar_yield_pct_ds: float = 0.0       # % of dry feed that becomes product
    biochar_yield_t_per_day: float = 0.0    # Actual product tonnes/day

    # Carbon content
    fixed_carbon_pct: float = 0.0           # % fixed carbon in product
    carbon_in_product_t_per_day: float = 0.0
    co2e_sequestered_t_per_day: float = 0.0 # Linked from carbon_balance

    # Nutrients retained in product (kg/day)
    N_retained_kg_d: float = 0.0
    P_retained_kg_d: float = 0.0
    K_retained_kg_d: float = 0.0

    # PFAS marketability gate
    pfas_present: str = "unknown"            # unknown / confirmed / negative
    pfas_destroyed: bool = False             # True if ITS L4 (or validated L3)
    product_marketable: str = ""             # YES / CONDITIONAL / NO
    marketability_note: str = ""

    # Market assessment
    market_value_low: float = 0.0            # $/tonne product
    market_value_mid: float = 0.0
    market_value_high: float = 0.0
    market_confidence: str = "low"           # low / moderate / high
    market_revenue_low_yr: float = 0.0       # $/yr at low value
    market_revenue_mid_yr: float = 0.0
    market_revenue_high_yr: float = 0.0
    market_size_note: str = ""

    # Product quality flags
    nutrient_dense: bool = False             # N+P significant?
    suitable_for_agriculture: bool = False
    requires_validation: bool = True

    # Summary
    product_summary: str = ""


@dataclass
class EnergyVsProductTradeOff:
    """
    Explicit energy vs carbon product trade-off for one pathway.
    Shows what can be tuned and what the operating envelope is.
    """
    pathway_type: str = ""

    # Energy outputs
    feedstock_energy_kwh_d: float = 0.0
    recoverable_energy_kwh_d: float = 0.0    # After drying and process
    energy_recovery_pct: float = 0.0         # % of feedstock energy recovered

    # Product carbon
    carbon_in_product_t_d: float = 0.0
    carbon_in_gas_t_d: float = 0.0
    carbon_as_energy_pct: float = 0.0        # % of feedstock C converted to energy gas

    # The trade-off: higher temp → more energy, less char; lower temp → more char, less energy
    tuning_lever: str = ""                   # "temperature" / "residence_time" / "none"
    energy_led_setting: str = ""             # Description of energy-maximising config
    product_led_setting: str = ""            # Description of product-maximising config
    balanced_setting: str = ""

    # Operating envelope
    can_tune_toward_energy: bool = False
    can_tune_toward_product: bool = False

    # Financial impact of tuning (delta from base)
    energy_led_revenue_adj_yr: float = 0.0  # Additional electricity revenue
    product_led_revenue_adj_yr: float = 0.0 # Additional biochar revenue


@dataclass
class ThermalBiocharResult:
    """
    Full integrated assessment for one thermal pathway.
    Combines ITS classification, drying, carbon product, and trade-off.
    """
    pathway_type: str = ""
    pathway_name: str = ""
    flowsheet_id: str = ""

    # Part 1: System validation
    its_level: int = 0
    its_label: str = ""
    pfas_destruction: str = ""              # VALIDATED / DESIGN-BASED / NOT SUITABLE
    pfas_evidence: str = ""

    # Part 2: Drying
    drying_required: bool = False
    drying_achievable: bool = False         # True if PASS gate or no drying needed
    drying_note: str = ""

    # Part 3: Carbon product
    product: Optional[CarbonProductAssessment] = None

    # Part 4: Trade-off
    trade_off: Optional[EnergyVsProductTradeOff] = None

    # Part 5: System classification
    system_classification: str = ""        # ENERGY-LED / PRODUCT-LED / COMPLIANCE-LED / BALANCED
    classification_rationale: str = ""

    # Part 6: Board output (5 questions)
    board_pfas_destroyed: str = ""          # YES / CONDITIONAL / NO
    board_drying_achievable: str = ""       # YES / NO / CONDITIONAL
    board_biochar_marketable: str = ""      # YES / CONDITIONAL / NO
    board_dominant_value: str = ""          # Short phrase
    board_recommended_strategy: str = ""    # Operating strategy recommendation

    # Scoring signal
    integrated_value_score: float = 0.0    # Composite score for ranking
    green_finance_eligible: bool = False


@dataclass
class ThermalBiocharSystem:
    """System-level integrated assessment across all relevant pathways."""
    results: dict = field(default_factory=dict)   # pathway_type -> ThermalBiocharResult

    # System-level findings
    best_pfas_pathway: str = ""
    best_product_pathway: str = ""
    best_energy_pathway: str = ""
    best_balanced_pathway: str = ""

    # Lookup
    _by_type: dict = field(default_factory=dict)

    def get(self, pathway_type: str) -> Optional[ThermalBiocharResult]:
        return self._by_type.get(pathway_type)


# ---------------------------------------------------------------------------
# MAIN ENGINE
# ---------------------------------------------------------------------------

def run_thermal_biochar_engine(
    flowsheets: list,
    feedstock_inputs,
    strategic_inputs,
) -> ThermalBiocharSystem:
    """
    Run the integrated thermal & biochar decision engine.

    Evaluates pyrolysis, gasification, incineration, HTC, and THP+incineration.
    Draws on ITS classification, drying dominance, and carbon balance already
    computed by the BioPoint V1 runner.
    """
    fs_in = feedstock_inputs
    ds_tpd   = fs_in.dry_solids_tpd
    vs_pct   = fs_in.volatile_solids_percent
    pfas_st  = fs_in.pfas_present       # unknown / confirmed / negative
    market_conf = getattr(strategic_inputs, 'biochar_market_confidence', 'low')
    cc_per_tco2e = getattr(strategic_inputs, 'carbon_credit_value_per_tco2e', 40.0)

    results = {}
    by_type = {}

    target_ptypes = {'pyrolysis', 'gasification', 'incineration',
                     'HTC', 'HTC_sidestream', 'thp_incineration'}

    for fs in flowsheets:
        ptype = fs.pathway_type
        if ptype not in target_ptypes:
            continue

        result = _build_pathway_result(
            fs, ptype, ds_tpd, vs_pct, pfas_st,
            market_conf, cc_per_tco2e
        )
        results[ptype] = result
        by_type[ptype] = result

        # Attach to flowsheet
        fs.thermal_biochar = result

    # System-level bests
    system = ThermalBiocharSystem(results=results, _by_type=by_type)
    _assign_system_bests(system, results)
    return system


# ---------------------------------------------------------------------------
# PATHWAY RESULT BUILDER
# ---------------------------------------------------------------------------

def _build_pathway_result(
    fs, ptype: str, ds_tpd: float, vs_pct: float,
    pfas_status: str, market_conf: str, cc_per_tco2e: float
) -> ThermalBiocharResult:

    its  = fs.its_classification
    dd   = fs.drying_dominance
    cb   = fs.carbon_balance

    result = ThermalBiocharResult(
        pathway_type=ptype,
        pathway_name=fs.name,
        flowsheet_id=fs.flowsheet_id,
    )

    # --- PART 1: SYSTEM VALIDATION ---
    result.its_level = its.its_level
    result.its_label = its.its_level_label

    if its.its_level == 4:
        result.pfas_destruction = "VALIDATED"
        result.pfas_evidence = (
            "Incineration at >850°C: PFAS destruction validated at full scale. "
            "US EPA, UK EA, and Australian NEMP all reference FBF incineration "
            "as the confirmed thermal disposal route for PFAS-contaminated biosolids."
        )
    elif its.its_level == 3:
        result.pfas_destruction = "DESIGN-BASED"
        result.pfas_evidence = (
            "ITS configuration (primary reactor + secondary oxidation ≥850°C). "
            "Design-capable of PFAS destruction. Independent validation testing "
            "required before regulatory acceptance."
        )
    elif its.its_level == 2:
        result.pfas_destruction = "NOT SUITABLE (without upgrade)"
        result.pfas_evidence = (
            "Standard thermal conversion without validated secondary oxidation stage. "
            "PFAS outcome is UNCERTAIN — redistribution between char, gas, and "
            "condensate likely. Cannot be accepted as PFAS destruction route "
            "without independent testing AND secondary oxidation stage confirmation."
        )
    else:  # L1
        result.pfas_destruction = "NOT SUITABLE"
        result.pfas_evidence = (
            "Non-thermal or low-temperature process. PFAS is transferred to the "
            "output product — not destroyed. Not acceptable where PFAS disposal "
            "restrictions apply."
        )

    # --- PART 2: DRYING ---
    result.drying_required = dd.drying_required
    drying_achievable = dd.can_rank_as_preferred  # True = PASS gate
    result.drying_achievable = drying_achievable

    if not dd.drying_required:
        result.drying_note = (
            f"No pre-drying required — wet-feed process. "
            "Drying energy constraint does not apply to this pathway."
        )
        result.board_drying_achievable = "YES (no drying required)"
    elif drying_achievable:
        result.drying_note = (
            f"Drying feasibility: PASS. "
            f"Internal heat covers {dd.internal_coverage_pct:.0f}% of demand. "
            f"Feed DS {dd.feed_ds_pct:.0f}% → target {dd.target_ds_pct:.0f}% DS."
        )
        result.board_drying_achievable = "YES"
    else:
        nd = dd.ds_for_energy_neutrality_pct
        result.drying_note = (
            f"Drying feasibility: FAIL at {dd.feed_ds_pct:.0f}% DS. "
            f"Drying demand = {dd.drying_as_pct_of_feedstock_energy:.0f}% of feedstock energy "
            f"({dd.drying_dominance_label}). "
            f"Internal coverage: {dd.internal_coverage_pct:.0f}%. "
            + (f"Energy neutrality requires DS ≥ {nd:.0f}%." if nd else
               "Energy neutrality not achievable through standard preconditioning.")
        )
        result.board_drying_achievable = (
            f"NO at current DS% — requires {nd:.0f}% DS" if nd else "NO"
        )

    # --- PART 3: CARBON PRODUCT ---
    product = _build_product_assessment(
        ptype, ds_tpd, vs_pct, pfas_status, market_conf, cc_per_tco2e, cb, its
    )
    result.product = product

    # Board: biochar marketable?
    result.board_biochar_marketable = product.product_marketable

    # --- PART 4: TRADE-OFF ---
    tradeoff = _build_trade_off(ptype, fs, dd, cb, ds_tpd, vs_pct)
    result.trade_off = tradeoff

    # --- PART 5: SYSTEM CLASSIFICATION ---
    result.system_classification, result.classification_rationale = _classify_system(
        ptype, its.its_level, product, tradeoff, dd, pfas_status
    )

    # --- PART 6: BOARD OUTPUT ---
    # Q1: PFAS destroyed?
    if its.its_level == 4:
        result.board_pfas_destroyed = "YES"
    elif its.its_level == 3:
        result.board_pfas_destroyed = "CONDITIONAL (design-based — validate)"
    else:
        result.board_pfas_destroyed = "NO"

    # Q4: Dominant value pathway
    sc = result.system_classification
    if sc == "COMPLIANCE-LED":
        result.board_dominant_value = "Regulatory compliance (PFAS destruction)"
    elif sc == "PRODUCT-LED":
        result.board_dominant_value = (
            f"Carbon product revenue (biochar at "
            f"${product.market_value_mid:.0f}/t mid estimate)"
        )
    elif sc == "ENERGY-LED":
        result.board_dominant_value = "Energy recovery and avoided disposal cost"
    else:
        result.board_dominant_value = "Balanced: disposal reduction + carbon value + compliance"

    # Q5: Recommended strategy
    result.board_recommended_strategy = _recommended_strategy(
        ptype, sc, drying_achievable, product, its.its_level, pfas_status
    )

    # Green finance
    result.green_finance_eligible = (
        its.its_level >= 3 or
        (ptype in ('pyrolysis', 'HTC') and product.co2e_sequestered_t_per_day > 0)
    )

    # Integrated value score
    result.integrated_value_score = _integrated_score(
        product, tradeoff, its.its_level, drying_achievable
    )

    return result


# ---------------------------------------------------------------------------
# CARBON PRODUCT ASSESSMENT
# ---------------------------------------------------------------------------

def _build_product_assessment(
    ptype: str, ds_tpd: float, vs_pct: float,
    pfas_status: str, market_conf: str,
    cc_per_tco2e: float, cb, its
) -> CarbonProductAssessment:

    pa = CarbonProductAssessment(
        pathway_type=ptype,
        pfas_present=pfas_status,
        pfas_destroyed=(its.its_level >= 3),  # L3 design-based, L4 validated
    )
    pa.market_confidence = market_conf

    # Nutrients in feed (kg/day)
    N_feed = ds_tpd * 1000 * SLUDGE_NUTRIENTS["N_pct_ds"] / 100
    P_feed = ds_tpd * 1000 * SLUDGE_NUTRIENTS["P_pct_ds"] / 100
    K_feed = ds_tpd * 1000 * SLUDGE_NUTRIENTS["K_pct_ds"] / 100

    # --- PYROLYSIS ---
    if ptype == "pyrolysis":
        prof = PYROLYSIS_TEMP_PROFILES["medium"]  # default
        pa.product_label    = "Biochar"
        pa.product_type_key = prof["product_type"]
        pa.biochar_yield_pct_ds = prof["biochar_yield_pct_ds"]
        pa.biochar_yield_t_per_day = ds_tpd * prof["biochar_yield_pct_ds"] / 100
        pa.fixed_carbon_pct = prof["fixed_carbon_pct"]
        pa.carbon_in_product_t_per_day = cb.carbon_to_char_t_per_day
        pa.co2e_sequestered_t_per_day  = cb.co2e_sequestered_t_per_day
        pa.N_retained_kg_d  = N_feed * prof["N_ret"]
        pa.P_retained_kg_d  = P_feed * prof["P_ret"]
        pa.K_retained_kg_d  = K_feed * prof["K_ret"]
        pa.nutrient_dense   = True
        ptype_key = prof["product_type"]

    # --- GASIFICATION ---
    elif ptype == "gasification":
        pa.product_label    = "Vitrified mineral / char fines"
        pa.product_type_key = "ash_construction"
        pa.biochar_yield_pct_ds = 20.0
        pa.biochar_yield_t_per_day = ds_tpd * 0.20
        pa.fixed_carbon_pct = 5.0
        pa.carbon_in_product_t_per_day = cb.carbon_to_char_t_per_day
        pa.co2e_sequestered_t_per_day  = 0.0   # Minimal sequestration credit
        pa.N_retained_kg_d  = N_feed * 0.10    # Most N oxidised to NOx
        pa.P_retained_kg_d  = P_feed * 0.80
        pa.K_retained_kg_d  = K_feed * 0.70
        ptype_key = "ash_construction"

    # --- INCINERATION / THP+INCINERATION ---
    elif ptype in ("incineration", "thp_incineration"):
        ash_pct = INCINERATION_ASH["yield_pct_ds"]
        pa.product_label    = "Incineration ash (P-rich)"
        # PFAS at L4 is destroyed in the combustion zone
        # Ash characterisation still required for metals and residual compounds
        ptype_key = INCINERATION_ASH["product_type_no_pfas"]
        pa.product_type_key = ptype_key
        pa.biochar_yield_pct_ds = ash_pct
        pa.biochar_yield_t_per_day = ds_tpd * ash_pct / 100
        pa.fixed_carbon_pct = INCINERATION_ASH["fixed_carbon_pct"]
        pa.carbon_in_product_t_per_day = 0.0
        pa.co2e_sequestered_t_per_day  = 0.0
        pa.N_retained_kg_d  = N_feed * 0.02    # Almost all N oxidised
        pa.P_retained_kg_d  = P_feed * 0.95    # P concentrates in ash
        pa.K_retained_kg_d  = K_feed * 0.60
        pa.nutrient_dense   = True   # P-rich ash

    # --- HTC / HTC_SIDESTREAM ---
    elif ptype in ("HTC", "HTC_sidestream"):
        prof = HTC_HYDROCHAR
        # If PFAS is confirmed, land application is precluded → fuel route
        if pfas_status == "confirmed":
            ptype_key = prof["product_type_pfas_positive"]
        else:
            ptype_key = prof["product_type_pfas_negative"]
        pa.product_label    = "Hydrochar"
        pa.product_type_key = ptype_key
        pa.biochar_yield_pct_ds = prof["yield_pct_ds"]
        pa.biochar_yield_t_per_day = ds_tpd * prof["yield_pct_ds"] / 100
        pa.fixed_carbon_pct = prof["fixed_carbon_pct"]
        pa.carbon_in_product_t_per_day = cb.carbon_to_char_t_per_day
        pa.co2e_sequestered_t_per_day  = cb.co2e_sequestered_t_per_day
        pa.N_retained_kg_d  = N_feed * prof["N_ret"]
        pa.P_retained_kg_d  = P_feed * prof["P_ret"]
        pa.K_retained_kg_d  = K_feed * prof["K_ret"]
        pa.nutrient_dense   = True
    else:
        ptype_key = "none"
        pa.product_type_key = ptype_key

    # Market values
    pt_def = PRODUCT_TYPES.get(ptype_key, PRODUCT_TYPES["none"])
    pa.market_value_low  = pt_def["value_low"]
    pa.market_value_mid  = pt_def["value_mid"]
    pa.market_value_high = pt_def["value_high"]
    pa.market_size_note  = pt_def["market_size"]

    # Annual revenues
    yield_t_yr = pa.biochar_yield_t_per_day * 365
    pa.market_revenue_low_yr  = yield_t_yr * pa.market_value_low
    pa.market_revenue_mid_yr  = yield_t_yr * pa.market_value_mid
    pa.market_revenue_high_yr = yield_t_yr * pa.market_value_high

    # Carbon credit revenue (already in economics; confirm here)
    cc_revenue_yr = pa.co2e_sequestered_t_per_day * 365 * cc_per_tco2e
    pa.market_revenue_mid_yr += cc_revenue_yr  # Add carbon credit to mid

    # Agriculture suitability
    pa.suitable_for_agriculture = (
        ptype_key in ("biochar_soil_amendment", "biochar_fertiliser", "hydrochar_soil")
        and pfas_status != "confirmed"
    )

    # --- PFAS MARKETABILITY GATE ---
    if its.its_level >= 4:
        # Incineration: PFAS destroyed; ash is clean (characterisation still needed)
        if ptype_key == "ash_construction":
            pa.product_marketable = "YES"
            pa.marketability_note = (
                "PFAS destroyed at >850°C. Ash characterisation required "
                "for metals and residual compounds before construction use approval. "
                "P-rich ash has phosphate recovery potential."
            )
        else:
            pa.product_marketable = "YES"
            pa.marketability_note = "PFAS destroyed — product marketability limited only by quality specifications."
    elif its.its_level == 3:
        pa.product_marketable = "CONDITIONAL"
        pa.marketability_note = (
            "ITS design-based PFAS destruction. Marketable where destruction "
            "is validated. Independent PFAS testing of product required before "
            "agricultural or construction use in regulated markets."
        )
    elif pfas_status == "confirmed":
        pa.product_marketable = "NO"
        pa.marketability_note = (
            "PFAS CONFIRMED in feed AND pathway does not destroy PFAS. "
            "Product (biochar/hydrochar) will contain concentrated PFAS. "
            "Land application route is precluded. Product is a regulated waste, "
            "not a marketable commodity."
        )
    elif pfas_status == "unknown":
        pa.product_marketable = "CONDITIONAL"
        pa.marketability_note = (
            "PFAS status unknown. Product marketability is CONDITIONAL on "
            "PFAS characterisation result. If PFAS is confirmed in the feed, "
            "this product route closes. Commission PFAS testing before "
            "committing to a product-revenue business case."
        )
    else:
        # PFAS negative
        pa.product_marketable = "YES"
        pa.marketability_note = (
            "PFAS characterised and negative. Product marketable subject to "
            "metals, nutrient content, and regulatory approval in target market."
        )

    # Summary
    pa.product_summary = (
        f"{pa.product_label}: {pa.biochar_yield_pct_ds:.0f}% yield of DS input "
        f"= {pa.biochar_yield_t_per_day:.1f} t/day. "
        f"Fixed carbon: {pa.fixed_carbon_pct:.0f}%. "
        f"Market value: ${pa.market_value_low:.0f}–${pa.market_value_high:.0f}/t "
        f"(mid ${pa.market_value_mid:.0f}/t). "
        f"Marketable: {pa.product_marketable}."
    )

    return pa


# ---------------------------------------------------------------------------
# TRADE-OFF ENGINE
# ---------------------------------------------------------------------------

def _build_trade_off(ptype: str, fs, dd, cb, ds_tpd: float, vs_pct: float
                      ) -> EnergyVsProductTradeOff:
    t = EnergyVsProductTradeOff(pathway_type=ptype)
    t.feedstock_energy_kwh_d = dd.feedstock_energy_kwh_d
    t.carbon_in_product_t_d  = cb.carbon_to_char_t_per_day
    t.carbon_in_gas_t_d      = cb.carbon_to_gas_t_per_day

    carbon_input = cb.carbon_input_t_per_day
    if carbon_input > 0:
        t.carbon_as_energy_pct = cb.carbon_to_gas_t_per_day / carbon_input * 100
    else:
        t.carbon_as_energy_pct = 0.0

    if ptype == "pyrolysis":
        t.tuning_lever = "temperature"
        t.can_tune_toward_energy  = True
        t.can_tune_toward_product = True
        t.energy_led_setting = (
            "HIGH temperature (700–750°C): maximises syngas/pyrogas energy yield. "
            "Biochar yield falls to ~22% DS; fixed carbon rises to ~70%. "
            "Energy-led mode — lower biochar mass, higher quality per tonne."
        )
        t.product_led_setting = (
            "LOW temperature (400–500°C): maximises biochar yield (~40% DS). "
            "Higher nutrient retention (N, P, K). Lower fixed carbon (~40%). "
            "Product-led mode — more biochar mass, nutrient-rich, fertiliser grade."
        )
        t.balanced_setting = (
            "MEDIUM temperature (550–650°C): balanced yield and carbon content. "
            "~30% DS yield, ~55% fixed carbon, good nutrient retention. "
            "Soil amendment grade. Recommended for uncertain markets."
        )
        # Approximate revenue delta: high temp → +energy value but -biochar mass
        t.energy_led_revenue_adj_yr  = ds_tpd * 365 * 0.18 * 50    # +50 kWh/tDS energy
        t.product_led_revenue_adj_yr = ds_tpd * (0.40 - 0.30) * 365 * 100  # +10% yield × $100/t
    elif ptype == "gasification":
        t.tuning_lever = "temperature"
        t.can_tune_toward_energy  = True
        t.can_tune_toward_product = False  # Product is mineral, not tunable to carbon
        t.energy_led_setting = (
            "Higher temperature (900–1000°C): maximises syngas yield, approaches "
            "full carbon-to-gas conversion. Vitrified mineral residue."
        )
        t.product_led_setting = "Not applicable — gasification does not produce a carbon-rich product."
        t.balanced_setting = "Optimise for syngas quality and mineral product specification."
    elif ptype in ("incineration", "thp_incineration"):
        t.tuning_lever = "none"
        t.can_tune_toward_energy = True
        t.can_tune_toward_product = False  # Ash yield is fixed; no carbon product
        t.energy_led_setting = "Maximise steam/electrical output from heat recovery."
        t.product_led_setting = (
            "Not applicable — all carbon is oxidised. "
            "Product value is in P-recovery from ash, not carbon."
        )
        t.balanced_setting = (
            "Optimise heat recovery + P-recovery from ash. "
            "These are complementary, not competing."
        )
    elif ptype in ("HTC", "HTC_sidestream"):
        t.tuning_lever = "temperature"
        t.can_tune_toward_energy  = False  # HTC energy is process heat, not exported
        t.can_tune_toward_product = True
        t.energy_led_setting = (
            "HTC is not primarily an energy pathway — process heat is internal. "
            "Energy surplus is minimal."
        )
        t.product_led_setting = (
            "Optimise for hydrochar quality: higher temperature (220–260°C) "
            "improves hydrophobicity and energy density; lower (180–200°C) "
            "retains more nutrients for agricultural application."
        )
        t.balanced_setting = (
            "Medium operating temperature (200–220°C). "
            "Moderate hydrochar quality, maximum nutrient retention."
        )

    # Recoverable energy estimate (approximate)
    if ptype in ("pyrolysis", "gasification"):
        t.recoverable_energy_kwh_d = t.feedstock_energy_kwh_d * 0.25
    elif ptype in ("incineration", "thp_incineration"):
        t.recoverable_energy_kwh_d = t.feedstock_energy_kwh_d * 0.35
    else:
        t.recoverable_energy_kwh_d = 0.0

    t.energy_recovery_pct = (
        t.recoverable_energy_kwh_d / t.feedstock_energy_kwh_d * 100
        if t.feedstock_energy_kwh_d > 0 else 0.0
    )

    return t


# ---------------------------------------------------------------------------
# SYSTEM CLASSIFICATION (Part 5)
# ---------------------------------------------------------------------------

def _classify_system(ptype: str, its_level: int, product: CarbonProductAssessment,
                      trade_off: EnergyVsProductTradeOff, dd, pfas_status: str
                      ) -> tuple:
    """Return (classification_label, rationale)."""

    # COMPLIANCE-LED: PFAS confirmed or ITS/incineration with confirmed PFAS
    if pfas_status == "confirmed" and its_level >= 3:
        return (
            "COMPLIANCE-LED",
            "PFAS confirmed in feed. Regulatory compliance (PFAS destruction) "
            "is the primary driver — system is selected for its compliance capability, "
            "not its energy or product economics."
        )

    # PRODUCT-LED: Significant biochar value, good marketability
    if (ptype in ("pyrolysis", "HTC", "HTC_sidestream") and
            product.product_marketable in ("YES", "CONDITIONAL") and
            product.market_value_mid > 100 and
            product.biochar_yield_pct_ds >= 25):
        return (
            "PRODUCT-LED",
            f"Carbon product ({product.product_label}) at ${product.market_value_mid:.0f}/t "
            f"mid estimate ({product.biochar_yield_pct_ds:.0f}% DS yield) is the "
            "primary value driver. System economics depend significantly on "
            "biochar offtake being confirmed."
        )

    # ENERGY-LED: Incineration or gasification without significant product value
    if ptype in ("incineration", "thp_incineration", "gasification"):
        return (
            "ENERGY-LED",
            "Thermal conversion maximises energy recovery and mass reduction. "
            "Carbon product value is secondary (ash for P-recovery or construction). "
            "Primary value drivers are avoided disposal cost and energy recovery."
        )

    # BALANCED: reasonable product + energy + compliance
    return (
        "BALANCED",
        "System delivers a combination of mass reduction, energy recovery, "
        "and carbon product value. No single output dominates the value case."
    )


# ---------------------------------------------------------------------------
# RECOMMENDED STRATEGY (Part 6, Q5)
# ---------------------------------------------------------------------------

def _recommended_strategy(ptype: str, classification: str,
                            drying_achievable: bool, product: CarbonProductAssessment,
                            its_level: int, pfas_status: str) -> str:

    if not drying_achievable and ptype not in ("HTC", "HTC_sidestream"):
        return (
            "DO NOT OPERATE until feed DS% reaches the neutrality threshold. "
            "Commission upstream preconditioning (THP or filter press) first. "
            "Then confirm energy balance at operating DS% before CAPEX commitment."
        )

    if classification == "COMPLIANCE-LED":
        return (
            "Select for PFAS destruction first — economics are secondary. "
            "Incineration (L4 validated) is the lowest-risk regulatory route. "
            "ITS (L3 design-based) is acceptable where validated with site-specific PFAS testing."
        )

    if classification == "PRODUCT-LED":
        strategy = (
            f"Operate at medium pyrolysis temperature (550–650°C) "
            f"for balanced biochar yield and quality. "
            if ptype == "pyrolysis" else
            f"Optimise hydrochar quality for confirmed offtake specification. "
        )
        if product.product_marketable == "CONDITIONAL":
            strategy += (
                "Commission PFAS characterisation and market offtake agreement "
                "BEFORE locking in capital — product revenue is the business case."
            )
        return strategy

    if ptype in ("incineration", "thp_incineration"):
        return (
            "Maximise heat recovery to reduce net operating cost. "
            "Explore P-recovery from ash (struvite or direct ash use). "
            "System value is driven by disposal avoided and regulatory certainty, "
            "not by product revenue."
        )

    return (
        "Operate for balanced value: confirm product market before commissioning, "
        "size energy recovery to offset operating cost, "
        "validate PFAS status before first product delivery to market."
    )


# ---------------------------------------------------------------------------
# INTEGRATED VALUE SCORE
# ---------------------------------------------------------------------------

def _integrated_score(product: CarbonProductAssessment,
                        trade_off: EnergyVsProductTradeOff,
                        its_level: int, drying_achievable: bool) -> float:
    score = 0.0

    # Drying gate
    if not drying_achievable:
        score -= 20.0

    # PFAS compliance
    if its_level == 4:   score += 25.0
    elif its_level == 3: score += 15.0
    elif its_level == 2: score += 5.0
    else:                score -= 10.0

    # Product marketability
    if product.product_marketable == "YES":         score += 20.0
    elif product.product_marketable == "CONDITIONAL": score += 10.0
    else:                                              score -= 15.0

    # Product value
    if product.market_value_mid > 200:   score += 10.0
    elif product.market_value_mid > 100: score += 5.0

    # Energy recovery
    if trade_off.energy_recovery_pct > 30: score += 5.0
    elif trade_off.energy_recovery_pct > 15: score += 3.0

    # Carbon sequestration
    if product.co2e_sequestered_t_per_day > 1.0: score += 5.0

    return round(score, 1)


# ---------------------------------------------------------------------------
# SYSTEM BESTS
# ---------------------------------------------------------------------------

def _assign_system_bests(system: ThermalBiocharSystem, results: dict):
    if not results:
        return

    # Best PFAS: highest ITS level
    pfas_order = sorted(results.values(), key=lambda r: r.its_level, reverse=True)
    system.best_pfas_pathway = pfas_order[0].pathway_name if pfas_order else ""

    # Best product: highest mid market revenue
    prod_order = sorted(
        [r for r in results.values() if r.product and r.product.market_revenue_mid_yr > 0],
        key=lambda r: r.product.market_revenue_mid_yr, reverse=True
    )
    system.best_product_pathway = prod_order[0].pathway_name if prod_order else ""

    # Best energy: highest energy recovery %
    energy_order = sorted(
        results.values(),
        key=lambda r: r.trade_off.energy_recovery_pct if r.trade_off else 0,
        reverse=True
    )
    system.best_energy_pathway = energy_order[0].pathway_name if energy_order else ""

    # Best balanced: highest integrated score
    balanced_order = sorted(
        results.values(), key=lambda r: r.integrated_value_score, reverse=True
    )
    system.best_balanced_pathway = balanced_order[0].pathway_name if balanced_order else ""
