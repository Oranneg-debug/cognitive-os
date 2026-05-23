"""Tests for src.workflow_router (E6, ARCH-2007E0A1)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.routing_rules_schema import RoutingDecision
from src.workflow_router import WorkflowRouter


ROOT = Path(__file__).resolve().parent.parent
RULES_PATH = ROOT / "config" / "routing_rules.yaml"


class MockOutputRouter:
    """A mock OutputRouter that tracks calls."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def route(self, content: str) -> RoutingDecision:
        """Return a mock RoutingDecision."""
        decision = RoutingDecision(
            rule_name="test_rule",
            destination="proposals",
            workflow_phase="beta",
            severity="HIGH",
            matched_markers=["#boardroom"],
            context={"severity": "HIGH"},
        )
        self.calls.append(("route", {"content": content}))
        return decision

    def apply(self, content: str, decision: RoutingDecision) -> Path:
        """Return a mock path."""
        self.calls.append(("apply", {"content": content, "decision": decision}))
        return Path("/mock/path/test.md")


class MockOutputRouterWithFailure:
    """A mock OutputRouter that raises on apply."""

    def __init__(self) -> None:
        self.route_calls = 0

    def route(self, content: str) -> RoutingDecision:
        self.route_calls += 1
        return RoutingDecision(
            rule_name="test_rule",
            destination="proposals",
            workflow_phase="beta",
            severity="HIGH",
            matched_markers=["#boardroom"],
            context={"severity": "HIGH"},
        )

    def apply(self, content: str, decision: RoutingDecision) -> Path:
        raise OSError("Simulated write failure")


def test_constructor_initializes_state() -> None:
    """WorkflowRouter initializes with empty state if state file doesn't exist."""
    watch_dir = ROOT / "tests" / "fixtures" / "watch"
    state_file = ROOT / "tests" / "fixtures" / "state.json"

    # Ensure state file doesn't exist
    if state_file.exists():
        state_file.unlink()

    mock_router = MockOutputRouter()
    workflow = WorkflowRouter(
        watch_dir=watch_dir,
        state_file=state_file,
        output_router=mock_router,
    )

    assert workflow._state == {}


def test_poll_once_processes_new_file(tmp_path: Path) -> None:
    """E6: poll_once processes a new file."""
    watch_dir = tmp_path / "watch"
    watch_dir.mkdir()
    state_file = tmp_path / "state.json"

    # Create a test file
    test_file = watch_dir / "test.md"
    test_file.write_text("#boardroom\n\nORCHESTRATED_BOARD_CHAIRMAN")

    mock_router = MockOutputRouter()
    workflow = WorkflowRouter(
        watch_dir=watch_dir,
        state_file=state_file,
        output_router=mock_router,
    )

    decisions = workflow.poll_once()

    assert len(decisions) == 1
    assert mock_router.calls[0][0] == "route"
    assert mock_router.calls[1][0] == "apply"


def test_poll_once_does_not_reprocess_same_file(tmp_path: Path) -> None:
    """E6: poll_once does NOT reprocess the same file on second call."""
    watch_dir = tmp_path / "watch"
    watch_dir.mkdir()
    state_file = tmp_path / "state.json"

    # Create a test file
    test_file = watch_dir / "test.md"
    test_content = "#boardroom\n\nORCHESTRATED_BOARD_CHAIRMAN"
    test_file.write_text(test_content)

    mock_router = MockOutputRouter()
    workflow = WorkflowRouter(
        watch_dir=watch_dir,
        state_file=state_file,
        output_router=mock_router,
    )

    # First poll - should process
    decisions1 = workflow.poll_once()
    assert len(decisions1) == 1
    assert len(mock_router.calls) == 2  # route + apply

    # Second poll - should NOT process again
    decisions2 = workflow.poll_once()
    assert len(decisions2) == 0
    assert len(mock_router.calls) == 2  # Still just route + apply (no new calls)


def test_poll_once_handles_corrupted_state_file(tmp_path: Path) -> None:
    """Recovers from corrupted state file and re-processes files."""
    watch_dir = tmp_path / "watch"
    watch_dir.mkdir()
    state_file = tmp_path / "state.json"

    # Create a corrupted state file
    state_file.write_text("{invalid json content")

    # Create a test file
    test_file = watch_dir / "test.md"
    test_file.write_text("#boardroom\n\nORCHESTRATED_BOARD_CHAIRMAN")

    mock_router = MockOutputRouter()
    workflow = WorkflowRouter(
        watch_dir=watch_dir,
        state_file=state_file,
        output_router=mock_router,
    )

    # Should recover from corrupted state and process the file
    decisions = workflow.poll_once()
    assert len(decisions) == 1


def test_poll_once_skips_non_md_files(tmp_path: Path) -> None:
    """Skips files that are not .md."""
    watch_dir = tmp_path / "watch"
    watch_dir.mkdir()
    state_file = tmp_path / "state.json"

    # Create various files
    (watch_dir / "test.md").write_text("#boardroom\n\nORCHESTRATED_BOARD_CHAIRMAN")
    (watch_dir / "test.txt").write_text("#boardroom\n\nORCHESTRATED_BOARD_CHAIRMAN")
    (watch_dir / "test.py").write_text("#boardroom\n\nORCHESTRATED_BOARD_CHAIRMAN")

    mock_router = MockOutputRouter()
    workflow = WorkflowRouter(
        watch_dir=watch_dir,
        state_file=state_file,
        output_router=mock_router,
    )

    decisions = workflow.poll_once()

    # Only the .md file should be processed
    assert len(decisions) == 1


def test_poll_once_returns_decisions_in_order(tmp_path: Path) -> None:
    """Returns decisions in the order files are processed."""
    watch_dir = tmp_path / "watch"
    watch_dir.mkdir()
    state_file = tmp_path / "state.json"

    # Create multiple test files
    for i in range(3):
        test_file = watch_dir / f"test{i}.md"
        test_file.write_text(f"#boardroom\n\nORCHESTRATED_BOARD_CHAIRMAN {i}")

    mock_router = MockOutputRouter()
    workflow = WorkflowRouter(
        watch_dir=watch_dir,
        state_file=state_file,
        output_router=mock_router,
    )

    decisions = workflow.poll_once()

    assert len(decisions) == 3
    # Decisions should be in sorted order (files are globbed)
    for i, decision in enumerate(decisions):
        assert decision["rule_name"] == "test_rule"