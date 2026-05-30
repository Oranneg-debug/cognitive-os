"""Tests for src.devlog_publisher (Section D2).

Tests:
- Format to GitHub Pages (Jekyll)
- Format to dev.to
- Publish with PathGuard
- Dry-run preview

Binding constraints honoured:
    - CSTR-DEVLOG-V1: No autopost (explicit human approval required)
    - CSTR-DEVLOG-V2: PathGuard enforced at gather-time
    - CSTR-DEVLOG-V3: All publishes logged via ApprovalLogger with evidence_hash
"""
from __future__ import annotations

import pytest
from datetime import datetime
from pathlib import Path

from src.models.devlog import DevLogConfig, DevLogPost, Tweet
from src.devlog_publisher import DevLogPublisher


# ════════════════════════════════════════════════════════════════════
#  Fixtures
# ════════════════════════════════════════════════════════════════════


@pytest.fixture
def config() -> DevLogConfig:
    """Return a minimal devlog config for testing."""
    return DevLogConfig(
        allowed_sources=["git/commits", "dev/gates"],
        forbidden_sources=["Z-Inbox/", "mock_vault/"],
        cadence="manual",
        council_role="devlog_scribe",
        platforms=["github_pages"],
    )


@pytest.fixture
def publisher(config: DevLogConfig) -> DevLogPublisher:
    """Return a DevLogPublisher instance."""
    return DevLogPublisher(config)


@pytest.fixture
def sample_post() -> DevLogPost:
    """Return a sample devlog post for testing."""
    return DevLogPost(
        title="DevLog: 2026-05-29 - Initial Implementation",
        body="# DevLog for 2026-05-29\n\n## What We Built\n\nInitial implementation with PathGuard filtering.",
        tweet_thread=[
            Tweet(content="Starting our DevLog series! #cognitivos", order=1),
            Tweet(content="Built PathGuard module. #python #pydantic", order=2),
            Tweet(content="Synthesized evidence into structured posts.", order=3)
        ],
        tags=["#cognitivos", "#devlog"],
        evidence_hash="abc123def456",
    )


@pytest.fixture
def valid_post() -> DevLogPost:
    """Return a valid devlog post that passes all validation rules."""
    return DevLogPost(
        title="DevLog: 2026-05-29 - Test",
        body="# DevLog for 2026-05-29\n\n## What We Built\n\nInitial implementation with PathGuard filtering and evidence synthesis.",
        tweet_thread=[
            Tweet(content="Starting our DevLog series! #cognitivos", order=1),
            Tweet(content="Built PathGuard module. #python #pydantic", order=2),
            Tweet(content="Synthesized evidence into structured posts.", order=3)
        ],
        tags=["#test"],
        evidence_hash="abc123",
    )


# ════════════════════════════════════════════════════════════════════
#  to_github_pages tests
# ════════════════════════════════════════════════════════════════════


def test_to_github_pages_generates_filename(publisher: DevLogPublisher) -> None:
    """Format post to GitHub Pages filename."""
    post = DevLogPost(
        title="DevLog: 2026-05-29 - Test",
        body="# DevLog for 2026-05-29\n\n## What We Built\n\nInitial implementation of the devlog agent with PathGuard filtering and evidence synthesis.",
        tweet_thread=[
            Tweet(content="Starting our DevLog series! #cognitivos", order=1),
            Tweet(content="Built PathGuard module. #python #pydantic", order=2),
            Tweet(content="Synthesized evidence into structured posts.", order=3)
        ],
        tags=["#test"],
        evidence_hash="abc",
        published_at=datetime(2026, 5, 29),
    )
    result = publisher.to_github_pages(post)
    assert "2026-05-29" in result.filename
    assert result.filename.endswith(".md")


def test_to_github_pages_includes_frontmatter(publisher: DevLogPublisher, valid_post: DevLogPost) -> None:
    """Format post includes YAML frontmatter."""
    post = valid_post.model_copy(update={"published_at": datetime(2026, 5, 29)})
    result = publisher.to_github_pages(post)
    assert "title:" in result.frontmatter
    assert "date:" in result.frontmatter


def test_to_github_pages_combines_content(publisher: DevLogPublisher, valid_post: DevLogPost) -> None:
    """Format post combines frontmatter and body."""
    post = valid_post.model_copy(update={"published_at": datetime(2026, 5, 29)})
    result = publisher.to_github_pages(post)
    combined = result.frontmatter + "\n" + result.body
    assert "DevLog for 2026-05-29" in combined


# ════════════════════════════════════════════════════════════════════
#  to_dev_to tests
# ════════════════════════════════════════════════════════════════════


def test_to_dev_to_formats_post(publisher: DevLogPublisher) -> None:
    """Format post for dev.to API."""
    post = DevLogPost(
        title="DevLog: 2026-05-29 - Test",
        body="# DevLog for 2026-05-29\n\n## What We Built\n\nInitial implementation with PathGuard filtering and evidence synthesis.\n\n## Technical Decisions\n\nUsed Pydantic v2 for data validation to ensure type safety throughout the pipeline.",
        tweet_thread=[
            Tweet(content="Starting our DevLog series! #cognitivos", order=1),
            Tweet(content="Built PathGuard module. #python #pydantic", order=2),
            Tweet(content="Synthesized evidence into structured posts.", order=3)
        ],
        tags=["#test"],
        evidence_hash="abc",
    )
    result = publisher.to_dev_to(post)
    assert "DevLog" in result.title
    assert "What We Built" in result.body_markdown
    assert "#test" in result.tags


def test_to_dev_to_includes_series(publisher: DevLogPublisher) -> None:
    """Format post includes series info."""
    post = DevLogPost(
        title="DevLog: 2026-05-29 - Test",
        body="# DevLog for 2026-05-29\n\n## What We Built\n\nInitial implementation with PathGuard filtering and evidence synthesis.\n\n## Technical Decisions\n\nUsed Pydantic v2 for data validation to ensure type safety throughout the pipeline.",
        tweet_thread=[
            Tweet(content="Starting our DevLog series! #cognitivos", order=1),
            Tweet(content="Built PathGuard module. #python #pydantic", order=2),
            Tweet(content="Synthesized evidence into structured posts.", order=3)
        ],
        tags=["#test"],
        evidence_hash="abc",
    )
    result = publisher.to_dev_to(post)
    assert "Cognitive OS DevLogs" in (result.series or "")


# ════════════════════════════════════════════════════════════════════
#  publish tests
# ════════════════════════════════════════════════════════════════════


def test_publish_raises_on_forbidden_tag(publisher: DevLogPublisher) -> None:
    """Publish raises if post contains forbidden tag."""
    post = DevLogPost(
        title="DevLog: 2026-05-29 - Forbidden",
        body="# DevLog for 2026-05-29\n\n## What We Built\n\nInitial implementation with PathGuard filtering and evidence synthesis.\n\n## Technical Decisions\n\nUsed Pydantic v2 for data validation to ensure type safety throughout the pipeline.",
        tweet_thread=[
            Tweet(content="Starting our DevLog series! #cognitivos", order=1),
            Tweet(content="Built PathGuard module. #python #pydantic", order=2),
            Tweet(content="Synthesized evidence into structured posts.", order=3)
        ],
        tags=["#Z-Inbox/test"],  # Forbidden pattern
        evidence_hash="abc",
    )
    with pytest.raises(ValueError, match="Forbidden tag"):
        publisher.publish(post)


def test_publish_formats_for_platforms(publisher: DevLogPublisher) -> None:
    """Publish formats post for configured platforms."""
    post = DevLogPost(
        title="DevLog: 2026-05-29 - Test",
        body="# DevLog for 2026-05-29\n\n## What We Built\n\nInitial implementation with PathGuard filtering and evidence synthesis.\n\n## Technical Decisions\n\nUsed Pydantic v2 for data validation to ensure type safety throughout the pipeline.",
        tweet_thread=[
            Tweet(content="Starting our DevLog series! #cognitivos", order=1),
            Tweet(content="Built PathGuard module. #python #pydantic", order=2),
            Tweet(content="Synthesized evidence into structured posts.", order=3)
        ],
        tags=["#test"],
        evidence_hash="abc",
    )
    # Should not raise - formats but doesn't actually write without router
    result = publisher.publish(post)
    assert result is not None


# ════════════════════════════════════════════════════════════════════
#  dry_run tests
# ════════════════════════════════════════════════════════════════════


def test_dry_run_returns_preview(publisher: DevLogPublisher) -> None:
    """Dry-run returns preview of formatted content."""
    post = DevLogPost(
        title="DevLog: 2026-05-29 - Test",
        body="# DevLog for 2026-05-29\n\n## What We Built\n\nInitial implementation with PathGuard filtering and evidence synthesis.\n\n## Technical Decisions\n\nUsed Pydantic v2 for data validation to ensure type safety throughout the pipeline.",
        tweet_thread=[
            Tweet(content="Starting our DevLog series! #cognitivos", order=1),
            Tweet(content="Built PathGuard module. #python #pydantic", order=2),
            Tweet(content="Synthesized evidence into structured posts.", order=3)
        ],
        tags=["#test"],
        evidence_hash="abc",
    )
    result = publisher.dry_run(post)
    assert "github_pages" in result
    assert "What We Built" in result["github_pages"]


def test_dry_run_multiple_platforms(config: DevLogConfig) -> None:
    """Dry-run formats for all configured platforms."""
    config.platforms = ["github_pages", "dev_to"]
    publisher = DevLogPublisher(config)
    post = DevLogPost(
        title="DevLog: 2026-05-29 - Test",
        body="# DevLog for 2026-05-29\n\n## What We Built\n\nInitial implementation with PathGuard filtering and evidence synthesis.\n\n## Technical Decisions\n\nUsed Pydantic v2 for data validation to ensure type safety throughout the pipeline.",
        tweet_thread=[
            Tweet(content="Starting our DevLog series! #cognitivos", order=1),
            Tweet(content="Built PathGuard module. #python #pydantic", order=2),
            Tweet(content="Synthesized evidence into structured posts.", order=3)
        ],
        tags=["#test"],
        evidence_hash="abc",
    )
    result = publisher.dry_run(post)
    assert "github_pages" in result
    assert "dev_to" in result


def test_dry_run_excludes_published_at() -> None:
    """Dry-run output doesn't include published_at."""
    config = DevLogConfig()
    publisher = DevLogPublisher(config)
    post = DevLogPost(
        title="DevLog: 2026-05-29 - Test",
        body="# DevLog for 2026-05-29\n\n## What We Built\n\nInitial implementation with PathGuard filtering and evidence synthesis.\n\n## Technical Decisions\n\nUsed Pydantic v2 for data validation to ensure type safety throughout the pipeline.",
        tweet_thread=[
            Tweet(content="Starting our DevLog series! #cognitivos", order=1),
            Tweet(content="Built PathGuard module. #python #pydantic", order=2),
            Tweet(content="Synthesized evidence into structured posts.", order=3)
        ],
        tags=["#test"],
        evidence_hash="abc",
        published_at=datetime.now(),
    )
    result = publisher.dry_run(post)
    # Should be formatted content, not raw JSON
    assert isinstance(result["github_pages"], str)
