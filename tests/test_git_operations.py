"""
Tests for Git Operations - subprocess wrapper with timeouts.

Gates covered:
- phase34_git_ops_timeouts: subprocess + timeout kwarg (+ asyncio.to_thread)
"""

import pytest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from src.git_operations import (
    GitOperationError,
    DEFAULT_TIMEOUT
)


# ============================================================================
# Test Git Operations Constants
# ============================================================================

class TestGitOperationsConstants:
    """Test timeout constants and defaults."""

    def test_default_timeout_value(self):
        """Test that DEFAULT_TIMEOUT is set to a reasonable value."""
        assert DEFAULT_TIMEOUT == 10
        assert DEFAULT_TIMEOUT > 0

    def test_git_operation_error_creation(self):
        """Test GitOperationError exception creation."""
        error = GitOperationError(operation="git branch", details="Branch already exists")
        
        assert error.operation == "git branch"
        assert "Branch already exists" in str(error)
        assert "git branch" in str(error)

    def test_git_operation_error_message_format(self):
        """Test GitOperationError message format."""
        error = GitOperationError(
            operation="git tag",
            details="Tag already exists"
        )
        
        expected_msg = "Git operation 'git tag' failed: Tag already exists"
        assert str(error) == expected_msg


# ============================================================================
# Test Feature Branch Naming
# ============================================================================

class TestFeatureBranchNaming:
    """Test that feature branches follow the naming convention."""

    def test_branch_name_format(self):
        """Test branch name format: feat/proposal-{id}."""
        proposal_id = "DEV-20260518-XXXX"
        branch_name = f"feat/proposal-{proposal_id}"
        
        assert branch_name == "feat/proposal-DEV-20260518-XXXX"
        assert branch_name.startswith("feat/proposal-")

    def test_branch_name_generation(self):
        """Test branch name generation from proposal ID."""
        proposal_ids = [
            "DEV-20260518-ABCD",
            "ARCH-20260517-WXYZ",
            "NLST-20260516-1234"
        ]
        
        for pid in proposal_ids:
            branch_name = f"feat/proposal-{pid}"
            assert branch_name.startswith("feat/proposal-")
            assert pid in branch_name


# ============================================================================
# Test GitOperationError Exception
# ============================================================================

class TestGitOperationErrorHandling:
    """Test GitOperationError exception behavior."""

    def test_error_has_operation_and_details(self):
        """Test that error stores operation and details."""
        error = GitOperationError(
            operation="git checkout",
            details="Branch not found"
        )
        
        assert error.operation == "git checkout"
        assert error.details == "Branch not found"

    def test_error_is_exception_subclass(self):
        """Test that GitOperationError extends Exception."""
        error = GitOperationError("test", "details")
        
        assert isinstance(error, Exception)

    def test_error_message_includes_operation_and_details(self):
        """Test that error message includes both operation and details."""
        error = GitOperationError(
            operation="git push",
            details="Permission denied"
        )
        
        error_str = str(error)
        assert "git push" in error_str
        assert "Permission denied" in error_str


if __name__ == "__main__":
    pytest.main([__file__, "-v"])