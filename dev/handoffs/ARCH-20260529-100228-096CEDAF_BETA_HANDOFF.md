---
proposal_id: ARCH-20260529-100228-096CEDAF
phase: beta
status: in_progress
created: 2026-05-31 06:14:43
handoff_type: beta_testing
related_proposal: "[[ARCH-20260529-100228-096CEDAF_PROPOSAL]]"
kanban_card_id: "^[ARCH-20260529100228-096CEDAF]"
source_note: ""
next_phase: Alpha Polish
tasks_completed: 0
tasks_total: 21
vault_kanban: "1. P - Seedlings/Dev-KanBan.md"
---

# 🧪 Beta Testing Handoff — ARCH-20260529-100228-096CEDAF

> **Generated**: 2026-05-31 06:14:43  
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
title: "ARCH-20260529-100228-096CEDAF: Spec-Kit Integration Engineering Plan"
author: Systems Architect (Beta Council)
date: 2026-05-31
version: "1.0"
status: approved
---

# **Spec-Kit Integration Engineering Plan**
*Transforming Cognitive-OS Governance into a Developer-Friendly CLI Workflow*

---

## **📜 Executive Summary**
This engineering plan outlines the integration of **GitHub's Spec-Kit** as a **presentation layer** for the Cognitive-OS governance pipeline. The goal is to

---

## ⚠️ Difficulties & Constraints

_No specific difficulties extracted — see full report below._

---

## 🔧 Implementation Tasks

> Tick each item off as you complete it in VS Code.
> Update `tasks_completed` in the frontmatter as you go.

### Section A — CLI Installation & Integration

- [ ] **[✏️ PLANNER] A1. Install spec-kit CLI with version lock**
   - [ ] uv tool install specify-cli --from git+https://github.com/github/spec-kit.git
   - [ ] specify init cognitive-os --integration copilot
   - **Acceptance:** Pinned spec-kit CLI with version lock and slash commands appear in VS Code
   - **Constraints:** CSTR-SPECKIT-V1

- [ ] **[✏️ PLANNER] A2. Create /speckit.constitution mapping**
   - [ ] Read master_config.md + .clinerules/ for governing principles
   - [ ] Produce a .specify/constitution.md that reflects Dark Maestro governance
   - **Acceptance:** A .specify/constitution.md is produced reflecting Dark Maestro governance
   - **Constraints:** CSTR-SPECKIT-V1
   - **Files:** `.specify/templates/constitution.md`

- [ ] **[✏️ PLANNER] A3. Map spec-kit commands to cognitive-os primitives**
   - [ ] /speckit.specify → ProposalWriter.create_proposal(origin='spec-kit')
   - [ ] /speckit.plan → Technical Meeting council (Phase 1)
   - [ ] /speckit.tasks → HandoffPlanner integration
   - [ ] /speckit.implement → Beta handoff → Cline pipeline
   - [ ] /speckit.analyze → alpha_polish_check.py compatibility
   - **Acceptance:** All spec-kit commands map correctly to cognitive-os primitives and flow through the governance pipeline
   - **Constraints:** CSTR-SPECKIT-V1
   - **Files:** `.specify/commands/speckit.specify.md`, `.specify/commands/speckit.plan.md`, `.specify/commands/speckit.tasks.md`, `.specify/commands/speckit.implement.md`

- [ ] **[✏️ PLANNER] A4. Add spec-kit origin to proposal schema**
   - [ ] origin: 'spec-kit' added to ValidatedProposal model
   - [ ] Dashboard shows spec-kit proposals with distinct icon/badge
   - **Acceptance:** All proposals from spec-kit carry the origin flag and flow through the standard lifecycle
   - **Constraints:** CSTR-SPECKIT-V3
   - **Files:** `src/models/proposal.py`

### Section B — Antigravity Preset

- [ ] **[✏️ PLANNER] B1. Build and publish antigravity-preset**
   - [ ] Overrides spec-kit's default templates with Dark Maestro governance
   - [ ] Ships the council prompt chain as a preset extension
   - **Acceptance:** Antigravity Preset is published to the community registry and can be installed via specify preset add antigravity
   - **Constraints:** CSTR-SPECKIT-V1
   - **Files:** `.specify/presets/antigravity/templates/`, `.specify/presets/antigravity/commands/`

### Section C — Dashboard Integration

- [ ] **[✏️ PLANNER] C1. Spec-kit tab in dashboard**
   - [ ] Shows active specs, their phase, linked proposals
   - [ ] Cross-references spec-kit task lists with Kanban cards
   - **Acceptance:** A spec-kit tab is integrated into the dashboard showing all relevant information

---
*Generated by HandoffPlanner v1.0. Dark Maestro Ready.*

---

## 🧠 Technical Council Deliberation

<details>
<summary>Full council report (click to expand)</summary>

```markdown
---
title: "ARCH-20260529-100228-096CEDAF: Spec-Kit Integration Engineering Plan"
author: Systems Architect (Beta Council)
date: 2026-05-31
version: "1.0"
status: approved
---

# **Spec-Kit Integration Engineering Plan**
*Transforming Cognitive-OS Governance into a Developer-Friendly CLI Workflow*

---

## **📜 Executive Summary**
This engineering plan outlines the integration of **GitHub's Spec-Kit** as a **presentation layer** for the Cognitive-OS governance pipeline. The goal is to replace manual proposal filing (Obsidian + Kanban drag-and-drop) with **slash commands** (`/speckit.specify`, `/speckit.plan`, etc.) that directly invoke Cognitive-OS primitives while preserving all governance constraints.

**Key Outcomes:**
- Developers can now file proposals via `/speckit.specify` → automatically routed to council, with handoffs generated via `/speckit.tasks` and `/speckit.implement`.
- An **Antigravity Preset** provides Dark Maestro governance templates and council prompt chains.
- Dashboard integration shows spec-kit-originated proposals alongside traditional ARCH/DEV/NLST workflows.
- **Security and determinism** are enforced via a hardened `speckit_bridge.py` module.

---

## **🔧 Core Components**
| Component               | Purpose                                                                 | Files/Modules                                                                 |
|-------------------------|-------------------------------------------------------------------------|-------------------------------------------------------------------------------|
| **spec-kit CLI**        | Standardized CLI for Spec-Driven Development.                           | `uv tool install specify-cli`                                                 |
| **speckit_bridge.py**   | Secure adapter module mapping slash commands to Cognitive-OS primitives. | New Python module (100+ LOC)                                                 |
| **Antigravity Preset**  | Dark Maestro governance templates for spec-kit.                         | `specify preset add antigravity`                                              |
| **Dashboard Integration**| Sync spec-kit proposals with internal Kanban/Kanban cards.              | Custom tab in dashboard (200+ LOC)                                          |

---

## **📋 Phase Breakdown**
### **Phase 1: CLI & Bridge Integration (Critical Path)**
1. **Install spec-kit CLI**
   - Pin version to avoid drift.
   - Verify slash commands appear in VS Code.

2. **Define `speckit_bridge.py` Interface**
   - **Input Schema**: Structured markdown prompts (e.g., YAML frontmatter for metadata).
   - **Execution Model**: Deterministic CLI/MCP contract (no LLM ambiguity).
   - **Security Hardening**: Explicit allowlists for filesystem/network access.

3. **Map Commands to Cognitive-OS**
   | spec-kit command | Cognitive-OS Primitive                     | Notes                                                                 |
   |-------------------|--------------------------------------------|-----------------------------------------------------------------------|
   | `/speckit.specify` | `ProposalWriter.create_proposal()`         | `origin: "spec-kit"` added to schema.                                  |
   | `/speckit.plan`    | Technical Meeting council (Phase 1)        | `--scope architecture` flag.                                           |
   | `/speckit.tasks`   | HandoffPlanner (`5DFB393F`)               | Council-aware task generation.                                        |
   | `/speckit.implement`| Beta handoff → Cline pipeline             | Preserves human approval gates.                                         |
   | `/speckit.analyze` | `alpha_polish_check.py`                   | Gate verification compatible with existing system.                      |
   | `/speckit.clarify` | Fast-track boardroom review              | Single-round, low-friction review.                                     |

4. **State Synchronization**
   - Embed **internal proposal/Kanban IDs** in `.specify/` artifacts via:
     - Standardized headers (e.g., `--- proposal_id: ARCH-12345 ---`).
     - Webhook callbacks for bidirectional traceability.

---

### **Phase 2: Antigravity Preset**
1. **Build Preset Package**
   - Override spec-kit templates with Dark Maestro governance:
     - `spec-template.md` → Dark aesthetic prompts.
     - `plan-template.md` → Council-aware planning.
     - `tasks-template.md` → HandoffPlanner format.
   - Include custom slash commands (`/council`, `/devlog`).

2. **Publish to Community Registry**
   - `specify preset add antigravity` installable via:
     ```bash
     specify preset add https://github.com/your-repo/antigravity-preset.git
     ```

---

### **Phase 3: Dashboard Integration**
1. **Spec-Kit Tab**
   - Display:
     - Active specs with phase status.
     - Cross-referenced Kanban cards.
     - `/speckit.analyze` gate results.

2. **Provenance Preservation**
   - All spec-kit proposals carry `origin: "spec-kit"` in the database.
   - Dashboard icons/badges distinguish spec-kit workflows.

---

## **🛡️ Binding Constraints (CSTR-SPECKIT)**
| Constraint ID | Description                                                                 | Enforcement Mechanism                          |
|---------------|-----------------------------------------------------------------------------|-----------------------------------------------|
| CSTR-SPECKIT-V1 | spec-kit is a UX layer, not the engine.                                    | No direct API changes; CLI only calls primitives. |
| CSTR-SPECKIT-V2 | No autopost tie-in; `/speckit.implement` respects human gates.              | DevLog Agent remains separate.               |
| CSTR-SPECKIT-V3 | Proposals originate from spec-kit but flow through standard lifecycle.      | `origin: "spec-kit"` metadata preserved.       |
| CSTR-SPECKIT-V4 | `/speckit.analyze` uses `alpha_polish_check.py`; no competing gates.       | Compatibility check script added.             |

---

## **🔍 Technical Risks & Mitigations**
| Risk                          | Mitigation Strategy                                                                 |
|-------------------------------|-----------------------------------------------------------------------------------|
| **Security Vulnerabilities**  | `speckit_bridge.py` runs in sandboxed environment with strict allowlists.          |
| **Data Drift**                | Metadata linking (headers/webhooks) ensures traceability.                          |
| **Deterministic Execution**   | MCP/CLI contract replaces LLM ambiguity.                                         |
| **Provenance Loss**           | `origin: "spec-kit"` flag embedded in all artifacts.                              |

---

## **📝 Implementation Roadmap**
| Task                          | Owner               | Deadline       | Status       |
|-------------------------------|---------------------|----------------|--------------|
| Draft `speckit_bridge.py` spec | Systems Architect   | 2026-05-31     | Approved     |
| Implement bridge module        | Editor Agent (Cline)| 2026-06-05     | In Progress  |
| Build Antigravity Preset       | Creative Expansionist| 2026-06-10     | In Progress  |
| Dashboard spec-kit tab         | Tech Board          | 2026-06-15     | Pending      |
| Beta Testing                  | Developer Community | 2026-06-20     | Planned      |

---

## **🎨 Creative Expansionist’s Vision (Optional Enhancements)**
While core requirements are met, the following **aesthetic/ritualistic** integrations could be explored:
1. **Dynamic Council Prompt Chaining**
   - Use ComfyUI’s canvas reader to analyze developer sentiment from slash commands and adjust council prompt weights (e.g., emphasize technical rigor vs. aesthetic innovation).
2. **Dark Realism Telemetry**
   - Embed contrast/symbolism principles into proposal validation (e.g., proposals scoring low on "visual impact" route to a "design polish" council round).
3. **Ritualistic Handoffs**
   - Transform `/speckit.implement` into a multi-step artistic ritual where Cline’s handoff includes mandatory dark-themed imagery generation before code execution.

**Note:** These enhancements are **non-critical** to core functionality but could enhance user experience.

---

## **📋 Final Verdict & Approval**
**Decision:** **APPROVED**
**Rationale:**
The proposal correctly positions spec-kit as a **deterministic, secure presentation layer** over the existing governance engine. Key risks (security, data drift, governance integrity) are addressed via:
- A hardened `speckit_bridge.py` with strict allowlists.
- Metadata linking to preserve provenance.
- Deterministic execution contracts (MCP/CLI).

**Next Steps:**
1. Draft and approve `speckit_bridge.py` interface specification.
2. Implement Phase 1 wiring (CLI + bridge).
3. Proceed to Phase 2 (Preset) and Phase 3 (Dashboard).

---
```json
{
  "engineering_plan": {
    "components": {
      "cli": {
        "installation": "Pinned spec-kit CLI with version lock",
        "commands": {
          "specify": "ProposalWriter.create_proposal(origin='spec-kit')",
          "plan": "Technical Meeting council (Phase 1)",
          "tasks": "HandoffPlanner integration",
          "implement": "Beta handoff → Cline pipeline",
          "analyze": "alpha_polish_check.py compatibility"
        }
      },
      "bridge": {
        "spec": "Deterministic CLI/MCP contract with allowlists",
        "security": "Sandboxed execution, no arbitrary shell access",
        "metadata": "Embedded proposal/Kanban IDs in artifacts"
      },
      "preset": {
        "templates": ["Dark Maestro governance templates"],
        "installation": "specify preset add antigravity"
      },
      "dashboard": {
        "integration": "Spec-kit tab with cross-referenced Kanban cards",
        "provenance": "origin: 'spec-kit' flag in database"
      }
    },
    "constraints": [
      {
        "id": "CSTR-SPECKIT-V1",
        "description": "spec-kit is a UX layer, not the engine",
        "enforcement": "No API changes; CLI only calls primitives"
      },
      {
        "id": "CSTR-SPECKIT-V3",
        "description": "Provenance preserved via origin metadata",
        "enforcement": "Embedded flag in all artifacts"
      }
    ],
    "risks": [
      {
        "type": "security",
        "level": "high",
        "mitigation": "Sandboxed bridge with strict allowlists"
      },
      {
        "type": "data_drift",
        "level": "medium",
        "mitigation": "Metadata linking (headers/webhooks)"
      }
    ],
    "roadmap": [
      {
        "task": "Draft bridge spec",
        "owner": "Systems Architect",
        "status": "approved"
      },
      {
        "task": "Implement bridge",
        "owner": "Editor Agent (Cline)",
        "status": "in_progress"
      }
    ]
  },
  "aesthetic_considerations": [
    {
      "feature": "Dynamic prompt chaining",
      "description": "Analyze developer sentiment via ComfyUI",
      "status": "optional enhancement"
    },
    {
      "feature": "Dark realism telemetry",
      "description": "Embed contrast/symbolism into validation",
      "status": "optional enhancement"
    }
  ]
}
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
