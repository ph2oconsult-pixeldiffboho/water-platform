"""
domains/wastewater/technologies/mabr_bnr.py

MABR + BNR — Membrane Aerated Biofilm Reactor in BNR Anoxic Zone
=================================================================
MABR modules are installed in the PRIMARY ANOXIC ZONE of the BNR process.

Configuration
-------------
  Anaerobic zone:  conventional mixers → bio-P release (unchanged)
  Anoxic zone:     conventional mixing + MABR modules
                   Bulk liquid: anoxic → denitrification by suspended biomass
                   MABR biofilm: O₂ delivered bubble-free at ~95% OTE
                                 → simultaneous nitrification within biofilm
                                 → MABR provides 30% of NH₄ removal
  Aerobic zone:    conventional diffused aeration, REDUCED BY 30%
                   → smaller aerobic tank volume
                   → lower blower energy
  Clarifiers:      unchanged — MABR does not replace clarification
  RAS / MLR / WAS: unchanged

Engineering basis (Syron & Casey 2008; Houweling et al. 2017)
--------------------------------------------------------------
  Counter-diffusion biofilm: O₂ diffuses inward through membrane wall
  Substrate (NH₄, organics) diffuses inward from bulk liquid
  Creates aerobic nitrifying zone inside biofilm
  Bulk anoxic liquid continues denitrification
  
  MABR handles 30% of NH₄ load in anoxic zone:
  → Aerobic zone NH₄ load reduced 30%
  → Aerobic zone volume reduced 30%
  → Aerobic blowers sized for 70% of original load
  → MABR gas supply (low-pressure) handles 30% at ~95% OTE

  Net aeration energy saving vs BNR: ~25-30%
  (not the theoretical ~88% — must account for blowers still required)

Available as:
  mode="new_build" — new BNR plant designed with MABR in anoxic zone from outset
  mode="retrofit"  — MABR modules added to existing BNR anoxic zone
                     No new tankage; aerobic zone can be decommissioned/repurposed 30%

References
----------
  - Syron & Casey (2008) Membrane-aerated biofilms — Water Research 42(8)
  - Martin et al. (2011) MABR energy comparison — Water Science & Technology
  - Houweling et al. (2017) MABR process design — WEFTEC
  - GE/Ovivo ZeeNon design guidelines (2015)
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
class MABRBNRInputs:
    """Design parameters for MABR + BNR (new-build or retrofit)."""

    # ── Mode ──────────────────────────────────────────────────────────────
    mode: str = "new_build"
    # "new_build" — dedicated MABR zone replaces aerobic basin
    # "retrofit"  — MABR modules submerged into existing aeration basin

    # ── MABR membrane parameters ──────────────────────────────────────────
    nh4_surface_loading_g_m2_day: float = 2.0
    # NH₄-N surface loading rate on the membrane biofilm (g NH₄-N/m²/day).
    # Conservative: 1.5 g/m²/day.  Typical: 2.0.  Aggressive: 2.5–3.0.
    # (GE/Ovivo ZeeNon data; Syron & Casey 2008 report 1–3 g/m²/day range)

    membrane_specific_area_m2_per_m3: float = 300.0
    # Specific surface area of MABR modules (m² membrane/m³ module volume).
    # Typical hollow-fibre: 200–400 m²/m³.

    o2_transfer_efficiency: float = 0.95
    # Fraction of O₂ supplied through membranes that is transferred to biofilm.
    # Near-100% for MABR vs 15–25% for fine-bubble diffusers.

    # ── BNR biological zone ───────────────────────────────────────────────
    srt_days: float = 12.0
    anoxic_fraction: float = 0.35    # Pre-anoxic zone fraction
    anaerobic_fraction: float = 0.10  # Anaerobic zone fraction for bio-P
    mlss_mg_l: float = 3500.0
    # MABR-BNR typically runs at lower suspended MLSS (2,000–4,000 mg/L)
    # because biomass also grows as a biofilm on the membranes.

    # ── Gas supply ────────────────────────────────────────────────────────
    use_pure_oxygen: bool = False
    # False = pressurised air supply (more common, lower capital)
    # True  = pure O₂ (higher transfer, used in high-loading applications)

    # ── Chemistry ─────────────────────────────────────────────────────────
    chemical_p_removal: bool = False
    # Bio-P often achievable via anaerobic zone; chemical polish optional

    # ── Primary clarifier option ───────────────────────────────────────────
    include_primary_clarifier: bool = False
    # Same as BNR: routes ~35% BOD to AD for CHP credit, reduces reactor size.
    # COD/TKN check applies — supplemental carbon may be needed post-PC.
    primary_clarifier_bod_removal_pct: float = 0.35

    _field_bounds: dict = field(default_factory=lambda: {
        "nh4_surface_loading_g_m2_day":     (0.5, 4.0),
        "membrane_specific_area_m2_per_m3": (150, 600),
        "o2_transfer_efficiency":           (0.80, 1.00),
        "srt_days":                         (5, 25),
        "mlss_mg_l":                        (1500, 5000),
    }, repr=False)


# ─────────────────────────────────────────────────────────────────────────────
# TECHNOLOGY CLASS
# ─────────────────────────────────────────────────────────────────────────────

class MABRBNRTechnology(BaseTechnology):
    """
    MABR + BNR — Membrane Aerated Biofilm Reactor (new-build or retrofit).

    Key advantage
    -------------
    Bubble-free O₂ transfer at ~95% efficiency vs 15–25% for fine-bubble
    diffusers → 50–75% lower aeration energy than conventional BNR.
    Simultaneous nitrification-denitrification within the biofilm reduces
    external carbon demand.

    Key limitation
    --------------
    Emerging technology (< 50 full-scale plants globally in 2024).
    MABR does NOT replace clarifiers — secondary clarifiers still required.
    Long-term membrane fouling and replacement costs not fully characterised.
    """

    @property
    def technology_code(self) -> str: return "mabr_bnr"

    @property
    def technology_name(self) -> str:
        suffix = "New-Build" if True else "Retrofit"
        return "MABR + BNR"

    @property
    def technology_category(self) -> str: return "Biological Treatment"

    @classmethod
    def input_class(cls) -> Type: return MABRBNRInputs

    def calculate(
        self,
        design_flow_mld: float,
        inputs: MABRBNRInputs,
    ) -> TechnologyResult:

        mode_label = "New-Build" if inputs.mode == "new_build" else "Retrofit"
        r = TechnologyResult(
            technology_name=f"MABR + BNR ({mode_label})",
            technology_code=self.technology_code,
            technology_category=self.technology_category,
            description=(
                f"MABR {mode_label}: hollow-fibre membranes deliver O₂ bubble-free "
                "into biofilm at ~95% transfer efficiency. "
                + ("New aerobic basin replaced by MABR zone. Pre-anoxic + anaerobic zones retained."
                   if inputs.mode == "new_build" else
                   "MABR modules submerged into existing aeration basin. No new tankage. "
                   "50–75% aeration energy saving at same or greater capacity.")
            ),
        )

        flow = design_flow_mld * 1000.0  # m³/day

        # ── 1. Influent loads ──────────────────────────────────────────────
        inf = self._load_influent()
        bod_load = flow * inf["bod_mg_l"] / 1000.0
        tn_load  = flow * inf["tn_mg_l"]  / 1000.0
        tp_load  = flow * inf["tp_mg_l"]  / 1000.0

        eff_tn  = self._get_eng("effluent_tn_mg_l",  10.0)
        eff_tp  = self._get_eng("effluent_tp_mg_l",   0.5)
        eff_nh4 = self._get_eng("effluent_nh4_mg_l",  1.0)
        eff_bod = self._get_eng("effluent_bod_mg_l", 10.0)
        eff_tss = self._get_eng("effluent_tss_mg_l", 12.0)

        tn_removed  = max(0.0, flow * (inf["tn_mg_l"] - eff_tn)  / 1000.0)
        tp_removed  = max(0.0, flow * (inf["tp_mg_l"] - eff_tp)  / 1000.0)
        bod_removed = max(0.0, flow * (inf["bod_mg_l"] - eff_bod) / 1000.0)

        # ── 1b. Primary clarifier (optional) ──────────────────────────────
        pc_sludge_kgds_day  = 0.0
        pc_area_m2          = 0.0
        pc_ch4_m3_day       = 0.0
        pc_chp_kwh_day      = 0.0
        pc_methanol_kg_day  = 0.0
        need_supplemental_c = False

        if inputs.include_primary_clarifier:
            pc_r               = inputs.primary_clarifier_bod_removal_pct
            pc_sludge_kgds_day = flow * inf["tss_mg_l"] * 0.55 / 1000.0
            bod_removed        = max(0.0, flow * (inf["bod_mg_l"] * (1 - pc_r) - eff_bod) / 1000.0)
            cod_after_pc       = inf["bod_mg_l"] * 2.0 * (1 - pc_r * 1.20)
            cod_tkn_ratio      = cod_after_pc / max(inf["tn_mg_l"], 1.0)
            need_supplemental_c = cod_tkn_ratio < 10.0
            if need_supplemental_c:
                pc_methanol_kg_day = flow * max(0.0, 10.0 * inf["tn_mg_l"] - cod_after_pc) / 1000.0 / 1.5
            pc_area_m2     = self._get_eng("peak_flow_factor", 2.5) * flow / 24.0 / 1.5
            pc_chp_kwh_day = pc_sludge_kgds_day * 0.80 * 0.60 * 0.35 * 10.0 * 0.35
            pc_ch4_m3_day  = pc_sludge_kgds_day * 0.80 * 0.60 * 0.35
            r.notes.add_assumption(
                f"Primary clarifier: {pc_r*100:.0f}% BOD removal | "
                f"COD/TKN = {cod_tkn_ratio:.1f} | CHP = {pc_chp_kwh_day:.0f} kWh/day"
            )
            if need_supplemental_c:
                r.notes.warn(f"⚠️ COD/TKN={cod_tkn_ratio:.1f} — methanol {pc_methanol_kg_day:.0f} kg/day needed")

        r.notes.add_assumption(
            f"Influent: BOD {inf['bod_mg_l']:.0f}, TN {inf['tn_mg_l']:.0f}, "
            f"TP {inf['tp_mg_l']:.0f} mg/L at Q = {design_flow_mld:.1f} MLD"
        )

        # ── 2. MABR membrane area: sized for 30% of NH₄ load ─────────────
        # MABR in anoxic zone handles 30% of total NH₄ removal.
        # Membrane area sized from NH₄ surface loading rate (Syron & Casey 2008).
        nh4_load_kg     = flow * inf.get("nh4_mg_l", inf["tn_mg_l"] * 0.78) / 1000.0
        mabr_nh4_frac   = 0.30   # MABR handles 30% of NH₄ load in anoxic zone
        nh4_via_mabr    = nh4_load_kg * mabr_nh4_frac   # kg/day
        nh4_via_conv    = nh4_load_kg * (1 - mabr_nh4_frac)  # remaining 70% via aerobic blowers

        mabr_area_m2    = (nh4_via_mabr * 1000.0) / inputs.nh4_surface_loading_g_m2_day
        module_vol_m3   = mabr_area_m2 / inputs.membrane_specific_area_m2_per_m3

        r.notes.add_assumption(
            f"MABR handles {mabr_nh4_frac*100:.0f}% of NH₄ load in anoxic zone = "
            f"{nh4_via_mabr:.0f} kg/day | "
            f"Membrane area = {mabr_area_m2:,.0f} m² at {inputs.nh4_surface_loading_g_m2_day} g NH₄-N/m²/day"
        )

        # ── 3. Reactor sizing ──────────────────────────────────────────────
        # BNR biology at conventional MLSS; aerobic zone REDUCED BY 30%
        Y_true  = 0.60
        kd      = 0.08
        y_obs   = Y_true / (1.0 + kd * inputs.srt_days)
        vss_tss = 0.80

        vss_prod = y_obs * bod_removed
        tss_prod = vss_prod / vss_tss

        # Full BNR reactor volume (at conventional MLSS)
        reactor_m3  = (vss_prod * inputs.srt_days * 1000.0) / (inputs.mlss_mg_l * vss_tss)

        # Zone breakdown: aerobic zone REDUCED 30% because MABR handles 30% of nitrification
        aerobic_red   = 0.30   # aerobic zone reduction
        aerobic_frac  = 1.0 - inputs.anoxic_fraction - inputs.anaerobic_fraction
        v_anaerobic   = reactor_m3 * inputs.anaerobic_fraction
        v_anoxic      = reactor_m3 * inputs.anoxic_fraction + module_vol_m3  # anoxic zone + MABR modules
        v_aerobic     = reactor_m3 * aerobic_frac * (1 - aerobic_red)        # 30% smaller aerobic zone
        total_reactor = v_anaerobic + v_anoxic + v_aerobic

        r.notes.add_assumption(
            f"Reactor: anaerobic={v_anaerobic:.0f} m³, "
            f"anoxic+MABR modules={v_anoxic:.0f} m³, "
            f"aerobic (30% reduced)={v_aerobic:.0f} m³ | total={total_reactor:.0f} m³ "
            f"(vs BNR {reactor_m3:.0f} m³)"
        )

        # ── 4. Sludge production ───────────────────────────────────────────
        inorg_tss    = flow * inf["tss_mg_l"] * (1.0 - vss_tss) / 1000.0
        biofilm_shed = vss_prod * 0.10   # 10% extra from MABR biofilm shedding
        total_sludge = tss_prod + inorg_tss + biofilm_shed / vss_tss + pc_sludge_kgds_day

        r.sludge.biological_sludge_kgds_day = round(total_sludge, 1)
        r.sludge.vs_fraction = vss_tss
        r.sludge.feed_ts_pct = 1.5

        r.notes.add_assumption(
            f"y_obs = {y_obs:.3f} kgVSS/kgBOD; "
            "10% additional biofilm shedding from MABR membranes"
        )

        # ── 5. Energy ──────────────────────────────────────────────────────
        # MABR in ANOXIC zone: handles 30% of NH₄ at ~95% OTE (bubble-free)
        # Aerobic zone: conventional blowers for remaining 70% of NH₄ + full BOD removal
        # Aerobic zone is 30% smaller → 30% less aerobic blower energy for nitrification
        #
        # O₂ demand breakdown:
        #   Carbonaceous (aerobic zone, unchanged): O₂_BOD
        #   Nitrification via MABR (anoxic zone, 95% OTE): O₂_nit_MABR  
        #   Nitrification via blowers (aerobic zone, 30% reduction): O₂_nit_conv
        #   Denitrification credit (anoxic zone, unchanged): O₂_DN

        nh4_frac = inf.get("nh4_mg_l", inf["tn_mg_l"] * 0.78) / max(inf["tn_mg_l"], 1.0)
        o2_c     = bod_removed * 1.42 * (1.0 - 1.42 * y_obs)   # carbonaceous (aerobic)
        o2_n_tot = 4.57 * tn_load * nh4_frac * 0.90             # total nitrification O₂
        o2_n_mabr = o2_n_tot * mabr_nh4_frac                    # MABR handles 30%
        o2_n_conv = o2_n_tot * (1 - mabr_nh4_frac)              # blowers handle 70%
        o2_dn    = 2.86 * tn_removed * (inputs.anoxic_fraction / 0.35)  # DN credit

        # Aerobic blowers: carbonaceous O₂ + 70% of nitrification - DN credit
        o2_aer   = max(0.0, o2_c + o2_n_conv - o2_dn)
        sae_conv = self._get_eng("standard_aeration_efficiency_kg_o2_kwh", 1.8) * 0.55
        conv_aer_kwh = o2_aer / sae_conv

        # MABR gas supply: 30% of nitrification at 95% OTE
        ote_mabr     = inputs.o2_transfer_efficiency
        sae_mabr_eff = self._get_eng("standard_aeration_efficiency_kg_o2_kwh", 1.8) * (ote_mabr / 0.20)
        mabr_gas_kwh = o2_n_mabr / sae_mabr_eff

        mabr_aer_kwh = conv_aer_kwh + mabr_gas_kwh

        # Energy saving vs full BNR (no MABR)
        bnr_aer_kwh_equiv = (o2_c + o2_n_tot - o2_dn) / sae_conv
        energy_saving_pct = (1 - mabr_aer_kwh / bnr_aer_kwh_equiv) * 100

        # ── Anoxic/anaerobic zone mixing (ALL zones need mixers) ───────────
        mix_kwh = (v_anoxic + v_anaerobic) * 0.008 * 24.0   # 8 W/m³

        # ── Pumping: RAS + MLR + WAS + ancillary (same as BNR) ───────────
        pump_eff  = self._get_eng("pump_efficiency", 0.72)
        flow_m3s  = flow / 86400.0
        ras_kwh   = (1000 * 9.81 * flow_m3s * 1.0 * 3.0  / pump_eff) * 24.0 / 1000.0
        mlr_kwh   = (1000 * 9.81 * flow_m3s * 4.0 * 0.5  / pump_eff) * 24.0 / 1000.0
        was_kwh   = (1000 * 9.81 * flow_m3s * 0.01 * 10.0 / pump_eff) * 24.0 / 1000.0
        ancillary_kwh = 70.0 * design_flow_mld

        # Clarifier sizing
        peak_flow = flow * 2.5
        sor       = self._get_eng("secondary_clarifier_sor_m_hr", 1.0)
        clar_area = peak_flow / 24.0 / sor
        n_clar    = max(2, int(clar_area / 500) + 1)

        r.energy.aeration_kwh_day = round(mabr_aer_kwh, 1)
        r.energy.mixing_kwh_day   = round(mix_kwh, 1)
        r.energy.pumping_kwh_day   = round(ras_kwh + mlr_kwh + was_kwh + ancillary_kwh, 1)
        r.energy.generation_kwh_day = round(pc_chp_kwh_day, 1)

        r.notes.add_assumption(
            f"Aerobic blowers (70% NH₄ + BOD): O₂={o2_aer:.0f} kg/day → {conv_aer_kwh:.0f} kWh/day | "
            f"MABR gas (30% NH₄ at OTE {ote_mabr*100:.0f}%): O₂={o2_n_mabr:.0f} kg/day → {mabr_gas_kwh:.0f} kWh/day | "
            f"Total aeration saving vs BNR: {energy_saving_pct:.0f}%"
        )
        r.notes.add_assumption(
            f"Pumping (same as BNR): RAS={ras_kwh:.0f} + MLR(4×Q)={mlr_kwh:.0f} + "
            f"WAS={was_kwh:.0f} + ancillary={ancillary_kwh:.0f} kWh/day"
        )

        # ── 6. Effluent quality ────────────────────────────────────────────
        r.performance.effluent_bod_mg_l = eff_bod
        r.performance.effluent_tss_mg_l = eff_tss
        r.performance.effluent_nh4_mg_l = eff_nh4
        r.performance.effluent_tn_mg_l  = eff_tn
        r.performance.effluent_tp_mg_l  = eff_tp if inputs.chemical_p_removal else min(eff_tp + 0.2, 0.7)

        # Footprint: total reactor (30% smaller aerobic zone) + clarifiers
        # MABR modules sit within the existing anoxic zone — no added footprint
        total_footprint = total_reactor / 4.5 + clar_area

        r.performance.reactor_volume_m3           = round(total_reactor, 0)
        r.performance.hydraulic_retention_time_hr = round(total_reactor / flow * 24, 1)
        r.performance.footprint_m2 = round(total_footprint, 0)

        r.performance.additional.update({
            "mabr_membrane_area_m2":      round(mabr_area_m2, 0),
            "mabr_module_volume_m3":      round(module_vol_m3, 0),
            "mabr_nh4_fraction_pct":      round(mabr_nh4_frac * 100, 0),
            "nh4_loading_g_m2_day":       inputs.nh4_surface_loading_g_m2_day,
            "o2_demand_kg_day":           round(o2_aer + o2_n_mabr, 0),
            "aeration_energy_saving_pct": round(energy_saving_pct, 0),
            "aerobic_zone_reduction_pct": round(aerobic_red * 100, 0),
            "clarifier_area_m2":          round(clar_area, 0),
            "n_clarifiers":               n_clar,
            "v_anaerobic_m3":             round(v_anaerobic, 0),
            "v_anoxic_m3":                round(v_anoxic, 0),
            "v_aerobic_reduced_m3":       round(v_aerobic, 0),
            "kwh_per_kg_nh4_removed":     round(mabr_aer_kwh / max(nh4_load_kg * 0.90, 0.001), 1),
            "mode":                       inputs.mode,
        })

        # ── 7. Scope 1 ─────────────────────────────────────────────────────
        n2o_ef  = self._get_eng("n2o_emission_factor_g_n2o_per_g_n_removed", 0.016)
        n2o_gwp = self._get_eng("n2o_gwp", 273)
        r.carbon.n2o_biological_tco2e_yr = round(
            tn_removed * n2o_ef * 365 * n2o_gwp / 1000.0, 1
        )
        r.notes.add_assumption(
            f"N₂O EF = {n2o_ef} kg N₂O/kg N removed (IPCC 2019 Tier 1)"
        )

        # ── 8. Risk ────────────────────────────────────────────────────────
        r.risk.reliability_risk       = "Moderate"    # Emerging — limited full-scale data
        r.risk.regulatory_risk        = "Low"
        r.risk.technology_maturity    = "Commercial"  # ~50 full-scale plants (2024)
        r.risk.operational_complexity = "Moderate"    # Gas supply management + membrane maintenance
        r.risk.site_constraint_risk   = "Low" if inputs.mode == "retrofit" else "Moderate"
        r.risk.implementation_risk    = "Moderate"    # Limited vendor base

        r.risk.additional_flags["vendor_concentration_risk"] = "Moderate"
        r.risk.additional_flags["membrane_fouling_risk"]      = "Low"  # Low pressure gas, lower fouling than liquid MBR
        r.risk.additional_flags["long_term_opex_uncertainty"] = "Moderate"  # Membrane replacement not well characterised

        # ── 9. Warnings ───────────────────────────────────────────────────
        r.notes.add_limitation(
            "MABR is an emerging technology with fewer than 50 full-scale municipal "
            "plants globally (2024). Long-term membrane replacement costs are not yet "
            "well characterised — budget 15–25% contingency on membrane OPEX."
        )
        r.notes.add_limitation(
            "MABR does NOT replace secondary clarifiers. Footprint includes clarifiers. "
            "For clarifier-free operation, use MBR or BNR+MBR hybrid."
        )
        if inputs.mode == "retrofit":
            r.notes.warn(
                "MABR retrofit: existing blower infrastructure is replaced by a "
                "low-pressure gas supply system. Structural assessment of existing "
                "basin required to confirm module attachment points and weight loading."
            )
        if inputs.use_pure_oxygen:
            r.notes.warn(
                "Pure O₂ supply requires on-site generation (VPSA/PSA) or bulk liquid "
                "O₂ delivery. Significant CAPEX and safety management requirements."
            )

        # ── 10. Chemical consumption ───────────────────────────────────────
        chems: Dict[str, float] = {}
        if inputs.chemical_p_removal:
            p_mol = tp_removed * 1000.0 / 31.0
            chems["ferric_chloride_kg_day"] = round(p_mol * 2.5 * 162.2 / 1000.0, 2)
        r.chemical_consumption = chems

        # ── 11. CAPEX ─────────────────────────────────────────────────────
        mabr_unit_rate = 65.0    # $/m² membrane installed (GE/Ovivo ZeeNon 2015 indicative; ±40%)
        # Comparable to MBR cassettes but gas-side rather than liquid-side

        r.capex_items = []
        if inputs.include_primary_clarifier:
            r.capex_items.append(CostItem(
                "Primary clarifier",
                "secondary_clarifier_per_m2",
                pc_area_m2,
                "m²",
                notes=f"Primary clarifier: {inputs.primary_clarifier_bod_removal_pct*100:.0f}% BOD removal; primary sludge to AD",
            ))
        r.capex_items += [
            CostItem(
                "MABR membrane modules",
                "mabr_membrane_per_m2",
                mabr_area_m2,
                "m² membrane area",
                unit_cost_override=mabr_unit_rate,
                notes="Hollow-fibre MABR modules incl. gas distribution manifolds (indicative ±40%)",
            ),
            CostItem(
                "Low-pressure gas supply system",
                "blower_per_kw",
                mabr_aer_kwh / 24.0 * 0.3,   # ~30% of equivalent diffused air blower kW
                "kW installed",
                notes="Low-pressure blower/compressor for MABR gas supply (10–20 kPa vs 60–80 kPa diffused air)",
            ),
        ]
        if inputs.mode == "new_build":
            # New-build: full BNR tankage (30% smaller aerobic zone) + clarifiers
            r.capex_items.insert(0, CostItem(
                "BNR bioreactor tankage (anaerobic + anoxic + reduced aerobic zone)",
                "aeration_tank_per_m3",
                total_reactor,
                "m³",
                notes=f"Aerobic zone reduced 30% ({v_aerobic:.0f} m³ vs standard {reactor_m3 * aerobic_frac:.0f} m³); MABR modules in anoxic zone",
            ))
            r.capex_items.append(CostItem(
                "Conventional aeration blowers (70% of standard BNR capacity)",
                "blower_per_kw",
                conv_aer_kwh / 24.0,
                "kW installed",
                notes="Sized for reduced aerobic zone O₂ demand (30% NH₄ handled by MABR)",
            ))
            r.capex_items.append(CostItem(
                "Secondary clarifiers",
                "secondary_clarifier_per_m2",
                clar_area,
                "m²",
                notes=f"{n_clar} clarifiers — MABR in anoxic zone does not replace clarification",
            ))
        else:
            # Retrofit: MABR modules into existing anoxic zone, decommission 30% of blowers
            r.capex_items.append(CostItem(
                "Anoxic zone MABR retrofit (structural + gas distribution)",
                "concrete_tank_per_m3",
                module_vol_m3 * 0.20,
                "m³ equivalent civil works",
                notes="MABR module attachment points, low-pressure gas headers, control upgrades in anoxic zone",
            ))

        # ── 12. OPEX ──────────────────────────────────────────────────────
        r.opex_items = [
            CostItem("Electricity — conventional aeration (blowers)", "electricity_per_kwh",
                     conv_aer_kwh, "kWh/day",
                     notes=f"Conventional aerobic blowers — {(1-mabr_nh4_frac)*100:.0f}% of nit. O₂ + all carbonaceous O₂"),
            CostItem("Electricity — MABR low-pressure gas supply", "electricity_per_kwh",
                     mabr_gas_kwh, "kWh/day",
                     notes=f"MABR in anoxic zone — {mabr_nh4_frac*100:.0f}% of nitrification O₂ at OTE {ote_mabr*100:.0f}%; aeration saving {energy_saving_pct:.0f}% vs BNR"),
            CostItem("Electricity — mixing, RAS/MLR/WAS & ancillary", "electricity_per_kwh",
                     mix_kwh + ras_kwh + mlr_kwh + was_kwh + ancillary_kwh, "kWh/day",
                     notes="Anoxic/anaerobic mixing + RAS + MLR(4×Q) + WAS + plant ancillary — same as BNR"),
            CostItem("MABR membrane replacement (annualised)",
                     "mabr_membrane_per_m2",
                     mabr_area_m2 * 0.04 / 365.0,   # ~4%/yr indicative (gas-side, much lower fouling than liquid MBR)
                     "m²/day",
                     unit_cost_override=mabr_unit_rate,
                     notes="Indicative 4%/yr replacement (gas-side membranes foul less than liquid MBR — allow ±50%)"),
            CostItem("Sludge disposal", "sludge_disposal_per_tds", total_sludge / 1000.0, "t DS/day"),
        ]
        if inputs.chemical_p_removal and "ferric_chloride_kg_day" in chems:
            r.opex_items.append(CostItem("Ferric chloride (P removal)", "ferric_chloride_per_kg",
                                         chems["ferric_chloride_kg_day"], "kg/day"))
        if inputs.include_primary_clarifier and need_supplemental_c and pc_methanol_kg_day > 0:
            r.opex_items.append(CostItem("Methanol (post-primary clarifier)", "methanol_per_kg",
                                         pc_methanol_kg_day, "kg/day",
                                         notes="Supplemental carbon to raise COD/TKN to 10"))
        if inputs.include_primary_clarifier and pc_chp_kwh_day > 0:
            r.opex_items.append(CostItem("Primary sludge CHP electricity credit", "electricity_per_kwh",
                                         -pc_chp_kwh_day, "kWh/day",
                                         notes=f"CHP from primary sludge AD: {pc_ch4_m3_day:.0f} m³ CH4/day"))

        # ── 13. Assumptions log ───────────────────────────────────────────
        r.assumptions_used = {
            "mode":                              inputs.mode,
            "nh4_surface_loading_g_m2_day":      inputs.nh4_surface_loading_g_m2_day,
            "o2_transfer_efficiency":            inputs.o2_transfer_efficiency,
            "sae_mabr_kg_o2_kwh":                round(sae_mabr_eff, 1),
            "aeration_energy_saving_pct":        round(energy_saving_pct, 0),
            "y_obs_kgvss_kgbod":                 round(y_obs, 3),
            "n2o_ef":                            n2o_ef,
            "membrane_specific_area_m2_per_m3":  inputs.membrane_specific_area_m2_per_m3,
        }

        # ── 14. Finalise ──────────────────────────────────────────────────
        return r.finalise(
            design_flow_mld,
            influent_bod_mg_l=inf["bod_mg_l"],
            influent_nh4_mg_l=inf["tn_mg_l"] * nh4_frac,
            influent_tn_mg_l=inf["tn_mg_l"],
            influent_tp_mg_l=inf["tp_mg_l"],
        )
