"""
Hermes quantization benchmark — load any hermes variant via /api/load,
generate a fixed prompt, report tok/s and grep the LM Studio runtime log
for the headline indicators (n_parallel, pipeline parallelism, KV alloc).

Usage:

    python scripts/bench_hermes.py <model_key>
    python scripts/bench_hermes.py <model_key> --context 131072 --kv f16

Assumes the FastAPI server (`python -m src.api`) is already listening on
:5000. The script does NOT start it for you.

Designed for A/B testing different quants of the same model. Run once
per quant; results are appended to scratch/bench_hermes_results.jsonl
(JSONL stays under scratch/ because /api/benchmarks reads it from there
and the file is run-evidence, not source code). Harness promoted from
scratch/ to scripts/ on 2026-05-26 (A6 of DEV-…-B5D5C0DE).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

API = "http://127.0.0.1:5000"
LMS_OPENAI = "http://127.0.0.1:1234/v1"
# Results JSONL lives under cognitive-os/scratch/ (one level up from scripts/).
# /api/benchmarks reads from the same path; don't move it.
RESULTS = Path(__file__).resolve().parent.parent / "scratch" / "bench_hermes_results.jsonl"

PROMPT = (
    "Write a 200-word description of a baroque-mechanical clock tower "
    "at twilight, focusing on the gears, brass mechanisms, and the way "
    "the dying light catches the polished surfaces."
)


def http_json(method: str, path: str, body=None, timeout: float = 600):
    req = urllib.request.Request(
        f"{API}{path}",
        method=method,
        data=json.dumps(body).encode("utf-8") if body is not None else None,
        headers={"Content-Type": "application/json"} if body else {},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            payload = json.loads(e.read())
        except Exception:
            payload = e.read().decode("utf-8", "replace")
        return e.code, payload


def find_latest_lmstudio_log() -> Path | None:
    root = Path.home() / ".lmstudio" / "server-logs"
    if not root.exists():
        return None
    logs = sorted(root.rglob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
    return logs[0] if logs else None


def grep_runtime_log(log_path: Path, since_byte: int) -> dict:
    """Read the log delta and return parsed headline indicators."""
    if not log_path or not log_path.exists():
        return {"_error": f"log not found: {log_path}"}
    with log_path.open("rb") as f:
        f.seek(since_byte)
        delta = f.read().decode("utf-8", "replace")

    result = {
        "raw_delta_bytes": len(delta),
        "n_parallel": None,
        "n_seq_max": None,
        "k_cache_type": None,
        "v_cache_type": None,
        "kv_total_mib": None,
        "pipeline_parallelism": None,
        "fell_back_no_pp": False,
        "cudaMalloc_failed_mib": None,
        "server_eval_tps": None,
        "server_prompt_eval_tps": None,
    }
    if m := re.search(r"LlamaV4::load config:\s*n_parallel=(\d+)\s*n_ctx=(\d+)", delta):
        result["n_parallel"] = int(m.group(1))
        result["n_ctx"] = int(m.group(2))
    if m := re.search(r"n_seq_max\s*=\s*(\d+)", delta):
        result["n_seq_max"] = int(m.group(1))
    if m := re.search(
        r"K \((\w+)\):\s*([\d.]+)\s*MiB,\s*V \((\w+)\):\s*([\d.]+)\s*MiB", delta
    ):
        result["k_cache_type"] = m.group(1)
        result["v_cache_type"] = m.group(3)
    if m := re.search(r"llama_kv_cache:\s*size\s*=\s*([\d.]+)\s*MiB", delta):
        result["kv_total_mib"] = float(m.group(1))
    if "pipeline parallelism enabled" in delta:
        result["pipeline_parallelism"] = True
    if "retrying without pipeline parallelism" in delta:
        result["fell_back_no_pp"] = True
        result["pipeline_parallelism"] = False
    if m := re.search(r"cudaMalloc failed: out of memory.*?(\d+)\s*MiB", delta, re.DOTALL):
        result["cudaMalloc_failed_mib"] = int(m.group(1))
    if m := re.search(r"prompt eval time\s*=\s*[\d.]+\s*ms.*?([\d.]+)\s*tokens per second", delta):
        result["server_prompt_eval_tps"] = float(m.group(1))
    # Capture the LAST "eval time" tps (the generation rate, not prompt eval)
    matches = re.findall(
        r"eval time\s*=\s*[\d.]+\s*ms\s*/\s*\d+\s*tokens\s*\(\s*[\d.]+\s*ms per token,\s*([\d.]+)\s*tokens per second\)",
        delta,
    )
    if matches:
        result["server_eval_tps"] = float(matches[-1])
    return result


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("model_key", help="LM Studio model_key (e.g. hermes-4.3-36b)")
    p.add_argument("--context", type=int, default=131072, dest="context_length")
    p.add_argument("--n-parallel", type=int, default=1)
    p.add_argument("--kv", choices=("f16", "q8_0", "q4_0"), default="f16",
                   help="K/V cache quantization. Both K and V get the same type.")
    p.add_argument("--max-tokens", type=int, default=400)
    p.add_argument("--identifier", default="_bench")
    args = p.parse_args()

    # --- 1. Snapshot log size before we touch anything --------------------
    log_path = find_latest_lmstudio_log()
    log_size_before = log_path.stat().st_size if log_path else 0
    print(f"[bench] LM Studio log: {log_path} (size={log_size_before})")

    # --- 2. POST /api/load ------------------------------------------------
    cfg: dict = {
        "context_length": args.context_length,
        "flashAttention": True,
        "maxParallelPredictions": args.n_parallel,
    }
    if args.kv != "f16":
        cfg["cache_type_k"] = args.kv
        cfg["cache_type_v"] = args.kv
    body = {
        "model_key": args.model_key,
        "identifier": args.identifier,
        "config": cfg,
        "ttl": None,
        "force_reload": True,
    }
    print(f"[bench] POST /api/load — model={args.model_key!r}, "
          f"ctx={args.context_length}, n_par={args.n_parallel}, kv={args.kv}")
    t0 = time.monotonic()
    code, resp = http_json("POST", "/api/load", body, timeout=600)
    load_wall = time.monotonic() - t0
    if code != 200:
        print(f"[bench] LOAD FAILED HTTP {code}")
        print(json.dumps(resp, indent=2, default=str))
        return 2
    print(f"[bench] load wall-clock: {load_wall:.2f}s (server-reported: "
          f"{resp.get('duration_seconds')}s)")

    # --- 3. Generation ----------------------------------------------------
    try:
        from openai import OpenAI
    except ImportError:
        print("[bench] openai package missing — skipping generation")
        return 1

    client = OpenAI(base_url=LMS_OPENAI, api_key="lm-studio")
    print(f"[bench] generating ({args.max_tokens} max tokens)...")
    t0 = time.monotonic()
    completion = client.chat.completions.create(
        model=args.identifier,
        messages=[{"role": "user", "content": PROMPT}],
        temperature=0.7,
        max_tokens=args.max_tokens,
    )
    gen_wall = time.monotonic() - t0
    text = completion.choices[0].message.content or ""
    pt = completion.usage.prompt_tokens
    ct = completion.usage.completion_tokens
    client_tps = ct / gen_wall if gen_wall > 0 else 0.0

    print(f"[bench] gen wall-clock: {gen_wall:.2f}s")
    print(f"[bench] prompt_tokens={pt} completion_tokens={ct}")
    print(f"[bench] client-side tok/s: {client_tps:.2f}")

    # --- 4. Read log delta and parse --------------------------------------
    log_indicators = grep_runtime_log(log_path, log_size_before) if log_path else {}

    # --- 5. Cleanup -------------------------------------------------------
    http_json("DELETE", f"/api/load/{args.identifier}")

    # --- 6. Persist + print report ---------------------------------------
    record = {
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        "model_key": args.model_key,
        "config": cfg,
        "load_wall_s": round(load_wall, 2),
        "load_reported_s": resp.get("duration_seconds"),
        "gen_wall_s": round(gen_wall, 2),
        "prompt_tokens": pt,
        "completion_tokens": ct,
        "client_tps": round(client_tps, 2),
        "log": log_indicators,
        "first_200_chars": text[:200],
    }
    with RESULTS.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    print()
    print("=== BENCHMARK REPORT ===")
    for k, v in record.items():
        if k in ("first_200_chars",):
            continue
        if k == "log":
            print(f"  {k}:")
            for lk, lv in (v or {}).items():
                print(f"    {lk}: {lv}")
        else:
            print(f"  {k}: {v}")
    print(f"\n  first_200_chars: {text[:200]}")
    print(f"\n[bench] appended to {RESULTS}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
