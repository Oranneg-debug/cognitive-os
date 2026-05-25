"""D6: Migration dry-run - classify legacy files via OutputRouter without moving them.

Spec: 3-file fixture in fake AI-Help/cognitive-os/; run script with --dry-run;
assert manifest.json contains 3 entries with correct sha256s; no files moved.

VETO COMPLIANCE:
- V4: No circular imports; lazy imports only where necessary
- V9: Explicit exceptions raised, never silently swallowed
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


def test_migration_dry_run_classifies_three_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Dry-run classifies 3 files via OutputRouter, writes manifest, no files moved."""
    # Setup temp directories
    ai_help_dir = tmp_path / "AI-Help" / "cognitive-os"
    ai_help_dir.mkdir(parents=True)

    # Create 3 fixture files with distinct routing markers
    boardroom_file = ai_help_dir / "OLMR_001_boardroom.md"
    boardroom_file.write_text(
        "---\ntitle: Board Proposal\n---\n#boardroom\n\nThis is a boardroom proposal.",
        encoding="utf-8",
    )

    decision_file = ai_help_dir / "OLMR_002_decision.md"
    decision_file.write_text(
        "---\ntitle: Council Decision\n---\n#decision\n\nThis is a council decision.",
        encoding="utf-8",
    )

    handoff_file = ai_help_dir / "OLMR_003_handoff.md"
    handoff_file.write_text(
        "---\ntitle: Handoff Archive\n---\n#handoff\n\nThis is a handoff archival.",
        encoding="utf-8",
    )

    # Patch module-level constants on the migrate_ai_help_legacy script
    import scripts.migrate_ai_help_legacy as migrate_script

    monkeypatch.setattr(migrate_script, "LEGACY_DIR", ai_help_dir)
    monkeypatch.setattr(migrate_script, "MANIFEST_PATH", tmp_path / "dev" / "migration_manifest.json")
    monkeypatch.setattr(migrate_script, "DEV_DIR", tmp_path / "dev")

    # Run dry-run (default mode)
    result = migrate_script.cmd_dry_run()

    assert result == 0, "cmd_dry_run should return 0 on success"

    # Read manifest
    manifest_path = tmp_path / "dev" / "migration_manifest.json"
    assert manifest_path.exists(), "Manifest should be written to dev/"

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    # Assert: 3 entries, 0 manual_review
    assert len(manifest["entries"]) == 3, "All 3 files should be classified (not catch-all)"
    assert len(manifest["manual_review"]) == 0, "No files should go to manual_review"

    # Assert: correct destinations for each rule type
    destinations = {e["intended_destination"] for e in manifest["entries"]}
    assert "proposals" in destinations, "boardroom file should route to proposals"
    assert "decisions" in destinations, "decision file should route to decisions"
    assert "handoffs" in destinations, "handoff file should route to handoffs"

    # Assert: correct sha256 hashes
    for entry in manifest["entries"]:
        source_path = Path(entry["source_path"])
        actual_hash = entry["sha256"]
        expected_hash = _sha256_of(source_path)
        assert actual_hash == expected_hash, f"Hash mismatch for {source_path.name}"

    # Assert: original files still exist (no files moved)
    assert boardroom_file.exists(), "Original boardroom file should still exist"
    assert decision_file.exists(), "Original decision file should still exist"
    assert handoff_file.exists(), "Original handoff file should still exist"


def _sha256_of(p: Path) -> str:
    """Compute SHA256 of a file."""
    import hashlib

    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()