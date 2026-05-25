"""HandoffPlanner — turns a council verdict into a code-ready checklist.

This is the core of ARCH-5DFB393F (Section A4 of the BETA handoff). The
planner sits between the boardroom/tech-board council and the editor
handoff: it reads the proposal + verdict + binding constraints, asks a
small local LLM to decompose the work into structured tasks, and emits
a Pydantic-validated ``HandoffPlan``.

Pipeline
--------
::

    proposal + verdict + constraints
              │
              │  strip_fences()    ← CSTR-PLANNER-V3
              ▼
        clean council report
              │
              │  LLM call (ministral-3-3b @ 0.3, 60s timeout)
              ▼
            raw JSON
              │
              │  json.loads + HandoffPlan.model_validate()   ← CSTR-PLANNER-V4
              ▼  (one retry on ValidationError, embedding the error in the prompt)
        HandoffPlan
              │
              ▼
       .to_markdown()  → handoff doc

Failure modes
-------------
- Timeout (60s) → raise ``PlannerTimeout``. Caller falls back to legacy
  regex extractor (CSTR-PLANNER-V2).
- LLM returns non-JSON or invalid schema twice → write dead-letter at
  ``dev/failed_routings/handoff_planner_<ts>.failed.md`` and raise
  ``PlannerValidationFailed``.
- Any other ``Exception`` from the LLM call → propagate up. Caller
  decides whether to fallback.

Binding constraints
-------------------
CSTR-PLANNER-V1 : no new deps (stdlib + Pydantic only — both installed)
CSTR-PLANNER-V2 : planner failure never blocks handoff (caller fallback)
CSTR-PLANNER-V3 : strip fences before the LLM sees text
CSTR-PLANNER-V4 : fail-fast Pydantic validation
CSTR-PLANNER-V5 : idempotent (deterministic LLM at temp 0.3 + sorted output)
CSTR-PLANNER-V6 : schema-stable output (HandoffPlan is the contract)
"""

from __future__ import annotations

import json
import logging
import re
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, List, Optional

from pydantic import ValidationError

from src.markdown_fence_parser import strip_fences
from src.models.handoff_plan import HandoffPlan, PlanSection, PlanTask
from src.paths import DEV_DIR

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════════
#  Module constants
# ════════════════════════════════════════════════════════════════════

#: Hard timeout on a single LLM call. The planner may issue up to two
#: calls (initial + one retry), so worst-case wall time is ~2×TIMEOUT.
#:
#: Originally 60s per Specialist amendment A2 from the boardroom
#: verdict. Bumped to 180s on 2026-05-25 after observing ministral-3-3b
#: timing out on the dashboard-migration handoff (~600 lines of
#: verdict + proposal body). The intent of the timeout is a safety
#: net against true hangs, not a performance target — 180s still
#: bounds worst-case planner cost at ~6 min (initial + retry).
LLM_TIMEOUT_SECONDS: float = 180.0

#: Where dead-letters land when the LLM emits invalid output twice. We
#: mirror ``api.py``'s convention rather than introducing a new const.
_DEAD_LETTER_DIR: Path = DEV_DIR / "failed_routings"


# ════════════════════════════════════════════════════════════════════
#  System prompt — the load-bearing constant (CREATIVE-A1, Specialist A1)
# ════════════════════════════════════════════════════════════════════

#: The hard-coded planner system prompt. Embeds:
#:   - Exact JSON schema (matches ``HandoffPlan`` Pydantic models)
#:   - Two worked examples
#:   - Discipline rules
#:
#: Profile-adaptive prompts are deferred to ``ARCH-CODER-PROFILE-REGISTRY``
#: per the scope trim in commit 5f8550c. Keep this as a module constant
#: rather than a YAML field — multi-line YAML escape rules made the
#: examples unreadable in master_config.md.
_PLANNER_SYSTEM_PROMPT: str = '''You are the Handoff Planner for the Dark Maestro Cognitive OS.

Your job: decompose a council verdict into a code-ready implementation
checklist for an editor agent (Qwen3-Coder-Next, Deepseek-Coder-V2-Lite,
or similar). The editor reads your output and flips straight to Act mode.

# OUTPUT FORMAT — STRICT

Emit ONLY a single JSON object. No prose, no commentary, no code fences,
no markdown headers. Just the JSON. The schema is:

{
  "proposal_id": "<ARCH-… or DEV-… proposal id>",
  "sections": [
    {
      "name": "<short section title>",
      "tasks": [
        {
          "id": "<one uppercase letter + digits, e.g. A1, B2>",
          "title": "<single-line, active, concise task title>",
          "subtasks": ["<step 1>", "<step 2>"],
          "acceptance": "<single-line acceptance criterion>",
          "constraints": ["<CSTR-X-V2>", "<H3>"],
          "file_paths": ["src/x.py", "tests/test_x.py"]
        }
      ]
    }
  ]
}

# DISCIPLINE RULES

1. EVERY task MUST have: id, title, acceptance. subtasks / constraints / file_paths may be empty lists.
2. Task ids are unique across the whole plan.
3. Task ids start with an uppercase letter (one) followed by digits: A1, A2, B1, B2.
4. title and acceptance are SINGLE-LINE strings — no embedded newlines.
5. subtasks are short imperative phrases, not full sentences.
6. file_paths are REPO-RELATIVE (e.g. "src/api.py", NOT "/abs/path" or "./src/api.py").
7. constraints reference binding-constraint ids from the proposal (CSTR-…, H1-H9) verbatim.
8. NEVER emit a placeholder or filler task. If you cannot decompose, emit a single task explaining the blocker.
9. Group related tasks into sections by logical theme (e.g. "Core wiring", "Tests", "Migration").

# EXAMPLE 1 — minimal

{
  "proposal_id": "ARCH-EXAMPLE-001",
  "sections": [
    {
      "name": "Core",
      "tasks": [
        {
          "id": "A1",
          "title": "Add output router to /process endpoint",
          "subtasks": ["import OutputRouter at module top", "instantiate at startup"],
          "acceptance": "calling /process now persists synthesis via OutputRouter.apply()",
          "constraints": ["H3"],
          "file_paths": ["src/api.py"]
        }
      ]
    }
  ]
}

# EXAMPLE 2 — multi-section with subtasks

{
  "proposal_id": "ARCH-EXAMPLE-002",
  "sections": [
    {
      "name": "Schema",
      "tasks": [
        {
          "id": "A1",
          "title": "Define PlanTask Pydantic model",
          "subtasks": ["fields: id, title, acceptance", "validator on id regex"],
          "acceptance": "PlanTask(id='a1', ...) raises ValidationError",
          "constraints": ["CSTR-PLANNER-V4"],
          "file_paths": ["src/models/handoff_plan.py"]
        }
      ]
    },
    {
      "name": "Tests",
      "tasks": [
        {
          "id": "B1",
          "title": "Cover PlanTask validation paths",
          "subtasks": ["happy case", "invalid id", "missing acceptance"],
          "acceptance": "pytest tests/test_handoff_plan.py reports 3 passing",
          "constraints": ["CSTR-PLANNER-V4"],
          "file_paths": ["tests/test_handoff_plan.py"]
        }
      ]
    }
  ]
}

# YOUR TURN

The user message contains the proposal, the council verdict, and the
binding constraints. Decompose them into the JSON schema above. ONLY
the JSON. No surrounding text.
'''


# ════════════════════════════════════════════════════════════════════
#  Exceptions
# ════════════════════════════════════════════════════════════════════


class PlannerError(Exception):
    """Base class for planner failures. Caller can catch this for fallback."""


class PlannerTimeout(PlannerError):
    """Raised when the LLM did not respond within ``LLM_TIMEOUT_SECONDS``."""


class PlannerValidationFailed(PlannerError):
    """Raised when the LLM returned invalid output twice.

    The ``dead_letter_path`` attribute points at the file holding the
    raw LLM response and the validation error, for post-mortem use.
    """

    def __init__(self, message: str, dead_letter_path: Path) -> None:
        super().__init__(message)
        self.dead_letter_path = dead_letter_path


# ════════════════════════════════════════════════════════════════════
#  LLM type stubs — Protocol-flavoured, but we keep it ducktyped to
#  avoid pulling Protocol just for one method.
# ════════════════════════════════════════════════════════════════════

#: The minimal LLM client surface the planner needs. ``llm_client.LLMClient``
#: satisfies this. Tests inject fakes that match this signature.
LLMClientLike = Any


# ════════════════════════════════════════════════════════════════════
#  HandoffPlanner
# ════════════════════════════════════════════════════════════════════


class HandoffPlanner:
    """Decomposes a council verdict into a ``HandoffPlan`` via one LLM call.

    The planner is stateless beyond the injected LLM client. Each call
    to :meth:`plan` is an independent transaction with its own retry
    and dead-letter handling.
    """

    def __init__(
        self,
        llm_client: Optional[LLMClientLike] = None,
        role_config_loader: Optional[Callable[[str], dict]] = None,
        dead_letter_dir: Optional[Path] = None,
    ) -> None:
        """Construct a planner.

        Args:
            llm_client: Anything with a ``generate_response(prompt, system_prompt, model, ...)``
                method returning ``str``. Defaults to the shared
                ``src.llm_client.llm`` singleton (resolved lazily so this
                module remains import-side-effect-free).
            role_config_loader: Callable taking a role key (``"handoff_planner"``)
                and returning the role's config dict. Defaults to
                ``src.orchestrator.get_role_config``. Injectable for tests.
            dead_letter_dir: Override for the dead-letter location. Defaults
                to ``dev/failed_routings`` (per :data:`_DEAD_LETTER_DIR`).
                Tests pass a tmp_path here to keep the real dir clean.
        """
        self._llm = llm_client  # lazy resolved in plan() if None
        self._role_loader = role_config_loader  # lazy resolved
        self._dead_letter_dir = dead_letter_dir or _DEAD_LETTER_DIR

    # ----------------------------------------------------------------
    #  Public API
    # ----------------------------------------------------------------

    def plan(
        self,
        proposal_id: str,
        proposal_body: str,
        council_report: str,
        binding_constraints: List[str],
    ) -> HandoffPlan:
        """Generate a ``HandoffPlan`` from a council verdict.

        Args:
            proposal_id: The proposal's id, e.g. ``ARCH-20260524-011510-5DFB393F``.
            proposal_body: Full markdown text of the proposal (frontmatter included
                is fine; the LLM tolerates it).
            council_report: Council deliberation / verdict text. May contain
                fenced code blocks — they will be stripped before the LLM sees them.
            binding_constraints: List of constraint ids that the plan must honour.

        Returns:
            A validated :class:`HandoffPlan`.

        Raises:
            PlannerTimeout: if any LLM call exceeds ``LLM_TIMEOUT_SECONDS``.
            PlannerValidationFailed: if the LLM emits invalid output twice.
        """
        # CSTR-PLANNER-V3: strip fences before the LLM sees the report.
        clean_report = strip_fences(council_report)

        user_prompt = self._build_user_prompt(
            proposal_id, proposal_body, clean_report, binding_constraints
        )

        # First attempt
        raw_response = self._call_llm(user_prompt)
        try:
            return self._parse_and_validate(raw_response, proposal_id)
        except (json.JSONDecodeError, ValidationError) as first_err:
            logger.warning(
                "HandoffPlanner: first attempt failed validation (%s). Retrying once.",
                type(first_err).__name__,
            )
            # Retry once with the error injected into the prompt.
            retry_prompt = self._build_retry_prompt(user_prompt, raw_response, first_err)
            retry_response = self._call_llm(retry_prompt)
            try:
                return self._parse_and_validate(retry_response, proposal_id)
            except (json.JSONDecodeError, ValidationError) as second_err:
                # Dead-letter and raise. The handoff_writer is responsible
                # for activating the legacy fallback (CSTR-PLANNER-V2).
                dead_letter = self._write_dead_letter(
                    proposal_id=proposal_id,
                    first_response=raw_response,
                    first_error=first_err,
                    retry_response=retry_response,
                    retry_error=second_err,
                )
                raise PlannerValidationFailed(
                    f"Planner emitted invalid output twice for {proposal_id}. "
                    f"See {dead_letter}.",
                    dead_letter_path=dead_letter,
                ) from second_err

    # ----------------------------------------------------------------
    #  Internals
    # ----------------------------------------------------------------

    def _resolve_llm(self) -> LLMClientLike:
        """Lazily import the default LLM client to keep this module
        side-effect-free at import time."""
        if self._llm is not None:
            return self._llm
        from src.llm_client import llm as default_llm  # local import on purpose
        return default_llm

    def _resolve_role_loader(self) -> Callable[[str], dict]:
        if self._role_loader is not None:
            return self._role_loader
        from src.orchestrator import get_role_config  # local import on purpose
        return get_role_config

    def _build_user_prompt(
        self,
        proposal_id: str,
        proposal_body: str,
        clean_report: str,
        binding_constraints: List[str],
    ) -> str:
        constraints_block = (
            "\n".join(f"- {c}" for c in binding_constraints)
            if binding_constraints
            else "(none specified)"
        )
        return (
            f"# PROPOSAL ID\n{proposal_id}\n\n"
            f"# PROPOSAL BODY\n{proposal_body}\n\n"
            f"# COUNCIL VERDICT (fences pre-stripped)\n{clean_report}\n\n"
            f"# BINDING CONSTRAINTS\n{constraints_block}\n\n"
            f"# YOUR OUTPUT\nReturn ONLY the JSON object per the schema in your system prompt."
        )

    def _build_retry_prompt(
        self,
        original_prompt: str,
        bad_response: str,
        validation_error: Exception,
    ) -> str:
        return (
            f"{original_prompt}\n\n"
            f"# YOUR PREVIOUS ATTEMPT FAILED VALIDATION\n"
            f"## Error\n{type(validation_error).__name__}: {validation_error}\n\n"
            f"## Your previous (rejected) response\n{bad_response}\n\n"
            f"# CORRECTIVE INSTRUCTION\n"
            f"Re-emit a fresh JSON object that satisfies the schema. Fix the issue above. "
            f"Return ONLY the JSON — no prose, no fences, no explanation."
        )

    def _call_llm(self, user_prompt: str) -> str:
        """Run one LLM call with a hard timeout.

        We use a ``ThreadPoolExecutor`` because ``signal.alarm`` is
        Unix-only and the dev box is Windows. The downside is that a
        timed-out call leaks until the underlying HTTP request itself
        gives up — but the planner returns to the caller as if it had
        raised ``PlannerTimeout``, which is what callers care about.
        """
        llm = self._resolve_llm()
        role = self._resolve_role_loader()("handoff_planner")

        def _invoke() -> str:
            return llm.generate_response(
                prompt=user_prompt,
                system_prompt=_PLANNER_SYSTEM_PROMPT,
                model=role["model"],
                temperature=role.get("temperature", 0.3),
                top_p=role.get("top_p", 0.9),
                top_k=role.get("top_k", 40),
                min_p=role.get("min_p", 0.1),
                max_tokens=role.get("max_tokens", 8192),
                context_window=role.get("context_window", 131072),
                gpu_layers=role.get("gpu_layers", -1),
            )

        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(_invoke)
            try:
                return future.result(timeout=LLM_TIMEOUT_SECONDS)
            except FutureTimeoutError as exc:
                raise PlannerTimeout(
                    f"Planner LLM call exceeded {LLM_TIMEOUT_SECONDS}s timeout."
                ) from exc

    def _parse_and_validate(self, raw_response: str, proposal_id: str) -> HandoffPlan:
        """Extract JSON from the response and validate against ``HandoffPlan``.

        We are defensive about the LLM occasionally wrapping its output
        in a markdown code fence even though the prompt forbids it — we
        strip a single outer triple-backtick block (with optional ``json``
        / ``markdown`` tag) if present. We do NOT try to recover from
        arbitrary prose around the JSON; that's a validation failure and
        we let the retry handle it.
        """
        cleaned = _peel_outer_fence(raw_response).strip()
        # Defensively trim "data:" / "```" prefixes some local models
        # like to add. Don't over-engineer; let validation reject the
        # rest.
        if not cleaned:
            raise json.JSONDecodeError("Empty LLM response", "", 0)

        # Some LLMs prepend a short prose intro before the JSON. Slice
        # from the first '{' to the matching last '}' if both exist.
        first_brace = cleaned.find("{")
        last_brace = cleaned.rfind("}")
        if first_brace > 0 and last_brace > first_brace:
            cleaned = cleaned[first_brace : last_brace + 1]

        # Defensively repair bare backslashes that ministral-3-3b
        # sometimes emits inside string values. ``json.loads`` rejects
        # ``"\\X"`` for any X not in {"\\", "/", "b", "f", "n", "r", "t",
        # "u", `"`}. The model especially likes prepending ``\`` to
        # word chars when quoting CLI-ish snippets in subtasks.
        # We rewrite ``\X`` → ``\\X`` for those bad X, leaving valid
        # JSON escapes alone. This is best-effort: if the model emits
        # genuinely broken JSON elsewhere, validation will still fail
        # and the retry will fire.
        cleaned = _repair_bare_backslashes(cleaned)

        data = json.loads(cleaned)

        # Allow the LLM to omit proposal_id (we always know it) — inject
        # ours if missing. We do NOT override if present; that would
        # silently mask a mistake.
        if isinstance(data, dict) and "proposal_id" not in data:
            data["proposal_id"] = proposal_id

        return HandoffPlan.model_validate(data)

    def _write_dead_letter(
        self,
        proposal_id: str,
        first_response: str,
        first_error: Exception,
        retry_response: str,
        retry_error: Exception,
    ) -> Path:
        self._dead_letter_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%dT%H%M%S_%f")
        path = self._dead_letter_dir / f"handoff_planner_{ts}.failed.md"
        body = (
            f"# HandoffPlanner dead-letter\n\n"
            f"- proposal_id: {proposal_id}\n"
            f"- timestamp: {ts}\n"
            f"- first_error: {type(first_error).__name__}: {first_error}\n"
            f"- retry_error: {type(retry_error).__name__}: {retry_error}\n\n"
            f"## First (rejected) response\n\n"
            f"```\n{first_response}\n```\n\n"
            f"## Retry (also rejected) response\n\n"
            f"```\n{retry_response}\n```\n"
        )
        path.write_text(body, encoding="utf-8")
        return path


# ════════════════════════════════════════════════════════════════════
#  Module-private helpers
# ════════════════════════════════════════════════════════════════════


_OUTER_FENCE_RE: re.Pattern[str] = re.compile(
    r"^\s*```(?:json|markdown)?\s*\n(.*?)\n```\s*$",
    re.DOTALL,
)


def _peel_outer_fence(text: str) -> str:
    """If ``text`` is wrapped in a single outer markdown code fence,
    return the inner contents; otherwise return ``text`` unchanged.

    We only peel ONE level. Nested fences are left for the validator
    to choke on, which is the right signal that the LLM ignored the
    "no fences" rule and needs a retry.
    """
    match = _OUTER_FENCE_RE.match(text)
    if match:
        return match.group(1)
    return text


# JSON spec: a backslash may be followed by ONE of: " \ / b f n r t
# (literal escape chars) or u + 4 hex digits.
# This regex matches a backslash that is NOT part of a valid escape.
# Greedy alternation: match ``\\`` as a pair first (so its second
# backslash isn't seen as a stray); same for other valid escapes.
# What's LEFT over after the alternation is by definition invalid.
_VALID_ESCAPE_RE: re.Pattern[str] = re.compile(
    r'\\(?:["\\/bfnrt]|u[0-9a-fA-F]{4})'
)


def _repair_bare_backslashes(text: str) -> str:
    """Escape bare backslashes that would break ``json.loads``.

    Rewrites ``\\X`` to ``\\\\X`` for any X that's not a valid JSON
    escape. Conservative: walks the string once, recognises valid
    escapes as pairs, and only doubles standalone backslashes.

    Background: ``ministral-3-3b`` (the default planner model) often
    emits things like ``"import \\W from foo"`` inside subtasks. The
    proper fix is at prompt level, but defensive parsing here pays
    off in practice and is easy to remove if the model behaviour
    improves.
    """
    out: list[str] = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch != "\\":
            out.append(ch)
            i += 1
            continue
        # We have a backslash. Try to match a valid escape starting here.
        m = _VALID_ESCAPE_RE.match(text, i)
        if m:
            out.append(m.group(0))
            i = m.end()
        else:
            # Bare backslash → double it
            out.append("\\\\")
            i += 1
    return "".join(out)
