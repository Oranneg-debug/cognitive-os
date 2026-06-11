---
date: 2026-06-01 21:30:00
proposal_id: DEV-20260601-SETTINGS_REDESIGN
decision_type: architecture_revision
approved_by: Systems Architect (GitHub Copilot)
---

# Architecture Decision: DEV-20260601-SETTINGS_REDESIGN

**Date**: 2026-06-01 21:30:00  
**Proposal**: DEV-20260601-SETTINGS_REDESIGN  
**Decision Type**: Architecture Revision (v2.0.0 Governance Foundation Compliance)

---

## Executive Summary

**Problem**: The original proposal attempted to implement settings UI changes without considering the v2.0.0 governance foundation, which would have violated VETO compliance.

**Solution**: Revised the proposal to route all settings changes through the Cognitive OS API layer (FastAPI → OutputRouter → UoW → master_config.md).

**Status**: ✅ **Approved** - Architecture alignment complete

---

## Original Problem

The initial proposal for settings redesign included:
- Tabbed interface with 6 categories
- Real-time search functionality
- Model health dashboard
- Contextual help tooltips
- Save status indicators

**Critical Issue**: The implementation plan involved **direct file I/O from the Obsidian plugin**, which would have:
- Bypassed `GovernanceUnitOfWork` (v2.0.0 pattern)
- Created dual sources of truth (Obsidian store + master_config.md)
- Lost audit trail for configuration changes
- Violated VETO compliance (B4, G2, T2)

---

## Architectural Decision

### Decision: Route All Settings Changes Through API Layer

**Rationale**:
1. **VETO B4 (Atomic dual-write)**: UoW ensures all-or-nothing commits across KanbanStore + HandoffVault + ApprovalLogger
2. **VETO G2 (Saga pattern)**: Compensating functions allow rollback on failure
3. **VETO T2 (Semantic hashing)**: version_hash computed from config keys only
4. **VETO E3 (Fail-fast validation)**: Pydantic schemas reject invalid values before write

### Architecture Flow

```
User (Obsidian Plugin)
    ↓ POST /api/config/settings
FastAPI (/api/config/settings)
    ↓
OutputRouter (routing_rules.yaml)
    ↓
WorkflowEngine (state_machine.yaml)
    ↓
GovernanceUnitOfWork (transactional)
    ├─→ KanbanStore (SQLite)
    ├─→ HandoffVault (content-addressable)
    └─→ ApprovalLogger (cryptographic hash chain)
    ↓
master_config.md (single source of truth)
```

---

## Implementation Changes

### Phase 0: API & Governance (NEW)

**Files to Create**:
- `cognitive-os/src/config_validator.py` - Pydantic schemas + validation layer
- `obsidian-lmstudio-agent/src/settings-redesign.ts` - Redesigned settings UI

**Files to Modify**:
- `cognitive-os/src/api.py` - Add `/api/config/settings` endpoints
  ```python
  @app.get("/api/config/settings")
  async def get_settings():
      """Return merged settings from master_config.md + plugin defaults"""
  
  @app.post("/api/config/settings")
  async def update_settings(settings: SettingsUpdate):
      """Validate and commit changes via OutputRouter → UoW"""
  ```

- `obsidian-lmstudio-agent/src/settings.ts` - Remove direct file I/O, use API

### Phase 1-3: UX Improvements (Unchanged)

All original UX improvements remain:
- Tabbed interface (6 categories)
- Real-time search with `Ctrl+K`
- Model health dashboard
- Contextual help tooltips
- Save status indicators
- Mobile responsiveness

---

## Timeline Impact

| Phase | Original | Revised | Change |
|-------|----------|---------|--------|
| **Phase 0** | N/A | API & Governance | +1 week (NEW) |
| Phase 1 | 1 week | 1 week | No change |
| Phase 2 | 1 week | 1 week | No change |
| Phase 3 | 1 week | 1 week | No change |
| **Total** | 2-3 weeks | **3-4 weeks** | +1 week |

---

## VETO Compliance Matrix

| VETO | Requirement | Implementation | Status |
|------|-------------|----------------|--------|
| **B4** | Atomic dual-write | UoW wraps KanbanStore + HandoffVault + ApprovalLogger | ✅ |
| **V9** | Explicit exceptions | Pydantic schemas raise typed exceptions | ✅ |
| **G2** | Saga pattern | WorkflowEngine uses compensating functions | ✅ |
| **E3** | Fail-fast validation | SchemaValidator rejects invalid values before write | ✅ |
| **T2** | Semantic hashing | version_hash computed from config keys only | ✅ |

---

## Relationship with DEV-20260601-SETTINGS-IMPROVEMENTS

**Decision**: Merge SETTINGS-IMPROVEMENTS into SETTINGS_REDESIGN

**Rationale**: Both proposals address settings, so merging creates a single comprehensive solution.

**Integration Points**:
- Model health verification → Phase 0 API endpoints
- Timeout controls → Pydantic validation schemas
- Retry logic → UoW compensating functions
- Error handling → Typed exceptions

---

## Acceptance Criteria (Beta Phase)

### Phase 0: API & Governance (MUST PASS)
- [ ] `GET /api/config/settings` returns merged settings from master_config.md
- [ ] `POST /api/config/settings` validates input via Pydantic schemas
- [ ] Settings changes commit atomically via UoW (KanbanStore + HandoffVault + ApprovalLogger)
- [ ] All changes logged in `dev/decisions/` with cryptographic hash chain

### Phase 1: Core UI (MUST PASS)
- [ ] Tabbed interface allows switching between 6 categories
- [ ] Real-time search filters settings across all tabs
- [ ] Model health dashboard displays real-time status
- [ ] Search keyboard shortcut `Ctrl+K` works

### Phase 2: Enhanced Features (MUST PASS)
- [ ] Contextual help tooltips display on hover
- [ ] Save status indicators show saved/pending/error states
- [ ] Toast notifications appear on save completion

### Phase 3: Polish & Testing (MUST PASS)
- [ ] Mobile responsive design passes all test devices
- [ ] Accessibility audit passes WCAG 2.1 AA
- [ ] User testing confirms 80%+ satisfaction with new UI

---

## Rollback Plan

If issues are discovered during Beta Testing:

1. **Revert API endpoints**: Remove `/api/config/settings` from FastAPI
2. **Restore old settings.ts**: Use git history to restore previous version
3. **Clear UoW queue**: Delete pending transactions from KanbanStore
4. **Restore master_config.md**: Use HandoffVault snapshot

**Compensating Function**: The UoW pattern ensures all changes can be rolled back atomically.

---

## Approval Chain

| Role | Name | Approved | Timestamp |
|------|------|----------|-----------|
| Systems Architect | GitHub Copilot | ✅ | 2026-06-01 21:30:00 |
| Beta Council | Pending | 🔒 | - |
| Alpha Council | Pending | 🔒 | - |
| Final Audit | Pending | 🔒 | - |

---

## Related Proposals

- **Primary**: DEV-20260601-SETTINGS_REDESIGN (this proposal)
- **Merged**: DEV-20260601-SETTINGS-IMPROVEMENTS (integrated into this proposal)

---

## References

- `docs/SYSTEM_ARCHITECTURE.md` - v2.0.0 Governance Foundation
- `docs/MODEL_ORCHESTRATION.md` - Configuration management
- `cognitive-os/src/governance_unit_of_work.py` - UoW implementation
- `cognitive-os/src/workflow_engine.py` - State machine engine
- `cognitive-os/src/schema_validator.py` - Pydantic validation

---

*Decision logged via ApprovalLogger v2.0.0*
