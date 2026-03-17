"""
domains/wastewater/technologies/ifas_mbbr.py

IFAS (Integrated Fixed-film Activated Sludge) / MBBR
======================================================
Suspended plastic carrier media added to biological reactors to grow
a mixed biofilm + activated-sludge biomass system.

IFAS (retrofit)
  Carriers added to existing aeration basins while retaining suspended
  mixed liquor and secondary clarifiers. The biofilm supplements
  nitrification capacity without increasing tank volume — the primary
  application is capacity upgrade under land constraints.

MBBR (standalone)
  Carriers are the sole biomass support; no suspended MLSS target.
  Followed by a downstream separation step (clarifier, DAF, or membrane).

Design basis
------------
• Biofilm nitrification surface rate: 1.5–2.5 g NH4-N/m²/day at 20°C
  (WEF MOP 35 Table 4-6; Ødegaard 2006)
• Temperature correction (Arrhenius): rate(T) = rate(20°C) × 1.07^(T−20)
• Aerobic zone volume for IFAS = total reactor volume × (1 − fill_ratio)
  (media occupies fill_ratio fraction; suspended MLSS fills the rest)
• Oxygen demand: carbonaceous + nitrification − denitrification credit
• alpha_factor reduced near media (0.60 vs 0.65 for clean CAS)

References
----------
  - WEF MOP 35 (2011) Biofilm Reactors — Chapters 3–4
  - Ødegaard (2006) Innovations in wastewater treatment — Water Sci. Tech.
  - Metcalf & Eddy (2014) Ch. 9 — Attached-growth processes
  - EPA (2010) Nutrient Control Design Manual — Biofilm section
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
class IFASMBBRInputs:
    """Design parameters for the IFAS / MBBR process."""

    # ── Mode ──────────────────────────────────────────────────────────────
    mode: str = "ifas"
    # "ifas"             — retrofit into existing aeration basins
    # "mbbr_standalone"  — new-build MBBR with downstream separation

    # ── Media parameters ──────────────────────────────────────────────────
    media_fill_ratio: float = 0.35
    # Volumetric fill ratio of carriers in the aerobic zone (0.20–0.55).
    # Typical IFAS design: 0.30–0.45. > 0.50 risks media bridging.

    media_surface_area_m2_per_m3: float = 500.0
    # Carrier specific surface area (m²/m³ carrier). Typical: 350–800.
    # High values (> 600) have thinner biofilm and lower unit cost per m².

    # ── Biological design ─────────────────────────────────────────────────
    srt_days: float = 8.0
    # Suspended fraction SRT (days). IFAS can operate at lower SRT than CAS
    # because the biofilm carries most of the nitrifying biomass.

    mlss_mg_l: float = 2500.0
    # Suspended MLSS in the IFAS basin (mg/L). Lower than CAS (3000–4000)
    # because nitrifiers reside primarily on the carriers.

    design_temperature_celsius: float = 20.0
    # Basin design temperature (°C). Critical for biofilm nitrification rate.

    # ── Chemistry ─────────────────────────────────────────────────────────
    chemical_p_removal: bool = False
    # Auto-triggered when effluent TP target < 1.0 mg/L — biological P removal
    # from the activated sludge fraction typically achieves 1-2 mg/L without dosing.
    coagulant: str = "ferric_chloride"   # "ferric_chloride" | "alum"

    supplemental_carbon: bool = False
    # External carbon (methanol) for denitrification polishing. IFAS
    # denitrification is limited in the absence of a dedicated anoxic zone.

    _field_bounds: dict = field(default_factory=lambda: {
        "media_fill_ratio":             (0.10, 0.65),
        "media_surface_area_m2_per_m3": (250, 900),
        "srt_days":                     (3, 25),
        "mlss_mg_l":                    (1000, 5000),
        "design_temperature_celsius":   (8, 30),
    }, repr=False)


# ─────────────────────────────────────────────────────────────────────────────
# TECHNOLOGY CLASS
# ─────────────────────────────────────────────────────────────────────────────

class IFASMBBRTechnology(BaseTechnology):
    """
    IFAS Retrofit / MBBR Standalone — screening-level planning model.

    Advantages
    ----------
    IFAS: no new tankage, minimal civil disruption, boosts nitrification
    capacity by 50–100% in existing basins.
    MBBR: very compact (no suspended MLSS target), continuous operation
    without SBR cycles.

    Limitations
    -----------
    Secondary clarifiers still required for IFAS (no footprint saving vs CAS).
    Media retention screens (1 mm) essential — screen failure loses media.
    TN removal limited unless dedicated anoxic zone is included.
    """

    @property
    def technology_code(self) -> str: return "ifas_mbbr"

    @property
    def technology_name(self) -> str:
        return "IFAS Retrofit" if True else "MBBR (Standalone)"

    @property
    def technology_category(self) -> str:
        return "Biological Treatment"

    @classmethod
    def input_class(cls) -> Type: return IFASMBBRInputs

    def calculate(
        self,
        design_flow_mld: float,
        inputs: IFASMBBRInputs,
    ) -> TechnologyResult:

        r = TechnologyResult(
            technology_name=(
                "IFAS Retrofit"
                if inputs.mode == "ifas"
                else "MBBR (Standalone)"
            ),
            technology_code=self.technology_code,
            technology_category=self.technology_category,
            description=(
                "IFAS: fixed-film carriers retrofit into existing aeration tanks to "
                "boost nitrification capacity without new concrete."
                if inputs.mode == "ifas" else
                "MBBR standalone: biofilm carriers as the sole biomass support "
                "in a continuous-flow reactor."
            ),
        )

        flow = design_flow_mld * 1000.0   # m³/day

        # ── Temperature: inherit from scenario if not explicitly overridden ──
        import dataclasses as _dc
        _T_default = next(f.default for f in _dc.fields(type(inputs))
                          if f.name == "design_temperature_celsius")
        if inputs.design_temperature_celsius == _T_default:
            _scenario_T = self._get_eng("influent_temperature_celsius", _T_default)
            inputs = _dc.replace(inputs, design_temperature_celsius=_scenario_T)

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

        r.notes.add_assumption(
            f"Influent: BOD {inf['bod_mg_l']:.0f}, TN {inf['tn_mg_l']:.0f}, "
            f"TP {inf['tp_mg_l']:.0f}, TSS {inf['tss_mg_l']:.0f} mg/L "
            f"at Q = {design_flow_mld:.1f} MLD"
        )

        # ── 2. Temperature correction for biofilm nitrification ───────────
        # Biofilm nitrification rate follows Arrhenius: theta ≈ 1.07 (WEF MOP 35)
        nit_rate_base = 2.0   # g NH4-N/m²/day at 20°C (WEF MOP 35 Table 4-6)
        theta_nit     = 1.07
        nit_rate_T    = nit_rate_base * (theta_nit ** (inputs.design_temperature_celsius - 20.0))

        r.notes.add_assumption(
            f"Biofilm nitrification rate: {nit_rate_T:.2f} g NH4-N/m²/day "
            f"(base {nit_rate_base:.1f} at 20°C × 1.07^(T−20), T={inputs.design_temperature_celsius}°C; "
            "WEF MOP 35 Table 4-6)"
        )

        # Temperature warning
        if inputs.design_temperature_celsius < 15.0:
            r.notes.warn(
                f"⚠ Design temperature {inputs.design_temperature_celsius}°C is below 15°C. "
                f"Biofilm nitrification rate is {nit_rate_T/nit_rate_base*100:.0f}% of the 20°C value. "
                "Increase media area or add supplemental heat."
            )

        # ── 3. Reactor and media sizing ────────────────────────────────────
        # For IFAS: existing tank volume is the starting point.
        # For sizing here, we derive required volume from suspended fraction SRT.
        y_obs_sus  = 0.35    # kgVSS/kgBOD for suspended fraction
        vss_tss    = 0.80
        reactor_m3 = (y_obs_sus * bod_removed * inputs.srt_days * 1000.0) / (inputs.mlss_mg_l * vss_tss)

        # ── Media area: sized from NITRIFICATION DEMAND not reactor fill ──
        # IFAS media only needs to provide the nitrification capacity required.
        # The suspended biomass provides carbonaceous BOD removal and some nitrification;
        # the biofilm supplements nitrification to meet the effluent NH4 target.
        # Area = (NH4_load_to_nitrify × 1000) / nit_rate_T  [g/day / (g/m²/day) = m²]
        nh4_load_kg  = flow * inf.get("nh4_mg_l", inf["tn_mg_l"] * 0.78) / 1000.0
        nh4_to_nitrify = nh4_load_kg * 0.90   # 90% removal efficiency target
        media_area_m2 = (nh4_to_nitrify * 1000.0) / nit_rate_T

        # For MBBR standalone: size for full nitrification (100% of NH4 load on biofilm)
        # For IFAS: biofilm provides incremental capacity above what suspended MLSS achieves
        # Conservative: size all nitrification on biofilm (ensures adequate capacity)
        # This gives: ~160,000 m² at 10 MLD vs previous 350,000 m²

        # Also compute fill fraction that this media area implies
        aerobic_frac = 0.60
        aerobic_vol  = reactor_m3 * aerobic_frac
        media_vol    = media_area_m2 / inputs.media_surface_area_m2_per_m3
        implied_fill = media_vol / aerobic_vol if aerobic_vol > 0 else inputs.media_fill_ratio
        # Cap at design fill ratio — don't overflow the basin
        if implied_fill > inputs.media_fill_ratio:
            media_area_m2 = aerobic_vol * inputs.media_fill_ratio * inputs.media_surface_area_m2_per_m3
            media_vol     = aerobic_vol * inputs.media_fill_ratio

        # Nitrification capacity from biofilm
        nit_cap_kg_day = media_area_m2 * nit_rate_T / 1000.0

        r.notes.add_assumption(
            f"Reactor: {reactor_m3:.0f} m³ | aerobic zone {aerobic_vol:.0f} m³ | "
            f"media volume {media_vol:.0f} m³ | "
            f"media area {media_area_m2:,.0f} m² (sized from NH4 removal demand)"
        )

        # Fill ratio warning
        if inputs.media_fill_ratio > 0.50:
            r.notes.warn(
                f"⚠ Media fill ratio {inputs.media_fill_ratio:.0%} exceeds 0.50. "
                "High fill ratios risk media bridging, uneven distribution, and mixing dead zones. "
                "Reduce to ≤ 0.45 for robust operation (Ødegaard 2006)."
            )

        # Media retention note
        r.notes.add_limitation(
            "Fine screens (≤ 1 mm opening) are required at all effluent points to retain carriers. "
            "Screen failure results in loss of biofilm biomass to downstream processes."
        )

        # ── 4. Sludge production ───────────────────────────────────────────
        sludge_vss  = y_obs_sus * bod_removed
        sludge_tss  = sludge_vss / vss_tss
        # Inorganic TSS pass-through
        inorg_tss   = flow * inf["tss_mg_l"] * (1.0 - vss_tss) / 1000.0
        total_sludge = sludge_tss + inorg_tss

        r.sludge.biological_sludge_kgds_day = round(total_sludge, 1)
        r.sludge.vs_fraction  = vss_tss
        r.sludge.feed_ts_pct  = 1.5   # Typical thickened WAS

        # ── 5. Oxygen demand and aeration energy ───────────────────────────
        # alpha is reduced in biofilm zones due to surfactant accumulation near media
        alpha   = 0.60   # (Ødegaard 2006 reports 0.55–0.65 for IFAS)
        sae_std = self._get_eng("standard_aeration_efficiency_kg_o2_kwh", 1.8)
        sae     = sae_std * alpha

        o2_c  = max(0.0, bod_removed - 1.42 * sludge_vss)         # carbonaceous (M&E Eq 8-20)
        nh4_f = self._get_eng("influent_nh4_mg_l", 35.0) / max(inf["tn_mg_l"], 1.0)
        o2_n  = 4.57 * tn_load * nh4_f * 0.90                   # nitrification (90%)
        no3_dn = tn_removed * 0.50                               # 50% via denitrification (limited without anoxic zone)
        o2_dn  = 2.86 * no3_dn
        o2_kg  = max(0.0, o2_c + o2_n - o2_dn)

        aer_kwh = o2_kg / sae
        mix_kwh = reactor_m3 * 0.008 * 24.0   # 8 W/m³ — slightly higher than CAS to keep media suspended

        r.energy.aeration_kwh_day = round(aer_kwh, 1)
        r.energy.mixing_kwh_day   = round(mix_kwh, 1)

        # ── Pumping: RAS + MLR + WAS + ancillary (same as BNR) ────────────
        pump_eff  = self._get_eng("pump_efficiency", 0.72)
        flow_m3s  = flow / 86400.0
        ras_kwh   = (1000 * 9.81 * flow_m3s * 1.0 * 3.0 / pump_eff) * 24.0 / 1000.0  # RAS 1×Q, 3m
        mlr_kwh   = (1000 * 9.81 * flow_m3s * 4.0 * 0.5 / pump_eff) * 24.0 / 1000.0  # MLR 4×Q, 0.5m
        was_kwh   = (1000 * 9.81 * flow_m3s * 0.01 * 10.0 / pump_eff) * 24.0 / 1000.0  # WAS
        ancillary_kwh = 70.0 * design_flow_mld  # screening, UV, SCADA, misc
        r.energy.pumping_kwh_day = round(ras_kwh + mlr_kwh + was_kwh + ancillary_kwh, 1)

        r.notes.add_assumption(
            f"alpha = {alpha} (biofilm zone, Ødegaard 2006); "
            f"O2 demand = {o2_kg:.0f} kg/day (carbonaceous {o2_c:.0f} + nit {o2_n:.0f} − DeN credit {o2_dn:.0f})"
        )
        r.notes.add_assumption(
            f"Pumping: RAS={ras_kwh:.0f} + MLR(4×Q)={mlr_kwh:.0f} + "
            f"WAS={was_kwh:.0f} + ancillary={ancillary_kwh:.0f} kWh/day"
        )

        if not inputs.supplemental_carbon:
            r.notes.add_limitation(
                "Denitrification is limited without a dedicated anoxic zone. "
                "TN removal may be restricted to 40–60% without supplemental carbon "
                "or internal recycle from aerobic to anoxic zones."
            )
        else:
            r.notes.add_assumption(
                "Methanol dose: 4 kg/kg NO3-N denitrified (WEF MOP 32 Table 7-5)"
            )

        # ── 6. Chemical consumption ────────────────────────────────────────
        chems: Dict[str, float] = {}
        # Compute ferric dose whenever chemical P removal is needed
        # (explicit flag OR TP target < 1.0 mg/L where biological alone insufficient)
        _needs_cpr = inputs.chemical_p_removal or eff_tp < 1.0
        if _needs_cpr:
            p_mol = tp_removed * 1000.0 / 31.0
            chems["ferric_chloride_kg_day"] = round(p_mol * 2.5 * 162.2 / 1000.0, 2)
        if inputs.supplemental_carbon:
            methanol_kg = no3_dn * 4.0 * 0.30   # 30% of denitrification deficit
            chems["methanol_kg_day"] = round(methanol_kg, 2)
        r.chemical_consumption = chems

        # ── 7. Effluent quality ────────────────────────────────────────────
        # Carbon-limited denitrification (Metcalf Table 7-32 adapted for IFAS).
        # IFAS aerobic zone dominates; anoxic fraction typically 20-30%.
        # Without dedicated anoxic zone, denitrification efficiency is lower
        # than BNR — COD/TKN thresholds tighter:
        cod_tkn_ratio_ifas = inf["bod_mg_l"] * 2.0 / max(inf["tn_mg_l"], 1.0)
        if inputs.supplemental_carbon:
            eff_tn_actual = eff_tn
        elif cod_tkn_ratio_ifas < 5.0:
            eff_tn_actual = max(eff_tn, inf["tn_mg_l"] * 0.65)
            r.notes.warn(
                f"⚠️ COD/TKN = {cod_tkn_ratio_ifas:.1f} — severely carbon-limited. "
                f"IFAS achievable TN ≈ {eff_tn_actual:.1f} mg/L (target {eff_tn:.1f}). "
                "Supplemental carbon (methanol) required."
            )
        elif cod_tkn_ratio_ifas < 8.0:
            eff_tn_actual = max(eff_tn, inf["tn_mg_l"] * 0.45)
            r.notes.warn(
                f"⚠️ COD/TKN = {cod_tkn_ratio_ifas:.1f} — carbon-limited. "
                f"IFAS achievable TN ≈ {eff_tn_actual:.1f} mg/L (limited anoxic zone). "
                "Consider supplemental carbon or dedicated anoxic stage."
            )
        elif cod_tkn_ratio_ifas < 10.0:
            eff_tn_actual = max(eff_tn, inf["tn_mg_l"] * 0.30)
            if eff_tn_actual > eff_tn:
                r.notes.warn(
                    f"⚠️ COD/TKN = {cod_tkn_ratio_ifas:.1f} — marginal for IFAS. "
                    f"Achievable TN ≈ {eff_tn_actual:.1f} mg/L. "
                    "Increase carbon source or add dedicated anoxic zone."
                )
        else:
            eff_tn_actual = eff_tn

        r.performance.effluent_bod_mg_l = eff_bod
        r.performance.effluent_tss_mg_l = eff_tss
        r.performance.effluent_nh4_mg_l = eff_nh4
        r.performance.effluent_tn_mg_l  = round(eff_tn_actual, 2)
        r.performance.effluent_tp_mg_l  = (
            eff_tp if (inputs.chemical_p_removal or eff_tp < 1.0) else min(eff_tp + 0.3, 1.2)
        )
        r.performance.reactor_volume_m3           = round(reactor_m3, 0)
        r.performance.hydraulic_retention_time_hr = round(reactor_m3 / flow * 24.0, 1)
        r.performance.footprint_m2 = round(
            reactor_m3 / 4.5                    # basin depth ~4.5 m
            + self._get_eng("peak_flow_factor", 2.5) * flow / 24.0 / 1.5,          # secondary clarifier at peak SOR
            0
        )
        r.performance.additional.update({
            "media_total_area_m2":              round(media_area_m2, 0),
            "media_fill_ratio":                 inputs.media_fill_ratio,
            "media_surface_area_m2_per_m3":     inputs.media_surface_area_m2_per_m3,
            "nitrification_capacity_kg_n_day":  round(nit_cap_kg_day, 1),
            "nit_rate_T_g_m2_day":              round(nit_rate_T, 2),
            "retrofit_compatible":              inputs.mode == "ifas",
            "o2_demand_kg_day":                 round(o2_kg, 0),
            "kwh_per_kg_tn_removed":            round(aer_kwh / max(tn_removed, 0.001), 1),
        })

        # ── 8. Scope 1 emissions ───────────────────────────────────────────
        n2o_ef  = self._get_eng("n2o_emission_factor_g_n2o_per_g_n_removed", 0.016)
        n2o_gwp = self._get_eng("n2o_gwp", 273)
        r.carbon.n2o_biological_tco2e_yr = round(
            tn_removed * n2o_ef * 365 * n2o_gwp / 1000.0, 1
        )
        r.notes.add_assumption(
            f"N2O EF = {n2o_ef} kg N2O/kg N removed (IPCC 2019 Tier 1)"
        )
        r.notes.add_limitation(
            "N2O is the largest carbon uncertainty (±3×). "
            "Site-specific measurement recommended for detailed carbon accounting."
        )

        # ── 9. Risk ────────────────────────────────────────────────────────
        r.risk.reliability_risk       = "Low"
        r.risk.regulatory_risk        = "Low"
        r.risk.technology_maturity    = "Established"   # 500+ full-scale installations
        r.risk.operational_complexity = "Low"            # Simpler than MBR; media self-manages
        r.risk.site_constraint_risk   = "Low"            # Retrofit uses existing footprint
        r.risk.implementation_risk    = "Low"

        r.risk.additional_flags["media_retention_screen_risk"] = "Moderate"
        r.risk.additional_flags["low_temperature_nitrification_risk"] = (
            "High" if inputs.design_temperature_celsius < 12 else
            "Moderate" if inputs.design_temperature_celsius < 15 else "Low"
        )

        # ── 10. CAPEX ─────────────────────────────────────────────────────
        r.capex_items = [
            CostItem(
                "IFAS/MBBR carrier media",
                "ifas_media_per_m2",
                media_area_m2,
                "m² protected surface area",
                unit_cost_override=45.0,   # ~$45/m² carrier (industry range $30-60/m²; Ødegaard 2006)
                notes="Polyethylene/polypropylene carriers; includes filling and commissioning",
            ),
            CostItem(
                "Blower/aeration upgrade",
                "blower_per_kw",
                aer_kwh / 24.0,
                "kW installed",
            ),
            CostItem(
                "Media retention screens",
                "fine_screen_per_unit",
                max(1, int(design_flow_mld / 5) + 1),
                "unit",
                notes="≤ 1 mm openings; sized for peak flow",
            ),
        ]
        if inputs.mode == "mbbr_standalone":
            r.capex_items.insert(0, CostItem(
                "MBBR reactor tankage (concrete)",
                "aeration_tank_per_m3",
                reactor_m3,
                "m³",
            ))
        else:
            r.notes.add_assumption(
                "CAPEX: IFAS retrofit — existing tankage retained. "
                "Only media, screen, and blower upgrade costs included."
            )

        # ── 11. OPEX ──────────────────────────────────────────────────────
        r.opex_items = [
            CostItem(
                "Electricity — aeration",
                "electricity_per_kwh",
                aer_kwh,
                "kWh/day",
            ),
            CostItem(
                "Electricity — mixing, RAS/MLR/WAS & ancillary",
                "electricity_per_kwh",
                mix_kwh + ras_kwh + mlr_kwh + was_kwh + ancillary_kwh,
                "kWh/day",
                notes="Whole-reactor mixing (media suspension) + RAS + MLR(4×Q) + WAS + ancillary",
            ),
            CostItem(
                "Sludge disposal",
                "sludge_disposal_per_tds",
                total_sludge / 1000.0,
                "t DS/day",
            ),
            CostItem(
                "Media top-up (replacement ~5%/yr)",
                "ifas_media_per_m2",
                media_area_m2 * 0.05 / 365.0,
                "m²/day",
                notes="~5% annual replacement for attrition and fouled carriers",
            ),
        ]
        # Apply chemical P removal if explicitly enabled OR if TP target < 1.0 mg/L
        # Biological P from activated sludge fraction typically achieves ~1-2 mg/L.
        # Chemical dosing required to reliably achieve < 1 mg/L.
        apply_cpr = inputs.chemical_p_removal or eff_tp < 1.0

        if apply_cpr and "ferric_chloride_kg_day" in chems:
            r.opex_items.append(CostItem(
                "Ferric chloride (P removal)",
                "ferric_chloride_per_kg",
                chems["ferric_chloride_kg_day"],
                "kg/day",
            ))
        if inputs.supplemental_carbon and "methanol_kg_day" in chems:
            r.opex_items.append(CostItem(
                "Methanol (supplemental carbon)",
                "methanol_per_kg",
                chems["methanol_kg_day"],
                "kg/day",
            ))

        r.notes.add_limitation(
            "CAPEX excludes secondary clarifier upgrades (IFAS) or downstream "
            "clarifier/DAF/membrane (MBBR standalone). These are typically the "
            "cost-limiting items in an IFAS/MBBR upgrade."
        )

        # ── 12. Assumptions log ───────────────────────────────────────────
        r.assumptions_used = {
            "mode":                          inputs.mode,
            "media_fill_ratio":              inputs.media_fill_ratio,
            "media_surface_area_m2_per_m3":  inputs.media_surface_area_m2_per_m3,
            "nit_rate_base_g_m2_day":        nit_rate_base,
            "nit_rate_T_g_m2_day":           round(nit_rate_T, 3),
            "design_temperature_celsius":    inputs.design_temperature_celsius,
            "alpha_factor":                  alpha,
            "sae_process_kg_o2_kwh":         round(sae, 2),
            "y_obs_kgvss_kgbod":             y_obs_sus,
            "n2o_ef_kg_n2o_kg_n":            n2o_ef,
        }

        # ── 13. Finalise ──────────────────────────────────────────────────
        return r.finalise(
            design_flow_mld,
            influent_bod_mg_l=inf["bod_mg_l"],
            influent_nh4_mg_l=inf["tn_mg_l"] * nh4_f,
            influent_tn_mg_l=inf["tn_mg_l"],
            influent_tp_mg_l=inf["tp_mg_l"],
        )
