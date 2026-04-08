"""
PurePoint — CCP / surrogate framework builder
Filters the full CCP table to barriers present in selected trains.
"""
from . import EffluentInputs
from ..constants import CCP_FRAMEWORK, TREATMENT_TRAINS


def build_ccp_table(inputs: EffluentInputs) -> list:
    """
    Returns CCP rows relevant to the union of barriers across all target classes.
    """
    active_barriers = set()
    for cls in inputs.target_classes:
        train = TREATMENT_TRAINS.get(cls, {})
        for step in train.get("lrv_barriers", []):
            active_barriers.add(_normalise(step))
        for step in train.get("steps", []):
            active_barriers.add(_normalise(step))

    result = []
    for row in CCP_FRAMEWORK:
        if _normalise(row["barrier"]) in active_barriers:
            result.append(row)

    # Always include Cl₂ disinfection
    if not any(r["barrier"] == "Cl₂ disinfection" for r in result):
        for row in CCP_FRAMEWORK:
            if row["barrier"] == "Cl₂ disinfection":
                result.append(row)

    return result


def _normalise(name: str) -> str:
    return name.lower().replace("mf/uf membrane", "mf/uf").replace("mf/uf", "mf/uf").strip()
