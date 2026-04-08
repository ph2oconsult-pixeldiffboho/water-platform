"""
apps/biosolids_app/pages/page_06_manual.py
BioPoint V1 — User Manual.

Tab structure mirrors WaterPoint manual:
  Getting Started | Workflow Guide | Pathway Modules | Input Reference |
  Understanding Results | Pyrolysis Detail | BioPoint Intelligence | Engineering Notes
"""
import streamlit as st


def render():
    st.markdown("## 📖 User Manual")
    st.caption("Platform guide, module reference, and engineering notes.")
    st.divider()

    tabs = st.tabs([
        "🚀 Getting Started",
        "🔄 Workflow Guide",
        "⚙️ Pathway Modules",
        "📋 Input Reference",
        "📊 Understanding Results",
        "📈 Pyrolysis Detail",
        "⚡ BioPoint Intelligence",
        "🔧 Engineering Notes",
    ])

    # ── TAB 1: GETTING STARTED ─────────────────────────────────────────────
    with tabs[0]:
        st.markdown("## What this platform does")
        st.markdown(
            "BioPoint is a **concept-stage biosolids decision engine** for wastewater "
            "treatment utilities, consultants, and owner's engineers. It is designed for "
            "use during options investigation, master planning, and early feasibility — "
            "not for detailed process design."
        )

        st.markdown("### What it calculates")
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("""
- Mass balance for 11 biosolids pathways
- Drying energy demand vs feedstock energy available
- Drying feasibility gate (PASS / FAIL) per pathway
- Mainstream coupling: NH₄, COD, TP return loads
- Siting flexibility: on-site vs off-site classification
- Preconditioning benefit: DS% uplift scenarios
            """)
        with col2:
            st.markdown("""
- ITS/PFAS classification: Level 1–4 per pathway
- Pyrolysis operating envelope: 300–800°C continuous curve
- Biochar value: yield, nutrients, market grade, revenue
- Energy vs product trade-off ($/tDS across temperatures)
- Vendor claim validation: SUPPORTED / CONDITIONAL / REFUTED
- Carbon and ESG signal with green finance eligibility
            """)

        st.markdown("### What it does not replace")
        st.markdown("""
- Detailed process design or hydraulic modelling
- Site-specific geotechnical or civil assessments
- Vendor quotes (CAPEX figures are order-of-magnitude ±30%)
- Regulatory pre-consultation or permit applications
- Full lifecycle assessment (ISO 14040/14044)
- Legal or compliance advice on PFAS obligations
        """)

        st.info(
            "**Intended use:** BioPoint outputs are appropriate for Stage 1–2 "
            "options analysis, business case development, and investment sequencing. "
            "All figures should be validated against site-specific data before "
            "financial commitment."
        )

        st.markdown("### Quick start")
        st.markdown("""
1. Navigate to **⚙️ Inputs** in the sidebar
2. Enter your feedstock characteristics (DS%, GCV, VS%, throughput)
3. Set site infrastructure and economic parameters
4. Click **▶ Run BioPoint Analysis**
5. Review ranked pathways in **📊 Pathway Rankings**
6. Explore drying constraints in **🔥 Drying & Coupling**
7. Check PFAS classification in **🛡️ ITS & PFAS**
8. Review pyrolysis trade-off in **📈 Pyrolysis Envelope**

*Or upload existing data via **📂 Load Data** to pre-fill inputs automatically.*
        """)

    # ── TAB 2: WORKFLOW GUIDE ──────────────────────────────────────────────
    with tabs[1]:
        st.markdown("## Recommended workflow")

        st.markdown("### Step 1 — Diagnose the system constraint first")
        st.markdown("""
Before reviewing pathway rankings, check the **system classification** at the
top of the results page:

| Classification | Meaning | Primary action |
|---|---|---|
| **Water-removal constrained** | DS% < 20% — all thermal blocked | Install dewatering first |
| **Drying constrained** | DS% 20–30% — most thermal fail | Evaluate preconditioning |
| **Thermally viable** | DS% ≥ 30% — thermal pathways accessible | Proceed to technology selection |

BioPoint enforces a **drying feasibility gate**. No thermal pathway can rank as
Preferred unless it can demonstrate energy viability at the current feed DS%.
This is a physical constraint, not a preference — it cannot be overridden.
        """)

        st.markdown("### Step 2 — Review preconditioning options")
        st.markdown("""
Navigate to **🔥 Drying & Coupling → Preconditioning pathways**.

This shows the DS% achievable through polymer optimisation, filter press,
THP, and THP + filter press — and the drying energy saving at each step.

The 28% DS threshold is the gateway to incineration. The 42–48% DS range
is the gateway to pyrolysis energy neutrality. Identify which scenario
reaches your target and factor the CAPEX into the investment sequence.
        """)

        st.markdown("### Step 3 — Check PFAS status before finalising strategy")
        st.markdown("""
Navigate to **🛡️ ITS & PFAS**.

If PFAS status is **unknown**: product revenue business cases (biochar, hydrochar)
are conditional. Do not commit capital based on product revenue until PFAS
characterisation is complete.

If PFAS status is **confirmed**: only Level 3 ITS and Level 4 Incineration pathways
are acceptable. All L1 and L2 pathways are automatically downgraded.
        """)

        st.markdown("### Step 4 — Use pyrolysis trade-off for operating strategy")
        st.markdown("""
If pyrolysis is in your shortlist, navigate to **📈 Pyrolysis Envelope**.

The trade-off curve shows total value ($/tDS) across 300–800°C broken into:
energy recovery + biochar revenue + carbon credits.

Remember the board message: *there is no single optimal temperature.*
The recommended operating mode depends on whether the system is optimised
for energy, product value, or compliance.
        """)

        st.markdown("### Step 5 — Build the investment sequence")
        st.markdown("""
Use the **Three-state strategy** output on the results page:

| State | Description |
|---|---|
| **PREFERRED (now)** | Immediately bankable, positive or near-zero net economics |
| **CONDITIONAL** | Viable pending validation (PFAS, DS%, market confirmation) |
| **INEVITABLE** | Structurally required under forcing conditions (PFAS, disposal failure) |

This sequence — not the ranked list — is the strategic output of BioPoint.
        """)

    # ── TAB 3: PATHWAY MODULES ────────────────────────────────────────────
    with tabs[2]:
        st.markdown("## The 11 evaluated pathways")

        pathways = [
            ("FS01", "Baseline disposal", "Status quo — dewatered cake to land application. No treatment upgrade. Zero resilience baseline."),
            ("FS02", "AD-led conventional", "Optimised anaerobic digestion + CHP across all sites. Mass reduction ~45%. The only pathway with consistently positive net economics at typical disposal costs."),
            ("FS03", "Drying only", "Thermal drying to 80%+ DS without downstream thermal conversion. Energy-intensive; passes only when DS% is high or confirmed waste heat is available."),
            ("FS04", "Drying + pyrolysis", "Drying to 85–90% DS followed by pyrolysis at 450–750°C. Product-led or energy-led depending on operating temperature. Requires ITS configuration for PFAS compliance."),
            ("FS05", "Drying + gasification", "Drying to 90% DS followed by gasification. 100% mass elimination. Highest drying energy demand of all pathways. Poor gate performance below 40% DS."),
            ("FS06", "HTC pathway", "Hydrothermal carbonisation — wet feed, no pre-drying. Tier 3 Fully Coupled: high-strength process liquor returns to mainstream. PFAS is transferred not destroyed."),
            ("FS07", "Centralised hub", "Off-site drying + pyrolysis hub serving multiple plants. HIGH siting flexibility. Fails drying gate at low DS% — viable after preconditioning."),
            ("FS08", "Decentralised site-based", "Site-level drying at each WWTP. Capital duplication; no economy of scale. Useful only with confirmed site-level waste heat."),
            ("FS09", "AD → drying → incineration", "AD optimisation followed by drying and FBF incineration. Mandatory benchmark at >50 tDS/day. Level 4 PFAS destruction. Highest CAPEX."),
            ("FS10", "AD → THP → dewatering → incineration", "THP upstream improves dewatering to 30–38% DS, improving incineration energy closure. Highest combined CAPEX of any pathway."),
            ("FS11", "HTC → sidestream → discharge", "HTC with SHARON/ANAMMOX sidestream treatment. Tier 2 Partially Coupled. Removes the raw HTC compliance risk. Near-breakeven economics."),
        ]

        for fs_id, name, desc in pathways:
            with st.expander(f"**{fs_id} — {name}**"):
                st.markdown(desc)

        st.markdown("### Hybrid system configurations")
        st.markdown("""
In addition to the 11 single-technology flowsheets, BioPoint evaluates
four hybrid configurations for multi-site systems:

| Config | Description |
|---|---|
| **H00** | Full decentralised — AD at all sites |
| **H01** | Single hub at largest site (HTC + sidestream) |
| **H02** | Two-hub hybrid (two largest sites) |
| **H03** | Partial hub — 60% consolidation at Site 1, AD at satellites |

H03 typically delivers the best balance of disposal reduction (91%) and
transport cost vs full centralisation.
        """)

    # ── TAB 4: INPUT REFERENCE ────────────────────────────────────────────
    with tabs[3]:
        st.markdown("## Input reference")

        st.markdown("### Feedstock inputs")
        feedstock_data = {
            "Parameter": [
                "Dry solids (tDS/day)",
                "Feed DS%",
                "Volatile solids (%)",
                "GCV (MJ/kgDS)",
                "Sludge type",
                "Feed variability",
                "PFAS status",
            ],
            "Typical range": [
                "1–500",
                "3–50%",
                "45–85%",
                "6–18",
                "blended / digested / primary / secondary / thp_digested",
                "low / moderate / high",
                "unknown / negative / confirmed",
            ],
            "Notes": [
                "Total dry solids throughput per day",
                "3% = digested sludge direct from digester. 20–22% = after centrifuge. 30–38% = after THP+filter press",
                "VS as % of DS. Digested sludge typically 60–68%. Raw sludge 75–80%",
                "Gross calorific value of dry solids. Digested: 9–12. Raw: 13–16",
                "Affects biogas yield, GCV defaults, and nutrient content",
                "HIGH variability penalises pyrolysis/gasification — reactor stability risk",
                "CONFIRMED forces incineration mandatory; closes biochar product routes",
            ],
        }
        import pandas as pd
        st.dataframe(pd.DataFrame(feedstock_data), use_container_width=True, hide_index=True)

        st.markdown("### Economic inputs")
        econ_data = {
            "Parameter": [
                "Disposal cost ($/tDS)",
                "Electricity ($/kWh)",
                "Fuel price ($/GJ)",
                "Transport ($/t·km)",
                "Avg transport distance (km)",
                "Carbon price ($/tCO₂e)",
                "Discount rate (%)",
                "Asset life (years)",
            ],
            "Typical range": [
                "$80–$400/tDS",
                "$0.12–$0.30/kWh",
                "$10–$20/GJ",
                "$0.15–$0.40/t·km",
                "10–200 km",
                "$20–$150/tCO₂e",
                "5–10%",
                "20–30 years",
            ],
            "Notes": [
                "Gate fee or landfill cost for dewatered cake. Primary driver of AD economics",
                "Grid electricity price. Major driver of drying pathway economics",
                "Natural gas or equivalent. Used for auxiliary drying fuel",
                "Wet sludge haulage. At 3% DS, transport is the dominant logistics cost",
                "Average haul to disposal or hub. Multi-site systems: hub distance",
                "Carbon credit value. Applied to sequestered biochar carbon (R50 > 0.55)",
                "Applied to annualised CAPEX calculation",
                "Infrastructure asset life for annualised cost",
            ],
        }
        st.dataframe(pd.DataFrame(econ_data), use_container_width=True, hide_index=True)

        st.markdown("### Strategy inputs")
        st.markdown("""
| Parameter | Options | Effect |
|---|---|---|
| Optimisation priority | balanced / highest_resilience / cost_minimisation / carbon_optimised | Weights the scoring of pathways |
| Regulatory pressure | low / moderate / high | Affects inevitability classification and compliance urgency |
| Land constraint | low / moderate / high | Activates siting score adjustments (+15 for flexible off-site pathways) |
| Social licence | low / moderate / high | Favours off-site thermal pathways with no WWTP community interface |
| Biochar market confidence | low / moderate / high | Affects carbon product revenue assumptions |
        """)

    # ── TAB 5: UNDERSTANDING RESULTS ─────────────────────────────────────
    with tabs[4]:
        st.markdown("## Understanding results")

        st.markdown("### The scoring system")
        st.markdown("""
Each pathway receives a composite score (0–100) incorporating:

- **Base score** — compatibility, risk, economics, energy system
- **Drying gate penalty** — up to −25 points for severe energy deficit
- **Coupling adjustment** — Tier 3 pathways penalised; Tier 1 decoupled pathways rewarded under resilience priority
- **Siting adjustment** — +13 to +15 for flexible off-site pathways when land/social constraints are active
- **PFAS scoring** — confirmed PFAS: L3/L4 pathways +25, L1/L2 pathways −20

The score represents strategic fit under the stated constraints — not absolute
economics. A pathway with negative net economics can score highly if it provides
resilience, PFAS compliance, and siting flexibility that the context demands.
        """)

        st.markdown("### Drying gate")
        st.markdown("""
The drying feasibility gate is a hard physical constraint:

| DS% range | Pyrolysis | Incineration | Label |
|---|---|---|---|
| < 30% | FAIL | FAIL | NOT VIABLE |
| 30–38% | FAIL | PASS | MARGINAL |
| 38–48% | Approaching | PASS | APPROACHING ENERGY-NEUTRAL |
| > 41% (incin) / > 48% (pyr) | PASS | PASS | ENERGY-NEUTRAL |

A pathway that fails the gate **cannot rank as Preferred** regardless of its score.
It will appear in the ranked list with a ❌ gate flag and a conditional decision status.
        """)

        st.markdown("### ITS classification levels")
        st.markdown("""
| Level | Label | PFAS outcome | Status |
|---|---|---|---|
| L1 | Transfer System | TRANSFER — PFAS into product | NOT ACCEPTABLE |
| L2 | Partial Thermal | UNCERTAIN / REDISTRIBUTION | CONDITIONAL |
| L3 | Integrated Thermal System | DESTRUCTION (design-based) | ACCEPTABLE with validation |
| L4 | Dedicated Incineration | DESTRUCTION (validated) | HIGH CONFIDENCE |

Standard pyrolysis without a secondary oxidation chamber at ≥850°C is L2 — conditional.
Adding a secondary combustion chamber upgrades it to L3 (ITS). This is the minimum
viable configuration for PFAS-risk biosolids, not an optional upgrade.
        """)

        st.markdown("### Net annual value")
        st.markdown("""
Net annual value = Avoided costs − OPEX − Annualised CAPEX

**Avoided costs** include: disposal cost avoided, transport saving, energy revenue,
product revenue (biochar/hydrochar), carbon credit revenue.

**A negative net value does not mean the pathway is wrong.** At high disposal costs
or under PFAS forcing conditions, a pathway costing $30M/yr may be the only
compliant option. The strategic value (resilience, regulatory certainty, PFAS
destruction) is captured in the score — not the net annual value alone.
        """)

        st.markdown("### Three-state strategy output")
        st.markdown("""
| State | Definition |
|---|---|
| **PREFERRED** | Immediately bankable. Positive or near-zero net economics at current conditions. Low risk. |
| **CONDITIONAL** | Viable but requires validation before capital commitment (PFAS result, DS% confirmed, market offtake). |
| **INEVITABLE** | Structurally required under forcing conditions — PFAS confirmation, disposal market failure, or regulatory tightening. |

The three-state output is the primary strategic deliverable of BioPoint.
It answers: what should we do now, what do we need to validate, and what will
we be forced into regardless.
        """)

    # ── TAB 6: PYROLYSIS DETAIL ───────────────────────────────────────────
    with tabs[5]:
        st.markdown("## Pyrolysis operating envelope")

        st.markdown("""
The pyrolysis module models the conversion process as continuously tunable
across 300–800°C. There is no single optimal temperature — the best operating
point depends on the stated objective.
        """)

        st.markdown("### Temperature response functions")
        st.markdown("""
Eight physical properties are modelled as continuous functions of temperature,
calibrated to sludge biosolids literature (Zhao et al. 2013, IBI Standards,
Lehmann & Joseph 2015):

| Property | Direction | 300°C | 575°C | 700°C |
|---|---|---:|---:|---:|
| Biochar yield (% DS) | Decreases | ~42% | ~27% | ~22% |
| Fixed carbon (%) | Increases | ~22% | ~40% | ~50% |
| Carbon stability (R50) | Increases | 0.23 | 0.64 | 0.80 |
| N retention (%) | Decreases | ~51% | ~35% | ~30% |
| Pyrogas energy fraction | Increases | 19% | 41% | 50% |
| Biochar CV (MJ/kg) | Decreases | ~17 | ~14 | ~12 |

**Heating rate effects:** Fast pyrolysis produces more gas and less char.
Slow pyrolysis maximises char yield. The engine adjusts all outputs for
slow / medium / fast heating rate selection.
        """)

        st.markdown("### Three operating modes")
        st.markdown("""
| Mode | Temperature | Best for | Not for |
|---|---|---|---|
| **LOW TEMP** | 400–500°C | Soil amendment, maximum biochar mass, nutrient recovery | PFAS compliance, carbon credits |
| **MID TEMP** | 550–650°C | Balanced: soil amendment + moderate energy + R50 eligibility | Definitive PFAS compliance without secondary oxidation |
| **HIGH TEMP** | 650–800°C | Carbon credits, engineered carbon, energy maximisation | Maximum biochar mass output |
        """)

        st.markdown("### PFAS confidence by temperature")
        st.markdown("""
| Temperature | Configuration | PFAS confidence |
|---|---|---|
| < 500°C | Any | LOW — insufficient for C-F bond cleavage |
| 500–700°C | No secondary oxidation | MODERATE — partial destruction, compound-specific |
| > 700°C | No secondary oxidation | MODERATE — recombination risk in downstream equipment |
| > 700°C | + Secondary oxidation ≥850°C | HIGH — ITS configuration, design-based destruction |

The secondary oxidation chamber is not optional for PFAS compliance.
It is the minimum viable configuration for treating PFAS-risk sludge via pyrolysis.
        """)

        st.markdown("### Trade-off curve ($/tDS)")
        st.markdown("""
The trade-off curve aggregates three revenue streams at each temperature:

**Total value = Energy value + Biochar value + Carbon credits**

- **Energy value:** Pyrogas → electricity at 30% conversion efficiency × $/kWh
- **Biochar value:** Yield% × market price/tonne (low-grade / soil amendment / engineered carbon)
- **Carbon credits:** Stable carbon fraction (R50 > 0.55) × CO₂e × $/tCO₂e

Carbon credits are zero below ~550°C (R50 < 0.55 threshold). They increase
with temperature as carbon stability rises. This creates a crossover point
where the energy + credit gain at high temperature can outweigh the biochar
mass loss — but only if a confirmed carbon credit offtake exists.
        """)

    # ── TAB 7: BIOPOINT INTELLIGENCE ─────────────────────────────────────
    with tabs[6]:
        st.markdown("## BioPoint Intelligence")
        st.markdown(
            "BioPoint applies engineering logic across 13 analysis layers "
            "simultaneously. This section explains the key reasoning engines."
        )

        st.markdown("### Drying Dominance Engine")
        st.markdown("""
The drying dominance engine calculates the explicit latent heat burden
for each thermal pathway:

- **Latent heat:** 2,270 kJ/kg of water evaporated (630.6 kWh/tonne)
- **Theoretical minimum** (latent heat only) vs **actual** (including dryer efficiency losses)
- **Drying as % of feedstock energy** — the critical dominance ratio
- **DS% for energy neutrality** — solved algebraically for each pathway

At 20% DS feed, drying to 80% DS requires ~600 kWh per dry tonne of feedstock
energy equivalent. This exceeds the feedstock energy content for most sludge types,
making self-sufficient drying physically impossible without preconditioning.
        """)

        st.markdown("### Coupling Classification Engine")
        st.markdown("""
Three coupling tiers reflect the degree of interaction between the biosolids
pathway and the liquid treatment plant:

- **Tier 1 — Fully Decoupled:** No significant return load. Mainstream plant independent.
  *(Incineration, pyrolysis, gasification)*
- **Tier 2 — Partially Coupled:** Moderate centrate/condensate return. Manageable with scheduling.
  *(AD, HTC+sidestream, drying, centralised hub)*
- **Tier 3 — Fully Coupled:** High-strength process liquor with significant N and COD.
  *(Raw HTC — 12.3% of plant influent N at typical scale)*

HTC cannot be recommended without explicit coupling evaluation. The engine
enforces this rule structurally — raw HTC receives Tier 3 penalties and
compliance risk flags automatically.
        """)

        st.markdown("### ITS Classification Engine")
        st.markdown("""
PFAS destruction is classified by **system design**, not reactor type label.

The engine evaluates: presence of secondary oxidation stage, secondary
temperature (≥850°C threshold), gas residence time (≥2 seconds), and
emissions control system.

Standard pyrolysis = L2 regardless of operating temperature.
The same reactor with a 900°C secondary combustion chamber = L3 (ITS).

Three vendor ITS systems are pre-configured in the library:
PYREG Advanced (950°C secondary), Ecoremedy (1,100°C), Earthcare (900°C).
All three classify as Level 3 — design-based PFAS destruction.
        """)

        st.markdown("### Vendor Claim Validation Engine")
        st.markdown("""
28 structured claims across 6 thermal pathways are evaluated against the
site-specific engine outputs. Each claim receives one of four verdicts:

| Verdict | Meaning |
|---|---|
| **SUPPORTED** | Consistent with physics at this feedstock/site condition |
| **CONDITIONAL** | Holds only under specific stated conditions |
| **REFUTED** | Physically inconsistent at this feedstock/site |
| **UNVERIFIABLE** | Cannot be tested with available data |

Common refutations at 20% DS feed:
- Pyrolysis "energy positive after drying" → **REFUTED**
- Incineration "combustion heat self-supplies dryer" → **REFUTED** at <30% DS
- Gasification "syngas fully supports drying loop" → **REFUTED**
- HTC "process liquor is dilute and manageable" → **REFUTED**
        """)

        st.markdown("### Inevitability Engine")
        st.markdown("""
Four forcing drivers are evaluated:

1. **PFAS** — if confirmed: land application closes, thermal mandatory
2. **Disposal market** — high cost trajectory forces mass elimination
3. **Energy deficit** — large external energy requirement at current DS%
4. **Regulatory pressure** — tightening standards accelerate thermal timeline

Each pathway is classified as PREFERRED / CONDITIONAL / INEVITABLE / EXCLUDED
based on which drivers are active and what timeline forcing conditions apply.
        """)

    # ── TAB 8: ENGINEERING NOTES ──────────────────────────────────────────
    with tabs[7]:
        st.markdown("## Engineering notes")

        st.markdown("### Model basis and calibration")
        st.markdown("""
BioPoint V1 is calibrated against published engineering references:

- **Metcalf & Eddy, Wastewater Engineering 5th Ed.** — mass balance, energy, solids handling
- **IBI Biochar Standards v2.1** — biochar yield, fixed carbon, stability (R50)
- **Lehmann & Joseph (2015)** — pyrolysis temperature response functions
- **Zhao et al. (2013)** — sludge pyrolysis characterisation data
- **Woolf et al. (2010)** — carbon stability index methodology
- **US EPA PFAS Destruction and Disposal Guidance (2022)** — thermal treatment thresholds
- **ITRC PFAS Technical and Regulatory Guidance (2023)** — ITS classification basis
- **Australian PFAS NEMP v2.0 (2020)** — jurisdiction-specific compliance context
- **WEF MOP 8** — CAPEX ranges for biosolids infrastructure

All CAPEX figures are order-of-magnitude estimates (±30%). They are appropriate
for options screening and business case development — not for procurement or
contract pricing.
        """)

        st.markdown("### Key assumptions")
        st.markdown("""
| Assumption | Value | Basis |
|---|---|---|
| Drying specific energy | 0.80 kWh/kg water | Conservative mid-range for indirect dryer |
| Dryer efficiency | 75% | Indirect dryer heat transfer |
| CHP electrical efficiency | 35% | Standard gas engine CHP |
| CHP thermal efficiency | 45% | Jacket heat recovery |
| Incineration thermal recovery | 40% of feedstock energy | FBF steam/hot water extraction |
| Pyrolysis gas energy fraction | 19–57% (temperature dependent) | Zhao et al. 2013 |
| Biochar CV at 300°C | ~17 MJ/kg | Sludge biochar (high ash) |
| Biochar CV at 800°C | ~11 MJ/kg | Ash dilution at high temperature |
| Carbon stability threshold | R50 ≥ 0.55 | Woolf et al. 2010 carbon credit eligibility |
| PFAS secondary oxidation threshold | ≥850°C, ≥2s residence | US EPA / ITRC guidance |
| ITS classification basis | System design factors | Not reactor type label |
        """)

        st.markdown("### CAPEX calibration ranges")
        st.markdown("""
| Technology | Model range ($/tDS/day) | Industry reference |
|---|---|---|
| AD upgrade | $150K–$400K | M&E / WEF MOP 8 |
| HTC + sidestream | $300K–$800K | Emerging — wide range |
| Pyrolysis (ITS) | $200K–$600K | PYREG/Haarslev operational |
| Incineration (FBF) | $800K–$2,000K | UK/EU FBF operational data |
| THP + incineration | $1,000K–$2,500K | Combined system |
| Centralised hub (drying) | $400K–$900K | Dryer vendors |

All model CAPEX values have been verified to fall within these calibrated ranges.
No values have been flagged as outside the operating envelope.
        """)

        st.markdown("### Limitations")
        st.markdown("""
- **Single-site model:** The engine models one feedstock condition. Multi-site
  systems should be run at blended average conditions, or run separately per site.
- **Steady-state:** All calculations are annual averages. Seasonal variation,
  wet weather peaks, and startup transients are not modelled.
- **Fixed DS% target:** Pyrolysis targets 87% DS, incineration 78% DS, gasification
  90% DS. Site-specific dryer specifications may shift these targets.
- **Biochar market:** Revenue estimates use mid-case market prices. The biochar
  market is developing — treat revenue as upside until offtake is confirmed.
- **Carbon credits:** R50-based carbon credit eligibility is an approximation.
  Third-party verification against an approved methodology (Verra VM0044,
  Gold Standard) is required before carbon credit revenue is bankable.
- **PFAS:** The ITS classification is based on system design criteria, not
  site-specific stack testing. Independent PFAS destruction verification is
  required before regulatory acceptance in all jurisdictions.
        """)

        st.markdown("### Version history")
        st.markdown("""
| Version | Key additions |
|---|---|
| v24Z78 | System coupling classification (Tier 1/2/3) |
| v24Z79 | Siting engine (location flexibility, planning risk) |
| v24Z80 | Vendor claim validation (28 structured claims) |
| v24Z81 | Drying dominance engine (latent heat, fail gate, DS% labels) |
| v24Z87 | ITS classification (L1–L4 by system design factors) |
| v24Z89 | Thermal biochar engine (product, trade-off, 5-question board output) |
| v25A12 | Pyrolysis operating envelope (300–800°C continuous curve) |
| v25A20 | Pyrolysis trade-off curve ($/tDS value at each temperature) |
| v25A30 | System transition engine (role-shift, end-state declaration, step-gates) |
        """)
