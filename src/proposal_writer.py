"""
Proposal Writer Module - Handles proposal CRUD operations.

Extracted from dev_route.py to enforce Single Responsibility Principle.
"""

import os
import glob
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from src.paths import (
    VAULT_ROOT,
    PROPOSALS_DIR,
    HANDOFFS_DIR,
    RELEASES_DIR,
    TEMPLATES_DIR,
    KANBAN_FILE,
)

# Governance Foundation imports
from src.workflow_models import ValidatedProposal, Severity, WorkflowPhase
from src.schema_validator import validate_proposal_yaml, SchemaValidationError
from src.handoff_vault import HandoffVault
from src.approval_logger import ApprovalLogger
from src.governance_unit_of_work import GovernanceUnitOfWork
from src.integration_flags import get_integration_flags, is_governance_uow_enabled


class ProposalWriter:
    """
    Handles proposal lifecycle operations: creation, Kanban updates, sync.
    
    This module extracts proposal CRUD from DevRouteManager to enforce SRP.
    """

    def __init__(self):
        """Initialize the proposal writer with path constants."""
        self.proposals_dir = str(PROPOSALS_DIR)
        self.releases_dir = str(RELEASES_DIR)
        self.vault_proposals_dir = str(VAULT_ROOT / "1. P - Seedlings" / "dev" / "proposals")
        self.vault_releases_dir = str(VAULT_ROOT / "1. P - Seedlings" / "dev" / "releases")
        
        # Create directories
        os.makedirs(self.proposals_dir, exist_ok=True)
        os.makedirs(self.releases_dir, exist_ok=True)
        os.makedirs(self.vault_proposals_dir, exist_ok=True)
        os.makedirs(self.vault_releases_dir, exist_ok=True)

    def create_proposal(
        self,
        user_input: str,
        origin: str = "unknown",
        needs_approval: bool = True,
        llm_proposal_data: dict = None,
        source_file_path: str = None
    ) -> Dict:
        """
        Create a new development proposal using the lean template.

        Args:
            user_input: The proposal description
            origin: Where the proposal came from ("telegram", "obsidian", etc.)
            needs_approval: Whether user approval is required (default True)
            llm_proposal_data: Optional dict with LLM-generated details (ignored here)
            source_file_path: Optional path to the originating note/file

        Returns:
            dict with proposal_id, filepath, status, and approval_info
        """
        from src.dev_route import prefix_for_origin, generate_kanban_card_id

        # Origin determines the prefix (DEV / ARCH / NLST)
        prefix = prefix_for_origin(origin)
        proposal_id = f"{prefix}-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8].upper()}"
        kanban_card_id = generate_kanban_card_id(prefix)

        # Derive a clean Obsidian wikilink name from the source path
        source_note = (
            os.path.splitext(os.path.basename(source_file_path))[0]
            if source_file_path else None
        )

        # Load template from Obsidian vault (source of truth for template)
        vault_template_path = str(
            VAULT_ROOT / "1. P - Seedlings" / "dev" / "templates" / "proposal-template.md"
        )

        if not os.path.exists(vault_template_path):
            raise FileNotFoundError(f"Proposal template not found at {vault_template_path}")

        with open(vault_template_path, 'r', encoding='utf-8') as f:
            template = f.read()

        # Replace template placeholders.
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        content = template
        # New neutral placeholders
        content = content.replace('<PROPOSAL_ID>', proposal_id)
        content = content.replace('<CARD_ID>', kanban_card_id)
        content = content.replace('<PREFIX>', prefix)
        content = content.replace('<ORIGIN>', origin)
        # Legacy placeholders (any vault template still on the old shape)
        content = content.replace('DEV-YYYYMMDD-HHMMSS-XXXX', proposal_id)
        content = content.replace('^[DEV-YYYYMMDDHHMMSS-XXXX]', kanban_card_id)
        content = content.replace('DEV PROPOSAL', f'{prefix} PROPOSAL')
        # Shared placeholders (date / origin / body)
        content = content.replace('YYYY-MM-DD HH:MM:SS', timestamp)
        content = content.replace('[Telegram/Obsidian/Direct/Systems-Architect/Analyst]', origin)
        content = content.replace('[Telegram/Obsidian/Direct]', origin)
        content = content.replace('[User\'s original request/description goes here]', user_input)
        content = content.replace('[origin]', origin)

        # ------------------------------------------------------------------
        # Inject source provenance into YAML frontmatter so it survives
        # LLM rewrites (the rewriter is instructed to preserve this block).
        # ------------------------------------------------------------------
        fm_close = content.find('\n---\n', 3)  # skip opening ---
        if fm_close > 0:
            fm_extra = (
                f"\noriginal_request: \"{user_input[:300].replace(chr(34), chr(39))}\""
                f"\norigin: \"{origin}\""
            )
            if source_note:
                fm_extra += f"\nsource_note: \"[[{source_note}]]\""
            content = content[:fm_close] + fm_extra + content[fm_close:]

        # ------------------------------------------------------------------
        # Add a visible "📥 Original Request" section near the top of the
        # body so the chain-of-custody is readable in Obsidian.
        # ------------------------------------------------------------------
        source_section_lines = [
            "",
            "## 📥 Original Request",
            "",
            f"> **Origin**: {origin}",
        ]
        if source_note:
            source_section_lines.append(f"> **Source note**: [[{source_note}]]")
        source_section_lines += [
            "",
            user_input,
            "",
            "---",
            "",
        ]
        source_section = "\n".join(source_section_lines)

        # Insert after the first top-level heading (# ...) in the body
        first_h1 = re.search(r'\n(#\s+[^\n]+)\n', content)
        if first_h1:
            insert_at = first_h1.end()
            content = content[:insert_at] + source_section + content[insert_at:]
        else:
            # Fallback: prepend after frontmatter closing ---
            body_start = content.find('\n---\n', 3)
            if body_start > 0:
                content = content[:body_start + 5] + source_section + content[body_start + 5:]

        # Use GovernanceUnitOfWork for atomic multi-file writes if enabled
        flags = get_integration_flags()
        
        if flags['governance_uow_enabled']:
            with GovernanceUnitOfWork() as uow:
                # Stage proposal file (backend directory)
                filename = f"{self.proposals_dir}/{proposal_id}_PROPOSAL.md"
                uow.stage_file(Path(filename), content)

                # Stage vault copy (Obsidian sync directory)
                vault_filename = filename.replace(self.proposals_dir, self.vault_proposals_dir)
                uow.stage_file(Path(vault_filename), content)
        else:
            # Legacy fallback: direct file writes
            print("[WARNING] GovernanceUnitOfWork is disabled - using legacy direct file writes")
            filename = f"{self.proposals_dir}/{proposal_id}_PROPOSAL.md"
            Path(filename).write_text(content, encoding='utf-8')

            vault_filename = filename.replace(self.proposals_dir, self.vault_proposals_dir)
            Path(vault_filename).parent.mkdir(parents=True, exist_ok=True)
            Path(vault_filename).write_text(content, encoding='utf-8')

        # Extract a human-readable title for the Kanban card metadata
        card_title = self._extract_card_title(user_input)

        # Auto-add card to Kanban Board in vault (OUTSIDE UoW per A4 design)
        self._add_card_to_kanban(proposal_id, card_title, kanban_card_id, source_note=source_note)

        proposal_data = {
            "proposal_id": proposal_id,
            "kanban_card_id": kanban_card_id,
            "filepath": filename,
            "vault_filepath": vault_filename,
            "status": "pending_approval",
            "created_at": timestamp,
            "source_note": source_note,
        }

        return proposal_data

    def _extract_card_title(self, user_input: str) -> str:
        """Extract a short human-readable title from a proposal's user_input.

        Priority order:
        1. ``title:`` key inside a YAML front-matter block in user_input
        2. First non-empty, non-YAML line of text
        3. Empty string (caller falls back to showing just the DEV ID)
        """
        # 1. YAML title field (handles "title: \"OLM_R_boardroom_proposal_for_file_system\"")
        yaml_title_match = re.search(r'title:\s*["\']?([^"\'\n]+)["\']?', user_input)
        if yaml_title_match:
            raw = yaml_title_match.group(1).strip()
            # Strip common channel prefixes: TG_R_, OLM_R_, DEV_R_, etc.
            raw = re.sub(r'^[A-Z]+_R_', '', raw)
            # Replace underscores/dashes with spaces, collapse whitespace
            raw = re.sub(r'[_\-]+', ' ', raw).strip()
            if raw:
                return raw[:80]
        # 2. First meaningful line of free text
        for line in user_input.splitlines():
            line = line.strip()
            if (line
                    and not line.startswith('---')
                    and not line.startswith('#')
                    and not line.startswith('```')
                    and ':' not in line[:25]):
                return line[:80]
        return ""

    def _add_card_to_kanban(
        self,
        proposal_id: str,
        title: str,
        card_id: str,
        source_note: str = None
    ) -> bool:
        """
        Add a new proposal card to the Kanban Board.md file.

        Args:
            proposal_id: The ID of the proposal
            title: Short title for the card
            card_id: The Kanban card ID
            source_note: Optional Obsidian note name that originated this proposal

        Returns:
            True if successful, False otherwise
        """
        try:
            # Build path to Kanban board in vault safely by going up two directories
            seedlings_dir = VAULT_ROOT / "1. P - Seedlings"
            kanban_path = str(seedlings_dir / "Dev-KanBan.md")

            # Check if file exists, create if not
            if not os.path.exists(kanban_path):
                os.makedirs(os.path.dirname(kanban_path), exist_ok=True)
                with open(kanban_path, 'w', encoding='utf-8') as f:
                    f.write(self._get_kanban_template())

            # Read current board content
            with open(kanban_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # Check if card already exists
            if card_id in content:
                return True

            current_hour = datetime.now().strftime('%H:%M')

            # Build metadata lines — title first, then standard fields
            meta_lines = ""
            if title and title != proposal_id:
                meta_lines += f"  - title: {title}\n"
            meta_lines += (
                f"  - status: backlog\n"
                f"  - priority: medium\n"
                f"  - created: {datetime.now().strftime('%Y-%m-%d')} at {current_hour}\n"
                f"  - related: [[{proposal_id}_PROPOSAL]]\n"
            )
            if source_note:
                meta_lines += f"  - source: [[{source_note}]]\n"

            # Always use the DEV ID on the card title line so ID-based lookup keeps working
            card_entry = f"\n- [ ] {proposal_id}{card_id}\n{meta_lines}"

            # Find Backlog section and add card
            backlog_marker = "## Backlog"
            if backlog_marker in content:
                content = content.replace(backlog_marker, backlog_marker + "\n" + card_entry)
            else:
                content += "\n\n## Backlog\n" + card_entry

            with open(kanban_path, 'w', encoding='utf-8') as f:
                f.write(content)

            return True

        except Exception as e:
            print(f"Warning: Could not update Kanban board: {e}")
            return False

    def _get_kanban_template(self) -> str:
        """Return default Kanban Board template."""
        return """---

kanban-plugin: basic

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
"""

    def sync_proposals(self) -> Dict:
        """
        Sync proposals from backend to vault.

        Returns:
            dict with sync result information
        """
        try:
            from src.sync_check import get_sync_manager
            sync_manager = get_sync_manager()
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


__all__ = ["ProposalWriter"]