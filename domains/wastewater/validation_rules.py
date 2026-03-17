"""
domains/wastewater/validation_rules.py

Wastewater-specific validation rules registered as hooks on the ValidationEngine.
"""

from __future__ import annotations
from typing import Any, List, Optional
from core.project.project_model import ValidationMessage, ValidationLevel
from core.validation.validation_engine import ValidationEngine, make_validation_message


def register_wastewater_validators(engine: ValidationEngine) -> None:
    engine.register_domain_hook(_check_influent_plausibility)
    engine.register_domain_hook(_check_cross_parameter_consistency)
    engine.register_domain_hook(_check_nutrient_balance)
    engine.register_domain_hook(_check_effluent_achievability)
    engine.register_domain_hook(_check_technology_consistency)


def _check_influent_plausibility(inputs: Any, domain_result: Optional[Any] = None) -> List[ValidationMessage]:
    """
    Plausibility checks for influent quality against realistic municipal ranges.
    Warns (does not block) when inputs are outside typical municipal wastewater bounds.
    Ref: Metcalf & Eddy 5th Ed Table 3-15; WEF Design of Municipal Wastewater Treatment Plants.
    """
    messages = []

    bod = getattr(inputs, "influent_bod_mg_l", None)
    tkn = getattr(inputs, "influent_tkn_mg_l", None)
    nh4 = getattr(inputs, "influent_nh4_mg_l", None)
    tp  = getattr(inputs, "influent_tp_mg_l", None)
    tss = getattr(inputs, "influent_tss_mg_l", None)
    flow = getattr(inputs, "design_flow_mld", None)
    peak = getattr(inputs, "peak_flow_factor", None)
    T    = getattr(inputs, "influent_temperature_celsius", None)

    if bod is not None:
        if bod < 50:
            messages.append(make_validation_message("warning", "influent_bod_mg_l",
                f"BOD {bod} mg/L is very low for municipal wastewater (typical: 100–400 mg/L). "
                "Verify — dilute catchment or industrial trade waste? Outputs may not be realistic.", bod))
        elif bod > 800:
            messages.append(make_validation_message("warning", "influent_bod_mg_l",
                f"BOD {bod} mg/L exceeds typical municipal range (max ~800 mg/L). "
                "This model is calibrated for municipal wastewater. Strong industrial inputs may require site-specific design.", bod))

    if tkn is not None:
        if tkn < 15:
            messages.append(make_validation_message("warning", "influent_tkn_mg_l",
                f"TKN {tkn} mg/L is very low (typical municipal: 25–70 mg/L). "
                "Check units — is this mg/L as N?", tkn))
        elif tkn > 120:
            messages.append(make_validation_message("warning", "influent_tkn_mg_l",
                f"TKN {tkn} mg/L exceeds typical municipal range. "
                "Sludge reject water, food processing, or anaerobic digestion effluent?", tkn))

    if nh4 is not None and tkn is not None:
        ratio = nh4 / max(tkn, 1)
        if ratio > 0.95:
            messages.append(make_validation_message("warning", "influent_nh4_mg_l",
                f"NH₄-N ({nh4} mg/L) ≈ TKN ({tkn} mg/L) — organic N fraction is near zero. "
                "Typical municipal NH₄/TKN = 0.60–0.80. Verify inputs.", nh4))

    if tp is not None and tp > 20:
        messages.append(make_validation_message("warning", "influent_tp_mg_l",
            f"TP {tp} mg/L is high for municipal wastewater (typical: 4–12 mg/L). "
            "Detergent-rich or food processing catchment?", tp))

    if bod is not None and tkn is not None and tkn > 0:
        bod_tkn = bod / tkn
        if bod_tkn < 2.5:
            messages.append(make_validation_message("warning", "influent_bod_mg_l",
                f"BOD/TKN = {bod_tkn:.1f} is very low (typical >4). "
                "Denitrification will be severely carbon-limited. "
                "Supplemental carbon (methanol) will likely be required to meet TN targets.", bod))

    if flow is not None and flow < 0.5:
        messages.append(make_validation_message("warning", "design_flow_mld",
            f"Design flow {flow} MLD is very small. This tool is calibrated for municipal plants ≥0.5 MLD. "
            "Package plant or dedicated industrial application?", flow))
    if flow is not None and flow > 500:
        messages.append(make_validation_message("warning", "design_flow_mld",
            f"Design flow {flow} MLD is very large. Outputs are extrapolated beyond calibration range.", flow))

    if peak is not None and peak > 5.0:
        messages.append(make_validation_message("warning", "peak_flow_factor",
            f"Peak flow factor {peak}× is extremely high (typical municipal: 1.5–3.5×). "
            "Combined sewer overflow mitigation or stormwater bypass recommended.", peak))

    if T is not None and T < 8.0:
        messages.append(make_validation_message("warning", "influent_temperature_celsius",
            f"Wastewater temperature {T}°C is below 8°C. "
            "Biological treatment (especially nitrification) is severely impaired. "
            "Consider heated reactors or alternative technology.", T))

    return messages


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
