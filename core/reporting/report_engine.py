"""
core/reporting/report_engine.py

Assembles structured report objects from project and scenario data.
The report object can be rendered in Streamlit or exported to PDF/Word/Excel.
All content is domain-agnostic at this layer — domain-specific narratives
are provided via the domain_specific_outputs dict in ScenarioModel.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.project.project_model import (
    ProjectModel, ScenarioModel, CostResult, CarbonResult, RiskResult,
)


# ─────────────────────────────────────────────────────────────────────────────
# REPORT OBJECT MODEL
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ReportSection:
    title: str = ""
    content_type: str = "text"  # text | table | chart | list
    content: Any = None
    notes: str = ""


@dataclass
class ReportObject:
    """
    Fully assembled report ready for rendering or export.
    All content is structured for consumption by any output format.
    """
    project_name: str = ""
    plant_name: str = ""
    domain: str = ""
    prepared_by: str = ""
    reviewed_by: str = ""
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    report_version: str = "1.0"

    # Ordered sections
    executive_summary: str = ""
    sections: List[ReportSection] = field(default_factory=list)

    # Structured data tables (for export)
    cost_table: Optional[Dict] = None
    opex_breakdown_table: Optional[Dict] = None
    specific_metrics_table: Optional[Dict] = None
    carbon_table: Optional[Dict] = None
    risk_table: Optional[Dict] = None
    comparison_table: Optional[List[Dict]] = None
    assumptions_appendix: Optional[List[Dict]] = None

    # Chart data (Plotly-compatible dicts)
    charts: Dict[str, Any] = field(default_factory=dict)

    # Decision framework output (populated when wastewater domain scenarios are present)
    decision: Optional[Any] = None  # ScenarioDecision from decision_engine
    decision_summary: Optional[Dict] = None  # Structured box: preferred, runner-up, driver, trade-off
    scoring_result:          Optional[Any] = None   # DecisionResult from scoring_engine
    platform_qa_result:      Optional[Any] = None   # PlatformQAResult
    intervention_results:    Optional[Any] = None   # List[InterventionResult]
    carbon_pathway_result:   Optional[Any] = None   # DecisionResult (Low-carbon profile)
    hydraulic_stress:        Optional[Any] = None   # Dict[name, HydraulicStressResult]
    complexity_results:      Optional[Any] = None   # Dict[name, OperationalComplexityResult]
    constructability_results:Optional[Any] = None   # Dict[name, ConstructabilityResult]
    advanced_carbon_results: Optional[Any] = None   # Dict[name, AdvancedCarbonResult]
    remediation_results:     Optional[Any] = None   # List[RemediationResult]
    feasible_preferred:      Optional[str] = None   # preferred after QA/hydraulic override
    requires_redesign:       bool = False
    qa_recommendation_text:  Optional[str] = None

    # Metadata
    scenario_names: List[str] = field(default_factory=list)
    # Design data per scenario: {scenario_name: {tech_code: perf_dict, design_params: {...}}}
    scenario_design_data: Dict[str, Any] = field(default_factory=dict)
    preferred_scenario: Optional[str] = None


# ─────────────────────────────────────────────────────────────────────────────
# REPORT ENGINE
# ─────────────────────────────────────────────────────────────────────────────

class ReportEngine:
    """
    Assembles a ReportObject from a project and a list of scenarios.

    The engine is domain-agnostic.  It reads from the standardised
    CostResult, CarbonResult, and RiskResult objects and from the
    domain_specific_outputs dict for supplementary content.
    """

    def build_report(
        self,
        project: ProjectModel,
        scenario_ids: Optional[List[str]] = None,
        include_assumptions: bool = True,
    ) -> ReportObject:
        """
        Build a complete ReportObject for the specified scenarios.

        Parameters
        ----------
        project : ProjectModel
        scenario_ids : list, optional
            Subset of scenario IDs to include; defaults to all
        include_assumptions : bool
            Whether to include the assumptions appendix
        """
        ids = scenario_ids or list(project.scenarios.keys())
        scenarios = [
            project.scenarios[sid] for sid in ids if sid in project.scenarios
        ]
        preferred = next((s for s in scenarios if s.is_preferred), None)

        report = ReportObject(
            project_name=project.metadata.project_name,
            plant_name=project.metadata.plant_name,
            domain=project.metadata.domain.value,
            prepared_by=project.metadata.author,
            reviewed_by=project.metadata.reviewer,
            scenario_names=[s.scenario_name for s in scenarios],
            preferred_scenario=preferred.scenario_name if preferred else None,
        )

        # ── Executive summary ─────────────────────────────────────────────
        report.executive_summary = self._build_executive_summary(project, scenarios, preferred)

        # ── Cost section ──────────────────────────────────────────────────
        if any(s.cost_result for s in scenarios):
            report.cost_table = self._build_cost_table(scenarios)
            report.sections.append(ReportSection(
                title="Cost Summary",
                content_type="table",
                content=report.cost_table,
            ))
            # OPEX breakdown table — shows what drives OPEX delta between scenarios
            report.opex_breakdown_table = self._build_opex_breakdown_table(scenarios)
            report.sections.append(ReportSection(
                title="OPEX Breakdown",
                content_type="table",
                content=report.opex_breakdown_table,
            ))
            # Specific metrics — m2/MLD, kgDS/ML, kgCO2e/kL, tDS/yr
            report.specific_metrics_table = self._build_specific_metrics_table(scenarios)
            report.sections.append(ReportSection(
                title="Specific Performance Metrics",
                content_type="table",
                content=report.specific_metrics_table,
            ))
            report.charts["capex_comparison"] = self._build_capex_chart_data(scenarios)
            report.charts["opex_breakdown"] = self._build_opex_chart_data(scenarios)

        # ── Carbon section ────────────────────────────────────────────────
        if any(s.carbon_result for s in scenarios):
            report.carbon_table = self._build_carbon_table(scenarios)
            report.sections.append(ReportSection(
                title="Carbon & Energy Summary",
                content_type="table",
                content=report.carbon_table,
            ))
            report.charts["carbon_comparison"] = self._build_carbon_chart_data(scenarios)

        # ── Risk section ──────────────────────────────────────────────────
        if any(s.risk_result for s in scenarios):
            report.risk_table = self._build_risk_table(scenarios)
            report.sections.append(ReportSection(
                title="Risk Summary",
                content_type="table",
                content=report.risk_table,
            ))

        # ── Scenario definitions section ──────────────────────────────────
        report.sections.append(ReportSection(
            title="Scenario Definitions",
            content_type="table",
            content=self._build_scenario_definition_table(scenarios),
        ))

        # ── Comparison table ──────────────────────────────────────────────
        if len(scenarios) > 1:
            report.comparison_table = self._build_comparison_table(scenarios)
            report.sections.append(ReportSection(
                title="Scenario Comparison",
                content_type="table",
                content=report.comparison_table,
            ))
            report.charts["comparison_radar"] = self._build_radar_chart_data(scenarios)

        # ── Decision framework ───────────────────────────────────────────
        # Run decision engine for wastewater scenarios with full results
        decision_scenarios = [
            s for s in scenarios
            if s.cost_result and s.risk_result and s.domain_specific_outputs
               and s.treatment_pathway
        ]
        if decision_scenarios:
            try:
                from domains.wastewater.decision_engine import evaluate_scenario
                from domains.wastewater.input_model import WastewaterInputs

                # Reconstruct inputs from first scenario's domain_inputs
                di = decision_scenarios[0].domain_inputs or {}
                known_fields = {f for f in WastewaterInputs.__dataclass_fields__}
                inp_kwargs = {k: v for k, v in di.items() if k in known_fields}
                try:
                    ref_inputs = WastewaterInputs(**inp_kwargs)
                except Exception:
                    ref_inputs = WastewaterInputs()

                report.decision = evaluate_scenario(decision_scenarios, ref_inputs)

                # ── Build decision_summary box ────────────────────────────
                d = report.decision
                if d and d.recommended_tech:
                    # Find runner-up (next cheapest scenario by scenario_name, not tech label)
                    runner_up = None
                    runner_up_note = ""
                    rec_tech = d.recommended_tech  # e.g. "granular_sludge"
                    # Use scenario_name of the recommended scenario
                    rec_scenario_name = next(
                        (s.scenario_name for s in decision_scenarios
                         if s.treatment_pathway and
                         s.treatment_pathway.technology_sequence and
                         s.treatment_pathway.technology_sequence[0] == rec_tech),
                        d.recommended_label
                    )
                    # Runner-up: prefer compliant/CWI options over non-compliant
                    # Build compliance classification for decision scenarios
                    _dec_compliance = {}
                    for _ds in decision_scenarios:
                        _ds_tp = (_ds.domain_specific_outputs or {}).get("technology_performance",{})
                        _ds_di = getattr(_ds, "domain_inputs", None) or {}
                        _tn_t  = _ds_di.get("effluent_tn_mg_l", 10.0)
                        _tp_t  = _ds_di.get("effluent_tp_mg_l",  1.0)
                        _hard_fail = any(
                            v > tgt * 1.10
                            for _tc_data in _ds_tp.values()
                            for (key, tgt) in [("effluent_tn_mg_l",_tn_t),("effluent_tp_mg_l",_tp_t)]
                            for v in [_tc_data.get(key, 0) or 0]
                            if _tc_data.get(key) is not None
                        )
                        _dec_compliance[_ds.scenario_name] = "non-compliant" if _hard_fail else "compliant"
                    
                    other_scens = [s for s in decision_scenarios
                                   if s.scenario_name != rec_scenario_name and s.cost_result]
                    # Prefer compliant runner-ups over non-compliant
                    compliant_others = [s for s in other_scens
                                        if _dec_compliance.get(s.scenario_name) != "non-compliant"]
                    if compliant_others:
                        runner_up_s = min(compliant_others,
                                          key=lambda s: s.cost_result.lifecycle_cost_annual)
                    elif other_scens:
                        runner_up_s = min(other_scens,
                                          key=lambda s: s.cost_result.lifecycle_cost_annual)
                    else:
                        runner_up_s = None
                    if runner_up_s:
                        runner_up = runner_up_s.scenario_name
                        # Runner-up note: when it's preferred
                        rr = runner_up_s.risk_result
                        runner_up_note = (
                            "preferred where lowest operational risk or process familiarity "
                            "is critical"
                            if rr and rr.overall_level == "Low"
                            else "preferred where higher compliance confidence is required"
                        )
                    else:
                        runner_up = None
                        runner_up_note = ""

                    # Key driver — first trade_off or why_recommended item
                    driver = (d.trade_offs[0] if d.trade_offs
                              else d.why_recommended[0] if d.why_recommended
                              else d.selection_basis)

                    # Key trade-off
                    trade_off = (d.trade_offs[1] if len(d.trade_offs) > 1
                                 else d.key_risks[0] if d.key_risks
                                 else "Higher implementation complexity than conventional BNR")

                    report.decision_summary = {
                        "preferred":   rec_scenario_name,
                        "runner_up":   runner_up,
                        "runner_up_note": runner_up_note,
                        "driver":      driver,
                        "trade_off":   trade_off,
                        "basis":       d.selection_basis,
                        "confidence":  getattr(getattr(d, "confidence", None), "level", "Moderate"),
                    }

                # Add decision sections to report
                d = report.decision
                if d and d.recommended_tech:
                    report.sections.append(ReportSection(
                        title="Decision Framework",
                        content_type="decision",
                        content={
                            "selection_basis": d.selection_basis,
                            "recommended_label": d.recommended_label,
                            "non_viable": d.non_viable,
                            "why_recommended": d.why_recommended,
                            "key_risks": d.key_risks,
                            "regulatory_note": getattr(d, "regulatory_note", ""),
                            "trade_offs": d.trade_offs,
                            "conclusion": d.conclusion,
                        },
                        notes=d.selection_basis,
                    ))

                    # Alternative pathways section
                    alt_paths = getattr(d, "alternative_pathways", [])
                    if alt_paths:
                        report.sections.append(ReportSection(
                            title="Alternative Pathways",
                            content_type="list",
                            content=[{
                                "tech_label": p.tech_label,
                                "intervention": p.intervention,
                                "capex_delta_m": p.capex_delta_m,
                                "opex_delta_k": p.opex_delta_k,
                                "lcc_total_k": p.lcc_total_k,
                                "achieves_compliance": p.achieves_compliance,
                                "residual_risks": p.residual_risks,
                                "procurement": p.procurement,
                                "regulatory": p.regulatory,
                                "summary": p.summary,
                            } for p in alt_paths],
                        ))

                    # Per-technology profiles (delivery, constructability, etc.)
                    if d.profiles:
                        profiles_content = {}
                        for name, profile in d.profiles.items():
                            profiles_content[name] = {
                                "delivery_recommended": profile.delivery.recommended_model,
                                "delivery_dnc":         profile.delivery.dnc.value,
                                "delivery_dbom":        profile.delivery.dbom.value,
                                "delivery_alliance":    profile.delivery.alliance.value,
                                "delivery_note":        profile.delivery.procurement_note,
                                "construct_overall":    profile.constructability.overall.value,
                                "construct_brownfield": profile.constructability.brownfield_note,
                                "construct_tiein":      profile.constructability.tie_in_risk,
                                "staging_can_stage":    profile.staging.can_stage,
                                "staging_stages":       profile.staging.stages,
                                "ops_overall":          profile.ops_complexity.overall.value,
                                "ops_skill":            profile.ops_complexity.operator_skill,
                                "failure_critical":     profile.failure_modes.critical_note,
                                "failure_modes":        [
                                    {"name": f.name, "likelihood": f.likelihood,
                                     "consequence": f.consequence, "mitigation": f.mitigation}
                                    for f in profile.failure_modes.modes
                                ],
                                "reg_overall":          profile.regulatory.overall.value,
                                "reg_note":             profile.regulatory.note,
                            }
                        report.sections.append(ReportSection(
                            title="Technology Profiles",
                            content_type="profiles",
                            content=profiles_content,
                        ))

                    # Confidence
                    conf = getattr(d, "confidence", None)
                    if conf:
                        report.sections.append(ReportSection(
                            title="Recommendation Confidence",
                            content_type="text",
                            content=(
                                f"**{conf.level}**\n\n"
                                "Drivers:\n" + "\n".join(f"- {dr}" for dr in conf.drivers) +
                                "\n\nCaveats:\n" + "\n".join(f"- {c}" for c in conf.caveats)
                            ),
                        ))

                    # Financial risk perspective
                    cf_fr = getattr(d, "client_framing", None)
                    alt_fr = getattr(d, "alternative_pathways", [])
                    if cf_fr and alt_fr:
                        a_fr = alt_fr[0]
                        report.sections.append(ReportSection(
                            title="Financial Risk Perspective",
                            content_type="list",
                            content=[
                                {
                                    "dimension": "CAPEX exposure",
                                    "option_a": next((b for b in cf_fr.option_a_bullets if "CAPEX" in b), "—"),
                                    "option_b": next((b for b in cf_fr.option_b_bullets if "CAPEX" in b), "—"),
                                },
                                {
                                    "dimension": "OPEX character",
                                    "option_a": "Moderate — electricity + vendor DBOM fee",
                                    "option_b": "Higher — heating energy + methanol (ongoing)",
                                },
                                {
                                    "dimension": "Energy dependency",
                                    "option_a": "Moderate — MABR gas-side pressure control",
                                    "option_b": "High — continuous heating critical at 15°C",
                                },
                                {
                                    "dimension": "Chemical dependency",
                                    "option_a": "None — biological process only",
                                    "option_b": "High — methanol supply, storage, dosing",
                                },
                                {
                                    "dimension": "LCC sensitivity",
                                    "option_a": "Electricity price, vendor contract fee",
                                    "option_b": "Gas/heating energy price, methanol price",
                                },
                                {
                                    "dimension": "Long-term financial risk",
                                    "option_a": f"Vendor dependency; technology evolution risk",
                                    "option_b": "Commodity price exposure; heating system replacement at 15–20yr",
                                },
                            ],
                            notes=(
                                f"Option A: {d.recommended_label}  |  "
                                f"Option B: {a_fr.tech_label} + thermal management. "
                                "Both carry ±25% LCC uncertainty at concept stage."
                            ),
                        ))

                    # Strategic insight (two-pathway framing)
                    si = getattr(d, "strategic_insight", "")
                    if si:
                        report.sections.append(ReportSection(
                            title="Strategic Insight",
                            content_type="text",
                            content=si,
                        ))

                    # Recommended approach (parallel evaluation steps)
                    ra = getattr(d, "recommended_approach", [])
                    if ra:
                        report.sections.append(ReportSection(
                            title="Recommended Approach",
                            content_type="list",
                            content=ra,
                        ))

                    # Update executive summary to use decision engine output
                    report.executive_summary = self._build_decision_executive_summary(
                        project, scenarios, d
                    )

            except Exception as _decision_err:
                # Decision engine failure must not break report generation
                import warnings
                warnings.warn(f"Decision engine failed: {_decision_err}")

        # ── Key warnings section ──────────────────────────────────────────
        report.sections.append(ReportSection(
            title="Warnings and Engineering Flags",
            content_type="table",
            content=self._build_warnings_table(scenarios),
        ))

        # ── Limitations and uncertainties ─────────────────────────────────
        report.sections.append(ReportSection(
            title="Limitations and Uncertainties",
            content_type="text",
            content=self._build_limitations_text(scenarios),
        ))

        # ── Assumptions appendix ──────────────────────────────────────────
        if include_assumptions and scenarios:
            # Use first scenario's assumptions; note any overrides
            base_assumptions = scenarios[0].assumptions
            if base_assumptions:
                report.assumptions_appendix = self._build_assumptions_appendix(
                    base_assumptions
                )
                report.sections.append(ReportSection(
                    title="Assumptions",
                    content_type="table",
                    content=report.assumptions_appendix,
                ))

        # ── Design data per scenario (for PFD and design tables) ──────────
        for s in scenarios:
            eng = s.domain_specific_outputs.get("engineering_summary", {})
            tp  = s.domain_specific_outputs.get("technology_performance", {})
            report.scenario_design_data[s.scenario_name] = {
                "tech_sequence": s.treatment_pathway.technology_sequence if s.treatment_pathway else [],
                "tech_performance": tp,
                "total_energy_kwh_day": eng.get("total_energy_kwh_day", 0),
                "specific_energy_kwh_kl": eng.get("specific_energy_kwh_kl", 0),
                "domain_inputs": s.domain_inputs or {},
            }

        # ── Run scoring engine for report integration ─────────────────────
        scored_scens = [s for s in scenarios if s.cost_result and s.risk_result]
        # Stamp compliance on any scenario that hasn't been stamped yet
        try:
            from domains.wastewater.domain_interface import stamp_compliance
            for _sc in scored_scens:
                if not getattr(_sc, "compliance_status", ""):
                    stamp_compliance(_sc)
        except Exception:
            pass
        # ── Run engineering layers before scoring so adjustments feed into scores ──
        try:
            from core.engineering.hydraulic_stress import run_all_hydraulic_stress
            from core.engineering.operational_complexity import score_all_complexity
            from core.engineering.constructability import score_all_constructability
            from core.engineering.advanced_carbon import run_all_advanced_carbon

            if len(scored_scens) >= 1:
                report.hydraulic_stress         = run_all_hydraulic_stress(scored_scens)
                report.complexity_results       = score_all_complexity(scored_scens)
                report.constructability_results = score_all_constructability(scored_scens)
                report.advanced_carbon_results  = run_all_advanced_carbon(scored_scens)

                # Write adjustments into DSO before scoring so _extract_raw picks them up
                for _sc in scored_scens:
                    _cx2 = report.complexity_results.get(_sc.scenario_name)
                    _co2 = report.constructability_results.get(_sc.scenario_name)
                    _dso2 = _sc.domain_specific_outputs or {}
                    _tp2  = _dso2.get("technology_performance") or {}
                    _tc2  = (_sc.treatment_pathway.technology_sequence[0]
                             if _sc.treatment_pathway and _sc.treatment_pathway.technology_sequence else "")
                    if _tc2 in _tp2:
                        if _cx2:
                            _tp2[_tc2]["complexity_score"]      = _cx2.complexity_score
                            _tp2[_tc2]["ops_risk_adjustment"]   = _cx2.ops_risk_adjustment
                            _tp2[_tc2]["complexity_narrative"]  = _cx2.narrative
                        if _co2:
                            _tp2[_tc2]["impl_risk_adjustment"]  = _co2.impl_risk_adjustment
                            _tp2[_tc2]["constructability_score"]= _co2.constructability_score
                            _tp2[_tc2]["constructability_narrative"] = _co2.narrative
                            _tp2[_tc2]["can_stage"]             = _co2.can_stage
                            _tp2[_tc2]["programme_months"]      = _co2.estimated_programme_months
        except Exception:
            pass   # engineering layers are non-critical

        if len(scored_scens) >= 2:
            try:
                # ── Remediation engine (before scoring) ───────────────────────────────
                try:
                    from core.engineering.remediation import remediate_scenarios
                    if report.hydraulic_stress:
                        report.remediation_results = remediate_scenarios(
                            scored_scens,
                            report.hydraulic_stress,
                            report.platform_qa_result,
                        )
                except Exception:
                    pass

                from core.decision.scoring_engine import ScoringEngine, WeightProfile

                # Read compliance_status stamped directly onto the ScenarioModel.
                # This is the single source of truth — set in domain_interface
                # populate_scenario_from_calc after every run_scenario call.
                def _classify_compliance_inline(scenario) -> str:
                    # 1. Use ScenarioModel.compliance_status if already stamped (preferred)
                    status = getattr(scenario, "compliance_status", "")
                    if status in ("Compliant", "Non-compliant", "Compliant with intervention"):
                        return status
                    # 2. Fall back to pre-computed compliance_flag in technology_performance
                    dso = getattr(scenario, "domain_specific_outputs", None) or {}
                    tp  = dso.get("technology_performance", {})
                    for tc_data in tp.values():
                        flag   = tc_data.get("compliance_flag", "")
                        issues = tc_data.get("compliance_issues", "") or ""
                        if flag == "Review Required" and issues:
                            return "Non-compliant"
                        if flag == "Review Required":
                            return "Compliant with intervention"
                    return "Compliant"

                compliance_map = {
                    s.scenario_name: _classify_compliance_inline(s) for s in scored_scens
                }
                engine = ScoringEngine()
                report.scoring_result = engine.score(
                    scored_scens,
                    weight_profile=WeightProfile.BALANCED,
                    compliance_map=compliance_map,
                )
                # Run platform QA
                try:
                    from core.decision.platform_qa import run_platform_qa
                    report.platform_qa_result = run_platform_qa(
                        scored_scens,
                        report.scoring_result,
                        report.decision,
                    )
                except Exception:
                    pass

                # Generate intervention scenarios for non-compliant options
                try:
                    from core.decision.intervention_scenarios import generate_interventions
                    ref_inp_for_int = {
                        "design_flow_mld":    scored_scens[0].domain_inputs.get("design_flow_mld", 10.0)
                                              if scored_scens and scored_scens[0].domain_inputs else 10.0,
                        "effluent_tn_mg_l":   scored_scens[0].domain_inputs.get("effluent_tn_mg_l", 10.0)
                                              if scored_scens and scored_scens[0].domain_inputs else 10.0,
                        "effluent_tp_mg_l":   scored_scens[0].domain_inputs.get("effluent_tp_mg_l", 1.0)
                                              if scored_scens and scored_scens[0].domain_inputs else 1.0,
                    }
                    # Get assumptions from first scenario's cost_result metadata
                    report.intervention_results = generate_interventions(
                        scored_scens, None, ref_inp_for_int
                    )
                except Exception:
                    pass

                # Generate carbon decision pathway (Low-carbon profile re-ranking)
                try:
                    carbon_cm = {
                        s.scenario_name: _classify_compliance_inline(s)
                        for s in scored_scens
                    }
                    report.carbon_pathway_result = engine.score(
                        scored_scens,
                        weight_profile=WeightProfile.LOW_CARBON,
                        compliance_map=carbon_cm,
                    )
                except Exception:
                    pass

                # Update decision_summary driver from scoring_result —
                # ensures ALL output formats (PDF, DOCX, page 3 box) use correct text
                sr_result = report.scoring_result
                ds_box    = report.decision_summary
                if sr_result and sr_result.preferred and sr_result.runner_up and ds_box:
                    pref = sr_result.preferred
                    ru   = sr_result.runner_up
                    lcc_p = pref.criterion_scores.get("lcc")
                    lcc_r = ru.criterion_scores.get("lcc")
                    op_p  = pref.criterion_scores.get("operational_risk")
                    op_r  = ru.criterion_scores.get("operational_risk")
                    risk_note = ""
                    if op_p and op_r:
                        risk_diff = int(op_r.raw_value - op_p.raw_value)
                        if abs(risk_diff) >= 3:
                            risk_note = (f", {abs(risk_diff)} points lower risk"
                                         if risk_diff > 0
                                         else f", {abs(risk_diff)} points higher risk")
                    if lcc_p and lcc_r:
                        diff = lcc_r.raw_value - lcc_p.raw_value
                        # Enrich risk note with "why" for higher-risk preferred options
                        risk_why = ""
                        if op_p and op_r and int(op_r.raw_value - op_p.raw_value) < -3:
                            # Preferred has HIGHER risk than runner-up — explain why it's still preferred
                            risk_why = " (driven by implementation complexity and operator familiarity)"
                        enriched_risk_note = risk_note + risk_why if risk_note else risk_why
                        if diff > 100:   # material — state with confidence
                            ds_box["driver"] = (
                                f"Clear economic advantage: {pref.scenario_name} reduces "
                                f"lifecycle cost by ${diff:.0f}k/yr vs {ru.scenario_name} "
                                f"(next-best compliant option){enriched_risk_note}"
                            )
                        elif diff > 0:
                            ds_box["driver"] = (
                                f"{pref.scenario_name} saves ${diff:.0f}k/yr lifecycle cost "
                                f"vs {ru.scenario_name}{enriched_risk_note}"
                            )
                        else:
                            ds_box["driver"] = (
                                f"{pref.scenario_name} costs ${abs(diff):.0f}k/yr more than "
                                f"{ru.scenario_name} but scores higher on risk and maturity{enriched_risk_note}"
                            )
                    ds_box["preferred"] = pref.scenario_name
                    ds_box["runner_up"] = ru.scenario_name

                # ── QA override: determine feasible_preferred ─────────────────
                # If the scoring-preferred option has a QA FAIL (hydraulic or other),
                # the feasible_preferred is the highest-scoring eligible option
                # that does NOT have a QA FAIL.
                try:
                    _hs_r = report.hydraulic_stress or {}
                    _qa_r = report.platform_qa_result
                    # Build set of scenario names with QA FAIL
                    _qa_fail_names = set()
                    if _qa_r:
                        for _e in (_qa_r.errors or []):
                            # QA error format: "QA-Exx: <ScenarioName> — ..."
                            for _sc in scored_scens:
                                if _sc.scenario_name in _e:
                                    _qa_fail_names.add(_sc.scenario_name)
                    # Also add hydraulic FAIL scenarios
                    for _hsn, _hsr in _hs_r.items():
                        if _hsr.overall_status == "FAIL":
                            _qa_fail_names.add(_hsn)

                    _pref_name = (report.scoring_result.preferred.scenario_name
                                 if report.scoring_result and report.scoring_result.preferred
                                 else None)

                    if _pref_name and _pref_name in _qa_fail_names:
                        # Preferred has QA FAIL — find next eligible without fail
                        _fallback = next(
                            (o for o in sorted(report.scoring_result.scored_options,
                                               key=lambda x: -x.total_score)
                             if o.is_eligible
                             and o.scenario_name not in _qa_fail_names
                             and o.scenario_name != _pref_name),
                            None
                        )
                        if _fallback:
                            report.feasible_preferred = _fallback.scenario_name
                        else:
                            report.feasible_preferred = None
                            report.requires_redesign  = True
                    else:
                        report.feasible_preferred = _pref_name
                except Exception:
                    report.feasible_preferred = None

                # Build QA-aware recommendation text
                try:
                    _fp2  = report.feasible_preferred
                    _sr2  = report.scoring_result
                    _raw2 = _sr2.preferred.scenario_name if (_sr2 and _sr2.preferred) else None
                    _ru2  = (_sr2.runner_up.scenario_name
                             if (_sr2 and _sr2.runner_up) else '-')
                    _rems2 = report.remediation_results or []
                    _qa2   = report.platform_qa_result
                    _blocked2 = (_fp2 and _fp2 != _raw2) or report.requires_redesign
                    if _blocked2 and _raw2:
                        _rem2 = next(
                            (r for r in _rems2 if r.scenario_name == _raw2), None
                        )
                        _errs2   = [e for e in (_qa2.errors if _qa2 else []) if _raw2 in e]
                        _detail2 = _errs2[0].split('-- ', 1)[-1].split('\u2014 ',1)[-1][:130] if _errs2 else ''
                        if not _detail2 and _errs2:
                            _detail2 = _errs2[0][_errs2[0].find(' -- ')+4:][:130] if ' -- ' in _errs2[0] else _errs2[0].split(': ',2)[-1][:130]
                        _fix2 = _rem2.fix_description[:80] if _rem2 else ''
                        _lcc2 = (
                            _rem2.modified_scenario.cost_result.lifecycle_cost_annual / 1e3
                            if (_rem2 and _rem2.modified_scenario
                                and _rem2.modified_scenario.cost_result) else 0
                        )
                        _parts2 = []
                        _parts2.append(
                            _raw2 + ' is the preferred option based on cost and carbon performance.'
                        )
                        if _detail2:
                            _parts2.append(
                                'However, QA-E07 identifies a hydraulic constraint at peak flow: '
                                + _detail2
                                + ' As currently configured, ' + _raw2
                                + ' is not feasible for procurement.'
                            )
                        _parts2.append('Required action before selection:')
                        if _fix2:
                            _parts2.append('\u2022 Modify ' + _raw2 + ': ' + _fix2)
                        _parts2.append(
                            '\u2022 Re-run ' + _raw2
                            + ' with updated hydraulic sizing before final selection.'
                        )
                        if _fp2 and not report.requires_redesign:
                            _parts2.append(
                                'Current feasible recommendation: ' + _fp2 + '. '
                                + _fp2 + ' passes all hydraulic checks as currently designed '
                                + 'and is recommended for detailed feasibility unless '
                                + _raw2 + ' is redesigned.'
                            )
                        report.qa_recommendation_text = ' '.join(_parts2)
                    else:
                        report.qa_recommendation_text = None
                except Exception:
                    report.qa_recommendation_text = None
                    # Override trade-off: compare preferred vs runner-up (both compliant)
                    ru_advantages = []
                    for crit, cs in ru.criterion_scores.items():
                        p_cs = pref.criterion_scores.get(crit)
                        if p_cs and cs.normalised > p_cs.normalised + 15:
                            ru_advantages.append(cs.label)
                    if ru_advantages:
                        ds_box["trade_off"] = (
                            f"Choosing {pref.scenario_name} over {ru.scenario_name} means "
                            f"accepting higher {', '.join(ru_advantages[:2]).lower()}. "
                            f"{ru.scenario_name} scores better on these criteria and "
                            "should be reconsidered if they are utility priorities."
                        )
                    else:
                        ds_box["trade_off"] = (
                            f"{pref.scenario_name} outperforms {ru.scenario_name} "
                            "on all major criteria under the selected weight profile."
                        )
            except Exception:
                pass  # scoring is non-critical — report generates without it

        return report

    # ── Section builders ──────────────────────────────────────────────────

    def _build_executive_summary(
        self,
        project: ProjectModel,
        scenarios: List[ScenarioModel],
        preferred: Optional[ScenarioModel],
    ) -> str:
        meta = project.metadata
        domain_name = meta.domain.display_name

        lines = [
            f"# {meta.project_name}",
            f"**{domain_name} — Concept Planning Study**",
            f"**Plant:** {meta.plant_name or 'Not specified'}  ",
            f"**Prepared by:** {meta.author or 'Not specified'}  ",
            f"**Date:** {datetime.now(timezone.utc).strftime('%B %Y')}",
            "",
            "## Study Overview",
            (
                f"This report presents the results of a concept-stage planning study for "
                f"{meta.plant_name or 'the facility'} in the {domain_name.lower()} domain. "
                f"A total of {len(scenarios)} scenario(s) have been evaluated."
            ),
        ]

        # Cost summary
        costed = [s for s in scenarios if s.cost_result]
        if costed:
            capex_range = (
                min(s.cost_result.capex_total for s in costed),
                max(s.cost_result.capex_total for s in costed),
            )
            lines.append("")
            lines.append("## Key Findings")
            if len(costed) == 1:
                lines.append(
                    f"- **CAPEX:** ${costed[0].cost_result.capex_total/1e6:.1f}M "
                    f"({costed[0].cost_result.cost_confidence})"
                )
            else:
                lines.append(
                    f"- **CAPEX range across scenarios:** "
                    f"${capex_range[0]/1e6:.1f}M – ${capex_range[1]/1e6:.1f}M"
                )

        if preferred:
            lines.append("")
            lines.append("## Recommended Option")
            lines.append(
                f"The **{preferred.scenario_name}** scenario is identified as the "
                f"preferred option based on the comparative assessment of lifecycle "
                f"cost, carbon footprint, and risk."
            )
            if preferred.cost_result:
                lines.append(
                    f"- CAPEX: ${preferred.cost_result.capex_total/1e6:.1f}M"
                )
                lines.append(
                    f"- OPEX: ${preferred.cost_result.opex_annual/1e3:.0f}k/yr"
                )
            if preferred.carbon_result:
                lines.append(
                    f"- Net carbon: {preferred.carbon_result.net_tco2e_yr:.0f} tCO2e/yr"
                )
            if preferred.risk_result:
                lines.append(
                    f"- Risk level: {preferred.risk_result.overall_level}"
                )

        return "\n".join(lines)

    def _build_decision_executive_summary(
        self,
        project: ProjectModel,
        scenarios: list,
        decision: Any,
    ) -> str:
        """
        Executive summary that leads with the decision engine output.
        Replaces the generic summary when decision data is available.
        """
        meta = project.metadata
        lines = [
            f"# {meta.project_name}",
            f"**Wastewater Treatment — Capital Planning Options Study**",
            f"**Plant:** {meta.plant_name or 'Not specified'}  ",
            f"**Prepared by:** {meta.author or 'Not specified'}  ",
            f"**Date:** {datetime.now(timezone.utc).strftime('%B %Y')}",
            "",
        ]

        # Selection basis
        lines += [
            "## Selection Basis",
            f"_{decision.selection_basis}_",
            "",
        ]

        # Recommendation — use qualified display label
        display_label = getattr(decision, "display_recommended_label",
                                decision.recommended_label)
        lines += [
            "## Recommended Option",
            f"**{display_label}**",
            "",
        ]
        for reason in decision.why_recommended:
            lines.append(f"- {reason}")
        lines.append("")

        # Non-viable
        if decision.non_viable:
            lines += [
                "## Base Case Non-Compliant Options (without intervention)",
            ]
            for nv in decision.non_viable:
                lines.append(f"- **{nv}** — non-compliant as base case; compliant with engineering intervention")
            lines.append("")

        # Key risks
        if decision.key_risks:
            lines += ["## Key Risks"]
            for risk in decision.key_risks:
                lines.append(f"- {risk}")
            lines.append("")

        # Alternative pathway summary
        alt_paths = getattr(decision, "alternative_pathways", [])
        if alt_paths:
            lines += ["## Alternative Pathway Available"]
            for p in alt_paths:
                icon = "✓" if p.achieves_compliance else "⚠"
                lines.append(
                    f"- **{p.tech_label}** + intervention: "
                    f"${p.lcc_total_k:.0f}k/yr LCC  |  "
                    f"{icon} {'Achieves' if p.achieves_compliance else 'Partial'} compliance  |  "
                    f"{p.procurement}"
                )
            lines.append("")

        # Regulatory note
        reg_note = getattr(decision, "regulatory_note", "")
        if reg_note:
            lines += [
                "## Regulatory Note",
                reg_note,
                "",
            ]

        # Cost summary
        costed = [s for s in scenarios if s.cost_result]
        if costed:
            lines += ["## Cost Summary"]
            for s in costed:
                cr = s.cost_result
                # Compare by tech code (recommended_tech) not display label
                _rec_tech = getattr(decision, "recommended_tech", None)
                _s_tech = (s.treatment_pathway.technology_sequence[0]
                           if s.treatment_pathway and s.treatment_pathway.technology_sequence
                           else "")
                is_rec = (_rec_tech and _s_tech == _rec_tech) or (s.scenario_name == decision.recommended_label)
                star = "★ " if is_rec else ""
                lines.append(
                    f"- **{star}{s.scenario_name}**: "
                    f"CAPEX ${cr.capex_total/1e6:.1f}M | "
                    f"LCC ${cr.lifecycle_cost_annual/1e3:.0f}k/yr | "
                    f"${cr.specific_cost_per_kl:.3f}/kL"
                )
            lines.append("")

        # Confidence
        conf = getattr(decision, "confidence", None)
        if conf:
            lines += [
                f"## Recommendation Confidence: {conf.level}",
            ]
            for c in conf.caveats[:2]:
                lines.append(f"- {c}")
            lines.append("")

        # Strategic insight
        si = getattr(decision, "strategic_insight", "")
        if si:
            lines += [
                "## Strategic Insight",
                si,
                "",
            ]

        # Recommended approach
        ra = getattr(decision, "recommended_approach", [])
        if ra:
            lines += ["## Recommended Approach"]
            for step in ra:
                lines.append(f"- {step}")
            lines.append("")

        # Conclusion
        lines += [
            "## Conclusion",
            decision.conclusion,
            "",
            "---",
            "_Concept-level study, AUD 2024. CAPEX ±40%. "
            "Not for procurement or regulatory submission._",
        ]

        return "\n".join(lines)

    def _build_cost_table(self, scenarios: List[ScenarioModel]) -> Dict:
        rows = []
        for s in scenarios:
            if not s.cost_result:
                continue
            cr = s.cost_result
            rows.append({
                "Scenario": s.scenario_name,
                "CAPEX ($M)": f"{cr.capex_total/1e6:.2f}",
                "OPEX ($/yr)": f"{cr.opex_annual:,.0f}",
                "Lifecycle Cost ($/yr)": f"{cr.lifecycle_cost_annual:,.0f}",
                "Specific Cost ($/kL)": (
                    f"{cr.specific_cost_per_kl:.2f}" if cr.specific_cost_per_kl else "—"
                ),
                "Confidence": cr.cost_confidence,
            })
        return {"headers": list(rows[0].keys()) if rows else [], "rows": rows}

    def _build_opex_breakdown_table(self, scenarios: List[ScenarioModel]) -> Dict:
        """Detailed OPEX breakdown table: energy / sludge / labour / maintenance / chemicals."""
        # Canonical categories — order matters for display
        CATEGORY_MAP = [
            ("energy",       ["Electricity", "electricity", "Energy", "energy"]),
            ("sludge",       ["Sludge", "sludge", "Biosolids", "biosolids"]),
            ("labour",       ["labour", "Labor", "Operator"]),
            ("maintenance",  ["maintenance", "Maintenance"]),
            ("chemicals",    ["chemical", "Chemical", "chloride", "caustic", "polymer",
                               "methanol", "alum", "ferric", "citric", "hypochlorite"]),
            ("other",        []),  # catch-all
        ]

        def _categorise(key: str) -> str:
            kl = key.lower()
            for cat, keywords in CATEGORY_MAP:
                if cat == "other":
                    return "other"
                if any(kw.lower() in kl for kw in keywords):
                    return cat
            return "other"

        rows = []
        for s in scenarios:
            if not s.cost_result:
                continue
            cr = s.cost_result
            totals: Dict[str, float] = {"energy": 0, "sludge": 0, "labour": 0,
                                         "maintenance": 0, "chemicals": 0, "other": 0}
            for k, v in cr.opex_breakdown.items():
                totals[_categorise(k)] += v
            opex = cr.opex_annual or 1  # avoid div/0
            row = {"Scenario": s.scenario_name}
            # Combine value + % into single cell to avoid column splitting
            for cat in ["energy", "sludge", "labour", "maintenance", "chemicals"]:
                val = totals[cat]
                pct = val / opex * 100
                if val > 0:
                    row[cat.capitalize()] = f"${val/1e3:.0f}k ({pct:.0f}%)"
                else:
                    row[cat.capitalize()] = "$0k (0%)"
            row["Total OPEX"] = f"${opex/1e3:.0f}k/yr"
            rows.append(row)
        hdrs = ["Scenario", "Energy", "Sludge", "Labour", "Maintenance", "Chemicals", "Total OPEX"]
        return {"headers": hdrs, "rows": rows}

    def _build_specific_metrics_table(self, scenarios: List[ScenarioModel]) -> Dict:
        """Specific metrics table: m2/MLD, kgDS/ML, kgCO2e/kL, tDS/yr."""
        rows = []
        for s in scenarios:
            if not s.cost_result:
                continue
            cr  = s.cost_result
            car = s.carbon_result
            eng = (s.domain_specific_outputs or {}).get("engineering_summary", {})
            tp  = (s.domain_specific_outputs or {}).get("technology_performance", {})
            flow_mld = eng.get("design_flow_mld") or 0
            flow_kl_yr = flow_mld * 1000 * 365 if flow_mld else None

            # Footprint: sum across technologies (lives in technology_performance, not engineering_summary)
            footprint = sum(v.get("footprint_m2", 0) or 0 for v in tp.values()) if tp else 0
            sludge_kgd = eng.get("total_sludge_kgds_day") or 0

            specific_footprint = round(footprint / flow_mld, 0) if flow_mld and footprint else None
            sludge_tds_yr      = round(sludge_kgd * 365 / 1000, 0) if sludge_kgd else None
            sludge_kgds_ml     = round(sludge_kgd / flow_mld, 0) if flow_mld and sludge_kgd else None
            carbon_intensity   = (
                round(car.net_tco2e_yr * 1000 / flow_kl_yr, 3)
                if car and flow_kl_yr else None
            )

            rows.append({
                "Scenario":             s.scenario_name,
                "Footprint (m2)":       f"{footprint:,.0f}" if footprint else "—",
                "Specific Footprint (m2/MLD)": f"{specific_footprint:.0f}" if specific_footprint else "—",
                "Sludge (kgDS/day)":    f"{sludge_kgd:,.0f}" if sludge_kgd else "—",
                "Sludge (tDS/yr)":      f"{sludge_tds_yr:,.0f}" if sludge_tds_yr else "—",
                "Specific Sludge (kgDS/ML)": f"{sludge_kgds_ml:.0f}" if sludge_kgds_ml else "—",
                "Carbon Intensity (kgCO2e/kL)": f"{carbon_intensity:.3f}" if carbon_intensity else "—",
            })
        hdrs = (["Scenario", "Footprint (m2)", "Specific Footprint (m2/MLD)",
                  "Sludge (kgDS/day)", "Sludge (tDS/yr)", "Specific Sludge (kgDS/ML)",
                  "Carbon Intensity (kgCO2e/kL)"])
        return {"headers": hdrs, "rows": rows}

    def _build_carbon_table(self, scenarios: List[ScenarioModel]) -> Dict:
        rows = []
        for s in scenarios:
            if not s.carbon_result:
                continue
            c = s.carbon_result
            rows.append({
                "Scenario": s.scenario_name,
                "Scope 1 (tCO2e/yr)": f"{c.scope_1_tco2e_yr:.1f}",
                "Scope 2 (tCO2e/yr)": f"{c.scope_2_tco2e_yr:.1f}",
                "Scope 3 (tCO2e/yr)": f"{c.scope_3_tco2e_yr:.1f}",
                "Avoided (tCO2e/yr)": f"{c.avoided_tco2e_yr:.1f}",
                "Net (tCO2e/yr)": f"{c.net_tco2e_yr:.1f}",
                "Carbon Cost ($/yr)": f"{c.carbon_cost_annual:,.0f}",
            })
        return {"headers": list(rows[0].keys()) if rows else [], "rows": rows}

    def _build_risk_table(self, scenarios: List[ScenarioModel]) -> Dict:
        rows = []
        for s in scenarios:
            if not s.risk_result:
                continue
            r = s.risk_result
            rows.append({
                "Scenario": s.scenario_name,
                "Overall Score": f"{r.overall_score:.0f}",
                "Overall Level": r.overall_level,
                "Technical": f"{r.technical_score:.0f}",
                "Implementation": f"{r.implementation_score:.0f}",
                "Operational": f"{r.operational_score:.0f}",
                "Regulatory": f"{r.regulatory_score:.0f}",
            })
        return {"headers": list(rows[0].keys()) if rows else [], "rows": rows}

    def _build_comparison_table(self, scenarios: List[ScenarioModel]) -> List[Dict]:
        """Multi-criteria comparison table (rows = criteria, cols = scenarios)."""

        def _eng(s, key, fmt="{:.0f}", fallback="—"):
            """Extract a value from engineering_summary or technology_performance."""
            eng = s.domain_specific_outputs.get("engineering_summary", {})
            if key in eng:
                v = eng[key]
                return fmt.format(v) if v is not None else fallback
            # Try summing across technology_performance dicts
            tp = s.domain_specific_outputs.get("technology_performance", {})
            for tc_data in tp.values():
                if key in tc_data:
                    v = tc_data[key]
                    return fmt.format(v) if v is not None else fallback
            return fallback

        criteria = [
            # ── Cost ───────────────────────────────────────────────────────
            ("CAPEX ($M)",
             lambda s: f"{s.cost_result.capex_total/1e6:.1f}" if s.cost_result else "—"),
            ("OPEX (k$/yr)",
             lambda s: f"{s.cost_result.opex_annual/1e3:.0f}" if s.cost_result else "—"),
            ("Lifecycle Cost (k$/yr)",
             lambda s: f"{s.cost_result.lifecycle_cost_annual/1e3:.0f}" if s.cost_result else "—"),
            ("Specific Cost ($/kL)",
             lambda s: f"{s.cost_result.specific_cost_per_kl:.2f}" if s.cost_result and s.cost_result.specific_cost_per_kl else "—"),

            # ── Energy ────────────────────────────────────────────────────
            ("Specific Energy (kWh/ML)",
             lambda s: f"{s.domain_specific_outputs.get('engineering_summary',{}).get('specific_energy_kwh_kl',0)*1000:.0f}"
                       if s.domain_specific_outputs else "—"),

            # ── Carbon ────────────────────────────────────────────────────
            ("Net Carbon (tCO2e/yr)",
             lambda s: f"{s.carbon_result.net_tco2e_yr:.0f}" if s.carbon_result else "—"),
            ("Scope 2 Electricity (tCO2e/yr)",
             lambda s: f"{s.carbon_result.scope_2_tco2e_yr:.0f}" if s.carbon_result else "—"),

            # ── Sludge ────────────────────────────────────────────────────
            ("Sludge Production (kgDS/day)",
             lambda s: _eng(s, "sludge_production_kgds_day", "{:.0f}")),

            # ── Physical sizing ───────────────────────────────────────────
            ("Reactor Volume (m³)",
             lambda s: _eng(s, "reactor_volume_m3", "{:.0f}")),
            ("Process Footprint (m2)",
             lambda s: _eng(s, "footprint_m2", "{:.0f}")),

            # ── Effluent quality ──────────────────────────────────────────
            ("Effluent TN (mg/L)",
             lambda s: _eng(s, "effluent_tn_mg_l", "{:.1f}")),
            ("Effluent TP (mg/L)",
             lambda s: _eng(s, "effluent_tp_mg_l", "{:.1f}")),

            # ── Risk ──────────────────────────────────────────────────────
            ("Risk Level",
             lambda s: s.risk_result.overall_level if s.risk_result else "—"),
            ("Risk Score (/100)",
             lambda s: f"{s.risk_result.overall_score:.0f}" if s.risk_result else "—"),
        ]
        rows = []
        for criterion_name, getter in criteria:
            row = {"Criterion": criterion_name}
            for s in scenarios:
                try:
                    row[s.scenario_name] = getter(s)
                except Exception:
                    row[s.scenario_name] = "—"
            rows.append(row)
        return rows

    def _build_assumptions_appendix(self, assumptions) -> List[Dict]:
        """Build a flat list of key assumptions for the appendix."""
        rows = []
        category_map = {
            "cost_assumptions": "Cost",
            "carbon_assumptions": "Carbon",
            "engineering_assumptions": "Engineering",
            "risk_assumptions": "Risk",
        }
        for attr, label in category_map.items():
            cat_dict = getattr(assumptions, attr, {})
            for key, value in cat_dict.items():
                if isinstance(value, dict):
                    for sub_key, sub_val in value.items():
                        override_key = f"{attr.replace('_assumptions', '')}.{key}.{sub_key}"
                        is_override = override_key in assumptions.user_overrides
                        rows.append({
                            "Category": label,
                            "Parameter": f"{key} → {sub_key}",
                            "Value": sub_val,
                            "User Override": "✓" if is_override else "",
                        })
                else:
                    category_short = attr.replace("_assumptions", "")
                    override_key = f"{category_short}.{key}"
                    is_override = override_key in assumptions.user_overrides
                    rows.append({
                        "Category": label,
                        "Parameter": key,
                        "Value": value,
                        "User Override": "✓" if is_override else "",
                    })
        return rows

    # ── Chart data builders (Plotly-compatible) ───────────────────────────

    def _build_capex_chart_data(self, scenarios: List[ScenarioModel]) -> Dict:
        names = []
        values = []
        for s in scenarios:
            if s.cost_result:
                names.append(s.scenario_name)
                values.append(round(s.cost_result.capex_total / 1e6, 2))
        return {"x": names, "y": values, "xlabel": "Scenario", "ylabel": "CAPEX ($M)"}

    def _build_opex_chart_data(self, scenarios: List[ScenarioModel]) -> Dict:
        """Stacked bar: OPEX breakdown categories."""
        categories = set()
        for s in scenarios:
            if s.cost_result:
                categories.update(s.cost_result.opex_breakdown.keys())
        chart_data = {"scenarios": [], "categories": list(categories), "data": {}}
        for cat in categories:
            chart_data["data"][cat] = []
        for s in scenarios:
            if s.cost_result:
                chart_data["scenarios"].append(s.scenario_name)
                for cat in categories:
                    chart_data["data"][cat].append(
                        round(s.cost_result.opex_breakdown.get(cat, 0) / 1e3, 1)
                    )
        return chart_data

    def _build_carbon_chart_data(self, scenarios: List[ScenarioModel]) -> Dict:
        data = {"scenarios": [], "scope_1": [], "scope_2": [], "scope_3": [], "avoided": [], "net": []}
        for s in scenarios:
            if s.carbon_result:
                data["scenarios"].append(s.scenario_name)
                data["scope_1"].append(s.carbon_result.scope_1_tco2e_yr)
                data["scope_2"].append(s.carbon_result.scope_2_tco2e_yr)
                data["scope_3"].append(s.carbon_result.scope_3_tco2e_yr)
                data["avoided"].append(-s.carbon_result.avoided_tco2e_yr)
                data["net"].append(s.carbon_result.net_tco2e_yr)
        return data

    def _build_radar_chart_data(self, scenarios: List[ScenarioModel]) -> Dict:
        """Radar chart data for multi-criteria comparison."""
        categories = ["Cost", "Carbon", "Risk", "Technical Risk", "Regulatory Risk"]
        chart_data = {"categories": categories, "scenarios": []}
        for s in scenarios:
            values = [0, 0, 0, 0, 0]
            if s.cost_result and s.cost_result.capex_total > 0:
                # Normalise — lower is better (invert)
                values[0] = min(100, s.cost_result.capex_total / 1e5)
            if s.carbon_result:
                values[1] = min(100, max(0, s.carbon_result.net_tco2e_yr / 100))
            if s.risk_result:
                values[2] = s.risk_result.overall_score
                values[3] = s.risk_result.technical_score
                values[4] = s.risk_result.regulatory_score
            chart_data["scenarios"].append({
                "name": s.scenario_name,
                "values": values,
            })
        return chart_data

    def _build_scenario_definition_table(self, scenarios: List[ScenarioModel]) -> List[Dict]:
        """Phase 7: Scenario definition table for report."""
        rows = []
        for s in scenarios:
            di = s.domain_inputs or {}
            rows.append({
                "Scenario":         s.scenario_name,
                "Flow (MLD)":       di.get("design_flow_mld", "—"),
                "Peak Factor":      di.get("peak_flow_factor", "—"),
                "BOD (mg/L)":       di.get("influent_bod_mg_l", "—"),
                "TKN (mg/L)":       di.get("influent_tkn_mg_l", "—"),
                "NH4 (mg/L)":       di.get("influent_nh4_mg_l", "—"),
                "TP (mg/L)":        di.get("influent_tp_mg_l", "—"),
                "Temp (°C)":        di.get("influent_temperature_celsius", "—"),
                "Eff. TN (mg/L)":   di.get("effluent_tn_mg_l", "—"),
                "Eff. TP (mg/L)":   di.get("effluent_tp_mg_l", "—"),
                "Technologies":     " + ".join(
                    s.treatment_pathway.technology_sequence
                    if s.treatment_pathway else []
                ).upper(),
            })
        return rows

    def _build_warnings_table(self, scenarios: List[ScenarioModel]) -> List[Dict]:
        """Phase 7: Collect engineering warnings from all scenarios."""
        rows = []
        for s in scenarios:
            tp = s.domain_specific_outputs.get("technology_performance", {}) if s.domain_specific_outputs else {}
            for tech_code, perf in tp.items():
                notes = perf.get("_notes", {})
                if isinstance(notes, dict):
                    for warning in notes.get("warnings", []):
                        rows.append({
                            "Scenario":   s.scenario_name,
                            "Technology": tech_code.upper(),
                            "Warning":    str(warning)[:200],
                        })
                # Compliance flag
                if perf.get("compliance_flag") == "warning":
                    for issue in (perf.get("compliance_issues") or []):
                        rows.append({
                            "Scenario":   s.scenario_name,
                            "Technology": tech_code.upper(),
                            "Warning":    f"Compliance: {issue}",
                        })
        if not rows:
            rows = [{"Scenario": "—", "Technology": "—",
                     "Warning": "No engineering warnings raised for any scenario."}]
        return rows

    def _build_limitations_text(self, scenarios: List[ScenarioModel]) -> str:
        """Phase 7: Standard limitations and uncertainties section."""
        # Check for any cold climate or carbon-limited scenarios
        warnings = []
        for s in scenarios:
            di = s.domain_inputs or {}
            T = di.get("influent_temperature_celsius", 20) or 20
            bod = di.get("influent_bod_mg_l", 250) or 250
            tkn = di.get("influent_tkn_mg_l", 45) or 45
            if T < 15:
                warnings.append(f"• {s.scenario_name}: design temperature {T}°C — "
                                 "nitrification performance should be verified with detailed design.")
            if bod * 2 / max(tkn, 1) < 7:
                warnings.append(f"• {s.scenario_name}: COD/TKN = {bod*2/tkn:.1f} — "
                                 "supplemental carbon may be required for TN compliance.")

        limitations = [
            "COST ESTIMATES",
            f"All capital cost estimates are concept-level (±40%) in AUD 2024. "
            "They cover the biological treatment train only and exclude: site preparation and "
            "earthworks, headworks, inlet works, sludge treatment, buildings, land, owner's costs, "
            "and connection to existing infrastructure. Detailed cost estimates require site "
            "investigation and preliminary design.",
            "",
            "ENGINEERING CALCULATIONS",
            "All engineering calculations use Metcalf & Eddy 5th Edition methodology. "
            "Calculations are at average design flow — peak flow performance is not simulated. "
            "Effluent quality predictions are based on design steady-state conditions; "
            "wet weather performance, startup periods, and upset conditions are not modelled.",
            "",
            "CARBON ESTIMATES",
            "Net carbon estimates use the IPCC 2019 Tier 1 N2O emission factor (0.016 kg N2O/kg N "
            "removed). The actual factor varies ×3–10 between sites. Site-specific monitoring is "
            "strongly recommended before using carbon estimates for formal reporting. "
            f"Grid emission factor: 0.79 kgCO2e/kWh (AUS NEM 2024).",
            "",
            "RISK SCORES",
            "Risk scores are screening-level assessments based on technology maturity and "
            "scenario operating conditions. They should be supplemented by a formal risk "
            "register and stakeholder engagement for detailed feasibility studies.",
            "",
            "SCENARIO-SPECIFIC NOTES",
        ] + (warnings if warnings else ["• No specific warnings for these scenarios."]) + [
            "",
            "This report was produced by the Water Utility Planning Platform. "
            "It is intended to support concept design and option evaluation only. "
            "It is not suitable for procurement, funding approval, or regulatory submission "
            "without further detailed design and independent review.",
        ]
        return "\n".join(limitations)
