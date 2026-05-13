"""
core/characteriser/correlation_heatmap.py

Spearman correlation heatmap module for the water-platform characteriser.
========================================================================

Scope: input-data characterisation only. Surfaces "what variables move
together in this dataset"; does NOT produce treatment, dosing, or
operational recommendations.

Per AquaPoint engineering rule table v5.5 §6.3.

Schema alignment (v5.5 schema reconciliation, May 2026)
--------------------------------------------------------
This module previously produced a parallel `CorrelationCell` dataclass.
That type has been removed; the module now produces `CrossCorrelation`
objects from `core.characteriser.report`, which is the existing schema
type for cross-parameter correlation results.

Mapping from old CorrelationCell → CrossCorrelation:
  rho, p_value, n_pair, confidence → spearman_lag0 (Statistic)
  relationship_type, rationale     → observation.pattern / .note
  intermediate_parameter           → observation.candidates[0].explanation
  pearson_lag0                     → Statistic(applicability=Not applicable)
  best_lag_days                    → None  (lag analysis is future scope)

The §7 Explanation layer (explanation.py) has been removed. The
architectural commitment — every output carries a structured trace —
is fulfilled by populating CrossCorrelation.observation (Observation)
on every cell. This is the existing schema type for the same purpose.

Public API (unchanged from prior version)
-----------------------------------------
  select_numeric_variables(df, module_registry, user_selection=None)
  compute_spearman_matrix(df, variables, min_pair_n=10)
      → dict[tuple[str,str], CrossCorrelation]
  classify_relationships(matrix, registry_relationship_metadata)
      → dict[tuple[str,str], CrossCorrelation]
  build_heatmap_payload(matrix, variables, title, n_obs, subtitle=None)
  render_heatmap_png(payload, output_path)
  build_top_relationship_table(matrix, variables, min_abs_rho=0.6)
  compare_full_vs_subset_heatmaps(df, subset_mask, variables)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

import numpy as np
import pandas as pd
from scipy import stats

from .report import (
    APPLIC_INSUFFICIENT,
    APPLIC_LIMITED,
    APPLIC_NOT_APPLICABLE,
    APPLIC_OK,
    CandidateExplanation,
    CrossCorrelation,
    Observation,
    Statistic,
)


# ── Registry types ────────────────────────────────────────────────────────────
#
# VariableSpec and RelationshipSpec are local to this module.
# They serve the heatmap renderer (VariableSpec carries short labels and
# group information for axis layout) and the relationship classifier
# (RelationshipSpec is the internal registry used by classify_relationships).
#
# The authoritative source for AquaPoint relationship metadata is
# CharacterisationConfig.relationships (List[config_schema.RelationshipSpec]).
# The local RelationshipSpec here is a simplified form used only as the
# default argument to classify_relationships(); callers can pass the config
# registry directly by converting it.

@dataclass(frozen=True)
class VariableSpec:
    """
    A variable in the correlation registry.

    name:                short label for axis tick (e.g. 'Turb')
    long_name:           full name for hover/legend (e.g. 'Turbidity NTU')
    column:              canonical column name in the dataframe
    group:               heatmap grouping (matches config_schema.GROUP_* values)
    kind:                'observed' | 'derived'
    lod_aware:           True if the parameter has a declared detection limit
    excluded_from_main:  True → never included in the default heatmap
    """
    name:               str
    long_name:          str
    column:             str
    group:              str
    kind:               str = "observed"
    lod_aware:          bool = False
    excluded_from_main: bool = False


@dataclass(frozen=True)
class RelationshipSpec:
    """
    A known relationship between two variables (internal registry type).

    relationship_type ∈ {
      'structural'          — mathematically linked (e.g. UV254 → UVT)
      'expected'            — biologically or geochemically expected
      'derived_via_structural' — inherited through a structural chain
      'observed'            — default; no prior expectation
    }
    """
    var_a:             str   # column name
    var_b:             str   # column name
    relationship_type: str
    rationale:         str

    def involves(self, col_a: str, col_b: str) -> bool:
        return {self.var_a, self.var_b} == {col_a, col_b}


# ── AquaPoint variable registry ───────────────────────────────────────────────
#
# One entry per monitored parameter. Short names ('Turb', 'DOC') are used
# on heatmap axes; long names appear in legends and the top-relationship table.
# Column names must match the canonical names in characteriser_config.py.

AQUAPOINT_VARIABLES: list[VariableSpec] = [
    # Physical / hydraulic
    VariableSpec("Flow",  "Flow ML/day",          "Flow_MLd",                       "physical"),
    VariableSpec("Turb",  "Turbidity NTU",         "Turbidity_NTU",                  "physical"),
    VariableSpec("SS",    "Suspended solids",      "SuspendedSolids_mg_L",           "physical"),
    VariableSpec("Temp",  "Temperature",           "Temperature_C",                  "physical"),
    VariableSpec("Rain",  "Rainfall",              "Rainfall_mm",                    "physical"),
    # Organic / optical
    VariableSpec("Colour","True colour HU",        "TrueColour_HU",                  "organic"),
    VariableSpec("DOC",   "DOC",                   "DOC_mg_L",                       "organic"),
    VariableSpec("TOC",   "TOC",                   "TOC_mg_L",                       "organic"),
    VariableSpec("UV254", "UV254 cm⁻¹",            "UV254_cm_1",                     "organic"),
    VariableSpec("UVT",   "UVT %",                 "UVT_pct_derived",                "organic",  kind="derived"),
    VariableSpec("SUVA",  "SUVA L/(mg·m)",         "SUVA",                           "organic",  kind="derived"),
    # Mineral / inorganic
    VariableSpec("Alk",   "Alkalinity",            "Alkalinity_mg_L_as_CaCO3",       "mineral"),
    VariableSpec("Hard",  "Hardness",              "Hardness_mg_L_as_CaCO3",         "mineral"),
    VariableSpec("EC",    "Conductivity µS/cm",    "EC_uS_cm",                       "mineral"),
    VariableSpec("TDS",   "TDS",                   "TDS_mg_L",                       "mineral"),
    VariableSpec("Cl",    "Chloride",              "Chloride_mg_L",                  "mineral"),
    # Metals / redox
    VariableSpec("Fe",    "Iron",                  "Iron_mg_L",                      "metals"),
    VariableSpec("Mn",    "Manganese",             "Manganese_mg_L",                 "metals"),
    VariableSpec("NH4",   "Ammonia-N",             "Ammonia_N_mg_L",                 "nutrients"),
    VariableSpec("NO3",   "Nitrate-N",             "Nitrate_N_mg_L",                 "nutrients"),
    VariableSpec("DO",    "Dissolved oxygen",      "DissolvedOxygen_mg_L",           "biological"),
    VariableSpec("pH",    "pH",                    "pH",                             "biological"),
    VariableSpec("TP",    "Total phosphorus",      "Total_Phosphorus_mg_L",          "nutrients"),
    # Biological / algal
    VariableSpec("ChlA",  "Chlorophyll-a",         "Chlorophyll_a_ug_L",             "biological"),
    VariableSpec("AlgC",  "Total algal cells",     "Total_Algal_Cells_mL",           "biological"),
    VariableSpec("AlgBV", "Total algal biovolume", "Algal_Biovolume_mm3_L",          "biological"),
    VariableSpec("CyaC",  "Cyano cells",           "Cyanobacteria_cells_mL",         "biological", lod_aware=True),
    VariableSpec("CyaBV", "Cyano biovolume",       "Cyanobacterial_Biovolume_mm3_L", "biological", lod_aware=True),
    VariableSpec("Mcst",  "Microcystin-LR",        "Microcystin_LR_ug_L",            "microbial",  lod_aware=True),
    # Taste and odour
    VariableSpec("Geo",   "Geosmin",               "Geosmin_ng_L",                   "chemical",   lod_aware=True),
    VariableSpec("MIB",   "2-MIB",                 "MIB_ng_L",                       "chemical",   lod_aware=True),
    # Microbial
    VariableSpec("EColi", "E. coli",               "E_coli_MPN_100mL",               "microbial",  lod_aware=True),
    # Chemical markers
    VariableSpec("Br",    "Bromide",               "Bromide_mg_L",                   "chemical",   lod_aware=True),
    VariableSpec("PFAS",  "PFAS",                  "PFAS_sum_ng_L",                  "chemical",   lod_aware=True),
    VariableSpec("As",    "Arsenic",               "Arsenic_ug_L",                   "chemical",   lod_aware=True),

    # Major cations (new)
    VariableSpec("Ca",    "Calcium",               "Calcium_mg_L",                   "mineral"),
    VariableSpec("Mg",    "Magnesium",             "Magnesium_mg_L",                 "mineral"),

    # Biological / algal — extended (new)
    VariableSpec("PC",    "Phycocyanin",           "Phycocyanin_ug_L",               "biological", lod_aware=True),
    VariableSpec("Ctox",  "Cyanotoxin (total)",    "Cyanotoxin_ug_L",                "microbial",  lod_aware=True),

    # Pathogen indicators (new)
    VariableSpec("Crypt", "Cryptosporidium",       "Cryptosporidium_oocysts_10L",    "microbial",  lod_aware=True),
    VariableSpec("Giard", "Giardia",               "Giardia_cysts_10L",              "microbial",  lod_aware=True),
    VariableSpec("TC",    "Total Coliforms",       "Total_Coliforms_MPN_100mL",      "microbial"),

    # Physical — extended (new)
    VariableSpec("PrtCt", "Particle Count (>2µm)", "Particle_Count_gt2um_per_mL",    "physical"),
]


# Internal relationship registry — used as default arg to classify_relationships().
# The authoritative source is CharacterisationConfig.relationships;
# callers should prefer passing that directly.
_AQUAPOINT_RELATIONSHIPS: list[RelationshipSpec] = [
    # Structural
    RelationshipSpec("UV254_cm_1", "UVT_pct_derived", "structural",
                     "UVT is mathematically derived from UV254 via Beer-Lambert law. "
                     "The correlation is definitional, not observed."),
    RelationshipSpec("UV254_cm_1", "SUVA", "expected",
                     "SUVA = (UV254 × 100) / DOC. UV254 is in the numerator, so they share "
                     "a component — but SUVA is independently computed and the relationship "
                     "is not mathematically fixed because DOC (the denominator) varies. "
                     "Expected strong positive correlation; strength reflects DOC variability."),
    RelationshipSpec("DOC_mg_L", "SUVA", "expected",
                     "SUVA = (UV254 × 100) / DOC. DOC is in the denominator, creating an "
                     "inverse shared-component relationship. Expected negative or weak "
                     "correlation depending on whether UV254 or DOC drives SUVA variation "
                     "more at this source."),
    RelationshipSpec("TrueColour_HU", "SUVA", "expected",
                     "True colour is driven by chromophoric humic/fulvic acids that also "
                     "absorb at 254 nm. Expected positive correlation between colour and SUVA "
                     "in humic catchments; both respond to the same aromatic organic fraction. "
                     "Weak or inverse correlations may occur if colour and UV254 respond "
                     "differently to storm events."),
    RelationshipSpec("DOC_mg_L", "TOC_mg_L", "expected",
                     "DOC is the dissolved fraction of TOC and DOC ≤ TOC holds as a physical constraint, "
                     "but DOC and TOC are independently measured channels. Analytical uncertainty, "
                     "particulate fraction variability, and filtration method differences mean the "
                     "correlation is physically expected but not mathematically fixed."),
    RelationshipSpec("Cyanobacteria_cells_mL", "Total_Algal_Cells_mL", "structural",
                     "Cyanobacteria is a taxonomic subset of total algal cells."),
    RelationshipSpec("Cyanobacterial_Biovolume_mm3_L", "Algal_Biovolume_mm3_L", "structural",
                     "Cyanobacterial biovolume is a component of total algal biovolume."),
    # Expected
    RelationshipSpec("EC_uS_cm", "TDS_mg_L", "expected",
                     "EC and TDS are expected to co-vary; TDS is commonly estimated from EC "
                     "via a fixed conversion factor (~0.64)."),
    RelationshipSpec("Alkalinity_mg_L_as_CaCO3", "Hardness_mg_L_as_CaCO3", "expected",
                     "In carbonate-dominated systems hardness and alkalinity co-vary with geological source."),
    RelationshipSpec("DOC_mg_L", "UV254_cm_1", "expected",
                     "Chromophoric DOC absorbs at 254 nm; higher DOC typically increases UV254."),
    RelationshipSpec("DOC_mg_L", "TrueColour_HU", "expected",
                     "Humic and fulvic acids drive both DOC and true colour."),
    RelationshipSpec("TrueColour_HU", "UV254_cm_1", "expected",
                     "Both colour and UV254 respond to humic dissolved organics."),
    RelationshipSpec("TOC_mg_L", "UV254_cm_1", "expected",
                     "TOC includes the chromophoric dissolved fraction; expected correlation "
                     "but weaker than DOC↔UV254."),
    RelationshipSpec("Turbidity_NTU", "SuspendedSolids_mg_L", "expected",
                     "Turbidity is an optical proxy for suspended solids."),
    RelationshipSpec("Turbidity_NTU", "Iron_mg_L", "expected",
                     "Particulate iron is a common turbidity driver in surface catchments."),
    RelationshipSpec("Chlorophyll_a_ug_L", "Total_Algal_Cells_mL", "expected",
                     "Chlorophyll-a is the primary algal biomass pigment."),
    RelationshipSpec("Chlorophyll_a_ug_L", "Cyanobacteria_cells_mL", "expected",
                     "Cyanobacteria contain chlorophyll-a; expected positive correlation."),
    RelationshipSpec("EC_uS_cm", "Hardness_mg_L_as_CaCO3", "expected",
                     "Divalent cations (Ca²⁺, Mg²⁺) contribute significantly to specific conductance."),
    RelationshipSpec("EC_uS_cm", "Alkalinity_mg_L_as_CaCO3", "expected",
                     "Bicarbonate and carbonate ions are major contributors to conductance."),
    RelationshipSpec("Rainfall_mm", "Turbidity_NTU", "expected",
                     "Storm runoff entrains particulates; turbidity responds to rainfall events."),
    RelationshipSpec("Rainfall_mm", "DOC_mg_L", "expected",
                     "Storm flushing mobilises dissolved organic matter from catchment soils."),
    RelationshipSpec("Cyanobacteria_cells_mL", "Microcystin_LR_ug_L", "expected",
                     "Microcystin is produced by cyanobacteria; expected but highly variable."),
    RelationshipSpec("Cyanobacteria_cells_mL", "Geosmin_ng_L", "expected",
                     "Geosmin is produced by specific cyanobacteria genera (Anabaena, Oscillatoria)."),
    RelationshipSpec("Cyanobacteria_cells_mL", "MIB_ng_L", "expected",
                     "2-MIB is produced by specific cyanobacteria (Planktothrix, Pseudanabaena)."),

    # New parameter relationships
    RelationshipSpec("Phycocyanin_ug_L", "Cyanobacteria_cells_mL", "expected",
                     "Phycocyanin is the primary blue-green pigment in cyanobacteria. "
                     "Expected strong positive correlation with cell count."),
    RelationshipSpec("Phycocyanin_ug_L", "Cyanotoxin_ug_L", "expected",
                     "Cyanotoxins are produced by cyanobacteria; phycocyanin is a "
                     "cyanobacterial biomass proxy. Expected positive correlation."),
    RelationshipSpec("Cryptosporidium_oocysts_10L", "Giardia_cysts_10L", "expected",
                     "Both are protozoan pathogens associated with faecal contamination "
                     "and commonly co-occur following storm-driven catchment runoff."),
    RelationshipSpec("Cryptosporidium_oocysts_10L", "E_coli_MPN_100mL", "expected",
                     "Both indicate faecal contamination; expected positive correlation "
                     "during storm-driven runoff events."),
    RelationshipSpec("Particle_Count_gt2um_per_mL", "Turbidity_NTU", "expected",
                     "Particle count and turbidity are both responses to particulate matter. "
                     "Expected positive correlation; may decouple during algal blooms."),
    RelationshipSpec("Calcium_mg_L", "Hardness_mg_L_as_CaCO3", "expected",
                     "Calcium is a primary component of total hardness. "
                     "Expected strong positive correlation."),
    RelationshipSpec("Magnesium_mg_L", "Hardness_mg_L_as_CaCO3", "expected",
                     "Magnesium is a primary component of total hardness alongside calcium."),
    RelationshipSpec("Calcium_mg_L", "Alkalinity_mg_L_as_CaCO3", "expected",
                     "In carbonate-dominated systems calcium and bicarbonate alkalinity "
                     "co-vary with geological source."),
]


# ── Internal helpers ──────────────────────────────────────────────────────────

def _confidence_label(n_pair: int) -> str:
    if n_pair < 10:   return "Insufficient"
    if n_pair < 30:   return "Limited"
    if n_pair < 100:  return "Acceptable"
    return "Strong"


def _confidence_to_applicability(confidence: str, lod_heavy: bool) -> str:
    """Map confidence label + lod_heavy flag to Statistic.applicability."""
    if confidence == "Insufficient":
        return APPLIC_INSUFFICIENT
    if lod_heavy or confidence == "Limited":
        return APPLIC_LIMITED
    return APPLIC_OK


def _evidence_strength(confidence: str) -> str:
    return {"Strong": "Strong", "Acceptable": "Moderate"}.get(confidence, "Weak")


def _censoring_fraction(
    series: pd.Series,
    spec: Optional[VariableSpec],
    lod_substitution_counts: Optional[dict[str, int]] = None,
) -> float:
    """Return fraction of series values at the LoD-substituted value."""
    if spec is None or not spec.lod_aware:
        return 0.0
    valid = series.dropna()
    if len(valid) == 0:
        return 0.0
    if lod_substitution_counts and spec.column in lod_substitution_counts:
        return lod_substitution_counts[spec.column] / len(valid)
    counts = valid.value_counts()
    return counts.iloc[0] / len(valid) if len(counts) else 0.0


def _build_spearman_statistic(
    rho: Optional[float],
    p_value: Optional[float],
    n_pair: int,
    confidence: str,
    lod_heavy: bool,
    censored_fraction_pct: Optional[float],
) -> Statistic:
    """Construct the spearman_lag0 Statistic for a CrossCorrelation."""
    applicability = _confidence_to_applicability(confidence, lod_heavy)

    note_parts = []
    if p_value is not None:
        note_parts.append(f"p={p_value:.4f}")
    if lod_heavy and censored_fraction_pct is not None:
        note_parts.append(f"lod_heavy: {censored_fraction_pct:.0f}% censored")
    elif censored_fraction_pct is not None:
        note_parts.append(f"censored: {censored_fraction_pct:.0f}%")

    return Statistic(
        value=rho,
        unit="",
        applicability=applicability,
        n=n_pair,
        note="; ".join(note_parts),
        basis="Spearman rank correlation, pairwise complete observations",
    )


def _build_observation(
    rho: Optional[float],
    confidence: str,
    relationship_type: str,
    rationale: Optional[str],
    intermediate_parameter: Optional[str],
    n_pair: int,
) -> Observation:
    """
    Construct the CrossCorrelation.observation for a cell.

    Replaces _build_correlation_explanation() from the prior version.
    Uses Observation + CandidateExplanation — existing report.py types —
    rather than the now-dropped Explanation dataclass.
    """
    # Finding string
    if rho is None:
        finding = f"Insufficient data ({n_pair} paired observations) — ρ not computed."
    else:
        direction = "positive" if rho > 0 else "negative"
        magnitude = (
            "strong" if abs(rho) >= 0.8 else
            "moderate" if abs(rho) >= 0.6 else
            "weak"
        )
        finding = (
            f"ρ = {rho:+.3f} ({confidence}, n={n_pair}). "
            f"{magnitude.title()} {direction} rank correlation."
        )

    evidence = _evidence_strength(confidence) if rho is not None else "Weak"

    # Candidates — one candidate for derived_via_structural (names the chain);
    # empty for all other types (the pattern string carries the framing)
    candidates: list[CandidateExplanation] = []
    if relationship_type == "derived_via_structural" and intermediate_parameter:
        candidates.append(CandidateExplanation(
            explanation=(
                f"Inherited via {intermediate_parameter}: the correlation is "
                f"mathematically constrained by a structural chain through "
                f"{intermediate_parameter}, not an independent empirical finding."
            ),
            plausibility="Likely",
            discriminating_test=(
                f"Partial correlation controlling for {intermediate_parameter} "
                "should reduce ρ substantially if the chain is the primary driver."
            ),
            weight=1.0,
        ))
    elif relationship_type == "expected" and rationale:
        candidates.append(CandidateExplanation(
            explanation=rationale,
            plausibility="Likely",
            discriminating_test=(
                "Confirm by checking whether the relationship is consistent "
                "across different seasons and flow regimes."
            ),
        ))
    elif relationship_type == "observed" and rho is not None and abs(rho) >= 0.6:
        candidates.append(CandidateExplanation(
            explanation="Mechanism not pre-specified; examine site-specific conditions.",
            plausibility="Possible",
            discriminating_test=(
                "Review coincident events, seasonal patterns, or known "
                "site-specific drivers to identify the most likely mechanism."
            ),
        ))

    return Observation(
        pattern=relationship_type,
        finding=finding,
        evidence_strength=evidence,
        candidates=candidates,
        note=rationale or "",
    )


def _plain_english_observation(
    a_long: str, b_long: str, rho: float, rel_type: str
) -> str:
    """Plain-English row for the top-relationship table."""
    direction = "move together" if rho > 0 else "move in opposite directions"
    magnitude = (
        "strongly" if abs(rho) >= 0.8 else
        "moderately" if abs(rho) >= 0.6 else "weakly"
    )
    base = f"The data show that {a_long} and {b_long} {direction} {magnitude}."
    if rel_type == "expected":
        return f"{base} This is an expected coupling and not a novel finding."
    if rel_type == "structural":
        return f"{base} This relationship is mathematical, not observational."
    if rel_type == "derived_via_structural":
        return (
            f"{base} This relationship is inherited through a structural chain — "
            "the correlation is mathematically constrained by an intermediate "
            "derivation, not an independent empirical finding."
        )
    return base


# ── Public API ────────────────────────────────────────────────────────────────

def select_numeric_variables(
    df: pd.DataFrame,
    module_registry: list[VariableSpec] = AQUAPOINT_VARIABLES,
    user_selection: Optional[Iterable[str]] = None,
    group: Optional[str] = None,
    include_derived: bool = True,
    include_excluded: bool = False,
) -> list[VariableSpec]:
    """
    Select variables to include in the correlation heatmap.

    Picks numeric columns present in `df` that are also in the registry.
    Excludes non-numeric (object, datetime) columns implicitly.
    Honours the `excluded_from_main` flag unless `include_excluded=True`.

    Selection precedence:
      1. user_selection (list of variable short-names or column names)
      2. group filter
      3. all registry variables present in df
    """
    df_cols = set(df.columns)
    available = []
    for v in module_registry:
        if v.column not in df_cols:
            continue
        if not pd.api.types.is_numeric_dtype(df[v.column]):
            continue
        if v.kind == "derived" and not include_derived:
            continue
        if v.excluded_from_main and not include_excluded:
            continue
        available.append(v)

    if user_selection is not None:
        sel = set(user_selection)
        available = [v for v in available if v.name in sel or v.column in sel]

    if group is not None:
        available = [v for v in available if v.group == group]

    return available


def compute_spearman_matrix(
    df: pd.DataFrame,
    variables: list[VariableSpec],
    min_pair_n: int = 10,
    lod_substitution_counts: Optional[dict[str, int]] = None,
) -> dict[tuple[str, str], CrossCorrelation]:
    """
    Compute pairwise Spearman correlation matrix.

    Returns a dict keyed by (col_a, col_b) upper-triangle pairs.
    Values are CrossCorrelation objects with spearman_lag0 populated.
    observation and pearson_lag0 are set to sensible defaults;
    classify_relationships() fills in observation.pattern and .candidates.

    Changes from prior version
    --------------------------
    - Returns CrossCorrelation (report.py) instead of CorrelationCell
    - Censoring annotations → spearman_lag0.applicability + .note
    - pearson_lag0 → Statistic(applicability=APPLIC_NOT_APPLICABLE)
    - best_lag_days → None  (lag analysis is future scope)
    """
    cells: dict[tuple[str, str], CrossCorrelation] = {}
    cols = [v.column for v in variables]
    spec_by_col = {v.column: v for v in variables}

    _not_applicable = Statistic(
        applicability=APPLIC_NOT_APPLICABLE,
        note="Spearman only; Pearson not computed by this module.",
    )

    for i, col_a in enumerate(cols):
        for col_b in cols[i:]:
            if col_a == col_b:
                continue

            s_a = df[col_a]
            s_b = df[col_b]
            mask = s_a.notna() & s_b.notna()
            n_pair = int(mask.sum())
            confidence = _confidence_label(n_pair)

            # Censoring fractions (Amendment C)
            frac_a = _censoring_fraction(s_a, spec_by_col.get(col_a), lod_substitution_counts)
            frac_b = _censoring_fraction(s_b, spec_by_col.get(col_b), lod_substitution_counts)
            max_frac = max(frac_a, frac_b)
            lod_heavy = max_frac > 0.5
            censored_pct = round(max_frac * 100, 1) if max_frac > 0.2 else None

            # Spearman computation
            rho: Optional[float] = None
            p_value: Optional[float] = None
            if n_pair >= min_pair_n:
                try:
                    res = stats.spearmanr(s_a[mask], s_b[mask])
                    if not np.isnan(res.correlation):
                        rho = float(res.correlation)
                    if not np.isnan(res.pvalue):
                        p_value = float(res.pvalue)
                except Exception:
                    pass

            spearman_stat = _build_spearman_statistic(
                rho, p_value, n_pair, confidence, lod_heavy, censored_pct
            )

            # Placeholder observation — classify_relationships() fills this in
            obs = _build_observation(
                rho=rho,
                confidence=confidence,
                relationship_type="observed",   # default; overridden in classify_relationships
                rationale=None,
                intermediate_parameter=None,
                n_pair=n_pair,
            )

            cells[(col_a, col_b)] = CrossCorrelation(
                parameter_a=col_a,
                parameter_b=col_b,
                pearson_lag0=_not_applicable,
                spearman_lag0=spearman_stat,
                best_lag_days=None,
                best_lag_corr=Statistic(applicability=APPLIC_NOT_APPLICABLE),
                interpretation="",     # deprecated field — leave empty
                observation=obs,
            )

    return cells


def classify_relationships(
    cells: dict[tuple[str, str], CrossCorrelation],
    relationships: list[RelationshipSpec] = _AQUAPOINT_RELATIONSHIPS,
    transitive_min_rho: float = 0.6,
) -> dict[tuple[str, str], CrossCorrelation]:
    """
    Annotate cells with relationship type, rationale, and Observation.

    Three passes (same logic as prior version; output type changed):
      1. Registry lookup: direct match sets observation.pattern
      2. Transitive propagation (Amendment B): structural chain detection
         reclassifies 'observed' pairs to 'derived_via_structural'
      3. Observation rebuild: every cell gets a fully populated Observation
         reflecting its final classification

    The relationship_type is stored in CrossCorrelation.observation.pattern.
    Accessor helper get_relationship_type(cell) reads it back.
    """

    def _get_rho(cell: CrossCorrelation) -> Optional[float]:
        return cell.spearman_lag0.value

    def _get_pattern(cell: CrossCorrelation) -> str:
        return cell.observation.pattern if cell.observation else "observed"

    def _set_pattern(cell: CrossCorrelation, pattern: str, note: str) -> None:
        """Update observation.pattern and .note in place."""
        old = cell.observation
        cell.observation = Observation(
            pattern=pattern,
            finding=old.finding if old else "",
            evidence_strength=old.evidence_strength if old else "Weak",
            candidates=old.candidates if old else [],
            note=note,
        )

    # ── Pass 1: registry lookup ───────────────────────────────────────────────
    for (a, b), cell in cells.items():
        for rel in relationships:
            if rel.involves(a, b):
                _set_pattern(cell, rel.relationship_type, rel.rationale)
                break

    # ── Pass 2: transitive propagation (Amendment B) ──────────────────────────
    # If A↔B is structural AND B↔C is expected/observed with |ρ| ≥ transitive_min_rho,
    # reclassify A↔C from 'observed' to 'derived_via_structural'.
    # Single-hop only (v5.5 §6.3.3).

    structural_neighbours: dict[str, list[str]] = {}
    for (a, b), cell in cells.items():
        if _get_pattern(cell) == "structural":
            structural_neighbours.setdefault(a, []).append(b)
            structural_neighbours.setdefault(b, []).append(a)

    def _get_cell(x: str, y: str) -> Optional[CrossCorrelation]:
        return cells.get((x, y)) or cells.get((y, x))

    reclassifications: list[tuple[str, str, str, str]] = []
    for (a, c), cell in cells.items():
        if _get_pattern(cell) != "observed":
            continue
        rho_ac = _get_rho(cell)
        if rho_ac is None:
            continue
        # Try: A↔B structural, B↔C strong
        for b in structural_neighbours.get(a, []):
            if b == c:
                continue
            bc = _get_cell(b, c)
            if bc is None or _get_rho(bc) is None:
                continue
            if (_get_pattern(bc) in ("expected", "observed")
                    and abs(_get_rho(bc)) >= transitive_min_rho):
                reclassifications.append((a, c, b, "structural_a"))
                break
        else:
            # Try: A↔B strong, B↔C structural
            for b in structural_neighbours.get(c, []):
                if b == a:
                    continue
                ab = _get_cell(a, b)
                if ab is None or _get_rho(ab) is None:
                    continue
                if (_get_pattern(ab) in ("expected", "observed")
                        and abs(_get_rho(ab)) >= transitive_min_rho):
                    reclassifications.append((a, c, b, "structural_c"))
                    break

    for a, c, intermediate, direction in reclassifications:
        cell = _get_cell(a, c)
        if cell is None:
            continue
        if direction == "structural_a":
            rationale = (
                f"Inherited via {intermediate}: {a}↔{intermediate} is structural "
                f"(mathematically derived); {intermediate}↔{c} is empirically coupled. "
                f"The {a}↔{c} correlation is mathematically constrained by the chain, "
                "not an independent finding."
            )
        else:
            rationale = (
                f"Inherited via {intermediate}: {intermediate}↔{c} is structural "
                f"(mathematically derived); {a}↔{intermediate} is empirically coupled. "
                f"The {a}↔{c} correlation is mathematically constrained by the chain, "
                "not an independent finding."
            )
        _set_pattern(cell, "derived_via_structural", rationale)

    # ── Pass 3: rebuild Observation with final classification ─────────────────
    # Now that every cell has its final pattern, rebuild the full Observation
    # (finding, evidence_strength, candidates all depend on the final type).

    for (a, b), cell in cells.items():
        pattern = _get_pattern(cell)
        note    = cell.observation.note if cell.observation else ""
        rho     = _get_rho(cell)
        n_pair  = cell.spearman_lag0.n or 0
        confidence = _confidence_label(n_pair)

        # Recover intermediate_parameter from the rationale note for derived cells
        intermediate: Optional[str] = None
        if pattern == "derived_via_structural" and "Inherited via " in note:
            # Extract the intermediate parameter name from the rationale string
            try:
                intermediate = note.split("Inherited via ")[1].split(":")[0].strip()
            except IndexError:
                pass

        cell.observation = _build_observation(
            rho=rho,
            confidence=confidence,
            relationship_type=pattern,
            rationale=note,
            intermediate_parameter=intermediate,
            n_pair=n_pair,
        )

    return cells


def get_relationship_type(cell: CrossCorrelation) -> str:
    """
    Read the relationship type from a CrossCorrelation.

    The type is stored in cell.observation.pattern.
    Returns 'observed' if observation is None (should not occur after classify_relationships).
    """
    if cell.observation is None:
        return "observed"
    return cell.observation.pattern


# ── Heatmap payload and renderer ──────────────────────────────────────────────
#
# These are unchanged from the prior version except:
#   - cells dict type is now dict[tuple[str,str], CrossCorrelation]
#   - relationship_type is read via get_relationship_type(cell)
#   - rho is read via cell.spearman_lag0.value
#   - confidence is inferred from cell.spearman_lag0.applicability

@dataclass
class HeatmapPayload:
    """Everything the renderer needs in one object."""
    variables:          list[VariableSpec]
    cells:              dict[tuple[str, str], CrossCorrelation]
    title:              str
    subtitle:           Optional[str] = None
    n_observations_total: int = 0
    comparison_cells:   Optional[dict[tuple[str, str], CrossCorrelation]] = None
    comparison_title:   Optional[str] = None
    comparison_n:       int = 0


def build_heatmap_payload(
    variables: list[VariableSpec],
    cells: dict[tuple[str, str], CrossCorrelation],
    title: str,
    n_observations_total: int,
    subtitle: Optional[str] = None,
) -> HeatmapPayload:
    return HeatmapPayload(
        variables=variables,
        cells=cells,
        title=title,
        subtitle=subtitle,
        n_observations_total=n_observations_total,
    )


def render_heatmap_png(payload: HeatmapPayload, output_path: Path) -> Path:
    """Render the heatmap payload to a PNG file."""
    import matplotlib.pyplot as plt

    if payload.comparison_cells is not None:
        return _render_side_by_side(payload, output_path)

    fig, ax = plt.subplots(figsize=(10, 9))
    _render_single_heatmap(
        ax, payload.variables, payload.cells,
        payload.title, payload.subtitle, payload.n_observations_total,
    )
    plt.tight_layout()
    plt.savefig(output_path, dpi=140, bbox_inches="tight", facecolor="white")
    plt.close()
    return output_path


def _render_single_heatmap(ax, variables, cells, title, subtitle, n_total):
    """Render one heatmap panel (unchanged display logic from prior version)."""
    import matplotlib.pyplot as plt
    from matplotlib.colors import LinearSegmentedColormap
    from matplotlib.patches import Patch

    cmap = LinearSegmentedColormap.from_list(
        "rwb",
        [(0.0, "#2f5d9a"), (0.5, "#f5f1ea"), (1.0, "#a83d3d")],
    )

    n = len(variables)
    col_to_idx = {v.column: i for i, v in enumerate(variables)}
    grid = np.full((n, n), np.nan)
    is_structural           = np.zeros((n, n), dtype=bool)
    is_derived_via_structural = np.zeros((n, n), dtype=bool)
    is_insufficient         = np.zeros((n, n), dtype=bool)
    is_lod_heavy            = np.zeros((n, n), dtype=bool)

    for (a, b), cell in cells.items():
        if a not in col_to_idx or b not in col_to_idx:
            continue
        i, j = col_to_idx[a], col_to_idx[b]
        rho = cell.spearman_lag0.value
        applic = cell.spearman_lag0.applicability
        rel = get_relationship_type(cell)

        if rho is not None and applic != APPLIC_INSUFFICIENT:
            grid[i, j] = rho
            grid[j, i] = rho
        elif applic == APPLIC_INSUFFICIENT:
            is_insufficient[i, j] = is_insufficient[j, i] = True

        if rel == "structural":
            is_structural[i, j] = is_structural[j, i] = True
        if rel == "derived_via_structural":
            is_derived_via_structural[i, j] = is_derived_via_structural[j, i] = True
        if applic == APPLIC_LIMITED:
            is_lod_heavy[i, j] = is_lod_heavy[j, i] = True

    for i in range(n):
        grid[i, i] = 1.0

    im = ax.imshow(grid, cmap=cmap, vmin=-1, vmax=1, aspect="equal", interpolation="nearest")

    for i in range(n):
        for j in range(n):
            if i == j:
                ax.add_patch(plt.Rectangle(
                    (j - 0.5, i - 0.5), 1, 1,
                    facecolor="#e8e8e8", edgecolor="none", zorder=2,
                ))
            elif is_insufficient[i, j]:
                ax.add_patch(plt.Rectangle(
                    (j - 0.5, i - 0.5), 1, 1,
                    facecolor="#d8d8d8", edgecolor="none",
                    hatch=r"\\", alpha=0.7, zorder=2,
                ))
            elif is_structural[i, j]:
                ax.add_patch(plt.Rectangle(
                    (j - 0.5, i - 0.5), 1, 1,
                    facecolor="none", edgecolor="#666",
                    hatch="xxx", linewidth=0.4, zorder=2,
                ))
            elif is_derived_via_structural[i, j]:
                ax.add_patch(plt.Rectangle(
                    (j - 0.5, i - 0.5), 1, 1,
                    facecolor="none", edgecolor="#888",
                    hatch="///", linewidth=0.4, zorder=2,
                ))

    for i in range(n):
        for j in range(n):
            if i >= j:
                continue
            if np.isnan(grid[i, j]):
                continue
            rho = grid[i, j]
            if abs(rho) >= 0.6:
                color = "white" if abs(rho) > 0.7 else "#222"
                ax.text(j, i, f"{rho:.2f}", ha="center", va="center",
                        fontsize=7, color=color, zorder=3,
                        fontweight="bold" if abs(rho) >= 0.8 else "normal")

    short_labels = [v.name for v in variables]
    ax.set_xticks(range(n))
    ax.set_yticks(range(n))
    ax.set_xticklabels(short_labels, rotation=45, ha="right", fontsize=8)
    ax.set_yticklabels(short_labels, fontsize=8)

    for i, v in enumerate(variables):
        if v.kind == "derived":
            ax.get_xticklabels()[i].set_color("#666")
            ax.get_xticklabels()[i].set_style("italic")
            ax.get_yticklabels()[i].set_color("#666")
            ax.get_yticklabels()[i].set_style("italic")

    prev_group = None
    for i, v in enumerate(variables):
        if prev_group is not None and v.group != prev_group:
            ax.axvline(i - 0.5, color="white", linewidth=1.2, zorder=4)
            ax.axhline(i - 0.5, color="white", linewidth=1.2, zorder=4)
        prev_group = v.group

    ax.set_title(title, fontsize=12, pad=28, loc="left", fontweight="bold", y=1.05)
    footer_parts = []
    if subtitle:
        footer_parts.append(subtitle)
    footer_parts.append(f"n = {n_total} observations")
    ax.text(0, 1.02, "   |   ".join(footer_parts),
            fontsize=8, color="#555", ha="left", va="bottom", transform=ax.transAxes)

    cbar = ax.figure.colorbar(im, ax=ax, fraction=0.04, pad=0.04, shrink=0.7)
    cbar.set_label("Spearman ρ", fontsize=9)
    cbar.ax.tick_params(labelsize=8)

    legend_handles = [
        Patch(facecolor="#d8d8d8", hatch=r"\\", label="Insufficient (n<10)"),
        Patch(facecolor="white", edgecolor="#666", hatch="xxx", label="Structural"),
        Patch(facecolor="white", edgecolor="#888", hatch="///", label="Derived via structural"),
        Patch(facecolor="#e8e8e8", label="Diagonal (self)"),
    ]
    ax.legend(handles=legend_handles, loc="lower left",
              bbox_to_anchor=(0, -0.30), ncol=4, fontsize=7, frameon=False)


def _render_side_by_side(payload: HeatmapPayload, output_path: Path) -> Path:
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(20, 9))
    _render_single_heatmap(axes[0], payload.variables, payload.cells,
                           payload.title, payload.subtitle, payload.n_observations_total)
    _render_single_heatmap(axes[1], payload.variables, payload.comparison_cells,
                           payload.comparison_title, None, payload.comparison_n)
    plt.tight_layout()
    plt.savefig(output_path, dpi=140, bbox_inches="tight", facecolor="white")
    plt.close()
    return output_path


def build_top_relationship_table(
    cells: dict[tuple[str, str], CrossCorrelation],
    variables: list[VariableSpec],
    min_abs_rho: float = 0.6,
    exclude_structural: bool = True,
    exclude_derived_via_structural: bool = True,
    max_rows: int = 25,
) -> pd.DataFrame:
    """
    Ranked table of strongest non-structural relationships.

    Output columns:
      var_a_long, var_b_long, rho, n_pair, confidence,
      relationship_type, plain_english, caveat
    """
    long_by_col = {v.column: v.long_name for v in variables}

    rows = []
    for (a, b), cell in cells.items():
        rho = cell.spearman_lag0.value
        if rho is None:
            continue
        if abs(rho) < min_abs_rho:
            continue

        rel = get_relationship_type(cell)
        if exclude_structural and rel == "structural":
            continue
        if exclude_derived_via_structural and rel == "derived_via_structural":
            continue

        n_pair     = cell.spearman_lag0.n or 0
        confidence = _confidence_label(n_pair)
        applic     = cell.spearman_lag0.applicability
        note       = cell.spearman_lag0.note or ""

        plain = _plain_english_observation(
            long_by_col.get(a, a), long_by_col.get(b, b), rho, rel
        )

        caveats = []
        if confidence in ("Limited", "Insufficient"):
            caveats.append(f"{confidence} confidence (n={n_pair})")
        if applic == APPLIC_LIMITED:
            if "lod_heavy" in note:
                caveats.append(note)
            elif "censored" in note:
                caveats.append(note)
        if rel == "expected":
            caveats.append("expected coupling; not a novel finding")
        p_str = ""
        if "p=" in note:
            p_match = [p for p in note.split(";") if "p=" in p]
            if p_match:
                p_str = p_match[0].strip()
                try:
                    p_val = float(p_str.replace("p=", ""))
                    if p_val > 0.05:
                        caveats.append(f"{p_str} (not statistically significant)")
                except ValueError:
                    pass

        rows.append({
            "var_a_long":        long_by_col.get(a, a),
            "var_b_long":        long_by_col.get(b, b),
            "rho":               round(rho, 3),
            "n_pair":            n_pair,
            "confidence":        confidence,
            "relationship_type": rel,
            "plain_english":     plain,
            "caveat":            "; ".join(caveats),
        })

    df_table = pd.DataFrame(rows)
    if df_table.empty:
        return df_table

    df_table["abs_rho"] = df_table["rho"].abs()
    return (
        df_table
        .sort_values("abs_rho", ascending=False)
        .drop(columns=["abs_rho"])
        .head(max_rows)
        .reset_index(drop=True)
    )


def compare_full_vs_subset_heatmaps(
    df: pd.DataFrame,
    subset_mask: pd.Series,
    variables: list[VariableSpec],
    min_pair_n: int = 10,
    lod_substitution_counts: Optional[dict[str, int]] = None,
) -> tuple[
    dict[tuple[str, str], CrossCorrelation],
    dict[tuple[str, str], CrossCorrelation],
]:
    """
    Compute full-dataset and conditional-subset correlation matrices.

    Returns (full_cells, subset_cells). Each is a classified matrix of
    CrossCorrelation objects ready for render_heatmap_png().
    """
    full_cells = classify_relationships(
        compute_spearman_matrix(df, variables, min_pair_n, lod_substitution_counts)
    )
    subset_cells = classify_relationships(
        compute_spearman_matrix(df[subset_mask], variables, min_pair_n, lod_substitution_counts)
    )
    return full_cells, subset_cells
