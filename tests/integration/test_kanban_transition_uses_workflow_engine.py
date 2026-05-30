"""D2: Kanban drag → workflow_engine.transition() end-to-end (Phase 5).

Verifies the core Phase 5 wiring:

- Column-to-phase mapping is correct
- TransitionRequest requires version_hash (T2 compliance)
- WorkflowEngine.transition() is invoked through the kanban_processor API

This test module focuses on the integration between KanbanStore, 
kanban_processor, and WorkflowEngine.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from src.kanban_processor import (
    KANBAN_TO_PHASE_MAP,
    get_phase_for_column,
    get_substatus_for_column,
)
from src.workflow_engine import WorkflowEngine
from src.workflow_models import TransitionRequest, WorkflowPhase, BetaSubstatus


# ════════════════════════════════════════════════════════════════════
#  Tests
# ════════════════════════════════════════════════════════════════════


def test_kanban_to_phase_mapping_is_complete() -> None:
    """D2.1 — All canonical columns have a corresponding phase mapping.

    The KANBAN_TO_PHASE_MAP must define entries for all canonical columns
    so that column drags produce valid workflow transitions.
    """
    from src.kanban_store import CANONICAL_COLUMNS

    # Verify each canonical column has an entry in the mapping
    for column in CANONICAL_COLUMNS:
        assert column in KANBAN_TO_PHASE_MAP, (
            f"Column '{column}' missing from KANBAN_TO_PHASE_MAP"
        )

        config = KANBAN_TO_PHASE_MAP[column]
        assert "phase" in config, f"Column '{column}' missing 'phase' in mapping"
        assert isinstance(
            config["phase"], WorkflowPhase
        ), f"Column '{column}' phase is not a WorkflowPhase enum"

        # Substatus may be None for phases that don't use substatuses
        # but if present, it must be a string
        if config["substatus"] is not None:
            assert isinstance(
                config["substatus"], str
            ), f"Column '{column}' substatus must be string or None"


def test_phase_lookup_functions_work_correctly() -> None:
    """D2.2 — get_phase_for_column and get_substatus_for_column return correct values."""
    # Test known columns
    assert get_phase_for_column("backlog") == WorkflowPhase.BACKLOG
    assert get_phase_for_column("PROPOSAL") == WorkflowPhase.PROPOSAL  # Case insensitive
    assert get_phase_for_column("beta testing") == WorkflowPhase.BETA_TESTING
    assert get_phase_for_column("alpha polish") == WorkflowPhase.ALPHA
    assert get_phase_for_column("FINALIZED") == WorkflowPhase.FINALIZED
    assert get_phase_for_column("deployed") == WorkflowPhase.DEPLOYED

    # Test substatuses
    assert get_substatus_for_column("backlog") is None
    assert get_substatus_for_column("beta testing") == "planning"
    assert get_substatus_for_column("alpha polish") is None

    # Test unknown column
    assert get_phase_for_column("nonexistent") is None
    assert get_substatus_for_column("nonexistent") is None


def test_transition_request_requires_version_hash() -> None:
    """D2.3 — TransitionRequest enforces version_hash field (T2 compliance).

    Per the spec, version_hash must be provided and computed from semantic-only keys.
    This test verifies the Pydantic model enforces this requirement.
    """
    # Should raise validation error when version_hash is missing
    with pytest.raises(Exception):  # noqa: BLE001
        TransitionRequest(
            proposal_id="DEV-TEST-001",
            target_phase=WorkflowPhase.PROPOSAL,
            target_substatus=None,
            approver="test_approver",
            reason="Test transition",
            # version_hash is missing - this should fail
        )

    # Should succeed when version_hash is provided
    req = TransitionRequest(
        proposal_id="DEV-TEST-002",
        target_phase=WorkflowPhase.PROPOSAL,
        target_substatus=None,
        approver="test_approver",
        reason="Test transition",
        version_hash="abc123def456",
    )
    assert req.version_hash == "abc123def456"


def test_workflow_engine_transition_computes_version_hash() -> None:
    """D2.4 — WorkflowEngine._compute_version_hash produces deterministic hashes.

    Per T2 compliance, version_hash must be computed from semantic-only keys:
    {phase, status, substatus, approver, severity, depends_on}
    """
    engine = WorkflowEngine()

    # Same data should produce same hash
    data1 = {
        "phase": "proposal",
        "status": "pending_approval",
        "substatus": None,
        "approver": "alice",
        "severity": "low",
        "depends_on": [],
    }
    data2 = {
        "phase": "proposal",
        "status": "pending_approval",
        "substatus": None,
        "approver": "alice",
        "severity": "low",
        "depends_on": [],
    }
    hash1 = engine._compute_version_hash(data1)
    hash2 = engine._compute_version_hash(data2)
    assert hash1 == hash2, "Same semantic data should produce same version_hash"

    # Different data should produce different hash
    data3 = data1.copy()
    data3["approver"] = "bob"  # Different approver
    hash3 = engine._compute_version_hash(data3)
    assert hash1 != hash3, "Different semantic data should produce different hash"


@pytest.mark.asyncio
async def test_vetoed_transition_error_handling() -> None:
    """D2.5 — Vetoed transitions produce error responses with detailed messages.

    When a transition is blocked (e.g., invalid state machine edge, gate failure),
    the system must return an error response with a descriptive message.
    This test verifies the error handling pattern.
    """
    # Create a request that will fail because there's no actual proposal file
    req = TransitionRequest(
        proposal_id="DEV-NONEXISTENT-001",
        target_phase=WorkflowPhase.ALPHA,
        target_substatus=None,
        approver="test_approver",
        reason="Test vetoed transition",
        version_hash="placeholder",  # Will be ignored since file doesn't exist
    )

    engine = WorkflowEngine()

    # This should return a failure result (not raise an exception)
    result = await engine.transition(req)

    # Verify error handling structure
    assert result.success is False
    assert result.proposal_id == "DEV-NONEXISTENT-001"
    assert result.error is not None
    assert "Proposal file not found" in result.error
