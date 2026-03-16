"""
domains/wastewater/technologies/reuse/advanced_reuse.py

Advanced Reuse Preparation (MF/UF + RO + UV/AOP)
==================================================
Treatment train for producing Class A+ recycled water from secondary
or tertiary effluent for non-potable reuse (industrial, irrigation,
groundwater recharge) or indirect potable reuse (IPR) with relevant
regulatory validation.

Train
-----
  MF/UF → RO → UV/AOP (+ stabilisation for IPR)

Design basis
------------
• MF/UF: 0.01–0.1 µm — removes turbidity, pathogens, SDI control for RO
• RO:    0.0001 µm — removes dissolved TDS, PFAS, trace organics, viruses
• UV/AOP: destroys trace organics (NDMAs, pesticides) for IPR compliance
• Recovery: MF 95%, RO 75–85% (remainder = concentrate requiring management)

References
----------
  - AWWA (2019) Water Reuse — Issues, Technology and Applications
  - Wintgens et al. (2005) Role of MBR/RO in municipal WW reclamation
  - NRMMC/EPHC (2008) Australian Guidelines for Water Recycling
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Type

from domains.wastewater.technologies.base_technology import (
    BaseTechnology, CostItem, TechnologyResult,
)


@dataclass
class AdvancedReuseInputs:
    reuse_class: str = "non_potable"      # non_potable | ipr | dpr
    include_mf_uf: bool = True            # MF/UF pre-treatment for RO
    include_ro: bool = True               # Reverse osmosis
    include_uv_aop: bool = True           # UV/AOP for trace organics
    ro_recovery: float = 0.80             # RO permeate recovery (0.70–0.85)
    target_tds_mg_l: float = 200.0        # Product water TDS target
    influent_tds_mg_l: float = 800.0      # Feed TDS (after secondary treatment)
    concentrate_disposal: str = "sewer"   # sewer | brine_concentrator | evaporation_pond

    _field_bounds: dict = field(default_factory=lambda: {
        "ro_recovery": (0.60, 0.88), "influent_tds_mg_l": (200, 3000),
    }, repr=False)


class AdvancedReuseTechnology(BaseTechnology):
    """
    Advanced Reuse Preparation — MF/UF + RO + UV/AOP train.
    Produces high-quality product water for non-potable reuse or IPR.
    Limitation: significant energy demand and concentrate requiring management.
    """

    @property
    def technology_code(self) -> str: return "adv_reuse"
    @property
    def technology_name(self) -> str: return "Advanced Reuse Preparation (MF/UF + RO + UV/AOP)"
    @property
    def technology_category(self) -> str: return "Reuse"
    @property
    def requires_upstream(self): return ["bnr", "mbr", "tertiary_filt"]

    @classmethod
    def input_class(cls) -> Type: return AdvancedReuseInputs

    def calculate(self, design_flow_mld: float, inputs: AdvancedReuseInputs) -> TechnologyResult:
        r = TechnologyResult(
            technology_name=self.technology_name,
            technology_code=self.technology_code,
            technology_category=self.technology_category,
            description=(
                f"Advanced reuse train (MF→RO→UV/AOP) producing "
                f"{'Class A+ non-potable' if inputs.reuse_class=='non_potable' else 'IPR-grade'} "
                "recycled water."
            ),
        )
        flow = design_flow_mld * 1000.0  # m³/day feed flow

        # ── 1. Process train flow balance ──────────────────────────────────
        mf_feed   = flow
        mf_prod   = flow * 0.95 if inputs.include_mf_uf else flow  # 5% backwash
        ro_feed   = mf_prod if inputs.include_ro else 0.0
        ro_perm   = ro_feed * inputs.ro_recovery if inputs.include_ro else mf_prod
        ro_conc   = ro_feed - ro_perm if inputs.include_ro else 0.0

        product_flow_m3day = ro_perm    # Product water delivered

        r.notes.add_assumption(
            f"Flow balance: feed {flow:.0f} → MF permeate {mf_prod:.0f} → "
            f"RO permeate {ro_perm:.0f} m³/day "
            f"(recovery {inputs.ro_recovery*100:.0f}%)"
        )
        if ro_conc > 0:
            r.notes.warn(
                f"RO concentrate: {ro_conc:.0f} m³/day "
                f"({ro_conc/flow*100:.0f}% of feed) requires management via {inputs.concentrate_disposal}. "
                "TDS concentrate: ~"
                f"{inputs.influent_tds_mg_l/max(1-inputs.ro_recovery,0.01):.0f} mg/L."
            )

        # ── 2. Membrane sizing ─────────────────────────────────────────────
        mf_area_m2 = 0.0
        ro_area_m2 = 0.0
        if inputs.include_mf_uf:
            mf_flux = 60.0   # LMH — typical MF/UF flux
            mf_area_m2 = mf_feed * 1000.0 / 24.0 / mf_flux   # m²
        if inputs.include_ro:
            ro_flux = 17.0   # LMH — typical brackish RO flux
            ro_area_m2 = ro_feed * 1000.0 / 24.0 / ro_flux

        # ── 3. Energy ──────────────────────────────────────────────────────
        # MF/UF: ~0.1–0.3 kWh/m³
        mf_kwh = mf_feed * 0.20 if inputs.include_mf_uf else 0.0
        # RO: specific energy depends on osmotic pressure
        # Brackish RO (from WWTP secondary eff): ~0.8–1.5 kWh/m³ feed
        ro_kwh = ro_feed * 1.0 if inputs.include_ro else 0.0
        # UV/AOP: 40–100 mJ/cm², ~0.05–0.15 kWh/m³ product
        uv_kwh = product_flow_m3day * 0.08 if inputs.include_uv_aop else 0.0

        r.energy.membrane_kwh_day = round(mf_kwh + ro_kwh, 1)
        r.energy.uv_kwh_day       = round(uv_kwh, 1)
        r.energy.pumping_kwh_day  = round(product_flow_m3day * 0.05, 1)  # Distribution

        r.notes.add_assumption(
            f"Energy: MF {0.20} kWh/m³ + RO {1.0} kWh/m³ feed + UV {0.08} kWh/m³ product"
        )

        # ── 4. Chemical consumption ────────────────────────────────────────
        chems: Dict[str, float] = {}
        if inputs.include_mf_uf:
            chems["sodium_hypochlorite_kg_day"]  = round(mf_feed * 0.001, 3)
            chems["citric_acid_kg_day"]          = round(mf_feed * 0.0005, 3)
        if inputs.include_ro:
            chems["antiscalant_kg_day"]          = round(ro_feed * 0.002, 3)
            chems["acid_ph_adjust_kg_day"]       = round(ro_feed * 0.001, 3)
        r.chemical_consumption = chems

        # ── 5. Effluent quality ────────────────────────────────────────────
        # RO permeate: <50 mg/L TDS, <0.1 mg/L BOD, <0.01 mg/L TP, <1 mg/L TN
        r.performance.effluent_tss_mg_l = 0.1 if inputs.include_ro else 2.0
        r.performance.effluent_bod_mg_l = 0.5 if inputs.include_ro else 3.0
        r.performance.effluent_tn_mg_l  = 2.0 if inputs.include_ro else 5.0
        r.performance.effluent_tp_mg_l  = 0.02 if inputs.include_ro else 0.1
        r.performance.effluent_cod_mg_l = 5.0 if inputs.include_ro else 15.0
        product_tds = inputs.influent_tds_mg_l * (1 - inputs.ro_recovery) / max(inputs.ro_recovery, 0.1) \
                      if inputs.include_ro else inputs.influent_tds_mg_l

        r.performance.reactor_volume_m3 = round((mf_area_m2 + ro_area_m2) * 0.5, 0)
        r.performance.footprint_m2      = round((mf_area_m2 + ro_area_m2) * 0.15, 0)

        # Concentrate solids (rejected particulates + scalants)
        # RO concentrate typically contains 5–15 mg/L suspended solids at 80% recovery
        conc_tss_mg_l = 15.0
        conc_sludge_kg_day = ro_conc * conc_tss_mg_l / 1000.0
        r.sludge.chemical_sludge_kgds_day = round(conc_sludge_kg_day, 1)
        r.sludge.vs_fraction = 0.30   # Mainly inorganic scalants and fines
        r.performance.additional.update({
            "product_flow_m3day":   round(product_flow_m3day, 0),
            "product_flow_mld":     round(product_flow_m3day / 1000, 2),
            "concentrate_m3day":    round(ro_conc, 0),
            "mf_area_m2":           round(mf_area_m2, 0),
            "ro_area_m2":           round(ro_area_m2, 0),
            "product_tds_mg_l":     round(product_tds, 0),
            "pfas_removal":         ">99% via RO (EPA guidance)" if inputs.include_ro else "Not applicable",
            "reuse_class":          inputs.reuse_class,
        })

        # ── 6. Risk ────────────────────────────────────────────────────────
        r.risk.reliability_risk       = "Low"       # Well-proven membranes
        r.risk.regulatory_risk        = "Moderate"  # Reuse regulation evolving
        r.risk.technology_maturity    = "Established"
        r.risk.operational_complexity = "High"      # Fouling control, RO cleaning, validation
        r.risk.site_constraint_risk   = "Low"
        r.risk.implementation_risk    = "Low"
        r.risk.additional_flags["concentrate_management_risk"] = (
            "High" if inputs.concentrate_disposal == "evaporation_pond" else "Moderate"
        )
        r.risk.additional_flags["regulatory_reuse_pathway_risk"] = (
            "High" if inputs.reuse_class == "ipr" else "Low"
        )
        if inputs.reuse_class == "ipr":
            r.notes.warn(
                "IPR pathway requires full validation under state/territory EPA approval. "
                "Engage regulator early — additional monitoring, redundancy, and reporting required."
            )

        # ── 7. CAPEX / OPEX ────────────────────────────────────────────────
        r.capex_items = []
        if inputs.include_mf_uf:
            r.capex_items.append(CostItem("MF/UF membranes", "uf_membrane_per_m2", mf_area_m2, "m²"))
        if inputs.include_ro:
            r.capex_items.append(CostItem("RO membranes", "ro_membrane_per_m2", ro_area_m2, "m²"))
            r.capex_items.append(CostItem("RO high-pressure pumps", "pump_per_kw", ro_kwh / 24, "kW"))
        if inputs.include_uv_aop:
            r.capex_items.append(CostItem("UV/AOP system", "uv_per_kw_installed", uv_kwh / 24, "kW"))

        r.opex_items = [
            CostItem("Electricity — MF/UF + RO + UV",
                     "electricity_per_kwh", r.energy.total_consumption_kwh_day, "kWh/day"),
        ]
        if chems:
            r.opex_items.append(CostItem("Membrane chemicals (CIP, antiscalant)",
                                         "membrane_chemical_per_m3_product",
                                         product_flow_m3day, "m³/day product"))
        ro_repl_key = "ro_membrane_replacement_per_m2_yr"
        if inputs.include_ro:
            r.opex_items.append(CostItem("RO membrane replacement (7yr life)",
                                         ro_repl_key, ro_area_m2 / 365, "m²/day"))

        r.notes.add_limitation(
            "CAPEX excludes: concentrate management infrastructure, product water storage, "
            "regulatory validation programme, and reuse distribution system."
        )
        r.assumptions_used = {
            "reuse_class": inputs.reuse_class, "ro_recovery": inputs.ro_recovery,
            "mf_flux_lmh": 60, "ro_flux_lmh": 17,
            "mf_kwh_m3": 0.20, "ro_kwh_m3": 1.0, "uv_kwh_m3": 0.08,
        }
        return r.finalise(design_flow_mld)
