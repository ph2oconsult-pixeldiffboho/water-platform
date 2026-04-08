"""
AquaPoint v3.0 — New Decision Modules

Implements:
- AmmoniaDoctrine: Formal ammonia-disinfection operating doctrine
- SimplificationChallenge: Mandatory pre-output challenge step
- ConsistencyChecker: Report cross-section validation
- RegimeStructureAssessment: Dual-mode vs single-mode decision
- CyanotoxinDissolvedPhase: Extended dissolved toxin logic
"""
from dataclasses import dataclass, field
from typing import List, Optional
from .classifier import SourceWaterInputs


# ══ MODULE 1: AMMONIA-DISINFECTION OPERATING DOCTRINE ════════════════════════

@dataclass
class AmmoniaDoctrine:
    """Formal ammonia-disinfection operating doctrine."""
    ammonia_significant: bool = False

    raw_ammonia_median_mg_l: float = 0.0
    raw_ammonia_p95_mg_l: float = 0.0

    breakpoint_cl2_median_mg_l: float = 0.0
    breakpoint_cl2_p95_mg_l: float = 0.0

    mn_pre_oxidation_conflict: bool = False
    mn_pre_oxidation_recommendation: str = ""

    uv_role: str = ""
    chlorine_role: str = ""
    chloramine_role: str = ""

    ammonia_changes: List[str] = field(default_factory=list)
    load_bearing_instruments: List[str] = field(default_factory=list)
    nitrification_risk: str = ""

    chloramine_source: str = ""
    cl_n_ratio_target: float = 4.5
    supplemental_ammonium_sulphate_required: bool = True

    doctrine_text: str = ""


def build_ammonia_doctrine(inputs: SourceWaterInputs) -> AmmoniaDoctrine:
    """Build the ammonia-disinfection operating doctrine for this source."""
    d = AmmoniaDoctrine()

    ammonia = getattr(inputs, 'ammonia_mg_l_nh3n', 0.0)
    d.raw_ammonia_median_mg_l = ammonia
    d.raw_ammonia_p95_mg_l = ammonia * 2.5  # estimate if not provided
    d.ammonia_significant = ammonia > 0.1

    if not d.ammonia_significant:
        d.doctrine_text = (
            f"Source ammonia is negligible ({ammonia:.2f} mg/L NH3-N median). "
            "Breakpoint chlorination is not required. Free Cl2 Ct contact is straightforward. "
            "Standard chloramination for distribution using ammonium sulphate."
        )
        d.uv_role = "Primary protozoan inactivation (4 log Crypto at 22 mJ/cm2)."
        d.chlorine_role = "Primary virus and bacterial inactivation via free Cl2 Ct. No breakpoint required."
        d.chloramine_role = "Distribution residual maintenance. DBP suppression."
        return d

    # Significant ammonia — full doctrine
    d.breakpoint_cl2_median_mg_l = round(ammonia * 7.6, 1)
    d.breakpoint_cl2_p95_mg_l = round(d.raw_ammonia_p95_mg_l * 7.6, 1)

    # Check Mn pre-oxidation conflict
    if inputs.manganese_median_mg_l > 0.05:
        d.mn_pre_oxidation_conflict = True
        d.mn_pre_oxidation_recommendation = (
            f"Chlorine-based Mn2+ pre-oxidation is UNRELIABLE at {ammonia:.2f} mg/L NH3-N. "
            "Chlorine preferentially forms chloramines rather than oxidising Mn2+. "
            "KMnO4 pre-oxidation is required — it is not inhibited by ammonia."
        )

    d.uv_role = (
        "Primary protozoan inactivation — 4 log Cryptosporidium at 22 mJ/cm2. "
        "UV performance is INDEPENDENT of ammonia concentration and pH. "
        "This is UV's critical advantage for ammonia-bearing sources — "
        "it decouples protozoan protection from the ammonia-disinfection interaction."
    )

    d.chlorine_role = (
        f"Primary virus and bacterial inactivation via free Cl2 Ct. "
        f"Breakpoint chlorination required first: "
        f"~{d.breakpoint_cl2_median_mg_l:.1f} mg/L Cl2 at median NH3-N, "
        f"~{d.breakpoint_cl2_p95_mg_l:.1f} mg/L Cl2 at P95 NH3-N (design condition). "
        "Contact basin must be sized for P95 breakpoint dose, not median. "
        "Ct must be verified at maximum pH and minimum temperature."
    )

    d.chloramine_role = (
        "Distribution residual maintenance and DBP suppression ONLY. "
        "NOT primary disinfection. Chloramines provide negligible additional virus/bacteria Ct. "
        "Ammonium sulphate addition downstream of Ct contact targets Cl:N ratio 4–5:1. "
        "Background NH3-N contributes to the chloramine pool — measure post-treatment "
        "NH3-N before calculating supplemental ammonium sulphate dose."
    )

    d.ammonia_changes = [
        f"Chlorine-based Mn2+ oxidation is suppressed — KMnO4 pre-oxidation required." if d.mn_pre_oxidation_conflict else "",
        f"Breakpoint Cl2 dose at P95 is {d.breakpoint_cl2_p95_mg_l:.1f} mg/L — "
        "contact basin and chlorine storage must be sized for P95, not median.",
        "Post-ozone NH3-N is reduced by ozonation — measure before calculating supplemental ammonium sulphate.",
        "THM formation risk elevated during P95 Cl2 dose events — quarterly THM monitoring required.",
        f"Nitrification risk in distribution: {'HIGH' if ammonia > 0.5 else 'MODERATE'} — "
        "warm climate + chloramination + long distribution system.",
    ]
    d.ammonia_changes = [c for c in d.ammonia_changes if c]  # remove empty strings

    d.load_bearing_instruments = [
        "Continuous ammonia analyser at filter outlet (before chlorine dosing) — load-bearing",
        "Automated chlorine dose controller responding to real-time NH3-N measurement",
        "Online Ct verification (flow rate × contact time × Cl2 residual)",
        "Continuous chloramine residual monitors at distribution entry points",
        "Quarterly nitrification monitoring in distribution (nitrite, HPC, temperature)",
    ]

    d.nitrification_risk = "HIGH" if ammonia > 0.5 else "MODERATE"
    d.chloramine_source = "background_nh3_plus_ammonium_sulphate"
    d.cl_n_ratio_target = 4.5

    d.doctrine_text = f"""
AMMONIA–DISINFECTION OPERATING DOCTRINE

Source ammonia: {ammonia:.2f} mg/L median, ~{d.raw_ammonia_p95_mg_l:.2f} mg/L P95 NH3-N

What UV is doing:
{d.uv_role}

What free chlorine is doing:
{d.chlorine_role}

What chloramines are doing:
{d.chloramine_role}

How ammonia changes the design:
""" + "\n".join(f"  {i+1}. {c}" for i, c in enumerate(d.ammonia_changes)) + f"""

Load-bearing instrumentation and control:
""" + "\n".join(f"  - {inst}" for inst in d.load_bearing_instruments)

    return d


# ══ MODULE 2: SIMPLIFICATION CHALLENGE ════════════════════════════════════════

@dataclass
class SimplificationFlag:
    question: str
    finding: str
    recommendation: str
    process_that_could_be_removed: str = ""


@dataclass
class SimplificationChallengeResult:
    flags: List[SimplificationFlag] = field(default_factory=list)
    minimum_viable_train_description: str = ""
    preferred_is_minimum_viable: bool = True
    challenge_passed: bool = True
    summary: str = ""


def run_simplification_challenge(
    inputs: SourceWaterInputs,
    preferred_archetype_key: str,
    preferred_archetype_label: str,
    scores: list,
) -> SimplificationChallengeResult:
    """
    Challenge the preferred recommendation before finalising.
    Asks: is this train more complex than the source justifies?
    """
    result = SimplificationChallengeResult()
    flags = []

    # ── Q1: Is the train more complex than the source justifies? ─────────────
    # Signals of over-engineering:
    over_engineering_signals = []

    # Advanced T&O treatment on low-T&O source
    if (preferred_archetype_key in ["G", "E"] and
            not inputs.mib_geosmin_issue and
            inputs.algae_risk == "low"):
        over_engineering_signals.append(
            "Ozone/BAC selected despite no T&O problem at this source. "
            "MIB/geosmin not detected or minimal — PAC contingency is adequate."
        )

    # Membrane on low-risk source
    if (preferred_archetype_key == "H" and
            inputs.variability_class in ["low", "moderate"] and
            inputs.catchment_risk in ["low", "moderate"]):
        over_engineering_signals.append(
            "MF/UF membrane selected for a low-moderate risk source. "
            "Granular filtration + UV provides adequate LRV at lower cost and complexity."
        )

    if over_engineering_signals:
        flags.append(SimplificationFlag(
            question="Is the preferred train more complex than the source justifies?",
            finding="POSSIBLE OVER-ENGINEERING DETECTED:\n" + "\n".join(over_engineering_signals),
            recommendation="Review whether the governing constraint genuinely requires this technology.",
        ))

    # ── Q2: Can one process be removed? ──────────────────────────────────────
    removable_processes = []

    # GAC/BAC without T&O problem
    if preferred_archetype_key in ["G", "E"] and not inputs.mib_geosmin_issue:
        removable_processes.append("BAC/GAC contactors (no T&O problem; no NOM mineralisation required)")

    # Sedimentation on excellent source
    if (preferred_archetype_key in ["B", "C", "E"] and
            inputs.turbidity_p95_ntu < 10 and
            inputs.turbidity_p99_ntu < 20 and
            inputs.algae_risk == "low"):
        removable_processes.append(
            "Sedimentation stage — consider direct filtration (Archetype A) "
            "if storm event duration analysis confirms events are short-lived"
        )

    if removable_processes:
        flags.append(SimplificationFlag(
            question="Can one process be removed without materially reducing defensibility?",
            finding="Potentially removable process(es) identified.",
            recommendation="Assess each against the LRV build-up table to confirm removal is acceptable.",
            process_that_could_be_removed="; ".join(removable_processes),
        ))

    # ── Q3: Is recommendation drifting toward sophistication? ────────────────
    if preferred_archetype_key in ["G", "H"] and inputs.toc_median_mg_l < 3.0:
        flags.append(SimplificationFlag(
            question="Is the recommendation drifting toward sophistication rather than necessity?",
            finding=(
                f"TOC is {inputs.toc_median_mg_l:.1f} mg/L — low. "
                f"Advanced oxidation / membrane treatment selected. "
                "Verify that the governing constraint genuinely requires this level of treatment."
            ),
            recommendation="Confirm that the primary constraint cannot be addressed by a simpler train.",
        ))

    # ── Minimum viable train ──────────────────────────────────────────────────
    mvt_map = {
        "A": "In-line coagulation + dual-media filtration + UV + Cl2 Ct + Chloramination",
        "B": "Coagulation + sedimentation + filtration + UV + Cl2 Ct + Chloramination",
        "C": "Coagulation + lamella clarification + filtration + UV + Cl2 Ct + Chloramination",
        "D": "Coagulation + DAF + filtration + UV + Cl2 Ct + Chloramination",
        "E": "Coagulation + sedimentation + filtration + ozone + BAC + UV + Cl2 Ct + Chloramination",
        "F": "Coagulation + softening + recarbonation + filtration + UV + Cl2 Ct + Chloramination",
        "G": "Coagulation + sedimentation + filtration + ozone + BAC + UV + Cl2 Ct + Chloramination",
        "H": "Pre-coagulation + MF/UF + UV + Cl2 Ct + Chloramination",
        "I": (
            "Aeration + KMnO4 pre-oxidation + ferric co-precipitation + "
            "greensand filtration + GFH polishing + UV (40 mJ/cm2) + "
            "breakpoint Cl2 Ct + CCPP correction + chloramination"
        ),
    }

    result.minimum_viable_train_description = mvt_map.get(
        preferred_archetype_key,
        f"Minimum viable train for {preferred_archetype_label}"
    )
    result.flags = flags
    result.preferred_is_minimum_viable = len(flags) == 0
    result.challenge_passed = not any("OVER-ENGINEERING" in f.finding for f in flags)

    # Build summary
    if not flags:
        result.summary = (
            f"Simplification challenge PASSED. Preferred train ({preferred_archetype_label}) "
            "is the minimum viable train for this source. "
            "No processes can be removed without reducing defensibility."
        )
    else:
        issues = len(flags)
        result.summary = (
            f"Simplification challenge raised {issues} flag(s). "
            "Review flagged items before finalising the preferred pathway. "
            "Consider whether the source genuinely requires each process step."
        )

    return result


# ══ MODULE 3: CONSISTENCY CHECKER ═════════════════════════════════════════════

@dataclass
class ConsistencyIssue:
    check_name: str
    level: str  # "error" | "warning"
    description: str
    sections_affected: List[str] = field(default_factory=list)


@dataclass
class ConsistencyReport:
    errors: List[ConsistencyIssue] = field(default_factory=list)
    warnings: List[ConsistencyIssue] = field(default_factory=list)
    passed: bool = True
    summary: str = ""


def run_consistency_check(
    preferred_archetype_key: str,
    required_lrv: dict,
    lrv_by_archetype: dict,
    inputs: SourceWaterInputs,
    assumptions: list,
    doctrine: AmmoniaDoctrine,
) -> ConsistencyReport:
    """
    Run cross-section consistency validation.
    Returns ConsistencyReport — report should not be generated if errors > 0.
    """
    report = ConsistencyReport()

    # ── Check 1: LRV targets are consistent ──────────────────────────────────
    from .lrv_registry import REGULATORY_FRAMEWORK, LRV_CREDIT_REGISTRY
    cap = REGULATORY_FRAMEWORK["single_barrier_max_log"]

    # Verify no credits exceed cap anywhere
    violations = []
    for barrier, pathogens in LRV_CREDIT_REGISTRY.items():
        for pathogen, vals in pathogens.items():
            if vals[1] > cap:
                violations.append(f"{barrier}/{pathogen}: {vals[1]:.1f} > {cap:.1f} log cap")

    if violations:
        report.errors.append(ConsistencyIssue(
            check_name="single_barrier_cap",
            level="error",
            description=f"LRV credits exceed 4.0 log single-barrier cap: {'; '.join(violations)}",
            sections_affected=["lrv_registry", "barrier_table", "lrv_build_up"],
        ))

    # ── Check 2: Preferred archetype has LRV calculated ──────────────────────
    if preferred_archetype_key not in lrv_by_archetype:
        report.errors.append(ConsistencyIssue(
            check_name="preferred_lrv_missing",
            level="error",
            description=(
                f"Preferred archetype {preferred_archetype_key} has no LRV result calculated. "
                "LRV build-up cannot be shown for the preferred option."
            ),
            sections_affected=["barrier_table", "preferred_pathway"],
        ))

    # ── Check 3: Ammonia doctrine present if ammonia significant ─────────────
    ammonia = getattr(inputs, 'ammonia_mg_l_nh3n', None) or 0.0
    if ammonia > 0.1 and not doctrine.ammonia_significant:
        report.warnings.append(ConsistencyIssue(
            check_name="ammonia_doctrine_inactive",
            level="warning",
            description=(
                f"Source ammonia is {ammonia:.2f} mg/L (>0.1 mg/L threshold) "
                "but ammonia doctrine module was not activated. "
                "Review disinfection logic for ammonia-bearing source."
            ),
            sections_affected=["ammonia_doctrine", "disinfection_strategy"],
        ))

    # ── Check 4: CCPP mentioned if low alkalinity ─────────────────────────────
    if inputs.alkalinity_median_mg_l < 80:
        # Check that at least one assumption flags CCPP
        ccpp_flagged = any("CCPP" in a.assumption or "alkalinity" in a.triggered_by.lower()
                          for a in assumptions)
        if not ccpp_flagged:
            report.warnings.append(ConsistencyIssue(
                check_name="ccpp_not_flagged",
                level="warning",
                description=(
                    f"Source alkalinity is {inputs.alkalinity_median_mg_l:.0f} mg/L — below 80 mg/L threshold. "
                    "CCPP correction requirement should be flagged in load-bearing assumptions "
                    "and included in the preferred train description."
                ),
                sections_affected=["load_bearing_assumptions", "preferred_pathway", "chemical_table"],
            ))

    # ── Check 5: Virus LRV gap acknowledged ──────────────────────────────────
    if preferred_archetype_key in lrv_by_archetype:
        lrv = lrv_by_archetype[preferred_archetype_key]
        virus_gap = lrv.gap_low.get("virus", 0)
        if virus_gap > 0:
            # Check assumptions include virus Ct note
            ct_flagged = any("virus" in a.triggered_by.lower() or "Ct" in a.assumption
                            for a in assumptions)
            if not ct_flagged:
                report.warnings.append(ConsistencyIssue(
                    check_name="virus_lrv_gap_not_addressed",
                    level="warning",
                    description=(
                        f"Virus LRV gap of {virus_gap:.1f} log at low end not explicitly addressed "
                        "in load-bearing assumptions. Chlorine Ct is the load-bearing virus barrier — "
                        "this should be flagged as a critical assumption."
                    ),
                    sections_affected=["load_bearing_assumptions", "barrier_table"],
                ))

    # ── Check 6: Cyanobacteria sequencing if cyanobacteria confirmed ──────────
    if inputs.cyanobacteria_confirmed and preferred_archetype_key in ["G"]:
        cyano_flagged = any("cyano" in a.triggered_by.lower() for a in assumptions)
        if not cyano_flagged:
            report.errors.append(ConsistencyIssue(
                check_name="cyanobacteria_sequencing_not_flagged",
                level="error",
                description=(
                    "Cyanobacteria confirmed and ozone-containing archetype selected, "
                    "but cyanobacteria dissolved-phase logic not activated. "
                    "Cell removal sequencing and dissolved toxin control must be addressed."
                ),
                sections_affected=["cyanotoxin_module", "process_trains", "preferred_pathway"],
            ))

    # ── Build summary ─────────────────────────────────────────────────────────
    n_errors = len(report.errors)
    n_warnings = len(report.warnings)
    report.passed = n_errors == 0

    if report.passed and n_warnings == 0:
        report.summary = "Consistency check PASSED — no errors or warnings."
    elif report.passed:
        report.summary = f"Consistency check PASSED with {n_warnings} warning(s). Review before finalising."
    else:
        report.summary = (
            f"Consistency check FAILED — {n_errors} error(s), {n_warnings} warning(s). "
            "Resolve errors before generating final report."
        )

    return report


# ══ MODULE 4: REGIME STRUCTURE ASSESSMENT ═════════════════════════════════════

@dataclass
class RegimeStructureResult:
    dual_regime_detected: bool = False
    regime_a_description: str = ""
    regime_b_description: str = ""
    cooccurrence_at_peak: bool = False
    cooccurrence_evidence: str = ""
    shared_backbone_practical: bool = True
    shared_backbone_description: str = ""
    single_mode_compromise_acceptable: bool = True
    single_mode_compromise_description: str = ""
    dual_mode_justified: bool = False
    recommendation: str = ""
    regime_capital_premium: str = ""


def assess_regime_structure(
    inputs: SourceWaterInputs,
    classification,
) -> RegimeStructureResult:
    """
    Assess whether a dual-mode plant architecture is warranted.
    Only activates when two distinct governing constraints are identified.
    """
    result = RegimeStructureResult()

    # ── Detect dual regime ────────────────────────────────────────────────────
    # Regime indicators: high turbidity events + high hardness/mineral load
    has_turbidity_regime = (
        inputs.turbidity_p99_ntu > 20 or
        (getattr(inputs, 'turbidity_event_max_ntu', None) or 0) > 100
    )
    has_hardness_regime = inputs.hardness_median_mg_l > 250
    has_tao_regime = inputs.mib_geosmin_issue or inputs.algae_risk in ["high", "confirmed_bloom"]
    has_softening_conflict = has_turbidity_regime and has_hardness_regime

    if not (has_softening_conflict or (has_turbidity_regime and has_tao_regime)):
        result.dual_regime_detected = False
        result.recommendation = "Single operating regime — no dual-mode assessment required."
        return result

    result.dual_regime_detected = True

    if has_softening_conflict:
        result.regime_a_description = (
            f"Wet season / turbidity regime: "
            f"extreme turbidity events (P99 {inputs.turbidity_p99_ntu:.0f} NTU), "
            f"algae risk, solids removal as primary constraint."
        )
        result.regime_b_description = (
            f"Dry season / mineral regime: "
            f"hardness {inputs.hardness_median_mg_l:.0f} mg/L, "
            f"alkalinity {inputs.alkalinity_median_mg_l:.0f} mg/L — softening consideration."
        )

        # Co-occurrence test: high turbidity events dilute dissolved minerals
        result.cooccurrence_at_peak = False
        result.cooccurrence_evidence = (
            "Wet-season turbidity events dilute dissolved mineral content — "
            "peak turbidity and peak hardness are anti-correlated in this source type. "
            "Designing for simultaneous peak of both regimes is not warranted."
        )

        result.shared_backbone_practical = True
        result.shared_backbone_description = (
            "High-rate clarification (ballasted or DAF) operates across both regimes "
            "as the fixed front-end backbone. Filtration and UV are fixed. "
            "Advanced treatment (T&O or softening) is the switchable module."
        )

        result.single_mode_compromise_acceptable = False
        result.single_mode_compromise_description = (
            "A single ozone/BAC train (T&O mode) fails hardness aesthetic compliance "
            "during dry season low-flow periods. "
            "A single softening train fails T&O compliance during MIB/algae events. "
            "Neither single-mode compromise achieves compliance across all regimes."
        )

        result.dual_mode_justified = True
        result.recommendation = (
            "Dual-mode plant justified. "
            "Backbone: high-rate clarification + filtration + UV + chloramination (fixed). "
            "Module A: ozone/BAC (T&O / wet season — activated by monitoring trigger). "
            "Module B: lime/soda ash softening (hardness / dry season — activated by trigger). "
            "Mode switching triggers: defined monitoring thresholds for MIB and hardness."
        )
        result.regime_capital_premium = (
            "Capital premium for dual-mode: approximately 20–30% over single-mode — "
            "justified by compliance requirement across both regimes."
        )

    elif has_turbidity_regime and has_tao_regime:
        result.regime_a_description = "Event regime: extreme turbidity + algae/bloom conditions."
        result.regime_b_description = "Stable regime: low turbidity, T&O as primary concern."
        result.cooccurrence_at_peak = True  # these can co-occur
        result.cooccurrence_evidence = (
            "Turbidity events and algal blooms CAN co-occur in warm-climate sources. "
            "Treatment must handle both simultaneously."
        )
        result.shared_backbone_practical = True
        result.single_mode_compromise_acceptable = True
        result.dual_mode_justified = False
        result.recommendation = (
            "Single-mode train handles both regimes — "
            "ballasted clarification for turbidity events + ozone/BAC for T&O. "
            "Cell removal sequencing rule must be built structurally into the train."
        )

    return result


# ══ MODULE 5: CYANOTOXIN DISSOLVED-PHASE LOGIC ════════════════════════════════

@dataclass
class CyanotoxinDissolvedPhaseResult:
    activated: bool = False
    intracellular_dominant: bool = True
    bloom_collapse_risk: str = ""
    ozone_bromide_conflict: bool = False
    ozone_constrained_control_mechanism: str = ""
    oxidation_suspension_contingency: str = ""
    dissolved_toxin_barriers: List[str] = field(default_factory=list)
    monitoring_requirements: List[str] = field(default_factory=list)
    source_suspension_trigger: str = ""
    module_text: str = ""


def assess_cyanotoxin_dissolved_phase(
    inputs: SourceWaterInputs,
    preferred_archetype_key: str,
) -> CyanotoxinDissolvedPhaseResult:
    """
    Extend cyanotoxin logic beyond cell-removal sequencing to dissolved toxin control.
    Activates when cyanobacteria are confirmed or toxins detected.
    """
    result = CyanotoxinDissolvedPhaseResult()

    if not (inputs.cyanobacteria_confirmed or inputs.cyanotoxin_detected or
            inputs.algae_risk in ["high", "confirmed_bloom"]):
        result.activated = False
        return result

    result.activated = True
    result.intracellular_dominant = not inputs.cyanotoxin_detected

    # Bloom collapse risk
    result.bloom_collapse_risk = (
        "HIGH — cyanobacterial bloom collapse releases intracellular toxins rapidly. "
        "Dissolved toxin concentration can spike 10–100× compared to intact-cell events. "
        "Bloom collapse is not predictable — monitoring frequency must increase during declining blooms."
    )

    # Ozone/bromide conflict
    bromide = getattr(inputs, 'bromide_mg_l', 0.0)
    ozone_in_train = preferred_archetype_key in ["G", "E"]
    if ozone_in_train and bromide > 0.1:
        result.ozone_bromide_conflict = True
        result.ozone_constrained_control_mechanism = (
            f"At Br- {bromide:.2f} mg/L, ozone dose is constrained by bromate suppression requirements. "
            f"Reduced ozone dose ({1.0 if bromide > 0.3 else 1.5}–{1.5 if bromide > 0.3 else 2.0} mg/L) "
            "may result in incomplete dissolved toxin destruction. "
            "Microcystin-LR requires ozone Ct of approximately 0.25 mg·min/L for 1 log inactivation. "
            "PAC becomes the primary dissolved toxin control tool if ozone is constrained."
        )

    # Dissolved toxin barriers
    result.dissolved_toxin_barriers = []

    if ozone_in_train:
        result.dissolved_toxin_barriers.append(
            "Ozone (post cell removal): microcystin-LR is effectively destroyed by ozone — "
            "0.25 mg·min/L Ct achieves >1 log inactivation. "
            "Ozone must be operated POST-DAF/clarification (cell removal) — NEVER pre-ozone during blooms."
        )

    result.dissolved_toxin_barriers.append(
        "PAC: effective for dissolved toxins including microcystin and cylindrospermopsin. "
        "Dose 20–30 mg/L for moderate dissolved toxin concentrations. "
        "NOM competition reduces PAC efficiency — at TOC >8 mg/L, higher doses required."
    )

    if preferred_archetype_key in ["G", "E"]:
        result.dissolved_toxin_barriers.append(
            "BAC/GAC: provides adsorptive polishing of dissolved toxin breakdown products "
            "from upstream ozonation. Not a primary dissolved toxin barrier without ozone upstream."
        )

    result.dissolved_toxin_barriers.append(
        "Chlorination: free chlorine at pH <8.0 destroys microcystin effectively. "
        "Ct requirement: approximately 20 mg·min/L for >1 log microcystin-LR inactivation at pH 7.0. "
        "Less effective for cylindrospermopsin and saxitoxin — species confirmation required."
    )

    # Oxidation suspension contingency
    result.oxidation_suspension_contingency = (
        "If ozone must be suspended (e.g., bromide spike, maintenance): "
        "(1) Increase PAC dose to 30–50 mg/L ahead of filters. "
        "(2) Increase chlorine Ct in contact basin. "
        "(3) Activate dissolved toxin monitoring at filter outlet. "
        "(4) If treated water dissolved toxin >0.5 μg/L microcystin-LR, "
        "notify health authority and consider supply restriction."
    )

    # Monitoring requirements
    result.monitoring_requirements = [
        "Total and dissolved cyanotoxin analysis at source (weekly during bloom; daily during decline)",
        "Cyanobacterial species identification — toxin class depends on species",
        "Dissolved toxin monitoring at filter outlet during bloom periods (not just source)",
        "Cell count monitoring at off-take — trigger-based response protocol",
        "Online algae sensor at intake if bloom frequency is high",
    ]

    result.source_suspension_trigger = (
        "Source suspension trigger: dissolved microcystin-LR in treated water >1 μg/L "
        "at distribution entry point. Notify health authority. "
        "Review treatment performance and consider alternative source or supply restriction."
    )

    result.module_text = (
        "CYANOTOXIN DISSOLVED-PHASE ANALYSIS\n\n"
        f"Intracellular dominant assumption: {'YES — cell removal is primary control' if result.intracellular_dominant else 'NO — dissolved toxins are present; both pathways must be addressed'}\n\n"
        f"Bloom collapse risk: {result.bloom_collapse_risk}\n\n"
        "Dissolved toxin control mechanisms:\n" +
        "\n".join(f"  - {b}" for b in result.dissolved_toxin_barriers) +
        f"\n\nContingency if oxidation suspended:\n  {result.oxidation_suspension_contingency}\n\n"
        f"Source suspension trigger: {result.source_suspension_trigger}"
    )

    return result


# ══ RESIDUALS PENALTY ENGINE ═════════════════════════════════════════════════

@dataclass
class ResidualStreamPenalty:
    stream_name: str
    classified_solid: int = 0       # 0–3
    classified_liquid: int = 0      # 0–3
    dewaterability: int = 0         # 0–3
    disposal_uncertainty: int = 0   # 0–3
    offsite_dependency: int = 0     # 0–3
    reactivation_dependency: int = 0 # 0–3
    problem_transfer: int = 0       # 0–3
    total: int = 0
    burden_level: str = ""          # "low" | "moderate" | "high" | "very_high"


@dataclass
class ResidualspenaltyProfile:
    archetype_key: str = ""
    streams: List[ResidualStreamPenalty] = field(default_factory=list)
    total_penalty: int = 0
    tier3_score_impact: float = 0.0
    penalty_description: str = ""


def _calc_stream_penalty(s: ResidualStreamPenalty) -> ResidualStreamPenalty:
    s.total = (s.classified_solid + s.classified_liquid + s.dewaterability +
               s.disposal_uncertainty + s.offsite_dependency +
               s.reactivation_dependency + s.problem_transfer)
    if s.total <= 5:   s.burden_level = "low"
    elif s.total <= 10: s.burden_level = "moderate"
    elif s.total <= 15: s.burden_level = "high"
    else:              s.burden_level = "very_high"
    return s


def build_residuals_penalty_profile(
    archetype_key: str,
    inputs: SourceWaterInputs,
    contaminant_modules: list,
) -> ResidualspenaltyProfile:
    """Build structured residuals penalty profile for scoring."""
    profile = ResidualspenaltyProfile(archetype_key=archetype_key)
    streams = []

    # ── Standard filter backwash ──────────────────────────────────────────────
    backwash = ResidualStreamPenalty(stream_name="Filter backwash")
    backwash.classified_solid = 0
    backwash.classified_liquid = 0
    backwash.dewaterability = 1
    backwash.disposal_uncertainty = 0
    backwash.offsite_dependency = 0
    backwash.reactivation_dependency = 0
    backwash.problem_transfer = 0

    # Escalate if arsenic present
    if inputs.arsenic_ug_l > 5:
        backwash.classified_solid = 1
        backwash.problem_transfer = 2
    if inputs.pfas_detected:
        backwash.classified_solid = 2
        backwash.problem_transfer = 3

    streams.append(_calc_stream_penalty(backwash))

    # ── Clarifier/DAF sludge ──────────────────────────────────────────────────
    if archetype_key in ["B", "C", "D", "E", "F", "G", "I"]:
        sludge = ResidualStreamPenalty(stream_name="Clarifier sludge / DAF float")
        sludge.classified_solid = 0
        sludge.dewaterability = 1
        sludge.disposal_uncertainty = 0
        sludge.offsite_dependency = 0

        if inputs.arsenic_ug_l > 5:
            sludge.classified_solid = 2
            sludge.disposal_uncertainty = 2
            sludge.problem_transfer = 2

        if inputs.pfas_detected:
            sludge.classified_solid = 3
            sludge.disposal_uncertainty = 3
            sludge.problem_transfer = 3

        if inputs.cyanobacteria_confirmed or inputs.algae_risk in ["high", "confirmed_bloom"]:
            sludge.classified_liquid = 1  # cyanotoxin-bearing float during bloom

        streams.append(_calc_stream_penalty(sludge))

    # ── Softening sludge ──────────────────────────────────────────────────────
    if archetype_key == "F":
        lime = ResidualStreamPenalty(stream_name="Lime softening sludge")
        lime.classified_solid = 0
        lime.dewaterability = 3  # Mg(OH)2 fraction is extremely poor
        lime.disposal_uncertainty = 1
        lime.offsite_dependency = 1
        lime.problem_transfer = 0
        # Ca:Mg 50:50 makes it worse
        if inputs.hardness_median_mg_l > 250:
            lime.dewaterability = 3
            lime.offsite_dependency = 2
        streams.append(_calc_stream_penalty(lime))

    # ── Spent BAC/GAC ─────────────────────────────────────────────────────────
    if archetype_key in ["E", "G"] or "gac" in contaminant_modules or "pfas_troc" in contaminant_modules:
        gac = ResidualStreamPenalty(stream_name="Spent BAC/GAC media")
        gac.classified_solid = 0
        gac.offsite_dependency = 2  # thermal reactivation off-site
        gac.reactivation_dependency = 3

        if inputs.pfas_detected:
            gac.classified_solid = 3
            gac.disposal_uncertainty = 3
            gac.offsite_dependency = 3
            gac.problem_transfer = 3
        streams.append(_calc_stream_penalty(gac))

    # ── RO concentrate ────────────────────────────────────────────────────────
    if archetype_key == "H" and inputs.pfas_detected:
        concentrate = ResidualStreamPenalty(stream_name="RO concentrate (PFAS-bearing)")
        concentrate.classified_liquid = 3
        concentrate.disposal_uncertainty = 3
        concentrate.offsite_dependency = 3
        concentrate.problem_transfer = 3
        streams.append(_calc_stream_penalty(concentrate))
    elif archetype_key == "H":
        concentrate = ResidualStreamPenalty(stream_name="RO concentrate")
        concentrate.classified_liquid = 1
        concentrate.disposal_uncertainty = 2
        concentrate.offsite_dependency = 2
        concentrate.problem_transfer = 1
        streams.append(_calc_stream_penalty(concentrate))

    # ── IX brine ──────────────────────────────────────────────────────────────
    if archetype_key == "I" and inputs.arsenic_ug_l > 5:
        brine = ResidualStreamPenalty(stream_name="IX regeneration brine (As-bearing)")
        brine.classified_liquid = 3
        brine.disposal_uncertainty = 3
        brine.offsite_dependency = 3
        brine.problem_transfer = 3
        brine.reactivation_dependency = 2
        streams.append(_calc_stream_penalty(brine))

    profile.streams = streams
    total = sum(s.total for s in streams)
    profile.total_penalty = total

    # Convert to Tier 3 score impact (penalty applied to residuals_burden score)
    # Max theoretical penalty is 21 per stream × N streams; normalise to 0–3 deduction
    max_penalty = 21
    if streams:
        worst_stream = max(s.total for s in streams)
        avg_stream = sum(s.total for s in streams) / len(streams)
        # Penalty from worst stream (primary) + average (secondary weight)
        penalty_deduction = min(4.0,
            (worst_stream * 2.5 / max_penalty) + (avg_stream * 0.5 / max_penalty)
        )
        # Hard extra penalties for specific high-burden cases
        has_classified_liquid = any(s.classified_liquid >= 3 for s in streams)
        has_no_disposal_route = any(s.disposal_uncertainty >= 3 for s in streams)
        if has_classified_liquid: penalty_deduction = min(4.0, penalty_deduction + 1.0)
        if has_no_disposal_route: penalty_deduction = min(4.0, penalty_deduction + 0.5)
    else:
        penalty_deduction = 0.0

    profile.tier3_score_impact = -round(penalty_deduction, 1)

    profile.penalty_description = " | ".join(
        f"{s.stream_name}: {s.burden_level.upper()} ({s.total}/21)"
        for s in streams
    )

    return profile
