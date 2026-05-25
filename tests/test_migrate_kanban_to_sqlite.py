"""Unit tests for ``scripts/migrate_kanban_to_sqlite.py`` — ARCH-DA5B0A2D B1.

Exercises the parsing, planning, and apply paths against synthetic vault
files in ``tmp_path``. The real ``Dev-KanBan.md`` and
``dev/proposals/`` are never read; the real SQLite is never written.
"""

from __future__ import annotations

import asyncio
import importlib
import sys
from pathlib import Path

import pytest

# Add scripts/ to import path so we can import the module by name
SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

migrate = importlib.import_module("migrate_kanban_to_sqlite")
from src.kanban_store import KanbanStore  # noqa: E402


# ════════════════════════════════════════════════════════════════════
#  Fixtures — build a minimal synthetic vault + proposals tree
# ════════════════════════════════════════════════════════════════════


@pytest.fixture()
def fake_vault(tmp_path: Path) -> Path:
    """Write a minimal Dev-KanBan.md with three cards across three columns."""
    body = """---
kanban-plugin: board
---

## Backlog

- [ ] DEV-20260101-000001-A0001 — first backlog card ^[DEVxxx]

## Proposal

- [ ] ARCH-20260102-000001-B0001 — second card; in review ^[ARCHxxx]

## Beta Testing

- [ ] NLST-20260103-000001-C0001 — third card ^[NLSTxxx]

## Alpha Polish

## Finalized

## Deployed
"""
    f = tmp_path / "Dev-KanBan.md"
    f.write_text(body, encoding="utf-8")
    return f


@pytest.fixture()
def fake_proposals(tmp_path: Path) -> Path:
    """Build a proposals/ dir with three matching files + one disk-only file."""
    d = tmp_path / "proposals"
    d.mkdir()

    def _write(pid: str, severity: str, origin: str, original: str) -> None:
        (d / f"{pid}_PROPOSAL.md").write_text(
            f"---\n"
            f"status: pending\n"
            f"severity: {severity}\n"
            f"origin: {origin}\n"
            f"original_request: \"{original}\"\n"
            f"---\n\n"
            f"# Body of {pid}\n",
            encoding="utf-8",
        )

    _write("DEV-20260101-000001-A0001", "high", "systems-architect", "First card body")
    _write("ARCH-20260102-000001-B0001", "medium", "user", "Second card body")
    _write("NLST-20260103-000001-C0001", "low", "auto", "Third card body")
    # Disk-only proposal (not on the board) — should be migrated to backlog.
    _write("DEV-20260104-000001-D0001", "medium", "systems-architect", "Disk-only card")

    return d


@pytest.fixture()
def isolated_store(tmp_path: Path) -> KanbanStore:
    """A KanbanStore rooted in tmp_path with the schema already created."""
    store = KanbanStore(
        db_path=tmp_path / "kanban_state.sqlite",
        backup_dir=tmp_path / ".backups",
    )
    asyncio.run(store.init_schema())
    return store


# ════════════════════════════════════════════════════════════════════
#  _parse_vault_kanban
# ════════════════════════════════════════════════════════════════════


def test_parse_vault_finds_three_cards_in_three_columns(fake_vault: Path):
    """B1.1 — the parser extracts all cards under their columns."""
    plans = migrate._parse_vault_kanban(fake_vault)
    by_id = {p.proposal_id: p for p in plans}
    assert len(plans) == 3
    assert by_id["DEV-20260101-000001-A0001"].column_name == "backlog"
    assert by_id["ARCH-20260102-000001-B0001"].column_name == "proposal"
    assert by_id["NLST-20260103-000001-C0001"].column_name == "beta testing"


def test_parse_vault_extracts_prefix_correctly(fake_vault: Path):
    """B1.2 — DEV/ARCH/NLST prefixes derived from proposal_id."""
    plans = migrate._parse_vault_kanban(fake_vault)
    by_id = {p.proposal_id: p for p in plans}
    assert by_id["DEV-20260101-000001-A0001"].prefix == "DEV"
    assert by_id["ARCH-20260102-000001-B0001"].prefix == "ARCH"
    assert by_id["NLST-20260103-000001-C0001"].prefix == "NLST"


def test_parse_vault_missing_file_returns_empty(tmp_path: Path):
    """B1.3 — missing vault file is non-fatal; returns []."""
    plans = migrate._parse_vault_kanban(tmp_path / "does-not-exist.md")
    assert plans == []


def test_parse_vault_dedupes_repeated_cards(tmp_path: Path):
    """B1.4 — a card listed twice (legacy bug) is collapsed."""
    f = tmp_path / "Dev-KanBan.md"
    f.write_text(
        "---\nkanban-plugin: board\n---\n\n## Backlog\n\n"
        "- [ ] DEV-20260101-000001-A0001 — first ^[X]\n"
        "- [ ] DEV-20260101-000001-A0001 — duplicate ^[Y]\n",
        encoding="utf-8",
    )
    plans = migrate._parse_vault_kanban(f)
    assert len(plans) == 1


# ════════════════════════════════════════════════════════════════════
#  _scan_proposals_dir
# ════════════════════════════════════════════════════════════════════


def test_scan_proposals_dir_finds_all_proposal_files(fake_proposals: Path):
    """B1.5 — every *_PROPOSAL.md is a plan in backlog."""
    plans = migrate._scan_proposals_dir(fake_proposals)
    assert len(plans) == 4
    assert all(p.column_name == "backlog" for p in plans)
    assert all(p.source == "proposals_dir" for p in plans)


def test_scan_proposals_dir_skips_files_without_id(tmp_path: Path):
    """B1.6 — files that don't match the ARCH/DEV/NLST regex are skipped silently."""
    d = tmp_path / "proposals"
    d.mkdir()
    (d / "junk_PROPOSAL.md").write_text("nothing")
    (d / "no_underscore.md").write_text("nothing")
    (d / "ARCH-20260101-000001-A0001_PROPOSAL.md").write_text(
        "---\nstatus: pending\n---\n",
        encoding="utf-8",
    )
    plans = migrate._scan_proposals_dir(d)
    assert len(plans) == 1
    assert plans[0].proposal_id == "ARCH-20260101-000001-A0001"


# ════════════════════════════════════════════════════════════════════
#  _merge_plans
# ════════════════════════════════════════════════════════════════════


def test_merge_plans_vault_takes_priority_for_column(
    fake_vault: Path, fake_proposals: Path
):
    """B1.7 — when a card is in BOTH vault and disk, vault's column wins."""
    vault_plans = migrate._parse_vault_kanban(fake_vault)
    disk_plans = migrate._scan_proposals_dir(fake_proposals)
    merged = migrate._merge_plans(vault_plans, disk_plans)
    by_id = {p.proposal_id: p for p in merged}
    # The three cards that are in both → keep vault's column (not "backlog")
    assert by_id["NLST-20260103-000001-C0001"].column_name == "beta testing"
    assert by_id["ARCH-20260102-000001-B0001"].column_name == "proposal"


def test_merge_plans_disk_only_lands_in_backlog(
    fake_vault: Path, fake_proposals: Path
):
    """B1.8 — disk-only card (not on the board) becomes a backlog plan."""
    vault_plans = migrate._parse_vault_kanban(fake_vault)
    disk_plans = migrate._scan_proposals_dir(fake_proposals)
    merged = migrate._merge_plans(vault_plans, disk_plans)
    by_id = {p.proposal_id: p for p in merged}
    assert "DEV-20260104-000001-D0001" in by_id
    assert by_id["DEV-20260104-000001-D0001"].column_name == "backlog"
    assert by_id["DEV-20260104-000001-D0001"].source == "proposals_dir"


# ════════════════════════════════════════════════════════════════════
#  _enrich_from_proposal_file
# ════════════════════════════════════════════════════════════════════


def test_enrich_pulls_severity_origin_title(fake_proposals: Path):
    """B1.9 — frontmatter fields populate the plan in place."""
    plan = migrate.CardPlan(
        proposal_id="DEV-20260101-000001-A0001",
        prefix="DEV",
        column_name="backlog",
    )
    migrate._enrich_from_proposal_file(plan, fake_proposals)
    assert plan.severity == "high"
    assert plan.origin == "systems-architect"
    assert plan.title == "First card body"


def test_enrich_handles_missing_file_gracefully(tmp_path: Path):
    """B1.10 — non-existent proposal file leaves a note but doesn't crash."""
    plan = migrate.CardPlan(
        proposal_id="DEV-NEVER-EXISTED",
        prefix="DEV",
        column_name="backlog",
    )
    migrate._enrich_from_proposal_file(plan, tmp_path / "no_such_dir")
    assert plan.severity is None
    assert plan.title is None
    assert any("no proposal file" in n for n in plan.notes)


# ════════════════════════════════════════════════════════════════════
#  Apply (integration with real KanbanStore on tmp_path)
# ════════════════════════════════════════════════════════════════════


def test_apply_inserts_plans_into_sqlite(
    fake_vault: Path, fake_proposals: Path, isolated_store: KanbanStore
):
    """B1.11 — every valid plan ends up as a card in the store."""
    vault_plans = migrate._parse_vault_kanban(fake_vault)
    disk_plans = migrate._scan_proposals_dir(fake_proposals)
    merged = migrate._merge_plans(vault_plans, disk_plans)
    for p in merged:
        migrate._enrich_from_proposal_file(p, fake_proposals)

    report = migrate.MigrationReport(mode="apply", started_at="now")
    asyncio.run(migrate._apply_plans(merged, isolated_store, report))

    # 4 cards (3 in vault + 1 disk-only)
    assert len(report.inserted) == 4
    assert report.skipped_invalid_prefix == []
    assert report.skipped_invalid_column == []

    # Verify each one is queryable
    for pid in report.inserted:
        card = asyncio.run(isolated_store.get_card(pid))
        assert card is not None
        assert card.proposal_id == pid


def test_apply_is_idempotent(
    fake_vault: Path, fake_proposals: Path, isolated_store: KanbanStore
):
    """B1.12 — re-running apply on the same set inserts 0 new cards."""
    vault_plans = migrate._parse_vault_kanban(fake_vault)
    disk_plans = migrate._scan_proposals_dir(fake_proposals)
    merged = migrate._merge_plans(vault_plans, disk_plans)

    # First run
    report1 = migrate.MigrationReport(mode="apply", started_at="t1")
    asyncio.run(migrate._apply_plans(merged, isolated_store, report1))
    assert len(report1.inserted) == 4

    # Second run on the SAME store and SAME plans
    report2 = migrate.MigrationReport(mode="apply", started_at="t2")
    asyncio.run(migrate._apply_plans(merged, isolated_store, report2))
    assert report2.inserted == []
    assert len(report2.already_in_sqlite) == 4


def test_apply_skips_invalid_prefix(isolated_store: KanbanStore):
    """B1.13 — a plan with a bogus prefix is recorded in skipped, not inserted."""
    plans = [migrate.CardPlan(
        proposal_id="XXX-1234", prefix="XXX", column_name="backlog",
    )]
    report = migrate.MigrationReport(mode="apply", started_at="now")
    asyncio.run(migrate._apply_plans(plans, isolated_store, report))
    assert report.inserted == []
    assert report.skipped_invalid_prefix == ["XXX-1234"]


# ════════════════════════════════════════════════════════════════════
#  CLI entry point
# ════════════════════════════════════════════════════════════════════


def test_main_dry_run_returns_zero_and_does_not_write(
    fake_vault: Path, fake_proposals: Path, tmp_path: Path, capsys: pytest.CaptureFixture
):
    """B1.14 — default (dry-run) exits 0 and writes nothing to SQLite."""
    db = tmp_path / "kanban.sqlite"
    rc = migrate.main([
        "--vault-file", str(fake_vault),
        "--proposals-dir", str(fake_proposals),
        "--db-path", str(db),
    ])
    assert rc == 0
    assert not db.exists(), "dry-run must not create the SQLite file"
    captured = capsys.readouterr()
    assert "dry-run complete" in captured.out


def test_main_apply_creates_sqlite_and_returns_zero(
    fake_vault: Path, fake_proposals: Path, tmp_path: Path
):
    """B1.15 — --apply creates the DB, inserts cards, regenerates vault."""
    db = tmp_path / "kanban.sqlite"
    rc = migrate.main([
        "--apply",
        "--vault-file", str(fake_vault),
        "--proposals-dir", str(fake_proposals),
        "--db-path", str(db),
    ])
    assert rc == 0
    assert db.exists()
    # The vault file should have been regenerated by the renderer
    vault_after = fake_vault.read_text(encoding="utf-8")
    assert "AUTO-GENERATED by kanban_renderer" in vault_after
    # All 4 cards must appear in the regenerated vault
    for pid in (
        "DEV-20260101-000001-A0001",
        "ARCH-20260102-000001-B0001",
        "NLST-20260103-000001-C0001",
        "DEV-20260104-000001-D0001",
    ):
        assert pid in vault_after
