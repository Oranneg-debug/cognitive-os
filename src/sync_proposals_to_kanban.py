"""
Sync Proposals to Kanban - Backfill utility for the SQLite backend.

Scans the proposals directory and ensures cards are registered in the
SQLite kanban_state.sqlite database.
"""

import argparse
import asyncio
import re
import sys
import yaml
from pathlib import Path
from typing import Optional, Dict, Any

# Ensure we can import from src
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.kanban_store import KanbanStore, Card
from src.paths import PROPOSALS_DIR
from src.proposal_sync import ProposalSyncManager


def extract_metadata(file_path: Path) -> Dict[str, Any]:
    """Extract YAML frontmatter and title from a proposal file."""
    content = file_path.read_text(encoding='utf-8')
    
    # Extract frontmatter
    metadata = {}
    frontmatter_match = re.search(r'^---\n(.*?)\n---', content, re.DOTALL)
    if frontmatter_match:
        try:
            metadata = yaml.safe_load(frontmatter_match.group(1))
        except yaml.YAMLError:
            pass
            
    # Extract title
    title = ""
    title_match = re.search(r'^#\s+(.*)', content, re.MULTILINE)
    if title_match:
        title = title_match.group(1).strip()
        
    # Extract ID if not in metadata
    proposal_id = metadata.get('id')
    if not proposal_id:
        id_match = re.search(r'(?:DEV|ARCH|NLST)-\d{8}-\d{6}-[A-Z0-9]+', content)
        if id_match:
            proposal_id = id_match.group(0)
            
    return {
        "proposal_id": proposal_id,
        "prefix": metadata.get('prefix', proposal_id.split('-')[0] if proposal_id else "DEV"),
        "title": title,
        "column_name": metadata.get('column', 'backlog'),
        "substatus": metadata.get('substatus', metadata.get('status', 'pending')),
        "severity": metadata.get('severity', 'medium'),
        "origin": metadata.get('origin', 'unknown'),
        "keywords": _serialize_keywords(metadata.get('keywords')),
    }


def _serialize_keywords(keywords) -> Optional[str]:
    """Normalize keywords from YAML (list) to SQLite (comma-separated string)."""
    if not keywords:
        return None
    if isinstance(keywords, str):
        return keywords
    if isinstance(keywords, list):
        return ",".join(str(k).strip() for k in keywords if k)
    return str(keywords)


async def sync_proposal(store: KanbanStore, proposal_id: str) -> bool:
    """Sync a single proposal by ID."""
    # Look for the file
    for file_path in PROPOSALS_DIR.glob(f"*{proposal_id}*.md"):
        meta = extract_metadata(file_path)
        if meta["proposal_id"] == proposal_id:
            await store.add_card(
                proposal_id=meta["proposal_id"],
                prefix=meta["prefix"],
                column_name=meta["column_name"],
                title=meta["title"],
                substatus=meta["substatus"],
                severity=meta["severity"],
                origin=meta["origin"],
                keywords=meta.get("keywords"),
            )
            # Update keywords on existing cards (add_card is idempotent,
            # so it returns early without updating fields).
            if meta.get("keywords"):
                await store.update_card(meta["proposal_id"], {"keywords": meta["keywords"]})
            return True
    return False


async def main():
    parser = argparse.ArgumentParser(description="Sync proposals to Kanban SQLite backend.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--only", help="Sync only the specified proposal ID")
    group.add_argument("--all", action="store_true", help="Sync all proposals in the directory")
    
    args = parser.parse_args()
    
    store = KanbanStore()
    await store.init_schema()
    
    if args.only:
        success = await sync_proposal(store, args.only)
        if success:
            print(f"Successfully synced {args.only}")
            sys.exit(0)
        else:
            print(f"Could not find proposal {args.only}")
            sys.exit(1)
    elif args.all:
        count = 0
        for file_path in PROPOSALS_DIR.glob("*.md"):
            meta = extract_metadata(file_path)
            if meta["proposal_id"]:
                await store.add_card(
                    proposal_id=meta["proposal_id"],
                    prefix=meta["prefix"],
                    column_name=meta["column_name"],
                    title=meta["title"],
                    substatus=meta["substatus"],
                    severity=meta["severity"],
                    origin=meta["origin"],
                    keywords=meta.get("keywords"),
                )
                count += 1
        print(f"Synced {count} proposals")
    else:
        parser.print_help()
        return

    # Trigger active file sync to vault
    print("🔄 Synchronizing files to Obsidian vault...")
    sync_manager = ProposalSyncManager()
    result = sync_manager.sync_backend_to_vault()
    if result.success:
        print(f"✅ Vault sync complete: {result.files_synced} files updated.")
    else:
        print(f"⚠️ Vault sync encountered issues: {', '.join(result.errors)}")


if __name__ == "__main__":
    asyncio.run(main())
