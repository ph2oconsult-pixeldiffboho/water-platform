"""
PurePoint — master engine helpers
WaterPoint interface sensitivities and upgrade pathway deltas.
"""
from . import EffluentInputs


def build_wp_sensitivities(inputs: EffluentInputs) -> list:
    """
    Assesses how WaterPoint effluent quality parameters affect PurePoint
    treatment intensity and operational risk.
    """
    issues = []

    if inputs.doc_p95 > 12:
        issues.append({
            "parameter": f"DOC P95 = {inputs.doc_p95} mg/L",
            "impact": "Ozone demand elevated; AOP/GAC burden increased; RO fouling tendency",
            "severity": "High",
        })
    elif inputs.doc_p95 > 8:
        issues.append({
            "parameter": f"DOC P95 = {inputs.doc_p95} mg/L",
            "impact": "Moderate ozone demand; BAC/GAC sized accordingly",
            "severity": "Medium",
        })

    if inputs.tss_p99 > 15:
        issues.append({
            "parameter": f"TSS P99 = {inputs.tss_p99} mg/L",
            "impact": "MF/UF TMP spike risk; RO SDI elevated; upstream coagulation recommended",
            "severity": "High",
        })
    elif inputs.tss_p99 > 8:
        issues.append({
            "parameter": f"TSS P99 = {inputs.tss_p99} mg/L",
            "impact": "Moderate membrane fouling risk; monitor TMP closely",
            "severity": "Medium",
        })

    if inputs.turb_p99 > 10:
        issues.append({
            "parameter": f"Turbidity P99 = {inputs.turb_p99} NTU",
            "impact": "Membrane fouling risk; UV UVT reduction; ozone demand higher",
            "severity": "High",
        })
    elif inputs.turb_p99 > 5:
        issues.append({
            "parameter": f"Turbidity P99 = {inputs.turb_p99} NTU",
            "impact": "Marginal turbidity — monitor MF/UF TMP at event conditions",
            "severity": "Medium",
        })

    if inputs.pfas > 200:
        issues.append({
            "parameter": f"PFAS = {inputs.pfas} ng/L",
            "impact": "GAC capacity challenged; short-chain PFAS risk; consider PFAS-selective resin or RO",
            "severity": "High",
        })
    elif inputs.pfas > 70:
        issues.append({
            "parameter": f"PFAS = {inputs.pfas} ng/L",
            "impact": "GAC polishing required; monitor EBCT performance; regulatory sensitivity high",
            "severity": "Medium",
        })

    if inputs.nh3 > 30:
        issues.append({
            "parameter": f"NH₃-N = {inputs.nh3} mg/L",
            "impact": "Chloramine formation in distribution; nitrosamine precursor risk elevated",
            "severity": "High",
        })
    elif inputs.nh3 > 15:
        issues.append({
            "parameter": f"NH₃-N = {inputs.nh3} mg/L",
            "impact": "Monitor nitrification in BAC; chloramine formation in distribution",
            "severity": "Medium",
        })

    if inputs.no3 > 11.3:
        issues.append({
            "parameter": f"NO₃-N = {inputs.no3} mg/L (above drinking water guideline)",
            "impact": "PRW class requires RO or biological denitrification",
            "severity": "High",
        })

    if inputs.cond > 1500:
        issues.append({
            "parameter": f"Conductivity = {inputs.cond} µS/cm",
            "impact": "RO TDS management — permeate quality and concentrate disposal burden elevated",
            "severity": "High",
        })
    elif inputs.cond > 1200:
        issues.append({
            "parameter": f"Conductivity = {inputs.cond} µS/cm",
            "impact": "Elevated TDS — RO recovery planning required for PRW",
            "severity": "Medium",
        })

    if inputs.cec_risk == "high":
        issues.append({
            "parameter": "CEC Risk = High",
            "impact": "Enhanced bioassay monitoring required for A, A+, PRW; additional GAC/AOP capacity",
            "severity": "High",
        })

    if inputs.nitrosamine_risk == "high":
        issues.append({
            "parameter": "Nitrosamine precursor risk = High",
            "impact": "UV-AOP dose must target NDMA destruction; verify at ≥500 mJ/cm²",
            "severity": "High",
        })

    if inputs.aoc > 400:
        issues.append({
            "parameter": f"AOC = {inputs.aoc} µg/L",
            "impact": "Biological instability risk in distribution; BAC sizing and monitoring critical",
            "severity": "Medium",
        })

    if not issues:
        issues.append({
            "parameter": "WaterPoint effluent quality",
            "impact": "No significant interface issues at median conditions. Monitor P95/P99 events.",
            "severity": "Low",
        })

    return issues


def build_upgrade_deltas() -> dict:
    return {
        "C":   "Coagulation + dual-media filtration + Cl₂. Entry-level non-potable reuse.",
        "A":   "+ MF/UF membrane + Ozone or UV-AOP + BAC. Adds absolute pathogen barrier and PPCP treatment.",
        "A+":  "+ Ozone-AOP + GAC + independent UV. Adds chemical safety depth and barrier redundancy.",
        "PRW": "+ RO + UV-AOP + re-mineralisation. Full potable reuse — definitive chemical removal.",
    }
