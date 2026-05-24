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


def _llm_side_effect_factory() -> callable:
    """Return a side_effect that yields valid JSON for calls 1-12 and the
    scribe report on call 13. _extract_json must succeed on every JSON call.
    """
    state = {"n": 0}

    def _side(*args, **kwargs):
        state["n"] += 1
        if state["n"] == 13:
            return SCRIBE_REPORT
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
    # --- 1. Redirect every destination OutputRouter knows about into tmp_path.
    # output_router.py imports these as module-level names, so we patch the
    # names on `src.output_router` (the binding the test code sees), NOT on
    # `src.paths` (which only affects future-imported modules).
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

    # --- 2. Redirect AI-Help so the legacy-fallback negative assertion is
    # verifiable against tmp_path instead of the developer's real vault.
    vault_ai_help = tmp_path / "AI-Help"
    vault_council_outputs = vault_ai_help / "cognitive-os"
    vault_council_outputs.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("src.paths.VAULT_AI_HELP", vault_ai_help)
    monkeypatch.setattr("src.paths.VAULT_COUNCIL_OUTPUTS", vault_council_outputs)

    # --- 3. Redirect ApprovalLogger defaults so anything that incidentally
    # constructs it (e.g. through orchestrator imports) does not touch the
    # real dev/decisions/index.sqlite.
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

    # --- 5. Patch the LM Studio / orchestrator-internal symbols. We patch them
    # on `src.orchestrator` (where they're imported), not on their original
    # modules, so the orchestrator's local bindings change.
    mock_llm = MagicMock()
    mock_llm.generate_response.side_effect = _llm_side_effect_factory()
    monkeypatch.setattr("src.orchestrator.llm", mock_llm)
    monkeypatch.setattr(
        "src.orchestrator.get_role_config",
        lambda *_a, **_kw: {
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
    monkeypatch.setattr("src.orchestrator.MemoryFileManager", MagicMock)
    monkeypatch.setattr("src.orchestrator.SentryRouter", MagicMock)
    monkeypatch.setattr("src.orchestrator.load_dotenv", lambda *a, **k: None)

    # --- 6. Construct Orchestrator and run the boardroom.
    orchestrator = Orchestrator(output_router=router)
    result = orchestrator.execute_sequential_boardroom(
        user_input="D3 fixture prompt",
        source_file_path=None,
    )

    # --- 7. Assertions
    # 7a. Return value is a Path. Proves the router branch ran â€” the legacy
    # fallback returns `str` (the raw report).
    assert isinstance(result, Path), f"expected Path, got {type(result).__name__}"

    # 7b. The path is under proposals (router classified #boardroom correctly).
    # `result` may have been resolved by FilesystemBackendWriter; compare via
    # the resolved tmp_path/dev/proposals dir.
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

    # 7e. llm.generate_response invoked exactly 13 times:
    # 1 moderator + 5 board roles Ã— (1 agent + 1 brand_guard) + 1 chairman + 1 scribe.
    assert mock_llm.generate_response.call_count == 13, (
        f"expected 13 LLM calls, got {mock_llm.generate_response.call_count}"
    )
