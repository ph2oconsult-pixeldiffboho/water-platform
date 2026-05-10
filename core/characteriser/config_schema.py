"""
core/characteriser/config_schema.py
Minimal stub of CharacterisationConfig / ParameterSpec.

This file provides the schema dataclasses that integrity_checks.py imports.
It is a contract document for the real implementation — the production
config_schema.py (separate from Phase 5 work) must provide at least these
fields and types.

The real module will likely carry more: parameter-grouping metadata,
expected sample frequency, censoring conventions, etc. Anything used by
integrity_checks.py specifically is captured here.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


@dataclass
class ParameterSpec:
    """
    Specification for a single parameter (BOD, flow, temperature, etc.).

    Fields used by integrity_checks.py:
      name             : canonical column name in the dataframe
      display_name     : human-friendly label for messages
      unit             : units string (mg/L, MLD, etc.)
      physical_range   : (low, high) — outside this is physically impossible
                         (INT-01)
      typical_range    : (low, high) — outside this is unusual but possible
                         (INT-01b). Set to None to skip typical-range check.
      parameter_type   : one of "flow", "concentration", "load",
                         "temperature", "ph", "rainfall", "conductivity",
                         "other". Used by INT-02 to decide whether zero is
                         implausible.
    """
    name: str
    display_name: str
    unit: str
    physical_range: Tuple[float, float]
    typical_range: Optional[Tuple[float, float]] = None
    parameter_type: str = "other"


@dataclass
class CharacterisationConfig:
    """
    Top-level config — a list of ParameterSpec plus module-level metadata.

    Only `parameters` is consumed by integrity_checks.py. The real module
    will carry version, module identifier, cross-correlation pairs, design
    aggregation specifications, etc.
    """
    parameters: List[ParameterSpec] = field(default_factory=list)
    module: str = ""
    version: str = "stub-1.0"
