"""
Immutable Handoff Vault for Governance Foundation

This module provides content-addressable storage with hash chains.

VETO COMPLIANCE:
- V1/V7: ArtifactVersion stores ONLY path + sha256_hash; body lives on disk
- B4: Hash chain verification via prior_hash
- V9: Explicit exceptions raised, never silently swallowed
"""

from __future__ import annotations

import os
import hashlib
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict

from src.workflow_models import (
    ValidatedProposal,
    ArtifactVersion,
    WorkflowPhase,
    VaultIntegrityError,
)


# Configuration
ARCHIVES_DIR = Path("dev/.archives")
DB_PATH = Path("dev/.archives/vault_index.sqlite")


class HandoffVault:
    """
    Content-addressable vault for immutable snapshots.
    
    VETO COMPLIANCE:
    - V1/V7: Stores only metadata (path + hash); body lives on disk
    - B4: Hash chain via prior_hash
    """
    
    def __init__(
        self,
        base_dir: Optional[Path] = None,
        db_path: Optional[Path] = None,
    ):
        """Initialize the vault.

        Args:
            base_dir: Where snapshot files live. Defaults to production
                ``dev/.archives``.
            db_path: Where the SQLite index lives. Defaults to a sibling
                ``vault_index.sqlite`` next to ``base_dir`` so that passing
                only ``base_dir`` (e.g. in tests) isolates BOTH the files
                AND the index from production state.
        """
        self.base_dir = base_dir or ARCHIVES_DIR
        if db_path is not None:
            self.db_path = db_path
        elif base_dir is not None:
            # Custom base_dir → derive db_path so tests are fully isolated
            self.db_path = self.base_dir / "vault_index.sqlite"
        else:
            self.db_path = DB_PATH
        self._ensure_directory_exists()
        self._ensure_database_exists()
    
    def _ensure_directory_exists(self) -> None:
        """Create archives directory if it doesn't exist."""
        self.base_dir.mkdir(parents=True, exist_ok=True)
    
    def _ensure_database_exists(self) -> None:
        """Initialize SQLite database for metadata index."""
        conn = sqlite3.connect(str(self.db_path))
        try:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    proposal_id TEXT NOT NULL,
                    phase TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    sha256 TEXT NOT NULL UNIQUE,
                    prior_hash TEXT,
                    snapshot_path TEXT NOT NULL
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_snapshots_proposal_id 
                ON snapshots(proposal_id)
            """)
            conn.commit()
        finally:
            conn.close()
    
    def snapshot(self, proposal: ValidatedProposal, phase: WorkflowPhase) -> ArtifactVersion:
        """
        Create an immutable snapshot of a proposal.
        
        VETO COMPLIANCE:
        - V1/V7: Stores only path + sha256_hash in metadata; body lives on disk
        - B4: Hash chain via prior_hash
        
        Args:
            proposal: The validated proposal to snapshot
            phase: Current workflow phase
            
        Returns:
            ArtifactVersion with metadata (not full body)
        """
        # Compute SHA256 of the full proposal body (UTF-8 bytes, no
        # line-ending translation — so the on-disk file hashes identically).
        body_bytes = proposal.body.encode("utf-8")
        sha256 = hashlib.sha256(body_bytes).hexdigest()

        # Create archive filename from hash
        archive_filename = f"{proposal.proposal_id}_{sha256[:16]}.md"
        archive_path = self.base_dir / archive_filename

        # Write to temp file first (atomic write pattern). Binary mode so
        # Windows does not silently convert \n -> \r\n and break the hash.
        temp_path = archive_path.with_suffix(".tmp")

        try:
            with open(temp_path, "wb") as f:
                f.write(body_bytes)
                f.flush()
                os.fsync(f.fileno())
            
            # Atomic rename
            os.replace(temp_path, archive_path)
            # fsync directory on Unix-like systems (Windows doesn't support this)
            if hasattr(os, 'fsync'):
                try:
                    dir_fd = os.open(str(self.base_dir.parent), os.O_RDONLY | os.O_DIRECTORY)
                    os.fsync(dir_fd)
                    os.close(dir_fd)
                except (OSError, AttributeError):
                    pass  # Skip fsync for directories on Windows
            
            # Get prior hash for chain verification
            prior_hash = self._get_prior_hash(proposal.proposal_id)
            
            # Store metadata in SQLite
            conn = sqlite3.connect(str(self.db_path))
            try:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO snapshots (proposal_id, phase, timestamp, sha256, prior_hash, snapshot_path)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    proposal.proposal_id,
                    phase.value,  # Store enum value, not full name
                    datetime.now().isoformat(),
                    sha256,
                    prior_hash,
                    str(archive_path)
                ))
                conn.commit()
            finally:
                conn.close()
            
            # Return ArtifactVersion with ONLY metadata (V1/V7 compliance)
            return ArtifactVersion(
                proposal_id=proposal.proposal_id,
                phase=phase,
                timestamp=datetime.now(),
                sha256=sha256,
                prior_hash=prior_hash,
                snapshot_path=str(archive_path)
            )
            
        except Exception as e:
            # Clean up temp file on error
            if temp_path.exists():
                try:
                    os.remove(temp_path)
                except OSError:
                    pass
            raise VaultIntegrityError(
                proposal_id=proposal.proposal_id,
                reason=f"Failed to create snapshot: {e}"
            ) from e
    
    def get_history(self, proposal_id: str) -> List[ArtifactVersion]:
        """
        Retrieve artifact chain for a proposal.
        
        Args:
            proposal_id: The proposal ID to retrieve history for
            
        Returns:
            List of ArtifactVersion objects in chronological order
        """
        conn = sqlite3.connect(str(self.db_path))
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT proposal_id, phase, timestamp, sha256, prior_hash, snapshot_path
                FROM snapshots
                WHERE proposal_id = ?
                ORDER BY timestamp ASC
            """, (proposal_id,))
            
            rows = cursor.fetchall()
            return [
                ArtifactVersion(
                    proposal_id=row[0],
                    phase=WorkflowPhase(row[1]),
                    timestamp=datetime.fromisoformat(row[2]),
                    sha256=row[3],
                    prior_hash=row[4],
                    snapshot_path=row[5]
                )
                for row in rows
            ]
        finally:
            conn.close()
    
    def verify_chain(self, proposal_id: str) -> bool:
        """
        Verify the integrity of the hash chain.
        
        VETO COMPLIANCE:
        - B4: Cryptographic hash chain verification
        
        Args:
            proposal_id: The proposal ID to verify
            
        Returns:
            True if chain is valid, False otherwise
        """
        history = self.get_history(proposal_id)
        
        if not history:
            return False
        
        # Verify each snapshot file exists and matches hash
        for artifact in history:
            path = Path(artifact.snapshot_path)
            
            if not path.exists():
                raise VaultIntegrityError(
                    proposal_id=proposal_id,
                    reason=f"Snapshot file missing: {path}"
                )
            
            # Verify hash matches
            with open(path, "rb") as f:
                content_hash = hashlib.sha256(f.read()).hexdigest()
            
            if content_hash != artifact.sha256:
                raise VaultIntegrityError(
                    proposal_id=proposal_id,
                    reason=f"Hash mismatch for {path}"
                )
        
        # Verify hash chain integrity
        for i in range(1, len(history)):
            current = history[i]
            previous = history[i - 1]
            
            if current.prior_hash != previous.sha256:
                raise VaultIntegrityError(
                    proposal_id=proposal_id,
                    reason=f"Hash chain broken at index {i}"
                )
        
        return True
    
    def restore(self, sha256: str) -> Optional[ValidatedProposal]:
        """
        Restore a proposal from its hash.
        
        Args:
            sha256: The SHA256 hash of the snapshot to restore
            
        Returns:
            ValidatedProposal if found, None otherwise
        """
        conn = sqlite3.connect(str(self.db_path))
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT proposal_id, phase, timestamp, sha256, prior_hash, snapshot_path
                FROM snapshots
                WHERE sha256 = ?
            """, (sha256,))
            
            row = cursor.fetchone()
            if not row:
                return None
            
            path = Path(row[5])
            if not path.exists():
                return None

            # Read in binary mode to preserve the exact bytes that were
            # hashed at snapshot time (Windows newline translation would
            # otherwise corrupt the round-trip).
            with open(path, "rb") as f:
                body = f.read().decode("utf-8")

            # Severity is not stored in the snapshots table (only phase is).
            # Use "unknown" on restore — callers can re-classify after.
            return ValidatedProposal(
                proposal_id=row[0],
                severity="unknown",
                origin="vault_restore",
                workflow_version="1.0",
                phase=WorkflowPhase(row[1]),
                status="restored",
                body=body,
                created_at=datetime.fromisoformat(row[2]),
            )
        finally:
            conn.close()
    
    def _get_prior_hash(self, proposal_id: str) -> Optional[str]:
        """Get the hash of the most recent snapshot for a proposal."""
        history = self.get_history(proposal_id)
        if not history:
            return None
        return history[-1].sha256


def verify_vault_integrity(vault: Optional[HandoffVault] = None) -> Dict[str, bool]:
    """
    Verify integrity of all snapshots in the vault.
    
    Args:
        vault: Optional HandoffVault instance (uses default if not provided)
        
    Returns:
        Dict mapping proposal_id to verification result
    """
    if vault is None:
        vault = HandoffVault()
    
    # Get all unique proposal IDs
    conn = sqlite3.connect(str(vault.db_path))
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT proposal_id FROM snapshots")
        proposal_ids = [row[0] for row in cursor.fetchall()]
    finally:
        conn.close()
    
    results = {}
    for pid in proposal_ids:
        try:
            results[pid] = vault.verify_chain(pid)
        except VaultIntegrityError:
            results[pid] = False
    
    return results