import asyncio
import json
import sqlite3
import sys
import uvicorn
import os
import re
import yaml
import psutil
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional, Union, Dict, Any
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Governance Foundation imports (A1, ARCH-2007E0A1)
from src.output_router import OutputRouter
from src.filesystem_backend_writer import FilesystemBackendWriter
from src.routing_rules_schema import load_routing_rules
from src.orchestrator import Orchestrator
from src.obsidian_writer import ObsidianWriter
from src.paths import VAULT_ROOT, DEV_DIR, PROPOSALS_DIR, VAULT_PROPOSALS_DIR
from src.uow_recovery import run_recovery
from src.approval_logger import ApprovalLogger

# Dashboard kanban migration (ARCH-DA5B0A2D, A3)
from src.kanban_store import (
    CANONICAL_COLUMNS,
    KNOWN_PREFIXES,
    CardNotFound,
    InvalidColumn,
    InvalidPrefix,
    KanbanStore,
    KanbanStoreError,
)
from fastapi.middleware.cors import CORSMiddleware


def _validate_failed_routings_dir() -> None:
    """B1: Ensure dev/failed_routings/ exists, create if missing."""
    failed_routings = DEV_DIR / "failed_routings"
    if not failed_routings.exists():
        failed_routings.mkdir(parents=True, exist_ok=True)
        print(f"[STARTUP] Created dev/failed_routings/ directory")


def _validate_routing_rules() -> None:
    """B2: Validate config/routing_rules.yaml loads cleanly."""
    rules_path = Path(__file__).resolve().parent.parent / "config" / "routing_rules.yaml"
    try:
        load_routing_rules(rules_path)
        print("[STARTUP] routing_rules.yaml validated")
    except Exception as e:
        raise RuntimeError(
            f"Failed to load routing_rules.yaml. FastAPI refusing to start. "
            f"Error: {e}"
        ) from e


def _validate_state_machine() -> None:
    """B3: Validate config/state_machine.yaml loads cleanly via yaml."""
    state_machine_path = Path(__file__).resolve().parent.parent / "config" / "state_machine.yaml"
    if not state_machine_path.exists():
        raise FileNotFoundError(f"state_machine.yaml not found: {state_machine_path}")
    try:
        with open(state_machine_path, 'r', encoding='utf-8') as f:
            yaml.safe_load(f)
        print("[STARTUP] state_machine.yaml validated")
    except Exception as e:
        raise RuntimeError(
            f"Failed to load state_machine.yaml. FastAPI refusing to start. "
            f"Error: {e}"
        ) from e


def _validate_approval_logger_index() -> None:
    """B4: Verify composite index exists in approval log SQLite."""
    try:
        logger = ApprovalLogger()
        conn = sqlite3.connect(str(logger.db_path))
        try:
            cursor = conn.cursor()
            # Check if the composite index exists
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='index' AND name='idx_approval_log_composite'
            """)
            result = cursor.fetchone()
            if not result:
                raise RuntimeError(
                    "Composite index idx_approval_log_composite missing in approval_log table. "
                    "Run ApprovalLogger initialization first."
                )
            print("[STARTUP] ApprovalLogger composite index verified")
        finally:
            conn.close()
    except Exception as e:
        raise RuntimeError(
            f"ApprovalLogger validation failed. FastAPI refusing to start. "
            f"Error: {e}"
        ) from e


def _run_startup_validation() -> None:
    """Run all Section B boot-time validations."""
    print("[STARTUP] Running boot-time validation...")
    _validate_failed_routings_dir()
    _validate_routing_rules()
    _validate_state_machine()
    _validate_approval_logger_index()
    print("[STARTUP] Boot-time validation completed.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan: boot-time validation (Section B) + UoW recovery (A4)
    + kanban_store schema init (ARCH-DA5B0A2D A3) + Orchestrator.boot.

    Runs only when uvicorn starts the server, NOT on `import src.api`.
    This keeps tests, scripts, and tooling from triggering full startup side effects.

    The ``orchestrator.boot()`` call is what fires the VRAM eject + proposal-
    sync health check. Pre-2026-05-25 those used to live in
    ``Orchestrator.__init__`` and got triggered any time anything imported
    ``src.api`` (pytest, scripts, planner-driven flows) — which silently
    ejected models the user was actively working with. Splitting boot out
    of construct closes that gap.
    """
    _run_startup_validation()
    print("[STARTUP] Running UoW recovery...")
    run_recovery()
    print("[STARTUP] UoW recovery completed.")
    print("[STARTUP] Initialising kanban_store schema...")
    await kanban_store.init_schema()
    print("[STARTUP] kanban_store schema ready.")
    print("[STARTUP] Booting orchestrator (VRAM flush + sync health check)...")
    orchestrator.boot()
    print("[STARTUP] Orchestrator boot complete.")
    yield
    # No shutdown actions required at this time.


app = FastAPI(title="Cognitive OS API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- NEW: Dashboard & Config API ---
# Make paths absolute to be robust
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DASHBOARD_DIR = os.path.join(SCRIPT_DIR, '..', 'dashboard')
CONFIG_FILE_PATH = os.path.join(SCRIPT_DIR, '..', 'dev', 'master_config.md')

@app.get("/api/config")
def get_master_config():
    """Reads the master_config.md, parses the YAML, and returns it as JSON."""
    try:
        with open(CONFIG_FILE_PATH, 'r', encoding='utf-8') as f:
            content = f.read()
        
        yaml_match = re.search(r'```yaml\n(.*?)\n```', content, re.DOTALL)
        if not yaml_match:
            raise HTTPException(status_code=500, detail="Could not find YAML block in master_config.md")
        
        config = yaml.safe_load(yaml_match.group(1))
        return config
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="master_config.md not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error parsing config: {e}")

@app.get("/api/models")
def get_available_models():
    """Queries the local LM Studio server for a live list of installed models."""
    try:
        from src.llm_client import llm
        # Fetch the list of models from LM Studio using the standard OpenAI client
        models_response = llm.client.models.list()
        
        # Extract just the ID strings from the response objects
        # We also filter out any that might be None or empty just to be safe
        model_list = [model.id for model in models_response.data if model.id]
        
        # Sort them alphabetically for easier reading in the dropdown
        model_list.sort(key=lambda x: x.lower())
        
        return {"models": model_list}
    except Exception as e:
        print(f"Error fetching models from LM Studio: {e}")
        # If LM Studio isn't running, return an empty list rather than crashing the dashboard
        return {"models": []}

@app.post("/api/config")
async def save_master_config(request: Request):
    """Receives a JSON config, converts it to YAML, and saves it back to master_config.md."""
    try:
        new_config_json = await request.json()
        
        # Read the existing file to preserve the frontmatter
        with open(CONFIG_FILE_PATH, 'r', encoding='utf-8') as f:
            content = f.read()
        
        frontmatter_match = re.match(r'(---\s*.*?\s*---)', content, re.DOTALL)
        frontmatter = frontmatter_match.group(1) if frontmatter_match else "---"

        # Convert the incoming JSON back to a nice YAML string
        new_yaml_str = yaml.dump(new_config_json, indent=2, sort_keys=False, width=9999)
        
        new_content = f"{frontmatter}\n\n```yaml\n{new_yaml_str}```\n"
        
        with open(CONFIG_FILE_PATH, 'w', encoding='utf-8') as f:
            f.write(new_content)
            
        return {"status": "success", "message": "Configuration saved successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error saving config: {e}")

# --- NEW: System Visualization Endpoints ---

@app.get("/api/system/load")
def get_system_load() -> Dict[str, Any]:
    """Get current system resource usage (CPU, GPU, RAM)."""
    try:
        # Get CPU usage percentage
        cpu_percent = psutil.cpu_percent(interval=0.1)
        
        # Get memory usage
        memory = psutil.virtual_memory()
        memory_percent = memory.percent
        memory_used_gb = memory.used / (1024**3)
        memory_total_gb = memory.total / (1024**3)
        
        # Try to get GPU usage for all GPUs via pynvml (nvidia-ml-py).
        # We previously used GPUtil but it relies on `distutils` which is gone
        # in Python 3.14. pynvml is NVIDIA's official binding and reports the
        # same numbers as `nvidia-smi`. Two failure modes are surfaced loudly
        # (printed to stderr) instead of silently swallowed — explicit dev/user
        # rule: no silent drops in the diagnostic path.
        gpu1_info = {"percent": 0, "memory_used_gb": 0, "memory_total_gb": 0, "available": False}
        gpu2_info = {"percent": 0, "memory_used_gb": 0, "memory_total_gb": 0, "available": False}
        gpu_probe_error = None

        try:
            import warnings
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", category=FutureWarning, module="pynvml")
                import pynvml
            pynvml.nvmlInit()
            try:
                gpu_count = pynvml.nvmlDeviceGetCount()
                for idx in range(min(gpu_count, 2)):
                    handle = pynvml.nvmlDeviceGetHandleByIndex(idx)
                    name = pynvml.nvmlDeviceGetName(handle)
                    if isinstance(name, bytes):
                        name = name.decode("utf-8", errors="replace")
                    mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
                    util = pynvml.nvmlDeviceGetUtilizationRates(handle)
                    try:
                        temp = pynvml.nvmlDeviceGetTemperature(
                            handle, pynvml.NVML_TEMPERATURE_GPU
                        )
                    except Exception:
                        temp = None
                    info = {
                        "percent": float(util.gpu),
                        "memory_used_gb": mem.used / (1024 ** 3),
                        "memory_total_gb": mem.total / (1024 ** 3),
                        "available": True,
                        "name": name,
                        "temperature": temp,
                    }
                    if idx == 0:
                        gpu1_info = info
                    elif idx == 1:
                        gpu2_info = info
            finally:
                pynvml.nvmlShutdown()
        except ImportError as exc:
            gpu_probe_error = f"pynvml not installed ({exc}); run: pip install nvidia-ml-py"
            print(f"[GPU PROBE] {gpu_probe_error}", file=sys.stderr)
        except Exception as exc:
            gpu_probe_error = f"pynvml probe failed: {exc!r}"
            print(f"[GPU PROBE] {gpu_probe_error}", file=sys.stderr)
        
        return {
            "cpu": {
                "percent": cpu_percent,
                "cores": psutil.cpu_count()
            },
            "memory": {
                "percent": memory_percent,
                "used_gb": round(memory_used_gb, 2),
                "total_gb": round(memory_total_gb, 2)
            },
            "gpu": gpu1_info,  # Keep backward compatibility
            "gpu1": gpu1_info,
            "gpu2": gpu2_info,
            "gpu_probe_error": gpu_probe_error,  # null on success; string on failure (no silent drops)
            "timestamp": os.path.getmtime(__file__)  # Use file mod time as a simple timestamp
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting system load: {e}")

@app.get("/api/system/{diagram_type}")
def get_system_diagram(diagram_type: str):
    """
    Analyzes the system and returns a Mermaid diagram definition.
    This endpoint powers the visualization tabs on the dashboard.
    """
    if diagram_type == "structure":
        diagram = generate_structure_diagram()
    elif diagram_type == "flow":
        diagram = generate_flow_diagram()
    elif diagram_type == "kanban":
        diagram = generate_kanban_diagram()
    else:
        raise HTTPException(status_code=404, detail="Diagram type not found")
        
    return {"diagram": diagram}

def generate_structure_diagram():
    """Generates a Mermaid diagram of the cognitive-os file structure."""
    base_path = os.path.join(SCRIPT_DIR, '..')
    diagram = ["graph TD", "    subgraph CognitiveOS"]
    
    # Define key directories and files
    key_items = {
        "src": ["api.py", "orchestrator.py", "sentry_router.py", "kanban_store.py", "llm_client.py"],
        "dev": ["master_config.md"],
        "dashboard": ["index.html", "styles.css", "script.js"]
    }

    for d, files in key_items.items():
        diagram.append(f"        subgraph {d}")
        for f in files:
            diagram.append(f"            {d}_{f.replace('.', '_')}[{f}]")
        diagram.append("        end")

    diagram.append("    end")
    return "\n".join(diagram)

def generate_flow_diagram():
    """Analyzes sentry_router and orchestrator to map request flows."""
    # This is a simplified analysis for demonstration. A real implementation would parse the Python AST.
    diagram = [
        "graph TD",
        "    A[User Input] --> B{SentryRouter};",
        "    B --> |/technical, code...| C(TECHNICAL_MEETING);",
        "    B --> |/design, art...| D(DESIGN_MEETING);",
        "    B --> |/boardroom, strategy...| E(SEQUENTIAL_BOARDROOM);",
        "    B --> |/oracle| F(ORACLE_COUNCIL);",
        "    B --> |/dev| G(DEVELOPMENT_LIFECYCLE);",
        "    B --> |low complexity| H(SIMPLE);",
        "    B --> |medium complexity| I(STANDARD);",
        "    C --> C1(Orchestrator: execute_technical_meeting);",
        "    D --> D1(Orchestrator: execute_design_meeting);",
        "    E --> E1(Orchestrator: execute_sequential_boardroom);",
        "    F --> F1(Orchestrator: execute_oracle_council);",
        "    G --> G1(Kanban Processor);",
        "    H --> H1(Orchestrator: execute_simple);",
        "    I --> I1(Orchestrator: execute_standard);",
        "    style C fill:#8b1212,stroke:#333,stroke-width:2px",
        "    style D fill:#8b1212,stroke:#333,stroke-width:2px",
        "    style E fill:#8b1212,stroke:#333,stroke-width:2px",
        "    style F fill:#8b1212,stroke:#333,stroke-width:2px",
    ]
    return "\n".join(diagram)

def generate_kanban_diagram():
    """Map the automated workflow driven by /api/workflow/transition."""
    diagram = [
        "graph TD",
        "    A[Card moved: Backlog → Proposal] --> B{/api/workflow/transition};",
        "    B --> C[Severity dispatcher BackgroundTask];",
        "    C --> D{severity?};",
        "    D -->|high| E(Sequential Boardroom);",
        "    D -->|medium| F(Technical Meeting);",
        "    D -->|low| G(AUTO-APPROVED);",
        "    E --> H[approval_log row written];",
        "    F --> H;",
        "    G --> H;",
        "    I[Card moved: Proposal → Beta Testing] --> J{Approval gate};",
        "    J -->|approved| K(dev_beta_council BackgroundTask);",
        "    J -->|not approved| L[422 REJECTED];",
        "    K --> M[BETA_HANDOFF.md written];",
        "    N[Card moved: Beta → Alpha] --> O[Orchestrator.continue_development_lifecycle];",
        "    O --> P(dev_alpha_polish);",
    ]
    return "\n".join(diagram)

# ---------------------------------------------------------------------------
# LM Studio lifecycle endpoints (SDK migration, DEV-20260521-001000-B5D5C0DE)
#
# All sync SDK calls go through asyncio.to_thread to honour the Chairman's
# CRITICAL veto: the FastAPI event loop must NEVER block during a ~15s load.
# ---------------------------------------------------------------------------

BENCH_RESULTS_PATH = os.path.join(
    SCRIPT_DIR, '..', 'scratch', 'bench_hermes_results.jsonl'
)


def _shared_loader():
    """Return the singleton LMStudioLoader, lazy-initialised."""
    from src.llm_client import LLMClient
    return LLMClient._get_loader()


class LoadConfigIn(BaseModel):
    context_length: Optional[int] = None
    n_parallel: Optional[int] = None
    flash_attention: Optional[bool] = None
    cache_type_k: Optional[str] = None
    cache_type_v: Optional[str] = None
    # Either a float in [0.0, 1.0] OR the literal strings 'max' / 'off'.
    # Matches the GpuRatio contract in lmstudio_schema.py.
    gpu_offload_ratio: Optional[Union[float, str]] = None
    gpu: Optional[str] = None  # e.g. "max", "auto"


class SamplingIn(BaseModel):
    """Per-model sampling defaults. NOT load-time — these are applied at
    inference (chat.completions) and persisted to LM Studio's per-model
    GUI prefs so subsequent JIT-loads pick them up automatically."""
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    top_k: Optional[int] = None
    min_p: Optional[float] = None
    repeat_penalty: Optional[float] = None
    max_tokens: Optional[int] = None


class LoadRequest(BaseModel):
    model_key: str
    identifier: Optional[str] = None
    config: Optional[LoadConfigIn] = None
    sampling: Optional[SamplingIn] = None
    ttl: Optional[int] = None
    force_reload: Optional[bool] = False


@app.get("/api/loaded")
async def list_loaded_and_downloaded():
    """Snapshot of currently loaded + downloaded models from the loader.

    If LM Studio is offline / unreachable, returns empty lists with an
    ``lm_studio_offline`` flag rather than 500ing — the dashboard's other
    tabs (kanban, system, etc.) must keep working when LM Studio is down.
    """
    loader = _shared_loader()

    def _snapshot():
        loaded = []
        try:
            instances = loader.list_loaded()
        except Exception as exc:  # noqa: BLE001 — LM Studio down, etc.
            print(f"[API /api/loaded] LM Studio unreachable: {exc!r}")
            return {"loaded": [], "downloaded": [], "lm_studio_offline": True}
        for inst in instances:
            entry = {
                "identifier": inst.identifier,
                "model_key": inst.model_key,
            }
            try:
                eff = loader.get_effective_config(inst.identifier)
                if isinstance(eff, dict):
                    entry["context_length"] = eff.get("contextLength") or eff.get("context_length")
                    entry["path"] = eff.get("path")
            except Exception:
                pass
            loaded.append(entry)
        try:
            downloaded = sorted(d.model_key for d in loader.list_downloaded())
        except Exception:
            downloaded = []
        return {"loaded": loaded, "downloaded": downloaded, "lm_studio_offline": False}

    return await asyncio.to_thread(_snapshot)


def _write_sampling_prefs(model_path: str, sampling: dict) -> Optional[str]:
    """Write sampling defaults into LM Studio's per-model GUI prefs file.

    LM Studio stores per-model overrides at
        ~/.lmstudio/.internal/user-concrete-model-default-config/<path>.json
    using dotted keys like 'llm.prediction.temperature'. Writing here means
    every subsequent JIT-load (including ones triggered by chat.completions
    without an explicit POST /api/load) picks up these defaults.

    Returns the path written, or None if model_path is empty / write failed.
    """
    if not model_path:
        return None
    user_profile = os.environ.get("USERPROFILE", "")
    if not user_profile:
        return None
    cfg_root = os.path.join(
        user_profile, ".lmstudio", ".internal",
        "user-concrete-model-default-config",
    )
    cfg_file = os.path.join(cfg_root, model_path.replace("/", os.sep) + ".json")
    os.makedirs(os.path.dirname(cfg_file), exist_ok=True)

    # Map our snake_case sampling keys to LM Studio's dotted prefs keys.
    KEY_MAP = {
        "temperature":    "llm.prediction.temperature",
        "top_p":          "llm.prediction.topPSampling",
        "top_k":          "llm.prediction.topKSampling",
        "min_p":          "llm.prediction.minPSampling",
        "repeat_penalty": "llm.prediction.repeatPenalty",
        "max_tokens":     "llm.prediction.maxPredictedTokens",
    }

    # Merge with existing file (preserve any load-config fields already there).
    existing: dict = {"fields": []}
    if os.path.exists(cfg_file):
        try:
            with open(cfg_file, "r", encoding="utf-8") as f:
                existing = json.load(f) or {"fields": []}
        except Exception:
            existing = {"fields": []}
    fields = existing.get("fields") or []
    indexed = {f.get("key"): i for i, f in enumerate(fields) if isinstance(f, dict)}

    for skey, dotted in KEY_MAP.items():
        if skey not in sampling:
            continue
        entry = {"key": dotted, "value": sampling[skey]}
        if dotted in indexed:
            fields[indexed[dotted]] = entry
        else:
            fields.append(entry)
            indexed[dotted] = len(fields) - 1

    existing["fields"] = fields
    try:
        with open(cfg_file, "w", encoding="utf-8") as f:
            json.dump(existing, f, indent=2)
        return cfg_file
    except Exception:
        return None


@app.post("/api/load")
async def load_model(req: LoadRequest):
    """Load (or reload) a model under the loader. Honours full config schema."""
    loader = _shared_loader()
    cfg = (req.config.model_dump(exclude_none=True) if req.config else {})
    sampling = (req.sampling.model_dump(exclude_none=True) if req.sampling else {})

    def _do_load():
        # Auto-refresh catalog if the model_key was newly downloaded.
        try:
            known = {d.model_key for d in loader.list_downloaded()}
            if req.model_key not in known:
                loader.refresh_catalog()
        except Exception:
            pass
        return loader.ensure_loaded(
            req.model_key,
            config=cfg,
            ttl=req.ttl,
            instance_identifier=req.identifier,
            force_reload=bool(req.force_reload),
        )

    try:
        result = await asyncio.to_thread(_do_load)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"load failed: {e!r}")

    # Persist sampling defaults to per-model GUI prefs (best-effort).
    sampling_written_to = None
    if sampling:
        # Resolve the gguf path from the catalog so we write to the right file.
        try:
            for d in loader.list_downloaded():
                if d.model_key == result.model_key:
                    sampling_written_to = await asyncio.to_thread(
                        _write_sampling_prefs, d.path, sampling
                    )
                    break
        except Exception:
            pass

    return {
        "status": "ok",
        "action": result.action,
        "identifier": result.identifier,
        "model_key": result.model_key,
        "duration_s": result.duration_seconds,
        "config_applied": result.config_applied,
        "sampling_applied": sampling,
        "sampling_written_to": sampling_written_to,
    }


@app.delete("/api/load/{identifier}")
async def unload_model(identifier: str):
    """Unload a running model by its identifier."""
    loader = _shared_loader()
    try:
        await asyncio.to_thread(loader.unload, identifier)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"unload failed: {e!r}")
    return {"status": "ok", "identifier": identifier}


def _bench_new_model(model_key: str) -> None:
    """Background-task entrypoint that benches a freshly-downloaded model.

    Shells out to ``scripts/bench_hermes.py`` so the bench harness lives
    in one place (A6 of DEV-…-B5D5C0DE) instead of duplicating its logic
    inline. The script appends one JSONL row to
    ``scratch/bench_hermes_results.jsonl`` which the dashboard's
    Benchmarks tab reads via ``/api/benchmarks``.

    Failures are logged loudly but never raised — this runs from a
    FastAPI BackgroundTask, the request has already returned 200.
    """
    import subprocess
    repo_root = Path(__file__).resolve().parent.parent  # cognitive-os/
    script = repo_root / "scripts" / "bench_hermes.py"
    if not script.exists():
        print(f"[BENCH-RUNNER] bench script missing: {script}")
        return
    try:
        print(f"[BENCH-RUNNER] benching new model: {model_key}")
        result = subprocess.run(
            [sys.executable, str(script), model_key],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=600,  # 10-minute hard ceiling per bench
        )
        if result.returncode == 0:
            print(f"[BENCH-RUNNER] ✅ {model_key} baseline recorded")
        else:
            print(
                f"[BENCH-RUNNER] ⚠️ {model_key} bench exited "
                f"{result.returncode}: {result.stderr.strip()[:300]}"
            )
    except subprocess.TimeoutExpired:
        print(f"[BENCH-RUNNER] ❌ {model_key} timed out (>10min)")
    except Exception as exc:  # noqa: BLE001
        print(f"[BENCH-RUNNER] ❌ {model_key} failed: {exc!r}")


@app.post("/api/catalog/refresh")
async def refresh_catalog(
    background_tasks: BackgroundTasks,
    bench_new: bool = False,
):
    """Force the loader to re-scan the LM Studio catalog (after new download).

    When ``bench_new=true`` is passed, any model_keys that are present
    after the refresh but were not present before get scheduled as a
    background bench-runner job (A7 of DEV-…-B5D5C0DE). Returns the
    list of new keys so the dashboard can show "benching now…" badges.
    """
    loader = _shared_loader()

    def _refresh_and_diff() -> tuple[list[str], list[str]]:
        # Snapshot the existing catalog first so we know what's new.
        before = set(loader._downloaded_cache.keys()) if loader._downloaded_cache else set()
        cache = loader.refresh_catalog()  # returns dict[model_key, raw]
        after = set(cache.keys())
        return sorted(after), sorted(after - before)

    keys, new_keys = await asyncio.to_thread(_refresh_and_diff)

    if bench_new:
        for mk in new_keys:
            background_tasks.add_task(_bench_new_model, mk)

    return {
        "count": len(keys),
        "model_keys": keys,
        "new_keys": new_keys,
        "benching": new_keys if bench_new else [],
    }


@app.get("/api/lmstudio/logs")
def lmstudio_logs(lines: int = 200, filter: Optional[str] = None):
    """Tail the most-recently-modified LM Studio server log.

    Args:
        lines:  How many lines from the end to return. Capped at 2000.
        filter: Optional substring filter (case-insensitive). Useful for
                pulling only "LlamaV4::load", "pipeline parallelism",
                "n_seq_max", etc. — the bench-runner SOP's signal patterns.
    """
    import glob

    lines = max(1, min(int(lines), 2000))

    log_dir = os.path.join(
        os.environ.get("USERPROFILE", ""), ".lmstudio", "server-logs"
    )
    if not os.path.isdir(log_dir):
        return {"file": None, "lines": [], "error": f"log dir not found: {log_dir}"}

    candidates = glob.glob(os.path.join(log_dir, "**", "*.log"), recursive=True)
    if not candidates:
        return {"file": None, "lines": [], "error": "no .log files found"}

    log_file = max(candidates, key=os.path.getmtime)
    file_size = os.path.getsize(log_file)

    # Read just the last ~lines*200 bytes (rough average line length) to avoid
    # slurping a multi-megabyte log on every poll.
    approx_tail = min(file_size, max(lines * 250, 16_384))
    out: list[str] = []
    try:
        with open(log_file, "rb") as f:
            f.seek(file_size - approx_tail)
            raw = f.read().decode("utf-8", errors="replace")
        # Drop the first partial line (we likely seeked into the middle of one)
        chunks = raw.split("\n")[1:] if approx_tail < file_size else raw.split("\n")
        if filter:
            needle = filter.lower()
            chunks = [c for c in chunks if needle in c.lower()]
        out = chunks[-lines:]
    except Exception as e:
        return {"file": log_file, "lines": [], "error": repr(e)}

    return {
        "file": log_file,
        "file_size": file_size,
        "returned": len(out),
        "lines": out,
    }


@app.get("/api/benchmarks")
def benchmarks():
    """Return all rows of the bench results JSONL for the dashboard."""
    runs = []
    if os.path.exists(BENCH_RESULTS_PATH):
        with open(BENCH_RESULTS_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    runs.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    # Newest first
    runs.sort(key=lambda r: r.get("ts", ""), reverse=True)
    return {"count": len(runs), "runs": runs}


# Initialize Governance Foundation (A1, ARCH-2007E0A1)
# Boot-time validation: load rules/state at startup, fail fast if malformed
ROUTING_RULES_PATH = Path(__file__).resolve().parent.parent / "config" / "routing_rules.yaml"
STATE_MACHINE_PATH = Path(__file__).resolve().parent.parent / "config" / "state_machine.yaml"

# Validate routing rules (E3: fail-fast)
load_routing_rules(ROUTING_RULES_PATH)

# Validate state machine exists (B2: boot-time check)
if not STATE_MACHINE_PATH.exists():
    raise FileNotFoundError(f"State machine config not found: {STATE_MACHINE_PATH}")

# Initialize backend writer and router
DEAD_LETTER_DIR = DEV_DIR / "failed_routings"
backend_writer = FilesystemBackendWriter(base_dir=DEV_DIR, dead_letter_dir=DEAD_LETTER_DIR)
output_router = OutputRouter(
    rules_path=ROUTING_RULES_PATH,
    backend_writer=backend_writer,
    dead_letter_dir=DEAD_LETTER_DIR
)
print("[GOV] OutputRouter initialized successfully")

# Initialize Core Services Globally
orchestrator = Orchestrator(output_router=output_router)  # A2: Direct injection
obsidian = ObsidianWriter()

# ARCH-DA5B0A2D (A3): SQLite-backed kanban store. Schema is created via
# the lifespan hook so ``import src.api`` stays side-effect-free.
kanban_store = KanbanStore()

class PromptRequest(BaseModel):
    prompt: str
    image_base64: Optional[str] = None
    compass_weight: Optional[str] = None
    model_presets: Optional[list] = None
    document_base64: Optional[str] = None
    is_pdf: Optional[bool] = None
    source_file_path: Optional[str] = None

@app.post("/api/process")
async def process_prompt(request: PromptRequest):
    """
    Receives a prompt from Obsidian or other interfaces,
    runs the Cognitive OS, and routes the synthesis via OutputRouter.
    """
    print(f"\n🌐 API Request Received: {request.prompt[:50]}...")
    
    try:
        # 1. Run Council
        result = await orchestrator.process_request(
            request.prompt, 
            image_base64=request.image_base64,
            compass_weight=request.compass_weight,
            model_presets=request.model_presets,
            document_base64=request.document_base64,
            is_pdf=request.is_pdf,
            source_file_path=request.source_file_path
        )

        # 2. Persist synthesis via OutputRouter.
        #
        # Heterogeneous return contract from orchestrator.process_request:
        #  - Boardroom / oracle / technical / design meetings: orchestrator
        #    already routed via the injected OutputRouter (see
        #    _execute_orchestrated_meeting), so `result` is a Path.
        #  - Simple / standard / vision / nft / dev_lifecycle: orchestrator
        #    returns a str. Route it here.
        #
        # Calling output_router.route() on a Path crashes (Path has no
        # splitlines). Branch on type to avoid the double-route regression.
        if isinstance(result, Path):
            path = result
            decision = None
            response_payload = str(result)
        else:
            decision = output_router.route(result)
            path = output_router.apply(result, decision)
            response_payload = result

        # 3. Get task_id for the response
        task_id = orchestrator.memory.generate_task_id(request.prompt)

        return {
            "status": "success",
            "routing_decision": (
                {
                    "rule_name": decision.rule_name,
                    "destination": decision.destination,
                    "workflow_phase": decision.workflow_phase,
                    "severity": decision.severity,
                    "matched_markers": decision.matched_markers,
                }
                if decision is not None
                else {"rule_name": "orchestrator_routed", "destination": None}
            ),
            "saved_path": str(path),
            "task_id": task_id,
            "response": response_payload,
            "oversight": orchestrator.memory.get_task_data(task_id).get("oversight_analysis", {}).get("raw_analysis", "")
        }
        
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"\n🚨 FATAL ERROR IN /PROCESS ENDPOINT 🚨\n{error_trace}\n")
        return {
            "status": "error",
            "response": f"System Error: {str(e)}",
            "details": error_trace
        }

# ============================================================================
# Direct Role Chat API Endpoint (Dashboard Unified Chatbox)
# ============================================================================

class RoleChatRequest(BaseModel):
    role: str
    message: str
    history: list = []

@app.post("/api/chat/role")
def chat_with_role(request: RoleChatRequest):
    """
    Direct conversation with a specific role, maintaining multi-turn history.
    
    Args:
        role: Name of the role to chat with
        message: User's message
        history: Previous conversation history [{"role": "user"|"assistant", "content": "..."}]
    
    Returns:
        response: Role's response
        history: Updated conversation history
    """
    try:
        # Build conversation context from history
        conversation_context = []
        for msg in request.history:
            conversation_context.append(f"{msg.get('role', 'unknown')}: {msg.get('content', '')}")
        
        # Append current message
        full_prompt = request.message
        if conversation_context:
            context_str = "\n".join(conversation_context)
            full_prompt = f"Previous conversation:\n{context_str}\n\nUser: {request.message}"
        
        # Get role configuration
        config_path = Path(__file__).resolve().parent.parent / "dev" / "master_config.md"
        with open(config_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Extract YAML config
        import yaml
        yaml_match = re.search(r'```yaml\s*(.*?)\s*```', content, re.DOTALL)
        if not yaml_match:
            raise ValueError("Could not extract YAML from master_config.md")
        
        config = yaml.safe_load(yaml_match.group(1))
        
        if request.role not in config.get('roles', {}):
            raise HTTPException(status_code=404, detail=f"Role '{request.role}' not found in configuration")
        
        role_config = config['roles'][request.role]
        
        # Send to LLM using the orchestrator's LLM client
        from src.llm_client import LLMClient
        llm_client = LLMClient()
        
        # Get model from role config or use default
        model = role_config.get('model', 'local-model')
        
        response_text = llm_client.generate_response(
            prompt=full_prompt,
            system_prompt=role_config.get('system_prompt', ''),
            model=model,
            temperature=role_config.get('temperature', 0.7),
            max_tokens=role_config.get('max_tokens', 2048)
        )
        
        # Update history
        updated_history = request.history + [
            {"role": "user", "content": request.message},
            {"role": "assistant", "content": response_text}
        ]
        
        return {
            "response": response_text,
            "history": updated_history
        }
        
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"\n🚨 ERROR IN /CHAT/ROLE ENDPOINT 🚨\n{error_trace}\n")
        return {
            "error": f"Error communicating with role: {str(e)}",
            "response": None
        }

# ============================================================================
# Proposal Sync API Endpoints (DEV-20260521-001000-B5D5C0DE)
# ============================================================================

from src.proposal_sync import ProposalSyncManager

# Initialize sync manager
sync_manager = ProposalSyncManager()

@app.get("/api/sync/status")
def get_sync_status():
    """
    Get current sync status with health indicator.
    
    Returns:
        - health: "green" (in sync), "yellow" (missing files), or "red" (conflicts)
        - backend_count: Number of proposal files in backend
        - vault_count: Number of proposal files in vault
        - missing_in_vault: List of filenames missing in vault
        - conflicts: List of files with content conflicts
    """
    try:
        status = sync_manager.check_sync_status()
        return status.to_dict()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error checking sync status: {e}")

@app.get("/api/sync/proposals")
def list_proposals_with_status():
    """
    List all proposals with their sync status.
    
    Returns:
        List of proposals with backend/vault existence and hash info
    """
    try:
        from src.proposal_sync import ProposalSyncManager, SyncStatus
        
        # Get files from both locations
        backend_files = sync_manager._get_proposal_files(sync_manager.proposals_dir)
        vault_files = sync_manager._get_proposal_files(sync_manager.vault_dir)
        
        # Create lookup dictionaries
        vault_hashes = {f.filename: f for f in vault_files}
        
        proposals = []
        for file in backend_files:
            in_vault = file.filename in vault_hashes
            vault_hash = vault_hashes[file.filename].content_hash if in_vault else None
            
            proposals.append({
                "filename": file.filename,
                "proposal_id": file.proposal_id,
                "in_backend": True,
                "in_vault": in_vault,
                "backend_hash": file.content_hash,
                "vault_hash": vault_hash,
                "size": file.size,
                "modified_at": file.modified_at.isoformat()
            })
        
        return {"proposals": proposals, "count": len(proposals)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing proposals: {e}")

@app.get("/api/sync/missing")
def get_missing_proposals():
    """
    Get list of proposals missing in vault (exist in backend only).
    
    Returns:
        List of filenames missing in vault
    """
    try:
        missing = sync_manager.get_missing_files()
        return {"missing": missing, "count": len(missing)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting missing proposals: {e}")

@app.get("/api/sync/conflicts")
def get_conflicts():
    """
    Get list of files with conflicts between backend and vault.
    
    Returns:
        List of conflict details
    """
    try:
        conflicts = sync_manager.detect_conflicts()
        return {"conflicts": conflicts, "count": len(conflicts)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error detecting conflicts: {e}")

@app.post("/api/sync/force-sync")
def force_sync_proposals():
    """
    Force a sync from backend to vault.
    
    Returns:
        SyncResult with details about the operation
    """
    try:
        result = sync_manager.sync_backend_to_vault()
        
        if result.success:
            return {
                "status": "success",
                "message": f"Synced {result.files_synced} files",
                "result": result.to_dict()
            }
        else:
            return {
                "status": "partial_success",
                "message": f"Sync completed with errors",
                "result": result.to_dict()
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error during sync: {e}")

@app.get("/api/sync/history")
def get_sync_history(limit: int = 10):
    """
    Get sync operation history.
    
    Args:
        limit: Maximum number of records to return
        
    Returns:
        List of sync history records
    """
    try:
        history = sync_manager.get_sync_history(limit=limit)
        return {"history": history, "count": len(history)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting sync history: {e}")


# ============================================================================
# Kanban Migration API (ARCH-20260522-205800-DA5B0A2D, A3)
# ----------------------------------------------------------------------------
# SQLite is now the single source of truth for board state. The vault
# Dashboard at http://127.0.0.1:5000 is the only board editor; the
# vault Dev-KanBan.md mirror was deleted 2026-05-26 (zero purpose).
#
# Endpoints:
#   GET  /api/kanban/board               -> current BoardSnapshot
#   POST /api/kanban/cards               -> add a new card
#   POST /api/workflow/transition        -> move a card (writes vault mirror)
#   POST /api/workflow/rollback/{id}     -> revert to the previous column
#   GET  /api/workflow/state/{id}        -> card + last 10 transitions
#
# Per CSTR (proposal §"Difficulties"): every store call is async (uses
# asyncio.to_thread under the hood) so the FastAPI event loop never blocks.
# ============================================================================


class AddCardRequest(BaseModel):
    """Payload for ``POST /api/kanban/cards``."""

    proposal_id: str
    prefix: str
    column_name: str = "backlog"
    title: Optional[str] = None
    substatus: Optional[str] = None
    severity: Optional[str] = None
    origin: Optional[str] = None
    approver: str = "dashboard"
    reason: Optional[str] = None


class TransitionRequestPayload(BaseModel):
    """Payload for ``POST /api/workflow/transition``.

    Naming note: the existing ``src.workflow_models.TransitionRequest`` is
    a Pydantic model used by ``workflow_engine``. To avoid name-collision
    confusion at the API layer, we shape this slightly differently and
    keep the suffix ``Payload``. ``workflow_engine.transition`` is NOT
    invoked here — that's a Phase 3+4 concern (gate enforcement, sagas).
    This endpoint is the dashboard-side drag-drop signal: it updates the
    board state directly. Gate enforcement is layered in by a later
    proposal that wraps the call.
    """

    proposal_id: str
    target_column: str
    target_substatus: Optional[str] = None
    approver: str = "dashboard"
    reason: Optional[str] = None
    gate_passed: int = 0  # -1 failed | 0 N/A | 1 passed
    gate_details: Optional[Dict[str, Any]] = None
    archive_hash: Optional[str] = None


# NB: the vault-mirror render path (kanban_renderer.write_vault_mirror) was
# deleted 2026-05-26. SQLite is the single source of truth; the dashboard at
# http://127.0.0.1:5000 is the only board editor. The vault Dev-KanBan.md
# served no purpose post-watcher-removal — it was a read-only mirror nobody
# could act on.


@app.get("/api/kanban/board")
async def get_kanban_board():
    """Return the full board snapshot, columns in canonical order."""
    try:
        snap = await kanban_store.get_board()
        return snap.to_dict()
    except KanbanStoreError as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/kanban/cards")
async def add_kanban_card(req: AddCardRequest):
    """Add a new card. Idempotent: returns the existing card if already filed."""
    try:
        card = await kanban_store.add_card(
            proposal_id=req.proposal_id,
            prefix=req.prefix,
            column_name=req.column_name,
            title=req.title,
            substatus=req.substatus,
            severity=req.severity,
            origin=req.origin,
            approver=req.approver,
            reason=req.reason,
        )
    except InvalidColumn as exc:
        raise HTTPException(status_code=422, detail=f"Invalid column: {exc}")
    except InvalidPrefix as exc:
        raise HTTPException(status_code=422, detail=f"Invalid prefix: {exc}")
    except KanbanStoreError as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return {
        "status": "success",
        "card": card.to_dict(),
    }


#: Default substatus when a card enters a column that runs a micro-
#: lifecycle (planning -> coding -> testing -> review). Applied only
#: when the caller did NOT supply an explicit ``target_substatus``,
#: so drag-drop into Beta/Alpha lands on ``planning`` automatically
#: while substatus-dropdown changes (which DO supply a value) are
#: untouched.
#:
#: ``proposal`` → ``pending_council``: card just landed, the severity
#:   dispatcher is running. The dispatcher overwrites this to
#:   ``approved`` / ``rejected`` / ``auto-approved`` when it finishes.
#:
#: ``backlog`` is intentionally absent: a card moved back to backlog
#:   after a REJECTED verdict KEEPS its ``rejected`` substatus so the
#:   board still flags "needs rework".
_DEFAULT_SUBSTATUS_ON_ENTRY = {
    "proposal": "pending_council",
    "beta testing": "planning",
    "alpha polish": "planning",
}


# ----------------------------------------------------------------------------
# Phase-transition automation (kills the deprecated kanban_processor watcher)
# ----------------------------------------------------------------------------
# When a card enters the `proposal` column we dispatch a council based on the
# card's severity, then record the verdict in ``approval_log`` so the
# proposal → beta_testing drag can gate on it. When the card then enters
# `beta_testing` we run the dev_beta_council role and produce a handoff doc.
#
# All council work runs in a FastAPI BackgroundTask so the HTTP response
# stays sub-second; the dashboard polls /api/kanban/board for the result.
# ----------------------------------------------------------------------------

def _read_proposal_text(proposal_id: str) -> Optional[str]:
    """Return the markdown body of the backend proposal file, or None.

    Looks up the file by id-suffix match in ``dev/proposals/``. We don't
    fall back to the vault here — the backend is authoritative for the
    council inputs (the vault may contain a stale render).
    """
    return None if _proposal_path(proposal_id) is None else _proposal_path(proposal_id).read_text(encoding="utf-8")


def _proposal_path(proposal_id: str) -> Optional[Path]:
    """Resolve the backend proposal file Path for ``proposal_id`` or None."""
    if not PROPOSALS_DIR.exists():
        return None
    for entry in PROPOSALS_DIR.iterdir():
        if entry.is_file() and entry.suffix.lower() == ".md" and proposal_id in entry.name:
            return entry
    return None


def _append_verdict_to_proposal(
    proposal_id: str,
    decision: str,
    reasoning_excerpt: str,
    council_name: str,
    log_path: Optional[Path],
) -> None:
    """Append a Council Verdict section to the backend proposal file.

    The same proposal can be revised and re-reviewed; we append, never
    overwrite, so the proposal preserves a full audit trail visible in
    the vault (via the existing ProposalSyncManager mirror).
    """
    path = _proposal_path(proposal_id)
    if path is None:
        print(f"[VERDICT] cannot append: no proposal file for {proposal_id!r}")
        return
    ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    emoji = {"APPROVED": "✅", "REJECTED": "❌", "AUTO-APPROVED": "🟢"}.get(decision, "🏛")
    section = [
        "",
        f"## {emoji} Council Verdict — {ts} ({council_name})",
        f"**Decision:** `{decision}`",
        "",
        "**Reasoning excerpt:**",
        "",
    ]
    excerpt = (reasoning_excerpt or "").strip()
    if len(excerpt) > 800:
        excerpt = excerpt[:800].rsplit(" ", 1)[0] + " …"
    if excerpt:
        for line in excerpt.splitlines() or [excerpt]:
            section.append(f"> {line}")
    else:
        section.append("> _(no reasoning provided)_")
    if log_path is not None:
        section += ["", f"[Full verdict log →]({log_path.as_posix()})"]
    section += ["", "---", ""]
    try:
        with path.open("a", encoding="utf-8") as f:
            f.write("\n".join(section))
        print(f"[VERDICT] appended {decision} to {path.name}")
    except OSError as exc:
        print(f"[VERDICT] failed to append to {path}: {exc!r}")


def _trigger_vault_sync() -> None:
    """Push the backend proposal updates into the vault. Best-effort."""
    try:
        sync_manager.sync_backend_to_vault()
    except Exception as exc:  # noqa: BLE001
        print(f"[VERDICT] vault sync failed: {exc!r}")


def _dispatch_proposal_council(proposal_id: str, severity: Optional[str]) -> None:
    """Run the severity-appropriate council and record the verdict.

    Severity policy (locked 2026-05-26):
      * ``high``    → Sequential Boardroom (board_strategist..chairman)
      * ``medium``  → Technical Meeting (technical_specialist..overseer)
      * ``low``     → no council; auto-APPROVE
      * unknown/None → treat as ``medium`` (safe default)

    Side-effects:
      1. Council output is written via the orchestrator's OutputRouter
         (so a markdown verdict lands in dev/decisions/ or AI-Help).
      2. An ``approval_log`` row is written with ``role='proposal_council'``
         and ``decision`` ∈ {APPROVED, REJECTED, AUTO-APPROVED}. The
         proposal → beta_testing gate reads this row.
      3. The card's ``substatus`` is updated to ``approved`` /
         ``rejected`` / ``auto-approved`` so the dashboard shows the
         verdict at a glance.

    Failures are logged loudly but never raised — the dashboard already
    returned 200, this is a background task.
    """
    sev_norm = (severity or "medium").strip().lower()
    proposal_text = _read_proposal_text(proposal_id) or ""

    user_input = (
        f"Review proposal {proposal_id} for approval.\n\n"
        f"Severity: {sev_norm}\n\n"
        f"Your verdict MUST contain ONE of these literal lines on its own:\n"
        f"  VERDICT: APPROVED\n"
        f"  VERDICT: REJECTED\n\n"
        f"Followed by reasoning. Proposal content follows:\n\n"
        f"---\n{proposal_text}\n---\n"
    )

    decision = "AUTO-APPROVED"
    substatus = "auto-approved"
    report: Optional[str] = None
    report_text = ""
    council_name = "auto-dispatcher"

    try:
        if sev_norm == "low":
            council_name = "auto-dispatcher"
            ApprovalLogger().log_approval(
                proposal_id=proposal_id,
                phase="proposal_council",
                status="AUTO-APPROVED",
                approver="severity_dispatcher",
                reason="low severity bypasses the council",
            )
        else:
            if sev_norm == "high":
                council_name = "Sequential Boardroom"
                report = orchestrator.execute_sequential_boardroom(user_input=user_input)
            else:  # medium / unknown
                council_name = "Technical Meeting"
                report = orchestrator.execute_technical_meeting(user_input=user_input)

            # `report` may be a Path (output_router-routed) or str.
            report_text = report.read_text(encoding="utf-8") if isinstance(report, Path) else (report or "")
            decision = "APPROVED" if "VERDICT: APPROVED" in report_text else (
                "REJECTED" if "VERDICT: REJECTED" in report_text else "APPROVED"
            )
            substatus = decision.lower()
            ApprovalLogger().log_approval(
                proposal_id=proposal_id,
                phase="proposal_council",
                status=decision,
                approver=("sequential_boardroom" if sev_norm == "high" else "technical_meeting"),
                reason=f"council verdict on severity={sev_norm}",
                decision_log_path=str(report) if isinstance(report, Path) else None,
            )

        # Stale-card guard: if the user moved the card OUT of `proposal`
        # while the council was running, our write-back becomes noise.
        # Skip the verdict-append + substatus update so the board reflects
        # the user's latest intent. The approval_log row still stands as
        # evidence the council ran, so a future re-entry into Proposal
        # (which re-fires the dispatcher) will overwrite it cleanly.
        try:
            current_card = asyncio.run(kanban_store.get_card(proposal_id))
        except Exception as exc:  # noqa: BLE001
            print(f"[DISPATCH] post-council card lookup failed: {exc!r}")
            current_card = None
        if current_card is not None and current_card.column_name != "proposal":
            print(
                f"[DISPATCH] {proposal_id}: card moved to "
                f"{current_card.column_name!r} during council run; "
                f"skipping verdict-append + substatus update"
            )
            return

        # Append a Council Verdict section to the proposal file so the
        # user (and the synced vault note) can read the reasoning inline.
        log_path = report if isinstance(report, Path) else None
        if decision == "AUTO-APPROVED":
            _append_verdict_to_proposal(
                proposal_id,
                decision,
                f"Severity={sev_norm}; auto-approved without council review.",
                council_name,
                log_path,
            )
        else:
            _append_verdict_to_proposal(
                proposal_id, decision, report_text, council_name, log_path
            )

        # Push the proposal change into the vault so Obsidian sees it.
        _trigger_vault_sync()

        # Update card substatus so the dashboard reflects the verdict.
        try:
            asyncio.run(_update_card_substatus(proposal_id, substatus))
        except RuntimeError:
            # Already in a loop (shouldn't happen — BackgroundTasks run
            # threaded). Fall through to async helper.
            pass

        print(f"[DISPATCH] {proposal_id} severity={sev_norm} → {decision}")
    except Exception as exc:  # noqa: BLE001 — background task; never raise
        import traceback
        print(f"[DISPATCH][ERROR] {proposal_id}: {exc!r}\n{traceback.format_exc(limit=4)}")
        try:
            ApprovalLogger().log_approval(
                proposal_id=proposal_id,
                phase="proposal_council",
                status="ERROR",
                approver="severity_dispatcher",
                reason=f"{type(exc).__name__}: {exc}",
            )
        except Exception:
            pass
        try:
            asyncio.run(_update_card_substatus(proposal_id, "council_error"))
        except Exception:
            pass


async def _update_card_substatus(proposal_id: str, substatus: str) -> None:
    """Async helper to update a card's substatus in the kanban store."""
    try:
        await kanban_store.update_card(proposal_id, {"substatus": substatus})
    except Exception as exc:  # noqa: BLE001
        print(f"[DISPATCH] failed to update substatus for {proposal_id}: {exc!r}")


def _proposal_is_approved(proposal_id: str) -> bool:
    """Return True if approval_log has an APPROVED / AUTO-APPROVED row for
    the proposal_council phase of this proposal."""
    try:
        logger = ApprovalLogger()
        conn = sqlite3.connect(str(logger.db_path))
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT decision FROM approval_log "
                "WHERE proposal_id = ? AND role = 'proposal_council' "
                "ORDER BY id DESC LIMIT 1",
                (proposal_id,),
            )
            row = cur.fetchone()
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001
        print(f"[GATE] approval_log read failed for {proposal_id}: {exc!r}")
        return False
    if not row:
        return False
    decision = (row[0] or "").upper()
    return decision.startswith("APPROVED") or decision.startswith("AUTO-APPROVED")


def _run_beta_council_and_handoff(proposal_id: str) -> None:
    """Run dev_beta_council on the proposal, then write the beta handoff.

    Executes inside a BackgroundTask after a successful proposal→beta_testing
    transition. Never raises.
    """
    try:
        proposal_text = _read_proposal_text(proposal_id) or ""
        user_input = (
            f"Review proposal {proposal_id} as the Beta Council. Produce a JSON "
            f"engineering plan per your role spec.\n\n---\n{proposal_text}\n---\n"
        )
        # The Beta Council is a single dedicated role (dev_beta_council).
        # We run a one-shot Technical Meeting so the orchestration plumbing
        # (memory, brand-guard, scribe) still kicks in.
        report = orchestrator.execute_technical_meeting(user_input=user_input)
        report_text = report.read_text(encoding="utf-8") if isinstance(report, Path) else (report or "")

        from src.dev_route import DevRouteManager
        result = DevRouteManager().generate_beta_handoff(proposal_id, report_text)
        if "error" in result:
            print(f"[BETA] handoff generation FAILED for {proposal_id}: {result['error']}")
        else:
            print(f"[BETA] handoff written: {result.get('filename')}")
    except Exception as exc:  # noqa: BLE001
        import traceback
        print(f"[BETA][ERROR] {proposal_id}: {exc!r}\n{traceback.format_exc(limit=4)}")


@app.post("/api/workflow/transition")
async def transition_card(req: TransitionRequestPayload, background_tasks: BackgroundTasks):
    """Move a card to a target column / substatus.

    Post-commit hooks fire as FastAPI BackgroundTasks (kept off the request
    path so the dashboard returns immediately):

      * ``proposal``     → severity-dispatched council records APPROVED /
                           REJECTED / AUTO-APPROVED in ``approval_log``.
      * ``beta_testing`` → ``dev_beta_council`` produces a handoff doc.

    A drag into ``beta_testing`` is REJECTED with 422 unless the latest
    ``approval_log`` row for this proposal is APPROVED or AUTO-APPROVED.

    Successful moves trigger a vault-mirror render so the Obsidian view
    stays current. Mirror failures do NOT roll back the SQLite write —
    the state store is the single source of truth.
    """
    # ---- Approval gate: proposal → beta_testing requires council APPROVED.
    if req.target_column == "beta testing":
        if not _proposal_is_approved(req.proposal_id):
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Cannot move {req.proposal_id} to Beta Testing: the "
                    f"proposal-stage council has not APPROVED this proposal "
                    f"(check dev/decisions/ or wait for the dispatcher to finish)."
                ),
            )

    # ---- Substatus seeding (planning on entry to beta/alpha).
    effective_substatus = req.target_substatus
    if effective_substatus is None:
        effective_substatus = _DEFAULT_SUBSTATUS_ON_ENTRY.get(req.target_column)

    try:
        card = await kanban_store.move_card(
            proposal_id=req.proposal_id,
            target_column=req.target_column,
            target_substatus=effective_substatus,
            approver=req.approver,
            reason=req.reason,
            gate_passed=req.gate_passed,
            gate_details=req.gate_details,
            archive_hash=req.archive_hash,
        )
    except CardNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except InvalidColumn as exc:
        raise HTTPException(status_code=422, detail=f"Invalid target_column: {exc}")
    except ValueError as exc:
        # Catches the gate_passed-out-of-range guard in kanban_store
        raise HTTPException(status_code=422, detail=str(exc))
    except KanbanStoreError as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    # ---- Schedule post-commit hooks (fire-and-forget; survive HTTP 200).
    if req.target_column == "proposal":
        background_tasks.add_task(
            _dispatch_proposal_council, card.proposal_id, card.severity
        )
    elif req.target_column == "beta testing":
        background_tasks.add_task(_run_beta_council_and_handoff, card.proposal_id)

    return {
        "status": "success",
        "card": card.to_dict(),
    }


@app.post("/api/workflow/rollback/{proposal_id}")
async def rollback_transition(proposal_id: str, approver: str = "dashboard"):
    """Revert the most recent transition by re-applying the prior column.

    Reads ``transitions`` history; takes the **second-most-recent** row's
    ``to_column`` as the previous state and moves the card back there.
    The rollback itself is logged as a new transition row (we never
    delete history — append-only).

    Returns 404 if the card doesn't exist or has only one transition row
    (i.e. nothing to roll back to).
    """
    history = await kanban_store.history(proposal_id, limit=2)
    if not history:
        raise HTTPException(
            status_code=404,
            detail=f"No card or history found for {proposal_id!r}",
        )
    if len(history) < 2:
        raise HTTPException(
            status_code=409,
            detail=f"Card {proposal_id!r} has only its initial row; nothing to roll back",
        )

    # history is chronological; the second-to-last row is the previous state.
    previous = history[-2]
    prior_column = previous.to_column
    prior_substatus = previous.to_substatus

    try:
        card = await kanban_store.move_card(
            proposal_id=proposal_id,
            target_column=prior_column,
            target_substatus=prior_substatus,
            approver=approver,
            reason=f"rollback to transition id={previous.id}",
            gate_passed=0,
        )
    except CardNotFound as exc:
        # Shouldn't happen given the history check above, but be defensive.
        raise HTTPException(status_code=404, detail=str(exc))
    except KanbanStoreError as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return {
        "status": "success",
        "rolled_back_to": prior_column,
        "card": card.to_dict(),
    }


@app.get("/api/workflow/state/{proposal_id}")
async def get_workflow_state(proposal_id: str, history_limit: Optional[int] = 10):
    """Get the full state for a proposal, including recent history."""
    try:
        card = await kanban_store.get_card(proposal_id)
        if not card:
            raise HTTPException(status_code=404, detail=f"Card with proposal_id='{proposal_id}' not found")

        history = await kanban_store.history(proposal_id, limit=history_limit)
        return {
            "card": card.to_dict(),
            "history": [t.to_dict() for t in history],
            "history_count": len(history),
        }
    except KanbanStoreError as e:
        raise HTTPException(status_code=500, detail=str(e))


class UpdateCardRequest(BaseModel):
    title: Optional[str] = None
    substatus: Optional[str] = None
    severity: Optional[str] = None
    origin: Optional[str] = None


@app.put("/api/kanban/cards/{proposal_id}")
async def update_kanban_card(proposal_id: str, request: UpdateCardRequest):
    """Update fields on an existing Kanban card."""
    updates = request.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No update fields provided")

    try:
        updated_card = await kanban_store.update_card(proposal_id, updates)
        return {"status": "success", "card": updated_card.to_dict()}
    except CardNotFound:
        raise HTTPException(status_code=404, detail=f"Card with proposal_id='{proposal_id}' not found")
    except (KanbanStoreError, ValueError) as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/kanban/cards/{proposal_id}")
async def get_kanban_card(proposal_id: str):
    """Get a specific Kanban card."""
    try:
        card = await kanban_store.get_card(proposal_id)
        if not card:
            raise HTTPException(status_code=404, detail=f"Card with proposal_id='{proposal_id}' not found")
        return {"card": card.to_dict()}
    except KanbanStoreError as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/kanban/cards/{proposal_id}/history")
async def get_kanban_card_history(proposal_id: str, limit: Optional[int] = 10):
    """Get the history of a specific card."""
    try:
        history = await kanban_store.history(proposal_id, limit=limit)
        return {"history": [t.to_dict() for t in history]}
    except KanbanStoreError as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/kanban/cards/{proposal_id}")
async def delete_kanban_card(proposal_id: str):
    """Delete a card and its history from the Kanban store."""
    try:
        deleted = await kanban_store.delete_card(proposal_id)
        if not deleted:
            raise HTTPException(status_code=404, detail=f"Card with proposal_id='{proposal_id}' not found")
        return {
            "status": "success",
            "message": "Card deleted successfully",
            "proposal_id": proposal_id,
        }
    except KanbanStoreError as e:
        raise HTTPException(status_code=500, detail=str(e))


# Mount the static directory for the dashboard AFTER all other API routes
app.mount("/", StaticFiles(directory=DASHBOARD_DIR, html=True), name="static")


if __name__ == "__main__":
    # Launched via `python -m src.api` from start_services.bat. Port 5000
    # matches the dashboard's API_BASE convention.
    uvicorn.run(app, host="0.0.0.0", port=5000)
