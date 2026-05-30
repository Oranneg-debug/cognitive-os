"""SQLite-backed kanban state store — ARCH-20260522-205800-DA5B0A2D (A1).

Single source of truth for the kanban board. Replaces the markdown-parse +
JSON-cache scheme in ``kanban_processor.py`` with a real database.

Design notes
------------
- **Single writer**: only the API (via ``workflow_engine`` ➝ here) writes.
  SQLite is the single source of truth; the dashboard at
  http://127.0.0.1:5000 is the only board editor. Eliminates the
  proposal_sync / kanban_processor
  race that has been our recurring kanban-hiccup source.
- **Async-safe**: every public method is ``async`` and wraps blocking
  sqlite3 in ``asyncio.to_thread``. FastAPI routes call us directly without
  spinning their own thread pool.
- **Connection-per-call**: we open a fresh ``sqlite3.Connection`` per query.
  sqlite3's threading model is "connection-per-thread" and ``to_thread``
  hands out a different worker each time. Cheap on disk-backed SQLite.
- **Foreign keys ON**: enforced on every connection via ``PRAGMA``.
- **Backups**: ``backup()`` runs ``VACUUM INTO`` to a timestamped file under
  ``dev/.backups/``. Caller is expected to call it before migrations.
  Rotation (keep last 10) is built in.

Schema is the contract documented in the proposal §"Schema". See
``CARDS_SCHEMA_SQL`` and ``TRANSITIONS_SCHEMA_SQL`` below — modifying
those is a database migration, not a refactor.

Out of scope here
-----------------
- Markdown rendering (A2)
- API endpoints (A3)
- Dashboard UI (A4)
- ``kanban_processor.py`` slim-down (A5)
- One-shot migration (B1)

This module is **pure data plane**. No HTTP. No filesystem outside the
SQLite file + its backup dir. No prints.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator, List, Optional

from src.paths import DEV_DIR

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════════
#  Paths
# ════════════════════════════════════════════════════════════════════

#: Single SQLite file backing the board. Lives in the repo, NOT the vault
#: (process state belongs with the developer side).
KANBAN_DB_PATH: Path = DEV_DIR / "kanban_state.sqlite"

#: Backup directory. ``backup()`` rotates to keep the latest ``BACKUP_RETAIN``.
KANBAN_BACKUP_DIR: Path = DEV_DIR / ".backups"

#: How many ``kanban_state_*.sqlite`` snapshots to retain.
BACKUP_RETAIN: int = 10


# ════════════════════════════════════════════════════════════════════
#  Canonical columns — single source for the rest of the system
# ════════════════════════════════════════════════════════════════════

#: Column names in board order (left-to-right). Matches the existing
#: ``kanban_processor.columns`` order so we don't break callers.
CANONICAL_COLUMNS: tuple[str, ...] = (
    "backlog",
    "proposal",
    "beta testing",
    "alpha polish",
    "finalized",
    "deployed",
)

#: Prefixes we know how to file. Anything else is rejected by ``add_card``.
KNOWN_PREFIXES: frozenset[str] = frozenset({"DEV", "ARCH", "NLST"})


# ════════════════════════════════════════════════════════════════════
#  Dataclasses — the carrier types crossing module boundaries
# ════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class Card:
    """A single kanban card. Frozen so it round-trips safely."""

    proposal_id: str
    prefix: str
    column_name: str
    title: Optional[str] = None
    substatus: Optional[str] = None
    severity: Optional[str] = None
    origin: Optional[str] = None
    keywords: Optional[str] = None  # comma-separated tags for dashboard search
    created_ts: str = ""
    updated_ts: str = ""
    state_hash: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class Transition:
    """A row from the transitions log."""

    id: int
    proposal_id: str
    from_column: Optional[str]
    to_column: str
    from_substatus: Optional[str]
    to_substatus: Optional[str]
    approver: str
    reason: Optional[str]
    gate_passed: int  # 0=N/A, 1=passed, -1=failed
    gate_details: Optional[dict]  # decoded from JSON
    archive_hash: Optional[str]
    ts: str

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


@dataclass(frozen=True)
class Column:
    """A column projection in a ``BoardSnapshot``."""

    name: str
    cards: List[Card] = field(default_factory=list)


@dataclass(frozen=True)
class BoardSnapshot:
    """A read-only view of the entire board at one instant.

    Returned by ``get_board()``. Consumed by the dashboard JSON API.
    and the ``/api/kanban/board`` endpoint (A3).
    """

    columns: List[Column]
    generated_at: str

    def to_dict(self) -> dict:
        return {
            "columns": [
                {"name": c.name, "cards": [card.to_dict() for card in c.cards]}
                for c in self.columns
            ],
            "generated_at": self.generated_at,
        }


# ════════════════════════════════════════════════════════════════════
#  Schema
# ════════════════════════════════════════════════════════════════════


CARDS_SCHEMA_SQL: str = """
CREATE TABLE IF NOT EXISTS cards (
    proposal_id    TEXT PRIMARY KEY,
    prefix         TEXT NOT NULL,
    title          TEXT,
    column_name    TEXT NOT NULL,
    substatus      TEXT,
    severity       TEXT,
    origin         TEXT,
    keywords       TEXT,
    created_ts     TEXT NOT NULL,
    updated_ts     TEXT NOT NULL,
    state_hash     TEXT NOT NULL
)
"""


TRANSITIONS_SCHEMA_SQL: str = """
CREATE TABLE IF NOT EXISTS transitions (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    proposal_id    TEXT NOT NULL,
    from_column    TEXT,
    to_column      TEXT NOT NULL,
    from_substatus TEXT,
    to_substatus   TEXT,
    approver       TEXT NOT NULL,
    reason         TEXT,
    gate_passed    INTEGER NOT NULL DEFAULT 0,
    gate_details   TEXT,
    archive_hash   TEXT,
    ts             TEXT NOT NULL,
    FOREIGN KEY (proposal_id) REFERENCES cards(proposal_id)
)
"""


INDEX_SQL: tuple[str, ...] = (
    "CREATE INDEX IF NOT EXISTS idx_transitions_proposal ON transitions(proposal_id, ts)",
    "CREATE INDEX IF NOT EXISTS idx_cards_column ON cards(column_name, updated_ts DESC)",
)


# ════════════════════════════════════════════════════════════════════
#  Errors
# ════════════════════════════════════════════════════════════════════


class KanbanStoreError(Exception):
    """Base class for store errors. Caller can catch this for fallback."""


class CardNotFound(KanbanStoreError):
    """Raised when an operation targets a proposal_id that doesn't exist."""


class InvalidColumn(KanbanStoreError):
    """Raised when a column name is not in :data:`CANONICAL_COLUMNS`."""


class InvalidPrefix(KanbanStoreError):
    """Raised when a prefix is not in :data:`KNOWN_PREFIXES`."""


# ════════════════════════════════════════════════════════════════════
#  Low-level helpers (sync — wrapped by async API below)
# ════════════════════════════════════════════════════════════════════


@contextmanager
def _connect(db_path: Path) -> Iterator[sqlite3.Connection]:
    """Open a connection with foreign keys + row dict factory enabled.

    Always commits on clean exit; rolls back on exception. Closes
    unconditionally. Caller is responsible for not holding the connection
    across an ``await`` (use ``asyncio.to_thread`` to keep each connection
    pinned to one worker).
    """
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _compute_state_hash(column_name: str, substatus: Optional[str]) -> str:
    """Stable hash of (column, substatus). Used by the renderer to skip
    no-op re-writes and by ``transitions`` for cheap diffing.

    Deliberately SHA-256 truncated to 16 hex chars — collision risk is
    irrelevant at our cardinality (≤ ~200 cards over the project life)
    and short hashes read better in logs.
    """
    payload = f"{column_name}|{substatus or ''}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]


def _validate_column(name: str) -> None:
    if name not in CANONICAL_COLUMNS:
        raise InvalidColumn(
            f"Unknown column {name!r}; expected one of {CANONICAL_COLUMNS}"
        )


def _validate_prefix(prefix: str) -> None:
    if prefix not in KNOWN_PREFIXES:
        raise InvalidPrefix(
            f"Unknown prefix {prefix!r}; expected one of {sorted(KNOWN_PREFIXES)}"
        )


def _utcnow_iso() -> str:
    """Timezone-aware ISO 8601 'now' in UTC.

    Replaces ``datetime.utcnow()`` (deprecated in Python 3.12+, removal
    slated). The 'Z' suffix is conventionally preferred over '+00:00';
    we keep '+00:00' here because :func:`datetime.fromisoformat` round-trips
    that form on all supported Python versions.
    """
    return datetime.now(timezone.utc).isoformat()


def _row_to_card(row: sqlite3.Row) -> Card:
    return Card(
        proposal_id=row["proposal_id"],
        prefix=row["prefix"],
        title=row["title"],
        column_name=row["column_name"],
        substatus=row["substatus"],
        severity=row["severity"],
        origin=row["origin"],
        keywords=row["keywords"],
        created_ts=row["created_ts"],
        updated_ts=row["updated_ts"],
        state_hash=row["state_hash"],
    )


def _update_card_sync(db_path: Path, proposal_id: str, updates: dict) -> Card:
    """Update arbitrary fields on a card."""
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM cards WHERE proposal_id = ?",
            (proposal_id,),
        ).fetchone()
        if row is None:
            raise CardNotFound(f"No card found for proposal_id={proposal_id!r}")

        # Build the SET clause dynamically from the updates dict
        set_clauses = []
        params = []
        for key, value in updates.items():
            # Basic sanitization to prevent SQL injection on field names
            if key not in ("title", "substatus", "severity", "origin", "keywords"):
                raise ValueError(f"Invalid field for update: {key}")
            set_clauses.append(f"{key} = ?")
            params.append(value)

        if not set_clauses:
            return _row_to_card(row)  # No updates to apply

        params.append(proposal_id)
        sql = f"UPDATE cards SET {', '.join(set_clauses)} WHERE proposal_id = ?"
        conn.execute(sql, tuple(params))

        updated = conn.execute(
            "SELECT * FROM cards WHERE proposal_id = ?",
            (proposal_id,),
        ).fetchone()
        return _row_to_card(updated)


def _row_to_transition(row: sqlite3.Row) -> Transition:
    raw_details = row["gate_details"]
    parsed: Optional[dict]
    if raw_details:
        try:
            parsed = json.loads(raw_details)
        except json.JSONDecodeError:
            logger.warning(
                "transitions.gate_details is non-JSON for id=%s; surfacing as raw string",
                row["id"],
            )
            parsed = {"raw": raw_details}
    else:
        parsed = None
    return Transition(
        id=row["id"],
        proposal_id=row["proposal_id"],
        from_column=row["from_column"],
        to_column=row["to_column"],
        from_substatus=row["from_substatus"],
        to_substatus=row["to_substatus"],
        approver=row["approver"],
        reason=row["reason"],
        gate_passed=row["gate_passed"],
        gate_details=parsed,
        archive_hash=row["archive_hash"],
        ts=row["ts"],
    )


# ════════════════════════════════════════════════════════════════════
#  Sync implementations (the actual SQL)
# ════════════════════════════════════════════════════════════════════


def _init_schema_sync(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with _connect(db_path) as conn:
        conn.execute(CARDS_SCHEMA_SQL)
        conn.execute(TRANSITIONS_SCHEMA_SQL)
        for idx in INDEX_SQL:
            conn.execute(idx)


def _add_card_sync(
    db_path: Path,
    *,
    proposal_id: str,
    prefix: str,
    column_name: str,
    title: Optional[str],
    substatus: Optional[str],
    severity: Optional[str],
    origin: Optional[str],
    keywords: Optional[str] = None,
    approver: str,
    reason: Optional[str],
) -> Card:
    _validate_prefix(prefix)
    _validate_column(column_name)
    now = _utcnow_iso()
    state_hash = _compute_state_hash(column_name, substatus)

    with _connect(db_path) as conn:
        # Idempotent upsert: if the proposal already exists, return the
        # existing row. Callers wanting "really update" should use
        # ``move_card`` instead.
        existing = conn.execute(
            "SELECT * FROM cards WHERE proposal_id = ?",
            (proposal_id,),
        ).fetchone()
        if existing is not None:
            return _row_to_card(existing)

        conn.execute(
            """
            INSERT INTO cards
                (proposal_id, prefix, title, column_name, substatus,
                 severity, origin, keywords, created_ts, updated_ts, state_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                proposal_id,
                prefix,
                title,
                column_name,
                substatus,
                severity,
                origin,
                keywords,
                now,
                now,
                state_hash,
            ),
        )
        # Record the initial-placement transition. from_column NULL signals
        # "card was created here", which the renderer + history endpoint can
        # display as "Created in <column>".
        conn.execute(
            """
            INSERT INTO transitions
                (proposal_id, from_column, to_column,
                 from_substatus, to_substatus,
                 approver, reason, gate_passed, ts)
            VALUES (?, NULL, ?, NULL, ?, ?, ?, 0, ?)
            """,
            (proposal_id, column_name, substatus, approver, reason, now),
        )

        row = conn.execute(
            "SELECT * FROM cards WHERE proposal_id = ?",
            (proposal_id,),
        ).fetchone()
        return _row_to_card(row)


def _move_card_sync(
    db_path: Path,
    *,
    proposal_id: str,
    target_column: str,
    target_substatus: Optional[str],
    approver: str,
    reason: Optional[str],
    gate_passed: int,
    gate_details: Optional[dict],
    archive_hash: Optional[str],
) -> Card:
    _validate_column(target_column)
    if gate_passed not in (-1, 0, 1):
        raise ValueError(
            f"gate_passed must be -1 (failed), 0 (N/A), or 1 (passed); got {gate_passed!r}"
        )

    now = _utcnow_iso()
    new_hash = _compute_state_hash(target_column, target_substatus)
    details_json = json.dumps(gate_details) if gate_details else None

    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM cards WHERE proposal_id = ?",
            (proposal_id,),
        ).fetchone()
        if row is None:
            raise CardNotFound(f"No card found for proposal_id={proposal_id!r}")

        from_column = row["column_name"]
        from_substatus = row["substatus"]

        conn.execute(
            """
            UPDATE cards
               SET column_name = ?, substatus = ?, updated_ts = ?, state_hash = ?
             WHERE proposal_id = ?
            """,
            (target_column, target_substatus, now, new_hash, proposal_id),
        )
        conn.execute(
            """
            INSERT INTO transitions
                (proposal_id, from_column, to_column,
                 from_substatus, to_substatus,
                 approver, reason, gate_passed, gate_details, archive_hash, ts)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                proposal_id,
                from_column,
                target_column,
                from_substatus,
                target_substatus,
                approver,
                reason,
                gate_passed,
                details_json,
                archive_hash,
                now,
            ),
        )
        updated = conn.execute(
            "SELECT * FROM cards WHERE proposal_id = ?",
            (proposal_id,),
        ).fetchone()
        return _row_to_card(updated)


def _delete_card_sync(db_path: Path, proposal_id: str) -> bool:
    """Delete a card and its history. Returns True if a card was deleted."""
    with _connect(db_path) as conn:
        existing = conn.execute(
            "SELECT 1 FROM cards WHERE proposal_id = ?",
            (proposal_id,),
        ).fetchone()
        if existing is None:
            return False
        conn.execute("DELETE FROM transitions WHERE proposal_id = ?", (proposal_id,))
        cursor = conn.execute("DELETE FROM cards WHERE proposal_id = ?", (proposal_id,))
        return cursor.rowcount > 0


def _get_card_sync(db_path: Path, proposal_id: str) -> Optional[Card]:
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM cards WHERE proposal_id = ?",
            (proposal_id,),
        ).fetchone()
        return _row_to_card(row) if row else None


def _get_board_sync(db_path: Path) -> BoardSnapshot:
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM cards ORDER BY updated_ts DESC"
        ).fetchall()

    by_column: dict[str, List[Card]] = {col: [] for col in CANONICAL_COLUMNS}
    for row in rows:
        card = _row_to_card(row)
        # Defensive: a row with an unexpected column is logged + skipped, not
        # silently re-bucketed. We'd rather the API surface a hole than lie.
        bucket = by_column.get(card.column_name)
        if bucket is None:
            logger.warning(
                "kanban_store: card %s has unknown column %r; dropping from snapshot",
                card.proposal_id,
                card.column_name,
            )
            continue
        bucket.append(card)

    columns = [Column(name=col, cards=by_column[col]) for col in CANONICAL_COLUMNS]
    return BoardSnapshot(
        columns=columns,
        generated_at=_utcnow_iso(),
    )


def _history_sync(
    db_path: Path,
    proposal_id: str,
    limit: Optional[int],
) -> List[Transition]:
    with _connect(db_path) as conn:
        if limit is None:
            rows = conn.execute(
                "SELECT * FROM transitions WHERE proposal_id = ? ORDER BY ts ASC",
                (proposal_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM transitions WHERE proposal_id = ? ORDER BY ts DESC LIMIT ?",
                (proposal_id, limit),
            ).fetchall()
            rows = list(reversed(rows))
    return [_row_to_transition(r) for r in rows]


def _backup_sync(db_path: Path, backup_dir: Path) -> Path:
    """Take a backup via ``VACUUM INTO``. Returns the path written."""
    if not db_path.exists():
        raise KanbanStoreError(
            f"Cannot backup non-existent database: {db_path}"
        )
    backup_dir.mkdir(parents=True, exist_ok=True)
    # Microsecond precision — second-precision was tight enough for two
    # backups in the same second (e.g. during rotation tests) to collide
    # on ``VACUUM INTO`` (it refuses to overwrite).
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%f")
    out = backup_dir / f"kanban_state_{ts}.sqlite"
    with _connect(db_path) as conn:
        # SQL injection-safe: ``out`` is constructed by us; we still
        # round-trip through a sanitised string (no quotes possible).
        # VACUUM INTO requires a literal path.
        conn.execute(f"VACUUM INTO '{out.as_posix()}'")
    # Rotate: keep the latest BACKUP_RETAIN
    snapshots = sorted(
        backup_dir.glob("kanban_state_*.sqlite"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for stale in snapshots[BACKUP_RETAIN:]:
        try:
            stale.unlink()
        except OSError as exc:
            logger.warning("kanban_store: failed to delete stale backup %s: %r", stale, exc)
    return out


# ════════════════════════════════════════════════════════════════════
#  Async public API
# ════════════════════════════════════════════════════════════════════


class KanbanStore:
    """Async-safe handle to the kanban SQLite store.

    The store is process-local; each FastAPI worker / CLI command should
    instantiate one and reuse it. Concurrency is handled by sqlite3's
    own locking — we don't add our own.

    Pass ``db_path`` to override the default (mostly for tests; production
    callers use the module-level default).
    """

    def __init__(
        self,
        db_path: Optional[Path] = None,
        backup_dir: Optional[Path] = None,
    ) -> None:
        self.db_path = (db_path or KANBAN_DB_PATH).resolve()
        self.backup_dir = (backup_dir or KANBAN_BACKUP_DIR).resolve()

    # ----------------------------------------------------------------
    #  Schema
    # ----------------------------------------------------------------

    async def init_schema(self) -> None:
        """Create tables + indexes if they don't exist. Idempotent."""
        await asyncio.to_thread(_init_schema_sync, self.db_path)

    # ----------------------------------------------------------------
    #  Cards
    # ----------------------------------------------------------------

    async def add_card(
        self,
        *,
        proposal_id: str,
        prefix: str,
        column_name: str,
        title: Optional[str] = None,
        substatus: Optional[str] = None,
        severity: Optional[str] = None,
        origin: Optional[str] = None,
        keywords: Optional[str] = None,
        approver: str = "system",
        reason: Optional[str] = None,
    ) -> Card:
        """Insert a new card. Idempotent: returns the existing card if one
        already exists with the same ``proposal_id`` (use :meth:`move_card`
        to actually change state).

        Also writes a transitions row with ``from_column = NULL`` so the
        history correctly shows the creation event.
        """
        return await asyncio.to_thread(
            _add_card_sync,
            self.db_path,
            proposal_id=proposal_id,
            prefix=prefix,
            column_name=column_name,
            title=title,
            substatus=substatus,
            severity=severity,
            origin=origin,
            keywords=keywords,
            approver=approver,
            reason=reason,
        )

    async def move_card(
        self,
        *,
        proposal_id: str,
        target_column: str,
        target_substatus: Optional[str] = None,
        approver: str,
        reason: Optional[str] = None,
        gate_passed: int = 0,
        gate_details: Optional[dict] = None,
        archive_hash: Optional[str] = None,
    ) -> Card:
        """Move a card to a new column / substatus.

        Writes one transitions row. Raises :class:`CardNotFound` if the
        card doesn't exist. Use :meth:`add_card` first for new cards.

        ``gate_passed`` follows the proposal's tri-state convention:
        ``-1`` failed, ``0`` not applicable, ``1`` passed.
        """
        return await asyncio.to_thread(
            _move_card_sync,
            self.db_path,
            proposal_id=proposal_id,
            target_column=target_column,
            target_substatus=target_substatus,
            approver=approver,
            reason=reason,
            gate_passed=gate_passed,
            gate_details=gate_details,
            archive_hash=archive_hash,
        )

    async def get_card(self, proposal_id: str) -> Optional[Card]:
        """Return one card by id, or ``None`` if not found."""
        return await asyncio.to_thread(_get_card_sync, self.db_path, proposal_id)

    async def update_card(self, proposal_id: str, updates: dict) -> Card:
        """Update fields on an existing card."""
        return await asyncio.to_thread(
            _update_card_sync, self.db_path, proposal_id, updates
        )

    async def delete_card(self, proposal_id: str) -> bool:
        """Delete a card and its entire transition history.

        Returns:
            True if a card was found and deleted, False otherwise.
        """
        return await asyncio.to_thread(
            _delete_card_sync, self.db_path, proposal_id
        )

    # ----------------------------------------------------------------
    #  Board snapshot
    # ----------------------------------------------------------------

    async def get_board(self) -> BoardSnapshot:
        """Return the entire board grouped by column.

        Columns are always returned in :data:`CANONICAL_COLUMNS` order,
        even when empty. Cards within a column are sorted by ``updated_ts``
        DESC (most recently touched first).
        """
        return await asyncio.to_thread(_get_board_sync, self.db_path)

    # ----------------------------------------------------------------
    #  History
    # ----------------------------------------------------------------

    async def history(
        self,
        proposal_id: str,
        limit: Optional[int] = None,
    ) -> List[Transition]:
        """Return all transitions for ``proposal_id``, chronological.

        When ``limit`` is given, returns the LAST ``limit`` transitions
        (still in chronological order). This is what the dashboard's
        "history drawer" needs — pass ``limit=10`` per the proposal spec.
        """
        return await asyncio.to_thread(
            _history_sync, self.db_path, proposal_id, limit
        )

    # ----------------------------------------------------------------
    #  Backup
    # ----------------------------------------------------------------

    async def backup(self) -> Path:
        """Snapshot the DB via ``VACUUM INTO``. Rotates to keep
        :data:`BACKUP_RETAIN` most recent. Returns the path written.
        """
        return await asyncio.to_thread(_backup_sync, self.db_path, self.backup_dir)


__all__ = [
    # Constants
    "KANBAN_DB_PATH",
    "KANBAN_BACKUP_DIR",
    "BACKUP_RETAIN",
    "CANONICAL_COLUMNS",
    "KNOWN_PREFIXES",
    # Dataclasses
    "Card",
    "Column",
    "Transition",
    "BoardSnapshot",
    # Errors
    "KanbanStoreError",
    "CardNotFound",
    "InvalidColumn",
    "InvalidPrefix",
    # Class
    "KanbanStore",
]
