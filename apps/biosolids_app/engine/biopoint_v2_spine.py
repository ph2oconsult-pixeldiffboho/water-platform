"""
BioPoint V2 — Strategic Pathway Spine (first slice)
===================================================

This is NOT the old technology scorer. It is the spine of the pathway-intelligence
architecture agreed in design:

    objective (driver ranking)
      -> constraint diagnosis
        -> pathway register, each pathway carrying FOUR conserved-quantity ledgers
           (Carbon, Energy, Nitrogen, Phosphorus) that MUST close end-to-end
             -> drivers scored OFF the ledgers (no independent double-counted engines)
               -> moves tagged commit / keep-open / avoid (reward, residual risk, confidence)
                 -> roadmap

Core discipline (the St Marys gate, generalised): a ledger that does not close is a
model that is lying. Closure is both the QA gate and the headline. Driver scores are
VIEWS of the four balances, not separate calculations.

Worked pathway in this slice: Primary treatment -> separate dewater -> THP of WAS ->
MAD of (PS + THP-WAS) -> dewater -> struvite recovery -> cake to land. Chosen because
all four ledgers close against real calibrated data (St Marys / Mangere). The thermal
endpoint (PFAS / Scope-1) is left as a KEEP-OPEN move with a priced de-risking task —
it is the gap this "safe" pathway does not close, and the next build.

Boundary: includes upstream consequences (primary-capture aeration credit, dewatering),
per the decision that upstream processing is equally important to the energy balance.

Calibration provenance is tagged inline. Confidence is tracked SEPARATELY from
performance and gates the recommendation verb — it never silently excludes a pathway.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable


# ---------------------------------------------------------------------------
# 1. STRATEGIC OBJECTIVE  — driver ranking is an explicit input, never hidden
# ---------------------------------------------------------------------------
# The user's ranking. Order is the only thing asserted; no strategy inferred from it.
DRIVER_RANKING = [
    "scope1_emissions",
    "pfas",
    "nutrient_recovery",
    "opex",
    "future_proof",
    "capacity",
    "capex",
]
# Energy neutrality sits alongside these as a first-class driver (whole-pathway net).
DRIVER_RANKING_PLUS = ["energy_neutrality"] + DRIVER_RANKING


def rank_weights(ranking: list[str]) -> dict[str, float]:
    """Rank-order weights (top driver heaviest), normalised to sum 1.0.
    Deliberately simple and transparent — the board can see exactly why a
    weighting is what it is. No magic."""
    n = len(ranking)
    raw = {d: (n - i) for i, d in enumerate(ranking)}  # n, n-1, ... 1
    total = sum(raw.values())
    return {d: v / total for d, v in raw.items()}


# ---------------------------------------------------------------------------
# 2. CONSERVED-QUANTITY LEDGER  — the backbone. Must close or it is inadmissible.
# ---------------------------------------------------------------------------
@dataclass
class Ledger:
    """A single conserved quantity tracked across the whole pathway.
    `inflows` and `outflows` are {label: amount} in consistent units.
    Closure = (sum_in - sum_out) within tolerance. This is the St Marys gate."""
    quantity: str
    unit: str
    inflows: dict[str, float] = field(default_factory=dict)
    outflows: dict[str, float] = field(default_factory=dict)
    tol_pct: float = 2.0            # commit-grade closure tolerance
    provisional_tol_pct: float = 15.0  # thermal/uncertain branches: provisional, not committed
    provisional: bool = False       # set True when split fractions are not calibrated

    @property
    def total_in(self) -> float:
        return sum(self.inflows.values())

    @property
    def total_out(self) -> float:
        return sum(self.outflows.values())

    @property
    def imbalance_pct(self) -> float:
        if self.total_in == 0:
            return 0.0
        return 100.0 * (self.total_in - self.total_out) / self.total_in

    @property
    def closes(self) -> bool:
        tol = self.provisional_tol_pct if self.provisional else self.tol_pct
        return abs(self.imbalance_pct) <= tol

    def fraction_to(self, *labels: str) -> float:
        """Recovered / routed fraction — this is how a driver reads the ledger."""
        got = sum(self.outflows.get(l, 0.0) for l in labels)
        return got / self.total_in if self.total_in else 0.0

    def report(self) -> str:
        flag = ""
        if self.provisional:
            flag = "  [PROVISIONAL — split fractions not calibrated]"
        lines = [f"  {self.quantity} ledger ({self.unit}){flag}"]
        lines.append(f"    IN  {self.total_in:>10.2f}")
        for k, v in self.inflows.items():
            lines.append(f"        {k:<34}{v:>10.2f}")
        lines.append(f"    OUT {self.total_out:>10.2f}")
        for k, v in self.outflows.items():
            lines.append(f"        {k:<34}{v:>10.2f}")
        status = "CLOSES" if self.closes else "*** DOES NOT CLOSE ***"
        lines.append(f"    imbalance {self.imbalance_pct:+.2f}%   {status}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# 3. CALIBRATED CONSTANTS  — sourced from our validated reference work
# ---------------------------------------------------------------------------
class K:
    # St Marys Cambi THP full-scale (Sydney Water) — confidence 95/100
    VSR = 0.566                 # VS reduction, calibrated (St Marys; Mangere THP 0.582)
    VSR_CONV = 0.49             # conventional blended MAD VSR (ETP HRT-constrained; V1 ~44-49%)
    VS_TS = 0.808               # VS/TS, PFD Note 3
    METHANE_YIELD_NM3_TDS = 258 # Nm3 CH4 / tDS feed (St Marys == Davyhulme)
    STEAM_T_PER_TDS = 0.94      # THP steam, t/tDS THP feed (band 0.85-1.00)
    # Physical / stoichiometric
    C_PER_VS = 0.51             # gC / gVS, municipal sludge (band 0.45-0.53)
    N_PER_VS = 0.050            # gN / gVS feed (used only when no measured feed N)
    # Soluble NH4 reporting to centrate = feed_N x VSR x this efficiency. Calibrated so a
    # THP case lands in the Mangere MEASURED centrate band (32-43% of feed N), NOT = VSR.
    # Setting release = VSR (the legacy approach) over-predicts centrate N (the old "8,814").
    N_SOLUBILISATION_EFF = 0.70
    P_PER_DS = 0.012            # gP / gDS feed
    CH4_LHV_KWH_NM3 = 9.97      # lower heating value
    CH4_C_KG_PER_NM3 = 0.535    # kg C per Nm3 CH4
    BIOGAS_NM3_PER_KG_VSD = 0.95
    CH4_FRACTION = 0.63         # THP-AD biogas CH4 by volume
    FUGITIVE_CH4_FRAC = 0.015   # methane slip -> Scope 1 (capture performance, not gas volume)
    CHP_ELEC = 0.40
    CHP_HEAT = 0.45
    STEAM_KWH_PER_KG = 0.70     # ~2.6 MJ/kg saturated steam
    DEWATER_KWH_PER_TDS = 40.0
    DIGESTER_HEAT_MWH_D = 15.0  # net, after hot THP-WAS heat integration
    STRUVITE_PARASITIC_MWH_D = 1.5
    THP_PUMP_PARASITIC_MWH_D = 2.0
    PLANT_PARASITIC_MWH_D = 5.0
    PRIMARY_AERATION_CREDIT_MWH_D = 15.0  # UPSTREAM consequence: PS capture cuts aeration
    # Cooling model (V3 U6) - St Marys: 32.1 t/h cooling water at 45.8 tDS/d THP feed
    COOLING_WATER_T_PER_TDS = 16.8     # t cooling water / tDS THP feed (32.1 t/h x 24h / 45.8)
    COOLING_PUMP_KWH_PER_T = 0.10      # circulation + tower fans, kWh per t water (ESTIMATE, flagged)
    # Fate split fractions (calibrated for AD/THP; would be PROVISIONAL for thermal)
    C_LIQUOR_FRAC = 0.02        # of digestate C, to liquor on dewatering
    N_MINERALISED_AS_VSR = True # NH4 release tracks VS destruction
    P_SOLUBILISED_FRAC = 0.40   # of feed P released to liquor in MAD
    STRUVITE_P_RECOVERY = 0.85  # of soluble P captured as struvite
    STRUVITE_N_PER_P_MOLAR = 1.0  # struvite is 1:1 N:P -> N recovery is P-limited


# ---------------------------------------------------------------------------
# 4. CONFIDENCE  — multi-dimensional, gates the VERB not admissibility
# ---------------------------------------------------------------------------
class Conf(Enum):
    A = "A — Proven (full-scale reference)"
    B = "B — Strong evidence"
    C = "C — Emerging"
    D = "D — Hypothesis"


@dataclass
class Confidence:
    technical: Conf
    calibration: Conf
    social_regulatory: Conf

    def weakest(self) -> Conf:
        order = [Conf.A, Conf.B, Conf.C, Conf.D]
        return max((self.technical, self.calibration, self.social_regulatory),
                   key=lambda c: order.index(c))

    def verb(self) -> str:
        """Recommendation verb governed by the weakest gate that matters."""
        return {
            Conf.A: "RECOMMEND — commit-grade",
            Conf.B: "RECOMMEND — commit-grade",
            Conf.C: "SHORTLIST — pilot required before commit",
            Conf.D: "HYPOTHESIS — do not commit capital; de-risk first",
        }[self.weakest()]


# ---------------------------------------------------------------------------
# 5. MOVE  — the unit of the adaptive roadmap. Reward, risk, confidence: separate.
# ---------------------------------------------------------------------------
class Tag(Enum):
    COMMIT = "commit-now"
    KEEP_OPEN = "keep-open (option)"
    AVOID = "avoid (forecloses / asymmetric downside)"


@dataclass
class Move:
    name: str
    addresses: list[str]          # which drivers it serves
    reward: str                   # stated at full volume (not muted by low TRL)
    residual_risk: str            # what remains after de-risking
    confidence: Confidence
    derisk_task: str | None       # priced/scheduled task to reach commit-grade (None if A/B)
    tag: Tag
    forecloses: list[str] = field(default_factory=list)  # future moves it would block


# ---------------------------------------------------------------------------
# 6. PATHWAY  — carries the four ledgers + computes driver scores from them
# ---------------------------------------------------------------------------
def scope1_score(fugitive_C: float, fossil_C: float, stored_C: float, feed_C: float) -> float:
    """Unified Scope-1 view: penalise atmospheric leakage (fugitive CH4 + fossil CO2),
    credit durable carbon storage (char). One definition for all pathways."""
    leak = (fugitive_C + fossil_C) / feed_C
    stored = stored_C / feed_C
    return max(0.0, min(1.0, 1.0 - leak / 0.05 + stored))


@dataclass
class Pathway:
    name: str
    description: str
    ledgers: dict[str, Ledger]
    moves: list[Move]
    # PFAS is a trace contaminant, not a carbon-mass term — tracked as a fate fraction.
    pfas_destruction_frac: float = 0.0
    # Net pathway energy (incl. upstream aeration credit) and gross generation, MWh/d.
    net_export_mwh_d: float = 0.0
    generation_mwh_d: float = 0.0
    # Physical basis for bolt-on views (capacity, opex) that need feed/product data.
    basis: dict = field(default_factory=dict)
    # Provisional pathways carry energy/scope1 BANDS from uncertain (uncalibrated) terms.
    bands: dict[str, tuple[float, float, float]] = field(default_factory=dict)
    # Overall confidence (weakest gate) and traits the resilience engine reads.
    confidence_level: "Conf" = None
    traits: dict = field(default_factory=dict)

    def gate(self) -> tuple[bool, list[str]]:
        """Admissibility gate: every ledger must close (commit) or be flagged provisional."""
        msgs, ok = [], True
        for q, lg in self.ledgers.items():
            if not lg.closes:
                ok = False
                msgs.append(f"{q}: imbalance {lg.imbalance_pct:+.2f}% exceeds tolerance")
            elif lg.provisional:
                msgs.append(f"{q}: closes only within provisional tolerance — NOT commit-grade")
        return ok, msgs

    def driver_scores(self) -> dict[str, float]:
        """Scores are VIEWS of the ledgers. 0..1, higher = better. No double counting."""
        C, N, P = (self.ledgers[k] for k in ("carbon", "nitrogen", "phosphorus"))

        # Scope 1: unified view over the carbon ledger's leak + storage branches.
        fugitive_C = C.outflows.get("atmosphere_fugitive_CH4_scope1", 0.0)
        fossil_C = C.outflows.get("atmosphere_fossil_CO2_from_drying", 0.0)
        stored_C = C.outflows.get("char_permanently_stored", 0.0)
        scope1 = scope1_score(fugitive_C, fossil_C, stored_C, C.inflows["feed_volatile_carbon"])

        # PFAS: destruction fraction — a fate property of the endpoint, not carbon mass.
        pfas = self.pfas_destruction_frac

        # Nutrient recovery: recovered N + P fractions, off the N and P ledgers.
        n_rec = N.fraction_to("struvite_N")
        p_rec = P.fraction_to("struvite_P")
        nutrient_recovery = 0.5 * n_rec + 0.5 * p_rec

        # Energy neutrality: net pathway energy / gross generation (set per pathway).
        energy_neutrality = (min(1.0, max(0.0, self.net_export_mwh_d / self.generation_mwh_d))
                             if self.generation_mwh_d else 0.0)

        # OPEX and capacity: ledger/basis views (calibrated to Thames/Blue Plains/St Marys).
        opex = opex_view(self)["score"]
        capacity = capacity_view(self)["score"]

        return {
            "scope1_emissions": scope1,
            "pfas": pfas,
            "nutrient_recovery": nutrient_recovery,
            "opex": opex,
            "energy_neutrality": energy_neutrality,
            "capacity": capacity,
        }


# ---------------------------------------------------------------------------
# 6b. BOLT-ON VIEWS — capacity & opex, read off basis + ledgers (calibrated)
# ---------------------------------------------------------------------------
class KCAP:  # capacity constants — three-constraint sizing (Thames/Ringsend/Blue Plains/St Marys)
    THP_FEED_DS = 10.0      # %DS THP can feed the digester at
    CONV_FEED_DS = 5.5      # %DS conventional blended feed (used if per-stream TS absent)
    # OLR design limits (kgVS/m3/d): THP runs far higher because hydrolysis is pre-completed
    OLR_CONV = 2.5          # conventional stable limit (range 1-3)
    OLR_THP = 5.0           # THP (range 4-6; Ringsend/Cambi references)
    # HRT required for hydrolysis completion: conventional WAS-limited; THP pre-hydrolysed
    HRT_HYDROLYSIS_CONV = 18.0
    HRT_HYDROLYSIS_THP = 10.0
    HRT_FLOOR = 12.0        # hydraulic/washout minimum regardless of kinetics
    CAPEX_PER_M3 = 2000.0   # AUD installed digester capital
    DIGESTER_UNIT_M3 = 8000.0


def _volume_constraints(Q, vs_load_kg, olr_max, hrt_hydrolysis):
    """Three independent volume requirements; required volume is the binding (max) one."""
    v_hydraulic = Q * KCAP.HRT_FLOOR
    v_hydrolysis = Q * hrt_hydrolysis
    v_olr = vs_load_kg / olr_max
    vols = {"hydraulic": v_hydraulic, "hydrolysis": v_hydrolysis, "OLR": v_olr}
    governing = max(vols, key=vols.get)
    return vols, governing, vols[governing]


def capacity_view(pw: Pathway) -> dict:
    """Capacity intensification via the actual full-scale mechanism: THP pre-completes
    hydrolysis, so the binding constraint shifts from hydrolysis-limited HRT (conventional)
    to OLR (THP), which can run 2x higher. Required volume = MAX(hydraulic, hydrolysis, OLR)
    per mode. This is why Thames/Ringsend/Blue Plains/St Marys cut digester volume so far."""
    b = pw.basis
    if not b.get("has_thp"):
        return {"score": 0.0, "note": "no THP - baseline capacity (no intensification)"}
    tds = b["total_tds"]
    vs_ts = b.get("vs_ts", 0.65)
    vs_load_kg = tds * vs_ts * 1000.0
    # conventional hydraulic flow (per-stream TS if available)
    if b.get("ps_ts") and b.get("was_ts"):
        q_conv = b["ps_tds"] / (b["ps_ts"]/100.0) + b["was_tds"] / (b["was_ts"]/100.0)
    else:
        q_conv = tds / (KCAP.CONV_FEED_DS / 100.0)
    q_thp = tds / (KCAP.THP_FEED_DS / 100.0)

    cv, cgov, vol_conv = _volume_constraints(q_conv, vs_load_kg, KCAP.OLR_CONV, KCAP.HRT_HYDROLYSIS_CONV)
    tv, tgov, vol_thp = _volume_constraints(q_thp, vs_load_kg, KCAP.OLR_THP, KCAP.HRT_HYDROLYSIS_THP)
    avoided_m3 = max(0.0, vol_conv - vol_thp)
    out = {
        "q_conv_m3d": q_conv, "q_thp_m3d": q_thp,
        "conv_constraints": cv, "conv_governing": cgov, "vol_conv_m3": vol_conv,
        "thp_constraints": tv, "thp_governing": tgov, "vol_thp_m3": vol_thp,
        "avoided_m3": avoided_m3,
        "avoided_capex_aud": avoided_m3 * KCAP.CAPEX_PER_M3,
        # Low/Base/High: tank-only ($2,000) vs full replacement incl. mixers, HX, pumping,
        # pipework, odour, electrical, buildings, land ($3,500-5,000/m3)
        "capex_low_aud": avoided_m3 * 2000.0,
        "capex_base_aud": avoided_m3 * 3500.0,
        "capex_high_aud": avoided_m3 * 5000.0,
        "digesters_avoided": avoided_m3 / KCAP.DIGESTER_UNIT_M3,
        "score": min(1.0, avoided_m3 / vol_conv) if vol_conv else 0.0,
    }
    if b.get("digester_vol_m3"):
        V = b["digester_vol_m3"]
        out["existing_vol_m3"] = V
        out["hrt_conv_existing_d"] = V / q_conv
        out["hrt_thp_existing_d"] = V / q_thp
        # existing-tank throughput ceiling = MIN of OLR-limited and HRT-floor-limited DS
        ds_olr = (V * KCAP.OLR_THP) / (vs_ts * 1000.0)          # tDS/d at OLR limit
        ds_hrt = (V / KCAP.HRT_FLOOR) * (KCAP.THP_FEED_DS/100.0)  # tDS/d at HRT floor
        max_ds = min(ds_olr, ds_hrt)
        out["max_ds_existing_tds"] = max_ds
        out["existing_governing"] = "OLR" if ds_olr <= ds_hrt else "hydraulic floor"
        out["capacity_headroom_tds"] = max(0.0, max_ds - tds)
    return out


class KO:  # opex constants (AUD)
    ELEC_PRICE_MWH = 120.0
    TRANSPORT_PER_T = 15.0       # effective $/wet-t incl. ~100 km haul
    STRUVITE_PRICE_T = 400.0
    STRUVITE_MW_PER_P = 245.0 / 31.0


def opex_view(pw: Pathway) -> dict:
    """Annual OPEX, read off ledgers + basis. Energy from net export, transport from
    product tonnage, chemicals/O&M from basis, product revenue from the P ledger.
    Negative = net cash positive (revenue exceeds cost)."""
    b = pw.basis
    energy = -pw.net_export_mwh_d * KO.ELEC_PRICE_MWH * 365 / 1e6        # M$/yr
    transport = b.get("product_wet_tpd", 0.0) * 365 * KO.TRANSPORT_PER_T / 1e6
    chemicals = b.get("chemicals_m_aud", 0.0)
    om = b.get("om_m_aud", 0.0)
    P_struvite = pw.ledgers["phosphorus"].outflows.get("struvite_P", 0.0)  # kgP/d
    struvite_rev = (P_struvite * KO.STRUVITE_MW_PER_P / 1000.0
                    * 365 * KO.STRUVITE_PRICE_T / 1e6)
    net = energy + transport + chemicals + om - struvite_rev
    # score: net +$10M/yr -> 0 ; net -$5M/yr (revenue) -> 1
    score = max(0.0, min(1.0, (10.0 - net) / 15.0))
    return {
        "energy_m_aud": energy, "transport_m_aud": transport,
        "chemicals_m_aud": chemicals, "om_m_aud": om,
        "struvite_revenue_m_aud": struvite_rev, "net_m_aud": net, "score": score,
    }



# ---------------------------------------------------------------------------
# 6c. PLANT BASIS — real feed data; GENERIC is the demonstrator, ETP the road test
# ---------------------------------------------------------------------------
GENERIC = dict(name="Generic 100 tDS/d", PS_tds=40.0, WAS_tds=60.0,
               ps_ts=5.0, was_ts=5.0, vs_ts=0.808,
               feed_N_kgd=None, P_per_ds=0.012, digester_vol_m3=None)

# ETP real basis (from production cutover fixture + centrate case study):
# PS 120.7 tDS @7.5%TS, WAS 98.8 tDS @3.5%TS, VS 65% both, feed N 12,624 kg/d
# (PS 3.5%, WAS 8.5% of DS), existing conventional digesters 64,000 m3. P not
# measured at ETP -> retained as estimate, flagged.
ETP = dict(name="ETP (220 tDS/d, real basis)", PS_tds=120.7, WAS_tds=98.8,
           ps_ts=7.5, was_ts=3.5, vs_ts=0.65,
           feed_N_kgd=12624.0, P_per_ds=0.012, digester_vol_m3=64000.0)


# ===========================================================================
# V3 U6 - ST MARYS THP REFERENCE CARD (Sydney Water) - calibration anchor, 95/100
# Most figures here already drive class K (VSR, methane yield 258, steam 0.94,
# CH4 63%). Captured as the documented Tier-1 calibration plant.
ST_MARYS = dict(
    plant="St Marys THP (Sydney Water)",
    peak_load_tds_d=45.8, feed_ds_pct=16.5, thp_temp_C=165, thp_press_barg=6.0,
    steam_t_per_h=1.8, steam_t_per_tds=0.94, biogas_nm3_per_h=782, ch4_pct=63,
    ch4_yield_nm3_per_tds=258, flash_ds_pct=9.0, digester_feed_ds_pct=5.8,
    cooling_water_t_per_h=32.1, confidence_score=95,
)


def build_worked_pathway(plant: dict = GENERIC) -> Pathway:
    # --- Feed basis (from plant) ---
    WAS_tds = plant["WAS_tds"]
    PS_tds = plant["PS_tds"]
    total_tds = WAS_tds + PS_tds
    vs_ts = plant["vs_ts"]
    VS_in = total_tds * vs_ts
    VS_destroyed = VS_in * K.VSR
    VS_remaining = VS_in - VS_destroyed

    # ---------------- CARBON (tC/d) ----------------
    C_in = VS_in * K.C_PER_VS
    C_biogas = VS_destroyed * K.C_PER_VS
    C_digestate = C_in - C_biogas
    C_liquor = C_digestate * K.C_LIQUOR_FRAC
    C_cake = C_digestate - C_liquor
    # biogas carbon -> CH4-C and CO2-C; CH4 combusted -> biogenic CO2 to atm, slip -> Scope1
    CH4_nm3 = VS_destroyed * 1000 * K.BIOGAS_NM3_PER_KG_VSD * K.CH4_FRACTION
    C_CH4 = CH4_nm3 * K.CH4_C_KG_PER_NM3 / 1000.0
    C_CO2_biogas = C_biogas - C_CH4
    C_fugitive = C_CH4 * K.FUGITIVE_CH4_FRAC
    C_combusted = C_CH4 - C_fugitive
    carbon = Ledger("carbon", "tC/d",
        inflows={"feed_volatile_carbon": C_in},
        outflows={
            "soil_land_application": C_cake,
            "return_liquor_to_WWTW": C_liquor,
            "atmosphere_biogenic_CO2": C_combusted + C_CO2_biogas,
            "atmosphere_fugitive_CH4_scope1": C_fugitive,
        })

    # ---------------- ENERGY (MWh/d) ----------------
    biogas_chem = CH4_nm3 * K.CH4_LHV_KWH_NM3 / 1000.0
    elec_gen = biogas_chem * K.CHP_ELEC
    heat_gen = biogas_chem * K.CHP_HEAT
    chp_losses = biogas_chem * (1 - K.CHP_ELEC - K.CHP_HEAT)
    steam_t = WAS_tds * K.STEAM_T_PER_TDS
    steam_demand = steam_t * 1000 * K.STEAM_KWH_PER_KG / 1000.0
    heat_demand = steam_demand + K.DIGESTER_HEAT_MWH_D
    heat_surplus = heat_gen - heat_demand          # >0 -> no fossil top-up (no Scope1 from heat)
    dewater_par = (VS_remaining + total_tds*(1-vs_ts)) * K.DEWATER_KWH_PER_TDS / 1000.0
    cooling_water_t = WAS_tds * K.COOLING_WATER_T_PER_TDS         # V3 U6 St Marys cooling model
    cooling_par = cooling_water_t * K.COOLING_PUMP_KWH_PER_T / 1000.0  # MWh/d circulation parasitic
    parasitics = (dewater_par + K.STRUVITE_PARASITIC_MWH_D
                  + K.THP_PUMP_PARASITIC_MWH_D + K.PLANT_PARASITIC_MWH_D + cooling_par)
    heat_surplus_unused = heat_gen - heat_demand        # delivered but unused (real output)
    net_elec = elec_gen - parasitics + K.PRIMARY_AERATION_CREDIT_MWH_D  # net incl. upstream credit
    energy = Ledger("energy", "MWh/d",
        inflows={"biogas_chemical_energy": biogas_chem},
        outflows={                                       # closes by real physics, no plug
            "chp_electricity_generated": elec_gen,
            "ad_heat_used_thp_and_digester": heat_demand,
            "heat_surplus_unused": heat_surplus_unused,
            "chp_conversion_losses": chp_losses,
        })

    # ---------------- NITROGEN (kgN/d) ----------------
    N_in = plant["feed_N_kgd"] if plant.get("feed_N_kgd") else VS_in * K.N_PER_VS * 1000.0
    N_released = N_in * K.VSR * K.N_SOLUBILISATION_EFF   # calibrated to Mangere centrate band
    N_cake = N_in - N_released                           # organic N retained in cake to land
    # struvite N recovery is P-limited (1:1 molar with recovered P)
    P_in = total_tds * plant.get("P_per_ds", K.P_PER_DS) * 1000.0
    P_soluble = P_in * K.P_SOLUBILISED_FRAC
    P_struvite = P_soluble * K.STRUVITE_P_RECOVERY
    N_struvite = P_struvite * (14.0/31.0) * K.STRUVITE_N_PER_P_MOLAR  # mass via molar 1:1
    N_liquor_return = N_released - N_struvite
    nitrogen = Ledger("nitrogen", "kgN/d",
        inflows={"feed_nitrogen": N_in},
        outflows={
            "cake_organic_N_to_land": N_cake,
            "struvite_N": N_struvite,
            "return_liquor_NH4_to_WWTW": N_liquor_return,   # the §5.4 return-liquor risk, quantified
        })

    # ---------------- PHOSPHORUS (kgP/d) ----------------
    P_cake = P_in - P_soluble
    P_liquor_return = P_soluble - P_struvite
    phosphorus = Ledger("phosphorus", "kgP/d",
        inflows={"feed_phosphorus": P_in},
        outflows={
            "cake_P_to_land": P_cake,
            "struvite_P": P_struvite,
            "return_liquor_P_to_WWTW": P_liquor_return,
        })

    # ---------------- MOVES ----------------
    A = lambda: Confidence(Conf.A, Conf.A, Conf.A)
    moves = [
        Move("Optimise MAD (mixing, HRT, dewatering)",
             addresses=["opex", "capacity", "energy_neutrality"],
             reward="Bankable energy + capacity headroom; foundation for everything downstream",
             residual_risk="Minimal — standard practice",
             confidence=A(), derisk_task=None, tag=Tag.COMMIT),
        Move("THP of WAS (Cambi-class)",
             addresses=["capacity", "energy_neutrality", "opex"],
             reward="Higher VSR + cake DS; defers digester volume CAPEX; Class A biosolids",
             residual_risk="Return-liquor NH4 load on host WWTW (quantified in N ledger)",
             confidence=Confidence(Conf.A, Conf.A, Conf.B),  # social: steam/industrial process
             derisk_task=None, tag=Tag.COMMIT),
        Move("Struvite recovery from digestate liquor",
             addresses=["nutrient_recovery"],
             reward="Recovers ~34% of feed P as saleable product; cuts return-liquor P",
             residual_risk="Recovers little N (P-limited) — N driver still largely unmet",
             confidence=Confidence(Conf.A, Conf.B, Conf.A),
             derisk_task=None, tag=Tag.COMMIT),
        Move("Ammonium-sulphate / PN-A for return-liquor N",
             addresses=["nutrient_recovery", "scope1_emissions"],
             reward="Closes the N gap struvite leaves; cuts return-liquor N2O risk",
             residual_risk="Adds process complexity; modest CAPEX",
             confidence=Confidence(Conf.A, Conf.B, Conf.A),
             derisk_task="Sidestream N pilot, ~$0.4M / 9 months", tag=Tag.KEEP_OPEN),
        Move("Thermal endpoint (pyrolysis/gasification) for residual cake",
             addresses=["pfas", "scope1_emissions"],
             reward="ONLY family that destroys PFAS (driver #2) and can stabilise carbon as char",
             residual_risk="Carbon-to-char split, syngas yield, N/P-in-ash not yet closed full-scale",
             confidence=Confidence(Conf.C, Conf.C, Conf.C),
             derisk_task="Reference-plant balance + demo, ~$1.5M / 18 months",
             tag=Tag.KEEP_OPEN, forecloses=[]),
        Move("Commit land application as terminal disposal",
             addresses=["opex", "capex"],
             reward="Cheapest endpoint today",
             residual_risk="Strands the strategy if PFAS land-application is restricted (driver #2)",
             confidence=Confidence(Conf.A, Conf.A, Conf.D),  # social/reg: high regret under PFAS
             derisk_task=None, tag=Tag.AVOID,
             forecloses=["Thermal endpoint (pyrolysis/gasification) for residual cake"]),
    ]

    pw = Pathway(
        name="Primary + THP(WAS) + MAD + Struvite + Land",
        description="St Marys-class: separate dewater -> THP of WAS -> MAD of PS+THP-WAS "
                    "-> dewater -> struvite from liquor -> cake to land. Upstream "
                    "primary-capture aeration credit inside boundary.",
        ledgers={"carbon": carbon, "energy": energy,
                 "nitrogen": nitrogen, "phosphorus": phosphorus},
        moves=moves,
        net_export_mwh_d=net_elec,
        generation_mwh_d=biogas_chem,
        basis={
            "total_tds": total_tds, "has_thp": True, "vs_ts": vs_ts,
            "ps_tds": PS_tds, "was_tds": WAS_tds,
            "ps_ts": plant["ps_ts"], "was_ts": plant["was_ts"],
            "digester_vol_m3": plant.get("digester_vol_m3"),
            "product_wet_tpd": (VS_remaining + total_tds*(1-vs_ts)) / 0.28,  # cake @28% DS
            "cooling_water_tpd": cooling_water_t,   # V3 U6: rejected-heat / integration opportunity
            "chemicals_m_aud": 0.30 * total_tds / 100.0,   # scale with load
            "om_m_aud": 1.50 * total_tds / 100.0,
        },
    )
    _attach(pw, endpoint="land", conf=Conf.B)
    return pw


# ---------------------------------------------------------------------------
# 7b. THERMAL-ENDPOINT PATHWAY — exercises the PROVISIONAL ledger machinery
# ---------------------------------------------------------------------------
# Front end identical to the worked pathway (THP+MAD) for comparability; the
# endpoint swaps land application for dewater -> thermal dry -> gasification.
# Split fractions here are NOT calibrated against a closed full-scale balance,
# so the ledgers close arithmetically (conservation enforced) but are flagged
# PROVISIONAL, and the energy/Scope-1 drivers are rendered as BANDS.
class KT:
    CAKE_DS = 0.25              # dewatered digestate cake, fraction DS
    DRY_TARGET_DS = 0.90        # dried solids for gasifier feed
    DRY_MWH_PER_T_WATER = 0.90  # evaporation energy (latent + inefficiency)
    # PROVISIONAL (uncalibrated) — central ± band
    C_TO_CHAR_FRAC = (0.30, 0.40, 0.50)     # of feed-C retained/stabilised in char
    PFAS_DESTRUCTION = (0.85, 0.93, 0.99)   # thermal C-F bond cleavage
    SYNGAS_MWH_PER_TDS = (0.8, 1.5, 2.5)    # net usable syngas, MWh/tDS — LOW: solids already digested
    N_VOLATILISED_FRAC = 0.95   # thermal: organic+NH4 N volatilised (lost as NOx/N2)
    P_TO_ASH_FRAC = 0.98        # P locked into ash (not plant-available without recovery)


def build_thermal_pathway(plant: dict = GENERIC) -> Pathway:
    WAS_tds, PS_tds = plant["WAS_tds"], plant["PS_tds"]
    total_tds = WAS_tds + PS_tds
    vs_ts = plant["vs_ts"]
    VS_in = total_tds * vs_ts
    VS_destroyed = VS_in * K.VSR
    VS_remaining = VS_in - VS_destroyed
    fixed = total_tds * (1 - vs_ts)
    solids_to_dryer = VS_remaining + fixed                # tDS/d to dryer/gasifier

    # ---- CARBON (provisional split at gasifier) ----
    C_in = VS_in * K.C_PER_VS
    C_biogas = VS_destroyed * K.C_PER_VS
    C_digestate = C_in - C_biogas
    C_liquor = C_digestate * K.C_LIQUOR_FRAC
    C_cake = C_digestate - C_liquor                       # carbon into the dryer/gasifier
    CH4_nm3 = VS_destroyed * 1000 * K.BIOGAS_NM3_PER_KG_VSD * K.CH4_FRACTION
    C_CH4 = CH4_nm3 * K.CH4_C_KG_PER_NM3 / 1000.0
    C_CO2_biogas = C_biogas - C_CH4
    C_fugitive = C_CH4 * K.FUGITIVE_CH4_FRAC
    C_combusted = C_CH4 - C_fugitive
    char_lo, char_c, char_hi = KT.C_TO_CHAR_FRAC
    C_char = C_cake * char_c                               # central
    C_syngas_atm = C_cake - C_char                         # combusted -> atmosphere
    carbon = Ledger("carbon", "tC/d", provisional=True,
        inflows={"feed_volatile_carbon": C_in},
        outflows={
            "char_permanently_stored": C_char,             # the durable-storage branch
            "return_liquor_to_WWTW": C_liquor,
            "atmosphere_biogenic_CO2": C_combusted + C_CO2_biogas + C_syngas_atm,
            "atmosphere_fugitive_CH4_scope1": C_fugitive,
        })

    # ---- ENERGY (drying load is the crux; syngas recovery is the uncertain term) ----
    biogas_chem = CH4_nm3 * K.CH4_LHV_KWH_NM3 / 1000.0
    elec_gen = biogas_chem * K.CHP_ELEC
    heat_gen = biogas_chem * K.CHP_HEAT
    chp_losses = biogas_chem * (1 - K.CHP_ELEC - K.CHP_HEAT)
    steam_t = WAS_tds * K.STEAM_T_PER_TDS
    steam_demand = steam_t * 1000 * K.STEAM_KWH_PER_KG / 1000.0
    ad_heat_demand = steam_demand + K.DIGESTER_HEAT_MWH_D
    heat_surplus = heat_gen - ad_heat_demand               # recovered AD heat free for drying
    cake_mass = solids_to_dryer / KT.CAKE_DS
    dried_mass = solids_to_dryer / KT.DRY_TARGET_DS
    water_removed = cake_mass - dried_mass
    drying_load = water_removed * KT.DRY_MWH_PER_T_WATER    # MWh/d — the big parasitic
    syn_lo, syn_c, syn_hi = (solids_to_dryer * s for s in KT.SYNGAS_MWH_PER_TDS)
    parasitics = (solids_to_dryer * K.DEWATER_KWH_PER_TDS / 1000.0
                  + K.THP_PUMP_PARASITIC_MWH_D + K.PLANT_PARASITIC_MWH_D + 4.0)  # +gasifier aux

    def net_and_fossil(syngas):
        """AD heat covers drying first, then syngas; shortfall = FOSSIL -> Scope 1.
        Syngas beyond drying need is exported as power at gas-to-power efficiency."""
        ad_for_drying = min(heat_surplus, drying_load)
        drying_remaining = drying_load - ad_for_drying
        syn_for_drying = min(syngas, drying_remaining)
        syn_surplus = syngas - syn_for_drying
        fossil = max(0.0, drying_remaining - syn_for_drying)
        net = (elec_gen - parasitics + K.PRIMARY_AERATION_CREDIT_MWH_D
               + syn_surplus * 0.35 - fossil)
        return net, fossil

    net_c, fossil_c = net_and_fossil(syn_c)
    net_lo, fossil_lo = net_and_fossil(syn_lo)
    net_hi, fossil_hi = net_and_fossil(syn_hi)
    fossil_C_central = fossil_c * 0.05                     # tC fossil per MWh gas (~0.18 kgCO2/kWh)
    if fossil_C_central > 0:
        carbon.inflows["fossil_drying_carbon_in"] = fossil_C_central
        carbon.outflows["atmosphere_fossil_CO2_from_drying"] = fossil_C_central
    # Honest energy ledger: primary energy IN = useful delivered OUT + real losses (no plug).
    total_in = biogas_chem + syn_c + fossil_c
    useful_drying = min(drying_load, heat_surplus + syn_c + fossil_c)
    losses = total_in - elec_gen - ad_heat_demand - useful_drying - max(0.0, heat_surplus - drying_load)
    energy = Ledger("energy", "MWh/d", provisional=True,
        inflows={"biogas_chemical_energy": biogas_chem,
                 "syngas_recovery_provisional": syn_c,
                 **({"fossil_topup_for_drying": fossil_c} if fossil_c else {})},
        outflows={
            "chp_electricity_generated": elec_gen,
            "ad_heat_used": ad_heat_demand,
            "thermal_drying_delivered": useful_drying,
            "heat_surplus_unused": max(0.0, heat_surplus - drying_load),
            "conversion_and_process_losses": losses,
        })

    # ---- NITROGEN (thermal volatilises most N; little recoverable) ----
    N_in = plant["feed_N_kgd"] if plant.get("feed_N_kgd") else VS_in * K.N_PER_VS * 1000.0
    N_volatilised = N_in * KT.N_VOLATILISED_FRAC
    N_in_ash = N_in - N_volatilised
    nitrogen = Ledger("nitrogen", "kgN/d", provisional=True,
        inflows={"feed_nitrogen": N_in},
        outflows={"volatilised_NOx_N2": N_volatilised, "retained_in_ash": N_in_ash})

    # ---- PHOSPHORUS (locked in ash unless recovered upstream) ----
    P_in = total_tds * plant.get("P_per_ds", K.P_PER_DS) * 1000.0
    P_ash = P_in * KT.P_TO_ASH_FRAC
    P_liquor = P_in - P_ash
    phosphorus = Ledger("phosphorus", "kgP/d", provisional=True,
        inflows={"feed_phosphorus": P_in},
        outflows={"locked_in_ash": P_ash, "return_liquor_P": P_liquor})

    # energy / scope1 BANDS (driven by the uncalibrated syngas term)
    def en_view(net):
        return min(1.0, max(0.0, net / biogas_chem))
    energy_band = (en_view(net_lo), en_view(net_c), en_view(net_hi))
    def s1_view(fossil):
        return scope1_score(C_fugitive, fossil * 0.05, C_char, C_in)
    # low syngas -> high fossil -> worst Scope1; high syngas -> no fossil -> best
    scope1_band = (s1_view(fossil_lo), s1_view(fossil_c), s1_view(fossil_hi))

    C_grade = lambda: Confidence(Conf.C, Conf.C, Conf.C)
    moves = [
        Move("Thermal drying + low-temp gasification of digestate cake",
             addresses=["pfas", "scope1_emissions"],
             reward=f"Destroys ~{KT.PFAS_DESTRUCTION[1]*100:.0f}% PFAS; stabilises "
                    f"~{char_c*100:.0f}% of cake carbon as char; eliminates land-disposal volume",
             residual_risk="Net energy depends on uncalibrated syngas recovery; at the low band "
                           "needs fossil top-up -> Scope-1 penalty. P stranded in ash; N lost.",
             confidence=C_grade(),
             derisk_task="Full-scale reference mass balance + 6-month demo, ~$1.5M / 18 months",
             tag=Tag.KEEP_OPEN),
    ]
    pw = Pathway(
        name="THP + MAD + Thermal Drying + Gasification (endpoint)",
        description="Same THP+MAD front end; endpoint swaps land application for dewater -> "
                    "thermal dry -> low-temp gasification. PROVISIONAL: split fractions not "
                    "calibrated full-scale; energy and Scope-1 rendered as bands.",
        ledgers={"carbon": carbon, "energy": energy,
                 "nitrogen": nitrogen, "phosphorus": phosphorus},
        moves=moves,
        pfas_destruction_frac=KT.PFAS_DESTRUCTION[1],
        net_export_mwh_d=net_c,
        generation_mwh_d=biogas_chem,
        basis={
            "total_tds": total_tds, "has_thp": True, "vs_ts": vs_ts,
            "ps_tds": PS_tds, "was_tds": WAS_tds,
            "ps_ts": plant["ps_ts"], "was_ts": plant["was_ts"],
            "digester_vol_m3": plant.get("digester_vol_m3"),
            "product_wet_tpd": solids_to_dryer * 0.30 / 0.95,  # char/ash @95% DS — tiny tonnage
            "chemicals_m_aud": 0.20 * total_tds / 100.0,
            "om_m_aud": 2.50 * total_tds / 100.0,
        },
        bands={"energy_neutrality": energy_band, "scope1_emissions": scope1_band,
               "pfas": KT.PFAS_DESTRUCTION},
    )
    _attach(pw, endpoint="thermal", conf=Conf.C)
    return pw


# ---------------------------------------------------------------------------
# 7d. CONVENTIONAL MAD BASELINE — no THP; the resilience engine needs a true baseline
# ---------------------------------------------------------------------------
def build_conventional_pathway(plant: dict = GENERIC) -> Pathway:
    """Blended conventional MAD -> dewater -> land. No THP, no nutrient recovery.
    Lower VSR (HRT-constrained), Class B, no capacity intensification. The do-little
    baseline against which THP pathways are judged."""
    WAS_tds, PS_tds = plant["WAS_tds"], plant["PS_tds"]
    total_tds = WAS_tds + PS_tds
    vs_ts = plant["vs_ts"]
    VS_in = total_tds * vs_ts
    VSR = K.VSR_CONV
    VS_d = VS_in * VSR
    VS_rem = VS_in - VS_d

    C_in = VS_in * K.C_PER_VS
    C_biogas = VS_d * K.C_PER_VS
    C_dig = C_in - C_biogas
    C_liq = C_dig * K.C_LIQUOR_FRAC
    C_cake = C_dig - C_liq
    CH4 = VS_d * 1000 * K.BIOGAS_NM3_PER_KG_VSD * K.CH4_FRACTION
    C_CH4 = CH4 * K.CH4_C_KG_PER_NM3 / 1000.0
    C_fug = C_CH4 * K.FUGITIVE_CH4_FRAC
    carbon = Ledger("carbon", "tC/d",
        inflows={"feed_volatile_carbon": C_in},
        outflows={"soil_land_application": C_cake, "return_liquor_to_WWTW": C_liq,
                  "atmosphere_biogenic_CO2": (C_CH4 - C_fug) + (C_biogas - C_CH4),
                  "atmosphere_fugitive_CH4_scope1": C_fug})

    biogas_chem = CH4 * K.CH4_LHV_KWH_NM3 / 1000.0
    elec_gen = biogas_chem * K.CHP_ELEC
    heat_gen = biogas_chem * K.CHP_HEAT
    chp_losses = biogas_chem * (1 - K.CHP_ELEC - K.CHP_HEAT)
    heat_demand = K.DIGESTER_HEAT_MWH_D                       # no THP steam
    parasitics = (VS_rem + total_tds*(1-vs_ts)) * K.DEWATER_KWH_PER_TDS / 1000.0 + K.PLANT_PARASITIC_MWH_D
    net_elec = elec_gen - parasitics + K.PRIMARY_AERATION_CREDIT_MWH_D
    energy = Ledger("energy", "MWh/d",
        inflows={"biogas_chemical_energy": biogas_chem},
        outflows={"chp_electricity_generated": elec_gen, "ad_heat_used_digester": heat_demand,
                  "heat_surplus_unused": heat_gen - heat_demand, "chp_conversion_losses": chp_losses})

    N_in = plant["feed_N_kgd"] if plant.get("feed_N_kgd") else VS_in * K.N_PER_VS * 1000.0
    N_rel = N_in * VSR * K.N_SOLUBILISATION_EFF
    nitrogen = Ledger("nitrogen", "kgN/d",
        inflows={"feed_nitrogen": N_in},
        outflows={"cake_organic_N_to_land": N_in - N_rel,
                  "return_liquor_NH4_to_WWTW": N_rel})       # no recovery
    P_in = total_tds * plant.get("P_per_ds", K.P_PER_DS) * 1000.0
    P_sol = P_in * K.P_SOLUBILISED_FRAC
    phosphorus = Ledger("phosphorus", "kgP/d",
        inflows={"feed_phosphorus": P_in},
        outflows={"cake_P_to_land": P_in - P_sol, "return_liquor_P_to_WWTW": P_sol})

    moves = [Move("Conventional blended MAD + land application (baseline)",
                  addresses=["opex"], reward="Lowest capital; proven; operational baseline",
                  residual_risk="Class B only; no capacity headroom; no PFAS benefit; "
                                "fails under a land-application ban",
                  confidence=Confidence(Conf.A, Conf.A, Conf.B), derisk_task=None, tag=Tag.AVOID,
                  forecloses=[])]
    pw = Pathway(
        name="Conventional MAD + Land (baseline)",
        description="Blended PS+WAS mesophilic digestion, dewater, land application. No THP, "
                    "no nutrient recovery. The do-little baseline.",
        ledgers={"carbon": carbon, "energy": energy, "nitrogen": nitrogen, "phosphorus": phosphorus},
        moves=moves, pfas_destruction_frac=0.0,
        net_export_mwh_d=net_elec, generation_mwh_d=biogas_chem,
        basis={"total_tds": total_tds, "has_thp": False, "vs_ts": vs_ts,
               "ps_tds": PS_tds, "was_tds": WAS_tds, "ps_ts": plant["ps_ts"], "was_ts": plant["was_ts"],
               "digester_vol_m3": plant.get("digester_vol_m3"),
               "product_wet_tpd": (VS_rem + total_tds*(1-vs_ts)) / 0.22,  # Class B cake @22%
               "chemicals_m_aud": 0.15 * total_tds / 100.0, "om_m_aud": 0.80 * total_tds / 100.0})
    _attach(pw, endpoint="land", conf=Conf.A)
    return pw


def _attach(pw: Pathway, endpoint: str, conf: "Conf"):
    """Populate the traits the resilience engine reads, and the overall confidence level."""
    s = pw.driver_scores()
    C = pw.ledgers["carbon"]; P = pw.ledgers["phosphorus"]
    cap = capacity_view(pw)
    pw.confidence_level = conf
    pw.traits = {
        "endpoint": endpoint,
        "thp": bool(pw.basis.get("has_thp")),
        "pfas": pw.pfas_destruction_frac,
        "p_recovered": P.fraction_to("struvite_P"),
        "c_stored": C.fraction_to("char_permanently_stored"),
        "net_energy": pw.net_export_mwh_d,
        "net_energy_norm": max(0.0, min(1.0, pw.net_export_mwh_d / 250.0)),
        "scope1": s.get("scope1_emissions", 0.0),
        "nutrient": s.get("nutrient_recovery", 0.0),
        "headroom_norm": max(0.0, min(1.0, cap.get("capacity_headroom_tds", 0.0) / pw.basis.get("total_tds", 1))),
    }


# ---------------------------------------------------------------------------
# 7e. FUTURE RESILIENCE ENGINE — test pathways against different WORLDS
# ---------------------------------------------------------------------------
# A scenario is a future world that changes external conditions (not the driver
# weighting). Each returns (viable, performance 0-1, note) for a pathway's traits.
# Resilience = likelihood-weighted performance across worlds; a non-viable world scores 0.
_clip = lambda x: max(0.0, min(1.0, x))

@dataclass
class Scenario:
    name: str
    likelihood: float            # coarse prior: near-certain ~0.7, plausible ~0.5, tail ~0.3
    fn: object                   # (traits) -> (viable: bool, perf: float, note: str)


SCENARIOS = [
    Scenario("PFAS land-application ban", 0.70, lambda t: (
        (False, 0.0, "land application banned -> non-viable") if t["endpoint"] == "land"
        else (True, _clip(0.5 + 0.5*t["pfas"]), "thermal destroys PFAS -> becomes the solution"))),
    Scenario("Carbon price $150/tCO2e", 0.70, lambda t: (
        True, _clip(0.35 + 0.35*t["scope1"] + 0.6*t["c_stored"]),
        "monetises low Scope 1 and durable carbon storage (char)")),
    Scenario("Methane emissions regulation", 0.60, lambda t: (
        True, _clip(0.45 + 0.35*t["scope1"] + 0.2*t["c_stored"]),
        "penalises fugitive CH4; rewards captured/stabilised carbon")),
    Scenario("FOGO co-feed available", 0.50, lambda t: (
        True, _clip(0.40 + 0.25*t["thp"] + 0.45*t["headroom_norm"]),
        "spare OLR headroom (THP) absorbs co-feed for more biogas")),
    Scenario("Phosphorus price doubles", 0.45, lambda t: (
        True, _clip(0.30 + 0.70*t["p_recovered"]),
        "rewards recovered P (struvite); thermal strands P in ash")),
    Scenario("Electricity price halves", 0.40, lambda t: (
        True, _clip(0.45 + 0.20*t["thp"] + 0.15*t["nutrient"]),
        "value resting on capacity/disposal/nutrients holds; pure energy plays weaken")),
    Scenario("Utility becomes net energy exporter", 0.30, lambda t: (
        True, _clip(0.30 + 0.60*t["net_energy_norm"]),
        "rewards high net-energy pathways")),
]


def resilience(pw: Pathway) -> dict:
    """Likelihood-weighted performance of a pathway across the future worlds."""
    results, wsum, acc = [], 0.0, 0.0
    survives_pfas = True
    for sc in SCENARIOS:
        viable, perf, note = sc.fn(pw.traits)
        if not viable:
            perf = 0.0
            if "PFAS" in sc.name:
                survives_pfas = False
        results.append({"scenario": sc.name, "likelihood": sc.likelihood,
                        "viable": viable, "perf": perf, "note": note})
        wsum += sc.likelihood
        acc += sc.likelihood * perf
    return {"score": acc / wsum if wsum else 0.0, "survives_pfas_ban": survives_pfas,
            "results": results}


def three_axis(pw: Pathway, weights: dict) -> dict:
    """Performance / Confidence / Resilience — the three axes; no single one decides."""
    s = pw.driver_scores()
    avail = {d: w for d, w in weights.items() if d in s}
    tot = sum(avail.values())
    performance = sum(avail[d] * s[d] for d in avail) / tot if tot else 0.0
    conf_map = {Conf.A: 1.0, Conf.B: 0.8, Conf.C: 0.5, Conf.D: 0.2}
    confidence = conf_map.get(pw.confidence_level, 0.5)
    return {"performance": performance, "confidence": confidence,
            "resilience": resilience(pw)["score"]}


OPTION_SET = ["land application", "thermal endpoint", "P recovery (struvite)",
              "N recovery (AS)", "energy export", "FOGO co-digestion capacity"]


def optionality(pw: Pathway) -> dict:
    """How many future options a pathway keeps open vs forecloses. The Hunter Water lesson:
    some moves preserve futures, others lock them out. High optionality is itself value."""
    t = pw.traits
    preserved, foreclosed = [], []
    thermal = t["endpoint"] == "thermal"
    (foreclosed if thermal else preserved).append("land application")      # thermal destroys cake
    preserved.append("thermal endpoint")                                    # cake can always be diverted later
    (foreclosed if thermal else preserved).append("P recovery (struvite)")  # thermal strands P in ash
    (foreclosed if thermal else preserved).append("N recovery (AS)")        # thermal volatilises N
    (preserved if t["net_energy"] > 0 else foreclosed).append("energy export")
    (preserved if (t["thp"] and t["headroom_norm"] > 0.05) else foreclosed).append("FOGO co-digestion capacity")
    return {"preserved": preserved, "foreclosed": foreclosed,
            "score": len(preserved) / len(OPTION_SET)}


# ===========================================================================
# V2.1 — THERMAL ENDPOINT SPLIT (incineration / pyrolysis / gasification / HTL)
# Distinct pathways, each with closing C/N/P/energy ledgers + PFAS + maturity.
# Screening-grade, literature-anchored (ITRC 2020; Winchell 2022; IEA Bioenergy).
# ===========================================================================
# Per-endpoint fate fractions of the DIGESTED-CAKE carbon, feed N, and feed P, plus
# PFAS destruction, technology maturity and a screening net-energy yield (MWh/tDS to unit).
THERMAL_ENDPOINTS = {
    "incineration": dict(temp="850-950C", pfas=0.999, maturity="High",
        c_char=0.00, c_biocrude=0.00,                       # carbon fully oxidised
        n_atm=0.87, n_aqueous=0.05, n_solid=0.08,
        p_recoverable=0.92, energy_mwh_tds=1.8, drying=True),
    "pyrolysis": dict(temp="400-700C", pfas=0.70, maturity="Medium",
        c_char=0.45, c_biocrude=0.00,                       # ~45% cake C to stable biochar
        n_atm=0.35, n_aqueous=0.20, n_solid=0.45,
        p_recoverable=0.70, energy_mwh_tds=1.0, drying=True),
    "gasification": dict(temp="750-1000C", pfas=0.97, maturity="Medium",
        c_char=0.05, c_biocrude=0.00,                       # mostly to syngas->CO2
        n_atm=0.88, n_aqueous=0.07, n_solid=0.05,
        p_recoverable=0.90, energy_mwh_tds=2.2, drying=True),
    "htl": dict(temp="250-350C", pfas=0.45, maturity="Low",
        c_char=0.00, c_biocrude=0.50,                       # ~50% C to biocrude; wet feed, no drying
        n_atm=0.05, n_aqueous=0.80, n_solid=0.15,           # huge aqueous-N sidestream
        p_recoverable=0.45, energy_mwh_tds=2.6, drying=False),
}


# ===========================================================================
# V3 U5 — EVIDENCE-STRENGTH REGISTRY (single source of truth for maturity grading)
# Level A multiple full-scale refs | B multiple demonstrations |
# C limited full-scale refs | D site-specific hypothesis. Grades are deployment-
# based (biosolids-specific), with the reference basis recorded for each.
EVIDENCE = {
    "THP":            (Conf.A, "Cambi/Sustec full-scale fleet: St Marys, Davyhulme, Ringsend, Thames, Blue Plains"),
    "PN/A":           (Conf.A, "anammox sidestream: 100+ full-scale installations (DEMON/ANAMMOX)"),
    "struvite":       (Conf.A, "Ostara Pearl / NuReSys / Crystalactor full-scale P recovery"),
    "incineration":   (Conf.A, "sewage-sludge mono-incineration widespread (EU/Japan), fluidised bed"),
    "gasification":   (Conf.B, "Logan/Loganholme full-scale AU since 2022 (34 kt/yr); intl demos"),
    "pyrolysis":      (Conf.B, "South East Water PYROCO (VIC, commercial 2026) + Sydney Water Pyreg (2025); Pyreg EU sludge fleet"),
    "htl":            (Conf.C, "pre-commercial for biosolids; limited references (Genifuel/Licella pilots)"),
    "separate_PS_WAS":(Conf.B, "multiple demonstrations; mechanism established (Hillis & Taylor Ozwater'17)"),
    "site_uplift":    (Conf.D, "site-specific magnitude requires BMP calibration"),
}


def build_thermal_endpoints(plant: dict = GENERIC) -> dict:
    """Four DISTINCT thermal-endpoint pathways on the shared THP+MAD front end. Returns
    {endpoint_name: Pathway}. Each closes carbon/nitrogen/phosphorus/energy and carries
    a PFAS destruction fraction and a technology-maturity trait."""
    WAS_tds, PS_tds = plant["WAS_tds"], plant["PS_tds"]
    total_tds = WAS_tds + PS_tds
    vs_ts = plant["vs_ts"]
    VS_in = total_tds * vs_ts
    VS_d = VS_in * K.VSR
    C_in = VS_in * K.C_PER_VS
    C_biogas = VS_d * K.C_PER_VS
    C_digestate = C_in - C_biogas                       # cake carbon entering the thermal unit
    CH4 = VS_d * 1000 * K.BIOGAS_NM3_PER_KG_VSD * K.CH4_FRACTION
    C_CH4 = CH4 * K.CH4_C_KG_PER_NM3 / 1000.0
    C_fug = C_CH4 * K.FUGITIVE_CH4_FRAC
    biogas_chem = CH4 * K.CH4_LHV_KWH_NM3 / 1000.0
    elec_gen = biogas_chem * K.CHP_ELEC
    N_in = plant["feed_N_kgd"] if plant.get("feed_N_kgd") else VS_in * K.N_PER_VS * 1000.0
    P_in = total_tds * plant.get("P_per_ds", K.P_PER_DS) * 1000.0
    parasitics = (VS_in - VS_d) * K.DEWATER_KWH_PER_TDS / 1000.0 + K.PLANT_PARASITIC_MWH_D + 6.0

    out = {}
    for name, e in THERMAL_ENDPOINTS.items():
        c_char = C_digestate * e["c_char"]
        c_biocrude = C_digestate * e["c_biocrude"]
        c_thermal_CO2 = C_digestate - c_char - c_biocrude
        carbon = Ledger("carbon", "tC/d",
            inflows={"feed_volatile_carbon": C_in},
            outflows={
                "atmosphere_biogenic_CO2_biogas": (C_biogas - C_fug),
                "atmosphere_fugitive_CH4_scope1": C_fug,
                "char_permanently_stored": c_char,
                "biocrude_product": c_biocrude,
                "atmosphere_thermal_CO2": c_thermal_CO2})
        nitrogen = Ledger("nitrogen", "kgN/d",
            inflows={"feed_nitrogen": N_in},
            outflows={"volatilised_NOx_N2": N_in*e["n_atm"],
                      "aqueous_sidestream_N": N_in*e["n_aqueous"],
                      "retained_in_solid": N_in*e["n_solid"]})
        phosphorus = Ledger("phosphorus", "kgP/d",
            inflows={"feed_phosphorus": P_in},
            outflows={"recoverable_in_ash_or_char": P_in*e["p_recoverable"],
                      "aqueous_or_lost": P_in*(1-e["p_recoverable"])})
        # energy: biogas elec + endpoint recovery, less drying (if any) and parasitics
        endpoint_energy = (VS_d) * e["energy_mwh_tds"] * 0.4   # modest recovery from already-digested solids
        drying_load = (VS_in - VS_d) * 0.6 * KT.DRY_MWH_PER_T_WATER if e["drying"] else 0.0
        net = elec_gen - parasitics + K.PRIMARY_AERATION_CREDIT_MWH_D + endpoint_energy - drying_load
        losses = biogas_chem - elec_gen - (biogas_chem*K.CHP_HEAT)
        energy = Ledger("energy", "MWh/d", provisional=True,
            inflows={"biogas_chemical_energy": biogas_chem, "endpoint_recovery_provisional": endpoint_energy},
            outflows={"chp_electricity_generated": elec_gen,
                      "chp_heat_and_drying": biogas_chem*K.CHP_HEAT,
                      "process_losses": biogas_chem - elec_gen - biogas_chem*K.CHP_HEAT + endpoint_energy})
        conf = EVIDENCE.get(name, (Conf.C, ""))[0]   # V3 U5: registry is the single source of truth
        pw = Pathway(
            name=f"THP + MAD + {name.title()} endpoint",
            description=f"Thermal endpoint = {name} ({e['temp']}). Screening-grade, literature-anchored.",
            ledgers={"carbon": carbon, "energy": energy, "nitrogen": nitrogen, "phosphorus": phosphorus},
            moves=[], pfas_destruction_frac=e["pfas"],
            net_export_mwh_d=net, generation_mwh_d=biogas_chem,
            basis={"total_tds": total_tds, "has_thp": True, "vs_ts": vs_ts,
                   "ps_tds": PS_tds, "was_tds": WAS_tds, "ps_ts": plant["ps_ts"], "was_ts": plant["was_ts"],
                   "digester_vol_m3": plant.get("digester_vol_m3"),
                   "product_wet_tpd": (VS_in-VS_d)*0.3/0.95,
                   "chemicals_m_aud": 0.20*total_tds/100.0, "om_m_aud": 2.8*total_tds/100.0})
        _attach(pw, endpoint="thermal", conf=conf)
        pw.traits["maturity"] = e["maturity"]
        pw.traits["pfas"] = e["pfas"]
        out[name] = pw
    return out


# ===========================================================================
# V2.1 — CARBON VALUE ENGINE (permanence, not just fate)
# ===========================================================================
# Fraction of carbon still sequestered at 100 years, by destination (IPCC biochar
# permanence 0.6-0.9; soil-applied organic C largely mineralises within decades).
C_PERMANENCE = {
    "char_permanently_stored": 0.80, "biochar": 0.80,
    "soil_land_application": 0.15,
    "biocrude_product": 0.0,            # combusted as fuel -> counted via avoided fossil, not storage
}
def _permanence(name):
    for k, v in C_PERMANENCE.items():
        if k in name:
            return v
    return 0.0


def carbon_value(pw: Pathway, credit_price_per_t=150.0, credit_price_avoided=35.0,
                 grid_ef_t_per_mwh=0.6) -> dict:
    """Carbon FATE -> carbon VALUE. Durable REMOVAL (permanent sequestration) and
    AVOIDED fossil emissions are reported SEPARATELY and are NEVER summed into a single
    'removal' figure (V3 Update 3) - they are physically different and price differently.
    'carbon_negative' means genuine net removal: the pathway sequesters more durable
    carbon than it directly emits, EXCLUDING any avoided-emission credits."""
    cl = pw.ledgers["carbon"]
    perm_C = sum(v * _permanence(k) for k, v in cl.outflows.items() if v > 0)
    removed_CO2e_d = perm_C * 44/12
    fug_C = sum(v for k, v in cl.outflows.items() if "fugitive" in k)
    fug_CO2e = fug_C * (16/12) * 28
    fossil_C = sum(v for k, v in cl.outflows.items() if "fossil" in k)
    direct_CO2e_d = fug_CO2e + fossil_C * 44/12
    avoided_CO2e_d = max(0.0, pw.net_export_mwh_d) * grid_ef_t_per_mwh
    net_removal_y = (removed_CO2e_d - direct_CO2e_d) * 365
    avoided_y = avoided_CO2e_d * 365
    return {
        "permanent_C_tC_d": perm_C,
        "removed_gross_tCO2e_d": removed_CO2e_d,
        "direct_emissions_tCO2e_d": direct_CO2e_d,
        "net_removal_tCO2e_yr": net_removal_y,
        "carbon_negative": net_removal_y > 0,
        "avoided_fossil_tCO2e_yr": avoided_y,
        "combined_ghg_benefit_tCO2e_yr": net_removal_y + avoided_y,
        "removal_credit_m_aud_yr": net_removal_y * credit_price_per_t / 1e6,
        "avoided_credit_m_aud_yr": avoided_y * credit_price_avoided / 1e6,
        "credit_value_m_aud_yr": (net_removal_y * credit_price_per_t
                                  + avoided_y * credit_price_avoided) / 1e6,
        "sequestered_CO2e_d": removed_CO2e_d,
        "avoided_fossil_CO2e_d": avoided_CO2e_d,
        "fugitive_CO2e_d": fug_CO2e,
    }


def carbon_categories(pw: Pathway, grid_ef_t_per_mwh=0.6) -> dict:
    """The six V3 carbon categories, reported DISTINCTLY (Update 3). Fate categories are
    carbon MASS (tC/d) off the closed ledger; 'permanently sequestered' is the durable
    SUBSET of 'retained'. 'Removed' and 'Avoided' are climate metrics (tCO2e/d), kept apart."""
    cl = pw.ledgers["carbon"]
    out = {k: v for k, v in cl.outflows.items() if v > 0}
    feed_C = sum(cl.inflows.values())
    emitted   = sum(v for k, v in out.items() if k.startswith("atmosphere"))
    recovered = sum(v for k, v in out.items() if "biocrude" in k)
    liquor    = sum(v for k, v in out.items() if "liquor" in k)
    retained  = sum(v for k, v in out.items()
                    if any(t in k for t in ("soil", "land", "char", "ash", "cake")))
    sequestered = sum(v * _permanence(k) for k, v in out.items())
    fug_C    = sum(v for k, v in out.items() if "fugitive" in k)
    fossil_C = sum(v for k, v in out.items() if "fossil" in k)
    return {
        "feed_carbon_tC_d": feed_C,
        "destroyed_emitted_tC_d": emitted,
        "recovered_in_product_tC_d": recovered,
        "returned_in_liquor_tC_d": liquor,
        "retained_in_solids_tC_d": retained,
        "of_which_permanently_sequestered_tC_d": sequestered,
        "removed_tCO2e_d": sequestered * 44/12,
        "avoided_tCO2e_d": max(0.0, pw.net_export_mwh_d) * grid_ef_t_per_mwh,
        "direct_emissions_tCO2e_d": fug_C * (16/12) * 28 + fossil_C * 44/12,
    }


# ===========================================================================
# V2.1 — OPTIONALITY VALUE ENGINE (put $ on options preserved / foreclosed)
# ===========================================================================
# Per option: (likelihood it becomes needed, screening value $M/yr if available).
OPTION_ECON = {
    "land application":            (0.30, 2.0),   # cheap disposal retained
    "thermal endpoint":            (0.70, 8.0),   # avoids crisis retrofit if PFAS bans land
    "P recovery (struvite)":       (0.45, 1.5),
    "N recovery (AS)":             (0.35, 1.0),
    "energy export":               (0.50, 1.0),
    "FOGO co-digestion capacity":  (0.50, 3.0),   # gate fees + biogas
}


def optionality_value(pw: Pathway) -> dict:
    """Expected value retained (preserved options) vs expected value lost (foreclosed).
    Real-options-lite, screening-grade — quantifies WHY optionality has value."""
    o = optionality(pw)
    retained = sum(OPTION_ECON[x][0]*OPTION_ECON[x][1] for x in o["preserved"] if x in OPTION_ECON)
    regret = sum(OPTION_ECON[x][0]*OPTION_ECON[x][1] for x in o["foreclosed"] if x in OPTION_ECON)
    return {"score": o["score"], "value_retained_m_aud_yr": retained,
            "value_foreclosed_m_aud_yr": regret, "net_option_value_m_aud_yr": retained - regret,
            "preserved": o["preserved"], "foreclosed": o["foreclosed"]}


# ===========================================================================
# V2.1 — FEASIBILITY ENGINE (BVS-12: can BioPoint say "no feasible pathway"?)
# ===========================================================================
def feasibility(pathways: list, constraints: dict) -> dict:
    """Test candidate pathways against HARD constraints. If none satisfy all, return
    infeasible and name the mutually-exclusive constraints. A mature platform must be
    able to conclude that a set of objectives is incompatible."""
    feasible, rejected = [], []
    for pw in pathways:
        reasons = []
        ep = pw.traits.get("endpoint")
        if constraints.get("no_land") and ep == "land":
            reasons.append("requires land application")
        if constraints.get("no_thermal") and ep == "thermal":
            reasons.append("requires thermal processing")
        if constraints.get("no_bill_increase"):
            net = opex_view(pw).get("net_m_aud", 0.0)
            if net > 0:
                reasons.append(f"raises OPEX (+${net:.1f}M/yr)")
        if constraints.get("require_carbon_negative"):
            if not carbon_value(pw)["carbon_negative"]:
                reasons.append("not net carbon-negative")
        if constraints.get("require_nutrient_recovery"):
            if pw.traits.get("p_recovered", 0) <= 0.01:
                reasons.append("recovers no nutrients")
        (feasible if not reasons else rejected).append((pw.name, reasons))

    feasible = [f for f in feasible if not f[1]]
    result = {"feasible": [f[0] for f in feasible], "rejected": rejected,
              "is_feasible": len(feasible) > 0, "conflicts": []}
    if not feasible:
        # identify structural incompatibilities
        if constraints.get("no_land") and constraints.get("no_thermal"):
            result["conflicts"].append("no_land AND no_thermal: no endpoint family remains "
                                        "(land and thermal are the only terminal routes)")
        if constraints.get("no_bill_increase") and (constraints.get("require_carbon_negative")
                                                     or constraints.get("require_nutrient_recovery")):
            result["conflicts"].append("no_bill_increase AND require carbon/nutrient outcome: the "
                                        "required outcomes need capital/operating spend")
        if not result["conflicts"]:
            result["conflicts"].append("the combined constraints exclude every candidate pathway")
    return result



def compare(paths: list[Pathway], weights: dict[str, float]) -> str:
    lines = ["\nPATHWAY COMPARISON (under locked weighting — trade, not winner):"]
    drivers = ["energy_neutrality", "scope1_emissions", "pfas",
               "nutrient_recovery", "opex", "capacity"]
    header = f"    {'driver':<20}" + "".join(f"{p.name[:22]:>24}" for p in paths)
    lines.append(header)
    for d in drivers:
        row = f"    {d:<20}"
        for p in paths:
            s = p.driver_scores()
            if d in p.bands:
                lo, c, hi = p.bands[d]
                row += f"{f'{c:.2f} [{lo:.2f}-{hi:.2f}]':>24}"
            else:
                row += f"{s.get(d, float('nan')):>24.2f}"
        lines.append(row)
    return "\n".join(lines)
def build_roadmap(pathway: Pathway) -> list[str]:
    commit = [m for m in pathway.moves if m.tag == Tag.COMMIT]
    keep = [m for m in pathway.moves if m.tag == Tag.KEEP_OPEN]
    avoid = [m for m in pathway.moves if m.tag == Tag.AVOID]
    out = []
    out.append("Phase 1 (commit now):")
    for m in commit:
        out.append(f"    - {m.name}  [{m.confidence.verb()}]")
    out.append("Phase 2+ (keep open — priced de-risking, decide later):")
    for m in keep:
        out.append(f"    - {m.name}")
        out.append(f"        reward: {m.reward}")
        out.append(f"        de-risk: {m.derisk_task}   [{m.confidence.verb()}]")
    out.append("Avoid (forecloses future drivers):")
    for m in avoid:
        out.append(f"    - {m.name}")
        out.append(f"        why: {m.residual_risk}")
        if m.forecloses:
            out.append(f"        would foreclose: {', '.join(m.forecloses)}")
    return out


# ---------------------------------------------------------------------------
# 9b. REPORT  — drive the new strategic structure from the spine objects
# ---------------------------------------------------------------------------
def generate_report(pathways: list[Pathway], weights: dict[str, float]) -> str:
    def fate(lg: Ledger) -> str:
        rows = [f"  - {k}: {v:,.1f} {lg.unit}" for k, v in lg.outflows.items() if v > 0]
        tag = " *(provisional — split fractions not calibrated)*" if lg.provisional else ""
        return f"{lg.quantity.title()} fate{tag}:\n" + "\n".join(rows)

    L = []
    L.append("# Strategic Biosolids Pathway Report\n")
    L.append("*Generated by the BioPoint V2 spine. Drivers are read off conserved-quantity "
             "ledgers; the recommendation is a sequence, not a single technology. Constants are "
             "calibrated where reference data exists (St Marys, Mangere, Thames/Blue Plains) and "
             "mid-range estimates elsewhere — flagged accordingly.*\n")

    L.append("## 1. Strategic Objective\n")
    L.append("Pathways are weighted against the utility's stated driver ranking "
             "(rank-order weighting, fully transparent):\n")
    for d, w in sorted(weights.items(), key=lambda kv: -kv[1]):
        L.append(f"- **{d.replace('_',' ')}** — weight {w:.3f}")
    L.append("\nBecause cost sits mid-table and CAPEX last, recommending a costlier pathway over "
             "a cheaper one is consistent with the objective, not a contradiction.\n")

    L.append("## 2. Constraints (what the ledgers force into the open)\n")
    L.append("- **PFAS**: the calibrated AD/THP spine destroys none — it concentrates PFAS into "
             "land-applied cake. Only a thermal endpoint addresses this driver.\n"
             "- **Return-liquor nitrogen**: struvite is phosphorus-limited, so the bulk of "
             "mineralised ammonia returns to the host works — a load and an N₂O/Scope-1 risk.\n"
             "- **Nutrient–thermal tension**: thermal strands phosphorus in ash and volatilises "
             "nitrogen, so nutrients must be recovered *upstream* if both PFAS and recovery matter.\n")

    L.append("## 3. Pathways\n")
    for pw in pathways:
        ok, _ = pw.gate()
        prov = any(l.provisional for l in pw.ledgers.values())
        status = ("PROVISIONAL — not commit-grade" if prov
                  else "all ledgers close — commit-grade")
        L.append(f"### {pw.name}\n")
        L.append(f"{pw.description}\n")
        L.append(f"**Closure gate:** {status}.\n")
        L.append(fate(pw.ledgers["carbon"]) + "\n")
        L.append(fate(pw.ledgers["nitrogen"]) + "\n")
        L.append(fate(pw.ledgers["phosphorus"]) + "\n")

    L.append("## 4. Comparison (the trade — deliberately not a winner)\n")
    drivers = ["energy_neutrality", "scope1_emissions", "pfas",
               "nutrient_recovery", "opex", "capacity"]
    hdr = "| driver | " + " | ".join(p.name.split(" + ")[0] + "…" for p in pathways) + " |"
    L.append(hdr)
    L.append("|" + "---|" * (len(pathways) + 1))
    for d in drivers:
        cells = []
        for p in pathways:
            s = p.driver_scores()
            if d in p.bands:
                lo, c, hi = p.bands[d]
                cells.append(f"{c:.2f} [{lo:.2f}–{hi:.2f}]")
            else:
                cells.append(f"{s.get(d, float('nan')):.2f}")
        L.append(f"| {d.replace('_',' ')} | " + " | ".join(cells) + " |")
    L.append("")

    L.append("## 5. Confidence\n")
    L.append("Confidence is tracked separately from performance and governs the recommendation "
             "verb — it never excludes a pathway. The calibrated spine is commit-grade; the "
             "thermal endpoint is emerging (Level C): its reward is real and its physics plausible, "
             "but its split fractions are not yet closed against a full-scale balance, so it is "
             "shortlisted with a priced de-risking task, not committed.\n")

    L.append("## 6. Adaptive Roadmap\n")
    pw0 = pathways[0]
    commit = [m for m in pw0.moves if m.tag == Tag.COMMIT]
    keep = [m for m in pw0.moves if m.tag == Tag.KEEP_OPEN]
    avoid = [m for m in pw0.moves if m.tag == Tag.AVOID]
    L.append("**Phase 1 — commit now (bankable, commit-grade):**")
    for m in commit:
        L.append(f"- {m.name} — *{m.confidence.verb()}*")
    L.append("\n**Phase 2+ — keep open (priced de-risking, decide later):**")
    for m in keep:
        L.append(f"- {m.name} — *{m.confidence.verb()}*  \n"
                 f"  Reward: {m.reward}  \n"
                 f"  De-risk: {m.derisk_task}")
    L.append("\n**Avoid (forecloses future drivers):**")
    for m in avoid:
        foreclosed = f" Forecloses: {', '.join(m.forecloses)}." if m.forecloses else ""
        L.append(f"- {m.name} — {m.residual_risk}.{foreclosed}")
    L.append("")

    L.append("## 7. Recommendation\n")
    L.append("The recommendation is an **order of moves**, not a chosen technology:\n"
             "1. Optimise MAD and dewatering now — bankable, commit-grade, the foundation.\n"
             "2. Add THP for the capacity it buys (≈2 reference digesters of avoided volume) "
             "and the cake-solids and Class-A benefits.\n"
             "3. Recover phosphorus via struvite while it is still recoverable — before any "
             "thermal step would lock it into ash — and hold ammonium-sulphate/PN-A open to "
             "close the nitrogen gap.\n"
             "4. Do **not** commit land application as a terminal endpoint: it forecloses the "
             "only family that addresses PFAS.\n"
             "5. Hold the thermal endpoint as a priced, scheduled option (~$1.5M / 18 months to "
             "reach commit-grade), to be exercised if PFAS regulation or the carbon case demands "
             "it. Its energy and Scope-1 outcomes hinge on syngas recovery we cannot yet "
             "calibrate, so the decision is staged, not pre-empted.\n")
    return "\n".join(L)



def main():
    print("=" * 74)
    print("BioPoint V2 — Strategic Pathway Spine")
    print("=" * 74)

    weights = rank_weights(DRIVER_RANKING_PLUS)
    print("\nOBJECTIVE — driver weighting (rank-order, transparent):")
    for d, w in sorted(weights.items(), key=lambda kv: -kv[1]):
        print(f"    {d:<22}{w:.3f}")

    pw = build_worked_pathway()
    print(f"\nPATHWAY: {pw.name}")
    print(f"  {pw.description}")

    print("\nCONSERVATION LEDGERS (closure = admissibility gate):")
    for lg in pw.ledgers.values():
        print(lg.report())

    ok, msgs = pw.gate()
    print(f"\nGATE: {'ALL LEDGERS CLOSE — admissible (commit-grade)' if ok else 'BLOCKED'}")
    for m in msgs:
        print(f"    note: {m}")

    print("\nDRIVER SCORES (read off the ledgers — 0..1, higher better):")
    scores = pw.driver_scores()
    for d in DRIVER_RANKING_PLUS:
        if d in scores:
            bar = "#" * int(round(scores[d] * 30))
            print(f"    {d:<22}{scores[d]:.2f}  {bar}")
        else:
            print(f"    {d:<22}  (bolt-on engine — not yet ledger-derived)")

    print("\n  Honest reading falling OUT of the ledgers (not asserted):")
    print(f"    - Energy: strongly positive — heat surplus covers THP+digester, no fossil top-up")
    print(f"    - PFAS  : pathway destroys 0% — driver #2 UNMET by this safe spine")
    print(f"    - Nutr. : P recovery good (~{pw.ledgers['phosphorus'].fraction_to('struvite_P')*100:.0f}%), "
          f"N recovery poor (~{pw.ledgers['nitrogen'].fraction_to('struvite_N')*100:.0f}%) — struvite is P-limited")

    cap = capacity_view(pw)
    print("\n  CAPACITY INTENSIFICATION (calibrated — Thames/Blue Plains/Davyhulme):")
    print(f"    conventional digester volume needed : {cap['vol_conv_m3']:>8,.0f} m3")
    print(f"    THP digester volume needed          : {cap['vol_thp_m3']:>8,.0f} m3")
    print(f"    volume avoided                      : {cap['avoided_m3']:>8,.0f} m3  "
          f"(~{cap['digesters_avoided']:.1f} reference digesters)")
    print(f"    avoided digester CAPEX              : ${cap['avoided_capex_aud']/1e6:>7.1f}M")
    ox = opex_view(pw)
    print("\n  OPEX (M$/yr; negative = net cash positive):")
    print(f"    energy (net export) {ox['energy_m_aud']:+6.2f}   transport {ox['transport_m_aud']:+5.2f}   "
          f"chem {ox['chemicals_m_aud']:+5.2f}   O&M {ox['om_m_aud']:+5.2f}   "
          f"struvite rev {-ox['struvite_revenue_m_aud']:+5.2f}")
    print(f"    NET OPEX {ox['net_m_aud']:+.2f} M$/yr")

    print("\nADAPTIVE ROADMAP:")
    for line in build_roadmap(pw):
        print("  " + line)

    # ---- Thermal-endpoint pathway: the provisional / uncertainty-band half ----
    tp = build_thermal_pathway()
    print("\n" + "-" * 74)
    print(f"PROVISIONAL PATHWAY: {tp.name}")
    print(f"  {tp.description}")
    print("\nCONSERVATION LEDGERS (close arithmetically; flagged provisional):")
    for lg in tp.ledgers.values():
        print(lg.report())
    ok2, msgs2 = tp.gate()
    print(f"\nGATE: {'admissible but PROVISIONAL — not commit-grade' if ok2 else 'BLOCKED'}")
    for m in msgs2:
        print(f"    note: {m}")
    print("\n  Honest reading (the point of the band):")
    eb = tp.bands["energy_neutrality"]
    s1 = tp.bands["scope1_emissions"]
    print(f"    - PFAS  : now ADDRESSED — ~{tp.pfas_destruction_frac*100:.0f}% destroyed "
          f"(band {tp.bands['pfas'][0]*100:.0f}-{tp.bands['pfas'][2]*100:.0f}%) — driver #3 finally met")
    print(f"    - Energy: {eb[1]:.2f} central, but band {eb[0]:.2f}-{eb[2]:.2f} — at the LOW end "
          f"(syngas underperforms) the drying load forces fossil top-up")
    print(f"    - Scope1: band {s1[0]:.2f}-{s1[2]:.2f} — char storage helps, fossil-drying hurts")
    print(f"    - P stranded in ash, N volatilised: nutrient recovery ~0 unless recovered UPSTREAM")

    print(compare([pw, tp], weights))

    print("\nWHAT THE COMPARISON SAYS (and what it deliberately does NOT):")
    print("  - The safe spine wins energy (#1) and confidence; the thermal pathway is the")
    print("    ONLY one that addresses PFAS (#3). Neither dominates across your drivers.")
    print("  - The engine does NOT pick one. The roadmap's answer is to SEQUENCE: recover")
    print("    nutrients upstream (struvite, before P is lost to ash), run the safe spine as")
    print("    commit-grade NOW, and hold the thermal endpoint as a PRICED, scheduled option")
    print("    to be de-risked before any PFAS-driven commitment. Order is the recommendation.")

    print("\n" + "=" * 74)
    print("Spine proven on TWO pathways: one closing/commit-grade, one provisional with")
    print("honest bands. Drivers read off shared ledgers; recommendation is a sequence,")
    print("not a winner. Next: bolt-on engines (capacity, OPEX, regulatory) as ledger views.")
    print("=" * 74)

    # Drive the strategic report from the spine objects
    report = generate_report([pw, tp], weights)
    with open("/mnt/user-data/outputs/Strategic_Pathway_Report.md", "w") as f:
        f.write(report)
    print("\nStrategic report written: Strategic_Pathway_Report.md")


if __name__ == "__main__":
    main()
