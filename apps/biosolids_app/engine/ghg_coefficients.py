"""
engine/ghg_coefficients.py

BioPoint V1 — Carbon & GHG Lifecycle Coefficient Set.

Single, documented, versioned source of truth for all partition coefficients,
emission factors, and physical constants used by the carbon/GHG engine.

NEVER hard-code these inline in engine modules. Always import from here.
All values are screening-grade engineering estimates for Stage 1–2 analysis.
Sources cited per coefficient.

Version: v25B01
ph2o Consulting — BioPoint V1
"""

# ============================================================
# 1. FEEDSTOCK CHARACTERISATION
# ============================================================

# Carbon-to-VS ratio (gC / g VS)
# Municipal blended sludge: organic fraction is ~47–53% carbon by mass.
# Source: Metcalf & Eddy (2014), Henze et al. (2008).
# This is the default — overridden when measured ultimate analysis is provided.
CARBON_TO_VS_RATIO: float = 0.50

# Nitrogen fraction of DS by sludge type (% of DS)
# Used as a fallback when feedstock N% is not measured.
# Source: WEF MOP 8, Metcalf & Eddy 2014.
DEFAULT_N_PCT_BY_SLUDGE_TYPE: dict = {
    "blended":      3.5,
    "primary":      3.0,
    "secondary":    8.5,
    "digested":     4.0,
    "thp_digested": 4.5,
}

# Phosphorus fraction of DS (% of DS)
# Source: Metcalf & Eddy 2014, typical municipal.
DEFAULT_P_PCT_OF_DS: float = 2.0

# Ash = 100 - VS% (no separate input — ash is NOT independent of VS).
# Formula: ash_pct = 100 - vs_pct_of_ds


# ============================================================
# 2. BIOGAS COMPOSITION
# ============================================================

# Methane fraction of biogas (vol/vol)
# Municipal blended sludge mesophilic AD: 62–66% CH4.
# Source: Metcalf & Eddy (2014), WEF MOP 8.
CH4_FRACTION_OF_BIOGAS: float = 0.64

# CO2 fraction of biogas (vol/vol) — complement of CH4 + trace gases
CO2_FRACTION_OF_BIOGAS: float = 0.35   # Approximate; balance is H2S, N2

# Methane density (kg/m3 at STP)
CH4_DENSITY_KG_PER_M3: float = 0.717

# Methane lower heating value (MJ/m3)
CH4_LHV_MJ_PER_M3: float = 35.8


# ============================================================
# 3. FUGITIVE EMISSIONS
# ============================================================

# Fugitive CH4 from covered digesters (fraction of CH4 produced)
# Well-maintained covered digesters: 1–2%. Open digesters: 3–5%.
# Default: covered, well-maintained. Source: IPCC 2006 Vol. 5.
FUGITIVE_CH4_FRACTION_OF_PRODUCED: float = 0.015   # 1.5%

# Fugitive CH4 from biogas CHP combustion (fraction of CH4 fed)
# Unburned methane slip from gas engine.
# Source: EPA AP-42, Section 3.2 (stationary IC engines).
FUGITIVE_CH4_CHP_SLIP_FRACTION: float = 0.005      # 0.5%

# Fugitive CH4 from flare (destruction efficiency)
# Well-operated flare: 98–99.5% destruction.
FLARE_CH4_DESTRUCTION_EFFICIENCY: float = 0.99


# ============================================================
# 4. N2O EMISSION FACTORS
# ============================================================

# N2O from land application of biosolids (kg N2O-N / kg N applied)
# IPCC Tier 1 default. Source: IPCC 2006, Vol. 4, Ch. 11.
N2O_EF_LAND_APPLICATION: float = 0.01   # 1% of applied N

# N2O from biological N removal in sidestream treatment
# SHARON/ANAMMOX systems: lower than conventional nitrification.
# Source: IPCC 2006; Kampschreur et al. 2009.
N2O_EF_SIDESTREAM_TREATMENT: float = 0.008   # 0.8% of N treated

# N2O from mainstream nitrification (driven by return liquor)
# Source: IPCC 2006, Vol. 5; Ahn et al. 2010.
N2O_EF_MAINSTREAM_NITRIFICATION: float = 0.016   # 1.6% of N nitrified

# N2O atmospheric oxidation: indirect N2O from volatilised NH3
# Source: IPCC 2006, Vol. 4, Eq. 11.9.
N2O_EF_INDIRECT_ATMOSPHERIC: float = 0.01   # 1% of NH3-N volatilised


# ============================================================
# 5. CARBON STABILITY — SEQUESTRATION ACCOUNTING
# ============================================================

# Pyrochar carbon stability (R50) → mean residence time (years)
# R50 is a proxy for resistance to oxidative degradation.
# Source: Woolf et al. (2010); Zimmerman (2010).
# MRT estimate: R50 0.55 → ~100 yr; R50 0.70 → ~500 yr; R50 0.80 → ~1000 yr
# For carbon destiny: stable carbon = fixed_carbon_pct × R50_weight
# R50_weight = 1.0 when R50 >= 0.70 (fully creditable), 0 when R50 < 0.50.
PYROCHAR_R50_CREDIT_THRESHOLD: float = 0.50   # Below this: not creditable
PYROCHAR_R50_FULL_CREDIT: float = 0.70        # Above this: full credit
# Linear interpolation between thresholds.

# Hydrochar carbon stability
# HTC hydrochar is substantially less stable than pyrochar.
# Source: Wiedner et al. (2013); Libra et al. (2011); Kambo & Dutta (2015).
HYDROCHAR_R50: float = 0.35   # Range: 0.30–0.40

# Hydrochar fixed carbon fraction (% of hydrochar mass)
# Source: Kambo & Dutta (2015), typical municipal HTC 200–260°C.
HYDROCHAR_FIXED_CARBON_PCT: float = 55.0   # Range: 45–65%

# Incineration FBF ash residual carbon (% of ash mass)
# Well-operated FBF at 850°C+: near-complete combustion.
# Source: EPA (2002), EU WID compliance data.
INCINERATION_ASH_CARBON_PCT: float = 1.5   # Range: 0.5–3%

# Gasification residual char/slag carbon (% of solid residual mass)
# Source: Arena (2012); Belgiorno et al. (2003).
GASIFICATION_ASH_CARBON_PCT: float = 2.0   # Range: 1–5%

# Drying only — VS destroyed ≈ 0 (water removed, organics conserved)
DRYING_ONLY_VS_DESTROYED_PCT: float = 0.0

# Baseline (land application) — carbon applied to soil
# Fraction of applied carbon that mineralises in first year.
# Source: IPCC 2006, Vol. 4, Ch. 11.
BASELINE_CARBON_MINERALISATION_YR1: float = 0.20   # 20% rapid mineralisation
# Remainder (~80%) enters soil organic matter pool — slow oxidation over decades.
BASELINE_CARBON_DELAYED_OXIDATION_FRACTION: float = 0.80


# ============================================================
# 6. TRANSPORT EMISSIONS
# ============================================================

# Diesel truck emission factor (kg CO2e / tonne·km)
# Includes fuel combustion + upstream fuel production (well-to-wheel).
# Source: BITRE (2022); IPCC 2006 Vol. 2.
TRANSPORT_EMISSION_FACTOR_KG_CO2E_PER_T_KM: float = 0.10

# Note: the existing engine computes feed_transport_t_km_yr AND
# product_transport_t_km_yr separately. Both must be included in Scope 3.


# ============================================================
# 7. CHEMICAL INPUTS
# ============================================================

# Polymer (polyacrylamide) for dewatering
# Emission factor (kg CO2e / kg polymer applied).
# Source: Ecoinvent 3.8; typical PAM production.
POLYMER_EMISSION_KG_CO2E_PER_KG: float = 3.5

# Lime for pH control / biosolids conditioning
# Source: Ecoinvent 3.8; CaO production.
LIME_EMISSION_KG_CO2E_PER_KG: float = 0.78

# Natural gas (auxiliary fuel for drying)
# Source: IPCC 2006 Vol. 2; Australian NGA Factors 2024.
NATURAL_GAS_EMISSION_KG_CO2E_PER_GJ: float = 56.1   # Scope 1 combustion
NATURAL_GAS_UPSTREAM_KG_CO2E_PER_GJ: float = 6.5    # Scope 3 upstream


# ============================================================
# 8. AVOIDED EMISSIONS (DISPLACEMENT CREDITS)
# ============================================================

# Avoided fertiliser — emission factors per kg nutrient
# Source: Ecoinvent 3.8; IFA (2021).
AVOIDED_N_FERTILISER_KG_CO2E_PER_KG_N: float = 4.4    # Urea production + application
AVOIDED_P_FERTILISER_KG_CO2E_PER_KG_P: float = 1.8    # Single superphosphate
AVOIDED_K_FERTILISER_KG_CO2E_PER_KG_K: float = 0.5    # KCl

# Avoided fossil electricity (grid displacement)
# Applied to net electricity export from CHP.
# Grid intensity is SCENARIO-DEPENDENT — do not use a single value.
# See GHGInputs.grid_intensity_* fields.
# These are reference defaults only — always override from GHGInputs.
GRID_INTENSITY_DEFAULT_KG_CO2E_PER_KWH: float = 0.55   # NEM average 2025

# State-specific grid intensities (kg CO2e / kWh), 2025 estimates.
# Source: DCCEEW Australian Energy Statistics 2024; CER data.
# These are starting points — the grid is decarbonising rapidly.
GRID_INTENSITY_BY_STATE: dict = {
    "QLD":    0.72,
    "NSW":    0.55,
    "VIC":    0.60,
    "SA":     0.25,
    "WA":     0.65,
    "TAS":    0.08,
    "NT":     0.68,
    "NZ":     0.12,
    "Custom": None,   # User enters value directly
}

# Future grid scenarios (kg CO2e / kWh)
GRID_INTENSITY_2035_KG_CO2E_PER_KWH: float = 0.25    # NEM trajectory (AEMO ISP)
GRID_INTENSITY_NET_ZERO_KG_CO2E_PER_KWH: float = 0.05  # Near-zero residual


# ============================================================
# 9. SIDESTREAM CARBON CLOSURE (WET PATHWAYS)
# ============================================================

# COD to carbon conversion (g C / g COD)
# Theoretical oxygen demand = 2.67 g O2 / g C (for CH2O).
# In practice: 0.30–0.37 for mixed municipal wastewater organics.
# Source: Metcalf & Eddy (2014), Table 2-26.
COD_TO_CARBON_RATIO: float = 0.33


# ============================================================
# 10. GWP VALUES (AR5, 100-year)
# ============================================================
# Source: IPCC AR5 WG1, Chapter 8 (Myhre et al. 2013).
# Match this to whatever convention BioPoint uses elsewhere.
# If AR6 is preferred, CH4=27.9, N2O=273 (negligible difference for screening).

GWP_CH4: float = 28.0     # kg CO2e / kg CH4 (fossil; biogenic = 27)
GWP_N2O: float = 265.0    # kg CO2e / kg N2O

# N2O molecular weight ratio (N2O-N to N2O)
N2O_N_TO_N2O_MW_RATIO: float = 44.0 / 28.0   # = 1.571


# ============================================================
# 11. CARBON FATE DESTINY CATEGORIES
# ============================================================
# Five-way split used by Module C (Carbon Destiny view).
# These are labels only — values computed in carbon_fate.py.

DESTINY_SEQUESTERED       = "Sequestered (durable removal)"
DESTINY_ENERGY            = "Energy utilisation (fossil displacement)"
DESTINY_SOIL_DELAYED      = "Soil / delayed oxidation"
DESTINY_OXIDISED           = "Oxidised to atmosphere (biogenic CO2)"
DESTINY_FUGITIVE_METHANE  = "Fugitive methane"

DESTINY_CATEGORIES = [
    DESTINY_SEQUESTERED,
    DESTINY_ENERGY,
    DESTINY_SOIL_DELAYED,
    DESTINY_OXIDISED,
    DESTINY_FUGITIVE_METHANE,
]

# Anti-greenwashing rule (enforced in carbon_fate.py):
# DESTINY_SEQUESTERED must NEVER include energy utilisation or fertiliser
# displacement. Removal and displacement are separate lines always.



# ============================================================
# THP / SOLIDSTREAM PERFORMANCE COEFFICIENTS
# ============================================================
# Source: Cambi Conceptual Design Memo, Melbourne Eastern Treatment Plant,
#         20.05.2026 (Doc 10590-ZME-001-7035 A01, Melbourne Water Corporation)
#         Cambi plant data sheets: Antwerp Schijnpoort 2025, Munich Amperverband
# Confidence: VENDOR MODEL (pre-contract conceptual stage). Not peer-reviewed.
#         "Design numbers should be checked and verified as the project matures."
#         Consistent with published THP literature where noted.
# Configuration: SolidStream = post-digestion THP (distinct from pre-digestion THP)

# Cake DS% with SolidStream — minimum guarantee
# Antwerp Schijnpoort 2025 operational; Munich Amperverband demonstrated;
# Melbourne memo minimum guarantee 38%DS from 20-22%DS conventional
THP_SOLIDSTREAM_CAKE_DS_PCT: float = 38.0

# Conventional digestion cake DS% (baseline for comparison)
# Melbourne memo: 22%DS (Scenario 1, 65%VS) and 20%DS (Scenario 2, 72%VS)
THP_CONVENTIONAL_CAKE_DS_PCT_LOW: float = 20.0    # 72%VS feed (higher VS, wetter cake)
THP_CONVENTIONAL_CAKE_DS_PCT_HIGH: float = 22.0   # 65%VS feed

# Cake volume reduction with SolidStream vs conventional
# Melbourne memo: -50.6% (Scenario 1, 65%VS), -56.5% (Scenario 2, 72%VS)
# Use conservative end for BioPoint screening
THP_CAKE_VOLUME_REDUCTION_PCT: float = 50.0   # Conservative (Scenario 1)

# Drying energy reduction when drying applied after SolidStream
# Melbourne memo: -67% (Sc1), -72% (Sc2). Basis: less water to evaporate
# because cake is drier and volume is lower.
THP_DRYING_ENERGY_REDUCTION_PCT: float = 67.0   # Conservative (Scenario 1)

# Biogas uplift from SolidStream vs conventional mesophilic AD
# Melbourne memo: +22.7% (Sc1), +22.6% (Sc2)
# NOTE: This is POST-DIGESTION THP (SolidStream). Pre-digestion THP literature
#       shows 40–50% uplift (Amperverband 2015 data). The two configurations
#       are physically different — do not conflate.
THP_SOLIDSTREAM_BIOGAS_UPLIFT_PCT: float = 22.7   # Post-digestion (SolidStream)
THP_PREDIGESTION_BIOGAS_UPLIFT_PCT: float = 40.0  # Pre-digestion THP (literature range 40–50%)

# VSR with SolidStream
# Melbourne memo: 70.3% (Sc1), 70.4% (Sc2) vs 57.5% conventional
# Consistent with published THP literature: 65–75% VSR
THP_SOLIDSTREAM_VSR_PCT: float = 70.3
THP_CONVENTIONAL_VSR_PCT: float = 57.5   # Melbourne memo baseline

# Hygienisation: SolidStream operates at 145–165°C / 6 bar for 40 minutes
# This achieves sterilisation-level pathogen kill — Class A equivalent
# Source: Cambi Melbourne memo p.4, Antwerp data sheet
THP_SOLIDSTREAM_ACHIEVES_CLASS_A: bool = True

# Electricity production uplift with SolidStream vs conventional
# Melbourne memo: +20.7% (Sc1), +22.6% (Sc2)
THP_SOLIDSTREAM_ELECTRICITY_UPLIFT_PCT: float = 20.7   # Conservative (Scenario 1)

# Number of trucks reduction (indicative, basis 40 wet t/truck, Melbourne ETP scale)
# Melbourne memo: 15/day conventional → 7–8/day with SolidStream (Scenario 1)
# Relevant for transport emissions (Scope 3) and logistics planning
THP_SOLIDSTREAM_TRUCK_REDUCTION_PCT: float = 50.0

# Australian reference sites for THP (Cambi Reference List March 2026)
THP_AUSTRALIAN_REFERENCES = [
    {"site": "Brisbane - Oxley Creek",   "client": "Brisbane Water",    "year": 2007,
     "capacity_tds_day": 66,  "feedstock": "Secondary sludge", "use": "Land"},
    {"site": "Sydney - St Marys",        "client": "Sydney Water",      "year": 2022,
     "capacity_tds_day": 33,  "feedstock": "Mixed sludge",     "use": "Land"},
    {"site": "Perth - Woodman Point",    "client": "Water Corporation", "year": 2026,
     "capacity_tds_day": 70,  "feedstock": "Secondary sludge", "use": "Land",
     "status": "Under execution"},
]

# Key SolidStream operational references
THP_SOLIDSTREAM_REFERENCES = [
    {"site": "Antwerp - Schijnpoort", "client": "Aquafin", "country": "Belgium",
     "year": 2025, "capacity_tds_day": 45, "feedstock": "Digested PS+WAS",
     "use": "Incineration", "config": "SolidStream (B8 P)",
     "note": "Post-digestion THP; 38%DS cake; enables auto-thermal incineration"},
    {"site": "Munich - Amperverband", "client": "AmperVerband", "country": "Germany",
     "year": 2015, "capacity_tds_day": 6, "feedstock": "WAS only",
     "use": "Incineration", "config": "SolidStream (Custom)",
     "note": "40-50% biogas uplift; 70-75% VSR; 60% cake volume reduction; "
             "EUR 515,000/yr cost saving. WAS-only configuration."},
    {"site": "Oslo - Veas", "client": "Veas", "country": "Norway",
     "year": 2027, "capacity_tds_day": 70, "feedstock": "Digested PS+WAS",
     "use": "Land application", "config": "SolidStream (B6-4 E)",
     "note": "Under execution. Post-digestion THP; serves 1M population; "
             "biogas refined to liquid fuel for transportation."},
]

# ============================================================
# 12. VS DESTRUCTION SOURCE RULES (Gap 3 from audit)
# ============================================================
# Explicit per-pathway-family rules for VS_destroyed sourcing.
# Used by the adapter to select the correct quantity.

VS_DESTROYED_SOURCE = {
    # AD family: authoritative source is MAD engine
    "AD":             "mad_detail",
    "thp_incineration": "mad_detail_plus_thp",

    # Thermal family: VS_destroyed = VS_pct × (1 - char_yield_frac)
    "pyrolysis":      "char_yield",
    "gasification":   "near_complete",   # VS_pct × 0.99
    "incineration":   "near_complete",   # VS_pct × 0.99

    # HTC: hydrochar yield approach
    "HTC":            "hydrochar_yield",
    "HTC_sidestream": "hydrochar_yield",

    # Drying only: VS conserved
    "drying_only":    "zero",
    "decentralised":  "zero",
    "centralised":    "zero",

    # Baseline: no treatment
    "baseline":       "zero",
}

# Near-complete combustion/gasification efficiency
NEAR_COMPLETE_VS_DESTRUCTION_PCT: float = 99.0

# HTC process conditions (200–260°C, municipal sludge)
# Hydrochar yield as fraction of feed DS.
# Source: Kambo & Dutta (2015); Reza et al. (2013).
HTC_HYDROCHAR_YIELD_FRACTION_OF_DS: float = 0.55   # 55% DS as hydrochar
