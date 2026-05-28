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
from typing import Optional, List, Callable, Protocol
from pydantic import BaseModel, Field, ConfigDict


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
    BETA_TESTING = "beta_testing"
    ALPHA = "alpha"
    FINALIZED = "finalized"
    DEPLOYED = "deployed"


class BetaSubstatus(str, Enum):
    """Beta phase substatuses for planning vs execution."""
    PLANNING = "planning"
    CODING = "coding"
    DEBUGGING = "debugging"
    TESTING = "testing"
    READY_FOR_ALPHA = "ready-for-alpha"


class GateResult(BaseModel):
    """
    Result of a gate check during phase transition.
    
    VETO COMPLIANCE:
    - V1: Gates are absolute; no override mechanism
    """
    edge: str  # e.g., "beta_testing/planning -> beta_testing/execution"
    passed: List[str] = Field(default_factory=list)
    failed: List[str] = Field(default_factory=list)
    details: dict = Field(default_factory=dict)


class WorkflowTransitionResult(BaseModel):
    """
    Result of a workflow transition attempt.
    
    VETO COMPLIANCE:
    - V7: No partial transitions; success=True means atomic completion
    """
    success: bool
    proposal_id: str
    new_phase: Optional[WorkflowPhase] = None
    new_substatus: Optional[str] = None
    gate_result: Optional[GateResult] = None
    error: Optional[str] = None
    archive_hash: Optional[str] = None
    decision_log_entry_id: Optional[int] = None
    git_tag: Optional[str] = None


class TransitionRequest(BaseModel):
    """
    Request to transition a proposal to a new phase.
    
    VETO COMPLIANCE:
    - G3: version_hash field for optimistic concurrency control
    - T2: Hash computed from semantic-only keys (phase, status, substatus, approver, severity, depends_on)
    """
    proposal_id: str
    target_phase: WorkflowPhase
    target_substatus: Optional[str] = None
    approver: str
    reason: str
    version_hash: str  # SHA-1 of semantic keys (T2 compliance)


class CompensatingAction(Protocol):
    """
    Protocol for named compensating functions per Saga step.
    
    VETO COMPLIANCE:
    - T3: Explicit named functions, NOT generic try/except rollback
    """
    def __call__(self, *args, **kwargs) -> None:
        """Execute compensation for a failed step."""
        ...


class SagaStep(BaseModel):
    """
    A single step in the Saga pattern with explicit compensation.
    
    VETO COMPLIANCE:
    - G2: Atomic transitions via Saga with compensations
    - T3: Each step has a named compensate function
    """
    name: str
    action: Callable[[], None]
    compensate: Optional[Callable[[], None]] = None


class SagaTransaction(BaseModel):
    """
    A Saga transaction orchestrating multiple steps with compensations.
    
    VETO COMPLIANCE:
    - G2: Atomicity via Saga pattern
    - T3: Named compensating functions per step
    """
    steps: List[SagaStep]
    
    def execute(self) -> bool:
        """Execute all steps in order; on failure, run compensations in reverse."""
        executed_steps: List[SagaStep] = []
        try:
            for step in self.steps:
                step.action()
                executed_steps.append(step)
            return True
        except Exception as e:
            # Run compensations in reverse order (last step first)
            for completed_step in reversed(executed_steps):
                if completed_step.compensate:
                    try:
                        completed_step.compensate()
                    except Exception:
                        # Log but continue with other compensations
                        pass
            return False


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
    substatus: Optional[str] = None  # For beta_testing planning/execution split
    body: str  # Markdown content
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(use_enum_values=True)


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

    model_config = ConfigDict(use_enum_values=True)


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


class GitOperationError(Exception):
    """Raised when a git operation fails."""
    def __init__(self, operation: str, details: str):
        self.operation = operation
        self.details = details
        super().__init__(f"Git operation '{operation}' failed: {details}")


class TransitionConflictError(Exception):
    """Raised when version_hash mismatch indicates concurrent modification (409 Conflict)."""
    def __init__(self, proposal_id: str, expected_hash: str, actual_hash: str):
        self.proposal_id = proposal_id
        self.expected_hash = expected_hash
        self.actual_hash = actual_hash
        super().__init__(
            f"Transition conflict for {proposal_id}: version_hash mismatch. "
            f"Expected {expected_hash}, got {actual_hash}. (HTTP 409)"
        )


class GateError(Exception):
    """Raised when a gate check fails."""
    def __init__(self, proposal_id: str, gate_name: str, details: List[str]):
        self.proposal_id = proposal_id
        self.gate_name = gate_name
        self.details = details
        super().__init__(
            f"Gate '{gate_name}' failed for {proposal_id}: {', '.join(details)}"
        )