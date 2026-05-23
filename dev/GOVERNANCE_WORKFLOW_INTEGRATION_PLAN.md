---
title: Complete Governance & Workflow Integration Plan
date: 2026-05-21
version: 1.0
status: proposal
---

# Complete Governance & Workflow Integration Plan

**Document Version**: 1.0  
**Created**: 2026-05-21  
**Status**: 3 Dev Proposals Ready for Boardroom Review  
**Classification**: STRATEGIC - Architecture Foundation

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [The Four-Layer Architecture](#the-four-layer-architecture)
3. [Three Development Proposals](#three-development-proposals)
4. [Five-Phase Implementation Roadmap](#five-phase-implementation-roadmap)
5. [Complete Data Flow](#complete-data-flow)
6. [Verification Checklist](#verification-checklist)
7. [Acceptance Criteria](#acceptance-criteria)
8. [Veto Points](#veto-points)

---

## Executive Summary

This plan establishes a complete governance framework for the Cognitive OS, ensuring that:

- ✅ **Data integrity**: Immutable audit trail at every phase transition
- ✅ **Deterministic routing**: Council outputs & analyst reports automatically route to correct destinations
- ✅ **Approval gates**: Work cannot advance to coding without solid planning
- ✅ **Bidirectional flow**: Proposals can be rejected and re-worked
- ✅ **Full visibility**: Dashboard shows governance state and approval history
- ✅ **Audit compliance**: Every decision logged with timestamp, approver, reasoning

The plan is decomposed into **3 strategic dev proposals** that stack vertically:
1. **Governance Foundation** (Phase 1) - Data models, schema, durability
2. **Routing Automation** (Phase 2) - OutputRouter, workflow routing
3. **Workflow Execution** (Phase 3-4) - State machine, phase transitions, approval gates

---

## The Four-Layer Architecture

### Layer 1: Analyst Input & Governance Routing
**Entry point management** — where reports come from, how they're triaged by severity

- Analyst report persistence: `dev/reports/`
- Severity classification: HIGH / MEDIUM / LOW (auto-detected)
- Pre-decision log: `dev/decisions/`
- Routing decisions: Boardroom queue vs. Kanban backlog

### Layer 2: Board Execution
**Decision making** — where councils synthesize and approve work

- Boardroom: 6-role council (Strategist → Specialist → Critic → Creative → Logical → Chairman)
- Technical Board: 3-role subset (Analyst → Architect → Specialist)
- Council orchestrator: existing `src/orchestrator.py`

### Layer 3: Automatic Output Routing (OutputRouter)
**Content analysis & routing** — parse council outputs and automatically route to destinations

- Content analysis engine (Detect severity, routing markers)
- Routing rule matcher (Deterministic YAML-based rules)
- Destination resolver (proposal file, decision log, kanban column)
- Kanban updater (Automatic column changes)

### Layer 4: Workflow Execution & Validation
**State machine & approval gates** — phases with validation, approval gates, data protection

- State machine: 7 states (Backlog → Proposal → Beta Phase:Planning → Beta Phase:Execution → Alpha → Finalized → Deployed)
- Approval gates: Critical checkpoint before coding starts
- Artifact versioning: Immutable snapshots at each phase
- Approval logging: Append-only decision log

---

## Three Development Proposals

### Proposal 1: DEV-20260521-GOVERNANCE-FOUNDATION
**Phase 1 - Data Models, Schema, Durability**

Location: [`cognitive-os/dev/proposals/DEV-20260521-GOVERNANCE-FOUNDATION.md`](cognitive-os/dev/proposals/DEV-20260521-GOVERNANCE-FOUNDATION.md)

**Components**:
- `src/workflow_models.py` — Pydantic models (WorkflowEnvelope, ValidatedProposal, ArtifactVersion, ApprovalRecord)
- `src/schema_validator.py` — YAML frontmatter validation
- `src/handoff_vault.py` — Immutable versioned storage with content-addressable hashing
- `src/approval_logger.py` — Append-only decision log with SQLite index

**Deliverables**:
- 4 new Python modules (1,200+ lines)
- Folder structure: `dev/reports/`, `dev/decisions/`, `dev/.archives/`
- Templates: `report-template.md`, `decision-log-template.md`

**Dependencies**: None  
**Complexity**: HIGH  
**Status**: ⏳ Awaiting Approval

---

### Proposal 2: DEV-20260521-ROUTING-AUTOMATION
**Phase 2 - OutputRouter, Workflow Router, Integration**

Location: [`cognitive-os/dev/proposals/DEV-20260521-ROUTING-AUTOMATION.md`](cognitive-os/dev/proposals/DEV-20260521-ROUTING-AUTOMATION.md)

**Components**:
- `src/output_router.py` — Council synthesis → routing decision engine
- `src/workflow_router.py` — Analyst report → severity triage & escalation
- Integration with `src/memory_file_system.py` and `src/api.py`
- Analyst report watcher (watches `dev/reports/`)

**Deliverables**:
- 3 new Python modules (800+ lines)
- 7 deterministic routing rules (YAML-based, no LLM scoring)
- API response enhancement (includes routing_decision)
- Report watcher for automatic triage

**Dependencies**: DEV-20260521-GOVERNANCE-FOUNDATION (Phase 1)  
**Complexity**: HIGH  
**Status**: ⏳ Awaiting Approval

---

### Proposal 3: DEV-20260521-WORKFLOW-EXECUTION
**Phase 3 & 4 - Workflow Engine, State Machine, Approval Gates**

Location: [`cognitive-os/dev/proposals/DEV-20260521-WORKFLOW-EXECUTION.md`](cognitive-os/dev/proposals/DEV-20260521-WORKFLOW-EXECUTION.md)

**Components**:
- `src/workflow_engine.py` — State machine orchestrator (7 states, valid transitions, approval gates)
- `src/kanban_processor.py` update — Column change → phase transition detection
- `src/dev_route.py` refactor — Extract routing logic, delegate phase transitions
- Phase models in `src/workflow_models.py` extension

**Deliverables**:
- 2 new Python modules (1,500+ lines)
- State machine with 7 states and validated transitions
- Critical approval gate: Beta Phase:Planning → Beta Phase:Execution (5-check validation)
- Kanban integration (new `/api/kanban-transition` endpoint)
- Substatus tracking for Beta Phase:Execution (coding, debugging, testing, ready-for-alpha)

**Dependencies**: DEV-20260521-GOVERNANCE-FOUNDATION + DEV-20260521-ROUTING-AUTOMATION (Phases 1-2)  
**Complexity**: VERY HIGH  
**Status**: ⏳ Awaiting Approval

---

## Five-Phase Implementation Roadmap

### Phase 1: Governance Foundation
**Goal**: Define types, schema, and durability layer

✅ **Deliverable**: DEV-20260521-GOVERNANCE-FOUNDATION  
- Pydantic models for proposal lifecycle
- YAML frontmatter validation (required fields enforcement)
- Immutable versioned storage (content-addressable hashing, SHA256)
- Append-only decision log (SQLite indexed, never overwrite)
- Recovery mechanism (kill service mid-write, full recovery from vault)

**Effort**: 2-3 sprints  
**Risk**: Low (isolated data layer)  
**Success Criteria**: Data loss = 0, full recovery after service crash

---

### Phase 2: Routing & Automation
**Goal**: Implement analyst input routing and OutputRouter

✅ **Deliverable**: DEV-20260521-ROUTING-AUTOMATION  
- Deterministic routing rules (no LLM scoring, YAML-based)
- Council synthesis → automatic proposal file creation
- Analyst report → severity triage & escalation
- API response enhancement (client knows routing outcome)
- Analyst report watcher (auto-watches `dev/reports/`)

**Effort**: 2-3 sprints  
**Risk**: Medium (integration with existing API)  
**Success Criteria**: Zero manual filing, zero silent-drop failures

---

### Phase 3: Workflow Execution
**Goal**: Implement state machine and phase transitions

✅ **Deliverable**: DEV-20260521-WORKFLOW-EXECUTION  
- 7-state machine (Backlog, Proposal, Beta Phase:Planning, Beta Phase:Execution, Alpha, Finalized, Deployed)
- Validated transitions (not all states can go to all others)
- Kanban watcher integration (column change → phase transition)
- Archive snapshots before every phase transition
- Decision log entries for every approval

**Effort**: 3-4 sprints  
**Risk**: Medium-High (state machine complexity)  
**Success Criteria**: All transitions validated, no orphaned proposals

---

### Phase 4: Approval Gates & Execution Isolation
**Goal**: Implement approval gates and execution containers

✅ **Included in Phase 3 Proposal**  
- **Critical gate**: Beta Phase:Planning → Beta Phase:Execution (5-check validation)
  1. Implementation details documented (> 500 chars)
  2. Risks and mitigations documented
  3. Technical Board consensus (Analyst + Architect + Specialist voted APPROVED)
  4. Resources allocated
  5. Execution container flag set
- Container isolation (work happens in isolated environment)
- Substatus tracking (coding, debugging, testing, ready-for-alpha)
- Bidirectional flow (rejection moves proposal back to Backlog)

**Effort**: Included in Phase 3  
**Risk**: Medium (gate enforcement, container isolation)  
**Success Criteria**: No work starts without plan, gate blocks premature coding

---

### Phase 5: Observability & Polish
**Goal**: Visibility and user feedback

⏳ **Future Proposal** (not in current 3-proposal set)  
- Dashboard integration (show workflow state of all proposals)
- Display decision log entries
- Show archive snapshots
- Structured logging at each phase transition
- User documentation

**Effort**: 2 sprints  
**Risk**: Low (UI/UX only)  
**Success Criteria**: Users can see governance state at a glance

---

## Complete Data Flow

### Scenario: HIGH-Severity Architecture Issue

```
1. ANALYST DISCOVERY (Layer 1)
   Systems Architect writes: dev/reports/systems-architect_2026-05-21_high-coupling.md
   Severity: HIGH (auto-detected)
   → Routes to Boardroom queue (not regular backlog)

2. BOARDROOM EXECUTION (Layer 2)
   Boardroom council runs (5-phase council)
   Roles: Strategist → Specialist → Critic → Creative → Logical → Chairman
   Output: "definitive_blueprint: Refactor orchestrator into 3 modules
            #boardroom #severity:high #coupling"

3. OUTPUT ROUTING (Layer 3)
   OutputRouter.route_output() analyzes synthesis:
   ✓ Detect: #severity:high + #boardroom + definitive_blueprint
   ✓ Match: boardroom_proposal rule
   ✓ Action: create_proposal
   ✓ Kanban column: proposal
   
   OutputRouter.apply_routing():
   ✓ Create: dev/proposals/DEV-20260521-XXXX_PROPOSAL.md
   ✓ Create archive: dev/.archives/DEV-20260521-XXXX_proposal_20260521-143200.json
   ✓ Log entry: dev/decisions/DEV-20260521-XXXX_log.md
   ✓ Update Kanban: card → "proposal" column

4. WORKFLOW EXECUTION (Layer 4)
   User moves card: Proposal → Beta Phase:Planning
   ✓ Archive snapshot created
   ✓ Phase updated in YAML
   ✓ Decision log entry written
   
   Technical Board runs (Analyst → Architect → Specialist)
   Reviews and expands implementation details
   
   **CRITICAL GATE**: Beta Phase:Planning → Beta Phase:Execution
   ✓ Implementation details > 500 chars? ✓
   ✓ Risks and mitigations documented? ✓
   ✓ Technical Board consensus (all 3 voted)? ✓
   ✓ Resources allocated? ✓
   ✓ Execution container flag set? ✓
   → All checks pass!
   
   Archive snapshot created, gate approval logged
   Work advances to Beta Phase:Execution in isolated container
   
   Developer implements per technical plan
   Commits code, runs tests
   Moves card: Beta Phase:Execution → Alpha
   
   Alpha → Finalized → Deployed (auto-advance)
   Full audit trail: 6 archive snapshots (proposal, planning, execution, alpha, finalized, deployed)
```

---

## Verification Checklist

### Data Loss Prevention
- ✅ Analyst report saved before proposal creation
- ✅ Handoff vault contains snapshots before each phase transition
- ✅ Decision log appended on every approval
- ✅ Sync checkpoint logged before writes
- ✅ Kill service mid-proposal-write, restart: proposal recovers from vault

### Governance Routing
- ✅ Systems Architect HIGH-severity report → Boardroom queue (not regular backlog)
- ✅ MEDIUM/LOW-severity report → Kanban backlog card
- ✅ Analyst rejection creates decision log entry (not silent drop)

### Output Routing
- ✅ Council synthesis with #boardroom marker → proposal file created
- ✅ Council synthesis with #severity:high → kanban "proposal" column
- ✅ Decision-only output → dev/decisions/ (not proposal file)

### Workflow Validation
- ✅ Proposal missing required fields → rejected at entry
- ✅ Proposal without implementation plan → Beta Phase:Planning → Beta Phase:Execution gate blocks
- ✅ Phase transition → archive snapshot created + logged
- ✅ Rejection → proposal moves back to Backlog (bidirectional)
- ✅ Beta Phase:Execution substatus (coding/debugging) tracked in YAML
- ✅ Container isolation works for Beta Phase:Execution

### Audit Trail
- ✅ Decision log entries immutable (append-only, no edits)
- ✅ Archive snapshots include state hash
- ✅ Approval logger tracks who decided, when, why

---

## Acceptance Criteria

| Criterion | Pass Condition |
|-----------|----------------|
| Routing works | Systems Architect HIGH-severity proposal appears in Boardroom Queue, not regular Proposal column |
| Data loss prevented | Handoff vault snapshots exist before/after each phase transition |
| Audit complete | Approval log has immutable entry for every approval with timestamp, approver, proposal hash |
| Schema enforced | Proposal without severity/origin/workflow_version rejected at entry |
| Bidirectional flow | Technical Board can reject Beta Phase work back to Backlog (not forward-only) |
| OutputRouter works | Council synthesis with #boardroom marker creates proposal + updates Kanban automatically |
| Planning gate works | Proposal blocked at Beta Phase:Planning → Beta Phase:Execution without full implementation plan; unblocked after all details added |
| Execution substatus tracked | Beta Phase:Execution YAML includes substatus (coding/debugging/testing) with timestamps |
| Container isolation | Beta Phase:Execution work happens in isolated container; changes don't affect other phases |
| Recovery works | Kill backend mid-write, restart: no data loss, full recovery from vault |

---

## Veto Points

- ❌ **No LLM-generated routing decisions** (must be deterministic YAML-based)
- ❌ **No in-memory state** (must persist after every transition)
- ❌ **No automatic HIGH-severity escalation** (must be explicit analyst flag)
- ❌ **No silent-drop failures** (all errors logged with full context)
- ❌ **No manual gate override** (gates are hard constraints, no exceptions)

---

## Next Steps

1. **Boardroom Review**: Present all 3 proposals to Boardroom Council
2. **Technical Board Review**: Technical Board (Analyst → Architect → Specialist) reviews implementation feasibility
3. **Approval Gate**: Boardroom votes on each proposal (APPROVED / REJECTED / CONDITIONAL)
4. **Execution**: Phase 1 (Governance Foundation) begins once approved
5. **Sequential Rollout**: Phase 2 depends on Phase 1 completion; Phase 3 depends on Phase 1 + Phase 2

---

## Document Management

**Version**: 1.0  
**Created**: 2026-05-21  
**Status**: Ready for Boardroom Review  
**Next Review**: Upon Phase 1 completion  
**Owner**: Systems Architect

**Linked Proposals**:
- [`DEV-20260521-GOVERNANCE-FOUNDATION.md`](cognitive-os/dev/proposals/DEV-20260521-GOVERNANCE-FOUNDATION.md)
- [`DEV-20260521-ROUTING-AUTOMATION.md`](cognitive-os/dev/proposals/DEV-20260521-ROUTING-AUTOMATION.md)
- [`DEV-20260521-WORKFLOW-EXECUTION.md`](cognitive-os/dev/proposals/DEV-20260521-WORKFLOW-EXECUTION.md)

---

**End of Document**
