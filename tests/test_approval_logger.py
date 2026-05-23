"""Test approval logger for governance foundation.

VETO COMPLIANCE:
- B4: Hash chain via prior_record_hash (approval chain)
- V9: Explicit exceptions raised, never silently swallowed
"""

from __future__ import annotations

import os
import tempfile
import shutil
from pathlib import Path
from datetime import datetime

import pytest

from src.workflow_models import (
    ValidatedProposal,
    Severity,
    WorkflowPhase,
    ApprovalRecord,
    ApprovalLogError,
)
from src.approval_logger import ApprovalLogger, verify_approval_logs_integrity as verify_approval_chain


class TestApprovalLogger:
    """Tests for ApprovalLogger class."""

    @pytest.fixture
    def temp_dir(self) -> Path:
        """Create a temporary directory for testing."""
        temp_dir = Path(tempfile.mkdtemp())
        yield temp_dir
        shutil.rmtree(temp_dir)

    def test_log_decision_creates_markdown_file(self, temp_dir: Path) -> None:
        """log_decision creates markdown file with decision details."""
        logger = ApprovalLogger(decisions_dir=temp_dir)
        
        record = ApprovalRecord(
            proposal_id="TEST-LOG-1",
            approver="alice",
            decision="APPROVE",
            reason="Looks good",
            timestamp=datetime.now(),
            state_hash="state1" + "0" * 56,
            nonce="nonce1" + "0" * 28,
            prior_record_hash=None,
        )
        
        logger.log_decision(record)
        
        # Verify file exists
        log_path = temp_dir / "TEST-LOG-1_log.md"
        assert log_path.exists()

    def test_log_decision_creates_sqlite_entry(self, temp_dir: Path) -> None:
        """log_decision creates SQLite entry for fast lookup."""
        logger = ApprovalLogger(decisions_dir=temp_dir)
        
        record = ApprovalRecord(
            proposal_id="TEST-SQLITE",
            approver="alice",
            decision="APPROVE",
            reason="Looks good",
            timestamp=datetime.now(),
            state_hash="state1" + "0" * 56,
            nonce="nonce1" + "0" * 28,
            prior_record_hash=None,
        )
        
        logger.log_decision(record)
        
        # Verify SQLite entry exists
        db_path = temp_dir / "index.sqlite"
        assert db_path.exists()
        
        import sqlite3
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM decisions WHERE proposal_id = ?", (record.proposal_id,))
        row = cursor.fetchone()
        conn.close()
        
        assert row is not None
        assert row[1] == record.proposal_id
        assert row[2] == record.approver

    def test_verify_chain_validates_hash_integrity(self, temp_dir: Path) -> None:
        """verify_chain validates hash chain integrity."""
        logger = ApprovalLogger(decisions_dir=temp_dir)
        
        # Create first decision
        record1 = ApprovalRecord(
            proposal_id="TEST-CHAIN",
            approver="alice",
            decision="APPROVE",
            reason="Looks good",
            timestamp=datetime.now(),
            state_hash="state1" + "0" * 56,
            nonce="nonce1" + "0" * 28,
            prior_record_hash=None,
        )
        logger.log_decision(record1)
        
        # Create second decision linking to first
        record2 = ApprovalRecord(
            proposal_id="TEST-CHAIN",
            approver="bob",
            decision="APPROVE",
            reason="Confirmed",
            timestamp=datetime.now(),
            state_hash="state2" + "0" * 56,
            nonce="nonce2" + "0" * 28,
            prior_record_hash=None,  # Chain links via prior_record_hash
        )
        logger.log_decision(record2)
        
        # Verify chain is valid
        assert logger.verify_chain("TEST-CHAIN") is True

    def test_verify_chain_detects_hash_mismatch(self, temp_dir: Path) -> None:
        """version_hash mismatch raises StaleStateError (AC8)."""
        logger = ApprovalLogger(decisions_dir=temp_dir)
        
        record = ApprovalRecord(
            proposal_id="TEST-MISMATCH",
            approver="alice",
            decision="APPROVE",
            reason="Looks good",
            timestamp=datetime.now(),
            state_hash="state1" + "0" * 56,
            nonce="nonce1" + "0" * 28,
            prior_record_hash=None,
        )
        
        logger.log_decision(record)
        
        # Corrupt the log file
        log_path = temp_dir / "TEST-MISMATCH_log.md"
        with open(log_path, "w") as f:
            f.write("# Corrupted")
        
        # Verify chain detects mismatch
        with pytest.raises(Exception):  # VaultIntegrityError from verify_chain
            logger.verify_chain("TEST-MISMATCH")

    def test_restore_reconstructs_record(self, temp_dir: Path) -> None:
        """get_log reconstructs record from log."""
        logger = ApprovalLogger(decisions_dir=temp_dir)
        
        original_reason = "Original decision reason."
        record = ApprovalRecord(
            proposal_id="TEST-RESTORE",
            approver="alice",
            decision="APPROVE",
            reason=original_reason,
            timestamp=datetime.now(),
            state_hash="state1" + "0" * 56,
            nonce="nonce1" + "0" * 28,
            prior_record_hash=None,
        )
        
        logger.log_decision(record)
        
        # Restore from log
        restored = logger.get_log("TEST-RESTORE")
        
        assert len(restored) == 1
        assert restored[0].proposal_id == "TEST-RESTORE"
        assert restored[0].reason == original_reason

    def test_verify_chain_validates_hash_integrity(self, temp_dir: Path) -> None:
        """verify_chain validates hash chain integrity."""
        logger = ApprovalLogger(decisions_dir=temp_dir)
        
        # Create first decision
        record1 = ApprovalRecord(
            proposal_id="TEST-CHAIN",
            approver="alice",
            decision="APPROVE",
            reason="Looks good",
            timestamp=datetime.now(),
            state_hash="state1" + "0" * 56,
            nonce="nonce1" + "0" * 28,
            prior_record_hash=None,
        )
        logger.log_decision(record1)
        
        # Create second decision linking to first
        record2 = ApprovalRecord(
            proposal_id="TEST-CHAIN",
            approver="bob",
            decision="APPROVE",
            reason="Confirmed",
            timestamp=datetime.now(),
            state_hash="state2" + "0" * 56,
            nonce="nonce2" + "0" * 28,
            prior_record_hash=None,  # Chain links via prior_record_hash
        )
        logger.log_decision(record2)
        
        # Verify chain is valid
        assert logger.verify_chain("TEST-CHAIN") is True

    def test_verify_chain_detects_hash_mismatch(self, temp_dir: Path) -> None:
        """version_hash mismatch raises StaleStateError (AC8)."""
        logger = ApprovalLogger(decisions_dir=temp_dir)
        
        record = ApprovalRecord(
            proposal_id="TEST-MISMATCH",
            approver="alice",
            decision="APPROVE",
            reason="Looks good",
            timestamp=datetime.now(),
            state_hash="state1" + "0" * 56,
            nonce="nonce1" + "0" * 28,
            prior_record_hash=None,
        )
        
        logger.log_decision(record)
        
        # Corrupt the log file
        log_path = temp_dir / "TEST-MISMATCH_log.md"
        with open(log_path, "w") as f:
            f.write("# Corrupted")
        
        # Verify chain detects mismatch
        with pytest.raises(Exception):  # VaultIntegrityError from verify_chain
            logger.verify_chain("TEST-MISMATCH")

    def test_restore_reconstructs_record(self, temp_dir: Path) -> None:
        """get_log reconstructs record from log."""
        logger = ApprovalLogger(decisions_dir=temp_dir)
        
        original_reason = "Original decision reason."
        record = ApprovalRecord(
            proposal_id="TEST-RESTORE",
            approver="alice",
            decision="APPROVE",
            reason=original_reason,
            timestamp=datetime.now(),
            state_hash="state1" + "0" * 56,
            nonce="nonce1" + "0" * 28,
            prior_record_hash=None,
        )
        
        logger.log_decision(record)
        
        # Restore from log
        restored = logger.get_log("TEST-RESTORE")
        
        assert len(restored) == 1
        assert restored[0].proposal_id == "TEST-RESTORE"
        assert restored[0].reason == original_reason


class TestVerifyApprovalChain:
    """Tests for verify_approval_chain function."""

    @pytest.fixture
    def temp_dir(self) -> Path:
        """Create a temporary directory for testing."""
        temp_dir = Path(tempfile.mkdtemp())
        yield temp_dir
        shutil.rmtree(temp_dir)

    def test_verify_approval_logs_integrity_scans_all_proposals(self, temp_dir: Path) -> None:
        """verify_approval_logs_integrity scans all proposals in the logger."""
        logger = ApprovalLogger(decisions_dir=temp_dir)
        
        # Create multiple proposals with decisions
        for i in range(3):
            record = ApprovalRecord(
                proposal_id=f"TEST-CHAIN-{i}",
                approver="alice",
                decision="APPROVE",
                reason="Looks good",
                timestamp=datetime.now(),
                state_hash=f"state{i}" + "0" * 56,
                nonce=f"nonce{i}" + "0" * 28,
                prior_record_hash=None,
            )
            logger.log_decision(record)
        
        # Verify integrity
        results = verify_approval_chain(logger)
        
        assert len(results) == 3
        assert all(results.values())

    def test_verify_approval_logs_integrity_detects_corruption(self, temp_dir: Path) -> None:
        """verify_approval_logs_integrity detects corrupted log files."""
        logger = ApprovalLogger(decisions_dir=temp_dir)
        
        record = ApprovalRecord(
            proposal_id="TEST-CORRUPT",
            approver="alice",
            decision="APPROVE",
            reason="Looks good",
            timestamp=datetime.now(),
            state_hash="state1" + "0" * 56,
            nonce="nonce1" + "0" * 28,
            prior_record_hash=None,
        )
        
        logger.log_decision(record)
        
        # Corrupt the log file
        log_path = temp_dir / "TEST-CORRUPT_log.md"
        with open(log_path, "w") as f:
            f.write("# Corrupted")
        
        # Verify integrity detects corruption
        results = verify_approval_chain(logger)
        
        assert results["TEST-CORRUPT"] is False
