---
parent_handoff: "[[ARCH-20260522-205800-DA5B0A2D_BETA_HANDOFF]]"
parent_proposal: "[[ARCH-20260522-205800-DA5B0A2D_PROPOSAL]]"
section: A4
target_coder: qwen3-coder-next (Cline)
created: 2026-05-25
status: in_progress
tasks_total: 1
tasks_completed: 0
---

# A4 — Dashboard Kanban UI (Cline-scoped handoff)

> **You are the coder.** This is your only document. Everything you need
> to build the Kanban Workflow tab is on this page. Don't go file-spelunking
> in the proposal unless something here is genuinely ambiguous.

## What's already done (DO NOT TOUCH)

The backend is **live and tested** on `origin/main = 0dddf73`:

| File | Status |
|---|---|
| `src/kanban_store.py` | SQLite + async CRUD (23 tests green) |
| `src/kanban_renderer.py` | Renders to `Dev-KanBan.md` (28 tests green) |
| `src/api.py` | 5 endpoints + lifespan schema init (16 tests green) |
| `tests/test_kanban_store.py` | 23 cases |
| `tests/test_kanban_renderer.py` | 28 cases |
| `tests/integration/test_kanban_api.py` | 16 cases |

**Do not modify any file above.** If you think you need to, stop and ask the reviewer.

## API contract (use this verbatim)

The API is mounted on the same host:port as the dashboard (`http://127.0.0.1:5000`). Same-origin — no CORS needed.

### GET `/api/kanban/board`

Returns the full board. Use this for the initial render and after every transition (to refresh).

```json
{
  "columns": [
    {
      "name": "backlog",
      "cards": [
        {
          "proposal_id": "ARCH-…",
          "prefix": "ARCH",          // "DEV" | "ARCH" | "NLST"
          "title": "Migrate kanban to SQLite",
          "column_name": "backlog",
          "substatus": null,         // or "planning" | "execution.coding" | "review" | etc.
          "severity": "high",        // "high" | "medium" | "low" | null
          "origin": "systems-architect",
          "created_ts": "2026-05-22T20:58:00+00:00",
          "updated_ts": "2026-05-25T14:00:00+00:00",
          "state_hash": "abc123…"
        }
      ]
    },
    /* …5 more columns, always in this order: */
    /* "backlog", "proposal", "beta testing", "alpha polish", "finalized", "deployed" */
  ],
  "generated_at": "2026-05-25T14:00:00+00:00"
}
```

### POST `/api/workflow/transition`

Move a card. **This is the endpoint your drag-handler POSTs to.**

Request body:

```json
{
  "proposal_id": "ARCH-…",
  "target_column": "beta testing",     // must be one of the 6 canonical names
  "target_substatus": "planning",      // optional; null clears it
  "approver": "dashboard",             // free string; defaults to "dashboard"
  "reason": "user drag",               // free string; optional
  "gate_passed": 0,                    // -1=failed | 0=N/A | 1=passed
  "gate_details": null,                // optional dict (for future gate UI)
  "archive_hash": null                 // optional
}
```

Success response (HTTP 200):

```json
{
  "status": "success",
  "card": { /* same shape as in board.columns[*].cards */ },
  "vault_mirror": "E:\\…\\Dev-KanBan.md"
}
```

**Failure codes — handle these explicitly:**

| HTTP | Cause | Your UX |
|---|---|---|
| 404 | proposal_id not in store | toast: "Card no longer exists; refreshing board" → re-GET /api/kanban/board |
| 422 | invalid column / bad gate_passed | toast with the `detail` string; card snaps back |
| 500 | internal store error | toast with `detail`; card snaps back |

### POST `/api/workflow/rollback/{proposal_id}`

Revert the last move. Optional. Use for an "Undo" button (nice-to-have, not required for v1).

Failure codes: 404 (no card), 409 (only the creation row exists — nothing to roll back).

### GET `/api/workflow/state/{proposal_id}?history_limit=10`

Returns `{card, history, history_count}`. Use this to power the **history drawer**.

### POST `/api/kanban/cards`

Add a new card. **Not needed for v1** (cards arrive via the existing proposal pipeline / migration script). Skip the "+Add Card" button for now.

## What to build

Three files only:

1. **`dashboard/index.html`** — replace the placeholder at `<section id="system-kanban">` (line ~502) with the Kanban DOM. Keep everything else in the file untouched.
2. **`dashboard/script.js`** — add a `kanbanController` module/IIFE. Hook it into the existing subtab activation pattern (the file already has subtab logic for Structure / Request Flow — mirror it).
3. **`dashboard/styles.css`** — add Kanban-specific styles using the **existing CSS custom properties / design tokens** already in this file (don't introduce a new colour palette; reuse). Scope them under `#system-kanban`.

**No new files. No frameworks. No npm. Vanilla JS, native HTML5 drag events.**

## Feature checklist (v1)

- [ ] 6 columns in canonical order (`backlog`, `proposal`, `beta testing`, `alpha polish`, `finalized`, `deployed`). Column header is Title Case ("Beta Testing", not "beta testing").
- [ ] Cards show: prefix badge (DEV/ARCH/NLST), proposal_id (small/muted), title (bold), severity dot (high=red, medium=amber, low=green, null=grey).
- [ ] Drag-drop between columns (native HTML5 — `dragstart`, `dragover`, `dragleave`, `drop`).
- [ ] On successful drop → `POST /api/workflow/transition` with `target_column = <dropped column>`, `target_substatus = null`, `approver = "dashboard"`, `gate_passed = 0`. Visually snap the card into the new column. Then `GET /api/kanban/board` to refresh (other state may have changed).
- [ ] On 4xx/5xx → snap card BACK to its origin column + show an inline error message (top of the kanban area, dismissible). Do NOT use `alert()`.
- [ ] Click a card → opens a **history drawer** on the right side. Drawer fetches `GET /api/workflow/state/{id}?history_limit=10` and renders the rows newest-last (since the API already sorts chronologically — just iterate).
- [ ] Drawer has a close button + closes on Esc.
- [ ] **Substatus dropdown on beta-testing cards only.** When the card sits in the "Beta Testing" column AND has a `substatus`, render the substatus value as a small chip on the card. Clicking the chip opens a dropdown with these options: `planning`, `execution.coding`, `execution.testing`, `review`, `blocked`. Selection POSTs to `/api/workflow/transition` with the same `target_column = "beta testing"` and the new `target_substatus`. Use that exact mechanism — the API handles "moving a card to the same column with new substatus" as a regular transition.
- [ ] Auto-refresh board every 30 seconds while the Kanban tab is active (use `setInterval` and `clearInterval` on tab change so it doesn't run when hidden).

## Non-goals (defer to a later proposal)

- Gate-fail modal — there's no gate-checking layer here yet (the proposal says it's "standalone for now"). The `gate_passed` / `gate_details` fields exist on the wire, but the API doesn't enforce gates yet. Leave the gate-fail modal UX for when `workflow_engine.transition` lands.
- "+Add Card" button — cards arrive via migration / proposal pipeline.
- Rollback button — backend supports it; UI can come later.
- Real-time WebSocket updates — 30s polling is the v1 contract.

## Style conventions (re-use these — don't invent new ones)

- The dashboard already uses CSS variables like `--bg-primary`, `--bg-secondary`, `--text-primary`, `--accent`, etc. **Open `dashboard/styles.css` first**, scan the existing `:root` block, and re-use these tokens.
- Existing subtab pattern in `script.js` uses `.system-subtab-link` + `.system-subtab` with an `.active` class. Follow it; don't reinvent.
- For the severity dot, use the colour palette already used elsewhere for status indicators. If unclear, grep `styles.css` for `red|amber|green|warn|danger|success` first.
- Card width: ~280px. Column min-height: 400px. Drag-shadow: 0.6 opacity. Drag-over column: light highlight via `:has(.dragging)` or a JS-added class.

## Test plan (your acceptance gate)

1. `python -m uvicorn src.api:app --host 0.0.0.0 --port 5000` (the server is already running on your machine if not, start it).
2. Open `http://127.0.0.1:5000/` → click "System Architecture" → click "Kanban Workflow" subtab.
3. **Expectation:** 6 columns render. There's a fresh test card in "proposal" (from the migration we'll run later; OK if empty right now — the test card insert is a separate step).
4. Drag a card between columns → it moves visually + the column it landed in stays after a hard refresh (`Ctrl+F5`).
5. Trigger a deliberate failure: drag to a column then `POST /api/workflow/transition` directly via `curl` with `target_column: "purgatory"` → API returns 422 → your UI shows the error inline + the card stays put.
6. Click a card → drawer opens with at least one row (the card's creation transition). Esc closes it.

Run these manually before declaring done.

## What I (the reviewer) will check

- [ ] No new files outside the three listed.
- [ ] No new pip / npm dependencies.
- [ ] No `alert()` / `confirm()` / `prompt()` calls.
- [ ] No global namespace pollution — wrap your code in an IIFE or module.
- [ ] No inline `style="…"` attributes in the JS; all styling goes in CSS.
- [ ] No `fetch()` without a `try/catch` and 4xx/5xx branch.
- [ ] Substatus dropdown ONLY appears on beta-testing cards.
- [ ] Auto-refresh stops when the Kanban tab is not active.
- [ ] Vanilla JS. No imports from a CDN.

## Stop conditions

If you hit ANY of these, **STOP and report**:

1. The backend API behaves differently from what's documented above (don't work around it; report it).
2. You feel the urge to modify `src/api.py`, `src/kanban_store.py`, or `src/kanban_renderer.py`.
3. The existing dashboard structure (subtab pattern, CSS variables) makes one of the spec items impossible without refactoring shared code.
4. You hit a contradiction between this handoff and the existing dashboard code.

When done, push your branch + ping the reviewer. The reviewer (overarching agent) will:
1. Pull your changes
2. Smoke-test the 6-step manual checklist above
3. Run `python -m pytest tests/integration/test_kanban_api.py` to confirm backend wasn't broken
4. Approve or send back with specifics

## Tasks (tick as you go)

- [ ] **[✏️ PLANNER] A4. Implement Kanban Workflow tab in the dashboard**
   - [ ] Replace the placeholder in `#system-kanban` with the kanban DOM (6 columns, drawer container, error banner)
   - [ ] Add `kanbanController` module to `script.js` (init, fetch, render, drag-drop, drawer, polling)
   - [ ] Add `#system-kanban`-scoped styles in `styles.css` using existing tokens
   - [ ] Run the 6-step manual test plan
   - [ ] Confirm `pytest tests/integration/test_kanban_api.py` still passes
   - **Acceptance:** All checklist items above tick; reviewer's checklist passes
   - **Constraints:** Vanilla JS, no new deps, no inline styles, scope to existing subtab pattern
   - **Files:** `dashboard/index.html`, `dashboard/script.js`, `dashboard/styles.css`
