"""
Pathway assembler.
Orchestrates all engine modules in the correct sequence and
returns a fully-populated PathwayResult.

Sequence:
  1. Feedstock characterisation
  2. MAD (base HRT)
  3. THP delta (if applicable) → re-run MAD at reduced HRT
  4. Mass balance
  5. Energy balance (CHP)
  6. Heat balance (uses CHP thermal outputs)
  7. PFAS constraint
  8. Pathway classification + narrative

ph2o Consulting — BioPoint v1
"""

from engine.dataclasses import BioPointInputs, PathwayResult
from engine.feedstock import characterise_feedstock
from engine.mad import run_mad
from engine.thp import run_thp
from engine.mass_balance import run_mass_balance
from engine.energy_balance import run_energy_balance
from engine.heat_balance import run_heat_balance
from engine.pfas import evaluate_pfas
from engine.drying import run_drying
from engine.thermal import run_thermal_route
from engine.production import run_production, ProductionInputs
from engine.logistics import run_logistics, LogisticsInputs
from engine.decision_spine import build_decision_spine
from engine.sludge_character import characterise_sludge
from engine.trigger_engine import evaluate_triggers
from engine.adaptive_pathway import build_adaptive_pathway


def run_pathway(inputs: BioPointInputs) -> PathwayResult:
    """
    Master entry point. Returns fully-populated PathwayResult.
    """
    result = PathwayResult(inputs=inputs)
    warnings = []
    errors = []

    # --- 1. FEEDSTOCK CHARACTERISATION ---
    profile = characterise_feedstock(inputs)
    result.feedstock_profile = profile

    if profile.vs_load_kg_d <= 0:
        errors.append("VS load is zero — check sizing inputs.")
        result.errors = errors
        return result

    # --- 2. MAD BASE ---
    stab = inputs.stabilisation.stabilisation

    if stab == "NONE":
        mad = None
        thp = None
    else:
        # Run base MAD at user-specified HRT
        mad_base = run_mad(inputs, profile, thp_applied=False)

        if stab == "MAD_THP":
            # --- 3. THP DELTA ---
            thp = run_thp(inputs, profile, mad_base)

            # Re-run MAD at post-THP HRT to get kinetically-correct base,
            # then apply THP VSR uplift on top
            mad_at_thp_hrt = run_mad(
                inputs, profile,
                thp_applied=True,
                effective_hrt=thp.hrt_post_thp_days
            )

            # Apply THP VSR delta to the reduced-HRT MAD result
            # This captures: HRT reduction + THP biodegradability enhancement
            from engine.dataclasses import MADOutputs
            import copy
            mad = copy.deepcopy(mad_at_thp_hrt)

            # Override VSR and derived quantities with THP-enhanced values
            vsr_final = min(thp.vsr_with_thp_pct, 70.0)  # Physical ceiling ~70%
            vs_destroyed = profile.vs_load_kg_d * (vsr_final / 100.0)
            vs_effluent = profile.vs_load_kg_d - vs_destroyed
            biogas_total = vs_destroyed * profile.biogas_yield_m3_per_kgVSd
            methane_pct_final = profile.methane_content_pct + thp.delta_methane_content_pct
            methane_total = biogas_total * (methane_pct_final / 100.0)
            from data.feedstock_defaults import CHP_DEFAULTS
            biogas_energy = methane_total * CHP_DEFAULTS["methane_lhv_MJ_m3"]
            fsi = profile.ts_load_kg_d * (1.0 - profile.vs_ts_ratio)
            ts_digested = vs_effluent + fsi
            cake_ds = profile.cake_ds_pct_baseline + thp.delta_cake_ds_pct
            cake_mass = ts_digested / (cake_ds / 100.0) if cake_ds > 0 else 0.0

            mad.vsr_pct = round(vsr_final, 2)
            mad.vs_destroyed_kg_d = round(vs_destroyed, 1)
            mad.vs_effluent_kg_d = round(vs_effluent, 1)
            mad.biogas_total_m3_d = round(biogas_total, 1)
            mad.methane_content_pct = round(methane_pct_final, 2)
            mad.methane_total_m3_d = round(methane_total, 1)
            mad.biogas_energy_MJ_d = round(biogas_energy, 1)
            mad.ts_digested_kg_d = round(ts_digested, 1)
            mad.cake_ds_pct = round(cake_ds, 1)
            mad.cake_mass_kg_d = round(cake_mass, 1)
            mad.thp_applied = True

        else:
            mad = mad_base
            thp = None

    result.mad_outputs = mad
    result.thp_delta = thp

    # --- 4. MASS BALANCE ---
    if mad:
        mb = run_mass_balance(profile, mad)
        result.mass_balance = mb
        if mb.mass_balance_error_pct > 2.0:
            warnings.append(
                f"Mass balance closure error {mb.mass_balance_error_pct:.1f}% — review inputs."
            )

    # --- 5. ENERGY BALANCE (CHP) ---
    if mad:
        energy = run_energy_balance(inputs, profile, mad)
        result.energy_balance = energy
    else:
        energy = None

    # --- 6. HEAT BALANCE ---
    if mad and energy:
        thp_steam = thp.steam_demand_MJ_d if thp else 0.0
        heat = run_heat_balance(inputs, profile, mad, energy, thp_steam_MJ_d=thp_steam)
        result.heat_balance = heat
        if not heat.heat_self_sufficient:
            warnings.append(
                f"Heat shortfall: {abs(heat.heat_surplus_deficit_MJ_d):.0f} MJ/d — "
                f"auxiliary boiler required."
            )
    else:
        heat = None

    # --- 7. PFAS ---
    pfas = evaluate_pfas(inputs, profile)
    result.pfas_constraint = pfas
    if pfas.route_status == "CONSTRAINED":
        warnings.append(f"PFAS: route constrained — {pfas.constraint_narrative}")
    elif pfas.route_status == "CLOSED":
        warnings.append(f"PFAS: land application route CLOSED — {pfas.constraint_narrative}")

    # --- 8. DRYING ---
    ctx = inputs.context
    if mad and ctx.drying_route != "NONE":
        # CHP surplus heat available for thermal drying
        chp_surplus = heat.heat_surplus_deficit_MJ_d if heat and heat.heat_surplus_deficit_MJ_d > 0 else 0.0
        # Determine role: STAGING if thermal route follows, else ENDPOINT
        drying_role = "STAGING" if ctx.thermal_route != "NONE" else "ENDPOINT"
        drying = run_drying(
            drying_route=ctx.drying_route,
            cake_ds_in_pct=mad.cake_ds_pct,
            cake_ts_kg_d=mad.ts_digested_kg_d,
            climate_zone=ctx.climate_zone,
            role=drying_role,
            chp_surplus_heat_MJ_d=chp_surplus,
        )
        result.drying_result = drying
        if drying and not drying.suitable_for_thermal_route and ctx.thermal_route != "NONE":
            warnings.append(
                f"Drying output DS {drying.cake_ds_out_pct:.0f}% may be insufficient "
                f"for {ctx.thermal_route}. Review drying target."
            )
    else:
        drying = None

    # --- 9. THERMAL ROUTE ---
    if ctx.thermal_route != "NONE":
        # Input to thermal: drying output if drying present, else raw cake
        if drying:
            thermal_ds_in = drying.cake_ds_out_pct
            thermal_ts_in = drying.cake_ts_in_kg_d    # TS conserved through drying
        elif mad:
            thermal_ds_in = mad.cake_ds_pct
            thermal_ts_in = mad.ts_digested_kg_d
        else:
            thermal_ds_in = profile.cake_ds_pct_baseline
            thermal_ts_in = profile.ts_load_kg_d

        thermal = run_thermal_route(
            thermal_route=ctx.thermal_route,
            cake_ds_in_pct=thermal_ds_in,
            cake_ts_kg_d=thermal_ts_in,
            pfas_flagged=pfas.flagged,
        )
        result.thermal_result = thermal
        if thermal and not thermal.route_viable:
            warnings.append(f"Thermal route {ctx.thermal_route}: {thermal.viability_reason}")
        if thermal and not thermal.ds_adequate:
            warnings.append(
                f"{ctx.thermal_route}: DS shortfall of {thermal.ds_gap_pp:.1f}pp — "
                f"thermal pre-drying required before this route is viable."
            )
    else:
        thermal = None

    # --- 10. PATHWAY CLASSIFICATION ---
    result.stabilisation_class = _classify_stabilisation(mad, stab)
    result.recommended_route = _recommend_route(inputs, result)
    result.causal_narrative = _build_narrative(inputs, result)
    result.deferral_consequences = _deferral_logic(inputs, result)
    result.waterpoint_handoff = _build_handoff(inputs, result)

    # --- 11. PRODUCTION LAYER ---
    prod_inputs = ProductionInputs(
        production_mode=inputs.production_mode,
        current_ts_kg_d=profile.ts_load_kg_d,
        growth_rate_pct_yr=inputs.growth_rate_pct_yr,
        projection_years=inputs.projection_years,
        flow_ML_d=inputs.flow_ML_d,
        cod_influent_mg_L=inputs.cod_influent_mg_L,
    )
    production = run_production(prod_inputs, vs_ts_ratio=profile.vs_ts_ratio)
    result.production_result = production

    # --- 12. LOGISTICS LAYER ---
    if mad:
        log_cake_ds = mad.cake_ds_pct
        log_cake_ts = mad.ts_digested_kg_d
    else:
        log_cake_ds = profile.cake_ds_pct_baseline
        log_cake_ts = profile.ts_load_kg_d

    # If drying present, use drying output properties
    if drying:
        log_cake_ds = drying.cake_ds_out_pct
        log_cake_ts = drying.cake_ts_in_kg_d

    disposal_route = inputs.context.thermal_route if inputs.context.thermal_route != "NONE" \
        else "LAND_APPLICATION"

    log_inputs = LogisticsInputs(
        haul_distance_km=inputs.haul_distance_km,
        truck_payload_t=inputs.truck_payload_t,
        storage_days=inputs.storage_days,
        disposal_unit_cost_per_t_DS=inputs.disposal_unit_cost_per_t_DS,
    )
    logistics = run_logistics(
        cake_ds_pct=log_cake_ds,
        cake_ts_kg_d=log_cake_ts,
        disposal_route=disposal_route,
        logistics_inputs=log_inputs,
        growth_factor=production.growth_factor,
    )
    result.logistics_result = logistics

    # --- 13. DECISION SPINE ---
    spine = build_decision_spine(result, production, logistics)
    result.decision_spine = spine

    # --- 14. SLUDGE CHARACTER ---
    sludge_char = characterise_sludge(
        sludge_type=inputs.feedstock.feedstock_type,
        ds_pct=profile.ts_pct,
        ts_kg_d_direct=profile.ts_load_kg_d,
        population_EP=None,   # Not yet a UI input — future
    )
    result.sludge_character = sludge_char

    # --- 15. TRIGGER ENGINE ---
    trigger_assessment = evaluate_triggers(
        pathway_result=result,
        production_result=production,
        logistics_result=logistics,
        sludge_character=sludge_char,
        contract_renewal_years=getattr(inputs, 'contract_renewal_years', None),
        infrastructure_age_years=getattr(inputs, 'infrastructure_age_years', None),
        disposal_cost_escalation_pct_yr=getattr(inputs, 'disposal_cost_escalation_pct_yr', 5.0),
    )
    result.trigger_assessment = trigger_assessment

    # --- 16. ADAPTIVE PATHWAY ---
    cc = spine.constraint_classification if spine else None
    adaptive = build_adaptive_pathway(
        pathway_result=result,
        production_result=production,
        logistics_result=logistics,
        trigger_assessment=trigger_assessment,
        sludge_character=sludge_char,
        constraint_classification=cc,
    )
    result.adaptive_pathway = adaptive

    result.warnings = warnings
    result.errors = errors
    return result


# ---------------------------------------------------------------------------
# PATHWAY CLASSIFICATION
# ---------------------------------------------------------------------------

def _classify_stabilisation(mad, stab: str) -> str:
    if stab == "NONE" or mad is None:
        return "NONE"
    # Class A threshold: VSR > 38% + THP typically pushes above (US EPA 503 proxy)
    # Class B: stabilised, not Class A
    if mad.thp_applied or (mad.vsr_pct >= 38.0):
        return "CLASS_A" if mad.thp_applied else "CLASS_B"
    return "CLASS_B"


def _recommend_route(inputs: BioPointInputs, result: PathwayResult) -> str:
    pfas = result.pfas_constraint
    ctx = inputs.context

    if pfas and pfas.route_status == "CLOSED":
        return "THERMAL — PFAS precludes land application"
    if ctx.thermal_route != "NONE":
        return ctx.thermal_route
    if ctx.drying_route != "NONE":
        return f"{ctx.drying_route} DRYING → LAND APPLICATION"
    return "LAND APPLICATION (subject to stabilisation class)"


def _build_narrative(inputs: BioPointInputs, result: PathwayResult) -> str:
    mad = result.mad_outputs
    eb = result.energy_balance
    hb = result.heat_balance
    thp = result.thp_delta

    parts = []
    fs = inputs.feedstock

    parts.append(
        f"Feedstock: {fs.feedstock_type}"
        + (f" ({fs.blend_ratio_ps*100:.0f}% PS / {(1-fs.blend_ratio_ps)*100:.0f}% WAS)"
           if fs.feedstock_type == "PS_WAS" else "")
        + f". VS load: {result.feedstock_profile.vs_load_kg_d:.0f} kg VS/d."
    )

    if mad:
        parts.append(
            f"MAD at {mad.hrt_days:.0f}d HRT achieves {mad.vsr_pct:.1f}% VSR, "
            f"producing {mad.biogas_total_m3_d:.0f} m³/d biogas "
            f"({mad.methane_content_pct:.1f}% CH₄)."
        )
    if thp:
        parts.append(
            f"THP pre-treatment delivers +{thp.delta_vsr_pct:.1f}pp VSR uplift "
            f"and +{thp.delta_cake_ds_pct:.1f}pp cake DS improvement, "
            f"with HRT reduced from {thp.hrt_base_days:.0f}d to {thp.hrt_post_thp_days:.0f}d."
        )
    if eb:
        sign = "exports" if eb.energy_self_sufficient else "imports"
        parts.append(
            f"CHP ({eb.chp_capacity_kWe:.0f} kWe auto-sized): net {sign} "
            f"{abs(eb.net_electrical_export_kWh_d):.0f} kWh/d "
            f"({eb.electrical_self_sufficiency_pct:.0f}% self-sufficient)."
        )
    if hb:
        if hb.heat_self_sufficient:
            parts.append(
                f"Heat: self-sufficient with {hb.heat_surplus_deficit_MJ_d:.0f} MJ/d surplus."
            )
        else:
            parts.append(
                f"Heat: shortfall of {abs(hb.heat_surplus_deficit_MJ_d):.0f} MJ/d — "
                f"auxiliary boiler required."
            )

    return " ".join(parts)


def _deferral_logic(inputs: BioPointInputs, result: PathwayResult) -> str:
    stab = inputs.stabilisation.stabilisation
    if stab == "NONE":
        return (
            "Without stabilisation, raw sludge disposal costs and odour/regulatory risk "
            "increase substantially over time. Land application is precluded without Class B minimum. "
            "Deferring MAD investment increases lifecycle cost and delays energy recovery."
        )
    if result.thp_delta and not result.thp_delta.applied:
        return (
            "THP has been excluded. Cake DS and VSR remain at base MAD levels. "
            "If thermal drying is in scope, higher cake DS from THP would reduce dryer duty "
            "and operating cost. Deferring THP locks in higher downstream energy demand."
        )
    return "Pathway is complete. Review PFAS flag and climate zone if route constraints change."


def _build_handoff(inputs: BioPointInputs, result: PathwayResult) -> dict:
    """Structured handoff dict for WaterPoint bridge."""
    mad = result.mad_outputs
    eb = result.energy_balance
    return {
        "source": "BioPoint_v1",
        "feedstock_type": inputs.feedstock.feedstock_type,
        "vs_load_kg_d": result.feedstock_profile.vs_load_kg_d if result.feedstock_profile else 0,
        "stabilisation": inputs.stabilisation.stabilisation,
        "vsr_pct": mad.vsr_pct if mad else None,
        "biogas_m3_d": mad.biogas_total_m3_d if mad else None,
        "net_electrical_export_kWh_d": eb.net_electrical_export_kWh_d if eb else None,
        "stabilisation_class": result.stabilisation_class,
        "pfas_risk_tier": result.feedstock_profile.pfas_risk_tier if result.feedstock_profile else None,
        "recommended_route": result.recommended_route,
    }
