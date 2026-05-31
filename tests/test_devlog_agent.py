"""Tests for src.devlog_agent (Section D2).

Tests:
- Evidence gathering with PathGuard filtering
- Synthesize post via devlog_scribe role
- PathGuard enforcement at gather-time
- Evidence hash calculation for audit trail

Binding constraints honoured:
    - CSTR-DEVLOG-V1: No autopost (explicit human approval required)
    - CSTR-DEVLOG-V2: PathGuard enforced at gather-time
    - CSTR-DEVLOG-V3: All publishes logged via ApprovalLogger with evidence_hash
"""
from __future__ import annotations

import hashlib
import json
from unittest.mock import patch, MagicMock

import pytest

from src.models.devlog import DevLogConfig, DevLogPost
from src.devlog_agent import DevLogAgent


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
def agent(config: DevLogConfig) -> DevLogAgent:
    """Return a DevLogAgent instance."""
    return DevLogAgent(config)


# ════════════════════════════════════════════════════════════════════
#  gather_evidence tests
# ════════════════════════════════════════════════════════════════════


def test_gather_evidence_returns_dict(agent: DevLogAgent) -> None:
    """gather_evidence returns a dict with evidence arrays."""
    result = agent.gather_evidence("2026-05-29")
    assert isinstance(result, dict)
    assert "date" in result
    assert "git_commits" in result
    assert "gate_deltas" in result


def test_gather_evidence_applies_pathguard(agent: DevLogAgent) -> None:
    """gather_evidence applies PathGuard filtering."""
    evidence = {
        "date": "2026-05-29",
        "git_commits": [{"path": "Z-Inbox/test.txt"}],
        "gate_deltas": [],
        "council_verdicts": [],
        "test_results": [],
    }

    # Mock the path guard's filter method
    with patch.object(agent, "_apply_pathguard", return_value=evidence) as mock_filter:
        result = agent.gather_evidence("2026-05-29")
        mock_filter.assert_called_once()


# ════════════════════════════════════════════════════════════════════
#  synthesize_post tests
# ════════════════════════════════════════════════════════════════════


def test_synthesize_post_calculates_hash(agent: DevLogAgent) -> None:
    """synthesize_post calculates evidence hash for audit trail."""
    evidence = {"date": "2026-05-29", "git_commits": []}
    evidence_json = json.dumps(evidence, sort_keys=True)
    expected_hash = hashlib.sha256(evidence_json.encode()).hexdigest()

    # Mock the LLM call - valid data that passes Pydantic validation
    mock_response = {
        "title": "DevLog: 2026-05-29 - Test Post",
        "body": "# DevLog for 2026-05-29\n\n## What We Built\n\nInitial implementation of the devlog agent with PathGuard filtering and evidence synthesis.\n\n## Technical Decisions\n\nUsed Pydantic v2 for data validation to ensure type safety throughout the pipeline.\n\n## Gate Deltas\n\nBeta handoff approved by technical council.",
        "tweet_thread": [
            {"content": "DevLog: 2026-05-29 - Test Post", "order": 1},
            {"content": "Implemented PathGuard filtering for forbidden sources.", "order": 2},
            {"content": "Synthesized evidence into structured devlog posts.", "order": 3}
        ],
        "tags": ["#test"],
    }

    with patch("src.devlog_agent.llm.generate_response") as mock_llm:
        mock_llm.return_value = json.dumps(mock_response)
        post = agent.synthesize_post(evidence)

    assert post.evidence_hash == expected_hash


def test_synthesize_post_validates_response(agent: DevLogAgent) -> None:
    """synthesize_post raises ValidationError for invalid response."""
    evidence = {"date": "2026-05-29", "git_commits": []}

    # Mock an invalid LLM response
    with patch("src.devlog_agent.llm.generate_response") as mock_llm:
        mock_llm.return_value = json.dumps({"invalid": "response"})
        with pytest.raises(Exception):  # Will raise validation error
            agent.synthesize_post(evidence)


def test_synthesize_post_uses_devlog_scribe_role(agent: DevLogAgent) -> None:
    """synthesize_post calls the devlog_scribe role."""
    evidence = {"date": "2026-05-29", "git_commits": []}
    mock_response = {
        "title": "DevLog: 2026-05-29 - Test Post",
        "body": "# DevLog for 2026-05-29\n\n## What We Built\n\nInitial implementation of the devlog agent with PathGuard filtering.",
        "tweet_thread": [
            {"content": "Starting our DevLog series! #cognitivos", "order": 1},
            {"content": "Built PathGuard module. #python #pydantic", "order": 2},
            {"content": "Synthesized evidence into structured posts.", "order": 3}
        ],
        "tags": ["#test"],
    }

    with patch("src.devlog_agent.llm.generate_response") as mock_llm:
        mock_llm.return_value = json.dumps(mock_response)
        agent.synthesize_post(evidence)

        # Verify the role was resolved to the correct model key
        call_kwargs = mock_llm.call_args[1]
        assert call_kwargs.get("model") == "ministral-3-3b-instruct-2512"


# ════════════════════════════════════════════════════════════════════
#  PathGuard tests
# ════════════════════════════════════════════════════════════════════


def test_pathguard_filters_forbidden_sources(agent: DevLogAgent) -> None:
    """PathGuard filters out forbidden sources from evidence."""
    # Create an agent with custom forbidden patterns
    config = DevLogConfig(
        forbidden_sources=["Z-Inbox/", "mock_vault/"],
    )
    agent = DevLogAgent(config)

    evidence = {
        "date": "2026-05-29",
        "git_commits": [
            {"path": "git/commits/allowed.txt"},
            {"path": "Z-Inbox/forbidden.txt"},
        ],
    }

    result = agent._apply_pathguard(evidence)
    assert len(result["git_commits"]) == 1


# ════════════════════════════════════════════════════════════════════
#  Error handling tests
# ════════════════════════════════════════════════════════════════════


def test_synthesize_post_handles_json_error(agent: DevLogAgent) -> None:
    """synthesize_post raises ValueError on JSON decode error."""
    evidence = {"date": "2026-05-29", "git_commits": []}

    with patch("src.devlog_agent.llm.generate_response") as mock_llm:
        mock_llm.return_value = "{invalid json}"
        with pytest.raises(ValueError, match="Failed to parse LLM response"):
            agent.synthesize_post(evidence)


def test_synthesize_post_handles_validation_error(agent: DevLogAgent) -> None:
    """synthesize_post raises ValidationError for invalid schema."""
    evidence = {"date": "2026-05-29", "git_commits": []}

    # Mock a response that doesn't match the schema
    with patch("src.devlog_agent.llm.generate_response") as mock_llm:
        mock_llm.return_value = json.dumps({
            "title": "Test",
            # Missing required fields: body, tweet_thread
        })
        with pytest.raises(Exception):  # Will raise validation error
            agent.synthesize_post(evidence)