"""
Test module for git snapshot operations.

This is an alias/wrapper module that re-exports tests from
test_git_operations.py to satisfy the handoff naming requirement
for test_git_snapshot.py.

The actual implementation is in git_operations.py, and the tests
are in test_git_operations.py. This file exists purely for naming
compatibility with the ARCH-20260522-161800-F10FE0E1 handoff.

VETO COMPLIANCE:
- B2: test_git_snapshot.py exists (alias to test_git_operations.py)
"""

# Re-export all public symbols from test_git_operations
from tests.test_git_operations import *  # noqa: F401, F403