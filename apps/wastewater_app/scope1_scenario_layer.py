"""
apps/wastewater_app/scope1_scenario_layer.py

Scope 1 Methodology-Revision Scenario Layer
============================================

Produces a methodology-revision sensitivity view of the plant's Scope 1
N₂O number under three N₂O emission-factor accounting regimes:

  1. Legacy (IPCC 2006 default)         EF = 0.0035 (0.35% of influent TN)
  2. Current IPCC 2019 Refinement Tier 1 EF = 0.016  (1.6%)
  3. Plant-measured high case            EF = 0.030  (3.0% — top of full-
                                               scale measurement range)

Why this exists
---------------
The Whitepaper Rev 14 documents that the IPCC 2019 Refinement raised
the wastewater N₂O Tier 1 default by approximately 5× for Australian
utilities transitioning to the new methodology under NGER (and 46× for
NZ, 8× for the UK). A utility committing to a net-zero target on the
legacy default has unhedged step-change exposure from methodology
revision alone — separate from any actual change in plant operation.

Real-world full-scale measurement also documents annual N₂O emissions
up to 7% of influent TN, with microbiome-instability events (e.g.
Uster WWTP, Switzerland, Gruber et al. 2021) producing month-long
episodes up to 30%. The "measured high" scenario captures this
operational tail risk.

This layer is presentation-only: it takes the platform's central
Scope 1 N₂O number (computed by per-technology engines or by
carbon_layer.calculate_carbon) and produces three scaled views plus
two derived risk metrics:

  - methodology_revision_risk = ipcc_2019 − legacy
        the step-change a utility on the legacy default faces when
        their reporting framework migrates to IPCC 2019.

  - microbiome_instability_risk = measured_high − ipcc_2019
        the additional exposure if site-specific N₂O is in the upper
        tail of measured observations.

The layer does not modify any other layer's outputs.

References
----------
  - IPCC (2006) Guidelines for National GHG Inventories, Vol.5 Ch.6
        — wastewater N₂O Tier 1 default 0.005 kg N₂O-N/kg N → ~0.35% TN
  - IPCC (2019) Refinement to the 2006 Guidelines, Vol.5 Ch.6
        Table 6.8A — Tier 1 default 0.016 kg N₂O-N/kg N (1.6%);
        reported range 0.005–0.05.
  - Gruber et al. (2021) N₂O emissions from a full-scale municipal
        WWTP — Uster, Switzerland. Water Research 195, 116963.
        Documents microbiome-instability events with monthly N₂O
        emissions up to ~7% of influent TN, episodic peaks higher.
  - NGER (Australia), DEFRA (UK), and MfE (NZ) methodology updates
        reflecting the IPCC 2019 Refinement.
"""
from __future__ import annotations

from dataclasses import dataclass


# ── Scenario emission factors ────────────────────────────────────────────────
# All expressed on the canonical IPCC basis: kg N₂O-N per kg influent TN.

EF_LEGACY        = 0.0035   # IPCC 2006 / pre-2019 reporting frameworks
EF_IPCC_2019     = 0.016    # IPCC 2019 Refinement Tier 1 — current platform default
EF_MEASURED_HIGH = 0.030    # Top of full-scale observation range
                            # (Uster-class microbiome-instability worst-case)


# ── Result dataclass ─────────────────────────────────────────────────────────

@dataclass
class Scope1ScenarioReport:
    """
    Three-scenario view of the headline Scope 1 N₂O number.

    All values are in tCO₂e/yr. They are derived by scaling the central
    estimate by the ratio of each scenario's EF to the central EF
    used in the underlying calculation.
    """
    # Central inputs echoed for transparency
    central_n2o_tco2e_yr:  float    # the input central number
    ef_central:            float    # the EF used to produce the central number

    # The three scenarios
    legacy:                float    # tCO₂e/yr under EF_LEGACY
    ipcc_2019:             float    # tCO₂e/yr under EF_IPCC_2019
    measured_high:         float    # tCO₂e/yr under EF_MEASURED_HIGH

    # Derived exposure metrics
    methodology_revision_risk_tco2e_yr:  float   # ipcc_2019 − legacy
    microbiome_instability_risk_tco2e_yr: float  # measured_high − ipcc_2019

    # Plain-English framing
    interpretation:        str


# ── Main entry point ─────────────────────────────────────────────────────────

def build_scope1_scenarios(
    n2o_central_tco2e_yr: float,
    ef_central:           float = EF_IPCC_2019,
) -> Scope1ScenarioReport:
    """
    Build the three-scenario view from a central Scope 1 N₂O estimate.

    Parameters
    ----------
    n2o_central_tco2e_yr : float
        The plant's central Scope 1 N₂O emission estimate (tCO₂e/yr),
        as produced by the per-technology engine or carbon_layer.
        Should be the N₂O component only, NOT including CH₄ or Scope 2/3.

    ef_central : float, optional
        The emission factor used to produce n2o_central_tco2e_yr.
        Defaults to EF_IPCC_2019 (0.016) since that is the current
        platform default after PR feature/scope1-methodology-fixes.
        Pass an alternative value if the central estimate was produced
        using a different EF (e.g. AGS at 0.024) and you want the
        methodology-revision view scaled accordingly.

    Returns
    -------
    Scope1ScenarioReport
    """
    if ef_central <= 0:
        # Defensive — avoid division by zero; treat as zero everywhere.
        return Scope1ScenarioReport(
            central_n2o_tco2e_yr = n2o_central_tco2e_yr,
            ef_central           = ef_central,
            legacy               = 0.0,
            ipcc_2019            = 0.0,
            measured_high        = 0.0,
            methodology_revision_risk_tco2e_yr  = 0.0,
            microbiome_instability_risk_tco2e_yr = 0.0,
            interpretation = (
                "Scope 1 scenario layer received a non-positive central EF — "
                "no methodology-revision view computed."
            ),
        )

    legacy        = n2o_central_tco2e_yr * (EF_LEGACY        / ef_central)
    ipcc_2019     = n2o_central_tco2e_yr * (EF_IPCC_2019     / ef_central)
    measured_high = n2o_central_tco2e_yr * (EF_MEASURED_HIGH / ef_central)

    methodology_revision  = ipcc_2019 - legacy
    microbiome_instability = measured_high - ipcc_2019

    # Methodology-revision multiplier — the step-change a legacy utility faces
    revision_multiplier = EF_IPCC_2019 / EF_LEGACY  # ~4.6×

    interpretation = (
        f"Under current IPCC 2019 Tier 1 accounting this plant's Scope 1 N₂O "
        f"is {ipcc_2019:,.0f} tCO₂e/yr. A utility reporting on the legacy "
        f"(pre-2019) default would show {legacy:,.0f} tCO₂e/yr — "
        f"a ~{revision_multiplier:.1f}× understatement that is mechanically "
        f"corrected when reporting frameworks adopt IPCC 2019. Under the "
        f"upper measurement range (microbiome-instability case, EF=3.0% of "
        f"influent TN per Gruber 2021), the same plant would emit "
        f"{measured_high:,.0f} tCO₂e/yr. The gap between current accounting "
        f"and the measured-high case ({microbiome_instability:,.0f} tCO₂e/yr) "
        f"is the operational tail risk that site-specific monitoring is "
        f"needed to quantify."
    )

    return Scope1ScenarioReport(
        central_n2o_tco2e_yr = n2o_central_tco2e_yr,
        ef_central           = ef_central,
        legacy               = round(legacy, 1),
        ipcc_2019            = round(ipcc_2019, 1),
        measured_high        = round(measured_high, 1),
        methodology_revision_risk_tco2e_yr  = round(methodology_revision, 1),
        microbiome_instability_risk_tco2e_yr = round(microbiome_instability, 1),
        interpretation       = interpretation,
    )


# ── Plain-English warning copy for the UI ────────────────────────────────────

WARNING_COPY = (
    "The IPCC 2019 Refinement increased the default Tier 1 N₂O emission "
    "factor by approximately 5× for Australian utilities transitioning to "
    "the new methodology under NGER (and 46× for NZ, 8× for UK utilities). "
    "Real-world full-scale measurements have documented annual emissions up "
    "to 7% of influent TN, with microbiome-instability events producing "
    "month-long episodes up to 30% (Gruber et al. 2021, Uster WWTP, "
    "Switzerland). A utility planning to a 2050 net-zero target on the old "
    "default has unhedged exposure to both methodology revisions and "
    "microbiome events; the table below shows the magnitude of that "
    "exposure for this plant."
)
