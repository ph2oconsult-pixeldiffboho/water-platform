"""
domains/wastewater/technology_signatures.py

TechnologySignature — canonical process description for each wastewater technology.

Purpose:
  1. Document the structural identity of each process (continuous vs SBR, clarifiers, etc.)
  2. Define expected output ranges relative to BNR baseline for QA cross-checks
  3. Single source of truth for process type metadata used across the platform

Refs:
  - Metcalf & Eddy 5th Ed, Chapter 7-8
  - WEF MOP 8, MOP 32, MOP 35
  - Nereda: de Kreuk 2006, van Dijk 2020, Royal HaskoningDHV design guidelines
  - MABR: Houweling 2017, Gross 2016
  - MBR: Judd 2010, WEF MBR design guide
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple


@dataclass
class TechnologySignature:
    """
    Canonical process signature for a wastewater treatment technology.

    Used for:
      - Report differentiation summary
      - QA checks (T1-T4)
      - UI display
    """
    code:  str
    name:  str

    # ── Process structure ─────────────────────────────────────────────────
    process_type: str
    # "continuous_flow" | "sbr" | "membrane_bioreactor" | "biofilm_hybrid" | "mabr_hybrid"

    has_secondary_clarifiers:  bool
    has_ras:                   bool   # return activated sludge
    has_mlr:                   bool   # mixed liquor recycle / nitrate recycle
    uses_batch_cycles:         bool   # SBR-type sequencing

    # ── Design ranges (planning level) ───────────────────────────────────
    typical_mlss_mg_l:     Tuple[float, float]   # (low, high)
    typical_srt_days:      Tuple[float, float]
    typical_hrt_hours:     Tuple[float, float]   # equivalent HRT range
    typical_yobs_kgvss_kgbod: Tuple[float, float]

    # ── Relative factors vs BNR baseline ─────────────────────────────────
    # These are screening-level sentinels, not deterministic outputs.
    # Used by QA rules T2-T4 to flag implausible similarity.
    footprint_factor_vs_bnr:  Tuple[float, float]   # (min, max) ratio to BNR
    sludge_factor_vs_bnr:     Tuple[float, float]
    energy_factor_vs_bnr:     Tuple[float, float]
    capex_factor_vs_bnr:      Tuple[float, float]

    # ── Risk profile ──────────────────────────────────────────────────────
    risk_profile: Dict[str, str] = field(default_factory=dict)
    # keys: technical, implementation, operational, regulatory
    # values: "Low" | "Moderate" | "High" | "Very High"

    # ── Key advantages and penalties vs BNR ──────────────────────────────
    advantage_vs_bnr: str = ""
    penalty_vs_bnr:   str = ""

    # ── Special notes ─────────────────────────────────────────────────────
    notes: str = ""

    @property
    def structural_summary(self) -> str:
        parts = [self.process_type.replace("_", " ").title()]
        if self.has_secondary_clarifiers: parts.append("with secondary clarifiers")
        else:                              parts.append("no secondary clarifiers")
        if self.uses_batch_cycles:        parts.append("SBR cycle")
        if self.has_ras:                  parts.append("RAS")
        if self.has_mlr:                  parts.append("MLR")
        return " | ".join(parts)


# ── Canonical signatures ──────────────────────────────────────────────────────

SIGNATURES: Dict[str, TechnologySignature] = {

    "bnr": TechnologySignature(
        code="bnr",
        name="Conventional BNR",
        process_type="continuous_flow",
        has_secondary_clarifiers=True,
        has_ras=True,
        has_mlr=True,
        uses_batch_cycles=False,
        typical_mlss_mg_l=(3000, 4500),
        typical_srt_days=(10, 18),
        typical_hrt_hours=(6, 14),
        typical_yobs_kgvss_kgbod=(0.28, 0.40),
        footprint_factor_vs_bnr=(1.0, 1.0),
        sludge_factor_vs_bnr=(1.0, 1.0),
        energy_factor_vs_bnr=(1.0, 1.0),
        capex_factor_vs_bnr=(1.0, 1.0),
        risk_profile={
            "technical": "Low", "implementation": "Low",
            "operational": "Low", "regulatory": "Low",
        },
        advantage_vs_bnr="Lowest delivery risk; well-understood process",
        penalty_vs_bnr="Largest footprint; highest sludge production",
        notes="A2O / UCT / Modified Ludzack-Ettinger configurations",
    ),

    "granular_sludge": TechnologySignature(
        code="granular_sludge",
        name="Aerobic Granular Sludge (Nereda®)",
        process_type="sbr",
        has_secondary_clarifiers=False,
        has_ras=False,
        has_mlr=False,
        uses_batch_cycles=True,
        typical_mlss_mg_l=(6000, 10000),
        typical_srt_days=(15, 25),
        typical_hrt_hours=(4, 9),
        typical_yobs_kgvss_kgbod=(0.28, 0.33),
        footprint_factor_vs_bnr=(0.60, 0.85),   # 15–40% smaller
        sludge_factor_vs_bnr=(0.75, 0.90),       # 10–25% less
        energy_factor_vs_bnr=(0.85, 1.15),       # similar or slightly lower
        capex_factor_vs_bnr=(0.80, 1.05),        # slightly lower (no clarifiers)
        risk_profile={
            "technical": "Moderate", "implementation": "Moderate",
            "operational": "High", "regulatory": "Moderate",
        },
        advantage_vs_bnr="Compact footprint; lower sludge; no clarifiers",
        penalty_vs_bnr="Higher operational complexity; granule stability risk; specialist startup",
        notes="SBR cycle: fill (anaerobic) → react (aeration) → settle → decant. "
              "Simultaneous nitrification-denitrification (SND) in granule gradient. "
              "Cold-climate performance penalty below ~12°C. "
              "3–6 month granule formation startup.",
    ),

    "bnr_mbr": TechnologySignature(
        code="bnr_mbr",
        name="BNR + MBR",
        process_type="membrane_bioreactor",
        has_secondary_clarifiers=False,  # membranes replace clarifiers
        has_ras=True,
        has_mlr=True,
        uses_batch_cycles=False,
        typical_mlss_mg_l=(8000, 14000),
        typical_srt_days=(15, 30),
        typical_hrt_hours=(4, 8),
        typical_yobs_kgvss_kgbod=(0.20, 0.30),
        footprint_factor_vs_bnr=(0.50, 0.75),   # significantly smaller
        sludge_factor_vs_bnr=(0.60, 0.85),
        energy_factor_vs_bnr=(1.40, 2.00),      # much higher (membrane scouring)
        capex_factor_vs_bnr=(1.40, 2.00),
        risk_profile={
            "technical": "Low", "implementation": "Moderate",
            "operational": "High", "regulatory": "Low",
        },
        advantage_vs_bnr="Smallest footprint; best effluent solids barrier; reuse-ready",
        penalty_vs_bnr="Highest energy and CAPEX; membrane fouling/replacement O&M",
        notes="Hollow-fibre or flat-sheet submerged membranes replace secondary clarifiers.",
    ),

    "ifas_mbbr": TechnologySignature(
        code="ifas_mbbr",
        name="IFAS / MBBR",
        process_type="biofilm_hybrid",
        has_secondary_clarifiers=True,
        has_ras=True,
        has_mlr=False,
        uses_batch_cycles=False,
        typical_mlss_mg_l=(2500, 4000),
        typical_srt_days=(8, 15),
        typical_hrt_hours=(5, 10),
        typical_yobs_kgvss_kgbod=(0.30, 0.45),
        footprint_factor_vs_bnr=(0.75, 1.0),
        sludge_factor_vs_bnr=(0.90, 1.10),
        energy_factor_vs_bnr=(1.00, 1.25),
        capex_factor_vs_bnr=(0.90, 1.15),
        risk_profile={
            "technical": "Low", "implementation": "Moderate",
            "operational": "Moderate", "regulatory": "Low",
        },
        advantage_vs_bnr="Upgrade pathway for existing plants; robust nitrification",
        penalty_vs_bnr="Media cost; higher aeration energy; limited full-scale TN precedent",
        notes="Integrated Fixed-Film Activated Sludge. "
              "Media fill 30–40% in aerobic zone. "
              "Good for nitrification upgrades on constrained sites.",
    ),

    "mabr_bnr": TechnologySignature(
        code="mabr_bnr",
        name="MABR + BNR Hybrid",
        process_type="mabr_hybrid",
        has_secondary_clarifiers=True,
        has_ras=True,
        has_mlr=True,
        uses_batch_cycles=False,
        typical_mlss_mg_l=(3000, 4500),
        typical_srt_days=(10, 18),
        typical_hrt_hours=(6, 14),
        typical_yobs_kgvss_kgbod=(0.28, 0.40),
        footprint_factor_vs_bnr=(0.90, 1.05),
        sludge_factor_vs_bnr=(0.95, 1.05),
        energy_factor_vs_bnr=(0.65, 0.85),      # lower aeration energy (bubble-free O2)
        capex_factor_vs_bnr=(1.15, 1.40),
        risk_profile={
            "technical": "Moderate", "implementation": "High",
            "operational": "Moderate", "regulatory": "High",
        },
        advantage_vs_bnr="Lowest aeration energy; strong cold-climate nitrification",
        penalty_vs_bnr="Highest CAPEX; limited regulatory precedent; specialist vendor",
        notes="Membrane-Aerated Biofilm Reactor retrofitted into BNR aerobic zone. "
              "Bubble-free O2 transfer (alpha~1.0). "
              "Regulatory precedent limited in AU/NZ.",
    ),
}


def get_signature(tech_code: str) -> Optional[TechnologySignature]:
    """Return the TechnologySignature for a given technology code, or None."""
    return SIGNATURES.get(tech_code)


def get_all_codes() -> list:
    return list(SIGNATURES.keys())
