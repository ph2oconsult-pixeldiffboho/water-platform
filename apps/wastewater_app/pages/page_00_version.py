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
