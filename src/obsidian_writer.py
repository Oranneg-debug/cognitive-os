import os
from datetime import datetime
from pathlib import Path

from src.paths import (
    VAULT_COUNCIL_OUTPUTS,
    VAULT_MEMORY_LOGS,
    COS_VAULT_COUNCIL_OUTPUTS,
    COS_VAULT_MEMORY_LOGS,
)


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def pattern_to_council_type(pattern_name: str) -> str:
    """
    Map pattern name to council type for routing.

    Args:
        pattern_name: Pattern name like "DESIGN_MEETING", "SEQUENTIAL_BOARDROOM"

    Returns:
        "user_side" for Design/Oracle/NFT, "system_side" for others
    """
    user_side_patterns = {
        "DESIGN_MEETING",
        "ORACLE_COUNCIL",
        "NFT_CREATION",
    }
    if pattern_name in user_side_patterns:
        return "user_side"
    return "system_side"  # Default: system councils (Boardroom, Technical, Dev lifecycle)


# ============================================================================
# OBSIDIAN WRITER CLASS
# ============================================================================


class ObsidianWriter:
    def __init__(self, vault_path: str | Path | None = None, council_type: str | None = None):
        """
        Initialize the ObsidianWriter with appropriate vault destination.

        Args:
            vault_path: Optional override for vault path
            council_type: "user_side" or "system_side". If None, defaults to user_side for backward compatibility.
        """
        self.council_type = council_type
        if vault_path:
            self.vault_path = str(vault_path)
            # When vault_path is explicitly provided, use Grand Nexus memory logs for backward compatibility
            self.memory_path = str(VAULT_MEMORY_LOGS)
        elif council_type == "user_side":
            self.vault_path = str(VAULT_COUNCIL_OUTPUTS)
            self.memory_path = str(VAULT_MEMORY_LOGS)
        else:
            self.vault_path = str(COS_VAULT_COUNCIL_OUTPUTS)
            self.memory_path = str(COS_VAULT_MEMORY_LOGS)
        os.makedirs(self.vault_path, exist_ok=True)
        os.makedirs(self.memory_path, exist_ok=True)

    def write_note(
        self,
        title: str,
        content: str,
        pattern_used: str,
        task_id: str,
        source_file_path: str = None,
        council_type: str | None = None,
    ) -> str:
        """
        Writes a generated response to the Obsidian vault with appropriate frontmatter.
        If source_file_path is provided, it adds a backlink to the original document.

        Args:
            title: Note title
            content: Note content
            pattern_used: Pattern name used (e.g., "DESIGN_MEETING")
            task_id: Task identifier
            source_file_path: Optional source file path for backlink
            council_type: "user_side" or "system_side". If None, inferred from pattern_used.

        Returns:
            Path to the written file, or empty string on failure.
        """
        # Determine council type (explicit override > instance default > infer from pattern)
        if council_type is None:
            council_type = self.council_type
        if council_type is None:
            council_type = pattern_to_council_type(pattern_used)

        # Route to appropriate vault based on council type
        if council_type == "user_side":
            self.vault_path = str(VAULT_COUNCIL_OUTPUTS)
            self.memory_path = str(VAULT_MEMORY_LOGS)
        else:
            self.vault_path = str(COS_VAULT_COUNCIL_OUTPUTS)
            self.memory_path = str(COS_VAULT_MEMORY_LOGS)

        # Sanitize title for filename
        safe_title = "".join([c for c in title if c.isalpha() or c.isdigit() or c==' ']).rstrip()
        filename = f"{safe_title}.md"
        if not filename.strip('.md'):
            filename = f"Council_Output_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
            
        file_path = os.path.join(self.vault_path, filename)
        
        import re
        # Find all hashtags in the content (e.g. #DarkMaestro) and strip the '#'
        found_tags = set(re.findall(r'(?<![\w])#([a-zA-Z_][a-zA-Z0-9_\-]+)', content))
        
        # Combine default tags with found tags
        base_tags = ["ai-council", pattern_used.lower().replace('_', '-')]
        all_tags = base_tags + list(found_tags)
        
        # Format tags for YAML (comma-separated, no brackets here as we will wrap them)
        tags_str = ", ".join(all_tags)

        # Add YAML Frontmatter
        frontmatter = f"""---
title: "{title}"
created: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
tags: [{tags_str}]
pattern_used: {pattern_used}
task_id: {task_id}
---

"""
        
        # Add backlink if source_file_path is provided
        backlink_content = ""
        if source_file_path:
            # Assuming vault name is part of the vault_path, or can be configured
            # For now, let's just use the relative path, Obsidian can resolve it
            # Or a simple file:/// link
            # A more robust solution might involve knowing the Obsidian vault name dynamically
            # For demonstration, we'll use a direct file link or an assumed relative path if within vault
            relative_source_path = os.path.relpath(source_file_path, self.vault_path).replace("\\", "/")
            # Try to make an Obsidian URI if it's a markdown file, otherwise a file link
            if source_file_path.endswith(".md"):
                # This requires knowing the vault name. Let's assume a placeholder for now or pass it
                # For now, a simpler file link. User can configure vault path to their Obsidian vault root
                vault_name = os.path.basename(os.path.normpath(self.vault_path.split('/AI-Help/')[0])) # Heuristic for vault name
                if vault_name:
                     backlink_content = f"[Source Document](obsidian://open?vault={vault_name}&file={relative_source_path})\n\n"
                else:
                     backlink_content = f"[Source Document](file:///{source_file_path})\n\n"
            else: # For PDFs or other files, use a direct file link
                backlink_content = f"[Source Document](file:///{source_file_path})\n\n"

        # Generate the specific report name format for memory
        report_name = filename.replace('.md', '')
        
        memory_footer = f"\n\n---\n### 🧠 Deliberation Memory\n[Open Full Memory Log](file:///./memory_logs/{report_name}-mem.json)"
        full_content = frontmatter + backlink_content + content + memory_footer
        
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(full_content)
            print(f"✅ Note saved to Obsidian: {file_path}")
            return file_path
        except Exception as e:
            print(f"❌ Failed to write to Obsidian: {e}")
            return ""

    def save_memory_log(self, task_id: str, memory_data: dict, report_name: str = None):
        """Saves a copy of the boardroom memory JSON into the Obsidian vault for backlinking."""
        import json
        if report_name:
            safe_report = "".join([c for c in report_name if c.isalpha() or c.isdigit() or c=='_']).rstrip()
            filename = f"{safe_report}-mem.json"
        else:
            filename = f"{task_id}.json"
            
        memory_file = os.path.join(self.memory_path, filename)
        try:
            with open(memory_file, 'w', encoding='utf-8') as f:
                json.dump(memory_data, f, indent=2, ensure_ascii=False)
            print(f"🧠 Memory log archived to vault: {memory_file}")
        except Exception as e:
            print(f"⚠️ Failed to archive memory log: {e}")

    def search_vault(self, query: str, limit: int = 5) -> list:
        """
        Performs a basic keyword search over the vault.
        """
        results = []
        query = query.lower()
        
        # Traverse the vault
        for root, _, files in os.walk(self.vault_path):
            for file in files:
                if file.endswith(".md"):
                    path = os.path.join(root, file)
                    try:
                        with open(path, 'r', encoding='utf-8') as f:
                            content = f.read()
                            if query in content.lower() or query in file.lower():
                                # Simple scoring: title match is better
                                score = 2 if query in file.lower() else 1
                                results.append({
                                    "title": file.replace(".md", ""),
                                    "path": path,
                                    "snippet": content[:200] + "...",
                                    "score": score
                                })
                    except:
                        continue
        
        # Sort by score and return top results
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:limit]