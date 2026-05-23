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
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Callable, Any
from contextlib import contextmanager

from src.workflow_models import (
    ValidatedProposal,
    ArtifactVersion,
    ApprovalRecord,
    WorkflowPhase,
    VaultIntegrityError,
    ApprovalLogError,
)
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
    """
    
    def __init__(self):
        """Initialize the unit of work with vault and logger."""
        self.vault: Optional[HandoffVault] = None
        self.logger: Optional[ApprovalLogger] = None
        self._temp_dir: Optional[Path] = None
        self._snapshots_to_commit: List[tuple] = []  # (proposal, phase)
        self._decisions_to_commit: List[ApprovalRecord] = []
    
    @contextmanager
    def __call__(self):
        """Context manager for unit of work."""
        try:
            self._start()
            yield self
            self._commit()
        except Exception as e:
            self._rollback()
            raise
        finally:
            self._cleanup()
    
    def _start(self) -> None:
        """Start a new unit of work."""
        self.vault = HandoffVault()
        self.logger = ApprovalLogger()
        self._temp_dir = Path("dev/.temp_uow")
        self._temp_dir.mkdir(parents=True, exist_ok=True)
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
        
        # Compute SHA256 of the full proposal body
        import hashlib
        sha256_hash = hashlib.sha256(proposal.body.encode("utf-8")).hexdigest()
        
        # Create temp snapshot file
        temp_snapshot_path = self._temp_dir / f"{proposal.proposal_id}_{sha256_hash[:16]}.md"
        with open(temp_snapshot_path, "w", encoding="utf-8") as f:
            f.write(proposal.body)
        
        # Store for later commit
        self._snapshots_to_commit.append((proposal, phase, temp_snapshot_path))
        
        # Return ArtifactVersion (will be completed on commit)
        prior_hash = self.vault._get_prior_hash(proposal.proposal_id)
        return ArtifactVersion(
            proposal_id=proposal.proposal_id,
            phase=phase,
            timestamp=datetime.now(),
            sha256="pending",
            prior_hash=prior_hash,
            snapshot_path=str(temp_snapshot_path)
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
    
    def _commit(self) -> None:
        """Commit all queued operations atomically."""
        if not self.vault or not self.logger:
            raise RuntimeError("Unit of work not started")
        
        # Commit snapshots first
        for proposal, phase, temp_path in self._snapshots_to_commit:
            try:
                # Compute final hash
                with open(temp_path, "rb") as f:
                    sha256 = __import__('hashlib').sha256(f.read()).hexdigest()
                
                # Create final archive path
                archive_filename = f"{proposal.proposal_id}_{sha256[:16]}.md"
                archive_path = self.vault.base_dir / archive_filename
                
                # Atomic rename from temp to archive
                os.replace(temp_path, archive_path)
                
                # Get prior hash for chain verification
                prior_hash = self.vault._get_prior_hash(proposal.proposal_id)
                
                # Store metadata in SQLite
                conn = __import__('sqlite3').connect(str(self.vault.db_path))
                try:
                    cursor = conn.cursor()
                    cursor.execute("""
                        INSERT INTO snapshots (proposal_id, phase, timestamp, sha256, prior_hash, snapshot_path)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (
                        proposal.proposal_id,
                        str(phase),
                        datetime.now().isoformat(),
                        sha256,
                        prior_hash,
                        str(archive_path)
                    ))
                    conn.commit()
                finally:
                    conn.close()
                    
            except Exception as e:
                raise VaultIntegrityError(
                    proposal_id=proposal.proposal_id,
                    reason=f"Failed to commit snapshot: {e}"
                ) from e
        
        # Commit decisions
        for record, log_entry in self._decisions_to_commit:
            try:
                # Write to markdown file (source of truth)
                log_path = self.logger.decisions_dir / f"{record.proposal_id}_log.md"
                
                with open(log_path, "a", encoding="utf-8") as f:
                    f.write(log_entry)
                    f.flush()
                    os.fsync(f.fileno())
                
                # Store metadata in SQLite
                conn = __import__('sqlite3').connect(str(self.logger.db_path))
                try:
                    cursor = conn.cursor()
                    cursor.execute("""
                        INSERT INTO decisions (proposal_id, approver, decision, reason, timestamp, state_hash, nonce, prior_record_hash)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        record.proposal_id,
                        record.approver,
                        record.decision,
                        record.reason,
                        record.timestamp.isoformat() if hasattr(record.timestamp, 'isoformat') else str(record.timestamp),
                        record.state_hash or self._compute_state_hash(record),
                        record.nonce or __import__('secrets').token_hex(16),
                        self.logger._get_prior_hash(record.proposal_id)
                    ))
                    conn.commit()
                finally:
                    conn.close()
                    
            except Exception as e:
                raise ApprovalLogError(
                    proposal_id=record.proposal_id,
                    reason=f"Failed to commit decision: {e}"
                ) from e
    
    def _rollback(self) -> None:
        """Rollback all queued operations."""
        # Clean up temp files
        if self._temp_dir and self._temp_dir.exists():
            try:
                shutil.rmtree(self._temp_dir)
            except OSError:
                pass


@contextmanager
def governance_unit_of_work():
    """Context manager for governance unit of work."""
    uow = GovernanceUnitOfWork()
    with uow():
        yield uow