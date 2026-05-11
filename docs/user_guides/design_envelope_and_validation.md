# Design Envelope and Input Validation — User Guide

Audience: engineers using the WaterPoint platform.

This guide explains the two newest features on the Results page (Page 04)
and the Design Envelope page (Page 15). It complements the **📖 User Manual**
in the app, which documents the engineering rules behind these features —
this guide focuses on **how to read the outputs and what to do with them**.

If you want the rule definitions, IV-XX tables, or decision-framework
mechanics: see the User Manual → Decision Framework tab and Input Reference tab.

---

## Quick orientation — what you'll see

After running a scenario on Page 04, scroll down past the engineering tabs
to **⚡ WaterPoint Intelligence**. The first item is now:

> **📋 Input Validation — Confidence 🟢 High | Safe for analysis 🟢**

The panel is **collapsed by default when everything is clean** and
**auto-expanded when anything Critical was detected**. If you don't see
the panel at all, the calculation either didn't run or the engineering
results haven't been generated yet.

Below it are the existing WaterPoint sections: System State, Failure Modes,
Decision Layer, Compliance, Upgrade Stack, etc. Those are unchanged.

A separate page — **📐 Design Envelope** (Page 15) — generates a longer,
deeper analysis from plant time-series data uploaded via Page 07
Calibration. It produces a six-section markdown memo plus four charts.

These two features address different questions. Input Validation answers
**"do I trust the inputs I just typed in?"** The Design Envelope answers
**"what does my actual plant data say about the design conditions?"**

---

## Part 1 — Reading the Input Validation panel

The panel summarises three things, in this order:

1. **Top metrics** — counts of 🔴 Critical, 🟡 Warning, and ℹ️ Info flags.
2. **🎯 Governing condition** — the one design condition that should drive
   technology selection. One of: *Peak wet weather*, *Moderate wet weather
   / diurnal peak*, *Seasonal trade waste event*, *Dry weather ADWF*, or
   *Unknown*.
3. **Flag list** — grouped by severity. Each flag has a code (e.g.
   `[IV-03]`), a plain-English description, and a recommendation.

It also surfaces missing fields and **VOI items** (Value of Information —
which gaps in your inputs would most change the recommendation if filled).

### Severity — what to do with each colour

| Severity | What it means | What to do |
|---|---|---|
| 🔴 **Critical** | Physically impossible input, or a required field is missing | **Resolve before using the outputs.** The downstream upgrade stack and credibility checks treat the scenario as unsafe. |
| 🟡 **Warning** | A ratio is outside its typical band; the inputs are plausible but unusual | **Investigate before detailed design.** The scenario will still run, but the warning indicates a signal worth understanding — trade waste, I/I, septicity, etc. |
| ℹ️ **Info** | An optional field is missing | Note and proceed. The VOI panel will indicate whether the missing field is worth measuring. |

### Confidence — what to do with each level

The panel rolls all flags into one overall **Data confidence** verdict:

| Confidence | Trigger | What it means downstream |
|---|---|---|
| 🟢 **High** | No warnings, no missing fields | The upgrade recommendation is ready for client presentation (`ready_for_client = True`). |
| 🟡 **Acceptable** | One warning or one missing optional field | Concept stage acceptable. Noted but not blocking. |
| 🟠 **Low** | A required field is missing, or ≥4 warnings present | Treat the recommendation as preliminary. Resolve before commitment. |
| 🔴 **Very Low** | ≥1 Critical flag, or ≥3 missing required fields | The recommendation is automatically demoted — `ready_for_client = False`, and the Critical messages appear as consistency flags on the Recommended Upgrade Stack. |

**Important behaviour:** when confidence is Very Low, the **Recommended
Upgrade Stack** expander in WaterPoint Intelligence will show a "⚠️ Review
notes" badge instead of "✅ Ready", and the Critical messages will be
listed under the stack as consistency flags. This is the credibility-layer
integration — input validity is treated as part of the credibility check,
not as a separate concern.

### Governing condition — the single most important output

The governing condition determines which constraint your design must
resolve. **It is not advisory.** Every subsequent technology decision is
made against this:

| Condition | When you see it | What it implies |
|---|---|---|
| **Peak wet weather** | Peak:ADWF ≥ 3× | Clarifier hydraulic performance is the binding constraint. CoMag, EQ, storm storage are the relevant options. |
| **Moderate wet weather / diurnal peak** | Peak:ADWF 2–3× | Both wet-weather and dry-weather biology matter. Confirm which is binding before option ranking. |
| **Seasonal trade waste event** | COD:TKN > 13 without a high peak ratio | Vintage / food-processing / seasonal peak likely governs. Routine sampling probably doesn't capture it. Trade waste characterisation is High VOI. |
| **Dry weather ADWF** | None of the above | Standard biological design basis. Verify against any compliance failure history before accepting this. |
| **Unknown** | No flow data, or peak < average (broken inputs) | Cannot determine. Fix the flow data before proceeding. |

If the governing condition disagrees with what the failure-mode engine
identifies as the primary constraint, **the input data is internally
inconsistent and needs review** — usually trade waste or I/I that isn't
in the routine load data.

### VOI items — what to investigate next

The **Value of Information** section ranks missing or uncertain inputs by
how much they would change the decision if filled. **High VOI** items are
worth commissioning investigation for *before* detailed design. **Moderate
VOI** items are worth measuring in parallel with concept work. Low VOI
items can be deferred.

The most common High VOI items:

- **`peak_flow_mld` missing** — cannot apply the binding-constraint test
  to hydraulic options. Estimate or measure before option selection.
- **`peak_flow_mld` ratio ≥ 3×** — wet weather is likely governing; a
  clarifier hydraulic assessment is required before sizing.
- **`tn_target_mg_l` missing** — TN 5 mg/L vs 10 mg/L drives fundamentally
  different process selection. Confirm with the regulator.
- **COD:TKN > 13 with no fractionation data** — trade waste may overstate
  the effective denitrification carbon. Fbs characterisation is needed.
- **`o2_demand_kg_day` and `aeration_kwh_day` both missing** — cannot
  assess blower headroom. MABR/IFAS selection is blind without it.

### Common flag combinations and what they tell you

| You see | Likely cause | What to do |
|---|---|---|
| IV-01 alone (peak < average) | Transcription error or units mismatch | Fix peak flow value. Cannot proceed. |
| IV-03 (peak > 5×) + Peak wet weather governing | High I/I catchment | Hydraulic-side options take priority; investigate I/I sources |
| IV-10 (COD:TKN < 8) | Carbon-limited denitrification | Fbs characterisation; consider external carbon dosing assessment |
| IV-12 (COD:TKN > 13) + Seasonal trade waste governing | Vintage / food processing influence | Source profiling; trade waste characterisation is the priority investigation |
| IV-04 or IV-05 (NH₄ > TN) | Analytical or units error | Re-check TKN measurement basis. NH₄ is a fraction of TN. |
| IV-06 / IV-07 (MLSS out of range) | Process-type mismatch or measurement | Below 1,000 mg/L suggests a non-AS process; above 8,000 suggests MBR/AGS — verify the technology context |

### What the panel does **not** do

- It does not validate the *engineering* outputs (those are checked by the
  Failure Mode Analysis and Credibility layer further down the page).
- It does not assess data representativeness — a year of flow data that
  happens to miss the peak event will not be flagged. That kind of gap
  is the engineer's call. See the **high-volume / low-confidence paradox**
  note in the User Manual's Decision Framework tab.
- It does not block you from running the scenario. Critical flags only
  demote `ready_for_client`; the engineering calculation still runs and
  the outputs are still produced.

---

## Part 2 — Reading the Design Envelope memo

The Design Envelope (Page 15) is a deeper, data-driven assessment generated
from plant time-series data. Where Input Validation checks the dataset
you typed in, the envelope analyses the data you uploaded on Page 07.

### What it produces

For each design concern you select (e.g. *Peak hydraulic*, *BNR
nitrification stress*), the tool generates:

- A six-section **markdown memo** — typically 5–20 kB of structured text.
- Four **PNG charts** referenced from the memo:
  - **Figure 2.1** — Spearman correlation heatmap of focus parameters
  - **Figure 2.2** — pairwise scatters for the strongest correlations
  - **Figure 3.1** — time series of focus parameters with events overlaid
  - **Figure 4.1** — observed vs naive over-design bar comparison

The memo is the artefact you hand to a colleague. The charts inline support
the narrative.

### The six sections — what each one tells you

**Section 1 — Framing**

States the design concern, the matching condition, the dataset used, and
the size of the matched subset. **Always read this first.** A subset of
five days produces unreliable medians; a subset of 200 days is statistically
defensible. The header bar will say "Insufficient" / "Limited" /
"Acceptable" / "Strong" — anything below Acceptable means the conclusions
are illustrative only.

**Section 2 — Conditional medians (the design point candidates)**

For each focus parameter, this section gives the median, P5, P95, and
shift-vs-overall classification when the matching condition is true. **This
is the headline result.** If you're sizing for "peak hydraulic", the
conditional medians in Section 2 are the load and concentration values you
should use — not the all-data averages.

Read the **Cond. median (excl. flagged)** column when present. It shows
the same median with integrity-flagged data points removed. If the two
columns differ by more than ~10%, integrity issues materially affect the
result. If they agree to within a percent or two, the flagged rows are not
biasing the design point.

The **ratio table** is sorted by which ratios are diagnostic for your
concern. For *BNR nitrification stress*, alk/TKN, BOD/TKN, and NH₄/TKN are
marked diagnostic; for *Peak hydraulic*, all ratios are informational
because the story is loads-vs-concentrations, not ratio shifts.

**Section 3 — Event inventory**

Lists the discrete events (storms, septicity episodes, first-flush, etc.)
that overlap the matched subset. Each event has a **repeatability
indicator** — *"4 events of this type observed across 3 distinct calendar
years"*. This is **evidence-of-recurrence, not a ranking of importance.**
A high-repeatability event is one you've seen before; whether it's the
governing event is the engineer's call.

If you see only one or two events for the concern you're sizing for, the
recommendation is preliminary — extended monitoring may be required.

**Section 4 — Naive over-design check (Figure 4.1)**

Compares what your design point would be if you naïvely stacked P95 values
of each parameter, versus the observed joint medians under the condition.

The headline finding for *Peak hydraulic* on most municipal datasets:
concentrations show large over-design margin under naïve P95 stacking
(+50–60% on BOD and COD), **but loads show roughly zero margin or slight
under-design** — because at peak flow, load *goes up* even as
concentrations dilute. This is the concentration-vs-load distinction.
Always check both rows.

**Section 5 — Integrity audit**

Lists the INT-XX flags from the data characteriser that affect the matched
subset. INT-01 (physical range violations), INT-01b (typical range
excursions), INT-02 (zero values), INT-03 (duplicates), INT-04 (string
coercions), and INT-05 (stoichiometric violations).

The severity and effect of each flag are given. A handful of INT-01b BOD
excursions that don't materially shift the conditional median (e.g.
243.8 vs 243.9 mg/L excluding them) is itself a useful finding — it tells
you the outliers are *within distribution* and the design point is robust
to whether you include them.

**Section 6 — Limits and out-of-scope items**

Explicit list of what this analysis *cannot* tell you:

- Plant-side process consequences (influent-side evidence only — no claims
  about whether your existing process can handle the condition)
- Statistical extrapolation (no return-period estimates, no fitted
  distributions — observed conditions only)
- Prioritisation across envelopes (if you generated three concerns, the
  tool will not rank them; that's the engineer's judgement)
- Sub-daily hydrograph shape (unless your data has sub-daily resolution)
- Event severity ranking (the "Severity" column is currently a
  placeholder)

**Read this section every time.** It's the boundary of what the tool
claims.

### Six pre-built concerns

The tool ships with six concerns. Each has its own ratio prioritisation,
focus-parameter list, and event-type filter:

| Concern | What it sizes for | Key diagnostic ratios |
|---|---|---|
| `peak_hydraulic` | Clarifier sizing under wet weather | (none — loads-vs-concentrations is the story) |
| `bnr_nitrification_stress` | BNR/nitrification capacity under cold-weather low-carbon stress | alk/TKN, BOD/TKN, NH₄/TKN |
| `p_removal_stress` | BioP or chemical-P design point under TP-rich events | TP/COD |
| `septicity` | Sulphide / odour mitigation | rbCOD/sCOD, sCOD/COD |
| `biodegradability` | Carbon availability for BNR | COD/BOD, rbCOD/COD |
| `first_flush_solids` | TSS surge management | VSS/TSS |

If you have a concern that doesn't fit one of these, you can run with a
user-defined concern (leave the dropdown on *(none — user-defined)*) — the
analysis still runs but the ratio table falls back to alphabetical order
with a note that priority is the engineer's call.

### Running envelopes for multiple concerns

The tool runs one envelope per click. For a real plant assessment, you'll
typically generate:

1. *Peak hydraulic* first — to confirm or rule out wet weather as the
   governing condition
2. Whichever biological concern matches the compliance question — BNR
   nitrification stress, P removal stress, or septicity depending on the
   plant
3. Optionally *biodegradability* if Section 2 of #2 raised carbon questions

The six memos sit side-by-side in the output directory and can be read
sequentially. Cross-comparison between memos is the engineer's call —
the tool does not produce a "which concern dominates" summary because that
crosses the no-prioritisation-across-envelopes boundary in Section 6.

### What the envelope does **not** do

- It does not select technology. It produces design conditions; technology
  selection happens in the rest of the app.
- It does not estimate return periods. P95 of observed data is not P95 of
  the underlying distribution — only the observed tail.
- It does not invent uncertainty. The "integrity-aware secondary median"
  (Cond. median excl. flagged) is a real recomputation with flagged rows
  removed — not a synthesised confidence interval.
- It does not analyse hydrograph shape unless your data has sub-daily flow.

---

## Part 3 — How the two features relate

Both features use the same severity language (Critical / Warning / Info)
and confidence ladder (High / Acceptable / Low / Very Low). This is
deliberate — they're two views of the same underlying decision-framework
spec.

The differences:

| | Input Validation | Design Envelope |
|---|---|---|
| **Runs against** | The inputs you typed on Page 02 | The time-series data you uploaded on Page 07 |
| **Detects** | Physically impossible inputs, ratio anomalies, missing fields | Conditional design points, recurrence patterns, integrity-aware medians |
| **Speed** | Instant | A few seconds per concern |
| **Output** | A single panel on Page 04 | A six-section memo + four charts on Page 15 |
| **Use case** | "Can I trust this scenario before reading the recommendation?" | "What does my plant data actually say about the design condition?" |

If both are clean, the recommendation has the strongest support. If Input
Validation is clean but the envelope shows the matched subset is small or
the integrity-aware median diverges from the headline median, the scenario
inputs are internally consistent *but* the underlying data may not be
representative.

If Input Validation flags Critical but the envelope is rich and clean,
fix the scenario inputs first — the inputs determine which envelope concern
even applies.

---

## Common questions

**The panel says Confidence 🔴 Very Low — does that mean the analysis is wrong?**
No. The analysis ran. The flag means at least one Critical issue was
detected in the inputs — usually a physically impossible value or a
missing required field. The downstream recommendation is marked
`ready_for_client = False` so you know not to circulate it without first
resolving the flag.

**Page 02 already blocks me from saving impossible inputs. Why does the IV layer also check?**
Page 02 catches a subset of physical-impossibility cases at save time
(peak < average is the obvious one). The IV layer is a broader check on
the data *after* it has been combined with engineering assumptions and
flow scenario overlays. Some IV rules (COD:TKN bands, NH₄:TKN, BOD:TSS)
can only fire once loads have been derived. The two layers are
complementary, not redundant.

**The envelope says my matched subset is 8 days. Is that useful?**
Read Section 1 — the confidence ladder will say Insufficient or Limited.
Anything below Acceptable means the conditional medians are illustrative
only; extended monitoring or seasonal coverage is needed before relying on
the numbers for sizing. The chart and ratio breakdown may still be
qualitatively useful for understanding what kind of event is happening,
but the magnitudes are not design points.

**The envelope's over-design check says I have +56% margin on BOD but -2% on BOD load. Which is right?**
Both. They're different questions. The concentration margin tells you the
plant has slack against concentration-driven design conditions; the load
margin tells you that *at peak flow*, the kg/day load is roughly equal to
the naïve stack. Most biological design is load-driven, so the load row
is usually the binding number.

**Why do I sometimes see the same issue flagged by Input Validation and Failure Mode Analysis?**
They're complementary signals from different angles. A peak:ADWF ratio of
7× will be flagged by IV-03 (input integrity — "unusual for a reticulated
system") *and* by the failure-mode engine (engineering performance —
"hydraulic overload risk"). One says "verify this input"; the other says
"this design condition stresses the plant." Both correct, both useful.

---

## Where to go next

- **For the rule definitions** — User Manual → Input Reference tab → Input
  Validation Layer section (IV-01 through IV-27 with bands and severities)
- **For the engineering framework** — User Manual → Decision Framework tab
  (the nine-part framework, of which Parts 1–3 are what the IV panel
  implements)
- **For the envelope engine's design choices** — User Manual → Engineering
  Notes tab (and the developer README in `core/characteriser/`)

If something in the live tool doesn't match this guide, the live tool is
authoritative — and a bug. File it.
