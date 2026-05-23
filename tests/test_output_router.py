"""Tests for src.output_router (E1, E3, E4, E5, E7, T1, T2, ARCH-2007E0A1)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from src.output_router import OutputRouter, resolve_destination_path
from src.routing_rules_schema import RoutingDecision
from src.writer_protocols import BackendWriterProtocol, SingleWriterRuleViolation, VaultWriterProtocol


ROOT = Path(__file__).resolve().parent.parent
RULES_PATH = ROOT / "config" / "routing_rules.yaml"
GOLDENS_DIR = ROOT / "tests" / "routing"
FIXTURES_DIR = ROOT / "tests" / "routing"


class MockBackendWriter:
    """A mock backend writer that tracks writes."""

    def __init__(self) -> None:
        self.writes: list[tuple[Path, str]] = []
        self._raise_on_write: bool = False

    def write(self, destination: Path, content: str) -> Path:
        if self._raise_on_write:
            raise OSError("Simulated write failure")
        self.writes.append((destination, content))
        return destination


class MockVaultWriter:
    """A mock vault writer that should be rejected by the guard."""

    def write_to_vault(self, vault_destination: Path, content: str) -> Path:
        return vault_destination


class MockBackendAndVaultWriter:
    """A mock that implements both protocols - should still be rejected."""

    def write(self, destination: Path, content: str) -> Path:
        return destination

    def write_to_vault(self, vault_destination: Path, content: str) -> Path:
        return vault_destination


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#  Constructor tests (E4, E3)
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•


def test_constructor_rejects_vault_writer() -> None:
    """E4/T1: OutputRouter rejects VaultWriterProtocol at construction."""
    mock_vault = MockVaultWriter()
    mock_backend = MockBackendWriter()

    with pytest.raises(SingleWriterRuleViolation) as exc_info:
        OutputRouter(
            rules_path=RULES_PATH,
            backend_writer=mock_vault,
            dead_letter_dir=ROOT / "dev" / "failed_routings",
        )
    assert "VaultWriter" in str(exc_info.value)


def test_constructor_rejects_writer_implementing_both_protocols() -> None:
    """A class implementing both protocols should be rejected."""
    mock_both = MockBackendAndVaultWriter()
    mock_backend = MockBackendWriter()

    with pytest.raises(SingleWriterRuleViolation):
        OutputRouter(
            rules_path=RULES_PATH,
            backend_writer=mock_both,
            dead_letter_dir=ROOT / "dev" / "failed_routings",
        )


def test_constructor_accepts_backend_writer() -> None:
    """BackendWriterProtocol should be accepted."""
    mock_backend = MockBackendWriter()

    router = OutputRouter(
        rules_path=RULES_PATH,
        backend_writer=mock_backend,
        dead_letter_dir=ROOT / "dev" / "failed_routings",
    )
    assert router is not None


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#  Fixture routing tests (parameterized)
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•


@pytest.mark.parametrize(
    "fixture_name,golden_name",
    [
        ("input_1_boardroom_proposal", "golden_1_boardroom_proposal"),
        ("input_2_technical_proposal", "golden_2_technical_proposal"),
        ("input_3_council_decision", "golden_3_council_decision"),
        ("input_4_handoff_archival", "golden_4_handoff_archival"),
        ("input_5_unmatched_content", "golden_5_unmatched_content"),
        ("input_6_fence_with_markers", "golden_6_fence_with_markers"),
        ("input_7_complex_fences", "golden_7_complex_fences"),
    ],
)
def test_fixture_routes_to_golden_decision(fixture_name: str, golden_name: str) -> None:
    """E2: Each fixture routes to its golden RoutingDecision."""
    fixture_path = FIXTURES_DIR / f"{fixture_name}.md"
    golden_path = GOLDENS_DIR / f"{golden_name}.json"

    assert fixture_path.exists(), f"Fixture not found: {fixture_path}"
    assert golden_path.exists(), f"Golden not found: {golden_path}"

    # Load golden decision
    with open(golden_path, "r", encoding="utf-8") as f:
        golden_data = json.load(f)

    # Load fixture content
    content = fixture_path.read_text(encoding="utf-8")

    # Create router and route
    mock_backend = MockBackendWriter()
    router = OutputRouter(
        rules_path=RULES_PATH,
        backend_writer=mock_backend,
        dead_letter_dir=ROOT / "dev" / "failed_routings",
    )

    decision = router.route(content)

    # Verify decision matches golden
    assert decision.rule_name == golden_data["rule_name"]
    assert decision.destination == golden_data["destination"]
    assert decision.workflow_phase == golden_data["workflow_phase"]
    assert decision.severity == golden_data["severity"]
    assert decision.matched_markers == golden_data["matched_markers"]
    assert decision.context == golden_data["context"]


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#  Catch-all tests (E1)
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•


def test_catch_all_fires_when_nothing_matches() -> None:
    """E1: Catch-all rule fires when no specific rule matches."""
    content = "This content has no routing markers at all."
    mock_backend = MockBackendWriter()
    router = OutputRouter(
        rules_path=RULES_PATH,
        backend_writer=mock_backend,
        dead_letter_dir=ROOT / "dev" / "failed_routings",
    )

    decision = router.route(content)

    assert decision.rule_name == "decision_only"
    assert decision.destination == "decisions"
    assert decision.matched_markers == []


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#  Fence-stripping tests (T2)
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•


def test_fence_stripping_before_matching() -> None:
    """T2: Markers inside ``` blocks are ignored for routing."""
    content = """#boardroom

```
#boardroom inside code block
ORCHESTRATED_BOARD_CHAIRMAN
```

This content has #boardroom inside a fence, which should be stripped."""
    mock_backend = MockBackendWriter()
    router = OutputRouter(
        rules_path=RULES_PATH,
        backend_writer=mock_backend,
        dead_letter_dir=ROOT / "dev" / "failed_routings",
    )

    decision = router.route(content)

    # The markers inside the fence should be stripped, so this should match boardroom_proposal
    # because the marker outside the fence is still there
    assert decision.rule_name == "boardroom_proposal"
    assert "#boardroom" in decision.matched_markers


def test_fence_stripping_is_catch_all_when_markers_only_inside() -> None:
    """T2: If markers are ONLY inside fences, catch-all fires."""
    content = """Some content

```
#boardroom inside code block
ORCHESTRATED_BOARD_CHAIRMAN
```

No markers outside fences."""
    mock_backend = MockBackendWriter()
    router = OutputRouter(
        rules_path=RULES_PATH,
        backend_writer=mock_backend,
        dead_letter_dir=ROOT / "dev" / "failed_routings",
    )

    decision = router.route(content)

    # After stripping, no markers remain, so catch-all should fire
    assert decision.rule_name == "decision_only"
    assert decision.matched_markers == []


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#  apply() tests
# â•â•â•â•â•ââ•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•


def test_apply_writes_to_resolved_path() -> None:
    """apply() writes to the resolved destination path."""
    content = "#boardroom\n\nORCHESTRATED_BOARD_CHAIRMAN"
    mock_backend = MockBackendWriter()
    router = OutputRouter(
        rules_path=RULES_PATH,
        backend_writer=mock_backend,
        dead_letter_dir=ROOT / "dev" / "failed_routings",
    )

    decision = router.route(content)
    path = router.apply(content, decision)

    # Verify write occurred
    assert len(mock_backend.writes) == 1
    written_path, written_content = mock_backend.writes[0]
    assert written_content == content
    assert "proposals" in str(written_path)


def test_apply_falls_back_to_dead_letter_on_exception() -> None:
    """E5: apply() reroutes to dead-letter on writer exception."""
    content = "#boardroom\n\nORCHESTRATED_BOARD_CHAIRMAN"
    mock_backend = MockBackendWriter()
    mock_backend._raise_on_write = True  # Force write to fail

    router = OutputRouter(
        rules_path=RULES_PATH,
        backend_writer=mock_backend,
        dead_letter_dir=ROOT / "dev" / "failed_routings",
    )

    decision = router.route(content)
    path = router.apply(content, decision)

    # Verify failure handling
    assert path.name.endswith(".failed.md")
    # Should be in dead-letter directory
    assert "failed_routings" in str(path)


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#  resolve_destination_path tests
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•


def test_resolve_destination_path_proposals() -> None:
    """resolve_destination_path returns correct path for proposals."""
    path = resolve_destination_path("proposals", ROOT / "dev" / "failed_routings")
    assert "proposals" in str(path)


def test_resolve_destination_path_decisions() -> None:
    """resolve_destination_path returns correct path for decisions."""
    path = resolve_destination_path("decisions", ROOT / "dev" / "failed_routings")
    assert "decisions" in str(path)


def test_resolve_destination_path_rejects_unknown() -> None:
    """resolve_destination_path raises for unknown buckets."""
    with pytest.raises(ValueError):
        resolve_destination_path("unknown_bucket", ROOT / "dev" / "failed_routings")