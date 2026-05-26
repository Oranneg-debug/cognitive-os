---
type: tech_debt_register
created: 2026-05-22
status: active
description: |
  Append-only register of technical debt accepted during proposal reviews.
  Each row references the proposal that created the debt and the proposal
  that must eliminate it. Never edit existing rows — append a new row to
  mark resolution (with `resolved_in:` field).
---

# Technical Debt Register

| ID | Description | Created in | Target resolver | Status | Notes |
|---|---|---|---|---|---|
| `ARCH-…-F10FE0E1-DEBT-01` | Regex-based YAML status updaters in `dev_route.py` (`re.sub(r'\|\s*Lifecycle Phase\s*\|\s*…')` and similar). Fragile, write-in-place, no archive of prior state. | ARCH-20260522-161500-A0F1B0C0 (v1.1, Boardroom Review 2026-05-22) | ARCH-20260522-161800-F10FE0E1 (Phase 3+4 `workflow_engine`) | open | Out of scope for Phase 0 by design; `workflow_engine.transition()` becomes the single phase writer, deleting all regex-based status edits. |
