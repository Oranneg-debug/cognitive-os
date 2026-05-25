"""Smoke test for A4 (HandoffPlanner). Not part of the test suite —
just a quick sanity check during development. Delete after A9 is
written if you like."""

from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path

import src.handoff_planner as hp_mod
from src.handoff_planner import (
    HandoffPlanner,
    PlannerTimeout,
    PlannerValidationFailed,
    _peel_outer_fence,
)
from src.models.handoff_plan import HandoffPlan


class FakeLLM:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def generate_response(self, **kw):
        self.calls.append(kw)
        return self.responses.pop(0)


class SlowLLM:
    def __init__(self, delay, response):
        self.delay = delay
        self.response = response

    def generate_response(self, **kw):
        time.sleep(self.delay)
        return self.response


def fake_role(key):
    assert key == "handoff_planner"
    return {
        "model": "fake",
        "temperature": 0.3,
        "top_p": 0.9,
        "top_k": 40,
        "min_p": 0.1,
        "max_tokens": 4096,
        "context_window": 8192,
        "gpu_layers": -1,
    }


def main() -> int:
    valid_json = json.dumps({
        "proposal_id": "ARCH-X",
        "sections": [
            {
                "name": "Core",
                "tasks": [{
                    "id": "A1",
                    "title": "do thing",
                    "acceptance": "done",
                    "subtasks": ["s1", "s2"],
                    "constraints": ["CSTR-V1"],
                    "file_paths": ["src/x.py"],
                }],
            }
        ],
    })

    # Case 1 — happy
    p1 = HandoffPlanner(llm_client=FakeLLM([valid_json]), role_config_loader=fake_role)
    plan1 = p1.plan("ARCH-X", "body", "verdict", ["CSTR-V1"])
    assert isinstance(plan1, HandoffPlan), "case 1: plan type"
    assert plan1.sections[0].tasks[0].id == "A1"
    print("OK case 1 — happy path")

    # Case 2 — outer fence peel
    fenced = "```json\n" + valid_json + "\n```"
    assert _peel_outer_fence(fenced) == valid_json, "fence peel"
    p2 = HandoffPlanner(llm_client=FakeLLM([fenced]), role_config_loader=fake_role)
    plan2 = p2.plan("ARCH-X", "body", "verdict", [])
    assert plan2.sections[0].tasks[0].id == "A1"
    print("OK case 2 — outer-fence peel")

    # Case 3 — retry success
    p3 = HandoffPlanner(llm_client=FakeLLM(["{ not json", valid_json]), role_config_loader=fake_role)
    plan3 = p3.plan("ARCH-X", "body", "verdict", [])
    assert plan3.sections[0].tasks[0].id == "A1"
    print("OK case 3 — retry recovers")

    # Case 4 — dead-letter
    with tempfile.TemporaryDirectory() as td:
        p4 = HandoffPlanner(
            llm_client=FakeLLM(["bad1", "bad2 also bad"]),
            role_config_loader=fake_role,
            dead_letter_dir=Path(td),
        )
        try:
            p4.plan("ARCH-X", "body", "verdict", [])
            print("FAIL case 4 — expected PlannerValidationFailed")
            return 1
        except PlannerValidationFailed as e:
            assert e.dead_letter_path.exists()
            assert e.dead_letter_path.stat().st_size > 100
            content = e.dead_letter_path.read_text(encoding="utf-8")
            assert "First (rejected)" in content
            assert "Retry (also rejected)" in content
            print(f"OK case 4 — dead-letter at {e.dead_letter_path.name}")

    # Case 5 — timeout
    original_timeout = hp_mod.LLM_TIMEOUT_SECONDS
    hp_mod.LLM_TIMEOUT_SECONDS = 0.5
    try:
        p5 = HandoffPlanner(
            llm_client=SlowLLM(delay=2.0, response=valid_json),
            role_config_loader=fake_role,
        )
        try:
            p5.plan("ARCH-X", "body", "verdict", [])
            print("FAIL case 5 — expected PlannerTimeout")
            return 1
        except PlannerTimeout:
            print("OK case 5 — timeout fires")
    finally:
        hp_mod.LLM_TIMEOUT_SECONDS = original_timeout

    # Case 6 — markdown render
    print("--- to_markdown sample ---")
    print(plan1.to_markdown())
    print("--- end sample ---")

    print("\nAll A4 smoke cases pass.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
