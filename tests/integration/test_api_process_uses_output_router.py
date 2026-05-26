"""D1: POST /process uses OutputRouter end-to-end (Phase 5).

Verifies the full FastAPI -> OutputRouter -> FilesystemBackendWriter wiring:
- Boardroom synthesis (#boardroom marker) is classified as `boardroom_proposal`.
- File lands in dev/proposals/, NEVER in AI-Help/cognitive-os/.
- Response body exposes the routing_decision with rule_name + destination.

The orchestrator's LLM path is mocked; everything else (router, writer, FS)
runs for real, which is the point of an integration test.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch, AsyncMock

import pytest
from fastapi.testclient import TestClient

from src.api import app
from src.paths import DEV_DIR


BOARDROOM_FIXTURE = """# BOARDROOM SYNTHESIS

#boardroom

## Verdict
D1 integration test fixture.
"""


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_process_endpoint_routes_boardroom_to_proposals(client: TestClient) -> None:
    written_path: Path | None = None
    try:
        with patch("src.api.orchestrator.process_request", new_callable=AsyncMock, return_value=BOARDROOM_FIXTURE) as mock_proc:
            response = client.post("/api/process", json={"prompt": "test"})

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "success", body

        rd = body["routing_decision"]
        assert rd["rule_name"] == "boardroom_proposal"
        assert rd["destination"] == "proposals"

        saved = Path(body["saved_path"])
        written_path = saved
        assert saved.exists(), f"router did not produce {saved}"
        # Must be under the backend proposals dir, never under AI-Help/.
        assert saved.is_relative_to(DEV_DIR / "proposals"), saved
        assert "AI-Help" not in str(saved), saved

        # Sanity: orchestrator was actually invoked with the prompt.
        mock_proc.assert_called_once()
    finally:
        if written_path is not None and written_path.exists():
            written_path.unlink()
