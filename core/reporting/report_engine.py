"""
core/reporting/report_engine.py

Assembles structured report objects from project and scenario data.
The report object can be rendered in Streamlit or exported to PDF/Word/Excel.
All content is domain-agnostic at this layer — domain-specific narratives
are provided via the domain_specific_outputs dict in ScenarioModel.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
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
    generated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    report_version: str = "1.0"

    # Ordered sections
    executive_summary: str = ""
    sections: List[ReportSection] = field(default_factory=list)

    # Structured data tables (for export)
    cost_table: Optional[Dict] = None
    carbon_table: Optional[Dict] = None
    risk_table: Optional[Dict] = None
    comparison_table: Optional[List[Dict]] = None
    assumptions_appendix: Optional[List[Dict]] = None

    # Chart data (Plotly-compatible dicts)
    charts: Dict[str, Any] = field(default_factory=dict)

    # Metadata
    scenario_names: List[str] = field(default_factory=list)
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

        # ── Comparison table ──────────────────────────────────────────────
        if len(scenarios) > 1:
            report.comparison_table = self._build_comparison_table(scenarios)
            report.sections.append(ReportSection(
                title="Scenario Comparison",
                content_type="table",
                content=report.comparison_table,
            ))
            report.charts["comparison_radar"] = self._build_radar_chart_data(scenarios)

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
            f"**Date:** {datetime.utcnow().strftime('%B %Y')}",
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
                    f"- Net carbon: {preferred.carbon_result.net_tco2e_yr:.0f} tCO₂e/yr"
                )
            if preferred.risk_result:
                lines.append(
                    f"- Risk level: {preferred.risk_result.overall_level}"
                )

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

    def _build_carbon_table(self, scenarios: List[ScenarioModel]) -> Dict:
        rows = []
        for s in scenarios:
            if not s.carbon_result:
                continue
            c = s.carbon_result
            rows.append({
                "Scenario": s.scenario_name,
                "Scope 1 (tCO₂e/yr)": f"{c.scope_1_tco2e_yr:.1f}",
                "Scope 2 (tCO₂e/yr)": f"{c.scope_2_tco2e_yr:.1f}",
                "Scope 3 (tCO₂e/yr)": f"{c.scope_3_tco2e_yr:.1f}",
                "Avoided (tCO₂e/yr)": f"{c.avoided_tco2e_yr:.1f}",
                "Net (tCO₂e/yr)": f"{c.net_tco2e_yr:.1f}",
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
        criteria = [
            ("CAPEX ($M)", lambda s: f"{s.cost_result.capex_total/1e6:.2f}" if s.cost_result else "—"),
            ("OPEX (k$/yr)", lambda s: f"{s.cost_result.opex_annual/1e3:.0f}" if s.cost_result else "—"),
            ("Lifecycle Cost ($/yr)", lambda s: f"{s.cost_result.lifecycle_cost_annual:,.0f}" if s.cost_result else "—"),
            ("Net Carbon (tCO₂e/yr)", lambda s: f"{s.carbon_result.net_tco2e_yr:.0f}" if s.carbon_result else "—"),
            ("Overall Risk", lambda s: s.risk_result.overall_level if s.risk_result else "—"),
            ("Risk Score", lambda s: f"{s.risk_result.overall_score:.0f}" if s.risk_result else "—"),
        ]
        rows = []
        for criterion_name, getter in criteria:
            row = {"Criterion": criterion_name}
            for s in scenarios:
                row[s.scenario_name] = getter(s)
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
