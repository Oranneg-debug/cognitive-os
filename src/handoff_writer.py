"""
Handoff Writer Module - Handles handoff document generation.

Extracted from dev_route.py to enforce Single Responsibility Principle.
"""

import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from src.paths import (
    VAULT_ROOT,
    COS_VAULT_ROOT,
    COS_VAULT_HANDOFFS_DIR,
    COS_VAULT_PROPOSALS_DIR,
    COS_VAULT_TEMPLATES_DIR,
    HANDOFFS_DIR,
)
from src.governance_unit_of_work import GovernanceUnitOfWork
from src.integration_flags import is_governance_uow_enabled

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════════
#  ARCH-5DFB393F (A5+A6) — planner integration with explicit fallback
# ════════════════════════════════════════════════════════════════════

#: Exact fallback notice text. Pinned per Specialist amendment A4 from
#: the 2026-05-25 boardroom verdict on ARCH-5DFB393F. Integration tests
#: assert that this exact prefix appears at the top of a fallen-back
#: tasks block; do not edit casually.
_PLANNER_FALLBACK_NOTICE_TEMPLATE: str = (
    "> ⚠️ PLANNER FAILED, FALLBACK ACTIVE: {reason}. "
    "Tasks extracted via legacy regex.\n\n"
)


def _planner_enabled() -> bool:
    """Read ``handoff.planner_enabled`` from master_config.

    Returns ``True`` (the default) on any error so that the planner is
    on by default; the flag is intended as a kill-switch, not an opt-in.
    """
    try:
        from src.orchestrator import get_config
        return bool(get_config().get("handoff", {}).get("planner_enabled", True))
    except Exception as exc:
        logger.warning("handoff.planner_enabled read failed (%r); defaulting to True.", exc)
        return True


def _render_tasks_via_planner(
    proposal_id: str,
    council_report: str,
    proposal_file: Optional[str],
    binding_constraints: Optional[list] = None,
) -> Optional[str]:
    """Try the HandoffPlanner; return rendered tasks markdown on success.

    Returns ``None`` on any failure so the caller can fall back to the
    legacy regex extractor (CSTR-PLANNER-V2). Never raises.
    """
    if not _planner_enabled():
        return None

    try:
        from src.handoff_planner import HandoffPlanner, PlannerError
    except Exception as exc:
        logger.warning("HandoffPlanner import failed (%r); falling back.", exc)
        return None

    proposal_body = ""
    if proposal_file and os.path.exists(proposal_file):
        try:
            with open(proposal_file, "r", encoding="utf-8") as _f:
                proposal_body = _f.read()
        except OSError as exc:
            logger.warning("Could not read proposal %s (%r); planner will see empty body.", proposal_file, exc)

    try:
        plan = HandoffPlanner().plan(
            proposal_id=proposal_id,
            proposal_body=proposal_body,
            council_report=council_report,
            binding_constraints=binding_constraints or [],
        )
    except PlannerError as exc:
        logger.warning("HandoffPlanner failed (%s: %s); falling back to legacy extractor.",
                       type(exc).__name__, exc)
        return None
    except Exception as exc:  # noqa: BLE001 — true catch-all per CSTR-PLANNER-V2
        logger.warning("HandoffPlanner raised unexpected %s (%s); falling back.",
                       type(exc).__name__, exc)
        return None

    return plan.to_markdown()


def _build_tasks_block_with_fallback(
    proposal_id: str,
    council_report: str,
    proposal_file: Optional[str],
    legacy_tasks_block_factory,
    binding_constraints: Optional[list] = None,
) -> str:
    """Compose the final tasks block.

    On planner success: returns the planner-rendered markdown verbatim.
    On planner failure: returns the fallback notice prepended to the
    legacy block produced by ``legacy_tasks_block_factory()`` (a zero-arg
    callable so we never compute the legacy block when the planner
    succeeds).
    """
    rendered = _render_tasks_via_planner(
        proposal_id=proposal_id,
        council_report=council_report,
        proposal_file=proposal_file,
        binding_constraints=binding_constraints,
    )
    if rendered is not None:
        return rendered

    legacy = legacy_tasks_block_factory()
    if not _planner_enabled():
        # Flag explicitly off — no warning notice, this is the desired path.
        return legacy

    # Planner was tried and failed → caller needs the visible notice.
    reason = "planner unavailable or output rejected (see logs)"
    return _PLANNER_FALLBACK_NOTICE_TEMPLATE.format(reason=reason) + legacy


class HandoffWriter:
    """
    Generates handoff documents for Beta Testing and Alpha Polish phases.
    
    This module extracts handoff generation from DevRouteManager to enforce SRP.
    """

    def __init__(self):
        """Initialize the handoff writer with path constants."""
        self.vault_handoffs_dir = str(COS_VAULT_HANDOFFS_DIR)
        self.source_handoffs_dir = str(HANDOFFS_DIR)

        # Create directories
        os.makedirs(self.vault_handoffs_dir, exist_ok=True)
        os.makedirs(self.source_handoffs_dir, exist_ok=True)

    def generate_beta_handoff(
        self,
        proposal_id: str,
        council_report: str,
        proposals_dir: str = None,
        vault_proposals_dir: str = None
    ) -> Dict:
        """
        Generate a Beta Testing Handoff document from the Technical Council's report.

        The handoff is a developer-facing checklist document saved in both the
        Obsidian vault and the source project folder so the human can open it
        in VS Code and tick items off as they code.

        Args:
            proposal_id:   The DEV-… ID of the proposal.
            council_report: The full markdown report produced by execute_technical_meeting().
            proposals_dir: Optional override for proposals directory path
            vault_proposals_dir: Optional override for vault proposals directory path

        Returns:
            dict with 'vault_path', 'source_path', and 'filename' keys, or
            {'error': <message>} on failure.
        """
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        filename = f"{proposal_id}_BETA_HANDOFF.md"

        # ----------------------------------------------------------------
        # Locate the template (COS vault canonical, Grand Nexus fallback)
        # ----------------------------------------------------------------
        template_paths = [
            str(COS_VAULT_TEMPLATES_DIR / "beta-handoff-template.md"),
            str(HANDOFFS_DIR.parent / "templates" / "beta-handoff-template.md"),
        ]
        template = None
        for tp in template_paths:
            if os.path.exists(tp):
                with open(tp, "r", encoding="utf-8") as f:
                    template = f.read()
                break

        if template is None:
            return {"error": "beta-handoff-template.md not found"}

        # ----------------------------------------------------------------
        # Extract sections from the council report via simple heuristics.
        # The council report is free-form markdown so we do best-effort
        # extraction; whatever we can't parse goes into the full report.
        # ----------------------------------------------------------------
        def _extract_section(report: str, *headings) -> str:
            """Return the first matching section body, or empty string."""
            for h in headings:
                # Match heading and capture until next same-level or higher heading
                # This allows sub-headings (###) within a section (##)
                pattern = rf'(?:^|\n)(#{1,3})\s+{re.escape(h)}[^\n]*\n(.*?)(?=\n\1\s|\n##?\s|\Z)'
                m = re.search(pattern, report, re.IGNORECASE | re.DOTALL)
                if m:
                    return m.group(2).strip()
            return ""

        summary = (
            _extract_section(council_report, "Summary", "Executive Summary", "Overview")
            or council_report[:500].strip()
        )
        difficulties = (
            _extract_section(council_report,
                             "Difficulties", "Constraints", "Challenges",
                             "Risks", "Difficulties & Constraints")
            or "_No specific difficulties extracted — see full report below._"
        )

        # ----------------------------------------------------------------
        # Pre-lookup: kanban_card_id and source_note from proposal file
        # (reused below in the Beta Testing section append AND passed to
        # the planner so it can read the proposal body)
        # ----------------------------------------------------------------
        from src.paths import PROPOSALS_DIR, COS_VAULT_PROPOSALS_DIR
        proposals_dir = proposals_dir or str(PROPOSALS_DIR)
        vault_proposals_dir = str(COS_VAULT_PROPOSALS_DIR)

        proposal_file = None
        for _sd in [vault_proposals_dir, proposals_dir]:
            if os.path.exists(_sd):
                for _fn in os.listdir(_sd):
                    if proposal_id.lower() in _fn.lower() and _fn.endswith("_PROPOSAL.md"):
                        proposal_file = os.path.join(_sd, _fn)
                        break
            if proposal_file:
                break

        kanban_card_id_val = ""
        source_note_val = ""
        if proposal_file and os.path.exists(proposal_file):
            with open(proposal_file, "r", encoding="utf-8") as _pf:
                _prop_text = _pf.read()
            _card_m = re.search(r'\^\[(?:DEV|ARCH|NLST)-[^\]]+\]', _prop_text)
            if _card_m:
                kanban_card_id_val = _card_m.group(0)
            _src_m = re.search(r'source_note:\s*"?(\[\[[^\]]+\]\])"?', _prop_text)
            if _src_m:
                source_note_val = _src_m.group(1)

        # ARCH-5DFB393F (A5): planner-first, regex-fallback. The legacy
        # extractor is the closure passed to _build_tasks_block_with_fallback
        # so it only runs if the planner is disabled or fails.
        def _legacy_beta_tasks() -> str:
            tasks_raw = _extract_section(
                council_report,
                "Implementation Tasks", "Tasks", "Implementation Plan",
                "Action Items", "Next Steps"
            )
            if tasks_raw:
                task_lines = []
                for line in tasks_raw.splitlines():
                    stripped = line.strip()
                    if stripped and not stripped.startswith("#"):
                        stripped = re.sub(r'^[-*•\d+\.]+\s*', '', stripped)
                        if stripped:
                            task_lines.append(f"- [ ] {stripped}")
                return "\n".join(task_lines) if task_lines else "- [ ] See full council report for tasks"
            return "- [ ] See full council report below for implementation guidance"

        tasks_block = _build_tasks_block_with_fallback(
            proposal_id=proposal_id,
            council_report=council_report,
            proposal_file=proposal_file,
            legacy_tasks_block_factory=_legacy_beta_tasks,
        )

        tasks_count = sum(1 for ln in tasks_block.splitlines() if ln.strip().startswith("- [ ]"))

        # ----------------------------------------------------------------
        # Fill template placeholders
        # ----------------------------------------------------------------
        content = template
        content = content.replace("DEV-YYYYMMDD-HHMMSS-XXXX", proposal_id)
        content = content.replace("YYYY-MM-DD HH:MM:SS", timestamp)
        content = content.replace("<!-- COUNCIL_SUMMARY -->", summary)
        content = content.replace("<!-- COUNCIL_DIFFICULTIES -->", difficulties)
        content = content.replace("<!-- COUNCIL_TASKS -->", tasks_block)
        content = content.replace("<!-- COUNCIL_FULL_REPORT -->", council_report)
        # Machine-readable agent context fields
        content = content.replace(
            'kanban_card_id: "^[DEV-YYYYMMDDHHMMSS-XXXX]"',
            f'kanban_card_id: "{kanban_card_id_val}"'
        )
        content = content.replace('source_note: ""', f'source_note: "{source_note_val}"')
        content = content.replace(
            'tasks_completed: 0\ntasks_total: 0',
            f'tasks_completed: 0\ntasks_total: {tasks_count}'
        )

        # Use GovernanceUnitOfWork for atomic multi-file writes if enabled
        from src.integration_flags import get_integration_flags
        flags = get_integration_flags()
        
        vault_path = os.path.join(self.vault_handoffs_dir, filename)
        source_path = os.path.join(self.source_handoffs_dir, filename)

        if flags['governance_uow_enabled']:
            with GovernanceUnitOfWork() as uow:
                uow.stage_file(Path(vault_path), content)
                uow.stage_file(Path(source_path), content)
        else:
            # Legacy fallback: direct file writes
            print("[WARNING] GovernanceUnitOfWork is disabled - using legacy direct file writes")
            Path(vault_path).write_text(content, encoding='utf-8')
            Path(source_path).write_text(content, encoding='utf-8')

        print(f"[HANDOFF] Beta handoff saved → vault: {vault_path}")
        print(f"[HANDOFF] Beta handoff saved → source: {source_path}")

        # ----------------------------------------------------------------
        # Append a Beta Testing section to the proposal file with a link
        # (proposal_file already resolved above in the pre-lookup block)
        # OUTSIDE UoW per A4 design (single-file append operation)
        # ----------------------------------------------------------------

        if proposal_file and os.path.exists(proposal_file):
            with open(proposal_file, "r", encoding="utf-8") as f:
                prop_content = f.read()

            beta_section = (
                f"\n\n---\n\n"
                f"## 🧪 Beta Testing\n\n"
                f"**Status**: 🔧 In Progress\n"
                f"**Handoff**: [[{proposal_id}_BETA_HANDOFF]]\n"
                f"**Generated**: {timestamp}\n\n"
                f"> The Technical Council has reviewed this proposal and produced a "
                f"[Beta Testing Handoff]([[{proposal_id}_BETA_HANDOFF]]). "
                f"Take the handoff to VS Code and work through the task checklist. "
                f"Move the Kanban card to **Alpha Polish** when all tasks are complete.\n"
            )

            # Avoid duplicate sections
            if "## 🧪 Beta Testing" not in prop_content:
                prop_content += beta_section
                with open(proposal_file, "w", encoding="utf-8") as f:
                    f.write(prop_content)
                print(f"[HANDOFF] Proposal updated with beta section: {proposal_file}")

        return {
            "vault_path": vault_path,
            "source_path": source_path,
            "filename": filename,
        }

    def generate_alpha_handoff(
        self,
        proposal_id: str,
        council_report: str,
        proposals_dir: str = None,
        vault_proposals_dir: str = None
    ) -> Dict:
        """
        Generate an Alpha Polish Handoff document from the Boardroom report.

        Mirrors `generate_beta_handoff`: extracts key sections from a free-form
        markdown council report, writes a handoff to both the Obsidian vault
        and the source project folder, and appends an "Alpha Polish" section
        to the proposal linking to it.

        Args:
            proposal_id:    The DEV-… ID of the proposal.
            council_report: The full markdown report produced by the
                            boardroom (typically execute_sequential_boardroom).
            proposals_dir: Optional override for proposals directory path
            vault_proposals_dir: Optional override for vault proposals directory path

        Returns:
            dict with 'vault_path', 'source_path', 'filename', or
            {'error': <message>} on failure.
        """
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        filename = f"{proposal_id}_ALPHA_HANDOFF.md"

        # ----------------------------------------------------------------
        # Locate template (vault first, then source fallback)
        # ----------------------------------------------------------------
        template_paths = [
            str(COS_VAULT_TEMPLATES_DIR / "alpha-handoff-template.md"),
            str(HANDOFFS_DIR.parent / "templates" / "alpha-handoff-template.md"),
        ]
        template = None
        for tp in template_paths:
            if os.path.exists(tp):
                with open(tp, "r", encoding="utf-8") as f:
                    template = f.read()
                break

        if template is None:
            return {"error": "alpha-handoff-template.md not found"}

        # ----------------------------------------------------------------
        # Extract sections from the council report
        # ----------------------------------------------------------------
        
        # FIX: The orchestrator's output_router sometimes returns a Path object instead of a string.
        # We must read it into a string before running regex operations.
        from pathlib import Path
        if isinstance(council_report, Path):
            try:
                council_report = council_report.read_text(encoding="utf-8")
            except Exception as e:
                return {"error": f"Failed to read council report path: {e}"}
        elif not isinstance(council_report, str):
            council_report = str(council_report)

        def _extract_section(report: str, *headings) -> str:
            for h in headings:
                pattern = rf'(?:^|\n)#{1,3}\s+{re.escape(h)}[^\n]*\n(.*?)(?=\n#{1,3}\s|\Z)'
                m = re.search(pattern, report, re.IGNORECASE | re.DOTALL)
                if m:
                    return m.group(1).strip()
            return ""

        summary = (
            _extract_section(council_report,
                             "Executive Summary", "Summary", "Overview",
                             "Strategic View", "Definitive Blueprint")
            or council_report[:500].strip()
        )
        thresholds = (
            _extract_section(council_report,
                             "Acceptance Thresholds", "Acceptance",
                             "Success Criteria", "Targets", "Metrics")
            or "_No explicit thresholds extracted — see full report below._"
        )
        vetoes = (
            _extract_section(council_report,
                             "Veto Points", "Vetoes", "Rejected",
                             "Critical Risks")
            or "_No explicit veto points extracted — see full report below._"
        )

        # ----------------------------------------------------------------
        # Pre-lookup: kanban_card_id and source_note from proposal file
        # ----------------------------------------------------------------
        from src.paths import PROPOSALS_DIR, COS_VAULT_PROPOSALS_DIR
        proposals_dir = proposals_dir or str(PROPOSALS_DIR)
        vault_proposals_dir = str(COS_VAULT_PROPOSALS_DIR)

        proposal_file = None
        for _sd in [vault_proposals_dir, proposals_dir]:
            if os.path.exists(_sd):
                for _fn in os.listdir(_sd):
                    if proposal_id.lower() in _fn.lower() and _fn.endswith("_PROPOSAL.md"):
                        proposal_file = os.path.join(_sd, _fn)
                        break
            if proposal_file:
                break

        kanban_card_id_val = ""
        source_note_val = ""
        if proposal_file and os.path.exists(proposal_file):
            with open(proposal_file, "r", encoding="utf-8") as _pf:
                _prop_text = _pf.read()
            _card_m = re.search(r'\^\[(?:DEV|ARCH|NLST)-[^\]]+\]', _prop_text)
            if _card_m:
                kanban_card_id_val = _card_m.group(0)
            _src_m = re.search(r'source_note:\s*"?(\[\[[^\]]+\]\])"?', _prop_text)
            if _src_m:
                source_note_val = _src_m.group(1)

        # ARCH-5DFB393F (A6): planner-first, regex-fallback. See A5 for rationale.
        def _legacy_alpha_tasks() -> str:
            tasks_raw = _extract_section(
                council_report,
                "Implementation Tasks", "Tasks", "Implementation Plan",
                "Action Items", "Actionable Steps", "Next Steps", "Action Plan"
            )
            if tasks_raw:
                task_lines = []
                for line in tasks_raw.splitlines():
                    stripped = line.strip()
                    if stripped and not stripped.startswith("#"):
                        stripped = re.sub(r'^[-*•\d+\.]+\s*', '', stripped)
                        if stripped:
                            task_lines.append(f"- [ ] {stripped}")
                return "\n".join(task_lines) if task_lines else "- [ ] See full council report for tasks"
            return "- [ ] See full council report below for polish guidance"

        tasks_block = _build_tasks_block_with_fallback(
            proposal_id=proposal_id,
            council_report=council_report,
            proposal_file=proposal_file,
            legacy_tasks_block_factory=_legacy_alpha_tasks,
        )

        tasks_count = sum(1 for ln in tasks_block.splitlines() if ln.strip().startswith("- [ ]"))

        # ----------------------------------------------------------------
        # Fill template placeholders
        # ----------------------------------------------------------------
        content = template
        content = content.replace("DEV-YYYYMMDD-HHMMSS-XXXX", proposal_id)
        content = content.replace("YYYY-MM-DD HH:MM:SS", timestamp)
        content = content.replace("<!-- COUNCIL_SUMMARY -->", summary)
        content = content.replace("<!-- COUNCIL_THRESHOLDS -->", thresholds)
        content = content.replace("<!-- COUNCIL_VETOES -->", vetoes)
        content = content.replace("<!-- COUNCIL_TASKS -->", tasks_block)
        content = content.replace("<!-- COUNCIL_FULL_REPORT -->", council_report)
        # Machine-readable agent context fields
        content = content.replace(
            'kanban_card_id: "^[DEV-YYYYMMDDHHMMSS-XXXX]"',
            f'kanban_card_id: "{kanban_card_id_val}"'
        )
        content = content.replace('source_note: ""', f'source_note: "{source_note_val}"')
        content = content.replace(
            'tasks_completed: 0\ntasks_total: 0',
            f'tasks_completed: 0\ntasks_total: {tasks_count}'
        )

        # Use GovernanceUnitOfWork for atomic multi-file writes if enabled
        from src.integration_flags import get_integration_flags
        flags = get_integration_flags()
        
        vault_path = os.path.join(self.vault_handoffs_dir, filename)
        source_path = os.path.join(self.source_handoffs_dir, filename)

        if flags['governance_uow_enabled']:
            with GovernanceUnitOfWork() as uow:
                uow.stage_file(Path(vault_path), content)
                uow.stage_file(Path(source_path), content)
        else:
            # Legacy fallback: direct file writes
            print("[WARNING] GovernanceUnitOfWork is disabled - using legacy direct file writes")
            Path(vault_path).write_text(content, encoding='utf-8')
            Path(source_path).write_text(content, encoding='utf-8')

        print(f"[HANDOFF] Alpha handoff saved → vault: {vault_path}")
        print(f"[HANDOFF] Alpha handoff saved → source: {source_path}")

        # ----------------------------------------------------------------
        # Append an Alpha Polish section to the proposal file with a link
        # OUTSIDE UoW per A4 design (single-file append operation)
        # ----------------------------------------------------------------

        if proposal_file and os.path.exists(proposal_file):
            with open(proposal_file, "r", encoding="utf-8") as f:
                prop_content = f.read()

            alpha_section = (
                f"\n\n---\n\n"
                f"## 🔧 Alpha Polish\n\n"
                f"**Status**: 🔧 In Progress\n"
                f"**Handoff**: [[{proposal_id}_ALPHA_HANDOFF]]\n"
                f"**Generated**: {timestamp}\n\n"
                f"> The Boardroom has reviewed this proposal and produced an "
                f"[Alpha Polish Handoff]([[{proposal_id}_ALPHA_HANDOFF]]). "
                f"Take the handoff to VS Code and work through the task checklist. "
                f"Move the Kanban card to **Finalized** when all tasks are complete.\n"
            )

            # Avoid duplicate sections
            if "## 🔧 Alpha Polish" not in prop_content:
                prop_content += alpha_section
                with open(proposal_file, "w", encoding="utf-8") as f:
                    f.write(prop_content)
                print(f"[HANDOFF] Proposal updated with alpha section: {proposal_file}")

        return {
            "vault_path": vault_path,
            "source_path": source_path,
            "filename": filename,
        }


__all__ = ["HandoffWriter"]