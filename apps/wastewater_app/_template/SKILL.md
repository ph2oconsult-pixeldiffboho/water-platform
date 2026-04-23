# WaterPoint Concept Study Report — Drafting Skill

## When to use this template

Use this template when ph2o Consulting needs to produce a **screening-level
wastewater treatment plant intensification concept study**. Typical triggers:

- "Build me a concept study for [plant name] intensification"
- "We need a Rev 1 concept study to support a pre-feasibility phase"
- "Client needs a capacity assessment and intensification pathway"
- "Bidding on a concept study — what's our standard format?"

Do NOT use this template for:
- Detailed design reports (different level of rigour required)
- Environmental impact assessments (different audience and scope)
- Tender submissions or proposals (different commercial positioning)
- O&M manuals or operational procedures (different purpose)

## The template philosophy

Every section of this report template exists to serve three core commitments:

### Commitment 1 — Honest about confidence

Every claim in the report has one of four statuses:
- **Verified** — backed by site measurement, vendor data, or design report
- **Modelled** — produced by the process model with stated kinetic assumptions
- **Estimated** — calculated from standard engineering relationships
- **Assumed** — taken on faith from typical industry values

Section 9 explicitly tags the status of each key statement. Don't let verified
language bleed into modelled or assumed territory.

### Commitment 2 — Separate what we establish from what we don't

Section 1 (Document status and scope) and Section 9 (Caveats) bracket the
report with explicit statements of what's in-scope and what's excluded.

Default excluded disciplines (state explicitly unless we've done them):
- Inlet works and flow hydraulics
- Aeration blower capacity and alpha-factor
- Solids handling (WAS production, dewatering, biosolids)
- Structural (tank integrity, wall removal)
- Electrical and instrumentation (MCC, VSD sizing)
- Phosphorus compliance
- Receiving water assessment (always QUU/utility workstream)

### Commitment 3 — Equip the client for the next phase

The point of a concept study is not to tell the client what to do. It's to
arm them for an informed decision. Every report produces:
- Decision tree by growth horizon (not a single "recommendation")
- Phase 2 verification workstream (RFC-01 through RFC-N) with cost + timeline
- Decision gate items that must close before capital commitment
- Both-interpretations framing for regulatory uncertainty

## Report structure

### Section 0: Title and front matter

- Title: "[Plant name] Intensification Concept Study"
- Revision marker: "Rev N" (start at Rev 1, increment with substantive changes)
- Date, client name, author
- Document control box (revision history)

### Section 1: Document status and scope

Must contain:
- Confidence level subsection ("Screening-level process modelling...")
- What this document establishes (3-4 bullets, positive statements)
- What this document does NOT establish (3-5 bullets, explicit exclusions)

### Section 2: Plant background and baseline

- 2.1 As-built process configuration (reference Rev B or equivalent)
- 2.2 Licence limits (concentration + mass, as a table)
- 2.3 Mass load basis (if dual interpretation applies — see Canungra template)
- 2.4 Diurnal loading profile (if known)
- 2.5 PFD of existing plant (Rev B style)
- 2.6 Alternating operating modes (if applicable)

### Section 3: Modelling approach and limitations

- 3.1 Process kinetics (Bardenpho, MLE, A²O, etc. — whichever applies)
- 3.2 Kinetic parameters (as a table with confidence status)
- 3.3 Sensitivity analysis on most important parameter(s)
- 3.4 Other model limitations (steady-state, single-temperature, etc.)
- 3.5 Alkalinity balance (always include — it's usually the hidden constraint)
- 3.6 IFAS sensitivity if applicable

### Section 4: Intensification scenarios

Standard scenario hierarchy:
- 4.1 S1A — Controls and operational upgrades (no civil, no-regret immediate)
- 4.2 S1B — Intermediate technology step (e.g., IFAS, if applicable)
- 4.3 S2 introduction — intensification pathway with variants
- 4.4+ Individual S2 variants (A, B, C, D, E as appropriate)

Each S2 variant gets:
- Configuration bullet list
- PFD figure (Rev B visual style — see canungra pfds_v2/ for examples)
- Advantages (5 bullets)
- Risks and unknowns (5 bullets)
- Capex estimate (itemised breakdown)

- 4.N Decision tree (Table by growth horizon)
- 4.N+1 Recycle optimisation (if applicable across variants)
- 4.N+2 Capex band summary

### Section 5: Modelled process results

- 5.1 Capacity and binding constraints (table by scenario)
- 5.2 Annual mass load framing
- 5.3 Effluent quality response to loading (TN vs EP chart)
- 5.4 Increased annual discharge load (environmental quantification — see
  Canungra Rev 19 for the right "quantify and minimise" framing)

### Section 6: What could break Scenario S2

Red-team framing of top 5-10 risks. Each risk presented as a callout box:
- F1, F2, F3... as risk numbers
- Title: short description
- Body: risk explanation + mitigation plan + link to corresponding RFC

### Section 7: Phase 2 verification package

RFC-01 through RFC-N. Each RFC has:
- Scope (what would be done)
- Specific activities (bullet list)
- Cost (AUD range)
- Timeline (weeks or months)
- Priority (HIGH/MEDIUM/LOW/CONDITIONAL)
- Impact on project

Include Stage 0 gateway RFC if regulatory interpretation is a front-end issue
(as Canungra RFC-10 does for licence mass load).

### Section 8: Recommendations

- 8.1 Immediate action — no regret (what to do this quarter)
- 8.2 Pre-feasibility verification required (what to do next 6 months)
- 8.3 Intensification pathway — dependent on verification (medium-term)
- 8.4 Decision gate for capital commitment (list of gate items)
- 8.5 Regulatory parallel track (if applicable)

### Section 9: Caveats and limitations

- 9.1 Model limitations (5-10 items)
- 9.2 Scope exclusions (7-10 items)
- 9.3 Commercial and planning caveats (5-7 items)
- 9.4 Status of key statements (table: statement | status | basis)

## Standard language and tone

- Use "preferred concept for pre-feasibility development" NOT "recommended"
  at the concept study level
- Use "modelled capacity ceiling" or "could potentially remain compliant up
  to approximately X EP, subject to verification" NOT "X EP maximum"
- Use "screening-level capex" NOT "capex" or "cost estimate"
- Use "Interpretation A/B" framing when licence interpretation matters
- Use "verify in Phase 2" or "see RFC-N" whenever an assumption is flagged
- Use "concentration-compliant" and "mass-compliant" separately
- NEVER state opinions on regulatory outcomes — flag as RFC items
- NEVER state opinions on receiving water or catchment impact — that's
  the utility's workstream

## Process for drafting a new concept study

Step 1: **Read the as-built basis document** (usually a process design report).
Identify: plant type, capacity, licence limits, flow profile, kinetics used.

Step 2: **Establish the capacity target** from client scope. This is usually
the utility's growth projection for the catchment.

Step 3: **Build the scenario ladder**. At minimum:
- S0 (existing as-is)
- S1A (no-regret controls)
- S2 (reconfiguration variants)

Add S1B only if an intermediate technology (like IFAS) materially helps.

Step 4: **Run the process model** at each scenario. Use a Python module
modelled on canungra_runner.py — 5-stage Bardenpho with diurnal profile.

Step 5: **Identify the binding constraint** at each scenario. This is usually:
- S0/S1A: licence limits (concentration or mass)
- S1B: aerobic nitrification or alpha-factor
- S2: post-anoxic denitrification capacity

Step 6: **Build PFDs for each scenario** using the Rev B visual style
(orthogonal recycles, hatched anoxic, dotted aerobic, brown-orange fills,
red borders for new/modified elements).

Step 7: **Draft sections in order 1 → 9**. Don't skip Section 9 — the caveats
section is what makes the report defensible.

Step 8: **Run through the pre-issue checklist** (checklist_before_issue.md).

## Worked example

See `example_canungra_rev20.js` for a complete, production-quality report.
This is the Canungra STP Intensification Concept Study Rev 20 in its final
form, with all 38 pages worth of structured content.

## Integration with WaterPoint platform

When a concept study is part of a WaterPoint project workflow:

1. The scenario model lives in `apps/wastewater_app/[project_name]/`
2. The Streamlit UI shows the scenarios and lets users explore sensitivities
3. The report docx is produced using this template referring to the scenario
   results
4. Results can be re-exported from the model if assumptions change

Keep the report script and the model in sync. If the model changes, the
report revision number bumps.
