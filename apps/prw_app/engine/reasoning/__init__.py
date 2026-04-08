"""
PurePoint — reasoning engine public interface
Exports: EffluentInputs, run_reasoning_engine, PurePointResult
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class EffluentInputs:
    """WaterPoint final effluent quality inputs."""

    effluent_type: str = "cas"
    project_name: str = ""
    plant_name: str = ""
    target_classes: List[str] = field(default_factory=lambda: ["C", "A", "A+", "PRW"])
    notes: str = ""

    turb_med: float = 2.0
    turb_p95: float = 6.0
    turb_p99: float = 12.0

    tss_med: float = 5.0
    tss_p95: float = 12.0
    tss_p99: float = 20.0

    doc_med: float = 10.0
    doc_p95: float = 16.0
    doc_p99: float = 22.0

    uv254_med: float = 0.15
    uv254_p95: float = 0.25
    uv254_p99: float = 0.35

    aoc: float = 300.0

    nh3: float = 25.0
    no3: float = 8.0

    ecoli_med: float = 5000.0
    ecoli_p95: float = 50000.0
    ecoli_p99: float = 200000.0

    pfas: float = 50.0
    cond: float = 900.0
    cec_risk: str = "medium"
    nitrosamine_risk: str = "medium"


@dataclass
class ClassResult:
    cls: str
    feasible: bool
    status: str
    lrv_achieved: Dict[str, float] = field(default_factory=dict)
    lrv_required: Dict[str, float] = field(default_factory=dict)
    lrv_margin: Dict[str, float] = field(default_factory=dict)
    lrv_barriers: List[dict] = field(default_factory=list)
    lrv_penalty_note: str = ""
    warnings: List[str] = field(default_factory=list)
    train: dict = field(default_factory=dict)
    chem_matrix: dict = field(default_factory=dict)
    failure_modes: dict = field(default_factory=dict)


@dataclass
class PurePointResult:
    inputs: EffluentInputs = field(default_factory=EffluentInputs)
    classes: Dict[str, ClassResult] = field(default_factory=dict)
    ccp_table: List[dict] = field(default_factory=list)
    wp_sensitivities: List[dict] = field(default_factory=list)
    upgrade_deltas: Dict[str, str] = field(default_factory=dict)
    governing_constraints: List[str] = field(default_factory=list)


def run_reasoning_engine(inputs: EffluentInputs) -> PurePointResult:
    from .classifier import classify_effluent
    from .lrv import calculate_lrv
    from .chemical import build_chem_matrix
    from .trains import select_train
    from .ccp import build_ccp_table
    from .failure_modes import analyse_failure_modes
    from .engine import build_wp_sensitivities, build_upgrade_deltas

    result = PurePointResult(inputs=inputs)
    constraints, quality_flags = classify_effluent(inputs)
    result.governing_constraints = constraints

    for cls in inputs.target_classes:
        lrv = calculate_lrv(inputs, cls)
        train = select_train(inputs, cls)
        chem = build_chem_matrix(inputs, cls)
        fm = analyse_failure_modes(inputs, cls)

        warnings = _build_warnings(inputs, cls, lrv, quality_flags)
        blocking = [w for w in warnings if "required" in w.lower() or "rejected" in w.lower()]
        if not lrv["passes"]:
            status = "Requires additional barriers"
            feasible = False
        elif blocking or warnings:
            status = "Feasible — conditions apply"
            feasible = True
        else:
            status = "Feasible"
            feasible = True

        result.classes[cls] = ClassResult(
            cls=cls, feasible=feasible, status=status,
            lrv_achieved=lrv["achieved"], lrv_required=lrv["required"],
            lrv_margin=lrv["margin"], lrv_barriers=lrv["barriers"],
            lrv_penalty_note=lrv.get("penalty_note", ""),
            warnings=warnings, train=train, chem_matrix=chem, failure_modes=fm,
        )

    result.ccp_table = build_ccp_table(inputs)
    result.wp_sensitivities = build_wp_sensitivities(inputs)
    result.upgrade_deltas = build_upgrade_deltas()
    return result


def _build_warnings(inputs, cls, lrv, quality_flags):
    warnings = []
    if inputs.turb_p99 > 10 and cls == "C":
        warnings.append("P99 turbidity elevated — verify clarification at event conditions")
    if inputs.doc_p95 > 15:
        warnings.append("DOC P95 >15 mg/L — increased ozone / AOP demand; size accordingly")
    if inputs.pfas > 100 and cls != "PRW":
        warnings.append("PFAS >100 ng/L — GAC EBCT must be verified for long-chain removal")
    if inputs.pfas > 200 and cls != "PRW":
        warnings.append("PFAS >200 ng/L — PFAS-selective resin or RO may be required")
    if inputs.nh3 > 30 and cls == "PRW":
        warnings.append("NH₃-N >30 mg/L — nitrification or RO required for PRW")
    if inputs.no3 > 11.3 and cls == "PRW":
        warnings.append("NO₃-N exceeds drinking water guideline — RO required for PRW")
    if inputs.cond > 1500 and cls == "PRW":
        warnings.append("Conductivity >1500 µS/cm — RO TDS and concentrate management required")
    if inputs.cec_risk == "high" and cls in ("A", "A+", "PRW"):
        warnings.append("High CEC risk — enhanced multi-endpoint bioassay monitoring required")
    if inputs.nitrosamine_risk == "high":
        warnings.append("High nitrosamine precursors — UV-AOP or ozone-AOP essential")
    if inputs.tss_p99 > 15 and cls in ("A", "A+", "PRW"):
        warnings.append("TSS P99 >15 mg/L — MF/UF TMP spike risk; increased CIP frequency")
    if inputs.aoc > 400 and cls in ("A+", "PRW"):
        warnings.append("AOC >400 µg/L — biological instability risk; BAC sizing critical")
    return warnings
