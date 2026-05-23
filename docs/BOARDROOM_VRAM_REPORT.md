# Cognitive OS Boardroom: Hardware & VRAM Orchestration Strategy
**Date:** May 23, 2026
**Target Architecture:** Multi-Agent Pipeline (QG2 Qwen/Llama Framework)
**Hardware Baseline:** Intel i6900k, 128GB RAM (3000MHz), 2x RTX 3090 (48 GiB Total VRAM)

## 1. Executive Summary
The Cognitive OS Boardroom requires running multiple models concurrently: a 70B "Chairman/Strategist" for deep reasoning, and smaller agile agents (16B-36B) for moderation and routing. 

At a default F16 precision and maximum context lengths, a 70B model's context cache alone exceeds **20 GiB**, completely starving the 48 GiB VRAM limit when combined with the ~40 GiB model weights. This results in silent pipeline parallelism failures and token generation crashing to < 5 tok/s.

By strategically mapping Context Cache and lightweight agents to the 128GB System RAM, and enforcing K/V quantization protocols, we can fully saturate the hardware and hit QG2 standards (>25 tok/s for active agents) without encountering CUDA Out-of-Memory (OOM) failures.

## 2. The Model Matrix (Benchmarked)
*Metrics extracted from direct .gguf binary headers and live QG2 benchmarking runs on the target hardware.*

| Model Role | Model Key | Layers | Weight VRAM | Max Gen (tok/s) | 65K KV: F16 | 65K KV: Q8_0 |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| **Chairman (Heavy)** | unsloth/hermes-4-70b | 80 | ~41.0 GiB | OOM / Choke | 20.0 GiB | 10.0 GiB |
| **Chairman (Heavy)** | deepseek-r1-distill-llama-70b | 80 | ~35.3 GiB | 3.68 (Choke) | 20.0 GiB | 10.0 GiB |
| **Strategist (Mid)** | hermes-4.3-36b-heretic | 64 | ~22.0 GiB | **30.42** | 8.0 GiB | 4.0 GiB |
| **Strategist (Mid)** | qwen3.5-35b-a3b-moe | 40 | ~18.0 GiB | **61.24** | 2.5 GiB | 1.2 GiB |
| **Moderator/Guard** | deepseek-coder-v2-lite (16B)| 27 | ~11.0 GiB | **59.22** | 13.5 GiB | 6.8 GiB |
| **Instant Router** | ministral-3-3b-instruct | 26 | ~3.0 GiB | 9.99 (559 P/s) | 4.9 GiB | 2.4 GiB |

## 3. The Bottleneck: Context Window (KV Cache)
The largest threat to pipeline stability is not the model parameters, but the **KV Cache** (the memory holding the context window of the document being read). 

With 
_parallel=2, two Chairman agents reading a 65,536-token proposal will consume exactly **20 GiB of VRAM** just for memory retention, instantly crashing the 48 GiB limit.

### Solutions Available:
1. **KV Cache Quantization (cache_type_k = q8_0)**
   Slices the context memory footprint in half (20 GiB -> 10 GiB) with virtually zero degradation in logic or reasoning quality.
2. **CPU System RAM Offload (offload_kv_cache_to_gpu = False)**
   Evicts the entire 20 GiB KV Cache from the RTX 3090s and forces it into the 128GB of 3000MHz RAM. This trades raw prompt ingestion speed (slower) for immense stability (zero VRAM crashes).

## 4. Recommended Architectures for Boardroom Execution

### Strategy A: The "Zero Choke" 70B Layout (Recommended for Massive Documents)
**Objective:** Run the 70B Chairman with maximum context size safely.
* **GPUs 0 & 1:** Tensor Parallel execution of deepseek-r1-llama-70b (35 GiB).
* **System RAM:** The 20 GiB KV Cache is forcefully offloaded to the 128GB CPU RAM.
* **System RAM:** The deepseek-coder-v2-lite Moderator agent is loaded with gpu_offload_ratio: 0. It runs entirely on the i6900k + RAM via mmap.
* **Result:** The GPUs have ~11 GiB of VRAM to spare. Pipeline parallelism stays active.

**LM Studio Payload:**
`json
{
  "model_key": "deepseek-r1-distill-llama-70b",
  "config": {
    "context_length": 65536,
    "flashAttention": true,
    "offload_kv_cache_to_gpu": false,
    "gpu": "max",
    "maxParallelPredictions": 2
  }
}
`

### Strategy B: The High-Speed 36B Layout (Recommended for Real-Time Flow)
**Objective:** Maximum token throughput across all agents for rapid boardroom iteration.
* **GPUs 0 & 1:** Tensor Parallel execution of hermes-4.3-36b-heretic (22 GiB).
* **VRAM:** Because the Hermes 36B model uses grouped-query attention, its F16 KV cache is only 8.0 GiB.
* **Result:** The Model + Context fits perfectly into ~30 GiB of VRAM. It generates at a blazing **30.42 tok/s**, acting fast enough to handle both the Chairman and Strategist roles flawlessly.

### Strategy C: The Multi-Tiered Split
**Objective:** Running 70B and 36B simultaneously.
* **GPU 0:** 70B model loaded with gpu_offload_ratio: 0.5. It splits 40 layers to GPU 0 and 40 to CPU. 
* **GPU 1:** 36B model loaded with gpu: max. 
* **Result:** Generation speed drops drastically (5-10 tok/s) due to the PCIe bus bottleneck on the 70B model, but it allows discrete isolation of agent brains. *(Note: Not recommended unless deep logical diversity is required).*

## 5. Next Steps for Implementation
1. Inject the offload_kv_cache_to_gpu parameter into the LMStudioLoader Python class (src/lmstudio_loader.py).
2. Update master_config.md to map the deepseek-coder-v2-lite to the oard_moderator role with forced CPU execution.
3. Test a 50,000 token multi-agent boardroom sync against the new parameters.
