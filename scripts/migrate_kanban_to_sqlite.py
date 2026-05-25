"""One-shot migration: Dev-KanBan.md + dev/proposals/*.md → kanban_state.sqlite.

Part of ARCH-DA5B0A2D (B1). Reads the legacy markdown kanban board ONE
LAST TIME via the deprecated ``kanban_processor._parse_kanban_board``,
backfills any proposals on disk but not on the board, and inserts every
card into the new SQLite store.

Usage::

    python scripts/migrate_kanban_to_sqlite.py             # dry-run (default)
    python scripts/migrate_kanban_to_sqlite.py --apply     # actually write
    python scripts/migrate_kanban_to_sqlite.py --apply --backup-vault

Safety
------
- ``--dry-run`` (default) prints what would happen; touches nothing.
- ``--apply`` writes to SQLite + regenerates the vault mirror.
- ``--backup-vault`` snapshots ``Dev-KanBan.md`` to
  ``Dev-KanBan.md.pre-migration.bak`` before the renderer overwrites it.
- **Idempotent:** running twice does nothing. Cards already in SQLite
  are skipped silently (logged but not re-inserted). Re-running after a
  partial failure is safe.
- A migration report is written to
  ``dev/decisions/_kanban_migration_<ISO>.md`` only on ``--apply``.

What gets migrated
------------------
For each card discovered:
  1. **From vault**: ``proposal_id`` + ``column_name`` (from the column
     it sits under).
  2. **From ``dev/proposals/<id>_PROPOSAL.md``** (when present):
     ``prefix``, ``title`` (from filename), ``severity`` (frontmatter),
     ``origin`` (frontmatter).
  3. **Proposals on disk but NOT on the board** are inserted into the
     ``backlog`` column with a warning.

Out of scope
------------
- Deleting ``dev/.kanban_cache.json`` (separate step; the proposal
  treats it as a post-migration cleanup, not part of B1 itself).
- Deleting the deprecated ``kanban_processor.py`` (handled by A5; remains
  importable as a compat shim).
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Optional

import yaml

# Allow ``python scripts/migrate_kanban_to_sqlite.py`` from the project root
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Local imports (must come after sys.path manipulation)
from src.kanban_renderer import write_vault_mirror  # noqa: E402
from src.kanban_store import (  # noqa: E402
    CANONICAL_COLUMNS,
    KNOWN_PREFIXES,
    KanbanStore,
)
from src.paths import DEV_DIR, KANBAN_FILE, PROPOSALS_DIR  # noqa: E402

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════════
#  Data carriers
# ════════════════════════════════════════════════════════════════════


@dataclass
class CardPlan:
    """A planned card insertion. ``source`` is purely informational."""

    proposal_id: str
    prefix: str
    column_name: str
    title: Optional[str] = None
    severity: Optional[str] = None
    origin: Optional[str] = None
    source: str = "unknown"  # "vault" | "proposals_dir" | "merged"
    notes: List[str] = field(default_factory=list)


@dataclass
class MigrationReport:
    """Summary of what the migration did (or would do)."""

    mode: str  # "dry-run" | "apply"
    started_at: str
    finished_at: str = ""
    vault_cards_found: int = 0
    proposals_dir_cards_found: int = 0
    plans: List[CardPlan] = field(default_factory=list)
    already_in_sqlite: List[str] = field(default_factory=list)
    inserted: List[str] = field(default_factory=list)
    skipped_invalid_prefix: List[str] = field(default_factory=list)
    skipped_invalid_column: List[str] = field(default_factory=list)
    vault_backup_path: Optional[str] = None
    vault_mirror_path: Optional[str] = None
    errors: List[str] = field(default_factory=list)

    def to_markdown(self) -> str:
        lines = [
            f"# Kanban migration report — {self.started_at}",
            "",
            f"- mode: **{self.mode}**",
            f"- started: {self.started_at}",
            f"- finished: {self.finished_at}",
            f"- vault cards found: {self.vault_cards_found}",
            f"- proposals dir cards found: {self.proposals_dir_cards_found}",
            f"- total unique plans: {len(self.plans)}",
            f"- already in SQLite (skipped): {len(self.already_in_sqlite)}",
            f"- inserted this run: {len(self.inserted)}",
        ]
        if self.skipped_invalid_prefix:
            lines.append(f"- skipped — invalid prefix: {self.skipped_invalid_prefix}")
        if self.skipped_invalid_column:
            lines.append(f"- skipped — invalid column: {self.skipped_invalid_column}")
        if self.vault_backup_path:
            lines.append(f"- vault backup: `{self.vault_backup_path}`")
        if self.vault_mirror_path:
            lines.append(f"- vault mirror regenerated: `{self.vault_mirror_path}`")
        if self.errors:
            lines.append("")
            lines.append("## Errors")
            for e in self.errors:
                lines.append(f"- {e}")
        return "\n".join(lines) + "\n"


# ════════════════════════════════════════════════════════════════════
#  Discovery
# ════════════════════════════════════════════════════════════════════


# Same regex as the legacy kanban_processor uses, lifted out for clarity.
_PROPOSAL_ID_RE = re.compile(r"(?:DEV|ARCH|NLST)-\d{8}-\d{6}-[A-Z0-9]+")

# Map "Beta Testing" → "beta testing" (lowercase canonical) etc.
_TITLE_TO_CANONICAL = {
    "Backlog": "backlog",
    "Proposal": "proposal",
    "Beta Testing": "beta testing",
    "Alpha Polish": "alpha polish",
    "Finalized": "finalized",
    "Deployed": "deployed",
}


def _parse_vault_kanban(path: Path) -> List[CardPlan]:
    """Parse ``Dev-KanBan.md`` ONE LAST TIME.

    We deliberately don't import ``kanban_processor`` here — that module
    is deprecated, has heavy side-effects on import (DeprecationWarning
    + loads master_config), and only its tiny parse routine is needed.
    Re-implement that routine inline; it's ~30 lines.

    Returns one ``CardPlan`` per card. Title / severity / origin are
    populated by ``_enrich_from_proposal_file`` later.
    """
    if not path.exists():
        logger.warning("vault kanban not found at %s; skipping vault parse", path)
        return []

    plans: list[CardPlan] = []
    current_canonical: Optional[str] = None
    seen_in_vault: set[str] = set()

    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            stripped = line.strip()

            # Column header
            header_match = re.match(r"^## (.+)$", stripped)
            if header_match:
                title = header_match.group(1).strip()
                current_canonical = _TITLE_TO_CANONICAL.get(title)
                continue

            # Card line — must contain a proposal id
            if not current_canonical:
                continue
            id_match = _PROPOSAL_ID_RE.search(stripped)
            if not id_match:
                continue
            proposal_id = id_match.group(0)

            # De-dupe: legacy file occasionally has the same card listed twice.
            if proposal_id in seen_in_vault:
                continue
            seen_in_vault.add(proposal_id)

            prefix = proposal_id.split("-", 1)[0]
            plans.append(CardPlan(
                proposal_id=proposal_id,
                prefix=prefix,
                column_name=current_canonical,
                source="vault",
            ))

    return plans


def _enrich_from_proposal_file(plan: CardPlan, proposals_dir: Path) -> None:
    """Populate title / severity / origin from the proposal file frontmatter.

    Mutates ``plan`` in place. Best-effort: missing / malformed proposal
    files are logged but never fatal.
    """
    candidate = proposals_dir / f"{plan.proposal_id}_PROPOSAL.md"
    if not candidate.exists():
        plan.notes.append(f"no proposal file at {candidate.name}")
        return

    try:
        raw = candidate.read_text(encoding="utf-8")
    except OSError as exc:
        plan.notes.append(f"failed to read {candidate.name}: {exc!r}")
        return

    # Quick frontmatter extraction — between leading "---\n" and next "\n---".
    if not raw.startswith("---\n"):
        plan.notes.append(f"{candidate.name} has no leading frontmatter")
        return
    end = raw.find("\n---", 4)
    if end == -1:
        plan.notes.append(f"{candidate.name} frontmatter has no closing ---")
        return

    try:
        fm = yaml.safe_load(raw[4:end]) or {}
    except yaml.YAMLError as exc:
        plan.notes.append(f"{candidate.name} frontmatter YAML error: {exc!r}")
        return

    # We pull conservative fields only; the planner runs against the
    # proposal body later if it needs more context.
    severity = fm.get("severity")
    if isinstance(severity, str):
        plan.severity = severity.lower()

    origin = fm.get("origin")
    if isinstance(origin, str):
        plan.origin = origin

    # Title falls back to the proposal id if we can't derive a better one.
    # The proposal markdown doesn't store a top-level "title" field — we
    # try to use ``original_request`` truncated to 80 chars as a humane
    # display.
    original = fm.get("original_request")
    if isinstance(original, str) and original.strip():
        first_sentence = original.strip().split("\n", 1)[0]
        plan.title = first_sentence[:80] + ("…" if len(first_sentence) > 80 else "")


def _scan_proposals_dir(proposals_dir: Path) -> List[CardPlan]:
    """Find proposal files that don't have a card on the board yet.

    These go into ``backlog`` per the proposal's migration step #5.
    Returns one plan per proposal file. Caller is responsible for
    de-duplicating against vault plans.
    """
    if not proposals_dir.exists():
        return []

    out: list[CardPlan] = []
    for p in sorted(proposals_dir.glob("*_PROPOSAL.md")):
        id_match = _PROPOSAL_ID_RE.search(p.stem)
        if not id_match:
            continue
        proposal_id = id_match.group(0)
        prefix = proposal_id.split("-", 1)[0]
        out.append(CardPlan(
            proposal_id=proposal_id,
            prefix=prefix,
            column_name="backlog",
            source="proposals_dir",
        ))
    return out


def _merge_plans(
    vault_plans: List[CardPlan],
    disk_plans: List[CardPlan],
) -> List[CardPlan]:
    """Vault wins for column; disk fills in cards the vault missed.

    Returns one plan per proposal_id. Plans from disk only contribute
    when the vault didn't already mention the card (matches proposal
    step #5: "Proposals on disk but not on board → INSERT with
    column='backlog'").
    """
    by_id: dict[str, CardPlan] = {}
    for p in vault_plans:
        by_id[p.proposal_id] = p
    for p in disk_plans:
        if p.proposal_id not in by_id:
            by_id[p.proposal_id] = p
        else:
            # Already present from vault — mark that disk also saw it.
            existing = by_id[p.proposal_id]
            existing.source = "merged"
    return sorted(by_id.values(), key=lambda c: c.proposal_id)


# ════════════════════════════════════════════════════════════════════
#  Apply
# ════════════════════════════════════════════════════════════════════


async def _apply_plans(
    plans: Iterable[CardPlan],
    store: KanbanStore,
    report: MigrationReport,
) -> None:
    """Insert each plan into the store. Idempotent.

    ``store.add_card`` already returns the existing card if one is
    present — we treat that as "already migrated" rather than logging it
    as a new insertion.
    """
    for plan in plans:
        if plan.prefix not in KNOWN_PREFIXES:
            report.skipped_invalid_prefix.append(plan.proposal_id)
            continue
        if plan.column_name not in CANONICAL_COLUMNS:
            report.skipped_invalid_column.append(plan.proposal_id)
            continue

        existing = await store.get_card(plan.proposal_id)
        if existing is not None:
            report.already_in_sqlite.append(plan.proposal_id)
            continue

        try:
            await store.add_card(
                proposal_id=plan.proposal_id,
                prefix=plan.prefix,
                column_name=plan.column_name,
                title=plan.title,
                severity=plan.severity,
                origin=plan.origin,
                approver="migration",
                reason=f"migrated from {plan.source}",
            )
            report.inserted.append(plan.proposal_id)
        except Exception as exc:  # noqa: BLE001 — defensive at the script boundary
            report.errors.append(f"{plan.proposal_id}: {type(exc).__name__}: {exc}")


def _backup_vault(path: Path) -> Optional[Path]:
    if not path.exists():
        return None
    backup = path.with_suffix(path.suffix + ".pre-migration.bak")
    backup.write_bytes(path.read_bytes())
    return backup


def _write_report(report: MigrationReport, decisions_dir: Path) -> Optional[Path]:
    """Write the markdown migration report. Only called on --apply."""
    if not decisions_dir.exists():
        try:
            decisions_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            report.errors.append(f"could not create decisions dir: {exc!r}")
            return None
    # Filename: _kanban_migration_<ISO>.md (leading underscore puts it
    # alongside the existing _bootstrap_approvals / _tech_debt_register
    # bookkeeping files).
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    out = decisions_dir / f"_kanban_migration_{ts}.md"
    out.write_text(report.to_markdown(), encoding="utf-8")
    return out


# ════════════════════════════════════════════════════════════════════
#  Entry point
# ════════════════════════════════════════════════════════════════════


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually write to SQLite + regenerate vault. Default is dry-run.",
    )
    parser.add_argument(
        "--backup-vault",
        action="store_true",
        help="With --apply, snapshot Dev-KanBan.md to .pre-migration.bak first.",
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default=None,
        help="Override kanban DB path (mostly for tests).",
    )
    parser.add_argument(
        "--vault-file",
        type=str,
        default=None,
        help="Override path to the source Dev-KanBan.md (mostly for tests).",
    )
    parser.add_argument(
        "--proposals-dir",
        type=str,
        default=None,
        help="Override path to dev/proposals/ (mostly for tests).",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    vault_path = Path(args.vault_file) if args.vault_file else KANBAN_FILE
    proposals_dir = Path(args.proposals_dir) if args.proposals_dir else PROPOSALS_DIR
    decisions_dir = DEV_DIR / "decisions"

    report = MigrationReport(
        mode="apply" if args.apply else "dry-run",
        started_at=datetime.now(timezone.utc).isoformat(),
    )

    print(f"== Kanban migration ({report.mode}) ==")
    print(f"  vault:        {vault_path}")
    print(f"  proposals:    {proposals_dir}")
    if args.db_path:
        print(f"  db (override): {args.db_path}")

    # Discovery
    vault_plans = _parse_vault_kanban(vault_path)
    report.vault_cards_found = len(vault_plans)

    disk_plans = _scan_proposals_dir(proposals_dir)
    report.proposals_dir_cards_found = len(disk_plans)

    merged = _merge_plans(vault_plans, disk_plans)
    for plan in merged:
        _enrich_from_proposal_file(plan, proposals_dir)
    report.plans = merged

    print(f"  found {len(vault_plans)} cards in vault, "
          f"{len(disk_plans)} proposal files on disk, "
          f"{len(merged)} unique plans")

    if not merged:
        print("  nothing to migrate; exiting.")
        report.finished_at = datetime.now(timezone.utc).isoformat()
        if args.apply:
            written = _write_report(report, decisions_dir)
            report.vault_mirror_path = None
            print(f"  report: {written}")
        return 0

    # Dry-run: print summary and stop here.
    if not args.apply:
        print()
        print(f"  {'PROPOSAL_ID':<40} {'COLUMN':<14} {'PREFIX':<6} SOURCE")
        for plan in merged:
            print(f"  {plan.proposal_id:<40} {plan.column_name:<14} "
                  f"{plan.prefix:<6} {plan.source}")
        print()
        print("  dry-run complete; re-run with --apply to write.")
        return 0

    # Apply path: SQLite + vault mirror + report.
    db_path_override = Path(args.db_path) if args.db_path else None
    store = KanbanStore(db_path=db_path_override) if db_path_override else KanbanStore()

    async def _run():
        await store.init_schema()
        await _apply_plans(merged, store, report)
        if args.backup_vault:
            backup = _backup_vault(vault_path)
            if backup is not None:
                report.vault_backup_path = str(backup)
        # Regenerate the vault mirror from the freshly populated store.
        snap = await store.get_board()
        # The migration intentionally writes to the SAME vault path it
        # just parsed — that's the point: SQLite is now authoritative and
        # the markdown is regenerated from it.
        mirror_path = await asyncio.to_thread(write_vault_mirror, snap, vault_path)
        report.vault_mirror_path = str(mirror_path)

    asyncio.run(_run())

    report.finished_at = datetime.now(timezone.utc).isoformat()
    report_path = _write_report(report, decisions_dir)

    print()
    print(f"  inserted: {len(report.inserted)}")
    print(f"  already in SQLite: {len(report.already_in_sqlite)}")
    if report.skipped_invalid_prefix or report.skipped_invalid_column:
        print(f"  skipped (bad prefix): {len(report.skipped_invalid_prefix)}")
        print(f"  skipped (bad column): {len(report.skipped_invalid_column)}")
    if report.errors:
        print(f"  errors: {len(report.errors)}")
        for e in report.errors:
            print(f"    - {e}")
    print(f"  vault mirror: {report.vault_mirror_path}")
    if report.vault_backup_path:
        print(f"  vault backup: {report.vault_backup_path}")
    print(f"  report: {report_path}")
    return 0 if not report.errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
