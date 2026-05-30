"""D3: Orchestrator routes synthesis via the real OutputRouter (Phase 5).

The spec (handoff lines 173-176) requires:
- Fire `execute_sequential_boardroom` on a fixture.
- Synthesis lands at the correct backend path per routing rules.
- `AI-Help/cognitive-os/` gains NO new files (the legacy fallback would
  write there if Orchestrator silently bypassed the router).

What this test actually exercises:
- Orchestrator's `__init__` accepts the injected OutputRouter.
- After the meeting, the scribe report is passed through
  `output_router.route(...)` + `output_router.apply(...)` â€” NOT through any
  legacy ObsidianWriter call site that targets VAULT_AI_HELP.
- The router uses real routing rules (config/routing_rules.yaml) and the real
  FilesystemBackendWriter â€” both are redirected under tmp_path via
  monkeypatching the module-level destination constants on `src.output_router`.

If Orchestrator regressed to legacy behavior (e.g. a future commit ripped out
the `if self.output_router is not None:` block), the return value would be a
str (the raw report) and the AI-Help directory would gain a file.
"""

from __future__ import annotations

import json
import traceback
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.filesystem_backend_writer import FilesystemBackendWriter
from src.orchestrator import Orchestrator
from src.output_router import OutputRouter


SCRIBE_REPORT = (
    "# BOARDROOM SYNTHESIS\n\n"
    "#boardroom\n\n"
    "## Summary\nD3 fixture: this must route to `proposals`, not AI-Help.\n"
)


# Global counter for all LLM calls - shared across all mock invocations
_llm_call_counter = {"value": 0}


def _llm_side_effect_factory() -> callable:
    """Return a side_effect that yields valid JSON for all 13 LLM calls.
    
    Expected call sequence (council_runner.py):
    1. Moderator framing (next_role selection)
    2. board_alpha agent
    3. brand_guard_board_alpha audit
    4. board_beta agent
    5. brand_guard_board_beta audit
    6. board_gamma agent
    7. brand_guard_board_gamma audit
    8. board_delta agent
    9. brand_guard_board_delta audit
    10. board_epsilon agent
    11. brand_guard_board_epsilon audit
    12. board_chairman synthesis
    13. scribe report
    
    Uses a GLOBAL counter so both patches share state.
    """
    def _side(*args, **kwargs):
        _llm_call_counter["value"] += 1
        call_num = _llm_call_counter["value"]
        
        # Debug logging
        print(f"[MOCK_CALL_{call_num}]")
        
        if call_num == 1:
            return json.dumps({"next_role": "board_member_alpha", "transition_reason": "Start deliberation"})
        elif call_num == 2:
            return json.dumps({"opinion": "Opinion from board_alpha", "analysis": "Detailed analysis here"})
        elif call_num == 3:
            return json.dumps({"approved": True, "reasoning": "Looks good"})
        elif call_num == 4:
            return json.dumps({"opinion": "Opinion from board_beta", "analysis": "Detailed analysis here"})
        elif call_num == 5:
            return json.dumps({"approved": True, "reasoning": "Looks good"})
        elif call_num == 6:
            return json.dumps({"opinion": "Opinion from board_gamma", "analysis": "Detailed analysis here"})
        elif call_num == 7:
            return json.dumps({"approved": True, "reasoning": "Looks good"})
        elif call_num == 8:
            return json.dumps({"opinion": "Opinion from board_delta", "analysis": "Detailed analysis here"})
        elif call_num == 9:
            return json.dumps({"approved": True, "reasoning": "Looks good"})
        elif call_num == 10:
            return json.dumps({"opinion": "Opinion from board_epsilon", "analysis": "Detailed analysis here"})
        elif call_num == 11:
            return json.dumps({"approved": True, "reasoning": "Looks good"})
        elif call_num == 12:
            return json.dumps({"synthesis": "Final synthesized view", "recommendation": "Proceed with proposal"})
        elif call_num == 13:
            return SCRIBE_REPORT
        else:
            # Safety fallback - don't fail, just return a default response
            print(f"[MOCK_CALL_{call_num}] Default fallback (shouldn't reach here)")
            return json.dumps({"approved": True, "opinion": "ok"})
    
    return _side


@pytest.fixture
def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_boardroom_synthesis_routes_via_output_router(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    project_root: Path,
) -> None:
    # Reset counter before each test
    _llm_call_counter["value"] = 0
    
    # --- 1. Redirect every destination OutputRouter knows about into tmp_path.
    proposals_dir = tmp_path / "dev" / "proposals"
    decisions_dir = tmp_path / "dev" / "decisions"
    handoffs_dir = tmp_path / "dev" / "handoffs"
    reports_dir = tmp_path / "dev" / "reports"
    archives_dir = tmp_path / "archives"
    dead_letter_dir = tmp_path / "dev" / "failed_routings"

    monkeypatch.setattr("src.output_router.PROPOSALS_DIR", proposals_dir)
    monkeypatch.setattr("src.output_router.DECISIONS_DIR", decisions_dir)
    monkeypatch.setattr("src.output_router.HANDOFFS_DIR", handoffs_dir)
    monkeypatch.setattr("src.output_router.REPORTS_DIR", reports_dir)
    monkeypatch.setattr("src.output_router.ARCHIVES_DIR", archives_dir)

    # --- 2. Redirect AI-Help so the legacy-fallback negative assertion is verifiable.
    vault_ai_help = tmp_path / "AI-Help"
    vault_council_outputs = vault_ai_help / "cognitive-os"
    vault_council_outputs.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("src.paths.VAULT_AI_HELP", vault_ai_help)
    monkeypatch.setattr("src.paths.VAULT_COUNCIL_OUTPUTS", vault_council_outputs)

    # --- 3. Redirect ApprovalLogger defaults.
    monkeypatch.setattr("src.approval_logger.DECISIONS_DIR", decisions_dir)
    monkeypatch.setattr("src.approval_logger.DB_PATH", decisions_dir / "index.sqlite")

    # --- 4. Build the real OutputRouter against the real routing rules but
    # with a backend writer rooted under tmp_path.
    rules_path = project_root / "config" / "routing_rules.yaml"
    backend = FilesystemBackendWriter(
        base_dir=tmp_path / "dev",
        dead_letter_dir=dead_letter_dir,
    )
    router = OutputRouter(
        rules_path=rules_path,
        backend_writer=backend,
        dead_letter_dir=dead_letter_dir,
    )

    # --- 5. Patch the LM Studio / orchestrator-internal symbols.
    # Use a SINGLE mock with SHARED state for both patches to ensure coordination
    shared_mock = MagicMock()
    shared_mock.generate_response.side_effect = _llm_side_effect_factory()
    monkeypatch.setattr("src.orchestrator.llm", shared_mock)
    monkeypatch.setattr("src.council_runner.llm", shared_mock)

    # Patch get_role_config in council_runner (not orchestrator) - the actual callee
    def fake_get_role_config(role_key: str) -> dict:
        return {
            "model": "test-model",
            "system_prompt": f"test {role_key} prompt",
            "temperature": 0.7,
            "top_p": 0.9,
            "top_k": 40,
            "repeat_penalty": 1.0,
            "max_tokens": 2048,
            "context_window": 4096,
            "gpu_layers": 0,
            "enabled": True,
        }
    monkeypatch.setattr("src.council_runner.get_role_config", fake_get_role_config)

    # Configure SentryRouter mock to return correct pattern classification
    sentry_mock = MagicMock()
    sentry_mock.classify_request.return_value = {
        "pattern": "SEQUENTIAL_BOARDROOM",
        "complexity": "high",
        "domain": "strategic",
        "is_online": False,
        "available_vram_gb": 48.0,
        "timestamp": "2026-05-29T11:00:00",
    }
    monkeypatch.setattr("src.orchestrator.MemoryFileManager", MagicMock)
    monkeypatch.setattr("src.orchestrator.SentryRouter", lambda *a, **k: sentry_mock)
    monkeypatch.setattr("src.orchestrator.load_dotenv", lambda *a, **k: None)

    # --- 6. Construct Orchestrator and run via process_request with #boardroom prefix.
    orchestrator = Orchestrator(output_router=router)
    result = orchestrator.process_request(
        user_input="#boardroom D3 fixture prompt",
        source_file_path=None,
    )

    # --- 7. Assertions
    # 7a. Return value is a Path. Proves the router branch ran â€” the legacy
    # fallback returns `str` (the raw report).
    assert isinstance(result, Path), f"expected Path, got {type(result).__name__}"

    # 7b. The path is under proposals (router classified #boardroom correctly).
    assert proposals_dir.resolve() in result.resolve().parents, (
        f"expected file under {proposals_dir}, got {result}"
    )

    # 7c. The file actually exists with the scribe content.
    assert result.exists(), f"router said it wrote {result}, but file is missing"
    content = result.read_text(encoding="utf-8")
    assert "#boardroom" in content
    assert "BOARDROOM SYNTHESIS" in content

    # 7d. Negative assertion: AI-Help/cognitive-os/ has no new .md files.
    md_files = list(vault_council_outputs.glob("*.md"))
    assert md_files == [], f"legacy fallback leaked: {md_files}"

    # 7e. LLM mock should have been called exactly 13 times.
    assert shared_mock.generate_response.call_count == 13, (
        f"expected 13 LLM calls total, got {shared_mock.generate_response.call_count}"
    )