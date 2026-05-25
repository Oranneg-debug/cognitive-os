"""
Append-Only Approval Log for Governance Foundation

This module provides dual-write (Markdown + SQLite) with cryptographic chain-of-custody.

VETO COMPLIANCE:
- B4: Each entry contains nonce + timestamp + sha256_of_preceding_record
- V9: Explicit exceptions raised, never silently swallowed
"""

from __future__ import annotations

import os
import hashlib
import sqlite3
import secrets
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict

from src.workflow_models import (
    ApprovalRecord,
    VaultIntegrityError,
)


# Configuration
DECISIONS_DIR = Path("dev/decisions")
DB_PATH = Path("dev/decisions/index.sqlite")


class ApprovalLogger:
    """
    Append-only approval log with dual-write (Markdown + SQLite).
    
    VETO COMPLIANCE:
    - B4: Cryptographic chain-of-custody via SHA256 + nonces
    """
    
    def __init__(
        self,
        decisions_dir: Optional[Path] = None,
        db_path: Optional[Path] = None,
    ):
        """Initialize the logger.

        Args:
            decisions_dir: Where decision Markdown files live. Defaults to
                production ``dev/decisions``.
            db_path: Where the SQLite index lives. Defaults to a sibling
                ``index.sqlite`` next to ``decisions_dir`` so that passing
                only ``decisions_dir`` (e.g. in tests) isolates BOTH the
                files AND the index from production state.
        """
        self.decisions_dir = decisions_dir or DECISIONS_DIR
        if db_path is not None:
            self.db_path = db_path
        elif decisions_dir is not None:
            self.db_path = self.decisions_dir / "index.sqlite"
        else:
            self.db_path = DB_PATH
        self._ensure_directory_exists()
        self._ensure_database_exists()
    
    def _ensure_directory_exists(self) -> None:
        """Create decisions directory if it doesn't exist."""
        self.decisions_dir.mkdir(parents=True, exist_ok=True)
    
    def _ensure_database_exists(self) -> None:
        """Initialize SQLite database for metadata index."""
        conn = sqlite3.connect(str(self.db_path))
        try:
            cursor = conn.cursor()
            
            # Main decisions table (existing)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS decisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    proposal_id TEXT NOT NULL,
                    approver TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    reason TEXT,
                    timestamp TEXT NOT NULL,
                    state_hash TEXT NOT NULL,
                    nonce TEXT,
                    prior_record_hash TEXT
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_decisions_proposal_id 
                ON decisions(proposal_id)
            """)
            
            # approval_log table for Gate #3 queries (T4: composite index)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS approval_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    proposal_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    approver TEXT NOT NULL,
                    ts TEXT NOT NULL
                )
            """)
            # T4: Composite index for O(log N) Gate #3 queries
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_approval_log_composite 
                ON approval_log(proposal_id, role, decision, ts)
            """)
            
            conn.commit()
        finally:
            conn.close()
    
    def log_decision(self, record: ApprovalRecord) -> None:
        """
        Log a decision to both Markdown and SQLite with SHA256 verification.
        
        VETO COMPLIANCE:
        - B4: Dual-write pattern with cryptographic chain-of-custody
        
        Args:
            record: The approval record to log
        """
        # Compute hash of the current proposal state
        state_hash = hashlib.sha256(
            f"{record.proposal_id}:{record.approver}:{record.decision}".encode()
        ).hexdigest()
        
        # Get prior record hash for chain verification
        prior_hash = self._get_prior_hash(record.proposal_id)
        
        # Generate unique nonce for replay protection (B4)
        nonce = record.nonce or secrets.token_hex(16)
        
        # Build log entry
        timestamp = record.timestamp.isoformat() if hasattr(record.timestamp, 'isoformat') else str(record.timestamp)
        log_entry = self._build_log_entry(record, state_hash, prior_hash, nonce)
        
        # Write to markdown file (source of truth)
        log_path = self.decisions_dir / f"{record.proposal_id}_log.md"
        
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(log_entry)
                f.flush()
                os.fsync(f.fileno())
            
            # Store metadata in SQLite
            conn = sqlite3.connect(str(self.db_path))
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
                    timestamp,
                    state_hash,
                    nonce,
                    prior_hash
                ))
                conn.commit()
            finally:
                conn.close()
                
        except Exception as e:
            raise VaultIntegrityError(
                proposal_id=record.proposal_id,
                reason=f"Failed to log decision: {e}"
            ) from e
    
    def _build_log_entry(self, record: ApprovalRecord, state_hash: str, prior_hash: Optional[str], nonce: str) -> str:
        """Build a Markdown log entry."""
        timestamp = record.timestamp.isoformat() if hasattr(record.timestamp, 'isoformat') else str(record.timestamp)
        
        entry = f"""
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
            entry += f"Reason: {record.reason}\n"
        entry += "---\n\n"
        
        return entry
    
    def get_log(self, proposal_id: str) -> List[ApprovalRecord]:
        """
        Retrieve decision log for a proposal.
        
        Args:
            proposal_id: The proposal ID to retrieve log for
            
        Returns:
            List of ApprovalRecord objects in chronological order
        """
        conn = sqlite3.connect(str(self.db_path))
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT proposal_id, approver, decision, reason, timestamp, state_hash, nonce, prior_record_hash
                FROM decisions
                WHERE proposal_id = ?
                ORDER BY timestamp ASC
            """, (proposal_id,))
            
            rows = cursor.fetchall()
            return [
                ApprovalRecord(
                    proposal_id=row[0],
                    approver=row[1],
                    decision=row[2],
                    reason=row[3],
                    timestamp=datetime.fromisoformat(row[4]),
                    state_hash=row[5],
                    nonce=row[6],
                    prior_record_hash=row[7]
                )
                for row in rows
            ]
        finally:
            conn.close()
    
    def verify_chain(self, proposal_id: str) -> bool:
        """
        Verify the integrity of the decision log chain.

        VETO COMPLIANCE:
        - B4: Cryptographic chain-of-custody verification

        Checks three invariants:

        1. The Markdown log file exists and contains the SQLite-recorded
           nonces. If the file is missing or has been overwritten with
           content that does not include every nonce, the chain is
           considered corrupted.
        2. Every record's ``state_hash`` matches the deterministic hash
           computed from its (proposal_id, approver, decision) tuple.
        3. The hash chain links via ``prior_record_hash``.

        Args:
            proposal_id: The proposal ID to verify

        Returns:
            True if chain is valid, False otherwise

        Raises:
            VaultIntegrityError: when a corruption is detected.
        """
        records = self.get_log(proposal_id)

        if not records:
            return False

        # 1. Cross-check the SQLite records against the Markdown source-of-truth.
        log_path = self.decisions_dir / f"{proposal_id}_log.md"
        if not log_path.exists():
            raise VaultIntegrityError(
                proposal_id=proposal_id,
                reason=f"Decision log missing: {log_path}",
            )
        try:
            log_text = log_path.read_text(encoding="utf-8")
        except OSError as e:
            raise VaultIntegrityError(
                proposal_id=proposal_id,
                reason=f"Decision log unreadable: {e}",
            ) from e
        for i, record in enumerate(records):
            if record.nonce and record.nonce not in log_text:
                raise VaultIntegrityError(
                    proposal_id=proposal_id,
                    reason=(
                        f"Decision log corrupted: nonce for record {i} "
                        f"missing from {log_path.name}"
                    ),
                )

        # 2. Verify each record's hash matches its content.
        for i, record in enumerate(records):
            expected_hash = hashlib.sha256(
                f"{record.proposal_id}:{record.approver}:{record.decision}".encode()
            ).hexdigest()

            if record.state_hash != expected_hash:
                raise VaultIntegrityError(
                    proposal_id=proposal_id,
                    reason=f"Hash mismatch at record {i}",
                )

        # 3. Verify hash chain links.
        for i in range(1, len(records)):
            current = records[i]
            previous = records[i - 1]

            if current.prior_record_hash != previous.state_hash:
                raise VaultIntegrityError(
                    proposal_id=proposal_id,
                    reason=f"Hash chain broken at record {i}",
                )

        return True
    
    def _get_prior_hash(self, proposal_id: str) -> Optional[str]:
        """Get the hash of the most recent decision for a proposal."""
        records = self.get_log(proposal_id)
        if not records:
            return None
        return records[-1].state_hash
    
    def check_technical_consensus(self, proposal_id: str) -> int:
        """
        Check Gate #3: Technical consensus from 3 distinct roles in last 14 days.
        
        V5 COMPLIANCE: Uses structured SQLite query, NOT markdown parsing
        T4 COMPLIANCE: Uses composite index on (proposal_id, role, decision, ts)
        
        Args:
            proposal_id: The proposal ID to check
            
        Returns:
            Count of distinct roles that have approved in last 14 days
        """
        conn = sqlite3.connect(str(self.db_path))
        try:
            cursor = conn.cursor()
            # Gate #3 SQL query (from state_machine.yaml)
            cursor.execute("""
                SELECT COUNT(DISTINCT role) 
                FROM approval_log 
                WHERE proposal_id = ? 
                  AND decision = 'APPROVED' 
                  AND role IN ('analyst', 'architect', 'specialist') 
                  AND ts > datetime('now', '-14 days')
            """, (proposal_id,))
            
            result = cursor.fetchone()
            return result[0] if result else 0
        finally:
            conn.close()
    
    def log_approval_for_gate3(self, proposal_id: str, role: str, decision: str, approver: str) -> None:
        """
        Log an approval record for Gate #3 queries.
        
        Args:
            proposal_id: The proposal ID
            role: The role (analyst, architect, specialist)
            decision: APPROVED or REJECTED
            approver: Name of the approver
        """
        conn = sqlite3.connect(str(self.db_path))
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO approval_log (proposal_id, role, decision, approver, ts)
                VALUES (?, ?, ?, ?, datetime('now'))
            """, (proposal_id, role, decision, approver))
            conn.commit()
        finally:
            conn.close()

    def log_approval(
        self,
        proposal_id: str,
        phase: str,
        status: str,
        approver: str,
        reason: Optional[str] = None,
        decision_log_path: Optional[str] = None,
    ) -> int:
        """
        Log a generic approval/audit event to the approval_log table.

        Used by KanbanProcessor._audit_log_block to record blocked
        transitions and other audit events. The richer ``phase``,
        ``reason``, ``decision_log_path`` fields are encoded into the
        ``decision`` column as a compact string so the existing schema is
        not altered (the table is shared with Gate #3 queries).

        Returns the row id of the new entry, or -1 if the insert failed.
        """
        # The approval_log table holds (proposal_id, role, decision, approver, ts).
        # We map the richer audit fields into ``role`` (the phase that the
        # event refers to) and ``decision`` (status + reason summary).
        composed_decision = status
        if reason:
            composed_decision = f"{status}: {reason}"
        if decision_log_path:
            composed_decision = f"{composed_decision} | log: {decision_log_path}"

        conn = sqlite3.connect(str(self.db_path))
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO approval_log (proposal_id, role, decision, approver, ts)
                VALUES (?, ?, ?, ?, datetime('now'))
                """,
                (proposal_id, phase, composed_decision, approver),
            )
            conn.commit()
            return cursor.lastrowid or -1
        finally:
            conn.close()


def verify_approval_logs_integrity(logger: Optional[ApprovalLogger] = None) -> Dict[str, bool]:
    """
    Verify integrity of all approval logs.
    
    Args:
        logger: Optional ApprovalLogger instance (uses default if not provided)
        
    Returns:
        Dict mapping proposal_id to verification result
    """
    if logger is None:
        logger = ApprovalLogger()
    
    # Get all unique proposal IDs
    conn = sqlite3.connect(str(logger.db_path))
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT proposal_id FROM decisions")
        proposal_ids = [row[0] for row in cursor.fetchall()]
    finally:
        conn.close()
    
    results = {}
    for pid in proposal_ids:
        try:
            results[pid] = logger.verify_chain(pid)
        except VaultIntegrityError:
            results[pid] = False
    
    return results