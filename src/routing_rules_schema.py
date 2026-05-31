"""
Routing Rules Schema (E3, ARCH-2007E0A1).

Pydantic models for ``config/routing_rules.yaml``. Validated at FastAPI
startup so a malformed rules file fails fast — we do NOT wait until the
first synthesis arrives to discover a typo.

Also defines the ``RoutingDecision`` model that ``OutputRouter`` returns
to callers (the dashboard shows this so the user knows where the
artifact landed).

VETO COMPLIANCE:
- E3: Pydantic schema validation at FastAPI startup
- E7: regex word boundaries enforced via the Marker model's validator
- E8: rules are code (this file IS the schema)
- B4 from Phase 1: ruamel.yaml for round-trip preservation
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ════════════════════════════════════════════════════════════════════
#  ENUMS / LITERALS (kept as plain str classes to keep YAML readable)
# ════════════════════════════════════════════════════════════════════

# Allowed destination buckets. Match the proposal's "7 rules" + catch-all.
ALLOWED_DESTINATIONS = frozenset(
    {
        "proposals",
        "decisions",
        "handoffs",
        "reports",
        "archives",
        "failed_routings",   # E5 dead-letter
        "vault_mirror",      # vault-bound, but written by proposal_sync NOT router
        # COS vault destinations (dual-vault architecture)
        "proposals_vault",
        "handoffs_vault",
        "decisions_vault",
        "releases_vault",
    }
)

ALLOWED_SEVERITIES = frozenset({"HIGH", "MEDIUM", "LOW", "BACKLOG"})

# Allowed workflow phases (mirrors src.workflow_models.WorkflowPhase).
ALLOWED_PHASES = frozenset(
    {
        "backlog",
        "proposal",
        "beta_planning",
        "beta_execution",
        "beta",
        "alpha",
        "finalized",
        "deployed",
    }
)


# ════════════════════════════════════════════════════════════════════
#  RULE MODELS
# ════════════════════════════════════════════════════════════════════


class RoutingMarker(BaseModel):
    """A single marker that, when found outside any fenced code block,
    triggers the parent rule.

    The pattern is compiled with word-boundary anchors (E7) so that
    ``#boardroom`` does not match inside ``#boardrooming``.
    """

    model_config = ConfigDict(frozen=True)

    pattern: str = Field(
        ...,
        description="Literal marker text, e.g. '#boardroom'. Anchored to "
        r"word boundaries (\b) at compile time.",
    )
    case_sensitive: bool = Field(
        default=True,
        description="Whether matching is case-sensitive. Default true.",
    )

    @field_validator("pattern")
    @classmethod
    def _non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("marker.pattern must be non-empty")
        return value

    def to_regex(self) -> re.Pattern[str]:
        """Compile the marker into a word-bounded regex.

        E7 enforcement: every marker is wrapped in ``\b...\b`` so a
        partial-word collision (``#boardrooming``) cannot trigger the
        rule.
        """
        # Escape the literal then bound it. Note: hash (#) is not a word
        # character for \b purposes, so we use a custom boundary that
        # also handles markers that start with #.
        escaped = re.escape(self.pattern)
        if re.match(r"^\W", self.pattern):
            # Marker starts with non-word (e.g. '#'). Require non-word or
            # start-of-string before, and word-boundary after.
            boundary = rf"(?:(?<=^)|(?<=[^\w#])){escaped}\b"
        else:
            boundary = rf"\b{escaped}\b"
        flags = 0 if self.case_sensitive else re.IGNORECASE
        return re.compile(boundary, flags)


class RoutingRule(BaseModel):
    """A single routing rule.

    A council/agent output is matched against each rule's markers (in
    declaration order) AFTER fence-stripping. The first rule with at
    least one marker hit wins. If no rule matches, the catch-all (E1)
    fires.
    """

    model_config = ConfigDict(frozen=True)

    name: str = Field(
        ..., description="Human-readable rule name, e.g. 'boardroom_proposal'."
    )
    destination: str = Field(
        ...,
        description=(
            "Where the matched content is written. One of: "
            + ", ".join(sorted(ALLOWED_DESTINATIONS))
        ),
    )
    markers: List[RoutingMarker] = Field(
        default_factory=list,
        description="Markers whose presence triggers this rule. "
        "Empty list is only valid for catch-all (is_catchall=True).",
    )
    workflow_phase: str = Field(
        default="proposal",
        description="Workflow phase to stamp on the resulting artifact.",
    )
    severity: Optional[str] = Field(
        default=None,
        description="Severity to assign when this rule fires. May be None "
        "(routing infers severity from content).",
    )
    is_catchall: bool = Field(
        default=False,
        description="If true, this rule fires when no other rule matched. "
        "Exactly one rule in the file must have this set (E1).",
    )

    @field_validator("destination")
    @classmethod
    def _destination_allowed(cls, value: str) -> str:
        if value not in ALLOWED_DESTINATIONS:
            raise ValueError(
                f"destination={value!r} not in allowed set: "
                f"{sorted(ALLOWED_DESTINATIONS)}"
            )
        return value

    @field_validator("workflow_phase")
    @classmethod
    def _phase_allowed(cls, value: str) -> str:
        if value not in ALLOWED_PHASES:
            raise ValueError(
                f"workflow_phase={value!r} not in {sorted(ALLOWED_PHASES)}"
            )
        return value

    @field_validator("severity")
    @classmethod
    def _severity_allowed(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        if value not in ALLOWED_SEVERITIES:
            raise ValueError(
                f"severity={value!r} not in {sorted(ALLOWED_SEVERITIES)}"
            )
        return value

    @field_validator("name")
    @classmethod
    def _name_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("rule.name must be non-empty")
        return value


class RoutingRulesFile(BaseModel):
    """Top-level model for ``config/routing_rules.yaml``.

    Exactly one rule must be marked ``is_catchall: true`` (E1 — prevents
    silent data loss).
    """

    model_config = ConfigDict(frozen=True)

    version: str = Field(
        default="1.0",
        description="Schema version; bump when adding incompatible fields.",
    )
    rules: List[RoutingRule] = Field(
        ..., description="Routing rules evaluated in declaration order."
    )

    @field_validator("rules")
    @classmethod
    def _exactly_one_catchall(
        cls, value: List[RoutingRule]
    ) -> List[RoutingRule]:
        catchalls = [r for r in value if r.is_catchall]
        if len(catchalls) == 0:
            raise ValueError(
                "routing_rules.yaml must declare exactly one catch-all "
                "rule (is_catchall: true) — E1 of ARCH-2007E0A1."
            )
        if len(catchalls) > 1:
            names = ", ".join(r.name for r in catchalls)
            raise ValueError(
                f"routing_rules.yaml declares {len(catchalls)} catch-all "
                f"rules ({names}); exactly one is required."
            )
        # Catch-all must be last so non-catch-all rules get first refusal.
        if not value[-1].is_catchall:
            raise ValueError(
                "the catch-all rule must be the LAST entry in rules so "
                "specific rules match first."
            )
        return value


# ════════════════════════════════════════════════════════════════════
#  ROUTING DECISION (returned by OutputRouter.route())
# ════════════════════════════════════════════════════════════════════


class RoutingDecision(BaseModel):
    """The structured result of routing a single piece of content.

    Returned by ``OutputRouter.route(...)`` and included in the FastAPI
    /process response so the dashboard knows where the artifact landed.
    """

    model_config = ConfigDict(frozen=True)

    rule_name: str = Field(..., description="Which rule fired.")
    destination: str = Field(
        ..., description="Destination bucket (matches RoutingRule.destination)."
    )
    workflow_phase: str = Field(
        default="proposal", description="Workflow phase stamped on the artifact."
    )
    severity: Optional[str] = Field(
        default=None, description="Severity assigned to the artifact."
    )
    matched_markers: List[str] = Field(
        default_factory=list,
        description="The marker patterns that matched. Empty for catch-all.",
    )
    context: dict = Field(
        default_factory=dict,
        description="Free-form context bag (severity hint, fixtures, etc.).",
    )


# ════════════════════════════════════════════════════════════════════
#  LOADER
# ════════════════════════════════════════════════════════════════════


def load_routing_rules(yaml_path: Path) -> RoutingRulesFile:
    """Load and validate ``config/routing_rules.yaml``.

    Uses ruamel.yaml (consistency with schema_validator.py) and raises
    ``pydantic.ValidationError`` if anything is malformed. Call this at
    FastAPI startup (E3): a routing-rules typo MUST NOT wait for the
    first synthesis to surface.
    """
    from ruamel.yaml import YAML

    yaml = YAML(typ="safe")
    with open(yaml_path, "r", encoding="utf-8") as f:
        data = yaml.load(f)
    return RoutingRulesFile.model_validate(data)


__all__ = [
    "ALLOWED_DESTINATIONS",
    "ALLOWED_SEVERITIES",
    "ALLOWED_PHASES",
    "RoutingMarker",
    "RoutingRule",
    "RoutingRulesFile",
    "RoutingDecision",
    "load_routing_rules",
]
