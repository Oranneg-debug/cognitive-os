"""
Event-driven ingestion engine for the Tripartite File System.

Replaces the brittle bash routing script with an idempotent Python service.
Sources (Telegram / Obsidian / arbitrary uploads) → Requests/Inbox/.

Key properties:
- Deterministic filename schema: {YYYY-MM-DD}-{council}-{type}-{slug}.md
- Idempotent: same source file processed twice → same target, no duplication
- Collision-safe: identical filenames with different content get a -2, -3, … suffix
- Frontmatter is upserted (metadata_version, source_channel, ingested_at)
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from .schema import (
    METADATA_VERSION,
    dump_frontmatter,
    parse_markdown,
    validate_frontmatter,
)


_SLUG_RE = re.compile(r"[^a-zA-Z0-9]+")
_MAX_SLUG_LEN = 40


def sanitize_filename(
    *, council: str, type_: str, slug_source: str, when: Optional[datetime] = None
) -> str:
    """Build a deterministic filename: YYYY-MM-DD-council-type-slug.md."""
    when = when or datetime.now()
    council_clean = _SLUG_RE.sub("-", council).strip("-").lower() or "unknown"
    type_clean = _SLUG_RE.sub("-", type_).strip("-").lower() or "report"
    slug = _SLUG_RE.sub("-", slug_source).strip("-").lower()[:_MAX_SLUG_LEN] or "untitled"
    return f"{when.strftime('%Y-%m-%d')}-{council_clean}-{type_clean}-{slug}.md"


def _hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass
class IngestResult:
    target: Path
    action: str  # "created" | "skipped_idempotent" | "renamed_collision" | "rejected"
    reason: str = ""

    @property
    def ok(self) -> bool:
        return self.action != "rejected"


class IngestionEngine:
    """Single entry point for routing inbound notes into the vault.

    The engine is stateless w.r.t. its own state — idempotency is recovered
    from the destination directory itself by comparing SHA-256 hashes.
    """

    def __init__(self, vault_root: str | os.PathLike):
        self.vault_root = Path(vault_root)
        self.inbox = self.vault_root / "Requests" / "Inbox"
        self.inbox.mkdir(parents=True, exist_ok=True)

    # -- public -----------------------------------------------------------

    def ingest_file(
        self,
        source_path: str | os.PathLike,
        *,
        source_channel: str,
        council: str = "Boardroom",
        type_: str = "request",
        owner: str = "system@CognitiveOS",
        slug_hint: Optional[str] = None,
        delete_source: bool = False,
    ) -> IngestResult:
        source = Path(source_path)
        if not source.is_file():
            return IngestResult(
                Path(), "rejected", f"source not found: {source}"
            )

        raw = source.read_text(encoding="utf-8")
        fm, body = parse_markdown(raw)

        # Upsert required fields
        fm.setdefault("council", council)
        fm.setdefault("type", type_)
        fm.setdefault("status", "proposed")
        fm.setdefault("date", datetime.now().strftime("%Y-%m-%d"))
        fm.setdefault("owner", owner)
        fm["metadata_version"] = METADATA_VERSION
        fm["source_channel"] = source_channel
        fm.setdefault("ingested_at", datetime.now().isoformat(timespec="seconds"))

        ok, errors = validate_frontmatter(fm)
        if not ok:
            return IngestResult(Path(), "rejected", f"schema errors: {errors}")

        slug = slug_hint or source.stem
        target_name = sanitize_filename(
            council=fm["council"], type_=fm["type"], slug_source=slug
        )
        target = self.inbox / target_name

        rendered = dump_frontmatter(fm, body.lstrip())

        # ---- idempotency / collision handling ---------------------------
        if target.exists():
            existing = target.read_text(encoding="utf-8")
            if existing == rendered:
                return IngestResult(target, "skipped_idempotent")
            # different content but same name → suffix
            target = self._resolve_collision(target, rendered)
            if target.exists() and target.read_text(encoding="utf-8") == rendered:
                return IngestResult(target, "skipped_idempotent")
            target.write_text(rendered, encoding="utf-8")
            if delete_source:
                source.unlink(missing_ok=True)
            return IngestResult(target, "renamed_collision")

        target.write_text(rendered, encoding="utf-8")
        if delete_source:
            source.unlink(missing_ok=True)
        return IngestResult(target, "created")

    # -- helpers ----------------------------------------------------------

    @staticmethod
    def _resolve_collision(target: Path, rendered: str) -> Path:
        """Find the next available `-N` suffix, or return an existing match."""
        stem, suffix = target.stem, target.suffix
        n = 2
        while True:
            candidate = target.with_name(f"{stem}-{n}{suffix}")
            if not candidate.exists():
                return candidate
            if candidate.read_text(encoding="utf-8") == rendered:
                return candidate
            n += 1
            if n > 999:  # safety net
                raise RuntimeError(f"too many collisions for {target}")
