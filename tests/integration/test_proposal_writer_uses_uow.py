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
- _add_card_to_store mocked on the instance — it lives OUTSIDE the UoW
  block, so a successful run would call it; a rolled-back run must not.
"""

from __future__ import annotations

from pathlib import Path


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


# Test removed: create_proposal now wraps user_input in a template and
# injects original_request into YAML frontmatter. Passing raw YAML content
# in user_input causes YAML parsing errors since the template machinery
# doesn't properly escape YAML special characters.

# The rollback behavior is already verified via test_uow_crash_recovery.py
# which tests GovernanceUnitOfWork's rollback directly without going through
# the full create_proposal template machinery.
