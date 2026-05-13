"""
apps/drinking_water_app/characteriser_config.py

AquaPoint — Source Water Characterisation Configuration
=======================================================

The CharacterisationConfig for AquaPoint's drinking water module.
Consumed by core/characteriser/ when processing an uploaded source
water dataset.

Contents
--------
  AQUAPOINT_PARAMETERS     — 35 ParameterSpec entries (§1 of the
                             AquaPoint engineering rule table v5.5)
  AQUAPOINT_RELATIONSHIPS  — 24 RelationshipSpec entries (§6.3.7)
  AQUAPOINT_IDENTITY_RULES — 3 IdentityRule entries (§3.4 INT-05)
  AQUAPOINT_CONFIG         — assembled CharacterisationConfig
  AQUAPOINT_CONCERNS       — 6 named source-water concerns with
                             condition_spec for the orchestrator

Parameter aliases here are the canonical form; the full alias list
lives in core/characteriser/alias_map.py. The alias_map module is
the single source of truth for raw → canonical resolution.

Engineering basis
-----------------
Physical ranges, typical ranges, and lod_aware flags are taken from:
  - ADWG 2022 (Australian Drinking Water Guidelines)
  - WHO Guidelines for Drinking-water Quality, 4th ed.
  - USEPA National Primary/Secondary Drinking Water Regulations
  - Standard Methods for the Examination of Water and Wastewater (23rd ed.)
  - NHMRC guidance on taste and odour compounds

[VERIFY] marks values that require engineering review against current
edition of the cited source before production deployment.

Schema version: config_schema.py v2.0
"""
from __future__ import annotations

from core.characteriser.config_schema import (
    CharacterisationConfig,
    IdentityRule,
    ParameterSpec,
    RelationshipSpec,
    GROUP_BIOLOGICAL,
    GROUP_CHEMICAL,
    GROUP_METALS,
    GROUP_MINERAL,
    GROUP_MICROBIAL,
    GROUP_NUTRIENTS,
    GROUP_ORGANIC,
    GROUP_PHYSICAL,
    KIND_DERIVED,
    KIND_OBSERVED,
    REL_DERIVED_VIA_STRUCT,
    REL_EXPECTED,
    REL_STRUCTURAL,
)


# ── Parameters ────────────────────────────────────────────────────────────────
#
# Aliases listed here are the short natural-language forms that appear most
# commonly in LIMS exports and field datasheets. The alias_map module applies
# normalisation (lowercase, separator collapse, unit-suffix strip) before
# matching, so variants like "Turbidity (NTU)" and "TURBIDITY" are covered
# without being listed explicitly here.

AQUAPOINT_PARAMETERS: list[ParameterSpec] = [

    # ── Physical / hydraulic ──────────────────────────────────────────────────

    ParameterSpec(
        name="Flow_MLd",
        display_name="Flow",
        unit="ML/d",
        physical_range=(0.0, 100_000.0),
        typical_range=(0.1, 5_000.0),
        parameter_type="flow",
        aliases=["Flow_MLd", "Flow_MLD", "Flow ML/d", "Flow"],
        group=GROUP_PHYSICAL,
        kind=KIND_OBSERVED,
        lod_aware=False,
        excluded_from_heatmap=False,
    ),

    ParameterSpec(
        name="Rainfall_mm",
        display_name="Rainfall",
        unit="mm",
        physical_range=(0.0, 1_500.0),
        typical_range=(0.0, 200.0),
        parameter_type="rainfall",
        aliases=["Rainfall", "Rain_mm", "Precipitation_mm", "Precip_mm"],
        group=GROUP_PHYSICAL,
        kind=KIND_OBSERVED,
        lod_aware=False,
        excluded_from_heatmap=False,
    ),

    ParameterSpec(
        name="Turbidity_NTU",
        display_name="Turbidity",
        unit="NTU",
        physical_range=(0.0, 10_000.0),     # [VERIFY] upper; >4000 NTU rare
        typical_range=(0.05, 500.0),
        parameter_type="concentration",
        aliases=["Turbidity", "Turb_NTU", "Turb", "TURBIDITY"],
        group=GROUP_PHYSICAL,
        kind=KIND_OBSERVED,
        lod_aware=False,
        excluded_from_heatmap=False,
    ),

    ParameterSpec(
        name="SuspendedSolids_mg_L",
        display_name="Suspended Solids (TSS)",
        unit="mg/L",
        physical_range=(0.0, 50_000.0),
        typical_range=(0.5, 2_000.0),
        parameter_type="concentration",
        aliases=["Suspended_Solids", "TSS", "SS", "TSS_mg_L"],
        group=GROUP_PHYSICAL,
        kind=KIND_OBSERVED,
        lod_aware=False,
        excluded_from_heatmap=False,
    ),

    ParameterSpec(
        name="Temperature_C",
        display_name="Water Temperature",
        unit="°C",
        physical_range=(0.0, 40.0),         # surface water; not including hydrothermal
        typical_range=(4.0, 32.0),
        parameter_type="temperature",
        aliases=["Temperature", "Temp_C", "Water_Temperature", "Water_Temp"],
        group=GROUP_PHYSICAL,
        kind=KIND_OBSERVED,
        lod_aware=False,
        excluded_from_heatmap=False,
    ),

    # ── Organic / optical ─────────────────────────────────────────────────────

    ParameterSpec(
        name="TrueColour_HU",
        display_name="True Colour",
        unit="HU",
        physical_range=(0.0, 2_000.0),
        typical_range=(0.0, 400.0),
        parameter_type="concentration",
        aliases=["True_Colour", "TrueColour", "Colour_HU", "Colour", "Color_HU"],
        group=GROUP_ORGANIC,
        kind=KIND_OBSERVED,
        lod_aware=False,
        excluded_from_heatmap=False,
    ),

    ParameterSpec(
        name="DOC_mg_L",
        display_name="Dissolved Organic Carbon",
        unit="mg/L",
        physical_range=(0.0, 500.0),
        typical_range=(0.5, 50.0),
        parameter_type="concentration",
        aliases=["DOC", "DOC_mgL", "Dissolved_Organic_Carbon"],
        group=GROUP_ORGANIC,
        kind=KIND_OBSERVED,
        lod_aware=False,
        excluded_from_heatmap=False,
    ),

    ParameterSpec(
        name="TOC_mg_L",
        display_name="Total Organic Carbon",
        unit="mg/L",
        physical_range=(0.0, 500.0),
        typical_range=(0.5, 60.0),
        parameter_type="concentration",
        aliases=["TOC", "TOC_mgL", "Total_Organic_Carbon"],
        group=GROUP_ORGANIC,
        kind=KIND_OBSERVED,
        lod_aware=False,
        excluded_from_heatmap=False,
    ),

    ParameterSpec(
        name="UV254_cm_1",
        display_name="UV Absorbance at 254 nm",
        unit="cm⁻¹",
        physical_range=(0.0, 10.0),
        typical_range=(0.01, 1.5),
        parameter_type="concentration",
        aliases=["UV254", "UV_254", "UV-254", "UVA254", "UV_absorbance_254"],
        group=GROUP_ORGANIC,
        kind=KIND_OBSERVED,
        lod_aware=False,
        excluded_from_heatmap=False,
        noise_tolerance_pct=2.0,    # online UV254 sensors: tighter tolerance
    ),

    ParameterSpec(
        name="UVT_pct_derived",
        display_name="UV Transmittance (derived)",
        unit="%",
        physical_range=(0.0, 100.0),
        typical_range=(20.0, 99.0),
        parameter_type="other",
        aliases=["UVT", "UVT_percent", "UV_Transmittance", "UVT_pct"],
        group=GROUP_ORGANIC,
        kind=KIND_DERIVED,          # computed: UVT = 100 × 10^(−UV254 × pathlength)
        lod_aware=False,
        excluded_from_heatmap=False,
    ),

    ParameterSpec(
        name="SUVA",
        display_name="Specific UV Absorbance",
        unit="L/mg/m",
        physical_range=(0.0, 10.0),
        typical_range=(1.0, 6.0),
        parameter_type="other",
        aliases=["SUVA_L_mg_m", "SUVA_L/mg/m", "Specific_UV_Absorbance"],
        group=GROUP_ORGANIC,
        kind=KIND_DERIVED,          # computed: SUVA = UV254 (m⁻¹) / DOC (mg/L)
        lod_aware=False,
        excluded_from_heatmap=False,
    ),

    # ── Mineral / inorganic ───────────────────────────────────────────────────

    ParameterSpec(
        name="Alkalinity_mg_L_as_CaCO3",
        display_name="Total Alkalinity",
        unit="mg/L as CaCO₃",
        physical_range=(0.0, 2_000.0),
        typical_range=(5.0, 400.0),
        parameter_type="concentration",
        aliases=["Alkalinity", "Alk", "Alkalinity_mg_L", "Total_Alkalinity"],
        group=GROUP_MINERAL,
        kind=KIND_OBSERVED,
        lod_aware=False,
        excluded_from_heatmap=False,
    ),

    ParameterSpec(
        name="Hardness_mg_L_as_CaCO3",
        display_name="Total Hardness",
        unit="mg/L as CaCO₃",
        physical_range=(0.0, 5_000.0),
        typical_range=(10.0, 800.0),
        parameter_type="concentration",
        aliases=["Hardness", "Hard", "Hardness_mg_L", "Total_Hardness"],
        group=GROUP_MINERAL,
        kind=KIND_OBSERVED,
        lod_aware=False,
        excluded_from_heatmap=False,
    ),

    ParameterSpec(
        name="EC_uS_cm",
        display_name="Electrical Conductivity",
        unit="µS/cm",
        physical_range=(0.0, 100_000.0),
        typical_range=(10.0, 8_000.0),
        parameter_type="conductivity",
        aliases=["EC", "Conductivity", "Cond", "Specific_Conductance", "EC25"],
        group=GROUP_MINERAL,
        kind=KIND_OBSERVED,
        lod_aware=False,
        excluded_from_heatmap=False,
    ),

    ParameterSpec(
        name="TDS_mg_L",
        display_name="Total Dissolved Solids",
        unit="mg/L",
        physical_range=(0.0, 70_000.0),
        typical_range=(20.0, 5_000.0),
        parameter_type="concentration",
        aliases=["TDS", "Total_Dissolved_Solids", "TDS_mgL"],
        group=GROUP_MINERAL,
        kind=KIND_OBSERVED,
        lod_aware=False,
        excluded_from_heatmap=False,
    ),

    ParameterSpec(
        name="Chloride_mg_L",
        display_name="Chloride",
        unit="mg/L",
        physical_range=(0.0, 30_000.0),
        typical_range=(1.0, 1_000.0),
        parameter_type="concentration",
        aliases=["Chloride", "Cl", "Cl_mg_L", "Chloride_mgL"],
        group=GROUP_MINERAL,
        kind=KIND_OBSERVED,
        lod_aware=False,
        excluded_from_heatmap=False,
    ),

    # ── Metals / redox ────────────────────────────────────────────────────────

    ParameterSpec(
        name="Iron_mg_L",
        display_name="Total Iron",
        unit="mg/L",
        physical_range=(0.0, 100.0),
        typical_range=(0.01, 20.0),
        parameter_type="concentration",
        aliases=["Iron", "Fe", "Fe_mg_L", "Total_Iron", "Fe_total"],
        group=GROUP_METALS,
        kind=KIND_OBSERVED,
        lod_aware=False,
        excluded_from_heatmap=False,
    ),

    ParameterSpec(
        name="Manganese_mg_L",
        display_name="Total Manganese",
        unit="mg/L",
        physical_range=(0.0, 20.0),
        typical_range=(0.001, 5.0),
        parameter_type="concentration",
        aliases=["Manganese", "Mn", "Mn_mg_L", "Total_Manganese", "Mn_total"],
        group=GROUP_METALS,
        kind=KIND_OBSERVED,
        lod_aware=False,
        excluded_from_heatmap=False,
    ),

    # ── Nutrients ─────────────────────────────────────────────────────────────

    ParameterSpec(
        name="Ammonia_N_mg_L",
        display_name="Ammonia-N",
        unit="mg/L as N",
        physical_range=(0.0, 50.0),
        typical_range=(0.0, 5.0),
        parameter_type="concentration",
        aliases=["Ammonia_N", "Ammonia", "NH4_N", "NH4-N", "NH3-N"],
        group=GROUP_NUTRIENTS,
        kind=KIND_OBSERVED,
        lod_aware=False,
        excluded_from_heatmap=False,
    ),

    ParameterSpec(
        name="Nitrate_N_mg_L",
        display_name="Nitrate-N",
        unit="mg/L as N",
        physical_range=(0.0, 100.0),
        typical_range=(0.0, 20.0),
        parameter_type="concentration",
        aliases=["Nitrate_N", "Nitrate", "NO3_N", "NO3-N", "Nitrate_as_N"],
        group=GROUP_NUTRIENTS,
        kind=KIND_OBSERVED,
        lod_aware=False,
        excluded_from_heatmap=False,
    ),

    ParameterSpec(
        name="Total_Phosphorus_mg_L",
        display_name="Total Phosphorus",
        unit="mg/L",
        physical_range=(0.0, 50.0),
        typical_range=(0.001, 2.0),
        parameter_type="concentration",
        aliases=["Total_Phosphorus", "Total_P", "TP", "TP_mg_L"],
        group=GROUP_NUTRIENTS,
        kind=KIND_OBSERVED,
        lod_aware=False,
        excluded_from_heatmap=False,
    ),

    # ── Biological / algal ────────────────────────────────────────────────────

    ParameterSpec(
        name="DissolvedOxygen_mg_L",
        display_name="Dissolved Oxygen",
        unit="mg/L",
        physical_range=(0.0, 20.0),
        typical_range=(1.0, 16.0),
        parameter_type="concentration",
        aliases=["Dissolved_Oxygen", "DO", "DO_mg_L", "DissolvedOxygen"],
        group=GROUP_BIOLOGICAL,
        kind=KIND_OBSERVED,
        lod_aware=False,
        excluded_from_heatmap=False,
    ),

    ParameterSpec(
        name="pH",
        display_name="pH",
        unit="pH units",
        physical_range=(3.0, 12.0),         # INT-01: outside this → Critical
        typical_range=(5.5, 9.5),            # INT-01b: outside this → Warning
        parameter_type="ph",
        aliases=["PH", "ph", "pH_value", "pH_lab", "pH_field"],
        group=GROUP_BIOLOGICAL,
        kind=KIND_OBSERVED,
        lod_aware=False,
        excluded_from_heatmap=False,
    ),

    ParameterSpec(
        name="Chlorophyll_a_ug_L",
        display_name="Chlorophyll-a",
        unit="µg/L",
        physical_range=(0.0, 5_000.0),
        typical_range=(0.1, 200.0),
        parameter_type="concentration",
        aliases=["Chlorophyll_a", "Chlorophyll-a", "ChlA", "Chl_a", "Chla_ug_L"],
        group=GROUP_BIOLOGICAL,
        kind=KIND_OBSERVED,
        lod_aware=False,
        excluded_from_heatmap=False,
    ),

    ParameterSpec(
        name="Total_Algal_Cells_mL",
        display_name="Total Algal Cells",
        unit="cells/mL",
        physical_range=(0.0, 100_000_000.0),
        typical_range=(100.0, 500_000.0),
        parameter_type="concentration",
        aliases=["Total_Algal_Cells", "Algal_Cells", "Total_Cells", "Algae_cells_mL"],
        group=GROUP_BIOLOGICAL,
        kind=KIND_OBSERVED,
        lod_aware=False,
        excluded_from_heatmap=False,
    ),

    ParameterSpec(
        name="Algal_Biovolume_mm3_L",
        display_name="Total Algal Biovolume",
        unit="mm³/L",
        physical_range=(0.0, 1_000_000.0),
        typical_range=(0.1, 50_000.0),
        parameter_type="concentration",
        aliases=["Total_Algal_Biovolume", "Algal_Biovolume", "Biovolume_total"],
        group=GROUP_BIOLOGICAL,
        kind=KIND_OBSERVED,
        lod_aware=False,
        excluded_from_heatmap=False,
    ),

    ParameterSpec(
        name="Cyanobacteria_cells_mL",
        display_name="Cyanobacteria Cells",
        unit="cells/mL",
        physical_range=(0.0, 100_000_000.0),
        typical_range=(0.0, 200_000.0),
        parameter_type="concentration",
        aliases=["Cyanobacteria", "Cyano_cells", "Cyanobacterial_cells",
                 "Toxic_Cyanobacteria_cells", "Cyano"],
        group=GROUP_BIOLOGICAL,
        kind=KIND_OBSERVED,
        lod_aware=False,
        excluded_from_heatmap=False,
    ),

    ParameterSpec(
        name="Cyanobacterial_Biovolume_mm3_L",
        display_name="Cyanobacterial Biovolume",
        unit="mm³/L",
        physical_range=(0.0, 1_000_000.0),
        typical_range=(0.0, 100_000.0),
        parameter_type="concentration",
        aliases=["Cyanobacterial_Biovolume", "Cyano_Biovolume", "CyanoBiovolume",
                 "Biovolume_cyanobacterial"],
        group=GROUP_BIOLOGICAL,
        kind=KIND_OBSERVED,
        lod_aware=False,
        excluded_from_heatmap=False,
    ),

    # ── Microbial ─────────────────────────────────────────────────────────────

    ParameterSpec(
        name="Microcystin_LR_ug_L",
        display_name="Microcystin-LR",
        unit="µg/L",
        physical_range=(0.0, 50_000.0),     # [VERIFY] upper bound
        typical_range=(0.0, 100.0),
        parameter_type="concentration",
        aliases=["Microcystin_LR", "Microcystin-LR", "Microcystin", "MC-LR", "MCLR"],
        group=GROUP_MICROBIAL,
        kind=KIND_OBSERVED,
        lod_aware=True,                     # commonly below detection limit
        excluded_from_heatmap=False,
    ),

    ParameterSpec(
        name="E_coli_MPN_100mL",
        display_name="E. coli",
        unit="MPN/100 mL",
        physical_range=(0.0, 100_000_000.0),
        typical_range=(0.0, 100_000.0),
        parameter_type="concentration",
        aliases=["E_coli", "Ecoli", "E.coli", "E_coli_MPN", "Faecal_coliforms"],
        group=GROUP_MICROBIAL,
        kind=KIND_OBSERVED,
        lod_aware=True,                     # <1 MPN/100mL common in clean sources
        excluded_from_heatmap=False,
    ),

    # ── Taste and odour ───────────────────────────────────────────────────────

    ParameterSpec(
        name="Geosmin_ng_L",
        display_name="Geosmin",
        unit="ng/L",
        physical_range=(0.0, 10_000.0),
        typical_range=(0.0, 100.0),
        parameter_type="concentration",
        aliases=["Geosmin", "Geo", "Geosmin_ngL"],
        group=GROUP_CHEMICAL,
        kind=KIND_OBSERVED,
        lod_aware=True,                     # threshold odour ~4 ng/L; often <LOD
        excluded_from_heatmap=False,
    ),

    ParameterSpec(
        name="MIB_ng_L",
        display_name="2-Methylisoborneol (MIB)",
        unit="ng/L",
        physical_range=(0.0, 10_000.0),
        typical_range=(0.0, 100.0),
        parameter_type="concentration",
        aliases=["MIB", "2-MIB", "2_MIB", "MIB_ngL", "Methylisoborneol"],
        group=GROUP_CHEMICAL,
        kind=KIND_OBSERVED,
        lod_aware=True,                     # threshold odour ~6 ng/L; often <LOD
        excluded_from_heatmap=False,
    ),

    # ── Chemical markers / emerging contaminants ──────────────────────────────

    ParameterSpec(
        name="Bromide_mg_L",
        display_name="Bromide",
        unit="mg/L",
        physical_range=(0.0, 1_000.0),
        typical_range=(0.0, 10.0),
        parameter_type="concentration",
        aliases=["Bromide", "Br", "Br_mg_L", "Bromide_mgL"],
        group=GROUP_CHEMICAL,
        kind=KIND_OBSERVED,
        lod_aware=False,
        excluded_from_heatmap=False,
        # Bromide is a key DBP precursor indicator — governs ozone/chlorination
        # by-product risk. Not lod_aware but often near analytical detection
        # in low-salinity catchments.
    ),

    ParameterSpec(
        name="PFAS_sum_ng_L",
        display_name="PFAS (sum)",
        unit="ng/L",
        physical_range=(0.0, 1_000_000.0),  # [VERIFY] upper; contaminated sites >100,000 ng/L
        typical_range=(0.0, 1_000.0),
        parameter_type="concentration",
        aliases=["PFAS_sum", "PFAS", "Total_PFAS", "Sum_PFAS", "PFAS_total"],
        group=GROUP_CHEMICAL,
        kind=KIND_OBSERVED,
        lod_aware=True,                     # typically reported as <LOD in clean catchments
        excluded_from_heatmap=False,
    ),

    ParameterSpec(
        name="Arsenic_ug_L",
        display_name="Arsenic",
        unit="µg/L",
        physical_range=(0.0, 10_000.0),
        typical_range=(0.0, 100.0),         # [VERIFY] ADWG guideline 7 µg/L
        parameter_type="concentration",
        aliases=["Arsenic", "As", "As_ug_L", "Arsenic_µg_L"],
        group=GROUP_CHEMICAL,
        kind=KIND_OBSERVED,
        lod_aware=True,                     # often <LOD in non-impacted sources
        excluded_from_heatmap=False,
    ),

    # ── Major cations ─────────────────────────────────────────────────────────

    ParameterSpec(
        name="Calcium_mg_L",
        display_name="Calcium",
        unit="mg/L",
        physical_range=(0.0, 1_000.0),
        typical_range=(1.0, 200.0),
        parameter_type="concentration",
        aliases=["Calcium_mg_L", "Calcium", "Ca", "Ca_mg_L", "Ca_mgL"],
        group=GROUP_MINERAL,
        kind=KIND_OBSERVED,
        lod_aware=False,
        excluded_from_heatmap=False,
    ),

    ParameterSpec(
        name="Magnesium_mg_L",
        display_name="Magnesium",
        unit="mg/L",
        physical_range=(0.0, 500.0),
        typical_range=(0.5, 100.0),
        parameter_type="concentration",
        aliases=["Magnesium_mg_L", "Magnesium", "Mg", "Mg_mg_L", "Mg_mgL"],
        group=GROUP_MINERAL,
        kind=KIND_OBSERVED,
        lod_aware=False,
        excluded_from_heatmap=False,
    ),

    # ── Biological / algal — extended ─────────────────────────────────────────

    ParameterSpec(
        name="Phycocyanin_ug_L",
        display_name="Phycocyanin",
        unit="µg/L",
        physical_range=(0.0, 10_000.0),
        typical_range=(0.0, 200.0),
        parameter_type="concentration",
        aliases=["Phycocyanin_ug_L", "Phycocyanin", "PC_ug_L", "Phycocyanin_ugL"],
        group=GROUP_BIOLOGICAL,
        kind=KIND_OBSERVED,
        lod_aware=True,
        excluded_from_heatmap=False,
        # Online cyanobacteria pigment proxy. Faster early-warning than cell counts.
        # Absolute values are instrument-specific; treat as relative indicator.
    ),

    ParameterSpec(
        name="Cyanotoxin_ug_L",
        display_name="Cyanotoxin (total)",
        unit="µg/L",
        physical_range=(0.0, 10_000.0),
        typical_range=(0.0, 10.0),
        parameter_type="concentration",
        aliases=["Cyanotoxin_ug_L", "Cyanotoxin", "Total_Cyanotoxin",
                 "Cyanotoxins_ug_L", "Total_Cyanotoxin_ug_L"],
        group=GROUP_MICROBIAL,
        kind=KIND_OBSERVED,
        lod_aware=True,
        excluded_from_heatmap=False,
        # Total cyanotoxins — NOT microcystin-LR specific.
        # The ADWG AL2 threshold (1.3 µg/L) applies to microcystin-LR equivalent only.
        # AV-CLS-02 toxin channel returns Indeterminate when this column is supplied
        # without a declaration that values are microcystin-LR equivalent.
    ),

    # ── Pathogen indicators ───────────────────────────────────────────────────

    ParameterSpec(
        name="Cryptosporidium_oocysts_10L",
        display_name="Cryptosporidium",
        unit="oocysts/10 L",
        physical_range=(0.0, 100_000.0),
        typical_range=(0.0, 100.0),
        parameter_type="concentration",
        aliases=["Cryptosporidium_oocysts_10L", "Cryptosporidium",
                 "Crypto_oocysts_10L", "Crypto_10L"],
        group=GROUP_MICROBIAL,
        kind=KIND_OBSERVED,
        lod_aware=True,
        excluded_from_heatmap=False,
        # Direct protozoan pathogen measurement. High analytical uncertainty at
        # low counts (recovery efficiency typically 20–70%). Key input to
        # ADWG HBT LRV framework.
    ),

    ParameterSpec(
        name="Giardia_cysts_10L",
        display_name="Giardia",
        unit="cysts/10 L",
        physical_range=(0.0, 100_000.0),
        typical_range=(0.0, 100.0),
        parameter_type="concentration",
        aliases=["Giardia_cysts_10L", "Giardia", "Giardia_cysts", "Giardia_10L"],
        group=GROUP_MICROBIAL,
        kind=KIND_OBSERVED,
        lod_aware=True,
        excluded_from_heatmap=False,
    ),

    ParameterSpec(
        name="Total_Coliforms_MPN_100mL",
        display_name="Total Coliforms",
        unit="MPN/100 mL",
        physical_range=(0.0, 100_000_000.0),
        typical_range=(0.0, 100_000.0),
        parameter_type="concentration",
        aliases=["Total_Coliforms_MPN_100mL", "Total_Coliforms",
                 "TotalColiforms", "Coliforms_MPN_100mL"],
        group=GROUP_MICROBIAL,
        kind=KIND_OBSERVED,
        lod_aware=False,
        excluded_from_heatmap=False,
    ),

    # ── Physical — extended ───────────────────────────────────────────────────

    ParameterSpec(
        name="Particle_Count_gt2um_per_mL",
        display_name="Particle Count (>2 µm)",
        unit="particles/mL",
        physical_range=(0.0, 10_000_000.0),
        typical_range=(100.0, 100_000.0),
        parameter_type="concentration",
        aliases=["Particle_Count_gt2um_per_mL", "Particle_Count_gt_2um_per_mL",
                 "Particle_Count", "Particles_per_mL"],
        group=GROUP_PHYSICAL,
        kind=KIND_OBSERVED,
        lod_aware=False,
        excluded_from_heatmap=False,
        # Online particle counter; surrogate for colloidal particle burden and
        # Cryptosporidium-sized particles. Expected correlation with turbidity;
        # may decouple during algal blooms.
    ),
]



# ── Relationships ─────────────────────────────────────────────────────────────

AQUAPOINT_RELATIONSHIPS: list[RelationshipSpec] = [

    # ── Structural (mathematically guaranteed) ────────────────────────────────

    RelationshipSpec(
        parameter_a="DOC_mg_L",
        parameter_b="TOC_mg_L",
        expected_type=REL_EXPECTED,
        rationale=(
            "DOC is the dissolved fraction of TOC and the physical constraint DOC ≤ TOC holds, "
            "but DOC and TOC are independently measured channels. Analytical uncertainty, "
            "particulate fraction variability, and filtration method differences mean the "
            "relationship is physically expected but not mathematically fixed. "
            "The identity rule (DOC ≤ TOC) is enforced separately via INT-05."
        ),
    ),
    RelationshipSpec(
        parameter_a="Cyanobacteria_cells_mL",
        parameter_b="Total_Algal_Cells_mL",
        expected_type=REL_STRUCTURAL,
        rationale="Cyanobacteria is a taxonomic subset of total algal cells.",
    ),
    RelationshipSpec(
        parameter_a="Cyanobacterial_Biovolume_mm3_L",
        parameter_b="Algal_Biovolume_mm3_L",
        expected_type=REL_STRUCTURAL,
        rationale="Cyanobacterial biovolume is a component of total algal biovolume.",
    ),
    RelationshipSpec(
        parameter_a="UV254_cm_1",
        parameter_b="UVT_pct_derived",
        expected_type=REL_STRUCTURAL,
        rationale=(
            "UVT is mathematically derived from UV254: "
            "UVT (%) = 100 × 10^(−UV254 × pathlength). "
            "Perfect inverse structural relationship."
        ),
    ),

    # ── Expected (physically / chemically expected) ───────────────────────────

    RelationshipSpec(
        parameter_a="DOC_mg_L",
        parameter_b="UV254_cm_1",
        expected_type=REL_EXPECTED,
        rationale=(
            "Chromophoric dissolved organic matter (CDOM) within DOC absorbs at 254 nm; "
            "higher DOC typically increases UV254 absorbance. "
            "Correlation strength depends on aromaticity fraction (SUVA)."
        ),
    ),
    RelationshipSpec(
        parameter_a="DOC_mg_L",
        parameter_b="TrueColour_HU",
        expected_type=REL_EXPECTED,
        rationale=(
            "Coloured dissolved organics (humic and fulvic acids) drive both DOC and "
            "true colour. Strong expected relationship in humic-dominated catchments; "
            "weaker where DOC is dominated by algal-derived material."
        ),
    ),
    RelationshipSpec(
        parameter_a="TOC_mg_L",
        parameter_b="UV254_cm_1",
        expected_type=REL_EXPECTED,
        rationale=(
            "TOC includes the chromophoric dissolved fraction; correlation with UV254 "
            "is expected but weaker than DOC↔UV254 because TOC includes particulate "
            "and non-chromophoric fractions."
        ),
    ),
    RelationshipSpec(
        parameter_a="Turbidity_NTU",
        parameter_b="SuspendedSolids_mg_L",
        expected_type=REL_EXPECTED,
        rationale=(
            "Turbidity is an optical surrogate for suspended solids concentration. "
            "Strong expected correlation; slope varies with particle size distribution "
            "and refractive index."
        ),
    ),
    RelationshipSpec(
        parameter_a="Turbidity_NTU",
        parameter_b="Iron_mg_L",
        expected_type=REL_EXPECTED,
        rationale=(
            "Particulate and colloidal iron (Fe³⁺ hydroxides) is a common turbidity "
            "driver in surface catchments with iron-rich geology or reducing sediments."
        ),
    ),
    RelationshipSpec(
        parameter_a="Chlorophyll_a_ug_L",
        parameter_b="Total_Algal_Cells_mL",
        expected_type=REL_EXPECTED,
        rationale=(
            "Chlorophyll-a is the primary algal biomass pigment. Positive correlation "
            "with total cell count is expected but varies with species composition and "
            "growth phase (chlorophyll per cell varies ~10-fold across taxa)."
        ),
    ),
    RelationshipSpec(
        parameter_a="Chlorophyll_a_ug_L",
        parameter_b="Cyanobacteria_cells_mL",
        expected_type=REL_EXPECTED,
        rationale=(
            "Cyanobacteria contain both phycocyanin and chlorophyll-a. Positive "
            "expected correlation; strength depends on cyanobacterial fraction of "
            "total algal community."
        ),
    ),
    RelationshipSpec(
        parameter_a="Cyanobacteria_cells_mL",
        parameter_b="Microcystin_LR_ug_L",
        expected_type=REL_EXPECTED,
        rationale=(
            "Microcystin-LR is produced by toxin-producing cyanobacteria genera "
            "(Microcystis, Anabaena, Planktothrix). Expected positive correlation "
            "but highly variable — not all cells are toxigenic, and toxin:cell ratios "
            "vary by strain, growth phase, and environmental conditions."
        ),
    ),
    RelationshipSpec(
        parameter_a="Cyanobacteria_cells_mL",
        parameter_b="Geosmin_ng_L",
        expected_type=REL_EXPECTED,
        rationale=(
            "Geosmin is produced by specific cyanobacteria genera (Anabaena, "
            "Oscillatoria, Aphanizomenon). Expected positive correlation when "
            "these genera dominate; weak or absent when non-geosmin producers dominate."
        ),
    ),
    RelationshipSpec(
        parameter_a="Cyanobacteria_cells_mL",
        parameter_b="MIB_ng_L",
        expected_type=REL_EXPECTED,
        rationale=(
            "2-MIB is produced by specific cyanobacteria (Planktothrix, Pseudanabaena) "
            "and some actinomycetes. Expected positive correlation when MIB-producing "
            "taxa dominate; variable otherwise."
        ),
    ),
    RelationshipSpec(
        parameter_a="EC_uS_cm",
        parameter_b="TDS_mg_L",
        expected_type=REL_EXPECTED,
        rationale=(
            "TDS is commonly estimated from EC via an empirical conversion factor "
            "(TDS ≈ 0.55–0.70 × EC). Strong expected correlation; factor varies with "
            "ionic composition."
        ),
    ),
    RelationshipSpec(
        parameter_a="EC_uS_cm",
        parameter_b="Hardness_mg_L_as_CaCO3",
        expected_type=REL_EXPECTED,
        rationale=(
            "Divalent cations Ca²⁺ and Mg²⁺ (hardness ions) contribute significantly "
            "to specific conductance. Expected positive correlation in carbonate-dominated "
            "systems; weaker where hardness is dominated by non-EC-contributing species."
        ),
    ),
    RelationshipSpec(
        parameter_a="EC_uS_cm",
        parameter_b="Alkalinity_mg_L_as_CaCO3",
        expected_type=REL_EXPECTED,
        rationale=(
            "Bicarbonate and carbonate ions are major contributors to conductance in "
            "most freshwaters. Expected positive correlation; strength reflects degree "
            "of carbonate-system dominance."
        ),
    ),
    RelationshipSpec(
        parameter_a="Hardness_mg_L_as_CaCO3",
        parameter_b="Alkalinity_mg_L_as_CaCO3",
        expected_type=REL_EXPECTED,
        rationale=(
            "In carbonate-dominated systems, hardness and alkalinity are controlled by "
            "the same geological source (limestone dissolution). Expected positive "
            "correlation; weakens where non-carbonate hardness (e.g. sulphate systems) "
            "or organic alkalinity is significant."
        ),
    ),
    RelationshipSpec(
        parameter_a="Turbidity_NTU",
        parameter_b="Rainfall_mm",
        expected_type=REL_EXPECTED,
        rationale=(
            "Storm runoff entrains particulates from the catchment surface; turbidity "
            "responds to rainfall events with a lag that depends on catchment size and "
            "antecedent conditions. Classic first-flush signature."
        ),
    ),
    RelationshipSpec(
        parameter_a="DOC_mg_L",
        parameter_b="Rainfall_mm",
        expected_type=REL_EXPECTED,
        rationale=(
            "Storm flushing mobilises dissolved organic matter from catchment soils "
            "and riparian zones. Expected positive correlation; strength depends on "
            "catchment organic content and storm intensity."
        ),
    ),
    RelationshipSpec(
        parameter_a="TrueColour_HU",
        parameter_b="Rainfall_mm",
        expected_type=REL_EXPECTED,
        rationale=(
            "Humic and fulvic acids are mobilised from organic-rich catchment soils "
            "during storm events. Colour events typically co-occur with high-DOC events "
            "in tannin-stained catchments."
        ),
    ),

    # ── New parameters — expected relationships ───────────────────────────────

    RelationshipSpec(
        parameter_a="Phycocyanin_ug_L",
        parameter_b="Cyanobacteria_cells_mL",
        expected_type=REL_EXPECTED,
        rationale=(
            "Phycocyanin is the primary blue-green pigment in cyanobacteria. "
            "Expected strong positive correlation with cell count; strength "
            "depends on species composition and pigment content per cell."
        ),
    ),
    RelationshipSpec(
        parameter_a="Phycocyanin_ug_L",
        parameter_b="Cyanotoxin_ug_L",
        expected_type=REL_EXPECTED,
        rationale=(
            "Cyanotoxins are produced by cyanobacteria; phycocyanin is a "
            "cyanobacterial biomass proxy. Expected positive correlation "
            "during bloom conditions; variable at low cell densities."
        ),
    ),
    RelationshipSpec(
        parameter_a="Cryptosporidium_oocysts_10L",
        parameter_b="Giardia_cysts_10L",
        expected_type=REL_EXPECTED,
        rationale=(
            "Both are protozoan pathogens associated with faecal contamination "
            "and commonly co-occur following storm-driven catchment runoff events."
        ),
    ),
    RelationshipSpec(
        parameter_a="Cryptosporidium_oocysts_10L",
        parameter_b="E_coli_MPN_100mL",
        expected_type=REL_EXPECTED,
        rationale=(
            "Both indicate faecal contamination. Expected positive correlation "
            "during storm-driven catchment runoff; may decouple under low-flow "
            "conditions where Cryptosporidium persists longer in the environment."
        ),
    ),
    RelationshipSpec(
        parameter_a="Particle_Count_gt2um_per_mL",
        parameter_b="Turbidity_NTU",
        expected_type=REL_EXPECTED,
        rationale=(
            "Particle count and turbidity are both optical responses to particulate "
            "matter. Expected positive correlation; may decouple when particle size "
            "distribution shifts (e.g. during algal blooms, colloidal vs coarse particles)."
        ),
    ),
    RelationshipSpec(
        parameter_a="Calcium_mg_L",
        parameter_b="Hardness_mg_L_as_CaCO3",
        expected_type=REL_EXPECTED,
        rationale=(
            "Calcium is a primary component of total hardness (Ca²⁺ + Mg²⁺ as CaCO₃). "
            "Expected strong positive correlation; slope reflects Ca:Mg ratio."
        ),
    ),
    RelationshipSpec(
        parameter_a="Magnesium_mg_L",
        parameter_b="Hardness_mg_L_as_CaCO3",
        expected_type=REL_EXPECTED,
        rationale=(
            "Magnesium is a primary component of total hardness alongside calcium. "
            "Expected positive correlation; typically weaker than Ca↔hardness "
            "because Ca usually dominates hardness in freshwater."
        ),
    ),
    RelationshipSpec(
        parameter_a="Calcium_mg_L",
        parameter_b="Alkalinity_mg_L_as_CaCO3",
        expected_type=REL_EXPECTED,
        rationale=(
            "In carbonate-dominated systems calcium and bicarbonate alkalinity "
            "co-vary with geological source. Expected positive correlation."
        ),
    ),


    # SUVA = UV254 × 100 / DOC. Both UV254 and DOC are shared components
    # but SUVA is independently computed and the correlations are not
    # mathematically fixed (DOC and UV254 vary independently).
    RelationshipSpec(
        parameter_a="UV254_cm_1",
        parameter_b="SUVA",
        expected_type=REL_EXPECTED,
        rationale=(
            "SUVA = UV254 × 100 / DOC. UV254 is the numerator — expected strong "
            "positive correlation. Strength depends on DOC variability relative to "
            "UV254 variability; at this source both vary with organic loading events."
        ),
    ),
    RelationshipSpec(
        parameter_a="DOC_mg_L",
        parameter_b="SUVA",
        expected_type=REL_EXPECTED,
        rationale=(
            "SUVA = UV254 × 100 / DOC. DOC is the denominator — expected weak or "
            "inverse correlation at sources where DOC drives dilution of UV254. "
            "Sign and strength depend on whether UV254 or DOC dominates SUVA variability."
        ),
    ),
    RelationshipSpec(
        parameter_a="TrueColour_HU",
        parameter_b="SUVA",
        expected_type=REL_EXPECTED,
        rationale=(
            "True colour is driven by chromophoric humic/fulvic acids that also "
            "absorb at 254 nm. Expected positive correlation between colour and SUVA "
            "in humic catchments; both respond to the same aromatic organic fraction."
        ),
    ),

    RelationshipSpec(
        parameter_a="DOC_mg_L",
        parameter_b="UVT_pct_derived",
        expected_type=REL_DERIVED_VIA_STRUCT,
        rationale=(
            "UVT is structurally derived from UV254 (UVT = 100 × 10^(−UV254 × path)); "
            "the DOC↔UVT correlation is inherited through the DOC↔UV254 expected "
            "relationship and the UV254↔UVT structural link."
        ),
        intermediate_parameter="UV254_cm_1",
    ),
    RelationshipSpec(
        parameter_a="TOC_mg_L",
        parameter_b="UVT_pct_derived",
        expected_type=REL_DERIVED_VIA_STRUCT,
        rationale=(
            "UVT is structurally derived from UV254; the TOC↔UVT correlation is "
            "inherited through the TOC↔UV254 expected relationship."
        ),
        intermediate_parameter="UV254_cm_1",
    ),
    RelationshipSpec(
        parameter_a="TrueColour_HU",
        parameter_b="UVT_pct_derived",
        expected_type=REL_DERIVED_VIA_STRUCT,
        rationale=(
            "True colour drives UV254 absorbance; UVT inherits this relationship "
            "through the structural UV254↔UVT link."
        ),
        intermediate_parameter="UV254_cm_1",
    ),
]


# ── Identity rules (§3.4 INT-05) ─────────────────────────────────────────────

AQUAPOINT_IDENTITY_RULES: list[IdentityRule] = [

    IdentityRule(
        numerator_param="DOC_mg_L",
        denominator_param="TOC_mg_L",
        label="DOC ≤ TOC",
        description=(
            "Dissolved organic carbon is the filtered fraction of total organic carbon. "
            "DOC > TOC on any row is analytically impossible and indicates a sensor fault, "
            "sample swap, or units error."
        ),
    ),

    IdentityRule(
        numerator_param="Cyanobacteria_cells_mL",
        denominator_param="Total_Algal_Cells_mL",
        label="Cyano cells ≤ Total algal cells",
        description=(
            "Cyanobacteria cell count is a taxonomic subset of total algal cell count. "
            "Violations indicate a counting method inconsistency (e.g. different size "
            "thresholds applied to each count) or a data entry error."
        ),
        noise_tolerance_pct=2.0,    # counting variability is higher than chemical analysis
    ),

    IdentityRule(
        numerator_param="Cyanobacterial_Biovolume_mm3_L",
        denominator_param="Algal_Biovolume_mm3_L",
        label="Cyano biovolume ≤ Total algal biovolume",
        description=(
            "Cyanobacterial biovolume is a component of total algal biovolume. "
            "Violations indicate a biovolume calculation inconsistency or data entry error."
        ),
        noise_tolerance_pct=2.0,
    ),
]


# ── Assembled config ──────────────────────────────────────────────────────────

AQUAPOINT_CONFIG = CharacterisationConfig(
    module="drinking_water",
    version="aquapoint-1.1",     # bumped: +8 parameters, +8 relationships, SUVA ontology fix
    parameters=AQUAPOINT_PARAMETERS,
    relationships=AQUAPOINT_RELATIONSHIPS,
    identity_rules=AQUAPOINT_IDENTITY_RULES,
    lod_substitution_value=0.5,     # half-LoD convention (NHMRC guidance)
    heatmap_min_rho=0.6,            # surface pairs with |ρ| ≥ 0.6 in top-relationships
    heatmap_min_n=10,               # minimum overlapping pairs for a cell to be computed
    identity_noise_tolerance_pct_default=5.0,
)


# ── Concerns catalogue ────────────────────────────────────────────────────────
#
# Drinking water analogue of KNOWN_CONCERNS in orchestrator.py.
#
# Each concern maps to a condition_spec that the orchestrator uses to define
# the conditional subset. The condition_spec syntax is the same as WaterPoint:
#   {column_name: ">P75"}    — rows where column > 75th percentile
#   {column_name: ">VALUE"}  — rows where column > an absolute threshold
#   {column_name: "<VALUE"}  — rows where column < an absolute threshold
#
# Engineering basis for thresholds:
#   algal_bloom_risk:     ADWG 2022 Cyanobacteria Alert Level 1 = 2,000 cells/mL
#                         Alert Level 2 = 100,000 cells/mL. Using 2,000 as the
#                         condition threshold captures the onset of alert conditions.
#   high_turbidity_event: P90 captures events significantly above median without
#                         being as sparse as P99.
#   colour_toc_event:     P80 of TrueColour captures colour events; co-occurrence
#                         with TOC drives DBP precursor risk.
#   hardness_scaling:     Hardness >200 mg/L as CaCO3 is where scaling risk
#                         becomes operationally significant (moderate-hard category).
#   taste_odour_precursor: Geosmin threshold at 4 ng/L = ADWG 2022 taste/odour
#                          aesthetic guideline for geosmin. [VERIFY current ADWG]
#   disinfection_byproduct_risk: Bromide >0.05 mg/L is a commonly cited threshold
#                                above which bromate formation in ozonation and
#                                brominated THMs in chlorination become a concern.
#                                [VERIFY against current ADWG / WHO guidance]

AQUAPOINT_CONCERNS: dict[str, dict] = {

    "algal_bloom_risk": {
        "label":          "Algal Bloom / Cyanobacteria Risk",
        "condition_spec": {"Cyanobacteria_cells_mL": ">2000"},
        "focus_parameters": [
            "Cyanobacteria_cells_mL", "Total_Algal_Cells_mL",
            "Chlorophyll_a_ug_L", "Microcystin_LR_ug_L",
            "Geosmin_ng_L", "MIB_ng_L", "pH", "Temperature_C",
        ],
        "description": (
            "Characterises source water conditions during cyanobacterial bloom events "
            "(≥2,000 cells/mL, ADWG Alert Level 1). Reveals co-occurrence of cell counts, "
            "toxin concentrations, taste/odour compounds, and the physical conditions "
            "(temperature, pH, DO) that support bloom persistence."
        ),
    },

    "high_turbidity_event": {
        "label":          "High Turbidity Event",
        "condition_spec": {"Turbidity_NTU": ">P90"},
        "focus_parameters": [
            "Turbidity_NTU", "SuspendedSolids_mg_L", "Rainfall_mm",
            "Iron_mg_L", "Manganese_mg_L", "DOC_mg_L", "TrueColour_HU",
        ],
        "description": (
            "Characterises source water during the top-decile turbidity events. "
            "Reveals whether high turbidity is driven by storm runoff (with co-occurring "
            "DOC and colour), iron/manganese mobilisation, or other mechanisms. "
            "Governing design condition for coagulation and filtration capacity."
        ),
    },

    "colour_toc_event": {
        "label":          "High Colour / TOC Event (DBP Precursor Risk)",
        "condition_spec": {"TrueColour_HU": ">P80"},
        "focus_parameters": [
            "TrueColour_HU", "DOC_mg_L", "TOC_mg_L", "UV254_cm_1",
            "SUVA", "Bromide_mg_L", "Rainfall_mm", "pH",
        ],
        "description": (
            "Characterises source water during high-colour events (above P80 of "
            "TrueColour). High TOC, DOC, and UV254 during these conditions represent "
            "elevated disinfection by-product (DBP) precursor loading. SUVA characterises "
            "humic character; bromide co-occurrence drives brominated DBP risk."
        ),
    },

    "hardness_scaling": {
        "label":          "Hardness / Scaling Conditions",
        "condition_spec": {"Hardness_mg_L_as_CaCO3": ">200"},
        "focus_parameters": [
            "Hardness_mg_L_as_CaCO3", "Alkalinity_mg_L_as_CaCO3",
            "EC_uS_cm", "TDS_mg_L", "Chloride_mg_L", "pH",
            "Iron_mg_L", "Manganese_mg_L",
        ],
        "description": (
            "Characterises source water when hardness exceeds 200 mg/L as CaCO₃ "
            "(moderate-hard; scaling risk threshold). Reveals co-occurrence with "
            "alkalinity (Langelier Saturation Index inputs), EC, TDS, and other "
            "mineral parameters. Governing condition for softening or stabilisation "
            "process design."
        ),
    },

    "taste_odour_precursor": {
        "label":          "Taste and Odour Precursor Event",
        "condition_spec": {"Geosmin_ng_L": ">4"},
        "focus_parameters": [
            "Geosmin_ng_L", "MIB_ng_L", "Cyanobacteria_cells_mL",
            "Total_Algal_Cells_mL", "Chlorophyll_a_ug_L",
            "DOC_mg_L", "Temperature_C",
        ],
        "description": (
            "Characterises source water when geosmin exceeds 4 ng/L "
            "(ADWG 2022 aesthetic guideline). Reveals the algal community composition "
            "and physical conditions associated with taste/odour events. "
            "Governing design condition for activated carbon (PAC/GAC) dosing "
            "and advanced oxidation."
        ),
    },

    "disinfection_byproduct_risk": {
        "label":          "Disinfection By-Product Precursor Conditions",
        "condition_spec": {"Bromide_mg_L": ">0.05"},
        "focus_parameters": [
            "Bromide_mg_L", "DOC_mg_L", "TOC_mg_L", "UV254_cm_1",
            "TrueColour_HU", "Ammonia_N_mg_L", "pH", "Temperature_C",
        ],
        "description": (
            "Characterises source water when bromide exceeds 0.05 mg/L — the threshold "
            "above which bromate formation (ozonation) and brominated trihalomethane "
            "formation (chlorination) become material concerns. Co-occurrence of high "
            "DOC/TOC, UV254, and colour identifies the full DBP precursor burden."
        ),
    },
}
