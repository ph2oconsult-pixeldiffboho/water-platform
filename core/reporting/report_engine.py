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
                is_rec = (s.scenario_name == decision.recommended_label)
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
                    row[cat.capitalize()] = "—"
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
