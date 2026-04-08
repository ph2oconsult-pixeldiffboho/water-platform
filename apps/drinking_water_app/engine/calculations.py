"""
AquaPoint Calculation Engine
Drinking Water Treatment Decision-Support Platform
ph2o Consulting | Water Utility Planning Platform
"""

import math
from .constants import (
    TECHNOLOGIES,
    ENERGY_BENCHMARKS_kWh_ML,
    ELECTRICITY_COST_AUD_kWh,
    CHEMICAL_DOSES_mg_L,
    CAPEX_REFERENCE_AUD_ML_d,
    TECHNOLOGY_RISK,
    LIFECYCLE_DEFAULTS,
    MCA_DEFAULT_WEIGHTS,
    ADWG_GUIDELINES,
    SOURCE_WATER_QUALITY_PARAMS,
)


# ─── Feasibility Screening ────────────────────────────────────────────────────────

def screen_technology_feasibility(plant_type: str, flow_ML_d: float, source_water: dict, selected_technologies: list) -> dict:
    """
    Screen technologies for feasibility given plant type and source water quality.
    Returns per-technology feasibility flags and rationale.
    """
    results = {}

    for tech_key in selected_technologies:
        tech = TECHNOLOGIES.get(tech_key, {})
        flags = []
        feasible = True

        # Plant type compatibility
        applicable = tech.get("applicable_plants", [])
        if plant_type not in applicable:
            feasible = False
            flags.append(f"Not typically applied for {plant_type} plant type")

        # Source water specific screening
        turbidity = source_water.get("turbidity_ntu", 5)
        toc = source_water.get("toc_mg_l", 5)
        tds = source_water.get("tds_mg_l", 300)
        iron = source_water.get("iron_mg_l", 0.1)
        algae = source_water.get("algal_cells_ml", 500)

        if tech_key == "daf" and algae < 1000:
            flags.append("DAF provides greatest benefit for high-algae source waters")
        if tech_key == "ro" and tds < 1000:
            flags.append("RO most applicable for brackish (TDS > 1,000 mg/L) or seawater sources")
        if tech_key == "nf" and tds < 300:
            flags.append("NF most applicable where hardness or organics removal is required")
        if tech_key == "aop" and toc < 2:
            flags.append("AOP most beneficial for elevated TOC or refractory micropollutants")
        if tech_key == "ozonation" and toc < 2:
            flags.append("Ozonation most effective with moderate-to-high TOC for DBP control")
        if tech_key == "bac" and "ozonation" not in selected_technologies:
            flags.append("BAC typically follows ozonation; consider including ozonation in train")
        if tech_key == "slow_sand_filtration" and turbidity > 10:
            flags.append("Slow sand filtration requires pre-treatment for turbidity > 10 NTU")
        if tech_key == "brine_management" and plant_type not in ["membrane", "desalination"]:
            feasible = False
            flags.append("Brine management only applicable for membrane/desalination plants")

        results[tech_key] = {
            "feasible": feasible,
            "label": tech.get("label", tech_key),
            "flags": flags,
            "notes": tech.get("description", ""),
        }

    return results


# ─── Water Quality Performance ────────────────────────────────────────────────────

def assess_treatment_performance(source_water: dict, selected_technologies: list) -> dict:
    """
    Estimate treated water quality and ADWG compliance likelihood
    for the selected treatment train.
    """
    # Working estimate of removal efficiencies per parameter
    removal_efficacy = {
        # Each entry: {param: fractional removal achievable}
        "screening": {"turbidity_ntu": 0.05, "algal_cells_ml": 0.10},
        "coagulation_flocculation": {"turbidity_ntu": 0.60, "toc_mg_l": 0.25, "colour_hu": 0.50, "algal_cells_ml": 0.50},
        "daf": {"turbidity_ntu": 0.70, "algal_cells_ml": 0.85, "toc_mg_l": 0.20},
        "sedimentation": {"turbidity_ntu": 0.70, "algal_cells_ml": 0.50, "toc_mg_l": 0.15},
        "rapid_gravity_filtration": {"turbidity_ntu": 0.90, "algal_cells_ml": 0.90, "toc_mg_l": 0.10},
        "slow_sand_filtration": {"turbidity_ntu": 0.85, "algal_cells_ml": 0.95, "toc_mg_l": 0.30},
        "mf_uf": {"turbidity_ntu": 0.9995, "algal_cells_ml": 0.9995, "toc_mg_l": 0.05},
        "nf": {"turbidity_ntu": 0.9999, "tds_mg_l": 0.70, "hardness_mg_l": 0.80, "toc_mg_l": 0.90, "colour_hu": 0.95},
        "ro": {"turbidity_ntu": 0.9999, "tds_mg_l": 0.97, "hardness_mg_l": 0.97, "toc_mg_l": 0.97, "colour_hu": 0.99},
        "ozonation": {"toc_mg_l": 0.10, "colour_hu": 0.40, "algal_cells_ml": 0.30},
        "bac": {"toc_mg_l": 0.40, "colour_hu": 0.30},
        "gac": {"toc_mg_l": 0.50, "colour_hu": 0.50},
        "aop": {"toc_mg_l": 0.60, "colour_hu": 0.60},
        "chlorination": {},  # disinfection, not removal
        "chloramination": {},
        "uv_disinfection": {},
        "sludge_thickening": {},
        "brine_management": {},
    }

    iron_removal = {
        "coagulation_flocculation": 0.70,
        "sedimentation": 0.50,
        "rapid_gravity_filtration": 0.90,
        "mf_uf": 0.95,
        "ro": 0.99,
    }

    # Combine removals (series)
    predicted = dict(source_water)

    for tech_key in selected_technologies:
        eff = removal_efficacy.get(tech_key, {})
        for param, removal in eff.items():
            if param in predicted:
                predicted[param] = predicted[param] * (1 - removal)

        fe_rem = iron_removal.get(tech_key, 0)
        if fe_rem:
            predicted["iron_mg_l"] = predicted.get("iron_mg_l", 0.1) * (1 - fe_rem)

    # Disinfection: UV and Cl effectively remove microbial risk (track as qualitative)
    disinfection_technologies = [t for t in selected_technologies if t in ["chlorination", "chloramination", "uv_disinfection"]]
    disinfection_adequate = len(disinfection_technologies) >= 1

    # ADWG compliance assessment
    compliance = {}
    for param, guideline in ADWG_GUIDELINES.items():
        if param in predicted:
            val = predicted[param]
            limit = guideline.get("limit")
            if limit is not None:
                compliant = val <= limit
                compliance[param] = {
                    "predicted": round(val, 3),
                    "guideline": limit,
                    "unit": guideline["unit"],
                    "compliant": compliant,
                    "type": guideline["type"],
                }

    return {
        "predicted_quality": {k: round(v, 3) for k, v in predicted.items()},
        "compliance": compliance,
        "disinfection_adequate": disinfection_adequate,
        "disinfection_technologies": disinfection_technologies,
        "overall_compliant": all(v["compliant"] for v in compliance.values()),
    }


# ─── Energy Assessment ────────────────────────────────────────────────────────────

def calculate_energy(plant_type: str, flow_ML_d: float, selected_technologies: list,
                     electricity_cost: float = ELECTRICITY_COST_AUD_kWh) -> dict:
    """
    Estimate energy consumption and cost for the treatment train.
    Returns annual energy and cost at low/typical/high.
    """
    # Per-technology specific energy (kWh/ML)
    tech_energy_kWh_ML = {
        "screening": {"low": 2, "typical": 5, "high": 15},
        "coagulation_flocculation": {"low": 5, "typical": 10, "high": 25},
        "daf": {"low": 30, "typical": 55, "high": 90},
        "sedimentation": {"low": 5, "typical": 10, "high": 25},
        "rapid_gravity_filtration": {"low": 10, "typical": 20, "high": 40},
        "slow_sand_filtration": {"low": 2, "typical": 5, "high": 12},
        "mf_uf": {"low": 40, "typical": 70, "high": 120},
        "nf": {"low": 150, "typical": 300, "high": 500},
        "ro": {"low": 800, "typical": 1500, "high": 3000},
        "ozonation": {"low": 20, "typical": 40, "high": 80},
        "bac": {"low": 5, "typical": 10, "high": 25},
        "gac": {"low": 5, "typical": 10, "high": 20},
        "aop": {"low": 30, "typical": 70, "high": 150},
        "chlorination": {"low": 2, "typical": 5, "high": 10},
        "chloramination": {"low": 2, "typical": 5, "high": 10},
        "uv_disinfection": {"low": 10, "typical": 25, "high": 60},
        "sludge_thickening": {"low": 5, "typical": 15, "high": 40},
        "brine_management": {"low": 30, "typical": 80, "high": 200},
    }

    totals = {"low": 0.0, "typical": 0.0, "high": 0.0}
    breakdown = {}

    for tech in selected_technologies:
        bench = tech_energy_kWh_ML.get(tech, {"low": 10, "typical": 20, "high": 50})
        breakdown[tech] = bench
        for scenario in ["low", "typical", "high"]:
            totals[scenario] += bench[scenario]

    annual_ML = flow_ML_d * 365

    return {
        "specific_energy_kWh_ML": {k: round(v, 1) for k, v in totals.items()},
        "annual_energy_MWh": {k: round(v * annual_ML / 1000, 0) for k, v in totals.items()},
        "annual_cost_AUD": {k: round(v * annual_ML * electricity_cost, 0) for k, v in totals.items()},
        "technology_breakdown_kWh_ML": breakdown,
        "benchmark_kWh_ML": ENERGY_BENCHMARKS_kWh_ML.get(plant_type, {"low": 200, "typical": 400, "high": 800}),
    }


# ─── Chemical Use Assessment ──────────────────────────────────────────────────────

def calculate_chemical_use(flow_ML_d: float, selected_technologies: list,
                            source_water: dict) -> dict:
    """
    Estimate chemical consumption and annual cost for the selected treatment train.
    """
    # Map technologies to chemicals they consume
    tech_chemical_map = {
        "coagulation_flocculation": ["alum", "polymer"],
        "daf": ["alum", "polymer"],
        "sedimentation": [],
        "rapid_gravity_filtration": [],
        "slow_sand_filtration": [],
        "mf_uf": ["caustic_soda"],  # cleaning
        "nf": ["antiscalant", "acid", "caustic_soda"],
        "ro": ["antiscalant", "acid", "caustic_soda"],
        "ozonation": [],  # ozone generated on-site
        "bac": [],
        "gac": [],
        "aop": ["h2o2"],
        "chlorination": ["naocl"],
        "chloramination": ["naocl", "ammonia"],
        "uv_disinfection": [],
        "sludge_thickening": ["polymer"],
        "brine_management": [],
    }

    annual_ML = flow_ML_d * 365
    chemicals_used = {}

    for tech in selected_technologies:
        chem_list = tech_chemical_map.get(tech, [])
        for chem_key in chem_list:
            chem = CHEMICAL_DOSES_mg_L[chem_key]
            if chem_key not in chemicals_used:
                # Adjust dose for source water quality where relevant
                dose_typical = chem["typical"]
                toc = source_water.get("toc_mg_l", 5)
                turbidity = source_water.get("turbidity_ntu", 5)

                if chem_key == "alum" and turbidity > 20:
                    dose_typical = min(chem["high"], dose_typical * 1.3)
                if chem_key == "alum" and toc > 8:
                    dose_typical = min(chem["high"], dose_typical * 1.2)

                annual_kg = dose_typical * annual_ML  # mg/L × ML/yr = kg/yr (1 mg/L × 1 ML = 1 kg)
                annual_cost = annual_kg * chem["unit_cost_AUD_kg"]

                chemicals_used[chem_key] = {
                    "label": chem["label"],
                    "dose_mg_L": round(dose_typical, 2),
                    "annual_kg": round(annual_kg, 0),
                    "annual_cost_AUD": round(annual_cost, 0),
                    "unit_cost_AUD_kg": chem["unit_cost_AUD_kg"],
                }

    total_chemical_cost = sum(v["annual_cost_AUD"] for v in chemicals_used.values())

    return {
        "chemicals": chemicals_used,
        "total_annual_cost_AUD": round(total_chemical_cost, 0),
    }


# ─── CAPEX Assessment ─────────────────────────────────────────────────────────────

def calculate_capex(flow_ML_d: float, selected_technologies: list,
                    contingency_pct: float = 20.0) -> dict:
    """
    Estimate CAPEX for the selected treatment train.
    Returns component-level and total estimates at low/typical/high.
    """
    breakdown = {}
    totals = {"low": 0.0, "typical": 0.0, "high": 0.0}

    # Scale factor: economy of scale (non-linear with flow)
    # Reference: 10 ML/d. Exponent ~0.65 (water industry norm)
    scale_exponent = 0.65
    reference_flow = 10.0
    scale_factor = (flow_ML_d / reference_flow) ** scale_exponent if flow_ML_d != reference_flow else 1.0

    for tech in selected_technologies:
        ref = CAPEX_REFERENCE_AUD_ML_d.get(tech, {"low": 100_000, "typical": 300_000, "high": 700_000})
        breakdown[tech] = {
            "label": TECHNOLOGIES[tech]["label"],
        }
        for scenario in ["low", "typical", "high"]:
            # Base cost = unit rate × reference flow, then scale
            base = ref[scenario] * reference_flow * scale_factor
            breakdown[tech][scenario] = round(base, 0)
            totals[scenario] += base

    # Add contingency
    contingency_factor = 1 + contingency_pct / 100
    totals_with_contingency = {k: round(v * contingency_factor, 0) for k, v in totals.items()}

    return {
        "technology_breakdown_AUD": breakdown,
        "subtotal_AUD": {k: round(v, 0) for k, v in totals.items()},
        "contingency_pct": contingency_pct,
        "total_capex_AUD": totals_with_contingency,
    }


# ─── OPEX Assessment ─────────────────────────────────────────────────────────────

def calculate_opex(flow_ML_d: float, energy_results: dict, chemical_results: dict,
                   selected_technologies: list) -> dict:
    """
    Estimate annual OPEX: energy + chemicals + maintenance + labour + membrane/media replacement.
    """
    annual_ML = flow_ML_d * 365

    energy_cost = energy_results["annual_cost_AUD"]["typical"]
    chemical_cost = chemical_results["total_annual_cost_AUD"]

    # Maintenance: 1.5–3% of CAPEX typical — estimated from unit rates
    capex_proxy = sum(
        CAPEX_REFERENCE_AUD_ML_d.get(t, {}).get("typical", 200_000) * min(flow_ML_d, 50)
        for t in selected_technologies
    )
    maintenance_cost = round(capex_proxy * 0.02, 0)

    # Labour: rule-of-thumb by scale
    if flow_ML_d < 5:
        labour_cost = 250_000
    elif flow_ML_d < 20:
        labour_cost = 500_000
    elif flow_ML_d < 100:
        labour_cost = 1_000_000
    else:
        labour_cost = 2_000_000

    # Membrane replacement (if applicable)
    membrane_techs = [t for t in selected_technologies if t in ["mf_uf", "nf", "ro"]]
    membrane_replacement = 0
    if membrane_techs:
        # ~15% of membrane CAPEX per year amortised over 10 years
        for mt in membrane_techs:
            ref = CAPEX_REFERENCE_AUD_ML_d.get(mt, {}).get("typical", 1_000_000)
            membrane_replacement += ref * min(flow_ML_d, 50) * 0.015

    # GAC/media replacement
    media_techs = [t for t in selected_technologies if t in ["gac", "bac"]]
    media_replacement = 0
    if media_techs:
        for mt in media_techs:
            ref = CAPEX_REFERENCE_AUD_ML_d.get(mt, {}).get("typical", 400_000)
            media_replacement += ref * min(flow_ML_d, 50) * 0.08  # ~12.5 yr life = 8%/yr

    total_opex = (
        energy_cost + chemical_cost + maintenance_cost +
        labour_cost + membrane_replacement + media_replacement
    )

    return {
        "energy_AUD": round(energy_cost, 0),
        "chemicals_AUD": round(chemical_cost, 0),
        "maintenance_AUD": round(maintenance_cost, 0),
        "labour_AUD": round(labour_cost, 0),
        "membrane_replacement_AUD": round(membrane_replacement, 0),
        "media_replacement_AUD": round(media_replacement, 0),
        "total_annual_opex_AUD": round(total_opex, 0),
        "unit_opex_AUD_ML": round(total_opex / annual_ML, 1) if annual_ML > 0 else 0,
    }


# ─── Lifecycle Cost (NPV) ─────────────────────────────────────────────────────────

def calculate_lifecycle_cost(capex_results: dict, opex_results: dict,
                              analysis_period: int = 30,
                              discount_rate_pct: float = 7.0,
                              opex_escalation_pct: float = 2.5) -> dict:
    """
    Calculate 30-year NPV of lifecycle costs (typical scenario).
    """
    capex = capex_results["total_capex_AUD"]["typical"]
    annual_opex = opex_results["total_annual_opex_AUD"]

    r = discount_rate_pct / 100
    g = opex_escalation_pct / 100

    # PV of growing annuity
    if abs(r - g) < 1e-6:
        pv_opex = annual_opex * analysis_period / (1 + r)
    else:
        pv_opex = annual_opex * (1 - ((1 + g) / (1 + r)) ** analysis_period) / (r - g)

    npv_total = capex + pv_opex

    # Unit cost (AUD/kL)
    # Estimate annual production from OPEX results context: need flow
    # Approximate from unit_opex_AUD_ML
    unit_opex_ML = opex_results.get("unit_opex_AUD_ML", 0)

    return {
        "capex_AUD": round(capex, 0),
        "pv_opex_AUD": round(pv_opex, 0),
        "npv_total_AUD": round(npv_total, 0),
        "analysis_period_years": analysis_period,
        "discount_rate_pct": discount_rate_pct,
        "opex_escalation_pct": opex_escalation_pct,
        "capex_fraction_pct": round(capex / npv_total * 100, 1) if npv_total > 0 else 0,
        "opex_fraction_pct": round(pv_opex / npv_total * 100, 1) if npv_total > 0 else 0,
    }


# ─── Risk Assessment ──────────────────────────────────────────────────────────────

def assess_risk(selected_technologies: list, source_water: dict, plant_type: str) -> dict:
    """
    Score implementation, operational, and regulatory risk for the treatment train.
    """
    risk_score_map = {"Low": 1, "Medium": 2, "High": 3}
    score_label_map = {1: "Low", 2: "Medium", 3: "High"}

    tech_risks = {}
    total_impl = total_oper = total_reg = 0
    count = 0

    for tech in selected_technologies:
        risk = TECHNOLOGY_RISK.get(tech, {"implementation": "Medium", "operational": "Medium", "regulatory": "Medium"})
        impl_score = risk_score_map[risk["implementation"]]
        oper_score = risk_score_map[risk["operational"]]
        reg_score = risk_score_map[risk["regulatory"]]

        tech_risks[tech] = {
            "label": TECHNOLOGIES[tech]["label"],
            "implementation": risk["implementation"],
            "operational": risk["operational"],
            "regulatory": risk["regulatory"],
            "composite_score": round((impl_score + oper_score + reg_score) / 3, 1),
        }

        total_impl += impl_score
        total_oper += oper_score
        total_reg += reg_score
        count += 1

    if count == 0:
        return {"technology_risks": {}, "overall": {}}

    avg_impl = total_impl / count
    avg_oper = total_oper / count
    avg_reg = total_reg / count
    overall_score = (avg_impl + avg_oper + avg_reg) / 3

    # Additional source water risk flags
    water_quality_risk_flags = []
    if source_water.get("turbidity_ntu", 5) > 50:
        water_quality_risk_flags.append("High turbidity events increase treatment burden and operational risk")
    if source_water.get("algal_cells_ml", 500) > 10000:
        water_quality_risk_flags.append("High algal counts present taste/odour and cyanotoxin risk")
    if source_water.get("toc_mg_l", 5) > 10:
        water_quality_risk_flags.append("High TOC elevates DBP formation risk requiring careful disinfection management")
    if source_water.get("tds_mg_l", 300) > 1500:
        water_quality_risk_flags.append("High TDS may require periodic membrane cleaning and increased antiscalant doses")

    return {
        "technology_risks": tech_risks,
        "overall": {
            "implementation_score": round(avg_impl, 1),
            "operational_score": round(avg_oper, 1),
            "regulatory_score": round(avg_reg, 1),
            "composite_score": round(overall_score, 1),
            "implementation_label": score_label_map[round(avg_impl)],
            "operational_label": score_label_map[round(avg_oper)],
            "regulatory_label": score_label_map[round(avg_reg)],
            "overall_label": score_label_map[round(overall_score)],
        },
        "water_quality_risk_flags": water_quality_risk_flags,
    }


# ─── Environmental Assessment ─────────────────────────────────────────────────────

def assess_environmental(flow_ML_d: float, selected_technologies: list,
                          energy_results: dict, chemical_results: dict) -> dict:
    """
    Estimate carbon footprint and key environmental indicators.
    """
    EMISSION_FACTOR_kg_CO2_kWh = 0.79  # Australia average grid (Scope 2)

    annual_energy_MWh = energy_results["annual_energy_MWh"]["typical"]
    annual_CO2_tonnes = annual_energy_MWh * EMISSION_FACTOR_kg_CO2_kWh

    # Chemical carbon proxies (kg CO2-e per kg chemical)
    chem_emission_factors = {
        "alum": 0.37,
        "ferric_chloride": 0.84,
        "polymer": 3.0,
        "lime": 0.75,
        "chlorine": 1.8,
        "naocl": 1.5,
        "ammonia": 2.5,
        "caustic_soda": 1.1,
        "co2": 1.0,
        "h2o2": 1.8,
        "antiscalant": 3.5,
        "acid": 0.5,
    }

    chem_CO2 = 0
    for chem_key, chem_data in chemical_results["chemicals"].items():
        factor = chem_emission_factors.get(chem_key, 1.5)
        chem_CO2 += chem_data["annual_kg"] * factor / 1000  # tonnes

    total_CO2_tonnes = annual_CO2_tonnes + chem_CO2
    annual_ML = flow_ML_d * 365
    unit_CO2 = total_CO2_tonnes * 1000 / (annual_ML * 1000) if annual_ML > 0 else 0  # kg CO2/kL

    # Residuals generation
    residuals_flags = []
    if "coagulation_flocculation" in selected_technologies or "sedimentation" in selected_technologies:
        residuals_flags.append("Coagulation sludge requiring thickening and dewatering for disposal")
    if any(t in selected_technologies for t in ["mf_uf", "nf", "ro"]):
        residuals_flags.append("Membrane backwash/cleaning waste requiring treatment or disposal")
    if any(t in selected_technologies for t in ["nf", "ro"]):
        residuals_flags.append("RO/NF concentrate requiring disposal — regulatory approval typically required")
    if "bac" in selected_technologies or "gac" in selected_technologies:
        residuals_flags.append("Spent GAC/BAC requiring reactivation or disposal")

    return {
        "annual_energy_CO2_tonnes": round(annual_CO2_tonnes, 0),
        "annual_chemical_CO2_tonnes": round(chem_CO2, 0),
        "total_annual_CO2_tonnes": round(total_CO2_tonnes, 0),
        "unit_CO2_kg_per_kL": round(unit_CO2, 3),
        "emission_factor_kg_CO2_kWh": EMISSION_FACTOR_kg_CO2_kWh,
        "residuals_considerations": residuals_flags,
    }


# ─── Regulatory Compliance ────────────────────────────────────────────────────────

def assess_regulatory_compliance(selected_technologies: list, treatment_performance: dict,
                                  plant_type: str) -> dict:
    """
    Assess regulatory compliance status for Australian ADWG context.
    """
    compliance_items = []
    issues = []

    # Check ADWG compliance from treatment performance
    for param, comp_data in treatment_performance.get("compliance", {}).items():
        status = "✓ Compliant" if comp_data["compliant"] else "✗ Exceedance"
        compliance_items.append({
            "parameter": param,
            "predicted": comp_data["predicted"],
            "guideline": comp_data["guideline"],
            "unit": comp_data["unit"],
            "type": comp_data["type"],
            "status": status,
            "compliant": comp_data["compliant"],
        })
        if not comp_data["compliant"]:
            issues.append(f"{param}: predicted {comp_data['predicted']} {comp_data['unit']} exceeds ADWG {comp_data['guideline']} {comp_data['unit']}")

    # Disinfection adequacy
    disinfection_ok = treatment_performance.get("disinfection_adequate", False)
    if not disinfection_ok:
        issues.append("No primary disinfection technology selected — ADWG requires demonstrated pathogen inactivation")

    # Special technology regulatory considerations
    regulatory_notes = []
    if "ro" in selected_technologies or "nf" in selected_technologies:
        regulatory_notes.append("RO/NF concentrate disposal requires environmental permit — engage regulator early")
    if "aop" in selected_technologies:
        regulatory_notes.append("AOP systems may require H₂O₂ residual monitoring at point of supply")
    if "ozonation" in selected_technologies:
        regulatory_notes.append("Ozone systems require bromate monitoring where bromide present in source water")
    if "chloramination" in selected_technologies:
        regulatory_notes.append("Chloramine residual must be maintained; nitrification monitoring in distribution required")
    if "brine_management" in selected_technologies:
        regulatory_notes.append("Brine/concentrate disposal to surface water or sewer requires works approval")

    overall_compliant = all(c["compliant"] for c in compliance_items) and disinfection_ok

    return {
        "compliance_items": compliance_items,
        "overall_compliant": overall_compliant,
        "issues": issues,
        "regulatory_notes": regulatory_notes,
        "framework": "Australian Drinking Water Guidelines (ADWG 2011, updated 2022)",
    }


# ─── MCA Scoring ─────────────────────────────────────────────────────────────────

def calculate_mca_score(treatment_performance: dict, lifecycle_cost: dict,
                         risk_results: dict, energy_results: dict,
                         environmental_results: dict, regulatory_results: dict,
                         weights: dict = None) -> dict:
    """
    Multi-criteria score (0–100) for the treatment train.
    """
    if weights is None:
        weights = MCA_DEFAULT_WEIGHTS

    scores = {}

    # Water quality (0–100): based on compliance and predicted quality
    n_compliant = sum(1 for c in treatment_performance.get("compliance", {}).values() if c["compliant"])
    n_total = max(len(treatment_performance.get("compliance", {})), 1)
    disinfect_bonus = 10 if treatment_performance.get("disinfection_adequate") else 0
    scores["water_quality"] = min(100, (n_compliant / n_total) * 90 + disinfect_bonus)

    # Lifecycle cost (0–100): lower cost = higher score; normalise against $500M NPV
    npv = lifecycle_cost.get("npv_total_AUD", 50_000_000)
    scores["lifecycle_cost"] = max(0, 100 - (npv / 500_000_000) * 100)

    # Risk (0–100): lower risk score = higher MCA score
    risk_score = risk_results.get("overall", {}).get("composite_score", 2)  # 1-3
    scores["risk"] = max(0, 100 - (risk_score - 1) * 50)

    # Energy (0–100): normalise against 5000 kWh/ML
    specific_energy = energy_results.get("specific_energy_kWh_ML", {}).get("typical", 400)
    scores["energy"] = max(0, 100 - (specific_energy / 5000) * 100)

    # Environmental (0–100): lower CO2/kL = higher score; normalise against 2 kg CO2/kL
    unit_CO2 = environmental_results.get("unit_CO2_kg_per_kL", 0.5)
    scores["environmental"] = max(0, 100 - (unit_CO2 / 2) * 100)

    # Regulatory (0–100): compliance fraction
    comp_items = regulatory_results.get("compliance_items", [])
    n_reg_compliant = sum(1 for c in comp_items if c["compliant"])
    n_reg_total = max(len(comp_items), 1)
    scores["regulatory_compliance"] = (n_reg_compliant / n_reg_total) * 100

    # Weighted total
    total = sum(scores.get(k, 0) * v for k, v in weights.items())
    total = min(100, max(0, total))

    return {
        "scores": {k: round(v, 1) for k, v in scores.items()},
        "weights": weights,
        "total_score": round(total, 1),
    }


# ─── Master Analysis Runner ───────────────────────────────────────────────────────

def run_full_analysis(inputs: dict) -> dict:
    """
    Run complete AquaPoint analysis for a given set of inputs.
    Returns structured results across all analysis layers.
    """
    plant_type = inputs["plant_type"]
    flow_ML_d = inputs["flow_ML_d"]
    source_water = inputs["source_water"]
    selected_technologies = inputs["selected_technologies"]
    lifecycle_params = inputs.get("lifecycle_params", {})
    electricity_cost = inputs.get("electricity_cost_AUD_kWh", ELECTRICITY_COST_AUD_kWh)
    mca_weights = inputs.get("mca_weights", MCA_DEFAULT_WEIGHTS)
    contingency_pct = lifecycle_params.get("capex_contingency_pct", LIFECYCLE_DEFAULTS["capex_contingency_pct"])
    analysis_period = lifecycle_params.get("analysis_period_years", LIFECYCLE_DEFAULTS["analysis_period_years"])
    discount_rate = lifecycle_params.get("discount_rate_pct", LIFECYCLE_DEFAULTS["discount_rate_pct"])
    escalation = lifecycle_params.get("opex_escalation_pct", LIFECYCLE_DEFAULTS["opex_escalation_pct"])

    results = {}

    # 1. Feasibility
    results["feasibility"] = screen_technology_feasibility(
        plant_type, flow_ML_d, source_water, selected_technologies
    )

    # 2. Treatment Performance & Water Quality
    results["treatment_performance"] = assess_treatment_performance(source_water, selected_technologies)

    # 3. Energy
    results["energy"] = calculate_energy(plant_type, flow_ML_d, selected_technologies, electricity_cost)

    # 4. Chemical Use
    results["chemical_use"] = calculate_chemical_use(flow_ML_d, selected_technologies, source_water)

    # 5. CAPEX
    results["capex"] = calculate_capex(flow_ML_d, selected_technologies, contingency_pct)

    # 6. OPEX
    results["opex"] = calculate_opex(flow_ML_d, results["energy"], results["chemical_use"], selected_technologies)

    # 7. Lifecycle Cost
    results["lifecycle_cost"] = calculate_lifecycle_cost(
        results["capex"], results["opex"], analysis_period, discount_rate, escalation
    )

    # 8. Risk
    results["risk"] = assess_risk(selected_technologies, source_water, plant_type)

    # 9. Environmental
    results["environmental"] = assess_environmental(
        flow_ML_d, selected_technologies, results["energy"], results["chemical_use"]
    )

    # 10. Regulatory Compliance
    results["regulatory"] = assess_regulatory_compliance(
        selected_technologies, results["treatment_performance"], plant_type
    )

    # 11. MCA Score
    results["mca"] = calculate_mca_score(
        results["treatment_performance"],
        results["lifecycle_cost"],
        results["risk"],
        results["energy"],
        results["environmental"],
        results["regulatory"],
        mca_weights,
    )

    return results
