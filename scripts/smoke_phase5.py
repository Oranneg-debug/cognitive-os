#!/usr/bin/env python3
"""E1: Phase 5 production smoke test.

Three probes, each fast (<1s), no LLM dependency. Together they exercise the
production wiring that must work for a Phase 5 deploy:

  e1a  Boot-time validators (lifespan handlers from commit 24c129c):
       routing_rules.yaml + state_machine.yaml load cleanly, ApprovalLogger
       composite index exists, dev/failed_routings/ is reachable.

  e1b  OutputRouter classifies a fake `#decision` synthesis to `decisions`
       and writes it via the REAL FilesystemBackendWriter at the production
       path. Verifies routing landed in dev/decisions/ and NOT under
       AI-Help/cognitive-os/.

  e1c  ApprovalLogger gains one entry for a SMOKE proposal_id AND
       kanban_store.add_card/move_card succeed against the prod SQLite.
       Both are the concrete signals the handoff E1 spec lines 199-200
       asked for ("kanban card status updated" + "approval_log SQLite
       gained one entry"), exercised against production state without
       running the full WorkflowEngine saga (which would touch real git
       branches/tags). 2026-05-26: rewritten after the file-watcher
       (kanban_processor.py) was deleted — board state is now SQLite.

Usage:
    python scripts/smoke_phase5.py                # run all three probes
    python scripts/smoke_phase5.py e1a            # single probe
    python scripts/smoke_phase5.py e1b
    python scripts/smoke_phase5.py e1c

Exit 0 iff all selected probes pass. Exit 1 + diagnostic JSON on stdout.
All probe progress / status lines go to stderr so stdout is a single
parseable JSON document at exit.
"""

from __future__ import annotations

import argparse
import json
import secrets
import sqlite3
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List

# Ensure repo root is on sys.path before importing src.*
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _eprint(msg: str) -> None:
    print(msg, file=sys.stderr)


def _new_smoke_id() -> str:
    """Smoke proposal IDs use the DEV- prefix so prod accepts them."""
    # Format must match kanban_store's expected DEV-YYYYMMDD-HHMMSS-XXXXXXXX
    # (compact date, no internal dash inside the rand suffix).
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    rand = secrets.token_hex(4).upper()
    return f"DEV-{ts}-{rand}"


# ----------------------------------------------------------------------------
# E1a — Boot-time validator check
# ----------------------------------------------------------------------------
def probe_e1a() -> Dict[str, Any]:
    _eprint("[e1a] running boot-time validators...")
    from src.api import (
        _validate_failed_routings_dir,
        _validate_routing_rules,
        _validate_state_machine,
        _validate_approval_logger_index,
    )
    _validate_failed_routings_dir()
    _validate_routing_rules()
    _validate_state_machine()
    _validate_approval_logger_index()
    _eprint("[e1a] PASS")
    return {"probe": "e1a", "status": "pass"}


# ----------------------------------------------------------------------------
# E1b — Direct OutputRouter routing test
# ----------------------------------------------------------------------------
def probe_e1b(smoke_id: str) -> Dict[str, Any]:
    _eprint(f"[e1b] routing fake #decision synthesis ({smoke_id})...")
    from src.api import output_router  # production instance built at api.py import
    from src.paths import VAULT_AI_HELP

    fake_synthesis = (
        "# Council Decision (Smoke)\n\n"
        "#decision\n\n"
        f"E1b smoke fixture for {smoke_id}.\n"
    )
    decision = output_router.route(fake_synthesis)
    written_path = output_router.apply(fake_synthesis, decision)

    if decision.destination != "decisions":
        raise AssertionError(
            f"expected destination='decisions', got '{decision.destination}'"
        )
    if "AI-Help" in str(written_path):
        raise AssertionError(f"file landed under AI-Help: {written_path}")
    try:
        if VAULT_AI_HELP in written_path.resolve().parents:
            raise AssertionError(f"file landed under VAULT_AI_HELP: {written_path}")
    except (OSError, ValueError):
        pass  # vault may be unreachable; the "AI-Help" string check still applies
    if not written_path.exists():
        raise AssertionError(f"router said it wrote {written_path}, file missing")

    _eprint(f"[e1b] PASS (wrote {written_path})")
    return {
        "probe": "e1b",
        "status": "pass",
        "smoke_id": smoke_id,
        "rule_name": decision.rule_name,
        "destination": decision.destination,
        "written_path": str(written_path),
    }


# ----------------------------------------------------------------------------
# E1c — ApprovalLogger + kanban_store wiring against real prod state
# ----------------------------------------------------------------------------
def probe_e1c(smoke_id: str) -> Dict[str, Any]:
    _eprint(f"[e1c] exercising kanban_store + approval_log wiring ({smoke_id})...")
    import asyncio
    from src.approval_logger import ApprovalLogger
    from src.kanban_store import KanbanStore
    from src.paths import PROPOSALS_DIR

    # ---- Step 1: write a real proposal file (so backend twin path is realistic).
    proposal_path = PROPOSALS_DIR / f"{smoke_id}_PROPOSAL.md"
    proposal_path.write_text(
        "---\n"
        f"proposal_id: {smoke_id}\n"
        "phase: proposal\n"
        "status: pending_approval\n"
        "approver: null\n"
        "severity: low\n"
        "depends_on: []\n"
        "---\n"
        "# SMOKE FIXTURE — safe to delete\n"
        "\n"
        "E1c smoke probe fixture. Cleanup runs in the finally block.\n",
        encoding="utf-8",
    )
    _eprint(f"[e1c]   wrote {proposal_path}")

    # ---- Step 2: kanban_store add_card + move_card round-trip.
    store = KanbanStore()
    card = asyncio.run(store.add_card(
        proposal_id=smoke_id,
        prefix="DEV",
        column_name="backlog",
        title="E1c smoke fixture",
        severity="low",
        origin="smoke_phase5",
        approver="SMOKE_TEST",
        reason="E1c probe",
    ))
    if card.column_name != "backlog":
        raise AssertionError(f"add_card landed in {card.column_name!r}, expected 'backlog'")

    moved = asyncio.run(store.move_card(
        proposal_id=smoke_id,
        target_column="proposal",
        approver="SMOKE_TEST",
        reason="E1c move probe",
    ))
    if moved.column_name != "proposal":
        raise AssertionError(f"move_card landed in {moved.column_name!r}, expected 'proposal'")
    _eprint("[e1c]   PASS kanban_store add+move round-trip")

    # ---- Step 3: ApprovalLogger gains an entry for this smoke_id.
    logger = ApprovalLogger()
    entry_id = logger.log_approval(
        proposal_id=smoke_id,
        phase="proposal",
        status="recorded",
        approver="SMOKE_TEST",
        reason="E1c smoke probe entry — safe to delete",
        decision_log_path=None,
    )
    if not isinstance(entry_id, int) or entry_id < 0:
        raise AssertionError(f"log_approval returned non-positive id: {entry_id}")

    # Verify the row landed.
    conn = sqlite3.connect(str(logger.db_path))
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM approval_log WHERE proposal_id = ?",
            (smoke_id,),
        )
        count = cur.fetchone()[0]
    finally:
        conn.close()
    if count < 1:
        raise AssertionError(
            f"approval_log has {count} entries for {smoke_id}, expected >= 1"
        )

    _eprint(f"[e1c] PASS (entry_id={entry_id}, approval_log count={count})")
    return {
        "probe": "e1c",
        "status": "pass",
        "smoke_id": smoke_id,
        "proposal_path": str(proposal_path),
        "approval_log_entry_id": entry_id,
        "approval_log_count": count,
    }


# ----------------------------------------------------------------------------
# Cleanup (idempotent, always runs)
# ----------------------------------------------------------------------------
def cleanup(smoke_id: str, written_decision_path: Path | None) -> List[str]:
    """Best-effort cleanup. Returns a list of warning strings.

    Never raises — cleanup must not crash the exit code or mask the real
    probe result.
    """
    warnings: List[str] = []
    from src.paths import PROPOSALS_DIR
    from src.approval_logger import ApprovalLogger

    # Decision artifact written by e1b.
    if written_decision_path is not None:
        try:
            if written_decision_path.exists():
                written_decision_path.unlink()
                _eprint(f"[cleanup]   removed {written_decision_path}")
        except OSError as exc:
            warnings.append(f"failed to delete {written_decision_path}: {exc}")

    # Backend proposal written by e1c.
    backend_proposal = PROPOSALS_DIR / f"{smoke_id}_PROPOSAL.md"
    try:
        if backend_proposal.exists():
            backend_proposal.unlink()
            _eprint(f"[cleanup]   removed {backend_proposal}")
    except OSError as exc:
        warnings.append(f"failed to delete {backend_proposal}: {exc}")

    # Kanban card written by e1c.
    try:
        import asyncio
        from src.kanban_store import KanbanStore
        store = KanbanStore()
        asyncio.run(store.delete_card(smoke_id))
        _eprint(f"[cleanup]   removed kanban card {smoke_id}")
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"failed to delete kanban card {smoke_id}: {exc}")

    # approval_log row written by e1c.
    try:
        logger = ApprovalLogger()
        conn = sqlite3.connect(str(logger.db_path))
        try:
            conn.execute(
                "DELETE FROM approval_log WHERE proposal_id = ?", (smoke_id,)
            )
            conn.commit()
            _eprint(f"[cleanup]   purged approval_log rows for {smoke_id}")
        finally:
            conn.close()
    except sqlite3.Error as exc:
        warnings.append(f"failed to purge approval_log rows: {exc}")

    return warnings


# ----------------------------------------------------------------------------
# Driver
# ----------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 5 production smoke test.")
    parser.add_argument(
        "probe",
        nargs="?",
        default="all",
        choices=["all", "e1a", "e1b", "e1c"],
        help="Which probe(s) to run. Default: all.",
    )
    args = parser.parse_args()

    smoke_id = _new_smoke_id()
    _eprint(f"[smoke] proposal_id={smoke_id} probe={args.probe}")

    results: Dict[str, Dict[str, Any]] = {}
    written_decision_path: Path | None = None
    overall_status = "pass"

    def _record_failure(probe: str, exc: BaseException) -> None:
        nonlocal overall_status
        overall_status = "fail"
        results[probe] = {
            "probe": probe,
            "status": "fail",
            "smoke_id": smoke_id,
            "error_type": type(exc).__name__,
            "error": str(exc),
            "traceback": traceback.format_exc(limit=4),
        }
        _eprint(f"[{probe}] FAIL: {type(exc).__name__}: {exc}")

    selected = ["e1a", "e1b", "e1c"] if args.probe == "all" else [args.probe]

    try:
        if "e1a" in selected:
            try:
                results["e1a"] = probe_e1a()
            except Exception as exc:
                _record_failure("e1a", exc)

        if "e1b" in selected:
            try:
                r = probe_e1b(smoke_id)
                results["e1b"] = r
                written_decision_path = Path(r["written_path"])
            except Exception as exc:
                _record_failure("e1b", exc)

        if "e1c" in selected:
            try:
                results["e1c"] = probe_e1c(smoke_id)
            except Exception as exc:
                _record_failure("e1c", exc)
    finally:
        warnings = cleanup(smoke_id, written_decision_path)

    exit_code = 0 if overall_status == "pass" else 1
    output: Dict[str, Any] = {
        "smoke_id": smoke_id,
        "selected_probes": selected,
        "overall_status": overall_status,
        "exit_code": exit_code,
        "probes": results,
        "cleanup_warnings": warnings,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    print(json.dumps(output, indent=2))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
