"""
apps/wastewater_app/pages/page_08_manual.py

08 User Manual — platform documentation, module reference, and engineering notes.
"""

from __future__ import annotations
import streamlit as st
from apps.ui.ui_components import render_page_header


def render() -> None:
    render_page_header("📖 User Manual", "Platform guide, module reference, and engineering notes.")

    tab_start, tab_workflow, tab_modules, tab_inputs, tab_results, tab_dt, tab_eng = st.tabs([
        "🚀 Getting Started",
        "🔄 Workflow Guide",
        "⚙️ Treatment Modules",
        "📋 Input Reference",
        "📊 Understanding Results",
        "🔬 Digital Twin",
        "🔧 Engineering Notes",
    ])

    # ─────────────────────────────────────────────────────────────────────
    # TAB 1 — GETTING STARTED
    # ─────────────────────────────────────────────────────────────────────
    with tab_start:
        st.markdown("## What this platform does")
        st.markdown("""
This is a **concept-stage planning tool** for wastewater treatment upgrade and new-build projects.
It is designed for use during options investigation, master planning, and early feasibility —
not for detailed design.

**What it calculates:**
- Capital cost (CAPEX) and lifecycle cost estimates for 12 treatment technologies
- Annual energy demand and specific energy (kWh/ML)
- Greenhouse gas emissions — Scope 1 (process), Scope 2 (electricity), carbon cost
- Sludge production (kg DS/day and t DS/year)
- Effluent quality achievable at screening level
- Qualitative risk assessment (technical, regulatory, operational, implementation)

**What it does not replace:**
- Detailed process design or hydraulic modelling
- Site-specific geotechnical or civil assessments
- Vendor quotes (CAPEX figures are order-of-magnitude ±30–50%)
- Regulatory pre-consultation or permit applications
""")

        st.info("💡 **Accuracy level:** All outputs are screening-level estimates suitable for comparing options. "
                "CAPEX estimates carry ±30–50% uncertainty. Use for ranking and shortlisting only.")

        st.markdown("## Quick start (5 minutes)")
        st.markdown("""
1. **Page 01 — Project Setup:** Create a new project. Give it a name and select a planning scenario (e.g. *Nutrient Limit Tightening*).
2. **Page 02 — Inputs:** Enter your design flow (MLD) and influent quality. You can use the defaults for a first pass.
3. **Page 03 — Treatment Selection:** Choose a treatment technology (start with *Conventional BNR*) and click Save.
4. **Page 04 — Results:** Click **Run Calculations**. Review energy, cost, carbon, and risk outputs.
5. **Page 01 — Add a second scenario:** Duplicate your scenario, change the technology to *MBR*, and re-run.
6. **Page 05 — Compare:** See both scenarios side by side.
""")

        st.markdown("## Platform limits")
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("""
**Suitable for:**
- Options screening (2–10 alternatives)
- Relative cost and carbon comparisons
- Planning scenario sensitivity analysis
- Concept-level technology selection
- Early stakeholder communication
""")
        with col2:
            st.markdown("""
**Not suitable for:**
- Detailed design or hydraulic sizing
- Procurement or contract cost estimates
- Regulatory compliance modelling
- Site-specific ground investigation
- Detailed carbon accounting for reporting
""")

    # ─────────────────────────────────────────────────────────────────────
    # TAB 2 — WORKFLOW GUIDE
    # ─────────────────────────────────────────────────────────────────────
    with tab_workflow:
        st.markdown("## Page-by-page workflow")

        with st.expander("**Page 01 — Project Setup**", expanded=True):
            st.markdown("""
**Purpose:** Create and manage projects and scenarios.

A **project** represents a plant or study (e.g. *Northside WWTP Upgrade*).
A **scenario** is one option you want to evaluate (e.g. *Option A — BNR Upgrade*).
You can have multiple scenarios in one project and compare them on Page 05.

**Planning scenarios** adjust which metrics are highlighted in the results:
| Planning Scenario | Highlighted metric |
|---|---|
| Capacity Expansion | Cost |
| Nutrient Limit Tightening | Effluent quality |
| Energy Optimisation | Specific energy (kWh/ML) |
| Carbon Reduction | Total tCO₂e/year |
| Biosolids Constraints | Sludge production |
| Reuse / PRW Integration | Effluent TSS and reuse suitability |

**Tips:**
- Create one scenario per technology option you want to evaluate
- Use the *Duplicate Scenario* button to copy inputs before changing the technology
- Scenarios are saved automatically when you run calculations
""")

        with st.expander("**Page 02 — Plant Inputs**"):
            st.markdown("""
**Purpose:** Define the plant design basis — flows, water quality, and economic parameters.

These inputs are shared across all scenarios in the project. If you need different
influent assumptions for different scenarios, create separate projects.

**Critical inputs:**
- **Design flow (MLD):** The average dry weather flow. Peak flow is calculated automatically (×2.5).
- **Influent BOD, TN, TP, TSS:** Used directly in all technology calculations.
- **Effluent targets:** Determine removal percentages shown in results.
- **Electricity price ($/kWh):** Affects OPEX and carbon cost calculations.
- **Carbon price ($/tCO₂e):** Used for carbon cost in the results and comparison pages.

**Default values** are typical Australian municipal wastewater. Change them to match your site.
""")

        with st.expander("**Page 03 — Treatment Selection**"):
            st.markdown("""
**Purpose:** Select one or more treatment technologies and configure their parameters.

You can select **multiple technologies** in sequence (e.g. BNR + CPR + Tertiary Filtration).
The platform sums CAPEX, OPEX, energy, sludge, and carbon across the sequence.

**Configuration panels** appear for each selected technology. Key parameters to consider:
- SRT, MLSS, and temperature affect sludge yield and energy
- Retrofit vs greenfield affects CAPEX significantly (IFAS/MBBR)
- Chemical P removal adds OPEX but improves TP compliance confidence
- CHP efficiency and feed VS fraction drive AD+CHP energy outputs

**Save** your selection before moving to Page 04.
""")

        with st.expander("**Page 04 — Results**"):
            st.markdown("""
**Purpose:** View full engineering, cost, carbon, and risk outputs for the active scenario.

**Tabs:**
- **⚙️ Engineering:** Effluent quality, removal percentages, reactor sizing, energy breakdown, sludge production, per-technology notes and assumptions
- **💰 Cost:** CAPEX breakdown, annual OPEX, lifecycle cost (NPV over planning horizon)
- **🌿 Carbon & Energy:** Scope 1 (process N₂O/CH₄), Scope 2 (electricity), total tCO₂e/year, carbon cost
- **⚠️ Risk:** Risk matrix across technical, regulatory, operational, and implementation dimensions

**Calibration toggle** (appears when plant data has been uploaded on Page 07):
Switch between *Default model* and *Calibrated model* to see how plant-specific data changes the outputs.

**Re-run calculations** after changing inputs on Page 02 or technology parameters on Page 03.
""")

        with st.expander("**Page 05 — Compare Scenarios**"):
            st.markdown("""
**Purpose:** Side-by-side comparison of all calculated scenarios in the project.

Scenarios must have been calculated (Page 04) before they appear here.

**Comparison outputs:**
- CAPEX and OPEX bar charts
- Lifecycle cost comparison
- Energy intensity (kWh/ML)
- Carbon intensity (tCO₂e/year)
- Sludge production (t DS/year)
- Risk score

**Tips:**
- Scenarios with ❌ are not yet calculated — go to Page 04 and run them first
- Calibrated scenarios are flagged with 🔬 in the comparison table
""")

        with st.expander("**Page 06 — Report**"):
            st.markdown("""
**Purpose:** Generate a structured feasibility report for the selected scenarios.

The report includes:
1. Executive summary
2. Project description
3. Design basis (flows and loads)
4. Treatment options assessed
5. Results summary (cost, energy, carbon, risk)
6. Technology comparison table
7. Risk assessment
8. Plant Data Review and Calibration (if plant data uploaded)
9. Model assumptions appendix

Select which scenarios to include and click **Generate Report**.
Download as a structured document for client or internal review.
""")

        with st.expander("**Page 07 — Plant Data & Calibration**"):
            st.markdown("""
**Purpose:** Upload real plant operational data to calibrate the model against actual performance.

This is the *digital twin* module. It adjusts model assumptions (SAE, sludge yield, alpha factor)
to match observed plant behaviour, making the results more representative of your specific site.

**Workflow:**
1. Upload a CSV of plant operational data (flow, NH₄, power, biogas, etc.)
2. The platform cleans the data and calculates KPIs
3. Review calibration factors and accept/reject each one
4. Apply accepted factors — results on Page 04 now reflect plant-specific performance

See the **Digital Twin** tab in this manual for detailed guidance.
""")

    # ─────────────────────────────────────────────────────────────────────
    # TAB 3 — TREATMENT MODULES
    # ─────────────────────────────────────────────────────────────────────
    with tab_modules:
        st.markdown("## Treatment module reference")
        st.markdown("All 12 modules are screening-level. CAPEX figures are indicative order-of-magnitude only.")

        modules = [
            {
                "name": "Conventional BNR (Activated Sludge)",
                "code": "bnr",
                "category": "Biological Treatment",
                "description": "Activated sludge with anaerobic/anoxic/aerobic zones for combined nitrogen and phosphorus removal. Most common municipal wastewater treatment technology globally.",
                "best_for": "Standard municipal plants, broad applicability, large reference base",
                "key_assumptions": "SRT 12 days, MLSS 4,000 mg/L, alpha 0.55, SAE 1.8 kg O₂/kWh, N₂O EF 1.6% of N removed",
                "key_outputs": "Effluent TN 10 mg/L, TP 0.5–0.8 mg/L, reactor volume, clarifier area, O₂ demand",
                "limitations": "Clarifiers required (large footprint). BioP unreliable in industrial catchments.",
                "energy": "0.3–0.6 kWh/m³",
                "capex_driver": "Reactor tankage + secondary clarifiers",
            },
            {
                "name": "Membrane Bioreactor (MBR)",
                "code": "mbr",
                "category": "Biological Treatment",
                "description": "Activated sludge with submerged membranes replacing secondary clarifiers. Produces high-quality effluent with pathogen LRV credits.",
                "best_for": "Reuse projects, tight effluent limits, land-constrained sites",
                "key_assumptions": "Design flux 25 LMH, SRT 15 days, MLSS 10,000 mg/L, SAD 0.30 m³/m²/h",
                "key_outputs": "Effluent TSS <1 mg/L, BOD <3 mg/L, 4-log Cryptosporidium LRV, membrane area",
                "limitations": "Highest energy of biological options (scour aeration). Membrane replacement is dominant OPEX.",
                "energy": "0.6–1.2 kWh/m³",
                "capex_driver": "Membrane cassettes (dominant) + bioreactor",
            },
            {
                "name": "Aerobic Granular Sludge (Nereda®)",
                "code": "granular_sludge",
                "category": "Biological Treatment",
                "description": "Dense granular biomass in a sequencing batch reactor. Simultaneous N and P removal. No secondary clarifier required.",
                "best_for": "Low footprint, low sludge, energy optimisation",
                "key_assumptions": "y_obs 0.22 kgVSS/kgBOD, MLSS 8,000 mg/L, alpha 0.65, SND 60%",
                "key_outputs": "~35% footprint saving vs CAS, 40% lower sludge than CAS, TN 10 mg/L",
                "limitations": "Granule stability at T<12°C. ~80 full-scale plants — fewer references than CAS/MBR.",
                "energy": "0.25–0.45 kWh/m³",
                "capex_driver": "SBR tankage (3+ reactors) + blower + decanter control",
            },
            {
                "name": "IFAS / MBBR Retrofit",
                "code": "ifas_mbbr",
                "category": "Biological Treatment",
                "description": "Media carriers added to existing aeration basins (IFAS) to boost nitrification capacity without new concrete. MBBR standalone uses carriers as sole biomass support.",
                "best_for": "Capacity upgrades under land constraints, minimal disruption to operations",
                "key_assumptions": "Fill ratio 0.35, media surface area 500 m²/m³, nit rate 2.0 g/m²/day at 20°C, Arrhenius theta 1.07",
                "key_outputs": "Nitrification capacity uplift, media area required, no new tankage (IFAS retrofit)",
                "limitations": "Clarifiers still required (IFAS). TN removal limited without dedicated anoxic zone.",
                "energy": "0.3–0.55 kWh/m³",
                "capex_driver": "Carrier media + blower upgrade (IFAS: no tankage)",
            },
            {
                "name": "Anaerobic Treatment (AnMBR / UASB)",
                "code": "anmbr",
                "category": "Biological Treatment",
                "description": "Anaerobic digestion of the wastewater stream with biogas recovery. Net energy producer. Very low sludge yield. Requires aerobic post-treatment for nutrient removal.",
                "best_for": "Warm climates, high-strength wastewaters, energy recovery focus",
                "key_assumptions": "0.35 m³ CH₄/kg COD destroyed, CHP efficiency 38%, fugitive CH₄ 3%",
                "key_outputs": "Net energy surplus, sludge <10% of aerobic equivalent, biogas production",
                "limitations": "Temperature sensitive (<20°C). Nutrient removal requires separate post-treatment step.",
                "energy": "Net surplus: −0.1 to −0.5 kWh/m³",
                "capex_driver": "Reactor + CHP unit (+ membranes for AnMBR)",
            },
            {
                "name": "Sidestream PN/A (Anammox)",
                "code": "sidestream_pna",
                "category": "Biological Treatment",
                "description": "Partial nitritation/Anammox reactor treating reject water from sludge dewatering. Removes 85% of centrate NH₄ before it recycles to the main plant. No external carbon needed.",
                "best_for": "Plants with anaerobic digestion + dewatering, N load reduction, energy optimisation",
                "key_assumptions": "O₂ per kg N = 1.9 kg (vs 4.57 full N removal), N₂O EF 4%, Anammox yield 0.03 kgVSS/kgN",
                "key_outputs": "Main-plant N load reduction 15–30%, energy saved on main plant, very low sludge",
                "limitations": "Anammox sensitive to inhibitors and temperature. 3–6 month startup. Sidestream only.",
                "energy": "0.05–0.15 kWh/m³ of main plant flow",
                "capex_driver": "Reactor + DO/pH/N₂O control system",
            },
            {
                "name": "Mobile Organic Biofilm (MOB)",
                "code": "mob",
                "category": "Biological Treatment",
                "description": "Biodegradable carrier process with 40–60% lower sludge yield than CAS. Carriers are consumed over time, eliminating media replacement. Retrofit-compatible.",
                "best_for": "Sludge minimisation, retrofit into existing basins, reduced disposal costs",
                "key_assumptions": "Carrier fill 0.30, BOD loading 8 g/m²/day, y_obs 0.15 kgVSS/kgBOD",
                "key_outputs": "Sludge 40–60% lower than CAS, nitrification and denitrification",
                "limitations": "Emerging technology — limited large-scale references. Carrier replenishment is an ongoing cost.",
                "energy": "0.3–0.55 kWh/m³",
                "capex_driver": "Carrier media initial charge + blower",
            },
            {
                "name": "Chemical Phosphorus Removal (CPR)",
                "code": "cpr",
                "category": "Tertiary Treatment",
                "description": "FeCl₃ or alum dosing with lamella/RSF separator for TP polishing to <0.1 mg/L. Added as a tertiary step after biological treatment.",
                "best_for": "TP licence < 0.5 mg/L, unreliable biological P removal, sensitive receiving waters",
                "key_assumptions": "FeCl₃ dose 2.5 mol Fe/mol P, chemical sludge 0.78 kg DS/kg FeCl₃",
                "key_outputs": "TP <0.1 mg/L, chemical sludge quantity, coagulant consumption",
                "limitations": "Generates chemical sludge for disposal. Does not remove dissolved organic P.",
                "energy": "0.02 kWh/m³",
                "capex_driver": "Dosing system + separator",
            },
            {
                "name": "Tertiary Filtration",
                "code": "tertiary_filt",
                "category": "Tertiary Treatment",
                "description": "Depth filtration (RSF, deep bed, or cloth/disc) polishing TSS to 5 mg/L. Enables UV disinfection and reuse pathways.",
                "best_for": "Reuse pre-treatment, UV disinfection prerequisite, TSS licence <5 mg/L",
                "key_assumptions": "Hydraulic loading 8 m/hr, backwash 3% of filtered flow",
                "key_outputs": "Effluent TSS 5 mg/L, filter area, optional UV dose",
                "limitations": "Does not remove dissolved constituents. Backwash water recycles to headworks.",
                "energy": "0.04–0.07 kWh/m³",
                "capex_driver": "Filter cells + backwash system",
            },
            {
                "name": "Advanced Reuse (MF/UF + RO + UV/AOP)",
                "code": "adv_reuse",
                "category": "Reuse",
                "description": "Full advanced treatment train for Class A+ non-potable reuse or indirect potable reuse. Removes PFAS, TDS, trace organics, and pathogens.",
                "best_for": "Non-potable industrial reuse, IPR planning, PFAS reduction in product water",
                "key_assumptions": "MF flux 60 LMH, RO flux 17 LMH, RO recovery 80%, UV dose 40 mJ/cm²",
                "key_outputs": "Product flow (80% of feed), effluent TSS <0.1 mg/L, TDS <50 mg/L, PFAS removed",
                "limitations": "Highest energy and CAPEX of all modules. RO concentrate management required.",
                "energy": "0.8–1.5 kWh/m³",
                "capex_driver": "RO membranes + high-pressure pumps",
            },
            {
                "name": "Anaerobic Digestion + CHP",
                "code": "ad_chp",
                "category": "Solids / Energy Recovery",
                "description": "Mesophilic anaerobic digestion of biosolids with biogas recovery and CHP electricity generation. Reduces sludge 35–45% and offsets 30–60% of plant electricity.",
                "best_for": "Plants with sludge disposal challenges, energy recovery, carbon reduction",
                "key_assumptions": "Biogas yield 0.75 m³/kg VS, CH₄ fraction 65%, CHP efficiency 38%/45%, HRT 20 days",
                "key_outputs": "Sludge mass reduction %, electricity generated (kWh/day), reject water NH₄ load",
                "limitations": "High CAPEX. Reject water increases liquid train N load. Fugitive CH₄ is key carbon risk.",
                "energy": "Net generator: −0.2 to −0.5 kWh/m³",
                "capex_driver": "Digester tanks + CHP engine",
            },
            {
                "name": "Thermal Biosolids Treatment",
                "code": "thermal_biosolids",
                "category": "Solids / Thermal",
                "description": "Incineration, pyrolysis, or gasification of dewatered biosolids. Eliminates land application, destroys PFAS (>99% at ≥850°C), reduces biosolids to ash.",
                "best_for": "PFAS-affected biosolids, sites with restricted land application, no other disposal pathway",
                "key_assumptions": "Incineration: >850°C, 2s residence time, N₂O EF 0.5 kg/t DS, biogenic CO₂ excluded",
                "key_outputs": "PFAS destruction efficiency, ash quantity, scope 1 N₂O, energy recovery potential",
                "limitations": "Highest CAPEX/OPEX. Air permit required. Supplemental fuel needed if cake TS < 20%.",
                "energy": "Net consumer: 0.1–0.3 kWh/kg DS",
                "capex_driver": "Thermal treatment unit + flue gas scrubbing",
            },
        ]

        for m in modules:
            with st.expander(f"**{m['name']}**  ·  *{m['category']}*  ·  `{m['code']}`"):
                col1, col2 = st.columns([3, 2])
                with col1:
                    st.markdown(f"**Description:** {m['description']}")
                    st.markdown(f"**Best for:** {m['best_for']}")
                    st.markdown(f"**Limitations:** {m['limitations']}")
                with col2:
                    st.markdown(f"**Typical energy:** {m['energy']}")
                    st.markdown(f"**CAPEX driver:** {m['capex_driver']}")
                st.markdown(f"**Key assumptions:** {m['key_assumptions']}")
                st.markdown(f"**Key outputs:** {m['key_outputs']}")

    # ─────────────────────────────────────────────────────────────────────
    # TAB 4 — INPUT REFERENCE
    # ─────────────────────────────────────────────────────────────────────
    with tab_inputs:
        st.markdown("## Input parameters reference")

        st.markdown("### Design flows")
        st.markdown("""
| Parameter | Typical range | Notes |
|---|---|---|
| Design flow (MLD) | 0.5 – 500 | Average dry weather flow (ADWF) |
| Peak flow factor | 2.0 – 3.0 | Applied to ADWF for clarifier/membrane sizing |
| Planning horizon | 20 – 30 years | Used for lifecycle cost NPV calculation |
""")

        st.markdown("### Influent water quality — typical Australian municipal")
        st.markdown("""
| Parameter | Typical range | Platform default |
|---|---|---|
| BOD (mg/L) | 150 – 350 | 250 |
| COD (mg/L) | 350 – 700 | 500 |
| TSS (mg/L) | 180 – 380 | 280 |
| NH₄-N (mg/L) | 25 – 55 | 35 |
| TKN (mg/L) | 35 – 65 | 45 |
| TP (mg/L) | 4 – 12 | 7 |
| Temperature (°C) | 15 – 28 | 20 |
""")

        st.markdown("### Effluent targets")
        st.markdown("""
| Parameter | Typical licence | Stringent (reuse) |
|---|---|---|
| BOD (mg/L) | 20 | 5 |
| TSS (mg/L) | 30 | 2 |
| TN (mg/L) | 10 | 5 |
| NH₄-N (mg/L) | 5 | 1 |
| TP (mg/L) | 1.0 | 0.1 |
""")

        st.markdown("### Economic parameters")
        st.markdown("""
| Parameter | Typical range | Notes |
|---|---|---|
| Electricity price ($/kWh) | 0.10 – 0.25 | AU grid commercial rate 2024 |
| Sludge disposal ($/t DS) | 200 – 400 | Wet cake equivalent |
| Carbon price ($/tCO₂e) | 25 – 75 | ACCU market; used for carbon cost calculation |
| Discount rate | 5 – 8% | Used for NPV lifecycle cost |
""")

        st.warning("⚠️ **CAPEX accuracy:** All CAPEX estimates are order-of-magnitude (±30–50%). "
                   "Unit rates are based on Australian 2024 indicative costs. "
                   "Always obtain vendor quotes for any option proceeding to procurement.")

    # ─────────────────────────────────────────────────────────────────────
    # TAB 5 — UNDERSTANDING RESULTS
    # ─────────────────────────────────────────────────────────────────────
    with tab_results:
        st.markdown("## Understanding the results")

        st.markdown("### Engineering tab")
        st.markdown("""
**Removal percentages** (TN%, BOD%) are flow-weighted mass balances:

> Removal % = (Σ(Q × C_in) − Σ(Q × C_out)) / Σ(Q × C_in) × 100

This correctly weights high-flow periods more than low-flow periods.

**Energy intensity (kWh/kL)** is total electrical consumption divided by design flow.
It does not include energy credit from CHP generation — see *Net energy* for that.

**Sludge production (t DS/year)** is biological sludge only for biological modules,
or chemical sludge for CPR. AD+CHP reports the digested output (post VS destruction).

**Per-technology notes** contain the assumptions actually used in your calculation.
Always review these — they confirm what the model assumed for your specific inputs.
""")

        st.markdown("### Cost tab")
        st.markdown("""
**CAPEX** covers primary mechanical and civil items only. It excludes:
- Land acquisition
- Site preparation and civil works
- Electrical supply upgrades
- Project management and design fees
- Contingency (typically add 30–40% for early estimates)
- GST

**Lifecycle cost** = CAPEX + NPV of OPEX over the planning horizon at the discount rate.

**OPEX** includes electricity, chemicals, sludge disposal, and major maintenance items.
It excludes: staffing, minor maintenance, insurance, rates, and compliance monitoring.
""")

        st.markdown("### Carbon tab")
        st.markdown("""
| Emission type | What it covers | Key uncertainty |
|---|---|---|
| **Scope 1 — N₂O** | Biological N₂O from nitrification/denitrification | ±3–5× (IPCC Tier 1 EF range 0.005–0.05 kg N₂O/kg N) |
| **Scope 1 — CH₄** | Fugitive methane from biological reactors and digesters | ±2× depending on cover integrity |
| **Scope 2** | Grid electricity consumption × grid emission factor | Grid EF varies by state and time |
| **Carbon cost** | Total tCO₂e/yr × carbon price ($/tCO₂e) | Depends on carbon price assumption |

> **Important:** N₂O is the largest carbon uncertainty in wastewater treatment.
> The IPCC Tier 1 emission factor (0.016 kg N₂O/kg N removed) carries a range of 0.005–0.05.
> Site-specific N₂O measurement is recommended before detailed carbon accounting.
""")

        st.markdown("### Risk tab")
        st.markdown("""
Risk dimensions are rated Low / Moderate / High / Very High:

| Dimension | What it assesses |
|---|---|
| **Reliability** | Process uptime, sensitivity to upsets, operational track record |
| **Regulatory** | Permit complexity, likelihood of licence compliance |
| **Technology maturity** | Established / Commercial / Emerging / R&D |
| **Operational complexity** | Skill level required, control systems needed |
| **Site constraints** | Footprint, buffer distances, odour sensitivity |
| **Implementation** | Supply chain, lead times, construction complexity |

The risk score is the average of scored dimensions (Low=1, Moderate=2, High=3, Very High=4).
""")

    # ─────────────────────────────────────────────────────────────────────
    # TAB 6 — DIGITAL TWIN
    # ─────────────────────────────────────────────────────────────────────
    with tab_dt:
        st.markdown("## Digital twin and calibration (Page 07)")
        st.markdown("""
The digital twin module adjusts model assumptions to match actual plant performance.
This improves result accuracy when evaluating upgrades to an existing plant.
""")

        st.markdown("### CSV upload format")
        st.markdown("""
Upload a CSV file with a `timestamp` column and any of the following columns.
You do not need all columns — the platform handles partial datasets.

| Column name | Units | Description |
|---|---|---|
| `timestamp` | date or datetime | Required — date of observation |
| `flow_mld` | ML/day | Influent flow |
| `flow_ls` | L/s | Auto-converted to ML/day |
| `flow_m3_hr` | m³/hr | Auto-converted to ML/day |
| `influent_bod_mg_l` | mg/L | Influent BOD |
| `influent_nh4_mg_l` | mg/L | Influent NH₄-N |
| `influent_tkn_mg_l` | mg/L | Influent TKN |
| `effluent_nh4_mg_l` | mg/L | Effluent NH₄-N |
| `blower_power_kw` | kW | Blower power demand |
| `aeration_airflow_nm3_hr` | Nm³/hr | Aeration airflow |
| `sludge_production_t_ds_day` | t DS/day | WAS production |
| `biogas_m3_day` | m³/day | Biogas production |
| `mlss_mg_l` | mg/L | Mixed liquor SS |
| `do_aerobic_mg_l` | mg/L | Aerobic zone DO |
""")

        st.markdown("### Data quality checks")
        st.markdown("""
The platform automatically checks for:
- **Duplicate timestamps** — keeps the last value, warns you
- **Stuck sensor** — 10+ consecutive identical values flagged
- **Physical bounds violations** — impossible values set to NaN
- **Cross-parameter errors** — NH₄ > TKN or COD < BOD flagged and nulled
- **Isolated spikes** — single-row extreme values (likely sensor errors)
- **Wet weather events** — 3+ consecutive elevated flow values kept (real events, not spikes)
""")

        st.markdown("### Calibration factors")
        st.markdown("""
Three parameters can be calibrated from plant data:

| Parameter | Default | What it affects |
|---|---|---|
| **SAE** (kg O₂/kWh) | 1.8 | Aeration energy — the most directly observable parameter |
| **Alpha factor** | 0.55 | Process-water O₂ transfer vs clean water |
| **Observed sludge yield** (kgVSS/kgBOD) | 0.38 | Sludge production and reactor sizing |

**Minimum observations:** 14 paired data points required before a calibration factor is applied.
**Low-confidence factors** (sparse data) are flagged and should be reviewed before accepting.

> **Note:** Calibration represents an annual average.
> Seasonal variation (e.g. winter alpha vs summer alpha) is not captured at screening level.
""")

        st.info("💡 **Advisory outputs:** Average MLSS, SRT, and NH₄:TKN ratio are shown as advisory values. "
                "Update these directly in Page 02 inputs — they do not override model assumptions automatically.")

    # ─────────────────────────────────────────────────────────────────────
    # TAB 7 — ENGINEERING NOTES
    # ─────────────────────────────────────────────────────────────────────
    with tab_eng:
        st.markdown("## Engineering notes and key references")

        with st.expander("**Sludge yield model**"):
            st.markdown("""
All biological modules use the endogenous decay model from Metcalf & Eddy (2014) Eq. 7-57:

> y_obs = Y_true / (1 + kd × SRT)

Where:
- Y_true = 0.60 kgVSS/kgBOD (true yield, domestic wastewater)
- kd = 0.08 /day at 20°C (endogenous decay coefficient)
- Temperature correction: kd(T) = kd(20°C) × 1.04^(T−20)

MBR uses a lower observed yield (0.25 kgVSS/kgBOD) reflecting longer SRT operation.
AGS uses 0.22 kgVSS/kgBOD (van Dijk 2020) reflecting granule structure effects.
""")

        with st.expander("**Oxygen demand model**"):
            st.markdown("""
Oxygen demand is calculated as:

> O₂ = O₂_carbonaceous + O₂_nitrification − O₂_denitrification_credit

- **Carbonaceous:** 1.42 × BOD_removed × (1 − 1.42 × y_obs) — Metcalf Eq. 8-47
- **Nitrification:** 4.57 kg O₂ / kg NH₄-N oxidised
- **Denitrification credit:** 2.86 kg O₂ / kg NO₃-N denitrified

Aeration energy = O₂_demand / SAE_process, where SAE_process = SAE_clean × alpha
""")

        with st.expander("**N₂O emission factors**"):
            st.markdown("""
N₂O emission factors used in this platform:

| Process | EF (kg N₂O/kg N removed) | Source |
|---|---|---|
| Conventional BNR / CAS | 0.016 | IPCC 2019 Tier 1 central estimate |
| MBR | 0.016 | IPCC 2019 Tier 1 |
| AGS | 0.016 | IPCC 2019 Tier 1 |
| Sidestream PN/A | 0.04 | Lackner et al. 2014 (elevated due to NO₂ intermediate) |
| Incineration | 0.50 kg/t DS | IPCC 2019 Refinement Vol.5 |

**Important:** The IPCC Tier 1 range is 0.005–0.05 kg N₂O/kg N — a 10-fold range.
N₂O is the dominant carbon uncertainty in wastewater treatment.
Site-specific measurement (online N₂O analysers, 12-month campaign) is recommended
before finalising carbon accounts for any detailed assessment.
""")

        with st.expander("**CAPEX unit rate basis**"):
            st.markdown("""
All CAPEX figures are based on indicative Australian construction costs (2024, ex-GST).
They represent the installed cost of the primary treatment components only.

**Not included in any CAPEX estimate:**
- Land acquisition
- Site preparation, earthworks, piling
- Electrical reticulation and supply upgrade
- Instrumentation and control (except where explicitly listed)
- Project management, engineering design, and documentation fees
- Community engagement and approvals
- Contingency (add 30–40% for early-stage estimates per AS 4342)
- GST

**Recommended escalation:**
- Add 15% for projects in regional/remote locations
- Add 20–30% for works requiring full dewatering or bypass
- Add 10% per year for cost escalation beyond 2024
""")

        with st.expander("**Key references**"):
            st.markdown("""
- Metcalf & Eddy / Tchobanoglous et al. (2014) *Wastewater Engineering*, 5th ed. McGraw-Hill
- WEF MOP 32 (2010) *Nutrient Removal*
- WEF MOP 35 (2011) *Biofilm Reactors*
- WEF MOP 36 (2012) *Membrane Bioreactors*
- Judd, S. (2011) *The MBR Book*, 2nd ed. Elsevier
- de Kreuk et al. (2007) Aerobic granular sludge — *Water Research* 41(18)
- van Dijk et al. (2020) Full-scale Nereda performance — *Water Science & Technology*
- Lackner et al. (2014) Global survey of Anammox full-scale plants — *Water Research* 55
- IPCC (2019) *2019 Refinement to the 2006 IPCC Guidelines*, Volume 5, Chapter 6
- NRMMC/EPHC (2008) *Australian Guidelines for Water Recycling*
- AS/NZS 4342 (2014) Lifecycle costing — principles and procedures
""")

        st.markdown("---")
        st.caption("Water Utility Planning Platform — v1.0 — Concept Stage Planning Tool")
        st.caption("All outputs are screening-level estimates only. Not suitable for detailed design, procurement, or regulatory submissions.")
