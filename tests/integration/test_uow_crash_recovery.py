"""D5: UoW crash recovery rolls back incomplete transactions on boot.

Spec (handoff lines 182-185):
- Write a fake undo log to ``dev/.uow_log/``.
- Boot UoW (call ``run_recovery()``).
- Assert: incomplete transaction rolled back; undo log cleared.

Three scenarios:
- A  status="staged" + hash mismatch  -> staged deleted, target renamed
                                          to ``<name>.recovered_<uow_id>``,
                                          undo log deleted.
- B  status="staged" + hash match     -> staged deleted, target untouched,
                                          undo log deleted (regression
                                          guard for the rename guard).
- C  status="committed"                -> no rollback; undo log cleaned up
                                          (idempotent re-boot).

All three use ``monkeypatch.setattr("src.uow_recovery.UOW_LOG_DIR", ...)``
to keep recovery state under ``tmp_path``. The staging directory lives at
``target.parent / f".uow_{uow_id}"`` (sibling of the target), matching
GovernanceUnitOfWork.stage_file:323.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from src.uow_recovery import run_recovery


def _sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _write_undo_log(
    log_dir: Path,
    uow_id: str,
    target_path: Path,
    staged_path: Path,
    status: str,
    sha256_pre: str | None,
    sha256_staged: str | None,
) -> Path:
    """Persist a minimal undo log matching GovernanceUnitOfWork._write_undo_log."""
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{uow_id}.undo.json"
    log_path.write_text(
        json.dumps(
            {
                "uow_id": uow_id,
                "started_at": "2026-05-25T00:00:00",
                "operation": "generic",
                "staged_dir": str(staged_path.parent),
                "files": [
                    {
                        "target_path": str(target_path),
                        "staged_path": str(staged_path),
                        "sha256_pre": sha256_pre,
                        "sha256_staged": sha256_staged,
                    }
                ],
                "status": status,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return log_path


@pytest.fixture
def recovery_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Return (proposals_dir, log_dir) with UOW_LOG_DIR redirected to log_dir."""
    proposals_dir = tmp_path / "dev" / "proposals"
    log_dir = tmp_path / "dev" / ".uow_log"
    proposals_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("src.uow_recovery.UOW_LOG_DIR", log_dir)
    return proposals_dir, log_dir


def _stage_fixture(
    proposals_dir: Path,
    uow_id: str,
    staged_content: str,
) -> tuple[Path, Path]:
    """Create the staging dir + staged file as stage_file would."""
    staging_dir = proposals_dir / f".uow_{uow_id}"
    staging_dir.mkdir(parents=True, exist_ok=True)
    staged_path = staging_dir / f"{uow_id}_PROPOSAL.md"
    staged_path.write_text(staged_content, encoding="utf-8")
    target_path = proposals_dir / f"{uow_id}_PROPOSAL.md"
    return staged_path, target_path


def test_run_recovery_rolls_back_staged_with_hash_mismatch(recovery_env) -> None:
    """Scenario A: staged + hash mismatch -> target renamed, staged deleted, log gone."""
    proposals_dir, log_dir = recovery_env
    uow_id = "uow_hash_mismatch"

    staged_path, target_path = _stage_fixture(proposals_dir, uow_id, "staged version")

    # Pre-hash is what stage_file recorded when the UoW started.
    # Current target content differs -> mid-UoW modification detected.
    pre_hash = _sha256("original version")
    target_path.write_text("modified during uow", encoding="utf-8")

    _write_undo_log(
        log_dir,
        uow_id=uow_id,
        target_path=target_path,
        staged_path=staged_path,
        status="staged",
        sha256_pre=pre_hash,
        sha256_staged=_sha256("staged version"),
    )

    result = run_recovery()

    assert result["uows_recovered"] == [uow_id]
    assert not staged_path.exists(), "staged file must be deleted"
    assert not target_path.exists(), "target must be renamed away"

    recovered_path = proposals_dir / f"{uow_id}_PROPOSAL.md.recovered_{uow_id}"
    assert recovered_path.exists(), f"missing recovered file at {recovered_path}"
    # Recovered file holds the suspicious mid-UoW content for human review.
    assert recovered_path.read_text(encoding="utf-8") == "modified during uow"

    assert not (log_dir / f"{uow_id}.undo.json").exists(), "undo log must be deleted"


def test_run_recovery_rolls_back_staged_with_hash_match(recovery_env) -> None:
    """Scenario B: staged + hash match -> staged deleted, target untouched, log gone."""
    proposals_dir, log_dir = recovery_env
    uow_id = "uow_hash_match"

    staged_path, target_path = _stage_fixture(proposals_dir, uow_id, "staged version")

    # Target content equals what stage_file recorded as pre-state -> no
    # mid-UoW modification, no rename should happen.
    target_path.write_text("identical original", encoding="utf-8")
    pre_hash = _sha256("identical original")

    _write_undo_log(
        log_dir,
        uow_id=uow_id,
        target_path=target_path,
        staged_path=staged_path,
        status="staged",
        sha256_pre=pre_hash,
        sha256_staged=_sha256("staged version"),
    )

    result = run_recovery()

    assert result["uows_recovered"] == [uow_id]
    assert not staged_path.exists(), "staged file must be deleted"
    assert target_path.exists(), "target must remain (hashes match)"
    assert target_path.read_text(encoding="utf-8") == "identical original"

    recovered_path = proposals_dir / f"{uow_id}_PROPOSAL.md.recovered_{uow_id}"
    assert not recovered_path.exists(), "no recovered file when hashes match"

    assert not (log_dir / f"{uow_id}.undo.json").exists(), "undo log must be deleted"


def test_run_recovery_cleans_up_committed_log(recovery_env) -> None:
    """Scenario C: committed log -> no rollback, log cleaned up (idempotent re-boot)."""
    proposals_dir, log_dir = recovery_env
    uow_id = "uow_committed"

    staged_path, target_path = _stage_fixture(proposals_dir, uow_id, "staged version")
    # Pretend the commit went through: target has staged content; staged
    # file is still here on disk (the real _commit's os.rename removes it,
    # but a crash could leave it; recovery must NOT touch it for committed
    # transactions).
    target_path.write_text("staged version", encoding="utf-8")

    _write_undo_log(
        log_dir,
        uow_id=uow_id,
        target_path=target_path,
        staged_path=staged_path,
        status="committed",
        sha256_pre=None,
        sha256_staged=_sha256("staged version"),
    )

    result = run_recovery()

    assert result["uows_recovered"] == [], "committed UoW must not appear in rollback list"
    assert any(
        a.get("action") == "cleanup_committed_log" and a.get("uow_id") == uow_id
        for a in result["actions"]
    ), result["actions"]

    assert staged_path.exists(), "committed-state staged file must NOT be deleted"
    assert target_path.exists(), "committed target must remain"
    assert target_path.read_text(encoding="utf-8") == "staged version"

    assert not (log_dir / f"{uow_id}.undo.json").exists(), "committed log must be cleaned up"
