---
proposal_id: ARCH-20260522-161500-A0F1B0C0
phase: beta
status: in_progress
created: 2026-05-22 22:16:31
handoff_type: beta_testing
related_proposal: "[[ARCH-20260522-161500-A0F1B0C0_PROPOSAL]]"
kanban_card_id: ""
source_note: ""
next_phase: Alpha Polish
tasks_completed: 0
tasks_total: 1
vault_kanban: "1. P - Seedlings/Dev-KanBan.md"
---

# 🧪 Beta Testing Handoff — ARCH-20260522-161500-A0F1B0C0

> **Generated**: 2026-05-22 22:16:31  
> **Proposal**: [[ARCH-20260522-161500-A0F1B0C0_PROPOSAL]]  
> **Phase**: Beta Testing  
> **Status**: 🔧 In Progress — take this document to VS Code

---

## 🤖 Agent Context

> *This block is for AI agents (Cline/Claude in VS Code). It is not displayed in Obsidian reading mode.*

When a user references this handoff (e.g. *"work on ARCH-20260522-161500-A0F1B0C0"*):

1. **Find the proposal** → `cognitive-os/dev/proposals/ARCH-20260522-161500-A0F1B0C0_PROPOSAL.md`
2. **Work through the tasks** in `## 🔧 Implementation Tasks` below, ticking each `- [ ]` to `- [x]` as completed
3. **When all tasks are ticked** → update this file's frontmatter: `status: complete`, `tasks_completed: <n>`
4. **Update the proposal** → change `## 🧪 Beta Testing` status line to `✅ Complete`
5. **Update the Kanban card** at `vault_kanban` above → change `  - status: 🔍 Review` to `  - status: ✅ Ready for Alpha Polish`
6. **Tell the user** to drag the card to the `Alpha Polish` column to trigger the next council automatically

Backlinks to maintain:
- Proposal: [[ARCH-20260522-161500-A0F1B0C0_PROPOSAL]]
- Source note: see `source_note` in frontmatter above (if set)
- Kanban card ID: see `kanban_card_id` in frontmatter above

---

## 📋 Executive Summary

```markdown
# **ARCH-20260522-161500-A0F1B0C0: Phase 0 Refactor Proposal**
*A Clean Substrate for Governance Work*
**Proposal ID:** `ARCH-20260522-161500-A0F1B0C0`
**Status:** Boardroom Conditional Approval (v1.1)
**Phase:** Beta Testing

---

## **📋 Summary**
This proposal refactors the monolithic `dev_route.py` (1031 lines) into a modular architecture, addressing three critical structural defects:

1. **Byte-Duplicated Logic**: `_trigger_sync_check()` appears identically in both `dev_route.py`

---

## ⚠️ Difficulties & Constraints

_No specific difficulties extracted — see full report below._

---

## 🔧 Implementation Tasks

> Tick each item off as you complete it in VS Code.
> Update `tasks_completed` in the frontmatter as you go.

- [ ] See full council report below for implementation guidance

---

## 🧠 Technical Council Deliberation

<details>
<summary>Full council report (click to expand)</summary>

```markdown
# **ARCH-20260522-161500-A0F1B0C0: Phase 0 Refactor Proposal**
*A Clean Substrate for Governance Work*
**Proposal ID:** `ARCH-20260522-161500-A0F1B0C0`
**Status:** Boardroom Conditional Approval (v1.1)
**Phase:** Beta Testing

---

## **📋 Summary**
This proposal refactors the monolithic `dev_route.py` (1031 lines) into a modular architecture, addressing three critical structural defects:

1. **Byte-Duplicated Logic**: `_trigger_sync_check()` appears identically in both `dev_route.py` and `kanban_processor.py`.
2. **Hardcoded Vault Paths**: The literal `"E:\\Oranneg\\…\\Grand Nexus"` is hardcoded across three modules.
3. **God-Object Monolith**: `dev_route.py` handles CRUD, Kanban writes, handoff generation, and status updates—violating the Single Responsibility Principle (SRP).

**Goal:** A clean substrate for governance work by:
- Extracting a **sync helper module** (`src/sync_check.py`) to unify `_trigger_sync_check`.
- Creating a **constants module** (`src/paths.py`) for vault paths.
- Splitting `dev_route.py` into three single-responsibility modules: `proposal_writer.py`, `handoff_writer.py`, and a thin façade.

**Key Outcome:** All APIs remain unchanged; only internal structure evolves. The refactor is **behaviour-preserving**.

---

## **🔴 Difficulties & Constraints**
### **Technical Challenges**
1. **Dead-Code Bug in `_trigger_sync_check`**:
   - Original: `str(e) if 'e' in locals() else ...` (unreachable fallback).
   - Fix: Replace with a deterministic error string or logging.

2. **Vault Path Validation (C4)**:
   - Must fail-fast at import time if `OBSIDIAN_VAULT_PATH` is unset AND the fallback directory does not exist.
   - Requires cross-platform path normalization (`pathlib.Path.is_dir()`).

3. **Transition Rules Duplication (C2)**:
   - `kanban_processor.py` defines `transition_rules` twice: once in `__init__`, once via `_load_transition_rules`.
   - Must unify to a single source (JSON override preferred).

4. **Regex-Based YAML Status Updaters (C5, Technical Debt)**:
   - Fragile regex patterns in `dev_route.py` are out of scope for Phase 0 but must be tracked (`ARCH-…-F10FE0E1-DEBT-01`).

### **Operational Constraints**
- **Atomic Merge Requirement (C1)**: Refactor lands as a squashed feature branch, not a single live commit.
- **No Circular Imports (C3)**: Static analysis (`import-linter`) must enforce DAG structure.
- **API Surface Unchanged**: `api.py`’s `DevRouteManager` imports and endpoints must remain identical.

---

## **📋 Implementation Tasks**
### **Core Refactoring Steps**
1. **Create `src/paths.py`** (C4):
   - Define all filesystem constants as `Path` objects.
   - Enforce strict precedence: `OBSIDIAN_VAULT_PATH > hardcoded fallback`.
   - Raise `RuntimeError` if neither is valid.

2. **Extract `sync_check.py`**:
   - Implement `trigger_sync_check()` with deterministic error handling.
   - Replace `_trigger_sync_check` in `dev_route.py` and `kanban_processor.py`.

3. **Split `proposal_writer.py`** (from `dev_route.py`):
   - Methods: `create_proposal`, `_extract_card_title`, `_add_card_to_kanban`, `_get_kanban_template`.
   - Enforce `ProposalCreated` TypedDict contracts.

4. **Split `handoff_writer.py`** (from `dev_route.py`):
   - Methods: `generate_beta_handoff`, `generate_alpha_handoff`, `_extract_section`.
   - Enforce `HandoffArtifact` TypedDict contracts.

5. **Slim `dev_route.py`**:
   - Reduce to < 300 lines; delegate internal logic via façade pattern.
   - Preserve public API for backward compatibility.

6. **Unify `transition_rules`** (C2):
   - Choose `_STATUS_CONFIG.get("transition_rules", {})` or `_load_transition_rules()` as the sole source.
   - Remove duplicate definition entirely.

### **Validation & CI Checks**
7. Run full test suite (`pytest cognitive-os/tests/`).
8. Validate boundary tests for new modules.
9. Enforce static analysis (C3):
   - Use `import-linter` to detect circular imports.
   - Document in `README.md`.

10. **(C1) Atomic Merge**:
    - Develop on feature branch, squash-merge to `main`.
    - Ensure single merge commit with no live commits.

### **Technical Debt Tracking**
11. Append entry to `_tech_debt_register.md`:
    ```
    ID: ARCH-…-F10FE0E1-DEBT-01
    Description: Regex-based YAML status updaters in `dev_route.py`
    Target Proposal: ARCH-20260522-161800-F10FE0E1 (Phase 3+4)
    ```

---

## **🚀 Technical Recommendations**
### **Architecture & Patterns**
- **Single Responsibility Principle (SRP)**: Split `dev_route.py` into three modules (`proposal_writer`, `handoff_writer`, `sync_check`) and a façade.
- **Facade Pattern**: `dev_route.py` acts as a thin wrapper, delegating to specialized workers.
- **Dynamic Module Router** (Optional):
  - Prototype a dispatcher for `dev_route.py` using configuration-based routing.
  - Use adapter pattern for TypedDict serialization/deserialization.

### **Libraries & Tools**
| Purpose                     | Recommended Tool/Library                          |
|------------------------------|----------------------------------------------------|
| Path validation              | `pathlib.Path.is_dir()` + explicit env precedence   |
| Static analysis             | `import-linter` (for DAG contracts)                |
| Type hints                  | `mypy` or `pyright` for runtime validation         |
| CI/CD enforcement            | GitHub Actions / GitLab CI with pylint/import-linter |

### **Key Implementation Notes**
1. **Fail-Fast Vault Paths** (C4):
   - Use `pathlib.Path.is_dir()` to validate existence.
   - Raise `RuntimeError` if `OBSIDIAN_VAULT_PATH` is unset and fallback directory missing.

2. **Dead-Code Fix in `_trigger_sync_check`**:
   - Replace `'e' in locals()` with a deterministic error string or logging.
   - Ensure backward compatibility with existing error reporting.

3. **TypedDict Enforcement**:
   - Add runtime type checks for all module boundaries.
   - Use `typing.get_type_hints()` to validate contracts.

4. **Circular Import Prevention** (C3):
   - Configure `import-linter` to enforce DAG structure.
   - Document in `pyproject.toml` and `README.md`.

5. **Atomic Merge Workflow** (C1):
   - Use Git’s `--squash` flag for clean revertability.
   - Validate merge commit has exactly one parent.

---
## **📋 Summary**
### **System Purpose**
This refactor restructures the monolithic `dev_route.py` (1031 lines) into a modular, single-responsibility architecture to enable future governance/workflow integration. The goal is to eliminate byte-duplication, hardcoded paths, and mixed responsibilities while preserving all existing behavior.

### **Key Outcomes**
- **Modularity**: Split into `paths.py`, `sync_check.py`, `proposal_writer.py`, `handoff_writer.py`, and a thin `dev_route.py` façade.
- **Fail-Fast Paths**: Vault root validation with explicit error handling (no silent fallbacks).
- **Atomic Refactor**: Implemented via feature branch + squash merge for clean revertability.

---
## **🔧 Difficulties & Constraints**
### **Technical Challenges**
1. **Dead Code in `_trigger_sync_check`**: The original bug (`'e' in locals()`) must be fixed without breaking error reporting.
2. **Vault Path Triplication**: Consolidate literals into `paths.py` with strict validation (C4).
3. **Transition Rules Duplication** (C2): Unify source to avoid schema drift.

### **Constraints**
- **No Behavior Changes**: All API endpoints and Kanban automation must work identically.
- **Atomic Merge**: Feature branch squashed on merge for reversible history.
- **Static Analysis**: No circular imports post-split (enforced via `import-linter`).
- **Tech Debt Tracking**: Regex-based status updaters tracked as `ARCH-F10FE0E1-DEBT-01`.

---
## **🛠 Implementation Tasks**
### **Concrete Steps**
1. **Create `paths.py`** (C4):
   - Validate vault path with `pathlib.Path.is_dir()`; raise `RuntimeError` if invalid.
2. **Extract `sync_check.py`**:
   - Fix `_trigger_sync_check` dead code and centralize logic.
3. **Split `proposal_writer.py`**:
   - Move `create_proposal`, `_extract_card_title`, etc., with TypedDict contracts.
4. **Split `handoff_writer.py`**:
   - Extract handoff generation helpers; enforce `HandoffArtifact`.
5. **Thin `dev_route.py`**:
   - Delegate to new modules; ensure ≤ 300 lines and no API changes.
6. **Unify `transition_rules`** (C2):
   - Choose Python defaults or JSON override; remove duplicate source.
7. **Static Analysis** (C3):
   - Configure `import-linter` for DAG validation in CI.
8. **Tech Debt Entry**:
   - Add regex updaters to `_tech_debt_register.md`.

### **Additional Boardroom Requirements**
- Squash merge into atomic commit (`feat/arch-A0F1B0C0-phase0-refactor`).
- Run full test suite + boundary checks for new modules.

---
## **⚡ Technical Recommendations**
### **Architecture & Patterns**
- **Facade Pattern**: `dev_route.py` as a thin façade delegating to specialized workers.
- **Dynamic Dispatch Alternative** (optional):
  - Prototype a *Dynamic Module Router* with TypedDict adapters for non-breaking extensibility.
- **Strict Validation**:
  - Use `pathlib.Path` for filesystem operations; enforce fail-fast in `paths.py`.

### **Libraries & Tools**
| Purpose               | Tool/Library                          |
|-----------------------|---------------------------------------|
| Static Analysis       | `import-linter` (DAG contract)        |
| Type Safety           | Python TypedDict + `@dataclass`       |
| Path Validation       | `pathlib.Path.is_dir()`              |
| CI Enforcement        | GitHub Actions / GitLab CI            |

### **Key Trade-offs**
- **Facade vs. Dynamic Dispatch**:
  - Static façade is simpler; dynamic dispatch enables future extensibility.
- **Error Handling**:
  - Replace `'e' in locals()` with deterministic error strings or logging.

---
## **📋 Summary of Deliberation & Outcome**
### **Deliberation Highlights**
1. **Modularity Focus**: SRP and façade patterns were validated for decoupling the monolith.
2. **Critical Risks Addressed**:
   - Dead code in `_trigger_sync_check` (fixed via `sync_check.py`).
   - Silent path failures (enforced via `RuntimeError` in `paths.py`).
3. **Boardroom Conditions Met**:
   - Atomic merge requirement (`--squash`) implemented.
   - Circular imports prevented via static analysis.
4. **Technical Debt Mitigation**:
   - Regex updaters tracked as `ARCH-…-F10FE0E1-DEBT-01`.

### **Definitive Outcome**
**Approved with Conditions**: The refactor is **conditionally approved** under the following constraints:
- **Core Refactoring**: Extract `sync_check.py`, `paths.py`, and split `dev_route.py` into `proposal_writer.py`/`handoff_writer.py`.
- **Fail-Fast Paths**: Enforce `RuntimeError` for missing vault roots (C4).
- **Atomic Merge**: Squash commit to preserve revertability.
- **Static Analysis**: Prevent circular imports via `import-linter`.

**Next Steps**:
1. Implement the refactor with the dynamic module router prototype as an optional enhancement.
2. Resolve technical debt (`regex updaters`) in Phase 3+4.
3. Validate all acceptance criteria before merging.

---
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
