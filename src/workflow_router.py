"""
Workflow Router (E6, ARCH-2007E0A1).

Polls a directory for new markdown files, routes them through OutputRouter,
and tracks processed files via SHA256 checksums to ensure idempotency.

Usage:
    from pathlib import Path
    from src.paths import DEV_DIR
    from src.workflow_router import WorkflowRouter
    from src.output_router import OutputRouter

    router = WorkflowRouter(
        watch_dir=DEV_DIR / "reports",
        state_file=DEV_DIR / ".workflow_state.json",
        output_router=output_router,
    )

    # Poll once to process new files
    decisions = router.poll_once()

VETO COMPLIANCE:
- E6: Idempotency via SHA256 checksums + state file
- V4: No asyncio/threading; synchronous poll_once() only
- CSTR-PREMATURE-SYNC: No locks or concurrency primitives
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import List

from src.output_router import OutputRouter


class WorkflowRouter:
    """Polls a directory for new markdown files and routes them.

    Tracks processed files via SHA256 checksums stored in a state file.
    This ensures idempotency: the same file won't be re-processed on
    subsequent poll_once() calls.

    Usage:
        router = WorkflowRouter(watch_dir, state_file, output_router)
        decisions = router.poll_once()  # Process new files only
    """

    def __init__(
        self,
        watch_dir: Path,
        state_file: Path,
        output_router: OutputRouter,
    ) -> None:
        """Initialize the WorkflowRouter.

        Args:
            watch_dir: Directory to scan for *.md files.
            state_file: JSON file to store processed file hashes.
            output_router: OutputRouter to use for routing decisions.
        """
        self._watch_dir = watch_dir
        self._state_file = state_file
        self._output_router = output_router

        # Load existing state (or initialize empty)
        self._state: dict = self._load_state()

    def _load_state(self) -> dict:
        """Load the state file, returning empty dict if not found."""
        if not self._state_file.exists():
            return {}
        try:
            with open(self._state_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            # Corrupted state file - recover by starting fresh
            return {}

    def _save_state(self) -> None:
        """Save the current state to the state file (atomic write).

        Uses ``os.replace`` rather than ``Path.rename`` because the latter
        raises ``FileExistsError`` on Windows when the destination exists.
        ``os.replace`` is atomic on both POSIX and Windows and overwrites
        an existing target.
        """
        import os

        # Ensure parent directory exists
        self._state_file.parent.mkdir(parents=True, exist_ok=True)
        temp_file = self._state_file.with_suffix(".tmp")
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(self._state, f, indent=2)
        os.replace(temp_file, self._state_file)

    def _compute_hash(self, content: str) -> str:
        """Compute SHA256 hash of content."""
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def poll_once(self) -> List[dict]:
        """Scan watch_dir for new markdown files and route them.

        For each *.md file in watch_dir:
        1. Compute SHA256 hash
        2. Skip if hash already in state (idempotency - E6)
        3. Read file content
        4. Call output_router.route(content)
        5. Call output_router.apply(decision)
        6. Record hash to state file

        Returns:
            List of RoutingDecision objects (as dicts) for files processed.
        """
        decisions: List[dict] = []

        if not self._watch_dir.exists():
            return decisions

        # Get all .md files in watch_dir (non-recursive)
        md_files = sorted(self._watch_dir.glob("*.md"))

        for md_file in md_files:
            # Skip if not a file or is the state file
            if not md_file.is_file() or md_file == self._state_file:
                continue

            # Read file content
            try:
                content = md_file.read_text(encoding="utf-8")
            except OSError:
                # Skip files that can't be read
                continue

            # Compute hash and check idempotency (E6)
            file_hash = self._compute_hash(content)
            if file_hash in self._state:
                # Already processed - skip
                continue

            # Route the content
            try:
                decision = self._output_router.route(content)

                # Apply the routing decision
                self._output_router.apply(content, decision)

                # Record the hash to state file
                self._state[file_hash] = {
                    "filename": md_file.name,
                    "rule_name": decision.rule_name,
                    "destination": decision.destination,
                    "processed_at": md_file.stat().st_mtime,
                }

                # Save state after each successful processing
                self._save_state()

                # Record decision for return value
                decisions.append(decision.model_dump())

            except Exception:
                # On any error, continue with next file
                # The error is logged via dead-letter mechanism in apply()
                continue

        return decisions