"""
Output Router (E1, E3, E4, E5, E7, T1, T2, ARCH-2007E0A1).

Routes council syntheses and analyst reports to deterministic destinations
based on YAML-defined rules. Enforces single-writer boundaries and
structured error handling.

Usage:
    from src.output_router import OutputRouter
    from src.writer_protocols import BackendWriterProtocol
    from src.paths import DEV_DIR

    router = OutputRouter(
        rules_path=Path("config/routing_rules.yaml"),
        backend_writer=MyBackendWriter(),
        dead_letter_dir=DEV_DIR / "failed_routings",
    )
    decision = router.route(synthesis_text)
    path = router.apply(synthesis_text, decision)

VETO COMPLIANCE:
- E1: catch-all route prevents silent data loss
- E3: Pydantic validation at construction (fail-fast)
- E4: runtime single-writer guard (assert_no_vault_writer)
- E5: dead-letter directory for write failures
- E7: regex word boundaries via RoutingMarker
- T1: BackendWriterProtocol only (no vault writers)
- T2: fence-stripping via strip_fences() before marker matching
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from src.markdown_fence_parser import strip_fences
from src.routing_rules_schema import RoutingDecision, RoutingRulesFile, load_routing_rules
from src.writer_protocols import BackendWriterProtocol, SingleWriterRuleViolation, assert_no_vault_writer

from datetime import datetime

# Import paths constants for destination resolution
from src.paths import (
    ARCHIVES_DIR,
    DECISIONS_DIR,
    HANDOFFS_DIR,
    PROPOSALS_DIR,
    REPORTS_DIR,
    DEV_DIR,
    # COS vault paths
    COS_VAULT_PROPOSALS_DIR,
    COS_VAULT_HANDOFFS_DIR,
    COS_VAULT_DECISIONS_DIR,
    COS_VAULT_RELEASES_DIR,
)


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#  PATH RESOLUTION (for destination buckets)
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•


def resolve_destination_path(bucket: str, dead_letter_dir: Path) -> Path:
    """Resolve a destination bucket to a filesystem path.

    Args:
        bucket: One of the allowed destinations from RoutingRule.
        dead_letter_dir: The directory for failed routings (E5).

    Returns:
        The absolute path for the destination.

    Raises:
        ValueError: If bucket is not recognized.
    """
    path_map = {
        "proposals": PROPOSALS_DIR,
        "decisions": DECISIONS_DIR,
        "handoffs": HANDOFFS_DIR,
        "reports": REPORTS_DIR,
        "archives": ARCHIVES_DIR,
        "failed_routings": dead_letter_dir,
        # System-side vault destinations (COS vault)
        "proposals_vault": COS_VAULT_PROPOSALS_DIR,
        "handoffs_vault": COS_VAULT_HANDOFFS_DIR,
        "decisions_vault": COS_VAULT_DECISIONS_DIR,
        "releases_vault": COS_VAULT_RELEASES_DIR,
    }
    if bucket not in path_map:
        raise ValueError(f"Unknown destination bucket: {bucket!r}")
    return path_map[bucket]


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#  OUTPUT ROUTER
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•


class OutputRouter:
    """Deterministic content router based on YAML-defined rules.

    Routes council syntheses and analyst reports to the correct destination
    based on markers found in the content. The routing is:
    - Deterministic (same input always produces same output)
    - Fail-fast (malformed rules raise at construction)
    - Single-writer (only backend writes, no vault writes)
    - Resilient (failed writes go to dead-letter directory)

    Usage:
        router = OutputRouter(
            rules_path=Path("config/routing_rules.yaml"),
            backend_writer=backend,
            dead_letter_dir=DEV_DIR / "failed_routings",
        )
        decision = router.route(content)
        path = router.apply(content, decision)
    """

    def __init__(
        self,
        rules_path: Path,
        backend_writer: BackendWriterProtocol,
        dead_letter_dir: Path,
    ) -> None:
        """Initialize the OutputRouter.

        Args:
            rules_path: Path to the YAML routing rules file.
            backend_writer: Writer that targets project paths (NOT vault).
            dead_letter_dir: Directory for failed routing attempts.

        Raises:
            SingleWriterRuleViolation: If backend_writer is a vault writer.
            pydantic.ValidationError: If rules file is malformed (E3).
            FileNotFoundError: If rules file does not exist.
        """
        # E4/T1 runtime guard: reject vault writers immediately
        assert_no_vault_writer(backend_writer)

        # E3 fail-fast: validate rules at construction
        self._rules: RoutingRulesFile = load_routing_rules(rules_path)

        self._backend_writer = backend_writer
        self._dead_letter_dir = dead_letter_dir

        # Precompile regex patterns for efficiency (E7 word boundaries)
        self._compiled_patterns: List[re.Pattern[str]] = []
        for rule in self._rules.rules:
            for marker in rule.markers:
                self._compiled_patterns.append(marker.to_regex())

    def route(self, content: str) -> RoutingDecision:
        """Route content to its destination based on markers.

        1. Strips fenced code blocks from content (T2)
        2. Matches markers against rules in declaration order
        3. Returns RoutingDecision with rule_name, destination, severity

        Args:
            content: The markdown content to route.

        Returns:
            A RoutingDecision with:
                - rule_name: Which rule fired
                - destination: Where to write (proposals/decisions/etc.)
                - workflow_phase: Phase to stamp on artifact
                - severity: Assigned severity (may be None)
                - matched_markers: List of marker patterns that matched
                - context: Additional context bag
        """
        # T2: Strip fenced code blocks before marker matching
        clean_content = strip_fences(content)

        # Iterate rules in declaration order; first match wins
        matched_markers: List[str] = []

        for rule in self._rules.rules:
            if rule.is_catchall:
                # Catch-all fires only if no other rule matched
                continue

            # Check if any marker in this rule matches
            for marker in rule.markers:
                pattern = marker.to_regex()
                if pattern.search(clean_content):
                    matched_markers.append(marker.pattern)
                    # Build decision
                    return RoutingDecision(
                        rule_name=rule.name,
                        destination=rule.destination,
                        workflow_phase=rule.workflow_phase,
                        severity=rule.severity,
                        matched_markers=matched_markers,
                        context={"severity": rule.severity} if rule.severity else {},
                    )

        # E1: Fall back to catch-all rule if nothing matched
        catchall_rule = next(r for r in self._rules.rules if r.is_catchall)
        return RoutingDecision(
            rule_name=catchall_rule.name,
            destination=catchall_rule.destination,
            workflow_phase=catchall_rule.workflow_phase,
            severity=catchall_rule.severity,
            matched_markers=[],
            context={"severity": catchall_rule.severity} if catchall_rule.severity else {},
        )

    def apply(self, content: str, decision: RoutingDecision) -> Path:
        """Write content to the destination specified in the decision.

        Args:
            content: The content to write.
            decision: The RoutingDecision from route().

        Returns:
            The absolute path where content was written.

        Raises:
            OSError: If the write fails and cannot be rerouted to dead-letter.
        """
        try:
            destination_path = resolve_destination_path(
                decision.destination, self._dead_letter_dir
            )
            # Generate a unique filename based on rule and timestamp
            timestamp = datetime.now().strftime("%Y%m%dT%H%M%S_%f")
            filename = f"{decision.rule_name}_{timestamp}.md"
            full_path = destination_path / filename

            # Write via backend writer
            result_path = self._backend_writer.write(full_path, content)
            return result_path

        except Exception as e:
            # E5: Reroute to dead-letter on failure
            return self._handle_failure(content, decision, e)

    def _handle_failure(self, content: str, decision: RoutingDecision, error: Exception) -> Path:
        """Handle a write failure by rerouting to dead-letter directory.

        Creates:
            - <rule_name>_<timestamp>.failed.md: original content
            - <rule_name>_<timestamp>.failed.md.sidecar: exception info

        Args:
            content: The content that failed to route.
            decision: The RoutingDecision that was attempted.
            error: The exception that occurred.

        Returns:
            The path to the failed routing file in dead-letter dir.
        """
        # Ensure dead-letter directory exists
        self._dead_letter_dir.mkdir(parents=True, exist_ok=True)

        # Create sidecar with exception info
        sidecar_content = json.dumps(
            {
                "original_destination": decision.destination,
                "rule_name": decision.rule_name,
                "error_type": type(error).__name__,
                "error_message": str(error),
            },
            indent=2,
        )

        # Write files to dead-letter directory. Timestamp avoids collision
        # when multiple failures hit the same rule.
        timestamp = datetime.now().strftime("%Y%m%dT%H%M%S_%f")
        base_name = f"{decision.rule_name}_{timestamp}"

        failed_path = self._dead_letter_dir / f"{base_name}.failed.md"
        sidecar_path = self._dead_letter_dir / f"{base_name}.sidecar.json"

        # Write DIRECTLY to disk — do NOT use self._backend_writer, that's
        # the writer that just failed. This is the whole point of E5: the
        # dead letter must be writable even when the backend is broken.
        failed_path.write_text(content, encoding="utf-8")
        sidecar_path.write_text(sidecar_content, encoding="utf-8")

        return failed_path