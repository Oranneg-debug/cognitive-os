"""
Development Route Module - Handles proposal lifecycle from Telegram/Obsidian triggers.

Routes: /dev (Telegram), #dev (Obsidian)

LIFECYCLE APPROVAL FLOW:
User must approve at EVERY stage:
1. Proposal → 2. Beta Council Review → 3. Beta Testing → 4. Alpha Polish → 5. Final Audit

Triggers:
- Telegram: /dev <proposal> (significant changes only)
- Obsidian: #dev <proposal> (significant changes only)
- Minor changes: Skip proposal phase, start at Beta

This module acts as a façade delegating to specialized modules:
- src.proposal_writer: Proposal CRUD operations
- src.handoff_writer: Handoff document generation
"""

import os
import uuid
import asyncio
from datetime import datetime
from typing import Optional

from src.sync_check import trigger_sync_check
from src.proposal_writer import ProposalWriter
from src.handoff_writer import HandoffWriter


# Proposal-ID prefix system:
#   DEV  — generic dev proposal (default for user / Telegram / Obsidian flows)
#   ARCH — Systems Architect agent output
#   NLST — analyst agents (Data Flow Tracer, System Analyst, Bench Runner)
PROPOSAL_ID_PREFIXES = ("DEV", "ARCH", "NLST")

# Mapping from origin string to ID prefix. Anything not listed falls back to DEV.
# Keys are matched case-insensitively against the `origin` string.
ORIGIN_TO_PREFIX = {
    "systems-architect":  "ARCH",
    "systems_architect":  "ARCH",
    "systems architect":  "ARCH",
    "architect":          "ARCH",
    "data-flow-tracer":   "NLST",
    "data_flow_tracer":   "NLST",
    "data flow tracer":   "NLST",
    "system-analyst":     "NLST",
    "system_analyst":     "NLST",
    "system analyst":     "NLST",
    "bench-runner":       "NLST",
    "bench_runner":       "NLST",
    "bench runner":       "NLST",
    "analyst":            "NLST",
}


def prefix_for_origin(origin: str) -> str:
    """Return the ID prefix (DEV / ARCH / NLST) for a given origin string.

    Unknown origins fall back to DEV so existing callers keep working.
    """
    if not origin:
        return "DEV"
    return ORIGIN_TO_PREFIX.get(origin.strip().lower(), "DEV")


def generate_kanban_card_id(prefix: str = "DEV") -> str:
    """
    Generate a unique Kanban card ID for a proposal.

    Args:
        prefix: ID prefix (DEV / ARCH / NLST). Unknown prefixes fall back to DEV.

    Returns:
        str: Card ID in format ^[<PREFIX>-YYYYMMDDHHMMSS-XXXX]
    """
    prefix = prefix if prefix in PROPOSAL_ID_PREFIXES else "DEV"
    return f"^[{prefix}-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6].upper()}]"


class DevRouteManager:
    """
    Manages the development lifecycle workflow for proposals.
    
    This class acts as a façade delegating to specialized modules:
    - ProposalWriter: Proposal CRUD operations
    - HandoffWriter: Handoff document generation
    
    EVERY PHASE REQUIRES EXPLICIT USER APPROVAL before proceeding.
    """

    def __init__(self, orchestrator=None):
        """
        Initialize the dev route manager.
        
        Args:
            orchestrator: Optional orchestrator instance for lifecycle continuation
        """
        self.orchestrator = orchestrator
        self.proposal_writer = ProposalWriter()
        self.handoff_writer = HandoffWriter()

    def process_dev_proposal(
        self,
        user_input: str,
        origin: str = "unknown",
        needs_approval: bool = True,
        source_file_path: str = None
    ) -> dict:
        """
        Process a development proposal request.

        This is a convenience wrapper around create_proposal that handles
        the common case of creating a proposal from a user request.

        Args:
            user_input: The proposal description
            origin: Where the proposal came from ("telegram", "obsidian", etc.)
            needs_approval: Whether user approval is required (default True)
            source_file_path: Optional path to the originating note/file

        Returns:
            dict with proposal_id, filepath, status, and approval_info
        """
        return self.proposal_writer.create_proposal(
            user_input=user_input,
            origin=origin,
            needs_approval=needs_approval,
            llm_proposal_data=None,
            source_file_path=source_file_path
        )

    def generate_beta_handoff(self, proposal_id: str, council_report: str) -> dict:
        """
        Generate a Beta Testing Handoff document from the Technical Council's report.

        Args:
            proposal_id:   The DEV-… ID of the proposal.
            council_report: The full markdown report produced by execute_technical_meeting().

        Returns:
            dict with 'vault_path', 'source_path', and 'filename' keys, or
            {'error': <message>} on failure.
        """
        return self.handoff_writer.generate_beta_handoff(
            proposal_id=proposal_id,
            council_report=council_report
        )

    def generate_alpha_handoff(self, proposal_id: str, council_report: str) -> dict:
        """
        Generate an Alpha Polish Handoff document from the Boardroom report.

        Args:
            proposal_id:    The DEV-… ID of the proposal.
            council_report: The full markdown report produced by the boardroom.

        Returns:
            dict with 'vault_path', 'source_path', 'filename', or
            {'error': <message>} on failure.
        """
        return self.handoff_writer.generate_alpha_handoff(
            proposal_id=proposal_id,
            council_report=council_report
        )

    async def review_proposal(
        self,
        proposal_id: str,
        approver: str,
        reason: str
    ) -> dict:
        """
        Transition a proposal from backlog/proposal to beta_testing/planning.

        Args:
            proposal_id: The ID of the proposal
            approver: Name of the approving entity
            reason: Reason for the transition

        Returns:
            dict with transition result
        """
        try:
            from src.workflow_engine import WorkflowEngine
            from src.workflow_models import TransitionRequest, WorkflowPhase
            
            engine = WorkflowEngine()
            
            req = TransitionRequest(
                proposal_id=proposal_id,
                target_phase=WorkflowPhase.BETA_TESTING,
                target_substatus="planning",
                approver=approver,
                reason=reason
            )
            
            result = await engine.transition(req)
            
            if not result.success:
                return {"error": f"Transition failed: {result.error}"}
            
            return {
                "success": True,
                "proposal_id": proposal_id,
                "new_phase": result.new_phase.value if result.new_phase else None,
                "new_substatus": result.new_substatus
            }
        except Exception as e:
            return {"error": f"Failed to review proposal: {str(e)}"}

    async def create_alpha_plan(
        self,
        proposal_id: str,
        approver: str,
        reason: str
    ) -> dict:
        """
        Transition a proposal from beta_testing/execution to alpha phase.

        Args:
            proposal_id: The ID of the proposal
            approver: Name of the approving entity
            reason: Reason for the transition

        Returns:
            dict with transition result
        """
        try:
            from src.workflow_engine import WorkflowEngine
            from src.workflow_models import TransitionRequest, WorkflowPhase
            
            engine = WorkflowEngine()
            
            req = TransitionRequest(
                proposal_id=proposal_id,
                target_phase=WorkflowPhase.ALPHA,
                target_substatus=None,
                approver=approver,
                reason=reason
            )
            
            result = await engine.transition(req)
            
            if not result.success:
                return {"error": f"Transition failed: {result.error}"}
            
            return {
                "success": True,
                "proposal_id": proposal_id,
                "new_phase": result.new_phase.value if result.new_phase else None,
                "new_substatus": result.new_substatus
            }
        except Exception as e:
            return {"error": f"Failed to create alpha plan: {str(e)}"}

    def finalize_release(self, proposal_id: str, release_notes: str) -> dict:
        """
        Finalize a release for a proposal.

        Args:
            proposal_id: The ID of the proposal
            release_notes: The release notes for this version

        Returns:
            dict with release information
        """
        import glob

        proposals_dir = self.proposal_writer.proposals_dir
        vault_proposals_dir = self.proposal_writer.vault_proposals_dir

        # Search in both project and vault directories.
        # New-format filenames: <ID>_PROPOSAL.md (no leading prefix).
        # Old-format filenames: <date>_<ID>_PROPOSAL.md (with date prefix).
        # The wildcard covers both.
        patterns = [
            f"{proposals_dir}/{proposal_id}_PROPOSAL.md",
            f"{proposals_dir}/*_{proposal_id}_PROPOSAL.md",
            f"{vault_proposals_dir}/{proposal_id}_PROPOSAL.md",
            f"{vault_proposals_dir}/*_{proposal_id}_PROPOSAL.md",
        ]

        files = []
        for pattern in patterns:
            files.extend(glob.glob(pattern))

        if not files:
            return {"error": f"Proposal {proposal_id} not found"}

        filepath = files[0]

        from src.workflow_engine import WorkflowEngine
        engine = WorkflowEngine()
        
        from src.workflow_models import TransitionRequest, WorkflowPhase
        
        req = TransitionRequest(
            proposal_id=proposal_id,
            target_phase=WorkflowPhase.FINALIZED,
            target_substatus="released",
            approver="system",
            reason="Finalized via dev route",
            version_hash=""  # Final audit bypasses optimistic lock
        )
        
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(engine.transition(req))
            loop.close()
            if not result.success:
                return {"error": f"Failed to finalize proposal: {result.error}"}
        except Exception as e:
            return {"error": f"Failed to finalize proposal: {str(e)}"}

        # Write release notes to the handoff writer which should handle the markdown
        # (Assuming handoff_writer handles appending this cleanly now instead of regex in this file)
        
        return {
            "success": True,
            "proposal_id": proposal_id,
            "filepath": "delegated_to_engine",
            "status": "finalized"
        }

    def sync_proposals(self) -> dict:
        """
        Sync proposals from backend to vault.

        Returns:
            dict with sync result information
        """
        return self.proposal_writer.sync_proposals()