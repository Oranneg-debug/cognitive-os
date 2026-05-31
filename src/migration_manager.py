"""
Migration Manager - Idempotent migration from Grand Nexus to Cognitive OS Vault.

This module provides utilities for migrating existing artifacts from Grand Nexus
to the new COS vault while preserving data integrity through checksum-based dedup.
"""
import shutil
import hashlib
from datetime import datetime
from pathlib import Path

from src.paths import (
    VAULT_ROOT,
    COS_VAULT_ROOT,
    _ensure_cos_vault_structure,
)


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def _calculate_file_hash(file_path: Path) -> str:
    """
    Calculate SHA256 hash of a file for content-addressable comparison.

    Args:
        file_path: Path to the file

    Returns:
        Hexadecimal hash string, or empty string on error.
    """
    sha256_hash = hashlib.sha256()
    try:
        with open(file_path, 'rb') as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    except (IOError, OSError):
        return ""


def _needs_migration(src_file: Path, dst_file: Path) -> bool:
    """
    Return True if file needs to be copied (checksum-based dedup).

    Args:
        src_file: Source file path
        dst_file: Destination file path

    Returns:
        True if destination doesn't exist or has different content.
    """
    if not dst_file.exists():
        return True
    src_hash = _calculate_file_hash(src_file)
    dst_hash = _calculate_file_hash(dst_file)
    return src_hash != dst_hash


# ============================================================================
# MIGRATION FUNCTIONS
# ============================================================================


def migrate_to_cos_vault(force: bool = False) -> dict:
    """
    Copy Grand Nexus dev/ artifacts to COS vault if not already present.

    Args:
        force: If True, bypass the .migration_complete marker check.

    Returns:
        dict with status, files_copied, files_skipped, errors
    """
    dst_marker = COS_VAULT_ROOT / ".migration_complete"

    # Check marker (unless force)
    if dst_marker.exists() and not force:
        content = dst_marker.read_text()
        return {
            "status": "skipped",
            "reason": "Migration already complete. Use force=True to re-run.",
            "completed_at": content.strip() if content else None,
        }

    src = VAULT_ROOT / "1. P - Seedlings" / "dev"
    dst = COS_VAULT_ROOT / "1. P - Seedlings" / "dev"

    if not src.exists():
        return {
            "status": "complete",
            "reason": "Source directory does not exist. Nothing to migrate.",
            "files_copied": 0,
            "files_skipped": 0,
        }

    # Create destination dirs first
    _ensure_cos_vault_structure()

    files_copied = 0
    files_skipped = 0
    errors = []

    for file in src.rglob("*.md"):
        rel = file.relative_to(src)
        dest_file = dst / rel

        if not _needs_migration(src_file=file, dst_file=dest_file):
            files_skipped += 1
            continue

        try:
            dest_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(file, dest_file)
            files_copied += 1
        except (IOError, OSError, shutil.Error) as e:
            errors.append(f"Failed to copy {file}: {str(e)}")

    # Write marker file on success
    if not errors:
        dst_marker.write_text(
            f"Migration completed at {datetime.now().isoformat()}\n"
            f"Files copied: {files_copied}, skipped: {files_skipped}"
        )
        return {
            "status": "complete",
            "files_copied": files_copied,
            "files_skipped": files_skipped,
        }

    return {
        "status": "partial",
        "files_copied": files_copied,
        "files_skipped": files_skipped,
        "errors": errors,
    }


def migration_status() -> dict:
    """
    Check migration status without running it.

    Returns:
        dict with status and details about migration state.
    """
    dst_marker = COS_VAULT_ROOT / ".migration_complete"

    if not dst_marker.exists():
        src = VAULT_ROOT / "1. P - Seedlings" / "dev"
        if not src.exists():
            return {
                "status": "not_applicable",
                "reason": "Source directory does not exist",
            }
        md_files = list(src.rglob("*.md"))
        return {
            "status": "pending",
            "files_to_migrate": len(md_files),
        }

    content = dst_marker.read_text().strip()
    # Parse the marker file for stats
    stats = {"completed_at": content}
    for line in content.split("\n"):
        if line.startswith("Files copied:"):
            # Format: "Files copied: 5, skipped: 10"
            parts = line.replace("Files copied:", "").strip().split(",")
            for part in parts:
                if ":" in part:
                    key, val = part.strip().split(":", 1)
                    stats[key.strip()] = int(val.strip())

    return {"status": "complete", **stats}


def force_migration() -> dict:
    """
    Force a migration run, bypassing the marker file.

    Returns:
        dict with migration results.
    """
    return migrate_to_cos_vault(force=True)