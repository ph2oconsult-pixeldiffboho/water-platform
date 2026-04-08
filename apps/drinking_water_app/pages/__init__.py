"""
AquaPoint Pages Package
"""
from .page_01_project_setup import render as render_project_setup
from .page_02_source_water import render as render_source_water
from .page_03_technology_selection import render as render_technology_selection
from .page_04_results import render as render_results
from .page_05_report import render as render_report
from .page_06_treatment_philosophy import render as render_treatment_philosophy
from .page_07_scenario_comparison import render as render_scenario_comparison
from .page_08_manual import render as render_manual

__all__ = [
    "render_project_setup",
    "render_source_water",
    "render_technology_selection",
    "render_results",
    "render_report",
    "render_treatment_philosophy",
    "render_scenario_comparison",
    "render_manual",
]
