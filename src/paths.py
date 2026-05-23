"""
Vault and Project Filesystem Constants

Single source of truth for all filesystem paths used by the Cognitive OS.
Enforces fail-fast validation at import time if vault path is unresolvable.

Usage:
    from src.paths import VAULT_ROOT, PROPOSALS_DIR, ...
"""

import os
from pathlib import Path


# ============================================================================
# PATH VALIDATION
# ============================================================================

def _validate_vault_path() -> Path:
    """
    Validate the Obsidian vault root path.
    
    Precedence:
        1. OBSIDIAN_VAULT_PATH environment variable
        2. Hardcoded fallback (for backward compatibility)
    
    Raises:
        RuntimeError: If neither the env var nor fallback directory is valid.
    
    Returns:
        Path: Validated vault root directory.
    """
    # Try environment variable first
    env_path = os.environ.get("OBSIDIAN_VAULT_PATH")
    if env_path:
        p = Path(env_path)
        if p.is_dir():
            return p
    
    # Fallback: hardcoded path (Windows-style for current dev environment)
    fallback = Path(r"E:\Oranneg\CloudStation\Documents\Obsidian\Grand Nexus")
    if fallback.is_dir():
        return fallback
    
    # Fail-fast: neither source is valid
    raise RuntimeError(
        f"Obsidian vault path not found. "
        f"Set OBSIDIAN_VAULT_PATH env var or ensure '{fallback}' exists."
    )


# Validate at import time (fail-fast)
try:
    VAULT_ROOT = _validate_vault_path()
except Exception as e:
    raise RuntimeError(
        f"Failed to initialize vault paths: {e}. "
        f"Set OBSIDIAN_VAULT_PATH environment variable to fix."
    ) from e


# ============================================================================
# PROJECT PATHS (cognitive-os directory)
# ============================================================================

# Base project directory (where this module lives)
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Source directory
SRC_DIR = PROJECT_ROOT / "src"

# Dev folder for proposals, handoffs, etc.
DEV_DIR = PROJECT_ROOT / "dev"

# Proposals directory (project copy)
PROPOSALS_DIR = DEV_DIR / "proposals"

# Handoffs directory (project copy)
HANDOFFS_DIR = DEV_DIR / "handoffs"

# Releases directory
RELEASES_DIR = DEV_DIR / "releases"

# Config directory
CONFIG_DIR = PROJECT_ROOT / "config"


# ============================================================================
# VAULT PATHS (Obsidian Grand Nexus)
# ============================================================================

# Seedlings folder in vault
VAULT_SEEDLINGS = VAULT_ROOT / "1. P - Seedlings"

# Dev folder in vault
VAULT_DEV = VAULT_SEEDLINGS / "dev"

# Proposals directory (vault copy)
VAULT_PROPOSALS_DIR = VAULT_DEV / "proposals"

# Handoffs directory (vault copy)
VAULT_HANDOFFS_DIR = VAULT_DEV / "handoffs"

# Releases directory (vault copy)
VAULT_RELEASES_DIR = VAULT_DEV / "releases"

# Decisions directory (vault copy)
DECISIONS_DIR = VAULT_DEV / "decisions"

# Templates directory in vault
TEMPLATES_DIR = VAULT_DEV / "templates"

# Kanban board path
KANBAN_FILE = VAULT_SEEDLINGS / "Dev-KanBan.md"


# ============================================================================
# ARCHIVE PATHS
# ============================================================================

# Archives folder in vault
ARCHIVES_DIR = VAULT_ROOT / "2. P - Archive"

# Reports directory
REPORTS_DIR = DEV_DIR / "reports"


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    # Root paths
    "VAULT_ROOT",
    "PROJECT_ROOT",
    "SRC_DIR",
    # Project paths
    "DEV_DIR",
    "PROPOSALS_DIR",
    "HANDOFFS_DIR",
    "RELEASES_DIR",
    "CONFIG_DIR",
    # Vault paths
    "VAULT_SEEDLINGS",
    "VAULT_DEV",
    "VAULT_PROPOSALS_DIR",
    "VAULT_HANDOFFS_DIR",
    "VAULT_RELEASES_DIR",
    "DECISIONS_DIR",
    "TEMPLATES_DIR",
    "KANBAN_FILE",
    # Archive paths
    "ARCHIVES_DIR",
    "REPORTS_DIR",
]