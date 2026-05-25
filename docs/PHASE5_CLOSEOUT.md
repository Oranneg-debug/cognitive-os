# Phase 5 — Governance Foundation Production Integration — Closeout

**Proposal:** `ARCH-20260523-235908-49798A0E`
**Branch:** main (all work pushed)
**Status:** Functionally complete. F4 deferred to dashboard migration.

---

## Acceptance gate (handoff lines 204-213)

| Item | Status | Evidence |
|------|--------|----------|
| **F1** `python scripts/alpha_polish_check.py --phase all` → 35/35 PASS | ✅ | 35/35 gates green |
| **F2** `python -m pytest tests/ -v` → all green, ≥10 integration tests | ✅ | 169 passed, 1 skipped. 14 integration cases across 10 files (spec required ≥10). |
| **F3** `python scripts/smoke_phase5.py` → exit 0 | ✅ | All 3 probes (e1a / e1b / e1c) pass. JSON output, idempotent cleanup. |
| **F4** Manual: drag a test card on the kanban; verify verdict lands in `dev/decisions/` first try | 🟡 **Deferred** | See below. |
| **F5** Commit hygiene: one logical commit per section. No megacommits. | ✅ | 27 commits, average ~50 lines each. `fix:` and `test:` separated. No `WIP`. |

---

## F4 — what was found, why it's deferred

The handoff's F4 line says *"verify verdict lands in `dev/decisions/` first try"*. We attempted it three
times after Phase 5 D + E were green. Each attempt surfaced previously-latent production bugs in the
kanban-watcher → workflow_engine call path:

| Attempt | Bug surfaced | Commit |
|---------|--------------|--------|
| 1 | `kanban_processor.columns` had `phase_key="beta"` but `WorkflowPhase` enum is `"beta_testing"`. `WorkflowPhase(next_phase)` raised `ValueError` before workflow_engine was invoked. | `036d4ec` |
| 2 | `WorkflowEngine.transition` used the wrong filename pattern (`<id>.md`) and a relative `PROPOSALS_DIR`. Real proposals are `<id>_PROPOSAL.md` under an absolute path. | `ef2f6f6` |
| 3 | `WorkflowEngine.transition` called `yaml.safe_load(f)` on the whole proposal file. PyYAML rejected the multi-`---` stream. Also: `yaml.dump(current_data, f)` would have wiped the markdown body on a successful write — data-loss bug. | `20cc116` |

Three attempts, four production bugs. Two of those (the yaml.safe_load + yaml.dump pair) would have
caused silent data loss on any successful F4 transition. None were caught by the test suite or smoke
because D2 + E1c mock `WorkflowEngine.transition` and the smoke skips the saga.

Each fix is independently green (all 35/35 gates, all tests pass after each commit). They are real
production improvements regardless of whether F4 itself completes today.

### Why we stopped here

1. **The kanban-file watcher layer is being replaced by the dashboard.** Each remaining F4 fix
   buys partial throwaway value — the column-name parsing, the file-poll loop, and the markdown
   kanban format will all go away when the dashboard backend stores transitions as structured API
   calls.

2. **WorkflowEngine itself stays.** Bugs #2 and #3 (the `ef2f6f6` and `20cc116` fixes) benefit
   the future dashboard caller exactly the same way. Bug #1 (`036d4ec`) is partially obsolete but
   the WorkflowPhase enum value is still correct — only the column-string mapping is throwaway.

3. **Remaining unknowns are dashboard-layer concerns.** A successful F4 transition would have
   exercised `ensure_branch` (real git operations on the dev repo), `tag_execution_start`
   (skipped for beta_testing — only fires on ALPHA), the 13-call boardroom council via LM Studio,
   and `handoff_writer.generate_beta_handoff`. Each is testable more directly under the new
   dash architecture, with explicit unit-tested boundaries.

### What "F4 deferred" means concretely

- The **production wiring** Phase 5 delivered is verified by F2 (integration tests) and F3 (smoke).
  OutputRouter, GovernanceUnitOfWork, ApprovalLogger, integration_flags, and the lifespan validators
  all work in production paths under real disk I/O.
- The **kanban-driven trigger path** for that wiring is partially-but-not-fully verified end-to-end
  in real prod. Frontmatter updates work. Backend↔vault sync works. Watcher detection works.
  WorkflowEngine integration into kanban_processor is now patched but the full saga (git ops +
  council + handoff) has not run against real prod state.
- F4 will be **re-tested as part of the dashboard migration**, with an explicit "dashboard fires
  a phase transition via API; verdict lands in `dev/decisions/`" test that replaces F4's manual
  drag.

---

## Bugs surfaced during Phase 5 D + E + F (all fixed, all on origin)

D-section integration tests + E1 smoke + F4 attempts caught 13 latent production bugs:

| # | Commit | Module | Symptom |
|---|--------|--------|---------|
| 1 | `309f98d` | `src/api.py` | `OutputRouter.apply()` called with arg order inverted; endpoint errored on every hit |
| 2 | `94585d3` | `src/orchestrator.py` | Same arg order inverted at the council-synthesis call site |
| 3 | `0fdaf81` | `src/output_router.py` | `Path.cwd().name` used as a timestamp placeholder; filenames like `boardroom_proposal_cognitive-os.md` |
| 4 | `cb3f5bb` | `src/kanban_processor.py` | Vetoed transition dead-letter file was overwritten by broad `except Exception` with less informative reason |
| 5 | `eb3a622` | `src/proposal_writer.py` | Missing `get_integration_flags` import; `create_proposal` would NameError on every invocation |
| 6 | `ac5221c` | `src/governance_unit_of_work.py` | `_rollback` didn't clean up `target.parent/.uow_<id>` sibling staging dirs; every aborted UoW leaked a dir |
| 7 | `7fd2da1` | `src/uow_recovery.py` | `UoW_LOG_DIR` typo (vs `UOW_LOG_DIR`); recovery NameError'd on every call, silently swallowed by api.py lifespan |
| 8 | `14f9c46` | `src/uow_recovery.py` | `log_path.stem` for `<id>.undo.json` returned `<id>.undo`; recovered files named `…_PROPOSAL.md.recovered_<id>.undo` |
| 9 | `a2e9925` | `src/api.py` | `_validate_routing_rules()` called `load_routing_rules()` with no arg (B-section regression); RuntimeError wrapper masked the TypeError |
| 10 | `a7fd253` | `src/approval_logger.py` | Missing `log_approval` method; `KanbanProcessor._audit_log_block` silently NameError'd; vetoed-transition audit trail invisible since A4 |
| 11 | `036d4ec` | `src/kanban_processor.py` + `src/orchestrator.py` | `beta` vs `beta_testing` WorkflowPhase mismatch |
| 12 | `ef2f6f6` | `src/workflow_engine.py` | Wrong proposal filename pattern + relative path |
| 13 | `20cc116` | `src/workflow_engine.py` | yaml.safe_load on full markdown file; yaml.dump that would have wiped body |

---

## What ships from Phase 5

### Code
- `src/integration_flags.py` (new) — cached one-shot flag reader on top of MasterConfig singleton
- `src/output_router.py` (new in earlier phases, wired in A1) — single source of routing truth
- `src/filesystem_backend_writer.py` (new in A1)
- `src/governance_unit_of_work.py` (new in earlier phases, wired in A4)
- `src/uow_recovery.py` (new in A4) — boot-time staged-transaction recovery
- `scripts/migrate_ai_help_legacy.py` (new in C2) — one-shot OutputRouter-based migration
- `scripts/smoke_phase5.py` (new in E1) — production deployment gate
- 13 bug-fix commits in pre-existing modules (above)

### Tests
- `tests/integration/` directory created in D1
- 9 spec-deliverable D-section files + 1 parametrized D8 + 1 parametrized D9 = **14 integration test cases**
- `docs/REVIEWER_SOP.md` — workflow documentation

### Architecture documented
- `docs/REVIEWER_SOP.md` — plan / code / review / commit loop with LLM coders
- `dev/.cline_rejected_phase5/` (gitignored) — quarantined off-spec submissions for reference

---

## Recommended next milestone

**Dashboard migration** (separate proposal). When it lands, F4 becomes part of the dashboard's
own acceptance test:

> *"Dashboard fires a phase transition via POST /api/transitions; the verdict lands in
> `dev/decisions/` and the kanban widget reflects the new phase; no markdown-file polling involved."*

That obsoletes the kanban file watcher, retires `kanban_processor._update_proposal_phase`'s
column-string parsing, and the F4 deferral is naturally closed.

---

## Push status

`origin/main = 20cc116` as of Phase 5 closeout. 27 commits across the phase, no WIP, no
megacommits. All bug-fixes pushed.
