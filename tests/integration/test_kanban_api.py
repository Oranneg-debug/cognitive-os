"""Integration tests for the kanban migration API — ARCH-DA5B0A2D (A3).

Exercises the kanban endpoints end-to-end through the FastAPI
``TestClient``. The store is redirected to ``tmp_path`` per-test via
monkeypatching the module-level singleton — production
``dev/kanban_state.sqlite`` is never written.

The vault Dev-KanBan.md mirror was deleted 2026-05-26; the dashboard
at http://127.0.0.1:5000 is the only board editor now.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

import src.api as api_mod
from src.api import app
from src.approval_logger import ApprovalLogger
from src.kanban_store import CANONICAL_COLUMNS, KanbanStore


# ════════════════════════════════════════════════════════════════════
#  Fixtures
# ════════════════════════════════════════════════════════════════════


@pytest.fixture()
def isolated_kanban(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Redirect kanban_store to ``tmp_path`` for one test.

    Substitutes ``src.api.kanban_store`` → new ``KanbanStore`` rooted at
    tmp_path. Initialises the schema synchronously before yielding so
    endpoints don't depend on the FastAPI lifespan.
    """
    db_path = tmp_path / "kanban_state.sqlite"
    backup_dir = tmp_path / ".backups"
    fake_store = KanbanStore(db_path=db_path, backup_dir=backup_dir)
    asyncio.run(fake_store.init_schema())

    monkeypatch.setattr(api_mod, "kanban_store", fake_store)

    # Isolate ApprovalLogger so the proposal-stage approval gate reads
    # from tmp_path, not production dev/decisions/index.sqlite.
    fake_decisions = tmp_path / "decisions"
    fake_decisions.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("src.approval_logger.DECISIONS_DIR", fake_decisions)
    monkeypatch.setattr(
        "src.approval_logger.DB_PATH", fake_decisions / "index.sqlite"
    )

    # Disable background tasks (severity dispatcher + beta council) — they
    # would otherwise try to call the orchestrator / LM Studio in tests.
    monkeypatch.setattr(
        api_mod, "_dispatch_proposal_council", lambda *a, **k: None
    )
    monkeypatch.setattr(
        api_mod, "_run_beta_council_and_handoff", lambda *a, **k: None
    )

    yield tmp_path


def _seed_approval(proposal_id: str, decision: str = "APPROVED") -> None:
    """Helper: write an approval_log row so the proposal→beta gate passes."""
    ApprovalLogger().log_approval(
        proposal_id=proposal_id,
        phase="proposal_council",
        status=decision,
        approver="test_fixture",
        reason="seeded by test",
    )


@pytest.fixture()
def client(isolated_kanban: Path) -> Iterator[TestClient]:
    """FastAPI TestClient with isolated kanban state.

    We deliberately do NOT enter the app's lifespan (``with TestClient(app):``)
    because the production lifespan tries to import LM Studio + run UoW
    recovery + validate routing rules — all heavy and irrelevant here.
    The isolated_kanban fixture initialises the schema directly.
    """
    yield TestClient(app)


# ════════════════════════════════════════════════════════════════════
#  GET /api/kanban/board
# ════════════════════════════════════════════════════════════════════


def test_get_board_returns_six_empty_columns(client: TestClient):
    """A3.1 — empty board still lists all six canonical columns."""
    r = client.get("/api/kanban/board")
    assert r.status_code == 200, r.text
    body = r.json()
    assert [c["name"] for c in body["columns"]] == list(CANONICAL_COLUMNS)
    assert all(c["cards"] == [] for c in body["columns"])
    assert "generated_at" in body


# ════════════════════════════════════════════════════════════════════
#  POST /api/kanban/cards
# ════════════════════════════════════════════════════════════════════


def test_add_card_happy_path_creates_card(client: TestClient, isolated_kanban: Path):
    """A3.2 — add_card returns the card and persists it to SQLite."""
    payload = {
        "proposal_id": "ARCH-API-001",
        "prefix": "ARCH",
        "column_name": "proposal",
        "title": "API test card",
        "severity": "medium",
        "approver": "test-suite",
    }
    r = client.post("/api/kanban/cards", json=payload)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "success"
    assert body["card"]["proposal_id"] == "ARCH-API-001"
    assert body["card"]["column_name"] == "proposal"

    # Confirm via GET that the card landed in the store.
    board = client.get("/api/kanban/board").json()
    proposal_col = next(c for c in board["columns"] if c["name"] == "proposal")
    assert any(card["proposal_id"] == "ARCH-API-001" for card in proposal_col["cards"])


def test_add_card_rejects_unknown_column_with_422(client: TestClient):
    """A3.3 — InvalidColumn surfaces as HTTP 422, not 500."""
    r = client.post("/api/kanban/cards", json={
        "proposal_id": "ARCH-API-002",
        "prefix": "ARCH",
        "column_name": "purgatory",
        "approver": "test",
    })
    assert r.status_code == 422, r.text
    assert "Invalid column" in r.json()["detail"]


def test_add_card_rejects_unknown_prefix_with_422(client: TestClient):
    """A3.4 — InvalidPrefix surfaces as HTTP 422."""
    r = client.post("/api/kanban/cards", json={
        "proposal_id": "XXX-NOPE",
        "prefix": "XXX",
        "column_name": "proposal",
        "approver": "test",
    })
    assert r.status_code == 422, r.text
    assert "Invalid prefix" in r.json()["detail"]


def test_add_card_is_idempotent(client: TestClient):
    """A3.5 — re-POSTing the same proposal_id returns the existing card unchanged."""
    payload = {
        "proposal_id": "ARCH-IDEM-001",
        "prefix": "ARCH",
        "column_name": "proposal",
        "approver": "test",
    }
    r1 = client.post("/api/kanban/cards", json=payload)
    assert r1.status_code == 200
    # Second call with DIFFERENT column should NOT overwrite
    r2 = client.post("/api/kanban/cards", json={**payload, "column_name": "backlog"})
    assert r2.status_code == 200
    assert r2.json()["card"]["column_name"] == "proposal"  # original survives


# ════════════════════════════════════════════════════════════════════
#  PUT /api/kanban/cards/{id}
# ════════════════════════════════════════════════════════════════════


def test_update_card_happy_path(client: TestClient):
    """Test that we can update a card's severity."""
    client.post("/api/kanban/cards", json={
        "proposal_id": "ARCH-UPDATE-001",
        "prefix": "ARCH",
        "column_name": "proposal",
        "approver": "test",
    })
    r = client.put("/api/kanban/cards/ARCH-UPDATE-001", json={"severity": "high"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["card"]["severity"] == "high"


def test_update_card_404s_on_missing(client: TestClient):
    """Test that updating a non-existent card returns 404."""
    r = client.put("/api/kanban/cards/NON-EXISTENT", json={"severity": "high"})
    assert r.status_code == 404


def test_update_card_400s_on_no_updates(client: TestClient):
    """Test that an empty update request returns 400."""
    client.post("/api/kanban/cards", json={
        "proposal_id": "ARCH-UPDATE-002",
        "prefix": "ARCH",
        "column_name": "proposal",
        "approver": "test",
    })
    r = client.put("/api/kanban/cards/ARCH-UPDATE-002", json={})
    assert r.status_code == 400


# ════════════════════════════════════════════════════════════════════
#  DELETE /api/kanban/cards/{id}
# ════════════════════════════════════════════════════════════════════


def test_delete_card_happy_path(client: TestClient):
    """Test that we can delete a card."""
    client.post("/api/kanban/cards", json={
        "proposal_id": "ARCH-DELETE-001",
        "prefix": "ARCH",
        "column_name": "proposal",
        "approver": "test",
    })
    # Verify it exists first
    r_get = client.get("/api/kanban/cards/ARCH-DELETE-001")
    assert r_get.status_code == 200

    r_del = client.delete("/api/kanban/cards/ARCH-DELETE-001")
    assert r_del.status_code == 200

    # Verify it's gone
    r_get2 = client.get("/api/kanban/cards/ARCH-DELETE-001")
    assert r_get2.status_code == 404


def test_delete_card_404s_on_missing(client: TestClient):
    """Test that deleting a non-existent card returns 404."""
    r = client.delete("/api/kanban/cards/NON-EXISTENT")
    assert r.status_code == 404


# ════════════════════════════════════════════════════════════════════
#  POST /api/workflow/transition
# ════════════════════════════════════════════════════════════════════


def test_transition_moves_card_and_writes_mirror(client: TestClient):
    """A3.6 — transition updates SQLite and refreshes the vault mirror."""
    client.post("/api/kanban/cards", json={
        "proposal_id": "ARCH-MV-001",
        "prefix": "ARCH",
        "column_name": "proposal",
        "approver": "test",
    })
    _seed_approval("ARCH-MV-001")  # new gate: required for proposal→beta
    r = client.post("/api/workflow/transition", json={
        "proposal_id": "ARCH-MV-001",
        "target_column": "beta testing",
        "target_substatus": "planning",
        "approver": "alice",
        "reason": "approved",
        "gate_passed": 1,
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["card"]["column_name"] == "beta testing"
    assert body["card"]["substatus"] == "planning"
    # Confirm via GET that the card is now under "beta testing".
    board = client.get("/api/kanban/board").json()
    beta_col = next(c for c in board["columns"] if c["name"] == "beta testing")
    assert any(card["proposal_id"] == "ARCH-MV-001" for card in beta_col["cards"])


def test_transition_returns_404_for_missing_card(client: TestClient):
    """A3.7 — CardNotFound → HTTP 404, not 500."""
    r = client.post("/api/workflow/transition", json={
        "proposal_id": "DOES-NOT-EXIST-001",
        "target_column": "proposal",
        "approver": "test",
    })
    assert r.status_code == 404, r.text


def test_transition_rejects_invalid_column_with_422(client: TestClient):
    """A3.8 — invalid target_column → HTTP 422."""
    client.post("/api/kanban/cards", json={
        "proposal_id": "ARCH-MV-002",
        "prefix": "ARCH",
        "column_name": "proposal",
        "approver": "test",
    })
    r = client.post("/api/workflow/transition", json={
        "proposal_id": "ARCH-MV-002",
        "target_column": "purgatory",
        "approver": "test",
    })
    assert r.status_code == 422, r.text


def test_transition_rejects_bad_gate_passed_with_422(client: TestClient):
    """A3.9 — gate_passed must be -1/0/1; anything else → HTTP 422."""
    client.post("/api/kanban/cards", json={
        "proposal_id": "ARCH-MV-003",
        "prefix": "ARCH",
        "column_name": "backlog",
        "approver": "test",
    })
    # Target 'proposal' (not 'beta testing') so the new approval-gate
    # check doesn't pre-empt the gate_passed validation. The approval
    # gate only fires on transitions INTO beta_testing.
    r = client.post("/api/workflow/transition", json={
        "proposal_id": "ARCH-MV-003",
        "target_column": "proposal",
        "approver": "test",
        "gate_passed": 42,
    })
    assert r.status_code == 422, r.text


def test_transition_rejects_proposal_to_beta_without_approval(client: TestClient):
    """New: proposal → beta_testing blocked when no APPROVED row exists."""
    client.post("/api/kanban/cards", json={
        "proposal_id": "ARCH-GATE-001",
        "prefix": "ARCH",
        "column_name": "proposal",
        "approver": "test",
    })
    r = client.post("/api/workflow/transition", json={
        "proposal_id": "ARCH-GATE-001",
        "target_column": "beta testing",
        "approver": "test",
    })
    assert r.status_code == 422, r.text
    assert "council has not APPROVED" in r.json()["detail"]


def test_transition_rejects_proposal_to_beta_when_rejected(client: TestClient):
    """New: proposal → beta_testing blocked when council REJECTED."""
    client.post("/api/kanban/cards", json={
        "proposal_id": "ARCH-GATE-002",
        "prefix": "ARCH",
        "column_name": "proposal",
        "approver": "test",
    })
    _seed_approval("ARCH-GATE-002", decision="REJECTED")
    r = client.post("/api/workflow/transition", json={
        "proposal_id": "ARCH-GATE-002",
        "target_column": "beta testing",
        "approver": "test",
    })
    assert r.status_code == 422, r.text


def test_transition_allows_proposal_to_beta_when_auto_approved(client: TestClient):
    """New: AUTO-APPROVED (low severity) lets the card through the gate."""
    client.post("/api/kanban/cards", json={
        "proposal_id": "ARCH-GATE-003",
        "prefix": "ARCH",
        "column_name": "proposal",
        "approver": "test",
    })
    _seed_approval("ARCH-GATE-003", decision="AUTO-APPROVED")
    r = client.post("/api/workflow/transition", json={
        "proposal_id": "ARCH-GATE-003",
        "target_column": "beta testing",
        "approver": "test",
    })
    assert r.status_code == 200, r.text


# ════════════════════════════════════════════════════════════════════
#  POST /api/workflow/rollback/{id}
# ════════════════════════════════════════════════════════════════════


def test_rollback_reverts_to_previous_column(client: TestClient):
    """A3.10 — rollback after a forward move puts the card back."""
    client.post("/api/kanban/cards", json={
        "proposal_id": "ARCH-RB-001",
        "prefix": "ARCH",
        "column_name": "proposal",
        "approver": "test",
    })
    _seed_approval("ARCH-RB-001")
    client.post("/api/workflow/transition", json={
        "proposal_id": "ARCH-RB-001",
        "target_column": "beta testing",
        "approver": "alice",
    })

    r = client.post("/api/workflow/rollback/ARCH-RB-001")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["rolled_back_to"] == "proposal"
    assert body["card"]["column_name"] == "proposal"


def test_rollback_returns_409_when_no_prior_transition(client: TestClient):
    """A3.11 — a brand-new card has only its creation row → HTTP 409."""
    client.post("/api/kanban/cards", json={
        "proposal_id": "ARCH-RB-002",
        "prefix": "ARCH",
        "column_name": "proposal",
        "approver": "test",
    })
    r = client.post("/api/workflow/rollback/ARCH-RB-002")
    assert r.status_code == 409, r.text


def test_rollback_returns_404_for_missing_card(client: TestClient):
    """A3.12 — rolling back a non-existent card → HTTP 404."""
    r = client.post("/api/workflow/rollback/NEVER-EXISTED-001")
    assert r.status_code == 404, r.text


def test_rollback_appends_rollback_transition_to_history(client: TestClient):
    """A3.13 — rollback is append-only; original history is preserved."""
    client.post("/api/kanban/cards", json={
        "proposal_id": "ARCH-RB-HIST-001",
        "prefix": "ARCH",
        "column_name": "proposal",
        "approver": "test",
    })
    _seed_approval("ARCH-RB-HIST-001")
    client.post("/api/workflow/transition", json={
        "proposal_id": "ARCH-RB-HIST-001",
        "target_column": "beta testing",
        "approver": "alice",
    })
    client.post("/api/workflow/rollback/ARCH-RB-HIST-001")

    state = client.get("/api/workflow/state/ARCH-RB-HIST-001").json()
    # 1 creation + 1 forward + 1 rollback = 3 transitions
    assert state["history_count"] == 3
    last = state["history"][-1]
    assert last["to_column"] == "proposal"
    assert "rollback" in (last["reason"] or "").lower()


# ════════════════════════════════════════════════════════════════════
#  GET /api/workflow/state/{id}
# ════════════════════════════════════════════════════════════════════


def test_get_state_returns_card_and_default_history_limit(client: TestClient):
    """A3.14 — /state returns the card and up to 10 transitions by default."""
    client.post("/api/kanban/cards", json={
        "proposal_id": "ARCH-ST-001",
        "prefix": "ARCH",
        "column_name": "proposal",
        "approver": "test",
    })

    r = client.get("/api/workflow/state/ARCH-ST-001")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["card"]["proposal_id"] == "ARCH-ST-001"
    assert body["history_count"] == 1  # just the creation row
    assert body["history"][0]["from_column"] is None


def test_get_state_respects_history_limit_param(client: TestClient):
    """A3.15 — ?history_limit=N returns the LAST N rows in chronological order."""
    client.post("/api/kanban/cards", json={
        "proposal_id": "ARCH-ST-LIM-001",
        "prefix": "ARCH",
        "column_name": "backlog",
        "approver": "test",
    })
    # Move via each column. Seed approval AFTER the proposal hop so the
    # proposal→beta gate passes for the next iteration.
    for col in ("proposal", "beta testing", "alpha polish", "finalized"):
        if col == "beta testing":
            _seed_approval("ARCH-ST-LIM-001")
        client.post("/api/workflow/transition", json={
            "proposal_id": "ARCH-ST-LIM-001",
            "target_column": col,
            "approver": "test",
        })

    # Get all (default 10)
    full = client.get("/api/workflow/state/ARCH-ST-LIM-001").json()
    assert full["history_count"] == 5  # 1 creation + 4 transitions

    # Get last 2
    last_two = client.get("/api/workflow/state/ARCH-ST-LIM-001?history_limit=2").json()
    assert last_two["history_count"] == 2
    assert [t["to_column"] for t in last_two["history"]] == ["alpha polish", "finalized"]


def test_get_state_returns_404_for_missing_card(client: TestClient):
    """A3.16 — unknown proposal_id → HTTP 404."""
    r = client.get("/api/workflow/state/NEVER-EXISTED-002")
    assert r.status_code == 404, r.text
