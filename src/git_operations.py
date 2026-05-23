"""
Git Operations Wrapper for Phase 3+4 Workflow Execution

Provides per-proposal branch management with explicit timeouts and asyncio support.

VETO COMPLIANCE:
- T1: All subprocess.run() calls have explicit timeout= parameter
- T1: Git operations wrapped in asyncio.to_thread() for FastAPI worker safety
- G1: Per-proposal branches (feat/proposal-{id}) instead of global clean-tree check
"""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path
from typing import Optional


class GitOperationError(Exception):
    """Raised when a git operation fails."""
    def __init__(self, operation: str, details: str):
        self.operation = operation
        self.details = details
        super().__init__(f"Git operation '{operation}' failed: {details}")


# Default timeout for git operations (seconds)
DEFAULT_TIMEOUT = 10


async def _run_git_async(*args: str, timeout: int = DEFAULT_TIMEOUT) -> str:
    """
    Run a git command asynchronously with timeout.
    
    Args:
        *args: Git command arguments (e.g., "status", "--porcelain")
        timeout: Seconds before command is killed
        
    Returns:
        Command output stripped of trailing whitespace
        
    Raises:
        GitOperationError: On timeout or non-zero exit code
    """
    try:
        # Use asyncio.to_thread to prevent blocking FastAPI workers
        result = await asyncio.to_thread(
            subprocess.run,
            ["git"] + list(args),
            capture_output=True,
            text=True,
            timeout=timeout
        )
        
        if result.returncode != 0:
            raise GitOperationError(
                operation=" ".join(args),
                details=result.stderr.strip() or f"exit code {result.returncode}"
            )
        
        return result.stdout.strip()
    
    except subprocess.TimeoutExpired:
        raise GitOperationError(
            operation=" ".join(args),
            details=f"Command timed out after {timeout}s"
        )


async def ensure_branch(proposal_id: str) -> str:
    """
    Ensure a per-proposal branch exists for the given proposal.
    
    Creates feat/proposal-{id} branch if it doesn't exist.
    
    Args:
        proposal_id: The proposal ID (e.g., "DEV-20260518-XXXX")
        
    Returns:
        Branch name (feat/proposal-{id})
        
    VETO COMPLIANCE:
    - T1: Uses _run_git_async with default timeout
    - G1: Per-proposal branch naming convention
    """
    branch_name = f"feat/proposal-{proposal_id}"
    
    try:
        # Check if branch exists
        await _run_git_async("rev-parse", "--verify", branch_name)
    except GitOperationError:
        # Branch doesn't exist, create it
        try:
            # Get current branch first
            current_branch = await _run_git_async("rev-parse", "--abbrev-ref", "HEAD")
            
            # Create and checkout new branch
            await _run_git_async("checkout", "-b", branch_name)
            
            # If we were on a different branch, switch back
            if current_branch != branch_name:
                await _run_git_async("checkout", current_branch)
                
        except GitOperationError as e:
            raise GitOperationError(
                operation=f"create branch {branch_name}",
                details=f"Failed to create branch: {e.details}"
            )
    
    return branch_name


async def tag_execution_start(proposal_id: str) -> str:
    """
    Create an execution-start tag at the current commit.
    
    This tag serves as a guaranteed rollback point if execution corrupts
    the codebase.
    
    Args:
        proposal_id: The proposal ID (e.g., "DEV-20260518-XXXX")
        
    Returns:
        Tag name (exec-start/DEV-20260518-XXXX)
        
    Raises:
        GitOperationError: If working tree is not clean or tag creation fails
        
    VETO COMPLIANCE:
    - T1: Uses _run_git_async with default timeout
    - G1: Per-proposal branch required before calling this
    """
    # Check for uncommitted changes first (G1: per-proposal branch, so clean tree check is branch-local)
    status_output = await _run_git_async("status", "--porcelain")
    
    if status_output:
        raise GitOperationError(
            operation="tag_execution_start",
            details=f"Working tree has uncommitted changes. Commit or stash first:\n{status_output}"
        )
    
    tag_name = f"exec-start/{proposal_id}"
    
    try:
        # Create the tag
        await _run_git_async("tag", "-a", tag_name, "-m", f"Execution start for {proposal_id}")
        
    except GitOperationError as e:
        raise GitOperationError(
            operation=f"create tag {tag_name}",
            details=f"Failed to create tag: {e.details}"
        )
    
    return tag_name


async def rollback_to_tag(proposal_id: str, tag: str) -> None:
    """
    Rollback the working tree to a specific tag.
    
    Args:
        proposal_id: The proposal ID
        tag: The tag name to rollback to (e.g., "exec-start/DEV-20260518-XXXX")
        
    Raises:
        GitOperationError: If rollback fails
        
    VETO COMPLIANCE:
    - T1: Uses _run_git_async with default timeout
    """
    try:
        # Hard reset to the tag
        await _run_git_async("reset", "--hard", tag)
        
    except GitOperationError as e:
        raise GitOperationError(
            operation=f"rollback to {tag}",
            details=f"Failed to rollback: {e.details}"
        )


async def get_current_branch() -> str:
    """
    Get the current git branch name.
    
    Returns:
        Current branch name
        
    Raises:
        GitOperationError: If unable to determine current branch
    """
    try:
        return await _run_git_async("rev-parse", "--abbrev-ref", "HEAD")
    except GitOperationError as e:
        raise GitOperationError(
            operation="get_current_branch",
            details=f"Failed to get current branch: {e.details}"
        )


async def branch_exists(branch_name: str) -> bool:
    """
    Check if a branch exists.
    
    Args:
        branch_name: The branch name to check
        
    Returns:
        True if branch exists, False otherwise
    """
    try:
        await _run_git_async("rev-parse", "--verify", branch_name)
        return True
    except GitOperationError:
        return False


async def tag_exists(tag_name: str) -> bool:
    """
    Check if a tag exists.
    
    Args:
        tag_name: The tag name to check
        
    Returns:
        True if tag exists, False otherwise
    """
    try:
        await _run_git_async("rev-parse", "--verify", f"refs/tags/{tag_name}")
        return True
    except GitOperationError:
        return False


async def delete_tag(tag_name: str) -> None:
    """
    Delete a git tag.
    
    Args:
        tag_name: The tag name to delete
        
    Raises:
        GitOperationError: If tag deletion fails
    """
    try:
        await _run_git_async("tag", "-d", tag_name)
    except GitOperationError as e:
        raise GitOperationError(
            operation=f"delete tag {tag_name}",
            details=f"Failed to delete tag: {e.details}"
        )


async def get_commit_hash() -> str:
    """
    Get the current commit hash.
    
    Returns:
        Current commit SHA
        
    Raises:
        GitOperationError: If unable to determine commit
    """
    try:
        return await _run_git_async("rev-parse", "HEAD")
    except GitOperationError as e:
        raise GitOperationError(
            operation="get_commit_hash",
            details=f"Failed to get commit hash: {e.details}"
        )