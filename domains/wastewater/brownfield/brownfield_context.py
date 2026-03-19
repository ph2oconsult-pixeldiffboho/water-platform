"""
domains/wastewater/brownfield/brownfield_context.py

BrownfieldContext — Existing plant asset inventory.

This is the only new data model for brownfield mode.
It travels alongside WastewaterInputs — never replaces it.
Technology models, costing, carbon, and QA engines are not modified.

Design note
-----------
All fields are Optional with None defaults so the object can be built
incrementally from a UI form without requiring all fields at once.
The constraint engine handles missing fields gracefully.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class BrownfieldContext:
    """
    Inventory of existing biological treatment assets and site constraints.

    Field naming convention: all volumes in m³, areas in m², power in kW,
    flow in m³/d, time in days.

    Parameters
    ----------
    anaerobic_volume_m3
        Total existing anaerobic zone volume (m³).  0 if no anaerobic zone.
    anoxic_volume_m3
        Total existing anoxic zone volume (m³).
    aerobic_volume_m3
        Total existing aerobic zone volume (m³).  This is the primary
        biological volume used for upgrade feasibility checks.
    clarifier_area_m2
        Total secondary clarifier surface area (m²) across all clarifiers.
        Used for Surface Overflow Rate (SOR) check at peak flow.
    clarifier_count
        Number of secondary clarifiers.  Used to check per-unit SOR.
    blower_capacity_kw
        Installed blower capacity (kW).  Compared against required aeration kW.
        If unknown, set to 0 to trigger a conservative FAIL.
    ras_capacity_m3_d
        Return Activated Sludge pump capacity (m³/d).
        Typical design: 1.0–1.5 × average daily flow.
    mlr_capacity_m3_d
        Mixed Liquor Recirculation pump capacity (m³/d).
        Required for BNR processes.  0 for technologies without MLR.
    available_footprint_m2
        Unencumbered land area available for new civil works (m²).
        Excludes area occupied by existing structures.
    can_add_new_tank
        True if site permits new tank construction (space + planning).
        When False, any technology requiring net new volume fails.
    max_shutdown_days
        Maximum continuous operational shutdown the utility can tolerate.
        0 = no shutdown permitted (must maintain full flow at all times).
    """

    # ── Biological zone volumes ───────────────────────────────────────────
    anaerobic_volume_m3:   Optional[float] = None
    anoxic_volume_m3:      Optional[float] = None
    aerobic_volume_m3:     Optional[float] = None

    # ── Secondary clarification ───────────────────────────────────────────
    clarifier_area_m2:     Optional[float] = None
    clarifier_count:       Optional[int]   = None

    # ── Mechanical / process equipment ───────────────────────────────────
    blower_capacity_kw:    Optional[float] = None
    ras_capacity_m3_d:     Optional[float] = None
    mlr_capacity_m3_d:     Optional[float] = None

    # ── Site constraints ──────────────────────────────────────────────────
    available_footprint_m2: Optional[float] = None
    can_add_new_tank:       bool = True
    max_shutdown_days:      int  = 30

    # ── Computed helpers (populated by constraint_engine) ─────────────────
    @property
    def total_bioreactor_volume_m3(self) -> float:
        """Sum of all biological zone volumes."""
        return (
            (self.anaerobic_volume_m3 or 0.0)
            + (self.anoxic_volume_m3  or 0.0)
            + (self.aerobic_volume_m3 or 0.0)
        )

    @property
    def total_clarifier_area_m2(self) -> float:
        """Total clarifier area — same as clarifier_area_m2 for API consistency."""
        return self.clarifier_area_m2 or 0.0

    def is_complete(self) -> bool:
        """True if all fields required for a full constraint check are populated."""
        return all([
            self.aerobic_volume_m3    is not None,
            self.clarifier_area_m2    is not None,
            self.clarifier_count      is not None,
            self.blower_capacity_kw   is not None,
            self.ras_capacity_m3_d    is not None,
            self.available_footprint_m2 is not None,
        ])

    def summary(self) -> str:
        """One-line human-readable summary for logging and UI."""
        return (
            f"Bioreactor {self.total_bioreactor_volume_m3:.0f} m³ | "
            f"Clarifier {self.total_clarifier_area_m2:.0f} m² × {self.clarifier_count or '?'} | "
            f"Blower {self.blower_capacity_kw or '?'} kW | "
            f"Footprint {self.available_footprint_m2 or '?'} m² | "
            f"Shutdown ≤{self.max_shutdown_days}d"
        )
