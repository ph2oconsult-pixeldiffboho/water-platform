"""
tests/conftest.py
Shared pytest fixtures for the Phase 5 design envelope engine test suite.

Fixtures provide:
  clean_df            : synthetic municipal influent, 365 days, no integrity issues
  dirty_df            : clean_df with surgical integrity violations injected at
                        known row indices; tests assert affected_row_indices
                        captures exactly the injected indices
  minimal_config      : CharacterisationConfig with ParameterSpec for the
                        parameters present in the synthetic data
  characterisation_report_factory: builds a CharacterisationReport from a df
                        by running integrity_checks against minimal_config
"""
from __future__ import annotations
import sys
from pathlib import Path

# Make `core.characteriser` importable regardless of where this file lives.
# Walk up from this file's directory looking for the marker that identifies
# the repo root (run_tests.py at the platform repo root, or the parent dir
# that contains both `core` and `tests` for the standalone Phase 5 tree).
def _find_repo_root() -> Path:
    here = Path(__file__).resolve()
    for candidate in [here.parent, *here.parents]:
        if (candidate / "run_tests.py").exists():
            return candidate
        if (candidate / "core").is_dir() and (candidate / "tests").is_dir():
            return candidate
    return here.parent.parent  # last-resort fallback

_REPO_ROOT = _find_repo_root()
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import numpy as np
import pandas as pd
import pytest

from core.characteriser.config_schema import (
    CharacterisationConfig, ParameterSpec,
)
from core.characteriser.integrity_checks import run_integrity_checks
from core.characteriser.report import CharacterisationReport, DatasetMetadata


# Row indices used by the "dirty" fixture for surgical injection. Tests refer
# to these constants when asserting which rows a flag affects, so an injection
# in one place is verified consistently in all places.
DIRTY_INJECTIONS = {
    "bod_negative":          5,    # INT-01: physical_range violation (BOD < 0)
    "ph_too_high":           17,   # INT-01: physical_range violation (pH > 14)
    "flow_zero":             23,   # INT-02: zero in active flow series
    "bod_zero":              101,  # INT-02: zero in active BOD
    "duplicate_date_a":      200,  # INT-03: this date is duplicated at row 201
    "duplicate_date_b":      201,  # INT-03 partner
    "scattered_nan_cod":     145,  # INT-04: isolated NaN, surrounded by valid
    "bod_exceeds_cod":       250,  # INT-05: stoichiometric (BOD > COD)
    "bod_typical_excess":    300,  # INT-01b: above typical_range but below physical
}


@pytest.fixture
def clean_df() -> pd.DataFrame:
    """365-day synthetic municipal influent dataset. No integrity violations."""
    rng = np.random.default_rng(42)
    n = 365
    dates = pd.date_range("2023-01-01", periods=n, freq="D")

    storm_prob = 0.04
    rainfall = np.where(rng.random(n) < storm_prob,
                        rng.gamma(2.0, 6.0, n),
                        rng.gamma(0.3, 0.5, n))
    rainfall = np.clip(rainfall, 0, None)

    flow = (22.0 + rainfall * 0.6 + rng.normal(0, 0.8, n)
            + 1.5 * np.sin(2 * np.pi * np.arange(n) / 365.25))
    flow = np.clip(flow, 8.0, None)

    bod = 240 - 4.0 * (flow - 22.0) + rng.normal(0, 18, n)
    bod = np.clip(bod, 30, None)

    cod = bod * 2.2 + rng.normal(0, 25, n)
    cod = np.clip(cod, 60, None)

    tss = bod * 1.05 + rng.normal(0, 20, n)
    tss = np.clip(tss, 25, None)

    tkn = 45 + rng.normal(0, 2.5, n)
    nh4 = np.clip(tkn * 0.70 + rng.normal(0, 1.5, n), 5, None)
    tp = 7.5 + rng.normal(0, 0.5, n)
    temperature = (18.0 + 6.0 * np.sin(2 * np.pi * (np.arange(n) - 80) / 365.25)
                   + rng.normal(0, 0.6, n))
    ph = 7.3 + rng.normal(0, 0.2, n)

    df = pd.DataFrame({
        "_date":         dates,
        "flow_mld":      flow,
        "rainfall_mm":   rainfall,
        "bod_mg_l":      bod,
        "cod_mg_l":      cod,
        "tss_mg_l":      tss,
        "tkn_mg_l":      tkn,
        "nh4_mg_l":      nh4,
        "tp_mg_l":       tp,
        "temperature_c": temperature,
        "ph":            ph,
    })

    for c in ["bod", "cod", "tss", "tkn", "nh4", "tp"]:
        df[f"{c}_load_kg_d"] = df[f"{c}_mg_l"] * df["flow_mld"]

    df["nh4_to_tkn"] = df["nh4_mg_l"] / df["tkn_mg_l"]
    df["cod_to_bod"] = df["cod_mg_l"] / df["bod_mg_l"]
    df["bod_to_tkn"] = df["bod_mg_l"] / df["tkn_mg_l"]
    df["tp_to_cod"]  = df["tp_mg_l"]  / df["cod_mg_l"]

    return df


@pytest.fixture
def dirty_df(clean_df: pd.DataFrame) -> pd.DataFrame:
    """clean_df with surgical integrity violations at known indices."""
    df = clean_df.copy()
    inj = DIRTY_INJECTIONS

    # INT-01: physical impossibilities
    df.loc[inj["bod_negative"], "bod_mg_l"] = -50.0
    df.loc[inj["ph_too_high"], "ph"]        = 15.5

    # INT-02: implausible zeros in active series
    df.loc[inj["flow_zero"], "flow_mld"]    = 0.0
    df.loc[inj["bod_zero"], "bod_mg_l"]     = 0.0

    # INT-03: duplicate dates — make row 201's date equal row 200's
    df.loc[inj["duplicate_date_b"], "_date"] = df.loc[inj["duplicate_date_a"], "_date"]

    # INT-04: scattered NaN — isolated missing (surrounded by valid values)
    df.loc[inj["scattered_nan_cod"], "cod_mg_l"] = np.nan

    # INT-05: BOD > COD stoichiometric violation
    df.loc[inj["bod_exceeds_cod"], "bod_mg_l"] = 950.0   # remains below physical max
    df.loc[inj["bod_exceeds_cod"], "cod_mg_l"] = 500.0

    # INT-01b: typical range excursion (below physical max, above typical max)
    # typical for BOD is up to ~600, physical up to 2000. Also lift COD at the
    # same row so this injection does not spuriously trigger INT-05 (BOD>COD).
    df.loc[inj["bod_typical_excess"], "bod_mg_l"] = 850.0
    df.loc[inj["bod_typical_excess"], "cod_mg_l"] = 1900.0  # in typical, > 850 BOD

    return df


@pytest.fixture
def minimal_config() -> CharacterisationConfig:
    """Minimal ParameterSpec set covering the columns in clean_df."""
    return CharacterisationConfig(
        module="wastewater",
        parameters=[
            ParameterSpec("flow_mld",      "Flow",         "MLD",
                          physical_range=(0.0, 1000.0),
                          typical_range=(5.0, 200.0),
                          parameter_type="flow"),
            ParameterSpec("rainfall_mm",   "Rainfall",     "mm",
                          physical_range=(0.0, 500.0),
                          typical_range=(0.0, 100.0),
                          parameter_type="flow"),  # tagged flow, but name has 'rain' → INT-02 skips
            ParameterSpec("bod_mg_l",      "BOD",          "mg/L",
                          physical_range=(0.0, 2000.0),
                          typical_range=(50.0, 600.0),
                          parameter_type="concentration"),
            ParameterSpec("cod_mg_l",      "COD",          "mg/L",
                          physical_range=(0.0, 5000.0),
                          typical_range=(100.0, 1500.0),
                          parameter_type="concentration"),
            ParameterSpec("tss_mg_l",      "TSS",          "mg/L",
                          physical_range=(0.0, 5000.0),
                          typical_range=(50.0, 1000.0),
                          parameter_type="concentration"),
            ParameterSpec("tkn_mg_l",      "TKN",          "mg/L",
                          physical_range=(0.0, 500.0),
                          typical_range=(15.0, 100.0),
                          parameter_type="concentration"),
            ParameterSpec("nh4_mg_l",      "Ammonia",      "mg/L",
                          physical_range=(0.0, 300.0),
                          typical_range=(5.0, 80.0),
                          parameter_type="concentration"),
            ParameterSpec("tp_mg_l",       "Total P",      "mg/L",
                          physical_range=(0.0, 50.0),
                          typical_range=(2.0, 20.0),
                          parameter_type="concentration"),
            ParameterSpec("temperature_c", "Temperature",  "°C",
                          physical_range=(0.0, 45.0),
                          typical_range=(8.0, 30.0),
                          parameter_type="temperature"),
            ParameterSpec("ph",            "pH",           "pH units",
                          physical_range=(0.0, 14.0),
                          typical_range=(6.0, 8.5),
                          parameter_type="ph"),
        ],
    )


@pytest.fixture
def characterisation_report_factory(minimal_config):
    """
    Build a CharacterisationReport from a dataframe by actually running
    integrity_checks. The returned report carries `flags` with populated
    `affected_row_indices`, which Addition C and Section 5 depend on.
    """
    def _factory(df: pd.DataFrame) -> CharacterisationReport:
        report = CharacterisationReport(
            module="wastewater",
            config_version=minimal_config.version,
        )
        report.metadata = DatasetMetadata(
            filename="synthetic.csv",
            n_rows=len(df),
            n_columns=len(df.columns),
        )
        report.flags = run_integrity_checks(df, minimal_config)
        return report

    return _factory
