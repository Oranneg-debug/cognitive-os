"""D2: KanbanProcessor transitions go through WorkflowEngine (Phase 5).

Two scenarios:

* `test_approved_transition_calls_workflow_engine`
    - workflow_engine.transition() returns success=True.
    - Assert it was awaited exactly once with the expected TransitionRequest.
    - Assert NO `<id>_blocked.json` file appears in dev/failed_routings/.

* `test_vetoed_transition_writes_blocked_record`
    - workflow_engine.transition() returns success=False.
    - Assert a `<id>_blocked.json` file is written with the exact 5-key schema
      and `reason` starts with "Transition vetoed:" (regression guard for the
      dead-letter overwrite bug fixed in cb3f5bb).

Isolation strategy:
    - tmp_path is used as the simulated vault root.
    - `KanbanProcessor.cache_dir` and the post-construction `workflow_engine`
      attribute are redirected onto tmp_path.
    - `ApprovalLogger`'s default decisions_dir + DB_PATH are monkeypatched to
      tmp_path BEFORE constructing KanbanProcessor, so WorkflowEngine's
      internally-instantiated logger does not touch production sqlite.
    - `_find_proposal_file` and `_backend_twin_path` are monkeypatched on the
      instance so update_kanban_status writes only to tmp_path.
    - Orchestrator (instantiated inside `_update_proposal_phase` on the happy
      path) is patched at the import path used inside the function.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.workflow_models import WorkflowPhase, WorkflowTransitionResult


PROPOSAL_ID = "DEV-20260525-101010-ABCDEF12"


def _make_proposal_content() -> str:
    return (
        "---\n"
        "phase: proposal\n"
        "status: pending_approval\n"
        "approver: null\n"
        "severity: low\n"
        "depends_on: []\n"
        "---\n"
        "## Summary\n"
        "D2 integration fixture.\n"
    )


def _write_kanban_file(vault_root: Path, card_in_column: str) -> Path:
    kanban_path = vault_root / "1. P - Seedlings" / "Dev-KanBan.md"
    kanban_path.parent.mkdir(parents=True, exist_ok=True)
    columns = ["Backlog", "Proposal", "Beta Testing", "Alpha Polish", "Finalized", "Deployed"]
    body: list[str] = []
    for col in columns:
        body.append(f"## {col}\n")
        if col.lower() == card_in_column:
            body.append(f"- [ ] Card ^[{PROPOSAL_ID}]\n")
        body.append("\n")
    kanban_path.write_text("".join(body), encoding="utf-8")
    return kanban_path


@pytest.fixture
def proc(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Construct a KanbanProcessor with all writes redirected under tmp_path."""
    # Redirect ApprovalLogger defaults BEFORE WorkflowEngine instantiates one.
    fake_decisions = tmp_path / "dev" / "decisions"
    fake_decisions.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("src.approval_logger.DECISIONS_DIR", fake_decisions)
    monkeypatch.setattr("src.approval_logger.DB_PATH", fake_decisions / "index.sqlite")

    # Write the proposal under the vault path the processor would normally scan.
    proposal_dir = tmp_path / "1. P - Seedlings" / "dev" / "proposals"
    proposal_dir.mkdir(parents=True, exist_ok=True)
    (proposal_dir / f"{PROPOSAL_ID}.md").write_text(_make_proposal_content(), encoding="utf-8")

    # Now safe to construct.
    from src.kanban_processor import KanbanProcessor

    p = KanbanProcessor(vault_path=str(tmp_path))
    # Override the hardcoded prod-state cache_dir so failed_routings + cache
    # files land in tmp_path/dev instead of cognitive-os/dev.
    p.cache_dir = str(tmp_path / "dev")

    # Pin _find_proposal_file so the test never falls back to scanning the real
    # cognitive-os/dev/proposals directory.
    proposal_path = proposal_dir / f"{PROPOSAL_ID}.md"
    p._find_proposal_file = MagicMock(return_value=str(proposal_path))

    # Disable the backend-twin mirror writes — they target the real
    # cognitive-os/dev/proposals/ regardless of cwd. Returning None makes
    # update_kanban_status skip the mirror.
    p._backend_twin_path = MagicMock(return_value=None)

    return p


def test_approved_transition_calls_workflow_engine(proc, tmp_path: Path) -> None:
    _write_kanban_file(tmp_path, card_in_column="alpha polish")
    proc.cache = {"cards": {PROPOSAL_ID: "proposal"}}

    mock_transition = AsyncMock(
        return_value=WorkflowTransitionResult(
            success=True,
            proposal_id=PROPOSAL_ID,
            new_phase=WorkflowPhase.ALPHA,
        )
    )
    proc.workflow_engine.transition = mock_transition
    proc.workflow_engine._compute_version_hash = MagicMock(return_value="hash_under_test")

    mock_orch_instance = MagicMock()
    mock_orch_instance.continue_development_lifecycle.return_value = "stubbed council ran"

    with patch("orchestrator.Orchestrator", return_value=mock_orch_instance), \
         patch.object(proc, "_set_proposal_processing_status"), \
         patch.object(proc, "_write_card_status_to_board"):
        results = proc.process_all_transitions()

    mock_transition.assert_awaited_once()
    request = mock_transition.await_args.args[0]
    assert request.proposal_id == PROPOSAL_ID
    assert request.target_phase == WorkflowPhase.ALPHA
    assert request.approver == "KanbanProcessor"
    assert request.version_hash == "hash_under_test"

    assert any(r.get("status") == "success" for r in results), results

    failed_dir = tmp_path / "dev" / "failed_routings"
    if failed_dir.exists():
        assert not list(failed_dir.glob(f"{PROPOSAL_ID}_blocked.json"))


def test_vetoed_transition_writes_blocked_record(proc, tmp_path: Path) -> None:
    _write_kanban_file(tmp_path, card_in_column="alpha polish")
    proc.cache = {"cards": {PROPOSAL_ID: "proposal"}}

    mock_transition = AsyncMock(
        return_value=WorkflowTransitionResult(
            success=False,
            proposal_id=PROPOSAL_ID,
            error="version_hash mismatch (test)",
        )
    )
    proc.workflow_engine.transition = mock_transition
    proc.workflow_engine._compute_version_hash = MagicMock(return_value="hash_under_test")

    with patch("src.kanban_processor.ApprovalLogger") as mock_logger_cls:
        mock_logger_cls.return_value.log_approval.return_value = 1
        with pytest.raises(RuntimeError, match="Transition blocked"):
            proc.process_all_transitions()

    mock_transition.assert_awaited_once()

    blocked_path = tmp_path / "dev" / "failed_routings" / f"{PROPOSAL_ID}_blocked.json"
    assert blocked_path.exists(), f"missing {blocked_path}"

    record = json.loads(blocked_path.read_text(encoding="utf-8"))

    assert set(record.keys()) == {
        "proposal_id",
        "old_column",
        "new_column",
        "blocked_at",
        "reason",
    }, record.keys()

    assert record["proposal_id"] == PROPOSAL_ID
    assert record["old_column"] == "proposal"
    assert record["new_column"] == "alpha polish"

    # Regression guard for cb3f5bb: the broad `except Exception` must NOT
    # overwrite the dead-letter with a "RuntimeError: ..." reason.
    assert record["reason"].startswith("Transition vetoed:"), record["reason"]
    assert "version_hash mismatch (test)" in record["reason"]
