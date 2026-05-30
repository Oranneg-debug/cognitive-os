"""
Kanban Processor - Bridge between Kanban Column Drag and Workflow Engine

This module translates kanban store column updates into workflow engine
phase transitions, ensuring all phase writes go through the central
WorkflowEngine as required by V2 (no direct phase writes outside engine).

VETO COMPLIANCE:
- V2: All phase transitions delegate to workflow_engine.transition()
- A6: Column-drag handler calls workflow_engine.transition()
"""

from __future__ import annotations

from typing import Optional, Dict, Any
from src.workflow_engine import WorkflowEngine
from src.workflow_models import (
    TransitionRequest,
    WorkflowPhase,
    BetaSubstatus,
)


# Mapping from Kanban columns to workflow phases/substatuses
# This is the single source of truth for column → phase translation
KANBAN_TO_PHASE_MAP: Dict[str, Dict[str, Any]] = {
    "backlog": {"phase": WorkflowPhase.BACKLOG, "substatus": None},
    "proposal": {"phase": WorkflowPhase.PROPOSAL, "substatus": None},
    "beta testing": {"phase": WorkflowPhase.BETA_TESTING, "substatus": "planning"},
    "alpha polish": {"phase": WorkflowPhase.ALPHA, "substatus": None},
    "finalized": {"phase": WorkflowPhase.FINALIZED, "substatus": None},
    "deployed": {"phase": WorkflowPhase.DEPLOYED, "substatus": None},
}


def get_phase_for_column(column_name: str) -> Optional[WorkflowPhase]:
    """
    Get the workflow phase for a given Kanban column name.
    
    Args:
        column_name: The name of the Kanban column
        
    Returns:
        The corresponding WorkflowPhase, or None if column not found
    """
    return KANBAN_TO_PHASE_MAP.get(column_name.lower(), {}).get("phase")


def get_substatus_for_column(column_name: str) -> Optional[str]:
    """
    Get the substatus for a given Kanban column name.
    
    Args:
        column_name: The name of the Kanban column
        
    Returns:
        The corresponding substatus, or None if not applicable
    """
    return KANBAN_TO_PHASE_MAP.get(column_name.lower(), {}).get("substatus")


async def handle_column_drag(
    proposal_id: str,
    from_column: str,
    to_column: str,
    approver: str,
    reason: str,
) -> Dict[str, Any]:
    """
    Handle a column drag operation by triggering a workflow transition.
    
    This is the main entry point for Kanban → Workflow transitions.
    It translates the column names to phases and delegates to the
    WorkflowEngine.transition() method.
    
    Args:
        proposal_id: The ID of the proposal being moved
        from_column: The source Kanban column
        to_column: The target Kanban column
        approver: Name of the approving entity
        reason: Reason for the transition
        
    Returns:
        Dictionary with transition result containing:
        - success: bool
        - new_phase: str or None
        - new_substatus: str or None
        - error: str or None (if failed)
        
    VETO COMPLIANCE:
    - V2: All phase writes delegated to workflow_engine.transition()
    """
    # Look up target phase and substatus from column mapping
    target_config = KANBAN_TO_PHASE_MAP.get(to_column.lower())
    
    if not target_config:
        return {
            "success": False,
            "error": f"Unknown target column: {to_column}",
        }
    
    target_phase = target_config["phase"]
    target_substatus = target_config["substatus"]
    
    # Look up source phase for gate checks (if needed)
    source_config = KANBAN_TO_PHASE_MAP.get(from_column.lower())
    if source_config:
        # The workflow engine will validate the transition
        pass
    
    try:
        # Delegate to WorkflowEngine.transition()
        engine = WorkflowEngine()
        
        req = TransitionRequest(
            proposal_id=proposal_id,
            target_phase=target_phase,
            target_substatus=target_substatus,
            approver=approver,
            reason=reason,
        )
        
        result = await engine.transition(req)
        
        if not result.success:
            return {
                "success": False,
                "error": result.error or "Transition failed",
            }
        
        return {
            "success": True,
            "proposal_id": proposal_id,
            "from_column": from_column,
            "to_column": to_column,
            "new_phase": result.new_phase.value if result.new_phase else None,
            "new_substatus": result.new_substatus,
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to process column drag: {str(e)}",
        }


async def handle_beta_substatus_change(
    proposal_id: str,
    substatus: str,
    approver: str,
    reason: str,
) -> Dict[str, Any]:
    """
    Handle a beta substatus change without column change.
    
    Used for transitions like:
    - planning → coding
    - coding → debugging
    - debugging → testing
    - testing → ready-for-alpha
    
    Args:
        proposal_id: The ID of the proposal
        substatus: The target beta substatus
        approver: Name of the approving entity
        reason: Reason for the transition
        
    Returns:
        Dictionary with transition result
    """
    try:
        engine = WorkflowEngine()
        
        req = TransitionRequest(
            proposal_id=proposal_id,
            target_phase=WorkflowPhase.BETA_TESTING,
            target_substatus=substatus,
            approver=approver,
            reason=reason,
        )
        
        result = await engine.transition(req)
        
        if not result.success:
            return {
                "success": False,
                "error": result.error or "Transition failed",
            }
        
        return {
            "success": True,
            "proposal_id": proposal_id,
            "new_substatus": result.new_substatus,
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to update substatus: {str(e)}",
        }


# Column name validation
VALID_COLUMNS = set(KANBAN_TO_PHASE_MAP.keys())


def is_valid_column(column_name: str) -> bool:
    """Check if a column name is valid."""
    return column_name.lower() in KANBAN_TO_PHASE_MAP


def get_all_columns() -> list[str]:
    """Return the list of all valid Kanban column names."""
    return sorted(KANBAN_TO_PHASE_MAP.keys(), key=lambda c: KANBAN_TO_PHASE_MAP[c]["phase"].order)