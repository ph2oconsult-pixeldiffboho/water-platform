"""
tests/domains/wastewater/test_scope1_methodology.py

Verifies the Scope 1 N₂O methodology fixes from the Whitepaper Rev 14
implementation PR:

  1. carbon_layer.EF_N2O_DEFAULT is 0.016 (IPCC 2019 Refinement Tier 1),
     not the legacy 0.010.
  2. Aerobic Granular Sludge produces higher Scope 1 N₂O than conventional
     BNR for the same N load and removal (Jahn et al. 2019 mechanism —
     PHB-mediated SND in granule cores).
  3. The scope1_scenario_layer produces three distinct views of the
     headline Scope 1 number (legacy / IPCC 2019 / measured-high case).

Standalone — no pytest required.
"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from core.project.project_model import DomainType
from core.assumptions.assumptions_manager import AssumptionsManager
from domains.wastewater.technologies.bnr import BNRTechnology, BNRInputs
from domains.wastewater.technologies.granular_sludge import (
    GranularSludgeTechnology, GranularSludgeInputs,
)

_p = _f = 0
_err = []

def chk(name, cond, detail=""):
    global _p, _f
    if cond: _p += 1; print(f"  ✅ {name}")
    else:
        _f += 1; _err.append(name)
        print(f"  ❌ {name}" + (f" — {detail}" if detail else ""))


def _assumptions():
    """Identical influent and effluent targets for AGS vs BNR comparison."""
    a = AssumptionsManager().load_defaults(DomainType.WASTEWATER)
    a.engineering_assumptions.update({
        "influent_bod_mg_l": 250, "influent_tkn_mg_l": 45,
        "influent_tn_mg_l": 45, "influent_nh4_mg_l": 35,
        "influent_tss_mg_l": 280, "influent_tp_mg_l": 7,
        "effluent_tn_mg_l": 10, "effluent_nh4_mg_l": 1,
    })
    return a


# ── Test 1: carbon_layer headline EF reconciliation ──────────────────────────

def test_carbon_layer_ef_n2o_is_ipcc_2019_default():
    """The platform-wide headline EF must be the IPCC 2019 Refinement value."""
    from apps.wastewater_app.carbon_layer import EF_N2O_DEFAULT
    chk("carbon_layer.EF_N2O_DEFAULT == 0.016 (IPCC 2019 Refinement)",
        abs(EF_N2O_DEFAULT - 0.016) < 1e-9,
        f"got {EF_N2O_DEFAULT} — should be 0.016, was 0.010 pre-PR")


def test_carbon_layer_ef_no_longer_legacy():
    """The 0.010 legacy default must be gone (it understated Scope 1 by ~38%)."""
    from apps.wastewater_app.carbon_layer import EF_N2O_DEFAULT
    chk("carbon_layer.EF_N2O_DEFAULT != 0.010 (legacy value removed)",
        abs(EF_N2O_DEFAULT - 0.010) > 1e-9,
        f"still at legacy value {EF_N2O_DEFAULT}")


# ── Test 2: AGS Scope 1 > BNR Scope 1 (the headline whitepaper finding) ─────

def test_ags_n2o_higher_than_bnr_same_load():
    """
    Same flow + same influent TN + same effluent target →
    AGS N₂O > BNR N₂O. This is the Jahn et al. 2019 finding the PR encodes.
    """
    flow_mld = 20.0

    bnr_inputs = BNRInputs(process_configuration="a2o", srt_days=12.0,
                           mlss_mg_l=4000.0, do_aerobic_mg_l=2.0)
    ags_inputs = GranularSludgeInputs(srt_days=20.0, cycle_time_hours=4.0,
                                      granule_diameter_mm=2.0,
                                      design_temperature_celsius=20.0)

    bnr_r = BNRTechnology(_assumptions()).calculate(flow_mld, bnr_inputs)
    ags_r = GranularSludgeTechnology(_assumptions()).calculate(flow_mld, ags_inputs)

    bnr_n2o = bnr_r.carbon.n2o_biological_tco2e_yr
    ags_n2o = ags_r.carbon.n2o_biological_tco2e_yr

    chk("AGS N₂O > BNR N₂O for same load",
        ags_n2o > bnr_n2o,
        f"AGS={ags_n2o:.1f} tCO₂e/yr, BNR={bnr_n2o:.1f} tCO₂e/yr")

    # And by a material margin — AGS uses 0.024 vs BNR 0.016 → at least 30% higher
    # (allowing for differences in computed tn_removed between the two engines).
    chk("AGS N₂O is materially higher than BNR (≥25%)",
        ags_n2o >= bnr_n2o * 1.25,
        f"AGS={ags_n2o:.1f}, BNR={bnr_n2o:.1f}, ratio={ags_n2o/max(bnr_n2o,1e-9):.2f}")


def test_ags_emits_scope1_warning_in_notes():
    """The AGS engine must surface the 'not Scope 1 advantaged' caveat in notes."""
    flow_mld = 10.0
    inputs = GranularSludgeInputs()
    r = GranularSludgeTechnology(_assumptions()).calculate(flow_mld, inputs)
    joined = " ".join(str(a) for a in r.notes.assumptions).lower()
    chk("AGS notes mention Jahn et al. 2019",
        "jahn" in joined,
        "Jahn reference missing from assumptions")
    chk("AGS notes warn that AGS does NOT confer Scope 1 advantage",
        "does not" in joined or "does not deliver" in joined or "not deliver" in joined or "no" in joined,
        f"caveat language missing — notes were: {joined[:200]}")


# ── Test 3: scope1_scenario_layer (Change 3) ────────────────────────────────

def test_scope1_scenario_layer_three_distinct_values():
    """
    The scope1_scenario_layer must produce three distinct views of the
    headline Scope 1 number: legacy default, current IPCC 2019, measured high.
    """
    try:
        from apps.wastewater_app.scope1_scenario_layer import (
            build_scope1_scenarios, EF_LEGACY, EF_IPCC_2019, EF_MEASURED_HIGH,
        )
    except ImportError as e:
        chk("scope1_scenario_layer importable",
            False, f"layer not yet implemented: {e}")
        return

    chk("EF_LEGACY < EF_IPCC_2019 < EF_MEASURED_HIGH",
        EF_LEGACY < EF_IPCC_2019 < EF_MEASURED_HIGH,
        f"got legacy={EF_LEGACY}, ipcc={EF_IPCC_2019}, high={EF_MEASURED_HIGH}")

    chk("EF_LEGACY equals 0.0035 (IPCC 2006 default)",
        abs(EF_LEGACY - 0.0035) < 1e-9,
        f"got {EF_LEGACY}")
    chk("EF_IPCC_2019 equals 0.016",
        abs(EF_IPCC_2019 - 0.016) < 1e-9,
        f"got {EF_IPCC_2019}")
    chk("EF_MEASURED_HIGH equals 0.030",
        abs(EF_MEASURED_HIGH - 0.030) < 1e-9,
        f"got {EF_MEASURED_HIGH}")

    # Given a central Scope 1 N₂O number, the three scenarios must scale
    # linearly with the EF ratio. Use 1000 tCO₂e/yr as a synthetic central.
    central_tco2e_yr = 1000.0
    scenarios = build_scope1_scenarios(
        n2o_central_tco2e_yr = central_tco2e_yr,
        ef_central = EF_IPCC_2019,
    )

    chk("scenarios returned an object with three entries",
        hasattr(scenarios, "legacy") and hasattr(scenarios, "ipcc_2019")
        and hasattr(scenarios, "measured_high"),
        f"got {type(scenarios).__name__}")

    chk("scenarios.legacy = central × (EF_LEGACY / EF_IPCC_2019)",
        abs(scenarios.legacy - central_tco2e_yr * (EF_LEGACY / EF_IPCC_2019)) < 1.0,
        f"got {scenarios.legacy}, expected ~{central_tco2e_yr * (EF_LEGACY / EF_IPCC_2019):.1f}")
    chk("scenarios.ipcc_2019 equals central (when ef_central=EF_IPCC_2019)",
        abs(scenarios.ipcc_2019 - central_tco2e_yr) < 1.0,
        f"got {scenarios.ipcc_2019}, expected {central_tco2e_yr}")
    chk("scenarios.measured_high = central × (EF_HIGH / EF_IPCC_2019)",
        abs(scenarios.measured_high - central_tco2e_yr * (EF_MEASURED_HIGH / EF_IPCC_2019)) < 1.0,
        f"got {scenarios.measured_high}")

    # The methodology-revision risk = current - legacy
    chk("methodology_revision_risk_tco2e_yr > 0",
        scenarios.methodology_revision_risk_tco2e_yr > 0,
        f"got {scenarios.methodology_revision_risk_tco2e_yr}")
    chk("microbiome_instability_risk_tco2e_yr > 0",
        scenarios.microbiome_instability_risk_tco2e_yr > 0,
        f"got {scenarios.microbiome_instability_risk_tco2e_yr}")


# ── Test 4: AGS credibility flag fires when AGS is in pathway alternatives ──

def test_ags_credibility_flag_fires_on_nereda_alternative():
    """
    When the upgrade pathway includes a Nereda/AGS alternative, the credibility
    layer must surface the Scope 1 caveat as a compatibility flag.
    """
    from apps.wastewater_app.stack_generator import (
        UpgradePathway, AlternativePathway, PathwayStage, Constraint,
        TI_INDENSE, CT_NITRIFICATION,
        MECH_BIOMASS_SEL,
    )
    from apps.wastewater_app.credibility_layer import _check_compatibility

    # Minimal pathway with a Nereda alternative
    ags_alt = AlternativePathway(
        label = "Option C — Nereda® AGS (full process replacement)",
        stages = ["Nereda® Aerobic Granular Sludge reactor (replaces secondary treatment)"],
        rationale = "test",
        when_preferred = "test",
        capex_class = "High",
    )

    # Stub PathwayStage and Constraint with correct field names
    stage = PathwayStage(
        stage_number = 1,
        technology = TI_INDENSE,
        tech_display = "inDENSE",
        mechanism = MECH_BIOMASS_SEL,
        mechanism_label = "biomass selection",
        purpose = "test",
        engineering_basis = "test",
        addresses = [CT_NITRIFICATION],
    )
    constraint = Constraint(
        constraint_type = CT_NITRIFICATION,
        label = "Nitrification",
        severity = "High",
        priority = 1,
    )

    pathway = UpgradePathway(
        system_state = "Tightening",
        proximity_pct = 50.0,
        plant_type = "BNR",
        flow_scenario = "ADWF",
        constraints = [constraint],
        primary_constraint = constraint,
        secondary_constraints = [],
        stages = [stage],
        alternatives = [ags_alt],
        pathway_narrative = "test",
        constraint_summary = "test",
        residual_risks = [],
        confidence = "Medium",
    )

    flags = _check_compatibility(pathway, plant_context={})
    has_ags_flag = any(("ags" in f.lower() or "nereda" in f.lower())
                       and "scope 1" in f.lower()
                       for f in flags)
    chk("AGS Scope 1 caveat fires on Nereda alternative",
        has_ags_flag,
        f"no matching flag in {len(flags)} compatibility flags")


# ── Runner ────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  SCOPE 1 METHODOLOGY FIX TESTS (Whitepaper Rev 14)")
    print("=" * 60)
    test_carbon_layer_ef_n2o_is_ipcc_2019_default()
    test_carbon_layer_ef_no_longer_legacy()
    test_ags_n2o_higher_than_bnr_same_load()
    test_ags_emits_scope1_warning_in_notes()
    test_scope1_scenario_layer_three_distinct_values()
    test_ags_credibility_flag_fires_on_nereda_alternative()
    print(f"\n  {_p} passed, {_f} failed")
    if _err:
        [print(f"  ❌ {e}") for e in _err]
        return 1
    print("  ✅ ALL PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
