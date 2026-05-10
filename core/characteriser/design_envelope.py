"""
core/characteriser/design_envelope.py

Layer-5 orchestrator: builds a DesignEnvelope from a condition spec and
the existing layer-1 through layer-4 outputs.

Architecture
------------
The orchestrator does not do new analysis. It assembles evidence from
existing modules:

    Section 1 (Framing):     user input + dataset metadata
    Section 2 (Population):  coincidence.analyse_coincidence
                             + heatmap correlation analysis
                             + integrity-aware secondary medians (new)
                             + ratio priority lookup (new)
    Section 3 (Events):      filtered events from EventAnalysis
                             + repeatability annotations (new)
    Section 4 (Over-design): coincidence.compare_to_naive_stacking
    Section 5 (Integrity):   filtered flags from CharacterisationReport
    Section 6 (Limits):      mix of dataset metadata + fixed-list scope statements

Charts are produced by envelope_charts.py and referenced by path.

Design boundaries
-----------------
This module produces INFLUENT-SIDE EVIDENCE ONLY. It does not:
  - claim process consequences ("this stresses clarifiers first")
  - prioritise which envelope should dominate design
  - extrapolate to higher return periods
  - generate synthetic scenarios

The engineer reading the memo makes those calls; the engine surfaces
what the data shows.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd

from .report import (
    CharacterisationReport, CharacterisationFlag,
    CoincidenceAnalysis, ConditionalParameterStat,
    Event, EventAnalysis,
    DesignEnvelope, EnvelopeFraming, EnvelopePopulationSection,
    EnvelopeEventSection, EnvelopeOverDesignSection,
    EnvelopeIntegritySection, EnvelopeLimitsSection,
    IntegrityExclusionStat, IntegritySubsetFlag,
)
from .coincidence import analyse_coincidence, compare_to_naive_stacking, _build_mask


# ── Concern-to-ratio priority lookup (Addition B) ────────────────────────────
#
# Each concern maps to a list of (ratio_name, priority) tuples.
# priority is "diagnostic" or "informational".
#
# This is hardcoded rather than externalised; six concerns is too few to
# justify a config file, and the priority logic is part of the engine's
# domain knowledge.

_CONCERN_RATIO_PRIORITIES: Dict[str, Dict[str, str]] = {
    "peak_hydraulic": {
        # No ratio dominates for peak hydraulic — loads vs concentrations is the story
        "nh4_to_tkn":  "informational",
        "cod_to_bod":  "informational",
        "bod_to_tkn":  "informational",
        "alk_to_tkn":  "informational",
        "tp_to_cod":   "informational",
    },
    "bnr_nitrification_stress": {
        "alk_to_tkn":  "diagnostic",
        "bod_to_tkn":  "diagnostic",
        "nh4_to_tkn":  "diagnostic",
        "cod_to_bod":  "informational",
        "tp_to_cod":   "informational",
    },
    "p_removal_stress": {
        "tp_to_cod":   "diagnostic",
        "alk_to_tkn":  "informational",
        "nh4_to_tkn":  "informational",
        "cod_to_bod":  "informational",
        "bod_to_tkn":  "informational",
    },
    "septicity": {
        # rbcod-to-scod and scod-to-cod aren't pre-computed in most datasets;
        # if present they'll be picked up; if not, fall through to others
        "rbcod_to_scod":  "diagnostic",
        "scod_to_cod":    "diagnostic",
        "nh4_to_tkn":     "informational",
        "cod_to_bod":     "informational",
    },
    "biodegradability": {
        "cod_to_bod":  "diagnostic",
        "rbcod_to_cod": "diagnostic",
        "bod_to_tkn":  "informational",
        "alk_to_tkn":  "informational",
    },
    "first_flush_solids": {
        "vss_to_tss":  "diagnostic",
        "nh4_to_tkn":  "informational",
        "cod_to_bod":  "informational",
    },
}

# Plain-English label for concerns (for rendering)
_CONCERN_LABELS: Dict[str, str] = {
    "peak_hydraulic":           "Peak hydraulic conditions",
    "bnr_nitrification_stress": "BNR / nitrification stress",
    "p_removal_stress":         "P-removal stress",
    "septicity":                "Septicity exposure",
    "biodegradability":         "Biodegradability / carbon limitation",
    "first_flush_solids":       "First-flush solids mobilisation",
}


def _ratio_priority(concern: Optional[str], ratio_name: str) -> str:
    """
    Look up the priority of a ratio for a given concern.
    Returns "diagnostic" | "informational" | "" (no priority assigned).
    """
    if concern is None or concern not in _CONCERN_RATIO_PRIORITIES:
        return ""
    return _CONCERN_RATIO_PRIORITIES[concern].get(ratio_name, "informational")


# ── Default focus parameters ─────────────────────────────────────────────────

DEFAULT_FOCUS_CONCENTRATIONS = [
    "flow_mld",
    "bod_mg_l", "cod_mg_l", "tss_mg_l",
    "tkn_mg_l", "nh4_mg_l", "tp_mg_l",
    "temperature_c",
]
DEFAULT_FOCUS_LOADS = [
    "bod_load_kg_d", "cod_load_kg_d", "tss_load_kg_d",
    "tkn_load_kg_d", "nh4_load_kg_d", "tp_load_kg_d",
]
DEFAULT_FOCUS_RATIOS = [
    "nh4_to_tkn", "cod_to_bod", "bod_to_tkn", "alk_to_tkn", "tp_to_cod",
]


def _default_focus_parameters(df: pd.DataFrame) -> Tuple[List[str], List[str], List[str]]:
    """Select default focus parameters present in the dataset."""
    concentrations = [c for c in DEFAULT_FOCUS_CONCENTRATIONS if c in df.columns]
    loads          = [c for c in DEFAULT_FOCUS_LOADS if c in df.columns]
    ratios         = [c for c in DEFAULT_FOCUS_RATIOS if c in df.columns]
    return concentrations, loads, ratios


def _classify_parameter(name: str) -> str:
    """Classify a column name into 'concentration' | 'load' | 'ratio' | 'other'."""
    if name.endswith("_load_kg_d") or "_load" in name:
        return "load"
    if "_to_" in name or name in {"nh4_to_tkn", "cod_to_bod", "bod_to_tkn",
                                    "alk_to_tkn", "tp_to_cod"}:
        return "ratio"
    if name.endswith("_mg_l") or name in {"flow_mld", "rainfall_mm",
                                            "temperature_c", "ph", "ec_us_cm"}:
        return "concentration"
    return "other"


# ── Section 1 — Framing ──────────────────────────────────────────────────────

def _build_framing(df: pd.DataFrame,
                     label: str,
                     dataset_filename: str,
                     condition_spec: Dict,
                     focus_parameters: List[str],
                     concern: Optional[str]) -> EnvelopeFraming:
    """Build Section 1 — framing block."""
    framing = EnvelopeFraming(
        label=label,
        dataset_filename=dataset_filename,
        focus_parameters=focus_parameters,
    )

    if "_date" in df.columns and len(df) > 0:
        framing.period_start = df["_date"].min().strftime("%Y-%m-%d")
        framing.period_end = df["_date"].max().strftime("%Y-%m-%d")
        span_days = (df["_date"].max() - df["_date"].min()).days
        framing.n_complete_years = round(span_days / 365.25, 2)
    framing.n_total_observations = len(df)

    # Machine condition: stringify all values for serialization
    framing.condition_machine = {k: str(v) for k, v in condition_spec.items()}

    # Plain-English condition: simple translation
    parts = []
    for col, expr in condition_spec.items():
        if isinstance(expr, str):
            parts.append(f"{col} {expr}")
        elif isinstance(expr, bool):
            parts.append(f"{col} = {expr}")
        else:
            parts.append(f"{col} {expr}")
    framing.condition_plain = " AND ".join(parts)

    if concern and concern in _CONCERN_LABELS:
        framing.what_characterised = (
            f"The data-supported envelope for {_CONCERN_LABELS[concern].lower()} "
            "on this catchment, drawing from observed historical conditions."
        )
        framing.why_framing = (
            f"This envelope is intended to support design decisions where "
            f"{_CONCERN_LABELS[concern].lower()} is a binding consideration. "
            "It surfaces the joint conditional behaviour of focus parameters under "
            "the named condition, plus any discrete events of relevant type within "
            "the matching subset."
        )
    else:
        framing.what_characterised = (
            "The data-supported envelope for the condition specified, "
            "drawing from observed historical conditions."
        )
        framing.why_framing = (
            "This envelope surfaces the joint conditional behaviour of focus "
            "parameters under the named condition, plus any discrete events of "
            "relevant type within the matching subset."
        )

    return framing


# ── Section 2 — Population envelope ──────────────────────────────────────────

def _split_stats_by_kind(stats: List[ConditionalParameterStat]
                            ) -> Tuple[List[ConditionalParameterStat],
                                          List[ConditionalParameterStat],
                                          List[ConditionalParameterStat]]:
    """Split a list of ConditionalParameterStat into (concentrations, loads, ratios)."""
    conc, load, ratio = [], [], []
    for s in stats:
        kind = _classify_parameter(s.parameter)
        if kind == "load":
            load.append(s)
        elif kind == "ratio":
            ratio.append(s)
        else:
            conc.append(s)
    return conc, load, ratio


def _sort_ratios_by_priority(ratios: List[ConditionalParameterStat],
                                concern: Optional[str]
                                ) -> Tuple[List[ConditionalParameterStat], Dict[str, str]]:
    """
    Sort ratios diagnostic-first, informational-second, then alphabetically.
    Returns (sorted_list, priority_map).
    """
    if concern is None or concern not in _CONCERN_RATIO_PRIORITIES:
        # No priority — return alphabetical
        return (sorted(ratios, key=lambda r: r.parameter),
                {r.parameter: "" for r in ratios})

    priority_map = {r.parameter: _ratio_priority(concern, r.parameter) for r in ratios}
    # Diagnostic first (sorted alpha within), then informational, then unknown
    def sort_key(r: ConditionalParameterStat):
        p = priority_map[r.parameter]
        order = {"diagnostic": 0, "informational": 1, "": 2}.get(p, 2)
        return (order, r.parameter)
    return (sorted(ratios, key=sort_key), priority_map)


def _compute_integrity_exclusions(df: pd.DataFrame,
                                     subset_mask: pd.Series,
                                     report: CharacterisationReport,
                                     focus_parameters: List[str]
                                     ) -> List[IntegrityExclusionStat]:
    """
    Addition C: compute conditional median with integrity-flagged rows excluded.

    For each focus parameter, find rows inside the matched subset that are
    flagged by INT-class rules affecting that parameter. Compute the conditional
    median with those rows excluded. Returns only parameters where the
    exclusion changes the count (otherwise the exclusion is a no-op).

    Handles INT-05 compound parameter names (e.g. "bod_mg_l vs cod_mg_l") by
    splitting on " vs " and attaching the row indices to BOTH parameters.
    """
    if not report.flags:
        return []

    # Build a per-parameter set of flagged row indices
    flagged_idx_by_param: Dict[str, set] = {}
    for flag in report.flags:
        if not flag.rule_id.startswith("INT-"):
            continue
        if not flag.affected_row_indices:
            continue
        # Handle INT-05 compound parameter names
        if " vs " in flag.parameter:
            parts = [p.strip() for p in flag.parameter.split(" vs ")]
        else:
            parts = [flag.parameter]
        for param in parts:
            if param not in focus_parameters:
                continue
            flagged_idx_by_param.setdefault(param, set()).update(flag.affected_row_indices)

    if not flagged_idx_by_param:
        return []

    subset_indices = set(df.index[subset_mask].tolist())

    results = []
    for param, flagged_set in flagged_idx_by_param.items():
        if param not in df.columns:
            continue
        flagged_in_subset = flagged_set & subset_indices
        n_excluded = len(flagged_in_subset)
        if n_excluded == 0:
            continue
        keep_mask = subset_mask.copy()
        for idx in flagged_in_subset:
            keep_mask.loc[idx] = False
        clean_values = df.loc[keep_mask, param].dropna()
        if len(clean_values) < 5:
            continue
        results.append(IntegrityExclusionStat(
            parameter=param,
            conditional_median_excluded=float(clean_values.median()),
            n_excluded=n_excluded,
        ))
    return results


def _build_population_section(df: pd.DataFrame,
                                 condition_spec: Dict,
                                 focus_parameters: List[str],
                                 concern: Optional[str],
                                 report: Optional[CharacterisationReport]
                                 ) -> Tuple[EnvelopePopulationSection,
                                              Optional[pd.Series],
                                              Optional[CoincidenceAnalysis]]:
    """
    Build Section 2. Returns (section, matched_mask, coincidence_analysis).
    The mask and analysis are returned for downstream sections.
    """
    section = EnvelopePopulationSection()

    # Aggregation-scope disclaimer (Addition A) — always rendered
    section.aggregation_scope_note = (
        "The numbers in this section aggregate all observations matching the condition. "
        "Where the condition spans multiple distinct regime types (e.g., high flow may "
        "include both dilution-only events and first-flush events), the conditional "
        "median can blend regimes that should be considered separately. Section 3 breaks "
        "the matching subset into discrete events; read sections 2 and 3 together rather "
        "than in isolation."
    )

    # Use coincidence.analyse_coincidence to get the conditional stats
    coincidence_label = _CONCERN_LABELS.get(concern, "the condition specified")
    analysis = analyse_coincidence(df, condition_spec,
                                       condition_label=coincidence_label,
                                       parameters_to_report=focus_parameters)

    section.n_matching = analysis.n_matching
    section.n_total = analysis.n_total
    section.matching_pct = analysis.matching_pct
    section.sample_confidence = analysis.confidence
    section.sample_rationale = analysis.confidence_rationale

    # If Insufficient, return early — downstream sections will note this
    if analysis.confidence == "Insufficient":
        return (section, None, analysis)

    # Compute the matched mask (we need it for downstream sections)
    mask, _ = _build_mask(df, condition_spec)
    if mask is None:
        return (section, None, analysis)

    # Coverage statement
    for cond_col in condition_spec.keys():
        if cond_col in df.columns and pd.api.types.is_numeric_dtype(df[cond_col]):
            subset_vals = df.loc[mask, cond_col].dropna()
            if len(subset_vals) > 0:
                section.conditioning_range_note = (
                    f"{cond_col} ranged from {subset_vals.min():.2f} to "
                    f"{subset_vals.max():.2f} (median {subset_vals.median():.2f}) "
                    f"in the matched subset.")
                break

    if "_date" in df.columns:
        subset_dates = df.loc[mask, "_date"]
        if len(subset_dates) > 0:
            earliest = subset_dates.min().strftime("%Y-%m-%d")
            latest = subset_dates.max().strftime("%Y-%m-%d")
            by_year = subset_dates.dt.year.value_counts().sort_index()
            year_breakdown = ", ".join(f"{y} contributes {n}" for y, n in by_year.items())
            section.period_coverage_note = (
                f"Earliest matching date {earliest}; latest {latest}. "
                f"Matching observations by year: {year_breakdown}.")

            # Detect clustering
            if len(by_year) == 1:
                section.concentration_note = (
                    f"All matching observations fall in calendar year "
                    f"{by_year.index[0]}; the envelope reflects that year's "
                    "conditions only.")
            elif by_year.max() / len(subset_dates) > 0.7:
                dom_year = by_year.idxmax()
                section.concentration_note = (
                    f"Matching observations cluster heavily in {dom_year} "
                    f"({by_year.max()} of {len(subset_dates)} matches); conditions "
                    "in other years may not be well represented.")

    # Split stats into concentrations, loads, ratios
    conc, load, ratio = _split_stats_by_kind(analysis.conditional_stats)
    section.concentration_stats = conc
    section.load_stats = load

    # Apply ratio prioritisation (Addition B)
    sorted_ratios, priority_map = _sort_ratios_by_priority(ratio, concern)
    section.ratio_stats = sorted_ratios
    section.ratio_priority_map = priority_map
    if concern and concern in _CONCERN_LABELS:
        section.ratio_priority_note = (
            f"Ratios ordered by diagnostic priority for {_CONCERN_LABELS[concern]}. "
            "Diagnostic-primary ratios appear first; informational-secondary ratios follow.")
    else:
        section.ratio_priority_note = (
            "No design-concern priority applied — ratios listed alphabetically. "
            "Priority should be assigned by the engineer based on the design concern.")

    # Addition C: compute integrity-aware secondary medians
    if report is not None:
        exclusions = _compute_integrity_exclusions(df, mask, report, focus_parameters)
        section.integrity_exclusions = exclusions
        section.integrity_exclusion_active = len(exclusions) > 0

    return (section, mask, analysis)


# ── Section 3 — Events ──────────────────────────────────────────────────────

def _compute_repeatability(event: Event, all_events: List[Event]) -> str:
    """
    Addition D: build a repeatability string for one event.

    Counts events of the same type across the full record and the distinct
    calendar years they span.
    """
    same_type = [e for e in all_events if e.event_type == event.event_type]
    n_same = len(same_type)
    if n_same <= 1:
        return "Singular — only event of this type observed in the record."
    years = set()
    for e in same_type:
        if e.start_date:
            try:
                years.add(int(e.start_date[:4]))
            except (ValueError, IndexError):
                pass
    n_years = len(years)
    if n_years == 1:
        return f"{n_same} events of this type observed, all in calendar year {next(iter(years))}."
    return f"{n_same} events of this type observed across {n_years} distinct calendar years."


def _filter_events_to_subset(events: List[Event],
                                subset_mask: Optional[pd.Series],
                                df: pd.DataFrame,
                                event_types_relevant: Optional[List[str]] = None
                                ) -> List[Event]:
    """
    Filter events to those whose date range intersects the actual matching
    days in the subset (not just the broad date range covered).

    Strict interpretation: an event is relevant to the envelope only if at
    least one row inside the event's date window is also a matching row.

    If event_types_relevant is provided, also filter by type.
    """
    if subset_mask is None or not events:
        return []
    if "_date" not in df.columns:
        return events

    # Build a set of matching dates as strings
    matching_dates = set(df.loc[subset_mask, "_date"].dt.strftime("%Y-%m-%d"))
    if not matching_dates:
        return []

    filtered = []
    for ev in events:
        # Type filter
        if event_types_relevant and ev.event_type not in event_types_relevant:
            continue
        # Does the event's date window include at least one matching day?
        # Generate the date range of the event and intersect
        try:
            event_dates = pd.date_range(ev.start_date, ev.end_date, freq="D")
            event_date_strs = set(d.strftime("%Y-%m-%d") for d in event_dates)
        except (ValueError, TypeError):
            continue
        if event_date_strs & matching_dates:
            filtered.append(ev)
    return filtered


def _build_events_section(df: pd.DataFrame,
                            subset_mask: Optional[pd.Series],
                            event_analysis: Optional[EventAnalysis],
                            concern: Optional[str]
                            ) -> EnvelopeEventSection:
    """Build Section 3 — events within the matched subset."""
    section = EnvelopeEventSection()

    if event_analysis is None or not event_analysis.events:
        section.no_events_note = (
            "No event analysis was provided to this envelope, or no events "
            "were detected in the record. The aggregate envelope in Section 2 "
            "is the available evidence."
        )
        return section

    # Event-type relevance mapping per concern (informs filtering)
    concern_event_types = {
        "peak_hydraulic":           None,  # all event types are relevant
        "bnr_nitrification_stress": ["Low-carbon nitrification stress"],
        "p_removal_stress":         ["TP-rich coincident"],
        "septicity":                ["Septic episode"],
        "biodegradability":         None,  # no specific event type
        "first_flush_solids":       ["First-flush"],
    }
    relevant_types = concern_event_types.get(concern) if concern else None

    # Filter events by type-relevance AND subset-overlap
    section.events = _filter_events_to_subset(
        event_analysis.events,
        subset_mask if subset_mask is not None else pd.Series([True] * len(df)),
        df,
        event_types_relevant=relevant_types,
    )

    if not section.events:
        section.no_events_note = (
            "No events of relevant type detected within the matched subset. "
            "The aggregate envelope in Section 2 is the available evidence."
        )
        return section

    # Addition D: compute repeatability for each filtered event
    # (using the FULL event list, not just the filtered ones, for the count)
    for ev in section.events:
        section.repeatability_notes[ev.event_id] = _compute_repeatability(
            ev, event_analysis.events)

    return section


# ── Section 4 — Over-design ──────────────────────────────────────────────────

def _build_overdesign_section(df: pd.DataFrame,
                                  condition_spec: Dict,
                                  focus_parameters: List[str]
                                  ) -> EnvelopeOverDesignSection:
    """Build Section 4 — over-design comparison."""
    section = EnvelopeOverDesignSection()

    section.framing = (
        "The 'naive stacking' baseline takes P95 of every focus parameter "
        "independently. The 'observed joint' column takes the median of each "
        "parameter on days satisfying the condition. The difference is the "
        "over-design margin avoided by treating parameters as co-occurring "
        "rather than independently peaking.\n\n"
        "This comparison applies only to the condition specified in Section 1. "
        "Other conditions may show different over-design margins; this is not a "
        "global statement about the catchment."
    )

    # Identify the governing parameter — for a single-parameter condition, use it
    # For compound conditions, fall back to flow_mld if present
    governing_param = None
    if len(condition_spec) == 1:
        governing_param = next(iter(condition_spec.keys()))
    elif "flow_mld" in condition_spec:
        governing_param = "flow_mld"
    else:
        governing_param = next(iter(condition_spec.keys()))

    # Determine the governing percentile from the condition expression
    governing_pct = 95.0  # default
    cond_expr = condition_spec.get(governing_param)
    if isinstance(cond_expr, str):
        if "P" in cond_expr:
            try:
                pct_str = cond_expr.split("P", 1)[1].strip()
                governing_pct = float(pct_str)
            except (ValueError, IndexError):
                pass

    # Filter focus to numerical parameters only (skip ratios; over-design on a ratio
    # is conceptually different and would mislead)
    over_design_focus = [p for p in focus_parameters
                            if _classify_parameter(p) in ("concentration", "load")
                            and p in df.columns and p != governing_param]

    if not over_design_focus:
        return section

    comparison = compare_to_naive_stacking(
        df,
        governing_parameter=governing_param,
        governing_percentile=governing_pct,
        coincident_parameters=over_design_focus,
        design_concern=_CONCERN_LABELS.get(concern_label_from_param(governing_param, condition_spec), "design point"),
    )
    section.comparison = comparison
    return section


def concern_label_from_param(param: str, spec: Dict) -> str:
    """Fallback label generator if no concern is named."""
    return f"{param} {spec.get(param, '')}"


# ── Section 5 — Integrity ────────────────────────────────────────────────────

def _build_integrity_section(df: pd.DataFrame,
                                subset_mask: Optional[pd.Series],
                                report: Optional[CharacterisationReport]
                                ) -> EnvelopeIntegritySection:
    """Build Section 5 — integrity flags affecting matched subset."""
    section = EnvelopeIntegritySection()

    if report is None:
        section.is_clean = True
        section.clean_message = (
            "No characterisation report was provided to this envelope; integrity "
            "filtering against the matched subset was not performed. Numbers in "
            "this envelope are based on the input data as-loaded. "
            "Run `characterise(...)` first and pass the report through to get "
            "integrity-aware secondary medians and Section 5 evidence.")
        return section

    if not report.flags:
        section.is_clean = True
        section.clean_message = (
            "The characterisation report raised no flags. Numbers in this envelope "
            "are based on validated data.")
        return section

    if subset_mask is None:
        section.is_clean = True
        section.clean_message = (
            "Could not filter integrity flags to the matched subset (subset "
            "could not be constructed).")
        return section

    # Get the row indices of the subset
    subset_indices = set(df.index[subset_mask].tolist())

    # Filter INT-class flags whose affected row indices intersect the subset
    affecting = []
    for flag in report.flags:
        if not flag.rule_id.startswith("INT-"):
            continue
        if not flag.affected_row_indices:
            continue

        intersection = set(flag.affected_row_indices) & subset_indices
        if not intersection:
            continue

        # Build affected dates list from indices (cap at 20)
        dates_affected = []
        if "_date" in df.columns:
            sorted_intersection = sorted(intersection)[:20]
            for idx in sorted_intersection:
                try:
                    d = df.loc[idx, "_date"]
                    if pd.notna(d):
                        dates_affected.append(d.strftime("%Y-%m-%d"))
                except (KeyError, AttributeError):
                    continue

        affecting.append(IntegritySubsetFlag(
            rule_id=flag.rule_id,
            severity=flag.severity,
            parameter=flag.parameter,
            n_rows_affected=len(intersection),
            dates_affected=dates_affected,
            effect_on_envelope=_describe_flag_effect(flag),
        ))

    if not affecting:
        section.is_clean = True
        section.clean_message = (
            "No integrity flags affect rows in the matched subset. Numbers in "
            "Sections 2 through 4 are based on validated data.")
    else:
        section.is_clean = False
        section.flags_affecting_subset = affecting

    return section


def _describe_flag_effect(flag: CharacterisationFlag) -> str:
    """Map a flag to a brief description of its effect on the envelope."""
    rule = flag.rule_id
    if rule == "INT-01":
        return f"Inflates the upper tail of {flag.parameter} if not excluded; affects medians and P95."
    if rule == "INT-01b":
        return f"Affects the upper tail of {flag.parameter}; conditional median may be biased."
    if rule == "INT-02":
        return f"Excluded from medians as physically impossible (NaN on read)."
    if rule == "INT-03":
        return "Duplicate dates may double-count specific observations."
    if rule == "INT-04":
        return f"Scattered missing values in {flag.parameter}; reduces sample size."
    if rule == "INT-05":
        return f"Stoichiometric violation affecting {flag.parameter}; integrity of the value uncertain."
    return f"Affects {flag.parameter} in the matched subset."


# ── Section 6 — Limits ───────────────────────────────────────────────────────

def _build_limits_section(framing: EnvelopeFraming,
                             population: EnvelopePopulationSection,
                             events: EnvelopeEventSection,
                             df: pd.DataFrame) -> EnvelopeLimitsSection:
    """Build Section 6 — caveats and limits."""
    section = EnvelopeLimitsSection()

    # Period statement
    n_years = framing.n_complete_years or 0
    section.period_statement = (
        f"Period: {framing.period_start} to {framing.period_end}. "
        f"{n_years:.1f} complete years.\n"
        "The envelope reflects what occurred during this period only. Conditions "
        "not represented during this window are absent from the analysis."
    )

    # What's likely under-represented
    section.under_represented = [
        f"Events with return period > {n_years:.1f} years cannot be evidenced from "
        "this dataset; the record is too short.",
    ]
    # Add data-specific under-representations
    if "rainfall_mm" not in df.columns:
        section.under_represented.append(
            "Rainfall data is not present; wet-weather conditioning and first-flush "
            "analysis cannot be performed.")
    # Sub-daily flow check — heuristic: are there multiple observations per date?
    if "_date" in df.columns:
        dates_per_obs = df["_date"].dt.date.value_counts()
        if dates_per_obs.max() == 1:
            section.under_represented.append(
                "Sub-daily flow data is not present; within-event hydrograph shape "
                "(rising limb, peak lag, recession) cannot be characterised.")

    # Coverage concentration
    if population.concentration_note:
        section.under_represented.append(
            f"Matched-subset coverage caveat: {population.concentration_note}")

    # Insufficient confidence
    if population.sample_confidence == "Limited":
        section.under_represented.append(
            "The matched subset is small (Limited confidence); envelope numbers are "
            "indicative rather than design-grade.")
    elif population.sample_confidence == "Insufficient":
        section.under_represented.append(
            "The matched subset is too small to characterise; the envelope cannot be "
            "produced beyond Section 1.")

    # Fixed-list scope statements
    section.does_not_address = [
        "Plant-side process consequences (which subsystem binds first, how the plant "
        "responds). The envelope is influent-side evidence; mapping to process "
        "outcomes requires plant configuration data that is out of scope for this engine.",
        "Catchment trajectory (population growth, industrial change, climate shift). "
        "This is a backward-looking summary of observed conditions.",
        "Statistical extrapolation to higher percentiles. The envelope reports "
        "observations, not fitted distributions.",
        "Prioritisation across envelopes. The engine surfaces evidence per design concern; "
        "which envelope should dominate is engineering judgement and belongs to the "
        "engineer reading this memo.",
    ]

    # Recommended next steps
    steps = [
        "Cross-check event dates (Section 3) against operational logs, weather records, "
        "and trade-waste schedules to confirm or rule out specific mechanisms.",
        "Compare the envelope against any prior design assumptions; the over-design "
        "margin (Section 4) may justify reconsidering capacity assumptions.",
    ]
    if events.events:
        n_limited = sum(1 for e in events.events if e.confidence == "Limited")
        if n_limited > 0:
            steps.append(
                f"{n_limited} event(s) of Limited confidence appear in Section 3. "
                "Their underlying days should be reviewed individually before treating "
                "them as design-grade.")
    if not population.integrity_exclusion_active and population.sample_confidence != "Insufficient":
        steps.append(
            "Integrity flags affecting the matched subset (Section 5) should be reviewed "
            "for their impact on each derived design number.")

    # Conditional steps
    if "_date" in df.columns:
        dates_per_obs = df["_date"].dt.date.value_counts()
        if dates_per_obs.max() == 1:
            steps.append(
                "Sub-daily flow data, if available from SCADA, would enable within-event "
                "hydrograph analysis (rising limb, peak lag, recession behaviour).")

    section.recommended_steps = steps
    return section


# ── Public API ───────────────────────────────────────────────────────────────

def build_design_envelope(df: pd.DataFrame,
                              condition_spec: Dict[str, Union[str, bool, int, float]],
                              label: str,
                              focus_parameters: Optional[List[str]] = None,
                              concern: Optional[str] = None,
                              report: Optional[CharacterisationReport] = None,
                              event_analysis: Optional[EventAnalysis] = None,
                              dataset_filename: str = ""
                              ) -> DesignEnvelope:
    """
    Top-level entry point. Build a complete DesignEnvelope.

    Parameters
    ----------
    df : DataFrame
        Engine-cleaned dataframe (output of loader.load_dataset).
    condition_spec : dict
        Condition specification, in coincidence.py format (e.g.,
        {"flow_mld": ">P95"}).
    label : str
        Free-text label for the envelope (e.g., "Peak hydraulic for clarifier sizing").
    focus_parameters : list of str, optional
        Parameters to include in the envelope. Defaults to standard wastewater
        focus list filtered to what's present in df.
    concern : str, optional
        Pre-built concern name for ratio prioritisation and event-type filtering.
        One of: peak_hydraulic, bnr_nitrification_stress, p_removal_stress,
        septicity, biodegradability, first_flush_solids. None for user-defined
        (no priority applied).
    report : CharacterisationReport, optional
        Characterisation report — required for Section 5 (integrity) and the
        integrity-aware secondary medians in Section 2.
    event_analysis : EventAnalysis, optional
        Event analysis — required for Section 3.
    dataset_filename : str, optional
        Source filename for Section 1.

    Returns
    -------
    DesignEnvelope with all six sections populated. Chart paths remain None
    until envelope_charts.render_envelope_charts is called separately.
    """
    envelope = DesignEnvelope(
        generation_timestamp=datetime.now().isoformat(timespec="seconds"),
    )

    # Default focus parameters
    if focus_parameters is None:
        conc, load, ratio = _default_focus_parameters(df)
        focus_parameters = conc + load + ratio

    # Filter focus parameters to those present
    focus_parameters = [p for p in focus_parameters if p in df.columns]

    # Section 1
    envelope.framing = _build_framing(df, label, dataset_filename,
                                          condition_spec, focus_parameters, concern)

    # Section 2 (returns mask and analysis used downstream)
    section_2, subset_mask, _ = _build_population_section(
        df, condition_spec, focus_parameters, concern, report)
    envelope.population = section_2

    # Section 3
    envelope.events = _build_events_section(df, subset_mask, event_analysis, concern)

    # Section 4
    envelope.over_design = _build_overdesign_section(df, condition_spec, focus_parameters)

    # Section 5
    envelope.integrity = _build_integrity_section(df, subset_mask, report)

    # Section 6
    envelope.limits = _build_limits_section(envelope.framing,
                                                envelope.population,
                                                envelope.events,
                                                df)

    return envelope
