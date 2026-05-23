---
proposal_id: ARCH-20260522-161800-F10FE0E1
phase: beta
status: in_progress
created: 2026-05-23 13:48:24
handoff_type: beta_testing
related_proposal: "[[ARCH-20260522-161800-F10FE0E1_PROPOSAL]]"
kanban_card_id: "^[ARCH-20260522161800-F10FE0]"
source_note: ""
next_phase: Alpha Polish
tasks_completed: 0
tasks_total: 5
vault_kanban: "1. P - Seedlings/Dev-KanBan.md"
---

# 🧪 Beta Testing Handoff — ARCH-20260522-161800-F10FE0E1

> **Generated**: 2026-05-23 13:48:24  
> **Proposal**: [[ARCH-20260522-161800-F10FE0E1_PROPOSAL]]  
> **Phase**: Beta Testing  
> **Status**: 🔧 In Progress — take this document to VS Code

---

## 🤖 Agent Context

> *This block is for AI agents (Cline/Claude in VS Code). It is not displayed in Obsidian reading mode.*

When a user references this handoff (e.g. *"work on ARCH-20260522-161800-F10FE0E1"*):

1. **Find the proposal** → `cognitive-os/dev/proposals/ARCH-20260522-161800-F10FE0E1_PROPOSAL.md`
2. **Work through the tasks** in `## 🔧 Implementation Tasks` below, ticking each `- [ ]` to `- [x]` as completed
3. **When all tasks are ticked** → update this file's frontmatter: `status: complete`, `tasks_completed: <n>`
4. **Update the proposal** → change `## 🧪 Beta Testing` status line to `✅ Complete`
5. **Update the Kanban card** at `vault_kanban` above → change `  - status: 🔍 Review` to `  - status: ✅ Ready for Alpha Polish`
6. **Tell the user** to drag the card to the `Alpha Polish` column to trigger the next council automatically

Backlinks to maintain:
- Proposal: [[ARCH-20260522-161800-F10FE0E1_PROPOSAL]]
- Source note: see `source_note` in frontmatter above (if set)
- Kanban card ID: see `kanban_card_id` in frontmatter above

---

## 📋 Executive Summary

**Final Decision**: (no explicit final_decision; substance is APPROVAL per audit_report)

**Audit Report**:

The primary technical gaps identified during deliberation involve operational stability and atomicity. Specifically: 1) Raw subprocess calls for Git operations lack timeouts, risking FastAPI worker starvation. 2) The `version_hash` implementation is too broad, potentially including volatile metadata (timestamps) which would trigger false 409 Conflicts. 3) Saga compensation logic was conceptually present but lacked a concrete execution contract (e.g., how to handle tag deletion during rollback). 4) SQLite performance for Gate #3 was unoptimized without a composite index strategy.

---

## ⚠️ Difficulties & Constraints

**Binding Vetoes (from chairman)**:

- No raw subprocess git calls without timeouts.
- No hashing of volatile frontmatter fields for version control.
- No generic rollback logic; every saga step must have a defined compensating function.
- No manual overrides of the hard planning→execution gate.
- No direct writes to the 'phase:' field outside the WorkflowEngine.

**Risk Register (from technical critic)**:

- **high**: Raw subprocess git operations without timeouts or a structured client (risk of hanging workers).
- **medium**: Hashing entire frontmatter including volatile metadata fields (will cause false 409s).
- **high**: Underspecified saga compensations; must explicitly define rollback behavior per step, not assume generic revert.
- **medium**: No index strategy for SQLite Gate #3 query; will degrade under load.

---

## 🔧 Implementation Tasks

> Tick each item off as you complete it in VS Code.
> Update `tasks_completed` in the frontmatter as you go.

- [ ] **State & Concurrency**: Use optimistic concurrency control via a `version_hash`. This hash MUST be calculated only from semantic workflow keys (excluding volatile metadata like 'last_modified').
- [ ] **Atomic Transitions (Saga Pattern)**: Every transition follows a strict sequence: [Snapshot] -> [Version Verify] -> [Git Branch/Tag] -> [YAML Write] -> [Log]. Each step must have an explicit compensating action (e.g., if YAML write fails, the Git tag created in the previous step must be deleted).
- [ ] **Git Integration**: Replace raw subprocess calls with a structured wrapper (e.g., GitPython or a custom async client) enforcing strict timeouts and `asyncio.to_thread` execution to prevent blocking workers. Per-proposal branches (`feat/proposal-{id}`) are mandatory to allow parallel work.
- [ ] **Gate Execution**: Gate #3 (Technical Consensus) will be enforced via an SQLite query on the `approval_log` table, supported by a composite index on `(proposal_id, role, decision, ts)` for O(1) or O(log n) lookup.
- [ ] **UX/UI**: Implement G5 aesthetic direction (Gothic occult iconography, blood-red failure modals) while maintaining the existing 6-column Kanban structure via YAML substatus badges.

---

## 🧠 Technical Council Deliberation

<details>
<summary>Full council report (click to expand)</summary>

**Task ID**: `task_20260523_132456_db8e7ecf`
**Pattern**: `ORCHESTRATED_TECHNICAL_OVERSEER`
**Completed**: 2026-05-23T13:35:10.732485

### Chairman / Overseer Synthesis

#### audit_report

```
The primary technical gaps identified during deliberation involve operational stability and atomicity. Specifically: 1) Raw subprocess calls for Git operations lack timeouts, risking FastAPI worker starvation. 2) The `version_hash` implementation is too broad, potentially including volatile metadata (timestamps) which would trigger false 409 Conflicts. 3) Saga compensation logic was conceptually present but lacked a concrete execution contract (e.g., how to handle tag deletion during rollback). 4) SQLite performance for Gate #3 was unoptimized without a composite index strategy.
```

#### definitive_blueprint

```
The system will implement a centralized `WorkflowEngine` driving a 7-phase FSM with a hard planning→execution gate. 

1. **State & Concurrency**: Use optimistic concurrency control via a `version_hash`. This hash MUST be calculated only from semantic workflow keys (excluding volatile metadata like 'last_modified'). 
2. **Atomic Transitions (Saga Pattern)**: Every transition follows a strict sequence: [Snapshot] -> [Version Verify] -> [Git Branch/Tag] -> [YAML Write] -> [Log]. Each step must have an explicit compensating action (e.g., if YAML write fails, the Git tag created in the previous step must be deleted). 
3. **Git Integration**: Replace raw subprocess calls with a structured wrapper (e.g., GitPython or a custom async client) enforcing strict timeouts and `asyncio.to_thread` execution to prevent blocking workers. Per-proposal branches (`feat/proposal-{id}`) are mandatory to allow parallel work. 
4. **Gate Execution**: Gate #3 (Technical Consensus) will be enforced via an SQLite query on the `approval_log` table, supported by a composite index on `(proposal_id, role, decision, ts)` for O(1) or O(log n) lookup. 
5. **UX/UI**: Implement G5 aesthetic direction (Gothic occult iconography, blood-red failure modals) while maintaining the existing 6-column Kanban structure via YAML substatus badges.
```

#### veto_points

```
[
  "No raw subprocess git calls without timeouts.",
  "No hashing of volatile frontmatter fields for version control.",
  "No generic rollback logic; every saga step must have a defined compensating function.",
  "No manual overrides of the hard planning→execution gate.",
  "No direct writes to the 'phase:' field outside the WorkflowEngine."
]
```

### Per-Role Opinions

#### moderator — `deepseek-coder-v2-lite-instruct` — 2026-05-23T13:25:13.595629

**transition_reason**: To start the discussion on the implementation tasks for the workflow execution system.

**context_summary**: The proposal aims to build a state machine that drives proposals through their lifecycle with hard approval gates and immutable git-tag execution snapshots. The current shape of the system shows issues in modularity, central record keeping, and gate management between planning and execution phases.

#### technical_specialist — `qwen3.6-27b-heretic-uncensored-finetune-neo-code-di-imatrix-max` — 2026-05-23T13:29:44.130133

**technical_analysis**: **Summary**
Centralized WorkflowEngine enforcing a 7-phase FSM with a hard planning→execution gate, per-proposal git branches, saga-based atomic transitions, and optimistic concurrency control via frontmatter hashing. Eliminates scattered regex edits; guarantees auditability, rollback capability, and deterministic state changes.

**Difficulties & Constraints**
- Per-proposal branch model assumes isolated workloads; shared dependencies will cause merge conflicts without a clear strategy for cross-proposal changes.
- Saga compensations are underspecified. File snapshots are append-only; rollback must restore prior YAML from the vault, not delete artifacts.
- version_hash over raw frontmatter collides with auto-updated metadata (e.g., last_modified), causing false 409s on valid transitions.
- Gate #3 SQLite query requires composite indexing and strict UTC normalization to avoid performance degradation and timezone drift.
- Git subprocess calls must be wrapped with timeouts; hanging git operations will block FastAPI workers if not isolated.

**Technical Recommendations**
- Use gitpython or a robust wrapper instead of raw subprocess for branch/tag management; enforce structured error types (BranchConflictError, TagCreationError).
- Implement transactional file writes: write to temp path, validate schema, then atomic rename to avoid partial YAML corruption.
- Stabilize version_hash by excluding volatile fields or hashing only semantic workflow keys; alternatively, maintain a dedicated workflow_version field.
- Add composite index on (proposal_id, role, decision, ts) for Gate #3; enforce UTC timestamps across all loggers.
- Define explicit compensation handlers per saga step rather than generic rollback logic.

**actionable_steps**: [
  "1. Create config/state_machine.yaml with phases, transitions, gate specs, and SQLite query templates for Gate #3.",
  "2. Extend src/workflow_models.py: add TransitionRequest, SagaTransaction, CompensatingAction, GateResult, BetaSubstatus; enforce strict typing, zero I/O.",
  "3. Implement src/git_branch_manager.py with ensure_branch(), tag_execution_start(), rollback_to_tag(); wrap git calls in asyncio.to_thread with timeouts and explicit error classes.",
  "4. Build src/workflow_engine.transition() orchestrating the saga: snapshot → verify stable version_hash → git tag on proposal branch → atomic YAML write → log decision; wire compensating actions for each step.",
  "5. Refactor dev_route.py and kanban_processor.py: remove all regex phase edits; delegate to workflow_engine.transition(); handle 409/422 with structured retries or user prompts.",
  "6. Add API endpoints: POST /api/workflow/transition, GET /api/workflow/state/{id}, POST /api/workflow/rollback/{id}; enforce auth, rate limits, and deterministic error payloads.",
  "7. Run idempotent migration script: scan existing beta_testing proposals; inject substatus: planning into frontmatter without altering body; log changes.",
  "8. Implement dashboard substatus rendering and gate-fail modal per G5 direction; consume structured GateResult.failed array for precise UI feedback."
]

**veto_points**: [
  "Raw subprocess git operations without timeouts or a structured client (risk of hanging workers).",
  "Hashing entire frontmatter including volatile metadata fields (will cause false 409s).",
  "Underspecified saga compensations; must explicitly define rollback behavior per step, not assume generic revert.",
  "No index strategy for SQLite Gate #3 query; will degrade under load."
]

**next_step**: Refine saga compensation contracts and version_hash stability rules before coding; draft an explicit error-handling matrix for git/SQLite failures to ensure deterministic rollback behavior.

#### brand_guard_technical_specialist — `deepseek-coder-v2-lite-instruct` — 2026-05-23T13:30:12.595572

**reasoning**: The technical analysis provided outlines significant challenges and constraints that need to be addressed before proceeding with the implementation. The veto points highlight potential risks and deficiencies in the current approach.

**veto_points**: [
  "Raw subprocess git operations without timeouts or a structured client (risk of hanging workers).",
  "Hashing entire frontmatter including volatile metadata fields (will cause false 409s).",
  "Underspecified saga compensations; must explicitly define rollback behavior per step, not assume generic revert.",
  "No index strategy for SQLite Gate #3 query; will degrade under load."
]

**approved**: False

#### technical_creative — `hermes-4.3-36b-heretic-i1` — 2026-05-23T13:30:57.364253

**veto_points**: [
  "Insufficient documentation of how 'volatile frontmatter fields' (e.g., auto-updated timestamps) are filtered in the version_hash calculation. This could introduce false 409 Conflict errors if not precisely specified.",
  "Saga compensation logic for the 'git tag creation' step is underspecified. Rolling back to a prior state after a successful tag requires deleting the tag itself, which could leave the repository in an inconsistent state if the tag was referenced elsewhere."
]

**next_step**: Audit frontmatter structure to define stable semantic hashing fields. Draft compensation procedures for git tag removal as part of the saga rollback contract.

#### brand_guard_technical_creative — `deepseek-coder-v2-lite-instruct` — 2026-05-23T13:31:15.050792

**reasoning**: The proposal outlines a significant architectural innovation but contains veto points that need addressing before proceeding.

**veto_points**: [
  "Insufficient documentation on how volatile frontmatter fields are handled in the version_hash calculation, which could lead to operational issues.",
  "Saga compensation logic for git tag creation is not detailed enough, posing risks of inconsistent repository states."
]

**approved**: False

#### technical_critic — `deepseek-r1-distill-qwen-32b-uncensored` — 2026-05-23T13:33:13.409457

**critical_feedback**: The proposal outlines a comprehensive workflow execution system with several potential risks and challenges. The use of raw subprocess calls for git operations poses a significant risk of hanging workers, which could block FastAPI workers and degrade system performance. Additionally, the version_hash field, which is intended to prevent race conditions by checking if the YAML frontmatter has changed since the last transition, could cause false 409 errors if volatile fields like timestamps are included in the hash. The saga pattern for transitions requires well-defined compensating actions, but these are not clearly specified in the proposal. Finally, the SQLite query for Gate #3 lacks an index strategy, which could lead to performance degradation as more data is added.

**veto_points**: [
  {
    "type": "technical",
    "risk_level": "high",
    "description": "Raw subprocess git operations without timeouts or a structured client (risk of hanging workers)."
  },
  {
    "type": "technical",
    "risk_level": "medium",
    "description": "Hashing entire frontmatter including volatile metadata fields (will cause false 409s)."
  },
  {
    "type": "technical",
    "risk_level": "high",
    "description": "Underspecified saga compensations; must explicitly define rollback behavior per step, not assume generic revert."
  },
  {
    "type": "technical",
    "risk_level": "medium",
    "description": "No index strategy for SQLite Gate #3 query; will degrade under load."
  }
]

**next_step**: Refine saga compensation contracts and version_hash stability rules before coding; draft an explicit error-handling matrix for git/SQLite failures to ensure deterministic rollback behavior.

#### brand_guard_technical_critic — `deepseek-coder-v2-lite-instruct` — 2026-05-23T13:33:53.234385

**reasoning**: The proposal contains several significant technical risks that need to be addressed before proceeding with implementation. The high-risk items include potential hanging subprocesses and unstable version_hash handling which could lead to operational issues.

**veto_points**: [
  "High risk of hanging subprocesses in git operations",
  "Unstable version_hash leading to false 409 errors",
  "Underspecified saga compensations risking unpredictable system behavior"
]

**approved**: False


</details>

---

## 📝 Developer Notes

> *Fill in as you work through the tasks above.*

<!-- Add your implementation notes, decisions, and blockers here -->

---

## ✅ Completion Gate

Before moving the Kanban card to **Alpha Polish**, confirm:

- [ ] All implementation tasks above are ticked
- [ ] Core functionality works end-to-end
- [ ] No critical bugs remain
- [ ] Basic manual testing passed
- [ ] Frontmatter `status` updated to `complete`
- [ ] Proposal `## 🧪 Beta Testing` section updated to `✅ Complete`

---

*Handoff generated by Cognitive OS Technical Council*  
*Card stays in **Beta Testing** until all tasks above are complete.*  
*Only then move the card to **Alpha Polish**.*
