"""
domains/wastewater/domain_interface.py

Wastewater Domain Interface.
Orchestrates all wastewater domain calculations and connects to the shared core.

This is the only point of contact between:
    - the wastewater domain (technologies, risk items, validation rules)
    - the shared core engines (costing, carbon, risk, validation)

The Streamlit app only instantiates this class and calls run_scenario().
It never imports individual technology modules directly.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional

from core.project.project_model import AssumptionsSet, ScenarioModel
from core.costing.costing_engine import CostingEngine
from core.carbon.carbon_engine import CarbonEngine
from core.risk.risk_engine import RiskEngine
from core.validation.validation_engine import ValidationEngine
from core.assumptions.assumptions_manager import AssumptionsManager

from domains.wastewater.input_model import WastewaterInputs
from domains.wastewater.result_model import WastewaterCalculationResult
from domains.wastewater.validation_rules import register_wastewater_validators
from domains.wastewater.risk_items import get_wastewater_risk_items
from domains.wastewater.technologies.base_technology import TechnologyResult
from domains.wastewater.technologies.bnr import BNRTechnology, BNRInputs
from domains.wastewater.technologies.bnr_mbr import BNRMBRTechnology, BNRMBRInputs
from domains.wastewater.technologies.mabr_bnr import MABRBNRTechnology, MABRBNRInputs
from domains.wastewater.technologies.granular_sludge import GranularSludgeTechnology, GranularSludgeInputs
from domains.wastewater.technologies.ifas_mbbr import IFASMBBRTechnology, IFASMBBRInputs
from domains.wastewater.technologies.anmbr import AnMBRTechnology, AnMBRInputs
from domains.wastewater.technologies.sidestream_pna import SidestreamPNATechnology, SidestreamPNAInputs
from domains.wastewater.technologies.mob_biofilm import MOBTechnology, MOBInputs
from domains.wastewater.technologies.solids.thermal_biosolids import ThermalBiosolidsTechnology, ThermalBiosolidsInputs
from domains.wastewater.technologies.solids.ad_chp import ADCHPTechnology, ADCHPInputs
from domains.wastewater.technologies.tertiary.chemical_p_removal import CPRTechnology, CPRInputs
from domains.wastewater.technologies.tertiary.tertiary_filtration import TertiaryFiltrationTechnology, TertiaryFiltrationInputs
from domains.wastewater.technologies.reuse.advanced_reuse import AdvancedReuseTechnology, AdvancedReuseInputs


# ─────────────────────────────────────────────────────────────────────────────
# TECHNOLOGY REGISTRY
# Adding a new technology:
#   1. Create a new file in technologies/
#   2. Implement BaseTechnology
#   3. Add an entry here
#   No other file needs to change.
# ─────────────────────────────────────────────────────────────────────────────

TECHNOLOGY_REGISTRY: Dict[str, Any] = {
    # Biological treatment (existing)
    "bnr":             BNRTechnology,
    "bnr_mbr":         BNRMBRTechnology,
    "mabr_bnr":        MABRBNRTechnology,
    "granular_sludge": GranularSludgeTechnology,
    "ifas_mbbr":       IFASMBBRTechnology,
    "anmbr":           AnMBRTechnology,
    "sidestream_pna":  SidestreamPNATechnology,
    # New modules
    "mob":                MOBTechnology,
    "thermal_biosolids":  ThermalBiosolidsTechnology,
    "ad_chp":             ADCHPTechnology,
    # Tertiary + reuse
    "cpr":                CPRTechnology,
    "tertiary_filt":      TertiaryFiltrationTechnology,
    "adv_reuse":          AdvancedReuseTechnology,
}

TECHNOLOGY_INPUT_CLASSES: Dict[str, Any] = {
    "bnr":                BNRInputs,
    "bnr_mbr":            BNRMBRInputs,
    "mabr_bnr":           MABRBNRInputs,
    "granular_sludge":    GranularSludgeInputs,
    "ifas_mbbr":          IFASMBBRInputs,
    "anmbr":              AnMBRInputs,
    "sidestream_pna":     SidestreamPNAInputs,
    "mob":                MOBInputs,
    "thermal_biosolids":  ThermalBiosolidsInputs,
    "ad_chp":             ADCHPInputs,
    "cpr":                CPRInputs,
    "tertiary_filt":      TertiaryFiltrationInputs,
    "adv_reuse":          AdvancedReuseInputs,
}



def stamp_compliance(scenario: Any) -> None:
    """
    Stamp compliance status onto a ScenarioModel from its domain_specific_outputs.
    Call this after cost_result and domain_specific_outputs are both populated.
    This is the single source of truth for is_compliant / compliance_status.
    """
    dso = getattr(scenario, "domain_specific_outputs", None) or {}
    tp  = dso.get("technology_performance", {})
    hard_fail_issues = []
    for tc_data in tp.values():
        flag   = tc_data.get("compliance_flag", "")
        issues = tc_data.get("compliance_issues", "") or ""
        if flag == "Review Required" and issues:
            hard_fail_issues.append(issues)
    if hard_fail_issues:
        scenario.is_compliant      = False
        scenario.compliance_status = "Non-compliant"
        scenario.compliance_issues = " | ".join(hard_fail_issues)
    else:
        scenario.is_compliant      = True
        scenario.compliance_status = "Compliant"
        scenario.compliance_issues = ""

class WastewaterDomainInterface:
    """
    Orchestrates wastewater scenario calculations.

    Responsibilities
    ----------------
    1. Validate inputs using the shared ValidationEngine
       (with domain-specific hooks registered)
    2. Run individual technology plugins in sequence
    3. Aggregate technology outputs (energy, chemicals, cost items)
    4. Pass aggregated outputs to shared core engines
    5. Build and return a WastewaterCalculationResult

    The domain interface is intentionally thin.  All engineering
    science is in the technology plugins.  All costing/carbon/risk
    science is in the shared core engines.
    """

    def __init__(self, assumptions: AssumptionsSet):
        self.assumptions = assumptions
        self._mgr = AssumptionsManager()

        # Instantiate core engines
        self._costing_engine = CostingEngine(assumptions)
        self._carbon_engine = CarbonEngine(assumptions)
        self._risk_engine = RiskEngine(assumptions)

        # Validation engine with domain hooks registered
        self._validation_engine = ValidationEngine()
        register_wastewater_validators(self._validation_engine)

    def run_scenario(
        self,
        inputs: WastewaterInputs,
        technology_sequence: List[str],
        technology_parameters: Dict[str, Dict[str, Any]],
    ) -> WastewaterCalculationResult:
        """
        Execute the full calculation pipeline for one wastewater scenario.

        Parameters
        ----------
        inputs : WastewaterInputs
            Plant design inputs (flows, water quality, effluent targets)
        technology_sequence : list of str
            Ordered list of technology codes, e.g. ["bnr"] or ["mbr"]
        technology_parameters : dict
            {tech_code: {parameter: value}} — technology-specific inputs

        Returns
        -------
        WastewaterCalculationResult
        """
        result = WastewaterCalculationResult()

        # ── Step 1: Validate inputs ───────────────────────────────────────
        validation_result = self._validation_engine.validate(inputs)
        result.validation_result = validation_result

        if not validation_result.is_valid:
            result.is_valid = False
            return result

        # ── Step 2: Run technology calculations ───────────────────────────
        tech_results = self._run_technology_calculations(
            inputs, technology_sequence, technology_parameters
        )
        result.technology_results = tech_results

        # ── Step 3: Aggregate outputs ─────────────────────────────────────
        aggregated = self._aggregate_technology_results(tech_results)
        result.aggregated = aggregated

        # ── Step 4: Cross-validate outputs ────────────────────────────────
        # Re-run validation with domain result for cross-checks
        validation_result = self._validation_engine.validate(inputs, result)
        result.validation_result = validation_result

        # ── Step 5: Shared core engines ───────────────────────────────────
        result.cost_result = self._costing_engine.calculate(
            capex_items=aggregated["all_capex_items"],
            opex_items=aggregated["all_opex_items"],
            design_flow_mld=inputs.design_flow_mld,
            analysis_period_years=inputs.planning_horizon_years,
            tech_codes=technology_sequence,
        )

        result.carbon_result = self._carbon_engine.calculate(
            energy_kwh_per_day=aggregated["total_energy_kwh_day"],
            chemical_consumption=aggregated["total_chemical_consumption"],
            domain_specific_emissions=aggregated["process_emissions_tco2e_yr"],
            design_flow_mld=inputs.design_flow_mld,
        )

        risk_items = get_wastewater_risk_items(inputs, tech_results)
        result.risk_result = self._risk_engine.calculate(risk_items=risk_items)

        # ── Step 6: Engineering summary ───────────────────────────────────
        result.engineering_summary = self._build_engineering_summary(
            inputs, tech_results, aggregated
        )
        result.is_valid = True

        return result

    def update_scenario_model(
        self,
        scenario: ScenarioModel,
        calc_result: WastewaterCalculationResult,
    ) -> ScenarioModel:
        """
        Write calculation results back into a ScenarioModel.
        Called by the Streamlit app after run_scenario() completes.
        """
        scenario.cost_result = calc_result.cost_result
        scenario.carbon_result = calc_result.carbon_result
        scenario.risk_result = calc_result.risk_result
        scenario.validation_result = calc_result.validation_result
        scenario.domain_specific_outputs = calc_result.to_domain_outputs_dict()
        scenario.mark_calculated()

        # ── Stamp compliance onto ScenarioModel — single source of truth ─────
        # Every downstream consumer (report, scoring, UI) reads from here.
        dso = scenario.domain_specific_outputs or {}
        tp  = dso.get("technology_performance", {})
        hard_fail_issues = []
        for tc_data in tp.values():
            flag   = tc_data.get("compliance_flag", "")
            issues = tc_data.get("compliance_issues", "") or ""
            if flag == "Meets Targets":
                pass  # keep checking others
            elif flag == "Review Required" and issues:
                hard_fail_issues.append(issues)
        if hard_fail_issues:
            scenario.is_compliant       = False
            scenario.compliance_status  = "Non-compliant"
            scenario.compliance_issues  = " | ".join(hard_fail_issues)
        else:
            # Check for achievability warnings (CWI) vs clean pass
            scenario.is_compliant      = True
            scenario.compliance_status = "Compliant"
            scenario.compliance_issues = ""

        return scenario

    # ── Private methods ───────────────────────────────────────────────────

    def _run_technology_calculations(
        self,
        inputs: WastewaterInputs,
        technology_sequence: List[str],
        technology_parameters: Dict[str, Dict[str, Any]],
    ) -> Dict[str, TechnologyResult]:
        """Run each technology plugin and collect results."""
        results: Dict[str, TechnologyResult] = {}

        for tech_code in technology_sequence:
            TechClass = TECHNOLOGY_REGISTRY.get(tech_code)
            if not TechClass:
                # Unknown technology — create a placeholder result with a note
                placeholder = TechnologyResult(
                    technology_name=tech_code,
                    technology_code=tech_code,
                    calculation_notes=[
                        f"Technology '{tech_code}' is not yet implemented in this version."
                    ],
                )
                results[tech_code] = placeholder
                continue

            tech_instance = TechClass(self.assumptions)
            InputClass = TECHNOLOGY_INPUT_CLASSES.get(tech_code)

            # Deserialise technology parameters to the correct dataclass
            if InputClass:
                params = technology_parameters.get(tech_code, {})
                # Only pass known fields to avoid dataclass errors
                known_fields = {
                    f.name for f in InputClass.__dataclass_fields__.values()
                    if not f.name.startswith("_")
                }
                clean_params = {k: v for k, v in params.items() if k in known_fields}
                tech_inputs = InputClass(**clean_params)
            else:
                tech_inputs = {}

            # ── Inject influent quality from WastewaterInputs ─────────────
            # CRITICAL: modules read influent via _load_influent() from
            # engineering_assumptions. Without this injection every scenario
            # runs on YAML defaults (BOD=250, TKN=45) regardless of user inputs.
            influent_overrides = {
                "influent_bod_mg_l":            inputs.influent_bod_mg_l,
                "influent_cod_mg_l":            inputs.influent_cod_mg_l,
                # Canonical public field is influent_tkn_mg_l (WastewaterInputs).
                # Technology modules read influent_tn_mg_l internally via _load_influent().
                # Both keys are written so all read paths resolve correctly.
                "influent_tkn_mg_l":            inputs.influent_tkn_mg_l,
                "influent_tn_mg_l":             inputs.influent_tkn_mg_l,  # internal alias
                "influent_nh4_mg_l":            inputs.influent_nh4_mg_l,
                "influent_tss_mg_l":            inputs.influent_tss_mg_l,
                "influent_tp_mg_l":             inputs.influent_tp_mg_l,
                "influent_temperature_celsius": inputs.influent_temperature_celsius,
                # Peak flow factor — used by clarifier sizing in all CAS-family modules
                "peak_flow_factor":             inputs.peak_flow_factor,
                # DO setpoint — used by aeration energy calculation (SOTR driving force)
                "do_setpoint_mg_l":             inputs.do_setpoint_mg_l,
            }
            for k, v in influent_overrides.items():
                if v is not None:
                    tech_instance.assumptions.engineering_assumptions[k] = v

            # ── Inject effluent targets from WastewaterInputs ─────────────
            # This ensures technology modules use scenario-specific targets
            # rather than YAML defaults (which are fixed at 10/1/0.5 mg/L)
            effluent_overrides = {
                "effluent_tn_mg_l":  inputs.effluent_tn_mg_l,
                "effluent_nh4_mg_l": inputs.effluent_nh4_mg_l,
                "effluent_tp_mg_l":  inputs.effluent_tp_mg_l,
                "effluent_bod_mg_l": inputs.effluent_bod_mg_l,
                "effluent_tss_mg_l": inputs.effluent_tss_mg_l,
            }
            for k, v in effluent_overrides.items():
                if v is not None:
                    tech_instance.assumptions.engineering_assumptions[k] = v

            tech_result = tech_instance.calculate(inputs.design_flow_mld, tech_inputs)

            # ── Compliance check ──────────────────────────────────────────
            # Compare technology output against effluent targets and add warnings
            _check_effluent_compliance(tech_result, inputs)

            results[tech_code] = tech_result

        return results

    def _aggregate_technology_results(
        self, tech_results: Dict[str, TechnologyResult]
    ) -> Dict[str, Any]:
        """
        Aggregate outputs across all technology plugins.
        Produces the inputs required by the shared core engines.
        """
        total_energy = 0.0
        total_chemicals: Dict[str, float] = {}
        process_emissions: Dict[str, float] = {}
        all_capex_items = []
        all_opex_items = []

        for tech_code, result in tech_results.items():
            total_energy += result.energy_kwh_per_day

            for chem, qty in result.chemical_consumption.items():
                total_chemicals[chem] = total_chemicals.get(chem, 0.0) + qty

            for emission_source, tco2e in result.process_emissions_tco2e_yr.items():
                key = f"{tech_code}_{emission_source}"
                process_emissions[key] = tco2e

            all_capex_items.extend(result.capex_items)
            all_opex_items.extend(result.opex_items)

        # Sum sludge production across technologies
        total_sludge_kgds_day = sum(
            r.performance_outputs.get("sludge_production_kgds_day", 0.0)
            for r in tech_results.values()
        )

        # Aggregate N2O and CH4 for UI display (N2O uncertainty panel)
        total_n2o_tco2e_yr = sum(
            getattr(r.carbon, "n2o_biological_tco2e_yr", 0.0) or 0.0
            for r in tech_results.values()
        )
        total_ch4_tco2e_yr = sum(
            getattr(r.carbon, "ch4_fugitive_tco2e_yr", 0.0) or 0.0
            for r in tech_results.values()
        )

        return {
            "total_energy_kwh_day": round(total_energy, 2),
            "total_chemical_consumption": {
                k: round(v, 4) for k, v in total_chemicals.items()
            },
            "process_emissions_tco2e_yr": process_emissions,
            "total_sludge_kgds_day": round(total_sludge_kgds_day, 1),
            "all_capex_items": all_capex_items,
            "all_opex_items": all_opex_items,
            "total_n2o_tco2e_yr": round(total_n2o_tco2e_yr, 1),
            "total_ch4_tco2e_yr": round(total_ch4_tco2e_yr, 1),
        }

    def _build_engineering_summary(
        self,
        inputs: WastewaterInputs,
        tech_results: Dict[str, TechnologyResult],
        aggregated: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Build a human-readable engineering summary for display."""
        summary = {
            "design_flow_mld": inputs.design_flow_mld,
            "technology_sequence": list(tech_results.keys()),
            "total_energy_kwh_day": aggregated["total_energy_kwh_day"],
            "specific_energy_kwh_kl": (
                aggregated["total_energy_kwh_day"] / (inputs.design_flow_mld * 1000)
                if inputs.design_flow_mld else None
            ),
            "total_sludge_kgds_day": aggregated["total_sludge_kgds_day"],
        }

        # Add per-technology key parameters
        for tech_code, result in tech_results.items():
            summary[f"{tech_code}_performance"] = result.performance_outputs

        return summary


def _check_effluent_compliance(
    tech_result: "TechnologyResult",
    inputs: "WastewaterInputs",
) -> None:
    """
    Post-calculation compliance check.
    Compares technology effluent output against WastewaterInputs targets.
    Adds engineering warnings to the TechnologyResult notes.
    Also assesses whether compliance is achievable based on technology limitations.
    """
    p = tech_result.performance
    code = tech_result.technology_code

    # ── Technology capability limits ──────────────────────────────────────
    # These are the MINIMUM achievable effluent concentrations for each technology
    # under OPTIMAL conditions (warm, adequate SRT, good operation).
    # From: Metcalf & Eddy Table 8-14, WEF MOP 35, Judd 2011.
    TECH_LIMITS = {
        # code: {param: (achievable_min, condition_note)}
        "bnr":            {"nh4": (1.0,  "BNR: NH4 < 1 mg/L achievable at T>15°C, SRT>10d"),
                           "tn":  (6.0,  "BNR: TN < 6 mg/L requires supplemental carbon or 5-stage"),
                           "tp":  (0.5,  "BNR: TP < 0.5 mg/L requires chemical polish"),
                           "bod": (5.0,  "BNR: BOD < 5 mg/L requires tertiary filtration")},
        "granular_sludge":{"nh4": (1.0,  "AGS: NH4 < 1 mg/L achievable at T>12°C"),
                           "tn":  (8.0,  "AGS: TN < 8 mg/L via SND, lower requires external carbon"),
                           "tp":  (0.3,  "AGS: TP < 0.3 mg/L via enhanced bio-P at T>15°C"),
                           "bod": (5.0,  "AGS: BOD < 5 mg/L requires post-filtration")},
        "mbr":            {"nh4": (0.5,  "MBR: NH4 < 0.5 mg/L achievable at T>15°C"),
                           "tn":  (8.0,  "MBR: TN < 8 mg/L with pre-anoxic zone"),
                           "tp":  (0.2,  "MBR: TP < 0.2 mg/L with chemical dosing"),
                           "bod": (2.0,  "MBR: BOD < 2 mg/L — membrane barrier"),
                           "tss": (0.5,  "MBR: TSS < 0.5 mg/L — membrane barrier")},
        "ifas_mbbr":      {"nh4": (1.0,  "IFAS: NH4 < 1 mg/L achievable at T>15°C with sufficient media"),
                           "tn":  (8.0,  "IFAS: TN < 8 mg/L requires dedicated anoxic zone"),
                           "tp":  (0.5,  "IFAS: TP requires chemical removal"),
                           "bod": (8.0,  "IFAS/MBBR: BOD < 8 mg/L with downstream clarifier")},
        "anmbr":          {"nh4": (5.0,  "AnMBR: requires aerobic post-treatment for NH4 removal"),
                           "bod": (5.0,  "AnMBR: BOD < 5 mg/L with aerobic polishing"),
                           "tn":  (10.0, "AnMBR: TN removal limited without separate aerobic step")},
        "sidestream_pna": {"nh4": (1.0,  "PN/A: main plant NH4 — sidestream treatment only"),
                           "tn":  (6.0,  "PN/A: main plant TN — with sidestream N reduction")},
        "mob":            {"nh4": (1.0,  "MOB: NH4 < 1 mg/L achievable"),
                           "tn":  (8.0,  "MOB: TN similar to IFAS"),
                           "bod": (8.0,  "MOB: BOD requires downstream clarifier")},
        "cpr":            {"tp":  (0.05, "CPR: TP < 0.1 mg/L achievable with correct dosing")},
        "tertiary_filt":  {"tss": (2.0,  "Tertiary: TSS < 2 mg/L with RSF/cloth filter"),
                           "bod": (3.0,  "Tertiary: BOD < 3 mg/L with filtration")},
        "adv_reuse":      {"tss": (0.1,  "Reuse: TSS < 0.1 mg/L via RO"),
                           "bod": (1.0,  "Reuse: BOD < 1 mg/L via RO + UV/AOP")},
        "ad_chp":         {},
        "thermal_biosolids": {},
    }

    limits = TECH_LIMITS.get(code, {})
    targets = {
        "nh4": inputs.effluent_nh4_mg_l,
        "tn":  inputs.effluent_tn_mg_l,
        "tp":  inputs.effluent_tp_mg_l,
        "bod": inputs.effluent_bod_mg_l,
        "tss": inputs.effluent_tss_mg_l,
    }
    actuals = {
        "nh4": p.effluent_nh4_mg_l,
        "tn":  p.effluent_tn_mg_l,
        "tp":  p.effluent_tp_mg_l,
        "bod": p.effluent_bod_mg_l,
        "tss": p.effluent_tss_mg_l,
    }
    labels = {
        "nh4": "NH₄-N", "tn": "TN", "tp": "TP", "bod": "BOD", "tss": "TSS"
    }

    compliance_issues = []
    achievability_warnings = []

    for param, target in targets.items():
        if target is None:
            continue
        actual = actuals.get(param)
        tech_min, condition = limits.get(param, (None, None))

        # Check 1: Does the model output meet the target?
        if actual is not None and actual > target * 1.05:  # 5% tolerance
            compliance_issues.append(
                f"{labels[param]}: model output {actual:.1f} mg/L > target {target:.1f} mg/L"
            )

        # Check 2: Is the target achievable by this technology?
        # Only warn when target is STRICTER than what the technology can deliver
        if tech_min is not None and target < tech_min * 0.95:
            achievability_warnings.append(
                f"\u26a0 {labels[param]} target {target:.1f} mg/L is stricter than typical minimum "
                f"for {tech_result.technology_name} ({tech_min:.1f} mg/L). {condition}"
            )

    # Add warnings to notes
    for w in achievability_warnings:
        tech_result.notes.warn(w)

    # Add compliance flag to performance_outputs
    # IMPORTANT: distinguish hard fails (actual > target) from soft warnings (target is ambitious).
    # Hard fails mean the technology cannot meet the target as modelled.
    # Soft warnings mean the target is stricter than the typical technology minimum,
    # but the model still achieves it — these should NOT prevent recommendation.
    if compliance_issues:
        # Hard fail: model output exceeds target
        tech_result.performance_outputs["compliance_flag"] = "Review Required"
        tech_result.performance_outputs["compliance_issues"] = "; ".join(compliance_issues)
    elif achievability_warnings:
        # Soft warning only: achieves target but it's tighter than typical
        tech_result.performance_outputs["compliance_flag"] = "Meets Targets"
        tech_result.performance_outputs["compliance_issues"] = ""
    else:
        tech_result.performance_outputs["compliance_flag"] = "Meets Targets"
        tech_result.performance_outputs["compliance_issues"] = ""

    # Store achievability warnings separately (for report notes, not compliance gate)
    if achievability_warnings:
        tech_result.performance_outputs["achievability_warnings"] = "; ".join(
            [w.replace("⚠ ", "") for w in achievability_warnings]
        )
