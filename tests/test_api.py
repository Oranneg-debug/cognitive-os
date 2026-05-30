"""Tests for src.api endpoints (C2 + D1 + DA5B0A2D)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.api import app


@pytest.fixture(scope="module")
def client():
    """Create a test client for the FastAPI app."""
    with TestClient(app) as c:
        yield c


class TestSystemRolesEndpoint:
    """Tests for GET /api/system/roles (C2)."""

    def test_endpoint_returns_200(self, client):
        """The endpoint should return HTTP 200 with valid JSON."""
        response = client.get("/api/system/roles")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "roles" in data

    def test_known_role_appears_in_response(self, client):
        """A known role like 'board_strategist' should appear in the roles."""
        response = client.get("/api/system/roles")
        data = response.json()
        roles = data["roles"]
        # board_strategist is defined in dev/master_config.md
        assert "board_strategist" in roles

    def test_role_has_required_fields(self, client):
        """Each role should have model, temperature, context_window, compass_weight."""
        response = client.get("/api/system/roles")
        data = response.json()
        board_role = data["roles"].get("board_strategist")
        assert board_role is not None
        assert "model" in board_role
        assert "temperature" in board_role
        assert "context_window" in board_role
        assert "compass_weight" in board_role


class TestMasterConfigEndpoint:
    """Tests for GET /api/config (existing endpoint)."""

    def test_config_endpoint_returns_200(self, client):
        """The /api/config endpoint should return HTTP 200."""
        response = client.get("/api/config")
        assert response.status_code == 200
        data = response.json()
        # Should have at least roles key
        assert "roles" in data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])