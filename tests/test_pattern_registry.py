"""Test pattern registry completeness against SentryRouter patterns.

This test ensures that every pattern defined in SentryRouter has a corresponding
executor registered in PATTERN_REGISTRY.
"""
import pytest

from src.sentry_router import SentryRouter
from src.patterns import PATTERN_REGISTRY


def test_pattern_registry_covers_sentry():
    """Verify all SentryRouter patterns are implemented in registry."""
    sentry = SentryRouter()
    expected_patterns = set(sentry.patterns.keys())
    registered_patterns = set(PATTERN_REGISTRY.keys())
    
    # All SentryRouter patterns should have executors
    assert expected_patterns.issubset(registered_patterns), (
        f"Missing patterns: {expected_patterns - registered_patterns}. "
        f"SentryRouter has {len(expected_patterns)} patterns, registry has {len(registered_patterns)}."
    )


def test_pattern_registry_has_at_least_sentry_count():
    """Verify PATTERN_REGISTRY contains all SentryRouter patterns (8+)."""
    sentry = SentryRouter()
    expected_patterns = set(sentry.patterns.keys())
    registered_patterns = set(PATTERN_REGISTRY.keys())
    
    # All SentryRouter patterns should be present
    missing = expected_patterns - registered_patterns
    assert not missing, f"Missing patterns in PATTERN_REGISTRY: {missing}"
    
    # Should have at least as many as SentryRouter (8)
    assert len(registered_patterns) >= len(expected_patterns), (
        f"Expected at least {len(expected_patterns)} patterns, got {len(registered_patterns)}."
    )