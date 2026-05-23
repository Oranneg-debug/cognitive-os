"""
Regenerate a beta-testing handoff from the council_memory JSON memory.

The scribe role keeps failing on long transcripts (LM Studio ctx-decay quirk),
producing 3-KB stub handoffs containing only the n_keep>n_ctx error. But the
chairman's audit_report + definitive_blueprint + per-role opinions are intact
in the task JSON. This script rebuilds the handoff from that JSON, using the
same beta-handoff template the orchestrator uses.

Usage:
    python -m scripts.regenerate_handoff <proposal_id> <task_id>

Example:
    python -m scripts.regenerate_handoff ARCH-20260522-205800-DA5B0A2D task_20260523_012532_6dfbdb27
"""
from __future__ import annotations

import io
import json
import re
import sys
from datetime import datetime
from pathlib import Path

# Force UTF-8 stdout so emoji + arrows don't crash on Windows cp1252.
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_PATH = REPO_ROOT.parent / "dev" / "templates" / "beta-handoff-template.md"
PROPOSALS_DIR = REPO_ROOT / "dev" / "proposals"
HANDOFFS_DIR = REPO_ROOT / "dev" / "handoffs"
COUNCIL_ACTIVE = REPO_ROOT / "council_memory" / "active"
COUNCIL_ARCHIVED = REPO_ROOT / "council_memory" / "archived"


def find_task_json(task_id: str) -> Path | None:
    """Locate a task JSON file in active/ or archived/."""
    name = f"{task_id}.json" if not task_id.endswith(".json") else task_id
    candidates = [COUNCIL_ACTIVE / name]
    candidates.extend(COUNCIL_ARCHIVED.rglob(name))
    for c in candidates:
        if c.exists():
            return c
    return None


def find_proposal(proposal_id: str) -> Path | None:
    """Find the proposal markdown file by ID."""
    matches = list(PROPOSALS_DIR.glob(f"{proposal_id}_PROPOSAL.md"))
    return matches[0] if matches else None


def find_kanban_card_id(proposal_text: str) -> str:
    """Extract the ^[ARCH-…] kanban card id from a proposal."""
    m = re.search(r"\^\[(?:DEV|ARCH|NLST)-[A-Z0-9-]+\]", proposal_text)
    return m.group(0) if m else ""


def extract_chairman_keys(d: dict) -> dict:
    """Pull audit_report / definitive_blueprint / final_decision / veto_points
    from oversight_analysis.raw_analysis (which is markdown-wrapped JSON).
    Returns a dict with any keys that parsed successfully.
    """
    oa = d.get("oversight_analysis") or {}
    raw = oa.get("raw_analysis", "") if isinstance(oa, dict) else str(oa)
    m = re.search(r"```json\s*(.+?)\s*```", raw, re.DOTALL)
    if m:
        raw = m.group(1)
    try:
        return json.loads(raw)
    except Exception:
        return {}


def safe_role_opinion(raw: str) -> str:
    """Try to extract a readable narrative from a role's opinion JSON."""
    if not raw:
        return ""
    s = str(raw).strip()
    # If it's an error stub, return a one-liner instead of the whole dump.
    if s.startswith("{") and '"error"' in s[:200]:
        try:
            j = json.loads(s)
            if "error" in j and "raw" in j:
                return f"_[role failed: {j['error'][:200]}]_"
        except Exception:
            pass
    # If it's a JSON object, pretty-print salient keys.
    if s.startswith("{"):
        try:
            j = json.loads(s)
            lines: list[str] = []
            for key in (
                "technical_analysis",
                "audit_report",
                "definitive_blueprint",
                "critical_feedback",
                "logical_structure",
                "transition_reason",
                "context_summary",
                "reasoning",
                "actionable_steps",
                "veto_points",
                "next_step",
                "approved",
                "final_decision",
                "recommendation",
            ):
                if key in j:
                    v = j[key]
                    if isinstance(v, (dict, list)):
                        v = json.dumps(v, indent=2, ensure_ascii=False)
                    lines.append(f"**{key}**: {v}")
            if lines:
                return "\n\n".join(lines)
        except Exception:
            pass
    return s


def build_summary(d: dict, chairman: dict) -> str:
    """Build the Executive Summary section."""
    final = chairman.get("final_decision") or "(no explicit final_decision; substance is APPROVAL per audit_report)"
    audit = chairman.get("audit_report", "")
    parts = [
        f"**Final Decision**: {final}",
        "",
        "**Audit Report**:",
        "",
        audit if audit else "_(no audit_report)_",
    ]
    return "\n".join(parts)


def build_difficulties(chairman: dict, opinions: list[dict]) -> str:
    """Build the Difficulties & Constraints section from veto points + critic role."""
    parts: list[str] = []
    vetoes = chairman.get("veto_points") or []
    if vetoes:
        parts.append("**Binding Vetoes (from chairman)**:")
        parts.append("")
        for v in vetoes:
            if isinstance(v, dict):
                desc = v.get("description") or json.dumps(v, ensure_ascii=False)
                parts.append(f"- {desc}")
            else:
                parts.append(f"- {v}")
        parts.append("")

    # Critic role's veto points often have detailed risk descriptions.
    critic = next(
        (o for o in opinions if "critic" in (o.get("role") or "").lower()
         and not o.get("role", "").startswith("brand_guard_")),
        None,
    )
    if critic:
        raw = str(critic.get("opinion", ""))
        if raw.startswith("{"):
            try:
                j = json.loads(raw)
                cvs = j.get("veto_points") or []
                if cvs:
                    parts.append("**Risk Register (from technical critic)**:")
                    parts.append("")
                    for v in cvs:
                        if isinstance(v, dict):
                            risk = v.get("risk_level", "?")
                            desc = v.get("description", json.dumps(v, ensure_ascii=False))
                            parts.append(f"- **{risk}**: {desc}")
                        else:
                            parts.append(f"- {v}")
            except Exception:
                pass
    return "\n".join(parts) if parts else "_No specific difficulties extracted._"


def build_tasks(chairman: dict) -> str:
    """Build the Implementation Tasks checklist from definitive_blueprint."""
    bp = chairman.get("definitive_blueprint", "")
    if not bp:
        return "- [ ] See full council report below for implementation guidance"

    # Sometimes blueprint is a dict; flatten to a readable block.
    if isinstance(bp, dict):
        bp = json.dumps(bp, indent=2, ensure_ascii=False)

    bp_str = str(bp)

    # Try to extract numbered tasks (1. … 2. … etc.) into a checklist.
    tasks: list[str] = []
    for line in bp_str.splitlines():
        stripped = line.strip()
        m = re.match(r"^(\d+\.|-)\s+(.+)", stripped)
        if m:
            tasks.append(f"- [ ] {m.group(2).strip()}")

    if tasks:
        return "\n".join(tasks)

    # Fallback: present blueprint as a single block with a top-level task.
    return (
        "- [ ] Implement the system per the definitive blueprint:\n\n"
        + "  > " + bp_str.replace("\n", "\n  > ")
    )


def build_full_report(d: dict, chairman: dict, opinions: list[dict]) -> str:
    """Build the expandable full council report."""
    out: list[str] = []
    out.append(f"**Task ID**: `{d.get('task_id')}`")
    out.append(f"**Pattern**: `{d.get('pattern_used')}`")
    out.append(f"**Completed**: {d.get('timestamp_completed', '?')}")
    out.append("")
    out.append("### Chairman / Overseer Synthesis")
    out.append("")
    for k in ("audit_report", "definitive_blueprint", "final_decision", "veto_points"):
        if k in chairman:
            v = chairman[k]
            if isinstance(v, (dict, list)):
                v = json.dumps(v, indent=2, ensure_ascii=False)
            out.append(f"#### {k}")
            out.append("")
            out.append(f"```\n{v}\n```")
            out.append("")
    out.append("### Per-Role Opinions")
    out.append("")
    for op in opinions:
        role = op.get("role", "?")
        model = op.get("model_name", "?")
        ts = op.get("timestamp_completed", "?")
        body = safe_role_opinion(op.get("opinion", ""))
        out.append(f"#### {role} — `{model}` — {ts}")
        out.append("")
        out.append(body)
        out.append("")
    return "\n".join(out)


def regenerate(proposal_id: str, task_id: str) -> Path:
    """Rebuild a beta handoff from the task JSON. Returns the written path."""
    task_path = find_task_json(task_id)
    if task_path is None:
        raise FileNotFoundError(f"task {task_id} not found in active or archived")

    proposal_path = find_proposal(proposal_id)
    if proposal_path is None:
        raise FileNotFoundError(f"proposal {proposal_id} not found in {PROPOSALS_DIR}")

    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    proposal_text = proposal_path.read_text(encoding="utf-8")
    d = json.loads(task_path.read_text(encoding="utf-8"))

    chairman = extract_chairman_keys(d)
    opinions = d.get("models_participated") or []
    kanban_card_id = find_kanban_card_id(proposal_text)

    summary = build_summary(d, chairman)
    difficulties = build_difficulties(chairman, opinions)
    tasks = build_tasks(chairman)
    full_report = build_full_report(d, chairman, opinions)

    # Count tasks for frontmatter
    task_count = sum(1 for ln in tasks.splitlines() if ln.strip().startswith("- [ ]"))

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    content = template
    # Legacy template placeholders
    content = content.replace("DEV-YYYYMMDD-HHMMSS-XXXX", proposal_id)
    content = content.replace("YYYY-MM-DD HH:MM:SS", timestamp)
    content = content.replace(
        'kanban_card_id: "^[DEV-YYYYMMDDHHMMSS-XXXX]"',
        f'kanban_card_id: "{kanban_card_id}"',
    )
    # Section placeholders
    content = content.replace("<!-- COUNCIL_SUMMARY -->", summary)
    content = content.replace("<!-- COUNCIL_DIFFICULTIES -->", difficulties)
    content = content.replace("<!-- COUNCIL_TASKS -->", tasks)
    content = content.replace("<!-- COUNCIL_FULL_REPORT -->", full_report)
    # Frontmatter task count
    content = content.replace(
        "tasks_completed: 0\ntasks_total: 0",
        f"tasks_completed: 0\ntasks_total: {task_count}",
    )

    HANDOFFS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = HANDOFFS_DIR / f"{proposal_id}_BETA_HANDOFF.md"

    # Backup any existing broken handoff
    if out_path.exists():
        backup = out_path.with_suffix(
            f".bak.{datetime.now().strftime('%Y%m%d-%H%M%S')}.md"
        )
        out_path.rename(backup)
        print(f"  backed up existing handoff -> {backup.name}")

    out_path.write_text(content, encoding="utf-8")
    print(f"  wrote {out_path}  ({out_path.stat().st_size} bytes, {task_count} tasks)")
    return out_path


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    proposal_id, task_id = argv[1], argv[2]
    regenerate(proposal_id, task_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
