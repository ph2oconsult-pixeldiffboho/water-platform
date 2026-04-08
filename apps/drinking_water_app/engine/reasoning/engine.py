"""
AquaPoint Reasoning Engine — Master Orchestrator
Runs all 5 gates and returns a structured, complete reasoning output.
"""

from dataclasses import dataclass, field
from typing import Optional

from .classifier import SourceWaterInputs, ClassificationResult, run_classification
from .archetypes import ArchetypeSelectionResult, run_archetype_selection, ARCHETYPES
from .lrv import LRVResult, get_lrv_for_archetype, DEFAULT_LRV_TARGETS
from .residuals import ResidualsComparisonResult, compare_residuals, assess_archetype_residuals
from .contaminants import run_contaminant_modules
from .scorer import ArchetypeScore, score_archetypes
from .lrv_registry import REGULATORY_FRAMEWORK, get_framework_declaration, REQUIRED_LRV_BY_RISK
from .assumptions import identify_load_bearing_assumptions, LoadBearingAssumption
from .v3_modules import (
    build_ammonia_doctrine, AmmoniaDoctrine,
    run_simplification_challenge, SimplificationChallengeResult,
    run_consistency_check, ConsistencyReport,
    assess_regime_structure, RegimeStructureResult,
    assess_cyanotoxin_dissolved_phase, CyanotoxinDissolvedPhaseResult,
    build_residuals_penalty_profile, ResidualspenaltyProfile,
)


@dataclass
class AquaPointReasoningOutput:
    """Complete structured output from the AquaPoint reasoning engine."""

    # Input echo
    inputs: Optional[SourceWaterInputs] = None

    # Gate 1 + 2
    classification: Optional[ClassificationResult] = None

    # Gate 4
    archetype_selection: Optional[ArchetypeSelectionResult] = None

    # LRV thread
    lrv_by_archetype: dict = field(default_factory=dict)   # key → LRVResult
    required_lrv: dict = field(default_factory=dict)

    # Gate 5
    residuals: Optional[ResidualsComparisonResult] = None

    # Contaminant modules
    contaminant_modules: dict = field(default_factory=dict)  # module_key → ContaminantModuleResult

    # Tier 1–4 scoring
    scores: list = field(default_factory=list)   # list of ArchetypeScore, sorted

    # v3.0 new modules
    regulatory_framework: dict = field(default_factory=dict)
    load_bearing_assumptions: list = field(default_factory=list)
    ammonia_doctrine: Optional[AmmoniaDoctrine] = None
    simplification_challenge: Optional[SimplificationChallengeResult] = None
    consistency_report: Optional[ConsistencyReport] = None
    regime_assessment: Optional[RegimeStructureResult] = None
    cyanotoxin_dissolved_phase: Optional[CyanotoxinDissolvedPhaseResult] = None
    residuals_penalty_profiles: dict = field(default_factory=dict)

    # Final outputs
    preferred_archetype_key: str = ""
    preferred_archetype_label: str = ""
    preferred_archetype_rationale: str = ""
    executive_summary: str = ""
    critical_uncertainties: list = field(default_factory=list)
    next_steps: list = field(default_factory=list)
    key_warnings: list = field(default_factory=list)


def _derive_required_lrv(inputs: SourceWaterInputs) -> dict:
    """Derive required LRV targets from source risk and treatment objective."""
    if inputs.treatment_objective == "recycled":
        base = DEFAULT_LRV_TARGETS["recycled_ipre"]
    elif inputs.catchment_risk == "very_high":
        base = DEFAULT_LRV_TARGETS["potable_high_risk"]
    elif inputs.catchment_risk == "high":
        base = DEFAULT_LRV_TARGETS["potable_moderate_risk"]
    else:
        base = DEFAULT_LRV_TARGETS["potable_low_risk"]

    # Override with explicit inputs only when user has deliberately set them (> 0).
    # Default sentinel is -1 — do not override the framework target in that case.
    result = dict(base)
    if inputs.pathogen_lrv_required_protozoa > 0:
        result["protozoa"] = inputs.pathogen_lrv_required_protozoa
    if inputs.pathogen_lrv_required_bacteria > 0:
        result["bacteria"] = inputs.pathogen_lrv_required_bacteria
    if inputs.pathogen_lrv_required_virus > 0:
        result["virus"] = inputs.pathogen_lrv_required_virus

    return result


def _build_executive_summary(
    classification: ClassificationResult,
    archetype_selection: ArchetypeSelectionResult,
    scores: list,
    inputs: SourceWaterInputs,
) -> str:
    """Construct a concise executive summary paragraph."""
    source_desc = classification.source_description
    primary = classification.primary_constraint_description
    n_viable = len(archetype_selection.viable_archetypes)
    n_excl = len(archetype_selection.excluded_archetypes)

    preferred_key = archetype_selection.primary_recommendation
    preferred_label = ARCHETYPES.get(preferred_key, {}).get("label", preferred_key)

    top_score = next((s for s in scores if s.archetype_key == preferred_key), None)
    score_str = f" (overall score {top_score.overall_score:.1f}/10)" if top_score else ""

    df_note = ""
    if classification.direct_filtration_eligible:
        df_note = " Direct filtration is eligible and is the preferred option given source water stability."
    elif classification.direct_filtration_exclusion_reasons:
        df_note = f" Direct filtration is excluded ({len(classification.direct_filtration_exclusion_reasons)} disqualifying conditions)."

    contaminant_note = ""
    if classification.contaminant_modules_required:
        modules = ", ".join(m.replace("_", " ") for m in classification.contaminant_modules_required)
        contaminant_note = f" Contaminant-specific modules activated: {modules}."

    warnings_count = sum(1 for s in scores if not s.tier1_pass)
    warning_note = ""
    if warnings_count > 0:
        warning_note = f" {warnings_count} archetype(s) failed Tier 1 compliance screening and are not recommended."

    return (
        f"Source classified as: {source_desc}. "
        f"Primary treatment challenge: {primary}. "
        f"{n_viable} of {n_viable + n_excl} treatment archetypes are viable for this source water."
        f"{df_note}{contaminant_note}{warning_note} "
        f"Preferred treatment philosophy: {preferred_label}{score_str}. "
        f"{archetype_selection.recommendation_rationale}"
    )


def _build_critical_uncertainties(
    classification: ClassificationResult,
    inputs: SourceWaterInputs,
    contaminant_modules: dict,
) -> list:
    """Compile critical uncertainties from all modules."""
    uncertainties = []

    if inputs.turbidity_event_max_ntu is None:
        uncertainties.append(
            "No extreme turbidity event data provided. Turbidity at 99th percentile and peak event "
            "conditions are critical for front-end design. Obtain historical or modelled extreme data."
        )

    if inputs.uv254_median_cm is None and inputs.toc_median_mg_l > 3:
        uncertainties.append(
            "UV254 not provided. UV254 (specific UV absorbance) is the best indicator of NOM character "
            "and DBP precursor load — more informative than TOC alone. Measure at source."
        )

    if inputs.algae_risk != "low" and not inputs.cyanobacteria_confirmed:
        uncertainties.append(
            "Algae risk elevated but cyanobacteria not confirmed. "
            "Species identification is essential — cyanobacterial presence fundamentally changes treatment sequencing."
        )

    if inputs.arsenic_ug_l > 0 and inputs.source_type == "groundwater":
        uncertainties.append(
            "Arsenic speciation (As(III) vs As(V)) not confirmed. "
            "Speciation governs whether pre-oxidation is required and which removal pathway will be effective."
        )

    if inputs.pfas_detected and inputs.pfas_concentration_ng_l == 0:
        uncertainties.append(
            "PFAS detected but not quantified. Full compound profile analysis (not just screening) "
            "is required to select and size treatment — short-chain vs long-chain PFAS behave very differently."
        )

    if inputs.alkalinity_median_mg_l < 60:
        uncertainties.append(
            f"Low alkalinity ({inputs.alkalinity_median_mg_l} mg/L): coagulation pH stability is sensitive. "
            "Full coagulation jar testing at range of source water conditions is required before finalising "
            "coagulant type, dose, and pH correction strategy."
        )

    if classification.variability_class in ["high", "extreme"] and inputs.turbidity_p99_ntu == inputs.turbidity_median_ntu:
        uncertainties.append(
            "High variability declared but percentile data is uniform — percentile data may be incomplete. "
            "Obtain at least 2 years of daily turbidity data before finalising front-end design."
        )

    # From contaminant modules
    for module_key, module_result in contaminant_modules.items():
        for step in module_result.next_steps[:2]:  # Top 2 per module
            uncertainties.append(f"[{module_key.replace('_', ' ').title()}] {step}")

    return uncertainties


def _build_key_warnings(
    classification: ClassificationResult,
    archetype_selection: ArchetypeSelectionResult,
    residuals: ResidualsComparisonResult,
    scores: list,
    inputs: SourceWaterInputs,
) -> list:
    """Compile critical safety and engineering warnings."""
    warnings = []

    # Cyanobacteria + ozone sequencing
    if inputs.cyanobacteria_confirmed:
        warnings.append(
            "⚠ CYANOBACTERIA SEQUENCING: Do not apply oxidants before intact cell removal. "
            "Pre-oxidation before DAF/clarification + filtration risks releasing intracellular toxins."
        )

    # Ozone + bromide — calibrated to whether bromide has been measured
    if archetype_selection.ozone_bromide_warning:
        if inputs.bromide_ug_l < 0:
            warnings.append(
                "⚠ OZONE + BROMIDE: Bromide has not been measured for this source. "
                "Bromide data is required before finalising ozone design — measure across seasons. "
                "If bromide exceeds 50 μg/L, bromate suppression is required."
            )
        elif inputs.bromide_ug_l > 100:
            warnings.append(
                f"⚠ HIGH BROMIDE ({inputs.bromide_ug_l:.0f} μg/L): bromate formation at practical "
                f"ozone doses is likely to exceed the 10 μg/L ADWG limit. "
                "Bromate suppression (pH depression, H₂O₂, or ammonia) is mandatory. "
                "Assess whether ozone remains viable at this bromide concentration."
            )
        elif inputs.bromide_ug_l > 50:
            warnings.append(
                f"⚠ ELEVATED BROMIDE ({inputs.bromide_ug_l:.0f} μg/L): bromate formation risk is "
                "significant at typical ozone doses. Bromate suppression strategy required. "
                "Verify compliance in treatability testing before design."
            )
        else:
            warnings.append(
                f"Bromide measured at {inputs.bromide_ug_l:.0f} μg/L — below 50 μg/L threshold. "
                "Bromate formation at practical ozone doses is unlikely to exceed ADWG 10 μg/L limit. "
                "Confirm in pilot or bench-scale testing."
            )

    # Problem transfer
    for flag in residuals.problem_transfer_warnings[:3]:
        if flag not in warnings:
            warnings.append(flag)

    # Tier 1 failures
    for s in scores:
        if not s.tier1_pass:
            for issue in s.tier1_issues[:2]:
                warnings.append(f"⚠ [{s.archetype_label}] Tier 1 issue: {issue}")

    # Direct filtration risk if considered
    if classification.direct_filtration_eligible and inputs.variability_class != "low":
        warnings.append(
            "⚡ Direct filtration is eligible based on current data, but variability class is not 'low'. "
            "Ensure 99th percentile turbidity data is robust before committing to direct filtration."
        )

    return warnings


# ─── Master Run Function ──────────────────────────────────────────────────────

def run_reasoning_engine(inputs: SourceWaterInputs) -> AquaPointReasoningOutput:
    """
    Run the full AquaPoint reasoning engine.
    Returns a complete AquaPointReasoningOutput.
    """
    output = AquaPointReasoningOutput(inputs=inputs)

    # ── Gates 1 + 2: Classification ──────────────────────────────────────────
    output.classification = run_classification(inputs)

    # ── Gate 3: Variability already embedded in classification ────────────────

    # ── Gate 4: Archetype selection ───────────────────────────────────────────
    output.archetype_selection = run_archetype_selection(inputs, output.classification)

    # ── LRV Thread ────────────────────────────────────────────────────────────
    output.required_lrv = _derive_required_lrv(inputs)
    viable_keys = [a.key for a in output.archetype_selection.viable_archetypes]
    for key in viable_keys:
        output.lrv_by_archetype[key] = get_lrv_for_archetype(key, output.required_lrv)

    # ── Gate 5: Residuals ─────────────────────────────────────────────────────
    contaminant_modules_list = output.classification.contaminant_modules_required
    output.residuals = compare_residuals(viable_keys, inputs, contaminant_modules_list)

    # ── Contaminant Modules ───────────────────────────────────────────────────
    output.contaminant_modules = run_contaminant_modules(inputs, contaminant_modules_list)

    # ── Tier 1–4 Scoring ─────────────────────────────────────────────────────
    residuals_by_archetype = {
        k: assess_archetype_residuals(k, inputs, contaminant_modules_list)
        for k in viable_keys
    }
    output.scores = score_archetypes(
        output.archetype_selection.viable_archetypes,
        inputs,
        residuals_by_archetype,
        output.required_lrv,
    )

    # ── Preferred Pathway ─────────────────────────────────────────────────────
    # Use archetype selection logic (engineering-driven) as primary recommendation,
    # but verify it passes Tier 1. If not, fall back to top-scoring Tier 1 pass.
    logic_key = output.archetype_selection.primary_recommendation
    logic_score_obj = next((s for s in output.scores if s.archetype_key == logic_key), None)

    if logic_score_obj and logic_score_obj.tier1_pass:
        output.preferred_archetype_key = logic_key
        output.preferred_archetype_label = ARCHETYPES.get(logic_key, {}).get("label", logic_key)
        output.preferred_archetype_rationale = output.archetype_selection.recommendation_rationale
    else:
        # logic_key failed Tier 1 — select the best constraint-appropriate fallback.
        # Priority: (1) engineering-ordered fallback based on logic_key type,
        # (2) top-scoring Tier 1 pass.
        # This prevents abstract scoring from selecting an inappropriate archetype
        # (e.g. DAF for clean groundwater when direct filtration fails Tier 1 on virus LRV).
        FALLBACK_ORDER = {
            "A": ["B", "C", "D"],      # DF fails → conventional → intensified → DAF
            "B": ["D", "C", "E"],
            "D": ["B", "C", "E"],
            "F": ["H", "B"],            # softening fails → membrane or conventional
            "G": ["E", "B"],            # ozone+BAC fails → enhanced coag → conventional
            "H": ["G", "B"],
            "I": ["H", "B"],
        }
        fallback_keys = FALLBACK_ORDER.get(logic_key, [])
        passing_keys = {s.archetype_key for s in output.scores if s.tier1_pass}

        # Try ordered fallback first
        best_key = next((k for k in fallback_keys if k in passing_keys), None)
        # Then highest scorer among all passing
        if not best_key:
            best_score = next((s for s in output.scores if s.tier1_pass), None)
            best_key = best_score.archetype_key if best_score else logic_key

        best_passing = next((s for s in output.scores if s.archetype_key == best_key), None)
        if best_passing:
            output.preferred_archetype_key = best_passing.archetype_key
            output.preferred_archetype_label = best_passing.archetype_label
            aa_match = next(
                (a for a in output.archetype_selection.viable_archetypes
                 if a.key == best_passing.archetype_key), None
            )
            if aa_match and aa_match.inclusion_rationale:
                output.preferred_archetype_rationale = aa_match.inclusion_rationale[0]
            else:
                output.preferred_archetype_rationale = (
                    f"{best_passing.archetype_label} is the recommended fallback archetype "                    f"(engineering logic archetype {logic_key} did not pass Tier 1 screening). "
                )
        else:
            output.preferred_archetype_key = logic_key
            output.preferred_archetype_label = ARCHETYPES.get(logic_key, {}).get("label", logic_key)
            output.preferred_archetype_rationale = output.archetype_selection.recommendation_rationale

    # ── Executive Summary ─────────────────────────────────────────────────────
    output.executive_summary = _build_executive_summary(
        output.classification, output.archetype_selection, output.scores, inputs
    )

    # ── Critical Uncertainties and Warnings ───────────────────────────────────
    output.critical_uncertainties = _build_critical_uncertainties(
        output.classification, inputs, output.contaminant_modules
    )
    output.key_warnings = _build_key_warnings(
        output.classification, output.archetype_selection,
        output.residuals, output.scores, inputs
    )

    # ══ v3.0 MODULES ══════════════════════════════════════════════════════════

    # Regulatory framework lock
    output.regulatory_framework = REGULATORY_FRAMEWORK

    # Ammonia-disinfection doctrine
    output.ammonia_doctrine = build_ammonia_doctrine(inputs)

    # Regime structure assessment
    output.regime_assessment = assess_regime_structure(inputs, output.classification)

    # Cyanotoxin dissolved-phase
    output.cyanotoxin_dissolved_phase = assess_cyanotoxin_dissolved_phase(
        inputs, output.preferred_archetype_key
    )

    # Residuals penalty profiles
    contaminant_list = output.classification.contaminant_modules_required
    for key in viable_keys:
        output.residuals_penalty_profiles[key] = build_residuals_penalty_profile(
            key, inputs, contaminant_list
        )

    # Load-bearing assumptions
    output.load_bearing_assumptions = identify_load_bearing_assumptions(
        inputs, output.classification,
        output.preferred_archetype_key,
        output.contaminant_modules,
    )

    # Simplification challenge
    output.simplification_challenge = run_simplification_challenge(
        inputs, output.preferred_archetype_key,
        output.preferred_archetype_label, output.scores
    )

    # Consistency check (final gate)
    output.consistency_report = run_consistency_check(
        output.preferred_archetype_key,
        output.required_lrv,
        output.lrv_by_archetype,
        inputs,
        output.load_bearing_assumptions,
        output.ammonia_doctrine,
    )

    # ── Next Steps ────────────────────────────────────────────────────────────
    output.next_steps = [
        "Validate source water characterisation data (confirm percentile turbidity, NOM, and pathogen risk data are complete)",
        "Undertake jar testing / coagulation optimisation for NOM and turbidity removal targets",
        "Confirm LRV barrier credits through regulatory framework review (ADWG, jurisdictional guidance)",
        "Develop residuals handling concept and confirm disposal/management pathway",
        "If advanced treatment indicated: commission treatability study or pilot test",
        "Engage with the environmental regulator early where concentrate or classified waste streams are present",
    ]

    # Prepend contaminant-specific next steps
    for mod_result in output.contaminant_modules.values():
        for step in mod_result.next_steps[:1]:
            if step not in output.next_steps:
                output.next_steps.insert(0, step)

    return output
