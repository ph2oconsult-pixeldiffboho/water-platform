"""
PurePoint engine — public interface
"""
from .reasoning import run_reasoning_engine, EffluentInputs, PurePointResult, ClassResult
from .constants import (
    CLASSES, CLASS_LABELS, CLASS_COLOURS, LRV_REQUIRED, BARRIER_CREDITS,
    TREATMENT_TRAINS, CHEMICAL_GROUPS, CHEMICAL_MATRIX, CCP_FRAMEWORK,
    EFFLUENT_PRESETS, FAILURE_SCENARIOS, FAILURE_RESPONSES,
)

def run_full_analysis(inputs: EffluentInputs) -> PurePointResult:
    return run_reasoning_engine(inputs)

__all__ = [
    "run_full_analysis", "EffluentInputs", "PurePointResult", "ClassResult",
    "CLASSES", "CLASS_LABELS", "CLASS_COLOURS", "LRV_REQUIRED", "BARRIER_CREDITS",
    "TREATMENT_TRAINS", "CHEMICAL_GROUPS", "CHEMICAL_MATRIX", "CCP_FRAMEWORK",
    "EFFLUENT_PRESETS", "FAILURE_SCENARIOS", "FAILURE_RESPONSES",
]
