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
    # Physical removal barriers
    "coagulation_flocculation": {
        "protozoa":  (0.5, 1.0, "Indicative. Removal depends on floc quality.", "indicative"),
        "bacteria":  (0.5, 1.0, "Indicative. Not a primary bacterial barrier.", "indicative"),
        "virus":     (0.0, 0.5, "Limited — viruses are very small.", "indicative"),
    },
    "sedimentation": {
        "protozoa":  (1.0, 2.0, "Gravity settling removes flocculated Cryptosporidium oocysts.", "indicative"),
        "bacteria":  (0.5, 1.0, "Indicative.", "indicative"),
        "virus":     (0.0, 0.5, "Limited virus settling.", "indicative"),
    },
    "daf": {
        "protozoa":  (1.5, 2.5, "DAF effective for Cryptosporidium when well-coagulated.", "validated"),
        "bacteria":  (1.0, 2.0, "Indicative.", "indicative"),
        "virus":     (0.5, 1.0, "Limited.", "indicative"),
    },
    "lamella_clarification": {
        "protozoa":  (1.0, 2.0, "Similar to conventional sedimentation.", "indicative"),
        "bacteria":  (0.5, 1.0, "Indicative.", "indicative"),
        "virus":     (0.0, 0.5, "Limited.", "indicative"),
    },
    "ballasted_clarification": {
        "protozoa":  (1.0, 2.5, "Can achieve higher Cp removal due to ballasted floc.", "indicative"),
        "bacteria":  (0.5, 1.0, "Indicative.", "indicative"),
        "virus":     (0.0, 0.5, "Limited.", "indicative"),
    },
    "rapid_gravity_filtration": {
        "protozoa":  (2.0, 3.0, "Validated. Key Cryptosporidium barrier when turbidity <0.1 NTU.", "validated"),
        "bacteria":  (1.0, 2.0, "Indicative.", "indicative"),
        "virus":     (1.0, 2.0, "Indicative. Depends on media type and run condition.", "indicative"),
    },
    "slow_sand_filtration": {
        "protozoa":  (2.0, 4.0, "Validated. Excellent Cryptosporidium barrier via schmutzdecke.", "validated"),
        "bacteria":  (2.0, 3.0, "Validated.", "validated"),
        "virus":     (1.0, 2.0, "Indicative. Slower biological removal.", "indicative"),
    },
    "mf_uf": {
        "protozoa":  (3.0, 4.0, "Validated. Absolute barrier for particles > membrane pore size.", "validated"),
        "bacteria":  (3.0, 4.0, "Validated.", "validated"),
        "virus":     (0.5, 2.0, "Partial removal — UF provides better virus removal than MF.", "validated"),
    },
    "ro": {
        "protozoa":  (4.0, 6.0, "Very high removal. Validated in advanced systems.", "validated"),
        "bacteria":  (4.0, 6.0, "Very high removal.", "validated"),
        "virus":     (3.0, 6.0, "Validated for high LRV systems.", "validated"),
    },
    "nf": {
        "protozoa":  (3.0, 5.0, "High removal.", "indicative"),
        "bacteria":  (3.0, 5.0, "High removal.", "indicative"),
        "virus":     (2.0, 4.0, "Depends on MWCO.", "indicative"),
    },

    # Disinfection barriers
    "chlorination": {
        "protozoa":  (0.0, 0.5, "Chlorine is NOT an effective Cryptosporidium or Giardia barrier "
                                 "at practical Ct values. Ct requirements are very high for Giardia.", "validated"),
        "bacteria":  (2.0, 4.0, "Validated. Effective primary disinfectant for bacteria.", "validated"),
        "virus":     (2.0, 4.0, "Validated. Effective for viruses at typical Ct.", "validated"),
    },
    "chloramination": {
        "protozoa":  (0.0, 0.0, "Chloramines provide no meaningful protozoan inactivation.", "validated"),
        "bacteria":  (0.5, 1.5, "Low inactivation — secondary residual only.", "validated"),
        "virus":     (0.5, 1.5, "Low inactivation — secondary residual only.", "validated"),
    },
    "uv_disinfection": {
        "protozoa":  (2.0, 4.0, "Validated. UV is the key protozoan inactivation barrier (Cryptosporidium, Giardia).", "validated"),
        "bacteria":  (2.0, 3.0, "Validated. Effective at typical doses.", "validated"),
        "virus":     (1.0, 4.0, "Validated. Higher UV doses required. LP vs. MP UV differs.", "validated"),
    },
    "ozonation": {
        "protozoa":  (0.5, 2.5, "Validated for Giardia. Cryptosporidium requires very high Ct. "
                                 "Credit is CT-verified and restricted.", "validated"),
        "bacteria":  (2.0, 4.0, "Validated. Strong oxidant.", "validated"),
        "virus":     (2.0, 4.0, "Validated. Effective virus inactivation.", "validated"),
    },
    "aop": {
        "protozoa":  (1.0, 3.0, "Indicative. UV/H₂O₂ provides UV-equivalent protozoan inactivation.", "indicative"),
        "bacteria":  (2.0, 4.0, "Indicative.", "indicative"),
        "virus":     (2.0, 4.0, "Indicative.", "indicative"),
    },

    # Source protection (credit in some frameworks)
    "source_protection": {
        "protozoa":  (0.5, 1.0, "Indicative source risk reduction.", "indicative"),
        "bacteria":  (0.5, 1.0, "Indicative.", "indicative"),
        "virus":     (0.5, 1.0, "Indicative.", "indicative"),
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
    for pathogen in PATHOGEN_CLASSES:
        total_low = sum(b.credited_low.get(pathogen, 0) for b in result.barriers)
        total_high = sum(b.credited_high.get(pathogen, 0) for b in result.barriers)
        required = required_lrv.get(pathogen, 0)
        result.total_credited_low[pathogen] = round(total_low, 1)
        result.total_credited_high[pathogen] = round(total_high, 1)
        result.gap_low[pathogen] = round(required - total_low, 1)
        result.gap_high[pathogen] = round(required - total_high, 1)
        result.meets_target_low[pathogen] = total_low >= required
        result.meets_target_high[pathogen] = total_high >= required

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
    for pathogen in PATHOGEN_CLASSES:
        if result.gap_high.get(pathogen, 0) > 0:
            result.key_risks.append(
                f"⚠ {pathogen.title()} LRV DEFICIT: required {result.required.get(pathogen, 0):.1f} log, "
                f"maximum credited {result.total_credited_high.get(pathogen, 0):.1f} log "
                f"(gap: {result.gap_high[pathogen]:.1f} log). Additional barrier required."
            )
        elif result.gap_low.get(pathogen, 0) > 0:
            result.key_risks.append(
                f"⚡ {pathogen.title()} LRV marginal: achieved only under optimistic conditions. "
                f"Validate barrier credits and consider additional redundancy."
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
    "F": ["coagulation_flocculation", "sedimentation", "rapid_gravity_filtration",
          "chlorination"],
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
