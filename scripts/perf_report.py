"""
High-Contrast Performance Report — ARCH-A0F1B0C0 Alpha Polish

Per chairman verdict 2026-05-23: technical metrics presented with stark,
unadorned precision. No graphs, no colour, no theatrics. Numbers only,
framed for legibility.

Stdlib only (per CSTR-PREMATURE-SYNC).

Usage:
    python scripts/perf_report.py
    python scripts/perf_report.py --runs 10
    python scripts/perf_report.py --json
"""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


# ════════════════════════════════════════════════════════════════════
#  MEASUREMENT
# ════════════════════════════════════════════════════════════════════

@dataclass
class Sample:
    name: str
    samples_s: list[float]

    @property
    def n(self) -> int:
        return len(self.samples_s)

    @property
    def min_ms(self) -> float:
        return min(self.samples_s) * 1000

    @property
    def median_ms(self) -> float:
        return statistics.median(self.samples_s) * 1000

    @property
    def p95_ms(self) -> float:
        if self.n < 2:
            return self.samples_s[0] * 1000
        sorted_s = sorted(self.samples_s)
        idx = max(0, int(round(0.95 * (self.n - 1))))
        return sorted_s[idx] * 1000

    @property
    def max_ms(self) -> float:
        return max(self.samples_s) * 1000

    @property
    def stdev_ms(self) -> float:
        if self.n < 2:
            return 0.0
        return statistics.stdev(self.samples_s) * 1000


def measure_import(module: str, runs: int) -> Sample:
    """Run `python -c 'import <module>'` in a subprocess `runs` times.

    Subprocess isolation gives cold-import numbers each run; importing
    in-process would cache the module after the first iteration.
    """
    times: list[float] = []
    code = f"import time;t=time.perf_counter();import {module};print(time.perf_counter()-t)"
    for _ in range(runs):
        proc = subprocess.run(
            [sys.executable, "-c", code],
            cwd=ROOT, capture_output=True, text=True, timeout=30,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"import {module} failed: {proc.stderr.strip()[:200]}")
        try:
            times.append(float(proc.stdout.strip()))
        except ValueError as exc:
            raise RuntimeError(f"parse error for {module}: {proc.stdout!r}") from exc
    return Sample(name=module, samples_s=times)


def measure_callable(name: str, fn, runs: int) -> Sample:
    """Measure an in-process callable `runs` times."""
    times: list[float] = []
    for _ in range(runs):
        t = time.perf_counter()
        fn()
        times.append(time.perf_counter() - t)
    return Sample(name=name, samples_s=times)


# ════════════════════════════════════════════════════════════════════
#  RENDERING — Dark Maestro
# ════════════════════════════════════════════════════════════════════

def render_text(samples: list[Sample], baseline: dict | None) -> str:
    width = 88
    bar = "═" * width
    lines: list[str] = []
    lines.append(bar)
    lines.append("  HIGH-CONTRAST PERFORMANCE REPORT — Phase 0 (ARCH-A0F1B0C0)")
    lines.append(bar)
    lines.append(
        f"  {'metric'.ljust(36)} "
        f"{'n':>4} "
        f"{'min':>8} "
        f"{'p50':>8} "
        f"{'p95':>8} "
        f"{'max':>8} "
        f"{'σ':>7} "
        f"{'Δvs base':>9}"
    )
    lines.append("  " + "─" * (width - 2))
    for s in samples:
        if baseline and s.name in baseline:
            base = baseline[s.name]
            delta = (s.median_ms - base) / base * 100 if base > 0 else 0.0
            delta_str = f"{delta:+.1f}%"
        else:
            delta_str = "  —"
        lines.append(
            f"  {s.name.ljust(36)} "
            f"{s.n:>4} "
            f"{s.min_ms:>7.1f}m "
            f"{s.median_ms:>7.1f}m "
            f"{s.p95_ms:>7.1f}m "
            f"{s.max_ms:>7.1f}m "
            f"{s.stdev_ms:>6.1f}m "
            f"{delta_str:>9}"
        )
    lines.append(bar)
    lines.append("  Units: milliseconds. Subprocess cold-import. No warm-up.")
    if baseline:
        lines.append("  Baseline: dev/runbooks/_perf_baseline.json")
        lines.append("  Veto threshold: median Δ > +3.0% (Alpha Polish gate)")
    else:
        lines.append("  No baseline recorded — this run will become the baseline.")
    lines.append(bar)
    return "\n".join(lines)


# ════════════════════════════════════════════════════════════════════
#  MAIN
# ════════════════════════════════════════════════════════════════════

TARGETS = [
    "src.paths",
    "src.sync_check",
    "src.proposal_writer",
    "src.handoff_writer",
    "src.dev_route",
    "src.kanban_processor",
]


def main() -> int:
    parser = argparse.ArgumentParser(description="High-Contrast Performance Report")
    parser.add_argument("--runs", type=int, default=5, help="samples per metric (default: 5)")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--update-baseline", action="store_true",
                        help="write current medians as the new baseline")
    args = parser.parse_args()

    baseline_file = ROOT / "dev" / "runbooks" / "_perf_baseline.json"
    baseline: dict | None = None
    if baseline_file.exists():
        try:
            baseline = json.loads(baseline_file.read_text())
        except json.JSONDecodeError:
            baseline = None

    samples: list[Sample] = []
    for module in TARGETS:
        try:
            samples.append(measure_import(module, args.runs))
        except RuntimeError as e:
            print(f"  □ ERROR  {module}: {e}", file=sys.stderr)

    if args.json:
        out = {
            "runs": args.runs,
            "samples": [
                {
                    "name": s.name,
                    "n": s.n,
                    "min_ms": round(s.min_ms, 3),
                    "median_ms": round(s.median_ms, 3),
                    "p95_ms": round(s.p95_ms, 3),
                    "max_ms": round(s.max_ms, 3),
                    "stdev_ms": round(s.stdev_ms, 3),
                }
                for s in samples
            ],
            "baseline": baseline,
        }
        print(json.dumps(out, indent=2))
    else:
        print(render_text(samples, baseline))

    if args.update_baseline:
        baseline_file.parent.mkdir(parents=True, exist_ok=True)
        new_baseline = {s.name: round(s.median_ms, 3) for s in samples}
        baseline_file.write_text(json.dumps(new_baseline, indent=2))
        print(f"\n  ■ baseline written → {baseline_file.relative_to(ROOT)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
