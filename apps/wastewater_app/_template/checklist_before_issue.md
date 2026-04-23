# Pre-Issue QA Checklist — WaterPoint Concept Study

Before issuing a concept study to a client, work through this checklist.
Any item that fails needs to be addressed before release.

## Structural

- [ ] Front matter is populated (title, revision, date, client, author)
- [ ] Revision number reflects the latest substantive change
- [ ] Change log exists and is up-to-date (if Rev 2+)
- [ ] Page numbers, headers, and footers are present
- [ ] All figures have captions; all tables have titles
- [ ] All sections are numbered consistently (no 4.8 appearing twice)

## Section 1 — Document status and scope

- [ ] Confidence level is explicitly stated (screening / pre-feasibility / detailed)
- [ ] "What this establishes" has 3-4 positive statements
- [ ] "What this does NOT establish" has 3-5 explicit exclusions
- [ ] Out-of-scope disciplines are listed (aeration, hydraulics, solids, structural, etc.)

## Section 2 — Plant background

- [ ] As-built basis document is referenced (Rev B, or equivalent)
- [ ] All zone volumes are listed with their source
- [ ] Licence limits table is present
- [ ] Diurnal profile is shown if available
- [ ] PFD of existing plant is present
- [ ] If dual licence interpretation applies, Section 2.3 covers both

## Section 3 — Modelling

- [ ] Kinetic parameters are tabulated with confidence status
- [ ] Temperature basis is stated (e.g., 17°C winter minimum)
- [ ] MLSS range is specified
- [ ] At least one sensitivity analysis is presented (the most important parameter)
- [ ] Alkalinity balance has been done (Section 3.5)
- [ ] Model limitations are listed explicitly (3.4)

## Section 4 — Scenarios

- [ ] S0 baseline is documented
- [ ] S1A is present (no-regret immediate action)
- [ ] S2 variants are each documented with:
  - [ ] Configuration description
  - [ ] PFD figure
  - [ ] Advantages (5 bullets)
  - [ ] Risks (5 bullets)
  - [ ] Capex breakdown (itemised)
- [ ] Decision tree by growth horizon is present
- [ ] No variant is labelled "recommended" — use "preferred concept for pre-feasibility development"

## Section 5 — Results

- [ ] Capacity table with binding constraints
- [ ] Effluent quality chart (TN vs EP or equivalent)
- [ ] Annual mass load framing (if relevant)
- [ ] Environmental discharge quantification (5.4 — if S2 increases mass)
- [ ] Treatment efficiency (% removal) is stated alongside total mass

## Section 6 — Risks

- [ ] Top 5-10 risks identified as F1, F2, ...
- [ ] Each risk has: title + description + mitigation + related RFC number
- [ ] Callout boxes use consistent colour (warning amber typically)

## Section 7 — Phase 2 verification package

- [ ] All material unknowns from Section 3-6 have corresponding RFCs
- [ ] Each RFC has: scope + activities + cost + timeline + priority + impact
- [ ] Stage 0 gateway items are distinguished from parallel verifications
- [ ] Conditional RFCs are flagged (only required if variant X carried forward)
- [ ] Total Phase 2 cost is summed (should be well under 5% of capex band)

## Section 8 — Recommendations

- [ ] 8.1 Immediate action is identified (the no-regret move)
- [ ] 8.2 Pre-feasibility scope is defined
- [ ] 8.4 Decision gate items are listed
- [ ] No recommendation is stronger than "preferred concept" at concept study level
- [ ] No capex commitment is implied

## Section 9 — Caveats

- [ ] Model limitations are exhaustive (5-10 items)
- [ ] Scope exclusions are exhaustive (7-10 items)
- [ ] Commercial caveats address capex confidence (5-7 items)
- [ ] Status of key statements is tagged (verified / modelled / estimated / assumed)

## Language and tone

- [ ] No marketing language or vendor claims repeated uncritically
- [ ] Capacity numbers are presented as "modelled" or "could potentially" not "will"
- [ ] Variant comparison presents trade-offs honestly (no single variant "wins" without caveats)
- [ ] Client utility is named as owning receiving water and regulator workstreams
- [ ] "Phase 2", "RFC-N", or "verify before capital" appears at every key assumption

## File integrity

- [ ] Docx validates (run validate.py)
- [ ] All images referenced in embedChart() exist at the specified paths
- [ ] PDF renders cleanly (soffice.py --convert-to pdf)
- [ ] Page count is reasonable (typically 30-40 for a complete study)
- [ ] File size is reasonable (<3 MB typically, up to 5 MB with many charts)

## WaterPoint platform integration

- [ ] Scenario model matches the report (same capacity numbers, same kinetics)
- [ ] Streamlit UI reflects the scenarios in the report
- [ ] Regression tests pass for all scenarios referenced
- [ ] If dual licence interpretation applies, the toggle works in the UI

## Final check

- [ ] A colleague other than the author has reviewed the draft
- [ ] The client's key question is answered in the executive summary
- [ ] Reading the exec summary alone gives a fair picture of the full report
- [ ] You would be comfortable defending every number in front of a regulator
