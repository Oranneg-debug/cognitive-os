"""Tests for src.routing_rules_schema (E3 + E1 + E7 + E8)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.routing_rules_schema import (
    ALLOWED_DESTINATIONS,
    ALLOWED_SEVERITIES,
    RoutingDecision,
    RoutingMarker,
    RoutingRule,
    RoutingRulesFile,
    load_routing_rules,
)


ROOT = Path(__file__).resolve().parent.parent
RULES_PATH = ROOT / "config" / "routing_rules.yaml"


# ════════════════════════════════════════════════════════════════════
#  Marker model + E7 word boundary
# ════════════════════════════════════════════════════════════════════


def test_marker_rejects_empty_pattern() -> None:
    with pytest.raises(ValidationError):
        RoutingMarker(pattern="")


def test_marker_compiles_to_word_bounded_regex() -> None:
    m = RoutingMarker(pattern="#boardroom")
    rx = m.to_regex()
    assert isinstance(rx, re.Pattern)
    # Matches the literal as a standalone token
    assert rx.search("see #boardroom verdict") is not None
    # Does NOT match inside a larger token (E7)
    assert rx.search("#boardrooming") is None


def test_marker_case_insensitive_when_requested() -> None:
    m = RoutingMarker(pattern="#BOARDROOM", case_sensitive=False)
    rx = m.to_regex()
    assert rx.search("see #boardroom verdict") is not None


def test_marker_case_sensitive_by_default() -> None:
    m = RoutingMarker(pattern="#BOARDROOM")
    rx = m.to_regex()
    # Default is case-sensitive, so lowercase form should NOT match
    assert rx.search("see #boardroom verdict") is None


def test_marker_handles_word_starting_pattern() -> None:
    # A pattern that starts with a word character uses standard \b.
    m = RoutingMarker(pattern="ORCHESTRATED_BOARD_CHAIRMAN")
    rx = m.to_regex()
    assert rx.search("ORCHESTRATED_BOARD_CHAIRMAN verdict") is not None
    assert rx.search("not_ORCHESTRATED_BOARD_CHAIRMAN_x") is None


# ════════════════════════════════════════════════════════════════════
#  Rule model
# ════════════════════════════════════════════════════════════════════


def test_rule_rejects_unknown_destination() -> None:
    with pytest.raises(ValidationError):
        RoutingRule(name="bad", destination="trash_can")


def test_rule_rejects_unknown_severity() -> None:
    with pytest.raises(ValidationError):
        RoutingRule(name="bad", destination="proposals", severity="CRITICAL")


def test_rule_accepts_none_severity() -> None:
    r = RoutingRule(name="ok", destination="proposals", severity=None)
    assert r.severity is None


def test_rule_rejects_empty_name() -> None:
    with pytest.raises(ValidationError):
        RoutingRule(name="   ", destination="proposals")


# ════════════════════════════════════════════════════════════════════
#  RulesFile + E1 catch-all enforcement
# ════════════════════════════════════════════════════════════════════


def test_rules_file_rejects_zero_catchalls() -> None:
    with pytest.raises(ValidationError) as exc:
        RoutingRulesFile(
            rules=[
                RoutingRule(name="r1", destination="proposals"),
                RoutingRule(name="r2", destination="decisions"),
            ]
        )
    assert "catch-all" in str(exc.value)


def test_rules_file_rejects_multiple_catchalls() -> None:
    with pytest.raises(ValidationError):
        RoutingRulesFile(
            rules=[
                RoutingRule(name="r1", destination="proposals"),
                RoutingRule(name="c1", destination="decisions", is_catchall=True),
                RoutingRule(name="c2", destination="decisions", is_catchall=True),
            ]
        )


def test_rules_file_requires_catchall_last() -> None:
    with pytest.raises(ValidationError) as exc:
        RoutingRulesFile(
            rules=[
                RoutingRule(name="c", destination="decisions", is_catchall=True),
                RoutingRule(name="r", destination="proposals"),
            ]
        )
    assert "last" in str(exc.value).lower()


def test_rules_file_accepts_valid_set() -> None:
    f = RoutingRulesFile(
        rules=[
            RoutingRule(
                name="boardroom",
                destination="proposals",
                markers=[RoutingMarker(pattern="#boardroom")],
            ),
            RoutingRule(
                name="catch", destination="decisions", is_catchall=True
            ),
        ]
    )
    assert len(f.rules) == 2
    assert f.rules[-1].is_catchall is True


# ════════════════════════════════════════════════════════════════════
#  Production YAML file loads + validates
# ════════════════════════════════════════════════════════════════════


def test_production_rules_yaml_loads() -> None:
    """The shipped config/routing_rules.yaml must load and validate."""
    rules_file = load_routing_rules(RULES_PATH)
    assert isinstance(rules_file, RoutingRulesFile)
    assert len(rules_file.rules) >= 7  # 7 rules + catch-all minimum


def test_production_rules_yaml_has_catchall_named_decision_only() -> None:
    rules_file = load_routing_rules(RULES_PATH)
    catchall = rules_file.rules[-1]
    assert catchall.is_catchall is True
    assert catchall.name == "decision_only"


def test_production_rules_yaml_all_destinations_allowed() -> None:
    rules_file = load_routing_rules(RULES_PATH)
    for r in rules_file.rules:
        assert r.destination in ALLOWED_DESTINATIONS


# ════════════════════════════════════════════════════════════════════
#  RoutingDecision shape (matches Cline's golden JSONs)
# ════════════════════════════════════════════════════════════════════


def test_routing_decision_matches_golden_shape() -> None:
    d = RoutingDecision(
        rule_name="boardroom_proposal",
        destination="proposals",
        workflow_phase="beta",
        severity="HIGH",
        matched_markers=["#boardroom"],
        context={"severity": "HIGH"},
    )
    blob = d.model_dump()
    assert blob["rule_name"] == "boardroom_proposal"
    assert blob["destination"] == "proposals"
    assert blob["matched_markers"] == ["#boardroom"]


def test_routing_decision_allows_null_severity() -> None:
    d = RoutingDecision(
        rule_name="decision_only",
        destination="decisions",
        workflow_phase="beta",
        severity=None,
        matched_markers=[],
        context={"severity": "BACKLOG"},
    )
    assert d.severity is None
    assert d.matched_markers == []
