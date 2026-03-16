"""
domains/wastewater/technologies/sidestream_pna.py

Sidestream Partial Nitritation / Anammox (PN/A)
================================================
High-rate nitrogen removal from concentrated reject water produced by
dewatering of anaerobically digested sludge (centrate / filtrate).

Removing 80–90% of reject-water NH4 before it recycles to the main
biological train reduces the main plant TN load by 15–30% and cuts
aeration energy and external carbon demand accordingly.

Process chemistry
-----------------
  Partial nitritation (AOB only):
    NH4+ + 0.75 O2 → 0.5 NO2- + 0.5 NH4+    (aerobic — AOB)

  Anammox (anaerobic ammonium oxidation):
    NH4+ + NO2-  → N2 + 2H2O                 (anoxic  — Planctomycetes)

  Net reaction:
    NH4+ + 0.75 O2 → 0.5 N2 + 1.5 H2O
    O2 requirement: ~1.9 kg O2 / kg N  (vs 4.57 for full nitrification-denitrification)

Key process parameters
----------------------
• NO2 / NH4 ratio ≈ 1.0:1.0 entering Anammox (maintained by DO and pH control)
• Anammox growth rate very slow (doubling time ~11 days at 30°C)
  → startup: 3–6 months; inhibitor recovery: weeks
• N2O emission factor for PN/A: 2–5% of N removed (higher than CAS)
  (Lackner 2014: mean 4%; range 0.1–10%)

Modes
-----
  DEMON®:         integrated single-reactor with pH-controlled intermittent aeration
  SHARON-Anammox: two-step (SHARON nitritation reactor → Anammox reactor)
  Mainstream:     treating the main flow at low NH4 concentration (emerging)

References
----------
  - Lackner et al. (2014) Global survey of Anammox full-scale plants — Water Research
  - Siegrist et al. (2008) Math model of single-stage N removal via PN/A
  - Kartal et al. (2010) Anammox in the water cycle — Science 328
  - Kampschreur et al. (2009) N2O emission during biological N removal — WR 43
  - Wett (2007) Development and implementation of DEMON® — Water Sci. Tech.
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
class SidestreamPNAInputs:
    """Design parameters for the Sidestream PN/A reactor."""

    # ── Process mode ──────────────────────────────────────────────────────
    mode: str = "demon"
    # "demon"         — integrated single-reactor with pH-based control (most common)
    # "sharon_anammox" — two-stage: SHARON + Anammox reactors
    # "mainstream"    — applied to main plant flow (emerging; not full-scale proven)

    # ── Sidestream characterisation ───────────────────────────────────────
    sidestream_nh4_mg_l: float = 800.0
    # NH4-N concentration in reject water (mg/L).
    # Typical centrate from mesophilic digestion: 600–1200 mg/L NH4-N.

    sidestream_flow_fraction: float = 0.01
    # Sidestream flow as a fraction of the main plant design flow.
    # Typical centrate return: 0.5–2.0% of design flow.

    # ── Process temperature ───────────────────────────────────────────────
    temperature_celsius: float = 30.0
    # Sidestream temperature (°C). Reject water is typically warm (30–35°C)
    # from mesophilic digesters. Anammox activity drops sharply below 20°C.

    # ── Anammox performance ───────────────────────────────────────────────
    n_removal_efficiency: float = 0.85
    # Fraction of sidestream NH4-N removed (0.70–0.95).
    # 0.85 is a safe design value for established full-scale plants.

    # ── N2O emission factor ───────────────────────────────────────────────
    n2o_emission_factor: float = 0.04
    # kg N2O per kg N removed. PN/A higher than CAS due to NO2 intermediate.
    # Lackner 2014 central estimate: 0.04 (range 0.001–0.10).

    _field_bounds: dict = field(default_factory=lambda: {
        "sidestream_nh4_mg_l":    (100, 2000),
        "sidestream_flow_fraction": (0.001, 0.05),
        "temperature_celsius":    (15, 45),
        "n_removal_efficiency":   (0.50, 0.95),
        "n2o_emission_factor":    (0.001, 0.15),
    }, repr=False)


# ─────────────────────────────────────────────────────────────────────────────
# TECHNOLOGY CLASS
# ─────────────────────────────────────────────────────────────────────────────

class SidestreamPNATechnology(BaseTechnology):
    """
    Sidestream PN/A (Anammox) — screening-level planning model.

    NOTE: this module sizes the sidestream reactor only.
    Main-plant energy and carbon savings are calculated and reported
    as reference values, but are NOT deducted from this module's cost
    or energy accounts (to avoid double-counting with the main plant module).

    Advantages
    ----------
    - No external carbon required (unlike denitrification)
    - Only 40% of the aeration of full nitrification-denitrification
    - Very low sludge production (Anammox yield ~0.03 kgVSS/kgN)
    - Reduces main plant N load 15–30%, cutting aeration + chemical costs

    Limitations
    -----------
    - Anammox bacteria extremely sensitive to DO, temperature, and inhibitors
    - Startup requires 3–6 months of granule/biomass establishment
    - Very high N2O emission factor (2–10%) vs CAS (0.5–2%)
    - Mainstream application (treating main flow) not yet full-scale proven
    """

    @property
    def technology_code(self) -> str: return "sidestream_pna"

    @property
    def technology_name(self) -> str: return "Sidestream PN/A (Anammox)"

    @property
    def technology_category(self) -> str: return "Biological Treatment"

    @property
    def requires_upstream(self) -> list: return ["ad_chp"]

    @classmethod
    def input_class(cls) -> Type: return SidestreamPNAInputs

    def calculate(
        self,
        design_flow_mld: float,
        inputs: SidestreamPNAInputs,
    ) -> TechnologyResult:

        r = TechnologyResult(
            technology_name=self.technology_name,
            technology_code=self.technology_code,
            technology_category=self.technology_category,
            description=(
                f"Sidestream PN/A reactor ({inputs.mode.upper().replace('_','-')}) "
                f"removing {inputs.n_removal_efficiency*100:.0f}% of reject-water NH4 "
                "before it recycles to the main plant."
            ),
        )

        # ── 1. Sidestream flow and load ────────────────────────────────────
        ss_flow_m3day  = design_flow_mld * 1000.0 * inputs.sidestream_flow_fraction
        nh4_load_kg    = ss_flow_m3day * inputs.sidestream_nh4_mg_l / 1000.0
        n_removed_kg   = nh4_load_kg * inputs.n_removal_efficiency
        nh4_remaining  = nh4_load_kg * (1.0 - inputs.n_removal_efficiency)

        r.notes.add_assumption(
            f"Sidestream: {ss_flow_m3day:.1f} m³/day at "
            f"{inputs.sidestream_nh4_mg_l:.0f} mg/L NH4-N "
            f"({inputs.sidestream_flow_fraction*100:.1f}% of main Q = {design_flow_mld:.1f} MLD)"
        )
        r.notes.add_assumption(
            f"N removal: {inputs.n_removal_efficiency*100:.0f}% of sidestream NH4 "
            f"→ {n_removed_kg:.1f} kg N/day removed, "
            f"{nh4_remaining:.1f} kg N/day returns to main plant"
        )

        # ── 2. Temperature check ───────────────────────────────────────────
        T = inputs.temperature_celsius
        if T < 20.0:
            r.notes.warn(
                f"⚠ Sidestream temperature {T}°C is below 20°C. "
                "Anammox activity roughly halves for every 10°C reduction below 30°C. "
                "Consider insulating the sidestream line or heating the reactor. "
                "Below 15°C, Anammox activity becomes negligible and the process fails "
                "(Lackner 2014)."
            )
        if T > 40.0:
            r.notes.warn(
                f"⚠ Sidestream temperature {T}°C may inhibit Anammox. "
                "Activity drops above 40°C (optimum 30–37°C)."
            )

        # ── 3. Oxygen demand for partial nitritation only ─────────────────
        # O2 for PN/A: ~1.9 kg O2 / kg N (vs 4.57 for full nitrification-denitrification)
        # This is a fundamental advantage of the Anammox pathway.
        o2_pna_kg  = n_removed_kg * 1.9

        alpha      = 0.70   # Concentrated sidestream; higher than main plant
        sae_std    = self._get_eng("standard_aeration_efficiency_kg_o2_kwh", 1.8)
        sae        = sae_std * alpha
        aer_kwh    = o2_pna_kg / sae

        r.energy.aeration_kwh_day = round(aer_kwh, 1)

        r.notes.add_assumption(
            f"O2 for partial nitritation: 1.9 kg O2 / kg N "
            f"(vs 4.57 full N removal — 58% O2 savings); "
            f"alpha = {alpha}, SAE_process = {sae:.2f} kg O2/kWh"
        )

        # ── 4. Main-plant benefit (reference values) ───────────────────────
        # O2 saved on main plant = n_removed × (4.57 - 1.9) (no longer nitrified there)
        # These are reference values only — not deducted from this module's accounts.
        o2_saved_main     = n_removed_kg * (4.57 - 1.9)
        kwh_saved_main    = o2_saved_main / sae
        methanol_saved    = n_removed_kg * 4.0 * 0.15   # 15% denitrification deficit saved
        n_load_reduction  = n_removed_kg / max(
            design_flow_mld * 1000.0 * self._get_eng("influent_tn_mg_l", 45.0) / 1000.0, 1.0
        ) * 100.0   # % of whole-plant TN load

        r.notes.add_limitation(
            "Main-plant energy and carbon savings (below) are reference values. "
            "They are NOT deducted from this module's cost/energy accounts. "
            "Capture them at the whole-plant comparison level to avoid double-counting."
        )

        # ── 5. Effluent from the sidestream reactor ────────────────────────
        # The treated sidestream returns to the main plant liquid train.
        # Effluent NH4 = remaining NH4 in sidestream (mg/L)
        ss_effluent_nh4 = inputs.sidestream_nh4_mg_l * (1.0 - inputs.n_removal_efficiency)
        # BOD: very low — Anammox does not remove organic carbon
        ss_effluent_bod = 30.0   # Typical: reject water BOD is low (~30–80 mg/L)
        # TN out: NH4 remaining + any NO3 (small in PN/A)
        ss_effluent_tn  = ss_effluent_nh4 * 1.15   # 15% as NO3 and N2O

        # Set on performance typed sub-result so finalise() can compute removal pcts
        # The "influent" here is the sidestream, not the whole plant
        r.performance.effluent_nh4_mg_l = round(ss_effluent_nh4, 0)
        r.performance.effluent_tn_mg_l  = round(ss_effluent_tn, 0)
        r.performance.effluent_bod_mg_l = ss_effluent_bod   # not changed by PN/A

        # ── 6. Sludge production ───────────────────────────────────────────
        # Anammox yield is extremely low: ~0.03 kgVSS/kgN (Lackner 2014)
        y_anammox   = 0.03
        sludge_kg   = n_removed_kg * y_anammox
        reactor_m3  = ss_flow_m3day * 0.5   # ~12 h HRT for granular SBR
        hrt_hr      = reactor_m3 / ss_flow_m3day * 24.0

        r.sludge.biological_sludge_kgds_day = round(sludge_kg, 2)
        r.sludge.vs_fraction  = 0.75   # Granular Anammox biomass
        r.sludge.feed_ts_pct  = 1.5

        r.notes.add_assumption(
            f"Anammox yield = {y_anammox} kgVSS/kgN (Lackner 2014 — very low; "
            "Anammox slow growth rate Td ≈ 11d at 30°C)"
        )

        # ── 7. Physical sizing ─────────────────────────────────────────────
        r.performance.reactor_volume_m3           = round(reactor_m3, 0)
        r.performance.hydraulic_retention_time_hr = round(hrt_hr, 1)
        r.performance.footprint_m2                = round(reactor_m3 * 0.20, 0)

        r.performance.additional.update({
            "sidestream_flow_m3_day":            round(ss_flow_m3day, 1),
            "nh4_load_sidestream_kg_n_day":      round(nh4_load_kg, 1),
            "n_removed_kg_day":                  round(n_removed_kg, 1),
            "n_removal_efficiency_pct":          round(inputs.n_removal_efficiency * 100, 0),
            "sidestream_effluent_nh4_mg_l":      round(ss_effluent_nh4, 0),
            # Main-plant benefit reference values
            "main_plant_n_reduction_kg_day":     round(n_removed_kg, 1),
            "main_plant_n_load_reduction_pct":   round(n_load_reduction, 1),
            "main_plant_energy_saved_kwh_day":   round(kwh_saved_main, 0),
            "main_plant_methanol_saved_kg_day":  round(methanol_saved, 2),
            "no_external_carbon_required":       True,
            "o2_per_kg_n_pna":                  1.9,
            "mode":                              inputs.mode,
        })

        # ── 8. Scope 1 N2O emissions ───────────────────────────────────────
        # PN/A N2O EF is significantly higher than CAS due to the NO2 intermediate
        n2o_ef  = inputs.n2o_emission_factor
        n2o_gwp = self._get_eng("n2o_gwp", 273)
        r.carbon.n2o_biological_tco2e_yr = round(
            n_removed_kg * 1000.0 * n2o_ef * 365 * n2o_gwp / 1e6, 1
        )

        r.notes.add_assumption(
            f"N2O EF = {n2o_ef*100:.0f}% of N removed "
            "(PN/A elevated EF due to NO2 intermediate; Lackner 2014 mean; range 0.1–10%). "
            "This is the dominant Scope 1 risk — measure on site for detailed reporting."
        )

        # Inhibitor warning (critical for Anammox)
        r.notes.warn(
            "Anammox is sensitive to: free ammonia > 20 mg/L, nitrous acid > 0.02 mg/L, "
            "heavy metals (Cu, Zn), antibiotics, salinity > 3 g/L, and dissolved O2 > 0.5 mg/L. "
            "Characterise the centrate for inhibitors before design."
        )

        # Startup note
        r.notes.add_limitation(
            "Anammox requires 3–6 months to establish from activated sludge seed. "
            "Budget for inoculation sludge from an operating Anammox plant or "
            "commercial granular biomass to reduce startup time to 4–8 weeks."
        )

        # Mainstream note
        if inputs.mode == "mainstream":
            r.notes.warn(
                "Mainstream Anammox (applying PN/A to the main plant flow at low NH4 concentration) "
                "is not yet demonstrated at full scale with reliable TN removal. "
                "Treat as R&D / pilot scale for planning purposes only."
            )

        # ── 9. Risk ───────────────────────────────────────────────────────
        r.risk.reliability_risk       = "Moderate"   # Anammox sensitive to upsets
        r.risk.regulatory_risk        = "Low"
        r.risk.technology_maturity    = (
            "Commercial"     # 100+ full-scale sidestream plants (2024)
            if inputs.mode != "mainstream" else
            "Emerging"       # Mainstream not full-scale proven
        )
        r.risk.operational_complexity = "High"       # Tight DO, pH, temperature control required
        r.risk.site_constraint_risk   = "Low"
        r.risk.implementation_risk    = (
            "Moderate" if inputs.mode != "mainstream" else "High"
        )

        r.risk.additional_flags["anammox_inhibition_risk"]  = "Moderate"
        r.risk.additional_flags["low_temperature_risk"]     = (
            "High" if T < 20.0 else "Moderate" if T < 25.0 else "Low"
        )
        r.risk.additional_flags["startup_duration_risk"]    = "Moderate"
        r.risk.additional_flags["n2o_emission_uncertainty"] = "High"  # ±10× range

        # ── 10. CAPEX ─────────────────────────────────────────────────────
        r.capex_items = [
            CostItem(
                "PN/A reactor vessel (granular SBR or carousel)",
                "concrete_tank_per_m3",
                reactor_m3,
                "m³",
                notes=f"{inputs.mode.upper()} configuration; includes covers and gas collection",
            ),
            CostItem(
                "Aeration system (intermittent, DO-controlled)",
                "blower_per_kw",
                aer_kwh / 24.0,
                "kW installed",
            ),
            CostItem(
                "Process control system (DO, pH, N2O probe, NH4)",
                "scada_per_m3_reactor",
                reactor_m3,
                "m³",
                notes="Tight DO control (<0.2 mg/L) and pH = 7.5–8.0 essential for Anammox",
            ),
        ]
        if inputs.mode == "sharon_anammox":
            r.capex_items.insert(0, CostItem(
                "SHARON pre-treatment reactor",
                "concrete_tank_per_m3",
                reactor_m3 * 0.30,   # SHARON HRT ~1 day, smaller than Anammox reactor
                "m³",
                notes="SHARON: partial nitritation only; separate from Anammox reactor",
            ))

        # ── 11. OPEX ──────────────────────────────────────────────────────
        r.opex_items = [
            CostItem(
                "Electricity — PN/A aeration",
                "electricity_per_kwh",
                aer_kwh,
                "kWh/day",
            ),
            CostItem(
                "Sludge disposal (very low quantity)",
                "sludge_disposal_per_tds",
                sludge_kg / 1000.0,
                "t DS/day",
            ),
        ]

        r.notes.add_limitation(
            "CAPEX excludes: centrate storage buffer tank, odour control "
            "(H2S/NH3 from open sidestream), and any structural upgrades to "
            "dewatering building for reactor installation."
        )

        # ── 12. Assumptions log ───────────────────────────────────────────
        r.assumptions_used = {
            "mode":                     inputs.mode,
            "sidestream_nh4_mg_l":      inputs.sidestream_nh4_mg_l,
            "sidestream_flow_fraction": inputs.sidestream_flow_fraction,
            "n_removal_efficiency":     inputs.n_removal_efficiency,
            "temperature_celsius":      T,
            "alpha_factor":             alpha,
            "sae_process_kg_o2_kwh":    round(sae, 2),
            "o2_per_kg_n_pna":          1.9,
            "y_anammox_kgvss_kgn":      y_anammox,
            "n2o_ef_fraction":          n2o_ef,
        }

        # ── 13. Finalise ──────────────────────────────────────────────────
        # Pass sidestream concentrations as "influent" for removal % calculation.
        # This gives sidestream-specific removal efficiencies, not whole-plant values.
        return r.finalise(
            design_flow_mld,
            influent_nh4_mg_l=inputs.sidestream_nh4_mg_l,
            influent_tn_mg_l=inputs.sidestream_nh4_mg_l * 1.10,   # ~10% as organic N
            influent_bod_mg_l=ss_effluent_bod * 3.0,               # typical reject water BOD
        )
