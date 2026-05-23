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
        choices=["0", "1", "all"],
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
    else:
        gates = list(PHASE0_GATES) + list(PHASE1_GATES)
        title = "ALPHA POLISH GATE — Phase 0 + Phase 1"

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
