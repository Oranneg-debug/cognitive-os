---
type: SOP
domain: model_benchmarking
applies_to:
  - cognitive-os/src/lmstudio_loader.py
  - cognitive-os/scratch/bench_hermes.py
  - cognitive-os/scratch/bench_hermes_results.jsonl
last_verified: 2026-05-21
last_verified_against:
  - hermes-4.3-36b-heretic-i1 (IQ4_XS): 29.11 tok/s @ 65K
  - hermes-4.3-36b-heretic-i1 (IQ4_XS @98K): 27.40 tok/s
  - hermes-4.3-36b (Q6_K): 17.26 tok/s @ 65K  (pre-migration baseline)
hardware:
  gpu: 2× RTX 3090 (24 GiB each, 48 GiB total)
  cuda_runtime: enabled
---

# SOP — Benchmark a Model on the Cognitive OS

This Standard Operating Procedure documents how to benchmark **any LLM** in
the LM Studio catalog against the Cognitive OS pipeline. It produces:

1. A clean tokens/sec number (client-side AND server-side eval rate).
2. LM Studio runtime indicators (n_parallel, n_seq_max, pipeline
   parallelism, KV cache shape, CUDA buffer status).
3. A JSONL row appended to `cognitive-os/scratch/bench_hermes_results.jsonl`
   so the dashboard's **LM Studio → Benchmarks** sub-tab shows the run.

Use this SOP every time:

- A new model is downloaded to the LM Studio catalog.
- An existing model is re-quantized or replaced.
- `master_config.md` parameters change for any role.
- LM Studio is upgraded (its KV / FA / pipeline-parallel behaviour can
  shift between versions).

The bench-runner agent (`bench-runner.agent.md`) is the canonical
executor of this SOP. A human can also run the same steps manually.

---

## Preflight (run once per session)

1. **API up?**

   ```powershell
   netstat -ano | findstr ':5000.*LISTENING'
   ```

   If nothing listening:

   ```powershell
   $env:PYTHONIOENCODING = 'utf-8'
   Start-Process -FilePath python -ArgumentList '-u','-m','src.api' `
     -WorkingDirectory 'e:\Antigravity\cognitive-os' `
     -RedirectStandardOutput 'e:\Antigravity\cognitive-os\logs\api.stdout.log' `
     -RedirectStandardError  'e:\Antigravity\cognitive-os\logs\api.stderr.log' `
     -PassThru -WindowStyle Hidden
   Start-Sleep -Seconds 10
   ```

2. **Catalog fresh?** LM Studio newly-downloaded models won't appear in
   the API's cached catalog until refreshed:

   ```powershell
   Invoke-RestMethod -Uri http://localhost:5000/api/catalog/refresh -Method POST
   ```

3. **Snapshot the LM Studio runtime log size.** We'll read only the delta:

   ```powershell
   $logFile = (Get-ChildItem 'C:\Users\Gebruiker\.lmstudio\server-logs\' -Recurse -Filter '*.log' |
                Sort-Object LastWriteTime -Descending | Select-Object -First 1).FullName
   $script:logBefore = (Get-Item $logFile).Length
   ```

4. **Confirm the model_key**:

   ```powershell
   $catalog = Invoke-RestMethod -Uri http://localhost:5000/api/loaded
   $catalog.downloaded | Sort-Object | ForEach-Object { Write-Host "  $_" }
   ```

   Pick the exact key. **Important quirk**: LM Studio derives the
   model_key from the *parent folder name*, not the .gguf filename.
   If a folder contains multiple quants, the SDK reports the same key
   regardless of which file is active. Verify which physical .gguf
   file is loaded with `lms ps` (it prints the .gguf filename in the
   identifier-row's hidden detail) and re-loading is the only safe way
   to switch quants.

---

## The Bench Itself

The harness lives at `cognitive-os/scratch/bench_hermes.py` (despite the
name, it works for any model — "hermes" is just a historical artifact).

### One-line invocation

```powershell
cd e:/Antigravity
python cognitive-os/scratch/bench_hermes.py <model_key> --context <N> --n-parallel 1 --kv f16
```

### What it does

1. POSTs to `/api/load` with the given config (`context_length`,
   `n_parallel`, `flashAttention=true`, `cache_type_k`, `cache_type_v`).
2. Runs an OpenAI-client `chat.completions` call with a fixed prompt
   (200-word baroque-mechanical clock tower; chosen because it stresses
   the creative seat's typical workload without triggering tool calls).
3. Times the wall-clock and computes client-side tok/s.
4. Reads the LM Studio runtime log delta and parses headline indicators.
5. Appends one JSONL row to
   `cognitive-os/scratch/bench_hermes_results.jsonl`.

### Known issue: `--n-parallel 1` routes to the CLI back-channel

If you pass `--n-parallel 1`, the `LMStudioLoader` dispatches via
`lms load` (because the SDK 1.5.0 `LlmLoadModelConfig` has no slot for
`maxParallelPredictions`). The CLI back-channel **silently drops**
`flash_attention` and `cache_type_*` from the load command. To force
those to apply, write them into the per-model GUI prefs first:

```powershell
$cfgFile = "C:\Users\Gebruiker\.lmstudio\.internal\user-concrete-model-default-config\<publisher>\<repo>\<file>.gguf.json"
$cfgDir = Split-Path $cfgFile -Parent
New-Item -ItemType Directory -Path $cfgDir -Force | Out-Null
@{
  fields = @(
    @{ key = 'llm.load.contextLength'; value = 65536 },
    @{ key = 'llm.load.llama.flashAttention'; value = $true },
    @{ key = 'llm.load.llama.acceleration.offloadRatio'; value = 'max' }
  )
} | ConvertTo-Json -Depth 5 -Compress | Set-Content -Path $cfgFile -Encoding UTF8
```

Then load via `lms load --parallel 1 --context-length 65536 --gpu max --yes <model_key>`
and the GUI prefs file injects FA + offload settings.

This workaround is tracked as Task 10 of `DEV-20260521-001000-B5D5C0DE`
("Timeout/heartbeat + state machine"). Once that lands the SOP can stop
mentioning this paragraph.

---

## Pass / Fail Criteria

A model "passes" QG2 if all three are true:

| Criterion | Threshold |
|---|---|
| Client tok/s | **≥ 25** (sustained over a 200-token generation) |
| Pipeline parallelism | **`enabled` in log** (no "retrying without pipeline parallelism" line) |
| No CUDA OOM | **no `cudaMalloc failed` line** in the log delta |

If client tok/s < 25 OR pipeline parallelism falls back:

1. **Drop context length** by 25% (e.g. 131072 → 98304 → 65536 → 49152).
2. **If still fails**: switch K and V cache to `q8_0` (saves ~2× KV VRAM).
3. **If still fails**: the model is too big for the hardware at any
   reasonable context. Document the failure in the JSONL row and
   either upgrade hardware, downgrade quant, or remove the model from
   `master_config.md`'s role bindings.

---

## After the Bench

1. **Inspect the JSONL row** — `scratch/bench_hermes_results.jsonl`,
   last line. Confirm:
   - `client_tps` is set
   - `log.pipeline_parallelism` is `true`
   - `log.cudaMalloc_failed_mib` is `null`
2. **Refresh the dashboard** — open the LM Studio tab, click the
   "Benchmarks" sub-tab, click `↻ reload history`. The new row should
   appear at the top.
3. **If the bench passed AND the model is intended for a role**, update
   `cognitive-os/dev/master_config.md`:
   - Add an entry to the `models:` block with the verified config.
   - Point the relevant `roles:` entry at the new model_key.
4. **If the bench is part of a re-baseline** (e.g. after LM Studio
   upgrade), keep the old JSONL rows — the dashboard shows them
   chronologically so the regression is visible.

---

## A/B Comparisons

To compare two quants of the same model:

```powershell
# Bench A
python cognitive-os/scratch/bench_hermes.py <model_key> --context 65536 --n-parallel 1 --kv f16

# Swap the .gguf file by ejecting + reloading with a different per-model config:
# (manually edit cfgFile to point at the alternate quant — LM Studio picks the
# .gguf file from the prefs)

# Bench B
python cognitive-os/scratch/bench_hermes.py <model_key> --context 65536 --n-parallel 1 --kv f16
```

Both rows land in the JSONL with the same `model_key` but different
timestamps. The dashboard renders them adjacent in the Benchmarks table.

---

## Reference Numbers (verified 2026-05-21)

For "did I regress?" sanity checks:

| Model | Quant | Ctx | n_par | KV | Client tps | Server eval | Notes |
|---|---|---|---|---|---|---|---|
| hermes-4.3-36b | Q6_K | 131072 | 1 | q8_0 | 17.26 | — | PP fell back (OOM) |
| hermes-4.3-36b-heretic-i1 | Q4_K_M | 65536 | 1 | f16 | 25.03 | 28.49 | first heretic bench |
| hermes-4.3-36b-heretic-i1 | IQ4_XS | 65536 | 1 | f16 | **29.11** | **33.72** | current Creative default |
| hermes-4.3-36b-heretic-i1 | IQ4_XS | 98304 | 1 | f16 | 27.40 | 31.56 | stretch goal, fits |

Any future bench of these models that comes in >15% below these numbers
indicates a regression — investigate before re-baselining.

---

*SOP authored by the Cognitive OS development team during
DEV-20260521-001000-B5D5C0DE (LM Studio SDK Migration).
Update this file whenever the bench harness or pass/fail thresholds
change.*
