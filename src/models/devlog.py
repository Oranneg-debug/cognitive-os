"""DevLog data models for DevLog Agent (Section A1).

This module provides Pydantic models for:
- Evidence gathering (git commits, gate deltas, council verdicts, test results)
- Synthesized devlog posts
- Publishing output formats

Binding constraints honoured:
    - CSTR-DEVLOG-V4: No new dependencies (Pydantic v2 only).
    - CSTR-DEVLOG-V3: All publishes logged via ApprovalLogger with evidence_hash.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


# ════════════════════════════════════════════════════════════════════
#  Evidence Models
# ════════════════════════════════════════════════════════════════════


class GitCommit(BaseModel):
    """A single git commit from the devlog evidence base."""

    model_config = ConfigDict(frozen=True)

    sha: str = Field(..., description="Full commit hash.")
    short_sha: str = Field(..., description="Short 7-char commit hash.")
    author: str = Field(..., description="Author name and email.")
    date: datetime = Field(..., description="Commit timestamp.")
    message: str = Field(..., description="Commit message body.")
    files_changed: List[str] = Field(default_factory=list, description="Changed files.")


class GateDelta(BaseModel):
    """Gate progress for a proposal (beta → alpha → final)."""

    model_config = ConfigDict(frozen=True)

    proposal_id: str = Field(..., description="Proposal identifier, e.g. 'ARCH-2026...'.")
    stage: str = Field(..., description="Stage name: 'beta', 'alpha', or 'final'.")
    passed_at: datetime = Field(..., description="When this gate was passed.")
    approvers: List[str] = Field(default_factory=list, description="Approving role names.")


class CouncilVerdict(BaseModel):
    """A council decision with rationale."""

    model_config = ConfigDict(frozen=True)

    proposal_id: str = Field(..., description="Proposal identifier.")
    stage: str = Field(..., description="Stage name: 'beta', 'alpha', or 'final'.")
    timestamp: datetime = Field(..., description="When the verdict was rendered.")
    outcome: str = Field(..., description="'APPROVED' or 'REJECTED'.")
    rationale: str = Field(..., description="Verdict explanation.")
    voting_roles: List[str] = Field(default_factory=list, description="Voting roles.")


class TestResult(BaseModel):
    """Test suite execution result."""

    model_config = ConfigDict(frozen=True)

    test_file: str = Field(..., description="Path to the test file.")
    passed: int = Field(..., description="Number of passed tests.")
    failed: int = Field(..., description="Number of failed tests.")
    skipped: int = Field(default=0, description="Number of skipped tests.")
    total: int = Field(..., description="Total tests in the file.")


# ════════════════════════════════════════════════════════════════════
#  DevLog Post Models
# ════════════════════════════════════════════════════════════════════


class Tweet(BaseModel):
    """A single tweet in a devlog's tweet thread."""

    model_config = ConfigDict(frozen=True)

    content: str = Field(..., min_length=1, max_length=280, description="Tweet text.")
    order: int = Field(..., ge=1, le=4, description="Position in the thread (1-4).")


class DevLogPost(BaseModel):
    """A complete devlog post ready for publishing."""

    model_config = ConfigDict(frozen=False)

    title: str = Field(
        ...,
        min_length=5,
        max_length=120,
        description="Post title (SEO-friendly, <120 chars).",
    )
    body: str = Field(
        ...,
        min_length=100,
        description="Main post content in markdown format.",
    )
    tweet_thread: List[Tweet] = Field(
        ...,
        min_length=3,
        max_length=4,
        description="Twitter/X thread (3-4 tweets).",
    )
    tags: List[str] = Field(
        default_factory=lambda: ["#cognitivos", "#devlog", "#buildinpublic"],
        description="Hashtags for social distribution.",
    )
    published_at: Optional[datetime] = Field(
        None, description="Timestamp when this post was published."
    )
    evidence_hash: str = Field(
        ..., description="SHA256 hash of evidence used to generate this post."
    )

    def model_dump_json_for_publish(self) -> str:
        """Return JSON payload for publishing API (excludes published_at)."""
        return self.model_dump_json(exclude={"published_at"})


# ════════════════════════════════════════════════════════════════════
#  Publishing Output Models
# ════════════════════════════════════════════════════════════════════


class GitHubPagesPost(BaseModel):
    """DevLog post formatted for GitHub Pages (/_posts/)."""

    model_config = ConfigDict(frozen=False)

    filename: str = Field(..., description="Jekyll filename: YYYY-MM-DD-title.md")
    frontmatter: str = Field(..., description="YAML frontmatter block.")
    body: str = Field(..., description="Markdown post body.")


class DevToPost(BaseModel):
    """DevLog post formatted for dev.to API."""

    model_config = ConfigDict(frozen=False)

    title: str = Field(..., description="Post title.")
    body_markdown: str = Field(..., description="Full markdown content.")
    tags: List[str] = Field(default_factory=list, description="Article tags.")
    series: Optional[str] = Field(None, description="Series name if applicable.")
    main_image: Optional[str] = Field(None, description="Featured image URL.")


# ════════════════════════════════════════════════════════════════════
#  Config Model
# ════════════════════════════════════════════════════════════════════


class DevLogConfig(BaseModel):
    """Configuration for DevLog Agent from config/devlog_config.yaml."""

    model_config = ConfigDict(frozen=False)

    allowed_sources: List[str] = Field(
        default_factory=lambda: [
            "git/commits",
            "dev/gates",
            "council_memory",
            "tests",
        ],
        description="Allowed evidence source directories.",
    )
    forbidden_sources: List[str] = Field(
        default_factory=lambda: ["Z-Inbox/", "mock_vault/", ".private", "_private"],
        description="Forbidden source patterns.",
    )
    cadence: str = Field(
        default="daily",
        description="Publishing cadence: 'daily', 'weekly', or 'manual'.",
    )
    council_role: str = Field(
        default="devlog_scribe",
        description="Role name for the devlog scribe in master_config.md.",
    )
    platforms: List[str] = Field(
        default_factory=lambda: ["github_pages", "dev_to"],
        description="Target publishing platforms.",
    )
    temperature: float = Field(
        default=0.7,
        description="LLM temperature for synthesis.",
    )
    top_p: float = Field(
        default=0.9,
        description="LLM top_p for synthesis.",
    )
    top_k: int = Field(
        default=40,
        description="LLM top_k for synthesis.",
    )
    repeat_penalty: float = Field(
        default=1.1,
        description="LLM repeat penalty for synthesis.",
    )
    min_p: float = Field(
        default=0.0,
        description="LLM min_p for synthesis.",
    )
    max_tokens: int = Field(
        default=8192,
        description="LLM max tokens for synthesis.",
    )
    context_window: int = Field(
        default=32768,
        description="LLM context window for synthesis.",
    )
    gpu_offload_ratio: Optional[str] = Field(
        default="max",
        description="LLM GPU offload ratio for synthesis.",
    )
    n_parallel: Optional[int] = Field(
        default=1,
        description="LLM n_parallel for synthesis.",
    )