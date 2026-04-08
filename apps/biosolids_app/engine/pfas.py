"""
PFAS constraint engine.
Maps PFAS flag + feedstock risk tier → route constraint status.

ph2o Consulting — BioPoint v1
"""

from engine.dataclasses import BioPointInputs, FeedstockProfile, PFASConstraint


def evaluate_pfas(inputs: BioPointInputs, profile: FeedstockProfile) -> PFASConstraint:
    """
    Evaluate PFAS constraint.
    Returns PFASConstraint with route_status: OPEN / CONSTRAINED / CLOSED.
    """
    pfas_flagged = inputs.context.pfas_flag
    risk_tier = profile.pfas_risk_tier

    if not pfas_flagged:
        return PFASConstraint(
            flagged=False,
            risk_tier=risk_tier,
            route_status="OPEN",
            constraint_narrative="No PFAS flag set. All routes remain open pending site data.",
            affected_routes=[],
        )

    if risk_tier == "LOW":
        status = "CONSTRAINED"
        narrative = (
            "PFAS flagged at LOW risk tier. Land application may proceed with monitoring. "
            "Composting and thermal routes are preferred."
        )
        affected = ["LAND_APPLICATION"]

    elif risk_tier == "MEDIUM":
        status = "CONSTRAINED"
        narrative = (
            "PFAS flagged at MEDIUM risk (WAS fraction present). "
            "Land application constrained — regulatory approval required. "
            "Thermal routes (incineration, gasification) preferred."
        )
        affected = ["LAND_APPLICATION", "COMPOSTING"]

    else:  # HIGH
        status = "CLOSED"
        narrative = (
            "PFAS flagged at HIGH risk (WAS-dominant). "
            "Land application route CLOSED. "
            "Thermal destruction (incineration) is the recommended route. "
            "Pyrolysis and gasification under assessment — confirm destruction efficiency."
        )
        affected = ["LAND_APPLICATION", "COMPOSTING", "SOLAR_DRYING"]

    return PFASConstraint(
        flagged=True,
        risk_tier=risk_tier,
        route_status=status,
        constraint_narrative=narrative,
        affected_routes=affected,
    )
