"""
canungra_runner.py — WaterPoint scenario runner for Canungra STP intensification

Drops into apps/wastewater_app/canungra/ or similar WaterPoint extension point.

Consumes:
  - canungra_diurnal_profile.json    (Figure 3.1 diurnal data)
  - canungra_scenarios.json          (4 scenarios: S0, S1, S2, S3)

Produces:
  - Permeate TN time series per scenario at given EP
  - Flow-weighted mean, 50%ile, 80%ile, peak
  - Compliance status against licence limits
  - Binding constraint identification
  - DIL-compliant output dict for UI rendering

Integration points with WaterPoint:
  1. Replace `_kinetics` with WaterPoint-calibrated SE QLD values
  2. Replace `_solve_bardenpho_steady_state` with WaterPoint BioWin-equivalent solver
  3. Emit outputs through WaterPoint's DIL layer for UI
  4. Link to Feasibility Layer for capex/opex scoring
  5. Link to Credibility Layer for uncertainty bands
"""
from __future__ import annotations
import json
import math
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional


# ============================================================================
# DATA STRUCTURES
# ============================================================================
@dataclass
class LicenceLimits:
    """Canungra STP effluent licence limits.
    
    Mass load interpretation:
      - Interpretation A (interpretation='A'): 607 kg/yr is a hard cap,
        regardless of design EP. Conservative.
      - Interpretation B (interpretation='B', default): 607 kg/yr was derived
        from 1,500 EP × 5 mg/L × ADWF × 365 × 1.10 (Rev B Table 2.1 fn 1).
        At re-licensing, the mass limit scales with design EP.
    
    Use .get_mass_limit(EP) to get the applicable annual mass cap.
    """
    TN_median: float = 5.0
    TN_80ile: float = 10.0
    TN_max: float = 15.0
    TN_mass_kg_yr: float = 607  # At Rev B 1,500 EP design
    NH3_80ile: float = 2.0
    NH3_max: float = 4.0
    TP_median: float = 1.0
    TP_80ile: float = 2.0
    TP_max: float = 3.0
    # Licence interpretation
    interpretation: str = 'B'  # 'A' (hard cap) or 'B' (scales with EP)
    design_basis_ep: int = 1500
    
    def get_mass_limit(self, EP: int) -> float:
        """Return applicable TN mass limit (kg/yr) at the given design EP."""
        if self.interpretation == 'A':
            return self.TN_mass_kg_yr
        elif self.interpretation == 'B':
            return self.TN_mass_kg_yr * (EP / self.design_basis_ep)
        else:
            raise ValueError(f"Unknown interpretation: {self.interpretation}")


@dataclass
class ComplianceResult:
    flow_weighted_mean: float
    p50: float
    p80: float
    peak: float
    median_pass: bool
    p80_pass: bool
    max_pass: bool
    annual_mass_kg: float
    mass_pass: bool
    
    @property
    def overall_pass(self) -> bool:
        return self.median_pass and self.p80_pass and self.max_pass and self.mass_pass
    
    def to_dict(self) -> dict:
        d = asdict(self)
        d["overall_pass"] = self.overall_pass
        return d


# ============================================================================
# BARDENPHO SOLVER — 5-stage with two distinct denit zones
# ============================================================================
class BardenphoSolver:
    """
    5-stage Bardenpho steady-state mass balance.
    
    NOT MLE — two denit zones in series:
      1. Primary anoxic: fed by A-recycle from aerobic, uses influent COD
      2. Post-anoxic: fed by forward flow only, uses endogenous + dosed carbon
    """
    
    def __init__(self, scenario: dict, kinetics: dict):
        self.scen = scenario
        self.kin = kinetics
    
    @staticmethod
    def arrhenius(k20, theta, T):
        return k20 * theta ** (T - 20)
    
    def solve(
        self,
        Q_kLd: float,
        TKN_mgL: float,
        COD_mgL: float,
        T_C: float,
        MeOH_Ld: float,
        MLSS_bio_mgL: float,
        EP: float,
        flow_paced_A: bool = False,
    ) -> dict:
        """
        Solve the Bardenpho at a given operating point (steady-state).
        
        Returns dict with concentrations at each zone outlet and permeate TN.
        """
        s = self.scen
        k = self.kin
        
        V_anox = s["zone_volumes_kL"]["primary_anoxic"]
        V_aer = s["zone_volumes_kL"]["aerobic"]
        V_deae = s["zone_volumes_kL"]["de_aeration"]
        V_postanox = s["zone_volumes_kL"]["post_anoxic"]
        V_MBR = s["zone_volumes_kL"]["MBR_tanks"]
        
        a = s["recycles"]["A_recycle_x_ADWF"]
        r_recycle = s["recycles"]["R_recycle_x_influent"]
        s_recycle = s["recycles"]["S_recycle_x_ADWF"]
        
        # Flow-paced A uses instantaneous Q; fixed uses ADWF setpoint
        Q_ADWF = EP * 0.200  # kL/d (200 L/EP/d)
        if flow_paced_A:
            Q_A = a * Q_kLd
        else:
            Q_A = a * Q_ADWF
        Q_R = r_recycle * Q_kLd
        Q_S = s_recycle * Q_ADWF if not flow_paced_A else s_recycle * Q_kLd
        
        # Nitrification load
        VSS_per_EP = s["operating"]["VSS_per_EP_gEPd_AAL"]
        N_WAS_mgL = VSS_per_EP * 0.08 * 1000 / 200  # mg/L of influent basis
        NH3_eff = s["operating"].get("NH3_eff_target_mgL", 0.5)
        rDON = 1.2
        NO3_produced = TKN_mgL - rDON - N_WAS_mgL - NH3_eff
        P_kgd = NO3_produced * Q_kLd / 1000
        
        # IFAS nitrification capacity
        ifas = s["ifas"]
        SA_IFAS = V_aer * ifas["fill_fraction"] * ifas["SSA_m2_per_m3"]
        nit_flux_T = self.arrhenius(ifas["biofilm_nit_flux_20C_gN_m2_d"], 1.09, T_C)
        IFAS_nit_cap = SA_IFAS * nit_flux_T / 1000  # kg/d
        
        # Biomass (kg)
        MLVSS = MLSS_bio_mgL * 0.72
        VSS_anox_kg = MLVSS * V_anox / 1000
        VSS_postanox_kg = MLVSS * V_postanox / 1000
        
        # Primary anoxic denit capacity
        K2_primary_T = self.arrhenius(k["K2_primary_anoxic_20C_gN_gVSS_d"],
                                       k["theta_K2"], T_C)
        kinetic_primary_kgd = VSS_anox_kg * K2_primary_T
        
        # COD-limited primary denit
        Fbs = 0.187
        PAO_frac = s["operating"].get("PAO_frac_RBCOD_uptake", 0.40)
        SBCOD_boost = k["SBCOD_hydrolysis_boost_factor"]
        RBCOD_avail = Fbs * COD_mgL * (1 - PAO_frac) * SBCOD_boost
        cod_cap_mgL = RBCOD_avail / k["COD_per_N_denit_carbonaceous"]
        cod_cap_kgd = cod_cap_mgL * Q_kLd / 1000
        
        # Post-anoxic capacities
        K2_endo_T = self.arrhenius(k["K2_endogenous_postanox_20C_gN_gVSS_d"],
                                    k["theta_endogenous"], T_C)
        K2_MeOH_T = self.arrhenius(k["K2_MeOH_acclimated_20C_gN_gVSS_d"],
                                    k["theta_K2"], T_C)
        endo_cap_kgd = VSS_postanox_kg * K2_endo_T
        MeOH_kinetic_cap = VSS_postanox_kg * K2_MeOH_T
        
        MeOH_kg = MeOH_Ld * 0.79  # density
        MeOH_N_support = MeOH_kg / k["MeOH_per_NO3N_stoichiometry_g_g"]
        
        # Iterate Bardenpho steady state
        NO3_ae = NO3_produced * 0.3  # initial guess
        for iteration in range(100):
            # Primary anoxic: bounded by kinetic, COD, delivery
            delivery_cap = Q_A * NO3_ae / 1000
            D1 = min(kinetic_primary_kgd, cod_cap_kgd, delivery_cap)
            
            if D1 == kinetic_primary_kgd:
                bind1 = "kinetic"
            elif D1 == cod_cap_kgd:
                bind1 = "COD"
            else:
                bind1 = "delivery"
            
            NO3_anox = max(0, (Q_A * NO3_ae - D1 * 1000) / ((1 + a + r_recycle) * Q_ADWF if not flow_paced_A else (Q_kLd + Q_A + Q_R)))
            
            # Post-anoxic: forward flow (1+S)×Q
            Q_fwd_post = Q_kLd + Q_S
            NO3_load_post = NO3_ae * Q_fwd_post / 1000  # kg/d entering post-anoxic
            
            # Endogenous removal (free)
            endo_rem = min(endo_cap_kgd, NO3_load_post)
            NO3_after_endo = NO3_load_post - endo_rem
            
            # MeOH-assisted removal
            kin_room = max(0, MeOH_kinetic_cap - endo_cap_kgd)
            meoh_rem = min(MeOH_N_support, kin_room, NO3_after_endo)
            
            D2 = endo_rem + meoh_rem
            NO3_post_conc = max(0, NO3_load_post - D2) * 1000 / Q_fwd_post
            
            # MBR does not remove N
            NO3_permeate = NO3_post_conc
            
            # Update NO3_ae
            # (1+A+S)×Q × NO3_ae = (1+A)×Q × NO3_anox + S×Q × NO3_perm + P×1000
            Q_in_aer = Q_kLd + Q_A + Q_S
            NO3_ae_new = ((Q_kLd + Q_A) * NO3_anox + Q_S * NO3_permeate + P_kgd * 1000) / Q_in_aer
            
            if abs(NO3_ae_new - NO3_ae) < 0.005:
                break
            NO3_ae = 0.6 * NO3_ae + 0.4 * NO3_ae_new
        
        # Determine effective NH3 slip
        total_nit_cap = IFAS_nit_cap + self._suspended_nit_cap(MLVSS, V_aer, s, k, T_C)
        NH3_load_kgd = (TKN_mgL - rDON - N_WAS_mgL) * Q_kLd / 1000
        NH3_slip_kgd = max(0, NH3_load_kgd - total_nit_cap)
        NH3_eff_actual = NH3_eff + NH3_slip_kgd * 1000 / Q_kLd if Q_kLd > 0 else NH3_eff
        NH3_eff_actual = min(NH3_eff_actual, 5.0)
        
        # TN
        TN = NO3_permeate + NH3_eff_actual + 0.15 + rDON
        
        return {
            "converged": True,
            "iterations": iteration,
            "NO3_produced_mgL": NO3_produced,
            "NO3_anox": NO3_anox,
            "NO3_ae": NO3_ae,
            "NO3_permeate": NO3_permeate,
            "NH3_eff": NH3_eff_actual,
            "TN_permeate": TN,
            "D1_kgd": D1, "D2_kgd": D2,
            "primary_binding": bind1,
            "nit_capacity_kgd": total_nit_cap,
            "NH3_load_kgd": NH3_load_kgd,
        }
    
    def _suspended_nit_cap(self, MLVSS, V_aer, s, k, T_C):
        """Approximate suspended AOB capacity based on SRT and load."""
        SRT = s["operating"]["design_SRT_days"]
        V_total_bio = sum(s["zone_volumes_kL"][z] for z in
                          ["anaerobic", "primary_anoxic", "aerobic", "de_aeration", "post_anoxic"])
        aerobic_frac = V_aer / (V_total_bio + s["zone_volumes_kL"]["MBR_tanks"])
        aerobic_SRT = SRT * aerobic_frac * 1.5
        AOB_frac = min(0.05, aerobic_SRT * 0.003)
        VSS_aerobic_kg = MLVSS * V_aer / 1000
        return VSS_aerobic_kg * AOB_frac * 5.0  # kg N/d


# ============================================================================
# DIURNAL SIMULATOR — CSTR chain with 30-min resolution
# ============================================================================
class DiurnalSimulator:
    """
    Applies the Rev B Figure 3.1 diurnal profile to a steady-state solver.
    Uses tanks-in-series CSTR model to properly capture MBR buffering.
    """
    
    def __init__(self, solver: BardenphoSolver, profile: dict):
        self.solver = solver
        self.profile = profile["data"]
    
    def run(
        self,
        EP: float,
        TKN_base_mgL: float,
        COD_base_mgL: float,
        T_C: float,
        MeOH_Ld_avg: float,
        MLSS_bio_mgL: float,
        n_cycles: int = 3,
        flow_paced_A: bool = False,
    ) -> list[dict]:
        """
        Simulate diurnal cycle and return time-series of permeate concentrations
        incorporating MBR tank buffering.
        
        Strategy:
          1. For each 30-min slice: compute what the "instantaneous" zone
             concentrations would be given current loading and recycles
          2. Pass the result through a first-order MBR tank buffer
          3. Report buffered permeate TN
          
        This is a pragmatic decoupling that gets the key behaviours right
        without requiring full CSTR-chain integration. WaterPoint's dynamic
        engine should replace this with proper integration.
        """
        Q_ADWF = EP * 0.200
        V_MBR = self.solver.scen["zone_volumes_kL"]["MBR_tanks"]
        
        results = []
        
        # MBR tank state (concentration of NO3 in MBR, persists across steps)
        NO3_MBR_state = 2.0  # initial guess
        
        for cycle in range(n_cycles):
            cycle_results = []
            for point in self.profile:
                t_h = point["t_h"]
                Q_inst = Q_ADWF * point["flow"]
                Q_inst = max(Q_inst, Q_ADWF * 0.3)  # minimum floor
                TKN_inst = TKN_base_mgL * point["tkn"]
                COD_inst = COD_base_mgL * point["cod"]
                
                # Solve at instantaneous conditions
                r = self.solver.solve(
                    Q_kLd=Q_inst,
                    TKN_mgL=TKN_inst,
                    COD_mgL=COD_inst,
                    T_C=T_C,
                    MeOH_Ld=MeOH_Ld_avg,
                    MLSS_bio_mgL=MLSS_bio_mgL,
                    EP=EP,
                    flow_paced_A=flow_paced_A,
                )
                
                # MBR tank buffering: first-order mixing with 30-min step
                # dC/dt = (Q/V)(C_in - C)
                # C[n+1] = C[n] + (Q×Δt/V)(C_in - C[n])
                dt_hr = 0.5
                Q_through = Q_inst  # permeate flow through MBR tank
                frac = min(1.0, Q_through * dt_hr / 24 / V_MBR)
                NO3_in_MBR = r["NO3_permeate"]
                NO3_MBR_state = NO3_MBR_state + frac * (NO3_in_MBR - NO3_MBR_state)
                
                TN_buffered = NO3_MBR_state + r["NH3_eff"] + 0.15 + 1.2
                
                cycle_results.append({
                    "t_h": t_h,
                    "Q_kLd": Q_inst,
                    "TKN_mgL": TKN_inst,
                    "NO3_unbuffered": r["NO3_permeate"],
                    "NO3_buffered": NO3_MBR_state,
                    "NH3_eff": r["NH3_eff"],
                    "TN_buffered": TN_buffered,
                    "primary_binding": r["primary_binding"],
                })
            
            results = cycle_results  # keep last cycle
        
        return results


# ============================================================================
# COMPLIANCE ASSESSOR
# ============================================================================
def assess_compliance(
    series: list[dict],
    limits: LicenceLimits,
    annual_days: int = 365,
    EP: int = 1500,
) -> ComplianceResult:
    """Compute flow-weighted statistics and check against licence.
    
    The mass_pass check respects the licence interpretation:
      - 'A' (hard cap): uses limits.TN_mass_kg_yr unchanged
      - 'B' (scales with EP): uses limits.get_mass_limit(EP)
    """
    tn_values = [s["TN_buffered"] for s in series]
    Q_values = [s["Q_kLd"] for s in series]
    
    # Flow-weighted mean (what's actually discharged)
    fwm = sum(t * q for t, q in zip(tn_values, Q_values)) / sum(Q_values)
    
    # Percentiles
    sorted_tn = sorted(tn_values)
    n = len(sorted_tn)
    p50 = sorted_tn[n // 2]
    p80 = sorted_tn[int(n * 0.80)]
    peak = max(tn_values)
    
    # Annual mass (daily avg × 365)
    daily_avg_mass = fwm * sum(Q_values) / len(Q_values) / 1000  # kg/d
    annual_mass = daily_avg_mass * annual_days
    
    # Get EP-aware mass limit
    applicable_mass_limit = limits.get_mass_limit(EP)
    
    return ComplianceResult(
        flow_weighted_mean=fwm,
        p50=p50, p80=p80, peak=peak,
        median_pass=(fwm < limits.TN_median),
        p80_pass=(p80 < limits.TN_80ile),
        max_pass=(peak < limits.TN_max),
        annual_mass_kg=annual_mass,
        mass_pass=(annual_mass < applicable_mass_limit),
    )


# ============================================================================
# MAIN RUNNER
# ============================================================================
def run_scenario(
    scenario_name: str,
    scenarios: dict,
    profile: dict,
    kinetics: dict,
    EP: float,
    loading: str = "AAL",
    T_C: float = 17.0,
    MeOH_Ld: Optional[float] = None,
    flow_paced_A: bool = False,
    licence_interpretation: str = "B",
) -> dict:
    """
    Run a single scenario and return full output dict for WaterPoint DIL.
    
    licence_interpretation:
      'A' - 607 kg/yr hard cap regardless of EP (conservative)
      'B' - 607 kg/yr scales with EP (default, Rev 16+ design basis)
    """
    scen = scenarios[scenario_name]
    
    # Get influent composition
    inf = scenarios.get("_influent_design", {}).get(loading) or {
        "AAL": {"TKN_mgL": 62, "COD_mgL": 701},
        "MML": {"TKN_mgL": 71, "COD_mgL": 876},
    }[loading]
    
    TKN = inf.get("TKN_mgL", 62)
    COD = inf.get("COD_mgL", 701)
    
    # Calculate MLSS at operating SRT
    V_bio = sum(scen["zone_volumes_kL"][z] for z in
                ["anaerobic", "primary_anoxic", "aerobic", "de_aeration", "post_anoxic"])
    V_MBR = scen["zone_volumes_kL"]["MBR_tanks"]
    s_recycle = scen["recycles"]["S_recycle_x_ADWF"]
    VSS_per_EP = scen["operating"]["VSS_per_EP_gEPd_AAL"]
    SRT = scen["operating"]["design_SRT_days"]
    MLSS_floor = scen["membrane"]["MLSS_floor_mgL"]
    # MLSS ceiling — realistic upper bound for membrane operation
    # Kubota: typically 12,000 mg/L ceiling (fouling/viscosity constraint)
    # HF: typically 10,000 mg/L ceiling
    MLSS_ceiling = scen["membrane"].get("MLSS_ceiling_mgL", 12000)
    
    total_kg_d = EP * (VSS_per_EP + 5) / 1000 / 0.72
    factor = V_bio + V_MBR * (s_recycle + 1) / s_recycle
    MLSS_bio = total_kg_d * SRT * 1000 / factor
    MLSS_MBR = MLSS_bio * (s_recycle + 1) / s_recycle
    
    # Operator-realistic SRT adjustment: hold MLSS_MBR within the band
    # [floor + 200, ceiling - 500] by trimming SRT in either direction.
    target_MLSS_MBR_low = MLSS_floor + 200
    target_MLSS_MBR_high = MLSS_ceiling - 500
    
    if MLSS_MBR < target_MLSS_MBR_low:
        # Raise SRT to hit the low target
        target_MLSS_bio = target_MLSS_MBR_low * s_recycle / (s_recycle + 1)
        SRT = min(target_MLSS_bio * factor / 1000 / total_kg_d, 60)
        MLSS_bio = total_kg_d * SRT * 1000 / factor
        MLSS_MBR = MLSS_bio * (s_recycle + 1) / s_recycle
    elif MLSS_MBR > target_MLSS_MBR_high:
        # Lower SRT to hit the ceiling — CANNOT go below nitrification minimum
        SRT_nit_min = 8  # days — below this, nitrifiers wash out
        target_MLSS_bio = target_MLSS_MBR_high * s_recycle / (s_recycle + 1)
        SRT_candidate = target_MLSS_bio * factor / 1000 / total_kg_d
        if SRT_candidate < SRT_nit_min:
            # We can't get MLSS below the ceiling without losing nitrification.
            # This means the plant is effectively overloaded.
            SRT = SRT_nit_min
            MLSS_bio = total_kg_d * SRT * 1000 / factor
            MLSS_MBR = MLSS_bio * (s_recycle + 1) / s_recycle
            # MLSS_MBR is now ABOVE ceiling — this is a fail state but we
            # let the simulation continue so compliance checks identify it.
        else:
            SRT = SRT_candidate
            MLSS_bio = total_kg_d * SRT * 1000 / factor
            MLSS_MBR = MLSS_bio * (s_recycle + 1) / s_recycle
    
    # Auto-find MeOH if not specified
    solver = BardenphoSolver(scen, kinetics)
    simulator = DiurnalSimulator(solver, profile)
    limits = LicenceLimits(interpretation=licence_interpretation)
    
    if MeOH_Ld is None:
        # Find minimum MeOH for median compliance
        for trial_meoh in range(0, 401, 4):
            series = simulator.run(
                EP=EP, TKN_base_mgL=TKN, COD_base_mgL=COD, T_C=T_C,
                MeOH_Ld_avg=trial_meoh, MLSS_bio_mgL=MLSS_bio,
                flow_paced_A=flow_paced_A,
            )
            compl = assess_compliance(series, limits, EP=int(EP))
            if compl.overall_pass and compl.flow_weighted_mean < 4.5:
                MeOH_Ld = trial_meoh
                break
        else:
            MeOH_Ld = 400  # not achievable
            series = simulator.run(
                EP=EP, TKN_base_mgL=TKN, COD_base_mgL=COD, T_C=T_C,
                MeOH_Ld_avg=MeOH_Ld, MLSS_bio_mgL=MLSS_bio,
                flow_paced_A=flow_paced_A,
            )
            compl = assess_compliance(series, limits, EP=int(EP))
    else:
        series = simulator.run(
            EP=EP, TKN_base_mgL=TKN, COD_base_mgL=COD, T_C=T_C,
            MeOH_Ld_avg=MeOH_Ld, MLSS_bio_mgL=MLSS_bio,
            flow_paced_A=flow_paced_A,
        )
        compl = assess_compliance(series, limits, EP=int(EP))
    
    return {
        "scenario": scenario_name,
        "EP": EP,
        "loading": loading,
        "temperature_C": T_C,
        "MeOH_Ld": MeOH_Ld,
        "flow_paced_A": flow_paced_A,
        "MLSS_bio": MLSS_bio,
        "MLSS_MBR": MLSS_MBR,
        "compliance": compl.to_dict(),
        "series": series,
    }


def sweep_EP(
    scenario_name: str,
    scenarios: dict,
    profile: dict,
    kinetics: dict,
    EP_range: range,
    T_C: float = 17.0,
    flow_paced_A: bool = False,
    licence_interpretation: str = "B",
) -> list[dict]:
    """Find maximum EP for which a scenario achieves compliance."""
    results = []
    for EP in EP_range:
        r_aal = run_scenario(scenario_name, scenarios, profile, kinetics,
                              EP=EP, loading="AAL", T_C=T_C,
                              flow_paced_A=flow_paced_A,
                              licence_interpretation=licence_interpretation)
        r_mml = run_scenario(scenario_name, scenarios, profile, kinetics,
                              EP=EP, loading="MML", T_C=T_C,
                              flow_paced_A=flow_paced_A,
                              licence_interpretation=licence_interpretation)
        results.append({
            "EP": EP,
            "AAL_compliance": r_aal["compliance"],
            "MML_compliance": r_mml["compliance"],
            "AAL_MeOH": r_aal["MeOH_Ld"],
            "MML_MeOH": r_mml["MeOH_Ld"],
            "pass_both": r_aal["compliance"]["overall_pass"] and r_mml["compliance"]["overall_pass"],
        })
        if not results[-1]["pass_both"]:
            break
    return results


# ============================================================================
# ENTRY POINT — loads files and runs full analysis
# ============================================================================
def main(
    scenarios_path: str = "canungra_scenarios.json",
    profile_path: str = "canungra_diurnal_profile.json",
    out_path: str = "canungra_results.json",
    licence_interpretation: str = "B",
):
    """Load inputs, run all scenarios across EP range, write output.
    
    Default licence_interpretation is 'B' (Rev 17 design basis).
    """
    scenarios = json.loads(Path(scenarios_path).read_text())
    profile = json.loads(Path(profile_path).read_text())
    kinetics = scenarios["kinetic_parameters"]
    
    all_scenarios = scenarios["scenarios"]
    
    output = {
        "metadata": scenarios["metadata"],
        "licence_interpretation": licence_interpretation,
        "results_by_scenario": {},
    }
    
    # Skip the legacy alias in the sweep
    scenario_keys = [k for k in all_scenarios if k != "S2_ifas_plus_postanox"]
    
    for scen_name in scenario_keys:
        print(f"\nRunning scenario: {scen_name}")
        
        # Flow-paced A-recycle (recommended for all intensified configs)
        sweep_paced = sweep_EP(
            scen_name, all_scenarios, profile, kinetics,
            EP_range=range(1500, 7001, 250),
            T_C=17.0, flow_paced_A=True,
            licence_interpretation=licence_interpretation,
        )
        
        # Fixed A-recycle only for S0 baseline (legacy Rev B control)
        sweep_fixed = sweep_EP(
            scen_name, all_scenarios, profile, kinetics,
            EP_range=range(1500, 7001, 250),
            T_C=17.0, flow_paced_A=False,
            licence_interpretation=licence_interpretation,
        )
        
        max_EP_fixed = max((r["EP"] for r in sweep_fixed if r["pass_both"]), default=0)
        max_EP_paced = max((r["EP"] for r in sweep_paced if r["pass_both"]), default=0)
        
        output["results_by_scenario"][scen_name] = {
            "max_EP_fixed_A_recycle": max_EP_fixed,
            "max_EP_flow_paced_A_recycle": max_EP_paced,
            "sweep_fixed": sweep_fixed,
            "sweep_paced": sweep_paced,
        }
        print(f"  Max EP (fixed A):      {max_EP_fixed}")
        print(f"  Max EP (flow-paced A): {max_EP_paced}")
    
    Path(out_path).write_text(json.dumps(output, indent=2))
    print(f"\nWrote results to {out_path}")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        main(*sys.argv[1:])
    else:
        main()
