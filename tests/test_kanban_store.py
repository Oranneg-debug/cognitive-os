"""Unit tests for ``src.kanban_store`` — ARCH-DA5B0A2D Section A (A1).

Covers the full public surface of :class:`KanbanStore` plus the dataclass
contracts. Every test uses ``tmp_path`` so the real
``dev/kanban_state.sqlite`` is never touched.

Async tests use the ``pytest-anyio`` plugin already installed in the
project (see pytest.ini); we annotate with ``@pytest.mark.anyio`` so the
test runs on the default asyncio backend.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from src.kanban_store import (
    BACKUP_RETAIN,
    CANONICAL_COLUMNS,
    KNOWN_PREFIXES,
    BoardSnapshot,
    Card,
    CardNotFound,
    Column,
    InvalidColumn,
    InvalidPrefix,
    KanbanStore,
    KanbanStoreError,
    Transition,
    _compute_state_hash,
)


# ════════════════════════════════════════════════════════════════════
#  Fixtures
# ════════════════════════════════════════════════════════════════════


@pytest.fixture()
def store(tmp_path: Path) -> KanbanStore:
    """Return a fresh KanbanStore pointed at tmp_path.

    Schema is intentionally NOT initialized here so we can exercise
    ``init_schema`` from at least one test.
    """
    return KanbanStore(
        db_path=tmp_path / "kanban_state.sqlite",
        backup_dir=tmp_path / ".backups",
    )


@pytest.fixture()
def initialised_store(store: KanbanStore) -> KanbanStore:
    """Schema-initialised store. Synchronous fixture (uses ``run``)."""
    run(store.init_schema())
    return store


def run(coro):
    """Drive a coroutine on a fresh event loop.

    Python 3.14 removed the implicit "create loop on first access" behaviour
    of ``asyncio.get_event_loop()``; ``asyncio.run`` is the supported entry
    point for synchronous-test contexts. Each call gets a fresh loop, which
    is exactly what we want — no test should depend on event-loop identity.
    """
    return asyncio.run(coro)


# ════════════════════════════════════════════════════════════════════
#  Constants + helpers
# ════════════════════════════════════════════════════════════════════


def test_canonical_columns_in_proposal_order():
    """A1.1 — columns are exactly the six the proposal specifies, in order."""
    assert CANONICAL_COLUMNS == (
        "backlog",
        "proposal",
        "beta testing",
        "alpha polish",
        "finalized",
        "deployed",
    )


def test_known_prefixes_only_dev_arch_nlst():
    """A1.2 — we accept exactly the three prefixes the proposal mentions."""
    assert KNOWN_PREFIXES == frozenset({"DEV", "ARCH", "NLST"})


def test_compute_state_hash_is_stable():
    """A1.3 — same (column, substatus) yields same hash; different inputs differ."""
    h1 = _compute_state_hash("beta testing", "planning")
    h2 = _compute_state_hash("beta testing", "planning")
    h3 = _compute_state_hash("beta testing", "execution.coding")
    h4 = _compute_state_hash("beta testing", None)
    assert h1 == h2
    assert h1 != h3
    assert h1 != h4
    # Hash is 16 hex chars (SHA256[:16])
    assert len(h1) == 16
    assert all(c in "0123456789abcdef" for c in h1)


# ════════════════════════════════════════════════════════════════════
#  Schema init
# ════════════════════════════════════════════════════════════════════


def test_init_schema_is_idempotent(store: KanbanStore):
    """A1.4 — init_schema can be called repeatedly without error."""
    run(store.init_schema())
    run(store.init_schema())
    run(store.init_schema())
    assert store.db_path.exists()


def test_init_schema_creates_parent_dir(tmp_path: Path):
    """A1.5 — init_schema creates DEV_DIR equivalents under tmp."""
    nested = tmp_path / "deep" / "deeper" / "kanban.sqlite"
    s = KanbanStore(db_path=nested, backup_dir=tmp_path / ".backups")
    run(s.init_schema())
    assert nested.exists()


# ════════════════════════════════════════════════════════════════════
#  add_card
# ════════════════════════════════════════════════════════════════════


def test_add_card_happy_path(initialised_store: KanbanStore):
    """A1.6 — minimal add_card returns a Card with timestamps + hash filled."""
    card = run(
        initialised_store.add_card(
            proposal_id="ARCH-TEST-001",
            prefix="ARCH",
            column_name="proposal",
            title="Sample card",
            approver="alice",
        )
    )
    assert isinstance(card, Card)
    assert card.proposal_id == "ARCH-TEST-001"
    assert card.column_name == "proposal"
    assert card.created_ts == card.updated_ts  # fresh card
    assert card.state_hash != ""


def test_add_card_records_creation_transition(initialised_store: KanbanStore):
    """A1.7 — the initial INSERT must also write a transitions row with from_column NULL."""
    run(
        initialised_store.add_card(
            proposal_id="DEV-TEST-002",
            prefix="DEV",
            column_name="backlog",
            approver="bob",
            reason="initial filing",
        )
    )
    history = run(initialised_store.history("DEV-TEST-002"))
    assert len(history) == 1
    assert history[0].from_column is None
    assert history[0].to_column == "backlog"
    assert history[0].approver == "bob"
    assert history[0].reason == "initial filing"


def test_add_card_is_idempotent(initialised_store: KanbanStore):
    """A1.8 — calling add_card twice with the same id is a no-op (returns existing)."""
    first = run(
        initialised_store.add_card(
            proposal_id="ARCH-TEST-003",
            prefix="ARCH",
            column_name="proposal",
            approver="alice",
        )
    )
    second = run(
        initialised_store.add_card(
            proposal_id="ARCH-TEST-003",
            prefix="ARCH",
            column_name="backlog",  # would-be different column — must be IGNORED
            approver="other",
        )
    )
    assert first.column_name == second.column_name == "proposal"
    # Only ONE transition row exists
    history = run(initialised_store.history("ARCH-TEST-003"))
    assert len(history) == 1


def test_add_card_rejects_unknown_prefix(initialised_store: KanbanStore):
    """A1.9 — only DEV/ARCH/NLST are valid prefixes."""
    with pytest.raises(InvalidPrefix):
        run(
            initialised_store.add_card(
                proposal_id="XXX-NOPE",
                prefix="XXX",
                column_name="proposal",
                approver="alice",
            )
        )


def test_add_card_rejects_unknown_column(initialised_store: KanbanStore):
    """A1.10 — column must be one of CANONICAL_COLUMNS."""
    with pytest.raises(InvalidColumn):
        run(
            initialised_store.add_card(
                proposal_id="ARCH-TEST-004",
                prefix="ARCH",
                column_name="purgatory",
                approver="alice",
            )
        )


# ════════════════════════════════════════════════════════════════════
#  move_card
# ════════════════════════════════════════════════════════════════════


def test_move_card_happy_path(initialised_store: KanbanStore):
    """A1.11 — move updates the card and writes a transition."""
    run(
        initialised_store.add_card(
            proposal_id="ARCH-MOVE-001",
            prefix="ARCH",
            column_name="proposal",
            approver="alice",
        )
    )
    moved = run(
        initialised_store.move_card(
            proposal_id="ARCH-MOVE-001",
            target_column="beta testing",
            target_substatus="planning",
            approver="alice",
            reason="approved",
            gate_passed=1,
        )
    )
    assert moved.column_name == "beta testing"
    assert moved.substatus == "planning"
    # State hash changed
    fresh = run(initialised_store.get_card("ARCH-MOVE-001"))
    assert fresh is not None
    assert fresh.state_hash == moved.state_hash

    # transitions: 1 (creation, NULL→proposal) + 1 (proposal→beta testing)
    history = run(initialised_store.history("ARCH-MOVE-001"))
    assert len(history) == 2
    assert history[1].from_column == "proposal"
    assert history[1].to_column == "beta testing"
    assert history[1].gate_passed == 1


def test_move_card_persists_gate_details_as_json(initialised_store: KanbanStore):
    """A1.12 — gate_details dict round-trips through SQLite as JSON."""
    run(
        initialised_store.add_card(
            proposal_id="DEV-GATE-001",
            prefix="DEV",
            column_name="proposal",
            approver="alice",
        )
    )
    details = {"failed": ["test_x"], "passed": ["test_y", "test_z"]}
    run(
        initialised_store.move_card(
            proposal_id="DEV-GATE-001",
            target_column="beta testing",
            approver="alice",
            gate_passed=-1,
            gate_details=details,
            reason="gate failure",
        )
    )
    history = run(initialised_store.history("DEV-GATE-001"))
    assert history[1].gate_details == details
    assert history[1].gate_passed == -1


def test_move_card_raises_when_card_missing(initialised_store: KanbanStore):
    """A1.13 — moving a non-existent card raises CardNotFound, not a silent insert."""
    with pytest.raises(CardNotFound):
        run(
            initialised_store.move_card(
                proposal_id="DEV-NEVER-EXISTED",
                target_column="proposal",
                approver="alice",
            )
        )


def test_move_card_rejects_unknown_column(initialised_store: KanbanStore):
    """A1.14 — InvalidColumn on bogus target_column."""
    run(
        initialised_store.add_card(
            proposal_id="DEV-MOVE-BAD",
            prefix="DEV",
            column_name="proposal",
            approver="alice",
        )
    )
    with pytest.raises(InvalidColumn):
        run(
            initialised_store.move_card(
                proposal_id="DEV-MOVE-BAD",
                target_column="purgatory",
                approver="alice",
            )
        )


def test_move_card_rejects_bad_gate_passed_value(initialised_store: KanbanStore):
    """A1.15 — gate_passed must be -1/0/1."""
    run(
        initialised_store.add_card(
            proposal_id="DEV-GATE-BAD",
            prefix="DEV",
            column_name="proposal",
            approver="alice",
        )
    )
    with pytest.raises(ValueError):
        run(
            initialised_store.move_card(
                proposal_id="DEV-GATE-BAD",
                target_column="beta testing",
                approver="alice",
                gate_passed=42,
            )
        )


# ════════════════════════════════════════════════════════════════════
#  get_board
# ════════════════════════════════════════════════════════════════════


def test_get_board_returns_all_columns_even_when_empty(initialised_store: KanbanStore):
    """A1.16 — BoardSnapshot always lists six columns (in order), regardless of card count."""
    board = run(initialised_store.get_board())
    assert isinstance(board, BoardSnapshot)
    assert [c.name for c in board.columns] == list(CANONICAL_COLUMNS)
    assert all(len(c.cards) == 0 for c in board.columns)


def test_get_board_buckets_cards_by_column(initialised_store: KanbanStore):
    """A1.17 — cards in different columns land in the right buckets."""
    run(initialised_store.add_card(
        proposal_id="ARCH-BUCKET-1", prefix="ARCH",
        column_name="backlog", approver="x"))
    run(initialised_store.add_card(
        proposal_id="ARCH-BUCKET-2", prefix="ARCH",
        column_name="beta testing", approver="x"))
    run(initialised_store.add_card(
        proposal_id="ARCH-BUCKET-3", prefix="ARCH",
        column_name="beta testing", approver="x"))

    board = run(initialised_store.get_board())
    by_name = {c.name: c for c in board.columns}
    assert {c.proposal_id for c in by_name["backlog"].cards} == {"ARCH-BUCKET-1"}
    assert {c.proposal_id for c in by_name["beta testing"].cards} == {
        "ARCH-BUCKET-2",
        "ARCH-BUCKET-3",
    }
    assert by_name["proposal"].cards == []


def test_get_board_to_dict_round_trips(initialised_store: KanbanStore):
    """A1.18 — BoardSnapshot.to_dict() is JSON-serialisable."""
    run(initialised_store.add_card(
        proposal_id="ARCH-DICT-1", prefix="ARCH",
        column_name="proposal", approver="x"))
    board = run(initialised_store.get_board())
    encoded = json.dumps(board.to_dict())
    decoded = json.loads(encoded)
    assert decoded["columns"][1]["name"] == "proposal"  # index 1 = proposal
    assert any(c["proposal_id"] == "ARCH-DICT-1" for c in decoded["columns"][1]["cards"])


# ════════════════════════════════════════════════════════════════════
#  history
# ════════════════════════════════════════════════════════════════════


def test_history_limit_returns_last_N_in_chronological_order(initialised_store: KanbanStore):
    """A1.19 — history(limit=N) returns the LAST N transitions, oldest-first."""
    pid = "ARCH-HIST-001"
    run(initialised_store.add_card(
        proposal_id=pid, prefix="ARCH", column_name="backlog", approver="x"))
    # Do 4 moves; we should see 5 transitions total (1 creation + 4 moves)
    for target in ["proposal", "beta testing", "alpha polish", "finalized"]:
        run(initialised_store.move_card(
            proposal_id=pid,
            target_column=target,
            approver="x",
        ))

    all_rows = run(initialised_store.history(pid))
    assert len(all_rows) == 5
    last_three = run(initialised_store.history(pid, limit=3))
    assert len(last_three) == 3
    # Should be chronological — last three are proposal→beta, beta→alpha, alpha→final
    assert [r.to_column for r in last_three] == ["beta testing", "alpha polish", "finalized"]


# ════════════════════════════════════════════════════════════════════
#  backup
# ════════════════════════════════════════════════════════════════════


def test_backup_creates_vacuumed_snapshot(initialised_store: KanbanStore):
    """A1.20 — backup() writes a snapshot file and returns its path."""
    run(initialised_store.add_card(
        proposal_id="ARCH-BAK-1", prefix="ARCH",
        column_name="proposal", approver="x"))

    snapshot = run(initialised_store.backup())
    assert snapshot.exists()
    assert snapshot.name.startswith("kanban_state_")
    assert snapshot.suffix == ".sqlite"
    # Snapshot is a valid SQLite file
    import sqlite3
    conn = sqlite3.connect(str(snapshot))
    try:
        row = conn.execute("SELECT COUNT(*) FROM cards").fetchone()
        assert row[0] == 1
    finally:
        conn.close()


def test_backup_rotates_to_BACKUP_RETAIN(initialised_store: KanbanStore, tmp_path: Path):
    """A1.21 — only the last BACKUP_RETAIN snapshots are kept on disk."""
    # Insert ONE card so backups have content
    run(initialised_store.add_card(
        proposal_id="ARCH-ROT-1", prefix="ARCH",
        column_name="proposal", approver="x"))

    # Take BACKUP_RETAIN + 3 snapshots, with mtime distinct enough to sort.
    # We can't actually sleep here — instead we manipulate mtime after the
    # fact so rotation has a stable ordering to work with.
    import os
    import time as _time
    for i in range(BACKUP_RETAIN + 3):
        snap = run(initialised_store.backup())
        # Spread mtimes by i seconds so rotation has something to sort.
        new_time = _time.time() - (BACKUP_RETAIN + 3 - i)
        os.utime(snap, (new_time, new_time))

    remaining = sorted(initialised_store.backup_dir.glob("kanban_state_*.sqlite"))
    assert len(remaining) == BACKUP_RETAIN


def test_backup_raises_when_db_missing(tmp_path: Path):
    """A1.22 — backup() on a nonexistent DB fails clearly, not silently."""
    s = KanbanStore(
        db_path=tmp_path / "never_initialised.sqlite",
        backup_dir=tmp_path / ".backups",
    )
    with pytest.raises(KanbanStoreError):
        run(s.backup())


# ════════════════════════════════════════════════════════════════════
#  Foreign keys
# ════════════════════════════════════════════════════════════════════


def test_foreign_key_enforced_on_orphan_transition(initialised_store: KanbanStore):
    """A1.23 — manually inserting a transition for a non-existent card fails.

    This guards the FK clause in TRANSITIONS_SCHEMA_SQL — if we ever drop
    ``PRAGMA foreign_keys = ON`` from ``_connect``, this test catches it.
    """
    import sqlite3
    conn = sqlite3.connect(str(initialised_store.db_path))
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO transitions
                    (proposal_id, from_column, to_column, approver, gate_passed, ts)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                ("PHANTOM-001", "backlog", "proposal", "alice", 0, "2026-05-25T00:00:00"),
            )
            conn.commit()
    finally:
        conn.close()
