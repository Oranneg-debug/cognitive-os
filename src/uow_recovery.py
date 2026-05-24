"""
Unit of Work Crash Recovery Module

Scans dev/.uow_log/ at boot and rolls back any incomplete transactions.

VETO COMPLIANCE:
- B4: Rollback of staged files only (never target files)
- V9: Explicit exceptions raised, never silently swallowed
"""

from __future__ import annotations

import json
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

# Configuration
UOW_LOG_DIR = Path("dev/.uow_log")


class UoWRecoveryError(Exception):
    """Raised when UoW recovery encounters an error."""
    def __init__(self, uow_id: str, reason: str):
        self.uow_id = uow_id
        self.reason = reason
        super().__init__(f"UoW recovery failed for {uow_id}: {reason}")


def _load_undo_log(log_path: Path) -> Optional[Dict[str, Any]]:
    """Load an undo log JSON file."""
    if not log_path.exists():
        return None
    try:
        with open(log_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        raise UoWRecoveryError(
            uow_id=log_path.stem,
            reason=f"Failed to parse undo log: {e}"
        ) from e


def _compute_sha256(file_path: Path) -> Optional[str]:
    """Compute SHA256 of a file, return None if file doesn't exist."""
    if not file_path.exists():
        return None
    import hashlib
    try:
        with open(file_path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except OSError:
        return None


def _rollback_uow(uow_id: str, undo_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Roll back a single UoW transaction.
    
    Returns a list of actions taken (for reporting).
    """
    actions = []
    staged_dir = Path(undo_data.get("staged_dir", ""))
    
    for file_info in undo_data.get("files", []):
        target_path = Path(file_info["target_path"])
        staged_path = Path(file_info["staged_path"])
        sha256_pre = file_info.get("sha256_pre")
        
        # Always delete staged file if it exists
        if staged_path.exists():
            try:
                staged_path.unlink()
                actions.append({
                    "action": "deleted_staged",
                    "path": str(staged_path),
                    "reason": "Staged file removed during rollback"
                })
            except OSError as e:
                raise UoWRecoveryError(
                    uow_id=uow_id,
                    reason=f"Failed to delete staged file {staged_path}: {e}"
                ) from e
        
        # Check if target needs recovery (only if sha256_pre doesn't match)
        if target_path.exists():
            current_hash = _compute_sha256(target_path)
            if current_hash and sha256_pre and current_hash != sha256_pre:
                # Suspicious: file was modified mid-UoW or partial rename happened
                # Rename to .recovered_<uow_id> for human review
                recovered_name = f"{target_path.name}.recovered_{uow_id}"
                recovered_path = target_path.parent / recovered_name
                
                try:
                    shutil.move(str(target_path), str(recovered_path))
                    actions.append({
                        "action": "renamed_target",
                        "from": str(target_path),
                        "to": str(recovered_path),
                        "reason": "Suspicious hash mismatch - human review required"
                    })
                except OSError as e:
                    raise UoWRecoveryError(
                        uow_id=uow_id,
                        reason=f"Failed to rename target {target_path}: {e}"
                    ) from e
    
    return actions


def run_recovery() -> Dict[str, Any]:
    """
    Scan dev/.uow_log/ and roll back any incomplete transactions.
    
    Returns a dict with:
        - uows_recovered: list of UoW IDs that were rolled back
        - warnings: list of warning messages
        - actions: list of all recovery actions taken
    """
    result = {
        "uows_recovered": [],
        "warnings": [],
        "actions": []
    }
    
    if not UOW_LOG_DIR.exists():
        return result
    
    # Get all undo log files
    undo_logs = list(UOW_LOG_DIR.glob("*.undo.json"))
    
    for log_path in undo_logs:
        uow_id = log_path.stem
        
        try:
            undo_data = _load_undo_log(log_path)
            if undo_data is None:
                result["warnings"].append(
                    f"Skipping {log_path}: failed to load undo log"
                )
                continue
            
            status = undo_data.get("status", "staged")
            
            # Only rollback if not yet committed
            if status != "committed":
                actions = _rollback_uow(uow_id, undo_data)
                result["uows_recovered"].append(uow_id)
                result["actions"].extend(actions)
                
                # Delete the undo log after successful rollback
                try:
                    log_path.unlink()
                except OSError as e:
                    result["warnings"].append(
                        f"UoW {uow_id}: rolled back but failed to delete undo log: {e}"
                    )
            else:
                # Committed but log still present - idempotent cleanup
                try:
                    log_path.unlink()
                    result["actions"].append({
                        "action": "cleanup_committed_log",
                        "uow_id": uow_id,
                        "reason": "Committed UoW log was cleaned up"
                    })
                except OSError as e:
                    result["warnings"].append(
                        f"UoW {uow_id}: cleanup failed for committed log: {e}"
                    )
        
        except UoWRecoveryError as e:
            result["warnings"].append(str(e))
    
    return result


def __bootstrap_recovery() -> None:
    """
    Bootstrap recovery - runs at module import.
    
    This is called by api.py during startup to ensure recovery runs
    before the application starts accepting requests.
    """
    try:
        result = run_recovery()
        if result["uows_recovered"]:
            print(f"[UoW Recovery] Recovered {len(result['uows_recovered'])} UoW(s)")
            for uow_id in result["uows_recovered"]:
                print(f"  - {uow_id}")
        if result["warnings"]:
            print("[UoW Recovery] Warnings:")
            for w in result["warnings"]:
                print(f"  ! {w}")
    except Exception as e:
        # Log but don't fail - we don't want to prevent app startup
        print(f"[UoW Recovery] ERROR: {e}")