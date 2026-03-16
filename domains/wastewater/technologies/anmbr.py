"""
domains/wastewater/technologies/anmbr.py

Anaerobic Treatment — AnMBR / UASB
=====================================
AnMBR: Anaerobic Membrane Bioreactor — membrane replaces gravity settling.
UASB:  Upflow Anaerobic Sludge Blanket — simpler, lower capital.

Key advantage: net energy producer (biogas offset > electrical consumption).
Limitation: requires aerobic post-treatment for nutrient removal.

References
----------
  - Liao et al. (2006) AnMBR for municipal WW — Bioresource Tech.
  - Metcalf & Eddy (2014) Ch. 10 — Anaerobic treatment
  - van Lier (2008) High-rate anaerobic WW treatment — Water Sci. Tech.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Type

from domains.wastewater.technologies.base_technology import (
    BaseTechnology, CostItem, TechnologyResult,
)

CH4_DENSITY_KG_M3 = 0.716   # kg/Nm³
CH4_LHV_MJ_M3    = 35.8     # Lower heating value


@dataclass
class AnMBRInputs:
    mode: str = "anmbr"               # anmbr | uasb
    hrt_hours: float = 8.0
    srt_days: float = 30.0
    temperature_celsius: float = 30.0  # Mesophilic preferred (30–37°C)
    vs_destruction_pct: float = 55.0   # VS destruction (%)
    biogas_ch4_fraction: float = 0.65
    include_post_treatment: bool = True

    _field_bounds: dict = field(default_factory=lambda: {
        "hrt_hours": (4, 24), "temperature_celsius": (20, 40),
    }, repr=False)


class AnMBRTechnology(BaseTechnology):
    """
    AnMBR / UASB anaerobic treatment.
    Net energy producer at typical municipal BOD loadings.
    Temperature sensitive — performance drops significantly below 20°C.
    """

    @property
    def technology_code(self) -> str: return "anmbr"
    @property
    def technology_name(self) -> str:
        return "Anaerobic MBR (AnMBR)" if True else "UASB"
    @property
    def technology_category(self) -> str: return "Biological Treatment"

    @classmethod
    def input_class(cls) -> Type: return AnMBRInputs

    def calculate(self, design_flow_mld: float, inputs: AnMBRInputs) -> TechnologyResult:
        r = TechnologyResult(
            technology_name="Anaerobic MBR (AnMBR)" if inputs.mode == "anmbr" else "UASB Reactor",
            technology_code=self.technology_code,
            technology_category=self.technology_category,
            description="Anaerobic treatment producing biogas energy from organic solids.",
        )
        flow = design_flow_mld * 1000.0

        # ── 1. Influent ────────────────────────────────────────────────────
        inf = self._load_influent()
        bod_load = flow * inf["bod_mg_l"] / 1000.0
        cod_load = flow * inf["cod_mg_l"] / 1000.0

        r.notes.add_assumption(
            f"Influent BOD {inf['bod_mg_l']:.0f} mg/L, COD {inf['cod_mg_l']:.0f} mg/L"
        )

        # ── 2. Biogas production ───────────────────────────────────────────
        # 0.35 m³ CH4 per kg COD destroyed (Metcalf Eq. 10-18, STP)
        cod_dest  = cod_load * (inputs.vs_destruction_pct / 100.0)
        ch4_m3    = cod_dest * 0.35
        biogas_m3 = ch4_m3 / inputs.biogas_ch4_fraction

        r.notes.add_assumption(
            f"0.35 m³ CH4 / kg COD destroyed (Metcalf Eq. 10-18); "
            f"CH4 fraction = {inputs.biogas_ch4_fraction}"
        )

        # ── 3. CHP electricity generation ────────────────────────────────
        ch4_e_mj    = self._get_carbon("ch4_energy_density_mj_m3", 35.8)
        chp_eff     = self._get_carbon("chp_electrical_efficiency", 0.38)
        chp_kwh_day = ch4_m3 * ch4_e_mj / 3.6 * chp_eff

        r.energy.generation_kwh_day = round(chp_kwh_day, 1)
        r.energy.biogas_m3_day      = round(biogas_m3, 1)
        r.energy.ch4_m3_day         = round(ch4_m3, 1)

        # ── 4. Parasitic energy consumption ──────────────────────────────
        # AnMBR: membrane scour (biogas sparging) ~0.4 kWh/m³
        # UASB:  very low ~0.1 kWh/m³
        parasitic = flow * (0.40 if inputs.mode == "anmbr" else 0.10)
        r.energy.membrane_kwh_day = round(parasitic, 1) if inputs.mode == "anmbr" else 0.0
        r.energy.pumping_kwh_day  = round(parasitic, 1) if inputs.mode == "uasb" else 0.0

        r.notes.add_assumption(
            f"Parasitic energy: {0.40 if inputs.mode=='anmbr' else 0.10} kWh/m³ "
            f"({'membrane scour' if inputs.mode=='anmbr' else 'UASB pumping'})"
        )

        # ── 5. Sludge production — very low ──────────────────────────────
        y_anaerobic = 0.08   # kgVSS/kgCOD (Metcalf Table 10-5; vs aerobic 0.4–0.6)
        sludge      = y_anaerobic * cod_dest / 0.75
        reactor_m3  = flow * inputs.hrt_hours / 24.0
        mem_area_m2 = (flow * 1000 / 24.0 / 12.0) if inputs.mode == "anmbr" else 0.0

        r.sludge.biological_sludge_kgds_day = round(sludge, 1)
        r.sludge.vs_fraction = 0.70   # Digested anaerobic sludge
        r.performance.reactor_volume_m3  = round(reactor_m3, 0)
        r.performance.footprint_m2       = round(reactor_m3 * 0.18, 0)

        r.notes.add_assumption(
            f"y_anaerobic = {y_anaerobic} kgVSS/kgCOD (Metcalf Table 10-5)"
        )

        # ── 6. Effluent quality ────────────────────────────────────────────
        r.performance.effluent_bod_mg_l = 30.0 if inputs.mode == "uasb" else 5.0
        r.performance.effluent_tss_mg_l = 20.0 if inputs.mode == "uasb" else 1.0
        r.performance.effluent_tn_mg_l  = inf["tn_mg_l"] * 0.9  # minimal N removal
        r.performance.effluent_tp_mg_l  = inf["tp_mg_l"] * 0.9
        r.performance.additional.update({
            "biogas_m3_day": round(biogas_m3, 0),
            "chp_electricity_kwh_day": round(chp_kwh_day, 0),
            "net_energy_kwh_day": round(chp_kwh_day - parasitic, 0),
            "membrane_area_m2": round(mem_area_m2, 0) if inputs.mode == "anmbr" else "N/A",
            "post_treatment_required": True,
        })

        # ── 7. Scope 1 CH4 fugitive ────────────────────────────────────────
        ch4_fug_pct = 0.03   # 3% fugitive (cover + handling)
        ch4_fug_kg  = ch4_m3 * ch4_fug_pct * CH4_DENSITY_KG_M3
        ch4_gwp     = self._get_carbon("ch4_gwp", 28)
        r.carbon.ch4_fugitive_tco2e_yr = round(ch4_fug_kg * 365 * ch4_gwp / 1000, 1)

        grid_ef    = self._get_carbon("grid_emission_factor_kg_co2e_per_kwh", 0.79)
        avoided    = chp_kwh_day * 365 * grid_ef / 1000
        r.performance.additional["avoided_scope2_tco2e_yr_reference"] = round(avoided, 0)

        r.notes.add_assumption(f"CH4 fugitive = {ch4_fug_pct*100:.0f}% of generated (cover + handling)")
        r.notes.warn("Post-treatment required for TN/TP removal — size aerobic polishing step separately.")
        if inputs.temperature_celsius < 20:
            r.notes.warn(f"Temperature {inputs.temperature_celsius}°C < 20°C. Anaerobic performance significantly reduced.")

        # ── 8. Risk ────────────────────────────────────────────────────────
        r.risk.reliability_risk       = "Moderate"   # Temperature/loading sensitive
        r.risk.regulatory_risk        = "Moderate"   # Post-treatment required for permit compliance
        r.risk.technology_maturity    = "Established" if inputs.mode == "uasb" else "Commercial"
        r.risk.operational_complexity = "Moderate"
        r.risk.site_constraint_risk   = "Low"
        r.risk.implementation_risk    = "Moderate"
        r.risk.additional_flags["temperature_sensitivity_risk"] = (
            "High" if inputs.temperature_celsius < 20 else "Low"
        )

        # ── 9. CAPEX / OPEX ────────────────────────────────────────────────
        r.capex_items = [
            CostItem("Anaerobic reactor (covered)", "concrete_tank_per_m3", reactor_m3, "m³"),
            CostItem("Biogas CHP unit", "biogas_chp_per_kw", chp_kwh_day / 24, "kW"),
        ]
        if inputs.mode == "anmbr":
            r.capex_items.append(CostItem("AnMBR membranes", "mbr_membrane_per_m2", mem_area_m2, "m²"))
        r.opex_items = [
            CostItem("Parasitic electricity", "electricity_per_kwh", parasitic, "kWh/day"),
            CostItem("Sludge disposal", "sludge_disposal_per_tds", sludge / 1000, "t DS/day"),
        ]
        r.notes.add_limitation("CAPEX excludes aerobic post-treatment unit for nutrient removal.")
        r.assumptions_used = {
            "mode": inputs.mode, "vs_destruction_pct": inputs.vs_destruction_pct,
            "ch4_m3_per_kg_cod": 0.35, "y_anaerobic": y_anaerobic,
            "chp_efficiency": chp_eff, "ch4_fugitive_pct": ch4_fug_pct,
        }
        return r.finalise(design_flow_mld,
                          influent_bod_mg_l=inf["bod_mg_l"], influent_tn_mg_l=inf["tn_mg_l"])
