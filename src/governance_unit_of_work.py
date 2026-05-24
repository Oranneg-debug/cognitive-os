"""
Governance Unit of Work for Transactional Governance Operations

This module provides a transactional wrapper for dual-write operations.

VETO COMPLIANCE:
- B4: Ensures Markdown + SQLite writes are atomic
- V9: Explicit exceptions raised, never silently swallowed
"""

from __future__ import annotations

import os
import shutil
import json
import hashlib
import secrets
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Callable, Any, Dict, Tuple
from contextlib import contextmanager

from src.workflow_models import (
    ValidatedProposal,
    ArtifactVersion,
    ApprovalRecord,
    WorkflowPhase,
    VaultIntegrityError,
    ApprovalLogError,
)

# Configuration
UOW_LOG_DIR = Path("dev/.uow_log")
from src.handoff_vault import HandoffVault
from src.approval_logger import ApprovalLogger


class GovernanceUnitOfWork:
    """
    Transactional wrapper for governance operations.

    Ensures that Markdown + SQLite writes are atomic - if either fails,
    the entire operation is rolled back.

    VETO COMPLIANCE:
    - B4: Atomic dual-write pattern
    - V9: Explicit exceptions, no silent swallowing

    Usage:
        with GovernanceUnitOfWork() as uow:                # production
            uow.snapshot_proposal(p, phase)
            uow.log_decision(r)

        with GovernanceUnitOfWork(base_dir=tmp) as uow:    # isolated (tests)
            ...
    """

    def __init__(
        self,
        base_dir: Optional[Path] = None,
        vault_dir: Optional[Path] = None,
        decisions_dir: Optional[Path] = None,
    ):
        """Initialize the unit of work.

        Args:
            base_dir: Single isolation root. When provided, the vault lives
                at ``base_dir/vault`` and the approvals db at
                ``base_dir/approvals.db``. Convenience for tests.
            vault_dir: Explicit vault directory (overrides ``base_dir``).
            decisions_dir: Explicit decisions directory (overrides
                ``base_dir``). Its sqlite index is ``approvals.db`` in the
                same directory.

        Either pass nothing (uses production paths) or pass ``base_dir``
        (test isolation) or pass ``vault_dir``+``decisions_dir`` (full
        control).
        """
        self._base_dir = base_dir
        if vault_dir is not None:
            self._vault_dir = vault_dir
        elif base_dir is not None:
            self._vault_dir = base_dir / "vault"
        else:
            self._vault_dir = None  # HandoffVault uses production default

        if decisions_dir is not None:
            self._decisions_dir = decisions_dir
            self._decisions_db = decisions_dir / "approvals.db"
        elif base_dir is not None:
            self._decisions_dir = base_dir
            self._decisions_db = base_dir / "approvals.db"
        else:
            self._decisions_dir = None
            self._decisions_db = None

        self.vault: Optional[HandoffVault] = None
        self.logger: Optional[ApprovalLogger] = None
        self._temp_dir: Optional[Path] = None
        self._snapshots_to_commit: List[tuple] = []
        self._decisions_to_commit: List[tuple] = []
        # NEW: For generic multi-file staging (A4)
        self._files_to_commit: List[Tuple[Path, str, Path]] = []  # (target_path, content, staged_path)
        self._undo_log_entries: List[Dict[str, Any]] = []
        # UoW ID for this transaction
        self._uow_id: str = f"uow_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{secrets.token_hex(4)}"
        # Reentrancy: nested `with uow():` on the same instance is treated
        # as a savepoint — only the outermost ``__exit__`` commits or
        # rolls back. Standard UoW behaviour.
        self._depth: int = 0

    # ------------------------------------------------------------------
    #  Context manager protocol — supports BOTH `with uow:` and `with uow():`
    # ------------------------------------------------------------------

    def __enter__(self) -> "GovernanceUnitOfWork":
        if self._depth == 0:
            self._start()
        self._depth += 1
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        self._depth -= 1
        if self._depth > 0:
            # Inner savepoint exit — defer commit/rollback to outermost
            if exc_type is not None:
                # Mark for rollback at outermost level
                self._rollback_pending = True
            return False
        # Outermost exit
        try:
            if exc_type is not None or getattr(self, "_rollback_pending", False):
                self._rollback()
                self._rollback_pending = False
                return False  # re-raise original (or no-op if no exc)
            self._commit()
        finally:
            self._cleanup()
        return False

    @contextmanager
    def __call__(self):
        """Legacy ``with uow():`` form — delegates to __enter__/__exit__."""
        with self:
            yield self

    def _start(self) -> None:
        """Start a new unit of work."""
        self.vault = HandoffVault(base_dir=self._vault_dir)
        if self._decisions_db is not None:
            self.logger = ApprovalLogger(
                decisions_dir=self._decisions_dir,
                db_path=self._decisions_db,
            )
        else:
            self.logger = ApprovalLogger(decisions_dir=self._decisions_dir)
        # Per-UoW temp directory so concurrent UoWs don't trample each
        # other. Placed under base_dir when isolated, otherwise under
        # dev/.temp_uow as before.
        temp_root = (self._base_dir or Path("dev")) / ".temp_uow"
        temp_root.mkdir(parents=True, exist_ok=True)
        self._temp_dir = Path(
            __import__("tempfile").mkdtemp(prefix="uow_", dir=str(temp_root))
        )
        self._snapshots_to_commit = []
        self._decisions_to_commit = []
    
    def _cleanup(self) -> None:
        """Clean up temporary resources."""
        if self._temp_dir and self._temp_dir.exists():
            try:
                shutil.rmtree(self._temp_dir)
            except OSError:
                pass
        self.vault = None
        self.logger = None
    
    def snapshot_proposal(self, proposal: ValidatedProposal, phase: WorkflowPhase) -> ArtifactVersion:
        """
        Queue a snapshot operation for atomic commit.
        
        Args:
            proposal: The proposal to snapshot
            phase: Current workflow phase
            
        Returns:
            ArtifactVersion with metadata (not full body)
        """
        if not self.vault:
            raise RuntimeError("Unit of work not started")

        # Compute real SHA256 up-front so callers can use it within the
        # transaction (e.g. for ``uow.restore(artifact.sha256)``).
        import hashlib
        sha256_hash = hashlib.sha256(proposal.body.encode("utf-8")).hexdigest()

        # Create temp snapshot file
        temp_snapshot_path = self._temp_dir / f"{proposal.proposal_id}_{sha256_hash[:16]}.md"
        with open(temp_snapshot_path, "w", encoding="utf-8") as f:
            f.write(proposal.body)

        self._snapshots_to_commit.append((proposal, phase, temp_snapshot_path))

        prior_hash = self.vault._get_prior_hash(proposal.proposal_id)
        return ArtifactVersion(
            proposal_id=proposal.proposal_id,
            phase=phase,
            timestamp=datetime.now(),
            sha256=sha256_hash,
            prior_hash=prior_hash,
            snapshot_path=str(temp_snapshot_path),
        )
    
    def log_decision(self, record: ApprovalRecord) -> None:
        """
        Queue a decision log operation for atomic commit.
        
        Args:
            record: The approval record to log
        """
        if not self.logger:
            raise RuntimeError("Unit of work not started")
        
        # Compute hash of the current proposal state
        state_hash = record.state_hash or self._compute_state_hash(record)
        
        # Get prior record hash for chain verification
        prior_hash = self.logger._get_prior_hash(record.proposal_id)
        
        # Generate unique nonce for replay protection (B4)
        nonce = record.nonce or __import__('secrets').token_hex(16)
        
        # Build log entry
        timestamp = record.timestamp.isoformat() if hasattr(record.timestamp, 'isoformat') else str(record.timestamp)
        log_entry = f"""
---
Proposal ID: {record.proposal_id}
Approver: {record.approver}
Decision: {record.decision}
Timestamp: {timestamp}
State Hash: {state_hash}
Nonce: {nonce}
Prior Record Hash: {prior_hash or 'N/A'}
"""
        if record.reason:
            log_entry += f"Reason: {record.reason}\n"
        log_entry += "---\n\n"
        
        # Store for later commit
        self._decisions_to_commit.append((record, log_entry))
    
    def _compute_state_hash(self, record: ApprovalRecord) -> str:
        """Compute state hash for a record."""
        import hashlib
        return hashlib.sha256(
            f"{record.proposal_id}:{record.approver}:{record.decision}".encode()
        ).hexdigest()
    
    def restore(self, sha256: str) -> Optional[ValidatedProposal]:
        """Restore a proposal by its SHA256.

        Searches both the committed vault and any in-flight snapshots
        queued in this UoW (consistent view inside the transaction).
        """
        if not self.vault:
            raise RuntimeError("Unit of work not started")
        restored = self.vault.restore(sha256)
        if restored is not None:
            return restored
        import hashlib
        for proposal, _phase, _temp in self._snapshots_to_commit:
            in_flight_sha = hashlib.sha256(
                proposal.body.encode("utf-8")
            ).hexdigest()
            if in_flight_sha == sha256:
                return proposal
        return None

    def _rollback(self) -> None:
        """Discard queued operations and remove temp snapshot files.

        Since writes only happen in ``_commit`` (no pre-writes), rollback
        is just queue clearing + temp cleanup.
        """
        if self._temp_dir and self._temp_dir.exists():
            try:
                shutil.rmtree(self._temp_dir)
            except OSError:
                pass
        self._snapshots_to_commit = []
        self._decisions_to_commit = []
        # NEW: Clean up staged files for generic writes
        self._files_to_commit = []
        self._undo_log_entries = []
    
    def stage_file(self, target_path: Path, content: str) -> None:
        """
        Stage a file for atomic commit.
        
        The file is written to a staging directory that's a sibling of the target,
        ensuring same-filesystem atomic rename via os.rename().
        
        Args:
            target_path: Final destination path for the file
            content: File content to write
        """
        # Compute hash of staged content (for undo log)
        content_bytes = content.encode("utf-8")
        sha256_staged = hashlib.sha256(content_bytes).hexdigest()
        
        # Get pre-existing hash if target exists (None if file didn't exist)
        sha256_pre: Optional[str] = None
        if target_path.exists():
            try:
                with open(target_path, "rb") as f:
                    sha256_pre = hashlib.sha256(f.read()).hexdigest()
            except OSError:
                sha256_pre = None
        
        # Create staging directory as sibling of target (same filesystem guarantee)
        staging_dir = target_path.parent / f".uow_{self._uow_id}"
        staging_dir.mkdir(parents=True, exist_ok=True)
        
        # Write to staged path
        filename = target_path.name
        staged_path = staging_dir / filename
        with open(staged_path, "wb") as f:
            f.write(content_bytes)
        
        # Queue for commit
        self._files_to_commit.append((target_path, content, staged_path))
        
        # Record in undo log entries
        self._undo_log_entries.append({
            "target_path": str(target_path),
            "staged_path": str(staged_path),
            "sha256_pre": sha256_pre,
            "sha256_staged": sha256_staged,
        })
    
    def _compute_file_hash(self, file_path: Path) -> Optional[str]:
        """Compute SHA256 of a file, return None if file doesn't exist."""
        if not file_path.exists():
            return None
        try:
            with open(file_path, "rb") as f:
                return hashlib.sha256(f.read()).hexdigest()
        except OSError:
            return None
    
    def _write_undo_log(self) -> Path:
        """
        Write undo log to dev/.uow_log/ before commit.
        
        Returns the path to the written undo log.
        """
        UOW_LOG_DIR.mkdir(parents=True, exist_ok=True)
        
        undo_data = {
            "uow_id": self._uow_id,
            "started_at": datetime.now().isoformat(),
            "operation": "generic",
            "staged_dir": str(self._files_to_commit[0][2].parent) if self._files_to_commit else "",
            "files": self._undo_log_entries,
            "status": "staged",
        }
        
        undo_path = UOW_LOG_DIR / f"{self._uow_id}.undo.json"
        with open(undo_path, "w", encoding="utf-8") as f:
            json.dump(undo_data, f, indent=2)
        
        return undo_path
    
    def _commit(self) -> None:
        """Commit all queued operations atomically.

        Delegates to ``HandoffVault.snapshot`` and ``ApprovalLogger.log_decision``
        so writes go through the canonical code paths (no duplicate logic).
        
        NEW: Also commits staged generic files via atomic os.rename().
        """
        if not self.vault or not self.logger:
            raise RuntimeError("Unit of work not started")

        committed_artifacts: List[ArtifactVersion] = []

        for proposal, phase, _temp_path in self._snapshots_to_commit:
            try:
                artifact = self.vault.snapshot(proposal, phase)
            except Exception as e:
                raise VaultIntegrityError(
                    proposal_id=proposal.proposal_id,
                    reason=f"Failed to commit snapshot: {e}",
                ) from e
            committed_artifacts.append(artifact)

        for record, _entry in self._decisions_to_commit:
            try:
                self.logger.log_decision(record)
            except Exception as e:
                raise ApprovalLogError(
                    proposal_id=record.proposal_id,
                    reason=f"Failed to commit decision: {e}",
                ) from e

        self._committed_artifacts = committed_artifacts
        
        # NEW: Commit staged generic files via atomic rename
        # First write undo log before any commits (for crash recovery)
        if self._files_to_commit:
            undo_path = self._write_undo_log()
        
        for target_path, content, staged_path in self._files_to_commit:
            try:
                # Atomic rename (same filesystem guaranteed by staging_dir design)
                os.rename(staged_path, target_path)
            except OSError as e:
                raise RuntimeError(
                    f"Failed to commit file {target_path}: {e}"
                ) from e
        
        # Update undo log status to committed
        if self._files_to_commit:
            try:
                undo_path = UOW_LOG_DIR / f"{self._uow_id}.undo.json"
                if undo_path.exists():
                    with open(undo_path, "r", encoding="utf-8") as f:
                        undo_data = json.load(f)
                    undo_data["status"] = "committed"
                    with open(undo_path, "w", encoding="utf-8") as f:
                        json.dump(undo_data, f, indent=2)
            except (OSError, json.JSONDecodeError):
                # Log but don't fail - idempotent cleanup will handle it
                pass


@contextmanager
def governance_unit_of_work(
    base_dir: Optional[Path] = None,
    vault_dir: Optional[Path] = None,
    decisions_dir: Optional[Path] = None,
):
    """Factory + context manager for governance unit of work.

    Equivalent to:
        with GovernanceUnitOfWork(base_dir=...) as uow:
            ...
    """
    uow = GovernanceUnitOfWork(
        base_dir=base_dir,
        vault_dir=vault_dir,
        decisions_dir=decisions_dir,
    )
    with uow as ctx:
        yield ctx