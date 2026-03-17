"""
domains/wastewater/technologies/bnr_mbr.py

BNR + MBR Hybrid (Retrofit / Upgrade)
======================================
Existing conventional BNR basins (anoxic + aerobic) operated at moderate
MLSS (4,000–6,000 mg/L) feeding a separate downstream membrane separation
tank. The membrane tank operates at higher MLSS (8,000–12,000 mg/L) and
replaces the secondary clarifiers.

This configuration is distinct from a fully integrated MBR:
- The BNR basins retain their existing volume and geometry
- The membrane tank is a new-build addition
- Biology occurs primarily in the BNR basins at conventional MLSS
- Membranes provide final separation + polishing

Typical use case
----------------
A plant with existing conventional BNR wants to:
  a) Eliminate or reduce reliance on secondary clarifiers
  b) Improve effluent TSS and pathogen quality for reuse
  c) Increase hydraulic capacity without expanding the biological basins
  d) Achieve Class A+ reuse quality as a pre-step before RO

Design basis
------------
  BNR basins: conventional MLSS, existing HRT / reactor volume
  Membrane tank: separate vessel, MLSS 8,000–10,000 mg/L, submerged HF modules
  Membrane area: sized from design flux at the BNR effluent flow
  Sludge: single WAS stream from membrane tank (lower yield than pure MBR
          because biology is done at conventional SRT in the BNR zone)

References
----------
  - WEF MOP 36 (2012) Membrane Bioreactors
  - Judd (2011) The MBR Book, 2nd ed. — hybrid configurations Ch.5
  - Metcalf & Eddy (2014) Ch. 9
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, Type

from domains.wastewater.technologies.base_technology import (
    BaseTechnology, CostItem, TechnologyResult,
)


# ─────────────────────────────────────────────────────────────────────────────
# INPUTS
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class BNRMBRInputs:
    """Design parameters for the BNR + MBR hybrid configuration."""

    # ── BNR biological zone ────────────────────────────────────────────────
    srt_days: float = 12.0
    # SRT in the BNR zone (days). Conventional range 8–15d.

    mlss_bnr_mg_l: float = 4000.0
    # MLSS in the BNR basins (mg/L). Conventional: 3,000–5,000 mg/L.
    # Lower than pure integrated MBR because biology is decoupled from membrane.

    anoxic_fraction: float = 0.35
    # Fraction of BNR reactor as pre-anoxic zone (for TN removal).

    # ── Membrane separation tank ───────────────────────────────────────────
    design_flux_lmh: float = 20.0
    # Net design flux (L/m²/h). Conservative for hybrid: 15–25 LMH.
    # Lower than pure MBR because feed is already clarified secondary effluent.

    mlss_membrane_tank_mg_l: float = 8000.0
    # MLSS in the membrane tank (mg/L). 6,000–12,000.

    membrane_configuration: str = "hollow_fibre"
    # "hollow_fibre" | "flat_sheet"

    # ── Clarifier disposition ──────────────────────────────────────────────
    retain_one_clarifier: bool = True
    # Keep one secondary clarifier as standby/bypass during membrane maintenance.
    # True = one clarifier CAPEX included; False = no clarifier (full replacement).

    # ── Chemistry ─────────────────────────────────────────────────────────
    chemical_p_removal: bool = False
    # Usually not required — MBR effluent quality often good enough for TP < 0.5 mg/L
    # via enhanced bio-P in the BNR zone.

    _field_bounds: dict = field(default_factory=lambda: {
        "srt_days":                (5, 25),
        "mlss_bnr_mg_l":           (2000, 6000),
        "design_flux_lmh":         (10, 35),
        "mlss_membrane_tank_mg_l": (5000, 14000),
    }, repr=False)


# ─────────────────────────────────────────────────────────────────────────────
# TECHNOLOGY CLASS
# ─────────────────────────────────────────────────────────────────────────────

class BNRMBRTechnology(BaseTechnology):
    """
    BNR + MBR Hybrid — screening-level planning model.

    This models a genuine two-zone hybrid:
    - Zone 1: Conventional BNR basins (existing or new) at moderate MLSS
    - Zone 2: Separate membrane tank replacing secondary clarifiers

    Advantages
    ----------
    - Retains BNR basin investment (retrofit path)
    - Better effluent TSS and pathogen removal than BNR+clarifiers
    - Lower energy than fully integrated MBR (biology at lower MLSS)
    - Optional clarifier standby retained for resilience
    - Pathway to Class A+ reuse without full BNR replacement

    Comparison with integrated MBR
    --------------------------------
    Integrated MBR: single bioreactor, MLSS 8,000–12,000, membranes submerged in MLSS
    BNR+MBR hybrid: BNR at 4,000 MLSS + separate membrane tank at 8,000 MLSS
    Hybrid typically: lower energy, higher total footprint, more operational flexibility
    """

    @property
    def technology_code(self) -> str: return "bnr_mbr"

    @property
    def technology_name(self) -> str:
        return "BNR + MBR Hybrid (BNR Basins + Membrane Separation)"

    @property
    def technology_category(self) -> str:
        return "Biological Treatment"

    @classmethod
    def input_class(cls) -> Type: return BNRMBRInputs

    def calculate(
        self,
        design_flow_mld: float,
        inputs: BNRMBRInputs,
    ) -> TechnologyResult:

        r = TechnologyResult(
            technology_name=self.technology_name,
            technology_code=self.technology_code,
            technology_category=self.technology_category,
            description=(
                "Conventional BNR basins (anoxic + aerobic) at "
                f"{inputs.mlss_bnr_mg_l:,.0f} mg/L MLSS feeding a separate "
                "membrane separation tank. Replaces secondary clarifiers. "
                "Suitable as an upgrade path or new-build with operational flexibility."
            ),
        )

        flow = design_flow_mld * 1000.0   # m³/day
        flow_lph = design_flow_mld * 1e6 / 24.0

        # ── 1. Influent loads ──────────────────────────────────────────────
        inf = self._load_influent()
        bod_load = flow * inf["bod_mg_l"] / 1000.0
        tn_load  = flow * inf["tn_mg_l"]  / 1000.0
        tp_load  = flow * inf["tp_mg_l"]  / 1000.0

        eff_tn  = self._get_eng("effluent_tn_mg_l",  10.0)
        eff_tp  = self._get_eng("effluent_tp_mg_l",   0.5)
        eff_nh4 = self._get_eng("effluent_nh4_mg_l",  1.0)
        eff_bod = 3.0    # membrane polishing gives BOD < 3 mg/L
        eff_tss = 1.0    # membrane barrier

        tn_removed  = max(0.0, flow * (inf["tn_mg_l"] - eff_tn)  / 1000.0)
        tp_removed  = max(0.0, flow * (inf["tp_mg_l"] - eff_tp)  / 1000.0)
        bod_removed = max(0.0, flow * (inf["bod_mg_l"] - eff_bod) / 1000.0)

        r.notes.add_assumption(
            f"Influent: BOD {inf['bod_mg_l']:.0f}, TN {inf['tn_mg_l']:.0f}, "
            f"TP {inf['tp_mg_l']:.0f} mg/L at Q = {design_flow_mld:.1f} MLD"
        )
        r.notes.add_assumption(
            f"Zone 1 (BNR): MLSS {inputs.mlss_bnr_mg_l:,.0f} mg/L, SRT {inputs.srt_days}d, "
            f"anoxic fraction {inputs.anoxic_fraction:.0%}"
        )
        r.notes.add_assumption(
            f"Zone 2 (Membrane): MLSS {inputs.mlss_membrane_tank_mg_l:,.0f} mg/L, "
            f"flux {inputs.design_flux_lmh} LMH, {inputs.membrane_configuration.replace('_',' ')}"
        )

        # ── 2. BNR zone sizing ─────────────────────────────────────────────
        # Biology is done at conventional BNR MLSS — larger reactor than integrated MBR
        Y_true = 0.60
        kd     = 0.08
        y_obs  = Y_true / (1.0 + kd * inputs.srt_days)
        vss_tss = 0.80

        vss_prod = y_obs * bod_removed
        tss_prod = vss_prod / vss_tss

        # Reactor volume from BNR MLSS target
        bnr_reactor_m3 = (vss_prod * inputs.srt_days * 1000.0) / (inputs.mlss_bnr_mg_l * vss_tss)
        bnr_anoxic = bnr_reactor_m3 * inputs.anoxic_fraction
        bnr_aerobic = bnr_reactor_m3 * (1 - inputs.anoxic_fraction)

        # ── 3. Membrane tank sizing ────────────────────────────────────────
        # Membrane tank receives the full flow from BNR zone
        # Area sized from design flux at average flow (+ peak check)
        import math
        T = self._get_eng("influent_temperature_celsius", 20.0)
        nu_20 = 1.004
        nu_T  = 1.004 * math.exp(-0.025 * (T - 20.0))
        flux_derate = nu_20 / nu_T
        effective_flux = inputs.design_flux_lmh * flux_derate

        net_gross   = self._get_eng("mbr_net_to_gross_factor", 0.90)
        gross_flux  = effective_flux * net_gross
        mem_area_av = flow_lph / gross_flux
        # Peak flux: BNR+MBR feeds membrane with clarified BNR effluent at lower MLSS
        # → can operate at higher peak flux than integrated MBR
        peak_flux   = min(inputs.design_flux_lmh * 1.8, 40.0)
        _peak_factor = self._get_eng("peak_flow_factor", 2.5)
        mem_area_pk = flow_lph * _peak_factor / peak_flux
        mem_area_m2 = max(mem_area_av, mem_area_pk)

        # Membrane tank volume — sized to achieve the membrane tank MLSS target
        # WAS from membrane tank back to BNR zone; membrane tank MLSS = f(recycle ratio)
        mem_tank_vol = vss_prod * inputs.srt_days * 1000.0 / (inputs.mlss_membrane_tank_mg_l * vss_tss)

        r.notes.add_assumption(
            f"Membrane area: {mem_area_m2:,.0f} m² at {inputs.design_flux_lmh} LMH "
            f"(T-corrected {effective_flux:.1f} LMH, net/gross={net_gross})"
        )

        # ── 4. Sludge production ───────────────────────────────────────────
        # Single WAS stream — yield is the BNR zone yield (lower than pure MBR
        # because conventional SRT at lower MLSS)
        inorg_tss = flow * inf["tss_mg_l"] * (1.0 - vss_tss) / 1000.0
        total_sludge = tss_prod + inorg_tss

        r.sludge.biological_sludge_kgds_day = round(total_sludge, 1)
        r.sludge.vs_fraction  = vss_tss
        r.sludge.feed_ts_pct  = 1.5

        r.notes.add_assumption(
            f"y_obs = {y_obs:.3f} kgVSS/kgBOD (BNR zone SRT {inputs.srt_days}d, "
            "conventional MLSS — lower yield than integrated MBR)"
        )

        # ── 5. Energy ──────────────────────────────────────────────────────
        # BNR zone: conventional aeration; membrane tank: scour aeration
        alpha   = 0.55
        sae_std = self._get_eng("standard_aeration_efficiency_kg_o2_kwh", 1.8)
        _beta_fact_do = self._get_eng("beta_factor", 0.97)

        # ── DO setpoint correction (Metcalf 5th Ed Eq 5-26) ──────────────
        _T_aer   = self._get_eng("influent_temperature_celsius", 20.0)
        _Cs_T    = 468.0 / (31.6 + _T_aer)
        _Cs_proc = _beta_fact_do * _Cs_T
        _do_set  = self._get_eng("do_setpoint_mg_l", 2.0)
        _do_corr = ((_Cs_proc - 2.0) / max(_Cs_proc - _do_set, 0.1))
        _do_corr = max(0.5, min(2.5, _do_corr))
        sae     = sae_std * alpha * _do_corr

        nh4_frac    = self._get_eng("influent_nh4_mg_l", 35.0) / max(inf["tn_mg_l"], 1.0)
        o2_c        = max(0.0, bod_removed - 1.42 * vss_prod)    # carbonaceous (M&E Eq 8-20)
        o2_n        = 4.57 * tn_load * nh4_frac * 0.90
        no3_dn      = tn_removed * inputs.anoxic_fraction / 0.35
        o2_dn       = 2.86 * no3_dn
        o2_kg       = max(0.0, o2_c + o2_n - o2_dn)
        bio_aer_kwh = o2_kg / sae

        # Membrane scour aeration
        sad       = self._get_eng("mbr_sad", 0.30)
        scour_kwh = sad * mem_area_m2 * 24.0 * 0.006

        # Anoxic BNR zone mixing (7 W/m³)
        mix_kwh = bnr_anoxic * 0.007 * 24.0

        # ── Pumping: RAS + MLR + WAS + permeate + ancillary ───────────────
        tmp_kpa  = abs(self._get_eng("mbr_tmp_kpa", 25.0))
        pump_eff = self._get_eng("pump_efficiency", 0.72)
        flow_m3s = flow / 86400.0
        flow_lph_avg = flow * 1000.0 / 24.0

        perm_kwh = (tmp_kpa * 1000 * flow_lph_avg / 1000 * 24) / (3600 * 1000 * pump_eff)
        ras_kwh  = (1000 * 9.81 * flow_m3s * 1.2 * 3.0  / pump_eff) * 24.0 / 1000.0
        mlr_kwh  = (1000 * 9.81 * flow_m3s * 4.0 * 0.5  / pump_eff) * 24.0 / 1000.0
        was_kwh  = (1000 * 9.81 * flow_m3s * 0.01 * 10.0 / pump_eff) * 24.0 / 1000.0
        ancillary_kwh = 70.0 * design_flow_mld

        r.energy.aeration_kwh_day = round(bio_aer_kwh, 1)
        r.energy.membrane_kwh_day = round(scour_kwh, 1)
        r.energy.mixing_kwh_day   = round(mix_kwh, 1)
        r.energy.pumping_kwh_day  = round(perm_kwh + ras_kwh + mlr_kwh + was_kwh + ancillary_kwh, 1)

        r.notes.add_assumption(
            f"O₂ demand = {o2_kg:.0f} kg/day | Membrane scour = {scour_kwh:.0f} kWh/day"
        )
        r.notes.add_assumption(
            f"Pumping: permeate={perm_kwh:.0f} + RAS={ras_kwh:.0f} + "
            f"MLR(4×Q)={mlr_kwh:.0f} + WAS={was_kwh:.0f} + ancillary={ancillary_kwh:.0f} kWh/day"
        )

        # ── 6. Effluent quality ────────────────────────────────────────────
        r.performance.effluent_bod_mg_l = eff_bod
        r.performance.effluent_tss_mg_l = eff_tss
        r.performance.effluent_nh4_mg_l = eff_nh4
        r.performance.effluent_tn_mg_l  = eff_tn
        r.performance.effluent_tp_mg_l  = eff_tp if inputs.chemical_p_removal else min(eff_tp + 0.2, 0.7)

        # Total footprint: BNR basins + membrane tank + optional 1 clarifier
        bnr_footprint = bnr_reactor_m3 / 4.5   # BNR basins at ~4.5m depth
        mem_footprint = mem_tank_vol / 5.0      # Membrane tank at ~5m depth
        clar_footprint = (flow * 1.5 / 24 / 1.5) if inputs.retain_one_clarifier else 0  # 1 standby clarifier

        r.performance.reactor_volume_m3           = round(bnr_reactor_m3 + mem_tank_vol, 0)
        r.performance.hydraulic_retention_time_hr = round((bnr_reactor_m3 + mem_tank_vol) / flow * 24, 1)
        r.performance.footprint_m2 = round(bnr_footprint + mem_footprint + clar_footprint, 0)

        r.performance.additional.update({
            "bnr_reactor_volume_m3":    round(bnr_reactor_m3, 0),
            "bnr_anoxic_volume_m3":     round(bnr_anoxic, 0),
            "bnr_aerobic_volume_m3":    round(bnr_aerobic, 0),
            "membrane_tank_volume_m3":  round(mem_tank_vol, 0),
            "membrane_area_m2":         round(mem_area_m2, 0),
            "design_flux_lmh":          inputs.design_flux_lmh,
            "retain_one_clarifier":     inputs.retain_one_clarifier,
            "o2_demand_kg_day":         round(o2_kg, 0),
            "lrv_cryptosporidium":      4.0,
            "lrv_virus":                2.0,
        })

        # ── 7. Scope 1 ─────────────────────────────────────────────────────
        n2o_ef  = self._get_eng("n2o_emission_factor_g_n2o_per_g_n_removed", 0.016)
        n2o_gwp = self._get_eng("n2o_gwp", 273)
        r.carbon.n2o_biological_tco2e_yr = round(
            tn_removed * n2o_ef * 365 * n2o_gwp / 1000.0, 1
        )
        r.notes.add_assumption(f"N₂O EF = {n2o_ef} kg N₂O/kg N (IPCC 2019 Tier 1)")

        # ── 8. Risk ────────────────────────────────────────────────────────
        r.risk.reliability_risk       = "Low"
        r.risk.regulatory_risk        = "Low"
        r.risk.technology_maturity    = "Established"
        r.risk.operational_complexity = "Moderate"
        r.risk.site_constraint_risk   = "Low"
        r.risk.implementation_risk    = "Low"

        # ── 9. Limitations ─────────────────────────────────────────────────
        r.notes.add_limitation(
            "Footprint includes: BNR basins + membrane tank"
            + (" + 1 standby clarifier." if inputs.retain_one_clarifier
               else ". No clarifier retained (full replacement mode).")
        )
        r.notes.add_limitation(
            "CAPEX excludes: interconnecting pipework between BNR and membrane zones, "
            "which can be significant in retrofit applications. Allow 15–25% on top of "
            "civil costs for piping, valves, and flow distribution."
        )

        # ── 10. CIP chemicals ──────────────────────────────────────────────
        cip_days = self._get_eng("mbr_cip_interval_days", 30)
        chems = {
            "sodium_hypochlorite_kg_day": round(mem_area_m2 * 0.002 / cip_days, 3),
            "citric_acid_kg_day":         round(mem_area_m2 * 0.001 / cip_days, 3),
        }
        r.chemical_consumption = chems

        # ── 11. CAPEX ──────────────────────────────────────────────────────
        r.capex_items = [
            CostItem(
                "BNR bioreactor tankage (anoxic + aerobic)",
                "aeration_tank_per_m3",
                bnr_reactor_m3,
                "m³",
                notes="A2O / modified Bardenpho configuration",
            ),
            CostItem(
                "Membrane separation tank",
                "aeration_tank_per_m3",
                mem_tank_vol,
                "m³",
                notes="Separate vessel downstream of BNR, submerged membranes",
            ),
            CostItem(
                "MBR membrane cassettes",
                "mbr_membrane_per_m2",
                mem_area_m2,
                "m² protected area",
                notes=f"{inputs.membrane_configuration.replace('_',' ')} cassettes, air diffusers, manifolds",
            ),
            CostItem(
                "Blower system (biological + membrane scour)",
                "blower_per_kw",
                (bio_aer_kwh + scour_kwh) / 24.0,
                "kW installed",
            ),
            CostItem(
                "Permeate + RAS pump systems",
                "pump_per_kw",
                (perm_kwh + ras_kwh) / 24.0,
                "kW installed",
            ),
        ]
        if inputs.retain_one_clarifier:
            r.capex_items.append(CostItem(
                "Secondary clarifier (1 standby / bypass unit)",
                "secondary_clarifier_per_m2",
                clar_footprint,
                "m² surface area",
                notes="Retained for operational resilience and membrane maintenance bypass",
            ))

        # ── 12. OPEX ──────────────────────────────────────────────────────
        r.opex_items = [
            CostItem("Electricity — biological aeration", "electricity_per_kwh", bio_aer_kwh, "kWh/day"),
            CostItem("Electricity — membrane scour", "electricity_per_kwh", scour_kwh, "kWh/day",
                     notes="Membrane tank scour aeration at corrected 0.006 kWh/m³ air"),
            CostItem("Electricity — mixing, RAS/MLR/WAS & ancillary", "electricity_per_kwh",
                     mix_kwh + perm_kwh + ras_kwh + mlr_kwh + was_kwh + ancillary_kwh, "kWh/day",
                     notes="Anoxic mixing + permeate pump + RAS + MLR(4×Q) + WAS + plant ancillary"),
            CostItem("Membrane replacement (annualised)", "mbr_membrane_replacement_per_m2_yr",
                     mem_area_m2 / 365.0, "m²/day"),
            CostItem("CIP chemicals", "sodium_hypochlorite_per_kg", chems["sodium_hypochlorite_kg_day"], "kg/day NaOCl"),
            CostItem("Sludge disposal", "sludge_disposal_per_tds", total_sludge / 1000.0, "t DS/day"),
        ]

        # ── 13. Assumptions log ────────────────────────────────────────────
        r.assumptions_used = {
            "srt_days":                      inputs.srt_days,
            "mlss_bnr_mg_l":                 inputs.mlss_bnr_mg_l,
            "mlss_membrane_tank_mg_l":       inputs.mlss_membrane_tank_mg_l,
            "y_obs_kgvss_kgbod":             round(y_obs, 3),
            "design_flux_lmh":               inputs.design_flux_lmh,
            "alpha_factor":                  alpha,
            "n2o_ef":                        n2o_ef,
            "retain_one_clarifier":          inputs.retain_one_clarifier,
        }

        # ── 14. Finalise ──────────────────────────────────────────────────
        return r.finalise(
            design_flow_mld,
            influent_bod_mg_l=inf["bod_mg_l"],
            influent_nh4_mg_l=inf["tn_mg_l"] * nh4_frac,
            influent_tn_mg_l=inf["tn_mg_l"],
            influent_tp_mg_l=inf["tp_mg_l"],
        )
