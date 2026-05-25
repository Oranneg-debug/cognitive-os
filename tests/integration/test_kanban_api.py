"""Integration tests for the kanban migration API — ARCH-DA5B0A2D (A3).

Exercises the five new endpoints end-to-end through the FastAPI
``TestClient``. The store is redirected to ``tmp_path`` per-test via
monkeypatching the module-level singleton — production
``dev/kanban_state.sqlite`` is never written.

The vault mirror is redirected the same way: each test monkeypatches
``src.kanban_renderer.KANBAN_FILE`` to ``tmp_path / "Dev-KanBan.md"``
before its first endpoint call.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

import src.api as api_mod
import src.kanban_renderer as renderer_mod
from src.api import app
from src.kanban_store import CANONICAL_COLUMNS, KanbanStore


# ════════════════════════════════════════════════════════════════════
#  Fixtures
# ════════════════════════════════════════════════════════════════════


@pytest.fixture()
def isolated_kanban(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Redirect kanban_store + renderer to ``tmp_path`` for one test.

    Substitutes:
      - ``src.api.kanban_store`` → new ``KanbanStore`` rooted at tmp_path
      - ``src.kanban_renderer.KANBAN_FILE`` → tmp_path / "Dev-KanBan.md"

    Initialises the schema synchronously before yielding so endpoints
    don't depend on the FastAPI lifespan (TestClient does run lifespan
    on enter, but we want the schema there even when callers don't use
    the context-manager form).
    """
    db_path = tmp_path / "kanban_state.sqlite"
    backup_dir = tmp_path / ".backups"
    fake_store = KanbanStore(db_path=db_path, backup_dir=backup_dir)
    asyncio.run(fake_store.init_schema())

    vault_file = tmp_path / "Dev-KanBan.md"

    monkeypatch.setattr(api_mod, "kanban_store", fake_store)
    monkeypatch.setattr(renderer_mod, "KANBAN_FILE", vault_file)

    yield tmp_path


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


def test_add_card_happy_path_creates_card_and_writes_vault_mirror(
    client: TestClient, isolated_kanban: Path
):
    """A3.2 — add_card returns the card AND triggers a vault-mirror write."""
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
    # Vault mirror was written
    vault_path = Path(body["vault_mirror"])
    assert vault_path.exists()
    assert "ARCH-API-001" in vault_path.read_text(encoding="utf-8")


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
    # Vault mirror reflects the new state
    vault = Path(body["vault_mirror"]).read_text(encoding="utf-8")
    # In the rendered file, ARCH-MV-001 should be under "## Beta Testing"
    beta_idx = vault.find("## Beta Testing")
    next_col_idx = vault.find("## Alpha Polish")
    assert beta_idx != -1 and next_col_idx != -1
    beta_block = vault[beta_idx:next_col_idx]
    assert "ARCH-MV-001" in beta_block


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
        "column_name": "proposal",
        "approver": "test",
    })
    r = client.post("/api/workflow/transition", json={
        "proposal_id": "ARCH-MV-003",
        "target_column": "beta testing",
        "approver": "test",
        "gate_passed": 42,
    })
    assert r.status_code == 422, r.text


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
    for col in ("proposal", "beta testing", "alpha polish", "finalized"):
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
