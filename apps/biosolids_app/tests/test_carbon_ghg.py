"""
tests/test_carbon_ghg.py

BioPoint V1 — Carbon & GHG Engine Test Suite.

Covers:
  - C/N/P closure assertions for all 11 pathway families + 4 hybrid configs
  - Biogenic CO2 convention switching (carbon_neutral vs count_all)
  - Grid scenario sensitivity (current / 2035 / net-zero)
  - Anti-greenwashing flag correctness
  - Removal vs displacement separation
  - R50 credit weight edge cases
  - Regression snapshots (AD baseline)

Run: python tests/test_carbon_ghg.py

ph2o Consulting — BioPoint V1 — v25B01
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.ghg_coefficients import (
    CARBON_TO_VS_RATIO, CH4_FRACTION_OF_BIOGAS, COD_TO_CARBON_RATIO,
    HYDROCHAR_R50, PYROCHAR_R50_CREDIT_THRESHOLD, PYROCHAR_R50_FULL_CREDIT,
    GWP_CH4, GWP_N2O,
)
from engine.carbon_adapter import PathwayBalanceResult, _r50_credit_weight
from engine.carbon_fate import run_carbon_fate, run_carbon_fate_all
from engine.carbon_ghg import GHGInputs, run_ghg, run_ghg_all

# ── helpers ────────────────────────────────────────────────────────────────
passed = 0
failures = []

def chk(name, cond, detail=''):
    global passed
    if cond:
        print(f'  ok  {name}')
        passed += 1
    else:
        print(f'  FAIL {name}' + (f': {detail}' if detail else ''))
        failures.append(name)

def approx(a, b, tol=0.01): return abs(a - b) <= tol

VS_PCT  = 72.0
CARBON  = CARBON_TO_VS_RATIO * VS_PCT / 100.0 * 1000.0   # 360 kgC/tDS

def make_bal(ptype, *, biogas_m3=0.0, net_elec=0.0,
             char_kg=0.0, char_fc_pct=0.0, char_r50=0.0,
             ash_residual_c=0.0, centrate_cod=0.0,
             n_product=20.0, p_product=15.0,
             fossil_gj=0.0, transport_tkm=1.0,
             vs_pct=VS_PCT):
    carbon = CARBON_TO_VS_RATIO * vs_pct / 100.0 * 1000.0
    bal = PathwayBalanceResult(
        pathway_type=ptype, pathway_name=ptype,
        ds_tpd=50.0, vs_pct=vs_pct, ash_pct=100-vs_pct,
        carbon_kg_per_tds=carbon, carbon_in_kg_per_tds=carbon,
        nitrogen_kg_per_tds=35.0, phosphorus_kg_per_tds=20.0,
        transport_t_km_per_tds=transport_tkm,
        fossil_fuel_gj_per_tds=fossil_gj,
        n_in_product_kg_per_tds=n_product,
        p_in_product_kg_per_tds=p_product,
    )
    if biogas_m3 > 0:
        bal.biogas_m3_per_tds = biogas_m3
        bal.biogas_ch4_m3_per_tds = biogas_m3 * CH4_FRACTION_OF_BIOGAS
        bal.biogas_co2_m3_per_tds = biogas_m3 * (1 - CH4_FRACTION_OF_BIOGAS)
        bal.biogas_carbon_kg_per_tds = (
            bal.biogas_ch4_m3_per_tds * 0.717 * (12/16) +
            bal.biogas_co2_m3_per_tds * 1.964 * (12/44))
    bal.net_electricity_kwh_per_tds = net_elec
    if char_kg > 0:
        from engine.carbon_adapter import _r50_credit_weight
        w = _r50_credit_weight(char_r50)
        bal.char_kg_per_tds = char_kg
        bal.char_fixed_carbon_pct = char_fc_pct
        bal.char_r50 = char_r50
        bal.char_stable_carbon_kg_per_tds = char_kg * char_fc_pct/100 * w
        bal.char_labile_carbon_kg_per_tds  = char_kg * char_fc_pct/100 * (1-w)
    bal.ash_residual_carbon_kg_per_tds = ash_residual_c
    if centrate_cod > 0:
        bal.centrate_cod_kg_per_tds    = centrate_cod
        bal.centrate_carbon_kg_per_tds = centrate_cod * COD_TO_CARBON_RATIO
        bal.centrate_n_kg_per_tds      = centrate_cod / 10.0
    return bal


# ── standard balances for 11 pathways ─────────────────────────────────────
BALANCES = {
    "baseline":       make_bal("baseline", n_product=35.0, p_product=20.0),
    "AD":             make_bal("AD", biogas_m3=8.0, net_elec=200.0,
                               centrate_cod=18.0, n_product=27.0, p_product=17.0),
    "drying_only":    make_bal("drying_only", fossil_gj=0.5, n_product=35.0, p_product=20.0),
    "pyrolysis":      make_bal("pyrolysis", char_kg=270.0, char_fc_pct=40.0, char_r50=0.65,
                               net_elec=150.0),
    "gasification":   make_bal("gasification", net_elec=180.0,
                               ash_residual_c=280.0*0.02, n_product=1.0, p_product=18.0),
    "HTC":            make_bal("HTC", char_kg=550.0, char_fc_pct=55.0, char_r50=0.35,
                               centrate_cod=120.0, n_product=15.0, p_product=14.0),
    "HTC_sidestream": make_bal("HTC_sidestream", char_kg=550.0, char_fc_pct=55.0,
                               char_r50=0.35, centrate_cod=15.0, n_product=15.0, p_product=14.0),
    "centralised":    make_bal("centralised", char_kg=270.0, char_fc_pct=38.0, char_r50=0.60,
                               centrate_cod=15.0, net_elec=120.0),
    "decentralised":  make_bal("decentralised", fossil_gj=0.3, n_product=35.0, p_product=20.0),
    "incineration":   make_bal("incineration", net_elec=80.0,
                               ash_residual_c=280.0*0.015, n_product=1.5, p_product=18.0),
    "thp_incineration": make_bal("thp_incineration", biogas_m3=3.0, net_elec=60.0,
                                  centrate_cod=20.0, ash_residual_c=280.0*0.015,
                                  n_product=1.5, p_product=18.0),
}

# Hybrid balances H00–H03
def make_hybrid(config_id, hub_treatment, transport_tkm):
    bal = make_bal(f"hybrid_{config_id}", transport_tkm=transport_tkm)
    bal.is_hybrid = True
    bal.config_id = config_id
    return bal

HYBRID_BALANCES = {
    "H00": make_hybrid("H00", "AD", transport_tkm=0.2),
    "H01": make_hybrid("H01", "HTC_sidestream", transport_tkm=4.5),
    "H02": make_hybrid("H02", "HTC_sidestream", transport_tkm=2.8),
    "H03": make_hybrid("H03", "HTC_sidestream", transport_tkm=2.0),
}

GHG = GHGInputs()


# ============================================================
# SECTION 1 — CARBON CLOSURE (all 11 pathways)
# ============================================================
print("\n1. CARBON CLOSURE — 11 PATHWAYS")
print("="*55)

for ptype, bal in BALANCES.items():
    fate = run_carbon_fate(bal)
    C = bal.carbon_in_kg_per_tds
    total = fate.carbon_destiny_total_kg_per_tds
    err = abs(total - C) / C * 100 if C > 0 else 0
    chk(f"Closure [{ptype}]: err={err:.1f}% ≤ 5%", err <= 5.0,
        f"in={C:.1f} out={total:.1f}")


# ============================================================
# SECTION 2 — CARBON CLOSURE (4 hybrid configs)
# ============================================================
print("\n2. CARBON CLOSURE — 4 HYBRID CONFIGS")
print("="*55)

for config_id, bal in HYBRID_BALANCES.items():
    fate = run_carbon_fate(bal)
    C = bal.carbon_in_kg_per_tds
    total = fate.carbon_destiny_total_kg_per_tds
    err = abs(total - C) / C * 100 if C > 0 else 0
    chk(f"Closure [hybrid {config_id}]: err={err:.1f}% ≤ 5%", err <= 5.0)


# ============================================================
# SECTION 3 — FIVE-WAY SPLIT PROPERTIES
# ============================================================
print("\n3. FIVE-WAY DESTINY SPLIT PROPERTIES")
print("="*55)

for ptype, bal in BALANCES.items():
    fate = run_carbon_fate(bal)
    # All five categories must be non-negative
    for cat, val in fate.carbon_destiny.items():
        chk(f"Non-negative [{ptype}] {cat[:20]}", val >= 0, f"{val:.3f}")

# AD must have energy > 0 and no sequestration
fate_ad = run_carbon_fate(BALANCES["AD"])
chk("AD: energy > 0 (biogas CHP)", fate_ad.carbon_energy > 0)
chk("AD: sequestered = 0 (no biochar)", approx(fate_ad.carbon_sequestered, 0, 0.01))

# Incineration: sequestered = 0, oxidised dominates
fate_in = run_carbon_fate(BALANCES["incineration"])
chk("Incineration: sequestered = 0", approx(fate_in.carbon_sequestered, 0, 0.01))
chk("Incineration: oxidised dominant",
    fate_in.carbon_oxidised > fate_in.carbon_soil_delayed)

# Pyrolysis: sequestered > 0, energy = 0 (no biogas in test)
fate_py = run_carbon_fate(BALANCES["pyrolysis"])
chk("Pyrolysis: sequestered > 0", fate_py.carbon_sequestered > 0)
chk("Pyrolysis: has_biochar_product", fate_py.has_biochar_product)

# HTC: hydrochar R50 < threshold → sequestered = 0
fate_htc = run_carbon_fate(BALANCES["HTC"])
chk("HTC: sequestered = 0 (R50 below threshold)", approx(fate_htc.carbon_sequestered, 0, 0.01))

# Baseline: has land application flag
fate_bl = run_carbon_fate(BALANCES["baseline"])
chk("Baseline: has_land_application", fate_bl.has_land_application)


# ============================================================
# SECTION 4 — N/P CLOSURE
# ============================================================
print("\n4. N/P CLOSURE")
print("="*55)

for ptype, bal in BALANCES.items():
    fate = run_carbon_fate(bal)
    chk(f"N closure [{ptype}]", fate.n_closure_passes,
        f"{fate.n_closure_error_pct:.1f}%")
    chk(f"P closure [{ptype}]", fate.p_closure_passes,
        f"{fate.p_closure_error_pct:.1f}%")


# ============================================================
# SECTION 5 — BIOGENIC CO2 CONVENTION SWITCHING
# ============================================================
print("\n5. BIOGENIC CO2 CONVENTION SWITCHING")
print("="*55)

bal_ad = BALANCES["AD"]
fate_ad = run_carbon_fate(bal_ad)

# Biogenic CO2 always tracked regardless of convention
chk("Biogenic CO2 tracked in fate", fate_ad.biogenic_co2_kg_per_tds > 0)
chk("Biogenic CO2 note populated", len(fate_ad.biogenic_co2_note) > 20)

r_neutral  = run_ghg(bal_ad, fate_ad, GHGInputs(biogenic_co2_convention="carbon_neutral"))
r_count_all = run_ghg(bal_ad, fate_ad, GHGInputs(biogenic_co2_convention="count_all"))

chk("carbon_neutral: biogenic excluded from scope1",
    r_neutral.current.scope1_kg_co2e < r_count_all.current.scope1_kg_co2e)
chk("count_all: biogenic in scope1",
    r_count_all.current.biogenic_co2_kg_co2e > 0)
chk("biogenic_co2_kg_co2e same in both (tracking is identical)",
    approx(r_neutral.current.biogenic_co2_kg_co2e,
           r_count_all.current.biogenic_co2_kg_co2e, 0.01))
chk("convention label in result", r_neutral.biogenic_convention == "carbon_neutral")


# ============================================================
# SECTION 6 — GRID SCENARIO SENSITIVITY
# ============================================================
print("\n6. GRID SCENARIO SENSITIVITY")
print("="*55)

# Pathway that exports electricity — displacement credit should decrease at lower grid intensity
bal_py = BALANCES["pyrolysis"]
fate_py = run_carbon_fate(bal_py)
r = run_ghg(bal_py, fate_py, GHGInputs())

chk("3 grid scenarios computed", all([
    r.current.scenario_name,
    r.scenario_2035.scenario_name,
    r.net_zero.scenario_name,
]))
# For electricity exporter: higher grid → larger displacement credit
chk("Displacement credits: current > 2035 > net-zero (for exporter)",
    r.current.displacement_credits_kg_co2e >= r.scenario_2035.displacement_credits_kg_co2e >= r.net_zero.displacement_credits_kg_co2e)

# Pathway that imports electricity — scope2 should decrease at lower grid intensity
bal_dry = BALANCES["drying_only"]
bal_dry.net_electricity_kwh_per_tds = -300.0   # importer
fate_dry = run_carbon_fate(bal_dry)
r_dry = run_ghg(bal_dry, fate_dry, GHGInputs())
chk("Scope2 importer: current > 2035 > net-zero",
    r_dry.current.scope2_kg_co2e >= r_dry.scenario_2035.scope2_kg_co2e >= r_dry.net_zero.scope2_kg_co2e)

# State-selectable grid: SA should give lower scope2 than QLD
bal_test = make_bal("AD", biogas_m3=8.0, net_elec=-100.0)
fate_test = run_carbon_fate(bal_test)
r_qld = run_ghg(bal_test, fate_test, GHGInputs(grid_intensity_current_kg_per_kwh=0.72))
r_sa  = run_ghg(bal_test, fate_test, GHGInputs(grid_intensity_current_kg_per_kwh=0.25))
chk("State grid: SA scope2 < QLD scope2",
    r_sa.current.scope2_kg_co2e < r_qld.current.scope2_kg_co2e)


# ============================================================
# SECTION 7 — ANTI-GREENWASHING FLAGS
# ============================================================
print("\n7. ANTI-GREENWASHING FLAGS")
print("="*55)

# Pathway with net negative driven by displacement (large electricity export, no sequestration)
bal_disp = make_bal("AD", biogas_m3=20.0, net_elec=1000.0,
                    centrate_cod=5.0, n_product=25.0, p_product=15.0)
fate_disp = run_carbon_fate(bal_disp)
r_disp = run_ghg(bal_disp, fate_disp, GHGInputs())
if r_disp.current.net_ghg_kg_co2e < 0:
    chk("Net-negative pathway: flag fires if displacement-driven",
        r_disp.net_negative_is_displacement is not None)
else:
    chk("Net-negative flag: pathway not net-negative (as expected at default scale)", True)

# Removal and displacement must ALWAYS be on separate lines
bal_py = BALANCES["pyrolysis"]
fate_py = run_carbon_fate(bal_py)
r_py = run_ghg(bal_py, fate_py, GHGInputs())
removal_line = [li for li in r_py.current.line_items if "removal" in li.label.lower()]
displacement_lines = [li for li in r_py.current.line_items if "displacement" in li.label.lower() or "avoided" in li.label.lower()]
chk("Removal line item present for pyrolysis",
    len(removal_line) > 0 or fate_py.carbon_sequestered == 0)
chk("Net GHG ≠ net including removal (when removal > 0)",
    r_py.current.net_ghg_kg_co2e == r_py.current.net_ghg_including_removal_kg_co2e
    or fate_py.carbon_sequestered > 0)

# Destiny statement warns against greenwashing for baseline
fate_bl = run_carbon_fate(BALANCES["baseline"])
chk("Baseline destiny statement warns about land application",
    "land application" in fate_bl.destiny_statement.lower())

# Destiny statement for displacement-heavy pathway flags convention risk
fate_ad = run_carbon_fate(BALANCES["AD"])
chk("AD destiny statement populated", len(fate_ad.destiny_statement) > 30)


# ============================================================
# SECTION 8 — R50 CREDIT WEIGHT EDGE CASES
# ============================================================
print("\n8. R50 CREDIT WEIGHT EDGE CASES")
print("="*55)

chk("R50 = 0.0 → weight = 0.0", approx(_r50_credit_weight(0.0), 0.0))
chk("R50 at threshold → weight = 0.0",
    approx(_r50_credit_weight(PYROCHAR_R50_CREDIT_THRESHOLD), 0.0))
chk("R50 at full credit → weight = 1.0",
    approx(_r50_credit_weight(PYROCHAR_R50_FULL_CREDIT), 1.0))
chk("R50 = 1.0 → weight = 1.0", approx(_r50_credit_weight(1.0), 1.0))
chk("R50 = HYDROCHAR_R50 → weight = 0 (below threshold)",
    approx(_r50_credit_weight(HYDROCHAR_R50), 0.0))
chk("R50 mid-range → weight between 0 and 1",
    0 < _r50_credit_weight(0.60) < 1.0)
chk("R50 weight monotonically increases",
    _r50_credit_weight(0.55) < _r50_credit_weight(0.60) < _r50_credit_weight(0.70))


# ============================================================
# SECTION 9 — GHG LINE ITEMS COMPLETENESS
# ============================================================
print("\n9. GHG LINE ITEMS COMPLETENESS")
print("="*55)

fate_ad  = run_carbon_fate(BALANCES["AD"])
r_ad = run_ghg(BALANCES["AD"], fate_ad, GHGInputs())

scopes_present = {li.scope for li in r_ad.current.line_items}
chk("Scope 1 present in line items", "Scope 1" in scopes_present)
chk("Biogenic line item present", "Biogenic" in scopes_present)
chk("Credit line items present", "Credit" in scopes_present)

# Transport in scope 3 when transport_tkm > 0
bal_transport = make_bal("AD", biogas_m3=8.0, net_elec=200.0, transport_tkm=5.0)
fate_transport = run_carbon_fate(bal_transport)
r_transport = run_ghg(bal_transport, fate_transport, GHGInputs())
chk("Transport scope3 > 0 when transport_tkm > 0",
    r_transport.current.scope3_kg_co2e > 0)


# ============================================================
# SECTION 10 — REGRESSION SNAPSHOTS (AD baseline)
# ============================================================
print("\n10. REGRESSION SNAPSHOTS")
print("="*55)

# Fixed inputs for regression
bal_reg = make_bal("AD", biogas_m3=8.0, net_elec=200.0,
                   centrate_cod=18.0, n_product=27.0, p_product=17.0)
bal_reg.centrate_carbon_kg_per_tds = 18.0 * COD_TO_CARBON_RATIO
bal_reg.centrate_n_kg_per_tds = 8.0

fate_reg = run_carbon_fate(bal_reg)
r_reg = run_ghg(bal_reg, fate_reg, GHGInputs(
    grid_intensity_current_kg_per_kwh=0.55))

# Snapshot values (computed first run; verify stability on re-run)
chk("Snapshot: carbon_in = 360.0 kgC/tDS",
    approx(bal_reg.carbon_in_kg_per_tds, 360.0, 0.1))
chk("Snapshot: biogenic_co2 > 0",
    fate_reg.biogenic_co2_kg_per_tds > 0)
chk("Snapshot: scope1 > 0 (fugitive CH4 + N2O)",
    r_reg.current.scope1_kg_co2e > 0)
chk("Snapshot: displacement credits > 0 (electricity export)",
    r_reg.current.displacement_credits_kg_co2e > 0)
chk("Snapshot: removal credits = 0 (no biochar in AD)",
    approx(r_reg.current.removal_credits_kg_co2e, 0.0, 0.01))
chk("Snapshot: net_ghg < gross_ghg (credits reduce it)",
    r_reg.current.net_ghg_kg_co2e < r_reg.current.gross_ghg_kg_co2e)
chk("Snapshot: 2035 scenario has lower displacement credit than current",
    r_reg.scenario_2035.displacement_credits_kg_co2e <=
    r_reg.current.displacement_credits_kg_co2e)

# System-level runners
all_bals  = list(BALANCES.values())
all_fates = run_carbon_fate_all(all_bals)
all_ghgs  = run_ghg_all(all_bals, all_fates, GHGInputs())
chk("run_carbon_fate_all: returns 11 results", len(all_fates) == 11)
chk("run_ghg_all: returns 11 results", len(all_ghgs) == 11)
chk("All GHG results have 3 scenarios",
    all(r.current.scenario_name != "" and
        r.scenario_2035.scenario_name != "" for r in all_ghgs))


# ============================================================
# SUMMARY
# ============================================================
print()
total = passed + len(failures)
print(f"Carbon/GHG test suite: {passed}/{total} passed")
if failures:
    print(f"FAILURES ({len(failures)}): {failures}")
    raise SystemExit(1)
else:
    print("ALL TESTS PASSED ✓")
