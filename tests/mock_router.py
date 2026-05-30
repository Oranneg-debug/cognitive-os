"""MockRouter for testing DevLog Agent in isolation (Section D1).

This mock router simulates OutputRouter behavior for unit tests,
allowing DevLog Agent tests to run without requiring full infrastructure.
"""
from pathlib import Path
from typing import List, Any

from src.writer_protocols import BackendWriterProtocol


class MockRouter:
    """Mock router that simulates OutputRouter for testing.

    This mock:
    - Tracks all write attempts
    - Allows configuration of success/failure behavior
    - Supports path validation without actual file writes
    """

    def __init__(self, allow_vault_writes: bool = False):
        self.allow_vault_writes = allow_vault_writes
        self.write_attempts: List[dict] = []
        self.fail_next_write = False
        self.next_failure_message = "Simulated write failure"
        self.last_destination: Path | None = None
        self.last_content: str | None = None

    def write(self, destination: Path, content: str) -> Path:
        """Mock write method that records attempts without writing.

        Args:
            destination: The path where content would be written.
            content: The content to write.

        Returns:
            The destination path (same as input).

        Raises:
            OSError: If fail_next_write is True.
        """
        self.write_attempts.append({
            "destination": str(destination),
            "content_length": len(content),
            "timestamp": str(Path.cwd()),
        })

        if self.fail_next_write:
            self.fail_next_write = False
            raise OSError(self.next_failure_message)

        self.last_destination = destination
        self.last_content = content
        return destination

    def configure_fail_next(self, message: str = "Simulated write failure") -> None:
        """Configure the next write to fail."""
        self.fail_next_write = True
        self.next_failure_message = message

    def reset(self) -> None:
        """Reset all recorded state."""
        self.write_attempts.clear()
        self.fail_next_write = False
        self.last_destination = None
        self.last_content = None

    def get_last_write(self) -> dict | None:
        """Get the last write attempt."""
        if not self.write_attempts:
            return None
        return self.write_attempts[-1]