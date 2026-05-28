---
proposal_id: ARCH-20260522-161800-F10FE0E1
phase: alpha
status: in_progress
created: 2026-05-28 17:09:18
handoff_type: alpha_polish
related_proposal: "[[ARCH-20260522-161800-F10FE0E1_PROPOSAL]]"
related_beta_handoff: "[[ARCH-20260522-161800-F10FE0E1_BETA_HANDOFF]]"
kanban_card_id: "^[ARCH-20260522161800-F10FE0]"
source_note: ""
next_phase: Finalized
tasks_completed: 0
tasks_total: 21
vault_kanban: "1. P - Seedlings/Dev-KanBan.md"
---

# 🛠 Alpha Polish Handoff — ARCH-20260522-161800-F10FE0E1

> **Generated**: 2026-05-28 17:09:18
> **Proposal**: [[ARCH-20260522-161800-F10FE0E1_PROPOSAL]]
> **Beta Handoff**: [[ARCH-20260522-161800-F10FE0E1_BETA_HANDOFF]]
> **Phase**: Alpha Polish
> **Status**: 🔧 In Progress — take this document to VS Code

---

## 🤖 Agent Context

> *This block is for AI agents (Cline/Claude in VS Code). Not displayed in Obsidian reading mode.*

When a user references this handoff:

1. **Find the proposal** → `cognitive-os/dev/proposals/DEV-…_PROPOSAL.md`
2. **Find the beta handoff** → `cognitive-os/dev/handoffs/DEV-…_BETA_HANDOFF.md`
3. **Work through the tasks** in `## 🔧 Implementation Tasks` below, ticking each `- [ ]` to `- [x]` as completed
4. **When all tasks are ticked** → update this file's frontmatter: `status: complete`, `tasks_completed: <n>`
5. **Update the proposal** → change `## 🛠 Alpha Polish` status line to `✅ Complete`
6. **Update the Kanban card** at `vault_kanban` above → change status to `✅ Ready for Finalize`
7. **Tell the user** to drag the card to the `Finalized` column to trigger the release council

---

## 📜 Executive Summary

Error: Error code: 400 - {'error': 'The number of tokens to keep from the initial prompt is greater than the context length (n_keep: 10764>= n_ctx: 8192). Try to load the model with a larger context length, or provide a shorter input.'}

---

## 🎯 Acceptance Thresholds

_No explicit thresholds extracted — see full report below._

---

## 🚫 Veto Points

_No explicit veto points extracted — see full report below._

---

## 🔧 Implementation Tasks

> Tick each item off as you complete it in VS Code.
> Update `tasks_completed` in the frontmatter as you go.

### Section A — Core

- [ ] **[✏️ PLANNER] A1. Create config/state_machine.yaml with phases, transitions, gates**
   - **Acceptance:** The file config/state_machine.yaml exists and defines the state machine table and gate definitions.
   - **Constraints:** H3
   - **Files:** `config/state_machine.yaml`

- [ ] **[✏️ PLANNER] A2. Extend src/workflow_models.py with PhaseTransition, GateResult, WorkflowTransitionResult, BetaSubstatus enum**
   - **Acceptance:** The file src/workflow_models.py includes the new types and no I/O operations.
   - **Constraints:** H3
   - **Files:** `src/workflow_models.py`

- [ ] **[✏️ PLANNER] A3. Create src/git_snapshot.py with tag_execution_start and rollback_to_tag functions**
   - **Acceptance:** The file src/git_snapshot.py includes the two functions which raise on failure.
   - **Constraints:** H3
   - **Files:** `src/git_snapshot.py`

- [ ] **[✏️ PLANNER] A4. Create src/workflow_engine.py with transition() method**
   - **Acceptance:** The file src/workflow_engine.py includes the transition() method which orchestrates state transitions, gate checks, and snapshotting.
   - **Constraints:** H3
   - **Files:** `src/workflow_engine.py`

- [ ] **[✏️ PLANNER] A5. Refactor src/dev_route.py to delegate proposal lifecycle management to workflow_engine**
   - **Acceptance:** The file src/dev_route.py no longer contains regex edits to the phase field and delegates transitions through workflow_engine.
   - **Constraints:** H3
   - **Files:** `src/dev_route.py`

- [ ] **[✏️ PLANNER] A6. Extend src/kanban_processor.py to call workflow_engine.transition() for column-drag handling**
   - **Acceptance:** The file src/kanban_processor.py no longer contains direct phase writes and translates column changes through workflow_engine.
   - **Constraints:** H3
   - **Files:** `src/kanban_processor.py`

- [ ] **[✏️ PLANNER] A7. Add API endpoints for POST /api/workflow/transition, GET /api/workflow/state/{proposal_id}, and POST /api/workflow/rollback/{proposal_id}**
   - **Acceptance:** The API includes the specified endpoints which interact with workflow_engine.
   - **Constraints:** H3
   - **Files:** `src/api.py`

- [ ] **[✏️ PLANNER] A8. Run idempotent migration to set substatus: planning for existing beta_testing proposals**
   - **Acceptance:** The system automatically sets the substatus to planning for all legacy beta_testing proposals without manual intervention.
   - **Constraints:** H3

- [ ] **[✏️ PLANNER] A9. Dashboard: render substatus badge based on YAML substatus**
   - **Acceptance:** The dashboard displays the correct substatus badge for each proposal card.
   - **Constraints:** H3

- [ ] **[✏️ PLANNER] A10. Gate-fail UI: display checklist on transition failure**
   - **Acceptance:** When a transition fails due to gate checks, the dashboard shows a detailed checklist indicating which checks failed.
   - **Constraints:** H3

### Section B — Tests

- [ ] **[✏️ PLANNER] B1. Cover transition orchestration in src/workflow_engine.py with tests**
   - [ ] Test successful transitions
   - [ ] Test failed transitions due to gate checks
   - **Acceptance:** All code paths in src/workflow_engine.py are covered by unit tests.
   - **Constraints:** CSTR-PLANNER-V4
   - **Files:** `tests/test_workflow_engine.py`

- [ ] **[✏️ PLANNER] B2. Cover API endpoints in src/api.py with tests**
   - [ ] Test POST /api/workflow/transition
   - [ ] Test GET /api/workflow/state/{proposal_id}
   - [ ] Test POST /api/workflow/rollback/{proposal_id}
   - **Acceptance:** All code paths in the API endpoints are covered by integration tests.
   - **Constraints:** CSTR-PLANNER-V4
   - **Files:** `tests/test_api.py`

- [ ] **[✏️ PLANNER] B3. Cover git operations in src/git_snapshot.py with tests**
   - [ ] Test successful tag creation
   - [ ] Test failure scenarios in git operations
   - **Acceptance:** All code paths in src/git_snapshot.py are covered by unit tests.
   - **Constraints:** CSTR-PLANNER-V4
   - **Files:** `tests/test_git_snapshot.py`

### Section C — Migration

- [ ] **[✏️ PLANNER] C1. Ensure config/state_machine.yaml is compatible with previous versions**
   - **Acceptance:** The state machine configuration in config/state_machine.yaml can be read by older versions of the system without errors.
   - **Constraints:** CSTR-PLANNER-V4
   - **Files:** `config/state_machine.yaml`

---
*Generated by HandoffPlanner v1.0. Dark Maestro Ready.*

---

## 🧠 Boardroom Deliberation

<details>
<summary>Full council report (click to expand)</summary>

Error: Error code: 400 - {'error': 'The number of tokens to keep from the initial prompt is greater than the context length (n_keep: 10764>= n_ctx: 8192). Try to load the model with a larger context length, or provide a shorter input.'}

</details>

---

## 📝 Developer Notes

> *Fill in as you work through the tasks above.*

<!-- Add your implementation notes, decisions, and blockers here -->

---

## ✅ Completion Gate

Before moving the Kanban card to **Finalized**, confirm:

- [ ] All implementation tasks above are ticked
- [ ] Every acceptance threshold met
- [ ] No outstanding council vetoes
- [ ] Manual smoke test passed

---

*Handoff generated by Cognitive OS Boardroom Council*
*Card stays in **Alpha Polish** until all tasks above are complete.*
*Only then move the card to **Finalized**.*
