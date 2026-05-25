"""
One-shot script: submit ARCH-20260524-011510-5DFB393F (HandoffPlanner, Section A-E)
to the sequential boardroom via the /process API endpoint.

Usage:
    python scripts/submit_planner_to_boardroom.py

Writes the API response to scripts/.boardroom_verdict_5DFB393F.json for inspection.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
PROPOSAL = ROOT / "dev" / "proposals" / "ARCH-20260524-011510-5DFB393F_PROPOSAL.md"
OUT = Path(__file__).resolve().parent / ".boardroom_verdict_5DFB393F.json"

API_URL = "http://127.0.0.1:5000/process"


def main() -> int:
    if not PROPOSAL.exists():
        print(f"ERROR: proposal not found: {PROPOSAL}", file=sys.stderr)
        return 2

    proposal_text = PROPOSAL.read_text(encoding="utf-8")

    prompt = (
        "#boardroom\n"
        "\n"
        "You are reviewing an ARCH proposal for boardroom verdict. Section F has\n"
        "been deferred (see proposal). Review **only Section A-E (deliverables 1-11)**\n"
        "and the binding constraints CSTR-PLANNER-V1 through V6.\n"
        "\n"
        "## Decision required\n"
        "1. APPROVE / APPROVE-WITH-AMENDMENTS / REJECT\n"
        "2. If amendments: list them concretely so the coder can act.\n"
        "3. Confirm `ministral-3-3b-instruct-2512` is the right planner model\n"
        "   (or recommend a swap, e.g. `qwen3-vl-4b-thinking`).\n"
        "4. Identify the single biggest risk and how to mitigate it within scope.\n"
        "5. List the implementation tasks the coder should tick off (deliverables 1-11).\n"
        "   Tasks must include: file paths, acceptance criteria, binding-constraint refs.\n"
        "   This task list will land in the editor's `## 🔧 Implementation Tasks` section.\n"
        "\n"
        "## Proposal under review (verbatim)\n"
        "\n"
        f"{proposal_text}\n"
    )

    payload = {
        "prompt": prompt,
        "source_file_path": str(PROPOSAL),
    }

    print(f"Submitting to boardroom: {API_URL}")
    print(f"  proposal: {PROPOSAL.relative_to(ROOT)}")
    print(f"  prompt size: {len(prompt):,} chars")
    print()

    t0 = time.time()
    try:
        r = requests.post(API_URL, json=payload, timeout=2400)  # 40 min hard cap
    except requests.exceptions.RequestException as exc:
        print(f"ERROR: request failed: {exc}", file=sys.stderr)
        return 3
    elapsed = time.time() - t0

    print(f"HTTP {r.status_code} in {elapsed:.1f}s")
    try:
        body = r.json()
    except Exception:
        print("ERROR: non-JSON response", file=sys.stderr)
        print(r.text[:2000])
        return 4

    OUT.write_text(json.dumps(body, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote: {OUT.relative_to(ROOT)}")
    print()

    status = body.get("status")
    print(f"status: {status}")
    if status != "success":
        print("ERROR: boardroom did not return success", file=sys.stderr)
        print(json.dumps(body, indent=2)[:4000])
        return 5

    decision = body.get("routing_decision", {})
    print(f"routing_decision.rule_name: {decision.get('rule_name')}")
    print(f"routing_decision.destination: {decision.get('destination')}")
    print(f"saved_path: {body.get('saved_path')}")
    print(f"task_id: {body.get('task_id')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
