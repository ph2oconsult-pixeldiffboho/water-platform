"""
AquaPoint Engine — Constants & Reference Data
Drinking Water Treatment Decision-Support Platform
ph2o Consulting | Water Utility Planning Platform
"""

# ─── Plant Types ────────────────────────────────────────────────────────────────
PLANT_TYPES = {
    "conventional": {
        "label": "Conventional Surface Water",
        "description": "Coagulation, flocculation, sedimentation, filtration, disinfection",
        "icon": "🏞️",
        "typical_flow_range_ML_d": (1, 500),
    },
    "membrane": {
        "label": "Membrane Filtration",
        "description": "MF/UF/NF/RO-based treatment trains for surface or groundwater",
        "icon": "🔬",
        "typical_flow_range_ML_d": (0.5, 200),
    },
    "groundwater": {
        "label": "Groundwater Treatment",
        "description": "Iron/manganese removal, softening, disinfection",
        "icon": "🌊",
        "typical_flow_range_ML_d": (0.1, 100),
    },
    "desalination": {
        "label": "Desalination / Advanced Purification",
        "description": "Seawater or brackish RO with pre/post-treatment",
        "icon": "🌊",
        "typical_flow_range_ML_d": (1, 300),
    },
}

# ─── Treatment Technologies ──────────────────────────────────────────────────────
TECHNOLOGIES = {
    # Pretreatment
    "screening": {
        "label": "Screening & Microstraining",
        "category": "Pretreatment",
        "applicable_plants": ["conventional", "membrane", "desalination"],
        "description": "Removal of gross solids and debris prior to primary treatment",
    },
    "coagulation_flocculation": {
        "label": "Coagulation & Flocculation",
        "category": "Primary Treatment",
        "applicable_plants": ["conventional", "membrane"],
        "description": "Chemical destabilisation and aggregation of colloidal particles",
    },
    "daf": {
        "label": "Dissolved Air Flotation (DAF)",
        "category": "Primary Treatment",
        "applicable_plants": ["conventional", "membrane"],
        "description": "Low-density particle and algae removal by micro-bubble flotation",
    },
    "sedimentation": {
        "label": "Sedimentation / Clarification (incl. Densadeg / Actiflo)",
        "category": "Primary Treatment",
        "applicable_plants": ["conventional"],
        "description": "Gravity separation of flocculated solids (conventional or lamella)",
    },
    # Filtration
    "rapid_gravity_filtration": {
        "label": "Rapid Gravity Filtration",
        "category": "Filtration",
        "applicable_plants": ["conventional"],
        "description": "Dual or multimedia depth filtration; primary suspended solids barrier",
    },
    "slow_sand_filtration": {
        "label": "Slow Sand Filtration",
        "category": "Filtration",
        "applicable_plants": ["conventional", "groundwater"],
        "description": "Biological schmutzdecke filtration; high land area, low chemical use",
    },
    "mf_uf": {
        "label": "Microfiltration / Ultrafiltration (MF/UF)",
        "category": "Membrane",
        "applicable_plants": ["conventional", "membrane", "groundwater"],
        "description": "Pressure-driven membrane separation for turbidity and pathogen removal",
    },
    "nf": {
        "label": "Nanofiltration (NF)",
        "category": "Membrane",
        "applicable_plants": ["membrane", "groundwater"],
        "description": "Selective removal of divalent ions, hardness, and organics",
    },
    "ro": {
        "label": "Reverse Osmosis (RO)",
        "category": "Membrane",
        "applicable_plants": ["membrane", "desalination"],
        "description": "High-rejection membrane for desalination and advanced purification",
    },
    # Advanced Treatment
    "ozonation": {
        "label": "Ozonation",
        "category": "Advanced Treatment",
        "applicable_plants": ["conventional", "membrane"],
        "description": "Oxidation of organics, taste/odour compounds, and micropollutants",
    },
    "bac": {
        "label": "Biological Activated Carbon (BAC)",
        "category": "Advanced Treatment",
        "applicable_plants": ["conventional", "membrane"],
        "description": "Combined biological and adsorptive removal post-ozonation",
    },
    "gac": {
        "label": "Granular Activated Carbon (GAC)",
        "category": "Advanced Treatment",
        "applicable_plants": ["conventional", "membrane", "groundwater"],
        "description": "Adsorptive removal of taste/odour, organics, and micropollutants",
    },
    "aop": {
        "label": "Advanced Oxidation (AOP)",
        "category": "Advanced Treatment",
        "applicable_plants": ["conventional", "membrane", "desalination"],
        "description": "UV/H₂O₂ or O₃/H₂O₂ for refractory organics and CECs",
    },
    # Disinfection
    "chlorination": {
        "label": "Chlorination (Cl₂ / NaOCl)",
        "category": "Disinfection",
        "applicable_plants": ["conventional", "membrane", "groundwater"],
        "description": "Primary and secondary disinfection; residual maintenance",
    },
    "chloramination": {
        "label": "Chloramination (NH₂Cl)",
        "category": "Disinfection",
        "applicable_plants": ["conventional", "membrane", "groundwater"],
        "description": "Secondary disinfection with reduced DBP formation potential",
    },
    "uv_disinfection": {
        "label": "UV Disinfection",
        "category": "Disinfection",
        "applicable_plants": ["conventional", "membrane", "groundwater", "desalination"],
        "description": "Non-chemical pathogen inactivation; protozoa and virus control",
    },
    # Residuals
    "pre_filter_chlorination": {
        "label": "Pre-Filter Chlorination (Mn oxidation)",
        "category": "Pre-Oxidation",
        "applicable_plants": ["conventional", "groundwater"],
        "description": (
            "Free chlorine dosed ahead of rapid gravity filters to oxidise residual "
            "dissolved Mn\u00b2\u207a \u2192 MnO\u2082(s), captured in the filter bed. "
            "Used when KMnO\u2084 pre-oxidation alone is insufficient for high Mn sources, "
            "or as a primary Mn removal strategy in groundwater treatment. "
            "Dose: 0.5\u20132.0 mg/L free Cl\u2082 at filter inlet. "
            "Incompatible with biological activated carbon (BAC) downstream \u2014 "
            "free Cl\u2082 inhibits the biofilm responsible for biological treatment."
        ),
    },
    "kmno4_pre_oxidation": {
        "label": "KMnO₄ Pre-Oxidation",
        "category": "Pre-Oxidation",
        "applicable_plants": ["conventional", "groundwater"],
        "description": (
            "Potassium permanganate dosing ahead of clarification for dissolved "
            "manganese and iron oxidation to insoluble form. Enables removal by "
            "subsequent coagulation and sedimentation/filtration. Also provides "
            "limited cyanobacterial pre-treatment. Does NOT produce bromate "
            "(safe with high-bromide source waters). "
            "Prospect PPTP: 1–2 mg/L Normal range, 2 mg/L Design Envelope."
        ),
    },
    "polydadmac": {
        "label": "PolyDADMAC (Coagulant Aid)",
        "category": "Primary Treatment",
        "applicable_plants": ["conventional", "membrane"],
        "description": (
            "Cationic polymer used as secondary coagulant in combination with "
            "ferric chloride or alum. Improves floc structure, density, and "
            "settling rate. Particularly effective in ballasted clarification "
            "(Densadeg/Actiflo). Prospect PPTP: 1.5–2.0 mg/L; ratio to FeCl₃ ~7–9%. "
            "Not a standalone coagulant — always supplementary to primary coagulant."
        ),
    },
    "sludge_thickening": {
        "label": "Sludge Thickening & Dewatering",
        "category": "Residuals",
        "applicable_plants": ["conventional", "membrane"],
        "description": "Gravity or mechanical concentration of filter backwash and clarifier sludge",
    },
    "actiflo_carb": {
        "label": "Actiflo® Carb (Ballasted Clarification + PAC)",
        "category": "Primary Treatment",
        "applicable_plants": ["conventional", "membrane"],
        "description": (
            "Ballasted flocculation (microsand) combined with Powdered Activated Carbon (PAC) "
            "pre-contact tank. Removes algae, cyanobacteria, cyanotoxins, geosmin, MIB, and NOM "
            "in a single compact unit. Performance equivalent to or exceeding DAF for algae removal. "
            "NOT suitable for softening — CaCO₃ precipitation fouls microsand recycling system."
        ),
    },
    "chemical_softening": {
        "label": "Chemical Softening (Lime / Soda Ash)",
        "category": "Softening",
        "applicable_plants": ["conventional", "groundwater"],
        "description": "Precipitation softening using hydrated lime and/or soda ash to reduce hardness, TDS, and co-precipitate iron, manganese, and some NOM",
    },
    "brine_management": {
        "label": "Brine / Concentrate Management",
        "category": "Residuals",
        "applicable_plants": ["membrane", "desalination"],
        "description": "RO concentrate disposal, evaporation, or zero-liquid-discharge options",
    },
}

# ─── Water Quality Parameters ────────────────────────────────────────────────────
SOURCE_WATER_QUALITY_PARAMS = {
    "turbidity_ntu": {
        "label": "Turbidity (NTU)",
        "unit": "NTU",
        "typical_range": (0.5, 500),
        "default": 5.0,
        "low_threshold": 1,
        "high_threshold": 50,
    },
    "toc_mg_l": {
        "label": "Total Organic Carbon (mg/L)",
        "unit": "mg/L",
        "typical_range": (1, 30),
        "default": 5.0,
        "low_threshold": 2,
        "high_threshold": 10,
    },
    "tds_mg_l": {
        "label": "Total Dissolved Solids (mg/L)",
        "unit": "mg/L",
        "typical_range": (50, 45000),
        "default": 300,
        "low_threshold": 500,
        "high_threshold": 2000,
    },
    "hardness_mg_l": {
        "label": "Total Hardness (mg/L as CaCO₃)",
        "unit": "mg/L CaCO₃",
        "typical_range": (10, 800),
        "default": 150,
        "low_threshold": 60,
        "high_threshold": 300,
    },
    "iron_mg_l": {
        "label": "Iron (mg/L)",
        "unit": "mg/L",
        "typical_range": (0, 20),
        "default": 0.1,
        "low_threshold": 0.3,
        "high_threshold": 2.0,
    },
    "manganese_mg_l": {
        "label": "Manganese (mg/L)",
        "unit": "mg/L",
        "typical_range": (0, 5),
        "default": 0.02,
        "low_threshold": 0.1,
        "high_threshold": 0.5,
    },
    "colour_hu": {
        "label": "True Colour (Hazen Units)",
        "unit": "HU",
        "typical_range": (0, 200),
        "default": 10,
        "low_threshold": 15,
        "high_threshold": 50,
    },
    "algal_cells_ml": {
        "label": "Algal Cell Count (cells/mL)",
        "unit": "cells/mL",
        "typical_range": (0, 100000),
        "default": 500,
        "low_threshold": 2000,
        "high_threshold": 20000,
    },
}

# ─── ADWG Drinking Water Guidelines (Australia) ─────────────────────────────────
ADWG_GUIDELINES = {
    "turbidity_ntu": {"limit": 1.0, "unit": "NTU", "type": "aesthetic"},
    "toc_mg_l": {"limit": None, "unit": "mg/L", "type": "operational"},
    "tds_mg_l": {"limit": 600, "unit": "mg/L", "type": "aesthetic"},
    "hardness_mg_l": {"limit": 200, "unit": "mg/L CaCO₃", "type": "aesthetic"},
    "iron_mg_l": {"limit": 0.3, "unit": "mg/L", "type": "aesthetic"},
    "manganese_mg_l": {"limit": 0.1, "unit": "mg/L", "type": "health"},
    "colour_hu": {"limit": 15, "unit": "HU", "type": "aesthetic"},
    "ph": {"limit_low": 6.5, "limit_high": 8.5, "unit": "-", "type": "health"},
    "chlorine_mg_l": {"limit": 5.0, "unit": "mg/L", "type": "health"},
    "thm_ug_l": {"limit": 250, "unit": "μg/L", "type": "health"},
    "haa_ug_l": {"limit": 100, "unit": "μg/L", "type": "health"},
}

# ─── Analysis Layers ─────────────────────────────────────────────────────────────
ANALYSIS_LAYERS = [
    "feasibility",
    "water_quality",
    "treatment_performance",
    "energy",
    "chemical_use",
    "capex",
    "opex",
    "lifecycle_cost",
    "risk",
    "environmental",
    "regulatory_compliance",
    "residuals",
    "recommendation",
]

# ─── Energy Reference Data ────────────────────────────────────────────────────────
ENERGY_BENCHMARKS_kWh_ML = {
    "conventional": {"low": 200, "typical": 350, "high": 600},
    "membrane": {"low": 400, "typical": 700, "high": 1200},
    "groundwater": {"low": 100, "typical": 250, "high": 500},
    "desalination": {"low": 2000, "typical": 3500, "high": 6000},
}

ELECTRICITY_COST_AUD_kWh = 0.12  # default; user-configurable

# ─── Chemical Dosing Reference Ranges ────────────────────────────────────────────
CHEMICAL_DOSES_mg_L = {
    # dose ranges: mg/L as pure/active product applied to water
    # unit_cost_AUD_kg: cost per kg of COMMERCIAL PRODUCT (as supplied, not pure)
    # concentration_pct: active ingredient % by weight in commercial product
    # density_t_m3: density of commercial product (t/m³)
    # unit_cost_AUD_kg_pure: derived cost per kg of pure active ingredient
    "alum": {
        "label": "Alum (Al₂(SO₄)₃)",
        "low": 5, "typical": 25, "high": 80,
        "concentration_pct": 49,        # ~49% Al₂(SO₄)₃ solution (8.5% Al₂O₃ equiv)
        "density_t_m3": 1.33,           # liquid alum at 49%
        "unit_cost_AUD_kg": 0.18,       # per kg commercial product (liquid)
        "unit_cost_AUD_kg_pure": 0.37,  # per kg pure Al₂(SO₄)₃ (= 0.18/0.49)
    },
    "ferric_chloride": {
        "label": "Ferric Chloride (FeCl₃)",
        "low": 5, "typical": 20, "high": 60,
        "concentration_pct": 42,        # 42% FeCl₃ solution — Prospect doc, industry standard
        "density_t_m3": 1.49,           # density at 42% — matches Prospect doc exactly
        "unit_cost_AUD_kg": 0.21,       # per kg commercial product (42% solution)
        "unit_cost_AUD_kg_pure": 0.50,  # per kg pure FeCl₃ (= 0.21/0.42)
    },
    "polymer": {
        "label": "Polymer (flocculant — LT25 equivalent)",
        "low": 0.1, "typical": 0.5, "high": 2.0,
        "concentration_pct": 100,       # supplied as dry powder or neat liquid
        "density_t_m3": 0.75,
        "unit_cost_AUD_kg": 3.50,
        "unit_cost_AUD_kg_pure": 3.50,
    },
    "lime": {
        "label": "Hydrated Lime (Ca(OH)₂)",
        "low": 50, "typical": 150, "high": 400,
        "concentration_pct": 95,        # dry hydrated lime — 95% purity typical
        "density_t_m3": 0.50,           # bulk density (dry powder)
        "unit_cost_AUD_kg": 0.19,       # per kg commercial product
        "unit_cost_AUD_kg_pure": 0.20,  # per kg pure Ca(OH)₂
    },
    "soda_ash": {
        "label": "Soda Ash (Na₂CO₃)",
        "low": 20, "typical": 80, "high": 200,
        "concentration_pct": 99,        # dry soda ash — effectively pure
        "density_t_m3": 1.0,            # bulk density
        "unit_cost_AUD_kg": 0.45,
        "unit_cost_AUD_kg_pure": 0.45,
    },
    "chlorine": {
        "label": "Chlorine (as Cl₂)",
        "low": 0.5, "typical": 2.0, "high": 8.0,
        "concentration_pct": 100,       # pure Cl₂ gas (cylinders/tankers)
        "density_t_m3": 1.56,           # liquid Cl₂
        "unit_cost_AUD_kg": 0.60,
        "unit_cost_AUD_kg_pure": 0.60,
    },
    "naocl": {
        "label": "Sodium Hypochlorite (12.5% solution)",
        "low": 0.5, "typical": 2.0, "high": 8.0,
        "concentration_pct": 12.5,      # 12.5% available chlorine — standard commercial grade
        "density_t_m3": 1.21,           # at 12.5%
        "unit_cost_AUD_kg": 0.056,      # per kg commercial product
        "unit_cost_AUD_kg_pure": 0.45,  # per kg available chlorine (= 0.056/0.125)
    },
    "ammonia": {
        "label": "Ammonia (for chloramination)",
        "low": 0.2, "typical": 0.5, "high": 1.5,
        "concentration_pct": 29,        # aqueous ammonia 29%
        "density_t_m3": 0.90,
        "unit_cost_AUD_kg": 0.145,      # per kg commercial product
        "unit_cost_AUD_kg_pure": 0.50,
    },
    "caustic_soda": {
        "label": "Caustic Soda (NaOH — 32% solution)",
        "low": 1, "typical": 5, "high": 20,
        "concentration_pct": 32,        # 32% NaOH solution — standard delivery grade
        "density_t_m3": 1.34,           # at 32%
        "unit_cost_AUD_kg": 0.176,      # per kg commercial product
        "unit_cost_AUD_kg_pure": 0.55,
    },
    "co2": {
        "label": "Carbon Dioxide (pH correction)",
        "low": 1, "typical": 5, "high": 20,
        "concentration_pct": 100,       # pure CO₂ (liquid bulk or cylinder)
        "density_t_m3": 1.18,           # liquid CO₂
        "unit_cost_AUD_kg": 0.25,
        "unit_cost_AUD_kg_pure": 0.25,
    },
    "h2o2": {
        "label": "Hydrogen Peroxide (50% solution — AOP)",
        "low": 1, "typical": 5, "high": 15,
        "concentration_pct": 50,        # 50% H₂O₂ — standard AOP grade
        "density_t_m3": 1.20,           # at 50%
        "unit_cost_AUD_kg": 0.40,       # per kg commercial product
        "unit_cost_AUD_kg_pure": 0.80,
    },
    "antiscalant": {
        "label": "Antiscalant (RO)",
        "low": 1, "typical": 3, "high": 8,
        "concentration_pct": 100,       # neat liquid product
        "density_t_m3": 1.10,
        "unit_cost_AUD_kg": 4.00,
        "unit_cost_AUD_kg_pure": 4.00,
    },
    "kmno4": {
        "label": "Potassium Permanganate (KMnO₄)",
        "low": 0.5, "typical": 1.5, "high": 4.0,
        # Prospect PPTP: 1 mg/L Normal Design Range, 2 mg/L Design Envelope (500–750 MLD)
        # Engineering basis: 1 mg/L oxidises ~0.35 mg/L Mn; practical dose 1–3 mg/L
        # Over-dose risk: pink water (permanganate pass-through) — dose carefully
        "concentration_pct": 97,        # crystal KMnO₄ — 97% purity
        "density_t_m3": 1.60,           # bulk density of crystals
        "unit_cost_AUD_kg": 2.80,       # per kg commercial product (crystals)
        "unit_cost_AUD_kg_pure": 2.89,  # per kg pure KMnO₄ (= 2.80/0.97)
    },
    "polydadmac": {
        "label": "PolyDADMAC (Coagulant Aid — LT610 equivalent)",
        "low": 0.5, "typical": 1.5, "high": 3.0,
        # Prospect PPTP: 1.5–2.0 mg/L active; ratio to FeCl₃ ~7–9%
        "concentration_pct": 26,
        "density_t_m3": 1.10,
        "unit_cost_AUD_kg": 1.20,
        "unit_cost_AUD_kg_pure": 4.62,
    },
    "acid": {
        "label": "Sulfuric Acid (98% — RO pretreat)",
        "low": 1, "typical": 4, "high": 12,
        "concentration_pct": 98,
        "density_t_m3": 1.84,
        "unit_cost_AUD_kg": 0.29,
        "unit_cost_AUD_kg_pure": 0.30,
    },
}

# ─── CAPEX Reference (AUD/ML/d capacity) ─────────────────────────────────────────────────────────────────────────────
CAPEX_REFERENCE_AUD_ML_d = {
    "screening": {"low": 50_000, "typical": 150_000, "high": 400_000},
    "coagulation_flocculation": {"low": 100_000, "typical": 300_000, "high": 700_000},
    "daf": {"low": 400_000, "typical": 800_000, "high": 1_500_000},
    "sedimentation": {"low": 300_000, "typical": 600_000, "high": 1_200_000},
    "rapid_gravity_filtration": {"low": 200_000, "typical": 500_000, "high": 1_000_000},
    "slow_sand_filtration": {"low": 100_000, "typical": 250_000, "high": 500_000},
    "mf_uf": {"low": 400_000, "typical": 900_000, "high": 1_800_000},
    "nf": {"low": 600_000, "typical": 1_200_000, "high": 2_200_000},
    "ro": {"low": 800_000, "typical": 1_600_000, "high": 3_500_000},
    "ozonation": {"low": 300_000, "typical": 700_000, "high": 1_400_000},
    "bac": {"low": 200_000, "typical": 500_000, "high": 1_000_000},
    "gac": {"low": 150_000, "typical": 400_000, "high": 900_000},
    "aop": {"low": 200_000, "typical": 600_000, "high": 1_200_000},
    "chlorination": {"low": 50_000, "typical": 150_000, "high": 350_000},
    "chloramination": {"low": 80_000, "typical": 200_000, "high": 450_000},
    "uv_disinfection": {"low": 100_000, "typical": 300_000, "high": 700_000},
    "sludge_thickening": {"low": 100_000, "typical": 300_000, "high": 700_000},
    "actiflo_carb": {"low": 500_000, "typical": 1_100_000, "high": 2_200_000},
    "chemical_softening": {"low": 400_000, "typical": 900_000, "high": 1_800_000},
    "pre_filter_chlorination": {
        "label": "Pre-Filter Chlorination (Mn oxidation)",
        "category": "Pre-Oxidation",
        "applicable_plants": ["conventional", "groundwater"],
        "description": (
            "Free chlorine dosed ahead of rapid gravity filters to oxidise residual "
            "dissolved Mn\u00b2\u207a \u2192 MnO\u2082(s), captured in the filter bed. "
            "Used when KMnO\u2084 pre-oxidation alone is insufficient for high Mn sources, "
            "or as a primary Mn removal strategy in groundwater treatment. "
            "Dose: 0.5\u20132.0 mg/L free Cl\u2082 at filter inlet. "
            "Incompatible with biological activated carbon (BAC) downstream \u2014 "
            "free Cl\u2082 inhibits the biofilm responsible for biological treatment."
        ),
    },
    "pre_filter_chlorination": {"low": 5_000, "typical": 20_000, "high": 50_000},
    "kmno4_pre_oxidation": {"low": 20_000, "typical": 60_000, "high": 150_000},
    "polydadmac": {"low": 0, "typical": 0, "high": 0},
    "brine_management": {"low": 200_000, "typical": 600_000, "high": 1_500_000},
}


# ─── Risk Ratings ─────────────────────────────────────────────────────────────────
TECHNOLOGY_RISK = {
    "screening": {"implementation": "Low", "operational": "Low", "regulatory": "Low"},
    "coagulation_flocculation": {"implementation": "Low", "operational": "Low", "regulatory": "Low"},
    "daf": {"implementation": "Medium", "operational": "Medium", "regulatory": "Low"},
    "sedimentation": {"implementation": "Low", "operational": "Low", "regulatory": "Low"},
    "rapid_gravity_filtration": {"implementation": "Low", "operational": "Low", "regulatory": "Low"},
    "slow_sand_filtration": {"implementation": "Low", "operational": "Medium", "regulatory": "Low"},
    "mf_uf": {"implementation": "Medium", "operational": "Medium", "regulatory": "Low"},
    "nf": {"implementation": "Medium", "operational": "Medium", "regulatory": "Medium"},
    "ro": {"implementation": "High", "operational": "High", "regulatory": "Medium"},
    "ozonation": {"implementation": "Medium", "operational": "Medium", "regulatory": "Low"},
    "bac": {"implementation": "Medium", "operational": "Medium", "regulatory": "Medium"},
    "gac": {"implementation": "Low", "operational": "Low", "regulatory": "Low"},
    "aop": {"implementation": "High", "operational": "High", "regulatory": "Medium"},
    "chlorination": {"implementation": "Low", "operational": "Low", "regulatory": "Low"},
    "chloramination": {"implementation": "Low", "operational": "Medium", "regulatory": "Medium"},
    "uv_disinfection": {"implementation": "Low", "operational": "Low", "regulatory": "Low"},
    "brine_management": {"implementation": "High", "operational": "High", "regulatory": "High"},
    "pre_filter_chlorination": {
        "label": "Pre-Filter Chlorination (Mn oxidation)",
        "category": "Pre-Oxidation",
        "applicable_plants": ["conventional", "groundwater"],
        "description": (
            "Free chlorine dosed ahead of rapid gravity filters to oxidise residual "
            "dissolved Mn\u00b2\u207a \u2192 MnO\u2082(s), captured in the filter bed. "
            "Used when KMnO\u2084 pre-oxidation alone is insufficient for high Mn sources, "
            "or as a primary Mn removal strategy in groundwater treatment. "
            "Dose: 0.5\u20132.0 mg/L free Cl\u2082 at filter inlet. "
            "Incompatible with biological activated carbon (BAC) downstream \u2014 "
            "free Cl\u2082 inhibits the biofilm responsible for biological treatment."
        ),
    },
    "pre_filter_chlorination": {"implementation": "Low", "operational": "Low", "regulatory": "Low"},
    "kmno4_pre_oxidation": {"implementation": "Low", "operational": "Medium", "regulatory": "Low"},
    "polydadmac": {"implementation": "Low", "operational": "Low", "regulatory": "Low"},
}

# ─── Scoring Weights (MCA) ────────────────────────────────────────────────────────
MCA_DEFAULT_WEIGHTS = {
    "water_quality": 0.30,
    "lifecycle_cost": 0.25,
    "risk": 0.20,
    "energy": 0.10,
    "environmental": 0.10,
    "regulatory_compliance": 0.05,
}

# ─── Lifecycle Parameters ─────────────────────────────────────────────────────────
LIFECYCLE_DEFAULTS = {
    "analysis_period_years": 30,
    "discount_rate_pct": 7.0,
    "capex_contingency_pct": 20.0,
    "opex_escalation_pct": 2.5,
    "membrane_replacement_years": 10,
    "gac_replacement_years": 5,
}

APP_VERSION = "v1.0"
APP_NAME = "AquaPoint"
