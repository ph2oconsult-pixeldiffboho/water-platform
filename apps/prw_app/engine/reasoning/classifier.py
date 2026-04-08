"""
PurePoint — effluent classifier
Gate 1: classify effluent quality tier per parameter
Gate 2: identify governing constraints
"""

from typing import Tuple, List, Dict
from . import EffluentInputs


def classify_effluent(inputs: EffluentInputs) -> Tuple[List[str], Dict[str, str]]:
    """
    Returns:
        constraints: list of governing constraint strings
        quality_flags: dict of parameter -> "good" | "marginal" | "poor"
    """
    flags: Dict[str, str] = {}
    constraints: List[str] = []

    # Turbidity
    if inputs.turb_p99 <= 3:
        flags["turbidity"] = "good"
    elif inputs.turb_p99 <= 10:
        flags["turbidity"] = "marginal"
    else:
        flags["turbidity"] = "poor"
        constraints.append(f"Turbidity P99 {inputs.turb_p99} NTU — elevated MF/UF fouling risk")

    # TSS
    if inputs.tss_p99 <= 8:
        flags["tss"] = "good"
    elif inputs.tss_p99 <= 15:
        flags["tss"] = "marginal"
    else:
        flags["tss"] = "poor"
        constraints.append(f"TSS P99 {inputs.tss_p99} mg/L — membrane pre-treatment critical")

    # DOC
    if inputs.doc_med <= 8:
        flags["doc"] = "good"
    elif inputs.doc_med <= 12:
        flags["doc"] = "marginal"
    else:
        flags["doc"] = "poor"
        constraints.append(f"DOC median {inputs.doc_med} mg/L — high ozone/AOP demand")

    # UV254
    if inputs.uv254_p95 <= 0.15:
        flags["uv254"] = "good"
    elif inputs.uv254_p95 <= 0.25:
        flags["uv254"] = "marginal"
    else:
        flags["uv254"] = "poor"
        constraints.append(f"UV254 P95 {inputs.uv254_p95} cm⁻¹ — high NOM; ozone demand elevated")

    # PFAS
    if inputs.pfas <= 20:
        flags["pfas"] = "good"
    elif inputs.pfas <= 100:
        flags["pfas"] = "marginal"
    else:
        flags["pfas"] = "poor"
        constraints.append(f"PFAS {inputs.pfas} ng/L — advanced barrier required beyond Class A")

    # Nitrate
    if inputs.no3 <= 8:
        flags["no3"] = "good"
    elif inputs.no3 <= 11.3:
        flags["no3"] = "marginal"
    else:
        flags["no3"] = "poor"
        constraints.append(f"NO₃-N {inputs.no3} mg/L — exceeds DW guideline; RO required for PRW")

    # Conductivity
    if inputs.cond <= 800:
        flags["cond"] = "good"
    elif inputs.cond <= 1200:
        flags["cond"] = "marginal"
    else:
        flags["cond"] = "poor"
        constraints.append(f"Conductivity {inputs.cond} µS/cm — RO TDS management critical for PRW")

    # Ammonia
    if inputs.nh3 <= 10:
        flags["nh3"] = "good"
    elif inputs.nh3 <= 30:
        flags["nh3"] = "marginal"
    else:
        flags["nh3"] = "poor"
        constraints.append(f"NH₃-N {inputs.nh3} mg/L — nitrification or RO required for PRW")

    # CEC / PPCP risk
    if inputs.cec_risk == "high":
        constraints.append("High CEC risk — multi-endpoint bioassay monitoring required for A+ and PRW")

    # Nitrosamine risk
    if inputs.nitrosamine_risk == "high":
        constraints.append("High nitrosamine precursor load — UV-AOP or ozone-AOP essential")

    return constraints, flags
