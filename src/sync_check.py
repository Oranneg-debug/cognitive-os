"""
Sync Check Helper Module

Unified implementation of sync status checking for the Cognitive OS.
Fixes the dead-code bug in the original `_trigger_sync_check` implementations.

Usage:
    from src.sync_check import trigger_sync_check
    result = trigger_sync_check()
"""

from typing import Dict, Optional


def get_sync_manager():
    """
    Get or create the ProposalSyncManager instance.
    
    Returns:
        ProposalSyncManager: The sync manager instance or None if unavailable
    """
    try:
        from src.proposal_sync import ProposalSyncManager
        return ProposalSyncManager()
    except ImportError:
        # Fallback if proposal_sync module is not available
        return None


def trigger_sync_check() -> Dict[str, Optional[str]]:
    """
    Trigger a sync check and log any issues.
    
    Returns:
        dict with sync status information:
        - health: 'green', 'yellow', 'red', or 'unknown'
        - missing_in_vault: list of files missing in vault
        - conflicts: list of conflicting files
        - error: error message if an exception occurred, None otherwise
    """
    try:
        sync_manager = get_sync_manager()
        if sync_manager:
            status = sync_manager.check_sync_status()
            status_dict = status.to_dict()
            
            # Log warnings for yellow/red status
            if status_dict.get("health") == "yellow":
                print(f"⚠️ Sync Warning: {len(status_dict.get('missing_in_vault', []))} proposals missing in vault")
            elif status_dict.get("health") == "red":
                print(f"🚨 Sync Error: {len(status_dict.get('conflicts', []))} conflicts detected, "
                      f"{len(status_dict.get('missing_in_vault', []))} missing")
            
            return status_dict
    except Exception as e:
        print(f"Warning: Could not perform sync check: {e}")
    
    # Deterministic fallback (no dead code)
    return {"health": "unknown", "error": "Sync manager unavailable"}


__all__ = ["trigger_sync_check"]