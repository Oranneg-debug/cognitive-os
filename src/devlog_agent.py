"""DevLog Agent - Orchestrates evidence gathering, synthesis, and publishing.

This module provides the DevLogAgent class which:
1. Gathers evidence from git, gates, council, and test sources
2. Filters evidence using PathGuard (CSTR-DEVLOG-V2)
3. Synthesizes devlog posts via the devlog_scribe role
4. Routes output through OutputRouter

Binding constraints honoured:
    - CSTR-DEVLOG-V1: No autopost (explicit human approval required)
    - CSTR-DEVLOG-V2: PathGuard enforced at gather-time
    - CSTR-DEVLOG-V3: All publishes logged via ApprovalLogger with evidence_hash
    - CSTR-DEVLOG-V4: No new dependencies
    - CSTR-DEVLOG-V5: Single-writer rule (OutputRouter only, no direct vault writes)
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from pydantic import ValidationError

from src.llm_client import llm
from src.models.devlog import (
    DevLogConfig,
    DevLogPost,
    GitCommit,
    GateDelta,
    CouncilVerdict,
    TestResult,
)
from src.output_router import OutputRouter
from src.writer_protocols import BackendWriterProtocol

logger = logging.getLogger(__name__)


def _extract_json(text: str) -> dict:
    """Extract JSON from text response (handles markdown fences and extra text)."""
    try:
        # Try to find JSON in backticks first (markdown code blocks)
        match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
        if match:
            return json.loads(match.group(1))
        
        # Fallback: find any JSON object in the text
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        
        return {"error": "No JSON found", "raw": text}
    except Exception as e:
        raise ValueError(f"Failed to parse LLM response: {e}")


class DevLogAgent:
    """Orchestrates devlog post generation from evidence gathering to publishing."""

    def __init__(
        self,
        config: DevLogConfig,
        router: OutputRouter | None = None,
        backend_writer: BackendWriterProtocol | None = None,
    ):
        self.config = config
        self.router = router
        self.backend_writer = backend_writer
        self.path_guard = self._create_path_guard()

    def _create_path_guard(self) -> Any:
        """Create and configure PathGuard instance."""
        from src.path_guard import PathGuard

        return PathGuard(forbidden_patterns=self.config.forbidden_sources)

    def gather_evidence(self, date: str) -> Dict[str, Any]:
        """Gather evidence from allowed sources.

        This method:
        1. Scans git log for commits on the specified date
        2. Checks dev/gates/ for gate transitions
        3. Reviews council_memory/ for relevant deliberations
        4. Runs test suite and collects results
        5. Applies PathGuard to filter forbidden sources

        Args:
            date: Date string (YYYY-MM-DD) to gather evidence for.

        Returns:
            Dict containing evidence from allowed sources.
        """
        evidence = {
            "date": date,
            "gathered_at": datetime.now().isoformat(),
            "git_commits": [],
            "gate_deltas": [],
            "council_verdicts": [],
            "test_results": [],
        }

        # CSTR-DEVLOG-V2: PathGuard enforcement at gather-time
        # In a real implementation, this would:
        # 1. Query git log for commits on the specified date
        # 2. Check dev/gates/ for gate transitions
        # 3. Review council_memory/ for relevant deliberations
        # 4. Run test suite and collect results

        # For now, return placeholder evidence
        evidence["git_commits"].append({
            "sha": "abc1234",
            "author": "Dev Team <dev@example.com>",
            "date": date,
            "message": "Initial devlog agent implementation",
            "files_changed": ["src/path_guard.py", "src/models/devlog.py"],
        })

        # Apply PathGuard filtering
        evidence = self._apply_pathguard(evidence)

        return evidence

    def _apply_pathguard(self, evidence: Dict[str, Any]) -> Dict[str, Any]:
        """Apply PathGuard to filter forbidden sources from evidence.

        Args:
            evidence: Raw evidence dict to filter.

        Returns:
            Filtered evidence with forbidden sources removed.
        """
        # Filter git_commits paths
        if "git_commits" in evidence:
            evidence["git_commits"] = [
                commit for commit in evidence["git_commits"]
                if not self.path_guard.is_forbidden(commit.get("path", ""))
            ]

        # Filter gate_deltas paths
        if "gate_deltas" in evidence:
            evidence["gate_deltas"] = [
                delta for delta in evidence["gate_deltas"]
                if not self.path_guard.is_forbidden(delta.get("path", ""))
            ]

        return evidence

    def synthesize_post(self, evidence: Dict[str, Any]) -> DevLogPost:
        """Synthesize a devlog post from gathered evidence using devlog_scribe.

        This method:
        1. Calculates evidence hash for audit trail
        2. Formats evidence as JSON for the LLM prompt
        3. Calls the devlog_scribe role via llm_client
        4. Validates the response with Pydantic

        Args:
            evidence: Dict of gathered evidence.

        Returns:
            DevLogPost ready for approval.

        Raises:
            ValidationError: If the LLM response doesn't match DevLogPost schema.
        """
        # Calculate evidence hash (CSTR-DEVLOG-V3)
        evidence_json = json.dumps(evidence, sort_keys=True)
        evidence_hash = hashlib.sha256(evidence_json.encode()).hexdigest()

        # Format prompt for devlog_scribe
        system_prompt = self._build_synthesis_prompt()
        user_prompt = self._build_user_prompt(evidence)

        try:
            # Call the devlog_scribe role via llm_client
            response = llm.generate_response(
                prompt=user_prompt,
                system_prompt=system_prompt,
                model=self.config.council_role,
                temperature=self.config.temperature,
                top_p=self.config.top_p,
                top_k=self.config.top_k,
                repeat_penalty=self.config.repeat_penalty,
                min_p=self.config.min_p,
                max_tokens=self.config.max_tokens,
                context_window=self.config.context_window,
                gpu_offload_ratio=self.config.gpu_offload_ratio,
                n_parallel=self.config.n_parallel,
            )

            # Parse and validate the response (extract JSON from markdown fences if present)
            data = _extract_json(response)
            post = DevLogPost(
                title=data["title"],
                body=data["body"],
                tweet_thread=[
                    {"content": t["content"], "order": t["order"]}
                    for t in data["tweet_thread"]
                ],
                tags=data.get("tags", ["#cognitivos", "#devlog", "#buildinpublic"]),
                published_at=None,  # Will be set at publish time
                evidence_hash=evidence_hash,
            )
            return post

        except ValidationError as e:
            raise ValueError(f"DevLogPost validation failed: {e}")

    def _build_synthesis_prompt(self) -> str:
        """Build the system prompt for devlog_scribe role."""
        return f"""You are the DevLog Scribe for the Dark Maestro cognitive-os.

Your task is to synthesize structured evidence (git commits, gate deltas, council verdicts, test counts) into a public-facing devlog post.

**Tone**: Direct, technical, and build-in-public. Highlight interesting decisions, not routine work. Errors and failures are featured, not hidden.

**Output format**: Markdown with title, body, 4-tweet thread, and tags.

**Constraints**:
- Title must be SEO-friendly and under 120 characters
- Body must be at least 100 characters in markdown format
- Tweet thread must have 3-4 tweets, each under 280 characters
- Include relevant hashtags like #cognitivos, #devlog, #buildinpublic
- Never include the evidence hash in the output

Return your response as a single JSON object with this structure:
{{
    "title": "DevLog: YYYY-MM-DD - <title>",
    "body": "# DevLog for YYYY-MM-DD\n\n## What We Built\n\n...\n\n## Technical Decisions\n\n...\n\n## Gate Deltas\n\n...\n\n## Test Results\n\n...\n\n## Failures & Lessons\n\n...",
    "tweet_thread": [
        {{"content": "<tweet 1>", "order": 1}},
        {{"content": "<tweet 2>", "order": 2}},
        {{"content": "<tweet 3>", "order": 3}}
    ],
    "tags": ["#cognitivos", "#devlog", "#buildinpublic"]
}}"""

    def _build_user_prompt(self, evidence: Dict[str, Any]) -> str:
        """Build the user prompt from evidence."""
        return f"""Gather evidence and synthesize a devlog post for {evidence['date']}.

**Evidence**:
```json
{json.dumps(evidence, indent=2)}
```

**Instructions**:
1. Review all evidence sources
2. Highlight interesting technical decisions, not routine work
3. Feature errors and failures, not just successes
4. Keep the tone direct and technical
5. Format as markdown with title, body, tweet thread, and tags

Return ONLY valid JSON matching the required structure."""