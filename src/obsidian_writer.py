import os
from datetime import datetime

class ObsidianWriter:
    def __init__(self, vault_path: str = "E:/Oranneg/CloudStation/Documents/Obsidian/Grand Nexus/AI-Help/cognitive-os"):
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
        full_content = frontmatter + content
        
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(full_content)
            print(f"✅ Note saved to Obsidian: {file_path}")
            return file_path
        except Exception as e:
            print(f"❌ Failed to write to Obsidian: {e}")
            return ""
