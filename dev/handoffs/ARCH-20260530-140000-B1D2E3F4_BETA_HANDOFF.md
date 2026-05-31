---
proposal_id: ARCH-20260530-140000-B1D2E3F4
phase: beta
status: complete
created: 2026-05-31 03:35:48
last_updated: 2026-05-31 03:55:00
handoff_type: beta_testing
related_proposal: "[[ARCH-20260530-140000-B1D2E3F4_PROPOSAL]]"
kanban_card_id: "^[ARCH-20260530140000-B1D2E3F4]"
next_phase: Alpha Polish
tasks_completed: 4
tasks_total: 4
vault_kanban: "1. P - Seedlings/Dev-KanBan.md"
---

# 🧪 Beta Testing Handoff — ARCH-20260530-140000-B1D2E3F4

> **Generated**: 2026-05-31 03:35:48  
> **Proposal**: [[ARCH-20260530-140000-B1D2E3F4_PROPOSAL]]  
> **Phase**: Beta Testing  
> **Status**: ✅ Complete — ready for Alpha Polish phase

---

## 🤖 Agent Context

> *This block is for AI agents (Cline/Claude in VS Code). It is not displayed in Obsidian reading mode.*

When a user references this handoff (e.g. *"work on ARCH-20260530-140000-B1D2E3F4"*):

1. **Find the proposal** → `cognitive-os/dev/proposals/ARCH-20260530-140000-B1D2E3F4_PROPOSAL.md`
2. **Work through the tasks** in `## 🔧 Implementation Tasks` below, ticking each `- [ ]` to `- [x]` as completed
3. **When all tasks are ticked** → update this file's frontmatter: `status: complete`, `tasks_completed: <n>`
4. **Update the proposal** → change `## 🧪 Beta Testing` status line to `✅ Complete`
5. **Update the Kanban card** at `vault_kanban` above → change `  - status: 🔍 Review` to `  - status: ✅ Ready for Alpha Polish`
6. **Tell the user** to drag the card to the `Alpha Polish` column to trigger the next council automatically

Backlinks to maintain:
- Proposal: [[ARCH-20260530-140000-B1D2E3F4_PROPOSAL]]
- Source note: see `source_note` in frontmatter above (if set)
- Kanban card ID: see `kanban_card_id` in frontmatter above

---

## 📋 Executive Summary

```markdown
# **Final Deliberation Report: ARCH-20260530-140000-B1D2E3F4**
**Runtime Smoke Gates – Import & Data Integrity Verification**
**Origin:** Systems Architect
**Status:** **APPROVED**
**Date:** 2026-05-31
**Phase:** Alpha → Beta Transition

---

## **📋 Executive Summary**
The proposal to introduce **runtime smoke gates** in `scripts/alpha_polish_check.py` was approved with the following mandates:

1. **Core Implementation:** Add 8 runtime smoke gates to verify dynamic module functionali

---

## ⚠️ Difficulties & Constraints

_No specific difficulties extracted — see full report below._

---

## 🔧 Implementation Tasks

> Tick each item off as you complete it in VS Code.
> Update `tasks_completed` in the frontmatter as you go.

### Section A — Implementation

- [x] **[✏️ PLANNER] A1. Add --smoke flag to alpha_polish_check.py**
   - [x] Import argparse at module top
   - [x] Add --smoke flag with default True
   - [x] Add --no-smoke flag for backward compatibility
   - **Acceptance:** --help shows '--smoke' and '--no-smoke' flags, smoke gates run by default
   - **Files:** `scripts/alpha_polish_check.py`

- [x] **[✏️ PLANNER] A2. Implement smoke_role_resolution function**
   - [x] Import get_role_config from src.orchestrator
   - [x] Call get_role_config with 'devlog_scribe'
   - [x] Return GateResult based on model key presence
   - **Acceptance:** smoke_role_resolution passes when it returns a dict with 'model' key
   - **Files:** `scripts/alpha_polish_check.py`

- [x] **[✏️ PLANNER] A3. Register smoke_role_resolution in gate registry**
   - [x] Add the function to the appropriate section of alpha_polish_check.py
   - **Acceptance:** smoke_role_resolution appears in the output when --json is used
   - **Files:** `scripts/alpha_polish_check.py`

- [x] **[✏️ PLANNER] A4. Implement remaining smoke gates S3-S8**
   - [x] smoke_devlog_agent_inst (DevLogAgent instantiation)
   - [x] smoke_devlog_evidence (gather_evidence method)
   - [x] smoke_system_context (build_universal_context)
   - [x] smoke_devlog_config (DevLogConfig.council_role)
   - [x] smoke_path_guard_rejects (PathGuard blocking)
   - [x] smoke_path_guard_allows (PathGuard permitting)
   - **Acceptance:** All 8 smoke gates pass when --smoke flag is used
   - **Files:** `scripts/alpha_polish_check.py`

### Section B — Tests

- [x] **[✏️ PLANNER] B1. Write pytest for smoke_role_resolution**
   - [x] Import necessary modules
   - [x] Set up test to call smoke_role_resolution
   - [x] Assert expected behavior
   - **Acceptance:** pytest confirms smoke_role_resolution passes when it should
   - **Files:** `tests/test_alpha_polish_check.py` (already exists)

- [x] **[✏️ PLANNER] B2. Verify smoke gates work with --json**
   - [x] Smoke gates appear in JSON output
   - [x] All 8 smoke gates have
**Status:** **APPROVED**
**Date:** 2026-05-31
**Phase:** Alpha → Beta Transition

---

## **📋 Executive Summary**
The proposal to introduce **runtime smoke gates** in `scripts/alpha_polish_check.py` was approved with the following mandates:

1. **Core Implementation:** Add 8 runtime smoke gates to verify dynamic module functionality.
2. **Isolation Safety:** Each gate wrapped in `try-except` to prevent system crashes.
3. **Offline Execution:** No GPU/LM Studio dependencies; all gates run locally.
4. **Backward Compatibility:** `--no-smoke` flag restores legacy behavior.
5. **Final Auditor Integration:** Mandatory smoke gate passes for handoff approval.

---

## **🔍 Problem Statement**
Current gates in `alpha_polish_check.py` rely solely on static analysis:
- **File existence checks** miss runtime crashes.
- **Regex scans** fail to validate function behavior.
- **Line-counting** ignores dead code or empty stubs.
- **String searches** overlook runtime exceptions.

**Concrete Example:** The DevLog Agent passed static gates but failed runtime validation due to:
- Incorrect role mapping.
- Empty evidence lists.
- JSON control-character crashes.

---

## **🛠 Solution Overview**
### **8 New Runtime Smoke Gates**
Each gate dynamically imports modules or calls functions, verifying non-empty/non-error results. Gates are self-verifying and run offline.

| Gate # | Name                     | What It Calls                          | Pass Condition                          | Verifies                                  |
|-------|--------------------------|----------------------------------------|----------------------------------------|-------------------------------------------|
| S1    | `smoke_import_core`      | Imports `src.llm_client`, `src.orchestrator`, etc. | All imports succeed.                   | No SyntaxError, no circular imports.       |
| S2    | `smoke_role_resolution`  | `get_role_config("devlog_scribe")`     | Returns dict with `"model"` key.       | Role→model mapping works.                  |
| S3    | `smoke_devlog_agent_inst`| `DevLogAgent(DevLogConfig())`           | Returns without exception.             | Agent constructor doesn’t crash.          |
| S4    | `smoke_devlog_evidence`  | `agent.gather_evidence("2026-05-30")`  | Returns dict with non-empty data.      | Real data flows from disk.                 |
| S5    | `smoke_system_context`   | `build_universal_context()`             | Returns `str` > 200 chars.             | Context builder reads real docs.           |
| S6    | `smoke_devlog_config`    | `DevLogConfig().council_role`          | Equals `"devlog_scribe"`.               | Config YAML loads; default role wired.     |
| S7    | `smoke_path_guard_rejects`| `PathGuard([".private"]).is_forbidden(".private/secret.md")` | Returns `True`. | PathGuard blocks forbidden sources.      |
| S8    | `smoke_path_guard_allows`| `PathGuard([".private"]).is_forbidden("src/main.py")` | Returns `False`. | PathGuard permits allowed paths.         |

---

## **📋 Implementation Plan**
### **Key Changes**
1. **Flag:** Add `--smoke` (default: `True`) and `--no-smoke` for backward compatibility.
2. **Gates:** Implement 8 smoke gates in `alpha_polish_check.py` with `try-except` isolation.
3. **Registry:** Update gate registry and help output to include smoke gates.
4. **Documentation:** Add gates to `dev/quality_gates.md`.

### **Acceptance Criteria (Pre-Implementation)**
| #  | Check                                      | Expected Result (Before Implementation) |
|----|--------------------------------------------|----------------------------------------|
| 1  | `--help` shows `--smoke` flag.             | Flag appears in help output.            |
| 2  | `--smoke` flag is on by default.           | Gates S1–S8 appear in output.           |
| 3  | `--no-smoke` skips all S-gates.             | Only legacy gates appear.               |
| 4  | All 8 smoke gates **PASS**.                | 8/8 green.                              |
| 5  | Legacy gates unchanged.                     | Existing 35 gates still pass.           |
| 6  | Total gates increase (35 → 43).             | 43 gates total.                         |
| 7  | `--json` includes smoke gates.              | JSON output contains `smoke_*` entries.  |
| 8  | Smoke gates survive missing LM Studio.      | All pass offline (no GPU needed).       |

---

## **🎯 Deliberation Process**
### **1. Initial Review (Boardroom)**
**Proposal:** Runtime smoke gates to catch runtime-only bugs.
**Concerns:**
- Static gates are insufficient for runtime integrity.
- Potential for new bugs or performance overhead.

**Resolution:**
- **Board Specialist (qwen3.6-27b-27b):** Technical soundness confirmed. Gates are minimal, self-verifying, and offline.
- **Board Critic (deepseek-r1-distill-qwen-32b):** Risks mitigated via `try-except` isolation.

### **2. Strategic Alignment (Boardroom)**
**Key Levers:**
- Enhanced code quality.
- Improved system reliability.
- Proactive issue detection.

**Veto Points:**
- None. The proposal aligns with strategic goals.

### **3. Aesthetic & Elegance (Boardroom)**
**Board Creative (hermes-4.3-36b-heretic-i1):** Framed gates as an artistic enhancement.
**Design Notes:**
- Minimalistic implementation (130 lines).
- No new dependencies.
- Clean error messaging.

### **4. Logical Validation (Boardroom)**
**Board Logical (gemma-4-31b-it):** Validated the transition from static to functional verification.
**Key Points:**
- **Premise:** Static checks fail to detect runtime bugs.
- **Solution:** 8 gates transition to functional verification.
- **Risk Mitigation:** Isolation prevents system crashes.
- **Complexity:** Linear increase in gates (43 total).

---

## **⚠️ Risks & Mitigations**
| Risk Category       | Risk Description                          | Mitigation Strategy                          |
|---------------------|------------------------------------------|---------------------------------------------|
| **System Crashes**  | A single gate failure could halt the suite. | `try-except` wrapping isolates each gate.   |
| **Performance**     | Smoke gates may slow down execution.      | Gates run in milliseconds; offline execution. |
| **Dependency**      | LM Studio or GPU required.               | No dependencies; gates use existing modules. |

---

## **📋 Final Verdict**
**VERDICT: APPROVED**
**Reasoning:**
The proposal directly addresses a critical gap in runtime integrity verification with a minimal, self-contained solution. It has been rigorously vetted by all board members, with technical risks mitigated via isolation strategies and aesthetic concerns addressed through elegant implementation.

**Next Steps:**
1. Implement gates in `scripts/alpha_polish_check.py`.
2. Run full gate suite in CI to enforce runtime integrity.
3. Update `master_config.md` to require 8/8 smoke gate passes for handoff approval.

---

## **📋 Implementation Roadmap**
### **Phase 1: Core Implementation (2026-05-31 → 2026-06-02)**
- Add `--smoke` flag to `alpha_polish_check.py`.
- Implement S1–S8 gates with `try-except` isolation.
- Update gate registry and help output.

### **Phase 2: CI/CD Integration (2026-06-03 → 2026-06-05)**
- Deploy smoke gates in CI pipelines.
- Enforce runtime integrity checks.

### **Phase 3: Final Auditor Update (2026-06-06)**
- Add SMOKE-GATE VERIFICATION to `master_config.md`.
- Update JSON output schema for smoke gate results.

---

## **📎 Appendices**
### **Appendix A: Example Gate Implementation**
```python
def smoke_role_resolution() -> GateResult:
    """S2: get_role_config('devlog_scribe') returns model key."""
    try:
        from src.orchestrator import get_role_config
        cfg = get_role_config("devlog_scribe")
        model = cfg.get("model")
        return GateResult("smoke_role_resolution", bool(model),
                          f"model={model}" if model else "no model key")
    except Exception as e:
        return GateResult("smoke_role_resolution", False, str(e))
```

### **Appendix B: Final Auditor Prompt Upgrade**
```yaml
      3. SMOKE-GATE VERIFICATION (ARCH-B1D2E3F4)
         If runtime smoke-gate results (gates S1–S8) are included in the handoff, verify
         ALL 8 pass. If smoke gates were skipped or any failed, REJECT.
```

### **Appendix C: Veto Points & Mitigations**
| Veto Point                          | Mitigation Strategy                          |
|-------------------------------------|---------------------------------------------|
| System crashes from gate failures.   | `try-except` isolation for each gate.       |
| Performance overhead.               | Minimal runtime checks; offline execution.   |
| Dependency risks.                   | No new dependencies; uses existing modules. |
| Logical inconsistencies.            | Mandatory smoke gate passes in handoff.     |

---
**End of Report**
```

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
