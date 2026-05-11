# AquaPoint Engineering Rule Table — Source Water Characterisation

> **This document is a forward specification, not a description of currently-shipping AquaPoint code.**
>
> AquaPoint today consumes `SourceWaterInputs` through its Decision Intelligence Layer (`apps/drinking_water_app/engine/dil_aquapoint.py`). It does **not** yet have a characteriser surface wired up.
>
> This table specifies how AquaPoint's source-water characterisation should look once the registries refactor described in *HANDOVER_characterisation_rollout.md* (§7 Session 1) lands. It is reconciled against the *existing* wastewater characteriser (`core/characteriser/integrity_checks.py`) so that AquaPoint can drop into the same engine cleanly when the time comes.
>
> Use this document to: (a) review and resolve the open engineering decisions before code work begins, and (b) check AquaPoint-specific values (parameter bounds, identity rules, classification overlays) for engineering correctness against current ADWG / WHO guidance.

---

**Status:** v5 — reconciled against WaterPoint's actual `core/characteriser/integrity_checks.py`. Replaces v4.
**Scope:** Source (raw) water characterisation only. The platform describes what the raw water *is*; it does not compare raw water against treated-water targets or recommend treatment.
**Format:** Mirrors `apps/wastewater_app/pages/page_08_manual.py` lines 493–537 (column layout still pending sight — see "Pending reconciliation").
**Architecture:** Seven registries — parameters, integrity_rules, ratio_libraries, event_rules, concerns, caveats, source_water_classification.

**WaterPoint convention alignment (confirmed against `core/characteriser/integrity_checks.py`):**
- Integrity rules use the `INT-NN` family pattern — five families (six with INT-01b), each applied across parameters via parameter-keyed configuration. Module distinction (water-treatment vs wastewater) is handled by the registry namespace, not by rule-ID prefixing.
- Severity constants: `SEV_CRITICAL`, `SEV_WARNING`, `SEV_INFO` imported from `core.characteriser.report`.
- Flag dataclass `CharacterisationFlag` fields: `rule_id`, `severity`, `parameter`, `pattern`, `message`, `implication`, `recommended_action`, `affected_row_indices` (`list[int]`).
- Multi-parameter rules (INT-05 identity violations) combine names in the `parameter` field as `"{num_param} vs {den_param}"`.
- INT-02 exemption is by `spec.parameter_type` (only `{"flow", "concentration", "load"}` are checked) plus a single name-substring carve-out (`"rain" in spec.name.lower()`). Other parameters are *not* checked.
- INT-01b severity scaling: `SEV_WARNING if pct_outside >= 1.0 else SEV_INFO`. Skipped if `typical_range is None` or `len(s) < 30`.
- INT-05 severity scaling: `SEV_CRITICAL if pct_violated >= 5.0 else SEV_WARNING`. Tolerance defaults to 5% of `den` for analytical noise.
- INT-05 identity tuples: `(num_param, den_param, label, description)`. Identity: `num ≤ den` per row.
- INT-04 fires only when isolated NaN (singleton missing values bordered by valid values) make up `>= 50%` of total NaN. Pattern detection: scattered = string coercion likely; clustered = sensor outage.

**Boundary statement (read first):**
This is a characterisation tool. Regulations enter the table in **exactly one** way: as source-water *classification overlays* — frameworks that categorise raw water by its observed properties (ADWG Health-Based Targets source-water categories, ADWG Cyanobacteria Alert Levels Framework). They do **not** enter as treated-water target thresholds. Iron, manganese, nitrate, microcystin and similar parameters appear in the dictionary as descriptors of the source; they are not flagged against ADWG health or aesthetic guideline values, because those values are about water leaving a tap.

The integrity rules below are about **data integrity** — physical impossibility, sensor faults, mathematical inconsistency, evidence gaps — not about whether the raw water "passes" anything.

**Citation convention:** Each band cites ADWG, WHO, USEPA, or peer-reviewed water-quality literature. `[VERIFY]` marks values for engineering review against current editions.
**Severities:** `Critical` (sample rejected from envelope) / `Warning` (flagged but retained) / `Info` (annotation).

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

The seventh registry. Each entry is a classification scheme drawn from an external framework that itself classifies raw water. Each scheme defines categories, the parameter(s) and statistic on which the categorisation is computed, and a "current category" output for the source. The engine reports the resulting category in the envelope memo. **No treatment implications are stated** — only the category and the framework that defines it.

| Code | Framework | Parameter(s) | Statistic | Categories (band → label) | Output | Reference |
|---|---|---|---|---|---|---|
| AV-CLS-01 | ADWG Health-Based Targets — Source-Water Category | E. coli at WTP inlet (P-26) | P95 of full record (organisms / 100 mL) | ≤ 1 → C1 Well protected; > 1 to ≤ 20 → C2 Moderately protected; > 20 to ≤ 2000 → C3 Poorly protected; > 2000 → C4 Unprotected | One of {C1, C2, C3, C4, Indeterminate} + P95 value + sample count | WSAA (2015) *Manual for the Application of Health-Based Targets for Drinking Water Safety*; ADWG HBT Information Sheet 1.5. [VERIFY: band boundaries against the current WSAA manual edition; verify P95 is the correct statistic vs P90 or annual mean.] |
| AV-CLS-02 | ADWG Cyanobacteria Alert Levels — raw source | Toxic-species cyanobacterial cell count (P-19); biovolume if reported; microcystin-LR (P-20) | Max observed in record (instantaneous trigger) | < LoD → Below Detection; LoD to ≤ 500 cells/mL → Detection; > 500 cells/mL OR biovolume > 0.04 mm³/L → Alert Level 1; > 6,500 cells/mL OR biovolume > 0.6 mm³/L OR microcystin-LR > 1.3 µg/L → Alert Level 2 | Highest alert level reached in record + date(s) of breach + parameter(s) that triggered | NHMRC ADWG (2011, v3.7 2022) Cyanobacteria Information Sheet. (Microcystin-LR 1.3 µg/L is the ADWG raw-water alert escalation trigger, **not** a treated-water health limit.) [VERIFY: biovolume thresholds against current ADWG edition; verify whether "max observed" or "any sample" is the right trigger statistic.] |

**Indeterminate output:** if the parameter required for a classification is absent or has insufficient samples, the registry returns `Indeterminate` with a reason — never a default category. This is reported transparently in the memo (Section 6, evidence limits) rather than silently degrading to a guess.

**Adding a new classification:** other source-water classification frameworks (e.g. trophic-state classification, salinity classification for desalination feed) would slot in as AV-CLS-03, AV-CLS-04, … with the same shape. This is why §2 is a registry and not a hard-coded overlay.

**Architectural note for the integrator:** AV-CLS-XX entries are read by the engine's main orchestrator at envelope-build time and surfaced in Section 1 (or wherever the wastewater module places equivalent "source classification" output, if any — see "Pending reconciliation"). They do **not** participate in event detection or integrity checking; they are post-aggregation classification outputs.

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

**Open question:** for parameters where the typical range is "0 – X" (cyano cell count, microcystin, geosmin, 2-MIB, total algae), `typical_lower = 0` may conflict with INT-02 (implausible zero). Decide whether INT-01b should fire on values below typical_lower of zero, or whether typical_lower=0 means "no lower-bound check." Mirror whatever the wastewater module does for parameters like ammonia-N where similar low-typical-bound issues arise. [VERIFY against `integrity_checks.py`.]

### 3.3 INT-02 exemptions: parameter typing and zero-handling

**Mechanism (from WaterPoint):** INT-02 only fires when `spec.parameter_type ∈ {"flow", "concentration", "load"}` AND `"rain"` is not in the parameter name. Other types are skipped silently. There is **no separate exemption list** — exemption is by parameter type assignment in §1.

For the AquaPoint parameters in §1, the following table is the proposed `parameter_type` assignment with the resulting INT-02 behaviour:

| Parameter | Proposed `parameter_type` | INT-02 fires? | Rationale |
|---|---|---|---|
| P-01 Turbidity | `concentration` | Yes | Zero turbidity is implausible on a live raw-water sample (always some particulate). |
| P-02 True colour | `concentration` | Yes | Zero colour implausible. |
| P-03 UV254 | `concentration` | Yes | Zero UV254 implausible (always some absorbance). |
| P-04 UVT | `dimensionless` | No | UVT is a percentage; 100% is the meaningful upper-bound value, 0% would be physical (caught by INT-01). |
| P-05 DOC, P-06 TOC | `concentration` | Yes | Zero implausible on natural waters. |
| P-07 pH | `index` | No | pH is an index, not a concentration; zero is physical (caught by INT-01 if outside [0, 14]). |
| P-08 Temperature | `index` | No | Temperature is an index; zero °C is physical. |
| P-09 Alkalinity, P-10 Hardness, P-11 EC, P-12 TDS | `concentration` | Yes | Zero implausible on natural waters. |
| P-13 Iron, P-14 Manganese, P-15 Ammonia, P-16 Nitrate, P-17 TP | `concentration` | **Engineering decision required — see below** | Below-LoD values commonly reported as literal 0 in source data. |
| P-18 Chlorophyll-a, P-24 Total algal cells | `concentration` | **Engineering decision required** | True absence is common outside bloom season. |
| P-19 Cyano cell count, P-20 Microcystin-LR | `concentration` | **Engineering decision required** | True absence is common outside bloom season; below-LoD reporting common. |
| P-21 Geosmin, P-22 2-MIB | `concentration` | **Engineering decision required** | Below-LoD common. |
| P-23 DO | `concentration` | Yes | Zero DO is implausible at the surface (oxic) but possible at depth in stratified systems. |
| P-25 SS | `concentration` | Yes | Zero implausible on raw water. |
| P-26 E. coli | `concentration` | **Engineering decision required** | Below-LoD reporting common; LoD convention varies between labs. |

**Engineering decision required:** the parameters above marked "engineering decision required" can legitimately read zero when below LoD. WaterPoint handles rainfall (the only such parameter in wastewater) via a single hardcoded substring check: `"rain" in spec.name.lower()`. AquaPoint has many more parameters in this situation. Two paths:

- **Option A — Type-and-substring carve-outs.** Keep these as `parameter_type = "concentration"` and add per-parameter substring carve-outs to `_check_zero_values` (analogous to rainfall). Pros: minimal change to WaterPoint's pattern. Cons: list of exceptions grows; the substring approach is brittle (matches by name, not by intent).
- **Option B — New `parameter_type`.** Introduce e.g. `parameter_type = "censored_concentration"` for parameters where below-LoD literal zeros are legitimate. Add it to the *not-checked* list in INT-02. Pros: explicit intent in the type; no per-parameter substring hack. Cons: introduces a new type that WaterPoint doesn't have; affects type taxonomy elsewhere if `parameter_type` is consumed by other rules.
- **Option C — Loader normalisation.** Convert literal zeros in below-LoD parameters to `<LoD` markers (or `LoD/2`) at the loader, before INT-02 runs. Pros: separates the "is this zero real" question from integrity checking. Cons: requires upload-format work and per-parameter LoD declarations.

Recommendation deferred to engineering review. **Until decided, v5 leaves these parameters as `parameter_type = "concentration"` with the consequence that INT-02 will fire frequently on AquaPoint sources with low metals/nutrients — which is loud but not wrong.** Whichever path is chosen, the result should be documented in the parameter registry so it's discoverable.

### 3.4 INT-05 identity rules

**Shape (from WaterPoint):** identities are 4-tuples `(num_param, den_param, label, description)` — strictly `num ≤ den` per row, no equation forms, no two-sided windows. Tolerance defaults to 5% of `den` for analytical noise (`noise_tolerance_pct = 5.0` in `_check_row_level_identity`). For AquaPoint, only one v3-era identity fits this shape cleanly:

| `num_param` | `den_param` | `label` | `description` |
|---|---|---|---|
| `doc_mg_l` | `toc_mg_l` | DOC ≤ TOC | Dissolved organic carbon is the filterable fraction of total organic carbon; DOC > TOC is a definitional impossibility on a single sample. |

That is the **only** AquaPoint identity that fits INT-05's `num ≤ den` per-row form. The other two candidates from v3/v4 don't fit:

#### ID-02 — UVT ↔ UV254 Beer-Lambert consistency

**Why it doesn't fit:** the check is `|100·10^(-UV254) − UVT| > 5 pp` — a *bilateral tolerance band around a derived equation*, not a one-sided `num ≤ den`. INT-05's machinery is unsuited.

**Engineering options (deferred):**
- Move to ratio library as a diagnostic descriptor of method consistency, not an integrity flag.
- Add a new integrity-rule family `INT-06` for derived-parameter mathematical consistency. Would require new code in `core.characteriser.integrity_checks`.
- Handle at the loader / parameter-derivation layer: only accept one of (UVT, UV254) in the upload schema and compute the other internally. Eliminates the question.
- Leave it as a documented evidence-limit caveat rather than a checked rule.

Flagged for engineering decision.

#### ID-03 — TDS/EC window

**Why it doesn't fit:** the check is a population-level statistic ("> 10% of samples have TDS/EC ratio outside `[0.50, 0.85]`"). INT-05 operates per row, not population-level. Even per-row, the check is two-sided (a window), not `num ≤ den`.

**Engineering options (deferred):**
- Move to ratio library as `R-07` (already present in §4) and drop the integrity-level flag entirely. The ratio descriptor in the envelope memo will surface unusual TDS/EC behaviour without needing an integrity rule.
- Add a new family for population-level statistical checks if other AquaPoint parameters need similar checks (currently only this one).
- Leave it as a documented evidence-limit caveat.

Flagged for engineering decision.

**Position recommendation:** for both ID-02 and ID-03, the lightest-touch resolution is to leave them out of the integrity registry entirely and rely on the ratio library (§4) for the diagnostic, plus per-concern caveats (§7) for evidence-limit notes. This matches the spirit of "characterisation, not compliance checking" and avoids inventing new rule families that don't exist in WaterPoint. Engineering review confirms or overrides.

### 3.5 Critical-flag implication and recommended-action text

WaterPoint's tests require non-empty `implication` and `recommended_action` strings on `SEV_CRITICAL` flags. For AquaPoint's source-water-specific Critical conditions:

| Parameter | Implication text | Recommended action text |
|---|---|---|
| P-07 pH < 0 or > 14 | The value is non-physical; pH is mathematically bounded to [0, 14]. The reading is a data-entry error, sensor fault, or unit confusion (e.g. mV reported as pH). | Verify the source dataset's pH column units. Remove the affected row from the envelope dataset or correct it from the original record. |
| P-01 Turbidity < 0 | Negative turbidity is non-physical; nephelometric and ratio-turbidity instruments cannot return values below zero. Indicates sensor fault or data-entry error. | Check the sensor calibration log for the affected period. Remove the affected row or correct from the lab record. |
| P-08 Temperature outside -2 to 40 °C | Surface water cannot sit outside this range in any AU temperate catchment. Most likely Fahrenheit-as-Celsius unit confusion, sensor fault, or air-temperature reading. | Verify units of the temperature column in the source dataset. Cross-check against any second temperature record for the same period. |
| P-04 UVT outside [0, 100] % | UVT is a percentage; values outside [0, 100] indicate a derived-value calculation error or units mismatch. | Verify the UVT calculation against UV254 absorbance and the assumed path length. |
| P-09, P-13–P-17, P-26 negative concentrations | Negative concentrations are non-physical. Indicates sensor fault, lab data-entry error, or analyte interference flagged as negative by the instrument. | Verify the source lab report. Remove the affected row or correct from the original record. |
| INT-05 `doc_mg_l vs toc_mg_l` at ≥5% rows | Stoichiometric impossibility on ≥5% of rows where both DOC and TOC are reported. Indicates row-level data error: lab QA failure, sample mismatch (different sample dates reported on the same row), unit confusion, or transcription error. Statistics computed over the violating rows are unreliable. | Review the affected rows. Confirm DOC and TOC were measured on the same sample with consistent units. If samples were taken on different days or stored on the same row by accident, separate them. If a unit error (e.g. one in mg/L, the other in g/m³), correct at source. |

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
| R-07 | TDS/EC | TDS / conductivity | Salinity character (also ID-03 in §3.4). | 0.50 – 0.85 | Hem (1985). |
| R-08 | NH₄-N / NO₃-N | ammonia-N / nitrate-N | Redox / N-cycle state of source. High ratio = recent organic-N loading or anoxic. | <0.1 (oxic) to >1 (anoxic/fresh) | Wetzel *Limnology* 3rd ed. (2001). |
| R-09 | Cyanobacteria / total algae | cyanobacteria / total algal cells | Cyanobacterial dominance fraction. Feeds Alert Levels classification. | 0 – 1 | NHMRC ADWG Cyanobacteria info sheet. |
| R-10 | T&O sum | geosmin + 2-MIB | Combined taste & odour loading. | <10 ng/L acceptable; >20 ng/L likely complaints | Suffet et al. (1995); WaterRA. |
| R-11 | DOC seasonal range | max(DOC) − min(DOC) | Seasonal swing magnitude. Diagnostic for "is one design DOC value sufficient?" | 2 – 8 mg/L typical | Crittenden Ch. 3; WSAA *Source Water Characterisation Guideline*. [VERIFY: this WSAA title exists; otherwise replace with a peer-reviewed reference.] |
| R-12 | Turbidity:Colour | turbidity / true colour | Particle-vs-organic character of the source. | 0.1 – 5 NTU/HU | Crittenden Ch. 9. |

---

## 5. Event Rules (EV-NN)

Each event is a defined window in which the source water exhibits a **distinct character** relative to its own typical envelope. Events are detected from observed data; the engine characterises co-occurring parameters over the window. No treated-water target is involved in event definition.

**[VERIFY: event-rule naming convention.** The integrity rules in WaterPoint are `INT-NN`; by analogy v4 names event rules `EV-NN`. Confirm against the wastewater module's event-detection code once sighted — actual convention may differ.]

| Code | Event | Trigger | Co-parameters captured | Min duration | Reference |
|---|---|---|---|---|---|
| EV-01 | High-turbidity event | turbidity exceeds the site's own P95 for ≥ 2 consecutive samples AND is rising | Colour, DOC, TOC, pH, EC, iron, manganese | ≥ 1 day | Site-relative threshold per WSAA *Source Water Characterisation* guidance (event detection from observed envelope, not from a target). [VERIFY citation.] |
| EV-02 | Algal-bloom event | chlorophyll-a > 3 × site median for ≥ 7 days OR total algal cells > 15,000 cells/mL sustained ≥ 7 days | UV254, DOC, pH, DO, geosmin, 2-MIB, TP | ≥ 7 days | OECD eutrophication classification (Vollenweider 1982); site-relative trigger for non-eutrophic baselines. |
| EV-03 | Cyanobacterial alert | Any escalation to ADWG Alert Level 1 or 2 (see AV-CLS-02 in §2) | All algal markers, chlorophyll-a, T&O, NH₄-N | ≥ 1 sample (trigger is instant) | ADWG Cyanobacteria Information Sheet — Alert Levels Framework. |
| EV-04 | High-DOC event | DOC > site P90 AND SUVA > 3 | UV254, colour, TOC, pH, temperature | ≥ 1 day | Edzwald & Tobiason (1999) on DOC character; site-relative trigger. |
| EV-05 | Low-UVT event | UVT < site P10 sustained ≥ 1 day | UV254, DOC, colour, turbidity, iron | ≥ 1 day | USEPA UV Disinfection Guidance Manual §4; site-relative trigger (not a treated-water spec). |
| EV-06 | Cold-water event | Temperature < site P10 sustained ≥ 14 days | All co-occurring source parameters | ≥ 14 days | Crittenden Ch. 9 on temperature-dependent source-water behaviour; site-relative trigger. |

**Note:** Events are triggered against the **site's own observed envelope** (site-relative percentiles) wherever possible, not against absolute regulatory numbers. This keeps the event definition characterisation-centric: an event is "this source deviating from itself," not "this source breaching some target." The cyanobacterial alert is the one exception because the ADWG framework is itself a raw-water classification.

---

## 6. Pre-built Concerns → Ratio Priority Map

For each concern, the ordered list of ratios most diagnostic of that source-water character. The engine surfaces these prominently in the envelope memo when the concern is selected.

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
4. **Site-relative vs absolute event triggers (§5):** EV-01, EV-04, EV-05, EV-06 all use site-relative percentiles. This is the characterisation-pure approach. EV-02 uses a hybrid (site-relative for chl-a, absolute 15,000 cells/mL for total algae). EV-03 is purely absolute (ADWG Alert Levels). Decide whether to push EV-02 fully site-relative too.
5. **E. coli LoD handling:** the v3 rule on this has been moved out of the integrity registry (see §3.6 item 3) — it belongs at the upload-validation layer rather than in `integrity_checks.py`. Confirm with engineering where this lives.
6. **Parameter scope:** P-26 (E. coli) is included because it drives AV-CLS-01. If E. coli isn't in the AquaPoint upload schema, AV-CLS-01 returns `Indeterminate` and the parameter is optional rather than required.
7. **INT-01b severity-scaling threshold (1%):** confirmed by the WaterPoint test (`test_int01b_severity_scales_with_count`). Confirm whether this 1% threshold is hardcoded in `integrity_checks.py` or configurable per parameter.
8. **INT-05 severity-scaling threshold (≥5%):** v4 conjectures Critical at ≥5% based on the v3 wording, but the WaterPoint test only verifies Warning at low violation count. Confirm direction and threshold from the module source.
9. **Identity-rule ID-03 (TDS/EC window):** unclear whether this fits INT-05's per-row pattern. See §3.4 open question; resolution depends on what WaterPoint's INT-05 actually does internally.
10. **Population-level integrity checks:** v3 had several rules that don't fit any inherited family — stuck-sensor, sampling gaps, record duration, censored-data fraction, chl-a vs total algae rank correlation. v4 has flagged these in §3.6 for engineering decision; they may belong in a separate "evidence limits" or "methodological consistency" registry rather than `integrity_checks.py`.

---

## Pending Reconciliation with WaterPoint Engine

`core/characteriser/integrity_checks.py` is now sighted (resolves most §3-related items). Updated status table:

| Item | Status | Files to inspect |
|---|---|---|
| Naming convention | **Resolved for integrity.** `INT-NN` confirmed. Event-rule and classification naming (`EV-NN`, `AV-CLS-NN`) still inferred by analogy. | Event-detection module, `concerns.py` |
| Severity vocabulary | **Resolved.** `SEV_CRITICAL`, `SEV_WARNING`, `SEV_INFO` imported from `core.characteriser.report`. |
| Flag dataclass shape | **Resolved.** `CharacterisationFlag` with fields `rule_id`, `severity`, `parameter`, `pattern`, `message`, `implication`, `recommended_action`, `affected_row_indices: list[int]`. |
| Rule-family structure | **Resolved.** Five families. v5 §3 mirrors. |
| Severity-scaling thresholds | **Resolved.** INT-01b at 1%, INT-05 at 5%, both hardcoded in `integrity_checks.py`. Not per-parameter configurable in the current code. |
| INT-02 exemption mechanism | **Resolved.** By `parameter_type` filter plus `"rain"` substring carve-out. v5 §3.3 reflects, with engineering decision deferred for AquaPoint's many LoD-zero parameters. |
| Identity-rule shape | **Resolved.** 4-tuple `(num_param, den_param, label, description)`. Tolerance global default. v5 §3.4 reflects. |
| Rule-table format (page_08_manual.py) | **Open.** Column layout still needs verification. Lower priority now that registries shape is firm. | `apps/wastewater_app/pages/page_08_manual.py` |
| Seventh registry shape (AV-CLS) | **Open.** Where does AV-CLS-XX output surface in the memo? | `core/characteriser/orchestrator.py`, `core/characteriser/design_envelope.py`, `core/characteriser/report.py` |
| Event-rule registry shape | **Open.** Naming (`EV-NN`?), shape, and site-relative percentile support. | `core/characteriser/coincidence.py` (stub per handover §10 — confirmed) plus wherever real event detection lives. |
| Concerns → ratio priority map | **Open.** Shape that `concerns.py` consumes. | Concerns module (not yet present per `ls core/characteriser/`). |
| Memo output shape | **Open.** Section structure, chart placement, AV-CLS surfacing. | `core/characteriser/envelope_renderer.py`, `core/characteriser/report.py`, an example output from `phase_5/example_outputs/clean/`. |
| Population-level checks placement | **Resolved.** Not in `integrity_checks.py`. They live elsewhere (probably the dataset-confidence layer that demotes downstream confidence). v5 §3.6 reflects. |

**Next files to sight, in priority order:**
1. `core/characteriser/report.py` — confirms `CharacterisationFlag` dataclass details, severity constants, and likely the memo report shape.
2. `core/characteriser/orchestrator.py` — confirms how the seven registries plug in and where AV-CLS-XX surfaces.
3. One example output from `phase_5/example_outputs/clean/` — confirms memo structure and AV-CLS placement empirically.
4. `apps/wastewater_app/pages/page_08_manual.py` lines 493–537 — confirms the table-presentation format for engineering review.

---

## Changelog

**v5 (this version):** Reconciled against the actual `core/characteriser/integrity_checks.py`. Resolutions: INT-05 severity-scaling direction confirmed (Critical at ≥5%); INT-02 exemption mechanism corrected (parameter-type filter, not exemption list); INT-04 wording sharpened (≥50% isolated NaN heuristic); identity-rule tuple shape corrected to 4-field; ID-02 (UVT↔UV254) and ID-03 (TDS/EC) moved out of §3.4 and flagged for engineering decision; §3.6 dispositions firmed up (none of the v3 cross-family rules live in `integrity_checks.py`). §3.3 reflects WaterPoint's parameter-type filter exactly, with engineering decision deferred for AquaPoint's many LoD-prone parameters. Added Critical-flag implication/action text for INT-05 DOC>TOC case. Open Items table consolidated; Pending Reconciliation table updated to show what `integrity_checks.py` sighting resolved.

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
