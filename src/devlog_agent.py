"""DevLog Agent — gathers evidence and synthesises markdown devlog posts.

This module provides the DevLogAgent class which:
1. Gathers evidence from git, gates, council, and test sources
2. Filters evidence using PathGuard (CSTR-DEVLOG-V2)
3. Synthesises a raw-markdown devlog post via the devlog_scribe role
4. Writes the draft to dev/devlogs/pending/ (project path, not vault)

The LLM is asked for markdown, not JSON. We stopped fighting the parser
and embraced what language models do naturally — prose in markdown.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from src.llm_client import llm
from src.models.devlog import DevLogConfig, DevLogPost
from src.orchestrator import get_role_config

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════════
#  Agent
# ════════════════════════════════════════════════════════════════════


class DevLogAgent:
    """Orchestrates devlog post generation from evidence gathering to file."""

    ROOT = Path(__file__).resolve().parent.parent  # cognitive-os/

    def __init__(self, config: DevLogConfig):
        self.config = config
        self.path_guard = self._create_path_guard()

    def _create_path_guard(self) -> Any:
        from src.path_guard import PathGuard
        return PathGuard(forbidden_patterns=self.config.forbidden_sources)

    # ------------------------------------------------------------------
    #  Gather — real data from the filesystem, not hallucinations
    # ------------------------------------------------------------------

    def gather_evidence(self, date_str: str) -> Dict[str, Any]:
        """Collect evidence from git, council memory, decisions, and tests."""
        evidence: Dict[str, Any] = {
            "date": date_str,
            "gathered_at": datetime.now().isoformat(),
        }
        evidence["git_commits"] = self._gather_git(date_str)
        evidence["council_verdicts"] = self._gather_council(date_str)
        evidence["gate_deltas"] = self._gather_gates(date_str)
        evidence["test_summary"] = self._gather_tests(date_str)
        return self._apply_pathguard(evidence)

    # -- git -----------------------------------------------------------

    def _gather_git(self, date_str: str) -> list[dict]:
        """Last ~30 commits from the given date (or recent if none match)."""
        commits: list[dict] = []
        try:
            # Try date-bounded first, fall back to just "recent"
            for since in [f"--since={date_str} --until={date_str}T23:59:59", ""]:
                cmd = ["git", "log", "--oneline", "--no-merges", "-n", "30"]
                if since:
                    cmd.insert(2, since)
                result = subprocess.run(
                    cmd, cwd=str(self.ROOT), capture_output=True, text=True, timeout=10
                )
                if result.stdout.strip():
                    break
            for line in result.stdout.strip().splitlines():
                parts = line.split(" ", 1)
                if len(parts) == 2:
                    commits.append({"sha": parts[0], "message": parts[1][:200]})
        except Exception:
            pass
        return commits

    # -- council verdicts ----------------------------------------------

    def _gather_council(self, date_str: str) -> list[dict]:
        """Council tasks from active/ that were created or completed on date_str."""
        verdicts: list[dict] = []
        active_dir = self.ROOT / "council_memory" / "active"
        if not active_dir.is_dir():
            return verdicts
        date_prefix = date_str  # "2026-05-30"
        for f in sorted(active_dir.glob("task_*.json"), reverse=True):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                created = data.get("timestamp_created", "")
                if date_prefix in created:
                    participants = data.get("models_participated", [])
                    verdicts.append({
                        "task_id": data.get("task_id", f.stem),
                        "user_input": data.get("user_input", "")[:200],
                        "status": data.get("status", "unknown"),
                        "roles": [p.get("role") for p in participants],
                        "models": [p.get("model_name") for p in participants],
                    })
            except Exception:
                pass
        return verdicts

    # -- gate deltas (proposal decisions) ------------------------------

    def _gather_gates(self, date_str: str) -> list[dict]:
        """Proposal decisions logged in dev/decisions/ on date_str."""
        gates: list[dict] = []
        dec_dir = self.ROOT / "dev" / "decisions"
        if not dec_dir.is_dir():
            return gates
        for f in sorted(dec_dir.glob("ARCH-*_log.md"), reverse=True):
            try:
                text = f.read_text(encoding="utf-8")
                # Extract frontmatter
                fm_match = re.search(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
                if not fm_match:
                    continue
                fm = {}
                for line in fm_match.group(1).splitlines():
                    if ":" in line:
                        k, v = line.split(":", 1)
                        fm[k.strip()] = v.strip()
                ts = fm.get("Timestamp", "")
                if date_str in ts:
                    gates.append({
                        "proposal_id": fm.get("Proposal ID", f.stem),
                        "decision": fm.get("Decision", "UNKNOWN"),
                        "approved_at": ts,
                        "approver": fm.get("Approver", ""),
                    })
            except Exception:
                pass
        return gates

    # -- tests ---------------------------------------------------------

    def _gather_tests(self, date_str: str) -> dict:
        """Count test files and try to run pytest --collect-only for counts."""
        summary: dict[str, Any] = {"test_files": 0, "test_count": 0, "error": None}
        tests_dir = self.ROOT / "tests"
        if tests_dir.is_dir():
            py_files = list(tests_dir.rglob("test_*.py"))
            summary["test_files"] = len(py_files)
        # Try pytest --collect-only (non-blocking, short timeout)
        try:
            result = subprocess.run(
                ["pytest", "--collect-only", "-q", "--no-header"],
                cwd=str(self.ROOT), capture_output=True, text=True, timeout=30
            )
            # Count lines with "::" (test items)
            summary["test_count"] = sum(
                1 for line in result.stdout.splitlines()
                if "::" in line and not line.startswith("=")
            )
        except Exception as e:
            summary["error"] = str(e)[:200]
        return summary

    # -- pathguard filter ----------------------------------------------

    def _apply_pathguard(self, evidence: Dict[str, Any]) -> Dict[str, Any]:
        """Strip forbidden paths from git commits."""
        if "git_commits" in evidence:
            evidence["git_commits"] = [
                c for c in evidence["git_commits"]
                if not self.path_guard.is_forbidden(c.get("path", ""))
            ]
        return evidence

    # ------------------------------------------------------------------
    #  Synthesise → raw markdown
    # ------------------------------------------------------------------

    def synthesise(self, date_str: str) -> str:
        """Gather evidence and produce a **raw markdown** devlog post.

        Returns the LLM's markdown output directly — no JSON parsing.
        """
        evidence = self.gather_evidence(date_str)
        evidence_hash = hashlib.sha256(
            json.dumps(evidence, sort_keys=True).encode()
        ).hexdigest()

        # Resolve role → model key
        try:
            role_cfg = get_role_config(self.config.council_role)
            model_key = role_cfg.get("model", self.config.council_role)
        except ValueError:
            role_cfg = {}
            model_key = self.config.council_role

        system_prompt = self._build_prompt()
        user_prompt = self._build_user_prompt(evidence)

        response = llm.generate_response(
            prompt=user_prompt,
            system_prompt=system_prompt,
            model=model_key,
            temperature=role_cfg.get("temperature", self.config.temperature),
            top_p=role_cfg.get("top_p", self.config.top_p),
            top_k=role_cfg.get("top_k", self.config.top_k),
            repeat_penalty=role_cfg.get("repeat_penalty", self.config.repeat_penalty),
            min_p=role_cfg.get("min_p", self.config.min_p),
            max_tokens=role_cfg.get("max_tokens", self.config.max_tokens),
            context_window=role_cfg.get("context_window", self.config.context_window),
            gpu_offload_ratio=role_cfg.get("gpu_offload_ratio", self.config.gpu_offload_ratio),
        )

        if response.startswith(("Error:", "error:", "No models", "Failed")):
            raise ValueError(f"LLM returned error: {response}")

        # Strip markdown fences if the model wrapped its output
        cleaned = response.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:markdown|md)?\s*\n?", "", cleaned)
            cleaned = re.sub(r"\n?```\s*$", "", cleaned)

        return cleaned

    def synthesize_post(self, evidence: Dict[str, Any]) -> "DevLogPost":
        """Synthesize a structured DevLogPost from evidence (test compatibility).

        This method exists for backward compatibility with tests that expect
        a JSON-based API. It calls the LLM, parses the JSON response, and
        returns a validated DevLogPost object.
        """
        from src.models.devlog import DevLogPost

        evidence_hash = hashlib.sha256(
            json.dumps(evidence, sort_keys=True).encode()
        ).hexdigest()

        # Resolve role → model key
        try:
            role_cfg = get_role_config(self.config.council_role)
            model_key = role_cfg.get("model", self.config.council_role)
        except ValueError:
            role_cfg = {}
            model_key = self.config.council_role

        system_prompt = self._build_prompt()
        user_prompt = self._build_user_prompt(evidence)

        response = llm.generate_response(
            prompt=user_prompt,
            system_prompt=system_prompt,
            model=model_key,
            temperature=role_cfg.get("temperature", self.config.temperature),
            top_p=role_cfg.get("top_p", self.config.top_p),
            top_k=role_cfg.get("top_k", self.config.top_k),
            repeat_penalty=role_cfg.get("repeat_penalty", self.config.repeat_penalty),
            min_p=role_cfg.get("min_p", self.config.min_p),
            max_tokens=role_cfg.get("max_tokens", self.config.max_tokens),
            context_window=role_cfg.get("context_window", self.config.context_window),
            gpu_offload_ratio=role_cfg.get("gpu_offload_ratio", self.config.gpu_offload_ratio),
        )

        if response.startswith(("Error:", "error:", "No models", "Failed")):
            raise ValueError(f"LLM returned error: {response}")

        # Parse JSON response
        try:
            data = json.loads(response)
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse LLM response as JSON: {e}")

        # Add evidence hash to the post data
        data["evidence_hash"] = evidence_hash

        # Validate and return DevLogPost
        return DevLogPost(**data)

    # ------------------------------------------------------------------
    #  Write to project path  (not vault — OutputRouter discipline)
    # ------------------------------------------------------------------

    PENDING_DIR = Path("dev/devlogs/pending")

    def write_to_pending(self, markdown: str, date_str: str) -> Path:
        """Save the draft to dev/devlogs/pending/YYYY-MM-DD_devlog.md."""
        self.PENDING_DIR.mkdir(parents=True, exist_ok=True)
        dest = self.PENDING_DIR / f"{date_str}_devlog.md"
        frontmatter = (
            f"---\ndate: {date_str}\n"
            f"generated: {datetime.now().isoformat()}\n"
            f"status: draft\n---\n\n"
        )
        dest.write_text(frontmatter + markdown, encoding="utf-8")
        logger.info("DevLog draft saved → %s", dest)
        return dest

    # ------------------------------------------------------------------
    #  Full pipeline
    # ------------------------------------------------------------------

    def generate_and_save(self, date_str: str) -> tuple[str, Path]:
        """Synthesise + save — returns (markdown, filepath)."""
        md = self.synthesise(date_str)
        path = self.write_to_pending(md, date_str)
        return md, path

    # ------------------------------------------------------------------
    #  Prompts
    # ------------------------------------------------------------------

    def _build_prompt(self) -> str:
        return """\
You are the DevLog Scribe for the Dark Maestro cognitive-os.

Output a public-facing devlog post in **raw markdown**. No JSON, no code
fences, no preamble — just the markdown post body.

Tone: direct, technical, build-in-public. Feature errors and failures,
don't hide them. Highlight interesting decisions, not routine work.

Structure your post like this:

# DevLog: YYYY-MM-DD — One-line summary

## What We Built
...

## Technical Decisions
...

## Gate Deltas
...

## Test Results
...

## Failures & Lessons
...

## Tags
#cognitivos #devlog #buildinpublic

Keep it under 2000 words. Start directly with the `# DevLog:` heading."""

    def _build_user_prompt(self, evidence: Dict[str, Any]) -> str:
        return f"""Write today's devlog post from this evidence:

{json.dumps(evidence, indent=2)}

Remember: raw markdown only. Start with `# DevLog: {evidence['date']} —`."""