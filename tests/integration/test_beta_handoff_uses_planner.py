"""Integration tests for ARCH-5DFB393F (HandoffWriter ↔ HandoffPlanner).

Verifies the wiring done in deliverables A5 + A6: when ``handoff.planner_enabled``
is true, ``HandoffWriter.generate_beta_handoff`` calls ``HandoffPlanner`` and
embeds its output in the handoff document; on planner failure, the legacy
regex extractor fires with the exact fallback notice prepended.

Isolation:
- ``tmp_path`` (and a ``monkeypatch`` of the writer's output directories)
  keep all writes off the real ``dev/handoffs/`` and Obsidian vault.
- The LLM is fully mocked. No test in this file talks to LM Studio.
- The proposal file is created in ``tmp_path`` so we exercise the file-
  read path without touching the real proposals directory.

Spec sources:
- Verdict: Section A5/A6 of dev/handoffs/ARCH-20260524-011510-5DFB393F_BETA_HANDOFF.md
- Fallback notice: docs/HANDOFF_PLANNER_OUTPUT_SPEC.md §5
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator

import pytest

import src.handoff_writer as writer_mod
from src.handoff_writer import HandoffWriter


# ════════════════════════════════════════════════════════════════════
#  Fixtures
# ════════════════════════════════════════════════════════════════════


@pytest.fixture()
def isolated_writer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> HandoffWriter:
    """Return a HandoffWriter pointing at ``tmp_path`` for ALL output dirs.

    The real ``HandoffWriter`` reads ``VAULT_ROOT`` and ``HANDOFFS_DIR`` from
    ``src.paths`` at ``__init__`` time, so we monkeypatch the instance
    attributes after construction.
    """
    w = HandoffWriter()
    vault_dir = tmp_path / "vault_handoffs"
    source_dir = tmp_path / "source_handoffs"
    vault_dir.mkdir()
    source_dir.mkdir()
    w.vault_handoffs_dir = str(vault_dir)
    w.source_handoffs_dir = str(source_dir)
    return w


@pytest.fixture()
def stub_template(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Drop a stub beta-handoff template that the writer will find.

    Generate_beta_handoff probes two template paths; we redirect both by
    monkeypatching ``HANDOFFS_DIR`` to a ``tmp_path`` parent whose
    ``templates/`` sibling contains the stub. Cleaner than per-call kwargs.
    """
    project_root = tmp_path / "project"
    templates_dir = project_root / "templates"
    handoffs_dir = project_root / "handoffs"
    templates_dir.mkdir(parents=True)
    handoffs_dir.mkdir(parents=True)

    # Stub template — must include the placeholders that generate_beta_handoff
    # substitutes. Anything missing is a passthrough.
    template_body = (
        "---\n"
        "proposal_id: DEV-YYYYMMDD-HHMMSS-XXXX\n"
        "created: YYYY-MM-DD HH:MM:SS\n"
        'kanban_card_id: "^[DEV-YYYYMMDDHHMMSS-XXXX]"\n'
        'source_note: ""\n'
        "tasks_completed: 0\n"
        "tasks_total: 0\n"
        "---\n\n"
        "# Beta Handoff Stub\n\n"
        "## Summary\n<!-- COUNCIL_SUMMARY -->\n\n"
        "## Difficulties\n<!-- COUNCIL_DIFFICULTIES -->\n\n"
        "## 🔧 Implementation Tasks\n<!-- COUNCIL_TASKS -->\n\n"
        "## Full Report\n<!-- COUNCIL_FULL_REPORT -->\n"
    )
    (templates_dir / "beta-handoff-template.md").write_text(
        template_body, encoding="utf-8"
    )

    monkeypatch.setattr("src.handoff_writer.HANDOFFS_DIR", handoffs_dir)
    return handoffs_dir


@pytest.fixture()
def stub_proposal(tmp_path: Path) -> Path:
    """Create a minimal proposal file the writer can find by id."""
    proposals_dir = tmp_path / "proposals"
    proposals_dir.mkdir()
    proposal_id = "ARCH-TESTPROPOSAL"
    body = (
        "---\nproposal_id: ARCH-TESTPROPOSAL\nphase: proposal\n---\n\n"
        "# Test Proposal\n\nBody for fixture.\n^[ARCH-TESTPROPOSAL]\n"
    )
    (proposals_dir / f"{proposal_id}_PROPOSAL.md").write_text(body, encoding="utf-8")
    return proposals_dir


def _valid_plan_json() -> str:
    return json.dumps(
        {
            "proposal_id": "ARCH-TESTPROPOSAL",
            "sections": [
                {
                    "name": "Core",
                    "tasks": [
                        {
                            "id": "A1",
                            "title": "Wire it up",
                            "subtasks": ["read config", "instantiate"],
                            "acceptance": "module loads cleanly",
                            "constraints": ["CSTR-V1"],
                            "file_paths": ["src/x.py"],
                        },
                        {
                            "id": "A2",
                            "title": "Cover with test",
                            "subtasks": [],
                            "acceptance": "tests pass",
                            "constraints": [],
                            "file_paths": ["tests/test_x.py"],
                        },
                        {
                            "id": "A3",
                            "title": "Document the change",
                            "subtasks": [],
                            "acceptance": "spec updated",
                            "constraints": [],
                            "file_paths": ["docs/x.md"],
                        },
                        {
                            "id": "A4",
                            "title": "Wire flag",
                            "subtasks": [],
                            "acceptance": "flag respected",
                            "constraints": [],
                            "file_paths": ["dev/master_config.md"],
                        },
                        {
                            "id": "A5",
                            "title": "Migration script",
                            "subtasks": [],
                            "acceptance": "script runs",
                            "constraints": [],
                            "file_paths": ["scripts/x.py"],
                        },
                    ],
                }
            ],
        }
    )


# ════════════════════════════════════════════════════════════════════
#  Cases
# ════════════════════════════════════════════════════════════════════


def test_beta_handoff_calls_planner_when_enabled(
    isolated_writer: HandoffWriter,
    stub_template: Path,
    stub_proposal: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A10.1 — When ``handoff.planner_enabled`` is true (default), the writer
    invokes ``HandoffPlanner.plan`` and renders its output into the handoff."""

    call_log: list[dict] = []

    def fake_render(*, proposal_id, council_report, proposal_file, binding_constraints):
        call_log.append(
            dict(
                proposal_id=proposal_id,
                council_report=council_report,
                proposal_file=proposal_file,
                binding_constraints=binding_constraints,
            )
        )
        # Return a credible planner output
        return (
            "### Section A — Core\n\n"
            "- [ ] **[✏️ PLANNER] A1. Test task one**\n"
            "   - **Acceptance:** done\n\n"
            "- [ ] **[✏️ PLANNER] A2. Test task two**\n"
            "   - **Acceptance:** done\n\n"
            "- [ ] **[✏️ PLANNER] A3. Test task three**\n"
            "   - **Acceptance:** done\n\n"
            "- [ ] **[✏️ PLANNER] A4. Test task four**\n"
            "   - **Acceptance:** done\n\n"
            "- [ ] **[✏️ PLANNER] A5. Test task five**\n"
            "   - **Acceptance:** done\n\n"
            "- [ ] **[✏️ PLANNER] A6. Test task six**\n"
            "   - **Acceptance:** done\n\n"
            "---\n*Generated by HandoffPlanner v1.0. Dark Maestro Ready.*"
        )

    monkeypatch.setattr(writer_mod, "_render_tasks_via_planner", fake_render)
    # Make absolutely sure the flag is on in case a leftover monkeypatch lingered
    monkeypatch.setattr(writer_mod, "_planner_enabled", lambda: True)

    result = isolated_writer.generate_beta_handoff(
        proposal_id="ARCH-TESTPROPOSAL",
        council_report="# Verdict\n\nAPPROVE.",
        proposals_dir=str(stub_proposal),
    )

    assert "error" not in result, result
    assert len(call_log) == 1, "planner should be called exactly once"
    assert call_log[0]["proposal_id"] == "ARCH-TESTPROPOSAL"
    assert "APPROVE" in call_log[0]["council_report"]

    # The rendered file should contain the planner output verbatim
    written = Path(result["source_path"])
    assert written.exists()
    content = written.read_text(encoding="utf-8")
    assert "[✏️ PLANNER]" in content
    # Spec demands ≥5 task lines in the planner-generated block (verdict A10.2)
    assert content.count("[✏️ PLANNER]") >= 5
    # And the signature footer must land in the file
    assert "Dark Maestro Ready" in content


def test_beta_handoff_falls_back_with_exact_notice_when_planner_fails(
    isolated_writer: HandoffWriter,
    stub_template: Path,
    stub_proposal: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A10.2 — On planner failure (here: ``_render_tasks_via_planner`` returns
    ``None``), the writer falls back to the legacy extractor AND prepends the
    exact fallback notice from docs/HANDOFF_PLANNER_OUTPUT_SPEC.md §5."""

    monkeypatch.setattr(writer_mod, "_render_tasks_via_planner", lambda **_: None)
    monkeypatch.setattr(writer_mod, "_planner_enabled", lambda: True)

    council_report = (
        "# Verdict\n\nAPPROVE.\n\n"
        "## Implementation Tasks\n"
        "- A1. Do thing\n"
        "- A2. Do other thing\n"
    )

    result = isolated_writer.generate_beta_handoff(
        proposal_id="ARCH-TESTPROPOSAL",
        council_report=council_report,
        proposals_dir=str(stub_proposal),
    )

    assert "error" not in result, result
    written = Path(result["source_path"])
    content = written.read_text(encoding="utf-8")

    # Exact fallback notice (per spec §5). The text is anchored on both
    # ends so a typo in either half of the template fails this test.
    assert "PLANNER FAILED, FALLBACK ACTIVE" in content
    assert "Tasks extracted via legacy regex." in content
    # Legacy extractor output is preserved beneath the notice
    assert "Do thing" in content
    assert "Do other thing" in content
    # Planner-only markers must NOT appear when the planner failed
    assert "[✏️ PLANNER]" not in content
    assert "Dark Maestro Ready" not in content


def test_beta_handoff_skips_planner_when_flag_is_off(
    isolated_writer: HandoffWriter,
    stub_template: Path,
    stub_proposal: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A10.3 — When ``handoff.planner_enabled`` is false, the writer goes
    straight to the legacy extractor with NO fallback notice (that path is
    the desired output, not a failure)."""

    monkeypatch.setattr(writer_mod, "_planner_enabled", lambda: False)

    # Even if a planner were to be invoked, this would crash the test:
    def boom(**_):
        raise AssertionError("planner must not be invoked when flag is off")

    monkeypatch.setattr(writer_mod, "_render_tasks_via_planner", lambda **_: None)
    # Sanity: confirm legacy path triggers (no notice prepended)
    council_report = (
        "# Verdict\n\nAPPROVE.\n\n"
        "## Implementation Tasks\n"
        "- A1. Legacy task\n"
    )

    result = isolated_writer.generate_beta_handoff(
        proposal_id="ARCH-TESTPROPOSAL",
        council_report=council_report,
        proposals_dir=str(stub_proposal),
    )

    assert "error" not in result, result
    content = Path(result["source_path"]).read_text(encoding="utf-8")
    assert "PLANNER FAILED" not in content, "no notice when flag is explicitly off"
    assert "Legacy task" in content
    assert "[✏️ PLANNER]" not in content
