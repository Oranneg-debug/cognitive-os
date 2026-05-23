---
style_id: DARK-MAESTRO-V1
applies_to: all internal documentation, error messages, CI output, runbooks
binding: true
source: Alpha Polish chairman verdict, 2026-05-23
veto_severity: MEDIUM (aesthetic)
---

# ╔══════════════════════════════════════════════════════════════╗
# ║  DARK MAESTRO — Aesthetic Style Guide                         ║
# ║  High-contrast clarity. Evocative precision. No ornament.     ║
# ╚══════════════════════════════════════════════════════════════╝

## The three rules

1. **High contrast.** Text vs space. Pass vs fail. Done vs blocked.
   Never grey. Never "warning-but-not-really".

2. **Evocative precision.** Every line earns its presence.
   Status changes get a verdict, never a vibe.

3. **No ornament.** Emoji are tools, not decoration. Box-drawing
   characters frame meaning, never fill space.

## Pass / fail / pending — the three canonical glyphs

| State    | Glyph | Use                                          |
|----------|-------|----------------------------------------------|
| Pass     | `■`   | Filled square. Earned, definitive.           |
| Fail     | `□`   | Hollow square. Absence, not noise.           |
| Pending  | `▷`   | Right-pointing triangle. In motion.          |

Examples:

```
  ■ PASS  dev_route_size       2ms   197 lines (limit: 300)
  □ FAIL  no_vault_literals    7ms   1 hit: src/api.py:629
  ▷ WAIT  perf_smoke           —     baseline not yet recorded
```

**Never** mix with `✔ ✘ ✓ ✗ ☑ ☒ ❌ ✅` etc. One vocabulary.

## Headers

Section breaks use ASCII rules, not Markdown underlines:

```
═══════════════════════════════════════════════════════════════
  SECTION TITLE — terse subtitle
═══════════════════════════════════════════════════════════════
```

For Markdown files, `## ╔══╗ / ║  TITLE  ║ / ╚══╝` is reserved for the
single top-of-file banner. Subordinate sections use plain `##`.

## Error messages

Every error message answers three questions in order:

1. **What** happened (one sentence, past tense, no apology).
2. **Where** it happened (file, line, identifier).
3. **What to do** (one concrete next action).

Bad:

```
⚠️ Oops! It looks like something went wrong while trying to load the
configuration. Please check your settings and try again. ❌
```

Good:

```
□ FAIL  master_config load — src/orchestrator.py:142
        Missing key 'simple.context_window' in dev/master_config.md.
        Edit the file and set a value ≥ 16384 (recommended: 131072).
```

## Logging

`print(...)` is acceptable in scripts; the standard library `logging` is
required in long-running services (api, telegram_bot, kanban_processor).

Log level conventions:

| Level     | When                                                 |
|-----------|------------------------------------------------------|
| `DEBUG`   | State transitions, IDs, sizes. Off by default.       |
| `INFO`    | Lifecycle events: started, loaded, written.          |
| `WARNING` | Recovered-from anomalies. Never normal operation.    |
| `ERROR`   | Operation failed. Caller will be notified.           |
| `CRITICAL`| Service must restart. Reserved.                      |

## Forbidden

- Emoji as decoration (✨ 🎉 🚀 in headers, etc.)
- Markdown tables with one column.
- Trailing exclamation marks in titles.
- "TODO:" without an associated proposal ID.
- "FIXME:" in committed code (file a proposal instead).
- ANSI colour codes in committed artifacts (terminal renderers vary).

## Permitted ornament — narrowly

- ASCII box-drawing for module banners (`╔ ═ ╗`, `║`, `╚ ═ ╝`).
- Em-dash (`—`) as separator. Never `--` or `~`.
- Vertical bar (`│`) inside box-drawn frames only.
- Right-pointing arrow (`→`) for transformations. Never `->`.

## How to verify your output

Read it aloud. If a line would sound theatrical in a meeting, cut it.
If a glyph doesn't carry meaning, remove it. If a sentence doesn't
change what the reader will do next, the reader doesn't need it.
