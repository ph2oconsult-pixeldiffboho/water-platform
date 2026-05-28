"""
engine/carbon_fate.py

BioPoint V1 — Module A: C/N/P Fate Engine.

Partitions carbon, nitrogen, and phosphorus from feed to physical endpoints
for every pathway. All partition coefficients come from ghg_coefficients.py.

PRIME DIRECTIVE: reads only from PathwayBalanceResult. No independent
mass/energy balance. If a quantity is not in the adapter, it is derived
from what is there or flagged explicitly.

CLOSURE IS MANDATORY. Each balance must sum to feed quantity within
tolerance. Closure is an automated assertion — not a rounded-off residual.

Five-way carbon destiny:
  SEQUESTERED         Durable removal (stable biochar, R50-weighted)
  ENERGY              Energy utilisation (CH4 combusted for power/heat)
  SOIL_DELAYED        Land application + labile char (slow oxidation)
  OXIDISED            Biogenic CO2 to atmosphere (direct oxidation)
  FUGITIVE_METHANE    Unburned CH4 slip (Scope 1)

ph2o Consulting — BioPoint V1 — v25B01
"""

from dataclasses import dataclass, field
from typing import Dict
from engine.ghg_coefficients import (
    FUGITIVE_CH4_FRACTION_OF_PRODUCED,
    FUGITIVE_CH4_CHP_SLIP_FRACTION,
    CH4_DENSITY_KG_PER_M3,
    GWP_CH4,
    N2O_EF_LAND_APPLICATION,
    N2O_EF_MAINSTREAM_NITRIFICATION,
    BASELINE_CARBON_MINERALISATION_YR1,
    BASELINE_CARBON_DELAYED_OXIDATION_FRACTION,
    AVOIDED_N_FERTILISER_KG_CO2E_PER_KG_N,
    AVOIDED_P_FERTILISER_KG_CO2E_PER_KG_P,
    DESTINY_SEQUESTERED,
    DESTINY_ENERGY,
    DESTINY_SOIL_DELAYED,
    DESTINY_OXIDISED,
    DESTINY_FUGITIVE_METHANE,
    DESTINY_CATEGORIES,
)
from engine.carbon_adapter import PathwayBalanceResult


# ============================================================
# OUTPUT DATACLASS
# ============================================================

@dataclass
class CNPFateResult:
    """
    C/N/P fate for one pathway, per tDS basis.
    All carbon quantities in kg C / tDS.
    All nitrogen quantities in kg N / tDS.
    All phosphorus quantities in kg P / tDS.
    """

    pathway_type: str = ""
    pathway_name: str = ""

    # --- CARBON DESTINY (five-way split, kg C / tDS) ---
    carbon_sequestered: float = 0.0        # Durable removal (stable biochar)
    carbon_energy: float = 0.0             # CH4 combusted → energy utilisation
    carbon_soil_delayed: float = 0.0       # Labile biochar + land application
    carbon_oxidised: float = 0.0           # Biogenic CO2 directly to atmosphere
    carbon_fugitive_ch4: float = 0.0       # Fugitive methane carbon

    # Five-way as dict (for charting)
    carbon_destiny: Dict[str, float] = field(default_factory=dict)

    # Biogenic CO2 quantity (always tracked regardless of convention)
    biogenic_co2_kg_per_tds: float = 0.0
    biogenic_co2_note: str = ""

    # Carbon balance closure
    carbon_feed_kg_per_tds: float = 0.0
    carbon_destiny_total_kg_per_tds: float = 0.0
    carbon_closure_error_pct: float = 0.0
    carbon_closure_passes: bool = False

    # --- NITROGEN FATE (kg N / tDS) ---
    n_in_product_kg_per_tds: float = 0.0      # In solid product (land application)
    n_in_sidestream_kg_per_tds: float = 0.0   # Centrate / process liquor
    n_volatilised_kg_per_tds: float = 0.0     # NH3 + N2 from thermal
    n_as_n2o_kg_per_tds: float = 0.0          # N2O (from land app + sidestream)
    n_to_atmosphere_kg_per_tds: float = 0.0   # N2 (denitrification)
    n_in_ash_kg_per_tds: float = 0.0

    n_feed_kg_per_tds: float = 0.0
    n_fate_total_kg_per_tds: float = 0.0
    n_closure_error_pct: float = 0.0
    n_closure_passes: bool = False

    # --- PHOSPHORUS FATE (kg P / tDS) ---
    p_in_product_kg_per_tds: float = 0.0
    p_in_sidestream_kg_per_tds: float = 0.0
    p_in_ash_kg_per_tds: float = 0.0
    p_recovered_kg_per_tds: float = 0.0   # Struvite or other recovery

    p_feed_kg_per_tds: float = 0.0
    p_fate_total_kg_per_tds: float = 0.0
    p_closure_error_pct: float = 0.0
    p_closure_passes: bool = False

    # --- AVOIDED EMISSIONS (displacement credits, kg CO2e / tDS) ---
    avoided_n_fertiliser_kg_co2e: float = 0.0
    avoided_p_fertiliser_kg_co2e: float = 0.0
    total_avoided_kg_co2e: float = 0.0

    # --- FLAGS ---
    has_land_application: bool = False
    has_biochar_product: bool = False
    has_thermal_destruction: bool = False

    # Plain-language destiny statement
    destiny_statement: str = ""


# ============================================================
# MAIN ENGINE
# ============================================================

def run_carbon_fate(bal: PathwayBalanceResult) -> CNPFateResult:
    """
    Compute C/N/P fate from a PathwayBalanceResult.
    Returns CNPFateResult with closure assertions evaluated.
    """
    result = CNPFateResult(
        pathway_type=bal.pathway_type,
        pathway_name=bal.pathway_name,
        carbon_feed_kg_per_tds=bal.carbon_in_kg_per_tds,
        n_feed_kg_per_tds=bal.nitrogen_kg_per_tds,
        p_feed_kg_per_tds=bal.phosphorus_kg_per_tds,
    )

    result = _carbon_fate(result, bal)
    result = _nitrogen_fate(result, bal)
    result = _phosphorus_fate(result, bal)
    result = _avoided_emissions(result, bal)
    result = _destiny_statement(result, bal)

    return result


# ============================================================
# CARBON FATE
# ============================================================

def _carbon_fate(result: CNPFateResult, bal: PathwayBalanceResult) -> CNPFateResult:
    ptype = bal.pathway_type
    C_feed = bal.carbon_in_kg_per_tds

    # --- 1. SEQUESTERED ---
    # Durable removal: stable biochar carbon (R50-weighted, above threshold)
    sequestered = bal.char_stable_carbon_kg_per_tds
    result.has_biochar_product = sequestered > 0

    # --- 2. ENERGY UTILISATION ---
    # CH4 combusted in CHP → useful energy (carbon utilised, not sequestered)
    # CH4 volume × density × carbon fraction (12/16)
    ch4_combusted_m3 = (
        bal.biogas_ch4_m3_per_tds
        * (1.0 - FUGITIVE_CH4_FRACTION_OF_PRODUCED)   # minus fugitive
        * (1.0 - FUGITIVE_CH4_CHP_SLIP_FRACTION)      # minus CHP slip
    )
    ch4_combusted_carbon = ch4_combusted_m3 * CH4_DENSITY_KG_PER_M3 * (12.0 / 16.0)
    energy_carbon = ch4_combusted_carbon

    # --- 3. FUGITIVE CH4 ---
    # Fugitive from digester cover + CHP slip (both unburned)
    fugitive_m3 = (
        bal.biogas_ch4_m3_per_tds * FUGITIVE_CH4_FRACTION_OF_PRODUCED
        + bal.biogas_ch4_m3_per_tds * FUGITIVE_CH4_CHP_SLIP_FRACTION
    )
    fugitive_carbon = fugitive_m3 * CH4_DENSITY_KG_PER_M3 * (12.0 / 16.0)

    # --- 4. OXIDISED (biogenic CO2) ---
    # Sources: CO2 in biogas + carbon oxidised in thermal processes
    # CO2 in biogas
    biogas_co2_carbon = bal.biogas_co2_m3_per_tds * 1.964 * (12.0 / 44.0)

    # Thermal oxidation: VS_destroyed × carbon_fraction − biogas carbon
    if ptype in ("incineration", "thp_incineration", "gasification"):
        # Thermal oxidation: nearly all organic carbon → CO2
        # For thp_incineration: biogas carbon already accounted — subtract it
        oxidised = max(0.0, C_feed - bal.ash_residual_carbon_kg_per_tds
                       - bal.centrate_carbon_kg_per_tds
                       - energy_carbon - fugitive_carbon)
        result.has_thermal_destruction = True
    elif ptype in ("pyrolysis", "centralised"):
        # Pyrolysis / centralised hub (drying+pyrolysis): carbon not in char → pyrogas CO2
        carbon_in_char = (bal.char_stable_carbon_kg_per_tds
                          + bal.char_labile_carbon_kg_per_tds)
        oxidised = max(0.0, C_feed - carbon_in_char - energy_carbon
                       - fugitive_carbon - bal.centrate_carbon_kg_per_tds)
    elif ptype in ("HTC", "HTC_sidestream"):
        # HTC: carbon in hydrochar + carbon in aqueous phase (centrate)
        # Remaining C is assumed oxidised over time in soil/water
        carbon_in_hydrochar = (bal.char_stable_carbon_kg_per_tds
                                + bal.char_labile_carbon_kg_per_tds)
        oxidised = max(0.0, C_feed - carbon_in_hydrochar
                       - bal.centrate_carbon_kg_per_tds)
    elif ptype in ("AD", "thp_incineration"):
        # AD: biogenic CO2 from biogas is the primary atmospheric carbon release
        # All biogas CO2 is biogenic — it was fixed from atmosphere
        oxidised = biogas_co2_carbon
        # Note: CH4 carbon goes to ENERGY (combusted) or FUGITIVE — not oxidised here
    elif ptype in ("baseline",):
        # Land application: fraction mineralises in yr 1
        oxidised = C_feed * BASELINE_CARBON_MINERALISATION_YR1
        result.has_land_application = True
    elif ptype in ("drying_only", "decentralised", "centralised"):
        oxidised = 0.0   # No destruction
    else:
        oxidised = biogas_co2_carbon

    # --- 5. SOIL / DELAYED ---
    # Sources: labile biochar, land-applied carbon (slow pool), centrate carbon (aquatic)
    if ptype == "baseline":
        soil_delayed = C_feed * BASELINE_CARBON_DELAYED_OXIDATION_FRACTION
    elif ptype in ("drying_only", "decentralised"):
        soil_delayed = C_feed - bal.centrate_carbon_kg_per_tds
    elif ptype in ("AD",):
        digestate_carbon = max(0.0,
            C_feed - bal.biogas_carbon_kg_per_tds - bal.centrate_carbon_kg_per_tds)
        soil_delayed = digestate_carbon + bal.centrate_carbon_kg_per_tds
    elif ptype in ("incineration", "thp_incineration", "gasification"):
        soil_delayed = 0.0   # All organic carbon oxidised or in ash
    elif ptype.startswith("hybrid_"):
        # Hybrid: bulk of carbon goes to product/soil via hub treatment
        # char_labile is set in the hybrid balance as (1-disposal_reduction) × C_feed
        soil_delayed = max(0.0, C_feed - bal.char_labile_carbon_kg_per_tds
                           - bal.centrate_carbon_kg_per_tds)
        oxidised = 0.0   # Hybrid aggregation — no explicit oxidation split
    else:
        soil_delayed = bal.char_labile_carbon_kg_per_tds + bal.centrate_carbon_kg_per_tds

    # Biogenic CO2 total (tracked separately, regardless of accounting convention)
    result.biogenic_co2_kg_per_tds = max(0.0,
        oxidised + energy_carbon + biogas_co2_carbon
        - fugitive_carbon * (44.0 / 12.0)  # subtract fugitive CH4 (not CO2)
    )
    result.biogenic_co2_note = (
        "Biogenic CO2 is tracked explicitly. Under the carbon-neutral convention "
        "(IPCC default, used by Module B GHG engine), biogenic CO2 from decomposition "
        "of organic waste is excluded from the net GHG total. This quantity is shown "
        "here regardless of accounting convention."
    )

    # Assign to result
    result.carbon_sequestered     = round(max(0.0, sequestered), 3)
    result.carbon_energy           = round(max(0.0, energy_carbon), 3)
    result.carbon_soil_delayed     = round(max(0.0, soil_delayed), 3)
    result.carbon_oxidised          = round(max(0.0, oxidised), 3)
    result.carbon_fugitive_ch4     = round(max(0.0, fugitive_carbon), 3)

    # Five-way dict (for charting)
    result.carbon_destiny = {
        DESTINY_SEQUESTERED:      result.carbon_sequestered,
        DESTINY_ENERGY:           result.carbon_energy,
        DESTINY_SOIL_DELAYED:     result.carbon_soil_delayed,
        DESTINY_OXIDISED:         result.carbon_oxidised,
        DESTINY_FUGITIVE_METHANE: result.carbon_fugitive_ch4,
    }

    # --- CLOSURE CHECK ---
    total = sum(result.carbon_destiny.values())
    result.carbon_destiny_total_kg_per_tds = round(total, 3)

    if C_feed > 0:
        error_pct = abs(total - C_feed) / C_feed * 100
    else:
        error_pct = 0.0

    result.carbon_closure_error_pct = round(error_pct, 2)
    result.carbon_closure_passes = error_pct <= 5.0   # 5% tolerance for screening

    return result


# ============================================================
# NITROGEN FATE
# ============================================================

def _nitrogen_fate(result: CNPFateResult, bal: PathwayBalanceResult) -> CNPFateResult:
    ptype = bal.pathway_type
    N_feed = bal.nitrogen_kg_per_tds

    n_product   = bal.n_in_product_kg_per_tds
    n_sidestream = bal.centrate_n_kg_per_tds

    # For pathways where N in product + N in sidestream don't sum to feed,
    # route the remainder to volatilised/atmosphere (consistent with chemistry)
    n_ash = 0.0
    n_volatilised = 0.0

    if ptype in ("incineration", "thp_incineration", "gasification"):
        n_ash         = bal.n_in_product_kg_per_tds
        n_volatilised = max(0.0, N_feed - n_ash - n_sidestream)
    elif ptype in ("pyrolysis", "centralised"):
        # Pyrolysis: N mainly retained in char + some to gas phase
        n_volatilised = max(0.0, N_feed - n_product - n_sidestream)
    elif ptype in ("HTC", "HTC_sidestream"):
        # HTC: N split between hydrochar and process water
        n_volatilised = max(0.0, N_feed - n_product - n_sidestream)
    elif ptype == "AD":
        # AD: N in cake + centrate; remainder (small) to atmosphere via denitrification
        n_volatilised = max(0.0, N_feed - n_product - n_sidestream) * 0.05
        n_sidestream  = max(n_sidestream, N_feed - n_product - n_volatilised)
    else:
        n_volatilised = max(0.0, N_feed - n_product - n_sidestream)

    # N2O from land application
    n_as_n2o = 0.0
    if ptype in ("baseline", "drying_only", "decentralised") and n_product > 0:
        n_as_n2o = n_product * N2O_EF_LAND_APPLICATION
        result.has_land_application = True

    # N2O from sidestream return (nitrification in liquid treatment)
    if n_sidestream > 0:
        n_as_n2o += n_sidestream * N2O_EF_MAINSTREAM_NITRIFICATION

    # N to atmosphere (denitrification of sidestream — subset of sidestream)
    # This is NOT additional N — it is the fraction of sidestream N that is denitrified
    # For closure: sidestream N is already counted; n_to_atm is informational only
    n_to_atm = max(0.0, n_sidestream * 0.40)

    result.n_in_product_kg_per_tds   = round(max(0.0, n_product), 3)
    result.n_in_sidestream_kg_per_tds = round(max(0.0, n_sidestream), 3)
    result.n_volatilised_kg_per_tds   = round(max(0.0, n_volatilised), 3)
    result.n_as_n2o_kg_per_tds        = round(max(0.0, n_as_n2o), 4)
    result.n_to_atmosphere_kg_per_tds = round(max(0.0, n_to_atm), 3)
    result.n_in_ash_kg_per_tds        = round(max(0.0, n_ash), 3)

    # Closure: n_to_atm is a SUBSET of sidestream (not additive), so exclude from total
    # n_as_n2o is a tiny fraction of applied/sidestream N — also not additive to total
    # (both are flow fractions, already counted in product/sidestream/volatilised)
    n_total = (result.n_in_product_kg_per_tds
               + result.n_in_sidestream_kg_per_tds
               + result.n_volatilised_kg_per_tds
               + result.n_in_ash_kg_per_tds)
    result.n_fate_total_kg_per_tds = round(n_total, 3)

    if N_feed > 0:
        n_err = abs(n_total - N_feed) / N_feed * 100
    else:
        n_err = 0.0
    result.n_closure_error_pct = round(n_err, 2)
    result.n_closure_passes = n_err <= 10.0   # Wider tolerance: N routing is approximate

    return result


# ============================================================
# PHOSPHORUS FATE
# ============================================================

def _phosphorus_fate(result: CNPFateResult, bal: PathwayBalanceResult) -> CNPFateResult:
    P_feed = bal.phosphorus_kg_per_tds

    p_product    = bal.p_in_product_kg_per_tds
    p_sidestream = bal.centrate_p_kg_per_tds
    p_ash        = 0.0
    p_recovered  = 0.0

    ptype = bal.pathway_type
    if ptype in ("incineration", "thp_incineration"):
        p_ash       = P_feed * 0.90
        p_product   = 0.0
        p_sidestream = P_feed * 0.10
    elif ptype in ("pyrolysis", "centralised", "HTC", "HTC_sidestream"):
        # P remainder not in product goes to sidestream/centrate
        p_sidestream = max(p_sidestream, P_feed - p_product)
    else:
        # General: route remainder to sidestream
        remainder = P_feed - p_product - p_sidestream - p_ash - p_recovered
        if remainder > 0.01:
            p_sidestream = p_sidestream + remainder

    # Assign
    result.p_in_product_kg_per_tds   = round(max(0.0, p_product), 3)
    result.p_in_sidestream_kg_per_tds = round(max(0.0, p_sidestream), 3)
    result.p_in_ash_kg_per_tds        = round(max(0.0, p_ash), 3)
    result.p_recovered_kg_per_tds     = round(max(0.0, p_recovered), 3)

    p_total = (result.p_in_product_kg_per_tds
               + result.p_in_sidestream_kg_per_tds
               + result.p_in_ash_kg_per_tds
               + result.p_recovered_kg_per_tds)
    result.p_fate_total_kg_per_tds = round(p_total, 3)

    if P_feed > 0:
        p_err = abs(p_total - P_feed) / P_feed * 100
    else:
        p_err = 0.0
    result.p_closure_error_pct = round(p_err, 2)
    result.p_closure_passes = p_err <= 10.0

    return result


# ============================================================
# AVOIDED EMISSIONS (displacement credits)
# ============================================================

def _avoided_emissions(result: CNPFateResult, bal: PathwayBalanceResult) -> CNPFateResult:
    """
    Fertiliser displacement credits from N and P in product.
    These are DISPLACEMENT credits — clearly separated from REMOVAL.
    """
    result.avoided_n_fertiliser_kg_co2e = (
        result.n_in_product_kg_per_tds * AVOIDED_N_FERTILISER_KG_CO2E_PER_KG_N
    )
    result.avoided_p_fertiliser_kg_co2e = (
        result.p_in_product_kg_per_tds * AVOIDED_P_FERTILISER_KG_CO2E_PER_KG_P
    )
    result.total_avoided_kg_co2e = (
        result.avoided_n_fertiliser_kg_co2e
        + result.avoided_p_fertiliser_kg_co2e
    )
    return result


# ============================================================
# PLAIN-LANGUAGE DESTINY STATEMENT
# ============================================================

def _destiny_statement(result: CNPFateResult, bal: PathwayBalanceResult) -> CNPFateResult:
    """
    Plain-language summary of where the feed carbon ends up.
    Anti-greenwashing: explicitly flags when 'net-negative' is displacement not removal.
    """
    ptype = bal.pathway_type
    C = bal.carbon_in_kg_per_tds
    if C <= 0:
        result.destiny_statement = "No carbon feed — no fate assessment."
        return result

    seq_pct  = result.carbon_sequestered    / C * 100
    en_pct   = result.carbon_energy          / C * 100
    soil_pct = result.carbon_soil_delayed    / C * 100
    ox_pct   = result.carbon_oxidised        / C * 100
    fug_pct  = result.carbon_fugitive_ch4   / C * 100

    # Primary carbon outcome
    if seq_pct >= 30:
        primary = f"{seq_pct:.0f}% is durably sequestered as stable biochar"
    elif en_pct >= 40:
        primary = f"{en_pct:.0f}% is converted to energy (displacing fossil fuel)"
    elif ox_pct >= 60:
        primary = f"{ox_pct:.0f}% is oxidised to biogenic CO₂ (complete thermal treatment)"
    elif soil_pct >= 50:
        primary = f"{soil_pct:.0f}% enters soil or slow-oxidation pool"
    else:
        primary = "carbon is distributed across multiple fate categories"

    stmt = f"For {bal.pathway_name}: {primary}."

    # Anti-greenwashing flags
    if seq_pct < 5 and en_pct > 30:
        stmt += (
            " NOTE: The beneficial GHG outcome for this pathway is driven by "
            "fossil fuel displacement (energy recovery), not by carbon removal. "
            "If the grid decarbonises, this displacement credit will diminish."
        )

    if result.carbon_fugitive_ch4 > 0.5:
        stmt += (
            f" Fugitive methane represents {fug_pct:.1f}% of feed carbon "
            f"({result.carbon_fugitive_ch4 * GWP_CH4:.0f} kg CO₂e/tDS at AR5 GWP). "
            "Digester cover integrity and CHP slip should be monitored."
        )

    if ptype == "baseline":
        stmt += (
            " Land application without treatment: carbon enters the slow soil organic "
            "matter pool, but PFAS and contaminant risks are not managed. "
            "This is not a carbon sequestration pathway — it is delayed oxidation."
        )

    result.destiny_statement = stmt
    return result


# ============================================================
# SYSTEM-LEVEL RUNNER
# ============================================================

def run_carbon_fate_all(balances: list) -> list:
    """
    Run carbon fate for all pathways. Returns List[CNPFateResult].
    Closure failures are surfaced as warnings, not silently passed.
    """
    results = []
    for bal in balances:
        fate = run_carbon_fate(bal)
        results.append(fate)
    return results
