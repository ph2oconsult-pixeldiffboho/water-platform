"""
tests/domains/wastewater/test_decision_engine.py

Decision Engine Test Suite
===========================
Tests for the capital planning decision engine, covering:
  - Selection hierarchy (compliance → cost → risk)
  - New ScenarioDecision fields
  - Alternative pathway generation
  - Client decision framing
  - Recommendation confidence
  - Internal consistency (no contradictions)

Run standalone: python3 tests/domains/wastewater/test_decision_engine.py
"""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from core.assumptions.assumptions_manager import AssumptionsManager
from core.project.project_model import DomainType, ScenarioModel, TreatmentPathway
from domains.wastewater.domain_interface import WastewaterDomainInterface
from domains.wastewater.input_model import WastewaterInputs
from domains.wastewater.decision_engine import (
    evaluate_scenario, _build_profile, _TECH_LABELS,
    AlternativePathway, ClientDecisionFraming, RecommendationConfidence,
    ScenarioDecision, Rating,
)
from tests.benchmark.scenarios import get_by_id, to_inputs_dict
from tests.benchmark.conftest import run_scenario_tech, base_assumptions as mk_a


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_scenarios(tech_list, inputs, base_a=None):
    """Build a list of ScenarioModels for evaluate_scenario()."""
    if base_a is None:
        base_a = mk_a()
    iface = WastewaterDomainInterface(base_a)
    scenarios = []
    for tech in tech_list:
        calc = iface.run_scenario(inputs, [tech], {})
        label = _TECH_LABELS.get(tech, tech)
        sc = ScenarioModel(scenario_name=label)
        sc.treatment_pathway = TreatmentPathway(
            pathway_name=tech, technology_sequence=[tech],
            technology_parameters={})
        sc.domain_inputs = {
            k: getattr(inputs, k)
            for k in inputs.__dataclass_fields__
            if not k.startswith("_")
        }
        iface.update_scenario_model(sc, calc)
        scenarios.append(sc)
    return scenarios


# ── Test classes ──────────────────────────────────────────────────────────────

passed = failed = 0
failures = []

def chk(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  ✅ {name}")
    else:
        failed += 1
        failures.append((name, detail))
        print(f"  ❌ {name}" + (f"  [{detail[:90]}]" if detail else ""))


class TestSelectionHierarchy:
    """
    COMPLIANCE → COST → RISK must be strictly enforced.
    The cheapest option must not win if it fails compliance.
    """

    def test_sole_compliant_wins_despite_higher_cost(self):
        """S2: only MABR passes NH4<3 at 12°C — must be recommended despite 67% LCC premium."""
        s2 = get_by_id("S2")
        inp = WastewaterInputs(**to_inputs_dict(s2))
        scenarios = _make_scenarios(s2.technologies, inp)
        d = evaluate_scenario(scenarios, inp)
        chk("S2 MABR recommended as sole compliant",
            d.recommended_tech == "mabr_bnr",
            f"got {d.recommended_tech}")

    def test_sole_compliant_selection_basis_label(self):
        """selection_basis must explicitly name compliance as the driver."""
        s2 = get_by_id("S2")
        inp = WastewaterInputs(**to_inputs_dict(s2))
        scenarios = _make_scenarios(s2.technologies, inp)
        d = evaluate_scenario(scenarios, inp)
        chk("S2 selection_basis mentions compliance",
            "compliant" in d.selection_basis.lower(),
            d.selection_basis)

    def test_noncompliant_in_non_viable(self):
        """All scenarios that fail compliance must appear in non_viable."""
        s2 = get_by_id("S2")
        inp = WastewaterInputs(**to_inputs_dict(s2))
        scenarios = _make_scenarios(s2.technologies, inp)
        d = evaluate_scenario(scenarios, inp)
        chk("S2 non_viable list non-empty",
            len(d.non_viable) >= 3,
            f"non_viable={d.non_viable}")

    def test_why_recommended_does_not_say_lower_risk_for_sole_compliant(self):
        """CRITICAL: why_recommended must not say 'offset by lower risk' when selection is compliance-forced."""
        s2 = get_by_id("S2")
        inp = WastewaterInputs(**to_inputs_dict(s2))
        scenarios = _make_scenarios(s2.technologies, inp)
        d = evaluate_scenario(scenarios, inp)
        contradiction = any("offset by lower risk" in w.lower() for w in d.why_recommended)
        chk("S2 no 'offset by lower risk' contradiction",
            not contradiction,
            f"why_recommended={d.why_recommended}")

    def test_why_recommended_acknowledges_compliance_forcing(self):
        """why_recommended must explicitly acknowledge compliance forces the selection."""
        s2 = get_by_id("S2")
        inp = WastewaterInputs(**to_inputs_dict(s2))
        scenarios = _make_scenarios(s2.technologies, inp)
        d = evaluate_scenario(scenarios, inp)
        compliance_acknowledged = any(
            any(w in reason.lower() for w in ["compliant", "compliance", "non-negotiable"])
            for reason in d.why_recommended
        )
        chk("S2 why_recommended acknowledges compliance forcing",
            compliance_acknowledged,
            f"why_recommended={d.why_recommended}")

    def test_competitive_selection_uses_lcc(self):
        """S1: all options compliant — lowest LCC should win."""
        s1 = get_by_id("S1")
        inp = WastewaterInputs(**to_inputs_dict(s1))
        scenarios = _make_scenarios(s1.technologies, inp)
        d = evaluate_scenario(scenarios, inp)
        # Find actual lowest LCC among non-non-viable
        viable = [s for s in scenarios if s.scenario_name not in d.non_viable]
        if viable:
            lowest_lcc = min(viable, key=lambda s: s.cost_result.lifecycle_cost_annual)
            chk("S1 lowest LCC recommended among compliant",
                d.recommended_label == lowest_lcc.scenario_name,
                f"recommended={d.recommended_label} lowest={lowest_lcc.scenario_name}")
        else:
            chk("S1 has viable options", False, "no viable options found")

    def test_cost_over_risk_when_both_compliant(self):
        """When two options are compliant, lower LCC wins even if higher risk."""
        # S7 sludge scenario: AGS has higher risk (28.4) but lower LCC — should win
        s7 = get_by_id("S7")
        inp = WastewaterInputs(**to_inputs_dict(s7))
        scenarios = _make_scenarios(["bnr", "granular_sludge"], inp)
        d = evaluate_scenario(scenarios, inp)
        bnr_lcc  = next(s for s in scenarios if "BNR" in s.scenario_name and "Granular" not in s.scenario_name).cost_result.lifecycle_cost_annual
        ags_lcc  = next(s for s in scenarios if "Granular" in s.scenario_name).cost_result.lifecycle_cost_annual
        expected = "Aerobic Granular Sludge" if ags_lcc < bnr_lcc else "BNR (Activated Sludge)"
        chk("S7 cost drives selection between compliant options",
            d.recommended_label == expected,
            f"recommended={d.recommended_label} expected={expected}")


class TestNewDecisionFields:
    """All new ScenarioDecision fields must be present and well-formed."""

    def _get_s2_decision(self):
        s2 = get_by_id("S2")
        inp = WastewaterInputs(**to_inputs_dict(s2))
        scenarios = _make_scenarios(s2.technologies, inp)
        return evaluate_scenario(scenarios, inp)

    def test_selection_basis_field_present(self):
        d = self._get_s2_decision()
        chk("selection_basis field present and non-empty",
            hasattr(d, "selection_basis") and bool(d.selection_basis),
            f"selection_basis={getattr(d, 'selection_basis', 'MISSING')}")

    def test_regulatory_note_field_present(self):
        d = self._get_s2_decision()
        chk("regulatory_note field present",
            hasattr(d, "regulatory_note"),
            "regulatory_note attribute missing")

    def test_regulatory_note_explains_low_confidence(self):
        """When regulatory confidence is Low, the note must explain why it doesn't block the rec."""
        d = self._get_s2_decision()
        note = getattr(d, "regulatory_note", "")
        chk("regulatory_note explains low conf doesn't block recommendation",
            "not prevent" in note.lower() or "non-negotiable" in note.lower() or "takes precedence" in note.lower(),
            f"note={note[:100]}")

    def test_alternative_pathways_field_present(self):
        d = self._get_s2_decision()
        chk("alternative_pathways field present",
            hasattr(d, "alternative_pathways"),
            "alternative_pathways missing")

    def test_alternative_pathways_generated_for_cold_scenario(self):
        """S2 cold scenario: BNR+thermal pathway must be generated."""
        d = self._get_s2_decision()
        paths = getattr(d, "alternative_pathways", [])
        chk("S2 has at least one alternative pathway",
            len(paths) >= 1,
            f"got {len(paths)}")

    def test_alternative_pathway_achieves_compliance(self):
        """The BNR+thermal pathway must report achieves_compliance=True."""
        d = self._get_s2_decision()
        paths = getattr(d, "alternative_pathways", [])
        if paths:
            chk("BNR+thermal pathway achieves compliance",
                any(p.achieves_compliance for p in paths),
                f"compliant flags: {[p.achieves_compliance for p in paths]}")
        else:
            chk("alternative pathways exist", False, "no pathways")

    def test_alternative_pathway_lcc_lower_than_mabr(self):
        """BNR+thermal must be cheaper LCC than MABR."""
        s2 = get_by_id("S2")
        inp = WastewaterInputs(**to_inputs_dict(s2))
        scenarios = _make_scenarios(s2.technologies, inp)
        d = evaluate_scenario(scenarios, inp)
        mabr_lcc = next(
            s.cost_result.lifecycle_cost_annual
            for s in scenarios
            if s.scenario_name == d.recommended_label
        )
        paths = getattr(d, "alternative_pathways", [])
        if paths:
            best_path_lcc = min(p.lcc_total_k for p in paths) * 1000
            chk("BNR+thermal LCC < MABR LCC",
                best_path_lcc < mabr_lcc,
                f"pathway={best_path_lcc/1e3:.0f}k MABR={mabr_lcc/1e3:.0f}k")
        else:
            chk("alternative pathway exists", False, "none found")

    def test_client_framing_generated_when_alt_pathway_exists(self):
        """client_framing must be populated when sole-compliant + alternative pathway."""
        d = self._get_s2_decision()
        cf = getattr(d, "client_framing", None)
        chk("client_framing present for S2",
            cf is not None,
            "client_framing is None")

    def test_client_framing_has_two_options(self):
        d = self._get_s2_decision()
        cf = getattr(d, "client_framing", None)
        if cf:
            chk("client_framing has option_a_label",
                bool(cf.option_a_label))
            chk("client_framing has option_b_label",
                bool(cf.option_b_label))
            chk("client_framing has deciding_factors",
                len(cf.deciding_factors) >= 3,
                f"got {len(cf.deciding_factors)}")
        else:
            chk("client_framing fields", False, "cf is None")

    def test_confidence_field_present(self):
        d = self._get_s2_decision()
        conf = getattr(d, "confidence", None)
        chk("confidence field present",
            conf is not None,
            "confidence is None")

    def test_confidence_level_valid(self):
        d = self._get_s2_decision()
        conf = getattr(d, "confidence", None)
        if conf:
            chk("confidence.level is High/Moderate/Low",
                conf.level in ("High", "Moderate", "Low"),
                f"level={conf.level}")
        else:
            chk("confidence present", False, "None")

    def test_confidence_has_drivers_and_caveats(self):
        d = self._get_s2_decision()
        conf = getattr(d, "confidence", None)
        if conf:
            chk("confidence has at least one driver",
                len(conf.drivers) >= 1,
                f"drivers={conf.drivers}")
            chk("confidence has at least one caveat",
                len(conf.caveats) >= 1,
                f"caveats={conf.caveats}")
        else:
            chk("confidence present", False, "None")

    def test_sole_compliant_confidence_is_moderate(self):
        """MABR as sole compliant with novel tech should be Moderate, not High."""
        d = self._get_s2_decision()
        conf = getattr(d, "confidence", None)
        if conf:
            chk("S2 MABR confidence is not High (novel tech)",
                conf.level in ("Moderate", "Low"),
                f"level={conf.level}")
        else:
            chk("confidence present", False, "None")


class TestTradeoffLanguage:
    """Trade-offs must be decision-driving, not merely descriptive."""

    def test_sole_compliant_tradeoff_explains_cost_premium(self):
        """When sole compliant costs more, trade-offs must say the premium is compliance-driven."""
        s2 = get_by_id("S2")
        inp = WastewaterInputs(**to_inputs_dict(s2))
        scenarios = _make_scenarios(s2.technologies, inp)
        d = evaluate_scenario(scenarios, inp)
        # At least one trade-off should mention non-compliant status
        noncompliant_mentioned = any(
            "non-compliant" in t.lower() or "compliance" in t.lower()
            for t in d.trade_offs
        )
        chk("trade-offs mention non-compliant status",
            noncompliant_mentioned,
            f"trade_offs={d.trade_offs[:1]}")

    def test_competitive_tradeoff_is_specific(self):
        """S1 trade-offs should include dollar amounts."""
        s1 = get_by_id("S1")
        inp = WastewaterInputs(**to_inputs_dict(s1))
        scenarios = _make_scenarios(s1.technologies, inp)
        d = evaluate_scenario(scenarios, inp)
        has_dollar = any("$" in t for t in d.trade_offs)
        chk("S1 trade-offs include dollar amounts",
            has_dollar,
            f"trade_offs={d.trade_offs[:1]}")


class TestEdgeCases:
    """Empty input and single-scenario edge cases."""

    def test_empty_scenarios_returns_graceful_result(self):
        inp = WastewaterInputs(design_flow_mld=10)
        d = evaluate_scenario([], inp)
        chk("empty scenarios: decision produced",
            d is not None)
        chk("empty scenarios: conclusion non-empty",
            bool(d.conclusion))

    def test_single_scenario_no_trade_offs(self):
        s1 = get_by_id("S1")
        inp = WastewaterInputs(**to_inputs_dict(s1))
        scenarios = _make_scenarios(["bnr"], inp)
        d = evaluate_scenario(scenarios, inp)
        chk("single scenario: recommended set",
            bool(d.recommended_tech))
        chk("single scenario: no trade-offs",
            len(d.trade_offs) == 0,
            f"trade_offs={d.trade_offs}")

    def test_all_scenarios_same_tech_returns_first(self):
        """Duplicate technologies should not crash."""
        s1 = get_by_id("S1")
        inp = WastewaterInputs(**to_inputs_dict(s1))
        scenarios = _make_scenarios(["bnr", "bnr"], inp)
        d = evaluate_scenario(scenarios, inp)
        chk("duplicate tech: no crash", d is not None)


class TestProfileCompleteness:
    """Every profile must have all 6 decision components."""

    def test_all_s1_profiles_complete(self):
        s1 = get_by_id("S1")
        inp = WastewaterInputs(**to_inputs_dict(s1))
        scenarios = _make_scenarios(s1.technologies, inp)
        d = evaluate_scenario(scenarios, inp)
        for name, profile in d.profiles.items():
            chk(f"{name}/delivery.recommended_model",
                bool(profile.delivery.recommended_model))
            chk(f"{name}/constructability.overall",
                profile.constructability.overall is not None)
            chk(f"{name}/staging.stages non-empty",
                len(profile.staging.stages) >= 1)
            chk(f"{name}/ops_complexity.overall",
                profile.ops_complexity.overall is not None)
            chk(f"{name}/failure_modes.critical_note",
                bool(profile.failure_modes.critical_note))
            chk(f"{name}/regulatory.overall",
                profile.regulatory.overall in list(Rating))

    def test_build_profile_all_techs(self):
        for tech in ["bnr", "granular_sludge", "mabr_bnr", "bnr_mbr", "ifas_mbbr"]:
            p = _build_profile(tech, 10.0, 1200.0)
            chk(f"_build_profile/{tech}/complete",
                all([p.delivery, p.constructability, p.staging,
                     p.ops_complexity, p.failure_modes, p.regulatory]),
                f"tech={tech}")


class TestInternalConsistency:
    """No field should contradict another."""

    def test_sole_compliant_conclusion_mentions_alternative(self):
        """When a cheaper alternative pathway exists, the conclusion must mention it."""
        s2 = get_by_id("S2")
        inp = WastewaterInputs(**to_inputs_dict(s2))
        scenarios = _make_scenarios(s2.technologies, inp)
        d = evaluate_scenario(scenarios, inp)
        paths = getattr(d, "alternative_pathways", [])
        if paths and any(p.achieves_compliance for p in paths):
            chk("conclusion mentions cheaper alternative pathway",
                any(w in d.conclusion.lower()
                    for w in ["alternative", "bnr", "lower", "cheaper"]),
                f"conclusion={d.conclusion[:100]}")
        else:
            chk("alternative pathway exists for consistency check", False, "no paths")

    def test_regulatory_note_present_when_confidence_low(self):
        """If confidence is Moderate/Low, regulatory_note should be non-trivial."""
        s2 = get_by_id("S2")
        inp = WastewaterInputs(**to_inputs_dict(s2))
        scenarios = _make_scenarios(s2.technologies, inp)
        d = evaluate_scenario(scenarios, inp)
        conf = getattr(d, "confidence", None)
        note = getattr(d, "regulatory_note", "")
        if conf and conf.level in ("Moderate", "Low"):
            chk("regulatory_note present when confidence is not High",
                len(note) > 30,
                f"note length={len(note)}")

    def test_non_viable_are_not_recommended_when_viable_exist(self):
        """When viable options exist, the recommended must not be in non_viable."""
        for sid in ["S1", "S2", "S3"]:
            s = get_by_id(sid)
            inp = WastewaterInputs(**to_inputs_dict(s))
            scenarios = _make_scenarios(s.technologies, inp)
            d = evaluate_scenario(scenarios, inp)
            chk(f"{sid} recommended not in non_viable",
                d.recommended_label not in d.non_viable,
                f"recommended={d.recommended_label} non_viable={d.non_viable}")

    def test_all_non_viable_selection_basis_says_so(self):
        """S5: all options fail compliance — selection_basis must explicitly state this."""
        s5 = get_by_id("S5")
        inp = WastewaterInputs(**to_inputs_dict(s5))
        scenarios = _make_scenarios(s5.technologies, inp)
        d = evaluate_scenario(scenarios, inp)
        all_nv = all(s.scenario_name in d.non_viable for s in scenarios)
        if all_nv:
            chk("S5 all-non-viable: selection_basis flags the situation",
                "no compliant" in d.selection_basis.lower() or "reference only" in d.selection_basis.lower(),
                f"selection_basis={d.selection_basis[:80]}")
        else:
            chk("S5 recommended not in non_viable (partial compliance)",
                d.recommended_label not in d.non_viable,
                f"recommended={d.recommended_label} non_viable={d.non_viable}")




class TestTwoPathwayScenario:
    """
    When a sole-compliant technology has a viable alternative pathway,
    the engine must correctly reframe the decision as two compliant options.
    This is the critical improvement from single-pathway to dual-pathway framing.
    """

    def _get_s2_decision(self):
        s2 = get_by_id("S2")
        inp = WastewaterInputs(**to_inputs_dict(s2))
        scenarios = _make_scenarios(s2.technologies, inp)
        return evaluate_scenario(scenarios, inp)

    def test_two_pathway_selection_basis(self):
        """selection_basis must say 'two compliant pathways', not 'sole compliant'."""
        d = self._get_s2_decision()
        chk("two-pathway basis: 'two compliant' in selection_basis",
            "two compliant" in d.selection_basis.lower(),
            f"selection_basis='{d.selection_basis}'")

    def test_sole_compliant_removed_from_selection_basis(self):
        """'sole compliant' must be gone when alt pathway achieves compliance."""
        d = self._get_s2_decision()
        chk("'sole' gone from two-pathway selection_basis",
            "sole" not in d.selection_basis.lower(),
            f"selection_basis='{d.selection_basis}'")

    def test_why_recommended_reflects_two_pathways(self):
        """why_recommended must acknowledge both pathways exist."""
        d = self._get_s2_decision()
        combined = " ".join(d.why_recommended).lower()
        chk("why_recommended mentions parallel evaluation or both pathways",
            any(w in combined for w in ["parallel", "both pathway", "two pathway",
                                         "alternative pathway", "evaluate both"]),
            f"why_recommended={d.why_recommended[:1]}")

    def test_strategic_insight_populated(self):
        """strategic_insight must be populated for two-pathway scenario."""
        d = self._get_s2_decision()
        chk("strategic_insight populated",
            bool(d.strategic_insight) and len(d.strategic_insight) > 50,
            f"strategic_insight='{d.strategic_insight[:50]}'")

    def test_strategic_insight_frames_intensification_vs_robustness(self):
        """strategic_insight must frame the process intensification vs robustness distinction."""
        d = self._get_s2_decision()
        si = d.strategic_insight.lower()
        chk("strategic_insight mentions intensification",
            "intensif" in si,
            f"strategic_insight[:100]='{d.strategic_insight[:100]}'")
        chk("strategic_insight mentions robustness or conventional",
            "robust" in si or "conventional" in si,
            f"strategic_insight[:100]='{d.strategic_insight[:100]}'")

    def test_recommended_approach_populated(self):
        """recommended_approach must contain parallel evaluation steps."""
        d = self._get_s2_decision()
        chk("recommended_approach has steps",
            len(d.recommended_approach) >= 3,
            f"len={len(d.recommended_approach)}")

    def test_recommended_approach_includes_parallel_eval(self):
        """recommended_approach must include parallel concept design language."""
        d = self._get_s2_decision()
        combined = " ".join(d.recommended_approach).lower()
        chk("recommended_approach includes parallel evaluation",
            "parallel" in combined or "both pathway" in combined,
            f"steps={d.recommended_approach[:2]}")

    def test_recommended_approach_includes_no_premature_lock_in(self):
        """recommended_approach must not commit to one technology prematurely."""
        d = self._get_s2_decision()
        combined = " ".join(d.recommended_approach).lower()
        chk("recommended_approach avoids premature lock-in language",
            "lock" not in combined or "lock-in" in combined,
            "contains lock-in language")

    def test_client_framing_option_b_capex_accurate(self):
        """Option B CAPEX must reflect BNR base + intervention, not MABR CAPEX."""
        d = self._get_s2_decision()
        if d.client_framing:
            capex_bullets = [b for b in d.client_framing.option_b_bullets
                             if "CAPEX" in b or ("$" in b and "M" in b)]
            chk("Option B CAPEX bullet exists", len(capex_bullets) >= 1,
                f"bullets={d.client_framing.option_b_bullets}")
            if capex_bullets:
                # BNR+thermal should be ~$8M, definitely not $11-12M (MABR range)
                capex_str = capex_bullets[0]
                has_approx_8m = any(f"${v}" in capex_str
                                    for v in ["7.", "8.", "8.0", "8.1", "8.2"])
                chk("Option B CAPEX is ~$8M (not $12M MABR range)",
                    has_approx_8m,
                    f"capex_bullet='{capex_str}'")
        else:
            chk("client_framing exists", False, "no client_framing")

    def test_framing_note_about_how_compliance_achieved(self):
        """framing_note must frame the decision as HOW compliance is achieved, not whether."""
        d = self._get_s2_decision()
        if d.client_framing:
            fn = d.client_framing.framing_note.lower()
            chk("framing_note says 'how compliance is achieved'",
                "how compliance is achieved" in fn,
                f"framing_note='{d.client_framing.framing_note[:100]}'")
            chk("framing_note no longer says 'not about compliance'",
                "not about compliance" not in fn,
                f"framing_note contains 'not about compliance'")
        else:
            chk("client_framing exists", False, "no client_framing")

    def test_conclusion_mentions_two_pathways(self):
        """Conclusion must reflect the two-pathway reality."""
        d = self._get_s2_decision()
        chk("conclusion mentions two pathways",
            "two compliant" in d.conclusion.lower()
            or "two pathway" in d.conclusion.lower(),
            f"conclusion='{d.conclusion[:100]}'")

    def test_no_sole_compliant_contradiction(self):
        """Conclusion must not contradict selection_basis with 'sole compliant' language."""
        d = self._get_s2_decision()
        chk("no 'sole option that meets compliance' contradiction in conclusion",
            "sole option that meets compliance as modelled" not in d.conclusion,
            f"conclusion contains contradictory sole-compliant language")

    def test_competitive_scenario_no_strategic_insight(self):
        """S1 (all compliant, competitive) should NOT get strategic_insight — not needed."""
        s1 = get_by_id("S1")
        inp = WastewaterInputs(**to_inputs_dict(s1))
        scenarios = _make_scenarios(s1.technologies, inp)
        d = evaluate_scenario(scenarios, inp)
        # strategic_insight only generated for two-pathway situations
        # S1 may or may not have it depending on whether there are alt pathways
        # The key check: if no alt pathways, no strategic_insight
        if not d.alternative_pathways:
            chk("S1 no alt paths → no strategic_insight",
                not d.strategic_insight,
                f"unexpected strategic_insight: '{d.strategic_insight[:50]}'")
        else:
            chk("S1 competitive selection basis is LCC-based",
                "lifecycle cost" in d.selection_basis.lower()
                or "compliant" in d.selection_basis.lower(),
                f"selection_basis='{d.selection_basis}'")


# ── Runner ────────────────────────────────────────────────────────────────────

def run_all():
    global passed, failed
    classes = [
        TestSelectionHierarchy,
        TestNewDecisionFields,
        TestTwoPathwayScenario,
        TestTradeoffLanguage,
        TestEdgeCases,
        TestProfileCompleteness,
        TestInternalConsistency,
    ]
    for cls in classes:
        print(f"\n  {cls.__name__}")
        obj = cls()
        for name in [m for m in dir(obj) if m.startswith("test_")]:
            try:
                getattr(obj, name)()
            except Exception as e:
                failed += 1
                failures.append((f"{cls.__name__}.{name}", str(e)))
                print(f"  ❌ {name}  [EXCEPTION: {str(e)[:80]}]")


if __name__ == "__main__":
    print("=" * 60)
    print("  DECISION ENGINE TEST SUITE")
    print("=" * 60)
    run_all()
    print()
    print("=" * 60)
    total = passed + failed
    print(f"  RESULTS: {passed}/{total} passed  ({failed} failed)")
    if failures:
        print("\n  FAILURES:")
        for name, detail in failures:
            print(f"    ❌ {name}")
            if detail:
                print(f"       {detail[:100]}")
    else:
        print("  ✅ ALL DECISION ENGINE TESTS PASSED")
    print("=" * 60)
    sys.exit(0 if failed == 0 else 1)
