#!/usr/bin/env python3
"""One-shot migration: classify legacy AI-Help/cognitive-os/OLMR*.md via OutputRouter.

Per Phase 5 handoff (ARCH-20260523-235908-49798A0E), Section C2:

  --dry-run (default): walks AI-Help/cognitive-os/OLMR*.md, classifies each via
                       OutputRouter, emits dev/migration_manifest.json with
                       entries (source_path, intended_destination, sha256,
                       classification_confidence, rule_name) and a separate
                       manual_review section for files that only match the
                       catch-all rule.

  --apply             : reads the existing manifest, copies file content to the
                       intended destination, moves the original to
                       AI-Help/cognitive-os/_migrated/. Refuses to run when no
                       manifest exists.

VETO COMPLIANCE:
- V4: imports at top of file; no circular imports.
- V9: explicit error exits; never silently swallow.
- E4: classification uses OutputRouter (single source of routing truth);
      no filename heuristics.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

# Allow `python scripts/migrate_ai_help_legacy.py` from repo root by exposing the
# repo root on sys.path *before* `src.*` imports.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.filesystem_backend_writer import FilesystemBackendWriter  # noqa: E402
from src.output_router import OutputRouter  # noqa: E402
from src.paths import DEV_DIR  # noqa: E402

LEGACY_DIR = REPO_ROOT / "AI-Help" / "cognitive-os"
MIGRATED_DIR = LEGACY_DIR / "_migrated"
MANIFEST_PATH = REPO_ROOT / "dev" / "migration_manifest.json"
ROUTING_RULES_PATH = REPO_ROOT / "config" / "routing_rules.yaml"
DEAD_LETTER_DIR = DEV_DIR / "failed_routings"
CATCHALL_RULE_NAME = "decision_only"  # canonical name of the fallback rule (config/routing_rules.yaml)


def _sha256_of(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _make_router() -> OutputRouter:
    """Build an OutputRouter wired to the production routing_rules.yaml."""
    backend = FilesystemBackendWriter(
        base_dir=DEV_DIR,
        dead_letter_dir=DEAD_LETTER_DIR,
    )
    return OutputRouter(
        rules_path=ROUTING_RULES_PATH,
        backend_writer=backend,
        dead_letter_dir=DEAD_LETTER_DIR,
    )


def _classify(router: OutputRouter, path: Path) -> Dict[str, Any]:
    """Run OutputRouter.route() on the file contents and build a manifest entry."""
    content = path.read_text(encoding="utf-8")
    decision = router.route(content)
    return {
        "source_path": str(path),
        "intended_destination": decision.destination,
        "sha256": _sha256_of(path),
        # OutputRouter is deterministic — confidence is binary: 1.0 if a real
        # rule matched, 0.0 if only the catch-all fired.
        "classification_confidence": 0.0 if decision.rule_name == CATCHALL_RULE_NAME else 1.0,
        "rule_name": decision.rule_name,
        "workflow_phase": decision.workflow_phase,
        "matched_markers": list(decision.matched_markers),
    }


def cmd_dry_run() -> int:
    """Default mode: classify every OLMR*.md and write the manifest."""
    print(f"[DRY-RUN] scanning {LEGACY_DIR}")

    if not LEGACY_DIR.exists():
        print(f"[INFO] {LEGACY_DIR} does not exist; manifest will be empty.")
        MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
        MANIFEST_PATH.write_text(
            json.dumps(
                {
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "entries": [],
                    "manual_review": [],
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"[OK] manifest written: 0 entries, 0 manual_review -> {MANIFEST_PATH}")
        return 0

    router = _make_router()
    entries: List[Dict[str, Any]] = []
    manual_review: List[Dict[str, Any]] = []

    files = sorted(LEGACY_DIR.glob("OLMR*.md"))
    for path in files:
        if MIGRATED_DIR in path.parents:
            continue  # never re-process already-migrated files
        entry = _classify(router, path)
        if entry["rule_name"] == CATCHALL_RULE_NAME:
            manual_review.append(entry)
        else:
            entries.append(entry)

    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(
        json.dumps(
            {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "entries": entries,
                "manual_review": manual_review,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(
        f"[OK] manifest written: {len(entries)} classified, "
        f"{len(manual_review)} need manual review -> {MANIFEST_PATH}"
    )
    return 0


def cmd_apply() -> int:
    """Read the manifest, copy classified files to their destinations, move originals."""
    if not MANIFEST_PATH.exists():
        print(
            f"[ERROR] cannot --apply without a manifest at {MANIFEST_PATH}. "
            f"Run --dry-run first.",
            file=sys.stderr,
        )
        return 2

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    entries: List[Dict[str, Any]] = manifest.get("entries", [])

    if not entries:
        print("[INFO] manifest has no classified entries; nothing to apply.")
        return 0

    MIGRATED_DIR.mkdir(parents=True, exist_ok=True)
    applied = 0
    skipped = 0

    for entry in entries:
        src = Path(entry["source_path"])
        if not src.exists():
            print(f"[SKIP] source already gone: {src}")
            skipped += 1
            continue

        # V9: verify the file we are about to move still matches the manifest hash;
        # refuse to migrate if the content drifted between dry-run and apply.
        actual_hash = _sha256_of(src)
        if actual_hash != entry["sha256"]:
            print(
                f"[SKIP] sha256 drift for {src.name}: "
                f"manifest={entry['sha256'][:12]} actual={actual_hash[:12]}; "
                f"re-run --dry-run before applying.",
                file=sys.stderr,
            )
            skipped += 1
            continue

        dest_dir = DEV_DIR / entry["intended_destination"]
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / src.name

        # Copy content to destination, then move original to _migrated/
        dest.write_bytes(src.read_bytes())
        shutil.move(str(src), str(MIGRATED_DIR / src.name))
        applied += 1
        print(f"[MIGRATED] {src.name} -> {dest}")

    print(f"[OK] applied={applied}, skipped={skipped}, originals in {MIGRATED_DIR}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="One-shot migration of legacy AI-Help/cognitive-os files via OutputRouter."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Execute the migration. Default is --dry-run.",
    )
    args = parser.parse_args()
    return cmd_apply() if args.apply else cmd_dry_run()


if __name__ == "__main__":
    sys.exit(main())
