#!/usr/bin/env python3
"""
Migration Script: Inject substatus: planning into existing beta_testing proposals.

This script is idempotent - safe to run multiple times.
It scans dev/proposals/ for proposals in beta_testing phase without substatus
and injects substatus: planning into the frontmatter.

VETO COMPLIANCE:
- A8: Idempotent migration for existing beta_testing proposals
"""

import sys
from pathlib import Path

# Add cognitive-os root to path
SCRIPT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

from src.paths import PROPOSALS_DIR


def has_substatus(fm_data: dict) -> bool:
    """Check if the frontmatter data already has a substatus field."""
    return 'substatus' in fm_data and fm_data['substatus'] is not None


def needs_migration(fm_data: dict) -> bool:
    """
    Check if proposal needs migration.
    
    A proposal needs migration if:
    - phase is 'beta_testing'
    - AND no substatus field exists OR substatus is None
    """
    return (
        fm_data.get('phase') == 'beta_testing' 
        and not has_substatus(fm_data)
    )


def inject_substatus(content: str) -> str:
    """
    Inject substatus: planning into the frontmatter.
    
    Finds the closing --- of the frontmatter block and inserts
    substatus: planning before it.
    
    Args:
        content: Full markdown file content
        
    Returns:
        Updated content with substatus injected
    """
    # Find the frontmatter closing ---
    # The format is: ---\n<yaml>\n---\n<body>
    if not content.startswith('---\n'):
        return content  # No frontmatter, nothing to do
    
    end = content.find('\n---', 4)
    if end == -1:
        return content  # Malformed frontmatter, skip
    
    # Extract current frontmatter
    fm_str = content[4:end]
    
    # Check if substatus already exists (idempotency check)
    for line in fm_str.split('\n'):
        if line.startswith('substatus:'):
            return content  # Already has substatus, skip
    
    # Inject substatus before the closing ---
    new_fm = f"{fm_str}\n  substatus: planning"
    new_content = f"---\n{new_fm}\n---{content[end+4:]}"
    
    return new_content


def migrate_proposal_file(filepath: Path) -> bool:
    """
    Migrate a single proposal file.
    
    Args:
        filepath: Path to the proposal file
        
    Returns:
        True if migration was performed, False if skipped
    """
    try:
        content = filepath.read_text(encoding='utf-8')
        
        # Check if migration is needed (idempotency check)
        if content.startswith('---\n'):
            end = content.find('\n---', 4)
            if end != -1:
                fm_str = content[4:end]
                # Parse just enough to check phase and substatus
                for line in fm_str.split('\n'):
                    if line.strip().startswith('phase: beta_testing'):
                        if 'substatus:' not in fm_str:
                            break
                else:
                    return False  # Not beta_testing or already has substatus
        
        # Perform migration
        new_content = inject_substatus(content)
        
        if new_content != content:
            filepath.write_text(new_content, encoding='utf-8')
            print(f"✅ Migrated: {filepath.name}")
            return True
        else:
            print(f"⏭️  Skipped (already migrated): {filepath.name}")
            return False
            
    except Exception as e:
        print(f"❌ Error processing {filepath.name}: {e}")
        return False


def main():
    """Run the migration on all proposal files."""
    print("=" * 60)
    print("Migration: Inject substatus: planning into beta_testing proposals")
    print("=" * 60)
    print()
    
    if not PROPOSALS_DIR.exists():
        print(f"❌ Proposals directory not found: {PROPOSALS_DIR}")
        sys.exit(1)
    
    # Find all proposal files
    proposal_files = list(PROPOSALS_DIR.glob("*.md"))
    
    if not proposal_files:
        print("No proposal files found.")
        return
    
    print(f"Found {len(proposal_files)} proposal files")
    print()
    
    migrated_count = 0
    skipped_count = 0
    
    for filepath in sorted(proposal_files):
        if migrate_proposal_file(filepath):
            migrated_count += 1
        else:
            skipped_count += 1
    
    print()
    print("=" * 60)
    print(f"Migration complete: {migrated_count} migrated, {skipped_count} skipped")
    print("=" * 60)


if __name__ == "__main__":
    main()