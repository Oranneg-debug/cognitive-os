"""D7: Migration dry-run - unclassifiable file goes to manual_review section.

Spec: unclassifiable file in migration goes to manual-review section.

Per script contract: classification_confidence == 0.0 for catch-all matches,
1.0 for real rules. This assertion proves the catch-all path was correctly identified.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


def test_migration_dry_run_manual_review_for_unclassifiable_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Dry-run routes unclassifiable file to manual_review with confidence 0.0."""
    # Setup temp directories
    ai_help_dir = tmp_path / "AI-Help" / "cognitive-os"
    ai_help_dir.mkdir(parents=True)

    # Create 2 files that match real rules + 1 unmatchable file
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

    # Unclassifiable: no recognized marker
    unknown_file = ai_help_dir / "OLMR_003_unknown.md"
    unknown_file.write_text(
        "---\ntitle: Unmatchable Document\n---\n\nThis file has no routing markers.",
        encoding="utf-8",
    )

    # Patch module-level constants on the migrate_ai_help_legacy script
    import scripts.migrate_ai_help_legacy as migrate_script

    monkeypatch.setattr(migrate_script, "LEGACY_DIR", ai_help_dir)
    monkeypatch.setattr(migrate_script, "MANIFEST_PATH", tmp_path / "dev" / "migration_manifest.json")
    monkeypatch.setattr(migrate_script, "DEV_DIR", tmp_path / "dev")

    # Run dry-run
    result = migrate_script.cmd_dry_run()

    assert result == 0, "cmd_dry_run should return 0 on success"

    # Read manifest
    manifest_path = tmp_path / "dev" / "migration_manifest.json"
    assert manifest_path.exists(), "Manifest should be written to dev/"

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    # Assert: 2 entries (matched files), 1 manual_review
    assert len(manifest["entries"]) == 2, "2 files should be classified via real rules"
    assert len(manifest["manual_review"]) == 1, "1 file should go to manual_review"

    # Assert: correct destinations for matched files
    destinations = {e["intended_destination"] for e in manifest["entries"]}
    assert "proposals" in destinations, "boardroom file should route to proposals"
    assert "decisions" in destinations, "decision file should route to decisions"

    # Assert: manual_review entry has catch-all rule and 0.0 confidence
    mr = manifest["manual_review"][0]
    assert mr["rule_name"] == "decision_only", "Catch-all rule should be decision_only"
    assert mr["classification_confidence"] == 0.0, "Catch-all matches must have 0.0 confidence"

    # Assert: correct sha256 hashes for all files
    expected_hashes = {
        "OLMR_001_boardroom.md": _sha256_of(boardroom_file),
        "OLMR_002_decision.md": _sha256_of(decision_file),
        "OLMR_003_unknown.md": _sha256_of(unknown_file),
    }
    for entry in manifest["entries"]:
        assert entry["sha256"] == expected_hashes[Path(entry["source_path"]).name]
    for mr_entry in manifest["manual_review"]:
        assert mr_entry["sha256"] == expected_hashes[Path(mr_entry["source_path"]).name]

    # Assert: original files still exist (no files moved)
    assert boardroom_file.exists(), "Original boardroom file should still exist"
    assert decision_file.exists(), "Original decision file should still exist"
    assert unknown_file.exists(), "Original unknown file should still exist"


def _sha256_of(p: Path) -> str:
    """Compute SHA256 of a file."""
    import hashlib

    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()