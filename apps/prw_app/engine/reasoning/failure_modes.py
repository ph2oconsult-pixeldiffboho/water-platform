"""
PurePoint — failure mode analysis
"""
from . import EffluentInputs
from ..constants import FAILURE_SCENARIOS, FAILURE_RESPONSES


def analyse_failure_modes(inputs: EffluentInputs, cls: str) -> dict:
    """
    Returns dict of scenario_key -> response dict for the given class.
    """
    results = {}
    for scenario in FAILURE_SCENARIOS:
        key = scenario["key"]
        response = dict(FAILURE_RESPONSES.get(key, {}).get(cls, {
            "lrv": "Not assessed",
            "chem": "Not assessed",
            "action": "Review",
        }))
        response["scenario"] = scenario["scenario"]
        results[key] = response
    return results
