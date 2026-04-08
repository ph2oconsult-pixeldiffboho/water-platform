"""
AquaPoint LRV Registry — Centralised Barrier Credit Source of Truth
All LRV credits are declared here once and read-only thereafter.
No section of the app may use different credit values.

Regulatory basis: WSAA Health-Based Targets / USEPA UVDGM 2006
Single-barrier cap: 4.0 log maximum per WSAA HBT rule.
"""
from dataclasses import dataclass, field
from typing import Optional


# ── Regulatory Framework Declaration ─────────────────────────────────────────
# This is the locked framework for the session. All downstream sections
# must pull from this. The consistency checker validates against it.

REGULATORY_FRAMEWORK = {
    "name": "WSAA Health-Based Targets / USEPA UVDGM 2006",
    "uv_protozoa_design_dose_mj_cm2": 22,
    "uv_bacteria_design_dose_mj_cm2": 40,
    "uv_virus_governing_organism": "adenovirus",
    "uv_virus_dose_for_4log_mj_cm2": 168,
    "single_barrier_max_log": 4.0,
    "reference_adwg": "ADWG 2022 (NHMRC/NRMMC)",
    "note": (
        "UV protozoa credit (4.0 log) is based on 22 mJ/cm2 LP UV dose per USEPA UVDGM 2006 Table 3-1. "
        "UV bacteria credit (4.0 log) is based on 40 mJ/cm2 LP UV dose per WSAA HBT design reference. "
        "UV virus credit (0.5-1.0 log) is governed by adenovirus resistance at LP UV — "
        "MS2 achieves ~3.0 log at 40 mJ/cm2 but adenovirus requires ~168 mJ/cm2 for 4 log. "
        "All credits capped at 4.0 log per WSAA HBT single-barrier rule."
    ),
}

# ── Required LRV Targets by Source Risk Class ─────────────────────────────────
REQUIRED_LRV_BY_RISK = {
    "potable_low_risk": {
        "protozoa": 3.0, "bacteria": 5.0, "virus": 5.0,
        "description": "Low-risk groundwater or highly protected source",
    },
    "potable_lower_moderate": {
        "protozoa": 4.0, "bacteria": 6.0, "virus": 6.0,
        "description": "Lower-moderate risk — upland reservoir, protected catchment",
    },
    "potable_moderate_risk": {
        "protozoa": 4.0, "bacteria": 6.0, "virus": 6.0,
        "description": "Moderate risk — groundwater-influenced, managed catchment",
    },
    "potable_high_risk": {
        "protozoa": 6.0, "bacteria": 8.0, "virus": 8.0,
        "description": "High risk — open surface water, variable catchment",
    },
    "potable_very_high_risk": {
        "protozoa": 7.0, "bacteria": 9.0, "virus": 9.0,
        "description": "Very high risk — extreme event source, poor catchment control",
    },
    "recycled_ipre": {
        "protozoa": 8.0, "bacteria": 10.0, "virus": 10.0,
        "description": "Indirect potable reuse — NRMMC/EPHC recycled water guidelines",
    },
}

# ── Centralised LRV Credit Registry ──────────────────────────────────────────
# Each entry: (low_credit, high_credit, note, validation_status)
# All values capped at 4.0 per WSAA HBT single-barrier rule.
# This registry is the SINGLE SOURCE OF TRUTH. All modules read from here.

LRV_CREDIT_REGISTRY = {

    # ── Physical removal ──────────────────────────────────────────────────────
    "coagulation_flocculation": {
        "protozoa": (0.0, 0.5,
            "Coagulation is an ENABLER — it conditions particles for downstream removal. "
            "No independent LRV credit. Credited only as part of a complete train.",
            "indicative"),
        "bacteria": (0.0, 0.0, "No independent credit.", "indicative"),
        "virus":    (0.0, 0.0, "No independent credit.", "indicative"),
    },
    "sedimentation": {
        "protozoa": (0.5, 1.5,
            "Gravity sedimentation of coagulated floc including Cryptosporidium oocysts. "
            "Credit conditional on well-coagulated feed and stable overflow rates.",
            "indicative"),
        "bacteria": (0.5, 1.0, "Indicative credit.", "indicative"),
        "virus":    (0.0, 0.5, "Limited virus removal by sedimentation.", "indicative"),
    },
    "daf": {
        "protozoa": (1.5, 2.0,
            "DAF is effective for Cryptosporidium when well-coagulated. "
            "Validated credit at 85-95% oocyst removal efficiency. "
            "Excluded at turbidity >50 NTU — flotation mechanism overwhelmed.",
            "validated"),
        "bacteria": (1.0, 1.5, "Validated. DAF removes bacteria-associated floc.", "validated"),
        "virus":    (0.5, 1.0, "Indicative. Limited direct virus removal.", "indicative"),
    },
    "lamella_clarification": {
        "protozoa": (0.5, 1.5, "Similar to conventional sedimentation.", "indicative"),
        "bacteria": (0.5, 1.0, "Indicative.", "indicative"),
        "virus":    (0.0, 0.5, "Limited.", "indicative"),
    },
    "ballasted_clarification": {
        "protozoa": (1.0, 2.0,
            "Ballasted floc improves Cryptosporidium capture vs conventional sedimentation. "
            "Effective at high turbidity events — designed for 600 NTU inlet.",
            "indicative"),
        "bacteria": (0.5, 1.0, "Indicative.", "indicative"),
        "virus":    (0.0, 0.5, "Indicative.", "indicative"),
    },
    "rapid_gravity_filtration": {
        "protozoa": (1.5, 2.5,
            "Key Cryptosporidium removal barrier when producing <0.1 NTU effluent. "
            "Credit conditional on turbidity performance — filter-to-waste protocol required "
            "at inlet turbidity >10 NTU. Credit is LOST if effluent turbidity >0.3 NTU.",
            "validated"),
        "bacteria": (0.5, 1.5, "Validated depth filtration removal.", "validated"),
        "virus":    (0.5, 1.0, "Indicative virus removal in depth filtration.", "indicative"),
    },
    "slow_sand_filtration": {
        "protozoa": (2.0, 3.5,
            "Biological schmutzdecke provides validated Cryptosporidium removal. "
            "Very large footprint — impractical at most urban/regional scales.",
            "validated"),
        "bacteria": (2.0, 3.0, "Validated biological and physical removal.", "validated"),
        "virus":    (1.0, 2.0, "Validated biological removal.", "validated"),
    },
    "mf_uf": {
        "protozoa": (3.5, 4.0,
            "Absolute physical barrier for protozoa — pore size excludes Cryptosporidium oocysts. "
            "Capped at 4.0 log per WSAA HBT single-barrier rule. "
            "Integrity testing (pressure hold) required to claim credit — "
            "any integrity breach invalidates the protozoan credit.",
            "validated"),
        "bacteria": (3.5, 4.0,
            "Absolute physical barrier for bacteria. Capped at 4.0 log.",
            "validated"),
        "virus":    (0.0, 2.0,
            "MF: negligible virus removal (pore size too large). "
            "UF (MWCO ≤100 kDa): up to 2 log virus removal. "
            "LP UV or chemical disinfection required for virus barrier.",
            "validated"),
    },
    "nf": {
        "protozoa": (3.0, 4.0, "High removal by size exclusion. Integrity dependent.", "validated"),
        "bacteria": (3.0, 4.0, "High removal. Capped at 4.0 log.", "validated"),
        "virus":    (1.5, 3.5, "Good virus removal depending on MWCO.", "validated"),
    },
    "ro": {
        "protozoa": (3.5, 4.0,
            "Very high removal. Capped at 4.0 log per WSAA HBT single-barrier rule. "
            "Integrity testing required to claim credit.",
            "validated"),
        "bacteria": (4.0, 4.0,
            "Very high removal. Capped at 4.0 log per WSAA HBT single-barrier rule.",
            "validated"),
        "virus":    (3.0, 4.0,
            "High removal. Capped at 4.0 log per WSAA HBT single-barrier rule. "
            "Integrity testing required.",
            "validated"),
    },

    # ── Disinfection ──────────────────────────────────────────────────────────
    "uv_disinfection": {
        "protozoa": (4.0, 4.0,
            "Validated. LP UV at 22 mJ/cm2 achieves 4 log Cryptosporidium and Giardia inactivation "
            "per USEPA UVDGM 2006 Table 3-1 (WSAA HBT framework). "
            "22 mJ/cm2 is the protozoa design dose. "
            "Capped at 4.0 log per WSAA HBT single-barrier rule. "
            "Credit conditional on validated dose delivery and UVT ≥72%.",
            "validated"),
        "bacteria": (4.0, 4.0,
            "Validated. 40 mJ/cm2 is the bacteria design dose per WSAA HBT reference. "
            "NOTE: 22 mJ/cm2 is the Cryptosporidium design dose — bacteria have a different "
            "(steeper) dose-response curve and are more UV-sensitive. "
            "At 40 mJ/cm2 (governing plant design dose), bacteria achieve 4 log inactivation. "
            "Capped at 4.0 log per WSAA HBT single-barrier rule.",
            "validated"),
        "virus":    (0.5, 1.0,
            "LP UV virus credit is governed by ADENOVIRUS RESISTANCE, not MS2 surrogate. "
            "At the 40 mJ/cm2 plant design dose: adenovirus achieves ~0.5-1.0 log inactivation. "
            "MS2 achieves ~3.0 log at 40 mJ/cm2 per USEPA UVDGM 2006 Table 3-1 — "
            "but MS2 does not represent adenovirus resistance. "
            "Adenovirus requires ~168 mJ/cm2 for 4 log LP UV — not a practical design dose. "
            "PRIMARY VIRUS INACTIVATION MUST COME FROM CHLORINE Ct.",
            "validated"),
    },
    "ozonation": {
        "protozoa": (0.0, 0.5,
            "CRITICAL: Cryptosporidium is highly resistant to ozone. "
            "Practical water treatment Ct (0.5-1.5 mg·min/L at 15°C) provides "
            "essentially 0 log Cryptosporidium inactivation. Giardia credit up to 0.5 log. "
            "Ozone is NOT a protozoan inactivation barrier at practical doses.",
            "validated"),
        "bacteria": (2.0, 3.5,
            "Validated. Strong oxidant — effective bacterial inactivation at practical Ct.",
            "validated"),
        "virus":    (2.0, 3.5,
            "Validated. Ozone effectively inactivates adenovirus at practical Ct — "
            "unlike LP UV which is limited by adenovirus resistance. "
            "Credit 2.0-3.5 log at practical ozone doses (0.5-2.5 mg/L).",
            "validated"),
    },
    "aop": {
        "protozoa": (1.0, 2.5,
            "UV/H2O2 AOP: credit from UV component only — same dose-response as uv_disinfection. "
            "O3/H2O2 (peroxone): H2O2 quenches ozone, reducing Ct; "
            "less protozoa credit than ozone alone at same dose.",
            "indicative"),
        "bacteria": (0.0, 0.0,
            "AOP bacterial LRV credit: ZERO — insufficient validated data at practical doses. "
            "Bacterial credit comes from the UV component (credited under uv_disinfection) "
            "or from downstream chlorination — not from H2O2 hydroxyl radical component.",
            "indicative"),
        "virus":    (0.0, 0.0,
            "AOP virus LRV credit: ZERO — insufficient validated data at practical doses. "
            "Virus credit must come from downstream chlorination Ct.",
            "indicative"),
    },
    "chlorination": {
        "protozoa": (0.0, 0.0,
            "ZERO protozoa credit. Chlorine does NOT inactivate Cryptosporidium at any "
            "practical water treatment Ct. Free chlorine is not a Cryptosporidium barrier. "
            "UV is mandatory for protozoan inactivation on surface water sources.",
            "validated"),
        "bacteria": (1.5, 3.0,
            "Validated. Free chlorine is effective for bacterial inactivation. "
            "Ct must be calculated at maximum expected pH and minimum temperature. "
            "IMPORTANT: Ammonia suppresses free chlorine — breakpoint chlorination "
            "required before Ct can be achieved when NH3 is present.",
            "validated"),
        "virus":    (2.0, 3.5,
            "Validated. Primary virus inactivation mechanism in Australian drinking water treatment. "
            "Ct dependent on pH, temperature, and contact time. "
            "At pH >8.0, virus inactivation efficiency is significantly reduced. "
            "This is the LOAD-BEARING virus barrier when LP UV is used for protozoa.",
            "validated"),
    },
    "chloramination": {
        "protozoa": (0.0, 0.0,
            "ZERO protozoa credit. Chloramines are not a protozoan inactivation barrier.",
            "validated"),
        "bacteria": (0.0, 1.0,
            "Distribution residual maintenance only. Not primary disinfection. "
            "Provides minor additional bacterial credit in distribution.",
            "indicative"),
        "virus":    (0.0, 1.0,
            "Distribution residual maintenance only. Not primary disinfection. "
            "Provides minor additional viral credit in distribution.",
            "indicative"),
    },

    # ── Source protection ─────────────────────────────────────────────────────
    "source_protection": {
        "protozoa": (0.0, 1.0,
            "Catchment management, protection zones, off-take management. "
            "Indicative credit for protected upland reservoirs or managed aquifers.",
            "indicative"),
        "bacteria": (0.0, 1.0, "Indicative.", "indicative"),
        "virus":    (0.0, 1.0, "Indicative.", "indicative"),
    },

    # ── Other ─────────────────────────────────────────────────────────────────
    "sludge_thickening": {
        "protozoa": (0.0, 0.0, "Residuals management — no LRV credit.", "indicative"),
        "bacteria": (0.0, 0.0, "No LRV credit.", "indicative"),
        "virus":    (0.0, 0.0, "No LRV credit.", "indicative"),
    },
    "brine_management": {
        "protozoa": (0.0, 0.0, "Residuals management — no LRV credit.", "indicative"),
        "bacteria": (0.0, 0.0, "No LRV credit.", "indicative"),
        "virus":    (0.0, 0.0, "No LRV credit.", "indicative"),
    },
    "gac": {
        "protozoa": (0.0, 0.0, "GAC/BAC is not a validated pathogen barrier.", "indicative"),
        "bacteria": (0.0, 0.5,
            "Biological BAC mode may provide minor bacterial credit. "
            "Not a primary bacterial barrier.",
            "indicative"),
        "virus":    (0.0, 0.0, "No validated virus LRV credit for GAC/BAC.", "indicative"),
    },
    "bac": {
        "protozoa": (0.0, 0.0, "BAC is not a validated pathogen barrier.", "indicative"),
        "bacteria": (0.0, 0.5, "Minor biological credit only.", "indicative"),
        "virus":    (0.0, 0.0, "No validated virus credit.", "indicative"),
    },
    "screening": {
        "protozoa": (0.0, 0.0, "Physical screening — no LRV credit.", "indicative"),
        "bacteria": (0.0, 0.0, "No LRV credit.", "indicative"),
        "virus":    (0.0, 0.0, "No LRV credit.", "indicative"),
    },
}

# ── Consistency validation ────────────────────────────────────────────────────

def validate_registry() -> list:
    """Validate that no credit exceeds the single-barrier cap. Returns list of violations."""
    cap = REGULATORY_FRAMEWORK["single_barrier_max_log"]
    violations = []
    for barrier, pathogens in LRV_CREDIT_REGISTRY.items():
        for pathogen, vals in pathogens.items():
            lo, hi = vals[0], vals[1]
            if hi > cap:
                violations.append(
                    f"{barrier}/{pathogen}: {hi:.1f} log exceeds {cap:.1f} log cap"
                )
    return violations


def get_credit(barrier_key: str, pathogen: str) -> tuple:
    """
    Get (low, high) LRV credit for a barrier/pathogen combination.
    Returns (0, 0) if not found. All callers must use this function —
    never access LRV_CREDIT_REGISTRY directly in report sections.
    """
    if barrier_key not in LRV_CREDIT_REGISTRY:
        return (0.0, 0.0)
    entry = LRV_CREDIT_REGISTRY[barrier_key].get(pathogen, (0.0, 0.0, "", ""))
    return (entry[0], entry[1])


def get_credit_note(barrier_key: str, pathogen: str) -> str:
    """Get the engineering note for a barrier/pathogen credit."""
    if barrier_key not in LRV_CREDIT_REGISTRY:
        return ""
    entry = LRV_CREDIT_REGISTRY[barrier_key].get(pathogen, (0.0, 0.0, "", ""))
    return entry[2] if len(entry) > 2 else ""


def get_framework_declaration() -> str:
    """Return a formatted regulatory framework declaration for report output."""
    fw = REGULATORY_FRAMEWORK
    return (
        f"**Regulatory framework:** {fw['name']}  \n"
        f"**UV protozoa design dose:** {fw['uv_protozoa_design_dose_mj_cm2']} mJ/cm² "
        f"(4 log Cryptosporidium — USEPA UVDGM 2006 Table 3-1)  \n"
        f"**UV bacteria design dose:** {fw['uv_bacteria_design_dose_mj_cm2']} mJ/cm² "
        f"(4 log bacteria — WSAA HBT)  \n"
        f"**UV virus governing organism:** {fw['uv_virus_governing_organism']} "
        f"(~168 mJ/cm² for 4 log — not a practical design dose)  \n"
        f"**Single-barrier maximum credit:** {fw['single_barrier_max_log']:.1f} log (WSAA HBT rule)  \n"
        f"**Reference:** {fw['reference_adwg']}"
    )


# ── Run validation on import ──────────────────────────────────────────────────
_violations = validate_registry()
if _violations:
    raise ValueError(
        f"LRV Registry validation failed — {len(_violations)} credit(s) exceed the "
        f"{REGULATORY_FRAMEWORK['single_barrier_max_log']:.1f} log single-barrier cap:\n"
        + "\n".join(_violations)
    )
