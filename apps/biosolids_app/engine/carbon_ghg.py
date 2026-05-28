"""
engine/carbon_ghg.py

BioPoint V1 — Module B: GHG Engine.

Produces a full Scope 1/2/3 greenhouse-gas inventory per pathway.
Reads ONLY from CNPFateResult + PathwayBalanceResult + GHGInputs.

Conventions (must be shown in UI — never silent):
  - GWP basis: AR5, 100-year (CH4=28, N2O=265)
  - Biogenic CO2: EXCLUDED from net GHG total under carbon-neutral convention
    (IPCC default for organic waste). Tracked as a separate line always.
  - Removal ≠ displacement. Sequestration and fossil displacement are
    reported on separate lines and NEVER netted against each other.
  - Net GHG = Scope1 + Scope2 + Scope3 - Displacement credits
    (Removal credits are a further separate line below net GHG)

ph2o Consulting — BioPoint V1 — v25B01
"""

from dataclasses import dataclass, field
from typing import Literal, Optional
from engine.ghg_coefficients import (
    GWP_CH4,
    GWP_N2O,
    N2O_N_TO_N2O_MW_RATIO,
    CH4_DENSITY_KG_PER_M3,
    NATURAL_GAS_EMISSION_KG_CO2E_PER_GJ,
    NATURAL_GAS_UPSTREAM_KG_CO2E_PER_GJ,
    TRANSPORT_EMISSION_FACTOR_KG_CO2E_PER_T_KM,
    GRID_INTENSITY_DEFAULT_KG_CO2E_PER_KWH,
    GRID_INTENSITY_2035_KG_CO2E_PER_KWH,
    GRID_INTENSITY_NET_ZERO_KG_CO2E_PER_KWH,
    GRID_INTENSITY_BY_STATE,
    AVOIDED_N_FERTILISER_KG_CO2E_PER_KG_N,
    AVOIDED_P_FERTILISER_KG_CO2E_PER_KG_P,
    FUGITIVE_CH4_FRACTION_OF_PRODUCED,
    FUGITIVE_CH4_CHP_SLIP_FRACTION,
    N2O_EF_LAND_APPLICATION,
    N2O_EF_SIDESTREAM_TREATMENT,
    N2O_EF_MAINSTREAM_NITRIFICATION,
)
from engine.carbon_adapter import PathwayBalanceResult
from engine.carbon_fate import CNPFateResult


# ============================================================
# INPUTS DATACLASS
# ============================================================

BiogenicConvention = Literal["carbon_neutral", "count_all"]


@dataclass
class GHGInputs:
    """
    Scenario parameters for the GHG engine.
    Separate from FeedstockInputsV2 / AssetInputs — these are scenario choices,
    not plant characteristics.
    """

    # Grid carbon intensity — state selectable
    grid_state: str = "NEM_average"   # Key into GRID_INTENSITY_BY_STATE or "Custom"
    grid_intensity_current_kg_per_kwh: float = GRID_INTENSITY_DEFAULT_KG_CO2E_PER_KWH
    grid_intensity_2035_kg_per_kwh: float = GRID_INTENSITY_2035_KG_CO2E_PER_KWH
    grid_intensity_net_zero_kg_per_kwh: float = GRID_INTENSITY_NET_ZERO_KG_CO2E_PER_KWH

    # Biogenic CO2 accounting convention
    # "carbon_neutral" (IPCC default): biogenic CO2 excluded from net GHG
    # "count_all": all CO2 counted (conservative / non-IPCC approach)
    biogenic_co2_convention: BiogenicConvention = "carbon_neutral"

    # GWP basis
    gwp_ch4: float = GWP_CH4
    gwp_n2o: float = GWP_N2O

    # Polymer dose (kg polymer / tDS) — for dewatering Scope 3
    polymer_dose_kg_per_tds: float = 5.0

    # Lime dose (kg lime / tDS) — for biosolids conditioning
    lime_dose_kg_per_tds: float = 0.0


# ============================================================
# OUTPUT DATACLASS
# ============================================================

@dataclass
class GHGLineItem:
    """One line in the GHG inventory."""
    label: str = ""
    scope: str = ""           # "Scope 1" / "Scope 2" / "Scope 3" / "Biogenic" / "Credit"
    kg_co2e_per_tds: float = 0.0
    is_credit: bool = False   # True for avoided/removal credits (negative contribution)
    note: str = ""


@dataclass
class GHGScenario:
    """GHG result at one grid intensity scenario."""
    scenario_name: str = ""
    grid_intensity: float = 0.0

    scope1_kg_co2e: float = 0.0
    scope2_kg_co2e: float = 0.0
    scope3_kg_co2e: float = 0.0
    biogenic_co2_kg_co2e: float = 0.0   # Always tracked; convention determines inclusion

    gross_ghg_kg_co2e: float = 0.0      # Scope 1+2+3 (excl biogenic under carbon_neutral)

    # Displacement credits (fossil energy, fertiliser) — SEPARATE from removal
    displacement_credits_kg_co2e: float = 0.0

    # Removal credits (durable sequestration) — SEPARATE from displacement
    removal_credits_kg_co2e: float = 0.0

    # Net GHG = gross - displacement credits
    # (removal credits shown separately — never netted into gross)
    net_ghg_kg_co2e: float = 0.0

    # Full net including removal (for transparency only — labelled explicitly)
    net_ghg_including_removal_kg_co2e: float = 0.0

    line_items: list = field(default_factory=list)  # List[GHGLineItem]


@dataclass
class GHGResult:
    """
    Full GHG result for one pathway across three grid scenarios.
    """
    pathway_type: str = ""
    pathway_name: str = ""

    # Three scenarios
    current: GHGScenario = field(default_factory=GHGScenario)
    scenario_2035: GHGScenario = field(default_factory=GHGScenario)
    net_zero: GHGScenario = field(default_factory=GHGScenario)

    # Conventions used (must be displayed in UI)
    biogenic_convention: str = ""
    gwp_basis: str = "AR5, 100-year (CH4=28, N2O=265)"
    grid_state: str = ""

    # Uncertainty band (screening-grade: ±30% of net GHG)
    uncertainty_pct: float = 30.0

    # Anti-greenwashing flags
    net_negative_is_displacement: bool = False   # True when net<0 driven by displacement not removal
    grid_dependent: bool = False                  # True when Scope 2 is dominant


# ============================================================
# MAIN ENGINE
# ============================================================

def run_ghg(
    bal: PathwayBalanceResult,
    fate: CNPFateResult,
    ghg_inputs: GHGInputs,
) -> GHGResult:
    """
    Compute full GHG inventory for one pathway across three grid scenarios.
    """
    result = GHGResult(
        pathway_type=bal.pathway_type,
        pathway_name=bal.pathway_name,
        biogenic_convention=ghg_inputs.biogenic_co2_convention,
        grid_state=ghg_inputs.grid_state,
    )

    result.current      = _compute_scenario(
        bal, fate, ghg_inputs,
        "Current grid",
        ghg_inputs.grid_intensity_current_kg_per_kwh,
    )
    result.scenario_2035 = _compute_scenario(
        bal, fate, ghg_inputs,
        "2035 grid",
        ghg_inputs.grid_intensity_2035_kg_per_kwh,
    )
    result.net_zero     = _compute_scenario(
        bal, fate, ghg_inputs,
        "Net-zero grid",
        ghg_inputs.grid_intensity_net_zero_kg_per_kwh,
    )

    # Anti-greenwashing flags
    if result.current.net_ghg_kg_co2e < 0:
        if abs(result.current.displacement_credits_kg_co2e) > abs(result.current.removal_credits_kg_co2e):
            result.net_negative_is_displacement = True

    scope2_abs = abs(result.current.scope2_kg_co2e)
    gross_abs  = abs(result.current.gross_ghg_kg_co2e) or 1.0
    if scope2_abs / gross_abs > 0.40:
        result.grid_dependent = True

    return result


def _compute_scenario(
    bal: PathwayBalanceResult,
    fate: CNPFateResult,
    ghg: GHGInputs,
    scenario_name: str,
    grid_intensity: float,
) -> GHGScenario:
    """Compute GHG inventory at one grid intensity."""
    s = GHGScenario(scenario_name=scenario_name, grid_intensity=grid_intensity)
    lines = []
    ptype = bal.pathway_type

    # ── SCOPE 1: Direct emissions ─────────────────────────────────────────

    # 1a. Fugitive CH4 from digester
    fugitive_ch4_m3 = bal.biogas_ch4_m3_per_tds * FUGITIVE_CH4_FRACTION_OF_PRODUCED
    fugitive_ch4_kg = fugitive_ch4_m3 * CH4_DENSITY_KG_PER_M3
    s1_fugitive_ch4 = fugitive_ch4_kg * ghg.gwp_ch4
    if s1_fugitive_ch4 > 0:
        lines.append(GHGLineItem(
            label="Fugitive CH₄ (digester cover)",
            scope="Scope 1",
            kg_co2e_per_tds=round(s1_fugitive_ch4, 2),
            note=f"{fugitive_ch4_kg*1000:.1f} g CH4/tDS × GWP {ghg.gwp_ch4}"
        ))

    # 1b. CHP methane slip
    chp_slip_m3 = bal.biogas_ch4_m3_per_tds * FUGITIVE_CH4_CHP_SLIP_FRACTION
    chp_slip_kg  = chp_slip_m3 * CH4_DENSITY_KG_PER_M3
    s1_chp_slip  = chp_slip_kg * ghg.gwp_ch4
    if s1_chp_slip > 0:
        lines.append(GHGLineItem(
            label="CHP methane slip",
            scope="Scope 1",
            kg_co2e_per_tds=round(s1_chp_slip, 2),
        ))

    # 1c. N2O from land application
    s1_n2o_land = 0.0
    if fate.has_land_application and fate.n_in_product_kg_per_tds > 0:
        n2o_n_kg = fate.n_in_product_kg_per_tds * N2O_EF_LAND_APPLICATION
        n2o_kg   = n2o_n_kg * N2O_N_TO_N2O_MW_RATIO
        s1_n2o_land = n2o_kg * ghg.gwp_n2o
        lines.append(GHGLineItem(
            label="N₂O — land application (direct)",
            scope="Scope 1",
            kg_co2e_per_tds=round(s1_n2o_land, 2),
            note=f"IPCC Tier 1: {N2O_EF_LAND_APPLICATION*100:.0f}% of applied N as N2O-N"
        ))

    # 1d. N2O from sidestream treatment
    s1_n2o_ss = 0.0
    if fate.n_in_sidestream_kg_per_tds > 0:
        n2o_n_kg  = fate.n_in_sidestream_kg_per_tds * N2O_EF_SIDESTREAM_TREATMENT
        n2o_kg    = n2o_n_kg * N2O_N_TO_N2O_MW_RATIO
        s1_n2o_ss = n2o_kg * ghg.gwp_n2o
        lines.append(GHGLineItem(
            label="N₂O — sidestream / mainstream nitrification",
            scope="Scope 1",
            kg_co2e_per_tds=round(s1_n2o_ss, 2),
        ))

    # 1e. Fossil fuel combustion (drying)
    s1_fossil = bal.fossil_fuel_gj_per_tds * NATURAL_GAS_EMISSION_KG_CO2E_PER_GJ
    if s1_fossil > 0:
        lines.append(GHGLineItem(
            label="Fossil fuel combustion (drying — Scope 1)",
            scope="Scope 1",
            kg_co2e_per_tds=round(s1_fossil, 2),
            note=f"{bal.fossil_fuel_gj_per_tds:.3f} GJ/tDS × {NATURAL_GAS_EMISSION_KG_CO2E_PER_GJ} kgCO2e/GJ"
        ))

    # 1f. Biogenic CO2 (tracked always; excluded from net under carbon_neutral)
    biogenic_co2_kg = fate.biogenic_co2_kg_per_tds * (44.0 / 12.0)   # kgC → kgCO2
    biogenic_co2e   = biogenic_co2_kg   # CO2 GWP = 1
    s.biogenic_co2_kg_co2e = round(biogenic_co2e, 2)
    lines.append(GHGLineItem(
        label="Biogenic CO₂ (tracked separately — see convention note)",
        scope="Biogenic",
        kg_co2e_per_tds=round(biogenic_co2e, 2),
        note=fate.biogenic_co2_note[:120],
    ))

    s.scope1_kg_co2e = round(
        s1_fugitive_ch4 + s1_chp_slip + s1_n2o_land + s1_n2o_ss + s1_fossil, 2
    )
    # Biogenic excluded from scope1 under carbon_neutral (it is a separate line)
    if ghg.biogenic_co2_convention == "count_all":
        s.scope1_kg_co2e += round(biogenic_co2e, 2)

    # ── SCOPE 2: Imported grid electricity ───────────────────────────────

    # Net electricity: negative means import (demand), positive means export
    net_kwh = bal.net_electricity_kwh_per_tds
    s2_electricity = 0.0
    if net_kwh < 0:
        # Importing electricity → Scope 2 emission
        s2_electricity = abs(net_kwh) * grid_intensity
        lines.append(GHGLineItem(
            label=f"Grid electricity import ({scenario_name})",
            scope="Scope 2",
            kg_co2e_per_tds=round(s2_electricity, 2),
            note=f"{abs(net_kwh):.1f} kWh/tDS × {grid_intensity:.3f} kgCO2e/kWh"
        ))

    s.scope2_kg_co2e = round(s2_electricity, 2)

    # ── SCOPE 3: Upstream and transport ──────────────────────────────────

    # 3a. Transport emissions (feed + product haul)
    s3_transport = bal.transport_t_km_per_tds * TRANSPORT_EMISSION_FACTOR_KG_CO2E_PER_T_KM
    if s3_transport > 0:
        lines.append(GHGLineItem(
            label="Transport (feed + product haul)",
            scope="Scope 3",
            kg_co2e_per_tds=round(s3_transport, 3),
            note=f"{bal.transport_t_km_per_tds:.2f} t·km/tDS × {TRANSPORT_EMISSION_FACTOR_KG_CO2E_PER_T_KM} kgCO2e/t·km"
        ))

    # 3b. Upstream fossil fuel (drying)
    s3_fuel_upstream = bal.fossil_fuel_gj_per_tds * NATURAL_GAS_UPSTREAM_KG_CO2E_PER_GJ
    if s3_fuel_upstream > 0:
        lines.append(GHGLineItem(
            label="Upstream fossil fuel (well-to-gate)",
            scope="Scope 3",
            kg_co2e_per_tds=round(s3_fuel_upstream, 3),
        ))

    s.scope3_kg_co2e = round(s3_transport + s3_fuel_upstream, 2)

    # ── DISPLACEMENT CREDITS (fossil energy + fertiliser) ────────────────
    # SEPARATE from removal. Labelled explicitly.

    # Avoided grid electricity (net export)
    avoided_electricity = 0.0
    if net_kwh > 0:
        avoided_electricity = net_kwh * grid_intensity
        lines.append(GHGLineItem(
            label=f"Avoided grid electricity (CHP export) [{scenario_name}]",
            scope="Credit",
            kg_co2e_per_tds=round(-avoided_electricity, 2),
            is_credit=True,
            note="DISPLACEMENT credit — not removal. Value diminishes as grid decarbonises."
        ))

    # Avoided fertiliser (N and P in product)
    avoided_n_fert = fate.avoided_n_fertiliser_kg_co2e
    avoided_p_fert = fate.avoided_p_fertiliser_kg_co2e
    if avoided_n_fert > 0:
        lines.append(GHGLineItem(
            label="Avoided N fertiliser (product nutrient value)",
            scope="Credit",
            kg_co2e_per_tds=round(-avoided_n_fert, 2),
            is_credit=True,
            note="DISPLACEMENT credit — not removal."
        ))
    if avoided_p_fert > 0:
        lines.append(GHGLineItem(
            label="Avoided P fertiliser (product nutrient value)",
            scope="Credit",
            kg_co2e_per_tds=round(-avoided_p_fert, 2),
            is_credit=True,
        ))

    s.displacement_credits_kg_co2e = round(
        avoided_electricity + avoided_n_fert + avoided_p_fert, 2
    )

    # ── REMOVAL CREDITS (durable sequestration) ──────────────────────────
    # SEPARATE from displacement. Never netted with displacement.

    removal_kg_co2e = fate.carbon_sequestered * (44.0 / 12.0)   # kgC → kgCO2e
    if removal_kg_co2e > 0:
        lines.append(GHGLineItem(
            label="Carbon removal (stable biochar sequestration)",
            scope="Credit",
            kg_co2e_per_tds=round(-removal_kg_co2e, 2),
            is_credit=True,
            note="REMOVAL credit (durable). Separate from displacement. R50-weighted."
        ))

    s.removal_credits_kg_co2e = round(removal_kg_co2e, 2)

    # ── TOTALS ────────────────────────────────────────────────────────────

    s.gross_ghg_kg_co2e = round(s.scope1_kg_co2e + s.scope2_kg_co2e + s.scope3_kg_co2e, 2)

    # Net GHG = gross - displacement (removal shown separately)
    s.net_ghg_kg_co2e = round(
        s.gross_ghg_kg_co2e - s.displacement_credits_kg_co2e, 2
    )

    # Full net including removal (labelled to prevent misreading)
    s.net_ghg_including_removal_kg_co2e = round(
        s.net_ghg_kg_co2e - s.removal_credits_kg_co2e, 2
    )

    s.line_items = lines
    return s


# ============================================================
# SYSTEM-LEVEL RUNNER
# ============================================================

def run_ghg_all(
    balances: list,
    fates: list,
    ghg_inputs: GHGInputs,
) -> list:
    """
    Run GHG inventory for all pathways.
    Returns List[GHGResult].
    """
    results = []
    for bal, fate in zip(balances, fates):
        ghg_result = run_ghg(bal, fate, ghg_inputs)
        results.append(ghg_result)
    return results


# ============================================================
# CONVENIENCE: DEFAULT GHG INPUTS FROM BIOPOINT ASSET INPUTS
# ============================================================

def ghg_inputs_from_assets(assets, strategic=None) -> GHGInputs:
    """
    Build GHGInputs from existing BioPoint asset/strategic inputs.
    Provides sensible defaults when GHG-specific inputs are not set.
    """
    # Grid intensity from electricity price proxy (rough)
    # Better: let UI set grid_state directly
    elec_price = getattr(assets, "local_power_price_per_kwh", 0.18)

    # Carbon credit value in strategic inputs implies a carbon price context
    carbon_price = getattr(strategic, "carbon_credit_value_per_tco2e", 50.0) \
        if strategic else 50.0

    return GHGInputs(
        grid_state="NEM_average",
        grid_intensity_current_kg_per_kwh=GRID_INTENSITY_DEFAULT_KG_CO2E_PER_KWH,
        grid_intensity_2035_kg_per_kwh=GRID_INTENSITY_2035_KG_CO2E_PER_KWH,
        grid_intensity_net_zero_kg_per_kwh=GRID_INTENSITY_NET_ZERO_KG_CO2E_PER_KWH,
        biogenic_co2_convention="carbon_neutral",
    )
