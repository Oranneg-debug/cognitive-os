"""
Workflow Engine - Central State Machine for Phase 3+4

Orchestrates proposal phase transitions using Saga pattern with compensations.

VETO COMPLIANCE:
- G2: Atomic transitions via Saga pattern with named compensating functions
- G3: TransitionRequest carries version_hash; 409 on mismatch
- T1: Git operations use asyncio.to_thread with explicit timeouts
- T2: version_hash computed from semantic-only keys
- T3: Each Saga step has explicit named compensate function
- V2: Only this module writes phase: field
"""

from __future__ import annotations

import hashlib
import yaml
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Callable, Any

from src.workflow_models import (
    TransitionRequest,
    WorkflowTransitionResult,
    WorkflowPhase,
    BetaSubstatus,
    SagaStep,
    SagaTransaction,
    GitOperationError,
    TransitionConflictError,
    GateError,
)
from src.git_operations import (
    ensure_branch,
    tag_execution_start,
    rollback_to_tag,
    get_commit_hash,
)
from src.handoff_vault import HandoffVault
from src.approval_logger import ApprovalLogger
from src.paths import PROPOSALS_DIR as _DEFAULT_PROPOSALS_DIR


# Configuration
# Default to the canonical absolute path from src.paths so the engine
# resolves the same files regardless of process cwd. Tests can override
# via the ``proposals_dir`` constructor arg.
PROPOSALS_DIR = _DEFAULT_PROPOSALS_DIR
STATE_MACHINE_PATH = Path(__file__).resolve().parent.parent / "config" / "state_machine.yaml"


class WorkflowEngine:
    """
    Central state machine orchestrating proposal phase transitions.
    
    VETO COMPLIANCE:
    - G2: Saga pattern with compensations ensures atomicity
    - V7: No partial transitions; success=True means complete atomic transition
    - T3: Named compensating functions per step
    """
    
    def __init__(
        self,
        state_machine_path: Optional[Path] = None,
        proposals_dir: Optional[Path] = None,
    ):
        self.state_machine_path = state_machine_path or STATE_MACHINE_PATH
        self.proposals_dir = proposals_dir or PROPOSALS_DIR
        self._state_machine = self._load_state_machine()
        self._handoff_vault = HandoffVault()
        self._approval_logger = ApprovalLogger()
    
    def _load_state_machine(self) -> Dict[str, Any]:
        """Load state machine configuration from YAML."""
        if not self.state_machine_path.exists():
            raise FileNotFoundError(
                f"State machine config not found: {self.state_machine_path}"
            )
        
        with open(self.state_machine_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    
    def _compute_version_hash(self, proposal_data: Dict[str, Any]) -> str:
        """
        Compute version_hash from semantic-only keys (T2 compliance).
        
        Hash basis: {phase, status, substatus, approver, severity, depends_on}
        EXCLUDES volatile metadata like last_modified, updated_ts.
        
        Args:
            proposal_data: The current proposal YAML data
            
        Returns:
            SHA-1 hex digest of semantic keys
        """
        # Extract only semantic keys (T2 compliance)
        semantic_keys = {
            'phase': proposal_data.get('phase'),
            'status': proposal_data.get('status'),
            'substatus': proposal_data.get('substatus'),
            'approver': proposal_data.get('approver'),
            'severity': proposal_data.get('severity'),
            'depends_on': proposal_data.get('depends_on'),
        }
        
        # Sort keys for deterministic serialization
        yaml_content = yaml.dump(semantic_keys, sort_keys=True, default_flow_style=True)
        
        # SHA-1 hash (for shorter hash than SHA-256, matching common git practice)
        return hashlib.sha1(yaml_content.encode()).hexdigest()
    
    def _get_transition(self, from_phase: str, to_phase: str) -> Optional[Dict[str, Any]]:
        """Get transition definition from state machine."""
        transitions = self._state_machine.get('transitions', [])
        for t in transitions:
            if t['from'] == from_phase and t['to'] == to_phase:
                return t
        return None
    
    async def transition(self, req: TransitionRequest) -> WorkflowTransitionResult:
        """
        Execute a phase transition using Saga pattern.
        
        Args:
            req: The transition request with version_hash
            
        Returns:
            WorkflowTransitionResult indicating success/failure
            
        Raises:
            TransitionConflictError: If version_hash mismatch (409)
            GateError: If gate check fails
        """
        # Canonical filename is ``<proposal_id>_PROPOSAL.md`` (set by
        # ProposalWriter.create_proposal and respected by every consumer).
        proposal_path = self.proposals_dir / f"{req.proposal_id}_PROPOSAL.md"

        if not proposal_path.exists():
            return WorkflowTransitionResult(
                success=False,
                proposal_id=req.proposal_id,
                error=f"Proposal file not found: {proposal_path}"
            )
        
        # Proposal files are markdown with a YAML frontmatter fence
        # (``---\n<yaml>\n---\n<body>``). yaml.safe_load chokes on the
        # closing ``---`` because PyYAML treats it as a multi-document
        # stream separator. Extract just the frontmatter block.
        raw = proposal_path.read_text(encoding='utf-8')
        if raw.startswith('---\n'):
            end = raw.find('\n---', 4)
            if end == -1:
                raise ValueError(
                    f"Malformed frontmatter in {proposal_path}: no closing ---"
                )
            current_data = yaml.safe_load(raw[4:end]) or {}
        else:
            current_data = yaml.safe_load(raw) or {}
        
        # Compute current version_hash and verify (G3/T2 compliance)
        current_hash = self._compute_version_hash(current_data)
        
        if current_hash != req.version_hash:
            raise TransitionConflictError(
                proposal_id=req.proposal_id,
                expected_hash=current_hash,
                actual_hash=req.version_hash
            )
        
        # Build Saga steps
        saga_steps: List[SagaStep] = []
        
        # Step 1: Snapshot prior state (T3: named compensate function)
        def snapshot_action():
            self._handoff_vault.snapshot(req.proposal_id, current_data)
        
        def snapshot_compensate():
            # Mark snapshot as superseded
            self._handoff_vault.mark_superseded(req.proposal_id)
        
        saga_steps.append(SagaStep(
            name="snapshot_prior_state",
            action=snapshot_action,
            compensate=snapshot_compensate
        ))
        
        # Step 2: Ensure proposal branch exists (T1: git operations with timeout)
        def branch_action():
            import asyncio
            asyncio.get_event_loop().run_until_complete(
                ensure_branch(req.proposal_id)
            )
        
        def branch_compensate():
            import asyncio
            asyncio.get_event_loop().run_until_complete(
                self._delete_branch(req.proposal_id)
            )
        
        saga_steps.append(SagaStep(
            name="ensure_proposal_branch",
            action=branch_action,
            compensate=branch_compensate
        ))
        
        # Step 3: Create execution tag if entering execution phase
        if req.target_substatus == 'coding' or req.target_phase == WorkflowPhase.ALPHA:
            def tag_action():
                import asyncio
                asyncio.get_event_loop().run_until_complete(
                    tag_execution_start(req.proposal_id)
                )
            
            def tag_compensate():
                import asyncio
                asyncio.get_event_loop().run_until_complete(
                    self._delete_tag(req.proposal_id, f"exec-start/{req.proposal_id}")
                )
            
            saga_steps.append(SagaStep(
                name="create_execution_tag",
                action=tag_action,
                compensate=tag_compensate
            ))
        
        # Step 4: Write updated YAML (T2: version_hash update). Critical:
        # rewrite ONLY the frontmatter block; the markdown body below
        # ``---\n`` is the proposal text and must be preserved verbatim.
        def _rewrite_frontmatter(updated_fm: Dict[str, Any]) -> None:
            raw = proposal_path.read_text(encoding='utf-8')
            if raw.startswith('---\n'):
                end = raw.find('\n---', 4)
                body = raw[end:] if end != -1 else ''
            else:
                body = '\n---\n' + raw
            new_fm = yaml.dump(updated_fm, default_flow_style=False, sort_keys=False)
            proposal_path.write_text(
                f"---\n{new_fm}{body}",
                encoding='utf-8',
            )

        def yaml_action():
            current_data['phase'] = req.target_phase.value
            if req.target_substatus:
                current_data['substatus'] = req.target_substatus
            current_data['approver'] = req.approver
            current_data['updated_at'] = datetime.utcnow().isoformat()
            _rewrite_frontmatter(current_data)

        def yaml_compensate():
            # Restore from snapshot
            snapshot = self._handoff_vault.get_latest(req.proposal_id)
            if snapshot:
                _rewrite_frontmatter(snapshot)
        
        saga_steps.append(SagaStep(
            name="write_yaml_update",
            action=yaml_action,
            compensate=yaml_compensate
        ))
        
        # Step 5: Log decision to approval log
        def log_action():
            self._approval_logger.log_approval_for_gate3(
                proposal_id=req.proposal_id,
                role='approver',
                decision='APPROVED',
                approver=req.approver
            )
        
        def log_compensate():
            # Remove the last entry - simplified for now
            pass
        
        saga_steps.append(SagaStep(
            name="log_decision",
            action=log_action,
            compensate=log_compensate
        ))
        
        # Execute Saga
        saga = SagaTransaction(steps=saga_steps)
        success = saga.execute()
        
        if not success:
            return WorkflowTransitionResult(
                success=False,
                proposal_id=req.proposal_id,
                error="Saga execution failed - partial rollback completed"
            )
        
        return WorkflowTransitionResult(
            success=True,
            proposal_id=req.proposal_id,
            new_phase=req.target_phase,
            new_substatus=req.target_substatus,
            git_tag=f"exec-start/{req.proposal_id}"
        )
    
    async def _delete_branch(self, proposal_id: str) -> None:
        """Delete a proposal branch (compensation)."""
        import asyncio
        from src.git_operations import GitOperationError as GitErr
        
        try:
            await ensure_branch(proposal_id)  # Check if exists
            await asyncio.to_thread(
                lambda: __import__('subprocess').run(
                    ['git', 'branch', '-D', f'feat/proposal-{proposal_id}'],
                    capture_output=True,
                    timeout=10
                )
            )
        except GitErr:
            pass  # Branch doesn't exist, that's fine for compensation
    
    async def _delete_tag(self, proposal_id: str, tag_name: str) -> None:
        """Delete a tag (compensation)."""
        import asyncio
        from src.git_operations import GitOperationError as GitErr
        
        try:
            await asyncio.to_thread(
                lambda: __import__('subprocess').run(
                    ['git', 'tag', '-d', tag_name],
                    capture_output=True,
                    timeout=10
                )
            )
        except GitErr:
            pass  # Tag doesn't exist, that's fine for compensation


# Global workflow engine instance
_workflow_engine: Optional[WorkflowEngine] = None


def get_workflow_engine() -> WorkflowEngine:
    """Get or create the global workflow engine instance."""
    global _workflow_engine
    if _workflow_engine is None:
        _workflow_engine = WorkflowEngine()
    return _workflow_engine


async def transition(req: TransitionRequest) -> WorkflowTransitionResult:
    """
    Convenience function to execute a transition.
    
    Args:
        req: The transition request
        
    Returns:
        WorkflowTransitionResult
    """
    engine = get_workflow_engine()
    return await engine.transition(req)