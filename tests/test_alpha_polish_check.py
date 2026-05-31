"""Tests for alpha_polish_check.py smoke gates.

This module provides pytest tests for the runtime smoke gates
introduced in ARCH-20260530-140000-B1D2E3F4 (Beta Handoff).

Tests:
    - test_smoke_import_core: Verifies core module imports work.
    - test_smoke_role_resolution: Verifies devlog_scribe role has model key.
    - test_smoke_devlog_agent_inst: Verifies DevLogAgent instantiation.
    - test_smoke_devlog_evidence: Verifies evidence gathering works.
    - test_smoke_system_context: Verifies system context building.
    - test_smoke_devlog_config: Verifies DevLogConfig defaults.
    - test_smoke_path_guard_rejects: Verifies PathGuard blocks forbidden paths.
    - test_smoke_path_guard_allows: Verifies PathGuard permits allowed paths.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Prepend cognitive-os to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.alpha_polish_check import (
    GateResult,
    smoke_devlog_agent_inst,
    smoke_devlog_config,
    smoke_devlog_evidence,
    smoke_import_core,
    smoke_path_guard_allows,
    smoke_path_guard_rejects,
    smoke_role_resolution,
    smoke_system_context,
)


def test_smoke_import_core() -> None:
    """S1: smoke_import_core gate passes when all core imports succeed.

    The gate imports:
        - src.llm_client
        - src.orchestrator
        - src.council_runner
        - src.devlog_agent
        - src.system_context_builder
        - src.path_guard

    Returns GateResult with passed=True on success.
    """
    result = smoke_import_core()

    assert isinstance(result, GateResult), "smoke_import_core must return GateResult"
    assert result.name == "smoke_import_core", f"name mismatch: {result.name}"
    assert result.passed is True, f"expected passed=True, got {result.passed}"
    assert "all core imports succeeded" in result.detail


def test_smoke_role_resolution() -> None:
    """S2: smoke_role_resolution gate passes when devlog_scribe has model key.

    The gate calls get_role_config("devlog_scribe") and checks that
    the returned dict contains a non-empty "model" key.
    """
    result = smoke_role_resolution()

    assert isinstance(result, GateResult), "smoke_role_resolution must return GateResult"
    assert result.name == "smoke_role_resolution", f"name mismatch: {result.name}"
    assert result.passed is True, f"expected passed=True, got {result.passed}"
    # Detail should contain model=<value>
    assert "model=" in result.detail, f"model key not in detail: {result.detail}"


def test_smoke_devlog_agent_inst() -> None:
    """S3: smoke_devlog_agent_inst gate passes when DevLogAgent instantiates.

    The gate calls DevLogAgent(DevLogConfig()) and checks that
    instantiation completes without raising an exception.
    """
    result = smoke_devlog_agent_inst()

    assert isinstance(result, GateResult), "smoke_devlog_agent_inst must return GateResult"
    assert result.name == "smoke_devlog_agent_inst", f"name mismatch: {result.name}"
    assert result.passed is True, f"expected passed=True, got {result.passed}"
    assert "DevLogAgent instantiated" in result.detail or "successfully" in result.detail.lower()


def test_smoke_devlog_evidence() -> None:
    """S4: smoke_devlog_evidence gate passes when evidence gathering returns data.

    The gate calls agent.gather_evidence("2026-05-30") and checks that
    the returned dict contains non-empty git_commits or council_verdicts.
    """
    result = smoke_devlog_evidence()

    assert isinstance(result, GateResult), "smoke_devlog_evidence must return GateResult"
    assert result.name == "smoke_devlog_evidence", f"name mismatch: {result.name}"
    assert result.passed is True, f"expected passed=True, got {result.passed}"
    # Detail should mention the data gathered
    assert ("commits" in result.detail.lower() or "verdicts" in result.detail.lower() or
            "evidence" in result.detail.lower())


def test_smoke_system_context() -> None:
    """S5: smoke_system_context gate passes when context builder returns long string.

    The gate calls build_universal_context() and checks that
    the returned value is a string longer than 200 characters.
    """
    result = smoke_system_context()

    assert isinstance(result, GateResult), "smoke_system_context must return GateResult"
    assert result.name == "smoke_system_context", f"name mismatch: {result.name}"
    assert result.passed is True, f"expected passed=True, got {result.passed}"
    # Detail should mention the context length
    assert "chars" in result.detail.lower() or "length" in result.detail.lower()


def test_smoke_devlog_config() -> None:
    """S6: smoke_devlog_config gate passes when DevLogConfig has correct default role.

    The gate checks that DevLogConfig().council_role equals 'devlog_scribe'.
    """
    result = smoke_devlog_config()

    assert isinstance(result, GateResult), "smoke_devlog_config must return GateResult"
    assert result.name == "smoke_devlog_config", f"name mismatch: {result.name}"
    assert result.passed is True, f"expected passed=True, got {result.passed}"
    assert "devlog_scribe" in result.detail, f"council_role should be 'devlog_scribe': {result.detail}"


def test_smoke_path_guard_rejects() -> None:
    """S7: smoke_path_guard_rejects gate passes when PathGuard blocks forbidden paths.

    The gate checks that PathGuard([".private"]).is_forbidden(".private/secret.md")
    returns True.
    """
    result = smoke_path_guard_rejects()

    assert isinstance(result, GateResult), "smoke_path_guard_rejects must return GateResult"
    assert result.name == "smoke_path_guard_rejects", f"name mismatch: {result.name}"
    assert result.passed is True, f"expected passed=True, got {result.passed}"
    # Detail should show the result
    assert "True" in result.detail or "forbidden" in result.detail.lower()


def test_smoke_path_guard_allows() -> None:
    """S8: smoke_path_guard_allows gate passes when PathGuard permits allowed paths.

    The gate checks that PathGuard([".private"]).is_forbidden("src/main.py")
    returns False.
    """
    result = smoke_path_guard_allows()

    assert isinstance(result, GateResult), "smoke_path_guard_allows must return GateResult"
    assert result.name == "smoke_path_guard_allows", f"name mismatch: {result.name}"
    assert result.passed is True, f"expected passed=True, got {result.passed}"
    # Detail should show the result
    assert "False" in result.detail or "forbidden" in result.detail.lower()