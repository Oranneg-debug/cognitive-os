"""Unit tests for ``src.kanban_renderer`` — ARCH-DA5B0A2D Section A (A2).

Covers ``render()`` purity, the Obsidian-kanban-plugin format invariants,
and ``write_vault_mirror`` atomicity / no-op short-circuit.

All filesystem writes go to ``tmp_path``; the real
``E:\\Oranneg\\…\\Dev-KanBan.md`` is never touched.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from src.kanban_renderer import (
    AUTOGEN_PREFIX,
    KANBAN_PLUGIN_HEADER,
    render,
    write_vault_mirror,
    _block_ref,
    _iso_to_kanban_date,
    _render_status,
)
from src.kanban_store import (
    CANONICAL_COLUMNS,
    BoardSnapshot,
    Card,
    Column,
)


# ════════════════════════════════════════════════════════════════════
#  Helpers
# ════════════════════════════════════════════════════════════════════


def _make_card(
    proposal_id: str,
    column_name: str,
    *,
    prefix: str = "ARCH",
    title: str = "Sample card",
    substatus: str | None = None,
    severity: str | None = "medium",
    origin: str | None = None,
    created_ts: str = "2026-05-25T10:00:00+00:00",
    updated_ts: str = "2026-05-25T10:00:00+00:00",
    state_hash: str = "deadbeefcafef00d",
) -> Card:
    return Card(
        proposal_id=proposal_id,
        prefix=prefix,
        title=title,
        column_name=column_name,
        substatus=substatus,
        severity=severity,
        origin=origin,
        created_ts=created_ts,
        updated_ts=updated_ts,
        state_hash=state_hash,
    )


def _make_snapshot(cards_by_column: dict[str, list[Card]]) -> BoardSnapshot:
    """Build a snapshot from a {column_name: [Card, …]} map.

    Columns not in the map are emitted empty (per the renderer contract:
    all six canonical columns always appear).
    """
    columns = [
        Column(name=col, cards=cards_by_column.get(col, []))
        for col in CANONICAL_COLUMNS
    ]
    return BoardSnapshot(columns=columns, generated_at="2026-05-25T12:00:00+00:00")


# ════════════════════════════════════════════════════════════════════
#  Frontmatter + autogen marker invariants
# ════════════════════════════════════════════════════════════════════


def test_render_emits_obsidian_kanban_frontmatter():
    """A2.1 — output starts with the exact ``---\\nkanban-plugin: board\\n---`` block."""
    rendered = render(_make_snapshot({}))
    assert rendered.startswith(f"---\n{KANBAN_PLUGIN_HEADER}\n---\n")


def test_render_includes_autogen_marker_with_timestamp():
    """A2.2 — the autogen marker is present and carries the snapshot's generated_at."""
    snap = _make_snapshot({})
    rendered = render(snap)
    assert AUTOGEN_PREFIX in rendered
    assert snap.generated_at in rendered
    assert "Drag cards in the dashboard" in rendered


def test_render_is_deterministic():
    """A2.3 — same snapshot → byte-identical output (no time/random in render())."""
    snap = _make_snapshot({
        "proposal": [_make_card("ARCH-DET-1", "proposal")],
    })
    assert render(snap) == render(snap)


def test_render_ends_with_newline():
    """A2.4 — output is well-terminated for git's final-newline checks + ``wc -l``."""
    rendered = render(_make_snapshot({}))
    assert rendered.endswith("\n")


# ════════════════════════════════════════════════════════════════════
#  Column structure
# ════════════════════════════════════════════════════════════════════


def test_render_emits_all_six_columns_in_canonical_order():
    """A2.5 — even an empty board has six ``## <Title>`` headers in the right order."""
    rendered = render(_make_snapshot({}))
    # Find each header in order, locations must be ascending
    expected_titles = [
        "## Backlog",
        "## Proposal",
        "## Beta Testing",
        "## Alpha Polish",
        "## Finalized",
        "## Deployed",
    ]
    positions = [rendered.find(h) for h in expected_titles]
    assert all(p >= 0 for p in positions), f"missing header(s); positions={positions}"
    assert positions == sorted(positions), "column headers not in canonical order"


def test_render_empty_columns_have_no_cards():
    """A2.6 — empty columns get their header but zero ``- [ ]`` lines underneath."""
    rendered = render(_make_snapshot({"backlog": [_make_card("ARCH-EMPTY-1", "backlog")]}))
    # Slice the rendered output between "## Proposal" and "## Beta Testing".
    start = rendered.find("## Proposal")
    end = rendered.find("## Beta Testing")
    proposal_block = rendered[start:end]
    assert "- [ ]" not in proposal_block


# ════════════════════════════════════════════════════════════════════
#  Card rendering
# ════════════════════════════════════════════════════════════════════


def test_render_card_includes_id_title_blockref():
    """A2.7 — each card line carries proposal_id, em-dash, title, block ref."""
    snap = _make_snapshot({"proposal": [_make_card(
        "ARCH-CARD-1", "proposal", title="Migrate kanban to SQLite"
    )]})
    rendered = render(snap)
    assert "- [ ] ARCH-CARD-1 — Migrate kanban to SQLite" in rendered
    # Block ref present
    assert "^[ARCHCARD1]" in rendered


def test_render_card_emits_block_ref_only_once():
    """A2.8 — regression guard for the legacy bug that duplicated ^[…] 12 times."""
    snap = _make_snapshot({"proposal": [_make_card("ARCH-ONCE-1", "proposal")]})
    rendered = render(snap)
    assert rendered.count("^[ARCHONCE1]") == 1


def test_render_card_with_substatus_uses_friendly_label():
    """A2.9 — known substatus values map to emoji+label."""
    snap = _make_snapshot({"beta testing": [_make_card(
        "ARCH-SUB-1", "beta testing", substatus="planning"
    )]})
    rendered = render(snap)
    assert "📋 Planning" in rendered


def test_render_card_with_unknown_substatus_emits_verbatim():
    """A2.10 — unknown substatus passes through (forward-compatibility)."""
    snap = _make_snapshot({"beta testing": [_make_card(
        "ARCH-SUB-2", "beta testing", substatus="weird_new_substatus"
    )]})
    rendered = render(snap)
    assert "weird_new_substatus" in rendered


def test_render_card_without_substatus_uses_pending_label():
    """A2.11 — no substatus → ⏳ Pending (legacy default)."""
    snap = _make_snapshot({"backlog": [_make_card("ARCH-NSUB-1", "backlog")]})
    rendered = render(snap)
    assert "status: ⏳ Pending" in rendered


def test_render_card_skips_empty_optional_fields():
    """A2.12 — origin/severity lines are omitted when fields are None.

    Severity is supplied as None here (overrides helper default); origin
    is None by default.
    """
    snap = _make_snapshot({"backlog": [_make_card(
        "ARCH-OPT-1", "backlog", severity=None, origin=None
    )]})
    rendered = render(snap)
    # Slice the card block
    card_block_start = rendered.find("- [ ] ARCH-OPT-1")
    card_block = rendered[card_block_start:card_block_start + 500]
    assert "severity:" not in card_block
    assert "origin:" not in card_block


def test_render_card_emits_updated_only_when_different_from_created():
    """A2.13 — fresh cards (created == updated) get one date line; touched cards get two."""
    fresh = _make_card("ARCH-DATES-1", "backlog",
                       created_ts="2026-05-25T10:00:00+00:00",
                       updated_ts="2026-05-25T10:00:00+00:00")
    touched = _make_card("ARCH-DATES-2", "backlog",
                         created_ts="2026-05-24T10:00:00+00:00",
                         updated_ts="2026-05-25T10:00:00+00:00")
    snap = _make_snapshot({"backlog": [fresh, touched]})
    rendered = render(snap)

    # Slice each card's block separately
    fresh_block = rendered[rendered.find("ARCH-DATES-1"):rendered.find("ARCH-DATES-2")]
    touched_block = rendered[rendered.find("ARCH-DATES-2"):]
    assert fresh_block.count("created:") == 1
    assert "updated:" not in fresh_block
    assert touched_block.count("created:") == 1
    assert touched_block.count("updated:") == 1


def test_render_card_iso_dates_are_trimmed_to_date_only():
    """A2.14 — ``T``-portion of the ISO timestamp is stripped for readability."""
    card = _make_card("ARCH-DATE-FMT", "backlog",
                      created_ts="2026-05-25T13:45:30.123456+00:00")
    rendered = render(_make_snapshot({"backlog": [card]}))
    assert "created: 2026-05-25" in rendered
    assert "T13:45" not in rendered


def test_render_card_includes_proposal_wikilink():
    """A2.15 — ``[[<id>_PROPOSAL]]`` link is always emitted last."""
    snap = _make_snapshot({"backlog": [_make_card("ARCH-LINK-1", "backlog")]})
    rendered = render(snap)
    assert "[[ARCH-LINK-1_PROPOSAL]]" in rendered


# ════════════════════════════════════════════════════════════════════
#  Helper functions (direct unit tests)
# ════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(("pid", "expected"), [
    ("ARCH-20260522-205800-DA5B0A2D", "^[ARCH20260522205800DA5B0A2D]"),
    ("DEV-001", "^[DEV001]"),
    ("NLST-X", "^[NLSTX]"),
])
def test_block_ref_strips_all_hyphens(pid: str, expected: str):
    """A2.16 — block-ref label has no hyphens (Obsidian block-id charset)."""
    assert _block_ref(pid) == expected


@pytest.mark.parametrize(("iso", "expected"), [
    ("2026-05-25T10:00:00+00:00", "2026-05-25"),
    ("2026-05-25T10:00:00.123456", "2026-05-25"),
    ("2026-05-25", "2026-05-25"),
    ("", ""),
])
def test_iso_to_kanban_date(iso: str, expected: str):
    """A2.17 — ISO date trimming handles common shapes + empty input."""
    assert _iso_to_kanban_date(iso) == expected


def test_render_status_handles_none_known_and_unknown():
    """A2.18 — _render_status: None → ⏳, known → emoji+label, unknown → verbatim."""
    assert _render_status(_make_card("X", "backlog", substatus=None)) == "⏳ Pending"
    assert _render_status(_make_card("X", "backlog", substatus="planning")) == "📋 Planning"
    assert _render_status(_make_card("X", "backlog", substatus="brand_new_thing")) == "brand_new_thing"


# ════════════════════════════════════════════════════════════════════
#  write_vault_mirror
# ════════════════════════════════════════════════════════════════════


def test_write_vault_mirror_creates_file(tmp_path: Path):
    """A2.19 — first write creates the target file with rendered content."""
    target = tmp_path / "Dev-KanBan.md"
    snap = _make_snapshot({"proposal": [_make_card("ARCH-W-1", "proposal")]})
    out = write_vault_mirror(snap, path=target)
    assert out == target.resolve()
    assert target.exists()
    written = target.read_text(encoding="utf-8")
    assert written == render(snap)


def test_write_vault_mirror_creates_parent_dir(tmp_path: Path):
    """A2.20 — write through a missing parent dir works."""
    target = tmp_path / "deep" / "deeper" / "Dev-KanBan.md"
    snap = _make_snapshot({})
    write_vault_mirror(snap, path=target)
    assert target.exists()


def test_write_vault_mirror_is_atomic_no_tmp_leak(tmp_path: Path):
    """A2.21 — after a successful write, no .tmp_ files remain in the target dir."""
    target = tmp_path / "Dev-KanBan.md"
    write_vault_mirror(_make_snapshot({}), path=target)
    leftover_tmp = [p for p in tmp_path.iterdir() if p.name.startswith(".tmp_")]
    assert leftover_tmp == [], f"tmp files leaked: {leftover_tmp}"


def test_write_vault_mirror_skips_when_content_unchanged(tmp_path: Path):
    """A2.22 — content-equality short-circuit prevents spurious mtime bumps."""
    target = tmp_path / "Dev-KanBan.md"
    snap = _make_snapshot({"backlog": [_make_card("ARCH-NOWRITE-1", "backlog")]})

    write_vault_mirror(snap, path=target)
    first_mtime = target.stat().st_mtime_ns

    # Sleep-free: instead of waiting for clock tick, we just rewrite and
    # assert that the mtime did NOT advance. (Filesystems with sub-ms
    # resolution would tick even on a no-op write; we want the explicit
    # short-circuit, not luck.)
    import time
    time.sleep(0.01)  # ensure clock would advance if a write happened
    write_vault_mirror(snap, path=target)
    second_mtime = target.stat().st_mtime_ns

    assert first_mtime == second_mtime, "unchanged-content write was not skipped"


def test_write_vault_mirror_overwrites_on_content_change(tmp_path: Path):
    """A2.23 — a different snapshot DOES produce a fresh write."""
    target = tmp_path / "Dev-KanBan.md"

    snap_a = _make_snapshot({"backlog": [_make_card("ARCH-CH-1", "backlog")]})
    snap_b = _make_snapshot({"backlog": [_make_card("ARCH-CH-2", "backlog")]})

    write_vault_mirror(snap_a, path=target)
    written_a = target.read_text(encoding="utf-8")
    write_vault_mirror(snap_b, path=target)
    written_b = target.read_text(encoding="utf-8")

    assert written_a != written_b
    assert "ARCH-CH-1" not in written_b
    assert "ARCH-CH-2" in written_b
