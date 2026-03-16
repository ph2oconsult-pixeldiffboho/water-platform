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

        # ── Lifecycle cost ────────────────────────────────────────────────
        # Simple annualised method: CAPEX / period + OPEX
        # Future: DCF using discount rate
        lifecycle_cost_annual = capex_total / period + opex_annual
        lifecycle_cost_total = capex_total + opex_annual * period

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
        Applies contingency and client on-costs if apply_oncosts is True.
        """
        contingency_pct = self._get("cost", "design_contingency_pct", 0.20)
        contractor_pct = self._get("cost", "contractor_margin_pct", 0.12)
        client_pct = self._get("cost", "client_oncosts_pct", 0.15)

        breakdown: Dict[str, float] = {}
        for item in items:
            unit_cost = self._resolve_capex_unit_cost(item)
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
