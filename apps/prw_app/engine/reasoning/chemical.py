"""
PurePoint — chemical contaminant matrix builder
"""
from . import EffluentInputs
from ..constants import CHEMICAL_MATRIX, CHEMICAL_GROUPS


def build_chem_matrix(inputs: EffluentInputs, cls: str) -> dict:
    """
    Returns dict of group -> assessed row for the given class.
    Applies input-driven overrides where relevant.
    """
    matrix = {}
    for group in CHEMICAL_GROUPS:
        row = dict(CHEMICAL_MATRIX[group][cls])

        # PFAS override — elevate residual risk if input concentration is high
        if group == "PFAS":
            if inputs.pfas > 200 and cls != "PRW":
                row["residual_risk"] = "High — concentration exceeds typical GAC capacity"
            elif inputs.pfas > 100 and cls == "A":
                row["residual_risk"] = "High — GAC EBCT verification required"

        # Nitrosamine override
        if group == "Nitrosamines" and inputs.nitrosamine_risk == "high":
            if row["residual_risk"] in ("Medium", "Low-Medium"):
                row["residual_risk"] = "Medium — elevated precursor load; verify UV-AOP dose"

        # CEC override
        if group == "Endocrine-active compounds" and inputs.cec_risk == "high":
            if row["risk"] in ("Low", "Medium"):
                row["risk"] = "High"

        matrix[group] = row
    return matrix
