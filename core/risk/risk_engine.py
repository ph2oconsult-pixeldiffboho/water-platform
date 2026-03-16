"""
core/risk/risk_engine.py

Domain-agnostic risk framework.
Scores, aggregates, and classifies risk items provided by domain modules.
Domain modules extend the framework by registering additional risk items.
"""

from __future__ import annotations
from typing import Dict, List, Optional, Any

from core.project.project_model import AssumptionsSet, RiskItem, RiskResult
from core.assumptions.assumptions_manager import AssumptionsManager


# Risk level thresholds (0–25 scale: 5×5 matrix)
RISK_LEVEL_THRESHOLDS = {
    "Low": (0, 6),
    "Medium": (6, 12),
    "High": (12, 20),
    "Very High": (20, 26),
}

# Category weights (must sum to 1.0)
DEFAULT_CATEGORY_WEIGHTS = {
    "technical": 0.30,
    "implementation": 0.25,
    "operational": 0.25,
    "regulatory": 0.20,
}


class RiskEngine:
    """
    Scores and aggregates risk items into a standardised RiskResult.

    Risk items are provided by domain modules (and optionally enriched by the
    domain interface).  The engine calculates individual item scores, computes
    weighted category averages, and produces an overall risk level.

    Scoring Matrix (5×5)
    --------------------
    Score = Likelihood (1–5) × Consequence (1–5) → range 1–25
    """

    def __init__(self, assumptions: AssumptionsSet):
        self.assumptions = assumptions
        self._mgr = AssumptionsManager()

    def calculate(
        self,
        risk_items: List[RiskItem],
        category_weights: Optional[Dict[str, float]] = None,
    ) -> RiskResult:
        """
        Calculate risk scores from a list of RiskItems.

        Parameters
        ----------
        risk_items : list of RiskItem
            All risk items for this scenario, provided by domain module
        category_weights : dict, optional
            Override default category weights {category_name: weight}
        """
        weights = category_weights or self._load_weights()

        # Score all items
        for item in risk_items:
            item.calculate_score()

        # Group by category
        by_category: Dict[str, List[RiskItem]] = {}
        for item in risk_items:
            cat = item.category.lower()
            by_category.setdefault(cat, []).append(item)

        # Average score per category
        category_averages: Dict[str, float] = {}
        for cat, items in by_category.items():
            if items:
                category_averages[cat] = sum(i.score for i in items) / len(items)
            else:
                category_averages[cat] = 0.0

        # Weighted overall score (as 0–100)
        total_weight = 0.0
        weighted_score = 0.0
        for cat, weight in weights.items():
            avg = category_averages.get(cat, 0.0)
            # Normalise 1–25 score to 0–100
            normalised = (avg / 25.0) * 100.0
            weighted_score += normalised * weight
            total_weight += weight

        if total_weight > 0:
            overall_score = weighted_score / total_weight
        else:
            overall_score = 0.0

        # Classify overall level using 0–100 scale
        overall_level = self._classify_level_pct(overall_score)

        # Normalise per-category scores to 0–100
        def cat_score_pct(cat: str) -> float:
            avg = category_averages.get(cat, 0.0)
            return round((avg / 25.0) * 100.0, 1)

        # Collect domain-specific (any category not in the standard four)
        standard_cats = {"technical", "implementation", "operational", "regulatory"}
        domain_specific_items = [
            item for item in risk_items
            if item.category.lower() not in standard_cats
        ]
        domain_score = 0.0
        if domain_specific_items:
            avg = sum(i.score for i in domain_specific_items) / len(domain_specific_items)
            domain_score = round((avg / 25.0) * 100.0, 1)

        narrative = self._generate_narrative(overall_level, category_averages, risk_items)

        return RiskResult(
            overall_score=round(overall_score, 1),
            overall_level=overall_level,
            technical_score=cat_score_pct("technical"),
            implementation_score=cat_score_pct("implementation"),
            operational_score=cat_score_pct("operational"),
            regulatory_score=cat_score_pct("regulatory"),
            domain_specific_score=domain_score,
            risk_items=risk_items,
            risk_narrative=narrative,
        )

    # ── Helpers ───────────────────────────────────────────────────────────

    def _load_weights(self) -> Dict[str, float]:
        risk_config = self.assumptions.risk_assumptions
        return {
            "technical": risk_config.get("weight_technical", 0.30),
            "implementation": risk_config.get("weight_implementation", 0.25),
            "operational": risk_config.get("weight_operational", 0.25),
            "regulatory": risk_config.get("weight_regulatory", 0.20),
        }

    @staticmethod
    def _classify_level_pct(score_pct: float) -> str:
        """Classify a 0–100 risk score into a level."""
        if score_pct < 24:
            return "Low"
        elif score_pct < 48:
            return "Medium"
        elif score_pct < 72:
            return "High"
        else:
            return "Very High"

    @staticmethod
    def _classify_item_level(score: float) -> str:
        """Classify a 1–25 item score."""
        if score <= 6:
            return "Low"
        elif score <= 12:
            return "Medium"
        elif score <= 20:
            return "High"
        else:
            return "Very High"

    def _generate_narrative(
        self,
        overall_level: str,
        category_averages: Dict[str, float],
        risk_items: List[RiskItem],
    ) -> str:
        """Generate a short automated risk narrative."""
        high_items = [
            item for item in risk_items
            if item.score > 12
        ]
        high_categories = [
            cat for cat, avg in category_averages.items()
            if avg > 12
        ]

        lines = [
            f"The overall risk level for this scenario is assessed as **{overall_level}**.",
        ]

        if high_categories:
            cats_str = ", ".join(c.replace("_", " ").title() for c in high_categories)
            lines.append(
                f"Elevated risk is identified in the following categories: {cats_str}."
            )

        if high_items:
            item_names = ", ".join(item.name for item in high_items[:3])
            if len(high_items) > 3:
                item_names += f" and {len(high_items) - 3} others"
            lines.append(
                f"Key risk items requiring attention include: {item_names}."
            )

        if overall_level in ("High", "Very High"):
            lines.append(
                "Mitigation measures should be identified and incorporated into "
                "the preferred option design before proceeding to detailed design."
            )

        return " ".join(lines)
