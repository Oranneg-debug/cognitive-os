"""D4: ProposalWriter UoW rolls back atomically on mid-operation failure.

Spec (handoff lines 178-181):
- Patch one of the writes to raise mid-operation.
- Assert NO files in target dirs (full rollback).
- Assert ``dev/.uow_log/`` is clean (undo log deleted).

Failure-injection strategy:
- Patch GovernanceUnitOfWork.stage_file at the class level (autospec=True) so
  the 2nd call raises OSError. _commit() never runs, so _write_undo_log is
  never called — UOW_LOG_DIR stays empty.

Isolation:
- tmp_path holds proposals/, vault/dev/proposals/, .uow_log/, decisions/.
- Module-level paths patched on src.proposal_writer (VAULT_ROOT) and
  src.governance_unit_of_work (UOW_LOG_DIR).
- ApprovalLogger defaults patched on src.approval_logger (DECISIONS_DIR,
  DB_PATH) so the UoW's internal ApprovalLogger() does not touch real sqlite.
- ProposalWriter instance attributes (proposals_dir, vault_proposals_dir)
  overridden after construction.
- _add_card_to_kanban mocked on the instance — it lives OUTSIDE the UoW
  block, so a successful run would call it; a rolled-back run must not.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from src.integration_flags import reset_cache_for_tests
from src.governance_unit_of_work import GovernanceUnitOfWork


MINIMAL_TEMPLATE = """---
phase: proposal
status: pending_approval
---

# <PROPOSAL_ID>

Origin: <ORIGIN>

Body: [User's original request/description goes here]
"""


def _make_writer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Build a fully isolated ProposalWriter rooted in tmp_path."""
    reset_cache_for_tests()

    proposals_dir = tmp_path / "dev" / "proposals"
    vault_proposals_dir = tmp_path / "vault" / "dev" / "proposals"
    uow_log_dir = tmp_path / "dev" / ".uow_log"
    decisions_dir = tmp_path / "dev" / "decisions"

    for d in (proposals_dir, vault_proposals_dir, uow_log_dir, decisions_dir):
        d.mkdir(parents=True, exist_ok=True)

    # Redirect every path the UoW + writer might touch.
    monkeypatch.setattr("src.proposal_writer.VAULT_ROOT", tmp_path)
    monkeypatch.setattr("src.governance_unit_of_work.UOW_LOG_DIR", uow_log_dir)
    monkeypatch.setattr("src.approval_logger.DECISIONS_DIR", decisions_dir)
    monkeypatch.setattr("src.approval_logger.DB_PATH", decisions_dir / "index.sqlite")

    # Provide a minimal template at the path create_proposal expects.
    templates_dir = tmp_path / "1. P - Seedlings" / "dev" / "templates"
    templates_dir.mkdir(parents=True, exist_ok=True)
    (templates_dir / "proposal-template.md").write_text(
        MINIMAL_TEMPLATE, encoding="utf-8"
    )

    # Construct AFTER VAULT_ROOT is patched. ProposalWriter reads VAULT_ROOT
    # in __init__ to build self.vault_proposals_dir; we override it anyway.
    from src.proposal_writer import ProposalWriter

    writer = ProposalWriter()
    writer.proposals_dir = str(proposals_dir)
    writer.vault_proposals_dir = str(vault_proposals_dir)

    return writer, proposals_dir, vault_proposals_dir, uow_log_dir


def test_proposal_writer_rolls_back_on_stage_file_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    writer, proposals_dir, vault_proposals_dir, uow_log_dir = _make_writer(
        tmp_path, monkeypatch
    )

    # Save a reference to the REAL stage_file so the first call delegates
    # to it. Re-implementing the staging logic in the test would silently
    # diverge from production if stage_file ever changes.
    real_stage_file = GovernanceUnitOfWork.stage_file

    calls = {"n": 0}

    def stage_or_raise(self, target_path: Path, content: str) -> None:
        calls["n"] += 1
        if calls["n"] == 2:
            raise OSError("simulated write failure")
        # Delegate to real implementation for the first call so the staging
        # dir genuinely gets created — we want to verify _rollback cleans it up.
        return real_stage_file(self, target_path, content)

    with patch.object(writer, "_add_card_to_kanban") as mock_kanban, patch(
        "src.governance_unit_of_work.GovernanceUnitOfWork.stage_file",
        new=stage_or_raise,
    ):
        with pytest.raises(OSError, match="simulated write failure"):
            writer.create_proposal(
                user_input="D4 rollback fixture",
                origin="direct",
            )

    # 1. Exception propagated -> pytest.raises matched above.

    # 2. No files in backend proposals dir.
    backend_files = list(proposals_dir.glob("*.md"))
    assert backend_files == [], f"backend leaked: {backend_files}"

    # 3. No files in vault proposals dir.
    vault_files = list(vault_proposals_dir.glob("*.md"))
    assert vault_files == [], f"vault leaked: {vault_files}"

    # 4. No undo log files (commit never ran, so _write_undo_log never wrote).
    undo_logs = list(uow_log_dir.glob("*.undo.json"))
    assert undo_logs == [], f"undo log leaked: {undo_logs}"

    # 5. _add_card_to_kanban was never invoked (it lives after the `with` block).
    assert mock_kanban.call_count == 0, "kanban write must not run on rollback"

    # 6. No leftover ``.uow_uow_<id>/`` staging directories under tmp_path.
    # stage_file creates per-target staging dirs as siblings of the target
    # (named ``.uow_<uow_id>`` where ``uow_id`` itself starts with ``uow_``).
    # _rollback must clean these up (regression guard for the leak fix).
    # Note: we glob for ``.uow_uow_*`` specifically so the ``.uow_log/``
    # directory does not produce a false positive.
    leftover_staging = list(tmp_path.rglob(".uow_uow_*"))
    assert leftover_staging == [], f"staging dirs leaked: {leftover_staging}"
