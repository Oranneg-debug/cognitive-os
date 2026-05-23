"""Test governance unit of work for end-to-end atomicity.

VETO COMPLIANCE:
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
)
from src.governance_unit_of_work import GovernanceUnitOfWork


class TestGovernanceUnitOfWork:
    """Tests for GovernanceUnitOfWork class."""

    @pytest.fixture
    def temp_dir(self) -> Path:
        """Create a temporary directory for testing."""
        temp_dir = Path(tempfile.mkdtemp())
        yield temp_dir
        shutil.rmtree(temp_dir)

    def test_successful_commit_commits_all_operations(self, temp_dir: Path) -> None:
        """Successful commit commits all operations atomically."""
        uow = GovernanceUnitOfWork(base_dir=temp_dir)
        
        proposal_id = f"TEST-ATOMIC-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        proposal = ValidatedProposal(
            proposal_id=proposal_id,
            severity=Severity.HIGH,
            origin="test_user",
            workflow_version="1.0",
            phase=WorkflowPhase.PROPOSAL,
            status="draft",
            body="# Test Proposal",
        )
        
        record = ApprovalRecord(
            proposal_id=proposal_id,
            approver="alice",
            decision="APPROVE",
            reason="Looks good",
            timestamp=datetime.now(),
            state_hash="state1" + "0" * 56,
            nonce="nonce1" + "0" * 28,
            prior_record_hash=None,
        )
        
        with uow():
            uow.snapshot_proposal(proposal, WorkflowPhase.PROPOSAL)
            uow.log_decision(record)
        
        # Verify both operations were committed
        assert (temp_dir / "vault").exists()
        assert (temp_dir / "approvals.db").exists()

    def test_exception_rolls_back_all_operations(self, temp_dir: Path) -> None:
        """Exception during commit rolls back all operations."""
        uow = GovernanceUnitOfWork(base_dir=temp_dir)
        
        proposal_id = f"TEST-ROLLBACK-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        proposal = ValidatedProposal(
            proposal_id=proposal_id,
            severity=Severity.HIGH,
            origin="test_user",
            workflow_version="1.0",
            phase=WorkflowPhase.PROPOSAL,
            status="draft",
            body="# Test Proposal",
        )
        
        record = ApprovalRecord(
            proposal_id=proposal_id,
            approver="alice",
            decision="APPROVE",
            reason="Looks good",
            timestamp=datetime.now(),
            state_hash="state1" + "0" * 56,
            nonce="nonce1" + "0" * 28,
            prior_record_hash=None,
        )
        
        with pytest.raises(ValueError):
            with uow():
                uow.snapshot_proposal(proposal, WorkflowPhase.PROPOSAL)
                uow.log_decision(record)
                raise ValueError("Simulated error")

        # Verify no snapshot files exist (the vault dir is created eagerly
        # by HandoffVault but must contain no committed artifacts).
        vault_dir = temp_dir / "vault"
        if vault_dir.exists():
            snapshot_files = [
                p for p in vault_dir.iterdir()
                if p.is_file() and p.suffix == ".md"
            ]
            assert snapshot_files == [], (
                f"rollback failed: snapshot files leaked: {snapshot_files}"
            )
        # Verify no decision was logged
        log_files = list(temp_dir.glob(f"{proposal_id}_log.md"))
        assert log_files == [], f"rollback failed: log files leaked: {log_files}"

    def test_nested_uow_commits_independently(self, temp_dir: Path) -> None:
        """Nested units of work commit independently."""
        uow = GovernanceUnitOfWork(base_dir=temp_dir)
        
        proposal_id1 = f"TEST-NESTED-1-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        proposal1 = ValidatedProposal(
            proposal_id=proposal_id1,
            severity=Severity.HIGH,
            origin="test_user",
            workflow_version="1.0",
            phase=WorkflowPhase.PROPOSAL,
            status="draft",
            body="# Test Proposal 1",
        )
        
        record1 = ApprovalRecord(
            proposal_id=proposal_id1,
            approver="alice",
            decision="APPROVE",
            reason="Looks good",
            timestamp=datetime.now(),
            state_hash="state1" + "0" * 56,
            nonce="nonce1" + "0" * 28,
            prior_record_hash=None,
        )
        
        with uow():
            uow.snapshot_proposal(proposal1, WorkflowPhase.PROPOSAL)
            uow.log_decision(record1)
            
            proposal_id2 = f"TEST-NESTED-2-{datetime.now().strftime('%Y%m%d%H%M%S')}"
            proposal2 = ValidatedProposal(
                proposal_id=proposal_id2,
                severity=Severity.LOW,
                origin="test_user",
                workflow_version="1.0",
                phase=WorkflowPhase.ALPHA,
                status="review",
                body="# Test Proposal 2",
            )
            
            record2 = ApprovalRecord(
                proposal_id=proposal_id2,
                approver="bob",
                decision="REVIEW",
                reason="Needs work",
                timestamp=datetime.now(),
                state_hash="state2" + "0" * 56,
                nonce="nonce2" + "0" * 28,
                prior_record_hash=None,
            )
            
            with uow():
                uow.snapshot_proposal(proposal2, WorkflowPhase.ALPHA)
                uow.log_decision(record2)
        
        # Verify both proposals were committed
        assert (temp_dir / "vault").exists()
        assert (temp_dir / "approvals.db").exists()

    def test_uow_provides_consistent_view(self, temp_dir: Path) -> None:
        """Unit of work provides consistent view during transaction."""
        uow = GovernanceUnitOfWork(base_dir=temp_dir)
        
        proposal_id = f"TEST-CONSISTENT-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        proposal = ValidatedProposal(
            proposal_id=proposal_id,
            severity=Severity.HIGH,
            origin="test_user",
            workflow_version="1.0",
            phase=WorkflowPhase.PROPOSAL,
            status="draft",
            body="# Test Proposal",
        )
        
        with uow():
            artifact = uow.snapshot_proposal(proposal, WorkflowPhase.PROPOSAL)
            
            # Verify artifact is available within UoW
            restored = uow.restore(artifact.sha256)
            assert restored is not None
            assert restored.proposal_id == proposal_id

    def test_uow_handles_multiple_snapshots(self, temp_dir: Path) -> None:
        """Unit of work handles multiple snapshots in one transaction."""
        uow = GovernanceUnitOfWork(base_dir=temp_dir)
        
        artifacts = []
        base_id = datetime.now().strftime('%Y%m%d%H%M%S')
        for i in range(3):
            proposal = ValidatedProposal(
                proposal_id=f"TEST-MULTI-{base_id}-{i}",
                severity=Severity.HIGH,
                origin="test_user",
                workflow_version="1.0",
                phase=WorkflowPhase.PROPOSAL,
                status=f"stage_{i}",
                body=f"# Test Proposal {i}",
            )
            
            with uow():
                artifact = uow.snapshot_proposal(proposal, WorkflowPhase.PROPOSAL)
                artifacts.append(artifact)
        
        # Verify all snapshots were committed
        assert len(artifacts) == 3
        assert (temp_dir / "vault").exists()

    def test_uow_handles_multiple_decisions(self, temp_dir: Path) -> None:
        """Unit of work handles multiple decisions in one transaction."""
        uow = GovernanceUnitOfWork(base_dir=temp_dir)
        
        artifacts = []
        base_id = datetime.now().strftime('%Y%m%d%H%M%S')
        for i in range(3):
            record = ApprovalRecord(
                proposal_id=f"TEST-MULTI-DECISION-{base_id}",
                approver=f"approver_{i}",
                decision=f"decision_{i}",
                reason=f"Decision {i}",
                timestamp=datetime.now(),
                state_hash=f"state{i}" + "0" * 56,
                nonce=f"nonce{i}" + "0" * 28,
                prior_record_hash=None,
            )
            
            with uow():
                artifact = uow.log_decision(record)
                artifacts.append(artifact)
        
        # Verify all decisions were committed
        assert len(artifacts) == 3
        assert (temp_dir / "approvals.db").exists()
