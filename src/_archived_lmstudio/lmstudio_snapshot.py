"""
LM Studio Preferences Snapshot Utility — DEV-20260521-001000-B5D5C0DE / Task 3.

Snapshots LM Studio's per-model and global configuration files BEFORE the
first `lmstudio-python` SDK call ever runs against this machine. The
boardroom (Strategist veto, 2026-05-20) mandated that the SDK MUST NOT be
allowed to override GUI-managed prefs without a verifiable, hash-pinned
backup on disk first.

What gets snapshotted (Windows paths shown — discovered empirically on
the dev machine 2026-05-21):

  - ~/.lmstudio/.internal/user-concrete-model-default-config/
    (recursive — ~50 JSON files, one per loaded gguf variant)
  - ~/.lmstudio/.internal/backend-preferences-v1.json
  - ~/.lmstudio/.internal/hardware-config.json
  - ~/.lmstudio/config-presets/
    (recursive — user's named presets)

Output layout:

  cognitive-os/backups/lmstudio-prefs/<YYYY-MM-DD_HHMMSS>/
    ├── snapshot_manifest.json   ← timestamp, source root, SHA-256 of every file
    ├── user-concrete-model-default-config/...
    ├── backend-preferences-v1.json
    ├── hardware-config.json
    └── config-presets/...

The utility is **idempotent**: if a snapshot taken in the last hour
exists and contains exactly the same SHA-256 set as the current sources,
no new directory is created. This means "snapshot before first call" is
safe to invoke before *every* SDK lifecycle operation if we want belt +
suspenders later — costs nothing when nothing changed.

Public API:

  snapshot(lmstudio_root: Path | None = None,
           output_root: Path | None = None,
           reuse_window_seconds: int = 3600,
           dry_run: bool = False) -> SnapshotResult

Run as a module from the repo root:

  python -m cognitive-os.src.lmstudio_snapshot          # default paths
  python -m cognitive-os.src.lmstudio_snapshot --dry-run

Or imported from `lmstudio_loader.py` before its first SDK call.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable

# ---------------------------------------------------------------------------
# Paths — Windows-first, but configurable for tests & other OSes.
# ---------------------------------------------------------------------------

def default_lmstudio_root() -> Path:
    """Return the platform-default location of LM Studio's user state."""
    return Path.home() / ".lmstudio"


def default_output_root() -> Path:
    """Snapshots land inside the repo so they're git-ignorable and visible."""
    # This file lives at cognitive-os/src/lmstudio_snapshot.py
    # Backups go to cognitive-os/backups/lmstudio-prefs/
    return Path(__file__).resolve().parent.parent / "backups" / "lmstudio-prefs"


# Relative paths (from lmstudio_root) that we snapshot.
# - Files are copied byte-for-byte.
# - Dirs are walked recursively; non-JSON files inside them are still copied
#   (the LM Studio team may add new file types later — we don't want to drop them).
SNAPSHOT_PATHS: tuple[str, ...] = (
    ".internal/user-concrete-model-default-config",   # per-model load/inference defaults
    ".internal/backend-preferences-v1.json",          # global llama.cpp backend prefs
    ".internal/hardware-config.json",                 # GPU/CPU detection + offload defaults
    "config-presets",                                  # user's named presets
)


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class SnapshotResult:
    """Returned by :func:`snapshot` so callers can act on the outcome."""

    snapshot_dir: Path
    manifest_path: Path
    files_copied: int
    bytes_copied: int
    reused_existing: bool
    skipped_missing: list[str] = field(default_factory=list)

    def __str__(self) -> str:  # pragma: no cover — display
        if self.reused_existing:
            verb = "reused"
        elif self.files_copied == 0 and self.bytes_copied == 0:
            verb = "would create (dry-run)"
        else:
            verb = "created"
        kb = self.bytes_copied / 1024
        return (
            f"[snapshot] {verb} {self.snapshot_dir} "
            f"({self.files_copied} files, {kb:.1f} KiB)"
        )


# ---------------------------------------------------------------------------
# Hashing helpers
# ---------------------------------------------------------------------------

def _sha256_file(path: Path, _buf: int = 65536) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(_buf), b""):
            h.update(chunk)
    return h.hexdigest()


def _iter_source_files(lmstudio_root: Path) -> Iterable[tuple[Path, Path]]:
    """Yield (absolute_source_path, relative_path_from_lmstudio_root) pairs.

    Sorted for deterministic manifest output across runs/OSes.
    """
    for rel in SNAPSHOT_PATHS:
        src = lmstudio_root / rel
        if not src.exists():
            continue
        if src.is_file():
            yield src, Path(rel)
        else:
            for file in sorted(src.rglob("*")):
                if file.is_file():
                    yield file, file.relative_to(lmstudio_root)


def _build_current_hashmap(lmstudio_root: Path) -> dict[str, str]:
    """Return {relative_posix_path: sha256_hex} for every snapshot target."""
    hashmap: dict[str, str] = {}
    for src, rel in _iter_source_files(lmstudio_root):
        hashmap[rel.as_posix()] = _sha256_file(src)
    return hashmap


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------

def _find_recent_match(
    output_root: Path,
    current_hashes: dict[str, str],
    within: timedelta,
) -> Path | None:
    """Return the most recent existing snapshot dir whose manifest matches
    `current_hashes` exactly AND was taken within ``within``. Otherwise None.
    """
    if not output_root.exists():
        return None

    now = datetime.now()
    candidates: list[tuple[datetime, Path]] = []
    for entry in output_root.iterdir():
        if not entry.is_dir():
            continue
        manifest = entry / "snapshot_manifest.json"
        if not manifest.exists():
            continue
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
            taken_at = datetime.fromisoformat(data["taken_at"])
        except (json.JSONDecodeError, KeyError, ValueError):
            continue
        if now - taken_at > within:
            continue
        if data.get("file_hashes") == current_hashes:
            candidates.append((taken_at, entry))

    if not candidates:
        return None
    candidates.sort(reverse=True)  # newest first
    return candidates[0][1]


# ---------------------------------------------------------------------------
# Core snapshot
# ---------------------------------------------------------------------------

def snapshot(
    lmstudio_root: Path | None = None,
    output_root: Path | None = None,
    reuse_window_seconds: int = 3600,
    dry_run: bool = False,
) -> SnapshotResult:
    """Take a snapshot of LM Studio prefs, or reuse a recent identical one.

    Args:
        lmstudio_root: Override LM Studio's user state dir (default: ~/.lmstudio).
        output_root:   Override where snapshots are written
                       (default: cognitive-os/backups/lmstudio-prefs).
        reuse_window_seconds: If an existing snapshot in this window matches
                       the current source hashes byte-for-byte, reuse it
                       instead of writing a new one. Set to 0 to always write.
        dry_run:       Plan but don't write anything. Returns a result with
                       ``files_copied = 0`` and ``snapshot_dir`` pointed at
                       the would-be target.
    """
    src_root = (lmstudio_root or default_lmstudio_root()).resolve()
    dst_root = (output_root or default_output_root()).resolve()

    if not src_root.exists():
        raise FileNotFoundError(
            f"LM Studio root not found: {src_root} "
            f"(set LMSTUDIO_HOME or pass lmstudio_root=)"
        )

    # 1. Hash everything at source. This also tells us what's missing.
    current_hashes = _build_current_hashmap(src_root)
    skipped_missing = [
        p for p in SNAPSHOT_PATHS if not (src_root / p).exists()
    ]

    # 2. Idempotency check.
    if reuse_window_seconds > 0:
        match = _find_recent_match(
            dst_root,
            current_hashes,
            timedelta(seconds=reuse_window_seconds),
        )
        if match is not None:
            return SnapshotResult(
                snapshot_dir=match,
                manifest_path=match / "snapshot_manifest.json",
                files_copied=0,
                bytes_copied=0,
                reused_existing=True,
                skipped_missing=skipped_missing,
            )

    # 3. New snapshot dir.
    ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    snap_dir = dst_root / ts

    if dry_run:
        return SnapshotResult(
            snapshot_dir=snap_dir,
            manifest_path=snap_dir / "snapshot_manifest.json",
            files_copied=0,
            bytes_copied=0,
            reused_existing=False,
            skipped_missing=skipped_missing,
        )

    snap_dir.mkdir(parents=True, exist_ok=False)

    # 4. Copy every file, preserving relative paths.
    files_copied = 0
    bytes_copied = 0
    for src, rel in _iter_source_files(src_root):
        dst = snap_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        files_copied += 1
        bytes_copied += dst.stat().st_size

    # 5. Write manifest.
    manifest = {
        "schema_version": 1,
        "taken_at": datetime.now().isoformat(timespec="seconds"),
        "lmstudio_root": str(src_root),
        "snapshot_dir": str(snap_dir),
        "snapshot_paths": list(SNAPSHOT_PATHS),
        "skipped_missing": skipped_missing,
        "files_copied": files_copied,
        "bytes_copied": bytes_copied,
        "file_hashes": current_hashes,
        "purpose": (
            "Pre-SDK-override backup. Restore by copying back into "
            "lmstudio_root. See DEV-20260521-001000-B5D5C0DE."
        ),
    }
    manifest_path = snap_dir / "snapshot_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=False),
        encoding="utf-8",
    )

    return SnapshotResult(
        snapshot_dir=snap_dir,
        manifest_path=manifest_path,
        files_copied=files_copied,
        bytes_copied=bytes_copied,
        reused_existing=False,
        skipped_missing=skipped_missing,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="lmstudio_snapshot",
        description="Snapshot LM Studio per-model + global preferences "
                    "before the lmstudio-python SDK is allowed to override them.",
    )
    p.add_argument(
        "--lmstudio-root",
        type=Path,
        default=None,
        help="Override the LM Studio user state directory (default: ~/.lmstudio).",
    )
    p.add_argument(
        "--output-root",
        type=Path,
        default=None,
        help="Where snapshots are written (default: "
             "cognitive-os/backups/lmstudio-prefs/).",
    )
    p.add_argument(
        "--reuse-window",
        type=int,
        default=3600,
        metavar="SECONDS",
        help="Reuse an identical snapshot taken within this window "
             "(default: 3600, set 0 to always create a new one).",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Plan the snapshot but don't write anything.",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_argparser().parse_args(argv)
    try:
        result = snapshot(
            lmstudio_root=args.lmstudio_root,
            output_root=args.output_root,
            reuse_window_seconds=args.reuse_window,
            dry_run=args.dry_run,
        )
    except FileNotFoundError as e:
        print(f"[snapshot] ERROR: {e}", file=sys.stderr)
        return 2

    print(result)
    if result.skipped_missing:
        print(
            f"[snapshot] note: {len(result.skipped_missing)} expected "
            f"path(s) were missing on disk and skipped: "
            f"{result.skipped_missing}"
        )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
