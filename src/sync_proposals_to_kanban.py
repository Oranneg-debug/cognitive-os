"""
Sync proposal files to the Obsidian Kanban board — without going through
the LLM proposal-refinement stage.

When you (or the Systems Architect agent) author a thorough proposal
directly as a markdown file under ``cognitive-os/dev/proposals/``, the
existing council pipeline doesn't know it exists until something pokes
the kanban. This script bridges that gap:

  1. Walk both the project and vault proposals folders.
  2. For each ``DEV-*_PROPOSAL.md`` not already in the kanban board:
     - Read its frontmatter (``phase``, ``status``) to decide which
       column it belongs in.
     - Build a kanban card line that matches the watcher's regex
       (title must contain the full ``DEV-YYYYMMDD-HHMMSS-XXXXXXXX`` form).
     - Insert it under the right column.
  3. Print a summary + (if requested) the raw card lines for manual paste.

Default destination column is ``## Proposal`` (not ``## Backlog``) — this
is the "skip the refinement stage" semantic. Thorough, architect-authored
proposals don't need the proposal-refine LLM pass; they go straight to the
human-approval state.

Idempotency / safety rails
~~~~~~~~~~~~~~~~~~~~~~~~~~

The script avoids re-adding any proposal that is **either** currently on
the board **or** known to the kanban cache (``.kanban_cache.json``). The
cache records every proposal the watcher has ever seen on the board, so
proposals you intentionally removed (e.g. archived, cleaned out of
Backlog) won't be silently resurrected. Pass ``--ignore-cache`` to bypass
this guard.

Usage:

  python -m src.sync_proposals_to_kanban             # dry-run-friendly: print plan + execute
  python -m src.sync_proposals_to_kanban --dry-run   # don't touch the kanban file
  python -m src.sync_proposals_to_kanban --column "Backlog"   # override target column
  python -m src.sync_proposals_to_kanban --only DEV-20260521-001000-B5D5C0DE

Exit codes:
  0 = success (cards added, or nothing to do)
  2 = kanban file unreachable (vault offline) — card lines printed for paste
  3 = malformed proposal frontmatter
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

# Optional yaml — fall back to a minimal frontmatter parser if not available
try:
    import yaml  # type: ignore
    _HAVE_YAML = True
except ImportError:
    _HAVE_YAML = False


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_HERE = Path(__file__).resolve().parent

# The two canonical proposal locations (project + vault mirror).
PROJECT_PROPOSALS = (_HERE.parent / "dev" / "proposals").resolve()
VAULT_ROOT = Path(
    os.environ.get(
        "OBSIDIAN_VAULT_PATH",
        r"E:\Oranneg\CloudStation\Documents\Obsidian\Grand Nexus",
    )
)
VAULT_PROPOSALS = (VAULT_ROOT / "1. P - Seedlings" / "dev" / "proposals").resolve()
VAULT_KANBAN = (VAULT_ROOT / "1. P - Seedlings" / "Dev-KanBan.md").resolve()

# Local kanban cache (the watcher writes this — we read it to detect
# proposals that were previously on the board but have since been removed).
KANBAN_CACHE = (_HERE.parent / "dev" / ".kanban_cache.json").resolve()

# Watcher-friendly proposal-id pattern: DEV-YYYYMMDD-HHMMSS-XXXX...
PROPOSAL_ID_RE = re.compile(r"DEV-\d{8}-\d{6}-[A-Z0-9]+")

# Frontmatter delimiters
FM_OPEN = "---"

# Map a frontmatter `phase:` value → Kanban column heading.
# Keep this conservative — unknown phases route to Proposal (the default
# human-approval state), never silently to Beta/Alpha/etc.
PHASE_TO_COLUMN = {
    "backlog":     "Backlog",
    "proposal":    "Proposal",
    "beta":        "Beta Testing",
    "alpha":       "Alpha Polish",
    "finalized":   "Finalized",
    "deployed":    "Deployed",
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Proposal:
    """A proposal file located on disk."""
    proposal_id: str
    path: Path
    phase: str | None        # value from frontmatter, lower-cased
    status: str | None
    title: str | None        # `original_request` or first heading-derived line

    @property
    def filename(self) -> str:
        return self.path.name


@dataclass(frozen=True)
class CardPlan:
    """A planned insertion into the Kanban board."""
    proposal: Proposal
    target_column: str
    card_text: str           # the multi-line markdown card block


# ---------------------------------------------------------------------------
# Frontmatter parsing
# ---------------------------------------------------------------------------

def _parse_frontmatter(text: str) -> dict:
    """Best-effort YAML frontmatter parse. Returns {} if no FM or unparseable."""
    if not text.startswith(FM_OPEN + "\n") and not text.startswith(FM_OPEN + "\r\n"):
        return {}
    end_idx = text.find("\n" + FM_OPEN, len(FM_OPEN))
    if end_idx == -1:
        return {}
    fm_body = text[len(FM_OPEN):end_idx].lstrip("\r\n")
    if _HAVE_YAML:
        try:
            data = yaml.safe_load(fm_body)
            return data if isinstance(data, dict) else {}
        except Exception:
            pass
    # Stdlib fallback: only parse the simplest `key: value` form. Enough
    # for `phase`, `status`, and `original_request`.
    out: dict = {}
    for line in fm_body.splitlines():
        if ":" not in line or line.lstrip().startswith("#"):
            continue
        if line.startswith(" ") or line.startswith("\t"):
            continue  # skip nested fields, we don't need them
        k, _, v = line.partition(":")
        v = v.strip().strip('"').strip("'")
        if k and v:
            out[k.strip()] = v
    return out


def _extract_proposal_from_file(path: Path) -> Proposal | None:
    """Read one ``DEV-*_PROPOSAL.md`` file. Returns None if unrecognised."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        print(f"  ⚠️  cannot read {path}: {exc!r}", file=sys.stderr)
        return None

    # Proposal ID lives in the body (Markdown), not the frontmatter.
    m = PROPOSAL_ID_RE.search(text)
    if not m:
        return None
    proposal_id = m.group(0)

    fm = _parse_frontmatter(text)
    phase = (fm.get("phase") or "").strip().lower() or None
    status = (fm.get("status") or "").strip().lower() or None
    title = fm.get("original_request") or fm.get("title") or None
    if isinstance(title, str):
        title = title.strip().strip('"').strip("'") or None

    return Proposal(
        proposal_id=proposal_id,
        path=path,
        phase=phase,
        status=status,
        title=title,
    )


def _iter_proposal_files(*roots: Path) -> Iterable[Path]:
    seen: set[Path] = set()
    for root in roots:
        if not root.exists():
            continue
        for entry in sorted(root.iterdir()):
            if not entry.is_file():
                continue
            if not entry.name.endswith("_PROPOSAL.md"):
                continue
            resolved = entry.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            yield entry


# ---------------------------------------------------------------------------
# Kanban board parsing & writing
# ---------------------------------------------------------------------------

# Column-header regex: `## Backlog`, `## Beta Testing`, etc.
COLUMN_HEADER_RE = re.compile(r"^(## (?:Backlog|Proposal|Beta Testing|Alpha Polish|Finalized|Deployed|Archive))\s*$", re.MULTILINE)


def _existing_proposal_ids_in_board(board_text: str) -> set[str]:
    """Return every DEV-… id already present anywhere in the board."""
    return set(PROPOSAL_ID_RE.findall(board_text))


def _ensure_column(board_text: str, column_name: str) -> str:
    """If `## <column_name>` is missing from the board, append it."""
    pattern = re.compile(rf"^## {re.escape(column_name)}\s*$", re.MULTILINE)
    if pattern.search(board_text):
        return board_text
    # Append, separated by a blank line.
    sep = "" if board_text.endswith("\n") else "\n"
    return f"{board_text}{sep}\n## {column_name}\n"


def _build_card_text(p: Proposal, now: datetime) -> str:
    """Compose the kanban card block for a proposal.

    The first line MUST contain the full DEV-… id so the watcher's
    `_extract_proposal_id_from_line` regex picks it up.
    Sub-bullets follow the format used elsewhere in `Dev-KanBan.md`.
    """
    # Tab + two spaces is the indentation Obsidian Kanban uses on this
    # board (verified empirically 2026-05-21).
    indent = "\t  "
    title_part = f"{p.proposal_id}"
    if p.title and p.title != p.proposal_id:
        # Keep titles short; the kanban-plugin truncates very long ones.
        title_part = f"{p.proposal_id} — {p.title[:80]}"
    card_id_block_ref = f"^[{p.proposal_id.replace('-', '')[:24]}]"

    lines = [
        f"- [ ] {title_part} {card_id_block_ref}",
        f"{indent}- status: ⏳ Pending",
        f"{indent}- priority: medium",
        f"{indent}- created: {now.strftime('%Y-%m-%d at %H:%M')}",
        f"{indent}- related: [[{p.path.stem}]]",
    ]
    return "\n".join(lines) + "\n"


def _insert_into_column(board_text: str, column_name: str, card_text: str) -> str:
    """Insert ``card_text`` immediately after the column heading + its blank line."""
    header = f"## {column_name}"
    idx = board_text.find(header)
    if idx == -1:
        # Caller should have ensured the column exists; defensive append.
        return f"{board_text.rstrip()}\n\n{header}\n\n{card_text}"

    # Move past the header line.
    after_header = idx + len(header)
    # Skip one trailing newline (the one ending the header line).
    if after_header < len(board_text) and board_text[after_header] == "\n":
        after_header += 1

    # Insert: blank line, then the card.
    return board_text[:after_header] + "\n" + card_text + board_text[after_header:]


# ---------------------------------------------------------------------------
# Core orchestration
# ---------------------------------------------------------------------------

def _load_cache_ids(cache_path: Path) -> set[str]:
    """Read the kanban-watcher's cache and return every recorded DEV-id.

    The cache is written by :mod:`src.kanban_processor` and represents
    every proposal the watcher has ever seen on the board. Returning the
    empty set on read failure is intentional — we'd rather sync too many
    than zero when we can't tell.
    """
    try:
        import json
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        return set((data.get("cards") or {}).keys())
    except (OSError, ValueError):
        return set()


def plan_inserts(
    proposals: list[Proposal],
    existing_ids: set[str],
    default_column: str,
    now: datetime,
    column_override: str | None = None,
    known_to_cache: set[str] | None = None,
) -> tuple[list[CardPlan], list[Proposal], list[Proposal]]:
    """Return (plans, skipped_already_in_board, skipped_known_to_cache)."""
    plans: list[CardPlan] = []
    skipped_on_board: list[Proposal] = []
    skipped_cache_hit: list[Proposal] = []
    cache = known_to_cache or set()
    for p in proposals:
        if p.proposal_id in existing_ids:
            skipped_on_board.append(p)
            continue
        if p.proposal_id in cache:
            skipped_cache_hit.append(p)
            continue
        if column_override:
            target = column_override
        else:
            target = PHASE_TO_COLUMN.get(p.phase or "", default_column)
        plans.append(
            CardPlan(
                proposal=p,
                target_column=target,
                card_text=_build_card_text(p, now),
            )
        )
    return plans, skipped_on_board, skipped_cache_hit


def apply_plans(board_text: str, plans: list[CardPlan]) -> str:
    """Apply every plan to the board text, ensuring columns exist."""
    out = board_text
    for plan in plans:
        out = _ensure_column(out, plan.target_column)
        out = _insert_into_column(out, plan.target_column, plan.card_text)
    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="sync_proposals_to_kanban",
        description="Add proposal files to the Obsidian Kanban board without "
                    "going through the LLM proposal-refinement stage.",
    )
    p.add_argument(
        "--column",
        choices=tuple(PHASE_TO_COLUMN.values()),
        default=None,
        help="Force every new card into this column (overrides per-proposal phase).",
    )
    p.add_argument(
        "--default-column",
        choices=tuple(PHASE_TO_COLUMN.values()),
        default="Proposal",
        help="Target column when a proposal's `phase` frontmatter is missing "
             "or unrecognised. Default: Proposal (skips backlog refinement).",
    )
    p.add_argument(
        "--only",
        action="append",
        default=[],
        metavar="DEV-…",
        help="Only sync proposals matching one of these IDs. Repeatable.",
    )
    p.add_argument(
        "--kanban",
        type=Path,
        default=VAULT_KANBAN,
        help=f"Path to the Kanban board file (default: {VAULT_KANBAN}).",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Plan but don't write the kanban file.",
    )
    p.add_argument(
        "--print-cards",
        action="store_true",
        help="Print each card block on stdout so it can be pasted by hand "
             "(useful when --dry-run or when the vault is offline).",
    )
    p.add_argument(
        "--ignore-cache",
        action="store_true",
        help="Bypass the kanban-cache guard. Without this flag, the script "
             "skips any proposal whose id was once on the board (per "
             ".kanban_cache.json) — protecting intentional removals.",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_argparser().parse_args(argv)
    now = datetime.now()

    # 1. Discover proposal files.
    files = list(_iter_proposal_files(PROJECT_PROPOSALS, VAULT_PROPOSALS))
    if not files:
        print(
            f"[sync] no _PROPOSAL.md files found under "
            f"{PROJECT_PROPOSALS} or {VAULT_PROPOSALS}"
        )
        return 0

    # 2. Parse each.
    proposals: list[Proposal] = []
    bad = 0
    for f in files:
        p = _extract_proposal_from_file(f)
        if p is None:
            bad += 1
            print(f"  ⚠️  skipping (no DEV-id found): {f.name}")
            continue
        if args.only and p.proposal_id not in args.only:
            continue
        proposals.append(p)
    if bad and not proposals:
        return 3
    if not proposals:
        print("[sync] nothing matched --only filter; aborting")
        return 0

    print(f"[sync] discovered {len(proposals)} proposal file(s)")

    # 3. Read the kanban board (or initialise an empty one).
    board_path: Path = args.kanban
    board_exists = board_path.exists()
    if not board_exists:
        print(f"[sync] kanban not found at {board_path}")
        if not args.print_cards:
            print(
                f"[sync] re-run with --print-cards to get pasteable card text, "
                f"or place a Dev-KanBan.md at {board_path}"
            )
            return 2
        board_text = ""
        existing_ids: set[str] = set()
    else:
        try:
            board_text = board_path.read_text(encoding="utf-8")
        except OSError as exc:
            print(f"[sync] cannot read {board_path}: {exc!r}")
            return 2
        existing_ids = _existing_proposal_ids_in_board(board_text)

    # 4. Plan insertions.
    cache_ids = set() if args.ignore_cache else _load_cache_ids(KANBAN_CACHE)
    if cache_ids:
        print(f"[sync] cache guard active ({len(cache_ids)} ids known to watcher)")
    elif not args.ignore_cache:
        print(f"[sync] cache not found at {KANBAN_CACHE} — proceeding without guard")

    plans, skipped_on_board, skipped_cache_hit = plan_inserts(
        proposals,
        existing_ids,
        default_column=args.default_column,
        now=now,
        column_override=args.column,
        known_to_cache=cache_ids,
    )

    for s in skipped_on_board:
        print(f"  ↺  already in board: {s.proposal_id}")
    for s in skipped_cache_hit:
        print(f"  ⛔ skipped (cache says was-once-on-board, intentional removal?): "
              f"{s.proposal_id} — pass --ignore-cache to re-add")
    for p in plans:
        print(f"  ➕ plan: {p.proposal.proposal_id}  →  ## {p.target_column}")

    # 5. Print cards (always handy for log forensics).
    if args.print_cards or args.dry_run:
        for plan in plans:
            print()
            print(f"# Suggested card for {plan.proposal.proposal_id} "
                  f"(paste under ## {plan.target_column}):")
            print(plan.card_text, end="")

    if not plans:
        print("[sync] nothing to add")
        return 0

    if args.dry_run:
        print(f"[sync] dry-run: not writing {board_path}")
        return 0

    if not board_exists:
        # We already returned with exit 2 above if the board is missing
        # and --print-cards wasn't set. This branch handles --print-cards
        # without an existing board: we *don't* create one (Obsidian's
        # kanban plugin needs frontmatter we don't want to invent here).
        print(f"[sync] board file missing; printed {len(plans)} card(s) above")
        return 2

    # 6. Apply.
    new_board = apply_plans(board_text, plans)
    if new_board == board_text:
        print("[sync] no changes to write (board already matched plan)")
        return 0

    backup = board_path.with_suffix(
        f".bak.{now.strftime('%Y%m%d-%H%M%S')}-sync"
    )
    backup.write_text(board_text, encoding="utf-8")
    board_path.write_text(new_board, encoding="utf-8")
    print(f"[sync] wrote {board_path} (backup: {backup.name})")
    print(f"[sync] added {len(plans)} card(s)")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
