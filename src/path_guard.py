"""PathGuard module for enforcing forbidden source restrictions.

This module provides PathGuard to ensure DevLog Agent only gathers evidence
from allowed sources (git, gate deltas, council verdicts, test results) and
excludes forbidden directories like Z-Inbox/, mock_vault/, and private files.
"""
from pathlib import Path
from typing import List


# Forbidden source patterns
FORBIDDEN_PATTERNS: List[str] = [
    "Z-Inbox/",
    "mock_vault/",
    ".private",
    "_private",
]

# Allowed evidence sources
ALLOWED_SOURCES: List[str] = [
    "git/",
    "dev/gates/",
    "council_memory/",
    "tests/",
]


class PathGuard:
    """Enforces forbidden source restrictions for DevLog gathering."""

    def __init__(self, forbidden_patterns: List[str] | None = None):
        self.forbidden_patterns = forbidden_patterns or FORBIDDEN_PATTERNS

    def is_forbidden(self, path_str: str) -> bool:
        """Check if a path matches any forbidden pattern.

        Args:
            path_str: The path string to check (relative or absolute).

        Returns:
            True if the path is forbidden, False otherwise.
        """
        path_lower = path_str.lower()
        return any(pattern.lower() in path_lower for pattern in self.forbidden_patterns)

    def get_allowed_sources(self) -> List[str]:
        """Return list of allowed evidence source patterns."""
        return ALLOWED_SOURCES.copy()

    def filter_paths(self, paths: List[Path]) -> List[Path]:
        """Filter out forbidden paths from a list.

        Args:
            paths: List of Path objects to filter.

        Returns:
            List of allowed Path objects.
        """
        return [p for p in paths if not self.is_forbidden(str(p))]


# Global instance for convenience
_default_guard: PathGuard | None = None


def get_default_guard() -> PathGuard:
    """Get the global default PathGuard instance."""
    global _default_guard
    if _default_guard is None:
        _default_guard = PathGuard()
    return _default_guard


def is_forbidden(path_str: str) -> bool:
    """Convenience function to check if a path is forbidden.

    Args:
        path_str: The path string to check.

    Returns:
        True if the path is forbidden, False otherwise.
    """
    return get_default_guard().is_forbidden(path_str)


def filter_paths(paths: List[Path]) -> List[Path]:
    """Convenience function to filter forbidden paths.

    Args:
        paths: List of Path objects to filter.

    Returns:
        List of allowed Path objects.
    """
    return get_default_guard().filter_paths(paths)