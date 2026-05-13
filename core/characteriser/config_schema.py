"""
core/characteriser/config_schema.py

WaterPoint Platform — Characterisation Configuration Schema
===========================================================

Dataclasses that define how the characteriser engine is configured for a
given module (wastewater, drinking water, purified recycled water, biosolids).

Schema version: 2.0
-------------------
Extends stub-1.0 with fields required by:
  - AquaPoint §0.0.4  alias resolution   (aliases on ParameterSpec)
  - AquaPoint §0.1    LoD substitution   (lod_aware, lod_substitution_value)
  - AquaPoint §6.3    correlation engine (group, kind, excluded_from_heatmap,
                                          RelationshipSpec, heatmap thresholds)
  - AquaPoint §3.4    INT-05 identity    (IdentityRule, noise_tolerance_pct)

All additions carry defaults so that existing wastewater config objects
continue to work without modification. This is a backward-compatible change.

Consumed by
-----------
  integrity_checks.py       — ParameterSpec (physical_range, typical_range,
                               parameter_type, noise_tolerance_pct)
                              CharacterisationConfig.identity_rules
  alias_map.py              — ParameterSpec.aliases
  correlation_heatmap.py    — ParameterSpec (group, kind, lod_aware,
                               excluded_from_heatmap)
                              CharacterisationConfig (relationships,
                               heatmap_min_rho, heatmap_min_n,
                               lod_substitution_value)
  classifier_hbt.py         — CharacterisationConfig.parameters (physical
                               bounds, parameter groups)
  trend_indicator.py        — ParameterSpec.parameter_type
  regime_shift.py           — ParameterSpec.parameter_type
  orchestrator.py           — CharacterisationConfig (module, version)

Stability note
--------------
This schema is consumed by every module in core/characteriser/ and by all
four platform modules. Treat changes as breaking until proven otherwise.
Pin the schema_version string when changing field semantics; add new fields
with defaults rather than removing or renaming existing ones.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple


SCHEMA_VERSION = "2.0"


# ── Parameter groups ──────────────────────────────────────────────────────────
#
# Used by the correlation heatmap to visually cluster parameters and to
# apply group-level structural relationship rules (§6.3.2).
# Extend this set if a new module needs a new grouping.

GROUP_PHYSICAL    = "physical"      # turbidity, TSS, temperature, flow
GROUP_ORGANIC     = "organic"       # DOC, TOC, UV254, UVT, colour, SUVA
GROUP_MINERAL     = "mineral"       # alkalinity, hardness, EC, TDS, chloride, SO4
GROUP_NUTRIENTS   = "nutrients"     # ammonia, nitrate, nitrite, TP, TDP
GROUP_BIOLOGICAL  = "biological"    # chlorophyll-a, algal cells, biovolume, cyanobacteria
GROUP_MICROBIAL   = "microbial"     # E. coli, coliforms
GROUP_CHEMICAL    = "chemical"      # bromide, PFAS, arsenic, taste/odour compounds
GROUP_METALS      = "metals"        # iron, manganese
GROUP_OTHER       = "other"         # catch-all; rainfall, pH, DO

# Parameter kinds (§6.3.2 — governs relationship classification)
KIND_OBSERVED = "observed"     # measured directly from the sample
KIND_DERIVED  = "derived"      # mathematically computed from another parameter
                                # (e.g. UVT = 10^(-UV254); SUVA = UV254/DOC)
                                # derived pairs trigger derived_via_structural
                                # classification in the correlation engine


# ── Relationship types (§6.3.3) ───────────────────────────────────────────────
#
# Used in RelationshipSpec.expected_type and CrossCorrelation observation.pattern.

REL_STRUCTURAL           = "structural"            # mathematically guaranteed (e.g. TKN ≤ TN)
REL_EXPECTED             = "expected"              # physically/chemically expected but not guaranteed
REL_OBSERVED             = "observed"              # empirical only; no mechanistic expectation
REL_DERIVED_VIA_STRUCT   = "derived_via_structural" # inherited from a structural chain A→B→C


# ── New types (genuinely additive — not present in report.py) ─────────────────

@dataclass
class RelationshipSpec:
    """
    A known or expected relationship between two parameters.

    Populates CharacterisationConfig.relationships. The correlation engine
    uses this registry to classify computed CrossCorrelation objects and to
    apply transitive propagation (§6.3.3 Amendment B).

    For derived_via_structural entries, `intermediate_parameter` names the
    parameter that forms the structural link (e.g. UV254 in the
    DOC → UV254 → UVT chain).

    Engineering note: entries here are claims about the *expected* relationship
    given the underlying chemistry or mathematics. The correlation engine checks
    whether the observed ρ is consistent — it doesn't override an observed
    weak correlation just because the spec says "expected".
    """
    parameter_a:            str
    parameter_b:            str
    expected_type:          str             # one of REL_* constants above
    rationale:              str             # engineering basis (one sentence)
    intermediate_parameter: Optional[str] = None   # for derived_via_structural only


@dataclass
class IdentityRule:
    """
    A stoichiometric or mass-balance identity that must hold within
    analytical noise tolerance (INT-05, §3.4).

    The rule asserts: numerator_param ≤ denominator_param on every row,
    within noise_tolerance_pct of denominator_param.

    Examples:
        IdentityRule("TKN_mg_L", "Total_N_mg_L", "TKN ≤ Total N",
                     "TKN is a component of TN")
        IdentityRule("DOC_mg_L", "TOC_mg_L", "DOC ≤ TOC",
                     "Dissolved fraction cannot exceed total")
        IdentityRule("Cyanobacteria_cells_mL", "Total_Algal_Cells_mL",
                     "Cyano ≤ Total algal cells",
                     "Cyanobacteria is a subset of total algal count")

    noise_tolerance_pct: if None, falls back to the denominator parameter's
    ParameterSpec.noise_tolerance_pct, then to 5.0% if that's also None.
    """
    numerator_param:        str
    denominator_param:      str
    label:                  str             # short label for flag messages
    description:            str             # plain-language rationale
    noise_tolerance_pct:    Optional[float] = None   # overrides ParameterSpec default


# ── ParameterSpec ─────────────────────────────────────────────────────────────

@dataclass
class ParameterSpec:
    """
    Specification for a single parameter.

    v2.0 additions (all with defaults — backward compatible with stub-1.0):
      aliases               — raw alias strings for alias_map.py (§0.0.4)
      group                 — heatmap grouping (§6.3.2)
      kind                  — observed vs derived (§6.3.2)
      lod_aware             — participates in LoD substitution (§0.1)
      excluded_from_heatmap — omit from correlation matrix
      noise_tolerance_pct   — analytical noise for INT-05; None → config default

    Fields consumed by integrity_checks.py (unchanged from stub-1.0):
      name, display_name, unit, physical_range, typical_range, parameter_type

    Fields consumed by alias_map.py (new):
      name (canonical target), aliases (raw variants)

    Fields consumed by correlation engine (new):
      group, kind, lod_aware, excluded_from_heatmap

    Fields consumed by INT-05 (new):
      noise_tolerance_pct
    """

    # ── Core identity (stub-1.0, unchanged) ───────────────────────────────────

    name:            str                            # canonical column name in the dataframe
    display_name:    str                            # human-friendly label for messages/UI
    unit:            str                            # canonical unit string (mg/L, NTU, etc.)

    # ── Integrity bounds (stub-1.0, unchanged) ────────────────────────────────

    physical_range:  Tuple[float, float]            # (low, high) — physically impossible outside
                                                    # INT-01: rows outside → Critical flag
    typical_range:   Optional[Tuple[float, float]] = None
                                                    # (low, high) — unusual but possible
                                                    # INT-01b: rows outside → Warning/Info
                                                    # None → skip typical-range check
    parameter_type:  str = "other"
                                                    # "flow" | "concentration" | "load" |
                                                    # "temperature" | "ph" | "rainfall" |
                                                    # "conductivity" | "other"
                                                    # INT-02: only flow/concentration/load
                                                    # are checked for implausible zeros

    # ── v2.0 additions ────────────────────────────────────────────────────────

    aliases: List[str] = field(default_factory=list)
                                                    # Raw alias strings for alias_map.py.
                                                    # alias_map normalises both these and the
                                                    # incoming column headers before matching,
                                                    # so case/separator variants don't need to
                                                    # be listed exhaustively — just the
                                                    # "natural" forms encountered in the field.
                                                    # The canonical `name` is implicitly an
                                                    # alias of itself; no need to repeat it.
                                                    # Example for Turbidity_NTU:
                                                    #   ["Turbidity", "Turb_NTU", "TURBIDITY",
                                                    #    "Turbidity (NTU)", "turb"]

    group: str = GROUP_OTHER
                                                    # Heatmap grouping (§6.3.2).
                                                    # Parameters in the same group share a
                                                    # visual block on the heatmap; intra-group
                                                    # correlations are expected rather than
                                                    # surprising.
                                                    # Use GROUP_* constants above.

    kind: str = KIND_OBSERVED
                                                    # KIND_OBSERVED: measured directly
                                                    # KIND_DERIVED: computed from another
                                                    # parameter (e.g. UVT from UV254; SUVA
                                                    # from UV254/DOC).
                                                    # Derived parameters trigger
                                                    # derived_via_structural classification
                                                    # in the correlation engine when their
                                                    # source parameter is involved.

    lod_aware: bool = False
                                                    # True if values can be below the
                                                    # analytical detection limit (LoD).
                                                    # When True:
                                                    #   - values reported as 0 or as
                                                    #     "<LoD" strings are substituted
                                                    #     per config.lod_substitution_value
                                                    #   - censored_fraction_pct is computed
                                                    #     and surfaced on CrossCorrelation
                                                    #   - cells with censored_fraction ≥ 50%
                                                    #     are flagged lod_heavy
                                                    # Typical lod_aware=True parameters:
                                                    # Geosmin, MIB, Microcystin, PFAS, Arsenic,
                                                    # E_coli (when reported as <1).

    excluded_from_heatmap: bool = False
                                                    # True → parameter is computed but NOT
                                                    # included in the correlation matrix.
                                                    # Use for arithmetic load parameters
                                                    # (e.g. daily_load_kg = flow × conc)
                                                    # that would otherwise dominate the
                                                    # heatmap with trivially high correlations
                                                    # to their component parameters.

    noise_tolerance_pct: Optional[float] = None
                                                    # Analytical noise tolerance for INT-05
                                                    # identity checks involving this parameter
                                                    # as the denominator.
                                                    # None → fall back to
                                                    # CharacterisationConfig.identity_noise_tolerance_pct_default
                                                    # (which itself defaults to 5.0).
                                                    # Override for high-precision instruments
                                                    # (e.g. online UV254 sensors: 2.0%)
                                                    # or for parameters with known high
                                                    # analytical variability (e.g. 10.0%).


# ── CharacterisationConfig ────────────────────────────────────────────────────

@dataclass
class CharacterisationConfig:
    """
    Top-level configuration for one characteriser module.

    v2.0 additions:
      relationships                       — §6.3.3 known parameter pairs
      identity_rules                      — §3.4 INT-05 stoichiometric identities
      lod_substitution_value              — §0.1 fraction of LoD to substitute
      heatmap_min_rho                     — §6.3.2 reporting threshold
      heatmap_min_n                       — §6.3.2 minimum pair count for a cell
      identity_noise_tolerance_pct_default — §3.4 fallback for IdentityRule

    Fields consumed by integrity_checks.py (unchanged):
      parameters, module

    Schema version tracked on the instance so downstream consumers can
    detect mismatches at runtime.
    """

    # ── Core (stub-1.0, unchanged) ────────────────────────────────────────────

    parameters: List[ParameterSpec] = field(default_factory=list)
                                                    # One entry per monitored parameter.
                                                    # Order doesn't matter; engine builds
                                                    # a name-keyed dict at startup.

    module: str = ""
                                                    # "wastewater" | "drinking_water" |
                                                    # "purified_recycled" | "biosolids"

    version: str = SCHEMA_VERSION
                                                    # Config version string (not schema version).
                                                    # Flows into CharacterisationReport.config_version.

    # ── v2.0 additions ────────────────────────────────────────────────────────

    relationships: List[RelationshipSpec] = field(default_factory=list)
                                                    # Known or expected parameter pairs.
                                                    # The correlation engine classifies each
                                                    # computed CrossCorrelation against this
                                                    # registry. Pairs not in the registry are
                                                    # classified as REL_OBSERVED.
                                                    # Transitive propagation (§6.3.3 Amendment B)
                                                    # is applied after direct classification:
                                                    # if A↔B is structural and B↔C is structural
                                                    # or expected, A↔C is classified as
                                                    # derived_via_structural with B as
                                                    # intermediate_parameter.

    identity_rules: List[IdentityRule] = field(default_factory=list)
                                                    # INT-05 stoichiometric checks.
                                                    # Each rule asserts numerator ≤ denominator
                                                    # within noise_tolerance_pct on every row.
                                                    # Violations produce Critical/Warning flags
                                                    # on CharacterisationReport.flags with
                                                    # affected_row_indices populated.

    lod_substitution_value: float = 0.5
                                                    # §0.1 LoD substitution factor.
                                                    # Values at or below zero that belong to
                                                    # lod_aware parameters are substituted
                                                    # as: substituted = lod × factor.
                                                    # Default 0.5 (half-LoD convention, per
                                                    # USEPA/NHMRC guidance for censored data).
                                                    # Set to 0.0 to substitute as zero.
                                                    # Set to 1.0 to substitute as LoD itself.

    heatmap_min_rho: float = 0.6
                                                    # §6.3.2 minimum absolute Spearman ρ
                                                    # for a pair to appear in the
                                                    # top-relationships table.
                                                    # All pairs are computed; this threshold
                                                    # controls what's surfaced in the report.
                                                    # Structural and derived_via_structural
                                                    # pairs are always surfaced regardless
                                                    # of ρ magnitude.

    heatmap_min_n: int = 10
                                                    # §6.3.2 minimum number of overlapping
                                                    # non-censored row pairs for a correlation
                                                    # cell to be computed.
                                                    # Cells below this threshold are rendered
                                                    # as grey (insufficient data) on the
                                                    # heatmap and carry
                                                    # applicability=APPLIC_INSUFFICIENT.

    identity_noise_tolerance_pct_default: float = 5.0
                                                    # §3.4 fallback noise tolerance for
                                                    # INT-05 checks when neither the
                                                    # IdentityRule nor the denominator
                                                    # ParameterSpec specifies one.
                                                    # 5% covers typical analytical
                                                    # variability for grab samples;
                                                    # reduce for online instrumentation.

    # ── Convenience accessors ─────────────────────────────────────────────────

    def parameter_by_name(self, name: str) -> Optional[ParameterSpec]:
        """Look up a ParameterSpec by canonical name."""
        for p in self.parameters:
            if p.name == name:
                return p
        return None

    def heatmap_parameters(self) -> List[ParameterSpec]:
        """Parameters that should appear in the correlation matrix."""
        return [p for p in self.parameters if not p.excluded_from_heatmap]

    def lod_aware_parameters(self) -> List[str]:
        """Canonical names of parameters subject to LoD substitution."""
        return [p.name for p in self.parameters if p.lod_aware]

    def parameters_by_group(self) -> dict:
        """Parameters grouped by heatmap group. Returns Dict[group, List[ParameterSpec]]."""
        out: dict = {}
        for p in self.parameters:
            out.setdefault(p.group, []).append(p)
        return out

    def relationships_for(self, parameter_a: str, parameter_b: str
                          ) -> Optional[RelationshipSpec]:
        """Look up the RelationshipSpec for a pair (order-insensitive)."""
        for r in self.relationships:
            if ({r.parameter_a, r.parameter_b} == {parameter_a, parameter_b}):
                return r
        return None
