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
        "🛠️ Engineering Notes",
    ])

    with tabs[0]:
        st.markdown("## What PurePoint does")
        st.markdown("PurePoint is a **barrier-credit-based advanced water reuse decision engine**. It takes WaterPoint final effluent as its starting point and determines whether — and how — that effluent can be converted into Class C, Class A, Class A+, or Purified Recycled Water (PRW) under both normal and upset conditions.")
        st.markdown("**What it evaluates:**")
        st.markdown("- Microbial LRV performance — protozoa, bacteria, viruses\n- Barrier-credit accounting for each treatment step\n- Chemical contaminant removal across 7 contaminant groups\n- CCP and surrogate monitoring framework\n- Failure mode resilience\n- WaterPoint effluent quality sensitivities\n- Upgrade pathway from Class C through to PRW")
        st.markdown("**What it does not replace:**")
        st.markdown("- Detailed process design or hydraulic modelling\n- Site-specific membrane pilot testing or ozone CT validation\n- Vendor quotes\n- Regulatory pre-consultation or scheme approval\n- Quantitative Microbial Risk Assessment (QMRA)")
        st.divider()
        st.markdown("## Platform position")
        st.markdown("PurePoint is **Stage 3** of the Water Utility Planning Platform:\n\n| Stage | App | Domain |\n|---|---|---|\n| 1 | WaterPoint | Wastewater treatment |\n| 2 | AquaPoint | Drinking water treatment |\n| **3** | **PurePoint** | **Purified recycled water** |\n| 4 | BioPoint | Biosolids management |")

    with tabs[1]:
        st.markdown("## Recommended workflow")
        st.markdown("Work through pages sequentially. Run the assessment on page 2 before navigating to results pages.")
        steps = [
            ("🏗️ 1. Project Setup", "Define project name, effluent source type, and target reuse classes. Select effluent type preset to pre-fill quality defaults."),
            ("💧 2. Effluent Quality", "Enter WaterPoint final effluent quality — median, P95, and P99. Click Run Assessment at the bottom of the page."),
            ("✅ 3. Class Assessment", "Review feasibility cards and per-class LRV tables. Check the margin column — positive is compliance with headroom, negative requires additional barriers."),
            ("⚙️ 4. Treatment Trains", "Review minimum-sufficient trains per class. Key barriers are highlighted. CCP framework table shows monitoring requirements."),
            ("🧪 5. Chemical Matrix", "Seven contaminant groups assessed per class — risk, mechanism, credit, surrogate, residual risk. Bioassay layer explained below the matrix."),
            ("⚠️ 6. Failure Modes", "Four failure scenarios across all classes. Action column defines required operational response. WaterPoint interface sensitivities shown below."),
            ("📄 7. Report", "Download full assessment as markdown. Re-run assessment before exporting if inputs have changed."),
        ]
        for label, desc in steps:
            with st.expander(label):
                st.markdown(desc)

    with tabs[2]:
        st.markdown("## Input parameters — reference")
        st.markdown("### Physical\n| Parameter | Unit | Notes |\n|---|---|---|\n| Turbidity | NTU | P99 used for membrane TMP stress and LRV penalty |\n| TSS | mg/L | P99 governs MF/UF fouling and RO SDI assessment |")
        st.markdown("### Organic\n| Parameter | Unit | Notes |\n|---|---|---|\n| DOC | mg/L | Drives ozone demand; P95 governs AOP sizing |\n| UV254 | cm⁻¹ | NOM indicator; increases ozone demand at higher values |\n| AOC/BDOC | µg/L | Biological stability indicator for BAC sizing |")
        st.markdown("### Nutrients\n| Parameter | Unit | Notes |\n|---|---|---|\n| NH₃-N | mg/L | Chloramine precursor; nitrosamine risk; >30 mg/L flags PRW |\n| NO₃-N | mg/L | >11.3 mg/L exceeds DW guideline — RO required for PRW |")
        st.markdown("### Chemical\n| Parameter | Unit | Notes |\n|---|---|---|\n| PFAS sum | ng/L | >100 ng/L flags GAC EBCT concern; >200 ng/L flags advanced treatment |\n| Conductivity | µS/cm | TDS proxy; >1200 µS/cm flags RO TDS management for PRW |\n| CEC risk | qualitative | Low/Medium/High — drives bioassay requirements |\n| Nitrosamine risk | qualitative | High triggers UV-AOP dose requirement |")
        st.markdown("### Effluent presets\n| Preset | Turbidity P99 | E. coli median |\n|---|---|---|\n| CAS | 12 NTU | 5,000 cfu/100mL |\n| BNR | 10 NTU | 2,000 cfu/100mL |\n| MBR | 1 NTU | 10 cfu/100mL |\n| Tertiary | 3 NTU | 500 cfu/100mL |")

    with tabs[3]:
        st.markdown("## Reuse class framework")
        for cls, apps, train, note in [
            ("Class C — Non-potable reuse", "Agricultural irrigation (non-edible crops), dust suppression, construction water.", "Coagulation + clarification + dual-media filtration + Cl₂ disinfection.", "No membrane or advanced oxidation required. Not suitable for food-crop irrigation or human contact applications."),
            ("Class A — Unrestricted urban reuse", "Public open space irrigation, road medians, sports fields, toilet flushing.", "MF/UF membrane + ozone or UV-AOP + BAC + Cl₂ disinfection.", "MF/UF is the minimum filtration standard. Conventional filtration does not meet Class A protozoan LRV requirements."),
            ("Class A+ — High-exposure / food-crop reuse", "Food-crop irrigation (edible crops), high-contact urban reuse, groundwater recharge.", "MF/UF + ozone-AOP + BAC/GAC + UV (40 mJ/cm²) + Cl₂ disinfection.", "Two independent oxidation steps required. Multi-endpoint bioassay monitoring required."),
            ("PRW — Purified Recycled Water", "Indirect potable reuse via aquifer or reservoir augmentation.", "MF/UF + RO + UV-AOP + Cl₂ CT + re-mineralisation.", "RO is the defining barrier. Re-mineralisation required post-RO. Environmental buffer provides additional attenuation before potable extraction."),
        ]:
            st.markdown(f"### {cls}")
            st.markdown(f"**Applications:** {apps}\n\n**Train:** {train}\n\n**Notes:** {note}")
        st.divider()
        st.markdown("## Upgrade pathway\n**C→A:** Add MF/UF + ozone or UV-AOP + BAC.\n\n**A→A+:** Add ozone-AOP + polishing GAC + independent UV.\n\n**A+→PRW:** Add RO + UV-AOP upgrade + re-mineralisation.\n\n> Design civil works from day one to allow future upgrades without demolition.")

    with tabs[4]:
        st.markdown("## LRV framework")
        st.markdown("### Required LRV by class\n| Class | Protozoa | Bacteria | Virus |\n|---|---|---|---|\n| C | 3.0 | 4.0 | 2.0 |\n| A | 4.0 | 5.0 | 4.0 |\n| A+ | 5.0 | 6.0 | 6.0 |\n| PRW | 6.0 | 6.0 | 8.0 |")
        st.markdown("### Barrier credits\n| Barrier | Protozoa | Bacteria | Virus |\n|---|---|---|---|\n| Coagulation + clarification | 1.0 | 0.5 | 0.5 |\n| MF/UF membrane | 4.0 | 2.0 | 1.0 |\n| RO | 2.0 | 2.0 | 2.0 |\n| Ozone | 0.5 | 2.0 | 2.0 |\n| UV-AOP | 2.0 | 3.0 | 3.0 |\n| UV (40 mJ/cm²) | 3.0 | 4.0 | 3.0 |\n| Cl₂ disinfection | 0.5 | 3.0 | 4.0 |\n| BAC/GAC | 0.0 | 0.5 | 0.0 |")
        st.markdown("### P99 penalty\nWhen P99 turbidity >5 NTU or TSS >10 mg/L, a −0.5 log protozoa penalty is applied. This is flagged explicitly in the LRV table.")
        st.markdown("### Margin interpretation\n| Margin | Meaning |\n|---|---|\n| >+1.0 log | Good margin — comfortable compliance |\n| 0 to +1.0 log | Tight — monitor closely |\n| <0 log | Insufficient — additional barrier required |")

    with tabs[5]:
        st.markdown("## Chemical matrix — reference")
        st.markdown("Seven contaminant groups are evaluated per class using a barrier-credit approach.")
        groups = [
            ("PFAS", "Persistent — subject to tightening limits. GAC addresses long-chain; RO addresses all. Short-chain uncertain without PFAS-selective resin."),
            ("Nitrosamines", "NDMA is formed by chloramination — not destroyed by conventional Cl₂. UV-AOP is the primary destruction mechanism. High precursor risk triggers ≥500 mJ/cm² UV-AOP requirement."),
            ("PPCPs", "Present in all effluents. Ozone and UV-AOP provide partial removal. RO near-complete. Class C provides minimal removal."),
            ("Pesticides", "Profile varies by catchment. Ozone-AOP + GAC provides good removal. RO is definitive."),
            ("Endocrine-active compounds", "Active at ng/L concentrations. Ozone-AOP provides strong removal. ER-CALUX bioassay is the primary surrogate monitoring tool."),
            ("Industrial organics", "Presence depends on catchment industrial profile. Ozone + BAC/GAC moderate removal. RO definitive."),
            ("Bulk organic toxicity", "Aggregate toxic effect measured by bioassay — not individual compounds. Multi-endpoint bioassay is the verification tool for A+ and PRW."),
        ]
        for name, desc in groups:
            with st.expander(f"**{name}**"):
                st.markdown(desc)

    with tabs[6]:
        st.markdown("## Failure mode analysis")
        st.markdown("Four deterministic stress tests across all assessed classes.")
        st.markdown("### Scenarios\n1. **MF/UF integrity breach** — absolute protozoa barrier lost. Divert and restore for Class A, A+, PRW.\n2. **Ozone failure** — virus LRV reduced; PPCPs unoxidised. Increase Cl₂ CT; divert for A+.\n3. **TSS/turbidity spike** — most common real-world upset. Reduce flow; monitor TMP; increase coagulant.\n4. **UV lamp degradation** — protozoa and virus margin consumed; AOP lost. Replace lamp before resuming production.")
        st.markdown("### Action codes\n| Action | Meaning |\n|---|---|\n| Continue | Compliance maintained — no action |\n| Increase dose | Operational adjustment available |\n| Divert | Do not deliver at this class until barrier restored |\n| N/A | Barrier not in this class |")

    with tabs[7]:
        st.markdown("## Engineering notes and limitations")
        st.markdown("### LRV model\n- Credits assume barriers operating within validated design envelopes\n- P99 turbidity/TSS penalty is a conservative proxy\n- Virus LRV for RO assumes salt rejection ≥98%\n- Ozone credits assume O₃:TOC ≥0.5 mg/mg")
        st.markdown("### Chemical matrix\n- Risk ratings are qualitative — not compound-specific removal efficiencies\n- PFAS GAC removal assumes EBCT ≥15 min for long-chain\n- Short-chain PFAS removal by GAC is uncertain\n- Nitrosamine formation potential depends on precursor load, dose, pH, temperature")
        st.markdown("### Treatment trains\n- Minimum-sufficient configurations — no redundancy or standby capacity\n- Unit sizing requires detailed design\n- RO concentrate management not assessed in v1.0\n- Re-mineralisation sizing outside PurePoint scope")
        st.markdown("### Regulatory\n- Framework-agnostic — consistent with AGWR, WHO, US EPA guidelines\n- Jurisdiction-specific requirements must be applied by the user\n- PRW schemes require formal regulatory approval beyond this assessment")
        st.markdown("### Version\n| Version | Notes |\n|---|---|\n| v1.0 | Initial release — all four classes, full engine, report export |")
        st.divider()
        st.markdown("<span style='font-size:0.82rem;color:#888;'>PurePoint v1.0 · ph2o Consulting · Assessment outputs are decision-support only and do not constitute regulatory approval.</span>", unsafe_allow_html=True)
