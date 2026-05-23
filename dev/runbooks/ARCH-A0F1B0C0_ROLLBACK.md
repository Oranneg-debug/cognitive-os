---
proposal_id: ARCH-20260522-161500-A0F1B0C0
phase: alpha_polish
artifact_type: rollback_runbook
target_duration_minutes: 10
verification: deterministic_git_hash
last_updated: 2026-05-23
---

# ╔══════════════════════════════════════════════════════════════╗
# ║  ROLLBACK RUNBOOK — Phase 0 Refactor (ARCH-A0F1B0C0)         ║
# ║  Target: ≤ 10 minutes wall-clock from decision to verified.  ║
# ╚══════════════════════════════════════════════════════════════╝

## When to roll back

Trigger rollback **only** if **any** of the following is true after deploy:

| Symptom                                                  | Severity |
|----------------------------------------------------------|----------|
| `pytest tests/` fails on `main`                          | HIGH     |
| Any FastAPI endpoint returns 500 that worked before      | HIGH     |
| `pylint --disable=all --enable=cyclic-import src/` fails | HIGH     |
| Import error on cold start (`python -m src.api`)         | HIGH     |
| `dev_route.py` imports from anything not in the branch   | MEDIUM   |

Do **not** roll back for: lint warnings, docstring complaints, unused imports.

---

## Pre-rollback: record the failed state

Capture the broken HEAD so we can diff later.

```powershell
cd e:\Antigravity\cognitive-os
git rev-parse HEAD | Out-File -Encoding ASCII rollback_failed_head.txt
git log -1 --stat | Out-File -Encoding ASCII rollback_failed_summary.txt
```

---

## The rollback itself

### Step 1 — Identify the last green commit

```powershell
git log --oneline --first-parent main..HEAD
```

The **parent** of Cline's Phase 0 commit is the last known-green:

| Commit   | Description                                        |
|----------|----------------------------------------------------|
| `1014acc`| Phase 0 refactor (Cline)                           |
| `baf018c`| ObsidianWriter → paths.py polish                   |
| `<base>` | **Roll back to this** (parent of `1014acc`)        |

Get the base hash:

```powershell
$BASE = git rev-parse 1014acc^
$BASE  # paste this into the next step
```

### Step 2 — Hard reset the feature branch

```powershell
git checkout feat/proposal-A0F1B0C0-phase0-refactor
git reset --hard $BASE
```

### Step 3 — Restart services

```powershell
# kill old python procs (use Task Manager if access denied)
Get-Process python -ErrorAction SilentlyContinue | Stop-Process -Force
# relaunch
.\start_services.bat
```

### Step 4 — Verify

```powershell
python -m pytest tests/ --tb=short -q
python -m pylint --disable=all --enable=cyclic-import src/
```

Both must pass.

---

## Deterministic verification (the post-rollback checksum)

Compute a stable hash of the source tree at the rolled-back HEAD:

```powershell
$post = git rev-parse HEAD
$tree = git rev-parse "${post}^{tree}"
$srcSha = git ls-tree -r $tree src/ | git hash-object --stdin
"HEAD     : $post"
"TREE     : $tree"
"SRC HASH : $srcSha"
```

**Acceptance criterion:**

- `HEAD` MUST equal `$BASE` from Step 1.
- `TREE` MUST match the recorded tree hash of the last green commit
  (capture this once in `dev/runbooks/_known_green_tree_hashes.txt`).
- `SRC HASH` MUST be identical between any two rollbacks to the same base
  (it's deterministic from git tree contents — proves bit-identical state).

Record the result:

```powershell
@{
    timestamp = (Get-Date).ToString('o')
    rolled_back_to = $BASE
    tree_hash = $tree
    src_hash = $srcSha
    operator = $env:USERNAME
} | ConvertTo-Json | Out-File -Append -Encoding ASCII dev/runbooks/_rollback_ledger.jsonl
```

---

## ⏱  Time budget

| Step                          | Budget |
|-------------------------------|--------|
| Decide to roll back           |  1 min |
| Record failed state           |  1 min |
| Reset + restart services      |  3 min |
| pytest + pylint verification  |  3 min |
| Checksum + ledger write       |  1 min |
| Buffer                        |  1 min |
| **Total**                     | **10 min** |

If the budget is exceeded, **escalate to manual investigation**.
Do not attempt fix-forward during rollback.

---

## Post-mortem (within 24h)

Append to `dev/decisions/_bootstrap_approvals_2026-05-22.md`:

- entry_id: `<incident-date>-A0F1B0C0-rollback`
- entry_type: `rollback_event`
- failed_head: `<hash from rollback_failed_head.txt>`
- rolled_back_to: `<BASE hash>`
- src_hash_post: `<from ledger>`
- root_cause: (one paragraph)
- corrective_action: (next-step proposal ID or "none, transient")
