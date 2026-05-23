---
constraint_id: CSTR-PREMATURE-SYNC
applies_to:
  - ARCH-20260522-161500-A0F1B0C0  # Phase 0
  - ARCH-20260522-161600-60FE0001  # Phase 1 (informational; Phase 1 may add some)
binding: true
source: Alpha Polish chairman verdict, 2026-05-23 (task_20260523_155614_03a37ee9)
veto_severity: HIGH (logical)
---

# ╔══════════════════════════════════════════════════════════════╗
# ║  CONSTRAINT — Premature Synchronization                       ║
# ╚══════════════════════════════════════════════════════════════╝

## Definition

**Premature synchronization** is the introduction, during a "pure refactor"
phase, of any concurrency-control or coordination primitive that:

1. Was **not present** in the Beta-Testing version of the affected module, AND
2. Was **not explicitly mandated** by the proposal that authorised the phase.

## Concretely — what is forbidden during Alpha Polish of Phase 0

Adding any of the following to `paths.py`, `sync_check.py`, `proposal_writer.py`,
`handoff_writer.py`, `dev_route.py`, `kanban_processor.py` is **VETOED**:

| Primitive type           | Examples (illustrative, non-exhaustive)                  |
|--------------------------|----------------------------------------------------------|
| Mutex / Lock             | `threading.Lock`, `threading.RLock`, `multiprocessing.Lock` |
| Distributed lock         | `filelock`, `portalocker`, Redis SETNX, `fcntl.flock`    |
| Async coordination       | `asyncio.Lock`, `asyncio.Semaphore`, `asyncio.Event`     |
| Queue                    | `queue.Queue`, `asyncio.Queue`, `multiprocessing.Queue`  |
| Condition variable       | `threading.Condition`, `asyncio.Condition`               |
| Barrier                  | `threading.Barrier`                                      |
| Atomic / CAS             | `multiprocessing.Value`, custom CAS loops                |
| External coordinator     | etcd, Consul, Zookeeper, Redis pub/sub                   |

## Why this constraint exists

Phase 0 is a **structural extraction** — moving code, not changing behaviour.
Concurrency primitives change behaviour. Adding them during a refactor:

- Hides genuine refactoring bugs behind newly-introduced race conditions.
- Couples the rollback path to runtime state that wasn't there in Beta.
- Invents requirements that should have been captured in the proposal.
- Breaks the "pure refactor" assumption that lets reviewers reason about
  the diff as a no-op.

## When concurrency primitives ARE allowed

Phase 1 (ARCH-60FE0001) explicitly mandates `GovernanceUnitOfWork`, optimistic
concurrency via `version_hash`, and SQLite transactions. Those are
**authorised** because the proposal calls for them by name. They are NOT
premature — they are the contracted scope of that phase.

Future phases that need synchronization MUST:

1. File a proposal naming the specific primitive (e.g. "introduce
   `asyncio.Lock` around the kanban write path").
2. Pass boardroom + tech board review.
3. Document the invariant being protected and the failure mode if absent.

## Detection

The Alpha Polish CI gate does not currently AST-scan for these imports
(stdlib-only constraint precludes adding `libcst` or similar). Detection is
performed at proposal review time by the human reviewer + tech board.

A future proposal MAY introduce a regex-based pre-commit hook that fails on
any new `import threading|asyncio|multiprocessing|filelock|portalocker` not
accompanied by a `# CSTR-PREMATURE-SYNC: authorised by ARCH-XXXX` comment.

## Enforcement during Alpha Polish

The Alpha Polish branch (`feat/proposal-A0F1B0C0-phase0-refactor`) MUST NOT
add any of the imports in the forbidden table above. Verify with:

```powershell
git diff main...HEAD -- src/ | Select-String '^\+.*import\s+(threading|asyncio|multiprocessing|queue|filelock|portalocker|fcntl)'
```

Expected output: **empty**. Any match is a HIGH-severity veto trigger.
