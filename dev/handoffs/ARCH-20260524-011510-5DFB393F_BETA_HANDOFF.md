---
proposal_id: ARCH-20260524-011510-5DFB393F
phase: beta
status: in_progress
created: 2026-05-25
last_updated: 2026-05-25
handoff_type: beta_testing
related_proposal: "[[ARCH-20260524-011510-5DFB393F_PROPOSAL]]"
kanban_card_id: "ARCH-202605240115105DFB393F"
source_note: ""
next_phase: Alpha Polish
tasks_completed: 0
tasks_total: 11
tasks_logical_total: 11
vault_kanban: "1. P - Seedlings/Dev-KanBan.md"
council_task_id: task_20260525_125253_9afe2aaf
council_verdict: APPROVE-WITH-AMENDMENTS
sections:
  - A — handoff_planner role config
  - B — HandoffPlanner module + Pydantic models
  - C — Wire planner into handoff_writer
  - D — Tests (unit + integration)
  - E — Feature flag + replan script
note_on_scribe: |
  The scribe role (ministral-3-3b-instruct-2512) hit a Channel Error
  at the end of this boardroom run (2026-05-25 13:20:25). The scribe-
  generated master report was lost. This handoff is the canonical
  artefact synthesised by hand from the archived per-role opinions at
  council_memory/archived/2026-05/task_20260525_125253_9afe2aaf.json
  and the Chairman verdict at scripts/.boardroom_verdict_chairman.txt.
---

# 🧪 Beta Testing Handoff — ARCH-20260524-011510-5DFB393F (HandoffPlanner)

> **Generated**: 2026-05-25 (manual reconstruction; scribe channel-errored)
> **Proposal**: [[ARCH-20260524-011510-5DFB393F_PROPOSAL]]
> **Phase**: Beta Testing
> **Status**: 🔧 In Progress — take this document to VS Code

---

## 🤖 Agent Context

> *This block is for AI coding agents working in VS Code (Cline / Claude / Copilot).*

When a user references this handoff (e.g. *"work on ARCH-5DFB393F"*):

1. **Read the proposal** → [dev/proposals/ARCH-20260524-011510-5DFB393F_PROPOSAL.md](../proposals/ARCH-20260524-011510-5DFB393F_PROPOSAL.md)
2. **Read this handoff in full** — both the council amendments and the task list below
3. **Work through `## 🔧 Implementation Tasks`**, ticking each `- [ ]` to `- [x]` as completed
4. **When all tasks are ticked** → update this file's frontmatter: `status: complete`, `tasks_completed: 11`
5. **Update the proposal** → change phase to `alpha_polish`
6. **Update the Kanban card** at `vault_kanban` → drag from `Beta Testing` to `Alpha Polish`

**Scope reminder:** Section F of the proposal (Coder Profile Registry, deliverables 12–17) is **deferred** to a follow-on ARCH-CODER-PROFILE-REGISTRY proposal. Do NOT implement Section F here. The planner uses a hard-coded `_PLANNER_SYSTEM_PROMPT` module constant.

---

## 📋 Executive Summary

**Verdict: APPROVE-WITH-AMENDMENTS.** All five board roles (Strategist, Specialist, Critic, Creative, Logical) plus the Chairman (Hermes-4-70B) converged on approving Section A–E with two clusters of amendments:

- **Technical amendments (Specialist):** prompt precision, 60s timeout, deterministic ordering, exact fallback notice, structural-equivalence idempotency test.
- **Aesthetic amendments (Creative):** `[✏️ PLANNER]` task prefix, subtask visual distinction, signature footer, evocative task titles, Dark-Maestro styling embedded in the system prompt.

**Model choice confirmed:** `ministral-3-3b-instruct-2512` (already loaded; fast; deterministic at temp 0.3). Document a swap-trigger to `qwen3-vl-4b-thinking` in `docs/HANDOFF_PLANNER_OUTPUT_SPEC.md` if validation success-rate falls below 90% or fallback usage exceeds 5%.

**Biggest risk:** the planner emitting markdown that's structurally valid but stylistically inconsistent — leading to manual rework and brand drift. Mitigation: example-driven system prompt + Pydantic schema + one retry with validator error injection + monitoring hooks.

---

## ⚠️ Difficulties & Constraints

**CSTR-PLANNER-V1 — No new dependencies.** Stdlib + already-installed (Pydantic, ruamel.yaml). No langchain, no pydantic-ai, no template engines.

**CSTR-PLANNER-V2 — Planner failure NEVER blocks the handoff.** Timeout, error, or twice-invalid output → fallback to legacy regex extractor with explicit notice. Exact notice text (per Specialist A4):

```
PLANNER FAILED, FALLBACK ACTIVE: [short reason]. Tasks extracted via legacy regex.
```

**CSTR-PLANNER-V3 — Strip fences before the planner sees text.** Use `src.markdown_fence_parser.strip_fences()` (Phase 2, production).

**CSTR-PLANNER-V4 — Planner output is Pydantic-validated.** Match the Phase 1 / Phase 2 schema-first fail-fast pattern.

**CSTR-PLANNER-V5 — Idempotent.** Running the planner twice on the same verdict produces equivalent plans. Tests assert structural equivalence (normalized task sets), not raw-string equality.

**CSTR-PLANNER-V6 — Schema-stable output.** Sections → tasks → acceptance → constraint refs → file paths. Fixed structure, Pydantic-enforced. System prompt is a module constant; profile-adaptive prompts deferred to follow-on proposal.

---

## 🧱 Reading order for the implementing agent

1. `dev/proposals/ARCH-20260524-011510-5DFB393F_PROPOSAL.md` — the full proposal text
2. `docs/HANDOFF_PLANNER_OUTPUT_SPEC.md` (to be created in this handoff, deliverable A7) — once written, becomes the SSOT for output shape
3. `src/markdown_fence_parser.py` — already in production; use `strip_fences()`
4. `src/routing_rules_schema.py` — Pydantic + fail-fast pattern to mirror
5. `src/handoff_writer.py` — current regex extractor lives here; you'll modify `generate_beta_handoff` + `generate_alpha_handoff`
6. `src/orchestrator.py` — `execute_sequential_boardroom` + `execute_technical_meeting` return-type change
7. `dev/master_config.md` — add `handoff_planner` role + `handoff.planner_enabled` flag

---

## 🔧 Implementation Tasks

> Tick each `- [ ]` to `- [x]` as the work lands. Commit after each numbered task (A1–A11). Do not bundle.

### Section A — Role config

- [ ] **A1. Add `handoff_planner` role to master_config**
   - [ ] File: [dev/master_config.md](../master_config.md)
   - [ ] Add `roles.handoff_planner` under the existing `roles:` block with:
     - `model: ministral-3-3b-instruct-2512`
     - `compass_weight: IGNORE`
     - `context_window: 131072`
     - `temperature: 0.3`
     - `top_p: 0.9`, `top_k: 40`, `min_p: 0.1`
     - `max_tokens: 8192`
     - `gpu_layers: -1`
     - `n_parallel: 1`
     - `system_prompt: "<reference _PLANNER_SYSTEM_PROMPT in src/handoff_planner.py>"` — the actual prompt body is a module constant; this field can be a one-line marker that `get_role_config('handoff_planner')` consumers ignore
   - [ ] **Acceptance:** `get_role_config("handoff_planner")` returns a dict with the above keys; existing role loaders pass; `python -c "from src.config_loader import get_config; print(get_config()['roles']['handoff_planner']['model'])"` prints the model id
   - [ ] **Constraints:** CSTR-PLANNER-V1, CSTR-PLANNER-V6
   - [ ] **Files:** `dev/master_config.md`

### Section B — HandoffPlanner module + Pydantic models

- [ ] **A2. Implement Pydantic models for the plan structure**
   - [ ] File: `src/models/handoff_plan.py` (new; ~100 LOC)
   - [ ] Define three Pydantic models:
     - `PlanTask` — fields: `id: str` (e.g. "A1"), `title: str`, `subtasks: list[str]`, `acceptance: str`, `constraints: list[str]`, `file_paths: list[str]`
     - `PlanSection` — fields: `name: str`, `tasks: list[PlanTask]`
     - `HandoffPlan` — fields: `sections: list[PlanSection]`, `proposal_id: str`, `generated_at: datetime`
   - [ ] Validators: `tasks` and `sections` must be non-empty; `acceptance` must be non-empty per task; `id` must match `^[A-Z]\d+$` pattern
   - [ ] **Acceptance:** importing the module produces no side effects; `HandoffPlan(sections=[], ...)` raises ValidationError; valid plan round-trips through `.model_dump()` / `.model_validate()`
   - [ ] **Constraints:** CSTR-PLANNER-V1, CSTR-PLANNER-V4, CSTR-PLANNER-V6
   - [ ] **Files:** `src/models/handoff_plan.py` (new), `src/models/__init__.py` (touch if `models/` is new)

- [ ] **A3. Implement `HandoffPlan.to_markdown()` (Dark-Maestro styling)**
   - [ ] File: `src/models/handoff_plan.py` (extends A2)
   - [ ] Render each section as `### Section A — <name>` (em-dash separator)
   - [ ] Render each task as: `- [ ] **[✏️ PLANNER] A1. <title>**` (the `[✏️ PLANNER]` prefix is mandatory — Creative amendment CREATIVE-A2)
   - [ ] Render each subtask as `   - [ ] <step>` (3-space indent, hyphen bullet — Creative amendment CREATIVE-A3)
   - [ ] Render acceptance as `   - **Acceptance:** <criterion>` (single line; mandatory per Specialist A1)
   - [ ] Render constraints as `   - **Constraints:** <comma-joined refs>` (e.g. `H3, CSTR-X-V2`)
   - [ ] Render file paths as `   - **Files:** <comma-joined paths>` (each path in backticks)
   - [ ] Append signature footer at the very end of the `## 🔧 Implementation Tasks` block: `\n\n---\n*Generated by HandoffPlanner v1.0. Dark Maestro Ready.*` (Creative amendment CREATIVE-A4)
   - [ ] Output is **deterministic**: sections in input order, tasks in input order, subtasks in input order (Specialist amendment A3)
   - [ ] **Acceptance:** `to_markdown()` output matches the exact shape documented in A7; round-trip test (parse rendered markdown back to a `HandoffPlan` via a small `parse_markdown` helper) yields structurally equivalent objects
   - [ ] **Constraints:** CSTR-PLANNER-V5, CSTR-PLANNER-V6
   - [ ] **Files:** `src/models/handoff_plan.py`

- [ ] **A4. Implement `HandoffPlanner` class with LLM call + Pydantic validation + retry + dead-letter**
   - [ ] File: `src/handoff_planner.py` (new; ~250 LOC)
   - [ ] Module-level constant `_PLANNER_SYSTEM_PROMPT: str` — embed:
     - The exact output shape (mirror A7 spec verbatim)
     - 2–3 minimal canonical examples (Specialist A1, Creative CREATIVE-A1)
     - Discipline rules: no prose outside structure, no code fences, one task per atomic change, always include acceptance + constraints + files (Specialist A1)
   - [ ] Class `HandoffPlanner` with:
     - `__init__(self, llm_client=None)` — accept injectable LLM client for testing; default to module-level `llm` import
     - `def plan(self, proposal: ValidatedProposal, council_report: str, binding_constraints: list[str]) -> HandoffPlan`
   - [ ] `plan()` flow:
     1. `clean_report = strip_fences(council_report)` (CSTR-PLANNER-V3)
     2. Build user prompt: include proposal id, proposal body, clean report, binding constraints
     3. Call LLM with role config from `get_role_config("handoff_planner")`, **wrap in a 60-second hard timeout** (Specialist A2). On timeout → raise `PlannerTimeout`
     4. Try to parse + validate response into `HandoffPlan`
     5. On `ValidationError`: retry once with `f"Your previous response failed validation: {error}. Re-emit per the schema."` injected into the prompt
     6. On second failure: write a dead-letter file at `dev/failed_routings/handoff_planner_<ts>.failed.md` with the raw LLM output + validation error, then raise `PlannerValidationFailed`
   - [ ] Custom exceptions: `PlannerTimeout`, `PlannerValidationFailed`
   - [ ] **Acceptance:** unit tests in A8 pass; no new pip deps; importing the module has zero side effects (no LLM calls, no filesystem writes)
   - [ ] **Constraints:** CSTR-PLANNER-V1, CSTR-PLANNER-V2, CSTR-PLANNER-V3, CSTR-PLANNER-V4
   - [ ] **Files:** `src/handoff_planner.py` (new)

### Section C — Wire planner into existing handoff pipeline

- [ ] **A5. Wire planner into `generate_beta_handoff` with explicit fallback**
   - [ ] File: `src/handoff_writer.py`
   - [ ] In `generate_beta_handoff`:
     - If `handoff.planner_enabled` flag is `true` (default): try `HandoffPlanner().plan(...)`, then `plan.to_markdown()` for the `## 🔧 Implementation Tasks` block
     - On `PlannerTimeout`, `PlannerValidationFailed`, or any other exception from the planner: fall back to today's regex extractor and **prepend** the exact notice (Specialist A4): `PLANNER FAILED, FALLBACK ACTIVE: <short reason>. Tasks extracted via legacy regex.`
     - The notice MUST be the first line of the `## 🔧 Implementation Tasks` block (above any tasks)
   - [ ] **Acceptance:** integration tests A9 confirm planner-called path + fallback path; existing handoffs still generate correctly when planner is disabled
   - [ ] **Constraints:** CSTR-PLANNER-V2
   - [ ] **Files:** `src/handoff_writer.py`

- [ ] **A6. Wire planner into `generate_alpha_handoff` with explicit fallback**
   - [ ] File: `src/handoff_writer.py`
   - [ ] Apply the same change as A5 to the alpha-handoff path
   - [ ] **Acceptance:** alpha-path equivalent of A9 passes
   - [ ] **Constraints:** CSTR-PLANNER-V2
   - [ ] **Files:** `src/handoff_writer.py`

- [ ] **A7. Update orchestrator return contract for technical + boardroom meetings**
   - [ ] File: `src/orchestrator.py`
   - [ ] `execute_technical_meeting` and `execute_sequential_boardroom` currently return `str` (or `Path` post Phase 5 A2 — see [src/api.py](../../src/api.py) which now branches on type after commit `260d92a`)
   - [ ] Change return shape to `{"report": str, "plan": HandoffPlan | None, "saved_path": Path | None}` where `plan` is generated by the same `HandoffPlanner` call used in `handoff_writer`
   - [ ] **Backward compatibility:** any caller doing `result["report"]` keeps working. Update `api.py:/process` to handle the new dict shape (extract `saved_path` directly; no double-route)
   - [ ] **Acceptance:** existing CLI / API callers still work; new callers can access `result["plan"]`
   - [ ] **Constraints:** CSTR-PLANNER-V1
   - [ ] **Files:** `src/orchestrator.py`, `src/api.py`

### Section D — Output spec doc

- [ ] **A8. Create `docs/HANDOFF_PLANNER_OUTPUT_SPEC.md` — the single source of truth**
   - [ ] File: `docs/HANDOFF_PLANNER_OUTPUT_SPEC.md` (new; ~120 LOC including 2 examples)
   - [ ] Must cover:
     - Exact markdown shape (sections, task lines, subtasks, acceptance, constraints, files, signature)
     - The `[✏️ PLANNER]` prefix convention (CREATIVE-A2)
     - Subtask indentation (CREATIVE-A3)
     - Signature footer (CREATIVE-A4)
     - 2 worked examples: (i) a simple 3-task plan, (ii) a 2-section plan with subtasks
     - Pydantic schema reference (`src/models/handoff_plan.py`)
     - Fallback notice exact text (Specialist A4)
     - Model-swap trigger: validation success-rate < 90% OR fallback rate > 5% over 20 consecutive runs → swap to `qwen3-vl-4b-thinking`
   - [ ] **Acceptance:** spec is unambiguous — any reviewer reading only this doc can predict the exact output bytes of `to_markdown()` for a given `HandoffPlan`
   - [ ] **Constraints:** CSTR-PLANNER-V6
   - [ ] **Files:** `docs/HANDOFF_PLANNER_OUTPUT_SPEC.md`

### Section E — Tests, flag, migration

- [ ] **A9. Unit tests for `HandoffPlanner` + `HandoffPlan`**
   - [ ] File: `tests/test_handoff_planner.py` (new; ≥12 cases)
   - [ ] Required cases:
     1. Planner on a real Phase 5 verdict (fixture) → emits valid `HandoffPlan`
     2. Planner on a verdict wrapped in `\`\`\`markdown` fenced block → still valid (CSTR-PLANNER-V3)
     3. `HandoffPlan` rejects empty `sections`
     4. `HandoffPlan` rejects task without `acceptance`
     5. `HandoffPlan` rejects task with malformed `id`
     6. `strip_fences` is called BEFORE the LLM (assert via mock)
     7. `to_markdown()` round-trips to structurally equivalent `HandoffPlan` (CSTR-PLANNER-V5)
     8. Retry-on-validation-failure: first LLM response invalid, second valid → returns the second
     9. Dead-letter fires on double-failure → file at `dev/failed_routings/handoff_planner_*.failed.md` exists; raises `PlannerValidationFailed`
     10. Timeout: mock LLM that sleeps 65s → raises `PlannerTimeout`
     11. End-to-end with recorded fixture council report → produces ≥5 tasks
     12. `to_markdown()` output includes the `[✏️ PLANNER]` prefix on every task (CREATIVE-A2)
   - [ ] **Acceptance:** all 12 cases pass; mutation-validated (remove `[✏️ PLANNER]` from `to_markdown` → case 12 fails)
   - [ ] **Constraints:** CSTR-PLANNER-V4, CSTR-PLANNER-V5
   - [ ] **Files:** `tests/test_handoff_planner.py`

- [ ] **A10. Integration tests for the handoff pipeline**
   - [ ] File: `tests/integration/test_beta_handoff_uses_planner.py` (new; ≥3 cases)
   - [ ] Required cases:
     1. `generate_beta_handoff` calls `HandoffPlanner().plan(...)` (mock confirms)
     2. Resulting handoff file has ≥5 task items (not the placeholder)
     3. On `PlannerTimeout` injected via mock, fallback extractor fires and the resulting handoff starts with the exact notice text
   - [ ] **Acceptance:** all 3 cases pass with `tmp_path` isolation (no pollution of real `dev/handoffs/`)
   - [ ] **Constraints:** CSTR-PLANNER-V2
   - [ ] **Files:** `tests/integration/test_beta_handoff_uses_planner.py`

- [ ] **A11. Feature flag + migration script**
   - [ ] File 1: [dev/master_config.md](../master_config.md) — add the `handoff` block:
     ```yaml
     handoff:
       planner_enabled: true   # false = revert to legacy regex extractor
     ```
   - [ ] File 2: `scripts/replan_existing_handoffs.py` (new; ~80 LOC) — re-run planner against:
     - `dev/handoffs/ARCH-20260523-235908-49798A0E_BETA_HANDOFF.md` (Phase 5)
     - `dev/handoffs/ARCH-20260523-223403-78D36EDB_BETA_HANDOFF.md` (DevLog Agent, if present)
   - [ ] Script must:
     - Read the existing handoff
     - Extract the council verdict (already-embedded `## 🧠 Technical Council Deliberation` block)
     - Run `HandoffPlanner().plan(...)`
     - Overwrite **only** the `## 🔧 Implementation Tasks` block (preserve everything else)
     - Print a diff summary
     - Take a `--dry-run` flag (default true; require `--apply` to actually write)
   - [ ] **Acceptance:** `python scripts/replan_existing_handoffs.py --dry-run` shows a non-empty diff for each handoff; `--apply` writes successfully; the rewritten handoffs validate with the Pydantic schema if parsed back
   - [ ] **Constraints:** CSTR-PLANNER-V2, CSTR-PLANNER-V5, CSTR-PLANNER-V6
   - [ ] **Files:** `dev/master_config.md`, `scripts/replan_existing_handoffs.py`

---

## 🚦 Stop & report when done

When all 11 task boxes are ticked:
1. Run `pytest tests/test_handoff_planner.py tests/integration/test_beta_handoff_uses_planner.py -v` — must be 100% green
2. Run the existing gate: `python scripts/alpha_polish_check.py --phase all` — must stay at 35/35
3. Run `python scripts/replan_existing_handoffs.py --apply` once and commit the rewritten handoffs as a separate commit (so it's reversible)
4. Update this file's frontmatter: `status: complete`, `tasks_completed: 11`
5. Report back: "ARCH-5DFB393F implementation complete; ready for alpha polish"

---

## 🧠 Technical Council Deliberation — preserved from boardroom run

> Source: `council_memory/archived/2026-05/task_20260525_125253_9afe2aaf.json` (62 KB, 5 board roles + chairman, 27.5 min wall-clock). Per-role JSON-mode opinions and the chairman verdict are summarised below; the raw JSON is the authoritative artefact.

### 📜 Definitive Verdict (Chairman — `hermes-4-70b`)

**APPROVE-WITH-AMENDMENTS.** Approve Section A–E (deliverables 1–11). Implement with the consolidated amendments below (full text in `scripts/.boardroom_verdict_chairman.txt`). Section F remains deferred per the proposal.

### 🛠 Specialist amendments (technical — `qwen3.6-27b`)

- **A1** Expand `_PLANNER_SYSTEM_PROMPT` with the exact markdown template + 2–3 minimal examples + discipline rules
- **A2** 60-second hard timeout on the planner LLM call → fallback on timeout
- **A3** Deterministic ordering: sections in proposal order, tasks by id, subtasks as-provided
- **A4** Exact fallback notice text: `PLANNER FAILED, FALLBACK ACTIVE: [short reason]. Tasks extracted via legacy regex.`
- **A5** Planner reads the latest proposal version at call time (no stale snapshots)
- **A6** Idempotency test compares normalised task sets, not raw strings (CSTR-PLANNER-V5)

### 🎨 Creative amendments (aesthetic — `hermes-4.3-36b-heretic-i1`)

- **CREATIVE-A1** Embed Dark-Maestro examples (backticks on paths, H3 / CSTR-X-V2 notation) directly in the system prompt
- **CREATIVE-A2** Task prefix `[✏️ PLANNER]` on every machine-generated task line
- **CREATIVE-A3** Subtask visual distinction (3-space indent + hyphen)
- **CREATIVE-A4** Signature footer at end of the `## 🔧 Implementation Tasks` block: `*Generated by HandoffPlanner v1.0. Dark Maestro Ready.*`
- **CREATIVE-A5** Evocative, active, concise task titles (enforce via prompt examples)

### ⚖️ Logical structure (`gemma-4-31b-it`)

1. Section A–E is a closed loop: Role → Logic → Wiring → Spec → Test → Rollout.
2. Specialist's technical guardrails + Creative's aesthetic markers merge cleanly — no conflicts.
3. `ministral-3-3b` is logically sufficient for structural mapping; Pydantic mitigates schema drift.
4. Primary failure mode: "schema drift" (valid markdown, invalid logic / paths). Mitigation: strict prompt examples + A8 round-trip test.

### 🔴 Critic concerns (addressed)

- **Backtick consistency** on file paths → resolved by Spec doc (A8) + system-prompt examples (CREATIVE-A1)
- **System-prompt vagueness** → resolved by Specialist A1 + Creative CREATIVE-A1 (both demand explicit examples)

### Strategic view (`hermes-4-70b`)

This proposal bridges council deliberation and editor actionability via deterministic task decomposition. Section A–E is a complete, testable solution with robust fallback. Success depends on (1) LLM consistency at low temperature with tight schema, and (2) system-prompt precision.

---

## 🚨 Binding Constraints (Reaffirmed)

| ID | Constraint |
|---|---|
| CSTR-PLANNER-V1 | No new dependencies. Stdlib + already-installed only. |
| CSTR-PLANNER-V2 | Planner failure NEVER blocks the handoff. Fallback with explicit notice. |
| CSTR-PLANNER-V3 | Strip fences before the planner sees text (use existing `strip_fences()`). |
| CSTR-PLANNER-V4 | Planner output is Pydantic-validated, fail-fast. |
| CSTR-PLANNER-V5 | Idempotent. Tests assert structural (normalised) equivalence. |
| CSTR-PLANNER-V6 | Schema-stable output. System prompt is a module constant; profiles deferred. |

---

## 📝 Developer Notes

- **Scribe error:** the scribe role (`ministral-3-3b`) channel-errored at 13:20:25, after the full council had finished deliberating. The deliberation **completed successfully**; only the master-report synthesis was lost. Per-role opinions are preserved at `council_memory/archived/2026-05/task_20260525_125253_9afe2aaf.json`.
- **Brand Guard output:** the brand-guard pass between each board role returned `{"error": "No JSON found", "raw": ""}` — pre-existing issue with `qwen3-vl-4b-thinking` when invoked with no image. Not in scope for this handoff; flag separately if needed.
- **Double-route fix:** the `/process` endpoint was double-routing boardroom outputs (Phase 5 regression). Fixed at commit `260d92a` immediately before this handoff was written.
- **Section F deferred:** see commit `5f8550c` for the scope trim. Filed as a follow-on `ARCH-CODER-PROFILE-REGISTRY` once the planner has run against ≥3 real handoffs.

---

## ✅ Completion Gate

- [ ] All 11 tasks A1–A11 ticked
- [ ] `pytest tests/test_handoff_planner.py tests/integration/test_beta_handoff_uses_planner.py` green
- [ ] `python scripts/alpha_polish_check.py --phase all` reports 35/35
- [ ] `scripts/replan_existing_handoffs.py --apply` run + rewritten handoffs committed separately
- [ ] Frontmatter updated: `status: complete`, `tasks_completed: 11`
- [ ] Kanban card dragged from Beta Testing → Alpha Polish

---

*Generated by manual reconstruction from boardroom task_20260525_125253_9afe2aaf. Dark Maestro Ready.*
