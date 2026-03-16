"""
domains/wastewater/validation_rules.py

Wastewater-specific validation rules registered as hooks on the ValidationEngine.
"""

from __future__ import annotations
from typing import Any, List, Optional
from core.project.project_model import ValidationMessage, ValidationLevel
from core.validation.validation_engine import ValidationEngine, make_validation_message


def register_wastewater_validators(engine: ValidationEngine) -> None:
    engine.register_domain_hook(_check_cross_parameter_consistency)
    engine.register_domain_hook(_check_nutrient_balance)
    engine.register_domain_hook(_check_effluent_achievability)
    engine.register_domain_hook(_check_technology_consistency)


def _check_cross_parameter_consistency(inputs: Any, domain_result: Optional[Any] = None) -> List[ValidationMessage]:
    """
    Spec-required cross-checks:
      COD must be >= BOD
      TKN must be >= NH4-N
      Peak flow must be >= average flow
    """
    messages = []

    bod = getattr(inputs, "influent_bod_mg_l", None)
    cod = getattr(inputs, "influent_cod_mg_l", None)
    if bod is not None and cod is not None and cod < bod:
        messages.append(make_validation_message(
            "critical", "influent_cod_mg_l",
            f"COD ({cod} mg/L) must be ≥ BOD ({bod} mg/L). "
            "COD always exceeds BOD in raw wastewater.", cod,
        ))

    nh4 = getattr(inputs, "influent_nh4_mg_l", None)
    tkn = getattr(inputs, "influent_tkn_mg_l", None)
    if nh4 is not None and tkn is not None and tkn < nh4:
        messages.append(make_validation_message(
            "critical", "influent_tkn_mg_l",
            f"TKN ({tkn} mg/L) must be ≥ NH₄-N ({nh4} mg/L). "
            "TKN includes ammonium plus organic nitrogen.", tkn,
        ))

    avg = getattr(inputs, "design_flow_mld", None)
    peak = getattr(inputs, "peak_flow_mld", None)
    if avg is not None and peak is not None and peak > 0 and peak < avg:
        messages.append(make_validation_message(
            "critical", "peak_flow_mld",
            f"Peak wet weather flow ({peak} ML/d) must be ≥ average flow ({avg} ML/d).", peak,
        ))

    return messages


def _check_nutrient_balance(inputs: Any, domain_result: Optional[Any] = None) -> List[ValidationMessage]:
    messages = []
    tn_in  = getattr(inputs, "influent_tkn_mg_l", None)
    tn_eff = getattr(inputs, "effluent_tn_mg_l",  None)
    tp_in  = getattr(inputs, "influent_tp_mg_l",  None)
    tp_eff = getattr(inputs, "effluent_tp_mg_l",  None)

    if tn_in and tn_eff and tn_eff >= tn_in:
        messages.append(make_validation_message("critical", "effluent_tn_mg_l",
            f"Effluent TN target ({tn_eff} mg/L) must be less than influent TKN ({tn_in} mg/L).", tn_eff))
    if tn_eff and tn_eff < 3.0:
        messages.append(make_validation_message("warning", "effluent_tn_mg_l",
            f"Effluent TN of {tn_eff} mg/L is very stringent — consider MBR or tertiary treatment.", tn_eff))
    if tp_in and tp_eff and tp_eff >= tp_in:
        messages.append(make_validation_message("critical", "effluent_tp_mg_l",
            f"Effluent TP target ({tp_eff} mg/L) must be less than influent TP ({tp_in} mg/L).", tp_eff))
    if tp_eff and tp_eff < 0.1:
        messages.append(make_validation_message("warning", "effluent_tp_mg_l",
            f"Effluent TP target of {tp_eff} mg/L is extremely stringent — chemical P removal plus tertiary filtration required.", tp_eff))
    return messages


def _check_effluent_achievability(inputs: Any, domain_result: Optional[Any] = None) -> List[ValidationMessage]:
    messages = []
    bod_eff = getattr(inputs, "effluent_bod_mg_l", None)
    tss_eff = getattr(inputs, "effluent_tss_mg_l", None)
    if bod_eff and bod_eff < 3.0:
        messages.append(make_validation_message("warning", "effluent_bod_mg_l",
            f"BOD target of {bod_eff} mg/L requires MBR or tertiary filtration.", bod_eff))
    if tss_eff and tss_eff < 5.0:
        messages.append(make_validation_message("warning", "effluent_tss_mg_l",
            f"TSS target of {tss_eff} mg/L requires MBR or tertiary filtration.", tss_eff))
    return messages


def _check_technology_consistency(inputs: Any, domain_result: Optional[Any] = None) -> List[ValidationMessage]:
    messages = []
    if domain_result is None:
        return messages
    tech_results = getattr(domain_result, "technology_results", {})
    if "mbr" in tech_results and "bnr" in tech_results:
        messages.append(make_validation_message("info", "technology_selection",
            "Both BNR and MBR are selected. Review combined sludge production to avoid double-counting."))
    return messages
