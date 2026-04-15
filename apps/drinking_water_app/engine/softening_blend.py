"""
apps/drinking_water_app/engine/softening_blend.py

Split-stream softening blend calculator.

In split-stream softening, only a fraction of the total flow passes through
the softening stage. The bypass stream is blended with the softened stream
to achieve the target hardness and CCPP in the product water.

This avoids treating 100% of the flow to very low hardness (over-softening)
and then having to add back hardness via recarbonation.

Engineering basis:
  - Simple mass balance on hardness (mg/L as CaCO3)
  - CCPP estimated from Langelier Saturation Index (LSI) approximation
  - Lime dose calculated from stoichiometry for carbonate hardness removal
  - Soda ash dose for non-carbonate hardness if required
  - Chemical cost from constants

CCPP (Calcium Carbonate Precipitation Potential):
  Positive CCPP → scale-forming → distribution pipe scaling
  Negative CCPP → corrosive → pipe corrosion
  Target: -5 to 0 mg/L (as CaCO3) per Table 8 spec

ph2o Consulting — AquaPoint v3.0
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional

# ── Target ranges (from Table 8 treated water spec) ──────────────────────────
TARGET_HARDNESS_MIN = 50.0     # mg/L CaCO3 — avoid over-softening
TARGET_HARDNESS_MAX = 200.0    # mg/L CaCO3 — ADWG aesthetic limit
TARGET_CCPP_MIN = -5.0         # mg/L CaCO3 (corrosion threshold)
TARGET_CCPP_MAX = 0.0          # mg/L CaCO3 (scale threshold)
TARGET_ALKALINITY_MIN = 30.0   # mg/L CaCO3 (TWY spec: ≥30)

# Stoichiometry: lime dose to remove carbonate hardness
# Ca(OH)2 + Ca(HCO3)2 → 2CaCO3 + 2H2O
# 1 mol Ca(OH)2 (74 g/mol) removes 1 mol CaCO3 hardness (100 g/mol)
# → lime dose (mg/L) = carbonate_hardness_removed (mg/L CaCO3) × 74/100 × 1.1 (excess)
LIME_STOICH = 74.0 / 100.0     # kg lime / kg CaCO3 hardness removed
LIME_EXCESS  = 1.15             # 15% stoichiometric excess — practical
SODAASH_STOICH = 106.0 / 100.0 # Na2CO3 per CaCO3 non-carbonate hardness

# Chemical unit costs from constants
LIME_COST_AUD_KG_PURE    = 0.20   # $/kg Ca(OH)2
SODAASH_COST_AUD_KG_PURE = 0.45   # $/kg Na2CO3

# Softening residual hardness (what the softening stage achieves)
# Lime softening to: ~80 mg/L CaCO3 (practical minimum without over-softening)
SOFTENED_HARDNESS = 80.0     # mg/L CaCO3
SOFTENED_ALKALINITY = 40.0   # mg/L CaCO3 (post-softening, pre-recarbonation)


@dataclass
class SofteningBlendOption:
    """Results for one split-stream fraction."""
    softening_fraction_pct: float           # % of flow through softening stage
    softening_flow_ML_d: float              # ML/d through softener
    bypass_flow_ML_d: float                 # ML/d bypassing softener
    blended_hardness_mg_l: float            # product hardness mg/L CaCO3
    blended_alkalinity_mg_l: float          # product alkalinity mg/L CaCO3
    ccpp_approx: float                      # approximate CCPP mg/L CaCO3
    hardness_compliant: bool                # within ADWG 200 mg/L
    ccpp_compliant: bool                    # within -5 to 0 spec
    alkalinity_compliant: bool              # ≥30 mg/L
    fully_compliant: bool                   # all three pass
    lime_dose_mg_l: float                   # mg/L applied to softening stream
    soda_ash_dose_mg_l: float               # mg/L applied to softening stream
    lime_annual_cost_AUD: float             # $/yr for full plant flow basis
    soda_ash_annual_cost_AUD: float         # $/yr for full plant flow basis
    total_chemical_cost_AUD: float          # $/yr combined
    sludge_production_t_d: float            # t/d dry solids from softening
    notes: List[str] = field(default_factory=list)


@dataclass
class SofteningBlendAnalysis:
    """Full split-stream analysis across 0-100% in 10% increments."""
    total_flow_ML_d: float
    raw_hardness_mg_l: float
    raw_alkalinity_mg_l: float
    raw_tds_mg_l: float
    product_ph: float
    options: List[SofteningBlendOption] = field(default_factory=list)
    recommended_fraction_pct: Optional[float] = None
    recommended_option: Optional[SofteningBlendOption] = None
    recommendation_rationale: str = ""


def _estimate_ccpp(hardness_mg_l: float, alkalinity_mg_l: float,
                   ph: float, temp_c: float = 20.0,
                   ca_fraction: float = 0.75) -> float:
    """
    Estimate CCPP using Langelier Saturation Index (LSI) approach.
    CCPP ≈ LSI × (alkalinity / 2.5)  — concept-stage approximation.

    LSI = pH - pHs
    pHs = (pK2 - pKs) + pCa + pAlk

    Positive CCPP → scale-forming. Negative → corrosive.
    Target for most potable water specs: -5 to 0 mg/L CaCO3.
    """
    import math
    if hardness_mg_l <= 0 or alkalinity_mg_l <= 0:
        return 0.0

    pKs = 8.34   # calcite solubility at 20°C
    pK2 = 10.33  # carbonate second dissociation at 20°C

    # Ca2+ from hardness (75% Ca, 25% Mg is typical)
    ca_mg_l = hardness_mg_l * ca_fraction * 40.08 / 50.045
    ca_mol_l = ca_mg_l / 40_080

    # HCO3- from alkalinity (mg/L CaCO3 → mol/L)
    alk_mol_l = alkalinity_mg_l / 50_000

    pCa  = -math.log10(ca_mol_l)
    pAlk = -math.log10(alk_mol_l)
    pHs  = (pK2 - pKs) + pCa + pAlk
    lsi  = ph - pHs

    ccpp = lsi * (alkalinity_mg_l / 2.5)
    return round(ccpp, 2)


def calculate_softening_blend(
    total_flow_ML_d: float,
    raw_hardness_mg_l: float,        # mg/L as CaCO3
    raw_alkalinity_mg_l: float,      # mg/L as CaCO3
    raw_tds_mg_l: float,
    product_ph: float = 7.8,         # target product water pH after recarbonation
                                     # Lime softening raises pH to ~10.5; CO2 recarbonation
                                     # brings it back to this target. 7.8 achieves CCPP ≈ -3
                                     # to -1 for typical softened waters.
    temp_c: float = 20.0,
    carbonate_fraction: float = 0.70,  # fraction of hardness that is carbonate hardness
                                       # High alkalinity sources: 0.65-0.75
                                       # Low alkalinity sources: 0.40-0.55
    ca_fraction: float = 0.75,         # fraction of hardness as Ca (vs Mg)
) -> SofteningBlendAnalysis:
    """
    Evaluate split-stream softening at 0%, 10%, 20% ... 100% of flow.

    Split-stream softening treats only a fraction of the total flow through
    the softening stage, then blends softened and bypass streams to achieve
    target hardness and CCPP. This minimises capital, chemical cost, and
    sludge production vs full-flow softening.

    carbonate_fraction: fraction of total hardness that is carbonate hardness.
    Non-carbonate hardness requires soda ash; carbonate needs lime only.

    Note: If no split fraction achieves CCPP compliance, full-flow softening
    is required. This typically occurs when raw alkalinity is very high
    (>200 mg/L CaCO3) relative to hardness.
    """
    analysis = SofteningBlendAnalysis(
        total_flow_ML_d=total_flow_ML_d,
        raw_hardness_mg_l=raw_hardness_mg_l,
        raw_alkalinity_mg_l=raw_alkalinity_mg_l,
        raw_tds_mg_l=raw_tds_mg_l,
        product_ph=product_ph,
    )

    annual_ML = total_flow_ML_d * 365
    carbonate_hardness   = raw_hardness_mg_l * carbonate_fraction
    noncarbonate_hardness = raw_hardness_mg_l * (1 - carbonate_fraction)

    for pct in range(0, 110, 10):
        f = pct / 100.0
        soft_flow   = total_flow_ML_d * f
        bypass_flow = total_flow_ML_d * (1 - f)

        if pct == 0:
            # No softening — raw water passes through
            blended_h  = raw_hardness_mg_l
            blended_alk = raw_alkalinity_mg_l
            lime_dose   = 0.0
            soda_dose   = 0.0
            sludge_t_d  = 0.0
        else:
            # Softened stream exits at SOFTENED_HARDNESS
            # Blend: blended = (softened × f + raw × (1-f))
            blended_h   = SOFTENED_HARDNESS * f + raw_hardness_mg_l * (1 - f)
            blended_alk = SOFTENED_ALKALINITY * f + raw_alkalinity_mg_l * (1 - f)

            # Lime dose (applied to softening stream, expressed as mg/L of that stream)
            carb_removed = max(0, carbonate_hardness - SOFTENED_HARDNESS * carbonate_fraction)
            lime_dose    = carb_removed * LIME_STOICH * LIME_EXCESS * 1000 / 1000
            # mg/L CaCO3 × (74/100) × 1.15 = mg/L Ca(OH)2 applied to softening stream

            # Soda ash dose for non-carbonate hardness
            nc_removed  = max(0, noncarbonate_hardness - SOFTENED_HARDNESS * (1 - carbonate_fraction))
            soda_dose   = nc_removed * SODAASH_STOICH

            # Sludge from softening: CaCO3 precipitate ≈ hardness removed as CaCO3
            hardness_removed_kg_d = carb_removed * soft_flow  # mg/L × ML/d = kg/d
            sludge_t_d = hardness_removed_kg_d / 1000        # kg → tonnes

        # CCPP at blended conditions
        ccpp = _estimate_ccpp(blended_h, blended_alk, product_ph, temp_c, ca_fraction)

        # Annual chemical costs (on total plant flow basis)
        # Lime applied to soft_flow stream
        lime_annual_kg  = lime_dose * soft_flow * 365    # mg/L × ML/d × 365 = kg/yr
        soda_annual_kg  = soda_dose * soft_flow * 365
        lime_cost   = lime_annual_kg  * LIME_COST_AUD_KG_PURE
        soda_cost   = soda_annual_kg  * SODAASH_COST_AUD_KG_PURE
        total_cost  = lime_cost + soda_cost

        # Compliance checks
        h_ok   = TARGET_HARDNESS_MIN <= blended_h <= TARGET_HARDNESS_MAX
        ccpp_ok = TARGET_CCPP_MIN <= ccpp <= TARGET_CCPP_MAX
        alk_ok  = blended_alk >= TARGET_ALKALINITY_MIN
        ok      = h_ok and ccpp_ok and alk_ok

        notes = []
        if pct == 0:
            notes.append("No softening — raw water quality passes through untreated")
        if not h_ok:
            if blended_h > TARGET_HARDNESS_MAX:
                notes.append(f"Hardness {blended_h:.0f} mg/L exceeds ADWG 200 mg/L")
            else:
                notes.append(f"Hardness {blended_h:.0f} mg/L below practical minimum — over-softened")
        if not ccpp_ok:
            if ccpp > TARGET_CCPP_MAX:
                notes.append(f"CCPP +{ccpp:.1f} → scale-forming — distribution pipe risk")
            else:
                notes.append(f"CCPP {ccpp:.1f} → corrosive — below -5 threshold")
        if not alk_ok:
            notes.append(f"Alkalinity {blended_alk:.0f} mg/L below minimum 30 mg/L")
        if ok:
            notes.append("All targets met — viable blend fraction")

        opt = SofteningBlendOption(
            softening_fraction_pct    = float(pct),
            softening_flow_ML_d       = round(soft_flow, 1),
            bypass_flow_ML_d          = round(bypass_flow, 1),
            blended_hardness_mg_l     = round(blended_h, 1),
            blended_alkalinity_mg_l   = round(blended_alk, 1),
            ccpp_approx               = round(ccpp, 2),
            hardness_compliant        = h_ok,
            ccpp_compliant            = ccpp_ok,
            alkalinity_compliant      = alk_ok,
            fully_compliant           = ok,
            lime_dose_mg_l            = round(lime_dose, 1),
            soda_ash_dose_mg_l        = round(soda_dose, 1),
            lime_annual_cost_AUD      = round(lime_cost, 0),
            soda_ash_annual_cost_AUD  = round(soda_cost, 0),
            total_chemical_cost_AUD   = round(total_cost, 0),
            sludge_production_t_d     = round(sludge_t_d, 1),
            notes                     = notes,
        )
        analysis.options.append(opt)

    # Recommend: minimum compliant fraction (lowest capital/chemical cost)
    compliant = [o for o in analysis.options if o.fully_compliant]
    if compliant:
        rec = min(compliant, key=lambda o: o.softening_fraction_pct)
        analysis.recommended_fraction_pct = rec.softening_fraction_pct
        analysis.recommended_option = rec
        analysis.recommendation_rationale = (
            f"Minimum viable split-stream fraction is {rec.softening_fraction_pct:.0f}% "
            f"({rec.softening_flow_ML_d:.1f} ML/d softened, {rec.bypass_flow_ML_d:.1f} ML/d bypass). "
            f"Blended hardness: {rec.blended_hardness_mg_l:.0f} mg/L CaCO₃. "
            f"CCPP: {rec.ccpp_approx:+.1f} mg/L. "
            f"Lime dose to softening stream: {rec.lime_dose_mg_l:.0f} mg/L. "
            f"Chemical cost: ${rec.total_chemical_cost_AUD/1e6:.2f}M/yr. "
            f"Treating a smaller fraction reduces softener capital, chemical use, "
            f"and sludge production — while achieving the same product water quality."
        )
    else:
        analysis.recommendation_rationale = (
            "No single blend fraction achieves all targets simultaneously. "
            "Review raw water inputs or target specifications."
        )

    return analysis
