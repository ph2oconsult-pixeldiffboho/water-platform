"""
domains/wastewater/risk_items.py

Wastewater-domain risk item definitions.
These are passed to the shared RiskEngine for scoring.
Domain modules extend the base risk framework by providing these items.
"""

from __future__ import annotations
from typing import Any, Dict, List

from core.project.project_model import RiskItem


def get_wastewater_risk_items(
    inputs: Any,
    tech_results: Dict[str, Any],
) -> List[RiskItem]:
    """
    Build the wastewater-specific risk item list for a scenario.
    Risk scores (likelihood, consequence) are set based on
    the selected technologies and design parameters.

    Parameters
    ----------
    inputs : WastewaterInputs
    tech_results : dict of {tech_code: TechnologyResult}

    Returns
    -------
    List[RiskItem]
    """
    items = []
    has_mbr = "mbr" in tech_results
    has_bnr = "bnr" in tech_results
    flow = inputs.design_flow_mld or 1.0

    # ── Technical risks ───────────────────────────────────────────────────

    items.append(RiskItem(
        risk_id="ww_tech_01",
        category="technical",
        name="Biological process instability",
        description=(
            "Risk of biological process upset due to toxic influent, "
            "temperature shock, or nutrient imbalance."
        ),
        likelihood=2,
        consequence=4,
        mitigation=(
            "Online monitoring of key parameters (DO, pH, NH4-N). "
            "Equalization basin upstream to buffer shock loads."
        ),
    ))

    items.append(RiskItem(
        risk_id="ww_tech_02",
        category="technical",
        name="Sludge bulking / settling issues",
        description="Filamentous bulking can impair secondary clarifier performance.",
        likelihood=2 if has_mbr else 3,  # MBR eliminates this risk
        consequence=2 if has_mbr else 4,
        mitigation="MBR selected (eliminates clarifier settling dependency)" if has_mbr
                   else "Selector zones, chlorination of RAS, DO control.",
    ))

    if has_mbr:
        items.append(RiskItem(
            risk_id="ww_tech_03",
            category="technical",
            name="MBR membrane fouling",
            description=(
                "Irreversible membrane fouling reduces flux and increases TMP, "
                "requiring more frequent CIP and early membrane replacement."
            ),
            likelihood=3,
            consequence=3,
            mitigation=(
                "Robust pre-screening, optimised SAD, regular CIP protocol, "
                "online TMP monitoring."
            ),
        ))
        items.append(RiskItem(
            risk_id="ww_tech_04",
            category="technical",
            name="MBR membrane integrity failure",
            description="Membrane breach allowing passage of pathogens to effluent.",
            likelihood=1,
            consequence=5,
            mitigation="Continuous pressure decay testing, turbidity monitoring of permeate.",
        ))

    if flow > 50:
        items.append(RiskItem(
            risk_id="ww_tech_05",
            category="technical",
            name="Large plant complexity",
            description="Multiple treatment trains increase coordination and control complexity.",
            likelihood=2,
            consequence=3,
            mitigation="Comprehensive SCADA, clear SOPs, adequate operator training.",
        ))

    # ── Implementation risks ──────────────────────────────────────────────

    items.append(RiskItem(
        risk_id="ww_impl_01",
        category="implementation",
        name="Odour management during construction",
        description="Excavation and sewer diversions during construction may cause odour complaints.",
        likelihood=3 if inputs.odour_sensitive else 2,
        consequence=3 if inputs.odour_sensitive else 2,
        mitigation="Construction noise and odour management plan, community liaison.",
    ))

    items.append(RiskItem(
        risk_id="ww_impl_02",
        category="implementation",
        name="Construction programme overrun",
        description="Commissioning delays for complex biological systems.",
        likelihood=2,
        consequence=3,
        mitigation="Allow adequate commissioning period in programme, phased commissioning plan.",
    ))

    items.append(RiskItem(
        risk_id="ww_impl_03",
        category="implementation",
        name="Site constraints / available land",
        description="Limited footprint availability may constrain technology selection.",
        likelihood=1 if not inputs.available_land_m2 else 2,
        consequence=3,
        mitigation="Compact technologies (MBR) to be considered if land is constrained.",
    ))

    # ── Operational risks ─────────────────────────────────────────────────

    items.append(RiskItem(
        risk_id="ww_ops_01",
        category="operational",
        name="Operator skill requirements",
        description=(
            "MBR and advanced BNR require higher operator skill levels "
            "than conventional activated sludge."
        ),
        likelihood=2 if has_mbr else 1,
        consequence=3,
        mitigation="Operator training programme, O&M manual, supplier support contract.",
    ))

    items.append(RiskItem(
        risk_id="ww_ops_02",
        category="operational",
        name="Chemical supply reliability",
        description="Dependence on consistent chemical supply for P removal or carbon dosing.",
        likelihood=2,
        consequence=3,
        mitigation="Dual supplier contracts, minimum 30-day onsite storage.",
    ))

    items.append(RiskItem(
        risk_id="ww_ops_03",
        category="operational",
        name="Energy cost exposure",
        description="Aeration is energy-intensive; electricity price rises increase OPEX.",
        likelihood=3,
        consequence=2,
        mitigation="Energy efficiency optimisation, renewable energy procurement strategy.",
    ))

    # ── Regulatory risks ──────────────────────────────────────────────────

    items.append(RiskItem(
        risk_id="ww_reg_01",
        category="regulatory",
        name="Effluent licence compliance",
        description=(
            "Risk of exceeding consent conditions for TN, TP, BOD, or TSS, "
            "particularly during process start-up or wet weather events."
        ),
        likelihood=2,
        consequence=4,
        mitigation=(
            "Conservative design to licence limits, wet weather bypass strategy, "
            "process contingency (e.g. effluent storage)."
        ),
    ))

    items.append(RiskItem(
        risk_id="ww_reg_02",
        category="regulatory",
        name="Biosolids classification and disposal pathway approval",
        description=(
            "If sludge treatment does not achieve required pathogen reduction, "
            "biosolids may not qualify for land application."
        ),
        likelihood=2,
        consequence=3,
        mitigation="Confirm biosolids classification early; design sludge treatment accordingly.",
    ))

    items.append(RiskItem(
        risk_id="ww_reg_03",
        category="regulatory",
        name="Future licence tightening",
        description="Regulatory tightening (especially nutrient limits) may require plant upgrade.",
        likelihood=2,
        consequence=3,
        mitigation="Design for future upgrade pathway; use modular process configurations.",
    ))

    return items
