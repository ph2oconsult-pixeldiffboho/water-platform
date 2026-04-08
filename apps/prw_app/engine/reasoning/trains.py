"""
PurePoint — treatment train selector
"""
from . import EffluentInputs
from ..constants import TREATMENT_TRAINS


def select_train(inputs: EffluentInputs, cls: str) -> dict:
    """
    Returns the treatment train for the given class.
    May annotate steps based on inputs (e.g. flag RO requirement).
    """
    train = dict(TREATMENT_TRAINS.get(cls, {}))
    steps = list(train.get("steps", []))
    annotations = []

    if cls == "PRW" and inputs.no3 > 11.3:
        annotations.append("RO sizing must address NO₃-N removal to <11.3 mg/L")
    if cls == "PRW" and inputs.cond > 1500:
        annotations.append("High TDS — RO recovery and concentrate management require design attention")
    if cls in ("A+", "PRW") and inputs.pfas > 100:
        annotations.append("PFAS concentration elevated — verify GAC EBCT or consider PFAS-selective polishing")
    if inputs.nitrosamine_risk == "high" and cls in ("A", "A+", "PRW"):
        annotations.append("High nitrosamine precursors — UV-AOP dose must target NDMA destruction (≥500 mJ/cm²)")
    if inputs.tss_p99 > 15 and cls in ("A", "A+", "PRW"):
        annotations.append("TSS P99 elevated — consider upstream coagulation ahead of MF/UF")

    train["annotations"] = annotations
    return train
