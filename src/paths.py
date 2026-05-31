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


def _validate_cos_vault_path() -> Path:
    """
    Validate the Cognitive OS Vault root path.
    
    Precedence:
        1. COS_VAULT_PATH environment variable
        2. Fallback: VAULT_ROOT.parent / "Cognitive OS"
    
    Raises:
        RuntimeError: If neither source is valid or both vaults resolve to same directory.
    
    Returns:
        Path: Validated COS vault root directory.
    """
    env_path = os.environ.get("COS_VAULT_PATH")
    if env_path:
        p = Path(env_path)
        if p.is_dir():
            # Collision guard: prevent VAULT_ROOT == COS_VAULT_ROOT
            if p == VAULT_ROOT:
                raise RuntimeError(
                    f"COS_VAULT_PATH ({p}) resolves to same directory as VAULT_ROOT. "
                    "Dual-vault mode requires two distinct paths."
                )
            return p
    
    # Fallback: create Cognitive OS folder next to Grand Nexus
    fallback = VAULT_ROOT.parent / "Cognitive OS"
    if not fallback.exists():
        fallback.mkdir(parents=True, exist_ok=True)
    if fallback.is_dir():
        return fallback
    
    raise RuntimeError(
        f"Cognitive OS vault path not found. "
        f"Set COS_VAULT_PATH env var or ensure '{fallback}' exists."
    )


# Validate at import time (fail-fast)
try:
    VAULT_ROOT = _validate_vault_path()
except Exception as e:
    raise RuntimeError(
        f"Failed to initialize vault paths: {e}. "
        f"Set OBSIDIAN_VAULT_PATH environment variable to fix."
    ) from e

try:
    COS_VAULT_ROOT = _validate_cos_vault_path()
except Exception as e:
    raise RuntimeError(
        f"Failed to initialize COS vault paths: {e}. "
        f"Set COS_VAULT_PATH environment variable to fix."
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

# AI-Help mirror in vault (cognitive-os writes council outputs here)
VAULT_AI_HELP = VAULT_ROOT / "AI-Help"
VAULT_COUNCIL_OUTPUTS = VAULT_AI_HELP / "cognitive-os"
VAULT_MEMORY_LOGS = VAULT_COUNCIL_OUTPUTS / "memory_logs"


# ============================================================================
# COS VAULT PATHS (Cognitive OS Vault - system artifacts)
# ============================================================================

# Seedlings folder in COS vault
COS_VAULT_SEEDLINGS = COS_VAULT_ROOT / "1. P - Seedlings"

# Dev folder in COS vault
COS_VAULT_DEV = COS_VAULT_SEEDLINGS / "dev"

# Proposals directory (COS vault copy)
COS_VAULT_PROPOSALS_DIR = COS_VAULT_DEV / "proposals"

# Handoffs directory (COS vault copy)
COS_VAULT_HANDOFFS_DIR = COS_VAULT_DEV / "handoffs"

# Releases directory (COS vault copy)
COS_VAULT_RELEASES_DIR = COS_VAULT_DEV / "releases"

# Decisions directory (COS vault copy)
COS_VAULT_DECISIONS_DIR = COS_VAULT_DEV / "decisions"

# Templates directory in COS vault
COS_VAULT_TEMPLATES_DIR = COS_VAULT_DEV / "templates"

# AI-Help mirror in COS vault (system-side council outputs)
COS_VAULT_AI_HELP = COS_VAULT_ROOT / "AI-Help"
COS_VAULT_COUNCIL_OUTPUTS = COS_VAULT_AI_HELP / "cognitive-os"
COS_VAULT_MEMORY_LOGS = COS_VAULT_COUNCIL_OUTPUTS / "memory_logs"


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def _ensure_cos_vault_structure() -> None:
    """
    Create required directory structure in COS vault.

    Creates:
        - AI-Help/cognitive-os/
        - 1. P - Seedlings/dev/proposals/
        - 1. P - Seedlings/dev/handoffs/
        - 1. P - Seedlings/dev/releases/
        - 1. P - Seedlings/dev/decisions/
        - 1. P - Seedlings/dev/templates/
    """
    dirs = [
        COS_VAULT_AI_HELP,
        COS_VAULT_COUNCIL_OUTPUTS,
        COS_VAULT_MEMORY_LOGS,
        COS_VAULT_PROPOSALS_DIR,
        COS_VAULT_HANDOFFS_DIR,
        COS_VAULT_RELEASES_DIR,
        COS_VAULT_DECISIONS_DIR,
        COS_VAULT_TEMPLATES_DIR,
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)


def cross_vault_link(target_vault_name: str, relative_path: str) -> str:
    """Generate an obsidian:// URI for cross-vault references.

    Args:
        target_vault_name: Name of the target Obsidian vault
        relative_path: File path relative to vault root

    Returns:
        obsidian:// URI string
    """
    return f"obsidian://open?vault={target_vault_name}&file={relative_path}"


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
    "COS_VAULT_ROOT",
    "PROJECT_ROOT",
    "SRC_DIR",
    # Project paths
    "DEV_DIR",
    "PROPOSALS_DIR",
    "HANDOFFS_DIR",
    "RELEASES_DIR",
    "CONFIG_DIR",
    # Grand Nexus vault paths
    "VAULT_SEEDLINGS",
    "VAULT_DEV",
    "VAULT_PROPOSALS_DIR",
    "VAULT_HANDOFFS_DIR",
    "VAULT_RELEASES_DIR",
    "DECISIONS_DIR",
    "TEMPLATES_DIR",
    "VAULT_AI_HELP",
    "VAULT_COUNCIL_OUTPUTS",
    "VAULT_MEMORY_LOGS",
    # COS vault paths
    "COS_VAULT_SEEDLINGS",
    "COS_VAULT_DEV",
    "COS_VAULT_PROPOSALS_DIR",
    "COS_VAULT_HANDOFFS_DIR",
    "COS_VAULT_RELEASES_DIR",
    "COS_VAULT_DECISIONS_DIR",
    "COS_VAULT_TEMPLATES_DIR",
    "COS_VAULT_AI_HELP",
    "COS_VAULT_COUNCIL_OUTPUTS",
    "COS_VAULT_MEMORY_LOGS",
    # Utility functions
    "_ensure_cos_vault_structure",
    "cross_vault_link",
    # Archive paths
    "ARCHIVES_DIR",
    "REPORTS_DIR",
]