"""
apps/wastewater_app/pages/page_14_canungra.py

Canungra STP Intensification Concept Study
============================================
Renders the WaterPoint-integrated view of the Canungra case study:
- 8 scenarios (S0, S1A, S1B, S2-A/B/C3/D/E)
- Dual-interpretation licence basis (A hard cap / B scaled)
- Decision tree by growth horizon with parallel preferred concepts
- Single-point, sweep, diurnal simulation, and DIL tabs

Backed by apps/wastewater_app/canungra/canungra_streamlit.py (Rev 20).
"""
from __future__ import annotations


def render():
    """Entry point called by app.py routing."""
    from apps.wastewater_app.canungra import canungra_streamlit
    canungra_streamlit.render_canungra_tab()
