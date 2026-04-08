"""
BioPoint V1 — Regional Hybrid System Engine.
Models multi-site biosolids systems with partial centralisation.

Hybrid systems sit between full centralisation (single hub) and full
decentralisation (site-based treatment). The engine:

  1. Takes a list of Site objects (volume, DS%, location, infrastructure)
  2. Applies a SiteSelectionAlgorithm to identify optimal hub candidates
  3. Generates HybridConfiguration objects: hub sites + satellite sites
  4. For each configuration calculates:
       - Mass flows between sites and hub
       - Transport distances and costs
       - Hub capacity requirements
       - CAPEX: hub investment vs distributed
       - Disposal volume and cost reduction
       - Aggregated CHP and energy integration potential
       - Mainstream coupling load at hub site
  5. Ranks configurations and compares to full centralised / full decentralised

The engine does not require known GPS coordinates — it works from relative
distance estimates and volume fractions.

ph2o Consulting — BioPoint V1
"""

from dataclasses import dataclass, field
from typing import Optional
import math


# ---------------------------------------------------------------------------
# CONSTANTS
# ---------------------------------------------------------------------------

# Economy of scale for hub CAPEX (0.6 rule)
HUB_CAPEX_SCALE_EXPONENT = 0.65
HUB_CAPEX_REFERENCE_TDS_D = 5.0     # Calibration reference

# Transport cost structure
TRANSPORT_COST_PER_TONNE_KM = 0.25  # Default — overridden by inputs

# Hub treatment technology CAPEX benchmarks ($/tDS/d capacity at reference scale)
# Scaled using HUB_CAPEX_SCALE_EXPONENT
HUB_CAPEX_M_AT_REF = {
    "HTC":             7.0,
    "HTC_sidestream":  10.5,
    "incineration":    20.0,
    "pyrolysis":       8.0,
    "AD":              5.0,
    "drying_only":     3.5,
}

# Satellite treatment CAPEX (typically AD optimisation + dewatering)
SATELLITE_AD_CAPEX_M_AT_REF = 3.0   # Per satellite site, at reference scale


# ---------------------------------------------------------------------------
# INPUT DATACLASSES
# ---------------------------------------------------------------------------

@dataclass
class SiteInput:
    """
    One WWTP site in the regional system.
    Distance matrix is implicit — inter-site distances given in km.
    """
    site_id: str
    name: str
    dry_solids_tpd: float           # DS production
    dewatered_ds_pct: float         # Dewatered cake DS%
    has_ad: bool = False            # Existing AD
    has_chp: bool = False
    has_dryer: bool = False
    distance_to_hub_km: float = 0.0  # Populated by site selection algorithm
    is_hub_candidate: bool = True    # Can this site host a hub?

    # Derived
    wet_sludge_tpd: float = 0.0
    fraction_of_system_ds: float = 0.0

    def resolve(self, system_ds_tpd: float):
        self.wet_sludge_tpd = self.dry_solids_tpd / (self.dewatered_ds_pct / 100.0)
        self.fraction_of_system_ds = self.dry_solids_tpd / system_ds_tpd if system_ds_tpd > 0 else 0


@dataclass
class HybridConfiguration:
    """
    One hybrid system configuration: hub sites + satellite sites.
    """
    config_id: str = ""
    config_name: str = ""
    description: str = ""

    hub_treatment: str = ""          # Treatment technology at hub
    hub_sites: list = field(default_factory=list)     # List[SiteInput]
    satellite_sites: list = field(default_factory=list)

    # Capacity
    hub_ds_tpd: float = 0.0          # DS arriving at hub per day
    hub_wet_tpd: float = 0.0         # Wet tonnes arriving at hub
    satellite_ds_tpd: float = 0.0    # DS treated locally at satellites
    satellite_wet_tpd: float = 0.0

    # Mass flows
    feed_transport_t_d: float = 0.0   # Wet tonnes moved to hub per day
    feed_transport_km: float = 0.0    # Weighted average haul to hub (km)
    feed_transport_t_km_yr: float = 0.0
    feed_transport_cost_yr: float = 0.0

    product_transport_t_d: float = 0.0   # Residual product from hub
    product_transport_km: float = 0.0
    product_transport_cost_yr: float = 0.0

    satellite_disposal_t_d: float = 0.0   # Residual from satellites
    satellite_disposal_cost_yr: float = 0.0

    total_disposal_t_d: float = 0.0
    total_disposal_reduction_pct: float = 0.0

    # Economics
    hub_capex_m: float = 0.0
    satellite_capex_m: float = 0.0
    total_capex_m: float = 0.0
    annualised_capex_yr: float = 0.0

    hub_opex_yr: float = 0.0
    satellite_opex_yr: float = 0.0
    transport_cost_yr: float = 0.0
    disposal_cost_yr: float = 0.0
    total_opex_yr: float = 0.0

    avoided_disposal_yr: float = 0.0
    net_annual_value: float = 0.0

    # Energy
    hub_chp_kwh_d: float = 0.0
    satellite_chp_kwh_d: float = 0.0
    total_chp_kwh_d: float = 0.0
    hub_heat_for_drying_kwh_d: float = 0.0
    hub_drying_self_sufficient: bool = False

    # Mainstream coupling at hub
    hub_return_nh4_kg_d: float = 0.0
    hub_mainstream_impact: str = ""
    hub_sidestream_required: bool = False

    # Risk
    system_resilience: str = ""    # "Low" / "Moderate" / "High"
    resilience_basis: str = ""
    disposal_dependency_pct: float = 0.0

    # Verdict
    vs_full_centralised: str = ""
    vs_full_decentralised: str = ""
    recommendation: str = ""
    notes: list = field(default_factory=list)


@dataclass
class HybridSystemAssessment:
    """Full hybrid system assessment output."""
    system_ds_tpd: float = 0.0
    n_sites: int = 0
    sites: list = field(default_factory=list)

    # Generated configurations
    configurations: list = field(default_factory=list)    # List[HybridConfiguration]

    # Benchmarks
    full_centralised: Optional[HybridConfiguration] = None
    full_decentralised: Optional[HybridConfiguration] = None

    # Best hybrid
    best_hybrid: Optional[HybridConfiguration] = None
    best_hybrid_rank: int = 0

    # Summary
    recommended_config: str = ""
    recommended_hub_sites: list = field(default_factory=list)
    recommended_hub_treatment: str = ""
    system_narrative: str = ""


# ---------------------------------------------------------------------------
# SITE SELECTION ALGORITHM
# ---------------------------------------------------------------------------

def select_hub_sites(sites: list, n_hub_sites: int,
                      distance_matrix: Optional[dict] = None) -> list:
    """
    Identify optimal hub sites by volume × infrastructure score.

    Scoring:
      - Volume fraction (0–50 points): larger sites are preferred
      - Infrastructure (0–30 points): existing AD, CHP, dryer
      - Hub candidate (0–20 points): not all sites can host a hub

    Returns list of selected hub SiteInputs.
    """
    scores = {}
    system_ds = sum(s.dry_solids_tpd for s in sites)

    for s in sites:
        if not s.is_hub_candidate:
            scores[s.site_id] = 0.0
            continue
        vol_score  = (s.dry_solids_tpd / system_ds) * 50
        infra_score = (10 if s.has_ad else 0) + (10 if s.has_chp else 0) + (10 if s.has_dryer else 0)
        candidate_score = 20
        scores[s.site_id] = vol_score + infra_score + candidate_score

    ranked = sorted(sites, key=lambda s: scores[s.site_id], reverse=True)
    return ranked[:n_hub_sites]


# ---------------------------------------------------------------------------
# CONFIGURATION BUILDER
# ---------------------------------------------------------------------------

def _annualisation_factor(rate_pct: float = 7.0, years: int = 25) -> float:
    r = rate_pct / 100.0
    return r * (1 + r)**years / ((1 + r)**years - 1)


def _hub_capex(technology: str, ds_tpd: float) -> float:
    """Scale hub CAPEX to actual throughput ($M)."""
    base = HUB_CAPEX_M_AT_REF.get(technology, 7.0)
    if ds_tpd <= 0:
        return 0.0
    scale = (ds_tpd / HUB_CAPEX_REFERENCE_TDS_D) ** HUB_CAPEX_SCALE_EXPONENT
    return base * scale


def _hub_mass_reduction(technology: str) -> float:
    """Fraction of incoming DS that becomes residual solid (not destroyed)."""
    reductions = {
        "HTC":          0.35,   # 35% DS as hydrochar
        "HTC_sidestream": 0.35,
        "incineration": 0.30,   # 30% DS as ash
        "pyrolysis":    0.45,   # 45% DS as char + ash
        "AD":           0.55,   # 55% DS remains (45% VS destroyed)
        "drying_only":  1.00,   # No DS destruction
    }
    return reductions.get(technology, 0.50)


def _hub_product_ds_pct(technology: str) -> float:
    """DS% of residual product leaving hub."""
    ds_pcts = {
        "HTC":          55.0,
        "HTC_sidestream": 55.0,
        "incineration": 98.0,
        "pyrolysis":    95.0,
        "AD":           22.0,   # Dewatered cake
        "drying_only":  82.0,
    }
    return ds_pcts.get(technology, 80.0)


def _hub_mainstream_impact(technology: str, ds_tpd: float) -> tuple:
    """Return (nh4_kg_d, impact_rating, sidestream_needed) for hub."""
    from engine.mainstream_coupling import RETURN_NH4_KG_PER_TDS
    nh4_per_tds = RETURN_NH4_KG_PER_TDS.get(technology, 8.0)
    nh4_kg_d = nh4_per_tds * ds_tpd
    if nh4_kg_d > 500 or technology == "HTC":
        impact = "High"
        sidestream = True
    elif nh4_kg_d > 150:
        impact = "Moderate"
        sidestream = False
    else:
        impact = "Low"
        sidestream = False
    return nh4_kg_d, impact, sidestream


def _chp_output_kwh_d(ds_tpd: float, has_ad: bool, vs_pct: float = 72.0) -> float:
    """Estimate CHP electrical output from AD at a site."""
    if not has_ad:
        return 0.0
    vsr = 0.45
    vs_destroyed_kg_d = ds_tpd * (vs_pct / 100) * vsr * 1000
    biogas_m3_d = vs_destroyed_kg_d * 0.55   # blended yield
    ch4_m3_d    = biogas_m3_d * 0.64
    ch4_lhv     = 35.8 / 3.6   # kWh/m³
    chp_kwe     = ch4_m3_d / 24 * ch4_lhv * 0.35
    return chp_kwe * 22.0   # 22h/d runtime


def build_configuration(config_id: str, config_name: str, description: str,
                         hub_treatment: str, hub_sites: list, satellite_sites: list,
                         sites_all: list, inputs_assets, inputs_strategic,
                         system_ds_tpd: float, vs_pct: float = 72.0,
                         avg_haul_satellite_to_hub_km: float = 40.0,
                         avg_haul_hub_to_disposal_km: float = 30.0,
                         dewatered_ds_pct: float = 20.0) -> HybridConfiguration:
    """Build and calculate one HybridConfiguration."""
    c = HybridConfiguration(
        config_id=config_id,
        config_name=config_name,
        description=description,
        hub_treatment=hub_treatment,
        hub_sites=hub_sites,
        satellite_sites=satellite_sites,
    )

    discount   = inputs_strategic.discount_rate_pct
    asset_life = inputs_strategic.asset_life_years
    transport_rate = inputs_assets.transport_cost_per_tonne_km
    disposal_rate  = inputs_assets.disposal_cost_per_tds

    crf = _annualisation_factor(discount, asset_life)

    # --- VOLUMES ---
    hub_ds   = sum(s.dry_solids_tpd for s in hub_sites)
    sat_ds   = sum(s.dry_solids_tpd for s in satellite_sites)
    hub_wet  = hub_ds / (dewatered_ds_pct / 100.0)
    sat_wet  = sat_ds / (dewatered_ds_pct / 100.0)

    c.hub_ds_tpd       = hub_ds
    c.hub_wet_tpd      = hub_wet
    c.satellite_ds_tpd = sat_ds
    c.satellite_wet_tpd = sat_wet

    # --- TRANSPORT TO HUB ---
    # Satellites send wet sludge to hub
    feed_transport_t_d = sat_wet
    c.feed_transport_t_d   = feed_transport_t_d
    c.feed_transport_km    = avg_haul_satellite_to_hub_km
    t_km_yr = feed_transport_t_d * 365 * avg_haul_satellite_to_hub_km
    c.feed_transport_t_km_yr   = t_km_yr
    c.feed_transport_cost_yr   = t_km_yr * transport_rate

    # --- HUB MASS REDUCTION ---
    residual_frac = _hub_mass_reduction(hub_treatment)
    product_ds_pct = _hub_product_ds_pct(hub_treatment)
    hub_total_ds   = hub_ds + sat_ds   # All DS arriving at hub (own + satellite)
    hub_residual_ds = hub_total_ds * residual_frac
    hub_residual_wet = (hub_residual_ds / (product_ds_pct / 100.0)
                        if product_ds_pct > 0 else 0.0)

    # --- SATELLITE RESIDUAL ---
    # When satellites send wet sludge to hub, all DS is processed at hub.
    # hub_total_ds = hub_ds + sat_ds already captures the full throughput.
    # Satellite local residual = 0 in consolidation configs (H01, H02, H03).
    # For H00 (full decentralised), satellite_sites is empty so we calculate
    # hub residual directly from the "hub" (which is all sites treated locally).
    if len(satellite_sites) > 0:
        # Satellites send to hub — no local residual; hub output covers everything
        sat_residual_ds  = 0.0
        sat_residual_wet = 0.0
    else:
        sat_residual_ds  = 0.0
        sat_residual_wet = 0.0

    c.satellite_disposal_t_d = sat_residual_wet
    c.satellite_disposal_cost_yr = (sat_residual_wet * 365
                                    * disposal_rate
                                    * dewatered_ds_pct / 100.0)

    # --- HUB PRODUCT TRANSPORT ---
    c.product_transport_t_d   = hub_residual_wet
    c.product_transport_km    = avg_haul_hub_to_disposal_km
    c.product_transport_cost_yr = (hub_residual_wet * 365
                                   * avg_haul_hub_to_disposal_km
                                   * transport_rate)

    # --- TOTAL DISPOSAL ---
    baseline_wet = system_ds_tpd / (dewatered_ds_pct / 100.0)
    total_residual = hub_residual_wet + sat_residual_wet
    c.total_disposal_t_d = total_residual
    c.total_disposal_reduction_pct = max(0.0,
        (1 - total_residual / baseline_wet) * 100 if baseline_wet > 0 else 0.0)

    # Disposal cost on residual
    residual_ds_total = hub_residual_ds + sat_residual_ds
    c.disposal_cost_yr = residual_ds_total * 365 * disposal_rate

    # --- CAPEX ---
    c.hub_capex_m = _hub_capex(hub_treatment, hub_total_ds)
    # Satellite CAPEX: AD upgrade at each satellite site
    sat_capex_per_site = SATELLITE_AD_CAPEX_M_AT_REF * (
        (sum(s.dry_solids_tpd for s in satellite_sites) / max(len(satellite_sites), 1)
         / HUB_CAPEX_REFERENCE_TDS_D) ** HUB_CAPEX_SCALE_EXPONENT
        if satellite_sites else 1.0
    )
    c.satellite_capex_m = sat_capex_per_site * len(satellite_sites)
    c.total_capex_m = c.hub_capex_m + c.satellite_capex_m
    c.annualised_capex_yr = c.total_capex_m * 1_000_000 * crf

    # --- OPEX ---
    # Hub OPEX: ~4% CAPEX/yr + energy (~$0.18/kWh × parasitic)
    c.hub_opex_yr = c.hub_capex_m * 1_000_000 * 0.04
    # Satellite OPEX: ~4% satellite CAPEX/yr
    c.satellite_opex_yr = c.satellite_capex_m * 1_000_000 * 0.04
    c.transport_cost_yr = c.feed_transport_cost_yr + c.product_transport_cost_yr
    c.total_opex_yr = (c.hub_opex_yr + c.satellite_opex_yr
                       + c.transport_cost_yr + c.disposal_cost_yr)

    # --- AVOIDED DISPOSAL ---
    # vs baseline: full wet sludge disposed at disposal_rate
    baseline_disposal_yr = system_ds_tpd * 365 * disposal_rate
    c.avoided_disposal_yr = baseline_disposal_yr - c.disposal_cost_yr

    # --- NET ANNUAL VALUE ---
    c.net_annual_value = c.avoided_disposal_yr - c.total_opex_yr - c.annualised_capex_yr

    # --- ENERGY INTEGRATION ---
    hub_chp   = sum(_chp_output_kwh_d(s.dry_solids_tpd, s.has_ad, vs_pct) for s in hub_sites)
    sat_chp   = sum(_chp_output_kwh_d(s.dry_solids_tpd, s.has_ad, vs_pct) for s in satellite_sites)
    c.hub_chp_kwh_d       = hub_chp
    c.satellite_chp_kwh_d = sat_chp
    c.total_chp_kwh_d     = hub_chp + sat_chp

    # Hub heat for drying: CHP thermal ~45/35 × electrical
    hub_heat = hub_chp * (0.45 / 0.35)
    c.hub_heat_for_drying_kwh_d = hub_heat
    # Drying energy at hub (to 82% DS from dewatered_ds_pct)
    if dewatered_ds_pct < 82 and hub_treatment in ("drying_only", "pyrolysis", "incineration"):
        water_to_dry_t_d = hub_total_ds / (dewatered_ds_pct/100) - hub_total_ds / 0.82
        drying_kwh_d = water_to_dry_t_d * 1000 * 0.80 / 0.75
        c.hub_drying_self_sufficient = hub_heat >= drying_kwh_d
    else:
        c.hub_drying_self_sufficient = True  # HTC/AD don't need pre-drying

    # --- MAINSTREAM COUPLING AT HUB ---
    nh4, impact, sidestream = _hub_mainstream_impact(hub_treatment, hub_total_ds)
    c.hub_return_nh4_kg_d   = nh4
    c.hub_mainstream_impact = impact
    c.hub_sidestream_required = sidestream

    # --- RESILIENCE ---
    if len(hub_sites) >= 2 or (len(satellite_sites) >= 2 and hub_total_ds > 0):
        c.system_resilience = "High"
        c.resilience_basis  = (
            f"Multiple treatment nodes: {len(hub_sites)} hub site(s) + "
            f"{len(satellite_sites)} satellite site(s). "
            "System can absorb single-site disruption."
        )
    elif len(hub_sites) == 1 and len(satellite_sites) >= 1:
        c.system_resilience = "Moderate"
        c.resilience_basis  = (
            "Single hub with satellites. Hub failure creates volume surge at satellites."
        )
    else:
        c.system_resilience = "Low"
        c.resilience_basis  = "Single node — no redundancy."

    c.disposal_dependency_pct = (
        c.total_disposal_t_d / baseline_wet * 100 if baseline_wet > 0 else 100.0
    )

    # --- NOTES ---
    if impact == "High" and hub_treatment == "HTC":
        c.notes.append(
            f"HTC hub: return NH₄-N {nh4:.0f} kgN/d — HIGH mainstream impact at hub WWTP. "
            "Sidestream treatment required. Consider HTC_sidestream configuration."
        )
    if not c.hub_drying_self_sufficient and hub_treatment in ("drying_only", "incineration"):
        c.notes.append(
            "Hub drying energy: CHP heat insufficient to self-supply dryer. "
            "External energy required — confirm heat source before committing."
        )

    return c


# ---------------------------------------------------------------------------
# MAIN ENGINE
# ---------------------------------------------------------------------------

def run_hybrid_system(sites: list, hub_treatment: str,
                       inputs_assets, inputs_strategic,
                       vs_pct: float = 72.0,
                       dewatered_ds_pct: float = 20.0,
                       avg_inter_site_km: float = 60.0) -> HybridSystemAssessment:
    """
    Full hybrid system assessment.
    Generates and ranks multiple hub configurations: 1-hub, 2-hub, full, decentral.

    Parameters
    ----------
    sites            : list[SiteInput]
    hub_treatment    : primary treatment technology at hub
    inputs_assets    : AssetInputs
    inputs_strategic : StrategicInputs
    vs_pct           : weighted average VS% of system
    dewatered_ds_pct : weighted average dewatered DS%
    avg_inter_site_km: average distance between any two sites (used for haul estimates)
    """
    system_ds = sum(s.dry_solids_tpd for s in sites)
    n = len(sites)
    for s in sites:
        s.resolve(system_ds)

    configs = []

    # Haul estimates: satellite → hub depends on configuration
    # 1-hub: all sites haul to hub → avg_inter_site_km
    # 2-hub: half the sites haul to nearest hub → avg_inter_site_km × 0.55
    haul_1hub = avg_inter_site_km * 0.85
    haul_2hub = avg_inter_site_km * 0.50
    haul_hub_to_disposal = avg_inter_site_km * 0.40

    # --- CONFIGURATION 1: FULL DECENTRALISED ---
    # All sites treat locally (AD only) — no transport to hub, technology = AD
    c_decentral = build_configuration(
        "H00", "Full Decentralised (AD at all sites)",
        f"AD optimisation at all {n} sites. No hub. Digestate to local disposal.",
        "AD",                              # Always AD for decentralised baseline
        hub_sites=sites, satellite_sites=[],
        sites_all=sites, inputs_assets=inputs_assets,
        inputs_strategic=inputs_strategic, system_ds_tpd=system_ds,
        vs_pct=vs_pct, avg_haul_satellite_to_hub_km=0.0,
        avg_haul_hub_to_disposal_km=haul_hub_to_disposal,
        dewatered_ds_pct=dewatered_ds_pct,
    )
    c_decentral.vs_full_centralised  = "Lower CAPEX, higher disposal dependency"
    c_decentral.vs_full_decentralised = "This IS full decentralised — baseline"
    configs.append(c_decentral)

    # --- CONFIGURATION 2: SINGLE HUB (largest site) ---
    hub_1 = select_hub_sites(sites, 1)
    sats_1 = [s for s in sites if s.site_id not in {h.site_id for h in hub_1}]
    c_1hub = build_configuration(
        "H01", f"Single Hub at {hub_1[0].name} ({hub_treatment})",
        f"All sludge consolidated at {hub_1[0].name}. "
        f"{len(sats_1)} satellite sites haul wet sludge to hub.",
        hub_treatment, hub_sites=hub_1, satellite_sites=sats_1,
        sites_all=sites, inputs_assets=inputs_assets,
        inputs_strategic=inputs_strategic, system_ds_tpd=system_ds,
        vs_pct=vs_pct, avg_haul_satellite_to_hub_km=haul_1hub,
        avg_haul_hub_to_disposal_km=haul_hub_to_disposal,
        dewatered_ds_pct=dewatered_ds_pct,
    )
    c_1hub.vs_full_centralised   = "This IS full centralisation"
    c_1hub.vs_full_decentralised = (
        f"Higher CAPEX (+${c_1hub.total_capex_m - c_decentral.total_capex_m:.0f}M) "
        f"but {c_1hub.total_disposal_reduction_pct:.0f}% disposal reduction vs "
        f"{c_decentral.total_disposal_reduction_pct:.0f}%"
    )
    configs.append(c_1hub)

    # --- CONFIGURATION 3: TWO-HUB HYBRID (top 2 sites as hubs) ---
    if n >= 3:
        hub_2 = select_hub_sites(sites, 2)
        sats_2 = [s for s in sites if s.site_id not in {h.site_id for h in hub_2}]
        c_2hub = build_configuration(
            "H02", f"Two-Hub Hybrid ({hub_2[0].name} + {hub_2[1].name})",
            f"Two regional hubs at top-2 sites. "
            f"{len(sats_2)} satellite(s) haul to nearest hub.",
            hub_treatment, hub_sites=hub_2, satellite_sites=sats_2,
            sites_all=sites, inputs_assets=inputs_assets,
            inputs_strategic=inputs_strategic, system_ds_tpd=system_ds,
            vs_pct=vs_pct, avg_haul_satellite_to_hub_km=haul_2hub,
            avg_haul_hub_to_disposal_km=haul_hub_to_disposal,
            dewatered_ds_pct=dewatered_ds_pct,
        )
        c_2hub.vs_full_centralised = (
            f"Lower transport cost (avg haul {haul_2hub:.0f} km vs {haul_1hub:.0f} km). "
            f"Slightly higher CAPEX (two smaller units lose economy of scale)."
        )
        c_2hub.vs_full_decentralised = (
            f"{c_2hub.total_disposal_reduction_pct:.0f}% disposal reduction "
            "with lower per-unit transport than single hub."
        )
        configs.append(c_2hub)

    # --- CONFIGURATION 4: PARTIAL HUB HYBRID (top site only; others keep AD) ---
    if n >= 3:
        hub_partial = select_hub_sites(sites, 1)
        # In this config, satellites only send 60% of volume to hub (pre-dewatered)
        # Remaining 40% is managed locally after AD
        # Model as: satellite_ds = 60% of sat volume; hub handles its own + partial import
        sats_partial = [s for s in sites if s.site_id not in {h.site_id for h in hub_partial}]
        # Create reduced-volume satellites
        import copy
        sats_partial_reduced = []
        for s in sats_partial:
            s_copy = copy.copy(s)
            s_copy.dry_solids_tpd = s.dry_solids_tpd * 0.60   # Send 60% to hub
            sats_partial_reduced.append(s_copy)

        c_partial = build_configuration(
            "H03", f"Partial Hub Hybrid (60% consolidation at {hub_partial[0].name})",
            f"Hub at {hub_partial[0].name} receives 60% of satellite volume. "
            "Remaining 40% treated locally via AD + dewatering.",
            hub_treatment, hub_sites=hub_partial, satellite_sites=sats_partial_reduced,
            sites_all=sites, inputs_assets=inputs_assets,
            inputs_strategic=inputs_strategic, system_ds_tpd=system_ds,
            vs_pct=vs_pct, avg_haul_satellite_to_hub_km=haul_1hub * 0.7,
            avg_haul_hub_to_disposal_km=haul_hub_to_disposal,
            dewatered_ds_pct=dewatered_ds_pct,
        )
        c_partial.vs_full_centralised = (
            "Lower transport: only 60% of satellite volume hauled to hub. "
            "Lower hub CAPEX (smaller unit). Retains distributed resilience."
        )
        c_partial.vs_full_decentralised = (
            f"Hub provides {c_partial.total_disposal_reduction_pct:.0f}% disposal reduction "
            "at lower investment than full centralisation."
        )
        configs.append(c_partial)

    # --- RANK CONFIGURATIONS ---
    # Primary: net annual value. Secondary: system resilience.
    resilience_bonus = {"High": 0, "Moderate": -0.5e6, "Low": -2e6}
    configs.sort(
        key=lambda c: c.net_annual_value + resilience_bonus.get(c.system_resilience, 0),
        reverse=True
    )

    # Identify benchmarks and best hybrid
    full_central = next((c for c in configs if c.config_id == "H01"), None)
    full_decentral = next((c for c in configs if c.config_id == "H00"), None)
    hybrids = [c for c in configs if c.config_id not in ("H00", "H01")]
    best_hybrid = hybrids[0] if hybrids else None
    best_rank   = configs.index(best_hybrid) + 1 if best_hybrid else 0

    # Narrative
    narrative = _system_narrative(configs, best_hybrid, full_central, full_decentral,
                                   hub_treatment, system_ds, n)

    # Recommended hub sites
    rec_hubs = best_hybrid.hub_sites if best_hybrid else (full_central.hub_sites if full_central else [])

    return HybridSystemAssessment(
        system_ds_tpd=system_ds,
        n_sites=n,
        sites=sites,
        configurations=configs,
        full_centralised=full_central,
        full_decentralised=full_decentral,
        best_hybrid=best_hybrid,
        best_hybrid_rank=best_rank,
        recommended_config=best_hybrid.config_name if best_hybrid else (full_central.config_name if full_central else ""),
        recommended_hub_sites=[s.name for s in rec_hubs],
        recommended_hub_treatment=hub_treatment,
        system_narrative=narrative,
    )


def _system_narrative(configs, best_hybrid, full_central, full_decentral,
                       hub_treatment, system_ds, n_sites) -> str:
    parts = []
    if best_hybrid:
        parts.append(
            f"Best hybrid configuration: {best_hybrid.config_name}. "
            f"Net annual value ${best_hybrid.net_annual_value:+,.0f}/yr. "
            f"Disposal reduction {best_hybrid.total_disposal_reduction_pct:.0f}%. "
            f"System resilience: {best_hybrid.system_resilience}."
        )
    if full_central and best_hybrid:
        if best_hybrid.net_annual_value > full_central.net_annual_value:
            parts.append(
                f"Hybrid outperforms full centralisation by "
                f"${best_hybrid.net_annual_value - full_central.net_annual_value:+,.0f}/yr "
                f"through lower transport cost and retained distributed resilience."
            )
        else:
            parts.append(
                f"Full centralisation outperforms best hybrid by "
                f"${full_central.net_annual_value - best_hybrid.net_annual_value:+,.0f}/yr "
                f"through stronger economy of scale — but at higher single-node risk."
            )
    if best_hybrid and best_hybrid.hub_mainstream_impact == "High":
        parts.append(
            f"Hub mainstream coupling: HIGH at {hub_treatment} hub. "
            "Consider HTC_sidestream or schedule return liquor for off-peak."
        )
    return " ".join(parts)
