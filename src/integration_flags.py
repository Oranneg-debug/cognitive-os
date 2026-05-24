"""
Integration Feature Flags - Phase 5 Migration Safety (C1).

Flags live in the YAML block of dev/master_config.md under the `integration:` key.
Read once via the canonical MasterConfig loader and cached. Restart the API to
pick up changes (matches the handoff requirement: "Read once at startup; cache").

Each flag defaults to True per CSTR-PHASE5-V2 (default-on, opt-out for rollback).

VETO COMPLIANCE:
- V4: no circular imports; lazy-import of get_config inside the loader.
- V9: explicit exceptions raised, never silently swallowed.
"""

from typing import Dict

_DEFAULTS: Dict[str, bool] = {
    "output_router_enabled": True,
    "workflow_engine_enabled": True,
    "governance_uow_enabled": True,
}

_flags_cache: Dict[str, bool] | None = None


def _load_integration_flags() -> Dict[str, bool]:
    """Load flags from master_config.md via canonical MasterConfig (cached)."""
    global _flags_cache

    if _flags_cache is not None:
        return _flags_cache

    # Lazy import: orchestrator.py imports many heavy modules, and importing it
    # at module-top would create circular import risks for writers that import
    # this module.
    from src.orchestrator import get_config

    cfg = get_config() or {}
    integration_block = cfg.get("integration") or {}

    _flags_cache = {
        name: bool(integration_block.get(name, default))
        for name, default in _DEFAULTS.items()
    }
    return _flags_cache


def get_integration_flags() -> Dict[str, bool]:
    """Return the cached integration flag dict."""
    return _load_integration_flags()


def is_output_router_enabled() -> bool:
    """C1: gate for OutputRouter wiring in orchestrator + api."""
    return _load_integration_flags()["output_router_enabled"]


def is_workflow_engine_enabled() -> bool:
    """C1: gate for WorkflowEngine wiring in kanban_processor."""
    return _load_integration_flags()["workflow_engine_enabled"]


def is_governance_uow_enabled() -> bool:
    """C1: gate for GovernanceUnitOfWork in proposal_writer + handoff_writer."""
    return _load_integration_flags()["governance_uow_enabled"]


def reset_cache_for_tests() -> None:
    """Test-only: clear the cache so a test can flip a flag and re-read."""
    global _flags_cache
    _flags_cache = None
