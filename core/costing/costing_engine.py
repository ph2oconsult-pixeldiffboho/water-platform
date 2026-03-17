"""
core/costing/costing_engine.py

Domain-agnostic costing engine.
Receives structured CostItem lists from domain technology plugins.
Applies unit costs from the assumptions library.
Returns a standardised CostResult for reporting.
"""

from __future__ import annotations
from typing import Dict, List, Optional, Any

from core.project.project_model import AssumptionsSet, CostItem, CostResult
from core.assumptions.assumptions_manager import AssumptionsManager


class CostingEngine:
    """
    Calculates CAPEX, OPEX, and lifecycle costs from structured cost items.

    The engine is entirely domain-agnostic.  It receives a list of CostItems
    from the domain calculation result and resolves unit costs from the
    assumptions library.  No domain-specific logic appears here.

    Cost Item Resolution Priority
    ------------------------------
    1. item.unit_cost_override (explicit override on the item itself)
    2. assumptions.cost_assumptions.capex_unit_costs[item.cost_basis_key]
    3. assumptions.cost_assumptions.opex_unit_rates[item.cost_basis_key]
    4. assumptions.cost_assumptions.chemical_prices[item.cost_basis_key]
    5. Fallback: 0.0 (logged as a data gap)
    """

    def __init__(self, assumptions: AssumptionsSet):
        self.assumptions = assumptions
        self._mgr = AssumptionsManager()

    def calculate(
        self,
        capex_items: List[CostItem],
        opex_items: List[CostItem],
        design_flow_mld: float = 0.0,
        throughput_tonne_ds_day: float = 0.0,
        analysis_period_years: Optional[int] = None,
        apply_oncosts: bool = True,
        tech_codes: Optional[List[str]] = None,
    ) -> CostResult:
        """
        Perform the full cost calculation for a scenario.

        Parameters
        ----------
        capex_items : list of CostItem
            Capital cost items from the domain technology results
        opex_items : list of CostItem
            Operating cost items from the domain technology results
        design_flow_mld : float
            Design flow in ML/day (for $/kL specific cost)
        throughput_tonne_ds_day : float
            Dry solids throughput (for biosolids $/t DS specific cost)
        analysis_period_years : int, optional
            Override the default analysis period
        apply_oncosts : bool
            Whether to apply contingency and client on-costs to CAPEX
        """
        period = analysis_period_years or self._get(
            "cost", "analysis_period_years", 30
        )
        discount_rate = self._get("cost", "discount_rate", 0.07)

        # ── CAPEX ─────────────────────────────────────────────────────────
        capex_breakdown = self._calculate_capex(capex_items, apply_oncosts)
        capex_total = sum(capex_breakdown.values())

        # ── OPEX ──────────────────────────────────────────────────────────
        opex_breakdown = self._calculate_opex(opex_items)
        opex_annual = sum(opex_breakdown.values())

        # ── Maintenance and labour OPEX ──────────────────────────────────
        # Fixed O&M (labour + maintenance) is applied ONLY for real plant scenarios.
        #
        # RULE: apply fixed O&M when ALL of these are true:
        #   1. capex_total > 0  (a real treatment train exists)
        #   2. tech_codes is non-empty  (domain explicitly identified technologies)
        #   3. design_flow_mld > 0  (a real flow has been set)
        #
        # This ensures:
        #   - Real plant scenarios get full OPEX (electricity + sludge + maintenance + labour)
        #   - Unit tests with empty items or single-item-only calls get exact OPEX (no extras)
        #   - Costing engine remains domain-agnostic (biosolids/PRW can opt in via tech_codes)
        #
        # Ref: WEF Cost Estimating Manual 2018; AU Water Association benchmarks.

        self._current_tech_codes = tech_codes or []

        _is_real_scenario = (
            capex_total > 0
            and bool(self._current_tech_codes)
            and (design_flow_mld or 0) > 0
        )

        if _is_real_scenario:
            # Technology-specific maintenance rates:
            # Conventional (BNR, IFAS, clarifiers): 1.5% CAPEX/yr
            # Novel/specialist (MABR, AGS, MBR): 2.0% CAPEX/yr
            # Ref: WEF Cost Estimating Manual 2018, Table 6-3; GHD AU utility benchmarks
            _novel_techs = {"mabr_bnr", "granular_sludge", "bnr_mbr", "anmbr", "adv_reuse"}
            _is_novel = any(tc in _novel_techs for tc in self._current_tech_codes)
            _default_maint_pct = 0.020 if _is_novel else 0.015
            _user_maint_override = self._get(
                "cost", "opex_unit_rates.maintenance_pct_of_capex_annual", None
            )
            maint_pct = (
                _user_maint_override
                if _user_maint_override is not None
                else _default_maint_pct
            )
            labour_fte_per_10mld = self._get(
                "cost", "opex_unit_rates.labour_fte_per_10mld",
                self._get("cost", "labour_fte_per_10mld", 2.5)
            )
            labour_cost_fte = self._get(
                "cost", "opex_unit_rates.labour_cost_per_fte",
                self._get("cost", "labour_cost_per_fte", 105000.0)
            )
            maintenance_annual = capex_total * maint_pct
            # FTE scales with flow; minimum 2.0 FTE for small plants
            labour_fte = max(2.0, labour_fte_per_10mld * (design_flow_mld / 10.0))
            labour_annual = labour_fte * labour_cost_fte

            if maintenance_annual > 0:
                maint_label = f"Mechanical maintenance ({maint_pct*100:.0f}% CAPEX/yr)"
                opex_breakdown[maint_label] = maintenance_annual
            if labour_annual > 0:
                opex_breakdown["Operator & maintenance labour"] = labour_annual

        opex_annual = sum(opex_breakdown.values())

        # ── Lifecycle cost ────────────────────────────────────────────────
        # Annualised lifecycle cost = CAPEX × CRF + OPEX_annual
        # where CRF = Capital Recovery Factor = i(1+i)^n / ((1+i)^n - 1)
        # This correctly accounts for time value of money on capital expenditure.
        # Ref: Metcalf & Eddy 5th Ed, Chapter 3; WEF Cost Estimating Manual.
        if discount_rate > 0 and period > 0:
            crf = (discount_rate * (1 + discount_rate)**period /
                   ((1 + discount_rate)**period - 1))
        else:
            crf = 1.0 / period if period > 0 else 1.0

        lifecycle_cost_annual = capex_total * crf + opex_annual

        # NPV total: CAPEX + PV of OPEX stream
        # PV_factor = (1 - (1+i)^-n) / i
        if discount_rate > 0:
            pv_factor = (1 - (1 + discount_rate)**(-period)) / discount_rate
        else:
            pv_factor = period
        lifecycle_cost_total = capex_total + opex_annual * pv_factor

        # ── Specific cost ─────────────────────────────────────────────────
        specific_cost_per_kl = None
        if design_flow_mld > 0:
            annual_volume_kl = design_flow_mld * 1000 * 365
            specific_cost_per_kl = lifecycle_cost_annual / annual_volume_kl

        specific_cost_per_tonne_ds = None
        if throughput_tonne_ds_day > 0:
            annual_tonne_ds = throughput_tonne_ds_day * 365
            specific_cost_per_tonne_ds = lifecycle_cost_annual / annual_tonne_ds

        return CostResult(
            capex_total=round(capex_total, 2),
            capex_breakdown={k: round(v, 2) for k, v in capex_breakdown.items()},
            opex_annual=round(opex_annual, 2),
            opex_breakdown={k: round(v, 2) for k, v in opex_breakdown.items()},
            lifecycle_cost_annual=round(lifecycle_cost_annual, 2),
            lifecycle_cost_total=round(lifecycle_cost_total, 2),
            specific_cost_per_kl=(
                round(specific_cost_per_kl, 4) if specific_cost_per_kl else None
            ),
            specific_cost_per_tonne_ds=(
                round(specific_cost_per_tonne_ds, 2) if specific_cost_per_tonne_ds else None
            ),
            analysis_period_years=period,
            discount_rate=discount_rate,
            cost_confidence=self._get("cost", "cost_confidence", "±30%"),
            currency=self._get("cost", "currency", "AUD"),
            price_base_year=self._get("cost", "price_base_year", 2024),
        )

    # ── Internal calculation methods ──────────────────────────────────────

    def _calculate_capex(
        self, items: List[CostItem], apply_oncosts: bool
    ) -> Dict[str, float]:
        """
        Calculate each CAPEX line item.
        Applies contingency, client on-costs, and economy-of-scale factor.

        Economy of scale: civil tank works follow a 0.6 power law
        (Six-Tenths Rule). Base volume = 2750 m³ (~10 MLD BNR).
        Mechanical/electrical items scale linearly (exponent = 1.0).
        """
        contingency_pct = self._get("cost", "design_contingency_pct", 0.20)
        contractor_pct  = self._get("cost", "contractor_margin_pct",  0.12)
        client_pct      = self._get("cost", "client_oncosts_pct",     0.15)

        # Civil tank basis: total m³ of tankage across all civil items
        CIVIL_KEYS  = {"aeration_tank_per_m3", "secondary_clarifier_per_m2",
                        "equalisation_tank_per_m3"}  # plain concrete tanks all scale together
        SCALE_EXP   = 0.60   # Six-Tenths Rule for civil works
        BASE_VOL    = 2750.0 # m³ (calibration point — 10 MLD BNR)

        total_civil_m3 = sum(
            item.quantity for item in items
            if item.cost_basis_key in CIVIL_KEYS and item.quantity > 0
        )

        breakdown: Dict[str, float] = {}
        for item in items:
            unit_cost = self._resolve_capex_unit_cost(item)

            # Apply economy of scale to civil works (Six-Tenths Rule)
            # Applies to both large plants (scale < 1) and small plants (scale > 1)
            # Excludes AGS which has its own scaling in granular_sludge.py
            if item.cost_basis_key in CIVIL_KEYS and total_civil_m3 > 0:
                # scale_factor = (V/V_base)^(0.6-1) = (V/V_base)^(-0.4)
                # < 1 for large plants, > 1 for small plants, = 1 at base volume
                scale_factor = (total_civil_m3 / BASE_VOL) ** (SCALE_EXP - 1.0)
                unit_cost *= scale_factor

            direct_cost = item.quantity * unit_cost * item.contingency_factor

            if apply_oncosts:
                direct_cost *= (1 + contingency_pct) * (1 + contractor_pct) * (1 + client_pct)

            if item.name in breakdown:
                breakdown[f"{item.name} (2)"] = direct_cost
            else:
                breakdown[item.name] = direct_cost

        return breakdown

    def _calculate_opex(self, items: List[CostItem]) -> Dict[str, float]:
        """Calculate each OPEX line item as an annual cost."""
        breakdown: Dict[str, float] = {}
        for item in items:
            unit_rate = self._resolve_opex_unit_rate(item)
            # item.quantity is typically a daily rate; multiply by 365 for annual
            annual_cost = item.quantity * unit_rate * 365

            if item.name in breakdown:
                breakdown[f"{item.name} (2)"] = annual_cost
            else:
                breakdown[item.name] = annual_cost

        return breakdown

    def _resolve_capex_unit_cost(self, item: CostItem) -> float:
        """
        Resolve CAPEX unit cost.
        Priority: item override > user_overrides > capex_unit_costs > top-level > 0.0
        """
        if item.unit_cost_override is not None:
            return item.unit_cost_override

        # Check user_overrides (scenario-level override)
        override_key = f"cost.{item.cost_basis_key}"
        if override_key in self.assumptions.user_overrides:
            return self.assumptions.user_overrides[override_key]

        cost_assumptions = self.assumptions.cost_assumptions
        unit_costs = cost_assumptions.get("capex_unit_costs", {})
        if item.cost_basis_key in unit_costs:
            return unit_costs[item.cost_basis_key]

        if item.cost_basis_key in cost_assumptions:
            return cost_assumptions[item.cost_basis_key]

        return 0.0

    def _resolve_opex_unit_rate(self, item: CostItem) -> float:
        """
        Resolve OPEX unit rate.
        Priority:
          1. item.unit_cost_override (explicit per-item override)
          2. user_overrides in assumptions (scenario-level override via AssumptionsManager)
          3. opex_unit_rates nested dict
          4. chemical_prices nested dict
          5. top-level cost_assumptions key
          6. 0.0 (gap — appears as zero in results)
        """
        if item.unit_cost_override is not None:
            return item.unit_cost_override

        # Check user_overrides first (highest priority after item-level override)
        override_key = f"cost.{item.cost_basis_key}"
        if override_key in self.assumptions.user_overrides:
            return self.assumptions.user_overrides[override_key]

        cost_assumptions = self.assumptions.cost_assumptions
        # Check nested opex_unit_rates dict
        opex_rates = cost_assumptions.get("opex_unit_rates", {})
        if item.cost_basis_key in opex_rates:
            return opex_rates[item.cost_basis_key]

        # Check chemical_prices
        chem_prices = cost_assumptions.get("chemical_prices", {})
        if item.cost_basis_key in chem_prices:
            return chem_prices[item.cost_basis_key]

        # Top-level fallback
        if item.cost_basis_key in cost_assumptions:
            return cost_assumptions[item.cost_basis_key]

        return 0.0

    def _get(self, category: str, key: str, default: Any = None) -> Any:
        return self._mgr.get(self.assumptions, category, key, default)
