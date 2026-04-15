"""
AquaPoint Reasoning Engine — LRV Parallel Thread
Log Reduction Value accounting by pathogen class.

Runs in parallel through the decision structure — not a post-analysis bolt-on.
Assigns credited LRVs to each barrier, assesses redundancy, and flags gaps.
"""

from dataclasses import dataclass, field
from typing import Optional


# ─── LRV Credit Library ───────────────────────────────────────────────────────
# (credited_low, credited_high, notes, validated_or_indicative)

LRV_BARRIER_CREDITS = {
    # ── Physical removal barriers ──────────────────────────────────────────────
    # IMPORTANT: Credits reflect what regulators would accept under ADWG 2022.
    # Coagulation-flocculation is an ENABLER of downstream barriers, not an
    # independent LRV barrier. No standalone protozoa/virus credit is awarded.
    # Sedimentation and filtration credits are conditional on coagulation quality
    # and upstream turbidity — indicative credits assume well-optimised conditions.
    "coagulation_flocculation": {
        "protozoa":  (0.0, 0.0, "Not an independent LRV barrier. Enables clarification and "
                                 "filtration performance. Credit assigned to downstream steps.", "validated"),
        "bacteria":  (0.0, 0.5, "Marginal. Most credit assigned to downstream filtration.", "indicative"),
        "virus":     (0.0, 0.0, "No independent virus removal credit.", "validated"),
    },
    "sedimentation": {
        "protozoa":  (0.5, 1.5, "Gravity settling of coagulated Cryptosporidium oocysts. "
                                 "Credit conditional on coagulation optimisation.", "indicative"),
        "bacteria":  (0.5, 1.0, "Indicative. Requires effective coagulation upstream.", "indicative"),
        "virus":     (0.0, 0.5, "Limited virus settling. Viruses are colloidal.", "indicative"),
    },

    "chemical_softening": {
        "protozoa":  (1.0, 2.0, "High pH during lime softening inactivates protozoa; co-precipitation adds physical removal.", "indicative"),
        "bacteria":  (1.5, 3.0, "pH >10 during lime softening lethal to most bacteria. Credit conditional on achieving target pH.", "validated"),
        "virus":     (1.0, 2.5, "Lime at pH >11 provides meaningful virus inactivation. pH-dependent — credit requires pH verification.", "indicative"),
    },

    "actiflo_carb": {
        "protozoa":  (3.0, 4.0, "Ballasted clarification + microsand floc provides validated protozoa removal. "
                              "Paper (Kruger/Veolia): 90-99.9% algae removal including cyanobacteria. "
                              "Credit is physical settling, not PAC.", "validated"),
        "bacteria":  (1.5, 2.5, "Ballasted coagulation/settling provides bacterial removal. "
                              "PAC contact provides adsorptive removal at >10 min contact time.", "indicative"),
        "virus":     (1.0, 2.0, "Coagulation and ballasted settling provide partial virus removal. "
                              "PAC adsorption credit indicative at >10 min contact time.", "indicative"),
    },

    "daf": {
        "protozoa":  (1.5, 2.0, "DAF effective for Cryptosporidium when well-coagulated. "
                                 "Validated at 1.5–2.0 log in Australian DAF studies (WRc, AWWARF).", "validated"),
        "bacteria":  (1.0, 1.5, "Indicative.", "indicative"),
        "virus":     (0.5, 1.0, "Limited. Viruses not effectively floated.", "indicative"),
    },
    "lamella_clarification": {
        "protozoa":  (0.5, 1.5, "Similar performance to conventional sedimentation.", "indicative"),
        "bacteria":  (0.5, 1.0, "Indicative.", "indicative"),
        "virus":     (0.0, 0.5, "Limited.", "indicative"),
    },
    "ballasted_clarification": {
        "protozoa":  (1.0, 2.0, "Ballasted floc can improve Cryptosporidium removal "
                                 "vs conventional sedimentation.", "indicative"),
        "bacteria":  (0.5, 1.0, "Indicative.", "indicative"),
        "virus":     (0.0, 0.5, "Limited.", "indicative"),
    },
    "rapid_gravity_filtration": {
        "protozoa":  (1.5, 2.5, "Key Cryptosporidium removal barrier. Credit conditional on "
                                 "filter effluent turbidity <0.1 NTU and effective upstream coagulation. "
                                 "Validated at 1.5–2.5 log under good operating conditions (ADWG Table 10.1).", "validated"),
        "bacteria":  (0.5, 1.5, "Indicative. Not a primary bacterial barrier.", "indicative"),
        "virus":     (0.5, 1.0, "Limited. Viruses pass most granular filters without chemical aid.", "indicative"),
    },
    "slow_sand_filtration": {
        "protozoa":  (2.0, 3.5, "Validated. Excellent Cryptosporidium barrier via biological "
                                 "schmutzdecke when mature. Requires stable influent quality.", "validated"),
        "bacteria":  (2.0, 3.0, "Validated.", "validated"),
        "virus":     (1.0, 2.0, "Biological removal. Indicative.", "indicative"),
    },
    "mf_uf": {
        "protozoa":  (3.0, 4.0, "Validated absolute barrier for particles above membrane pore size. "
                                 "Integrity testing required to claim full credit (ADWG).", "validated"),
        "bacteria":  (3.0, 4.0, "Validated.", "validated"),
        "virus":     (0.0, 2.0, "MF: minimal virus removal. UF: up to 2 log if MWCO ≤100 kDa. "
                                 "Credit requires integrity verification.", "validated"),
    },
    "ro": {
        "protozoa":  (3.5, 4.0, "Very high removal. Validated in advanced water recycling systems. "
                                 "Credit capped at 4.0 log maximum per WSAA HBT single-barrier rule — "
                                 "no single process may be credited more than 4 log for any pathogen. "
                                 "Integrity testing required to claim credit. "
                                 "Where MF/UF precedes RO, protozoan credit is dominated by MF/UF.", "validated"),
        "bacteria":  (4.0, 4.0, "Very high removal. Capped at 4.0 log maximum per WSAA HBT "
                                 "single-barrier rule — no single process credited >4 log. "
                                 "Integrity testing required.", "validated"),
        "virus":     (3.0, 4.0, "High removal. Capped at 4.0 log maximum per WSAA HBT "
                                 "single-barrier rule — no single process credited >4 log. "
                                 "Credit requires integrity testing and validated rejection data.", "validated"),
    },
    "nf": {
        "protozoa":  (3.0, 4.0, "High removal. Depends on MWCO and membrane condition.", "indicative"),
        "bacteria":  (3.0, 4.0, "High removal.", "indicative"),
        "virus":     (1.5, 3.5, "Variable. Depends strongly on MWCO.", "indicative"),
    },

    # ── Disinfection barriers ─────────────────────────────────────────────────
    "chlorination": {
        "protozoa":  (0.0, 0.0, "Chlorine provides NO validated credit for Cryptosporidium at "
                                 "practical water treatment Ct values (<10 mg·min/L). "
                                 "Giardia credit only at high Ct (>65 mg·min/L at pH 6–7). "
                                 "Chlorine alone is not an adequate protozoan barrier.", "validated"),
        "bacteria":  (1.5, 3.0, "Validated. Effective at typical Ct (>0.2 mg·min/L). "
                                 "Credit reduced at high TOC or pH >8.", "validated"),
        "virus":     (2.0, 3.5, "Validated. Effective for enteric viruses at typical Ct. "
                                 "Credit reduced at high TOC or high pH.", "validated"),
    },
    "chloramination": {
        "protozoa":  (0.0, 0.0, "Chloramines provide NO protozoan inactivation credit.", "validated"),
        "bacteria":  (0.0, 1.0, "Very low inactivation — secondary residual maintenance only.", "validated"),
        "virus":     (0.0, 1.0, "Very low inactivation — secondary residual maintenance only.", "validated"),
    },
    "uv_disinfection": {
        "protozoa":  (4.0, 4.0, "Validated. LP UV at 22 mJ/cm² achieves 4 log Cryptosporidium "
                                 "and 4 log Giardia inactivation per USEPA UVDGM 2006 Table 3-1, "
                                 "referenced by WSAA Health-Based Targets. "
                                 "22 mJ/cm² is the protozoa design dose. "
                                 "Capped at 4.0 log per WSAA HBT single-barrier rule. "
                                 "Credit conditional on validated dose delivery and UVT ≥72%.", "validated"),
        "bacteria":  (4.0, 4.0, "Validated. LP UV at 40 mJ/cm² achieves 4 log bacterial inactivation "
                                 "(WSAA HBT / reviewer reference). "
                                 "40 mJ/cm² is the bacteria design dose — separate from the 22 mJ/cm² "
                                 "protozoa design dose. The governing plant design dose is therefore "
                                 "40 mJ/cm² (the higher of the two), at which protozoa also achieve "
                                 "4 log (already met at 22 mJ/cm²). "
                                 "Capped at 4.0 log per WSAA HBT single-barrier rule. "
                                 "NOTE: bacteria are not in USEPA UVDGM 2006 Table 3-1; "
                                 "this credit uses the WSAA HBT bacteria design dose reference.", "validated"),
        "virus":     (0.5, 1.0, "LP UV virus credit is GOVERNED BY ADENOVIRUS RESISTANCE, "
                                 "not MS2 surrogate. "
                                 "At the 40 mJ/cm² design dose: adenovirus achieves approximately "
                                 "0.5–1.0 log LP UV inactivation. "
                                 "MS2 surrogate (USEPA UVDGM 2006 Table 3-1) achieves ~3.0 log at "
                                 "40 mJ/cm² — but MS2 does not represent adenovirus resistance. "
                                 "Human adenovirus requires ~168 mJ/cm² for 4 log LP UV — "
                                 "not a practical design dose. "
                                 "UV virus credit is therefore 0.5–1.0 log at the 40 mJ/cm² design dose. "
                                 "PRIMARY VIRUS INACTIVATION CREDIT MUST COME FROM CHLORINE Ct — "
                                 "LP UV alone is not an adequate virus barrier.", "validated"),
    },
    "ozonation": {
        "protozoa":  (0.0, 0.5, "CRITICAL: Cryptosporidium is highly resistant to ozone. "
                                 "Practical water treatment Ct (0.5–1.5 mg·min/L at 15°C) provides "
                                 "essentially 0 log Cryptosporidium inactivation. Giardia credit "
                                 "up to 0.5 log at low Ct. High ozone credit for protozoa requires "
                                 "Ct >10 mg·min/L which is NOT achievable in most plants.", "validated"),
        "bacteria":  (2.0, 3.5, "Validated. Strong oxidant — effective bacterial inactivation.", "validated"),
        "virus":     (2.0, 3.5, "Validated. Ozone is effective for virus inactivation at practical "
                                 "water treatment Ct (0.5–2.0 mg·min/L). Credit 2.0–3.5 log at "
                                 "practical ozone doses. Ozone provides good virus inactivation — "
                                 "unlike LP UV which is limited by adenovirus resistance, ozone "
                                 "inactivates adenovirus effectively at practical Ct values.", "validated"),
    },
    "aop": {
        "protozoa":  (1.0, 2.5, "UV/H₂O₂ AOP: credit from the UV component only (protozoa). "
                                 "Same dose-response as uv_disinfection for Cryptosporidium. "
                                 "O₃/H₂O₂ (peroxone): limited additional Crypto credit over ozone alone — "
                                 "H₂O₂ quenches ozone and reduces ozone Ct, so peroxone provides "
                                 "less protozoa credit than ozone alone at same dose.", "indicative"),
        "bacteria":  (0.0, 0.0, "AOP bacterial LRV credit: ZERO — insufficient validated data for "
                                 "a defensible planning-level credit. "
                                 "UV component provides bacterial inactivation (see uv_disinfection) "
                                 "but the additional H₂O₂ hydroxyl radical component does not have "
                                 "validated bacterial LRV data at practical AOP doses for drinking water. "
                                 "Bacterial credit must come from the UV component (credited separately) "
                                 "or from downstream chlorination.", "indicative"),
        "virus":     (0.0, 0.0, "AOP virus LRV credit: ZERO — insufficient validated data for "
                                 "a defensible planning-level credit. "
                                 "LP UV component at practical AOP doses achieves ~2.0–2.5 log virus "
                                 "(same as uv_disinfection, adenovirus governs). "
                                 "H₂O₂ hydroxyl radical contribution to virus inactivation is not "
                                 "validated to a standard that supports a credited LRV at this stage. "
                                 "Virus credit must come from downstream chlorination.", "indicative"),
    },

    # ── Source protection ─────────────────────────────────────────────────────
    "source_protection": {
        "protozoa":  (0.0, 1.0, "Indicative source risk reduction. Only credited in some "
                                 "jurisdictional frameworks with formal catchment management.", "indicative"),
        "bacteria":  (0.0, 1.0, "Indicative.", "indicative"),
        "virus":     (0.0, 1.0, "Indicative.", "indicative"),
    },
}

# ─── Pathogen Classes and Default Required LRVs ───────────────────────────────

PATHOGEN_CLASSES = ["protozoa", "bacteria", "virus"]

DEFAULT_LRV_TARGETS = {
    "potable_low_risk": {
        "protozoa": 4.0, "bacteria": 6.0, "virus": 6.0,
    },
    "potable_moderate_risk": {
        "protozoa": 5.0, "bacteria": 7.0, "virus": 7.0,
    },
    "potable_high_risk": {
        "protozoa": 6.0, "bacteria": 8.0, "virus": 8.0,
    },
    "recycled_ipre": {
        "protozoa": 6.0, "bacteria": 6.0, "virus": 7.0,
    },
    "recycled_dpr": {
        "protozoa": 8.0, "bacteria": 8.0, "virus": 10.0,
    },
}


@dataclass
class BarrierLRV:
    barrier_key: str = ""
    barrier_label: str = ""
    credited_low: dict = field(default_factory=dict)   # pathogen → float
    credited_high: dict = field(default_factory=dict)
    notes: dict = field(default_factory=dict)
    validated: dict = field(default_factory=dict)       # pathogen → "validated" | "indicative"


@dataclass
class LRVResult:
    """Full LRV accounting result."""
    required: dict = field(default_factory=dict)          # pathogen → float
    barriers: list = field(default_factory=list)          # list of BarrierLRV
    total_credited_low: dict = field(default_factory=dict)
    total_credited_high: dict = field(default_factory=dict)
    gap_low: dict = field(default_factory=dict)           # positive = deficit
    gap_high: dict = field(default_factory=dict)
    meets_target_low: dict = field(default_factory=dict)  # pathogen → bool
    meets_target_high: dict = field(default_factory=dict)
    single_barrier_dependence: list = field(default_factory=list)
    key_risks: list = field(default_factory=list)
    disinfection_assessment: dict = field(default_factory=dict)


# ─── LRV Calculation ─────────────────────────────────────────────────────────

def calculate_lrv(
    selected_barriers: list,           # list of barrier keys from LRV_BARRIER_CREDITS
    required_lrv: dict,                # {pathogen: float}
    source_risk: str = "potable_moderate_risk",
) -> LRVResult:
    """
    Calculate total LRV credits across selected barriers.
    Runs the parallel LRV thread.
    """
    result = LRVResult()
    result.required = required_lrv

    # Build barrier list
    for barrier_key in selected_barriers:
        if barrier_key not in LRV_BARRIER_CREDITS:
            continue
        credits = LRV_BARRIER_CREDITS[barrier_key]
        blrv = BarrierLRV(barrier_key=barrier_key, barrier_label=barrier_key.replace("_", " ").title())
        for pathogen in PATHOGEN_CLASSES:
            if pathogen in credits:
                low, high, note, val = credits[pathogen]
                blrv.credited_low[pathogen] = low
                blrv.credited_high[pathogen] = high
                blrv.notes[pathogen] = note
                blrv.validated[pathogen] = val
            else:
                blrv.credited_low[pathogen] = 0.0
                blrv.credited_high[pathogen] = 0.0
                blrv.notes[pathogen] = "No data."
                blrv.validated[pathogen] = "indicative"
        result.barriers.append(blrv)

    # Sum totals
    # NOTE: Raw arithmetic summation is used for gap/compliance checks.
    # Display totals are capped at (required + 2.0) to avoid presenting
    # physically implausible values (e.g. 12 log protozoa, 13 log bacteria).
    # The cap does not affect compliance assessment — gap_high uses raw totals.
    DISPLAY_REDUNDANCY_CAP = 2.0   # max log surplus above target shown in UI
    for pathogen in PATHOGEN_CLASSES:
        total_low = sum(b.credited_low.get(pathogen, 0) for b in result.barriers)
        total_high = sum(b.credited_high.get(pathogen, 0) for b in result.barriers)
        required = required_lrv.get(pathogen, 0)
        # Compliance uses raw totals
        result.gap_low[pathogen] = round(required - total_low, 1)
        result.gap_high[pathogen] = round(required - total_high, 1)
        result.meets_target_low[pathogen] = total_low >= required
        result.meets_target_high[pathogen] = total_high >= required
        # Display uses capped totals
        cap = required + DISPLAY_REDUNDANCY_CAP if required > 0 else total_high
        result.total_credited_low[pathogen] = round(min(total_low, cap), 1)
        result.total_credited_high[pathogen] = round(min(total_high, cap), 1)

    # Single-barrier dependence check
    for pathogen in PATHOGEN_CLASSES:
        required = required_lrv.get(pathogen, 0)
        if required == 0:
            continue
        for b in result.barriers:
            credit = b.credited_high.get(pathogen, 0)
            if required > 0 and credit / max(required, 0.01) > 0.5:
                result.single_barrier_dependence.append(
                    f"{pathogen.title()}: '{b.barrier_label}' provides >{credit/required*100:.0f}% "
                    f"of required LRV ({credit:.1f} of {required:.1f} log). "
                    f"Loss of this barrier creates significant pathogen risk."
                )

    # Key risks
    # Note: gap_high uses raw (uncapped) totals for compliance assessment.
    # This means a gap_high > 0 is a genuine deficit even if credited appears capped.
    for pathogen in PATHOGEN_CLASSES:
        raw_high = sum(b.credited_high.get(pathogen, 0) for b in result.barriers)
        raw_low  = sum(b.credited_low.get(pathogen, 0) for b in result.barriers)
        required = result.required.get(pathogen, 0)
        if raw_high < required:
            result.key_risks.append(
                f"⚠ {pathogen.title()} LRV DEFICIT: required {required:.1f} log, "
                f"maximum credited {raw_high:.1f} log "
                f"(gap: {required - raw_high:.1f} log). Additional barrier required."
            )
        elif raw_low < required:
            # Meets target at high end only — conditional on all barriers performing optimally.
            # For virus specifically, flag that Ct verification is load-bearing.
            if pathogen == "virus":
                result.key_risks.append(
                    f"⚡ Virus LRV conditional: target {required:.1f} log met only under 'best case' "                    f"barrier performance ({raw_low:.1f}–{raw_high:.1f} log range). "                    f"Free chlorine Ct is the load-bearing virus barrier — "                    f"verify Ct at governing pH and minimum design temperature. "                    f"Chloramine provides no additional virus inactivation credit."
                )
            else:
                result.key_risks.append(
                    f"⚡ {pathogen.title()} LRV marginal: target achieved only under optimistic "                    f"conditions ({raw_low:.1f}–{raw_high:.1f} log). "                    f"Validate barrier credits and consider additional redundancy."
                )

    # Disinfection adequacy assessment
    disinfection_barriers = [b for b in result.barriers
                             if b.barrier_key in ["chlorination", "chloramination", "uv_disinfection", "ozonation", "aop"]]
    chlorine_present = any(b.barrier_key == "chlorination" for b in disinfection_barriers)
    chloramine_present = any(b.barrier_key == "chloramination" for b in disinfection_barriers)
    uv_present = any(b.barrier_key == "uv_disinfection" for b in disinfection_barriers)
    ozone_present = any(b.barrier_key == "ozonation" for b in disinfection_barriers)

    result.disinfection_assessment = {
        "primary_disinfection": chlorine_present or ozone_present or uv_present,
        "secondary_residual": chlorine_present or chloramine_present,
        "protozoan_inactivation_barrier": uv_present or (ozone_present),
        "chlorine_present": chlorine_present,
        "chloramine_present": chloramine_present,
        "uv_present": uv_present,
        "ozone_present": ozone_present,
    }

    if not result.disinfection_assessment["primary_disinfection"]:
        result.key_risks.append(
            "⚠ CRITICAL: No primary disinfection barrier identified in treatment train. "
            "Minimum requirement is chlorination or UV."
        )
    if not result.disinfection_assessment["secondary_residual"]:
        result.key_risks.append(
            "⚠ No secondary disinfectant residual identified. "
            "Distribution system protection requires a maintained chlorine or chloramine residual."
        )
    if not result.disinfection_assessment["protozoan_inactivation_barrier"]:
        result.key_risks.append(
            "⚠ No validated protozoan inactivation barrier: "
            "Chlorine alone is not an adequate Cryptosporidium barrier. "
            "UV disinfection or ozone (at verified Ct) is required for protozoan inactivation."
        )

    return result


# ─── LRV Archetype Mapping ────────────────────────────────────────────────────

ARCHETYPE_DEFAULT_BARRIERS = {
    "A": ["coagulation_flocculation", "rapid_gravity_filtration",
          "chlorination", "uv_disinfection"],
    "B": ["coagulation_flocculation", "sedimentation", "rapid_gravity_filtration",
          "chlorination", "uv_disinfection"],
    "C": ["coagulation_flocculation", "lamella_clarification", "rapid_gravity_filtration",
          "chlorination", "uv_disinfection"],
    "D": ["coagulation_flocculation", "daf", "rapid_gravity_filtration",
          "chlorination", "uv_disinfection"],
    "E": ["coagulation_flocculation", "sedimentation", "rapid_gravity_filtration",
          "chlorination", "uv_disinfection"],
    "F": ["coagulation_flocculation", "chemical_softening", "rapid_gravity_filtration",
          "uv_disinfection", "chlorination"],
    "G": ["coagulation_flocculation", "sedimentation", "rapid_gravity_filtration",
          "ozonation", "chlorination", "uv_disinfection"],
    "H": ["coagulation_flocculation", "mf_uf", "ro",
          "uv_disinfection", "chloramination"],
    "I": ["coagulation_flocculation", "sedimentation", "rapid_gravity_filtration",
          "chlorination", "uv_disinfection"],
}


def get_lrv_for_archetype(archetype_key: str, required_lrv: dict,
                           source_risk: str = "potable_moderate_risk") -> LRVResult:
    """Calculate LRV result for a given archetype's default barrier set."""
    barriers = ARCHETYPE_DEFAULT_BARRIERS.get(archetype_key, [])
    return calculate_lrv(barriers, required_lrv, source_risk)
