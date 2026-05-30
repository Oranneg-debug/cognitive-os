import os
import re
from pathlib import Path


def build_universal_context() -> str:
    """
    Aggregates system knowledge from docs/, src/, and dev/ directories.
    
    Returns a formatted markdown block containing:
    - Architecture overview (first 100 lines + Mermaid extraction)
    - Module listing from src/
    - Recent decisions from dev/decisions/
    - Proposal count from dev/proposals/
    
    Every I/O call is wrapped in try/except returning empty string on failure.
    """
    sections = []
    status_parts = []
    
    # 1. Architecture doc
    architecture_content = _get_architecture_doc()
    if architecture_content:
        sections.append(f"# ARCHITECTURE OVERVIEW\n{architecture_content}")
        status_parts.append("Architecture=OK")
    else:
        status_parts.append("Architecture=MISSING")
    
    # 2. Module listing
    module_listing = _get_module_listing()
    if module_listing:
        sections.append(f"# MODULE CONGREGATION\n{module_listing}")
        status_parts.append("Modules=OK")
    else:
        status_parts.append("Modules=MISSING")
    
    # 3. Recent decisions
    decisions_content = _get_recent_decisions()
    if decisions_content:
        sections.append(f"# RECENT DECISIONS\n{decisions_content}")
        status_parts.append("Decisions=OK")
    else:
        status_parts.append("Decisions=MISSING")
    
    # 4. Proposal count
    proposal_count = _count_proposals()
    if proposal_count >= 0:
        sections.append(f"# PROPOSAL COUNT\n{proposal_count} proposals etched in dev/proposals/")
        status_parts.append("Proposals=OK")
    else:
        status_parts.append("Proposals=MISSING")
    
    # Build status header
    status_header = f"[SYSTEM KNOWLEDGE STATUS: {', '.join(status_parts)}]"
    
    # Combine all sections
    full_content = "\n\n".join(sections)
    
    # Truncate to ~1000 tokens if needed (conservative estimate: 4 chars ≈ 1 token)
    max_chars = 4000  # ~1000 tokens buffer
    if len(full_content) > max_chars:
        truncated = full_content[:max_chars]
        # Try to truncate at a natural break (newline)
        last_break = truncated.rfind('\n')
        if last_break > max_chars * 0.9:
            truncated = truncated[:last_break]
        full_content = truncated + "\n\n[...context truncated for brevity...]"
    
    return f"{status_header}\n\n{full_content}"


def _get_architecture_doc() -> str:
    """Read docs/SYSTEM_ARCHITECTURE.md (first 100 lines + Mermaid extraction)."""
    try:
        docs_dir = Path(__file__).parent.parent / "docs"
        arch_path = docs_dir / "SYSTEM_ARCHITECTURE.md"
        
        if not arch_path.exists():
            return ""
        
        with open(arch_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        # Take first 100 lines
        first_100 = lines[:100]
        content = "".join(first_100).strip()
        
        # Extract Mermaid diagrams (```mermaid ... ```)
        mermaid_pattern = r'```mermaid\s+.*?```'
        mermaids = re.findall(mermaid_pattern, content, re.DOTALL)
        
        if mermaids:
            content += "\n\n## DIAGRAMS\n"
            for i, mermaid in enumerate(mermaids):
                content += f"\n### Diagram {i + 1}\n```mermaid\n{re.search(r'```mermaid\s+(.*?)\s+```', mermaid, re.DOTALL).group(1).strip()}\n```\n"
        
        return content.strip()
    except Exception:
        return ""


def _get_module_listing() -> str:
    """Glob src/**/*.py and list module names."""
    try:
        src_dir = Path(__file__).parent
        py_files = list(src_dir.rglob("*.py"))
        
        if not py_files:
            return ""
        
        modules = []
        for py_file in sorted(py_files):
            rel_path = py_file.relative_to(src_dir.parent)
            module_name = str(rel_path).replace("/", ".").replace("\\", ".")[:-3]  # Remove .py
            modules.append(f"- {module_name}")
        
        return "\n".join(modules)
    except Exception:
        return ""


def _get_recent_decisions() -> str:
    """Load 3 most recent .md files from dev/decisions/ (title + first 3 lines)."""
    try:
        decisions_dir = Path(__file__).parent.parent / "dev" / "decisions"
        
        if not decisions_dir.exists():
            return ""
        
        # Get all .md files
        md_files = list(decisions_dir.glob("*.md"))
        
        # Filter out special files
        md_files = [f for f in md_files if not f.name.startswith("_") and f.suffix == ".md"]
        
        if not md_files:
            return ""
        
        # Sort by modification time (most recent first)
        md_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
        
        # Take first 3
        recent = []
        for file_path in md_files[:3]:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                
                if lines:
                    title = lines[0].strip()
                    if title.startswith("# "):
                        title = title[2:]
                    elif title.startswith("## "):
                        title = title[3:]
                    
                    # Get first 3 non-empty lines
                    content_lines = []
                    for line in lines[:10]:
                        stripped = line.strip()
                        if stripped and not stripped.startswith("---"):
                            content_lines.append(stripped)
                            if len(content_lines) >= 3:
                                break
                    
                    recent.append(f"1. **{file_path.name}**\n   {title}\n   {' '.join(content_lines[:3])}")
            except Exception:
                continue
        
        return "\n\n".join(recent) if recent else ""
    except Exception:
        return ""


def _count_proposals() -> int:
    """Count .md files in dev/proposals/ (excluding special directories)."""
    try:
        proposals_dir = Path(__file__).parent.parent / "dev" / "proposals"
        
        if not proposals_dir.exists():
            return -1
        
        # Count .md files, excluding .gitkeep and .uow_* directories
        count = 0
        for item in proposals_dir.iterdir():
            if item.is_file() and item.suffix == ".md" and not item.name.startswith("_"):
                count += 1
        
        return count
    except Exception:
        return -1