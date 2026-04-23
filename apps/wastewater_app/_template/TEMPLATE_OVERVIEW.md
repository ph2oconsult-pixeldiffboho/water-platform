# WaterPoint Concept Study Template

**Template version:** v1.0 (derived from Canungra STP Rev 20, April 2026)
**Target platform:** ph2o WaterPoint Platform
**Output format:** Word (.docx) + optional PDF

## What this template is for

The WaterPoint Concept Study template produces a screening-level intensification
concept study for a small-to-mid municipal wastewater treatment plant. It was
developed during the Canungra STP study and has been generalised across the
ph2o Consulting portfolio.

This template is designed specifically for:

- **Retrofit capacity intensification** of existing plants (not greenfield)
- **Screening-level engineering analysis** (not tender-ready detailed design)
- **Concept studies that honestly distinguish modelled capacity from verified capacity**
- **Projects requiring a defined Phase 2 verification workstream before capital commitment**

## What makes the Canungra template different

The template's distinguishing features over generic consulting-report formats:

### 1. Explicit document status and scope framing
Every document opens by declaring:
- Confidence level of the study (screening/pre-feasibility/detailed design)
- What it establishes (positive statements)
- What it does NOT establish (explicit scope boundaries)
- Out-of-scope disciplines that could affect the conclusions

This prevents over-reading and sets appropriate expectations for the client.

### 2. Dual-interpretation licence framing
Where licence interpretation at re-licensing materially affects the scheme:
- Present both interpretations (hard cap vs scaled with design EP)
- State which is adopted as the strategic planning basis
- Flag the regulatory consultation as a gateway question (not just a verification item)
- Show business case impact of each interpretation

### 3. Scenario structure: baseline → controls → intensification → reconfiguration
- S0: existing plant (Rev B or equivalent as-built basis)
- S1A: controls/operational (no civil works, no-regret immediate action)
- S1B: intermediate technology (e.g., IFAS retrofit if applicable)
- S2: full reconfiguration (A/B/C/D/E variants as appropriate)

### 4. S2 variants = physically distinct configurations with equal rigour
- Each variant gets: configuration text, PFD, advantages, risks, capex estimate
- Decision tree by growth horizon (not a single "recommended" option)
- Variants are "preferred concepts for pre-feasibility development", not "the recommendation"

### 5. Verification workstream as RFC numbered items
- Each RFC has: scope, specific activities, cost, timeline, priority
- Stage 0 gateway items (regulator consultation) distinguished from parallel verifications
- Conditional RFCs flagged (only required if specific variant carried forward)

### 6. Comprehensive caveats section at end
- Model limitations (kinetic parameters, steady-state vs dynamic)
- Scope exclusions (aeration, hydraulics, solids, structural, electrical, phosphorus)
- Commercial and planning caveats (capex confidence band, vendor dependencies)
- Status of key statements (which are verified, which are modelled, which are assumed)

### 7. Engineering discipline, not marketing
- Paraphrases, never vendor marketing language
- Quantified confidence ranges (conservative/base/optimistic)
- Red-team framing ("what could break this")
- Honest acknowledgement of unverified assumptions

## Template files

```
wp_template/
├── TEMPLATE_OVERVIEW.md            # This file
├── template_structure.py            # Python module defining the report skeleton
├── template_helpers.js              # Shared docx helpers (makeTable, calloutBox, etc.)
├── template_styles.json             # Colour palette and text styles
├── SKILL.md                         # Usage instructions for Claude
├── example_canungra_rev20.js        # Worked example from Canungra project
└── checklist_before_issue.md        # Pre-issue QA checklist
```

## How to use

1. **Copy template_structure.py to your project directory**
2. **Populate the project-specific placeholders** (plant name, capacity, licence limits, etc.)
3. **Build scenarios** — at minimum S0, S1A, optionally S1B, and S2 variants
4. **Draft sections iteratively** — Section 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9
5. **Run through checklist_before_issue.md** before releasing

See SKILL.md for detailed guidance when Claude is drafting reports.
