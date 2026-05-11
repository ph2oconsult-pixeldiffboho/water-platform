# AquaPoint Engineering Rule Table — Source Water Characterisation

> **This document is a forward specification, not a description of currently-shipping AquaPoint code.**
>
> AquaPoint today consumes `SourceWaterInputs` through its Decision Intelligence Layer (`apps/drinking_water_app/engine/dil_aquapoint.py`). It does **not** yet have a characteriser surface wired up.
>
> This table specifies how AquaPoint's source-water characterisation should look once the registries refactor described in *HANDOVER_characterisation_rollout.md* (§7 Session 1) lands. It is reconciled against the *existing* wastewater characteriser (`core/characteriser/integrity_checks.py`, `report.py`, `orchestrator.py`, `envelope_renderer.py`) so that AquaPoint can drop into the same engine cleanly when the time comes.
>
> Use this document to: (a) review and resolve the open engineering decisions before code work begins, and (b) check AquaPoint-specific values (parameter bounds, identity rules, classification overlays) for engineering correctness against current ADWG / WHO guidance.

---

**Status:** v5.3 — Phase 0 engine-internals sighting complete. Four findings resolved against `report.py`, `orchestrator.py`, and `envelope_renderer.py`. Replaces v5.2.
**Scope:** Source (raw) water characterisation only. The platform describes what the raw water *is*; it does not compare raw water against treated-water targets or recommend treatment.
**Format:** Mirrors `apps/wastewater_app/pages/page_08_manual.py` lines 493–537 (column layout still pending sight — see "Pending reconciliation").
**Architecture:** The registries refactor (per handover §6) introduces **six registries**: parameters, integrity_rules, ratio_libraries, event_rules, concerns, caveats. AquaPoint adds **one more on top** — `source_water_classification` (AV-CLS-XX) — as additive scope. This is explicitly net-new structure for AquaPoint, not part of the handover's wastewater-extraction refactor. See §2.

**WaterPoint convention alignment (confirmed against `core/characteriser/integrity_checks.py` and `report.py`):**
- Integrity rules use the `INT-NN` family pattern — five families (six with INT-01b), each applied across parameters via parameter-keyed configuration. Module distinction (water-treatment vs wastewater) is handled by the registry namespace, not by rule-ID prefixing. **Finding 1 confirmed:** `integrity_checks.py` emits `rule_id="INT-01"` through `"INT-05"` (plus `"INT-01b"`) at lines 382, 433, 465, 489, 513, 542. The `CH-XX namespace` comment in `report.py`'s `CharacterisationFlag` dataclass is stale — likely aspirational from an earlier design or referring to a different layer of flagging. v5.3 retains the `INT-NN` convention throughout; the stale comment is a `report.py` maintenance note, not a spec change.
- Severity constants: `SEV_CRITICAL`, `SEV_WARNING`, `SEV_INFO` imported from `core.characteriser.report`.
- Flag dataclass `CharacterisationFlag` fields: `rule_id`, `severity`, `parameter`, `pattern`, `message`, `implication`, `recommended_action`, `affected_row_indices` (`list[int]`). Empty `affected_row_indices` means "not tracked"; it is not the same as "no rows affected" (confirmed by dataclass comment in `report.py`).
- Multi-parameter rules (INT-05 identity violations) combine names in the `parameter` field as `"{num_param} vs {den_param}"`.
- INT-02 exemption is by `spec.parameter_type` (only `{"flow", "concentration", "load"}` are checked) plus a single name-substring carve-out (`"rain" in spec.name.lower()`). Other parameters are *not* checked.
- INT-01b severity scaling: `SEV_WARNING if pct_outside >= 1.0 else SEV_INFO`. Skipped if `typical_range is None` or `len(s) < 30`.
- INT-05 severity scaling: `SEV_CRITICAL if pct_violated >= 5.0 else SEV_WARNING`. Tolerance defaults to 5% of `den` for analytical noise.
- INT-05 identity tuples: `(num_param, den_param, label, description)`. Identity: `num ≤ den` per row.
- INT-04 fires only when isolated NaN (singleton missing values bordered by valid values) make up `>= 50%` of total NaN. Pattern detection: scattered = string coercion likely; clustered = sensor outage.

**Engine architecture (confirmed against `orchestrator.py` and `envelope_renderer.py`):**
- The `build_design_envelope` orchestrator is pure: it consumes a cleaned dataframe, condition spec, and optionally a `CharacterisationReport` and `EventAnalysis`. **Event detection happens upstream of envelope build**; the envelope's Section 3 filters and presents events the caller has already detected. This has implications for §5 (see banner there).
- The envelope memo has **six sections** rendered by `envelope_renderer.py`: framing, observed envelope (population), observed events, over-design comparison, integrity, limits. There is no extension point for additional sections; the `render_envelope_markdown` function calls six hardcoded `_render_section_N` helpers in order. Adding a seventh section would require renderer changes; surfacing AV-CLS output within Section 1 requires only a schema field addition to `EnvelopeFraming` and a small block in `_render_section_1`.
- `KNOWN_CONCERNS` is a module-level dict in `orchestrator.py` (six concerns: `peak_hydraulic`, `bnr_nitrification_stress`, `p_removal_stress`, `septicity`, `biodegradability`, `first_flush_solids`). The handover's `registries/concerns.py` is forward spec for the registries refactor, not a refactor of an existing structure.

**Boundary statement (read first):**
This is a characterisation tool. Regulations enter the table in **exactly one** way: as source-water *classification overlays* — frameworks that categorise raw water by its observed properties (ADWG Health-Based Targets source-water categories, ADWG Cyanobacteria Alert Levels Framework). They do **not** enter as treated-water target thresholds. Iron, manganese, nitrate, microcystin and similar parameters appear in the dictionary as descriptors of the source; they are not flagged against ADWG health or aesthetic guideline values, because those values are about water leaving a tap.

The integrity rules below are about **data integrity** — physical impossibility, sensor faults, mathematical inconsistency, evidence gaps — not about whether the raw water "passes" anything.

**Citation convention:** Each band cites ADWG, WHO, USEPA, or peer-reviewed water-quality literature. `[VERIFY]` marks values for engineering review against current editions.
**Severities:** `Critical` (sample rejected from envelope) / `Warning` (flagged but retained) / `Info` (annotation).

---

## 0. Upload Contract (loader-layer requirements)

Some characterisation decisions are made at the **loader layer**, before integrity checks run. These are not engine rules per se but constraints on the upload format that the loader implements. They're documented here because skipping them invalidates downstream behaviour.

### 0.1 LoD declaration and substitution

**Decision (v5.2):** Below-LoD values are handled at the loader, not by skipping INT-02 per parameter.

The upload must include a **per-parameter limit-of-detection (LoD)** declaration for each parameter that can read below detection. The user supplies the LoD when constructing the upload (sidecar configuration or header row — implementation choice). The loader then applies:

- For literal zeros in declared-LoD-prone parameters: substitute `LoD / 2`.
- For explicit `<LoD`, `ND`, `<DL`, or similar string markers in the source data: substitute `LoD / 2`.
- For values *between* LoD and a normal measurement: keep as reported.
- For literal zeros in parameters where below-LoD is **not declared**: leave as `0` and let INT-02 fire normally — a zero in a parameter that shouldn't read zero is still a data-integrity issue.

**Substitution convention:** LoD/2 chosen for v5.2. This is the standard for compliance reporting and the value most utilities will recognise. Helsel (2012) argues for LoD/√2 on lognormal-distributed data; for concept-stage design the difference is negligible. **Document the substitution in the envelope memo's Section 6** so users know that "0.005 mg/L" appearing in their iron envelope may be `LoD/2 = 0.01/2`, not a real measurement.

**Parameters expected to require LoD declaration in AquaPoint uploads:**

| Parameter | Typical LoD range | Notes |
|---|---|---|
| P-13 Iron (total) | 0.01 – 0.05 mg/L | ICP-MS typically 0.005; older methods 0.05. |
| P-14 Manganese (total) | 0.005 – 0.01 mg/L | |
| P-15 Ammonia (as N) | 0.01 – 0.05 mg/L | |
| P-16 Nitrate (as N) | 0.05 – 0.1 mg/L | |
| P-17 Total phosphorus | 0.005 – 0.01 mg/L | |
| P-19 Cyanobacteria cells | 50 – 100 cells/mL | Microscopy LoD; method-dependent. |
| P-20 Microcystin-LR | 0.1 µg/L | ELISA typical; LCMS lower. |
| P-21 Geosmin | 5 ng/L | |
| P-22 2-MIB | 5 ng/L | |
| P-24 Total algal cells | 50 – 100 cells/mL | |
| P-26 E. coli | 1 organism/100 mL | MPN; declared zero typically means < LoD. |

Other parameters (turbidity, pH, temperature, conductivity, etc.) generally don't need LoD declarations because their measurements don't routinely sit at the detection limit.

**Consequence for §3.3:** INT-02 still fires on any literal zero where the parameter type is `concentration`/`flow`/`load` *and* the parameter doesn't have a declared LoD. The §3.3 "engineering decision required" rows are now resolved: those parameters are expected to have LoDs declared in the upload, so their literal zeros are normalised to `LoD/2` by the loader and INT-02 never sees them.

### 0.2 UV measurement reconciliation

**Decision (v5.2):** Accept one of {UVT, UV254} per upload, plus a declared optical path length. The loader derives the other.

UV254 and UVT are mathematically linked by the Beer-Lambert relation: `UVT = 100 · 10^(−UV254 · L)`, where `L` is the optical path length in centimetres (typically 1 cm).

**Upload contract:**
- The user uploads either UVT or UV254 — **not both**.
- The user declares the optical path length `L` for their measurement.
- The loader computes the derived parameter using the Beer-Lambert relation.
- Both parameters then appear in the dataset for downstream use, but the engine knows which is primary and which is derived.

**Why one primary, not both:**
- Eliminates the v4-era ID-02 consistency-check question — if both are uploaded independently, inevitable lab/instrument differences fire false positives.
- Surfaces the path-length assumption explicitly at upload time, rather than hiding it in the parameter bounds. (Path length silently drives INT-01 on UVT; without an explicit declaration, a 10-cm-cell UVT looks valid on a 1-cm scale and corrupts UV-disinfection diagnostics downstream.)

**Default path length:** if not declared, the loader assumes `L = 1 cm` and warns. UV254 in spectrophotometer cells is conventionally reported on a 1-cm path, so this is the right default — but the warning ensures the user confirms.

**Consequence for §3.4:** ID-02 disposition is now resolved. The check is eliminated by upload constraint; there's no integrity flag to fire because the two values are guaranteed consistent by construction.

### 0.3 Note on `CharacterisationFlag.rule_id` namespace

Phase 0 sighting of `report.py` surfaced a stale comment on the `CharacterisationFlag` dataclass: `rule_id: str # CH-XX namespace (separate from IV-XX)`. This comment does **not** reflect current behaviour. `integrity_checks.py` emits `INT-NN` rule IDs (confirmed: lines 382, 433, 465, 489, 513, 542). v5.3 (and AquaPoint's integrity registry) uses `INT-NN` throughout.

This is flagged as a `report.py` maintenance note for whoever next touches that file: either update the comment to reflect `INT-NN`, or confirm there's a separate `CH-XX` layer of flagging used elsewhere that just doesn't apply to integrity rules. No spec change required for AquaPoint.

---

## 1. Parameter Dictionary

Source water parameters expected in an AquaPoint upload. "Typical observed range" describes where temperate Australian surface-water sources commonly sit — a descriptive band, not a target. "Physical bounds" mark the limits of what the parameter can possibly be (sensor-error detection only).

| Code | Parameter | Units | Typical observed range (raw surface, AU temperate) | Physical lower bound | Physical upper bound | Notes |
|---|---|---|---|---|---|---|
| P-01 | Turbidity | NTU | 0.5 – 50 | 0 | ~10,000 | Storm peaks can far exceed range |
| P-02 | True colour | HU (Pt-Co) | 5 – 80 | 0 | ~500 | Correlates with DOC |
| P-03 | UV254 absorbance | cm⁻¹ | 0.05 – 0.50 | 0 | ~2.0 | Filtered (0.45 µm) assumed |
| P-04 | UVT @ 254 nm | % | 60 – 95 | 0 | 100 | Derived from UV254; 1 cm path length assumed |
| P-05 | DOC | mg/L | 2 – 15 | 0 | ~50 | Filtered |
| P-06 | TOC | mg/L | 2 – 20 | 0 | ~50 | Unfiltered |
| P-07 | pH | pH units | 6.5 – 8.5 | 0 | 14 | Source-water observation, not aesthetic target |
| P-08 | Temperature | °C | 5 – 28 | -2 | 40 | Surface water; AU temperate |
| P-09 | Alkalinity (as CaCO₃) | mg/L | 20 – 200 | 0 | ~1000 | |
| P-10 | Total hardness (as CaCO₃) | mg/L | 30 – 250 | 0 | ~2000 | |
| P-11 | Conductivity (EC) | µS/cm | 100 – 1500 | 0 | ~50,000 | Saline intrusion indicator |
| P-12 | TDS | mg/L | 50 – 1000 | 0 | ~35,000 | |
| P-13 | Iron (total) | mg/L | 0.02 – 1.0 | 0 | ~50 | |
| P-14 | Manganese (total) | mg/L | 0.005 – 0.5 | 0 | ~10 | |
| P-15 | Ammonia (as N) | mg/L | 0.02 – 1.5 | 0 | ~50 | |
| P-16 | Nitrate (as N) | mg/L | 0.1 – 10 | 0 | ~100 | |
| P-17 | Total phosphorus | mg/L | 0.01 – 0.3 | 0 | ~10 | |
| P-18 | Chlorophyll-a | µg/L | 1 – 30 | 0 | ~500 | |
| P-19 | Cyanobacteria cell count (toxic species) | cells/mL | 0 – 6,500 | 0 | ~10⁷ | Anchored to ADWG Alert Levels Framework |
| P-20 | Microcystin-LR (or total) | µg/L | <0.1 – 1.0 | 0 | ~100 | |
| P-21 | Geosmin | ng/L | <5 – 50 | 0 | ~1000 | |
| P-22 | 2-MIB | ng/L | <5 – 30 | 0 | ~500 | |
| P-23 | Dissolved oxygen | mg/L | 4 – 12 | 0 | ~20 | Stratification / anoxia indicator |
| P-24 | Algal cell count (total) | cells/mL | 0 – 50,000 | 0 | ~10⁷ | |
| P-25 | Suspended solids | mg/L | 1 – 50 | 0 | ~10,000 | |
| P-26 | E. coli | CFU or MPN / 100 mL | 1 – 1000 | 0 | ~10⁶ | Inlet-to-WTP value used in ADWG HBT source-water categorisation |

**References:**
- WHO *Guidelines for Drinking-water Quality*, 4th ed. + 2nd addendum (2022) — physical bounds, typical surface-water characteristics.
- Crittenden et al., *MWH's Water Treatment*, 3rd ed. (2012), Ch. 3 — source-water parameter ranges.
- NHMRC ADWG (2011, v3.7 2022) — Cyanobacteria Information Sheet; Information Sheet 1.5 (Health-Based Targets).
- WSAA *Manual for the Application of Health-Based Targets for Drinking Water Safety* (2015). [VERIFY: edition.]

---

## 2. Source-Water Classification Registry (AV-CLS-XX)

AquaPoint's seventh registry, **additive to the six** specified in the handover's registries refactor (`parameters`, `integrity_rules`, `ratio_libraries`, `event_rules`, `concerns`, `caveats`). The handover does not specify this registry because it's not present in wastewater; AquaPoint introduces it because raw water classification by external regulatory frameworks is a first-class output for drinking-water source characterisation, with no wastewater analogue.

Each entry is a classification scheme drawn from an external framework that itself classifies raw water. Each scheme defines categories, the parameter(s) and statistic on which the categorisation is computed, and a "current category" output for the source. The engine reports the resulting category in the envelope memo. **No treatment implications are stated** — only the category and the framework that defines it.

| Code | Framework | Parameter(s) | Statistic | Categories (band → label) | Output | Reference |
|---|---|---|---|---|---|---|
| AV-CLS-01 | ADWG Health-Based Targets — Source-Water Category | E. coli at WTP inlet (P-26) | P95 of last 24 months (organisms / 100 mL). If less than 24 months of data is uploaded, statistic is computed over the full record with a `[partial window]` annotation. | ≤ 1 → C1 Well protected; > 1 to ≤ 20 → C2 Moderately protected; > 20 to ≤ 2000 → C3 Poorly protected; > 2000 → C4 Unprotected | One of {C1, C2, C3, C4, Indeterminate} + P95 value + sample count + window-coverage note | WSAA (2015) *Manual for the Application of Health-Based Targets for Drinking Water Safety*; ADWG HBT Information Sheet 1.5. 24-month windowing is engineering judgment (v5.2 decision); the regulatory framework specifies the band boundaries but not the window. [VERIFY: band boundaries against the current WSAA manual edition.] |
| AV-CLS-02 | ADWG Cyanobacteria Alert Levels — raw source | Toxic-species cyanobacterial cell count (P-19); biovolume if reported; microcystin-LR (P-20) | Highest alert level reached in last 24 months. If less than 24 months of data is uploaded, statistic is computed over the full record with a `[partial window]` annotation. | < LoD → Below Detection; LoD to ≤ 500 cells/mL → Detection; > 500 cells/mL OR biovolume > 0.04 mm³/L → Alert Level 1; > 6,500 cells/mL OR biovolume > 0.6 mm³/L OR microcystin-LR > 1.3 µg/L → Alert Level 2 | Highest alert level reached + date(s) of breach + parameter(s) that triggered + window-coverage note | NHMRC ADWG (2011, v3.7 2022) Cyanobacteria Information Sheet. 24-month windowing is engineering judgment (v5.2 decision); ADWG specifies the thresholds, not the look-back window. (Microcystin-LR 1.3 µg/L is the ADWG raw-water alert escalation trigger, **not** a treated-water health limit.) [VERIFY: biovolume thresholds against current ADWG edition.] |

**Indeterminate output:** if the parameter required for a classification is absent or has insufficient samples, the registry returns `Indeterminate` with a reason — never a default category. This is reported transparently in the memo (Section 6, evidence limits) rather than silently degrading to a guess.

**Adding a new classification:** other source-water classification frameworks (e.g. trophic-state classification, salinity classification for desalination feed) would slot in as AV-CLS-03, AV-CLS-04, … with the same shape. This is why §2 is a registry and not a hard-coded overlay.

### 2.1 Surfacing in the envelope memo

**Decision (v5.3, Finding 2 resolved):** AV-CLS-XX output surfaces in **Section 1 (Framing)** of the envelope memo, as additional fields on the existing `EnvelopeFraming` dataclass and a small rendering block in `_render_section_1`.

**Architectural rationale.** Phase 0 sighting of `envelope_renderer.py` confirmed wastewater has no existing slot for classification output: `EnvelopeFraming` carries no classification field, and the six `_render_section_N` functions are called by `render_envelope_markdown` in a hardcoded sequence with no extension point. The three options considered:

- **Option A — field on `EnvelopeFraming`, rendered in Section 1.** Smallest footprint. Reads naturally as part of "what is being characterised on what dataset" — the source's framework category sits alongside the dataset framing.
- **Option B — new `EnvelopeClassificationSection` (Section 7).** Cleanest separation; own header. But promotes one or two short outputs to peer-of-events / peer-of-integrity status, which overweights it.
- **Option C — separate output artefact alongside `envelope.md`.** Doesn't touch the renderer at all. But splits a logically unified design memo across files, working against the artefact-as-handover-document model.

**Option A selected.** Source classification is framing.

**Schema and renderer additions required (specification, not code change to v5.3):**

*Schema change (`report.py`):*

```python
@dataclass
class ClassificationResult:
    """One AV-CLS-XX output for the source water."""
    code: str                          # e.g. "AV-CLS-01"
    framework: str                     # e.g. "ADWG HBT Source-Water Category"
    category: str                      # e.g. "C3 Poorly protected" | "Indeterminate"
    statistic_value: Optional[float]   # the P95 / highest-alert / etc that drove the category
    statistic_label: str               # e.g. "P95 over 24 months"
    n_samples: int                     # samples behind the statistic
    window_coverage: str               # "full" | "partial — only N months of data"
    indeterminate_reason: str = ""     # populated when category == "Indeterminate"
    triggering_dates: List[str] = field(default_factory=list)  # e.g. AV-CLS-02 alert dates
```

*Addition to `EnvelopeFraming`:*

```python
source_classifications: List[ClassificationResult] = field(default_factory=list)
```

*Renderer addition (block within `_render_section_1`, after `why_framing`):*

If `f.source_classifications` is non-empty, render a sub-block:

> **Source-water classifications (external frameworks):**
>
> | Framework | Category | Statistic | Coverage |
> |---|---|---|---|
> | ADWG HBT (AV-CLS-01) | C3 Poorly protected | P95 = 42 org/100mL (n=486) | 24 months — full |
> | ADWG Cyanobacteria Alert Levels (AV-CLS-02) | Alert Level 1 | breached 2024-02-15; 2024-11-03 | 24 months — full |
>
> *These are classifications under the named external frameworks, not treated-water compliance assessments. See §2 of the engineering rule table for definitions.*

`Indeterminate` rows are rendered with the `indeterminate_reason` populating the Statistic column.

**Why Section 1, specifically.** Section 1's role is to orient the engineer to what they're looking at: which dataset, which condition, which parameters, why this framing. The source's framework category is the same kind of context — it tells the engineer "this source is in this regulatory bucket" before they read the population stats and event analysis below. Putting it in Section 6 (limits) would understate it; putting it in its own section would overstate it. Section 1, after `why_framing`, is the right home.

**Implementation cost.** Two dataclass additions to `report.py`, one rendering block in `_render_section_1`, plus the orchestrator wiring to compute classifications and populate the field (which is AquaPoint-specific work the registries refactor would have to add anyway). No changes to the other five renderers, no changes to `render_envelope_markdown`'s section list.

---

## 3. Integrity Rules (INT-NN)

WaterPoint's integrity-check architecture uses a small set of **rule families**, each applied across parameters via parameter-keyed configuration, rather than one rule per parameter-and-condition. v4 follows the same pattern. The AquaPoint integrity registry therefore consists of:

- The five (six with INT-01b) family-rule definitions inherited from `core.characteriser.integrity_checks` — no new rules.
- A **parameter-bounds configuration table** keyed by parameter, supplying the physical and typical ranges INT-01 and INT-01b need.
- A **zero-exemption list** for INT-02.
- An **identity-rules table** for INT-05.
- Any source-water-specific cross-family rules that don't fit the inherited families. (v4 currently introduces one — see §3.4 — and flags it for engineering review.)

### 3.1 Family Rules (inherited from WaterPoint)

| Rule ID | Family | Condition | Severity | Notes |
|---|---|---|---|---|
| INT-01 | Physical range violation | Value < `physical_lower` OR value > `physical_upper` (from parameter config §3.2) | Critical | One flag per parameter that violates; `affected_row_indices` lists all violating rows. |
| INT-01b | Typical range excursion | Value < `typical_lower` OR value > `typical_upper` (but within physical bounds) | Info if < 1% of rows; Warning if ≥ 1% | Skipped if `typical_range is None` or fewer than 30 valid samples. Threshold is hardcoded at 1% in `_check_typical_range`. |
| INT-02 | Implausible zero | Value == 0 AND `spec.parameter_type ∈ {"flow", "concentration", "load"}` AND parameter is not name-exempt | Warning | Exemption mechanism: parameter must have an exempt `parameter_type`, otherwise exempt via name-substring (`"rain" in spec.name.lower()` is the only one wastewater currently uses). See §3.3 for AquaPoint engineering decision. |
| INT-03 | Duplicate dates | Two or more rows share the same `_date` value | Warning | Cross-parameter rule. Flag's `parameter` field is the literal string `"dataset"`. |
| INT-04 | Scattered NaN suggesting string coercion | Isolated NaN values (NaN with non-NaN neighbours on both sides) make up `≥ 50%` of total NaN in the parameter | Info | Heuristic for detecting source-data tokens (`"ERROR"`, `"N/A"`, `"<DL"`) silently coerced to NaN by the loader. Skipped if `len(s) < 30` or no NaN present. |
| INT-05 | Stoichiometric / identity violation | Per-row: `num_param > den_param * (1 + noise_tolerance_pct/100)`. Tolerance defaults to 5%. | Critical if `≥ 5%` of compared rows violate; Warning otherwise | Multi-parameter. `parameter` field is `"{num_param} vs {den_param}"`. Identity tuples are `(num_param, den_param, label, description)` (no per-identity tolerance — global default). |

**Critical-severity flag requirement (from WaterPoint tests):** any flag at `SEV_CRITICAL` must have non-empty `implication` and `recommended_action` fields. The text of these for source-water-specific violations is in §3.5.

### 3.2 Parameter-Bounds Configuration (feeds INT-01 and INT-01b)

This table is the AquaPoint-specific configuration consumed by INT-01 (physical bounds) and INT-01b (typical bounds). Drawn from the §1 parameter dictionary; reproduced here in the form the integrity engine consumes.

| Parameter code | physical_lower | physical_upper | typical_lower | typical_upper | Reference |
|---|---|---|---|---|---|
| P-01 Turbidity | 0 | 10000 | 0.5 | 50 | WHO GDWQ §10.1; site envelope. |
| P-02 True colour | 0 | 500 | 5 | 80 | Crittenden Ch. 3. |
| P-03 UV254 | 0 | 2.0 | 0.05 | 0.50 | Crittenden Ch. 9. |
| P-04 UVT @ 254 nm | 0 | 100 | 60 | 95 | Beer-Lambert; USEPA UV Manual §4. |
| P-05 DOC | 0 | 50 | 2 | 15 | Standard Methods 5310. |
| P-06 TOC | 0 | 50 | 2 | 20 | Standard Methods 5310. |
| P-07 pH | 0 | 14 | 4 | 11 | WHO GDWQ §10.1 (physical); surface-water envelope (typical). |
| P-08 Temperature | -2 | 40 | 5 | 28 | AU surface water, temperate. |
| P-09 Alkalinity | 0 | 1000 | 20 | 200 | Crittenden Ch. 9. |
| P-10 Hardness | 0 | 2000 | 30 | 250 | Crittenden Ch. 9. |
| P-11 Conductivity | 0 | 50000 | 100 | 1500 | Hem (1985). |
| P-12 TDS | 0 | 35000 | 50 | 1000 | Standard Methods 2540. |
| P-13 Iron | 0 | 50 | 0.02 | 1.0 | Crittenden Ch. 3. |
| P-14 Manganese | 0 | 10 | 0.005 | 0.5 | Crittenden Ch. 3. |
| P-15 Ammonia (as N) | 0 | 50 | 0.02 | 1.5 | Crittenden Ch. 3. |
| P-16 Nitrate (as N) | 0 | 100 | 0.1 | 10 | Crittenden Ch. 3. |
| P-17 Total phosphorus | 0 | 10 | 0.01 | 0.3 | Vollenweider (1982). |
| P-18 Chlorophyll-a | 0 | 500 | 1 | 30 | OECD trophic state. |
| P-19 Cyano cell count | 0 | 10⁷ | 0 | 6500 | ADWG Alert Levels Framework. |
| P-20 Microcystin-LR | 0 | 100 | 0 | 1.0 | ADWG Cyanobacteria info sheet. |
| P-21 Geosmin | 0 | 1000 | 0 | 50 | Suffet et al. (1995). |
| P-22 2-MIB | 0 | 500 | 0 | 30 | Suffet et al. (1995). |
| P-23 Dissolved oxygen | 0 | 20 | 4 | 12 | Wetzel (2001). |
| P-24 Total algal cells | 0 | 10⁷ | 0 | 50000 | Standard Methods 10200. |
| P-25 Suspended solids | 0 | 10000 | 1 | 50 | Standard Methods 2540D. |
| P-26 E. coli | 0 | 10⁶ | 1 | 1000 | WSAA HBT Manual; site envelope. [VERIFY] |

**Resolved:** for parameters where the typical range is "0 to X" (cyano cell count, microcystin, geosmin, 2-MIB, chlorophyll-a, total algal cells), set `typical_range = None` in the parameter spec. The `_check_typical_range` function in WaterPoint's `integrity_checks.py` already skips parameters with `typical_range is None` (line: `if spec.name not in df.columns or spec.typical_range is None: return None`). This is the cleanest answer: INT-01b is not meaningful for these parameters — a value of "above 6500 cells/mL" is captured by AV-CLS-02 (Alert Level escalation) and EV-03 (event detection), not by integrity checking against a typical range. The §3.2 table reads `typical_lower = 0, typical_upper = 6500` for documentation purposes, but the actual spec configuration should be `None` for these rows.

**Affected parameters:** P-18 Chlorophyll-a, P-19 Cyano cell count, P-20 Microcystin-LR, P-21 Geosmin, P-22 2-MIB, P-24 Total algal cells.

### 3.3 INT-02 zero-handling: resolved at the loader

**Mechanism (from WaterPoint):** INT-02 only fires when `spec.parameter_type ∈ {"flow", "concentration", "load"}` AND `"rain"` is not in the parameter name. Other types are skipped silently.

**Decision (v5.2):** AquaPoint's many LoD-prone parameters are handled at the **loader**, not by skipping INT-02 per parameter. Below-LoD values are substituted to `LoD/2` at upload (see §0.1), so by the time INT-02 runs, those parameters never see literal zeros. INT-02 then fires on any *remaining* literal zero in a `concentration`/`flow`/`load` parameter, which is the right behaviour: it catches data errors without misclassifying legitimate below-LoD readings.

For the AquaPoint parameters in §1, the `parameter_type` assignment is:

| Parameter | `parameter_type` | INT-02 fires on literal zero? |
|---|---|---|
| P-01 Turbidity | `concentration` | Yes (no LoD declaration expected; zeros are sensor faults) |
| P-02 True colour | `concentration` | Yes |
| P-03 UV254 | `concentration` | Yes |
| P-04 UVT | `dimensionless` | No (zero would be physical extreme; caught by INT-01) |
| P-05 DOC, P-06 TOC | `concentration` | Yes |
| P-07 pH | `index` | No |
| P-08 Temperature | `index` | No (zero °C is physical) |
| P-09 Alkalinity, P-10 Hardness, P-11 EC, P-12 TDS | `concentration` | Yes |
| P-13 Iron through P-17 TP | `concentration` | **No** for declared-LoD zeros (loader substitutes); **Yes** for undeclared zeros |
| P-18 Chlorophyll-a, P-24 Total algal cells | `concentration` | Same as above — declare LoD or accept INT-02 firing |
| P-19 Cyano, P-20 Microcystin-LR | `concentration` | Same — declare LoD |
| P-21 Geosmin, P-22 2-MIB | `concentration` | Same — declare LoD |
| P-23 DO | `concentration` | Yes (zero DO is implausible at surface, possible at depth — INT-02 firing here is a useful prompt to check sampling depth) |
| P-25 SS | `concentration` | Yes |
| P-26 E. coli | `concentration` | **No** for declared-LoD zeros; **Yes** for undeclared (most utilities should declare LoD = 1 organism/100 mL) |

**Documentation requirement:** the envelope memo's Section 6 (evidence limits) must list which parameters had LoD substitutions applied, with the substituted value count and the LoD value used. This makes the substitution discoverable rather than silent.

### 3.4 INT-05 identity rules

**Shape (from WaterPoint):** identities are 4-tuples `(num_param, den_param, label, description)` — strictly `num ≤ den` per row, no equation forms, no two-sided windows. Tolerance defaults to 5% of `den` for analytical noise.

**Decision (v5.2): AquaPoint's INT-05 registry is empty.**

The three identity candidates considered across v3 → v5.1 are all resolved as follows:

#### ID-01 — DOC ≤ TOC

**Decision (v5.2):** Drop the rule.

**Rationale:** WaterPoint's stoichiometric identities (BOD/COD, NH4/TKN, VSS/TSS, ortho-P/TP) work because the wastewater module assumes daily composite samples analysed by the same lab batch — so any two parameters on the same row are paired. For drinking-water source data, DOC and TOC are typically measured at different cadences (TOC weekly via online analyser; DOC monthly via grab sample to an external lab). When utilities upload to AquaPoint, the most common pattern is to align both to a monthly row in the spreadsheet — which means DOC and TOC on the same row are *not paired samples*. The identity check would fire false positives whenever the DOC sample (from a different day) happened to exceed the TOC value on the row.

The alternative — require paired samples in the upload contract — pushes work onto users to know what "paired" means and prepare data accordingly. Likely violated in practice, silently corrupting the diagnostic.

The DOC > TOC condition is still surfaceable through the **ratio library**: R-04 (POC = TOC − DOC) shows whenever the difference goes negative, and the envelope memo can flag this in evidence-limits. That's the right home for the diagnostic — descriptive, not integrity-level.

#### ID-02 — UVT ↔ UV254 Beer-Lambert consistency

**Decision (v5.2):** Resolved at the loader (see §0.2). The upload accepts one of {UVT, UV254} plus a declared path length; the loader derives the other. No INT-05 entry needed — by construction the two values are consistent.

#### ID-03 — TDS/EC window

**Decision (v5.2):** Resolved as ratio library only. R-07 (TDS/EC) in §4 is the only home for this diagnostic. The envelope memo surfaces the ratio distribution; users see whenever the ratio sits outside the 0.50–0.85 typical band. No INT-05 entry.

**Net result for AquaPoint INT-05:** the registry contains zero identity tuples. The INT-05 *family* still exists in the engine (inherited from WaterPoint's `integrity_checks.py`); the AquaPoint *configuration* simply has nothing to feed it. If a future identity is identified that fits INT-05's per-row `num ≤ den` shape on drinking-water source data, it slots in as the first entry.

This is the honest spec state. WaterPoint's identities reflect process-water lab discipline (same composite, same lab, same day). AquaPoint's source-water data shape is different and doesn't currently have analogous strict-identity pairs.

### 3.5 Critical-flag implication and recommended-action text

WaterPoint's tests require non-empty `implication` and `recommended_action` strings on `SEV_CRITICAL` flags. For AquaPoint's source-water-specific Critical conditions:

| Parameter | Implication text | Recommended action text |
|---|---|---|
| P-07 pH < 0 or > 14 | The value is non-physical; pH is mathematically bounded to [0, 14]. The reading is a data-entry error, sensor fault, or unit confusion (e.g. mV reported as pH). | Verify the source dataset's pH column units. Either correct the value at source, or mark the affected row(s) for exclusion in the characterisation run. The engine does not mutate uploaded data. |
| P-01 Turbidity < 0 | Negative turbidity is non-physical; nephelometric and ratio-turbidity instruments cannot return values below zero. Indicates sensor fault or data-entry error. | Check the sensor calibration log for the affected period. Either correct from the lab record, or mark the affected row(s) for exclusion. |
| P-08 Temperature outside -2 to 40 °C | Surface water cannot sit outside this range in any AU temperate catchment. Most likely Fahrenheit-as-Celsius unit confusion, sensor fault, or air-temperature reading. | Verify units of the temperature column. Cross-check against any second temperature record for the same period. Correct at source or mark for exclusion. |
| P-04 UVT outside [0, 100] % | UVT is a percentage; values outside [0, 100] indicate a derived-value calculation error or units mismatch. | Verify the UVT calculation against UV254 absorbance and the assumed path length. Correct at source or mark for exclusion. |
| P-09, P-13–P-17, P-26 negative concentrations | Negative concentrations are non-physical. Indicates sensor fault, lab data-entry error, or analyte interference flagged as negative by the instrument. | Verify the source lab report. Correct at source or mark the affected row(s) for exclusion. |

(The v5.1 INT-05 DOC/TOC Critical-flag row has been removed in v5.2 — see §3.4 for the disposition.)

### 3.6 Source-water-specific cross-family rules: confirmed dispositions

Now that `core/characteriser/integrity_checks.py` has been sighted, the v3-era candidate rules that don't fit the inherited families have firmer dispositions:

1. **Stuck-sensor detection (v3 AV-INT-13: > 30 consecutive identical non-zero values).** **Confirmed: not in `integrity_checks.py`.** No equivalent rule exists in the wastewater module. If AquaPoint needs this check, it would have to be added as a new rule family — but the engineering judgment for v5 is that this belongs in a separate sensor-quality / operational-data-quality module, not in the integrity-checks file, since it's not a per-value physics check. Defer to engineering.

2. **Record-duration / sampling-gap / censored-data-fraction rules (v3 AV-INT-14/15/16/20).** **Confirmed: not in `integrity_checks.py`.** None of these live in the integrity-checks file. They are evidence-limit annotations and would naturally live in the dataset-confidence / evidence-limits module that produces Section 6 of the memo. Defer; AquaPoint should rely on the same dataset-confidence machinery as WaterPoint.

3. **E. coli zero-handling ambiguity (v3 AV-INT-19).** **Confirmed: not an integrity check at all.** This is a data-convention question (does the upload declare LoD and zero conventions?). Belongs at the upload-validation layer (`input_validation_layer.py` or equivalent for AquaPoint), not at integrity.

4. **Chlorophyll-a vs total algal cells rank correlation (v3 AV-INT-17).** **Confirmed: doesn't fit INT-05.** Same disposition as ID-03 in §3.4 — population-level methodological cross-check. Recommend moving to the ratio library as a derived diagnostic, or treating as an evidence-limit caveat. Defer.

5. **UVT ↔ UV254 Beer-Lambert (v3/v4 ID-02).** See §3.4 — flagged for engineering decision.

6. **TDS/EC window (v3/v4 ID-03).** See §3.4 — flagged for engineering decision.

**Bottom line:** WaterPoint's `integrity_checks.py` has exactly five rule families (INT-01, INT-01b, INT-02, INT-03, INT-04, INT-05). v5 does not propose adding new ones. AquaPoint's integrity registry is identical in shape and inherits the same five families; the AquaPoint-specific data is in §3.2 (parameter bounds), §3.3 (parameter typing), §3.4 (the one identity that fits), and §3.5 (Critical-flag text).

---

## 4. Ratio Library

Diagnostic ratios derived from raw parameters. Descriptors of source-water *character*. The engine uses them to prioritise what appears in the envelope memo.

| Code | Ratio | Formula | Diagnostic meaning | Typical band | Reference |
|---|---|---|---|---|---|
| R-01 | SUVA | (UV254 / DOC) × 100 | DOC character: humic vs non-humic. High SUVA = aromatic, hydrophobic DOC. Low SUVA = non-humic. | 1 – 6 L/mg·m | Edzwald & Tobiason (1999); USEPA EPA 815-R-99-014. |
| R-02 | Colour/DOC | true colour / DOC | Colour-forming fraction of DOC. | 3 – 15 HU/(mg/L) | Crittenden Ch. 9. |
| R-03 | UV254/Colour | UV254 / true colour | Cross-check for DOC character; stable for a given catchment. | 0.005 – 0.020 cm⁻¹/HU | Crittenden Ch. 9. |
| R-04 | POC | TOC − DOC | Particulate organic carbon. Elevated values indicate algae or detrital load. | 0 – 3 mg/L typical | Standard Methods 5310. |
| R-05 | Chl-a / TP | chl-a / TP (both µg/L) | Trophic-status indicator; high ratio = phytoplankton-dominated source. | 0.1 – 1.0 eutrophic | OECD (Vollenweider 1982). |
| R-06 | Non-carbonate hardness | hardness − alkalinity | Character of mineral content. | -50 to +200 mg/L as CaCO₃ | Crittenden Ch. 9. |
| R-07 | TDS/EC | TDS / conductivity | Salinity character. Values outside 0.50–0.85 suggest unusual ion mix, mismatched units, or instrument drift. **Only home for the TDS/EC consistency diagnostic** — there is no equivalent integrity flag (v5.2 decision per §3.4). The envelope memo should auto-highlight when >10% of samples fall outside the typical band. | 0.50 – 0.85 | Hem (1985). |
| R-08 | NH₄-N / NO₃-N | ammonia-N / nitrate-N | Redox / N-cycle state of source. High ratio = recent organic-N loading or anoxic. | <0.1 (oxic) to >1 (anoxic/fresh) | Wetzel *Limnology* 3rd ed. (2001). |
| R-09 | Cyanobacteria / total algae | cyanobacteria / total algal cells | Cyanobacterial dominance fraction. Feeds Alert Levels classification. | 0 – 1 | NHMRC ADWG Cyanobacteria info sheet. |
| R-10 | T&O sum | geosmin + 2-MIB | Combined taste-and-odour compound loading. Descriptor of source character. | <10 ng/L typical clean source; >20 ng/L indicates a strong T&O-producing source | Suffet et al. (1995); WaterRA. |
| R-11 | DOC seasonal range | max(DOC) − min(DOC) | Seasonal swing magnitude. Diagnostic for "is one design DOC value sufficient?" | 2 – 8 mg/L typical | Crittenden Ch. 3; WSAA *Source Water Characterisation Guideline*. [VERIFY: this WSAA title exists; otherwise replace with a peer-reviewed reference.] |
| R-12 | Turbidity:Colour | turbidity / true colour | Particle-vs-organic character of the source. | 0.1 – 5 NTU/HU | Crittenden Ch. 9. |

---

## 5. Event Rules (EV-NN)

> **Scope banner (v5.3).** §5 specifies AquaPoint event rules **and** the engine capabilities those rules require. The Phase 5 wastewater build has `first_flush` rule-coded as the only complete event-detection rule (per HANDOVER §10); the other wastewater event types are referenced in `report.py` comments but not implemented. The `EventAnalysis` dataclass exists in `report.py`, and the envelope's Section 3 consumes event results — but the **event-detection module that *produces* events is largely greenfield**.
>
> Two specific engine capabilities §5 assumes are not yet present in the engine and are being specified here for the same code session that builds AquaPoint event rules:
>
> 1. **Compound triggers** — e.g. EV-01's "P95 AND rising for ≥ 2 consecutive samples", EV-04's "DOC > P90 AND SUVA > 3". The current `condition_machine` syntax (per `EnvelopeFraming.condition_machine: Dict[str, str]` and the `{"flow_mld": ">P95"}` example in `orchestrator.py`) appears to be single-parameter column→expression. Multi-parameter compound expressions and rate-of-change predicates ("AND rising") are not visible in the schema; the event-detection module will need to support them.
> 2. **Multi-sample-window triggers** — e.g. "for ≥ 2 consecutive samples", "sustained ≥ 7 days", "sustained ≥ 14 days". These are window predicates, not per-row predicates. Whether they live inside the event-rule grammar or as a separate window-checker on top of per-row predicates is an implementation choice for the engine session.
>
> v5.3 is not waiting for these capabilities to exist before specifying the AquaPoint rules; the rules document the requirements. The event-detection module's implementation session will need to read this section as part of its scope.

Each event is a defined window in which the source water exhibits a **distinct character** relative to its own typical envelope. Events are detected from observed data; the engine characterises co-occurring parameters over the window. No treated-water target is involved in event definition.

**Event ID convention (v5.3):** event IDs follow the pattern `{event_code}_{start_date}`, e.g. `EV-03_2024-02-15`. This is the join key for `EnvelopeEventSection.repeatability_notes` and the user-visible identifier in Section 3's event-inventory table.

| Code | Event | Trigger | Co-parameters captured | Min duration | Reference |
|---|---|---|---|---|---|
| EV-01 | High-turbidity event | turbidity exceeds the site's own P95 for ≥ 2 consecutive samples AND is rising | Colour, DOC, TOC, pH, EC, iron, manganese | ≥ 1 day | Site-relative threshold per WSAA *Source Water Characterisation* guidance (event detection from observed envelope, not from a target). [VERIFY citation.] |
| EV-02 | Algal-bloom event | Chlorophyll-a > 3 × site median sustained ≥ 7 days **OR** total algal cells > 3 × site median sustained ≥ 7 days | UV254, DOC, pH, DO, geosmin, 2-MIB, TP | ≥ 7 days | Site-relative trigger (consistent with §5 principle: "event = this source deviating from itself"). Threshold of 3× site median is a conventional eutrophication-event multiplier; OECD trophic classification (Vollenweider 1982) supports the qualitative pattern. [VERIFY: 3× multiplier against utility practice; some authorities use 2×.] |
| EV-03 | Cyanobacterial alert | Per-sample: toxic cyanobacteria > 500 cells/mL **OR** biovolume > 0.04 mm³/L **OR** microcystin-LR > 1.3 µg/L. Event window: from the first triggering sample until the parameter falls back below the trigger for ≥ 14 days. | All algal markers, chlorophyll-a, T&O, NH₄-N, temperature, DO | ≥ 1 sample (event opens immediately); closes after 14 days of below-trigger readings | Trigger thresholds from ADWG Cyanobacteria Information Sheet — Alert Levels Framework (raw-water classification thresholds repurposed as event-detection thresholds). Window-close convention is engineering judgment, not a regulatory specification. [VERIFY: 14-day below-trigger close window against utility operational practice.] |
| EV-04 | High-DOC event | DOC > site P90 AND SUVA > 3 | UV254, colour, TOC, pH, temperature | ≥ 1 day | Edzwald & Tobiason (1999) on DOC character; site-relative trigger. |
| EV-05 | Low-UVT event | UVT < site P10 sustained ≥ 1 day | UV254, DOC, colour, turbidity, iron | ≥ 1 day | USEPA UV Disinfection Guidance Manual §4; site-relative trigger (not a treated-water spec). |
| EV-06 | Cold-water event | Temperature < site P10 sustained ≥ 14 days | All co-occurring source parameters | ≥ 14 days | Crittenden Ch. 9 on temperature-dependent source-water behaviour; site-relative trigger. |

**Note:** Events are triggered against the **site's own observed envelope** (site-relative percentiles) wherever possible, not against absolute regulatory numbers. This keeps the event definition characterisation-centric: an event is "this source deviating from itself," not "this source breaching some target." The cyanobacterial alert is the one exception because the ADWG framework is itself a raw-water classification.

---

## 6. Pre-built Concerns → Ratio Priority Map

For each concern, the ordered list of ratios most diagnostic of that source-water character. The engine surfaces these prominently in the envelope memo when the concern is selected.

**Note on registry placement (v5.3).** This concerns→ratio priority map is forward spec for the `registries/concerns.py` module described in HANDOVER §6. It is not a refactor of an existing structure: WaterPoint's `KNOWN_CONCERNS` is a six-entry module-level dict in `orchestrator.py` mapping concern_code → human label, with the ratio-prioritisation logic currently inside `build_design_envelope`. AquaPoint's concerns table below presupposes the registries refactor has extracted the priority map into a dedicated registry indexed by `module="water_treatment"`.

| Concern | Priority 1 | Priority 2 | Priority 3 | Priority 4 |
|---|---|---|---|---|
| `high_turbidity_event` | R-04 (POC) | R-12 (turb/colour) | R-02 (colour/DOC) | R-06 (non-carb hardness) |
| `algal_bloom` | R-05 (chl-a/TP) | R-09 (cyano fraction) | R-10 (T&O sum) | R-04 (POC) |
| `cyanobacterial_event` | R-09 (cyano fraction) | R-05 (chl-a/TP) | R-10 (T&O sum) | R-08 (NH/NO₃) |
| `high_doc` | R-01 (SUVA) | R-02 (colour/DOC) | R-11 (DOC seasonal range) | R-03 (UV254/colour) |
| `low_uvt` | R-01 (SUVA) | R-02 (colour/DOC) | R-04 (POC) | R-11 (DOC seasonal range) |
| `cold_water_event` | R-01 (SUVA) | R-11 (DOC seasonal range) | R-06 (non-carb hardness) | R-12 (turb/colour) |

---

## 7. Caveat Library

Per-concern caveats appended to Section 6 of the envelope memo. All framed as evidence limits on the *characterisation*, not treatment implications.

| Concern | Caveat text |
|---|---|
| `high_turbidity_event` | Storm-driven turbidity peaks are episodic; envelope statistics derived from < 3 years of record may undersample the upper tail. P99 turbidity reported alongside a standard error to indicate evidence weight. |
| `algal_bloom` | Chlorophyll-a and algal cell counts have high analytical variance and depend strongly on sample depth and time of day. Lab-counted cells and in-vivo fluorescence-derived chl-a can differ by an order of magnitude. |
| `cyanobacterial_event` | Cell counts alone do not characterise toxin presence; toxin assays are required for confirmation. Absence of toxin data in the record is not evidence of toxin absence. Cyanobacterial species composition shifts rapidly; historical species-level data may not represent future events. |
| `high_doc` | DOC character (SUVA, colour/DOC) is more diagnostic of source-water nature than DOC concentration alone. |
| `low_uvt` | UVT derived from UV254 assumes 1 cm path length and a calibrated spectrophotometer. Online-monitor UVT may differ systematically from grab-sample UVT; instrument and reconciliation should be documented. |
| `cold_water_event` | Cold-water envelope is a descriptive observation of source temperature behaviour. Implications for downstream processes are out of scope. |

---

## Open Items for Engineering Review

1. **HBT category bands (AV-CLS-01):** the four-category structure and the 1 / 20 / 2000 organisms·100mL⁻¹ band boundaries are widely cited but the canonical source is the WSAA HBT Manual (2015 or later edition). [VERIFY against the current WSAA manual or the draft ADWG revision text — these may have shifted since 2015.] Also confirm whether P95 is the canonical statistic (vs P90 or annual mean).
2. **Cyanobacteria biovolume thresholds (AV-CLS-02):** 0.04 / 0.6 mm³/L cited from the ADWG Cyanobacteria Information Sheet; confirm against the current v3.7 edition. Also confirm whether "max observed in record" is the correct trigger statistic for the platform's purpose, vs e.g. P95 or "any sample in last 12 months."
3. **WSAA *Source Water Characterisation Guideline* citation (R-11, EV-01):** I cite this as if it exists; the WSAA HBT Manual is real, but a separate "Source Water Characterisation Guideline" needs verification. If it doesn't exist under that title, swap to Crittenden Ch. 3 or a WSAA technical report.
4. **Site-relative vs absolute event triggers (§5):** ~~EV-01, EV-04, EV-05, EV-06 all use site-relative percentiles…~~ **Resolved in v5.1:** EV-02 now fully site-relative (3× site median for both chl-a and total algal cells). EV-03 redefined as a per-sample trigger with ADWG thresholds — these are raw-water classification thresholds repurposed as event triggers, not treated-water targets, so the principled exception still applies.
5. **E. coli LoD handling:** the v3 rule on this has been moved out of the integrity registry (see §3.6 item 3) — it belongs at the upload-validation layer rather than in `integrity_checks.py`. Confirm with engineering where this lives.
6. **Parameter scope:** P-26 (E. coli) is included because it drives AV-CLS-01. If E. coli isn't in the AquaPoint upload schema, AV-CLS-01 returns `Indeterminate` and the parameter is optional rather than required.
7. ~~**INT-01b severity-scaling threshold (1%):**~~ **Resolved in v5:** hardcoded at 1% in `_check_typical_range`. Not per-parameter configurable.
8. ~~**INT-05 severity-scaling threshold (≥5%):**~~ **Resolved in v5:** confirmed `SEV_CRITICAL if pct_violated >= 5.0 else SEV_WARNING` in source.
9. ~~**Identity-rule ID-03 (TDS/EC window):**~~ **Resolved in v5:** confirmed INT-05 is strictly per-row `num ≤ den`; ID-03 doesn't fit and is flagged for engineering decision (move to ratio library is the recommended path).
10. **Population-level integrity checks:** v3 had several rules that don't fit any inherited family — stuck-sensor, sampling gaps, record duration, censored-data fraction, chl-a vs total algae rank correlation. v4 has flagged these in §3.6 for engineering decision; they may belong in a separate "evidence limits" or "methodological consistency" registry rather than `integrity_checks.py`.
11. **Event-detection engine capabilities (new in v5.3):** §5's compound triggers (e.g. "P95 AND rising for ≥ 2 consecutive samples", "DOC > P90 AND SUVA > 3") and multi-sample-window triggers ("sustained ≥ 7 days") are engine capabilities not visible in the current schema. The condition_machine syntax appears single-parameter (per `EnvelopeFraming.condition_machine: Dict[str, str]`). The event-detection module's implementation session must address both. Treating §5's rules as the requirements specification for this work.
12. **`ClassificationResult` dataclass and Section 1 renderer block (new in v5.3):** the schema and renderer additions specified in §2.1 are net-new code for the registries-refactor session (Session 1 per HANDOVER §7) or for the AquaPoint build session (Session 2). Confirm with engineering which session owns this change. The AquaPoint build session is the more natural home, since AV-CLS is AquaPoint-specific scope, but the schema change touches `report.py` which is shared platform code — argument for landing it as part of the registries refactor to keep all `report.py` changes in one PR.
13. **`report.py` `CharacterisationFlag` namespace comment (new in v5.3):** the dataclass field comment reads `rule_id: str # CH-XX namespace (separate from IV-XX)` but the actual emitted values are `INT-NN`. Either update the comment or document where the `CH-XX` layer lives (if anywhere). Non-blocking for AquaPoint; maintenance note for whoever next touches `report.py`.

---

## Pending Reconciliation with WaterPoint Engine

Phase 0 sighting of `integrity_checks.py`, `report.py`, `orchestrator.py`, and `envelope_renderer.py` is now complete. (The `phase_5/example_outputs/clean/` directory referenced in v5.2's reconciliation table does not exist in the repo; the renderer is the source of truth for memo structure and was sighted directly.) Updated status table:

| Item | Status | Files inspected / to inspect |
|---|---|---|
| Naming convention | **Resolved.** `INT-NN` confirmed in `integrity_checks.py` (rule_ids at lines 382, 433, 465, 489, 513, 542). `report.py`'s `CH-XX` comment is stale — noted as Open Item 13. Event-rule and classification naming (`EV-NN`, `AV-CLS-NN`) still inferred by analogy; will firm up when the event-detection module exists. |
| Severity vocabulary | **Resolved.** `SEV_CRITICAL`, `SEV_WARNING`, `SEV_INFO` imported from `core.characteriser.report`. |
| Flag dataclass shape | **Resolved.** `CharacterisationFlag` with fields `rule_id`, `severity`, `parameter`, `pattern`, `message`, `implication`, `recommended_action`, `affected_row_indices: list[int]`. Empty list means "not tracked"; not the same as "no rows affected" (confirmed by dataclass docstring). |
| Rule-family structure | **Resolved.** Five families (six with INT-01b). v5 §3 mirrors. |
| Severity-scaling thresholds | **Resolved.** INT-01b at 1%, INT-05 at 5%, both hardcoded in `integrity_checks.py`. Not per-parameter configurable in the current code. |
| INT-02 exemption mechanism | **Resolved.** By `parameter_type` filter plus `"rain"` substring carve-out. v5 §3.3 reflects, with LoD handling resolved at the loader in v5.2 §0.1. |
| Identity-rule shape | **Resolved.** 4-tuple `(num_param, den_param, label, description)`. Tolerance global default 5%. AquaPoint INT-05 registry is empty (v5.2 §3.4). |
| Rule-table format (page_08_manual.py) | **Open.** Column layout still needs verification. Lower priority now that registries shape is firm. | `apps/wastewater_app/pages/page_08_manual.py` |
| Seventh registry shape (AV-CLS) | **Resolved (v5.3).** No existing slot in the envelope schema (`EnvelopeFraming` has no classification field; renderer has no extension point for a Section 7). AV-CLS surfacing is additive scope: new `ClassificationResult` dataclass + new `source_classifications` field on `EnvelopeFraming` + new rendering block in `_render_section_1`. See §2.1. | `core/characteriser/report.py`, `core/characteriser/envelope_renderer.py` ✓ |
| Event-rule registry shape | **Partially resolved.** Events consumed by envelope at `EnvelopeEventSection`; event-detection module is largely greenfield (`first_flush` only per HANDOVER §10). Engine capabilities for compound triggers and multi-sample windows specified in §5 banner as requirements. | Event-detection module (mostly net-new). |
| Concerns → ratio priority map | **Partial.** `KNOWN_CONCERNS` exists as a module-level dict in `orchestrator.py` (six concerns: `peak_hydraulic`, `bnr_nitrification_stress`, `p_removal_stress`, `septicity`, `biodegradability`, `first_flush_solids`). Priority-map registry per HANDOVER §6 is forward spec. | `core/characteriser/orchestrator.py` ✓ |
| Memo output shape | **Resolved.** Six sections rendered by hardcoded `_render_section_1..6` in `envelope_renderer.py`. No extension point. Adding a seventh section requires `render_envelope_markdown` changes; surfacing within an existing section requires only schema + that section's renderer block. | `core/characteriser/envelope_renderer.py` ✓ |
| Population-level checks placement | **Resolved.** Not in `integrity_checks.py`. They live elsewhere (probably the dataset-confidence layer that demotes downstream confidence). v5 §3.6 reflects. |

**Phase 0 sighting complete.** Remaining open items are engineering / domain decisions, not code-discovery gaps.

---

## Changelog

**v5.3 (this version):** Resolves the four Phase 0 findings raised on engine-internals review of v5.2 against `integrity_checks.py`, `report.py`, `orchestrator.py`, and `envelope_renderer.py`. Phase 0 complete.

- **Finding 1 (`rule_id` namespace):** confirmed `INT-NN` is correct via direct grep of `integrity_checks.py` (rule_ids at lines 382, 433, 465, 489, 513, 542). The `CH-XX` comment in `report.py`'s `CharacterisationFlag` dataclass is stale. Added §0.3 documenting the discrepancy as a `report.py` maintenance note. Added Open Item 13. No spec change to AquaPoint.
- **Finding 2 (AV-CLS surfacing):** resolved as **Option A — field on `EnvelopeFraming`, rendered in Section 1**. Phase 0 sighting of `envelope_renderer.py` confirmed wastewater has no existing slot: no classification field on `EnvelopeFraming`, no extension point in `render_envelope_markdown`'s six-section pipeline. New §2.1 specifies the required schema additions (`ClassificationResult` dataclass, `source_classifications: List[ClassificationResult]` field) and the renderer block within `_render_section_1`. Added Open Item 12 to clarify which code session owns these additions.
- **Finding 3 (events upstream of envelope build):** confirmed `generate_envelope_artefact` takes `event_analysis` as input — event detection is upstream of envelope build, not part of it. Added scope banner at top of §5 acknowledging event-detection engine is largely greenfield (per HANDOVER §10) and that §5 specifies both AquaPoint event rules *and* engine capabilities (compound triggers, multi-sample windows) those rules require. Added Open Item 11 to track engine-capability scope. Locked event_id pattern as `{event_code}_{start_date}` (e.g. `EV-03_2024-02-15`).
- **Architecture framing fix:** v5.2 described the architecture as "seven registries"; HANDOVER §6 specifies six. v5.3 clarifies: the registries refactor introduces six (parameters, integrity_rules, ratio_libraries, event_rules, concerns, caveats), and AquaPoint adds `source_water_classification` as **additive scope**, explicitly net-new structure not part of the wastewater-extraction refactor. Updated the top-of-document architecture line and the §2 intro.
- **Smaller items folded in:** §6 prefaced with note that the concerns priority map is forward spec for `registries/concerns.py` (not a refactor of an existing structure). §5 documents the event_id pattern.
- **Pending Reconciliation table:** updated to reflect Phase 0 completion. `phase_5/example_outputs/clean/` removed (does not exist in the repo per session note); `envelope_renderer.py` added as inspected. Three "Open" items moved to "Resolved": seventh registry shape, memo output shape, severity vocabulary already had been.

**v5.2:** Resolves the five engineering decisions that v5.1 had deferred. The spec is now ready for implementation — no remaining "engineering decision required" markers on the rule content itself.

- **Decision 1 (§3.3 INT-02 LoD exemption): resolved as loader normalisation (Option C).** Below-LoD values are substituted to `LoD/2` at the loader, before INT-02 runs. New §0.1 documents the upload contract for LoD declarations. INT-02 then fires only on genuine data-error zeros.
- **Decision 2 (§3.4 ID-02 UVT↔UV254): resolved at the loader (Option C).** Upload accepts one of {UVT, UV254} plus a declared optical path length. The other is derived. New §0.2 documents the upload contract. No integrity flag needed.
- **Decision 3 (§3.4 ID-03 TDS/EC): resolved as ratio library only (Option A).** R-07 in §4 is the diagnostic home. No integrity flag.
- **Decision 4 (AV-CLS windowing): resolved as 24-month window for both classifications (Option B).** AV-CLS-01 uses P95 of last 24 months for HBT category; AV-CLS-02 uses highest alert level reached in last 24 months. §2 updated.
- **Decision 5 (DOC/TOC identity): resolved as drop the rule (Option B).** AquaPoint's INT-05 registry is empty. WaterPoint's stoichiometric identities work because they assume paired same-sample measurements; drinking-water source data doesn't currently have analogous strict-identity pairs.

Architectural consequence: AquaPoint's INT-05 entry list is empty in v5.2. The family still exists in the inherited engine; the AquaPoint configuration just has no entries yet. ID-03 (TDS/EC) and the dropped ID-01 (DOC/TOC) become responsibilities of the ratio library + envelope memo's auto-flagging, not the integrity layer.

**v5.1:** Patched five spec bugs identified in red-team review of v5.
- **EV-03 redefined** with a real per-sample trigger (toxic cyano > 500 cells/mL OR biovolume > 0.04 mm³/L OR microcystin-LR > 1.3 µg/L) and an explicit event-close convention (14 days below trigger). v5's reference to AV-CLS-02 was a classification statistic, not a measurable event boundary.
- **EV-02 made fully site-relative.** Dropped the absolute 15,000 cells/mL alternate trigger which conflicted with §5's "events = source deviating from itself" principle. Now: chl-a OR total algal cells > 3× site median for ≥ 7 days.
- **R-10 reframed.** Removed "complaints" language (treated-water leakage) in favour of source-character descriptors.
- **§3.2 open question resolved.** Parameters with `typical_range = "0 to X"` (cyano, microcystin, geosmin, 2-MIB, chl-a, total algae) get `typical_range = None`, which causes WaterPoint's `_check_typical_range` to skip them. Captured by AV-CLS-02 and EV-03 instead.
- **§3.5 actions reframed.** "Remove the affected row" rephrased as "correct at source or mark for exclusion" — the engine flags, it doesn't mutate uploaded data, and the action text shouldn't imply otherwise.

Open items 7 and 9 in the Open Items list are now obsolete (resolved in this version); kept in the list for traceability but marked.

**v5:** Reconciled against the actual `core/characteriser/integrity_checks.py`. Resolutions: INT-05 severity-scaling direction confirmed (Critical at ≥5%); INT-02 exemption mechanism corrected (parameter-type filter, not exemption list); INT-04 wording sharpened (≥50% isolated NaN heuristic); identity-rule tuple shape corrected to 4-field; ID-02 (UVT↔UV254) and ID-03 (TDS/EC) moved out of §3.4 and flagged for engineering decision; §3.6 dispositions firmed up (none of the v3 cross-family rules live in `integrity_checks.py`). §3.3 reflects WaterPoint's parameter-type filter exactly, with engineering decision deferred for AquaPoint's many LoD-prone parameters. Added Critical-flag implication/action text for INT-05 DOC>TOC case. Open Items table consolidated; Pending Reconciliation table updated to show what `integrity_checks.py` sighting resolved.

**v4:** Aligned to WaterPoint conventions inferred from `tests/test_integrity_checks.py`. Renamed integrity rules from `AV-INT-XX` to `INT-NN`. Renamed event rules to `EV-NN`. §3 restructured around five family rules (INT-01, INT-01b, INT-02, INT-03, INT-04, INT-05) with parameter-keyed configuration tables instead of 20 separate rules. Added §3.2 parameter-bounds configuration, §3.3 zero-exemption list, §3.4 identity rules, §3.5 Critical-flag implication/action text (mandatory per WaterPoint test), §3.6 cross-family rules awaiting engineering decision. Severity vocabulary updated to reference `SEV_CRITICAL` / `SEV_WARNING` / `SEV_INFO`. Pending Reconciliation table revised to show partial resolutions and remaining gaps.

**v3:** §2 promoted to a proper seventh registry (`source_water_classification`, codes AV-CLS-01..02), shaped consistently with the other six registries. Added `Indeterminate` output convention for missing-data cases. Added "Pending Reconciliation with WaterPoint Engine" section listing what needs sighting before code work.

**v2:** Removed all treated-water target thresholds (ADWG aesthetic / health values for iron, manganese, TDS, ammonia, nitrate as flag triggers). Removed USEPA SWTR turbidity values — those are treated-water (CFE) limits, not source-water descriptors. Removed microcystin-LR 1.3 µg/L as a treated-water health flag; retained it only as the ADWG Alert Level 2 raw-water classification trigger. Reframed event triggers as site-relative percentiles wherever principled. Added §2 — the ADWG source-water classification overlay (HBT categories + Cyanobacteria Alert Levels Framework). Reframed all caveats as evidence limits on the characterisation rather than treatment implications.

**v1:** Initial draft. Superseded for conflating source characterisation with treated-water compliance.

---

## References

- **ADWG:** NHMRC & NRMMC (2011, updated to v3.7 Jan 2022, PFAS update Jun 2025). *Australian Drinking Water Guidelines 6, 2011*. NHMRC, Canberra. Cyanobacteria Information Sheet; HBT Information Sheet 1.5.
- **WHO GDWQ:** WHO (2017). *Guidelines for Drinking-water Quality, Fourth Edition incorporating the First Addendum*. 2nd addendum 2022.
- **WSAA HBT Manual:** WSAA (2015). *Manual for the Application of Health-Based Targets for Drinking Water Safety*. [VERIFY edition.]
- **USEPA UV Manual:** US EPA (2006). *Ultraviolet Disinfection Guidance Manual*, EPA 815-R-06-007.
- **Crittenden et al.:** Crittenden, Trussell, Hand, Howe & Tchobanoglous (2012). *MWH's Water Treatment: Principles and Design*, 3rd ed., Wiley.
- **Standard Methods:** APHA/AWWA/WEF (2017). *Standard Methods*, 23rd ed.
- **Edzwald & Tobiason (1999):** *Water Science & Technology* 40(9):63–70.
- **Hem (1985):** USGS Water-Supply Paper 2254.
- **Helsel (2012):** *Statistics for Censored Environmental Data*, 2nd ed., Wiley.
- **Vollenweider (1982):** OECD *Eutrophication of Waters*.
- **Wetzel (2001):** *Limnology*, 3rd ed., Academic Press.
- **ISO 5667-14 (2014):** *Water Quality — Sampling — Part 14*.
- **Suffet et al. (1995):** *Advances in Taste-and-Odor Treatment and Control*, AWWA Research Foundation.
