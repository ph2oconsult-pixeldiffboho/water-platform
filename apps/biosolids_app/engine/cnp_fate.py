"""
engine/cnp_fate.py
BioPoint V1 — Carbon, Nitrogen and Phosphorus Fate Analysis Engine

Tracks the fate of C, N and P through the biosolids treatment train,
from incoming sludge to all output streams (gaseous, liquid, solid).

Physics basis
─────────────
Each technology is described by partition coefficients (dimensionless
fractions 0–1) that distribute each element between output streams.
Coefficients are drawn from:
  - WEF MOP 36 (2012)
  - Metcalf & Eddy 5th ed (2014)
  - Batstone et al. (2002) ADM1 parameterisations
  - WERF LCA of Biosolids (2011)
  - Kelessidis & Stasinakis (2012) — comparative review
  - Literature on THP (Cambi, Haarstad 2012; Meunier 2020)

All partition coefficients are at the midpoint of the literature range.
Uncertainty is noted as a fraction of the midpoint value.

ph2o Consulting — v25B02
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Optional


# ── Sludge composition defaults ────────────────────────────────────────────
# Expressed as fraction of dry solids (DS)
# Primary sludge and WAS have different compositions

SLUDGE_COMPOSITION = {
    # Carbon fraction of DS (VS × organic carbon content of VS ≈ 0.50–0.55)
    "c_frac_ps":    0.52,   # kg C / kg DS  (PS: higher VS fraction)
    "c_frac_was":   0.44,   # kg C / kg DS  (WAS: lower C/VS ratio due to protein)
    # Nitrogen fraction of DS
    "n_frac_ps":    0.035,  # kg N / kg DS  (PS: ~3.5% N)
    "n_frac_was":   0.085,  # kg N / kg DS  (WAS: ~8.5% N, high protein content)
    # Phosphorus fraction of DS
    "p_frac_ps":    0.012,  # kg P / kg DS  (PS: ~1.2%)
    "p_frac_was":   0.030,  # kg P / kg DS  (WAS: ~3% P, bio-P enrichment)
}


# ── Technology partition coefficients ──────────────────────────────────────
#
# For each technology and element (C, N, P), the fractions to each output:
#   "biogas_ch4"    : to methane (energy)
#   "biogas_co2"    : to CO2 in biogas (biogenic)
#   "fugitive_ch4"  : fugitive methane losses
#   "digestate_sol" : to dewatered cake solids
#   "digestate_liq" : to centrate / filtrate (liquid stream)
#   "atm_n2o"       : to N2O emissions (N only)
#   "atm_nh3"       : to NH3 volatilisation (N only)
#   "thermal_co2"   : to CO2 from combustion / thermal treatment
#   "thermal_char"  : to char / ash residual (pyrolysis, gasification)
#   "thermal_liq"   : to HTL aqueous product
#   "soil_seq"      : long-term C sequestration in soil (land application)
#
# Fractions MUST sum to 1.0 for each element × technology combination.
# Where <1.0, the residual is assumed to be in "digestate_sol".
#
# All fractions are fractions of INCOMING element load to that technology.

TECH_PARTITIONS: Dict[str, Dict[str, Dict[str, float]]] = {

    # ── Conventional mesophilic anaerobic digestion (MAD) ──────────────────
    "base": {
        "C": {
            "biogas_ch4":    0.30,   # ~30% of C → CH4 (VSR 60%, yield 0.35 m3/kgVS)
            "biogas_co2":    0.18,   # ~18% → CO2 in biogas
            "fugitive_ch4":  0.010,  # ~1% fugitive (IPCC 2006 WW default)
            "digestate_sol": 0.50,   # retained in cake
            "digestate_liq": 0.010,  # dissolved organics in centrate (low)
            "soil_seq":      0.00,   # applied to land — no direct seq credit here
        },
        "N": {
            "digestate_liq": 0.70,   # ~70% mineralised → NH4-N in centrate
            "digestate_sol": 0.25,   # ~25% in dewatered cake (organic N)
            "atm_n2o":       0.010,  # N2O from land application (applied to cake N)
            "atm_nh3":       0.005,  # NH3 volatilisation from digester cover
            "atm_n2":        0.035,   # N2 from denitrification / unaccounted losses
        },
        "P": {
            "digestate_sol": 0.85,   # ~85% in dewatered cake
            "digestate_liq": 0.15,   # ~15% in centrate (phosphate release)
        },
    },

    # ── Separate PS/WAS digestion ───────────────────────────────────────────
    # Biogas uplift comes from PS VSR improvement.
    # N partition similar to MAD but slightly lower centrate load
    # (WAS HRT optimised so less protein over-hydrolysis).
    "separate": {
        "C": {
            "biogas_ch4":    0.38,   # higher due to improved PS VSR
            "biogas_co2":    0.22,
            "fugitive_ch4":  0.010,
            "digestate_sol": 0.38,
            "digestate_liq": 0.010,
            "soil_seq":      0.00,
        },
        "N": {
            "digestate_liq": 0.65,   # slightly lower — WAS HRT optimised
            "digestate_sol": 0.28,
            "atm_n2o":       0.010,
            "atm_nh3":       0.005,
            "atm_n2":        0.055,   # N2 from denitrification / unaccounted losses
        },
        "P": {
            "digestate_sol": 0.83,
            "digestate_liq": 0.17,
        },
    },

    # ── Separate PS/WAS + THP on WAS stream ────────────────────────────────
    "separate_thp": {
        "C": {
            "biogas_ch4":    0.40,
            "biogas_co2":    0.24,
            "fugitive_ch4":  0.010,
            "digestate_sol": 0.34,
            "digestate_liq": 0.010,
            "soil_seq":      0.00,
        },
        "N": {
            "digestate_liq": 0.75,   # THP increases N mineralisation
            "digestate_sol": 0.18,
            "atm_n2o":       0.010,
            "atm_nh3":       0.010,  # THP increases NH3 in steam condensate
            "atm_n2":        0.050,   # N2 from denitrification / unaccounted losses
        },
        "P": {
            "digestate_sol": 0.82,
            "digestate_liq": 0.18,
        },
    },

    # ── SolidStream (post-digestion THP) ───────────────────────────────────
    # THP applied after digestion — primary effect is dewatering improvement
    # Biogas uplift from hot centrate recycle improving digester performance
    "solidstream": {
        "C": {
            "biogas_ch4":    0.32,
            "biogas_co2":    0.19,
            "fugitive_ch4":  0.010,
            "digestate_sol": 0.46,
            "digestate_liq": 0.010,
            "soil_seq":      0.00,
        },
        "N": {
            "digestate_liq": 0.72,
            "digestate_sol": 0.20,
            "atm_n2o":       0.010,
            "atm_nh3":       0.010,
            "atm_n2":        0.060,   # N2 from denitrification / unaccounted losses
        },
        "P": {
            "digestate_sol": 0.80,
            "digestate_liq": 0.20,
        },
    },

    # ── Pre-digestion THP ──────────────────────────────────────────────────
    # THP before digestion — increases biodegradability, VSR, biogas yield
    # Also increases N mineralisation significantly
    "pre_thp": {
        "C": {
            "biogas_ch4":    0.35,
            "biogas_co2":    0.21,
            "fugitive_ch4":  0.010,
            "digestate_sol": 0.42,
            "digestate_liq": 0.010,
            "soil_seq":      0.00,
        },
        "N": {
            "digestate_liq": 0.78,   # THP strongly increases N mineralisation
            "digestate_sol": 0.15,
            "atm_n2o":       0.010,
            "atm_nh3":       0.015,
            "atm_n2":        0.045,   # N2 from denitrification / unaccounted losses
        },
        "P": {
            "digestate_sol": 0.79,
            "digestate_liq": 0.21,
        },
    },

    # ── Recuperative thickening ─────────────────────────────────────────────
    "recup": {
        "C": {
            "biogas_ch4":    0.31,
            "biogas_co2":    0.18,
            "fugitive_ch4":  0.010,
            "digestate_sol": 0.49,
            "digestate_liq": 0.010,
            "soil_seq":      0.00,
        },
        "N": {
            "digestate_liq": 0.68,
            "digestate_sol": 0.25,
            "atm_n2o":       0.010,
            "atm_nh3":       0.005,
            "atm_n2":        0.055,   # N2 from denitrification / unaccounted losses
        },
        "P": {
            "digestate_sol": 0.84,
            "digestate_liq": 0.16,
        },
    },

    # ── Pyrolysis (slow, 400–500°C) — STUB coefficients ────────────────────
    # No digestion — direct thermal conversion
    # Literature: Lehmann & Joseph 2009; Ro et al. 2010
    "pyrolysis": {
        "C": {
            "biogas_ch4":    0.00,
            "biogas_co2":    0.05,   # incomplete combustion CO2 in syngas
            "fugitive_ch4":  0.00,
            "thermal_char":  0.35,   # biochar — stable solid product
            "thermal_co2":   0.05,   # stack CO2 (non-energy syngas losses)
            "syngas_energy": 0.20,   # syngas combusted → heat/power (energy utilisation)
            "digestate_sol": 0.00,
            "digestate_liq": 0.00,
            "soil_seq":      0.35,   # biochar land-applied → long-term C store
        },
        "N": {
            "thermal_char":  0.30,   # N in char (low bioavailability)
            "digestate_liq": 0.20,   # condensate N
            "atm_n2o":       0.05,
            "atm_nh3":       0.30,   # NH3 in pyrolysis gas
            "digestate_sol": 0.15,
        },
        "P": {
            "thermal_char":  0.70,   # P concentrated in char
            "digestate_liq": 0.10,
            "digestate_sol": 0.20,
        },
    },

    # ── Hydrothermal liquefaction (HTL) — STUB coefficients ────────────────
    # Literature: Biller & Ross 2011; Elliott et al. 2015
    "htl": {
        "C": {
            "biogas_ch4":    0.00,
            "biogas_co2":    0.08,
            "thermal_char":  0.10,   # HTL char
            "thermal_liq":   0.50,   # bio-crude oil
            "digestate_liq": 0.15,   # aqueous product
            "digestate_sol": 0.17,
            "soil_seq":      0.00,
        },
        "N": {
            "digestate_liq": 0.72,   # aqueous product — very high NH4-N load
            "thermal_liq":   0.08,   # N in bio-crude (low, mostly organic N)
            "thermal_char":  0.05,   # N in HTL char
            "digestate_sol": 0.10,   # N in solid residual (if any)
            "atm_n2o":       0.02,   # N2O from aqueous product treatment
            "atm_n2":        0.03,   # N2 from partial oxidation during HTL
        },
        "P": {
            "thermal_char":  0.15,
            "digestate_liq": 0.55,   # aqueous product
            "digestate_sol": 0.30,
        },
    },

    # ── Gasification (750–1000°C, partial oxidation) ─────────────────────────
    # Literature: Dogru et al. 2002; GTC 2015; Werther & Ogada 1999
    "gasification": {
        "C": {
            "wte_energy":    0.65,   # syngas → electricity (net, after dryer parasitic)
            "thermal_co2":   0.15,   # CO2 in syngas + incomplete combustion
            "thermal_char":  0.18,   # vitrified ash/slag C residual
            "fugitive_ch4":  0.02,   # fugitive from gasifier seals
            "biogas_ch4":    0.00,
            "digestate_sol": 0.00,
            "digestate_liq": 0.00,
            "soil_seq":      0.00,
        },
        "N": {
            "atm_nox":       0.65,   # syngas NOx (treated by SCR/SNCR)
            "atm_n2":        0.15,   # N2 from partial oxidation
            "atm_n2o":       0.03,   # N2O (minor at high temp)
            "atm_nh3":       0.05,   # NH3 in syngas (removed by scrubber)
            "digestate_liq": 0.07,   # scrubber liquor N
            "thermal_char":  0.05,   # N in slag (low, non-volatile)
        },
        "P": {
            "thermal_char":  0.90,   # P concentrated in slag — very high recovery
            "digestate_liq": 0.10,   # minor loss to scrubber water
        },
    },

        # ── Incineration (MSWI-style, with energy recovery) — STUB ─────────────
    # Literature: Werther & Ogada 1999; WtE industry data
    "incineration": {
        "C": {
            "wte_energy":    0.72,   # biogenic C → heat/power in WtE (energy utilisation)
            "thermal_co2":   0.13,   # stack CO2 losses (incomplete recovery, ~85% WtE eff.)
            "thermal_char":  0.10,   # bottom ash / fly ash C (P recovery potential)
            "fugitive_ch4":  0.00,
            "biogas_ch4":    0.00,
            "digestate_sol": 0.00,
            "digestate_liq": 0.00,
            "soil_seq":      0.00,
            "biogas_co2":    0.05,   # flue gas treatment losses
        },
        "N": {
            "atm_nox":       0.70,   # organic N → NOx at 850°C (to atmosphere)
            "atm_n2":        0.10,   # N2 from complete oxidation
            "atm_n2o":       0.05,   # N2O from incomplete combustion
            "atm_nh3":       0.02,   # NH3 (trace, after flue gas treatment)
            "digestate_liq": 0.05,   # scrubber/wet scrubber liquor N
            "thermal_char":  0.08,   # N in bottom ash (low, non-volatile fraction)
        },
        "P": {
            "thermal_char":  0.95,   # P concentrated in ash — recoverable
            "digestate_liq": 0.05,
        },
    },
}


# ── Downstream fate of digestate (land application) ────────────────────────
# After dewatering, biosolids are land-applied, composted, or stockpiled.
# These additional partitions apply to the cake solid fraction.
LAND_APPLICATION_C_SEQ = 0.20   # fraction of cake C sequestered long-term in soil
LAND_APPLICATION_N2O   = 0.01   # fraction of cake N → N2O (IPCC EF1 = 1%)
LAND_APPLICATION_NH3   = 0.05   # fraction of cake N → NH3 volatilisation


# ── PFAS fate partition coefficients ──────────────────────────────────────
#
# PFAS fate by technology is expressed as fraction of incoming PFAS that is:
#   "retained"   : PFAS remains in biosolids/digestate (land application risk)
#   "destroyed"  : PFAS mineralized (defluorination) — net destruction
#   "transferred": PFAS transferred to centrate/liquid stream (WTP risk)
#   "volatilised": PFAS lost to atmosphere (air emissions)
#   "partitioned": PFAS distributed to char/ash product
#   "concentrated": PFAS concentrated in a specific output stream
#
# Basis: ITRC PFAS Technical Overview (2020), Rahman et al. (2014),
#   Sorengard et al. (2019), Winchell et al. (2022), USEPA 2020 WRF 5033.
#
# Confidence levels:
#   MAD/THP: Medium (multiple facility data available)
#   Pyrolysis/HTL: Low (limited pilot data, highly feedstock-dependent)
#   Gasification/Incineration: Medium-High (higher temperature ensures DRE)
#
# All destruction fractions are fraction of INCOMING PFAS destroyed.
# DRE = Destruction and Removal Efficiency (%)

PFAS_FATE: dict[str, dict[str, float]] = {
    # Conventional MAD — PFAS largely retained in biosolids
    # Literature: Higgins et al. 2005; Sepulvado et al. 2011
    "base": {
        "retained":    0.85,   # in dewatered cake
        "transferred": 0.12,   # to centrate
        "volatilised": 0.01,
        "destroyed":   0.00,   # anaerobic digestion does not destroy PFAS
        "partitioned": 0.00,
        "concentrated":0.02,   # in foam/scum
    },
    # THP (pre or post) — slightly more to centrate from increased solubilisation
    # Literature: Clarke et al. 2015; Winchell et al. 2022
    "pre_thp": {
        "retained":    0.78,
        "transferred": 0.18,   # hydrolysis increases liquid-phase PFAS
        "volatilised": 0.01,
        "destroyed":   0.00,
        "partitioned": 0.00,
        "concentrated":0.03,
    },
    "solidstream": {
        "retained":    0.80,
        "transferred": 0.16,
        "volatilised": 0.01,
        "destroyed":   0.00,
        "partitioned": 0.00,
        "concentrated":0.03,
    },
    "separate": {
        "retained":    0.83,
        "transferred": 0.14,
        "volatilised": 0.01,
        "destroyed":   0.00,
        "partitioned": 0.00,
        "concentrated":0.02,
    },
    "separate_thp": {
        "retained":    0.77,
        "transferred": 0.19,
        "volatilised": 0.01,
        "destroyed":   0.00,
        "partitioned": 0.00,
        "concentrated":0.03,
    },
    "recup": {
        "retained":    0.84,
        "transferred": 0.13,
        "volatilised": 0.01,
        "destroyed":   0.00,
        "partitioned": 0.00,
        "concentrated":0.02,
    },
    # Pyrolysis — partial destruction, depends on temperature and time
    # >700°C: high DRE; 400–500°C: significant PFAS in pyrolysis gas/condensate
    # Literature: Winchell et al. 2022; Sörengård et al. 2019
    "pyrolysis": {
        "retained":    0.05,   # char residual
        "transferred": 0.10,   # condensate
        "volatilised": 0.20,   # pyrolysis gas (if not fully combusted)
        "destroyed":   0.55,   # thermal defluorination at >500°C
        "partitioned": 0.10,   # concentrated in char
        "concentrated":0.00,
    },
    # Gasification (>750°C) — near-complete PFAS destruction
    # Literature: ITRC 2020; Winchell et al. 2022
    "gasification": {
        "retained":    0.02,
        "transferred": 0.01,   # scrubber liquor
        "volatilised": 0.01,   # syngas pre-combustion (treated)
        "destroyed":   0.97,   # high-temperature mineralisation >750°C
        "partitioned": 0.00,
        "concentrated":0.00,
    },
        # HTL — PFAS distributed between bio-crude, aqueous product, and char
    # Aqueous product has high PFAS load requiring treatment
    # Literature: Elliott et al. 2015; limited PFAS data
    "htl": {
        "retained":    0.05,
        "transferred": 0.40,   # aqueous product — significant PFAS burden
        "volatilised": 0.05,
        "destroyed":   0.30,   # sub-critical water partial mineralisation
        "partitioned": 0.20,   # bio-crude and char
        "concentrated":0.00,
    },
    # Incineration at >850°C — near-complete PFAS destruction
    # EU WI Directive requires >850°C, 2 sec residence time
    # Literature: USEPA 2020; Rahman et al. 2014
    "incineration": {
        "retained":    0.02,
        "transferred": 0.01,   # scrubber liquor
        "volatilised": 0.02,   # flue gas (treated by activated carbon)
        "destroyed":   0.95,   # thermal mineralisation >850°C
        "partitioned": 0.00,
        "concentrated":0.00,
    },
}

# Technology DRE labels for reporting
PFAS_DRE_LABEL: dict[str, str] = {
    "base":         "~0% (retained in biosolids)",
    "pre_thp":      "~0% (retained, increased liquid transfer)",
    "solidstream":  "~0% (retained in biosolids)",
    "separate":     "~0% (retained in biosolids)",
    "separate_thp": "~0% (retained, increased liquid transfer)",
    "recup":        "~0% (retained in biosolids)",
    "pyrolysis":    "~55% (temperature-dependent; 400–700°C)",
    "htl":          "~30% (sub-critical water partial mineralisation)",
    "incineration": "~95% (>850°C thermal mineralisation)",
}

# Confidence levels
PFAS_CONFIDENCE: dict[str, str] = {
    "base":         "Medium",
    "pre_thp":      "Low-Medium",
    "solidstream":  "Low-Medium",
    "separate":     "Low-Medium",
    "separate_thp": "Low-Medium",
    "recup":        "Low-Medium",
    "pyrolysis":    "Low",
    "htl":          "Very Low",
    "incineration": "Medium-High",
}


def pfas_fate(config_id: str, pfas_load_ng_per_g: float, ds_kg_d: float
              ) -> dict:
    """
    Estimate PFAS fate for a technology configuration.

    Parameters
    ----------
    config_id         : Technology string
    pfas_load_ng_per_g: PFAS concentration in incoming DS (ng/g = μg/kg DS)
    ds_kg_d           : Total DS feed (kg/day)

    Returns
    -------
    dict with keys: incoming_mg_d, retained_mg_d, destroyed_mg_d,
    transferred_mg_d, destroyed_pct, dre_label, confidence
    """
    fate = PFAS_FATE.get(config_id, PFAS_FATE["base"])
    incoming = pfas_load_ng_per_g * ds_kg_d / 1000   # mg/day (ng/g × kg/d = μg/d = mg/d × 1/1000)
    # Actually: ng/g × kg/d × 1e6 ng/g per kg = ng/g × kg → ng·kg/g → g·ng/g per mg...
    # Simpler: 1 ng/g × 1 kg = 1 μg = 0.001 mg → incoming = load_ng_g × ds_kg_d × 0.001 mg/d
    incoming_mg_d = pfas_load_ng_per_g * ds_kg_d * 0.001   # mg/day

    return {
        "incoming_mg_d":    round(incoming_mg_d, 1),
        "retained_mg_d":    round(incoming_mg_d * fate["retained"],    1),
        "transferred_mg_d": round(incoming_mg_d * fate["transferred"], 1),
        "destroyed_mg_d":   round(incoming_mg_d * fate["destroyed"],   1),
        "destroyed_pct":    fate["destroyed"] * 100,
        "retained_pct":     fate["retained"]  * 100,
        "transferred_pct":  fate["transferred"] * 100,
        "dre_label":        PFAS_DRE_LABEL.get(config_id, "Unknown"),
        "confidence":       PFAS_CONFIDENCE.get(config_id, "Low"),
    }




@dataclass
class CNPInput:
    """Input characterisation for CNP fate analysis."""
    ps_ds_tpd:   float  # Primary sludge, tDS/day
    was_ds_tpd:  float  # WAS, tDS/day
    ps_vs_pct:   float = 72.0   # VS fraction of DS (%)
    was_vs_pct:  float = 68.0   # VS fraction of DS (%)
    ps_n_pct:    float = 3.5    # N fraction of DS (%)
    was_n_pct:   float = 8.5    # N fraction of DS (%)
    ps_p_pct:    float = 1.2    # P fraction of DS (%)
    was_p_pct:   float = 3.0    # P fraction of DS (%)
    land_applied: bool = True   # Whether biosolids are land-applied
    # Override default C fractions if known
    ps_c_pct:    Optional[float] = None   # C fraction of DS (%)
    was_c_pct:   Optional[float] = None

    def total_ds_tpd(self) -> float:
        return self.ps_ds_tpd + self.was_ds_tpd

    def c_in_kg_d(self) -> float:
        ps_c = (self.ps_c_pct or SLUDGE_COMPOSITION["c_frac_ps"] * 100) / 100
        was_c = (self.was_c_pct or SLUDGE_COMPOSITION["c_frac_was"] * 100) / 100
        return (self.ps_ds_tpd * ps_c + self.was_ds_tpd * was_c) * 1000

    def n_in_kg_d(self) -> float:
        return (self.ps_ds_tpd * self.ps_n_pct / 100
                + self.was_ds_tpd * self.was_n_pct / 100) * 1000

    def p_in_kg_d(self) -> float:
        return (self.ps_ds_tpd * self.ps_p_pct / 100
                + self.was_ds_tpd * self.was_p_pct / 100) * 1000


@dataclass
class CNPStream:
    """kg/day of C, N or P in a single output stream."""
    name:   str
    label:  str     # human-readable
    c_kg_d: float = 0.0
    n_kg_d: float = 0.0
    p_kg_d: float = 0.0
    category: str = "other"   # "energy", "product", "loss", "atmospheric", "storage"


@dataclass
class CNPFateResult:
    """
    Complete C-N-P fate analysis for one technology configuration.

    All values in kg/day.
    """
    config_id:   str
    config_label:str
    inputs:      CNPInput

    # Total loads in
    c_in:  float = 0.0
    n_in:  float = 0.0
    p_in:  float = 0.0

    # Output streams
    streams: list = field(default_factory=list)

    # Derived indices (0–100%)
    c_utilised_pct:   float = 0.0   # C to energy (CH4 to CHP)
    c_sequestered_pct:float = 0.0   # C in stable soil store
    c_destroyed_pct:  float = 0.0   # C to atmosphere (CO2 + fugitive)
    c_retained_pct:   float = 0.0   # C in product (biosolids, char)
    c_recovery_index: float = 0.0   # utilised + sequestered

    n_recovered_pct:  float = 0.0   # N in useful products (fertiliser, struvite)
    n_recycled_pct:   float = 0.0   # N in centrate (recycle burden)
    n_lost_pct:       float = 0.0   # N to atmosphere
    n_burden_kg_d:    float = 0.0   # centrate NH4-N returned to mainstream

    p_recovered_pct:  float = 0.0   # P in biosolids / struvite (useful)
    p_recycled_pct:   float = 0.0   # P in centrate / filtrate
    p_lost_pct:       float = 0.0   # P not accounted for
    p_circularity_pct:float = 0.0   # P in land-applicable or recoverable form
    pfas_destroyed_pct: float = 0.0  # % PFAS destroyed by this technology

    def stream(self, name: str) -> Optional[CNPStream]:
        for s in self.streams:
            if s.name == name:
                return s
        return None

    def c_stream(self, name: str) -> float:
        s = self.stream(name)
        return s.c_kg_d if s else 0.0

    def n_stream(self, name: str) -> float:
        s = self.stream(name)
        return s.n_kg_d if s else 0.0

    def p_stream(self, name: str) -> float:
        s = self.stream(name)
        return s.p_kg_d if s else 0.0


# ── Stream definitions ──────────────────────────────────────────────────────
STREAM_META = {
    "biogas_ch4":    ("Methane (CHP/biomethane)", "energy"),
    "biogas_co2":    ("Biogenic CO2 (biogas)",    "atmospheric"),
    "fugitive_ch4":  ("Fugitive CH4",             "atmospheric"),
    "thermal_co2":   ("Combustion CO2",           "atmospheric"),
    "thermal_char":  ("Char / Ash",                "product"),
    "thermal_liq":   ("HTL Bio-crude",             "product"),
    "digestate_sol": ("Dewatered Cake",            "product"),
    "digestate_liq": ("Centrate / Filtrate",       "loss"),
    "atm_n2o":       ("N2O Emissions",            "atmospheric"),
    "atm_nh3":       ("NH3 Volatilisation",        "atmospheric"),
    "atm_n2":        ("N2 (denitrification/oxid.)", "atmospheric"),
    "atm_nox":       ("NOx Emissions",              "atmospheric"),
    "soil_seq":      ("Soil Sequestration",        "storage"),
    "syngas_energy": ("Syngas Energy (WtE)",       "energy"),
    "wte_energy":    ("WtE Heat/Power",            "energy"),
    "land_app_n2o":  ("Land App N2O",             "atmospheric"),
    "land_app_nh3":  ("Land App NH3",             "atmospheric"),
    "land_app_soil": ("Long-term Soil C",          "storage"),
}


def run_cnp_fate(
    inp:        CNPInput,
    config_id:  str,
    config_label: str = "",
) -> CNPFateResult:
    """
    Run C-N-P fate analysis for a technology configuration.

    Parameters
    ----------
    inp         : CNPInput with sludge characterisation
    config_id   : Technology string matching TECH_PARTITIONS keys,
                  or "base" for conventional MAD
    config_label: Human-readable label

    Returns
    -------
    CNPFateResult with all stream flows and indices
    """
    # Default to base if config not found
    tech_id = config_id if config_id in TECH_PARTITIONS else "base"
    parts = TECH_PARTITIONS[tech_id]

    c_in = inp.c_in_kg_d()
    n_in = inp.n_in_kg_d()
    p_in = inp.p_in_kg_d()

    streams: list[CNPStream] = []

    # Build stream objects
    for sname, (slabel, scat) in STREAM_META.items():
        c = c_in * parts["C"].get(sname, 0.0)
        n = n_in * parts["N"].get(sname, 0.0)
        p = p_in * parts["P"].get(sname, 0.0)
        if c > 0 or n > 0 or p > 0:
            streams.append(CNPStream(
                name=sname, label=slabel, category=scat,
                c_kg_d=c, n_kg_d=n, p_kg_d=p,
            ))

    # Add land application sub-streams (if cake is land-applied)
    cake_c = c_in * parts["C"].get("digestate_sol", 0)
    cake_n = n_in * parts["N"].get("digestate_sol", 0)
    if inp.land_applied and cake_c > 0:
        soil_c = cake_c * LAND_APPLICATION_C_SEQ
        streams.append(CNPStream(
            name="land_app_soil", label="Long-term Soil C", category="storage",
            c_kg_d=soil_c,
        ))
        streams.append(CNPStream(
            name="land_app_n2o", label="Land App N2O", category="atmospheric",
            n_kg_d=cake_n * LAND_APPLICATION_N2O,
        ))
        streams.append(CNPStream(
            name="land_app_nh3", label="Land App NH3", category="atmospheric",
            n_kg_d=cake_n * LAND_APPLICATION_NH3,
        ))

    # Compute indices
    # "Utilised" = all carbon converted to useful energy or fuel product
    # Includes: CH4 to CHP, syngas energy (pyrolysis WtE), WtE heat/power,
    # and liquid fuel (HTL bio-crude). Biochar counts as sequestration, not utilisation.
    ch4_c    = c_in * (parts["C"].get("biogas_ch4",   0)
                     + parts["C"].get("syngas_energy", 0)   # pyrolysis syngas
                     + parts["C"].get("wte_energy",   0)    # incineration WtE
                     + parts["C"].get("thermal_liq",  0))   # HTL bio-crude
    seq_c    = (c_in * parts["C"].get("soil_seq", 0)
                + (cake_c * LAND_APPLICATION_C_SEQ if inp.land_applied else 0))
    dest_c   = (c_in * (parts["C"].get("biogas_co2", 0)
                        + parts["C"].get("fugitive_ch4", 0)
                        + parts["C"].get("thermal_co2", 0)))
    ret_c    = c_in * (parts["C"].get("digestate_sol", 0)
                       + parts["C"].get("thermal_char", 0)
                       + parts["C"].get("thermal_liq", 0))

    n_cake   = n_in * parts["N"].get("digestate_sol", 0)
    n_liquid = n_in * parts["N"].get("digestate_liq", 0)
    # All atmospheric N streams: N2O, NH3, N2 (denitrification), NOx (incineration)
    n_atm    = n_in * (parts["N"].get("atm_n2o",  0)
                     + parts["N"].get("atm_nh3",  0)
                     + parts["N"].get("atm_n2",   0)   # N2 from denitrification
                     + parts["N"].get("atm_nox",  0))  # NOx from incineration
    if inp.land_applied:
        n_atm += n_cake * (LAND_APPLICATION_N2O + LAND_APPLICATION_NH3)

    p_cake   = p_in * parts["P"].get("digestate_sol", 0)
    p_liquid = p_in * parts["P"].get("digestate_liq", 0)
    p_char   = p_in * parts["P"].get("thermal_char", 0)
    p_circ   = p_cake + p_char  # land-applicable or recoverable from ash

    # PFAS destruction potential
    _pfas_fate_info = PFAS_FATE.get(tech_id, PFAS_FATE["base"])
    _pfas_destroyed = _pfas_fate_info.get("destroyed", 0.0) * 100

    result = CNPFateResult(
        config_id=config_id,
        config_label=config_label or config_id,
        inputs=inp,
        c_in=c_in, n_in=n_in, p_in=p_in,
        streams=streams,
        c_utilised_pct=   ch4_c  / c_in * 100 if c_in else 0,
        c_sequestered_pct=seq_c  / c_in * 100 if c_in else 0,
        c_destroyed_pct=  dest_c / c_in * 100 if c_in else 0,
        c_retained_pct=   ret_c  / c_in * 100 if c_in else 0,
        c_recovery_index= (ch4_c + seq_c) / c_in * 100 if c_in else 0,
        n_recovered_pct=  n_cake   / n_in * 100 if n_in else 0,
        n_recycled_pct=   n_liquid / n_in * 100 if n_in else 0,
        n_lost_pct=       n_atm    / n_in * 100 if n_in else 0,
        n_burden_kg_d=    n_liquid,
        p_recovered_pct=  p_cake   / p_in * 100 if p_in else 0,
        p_recycled_pct=   p_liquid / p_in * 100 if p_in else 0,
        p_lost_pct=       max(0, p_in - p_cake - p_liquid - p_char) / p_in * 100 if p_in else 0,
        p_circularity_pct=p_circ  / p_in * 100 if p_in else 0,
        pfas_destroyed_pct=_pfas_destroyed,
    )
    return result


def run_cnp_comparison(
    inp:      CNPInput,
    configs:  list[tuple[str, str]],   # [(config_id, label), ...]
) -> list[CNPFateResult]:
    """Run CNP fate analysis for multiple technology configurations."""
    return [run_cnp_fate(inp, cid, lbl) for cid, lbl in configs]


def cnp_summary_table(results: list[CNPFateResult]) -> list[dict]:
    """
    Return a list of dicts suitable for table rendering.
    Each dict has keys: metric, and one key per config_id.
    """
    metrics = [
        ("c_utilised_pct",    "C to Energy/Fuel % (CH4/syngas/WtE/bio-crude)"),
        ("c_sequestered_pct", "C Sequestered (soil) %"),
        ("c_destroyed_pct",   "C to Atmosphere %"),
        ("c_retained_pct",    "C in Product %"),
        ("c_recovery_index",  "Carbon Recovery Index %"),
        ("n_recovered_pct",   "N in Biosolids (cake) %"),
        ("n_recycled_pct",    "N in Centrate (burden) %"),
        ("n_lost_pct",        "N to Atmosphere %"),
        ("n_burden_kg_d",     "N Centrate Burden (kg/day)"),
        ("p_recovered_pct",   "P in Cake %"),
        ("p_recycled_pct",    "P in Centrate %"),
        ("p_circularity_pct", "P Circularity Index %"),
        ("pfas_destroyed_pct","PFAS Destroyed %"),
    ]
    rows = []
    for attr, label in metrics:
        row = {"metric": label}
        for r in results:
            row[r.config_id] = getattr(r, attr, 0)
        rows.append(row)
    return rows


# ── Sankey data helper ─────────────────────────────────────────────────────
def carbon_sankey_data(result: CNPFateResult) -> dict:
    """
    Return {nodes, links} for a Carbon Fate Sankey diagram.
    
    Compatible with D3.js sankey plugin and matplotlib.sankey.
    nodes: [{"name": str, "category": str}, ...]
    links: [{"source": int, "target": int, "value": float}, ...]
    """
    nodes = [
        {"name": "PS Carbon",       "category": "input"},
        {"name": "WAS Carbon",      "category": "input"},
        {"name": "Methane (CHP)",   "category": "energy"},
        {"name": "Biogenic CO2",    "category": "atmospheric"},
        {"name": "Fugitive CH4",    "category": "atmospheric"},
        {"name": "Dewatered Cake",  "category": "product"},
        {"name": "Centrate",        "category": "liquid"},
        {"name": "Char / Ash",      "category": "product"},
        {"name": "HTL Bio-crude",   "category": "product"},
        {"name": "Combustion CO2",  "category": "atmospheric"},
        {"name": "Soil Storage",    "category": "storage"},
    ]
    node_idx = {n["name"]: i for i, n in enumerate(nodes)}

    inp = result.inputs
    ps_c  = (inp.ps_c_pct or SLUDGE_COMPOSITION["c_frac_ps"] * 100) / 100 * inp.ps_ds_tpd * 1000
    was_c = (inp.was_c_pct or SLUDGE_COMPOSITION["c_frac_was"] * 100) / 100 * inp.was_ds_tpd * 1000

    links = []
    for sname, target_name in [
        ("biogas_ch4",    "Methane (CHP)"),
        ("biogas_co2",    "Biogenic CO2"),
        ("fugitive_ch4",  "Fugitive CH4"),
        ("digestate_sol", "Dewatered Cake"),
        ("digestate_liq", "Centrate"),
        ("thermal_char",  "Char / Ash"),
        ("thermal_liq",   "HTL Bio-crude"),
        ("thermal_co2",   "Combustion CO2"),
        ("soil_seq",      "Soil Storage"),
        ("land_app_soil", "Soil Storage"),
    ]:
        val = result.c_stream(sname)
        if val < 0.5:
            continue
        # Split PS and WAS proportionally as source
        total = result.c_in or 1
        ps_share  = ps_c  / total * val
        was_share = was_c / total * val
        if ps_share > 0.5:
            links.append({"source": node_idx["PS Carbon"],
                          "target": node_idx[target_name],
                          "value":  round(ps_share, 1)})
        if was_share > 0.5:
            links.append({"source": node_idx["WAS Carbon"],
                          "target": node_idx[target_name],
                          "value":  round(was_share, 1)})

    # Remove nodes with no flows
    used = {n for lk in links for n in (lk["source"], lk["target"])}
    final_nodes = [n for i, n in enumerate(nodes) if i in used]
    # Remap indices
    old_to_new = {old: new for new, old in enumerate(i for i, n in enumerate(nodes) if i in used)}
    final_links = [{"source": old_to_new[lk["source"]],
                    "target": old_to_new[lk["target"]],
                    "value":  lk["value"]} for lk in links]
    return {"nodes": final_nodes, "links": final_links, "unit": "kg C/day"}


if __name__ == "__main__":
    # Quick self-test
    inp = CNPInput(ps_ds_tpd=120.7, was_ds_tpd=98.8,
                   ps_vs_pct=65, was_vs_pct=65,
                   ps_n_pct=3.5, was_n_pct=8.5,
                   ps_p_pct=1.2, was_p_pct=3.0)

    configs = [
        ("base",         "Conventional MAD"),
        ("pre_thp",      "Pre-THP"),
        ("separate",     "Separate PS/WAS"),
        ("separate_thp", "Separate + THP"),
        ("incineration", "Incineration"),
    ]
    results = run_cnp_comparison(inp, configs)

    print("ETP 220 tDS/d — C-N-P FATE ANALYSIS")
    print("="*72)
    print(f"  C in: {results[0].c_in:,.0f} kg/d | N in: {results[0].n_in:,.0f} kg/d | P in: {results[0].p_in:,.0f} kg/d")
    print()

    hdr = f"{'Metric':32}" + "".join(f"{r.config_label[:12]:>14}" for r in results)
    print(hdr)
    print("-"*72)
    for row in cnp_summary_table(results):
        m = row["metric"]
        vals = "".join(
            f"{row[r.config_id]:>14.1f}" for r in results
        )
        print(f"  {m:30} {vals}")
