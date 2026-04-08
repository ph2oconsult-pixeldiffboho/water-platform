"""
BioPoint V1 — Preconditioning Engine.
Models upstream feedstock conditioning steps and their downstream impact.

Evaluates four preconditioning levers:
  1. AD optimisation (HRT extension, loading rate)
  2. THP pre-treatment (thermal hydrolysis)
  3. Improved dewatering (belt press → centrifuge → advanced)
  4. Co-digestion (food waste, FOG, industrial organics)

For each conditioning scenario, calculates the modified:
  - Feed DS%
  - VS fraction
  - GCV (on DS basis)
  - Drying energy requirement (at target DS)
  - Energy balance improvement
  - Whether the 28–30% DS threshold is achievable

ph2o Consulting — BioPoint V1
"""

from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# DEWATERING TECHNOLOGY REFERENCE
# DS% achievable by technology (M&E 5th ed. + operational benchmarks)
# ---------------------------------------------------------------------------

DEWATERING_DS_REFERENCE = {
    "gravity_thickener":    {"min": 4.0,  "mid": 6.0,  "max": 8.0,   "note": "Pre-thickening only"},
    "belt_press":           {"min": 18.0, "mid": 22.0, "max": 26.0,  "note": "Standard — WAS typical"},
    "centrifuge":           {"min": 20.0, "mid": 24.0, "max": 28.0,  "note": "Common baseline"},
    "centrifuge_polymer":   {"min": 22.0, "mid": 26.0, "max": 30.0,  "note": "Optimised polymer dosing"},
    "screw_press":          {"min": 18.0, "mid": 22.0, "max": 26.0,  "note": "Low energy; lower DS than centrifuge"},
    "filter_press":         {"min": 28.0, "mid": 33.0, "max": 38.0,  "note": "High DS; capital intensive"},
    "thp_centrifuge":       {"min": 28.0, "mid": 32.0, "max": 38.0,  "note": "Post-THP: EPS breakdown → excellent dewatering"},
    "advanced_dryer_press": {"min": 35.0, "mid": 40.0, "max": 45.0,  "note": "Thermal press / membrane filter"},
}

# THP impact on downstream parameters (reference: Cambi / Lysotherm operational data)
THP_IMPACTS = {
    "vsr_uplift_pct_points":    10.0,   # Absolute VSR improvement
    "biogas_uplift_pct":        20.0,   # % more biogas vs base MAD
    "dewatering_ds_uplift_pct_points": 8.0,  # DS% improvement post-dewatering
    "gcv_reduction_pct":        12.0,   # GCV falls (VS destroyed by THP + digestion)
    "steam_demand_mj_per_tts":  950.0,  # Steam consumption kJ/tTS feed
    "pathogen_class":           "CLASS_A",
}

# Co-digestion substrates — GCV and VS impact on blend
CO_DIGESTION_SUBSTRATES = {
    "food_waste":       {"gcv_mj_per_kg_ds": 18.0, "vs_pct": 90.0, "biogas_uplift_pct": 30.0},
    "fog":              {"gcv_mj_per_kg_ds": 32.0, "vs_pct": 95.0, "biogas_uplift_pct": 50.0},  # Fats/oils/grease
    "industrial_hc":    {"gcv_mj_per_kg_ds": 22.0, "vs_pct": 88.0, "biogas_uplift_pct": 35.0},
    "green_waste":      {"gcv_mj_per_kg_ds": 14.0, "vs_pct": 80.0, "biogas_uplift_pct": 15.0},
}


# ---------------------------------------------------------------------------
# DATACLASSES
# ---------------------------------------------------------------------------

@dataclass
class PreconditioningScenario:
    """One upstream conditioning configuration."""
    scenario_id: str = ""
    scenario_name: str = ""
    description: str = ""

    # Levers applied
    ad_optimised: bool = False
    thp_applied: bool = False
    dewatering_technology: str = "centrifuge"
    co_digestion_substrate: Optional[str] = None
    co_digestion_fraction: float = 0.0    # 0–1, fraction of feed that is co-substrate

    # Resulting feed quality (after conditioning, before drying)
    feed_ds_pct: float = 0.0
    feed_vs_pct: float = 0.0
    feed_gcv_mj_per_kg_ds: float = 0.0
    vsr_achieved_pct: float = 0.0

    # Biogas / energy impact
    biogas_uplift_factor: float = 1.0    # Multiplier on base biogas
    chp_additional_kwh_d: float = 0.0

    # Drying impact (vs baseline feed DS%)
    drying_energy_reduction_kwh_d: float = 0.0   # Less water to evaporate
    water_saved_t_d: float = 0.0
    threshold_28pct_reached: bool = False
    threshold_30pct_reached: bool = False

    # THP energy cost
    thp_steam_demand_mj_d: float = 0.0

    # Summary verdict
    net_energy_improvement_kwh_d: float = 0.0
    conditioning_viable: bool = True
    conditioning_notes: list = field(default_factory=list)


@dataclass
class PreconditioningAssessment:
    """Full preconditioning assessment — all scenarios compared."""
    base_ds_pct: float = 0.0
    base_gcv: float = 0.0
    base_vs_pct: float = 0.0
    ds_tpd: float = 0.0

    scenarios: list = field(default_factory=list)    # List[PreconditioningScenario]

    # Best scenario for reaching 28% DS
    best_for_ds_threshold: Optional[PreconditioningScenario] = None
    # Best scenario for energy improvement
    best_for_energy: Optional[PreconditioningScenario] = None

    # Threshold analysis
    any_scenario_reaches_28pct: bool = False
    any_scenario_reaches_30pct: bool = False
    min_ds_achievable_pct: float = 0.0
    max_ds_achievable_pct: float = 0.0

    assessment_narrative: str = ""


# ---------------------------------------------------------------------------
# MAIN ENGINE
# ---------------------------------------------------------------------------

def run_preconditioning(feedstock_inputs, assets_inputs,
                         drying_target_ds_pct: float = 78.0) -> PreconditioningAssessment:
    """
    Evaluate all upstream preconditioning scenarios for a given feedstock.
    Returns ranked scenarios with energy and DS% impact.
    """
    fs = feedstock_inputs
    ds_tpd = fs.dry_solids_tpd
    base_ds = fs.dewatered_ds_percent
    base_vs = fs.volatile_solids_percent
    base_gcv = fs.gross_calorific_value_mj_per_kg_ds
    base_vsr = 45.0   # Typical baseline MAD VSR for secondary sludge

    # Wet mass at base DS (before conditioning)
    wet_in_t_d = ds_tpd / (base_ds / 100.0)

    scenarios = []

    # -----------------------------------------------------------------------
    # SCENARIO 1: Baseline (no change)
    # -----------------------------------------------------------------------
    s1 = _make_scenario(
        "PC00", "Baseline (no preconditioning)",
        "Current dewatering and AD configuration. Reference case.",
        base_ds, base_vs, base_gcv, base_vsr, 1.0,
        False, False, "centrifuge", None, 0.0,
        ds_tpd, wet_in_t_d, drying_target_ds_pct, assets_inputs,
    )
    scenarios.append(s1)

    # -----------------------------------------------------------------------
    # SCENARIO 2: Improved dewatering only (centrifuge + polymer optimisation)
    # -----------------------------------------------------------------------
    dew_ds = DEWATERING_DS_REFERENCE["centrifuge_polymer"]["mid"]
    s2 = _make_scenario(
        "PC01", "Improved dewatering (polymer optimisation)",
        "Optimised polymer dosing on existing centrifuge. Capital-light. Typical uplift to 26% DS.",
        dew_ds, base_vs, base_gcv, base_vsr, 1.0,
        False, False, "centrifuge_polymer", None, 0.0,
        ds_tpd, wet_in_t_d, drying_target_ds_pct, assets_inputs,
    )
    scenarios.append(s2)

    # -----------------------------------------------------------------------
    # SCENARIO 3: Filter press dewatering
    # -----------------------------------------------------------------------
    fp_ds = DEWATERING_DS_REFERENCE["filter_press"]["mid"]
    s3 = _make_scenario(
        "PC02", "Filter press dewatering",
        "High-DS dewatering. Achieves 30–35% DS. Capital investment required.",
        fp_ds, base_vs, base_gcv, base_vsr, 1.0,
        False, False, "filter_press", None, 0.0,
        ds_tpd, wet_in_t_d, drying_target_ds_pct, assets_inputs,
    )
    scenarios.append(s3)

    # -----------------------------------------------------------------------
    # SCENARIO 4: THP + improved dewatering
    # -----------------------------------------------------------------------
    thp_ds = DEWATERING_DS_REFERENCE["thp_centrifuge"]["mid"]
    thp_vs = max(40.0, base_vs - THP_IMPACTS["vsr_uplift_pct_points"] * 1.5)
    thp_gcv = base_gcv * (1 - THP_IMPACTS["gcv_reduction_pct"] / 100.0)
    thp_vsr = min(70.0, base_vsr + THP_IMPACTS["vsr_uplift_pct_points"])
    thp_biogas_factor = 1.0 + THP_IMPACTS["biogas_uplift_pct"] / 100.0
    thp_steam_mj_d = ds_tpd * 1000 * THP_IMPACTS["steam_demand_mj_per_tts"] / 1e6

    s4 = _make_scenario(
        "PC03", "THP + enhanced dewatering",
        "Thermal hydrolysis pre-treatment + centrifuge. Achieves 30–35% DS. "
        "Reduces GCV of cake (VS destroyed) but boosts biogas and dewatering.",
        thp_ds, thp_vs, thp_gcv, thp_vsr, thp_biogas_factor,
        True, True, "thp_centrifuge", None, 0.0,
        ds_tpd, wet_in_t_d, drying_target_ds_pct, assets_inputs,
        thp_steam_mj_d=thp_steam_mj_d,
    )
    scenarios.append(s4)

    # -----------------------------------------------------------------------
    # SCENARIO 5: Co-digestion with FOG
    # -----------------------------------------------------------------------
    fog = CO_DIGESTION_SUBSTRATES["fog"]
    fog_frac = 0.15   # 15% FOG by DS mass
    blended_gcv = base_gcv * (1 - fog_frac) + fog["gcv_mj_per_kg_ds"] * fog_frac
    blended_vs  = base_vs  * (1 - fog_frac) + fog["vs_pct"] * fog_frac
    fog_biogas_factor = 1.0 + fog["biogas_uplift_pct"] / 100.0 * fog_frac

    s5 = _make_scenario(
        "PC04", "Co-digestion with FOG (15% blend)",
        "Fat/oil/grease co-digestion at 15% fraction. Improves GCV and biogas yield. "
        "Does not improve dewatering DS%.",
        base_ds, blended_vs, blended_gcv, base_vsr, fog_biogas_factor,
        False, False, "centrifuge", "fog", fog_frac,
        ds_tpd, wet_in_t_d, drying_target_ds_pct, assets_inputs,
    )
    scenarios.append(s5)

    # -----------------------------------------------------------------------
    # SCENARIO 6: THP + filter press (maximum DS uplift)
    # -----------------------------------------------------------------------
    thp_fp_ds = DEWATERING_DS_REFERENCE["thp_centrifuge"]["max"]   # 38% DS
    s6 = _make_scenario(
        "PC05", "THP + filter press (maximum DS pathway)",
        "THP + high-DS filter press. Achieves 35–40% DS. "
        "Most capital-intensive preconditioning; enables all thermal routes.",
        thp_fp_ds, thp_vs, thp_gcv, thp_vsr, thp_biogas_factor,
        True, True, "filter_press", None, 0.0,
        ds_tpd, wet_in_t_d, drying_target_ds_pct, assets_inputs,
        thp_steam_mj_d=thp_steam_mj_d,
    )
    scenarios.append(s6)

    # -----------------------------------------------------------------------
    # AGGREGATE
    # -----------------------------------------------------------------------
    ds_values = [s.feed_ds_pct for s in scenarios]
    best_ds   = max(scenarios, key=lambda s: s.feed_ds_pct)
    best_net  = max(scenarios, key=lambda s: s.net_energy_improvement_kwh_d)
    any_28    = any(s.threshold_28pct_reached for s in scenarios)
    any_30    = any(s.threshold_30pct_reached for s in scenarios)

    narrative = _build_narrative(base_ds, scenarios, any_28, any_30, best_ds)

    return PreconditioningAssessment(
        base_ds_pct=base_ds,
        base_gcv=base_gcv,
        base_vs_pct=base_vs,
        ds_tpd=ds_tpd,
        scenarios=scenarios,
        best_for_ds_threshold=best_ds,
        best_for_energy=best_net,
        any_scenario_reaches_28pct=any_28,
        any_scenario_reaches_30pct=any_30,
        min_ds_achievable_pct=min(ds_values),
        max_ds_achievable_pct=max(ds_values),
        assessment_narrative=narrative,
    )


# ---------------------------------------------------------------------------
# SCENARIO BUILDER
# ---------------------------------------------------------------------------

def _make_scenario(sid, name, desc, ds_pct, vs_pct, gcv, vsr, biogas_factor,
                   ad_opt, thp, dew_tech, cosub, cosub_frac,
                   ds_tpd, wet_in_t_d, drying_target, assets,
                   thp_steam_mj_d: float = 0.0) -> PreconditioningScenario:
    """Build one preconditioning scenario with all derived values."""
    notes = []

    # Drying energy at this DS%
    # Water to remove from DS% to drying_target
    if ds_pct < drying_target:
        water_to_remove = ds_tpd / (ds_pct / 100.0) - ds_tpd / (drying_target / 100.0)
        spec_energy = 0.80   # kWh/kg indirect dryer
        dryer_eff   = 0.75
        drying_kwh_d = water_to_remove * 1000 * spec_energy / dryer_eff
    else:
        water_to_remove = 0.0
        drying_kwh_d = 0.0

    # Baseline drying energy (from base_ds — scenario_0 DS)
    # We compute it fresh from wet_in_t_d which was calculated at base DS
    base_ds_approx = ds_tpd / wet_in_t_d * 100.0
    if base_ds_approx < drying_target:
        base_water = wet_in_t_d - ds_tpd / (drying_target / 100.0)
        base_drying = base_water * 1000 * 0.80 / 0.75
    else:
        base_drying = 0.0

    drying_reduction = max(0.0, base_drying - drying_kwh_d)
    water_saved = max(0.0, wet_in_t_d - ds_tpd / (ds_pct / 100.0) - water_to_remove +
                      (wet_in_t_d - ds_tpd / (base_ds_approx / 100.0)))

    # Additional CHP from biogas uplift
    # Rough estimate: 20% more biogas → 20% more CHP → estimate ~50 kWh/d per tDS baseline
    chp_base_per_tds = 80.0    # Approximate CHP kWh/d/tDS for secondary sludge AD
    chp_additional = ds_tpd * chp_base_per_tds * (biogas_factor - 1.0)

    # THP steam energy cost (convert to kWh for comparison)
    thp_steam_kwh_d = thp_steam_mj_d / 3.6

    # Net energy improvement: drying reduction + additional CHP - THP steam cost
    net_improvement = drying_reduction + chp_additional - thp_steam_kwh_d

    # DS thresholds
    t28 = ds_pct >= 28.0
    t30 = ds_pct >= 30.0

    # Notes
    if thp:
        notes.append(
            f"THP reduces GCV by ~{THP_IMPACTS['gcv_reduction_pct']:.0f}% "
            f"({gcv:.1f} MJ/kgDS post-THP) but boosts biogas "
            f"{THP_IMPACTS['biogas_uplift_pct']:.0f}% and dewatering DS."
        )
        notes.append(
            f"THP steam demand: {thp_steam_mj_d:.0f} MJ/d "
            f"({thp_steam_kwh_d:.0f} kWh/d energy cost)."
        )
    if cosub:
        notes.append(
            f"Co-digestion with {cosub} at {cosub_frac*100:.0f}% fraction: "
            f"GCV {gcv:.1f} MJ/kgDS, VS {vs_pct:.0f}%."
        )
    if t28:
        notes.append(
            f"✓ 28% DS threshold reached ({ds_pct:.0f}%) — "
            "incineration energy closure improves significantly."
        )
    if t30:
        notes.append(
            f"✓ 30% DS threshold reached ({ds_pct:.0f}%) — "
            "incineration may achieve energy neutrality for drying."
        )

    return PreconditioningScenario(
        scenario_id=sid,
        scenario_name=name,
        description=desc,
        ad_optimised=ad_opt,
        thp_applied=thp,
        dewatering_technology=dew_tech,
        co_digestion_substrate=cosub,
        co_digestion_fraction=cosub_frac,
        feed_ds_pct=round(ds_pct, 1),
        feed_vs_pct=round(vs_pct, 1),
        feed_gcv_mj_per_kg_ds=round(gcv, 2),
        vsr_achieved_pct=round(vsr, 1),
        biogas_uplift_factor=round(biogas_factor, 3),
        chp_additional_kwh_d=round(chp_additional, 0),
        drying_energy_reduction_kwh_d=round(drying_reduction, 0),
        water_saved_t_d=round(water_to_remove - (0 if base_drying == 0 else
                              ds_tpd/(base_ds_approx/100) - ds_tpd/(ds_pct/100)), 1),
        threshold_28pct_reached=t28,
        threshold_30pct_reached=t30,
        thp_steam_demand_mj_d=round(thp_steam_mj_d, 0),
        net_energy_improvement_kwh_d=round(net_improvement, 0),
        conditioning_viable=True,
        conditioning_notes=notes,
    )


def _build_narrative(base_ds, scenarios, any_28, any_30, best_ds) -> str:
    parts = []
    parts.append(
        f"Base feed DS is {base_ds:.0f}%. "
        f"{'28% DS threshold is achievable' if any_28 else '28% DS threshold is NOT achievable'} "
        f"through preconditioning. "
        f"{'30% DS threshold is achievable' if any_30 else '30% DS threshold is NOT achievable'}."
    )
    if any_28:
        parts.append(
            f"Best DS scenario: {best_ds.scenario_name} achieves {best_ds.feed_ds_pct:.0f}% DS "
            f"with {best_ds.net_energy_improvement_kwh_d:+,.0f} kWh/d net energy improvement "
            f"vs baseline drying configuration."
        )
        parts.append(
            "Recommendation: evaluate upstream thickening and/or THP to close the "
            "incineration energy gap before committing to auxiliary fuel at the dryer."
        )
    else:
        parts.append(
            "No feasible preconditioning scenario reaches the 28% DS threshold from this base. "
            "Consider wet-pathway options (HTC) or co-incineration at higher-DS regional feed."
        )
    return " ".join(parts)
