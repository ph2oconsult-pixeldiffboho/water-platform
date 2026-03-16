"""
core/validation/validation_engine.py

Shared validation runner.
Core validators handle universal checks (required fields, numeric ranges).
Domain modules register hooks for domain-specific validation rules.
"""

from __future__ import annotations
from typing import Any, Callable, List, Optional

from core.project.project_model import (
    ValidationLevel, ValidationMessage, ValidationResult,
)


class ValidationEngine:
    """
    Runs validation across inputs and domain results.

    Core validators (defined here) handle:
    - Required field presence
    - Numeric range / bounds checking
    - Type checks

    Domain validators (registered via register_domain_hook) handle:
    - Domain-specific mass balance checks
    - Engineering sanity checks (e.g. SRT vs flux consistency)
    - Regulatory threshold checks
    """

    def __init__(self):
        self._domain_hooks: List[Callable] = []

    def register_domain_hook(self, hook: Callable) -> None:
        """
        Register a domain-specific validation function.

        The hook must have signature:
            hook(inputs: Any, domain_result: Any = None) -> List[ValidationMessage]
        """
        self._domain_hooks.append(hook)

    def clear_hooks(self) -> None:
        """Remove all registered domain hooks (useful for testing)."""
        self._domain_hooks.clear()

    def validate(
        self,
        inputs: Any,
        domain_result: Optional[Any] = None,
    ) -> ValidationResult:
        """
        Run all validations and return a consolidated result.

        Parameters
        ----------
        inputs : Any
            The domain input object (e.g. WastewaterInputs)
        domain_result : Any, optional
            Intermediate domain calculation result for cross-checks
        """
        messages: List[ValidationMessage] = []

        # ── Shared core checks ────────────────────────────────────────────
        messages.extend(self._check_required_fields(inputs))
        messages.extend(self._check_numeric_ranges(inputs))
        messages.extend(self._check_positive_values(inputs))
        messages.extend(self._check_design_flow(inputs))

        # ── Domain-specific hooks ─────────────────────────────────────────
        for hook in self._domain_hooks:
            try:
                hook_messages = hook(inputs, domain_result)
                messages.extend(hook_messages)
            except Exception as e:
                messages.append(ValidationMessage(
                    level=ValidationLevel.WARNING,
                    field="validation_engine",
                    message=f"Domain validation hook error: {str(e)}",
                ))

        # ── Summarise ─────────────────────────────────────────────────────
        critical = [m for m in messages if m.level == ValidationLevel.CRITICAL]
        warnings = [m for m in messages if m.level == ValidationLevel.WARNING]
        infos = [m for m in messages if m.level == ValidationLevel.INFO]

        return ValidationResult(
            is_valid=len(critical) == 0,
            has_warnings=len(warnings) > 0,
            message_count_critical=len(critical),
            message_count_warning=len(warnings),
            message_count_info=len(infos),
            messages=[m.to_dict() for m in messages],
        )

    # ── Core validators ───────────────────────────────────────────────────

    def _check_required_fields(self, inputs: Any) -> List[ValidationMessage]:
        """Check that all required fields have been provided."""
        messages = []
        required_fields = getattr(inputs, "_required_fields", [])
        for field_name in required_fields:
            value = getattr(inputs, field_name, None)
            if value is None or value == "" or value == []:
                messages.append(ValidationMessage(
                    level=ValidationLevel.CRITICAL,
                    field=field_name,
                    message=(
                        f"'{field_name}' is required and has not been provided. "
                        "Calculations cannot proceed without this value."
                    ),
                ))
        return messages

    def _check_numeric_ranges(self, inputs: Any) -> List[ValidationMessage]:
        """
        Check numeric fields against defined bounds.
        Bounds are defined on the input class as:
            _field_bounds = {"field_name": (min, max)}
        Use None for no lower or upper bound.
        """
        messages = []
        bounds = getattr(inputs, "_field_bounds", {})
        for field_name, (min_val, max_val) in bounds.items():
            value = getattr(inputs, field_name, None)
            if value is None:
                continue
            if not isinstance(value, (int, float)):
                continue
            if min_val is not None and value < min_val:
                messages.append(ValidationMessage(
                    level=ValidationLevel.WARNING,
                    field=field_name,
                    value=value,
                    message=(
                        f"'{field_name}' = {value} is below the typical minimum "
                        f"of {min_val}. Please verify this value is correct."
                    ),
                ))
            if max_val is not None and value > max_val:
                messages.append(ValidationMessage(
                    level=ValidationLevel.CRITICAL,
                    field=field_name,
                    value=value,
                    message=(
                        f"'{field_name}' = {value} exceeds the maximum permitted "
                        f"value of {max_val}. Calculations will not run."
                    ),
                ))
        return messages

    def _check_positive_values(self, inputs: Any) -> List[ValidationMessage]:
        """Check that fields that must be positive are positive."""
        messages = []
        positive_fields = getattr(inputs, "_positive_fields", [])
        for field_name in positive_fields:
            value = getattr(inputs, field_name, None)
            if value is not None and isinstance(value, (int, float)) and value <= 0:
                messages.append(ValidationMessage(
                    level=ValidationLevel.CRITICAL,
                    field=field_name,
                    value=value,
                    message=(
                        f"'{field_name}' must be a positive value. "
                        f"Received: {value}."
                    ),
                ))
        return messages

    def _check_design_flow(self, inputs: Any) -> List[ValidationMessage]:
        """Universal check: design flow must be set and positive."""
        messages = []
        flow = getattr(inputs, "design_flow_mld", None)
        if flow is None:
            messages.append(ValidationMessage(
                level=ValidationLevel.CRITICAL,
                field="design_flow_mld",
                message=(
                    "Design flow (ML/day) is required. "
                    "Please enter the plant design flow."
                ),
            ))
        elif flow <= 0:
            messages.append(ValidationMessage(
                level=ValidationLevel.CRITICAL,
                field="design_flow_mld",
                value=flow,
                message="Design flow must be greater than zero.",
            ))
        elif flow > 1000:
            messages.append(ValidationMessage(
                level=ValidationLevel.WARNING,
                field="design_flow_mld",
                value=flow,
                message=(
                    f"Design flow of {flow} ML/day is very large. "
                    "Please confirm this is correct (input is in ML/day, not L/day)."
                ),
            ))
        return messages


# ── Convenience builder ───────────────────────────────────────────────────────

def make_validation_message(
    level: str,
    field: str,
    message: str,
    value: Any = None,
) -> ValidationMessage:
    """Helper for domain hooks to construct ValidationMessage objects cleanly."""
    return ValidationMessage(
        level=ValidationLevel(level),
        field=field,
        message=message,
        value=value,
    )
