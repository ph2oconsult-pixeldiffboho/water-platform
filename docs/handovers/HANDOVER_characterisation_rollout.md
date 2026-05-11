# Handover — Multi-Module Characterisation Rollout

**Date written:** 2026-05-11
**Status of the platform at handover:** Phase 5 closed out for WaterPoint; characterisation rollout to AquaPoint/PurePoint/BioPoint is the next phase of work.
**Scope of this memo:** what's been done, what the next phase is, what's required to start, and a session-by-session plan.

---

## 1. Where the platform currently stands

The water-platform repo (`github.com:ph2oconsult-pixeldiffboho/water-platform`) hosts four domain apps under `apps/`: `wastewater_app` (WaterPoint), `drinking_water_app` (AquaPoint), `prw_app` (PurePoint), `biosolids_app` (BioPoint). Shared platform code lives in `core/`.

Recent merged work on `main` (commits behind PR numbers):

| PR | Branch | What it shipped |
|---|---|---|
| #1 | `feature/phase-5-design-envelope` | `core/characteriser/` engine — six-section design envelope memo + four PNG charts |
| #2 | `feature/phase-5-item-4-streamlit` | WaterPoint Page 15 (Design Envelope) wired to the engine |
| #3 | `feature/phase-5-item-4-followup` | UX polish on Page 15 |
| #4 | `feature/hide-platform-home-cards` | Hide Platform Home content when inside a domain app |
| #5 | `fix/aquapoint-platform-home-button` | AquaPoint Home button: use correct session-state key, then `st.stop()` after `st.rerun()` |
| #6 | `feature/phase-5-item-3-input-validation` | WaterPoint input validation layer (IV-01..IV-27) |
| #7 | `feature/phase-5-item-3-followup-ui-wiring` | Wired the IV panel into WaterPoint Intelligence + credibility-layer injection |
| #8 | `feature/phase-5-item-6-user-guide` | End-user docs for Design Envelope + Input Validation |

Live on Streamlit Cloud — verified by manual testing during the session that merged #7. The IV panel renders on the WaterPoint Results page; the AquaPoint Home button works.

**Phase 5 status** (against the original seven deployment-readiness items):

- Items 1, 2, 3, 4, 6 ✅ complete
- Item 5 (performance check on a real catchment dataset) ⏸ deferred — needs a real plant dataset to run against
- Item 7 (deployment artefacts) ✅ done by way of PR merges

---

## 2. The phase that comes next

In a separate conversation the four-module brief was provided. The brief is for an **input data characterisation and evidence platform** across:

A. Wastewater
B. Water treatment
C. Recycled water
D. Biosolids

The brief is strict on product boundary. The platform is to characterise observed input data — what the data shows, what events occurred, which parameters coincide, where the evidence runs out. It must **not** recommend treatment processes, optimise operations, size equipment, simulate process response, or otherwise drift into process-design space.

The six functional areas the brief specifies are:

1. Data integrity checks
2. Dataset characterisation
3. Correlation and coincidence analysis
4. Event extraction
5. Design envelope reporting
6. Evidence limits and caveats

These map directly onto what `core/characteriser/` already implements for wastewater. So the framework exists; the rollout work is to make it multi-module.

---

## 3. The two-layer reality of WaterPoint

WaterPoint has two related features that need to be kept clearly distinct from each other when planning the rollout.

**Layer A — Design Envelope Engine (`core/characteriser/`)**

- This is what the brief is describing.
- Operates on uploaded plant time-series data.
- Produces a six-section markdown memo + four PNG charts.
- Wired into WaterPoint via Page 15 (Design Envelope).

**Layer B — Input Validation Layer (`apps/wastewater_app/input_validation_layer.py`)**

- This was built during Phase 5 in response to a different specification (the IV-XX rule table in `apps/wastewater_app/pages/page_08_manual.py`).
- Operates on the engineering scenario fields a user types into Pages 01/02 — peak flow, TN target, etc.
- Produces a panel at the top of WaterPoint Intelligence on Page 04.
- Critical flags feed the credibility layer; Very Low confidence demotes `ready_for_client`.

**The decision for the next phase: only Layer A rolls out to the other three modules.**

Layer B stays as a WaterPoint-specific product feature. It is acknowledged that some of Layer B's language (governing condition implications, VOI rationales mentioning "before sizing", IV-15 mentioning rising-main lengths) goes beyond the strict characterisation boundary of the brief — but Layer B isn't governed by that brief. Leave it as it developed.

For AquaPoint, PurePoint, BioPoint the work is **only Layer A**.

---

## 4. What the rollout actually requires

For each of the three target modules, the deliverable is feature parity with WaterPoint's Layer A — which means each gets:

| Deliverable | Wastewater equivalent | Status for the three target modules |
|---|---|---|
| Parameter dictionary (typical parameters in the brief) | Implicit in `core/characteriser/` focus list and config | **Net new — needs definition** |
| Integrity rules (INT-XX equivalents) | INT-01 through INT-05 in `integrity_checks.py` | **Net new — needs definition** |
| Ratio library | Embedded in the envelope orchestrator's ratio prioritisation | **Net new — needs definition** |
| Event rules | Referenced in `report.py`'s `EventAnalysis`; rules live elsewhere | **Net new — needs definition (note: the Phase 5 build deferred this for wastewater itself; only `first_flush` is currently rule-coded)** |
| Pre-built concerns (concern → ratio prioritisation map) | Six concerns: `peak_hydraulic`, `bnr_nitrification_stress`, etc. | **Net new — needs definition per module** |
| Caveat library | Section 6 limits in every envelope memo (currently generic) | Could remain generic; brief implies per-module library |
| Streamlit page | Page 15 in WaterPoint | **Net new — one page per module** |
| Test dataset | `Wastewater_Observed_Scenario_Extraction_Test_Dataset.xlsx` + the stress-test variant | **Net new — synthetic dataset per module** |
| Acceptance tests | The 47 tests in `tests/test_design_envelope.py` plus the rest of the 131-test Phase 5 suite | **Net new — per-module test coverage** |
| One worked example output | `phase_5/example_outputs/clean/` and `dirty/` for wastewater | **Net new — one per module** |

The shared engine (`core/characteriser/design_envelope.py`, `envelope_charts.py`, `envelope_renderer.py`) does not need rewriting. It needs to become module-aware via a registries pattern (see Section 6 below).

---

## 5. The gating piece of work — engineering rule definition

The bottleneck on this rollout is **not coding**. It is the engineering rule tables.

For WaterPoint, the IV-XX rules came pre-documented in `page_08_manual.py` with bands, severities, and field references. The build was implement-to-spec. The same will be true for the characterisation rollout — but the specs for AquaPoint, PurePoint, BioPoint do not yet exist in this form.

The brief gives us a **starting set**: typical parameters per module, typical ratios per module, typical event types per module. That's the topology. What's missing is the **thresholds**:

- For AquaPoint: at what P99 turbidity does the integrity rule flag? Above what UV254/DOC ratio is a high-DBP-formation-potential event flagged? Below what UVT is a low-UVT event detected?
- For PurePoint: what's the EC stability band that bounds a normal feed? What conductivity excursion is flagged? Below what UVT does the AOP barrier credit reduce?
- For BioPoint: what VS/TS triggers a poor-dewatering signature? What cake DS change is a step shift vs noise? What biogas yield per kg VS destroyed is the central tendency, and what's the excursion threshold?

Each module needs an equivalent of the IV-XX table — codes, fields, conditions, thresholds, severities, plain-English descriptions, caveats. The wastewater example sits in `page_08_manual.py` lines 493-537 and is the right format to mirror.

**This is engineering-judgement work, not coding work.** It can be done by whoever owns the engineering brief, working from published water-sector design references plus site-specific knowledge. Without this step, code work cannot begin for a given module.

---

## 6. Architectural proposal for the next coding session

When the rule tables are ready and coding can start, the right shape for the architecture is a **registries pattern in `core/characteriser/`**.

The existing engine is implicitly wastewater. To make it multi-module, introduce a `module` parameter to the orchestrator and a set of registries that the engine consults:

```
core/characteriser/
├── design_envelope.py        # existing — orchestrator
├── envelope_charts.py         # existing
├── envelope_renderer.py       # existing
├── integrity_checks.py        # existing — INT-XX rules, currently wastewater-flavoured
├── report.py                  # existing — schemas
├── coincidence.py             # existing — Spearman + condition matching
└── registries/                # NEW
    ├── __init__.py
    ├── parameters.py          # PARAMETER_DICTIONARIES[module] = {...}
    ├── integrity_rules.py     # INTEGRITY_RULES[module] = [INT_01, INT_02, ...]
    ├── ratio_libraries.py     # RATIO_LIBRARIES[module] = {ratio_name: definition}
    ├── event_rules.py         # EVENT_RULES[module] = [rule, rule, ...]
    ├── concerns.py            # CONCERN_RATIO_PRIORITIES[module] = {concern: [ratios]}
    └── caveats.py             # CAVEAT_LIBRARIES[module] = {scenario: text}
```

The orchestrator's signature becomes:

```python
def build_design_envelope(
    df,
    condition_spec,
    label,
    module: str = "wastewater",   # NEW — defaults preserve existing behaviour
    concern=None,
    ...
)
```

This preserves all current wastewater behaviour by default. Other modules are added by populating their entries in the registries — no engine rewrite required.

**Step ordering inside the architecture session:**

1. Define the `registries/` module structure.
2. Extract the implicit wastewater behaviour out of `integrity_checks.py` and the orchestrator into the registries, indexed by `module="wastewater"`. The existing wastewater tests must still pass unchanged after this refactor.
3. Add the `module` parameter to `build_design_envelope` and threaded through to chart/renderer where needed.
4. Add empty stub entries for `"water_treatment"`, `"recycled_water"`, `"biosolids"` so future per-module work has a clear slot to populate.
5. Run the full 131-test Phase 5 suite to confirm no regression.

That's one PR. After it merges, per-module work proceeds independently.

---

## 7. Session-by-session plan

Indicative pacing — assumes engineering rule tables are available at the start of each module's coding session.

| Session | Goal | Pre-requisite |
|---|---|---|
| **1 — Architecture** | Introduce `registries/` to `core/characteriser/`. Refactor wastewater path to live in the registries. Full test suite still passes. | None — purely architectural. |
| **2 — AquaPoint, build** | Populate water-treatment entries in all six registries. Add `apps/drinking_water_app/pages/page_NN_design_envelope.py`. Create synthetic test dataset. Add a module-specific test file. | AquaPoint engineering rule table for integrity, ratios, events, concerns. |
| **3 — AquaPoint, verify** | Real-data test if available. Live verification. Fix-ups. One worked example memo committed to `phase_5/example_outputs/water_treatment/`. | A real or synthetic AquaPoint dataset to characterise. |
| **4 — PurePoint** | Same shape as AquaPoint — should go faster because the pattern is proven. | PurePoint engineering rule table. |
| **5 — BioPoint** | Same shape. | BioPoint engineering rule table. |
| **6 — Cross-cutting** | Harmonised acceptance tests, extend the user guide to cover all four modules, one published worked example per module. Update the engineering manual page in each app to cover characterisation. | None. |

Three modules at two sessions each ≈ six sessions. Optimistic estimate; realistic if rule tables arrive cleanly and there are no architectural surprises. Bigger if either of those things drift.

---

## 8. What to do before the next coding session

In priority order:

**1. Decide which module to do first.**

Recommendation: **AquaPoint**. Reasons: you've been actively working on it (recent commits show coagulation, softening, calibration work); its input class `SourceWaterInputs` is already in place; the water-treatment literature has the most readily-available rule documentation (P99 turbidity, USEPA LRV credits, NHMRC ADWG bands).

**2. Author the AquaPoint engineering rule table.**

Format it like `page_08_manual.py` lines 493-537. The brief gives the topology (parameters, ratios, events). The table needs to fill in the bands. A first cut can be rough — "AV-01: turbidity_p99_ntu, Warning if > 50, Critical if > 200" — and refined as it's reviewed.

The brief's typical-parameter list for water treatment includes 26 parameters. Not every one needs an INT-class rule; only those where physical impossibility or out-of-band excursion is possible. Probably 15-20 rules total for AquaPoint, roughly matching the IV-XX count for wastewater.

Same for ratios: the brief lists 12 ratio relationships for water treatment; not every one needs to be in the diagnostic priority library. Pick the ones that are diagnostic for the pre-built concerns.

Pre-built concerns for water treatment — the brief implies several but doesn't list them by name. Plausible candidates:

- `high_turbidity_event` — sizing the coagulation/clarification stage
- `algal_bloom` — taste/odour, filterability stress
- `cyanobacterial_event` — cyanotoxin risk markers
- `high_doc` — DBP formation precursors, ozone/GAC stress
- `low_uvt` — UV disinfection performance bound
- `cold_water_event` — coagulation efficiency, biological filter performance

Six concerns matches the wastewater count, which felt right in practice. Could be more or fewer; rule of thumb is "one concern per binding-condition question the engineer needs the data to answer."

**3. Provide a test dataset for AquaPoint.**

Synthetic is fine for the build session. The wastewater build used a 1096-row synthetic dataset with known injection points for stress testing. Same pattern works here — a year of daily samples covering raw water turbidity, UV254, DOC, pH, temperature, plus the optional algae markers, with a deliberate high-turbidity event embedded for the orchestrator to extract.

If you have a real plant dataset that could be sanitised and committed, that's better.

**4. (Optional, for momentum) Sketch the PurePoint and BioPoint rule tables in parallel.**

The brief gives a strong starting set for both. Drafting them ahead of time means sessions 4 and 5 aren't gated on engineering work.

---

## 9. What not to do

A few traps worth naming.

**Do not port the WaterPoint IV layer to the other three modules.** That layer is governed by a different specification (the IV-XX framework which goes into process-implication territory). The brief for the rollout is strict on the characterisation boundary — observed data only, no recommendations. Porting IV-style logic to AquaPoint/PurePoint/BioPoint would violate the brief.

**Do not modify or extend the existing DIL modules** (`apps/drinking_water_app/engine/dil_aquapoint.py`, `apps/biosolids_app/engine/dil_biosolids.py`, and PurePoint's `decision_spine.py`) as part of this work. DIL is the *post-characterisation* decision-intelligence layer — distinct concern, distinct lifecycle. The rollout adds *upstream* of DIL, not into it.

**Do not unify `core/validation/validation_engine.py` with the IV layer scaffolding.** They serve different purposes and have different consumers. The existing `validation_engine.py` is for hook-based domain validation in the project-model context. The IV layer's `IVFlag`/`InputValidationReport` is for the WaterPoint product feature. Leaving them parallel is correct.

**Do not start coding the characterisation rollout before the rule tables are drafted.** It looks tempting because the architecture is straightforward — but the engine cannot fire useful rules without bands, and inventing bands during a coding session produces poorly-calibrated rules that are hard to revisit. Document first, code second.

---

## 10. Open items carried forward from Phase 5

These are unrelated to the rollout but worth keeping visible.

- **Phase 5 item 5** — performance check on a real catchment dataset for the design envelope engine. Synthetic data runs in ~3s; real data with 30+ parameters and 5+ years is unmeasured. Deferred until a real dataset is available.

- **Wastewater event rules beyond first-flush** — the Phase 5 README explicitly notes that only `first_flush` is currently rule-coded for event detection. The other event types the brief lists (septicity, low-carbon/high-ammonia, weekend regime, etc.) are referenced in `report.py` comments but not implemented. Worth catching up when the per-module event rule libraries are being built — the AquaPoint event detector code will be a natural companion to a more complete WaterPoint event detector.

- **Stub `coincidence.py` and `config_schema.py`** in `core/characteriser/` from the Phase 5 build. The handover at the time noted these were stubs with real (not mocked) implementations standing in for production modules that likely live elsewhere in the repo. Worth searching for `analyse_coincidence` and `CharacterisationConfig` in production code at some point — the stubs are passing all 16 contract tests but they're stubs.

- **User guide extensibility** — `docs/user_guides/design_envelope_and_validation.md` (merged this session) covers the wastewater rollout. After modules 2-4 are built it'll need additions or splitting into per-module guides.

---

## 11. Quick orientation for whoever picks this up

Most important files for the next coding session:

- `core/characteriser/design_envelope.py` — the orchestrator, ~640 lines. The `build_design_envelope` function is where the `module` parameter will be added.
- `core/characteriser/integrity_checks.py` — INT-XX rules, ~26 KB. The wastewater-specific bits to extract into the registries are here.
- `core/characteriser/report.py` — the dataclass schemas. Mostly module-agnostic; minor additions may be needed.
- `apps/wastewater_app/pages/page_15_design_envelope.py` — the template Streamlit page. The three new pages will mirror this.
- `apps/wastewater_app/pages/page_08_manual.py` lines 493-537 — the format for the engineering rule tables that the other three modules need to author.
- `docs/user_guides/design_envelope_and_validation.md` — the format and tone for end-user documentation.

The first thing the next coding session should do is read the brief in full, this memo in full, and then `git log --oneline -20` to confirm nothing has changed on `main` since this memo was written.

---

## 12. Contact points and conventions

Branch naming convention from recent history:

- `feature/<descriptive-name>` for new functionality
- `fix/<descriptive-name>` for bug fixes
- One PR per logical unit of work
- Squash-or-merge has not been consistent; recent merges have been "Merge pull request" (preserves history), keep that consistent
- PRs are descriptive — title summarises the change, body explains the reasoning and links any specs

Test suite invocation:

```
cd ~/wp_new
python3 run_tests.py --fast
# Currently 13 test files passing, plus 7 from Phase 5, plus item-3 module
```

Streamlit local entry point:

```
streamlit run apps/main_app.py
```

Streamlit Cloud deploys from `main` automatically, ~1-2 minutes after a merge.

---

This memo is the starting point for the next conversation. The conversation that wrote it can be referenced if context is needed but it should not be re-read in full — the architectural conclusions are summarised here.
