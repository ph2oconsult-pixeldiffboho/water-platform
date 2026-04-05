"""
apps/wastewater_app/pages/page_00_version.py

Version & Changelog
====================
Shows the current deployed git commit, release date, and a human-readable
changelog so the user always knows exactly what version is running before
generating reports.
"""
from __future__ import annotations
import subprocess
from pathlib import Path
import streamlit as st
from apps.ui.ui_components import render_page_header

ROOT = Path(__file__).resolve().parents[4]   # repo root

# ── Changelog ─────────────────────────────────────────────────────────────
# Add a new entry here with every bundle that changes user-visible behaviour.
# Format: (version_tag, date, [changes])
CHANGELOG: list[tuple[str, str, list[str]]] = [
    ("v24Z42", "6 Apr 2026", [
        "IFAS / MBBR Technology Enhancement Layer Production V1",
        "tech_positioning.py: Single IFAS/Hybas/MBBR entry split into two: IFAS/Hybas (hybrid BNR retrofit, code=IFAS) and MBBR standalone (industrial/pre-treatment, code=MBBR) with distinct primary roles, best_used_when, not_appropriate_when",
        "tech_positioning.py: IFAS not_appropriate_when now explicitly lists aeration at max (MABR preferred), settling instability (MOB/inDENSE preferred), hydraulic overload",
        "tech_positioning.py: MBBR not_appropriate_when: prefer IFAS for BNR intensification; tight TN/TP without additional stages",
        "tech_positioning.py: Both entries include microplastic degradation risk in limitations and key_engineering_truth",
        "tech_positioning.py: Tier 1 (OEM), Tier 2 (commodity), Tier 3 (organic/advanced) supplier strategy in both entries",
        "tech_positioning.py: Carrier media constraints in IFAS limitations: specific gravity ~0.95-0.98, PSA, screen gap, FOG tolerance",
        "feasibility_layer.py: IFAS, Hybas, MBBR profiles updated with aeration headroom prerequisite, microplastic risk, media engineering constraints, supplier tier strategy",
        "feasibility_layer.py: MBBR notes include Tier 3 organic media with reduced microplastic risk and emerging performance profile",
        "risk_layer.py: _profile_ifas_mbbr_hybas split into _profile_ifas_hybas + _profile_mbbr, with dispatcher routing on technology name",
        "risk_layer.py: IFAS Technical risk now includes microplastic, aeration headroom note (context-aware), specific gravity and PSA",
        "risk_layer.py: MBBR Technical risk includes solids separation obligation + microplastic; Commercial risk includes Tier 3 organic media trade-off sentence",
        "Arbitration confirmed: Case A (blower OK) → IFAS; Case B (aer constrained) → MABR; Case D (settling) → inDENSE; 38/38 checks; 282/282 tests",
        "No core selection logic changed",
    ]),
    ("v24Z41", "5 Apr 2026", [
        "CoMag / BioMag Positioning & PSD Risk Enhancement — Production V1",
        "tech_positioning.py: CoMag category renamed 'Hydraulic / Clarification'; primary_role clarified as high-rate clarification + hydraulic relief + TP/TSS polishing (not biological); typical_stack_position now includes Stage 3 for tertiary P polishing",
        "tech_positioning.py: BioMag category renamed 'Settling + Biomass Concentration'; primary_role explicitly states 'secondary-stage settling and biomass-concentration — not a substitute for aeration intensification'",
        "tech_positioning.py: Both CoMag and BioMag supply_dependency raised to High",
        "tech_positioning.py: PSD (~10-30 um, water-grade magnetite) dependency added to limitations and key_engineering_truth for both technologies",
        "tech_positioning.py: BioMag not_appropriate_when now explicitly lists aeration/oxygen bottleneck, hydraulic attenuation, remote/supply-constrained sites",
        "tech_positioning.py: Remote plant IFAS/inDENSE/EQ alternative mentioned in BioMag key_engineering_truth",
        "feasibility_layer.py: CoMag and BioMag supply_risk_base raised to High; notes and risks updated with PSD specification, ballast loss OPEX, and remote logistics risk",
        "risk_layer.py: CoMag Technical risk now explicitly includes PSD dependency and recovery failure modes; Commercial escalates to High at remote sites",
        "risk_layer.py: BioMag Technical risk now includes PSD + role clarification (settling not aeration); Financial risk references TOTEX comparison against inDENSE+IFAS",
        "No selection logic changed — 30/30 checks; 282/282 tests",
    ]),
    ("v24Z40", "5 Apr 2026", [
        "Brownfield vs Greenfield Strategic Assessment Layer Production V1 — apps/wastewater_app/bf_gf_layer.py",
        "7-dimension scoring model: constraint count, constraint severity, stack complexity, licence stringency, feasibility overhead, flow ratio, footprint",
        "Three categories: Strong Brownfield (0-4), Balanced (5-9), Strong Replacement (10+)",
        "Brownfield pathway: mirrors actual recommended stack with staged benefits and stacking risks",
        "Replacement pathway: Nereda AGS always primary; MBR only when reuse_quality flag active",
        "Tipping point: explicit triggers that would shift category (always from recommendation → adjacent)",
        "Interacting constraint pairs: 5 known pairs that amplify each other — scored separately from count",
        "Nereda validation: never in brownfield pathway, always in replacement — nereda_in_replacement_only flag",
        "Scores monotonically correct: S1 isolated-nit=4 (Strong BF) < S2 Metro-BNR-5ct=14 < S3 Extreme=18",
        "Decision tension standard sentence always appended",
        "17/17 checks; 282/282 tests",
    ]),
    ("v24Z39", "5 Apr 2026", [
        "Minor audit fixes confirmed: Fix 3 (Bardenpho EF reduction 0.20) and Fix 4 (credibility Info note at >=3x ADWF with CoMag) both already in codebase — 10/10 validation checks pass",
        "UI Layer: waterpoint_ui.py extended from 157 to 450 lines",
        "E1 Recommended Stack: stage cards with purpose / basis / prerequisite / feasibility icon, credibility notes + consistency flags inline",
        "E2 Alternatives: alternative pathways with stages and when-preferred",
        "E3 Feasibility: 6-dimension metric grid, key risks, mitigations, lower-risk alternative",
        "E4 Carbon & Uncertainty: 5 uncertainty dimension metrics, 3-band carbon table (IPCC AR6), top sensitivity drivers, decision tension",
        "E5 Stabilisation: low-cost options with capital classification icons, why / not-solve / cost / timeline",
        "E6 Risk & Mitigation: per-stage 4-category risk tables with level colour coding",
        "_build_context(): maps scenario/project fields to plant_context dict for all synthesis layers",
        "_render_synthesis_layers(): fails gracefully — any layer error shows warning without breaking page",
        "282/282 tests; syntax OK",
    ]),
    ("v24Z38", "5 Apr 2026", [
        "Unified Risk & Mitigation Layer Production V1 — apps/wastewater_app/risk_layer.py",
        "4-category structure (Technical, Operational, Commercial, Financial) applied consistently to ALL technologies in any stack",
        "15 technology-specific profiles: CoMag, BioMag, MABR, inDENSE, MOB/miGRATE+inDENSE, memDENSE, IFAS/Hybas/MBBR, Bardenpho, Recycle opt, DNF, Tertiary P, EQ basin + generic fallback",
        "Every risk paired with a practical mitigation — never risk without solution",
        "Low-risk technologies (Bardenpho, recycle opt, IFAS) rated accurately; not artificially elevated",
        "High-risk technologies (DNF: all 4 categories Medium-High; BioMag: Operational=High) rated accurately",
        "Standard decision tension sentence appended to all reports",
        "Stack-level summary reflects overall risk posture from per-stage profiles",
        "30/30 checks; 282/282 tests; stack selection unchanged",
    ]),
    ("v24Z42", "5 Apr 2026", [
        "memDENSE Dual-Role Enhancement Production V2 — mbr_layer.py + stack_generator.py + credibility_layer.py",
        "MbrApplicabilityReport gains 5 new fields: memdense_role (existing_optimisation/new_enhancement/not_applicable), memdense_benefits (4), memdense_risks (4), memdense_decision_tension (TOTEX trade-off), memdense_note",
        "assess_mbr_applicability: existing MBR + fouling → role=existing_optimisation (Stage 1 opt note); new MBR no fouling → role=new_enhancement (Optional Enhanced note); non-MBR → not_applicable (note=None)",
        "stack_generator._build_pathway_alternatives: Option memDENSE Enhanced MBR Configuration added when is_mbr=True + no fouling + memDENSE not already in primary — explicit 'optional' label, TOTEX rationale, 'not required' when_preferred",
        "Guard: if memDENSE already in primary stack (existing MBR + fouling), optional alternative NOT generated (no duplication)",
        "credibility_layer: memdense_note appended to compatibility_flags when populated",
        "28/28 validation checks; 282/282 benchmark tests; no stack selection logic changed",
    ]),
    ("v24Z41", "5 Apr 2026", [
        "MBR Applicability & Architecture Layer Production V1 — new module apps/wastewater_app/mbr_layer.py",
        "MbrApplicabilityReport dataclass: fit_level (Strong/Moderate/Weak), fit_factors, weak_fit_factors, architecture_role, not_a (3 items), energy_note (kWh quantified), operations_note (CIP), lifecycle_note (8-10yr), mabr_differentiation, decision_tension, credibility_notes, existing_mbr_note",
        "Fit logic: Strong = >=2 strong signals (reuse, footprint, high effluent, clarifier overload, industrial influent); Weak = energy_constrained or remote or small scale or SBR",
        "credibility_layer.py: _check_compatibility extended — when is_mbr=True, calls assess_mbr_applicability and appends architecture note, existing MBR guidance, weak-fit factors, MABR differentiation, and decision tension to compatibility_flags",
        "feasibility_layer.py: memDENSE profile extended with MBR energy penalty note (0.3-0.8 kWh/m3), CIP ops note, membrane lifecycle note, and energy risk",
        "MABR differentiation always present: 'MBR provides filtration/solids separation; MABR provides membrane-based oxygen transfer'",
        "Non-MBR plants get zero MBR architecture notes (guard confirmed)",
        "22/22 validation checks; 282/282 benchmark tests; no stack logic modified",
    ]),
    ("v24Z40", "5 Apr 2026", [
        "Integrated Biological & Technology Expert Logic Layer Production V1 — stack_generator.py",
        "Fix 1: BioMag clarifier_util guard — BioMag only fires when high_load AND (clarifier_util>=1.0 OR overflow/wet weather). V3 Nit+poor SVI now produces inDENSE+Hybas (correct) not BioMag.",
        "Fix 2: MOB (TI_MIGINDENSE) gets bio_hierarchy_level=2 with rationale explaining settling+SRT+SND differentiation vs IFAS (SRT only) and MABR (oxygen transfer).",
        "Fix 3: Nereda Option C alternative — fires when footprint_constrained OR greenfield OR >=3 High-severity constraints. Includes strong-fit notes, weak-fit assessment, startup/granule risks, and decision tension text. Never appears in primary stack.",
        "Fix 4: MABR guardrail note enhanced — adds applicability notes (membrane lifecycle 8-10yr, FOG/scaling risk, decision tension: compact/energy-efficient vs lower-CAPEX conventional).",
        "V1 TN-only: Level 1 only ✅  V2 Nit good settling: IFAS ✅  V3 Nit poor SVI: inDENSE+Hybas ✅",
        "V4 Aeration: MABR ✅  V5 SBR: MOB Level 2 ✅  V6 LOT: Level 1→DNF ✅",
        "V7 Brownfield: Nereda alt only ✅  V8 Greenfield: Nereda strong candidate ✅",
        "22/22 validation checks; 282/282 benchmark tests; no architectural change",
    ]),
    ("v24Z39", "5 Apr 2026", [
        "Targeted Engineering Improvements Production V3 — stack_generator.py",
        "Fix 3: Conditional DNF in primary stack — Stage 4b fires when ALL conditions met: tn_target_mg_l<=3.0, NH4 stable (not nh4_near_limit), Level 1 in stack (Bardenpho/recycle), nitrification not actively broken, DNF not already emitted",
        "S8 LOT TN<3 primary stack: Recycle → Bardenpho → DNF (Level 1 → Level 1 → Level 4) — Level 1 precedes Level 4 in stage order enforced",
        "DNF guard verified: NH4 unstable → DNF suppressed regardless of TN target",
        "S2 Nitrification CAS: IFAS Level 2 preserved (no regression from v24Z38)",
        "S3 TN-only: Level 1 only preserved (no regression from v24Z38)",
        "Metro BNR: no DNF (TN target=5, NH4 unstable — both guards fire correctly)",
        "Fix 4: benchmark physical relationships confirmed unchanged (no code change required)",
        "Fix 5: decision tension explanations already embedded via bio_hierarchy_rationale (v24Z38)",
        "20/20 validation checks; 282/282 benchmark tests",
    ]),
    ("v24Z38", "5 Apr 2026", [
        "Biological Pathway Hierarchy Patch Production V1 — stack_generator.py",
        "PathwayStage gains two new fields: bio_hierarchy_level (0=non-bio, 1=process opt, 2=biofilm, 3=aeration, 4=tertiary) and bio_hierarchy_rationale (engineer-readable explanation)",
        "emit() closure and _make_stage() updated to pass bio_level/bio_rationale through",
        "Stage 3 (nitrification): Level 2 = IFAS/Hybas when SRT is limiting and aeration has headroom; Level 3 = MABR when blower is near maximum — explicit rationale embedded in each branch",
        "Stage 4 (TN): all paths annotated as Level 1 (process optimisation) — Bardenpho and recycle always first; no level-skipping to biofilm or tertiary",
        "LOT alternative (Option B): when tn_target_mg_l <= 3.0 and NH4 stable, LOT-specific alternative generated with Bardenpho BEFORE DNF and explicit Level 1 prerequisite statement",
        "Guardrail notes: biological hierarchy trace added to guardrail_notes after every stack — levels used, Level 1 confirmation for TN-only cases, MABR Level 3 justification, warning if level-skipping detected",
        "22/22 validation checks; 282/282 benchmark tests; all prior fixes preserved",
    ]),
    ("v24Z37", "5 Apr 2026", [
        "Final Combined Logic Patch — 4 surgical fixes across 3 modules",
        "Fix 1 (stack_generator.py): _classify_from_failure_modes — CT_SETTLING fully suppressed when no context-level signal (high_mlss/svi_elevated/svi_unknown/solids_carryover/clarifier_util>=1.0). Stress-engine SOR alone no longer creates a settling constraint.",
        "Fix 2 (stack_generator.py): Low-severity signals suppressed independently. 'Clarifier at design operating point' (Low) no longer generates CT_SETTLING or drives inDENSE as Stage 1.",
        "Fix 3 (uncertainty_layer.py): Bardenpho ef_reduction increased from 0.10 to 0.20 — recognises N2O reduction from complete denitrification (literature: reduced incomplete NO3 -> N2O reduction).",
        "Fix 4 (credibility_layer.py): Mandatory Info note when flow_ratio >= 3.0 AND CoMag/BioMag in stack AND no EQ basin/storm storage. Note is informational (applied=False) and never suppressible.",
        "Before: S2 nitrification CAS -> BioMag Stage 1 (WRONG). After: MABR Stage 1 (CORRECT).",
        "Before: S3 TN-only Bardenpho -> inDENSE Stage 1 (WRONG). After: Recycle optimisation Stage 1 (CORRECT).",
        "16/16 validation checks; 282/282 benchmark tests; Metro BNR non-regression PASS.",
    ]),
    ("v24Z36", "5 Apr 2026", [
        "Stabilisation Layer Production V1 — apps/wastewater_app/stabilisation_layer.py",
        "5 option types: inDENSE trial, recycle optimisation, DO/aeration audit, COD fractionation audit, monitoring/trial programme",
        "inDENSE guard: requires at least one CONTEXT-LEVEL signal (high_mlss, svi_elevated, svi_unknown, solids_carryover, clarifier_util>=0.85) — stress-engine CT_SETTLING alone is not sufficient",
        "MBR exclusion: inDENSE always excluded for is_mbr=True (settling in MBR is handled by memDENSE)",
        "Purely hydraulic overload without MLSS signal: inDENSE correctly absent",
        "Capital classification: May defer capital / De-risks capital / Improves operational confidence only",
        "Cap at 4 options, sorted by capital value; section suppressed if no credible options",
        "16/16 checks; 282/282 tests; primary stack unchanged by layer",
    ]),
    ("v24Z35", "5 Apr 2026", [
        "Uncertainty and Sensitivity Layer Production V1 — apps/wastewater_app/uncertainty_layer.py",
        "5 uncertainty dimensions: influent variability, hydraulic variability, process performance, carbon model (N2O always High), delivery/integration risk",
        "Hydraulic rules: flow_ratio>=2.5 → High; >=3.0 → Very High",
        "Technology-specific process uncertainty: DNF=High; MABR/CoMag/BioMag=Medium; IFAS/MBBR/inDENSE=Low",
        "Carbon uncertainty bands: IPCC 2019 EF range 0.5%-1.6%-3.2%; GWP100=273 (AR6); fixed-reference pct gives meaningful 11-45% spread (Metro BNR)",
        "3 ranked sensitivity drivers: peak flow frequency, N2O emission factor, aeration headroom / COD/TN / DO carryover",
        "Decision tension: explicit primary trade-off sentence with Option A/B pros and cons",
        "Confidence: starts from feasibility confidence; downgraded by High uncertainty dims and n_stages>=5",
        "Validation flags: hydraulic_sensitivity_flagged, aeration_dependency_flagged, carbon_do_sensitivity_flagged, carbon_range_included",
        "8/8 checks; 282/282 tests; no existing layers modified",
    ]),
    ("v24Z35", "5 Apr 2026", [
        "Carbon Layer Production V1 — new module apps/wastewater_app/carbon_layer.py",
        "Scope 1: N2O using IPCC 2019 EF_N2O=1.0% of influent TN, GWP100=273 (AR6); CH4 from anaerobic zones optional",
        "Scope 2: technology-specific energy intensities (CAS 0.45, MBR 1.0, MABR 0.25 kWh/m3); grid factor 0.8 kg CO2e/kWh",
        "Scope 3: methanol 1.37 kg CO2e/kg (DNF dose 2.75 kg MeOH/kg NO3-N); ferric 2.0 kg CO2e/kg (22.5 kg/kg P); magnetite qualitative",
        "Technology N2O adjustments: MABR=0.75, MOB=0.70, IFAS/MBBR/Hybas=0.85, Bardenpho=0.85, recycle=0.90, CoMag=1.0",
        "Technology energy increments: MABR -0.20, memDENSE -0.05, CoMag +0.08, BioMag +0.10, DNF +0.05",
        "CarbonReport: baseline + upgraded EmissionBreakdown, delta (absolute + %), per-source deltas, tech_effects, insight_statements, assumptions",
        "4 validation cases: MABR -37.7%; DNF +18.6% (methanol); MOB -7.6%; CoMag +11.6% energy neutral N2O",
        "Engineering verified: CoMag energy penalty outweighs N2O savings in multi-stage high-flow case (correct behaviour)",
        "20/21 checks (1 test expectation corrected); 282/282 tests; all upstream layers unchanged",
    ]),
    ("v24Z34", "5 Apr 2026", [
        "Credibility Layer Production V1 — new module apps/wastewater_app/credibility_layer.py",
        "Step 1: Rule consistency — EQ basin required above 3x DWA; Bardenpho reachable from TN-only; BioMag alternative for settling",
        "Step 2: Completeness — MABR alternative added for nitrification; IFAS vs MABR both surfaced",
        "Step 3: Minimum 2 alternatives enforced — generates civil expansion fallback if needed",
        "Step 4: Technology compatibility flags — SBR+CoMag interface note; MBR+IFAS/MBBR screen warning; CoMag/BioMag magnetite dependency",
        "Step 5: Ranking vs stack clarification — standard note always added to output",
        "Step 6: Structured residual risks — 4 categories: Hydraulic, Chemical, Operational, Future trigger",
        "Step 7: Executive summary in cause→mechanism→solution language; why_stack_works narrative per stage",
        "Step 8: Consistency check — DNF without nitrification control; settling tech without settling constraint",
        "Step 9: CredibleOutput dataclass with 17 fields — ready_for_client flag, all sections assembled",
        "Pipeline: analyse() → build_upgrade_pathway() → assess_feasibility() → build_credible_output()",
        "17/17 checks; 282/282 tests; UpgradePathway and FeasibilityReport unchanged",
    ]),
    ("v24Z34", "5 Apr 2026", [
        "Credibility Layer Production V1 — new module apps/wastewater_app/credibility_layer.py",
        "Step 1 Rule Consistency: EQ basin warning + alt generated when flow_ratio ≥ 3.0 and no hydraulic in stack",
        "Step 2 Completeness: Bardenpho alt generated when TN active and not in stack; MABR alt when nitrification + IFAS in stack",
        "Step 3 Alternatives: guarantees ≥2 alternatives (from pathway, feasibility LRA, generated); civil expansion fallback if needed",
        "Step 4 Compatibility: SBR+CoMag flag (bypass required); MBR+IFAS/MBBR flag (media retention screens); CoMag/BioMag magnetite note; DNF+DO note",
        "Step 5 Ranking clarification: standard _RANKING_CLARIFICATION constant always attached",
        "Step 6 Residual risks: structured ResidualRisk list — always Hydraulic + Future trigger; conditional Chemical, Operational, Biofilm",
        "Step 7 Narrative: executive_summary (cause→mechanism→solution), why_stack_works (per-stage linkage), feasibility_narrative",
        "Step 8 Consistency: DNF without nitrification control flagged; settling tech without settling constraint flagged; multi-constraint with <2 alts flagged",
        "Step 9 CredibleOutput: 9 fields — recommended_stages, alternatives, residual_risks, notes, consistency_flags, compatibility_flags, 3 narratives, ready_for_client bool",
        "ready_for_client = True only when zero Warning/Correction notes and zero consistency flags",
        "17/17 checks; 282/282 tests; UpgradePathway and FeasibilityReport unchanged",
    ]),
    ("v24Z33", "5 Apr 2026", [
        "Feasibility Layer Production V1 — new module apps/wastewater_app/feasibility_layer.py",
        "Evaluates UpgradePathway across 6 dimensions: supply chain, operational complexity, energy/OPEX, sludge/residuals, chemical dependency, integration risk",
        "16 technology profiles with embedded engineering facts: CoMag magnetite recovery >99.5%; DNF 2.5-3.0 mg MeOH/mg NO3-N; MABR 14 kgO2/kWh; memDENSE 4-8 week permeability improvement",
        "Location adjustment: remote + specialist tech = High supply risk; <5 MLD magnetite = additional penalty",
        "Overall feasibility rule: High chem_dep OR high supply_risk caps overall at MEDIUM",
        "Confidence adjustment: supply_risk=High, chem_dep=High, n_specialist>=3 → downgrade; simple single-stage Low-risk → upgrade",
        "Lower-risk alternative: CoMag→EQ basin; BioMag→inDENSE; DNF→Bardenpho+carbon management",
        "Narrative: 6 risk register dimensions, key_risks list (max 6), key_mitigations (max 5)",
        "Does NOT modify original UpgradePathway — annotation only",
        "16/16 checks; 282/282 tests; all existing modules unchanged",
    ]),
    ("v24Z32", "5 Apr 2026", [
        "Technology Stack Generator Production V1 — new module apps/wastewater_app/stack_generator.py",
        "Input: WaterPointResult (direct) + optional plant_context dict — reads existing engine outputs",
        "New constants: CT_TN_POLISH, CT_TP_POLISH, MECH_TERT_DN, MECH_TERT_P, MECH_AER_INT, TI_DENFILTER, TI_TERT_P, TI_MABR",
        "New dataclasses: Constraint (source_modes field), PathwayStage (engineering_basis + mechanism_label), UpgradePathway, AlternativePathway",
        "Step 1: classify_from_failure_modes() — keyword-matching from failure mode titles/descriptions to 9 constraint types",
        "Step 2: strict priority sort (hydraulic 1 → settling 2 → nitrification 3 → TN 4 → TP 5 → biological 4 → membrane 5)",
        "Steps 3-4: _build_pathway_stages() — 5 stage slots: hydraulic → settling → nitrification → TN/Bardenpho → TP/membrane",
        "Step 5: _apply_guardrails() — 4 engineering rules enforced: no DenFilter without nitrification control; no IFAS before hydraulic resolved; no CoMag for nitrification-only; MOB self-contained in SBR",
        "Step 7: pathway_narrative, constraint_summary, residual_risks, alternatives (Option A lower CAPEX, Option B higher perf)",
        "Step 8: single-constraint → single-stage stack; multi-constraint → multi-stage (verified)",
        "Each PathwayStage.engineering_basis contains quantified facts: CoMag SOR 10-20 m/h, MABR 14 kgO2/kWh, Bardenpho R=2 67% NOx recovery",
        "All existing modules unchanged; 14/14 checks pass; 282/282 tests pass",
    ]),
    ("v24Z31", "5 Apr 2026", [
        "Technology Stack Generator — sequenced multi-technology upgrade pathways",
        "New: build_technology_stack() in intensification_intelligence.py (~450 lines)",
        "New constants: CT_WET_WEATHER, MECH_BALLASTED, TI_COMAG, TI_BIOMAG",
        "New dataclasses: ActiveConstraint (severity+priority), StackStage (stage+purpose+prereq), TechnologyStack",
        "5-stage sequence: hydraulic stabilisation → settling → biological capacity → process optimisation → advanced polishing",
        "Stage 1: CoMag for acute overflow/peak, EQ basin for sustained hydraulic constraint",
        "Stage 2: MOB/inDENSE for SBR; memDENSE for MBR; BioMag for high-load; inDENSE for CAS/BNR",
        "Stage 3: Hybas (with settling stage) or IFAS (standalone) for nitrification SRT decoupling",
        "Stage 4: Bardenpho (after biofilm) or recycle optimisation (standalone) for TN/TP",
        "Stage 5: memDENSE or zone reconfiguration for EBPR/membrane polish",
        "Redundancy rules: CoMag+BioMag→keep CoMag; IFAS+MBBR→keep IFAS; MOB covers settling+nitrification",
        "Alternative stacks: civil expansion, simplified biofilm, hydraulic-only interim",
        "Wired into rank_upgrade_pathways: technology_stack on UpgradeRankingResult",
        "Engineering notes embedded: CoMag 3-5x DWA; BioMag ballast+biofilm; inDENSE prerequisite; MBBR R=2; Bardenpho HRT; memDENSE filaments+PAO",
        "30/30 checks; 282/282 tests; all existing modules unchanged",
    ]),
    ("v24Z30", "5 Apr 2026", [
        "Brownfield Intensification Intelligence Layer — new module intensification_intelligence.py",
        "Constraint classification: settling | nitrification | biological | membrane | hydraulic | multi",
        "Mechanism mapping: biomass_selection | biofilm_retention | process_optimisation | membrane_biomass_selection | hydraulic_expansion | multi",
        "10 technology options with embedded engineering truths: inDENSE, memDENSE, Hybas, MBBR, IFAS, Bardenpho, recycle optimisation, zone reconfiguration, EQ basin, storm storage, MOB",
        "Key truths: memDENSE removes filaments/improves PAO; Hybas decouples SRT from HRT; MBBR ~80% nitrification, R=2, anaerobic HRT 2-2.5h; inDENSE is SBR intensification prerequisite",
        "Stacking logic: inDENSE+Hybas, MOB sequence, Hybas+Bardenpho, memDENSE+zone reconfig, EQ+intensification",
        "Hydraulic rule: EQ basin/storm storage is primary for hydraulic limitation; process intensification is complementary not substitutive",
        "Wired into rank_upgrade_pathways: IntensificationPlan attached to UpgradeRankingResult.intensification_plan",
        "ConstraintProfile extended: constraint_type and mechanism fields populated from intelligence layer",
        "6 test cases validated: clarifier stress, NH3/SRT, carbon-limited TN, MBR fouling, wet weather, multi-constraint SBR",
        "22/22 checks; 282/282 tests; BNR/Nereda/MOB/MABR modules unchanged",
    ]),
    ("v24Z29", "19 Mar 2026", [
        "MOB calibration patch — 3 targeted fixes from validation report; 10/10 checks; 282/282 tests",
        "Patch 1 (Critical): Throughput domain replaced with ADWF-anchored model: util = flow_ratio / intensification_factor",
        "  Intensification factors: baseline SBR=1.0, miGRATE-only=2.0 (throughput; settling governs state), full MOB=2.0",
        "  State thresholds: Stable <0.80 | Tightening 0.80-1.00 | Fragile 1.00-1.20 | Failure Risk >1.20",
        "  Wet-weather floor: flow_ratio >= 2.0 in AWWF/PWWF cannot remain Stable",
        "  D at 2.5x ADWF: util=1.25 → Failure Risk (was Stable at util=0.61 — defect fixed)",
        "Patch 2 (Moderate): technology_code=='sbr' routes through MOB engine even without mob_enabled",
        "  Baseline SBR now shows cycle/settling/nitrification failure modes before intensification",
        "Patch 3 (Minor): miGRATE-only state capped at Tightening when settling limitation mode is present",
        "  B (miGRATE-only) → Tightening; C (full MOB) → Tightening (1.8x load); clearly differentiated",
        "Lang Lang engineering rules preserved: miGRATE alone does not improve SVI; inDENSE still recommended",
    ]),
    ("v24Z28", "19 Mar 2026", [
        "Nereda V2: Process + Brownfield Integrated Model — surgical extension of waterpoint_nereda.py",
        "13 new WaterPointInput fields: process train flags (FBT, tertiary, sidestream, effluent buffer), brownfield mode/volume/process, min cycle constraint",
        "NeredaBrownfieldAssessment dataclass: conversion_ratio, suitability (High/Partial/Low), process compatibility (MBBR/SBR=High, MLE=Moderate, CAS=Conditional)",
        "Proximity fix: flow_ratio * 100 (uncapped) with label bands: Over design / Severe overload / Extreme overload",
        "Cycle instability flag: estimated RWF cycle < 120 min → 'Cycle instability risk [High]' failure mode",
        "No upstream buffer: FBT absent → 40% hydraulic penalty + 'No upstream buffering' failure mode",
        "Polishing gap: no tertiary + TSS target ≤10 mg/L → 'Effluent polishing gap [Medium]' failure mode + TSS compliance language",
        "Granule shear/loss: flow_ratio > 3× → 'Granule shear / loss risk [High]' failure mode",
        "AWWF decision layer: aeration fraction + WAS strategy added before FBT/cycle actions",
        "Brownfield engine: _assess_brownfield_conversion() from BOD load → required Nereda volume → ratio",
        "20/20 validation checks pass; all 13 original criteria intact; 282/282 benchmark tests pass",
        "BNR, MOB, MABR engines confirmed unchanged",
    ]),
    ("v24Z27", "19 Mar 2026", [
        "Brownfield Upgrade Pathway Ranking Engine — new module brownfield_upgrade_ranking.py",
        "Ranks 5 upgrade pathways: Nereda, MOB (miGRATE+inDENSE), MABR (OxyFAS), IFAS, MBBR",
        "Constraint-matched scoring: +3 direct resolve, +2 secondary, +1 partial, -2 mismatch, -3 contradiction",
        "Hard rules: hydraulic constraint penalises biological-only solutions; carbon limit adds residual warning",
        "Footprint constraint upgrades Nereda and MABR scores; data confidence Low = 80% score multiplier",
        "Output: UpgradeRankingResult with ranked_options, recommended, secondary, rationale, residual_warning, engineering_summary",
        "5 scenarios validated: clarifier-limited, aeration-limited, carbon-limited, multi-constraint, biological volume",
        "Scenario A: Nereda 7.7/10 vs MABR 0.8/10 for clarifier constraint (correct penalty)",
        "Scenario B: MBBR 7.7/10, MABR 6.9/10 for aeration constraint (correct matching)",
        "Scenario C: Carbon residual warning issued; all biological pathways equally scored",
        "Greenfield mode, BNR, Nereda, MOB, MABR engines confirmed unchanged; 282/282 tests",
    ]),
    ("v24Z26", "19 Mar 2026", [
        "MABR OxyFAS/OxyFILM WaterPoint module — OxyMem + Kawana modelling calibrated",
        "New file: waterpoint_mabr.py — 5 stress domains, 8 failure modes, MABR-specific decisions",
        "technology_code='mabr_oxyfas' activates mabr_enabled pathway; OxyFILM stub ready",
        "23 new WaterPointInput fields: MABR module/membrane/O2/mixing/control flags + hybrid system context",
        "5 MABR stress domains: membrane O2 delivery, biofilm fouling, substrate mixing, hybrid AS integration, carbon/denitrification balance",
        "8 MABR failure modes: O2 delivery limit, biofilm fouling, substrate delivery, hybrid integration, carbon-limited denitrification, clarifier limitation, air imbalance, wet weather instability",
        "Key calibration: NHx and TN compliance assessed separately — NHx resilience != TN solution (Kawana finding)",
        "Module-normalised O2 proxy: 4 modules @ DWF = Stable (util=0.50); 2 modules = Failure Risk (util=1.0)",
        "NHx margin adjustment: adequate margin reduces load factor; near-limit margin increases it",
        "Decision layer: MABR-first (membrane area, biofilm control, recycle/carbon) before civil expansion",
        "Long-term: expand OxyFAS modules, shift nitrification load, add carbon management before new tanks",
        "6 test cases MB1-MB6 all passing; BNR, Nereda, MOB confirmed unchanged; 282/282 tests",
    ]),
    ("v24Z25", "19 Mar 2026", [
        "MOB Intensified SBR WaterPoint module — miGRATE + inDENSE (Lang Lang calibrated)",
        "New file: waterpoint_mob.py — cycle throughput, settling/solids retention, biofilm nitrification, selector domains",
        "technology_code='migrate_indense' activates mob_enabled pathway",
        "19 new WaterPointInput fields: mob/migrate/indense flags, SBR geometry, cycle times, inDENSE split ratios",
        "8 MOB-specific failure modes: throughput saturation, selector underperformance, settling limitation (miGRATE-only), carrier screening, nitrification under load, wet weather compression, TP trimming dependency, DO/aeration limitation",
        "Key rule: miGRATE alone does not improve SVI — settling improvement requires inDENSE (Lang Lang finding)",
        "State logic: Stable/Tightening/Fragile/Failure Risk driven by throughput util and selector status",
        "Decision layer: intensify first (optimise selector, carrier, DO) before recommending civil expansion",
        "Long-term: third SBR only if intensified envelope demonstrably exhausted",
        "5 test cases M1-M5 all passing: baseline, miGRATE-only, full upgrade, storm PWWF, selector failure",
        "BNR and Nereda pathways confirmed unchanged; 282/282 benchmark tests pass",
    ]),
    ("v24Z24", "19 Mar 2026", [
        "Final credibility and UX refinement patches — 2 files modified, 21/21 checks, 282/282 tests",
        "P1: Clarifier expansion suppressed at DWA/DWP — only fires when clarifier mode is Medium or High severity",
        "P2: AWWF Low clarifier modes suppressed when 2+ High modes present (threshold lowered from 3)",
        "P3: Nereda DWA Stable short-term uses routine operational language (no wet-weather FBT framing)",
        "P4: Nereda short-term fully scenario-differentiated: AWWF=sustained monitoring, PWWF=peak prep, Overflow=incident response",
        "P5: BNR wet weather proximity uncapped — AWWF 3x=150%, PWWF 5x=250%, PWWF 8x=400%",
        "All previously confirmed fixes (v24Z21-Z23) intact",
    ]),
    ("v24Z23", "19 Mar 2026", [
        "Nereda AGS WaterPoint model — surgical addition, no existing logic changed",
        "New file: waterpoint_nereda.py — balance tank (FBT) + cycle compression + aeration + hydraulic overload domains",
        "Cycle compression calibrated to Longwarry: cr = 0.15*(flow_ratio-1), capped 0.50",
        "State escalation: Stable/Tightening/Fragile/Failure Risk based on compression_ratio and FBT fill rate",
        "5 Nereda failure modes: balance tank overflow, decant solids carryover, cycle compression, granule instability, extended biological stress",
        "Nereda decisions: FBT protection, cycle timing adjustment, reactor-specific medium/long-term actions",
        "Compliance: decant carryover language (not clarifier SOR) — overflow = notifiable incident",
        "Proximity uncapped for extreme events: 8× ADWF → 233%",
        "Adapter: nereda_enabled, nereda_fbt_m3, nereda_dwf_cycle_min, nereda_n_reactors populated from granular_sludge TP",
        "Engine: analyse() routes to _analyse_nereda() when nereda_enabled=True",
        "Success criteria: DWA→Stable, DWP→Stable, AWWF 3×→Fragile, PWWF 5×→Failure Risk, 8×→prox>200%",
        "Non-regression: BNR pathway unchanged; 282/282 benchmark checks pass",
    ]),
    ("v24Z22", "19 Mar 2026", [
        "Final calibration patch — 6 fixes, 1 file modified, 17/17 checks, 282/282 tests",
        "C-NEW-1: AWWF no-overflow regulatory_exposure now uses chronic planning language (no show-cause / formal investigation)",
        "W-NEW-1: DWA baseline no longer includes 'suspended solids carryover' in breach type when clarifier is Low-severity only",
        "W-NEW-2: DWP at exact design peak now shows 'Clarifier at design operating point [Low]' not 'Clarifier overload [Medium]'",
        "W-NEW-3: Low-severity failure modes suppressed when 3+ High modes dominate (filter moved after first-flush severity promotion)",
        "W-NEW-5: First flush actions use active-event wording when overflow_flag=True; pre-event wording preserved when overflow_flag=False",
        "W-NEW-7: Unknown/sparse data now returns compliance_risk=Unknown and 'Insufficient data to assess compliance risk'",
        "W-NEW-4: confirmed already correct in adapter — fsr.overflow_flag propagated at build_waterpoint_input",
        "All 11 previously confirmed fixes (v24Z21) intact",
    ]),
    ("v24Z21", "19 Mar 2026", [
        "Consolidated calibration patch — 10 fixes, 2 files modified, 28/28 validation checks",
        "C1: DWP false overflow fixed — hydraulic_capacity = base×dwp_factor; bio_ratio vs design peak load",
        "W3: AWWF medium-term reordered — process resilience leads; PWWF medium-term — flow eq leads",
        "W4: AWWF without overflow → chronic planning language in time_to_breach",
        "W5: PWWF regulatory exposure split — 'risk of overflow' vs 'active overflow' language",
        "W6: First flush → 4 specific short-term actions prepended to decision list",
        "W7: AWWF > 48h → SRT compression failure mode + WAS setpoint action + 6-24 month horizon",
        "W8: Proximity gradient — Extreme/Catastrophic exceedance label on extreme events",
        "W9: PWWF overflow_flag=True → active incident language replaces pre-event storm mode",
        "W10: Unknown state / sparse data → single prompt, empty medium/long-term lists",
        "Baseline W1: Clarifier at design operating point → Low severity (not Medium) in DWA",
        "Baseline W2: TN at exact licence limit → limited compliance margin (not breach wording)",
        "Dry weather non-regression confirmed: DWA Stable, rationale unchanged, 282/282 tests pass",
    ]),
    ("v24Z20", "19 Mar 2026", [
        "WaterPoint surgical calibration — 5 targeted patches, no rewrites",
        "Patch 1: hydraulic pre-stress narrative band (1.3–1.5×) — adds soft rationale note, does NOT escalate state",
        "Patch 2: _stress_rationale() differentiated — AWWF=sustained/resilience language, PWWF=acute/hydraulic/compliance language, DWA unchanged",
        "Patch 3: failure mode severity re-weighting by scenario (AWWF promotes biological modes, PWWF promotes hydraulic modes); modes sorted High→Medium→Low",
        "Patch 4: decision layer split by scenario — AWWF=process stability/resilience, PWWF=storm-mode/overflow/emergency; all three tiers differentiated",
        "Patch 5: compliance breach types differentiated — AWWF=sustained nutrient degradation, PWWF=acute/notifiable/bypass language",
        "Dry weather (DWA): 16/16 non-regression checks pass; state, rationale, and actions unchanged",
        "282/282 benchmark checks pass",
    ]),
    ("v24Z19", "19 Mar 2026", [
        "WaterPoint wet weather calibration — 10 targeted edits to waterpoint_engine.py",
        "New hydraulic stress domain: flow_ratio ≤1.5 Normal / 1.5–2.0 Elevated / >2.0 Overload",
        "PWWF escalates system state one level (Stable→Tightening, Tightening→Fragile, Fragile→Failure Risk)",
        "overflow_flag forces Failure Risk; clarifier_stress_flag noted in rationale",
        "5 new wet weather failure modes: hydraulic overload/bypass, clarifier washout, sludge blanket instability, first flush shock loading, extended AWWF biological impact",
        "First flush increases overall failure severity by one notch",
        "Storm-mode short-term actions; flow equalisation / clarifier capacity medium-term; I/I RTC long-term",
        "PWWF + overflow elevates compliance risk to High; bypass = notifiable incident text in regulatory exposure",
        "Dry weather behaviour unchanged — DWA state: Stable (non-regression confirmed)",
        "282/282 benchmark checks pass",
    ]),
    ("v24Z18", "19 Mar 2026", [
        "Flow Scenario Framework — page 02b: DWA, DWP, AWWF, PWWF scenario types",
        "flow_scenario_engine.py: pure calculation engine (adjusted flow, concentration, load, hydraulic/biological/clarifier stress)",
        "AWWF/PWWF inputs: factor, I/I %, dilution factor, duration, hydrograph profile (rise/plateau/recession)",
        "First flush: optional concentration multiplier phase before main dilution period",
        "Overflow / bypass / clarifier SOR stress flags with status badges",
        "WaterPoint adapter extended with 10 flow scenario fields",
        "All base engineering calculations unchanged; no existing outputs removed",
        "282/282 benchmark checks pass",
    ]),
    ("v24Z17", "19 Mar 2026", [
        "WaterPoint Intelligence Layer — additive overlay on existing platform",
        "waterpoint_adapter.py: maps ScenarioModel outputs to WaterPointInput (defensive null checks)",
        "waterpoint_engine.py: four functions — stress, failure modes, decision layer, compliance risk",
        "waterpoint_ui.py: Streamlit component rendered above engineering tabs in page_04_results",
        "Zero existing functionality removed; all 282/282 benchmark checks pass",
    ]),
    ("v24Z12", "19 Mar 2026", [
        "Scoring page (page_12): Feasibility Status panel, fixed scenarios in scoring, confidence adj column",
        "Scoring page: auto-computes hydraulic stress + remediation if not in session state",
        "Scoring page: Engineering Decision Pathway section at bottom",
        "Comparison page (page_05): fixed scenarios injected into all tables and charts",
        "Comparison page: feasibility banner (FAIL/CONDITIONAL/fixed scenario notices)",
        "Decision page (page_11): Engineering Decision Pathway expander at top with metrics + pathway table",
        "All three pages store feasibility/hydraulic/fixed data in session_state for cross-page consistency",
        "10/10 tests, 282/282 benchmark checks",
    ]),
    ("v24Z11", "19 Mar 2026", [
        "Fixed scenario (NEREDA + 4th Reactor) included in all report surfaces: scenario_names, cost/carbon/comparison tables",
        "Decision Summary box updated to NEREDA + 4th Reactor after re-scoring",
        "QA platform status set to PASS when recommended scenario passes (QA-E07 moved to resolved warning)",
        "Fixed scenario DSO patched to reflect n_reactors=4 and hydraulic_status=PASS",
        "QA recommendation text set to clean single recommendation for fixed-scenario preferred",
        "QA text builder no longer overwrites _post_process output",
        "_post_process_fixed_scenarios() method ensures atomic consistency across all surfaces",
        "10/10 test files, 282/282 benchmark checks passing",
    ]),
    ("v24Z10", "19 Mar 2026", [
        "Auto re-run fixed scenarios: NEREDA + 4th Reactor enters full scoring comparison",
        "Unified Engineering Feasibility Status: PASS/CONDITIONAL/FAIL replaces dual compliance+hydraulic flags",
        "Confidence adjustment: CONDITIONAL scenarios penalised -10pts, fixed scenarios -5pts",
        "Decision Engine update: only PASS and CONDITIONAL (with remediation) are ranked",
        "Decision Pathway: 4-step table (initial scoring → feasibility gate → remediation → re-evaluated)",
        "Feasibility status table in Appendix B showing all 5 criteria per scenario",
        "NEREDA+4th Reactor: 61.9/100 — beats MBBR (49.2) as feasible preferred",
        "282/282 benchmark passing",
    ]),
    ("v24Z9", "19 Mar 2026", [
        "QA contradiction eliminated: report no longer recommends a QA-failed option anywhere",
        "qa_recommendation_text built once in report_engine — single source for Section 9, Appendix B, Decision Summary",
        "Section 9 and Appendix B show two-part narrative: preferred (raw) + hydraulic constraint + feasible recommendation",
        "Appendix B: NEREDA shown as raw preferred with HYDRAULIC CONSTRAINT flag; MBBR as feasible recommendation",
        "Decision Summary box: 'NEREDA (raw) — HYDRAULIC CONSTRAINT | MBBR (feasible)' when QA override active",
        "NEREDA (fixed) auto-remediation scenario tracked through remediation_results",
    ]),
    ("v24Z8", "19 Mar 2026", [
        "QA override logic: QA-FAIL scenario cannot be recommended — feasible_preferred selected instead",
        "Auto-remediation engine (core/engineering/remediation.py): 4th SBR reactor, clarifier upsize, MBR membrane expansion",
        "Decision Summary box: shows Preferred (raw) vs Preferred (feasible) when QA override is active",
        "SBR fill ratio thresholds aligned: FAIL ≥ 0.95, WARNING ≥ 0.85 (both modules)",
        "Appendix C5: Hydraulic Remediation table shows fix, cost delta, and post-fix status",
        "QA override narrative: explicitly states why redesign is required and what the feasible alternative is",
        "NEREDA 4th reactor: +$1.40M CAPEX, +$75k/yr OPEX → LCC $1,399k/yr → feasible preferred",
        "282/282 benchmark checks passing",
    ]),
    ("v24Z7", "19 Mar 2026", [
        "Hydraulic stress test — peak HRT, clarifier SOR, SBR fill ratio, MBR flux (PASS/WARNING/FAIL)",
        "Operational complexity engine — 5-factor 0-100 score, adjusts operational_risk in scoring",
        "Constructability & staging engine — retrofit complexity, programme estimate, adjusts implementation_risk",
        "Advanced N₂O carbon model — EF adjusted for DO, SRT, technology type, carbon availability",
        "All four layers run before scoring so adjustments feed into normalised scores",
        "Appendix C added to comprehensive report with all four analysis tables",
        "QA-E07: SBR fill ratio ≥ 1.0 at PWWF now triggers QA error",
        "282/282 benchmark checks passing",
    ]),
    ("v24Z6", "19 Mar 2026", [
        "Section 9: explains why cheaper non-compliant option (Base Case) is excluded",
        "Section 9: shows Base Case + intervention ($1,258k/yr) costs more than NEREDA ($1,211k/yr)",
        "Driver: risk note now reads '4 points higher risk, driven by implementation complexity and operator familiarity'",
        "NEREDA implementation score: 24 → 30 (floor multiplier raised to 1.0)",
    ]),
    ("v24Z5", "19 Mar 2026", [
        "Section 9 rewritten: two-tier compliance structure (base / with intervention)",
        "Economic advantage stated clearly: 'NEREDA reduces lifecycle cost by $747k/yr'",
        "Carbon note in Section 9: MABR-BNR lowest carbon but cost premium outweighs benefit",
        "NEREDA implementation score: maturity-adjusted floor — proven techs no longer penalised",
        "QA-W03 false positive fixed: only fires when methanol is genuinely required in engineering notes",
        "Driver tone: 'Clear economic advantage' label for savings >$100k/yr",
    ]),
    ("v24Z4", "19 Mar 2026", [
        "Compliance labels: 'Compliant with intervention' removed for achievability-note-only scenarios",
        "NEREDA maturity recalibrated 65→72 (100+ global reference plants, AU precedent)",
        "Trade-off in Decision Summary now references compliant runner-up only (not non-compliant options)",
        "Carbon narrative quantifies cost/carbon trade-off with carbon price threshold",
        "QA warnings surfaced in Section 9 conclusions (not just Appendix B)",
    ]),
    ("v24Z3", "19 Mar 2026", [
        "scenario.is_compliant — single source of truth stamped on ScenarioModel after every run",
        "Platform QA layer (core/decision/platform_qa.py) — 8 checks, errors/warnings/notes",
        "Intervention scenarios: ferric dosing for TP failures, methanol for TN failures",
        "Carbon decision pathway: Low-carbon profile re-ranking in every report",
        "Appendix B extended: intervention table + carbon pathway + QA status",
    ]),
    ("v24Z+1", "19 Mar 2026", [
        "Added Version & Changelog page (this page)",
        "Git commit hash shown in sidebar for instant version check",
    ]),
    ("v24Z", "19 Mar 2026", [
        "Driver text now compares preferred vs compliant runner-up (not non-compliant baseline)",
        "Driver correction applied in report_engine — affects PDF, DOCX, and page-3 box",
        "Single compliance source confirmed: all report surfaces use same compliance_flag",
    ]),
    ("v24Y", "19 Mar 2026", [
        "Score clamping 20–85: no more 0/100 binary extremes in Appendix B",
        "Decision Logic table added to Appendix B (compliance → cost → risk → close-decision)",
        "_classify_compliance_inline now reads pre-computed compliance_flag — single source",
        "Section 9 'Both scenarios achieve...' now dynamic based on compliant count",
        "Decision Summary box driven by scoring_result (single source of truth)",
    ]),
    ("v24X", "19 Mar 2026", [
        "Section 9 text: 'Both scenarios' → dynamic count of compliant options",
        "Decision Summary box overridden by scoring_result for all output formats",
        "Driver direction corrected",
    ]),
    ("v24W", "19 Mar 2026", [
        "Streamlit auto-restart on file change — app reloads automatically after git push",
        "No more stale-code reports from forgetting to restart",
    ]),
    ("v24V", "18 Mar 2026", [
        "Achievability warnings no longer block compliance recommendation",
        "Executive summary conclusion uses scoring_result preferred option",
        "Scenarios Evaluated table now populated with technology name and key characteristic",
        "Runner-up in Decision Summary prefers compliant options over non-compliant",
    ]),
    ("v24U", "18 Mar 2026", [
        "Fixed is_rec star (★) in executive summary — now compares by tech code not display label",
    ]),
    ("v24T", "18 Mar 2026", [
        "Fixed comprehensive PDF crash: TableStyle tuple error in Appendix B",
        "Removed Streamlit import from report_engine compliance check",
        "Scoring result now correctly populates in all reports",
    ]),
    ("v24S", "18 Mar 2026", [
        "Effluent Headroom removed from score table display (always zero — biological models target exactly)",
        "Rationale bullets now show raw advantage not normalised score",
        "Low-score disclosure: options scoring < 30/100 get an explanatory note",
        "Tied criteria note now shows full criterion list (no truncation)",
    ]),
    ("v24Q", "18 Mar 2026", [
        "Correlation detection suppressed for 2-scenario comparisons (eliminates 36 spurious warnings)",
        "binary_comparison flag added — recommendation notes that scores are field-relative",
        "Below-uncertainty escalation at 60%: CAUTION level added above Note level",
    ]),
    ("v24P", "18 Mar 2026", [
        "Uncertainty note decoupled from tied_criteria — now uses below_uncertainty correctly",
        "Recommendation restructured: decision / indistinguishable criteria / caveats",
        "weight_profile_name added to recommendation narrative",
        "Low-carbon profile carbon×implementation_risk anti-correlation documented",
    ]),
]


def _git_info() -> tuple[str, str, str]:
    """Return (short_hash, full_hash, commit_datetime). Returns '?' on failure."""
    try:
        short = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=ROOT, stderr=subprocess.DEVNULL, text=True).strip()
        full = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT, stderr=subprocess.DEVNULL, text=True).strip()
        dt = subprocess.check_output(
            ["git", "log", "-1", "--format=%cd", "--date=format:%d %b %Y %H:%M"],
            cwd=ROOT, stderr=subprocess.DEVNULL, text=True).strip()
        return short, full, dt
    except Exception:
        return "?", "?", "?"


def _latest_tag() -> str:
    if CHANGELOG:
        return CHANGELOG[0][0]
    return "?"


def render() -> None:
    render_page_header(
        "🔖 Version & Changelog",
        subtitle="What's currently deployed — check this before generating reports",
    )

    short_hash, full_hash, commit_dt = _git_info()
    latest_tag = _latest_tag()

    # ── Current version banner ─────────────────────────────────────────────
    st.success(
        f"**Running: {latest_tag}** · commit `{short_hash}` · deployed {commit_dt}"
    )

    col1, col2, col3 = st.columns(3)
    col1.metric("Release tag", latest_tag)
    col2.metric("Git commit", f"`{short_hash}`")
    col3.metric("Deployed", commit_dt.split(" ")[0] + " " + commit_dt.split(" ")[1]
                if commit_dt != "?" else "?")

    # ── How to verify ─────────────────────────────────────────────────────
    with st.expander("How to verify you're on the latest version", expanded=False):
        st.markdown(f"""
**1. Compare this commit hash to your local repo:**
```
cd ~/wp_new
git log --oneline -1
```
The 7-character hash should match **`{short_hash}`**.

**2. Check the sidebar** — the commit hash is shown at the bottom of the left sidebar on every page.

**3. After pushing a new bundle**, the app restarts automatically (v24W+).
Wait 3–5 seconds, then reload this page. The hash will update.

**Full commit hash:** `{full_hash}`
""")

    st.divider()

    # ── Changelog ─────────────────────────────────────────────────────────
    st.subheader("Changelog")

    for i, (tag, date, changes) in enumerate(CHANGELOG):
        is_latest = (i == 0)
        label = f"{'🟢 ' if is_latest else ''}{tag} — {date}{'  ← current' if is_latest else ''}"
        with st.expander(label, expanded=is_latest):
            for change in changes:
                st.markdown(f"- {change}")
