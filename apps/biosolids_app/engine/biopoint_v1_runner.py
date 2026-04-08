"""
BioPoint V1 — Master Runner.
Orchestrates all calculation engines across all candidate flowsheets.
Returns fully evaluated, ranked flowsheets + board output.

ph2o Consulting — BioPoint V1
"""

from engine.input_schema import BioPointV1Inputs
from engine.flowsheet_generator import generate_flowsheets
from engine.calculation_engines import (
    run_mass_balance_v2, run_drying_calc, run_energy_balance_v2
)
from engine.analysis_engines import (
    run_compatibility, run_carbon_balance,
    run_product_pathway, run_economics, run_risk_engine
)
from engine.optimisation_engine import (
    score_flowsheet, build_output_card, build_board_output
)
from engine.thermal_comparison import run_thermal_comparison
from engine.energy_system import run_energy_system
from engine.preconditioning import run_preconditioning
from engine.inevitability import run_inevitability
from engine.mainstream_coupling import run_mainstream_coupling_system
from engine.coupling_classification import run_coupling_classification
from engine.hybrid_system import (
    run_hybrid_system, SiteInput, select_hub_sites
)
from engine.siting_engine import run_siting_engine
from engine.vendor_validation import run_vendor_validation
from engine.drying_dominance import run_drying_dominance_system
from engine.its_classification import run_its_classification
from engine.thermal_biochar import run_thermal_biochar_engine
from engine.pyrolysis_envelope import run_pyrolysis_envelope
from engine.pyrolysis_tradeoff import run_trade_off_curve
from engine.system_transition import run_system_transition_summary


def run_biopoint_v1(inputs: BioPointV1Inputs) -> dict:
    """
    Main entry point for BioPoint V1 calculation engine.

    Parameters
    ----------
    inputs : BioPointV1Inputs
        Fully populated input model. Call inputs.resolve() first.

    Returns
    -------
    dict with keys:
        flowsheets     : list[Flowsheet] — all 8 evaluated and ranked
        board_output   : BoardOutput — condensed board-level synthesis
        warnings       : list[str]
    """
    inputs.resolve()
    warnings = []

    # --- GENERATE CANDIDATE FLOWSHEETS ---
    flowsheets = generate_flowsheets(inputs)

    priority = inputs.strategic.optimisation_priority

    # --- RUN ALL ENGINES PER FLOWSHEET ---
    for fs in flowsheets:
        try:
            # Mass balance
            mb = run_mass_balance_v2(fs)
            fs.mass_balance = mb

            # Drying
            dc = run_drying_calc(fs, mb)
            fs.drying_calc = dc

            # Energy balance
            eb = run_energy_balance_v2(fs, mb, dc)
            fs.energy_balance = eb

            # Energy system integration layer
            esys = run_energy_system(fs, mb)
            fs.energy_system = esys

            # Compatibility
            compat = run_compatibility(fs)
            fs.compatibility = compat

            # Carbon balance
            carbon = run_carbon_balance(fs, mb)
            fs.carbon_balance = carbon

            # Product pathway
            product = run_product_pathway(fs, mb)
            fs.product_pathway = product

            # Economics
            econ = run_economics(fs, mb, dc, eb, carbon, product)
            fs.economics = econ

            # Risk
            risk = run_risk_engine(fs, mb, dc, eb, compat, carbon, product, econ)
            fs.risk = risk

            # Collect warnings
            if eb.energy_closure_risk:
                warnings.append(
                    f"{fs.name}: Energy closure risk — "
                    f"external energy {dc.net_external_drying_energy_kwh_per_day:,.0f} kWh/d required."
                )
            if mb.mass_balance_error_pct > 2.0:
                warnings.append(
                    f"{fs.name}: Mass balance closure error {mb.mass_balance_error_pct:.1f}%."
                )

        except Exception as ex:
            warnings.append(f"{fs.name}: Engine error — {type(ex).__name__}: {ex}")
            # Ensure all fields are at least initialised to avoid downstream crashes
            from engine.calculation_engines import MassBalanceV2, DryingCalc, EnergyBalanceV2
            from engine.analysis_engines import (
                CompatibilityResult, CarbonBalance, ProductPathwayResult,
                EconomicResult, RiskProfile
            )
            from engine.energy_system import EnergySystemResult
            if not fs.mass_balance:
                fs.mass_balance = MassBalanceV2(wet_sludge_in_tpd=inputs.feedstock.wet_sludge_tpd,
                                                ds_in_tpd=inputs.feedstock.dry_solids_tpd)
            if not fs.drying_calc:    fs.drying_calc    = DryingCalc()
            if not fs.energy_balance: fs.energy_balance = EnergyBalanceV2()
            if not fs.energy_system:  fs.energy_system  = EnergySystemResult()
            if not fs.compatibility:  fs.compatibility  = CompatibilityResult()
            if not fs.carbon_balance: fs.carbon_balance = CarbonBalance()
            if not fs.product_pathway: fs.product_pathway = ProductPathwayResult()
            if not fs.economics:      fs.economics      = EconomicResult()
            if not fs.risk:           fs.risk           = RiskProfile()

    # --- SCORE AND RANK ---
    for fs in flowsheets:
        try:
            score_result = score_flowsheet(fs, flowsheets, priority)
            fs.score = score_result["total"]
            fs.score_breakdown = score_result["breakdown"]
        except Exception as ex:
            fs.score = 0.0
            warnings.append(f"{fs.name}: Scoring error — {ex}")

    # Sort by score descending
    flowsheets.sort(key=lambda f: f.score, reverse=True)

    # Assign initial ranks and decision status
    for i, fs in enumerate(flowsheets):
        fs.rank = i + 1
        if i == 0:
            fs.decision_status = "Preferred"
        elif fs.score >= flowsheets[0].score * 0.85 and fs.risk.overall_risk != "High":
            fs.decision_status = "Viable but conditional"
        elif fs.risk.overall_risk == "High" or fs.compatibility.score == "Low":
            fs.decision_status = "Not recommended"
        else:
            fs.decision_status = "Viable but conditional"

    # --- MAINSTREAM COUPLING ---
    ds_tpd = inputs.feedstock.dry_solids_tpd
    mainstream_coupling = run_mainstream_coupling_system(flowsheets, ds_tpd)

    # --- COUPLING CLASSIFICATION ---
    resilience_priority = (inputs.strategic.optimisation_priority == "highest_resilience")
    # Plant capacity constrained: flag if disposal_cost high + regulatory pressure high
    # (proxy for a system under stress that can't absorb extra return loads)
    capacity_constrained = (
        inputs.assets.disposal_cost_per_tds > 300 and
        inputs.strategic.regulatory_pressure == "high"
    )
    coupling_classification = run_coupling_classification(
        flowsheets=flowsheets,
        ds_tpd=ds_tpd,
        plant_capacity_constrained=capacity_constrained,
        resilience_priority=resilience_priority,
    )

    # Apply coupling score adjustments to each flowsheet
    for fs in flowsheets:
        cc = fs.coupling_classification
        if cc and cc.net_coupling_score_adjustment != 0.0:
            old_score = fs.score
            fs.score = max(0.0, fs.score + cc.net_coupling_score_adjustment)
            if abs(cc.net_coupling_score_adjustment) >= 5.0:
                direction = "downgraded" if cc.net_coupling_score_adjustment < 0 else "upgraded"
                warnings.append(
                    f"{fs.name}: Score {direction} by {cc.net_coupling_score_adjustment:+.0f} "
                    f"({old_score:.1f} → {fs.score:.1f}) — "
                    f"coupling tier {cc.coupling_tier} ({cc.coupling_tier_label}), "
                    f"compliance risk: {cc.compliance_risk}."
                )
        # Also apply legacy raw-HTC downgrade if coupling is High
        mc = fs.mainstream_coupling
        if mc and mc.ranking_downgrade and fs.pathway_type == "HTC":
            fs.score = max(0.0, fs.score - 8.0)   # Additional for raw HTC (was -12, now -8 after tier adj)
            warnings.append(
                f"{fs.name}: Additional score penalty (−8) — Fully Coupled (Tier 3), "
                f"mainstream impact HIGH. Use FS11 (HTC + sidestream) to mitigate."
            )

    # Re-sort and re-rank after all coupling adjustments
    flowsheets.sort(key=lambda f: f.score, reverse=True)
    for i, fs in enumerate(flowsheets):
        fs.rank = i + 1
        cc  = fs.coupling_classification
        mc  = fs.mainstream_coupling
        coupling_clear = (cc is None or cc.coupling_tier <= 2 or
                          fs.pathway_type == "HTC_sidestream")
        if i == 0 and coupling_clear:
            fs.decision_status = "Preferred"
        elif i == 0 and not coupling_clear:
            fs.decision_status = "Viable but conditional"
        elif fs.score >= flowsheets[0].score * 0.85 and fs.risk.overall_risk != "High":
            fs.decision_status = "Viable but conditional"
        elif fs.risk.overall_risk == "High" or fs.compatibility.score == "Low":
            fs.decision_status = "Not recommended"
        else:
            fs.decision_status = "Viable but conditional"

    if mainstream_coupling.high_impact_flowsheets:
        warnings.append(
            f"⚠ HIGH mainstream coupling impact: "
            f"{', '.join(mainstream_coupling.high_impact_flowsheets)}. "
            "Confirm plant N capacity before selecting these pathways."
        )
    if coupling_classification.tier3_count > 0:
        tier3_names = [c.flowsheet_name for c in coupling_classification.classifications
                       if c.coupling_tier == 3]
        warnings.append(
            f"⚠ FULLY COUPLED (Tier 3) pathways require explicit mainstream plant assessment: "
            f"{', '.join(tier3_names)}. Cannot be recommended without capacity confirmation."
        )

    # --- SITING ENGINE ---
    multi_site = inputs.feedstock.dry_solids_tpd >= 50.0   # Heuristic: large scale = multi-site likely
    siting_assessment = run_siting_engine(
        flowsheets=flowsheets,
        land_constraint=inputs.strategic.land_constraint,
        social_licence_pressure=inputs.strategic.social_licence_pressure,
        multi_site_system=multi_site,
        regulatory_pressure=inputs.strategic.regulatory_pressure,
    )
    if siting_assessment.modifiers_applied:
        # Re-sort and re-rank after siting adjustments
        flowsheets.sort(key=lambda f: f.score, reverse=True)
        for i, fs in enumerate(flowsheets):
            fs.rank = i + 1

    # --- DRYING DOMINANCE & FEEDSTOCK REALITY ENGINE ---
    drying_dominance = run_drying_dominance_system(flowsheets, inputs.feedstock)

    # Apply score penalties from drying dominance (already applied inside run_drying_dominance_system)
    # Enforce fail gate: NON-VIABLE pathways cannot hold Preferred status
    # Re-sort after penalty application
    flowsheets.sort(key=lambda f: f.score, reverse=True)
    for i, fs in enumerate(flowsheets):
        fs.rank = i + 1
        ddr = fs.drying_dominance
        # Enforce the fail gate: NON-VIABLE + ranking Preferred → downgrade
        if ddr and not ddr.can_rank_as_preferred and i == 0:
            fs.decision_status = "Viable but conditional"
            warnings.append(
                f"⚠ DRYING GATE: {fs.name} ranked #1 but flagged "
                "ENERGY NON-VIABLE — cannot hold Preferred status. "
                "External energy must be confirmed before this pathway is selected."
            )
        elif ddr and not ddr.can_rank_as_preferred:
            if fs.decision_status == "Preferred":
                fs.decision_status = "Viable but conditional"

    if drying_dominance.primary_constraint_is_drying:
        warnings.append(
            f"⚠ DRYING DOMINANCE: At {inputs.feedstock.dewatered_ds_percent:.0f}% DS feed, "
            "drying is the primary system constraint. "
            f"{len(drying_dominance.gate_failed_pathways)} pathways fail the drying feasibility gate. "
            "Upstream DS improvement (preconditioning) is required to unlock thermal pathways."
        )

    for name in drying_dominance.gate_failed_pathways:
        warnings.append(
            f"⚠ DRYING GATE FAIL: {name} — ENERGY NON-VIABLE WITHOUT EXTERNAL INPUT. "
            "Cannot rank as Preferred. Confirm external energy source before selection."
        )

    # --- BUILD OUTPUT CARDS ---
    for fs in flowsheets:
        fs.output_card = build_output_card(fs)

    # --- THERMAL COMPARISON ---
    thermal_comparison = run_thermal_comparison(flowsheets)

    # Mandatory benchmark warning
    incin_fs = next((fs for fs in flowsheets if fs.pathway_type == "incineration"), None)
    if incin_fs and incin_fs.mandatory_benchmark:
        warnings.insert(0,
            f"⚑ MANDATORY BENCHMARK: At {inputs.feedstock.dry_solids_tpd:.0f} tDS/d, "
            "incineration (FS09) is a mandatory benchmark pathway. "
            "Do not proceed to detailed design without full incineration feasibility assessment."
        )

    # --- PRECONDITIONING ASSESSMENT ---
    preconditioning = run_preconditioning(inputs.feedstock, inputs.assets)

    # --- INEVITABILITY ASSESSMENT ---
    energy_systems_map = {
        fs.flowsheet_id: fs.energy_system
        for fs in flowsheets
        if fs.energy_system is not None
    }
    inevitability = run_inevitability(
        all_flowsheets=flowsheets,
        feedstock=inputs.feedstock,
        assets=inputs.assets,
        strategic=inputs.strategic,
        preconditioning=preconditioning,
        energy_systems=energy_systems_map,
    )

    # --- HYBRID SYSTEM ASSESSMENT ---
    # Auto-build a representative 5-site network from the system-level inputs.
    # Volume distribution follows a realistic utility-scale spread:
    # largest site ~35% of total, tapering to ~10%.
    # Users can override with explicit SiteInput lists via run_hybrid_system() directly.
    hybrid_system = None
    try:
        ds_tpd = inputs.feedstock.dry_solids_tpd
        ds_pct = inputs.feedstock.dewatered_ds_percent
        vs_pct = inputs.feedstock.volatile_solids_percent
        fracs  = [0.35, 0.25, 0.20, 0.12, 0.08]   # 5-site volume distribution
        has_ad_flags = [True, True, False, True, False]
        auto_sites = [
            SiteInput(
                site_id=f"S{i+1}",
                name=f"Site {i+1}",
                dry_solids_tpd=round(ds_tpd * fracs[i], 1),
                dewatered_ds_pct=ds_pct,
                has_ad=has_ad_flags[i],
                has_chp=has_ad_flags[i],
                distance_to_hub_km=0.0,
                is_hub_candidate=(i < 3),   # Top 3 sites are hub candidates
            )
            for i in range(5)
        ]

        # Choose hub treatment based on preferred flowsheet
        # (prefer HTC_sidestream if HTC ranked high, else AD)
        ranked_types = [fs.pathway_type for fs in flowsheets]
        if "HTC_sidestream" in ranked_types[:3]:
            hub_tech = "HTC_sidestream"
        elif "HTC" in ranked_types[:3]:
            hub_tech = "HTC_sidestream"  # Force sidestream for hub
        elif "AD" in ranked_types[:3]:
            hub_tech = "AD"
        else:
            hub_tech = "HTC_sidestream"  # Default

        hybrid_system = run_hybrid_system(
            sites=auto_sites,
            hub_treatment=hub_tech,
            inputs_assets=inputs.assets,
            inputs_strategic=inputs.strategic,
            vs_pct=vs_pct,
            dewatered_ds_pct=ds_pct,
            avg_inter_site_km=inputs.assets.average_transport_distance_km,
        )
    except Exception as ex:
        warnings.append(f"Hybrid system engine error: {type(ex).__name__}: {ex}")

    # --- ITS CLASSIFICATION ---
    its_assessment = run_its_classification(flowsheets)
    # Enforce: if PFAS is confirmed AND pathway is Level 1 or 2,
    # downgrade decision_status to "Not recommended"
    pfas_confirmed = inputs.feedstock.pfas_present == "confirmed"
    if pfas_confirmed:
        for fs in flowsheets:
            itsc = fs.its_classification
            if itsc and itsc.its_level <= 2:
                if fs.decision_status in ("Preferred", "Viable but conditional"):
                    fs.decision_status = "Not recommended"
                    warnings.append(
                        f"⚠ PFAS CONFIRMED: {fs.name} downgraded — "
                        f"{itsc.its_level_short} ({itsc.pfas_outcome}). "
                        "Cannot be selected where PFAS destruction is required."
                    )
            elif itsc and itsc.its_level >= 3:
                # L3/L4 pathways get a PFAS compliance bonus —
                # they are the only acceptable routes when PFAS is confirmed
                fs.score = min(100.0, fs.score + 25.0)

        # L1/L2 score penalty — applied after L3/L4 bonus so ordering is preserved
        for fs in flowsheets:
            itsc = fs.its_classification
            if itsc and itsc.its_level <= 2:
                fs.score = max(0.0, fs.score - 20.0)

        flowsheets.sort(key=lambda f: f.score, reverse=True)
        for i, fs in enumerate(flowsheets):
            fs.rank = i + 1
        warnings.append(
            f"⚠ PFAS CONFIRMED: Only Level 3 (ITS) and Level 4 (Incineration) pathways "
            "are acceptable. Thermal is mandatory. "
            f"Acceptable pathways: {', '.join(its_assessment.pfas_forced_pathways)}."
        )

    # --- THERMAL BIOCHAR ENGINE ---
    thermal_biochar_assessment = run_thermal_biochar_engine(
        flowsheets, inputs.feedstock, inputs.strategic
    )

    # --- PYROLYSIS OPERATING ENVELOPE ---
    pyr_fs = next((fs for fs in flowsheets if fs.pathway_type == "pyrolysis"), None)
    pyrolysis_envelope_result  = None
    pyrolysis_tradeoff_result  = None
    if pyr_fs:
        objective_map = {
            "highest_resilience": "compliance",
            "cost_minimisation":  "energy",
            "balanced":           "balanced",
            "carbon_optimised":   "carbon_credit",
        }
        obj = objective_map.get(inputs.strategic.optimisation_priority, "balanced")
        pyrolysis_envelope_result = run_pyrolysis_envelope(
            ds_tpd=inputs.feedstock.dry_solids_tpd,
            feedstock_type="biosolids",
            heating_rate="medium",
            feedstock_gcv_mj_per_kg_ds=inputs.feedstock.gross_calorific_value_mj_per_kg_ds,
            feedstock_vs_pct=inputs.feedstock.volatile_solids_percent,
            pfas_present=inputs.feedstock.pfas_present,
            has_secondary_oxidation=False,
            objective=obj,
        )
        pyr_fs.pyrolysis_envelope = pyrolysis_envelope_result

        pyrolysis_tradeoff_result = run_trade_off_curve(
            ds_tpd=inputs.feedstock.dry_solids_tpd,
            feedstock_type="biosolids",
            heating_rate="medium",
            feedstock_gcv_mj_per_kg_ds=inputs.feedstock.gross_calorific_value_mj_per_kg_ds,
            feedstock_vs_pct=inputs.feedstock.volatile_solids_percent,
            electricity_price_per_mwh=inputs.assets.local_power_price_per_kwh * 1000,
            biochar_market_type="soil_amendment",
            carbon_price_per_tco2e=inputs.strategic.carbon_credit_value_per_tco2e,
            pfas_present=inputs.feedstock.pfas_present,
        )
        pyr_fs.pyrolysis_tradeoff = pyrolysis_tradeoff_result

    # --- VENDOR VALIDATION ---
    vendor_validation = None
    try:
        vendor_validation = run_vendor_validation(flowsheets, inputs)
        # Surface key refutations as warnings
        for refutation in vendor_validation.key_refutations[:3]:
            warnings.append(f"⚠ CLAIM REFUTED: {refutation[:100]}")
    except Exception as ex:
        warnings.append(f"Vendor validation engine error: {type(ex).__name__}: {ex}")

    # --- SYSTEM TRANSITION SUMMARY (v25A30) ---
    system_transition = run_system_transition_summary(
        flowsheets=flowsheets,
        feedstock_inputs=inputs.feedstock,
        strategic_inputs=inputs.strategic,
        drying_dominance_system=drying_dominance,
        preconditioning=preconditioning,
        inevitability=inevitability,
        its_assessment=its_assessment,
    )

    # --- BOARD OUTPUT ---
    board = build_board_output(flowsheets)

    return {
        "flowsheets":             flowsheets,
        "board_output":           board,
        "thermal_comparison":     thermal_comparison,
        "preconditioning":        preconditioning,
        "inevitability":          inevitability,
        "mainstream_coupling":    mainstream_coupling,
        "coupling_classification":coupling_classification,
        "siting_assessment":      siting_assessment,
        "drying_dominance":       drying_dominance,
        "its_classification":     its_assessment,
        "system_transition":      system_transition,
        "thermal_biochar":        thermal_biochar_assessment,
        "pyrolysis_envelope":     pyrolysis_envelope_result,
        "pyrolysis_tradeoff":     pyrolysis_tradeoff_result,
        "hybrid_system":          hybrid_system,
        "vendor_validation":      vendor_validation,
        "warnings":               warnings,
    }
