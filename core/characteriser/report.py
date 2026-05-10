"""
core/characteriser/report.py

WaterPoint Platform — Characterisation Report Schema
=====================================================

The output contract of the platform-level data characteriser. Built once,
consumed by all four modules (wastewater, drinking water, purified recycled,
biosolids) and by the synthesiser/test harness.

Design principles
-----------------
- Mirrors the InputValidationReport pattern (severity-tagged flags, convenience
  properties, fails gracefully).
- Module-agnostic. Holds statistical results, not domain interpretation.
  Domain interpretation lives in the per-module config + the validation layer
  that consumes this report.
- Every statistic is wrapped in a small object that carries its own
  applicability and confidence — a diurnal mean from 8 weekly samples
  has no business being treated the same as one from 18 months of hourly data.
- Pure data. No Streamlit, no plotting, no I/O. Serialisable.

Stability
---------
This schema is the contract between the characteriser engine and every
downstream consumer (validation layer, decision layers, UI panels,
synthesiser, integration tests). Changes here ripple everywhere — version
the schema and treat changes as breaking until proven otherwise.

Schema version: 1.0
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple


# ── Schema versioning ─────────────────────────────────────────────────────────

SCHEMA_VERSION = "1.0"


# ── Confidence and applicability tags ─────────────────────────────────────────
#
# Every derived statistic carries one of these. They're how the report tells
# downstream consumers whether the number is trustworthy enough to use.

APPLIC_OK              = "OK"               # Enough data; statistic is meaningful
APPLIC_LIMITED         = "Limited"          # Computable but uncertain; report with caveat
APPLIC_INSUFFICIENT    = "Insufficient"     # Not enough data; do not use
APPLIC_NOT_APPLICABLE  = "Not applicable"   # Data type doesn't support this statistic


CONF_HIGH       = "High"
CONF_ACCEPTABLE = "Acceptable"
CONF_LOW        = "Low"
CONF_VERY_LOW   = "Very Low"


# Severity for characterisation-level flags (parallels validation layer)
SEV_CRITICAL = "Critical"
SEV_WARNING  = "Warning"
SEV_INFO     = "Info"


# ── Building blocks ───────────────────────────────────────────────────────────

@dataclass
class Statistic:
    """
    A single derived statistic with its applicability tag.

    Use this anywhere you'd otherwise return a bare float — every number in
    the report carries its own evidence quality.

    The `basis` field is critical for design-relevant aggregations: two
    engineers can produce radically different PWWF values from the same
    data depending on averaging interval, percentile basis, and event
    separation. The engine records its choices explicitly in `basis` so
    downstream consumers (and design assurance) can verify like-for-like
    comparisons.

    Examples:
        mean        = Statistic(value=220.0, applicability="OK", n=540)
        diurnal_pf  = Statistic(value=None, applicability="Insufficient",
                                n=12, note="Need ≥48 hourly samples")
        pwwf        = Statistic(value=41.95, unit="MLD", applicability="OK",
                                n=70176,
                                basis="P99.5 of hourly-mean flow on wet-weather days")
    """
    value:         Optional[float]   = None
    unit:          str               = ""
    applicability: str               = APPLIC_OK
    n:             Optional[int]     = None     # sample count behind the statistic
    ci_low:        Optional[float]   = None     # 95% CI lower (where applicable)
    ci_high:       Optional[float]   = None     # 95% CI upper
    note:          str               = ""       # short caveat or context
    basis:         str               = ""       # exact computation basis (governance)


@dataclass
class CategoricalStatistic:
    """
    Like Statistic but for categorical results (best-fit distribution name,
    detected regime, dominant pattern, etc).
    """
    value:         Optional[str]     = None
    applicability: str               = APPLIC_OK
    confidence:    str               = CONF_ACCEPTABLE
    alternatives:  List[Tuple[str, float]] = field(default_factory=list)
                                        # ranked alternatives with score (e.g. AIC weight)
    n:             Optional[int]     = None
    note:          str               = ""


@dataclass
class CharacterisationFlag:
    """
    A finding worth surfacing to the user. Mirrors ValidationFlag from the
    input validation layer so the UI can render both with the same widget.
    """
    rule_id:       str               # CH-XX namespace (separate from IV-XX)
    severity:      str               # Critical | Warning | Info
    parameter:     str               # parameter name (e.g. "bod_mg_l") or "" for dataset-level
    pattern:       str               # one-line label (e.g. "Bimodal distribution")
    message:       str               # plain-language description with numbers
    implication:   str = ""          # what this means for design / decisions
    recommended_action: str = ""     # what the user should do next

    # Row provenance — INT-class rules should populate this so downstream
    # consumers (like the design envelope's integrity-aware secondary medians)
    # can filter or exclude affected rows. Empty list means "not tracked";
    # not the same as "no rows affected".
    affected_row_indices: List[int] = field(default_factory=list)


# ── Provenance and interpretation framing ─────────────────────────────────────
#
# Engine outputs separate observation (the number) from interpretation
# (what it might mean). Every cross-correlation, mass-balance check, and
# aggregation carries an Observation rather than a free-text "this means X"
# string. Interpretation is multiple-candidate by default — the engine never
# picks one mechanism without confirmatory evidence.

@dataclass
class CandidateExplanation:
    """One possible explanation for an observed pattern, with discriminator.

    The `weight` field carries a normalised relative likelihood (0–1) across
    a candidate list. It's NOT a Bayesian posterior — it's a coarse evidence-
    based ranking the engine can apply when context (e.g. detected synthetic-
    data signatures) shifts the prior. Defaults to None when the engine
    can't justify a ranking; consumers should treat None as 'all candidates
    equally plausible'.
    """
    explanation:        str           # e.g. "Soluble trade waste influence"
    plausibility:       str           # "Likely" | "Possible" | "Unlikely"
    discriminating_test: str          # what would confirm or rule this out
    weight:             Optional[float] = None    # 0–1 relative likelihood


@dataclass
class Observation:
    """
    A measured-then-framed result: the number, its evidence quality, the
    candidate explanations, and the tests that would discriminate between
    them.

    Replaces free-text interpretation strings throughout the engine.
    """
    pattern:            str           # short label e.g. "BOD-TSS decoupled"
    finding:            str           # the measurement in words
    evidence_strength:  str           # "Strong" | "Moderate" | "Weak"
    candidates:         List[CandidateExplanation] = field(default_factory=list)
    note:               str = ""      # additional context



@dataclass
class DistributionFit:
    """
    Best-fit parametric distribution and how well it fits.
    """
    family:         CategoricalStatistic = field(default_factory=CategoricalStatistic)
                                            # "lognormal" | "gamma" | "normal" | "mixture-2" | ...
    parameters:     Dict[str, float]      = field(default_factory=dict)
                                            # e.g. {"mu": 5.4, "sigma": 0.6}
    goodness_of_fit: Statistic            = field(default_factory=Statistic)
                                            # KS or AD statistic; ci low/high carry the p-value
    is_bimodal:     bool                  = False
    bimodal_separation: Optional[float]   = None    # std. distance between modes


@dataclass
class TemporalStructure:
    """
    Time-domain patterns extracted from a parameter's series.
    """
    # Diurnal (hour-of-day)
    diurnal_present:        Statistic = field(default_factory=Statistic)
                                # value in [0,1] = strength; applicability captures sample-rate adequacy
    diurnal_peak_factor:    Statistic = field(default_factory=Statistic)  # peak-hour / day-mean
    diurnal_peak_hour:      Statistic = field(default_factory=Statistic)  # 0..23

    # Weekly
    weekday_weekend_shift:  Statistic = field(default_factory=Statistic)
                                # (weekday_mean − weekend_mean) / weekday_mean

    # Seasonal
    seasonality_present:    Statistic = field(default_factory=Statistic)
    seasonal_amplitude:     Statistic = field(default_factory=Statistic)
                                # (annual P95 − annual P5) / annual mean
    seasonal_peak_month:    Statistic = field(default_factory=Statistic)  # 1..12

    # Trend
    trend_slope:            Statistic = field(default_factory=Statistic)  # units / day
    trend_significant:      bool      = False
    trend_pct_per_year:     Statistic = field(default_factory=Statistic)

    # Autocorrelation
    autocorr_lag1:          Statistic = field(default_factory=Statistic)
    autocorr_lag7:          Statistic = field(default_factory=Statistic)
    autocorr_lag365:        Statistic = field(default_factory=Statistic)


@dataclass
class VariabilityProfile:
    """
    Variability and excursion behaviour beyond simple CV.
    """
    cv_overall:             Statistic = field(default_factory=Statistic)
    cv_dry_weather:         Statistic = field(default_factory=Statistic)  # if rainfall available
    cv_wet_weather:         Statistic = field(default_factory=Statistic)
    heteroscedastic:        bool      = False     # variance scales with mean
    heteroscedastic_slope:  Optional[float] = None

    # Excursion stats: how often and how badly the parameter exceeds high percentiles
    p95_exceedance_freq:    Statistic = field(default_factory=Statistic)  # fraction of days
    p99_exceedance_freq:    Statistic = field(default_factory=Statistic)
    typical_excursion_duration: Statistic = field(default_factory=Statistic)  # days


@dataclass
class EventDetection:
    """
    Discrete events found in the time series — changepoints, outliers, regime
    shifts. These often matter more than aggregate statistics.
    """
    n_outliers:             int = 0
    outlier_dates:          List[str] = field(default_factory=list)   # ISO dates
    n_changepoints:         int = 0
    changepoint_dates:      List[str] = field(default_factory=list)
    regime_shift_detected:  bool = False
    regime_shift_summary:   str = ""        # plain-language description
    last_event_date:        Optional[str] = None
    days_since_last_event:  Optional[int] = None


@dataclass
class ParameterCharacterisation:
    """
    Complete characterisation for a single parameter (BOD, turbidity, VS, etc).
    Aggregated by the engine; consumed by the validation layer and the UI.
    """
    name:           str                            # canonical parameter name
    unit:           str                            # canonical unit
    n_samples:      int                            = 0
    sample_period:  Optional[Tuple[str, str]]      = None    # (first_date, last_date) ISO
    sample_freq:    str                            = "unknown"
                                # "hourly" | "daily" | "weekly" | "irregular" | "unknown"

    # Basic descriptive (kept here for completeness — UI shouldn't have to fish elsewhere)
    mean:           Statistic = field(default_factory=Statistic)
    median:         Statistic = field(default_factory=Statistic)
    std:            Statistic = field(default_factory=Statistic)
    min:            Statistic = field(default_factory=Statistic)
    max:            Statistic = field(default_factory=Statistic)
    p05:            Statistic = field(default_factory=Statistic)
    p25:            Statistic = field(default_factory=Statistic)
    p75:            Statistic = field(default_factory=Statistic)
    p95:            Statistic = field(default_factory=Statistic)
    p99:            Statistic = field(default_factory=Statistic)

    # Higher-order shape
    skewness:       Statistic = field(default_factory=Statistic)
    kurtosis:       Statistic = field(default_factory=Statistic)
    distribution:   DistributionFit  = field(default_factory=DistributionFit)

    # Time-domain
    temporal:       TemporalStructure = field(default_factory=TemporalStructure)

    # Variability
    variability:    VariabilityProfile = field(default_factory=VariabilityProfile)

    # Events
    events:         EventDetection = field(default_factory=EventDetection)

    # Per-parameter quality
    completeness:   Statistic = field(default_factory=Statistic)  # fraction non-missing
    parameter_confidence: str = CONF_ACCEPTABLE   # rolled-up over above

    # Per-parameter flags raised by the engine
    flags:          List[CharacterisationFlag] = field(default_factory=list)


# ── Cross-parameter relationships ─────────────────────────────────────────────

@dataclass
class CrossCorrelation:
    """
    Correlation between two parameters at lag 0 and at user-specified lags.
    The config dictates which pairs to compute and which lags matter.

    The `interpretation` field is deprecated — kept for backward compatibility.
    New consumers should read `observation` (Observation), which lists multiple
    candidate explanations with discriminating tests rather than a single
    mechanistic claim.
    """
    parameter_a:    str
    parameter_b:    str
    pearson_lag0:   Statistic = field(default_factory=Statistic)
    spearman_lag0:  Statistic = field(default_factory=Statistic)   # robust to outliers
    best_lag_days:  Optional[int] = None
    best_lag_corr:  Statistic = field(default_factory=Statistic)
    interpretation: str = ""    # DEPRECATED — kept for back-compat
    observation:    Optional[Observation] = None    # PREFERRED


# ── Event-centric analysis (Phase 2) ──────────────────────────────────────────
#
# An EVENT is a contiguous run of days satisfying some condition — a storm,
# an industrial discharge, a septic episode. Aggregate conditional analysis
# (Phase 1) lumps all matching days together; event-centric analysis groups
# them into discrete episodes, each with start/peak/duration and a baseline
# comparison.
#
# The event class is deliberately generic — the same dataclass represents
# storm events, industrial events, low-temp/low-carbon stress events, etc.
# What differs across event types is the DETECTION RULE, not the structure.

@dataclass
class EventBaseline:
    """
    Baseline statistics computed from a window adjacent to the event.

    Used to compare what changed during the event vs the immediately-
    preceding period (more meaningful than comparing to the global median,
    which folds in seasonal and trend effects).
    """
    window_days:        int                     # how many days the baseline window covers
    window_start:       Optional[str] = None    # ISO date
    window_end:         Optional[str] = None
    n_samples:          int = 0
    parameter_medians:  Dict[str, float] = field(default_factory=dict)
    parameter_p10:      Dict[str, float] = field(default_factory=dict)
    parameter_p90:      Dict[str, float] = field(default_factory=dict)


@dataclass
class EventParameterShift:
    """How one parameter behaved during an event vs its baseline."""
    parameter:           str
    event_median:        Optional[float] = None
    baseline_median:     Optional[float] = None
    shift_pct:           Optional[float] = None    # vs baseline
    shift_significance:  str = ""                  # Strong | Moderate | None
    event_peak:          Optional[float] = None    # max within event
    event_peak_date:     Optional[str] = None      # ISO date of peak
    note:                str = ""


@dataclass
class CandidateMechanism:
    """
    One candidate mechanism for an observed event.

    Same framing pattern as CandidateExplanation (used for cross-correlations):
    the engine lists possibilities with supporting evidence and discriminating
    tests, never claims a single mechanism. The engineer reads the candidates
    and decides — or designs further data collection to discriminate.
    """
    mechanism:           str         # short description e.g. "Storm-driven runoff entrainment"
    supporting_evidence: str = ""    # what in the event data is consistent with this mechanism
    discriminating_test: str = ""    # what additional data would distinguish from other candidates


@dataclass
class Event:
    """
    A single discrete episode in the dataset.

    Event types are detected by named rules (StormEventRule, SepticEventRule,
    IndustrialEventRule, etc.); each rule produces Event objects with the
    same structure.
    """
    event_type:          str                     # human label e.g. "First-flush" | "High sulphide"
    event_id:            str = ""                # unique identifier within the analysis run
    start_date:          str = ""
    end_date:            str = ""
    duration_days:       int = 0
    peak_date:           str = ""
    detection_rule:      str = ""                # text description of the rule that fired
    n_samples:           int = 0                 # rows in the event window
    confidence:          str = ""                # Strong | Acceptable | Limited | Insufficient
    confidence_rationale: str = ""

    parameter_shifts:    List[EventParameterShift] = field(default_factory=list)
    baseline:            Optional[EventBaseline] = None

    # Severity scoring — "did the parameters actually move enough to matter,
    # or did the event just clip the threshold?" Computed from the parameter
    # shifts above; see event_analysis._compute_severity for definition.
    severity_score:      float = 0.0
    severity_label:      str = ""                # "Marginal" | "Moderate" | "Strong" | "Severe"
    severity_rationale:  str = ""

    # One-line plain-language summary of what's distinctive about this event.
    # Produced by the rendering layer — what to read first.
    summary_line:        str = ""

    # Candidate mechanisms framed as possibilities, not claims (per Observation pattern)
    candidate_mechanisms: List[CandidateMechanism] = field(default_factory=list)

    # Sequence context (Phase 2C)
    antecedent_dry_buildup: Optional[float] = None    # accumulated dry-day proxy at event start
    antecedent_context:  str = ""                       # human description of what preceded
    notes:               List[str] = field(default_factory=list)


@dataclass
class EventAnalysis:
    """
    Top-level result of an event-centric analysis pass.

    May contain multiple events of different types, ordered by start date.
    """
    detection_summary:   str = ""                # what rules ran, what they found
    n_events:            int = 0
    events:              List[Event] = field(default_factory=list)
    rules_evaluated:     List[str] = field(default_factory=list)
    notes:               List[str] = field(default_factory=list)


# ── Coincidence analysis ──────────────────────────────────────────────────────
#
# Conditional-evidence reporting: what happens to other parameters when
# parameter X is in some condition (top 5%, wet weather, winter, etc.)?
#
# This is the foundation for over-design avoidance. Standard practice often
# stacks worst cases (peak flow × peak load × peak ammonia × low temp) even
# though those don't co-occur — designing for a P99⁴ event that happens
# approximately never. The conditional-joint distribution from real data
# is the defensible alternative.
#
# This is NOT a generator. It only describes events that ACTUALLY OCCURRED
# in the historical record. The user can verify by checking the listed dates.

@dataclass
class ConditionalParameterStat:
    """One parameter's behaviour within the conditional subset, vs overall."""
    parameter:           str
    n:                   int
    overall_median:      Optional[float] = None
    conditional_median:  Optional[float] = None
    conditional_p05:     Optional[float] = None
    conditional_p95:     Optional[float] = None
    conditional_mean:    Optional[float] = None
    conditional_std:     Optional[float] = None
    shift_direction:     str = ""           # "increased" | "decreased" | "stable"
    shift_magnitude_pct: Optional[float] = None
    significance:        str = ""           # "Strong" | "Moderate" | "Weak" | "None"


@dataclass
class CoincidenceAnalysis:
    """
    Result of one conditional-extraction query.

    The user asks: "when condition X holds, what happens to everything else?"
    The engine returns what actually happened on the matching days.

    `confidence` follows the same scale used elsewhere in the engine:
      Insufficient (<10 matches): refuse to characterise
      Limited      (10-29):       report with caveat
      Acceptable   (30-99):       report with low confidence
      Strong       (100+):        report with confidence
    """
    condition_label:     str               # human description e.g. "Flow above P95"
    condition_spec:      Dict[str, str] = field(default_factory=dict)
    n_matching:          int = 0
    n_total:             int = 0
    matching_pct:        float = 0.0
    confidence:          str = ""
    confidence_rationale: str = ""
    matching_dates:      List[str] = field(default_factory=list)
    conditional_stats:   List[ConditionalParameterStat] = field(default_factory=list)
    integrity_flags_in_subset: List["CharacterisationFlag"] = field(default_factory=list)
    notes:               List[str] = field(default_factory=list)


# ── Design-relevant aggregations ──────────────────────────────────────────────
#
# These are the numbers the engine actually wants downstream — peak loads,
# governing percentiles, etc. The config decides which ones to compute for
# a given module.

@dataclass
class DesignAggregation:
    """
    A single design-relevant aggregation (e.g. ADWF, peak wet, max-month load).
    """
    name:           str                  # canonical name from config
    description:    str                  # plain-language description
    parameter:      str                  # which input parameter this is computed from
    value:          Statistic = field(default_factory=Statistic)
    method:         str = ""             # how it was computed (e.g. "P95 of dry-weather days")


# ── Design envelope (Phase 5: evidence-grounded design memo) ──────────────────
#
# A DesignEnvelope is the layer-5 output: a six-section evidence memo for one
# engineer-named design concern, drawing from integrity (1), characterisation
# (2), correlation/coincidence (3), and event-extraction (4) layers.
#
# The envelope is INFLUENT-SIDE evidence only. It does NOT make process-
# consequence claims (no "this stresses clarifiers first") and it does NOT
# prioritise which envelope should dominate design — that is engineering
# judgement and belongs to the engineer reading the memo.

@dataclass
class EnvelopeFraming:
    """Section 1: what's being characterised, on what dataset, why."""
    label:                  str = ""             # user-provided
    dataset_filename:       str = ""
    period_start:           str = ""
    period_end:             str = ""
    n_total_observations:   int = 0
    n_complete_years:       Optional[float] = None
    what_characterised:     str = ""             # one sentence
    condition_machine:      Dict[str, str] = field(default_factory=dict)
    condition_plain:        str = ""             # plain-English restatement
    focus_parameters:       List[str] = field(default_factory=list)
    why_framing:            str = ""             # 1-2 sentences

    # Set if condition fails to parse (envelope cannot be produced)
    parse_error:            Optional[str] = None


@dataclass
class IntegrityExclusionStat:
    """Secondary median computed with flagged rows excluded (Addition C)."""
    parameter:                          str
    conditional_median_excluded:        Optional[float] = None
    n_excluded:                         int = 0


@dataclass
class EnvelopePopulationSection:
    """Section 2: the conditional-aggregate envelope (population-level)."""
    aggregation_scope_note:     str = ""
    n_matching:                 int = 0
    n_total:                    int = 0
    matching_pct:               float = 0.0
    sample_confidence:          str = ""
    sample_rationale:           str = ""

    # Coverage statement
    conditioning_range_note:    str = ""
    period_coverage_note:       str = ""
    concentration_note:         str = ""         # any clustering of matches

    # Tables — using existing ConditionalParameterStat for individual entries
    concentration_stats:        List["ConditionalParameterStat"] = field(default_factory=list)
    load_stats:                 List["ConditionalParameterStat"] = field(default_factory=list)
    ratio_stats:                List["ConditionalParameterStat"] = field(default_factory=list)

    # Addition C: integrity-aware secondary medians (only populated when
    # integrity flags fall inside the matched subset)
    integrity_exclusions:       List[IntegrityExclusionStat] = field(default_factory=list)
    integrity_exclusion_active: bool = False

    # Addition B: ratio priority labels — parameter name → "diagnostic" | "informational"
    ratio_priority_map:         Dict[str, str] = field(default_factory=dict)
    ratio_priority_note:        str = ""         # what concern drove the priority

    # Chart references (filled by chart module)
    heatmap_path:               Optional[str] = None
    scatters_path:              Optional[str] = None
    scatters_pair_count:        int = 0           # how many |ρ| ≥ 0.6 pairs rendered


@dataclass
class EnvelopeEventSection:
    """Section 3: discrete events within the matched subset."""
    events:                     List["Event"] = field(default_factory=list)
    # Addition D: repeatability info per event (parallel list, same index)
    repeatability_notes:        Dict[str, str] = field(default_factory=dict)
                                # map event_id → repeatability string
    no_events_note:             str = ""         # populated if 0 events
    time_series_path:           Optional[str] = None


@dataclass
class EnvelopeOverDesignSection:
    """Section 4: naive stacking vs joint conditional."""
    framing:                    str = ""         # explanatory paragraph
    comparison:                 Optional["OverDesignComparison"] = None
    over_design_chart_path:     Optional[str] = None


@dataclass
class IntegritySubsetFlag:
    """One integrity flag affecting rows inside the matched subset."""
    rule_id:                str
    severity:               str
    parameter:              str
    n_rows_affected:        int = 0
    dates_affected:         List[str] = field(default_factory=list)  # capped at 20
    effect_on_envelope:     str = ""


@dataclass
class EnvelopeIntegritySection:
    """Section 5: integrity flags filtered to dates inside matched subset."""
    is_clean:               bool = True
    flags_affecting_subset: List[IntegritySubsetFlag] = field(default_factory=list)
    clean_message:          str = ""


@dataclass
class EnvelopeLimitsSection:
    """Section 6: caveats and limits."""
    period_statement:       str = ""
    under_represented:      List[str] = field(default_factory=list)
    does_not_address:       List[str] = field(default_factory=list)
    recommended_steps:      List[str] = field(default_factory=list)


@dataclass
class DesignEnvelope:
    """
    Top-level: all six sections of one design envelope.

    Renderable as markdown via the envelope renderer; serializable for
    UI consumption. Chart paths reference PNG files written alongside
    the markdown by the chart module.
    """
    framing:        EnvelopeFraming         = field(default_factory=EnvelopeFraming)
    population:     EnvelopePopulationSection = field(default_factory=EnvelopePopulationSection)
    events:         EnvelopeEventSection    = field(default_factory=EnvelopeEventSection)
    over_design:    EnvelopeOverDesignSection = field(default_factory=EnvelopeOverDesignSection)
    integrity:      EnvelopeIntegritySection = field(default_factory=EnvelopeIntegritySection)
    limits:         EnvelopeLimitsSection   = field(default_factory=EnvelopeLimitsSection)

    # Working-directory path where charts were written
    charts_directory: Optional[str] = None
    generation_timestamp: str = ""


# ── Top-level dataset and report ──────────────────────────────────────────────

@dataclass
class DatasetMetadata:
    """
    What was uploaded and what the engine made of it. Captured once so every
    consumer sees the same provenance.
    """
    filename:           str = ""
    upload_timestamp:   str = ""        # ISO datetime
    n_rows:             int = 0
    n_columns:          int = 0
    columns_detected:   List[str] = field(default_factory=list)
    columns_mapped:     Dict[str, str] = field(default_factory=dict)
                            # {raw_column_name: canonical_parameter_name}
    columns_unmapped:   List[str] = field(default_factory=list)
    date_column:        Optional[str] = None
    date_range:         Optional[Tuple[str, str]] = None
    sample_freq_detected: str = "unknown"
    units_detected:     Dict[str, str] = field(default_factory=dict)
    units_assumed:      Dict[str, str] = field(default_factory=dict)
                            # parameters where the engine had to assume a unit


@dataclass
class CharacterisationReport:
    """
    Top-level output of the characteriser.

    Lifecycle:
      1. User uploads dataset → engine parses → DatasetMetadata populated
      2. Engine iterates parameters → ParameterCharacterisation per parameter
      3. Engine iterates pairs from config → CrossCorrelation per pair
      4. Engine computes module-specific design aggregations
      5. Engine rolls up dataset_confidence
      6. Report flows to validation layer (which may demote its own confidence
         based on what's here), then to UI, then to engine.

    Consumers:
      - Validation layer: reads dataset_confidence, parameter flags, cross-
        correlations to demote its own confidence ladder.
      - Decision layers: read design_aggregations as governing inputs.
      - UI: renders parameter panels, distribution plots, event timelines.
      - Synthesiser: round-trip — generates datasets matching a given report.
      - Integration tests: assertions against expected report contents.
    """
    schema_version:     str = SCHEMA_VERSION
    module:             str = ""        # "wastewater" | "drinking_water" | "purified" | "biosolids"
    config_version:     str = ""        # version of the per-module config used

    # Provenance
    metadata:           DatasetMetadata = field(default_factory=DatasetMetadata)

    # Per-parameter
    parameters:         Dict[str, ParameterCharacterisation] = field(default_factory=dict)

    # Cross-parameter
    cross_correlations: List[CrossCorrelation] = field(default_factory=list)

    # Module-specific design-relevant aggregations
    design_aggregations: List[DesignAggregation] = field(default_factory=list)

    # Flow-specific analysis (populated only when a flow parameter is present).
    # Importing the actual class lazily to avoid a hard cross-module import here;
    # the engine populates this slot at runtime.
    flow_analysis:      Optional[object] = None

    # Roll-up confidence over the whole dataset
    dataset_confidence: str = CONF_ACCEPTABLE
    dataset_confidence_rationale: str = ""

    # Dataset-level flags (e.g. "Sample period <90 days", "Last sample 14 months ago")
    flags:              List[CharacterisationFlag] = field(default_factory=list)

    # Engine status
    safe_for_validation: bool = True    # if False, validation layer should not consume
    engine_errors:       List[str] = field(default_factory=list)
                                # populated when an internal step failed gracefully

    # ── Convenience accessors ────────────────────────────────────────────────

    @property
    def critical_flags(self) -> List[CharacterisationFlag]:
        out = [f for f in self.flags if f.severity == SEV_CRITICAL]
        for p in self.parameters.values():
            out.extend(f for f in p.flags if f.severity == SEV_CRITICAL)
        return out

    @property
    def warning_flags(self) -> List[CharacterisationFlag]:
        out = [f for f in self.flags if f.severity == SEV_WARNING]
        for p in self.parameters.values():
            out.extend(f for f in p.flags if f.severity == SEV_WARNING)
        return out

    @property
    def info_flags(self) -> List[CharacterisationFlag]:
        out = [f for f in self.flags if f.severity == SEV_INFO]
        for p in self.parameters.values():
            out.extend(f for f in p.flags if f.severity == SEV_INFO)
        return out

    @property
    def parameter_names(self) -> List[str]:
        return list(self.parameters.keys())

    def parameter(self, name: str) -> Optional[ParameterCharacterisation]:
        """Convenience for `report.parameter("bod_mg_l")` from validation layer."""
        return self.parameters.get(name)

    def design_value(self, aggregation_name: str) -> Optional[Statistic]:
        """Look up a named design aggregation's value, e.g. design_value('adwf')."""
        for agg in self.design_aggregations:
            if agg.name == aggregation_name:
                return agg.value
        return None
