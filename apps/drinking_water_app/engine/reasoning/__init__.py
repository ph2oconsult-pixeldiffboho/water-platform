"""
AquaPoint Reasoning Engine Package
"""
from .classifier import SourceWaterInputs, ClassificationResult, run_classification
from .archetypes import ARCHETYPES, ArchetypeSelectionResult, run_archetype_selection
from .lrv import LRVResult, calculate_lrv, get_lrv_for_archetype, LRV_BARRIER_CREDITS
from .residuals import ResidualsComparisonResult, compare_residuals, RESIDUAL_STREAMS
from .contaminants import run_contaminant_modules
from .scorer import ArchetypeScore, score_archetypes
from .engine import AquaPointReasoningOutput, run_reasoning_engine

__all__ = [
    "SourceWaterInputs", "ClassificationResult", "run_classification",
    "ARCHETYPES", "ArchetypeSelectionResult", "run_archetype_selection",
    "LRVResult", "calculate_lrv", "get_lrv_for_archetype", "LRV_BARRIER_CREDITS",
    "ResidualsComparisonResult", "compare_residuals", "RESIDUAL_STREAMS",
    "run_contaminant_modules",
    "ArchetypeScore", "score_archetypes",
    "AquaPointReasoningOutput", "run_reasoning_engine",
]
