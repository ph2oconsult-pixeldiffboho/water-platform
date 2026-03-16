"""
core/assumptions/assumptions_manager.py

Manages the full lifecycle of engineering assumptions.
Loads domain defaults from YAML libraries, applies user overrides,
and tracks all changes for auditability.
"""

from __future__ import annotations
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional
import yaml

from core.project.project_model import AssumptionsSet, DomainType


DEFAULTS_DIR = Path(__file__).parent / "defaults"


class AssumptionsManager:
    """
    Manages the full lifecycle of assumptions for a scenario.

    Responsibilities
    ----------------
    - Load domain defaults from YAML libraries (merged with shared defaults)
    - Apply per-scenario user overrides
    - Track all overrides with timestamps and reasons (audit trail)
    - Provide a clean get() interface for engine modules to resolve values
    """

    # ── Load defaults ─────────────────────────────────────────────────────

    def load_defaults(self, domain: DomainType) -> AssumptionsSet:
        """
        Load and merge shared + domain-specific defaults.
        Domain-specific values take precedence over shared values.
        """
        shared = self._load_yaml(DEFAULTS_DIR / "shared_defaults.yaml")
        domain_file = DEFAULTS_DIR / f"{domain.value}_defaults.yaml"

        if domain_file.exists():
            domain_specific = self._load_yaml(domain_file)
        else:
            domain_specific = {}

        # Deep merge: domain-level category dicts override shared category dicts
        merged = self._deep_merge(shared, domain_specific)

        return AssumptionsSet(
            domain=domain,
            base_version="default",
            cost_assumptions=merged.get("cost_assumptions", {}),
            carbon_assumptions=merged.get("carbon_assumptions", {}),
            risk_assumptions=merged.get("risk_assumptions", {}),
            engineering_assumptions=merged.get("engineering_assumptions", {}),
        )

    # ── Apply overrides ───────────────────────────────────────────────────

    def apply_override(
        self,
        assumptions: AssumptionsSet,
        category: str,
        key: str,
        value: Any,
        override_reason: str = "",
        author: str = "",
    ) -> AssumptionsSet:
        """
        Apply a user override to a single assumption.
        Returns a new AssumptionsSet (immutable pattern) so callers
        can safely store the previous version for comparison.

        Parameters
        ----------
        category : str
            One of 'cost', 'carbon', 'risk', 'engineering'
        key : str
            The assumption key within that category dict
        value : Any
            The new value
        override_reason : str
            Engineering justification (captured in audit log)
        author : str
            Who made the change
        """
        updated = deepcopy(assumptions)

        # Resolve the correct dict and update it
        category_attr = f"{category}_assumptions"
        category_dict: Dict = getattr(updated, category_attr, {})

        # Handle nested keys with dot notation (e.g. "capex_unit_costs.mbr_membrane_per_m2")
        parts = key.split(".", 1)
        if len(parts) == 2:
            parent_key, child_key = parts
            if parent_key not in category_dict:
                category_dict[parent_key] = {}
            category_dict[parent_key][child_key] = value
        else:
            category_dict[key] = value

        # Record override for audit trail
        override_key = f"{category}.{key}"
        updated.user_overrides[override_key] = value
        updated.override_log.append({
            "timestamp": datetime.utcnow().isoformat(),
            "category": category,
            "key": key,
            "new_value": value,
            "reason": override_reason,
            "author": author,
        })

        return updated

    def reset_override(
        self,
        assumptions: AssumptionsSet,
        category: str,
        key: str,
        domain: DomainType,
    ) -> AssumptionsSet:
        """
        Reset a single override back to the library default.
        """
        defaults = self.load_defaults(domain)
        category_attr = f"{category}_assumptions"
        default_value = getattr(defaults, category_attr, {}).get(key)

        if default_value is not None:
            updated = self.apply_override(
                assumptions,
                category=category,
                key=key,
                value=default_value,
                override_reason="Reset to default",
            )
            override_key = f"{category}.{key}"
            updated.user_overrides.pop(override_key, None)
            return updated
        return assumptions

    # ── Resolve values ────────────────────────────────────────────────────

    def get(
        self,
        assumptions: AssumptionsSet,
        category: str,
        key: str,
        default: Any = None,
    ) -> Any:
        """
        Resolve a single assumption value.
        User overrides take priority over category dict values.
        Falls back to `default` if key is not found anywhere.

        Parameters
        ----------
        category : str
            'cost', 'carbon', 'risk', or 'engineering'
        key : str
            Key within the category dict (dot notation supported for nested)
        """
        override_key = f"{category}.{key}"
        if override_key in assumptions.user_overrides:
            return assumptions.user_overrides[override_key]

        category_dict: Dict = getattr(
            assumptions, f"{category}_assumptions", {}
        )

        parts = key.split(".", 1)
        if len(parts) == 2:
            parent_key, child_key = parts
            return category_dict.get(parent_key, {}).get(child_key, default)
        return category_dict.get(key, default)

    def get_override_summary(self, assumptions: AssumptionsSet) -> list:
        """Return a human-readable list of all user overrides."""
        return [
            {
                "category": entry.get("category"),
                "key": entry.get("key"),
                "new_value": entry.get("new_value"),
                "reason": entry.get("reason", ""),
                "timestamp": entry.get("timestamp", ""),
                "author": entry.get("author", ""),
            }
            for entry in assumptions.override_log
        ]

    # ── Utilities ─────────────────────────────────────────────────────────

    @staticmethod
    def _load_yaml(path: Path) -> Dict:
        if not path.exists():
            return {}
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    @staticmethod
    def _deep_merge(base: Dict, override: Dict) -> Dict:
        """
        Recursively merge two dicts.
        Values in `override` take precedence.
        Nested dicts are merged, not replaced wholesale.
        """
        result = deepcopy(base)
        for key, value in override.items():
            if (
                key in result
                and isinstance(result[key], dict)
                and isinstance(value, dict)
            ):
                result[key] = AssumptionsManager._deep_merge(result[key], value)
            else:
                result[key] = deepcopy(value)
        return result
