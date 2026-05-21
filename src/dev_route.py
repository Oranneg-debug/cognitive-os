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
"""

import os
import glob
import re
from datetime import datetime


def generate_kanban_card_id() -> str:
    """
    Generate a unique Kanban card ID for a proposal.
    
    Returns:
        str: Card ID in format ^[DEV-YYYYMMDDHHMMSS-XXXX]
    """
    import uuid
    return f"^[DEV-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6].upper()}]"



class DevRouteManager:
    """
    Manages the development lifecycle workflow for proposals.
    
    EVERY PHASE REQUIRES EXPLICIT USER APPROVAL before proceeding.
    """
    
    def __init__(self, orchestrator=None):
        self.orchestrator = orchestrator
        # Proposal storage in dev folder (project) - also syncs to Obsidian vault
        self.proposals_dir = "dev/proposals"
        self.releases_dir = "dev/releases"
        # Obsidian vault paths for sync
        self.vault_proposals_dir = os.path.join(
            os.environ.get("OBSIDIAN_VAULT_PATH", "E:\\Oranneg\\CloudStation\\Documents\\Obsidian\\Grand Nexus"),
            "1. P - Seedlings", "dev", "proposals"
        )
        self.vault_releases_dir = os.path.join(
            os.environ.get("OBSIDIAN_VAULT_PATH", "E:\\Oranneg\\CloudStation\\Documents\\Obsidian\\Grand Nexus"),
            "1. P - Seedlings", "dev", "releases"
        )
        # Create directories
        os.makedirs(self.proposals_dir, exist_ok=True)
        os.makedirs(self.releases_dir, exist_ok=True)
        os.makedirs(self.vault_proposals_dir, exist_ok=True)
        os.makedirs(self.vault_releases_dir, exist_ok=True)
    
    def create_proposal(self, user_input: str, origin: str = "unknown", needs_approval: bool = True, llm_proposal_data: dict = None, source_file_path: str = None) -> dict:
        """
        Create a new development proposal using the lean template.

        Args:
            user_input: The proposal description
            origin: Where the proposal came from ("telegram", "obsidian", etc.)
            needs_approval: Whether user approval is required (default True)
            llm_proposal_data: Optional dict with LLM-generated details (ignored here)
            source_file_path: Optional path to the originating note/file (e.g. an
                              Obsidian message under AI-Help/cognitive-os). When
                              supplied the proposal is linked back to the source so
                              the chain of custody is never lost.

        Returns:
            dict with proposal_id, filepath, status, and approval_info
        """
        import uuid

        proposal_id = f"DEV-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8].upper()}"
        kanban_card_id = generate_kanban_card_id()

        # Derive a clean Obsidian wikilink name from the source path
        source_note = (
            os.path.splitext(os.path.basename(source_file_path))[0]
            if source_file_path else None
        )

        # Load template from Obsidian vault (source of truth for template)
        vault_template_path = os.path.join(
            os.environ.get("OBSIDIAN_VAULT_PATH", "E:\\Oranneg\\CloudStation\\Documents\\Obsidian\\Grand Nexus"),
            "1. P - Seedlings", "dev", "templates", "proposal-template.md"
        )

        if not os.path.exists(vault_template_path):
            raise FileNotFoundError(f"Proposal template not found at {vault_template_path}")

        with open(vault_template_path, 'r', encoding='utf-8') as f:
            template = f.read()

        # Replace template placeholders
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        content = template.replace('DEV-YYYYMMDD-HHMMSS-XXXX', proposal_id)
        content = content.replace('YYYY-MM-DD HH:MM:SS', timestamp)
        content = content.replace('[Telegram/Obsidian/Direct]', origin)
        content = content.replace('^[DEV-YYYYMMDDHHMMSS-XXXX]', kanban_card_id)
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

        # Save proposal to file - clean format: DEV-YYYYMMDD-HHMMSS-XXXX_PROPOSAL.md
        filename = f"{self.proposals_dir}/{proposal_id}_PROPOSAL.md"

        with open(filename, 'w', encoding='utf-8') as f:
            f.write(content)

        # Also save to vault directory for Obsidian sync
        vault_filename = filename.replace(self.proposals_dir, self.vault_proposals_dir)
        os.makedirs(os.path.dirname(vault_filename), exist_ok=True)
        with open(vault_filename, 'w', encoding='utf-8') as f:
            f.write(content)

        # Extract a human-readable title for the Kanban card metadata
        card_title = self._extract_card_title(user_input)

        # Auto-add card to Kanban Board in vault
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

    def _add_card_to_kanban(self, proposal_id: str, title: str, card_id: str, source_note: str = None) -> bool:
        """
        Add a new proposal card to the Kanban Board.md file.

        Args:
            proposal_id: The ID of the proposal
            title: Short title for the card
            card_id: The Kanban card ID
            source_note: Optional Obsidian note name that originated this proposal
                         (e.g. a message under AI-Help/cognitive-os). When supplied
                         a 'source' metadata line is added to the card so the
                         chain-of-custody is visible directly on the Kanban board.

        Returns:
            True if successful, False otherwise
        """
        try:
            # Build path to Kanban board in vault safely by going up two directories
            seedlings_dir = os.path.dirname(os.path.dirname(self.vault_proposals_dir))
            kanban_path = os.path.join(seedlings_dir, "Dev-KanBan.md")
            
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
    
    def review_proposal(self, proposal_id: str, review_data: dict, user_approved: bool = False) -> bool:
        """
        Record beta council review for a proposal (Phase 2).
        
        Args:
            proposal_id: The ID of the proposal to review
            review_data: Dict with keys: approved, concerns, model_recommendation
            user_approved: Whether user approved the beta phase
            
        Returns:
            True if successful
        """
        # Search in both project and vault directories
        patterns = [
            f"{self.proposals_dir}/*_{proposal_id}_PROPOSAL.md",
            f"{self.vault_proposals_dir}/*_{proposal_id}_PROPOSAL.md"
        ]
        
        files = []
        for pattern in patterns:
            files.extend(glob.glob(pattern))
        
        if not files:
            return False
        
        # Use the first matching file (project takes precedence)
        filepath = files[0]
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Update status
        approved = review_data.get("approved", False)
        
        if user_approved:
            # User approved - move to beta testing
            new_status = "beta_testing"
            
            # Add review section
            review_section = f"""
## Beta Council Review

**Status**: {"✅ APPROVED" if approved else "❌ REJECTED"}  
**Date**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

### Review Details
- **Technical Strengths**: {review_data.get("strengths", "N/A")}
- **Concerns**: {review_data.get("concerns", "None")}
- **Model Recommendation**: {review_data.get("model_recommendation", "N/A")}
- **Beta Ready**: {"Yes" if review_data.get("beta_ready", False) else "No"}

---
"""
            # Update lifecycle phase after Beta Council Review approval (ROBUST REGEX)
            content = re.sub(
                r'\|\s*Lifecycle Phase\s*\|\s*`?1/5[^|]*\|',
                '| Lifecycle Phase | `3/5 - Beta Testing` |',
                content
            )
            # Update approval status table (both phases 1 and 2 as approved) (ROBUST REGEX)
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            content = re.sub(
                r'\|\s*1️⃣\s*\|\s*Proposal Generation\s*\|[^|]*\|[^|]*\|[^|]*\|',
                f'| 1️⃣ | Proposal Generation | ✅ APPROVED | User | {timestamp} |',
                content
            )
            content = re.sub(
                r'\|\s*2️⃣\s*\|\s*Beta Council Review\s*\|[^|]*\|[^|]*\|[^|]*\|',
                f'| 2️⃣ | Beta Council Review | ✅ APPROVED | Beta Council | {timestamp} |',
                content
            )
            content = re.sub(
                r'\*\*Current Phase\*\*:\s*1/5[^\n]*',
                '**Current Phase**: 3/5 - Beta Testing',
                content
            )
            content = re.sub(
                r'\*\*Status\*\*:\s*🟡[^\n]*',
                '**Status**: 🟢 Beta Testing In Progress',
                content
            )
        else:
            # User did not approve
            new_status = "beta_rejected"
            review_section = f"""
## Beta Council Review

**Status**: ⏳ Awaiting User Approval  
**Date**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

### Review Details
- **Technical Strengths**: {review_data.get("strengths", "N/A")}
- **Concerns**: {review_data.get("concerns", "None")}
- **Model Recommendation**: {review_data.get("model_recommendation", "N/A")}
- **Beta Ready**: {"Yes" if review_data.get("beta_ready", False) else "No"}

---
"""
        
        # Insert before the footer
        content = content.replace("*Proposal created via", review_section + "*Proposal created via")
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        
        return True
    
    def save_beta_implementation_plan(self, proposal_id: str, plan_data: dict) -> bool:
        """
        Save the technical implementation plan generated in Phase 3.
        
        Args:
            proposal_id: The ID of the proposal
            plan_data: Dict with implementation plan details
            
        Returns:
            True if successful
        """
        pattern = f"{self.proposals_dir}/*_{proposal_id}_PROPOSAL.md"
        files = glob.glob(pattern)
        if not files: return False
        
        filepath = files[0]
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
            
        phases = plan_data.get("implementation_phases", [])
        if not phases:
            return True
            
        plan_section = "## 🏗️ Technical Implementation Plan (Beta Phase)\n\n"
        for phase in phases:
            phase_num = phase.get("phase", "?")
            plan_section += f"### Phase {phase_num}\n"
            for task in phase.get("tasks", []):
                plan_section += f"- [ ] {task}\n"
            plan_section += "\n"
            
        # Insert before the footer
        content = content.replace("*Proposal created via", plan_section + "\n*Proposal created via")
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
            
        return True

    def generate_beta_handoff(self, proposal_id: str, council_report: str) -> dict:
        """
        Generate a Beta Testing Handoff document from the Technical Council's report.

        The handoff is a developer-facing checklist document saved in both the
        Obsidian vault and the source project folder so the human can open it
        in VS Code and tick items off as they code.

        Args:
            proposal_id:   The DEV-… ID of the proposal.
            council_report: The full markdown report produced by execute_technical_meeting().

        Returns:
            dict with 'vault_path', 'source_path', and 'filename' keys, or
            {'error': <message>} on failure.
        """
        import re as _re

        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        filename = f"{proposal_id}_BETA_HANDOFF.md"

        # ----------------------------------------------------------------
        # Locate the template
        # ----------------------------------------------------------------
        template_paths = [
            os.path.join(
                os.environ.get("OBSIDIAN_VAULT_PATH",
                               "E:\\Oranneg\\CloudStation\\Documents\\Obsidian\\Grand Nexus"),
                "1. P - Seedlings", "dev", "templates", "beta-handoff-template.md"
            ),
            # Fallback: local project copy
            os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "..", "..", "dev", "templates", "beta-handoff-template.md"),
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
                pattern = rf'(?:^|\n)#{1,3}\s+{_re.escape(h)}[^\n]*\n(.*?)(?=\n#{1,3}\s|\Z)'
                m = _re.search(pattern, report, _re.IGNORECASE | _re.DOTALL)
                if m:
                    return m.group(1).strip()
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

        # Build a checklist from any bullet/numbered lines in an
        # "implementation" or "tasks" section.
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
                    # Normalise any existing bullet/number to a checkbox
                    stripped = _re.sub(r'^[-*•\d+\.]+\s*', '', stripped)
                    if stripped:
                        task_lines.append(f"- [ ] {stripped}")
            tasks_block = "\n".join(task_lines) if task_lines else "- [ ] See full council report for tasks"
        else:
            tasks_block = "- [ ] See full council report below for implementation guidance"

        # ----------------------------------------------------------------
        # Pre-lookup: kanban_card_id and source_note from proposal file
        # (reused below in the Beta Testing section append)
        # ----------------------------------------------------------------
        proposal_file = None
        for _sd in [self.vault_proposals_dir, self.proposals_dir]:
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
            _card_m = _re.search(r'\^\[DEV-[^\]]+\]', _prop_text)
            if _card_m:
                kanban_card_id_val = _card_m.group(0)
            _src_m = _re.search(r'source_note:\s*"?(\[\[[^\]]+\]\])"?', _prop_text)
            if _src_m:
                source_note_val = _src_m.group(1)

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

        # ----------------------------------------------------------------
        # Save to vault handoffs folder
        # ----------------------------------------------------------------
        vault_handoffs_dir = os.path.join(
            os.environ.get("OBSIDIAN_VAULT_PATH",
                           "E:\\Oranneg\\CloudStation\\Documents\\Obsidian\\Grand Nexus"),
            "1. P - Seedlings", "dev", "handoffs"
        )
        os.makedirs(vault_handoffs_dir, exist_ok=True)
        vault_path = os.path.join(vault_handoffs_dir, filename)
        with open(vault_path, "w", encoding="utf-8") as f:
            f.write(content)

        # ----------------------------------------------------------------
        # Save backup to source project handoffs folder
        # ----------------------------------------------------------------
        source_handoffs_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", "dev", "handoffs"
        )
        os.makedirs(source_handoffs_dir, exist_ok=True)
        source_path = os.path.join(source_handoffs_dir, filename)
        with open(source_path, "w", encoding="utf-8") as f:
            f.write(content)

        print(f"[HANDOFF] Beta handoff saved → vault: {vault_path}")
        print(f"[HANDOFF] Beta handoff saved → source: {source_path}")

        # ----------------------------------------------------------------
        # Append a Beta Testing section to the proposal file with a link
        # (proposal_file already resolved above in the pre-lookup block)
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

    def generate_alpha_handoff(self, proposal_id: str, council_report: str) -> dict:
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

        Returns:
            dict with 'vault_path', 'source_path', 'filename', or
            {'error': <message>} on failure.
        """
        import re as _re

        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        filename = f"{proposal_id}_ALPHA_HANDOFF.md"

        # ----------------------------------------------------------------
        # Locate template (vault first, then source fallback)
        # ----------------------------------------------------------------
        template_paths = [
            os.path.join(
                os.environ.get("OBSIDIAN_VAULT_PATH",
                               "E:\\Oranneg\\CloudStation\\Documents\\Obsidian\\Grand Nexus"),
                "1. P - Seedlings", "dev", "templates", "alpha-handoff-template.md"
            ),
            os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "..", "..", "dev", "templates", "alpha-handoff-template.md"),
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
        def _extract_section(report: str, *headings) -> str:
            for h in headings:
                pattern = rf'(?:^|\n)#{1,3}\s+{_re.escape(h)}[^\n]*\n(.*?)(?=\n#{1,3}\s|\Z)'
                m = _re.search(pattern, report, _re.IGNORECASE | _re.DOTALL)
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
                    stripped = _re.sub(r'^[-*•\d+\.]+\s*', '', stripped)
                    if stripped:
                        task_lines.append(f"- [ ] {stripped}")
            tasks_block = "\n".join(task_lines) if task_lines else "- [ ] See full council report for tasks"
        else:
            tasks_block = "- [ ] See full council report below for polish guidance"

        # ----------------------------------------------------------------
        # Pre-lookup: kanban_card_id and source_note from proposal file
        # ----------------------------------------------------------------
        proposal_file = None
        for _sd in [self.vault_proposals_dir, self.proposals_dir]:
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
            _card_m = _re.search(r'\^\[DEV-[^\]]+\]', _prop_text)
            if _card_m:
                kanban_card_id_val = _card_m.group(0)
            _src_m = _re.search(r'source_note:\s*"?(\[\[[^\]]+\]\])"?', _prop_text)
            if _src_m:
                source_note_val = _src_m.group(1)

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
        content = content.replace(
            'kanban_card_id: "^[DEV-YYYYMMDDHHMMSS-XXXX]"',
            f'kanban_card_id: "{kanban_card_id_val}"'
        )
        content = content.replace('source_note: ""', f'source_note: "{source_note_val}"')
        content = content.replace(
            'tasks_completed: 0\ntasks_total: 0',
            f'tasks_completed: 0\ntasks_total: {tasks_count}'
        )

        # ----------------------------------------------------------------
        # Save to vault + source backup
        # ----------------------------------------------------------------
        vault_handoffs_dir = os.path.join(
            os.environ.get("OBSIDIAN_VAULT_PATH",
                           "E:\\Oranneg\\CloudStation\\Documents\\Obsidian\\Grand Nexus"),
            "1. P - Seedlings", "dev", "handoffs"
        )
        os.makedirs(vault_handoffs_dir, exist_ok=True)
        vault_path = os.path.join(vault_handoffs_dir, filename)
        with open(vault_path, "w", encoding="utf-8") as f:
            f.write(content)

        source_handoffs_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", "dev", "handoffs"
        )
        os.makedirs(source_handoffs_dir, exist_ok=True)
        source_path = os.path.join(source_handoffs_dir, filename)
        with open(source_path, "w", encoding="utf-8") as f:
            f.write(content)

        print(f"[HANDOFF] Alpha handoff saved → vault: {vault_path}")
        print(f"[HANDOFF] Alpha handoff saved → source: {source_path}")

        # ----------------------------------------------------------------
        # Append Alpha Polish section to proposal (idempotent)
        # ----------------------------------------------------------------
        if proposal_file and os.path.exists(proposal_file):
            with open(proposal_file, "r", encoding="utf-8") as f:
                prop_content = f.read()

            alpha_section = (
                f"\n\n---\n\n"
                f"## 🛠 Alpha Polish\n\n"
                f"**Status**: 🔧 In Progress\n"
                f"**Handoff**: [[{proposal_id}_ALPHA_HANDOFF]]\n"
                f"**Generated**: {timestamp}\n\n"
                f"> The Boardroom Council has produced an "
                f"[Alpha Polish Handoff]([[{proposal_id}_ALPHA_HANDOFF]]) "
                f"covering UI/UX, performance, and pre-release hardening. "
                f"Take it to VS Code, work through the tasks, then move the "
                f"Kanban card to **Finalized**.\n"
            )

            if "## 🛠 Alpha Polish" not in prop_content and "## Alpha Polish" not in prop_content:
                prop_content += alpha_section
                with open(proposal_file, "w", encoding="utf-8") as f:
                    f.write(prop_content)
                print(f"[HANDOFF] Proposal updated with alpha section: {proposal_file}")

        return {
            "vault_path": vault_path,
            "source_path": source_path,
            "filename": filename,
        }

    def create_alpha_plan(self, proposal_id: str, implementation_plan: dict, user_approved: bool = False) -> bool:
        """
        DEPRECATED — kept as a thin back-compat shim around
        :py:meth:`generate_alpha_handoff`.

        The original regex-based implementation targeted a legacy
        "Lifecycle Phase | 3/5" template and silently dropped the council
        report when those markers were absent (see DEV-20260520-165800-7E5FA256
        post-mortem). New callers should use ``generate_alpha_handoff``
        directly.
        """
        report = ""
        if isinstance(implementation_plan, dict):
            tasks = implementation_plan.get("tasks") or []
            if tasks:
                # tasks may be a list of free-form markdown strings (full
                # council report passed as a single element) or a list of
                # short bullets — handle both.
                report = "\n\n".join(str(t) for t in tasks)
        if not report:
            report = "_No council report supplied to create_alpha_plan._"
        result = self.generate_alpha_handoff(proposal_id, report)
        return "error" not in result

    def finalize_release(self, proposal_id: str, final_data: dict, user_approved: bool = False) -> bool:
        """
        Finalize and release a proposal.
        
        Args:
            proposal_id: The ID of the proposal
            final_data: Dict with release notes, version, models_deployed
            user_approved: Whether user approved the final release
            
        Returns:
            True if successful
        """
        pattern = f"{self.proposals_dir}/*_{proposal_id}_PROPOSAL.md"
        files = glob.glob(pattern)
        
        if not files:
            return False
        
        filepath = files[0]
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        if user_approved:
            # Copy to releases directory
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            release_filename = f"{self.releases_dir}/2026-{timestamp}_{proposal_id}_RELEASE.md"
            
            with open(release_filename, 'w', encoding='utf-8') as f:
                f.write(content)
            
            # Update original proposal
            content = content.replace("Status: **🟢 Alpha Polish In Progress**", 
                                     "Status: **✅ FINALIZED AND RELEASED**")
            content = content.replace("Lifecycle Phase:", "*Lifecycle Phase (Complete):")
            
            release_section = f"""
---

## Release Information

**Version**: {final_data.get("version_number", "1.0.0")}  
**Release Date**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  
**Status**: ✅ **FINALIZED AND RELEASED**

### Models Deployed
{chr(10).join(f'- {m}' for m in final_data.get("models_deployed", []))}

### Release Notes
{final_data.get("release_notes", "No release notes provided.")}

---

*Released via Dev Route*
"""
            
            # Update approval status (phase 5: Final Audit)
            content = content.replace(
                "| 5️⃣ | Final Audit | 🔒 Locked | - | - |",
                "| 5️⃣ | Final Audit | ✅ APPROVED | User | " + datetime.now().strftime('%Y-%m-%d %H:%M:%S') + " |"
            )
            
            # Remove the old footer if present, add new one
            content = content.rstrip() + release_section
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            
            return True
        else:
            # Update status to show waiting for approval (phase 5: Final Audit)
            content = content.replace(
                "| 5️⃣ | Final Audit | 🔒 Locked | - | - |",
                "| 5️⃣ | Final Audit | ⏳ Awaiting Approval | - | - |"
            )
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            
            return False
    
    def process_dev_proposal(self, user_input: str, origin: str = "unknown", source_file_path: str = None) -> dict:
        """
        Process a new development proposal through the full lifecycle.

        Args:
            user_input: The proposal description
            origin: Where the proposal came from ("telegram", "obsidian", etc.)
            source_file_path: Optional path to the originating note/file so the
                              proposal can be linked back to its source.

        Returns:
            Final status dict with all phases completed
        """
        # Phase 1: Create proposal (forward source_file_path for link preservation)
        proposal = self.create_proposal(user_input, origin, source_file_path=source_file_path)

        return {
            "status": "created",
            "proposal_id": proposal["proposal_id"],
            "filepath": proposal["filepath"],
            "source_note": proposal.get("source_note"),
            "phases_completed": 1,
            "message": f"Proposal {proposal['proposal_id']} created. Awaiting your approval to proceed."
        }
