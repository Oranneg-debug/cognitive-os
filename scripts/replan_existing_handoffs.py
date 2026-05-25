"""Re-plan existing handoff documents with the new HandoffPlanner.

Part of ARCH-5DFB393F (deliverable A11). Reads each handoff in
``dev/handoffs/``, finds the embedded council verdict (``## 🧠 Technical
Council Deliberation`` section), feeds it back through the planner,
and rewrites ONLY the ``## 🔧 Implementation Tasks`` block.

Usage::

    python scripts/replan_existing_handoffs.py --dry-run        # default
    python scripts/replan_existing_handoffs.py --apply          # actually write
    python scripts/replan_existing_handoffs.py --apply --only ARCH-…

Safety:
    - Defaults to ``--dry-run``. You must pass ``--apply`` to write anything.
    - On planner failure for any handoff, the file is skipped (NOT silently
      mangled) and a notice is printed. The original handoff is left alone.
    - A ``.bak.<timestamp>.md`` snapshot of each rewritten handoff is created
      in ``dev/handoffs/`` so the rewrite is reversible.

Limitations:
    - Skips ``*.bak.*.md`` files automatically.
    - If a handoff has no ``## 🧠 Technical Council Deliberation`` section
      we can't extract the verdict, so it's skipped with a clear message.
"""

from __future__ import annotations

import argparse
import difflib
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
# Allow `python scripts/replan_existing_handoffs.py` from the project root —
# otherwise `from src.handoff_planner import HandoffPlanner` fails because the
# script's own directory is on sys.path[0], not the project root.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

HANDOFFS_DIR = ROOT / "dev" / "handoffs"
PROPOSALS_DIR = ROOT / "dev" / "proposals"


# Section header we look for to find the embedded verdict. Matches both
# Beta and Alpha handoffs in the wild.
_VERDICT_HEADERS = [
    "## 🧠 Technical Council Deliberation",
    "## 📜 Definitive Verdict",
    "## 📜 Final Deliberation Summary",
    "## 🧠 Council Deliberation",
]


# We rewrite ONLY this block. Anchor is the literal "## 🔧 Implementation Tasks"
# header; we replace from that header (inclusive) up to the next "## " header.
_TASKS_BLOCK_RE = re.compile(
    r"(## 🔧 Implementation Tasks\b[^\n]*\n)(.*?)(?=\n## |\Z)",
    re.DOTALL,
)


def _proposal_id_from_handoff(handoff_path: Path) -> Optional[str]:
    """Derive ``ARCH-…`` or ``DEV-…`` id from the handoff filename."""
    match = re.match(
        r"((?:ARCH|DEV|NLST)-\d{8}-\d{6}-[0-9A-F]+)",
        handoff_path.name,
    )
    return match.group(1) if match else None


def _extract_verdict(text: str) -> Optional[str]:
    """Return the council-verdict section from a handoff, or None."""
    for header in _VERDICT_HEADERS:
        idx = text.find(header)
        if idx >= 0:
            # Slice from this header to the next top-level (##) header
            tail = text[idx:]
            # Find next "## " on its own line after the header
            next_h = re.search(r"\n## (?!.*Implementation Tasks)", tail[len(header):])
            if next_h is None:
                return tail
            return tail[: len(header) + next_h.start()]
    return None


def _load_proposal_body(proposal_id: str) -> str:
    candidate = PROPOSALS_DIR / f"{proposal_id}_PROPOSAL.md"
    if candidate.exists():
        return candidate.read_text(encoding="utf-8")
    return ""


def _replan_one(
    handoff_path: Path,
    *,
    apply: bool,
) -> tuple[bool, str]:
    """Plan one handoff. Returns (success, message)."""
    try:
        from src.handoff_planner import HandoffPlanner, PlannerError
    except Exception as exc:  # noqa: BLE001
        return False, f"FAILED to import HandoffPlanner: {exc!r}"

    original = handoff_path.read_text(encoding="utf-8")

    proposal_id = _proposal_id_from_handoff(handoff_path)
    if not proposal_id:
        return False, "could not derive proposal id from filename"

    verdict = _extract_verdict(original)
    if not verdict:
        return (
            False,
            "no `## 🧠 Technical Council Deliberation` (or sibling) section "
            "found — nothing to replan from",
        )

    proposal_body = _load_proposal_body(proposal_id)

    try:
        plan = HandoffPlanner().plan(
            proposal_id=proposal_id,
            proposal_body=proposal_body,
            council_report=verdict,
            binding_constraints=[],
        )
    except PlannerError as exc:
        return False, f"planner failed: {type(exc).__name__}: {exc}"
    except Exception as exc:  # noqa: BLE001
        return False, f"planner raised unexpected {type(exc).__name__}: {exc}"

    new_tasks_block = plan.to_markdown()

    # Splice into the original, preserving everything else.
    match = _TASKS_BLOCK_RE.search(original)
    if match is None:
        return (
            False,
            "no `## 🔧 Implementation Tasks` header found — refusing to "
            "guess where to put the plan",
        )

    new_content = (
        original[: match.start(1)]
        + match.group(1)              # the header itself
        + new_tasks_block             # planner output
        + "\n"
        + original[match.end(2):]     # everything after the old block
    )

    if new_content == original:
        return True, "no change (plan rendered identically)"

    diff_lines = list(
        difflib.unified_diff(
            original.splitlines(keepends=True),
            new_content.splitlines(keepends=True),
            fromfile=str(handoff_path.name) + " (before)",
            tofile=str(handoff_path.name) + " (after)",
            n=2,
        )
    )

    if not apply:
        sample = "".join(diff_lines[:30])
        return True, f"DRY-RUN diff ({len(diff_lines)} lines, first 30 shown):\n{sample}"

    # Apply path: snapshot first, then write.
    backup_path = handoff_path.with_name(
        handoff_path.stem
        + f".bak.{datetime.now().strftime('%Y%m%dT%H%M%S')}.md"
    )
    backup_path.write_text(original, encoding="utf-8")
    handoff_path.write_text(new_content, encoding="utf-8")
    return True, f"REWRITTEN (backup at {backup_path.name})"


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually rewrite the files. Without this flag the script is dry-run.",
    )
    parser.add_argument(
        "--only",
        type=str,
        default=None,
        help="Process only the handoff whose filename contains this substring.",
    )
    args = parser.parse_args(argv)

    if not HANDOFFS_DIR.exists():
        print(f"ERROR: handoffs dir not found: {HANDOFFS_DIR}", file=sys.stderr)
        return 2

    candidates = sorted(
        p for p in HANDOFFS_DIR.glob("*.md")
        if ".bak." not in p.name and p.is_file()
    )
    if args.only:
        candidates = [p for p in candidates if args.only in p.name]
        if not candidates:
            print(f"No handoff matched --only={args.only!r}", file=sys.stderr)
            return 2

    print(f"Mode: {'APPLY' if args.apply else 'DRY-RUN'}")
    print(f"Handoffs to consider: {len(candidates)}")
    print()

    failures: list[tuple[Path, str]] = []
    successes: list[tuple[Path, str]] = []
    for handoff in candidates:
        ok, msg = _replan_one(handoff, apply=args.apply)
        prefix = "OK" if ok else "SKIP"
        print(f"[{prefix}] {handoff.name}")
        if not ok or args.apply:
            print(f"        {msg}")
        if ok:
            successes.append((handoff, msg))
        else:
            failures.append((handoff, msg))

    print()
    print(f"Summary: {len(successes)} processed, {len(failures)} skipped.")
    if failures and not args.apply:
        print("(Failures in --dry-run are informational; the files are unchanged.)")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
