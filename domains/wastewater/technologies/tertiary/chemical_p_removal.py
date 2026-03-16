"""
domains/wastewater/technologies/tertiary/chemical_p_removal.py

Chemical Phosphorus Removal (CPR) — Tertiary / Post-Precipitation
===================================================================
Coagulant (FeCl3 or alum) addition for TP polishing to <0.1 mg/L,
followed by lamella settler or rapid sand filter for floc separation.

Standalone tertiary module — used after biological secondary treatment
when biological P removal is insufficient for the discharge licence.

Design basis
------------
• Ferric dose: 2.5–4.0 mol Fe / mol P (excess ensures robust performance)
• Lamella settler: surface loading 5–10 m/hr
• Chemical sludge: ~0.7 kg DS per g FeCl3 added (co-precipitation of Fe)

References
----------
  - APHA (2017) Standard Methods — P precipitation
  - WEF MOP 32 (2010) Nutrient Removal, Ch. 5
  - Metcalf & Eddy (2014) Ch. 7 — Chemical P removal
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Type

from domains.wastewater.technologies.base_technology import (
    BaseTechnology, CostItem, TechnologyResult,
)


@dataclass
class CPRInputs:
    influent_tp_mg_l: float = 1.0           # TP entering CPR unit (after biological)
    target_effluent_tp_mg_l: float = 0.10   # Discharge licence target
    coagulant: str = "ferric_chloride"       # ferric_chloride | alum
    mol_ratio: float = 3.0                  # mol metal / mol P (2.5–4.0)
    separator_type: str = "lamella"         # lamella | rsf | daf
    include_polymer: bool = True            # Anionic polymer for floc settling aid

    _field_bounds: dict = field(default_factory=lambda: {
        "influent_tp_mg_l": (0.1, 10.0), "target_effluent_tp_mg_l": (0.02, 1.0),
        "mol_ratio": (1.5, 5.0),
    }, repr=False)


class CPRTechnology(BaseTechnology):
    """
    Chemical Phosphorus Removal — tertiary post-precipitation unit.
    Achieves TP < 0.1 mg/L reliably, even in the presence of variable biological P removal.
    Limitation: generates significant chemical sludge; must be handled separately.
    """

    @property
    def technology_code(self) -> str: return "cpr"
    @property
    def technology_name(self) -> str: return "Chemical Phosphorus Removal (CPR)"
    @property
    def technology_category(self) -> str: return "Tertiary Treatment"

    @classmethod
    def input_class(cls) -> Type: return CPRInputs

    def calculate(self, design_flow_mld: float, inputs: CPRInputs) -> TechnologyResult:
        r = TechnologyResult(
            technology_name=self.technology_name,
            technology_code=self.technology_code,
            technology_category=self.technology_category,
            description=(
                f"Tertiary {inputs.coagulant.replace('_',' ')} dosing for TP polishing "
                f"to {inputs.target_effluent_tp_mg_l} mg/L."
            ),
        )
        flow = design_flow_mld * 1000.0  # m³/day

        # ── 1. P load to be removed ────────────────────────────────────────
        tp_in  = inputs.influent_tp_mg_l
        tp_out = inputs.target_effluent_tp_mg_l
        tp_removed_kg_day = max(0.0, flow * (tp_in - tp_out) / 1000.0)
        tp_mol_day        = tp_removed_kg_day * 1000.0 / 31.0   # mol P/day

        r.notes.add_assumption(
            f"P removal: {tp_in:.2f} → {tp_out:.2f} mg/L "
            f"= {tp_removed_kg_day:.2f} kg P/day removed"
        )

        # ── 2. Coagulant dose ──────────────────────────────────────────────
        if inputs.coagulant == "ferric_chloride":
            # FeCl3, MW = 162.2 g/mol
            metal_mw  = 162.2
            metal_name = "ferric_chloride_kg_day"
            dose_kg   = tp_mol_day * inputs.mol_ratio * metal_mw / 1000.0
        else:
            # Alum Al2(SO4)3·14H2O MW ≈ 594, 2 Al per formula unit
            metal_mw  = 594.0
            metal_name = "alum_kg_day"
            dose_kg   = tp_mol_day * inputs.mol_ratio * metal_mw / 2000.0  # per Al atom

        r.chemical_consumption = {metal_name: round(dose_kg, 2)}

        if inputs.include_polymer:
            # Anionic polymer ~0.5 g/m³ (typical aid for floc settling)
            polymer_kg_day = flow * 0.0005
            r.chemical_consumption["anionic_polymer_kg_day"] = round(polymer_kg_day, 3)

        r.notes.add_assumption(
            f"{inputs.coagulant}: {inputs.mol_ratio:.1f} mol metal / mol P = "
            f"{dose_kg:.1f} kg/day (MW = {metal_mw} g/mol) — WEF MOP 32"
        )

        # ── 3. Chemical sludge production ──────────────────────────────────
        # Fe(OH)3 precipitation: ~0.78 kg DS / kg FeCl3 (WEF MOP 32)
        chem_sludge_kg_day = dose_kg * (0.78 if inputs.coagulant == "ferric_chloride" else 0.60)
        r.sludge.chemical_sludge_kgds_day = round(chem_sludge_kg_day, 2)
        r.sludge.vs_fraction = 0.20   # Chemical sludge is mostly inorganic

        r.notes.add_assumption(
            "Chemical sludge: 0.78 kg DS/kg FeCl3 (Fe(OH)3 + co-precipitated P, WEF MOP 32)"
        )

        # ── 4. Physical sizing ─────────────────────────────────────────────
        # Lamella settler: surface loading 5–10 m/hr
        # Rapid sand filter: 8–12 m/hr
        slr = {"lamella": 7.0, "rsf": 10.0, "daf": 5.0}.get(inputs.separator_type, 7.0)
        sep_area  = flow / 24.0 / slr   # m²
        mix_vol   = flow * 0.02 / 24.0  # flash mix tank ~1.2 min HRT
        floc_vol  = flow * 0.10 / 24.0  # flocculation tank ~6 min HRT

        r.performance.reactor_volume_m3 = round(mix_vol + floc_vol, 1)
        r.performance.footprint_m2      = round(sep_area + (mix_vol + floc_vol) * 0.3, 0)
        r.performance.effluent_tp_mg_l  = inputs.target_effluent_tp_mg_l
        r.performance.effluent_bod_mg_l = None   # Not changed by CPR
        r.performance.effluent_tn_mg_l  = None
        r.performance.additional.update({
            "separator_type": inputs.separator_type,
            "separator_area_m2": round(sep_area, 0),
            "coagulant_dose_kg_day": round(dose_kg, 1),
            "chemical_sludge_kgds_day": round(chem_sludge_kg_day, 1),
        })

        # ── 5. Energy ──────────────────────────────────────────────────────
        # Flash mix + flocculation + settled water pumping: ~0.02 kWh/m³
        r.energy.pumping_kwh_day = round(flow * 0.02, 1)

        # ── 6. Risk ────────────────────────────────────────────────────────
        r.risk.reliability_risk       = "Low"       # Very reliable chemistry
        r.risk.regulatory_risk        = "Low"       # Achieves <0.1 mg/L reliably
        r.risk.technology_maturity    = "Established"
        r.risk.operational_complexity = "Low"
        r.risk.site_constraint_risk   = "Low"
        r.risk.implementation_risk    = "Low"

        # ── 7. CAPEX / OPEX ────────────────────────────────────────────────
        r.capex_items = [
            CostItem("Coagulant dosing system", "coagulant_dosing_per_kgday",
                     dose_kg, "kg/day coagulant"),
            CostItem(f"Separator ({inputs.separator_type})",
                     f"{inputs.separator_type}_per_m2", sep_area, "m²"),
            CostItem("Flash mix + flocculation tanks", "aeration_tank_per_m3",
                     mix_vol + floc_vol, "m³"),
        ]
        r.opex_items = [
            CostItem("Ferric chloride" if inputs.coagulant == "ferric_chloride" else "Alum",
                     f"{'ferric_chloride' if inputs.coagulant=='ferric_chloride' else 'alum'}_per_kg",
                     dose_kg, "kg/day"),
            CostItem("Chemical sludge disposal", "sludge_disposal_per_tds",
                     chem_sludge_kg_day / 1000, "t DS/day"),
            CostItem("Electricity — mixing/pumping", "electricity_per_kwh",
                     r.energy.total_consumption_kwh_day, "kWh/day"),
        ]
        if inputs.include_polymer and "anionic_polymer_kg_day" in r.chemical_consumption:
            r.opex_items.append(CostItem("Anionic polymer", "polymer_per_kg",
                                         r.chemical_consumption["anionic_polymer_kg_day"], "kg/day"))

        r.notes.add_limitation(
            "CPR does not remove dissolved organic P (org-P) which can contribute to effluent TP. "
            "Confirm P speciation before setting effluent target."
        )
        r.assumptions_used = {
            "coagulant": inputs.coagulant, "mol_ratio": inputs.mol_ratio,
            "separator_type": inputs.separator_type,
            "influent_tp_mg_l": tp_in, "target_tp_mg_l": tp_out,
        }
        return r.finalise(design_flow_mld, influent_tp_mg_l=tp_in)
