"""page_08_manual.py — PurePoint User Manual"""
import streamlit as st


def render():
    st.markdown("# 📖 User Manual")
    st.markdown("*Platform guide, engineering framework, and technical reference for PurePoint.*")
    st.divider()

    tabs = st.tabs([
        "🚀 Getting Started",
        "🔄 Workflow Guide",
        "💧 Effluent Inputs",
        "✅ Class Framework",
        "🔬 LRV Engine",
        "🧪 Chemical Matrix",
        "⚠️ Failure Modes",
        "⚡ PurePoint Intelligence",
        "🛠️ Engineering Notes",
    ])

    # ------------------------------------------------------------------ #
    # TAB 1 — GETTING STARTED
    # ------------------------------------------------------------------ #
    with tabs[0]:
        st.markdown("## What PurePoint does")
        st.markdown(
            "PurePoint is a **barrier-credit-based advanced water reuse decision engine**. "
            "It takes WaterPoint final effluent as its starting point and determines whether — "
            "and how — that effluent can be converted into Class C, Class A, Class A+, or "
            "Purified Recycled Water (PRW) under both normal and upset conditions."
        )
        st.markdown("**What it evaluates:**")
        st.markdown("""
- Microbial log reduction value (LRV) performance — protozoa, bacteria, viruses
- Barrier-credit accounting for each treatment step
- Chemical contaminant removal across 7 contaminant groups
- Critical control point (CCP) and surrogate monitoring framework
- Failure mode resilience — single barrier failure, dose drop, influent spike, UV degradation
- WaterPoint effluent quality sensitivities and their downstream impacts
- Upgrade pathway from Class C through to PRW
        """)
        st.markdown("**What it does not replace:**")
        st.markdown("""
- Detailed process design or hydraulic modelling
- Site-specific membrane pilot testing or ozone CT validation
- Vendor quotes (treatment train sizing is indicative only)
- Regulatory pre-consultation or scheme approval processes
- Quantitative Microbial Risk Assessment (QMRA) — PurePoint uses LRV as a proxy
        """)

        st.divider()
        st.markdown("## Platform position")
        st.markdown("""
PurePoint is **Stage 3** of the Water Utility Planning Platform:

| Stage | App | Domain |
|---|---|---|
| 1 | WaterPoint | Wastewater treatment |
| 2 | AquaPoint | Drinking water treatment |
| **3** | **PurePoint** | **Purified recycled water / indirect potable reuse** |
| 4 | BioPoint | Biosolids management |

PurePoint begins where WaterPoint ends. The final effluent quality from WaterPoint 
is the input to PurePoint. In future versions, this handoff will be automatic via 
shared session state.
        """)

        st.divider()
        st.markdown("## Who it is for")
        st.markdown("""
- **Water utility planners** evaluating reuse scheme feasibility
- **Consulting engineers** developing options reports and concept designs
- **Owner's engineers** reviewing treatment train proposals
- **Regulatory advisors** assessing barrier adequacy and CCP frameworks

PurePoint is a concept-stage tool. It is not a substitute for detailed design 
or scheme-specific validation.
        """)

    # ------------------------------------------------------------------ #
    # TAB 2 — WORKFLOW GUIDE
    # ------------------------------------------------------------------ #
    with tabs[1]:
        st.markdown("## Recommended workflow")
        st.markdown(
            "PurePoint is designed to be worked through sequentially. "
            "Each page builds on the previous. Run the assessment before navigating to results pages."
        )

        steps = [
            ("🏗️ 1. Project Setup", "project_setup",
             "Define the project name, effluent source type, and target reuse classes. "
             "Select the effluent type preset — this pre-fills default quality values on the next page. "
             "Select all four classes if you want a full comparative assessment."),
            ("💧 2. Effluent Quality", "effluent_quality",
             "Enter WaterPoint final effluent quality. Provide median, P95, and P99 values. "
             "The engine uses P99 for failure mode and resilience assessment. "
             "Median values drive the baseline chemical matrix assessment. "
             "If you have WaterPoint results open, cross-reference the effluent outputs directly."),
            ("▶ Run Assessment", "run",
             "Click 'Run PurePoint Assessment' at the bottom of the Effluent Quality page. "
             "The engine runs all modules simultaneously — classifier, LRV calculator, "
             "chemical matrix, treatment train selector, CCP builder, failure mode analyser, "
             "and WaterPoint interface sensitivity check."),
            ("✅ 3. Class Assessment", "class_assessment",
             "Review the feasibility overview cards and per-class LRV tables. "
             "Check the margin column — positive margin means compliance with headroom, "
             "near-zero margin means tight compliance, negative means additional barriers required. "
             "Review warnings and conditions flagged for each class."),
            ("⚙️ 4. Treatment Trains", "treatment_trains",
             "Review the minimum-sufficient treatment train for each class. "
             "Key barriers are highlighted. Design annotations flag input-driven requirements "
             "such as PFAS concentration concerns or nitrate exceedances. "
             "The CCP framework table shows what to monitor and what failure looks like."),
            ("🧪 5. Chemical Matrix", "chemical_matrix",
             "Review the chemical contaminant assessment tabbed by class. "
             "Risk, mechanism, credit, surrogate, and residual risk are shown for "
             "seven contaminant groups. The bioassay layer section explains how "
             "bioassay fits into the monitoring framework."),
            ("⚠️ 6. Failure Modes", "failure_modes",
             "Review the four failure scenarios across all assessed classes. "
             "The action column defines the required operational response — "
             "continue, increase dose, divert, or restore barrier. "
             "The WaterPoint interface table shows how upstream effluent quality "
             "changes affect each class."),
            ("📄 7. Report", "report",
             "Generate and download the full assessment report as a markdown file. "
             "The report includes all tables, LRV results, treatment trains, "
             "chemical matrix, CCP framework, failure modes, and upgrade pathway. "
             "Re-run the assessment before exporting if inputs have changed."),
        ]

        for icon_label, key, desc in steps:
            with st.expander(icon_label, expanded=False):
                st.markdown(desc)

        st.divider()
        st.markdown("## Re-running the assessment")
        st.markdown(
            "You can return to Effluent Quality at any time, adjust inputs, and re-run. "
            "All results pages update automatically from the new `purepoint_result` session object. "
            "Previous results are overwritten — there is no comparison mode in v1.0."
        )

    # ------------------------------------------------------------------ #
    # TAB 3 — EFFLUENT INPUTS
    # ------------------------------------------------------------------ #
    with tabs[2]:
        st.markdown("## Input parameters — reference")
        st.markdown(
            "All inputs represent WaterPoint **final effluent** quality — "
            "not raw wastewater and not in-process streams."
        )

        st.markdown("### Physical quality")
        st.markdown("""
| Parameter | Unit | Notes |
|---|---|---|
| Turbidity — Median / P95 / P99 | NTU | P99 used for membrane TMP stress and LRV penalty assessment |
| TSS — Median / P95 / P99 | mg/L | P99 governs MF/UF fouling risk and RO SDI assessment |
        """)

        st.markdown("### Organic quality")
        st.markdown("""
| Parameter | Unit | Notes |
|---|---|---|
| DOC — Median / P95 / P99 | mg/L | Drives ozone demand; P95 governs AOP sizing |
| UV254 — Median / P95 / P99 | cm⁻¹ | NOM indicator; higher values increase ozone demand and UV lamp intensity |
| AOC / BDOC | µg/L | Optional; used for biological stability assessment in BAC sizing |
        """)

        st.markdown("### Nutrients")
        st.markdown("""
| Parameter | Unit | Notes |
|---|---|---|
| NH₃-N | mg/L | Chloramine precursor; nitrosamine risk indicator; >30 mg/L triggers PRW flag |
| NO₃-N | mg/L | Compared against 11.3 mg/L drinking water guideline; exceedance requires RO for PRW |
        """)

        st.markdown("### Microbial indicators")
        st.markdown("""
| Parameter | Unit | Notes |
|---|---|---|
| E. coli — Median / P95 / P99 | cfu/100mL | Used as surrogate pathogen indicator; P99 informs required LRV headroom |
        """)

        st.markdown("### Chemical contaminants")
        st.markdown("""
| Parameter | Unit | Notes |
|---|---|---|
| PFAS sum | ng/L | Sum of PFOS + PFOA + other detected PFAS; >100 ng/L flags GAC EBCT concern; >200 ng/L flags advanced treatment need |
| Conductivity | µS/cm | TDS proxy; >1200 µS/cm flags RO TDS management concern for PRW |
| CEC / PPCP risk | qualitative | Low / Medium / High; drives bioassay monitoring requirements |
| Nitrosamine precursor risk | qualitative | Low / Medium / High; High triggers UV-AOP dose requirement flag |
        """)

        st.markdown("### Effluent type presets")
        st.markdown("""
| Preset | Typical turbidity P99 | Typical E. coli median | Notes |
|---|---|---|---|
| CAS | 12 NTU | 5,000 cfu/100mL | Conventional activated sludge — variable quality |
| BNR | 10 NTU | 2,000 cfu/100mL | Better nitrification; lower ammonia |
| MBR | 1 NTU | 10 cfu/100mL | Near-membrane quality; significantly lower pathogen load |
| Tertiary | 3 NTU | 500 cfu/100mL | Post-filter; intermediate quality |
| Custom | User defined | User defined | Full manual entry |
        """)

    # ------------------------------------------------------------------ #
    # TAB 4 — CLASS FRAMEWORK
    # ------------------------------------------------------------------ #
    with tabs[3]:
        st.markdown("## Reuse class framework")
        st.markdown(
            "PurePoint evaluates four product classes. Each class has distinct "
            "microbial LRV requirements, chemical contaminant control expectations, "
            "and monitoring obligations. Higher classes are supersets of lower classes."
        )

        st.markdown("### Class C — Non-potable reuse")
        st.markdown("""
**Typical applications:** Agricultural irrigation (non-edible crops), dust suppression, 
construction water, some industrial process water.

**Treatment philosophy:** Coagulation, clarification, dual-media filtration, chlorine disinfection. 
No membrane or advanced oxidation required at this class.

**Limitations:** Not suitable for food-crop irrigation, urban amenity, or any application 
involving human contact. No PFAS treatment mechanism. Limited chemical contaminant control.
        """)

        st.markdown("### Class A — Unrestricted urban reuse")
        st.markdown("""
**Typical applications:** Public open space irrigation, road median strips, 
sports fields, toilet flushing, some industrial cooling.

**Treatment philosophy:** MF/UF membrane (absolute protozoan barrier) + ozone or UV-AOP 
(virus supplementation and PPCP partial removal) + BAC (biological polishing) + chlorine disinfection.

**Key requirement:** MF/UF membrane is the minimum filtration standard. 
Conventional filtration alone does not meet Class A protozoan LRV requirements.
        """)

        st.markdown("### Class A+ — High-exposure / food-crop reuse")
        st.markdown("""
**Typical applications:** Food-crop irrigation (edible crops), high-contact urban reuse, 
groundwater recharge where residence time is short.

**Treatment philosophy:** MF/UF + ozone-AOP (dual oxidation step) + BAC/GAC + 
independent UV barrier + chlorine disinfection. Two independent oxidation steps required.

**Key requirement:** Independent UV barrier in addition to ozone-AOP. 
GAC polishing for PFAS and CEC management. Multi-endpoint bioassay monitoring required.
        """)

        st.markdown("### PRW — Purified Recycled Water (Indirect Potable)")
        st.markdown("""
**Typical applications:** Indirect potable reuse via environmental buffer (aquifer or reservoir), 
groundwater replenishment, reservoir augmentation.

**Treatment philosophy:** MF/UF + RO (absolute chemical and ionic barrier) + UV-AOP 
(pathogen kill and residual organic oxidation) + chlorine CT disinfection + re-mineralisation.

**Key requirements:** RO is the defining barrier for PRW — it provides definitive PFAS, 
nitrate, conductivity, and organic removal. Re-mineralisation (lime, CO₂, calcium) is 
required post-RO to restore water quality for corrosion control and palatability. 
An environmental buffer (aquifer, reservoir) provides additional residence time and 
attenuation before extraction for potable supply.

**Regulatory note:** PRW schemes require formal regulatory approval pathways that are 
jurisdiction-specific. PurePoint provides the technical framework — regulatory pre-consultation 
must occur independently.
        """)

        st.divider()
        st.markdown("## Upgrade pathway logic")
        st.markdown("""
Each class is a superset of the previous:

**C → A:** Add MF/UF membrane + ozone or UV-AOP + BAC. 
The clarification and filtration stages of Class C are replaced or supplemented by membrane filtration.

**A → A+:** Add ozone-AOP (upgrade from ozone or UV-AOP to combined ozone-AOP) 
+ polishing GAC + independent UV. The treatment depth increases; the footprint increases moderately.

**A+ → PRW:** Add RO + UV-AOP upgrade + re-mineralisation. 
RO is the step-change barrier — it fundamentally changes the treatment philosophy 
from oxidation-based to separation-based for chemical contaminants.

**Design principle:** Locate civil works and pipe routes on day one to allow 
future class upgrades without demolition. PRW pipe routes, RO building footprint, 
and UV-AOP contactor positions should be reserved in the site masterplan even if 
initially built to Class A or A+.
        """)

    # ------------------------------------------------------------------ #
    # TAB 5 — LRV ENGINE
    # ------------------------------------------------------------------ #
    with tabs[4]:
        st.markdown("## LRV framework — how it works")
        st.markdown(
            "PurePoint uses a **barrier-credit-based LRV model** aligned with the WaterVal framework. "
            "Each treatment barrier is assigned a log reduction value credit for protozoa, bacteria, and viruses. "
            "Credits are summed across the treatment train and compared against the required LRV for each class."
        )

        st.markdown("### Required LRV by class")
        st.markdown("""
| Class | Protozoa | Bacteria | Virus |
|---|---|---|---|
| C | 3.0 log | 4.0 log | 2.0 log |
| A | 4.0 log | 5.0 log | 4.0 log |
| A+ | 5.0 log | 6.0 log | 6.0 log |
| PRW | 6.0 log | 6.0 log | 8.0 log |
        """)

        st.markdown("### Barrier credits")
        st.markdown("""
| Barrier | Protozoa | Bacteria | Virus | Conditionality |
|---|---|---|---|---|
| Coagulation + clarification | 1.0 | 0.5 | 0.5 | Settled turbidity ≤2 NTU |
| MF/UF membrane | 4.0 | 2.0 | 1.0 | PDT integrity verified; TMP within range |
| RO | 2.0 | 2.0 | 2.0 | Salt rejection ≥98%; conductivity in range |
| Ozone | 0.5 | 2.0 | 2.0 | O₃:TOC ≥0.5; CT achieved |
| UV-AOP | 2.0 | 3.0 | 3.0 | Validated dose ≥500 mJ/cm²; UVT ≥65% |
| UV (40 mJ/cm²) | 3.0 | 4.0 | 3.0 | Validated dose ≥40 mJ/cm²; UVT ≥75% |
| Cl₂ disinfection | 0.5 | 3.0 | 4.0 | CT achieved; pH ≤8.0; residual ≥0.5 mg/L |
| BAC/GAC | 0.0 | 0.5 | 0.0 | EBCT ≥10 min; DOC removal confirmed |
        """)

        st.markdown("### P99 turbidity / TSS penalty")
        st.markdown(
            "When P99 turbidity exceeds 5 NTU or P99 TSS exceeds 10 mg/L, "
            "the engine applies a 0.5 log reduction to the protozoa LRV total. "
            "This reflects the real reduction in filtration and membrane credit "
            "that occurs under high-load event conditions. "
            "The penalty is flagged explicitly in the LRV table."
        )

        st.markdown("### Margin interpretation")
        st.markdown("""
| Margin | Meaning | Action |
|---|---|---|
| > +1.0 log | Good margin — comfortable compliance | No action required |
| 0 to +1.0 log | Tight — marginal compliance | Monitor closely; verify barrier performance |
| < 0 log | Insufficient | Additional barrier required before class can be claimed |
        """)

        st.markdown("### LRV credit conditionality")
        st.markdown(
            "LRV credits are only valid when the barrier is operating within its validated design envelope. "
            "A membrane with a failed integrity test loses its protozoa credit. "
            "A UV reactor operating below validated dose loses its virus and protozoa credit. "
            "An ozone contactor operating below CT loses its oxidation credit. "
            "The CCP framework on page 4 defines the operating envelopes and failure indicators "
            "for each barrier in the selected treatment train."
        )

    # ------------------------------------------------------------------ #
    # TAB 6 — CHEMICAL MATRIX
    # ------------------------------------------------------------------ #
    with tabs[5]:
        st.markdown("## Chemical contaminant matrix — reference")
        st.markdown(
            "The chemical matrix evaluates seven contaminant groups across all assessed classes. "
            "It uses a barrier-credit approach rather than compound-by-compound analysis. "
            "Risk, mechanism, credit, surrogate, and residual risk are assigned based on "
            "the treatment train for each class and the input quality flags."
        )

        groups = [
            ("PFAS", """
**What it includes:** PFOS, PFOA, and the broader PFAS suite including short-chain variants.

**Why it matters:** PFAS are persistent, bioaccumulative, and subject to rapidly tightening 
regulatory limits in most jurisdictions. Short-chain PFAS (C4–C6) are poorly removed by GAC 
at standard EBCT and require either PFAS-selective ion exchange resin or RO for reliable removal.

**Treatment response by class:**
- Class C: No mechanism — PFAS passes through
- Class A: Limited GAC at adequate EBCT — long-chain partial removal only
- Class A+: GAC/BAC polishing — good long-chain removal; short-chain uncertain
- PRW: RO — >99% removal all chain lengths

**Key input threshold:** PFAS sum >100 ng/L triggers a GAC EBCT verification flag. 
>200 ng/L triggers an advanced treatment requirement flag (PFAS-selective resin or RO).
            """),
            ("Nitrosamines", """
**What it includes:** NDMA and the broader nitrosamine family. NDMA is the key concern 
in recycled water given its formation during chloramination and ozonation of nitrogen-rich effluents.

**Why it matters:** NDMA is a probable human carcinogen with a very low regulatory guideline 
(typically 10–100 ng/L depending on jurisdiction). It is formed — not destroyed — by conventional 
chlorination, making it a treatment-induced contaminant risk.

**Treatment response:** UV-AOP is the primary destruction mechanism for NDMA 
(photolysis at 254 nm + hydroxyl radical oxidation). Ozone alone does not reliably destroy NDMA. 
RO provides partial rejection but does not eliminate the risk.

**Key input flag:** High nitrosamine precursor risk triggers a UV-AOP dose requirement 
(minimum 500 mJ/cm² validated dose for NDMA destruction).
            """),
            ("PPCPs", """
**What it includes:** Pharmaceuticals and personal care products — antibiotics, hormones, 
anti-epileptics, analgesics, fragrances, UV filters.

**Why it matters:** PPCPs are present in all wastewater effluents at trace concentrations. 
Their long-term health effects at recycled water concentrations are uncertain, but 
endocrine-active PPCPs (oestrogens, progestins) are of particular concern.

**Treatment response:** Ozone and UV-AOP provide partial removal of most PPCPs. 
BAC biological degradation removes ozone transformation products. 
RO provides near-complete rejection. Conventional treatment (Class C train) provides 
minimal removal — PPCPs pass through largely intact.
            """),
            ("Pesticides", """
**What it includes:** Herbicides, insecticides, fungicides from agricultural and urban catchments.

**Why it matters:** Pesticide profiles vary significantly by catchment. 
Most are present at low concentrations in secondary effluent but some 
(glyphosate, chlorpyrifos, diuron) are persistent.

**Treatment response:** Ozone-AOP + GAC provides good removal for most pesticide classes. 
RO is definitive. Class C and Class A trains provide limited treatment.
            """),
            ("Endocrine-active compounds (EACs)", """
**What it includes:** Natural and synthetic oestrogens (E1, E2, EE2), bisphenol A, 
phthalates, alkylphenols, and other compounds that interfere with the endocrine system.

**Why it matters:** EACs are active at very low concentrations (ng/L range) and have 
demonstrated effects on aquatic organisms. Human health effects at environmental concentrations 
are debated but regulators are increasingly applying precautionary approaches.

**Treatment response:** Ozone-AOP provides strong EAC removal. 
BAC provides supplementary biological degradation. 
Bioassay (ER-CALUX) is the primary surrogate monitoring tool — 
it measures oestrogenic activity directly rather than individual compound concentrations.
            """),
            ("Industrial organics", """
**What it includes:** Solvents, petroleum hydrocarbons, halogenated organics, 
surfactants, and other industrial chemical residues.

**Why it matters:** Presence depends heavily on catchment industrial profile. 
Mixed urban/industrial catchments may have significant industrial organic loads that 
conventional treatment does not address.

**Treatment response:** Ozone + BAC/GAC provides moderate removal. 
RO is definitive. High CEC risk input flag elevates the assessment for this group.
            """),
            ("Bulk organic toxicity", """
**What it includes:** The aggregate toxic effect of all organic compounds in the water, 
measured as a bioassay endpoint rather than individual compound concentrations.

**Why it matters:** Individual compound monitoring cannot capture the effect of complex 
mixtures or unknown compounds. Bioassay provides a system-level check on chemical safety 
that complements targeted analytics.

**Treatment response:** The treatment train reduces bulk organic toxicity through 
combined oxidation, adsorption, and biological treatment. 
Multi-endpoint bioassay (DR-CALUX, cytotoxicity, genotoxicity) is the primary 
verification tool for A+ and PRW.
            """),
        ]

        for name, content in groups:
            with st.expander(f"**{name}**", expanded=False):
                st.markdown(content)

    # ------------------------------------------------------------------ #
    # TAB 7 — FAILURE MODES
    # ------------------------------------------------------------------ #
    with tabs[6]:
        st.markdown("## Failure mode analysis — how to interpret results")
        st.markdown(
            "The failure mode analysis tests each class against four scenarios. "
            "It is not a probabilistic risk assessment — it is a deterministic "
            "stress test of the treatment train under defined upset conditions."
        )

        st.markdown("### The four scenarios")
        st.markdown("""
**1. MF/UF membrane integrity breach**  
Simulates a membrane fibre break or O-ring failure causing loss of the physical protozoan barrier. 
For Class A, A+, and PRW this is a critical failure — the absolute protozoa barrier is lost. 
Required response is divert and restore membrane integrity before resuming production at that class.

**2. Ozone system failure / dose drop**  
Simulates ozone generator failure or CT falling below the design target. 
For Class C (no ozone in train) — no impact. 
For Class A — virus LRV is reduced; PPCPs pass through. Increasing Cl₂ CT partially compensates. 
For PRW — RO covers the chemical protection function; impact is limited but must be flagged and restored.

**3. Poor WaterPoint effluent event — TSS / turbidity spike**  
Simulates a storm event or upstream process upset driving elevated TSS and turbidity into PurePoint. 
This is the most common real-world upset condition. 
MF/UF TMP rises; membrane CIP frequency increases; ozone demand increases; RO SDI may rise. 
Response is to reduce flow, increase coagulant dose if upstream coagulation is present, and monitor TMP.

**4. UV lamp degradation — dose below validated minimum**  
Simulates gradual lamp intensity reduction or sudden lamp failure. 
For Class A and A+ — protozoa and virus LRV margin is consumed. 
For PRW — AOP function is lost; nitrosamine destruction is impaired. 
Required response is to replace lamp before resuming production at the affected class.
        """)

        st.markdown("### Action colour codes")
        st.markdown("""
| Action | Meaning |
|---|---|
| **Continue** | Treatment train maintains compliance — no immediate action required |
| **Increase dose / adjust** | Operational response available — increase Cl₂ CT, ozone dose, or coagulant |
| **Divert** | Do not deliver water at this class until barrier is restored |
| **N/A** | Barrier not present in this class — scenario does not apply |
        """)

        st.markdown("### WaterPoint interface sensitivities")
        st.markdown(
            "The second section of the Failure Modes page shows how WaterPoint effluent quality "
            "parameters affect PurePoint treatment intensity and class feasibility. "
            "These are not failure modes — they are sensitivity flags that indicate where "
            "upstream process upsets propagate into PurePoint operational risk. "
            "High-severity flags should be reflected in the WaterPoint operational protocols "
            "and in the PurePoint design basis for the affected process stage."
        )

    # ------------------------------------------------------------------ #
    # TAB 8 — PUREPOINT INTELLIGENCE
    # ------------------------------------------------------------------ #
    with tabs[7]:
        st.markdown("## PurePoint Intelligence — Reasoning Engine")
        st.markdown(
            "PurePoint runs a single integrated reasoning engine. Unlike WaterPoint and AquaPoint "
            "which pair a quantitative calc engine with a qualitative reasoning engine, PurePoint's "
            "engine is reasoning-first — every output is derived from structured logic applied to "
            "effluent quality inputs, not from empirical cost or energy models."
        )
        st.markdown("""
- **Reasoning engine** — qualitative and semi-quantitative: effluent classification, LRV barrier accounting, chemical matrix, train selection, CCP framework, failure mode analysis, WaterPoint interface sensitivities
- **No separate calc engine** — PurePoint does not calculate CAPEX, OPEX, energy demand, or carbon. These are scope items for a future PurePoint v2.0 calc layer.
        """)
        st.markdown(
            "The reasoning engine is not a lookup table — it is a structured engineering logic system "
            "that mirrors the way an experienced water reuse engineer assesses a treatment train: "
            "starting from effluent quality, working through barrier requirements, and explicitly "
            "testing each class under both normal and upset conditions."
        )
        st.info(
            "PurePoint Intelligence renders across all results pages (Pages 3–6) after the assessment "
            "is run on Page 2. Each page surfaces a different module of the reasoning engine output."
        )

        st.markdown("---")
        st.markdown("## Engine Architecture")
        st.markdown("The reasoning engine is orchestrated by `engine.py` and calls six specialist modules in sequence:")

        gates = [
            (
                "Module 1 — Effluent Classification — `classifier.py`",
                """
Classifies each effluent quality parameter into Good / Marginal / Poor tiers based on defined thresholds.

**Inputs:** All physical, organic, nutrient, microbial, and chemical inputs from Page 2.

**Outputs:**
- Per-parameter quality flags (Good / Marginal / Poor)
- Governing constraint list — parameters that will drive treatment intensity or limit class feasibility

**Logic:** Each parameter is evaluated against two thresholds. Parameters flagged as Poor generate a governing constraint string that propagates to the Class Assessment page.

**Key thresholds:**
- Turbidity P99: Good ≤3 NTU / Marginal ≤10 NTU / Poor >10 NTU
- DOC median: Good ≤8 mg/L / Marginal ≤12 mg/L / Poor >12 mg/L
- PFAS: Good ≤20 ng/L / Marginal ≤100 ng/L / Poor >100 ng/L
- NO₃-N: Good ≤8 mg/L / Marginal ≤11.3 mg/L / Poor >11.3 mg/L (drinking water guideline)
            """,
            ),
            (
                "Module 2 — LRV Barrier Calculator — `lrv.py`",
                """
Calculates cumulative LRV for each target class using a barrier-credit model.

**Inputs:** Target class, effluent quality flags (for P99 penalty), treatment train barrier list from `constants.py`.

**Outputs:**
- Achieved LRV per pathogen (protozoa, bacteria, virus)
- Required LRV per class
- Margin (achieved − required) per pathogen
- Pass / fail status per pathogen
- P99 penalty note if triggered

**Logic:**
1. Retrieves the barrier list for the class from `TREATMENT_TRAINS` in `constants.py`
2. Resolves barrier name aliases (e.g. "Ozone-AOP" → "Ozone" credit key)
3. Sums credits across all barriers for each pathogen
4. Applies P99 turbidity/TSS penalty (−0.5 log protozoa) if P99 turbidity >5 NTU or TSS >10 mg/L
5. Compares achieved vs required; calculates margin

**Barrier credits** are defined in `BARRIER_CREDITS` in `constants.py`. Credits are fixed — they do not vary with dose or concentration. Conditionality is expressed through the CCP framework, not through variable credits.
            """,
            ),
            (
                "Module 3 — Chemical Matrix Builder — `chemical.py`",
                """
Evaluates seven chemical contaminant groups for the given class, applying input-driven overrides where the effluent quality flags elevate risk.

**Inputs:** Target class, PFAS concentration, CEC risk flag, nitrosamine risk flag.

**Outputs:** Per-group assessment — risk, mechanism, credit, surrogate, residual risk.

**Logic:**
- Base matrix values are retrieved from `CHEMICAL_MATRIX` in `constants.py`
- Input-driven overrides are applied:
  - PFAS >200 ng/L and class ≠ PRW → residual risk elevated to High
  - PFAS >100 ng/L and class = A → residual risk elevated
  - Nitrosamine risk = High → residual risk elevated for nitrosamine group
  - CEC risk = High → endocrine-active compound risk elevated to High

**Design principle:** The matrix is not a pass/fail system — it is a risk characterisation that informs treatment train annotations and CCP requirements. Residual risk is the risk remaining after the recommended train is applied, not the raw source risk.
            """,
            ),
            (
                "Module 4 — Treatment Train Selector — `trains.py`",
                """
Selects the minimum-sufficient treatment train for the given class and annotates it with input-driven design requirements.

**Inputs:** Target class, effluent quality inputs.

**Outputs:** Treatment train (steps, key barriers, LRV barriers, design note) plus annotations.

**Logic:**
- Base train is retrieved from `TREATMENT_TRAINS` in `constants.py`
- Annotations are generated from input conditions:
  - PRW + NO₃-N >11.3 mg/L → RO sizing note
  - PRW + conductivity >1500 µS/cm → TDS management note
  - PFAS >100 ng/L → GAC EBCT verification note
  - Nitrosamine risk = High → UV-AOP dose note
  - TSS P99 >15 mg/L → upstream coagulation note

**Design principle:** Trains are minimum-sufficient — they represent the minimum barrier set required to achieve the class LRV targets. They do not include redundancy, standby units, or peak-flow capacity. Annotations flag where the specific effluent quality drives requirements beyond the minimum.
            """,
            ),
            (
                "Module 5 — CCP Framework Builder — `ccp.py`",
                """
Builds the CCP and surrogate monitoring table filtered to the barriers present in the selected treatment trains.

**Inputs:** Target classes (to determine union of active barriers), full CCP table from `constants.py`.

**Outputs:** Filtered list of CCP rows relevant to the assessed classes.

**Logic:**
- Unions all barriers across all target class trains
- Normalises barrier names for matching (e.g. "MF/UF membrane" → "mf/uf")
- Filters `CCP_FRAMEWORK` to rows whose barrier is in the active set
- Always includes Cl₂ disinfection regardless of train (it is present in every class)

**Design principle:** The CCP table is not a compliance checklist — it is an operational monitoring framework. Each row defines what to monitor (CCP parameter), what the acceptable operating envelope is, and what the failure indicator and required response are.
            """,
            ),
            (
                "Module 6 — Failure Mode Analyser — `failure_modes.py`",
                """
Tests each assessed class against four predefined failure scenarios and returns the LRV impact, chemical protection impact, and required operational response.

**Inputs:** Target class, scenario key.

**Outputs:** Per-scenario, per-class response — LRV impact, chemical protection, action.

**Logic:**
- Retrieves fixed response dict from `FAILURE_RESPONSES` in `constants.py`
- Responses are pre-defined per scenario × class combination — they are not calculated dynamically
- The action field drives the colour-coded response display on Page 6

**The four scenarios:**
1. `uf_failure` — MF/UF membrane integrity breach
2. `ozone_failure` — Ozone system failure / CT below target
3. `influent_spike` — Poor WaterPoint effluent event (TSS / turbidity)
4. `uv_failure` — UV lamp degradation below validated dose
            """,
            ),
            (
                "Module 7 — WaterPoint Interface & Upgrade Deltas — `engine.py`",
                """
Generates two outputs that provide cross-platform context:

**WaterPoint interface sensitivities:** Evaluates how each effluent quality input parameter affects PurePoint treatment intensity and operational risk. Each sensitivity has a parameter label, impact description, and severity (High / Medium / Low). These are generated dynamically from input values — they are not fixed lookup responses.

**Upgrade deltas:** Fixed text strings describing what each class upgrade step adds to the treatment train. Used to populate the upgrade pathway display on Page 3.

**Key sensitivity thresholds:**
- DOC P95 >12 mg/L → High ozone/AOP demand
- TSS P99 >15 mg/L → High MF/UF TMP risk
- PFAS >200 ng/L → High advanced barrier requirement
- NO₃-N >11.3 mg/L → High PRW restriction
- Conductivity >1500 µS/cm → High RO TDS concern
- CEC risk = High → High bioassay monitoring requirement
            """,
            ),
        ]

        for title, content in gates:
            with st.expander(title):
                st.markdown(content)

        st.markdown("---")
        st.markdown("## Engine orchestration — `engine/reasoning/__init__.py`")
        st.markdown(
            "The master orchestrator `run_reasoning_engine()` calls all seven modules in sequence "
            "and assembles the results into a single `PurePointResult` dataclass. "
            "This object is stored in `st.session_state['purepoint_result']` and is read by all pages."
        )
        st.markdown("""
```
run_reasoning_engine(inputs: EffluentInputs) → PurePointResult

  1. classify_effluent()        → constraints, quality_flags
  2. For each target class:
       calculate_lrv()          → LRVResult
       select_train()           → TrainResult
       build_chem_matrix()      → ChemMatrix
       analyse_failure_modes()  → FailureModeResult
       _build_warnings()        → warnings list → feasibility status
  3. build_ccp_table()          → CCPResult
  4. build_wp_sensitivities()   → sensitivity list
  5. build_upgrade_deltas()     → upgrade delta strings
  → PurePointResult
```
        """)

        st.markdown("---")
        st.markdown("## Data architecture")
        st.markdown("""
| Dataclass | Location | Contents |
|---|---|---|
| `EffluentInputs` | `reasoning/__init__.py` | All Page 2 input values |
| `ClassResult` | `reasoning/__init__.py` | Full assessment for one class |
| `PurePointResult` | `reasoning/__init__.py` | All class results + CCP + sensitivities + upgrade deltas |

All constants (LRV requirements, barrier credits, treatment trains, chemical matrix, CCP framework, failure responses, effluent presets) are defined in `engine/constants.py` and imported by the reasoning modules. No engineering values are hardcoded in the page files.
        """)

        st.markdown("---")
        st.markdown("## What PurePoint Intelligence does not do (v1.0)")
        st.markdown("""
- Does not calculate CAPEX, OPEX, energy demand, or carbon — these are planned for v2.0
- Does not perform QMRA — LRV is used as a deterministic proxy
- Does not validate barrier performance — it assumes barriers are operating within their design envelopes
- Does not assess concentrate management for RO trains
- Does not perform compound-specific chemical fate modelling
- Does not replace scheme-specific validation, pilot testing, or regulatory pre-consultation
        """)

    # ------------------------------------------------------------------ #
    # TAB 9 — ENGINEERING NOTES
    # ------------------------------------------------------------------ #
    with tabs[8]:
        st.markdown("## Engineering notes and limitations")

        st.markdown("### LRV model assumptions")
        st.markdown("""
- LRV credits are based on published guideline values and peer-reviewed literature defaults
- Credits assume barriers are operating within their validated design envelopes
- The P99 turbidity/TSS penalty (−0.5 log protozoa) is a conservative proxy — 
  actual performance depends on membrane type, coagulation upstream, and specific event conditions
- Virus LRV credits for RO assume salt rejection ≥98% — lower rejection reduces virus credit proportionally
- Ozone LRV credits assume O₃:TOC ≥0.5 mg/mg — at lower ratios, virus and bacteria credits should be reduced
        """)

        st.markdown("### Chemical matrix assumptions")
        st.markdown("""
- Risk and residual risk ratings are qualitative — they reflect the treatment train's 
  expected performance at the class level, not compound-specific removal efficiencies
- PFAS GAC removal assumes EBCT ≥15 minutes for long-chain compounds — 
  actual breakthrough depends on GAC type, PFAS profile, and competing organics
- Short-chain PFAS (C4 and below) removal by GAC is uncertain — 
  regulatory monitoring is essential; the engine flags this but cannot quantify removal
- Nitrosamine formation potential depends on precursor concentration, chloramine dose, 
  contact time, pH, and temperature — these are not captured in the engine
- Bioassay surrogates are monitoring tools, not removal mechanisms — 
  the engine uses them as CCPs, not as treatment credits
        """)

        st.markdown("### Treatment train sizing")
        st.markdown("""
- Treatment trains shown are minimum-sufficient configurations — 
  they do not include redundancy units, standby capacity, or peak-flow sizing
- MF/UF membrane area, ozone contactor volume, UV reactor sizing, and GAC EBCT 
  must be determined through detailed design
- RO recovery rate (typically 70–85%) determines concentrate volume — 
  concentrate management is not assessed in PurePoint v1.0
- Re-mineralisation for PRW (lime/CO₂ or calcite contactor) is shown in the train 
  but sizing and corrosion control design are outside PurePoint scope
        """)

        st.markdown("### Regulatory context")
        st.markdown("""
- PurePoint is framework-agnostic — it does not reference a specific national guideline
- LRV targets are broadly consistent with Australian Guidelines for Water Recycling (AGWR), 
  WHO guidelines for water reuse, and US EPA guidelines for water reuse
- Jurisdiction-specific requirements (validation protocols, scheme approval, 
  monitoring frequencies, indicator organisms) must be applied by the user
- PRW schemes in most jurisdictions require formal regulatory approval that goes 
  significantly beyond the technical assessment PurePoint provides
        """)

        st.markdown("### Version history")
        st.markdown("""
| Version | Notes |
|---|---|
| v1.0 | Initial release — all four classes, full LRV engine, chemical matrix, CCP framework, failure modes, report export |
        """)

        st.divider()
        st.markdown(
            "<span style='font-size:0.82rem;color:#888;'>"
            "PurePoint v1.0 · ph2o Consulting · "
            "Assessment outputs are decision-support only and do not constitute regulatory approval."
            "</span>",
            unsafe_allow_html=True,
        )
