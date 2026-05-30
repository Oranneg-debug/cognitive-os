---
proposal_id: ARCH-20260529-100228-096CEDAF
phase: beta
status: in_progress
created: 2026-05-30 01:38:49
handoff_type: beta_testing
related_proposal: "[[ARCH-20260529-100228-096CEDAF_PROPOSAL]]"
kanban_card_id: "^[ARCH-20260529100228-096CEDAF]"
source_note: ""
next_phase: Alpha Polish
tasks_completed: 0
tasks_total: 20
vault_kanban: "1. P - Seedlings/Dev-KanBan.md"
---

# 🧪 Beta Testing Handoff — ARCH-20260529-100228-096CEDAF

> **Generated**: 2026-05-30 01:38:49  
> **Proposal**: [[ARCH-20260529-100228-096CEDAF_PROPOSAL]]  
> **Phase**: Beta Testing  
> **Status**: 🔧 In Progress — take this document to VS Code

---

## 🤖 Agent Context

> *This block is for AI agents (Cline/Claude in VS Code). It is not displayed in Obsidian reading mode.*

When a user references this handoff (e.g. *"work on ARCH-20260529-100228-096CEDAF"*):

1. **Find the proposal** → `cognitive-os/dev/proposals/ARCH-20260529-100228-096CEDAF_PROPOSAL.md`
2. **Work through the tasks** in `## 🔧 Implementation Tasks` below, ticking each `- [ ]` to `- [x]` as completed
3. **When all tasks are ticked** → update this file's frontmatter: `status: complete`, `tasks_completed: <n>`
4. **Update the proposal** → change `## 🧪 Beta Testing` status line to `✅ Complete`
5. **Update the Kanban card** at `vault_kanban` above → change `  - status: 🔍 Review` to `  - status: ✅ Ready for Alpha Polish`
6. **Tell the user** to drag the card to the `Alpha Polish` column to trigger the next council automatically

Backlinks to maintain:
- Proposal: [[ARCH-20260529-100228-096CEDAF_PROPOSAL]]
- Source note: see `source_note` in frontmatter above (if set)
- Kanban card ID: see `kanban_card_id` in frontmatter above

---

## 📋 Executive Summary

```markdown
---
# **Cognitive-OS Spec-Kit Integration: Engineering Plan**
**Version**: 1.0
**Date**: 2026-05-30
**Author**: Systems Architect (Distilled by DeepSeek)
**Status**: Approved (with safeguards)
**Phase**: Backlog → Implementation
---

# **📜 Executive Summary**
This engineering plan outlines the technical implementation of **spec-kit as a presentation layer** for the Cognitive-OS governance engine. The integration enables developers to interact with the system via slash commands (`/spe

---

## ⚠️ Difficulties & Constraints

_No specific difficulties extracted — see full report below._

---

## 🔧 Implementation Tasks

> Tick each item off as you complete it in VS Code.
> Update `tasks_completed` in the frontmatter as you go.

### Section A — Phase 1 - Install & Integrate

- [ ] **[✏️ PLANNER] A1. Install spec-kit CLI**
   - [ ] Run `uv tool install specify-cli --from git+https://github.com/github/spec-kit.git`
   - **Acceptance:** Spec-kit CLI is installed and slash commands appear in VS Code.
   - **Constraints:** CSTR-SPECKIT-V1

- [ ] **[✏️ PLANNER] A2. Create `/speckit.constitution` mapping**
   - [ ] Read `master_config.md` and `.clinerules/` for governing principles.
   - [ ] Generate a `.specify/constitution.md` reflecting Dark Maestro governance.
   - **Acceptance:** .specify/constitution.md is generated with appropriate governance details.
   - **Constraints:** CSTR-SPECKIT-V1

- [ ] **[✏️ PLANNER] A3. Map spec-kit commands to cognitive-os primitives**
   - [ ] Implement command files for `/speckit.specify`, `/speckit.plan`, `/speckit.tasks`, and `/speckit.implement`.
   - [ ] Ensure these commands call the corresponding cognitive-os functions.
   - **Acceptance:** Spec-kit slash commands are functional, mapping to correct cognitive-os primitives.
   - **Constraints:** CSTR-SPECKIT-V1, H3
   - **Files:** `.specify/commands/speckit.specify.md`, `.specify/commands/speckit.plan.md`, `.specify/commands/speckit.tasks.md`, `.specify/commands/speckit.implement.md`

- [ ] **[✏️ PLANNER] A4. Add spec-kit origin to proposal schema**
   - [ ] Modify `ValidatedProposal` model to include `origin: "spec-kit"`.
   - [ ] Update the dashboard to display spec-kit proposals with a distinct icon/badge.
   - **Acceptance:** Proposals originating from spec-kit are marked correctly, and appear on the dashboard.
   - **Constraints:** CSTR-SPECKIT-V3, H1
   - **Files:** `src/models/proposal.py`

### Section B — Phase 2 - Antigravity Preset

- [ ] **[✏️ PLANNER] B1. Build and publish `antigravity-preset`**
   - [ ] Override spec-kit templates with Dark Maestro governance.
   - [ ] Ship the preset as an extension to the spec-kit community registry.
   - **Acceptance:** The `antigravity-preset` is published and can be installed via `specify preset add antigravity`.
   - **Constraints:** CSTR-SPECKIT-V2

- [ ] **[✏️ PLANNER] B2. Preset contents**
   - [ ] Create templates for `spec-template.md`, `plan-template.md`, and `tasks-template.md`.
   - [ ] Implement custom slash commands in the `.specify/commands/` directory.
   - **Acceptance:** Preset includes all necessary governance overrides and custom commands.
   - **Constraints:** CSTR-SPECKIT-V2
   - **Files:** `.specify/presets/antigravity/templates/`, `.specify/presets/antigravity/commands/`

### Section C — Phase 3 - Dashboard Integration

- [ ] **[✏️ PLANNER] C1. Spec-kit tab in dashboard**
   - [ ] Design and implement the spec-kit tab on the dashboard.
   - [ ] Show active specs, their phase, linked proposals, and `/speckit.analyze` results.
   - **Acceptance:** The spec-kit tab is functional, providing a clear view of spec-kit activities on the dashboard.
   - **Constraints:** CSTR-SPECKIT-V1, H2
   - **Files:** `src/dashboard/views.py`

---
*Generated by HandoffPlanner v1.0. Dark Maestro Ready.*

---

## 🧠 Technical Council Deliberation

<details>
<summary>Full council report (click to expand)</summary>

```markdown
---
# **Cognitive-OS Spec-Kit Integration: Engineering Plan**
**Version**: 1.0
**Date**: 2026-05-30
**Author**: Systems Architect (Distilled by DeepSeek)
**Status**: Approved (with safeguards)
**Phase**: Backlog → Implementation
---

# **📜 Executive Summary**
This engineering plan outlines the technical implementation of **spec-kit as a presentation layer** for the Cognitive-OS governance engine. The integration enables developers to interact with the system via slash commands (`/speckit.specify`, `/speckit.plan`, etc.) while preserving the Cognitive-OS’s core governance pipeline. The plan includes:
- **CLI Integration**: Installing spec-kit and mapping commands to Cognitive-OS primitives.
- **Antigravity Preset**: Customizing spec-kit templates with Dark Maestro governance aesthetics.
- **Dashboard Integration**: Visualizing spec-kit proposals alongside existing workflows.
- **Safeguards**: Preventing governance bypass, ensuring gate compatibility, and mitigating upgrade risks.

---

# **🔧 Technical Overview**
### **Core Architecture**
The system follows a **strictly decoupled** design:
- **spec-kit** = User-facing CLI/markdown prompts (read-only).
- **Cognitive-OS** = Backend engine (proposals, councils, handoffs, execution).
- **Bridge Module** (`src.speckit_bridge.py`) = Single entry point for spec-kit commands.

### **Key Components**
| Component               | Purpose                                                                 | Files/Modules                          |
|-------------------------|-------------------------------------------------------------------------|----------------------------------------|
| **spec-kit CLI**        | User interface for slash commands.                                       | `specify init cognitive-os`            |
| **Command Mapping**     | Maps spec-kit commands to Cognitive-OS primitives.                       | `src.speckit_bridge.py`                |
| **Antigravity Preset**  | Custom templates and prompts for Dark Maestro governance.               | `.specify/presets/antigravity/`        |
| **Dashboard Tab**       | Visualizes spec-kit proposals in the Cognitive-OS dashboard.            | `dashboard/spec-kit-tab.js`           |
| **Gate Wrapper**        | Ensures `/speckit.analyze` integrates cleanly with `alpha_polish_check.py`. | `src.gate_wrapper.py`                  |

---

# **📋 Implementation Phases**
## **Phase 1: CLI & Command Mapping**
### **Deliverables**
1. **Install spec-kit CLI**
   - Install via `uv tool install specify-cli --from git+https://github.com/github/spec-kit.git`.
   - Initialize Cognitive-OS integration: `specify init cognitive-os --integration copilot`.

2. **Create `src.speckit_bridge.py`**
   - **Functionality**:
     - Receives markdown prompts from spec-kit slash commands.
     - Validates input via `ProposalValidator`.
     - Routes to Cognitive-OS primitives:
       - `/speckit.specify` → `ProposalWriter.create_proposal(origin="spec-kit")`.
       - `/speckit.plan` → `CouncilRunner.run(phase="TechnicalMeeting", scope="architecture")`.
       - `/speckit.tasks` → `HandoffPlanner.generate_tasks(proposal_id)`.
       - `/speckit.implement` → `HandoffExecutor.generate_beta_handoff(proposal_id)`.
   - **Security**:
     - Runs in a constrained environment with explicit allowlists for file writes/execs.
     - Logs all requests to `src.approval_logger` with `origin: spec-kit` metadata.

3. **Map spec-kit commands to Cognitive-OS**
   | spec-kit command | Cognitive-OS Primitive                          | Notes                                  |
   |-------------------|-------------------------------------------------|----------------------------------------|
   | `/speckit.specify` | `ProposalWriter.create_proposal`               | Adds `origin: spec-kit` to proposal.   |
   | `/speckit.plan`    | `CouncilRunner.run(phase="TechnicalMeeting")`   | Fast-tracked to Phase 1.              |
   | `/speckit.tasks`   | `HandoffPlanner.generate_tasks`                | Uses HandoffPlanner (`5DFB393F`).      |
   | `/speckit.implement`| `HandoffExecutor.generate_beta_handoff`       | Requires `APPROVED` status.           |
   | `/speckit.analyze` | `GateWrapper.run_analyze(proposal_id)`         | Calls `alpha_polish_check.py`.        |

---

## **Phase 2: Antigravity Preset**
### **Deliverables**
1. **Customize spec-kit templates**
   - Override default templates with Dark Maestro governance aesthetics:
     - `.specify/presets/antigravity/templates/spec-template.md` → Gothic prompt structure.
     - `.specify/presets/antigravity/templates/plan-template.md` → Council-aware planning.
     - `.specify/presets/antigravity/templates/tasks-template.md` → HandoffPlanner format.

2. **Add custom slash commands**
   - `/speckit.symbolize` → Generates occult-inspired design motifs (e.g., glyphs for project scope).
   - `/speckit.council` → Directs to the Technical Meeting council with Dark Maestro prompts.

3. **Publish to spec-kit registry**
   - Package as `antigravity-preset` with:
     - Installation command: `specify preset add antigravity`.
     - Includes `Occult Prompt Weaving` utility for dynamic prompt injection.

---

## **Phase 3: Dashboard Integration**
### **Deliverables**
1. **spec-kit tab in dashboard**
   - Visualizes:
     - Active spec-kit proposals with phase status.
     - Cross-references tasks with Kanban cards.
     - Displays `/speckit.analyze` gate results.
   - **UI Design**:
     - Gothic architecture blueprints for spec-kit proposals.
     - Illuminated manuscript-style annotations for council verdicts.

2. **Proposal provenance**
   - All spec-kit proposals show `origin: spec-kit` in the dashboard.
   - Badge/icon for spec-kit proposals to distinguish them.

---

# **⚠️ Safeguards & Constraints**
### **1. Governance Bypass Prevention**
- **API Contracts**: All requests from `src.speckit_bridge.py` must include `origin: spec-kit` and route through `src.council_runner`.
- **Audit Logging**: Logs all bridge requests to `src.approval_logger` with timestamps and approval status.
- **Veto Points**:
  - **VETO**: Any implementation that allows `/speckit.implement` to bypass council approval.
  - **VETO**: Direct modification of `alpha_polish_check.py` internals.

### **2. Gate Compatibility**
- **JSON-RPC Wrapper**: `/speckit.analyze` calls `src.gate_wrapper.py`, which ensures compatibility with `alpha_polish_check.py`.
- **No Breaking Changes**: Preset and CLI are versioned independently to handle spec-kit upgrades.

### **3. Preset Maintenance**
- **Low Burden**: Preset is mostly template overrides; no code changes required unless spec-kit evolves.
- **Dynamic Prompts**: `Occult Prompt Weaving` system injects Sovereign Compass directives into prompts.

---

# **📝 Risk Mitigation**
| Risk                          | Mitigation Strategy                                                                 |
|-------------------------------|------------------------------------------------------------------------------------|
| Governance bypass             | Explicit API contracts + audit logging.                                            |
| Gate incompatibility          | JSON-RPC wrapper for `alpha_polish_check.py`.                                     |
| Preset upgrade conflicts      | Versioned preset and CLI.                                                          |
| Occult symbolism drift        | Centralized `Occult Prompt Weaving` system.                                         |

---

# **📅 Timeline & Dependencies**
| Phase       | Task                                      | Owner               | Deadline          |
|-------------|-------------------------------------------|---------------------|-------------------|
| **1**       | Install spec-kit CLI                       | Systems Architect   | 2026-05-31        |
| **2**       | Develop `src.speckit_bridge.py`           | Systems Architect   | 2026-06-05        |
| **3**       | Build Antigravity Preset                   | Creative Expansionist | 2026-06-10       |
| **4**       | Dashboard spec-kit tab                     | Tech Board          | 2026-06-15        |
| **5**       | Alpha Testing                               | Editor Agent (Cline) | 2026-06-20        |
| **6**       | Beta Polish                                | Beta Council        | 2026-06-25        |

**Dependencies**:
- Phase 5 (production wiring) complete.
- DevLog Agent operational (`78D36EDB`).
- HandoffPlanner (`5DFB393F`) wired to `/speckit.tasks`.

---

# **🎨 Aesthetic & Brand Integration**
### **Occult Prompt Weaving**
- **Dynamic Prompts**: Injects Dark Maestro’s Sovereign Compass directives into spec-kit prompts.
  Example:
  ```markdown
  # /speckit.specify "Build a photo album app"
  **Prompt**: "This spec must embody the Sovereign Compass’s principle of 'Gothic Precision.' Use occult symbols to represent the app’s core functions (e.g., a 'Photonic Glyph' for image storage)."
  ```

### **Governance Mosaic Dashboard**
- Visualizes spec-kit proposals as **gothic architecture blueprints**:
  - Proposal phases = "Foundational Stone," "Architectural Frame," "Illuminated Manuscript."
  - Council verdicts = "Sealed with Blood" (approved) or "Cursed by the Council" (rejected).

---

# **🔧 Technical Files**
| File                          | Purpose                                                                 |
|-------------------------------|-------------------------------------------------------------------------|
| `src/speckit_bridge.py`       | Maps spec-kit commands to Cognitive-OS primitives.                       |
| `src/gate_wrapper.py`         | Ensures `/speckit.analyze` integrates with `alpha_polish_check.py`.    |
| `src/approval_logger.py`      | Logs all spec-kit requests with `origin: spec-kit`.                     |
| `.specify/presets/antigravity/`| Custom templates and prompts for Dark Maestro governance.               |
| `dashboard/spec-kit-tab.js`   | Visualizes spec-kit proposals in the dashboard.                         |

---

# **📋 Appendix: Deliberation History**
### **Key Discussions**
1. **Systems Architect (2026-05-30)**
   - Proposed a **strictly decoupled** design with a bridge module.
   - Highlighted the need for **explicit API contracts** to prevent governance bypass.

2. **Creative Expansionist (2026-05-30)**
   - Proposed **Occult Prompt Weaving** and **Governance Mosaic** dashboard.
   - Emphasized aligning spec-kit with Dark Maestro’s aesthetic and governance ethos.

3. **Technical Critic (2026-05-30)**
   - **Vetoed** due to:
     - Lack of **specific safeguards** against governance bypass.
     - **Undefined compatibility** for `/speckit.analyze` and `alpha_polish_check.py`.
   - **Brand Guard Rejected** with **high-risk veto points**.

4. **Final Approval (2026-05-30)**
   - **Veto Points Implemented**:
     - Explicit API contracts + audit logging.
     - JSON-RPC wrapper for gate compatibility.
   - **Brand Guard Approved** with **aesthetic enhancements** integrated.

---
**End of Report**
```

---
This markdown report distills the proposal into a structured, actionable engineering plan while preserving the aesthetic, governance, and technical safeguards discussed during deliberation.

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
