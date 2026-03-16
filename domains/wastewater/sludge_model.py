"""
domains/wastewater/sludge_model.py

Sludge and Biosolids Mass Balance Model
=========================================
Screening-level sludge production and mass balance for whole-of-plant planning.

Calculation chain
-----------------
  1. Primary sludge production  (from primary clarification, if present)
  2. Secondary sludge production (from biological treatment)
  3. Combined sludge blend
  4. Thickening
  5. Dewatering
  6. Final cake quantities

All values are annual totals (tDS/yr, tVS/yr, wet tonnes/yr).

References
----------
  - Metcalf & Eddy 5th ed. Chapter 8 — Solids processing
  - WEF MOP 8 — Design of Municipal WWTP
  - EPA (2006) — Biosolids Technology Fact Sheets
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional


# ─────────────────────────────────────────────────────────────────────────────
# INPUT DATACLASS
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class SludgeInputs:
    """
    Inputs to the sludge mass balance model.
    Drawn from plant inputs, technology results, and user-editable assumptions.
    """

    # ── Sludge production (from biological technology results) ────────────
    # These are populated from domain technology outputs (BNR/MBR/etc.)
    secondary_sludge_kg_ds_day: float = 1500.0   # kg DS/day from biological process
    has_primary_treatment: bool = False            # Whether plant has primary clarification

    # Primary sludge parameters (if primary treatment present)
    bod_removed_primary_kg_day: float = 0.0        # kg BOD/day removed in primary
    primary_sludge_yield_kg_ds_per_kg_bod: float = 0.50  # Typical: 0.45–0.55

    # ── Sludge properties ─────────────────────────────────────────────────
    secondary_vs_fraction: float = 0.80           # VS/TS for secondary sludge (0.75–0.85)
    primary_vs_fraction: float = 0.75             # VS/TS for primary sludge (0.70–0.80)

    # ── Thickening ────────────────────────────────────────────────────────
    # Secondary sludge thickening before digestion or dewatering
    thickened_ts_pct: float = 5.0                 # % TS after thickening (4–6%)
    # Primary sludge is assumed at 3.5% TS before blending

    # ── Digestion ─────────────────────────────────────────────────────────
    digestion_included: bool = True
    vs_destruction_pct: float = 0.58              # VS destruction efficiency (0.50–0.70 mesophilic)

    # ── Dewatering ────────────────────────────────────────────────────────
    dewatering_type: str = "centrifuge"            # centrifuge | belt_press | screw_press
    # Cake TS% varies by technology
    centrifuge_cake_ts_pct: float = 22.0          # % TS (18–28%)
    belt_press_cake_ts_pct: float = 18.0          # % TS (15–22%)
    screw_press_cake_ts_pct: float = 20.0         # % TS (18–24%)

    # ── Polymer (for cost and chemical carbon) ────────────────────────────
    polymer_dose_kg_per_t_ds: float = 8.0         # kg polymer / t DS dewatered

    # ── Disposal pathway ──────────────────────────────────────────────────
    disposal_pathway: str = "land_application"
    # Options: land_application | landfill | composting | incineration | pyrolysis | gasification

    # ── Transport ─────────────────────────────────────────────────────────
    transport_distance_km: float = 50.0           # One-way transport distance (km)
    transport_truck_capacity_t: float = 20.0       # Wet tonnes per truck

    # ── Economic ─────────────────────────────────────────────────────────
    land_application_cost_per_t_ds: float = 45.0
    landfill_cost_per_t_ds: float = 280.0
    composting_cost_per_t_ds: float = 150.0
    incineration_cost_per_t_ds: float = 350.0
    pyrolysis_cost_per_t_ds: float = 200.0        # Net after energy recovery
    gasification_cost_per_t_ds: float = 180.0
    transport_cost_per_t_km: float = 0.28         # $/t·km


# ─────────────────────────────────────────────────────────────────────────────
# RESULT DATACLASSES
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class SludgeMassBalance:
    """Annual sludge mass balance — all quantities in tonnes/year."""

    # ── Production ────────────────────────────────────────────────────────
    primary_ds_t_yr: float = 0.0
    secondary_ds_t_yr: float = 0.0
    total_raw_ds_t_yr: float = 0.0
    total_raw_vs_t_yr: float = 0.0
    total_raw_wet_t_yr: float = 0.0       # At blend TS% before thickening

    # ── After thickening ──────────────────────────────────────────────────
    thickened_ds_t_yr: float = 0.0
    thickened_wet_t_yr: float = 0.0
    thickened_ts_pct: float = 0.0

    # ── After digestion (or skip if no digestion) ─────────────────────────
    digested_ds_t_yr: float = 0.0
    digested_vs_t_yr: float = 0.0
    digested_wet_t_yr: float = 0.0
    vs_destroyed_t_yr: float = 0.0
    vs_destruction_pct: float = 0.0
    digestion_included: bool = False

    # ── After dewatering ──────────────────────────────────────────────────
    cake_ds_t_yr: float = 0.0
    cake_ts_pct: float = 0.0
    cake_wet_t_yr: float = 0.0            # Final wet cake to disposal
    dewatering_type: str = ""

    # ── Disposal ─────────────────────────────────────────────────────────
    disposal_pathway: str = ""
    disposal_quantity_t_ds_yr: float = 0.0
    disposal_quantity_wet_t_yr: float = 0.0

    # ── Transport ─────────────────────────────────────────────────────────
    truck_trips_per_year: float = 0.0
    transport_distance_km: float = 0.0

    # ── Polymer ───────────────────────────────────────────────────────────
    polymer_kg_yr: float = 0.0

    # ── Annual disposal cost ──────────────────────────────────────────────
    disposal_cost_yr: float = 0.0
    transport_cost_yr: float = 0.0
    total_sludge_cost_yr: float = 0.0

    # ── Calculation notes ─────────────────────────────────────────────────
    notes: List[str] = field(default_factory=list)

    def to_summary_dict(self) -> Dict[str, Any]:
        return {
            "Raw DS (t/yr)":            round(self.total_raw_ds_t_yr, 0),
            "Raw VS (t/yr)":            round(self.total_raw_vs_t_yr, 0),
            "VS Destroyed (t/yr)":      round(self.vs_destroyed_t_yr, 0),
            "Digested DS (t/yr)":       round(self.digested_ds_t_yr, 0),
            "Cake TS%":                 round(self.cake_ts_pct, 1),
            "Wet Cake (t/yr)":          round(self.cake_wet_t_yr, 0),
            "Disposal Pathway":         self.disposal_pathway,
            "Disposal Cost ($/yr)":     round(self.disposal_cost_yr, 0),
            "Transport Cost ($/yr)":    round(self.transport_cost_yr, 0),
            "Total Sludge Cost ($/yr)": round(self.total_sludge_cost_yr, 0),
            "Truck Trips/yr":           round(self.truck_trips_per_year, 0),
            "Polymer Use (t/yr)":       round(self.polymer_kg_yr / 1000, 1),
        }


# ─────────────────────────────────────────────────────────────────────────────
# SLUDGE MODEL
# ─────────────────────────────────────────────────────────────────────────────

class SludgeModel:
    """
    Screening-level sludge and biosolids mass balance model.

    Usage
    -----
    >>> model = SludgeModel()
    >>> inputs = SludgeInputs(secondary_sludge_kg_ds_day=1500.0)
    >>> result = model.calculate(inputs)
    >>> print(result.cake_wet_t_yr)
    """

    def calculate(self, inp: SludgeInputs) -> SludgeMassBalance:
        r = SludgeMassBalance()
        r.digestion_included = inp.digestion_included
        r.disposal_pathway   = inp.disposal_pathway
        r.dewatering_type    = inp.dewatering_type
        r.transport_distance_km = inp.transport_distance_km

        # ── Step 1: Raw sludge production ─────────────────────────────────
        r.secondary_ds_t_yr = inp.secondary_sludge_kg_ds_day * 365 / 1000.0

        if inp.has_primary_treatment and inp.bod_removed_primary_kg_day > 0:
            r.primary_ds_t_yr = (
                inp.bod_removed_primary_kg_day *
                inp.primary_sludge_yield_kg_ds_per_kg_bod * 365 / 1000.0
            )
        else:
            r.primary_ds_t_yr = 0.0

        r.total_raw_ds_t_yr = r.primary_ds_t_yr + r.secondary_ds_t_yr

        # Blended VS fraction (weighted average)
        if r.total_raw_ds_t_yr > 0:
            vs_blend = (
                r.primary_ds_t_yr * inp.primary_vs_fraction +
                r.secondary_ds_t_yr * inp.secondary_vs_fraction
            ) / r.total_raw_ds_t_yr
        else:
            vs_blend = inp.secondary_vs_fraction

        r.total_raw_vs_t_yr = r.total_raw_ds_t_yr * vs_blend

        # Approximate wet weight before thickening (at low initial TS%)
        blend_ts_pct = self._blend_ts(inp, r.primary_ds_t_yr, r.secondary_ds_t_yr, r.total_raw_ds_t_yr)
        r.total_raw_wet_t_yr = r.total_raw_ds_t_yr / (blend_ts_pct / 100.0) if blend_ts_pct > 0 else 0.0

        r.notes.append(
            f"Raw sludge: {r.total_raw_ds_t_yr:.0f} t DS/yr | "
            f"VS fraction: {vs_blend:.2f} | "
            f"Raw VS: {r.total_raw_vs_t_yr:.0f} t VS/yr"
        )

        # ── Step 2: Thickening ────────────────────────────────────────────
        r.thickened_ds_t_yr  = r.total_raw_ds_t_yr          # DS unchanged
        r.thickened_ts_pct   = inp.thickened_ts_pct
        r.thickened_wet_t_yr = r.thickened_ds_t_yr / (inp.thickened_ts_pct / 100.0)

        r.notes.append(
            f"Thickened sludge: {r.thickened_wet_t_yr:.0f} t wet/yr @ {inp.thickened_ts_pct}% TS"
        )

        # ── Step 3: Digestion ─────────────────────────────────────────────
        if inp.digestion_included:
            vs_destroyed_frac = inp.vs_destruction_pct / 100.0 if inp.vs_destruction_pct > 1 else inp.vs_destruction_pct
            r.vs_destroyed_t_yr = r.total_raw_vs_t_yr * vs_destroyed_frac
            r.vs_destruction_pct = vs_destroyed_frac * 100.0

            # DS after digestion = original DS − VS destroyed
            r.digested_ds_t_yr = r.total_raw_ds_t_yr - r.vs_destroyed_t_yr
            r.digested_vs_t_yr = r.total_raw_vs_t_yr - r.vs_destroyed_t_yr
            r.digested_wet_t_yr = r.digested_ds_t_yr / (inp.thickened_ts_pct / 100.0)

            r.notes.append(
                f"Digestion: VS destruction {vs_destroyed_frac*100:.0f}% | "
                f"VS destroyed: {r.vs_destroyed_t_yr:.0f} t VS/yr | "
                f"Digested DS: {r.digested_ds_t_yr:.0f} t DS/yr"
            )
        else:
            r.digested_ds_t_yr  = r.total_raw_ds_t_yr
            r.digested_vs_t_yr  = r.total_raw_vs_t_yr
            r.digested_wet_t_yr = r.thickened_wet_t_yr
            r.vs_destroyed_t_yr = 0.0
            r.notes.append("No digestion — sludge dewatered directly.")

        # ── Step 4: Dewatering ────────────────────────────────────────────
        cake_ts = self._cake_ts(inp)
        r.cake_ts_pct = cake_ts
        r.cake_ds_t_yr  = r.digested_ds_t_yr
        r.cake_wet_t_yr = r.cake_ds_t_yr / (cake_ts / 100.0)

        r.notes.append(
            f"Dewatering ({inp.dewatering_type}): "
            f"cake @ {cake_ts}% TS | "
            f"wet cake: {r.cake_wet_t_yr:.0f} t/yr"
        )

        # ── Step 5: Polymer ───────────────────────────────────────────────
        r.polymer_kg_yr = r.cake_ds_t_yr * inp.polymer_dose_kg_per_t_ds

        # ── Step 6: Disposal and transport ───────────────────────────────
        r.disposal_quantity_t_ds_yr  = r.cake_ds_t_yr
        r.disposal_quantity_wet_t_yr = r.cake_wet_t_yr

        disposal_rate = self._disposal_rate(inp)
        r.disposal_cost_yr = r.cake_ds_t_yr * disposal_rate

        r.truck_trips_per_year = r.cake_wet_t_yr / inp.transport_truck_capacity_t
        r.transport_cost_yr = (
            r.cake_wet_t_yr * inp.transport_distance_km * 2 * inp.transport_cost_per_t_km
        )  # × 2 for return trip

        r.total_sludge_cost_yr = r.disposal_cost_yr + r.transport_cost_yr

        r.notes.append(
            f"Disposal ({inp.disposal_pathway}): "
            f"${disposal_rate}/t DS | "
            f"cost ${r.disposal_cost_yr:,.0f}/yr | "
            f"transport ${r.transport_cost_yr:,.0f}/yr"
        )

        return r

    # ── Helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def _blend_ts(inp: SludgeInputs, primary_t: float, secondary_t: float, total_t: float) -> float:
        """Weighted average TS% of blend before thickening."""
        if total_t <= 0:
            return 1.0
        primary_pct = 3.5   # Typical settled primary sludge
        secondary_pct = inp.secondary_sludge_kg_ds_day * 365 / 1000 / total_t * 0.8
        # Approximate: secondary WAS is low TS (~0.5–1%), primary is ~3.5%
        return max(0.5, (primary_t * 3.5 + secondary_t * 0.8) / total_t)

    @staticmethod
    def _cake_ts(inp: SludgeInputs) -> float:
        if inp.dewatering_type == "centrifuge":
            return inp.centrifuge_cake_ts_pct
        elif inp.dewatering_type == "belt_press":
            return inp.belt_press_cake_ts_pct
        elif inp.dewatering_type == "screw_press":
            return inp.screw_press_cake_ts_pct
        return inp.centrifuge_cake_ts_pct

    @staticmethod
    def _disposal_rate(inp: SludgeInputs) -> float:
        rates = {
            "land_application": inp.land_application_cost_per_t_ds,
            "landfill":         inp.landfill_cost_per_t_ds,
            "composting":       inp.composting_cost_per_t_ds,
            "incineration":     inp.incineration_cost_per_t_ds,
            "pyrolysis":        inp.pyrolysis_cost_per_t_ds,
            "gasification":     inp.gasification_cost_per_t_ds,
        }
        return rates.get(inp.disposal_pathway, inp.landfill_cost_per_t_ds)
