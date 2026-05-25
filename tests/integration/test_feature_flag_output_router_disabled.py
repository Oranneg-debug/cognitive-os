"""D9: Feature flag off bypasses OutputRouter subsystem.

C1 wiring test: when output_router_enabled=false, Orchestrator.__init__ sets
self.output_router = None, reverting to legacy ObsidianWriter path.

This tests the conditional in orchestrator.py lines 130-136:
    if not is_output_router_enabled():
        ...
        self.output_router = None
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

# Import the flag-checking function directly from integration_flags to avoid
# circular import issues (it lazily imports get_config internally)
from src.integration_flags import is_output_router_enabled
from src.orchestrator import Orchestrator


@pytest.mark.parametrize(
    "flag_value",
    [False, True],
    ids=["flag-disabled-clears-router", "flag-enabled-preserves-router"],
)
def test_orchestrator_respects_output_router_flag(
    monkeypatch: pytest.MonkeyPatch, flag_value: bool
) -> None:
    """Orchestrator.__init__ honours is_output_router_enabled() in both directions."""
    # --- 1. Patch the flag cache directly (no master_config fixture needed).
    # We monkeypatch is_output_router_enabled() so it returns our desired value.
    # This avoids touching _flags_cache which has lazy import dependencies.
    monkeypatch.setattr("src.integration_flags.is_output_router_enabled", lambda: flag_value)

    # --- 2. Mock heavy imports in Orchestrator.__init__
    monkeypatch.setattr("src.orchestrator.llm", MagicMock(eject_all_models=lambda: None))
    monkeypatch.setattr("src.orchestrator.MemoryFileManager", MagicMock)
    monkeypatch.setattr("src.orchestrator.SentryRouter", MagicMock)
    monkeypatch.setattr("src.orchestrator.load_dotenv", lambda *a, **k: None)
    monkeypatch.setattr(
        "src.orchestrator.get_role_config",
        lambda *a, **k: {
            "model": "test-model",
            "system_prompt": "test",
            "temperature": 0.7,
            "top_p": 0.9,
            "top_k": 40,
            "repeat_penalty": 1.0,
            "max_tokens": 2048,
            "context_window": 4096,
            "gpu_layers": 0,
            "enabled": True,
        },
    )
    monkeypatch.setattr(
        "src.orchestrator.Orchestrator._perform_startup_sync_check",
        lambda self: None,
    )

# --- 3. ALWAYS inject a mock router. The point of the flag-False case
    # is that the conditional in Orchestrator.__init__ clears the router.
    # Passing None in the flag-False case would make the assertion pass
    # trivially regardless of whether the conditional fires.
    mock_router = MagicMock(spec=["route", "apply"])
    orchestrator = Orchestrator(output_router=mock_router)

    # --- 4. Assertion: flag=False clears the router; flag=True preserves it.
    if flag_value:
        assert orchestrator.output_router is mock_router, (
            f"flag=True: injected router should be preserved, "
            f"got {orchestrator.output_router}"
        )
    else:
        assert orchestrator.output_router is None, (
            f"flag=False: injected router should be cleared to None, "
            f"got {orchestrator.output_router}"
        )
