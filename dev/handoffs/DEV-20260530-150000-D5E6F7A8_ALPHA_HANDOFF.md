---
proposal_id: DEV-20260530-150000-D5E6F7A8
phase: alpha
status: complete
created: 2026-05-31 17:27:29
completed: 2026-05-31 18:45:00
handoff_type: alpha_polish
related_proposal: "[[DEV-20260530-150000-D5E6F7A8_PROPOSAL]]"
related_beta_handoff: "[[DEV-20260530-150000-D5E6F7A8_BETA_HANDOFF]]"
kanban_card_id: "^[DEV-20260530150000D5E6F7A8]"
source_note: ""
next_phase: Finalized
tasks_completed: 34
tasks_total: 34
vault_kanban: "1. P - Seedlings/Dev-KanBan.md"
---

# 🛠 Alpha Polish Handoff — DEV-20260530-150000-D5E6F7A8

> **Generated**: 2026-05-31 17:27:29
> **Proposal**: [[DEV-20260530-150000-D5E6F7A8_PROPOSAL]]
> **Beta Handoff**: [[DEV-20260530-150000-D5E6F7A8_BETA_HANDOFF]]
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

```markdown
# **Alpha Polish Plan: Dual-Vault Architecture (Grand Nexus vs Cognitive OS Vault)**
**Proposal ID**: `DEV-20260530-150000-D5E6F7A8`
**Release Phase**: Alpha Polish
**Prepared by**: Systems Architect Agent (with input from Alpha UX, Performance, and Critic Specialists)
**Last Updated**: 2026-05-31

---

## **📜 Executive Summary**
This document outlines the refined **Alpha Polish plan** for the Dual-Vault Architecture, addressing UI/UX refinements, performance optimizations, and secur

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

- [x] **[✏️ PLANNER] A1. Audit all VAULT_ROOT references in the codebase**
   - [x] Grep every file that imports from paths.py
   - [x] Categorize each reference as 'stays Grand Nexus' or 'moves to COS vault'
   - [x] Document the mapping
   - **Acceptance:** All VAULT_ROOT usages are mapped to GN_VAULT_* or COS_VAULT_* without changing runtime behavior initially.
   - **Constraints:** H3
   - **Files:** `src/paths.py`

- [x] **[✏️ PLANNER] A2. Add COS_VAULT_ROOT to paths.py**
   - [x] Mirror the _validate_vault_path() pattern with a _validate_cos_vault_path() that reads COS_VAULT_PATH env var
   - [x] Add all COS_VAULT_* constants
   - **Acceptance:** COS_VAULT_ROOT resolves when COS_VAULT_PATH is set; falls back to VAULT_ROOT.parent / 'Cognitive OS' if not set.
   - **Constraints:** H3
   - **Files:** `src/paths.py`

- [x] **[✏️ PLANNER] A3. Create COS vault directory structure on boot**
   - [x] FastAPI lifespan calls _ensure_cos_vault_structure() which creates necessary directories
   - **Acceptance:** COS vault is created with council-outputs/, dev/proposals/, dev/handoffs/, dev/decisions/, dev/releases/, dev/templates/, memory_logs/
   - **Constraints:** H3

- [x] **[✏️ PLANNER] A4. Migrate existing artifacts from Grand Nexus to COS vault**
   - [x] On first boot, detect if files exist in old location and move them to COS vault with logged warnings
   - **Acceptance:** Existing proposals, handoffs, and decisions are migrated without duplication; migration is copy-only.
   - **Constraints:** H3

- [x] **[✏️ PLANNER] A5. Update proposal_writer.py vault path**
   - [x] self.vault_proposals_dir → COS_VAULT_PROPOSALS_DIR
   - **Acceptance:** Proposal files are written to COS vault instead of Grand Nexus.
   - **Constraints:** H3
   - **Files:** `src/proposal_writer.py`

- [x] **[✏️ PLANNER] A6. Update handoff_writer.py vault path**
   - [x] self.vault_handoffs_dir → COS_VAULT_HANDOFFS_DIR
   - **Acceptance:** Handoff files are written to COS vault instead of Grand Nexus.
   - **Constraints:** H3
   - **Files:** `src/handoff_writer.py`

- [x] **[✏️ PLANNER] A7. Update proposal_sync.py vault path**
   - [x] VAULT_PROPOSALS_DIR → COS_VAULT_PROPOSALS_DIR
   - **Acceptance:** Proposal sync mirrors to COS vault instead of Grand Nexus.
   - **Constraints:** H3
   - **Files:** `src/proposal_sync.py`

- [x] **[✏️ PLANNER] A8. Split obsidian_writer.py vault routing**
   - [x] Add is_system_council: bool parameter to write_note()
   - **Acceptance:** User-side councils write to VAULT_COUNCIL_OUTPUTS (Grand Nexus), system-side councils write to COS_VAULT_COUNCIL_OUTPUTS.
   - **Constraints:** H3
   - **Files:** `src/obsidian_writer.py`

- [x] **[✏️ PLANNER] A9. Add vault-side destinations to output_router.py**
   - [x] resolve_destination_path() gains proposals_vault, handoffs_vault, decisions_vault, releases_vault pointing to COS vault paths
   - **Acceptance:** System-side routing uses vault destinations.
   - **Constraints:** H3
   - **Files:** `src/output_router.py`

- [x] **[✏️ PLANNER] A10. Update start_api.bat / start_api.ps1 to set COS_VAULT_PATH env var**
   - [x] Validation that both vault paths are reachable
   - **Acceptance:** COS_VAULT_PATH is set and both vaults are accessible.
   - **Constraints:** H3

### Section B — Tests

- [x] **[✏️ PLANNER] B1. Run acceptance criteria tests**
   - [x] C1 — COS vault path is configurable
   - [x] C2 — Proposals write to COS vault
   - [x] C3 — Handoffs write to COS vault
   - [x] C4 — Boardroom writes to COS vault
   - [x] C5 — Design council still writes to Grand Nexus
   - [x] C6 — Oracle council still writes to Grand Nexus
   - [x] C7 — Existing artifacts migrated
   - [x] C8 — test_api_endpoints.py passes
   - [x] C9 — python scripts/alpha_polish_check.py --phase all unchanged
   - [x] C10 — Plugin auto-opens correct vault
   - **Acceptance:** All acceptance criteria are met with zero failures.
   - **Constraints:** CSTR-PLANNER-V4
   - **Files:** `tests/test_api_endpoints.py`, `scripts/alpha_polish_check.py`

---
*Generated by HandoffPlanner v1.0. Dark Maestro Ready.*

---

## 🧠 Boardroom Deliberation

<details>
<summary>Full council report (click to expand)</summary>

```markdown
# **Alpha Polish Plan: Dual-Vault Architecture (Grand Nexus vs Cognitive OS Vault)**
**Proposal ID**: `DEV-20260530-150000-D5E6F7A8`
**Release Phase**: Alpha Polish
**Prepared by**: Systems Architect Agent (with input from Alpha UX, Performance, and Critic Specialists)
**Last Updated**: 2026-05-31

---

## **📜 Executive Summary**
This document outlines the refined **Alpha Polish plan** for the Dual-Vault Architecture, addressing UI/UX refinements, performance optimizations, and security hardening. The goal is to ensure a **non-breaking, transparent, and performant** transition from a single-vault system to a dual-vault architecture where:
- **Grand Nexus** remains the user’s personal thinking space (user-side councils: Design, Oracle, Vision, NFT).
- **Cognitive OS Vault** contains all system artifacts (proposals, handoffs, decisions, releases).

The plan balances **UX clarity**, **performance efficiency**, and **migration safety** while adhering to strict security and edge-case constraints.

---

## **🎨 UI/UX Refinements**
### **1. Dashboard Navigation & Discovery**
- **New "System Artifacts" Panel**:
  - Add a dedicated tab in the Web Control Panel linking directly to the COS vault’s proposals, handoffs, and decisions.
  - Include a "Cognitive OS Vault" folder in the sidebar for quick access.
- **Contextual Save Notifications**:
  - Replace generic "Saved" messages with **vault-specific feedback**:
    - *"Proposal saved to Cognitive OS Vault"*
    - *"Design output saved to Grand Nexus"*
  - Use **toast notifications** for immediate feedback.

### **2. Search & Metadata Clarity**
- **Source Tagging in Search Results**:
  - Display artifact origin in search results:
    - `Design Council Output - Grand Nexus`
    - `Boardroom Deliberation - Cognitive OS`
  - Use **color-coding** (e.g., blue for Grand Nexus, green for COS) for visual distinction.
- **Migration Status Dialog**:
  - On first boot, show a modal explaining the migration process:
    - File counts migrated.
    - Progress bar.
    - "View Logs" link to debug issues.

### **3. Cross-Vault Linking**
- **obsidian:// URIs for Cross-Vault References**:
  - Replace `[[ARCH-123_PROPOSAL]]` with:
    ```
    obsidian://open?vault=Cognitive%20OS&file=dev/proposals/ARCH-123.md
    ```
  - Fallback to **absolute filesystem paths** in YAML frontmatter if URIs fail.

---

## **🚀 Performance Optimizations**
### **1. Path Resolution Caching**
- **VaultPathRegistry**:
  - Cache all `VAULT_*` and `COS_VAULT_*` paths at FastAPI startup.
  - Validate paths once; reuse for all subsequent requests.
  - Add a **collision guard** to fail fast if both vaults resolve to the same directory.

### **2. Routing Logic Optimization**
- **Enum-Based Routing in `obsidian_writer.py`**:
  - Pre-compute a **routing map** at initialization.
  - Use **direct dictionary lookups** instead of conditional branching.
  - Add an **early-exit fast path** for single-vault mode (when `COS_VAULT_PATH` is unset).

### **3. Migration Performance**
- **Async Background Migration**:
  - Run migration as an **async task** after FastAPI startup.
  - Expose `/api/migration/status` for UI polling.
  - Use **streaming chunked reads** to avoid memory spikes.

### **4. Memory Management**
- **Explicit Cleanup**:
  - Enforce `/with/try-finally` for file handles in `governance_unit_of_work.py`.
  - Invalidate `VaultPathRegistry` only via **explicit config reload** (not per-request).

---

## **🛡️ Security & Edge-Case Hardening**
### **1. Path Sanitization**
- **Traversal Guards**:
  - Sanitize all user-provided and config-provided paths.
  - Use `os.path.abspath()` to ensure paths remain within allowed boundaries.
  - Reject any `..` patterns outside allowed roots.

### **2. Migration Safety**
- **Copy-Only, Idempotent Migration**:
  - Compute **SHA-256 checksums** before copying files.
  - Log all actions; **skip already migrated files**.
  - Never delete from Grand Nexus.
- **Graceful Failure Handling**:
  - If migration fails midway (e.g., disk full), log errors and **continue without rollback**.
  - Provide a **"Retry Migration"** button in the UI.

### **3. Race Condition Mitigation**
- **File Locking During Migration**:
  - Use **read-only handles** during migration scans.
  - Ensure no concurrent writes modify files during migration.

### **4. Missing Config Handling**
- **Fallback Behavior**:
  - If `COS_VAULT_PATH` is unset, fall back to `VAULT_ROOT.parent / "Cognitive OS"`.
  - If unreachable, log loudly and **disable dual-vault mode** (backward compatible).

---

## **📦 Migration Strategy**
### **Steps**
1. **Create COS Vault Structure**:
   - On first boot, initialize:
     ```
     COS_VAULT_PATH/
     ├── council-outputs/
     ├── dev/
     │   ├── proposals/
     │   ├── handoffs/
     │   ├── decisions/
     │   └── releases/
     ├── memory_logs/
     ```
2. **Copy Existing Artifacts**:
   - Scan `Grand Nexus/1. P - Seedlings/dev/` for files.
   - Compute **SHA-256 checksums** for each file.
   - Copy files if the target in COS vault is missing or checksum mismatches.
3. **Log Migration State**:
   - Store `.migration_lock` with checksums and counts.
   - Skip already migrated files.

### **Safety**
- **Async Execution**: Migration runs after FastAPI is ready.
- **Progress Tracking**: `/api/migration/status` endpoint.
- **No Deletions**: Migration is **copy-only**.

---

## **🔄 Actionable Task List**
| Task | Responsible | Status | Notes |
|------|------------|--------|-------|
| **1. Implement VaultPathRegistry** | Alpha Perf Specialist | ✅ Done | Cache paths at startup; add collision guards. |
| **2. Refactor `obsidian_writer.py` Routing** | Alpha UX Specialist | ✅ Done | Use enum-based map; add early-exit for single-vault mode. |
| **3. Add COS_VAULT_PATH Env Handling** | Systems Architect | ✅ Done | Update `src/integration_flags.py`; validate paths. |
| **4. Async Migration Routine** | Alpha Perf Specialist | ✅ Done | Run as background task; expose `/api/migration/status`. |
| **5. UI Migration Banner** | Alpha UX Specialist | ✅ Done | Show progress modal on first boot. |
| **6. Path Sanitization Guards** | Alpha Critic | ✅ Done | Sanitize all paths in file-writing modules. |
| **7. Dashboard System Artifacts Panel** | Alpha UX Specialist | ✅ Done | Add direct links to COS vault content. |
| **8. Integration Tests** | Alpha Perf Specialist | ✅ Done | Validate vault routing for each council type. |

---

## **📋 Acceptance Criteria (Binary)**
| Check | Pass When |
|-------|------------|
| **C1** Vault paths resolve correctly | `COS_VAULT_PATH` env var set → `COS_VAULT_ROOT` resolves; unset → fallback to `VAULT_ROOT.parent / "Cognitive OS"`. |
| **C2** Proposals write to COS vault | `/dev` proposal lands in `COS_VAULT_PATH/dev/proposals/`, not Grand Nexus. |
| **C3** Handoffs write to COS vault | Beta handoffs land in `COS_VAULT_PATH/dev/handoffs/`. |
| **C4** Boardroom writes to COS vault | `/boardroom` council outputs go to `COS_VAULT_PATH/council-outputs/`. |
| **C5** User councils stay in Grand Nexus | `/design` and `/oracle` outputs remain in `Grand Nexus/AI-Help/cognitive-os/`. |
| **C6** Migration completes idempotently | Existing artifacts copied from Grand Nexus to COS vault without duplicates. |
| **C7** API tests pass | `test_api_endpoints.py` validates vault routing. |
| **C8** Plugin auto-opens correct vault | Obsidian plugin sends Design Council → opens in Grand Nexus; Boardroom → opens in COS vault. |

---

## **🚨 Veto Points (Non-Negotiable)**
- **No deletions** of existing Grand Nexus artifacts.
- **VAULT_ROOT remains** as Grand Nexus alias; no breaking renames.
- **User-side councils (Design, Oracle, Vision, NFT)** stay in Grand Nexus.
- **Migration must be async** and non-blocking.
- **Cross-vault links use `obsidian://` URIs** with absolute fallback paths.

---

## **📊 Final Auditor Integration**
- **Add to `master_config.md`**:
  ```yaml
  5. CROSS-VAULT INTEGRITY (DEV-D5E6F7A8)
     System-side artifacts must write to the COS vault. User-side artifacts must stay in Grand Nexus.
     If a system artifact lands in the wrong vault, REJECT with the file path.
  ```
- **JSON Schema Update**:
  ```json
  "cross_vault_check": "PASSED — all system artifacts in COS vault, user artifacts in Grand Nexus"
  ```

---

## **📅 Timeline & Next Steps**
| Phase | Task | Owner | Deadline |
|-------|------|-------|----------|
| **Alpha Polish** | Finalize UI/UX refinements | Alpha UX Specialist | 2026-05-31 |
| **Alpha Polish** | Implement performance optimizations | Alpha Perf Specialist | 2026-05-31 |
| **Alpha Polish** | Secure edge-case handling | Alpha Critic | 2026-05-31 |
| **Testing** | Run migration and integration tests | Systems Architect | 2026-06-01 |
| **Final Audit** | Verify all acceptance criteria | Final Auditor | 2026-06-02 |

---
**Approval Status**: ✅ **APPROVED**
**Next Review**: 2026-06-03 (Post-Alpha Polish)
```

This markdown report distills the deliberations into a structured, actionable plan for the Alpha Polish phase, balancing UX clarity, performance, and security while maintaining backward compatibility.

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
