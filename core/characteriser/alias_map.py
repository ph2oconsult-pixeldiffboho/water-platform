"""
core/characteriser/alias_map.py

First-pass column-alias map for AquaPoint, per v5.5 §0.0.4 (Amendment A).

Implements the normalised matching rule:
  1. Lowercase
  2. Strip leading/trailing whitespace
  3. Replace runs of [_, -, space, ., /] with single underscore
  4. Drop parenthesised/bracketed unit suffixes
  5. Exact match on normalised forms

Resolves column headers from real-world utility uploads (which vary by LIMS,
lab, and operational history) to the canonical column names expected by
the §1 parameter dictionary.

EXPLICIT CAVEAT: This is a first-pass alias map built from domain knowledge,
not from a sample of real utility uploads. Open Item 18 calls for extension
against deployment data. The entries below cover common syntactic variants;
they do NOT cover every variant in the wild.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


# ──────────────────────────────────────────────────────────────────────────
# NORMALISATION
# ──────────────────────────────────────────────────────────────────────────

# Pattern to match unit suffixes in parentheses or brackets
_UNIT_SUFFIX = re.compile(r"\s*[\(\[][^)\]]*[\)\]]\s*$")

# Pattern for canonical separator collapse
_SEPARATOR_RUN = re.compile(r"[\s_\-./]+")


def normalise(s: str) -> str:
    """Normalise a column header per v5.5 §0.0.4 rule.

    >>> normalise("Flow_MLD")
    'flow_mld'
    >>> normalise("Flow MLd")
    'flow_mld'
    >>> normalise("Turbidity (NTU)")
    'turbidity'
    >>> normalise("True_Colour_HU")
    'true_colour_hu'
    >>> normalise("TrueColour_HU")  # camelCase NOT auto-split; alias map handles
    'truecolour_hu'
    >>> normalise("DOC (mg/L)")
    'doc'
    """
    if not isinstance(s, str):
        return ""
    out = s.strip().lower()
    # Drop unit suffix in parens/brackets first (must happen before separator collapse)
    out = _UNIT_SUFFIX.sub("", out)
    out = out.strip()
    # Replace runs of separator chars with single underscore
    out = _SEPARATOR_RUN.sub("_", out)
    # Strip leading/trailing underscores
    out = out.strip("_")
    return out


# ──────────────────────────────────────────────────────────────────────────
# ALIAS REGISTRY
# ──────────────────────────────────────────────────────────────────────────

# Each entry: canonical_column → list of accepted aliases (in raw form;
# normalise() is applied to each at lookup time, so the entries here can
# be written in their natural form).
#
# Coverage philosophy: include the obvious case/separator variants and
# common unit-suffix decorations, NOT every conceivable spelling. Real
# deployment will surface more variants per Open Item 18.

ALIAS_MAP_RAW: dict[str, list[str]] = {
    # ── Physical / hydraulic
    "Flow_MLd": [
        "Flow_MLd", "Flow_MLD", "Flow_mLd",
        "Flow ML/d", "Flow_ML_d", "flow_ml_per_day",
        "Flow", "Flow_rate", "FlowRate",
        "Raw_Water_Flow_ML_d", "Flow_ML_D", "Inflow_MLd",
    ],
    "Rainfall_mm": [
        "Rainfall_mm", "Rainfall", "Rain_mm", "Rain",
        "Precipitation", "Precip_mm", "Precipitation_mm",
    ],
    "Turbidity_NTU": [
        "Turbidity_NTU", "Turbidity", "Turb_NTU", "Turb",
        "Turbidity (NTU)", "TURBIDITY", "Turbidity_ntu",
    ],
    "SuspendedSolids_mg_L": [
        "SuspendedSolids_mg_L", "Suspended_Solids_mg_L",
        "Suspended_Solids", "SuspendedSolids", "SS",
        "SS_mg_L", "TSS", "TSS_mg_L",
        "Total_Suspended_Solids",
    ],
    "Temperature_C": [
        "Temperature_C", "Temperature", "Temp_C", "Temp",
        "Temperature (degC)", "Temperature_degC", "Water_Temperature",
        "Water_Temp", "TempC",
    ],
    # ── Organic / optical
    "TrueColour_HU": [
        "TrueColour_HU", "True_Colour_HU", "True_Colour",
        "TrueColour", "Colour_HU", "Colour", "Color_HU", "Color",
        "TrueColor_HU", "True_Color",
        "True_Colour_Hazen", "Colour_Hazen", "TrueColour_Hazen",
        "Colour_HU_Hazen", "Apparent_Colour_HU",
    ],
    "DOC_mg_L": [
        "DOC_mg_L", "DOC", "DOC_mgL", "Dissolved_Organic_Carbon",
        "DOC (mg/L)",
    ],
    "TOC_mg_L": [
        "TOC_mg_L", "TOC", "TOC_mgL", "Total_Organic_Carbon",
        "TOC (mg/L)",
    ],
    "UV254_cm_1": [
        "UV254_cm_1", "UV254", "UV_254", "UV-254",
        "UV254_cm-1", "UV254 cm-1", "UVA254", "UVA_254",
        "UV_absorbance_254",
        "UV254_abs_cm", "UV254_absorbance_cm", "UV_254_abs",
        "UV254_Abs", "Absorbance_254nm",
    ],
    "UVT_pct_derived": [
        "UVT_pct_derived", "UVT_percent_derived", "UVT_pct",
        "UVT", "UVT_percent", "UVT (%)", "UV_Transmittance",
    ],
    "SUVA": [
        "SUVA", "SUVA_L_mg_m", "SUVA_L/mg/m",
        "Specific_UV_Absorbance",
    ],
    # ── Mineral / inorganic
    "Alkalinity_mg_L_as_CaCO3": [
        "Alkalinity_mg_L_as_CaCO3", "Alkalinity", "Alk",
        "Alkalinity_mg_L", "Total_Alkalinity",
        "Alkalinity as CaCO3",
    ],
    "Hardness_mg_L_as_CaCO3": [
        "Hardness_mg_L_as_CaCO3", "Hardness", "Hard",
        "Hardness_mg_L", "Total_Hardness",
        "Hardness as CaCO3",
    ],
    "EC_uS_cm": [
        "EC_uS_cm", "EC", "EC_uScm", "EC (µS/cm)",
        "Conductivity_uS_cm", "Conductivity", "Cond",
        "Specific_Conductance", "SpC", "EC25",
    ],
    "TDS_mg_L": [
        "TDS_mg_L", "TDS", "Total_Dissolved_Solids",
        "TDS_mgL",
    ],
    "Chloride_mg_L": [
        "Chloride_mg_L", "Chloride", "Cl", "Cl_mg_L",
        "Chloride_mgL",
    ],
    # ── Metals / redox
    "Iron_mg_L": [
        "Iron_mg_L", "Iron", "Fe", "Fe_mg_L",
        "Total_Iron", "Fe_total",
    ],
    "Manganese_mg_L": [
        "Manganese_mg_L", "Manganese", "Mn", "Mn_mg_L",
        "Total_Manganese", "Mn_total",
    ],
    "Ammonia_N_mg_L": [
        "Ammonia_N_mg_L", "Ammonia_N", "Ammonia",
        "NH4_N", "NH4-N", "NH3_N", "NH3-N",
        "NH4_N_mg_L", "Ammonia_as_N",
        "Ammonia_mg_L_as_N", "NH3_mg_L_as_N", "Ammonia_N_mg_L_as_N",
    ],
    "Nitrate_N_mg_L": [
        "Nitrate_N_mg_L", "Nitrate_N", "Nitrate",
        "NO3_N", "NO3-N", "NO3_N_mg_L", "Nitrate_as_N",
    ],
    "Total_Phosphorus_mg_L": [
        "Total_Phosphorus_mg_L", "Total_Phosphorus",
        "Total_P", "Total_P_mg_L", "TP", "TP_mg_L",
        "Total_Phosphorus_as_P",
    ],
    "DissolvedOxygen_mg_L": [
        "DissolvedOxygen_mg_L", "Dissolved_Oxygen_mg_L",
        "Dissolved_Oxygen", "DissolvedOxygen",
        "DO", "DO_mg_L", "DO_mgL",
    ],
    "pH": [
        "pH", "PH", "ph", "pH_value",
        "pH_lab", "pH_field",  # variants by sample site - both map to pH
    ],
    # ── Biological / algal
    "Chlorophyll_a_ug_L": [
        "Chlorophyll_a_ug_L", "Chlorophyll_a",
        "Chlorophyll-a", "ChlA", "Chl_a", "Chl-a",
        "Chlorophyll_a_µg_L", "Chla_ug_L",
    ],
    "Total_Algal_Cells_mL": [
        "Total_Algal_Cells_mL", "Total_Algal_Cells_cells_mL",
        "Total_Algal_Cells", "Algal_Cells",
        "Total_Cells", "Algae_cells_mL",
    ],
    "Algal_Biovolume_mm3_L": [
        "Algal_Biovolume_mm3_L", "Total_Algal_Biovolume",
        "Algal_Biovolume", "AlgalBiovolume",
        "Biovolume_total", "Total_Biovolume",
    ],
    "Cyanobacteria_cells_mL": [
        "Cyanobacteria_cells_mL", "Cyanobacteria",
        "Cyano_cells", "Cyanobacterial_cells",
        "Toxic_Cyanobacteria_cells", "Cyano",
        "Cyanobacteria_cells_per_mL",
    ],
    "Cyanobacterial_Biovolume_mm3_L": [
        "Cyanobacterial_Biovolume_mm3_L", "Cyanobacterial_Biovolume",
        "Cyano_Biovolume", "CyanoBiovolume",
        "Biovolume_cyanobacterial",
    ],
    "Microcystin_LR_ug_L": [
        "Microcystin_LR_ug_L", "Microcystin_LR",
        "Microcystin-LR", "Microcystin",
        "MC-LR", "MCLR", "mcyst_LR",
    ],
    # ── Taste and odour
    "Geosmin_ng_L": [
        "Geosmin_ng_L", "Geosmin", "Geo",
        "Geosmin_ngL",
    ],
    "MIB_ng_L": [
        "MIB_ng_L", "MIB", "2-MIB", "2_MIB",
        "MIB_ngL", "Methylisoborneol",
    ],
    # ── Microbial
    "E_coli_MPN_100mL": [
        "E_coli_MPN_100mL", "E_coli", "Ecoli", "E.coli",
        "E_coli_MPN", "E_coli_per_100mL",
        "Escherichia_coli", "Faecal_coliforms",  # often used interchangeably; flag if both present
    ],
    # ── Chemical markers
    "Bromide_mg_L": [
        "Bromide_mg_L", "Bromide", "Br", "Br_mg_L",
        "Bromide_mgL",
    ],
    "PFAS_sum_ng_L": [
        "PFAS_sum_ng_L", "PFAS_sum", "PFAS",
        "Total_PFAS", "Sum_PFAS", "PFAS_total",
        "PFAS_ngL",
        "PFAS_Total_ng_L", "Total_PFAS_ng_L", "PFAS_Sum_ng_L",
    ],
    "Arsenic_ug_L": [
        "Arsenic_ug_L", "Arsenic", "As", "As_ug_L",
        "Arsenic_µg_L", "Arsenic_mgL",
    ],

    # ── Major cations ─────────────────────────────────────────────────────────
    "Calcium_mg_L": [
        "Calcium_mg_L", "Calcium", "Ca", "Ca_mg_L", "Ca_mgL",
        "Calcium_mgL", "Total_Calcium",
    ],
    "Magnesium_mg_L": [
        "Magnesium_mg_L", "Magnesium", "Mg", "Mg_mg_L", "Mg_mgL",
        "Magnesium_mgL", "Total_Magnesium",
    ],

    # ── Biological / algal — extended ─────────────────────────────────────────
    "Phycocyanin_ug_L": [
        "Phycocyanin_ug_L", "Phycocyanin", "PC_ug_L", "Phycocyanin_ugL",
        "Phycocyanin_RFU", "Phycocyanin_ug_l",
    ],
    "Cyanotoxin_ug_L": [
        "Cyanotoxin_ug_L", "Cyanotoxin", "Total_Cyanotoxin",
        "Cyanotoxins_ug_L", "Total_Cyanotoxin_ug_L", "Cyanotoxin_ugL",
    ],

    # ── Pathogen indicators ───────────────────────────────────────────────────
    "Cryptosporidium_oocysts_10L": [
        "Cryptosporidium_oocysts_10L", "Cryptosporidium",
        "Crypto_oocysts_10L", "Crypto_10L",
        "Cryptosporidium_oocysts", "Cryptosporidium_10L",
    ],
    "Giardia_cysts_10L": [
        "Giardia_cysts_10L", "Giardia", "Giardia_cysts",
        "Giardia_10L", "Giardia_lamblia_cysts_10L",
    ],
    "Total_Coliforms_MPN_100mL": [
        "Total_Coliforms_MPN_100mL", "Total_Coliforms",
        "TotalColiforms", "Coliforms_MPN_100mL",
        "Total_Coliform_MPN", "TC_MPN_100mL",
    ],

    # ── Physical — extended ───────────────────────────────────────────────────
    "Particle_Count_gt2um_per_mL": [
        "Particle_Count_gt2um_per_mL", "Particle_Count_gt_2um_per_mL",
        "Particle_Count", "Particles_per_mL",
        "Particle_Count_2um", "PC_2um_per_mL",
    ],
}

# Build the normalised lookup table at import time
NORMALISED_ALIAS_MAP: dict[str, str] = {}
"""Maps normalised column header → canonical column name."""

_AMBIGUITY_LOG: dict[str, list[str]] = {}
"""Tracks any normalised forms that map to multiple canonicals; populated at module load."""


def _build_normalised_map() -> None:
    """Build NORMALISED_ALIAS_MAP at module load. Detects ambiguities."""
    seen: dict[str, str] = {}
    ambiguities: dict[str, list[str]] = {}
    for canonical, aliases in ALIAS_MAP_RAW.items():
        for alias in aliases:
            norm = normalise(alias)
            if not norm:
                continue
            if norm in seen and seen[norm] != canonical:
                # Ambiguity: two canonicals claim the same normalised form
                ambiguities.setdefault(norm, [seen[norm]]).append(canonical)
            else:
                seen[norm] = canonical
        # Also include the canonical itself (in case it's not in the alias list)
        norm_canonical = normalise(canonical)
        if norm_canonical and norm_canonical not in seen:
            seen[norm_canonical] = canonical
    NORMALISED_ALIAS_MAP.update(seen)
    _AMBIGUITY_LOG.update(ambiguities)


_build_normalised_map()


# ──────────────────────────────────────────────────────────────────────────
# RESOLUTION API
# ──────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class AliasResolution:
    """Result of resolving a single column header."""
    original: str
    normalised: str
    canonical: str | None
    status: str  # 'resolved' | 'unresolved' | 'ambiguous'
    ambiguity_candidates: tuple[str, ...] = ()


def resolve_column(name: str) -> AliasResolution:
    """Resolve a single column header to its canonical form.

    Returns AliasResolution with status:
      - 'resolved' if normalised form is in the alias map
      - 'unresolved' if no match (caller should warn but NOT drop the column)
      - 'ambiguous' if normalised form maps to multiple canonicals
    """
    norm = normalise(name)
    if not norm:
        return AliasResolution(name, norm, None, "unresolved")
    if norm in _AMBIGUITY_LOG:
        return AliasResolution(
            name, norm, None, "ambiguous",
            ambiguity_candidates=tuple(_AMBIGUITY_LOG[norm]),
        )
    canonical = NORMALISED_ALIAS_MAP.get(norm)
    if canonical is None:
        return AliasResolution(name, norm, None, "unresolved")
    return AliasResolution(name, norm, canonical, "resolved")


def resolve_columns(headers: list[str]) -> tuple[dict[str, str], list[AliasResolution]]:
    """Resolve a list of column headers in bulk.

    Returns:
        rename_map: dict[original_header → canonical_column_name] for columns
                    that resolved cleanly (omits unresolved and ambiguous)
        all_results: list of AliasResolution for every input header
                     (caller can use this to emit Warning/Critical flags)
    """
    rename_map = {}
    results = []
    for h in headers:
        r = resolve_column(h)
        results.append(r)
        if r.status == "resolved":
            rename_map[r.original] = r.canonical
    return rename_map, results


# ──────────────────────────────────────────────────────────────────────────
# DIAGNOSTICS
# ──────────────────────────────────────────────────────────────────────────

def report_alias_map_health() -> str:
    """Diagnostic summary of the alias map for spec / engineering review."""
    n_canonicals = len(ALIAS_MAP_RAW)
    n_aliases = sum(len(v) for v in ALIAS_MAP_RAW.values())
    n_normalised = len(NORMALISED_ALIAS_MAP)
    n_ambiguous = len(_AMBIGUITY_LOG)
    lines = [
        f"Alias map: {n_canonicals} canonical columns, {n_aliases} raw aliases, "
        f"{n_normalised} unique normalised forms, {n_ambiguous} ambiguities.",
    ]
    if _AMBIGUITY_LOG:
        lines.append("Ambiguities (review needed):")
        for norm, canonicals in _AMBIGUITY_LOG.items():
            lines.append(f"  '{norm}' → {sorted(set(canonicals))}")
    return "\n".join(lines)


if __name__ == "__main__":
    print(report_alias_map_health())
    print()
    # Quick sanity demo
    for test in ["Flow_MLD", "Flow_MLd", "Conductivity_uS_cm", "EC", "True_Colour_HU",
                 "Turbidity (NTU)", "TURBIDITY", "DOC (mg/L)", "made_up_column"]:
        r = resolve_column(test)
        print(f"  {test!r:30s} → {r.canonical or r.status}")
