"""
domains/wastewater/technologies/mbr.py

Membrane Bioreactor (MBR)
==========================
Activated sludge combined with submerged membrane filtration
for secondary clarification. Membrane provides a physical barrier
replacing conventional gravity settling.

Process description
-------------------
Wastewater feeds the biological reactor (pre-anoxic + aerobic zones).
The membrane cassettes are submerged directly in the mixed liquor.
Permeate is drawn through the membrane under slight vacuum (TMP 10–40 kPa).
Scour aeration below the membranes controls fouling and keeps the surface clear.
WAS is wasted from the reactor to maintain SRT and MLSS.

Design basis
------------
• Net membrane area:  feed_flow (L/h) / net_gross_factor / design_flux (LMH)
• Net/gross factor:   accounts for 10% downtime (backwash, maintenance)
• Scour aeration:     SADm = 0.20–0.40 m³ air/m²membrane/h (Judd 2011)
• Biological O2:      same as CAS with lower yield at long SRT
• Temperature effect: permeate flux de-rated at T < 20°C (viscosity increases)
• TMP threshold:      > 35 kPa signals severe fouling — needs CIP

References
----------
  - Judd (2011) The MBR Book, 2nd ed. — flux, fouling, SAD, design rules
  - WEF MOP 36 (2012) Membrane Bioreactors
  - Metcalf & Eddy (2014) Ch. 9 — Membrane processes
  - NRMMC/EPHC (2008) Australian Guidelines for Water Recycling
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Type

from domains.wastewater.technologies.base_technology import (
    BaseTechnology, CostItem, TechnologyResult,
)


# ─────────────────────────────────────────────────────────────────────────────
# INPUTS
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class MBRInputs:
    """Design parameters for the MBR process."""

    # ── Membrane design ────────────────────────────────────────────────────
    design_flux_lmh: float = 25.0
    # Net design flux (L/m²/h). Conservative range: 15–25.
    # > 30 LMH increases fouling risk for municipal wastewater.

    peak_flux_lmh: float = 40.0
    # Peak flux for membrane sizing check (usually 1.5–2× average flux).

    membrane_configuration: str = "hollow_fibre"
    # "hollow_fibre" — most common; lower cost per m²
    # "flat_sheet"   — more robust to high-TSS feeds; higher SAD requirement

    include_fine_screening: bool = True
    # 1 mm drum screen required immediately before MBR bioreactor.
    # Critical to prevent rag accumulation on membranes.

    # ── Biological design ──────────────────────────────────────────────────
    srt_days: float = 15.0
    # SRT (days). Longer than CAS (8–12d) → lower yield, better effluent.
    # Typical MBR: 12–25 days.

    mlss_mg_l: float = 10000.0
    # Mixed liquor SS (mg/L). Higher than CAS; typically 8,000–12,000.
    # > 12,000 increases viscosity and fouling propensity.

    design_temperature_celsius: float = 20.0
    # Basin temperature (°C). Flux de-rating applied at T < 20°C.

    anoxic_fraction: float = 0.30
    # Fraction of reactor volume as pre-anoxic zone for TN removal.

    # ── Chemistry ─────────────────────────────────────────────────────────
    chemical_p_removal: bool = True
    coagulant: str = "ferric_chloride"

    _field_bounds: dict = field(default_factory=lambda: {
        "design_flux_lmh":          (10, 45),
        "srt_days":                 (5, 40),
        "mlss_mg_l":                (6000, 15000),
        "design_temperature_celsius": (10, 35),
        "anoxic_fraction":          (0.0, 0.50),
    }, repr=False)


# ─────────────────────────────────────────────────────────────────────────────
# TECHNOLOGY CLASS
# ─────────────────────────────────────────────────────────────────────────────

class MBRTechnology(BaseTechnology):
    """
    Membrane Bioreactor — screening-level planning model.

    Advantages
    ----------
    - Compact footprint: no secondary clarifier required (~40% less space vs CAS)
    - Excellent effluent quality: TSS < 1 mg/L, BOD < 3 mg/L
    - Pathogen LRV credit: 4-log Cryptosporidium, 2-log virus (hollow-fibre)
    - Enables direct reuse: effluent suitable for MF pre-treatment bypass

    Limitations
    -----------
    - Higher OPEX than CAS: membrane replacement is the dominant cost driver
    - Energy-intensive scour aeration: ~0.4 kWh/m³ for membrane fouling control
    - Fine screening essential: rag accumulation destroys membranes rapidly
    - Flux de-rated at low temperature: higher membrane area required in cold climates
    """

    @property
    def technology_code(self) -> str: return "mbr"

    @property
    def technology_name(self) -> str: return "Membrane Bioreactor (MBR)"

    @property
    def technology_category(self) -> str: return "Biological Treatment"

    @classmethod
    def input_class(cls) -> Type: return MBRInputs

    def calculate(
        self,
        design_flow_mld: float,
        inputs: MBRInputs,
    ) -> TechnologyResult:

        r = TechnologyResult(
            technology_name=self.technology_name,
            technology_code=self.technology_code,
            technology_category=self.technology_category,
            description=(
                f"Submerged {inputs.membrane_configuration.replace('_',' ')} MBR replacing "
                "secondary clarification. Compact footprint, high-quality effluent, "
                "pathogen LRV credits."
            ),
        )

        flow_m3_day = design_flow_mld * 1000.0
        flow_lph    = design_flow_mld * 1e6 / 24.0    # L/h

        # ── 1. Influent loads ──────────────────────────────────────────────
        inf = self._load_influent()
        bod_load = flow_m3_day * inf["bod_mg_l"] / 1000.0
        tn_load  = flow_m3_day * inf["tn_mg_l"]  / 1000.0
        tp_load  = flow_m3_day * inf["tp_mg_l"]  / 1000.0

        eff_tn  = self._get_eng("effluent_tn_mg_l",  10.0)
        eff_tp  = self._get_eng("effluent_tp_mg_l",   0.5)
        eff_nh4 = self._get_eng("effluent_nh4_mg_l",  1.0)
        eff_bod = 3.0    # MBR typical (membrane barrier eliminates settleability issues)
        eff_tss = 0.5    # Essentially zero through intact membrane

        tn_removed  = max(0.0, flow_m3_day * (inf["tn_mg_l"] - eff_tn)  / 1000.0)
        tp_removed  = max(0.0, flow_m3_day * (inf["tp_mg_l"] - eff_tp)  / 1000.0)
        bod_removed = max(0.0, flow_m3_day * (inf["bod_mg_l"] - eff_bod) / 1000.0)

        r.notes.add_assumption(
            f"Influent: BOD {inf['bod_mg_l']:.0f}, TN {inf['tn_mg_l']:.0f}, "
            f"TP {inf['tp_mg_l']:.0f} mg/L at Q = {design_flow_mld:.1f} MLD"
        )

        # ── 2. Temperature flux de-rating ─────────────────────────────────
        # Water viscosity increases at lower temperature, reducing flux at the same TMP.
        # De-rating factor (Judd 2011): flux_T = flux_20 × (T/20)^0.5 approximately
        # More precise: kinematic viscosity ratio ν(20)/ν(T)
        import math
        T = inputs.design_temperature_celsius
        # Kinematic viscosity of water (mm²/s): approximate fit
        nu_20 = 1.004   # mm²/s at 20°C
        nu_T  = 1.004 * math.exp(-0.025 * (T - 20.0))   # simple exponential fit
        nu_T  = max(nu_T, 0.5)   # physical floor
        flux_derate = nu_20 / nu_T    # derate factor (< 1 at low T)
        effective_flux = inputs.design_flux_lmh * flux_derate

        if T < 15.0:
            r.notes.warn(
                f"⚠ Design temperature {T}°C is below 15°C. "
                f"Membrane flux de-rated to {effective_flux:.1f} LMH "
                f"({flux_derate*100:.0f}% of design flux). "
                "Additional membrane area may be required — verify with vendor."
            )

        # Flux check: > 30 LMH is aggressive for municipal wastewater
        if inputs.design_flux_lmh > 30.0:
            r.notes.warn(
                f"⚠ Design flux {inputs.design_flux_lmh} LMH exceeds 30 LMH. "
                "Municipal wastewater MBRs typically operate at 15–25 LMH (net). "
                "Confirm with membrane vendor for this feed quality."
            )

        # MLSS fouling warning
        if inputs.mlss_mg_l > 12000.0:
            r.notes.warn(
                f"⚠ MLSS {inputs.mlss_mg_l:,.0f} mg/L exceeds 12,000 mg/L. "
                "High MLSS increases viscosity and fouling propensity. "
                "Operating data suggests flux reduction > 15% above 12,000 mg/L "
                "(Judd 2011 §4.2)."
            )

        # ── 3. Membrane area sizing ────────────────────────────────────────
        net_gross   = self._get_eng("mbr_net_to_gross_factor", 0.90)
        # Gross flux accounts for membrane downtime during maintenance/backwash
        gross_flux  = effective_flux * net_gross
        # Area from average flow
        mem_area_av = flow_lph / gross_flux
        # Area from peak flow check (peak factor 2.5× with peak_flux limit)
        mem_area_pk = flow_lph * 2.5 / inputs.peak_flux_lmh
        mem_area_m2 = max(mem_area_av, mem_area_pk)

        r.notes.add_assumption(
            f"Membrane area: {mem_area_m2:,.0f} m² "
            f"(design flux {inputs.design_flux_lmh} LMH, T-corrected {effective_flux:.1f} LMH, "
            f"net/gross={net_gross}, {inputs.membrane_configuration}) — Judd 2011"
        )

        # ── 4. Biological zone sizing ──────────────────────────────────────
        y_obs    = self._get_eng("mbr_observed_yield", 0.25)   # Lower at long SRT
        vss_tss  = self._get_eng("vss_to_tss_ratio", 0.80)
        vss_prod = y_obs * bod_removed
        tss_prod = vss_prod / vss_tss
        reactor  = vss_prod * inputs.srt_days * 1000.0 / (inputs.mlss_mg_l * vss_tss)
        hrt_hr   = reactor / flow_m3_day * 24.0

        r.sludge.biological_sludge_kgds_day = round(tss_prod, 1)
        r.sludge.vs_fraction = vss_tss
        r.sludge.feed_ts_pct = 1.5

        r.notes.add_assumption(
            f"y_obs = {y_obs} kgVSS/kgBOD (MBR long SRT, Judd 2011 Table 4.1)"
        )

        # ── 5. Energy: biological aeration ────────────────────────────────
        alpha   = self._get_eng("alpha_factor", 0.55)
        sae_std = self._get_eng("standard_aeration_efficiency_kg_o2_kwh", 1.8)
        sae     = sae_std * alpha

        nh4_frac = self._get_eng("influent_nh4_mg_l", 35.0) / max(inf["tn_mg_l"], 1.0)
        o2_c     = bod_removed * 1.42 * (1.0 - 1.42 * y_obs)
        o2_n     = 4.57 * tn_load * nh4_frac * 0.90
        no3_dn   = tn_removed * 0.70 * inputs.anoxic_fraction / 0.30  # scale by anoxic fraction
        o2_dn    = 2.86 * no3_dn
        o2_kg    = max(0.0, o2_c + o2_n - o2_dn)
        bio_aer_kwh = o2_kg / sae

        # ── 6. Energy: membrane scour aeration ────────────────────────────
        sad        = self._get_eng("mbr_sad", 0.30)   # m³ air/m²membrane/h (Judd Table 3.3)
        scour_kwh  = sad * mem_area_m2 * 24.0 * 0.006  # 0.006 kWh/m³ air (Judd 2011)
        # Compression energy at ~60 kPa (4.5m submergence + 15 kPa losses):
        # ~0.006 kWh/m³ air. This gives scour ≈ 100–150 kWh/ML, total MBR ≈ 400–600 kWh/ML
        # consistent with full-scale data (WEF MOP 36, Judd 2011 Table 3.3)

        r.notes.add_assumption(
            f"Membrane SAD = {sad} m³ air/m²/h (Judd 2011 Table 3.3) → "
            f"scour aeration = {scour_kwh:.0f} kWh/day "
            f"({scour_kwh/(flow_m3_day)*1000:.0f} Wh/m³)"
        )

        # ── 7. Energy: permeate pumping ────────────────────────────────────
        tmp_kpa  = abs(self._get_eng("mbr_tmp_kpa", 25.0))
        pump_eff = self._get_eng("pump_efficiency", 0.72)
        perm_kwh = (tmp_kpa * 1000 * flow_lph / 1000 * 24) / (3600 * 1000 * pump_eff)

        # ── 8. Energy: RAS pumping ────────────────────────────────────────
        ras_kwh = (flow_m3_day * 1.0 * 3.0 * 9810) / (3600 * 1000 * pump_eff) * 24.0

        # ── 9. Energy: fine screening ─────────────────────────────────────
        screen_kwh = flow_m3_day * 0.005 if inputs.include_fine_screening else 0.0

        r.energy.aeration_kwh_day = round(bio_aer_kwh, 1)
        r.energy.membrane_kwh_day = round(scour_kwh, 1)
        r.energy.pumping_kwh_day  = round(perm_kwh + ras_kwh, 1)
        r.energy.other_kwh_day    = round(screen_kwh, 1)

        # ── 10. Chemical consumption (CIP) ────────────────────────────────
        cip_days  = self._get_eng("mbr_cip_interval_days", 30)
        # Recovery CIP: NaOCl + citric acid per m² membrane
        chems = {
            "sodium_hypochlorite_kg_day": round(mem_area_m2 * 0.002 / cip_days, 3),
            "citric_acid_kg_day":         round(mem_area_m2 * 0.001 / cip_days, 3),
        }
        if inputs.chemical_p_removal:
            p_mol = tp_removed * 1000.0 / 31.0
            chems["ferric_chloride_kg_day"] = round(p_mol * 2.5 * 162.2 / 1000.0, 2)
        r.chemical_consumption = chems

        r.notes.add_assumption(
            f"CIP: NaOCl {chems['sodium_hypochlorite_kg_day']:.3f} kg/day + "
            f"citric acid {chems['citric_acid_kg_day']:.3f} kg/day "
            f"(every {cip_days} days; Judd 2011 §3.4)"
        )

        # ── 11. Effluent quality ───────────────────────────────────────────
        r.performance.effluent_bod_mg_l = eff_bod
        r.performance.effluent_tss_mg_l = eff_tss
        r.performance.effluent_nh4_mg_l = eff_nh4
        r.performance.effluent_tn_mg_l  = eff_tn
        r.performance.effluent_tp_mg_l  = (
            eff_tp if inputs.chemical_p_removal else min(eff_tp + 0.3, 0.8)
        )
        r.performance.reactor_volume_m3           = round(reactor, 0)
        r.performance.hydraulic_retention_time_hr = round(hrt_hr, 1)
        r.performance.footprint_m2 = round(reactor * 0.20, 0)
        # Footprint = full bioreactor (pre-anoxic + aerobic/membrane zones) at ~5m depth.
        # No secondary clarifier required — this is the primary footprint saving vs BNR.
        # MLSS = 10,000 mg/L (2.5× BNR) is what drives the compact reactor volume.
        # Excludes: screening building, chemical dosing area, sludge handling.
        r.performance.additional.update({
            "membrane_area_m2":          round(mem_area_m2, 0),
            "membrane_configuration":    inputs.membrane_configuration,
            "design_flux_lmh":           inputs.design_flux_lmh,
            "effective_flux_lmh":        round(effective_flux, 1),
            "cip_interval_days":         cip_days,
            "tmp_kpa":                   tmp_kpa,
            "lrv_cryptosporidium":       4.0,    # NRMMC 2008 Table B3
            "lrv_virus":                 2.0,    # hollow-fibre at 20°C
            "o2_demand_kg_day":          round(o2_kg, 0),
            "scour_aeration_kwh_kl":     round(scour_kwh / flow_m3_day * 1000, 2),
        })

        # ── 12. Scope 1 emissions ──────────────────────────────────────────
        n2o_ef  = self._get_eng("n2o_emission_factor_g_n2o_per_g_n_removed", 0.016)
        n2o_gwp = self._get_eng("n2o_gwp", 273)
        r.carbon.n2o_biological_tco2e_yr = round(
            tn_removed * n2o_ef * 365 * n2o_gwp / 1000.0, 1
        )
        r.notes.add_assumption(
            f"N2O EF = {n2o_ef} kg N2O/kg N removed (IPCC 2019 Tier 1)"
        )
        r.notes.add_limitation(
            "Membrane replacement cost (~$25–50/m²/yr) is the dominant OPEX driver. "
            "Use vendor quotes for detailed studies; unit rates vary significantly by "
            "configuration and contract structure."
        )
        r.notes.add_limitation(
            "LRV credits are based on NRMMC/EPHC (2008) and may require "
            "site-specific validation for reuse licensing."
        )
        r.notes.add_assumption(
            f"Footprint basis: full bioreactor (pre-anoxic {inputs.anoxic_fraction:.0%} + "
            f"aerobic/membrane {1-inputs.anoxic_fraction:.0%}) at ~5m depth. "
            "No secondary clarifier required. High MLSS (10,000 mg/L) is the primary "
            "driver of compact footprint vs conventional BNR (4,000 mg/L)."
        )

        # ── 13. Risk ──────────────────────────────────────────────────────
        r.risk.reliability_risk       = "Low"
        r.risk.regulatory_risk        = "Low"
        r.risk.technology_maturity    = "Established"
        r.risk.operational_complexity = "Moderate"   # Fouling management, CIP scheduling
        r.risk.site_constraint_risk   = "Low"        # Compact footprint
        r.risk.implementation_risk    = "Low"

        r.risk.additional_flags["membrane_fouling_risk"] = "Moderate"
        r.risk.additional_flags["rag_accumulation_risk"]  = (
            "High" if not inputs.include_fine_screening else "Low"
        )
        if inputs.mlss_mg_l > 12000:
            r.risk.additional_flags["high_mlss_fouling_risk"] = "Moderate"

        # ── 14. CAPEX ─────────────────────────────────────────────────────
        mem_key = (
            "mbr_membrane_per_m2"
            if inputs.membrane_configuration == "hollow_fibre"
            else "mbr_membrane_flat_sheet_per_m2"
        )
        r.capex_items = [
            CostItem(
                "MBR membrane cassettes",
                mem_key,
                mem_area_m2,
                "m² protected area",
                notes="Include cassette modules, manifolds, air diffusers",
            ),
            CostItem(
                "MBR bioreactor tankage",
                "aeration_tank_per_m3",
                reactor,
                "m³",
            ),
            CostItem(
                "Blower system (biological + scour)",
                "blower_per_kw",
                (bio_aer_kwh + scour_kwh) / 24.0,
                "kW installed",
                notes="Combined biological and membrane scour air",
            ),
            CostItem(
                "Permeate + RAS pump systems",
                "pump_per_kw",
                (perm_kwh + ras_kwh) / 24.0,
                "kW installed",
            ),
        ]
        if inputs.include_fine_screening:
            r.capex_items.append(CostItem(
                "Fine screening (1 mm drum screen)",
                "fine_screen_per_unit",
                max(1, int(design_flow_mld / 5) + 1),
                "unit",
                notes="Critical — protects membranes from rags and fibres",
            ))

        # ── 15. OPEX ──────────────────────────────────────────────────────
        mem_repl_key = (
            "mbr_membrane_replacement_per_m2_yr"
            if inputs.membrane_configuration == "hollow_fibre"
            else "mbr_membrane_flat_sheet_replacement_per_m2_yr"
        )
        r.opex_items = [
            CostItem(
                "Electricity — biological aeration",
                "electricity_per_kwh",
                bio_aer_kwh,
                "kWh/day",
            ),
            CostItem(
                "Electricity — membrane scour",
                "electricity_per_kwh",
                scour_kwh,
                "kWh/day",
                notes="Largest single energy item in MBR; reduce via intermittent aeration control",
            ),
            CostItem(
                "Electricity — pumping & screening",
                "electricity_per_kwh",
                perm_kwh + ras_kwh + screen_kwh,
                "kWh/day",
            ),
            CostItem(
                "Membrane replacement (annualised)",
                mem_repl_key,
                mem_area_m2 / 365.0,
                "m²/day (annualised over 7–10 yr life)",
            ),
            CostItem(
                "CIP chemicals (NaOCl + citric acid)",
                "sodium_hypochlorite_per_kg",
                chems["sodium_hypochlorite_kg_day"],
                "kg/day NaOCl",
            ),
            CostItem(
                "Sludge disposal",
                "sludge_disposal_per_tds",
                tss_prod / 1000.0,
                "t DS/day",
            ),
        ]
        if inputs.chemical_p_removal and "ferric_chloride_kg_day" in chems:
            r.opex_items.append(CostItem(
                "Ferric chloride (P removal)",
                "ferric_chloride_per_kg",
                chems["ferric_chloride_kg_day"],
                "kg/day",
            ))

        # ── 16. Assumptions log ───────────────────────────────────────────
        r.assumptions_used = {
            "design_flux_lmh":           inputs.design_flux_lmh,
            "effective_flux_lmh":        round(effective_flux, 1),
            "membrane_configuration":    inputs.membrane_configuration,
            "net_gross_factor":          net_gross,
            "srt_days":                  inputs.srt_days,
            "mlss_mg_l":                 inputs.mlss_mg_l,
            "y_obs_kgvss_kgbod":         y_obs,
            "alpha_factor":              alpha,
            "sae_process_kg_o2_kwh":     round(sae, 2),
            "mbr_sad_m3_m2_h":          sad,
            "tmp_kpa":                   tmp_kpa,
            "cip_interval_days":         cip_days,
            "n2o_ef":                    n2o_ef,
            "design_temperature_celsius": T,
        }

        # ── 17. Finalise ──────────────────────────────────────────────────
        return r.finalise(
            design_flow_mld,
            influent_bod_mg_l=inf["bod_mg_l"],
            influent_nh4_mg_l=inf["tn_mg_l"] * nh4_frac,
            influent_tn_mg_l=inf["tn_mg_l"],
            influent_tp_mg_l=inf["tp_mg_l"],
        )
