import os
from datetime import datetime

class ObsidianWriter:
    def __init__(self, vault_path: str = "E:/Antigravity/mock_vault"):
        self.vault_path = vault_path
        os.makedirs(self.vault_path, exist_ok=True)
        
    def write_note(self, title: str, content: str, pattern_used: str, task_id: str) -> str:
        """
        Writes a generated response to the Obsidian vault with appropriate frontmatter.
        """
        # Sanitize title for filename
        safe_title = "".join([c for c in title if c.isalpha() or c.isdigit() or c==' ']).rstrip()
        filename = f"{safe_title}.md"
        if not filename.strip('.md'):
            filename = f"Council_Output_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
            
        file_path = os.path.join(self.vault_path, filename)
        
        # Add YAML Frontmatter
        frontmatter = f"""---
title: "{title}"
created: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
tags: [ai-council, {pattern_used.lower().replace('_', '-')}]
pattern_used: {pattern_used}
task_id: {task_id}
---

"""
        full_content = frontmatter + content
        
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(full_content)
            print(f"✅ Note saved to Obsidian: {file_path}")
            return file_path
        except Exception as e:
            print(f"❌ Failed to write to Obsidian: {e}")
            return ""
