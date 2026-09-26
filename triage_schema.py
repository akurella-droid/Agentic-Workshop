"""Triage-decision schema: the single contract Epic 2 and Epic 3 import.

Defines the shape of a valid triage decision per TRIAGE_POLICY.md and
SPEC-epic-1 (CAP-1): a category, a priority, a route and a one-sentence
rationale, each restricted to its allowed values, with the route required
to match its category.
"""

import json

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator, model_validator
from typing import Literal

CATEGORIES = ("billing", "bug", "access", "performance", "how-to")
PRIORITIES = ("P1", "P2", "P3", "P4")
ROUTES = ("billing-team", "bug-team", "access-team", "performance-team", "how-to-team")

# Fixed category -> route mapping from TRIAGE_POLICY.md.
CATEGORY_TO_ROUTE = {
    "billing": "billing-team",
    "bug": "bug-team",
    "access": "access-team",
    "performance": "performance-team",
    "how-to": "how-to-team",
}


class TriageDecision(BaseModel):
    """A validated triage decision: category, priority, route and rationale."""

    model_config = ConfigDict(extra="forbid")

    category: Literal[CATEGORIES]
    priority: Literal[PRIORITIES]
    route: Literal[ROUTES]
    rationale: str

    @field_validator("rationale")
    @classmethod
    def rationale_not_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("rationale must not be empty")
        return value

    @model_validator(mode="after")
    def route_matches_category(self) -> "TriageDecision":
        expected_route = CATEGORY_TO_ROUTE[self.category]
        if self.route != expected_route:
            raise ValueError(
                f"route '{self.route}' does not match category '{self.category}'; "
                f"expected route '{expected_route}'"
            )
        return self


def _format_validation_error(exc: ValidationError) -> str:
    """Build a message that names every offending field, no raw traceback."""
    parts = []
    for error in exc.errors():
        loc = ".".join(str(part) for part in error["loc"]) if error["loc"] else "decision"
        parts.append(f"{loc}: {error['msg']}")
    return "Invalid triage decision - " + "; ".join(parts)


def validate_decision(data: dict | str) -> TriageDecision:
    """Validate a dict or JSON string as a TriageDecision.

    Raises ValueError whose message names every offending field.
    """
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid triage decision - input is not valid JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError(
            "Invalid triage decision - a JSON object is expected, got "
            f"{type(data).__name__}"
        )

    try:
        return TriageDecision.model_validate(data)
    except ValidationError as exc:
        raise ValueError(_format_validation_error(exc)) from exc
