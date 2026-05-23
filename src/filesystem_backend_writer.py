"""
Filesystem Backend Writer (A1, ARCH-2007E0A1).

Minimal concrete implementation of BackendWriterProtocol that writes
to project paths (dev/proposals/, dev/decisions/, etc.) using atomic
temp + rename semantics.

Usage:
    from pathlib import Path
    from src.filesystem_backend_writer import FilesystemBackendWriter

    writer = FilesystemBackendWriter(
        base_dir=Path("dev"),
        dead_letter_dir=Path("dev/failed_routings")
    )
    path = writer.write(Path("proposals/report.md"), "content")
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Optional

from src.writer_protocols import BackendWriterProtocol


class FilesystemBackendWriter(BackendWriterProtocol):
    """Minimal filesystem backend writer for OutputRouter.

    Implements atomic writes using temp file + rename to ensure
    no partial writes are visible to readers.

    VETO COMPLIANCE:
    - B4: Atomic dual-write pattern (temp + rename)
    - V9: Explicit exceptions raised, never silently swallowed
    """

    def __init__(
        self,
        base_dir: Path,
        dead_letter_dir: Optional[Path] = None,
    ) -> None:
        """Initialize the filesystem backend writer.

        Args:
            base_dir: Base directory for project files (typically dev/).
            dead_letter_dir: Optional directory for failed routings.
        """
        self.base_dir = base_dir.resolve()
        self.dead_letter_dir = (
            dead_letter_dir.resolve() if dead_letter_dir else None
        )

        # Ensure base directory exists
        self.base_dir.mkdir(parents=True, exist_ok=True)

        if self.dead_letter_dir is not None:
            self.dead_letter_dir.mkdir(parents=True, exist_ok=True)

    def write(self, destination: Path, content: str) -> Path:
        """Persist ``content`` at ``destination`` using atomic write.

        The destination path is relative to ``base_dir``. For example,
        if ``base_dir`` is ``dev/`` and ``destination`` is ``proposals/report.md``,
        the file will be written to ``dev/proposals/report.md``.

        Args:
            destination: Relative path within base_dir (e.g., "proposals/report.md").
            content: The text content to write.

        Returns:
            The absolute path where content was written.

        Raises:
            OSError: If the write fails.
        """
        # Construct full path
        full_path = self.base_dir / destination

        # Ensure parent directory exists
        full_path.parent.mkdir(parents=True, exist_ok=True)

        # Atomic write: write to temp file, then rename
        # This ensures no partial writes are visible to readers
        fd: Optional[int] = None
        temp_path: Optional[Path] = None

        try:
            # Create temp file in the same directory for atomic rename
            fd, temp_path = tempfile.mkstemp(
                dir=full_path.parent,
                prefix=".tmp_",
                suffix=".md"
            )

            # Write content to temp file
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)

            # Atomic rename
            os.rename(temp_path, full_path)

            return full_path

        except Exception as e:
            # Clean up temp file on failure
            if temp_path is not None and temp_path.exists():
                try:
                    temp_path.unlink()
                except OSError:
                    pass  # Best-effort cleanup

            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass

            # Re-raise with explicit error (V9: no silent swallowing)
            raise OSError(
                f"Failed to write to {full_path}: {e}"
            ) from e