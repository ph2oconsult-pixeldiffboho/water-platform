"""
PurePoint — LRV barrier-credit calculator
Mirrors AquaPoint reasoning/lrv.py pattern.
"""

from typing import Dict, List
from . import EffluentInputs
from ..constants import LRV_REQUIRED, BARRIER_CREDITS, TREATMENT_TRAINS


def calculate_lrv(inputs: EffluentInputs, cls: str) -> dict:
    """
    Calculate cumulative LRV for a given class.
    Returns dict with: achieved, required, margin, barriers, passes, penalty_note
    """
    train = TREATMENT_TRAINS.get(cls, {})
    barrier_names = train.get("lrv_barriers", [])
    req = LRV_REQUIRED[cls]

    rows: List[dict] = []
    pro_total = bact_total = vir_total = 0.0

    for name in barrier_names:
        # resolve aliases (e.g. "Ozone" → "Ozone", "Ozone-AOP" → "Ozone")
        credit_key = _resolve_barrier(name)
        credits = BARRIER_CREDITS.get(credit_key, (0.0, 0.0, 0.0))
        pro, bact, vir = credits
        pro_total += pro
        bact_total += bact
        vir_total += vir
        rows.append({
            "barrier": name,
            "protozoa": pro,
            "bacteria": bact,
            "virus": vir,
        })

    # P99 turbidity / TSS penalty on filtration / membrane credit
    penalty_note = ""
    if inputs.turb_p99 > 5 or inputs.tss_p99 > 10:
        penalty = 0.5
        pro_total = max(0.0, pro_total - penalty)
        penalty_note = (
            f"⚠ P99 turbidity/TSS event penalty applied: −{penalty} log protozoa LRV. "
            "Membrane or filtration LRV credit reduced under high-load conditions."
        )

    achieved = {"protozoa": round(pro_total, 1), "bacteria": round(bact_total, 1), "virus": round(vir_total, 1)}
    margin = {k: round(achieved[k] - req[k], 1) for k in req}
    passes = all(achieved[k] >= req[k] for k in req)

    return {
        "achieved": achieved,
        "required": req,
        "margin": margin,
        "barriers": rows,
        "passes": passes,
        "penalty_note": penalty_note,
    }


def _resolve_barrier(name: str) -> str:
    """Map train step names to BARRIER_CREDITS keys."""
    aliases = {
        "Ozone or UV-AOP": "Ozone",
        "Ozone-AOP":       "Ozone",
        "BAC/GAC":         "BAC/GAC",
        "BAC polishing":   "BAC/GAC",
        "UV (40 mJ/cm²)":  "UV (40 mJ/cm²)",
        "UV-AOP":          "UV-AOP",
        "Cl₂ disinfection":"Cl₂ disinfection",
        "Cl₂ CT disinfection": "Cl₂ disinfection",
        "MF/UF membrane":  "MF/UF membrane",
        "RO":              "RO",
        "Coagulation + clarification": "Coagulation + clarification",
    }
    return aliases.get(name, name)
