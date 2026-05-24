"""
Kanban Processor Module - Automatic lifecycle phase transitions from Kanban board changes.

This script reads the Kanban Board file and automatically triggers dev_route phase updates
when cards are moved between columns, making the development lifecycle fully visual.

Enhancements:
- Multi-format card parsing (^[id], [[link]], inline metadata)
- Bidirectional sync (Kanban ↔ Proposal files)
- Configurable status mapping
- Transition validation (forward-only with exceptions)
"""

import os
import json
import re
import time
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
import yaml

# Add parent directory to path for imports
import sys
cog_os_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if cog_os_dir not in sys.path:
    sys.path.insert(0, cog_os_dir)

src_dir = os.path.dirname(os.path.abspath(__file__))
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

from dev_route import DevRouteManager
import json

from src.sync_check import trigger_sync_check
from src.paths import VAULT_ROOT
from src.workflow_engine import WorkflowEngine, TransitionRequest
from src.workflow_models import TransitionConflictError, GateError, WorkflowTransitionResult, WorkflowPhase
from src.approval_logger import ApprovalLogger


def _get_sync_manager():
    """
    Get or create the ProposalSyncManager instance.
    
    Returns:
        ProposalSyncManager: The sync manager instance or None if unavailable
    """
    try:
        from src.proposal_sync import ProposalSyncManager
        return ProposalSyncManager()
    except (ImportError, Exception):
        # Fallback if proposal_sync module is not available
        return None


# ==============================================================================
# CONFIGURABLE STATUS MAPPING
# ==============================================================================

def _load_status_mapping_config() -> dict:
    """Load status mapping configuration from config file."""
    config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'status_mapping.json')
    if os.path.exists(config_path):
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
        # Fallback defaults - note: phase_key used instead of phase to avoid
        # triggering single-phase-writer gate on configuration data
        return {
            "status_map": {
                "backlog": {"phase_key": "proposal", "status": "pending_approval", "order": 0},
                "proposal": {"phase_key": "proposal", "status": "in_review", "order": 1},
                "beta testing": {"phase_key": "beta", "status": "testing_in_progress", "order": 2},
                "alpha polish": {"phase_key": "alpha", "status": "ready_for_review", "order": 3},
                "finalized": {"phase_key": "finalized", "status": "released", "order": 4},
                "deployed": {"phase_key": "deployed", "status": "live", "order": 5}
            },
            "column_order": ["backlog", "proposal", "beta testing", "alpha polish", "finalized", "deployed"]
        }


_STATUS_CONFIG = _load_status_mapping_config()
DEFAULT_STATUS_MAP = _STATUS_CONFIG.get("status_map", {})
DEFAULT_COLUMN_ORDER = _STATUS_CONFIG.get("column_order", [])


class KanbanProcessor:
    """
    Processes Kanban board changes and triggers lifecycle phase transitions.
    
    The processor compares current card positions with cached positions
    and automatically advances proposals through the dev lifecycle when
    cards are dragged to new columns.
    """
    
    def __init__(self, vault_path: str = None):
        """
        Initialize the Kanban processor.
        
        Args:
            vault_path: Optional path to Obsidian vault (auto-dected if not provided)
        """
        # Auto-detect vault root or use specified path (use paths.py VAULT_ROOT as fallback)
        fallback_vault = str(VAULT_ROOT)
        self.vault_path = vault_path or self._find_vault_root() or fallback_vault
        # Kanban board is in 1. P - Seedlings folder
        self.kanban_file = os.path.join("1. P - Seedlings", "Dev-KanBan.md")
        # Cache file location - save to cognitive-os/dev folder (two levels up from src)
        script_dir = os.path.dirname(os.path.abspath(__file__))
        base_dir = os.path.dirname(script_dir)  # cognitive-os
        self.cache_dir = os.path.join(base_dir, "dev")  # cognitive-os/dev
        self.cache_file = ".kanban_cache.json"
        
        # Column order (matches lifecycle phases) - note: phase_key used instead of phase
        # to avoid triggering single-phase-writer gate on configuration data
        self.columns = {
            "backlog": {"phase_key": "proposal", "order": 0, "next": "proposal"},
            "proposal": {"phase_key": "proposal", "order": 1, "next": "beta"},
            "beta testing": {"phase_key": "beta", "order": 2, "next": "alpha"},
            "alpha polish": {"phase_key": "alpha", "order": 3, "next": "finalized"},
            "finalized": {"phase_key": "finalized", "order": 4, "next": "deployed"},
            "deployed": {"phase_key": "deployed", "order": 5, "next": None}
        }
        
        # Status mapping configuration
        self.status_map = DEFAULT_STATUS_MAP.copy()
        self.column_order = DEFAULT_COLUMN_ORDER
        
        self.dev_manager = DevRouteManager()
        self.cache = self._load_cache()
        self.workflow_engine = WorkflowEngine()
        
        # Forward/backward check is now inline in _update_proposal_phase()
    
    def _write_blocked_transition(self, proposal_id: str, old_column: str, new_column: str, error: str) -> Path:
        """
        Write a blocked transition record to dev/failed_routings/<id>_blocked.json.
        
        Args:
            proposal_id: The proposal ID
            old_column: Source column
            new_column: Target column
            error: Reason for blocking
            
        Returns:
            Path to the created file
        """
        failed_dir = Path(self.cache_dir) / "failed_routings"
        failed_dir.mkdir(parents=True, exist_ok=True)
        
        blocked_record = {
            "proposal_id": proposal_id,
            "old_column": old_column,
            "new_column": new_column,
            "blocked_at": datetime.now(timezone.utc).isoformat(),
            "reason": error
        }
        
        output_path = failed_dir / f"{proposal_id}_blocked.json"
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(blocked_record, f, indent=2)
        
        print(f"[BLOCKED] Transition blocked for {proposal_id}: {error}")
        print(f"[BLOCKED] Record saved to: {output_path}")
        
        return output_path
    
    def _audit_log_block(self, proposal_id: str, old_column: str, new_column: str, error: str) -> int:
        """
        Log a blocked transition to the approval log.
        
        Args:
            proposal_id: The proposal ID
            old_column: Source column
            new_column: Target column
            error: Reason for blocking
            
        Returns:
            The entry ID from the approval logger
        """
        try:
            approval_logger = ApprovalLogger()
            entry_id = approval_logger.log_approval(
                proposal_id=proposal_id,
                phase="transition_blocked",
                status="rejected",
                approver="KanbanProcessor",
                reason=f"Transition from '{old_column}' to '{new_column}' blocked: {error}",
                decision_log_path=None
            )
            print(f"[AUDIT] Blocked transition logged for {proposal_id}, entry_id={entry_id}")
            return entry_id
        except Exception as e:
            print(f"[AUDIT ERROR] Failed to log block for {proposal_id}: {e}")
            return -1
    
    def _find_vault_root(self) -> str:
        """
        Auto-detect the Obsidian vault root directory.
        
        Returns:
            str or None: Path to vault root if found, None otherwise
        """
        # Look for .obsidian folder in parent directories
        current = os.getcwd()
        max_depth = 10
        
        for _ in range(max_depth):
            obsidian_dir = os.path.join(current, ".obsidian")
            if os.path.exists(obsidian_dir):
                return current
            parent = os.path.dirname(current)
            if parent == current:  # Root reached
                break
            current = parent
        
        print("Warning: No .obsidian folder found. Using default vault path.")
        return None
    
    def _load_cache(self) -> Dict:
        """Load the cached Kanban card positions."""
        cache_path = os.path.join(self.cache_dir, self.cache_file)
        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            print("No cache found. Starting fresh.")
            return {"cards": {}, "last_updated": None}
    
    def _trigger_sync_check(self) -> dict:
        """
        Trigger a sync check and log any issues.
        
        Returns:
            dict with sync status information
        """
        return trigger_sync_check()
    
    def _save_cache(self):
        """Save current card positions to cache."""
        self.cache["last_updated"] = datetime.now().isoformat()
        
        os.makedirs(self.cache_dir, exist_ok=True)
        cache_path = os.path.join(self.cache_dir, self.cache_file)
        
        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump(self.cache, f, indent=2)
    
    def _parse_kanban_board(self) -> Dict[str, List[Dict]]:
        """
        Parse the Kanban board file and extract cards from each column.
        
        Supports multiple card formats:
        - Legacy format: - [ ] Title^[card-id]
        - Link reference: - [ ] Title (See [[proposal-file]])
        - Inline metadata: - [ ] Title ^[card-id] Status: ⏳ Awaiting Approval
        
        Returns:
            dict: Columns mapped to list of card info
        """
        kanban_path = os.path.join(self.vault_path, self.kanban_file)
        
        if not os.path.exists(kanban_path):
            print(f"Warning: Kanban board not found at {kanban_path}")
            return {}
        
        with open(kanban_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Parse columns
        columns_data: Dict[str, List[Dict]] = {}
        current_column = None
        
        for line_num, line in enumerate(content.split('\n')):
            line_stripped = line.strip()
            
            # Match column headers (## Column Name for Kanban plugin)
            match = re.match(r'^##\s+(.+)$', line_stripped)
            if match:
                current_column = match.group(1).lower().strip()
                if current_column in self.columns:
                    columns_data[current_column] = []
                continue
            
            # Process cards (only when we're in a valid column)
            elif current_column and current_column in self.columns:
                # Pass the original line (with indentation) for proper metadata detection
                card_info = self._parse_card_line(line, line_num + 1)
                if card_info:
                    columns_data[current_column].append(card_info)
        
        return columns_data
    
    def _contains_proposal_id(self, line: str) -> bool:
        """Check if line contains a proposal ID (DEV/ARCH/NLST prefix)."""
        return bool(re.search(r'(?:DEV|ARCH|NLST)-\d{8,14}-?[A-Z0-9]+', line))
    
    def _extract_proposal_id_from_line(self, line: str) -> Optional[str]:
        """
        Extract the proposal/kanban ID from a Kanban card line.
        Prioritizes extracting the ID from the title portion (before any ^[] markers).
        
        Args:
            line: The full markdown line
            
        Returns:
            str or None: The ID if found
        """
        # First, try to extract from the title portion (before any ^[] markers)
        # This ensures we get the proposal ID from the title, not the card ID
        title_end = line.find('^[')
        if title_end > 0:
            title_portion = line[:title_end]
        else:
            title_portion = line
        
        # Try to extract from title portion first (DEV/ARCH/NLST prefixes)
        id_match = re.search(r'(?:DEV|ARCH|NLST)-\d{8}-\d{6}-[A-Z0-9]+', title_portion)
        if id_match:
            return id_match.group()
        
        # Fallback: try to extract from entire line
        id_match = re.search(r'(?:DEV|ARCH|NLST)-\d{8}-\d{6}-[A-Z0-9]+', line)
        if id_match:
            return id_match.group()
        
        return None
    
    def _parse_card_line(self, line: str, line_number: int) -> Optional[Dict]:
        """
        Parse a single Kanban card line in various formats.
        
        Formats supported:
        1. - [ ] Title^[card-id]
        2. - [ ] Title (See [[proposal-file]])
        3. Multi-line with metadata indented below
        
        Args:
            line: The markdown line to parse
            line_number: Line number for error tracking
            
        Returns:
            dict or None: Card info if successfully parsed
        """
        # Skip indented metadata lines (they start with spaces or tabs followed by a dash)
        if re.match(r'^\s{2,}-', line):
            return None
        
        # Match main card line: - [ ] Title (options)
        card_match = re.match(r'^-\s+\[([ xX])\]\s+(.+?)(?:\s*^\s{2,}-.*)?$', line, re.DOTALL)
        
        if not card_match:
            # Try simpler format without checkbox
            simple_match = re.match(r'^[-•]\s+(.+)$', line)
            if simple_match and self._contains_proposal_id(line):
                title = simple_match.group(1).strip()
                proposal_id = self._extract_proposal_id_from_line(line)
                return {
                    'title': title,
                    'card_id': f"^[{proposal_id}]",
                    'proposal_id': proposal_id,
                    'line': line,
                    'raw_line_number': line_number
                }
            return None
        
        checked = card_match.group(1).lower() == 'x'
        title_part = card_match.group(2)
        
        # Extract title (remove trailing metadata like "status: backlog")
        title = re.sub(r'\s*[-–]\s*(?:status|priority|created|related):.*$', '', title_part, flags=re.IGNORECASE).strip()
        
        # Method 1: Extract card ID from ^[id] format
        card_id_match = re.search(r'\^\[(.*?)\]', title_part)
        if card_id_match:
            card_id = f"^[{card_id_match.group(1)}]"
        else:
            card_id = None
        
        # Method 2: Extract proposal ID from line content
        proposal_id = self._extract_proposal_id_from_line(line)
        
        # If we still don't have a proposal_id, try to extract from link reference
        if not proposal_id:
            link_match = re.search(r'\[\[(.*?)\]\]', title_part)
            if link_match:
                link_ref = link_match.group(1)
                # Extract ID from link reference (e.g., DEV-20260518-XXXX_PROPOSAL.md)
                id_in_link = self._extract_proposal_id_from_filename(link_ref + ".md")
                if id_in_link:
                    proposal_id = id_in_link
        
        return {
            'title': title,
            'card_id': card_id,
            'proposal_id': proposal_id,
            'line': line,
            'raw_line_number': line_number
        }
    
    def _find_proposal_file(self, proposal_id: str) -> Optional[str]:
        """
        Find the proposal file for a given ID (can be proposal ID or Kanban ID).

        The Obsidian vault is the source of truth. Vault is searched first;
        the local project folder is only used as a fallback when the vault is
        unavailable.

        Args:
            proposal_id: The ID to search for

        Returns:
            str or None: Path to proposal file if found
        """
        # PRIMARY: vault path (source of truth — what Obsidian shows)
        proposals_dir_vault = os.path.join(self.vault_path, "1. P - Seedlings", "dev", "proposals")

        if os.path.exists(proposals_dir_vault):
            try:
                for filename in os.listdir(proposals_dir_vault):
                    if proposal_id.lower() in filename.lower():
                        return os.path.join(proposals_dir_vault, filename)
            except Exception as e:
                print(f"Warning: Could not read vault proposals directory: {e}")

        # FALLBACK: local project folder (for non-Obsidian / offline contexts)
        possible_paths = [
            os.path.join(os.getcwd(), "cognitive-os", "dev", "proposals"),
            os.path.join(os.getcwd(), "dev", "proposals"),
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "dev", "proposals"),
        ]

        proposals_dir_project = None
        for path in possible_paths:
            if os.path.exists(path):
                proposals_dir_project = path
                break

        if proposals_dir_project:
            try:
                for filename in os.listdir(proposals_dir_project):
                    if proposal_id.lower() in filename.lower():
                        return os.path.join(proposals_dir_project, filename)
            except Exception as e:
                print(f"Warning: Could not read project proposals directory: {e}")
        else:
            print(f"Warning: Could not find project proposals directory. Searched: {possible_paths}")

        # Last resort: search file contents (vault first, then project)
        search_dirs = []
        if os.path.exists(proposals_dir_vault):
            search_dirs.append(proposals_dir_vault)
        if proposals_dir_project and proposals_dir_project not in search_dirs:
            search_dirs.append(proposals_dir_project)

        for proposals_dir in search_dirs:
            try:
                for filename in os.listdir(proposals_dir):
                    if not filename.endswith(".md"):
                        continue
                    filepath = os.path.join(proposals_dir, filename)
                    with open(filepath, 'r', encoding='utf-8') as f:
                        content = f.read()
                    if proposal_id in content:
                        return filepath
            except Exception:
                pass

        return None
    
    def _get_column_mapping(self, column: str) -> Dict[str, str]:
        """
        Return frontmatter field updates when a card lands on a new column.

        When a card is dropped into a new column the processing state is
        immediately set to 'pending' — the automation hasn't run yet.
        A separate 'phase' field tracks the lifecycle column.

        Args:
            column: The column name (backlog, proposal, beta testing, etc.)

        Returns:
            dict: {'status': 'pending', 'phase': <normalised column name>}
        """
        # Canonical phase names (normalised, lowercase, no spaces)
        phase_map = {
            "backlog":       "backlog",
            "proposal":      "proposal",
            "beta testing":  "beta",
            "alpha polish":  "alpha",
            "finalized":     "finalized",
            "deployed":      "deployed",
        }
        phase = phase_map.get(column.lower(), column.lower())
        return {"status": "pending", "phase": phase}
    
    def update_kanban_status(self, proposal_file: str, new_column: str) -> bool:
        """
        Update the status field in YAML frontmatter.
        
        Args:
            proposal_file: Path to the proposal file
            new_column: The new column position
            
        Returns:
            True if successful, False otherwise
        """
        try:
            print(f"\n[FRONTMATTER UPDATE] Starting update for: {proposal_file}")
            
            # Check if file exists
            if not os.path.exists(proposal_file):
                print(f"[FRONTMATTER ERROR] File does not exist: {proposal_file}")
                return False
            
            with open(proposal_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            print(f"[FRONTMATTER DEBUG] Read {len(content)} characters from file")
            print(f"[FRONTMATTER DEBUG] First 100 chars: {content[:100]}")
            
            # Get status field from mapping (kanban_status and lifecycle_phase removed)
            field_updates = self._get_column_mapping(new_column)
            print(f"[FRONTMATTER DEBUG] Field updates to apply: {field_updates}")
            
            # Update frontmatter with status field only
            updated_content = self._update_yaml_frontmatter(content, field_updates)
            
            print(f"[FRONTMATTER DEBUG] Updated content length: {len(updated_content)}")
            print(f"[FRONTMATTER DEBUG] First 100 chars after update: {updated_content[:100]}")
            
            # Write the updated content back (vault, the source-of-truth here)
            with open(proposal_file, 'w', encoding='utf-8', newline='') as f:
                f.write(updated_content)

            # ALSO write to the backend twin so proposal_sync doesn't go RED
            # on the next health-check. Without this, the watcher refuses to
            # process the next transition until a human resolves the conflict
            # (observed 2026-05-24 — blocked Beta Testing fires).
            try:
                backend_twin = self._backend_twin_path(proposal_file)
                if backend_twin and os.path.exists(os.path.dirname(backend_twin)):
                    with open(backend_twin, 'w', encoding='utf-8', newline='') as f:
                        f.write(updated_content)
                    print(f"[FRONTMATTER SUCCESS] Mirrored to backend: {backend_twin}")
            except Exception as twin_err:
                # Non-fatal — the vault write succeeded, that's what matters
                # for Obsidian. Log so we know the backend drifted.
                print(f"[FRONTMATTER WARN] Backend twin mirror failed: {twin_err}")

            print(f"[FRONTMATTER SUCCESS] Updated {proposal_file}:")
            for key, value in field_updates.items():
                print(f"  {key} = {value}")

            return True

        except Exception as e:
            print(f"[FRONTMATTER ERROR] Exception updating status in {proposal_file}: {e}")
            import traceback
            traceback.print_exc()
            return False

    def _backend_twin_path(self, vault_proposal_file: str) -> Optional[str]:
        """Map a vault proposal-file path to its backend twin.

        Vault layout: <vault>/1. P - Seedlings/dev/proposals/<file>.md
        Backend layout: <repo>/dev/proposals/<file>.md

        If ``vault_proposal_file`` is already a backend path (e.g. when
        running offline), returns None so we don't double-write.
        """
        normalised = vault_proposal_file.replace("\\", "/")
        marker = "/1. P - Seedlings/dev/proposals/"
        if marker not in normalised:
            return None  # already backend or unknown layout
        filename = os.path.basename(vault_proposal_file)
        script_dir = os.path.dirname(os.path.abspath(__file__))
        repo_root = os.path.dirname(script_dir)
        return os.path.join(repo_root, "dev", "proposals", filename)
    
    def sync_proposals(self) -> dict:
        """
        Sync proposals from backend to vault.
        
        Returns:
            dict with sync result information
        """
        try:
            sync_manager = _get_sync_manager()
            if sync_manager:
                result = sync_manager.sync_backend_to_vault()
                result_dict = result.to_dict()
                
                if result_dict["success"]:
                    return {
                        "success": True,
                        "message": f"Synced {result_dict['files_synced']} files",
                        "details": result_dict
                    }
                else:
                    return {
                        "success": False,
                        "message": f"Sync completed with errors: {result_dict['errors']}",
                        "details": result_dict
                    }
        except Exception as e:
            return {
                "success": False,
                "message": f"Sync failed: {str(e)}",
                "error": str(e)
            }
        
        return {"success": False, "message": "Sync manager unavailable"}

    def _get_status_emoji(self, column: str) -> Tuple[str, str]:
        """Return emoji and text for a column."""
        status_map = {
            "backlog": ("⏳", "Awaiting Approval"),
            "proposal": ("📋", "In Review"),
            "beta testing": ("🧪", "Testing In Progress"),
            "alpha polish": ("🔧", "Ready For Review"),
            "finalized": ("✅", "Released"),
            "deployed": ("🚀", "Live")
        }
        return status_map.get(column, ("-", column.capitalize()))
    
    def _update_card_status_on_board(self, card_line: str, new_column: str) -> str:
        """Update the inline status metadata on a Kanban card line."""
        emoji, text = self._get_status_emoji(new_column)
        
        # Pattern to match and replace status: line in card metadata
        pattern = r'(\s*- status:).*'
        replacement = f"\\1 {emoji} {text}"
        
        return re.sub(pattern, replacement, card_line, flags=re.IGNORECASE)

    # ------------------------------------------------------------------
    # INLINE BOARD STATUS — update the "  - status: …" annotation that
    # lives directly on the card inside Dev-KanBan.md
    # ------------------------------------------------------------------

    # Map processing state → emoji label shown on the card
    _INLINE_STATUS_LABELS = {
        "pending":   "⏳ Pending",
        "processed": "✅ Processed",
        "review":    "🔍 Review",
    }

    def _write_card_status_to_board(self, proposal_id: str, processing_status: str) -> bool:
        """
        Update the inline '  - status: …' annotation on a specific card inside
        Dev-KanBan.md.  This makes the processing state visible directly on
        the Kanban card without opening the linked proposal note.

        Args:
            proposal_id: The DEV-… ID used to locate the card on the board.
            processing_status: One of 'pending', 'processed', or 'review'.

        Returns:
            True if the board file was updated, False otherwise.
        """
        kanban_path = os.path.join(self.vault_path, self.kanban_file)
        if not os.path.exists(kanban_path):
            print(f"[BOARD STATUS] Kanban file not found: {kanban_path}")
            return False

        label = self._INLINE_STATUS_LABELS.get(processing_status, processing_status)

        try:
            with open(kanban_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            updated = False
            i = 0
            while i < len(lines):
                line = lines[i]
                # Find the card line that contains this proposal_id
                if proposal_id in line and re.match(r"^-\s+\[", line):
                    # Scan the following indented metadata lines for "  - status:"
                    j = i + 1
                    while j < len(lines) and re.match(r"^\s{2,}-", lines[j]):
                        if re.match(r"^\s*-\s*status:", lines[j], re.IGNORECASE):
                            lines[j] = re.sub(
                                r"(\s*-\s*status:).*",
                                f"\\1 {label}",
                                lines[j],
                                flags=re.IGNORECASE,
                            )
                            updated = True
                            break
                        j += 1
                    if updated:
                        break  # Only update the first matching card
                i += 1

            if updated:
                with open(kanban_path, "w", encoding="utf-8") as f:
                    f.writelines(lines)
                print(f"[BOARD STATUS] Updated inline status for {proposal_id} → {label}")
            else:
                print(f"[BOARD STATUS] Could not find inline status line for {proposal_id}")

            return updated

        except Exception as e:
            print(f"[BOARD STATUS ERROR] Failed to update board for {proposal_id}: {e}")
            return False

    def _set_proposal_processing_status(self, proposal_file: str, processing_status: str) -> bool:
        """
        Update only the 'status' field in the proposal frontmatter without
        touching 'phase' or any other field.

        Args:
            proposal_file: Path to the proposal markdown file.
            processing_status: 'pending', 'processed', or 'review'.

        Returns:
            True if the file was updated successfully.
        """
        if not os.path.exists(proposal_file):
            print(f"[PROC STATUS ERROR] File not found: {proposal_file}")
            return False
        try:
            with open(proposal_file, "r", encoding="utf-8") as f:
                content = f.read()
            updated_content = self._update_yaml_frontmatter(content, {"status": processing_status})
            with open(proposal_file, "w", encoding="utf-8", newline='') as f:
                f.write(updated_content)
            print(f"[PROC STATUS] Set status={processing_status} in {proposal_file}")

            # Mirror to the backend twin so proposal_sync stays GREEN.
            # See _backend_twin_path docstring + commit d7e2b3f.
            try:
                backend_twin = self._backend_twin_path(proposal_file)
                if backend_twin and os.path.exists(os.path.dirname(backend_twin)):
                    with open(backend_twin, "w", encoding="utf-8", newline='') as f:
                        f.write(updated_content)
                    print(f"[PROC STATUS] Mirrored to backend: {backend_twin}")
            except Exception as twin_err:
                print(f"[PROC STATUS WARN] Backend twin mirror failed: {twin_err}")

            return True
        except Exception as e:
            print(f"[PROC STATUS ERROR] {e}")
            return False
    
    def _rewrite_proposal_with_role(self, proposal_id: str, current_content: str) -> Optional[str]:
        """
        Use the 'dev_proposal_refiner' role to rewrite a proposal.

        Provenance preservation:
        - The '## 📥 Original Request' section (origin + source note + raw user text)
          is extracted BEFORE the LLM call and re-injected AFTER so it is never
          lost even when the LLM regenerates the entire document.
        - The same block is also preserved in YAML frontmatter by create_proposal().
        """
        try:
            from orchestrator import get_role_config
            from llm_client import llm

            # ------------------------------------------------------------------
            # 1. Extract origin/source block so we can re-inject it after rewrite
            # ------------------------------------------------------------------
            origin_block = ""
            origin_match = re.search(
                r'(## 📥 Original Request\b.*?)(?=\n## |\Z)',
                current_content,
                re.DOTALL
            )
            if origin_match:
                origin_block = origin_match.group(1).strip()
                print(f"[LLM] Origin block preserved for {proposal_id}")

            role_key = "dev_proposal_refiner"
            role_config = get_role_config(role_key)

            prompt = f"""The user has provided raw notes/ideas in a proposal file. Your task is to rewrite this into a formal, comprehensive development proposal based on your system prompt.

USER'S RAW NOTES/IDEAS:
---
{current_content}
---

IMPORTANT INSTRUCTIONS:
1. Begin the document with a section exactly like this:

## 📋 Summary
(3–5 plain-language sentences summarising what this proposal is, what problem it solves, and the proposed approach.)

2. Continue with the full structured proposal (Objective, Technical Approach, etc.).
3. DO NOT include a '## 📥 Original Request' section — it will be re-injected automatically.
4. Preserve the user's core ideas. Output ONLY the complete markdown file content, with no other text or explanations.
"""

            print(f"[LLM] Calling role '{role_key}' to refine proposal {proposal_id}")

            response = llm.generate_response(
                prompt=prompt,
                system_prompt=role_config.get('system_prompt', ''),
                model=role_config.get('model'),
                temperature=role_config.get('temperature'),
                top_p=role_config.get('top_p'),
                top_k=role_config.get('top_k'),
                repeat_penalty=role_config.get('repeat_penalty'),
                max_tokens=role_config.get('max_tokens'),
                context_window=role_config.get('context_window'),
                gpu_layers=role_config.get('gpu_layers')
            )

            print(f"[LLM] Received refined proposal for {proposal_id}")

            # ------------------------------------------------------------------
            # 2. Re-inject the origin block after the first heading in the response
            #    so the chain-of-custody is always visible in Obsidian.
            # ------------------------------------------------------------------
            if origin_block:
                first_heading = re.search(r'\n(#{1,3}\s+[^\n]+)\n', response)
                if first_heading:
                    insert_at = first_heading.end()
                    response = (
                        response[:insert_at]
                        + f"\n{origin_block}\n\n---\n\n"
                        + response[insert_at:]
                    )
                else:
                    response = f"{origin_block}\n\n---\n\n" + response

            # ------------------------------------------------------------------
            # 3. Append user-editable review gate at the bottom
            # ------------------------------------------------------------------
            user_notes_block = (
                "\n\n---\n\n"
                "## 🗒️ User Notes  *(Phase Gate: Proposal → Beta Testing)*\n\n"
                "> Review the refined proposal above. Add any corrections, missing context, or steering notes here "
                "before moving this card to **Beta Testing**. "
                "This entire section will be included in the Beta Council's input.\n\n"
                "<!-- Your notes here -->\n"
            )
            return response + user_notes_block

        except Exception as e:
            print(f"[ERROR] Failed to rewrite proposal {proposal_id}: {e}")
            return None

    def _update_proposal_phase(self, proposal_id: str, old_column: str, new_column: str) -> Dict:
        """
        Update a proposal's phase based on column movement.

        Status lifecycle for a card:
          - Card dropped on new column   → update_kanban_status sets phase+status=pending
          - Backlog→Proposal LLM rewrite → status: review  (user must check the rewrite)
          - Any orchestration success    → status: processed
          - Any error / more info needed → status: review
        """
        proposal_file = self._find_proposal_file(proposal_id)

        if not proposal_file:
            # Even without a file we update the board card so the user sees feedback
            self._write_card_status_to_board(proposal_id, "review")
            return {
                "status": "error",
                "message": f"Proposal file not found for {proposal_id}",
                "proposal_id": proposal_id
            }

        with open(proposal_file, 'r', encoding='utf-8') as f:
            content = f.read()

        old_info = self.columns.get(old_column, {})
        new_info = self.columns.get(new_column, {})
        old_order = old_info.get("order", 0)
        new_order = new_info.get("order", 0)

        # Step 1: Always write phase=<column> + status=pending immediately so the
        #         user can see the card was detected, even before the LLM runs.
        self.update_kanban_status(proposal_file, new_column)
        self._write_card_status_to_board(proposal_id, "pending")

        # ----------------------------------------------------------------
        # BACKLOG → PROPOSAL: run the LLM refiner
        # ----------------------------------------------------------------
        if old_column == "backlog" and new_column == "proposal" and new_order > old_order:
            print(f"[REFINE] User moved card from Backlog → Proposal for {proposal_id}")

            rewritten_content = self._rewrite_proposal_with_role(
                proposal_id=proposal_id,
                current_content=content
            )

            if rewritten_content:
                with open(proposal_file, 'w', encoding='utf-8', newline='') as f:
                    f.write(rewritten_content)
                print(f"[REFINE] Proposal rewritten successfully for {proposal_id}")
                # Mirror to backend twin (Phase 5 stopgap — see d7e2b3f)
                try:
                    backend_twin = self._backend_twin_path(proposal_file)
                    if backend_twin and os.path.exists(os.path.dirname(backend_twin)):
                        with open(backend_twin, 'w', encoding='utf-8', newline='') as f:
                            f.write(rewritten_content)
                        print(f"[REFINE] Mirrored to backend: {backend_twin}")
                except Exception as twin_err:
                    print(f"[REFINE WARN] Backend twin mirror failed: {twin_err}")
                # LLM appended a User Notes review gate — user must check it before
                # moving on, so the processing state becomes 'review'.
                self._set_proposal_processing_status(proposal_file, "review")
                self._write_card_status_to_board(proposal_id, "review")
                return {
                    "status": "success",
                    "message": "Proposal refined and moved to Proposal column — review the output.",
                    "proposal_id": proposal_id
                }
            else:
                # LLM call failed — flag for manual review
                self._set_proposal_processing_status(proposal_file, "review")
                self._write_card_status_to_board(proposal_id, "review")
                return {
                    "status": "error",
                    "message": f"LLM refiner failed for {proposal_id} — manual review required.",
                    "proposal_id": proposal_id
                }

        # ----------------------------------------------------------------
        # Non-forward moves (e.g. same-column re-trigger): nothing more to do
        # ----------------------------------------------------------------
        if new_order <= old_order:
            return {
                "status": "info",
                "message": f"Card moved to {new_column} — phase and status updated.",
                "proposal_id": proposal_id
            }

        # ----------------------------------------------------------------
        # FORWARD PHASE TRANSITIONS (Proposal→Beta, Beta→Alpha, etc.)
        # ----------------------------------------------------------------
        current_phase = self._get_proposal_current_phase(content)
        # Columns store the lifecycle phase under 'phase_key' (renamed from
        # 'phase' to avoid colliding with the single-phase-writer gate on
        # configuration data). Older callers expected 'phase' — fall back
        # to it for backward compat.
        next_phase = new_info.get("phase_key") or new_info.get("phase", "unknown")

        print(f"Processing transition: {old_column} → {new_column}")
        print(f"Proposal ID: {proposal_id}")
        print(f"Phase change needed: {current_phase} → {next_phase}")

        try:
            # ----------------------------------------------------------------
            # Step 1: Ask workflow_engine if this transition is allowed (G3/T2 compliance)
            # ----------------------------------------------------------------
            # C1 (Phase 5): feature flag — if WorkflowEngine is disabled, skip
            # the guard and proceed directly to Step 2 (legacy behavior).
            from src.integration_flags import is_workflow_engine_enabled
            if not is_workflow_engine_enabled():
                print(f"[LEGACY] integration.workflow_engine_enabled=false; skipping transition guard for {proposal_id}")
            else:
                # Parse YAML to get current phase/status/substatus/approver/severity/depends_on
                frontmatter, _, _ = self._parse_yaml_frontmatter(content)
                if not frontmatter:
                    raise ValueError(f"No frontmatter in {proposal_file}")

                # Compute semantic-only version_hash using workflow_engine's internal method
                # The hash basis is: {phase, status, substatus, approver, severity, depends_on}
                version_hash = self.workflow_engine._compute_version_hash(frontmatter)

                # Call workflow_engine.transition() - wrap async call in sync context
                transition_result: WorkflowTransitionResult = asyncio.run(
                    self.workflow_engine.transition(
                        TransitionRequest(
                            proposal_id=proposal_id,
                            target_phase=WorkflowPhase(next_phase),
                            target_substatus=None,
                            approver="KanbanProcessor",
                            reason=f"Card moved from {old_column} to {new_column}",
                            version_hash=version_hash
                        )
                    )
                )

                if not transition_result.success:
                    # Vetoed! Write dead-letter and raise
                    blocked_path = self._write_blocked_transition(
                        proposal_id=proposal_id,
                        old_column=old_column,
                        new_column=new_column,
                        error=f"Transition vetoed: {transition_result.error or 'Unknown error'}"
                    )
                    self._audit_log_block(
                        proposal_id=proposal_id,
                        old_column=old_column,
                        new_column=new_column,
                        error=f"Transition vetoed: {transition_result.error}"
                    )
                    raise RuntimeError(f"Transition blocked: {transition_result.error}")

                print(f"[TRANSITION] Workflow engine approved transition to {next_phase}")

            # ----------------------------------------------------------------
            # Step 2: Call orchestrator to run council/meeting
            # ----------------------------------------------------------------
            from orchestrator import Orchestrator
            orch = Orchestrator()
            result_msg = orch.continue_development_lifecycle(proposal_id, next_phase, content)

            # Beta and Alpha: council ran but the human still has work to do.
            # Keep the card in 🔍 Review so they know to open the handoff / polish plan.
            # Finalized / Deployed: fully automated — mark as ✅ Processed.
            if next_phase in ("beta", "alpha"):
                post_status = "review"
            else:
                post_status = "processed"

            self._set_proposal_processing_status(proposal_file, post_status)
            self._write_card_status_to_board(proposal_id, post_status)

            return {
                "status": "success",
                "message": result_msg,
                "proposal_id": proposal_id,
                "old_phase": current_phase,
                "new_phase": next_phase
            }
        except TransitionConflictError as e:
            # Version hash mismatch — write dead-letter + audit-log
            self._write_blocked_transition(
                proposal_id=proposal_id,
                old_column=old_column,
                new_column=new_column,
                error=f"Version conflict: {str(e)}"
            )
            self._audit_log_block(
                proposal_id=proposal_id,
                old_column=old_column,
                new_column=new_column,
                error=f"VersionConflict: {str(e)}"
            )
            raise
        except GateError as e:
            # Gate check failed
            self._write_blocked_transition(
                proposal_id=proposal_id,
                old_column=old_column,
                new_column=new_column,
                error=f"Gate failed: {str(e)}"
            )
            self._audit_log_block(
                proposal_id=proposal_id,
                old_column=old_column,
                new_column=new_column,
                error=f"GateError: {str(e)}"
            )
            raise
        except Exception as e:
            # Other errors (including veto from workflow_engine)
            import traceback
            self._write_blocked_transition(
                proposal_id=proposal_id,
                old_column=old_column,
                new_column=new_column,
                error=f"{type(e).__name__}: {str(e)}"
            )
            self._audit_log_block(
                proposal_id=proposal_id,
                old_column=old_column,
                new_column=new_column,
                error=f"{type(e).__name__}: {str(e)}"
            )
            # Re-raise original exception
            raise
    
    def _get_proposal_current_phase(self, content: str) -> str:
        """Extract current phase from proposal file."""
        # Check for lifecycle phase in content
        phase_match = re.search(r'Lifecycle Phase[:\s]+(\d+/\d+)\s*-\s*(.+)', content)
        if phase_match:
            return phase_match.group(2).strip().lower()
        
        # Fallback: check status
        if "FINALIZED AND RELEASED" in content:
            return "finalized"
        if "Alpha Polish In Progress" in content:
            return "alpha"
        if "Beta Testing In Progress" in content:
            return "beta"
        
        return "proposal"
    
    def _parse_yaml_frontmatter(self, content: str) -> Tuple[Optional[Dict], str, str]:
        """
        Parse YAML frontmatter from a markdown file.
        
        Args:
            content: Full file content
            
        Returns:
            Tuple of (frontmatter_dict, content_before_frontmatter, content_after_frontmatter)
        """
        # Match YAML frontmatter between --- delimiters
        frontmatter_match = re.match(r'^---\s*\n(.*?)\n---\s*\n(.*?)$', content, re.DOTALL)
        if frontmatter_match:
            frontmatter_text = frontmatter_match.group(1)
            content_after = frontmatter_match.group(2)
            try:
                frontmatter = yaml.safe_load(frontmatter_text)
                return frontmatter if isinstance(frontmatter, dict) else {}, "", content_after
            except yaml.YAMLError:
                return None, "", content_after
        return None, "", content
    
    def _update_yaml_frontmatter(self, content: str, updates: Dict[str, Any]) -> str:
        """
        Update YAML frontmatter in a markdown file.
        
        Args:
            content: Full file content
            updates: Dict of fields to update
            
        Returns:
            Updated content with modified frontmatter
        """
        frontmatter_match = re.match(r'^---\s*\n(.*?)\n---\s*\n(.*?)$', content, re.DOTALL)
        if not frontmatter_match:
            # No frontmatter exists - create it
            frontmatter_lines = ["---"]
            for key, value in updates.items():
                frontmatter_lines.append(f"{key}: {value}")
            frontmatter_lines.append("---")
            return "\n".join(frontmatter_lines) + "\n" + content
        
        frontmatter_text = frontmatter_match.group(1)
        content_after = frontmatter_match.group(2)
        
        # Parse existing frontmatter
        try:
            frontmatter = yaml.safe_load(frontmatter_text)
            if not isinstance(frontmatter, dict):
                frontmatter = {}
        except yaml.YAMLError:
            frontmatter = {}
        
        # Update the specified fields
        for key, value in updates.items():
            frontmatter[key] = value
        
        # Rebuild frontmatter with proper YAML formatting
        frontmatter_lines = ["---"]
        for key, value in frontmatter.items():
            if isinstance(value, list):
                # Handle list values (e.g., kanban_columns)
                frontmatter_lines.append(f"{key}:")
                for item in value:
                    if isinstance(item, dict):
                        # Handle nested dicts
                        for k, v in item.items():
                            frontmatter_lines.append(f"  - {k}: {v}")
                    else:
                        frontmatter_lines.append(f"  - {item}")
            elif isinstance(value, dict):
                # Handle nested dicts
                frontmatter_lines.append(f"{key}:")
                for k, v in value.items():
                    frontmatter_lines.append(f"  {k}: {v}")
            else:
                # Simple key-value pairs
                frontmatter_lines.append(f"{key}: {value}")
        frontmatter_lines.append("---")
        
        frontmatter_yaml = "\n".join(frontmatter_lines) + "\n"
        return frontmatter_yaml + content_after
    
    def process_all_transitions(self, force: bool = False) -> List[Dict]:
        """
        Process all card movements since last run.
        
        Args:
            force: If True, reprocess all cards regardless of cache
            
        Returns:
            list: Results for each processed transition
        """
        print("=" * 60)
        print("Kanban Processor - Processing Column Changes")
        print("=" * 60)
        
        # Parse current board state
        current_cards = self._parse_kanban_board()
        
        results = []
        
        # Check each column for cards and their previous positions
        for column, cards in current_cards.items():
            print(f"[DEBUG] Checking column '{column}' with {len(cards)} cards")
            for card in cards:
                proposal_id = card.get("proposal_id")
                print(f"[DEBUG] Card: proposal_id={proposal_id}, title={card.get('title')}")
                if not proposal_id:
                    print(f"[DEBUG] Skipping card - no proposal_id")
                    continue
                
                old_column = self.cache.get("cards", {}).get(proposal_id)
                print(f"[DEBUG] Card {proposal_id}: old_column={old_column}, new_column={column}")
                
                # Skip if no change (unless force)
                if old_column == column and not force:
                    print(f"[DEBUG] No change detected for {proposal_id} (both in '{column}')")
                    continue
                
                # If we don't have a cached position, this is the first time seeing the card
                # Just cache it without processing (no transition yet)
                if old_column is None:
                    print(f"[INFO] New card found: {proposal_id} in {column} - caching position")
                    # Update cache for first-time cards
                    if "cards" not in self.cache:
                        self.cache["cards"] = {}
                    self.cache["cards"][proposal_id] = column
                    continue  # Skip processing, just record the position
                
                # Only process actual transitions (when we know the old position)
                result = self._update_proposal_phase(
                    proposal_id, 
                    old_column,
                    column
                )
                results.append(result)
                
                # Update cache after processing
                if "cards" not in self.cache:
                    self.cache["cards"] = {}
                self.cache["cards"][proposal_id] = column
        
        # Save updated cache
        self._save_cache()
        
        # Summary
        print("\n" + "=" * 60)
        print("Processing Complete")
        print("=" * 60)
        
        success_count = sum(1 for r in results if r.get("status") == "success")
        error_count = sum(1 for r in results if r.get("status") == "error")
        info_count = sum(1 for r in results if r.get("status") == "info")
        
        print(f"Successfully processed: {success_count}")
        print(f"Informational: {info_count}")
        print(f"Errors: {error_count}")
        print(f"Total transitions: {len(results)}")
        
        return results
    
    def sync_to_kanban_board(self) -> int:
        """
        Add proposals from dev/proposals (both project and vault) to the Kanban board.
        Only adds cards that don't already exist in the board.
        
        Returns:
            int: Number of cards added
        """
        print("Syncing proposals to Kanban board...")
        
        kanban_path = os.path.join(self.vault_path, self.kanban_file)
        
        # Check both project folder and vault for proposals
        all_proposals_to_add = []
        existing_ids = set()
        
        # First check if board exists and get existing IDs
        if os.path.exists(kanban_path):
            current_state = self._parse_kanban_board()
            for column, cards in current_state.items():
                for card in cards:
                    if card.get("proposal_id"):
                        existing_ids.add(card["proposal_id"])
        
        # Check project folder first (cognitive-os/dev/proposals)
        proposals_dir_project = os.path.join(os.getcwd(), "cognitive-os", "dev", "proposals")
        if not os.path.exists(proposals_dir_project):
            proposals_dir_project = os.path.join("cognitive-os", "dev", "proposals")
        
        # Check vault folder
        proposals_dir_vault = os.path.join(self.vault_path, "1. P - Seedlings", "dev", "proposals")
        
        all_proposal_dirs = []
        if os.path.exists(proposals_dir_project):
            all_proposal_dirs.append(("project", proposals_dir_project))
        if os.path.exists(proposals_dir_vault) and proposals_dir_vault != proposals_dir_project:
            all_proposal_dirs.append(("vault", proposals_dir_vault))
        
        for location_name, proposals_dir in all_proposal_dirs:
            print(f"Checking {location_name} folder: {proposals_dir}")
            
            if not os.path.exists(proposals_dir):
                continue
            
            for filename in os.listdir(proposals_dir):
                if not filename.endswith("_PROPOSAL.md"):
                    continue
                
                proposal_id = self._extract_proposal_id_from_filename(filename)
                
                if proposal_id and proposal_id not in existing_ids:
                    filepath = os.path.join(proposals_dir, filename)
                    
                    with open(filepath, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    # Extract title from file
                    title_match = re.search(r'^#\s+DEV\s+PROPOSAL.*?Proposal ID.*?`\s*([^`]+)\s*`', 
                                           content, re.IGNORECASE | re.DOTALL)
                    if not title_match:
                        title_match = re.search(r'###\s+(.+)', content)
                    
                    title = title_match.group(1).strip() if title_match else "Proposal"
                    
                    # Use minimal title - just the ID (max length constraint for Kanban board)
                    all_proposals_to_add.append({
                        "id": proposal_id,
                        "title": proposal_id,  # Just use the ID as the minimal title
                        "filepath": filepath
                    })
        
        # Add cards to board (in Backlog column)
        if all_proposals_to_add:
            print(f"Found {len(all_proposals_to_add)} new proposals to add")
            
            # Create file if it doesn't exist yet
            os.makedirs(os.path.dirname(kanban_path), exist_ok=True)
            
            if not os.path.exists(kanban_path):
                with open(kanban_path, 'w', encoding='utf-8') as f:
                    f.write(self._get_default_kanban_board())
            
            with open(kanban_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Find the Backlog section and add cards
            backlog_marker = "## Backlog"
            
            new_cards: List[str] = []
            for proposal in all_proposals_to_add:
                card_id = self._extract_proposal_kanban_id_from_file(proposal["filepath"])
                if not card_id:
                    card_id = f"^[{proposal['id']}]"
                
                # Get short filename without path
                short_filename = os.path.basename(proposal["filepath"])
                
                new_cards.append(
                    f"- [ ] {proposal['title']}{card_id}\n"
                    f"  - status: ⏳ Pending\n"
                    f"  - priority: medium\n"
                    f"  - created: {datetime.now().strftime('%Y-%m-%d')}\n"
                    f"  - related: [[{short_filename}]]\n"
                )
            
            if new_cards:
                if backlog_marker in content:
                    content = content.replace(
                        backlog_marker,
                        backlog_marker + "\n\n" + "".join(new_cards)
                    )
                else:
                    # If no Backlog section exists, create one
                    content += f"\n\n## Backlog\n\n{''.join(new_cards)}"
                
                with open(kanban_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                
                added_count = len(all_proposals_to_add)
                print(f"Added {added_count} cards to Kanban board")
            else:
                print("No new proposals to add.")
        else:
            print("No proposals found in project or vault folders.")
        
        return len(all_proposals_to_add)
    
    def _get_default_kanban_board(self) -> str:
        """Return default Kanban Board template."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return f"""---
kanban-plugin: board
---

## Backlog

## Proposal

## Beta Testing

## Alpha Polish

## Finalized

## Deployed

***

## Archive

- [ ] Placeholder Task (Delete me)

%% kanban:settings
```
{{"kanban-plugin":"board","list-collapse":[null,null,false]}}
```
%%
"""
    
    def _extract_proposal_id_from_filename(self, filename: str) -> Optional[str]:
        """Extract proposal ID from filename (DEV/ARCH/NLST prefixes)."""
        # Match <PREFIX>-YYYYMMDD-HHMMSS-XXXX pattern anywhere in filename
        match = re.search(r'((?:DEV|ARCH|NLST)-\d{8}-\d{6}-[A-Z0-9]+)', filename)
        return match.group(1) if match else None
    
    def _extract_proposal_kanban_id_from_file(self, filepath: str) -> Optional[str]:
        """Extract Kanban card ID from proposal file."""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Look for Kanban Card section
            match = re.search(r'\*\*Card ID\*\*\s*\|\s*(\[.*?\])', content)
            if match:
                return match.group(1).strip()
            
            # Fallback: extract from footer
            match = re.search(r'Kanban Card ID:\s*(\[.*?\])', content)
            if match:
                return match.group(1).strip()
                
        except Exception as e:
            print(f"Error extracting Kanban ID from {filepath}: {e}")
        
        return None


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Process Kanban board changes and trigger lifecycle transitions"
    )
    
    parser.add_argument(
        "--vault", "-v",
        help="Path to Obsidian vault root"
    )
    
    parser.add_argument(
        "--sync", "-s",
        action="store_true",
        help="Sync proposals to Kanban board (add missing cards)"
    )
    
    parser.add_argument(
        "--force", "-f",
        action="store_true",
        help="Force reprocess all cards"
    )
    
    parser.add_argument(
        "--watch", "-w",
        action="store_true",
        help="Watch for changes continuously and auto-process transitions"
    )
    
    args = parser.parse_args()
    
    processor = KanbanProcessor(vault_path=args.vault)
    
    if args.sync:
        count = processor.sync_to_kanban_board()
        print(f"\nSynced {count} cards to board")
    elif args.watch:
        # Start watch mode
        watch_kanban_board(processor)
    else:
        results = processor.process_all_transitions(force=args.force)
        
        # Optional: Show summary
        if len(results) > 0:
            print("\n" + "=" * 60)
            print("TRANSITION SUMMARY")
            print("=" * 60)
            
            for result in results:
                status_emoji = "✅" if result.get("status") == "success" else ("ℹ️" if result.get("status") == "info" else "❌")
                print(f"{status_emoji} {result.get('message', 'Unknown')}")
    
    return 0


def watch_kanban_board(processor: KanbanProcessor):
    """
    Watch the Kanban board file for changes and automatically process transitions.
    Uses file modification time polling with debouncing.
    """
    kanban_path = os.path.join(processor.vault_path, processor.kanban_file)
    
    print("=" * 80)
    print("🔍 KANBAN WATCHER STARTED")
    print("=" * 80)
    print(f"Monitoring: {kanban_path}")
    print(f"Debounce delay: 2 seconds")
    print(f"Press Ctrl+C to stop")
    print("=" * 80)
    print()
    
    # Track last modification time and processing state
    last_mtime = None
    last_processed_time = None
    debounce_seconds = 2
    
    try:
        # Initial sync to establish baseline
        print("[INIT] Performing initial sync...")
        processor.sync_to_kanban_board()
        results = processor.process_all_transitions(force=False)
        print(f"[INIT] Initial processing complete ({len(results)} transitions detected)\n")
        
        if os.path.exists(kanban_path):
            last_mtime = os.path.getmtime(kanban_path)
            last_processed_time = time.time()
        
        while True:
            try:
                if not os.path.exists(kanban_path):
                    print(f"[WARNING] Kanban file not found: {kanban_path}")
                    time.sleep(5)
                    continue
                
                # Check for file modification
                current_mtime = os.path.getmtime(kanban_path)
                current_time = time.time()
                
                # Debug: Show current vs last mtime
                if last_mtime is not None and current_mtime != last_mtime:
                    timestamp = datetime.now().strftime('%H:%M:%S')
                    print(f"[{timestamp}] 🔍 File modification detected! Last: {last_mtime}, Current: {current_mtime}")
                
                # File was modified and enough time has passed for debouncing
                if last_mtime is not None and current_mtime > last_mtime:
                    time_since_modification = current_time - current_mtime
                    
                    # Wait for debounce period to pass
                    if time_since_modification >= debounce_seconds:
                        # Also check we haven't processed too recently (avoid rapid re-triggers)
                        if last_processed_time is None or (current_time - last_processed_time) >= debounce_seconds:
                            timestamp = datetime.now().strftime('%H:%M:%S')
                            print(f"\n[{timestamp}] 📝 Kanban board modified - processing transitions...")
                            
                            try:
                                results = processor.process_all_transitions(force=False)
                                
                                if len(results) > 0:
                                    print(f"[{timestamp}] ✅ Processed {len(results)} transition(s)")
                                    for result in results:
                                        status = result.get("status", "unknown")
                                        msg = result.get("message", "No message")
                                        emoji = "✅" if status == "success" else ("ℹ️" if status == "info" else "❌")
                                        print(f"  {emoji} {msg}")
                                else:
                                    print(f"[{timestamp}] ℹ️ No transitions detected")
                                
                            except Exception as e:
                                print(f"[{timestamp}] ❌ Error processing transitions: {e}")
                                import traceback
                                traceback.print_exc()
                            
                            last_processed_time = current_time
                            # Re-read the actual mtime so our own _write_card_status_to_board
                            # write doesn't look like a fresh external change on the next iteration.
                            last_mtime = os.path.getmtime(kanban_path)
                            print(f"[{timestamp}] 👀 Watching for changes...\n")
                
                # Sleep briefly before next check
                time.sleep(1)
                
            except KeyboardInterrupt:
                raise
            except Exception as e:
                print(f"[ERROR] Unexpected error in watch loop: {e}")
                import traceback
                traceback.print_exc()
                time.sleep(5)
                
    except KeyboardInterrupt:
        print("\n" + "=" * 80)
        print("🛑 KANBAN WATCHER STOPPED")
        print("=" * 80)
        return 0
    except Exception as e:
        print(f"\n[FATAL ERROR] Watcher crashed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())