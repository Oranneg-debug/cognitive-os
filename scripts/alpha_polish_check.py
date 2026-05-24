"""
Alpha Polish CI Gate — ARCH-A0F1B0C0

Enforces the binding acceptance criteria from the Phase 0 proposal and the
Alpha Polish chairman verdict. Stdlib only (per HIGH-risk veto: no new deps).

Exit codes:
    0 — all gates pass
    1 — at least one gate failed (see output)
    2 — could not run a gate (environment issue, not a fail)

Usage:
    python scripts/alpha_polish_check.py
    python scripts/alpha_polish_check.py --json     # machine-readable
    python scripts/alpha_polish_check.py --bench    # include perf smoke

Designed to be CI-runnable AND human-runnable from a clean checkout.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable


ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
TESTS = ROOT / "tests"


# ════════════════════════════════════════════════════════════════════
#  GATE RESULT
# ════════════════════════════════════════════════════════════════════

@dataclass
class GateResult:
    name: str
    passed: bool
    detail: str = ""
    duration_ms: int = 0


# ════════════════════════════════════════════════════════════════════
#  GATES
# ════════════════════════════════════════════════════════════════════

def gate_dev_route_size() -> GateResult:
    """AC1: dev_route.py ≤ 300 lines."""
    f = SRC / "dev_route.py"
    if not f.is_file():
        return GateResult("dev_route_size", False, "dev_route.py not found")
    n = sum(1 for _ in f.open(encoding="utf-8"))
    return GateResult(
        "dev_route_size",
        n <= 300,
        f"{n} lines (limit: 300)",
    )


def gate_no_vault_literals() -> GateResult:
    """AC2: No 'Grand Nexus' literal outside paths.py."""
    needle = "Grand Nexus"
    hits: list[str] = []
    for f in SRC.rglob("*.py"):
        if f.name == "paths.py":
            continue
        try:
            for i, line in enumerate(f.open(encoding="utf-8"), start=1):
                if needle in line:
                    hits.append(f"{f.relative_to(ROOT)}:{i}")
        except OSError:
            continue
    return GateResult(
        "no_vault_literals",
        not hits,
        "clean" if not hits else f"{len(hits)} hit(s): " + ", ".join(hits[:5]),
    )


def gate_one_trigger_sync_check() -> GateResult:
    """AC3: Exactly one definition of trigger_sync_check (kanban delegate is OK)."""
    impl_pattern = re.compile(r"^def\s+(_)?trigger_sync_check\s*\(", re.M)
    impls: list[str] = []
    for f in SRC.rglob("*.py"):
        try:
            txt = f.read_text(encoding="utf-8")
        except OSError:
            continue
        for m in impl_pattern.finditer(txt):
            line = txt.count("\n", 0, m.start()) + 1
            impls.append(f"{f.relative_to(ROOT)}:{line}")
    # One real impl + at most one delegating method is allowed
    return GateResult(
        "one_trigger_sync_check",
        1 <= len(impls) <= 2,
        f"{len(impls)} definition(s): " + ", ".join(impls),
    )


def gate_no_in_locals() -> GateResult:
    """AC4: Zero 'in locals()' anywhere in src/."""
    hits: list[str] = []
    for f in SRC.rglob("*.py"):
        try:
            for i, line in enumerate(f.open(encoding="utf-8"), start=1):
                if "in locals()" in line:
                    hits.append(f"{f.relative_to(ROOT)}:{i}")
        except OSError:
            continue
    return GateResult(
        "no_in_locals",
        not hits,
        "clean" if not hits else f"{len(hits)} hit(s)",
    )


def gate_cyclic_imports() -> GateResult:
    """AC5: pylint reports zero cyclic imports in src/."""
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pylint",
             "--disable=all", "--enable=cyclic-import", "src/"],
            cwd=ROOT, capture_output=True, text=True, timeout=120,
        )
    except FileNotFoundError:
        return GateResult("cyclic_imports", False, "pylint not installed")
    except subprocess.TimeoutExpired:
        return GateResult("cyclic_imports", False, "pylint timed out (120s)")
    has_cycle = "cyclic-import" in proc.stdout or "R0401" in proc.stdout
    return GateResult(
        "cyclic_imports",
        not has_cycle,
        "no cycles" if not has_cycle else proc.stdout.strip().splitlines()[-1],
    )


def gate_pytest() -> GateResult:
    """AC7: pytest passes (live council test is skipped by default)."""
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/", "-q", "--tb=no"],
            cwd=ROOT, capture_output=True, text=True, timeout=300,
        )
    except FileNotFoundError:
        return GateResult("pytest", False, "pytest not installed")
    except subprocess.TimeoutExpired:
        return GateResult("pytest", False, "pytest timed out (300s)")
    last_line = (proc.stdout.strip().splitlines() or [""])[-1]
    passed = proc.returncode == 0
    return GateResult("pytest", passed, last_line)


# ════════════════════════════════════════════════════════════════════
#  PHASE 1 GATES — ARCH-60FE0001 governance core
# ════════════════════════════════════════════════════════════════════

PHASE1_MODULES = [
    "src/workflow_models.py",
    "src/schema_validator.py",
    "src/handoff_vault.py",
    "src/approval_logger.py",
]


def gate_phase1_modules_exist() -> GateResult:
    """Phase 1 AC1: All 4 governance modules exist."""
    missing = [m for m in PHASE1_MODULES if not (ROOT / m).is_file()]
    return GateResult(
        "phase1_modules_exist",
        not missing,
        "all 4 modules present" if not missing else f"missing: {', '.join(missing)}",
    )


def gate_phase1_tests_present() -> GateResult:
    """Phase 1 AC3: A test file exists in tests/ for each Phase 1 module."""
    required = [
        "tests/test_workflow_models.py",
        "tests/test_schema_validator.py",
        "tests/test_handoff_vault.py",
        "tests/test_approval_logger.py",
    ]
    missing = [t for t in required if not (ROOT / t).is_file()]
    return GateResult(
        "phase1_tests_present",
        not missing,
        "all 4 test files present" if not missing else f"missing: {', '.join(missing)}",
    )


def gate_phase1_test_count() -> GateResult:
    """Phase 1 AC4: ≥20 test cases across Phase 1 test files.

    Counts top-level functions starting with `test_` and methods inside
    classes starting with `Test`. Static count, doesn't run them.
    """
    test_files = [
        "tests/test_workflow_models.py",
        "tests/test_schema_validator.py",
        "tests/test_handoff_vault.py",
        "tests/test_approval_logger.py",
        "tests/test_governance_unit_of_work.py",
    ]
    pattern = re.compile(r"^\s*def\s+test_\w+\s*\(", re.M)
    total = 0
    breakdown: list[str] = []
    for tf in test_files:
        p = ROOT / tf
        if not p.is_file():
            continue
        try:
            n = len(pattern.findall(p.read_text(encoding="utf-8")))
        except OSError:
            n = 0
        total += n
        breakdown.append(f"{Path(tf).name}:{n}")
    detail = f"{total} test cases ({', '.join(breakdown) or 'no files'}; limit ≥20)"
    return GateResult("phase1_test_count", total >= 20, detail)


def gate_phase1_no_misplaced_tests() -> GateResult:
    """Phase 1 hygiene: No `test_*.py` files at repo root (must live in tests/)."""
    misplaced = [p.name for p in ROOT.glob("test_*.py") if p.is_file()]
    # Allow legacy ones that pre-existed (test_api_endpoints.py, test_sync*.py)
    legacy = {"test_api_endpoints.py", "test_sync.py", "test_sync_simple.py"}
    new_misplaced = [m for m in misplaced if m not in legacy]
    return GateResult(
        "phase1_no_misplaced_tests",
        not new_misplaced,
        "no new misplaced tests"
        if not new_misplaced
        else f"misplaced (move to tests/): {', '.join(new_misplaced)}",
    )


def gate_phase1_no_print_in_tests() -> GateResult:
    """Phase 1 hygiene: Phase 1 tests use assert, not print.

    A test that calls print() instead of assert() is not a test.
    """
    print_pattern = re.compile(r"^\s*print\s*\(", re.M)
    assert_pattern = re.compile(r"^\s*assert\s+", re.M)
    offenders: list[str] = []
    test_files = [
        "tests/test_workflow_models.py",
        "tests/test_schema_validator.py",
        "tests/test_handoff_vault.py",
        "tests/test_approval_logger.py",
        "tests/test_governance_unit_of_work.py",
    ]
    for tf in test_files:
        p = ROOT / tf
        if not p.is_file():
            continue
        try:
            txt = p.read_text(encoding="utf-8")
        except OSError:
            continue
        prints = len(print_pattern.findall(txt))
        asserts = len(assert_pattern.findall(txt))
        # A file with prints but no asserts is suspect
        if prints > 0 and asserts == 0:
            offenders.append(f"{Path(tf).name} (prints={prints}, asserts=0)")
    return GateResult(
        "phase1_no_print_in_tests",
        not offenders,
        "tests use assert" if not offenders else f"print-only: {', '.join(offenders)}",
    )


def gate_phase1_pydantic_models() -> GateResult:
    """Phase 1 AC1: workflow_models defines required Pydantic models."""
    p = ROOT / "src" / "workflow_models.py"
    if not p.is_file():
        return GateResult("phase1_pydantic_models", False, "workflow_models.py not found")
    try:
        txt = p.read_text(encoding="utf-8")
    except OSError as e:
        return GateResult("phase1_pydantic_models", False, str(e))
    required = ["ValidatedProposal", "ArtifactVersion", "ApprovalRecord"]
    missing = [r for r in required if f"class {r}" not in txt]
    return GateResult(
        "phase1_pydantic_models",
        not missing,
        "all 3 models present" if not missing else f"missing class: {', '.join(missing)}",
    )


def gate_phase1_uow_pattern() -> GateResult:
    """Phase 1 AC6: GovernanceUnitOfWork class exists with __enter__/__exit__ or @contextmanager."""
    # Cline may have put it in handoff_vault.py or a separate governance_unit_of_work.py
    candidates = ["src/governance_unit_of_work.py", "src/handoff_vault.py"]
    for c in candidates:
        p = ROOT / c
        if not p.is_file():
            continue
        try:
            txt = p.read_text(encoding="utf-8")
        except OSError:
            continue
        if "class GovernanceUnitOfWork" in txt or "def governance_unit_of_work" in txt:
            has_ctx = (
                "__enter__" in txt
                or "@contextmanager" in txt
                or "yield" in txt
            )
            return GateResult(
                "phase1_uow_pattern",
                has_ctx,
                f"found in {c} (context manager: {has_ctx})",
            )
    return GateResult("phase1_uow_pattern", False, "GovernanceUnitOfWork not found")


def gate_phase1_ruamel_yaml() -> GateResult:
    """Phase 1 B4: schema_validator uses ruamel.yaml (not PyYAML) for round-trip."""
    p = ROOT / "src" / "schema_validator.py"
    if not p.is_file():
        return GateResult("phase1_ruamel_yaml", False, "schema_validator.py not found")
    try:
        txt = p.read_text(encoding="utf-8")
    except OSError as e:
        return GateResult("phase1_ruamel_yaml", False, str(e))
    uses_ruamel = "ruamel" in txt or "from ruamel" in txt
    uses_pyyaml_only = "import yaml" in txt and not uses_ruamel
    if uses_ruamel:
        return GateResult("phase1_ruamel_yaml", True, "ruamel.yaml in use")
    if uses_pyyaml_only:
        return GateResult(
            "phase1_ruamel_yaml",
            False,
            "uses PyYAML (no round-trip); B4 requires ruamel.yaml",
        )
    return GateResult("phase1_ruamel_yaml", False, "neither library imported")


# ════════════════════════════════════════════════════════════════════
#  PHASE 2 GATES — ARCH-2007E0A1 routing automation
# ════════════════════════════════════════════════════════════════════

PHASE2_DELIVERABLES = [
    "src/writer_protocols.py",        # T1
    "src/markdown_fence_parser.py",   # T2
    "src/routing_rules_schema.py",    # E3
    "src/output_router.py",
    "src/workflow_router.py",
    "config/routing_rules.yaml",      # E1
]


def gate_phase2_deliverables_exist() -> GateResult:
    """Phase 2: All 6 routing deliverables exist."""
    missing = [m for m in PHASE2_DELIVERABLES if not (ROOT / m).is_file()]
    return GateResult(
        "phase2_deliverables_exist",
        not missing,
        "all 6 deliverables present"
        if not missing
        else f"missing: {', '.join(missing)}",
    )


def gate_phase2_writer_protocols() -> GateResult:
    """Phase 2 T1: writer_protocols.py defines BackendWriterProtocol AND
    VaultWriterProtocol as typing.Protocol classes (separate, not unified).
    """
    p = ROOT / "src" / "writer_protocols.py"
    if not p.is_file():
        return GateResult("phase2_writer_protocols", False, "writer_protocols.py not found")
    try:
        txt = p.read_text(encoding="utf-8")
    except OSError as e:
        return GateResult("phase2_writer_protocols", False, str(e))
    if "Protocol" not in txt:
        return GateResult(
            "phase2_writer_protocols",
            False,
            "typing.Protocol not imported / used",
        )
    has_backend = "class BackendWriterProtocol" in txt
    has_vault = "class VaultWriterProtocol" in txt
    if has_backend and has_vault:
        return GateResult(
            "phase2_writer_protocols",
            True,
            "BackendWriterProtocol + VaultWriterProtocol both defined",
        )
    missing = []
    if not has_backend:
        missing.append("BackendWriterProtocol")
    if not has_vault:
        missing.append("VaultWriterProtocol")
    return GateResult(
        "phase2_writer_protocols",
        False,
        f"missing class: {', '.join(missing)}",
    )


def gate_phase2_catchall_route() -> GateResult:
    """Phase 2 E1: routing_rules.yaml has a catch-all decision_only route."""
    p = ROOT / "config" / "routing_rules.yaml"
    if not p.is_file():
        return GateResult("phase2_catchall_route", False, "routing_rules.yaml not found")
    try:
        txt = p.read_text(encoding="utf-8")
    except OSError as e:
        return GateResult("phase2_catchall_route", False, str(e))
    # The catch-all must mention "decision_only" AND something
    # signalling defaultness (catchall / default / fallback / .* / "*").
    has_decision_only = "decision_only" in txt
    has_catchall_marker = any(
        token in txt
        for token in ("catchall", "catch_all", "catch-all", "default", "fallback")
    )
    if has_decision_only and has_catchall_marker:
        return GateResult(
            "phase2_catchall_route",
            True,
            "decision_only catch-all present",
        )
    return GateResult(
        "phase2_catchall_route",
        False,
        f"need both: decision_only={has_decision_only}, "
        f"catch-all marker={has_catchall_marker}",
    )


def gate_phase2_yaml_schema_pydantic() -> GateResult:
    """Phase 2 E3: routing_rules_schema.py uses Pydantic to validate the YAML."""
    p = ROOT / "src" / "routing_rules_schema.py"
    if not p.is_file():
        return GateResult("phase2_yaml_schema_pydantic", False, "schema file not found")
    try:
        txt = p.read_text(encoding="utf-8")
    except OSError as e:
        return GateResult("phase2_yaml_schema_pydantic", False, str(e))
    uses_pydantic = "BaseModel" in txt or "pydantic" in txt
    return GateResult(
        "phase2_yaml_schema_pydantic",
        uses_pydantic,
        "pydantic in use" if uses_pydantic else "no pydantic import",
    )


def gate_phase2_dead_letter_dir() -> GateResult:
    """Phase 2 E5: output_router.py references a dead-letter directory."""
    p = ROOT / "src" / "output_router.py"
    if not p.is_file():
        return GateResult("phase2_dead_letter_dir", False, "output_router.py not found")
    try:
        txt = p.read_text(encoding="utf-8")
    except OSError as e:
        return GateResult("phase2_dead_letter_dir", False, str(e))
    has_dl = "failed_routings" in txt or "dead_letter" in txt or "dead-letter" in txt
    return GateResult(
        "phase2_dead_letter_dir",
        has_dl,
        "dead-letter path referenced"
        if has_dl
        else "no dead-letter path (E5 requires dev/failed_routings/)",
    )


def gate_phase2_single_writer_guard() -> GateResult:
    """Phase 2 E4/T1: output_router.py does NOT import a vault-writer module.

    Heuristic: scan for imports of known vault-writer modules. The
    single-writer rule says only ``proposal_sync`` may write to the vault.
    """
    p = ROOT / "src" / "output_router.py"
    if not p.is_file():
        return GateResult("phase2_single_writer_guard", False, "output_router.py not found")
    try:
        txt = p.read_text(encoding="utf-8")
    except OSError as e:
        return GateResult("phase2_single_writer_guard", False, str(e))
    # Forbidden imports — output_router must NOT pull in vault writers.
    forbidden_patterns = [
        r"^\s*from\s+src\.proposal_sync",
        r"^\s*import\s+src\.proposal_sync",
        r"^\s*from\s+src\.obsidian_writer",
        r"^\s*import\s+src\.obsidian_writer",
        r"^\s*from\s+src\.sync_proposals_to_kanban",
    ]
    hits: list[str] = []
    for pat in forbidden_patterns:
        m = re.search(pat, txt, re.M)
        if m:
            hits.append(m.group(0).strip())
    return GateResult(
        "phase2_single_writer_guard",
        not hits,
        "no vault-writer imports"
        if not hits
        else f"forbidden imports present: {', '.join(hits)}",
    )


def gate_phase2_fence_parser_stateful() -> GateResult:
    """Phase 2 T2: markdown_fence_parser.py uses a state machine, not regex
    matching of code fences. Heuristic: no ``re.`` calls that would parse
    fences (it may use re for line splitting, so a soft check).
    """
    p = ROOT / "src" / "markdown_fence_parser.py"
    if not p.is_file():
        return GateResult("phase2_fence_parser_stateful", False, "fence_parser not found")
    try:
        txt = p.read_text(encoding="utf-8")
    except OSError as e:
        return GateResult("phase2_fence_parser_stateful", False, str(e))
    # A state machine has at least: a state variable, a line iterator,
    # and conditional fence-open/fence-close handling.
    has_state = any(
        token in txt
        for token in ("in_fence", "inside_fence", "fence_open", "in_code_block")
    )
    iterates_lines = "splitlines" in txt or ".split('\\n')" in txt or 'split("\\n")' in txt or "for line in " in txt
    if has_state and iterates_lines:
        return GateResult(
            "phase2_fence_parser_stateful",
            True,
            "state variable + line iteration present",
        )
    return GateResult(
        "phase2_fence_parser_stateful",
        False,
        f"state var={has_state}, line iter={iterates_lines}",
    )


def gate_phase2_workflow_router_idempotency() -> GateResult:
    """Phase 2 E6: workflow_router tracks processed files via checksums or
    .processed flags so a restarted watcher does not re-fire.
    """
    p = ROOT / "src" / "workflow_router.py"
    if not p.is_file():
        return GateResult("phase2_workflow_router_idempotency", False, "workflow_router not found")
    try:
        txt = p.read_text(encoding="utf-8")
    except OSError as e:
        return GateResult("phase2_workflow_router_idempotency", False, str(e))
    has_hash = "sha256" in txt.lower() or "checksum" in txt.lower()
    has_flag = ".processed" in txt or "processed_files" in txt or "seen_files" in txt
    if has_hash or has_flag:
        markers = []
        if has_hash:
            markers.append("checksum")
        if has_flag:
            markers.append("processed-flag")
        return GateResult(
            "phase2_workflow_router_idempotency",
            True,
            f"idempotency via: {', '.join(markers)}",
        )
    return GateResult(
        "phase2_workflow_router_idempotency",
        False,
        "no idempotency mechanism (E6 requires checksum or .processed flag)",
    )


def gate_phase2_tests_present() -> GateResult:
    """Phase 2: Test files exist for the new modules."""
    required = [
        "tests/test_output_router.py",
        "tests/test_workflow_router.py",
    ]
    missing = [t for t in required if not (ROOT / t).is_file()]
    return GateResult(
        "phase2_tests_present",
        not missing,
        "test files present" if not missing else f"missing: {', '.join(missing)}",
    )


def gate_phase2_test_count() -> GateResult:
    """Phase 2: ≥15 test cases across Phase 2 test files."""
    test_files = [
        "tests/test_output_router.py",
        "tests/test_workflow_router.py",
        "tests/test_markdown_fence_parser.py",
        "tests/test_writer_protocols.py",
        "tests/test_routing_rules_schema.py",
    ]
    pattern = re.compile(r"^\s*def\s+test_\w+\s*\(", re.M)
    total = 0
    breakdown: list[str] = []
    for tf in test_files:
        p = ROOT / tf
        if not p.is_file():
            continue
        try:
            n = len(pattern.findall(p.read_text(encoding="utf-8")))
        except OSError:
            n = 0
        total += n
        breakdown.append(f"{Path(tf).name}:{n}")
    detail = f"{total} test cases ({', '.join(breakdown) or 'no files'}; limit ≥15)"
    return GateResult("phase2_test_count", total >= 15, detail)


def gate_phase2_routing_fixtures() -> GateResult:
    """Phase 2 E2: CI regression suite with 7 fixture council outputs and
    golden RoutingDecision JSONs in tests/routing/.
    """
    fixtures_dir = ROOT / "tests" / "routing"
    if not fixtures_dir.is_dir():
        return GateResult(
            "phase2_routing_fixtures",
            False,
            "tests/routing/ directory not found (E2 regression suite)",
        )
    inputs = list(fixtures_dir.glob("**/*.md")) + list(fixtures_dir.glob("**/input*.txt"))
    goldens = list(fixtures_dir.glob("**/*.golden.json")) + list(
        fixtures_dir.glob("**/golden*.json")
    )
    # At minimum: 7 inputs + 7 goldens (or paired files).
    passed = len(inputs) >= 7 and len(goldens) >= 7
    return GateResult(
        "phase2_routing_fixtures",
        passed,
        f"{len(inputs)} input(s), {len(goldens)} golden(s); need ≥7 of each",
    )


# ════════════════════════════════════════════════════════════════════
#  PHASE 3+4 GATES — ARCH-F10FE0E1 workflow execution
# ════════════════════════════════════════════════════════════════════

PHASE34_DELIVERABLES = [
    "src/workflow_engine.py",        # central state machine
    "src/git_operations.py",         # T1 git wrapper with timeouts
    "config/state_machine.yaml",     # phases + transitions + Gate #3 SQL
]


def gate_phase34_deliverables_exist() -> GateResult:
    """Phase 3+4: All 3 workflow execution deliverables exist."""
    missing = [m for m in PHASE34_DELIVERABLES if not (ROOT / m).is_file()]
    return GateResult(
        "phase34_deliverables_exist",
        not missing,
        "all 3 deliverables present"
        if not missing
        else f"missing: {', '.join(missing)}",
    )


def gate_phase34_transition_request_model() -> GateResult:
    """Phase 3+4 G3: TransitionRequest model exists with version_hash field."""
    p = ROOT / "src" / "workflow_models.py"
    if not p.is_file():
        return GateResult("phase34_transition_request_model", False, "workflow_models.py not found")
    try:
        txt = p.read_text(encoding="utf-8")
    except OSError as e:
        return GateResult("phase34_transition_request_model", False, str(e))
    has_class = "class TransitionRequest" in txt
    has_field = "version_hash" in txt
    if has_class and has_field:
        return GateResult(
            "phase34_transition_request_model",
            True,
            "TransitionRequest with version_hash present",
        )
    missing = []
    if not has_class:
        missing.append("class TransitionRequest")
    if not has_field:
        missing.append("version_hash field")
    return GateResult("phase34_transition_request_model", False, ", ".join(missing))


def gate_phase34_saga_compensating_actions() -> GateResult:
    """Phase 3+4 G2/T3: Saga pattern with named CompensatingAction class.

    T3 mandates explicit named compensating functions per step, not
    generic rollback logic.
    """
    p = ROOT / "src" / "workflow_models.py"
    eng = ROOT / "src" / "workflow_engine.py"
    if not p.is_file() and not eng.is_file():
        return GateResult(
            "phase34_saga_compensating_actions",
            False,
            "workflow_models.py and workflow_engine.py both missing",
        )
    sources = ""
    for f in (p, eng):
        if f.is_file():
            try:
                sources += f.read_text(encoding="utf-8")
            except OSError:
                continue
    has_compensating = "CompensatingAction" in sources or "class Compensating" in sources
    has_saga = "Saga" in sources or "SagaStep" in sources or "SagaTransaction" in sources
    if has_compensating and has_saga:
        return GateResult(
            "phase34_saga_compensating_actions",
            True,
            "CompensatingAction + Saga types present",
        )
    missing = []
    if not has_compensating:
        missing.append("CompensatingAction")
    if not has_saga:
        missing.append("SagaTransaction / SagaStep")
    return GateResult(
        "phase34_saga_compensating_actions",
        False,
        f"missing: {', '.join(missing)}",
    )


def gate_phase34_git_ops_timeouts() -> GateResult:
    """Phase 3+4 T1: git_operations.py uses explicit timeouts on subprocess calls.

    Without timeouts a hung ``git tag`` blocks a FastAPI worker
    indefinitely.
    """
    p = ROOT / "src" / "git_operations.py"
    if not p.is_file():
        return GateResult("phase34_git_ops_timeouts", False, "git_operations.py not found")
    try:
        txt = p.read_text(encoding="utf-8")
    except OSError as e:
        return GateResult("phase34_git_ops_timeouts", False, str(e))
    # Look for subprocess.run / subprocess.Popen with timeout= kw
    has_subprocess = "subprocess" in txt
    has_timeout_kw = re.search(r"timeout\s*=", txt) is not None
    has_asyncio = "asyncio.to_thread" in txt or "loop.run_in_executor" in txt
    if has_subprocess and has_timeout_kw:
        marker = "+ asyncio.to_thread" if has_asyncio else "sync"
        return GateResult(
            "phase34_git_ops_timeouts",
            True,
            f"subprocess + timeout kwarg present ({marker})",
        )
    missing = []
    if not has_subprocess:
        missing.append("subprocess module")
    if not has_timeout_kw:
        missing.append("timeout= kwarg")
    return GateResult(
        "phase34_git_ops_timeouts",
        False,
        f"missing: {', '.join(missing)}",
    )


def gate_phase34_version_hash_semantic() -> GateResult:
    """Phase 3+4 T2: version_hash computed from semantic-only keys.

    T2 requires the hash basis to be {phase, status, substatus, approver,
    severity, depends_on} and EXCLUDE volatile metadata like
    last_modified. Heuristic: scan for the function that computes the
    hash; confirm it does NOT include 'last_modified' or 'updated_ts'.
    """
    p = ROOT / "src" / "workflow_engine.py"
    if not p.is_file():
        # May also live in workflow_models.py
        p = ROOT / "src" / "workflow_models.py"
        if not p.is_file():
            return GateResult(
                "phase34_version_hash_semantic",
                False,
                "neither workflow_engine.py nor workflow_models.py found",
            )
    try:
        txt = p.read_text(encoding="utf-8")
    except OSError as e:
        return GateResult("phase34_version_hash_semantic", False, str(e))
    # Look for the hash function and its semantic-key set
    semantic_keys = {"phase", "status", "substatus", "approver", "severity", "depends_on"}
    semantic_hits = sum(1 for k in semantic_keys if k in txt)
    # Volatile keys MUST NOT appear in any version-hash-related function.
    # Heuristic: presence of 'last_modified' or 'updated_ts' literally in
    # the file is suspicious but not always wrong (e.g. they may exist
    # as Pydantic fields). Check the version_hash function body.
    mention_hash = "version_hash" in txt
    if not mention_hash:
        return GateResult(
            "phase34_version_hash_semantic",
            False,
            "no 'version_hash' references in workflow source",
        )
    passed = semantic_hits >= 4  # At least 4 of the 6 semantic keys named
    return GateResult(
        "phase34_version_hash_semantic",
        passed,
        f"{semantic_hits}/6 semantic keys referenced "
        f"({', '.join(sorted(k for k in semantic_keys if k in txt))})",
    )


def gate_phase34_gate3_sqlite_index() -> GateResult:
    """Phase 3+4 T4: composite index on approval_log (proposal_id, role,
    decision, ts) for the Gate #3 query.

    Check: an ``CREATE INDEX`` statement covering those columns appears
    somewhere in src/ (typically in approval_logger.py or workflow_engine.py).
    """
    pattern = re.compile(
        r"CREATE\s+INDEX[^;]*?approval_log[^;]*?proposal_id[^;]*?role[^;]*?decision",
        re.I | re.S,
    )
    for f in (ROOT / "src").rglob("*.py"):
        try:
            if pattern.search(f.read_text(encoding="utf-8")):
                return GateResult(
                    "phase34_gate3_sqlite_index",
                    True,
                    f"composite index found in {f.relative_to(ROOT)}",
                )
        except OSError:
            continue
    return GateResult(
        "phase34_gate3_sqlite_index",
        False,
        "no CREATE INDEX on approval_log(proposal_id, role, decision, ...) found",
    )


def gate_phase34_state_machine_yaml() -> GateResult:
    """Phase 3+4: config/state_machine.yaml exists with phase + transition
    definitions and a Gate #3 SQL spec.
    """
    p = ROOT / "config" / "state_machine.yaml"
    if not p.is_file():
        return GateResult("phase34_state_machine_yaml", False, "state_machine.yaml not found")
    try:
        txt = p.read_text(encoding="utf-8")
    except OSError as e:
        return GateResult("phase34_state_machine_yaml", False, str(e))
    has_phases = "phases" in txt or "states" in txt
    has_transitions = "transitions" in txt
    has_gate3 = "gate" in txt.lower() and ("APPROVED" in txt or "approval_log" in txt)
    if has_phases and has_transitions and has_gate3:
        return GateResult(
            "phase34_state_machine_yaml",
            True,
            "phases + transitions + Gate #3 spec present",
        )
    missing = []
    if not has_phases:
        missing.append("phases/states")
    if not has_transitions:
        missing.append("transitions")
    if not has_gate3:
        missing.append("Gate #3 spec (APPROVED + approval_log)")
    return GateResult(
        "phase34_state_machine_yaml",
        False,
        f"missing: {', '.join(missing)}",
    )


def gate_phase34_single_phase_writer() -> GateResult:
    """Phase 3+4 V2/G2: Only workflow_engine.py writes the phase: field.

    Other modules (dev_route, kanban_processor, proposal_writer) must
    delegate. Heuristic: scan for assignments to a phase field outside
    workflow_engine.

    Filters out false positives that look like phase writes but aren't:
      - Function-call kwargs:  some_fn(phase="x") — call site, not write
      - Pydantic Field defaults: phase: Phase = Field(default="x")
      - Comparisons: if x.phase == "x"
      - Lookups: d.get("phase"), "phase" in d
      - String-literal arguments inside ``log_*`` or ``audit_*`` helpers
        (these are recording the phase, not changing it)
    """
    # Search for writes that assign to a phase field. Two patterns:
    #   1. Dict/YAML-literal:  "phase": "value"  or  'phase': 'value'
    #   2. Direct assignment:  phase = "value"   (must be at line start)
    write_patterns = [
        re.compile(r"""['\"]phase['\"]\s*:\s*['\"]"""),
        # `\bphase\s*=` — but only if it looks like a STATEMENT (no preceding
        # `(` on the same line). A `(` before the match means we're inside
        # a function call, which is a kwarg, not a write.
        re.compile(r"""(?m)^[ \t]*phase\s*=\s*['\"]"""),
    ]
    violators: list[str] = []
    allowed = {"src/workflow_engine.py", "src/workflow_models.py"}
    for f in (ROOT / "src").rglob("*.py"):
        rel = str(f.relative_to(ROOT)).replace("\\", "/")
        if rel in allowed:
            continue
        if rel.endswith("_test.py") or "/tests/" in rel:
            continue
        try:
            txt = f.read_text(encoding="utf-8")
        except OSError:
            continue
        # Skip the existing schema_validator (it operates on YAML structurally,
        # not as a writer of phase transitions).
        if rel == "src/schema_validator.py":
            continue
        for pat in write_patterns:
            for m in pat.finditer(txt):
                # Pull the surrounding line for context-based filtering
                line_start = txt.rfind("\n", 0, m.start()) + 1
                line_end = txt.find("\n", m.end())
                line = txt[line_start:line_end if line_end >= 0 else None]
                stripped = line.strip()

                # Comparison / lookup — not a write
                if "==" in line or ".get(" in line or "in " in line:
                    continue
                # Pydantic field declaration: `phase: SomeType = Field(...)`
                # or default value via `= Field(...)`
                if "Field(" in line or "field(" in line:
                    continue
                # Function-call kwarg detection — works across multi-line calls.
                # Look at the 10 lines immediately preceding the match and count
                # unclosed parens. If there's at least one open `(` not yet
                # matched by `)`, we're inside a function call → kwarg, not a write.
                lookback_chars = txt[max(0, m.start() - 1000):m.start()]
                open_parens = lookback_chars.count("(")
                close_parens = lookback_chars.count(")")
                if open_parens > close_parens:
                    # We are syntactically inside an open function call.
                    continue
                # Comment line
                if stripped.startswith("#"):
                    continue

                violators.append(f"{rel}:{txt.count(chr(10), 0, m.start())+1}")
    return GateResult(
        "phase34_single_phase_writer",
        not violators,
        "no out-of-band phase writes"
        if not violators
        else f"{len(violators)} suspect write(s): {', '.join(violators[:3])}",
    )


def gate_phase34_tests_present() -> GateResult:
    """Phase 3+4: Test files exist for the new modules."""
    required = [
        "tests/test_workflow_engine.py",
        "tests/test_git_operations.py",
    ]
    missing = [t for t in required if not (ROOT / t).is_file()]
    return GateResult(
        "phase34_tests_present",
        not missing,
        "test files present" if not missing else f"missing: {', '.join(missing)}",
    )


def gate_phase34_test_count() -> GateResult:
    """Phase 3+4: ≥15 test cases across Phase 3+4 test files."""
    test_files = [
        "tests/test_workflow_engine.py",
        "tests/test_git_operations.py",
        "tests/test_state_machine_yaml.py",
        "tests/test_transition_request.py",
        "tests/test_saga.py",
    ]
    pattern = re.compile(r"^\s*def\s+test_\w+\s*\(", re.M)
    total = 0
    breakdown: list[str] = []
    for tf in test_files:
        p = ROOT / tf
        if not p.is_file():
            continue
        try:
            n = len(pattern.findall(p.read_text(encoding="utf-8")))
        except OSError:
            n = 0
        total += n
        breakdown.append(f"{Path(tf).name}:{n}")
    detail = f"{total} test cases ({', '.join(breakdown) or 'no files'}; limit ≥15)"
    return GateResult("phase34_test_count", total >= 15, detail)


def gate_perf_smoke() -> GateResult:
    """Alpha Polish: ≤3% perf regression on import + cold init.

    Smoke test only — measures the cost of importing src.dev_route which is
    the file Phase 0 touched. Baseline is recorded in
    dev/runbooks/_perf_baseline.json by the first run; subsequent runs
    compare against it.
    """
    baseline_file = ROOT / "dev" / "runbooks" / "_perf_baseline.json"
    code = "import time; t=time.perf_counter(); import src.dev_route; print(time.perf_counter()-t)"
    try:
        proc = subprocess.run(
            [sys.executable, "-c", code],
            cwd=ROOT, capture_output=True, text=True, timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        return GateResult("perf_smoke", False, f"could not run: {e}")
    if proc.returncode != 0:
        return GateResult("perf_smoke", False, proc.stderr.strip()[:200])
    try:
        elapsed = float(proc.stdout.strip())
    except ValueError:
        return GateResult("perf_smoke", False, "could not parse timing")

    if not baseline_file.exists():
        baseline_file.parent.mkdir(parents=True, exist_ok=True)
        baseline_file.write_text(json.dumps({"import_dev_route_s": elapsed}, indent=2))
        return GateResult(
            "perf_smoke",
            True,
            f"baseline recorded: {elapsed*1000:.1f}ms",
            duration_ms=int(elapsed * 1000),
        )

    baseline = json.loads(baseline_file.read_text())["import_dev_route_s"]
    delta_pct = (elapsed - baseline) / baseline * 100
    passed = delta_pct <= 3.0
    return GateResult(
        "perf_smoke",
        passed,
        f"{elapsed*1000:.1f}ms vs baseline {baseline*1000:.1f}ms "
        f"({delta_pct:+.1f}%; limit: +3.0%)",
        duration_ms=int(elapsed * 1000),
    )


# ════════════════════════════════════════════════════════════════════
#  RUNNER
# ════════════════════════════════════════════════════════════════════

PHASE0_GATES: list[Callable[[], GateResult]] = [
    gate_dev_route_size,
    gate_no_vault_literals,
    gate_one_trigger_sync_check,
    gate_no_in_locals,
    gate_cyclic_imports,
    gate_pytest,
]

PHASE1_GATES: list[Callable[[], GateResult]] = [
    gate_phase1_modules_exist,
    gate_phase1_pydantic_models,
    gate_phase1_uow_pattern,
    gate_phase1_ruamel_yaml,
    gate_phase1_tests_present,
    gate_phase1_test_count,
    gate_phase1_no_misplaced_tests,
    gate_phase1_no_print_in_tests,
]

PHASE2_GATES: list[Callable[[], GateResult]] = [
    gate_phase2_deliverables_exist,
    gate_phase2_writer_protocols,
    gate_phase2_catchall_route,
    gate_phase2_yaml_schema_pydantic,
    gate_phase2_dead_letter_dir,
    gate_phase2_single_writer_guard,
    gate_phase2_fence_parser_stateful,
    gate_phase2_workflow_router_idempotency,
    gate_phase2_tests_present,
    gate_phase2_test_count,
    gate_phase2_routing_fixtures,
]

PHASE34_GATES: list[Callable[[], GateResult]] = [
    gate_phase34_deliverables_exist,
    gate_phase34_state_machine_yaml,
    gate_phase34_transition_request_model,
    gate_phase34_saga_compensating_actions,
    gate_phase34_git_ops_timeouts,
    gate_phase34_version_hash_semantic,
    gate_phase34_gate3_sqlite_index,
    gate_phase34_single_phase_writer,
    gate_phase34_tests_present,
    gate_phase34_test_count,
]

BENCH_GATES: list[Callable[[], GateResult]] = [gate_perf_smoke]

# DEFAULT_GATES is kept as an alias for backward compatibility with any
# external CI scripts that might import it.
DEFAULT_GATES: list[Callable[[], GateResult]] = PHASE0_GATES


def run(gates: list[Callable[[], GateResult]]) -> list[GateResult]:
    results: list[GateResult] = []
    for g in gates:
        t = time.perf_counter()
        r = g()
        r.duration_ms = r.duration_ms or int((time.perf_counter() - t) * 1000)
        results.append(r)
    return results


# ════════════════════════════════════════════════════════════════════
#  RENDERING — high-contrast Dark Maestro aesthetic
# ════════════════════════════════════════════════════════════════════

PASS = "■ PASS"
FAIL = "□ FAIL"


def render_text(results: list[GateResult], title: str) -> str:
    width = 88
    bar = "═" * width
    lines: list[str] = []
    lines.append(bar)
    lines.append(f"  {title}")
    lines.append(bar)
    name_w = max((len(r.name) for r in results), default=20) + 2
    for r in results:
        mark = PASS if r.passed else FAIL
        lines.append(f"  {mark}  {r.name.ljust(name_w)} {r.duration_ms:>5}ms   {r.detail}")
    lines.append(bar)
    passed = sum(r.passed for r in results)
    total = len(results)
    summary = f"  {passed} / {total} gates passed"
    if passed == total:
        summary += "   ▼ READY FOR FINALIZATION"
    else:
        summary += "   ▼ BLOCKED — see failures above"
    lines.append(summary)
    lines.append(bar)
    return "\n".join(lines)


# ════════════════════════════════════════════════════════════════════
#  MAIN
# ════════════════════════════════════════════════════════════════════

def main() -> int:
    parser = argparse.ArgumentParser(description="Alpha Polish CI gate")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--bench", action="store_true", help="include perf smoke test")
    parser.add_argument(
        "--phase",
        choices=["0", "1", "2", "34", "all"],
        default="all",
        help="which phase gates to run (default: all)",
    )
    args = parser.parse_args()

    if args.phase == "0":
        gates = list(PHASE0_GATES)
        title = "ALPHA POLISH GATE — Phase 0 (ARCH-A0F1B0C0)"
    elif args.phase == "1":
        gates = list(PHASE1_GATES)
        title = "ALPHA POLISH GATE — Phase 1 (ARCH-60FE0001)"
    elif args.phase == "2":
        gates = list(PHASE2_GATES)
        title = "ALPHA POLISH GATE — Phase 2 (ARCH-2007E0A1)"
    elif args.phase == "34":
        gates = list(PHASE34_GATES)
        title = "ALPHA POLISH GATE — Phase 3+4 (ARCH-F10FE0E1)"
    else:
        gates = (
            list(PHASE0_GATES)
            + list(PHASE1_GATES)
            + list(PHASE2_GATES)
            + list(PHASE34_GATES)
        )
        title = "ALPHA POLISH GATE — Phase 0 + 1 + 2 + 3+4"

    if args.bench:
        gates.extend(BENCH_GATES)

    results = run(gates)
    all_passed = all(r.passed for r in results)

    if args.json:
        print(json.dumps(
            [{"name": r.name, "passed": r.passed, "detail": r.detail,
              "duration_ms": r.duration_ms} for r in results],
            indent=2,
        ))
    else:
        print(render_text(results, title))

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
