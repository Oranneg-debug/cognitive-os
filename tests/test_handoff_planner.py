"""Unit tests for ARCH-5DFB393F (HandoffPlanner) — Section A4 + A9.

Covers the planner module and the HandoffPlan / PlanTask / PlanSection
Pydantic models. ≥12 cases per the boardroom verdict (Specialist A1,
Creative CREATIVE-A1..A5).

Isolation: every test that touches the dead-letter directory uses
``tmp_path`` so the real ``dev/failed_routings/`` is never polluted.
LLM calls are always mocked — no test in this file hits LM Studio.
"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

import src.handoff_planner as planner_mod
from src.handoff_planner import (
    HandoffPlanner,
    PlannerError,
    PlannerTimeout,
    PlannerValidationFailed,
    _peel_outer_fence,
)
from src.models.handoff_plan import (
    PLANNER_SIGNATURE,
    PLANNER_TASK_PREFIX,
    HandoffPlan,
    PlanSection,
    PlanTask,
)


# ════════════════════════════════════════════════════════════════════
#  Fakes
# ════════════════════════════════════════════════════════════════════


class FakeLLM:
    """Replays a queue of canned responses. Records each call's kwargs."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls: list[dict] = []

    def generate_response(self, **kwargs) -> str:
        self.calls.append(kwargs)
        if not self._responses:
            raise RuntimeError("FakeLLM exhausted")
        return self._responses.pop(0)


class SlowLLM:
    """Sleeps before returning; lets us exercise the timeout path."""

    def __init__(self, delay: float, response: str):
        self.delay = delay
        self.response = response

    def generate_response(self, **kwargs) -> str:
        time.sleep(self.delay)
        return self.response


def _fake_role_loader(key: str) -> dict:
    assert key == "handoff_planner", f"unexpected role lookup: {key!r}"
    return {
        "model": "fake-model",
        "temperature": 0.3,
        "top_p": 0.9,
        "top_k": 40,
        "min_p": 0.1,
        "max_tokens": 4096,
        "context_window": 8192,
        "gpu_layers": -1,
    }


def _valid_plan_json(proposal_id: str = "ARCH-TEST-001") -> str:
    return json.dumps(
        {
            "proposal_id": proposal_id,
            "sections": [
                {
                    "name": "Core",
                    "tasks": [
                        {
                            "id": "A1",
                            "title": "Do the thing",
                            "subtasks": ["step 1", "step 2"],
                            "acceptance": "the thing is done",
                            "constraints": ["CSTR-V1"],
                            "file_paths": ["src/x.py"],
                        },
                        {
                            "id": "A2",
                            "title": "Cover with test",
                            "subtasks": [],
                            "acceptance": "tests/test_x.py passes",
                            "constraints": ["CSTR-V4"],
                            "file_paths": ["tests/test_x.py"],
                        },
                    ],
                }
            ],
        }
    )


# ════════════════════════════════════════════════════════════════════
#  HandoffPlan / PlanTask / PlanSection — schema tests
# ════════════════════════════════════════════════════════════════════


def test_plan_task_happy_path():
    """A1 (model). Minimal valid task constructs cleanly."""
    t = PlanTask(id="A1", title="x", acceptance="y")
    assert t.id == "A1"
    assert t.subtasks == []
    assert t.constraints == []
    assert t.file_paths == []


@pytest.mark.parametrize("bad_id", ["a1", "A", "1A", "AA1", "A1B", ""])
def test_plan_task_rejects_malformed_id(bad_id):
    """A2 (model). Task ids must match ``^[A-Z]\\d+$``."""
    with pytest.raises(ValidationError):
        PlanTask(id=bad_id, title="x", acceptance="y")


def test_plan_task_rejects_multiline_title_and_acceptance():
    """A3 (model). title and acceptance must be single-line."""
    with pytest.raises(ValidationError):
        PlanTask(id="A1", title="line1\nline2", acceptance="y")
    with pytest.raises(ValidationError):
        PlanTask(id="A1", title="x", acceptance="line1\nline2")


def test_plan_task_rejects_empty_acceptance():
    """A4 (model). acceptance is mandatory and must be non-empty."""
    with pytest.raises(ValidationError):
        PlanTask(id="A1", title="x", acceptance="")


def test_handoff_plan_rejects_empty_sections():
    """A5 (model). A plan with no sections is nonsensical."""
    with pytest.raises(ValidationError):
        HandoffPlan(proposal_id="X", sections=[])


def test_handoff_plan_rejects_duplicate_task_ids():
    """A6 (model). Cross-section task-id uniqueness is enforced."""
    s1 = PlanSection(
        name="One",
        tasks=[PlanTask(id="A1", title="x", acceptance="y")],
    )
    s2 = PlanSection(
        name="Two",
        tasks=[PlanTask(id="A1", title="z", acceptance="w")],
    )
    with pytest.raises(ValidationError) as exc_info:
        HandoffPlan(proposal_id="X", sections=[s1, s2])
    assert "Duplicate task id 'A1'" in str(exc_info.value)


# ════════════════════════════════════════════════════════════════════
#  to_markdown rendering — A3 spec compliance
# ════════════════════════════════════════════════════════════════════


def test_to_markdown_contains_planner_prefix_on_every_task():
    """A7 (render). CREATIVE-A2: every task must carry ``[✏️ PLANNER]``."""
    plan = HandoffPlan(
        proposal_id="ARCH-X",
        sections=[
            PlanSection(
                name="Core",
                tasks=[
                    PlanTask(id="A1", title="one", acceptance="ok"),
                    PlanTask(id="A2", title="two", acceptance="ok"),
                ],
            )
        ],
    )
    rendered = plan.to_markdown()
    # Two tasks → two prefix occurrences
    assert rendered.count(PLANNER_TASK_PREFIX) == 2
    assert "- [ ] **[✏️ PLANNER] A1. one**" in rendered
    assert "- [ ] **[✏️ PLANNER] A2. two**" in rendered


def test_to_markdown_appends_signature_footer():
    """A8 (render). CREATIVE-A4: signature footer at end."""
    plan = HandoffPlan(
        proposal_id="ARCH-X",
        sections=[
            PlanSection(
                name="Core",
                tasks=[PlanTask(id="A1", title="x", acceptance="y")],
            )
        ],
    )
    rendered = plan.to_markdown()
    assert rendered.endswith(PLANNER_SIGNATURE)
    assert "Dark Maestro Ready" in rendered


def test_to_markdown_section_letters_are_alphabetical_independent_of_name():
    """A9 (render). Section letter comes from index, not from name."""
    plan = HandoffPlan(
        proposal_id="ARCH-X",
        sections=[
            PlanSection(name="Zebra", tasks=[PlanTask(id="A1", title="a", acceptance="a")]),
            PlanSection(name="Antelope", tasks=[PlanTask(id="B1", title="b", acceptance="b")]),
            PlanSection(name="Crocodile", tasks=[PlanTask(id="C1", title="c", acceptance="c")]),
        ],
    )
    rendered = plan.to_markdown()
    assert "### Section A — Zebra" in rendered
    assert "### Section B — Antelope" in rendered
    assert "### Section C — Crocodile" in rendered


def test_to_markdown_is_deterministic():
    """A10 (render). CSTR-PLANNER-V5: same plan → byte-identical output."""
    spec = dict(
        proposal_id="ARCH-X",
        sections=[
            PlanSection(
                name="S",
                tasks=[
                    PlanTask(
                        id="A1",
                        title="t",
                        acceptance="ok",
                        subtasks=["a", "b"],
                        constraints=["C1", "C2"],
                        file_paths=["p1.py", "p2.py"],
                    )
                ],
            )
        ],
    )
    # Construct twice; the only non-deterministic field is generated_at, but
    # to_markdown does not render it.
    plan1 = HandoffPlan(**spec)
    plan2 = HandoffPlan(**spec)
    assert plan1.to_markdown() == plan2.to_markdown()


def test_to_markdown_omits_empty_constraints_and_files_lines():
    """A11 (render). Sparse fields are not rendered as empty lines."""
    plan = HandoffPlan(
        proposal_id="ARCH-X",
        sections=[
            PlanSection(
                name="S",
                tasks=[
                    PlanTask(id="A1", title="t", acceptance="ok"),  # no constraints/files
                ],
            )
        ],
    )
    rendered = plan.to_markdown()
    assert "**Constraints:**" not in rendered
    assert "**Files:**" not in rendered
    # But Acceptance is mandatory
    assert "**Acceptance:** ok" in rendered


# ════════════════════════════════════════════════════════════════════
#  HandoffPlanner — pipeline tests with fake LLM
# ════════════════════════════════════════════════════════════════════


def test_planner_happy_path_returns_validated_handoff_plan():
    """A12 (planner). LLM returns valid JSON → planner returns HandoffPlan."""
    p = HandoffPlanner(
        llm_client=FakeLLM([_valid_plan_json()]),
        role_config_loader=_fake_role_loader,
    )
    result = p.plan(
        proposal_id="ARCH-TEST-001",
        proposal_body="proposal body",
        council_report="verdict text",
        binding_constraints=["CSTR-V1"],
    )
    assert isinstance(result, HandoffPlan)
    assert result.proposal_id == "ARCH-TEST-001"
    assert len(result.sections) == 1
    assert len(result.sections[0].tasks) == 2


def test_planner_strips_fences_before_llm_sees_text():
    """A13 (planner). CSTR-PLANNER-V3: fences stripped before the LLM call."""
    llm = FakeLLM([_valid_plan_json()])
    p = HandoffPlanner(llm_client=llm, role_config_loader=_fake_role_loader)
    fenced_verdict = (
        "Some prose.\n"
        "```markdown\n"
        "## Important Section\n"
        "Inside the fence — this should be stripped.\n"
        "```\n"
        "More prose after."
    )
    p.plan("ARCH-X", "body", fenced_verdict, [])
    # The LLM saw the user prompt; assert the fenced content was stripped
    user_prompt = llm.calls[0]["prompt"]
    assert "Inside the fence" not in user_prompt
    assert "More prose after" in user_prompt
    assert "Some prose." in user_prompt


def test_planner_peels_outer_fence_around_response():
    """A14 (planner). Defensive: LLM wraps its JSON in ```json … ``` even though forbidden."""
    wrapped = "```json\n" + _valid_plan_json() + "\n```"
    p = HandoffPlanner(
        llm_client=FakeLLM([wrapped]),
        role_config_loader=_fake_role_loader,
    )
    plan = p.plan("ARCH-X", "body", "verdict", [])
    assert plan.sections[0].tasks[0].id == "A1"


def test_planner_retries_once_on_validation_failure():
    """A15 (planner). Invalid JSON → retry → valid → returns the second."""
    llm = FakeLLM(["{ not json at all", _valid_plan_json()])
    p = HandoffPlanner(llm_client=llm, role_config_loader=_fake_role_loader)
    plan = p.plan("ARCH-X", "body", "verdict", [])
    assert isinstance(plan, HandoffPlan)
    assert len(llm.calls) == 2
    # The retry prompt must include the validator error so the LLM learns
    retry_prompt = llm.calls[1]["prompt"]
    assert "FAILED VALIDATION" in retry_prompt
    assert "{ not json at all" in retry_prompt


def test_planner_dead_letters_on_double_failure(tmp_path):
    """A16 (planner). Two consecutive invalid responses → dead-letter + raise."""
    p = HandoffPlanner(
        llm_client=FakeLLM(["bad first", "still bad"]),
        role_config_loader=_fake_role_loader,
        dead_letter_dir=tmp_path,
    )
    with pytest.raises(PlannerValidationFailed) as exc_info:
        p.plan("ARCH-X", "body", "verdict", [])

    dead_letter = exc_info.value.dead_letter_path
    assert dead_letter.exists()
    assert dead_letter.parent == tmp_path  # isolation: real dir untouched
    content = dead_letter.read_text(encoding="utf-8")
    assert "## First (rejected)" in content
    assert "bad first" in content
    assert "## Retry (also rejected)" in content
    assert "still bad" in content


def test_planner_dead_letter_does_not_pollute_real_failed_routings(tmp_path):
    """A17 (planner). Regression guard: dead-letter MUST honour the tmp_path
    override, not write to the production dev/failed_routings."""
    from src.paths import DEV_DIR

    real_dead_letter_dir = DEV_DIR / "failed_routings"
    # Snapshot the real directory's file count before we run anything.
    real_before: set[str] = set()
    if real_dead_letter_dir.exists():
        real_before = {p.name for p in real_dead_letter_dir.iterdir()}

    p = HandoffPlanner(
        llm_client=FakeLLM(["bad", "still bad"]),
        role_config_loader=_fake_role_loader,
        dead_letter_dir=tmp_path,
    )
    with pytest.raises(PlannerValidationFailed):
        p.plan("ARCH-X", "body", "verdict", [])

    real_after: set[str] = set()
    if real_dead_letter_dir.exists():
        real_after = {p.name for p in real_dead_letter_dir.iterdir()}

    assert real_after == real_before, (
        "Real dev/failed_routings/ must NOT receive dead-letters from tmp_path-isolated test"
    )


def test_planner_timeout_raises_planner_timeout(monkeypatch):
    """A18 (planner). LLM call exceeding LLM_TIMEOUT_SECONDS → PlannerTimeout."""
    monkeypatch.setattr(planner_mod, "LLM_TIMEOUT_SECONDS", 0.4)
    slow = SlowLLM(delay=1.5, response=_valid_plan_json())
    p = HandoffPlanner(llm_client=slow, role_config_loader=_fake_role_loader)
    with pytest.raises(PlannerTimeout):
        p.plan("ARCH-X", "body", "verdict", [])


def test_planner_injects_proposal_id_when_llm_omits_it():
    """A19 (planner). Be forgiving: if the LLM forgot the proposal_id,
    inject ours rather than failing validation."""
    response_without_id = json.dumps(
        {
            "sections": [
                {
                    "name": "S",
                    "tasks": [
                        {
                            "id": "A1",
                            "title": "x",
                            "acceptance": "y",
                            "subtasks": [],
                            "constraints": [],
                            "file_paths": [],
                        }
                    ],
                }
            ]
        }
    )
    p = HandoffPlanner(
        llm_client=FakeLLM([response_without_id]),
        role_config_loader=_fake_role_loader,
    )
    plan = p.plan("ARCH-INJECTED", "body", "verdict", [])
    assert plan.proposal_id == "ARCH-INJECTED"


def test_planner_does_not_override_proposal_id_when_llm_provides_it():
    """A20 (planner). Don't silently mask LLM errors — if the LLM emits
    a different proposal_id, surface it (let it pass to validation)."""
    response = json.dumps(
        {
            "proposal_id": "ARCH-FROM-LLM",
            "sections": [
                {
                    "name": "S",
                    "tasks": [{"id": "A1", "title": "x", "acceptance": "y",
                               "subtasks": [], "constraints": [], "file_paths": []}],
                }
            ],
        }
    )
    p = HandoffPlanner(
        llm_client=FakeLLM([response]),
        role_config_loader=_fake_role_loader,
    )
    plan = p.plan("ARCH-CALLER", "body", "verdict", [])
    # The LLM's value wins; this is the right behaviour because silently
    # overriding would mask LLM mistakes.
    assert plan.proposal_id == "ARCH-FROM-LLM"


def test_planner_end_to_end_with_fixture_council_report():
    """A21 (planner, fixture). End-to-end happy path with a council-shaped
    verdict — exercises the prompt-building plumbing with realistic input."""
    fixture_verdict = (
        "# Definitive Verdict\n\n"
        "APPROVE-WITH-AMENDMENTS. Implement A1-A3 with file paths in backticks "
        "and CSTR-X-V2 binding-constraint references.\n\n"
        "## Implementation Tasks\n"
        "- A1. Add new role config\n"
        "- A2. Implement module\n"
        "- A3. Test it\n"
    )
    llm = FakeLLM([_valid_plan_json("ARCH-FIXTURE")])
    p = HandoffPlanner(llm_client=llm, role_config_loader=_fake_role_loader)
    plan = p.plan("ARCH-FIXTURE", "proposal body here", fixture_verdict, ["CSTR-X-V2"])
    assert plan.proposal_id == "ARCH-FIXTURE"
    # User prompt must contain all four inputs
    user_prompt = llm.calls[0]["prompt"]
    assert "ARCH-FIXTURE" in user_prompt
    assert "proposal body here" in user_prompt
    assert "APPROVE-WITH-AMENDMENTS" in user_prompt
    assert "CSTR-X-V2" in user_prompt


# ════════════════════════════════════════════════════════════════════
#  System-prompt invariants (CREATIVE-A1, Specialist A1)
# ════════════════════════════════════════════════════════════════════


def test_system_prompt_contains_required_examples():
    """A22 (prompt). Two worked JSON examples must be embedded in the prompt
    (Specialist A1: "2–3 minimal examples")."""
    prompt = planner_mod._PLANNER_SYSTEM_PROMPT
    assert "EXAMPLE 1" in prompt
    assert "EXAMPLE 2" in prompt


def test_system_prompt_forbids_prose_and_fences():
    """A23 (prompt). The prompt explicitly tells the LLM not to wrap output
    in fences or surround with prose."""
    prompt = planner_mod._PLANNER_SYSTEM_PROMPT
    assert re.search(r"no\s+(?:prose|fences)", prompt, re.IGNORECASE)
    assert "ONLY" in prompt  # "Return ONLY the JSON"
