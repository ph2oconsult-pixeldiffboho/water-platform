"""
domains/wastewater/technologies/granular_sludge.py

Aerobic Granular Sludge (AGS) — Nereda® / GSBR
================================================
Dense, self-aggregating granular biofilm growing in a sequencing batch
reactor (SBR) cycle. Granules settle 5–10× faster than activated sludge
floc, eliminating the secondary clarifier and reducing footprint ~35%.

Process description
-------------------
Each SBR cycle consists of: plug-flow fill (no aeration), aerated react,
brief settle (< 5 min), and decant. During fill, wastewater pushes out the
decanted effluent, creating the simultaneous nitrification-denitrification
(SND) and biological phosphorus removal zones within the granule gradient.
A selective pressure (feast-famine) maintains granule stability.

Design basis
------------
• Sludge yield:   y_obs = 0.22 kgVSS/kgBOD (long SRT + granule structure)
  (van Dijk 2020 — range 0.18–0.28 depending on SRT and temperature)
• MLSS:           8,000 mg/L (granular fraction; higher than CAS 3,000–4,000)
• O2 demand:      carbonaceous + nitrification − denitrification (SND 50–70%)
• alpha:          0.65 (granule structure reduces surfactant accumulation)
• Cycle time:     4 hours (fill 30 min, react 3 hr, settle 5 min, decant 25 min)
• Temperature:    Arrhenius correction for nitrification; granule stability
                  at risk below 10°C

References
----------
  - de Kreuk et al. (2007) AGS state of the art — Water Research 41(18)
  - van Dijk et al. (2020) Full-scale Nereda performance — Water Sci. Tech.
  - WEF (2018) Innovative Biological Treatment Processes, Ch. 3
  - Pronk et al. (2015) Full-scale performance of Nereda — Water Research
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
class GranularSludgeInputs:
    """Design parameters for the Aerobic Granular Sludge process."""

    # ── Process design ─────────────────────────────────────────────────────
    srt_days: float = 20.0
    # Sludge retention time (days). AGS: 15–30 days.
    # Longer SRT → lower yield, better P removal stability.

    cycle_time_hours: float = 4.0
    # SBR cycle duration (hours). Typical: 3–8 hours.
    # Determines number of reactors needed for continuous flow.

    granule_diameter_mm: float = 2.0
    # Target mature granule diameter (mm). Typical: 1–4 mm.
    # Larger granules settle faster but may have anaerobic core.

    design_temperature_celsius: float = 20.0
    # Basin temperature (°C). Granule stability at risk below 10°C.

    # ── Biological performance flags ──────────────────────────────────────
    simultaneous_n_removal: bool = True
    # True: SND via granule gradient (default). False: separate anoxic zone.

    biological_p_removal: bool = True
    # True: Bio-P via feast/famine cycles. May need chemical polish below 15°C.

    chemical_p_polish: bool = False
    # Adds FeCl3 tertiary dosing when bio-P reliability is uncertain
    # (cold climates, industrial catchments).

    # ── Flow balance tank ─────────────────────────────────────────────────
    include_flow_balance_tank: bool = True
    # AGS SBR receives flow intermittently (fill phase only).
    # A flow balance tank upstream buffers continuous influent during the
    # react/settle/decant phases. Sized for 1 full cycle time.
    # Required for all practical installations — default ON.
    # Without FBT: requires oversize headworks buffer or forced cycle timing.

    _field_bounds: dict = field(default_factory=lambda: {
        "srt_days":                   (10, 35),
        "cycle_time_hours":           (3, 8),
        "granule_diameter_mm":        (0.5, 5.0),
        "design_temperature_celsius": (8, 30),
    }, repr=False)


# ─────────────────────────────────────────────────────────────────────────────
# TECHNOLOGY CLASS
# ─────────────────────────────────────────────────────────────────────────────

class GranularSludgeTechnology(BaseTechnology):
    """
    Aerobic Granular Sludge (AGS/Nereda®) — screening-level planning model.

    Advantages
    ----------
    - ~35% smaller footprint than CAS (no secondary clarifier)
    - Lowest sludge yield of aerobic biological processes (~0.22 kgVSS/kgBOD)
    - Simultaneous N and P removal in a single reactor
    - Low energy per unit BOD removed vs CAS (SND oxygen credit)

    Limitations
    -----------
    - Granule stability sensitive to temperature (< 12°C) and shock loading
    - Bio-P unreliable in industrial catchments (competing organic acids)
    - Fewer full-scale references than CAS/MBR (~80 plants globally in 2024)
    - Startup requires 3–6 months for granule formation
    """

    @property
    def technology_code(self) -> str: return "granular_sludge"

    @property
    def technology_name(self) -> str: return "Aerobic Granular Sludge (Nereda® / GSBR)"

    @property
    def technology_category(self) -> str: return "Biological Treatment"

    @classmethod
    def input_class(cls) -> Type: return GranularSludgeInputs

    def calculate(
        self,
        design_flow_mld: float,
        inputs: GranularSludgeInputs,
    ) -> TechnologyResult:

        r = TechnologyResult(
            technology_name=self.technology_name,
            technology_code=self.technology_code,
            technology_category=self.technology_category,
            description=(
                "Aerobic granular SBR achieving simultaneous N and P removal "
                "in a compact footprint without secondary clarifiers."
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
        eff_bod = self._get_eng("effluent_bod_mg_l",   8.0)
        eff_tss = 8.0   # Fast-settling granules → good clarification in decant

        tn_removed  = max(0.0, flow * (inf["tn_mg_l"] - eff_tn)  / 1000.0)
        tp_removed  = max(0.0, flow * (inf["tp_mg_l"] - eff_tp)  / 1000.0)
        bod_removed = max(0.0, flow * (inf["bod_mg_l"] - eff_bod) / 1000.0)

        r.notes.add_assumption(
            f"Influent: BOD {inf['bod_mg_l']:.0f}, TN {inf['tn_mg_l']:.0f}, "
            f"TP {inf['tp_mg_l']:.0f} mg/L at Q = {design_flow_mld:.1f} MLD"
        )

        # ── 2. Sludge yield ────────────────────────────────────────────────
        # AGS: endogenous decay within dense granule matrix + long SRT
        # y_obs = 0.22 kgVSS/kgBOD (van Dijk 2020; range 0.18–0.28)
        y_obs   = 0.22
        mlss    = 8000.0   # mg/L — higher than CAS, lower than MBR
        vss_tss = 0.80

        vss_prod  = y_obs * bod_removed
        tss_prod  = vss_prod / vss_tss
        inorg_tss = flow * inf["tss_mg_l"] * (1.0 - vss_tss) / 1000.0
        total_sludge = tss_prod + inorg_tss

        r.sludge.biological_sludge_kgds_day = round(total_sludge, 1)
        r.sludge.vs_fraction  = vss_tss
        r.sludge.feed_ts_pct  = 1.5

        r.notes.add_assumption(
            f"y_obs = {y_obs} kgVSS/kgBOD (AGS long SRT + granule endogenous decay; "
            "van Dijk 2020 range 0.18–0.28)"
        )

        # ── 3. Reactor volume ──────────────────────────────────────────────
        # Temperature penalty factors — computed in section 4 but needed here.
        # Pre-compute from design temperature so reactor sizing is correct.
        _T_pre = inputs.design_temperature_celsius
        if _T_pre < 10.0:
            _reactor_penalty = 1.40; _energy_penalty = 1.15; _eff_nh4_penalty = 5.0; _granule_stable = False
        elif _T_pre < 12.0:
            _reactor_penalty = 1.25; _energy_penalty = 1.08; _eff_nh4_penalty = 3.0; _granule_stable = False
        elif _T_pre < 15.0:
            _reactor_penalty = 1.10; _energy_penalty = 1.03; _eff_nh4_penalty = 1.5; _granule_stable = True
        else:
            _reactor_penalty = 1.0;  _energy_penalty = 1.0;  _eff_nh4_penalty = 0.0; _granule_stable = True

        # Apply cold-temperature reactor volume penalty (extended SRT needed)
        _cold_srt = inputs.srt_days * _reactor_penalty
        reactor_m3 = (vss_prod * _cold_srt * 1000.0) / (mlss * vss_tss)
        # Number of SBR reactors for continuous flow: typically 3 reactors in rotation
        n_reactors  = max(3, int(design_flow_mld / 10) + 2)   # scale with plant size
        vol_per_reactor = reactor_m3 / n_reactors
        hrt_hr = reactor_m3 / flow * 24.0

        # Flow balance tank volume (defined here for footprint + CAPEX use)
        fbt_vol_m3 = (flow / 24.0) * inputs.cycle_time_hours

        r.performance.reactor_volume_m3           = round(reactor_m3, 0)
        r.performance.hydraulic_retention_time_hr = round(hrt_hr, 1)
        # Footprint: SBR reactor basins + flow balance tank (if included)
        fbt_footprint = (fbt_vol_m3 / 4.0) if inputs.include_flow_balance_tank else 0
        r.performance.footprint_m2 = round(
            reactor_m3 / 4.5 * 1.15 + fbt_footprint,
            0,
        )
        r.performance.additional.update({
            "n_reactors":              n_reactors,
            "vol_per_reactor_m3":      round(vol_per_reactor, 0),
            "mlss_granular_mg_l":      mlss,
            "granule_diameter_mm":     inputs.granule_diameter_mm,
        })

        r.notes.add_assumption(
            f"Reactor: {reactor_m3:.0f} m³ in {n_reactors} SBR tanks "
            f"({vol_per_reactor:.0f} m³ each) at MLSS {mlss:.0f} mg/L"
        )

        # ── 3b. Peak flow assessment (AGS SBR) ────────────────────────────
        # AGS SBR handles peak flow through cycle compression and FBT buffering.
        # At peak flow the fill phase is compressed — the FBT must be large enough
        # to buffer the peak volume arriving during the non-fill phases of the cycle.
        #
        # Key constraints (de Kreuk 2007; Pronk 2015; WEF 2018 Ch.3):
        #   • Minimum fill time: 30 min (shorter risks granule washout from plug-flow disruption)
        #   • FBT must hold peak flow × non-fill duration without overflow
        #   • Feed volume per reactor per cycle must not exceed reactor working volume (~80%)
        #
        # Design:
        #   n_reactors in rotation → at any time (n_reactors−1) are in react/settle/decant
        #   Fill phase = cycle_time / n_reactors (approx, assuming equal phase splits)
        #   At peak flow: all incoming volume must be buffered in FBT during non-fill phases
        #
        peak_factor     = self._get_eng("peak_flow_factor", 1.5)
        peak_flow_m3d   = flow * peak_factor
        peak_flow_m3hr  = peak_flow_m3d / 24.0

        # Fill time per reactor per cycle (fraction of cycle allocated to fill phase)
        fill_fraction   = 1.0 / n_reactors   # 1 reactor filling while others react/settle/decant
        fill_time_hr    = inputs.cycle_time_hours * fill_fraction
        # Volume received by each reactor per fill at PEAK flow
        fill_vol_peak   = peak_flow_m3hr * fill_time_hr
        # Working volume limit: 80% of reactor volume (headspace for aeration + granule bed)
        working_vol     = vol_per_reactor * 0.80

        # FBT required at peak: must buffer (n-1)/n of the cycle volume at peak flow
        # Non-fill phases occupy (n_reactors-1)/n_reactors of the cycle
        non_fill_fraction = (n_reactors - 1) / n_reactors
        fbt_required_peak = peak_flow_m3hr * inputs.cycle_time_hours * non_fill_fraction
        fbt_adequate      = fbt_vol_m3 >= fbt_required_peak * 0.90   # allow 10% tolerance

        # Minimum fill time check (< 30 min risks washout)
        fill_time_min_at_peak = fill_time_hr * 60.0
        fill_time_ok  = fill_time_min_at_peak >= 30.0

        r.performance.additional.update({
            "peak_flow_factor":          peak_factor,
            "peak_flow_m3d":             round(peak_flow_m3d, 0),
            "fill_time_hr":              round(fill_time_hr, 2),
            "fill_time_min_at_peak":     round(fill_time_min_at_peak, 1),
            "fill_vol_per_reactor_m3":   round(fill_vol_peak, 0),
            "feed_per_fill_m3":          round(fill_vol_peak, 0),  # alias for QA rule P3
            "working_vol_per_reactor_m3": round(working_vol, 0),
            "peak_fill_ratio":           round(fill_vol_peak / max(working_vol, 1.0), 2),
            "fbt_required_at_peak_m3":   round(fbt_required_peak, 0),
            "fbt_provided_m3":           round(fbt_vol_m3, 0),
            "fbt_adequate":              fbt_adequate,
            "fill_time_adequate":        fill_time_ok,
        })

        # Warnings
        if not fbt_adequate and inputs.include_flow_balance_tank:
            r.notes.warn(
                f"⚠️ Flow balance tank ({fbt_vol_m3:.0f} m³) undersized for peak flow "
                f"({peak_factor:.1f}× = {peak_flow_m3d:.0f} m³/d). "
                f"Required: {fbt_required_peak:.0f} m³ to buffer non-fill phases. "
                "Increase FBT volume or reduce peak flow factor through upstream attenuation."
            )
        elif not inputs.include_flow_balance_tank:
            r.notes.warn(
                f"⚠️ No flow balance tank specified. At peak flow {peak_factor:.1f}× "
                f"({peak_flow_m3d:.0f} m³/d), upstream headworks must buffer "
                f"≥{fbt_required_peak:.0f} m³ during non-fill phases or cycle timing will be disrupted."
            )

        if fill_vol_peak > working_vol:
            r.notes.warn(
                f"⚠️ At peak flow, fill volume per reactor ({fill_vol_peak:.0f} m³) "
                f"exceeds 80% working volume ({working_vol:.0f} m³). "
                "Risk of reactor overflow or granule washout during fill phase. "
                "Increase reactor volume, add a reactor, or provide upstream flow attenuation."
            )

        if not fill_time_ok:
            r.notes.warn(
                f"⚠️ Fill time at peak flow = {fill_time_min_at_peak:.0f} min "
                "(< 30 min minimum for AGS plug-flow fill). "
                "Short fill times disrupt the feast/famine gradient required for granule stability. "
                "Consider: additional reactor, longer cycle time, or upstream flow attenuation."
            )

        r.notes.add_assumption(
            f"Peak flow assessment: {peak_factor:.1f}× ADF = {peak_flow_m3d:.0f} m³/d. "
            f"Fill time per reactor = {fill_time_min_at_peak:.0f} min "
            f"({'✓ adequate' if fill_time_ok else '⚠ marginal'}). "
            f"FBT {fbt_vol_m3:.0f} m³ vs {fbt_required_peak:.0f} m³ required at peak "
            f"({'✓ adequate' if fbt_adequate else '⚠ undersized'})."
        )

        # ── 4. Temperature correction and warnings ─────────────────────────
        T = inputs.design_temperature_celsius
        # Nitrification Arrhenius correction: theta = 1.072 (Metcalf)
        theta_nit = 1.072
        T_factor  = theta_nit ** (T - 20.0)

        # ── Granule stability and performance penalties at cold temperature ──
        # Literature basis:
        #   van Dijk et al. (2020) — full-scale Nereda below 10°C: granule fragmentation,
        #     deteriorating settling, washout events. SVI increases from ~50 to >200 mL/g.
        #   de Kreuk (2007) — bio-P deteriorates below 15°C (PAO activity suppressed).
        #   Pronk et al. (2015) — nitrification unreliable below 12°C without SRT extension.
        #
        # Implementation: penalise effluent quality and add volume/SRT buffer for cold climates.

        if T < 10.0:
            # Critical: granule fragmentation risk; plant may not achieve stable operation
            r.notes.warn(
                f"⚠️ CRITICAL: T={T}°C — below practical minimum for AGS. "
                "Full-scale AGS plants (van Dijk 2020) show granule fragmentation, "
                "SVI > 200 mL/g, and washout events below 10°C. "
                "This technology is NOT recommended at this temperature without thermal management. "
                "Consider heated reactor, BNR, or IFAS instead."
            )
            # Penalise: effluent quality severely impaired, energy up for mixing
            pass  # penalties already set above in section 3

        elif T < 12.0:
            r.notes.warn(
                f"⚠️ T={T}°C — granule stability at risk. "
                f"Nitrification rate = {T_factor*100:.0f}% of 20°C. "
                "Granule fragmentation possible (van Dijk 2020). "
                "SRT must be extended; biological P removal unreliable. "
                "Recommend: chemical P backup, tank insulation, SRT extension."
            )
            pass  # penalties already set above in section 3

        elif T < 15.0:
            r.notes.warn(
                f"⚠️ T={T}°C — approaching granule stability boundary. "
                f"Nitrification reduced to {T_factor*100:.0f}%. "
                "Biological P removal may become unreliable (de Kreuk 2007). "
                "Enable chemical P polish for reliable TP compliance."
            )
            pass  # penalties already set above in section 3

        else:
            pass  # penalties already set above in section 3

        # C:N ratio check — granule feast/famine requires sufficient organic loading
        c_n_ratio = inf["bod_mg_l"] / max(inf["tn_mg_l"], 1.0)
        if c_n_ratio < 5.0:
            r.notes.warn(
                f"⚠ Influent BOD/TN ratio = {c_n_ratio:.1f} (< 5.0). "
                "Low C:N ratios reduce denitrification capacity and can destabilise "
                "granule structure. Consider supplemental carbon or pre-fermentation."
            )

        # Bio-P and temperature
        if inputs.biological_p_removal and T < 15.0 and not inputs.chemical_p_polish:
            r.notes.warn(
                f"⚠ Biological P removal at {T}°C may be unreliable. "
                "Enable chemical P polish (FeCl3) for cold climates to maintain TP < 0.5 mg/L."
            )

        # ── 5. Oxygen demand and aeration energy ───────────────────────────
        # AGS alpha slightly higher than CAS (less mixed liquor boundary layer effect)
        alpha   = 0.65   # de Kreuk 2007 (range 0.60–0.70)
        sae_std = self._get_eng("standard_aeration_efficiency_kg_o2_kwh", 1.8)
        sae     = sae_std * alpha

        # SND in granule provides partial denitrification oxygen credit (50–70%)
        snd_dn_frac = 0.60 if inputs.simultaneous_n_removal else 0.30
        nh4_frac = self._get_eng("influent_nh4_mg_l", 35.0) / max(inf["tn_mg_l"], 1.0)
        o2_c     = bod_removed * (1.0 - 1.42 * y_obs)   # carbonaceous (Metcalf Eq 7-57)
        o2_n     = 4.57 * tn_load * nh4_frac * 0.90 * T_factor  # nitrification (T-corrected)
        o2_dn    = 2.86 * tn_removed * snd_dn_frac               # SND credit
        o2_kg    = max(0.0, o2_c + o2_n - o2_dn)

        # Cold temperature energy: lower nitrification O2 reduces aeration slightly,
        # but longer SBR cycle times (more mixing, more cycles) offset this.
        # For concept planning, apply penalty to base 20°C O2 demand to avoid
        # showing decreasing energy with temperature (would mislead planners).
        _o2_base_T20 = o2_kg / max(0.5, T_factor)   # reverse Arrhenius to get base demand
        aer_kwh = (max(o2_kg, _o2_base_T20 * 0.90) / sae) * _energy_penalty
        mix_kwh = reactor_m3 * 0.005 * 24.0   # 5 W/m³ low-speed agitators between cycles
        dec_kwh = flow * 0.005                  # Decant pumping ~5 Wh/m³

        r.energy.aeration_kwh_day = round(aer_kwh, 1)
        r.energy.mixing_kwh_day   = round(mix_kwh, 1)
        # AGS SBR: no RAS or MLR (settled sludge stays in reactor — no clarifier)
        # Pumping: decant discharge + WAS feed pump
        # Ancillary: 50 kWh/ML (lower than BNR because no clarifier drives,
        # no RAS/WAS controls — saves ~15 kWh/ML vs CAS baseline of 70)
        ancillary_kwh = 50.0 * design_flow_mld
        r.energy.pumping_kwh_day  = round(dec_kwh + ancillary_kwh, 1)
        r.notes.add_assumption(
            f"Pumping: decant={dec_kwh:.0f} + ancillary={ancillary_kwh:.0f} kWh/day "
            "(no RAS or MLR — AGS SBR retains sludge; ancillary 50 kWh/ML vs 70 for BNR "
            "because no clarifier drives or RAS/WAS controls)"
        )

        r.notes.add_assumption(
            f"alpha = {alpha} (AGS, de Kreuk 2007); "
            f"SND denitrification fraction = {snd_dn_frac:.0%}; "
            f"O2 demand = {o2_kg:.0f} kg/day "
            f"(carbonaceous {o2_c:.0f} + nit {o2_n:.0f} − SND credit {o2_dn:.0f})"
        )

        # ── 6. Chemical consumption ────────────────────────────────────────
        chems: Dict[str, float] = {}
        # Compute ferric dose when chemical P polish needed
        # (explicit flag OR TP target < 0.5 mg/L where biological AGS alone insufficient)
        _needs_chem_p = inputs.chemical_p_polish or eff_tp < 0.5
        if _needs_chem_p:
            p_mol = tp_removed * 1000.0 / 31.0
            chems["ferric_chloride_kg_day"] = round(p_mol * 2.5 * 162.2 / 1000.0, 2)
            r.notes.add_assumption(
                "Chemical P polish: FeCl3 dose 2.5 mol Fe/mol P (WEF MOP 32)"
            )
        r.chemical_consumption = chems

        # ── 7. Effluent quality ────────────────────────────────────────────
        r.performance.effluent_bod_mg_l = eff_bod
        r.performance.effluent_tss_mg_l = eff_tss
        # Cold temperature degrades nitrification — effluent NH4 increases
        r.performance.effluent_nh4_mg_l = round(
            min(eff_nh4 + _eff_nh4_penalty,
                inf["tn_mg_l"] * self._get_eng("influent_nh4_mg_l", 35.0) /
                max(self._get_eng("influent_tkn_mg_l", 45.0), 1.0) * 0.8),
            2
        )
        r.performance.effluent_tn_mg_l  = eff_tn
        _bio_p_ok = inputs.biological_p_removal and T >= 15.0
        r.performance.effluent_tp_mg_l  = (
            eff_tp if _bio_p_ok or inputs.chemical_p_polish or eff_tp < 0.5
            else min(eff_tp + 0.5, 1.5)
        )
        r.performance.additional.update({
            "o2_demand_kg_day":          round(o2_kg, 0),
            "snd_dn_fraction":           snd_dn_frac,
            "t_factor_nitrification":    round(T_factor, 3),
            "lrv_cryptosporidium":       1.5,   # Modest credit from fast-settling granules
            "cycle_time_hours":          inputs.cycle_time_hours,
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
            "AGS bio-P removal can become unreliable at temperatures < 12°C or "
            "with industrial discharges containing competing organic acids."
        )
        r.notes.add_limitation(
            "Startup requires 3–6 months of granule formation. Budget for inoculation "
            "sludge from an operating Nereda® plant if commissioning timeline is critical."
        )

        # ── 9. Risk ───────────────────────────────────────────────────────
        r.risk.reliability_risk       = "Moderate"   # Granule stability at low T / shock load
        r.risk.regulatory_risk        = "Low"
        r.risk.technology_maturity    = "Commercial"  # ~80 full-scale plants (2024)
        r.risk.operational_complexity = "Moderate"   # SBR cycle management, granule monitoring
        r.risk.site_constraint_risk   = "Low"
        r.risk.implementation_risk    = "Moderate"   # Limited vendors; specialist startup required

        r.risk.additional_flags["granule_stability_risk"] = (
            "Critical" if T < 10.0 else "High" if T < 12.0 else "Moderate" if T < 15.0 else "Low"
        )
        r.performance.additional["granule_stable"] = _granule_stable
        r.performance.additional["cold_reactor_penalty"] = round(_reactor_penalty, 2)
        r.performance.additional["design_temperature_celsius"] = T
        r.risk.additional_flags["bio_p_reliability_risk"] = (
            "High" if T < 12.0 else "Moderate" if T < 15.0 else "Low"
        )
        r.risk.additional_flags["startup_granule_formation_risk"] = "Moderate"

        # ── 10. CAPEX ─────────────────────────────────────────────────────
        # Flow balance tank: buffers continuous influent during react/settle/decant.
        # Sized for 1 full cycle time at average flow (calculated above).
        r.capex_items = []
        if inputs.include_flow_balance_tank:
            r.capex_items.append(CostItem(
                "Flow balance tank",
                "aeration_tank_per_m3",
                fbt_vol_m3,
                "m³",
                notes=(
                    f"Buffers {inputs.cycle_time_hours}h SBR cycle × "
                    f"{flow/24:.0f} m³/hr avg flow = {fbt_vol_m3:.0f} m³. "
                    "Required for continuous-flow installations."
                ),
            ))

        r.capex_items += [
            CostItem(
                "AGS SBR reactor tankage",
                "aeration_tank_per_m3",
                reactor_m3,
                "m³",
                notes=f"{n_reactors} tanks × {vol_per_reactor:.0f} m³ each",
            ),
            CostItem(
                "Blower system + fine bubble diffusers",
                "blower_per_kw",
                aer_kwh / 24.0,
                "kW installed",
                notes="Blower + FBDA diffuser floor; AGS high-intensity aeration during feast phase",
            ),
            CostItem(
                "Decanter mechanisms",
                "aeration_tank_per_m3",
                n_reactors,
                "units",
                unit_cost_override=150000.0,
                notes=f"{n_reactors} tipping-weir decanters @ $150k each",
            ),
            CostItem(
                "SBR automation + controls",
                "aeration_tank_per_m3",
                n_reactors,
                "units",
                unit_cost_override=200000.0,
                notes="SBR cycle timers, DO/TSS sensors, SCADA per reactor @ $200k each",
            ),
            CostItem(
                "Granule wash + selection system",
                "aeration_tank_per_m3",
                1,
                "system",
                unit_cost_override=300000.0,
                notes="Granule classifiers, wash troughs, drain return — plant-wide",
            ),
            CostItem(
                "Discharge pumps",
                "pump_per_kw",
                dec_kwh / 24.0,
                "kW installed",
            ),
        ]

        r.performance.additional["fbt_volume_m3"] = round(fbt_vol_m3, 0) if inputs.include_flow_balance_tank else 0
        # ── 11. OPEX ──────────────────────────────────────────────────────
        r.opex_items = [
            CostItem(
                "Electricity — aeration",
                "electricity_per_kwh",
                aer_kwh,
                "kWh/day",
            ),
            CostItem(
                "Electricity — mixing & decant",
                "electricity_per_kwh",
                mix_kwh + dec_kwh,
                "kWh/day",
            ),
            CostItem(
                "Sludge disposal",
                "sludge_disposal_per_tds",
                total_sludge / 1000.0,
                "t DS/day",
            ),
        ]
        # Auto-trigger chemical P polish if TP target < 0.5 mg/L
        # AGS biological P is reliable to ~0.3-0.5 mg/L; below this, chemical polish needed.
        apply_chem_p = inputs.chemical_p_polish or eff_tp < 0.5
        if apply_chem_p and "ferric_chloride_kg_day" in chems:
            r.opex_items.append(CostItem(
                "Ferric chloride (P polish)",
                "ferric_chloride_per_kg",
                chems["ferric_chloride_kg_day"],
                "kg/day",
            ))

        # ── 12. Assumptions log ───────────────────────────────────────────
        r.assumptions_used = {
            "srt_days":                   inputs.srt_days,
            "mlss_mg_l":                  mlss,
            "y_obs_kgvss_kgbod":          y_obs,
            "alpha_factor":               alpha,
            "sae_process_kg_o2_kwh":      round(sae, 2),
            "snd_dn_fraction":            snd_dn_frac,
            "n2o_ef":                     n2o_ef,
            "design_temperature_celsius": T,
            "t_factor_nitrification":     round(T_factor, 3),
            "n_reactors":                 n_reactors,
        }

        # ── 13. Finalise ──────────────────────────────────────────────────
        return r.finalise(
            design_flow_mld,
            influent_bod_mg_l=inf["bod_mg_l"],
            influent_nh4_mg_l=inf["tn_mg_l"] * nh4_frac,
            influent_tn_mg_l=inf["tn_mg_l"],
            influent_tp_mg_l=inf["tp_mg_l"],
        )
