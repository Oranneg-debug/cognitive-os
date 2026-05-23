"""
Governance Foundation: Immutable Data Models & Approval Log System

This module defines Pydantic models for the governance framework.
Pure type definitions only - no I/O imports.

VETO COMPLIANCE:
- V5: No business logic or I/O in this module (pure Pydantic only)
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional, List
from pydantic import BaseModel, Field


class Severity(str, Enum):
    """Proposal severity levels."""
    UNKNOWN = "unknown"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class WorkflowPhase(str, Enum):
    """Workflow lifecycle phases."""
    BACKLOG = "backlog"
    PROPOSAL = "proposal"
    BETA_PLANNING = "beta_planning"
    BETA_EXECUTION = "beta_execution"
    ALPHA = "alpha"
    FINALIZED = "finalized"
    DEPLOYED = "deployed"


class ValidatedProposal(BaseModel):
    """
    A validated proposal with strict schema enforcement.
    
    VETO COMPLIANCE:
    - V1/V7: ArtifactVersion stores only path + sha256_hash (not full body)
    """
    proposal_id: str
    severity: Severity
    origin: str
    workflow_version: str
    phase: WorkflowPhase
    status: str
    body: str  # Markdown content
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        """Pydantic configuration."""
        use_enum_values = True


class ArtifactVersion(BaseModel):
    """
    A pointer to an immutable snapshot (content-addressable).
    
    VETO COMPLIANCE:
    - V1/V7: Stores ONLY path + sha256_hash; body lives on disk in snapshot file
    - No 'body' field to avoid storage bloat
    """
    proposal_id: str
    phase: WorkflowPhase
    timestamp: datetime
    sha256: str  # Content hash of the snapshot file
    prior_hash: Optional[str] = None  # For hash chain verification
    snapshot_path: str  # Path to the actual file (not stored here)

    class Config:
        """Pydantic configuration."""
        use_enum_values = True


class ApprovalRecord(BaseModel):
    """
    A decision record with cryptographic chain-of-custody.
    
    VETO COMPLIANCE:
    - B4: Each entry contains nonce + timestamp + sha256_of_preceding_record
    """
    proposal_id: str
    approver: str
    decision: str  # "APPROVE" or "REJECT"
    reason: Optional[str] = None
    timestamp: datetime
    state_hash: str  # Hash of the current proposal state
    nonce: Optional[str] = None  # For replay protection (B4)
    prior_record_hash: Optional[str] = None  # Hash of preceding record (B4)


class WorkflowEnvelope(BaseModel):
    """
    Carries ValidatedProposal + ArtifactVersion chain through transitions.
    
    Used to pass state through workflow engine transitions.
    """
    proposal: ValidatedProposal
    artifact_chain: List[ArtifactVersion] = Field(default_factory=list)


# Custom exceptions for explicit error handling (V9: No silent swallowing)
class SchemaValidationError(Exception):
    """Raised when schema validation fails."""
    def __init__(self, field: str, value: str, reason: str):
        self.field = field
        self.value = value
        self.reason = reason
        super().__init__(f"Invalid {field}: '{value}' ({reason})")


class VaultIntegrityError(Exception):
    """Raised when vault integrity check fails."""
    def __init__(self, proposal_id: str, reason: str):
        self.proposal_id = proposal_id
        self.reason = reason
        super().__init__(f"Vault integrity check failed for {proposal_id}: {reason}")


class ApprovalLogError(Exception):
    """Raised when approval log write fails."""
    def __init__(self, proposal_id: str, reason: str):
        self.proposal_id = proposal_id
        self.reason = reason
        super().__init__(f"Approval log error for {proposal_id}: {reason}")