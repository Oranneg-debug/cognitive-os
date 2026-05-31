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
from typing import Dict
import requests
import json

from src.paths import (
    VAULT_ROOT,
    COS_VAULT_ROOT,
    COS_VAULT_PROPOSALS_DIR,
    COS_VAULT_RELEASES_DIR,
    COS_VAULT_TEMPLATES_DIR,
    PROPOSALS_DIR,
    HANDOFFS_DIR,
    RELEASES_DIR,
    TEMPLATES_DIR,
)

# Governance Foundation imports
from src.workflow_models import ValidatedProposal, Severity, WorkflowPhase
from src.kanban_store import KanbanStore
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
        # System-side proposals and releases go to COS vault
        self.vault_proposals_dir = str(COS_VAULT_PROPOSALS_DIR)
        self.vault_releases_dir = str(COS_VAULT_RELEASES_DIR)
        
        # Create directories (both project and COS vault)
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

        # Load template from COS vault (system-side canonical source)
        vault_template_path = str(COS_VAULT_TEMPLATES_DIR / "proposal-template.md")

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
                f"\nid: \"{proposal_id}\""
                f"\noriginal_request: \"{user_input[:300].replace(chr(34), chr(39))}\""
                f"\norigin: \"{origin}\""
            )
            if source_note:
                fm_extra += f"\nsource_note: \"[[{source_note}]]\""
            # Inject keywords if provided via llm_proposal_data
            if llm_proposal_data and llm_proposal_data.get("keywords"):
                kw = llm_proposal_data["keywords"]
                kw_list = kw if isinstance(kw, list) else [str(kw)]
                kw_yaml = ", ".join(kw_list)
                fm_extra += f"\nkeywords: [{kw_yaml}]"
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

        # Validate proposal YAML before any writes (read-only, safe to run first)
        validate_proposal_yaml(content)

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

            # After UoW completes successfully, create a snapshot of the proposal
            handoff_vault = HandoffVault()
            handoff_vault.snapshot(proposal_id, filename)
        else:
            # Legacy fallback: direct file writes
            print("[WARNING] GovernanceUnitOfWork is disabled - using legacy direct file writes")
            filename = f"{self.proposals_dir}/{proposal_id}_PROPOSAL.md"
            Path(filename).write_text(content, encoding='utf-8')

            vault_filename = filename.replace(self.proposals_dir, self.vault_proposals_dir)
            Path(vault_filename).parent.mkdir(parents=True, exist_ok=True)
            Path(vault_filename).write_text(content, encoding='utf-8')

            # Also snapshot for legacy writes
            handoff_vault = HandoffVault()
            handoff_vault.snapshot(proposal_id, filename)

        # Extract a human-readable title for the Kanban card metadata
        card_title = self._extract_card_title(user_input)

        # Severity priority:
        #   1. explicit YAML frontmatter (e.g. ARCH/NLST agents set this)
        #   2. SentryRouter._assess_complexity() on the raw user_input —
        #      keyword heuristics that already exist in the router and map
        #      cleanly to high/medium/low. Free, instant, no LLM call.
        #   3. fallback: "medium" (safe default Technical Meeting).
        severity = self._extract_severity_from_frontmatter(content)
        if severity is None:
            try:
                from src.sentry_router import SentryRouter
                complexity, _ = SentryRouter()._assess_complexity(user_input)
                severity = complexity  # already 'low'/'medium'/'high'
            except Exception as exc:
                print(f"[ProposalWriter] sentry severity-classification failed: {exc!r}")
                severity = "medium"

        # Add card to SQLite kanban store (single source of truth — the
        # vault Dev-KanBan.md mirror was deleted 2026-05-26).
        keywords = None
        if llm_proposal_data and llm_proposal_data.get("keywords"):
            kw = llm_proposal_data["keywords"]
            keywords = ",".join(kw) if isinstance(kw, list) else str(kw)
        self._add_card_to_store(proposal_id, prefix, card_title, origin, severity, keywords)

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

    @staticmethod
    def _extract_severity_from_frontmatter(content: str) -> str | None:
        """Return ``severity`` value from a proposal's YAML frontmatter, or None.

        We do a tiny regex scan instead of full YAML parse — frontmatter
        shape varies and we only care about one field.
        """
        # Limit search to the frontmatter block (between the first two ---).
        if not content.startswith('---'):
            return None
        end = content.find('\n---\n', 3)
        if end < 0:
            return None
        block = content[3:end]
        m = re.search(r'^\s*severity:\s*["\']?(\w+)["\']?\s*$', block, re.MULTILINE)
        if not m:
            return None
        sev = m.group(1).strip().lower()
        # Only accept the three values the dispatcher knows.
        return sev if sev in ('high', 'medium', 'low') else None

    def _add_card_to_store(
        self,
        proposal_id: str,
        prefix: str,
        title: str,
        origin: str,
        severity: str | None = None,
        keywords: str | None = None,
    ) -> bool:
        """
        Add a new proposal card to the SQLite kanban store (for dashboard).

        Args:
            proposal_id: The ID of the proposal (e.g., DEV-20260525-123456-ABCD1234)
            prefix: The prefix (DEV, ARCH, NLST)
            title: Short title for the card
            origin: Where the proposal came from (telegram, obsidian, etc.)
            severity: high/medium/low
            keywords: Comma-separated tags for dashboard search

        Returns:
            True if successful, False otherwise
        """
        try:
            import asyncio
            import threading
            
            kanban_store = KanbanStore()
            
            # Run the async add_card method from sync context
            # Use threading to avoid event loop conflicts
            def _add_in_thread():
                asyncio.run(kanban_store.add_card(
                    proposal_id=proposal_id,
                    prefix=prefix,
                    column_name="backlog",
                    title=title or None,
                    substatus=None,
                    severity=severity,
                    origin=origin or "unknown",
                    keywords=keywords,
                    approver="system",
                    reason="Proposal created",
                ))
            
            thread = threading.Thread(target=_add_in_thread, daemon=True)
            thread.start()
            thread.join(timeout=5.0)  # Wait max 5 seconds
            
            if thread.is_alive():
                print(f"⚠️ Warning: Dashboard kanban store update timed out for {proposal_id}")
                return False
            
            print(f"✅ Added {proposal_id} to dashboard kanban store")
            return True

        except Exception as e:
            print(f"⚠️ Warning: Could not add card to dashboard kanban store: {e}")
            import traceback
            traceback.print_exc()
            return False

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
                        "details": result_dict,
                    }
                return {
                    "success": False,
                    "message": f"Sync completed with errors: {result_dict.get('errors')}",
                    "details": result_dict,
                }
        except Exception as e:
            return {
                "success": False,
                "message": f"Sync failed: {str(e)}",
                "error": str(e),
            }

        return {"success": False, "message": "Sync manager unavailable"}


__all__ = ["ProposalWriter"]