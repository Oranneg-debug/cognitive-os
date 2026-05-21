"""
SQLite-backed metadata index for sub-100ms YAML queries.

Required once the vault exceeds 5k notes; cheap to run earlier.
Stores frontmatter scalars in a normalised table, tags in a join table,
and offers a small query API. No external deps.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .schema import parse_markdown


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS notes (
    path             TEXT PRIMARY KEY,
    council          TEXT,
    type             TEXT,
    status           TEXT,
    date             TEXT,
    owner            TEXT,
    metadata_version TEXT,
    extra_json       TEXT,
    mtime            REAL
);
CREATE INDEX IF NOT EXISTS idx_notes_council ON notes(council);
CREATE INDEX IF NOT EXISTS idx_notes_type    ON notes(type);
CREATE INDEX IF NOT EXISTS idx_notes_status  ON notes(status);
CREATE INDEX IF NOT EXISTS idx_notes_date    ON notes(date);

CREATE TABLE IF NOT EXISTS tags (
    path TEXT NOT NULL,
    tag  TEXT NOT NULL,
    PRIMARY KEY (path, tag),
    FOREIGN KEY (path) REFERENCES notes(path) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_tags_tag ON tags(tag);
"""

_CORE_FIELDS = {"council", "type", "status", "date", "owner", "metadata_version", "tags"}


@dataclass
class IndexStats:
    indexed: int = 0
    skipped: int = 0
    removed: int = 0


class MetadataIndex:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.executescript(_SCHEMA_SQL)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "MetadataIndex":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    # ---- ingest --------------------------------------------------------

    def index_vault(self, vault_root: str | Path) -> IndexStats:
        root = Path(vault_root)
        stats = IndexStats()
        known: set[str] = set()
        for md in root.rglob("*.md"):
            if not md.is_file():
                continue
            key = str(md.resolve())
            known.add(key)
            mtime = md.stat().st_mtime
            row = self.conn.execute(
                "SELECT mtime FROM notes WHERE path = ?", (key,)
            ).fetchone()
            if row and abs(row[0] - mtime) < 1e-6:
                stats.skipped += 1
                continue
            try:
                content = md.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                stats.skipped += 1
                continue
            fm, _ = parse_markdown(content)
            if not fm:
                stats.skipped += 1
                continue
            self._upsert(key, fm, mtime)
            stats.indexed += 1

        # prune deleted notes
        rows = self.conn.execute("SELECT path FROM notes").fetchall()
        for (path,) in rows:
            if path not in known:
                self.conn.execute("DELETE FROM notes WHERE path = ?", (path,))
                stats.removed += 1
        self.conn.commit()
        return stats

    def _upsert(self, path: str, fm: dict, mtime: float) -> None:
        extras = {k: v for k, v in fm.items() if k not in _CORE_FIELDS}
        self.conn.execute(
            """
            INSERT INTO notes(path, council, type, status, date, owner,
                              metadata_version, extra_json, mtime)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(path) DO UPDATE SET
                council=excluded.council,
                type=excluded.type,
                status=excluded.status,
                date=excluded.date,
                owner=excluded.owner,
                metadata_version=excluded.metadata_version,
                extra_json=excluded.extra_json,
                mtime=excluded.mtime
            """,
            (
                path,
                fm.get("council"),
                fm.get("type"),
                fm.get("status"),
                fm.get("date"),
                fm.get("owner"),
                fm.get("metadata_version"),
                json.dumps(extras, default=str, ensure_ascii=False),
                mtime,
            ),
        )
        self.conn.execute("DELETE FROM tags WHERE path = ?", (path,))
        tags = fm.get("tags") or []
        if isinstance(tags, str):
            tags = [tags]
        for tag in tags:
            self.conn.execute(
                "INSERT OR IGNORE INTO tags(path, tag) VALUES (?, ?)", (path, str(tag))
            )

    # ---- query ---------------------------------------------------------

    def query(
        self,
        *,
        council: str | None = None,
        type: str | None = None,
        status: str | None = None,
        tag: str | None = None,
        since: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if council:
            clauses.append("notes.council = ?")
            params.append(council)
        if type:
            clauses.append("notes.type = ?")
            params.append(type)
        if status:
            clauses.append("notes.status = ?")
            params.append(status)
        if since:
            clauses.append("notes.date >= ?")
            params.append(since)
        join = ""
        if tag:
            join = "JOIN tags ON tags.path = notes.path"
            clauses.append("tags.tag = ?")
            params.append(tag)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        sql = (
            f"SELECT notes.path, notes.council, notes.type, notes.status, "
            f"notes.date, notes.owner, notes.metadata_version, notes.extra_json "
            f"FROM notes {join} {where} ORDER BY notes.date DESC LIMIT ?"
        )
        params.append(limit)
        rows = self.conn.execute(sql, params).fetchall()
        out: list[dict[str, Any]] = []
        for r in rows:
            out.append(
                {
                    "path": r[0],
                    "council": r[1],
                    "type": r[2],
                    "status": r[3],
                    "date": r[4],
                    "owner": r[5],
                    "metadata_version": r[6],
                    **(json.loads(r[7]) if r[7] else {}),
                }
            )
        return out

    def count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0]
