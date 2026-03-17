"""
domains/wastewater/technologies/bnr.py

Conventional Biological Nutrient Removal (BNR)
================================================
Activated sludge process with biological nitrogen and phosphorus removal.
Screening-level concept design model for planning and scenario comparison.

Supported configurations: a2o | bardenpho | uct | jdh

Design basis
------------
• Sludge yield:     y_obs = Y_true / (1 + kd × SRT)   [Metcalf & Eddy Eq. 7-57]
• Oxygen demand:    carbonaceous + nitrification − denitrification credit
• Aeration energy:  O2 demand / (SAE_clean × alpha)
• CAPEX:            unit costs per m³ reactor + m² clarifier
• Scope 1 carbon:   IPCC 2019 Tier 1 N2O + CH4 emission factors

References
----------
  - Metcalf & Eddy (2014) Wastewater Engineering, 5th ed. Chapters 7–9
  - WEF MOP 32 (2010) Nutrient Removal
  - IPCC (2019) Refinement Vol.5 Chapter 6 — N2O and CH4 from WWTP
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Type

from domains.wastewater.technologies.base_technology import (
    BaseTechnology, CostItem, TechnologyResult,
)


@dataclass
class BNRInputs:
    """Design parameters for the Conventional BNR process."""

    process_configuration: str = "a2o"
    # "a2o" | "bardenpho" | "uct" | "jdh"

    srt_days: float = 12.0
    # Sludge retention time (days). Range: 8–20 for combined N+P removal.

    mlss_mg_l: float = 4000.0
    # Mixed liquor suspended solids (mg/L). Typical: 3000–5000.

    do_aerobic_mg_l: float = 2.0
    # DO setpoint in aerobic zone. Typical: 1.5–3.0 mg/L.

    design_temperature_celsius: float = 20.0
    # Biological basin temperature (°C). Used for Arrhenius correction.

    anaerobic_fraction: float = 0.10
    anoxic_fraction:    float = 0.30
    aerobic_fraction:   float = 0.60
    # Zone fractions must sum to 1.0.

    supplemental_carbon: bool = False
    carbon_source: str = "methanol"

    # ── Primary clarifier option ───────────────────────────────────────────
    include_primary_clarifier: bool = False
    # Primary clarifier upstream of the bioreactor.
    # Purpose: redirect ~35% BOD as primary sludge to AD for biogas uplift,
    # reduce bioreactor O₂ demand, and reduce secondary sludge production.
    # Trade-off: reduces BOD available for denitrification. At BOD/TN < 3.5
    # supplemental carbon (methanol/VFA) may be needed.
    # Typical primary clarifier SOR: 1.2–2.0 m/hr. BOD removal: 25–40%.
    primary_clarifier_bod_removal_pct: float = 0.35  # 35% BOD removal in PC

    chemical_p_removal: bool = False
    coagulant: str = "ferric_chloride"  # "ferric_chloride" | "alum"

    secondary_clarifier_svi_ml_g:    float = 120.0
    clarifier_overflow_rate_m_hr:    float = 1.5

    _field_bounds: dict = field(default_factory=lambda: {
        "srt_days":     (6, 30), "mlss_mg_l": (2000, 8000),
        "do_aerobic_mg_l": (0.5, 4.0), "design_temperature_celsius": (10, 35),
    }, repr=False)


class BNRTechnology(BaseTechnology):
    """
    Conventional BNR (activated sludge) — screening-level planning model.

    Advantages: proven technology, moderate CAPEX, broad applicability.
    Limitations: secondary clarifiers required, BioP reliability in industrial catchments.
    """

    @property
    def technology_code(self) -> str:
        return "bnr"

    @property
    def technology_name(self) -> str:
        return "Conventional BNR (Activated Sludge)"

    @property
    def technology_category(self) -> str:
        return "Biological Treatment"

    @classmethod
    def input_class(cls) -> Type:
        return BNRInputs

    def calculate(self, design_flow_mld: float, inputs: BNRInputs) -> TechnologyResult:
        r = TechnologyResult(
            technology_name=self.technology_name,
            technology_code=self.technology_code,
            technology_category=self.technology_category,
            description=(
                f"Activated sludge BNR ({inputs.process_configuration.upper()}) "
                "removing BOD, N, and P."
            ),
        )
        flow = design_flow_mld * 1000.0  # m³/day

        # ── Temperature: prefer scenario value injected via engineering_assumptions ──
        # WastewaterInputs.influent_temperature_celsius → engineering_assumptions
        # BNRInputs.design_temperature_celsius is a per-run override (defaults to 20°C)
        # If the user hasn't explicitly set BNRInputs.design_temperature_celsius,
        # inherit from the scenario's influent temperature.
        import dataclasses
        _default_T = next(
            f.default for f in dataclasses.fields(BNRInputs)
            if f.name == "design_temperature_celsius"
        )
        if inputs.design_temperature_celsius == _default_T:
            # Not explicitly overridden — inherit from scenario
            scenario_T = self._get_eng("influent_temperature_celsius", _default_T)
            import dataclasses as _dc
            inputs = _dc.replace(inputs, design_temperature_celsius=scenario_T)

        # ── 1. Influent loads ──────────────────────────────────────────────
        inf = self._load_influent()
        bod_load   = flow * inf["bod_mg_l"] / 1000.0   # kg/day
        tn_load    = flow * inf["tn_mg_l"]  / 1000.0
        tp_load    = flow * inf["tp_mg_l"]  / 1000.0
        tss_load   = flow * inf["tss_mg_l"] / 1000.0

        r.notes.add_assumption(
            f"Influent: BOD {inf['bod_mg_l']:.0f}, TN {inf['tn_mg_l']:.0f}, "
            f"TP {inf['tp_mg_l']:.0f}, TSS {inf['tss_mg_l']:.0f} mg/L"
        )

        # ── 2. Effluent targets ────────────────────────────────────────────
        eff_tn  = self._get_eng("effluent_tn_mg_l",  10.0)
        eff_tp  = self._get_eng("effluent_tp_mg_l",   0.5)
        eff_nh4 = self._get_eng("effluent_nh4_mg_l",  1.0)
        eff_bod = self._get_eng("effluent_bod_mg_l", 10.0)
        eff_tss = self._get_eng("effluent_tss_mg_l", 10.0)

        tn_removed   = max(0.0, flow * (inf["tn_mg_l"]  - eff_tn)  / 1000.0)
        tp_removed   = max(0.0, flow * (inf["tp_mg_l"]  - eff_tp)  / 1000.0)
        bod_removed  = max(0.0, flow * (inf["bod_mg_l"] - eff_bod) / 1000.0)

        # ── 2b. Primary clarifier (optional) ──────────────────────────────
        pc_bod_removal_kg    = 0.0
        pc_tss_removal_kg    = 0.0
        pc_sludge_kgds_day   = 0.0
        pc_area_m2           = 0.0
        need_supplemental_c  = False
        pc_ch4_m3_day        = 0.0    # methane from primary sludge AD
        pc_chp_kwh_day       = 0.0    # CHP electricity credit from primary sludge
        pc_methanol_kg_day   = 0.0    # supplemental carbon if C:N too low
        cod_tkn_ratio        = inf["bod_mg_l"] * 2.0 / max(inf["tn_mg_l"], 1.0)  # rough COD from BOD

        if inputs.include_primary_clarifier:
            pc_r     = inputs.primary_clarifier_bod_removal_pct
            pc_tss_r = 0.55    # 55% TSS removal — typical primary clarifier
            pc_cod_r = pc_r * 1.20  # COD removal slightly higher than BOD (settleables)

            # ── Loads removed in primary clarifier ─────────────────────────
            pc_bod_removal_kg  = flow * inf["bod_mg_l"] * pc_r     / 1000.0
            pc_tss_removal_kg  = flow * inf["tss_mg_l"] * pc_tss_r / 1000.0
            pc_sludge_kgds_day = pc_tss_removal_kg

            # ── Bioreactor influent after primary clarifier ─────────────────
            bod_after_pc = inf["bod_mg_l"] * (1 - pc_r)
            cod_after_pc = inf["bod_mg_l"] * 2.0 * (1 - pc_cod_r)   # COD from BOD×2
            bod_removed  = max(0.0, flow * (bod_after_pc - eff_bod) / 1000.0)

            # ── COD:TKN check for enhanced TN removal ──────────────────────
            # WEF MOP 32 / Metcalf: COD/TKN > 10 for enhanced TN without external C
            # BOD/TKN > 4 minimum for basic denitrification
            # Use COD/TKN as the primary check (more rigorous)
            cod_tkn_ratio    = cod_after_pc / max(inf["tn_mg_l"], 1.0)
            bod_tkn_ratio    = bod_after_pc / max(inf["tn_mg_l"], 1.0)
            need_supplemental_c = cod_tkn_ratio < 10.0

            # ── Supplemental carbon demand ──────────────────────────────────
            # If COD/TKN < 10, calculate methanol needed to bridge the deficit
            # Methanol provides ~1.07 g COD/g methanol
            # Target: raise COD/TKN from current to 10
            if need_supplemental_c:
                cod_deficit_mg_l  = max(0.0, 10.0 * inf["tn_mg_l"] - cod_after_pc)
                cod_deficit_kg    = flow * cod_deficit_mg_l / 1000.0
                # Methanol (COD = 1.5 g/g): dose to provide deficit COD
                pc_methanol_kg_day = cod_deficit_kg / 1.5

            # ── Primary clarifier sizing ────────────────────────────────────
            sor_pc     = 1.5    # m/hr SOR at peak flow
            pc_area_m2 = flow * 2.5 / 24.0 / sor_pc

            # ── Primary sludge methane credit (AD assumed) ─────────────────
            # Primary sludge is high VS (0.80 VS/TS), readily digestible
            # Biogas yield: 0.35 m³ CH4/kg VS destroyed (Metcalf 2014 Table 17-10)
            # VS destruction: 60% for primary sludge in mesophilic AD
            # CHP electrical efficiency: 35%
            ps_vs_kg          = pc_sludge_kgds_day * 0.80
            vs_destruction    = 0.60
            ch4_yield_m3_kgvs = 0.35
            pc_ch4_m3_day     = ps_vs_kg * vs_destruction * ch4_yield_m3_kgvs
            ch4_energy_kwh_m3 = 10.0    # LHV: ~35.5 MJ/m³ ÷ 3.6 = ~9.9 kWh/m³
            chp_elec_eff      = 0.35
            pc_chp_kwh_day    = pc_ch4_m3_day * ch4_energy_kwh_m3 * chp_elec_eff

            r.notes.add_assumption(
                f"Primary clarifier: {pc_r*100:.0f}% BOD / {pc_tss_r*100:.0f}% TSS removal | "
                f"BOD to bioreactor = {bod_after_pc:.0f} mg/L | "
                f"COD/TKN = {cod_tkn_ratio:.1f} (threshold 10 for enhanced TN)"
            )
            r.notes.add_assumption(
                f"Primary sludge AD: {pc_sludge_kgds_day:.0f} kg DS/day × 0.80 VS × "
                f"60% destruction × 0.35 m³ CH4/kgVS = {pc_ch4_m3_day:.0f} m³ CH4/day | "
                f"CHP electricity credit = {pc_chp_kwh_day:.0f} kWh/day "
                f"({pc_chp_kwh_day/design_flow_mld/1000:.0f} kWh/ML)"
            )
            if need_supplemental_c:
                r.notes.warn(
                    f"⚠️ COD/TKN = {cod_tkn_ratio:.1f} after primary clarifier — below 10.0 threshold "
                    f"for enhanced TN removal without external carbon. "
                    f"Methanol dose required: ~{pc_methanol_kg_day:.0f} kg/day "
                    f"(to raise COD/TKN to 10). "
                    "Consider VFA recovery from primary sludge fermentation as a lower-cost alternative."
                )
            else:
                r.notes.add_assumption(
                    f"COD/TKN = {cod_tkn_ratio:.1f} — adequate for enhanced TN removal."
                )

        # y_obs = Y_true / (1 + kd_T × SRT)
        Y_true = 0.60     # kgVSS/kgBOD — Metcalf Table 7-15, domestic ww
        kd     = 0.08     # /day at 20°C — Metcalf Table 7-15
        kd_T   = kd * (1.04 ** (inputs.design_temperature_celsius - 20.0))
        y_obs  = Y_true / (1.0 + kd_T * inputs.srt_days)

        vss_to_tss   = self._get_eng("vss_to_tss_ratio", 0.80)
        vss_prod     = y_obs * bod_removed
        tss_prod     = vss_prod / vss_to_tss
        inorg_tss    = tss_load * (1.0 - vss_to_tss)
        total_sludge = tss_prod + inorg_tss + pc_sludge_kgds_day  # include primary sludge if applicable

        r.sludge.biological_sludge_kgds_day = round(total_sludge, 1)
        r.sludge.vs_fraction = vss_to_tss
        r.sludge.feed_ts_pct = 1.5  # Typical thickened WAS

        r.notes.add_assumption(
            f"y_obs = {y_obs:.3f} kgVSS/kgBOD "
            f"(Y=0.60, kd={kd_T:.3f}/day at {inputs.design_temperature_celsius}°C, "
            f"SRT={inputs.srt_days}d) — Metcalf Eq. 7-57"
        )

        # ── 4. Reactor sizing ──────────────────────────────────────────────
        # SRT adjustment for tight TN limits:
        # TN < 8 mg/L requires higher anoxic fraction (≥35%) and longer SRT.
        # TN < 5 mg/L: near-complete denitrification, SRT ≥ 15d often needed.
        # Ref: Metcalf 5th Ed Table 7-32; Tchobanoglous 2014 BNR design criteria.
        design_srt = inputs.srt_days
        anoxic_frac = inputs.anoxic_fraction
        if eff_tn < 8.0 and eff_tn >= 5.0:
            # Moderate TN target: increase anoxic fraction to 35%, SRT +20%
            anoxic_frac  = max(anoxic_frac, 0.35)
            design_srt   = max(design_srt, design_srt * 1.20)
        elif eff_tn < 5.0:
            # Tight TN target: substantial anoxic volume, SRT +40%, supplemental C likely
            anoxic_frac  = max(anoxic_frac, 0.40)
            design_srt   = max(design_srt, design_srt * 1.40)
            if not need_supplemental_c and cod_tkn_ratio < 10.0:
                r.notes.warn(
                    f"⚠️ TN target {eff_tn:.0f} mg/L with COD/TKN={cod_tkn_ratio:.1f} — "
                    "supplemental carbon (methanol) likely required for reliable compliance."
                )

        # Re-derive y_obs with adjusted SRT if changed
        if design_srt != inputs.srt_days:
            y_obs    = Y_true / (1.0 + kd_T * design_srt)
            vss_prod = y_obs * bod_removed
            tss_prod = vss_prod / vss_to_tss
            total_sludge = tss_prod + inorg_tss + pc_sludge_kgds_day
            r.sludge.biological_sludge_kgds_day = round(total_sludge, 1)
            r.notes.add_assumption(
                f"SRT extended to {design_srt:.1f}d (from {inputs.srt_days}d) "
                f"for TN target {eff_tn:.0f} mg/L — Metcalf Table 7-32"
            )

        reactor_m3 = (vss_prod * design_srt * 1000.0) / (inputs.mlss_mg_l * vss_to_tss)
        aerobic_frac = max(0.0, 1.0 - inputs.anaerobic_fraction - anoxic_frac)
        v_an = reactor_m3 * inputs.anaerobic_fraction
        v_ax = reactor_m3 * anoxic_frac
        v_ae = reactor_m3 * aerobic_frac
        hrt  = reactor_m3 / flow * 24.0

        r.performance.reactor_volume_m3          = round(reactor_m3, 0)
        r.performance.hydraulic_retention_time_hr = round(hrt, 1)
        r.performance.additional.update({
            "v_anaerobic_m3": round(v_an, 0), "v_anoxic_m3": round(v_ax, 0),
            "v_aerobic_m3":   round(v_ae, 0),
        })

        # ── 5. Oxygen demand ───────────────────────────────────────────────
        o2_c  = bod_removed * 1.42 * (1.0 - 1.42 * y_obs)   # carbonaceous
        nh4_frac = self._get_eng("influent_nh4_mg_l", 35.0) / max(inf["tn_mg_l"], 1.0)
        o2_n  = 4.57 * tn_load * nh4_frac * 0.90             # nitrification (90%)
        no3_dn = tn_removed * 0.70                            # 70% via denitrification
        o2_dn = 2.86 * no3_dn                                 # credit
        o2_kg_day = max(0.0, o2_c + o2_n - o2_dn)

        r.performance.additional["o2_demand_kg_day"] = round(o2_kg_day, 0)

        # ── 6. Energy ──────────────────────────────────────────────────────
        alpha    = self._get_eng("alpha_factor", 0.55)
        sae_std  = self._get_eng("standard_aeration_efficiency_kg_o2_kwh", 1.8)
        sae_proc = sae_std * alpha
        aer_kwh  = o2_kg_day / sae_proc
        mix_kwh  = (v_an + v_ax) * 0.007 * 24.0  # 7 W/m³ mixing
        pump_eff = self._get_eng("pump_efficiency", 0.72)
        flow_m3s = flow / 86400.0

        # ── Explicit pumping and ancillary breakdown ──────────────────────
        # RAS (return activated sludge): 1.0×Q at 3m total dynamic head
        ras_kwh  = (1000 * 9.81 * flow_m3s * 1.0 * 3.0 / pump_eff) * 24.0 / 1000.0

        # MLR (mixed liquor recycle, nitrate recycle): 4×Q at 0.5m head
        # 4×Q provides ~80% denitrification efficiency (WEF MOP 35)
        mlr_kwh  = (1000 * 9.81 * flow_m3s * 4.0 * 0.5 / pump_eff) * 24.0 / 1000.0

        # WAS (waste activated sludge): 0.01×Q at 10m head (to thickener)
        was_kwh  = (1000 * 9.81 * flow_m3s * 0.01 * 10.0 / pump_eff) * 24.0 / 1000.0

        # Ancillary (screening, UV, SCADA, sludge handling, misc): 70 kWh/ML
        ancillary_kwh = 70.0 * design_flow_mld

        r.energy.aeration_kwh_day   = round(aer_kwh, 1)
        r.energy.mixing_kwh_day     = round(mix_kwh, 1)
        r.energy.pumping_kwh_day    = round(ras_kwh + mlr_kwh + was_kwh + ancillary_kwh, 1)
        # Primary sludge CHP credit (if primary clarifier enabled)
        r.energy.generation_kwh_day = round(pc_chp_kwh_day, 1)

        r.notes.add_assumption(
            f"Pumping: RAS={ras_kwh:.0f} + MLR(4×Q)={mlr_kwh:.0f} + WAS={was_kwh:.0f} "
            f"+ ancillary={ancillary_kwh:.0f} kWh/day total={ras_kwh+mlr_kwh+was_kwh+ancillary_kwh:.0f}"
        )

        nh4_removed = max(0.001, flow * (inf["tn_mg_l"] * nh4_frac - eff_nh4) / 1000.0)
        r.performance.additional["kwh_per_kg_nh4_removed"] = round(aer_kwh / nh4_removed, 1)

        r.notes.add_assumption(
            f"alpha = {alpha} (municipal fine-bubble, Metcalf Table 5-8), "
            f"SAE_clean = {sae_std} kg O₂/kWh → SAE_process = {sae_proc:.2f}"
        )

        # ── 7. Chemicals ───────────────────────────────────────────────────
        chems: Dict[str, float] = {}
        if inputs.supplemental_carbon:
            chems["methanol_kg_day"] = round(no3_dn * 4.0 * 0.30, 2)
            r.notes.add_assumption("Methanol dose: 4 kg/kg NO3-N (WEF MOP 32 Table 7-5)")
        # Auto-add methanol if primary clarifier drops COD/TKN below 10
        if inputs.include_primary_clarifier and need_supplemental_c and pc_methanol_kg_day > 0:
            existing = chems.get("methanol_kg_day", 0.0)
            chems["methanol_kg_day"] = round(max(existing, pc_methanol_kg_day), 2)
            r.notes.add_assumption(
                f"Methanol post-primary clarifier: {pc_methanol_kg_day:.0f} kg/day "
                f"to raise COD/TKN from {cod_tkn_ratio:.1f} to 10.0 "
                f"(VFA from primary sludge fermentation is a lower-cost alternative)"
            )
        if inputs.chemical_p_removal:
            p_mol = tp_removed * 1000.0 / 31.0
            chems["ferric_chloride_kg_day"] = round(p_mol * 2.5 * 162.2 / 1000.0, 2)
            r.notes.add_assumption("FeCl3 dose: 2.5 mol Fe/mol P (WEF MOP 32)")
        r.chemical_consumption = chems

        # ── 8. Clarifier + footprint ───────────────────────────────────────
        # Use scenario peak flow factor (injected from WastewaterInputs)
        # Peak flow drives clarifier area — the primary hydraulic constraint.
        peak_factor = self._get_eng("peak_flow_factor", 2.5)
        peak_m3hr   = flow * peak_factor / 24.0
        clar_area   = peak_m3hr / inputs.clarifier_overflow_rate_m_hr
        n_clar      = max(2, int(clar_area / 900) + 1)
        r.performance.footprint_m2 = round(reactor_m3 / 4.5 + clar_area, 0)

        # Peak hydraulic HRT check — at peak flow, reactor HRT must remain
        # sufficient for biological treatment (minimum ~2 hr for BNR).
        # Ref: Metcalf 5th Ed, Table 7-20 — minimum HRT at peak flow.
        peak_flow_m3d  = flow * peak_factor
        peak_hrt_hr    = reactor_m3 / peak_flow_m3d * 24.0
        if peak_hrt_hr < 2.0:
            r.notes.warn(
                f"⚠️ At peak flow ({peak_factor:.1f}× = {peak_flow_m3d:.0f} m³/d), "
                f"reactor HRT = {peak_hrt_hr:.1f} hr — below 2 hr minimum for BNR. "
                "Consider increasing reactor volume or peak flow attenuation."
            )
        elif peak_hrt_hr < 3.0:
            r.notes.add_assumption(
                f"Peak HRT = {peak_hrt_hr:.1f} hr at {peak_factor:.1f}× peak — "
                "marginal; confirm with hydraulic modelling."
            )

        r.notes.add_assumption(
            f"Clarifier sized at peak flow factor {peak_factor:.1f}× "
            f"(SOR={inputs.clarifier_overflow_rate_m_hr} m/hr at peak)"
        )
        r.performance.additional.update({
            "clarifier_area_m2": round(clar_area, 0),
            "n_clarifiers": n_clar,
            "peak_flow_factor": peak_factor,
            "peak_hrt_hr": round(peak_hrt_hr, 1),
        })

        # ── 9. Effluent quality ────────────────────────────────────────────
        # Effluent NH4 degrades at low temperature and short SRT.
        # At T < 15°C nitrification kinetics slow — Metcalf Fig 7-42.
        # At T < 12°C or SRT < 10d, reliable nitrification is marginal.
        T = inputs.design_temperature_celsius
        if T < 12.0 or design_srt < 8.0:
            # Poor nitrification — NH4 may not meet target
            eff_nh4_actual = min(eff_nh4 * 4.0, inf["tn_mg_l"] * nh4_frac * 0.6)
            r.notes.warn(
                f"⚠️ T={T}°C, SRT={design_srt:.1f}d — nitrification unreliable. "
                f"Modelled effluent NH4 = {eff_nh4_actual:.1f} mg/L (target {eff_nh4:.1f} mg/L). "
                "Consider IFAS, MABR, or longer SRT."
            )
        elif T < 15.0:
            # Marginal nitrification — NH4 may be 2-3× target
            eff_nh4_actual = min(eff_nh4 * 2.0, inf["tn_mg_l"] * nh4_frac * 0.4)
            r.notes.warn(
                f"⚠️ T={T}°C — nitrification marginal. "
                f"Modelled effluent NH4 = {eff_nh4_actual:.1f} mg/L (target {eff_nh4:.1f} mg/L). "
                "Confirm SRT adequacy with detailed design."
            )
        else:
            eff_nh4_actual = eff_nh4  # full nitrification achievable

        # ── Effluent TN: carbon-availability constraint ───────────────
        # The target eff_tn is only achievable if sufficient BOD is available
        # for denitrification. Minimum COD/TKN thresholds (Metcalf Table 7-32,
        # WEF MOP 32 Section 7.4):
        #   COD/TKN < 4.5  → very limited DN, achievable TN ≈ TKN × 0.60
        #   COD/TKN 4.5-7  → partial DN,       achievable TN ≈ TKN × 0.40
        #   COD/TKN 7-10   → good DN,           achievable TN ≈ TKN × 0.25
        #   COD/TKN > 10   → enhanced DN, TN target achievable without external C
        # With supplemental carbon, TN target is achievable regardless of ratio.
        if inputs.supplemental_carbon:
            eff_tn_actual = eff_tn   # external C overcomes limitation
        else:
            if cod_tkn_ratio < 4.5:
                eff_tn_actual = max(eff_tn, inf["tn_mg_l"] * 0.60)
                r.notes.warn(
                    f"⚠️ COD/TKN = {cod_tkn_ratio:.1f} — severely carbon-limited. "
                    f"Achievable TN ≈ {eff_tn_actual:.1f} mg/L (target {eff_tn:.1f}). "
                    "Supplemental carbon (methanol) required to meet TN target. "
                    "Ref: Metcalf 5th Ed Table 7-32."
                )
            elif cod_tkn_ratio < 7.0:
                eff_tn_actual = max(eff_tn, inf["tn_mg_l"] * 0.40)
                r.notes.warn(
                    f"⚠️ COD/TKN = {cod_tkn_ratio:.1f} — carbon-limited denitrification. "
                    f"Achievable TN ≈ {eff_tn_actual:.1f} mg/L (target {eff_tn:.1f}). "
                    "Consider supplemental carbon or primary sludge fermentation."
                )
            elif cod_tkn_ratio < 10.0:
                eff_tn_actual = max(eff_tn, inf["tn_mg_l"] * 0.25)
                if eff_tn_actual > eff_tn:
                    r.notes.warn(
                        f"⚠️ COD/TKN = {cod_tkn_ratio:.1f} — marginal carbon availability. "
                        f"Achievable TN ≈ {eff_tn_actual:.1f} mg/L. "
                        "Increase anoxic fraction or add supplemental carbon for reliable compliance."
                    )
            else:
                eff_tn_actual = eff_tn   # adequate carbon — target achievable

        r.performance.effluent_bod_mg_l = eff_bod
        r.performance.effluent_tss_mg_l = eff_tss
        r.performance.effluent_nh4_mg_l = round(eff_nh4_actual, 2)
        r.performance.effluent_tn_mg_l  = round(eff_tn_actual, 2)
        r.performance.effluent_tp_mg_l  = eff_tp if inputs.chemical_p_removal else min(eff_tp + 0.3, 1.0)

        # ── 10. Scope 1 carbon ────────────────────────────────────────────
        n2o_ef  = self._get_eng("n2o_emission_factor_g_n2o_per_g_n_removed", 0.016)
        n2o_gwp = self._get_eng("n2o_gwp", 273)
        r.carbon.n2o_biological_tco2e_yr = round(tn_removed * n2o_ef * 365 * n2o_gwp / 1000.0, 1)

        ch4_ef  = self._get_eng("ch4_emission_factor_g_ch4_per_g_bod_influent", 0.0025)
        ch4_gwp = self._get_eng("ch4_gwp", 28)
        r.carbon.ch4_fugitive_tco2e_yr = round(bod_load * ch4_ef * 365 * ch4_gwp / 1000.0, 1)

        r.notes.add_assumption(
            f"N2O EF: {n2o_ef} kg N2O/kg N removed (IPCC 2019 Tier 1 central; range 0.005–0.05)"
        )
        r.notes.add_limitation(
            "N2O is the dominant carbon uncertainty (±3×). "
            "Site measurement recommended for detailed assessments."
        )

        # ── 11. Risk ──────────────────────────────────────────────────────
        r.risk.reliability_risk       = "Low"
        r.risk.regulatory_risk        = "Low"
        r.risk.technology_maturity    = "Established"
        r.risk.operational_complexity = "Moderate"
        r.risk.site_constraint_risk   = "Moderate"
        r.risk.implementation_risk    = "Low"
        if inputs.design_temperature_celsius < 15.0:
            r.risk.reliability_risk = "Moderate"
            r.notes.warn(f"Temperature {inputs.design_temperature_celsius}°C < 15°C may impair nitrification.")

        # ── 12. CAPEX / OPEX ──────────────────────────────────────────────
        r.capex_items = [
            CostItem("BNR reactor tankage", "aeration_tank_per_m3",
                     reactor_m3, "m³", notes="Includes baffles, mixers, diffusers"),
            CostItem("Secondary clarifiers", "secondary_clarifier_per_m2",
                     clar_area, "m²"),
            CostItem("Blower/aeration system", "blower_per_kw",
                     aer_kwh / 24.0, "kW installed"),
            CostItem("RAS/WAS pumps", "pump_per_kw",
                     ras_kwh / 24.0, "kW installed"),
        ]
        if inputs.include_primary_clarifier:
            r.capex_items.insert(0, CostItem(
                "Primary clarifier",
                "secondary_clarifier_per_m2",
                pc_area_m2,
                "m²",
                notes=f"Primary clarifier: {inputs.primary_clarifier_bod_removal_pct*100:.0f}% BOD removal, SOR=1.5 m/hr; primary sludge routed to AD",
            ))
            if need_supplemental_c and not inputs.supplemental_carbon:
                r.notes.warn(
                    "Supplemental carbon OPEX not included but may be required — "
                    "enable Supplemental carbon in BNR configuration if BOD/TN < 4.0."
                )

        r.opex_items = [
            CostItem("Electricity — aeration",       "electricity_per_kwh", aer_kwh,  "kWh/day"),
            CostItem("Electricity — mixing & RAS/MLR","electricity_per_kwh", mix_kwh + ras_kwh + mlr_kwh + was_kwh + ancillary_kwh, "kWh/day",
                     notes="Anoxic/anaerobic mixing + RAS + MLR (4×Q) + WAS + ancillary"),
            CostItem("Sludge disposal",            "sludge_disposal_per_tds",
                     total_sludge / 1000.0, "t DS/day"),
        ]
        if "methanol_kg_day" in chems:
            r.opex_items.append(CostItem("Methanol (supplemental carbon)", "methanol_per_kg",
                                         chems["methanol_kg_day"], "kg/day",
                                         notes="Post-primary clarifier dosing for TN removal" if inputs.include_primary_clarifier and need_supplemental_c else "Denitrification carbon source"))
        if inputs.chemical_p_removal and "ferric_chloride_kg_day" in chems:
            r.opex_items.append(CostItem("Ferric chloride", "ferric_chloride_per_kg",
                                         chems["ferric_chloride_kg_day"], "kg/day"))
        if inputs.include_primary_clarifier and pc_chp_kwh_day > 0:
            # CHP electricity credit reduces net electricity cost
            r.opex_items.append(CostItem(
                "Primary sludge CHP electricity credit",
                "electricity_per_kwh",
                -pc_chp_kwh_day,  # negative = credit
                "kWh/day",
                notes=f"CHP from primary sludge AD: {pc_ch4_m3_day:.0f} m³ CH4/day × 35% CHP efficiency"
            ))

        r.performance.additional.update({
            "include_primary_clarifier":   inputs.include_primary_clarifier,
            "primary_clarifier_area_m2":   round(pc_area_m2, 0) if inputs.include_primary_clarifier else 0,
            "primary_sludge_kgds_day":     round(pc_sludge_kgds_day, 1) if inputs.include_primary_clarifier else 0,
            "primary_sludge_ch4_m3_day":   round(pc_ch4_m3_day, 0) if inputs.include_primary_clarifier else 0,
            "primary_sludge_chp_kwh_day":  round(pc_chp_kwh_day, 0) if inputs.include_primary_clarifier else 0,
            "cod_tkn_ratio_to_bioreactor": round(cod_tkn_ratio, 1) if inputs.include_primary_clarifier else round(inf["bod_mg_l"]*2.0/max(inf["tn_mg_l"],1), 1),
            "need_supplemental_carbon":    need_supplemental_c,
            "methanol_post_pc_kg_day":     round(pc_methanol_kg_day, 0) if (inputs.include_primary_clarifier and need_supplemental_c) else 0,
        })

        r.notes.add_limitation(
            "CAPEX excludes land, site works, headworks, sludge treatment, and contingency (+30-40%)."
        )

        # ── 13. Assumptions log ───────────────────────────────────────────
        r.assumptions_used = {
            "process_configuration": inputs.process_configuration,
            "srt_days": inputs.srt_days, "mlss_mg_l": inputs.mlss_mg_l,
            "y_obs": round(y_obs, 3), "alpha_factor": alpha,
            "sae_clean": sae_std, "sae_process": round(sae_proc, 2),
            "n2o_ef": n2o_ef, "temp_celsius": inputs.design_temperature_celsius,
        }

        # ── 14. Finalise (ALWAYS last) ────────────────────────────────────
        return r.finalise(
            design_flow_mld,
            influent_bod_mg_l=inf["bod_mg_l"],
            influent_nh4_mg_l=inf["tn_mg_l"] * nh4_frac,
            influent_tn_mg_l=inf["tn_mg_l"],
            influent_tp_mg_l=inf["tp_mg_l"],
        )
