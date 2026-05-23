"""
Proposal Sync Manager - Bridges backend proposals with Obsidian vault mirror.

This module provides a ProposalSyncManager class that handles:
- One-way sync from backend to vault
- Health monitoring (green/yellow/red status)
- Conflict detection between backend and vault
- Content-addressable hashing for change detection

Usage:
    from src.proposal_sync import ProposalSyncManager
    
    sync_manager = ProposalSyncManager()
    status = sync_manager.check_sync_status()
    if status["health"] == "red":
        sync_manager.sync_backend_to_vault()
"""

import os
import hashlib
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, asdict

# Import centralized paths from paths.py
from src.paths import VAULT_ROOT


# ============================================================================
# Constants
# ============================================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEV_DIR = PROJECT_ROOT / "dev"
PROPOSALS_DIR = DEV_DIR / "proposals"
VAULT_PROPOSALS_DIR = VAULT_ROOT / "1. P - Seedlings" / "dev" / "proposals"

SYNC_HISTORY_FILE = DEV_DIR / ".sync_history.json"


# ============================================================================
# Data Classes
# ============================================================================

@dataclass(frozen=True)
class ProposalFile:
    """Represents a proposal file with its metadata."""
    filename: str
    path: Path
    content_hash: str
    size: int
    created_at: datetime
    modified_at: datetime
    proposal_id: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "filename": self.filename,
            "path": str(self.path),
            "content_hash": self.content_hash,
            "size": self.size,
            "created_at": self.created_at.isoformat(),
            "modified_at": self.modified_at.isoformat(),
            "proposal_id": self.proposal_id
        }


@dataclass(frozen=True)
class SyncResult:
    """Result of a sync operation."""
    success: bool
    files_synced: int = 0
    files_skipped: int = 0
    files_conflicted: int = 0
    errors: List[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "success": self.success,
            "files_synced": self.files_synced,
            "files_skipped": self.files_skipped,
            "files_conflicted": self.files_conflicted,
            "errors": self.errors or []
        }


@dataclass(frozen=True)
class SyncStatus:
    """Current sync status with health indicator."""
    health: str  # "green", "yellow", or "red"
    backend_count: int = 0
    vault_count: int = 0
    missing_in_vault: List[str] = None
    conflicts: List[Dict[str, Any]] = None
    last_sync: Optional[str] = None
    last_sync_duration_ms: Optional[int] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "health": self.health,
            "backend_count": self.backend_count,
            "vault_count": self.vault_count,
            "missing_in_vault": self.missing_in_vault or [],
            "conflicts": self.conflicts or [],
            "last_sync": self.last_sync,
            "last_sync_duration_ms": self.last_sync_duration_ms
        }


# ============================================================================
# ProposalSyncManager Class
# ============================================================================

class ProposalSyncManager:
    """
    Manages synchronization between backend proposals and Obsidian vault.
    
    Provides one-way sync from backend to vault, health monitoring,
    and conflict detection with content-addressable hashing.
    """
    
    def __init__(
        self,
        proposals_dir: Optional[Path] = None,
        vault_dir: Optional[Path] = None,
        history_file: Optional[Path] = None
    ):
        """
        Initialize the sync manager.
        
        Args:
            proposals_dir: Path to backend proposals directory
            vault_dir: Path to vault proposals directory
            history_file: Path to sync history file
        """
        self.proposals_dir = proposals_dir or PROPOSALS_DIR
        self.vault_dir = vault_dir or VAULT_PROPOSALS_DIR
        self.history_file = history_file or SYNC_HISTORY_FILE
        
        # Ensure directories exist
        self.proposals_dir.mkdir(parents=True, exist_ok=True)
        self.vault_dir.mkdir(parents=True, exist_ok=True)
        
        # Load sync history
        self.sync_history = self._load_sync_history()
    
    def _load_sync_history(self) -> Dict[str, Any]:
        """Load sync history from file."""
        if self.history_file.exists():
            try:
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                return {"syncs": []}
        return {"syncs": []}
    
    def _save_sync_history(self) -> None:
        """Save sync history to file."""
        try:
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(self.sync_history, f, indent=2)
        except IOError as e:
            print(f"Warning: Could not save sync history: {e}")
    
    def _calculate_hash(self, file_path: Path) -> str:
        """
        Calculate SHA256 hash of a file for content-addressable comparison.
        
        Args:
            file_path: Path to the file
            
        Returns:
            Hexadecimal hash string
        """
        sha256_hash = hashlib.sha256()
        try:
            with open(file_path, 'rb') as f:
                for byte_block in iter(lambda: f.read(4096), b""):
                    sha256_hash.update(byte_block)
            return sha256_hash.hexdigest()
        except (IOError, OSError):
            return ""
    
    def _extract_proposal_id(self, content: str) -> Optional[str]:
        """
        Extract proposal ID from file content.
        
        Args:
            content: File content
            
        Returns:
            Proposal ID string or None
        """
        import re
        # Match pattern like <PREFIX>-YYYYMMDD-HHMMSS-XXXXXXXX where PREFIX is DEV / ARCH / NLST
        match = re.search(r'(?:DEV|ARCH|NLST)-\d{8}-\d{6}-[A-Z0-9]+', content)
        return match.group(0) if match else None
    
    def _get_proposal_files(self, directory: Path) -> List[ProposalFile]:
        """
        Get all proposal files from a directory.
        
        Args:
            directory: Directory to scan
            
        Returns:
            List of ProposalFile objects
        """
        proposals = []
        if not directory.exists():
            return proposals
        
        for file_path in directory.glob("*.md"):
            try:
                content = file_path.read_text(encoding='utf-8')
                content_hash = self._calculate_hash(file_path)
                
                proposal_id = self._extract_proposal_id(content)
                
                stat_info = file_path.stat()
                proposals.append(ProposalFile(
                    filename=file_path.name,
                    path=file_path,
                    content_hash=content_hash,
                    size=stat_info.st_size,
                    created_at=datetime.fromtimestamp(stat_info.st_ctime),
                    modified_at=datetime.fromtimestamp(stat_info.st_mtime),
                    proposal_id=proposal_id
                ))
            except (IOError, OSError, UnicodeDecodeError) as e:
                print(f"Warning: Could not process {file_path}: {e}")
        
        return proposals
    
    def check_sync_status(self) -> SyncStatus:
        """
        Check current sync status and determine health.
        
        Returns:
            SyncStatus with health indicator and details
        """
        backend_files = self._get_proposal_files(self.proposals_dir)
        vault_files = self._get_proposal_files(self.vault_dir)
        
        # Create lookup dictionaries
        backend_hashes = {f.filename: f for f in backend_files}
        vault_hashes = {f.filename: f for f in vault_files}
        
        # Find missing files (in backend but not in vault)
        missing_in_vault = [
            filename for filename in backend_hashes.keys()
            if filename not in vault_hashes
        ]
        
        # Find conflicts (files that exist in both but have different content)
        conflicts = []
        for filename, backend_file in backend_hashes.items():
            if filename in vault_hashes:
                vault_file = vault_hashes[filename]
                if backend_file.content_hash != vault_file.content_hash:
                    conflicts.append({
                        "filename": filename,
                        "backend_hash": backend_file.content_hash,
                        "vault_hash": vault_file.content_hash,
                        "backend_modified": backend_file.modified_at.isoformat(),
                        "vault_modified": vault_file.modified_at.isoformat()
                    })
        
        # Determine health
        if len(missing_in_vault) == 0 and len(conflicts) == 0:
            health = "green"
        elif len(missing_in_vault) > 0 and len(conflicts) == 0:
            health = "yellow"  # Missing files but no conflicts
        else:
            health = "red"  # Has conflicts or other issues
        
        # Get last sync info
        last_sync = None
        last_sync_duration_ms = None
        if self.sync_history.get("syncs"):
            last_sync_info = self.sync_history["syncs"][-1]
            last_sync = last_sync_info.get("timestamp")
            last_sync_duration_ms = last_sync_info.get("duration_ms")
        
        return SyncStatus(
            health=health,
            backend_count=len(backend_files),
            vault_count=len(vault_files),
            missing_in_vault=missing_in_vault,
            conflicts=conflicts,
            last_sync=last_sync,
            last_sync_duration_ms=last_sync_duration_ms
        )
    
    def sync_backend_to_vault(self) -> SyncResult:
        """
        Perform one-way sync from backend to vault.
        
        Files are copied from backend to vault. If a file exists in both
        locations, the vault version is overwritten with the backend version.
        
        Returns:
            SyncResult with details about the operation
        """
        start_time = datetime.now()
        errors = []
        files_synced = 0
        files_skipped = 0
        
        backend_files = self._get_proposal_files(self.proposals_dir)
        
        for file in backend_files:
            try:
                dest_path = self.vault_dir / file.filename
                
                # Copy file from backend to vault
                shutil.copy2(file.path, dest_path)
                files_synced += 1
                
            except (IOError, OSError, shutil.Error) as e:
                errors.append(f"Failed to sync {file.filename}: {str(e)}")
        
        # Calculate duration
        duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
        
        # Update sync history
        self.sync_history["syncs"].append({
            "timestamp": datetime.now().isoformat(),
            "duration_ms": duration_ms,
            "files_synced": files_synced,
            "files_skipped": files_skipped,
            "errors": errors
        })
        
        # Keep only last 100 sync records
        if len(self.sync_history["syncs"]) > 100:
            self.sync_history["syncs"] = self.sync_history["syncs"][-100:]
        
        self._save_sync_history()
        
        success = len(errors) == 0
        
        return SyncResult(
            success=success,
            files_synced=files_synced,
            files_skipped=files_skipped,
            errors=errors
        )
    
    def detect_conflicts(self) -> List[Dict[str, Any]]:
        """
        Detect files with conflicts between backend and vault.
        
        Returns:
            List of conflict dictionaries with details
        """
        return self.check_sync_status().conflicts
    
    def get_missing_files(self) -> List[str]:
        """
        Get list of files missing in vault (exist in backend only).
        
        Returns:
            List of filenames
        """
        return self.check_sync_status().missing_in_vault
    
    def get_file_content(self, filename: str, location: str = "backend") -> Optional[str]:
        """
        Get content of a file from specified location.
        
        Args:
            filename: Name of the file
            location: "backend" or "vault"
            
        Returns:
            File content or None if not found
        """
        directory = self.proposals_dir if location == "backend" else self.vault_dir
        file_path = directory / filename
        
        if file_path.exists():
            try:
                return file_path.read_text(encoding='utf-8')
            except (IOError, UnicodeDecodeError):
                return None
        return None
    
    def get_sync_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get sync history.
        
        Args:
            limit: Maximum number of records to return
            
        Returns:
            List of sync records
        """
        return self.sync_history.get("syncs", [])[-limit:]
    
    def force_sync(self) -> SyncResult:
        """
        Force a sync operation (alias for sync_backend_to_vault).
        
        Returns:
            SyncResult with details about the operation
        """
        return self.sync_backend_to_vault()
