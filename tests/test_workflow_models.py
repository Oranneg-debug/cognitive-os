"""Test workflow models for governance foundation.

VETO COMPLIANCE:
- V5: Pure Pydantic models only, no I/O
- V9: Explicit exceptions raised, never silently swallowed
"""

from __future__ import annotations

import pytest
from datetime import datetime

from src.workflow_models import (
    ValidatedProposal,
    ArtifactVersion,
    ApprovalRecord,
    WorkflowEnvelope,
    Severity,
    WorkflowPhase,
    SchemaValidationError,
    VaultIntegrityError,
    ApprovalLogError,
)


class TestValidatedProposal:
    """Tests for ValidatedProposal model."""

    def test_validated_proposal_accepts_valid_data(self) -> None:
        """ValidatedProposal accepts valid data."""
        proposal = ValidatedProposal(
            proposal_id="TEST-001",
            severity=Severity.HIGH,
            origin="test_user",
            workflow_version="1.0",
            phase=WorkflowPhase.PROPOSAL,
            status="draft",
            body="# Test Body\n\nThis is a test proposal.",
        )
        
        assert proposal.proposal_id == "TEST-001"
        assert proposal.severity == Severity.HIGH
        assert proposal.origin == "test_user"
        assert proposal.workflow_version == "1.0"
        assert proposal.phase == WorkflowPhase.PROPOSAL
        assert proposal.status == "draft"
        assert "# Test Body" in proposal.body

    def test_validated_proposal_rejects_invalid_severity(self) -> None:
        """ValidatedProposal rejects invalid severity."""
        with pytest.raises(ValueError):
            ValidatedProposal(
                proposal_id="TEST-002",
                severity="invalid_severity",  # type: ignore
                origin="test_user",
                workflow_version="1.0",
                phase=WorkflowPhase.PROPOSAL,
                status="draft",
                body="# Test Body",
            )

    def test_validated_proposal_accepts_all_valid_severities(self) -> None:
        """ValidatedProposal accepts all valid severity levels."""
        for severity in Severity:
            proposal = ValidatedProposal(
                proposal_id=f"TEST-{severity.value}",
                severity=severity,
                origin="test_user",
                workflow_version="1.0",
                phase=WorkflowPhase.PROPOSAL,
                status="draft",
                body="# Test Body",
            )
            assert proposal.severity == severity

    def test_validated_proposal_accepts_all_valid_phases(self) -> None:
        """ValidatedProposal accepts all valid workflow phases."""
        for phase in WorkflowPhase:
            proposal = ValidatedProposal(
                proposal_id=f"TEST-{phase.value}",
                severity=Severity.LOW,
                origin="test_user",
                workflow_version="1.0",
                phase=phase,
                status="draft",
                body="# Test Body",
            )
            assert proposal.phase == phase

    def test_validated_proposal_with_timestamps(self) -> None:
        """ValidatedProposal accepts optional timestamps."""
        now = datetime.now()
        proposal = ValidatedProposal(
            proposal_id="TEST-TIMESTAMPS",
            severity=Severity.MEDIUM,
            origin="test_user",
            workflow_version="1.0",
            phase=WorkflowPhase.ALPHA,
            status="review",
            body="# Test Body",
            created_at=now,
            updated_at=now,
        )
        
        assert proposal.created_at == now
        assert proposal.updated_at == now


class TestArtifactVersion:
    """Tests for ArtifactVersion model."""

    def test_artifact_version_stores_only_path_and_sha(self) -> None:
        """ArtifactVersion stores only path+sha, never body (V1/V7 compliance)."""
        artifact = ArtifactVersion(
            proposal_id="TEST-003",
            phase=WorkflowPhase.PROPOSAL,
            timestamp=datetime.now(),
            sha256="a1b2c3d4e5f6" * 8,  # 64-char SHA256
            prior_hash=None,
            snapshot_path="/path/to/snapshot.md",
        )
        
        # Verify only metadata fields exist
        assert hasattr(artifact, "proposal_id")
        assert hasattr(artifact, "phase")
        assert hasattr(artifact, "timestamp")
        assert hasattr(artifact, "sha256")
        assert hasattr(artifact, "prior_hash")
        assert hasattr(artifact, "snapshot_path")
        
        # Verify NO body field exists
        assert not hasattr(artifact, "body")

    def test_artifact_version_with_prior_hash(self) -> None:
        """ArtifactVersion supports hash chain via prior_hash."""
        artifact = ArtifactVersion(
            proposal_id="TEST-004",
            phase=WorkflowPhase.ALPHA,
            timestamp=datetime.now(),
            sha256="b2c3d4e5f6a1" * 8,
            prior_hash="a1b2c3d4e5f6" * 8,
            snapshot_path="/path/to/snapshot.md",
        )
        
        assert artifact.prior_hash == "a1b2c3d4e5f6" * 8

    def test_artifact_version_chain_links(self) -> None:
        """ArtifactVersion chain: prior_hash links correctly."""
        now = datetime.now()
        
        # First snapshot
        artifact1 = ArtifactVersion(
            proposal_id="TEST-CHAIN",
            phase=WorkflowPhase.PROPOSAL,
            timestamp=now,
            sha256="hash1" + "0" * 56,
            prior_hash=None,
            snapshot_path="/path/to/snapshot1.md",
        )
        
        # Second snapshot links to first
        artifact2 = ArtifactVersion(
            proposal_id="TEST-CHAIN",
            phase=WorkflowPhase.ALPHA,
            timestamp=now,
            sha256="hash2" + "0" * 56,
            prior_hash=artifact1.sha256,
            snapshot_path="/path/to/snapshot2.md",
        )
        
        assert artifact2.prior_hash == artifact1.sha256


class TestApprovalRecord:
    """Tests for ApprovalRecord model."""

    def test_approval_record_chain_prior_record_hash_links(self) -> None:
        """ApprovalRecord chain: prior_record_hash links correctly (B4 compliance)."""
        now = datetime.now()
        
        # First record
        record1 = ApprovalRecord(
            proposal_id="TEST-APPROVAL",
            approver="alice",
            decision="APPROVE",
            reason="Looks good",
            timestamp=now,
            state_hash="state1" + "0" * 56,
            nonce="nonce1" + "0" * 28,
            prior_record_hash=None,
        )
        
        # Second record links to first
        record2 = ApprovalRecord(
            proposal_id="TEST-APPROVAL",
            approver="bob",
            decision="APPROVE",
            reason="Confirmed",
            timestamp=now,
            state_hash="state2" + "0" * 56,
            nonce="nonce2" + "0" * 28,
            prior_record_hash=record1.state_hash,
        )
        
        assert record2.prior_record_hash == record1.state_hash

    def test_approval_record_with_nonce_for_replay_protection(self) -> None:
        """ApprovalRecord includes nonce for replay protection (B4 compliance)."""
        now = datetime.now()
        record = ApprovalRecord(
            proposal_id="TEST-REPLAY",
            approver="alice",
            decision="APPROVE",
            reason="Test",
            timestamp=now,
            state_hash="state1" + "0" * 56,
            nonce="unique_nonce_12345",
            prior_record_hash=None,
        )
        
        assert record.nonce == "unique_nonce_12345"

    def test_approval_record_optional_fields(self) -> None:
        """ApprovalRecord supports optional reason and nonces."""
        now = datetime.now()
        record = ApprovalRecord(
            proposal_id="TEST-OPTIONAL",
            approver="alice",
            decision="REJECT",
            timestamp=now,
            state_hash="state1" + "0" * 56,
        )
        
        assert record.reason is None
        assert record.nonce is None
        assert record.prior_record_hash is None


class TestWorkflowEnvelope:
    """Tests for WorkflowEnvelope model."""

    def test_workflow_envelope_carries_chain_through_transitions(self) -> None:
        """WorkflowEnvelope carries ValidatedProposal + ArtifactVersion chain."""
        now = datetime.now()
        
        proposal = ValidatedProposal(
            proposal_id="TEST-ENVELOPE",
            severity=Severity.HIGH,
            origin="test_user",
            workflow_version="1.0",
            phase=WorkflowPhase.PROPOSAL,
            status="draft",
            body="# Test Body",
        )
        
        artifact1 = ArtifactVersion(
            proposal_id="TEST-ENVELOPE",
            phase=WorkflowPhase.PROPOSAL,
            timestamp=now,
            sha256="hash1" + "0" * 56,
            prior_hash=None,
            snapshot_path="/path/to/snapshot1.md",
        )
        
        artifact2 = ArtifactVersion(
            proposal_id="TEST-ENVELOPE",
            phase=WorkflowPhase.ALPHA,
            timestamp=now,
            sha256="hash2" + "0" * 56,
            prior_hash=artifact1.sha256,
            snapshot_path="/path/to/snapshot2.md",
        )
        
        envelope = WorkflowEnvelope(
            proposal=proposal,
            artifact_chain=[artifact1, artifact2],
        )
        
        assert envelope.proposal.proposal_id == "TEST-ENVELOPE"
        assert len(envelope.artifact_chain) == 2
        assert envelope.artifact_chain[0].sha256 == "hash1" + "0" * 56
        assert envelope.artifact_chain[1].prior_hash == "hash1" + "0" * 56


class TestCustomExceptions:
    """Tests for custom exception classes."""

    def test_schema_validation_error(self) -> None:
        """SchemaValidationError includes field, value, and reason."""
        error = SchemaValidationError(
            field="severity",
            value="invalid",
            reason="Must be one of: high, medium, low, unknown",
        )
        
        assert error.field == "severity"
        assert error.value == "invalid"
        assert "severity" in str(error)

    def test_vault_integrity_error(self) -> None:
        """VaultIntegrityError includes proposal_id and reason."""
        error = VaultIntegrityError(
            proposal_id="TEST-VAULT",
            reason="Snapshot file missing",
        )
        
        assert error.proposal_id == "TEST-VAULT"
        assert "Snapshot file missing" in str(error)

    def test_approval_log_error(self) -> None:
        """ApprovalLogError includes proposal_id and reason."""
        error = ApprovalLogError(
            proposal_id="TEST-LOG",
            reason="Failed to write decision",
        )
        
        assert error.proposal_id == "TEST-LOG"
        assert "Failed to write decision" in str(error)