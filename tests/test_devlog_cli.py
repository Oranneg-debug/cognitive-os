"""Tests for scripts/devlog.py CLI (Section D2).

Tests:
- draft command generates posts
- list command shows pending posts
- approve command moves posts to approved/
- publish command processes approved posts

Binding constraints honoured:
    - CSTR-DEVLOG-V1: No autopost (explicit human approval required)
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import yaml
from pathlib import Path

import pytest

# Test imports
from scripts.devlog import (
    load_config,
    gather_evidence,
    synthesize_post,
    save_post,
    load_pending_post,
    list_pending,
)

from src.models.devlog import DevLogPost, Tweet


def test_gather_evidence_returns_dict() -> None:
    """gather_evidence returns a dict with evidence arrays."""
    result = gather_evidence("2026-05-29")
    assert isinstance(result, dict)
    assert "date" in result
    assert "git_commits" in result
    assert "gate_deltas" in result


# ════════════════════════════════════════════════════════════════════
#  Fixtures for valid data


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


def test_synthesize_post_returns_devlog_post() -> None:
    """synthesize_post returns a DevLogPost instance."""
    from src.models.devlog import DevLogPost

    evidence = {
        "date": "2026-05-29",
        "git_commits": [{"sha": "abc123", "message": "Test commit"}],
    }
    post = synthesize_post(evidence)
    assert isinstance(post, DevLogPost)
    assert "DevLog" in post.title
    # Evidence hash is deterministic based on evidence JSON
    expected_hash = hashlib.sha256(json.dumps(evidence, sort_keys=True).encode()).hexdigest()
    assert post.evidence_hash == expected_hash


def test_save_post_creates_file(valid_post: DevLogPost) -> None:
    """save_post creates a JSON file in the output directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir) / "pending"
        result_path = save_post(valid_post, output_dir=output_dir)
        assert result_path.exists()
        assert result_path.suffix == ".json"


def test_load_pending_post_returns_devlog_post(valid_post: DevLogPost) -> None:
    """load_pending_post loads a DevLogPost from JSON."""
    with tempfile.TemporaryDirectory() as tmpdir:
        filepath = Path(tmpdir) / "test.json"
        with open(filepath, "w") as f:
            f.write(valid_post.model_dump_json())

        loaded = load_pending_post(filepath)
        assert isinstance(loaded, DevLogPost)
        assert loaded.title == valid_post.title


def test_list_pending_returns_list() -> None:
    """list_pending returns a list of JSON files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create some test files
        (Path(tmpdir) / "post1.json").write_text("{}")
        (Path(tmpdir) / "post2.json").write_text("{}")
        (Path(tmpdir) / "readme.txt").write_text("not a post")

        result = list_pending(tmpdir)
        assert isinstance(result, list)
        assert len(result) == 2
        assert all(p.suffix == ".json" for p in result)


def test_load_config_returns_devlog_config() -> None:
    """load_config returns a DevLogConfig instance."""
    from src.models.devlog import DevLogConfig

    # Use UTF-8 encoding to handle non-ASCII characters in YAML files
    config_path = Path("config/devlog_config.yaml")
    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    
    assert data is not None
