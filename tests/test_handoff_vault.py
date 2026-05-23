"""Test handoff vault for governance foundation.

VETO COMPLIANCE:
- V1/V7: ArtifactVersion stores ONLY path + sha256_hash; body lives on disk
- B4: Hash chain via prior_hash
- V9: Explicit exceptions raised, never silently swallowed
"""

from __future__ import annotations

import os
import tempfile
import shutil
from pathlib import Path

import pytest

from src.workflow_models import (
    ValidatedProposal,
    Severity,
    WorkflowPhase,
    VaultIntegrityError,
)
from src.handoff_vault import HandoffVault, verify_vault_integrity


class TestHandoffVault:
    """Tests for HandoffVault class."""

    @pytest.fixture
    def temp_vault_dir(self) -> Path:
        """Create a temporary directory for vault testing."""
        temp_dir = Path(tempfile.mkdtemp())
        vault_dir = temp_dir / "vault"
        yield vault_dir
        shutil.rmtree(temp_dir)

    def test_snapshot_creates_content_addressable_file(self, temp_vault_dir: Path) -> None:
        """snapshot creates content-addressable file with correct sha256."""
        vault = HandoffVault(base_dir=temp_vault_dir)
        
        proposal = ValidatedProposal(
            proposal_id="TEST-VAULT-1",
            severity=Severity.HIGH,
            origin="test_user",
            workflow_version="1.0",
            phase=WorkflowPhase.PROPOSAL,
            status="draft",
            body="# Test Proposal\n\nThis is the body.",
        )
        
        artifact = vault.snapshot(proposal, WorkflowPhase.PROPOSAL)
        
        # Verify ArtifactVersion contains only metadata (V1/V7 compliance)
        assert artifact.proposal_id == "TEST-VAULT-1"
        assert artifact.sha256 is not None
        assert len(artifact.sha256) == 64  # SHA256 hex string
        assert artifact.snapshot_path is not None
        
        # Verify file exists at the expected path
        snapshot_path = Path(artifact.snapshot_path)
        assert snapshot_path.exists()
        
        # Verify content hash matches
        with open(snapshot_path, "rb") as f:
            content_hash = __import__('hashlib').sha256(f.read()).hexdigest()
        assert content_hash == artifact.sha256

    def test_snapshot_stores_only_metadata_not_body(self, temp_vault_dir: Path) -> None:
        """ArtifactVersion stores only path+sha, never body (V1/V7 compliance)."""
        vault = HandoffVault(base_dir=temp_vault_dir)
        
        proposal = ValidatedProposal(
            proposal_id="TEST-NO-BODY",
            severity=Severity.LOW,
            origin="test_user",
            workflow_version="1.0",
            phase=WorkflowPhase.ALPHA,
            status="review",
            body="# Test Proposal\n\n" + "x" * 1000,  # Large body
        )
        
        artifact = vault.snapshot(proposal, WorkflowPhase.ALPHA)
        
        # Verify ArtifactVersion has NO body field
        assert not hasattr(artifact, "body")
        
        # Verify only metadata fields exist
        assert hasattr(artifact, "proposal_id")
        assert hasattr(artifact, "phase")
        assert hasattr(artifact, "timestamp")
        assert hasattr(artifact, "sha256")
        assert hasattr(artifact, "prior_hash")
        assert hasattr(artifact, "snapshot_path")

    def test_get_history_returns_artifact_chain(self, temp_vault_dir: Path) -> None:
        """get_history retrieves artifact chain for a proposal."""
        vault = HandoffVault(base_dir=temp_vault_dir)
        
        # Create multiple snapshots
        for i, phase in enumerate([WorkflowPhase.PROPOSAL, WorkflowPhase.ALPHA, WorkflowPhase.FINALIZED]):
            proposal = ValidatedProposal(
                proposal_id="TEST-HISTORY",
                severity=Severity.MEDIUM,
                origin="test_user",
                workflow_version="1.0",
                phase=phase,
                status=f"stage_{i}",
                body=f"# Test Proposal {i}",
            )
            vault.snapshot(proposal, phase)
        
        history = vault.get_history("TEST-HISTORY")
        
        assert len(history) == 3
        assert all(h.proposal_id == "TEST-HISTORY" for h in history)

    def test_verify_chain_validates_hash_integrity(self, temp_vault_dir: Path) -> None:
        """verify_chain validates hash chain integrity."""
        vault = HandoffVault(base_dir=temp_vault_dir)
        
        proposal = ValidatedProposal(
            proposal_id="TEST-CHAIN",
            severity=Severity.HIGH,
            origin="test_user",
            workflow_version="1.0",
            phase=WorkflowPhase.PROPOSAL,
            status="draft",
            body="# Test Proposal",
        )
        
        artifact1 = vault.snapshot(proposal, WorkflowPhase.PROPOSAL)
        
        # Update proposal and create second snapshot
        proposal.body += "\n\nUpdated content."
        artifact2 = vault.snapshot(proposal, WorkflowPhase.ALPHA)
        
        # Verify chain is valid
        assert vault.verify_chain("TEST-CHAIN") is True

    def test_verify_chain_detects_hash_mismatch(self, temp_vault_dir: Path) -> None:
        """version_hash mismatch raises StaleStateError (AC8)."""
        vault = HandoffVault(base_dir=temp_vault_dir)
        
        proposal = ValidatedProposal(
            proposal_id="TEST-MISMATCH",
            severity=Severity.LOW,
            origin="test_user",
            workflow_version="1.0",
            phase=WorkflowPhase.PROPOSAL,
            status="draft",
            body="# Test Proposal",
        )
        
        artifact = vault.snapshot(proposal, WorkflowPhase.PROPOSAL)
        
        # Corrupt the snapshot file
        snapshot_path = Path(artifact.snapshot_path)
        with open(snapshot_path, "w") as f:
            f.write("# Corrupted content")
        
        # Verify chain detects mismatch
        with pytest.raises(VaultIntegrityError) as exc_info:
            vault.verify_chain("TEST-MISMATCH")
        
        assert "Hash mismatch" in str(exc_info.value)

    def test_restore_reconstructs_proposal(self, temp_vault_dir: Path) -> None:
        """restore reconstructs proposal from snapshot."""
        vault = HandoffVault(base_dir=temp_vault_dir)
        
        original_body = "# Test Proposal\n\nOriginal content."
        proposal = ValidatedProposal(
            proposal_id="TEST-RESTORE",
            severity=Severity.HIGH,
            origin="test_user",
            workflow_version="1.0",
            phase=WorkflowPhase.PROPOSAL,
            status="draft",
            body=original_body,
        )
        
        artifact = vault.snapshot(proposal, WorkflowPhase.PROPOSAL)
        
        # Restore from hash
        restored = vault.restore(artifact.sha256)
        
        assert restored is not None
        assert restored.proposal_id == "TEST-RESTORE"
        assert restored.body == original_body


class TestVerifyVaultIntegrity:
    """Tests for verify_vault_integrity function."""

    @pytest.fixture
    def temp_vault_dir(self) -> Path:
        """Create a temporary directory for vault testing."""
        temp_dir = Path(tempfile.mkdtemp())
        vault_dir = temp_dir / "vault"
        yield vault_dir
        shutil.rmtree(temp_dir)

    def test_verify_vault_integrity_scans_all_proposals(self, temp_vault_dir: Path) -> None:
        """verify_vault_integrity scans all proposals in the vault."""
        vault = HandoffVault(base_dir=temp_vault_dir)
        
        # Create multiple proposals
        for i in range(3):
            proposal = ValidatedProposal(
                proposal_id=f"TEST-INT-{i}",
                severity=Severity.LOW,
                origin="test_user",
                workflow_version="1.0",
                phase=WorkflowPhase.PROPOSAL,
                status="draft",
                body=f"# Test Proposal {i}",
            )
            vault.snapshot(proposal, WorkflowPhase.PROPOSAL)
        
        # Verify integrity
        results = verify_vault_integrity(vault)
        
        assert len(results) == 3
        assert all(results.values())

    def test_verify_vault_integrity_detects_corruption(self, temp_vault_dir: Path) -> None:
        """verify_vault_integrity detects corrupted snapshots."""
        vault = HandoffVault(base_dir=temp_vault_dir)
        
        proposal = ValidatedProposal(
            proposal_id="TEST-CORRUPT",
            severity=Severity.HIGH,
            origin="test_user",
            workflow_version="1.0",
            phase=WorkflowPhase.PROPOSAL,
            status="draft",
            body="# Test Proposal",
        )
        
        artifact = vault.snapshot(proposal, WorkflowPhase.PROPOSAL)
        
        # Corrupt the snapshot
        Path(artifact.snapshot_path).write_text("# Corrupted")
        
        # Verify integrity detects corruption
        results = verify_vault_integrity(vault)
        
        assert results["TEST-CORRUPT"] is False