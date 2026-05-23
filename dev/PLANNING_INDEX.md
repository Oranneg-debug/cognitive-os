# Development Planning Index

**Last Updated**: 2026-05-18

This folder contains architectural proposals, decisions, and development workflows for the Antigravity project.

## 📋 Quick Navigation

| File | Purpose |
|------|---------|
| [proposals/](./proposals/) | Active architectural proposals awaiting review |
| [decisions/](./decisions/) | Log of architectural decisions |
| [templates/proposal-template.md](./templates/proposal-template.md) | Template for new proposals |

---

## 📊 Current Status

| Proposal | Date | Status |
|----------|------|--------|
| Obsidian Plugin Dev Flow | 2026-05-18 | ✅ Approved - Technical Council Meeting |

---

## 🚀 How to Use This Folder

### 1. Create a New Proposal
Copy the template and fill in your architectural proposal:
```bash
cp templates/proposal-template.md proposals/2026-MM-DD_YOUR_PROPOSAL.md
```

### 2. Send for Multi-Opinion Review
Share the proposal file with different AI systems or team members.

### 3. Log Decisions
When a decision is made, create an entry in `decisions/`:
```bash
cp templates/proposal-template.md decisions/2026-MM-DD_your_decision.md
```

---

## 🔗 Related Documentation

- [../../docs/SYSTEM_ARCHITECTURE.md](../../docs/SYSTEM_ARCHITECTURE.md) - System overview
- [../../docs/MODEL_ORCHESTRATION.md](../../docs/MODEL_ORCHESTRATION.md) - Model orchestration details

### Vault Integration
Planning docs sync to Obsidian vault at:
```
E:\Oranneg\CloudStation\Documents\Obsidian\Grand Nexus\.obsidian\plugins\dev\
```

Sync via: `npm run sync-to-vault` (from `cognitive-os/`)

---

## 📊 Sync Status

| Last Sync | Source | Target |
|-----------|--------|--------|
| Pending | `cognitive-os/dev/` | `.obsidian/plugins/dev/` |

---

*This index is auto-generated. Add new entries as you create proposals.*