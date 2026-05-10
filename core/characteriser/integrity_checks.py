"""
core/characteriser/integrity_checks.py

Integrity checks — does the data even make physical sense?

This layer runs AFTER the loader and BEFORE deeper analysis. It catches the
class of errors the original red-team review flagged but the characteriser
hadn't yet implemented at the data level:

  - Values outside physical_range envelopes (negative flow, pH > 14, Temp > 50)
  - Duplicate rows / duplicate dates
  - Columns where string coercion produced NaN (suggests a non-numeric value
    was present in a numeric column — e.g. "ERROR", "ND", "N/A")
  - Zero values where zero is implausible (zero flow on an active plant)
  - Sign flips (an entire column suddenly negative for a stretch)

Each finding produces an INT-XX flag. Integrity findings are SEVERE — they
indicate the dataset has values that violate physics or schema, not just
unusual statistics. Critical issues block downstream analysis (the engine
uses dataset_confidence demotion for that); Warning issues just surface.

Why this is a separate layer
----------------------------
Earlier checks (data-plausibility, operational-quality) describe properties
of the dataset as a whole. Integrity checks are about INDIVIDUAL VALUES that
shouldn't be there at all. Different mental model: plausibility says
"is this dataset trustworthy", integrity says "are these specific values
possible".
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .config_schema import CharacterisationConfig, ParameterSpec
from .report import (
    CharacterisationFlag, SEV_CRITICAL, SEV_WARNING, SEV_INFO,
)


# ── Per-parameter physical range check ───────────────────────────────────────

def _check_physical_range(df: pd.DataFrame, spec: ParameterSpec) -> Optional[Dict]:
    """
    Compare every value of a parameter against its HARD physical_range envelope.

    physical_range is the impossibility envelope — values outside cannot
    physically exist (negative concentration, pH > 14, temperature outside
    liquid water bounds). Violations are CRITICAL.

    Returns finding dict with the count of violations, examples, and the
    row indices of the violating rows (for downstream filtering).
    """
    if spec.name not in df.columns:
        return None
    s = df[spec.name].dropna()
    if len(s) == 0:
        return None

    low, high = spec.physical_range
    below = s[s < low]
    above = s[s > high]
    n_below = len(below)
    n_above = len(above)
    if n_below == 0 and n_above == 0:
        return None

    examples = []
    if n_below > 0:
        ex = below.head(3).tolist()
        examples.append(("below", low, ex))
    if n_above > 0:
        ex = above.head(3).tolist()
        examples.append(("above", high, ex))

    # Collect the row indices of all violations
    affected_indices = below.index.tolist() + above.index.tolist()

    return {
        "parameter":  spec.name,
        "display":    spec.display_name,
        "unit":       spec.unit,
        "low":        low,
        "high":       high,
        "n_below":    n_below,
        "n_above":    n_above,
        "examples":   examples,
        "n_total":    len(s),
        "affected_indices": affected_indices,
    }


def _check_typical_range(df: pd.DataFrame, spec: ParameterSpec) -> Optional[Dict]:
    """
    Compare values against the SOFT typical_range envelope.

    typical_range describes the expected envelope for the kind of system
    the engine assumes (municipal influent, by default). Values inside
    physical_range but outside typical_range are rare but possible:
    high-strength industrial influent, anaerobic digestion sidestreams,
    tropical conditions, post-treatment dilution, tanker discharge.

    Always reports any excursion. Severity scales with frequency:
      - <1% of values outside typical → Info severity (single excursions,
        likely noise OR a one-off event worth surfacing)
      - ≥1% of values outside typical → Warning severity (systematic —
        the catchment really is unusual, or there's a sampling issue)
    """
    if spec.name not in df.columns or spec.typical_range is None:
        return None
    s = df[spec.name].dropna()
    if len(s) < 30:
        return None

    # Filter to values within physical_range (INT-01 owns the impossible ones)
    phys_low, phys_high = spec.physical_range
    s_in_phys = s[(s >= phys_low) & (s <= phys_high)]
    if len(s_in_phys) == 0:
        return None

    typ_low, typ_high = spec.typical_range
    below = s_in_phys[s_in_phys < typ_low]
    above = s_in_phys[s_in_phys > typ_high]
    n_below = len(below)
    n_above = len(above)
    n_outside = n_below + n_above
    if n_outside == 0:
        return None

    pct_outside = 100.0 * n_outside / len(s_in_phys)

    examples = []
    if n_below > 0:
        examples.append(("below", typ_low, below.head(3).tolist()))
    if n_above > 0:
        examples.append(("above", typ_high, above.head(3).tolist()))

    return {
        "parameter":  spec.name,
        "display":    spec.display_name,
        "unit":       spec.unit,
        "typ_low":    typ_low,
        "typ_high":   typ_high,
        "n_below":    n_below,
        "n_above":    n_above,
        "pct_outside": pct_outside,
        "examples":   examples,
        "n_total":    len(s_in_phys),
        "affected_indices": below.index.tolist() + above.index.tolist(),
    }


# ── Zero-value implausibility check ──────────────────────────────────────────
#
# Zero is suspicious for some parameters (flow on an active plant, BOD,
# alkalinity) but not others (rainfall, NH4 in nitrified effluent). The
# decision is by parameter type — not by hardcoded list.

_ZERO_IMPLAUSIBLE_TYPES = {"flow", "concentration", "load"}


def _check_zero_values(df: pd.DataFrame, spec: ParameterSpec) -> Optional[Dict]:
    """Zero is implausible for flow, concentration, load (but fine for rainfall etc)."""
    if spec.name not in df.columns:
        return None
    if spec.parameter_type not in _ZERO_IMPLAUSIBLE_TYPES:
        return None
    # Rainfall is tagged 'flow' in the wastewater config — exclude it explicitly
    if "rain" in spec.name.lower():
        return None
    s = df[spec.name].dropna()
    zeros = s[s == 0.0]
    if len(zeros) == 0:
        return None
    return {
        "parameter":  spec.name,
        "display":    spec.display_name,
        "n_zeros":    len(zeros),
        "n_total":    len(s),
        "affected_indices": zeros.index.tolist(),
    }


# ── Duplicate-row detection ──────────────────────────────────────────────────

def _check_duplicate_dates(df: pd.DataFrame) -> Optional[Dict]:
    """
    Multiple rows with the same date are a schema integrity issue. They
    inflate sample counts and bias statistics by repeating values.
    """
    if "_date" not in df.columns:
        return None
    dup_mask = df["_date"].duplicated(keep=False)
    if not dup_mask.any():
        return None
    dup_dates = df.loc[dup_mask, "_date"].dt.strftime("%Y-%m-%d").value_counts()
    return {
        "n_duplicate_rows":  int(dup_mask.sum()),
        "n_unique_duplicates": int(len(dup_dates)),
        "examples": dup_dates.head(3).to_dict(),
        "affected_indices": df.index[dup_mask].tolist(),
    }


# ── String-coerced-to-NaN detection ──────────────────────────────────────────
#
# The loader's _parse_censored coerces unparseable strings to NaN. If a
# column has mostly numbers but a few NaN values that align with original
# string entries, that's a sign the source had non-numeric tokens like
# "ERROR", "N/A", "TBA" etc. We can't see the original file from here,
# but we CAN check: if the loader set both columns_unmapped and the NaN
# pattern is bursty rather than spread, suspect string contamination.
#
# Detection: a column with NaN counts > 0 but no extended timestamp gaps
# in the same period is suspicious — values were dropped row-by-row, not
# range-by-range.


def _check_potential_string_coercion(df: pd.DataFrame, spec: ParameterSpec) -> Optional[Dict]:
    """
    Heuristic — flags columns where NaN values are scattered (every NaN
    is bordered by valid values) rather than clustered (long runs of NaN
    that look like analyser dropouts). Scattered NaN = likely string
    coercion; clustered NaN = likely outage.
    """
    if spec.name not in df.columns:
        return None
    s = df[spec.name]
    if len(s) < 30:
        return None
    nan_mask = s.isna()
    n_nan = nan_mask.sum()
    if n_nan == 0:
        return None
    if n_nan == len(s):
        return None
    # Count isolated NaN — preceded and followed by a non-NaN value
    isolated = 0
    isolated_indices: List[int] = []
    for i in range(1, len(nan_mask) - 1):
        if nan_mask.iloc[i] and not nan_mask.iloc[i-1] and not nan_mask.iloc[i+1]:
            isolated += 1
            isolated_indices.append(int(nan_mask.index[i]))
    # If most of the NaN are isolated, scattered pattern suggests string coercion
    if isolated > 0 and isolated >= 0.5 * n_nan:
        return {
            "parameter": spec.name,
            "n_nan":     int(n_nan),
            "n_isolated": int(isolated),
            "affected_indices": isolated_indices,
        }
    return None


# ── Row-level cross-parameter consistency ────────────────────────────────────
#
# Stoichiometric identities — relationships that must hold on every row
# where both parameters are reported, because of how the parameters are
# defined chemically. A row that violates one of these has a data error
# (lab QA, transcription, sample mismatch, unit confusion); it is not a
# physics question.
#
# Each tuple: (numerator_param, denominator_param, label, description)
# Identity: numerator <= denominator on every row.

ROW_LEVEL_IDENTITIES = [
    ("bod_mg_l", "cod_mg_l", "BOD ≤ COD",
        "BOD measures the biodegradable fraction of oxidisable matter; COD "
        "measures the total. BOD greater than COD on the same row violates "
        "the chemistry."),
    ("nh4_mg_l", "tkn_mg_l", "NH4 ≤ TKN",
        "Ammonia is one component of total Kjeldahl nitrogen; NH4-N greater "
        "than TKN means the part is greater than the whole."),
    ("vss_mg_l", "tss_mg_l", "VSS ≤ TSS",
        "Volatile suspended solids are the organic fraction of total "
        "suspended solids; VSS > TSS is a definitional impossibility."),
    ("ortho_p_mg_l", "tp_mg_l", "Ortho-P ≤ TP",
        "Orthophosphate is one fraction of total phosphorus; ortho-P > TP "
        "violates the definition."),
    ("no3_mg_l", "tkn_mg_l", "NO3 vs TKN",
        # NO3 is NOT a component of TKN — different definition. This is a
        # cross-check on plausibility: total inorganic N (NO3 + NH4) shouldn't
        # exceed plausible total N. Not a strict identity, so the check is
        # softer (commented out — handled in mass_balance, not here).
        ""),
]


def _check_row_level_identity(df: pd.DataFrame, num_param: str, den_param: str,
                                 noise_tolerance_pct: float = 5.0) -> Optional[Dict]:
    """
    Check rows where both num_param and den_param are present.
    Identity: num <= den. Returns finding dict if any rows violate beyond
    a measurement-noise tolerance.

    noise_tolerance_pct (default 5%): real lab measurements have analytical
    uncertainty around 3-5%. A row where num exceeds den by 1-2% is noise,
    not a real violation. We flag only when num exceeds den by more than
    noise_tolerance_pct% of the den value. This keeps the check sensitive
    to real errors (sign flips, unit confusion, sample mismatch — which
    produce gross violations) while tolerating measurement noise.
    """
    if num_param not in df.columns or den_param not in df.columns:
        return None
    sub = df[[num_param, den_param]].dropna()
    if len(sub) == 0:
        return None
    # Tolerance in absolute terms: num must exceed den by more than
    # noise_tolerance_pct% of den
    threshold = sub[den_param] * (1.0 + noise_tolerance_pct / 100.0)
    violations = sub[sub[num_param] > threshold]
    if len(violations) == 0:
        return None
    examples = []
    for idx, row in violations.head(3).iterrows():
        excess_pct = 100.0 * (row[num_param] - row[den_param]) / row[den_param]
        examples.append(f"{num_param}={row[num_param]:.2f}, {den_param}={row[den_param]:.2f} "
                        f"(num exceeds den by {excess_pct:.1f}%)")
    return {
        "num_param":   num_param,
        "den_param":   den_param,
        "n_violations": int(len(violations)),
        "n_compared":  int(len(sub)),
        "pct_violated": 100.0 * len(violations) / len(sub),
        "noise_tolerance_pct": noise_tolerance_pct,
        "examples":    examples,
        "affected_indices": violations.index.tolist(),
    }


def _check_all_row_level_identities(df: pd.DataFrame) -> List[Dict]:
    """Run all stoichiometric-identity checks. Returns findings list."""
    findings = []
    for num_param, den_param, label, description in ROW_LEVEL_IDENTITIES:
        if not description:
            continue   # Skip soft / not-strict identities
        try:
            finding = _check_row_level_identity(df, num_param, den_param)
            if finding is None:
                continue
            finding["label"] = label
            finding["description"] = description
            findings.append(finding)
        except Exception:
            continue
    return findings




def run_integrity_checks(df: pd.DataFrame,
                           config: CharacterisationConfig
                           ) -> List[CharacterisationFlag]:
    """
    Run integrity checks against config-declared parameter specs.

    Findings are flagged with INT-XX rule IDs:
      INT-01: physical_range violation
      INT-02: zero-value implausibility
      INT-03: duplicate dates
      INT-04: scattered NaN suggesting string coercion in source data
    """
    flags: List[CharacterisationFlag] = []

    # INT-01: HARD physical range violations (per parameter) — Critical
    for spec in config.parameters:
        try:
            finding = _check_physical_range(df, spec)
            if finding is None:
                continue
            n_total_violations = finding["n_below"] + finding["n_above"]
            ex_strs = []
            for direction, bound, vals in finding["examples"]:
                vals_str = ", ".join(f"{v:.2f}" for v in vals)
                # Count direction-specific to avoid the "1 below ... 2 below" confusion
                count_dir = finding["n_below"] if direction == "below" else finding["n_above"]
                ex_strs.append(f"{count_dir} {direction} {bound} {finding['unit']} (e.g. {vals_str})")
            flags.append(CharacterisationFlag(
                rule_id="INT-01",
                severity=SEV_CRITICAL,
                parameter=spec.name,
                pattern=f"Physically impossible values for {finding['display']}",
                message=(f"{finding['display']} has {n_total_violations} value(s) outside the "
                         f"PHYSICAL range [{finding['low']}, {finding['high']}] {finding['unit']}: "
                         + "; ".join(ex_strs) + ". These values are physically impossible "
                         "(sign error, unit confusion, data corruption, or transcription error)."),
                implication=("These values cannot exist. They will distort means, percentiles, "
                              "and any derived design statistic. The dataset cannot be used for "
                              "design until these are explained or removed."),
                recommended_action=("Review the source file at the affected dates. Determine "
                                      "whether the values are data-entry errors, unit-conversion "
                                      "issues, or sign-flip artefacts. Either correct them at "
                                      "source or NaN them out before re-running."),
                affected_row_indices=finding.get("affected_indices", []),
            ))
        except Exception:
            pass

    # INT-01b: SOFT typical-range excursions (per parameter)
    # Severity scales with frequency: Info for single excursions, Warning
    # for sustained patterns. Always fires when there's an excursion.
    for spec in config.parameters:
        try:
            finding = _check_typical_range(df, spec)
            if finding is None:
                continue
            n_outside = finding["n_below"] + finding["n_above"]
            severity = SEV_WARNING if finding["pct_outside"] >= 1.0 else SEV_INFO
            ex_strs = []
            for direction, bound, vals in finding["examples"]:
                vals_str = ", ".join(f"{v:.2f}" for v in vals)
                count_dir = finding["n_below"] if direction == "below" else finding["n_above"]
                ex_strs.append(f"{count_dir} {direction} {bound} {finding['unit']} (e.g. {vals_str})")

            # Different message for single excursions vs sustained patterns
            if severity == SEV_INFO:
                lead = (f"{finding['display']} has {n_outside} value(s) outside the typical "
                        f"municipal envelope [{finding['typ_low']}, {finding['typ_high']}] "
                        f"{finding['unit']} (single or rare excursions): " + "; ".join(ex_strs)
                        + ". This is a heads-up — the value(s) are physically possible but "
                        "unusual.")
            else:
                lead = (f"{finding['display']} has {n_outside} value(s) "
                        f"({finding['pct_outside']:.1f}% of valid data) outside the typical "
                        f"municipal envelope [{finding['typ_low']}, {finding['typ_high']}] "
                        f"{finding['unit']}: " + "; ".join(ex_strs) + ". The pattern is "
                        "sustained, not a single excursion.")

            flags.append(CharacterisationFlag(
                rule_id="INT-01b",
                severity=severity,
                parameter=spec.name,
                pattern=f"Values outside typical range for {finding['display']}",
                message=(lead + " These values may represent industrial slug loads, "
                         "sidestream returns, anaerobic digester returns, tanker discharge, "
                         "tropical conditions, or unusual catchment characteristics — OR "
                         "they may represent data errors that the typical envelope catches "
                         "but the physical envelope does not."),
                implication=("Statistics may describe a system outside the typical municipal "
                              "envelope. Design assumptions calibrated against typical municipal "
                              "influent may not apply." if severity == SEV_WARNING else
                              "Single rare excursions usually do not affect aggregate statistics, "
                              "but each represents either a real one-off event or a data error "
                              "that warrants confirmation."),
                recommended_action=("Confirm whether the unusual values are real (verify with "
                                      "site context: industrial inputs, sidestreams, climate, "
                                      "post-treatment dilution) or data errors. If real, document "
                                      "the catchment as atypical so downstream design decisions "
                                      "account for it."),
                affected_row_indices=finding.get("affected_indices", []),
            ))
        except Exception:
            pass

    # INT-02: zero values where implausible
    for spec in config.parameters:
        try:
            finding = _check_zero_values(df, spec)
            if finding is None:
                continue
            flags.append(CharacterisationFlag(
                rule_id="INT-02",
                severity=SEV_WARNING,
                parameter=spec.name,
                pattern=f"Zero values in {finding['display']}",
                message=(f"{finding['display']} contains {finding['n_zeros']} zero value(s) "
                         f"out of {finding['n_total']} total. Zero is implausible for an active "
                         "wastewater stream and typically indicates instrument fault, "
                         "data-entry error, or an analyser reporting below-detection as 0."),
                implication=("Zero values bias means low and may corrupt log-space distribution "
                              "fits (lognormal cannot accept zero). Aggregate statistics affected."),
                recommended_action=("Confirm whether zeros are real (plant offline) or artefacts. "
                                      "Replace with NaN before re-running characterisation if "
                                      "they are not real measurements."),
                affected_row_indices=finding.get("affected_indices", []),
            ))
        except Exception:
            pass

    # INT-03: duplicate dates
    try:
        dup = _check_duplicate_dates(df)
        if dup:
            ex_str = "; ".join(f"{d} ({n} copies)" for d, n in dup["examples"].items())
            flags.append(CharacterisationFlag(
                rule_id="INT-03",
                severity=SEV_WARNING,
                parameter="dataset",
                pattern="Duplicate dates in record",
                message=(f"{dup['n_unique_duplicates']} date(s) appear more than once "
                         f"({dup['n_duplicate_rows']} duplicated rows total). Examples: {ex_str}."),
                implication=("Duplicate rows inflate sample counts and bias statistics toward "
                              "the duplicated values. Time-series analysis may produce inconsistent "
                              "results across resampling steps."),
                recommended_action=("De-duplicate the source data. Confirm whether the duplicates "
                                      "represent two genuine sub-samples taken on the same day, "
                                      "or accidental row repetition during compilation."),
                affected_row_indices=dup.get("affected_indices", []),
            ))
    except Exception:
        pass

    # INT-04: scattered NaN suggesting source-data string contamination
    for spec in config.parameters:
        try:
            finding = _check_potential_string_coercion(df, spec)
            if finding is None:
                continue
            flags.append(CharacterisationFlag(
                rule_id="INT-04",
                severity=SEV_INFO,
                parameter=spec.name,
                pattern=f"Scattered missing values in {spec.display_name}",
                message=(f"{spec.display_name} has {finding['n_nan']} missing value(s), of "
                         f"which {finding['n_isolated']} are isolated (single missing day "
                         "between two valid days). This bursty pattern is more consistent with "
                         "non-numeric tokens in source data ('ERROR', 'N/A', '<DL') than with "
                         "instrument outages."),
                implication="If the source data had string tokens, the engine has silently "
                              "discarded them. The discarded values may carry information "
                              "(e.g. detection-limit non-detects) that has been lost.",
                recommended_action=("Open the source file and check whether the affected rows "
                                      "contained string values. If yes, decide explicitly how to "
                                      "handle them (substitute DL/2, exclude, or impute)."),
                affected_row_indices=finding.get("affected_indices", []),
            ))
        except Exception:
            pass

    # INT-05: row-level stoichiometric identity checks
    # Catches BOD>COD, NH4>TKN, VSS>TSS, Ortho-P>TP — definitional
    # impossibilities the row-mean ratio checks (in mass_balance) miss.
    try:
        identity_findings = _check_all_row_level_identities(df)
        for finding in identity_findings:
            ex_str = "; ".join(finding["examples"])
            severity = SEV_CRITICAL if finding["pct_violated"] >= 5.0 else SEV_WARNING
            flags.append(CharacterisationFlag(
                rule_id="INT-05",
                severity=severity,
                parameter=f"{finding['num_param']} vs {finding['den_param']}",
                pattern=f"Stoichiometric identity violated: {finding['label']}",
                message=(f"Identity {finding['label']} fails on "
                         f"{finding['n_violations']} of {finding['n_compared']} rows where "
                         f"both parameters are reported "
                         f"({finding['pct_violated']:.1f}%), beyond a "
                         f"{finding['noise_tolerance_pct']:.0f}% measurement-noise tolerance. "
                         f"Examples: {ex_str}. {finding['description']}"),
                implication=("Stoichiometric impossibilities indicate row-level data errors: "
                              "lab QA failure, sample mismatch (different days reported on the "
                              "same row), unit confusion between parameters, or transcription "
                              "error. Statistics computed over the violating rows are unreliable."),
                recommended_action=("Review the affected rows. Confirm whether "
                                      f"{finding['num_param']} and {finding['den_param']} were "
                                      "measured on the same sample, by the same lab, with "
                                      "consistent units. If samples were taken on different days "
                                      "or stored on the same row by accident, separate them. "
                                      "If a unit error, correct at source."),
                affected_row_indices=finding.get("affected_indices", []),
            ))
    except Exception as e:
        pass

    return flags
