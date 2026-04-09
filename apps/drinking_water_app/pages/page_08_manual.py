"""
AquaPoint — Page 8: User Manual
Platform guide, module reference, and engineering notes.
Matches WaterPoint manual structure: 8-tab layout.
ph2o Consulting | Water Utility Planning Platform
"""
import streamlit as st
from ..ui_helpers import section_header, info_box, warning_box, success_box


def render():
    st.markdown("""
        <div style="margin-bottom:1rem">
            <h2 style="color:#1a1a2e;font-size:1.4rem;font-weight:600;margin-bottom:0.2rem">
                📖 User Manual
            </h2>
            <p style="color:#8899aa;font-size:0.9rem;margin:0;font-style:italic">
                Platform guide, module reference, and engineering notes.
            </p>
        </div>
    """, unsafe_allow_html=True)

    tabs = st.tabs([
        "🚀 Getting Started",
        "🔄 Workflow Guide",
        "⚙️ Treatment Modules",
        "📋 Input Reference",
        "📊 Understanding Results",
        "⚡ AquaPoint Intelligence",
        "🔬 Engineering Notes",
        "📐 Engineering Notes II",
    ])

    # ══ TAB 1 — GETTING STARTED ════════════════════════════════════════════════
    with tabs[0]:
        st.markdown("## What this platform does")
        st.markdown("""
This is a **concept-stage planning tool** for drinking water treatment upgrade and new-build projects.
It is designed for use during options investigation, master planning, and early feasibility — not for detailed design.
""")
        st.markdown("**What it calculates:**")
        for item in [
            "Capital cost (CAPEX) and lifecycle cost estimates for 18 treatment technologies",
            "Annual energy demand and specific energy (kWh/ML)",
            "Greenhouse gas emissions — Scope 2 (electricity) and chemical embodied carbon",
            "Chemical consumption and annual cost (coagulant, disinfectant, pH correction)",
            "Predicted treated water quality vs ADWG guidelines",
            "Regulatory compliance screening against Australian Drinking Water Guidelines (ADWG 2022)",
            "Qualitative risk assessment (implementation, operational, regulatory)",
            "Multi-criteria analysis (MCA) score across 6 weighted criteria",
            "LRV-based pathogen barrier accounting (protozoa, bacteria, virus) via the reasoning engine",
            "Treatment philosophy recommendation across 9 archetypes via the reasoning engine",
        ]:
            st.markdown(f"- {item}")

        st.markdown("**What it does not replace:**")
        for item in [
            "Detailed process design or hydraulic modelling",
            "Site-specific geotechnical or civil assessments",
            "Vendor quotes (CAPEX figures are order-of-magnitude ±30–50%)",
            "Regulatory pre-consultation or permit applications",
            "Treatability or piloting studies",
            "Detailed disinfection Ct calculations or UV validation",
            "QMRA (quantitative microbial risk assessment)",
        ]:
            st.markdown(f"- {item}")

        st.divider()

        st.markdown("## Who it is for")
        st.markdown("""
AquaPoint is designed for:

- **Water utility planners and asset managers** assessing treatment upgrade options
- **Consulting engineers** at options investigation or master planning stage
- **Owner's engineers and technical advisors** stress-testing treatment philosophy choices
- **Project directors** needing a quantified basis for comparing treatment trains before committing to detailed design
""")

        st.divider()
        st.markdown("## Quick start — five steps")

        steps = [
            ("1. Project Setup", "Enter project name, plant type, design flow, and client context. The plant type determines which technologies are available in the selection grid."),
            ("2. Source Water Quality", "Enter your source water parameters — turbidity, TOC, colour, hardness, iron, manganese, algae risk, PFAS, arsenic. Use median values for OPEX and water quality, and P95/P99 values to understand design-governing conditions."),
            ("3. Technology Selection", "Select the technologies in your treatment train. The AquaPoint Intelligence reasoning engine will recommend a treatment philosophy based on your source water — use the suggested train as a starting point, then modify as needed."),
            ("4. Treatment Philosophy", "Review the reasoning engine's full Gate 1–5 analysis: source classification, controlling constraints, archetype selection, LRV barrier accounting, and residuals implications. This is the qualitative backbone of the assessment."),
            ("5. Analysis Results", "Run the calc engine. Eleven analysis tabs cover MCA, water quality, energy, chemicals, CAPEX, OPEX, NPV, risk, environment, regulatory compliance, and feasibility."),
            ("← Platform Home", "Return to the Water Utility Planning Platform launcher at any time using the Platform Home button at the top of the sidebar. This takes you back to the tool selection screen without losing your current session."),
        ]
        for title, desc in steps:
            st.markdown(f"**{title}** — {desc}")

        info_box("You can return and change inputs at any time. The analysis re-runs automatically when you navigate to the Results page.")

    # ══ TAB 2 — WORKFLOW GUIDE ════════════════════════════════════════════════
    with tabs[1]:
        st.markdown("## Recommended Workflow")

        st.markdown("""
AquaPoint is built around a **sequential flow** but supports iteration.
The recommended sequence for a rigorous options analysis is:
""")

        workflow = [
            ("Project Setup", "project_setup", "📋",
             "Set plant type and design flow first — these determine which technologies appear in the selection grid. "
             "Flow is used for all sizing calculations. Plant type filters technologies to those applicable to the configuration."),
            ("Source Water Quality", "source_water", "💧",
             "Enter source water parameters at median and, where available, at 95th and 99th percentile conditions. "
             "The reasoning engine uses P95/P99 data to assess variability class and governing conditions. "
             "Algae risk, PFAS detection, and arsenic flags trigger specific contaminant modules in the intelligence engine."),
            ("Technology Selection", "technology_selection", "🔧",
             "The reasoning engine's recommended philosophy appears above the technology grid as a banner. "
             "Use 'Apply Suggested Train' to pre-populate the grid, then customise. "
             "Technologies greyed out are not applicable to the selected plant type. "
             "Feasibility flags (⚠) appear for technologies that may conflict with your source water conditions."),
            ("Treatment Philosophy", "treatment_philosophy", "🏗️",
             "The most important page for engineering review. "
             "Gate 1–5 analysis is shown across 7 tabs: source classification, controlling constraints, direct filtration assessment, "
             "archetype selection, LRV barrier thread, residuals assessment, and contaminant-specific modules. "
             "Review this before looking at numbers — the philosophy must be defensible before the cost figures mean anything."),
            ("Analysis Results", "results", "📊",
             "Eleven tabs of quantified outputs from the calc engine, with reasoning engine context embedded in the Risk and Environment tabs. "
             "Settings tab allows adjustment of lifecycle parameters, electricity cost, and MCA weights. "
             "Results are cached — tab switching does not re-run the engine."),
            ("Scenario Comparison", "scenario_comparison", "⚖️",
             "Run your current selection (Scenario A) against one of six named preset trains (Scenario B). "
             "Side-by-side comparison table with delta column, bar charts, LRV barrier analysis, and residuals/environment tab. "
             "Use this to stress-test the preferred philosophy against alternatives before reporting."),
            ("Export Report", "report", "📄",
             "Generate a markdown report of your analysis. Covers project details, source water inputs, selected train, "
             "and key results from all analysis layers. Download and paste into your options report or master plan."),
        ]

        for title, page_key, icon, desc in workflow:
            with st.expander(f"{icon} {title}", expanded=False):
                st.markdown(desc)
                if st.button(f"Go to {title} →", key=f"workflow_nav_{page_key}"):
                    st.session_state["current_page"] = page_key
                    st.rerun()

        st.divider()
        st.markdown("## Iterative use pattern")
        st.markdown("""
The most productive way to use AquaPoint is iteratively:

1. **First pass** — enter approximate source water data, apply suggested train, review treatment philosophy, check MCA and CAPEX order of magnitude.
2. **Refine** — update source water with better data, adjust technology selection, tune lifecycle parameters to match utility norms.
3. **Scenario comparison** — run your preferred train against 1–2 alternatives and check sensitivity to key assumptions.
4. **Report** — export and incorporate into your options investigation report.

Each iteration takes 5–10 minutes once source water data is prepared.
""")

    # ══ TAB 3 — TREATMENT MODULES ═════════════════════════════════════════════
    with tabs[2]:
        st.markdown("## Treatment Technology Modules")
        st.markdown("""
AquaPoint includes 18 treatment technology modules across 7 categories.
Each module includes CAPEX, OPEX, energy, chemical, risk, and environmental sub-models.
""")

        categories = [
            ("Pretreatment", [
                ("Screening", "screening",
                 "Coarse and fine screening for debris removal. Minimal energy and cost contribution. "
                 "Required for surface water intakes. Included by default in conventional and membrane trains."),
            ]),
            ("Primary Treatment / Clarification", [
                ("Coagulation + Flocculation", "coagulation_flocculation",
                 "Ferric or alum coagulant addition and rapid/slow mix flocculation. "
                 "The foundational step for turbidity, NOM, colour, arsenic, and pathogen reduction. "
                 "No independent LRV credit — enables downstream barrier performance. "
                 "Ferric preferred for NOM-rich, low-alkalinity, or high-arsenic sources."),
                ("Dissolved Air Flotation (DAF)", "daf",
                 "Pressurised recycle flotation for removal of algal cells, NOM, and low-density particles. "
                 "Preferred over conventional sedimentation for algae-dominated or NOM-rich source waters. "
                 "LRV credit: 1.5–2.0 log protozoa (validated). "
                 "Energy: 45–90 kWh/ML. Higher than sedimentation but more compact footprint."),
                ("Sedimentation", "sedimentation",
                 "Conventional horizontal flow clarification. Robust for turbidity-dominated sources. "
                 "Less effective than DAF for algal cells (40–70% vs 85–95% cell removal during blooms). "
                 "LRV credit: 0.5–1.5 log protozoa (indicative). "
                 "Largest footprint of clarification options."),
            ]),
            ("Filtration", [
                ("Rapid Gravity Filtration", "rapid_gravity_filtration",
                 "Dual media (anthracite/sand) or sand-only granular filtration. "
                 "Key Cryptosporidium barrier when operated to produce <0.1 NTU effluent. "
                 "LRV credit: 1.5–2.5 log protozoa, conditional on turbidity performance. "
                 "Required following any clarification step. Operates in conjunction with, not as a replacement for, disinfection."),
                ("Slow Sand Filtration", "slow_sand_filtration",
                 "Biological schmutzdecke filtration. Excellent pathogen barrier (2.0–3.5 log protozoa validated). "
                 "Very large footprint — impractical for most urban/regional plants at scale. "
                 "Best suited to small community supplies with stable low-turbidity source water."),
                ("MF / UF Membranes", "mf_uf",
                 "Microfiltration or ultrafiltration. Absolute physical barrier for protozoa and bacteria. "
                 "LRV credit: 3.0–4.0 log protozoa and bacteria (validated with integrity testing). "
                 "Limited virus removal — MF ~0 log, UF up to 2 log if MWCO ≤100 kDa. "
                 "Energy: 40–120 kWh/ML. Integrity testing (pressure hold) required to claim full LRV credit."),
                ("Nanofiltration (NF)", "nf",
                 "Pressure-driven membrane. Removes hardness, NOM, colour, and larger organic molecules. "
                 "Intermediate between UF and RO. Generates concentrate stream. "
                 "Used where full desalination (RO) is not required but high NOM removal is needed."),
                ("Reverse Osmosis (RO)", "ro",
                 "High-pressure membrane with near-complete dissolved solids rejection. "
                 "Removes PFAS, arsenic, nitrate, hardness, TDS, NOM. "
                 "LRV credit: 3.5–4.5 log protozoa, 4.0–5.5 log bacteria, 3.0–5.5 log virus (validated). "
                 "Energy: 800–3,000 kWh/ML. "
                 "CRITICAL: Generates a concentrate stream (15–20% of feed at 80–85% recovery) "
                 "containing all rejected contaminants at 5–7× concentration. "
                 "If PFAS is present in feed, the concentrate is a PFAS-bearing classified waste stream. "
                 "Confirm concentrate disposal pathway before recommending this option."),
            ]),
            ("Advanced Treatment", [
                ("Ozonation", "ozonation",
                 "Strong oxidant for taste and odour destruction, NOM transformation, and disinfection. "
                 "CRITICAL SEQUENCING: Must be applied AFTER cell removal when cyanobacteria are present. "
                 "Pre-ozonation lyses intact cells and releases intracellular toxins — never pre-ozonate during a cyanobacterial event. "
                 "LRV credit: 0–0.5 log protozoa (Crypto essentially resistant at practical Ct), 2.0–3.5 log bacteria/virus. "
                 "Bromate risk: bromide >0.05 mg/L requires suppression strategy (H₂O₂, pH depression, or ammonium). "
                 "Monitor bromate at ozone outlet — ADWG limit 10 μg/L. "
                 "Energy: 35–80 kWh/ML."),
                ("Biological Activated Carbon (BAC)", "bac",
                 "Granular activated carbon operating in biological mode. "
                 "Post-ozone BAC mineralises ozonation by-products and provides T&O polishing. "
                 "Most effective when preceded by ozonation — this activates the biological community. "
                 "BAC without ozone upstream still provides adsorptive T&O removal but performance degrades faster. "
                 "PFAS removal: limited — adsorption capacity for PFAS on BAC is lower than virgin GAC and declines with use. "
                 "Not a validated pathogen barrier."),
                ("GAC (Granular Activated Carbon)", "gac",
                 "Virgin GAC adsorption for PFAS, T&O, and NOM polishing. "
                 "More effective than BAC for PFAS removal on a per-bed-volume basis. "
                 "EBCT 10–20 min typical for T&O; longer for PFAS depending on compound profile. "
                 "Short-chain PFAS (C4–C6) break through GAC significantly faster than long-chain — "
                 "full PFAS compound profile is required before sizing GAC for PFAS removal. "
                 "Spent GAC is a PFAS-bearing waste if source PFAS is significant — confirm disposal classification."),
                ("Advanced Oxidation (AOP)", "aop",
                 "UV/H₂O₂ or O₃/H₂O₂ advanced oxidation for trace organic contaminants and T&O. "
                 "UV/H₂O₂ provides UV-equivalent protozoan inactivation plus hydroxyl radical oxidation. "
                 "O₃/H₂O₂ (peroxone): reduces bromate formation compared to ozone alone at equivalent T&O removal. "
                 "Energy: 30–150 kWh/ML depending on UV dose and H₂O₂ dose."),
            ]),
            ("Disinfection", [
                ("Chlorination", "chlorination",
                 "Free chlorine for primary disinfection of bacteria and viruses. "
                 "PROVIDES NO PROTOZOAN INACTIVATION — Cryptosporidium and Giardia are not effectively inactivated by chlorine at practical Ct values. "
                 "LRV credit: 0 log protozoa, 1.5–3.0 log bacteria, 2.0–3.5 log virus (Ct and pH dependent). "
                 "At pH >8.0, virus inactivation efficiency is significantly reduced. "
                 "Free chlorine in high-TOC water generates THMs and HAAs — consider chloramination for distribution."),
                ("Chloramination", "chloramination",
                 "Secondary chloramines for distribution residual maintenance. "
                 "NOT a primary disinfection step — provides negligible additional pathogen inactivation. "
                 "LRV credit: 0 log protozoa, 0–1.0 log bacteria/virus. "
                 "Preferred for distribution in high-TOC water — substantially reduces THM/HAA formation vs free chlorine. "
                 "Requires Cl₂:NH₃-N ratio of 4–5:1 to avoid dichloramine/trichloramine. "
                 "Nitrification monitoring programme in distribution is mandatory."),
                ("UV Disinfection", "uv_disinfection",
                 "UV photoinactivation — the primary validated protozoan inactivation barrier. "
                 "LP UV at 40 mJ/cm²: 1.5–2.0 log Cryptosporidium, 1.5–2.5 log bacteria, 1.0–2.5 log virus. "
                 "Credit is conditional on UVT ≥72% and validated dose delivery. "
                 "At P95/P99 turbidity and high TOC, UVT may drop — design must use worst-case UVT, not average. "
                 "MP UV at higher doses can achieve greater LRV credits but requires dose verification. "
                 "Must be positioned after filtration to ensure adequate UVT."),
            ]),
            ("Residuals", [
                ("Sludge Thickening", "sludge_thickening",
                 "Gravity thickening or mechanical thickening of clarification sludge and filter backwash. "
                 "Required for all clarification-based trains. "
                 "Existing lagoon capacity must be assessed — mechanical dewatering (centrifuge or belt press) "
                 "may be required if lagoon capacity is limited. "
                 "Sludge arsenic content must be characterised if source arsenic is elevated — "
                 "may trigger classified waste disposal requirements."),
                ("Brine/Concentrate Management", "brine_management",
                 "Management of RO or NF membrane concentrate stream. "
                 "At 80–85% recovery, concentrate volume is 15–20% of feed flow. "
                 "All rejected contaminants are concentrated 5–7×. "
                 "If PFAS is present in source water, concentrate is a PFAS-bearing classified waste. "
                 "Disposal options: sewer (requires utility consent and TDS/PFAS assessment), "
                 "river discharge (environmental licence required), evaporation ponds (land-intensive), "
                 "high-pressure membrane further concentration, or thermal destruction (for PFAS). "
                 "No viable disposal pathway should be assumed — confirm before selecting RO."),
            ]),
        ]

        for cat_name, techs in categories:
            section_header(cat_name, "▸")
            for label, key, desc in techs:
                with st.expander(f"**{label}**", expanded=False):
                    st.markdown(desc)

    # ══ TAB 4 — INPUT REFERENCE ════════════════════════════════════════════════
    with tabs[3]:
        st.markdown("## Input Parameter Reference")

        st.markdown("### Project Setup Inputs")
        project_inputs = [
            ("Plant Type", "Determines which technologies are available in the selection grid and which benchmark energy values are used.",
             "conventional | membrane | groundwater | desalination"),
            ("Design Flow (ML/d)", "Average daily design flow. Used for all sizing, energy, chemical, and cost calculations. "
             "Use the average day flow — not peak day — for lifecycle cost calculations.",
             "ML/d (megalitres per day)"),
            ("Project Name", "Label only — appears in sidebar and report header.", "Free text"),
        ]

        for name, desc, values in project_inputs:
            st.markdown(f"**{name}**")
            st.markdown(f"*{desc}*")
            st.markdown(f"Values: `{values}`")
            st.markdown("---")

        st.markdown("### Source Water Quality Inputs")

        source_inputs = [
            ("Turbidity (NTU)", "Single median value used by the calc engine for removal calculations and ADWG compliance. "
             "The reasoning engine uses this to infer P95 and P99 values (×4 and ×10 of median as defaults). "
             "If you have measured P95/P99 data, enter those directly in the Treatment Philosophy page inputs.",
             "Typical range: 1–500 NTU. Median for design, P99 for front-end sizing."),
            ("TOC (mg/L)", "Total organic carbon. Used for NOM removal calculations, chemical dose estimation, DBP precursor assessment, "
             "and UV transmittance inference. High TOC (>8 mg/L) triggers enhanced coagulation recommendation.",
             "Typical range: 1–20 mg/L. ADWG has no direct TOC limit but TOC drives THM/HAA formation."),
            ("Colour (HU)", "True colour in Hazen Units. Indicates NOM loading. High colour (>15 HU) is an exclusion criterion for direct filtration. "
             "90 HU at P95 is high and will drive enhanced coagulation requirements.",
             "Typical range: 5–100 HU. ADWG aesthetic guideline: 15 HU."),
            ("TDS (mg/L)", "Total dissolved solids. Used for ADWG compliance check and to determine whether TDS reduction (NF/RO) is required. "
             "ADWG aesthetic guideline is 600 mg/L — above this, RO or NF is needed for compliance.",
             "Typical range: 100–2,000 mg/L for surface water, up to 35,000 mg/L for seawater."),
            ("Hardness (mg/L as CaCO₃)", "Total hardness. High hardness (>400 mg/L) flags softening requirement. "
             "Moderate hardness (150–250 mg/L) may be acceptable without treatment. "
             "ADWG aesthetic guideline: 200 mg/L.",
             "Typical range: 50–800 mg/L. Softening recommended >250–300 mg/L for most applications."),
            ("Iron (mg/L)", "Total iron. Dissolved Fe²⁺ from groundwater or hypolimnetic reservoir water is the most problematic form. "
             "Fe²⁺ in groundwater >0.5 mg/L is a direct filtration exclusion criterion. "
             "ADWG aesthetic guideline: 0.3 mg/L.",
             "Typical range: 0.01–5 mg/L. Values >0.3 mg/L require dedicated treatment."),
            ("Manganese (mg/L)", "Total manganese. Dissolved Mn²⁺ in groundwater >0.1 mg/L is a direct filtration exclusion criterion. "
             "Manganese oxidation chemistry must be confirmed across the full pH range of the source. "
             "ADWG health guideline: 0.5 mg/L; aesthetic: 0.1 mg/L.",
             "Typical range: 0.001–0.5 mg/L. Values >0.05 mg/L require specific treatment attention."),
            ("Algal Cells/mL", "Algae risk driver. Used to set algae_risk category in the reasoning engine: "
             "<2,000 = low, 2,000–10,000 = moderate, >10,000 = high. "
             "Cyanobacteria dominance requires specific sequencing rules in the treatment train.",
             "WHO alert levels: >2,000 cells/mL (Alert 1), >100,000 cells/mL (Alert 3)."),
        ]

        for name, desc, guidance in source_inputs:
            with st.expander(f"**{name}**", expanded=False):
                st.markdown(desc)
                st.markdown(f"*{guidance}*")

        st.markdown("### Lifecycle Parameter Inputs")
        st.markdown("""
Accessible via the **Settings tab** on the Analysis Results page.

| Parameter | Default | Description |
|---|---|---|
| Analysis period | 30 years | NPV calculation horizon |
| Discount rate | 7.0% | Real discount rate for NPV |
| OPEX escalation | 2.5%/yr | Annual real cost escalation |
| CAPEX contingency | 20% | Added to subtotal CAPEX |
| Electricity cost | $0.12/kWh | Used for energy cost calculations |
| Membrane replacement | 10 years | MF/UF membrane replacement cycle |
| GAC/BAC replacement | 5 years | Media replacement cycle |

These defaults represent typical Australian water utility assumptions. Adjust to match your client's corporate norms.
""")

    # ══ TAB 5 — UNDERSTANDING RESULTS ═════════════════════════════════════════
    with tabs[4]:
        st.markdown("## Understanding the Results")

        st.markdown("### MCA Score")
        st.markdown("""
The Multi-Criteria Analysis score (0–100) is a weighted composite of 6 criteria:

| Criterion | Default weight | What it measures |
|---|---|---|
| Water quality | 30% | ADWG compliance confidence and treatment effectiveness |
| Lifecycle cost | 25% | NPV relative to plant type benchmark |
| Risk | 20% | Implementation, operational, and regulatory risk |
| Energy | 10% | Specific energy vs plant type benchmark |
| Environmental | 10% | Carbon intensity (kg CO₂/kL) |
| Regulatory compliance | 5% | ADWG parameter compliance status |

**What the MCA score means:**
- 75–100: Well-matched treatment train for this source water — strong across most criteria
- 50–74: Adequate — likely trade-offs between cost, performance, or operability
- Below 50: Significant weakness in at least one criterion — review before proceeding

The MCA score is relative to the selected train only. It does not compare against other trains unless you use the Scenario Comparison page.
""")
        warning_box("MCA weights can be adjusted in the Settings tab. Change them to reflect your client's priorities before using the score in reporting.")

        st.markdown("### CAPEX Estimates")
        st.markdown("""
CAPEX figures are **Class 4–5 estimates (±30–50%)** based on:
- Technology-specific unit cost databases (AUD, current year)
- Economy-of-scale exponent of 0.65 from a 10 ML/d reference plant
- Included: equipment, installation, civil works (allowance), electrical, instrumentation (allowance)
- Excluded: land, site-specific civil, connections and pipework, preliminary design, authority fees

**Low / Typical / High range** reflects uncertainty in scope and market conditions, not a confidence interval.
""")

        st.markdown("### Energy Estimates")
        st.markdown("""
Specific energy (kWh/ML) is the sum of per-technology energy benchmarks:

| Technology | Typical range (kWh/ML) |
|---|---|
| Coagulation + flocculation | 10–25 |
| DAF | 55–90 |
| Sedimentation | 10–25 |
| Rapid gravity filtration | 20–40 |
| MF/UF | 70–120 |
| RO | 1,500–3,000 |
| Ozonation | 40–80 |
| BAC/GAC | 10–25 |
| UV disinfection | 15–35 |

RO dominates energy in a membrane train — expect 5–10× the specific energy of a conventional train.
""")

        st.markdown("### LRV Barrier Accounting")
        st.markdown("""
The reasoning engine accounts for pathogen removal separately for three classes:

- **Protozoa** — Cryptosporidium, Giardia (most resistant to disinfection)
- **Bacteria** — Campylobacter, Salmonella, etc.
- **Viruses** — enteric viruses (adenovirus, norovirus, rotavirus)

Credits are **indicative validated values** based on ADWG 2022 Table 10.1 and WHO GDWQ.
They represent what a regulator would accept with appropriate process validation — not theoretical maxima.

**Critical rules embedded in the engine:**
- Coagulation alone: 0 log independent credit
- Chlorine: 0 log protozoan credit
- Ozone: 0–0.5 log protozoa (Cryptosporidium is highly ozone-resistant at practical Ct)
- UV at 40 mJ/cm²: 1.5–2.0 log protozoa (LP UV)
- All credits are conditional on process performance — a filter producing 0.5 NTU effluent does not get full filtration LRV credit
""")
        warning_box("LRV credits in AquaPoint are indicative planning-level estimates. Jurisdictional LRV validation under the applicable regulatory framework is required for design and approval.")

        st.markdown("### Water Quality Compliance")
        st.markdown("""
AquaPoint predicts treated water quality by applying removal efficiency factors for each technology to the source water inputs.
It then compares against ADWG 2022 guidelines.

Parameters assessed: turbidity, TOC, TDS, hardness, iron, manganese, colour, pH, chlorine, THMs, HAAs.

**Important limitations:**
- Removal factors are order-of-magnitude estimates — not validated treatment models
- Some ADWG parameters (e.g. fluoride, nitrate, heavy metals beyond iron/Mn) are not currently assessed
- DBP (THM/HAA) assessment is qualitative — detailed calculation requires site-specific Ct and TOC data
""")

    # ══ TAB 6 — AQUAPOINT INTELLIGENCE ════════════════════════════════════════
    with tabs[5]:
        st.markdown("## AquaPoint Intelligence — Reasoning Engine")
        st.markdown("""
AquaPoint runs two parallel engines:

- **Calc engine** — quantitative: CAPEX, OPEX, energy, MCA, water quality, environmental
- **Reasoning engine** — qualitative: treatment philosophy, source classification, LRV accounting, residuals

The reasoning engine is not just a classifier — it is a structured engineering logic system
that mirrors the way an experienced water treatment engineer frames a treatment selection problem.
""")

        st.markdown("### Gate Structure")

        gates = [
            ("Gate 1 — Source Classification", "classifier.py",
             "Classifies the source type (river, reservoir, groundwater, blended, recycled, desalination) "
             "and variability class (low/moderate/high/extreme). "
             "River and reservoir sources get higher variability scores. "
             "Source type drives which archetypes are available and which constraints are scored."),
            ("Gate 2 — Controlling Constraint Identification", "classifier.py",
             "Scores 13 constraint categories against the source water inputs: "
             "solids/events, NOM/DBP, algae/cyanobacteria, hardness, low alkalinity, pathogen LRV, "
             "arsenic, PFAS/TrOC, salinity/TDS, iron/manganese, residuals, taste/odour, cyanotoxins. "
             "The highest-scoring constraint becomes the primary constraint driving treatment philosophy selection."),
            ("Gate 2b — Governing Conditions", "classifier.py",
             "Identifies which conditions actually govern design — not average conditions. "
             "Outputs specific statements about P95/P99 turbidity ratios, TOC variability, "
             "algal bloom as a distinct operational mode, low alkalinity implications, and extreme event sizing."),
            ("Gate 2c — Direct Filtration Assessment", "classifier.py",
             "Direct filtration is opt-in only — requires positive evidence of suitability. "
             "Exclusion criteria: P95 turbidity >5 NTU, TOC >5 mg/L, algae risk ≥moderate, colour >15 HU, "
             "high variability river source, cyanobacteria confirmed, "
             "alkalinity <40 mg/L, pH min <6.5, dissolved Fe >0.5 mg/L (GW), dissolved Mn >0.1 mg/L (GW)."),
            ("Gate 3 — Contaminant Module Triggers", "contaminants.py",
             "Activates contaminant-specific modules: arsenic (>7 μg/L), PFAS (detected), "
             "taste and odour (MIB/geosmin flag), cyanotoxins (confirmed cyanobacteria or toxin detection), "
             "algae (high risk), iron/manganese (Fe >0.3 or Mn >0.1 mg/L). "
             "Each module provides a preferred pathway, critical preconditions, and residuals implications."),
            ("Gate 4 — Archetype Selection", "archetypes.py",
             "Selects the preferred treatment philosophy from 9 archetypes (A–I) based on the primary constraint. "
             "The primary constraint drives the recommendation — not just the highest-scoring archetype. "
             "Hardness → softening (F); algae → DAF (D); hardness → NOT DAF; NOM/DBP → enhanced coag (E); "
             "Fe/Mn groundwater → conventional with oxidation (B), not DAF. "
             "Archetypes that fail Tier 1 (LRV deficit, no disinfection) are excluded from recommendation."),
            ("Gate 5 — Residuals and Problem Transfer", "residuals.py",
             "Assesses residuals complexity for each archetype. "
             "Lime sludge (softening) is rated very_high complexity — volume, dewaterability, land requirement. "
             "RO concentrate is flagged as a PFAS-bearing classified waste if source PFAS is detected. "
             "Problem transfer flags are surfaced: arsenic in sludge, PFAS in spent GAC, "
             "cyanotoxin-bearing DAF float during bloom conditions."),
        ]

        for title, module, desc in gates:
            with st.expander(f"**{title}** — `{module}`", expanded=False):
                st.markdown(desc)

        st.markdown("### LRV Parallel Thread")
        st.markdown("""
The LRV module (`lrv.py`) runs in parallel through Gates 1–5.
It maintains a pathogen barrier accounting ledger for each archetype.

**Architecture:**
- Per-barrier credits stored in `LRV_BARRIER_CREDITS` — `(credited_low, credited_high, note, validated/indicative)`
- Default barrier sets defined for each archetype in `ARCHETYPE_DEFAULT_BARRIERS`
- Credits are summed across barriers — but coagulation contributes 0 (enabler only)
- Tier 1 of the scoring framework gates on LRV deficit — an archetype with a protozoan LRV gap fails Tier 1 unconditionally

**Key engineering constraints hardcoded:**
- Archetype F (softening) has no UV in the default barrier set — Tier 1 protozoan barrier check fails without UV
- Archetype G (ozone) Tier 1 fails when cyanobacteria are confirmed — ozone must follow cell removal
- Archetype H (membrane) credits MF/UF and RO independently; UV provides additional margin
""")

        st.markdown("### Decision Readiness")
        st.markdown("""
The reasoning engine produces a **Decision Readiness** assessment for each scenario — one of three statuses:

- **Ready** — Tier 1 safety gate passes, LRV targets met, no selection-blocking uncertainties. Proceed to detailed design.
- **Proceed with Conditions** — Treatment selection is defensible but 1–2 engineering conditions must be carried into detailed design (e.g. single-barrier dependence, residuals disposal confirmation, Ct verification). These are design conditions, not blockers.
- **Not Decision-Ready** — A Tier 1 failure (LRV deficit) or a selection-blocking uncertainty exists that must be resolved before committing to a treatment archetype.

**Important distinction:** Single-barrier dependence and residuals disposal confirmation are *conditions*, not blockers. They do not change which archetype is selected — they require resolution at detailed design stage. A clean, low-risk groundwater scenario with single-barrier dependence and a residuals pathway to confirm will return *Proceed with Conditions*, not *Not Decision-Ready*.

Selection-blocking items are those where resolving the uncertainty could change the archetype selection itself — for example, unquantified PFAS (could trigger membrane/GAC), uncharacterised cyanotoxin events (could require DAF over conventional), or extreme P99 variability data not yet available.
""")

        st.markdown("### Tier 1–4 Scoring")
        st.markdown("""
Each viable archetype is scored across 4 tiers:

| Tier | Basis | Weighting |
|---|---|---|
| Tier 1 | Compliance / safety — LRV adequacy, disinfection presence | Pass/Fail gate |
| Tier 2 | Robustness — variability, event response, barrier redundancy, operability | 50% of overall |
| Tier 3 | Resources — energy, chemicals, residuals, footprint | 30% of overall |
| Tier 4 | Cost and flexibility — CAPEX, OPEX, expandability, delivery risk | 20% of overall |

A Tier 1 fail sets overall score to 0 and marks the archetype `not_recommended`.
""")

    # ══ TAB 7 — ENGINEERING NOTES I ════════════════════════════════════════════
    with tabs[6]:
        st.markdown("## Engineering Notes — Microbial Barriers and Disinfection")

        st.markdown("### The Multi-Barrier Principle")
        st.markdown("""
Australian drinking water guidelines (ADWG 2022) and international frameworks (WHO GDWQ) require
a **multi-barrier approach** to pathogen control. No single barrier is sufficient.

A defensible treatment train must provide:
1. **Physical removal** — clarification and filtration to reduce pathogen numbers before disinfection
2. **Primary disinfection** — validated inactivation of key pathogens
3. **Secondary residual** — maintenance of a disinfectant residual through distribution to control regrowth

The barriers operate in series — each adds to the LRV total. The **weakest** individual barrier at its
**worst operating condition** determines the minimum achievable LRV, not the average.
""")

        st.markdown("### Cryptosporidium — The Governing Protozoan Pathogen")
        st.markdown("""
Cryptosporidium is the primary design driver for protozoan control because:
- It is highly resistant to chlorine (essentially no inactivation at practical Ct)
- UV at 40 mJ/cm² achieves 1.5–2.0 log inactivation (validated)
- Ozone provides essentially 0 log inactivation at practical treatment Ct (<1 mg·min/L at 15°C)
- Physical removal (filtration) provides 1.5–2.5 log removal (conditional on <0.1 NTU effluent)

**Consequence:** Every drinking water treatment train on a surface water source must include UV (or very high-dose ozone) as the primary protozoan inactivation barrier.
Chlorine alone is never sufficient for protozoan control.
""")
        warning_box(
            "Chlorine does NOT inactivate Cryptosporidium at any Ct achievable in practical water treatment. "
            "UV disinfection is mandatory for surface water sources where protozoan LRV targets must be met."
        )

        st.markdown("### Cyanobacteria — Sequencing Rules")
        st.markdown("""
When cyanobacteria are present or suspected:

**Rule 1: Cell removal before oxidation.**
Pre-chlorination or pre-ozonation lyses intact cyanobacterial cells, releasing intracellular toxins
(microcystin, cylindrospermopsin, saxitoxin) at concentrations that are far more difficult to treat
than intact cells. This is not a minor operational consideration — it is a public health risk.

**Response protocol (recommended trigger levels):**
- <500 cells/mL: standard operation
- 500–2,000 cells/mL: increase coagulant dose, verify DAF performance, increase monitoring
- 2,000–20,000 cells/mL: suspend pre-oxidation; manage off-take depth; verify cell removal efficiency
- >20,000 cells/mL (WHO Alert Level 3): consider source suspension if alternative available; notify regulator

**Rule 2: DAF is preferred over conventional sedimentation for algal cell removal.**
DAF achieves 85–95% algal cell removal when well-coagulated.
Conventional horizontal flow sedimentation achieves 40–70% during bloom conditions.
The difference is not operational performance — it is physics. Algal cells float.

**Rule 3: PAC during blooms.**
PAC alone is unreliable for MIB/geosmin removal at high TOC (NOM competes for adsorption sites).
At TOC >5 mg/L and MIB >30 ng/L, PAC doses >40 mg/L are required for 90% removal — impractical.
Ozone + BAC is the reliable long-term strategy; PAC is the emergency event response.
""")

        st.markdown("### Bromate Control")
        st.markdown("""
When ozone is used and bromide is present in the source water:

**Bromate formation risk:**
- Bromide <0.05 mg/L: low bromate risk at practical ozone doses
- Bromide 0.05–0.10 mg/L: moderate risk — monitor bromate at ozone outlet
- Bromide >0.10 mg/L: significant risk — suppression strategy required
- Bromide >0.18 mg/L (P95 in this source): mandatory suppression at all ozone doses

**ADWG bromate limit: 10 μg/L**

**Suppression strategies (in order of effectiveness):**
1. H₂O₂ co-injection at 0.5:1 H₂O₂:O₃ ratio — scavenges bromine radicals
2. pH depression at ozone contact to 6.5–7.0 — slows bromide oxidation
3. Ammonium addition — NH₃ scavenges bromine but may cause nitrification concerns downstream
4. Reduced ozone dose — trade-off against T&O and disinfection performance

Monitor bromate at the ozone outlet at minimum weekly, continuously if bromide is variable.
Target <8 μg/L to maintain margin below the 10 μg/L limit.
""")

        st.markdown("### Disinfection Strategy Summary")
        st.markdown("""
| Step | Technology | Purpose | LRV contribution |
|---|---|---|---|
| Pre-oxidation (conditional) | Chlorine or KMnO₄ | Fe/Mn oxidation only — NOT during cyanobacterial events | None for pathogens |
| Primary protozoan barrier | UV (LP, ≥40 mJ/cm²) | Cryptosporidium and Giardia inactivation | 1.5–2.0 log protozoa |
| Primary bacterial/viral disinfection | Free chlorine | Ct-based inactivation | 1.5–3.0 log bacteria, 2.0–3.5 log virus |
| Distribution residual | Chloramination | Residual maintenance, DBP control | Not a disinfection step |

**pH considerations:**
- Optimal coagulation pH: 6.2–7.0 (for ferric coagulant and NOM/arsenic removal)
- Chlorine virus inactivation efficiency: significantly reduced at pH >8.0
- Chloramine stability: best at pH 7.5–8.5
- Distribution corrosion control: target Langelier Saturation Index (LSI) of –0.1 to +0.2

These pH targets can conflict. pH management through the treatment train is required — not just at a single dosing point.
""")

    # ══ TAB 8 — ENGINEERING NOTES II ══════════════════════════════════════════
    with tabs[7]:
        st.markdown("## Engineering Notes — Source Types, PFAS, Arsenic, and Residuals")

        st.markdown("### Source Water Types and Design Implications")

        source_types = [
            ("River (variable surface water)", [
                "Highly variable — design must accommodate P99 conditions, not median",
                "Event-driven turbidity spikes (freshets, post-fire catchments) govern front-end sizing",
                "Seasonal algal/cyanobacterial risk — warm climates require bloom management protocols",
                "NOM typically moderate-high and variable with flow events",
                "Direct filtration rarely appropriate — high variability almost always excludes it",
            ]),
            ("Reservoir / Storage (buffered surface water)", [
                "Reservoir provides hydraulic buffering but introduces stratification",
                "Thermal stratification drives hypolimnetic iron, manganese, ammonia, and low dissolved oxygen",
                "Off-take depth management is the first line of treatment — draw from best quality layer",
                "Algal risk in warm climates — reservoirs concentrate algal growth during stratification",
                "Turbidity events lag river events by days to weeks",
            ]),
            ("Groundwater", [
                "Stable quality — but dissolved chemistry (Fe²⁺, Mn²⁺, hardness, arsenic) often elevated",
                "Dissolved Fe²⁺ and Mn²⁺ are the critical distinction from surface water — oxidation required before filtration",
                "Direct filtration may be appropriate for low-iron, stable groundwater but dissolved Fe/Mn is an exclusion criterion",
                "Low turbidity but may have high colour, hardness, or specific dissolved contaminants (arsenic, nitrate, PFAS)",
                "LRV requirements may differ from surface water depending on jurisdictional framework",
            ]),
            ("Desalination", [
                "TDS >1,000 mg/L (seawater ~35,000 mg/L) — RO is the only viable process",
                "Energy dominated by RO high-pressure pumping (800–3,000 kWh/ML for seawater)",
                "Concentrate disposal is a primary constraint — typically 15–20% of feed volume at seawater scale",
                "Pre-treatment (coagulation, DAF or UF) required to protect RO membranes",
                "Post-treatment remineralisation (calcite contactors or lime + CO₂) required to restore alkalinity and calcium for distribution stability",
            ]),
        ]

        for source_name, points in source_types:
            with st.expander(f"**{source_name}**", expanded=False):
                for point in points:
                    st.markdown(f"- {point}")

        st.markdown("### PFAS — Treatment and Residuals Implications")
        st.markdown("""
PFAS in drinking water sources presents a treatment challenge because:

**Why conventional treatment fails:**
- Coagulation: <10% removal of long-chain PFAS, essentially 0% short-chain
- Sedimentation and filtration: no PFAS removal
- Ozonation: PFAS are ozone-resistant — ozone does not degrade PFAS
- Chlorination and UV: no PFAS removal

**Treatment options in order of effectiveness:**

| Option | Long-chain PFAS | Short-chain PFAS | Residuals |
|---|---|---|---|
| GAC (virgin, EBCT 15 min) | 80%+ initially, degrades with breakthrough | 30–60%, breaks through rapidly | Spent GAC = PFAS-bearing waste |
| PFAS-selective IX resin | >95% removal, regenerable | 80–95% | Regenerant brine = PFAS concentrate |
| RO | >95% all chain lengths | >95% | Concentrate = PFAS-bearing liquid waste (15–20% of flow) |
| AOP (UV/H₂O₂ at very high dose) | Partial mineralisation only | Partial | Not yet viable at scale for PFAS |

**The concentrate problem:**
RO concentrate containing PFAS is a classified liquid waste. At 180 MLD with 85% recovery,
concentrate volume is ~27 ML/d. This requires a credible disposal pathway — landfill injection,
high-temperature incineration, or electrochemical destruction — before RO can be recommended for PFAS removal.

**Short-chain PFAS (C4–C6):**
Short-chain compounds dominate some PFAS profiles (particularly those from AFFF substitutes).
They are significantly more mobile and break through GAC faster than long-chain compounds.
Full compound profiling (EPA 533 or similar comprehensive method) is required before sizing any GAC-based PFAS treatment.
""")
        warning_box(
            "Never size GAC for PFAS removal based on PFOS/PFOA data alone. "
            "Short-chain PFAS compounds (PFBS, PFHxS, PFBA etc) break through orders of magnitude faster. "
            "Compound-specific breakthrough data is required."
        )

        st.markdown("### Arsenic — Treatment and Speciation")
        st.markdown("""
**Arsenic speciation matters:**
- **As(V) arsenate** — anionic, readily removed by ferric coagulation co-precipitation (70–90% removal at ferric dose 15–40 mg/L)
- **As(III) arsenite** — neutral at typical water pH, not removed by coagulation without prior oxidation to As(V)

Surface water sources typically contain predominantly As(V).
Groundwater sources may contain significant As(III) — oxidation (chlorination or KMnO₄) is required before coagulation.

**ADWG health guideline: 7 μg/L**

**Treatment options:**
- Coagulation + filtration with ferric: effective for As(V), pH-dependent (optimal pH 6.0–7.5)
- Iron-based adsorptive media (GFH, FeOOH): effective for As(V) and As(III) post-oxidation, EBCT 5–10 min
- Activated alumina: effective for As(V), requires pH adjustment
- Ion exchange: effective for As(V), brine regenerant contains arsenic
- RO/NF: >95% rejection, arsenic concentrated in reject stream

**Residuals implication:**
Arsenic removed by coagulation concentrates in the sludge. At high removal rates,
the sludge may be classified as a hazardous waste under jurisdictional thresholds.
Characterise sludge arsenic content before confirming disposal pathway.
""")

        st.markdown("### Residuals — The Often-Overlooked Design Constraint")
        st.markdown("""
Every contaminant removed from the water ends up in a residual stream.
AquaPoint surfaces residuals implications throughout the reasoning engine precisely because
they are frequently underweighted in early-stage options analysis.

**Key principle: removal is not disposal.**
When a technology removes a contaminant, it transfers it to a residual stream.
The residual stream has its own handling, treatment, and disposal requirements —
and sometimes those requirements are more difficult than the original water treatment problem.

**Examples of problem transfer:**
- RO removes PFAS from drinking water → PFAS concentrate stream at 6–7× concentration
- GAC adsorbs PFAS → spent GAC is a PFAS-bearing solid waste
- Ferric coagulation removes arsenic → sludge arsenic may trigger hazardous waste classification
- Lime softening removes hardness → very high volume lime sludge with poor dewaterability
- DAF during cyanobacterial bloom → float contains concentrated cyanobacterial cells and toxins

**Residuals management hierarchy:**
1. Source management — reduce contaminant load arriving at the plant (off-take management, catchment control)
2. Process selection — choose technologies that produce manageable residuals
3. Thickening and dewatering — reduce volume before disposal
4. Beneficial reuse — agricultural application of sludge (if not classified), biogas, etc.
5. Regulated disposal — landfill (confirm classification), licensed liquid waste facility, incineration

**Site-specific constraint: lagoon capacity.**
Many existing plants have lagoons near capacity. A treatment upgrade that significantly increases
sludge production without a mechanical dewatering solution will exhaust the lagoon within years.
Mechanical dewatering (centrifuge or belt press) should be included in the upgrade scope
whenever sludge production increases or lagoon capacity is limited.
""")
        info_box(
            "Residuals complexity ratings in AquaPoint: "
            "Low = filter backwash, standard clarifier sludge. "
            "Moderate = DAF float (bloom-period handling), BAC backwash. "
            "High = spent GAC/BAC with PFAS, RO membrane cleaning waste, arsenic-bearing sludge. "
            "Very High = RO concentrate with PFAS, lime softening sludge (volume and dewaterability)."
        )

        st.divider()
        st.markdown("### Platform Limitations and Accuracy")
        st.markdown("""
| Output | Accuracy class | Notes |
|---|---|---|
| CAPEX | ±30–50% | Class 4–5 estimate. Economy of scale from 10 ML/d reference. |
| OPEX | ±20–35% | Energy, chemicals, maintenance. Labour is approximate. |
| NPV | ±30–50% | Inherits CAPEX and OPEX uncertainty plus discount rate sensitivity. |
| Energy | ±20–30% | Benchmark ranges from published data. Actual depends on head and efficiency. |
| Water quality | Qualitative | Removal factors are order-of-magnitude. Not validated treatment models. |
| LRV credits | Indicative | Based on ADWG Table 10.1. Conditional on process performance — not guaranteed. |
| MCA score | Relative only | Scores are relative to the selected train. Weights are adjustable. |

**Version:** AquaPoint v3.0 | ph2o Consulting
**Regulatory reference:** ADWG 2022 (National Health and Medical Research Council / NRMMC)
**Engineering references:** WHO GDWQ 4th Edition; NHMRC/NRMMC Australian Drinking Water Guidelines; AWWA MOP series; WRc/UKWIR membrane and coagulation guidance
""")

    # ── Navigation ──────────────────────────────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("← Back to Results", use_container_width=False):
        st.session_state["current_page"] = "results"
        st.rerun()
