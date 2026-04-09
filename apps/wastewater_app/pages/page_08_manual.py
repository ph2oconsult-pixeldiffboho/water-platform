"""
apps/wastewater_app/pages/page_08_manual.py

08 User Manual — platform documentation, module reference, and engineering notes.
"""

from __future__ import annotations
import streamlit as st
from apps.ui.ui_components import render_page_header


def render() -> None:
    render_page_header("📖 User Manual", "Platform guide, module reference, and engineering notes.")

    tab_start, tab_workflow, tab_modules, tab_inputs, tab_results, tab_dt, tab_wp, tab_dil, tab_eng = st.tabs([
        "🚀 Getting Started",
        "🔄 Workflow Guide",
        "⚙️ Treatment Modules",
        "📋 Input Reference",
        "📊 Understanding Results",
        "🔬 Digital Twin",
        "⚡ WaterPoint Intelligence",
        "🧠 Decision Intelligence",
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
    # TAB 7 — WATERPOINT INTELLIGENCE
    # ─────────────────────────────────────────────────────────────────────
    with tab_wp:
        st.markdown("## WaterPoint Intelligence")
        st.markdown(
            "WaterPoint is the decision-support layer that runs on top of the engineering "
            "calculations. It interprets outputs, identifies compliance gaps, recommends "
            "upgrade pathways, and guides the user from rapid screening toward plant-specific "
            "analysis. All WaterPoint outputs are read-only — they never alter the engineering calculations."
        )

        st.info(
            "WaterPoint renders in the **Results page (Page 04)** after calculations are run. "
            "Sections E1–E8 appear below the main engineering tabs."
        )

        with st.expander("**What WaterPoint adds to the Results page**", expanded=True):
            rows = [
                ("A. System Stress", "Four metrics — System State, Load/Capacity %, Trajectory, and Confidence — with a colour-coded status badge and primary constraint summary."),
                ("B. Failure Mode Analysis", "Ranked failure modes with severity (High/Medium/Low), root cause, and recommended response."),
                ("C. Decision Layer", "Prioritised actions across three time horizons: Short-term (0–12 months operational), Medium-term (1–3 years debottlenecking), Long-term (3–10 years capital)."),
                ("D. Compliance & Regulatory Risk", "Compliance risk level, likely breach type, reputational risk, and regulatory exposure."),
                ("E1. Recommended Upgrade Stack", "Technology selection and stage-by-stage engineering rationale, feasibility rating per stage, credibility notes, and consistency checks."),
                ("E2. Alternative Pathways", "Up to three alternative technology stacks with CAPEX class and preferred use conditions."),
                ("E3. Feasibility Assessment", "Six feasibility dimensions (supply chain, operational complexity, chemical dependency, energy, integration, sludge), key risks and mitigations."),
                ("E4. Carbon & Uncertainty", "CO₂e reduction range (low/central/high bands, IPCC AR6), five uncertainty dimensions, top sensitivity drivers, decision tension."),
                ("E5. Stabilisation Options", "Low-cost stabilisation measures that may defer or de-risk capital. Each option is rated by capital class and time to result."),
                ("E6. Risk & Mitigation", "Per-technology risk profiles across four categories with mitigation strategies."),
                ("E7. Greenfield Delivery Model Comparison", "Conventional vs intensified comparison across footprint, resilience, OPEX style, and operational complexity. Shown for greenfield or intensified-stack scenarios."),
                ("E8. Refinement Prompt", "Phase 1 → Phase 2 upgrade path. Prompts the user to add plant-specific data when confidence is below 70 or constraints are present. See Refinement section below."),
            ]
            for section, desc in rows:
                st.markdown(f"**{section}**")
                st.caption(desc)
                st.markdown("")

        st.markdown("---")
        st.markdown("### Compliance Layer — Confidence Score")
        st.markdown("""
The **confidence score (0–100)** summarises how reliably the recommended stack can
achieve the compliance target under the stated conditions. It is not a probability —
it is a calibrated engineering judgement.

**How it is built:**

| Penalty category | Deduction |
|---|---|
| TN target not achievable at median | −20 |
| TN target not achievable at P95 | −20 |
| Compliance gap (stack cannot close target) | −20 |
| Nitrification uncertainty | −10 |
| Peak performance risk | −10 |
| Carbon limitation (COD:TN < 5) | −5 |
| Cold temperature (< 12°C) | −5 |
| Operator capability concern | −5 |
| Sludge production (COD ≥ 500 or TKN ≥ 60) | −5 |
| MABR / advanced configuration complexity | −5 |

**Confidence bands:**

| Score | Label | Meaning |
|---|---|---|
| 80–100 | High | Compliant under average and peak conditions |
| 60–79 | Moderate | Compliant at average; risk under peak |
| 40–59 | Low | Conditionally compliant; constraint present |
| 0–39 | Very Low | Compliance gap; escalation required |
""")

        st.markdown("---")
        st.markdown("### Diagnosis and Closure Statements")
        st.markdown("""
Every compliance output includes three structured statements:

**Diagnosis** — what is preventing or threatening compliance:
- If TN is *Conditional* (not failing at median): *"Current configuration can meet the target under average conditions but carries performance risk under peak or stressed conditions due to: [cause]."*
- If TN is *Not credible* (failing): *"Current configuration cannot meet the target under current constraints due to: [cause]."*
- If greenfield and score < 20: *"Current concept is not viable under the defined configuration and requires redesign."*

**Clarifier root-cause correction:** When SVI ≥ 140 mL/g or clarifier is flagged as overloaded, the diagnosis correctly cites **clarifier settling and hydraulic limitation** as the primary cause — not nitrification uncertainty.

**Dual-cause diagnosis:** When both a compliance failure and high sludge production coexist, the diagnosis includes a second sentence for the operational constraint.

**Closure** — what tertiary element is required to close the compliance gap (e.g. DNF, PdNA, CoMag). Only shown when escalation fires.
""")

        st.markdown("---")
        st.markdown("### Technology Stack Generation")
        st.markdown("""
The upgrade stack is generated by `stack_generator.py` using a rule-based engine
that reads plant context signals and selects technologies in priority order.

**Key selection rules:**

| Signal | Technology triggered |
|---|---|
| SVI ≥ 120 mL/g, clarifier overloaded, no storm | inDENSE (steady-state settling) |
| Storm risk (overflow_risk + wet_weather_peak) | CoMag (peak flow ballasted clarification) |
| Both SVI and storm present | CoMag → inDENSE (CoMag leads — storm priority) |
| TN ≤ 3 mg/L, carbon-limited, biofilm available | PdNA (partial denitrification-anammox) |
| TN ≤ 5 mg/L, escalation mode, DNF required | Denitrification Filter |
| Aeration-constrained | MABR (OxyFAS retrofit) |

**CoMag escalation guard:** CoMag only fires when `peak_flow_ratio ≥ 3.0` OR explicit storm/overflow flags are present. A clarifier overload signal alone at low flow ratios is insufficient — a conventional design management note is added instead.

**Hybrid ordering:** When both CoMag and inDENSE are selected, CoMag always appears first in the stack. CoMag addresses acute storm safety risk; inDENSE addresses sustained settling performance. The commissioning sequence follows the same order.
""")

        st.markdown("---")
        st.markdown("### Greenfield Pathway Comparison")
        st.markdown("""
For greenfield scenarios, WaterPoint generates two concept paths alongside the primary stack:

| Path | Description |
|---|---|
| **Conventional** | Bardenpho BNR, secondary clarifiers, tertiary P. Higher land; lower O&M complexity. |
| **Intensified** | MABR-led stack. Lower footprint; higher operational expertise required. |

**Scoring adjusts for:**
- **Footprint constraint** — abundant land boosts conventional; constrained land boosts intensified
- **Operator context** — remote location: conventional +5, intensified −5; metro: intensified +5
- **Combined effect** — constrained + metro produces the largest spread (S17: Conv 60M vs Int 75M)

**Primary stack override:** When `footprint_constraint = "abundant"` and the conventional path score ≥ intensified, the primary stack switches to conventional BNR (Bardenpho → Recycle/clarifier → Tertiary P) instead of MABR-led. This aligns the primary recommendation with the pathway comparison.

**GF redesign framing:** When greenfield score < 20, the diagnosis reads *"requires redesign"* not *"cannot meet."* This distinguishes design incompleteness from physical impossibility.
""")

        st.markdown("---")
        st.markdown("### Sludge and TKN Driver Visibility")
        st.markdown("""
**Sludge driver** appears in the top 3 confidence drivers when:
- COD ≥ 500 mg/L, OR
- TKN ≥ 60 mg/L, OR
- Sludge flag is active

Label: *"High solids production increases sludge handling, dewatering, and disposal requirements"*

**TKN removal impossibility driver** is always in the top 3 when TKN ≥ 60 mg/L or required removal ≥ 90%:

Label: *"High nitrogen removal requirement (>90%) exceeds typical biological limits"*

Both drivers are **protected** — they cannot be displaced by operational complexity or hydraulic drivers. When both are triggered together, both appear in the panel alongside whichever compliance driver leads.
""")

        st.markdown("---")
        st.markdown("### PdNA Selection Logic")
        st.markdown("""
PdNA (Partial Denitrification-Anammox) is selected when:

**Standard path (brownfield or greenfield):**
- TN target ≤ 5 mg/L
- Carbon limited (COD:TN < 5 or `carbon_limited_tn = True`)
- Biofilm available (IFAS, MBBR, or MABR in stack)
- `nh4_near_limit = False` (stable nitrification)

**Greenfield low-COD override:**
- Greenfield mode
- COD ≤ 200 mg/L
- TN target ≤ 3 mg/L

The override bypasses the `nh4_near_limit` suppression because on a greenfield design,
nitrification capacity is engineered from scratch — it is not inherited from an existing
plant with an unstable nitrification record. PdNA avoids methanol dependency and is preferred
over DNF on new plants with weak sewage.

When PdNA is selected, a mandatory carbon verification note is added to the delivery
considerations: *"Accurate characterisation of influent carbon is a critical prerequisite
for selecting the optimal nitrogen removal pathway."*
""")

        st.markdown("---")
        st.markdown("### Brownfield Asset Capture (Phase 2 Input Schema)")
        st.markdown("""
The `brownfield_asset_capture` module provides a structured ingestion schema
for plant-specific data. It validates inputs, derives engineering flags, and
produces a `plant_context` dict that bridges into the decision engine.

**Three-tier completeness:**

| Status | Condition | Behaviour |
|---|---|---|
| **COMPLETE** | All critical + secondary fields present | Full analysis; confidence up to 100 |
| **PARTIAL** | Missing secondary fields (SVI, aeration util, clarifier flag) | Analysis continues with warning; −10 per missing field |
| **INSUFFICIENT** | Missing any critical field (flow, temperature, TN target) | Analysis blocked; missing fields listed |

**Critical fields:** `average_flow_MLD`, `peak_flow_MLD`, `TN_target_mgL`, `temperature_typical_C`

**Secondary fields:** `average_SVI_mLg`, `peak_utilisation_percent`, `clarifier_limited`

**Consistency checks:** flow ordering (peak > average), temperature range (min ≤ typical ≤ max), blower count (duty ≤ total), SVI sanity (50–300 mL/g warning).

**Derived flags auto-computed:**
- `storm_flag` — peak/average ≥ 3.0
- `aeration_constraint_flag` — peak utilisation ≥ 90%
- `clarifier_constraint_flag` — SVI ≥ 140 mL/g
- `sludge_constraint_flag` — capacity_status = "overloaded"

**Data confidence score:** Starts at 100. Deducts −10 per missing secondary field, −5 per warning, −15 per estimated/default value used.
""")

        st.markdown("---")
        st.markdown("### Refinement Layer (Phase 1 → Phase 2)")
        st.markdown("""
After Phase 1 results are shown, WaterPoint evaluates whether to prompt the user
to add plant-specific data. This is **never blocking** — the user can always continue
with the current assessment.

**Trigger conditions (any one fires the prompt):**

| Condition | Threshold |
|---|---|
| Low confidence | score < 70 |
| Brownfield mode | always |
| High peak flow | ratio ≥ 2.5× |
| Tight TN target | ≤ 5 mg/L |
| Any constraint flag | clarifier, aeration, carbon, or sludge |

**Severity levels:**

| Severity | Condition | Body text |
|---|---|---|
| HIGH | score < 50, OR flow ≥ 3×, OR TN ≤ 3 | "This solution carries significant uncertainty..." |
| MEDIUM | score 50–69, OR any constraint flag | "This assessment is based on typical assumptions..." |
| LOW | otherwise triggered | "Add plant-specific data to refine this solution..." |

**Confidence uplift from plant data:**

| Data confidence | Uplift |
|---|---|
| ≥ 85 | +15 |
| 70–84 | +10 |
| 50–69 | +5 |
| < 50 | 0 |

**Caps:** Complex scenarios (flow ≥ 3× or TN ≤ 3 mg/L) — maximum 90.
Moderate scenarios — maximum 85.

After refinement, the display reads: *"Refined Confidence: XX (+YY from plant data)"*

The **Compare Initial vs Refined** toggle shows score change, stack differences,
and driver changes between Phase 1 and Phase 2 outputs.
""")

        st.markdown("---")
        st.markdown("### Carbon Verification Note")
        st.markdown("""
A mandatory carbon verification note is injected into the delivery considerations
when any of the following are true:
- COD ≤ 200 mg/L
- COD:TN ratio < 5
- TN target ≤ 3 mg/L
- PdNA is in the stack
- Carbon limitation flag is set

**Standard note:** *"Verification of biodegradable carbon availability is required
to confirm the nitrogen removal strategy and operating assumptions."*

**Strengthened note (PdNA or DNF+carbon-limited):** *"Accurate characterisation of
influent carbon is a critical prerequisite for selecting the optimal nitrogen removal
pathway and managing long-term operating requirements."*

This note is presented as a mandatory decision input, not a cost item or optional step.
""")

    # ─────────────────────────────────────────────────────────────────────
    # TAB 8 — DECISION INTELLIGENCE LAYER
    # ─────────────────────────────────────────────────────────────────────
    with tab_dil:
        st.markdown("## Decision Intelligence Layer")
        st.markdown(
            "The Decision Intelligence Layer (DIL) operates above the process optimisation engine. "
            "Its purpose is not to select a technology — that is the role of the stack generator "
            "and credibility layer. Its purpose is to determine whether available evidence is "
            "sufficient to act, where uncertainty materially affects the decision, whether further "
            "investigation has value, who ultimately carries the residual risk, and what decision "
            "boundary should be adopted."
        )
        st.info(
            "**Where to find it:** The DIL expander appears at the bottom of the Results page (Page 04) "
            "after calculations are run. It is labelled **🧠 Decision Intelligence** and shows the "
            "decision readiness status and criticality level in the expander header."
        )

        with st.expander("**Core principles**", expanded=True):
            st.markdown("""
The DIL is built on four operating principles that govern every output it produces:

**1. Good decisions are not made when uncertainty is removed.**
They are made when uncertainty is understood, bounded, and owned.

**2. Data is not valuable in itself.**
Its value depends on the decision it informs. More modelling is not always the answer.
The issue is often confidence in what data represents — not volume of data.

**3. Low confidence does not block decisions.**
It informs how they are framed. The DIL explicitly distinguishes between:
- Lack of data
- Low confidence in existing data
- Low value in collecting more data

**4. The utility always carries ultimate accountability.**
No delivery model — D&C, DBOM, Alliance, or PPP — transfers the licence obligation
or its public consequences. Risk allocation affects financial recourse. It does not
transfer the underlying obligation.
""")

        with st.expander("**Component 1 — Decision Criticality**"):
            st.markdown("""
Classifies the decision as Low, Medium, or High based on seven consequence dimensions.
Each dimension is assessed independently and contributes to a criticality score.

| Dimension | What it assesses |
|---|---|
| **Compliance** | Consequence and urgency of non-compliance; TN target severity |
| **Service** | Scale of public health and service delivery exposure |
| **Financial** | Capital programme complexity; specialist technology dependency |
| **Reputational** | Visibility of technology selection to regulators and sector peers |
| **Asset (WoL)** | Whole-of-life lock-in risk; greenfield configuration permanence |
| **Reversibility** | Cost and complexity of changing the decision after commitment |
| **Regulatory** | Trajectory of regulatory tightening; future licence amendment exposure |

**Key scoring signals:**

| Signal | Criticality effect |
|---|---|
| Metropolitan scale (≥ 50 MLD) | +2 Service |
| Regional or mid-scale (≥ 20 MLD) | +1 Service |
| Aeration system at limit | +1 |
| Overflow risk or flow ratio ≥ 2.5× | +1 |
| TN target < 5 mg/L with TN constraint | +2 Compliance |
| TN target < 8 mg/L or at limit | +1 Compliance |
| Specialist technology (MABR, CoMag, BioMag, DNF) | +1–2 Financial |
| Greenfield configuration | +2 Asset |
| Specialist membrane / magnetite system | +1 Reversibility |
| High regulatory pressure or tight TN | +1 Regulatory |

**Thresholds:** High ≥ 7 · Medium ≥ 4 · Low < 4

**Governance implications:**

| Level | Governance |
|---|---|
| High | Full board-level authorisation and independent peer review |
| Medium | Senior management review and documented engineering justification |
| Low | Standard delegated authority |
""")

        with st.expander("**Component 2 — Data Confidence Assessment**"):
            st.markdown("""
Assesses confidence in the data underlying the decision across six variables.

| Variable | What is assessed |
|---|---|
| Influent quality and variability | Peak event characterisation vs average conditions |
| Flow variability and peak events | I/I magnitude, frequency, and trajectory |
| Process performance data | Australian precedent; site-specific confirmation |
| Pilot data and scale-up | Whether site-specific pilot testing has occurred |
| N₂O emission factor | On-site monitoring vs IPCC Tier 1 default (±6× range) |
| Seasonal and temperature effects | Winter nitrification design temperature |

**Confidence levels:**

| Level | Meaning |
|---|---|
| High | Reliable data; adequate for concept-stage commitment |
| Acceptable | Adequate for concept stage; gaps noted but not blocking |
| Low | Actionable gap — targeted investigation recommended |
| Very Low | Insufficient for commitment without prior investigation |

**The high-volume/low-confidence paradox** is explicitly flagged when a variable
has high data volume but low confidence — for example, extensive flow monitoring
that does not characterise peak event frequency or I/I trajectory. More data of
the same type will not resolve this. A different type of investigation is required.

**N₂O is always Very Low confidence** because on-site monitoring is the only way
to determine it, and concept-stage decisions cannot wait for monitoring campaigns.
This is noted, accepted, and classified as Low VOI — it does not block decisions.
""")

        with st.expander("**Component 3 — Value of Information**"):
            st.markdown("""
For each uncertainty, assesses whether more data would change the decision.
This is the most operationally important DIL component — it determines what to
investigate, what to defer, and what to accept.

**Six change dimensions assessed per uncertainty:**

| Dimension | Question asked |
|---|---|
| Process selection | Would this data change which technology is recommended? |
| Sizing | Would this data change the scale of the commitment? |
| Compliance confidence | Would this data change compliance reliability? |
| Staging or timing | Would this data change the delivery sequence? |
| Lifecycle cost | Would this data materially change the economics? |
| Risk materially | Would this data change the risk profile? |

**VOI classification:**

| Classification | Meaning | Action |
|---|---|---|
| **High VOI** | Investigation may change the decision | Resolve before detailed design commitment |
| **Moderate VOI** | Investigation changes sizing or economics, not selection | Initiate in parallel with procurement |
| **Low VOI** | Proceed without investigation | Accept the uncertainty; do not delay |

**Standard VOI assignments:**

| Uncertainty | Typical classification | Reason |
|---|---|---|
| N₂O emission factor | Low VOI | Does not change selection, sizing, or compliance outcome |
| Peak wet weather flow (flow ratio ≥ 2.0×) | High VOI | Changes CoMag sizing, EQ basin need, I/I urgency |
| Blower audit (MABR scenario) | High VOI | Determines MABR vs IFAS — changes selection and CAPEX |
| Extended influent characterisation | Moderate VOI | Changes sizing, not selection |
| MABR pilot at this site | Moderate VOI | Reduces scale-up uncertainty; not mandatory for concept commitment |

**Key rule:** Low confidence and High VOI are independent. N₂O always has Very Low
confidence and Low VOI. Do not conflate them.
""")

        with st.expander("**Component 4 — Risk Ownership Mapping**"):
            st.markdown("""
Identifies who manages, shares, and ultimately owns each risk category across the
full delivery lifecycle.

**Six risk categories:**

| Category | Primary owner | Utility's irreducible exposure |
|---|---|---|
| Compliance risk | Utility | Licence obligation — cannot be contracted away |
| Technology adoption risk | OEM (specialist) / Designer (proven) | Selection decision owned at investment approval |
| Operational reliability | Operator | Operator capability is an asset management responsibility |
| Delivery and programme | Contractor | Programme delay creates compliance exposure for the utility |
| Whole-of-life asset | Utility | Technology obsolescence, membrane replacement, regulatory change |
| Customer and service | Utility | Service failure is experienced by customers regardless of delivery model |

**The residual utility position** — after all contractual risk transfers — includes:
compliance obligation, licence conditions, public health exposure, reputational
consequence of failure, and whole-of-life asset cost.

**Technology-specific notes are generated automatically:**
- MABR: membrane replacement cycle (10–15 years), biofilm establishment protocols,
  OEM guarantee requirements
- CoMag/BioMag: magnetite recovery circuit maintenance, daily logging, operator
  training as a procurement condition
- Multi-stage programmes: sequential commissioning dependencies, stage gate requirements
""")

        with st.expander("**Component 5 — Decision Boundary**"):
            st.markdown("""
Defines the conditions under which the recommended option remains acceptable.
This is the performance contract between the investment decision and the future asset.

**Seven boundary elements:**

| Element | What it defines |
|---|---|
| Acceptable performance range | TN, NH₄, TSS, and hydraulic targets to be achieved |
| Acceptable uncertainty | Which uncertainties are formally accepted at concept stage |
| Resilience margin | Headroom above the minimum compliance threshold |
| Fallback position | What happens if Stage 1 does not perform as expected |
| Monitoring requirements | Continuous and periodic monitoring required post-commissioning |
| Intervention triggers | Performance thresholds requiring escalation or process review |
| Critical assumptions | Conditions that must remain true for the decision to remain valid |

**Intervention triggers are technology-specific.** Examples:
- TN > licence × 1.2 on rolling 30-day average — initiate process review
- NH₄ > 3 mg/L sustained > 48 hours — initiate aeration system investigation
- Magnetite recovery < 90% — initiate circuit investigation and OEM notification
- Peak flow event > design capacity — log, assess, escalate to asset management

**Critical assumptions are always listed explicitly.** If any critical assumption is
later found to be incorrect, the decision boundary must be re-assessed before proceeding.
The most common critical assumption in MABR scenarios: *"Aeration system is at or near
maximum capacity — to be confirmed by blower audit."*
""")

        with st.expander("**Component 6 — Decision Readiness**"):
            st.markdown("""
The final conclusion of the DIL. Assigns one of three statuses based on the combined
output of all five preceding components.

| Status | Meaning |
|---|---|
| ✅ Ready to Proceed | Engineering case is sound; investment decision can proceed directly |
| ⚠️ Proceed with Conditions | Sufficient for investment decision; conditions carried into procurement |
| 🔴 Not Decision-Ready | Outstanding items could change the decision; resolve before commitment |

**Not Decision-Ready** is triggered when any of:
- Credibility validation items remain unresolved (`ready_for_client = False`)
- High VOI items exist that could change process selection
- Data confidence is Very Low on a decision-critical variable

**Proceed with Conditions** is triggered when:
- High VOI items affect sizing or economics but not process selection
- Data confidence gaps are actionable within the programme

**Each condition is stated explicitly** — not as a general advisory but as a
specific action with a clear scope (e.g. *"Complete blower audit before detailed
design commitment — determines MABR vs IFAS, not timing"*).

**The strategic implication** states what to do next. It distinguishes between
*"do not proceed"* and *"proceed and carry conditions into procurement"* —
because deferring a decision that is ready is itself a risk.

**Closing statement (always present):**
> *WaterPoint does not seek to eliminate uncertainty. It helps define when uncertainty
> is sufficiently understood, bounded, and owned to support action.*
""")

        with st.expander("**Limitations and appropriate use**"):
            st.markdown("""
**The DIL is an automated decision intelligence engine.** It applies structured
engineering logic calibrated against Australian municipal wastewater practice.
It does not replace engineering judgement or independent peer review.

**Appropriate use:**
- Concept-stage investment decision framing
- Structured preparation for peer review or board submission
- Identifying which investigations to commission before detailed design
- Defining monitoring and intervention requirements at procurement stage

**Not appropriate for:**
- Replacing independent peer review on High-criticality decisions
- Procurement or regulatory submission without engineering sign-off
- Decisions where plant-specific data materially differs from the inputs provided

**Input sensitivity:** All DIL outputs are conditional on the accuracy of the
`plant_context` inputs. If plant parameters are materially incorrect, re-run
with corrected values before relying on DIL conclusions.

**Scope:** The WaterPoint DIL covers the liquid phase only. Biosolids pathway
decisions are handled by a separate DIL module within BioPoint.
""")

    # ─────────────────────────────────────────────────────────────────────
    # TAB 9 — ENGINEERING NOTES
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
