"""
domains/wastewater/technologies/tertiary/tertiary_filtration.py

Tertiary Filtration
====================
Depth filtration for TSS polishing after biological secondary treatment.
Covers: rapid sand filter (RSF), deep bed (DBF), cloth/disc filter.

Primary function: remove residual TSS to 5–15 mg/L (enabling UV disinfection,
reuse pathways, or tighter discharge licence compliance).

References
----------
  - Tchobanoglous et al. (2014) Wastewater Engineering 5th ed. Ch. 9
  - WEF MOP 8 (2010) Design of Municipal Wastewater Treatment Plants
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Type

from domains.wastewater.technologies.base_technology import (
    BaseTechnology, CostItem, TechnologyResult,
)


@dataclass
class TertiaryFiltrationInputs:
    filter_type: str = "rsf"          # rsf | deep_bed | cloth_disc
    influent_tss_mg_l: float = 12.0   # TSS entering filter (after secondary)
    target_tss_mg_l: float = 5.0      # Target effluent TSS
    hydraulic_loading_rate_m_hr: float = 8.0  # Surface loading (m/hr)
    backwash_frequency_hr: float = 24.0        # Hours between backwashes
    include_uv_disinfection: bool = False      # Add UV after filtration

    _field_bounds: dict = field(default_factory=lambda: {
        "influent_tss_mg_l": (2.0, 40.0), "target_tss_mg_l": (1.0, 15.0),
        "hydraulic_loading_rate_m_hr": (5.0, 15.0),
    }, repr=False)


class TertiaryFiltrationTechnology(BaseTechnology):
    """
    Tertiary Filtration — TSS polishing module.
    Compact, reliable, low-energy TSS reduction to enable reuse or tighter discharge.
    """

    @property
    def technology_code(self) -> str: return "tertiary_filt"
    @property
    def technology_name(self) -> str: return "Tertiary Filtration"
    @property
    def technology_category(self) -> str: return "Tertiary Treatment"

    @classmethod
    def input_class(cls) -> Type: return TertiaryFiltrationInputs

    def calculate(self, design_flow_mld: float, inputs: TertiaryFiltrationInputs) -> TechnologyResult:
        r = TechnologyResult(
            technology_name=f"Tertiary Filtration ({inputs.filter_type.upper()})",
            technology_code=self.technology_code,
            technology_category=self.technology_category,
            description=(
                f"{inputs.filter_type.replace('_',' ').title()} filter polishing "
                f"TSS to {inputs.target_tss_mg_l} mg/L."
            ),
        )
        flow = design_flow_mld * 1000.0  # m³/day

        # ── 1. Filter area ─────────────────────────────────────────────────
        peak_flow_m3hr = flow * 2.0 / 24.0   # 2× peak factor
        filter_area    = peak_flow_m3hr / inputs.hydraulic_loading_rate_m_hr
        # Practical minimum: 2 cells for backwash redundancy
        n_cells = max(2, int(filter_area / 200) + 1)
        area_per_cell = filter_area / n_cells

        r.performance.footprint_m2      = round(filter_area * 1.3, 0)  # 30% for plant room
        r.performance.reactor_volume_m3 = round(filter_area * 1.5, 0)  # ~1.5 m bed depth
        r.performance.effluent_tss_mg_l = inputs.target_tss_mg_l
        r.performance.effluent_bod_mg_l = None   # BOD not significantly changed
        r.performance.effluent_tn_mg_l  = None

        r.performance.additional.update({
            "filter_area_m2":         round(filter_area, 0),
            "n_cells":                n_cells,
            "area_per_cell_m2":       round(area_per_cell, 0),
            "hydraulic_loading_m_hr": inputs.hydraulic_loading_rate_m_hr,
            "filter_type":            inputs.filter_type,
        })

        r.notes.add_assumption(
            f"Filter area: {filter_area:.0f} m² at peak 2× loading of "
            f"{inputs.hydraulic_loading_rate_m_hr} m/hr | "
            f"{n_cells} cells × {area_per_cell:.0f} m² each"
        )
        r.notes.add_assumption(
            f"Hydraulic loading: {inputs.hydraulic_loading_rate_m_hr} m/hr "
            f"(RSF typical: 5–10 m/hr at peak; Metcalf & Eddy Ch. 9)"
        )

        # ── 2. Energy ──────────────────────────────────────────────────────
        # Head loss through filter + backwash pump: ~0.04–0.06 kWh/m³
        filt_kwh  = flow * 0.05
        bw_kwh    = flow * 0.003   # Backwash ~3% of filtered flow
        uv_kwh    = 0.0
        if inputs.include_uv_disinfection:
            # UV dose 40 mJ/cm² for Class A reuse: ~0.05 kWh/m³
            uv_kwh = flow * 0.05
            r.energy.uv_kwh_day = round(uv_kwh, 1)
            r.notes.add_assumption("UV: 40 mJ/cm² dose, 0.05 kWh/m³ (Class A reuse standard)")

        r.energy.pumping_kwh_day = round(filt_kwh + bw_kwh, 1)

        # ── 3. Sludge (backwash water solids) ──────────────────────────────
        tss_removed_kg_day = max(0.0, flow * (inputs.influent_tss_mg_l - inputs.target_tss_mg_l) / 1000.0)
        # Backwash returns to headworks; net sludge is minimal
        r.sludge.biological_sludge_kgds_day = round(tss_removed_kg_day, 1)
        r.sludge.vs_fraction = 0.65
        r.performance.additional["tss_removed_kg_day"] = round(tss_removed_kg_day, 1)

        # ── 4. Risk ────────────────────────────────────────────────────────
        r.risk.reliability_risk       = "Low"
        r.risk.regulatory_risk        = "Low"
        r.risk.technology_maturity    = "Established"
        r.risk.operational_complexity = "Low"
        r.risk.site_constraint_risk   = "Low"
        r.risk.implementation_risk    = "Low"

        if inputs.influent_tss_mg_l > 20:
            r.notes.warn(
                f"Influent TSS {inputs.influent_tss_mg_l} mg/L is high for tertiary filtration. "
                "Consider dual-layer media or coagulant addition ahead of filter."
            )

        # ── 5. CAPEX / OPEX ────────────────────────────────────────────────
        filter_cost_key = {
            "rsf": "rsf_per_m2_filter",
            "deep_bed": "deep_bed_filter_per_m2",
            "cloth_disc": "cloth_filter_per_m2",
        }.get(inputs.filter_type, "rsf_per_m2_filter")

        r.capex_items = [
            CostItem(f"{inputs.filter_type.upper()} filter cells",
                     filter_cost_key, filter_area, "m² filter area"),
            CostItem("Backwash pump and pipework", "pump_per_kw",
                     bw_kwh * 3 / 24, "kW"),
        ]
        if inputs.include_uv_disinfection:
            r.capex_items.append(CostItem("UV disinfection system",
                                          "uv_per_kw_installed", uv_kwh / 24, "kW"))

        r.opex_items = [
            CostItem("Electricity — filtration + backwash",
                     "electricity_per_kwh", r.energy.total_consumption_kwh_day, "kWh/day"),
        ]
        r.notes.add_limitation("Backwash water recycles to plant inlet — add to hydraulic load balance.")
        r.assumptions_used = {
            "filter_type": inputs.filter_type,
            "hydraulic_loading_m_hr": inputs.hydraulic_loading_rate_m_hr,
            "target_tss_mg_l": inputs.target_tss_mg_l,
        }
        return r.finalise(design_flow_mld)
