import asyncio
import json
import sqlite3
import sys
import threading
import uvicorn
import os
import re
import yaml
import psutil
import subprocess
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional, Union, Dict, Any
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Governance Foundation imports (A1, ARCH-2007E0A1)
from src.output_router import OutputRouter
from src.filesystem_backend_writer import FilesystemBackendWriter
from src.routing_rules_schema import load_routing_rules
from src.orchestrator import Orchestrator
from src.obsidian_writer import ObsidianWriter
from src.paths import VAULT_ROOT, DEV_DIR, PROPOSALS_DIR, VAULT_PROPOSALS_DIR, HANDOFFS_DIR
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


async def _ingest_untracked_proposals() -> None:
    """Find .md files in dev/proposals/ that aren't in SQLite and add them to backlog."""
    from src.paths import PROPOSALS_DIR
    from src.kanban_store import CardNotFound
    import re
    
    if not PROPOSALS_DIR.exists():
        return
        
    for p in PROPOSALS_DIR.glob("*.md"):
        content = p.read_text(encoding="utf-8", errors="replace")
        
        # Match pattern like DEV-20260525-123456-XXXXXXXX
        match = re.search(r'(DEV|ARCH|NLST)-\d{8}-\d{6}-[A-Z0-9]+', content)
        if not match:
            continue
            
        proposal_id = match.group(0)
        prefix = match.group(1)
        
        try:
            await kanban_store.get_card(proposal_id)
            continue  # Already in DB
        except CardNotFound:
            pass  # Needs insertion
            
        # Extract metadata
        title = ""
        yaml_title_match = re.search(r'title:\s*["\']?([^"\'\n]+)["\']?', content)
        if yaml_title_match:
            raw = yaml_title_match.group(1).strip()
            raw = re.sub(r'^[A-Z]+_R_', '', raw)
            raw = re.sub(r'[_\-]+', ' ', raw).strip()
            title = raw[:80]
        else:
            # Fallback to first line
            for line in content.splitlines():
                line = line.strip()
                if line and not line.startswith('---') and not line.startswith('#') and not line.startswith('```'):
                    title = line[:80]
                    break
                    
        severity = None
        sev_match = re.search(r'^\s*severity:\s*["\']?(\w+)["\']?\s*$', content, re.MULTILINE)
        if sev_match:
            sev = sev_match.group(1).strip().lower()
            if sev in ('high', 'medium', 'low'):
                severity = sev
                
        origin_match = re.search(r'^\s*origin:\s*["\']?([^"\'\n]+)["\']?\s*$', content, re.MULTILINE)
        origin = origin_match.group(1).strip() if origin_match else "unknown"
        
        print(f"[STARTUP] Ingesting untracked proposal into kanban store: {proposal_id}")
        try:
            await kanban_store.add_card(
                proposal_id=proposal_id,
                prefix=prefix,
                column_name="backlog",
                title=title or None,
                substatus=None,
                severity=severity,
                origin=origin,
                approver="system",
                reason="Auto-ingested on startup"
            )
        except Exception as exc:
            print(f"[STARTUP] Failed to ingest {proposal_id}: {exc!r}")


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
    print("[STARTUP] Ingesting untracked proposals...")
    await _ingest_untracked_proposals()
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

@app.get("/api/system/roles")
async def get_system_roles():
    """Return all roles from master_config.md as JSON."""
    try:
        config_path = Path(__file__).resolve().parent.parent / "dev" / "master_config.md"
        content = config_path.read_text(encoding="utf-8")
        match = re.search(r'```yaml\n(.*?)\n```', content, re.DOTALL)
        if not match:
            raise HTTPException(status_code=500, detail="Could not find YAML block in master_config.md")
        
        config = yaml.safe_load(match.group(1))
        roles = config.get("roles", {})
        
        # Filter to just the display-relevant fields
        result = {}
        for name, cfg in roles.items():
            result[name] = {
                "model": cfg.get("model"),
                "temperature": cfg.get("temperature"),
                "context_window": cfg.get("context_window"),
                "compass_weight": cfg.get("compass_weight"),
            }
        
        return {"status": "success", "roles": result}
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="master_config.md not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error parsing roles: {e}")

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
    if diagram_type == "architecture":
        return generate_architecture_diagram()
    elif diagram_type == "structure":
        return generate_structure_diagram()
    elif diagram_type == "flow":
        return generate_flow_diagram()
    elif diagram_type == "kanban":
        return generate_kanban_diagram()
    else:
        raise HTTPException(status_code=404, detail="Diagram type not found")

def generate_architecture_diagram():
    """Generates the high-level system architecture map."""
    diagram = """flowchart TB
    classDef ui fill:#1a1a2e,stroke:#e94560,color:#fff
    classDef api fill:#0f3460,stroke:#16213e,color:#a8dadc
    classDef compute fill:#fff3e0,stroke:#ef6c00,color:#222
    classDef data fill:#e1f5fe,stroke:#0288d1,color:#222

    subgraph "Input Adapters"
        DASH[Dashboard UI]:::ui
        TG[Telegram Bot]:::ui
        OBS[Obsidian Plugin]:::ui
    end

    subgraph "API & Classification (HTTP Boundary)"
        API[FastAPI Server <br/>api.py]:::api
        SENTRY[Sentry Router <br/>sentry_router.py]:::api
        API -->|Classifies Request| SENTRY
    end

    subgraph "Orchestration Layer"
        ORCH[Orchestrator <br/>orchestrator.py]:::api
        WF[Workflow Engine <br/>workflow_engine.py]:::api
    end

    subgraph "LLM Lifecycle & Inference"
        LML[LM Studio Loader <br/>lmstudio_loader.py]:::compute
        LLMC[LLM Client <br/>llm_client.py]:::compute
        LMS((LM Studio <br/>localhost:1234)):::compute
        GEMINI((Google Gemini <br/>Fallback API)):::compute
    end

    subgraph "Persistence & Memory"
        KANBAN[(Kanban SQLite <br/>kanban_store.py)]:::data
        OBS_W[Obsidian Writer <br/>obsidian_writer.py]:::data
        VAULT[(Obsidian Vault)]:::data
    end

    DASH & TG & OBS -->|POST /process, /api/*| API
    
    SENTRY -.->|Routing Pattern| ORCH
    API --> ORCH
    API --> WF

    WF -->|State Transitions| KANBAN
    ORCH -->|Durable Records| OBS_W
    OBS_W -->|Markdown Sync| VAULT

    ORCH -->|Load/Unload| LML
    LML -->|Configure| LMS
    ORCH -->|Execute| LLMC
    LLMC -->|Inference| LMS
    LLMC -.->|Fallback| GEMINI"""
    
    desc = """
    <strong>FastAPI Backend</strong>: The central nervous system handling HTTP routing and async tasks.<br/>
    <strong>Sentry Router</strong>: The stateless classification engine picking multi-agent patterns.<br/>
    <strong>Orchestrator</strong>: The core workflow manager driving agent councils and LM Studio loaders.<br/>
    <strong>Kanban Store</strong>: The single-source-of-truth SQLite DB enforcing state transitions and transition gates.
    """
    return {"diagram": diagram, "description": desc}

def generate_structure_diagram():
    """Generates a Mermaid diagram of the cognitive-os file structure."""
    diagram = """graph TD
    subgraph CognitiveOS
        subgraph src
            src_api_py[api.py<br/>FastAPI / Hooks]
            src_orchestrator_py[orchestrator.py<br/>Multi-Agent Engine]
            src_sentry_router_py[sentry_router.py<br/>Classifier]
            src_kanban_store_py[kanban_store.py<br/>SQLite Data Plane]
            src_dev_route_py[dev_route.py<br/>Proposal Ingestion]
        end
        subgraph dashboard
            dash_index[index.html]
            dash_script[script.js<br/>Vanilla JS UI]
            dash_styles[styles.css]
        end
        subgraph dev
            dev_kanban[(kanban_state.sqlite)]
            dev_handoffs[handoffs/]
            dev_proposals[proposals/]
        end
    end"""
    desc = "The modular file structure isolates the HTTP ingress (api.py), orchestration business logic, data persistence (kanban_store.py), and frontend dashboard."
    return {"diagram": diagram, "description": desc}

def generate_flow_diagram():
    """Analyzes sentry_router and orchestrator to map request flows."""
    diagram = """graph TD
    A[User Chat Input] --> B{SentryRouter.classify_request};
    B --> |/technical, code...| C(TECHNICAL_MEETING);
    B --> |/design, art...| D(DESIGN_MEETING);
    B --> |/boardroom, strategy...| E(SEQUENTIAL_BOARDROOM);
    B --> |/oracle| F(ORACLE_COUNCIL);
    B --> |/dev| G(DEVELOPMENT_LIFECYCLE);
    B --> |low complexity| H(SIMPLE);
    B --> |medium complexity| I(STANDARD);
    
    C --> C1(Orchestrator: execute_technical_meeting);
    D --> D1(Orchestrator: execute_design_meeting);
    E --> E1(Orchestrator: execute_sequential_boardroom);
    F --> F1(Orchestrator: execute_oracle_council);
    G --> G1(DevRouteManager: create_proposal + Add to Kanban);
    H --> H1(Orchestrator: execute_simple);
    I --> I1(Orchestrator: execute_standard);
    
    style C fill:#8b1212,stroke:#333,stroke-width:2px
    style D fill:#8b1212,stroke:#333,stroke-width:2px
    style E fill:#8b1212,stroke:#333,stroke-width:2px
    style F fill:#8b1212,stroke:#333,stroke-width:2px"""
    
    desc = "<strong>Request Flow:</strong> Text inputs are evaluated for complexity and domain, mapping them to specific multi-agent orchestration paths (SIMPLE vs TECHNICAL vs BOARDROOM). The '/dev' trigger uniquely bypasses direct chat outputs to drop a new Proposal into the Kanban database."
    return {"diagram": diagram, "description": desc}

def generate_kanban_diagram():
    """Map the automated workflow driven by /api/workflow/transition."""
    diagram = """graph TD
    A[Dashboard Drag & Drop] -->|POST /api/workflow/transition| B{Target Column?}
    
    B -->|proposal| C[_dispatch_proposal_council]
    B -->|beta_testing| D{Approval Gate Passed?}
    B -->|alpha_polish| E{Beta Handoff Exists?}
    B -->|finalized/deployed| F{Alpha Handoff Exists?}

    D -->|Yes| G[_run_beta_council_and_handoff]
    D -->|No| H[422 REJECTED]
    E -->|Yes| I[_run_alpha_council_and_handoff]
    E -->|No| H
    F -->|Yes| J[_finalize_proposal]
    F -->|No| H

    C --> L((Wait for _council_lock))
    G --> L
    I --> L

    L -->|Lock Acquired| K[Execute AI Council Roles]
    K -->|Release Lock| M[Update SQLite Substatus & Vault Mirror]"""
    
    desc = "<strong>Kanban Background Automation:</strong> Dashboard drags trigger FastAPI background tasks. The tasks execute hard transition gates against the filesystem, queue for the global <code>_council_lock</code> (to prevent LM Studio VRAM crashing), execute the generation, and push substatus updates (e.g. <code>execution.coding</code>) back into SQLite."
    return {"diagram": diagram, "description": desc}

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

# Governance API endpoints (A7, ARCH-20260522-161600-60FE0001)
from src.handoff_vault import HandoffVault
from src.approval_logger import ApprovalLogger

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
        import asyncio
        
        def _locked_process_request():
            with _council_lock:
                return orchestrator.process_request(
                    request.prompt, 
                    image_base64=request.image_base64,
                    compass_weight=request.compass_weight,
                    model_presets=request.model_presets,
                    document_base64=request.document_base64,
                    is_pdf=request.is_pdf,
                    source_file_path=request.source_file_path
                )
                
        result = await asyncio.to_thread(_locked_process_request)

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
        
        # Await the coroutine result since orchestrator.process_request might be async or returning an async mock in tests
        import asyncio
        if asyncio.iscoroutine(result):
            result = await result
            
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
# Routing Rules Endpoint (A6 - ARCH-2007E0A1)
# ============================================================================
@app.get("/api/routing/rules")
def get_routing_rules():
    """
    Return the routing rules YAML file content for dashboard visibility.
    
    Returns:
        YAML content of config/routing_rules.yaml
    """
    rules_path = Path(__file__).resolve().parent.parent / "config" / "routing_rules.yaml"
    return Response(
        content=rules_path.read_text(encoding="utf-8"),
        media_type="text/yaml"
    )


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
    # Keep the full verdict — the 800-char cap was truncating boardroom reasoning mid-sentence.
    # Proposal files can handle longer blocks; Obsidian renders them fine.
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


def _sync_substatus_to_proposal(proposal_id: str, substatus: str) -> None:
    """Write the new substatus into the backend proposal's YAML frontmatter.

    Called after a same-column substatus-only transition (e.g. beta testing
    planning → execution.coding). Keeps the proposal markdown in sync with
    the SQLite card so the vault note shows the current sub-stage.

    Updates only the ``substatus:`` line inside the frontmatter fence.
    If the line doesn't exist yet, it is inserted after ``status:``.
    Best-effort — never raises.
    """
    path = _proposal_path(proposal_id)
    if path is None:
        return
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
        # Find the frontmatter block (between first and second '---')
        end = content.find("\n---\n", 3)
        if end < 0:
            return
        fm = content[3:end]  # raw frontmatter text (without the --- fences)

        import re as _re
        if _re.search(r"^substatus\s*:", fm, _re.MULTILINE):
            # Replace existing substatus line
            new_fm = _re.sub(
                r"^(substatus\s*:).*$",
                rf"\g<1> {substatus}",
                fm,
                flags=_re.MULTILINE,
            )
        else:
            # Insert after status: line, or at end of frontmatter
            if _re.search(r"^status\s*:", fm, _re.MULTILINE):
                new_fm = _re.sub(
                    r"(^status\s*:.*$)",
                    rf"\1\nsubstatus: {substatus}",
                    fm,
                    flags=_re.MULTILINE,
                    count=1,
                )
            else:
                new_fm = fm + f"\nsubstatus: {substatus}"

        new_content = "---" + new_fm + "\n---\n" + content[end + 5:]
        path.write_text(new_content, encoding="utf-8")

        # Mirror to vault
        _trigger_vault_sync()
        print(f"[SUBSTATUS] {proposal_id} → substatus: {substatus}")
    except Exception as exc:  # noqa: BLE001
        print(f"[SUBSTATUS] failed to update proposal {proposal_id}: {exc!r}")


# ---------------------------------------------------------------------------
# Global council lock (2026-05-26)
# ---------------------------------------------------------------------------
# LM Studio can only serve one heavy model at a time. All BackgroundTasks
# that touch the orchestrator (severity dispatcher, beta council, alpha
# boardroom) MUST hold this lock before calling any orchestrator method.
# ``_finalize_proposal`` is a pure file-write and doesn't need it.
#
# The lock is a plain ``threading.Lock``. BackgroundTasks run in a thread
# pool, not in the event loop, so asyncio primitives don't work here.
# A ``Lock`` (not ``RLock``) is correct — no task should re-acquire from
# the same thread.
#
# A card whose council is queued (waiting for the lock) will show
# substatus ``pending_council`` while it waits; the winner's substatus
# update to ``approved`` / ``rejected`` / ``planning`` etc. only lands
# after the lock is released by the previous run. This is visible in
# the dashboard without any extra code.
_council_lock = threading.Lock()


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
    
    # Store hash of the exact content we are sending to the LLM
    import hashlib
    content_hash_before = hashlib.sha256(proposal_text.encode("utf-8")).hexdigest()

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
            print(f"[DISPATCH] {proposal_id}: waiting for council lock (severity={sev_norm})…")
            with _council_lock:
                # We just acquired the lock, which means we are no longer in the queue.
                # Upgrade the card's substatus from queued_council to pending_council so
                # the dashboard switches from "COUNCIL QUEUE" to "COUNCIL RUNNING".
                from src.kanban_store import _move_card_sync, KANBAN_DB_PATH
                
                _move_card_sync(
                    db_path=KANBAN_DB_PATH,
                    proposal_id=proposal_id, target_column="proposal",
                    target_substatus="pending_council", approver="system", reason="Lock acquired", gate_passed=1,
                    gate_details=None, archive_hash=None
                )

                print(f"[DISPATCH] {proposal_id}: council lock acquired, starting {sev_norm} council")
                from src.patterns import PATTERN_REGISTRY, PatternRequest
                from src.patterns.alpha_council import execute as alpha_council_execute
                from src.patterns.final_audit import execute as final_audit_execute
                req = PatternRequest(user_input=user_input)
                if sev_norm == "high":
                    council_name = "Sequential Boardroom"
                    report = PATTERN_REGISTRY["SEQUENTIAL_BOARDROOM"](req)
                else:  # medium — single-pass check, no sequential deliberation
                    council_name = "Quick Technical Review (single-pass)"
                    from src.council_runner import get_role_config
                    from src.llm_client import llm
                    c = get_role_config("technical_specialist")
                    report = llm.generate_response(
                        prompt=req.user_input,
                        system_prompt=c.get("system_prompt"),
                        model=c.get("model"),
                        temperature=c.get("temperature", 0.7),
                        max_tokens=c.get("max_tokens", 4096),
                        gpu_layers=c.get("gpu_layers", -1),
                        context_window=c.get("context_window", 32768),
                    )

            # `report` may be a Path (output_router-routed) or str.
            report_text = report.read_text(encoding="utf-8") if isinstance(report, Path) else (report or "")
            decision = "APPROVED" if "VERDICT: APPROVED" in report_text else (
                "REJECTED" if "VERDICT: REJECTED" in report_text else "APPROVED"
            )
            substatus = decision.lower()
            from src.approval_logger import ApprovalLogger, ApprovalRecord
            from datetime import datetime
            from src.kanban_store import _get_card_sync, KANBAN_DB_PATH
            
            # Retrieve the current card to grab its state_hash for the audit log
            card = _get_card_sync(KANBAN_DB_PATH, proposal_id)
            current_hash = card.state_hash if card else "hash_not_found"
            
            ApprovalLogger().log_decision(ApprovalRecord(
                proposal_id=proposal_id,
                decision=decision,
                approver=("sequential_boardroom" if sev_norm == "high" else "technical_meeting"),
                reason=f"council verdict on severity={sev_norm}",
                timestamp=datetime.now(),
                state_hash=current_hash
            ))

            # Write the SQLite row explicitly so _proposal_is_approved gate works.
            # (ApprovalRecord model doesn't map 1:1 to approval_log schema —
            #  pending a proper fix; this is the systemic bug causing all
            #  "council has not approved" errors on beta-testing drags.)
            import sqlite3
            try:
                conn = sqlite3.connect(str(ApprovalLogger().db_path))
                cur = conn.cursor()
                cur.execute(
                    "INSERT INTO approval_log (proposal_id, role, decision, approver, ts) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (
                        proposal_id,
                        "sequential_boardroom" if sev_norm == "high" else "technical_meeting",
                        decision,
                        "sequential_boardroom" if sev_norm == "high" else "technical_meeting",
                        datetime.now().isoformat(),
                    ),
                )
                conn.commit()
                print(f"[DISPATCH] approval_log row written for {proposal_id}")
            except Exception as exc:
                print(f"[DISPATCH] approval_log write failed for {proposal_id}: {exc!r}")
            finally:
                conn.close()

        # Stale-card guard: if the user moved the card OUT of `proposal`
        # while the council was running, our write-back becomes noise.
        # Skip the verdict-append + substatus update so the board reflects
        # the user's latest intent. The approval_log row still stands as
        # evidence the council ran, so a future re-entry into Proposal
        # (which re-fires the dispatcher) will overwrite it cleanly.
        current_text = _read_proposal_text(proposal_id) or ""
        content_hash_after = hashlib.sha256(current_text.encode("utf-8")).hexdigest()
        if content_hash_before != content_hash_after:
            print(
                f"[DISPATCH] {proposal_id}: proposal content changed during council run; "
                f"skipping verdict-append to prevent stale overwrite"
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
            from src.approval_logger import ApprovalLogger, ApprovalRecord
            from datetime import datetime
            ApprovalLogger().log_decision(ApprovalRecord(
                proposal_id=proposal_id,
                role="proposal_council",
                decision="ERROR",
                approver="severity_dispatcher",
                notes=f"{type(exc).__name__}: {exc}",
                timestamp=datetime.now()
            ))
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
                "WHERE proposal_id = ? AND role IN "
                "('proposal_council', 'technical_meeting', 'sequential_boardroom', 'technical_board', 'boardroom') "
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


def _parse_beta_handoff_tasks(beta_handoff_path: Path) -> tuple[bool, list[str]]:
    """Parse BETA_HANDOFF.md to check if all implementation tasks are complete.
    
    Returns:
        Tuple of (all_tasks_complete, list of incomplete task IDs)
    """
    try:
        content = beta_handoff_path.read_text(encoding="utf-8", errors="replace")
        
        # Find the implementation tasks section
        tasks_section_match = re.search(
            r'## 🔧 Implementation Tasks.*?(?=---|\Z)',
            content,
            re.DOTALL | re.IGNORECASE
        )
        if not tasks_section_match:
            print(f"[GATE] BETA_HANDOFF.md missing '## Implementation Tasks' section")
            return False, []
        
        tasks_content = tasks_section_match.group(0)
        
        # Find all incomplete tasks (- [ ] pattern)
        incomplete_tasks = re.findall(
            r'^\s*-\s*\[\s*\]\s*\*\*\[(?:✏️|✅)\s+\w+\]\s+(.+?)\*\*',
            tasks_content,
            re.MULTILINE
        )
        
        # Find all complete tasks (- [x] pattern)
        complete_tasks = re.findall(
            r'^\s*-\s*\[x\]\s*\*\*\[(?:✏️|✅)\s+\w+\]\s+(.+?)\*\*',
            tasks_content,
            re.MULTILINE
        )
        
        all_complete = len(incomplete_tasks) == 0
        return all_complete, incomplete_tasks
        
    except Exception as exc:  # noqa: BLE001
        print(f"[GATE] Failed to parse BETA_HANDOFF.md for {beta_handoff_path.name}: {exc!r}")
        return False, []


def _run_pytests() -> tuple[bool, str]:
    """Run pytest and return (success, output).
    
    Returns:
        Tuple of (pytest_passed, output_text)
    """
    try:
        repo_root = Path(__file__).resolve().parent.parent  # cognitive-os/
        
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "-v", "--tb=short"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=300,  # 5-minute timeout for tests
        )
        
        passed = result.returncode == 0
        output = result.stdout + "\n" + result.stderr if result.stderr else result.stdout
        
        return passed, output
        
    except subprocess.TimeoutExpired:
        return False, "pytest timed out (>5 minutes)"
    except Exception as exc:  # noqa: BLE001
        return False, f"pytest execution failed: {exc!r}"


def _run_alpha_council_and_handoff(proposal_id: str) -> None:
    """Run the ALPHA_COUNCIL pattern to produce the Alpha Polish plan.

    Fires as a BackgroundTask when a card enters ``alpha polish``.
    Calls `alpha_council_execute` which runs the sequential boardroom
    and writes ``ALPHA_HANDOFF.md`` via OutputRouter.
    
    BEFORE executing, validates:
      1. BETA_HANDOFF.md exists with all implementation tasks complete
      2. All tests pass (pytest)
    
    Never raises — the dashboard already returned 200.
    """
    beta_path = HANDOFFS_DIR / f"{proposal_id}_BETA_HANDOFF.md"
    try:
        # ---- Validation Gate: BETA_HANDOFF.md must exist with all tasks complete
        if not beta_path.exists():
            print(f"[ALPHA] {proposal_id}: BLOCKED - BETA_HANDOFF.md not found")
            def _update_db_err():
                import asyncio
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                loop.run_until_complete(kanban_store.move_card(
                    proposal_id=proposal_id, target_column="alpha polish",
                    target_substatus="blocked", approver="system", 
                    reason="BETA_HANDOFF.md missing", gate_passed=-1
                ))
            _update_db_err()
            return
        
        all_complete, incomplete = _parse_beta_handoff_tasks(beta_path)
        if not all_complete:
            print(f"[ALPHA] {proposal_id}: BLOCKED - {len(incomplete)} tasks incomplete in BETA_HANDOFF.md")
            def _update_db_err():
                import asyncio
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                task_list = ", ".join(incomplete[:3]) + ("..." if len(incomplete) > 3 else "")
                loop.run_until_complete(kanban_store.move_card(
                    proposal_id=proposal_id, target_column="alpha polish",
                    target_substatus="blocked", approver="system", 
                    reason=f"Implementation tasks incomplete: {task_list}", gate_passed=-1
                ))
            _update_db_err()
            return
        
        # ---- Validation Gate: All tests must pass
        tests_passed, test_output = _run_pytests()
        if not tests_passed:
            print(f"[ALPHA] {proposal_id}: BLOCKED - pytest failed")
            def _update_db_err():
                import asyncio
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                # Truncate output to 500 chars for UI
                err_snippet = test_output[:500].strip() if len(test_output) > 500 else test_output
                loop.run_until_complete(kanban_store.move_card(
                    proposal_id=proposal_id, target_column="alpha polish",
                    target_substatus="blocked", approver="system", 
                    reason=f"Tests failed: {err_snippet}", gate_passed=-1
                ))
            _update_db_err()
            return
        
        print(f"[ALPHA] {proposal_id}: All validation gates passed, running alpha council")
        
        # ---- Execute Alpha Council
        proposal_text = _read_proposal_text(proposal_id) or ""
        print(f"[ALPHA] {proposal_id}: waiting for council lock…")
        with _council_lock:
            print(f"[ALPHA] {proposal_id}: council lock acquired, starting alpha council")
            from src.patterns import PatternRequest
            from src.patterns.alpha_council import execute as alpha_council_execute
            user_input = (
                f"Produce an Alpha Handoff plan for proposal {proposal_id}.\n\n"
                f"---\n{proposal_text}\n---\n"
            )
            req = PatternRequest(user_input=user_input)
            report = alpha_council_execute(req)
        report_text = report.read_text(encoding="utf-8") if isinstance(report, Path) else (report or "")
        print(f"[ALPHA] boardroom complete for {proposal_id}")

        def _update_db(subst: str, rsn: str):
            import asyncio
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            loop.run_until_complete(kanban_store.move_card(
                proposal_id=proposal_id, target_column="alpha polish",
                target_substatus=subst, approver="system", reason=rsn, gate_passed=1
            ))

        from src.dev_route import DevRouteManager
        result = DevRouteManager().generate_alpha_handoff(proposal_id, report_text)
        if "error" in result:
            print(f"[ALPHA] handoff generation FAILED for {proposal_id}: {result['error']}")
            _update_db("blocked", "handoff generation failed")
            return

        print(f"[ALPHA] handoff saved: {result.get('filename', 'unknown')}")
        _trigger_vault_sync()
        _update_db("execution.coding", "alpha handoff complete")
        
    except Exception as exc:  # noqa: BLE001
        import traceback
        print(f"[ALPHA][ERROR] {proposal_id}: {exc!r}\n{traceback.format_exc(limit=4)}")
        def _update_db_err():
            import asyncio
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            loop.run_until_complete(kanban_store.move_card(
                proposal_id=proposal_id, target_column="alpha polish",
                target_substatus="blocked", approver="system", reason=f"exception: {exc}", gate_passed=-1
            ))
        try:
            _update_db_err()
        except Exception:
            pass

def _finalize_proposal(proposal_id: str, phase: str) -> None:
    """Run the FINAL_AUDIT pattern to produce the Final Audit report.

    Fires as a BackgroundTask when a card enters ``finalized`` or
    ``deployed``. Calls `final_audit_execute` which runs the audit
    and writes ``FINAL_AUDIT.md`` via OutputRouter.
    
    Verifies the audit verdict (APPROVED/REJECTED) and blocks the transition
    if REJECTED.
    
    Never raises — the dashboard already returned 200.
    """
    try:
        proposal_text = _read_proposal_text(proposal_id) or ""
        print(f"[FINALIZE] {proposal_id}: waiting for council lock…")
        with _council_lock:
            print(f"[FINALIZE] {proposal_id}: council lock acquired, starting final audit")
            from src.patterns import PatternRequest
            from src.patterns.final_audit import execute as final_audit_execute
            user_input = (
                f"Produce a Final Audit report for proposal {proposal_id}.\n\n"
                f"---\n{proposal_text}\n---\n"
            )
            req = PatternRequest(user_input=user_input)
            report = final_audit_execute(req)
        report_text = report.read_text(encoding="utf-8") if isinstance(report, Path) else (report or "")
        print(f"[FINALIZE] final audit complete for {proposal_id}")
        
        # ---- Parse verdict from final audit output
        from src.kanban_store import _update_card_sync, KANBAN_DB_PATH

        if "VERDICT: REJECTED" in report_text or '"final_verdict": "REJECTED"' in report_text:
            print(f"[FINALIZE] {proposal_id}: BLOCKED by final audit")
            _update_card_sync(KANBAN_DB_PATH, proposal_id, {"substatus": "rejected"})
            print(f"[FINALIZE] kanban updated: substatus=rejected")
            return
        
        if "VERDICT: APPROVED" in report_text or '"final_verdict": "APPROVED"' in report_text or "**APPROVED**" in report_text:
            # ---- APPROVED: persist report, update kanban, trigger sync
            final_report_path = HANDOFFS_DIR / f"{proposal_id}_FINAL_AUDIT.md"
            final_report_path.write_text(report_text, encoding="utf-8")
            print(f"[FINALIZE] report saved: {final_report_path.name}")

            _update_card_sync(KANBAN_DB_PATH, proposal_id, {"substatus": "approved"})
            print(f"[FINALIZE] kanban updated: substatus=approved")

            _trigger_vault_sync()
        else:
            # No clear verdict found — save the report but don't auto-approve
            final_report_path = HANDOFFS_DIR / f"{proposal_id}_FINAL_AUDIT.md"
            final_report_path.write_text(report_text, encoding="utf-8")
            print(f"[FINALIZE] report saved: {final_report_path.name}")
            print(f"[FINALIZE] WARNING: No clear APPROVED/REJECTED verdict found in report — substatus NOT updated")
    except Exception as exc:  # noqa: BLE001
        import traceback
        print(f"[FINALIZE][ERROR] {proposal_id}: {exc!r}\n{traceback.format_exc(limit=4)}")


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
        print(f"[BETA] {proposal_id}: waiting for council lock…")
        with _council_lock:
            print(f"[BETA] {proposal_id}: council lock acquired, starting beta council")
            from src.patterns import PATTERN_REGISTRY, PatternRequest
            req = PatternRequest(user_input=user_input)
            report = PATTERN_REGISTRY["TECHNICAL_MEETING"](req)
        report_text = report.read_text(encoding="utf-8") if isinstance(report, Path) else (report or "")

        from src.dev_route import DevRouteManager
        result = DevRouteManager().generate_beta_handoff(proposal_id, report_text)
        
        # kanban_store is heavily async. To safely call it from a sync thread
        # without event loop collisions, we define a small wrapper.
        def _update_db(subst: str, rsn: str):
            import asyncio
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            loop.run_until_complete(kanban_store.move_card(
                proposal_id=proposal_id, target_column="beta testing",
                target_substatus=subst, approver="system", reason=rsn, gate_passed=1
            ))
            
        if "error" in result:
            print(f"[BETA] handoff generation FAILED for {proposal_id}: {result['error']}")
            _update_db("blocked", "handoff generation failed")
        else:
            print(f"[BETA] handoff written: {result.get('filename')}")
            _update_db("execution.coding", "beta handoff complete")
            
    except Exception as exc:  # noqa: BLE001
        import traceback
        print(f"[BETA][ERROR] {proposal_id}: {exc!r}\n{traceback.format_exc(limit=4)}")
        
        def _update_db_err():
            import asyncio
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            loop.run_until_complete(kanban_store.move_card(
                proposal_id=proposal_id, target_column="beta testing",
                target_substatus="blocked", approver="system", reason=f"exception: {exc}", gate_passed=-1
            ))
        try:
            _update_db_err()
        except Exception:
            pass

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

    # ---- Alpha Gate: beta_testing → alpha_polish requires BETA_HANDOFF.md + ready-for-alpha substatus
    if req.target_column == "alpha polish":
        beta_path = HANDOFFS_DIR / f"{req.proposal_id}_BETA_HANDOFF.md"
        if not beta_path.exists():
            raise HTTPException(
                status_code=422,
                detail=f"Cannot move to Alpha Polish: {beta_path.name} does not exist. Finish Beta Testing first."
            )
        # Only check substatus on cross-column moves (beta → alpha), not reruns
        current_card = await kanban_store.get_card(req.proposal_id)
        is_cross_column = current_card and current_card.column_name != "alpha polish"
        if is_cross_column and current_card.substatus not in ("ready-for-alpha", "testing", "execution.ready-for-alpha", "execution.testing"):
            raise HTTPException(
                status_code=422,
                detail=f"Cannot move to Alpha Polish: card substatus is '{current_card.substatus}'. Must complete beta cycle (reach 'testing' or 'ready-for-alpha') first."
            )

    # ---- Finalized Gate: alpha_polish → finalized requires ALPHA_HANDOFF.md
    if req.target_column == "finalized":
        alpha_path = HANDOFFS_DIR / f"{req.proposal_id}_ALPHA_HANDOFF.md"
        if not alpha_path.exists():
            raise HTTPException(
                status_code=422,
                detail=f"Cannot move to Finalized: {alpha_path.name} does not exist. Finish Alpha Polish first."
            )

    # ---- Substatus seeding (planning on entry to beta/alpha).
    effective_substatus = req.target_substatus
    if effective_substatus is None:
        effective_substatus = _DEFAULT_SUBSTATUS_ON_ENTRY.get(req.target_column)

    # If this is a proposal and we are about to queue for the council lock,
    # set the substatus to "queued_council" initially. The background task will 
    # upgrade it to "pending_council" the moment it actually acquires the lock.
    if req.target_column == "proposal" and effective_substatus == "pending_council":
        effective_substatus = "queued_council"

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
    #
    # Two kinds of moves:
    #   1. Cross-column (e.g. beta testing → alpha polish) — council/finalize hooks.
    #   2. Same-column substatus change (e.g. planning → execution.coding inside
    #      beta testing) — write substatus back to proposal YAML.
    _SUBSTATUS_COLUMNS = {"beta testing", "alpha polish"}
    is_substatus_change = (
        req.target_column in _SUBSTATUS_COLUMNS
        and req.target_substatus is not None
    )

    is_rerun = (
        req.approver == "dashboard-rerun"
        and card.column_name == req.target_column
    )

    if req.target_column == "proposal":
        background_tasks.add_task(
            _dispatch_proposal_council, card.proposal_id, card.severity
        )
    elif req.target_column == "beta testing" and (not is_substatus_change or is_rerun):
        # Entry into beta testing (cross-column) — run council + handoff.
        # Also fires on explicit "↻ Rerun" button from same column.
        background_tasks.add_task(_run_beta_council_and_handoff, card.proposal_id)
    elif req.target_column == "alpha polish" and (not is_substatus_change or is_rerun):
        # Entry into alpha polish (cross-column) — run boardroom + handoff.
        # Also fires on explicit "↻ Rerun" button from same column.
        background_tasks.add_task(_run_alpha_council_and_handoff, card.proposal_id)
    elif req.target_column in ("finalized", "deployed") or (card.column_name in ("finalized", "deployed") and is_rerun):
        # Entry into finalized/deployed — run final audit + handoff.
        # Also fires on explicit "↻ Rerun" button from same column.
        background_tasks.add_task(_finalize_proposal, card.proposal_id, req.target_column)

    # Substatus change within beta/alpha — sync to proposal YAML.
    if is_substatus_change:
        background_tasks.add_task(
            _sync_substatus_to_proposal, card.proposal_id, req.target_substatus
        )

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
async def get_kanban_card_history(proposal_id: str):
    """Return the last 10 transitions for a card."""
    history = await kanban_store.history(proposal_id, limit=10)
    return {"status": "success", "history": [h.to_dict() for h in history]}


@app.get("/api/workflow/artifact/{proposal_id}")
async def get_artifact(proposal_id: str, type: str = "proposal"):
    """Fetch raw markdown text of a workflow artifact (proposal or handoff)."""
    from src.paths import PROPOSALS_DIR, HANDOFFS_DIR
    
    if type == "proposal":
        path = PROPOSALS_DIR / f"{proposal_id}_PROPOSAL.md"
    elif type == "beta_handoff":
        path = HANDOFFS_DIR / f"{proposal_id}_BETA_HANDOFF.md"
    elif type == "alpha_handoff":
        path = HANDOFFS_DIR / f"{proposal_id}_ALPHA_HANDOFF.md"
    elif type == "final_audit":
        path = HANDOFFS_DIR / f"{proposal_id}_FINAL_AUDIT.md"
    else:
        raise HTTPException(status_code=400, detail=f"Unknown artifact type {type}")
        
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Artifact {path.name} not found")
        
    return {"status": "success", "content": path.read_text(encoding="utf-8")}


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


# Governance API endpoints (A7, ARCH-20260522-161600-60FE0001)
@app.get("/api/governance/log/{proposal_id}")
async def get_governance_log(proposal_id: str):
    """Return ordered ApprovalRecord JSON for a proposal."""
    try:
        logger = ApprovalLogger()
        records = logger.get_log(proposal_id)
        if not records:
            raise HTTPException(status_code=404, detail=f"No approval log found for proposal_id='{proposal_id}'")
        
        # Convert ApprovalRecord objects to serializable dicts
        return {
            "status": "success",
            "proposal_id": proposal_id,
            "records": [
                {
                    "proposal_id": r.proposal_id,
                    "role": r.role,
                    "decision": r.decision,
                    "approver": r.approver,
                    "ts": r.ts.isoformat() if r.ts else None,
                    "prior_record_hash": r.prior_record_hash,
                    "state_hash": r.state_hash
                }
                for r in records
            ]
        }
    except VaultIntegrityError as e:
        raise HTTPException(status_code=500, detail=f"Integrity check failed: {e.reason}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/governance/migrate")
async def run_migrate():
    """Idempotent migration rerun for legacy files."""
    try:
        from src.schema_validator import migrate_legacy_proposals
        result = migrate_legacy_proposals()
        return {
            "status": "success",
            "message": f"Migrated {result['migrated']} files, skipped {result['skipped']}"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# DevLog Agent Dashboard Endpoint (ARCH-78D36EDB, Alpha Polish)
# ============================================================================

from datetime import date

@app.post("/api/devlog/draft")
async def generate_devlog_draft(date_str: Optional[str] = None):
    """Generate a DevLog draft — returns raw markdown, saves to dev/devlogs/pending/."""
    try:
        today = date_str or date.today().isoformat()
        from src.devlog_agent import DevLogAgent
        from src.models.devlog import DevLogConfig

        agent = DevLogAgent(config=DevLogConfig())
        markdown, saved_path = agent.generate_and_save(today)

        return {
            "status": "success",
            "date": today,
            "draft": markdown,
            "saved_to": str(saved_path),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DevLog draft failed: {str(e)}")


@app.post("/api/governance/migrate")
async def run_migrate():
    """Idempotent migration rerun for legacy files."""
    try:
        from src.schema_validator import migrate_legacy_proposals
        result = migrate_legacy_proposals()
        return {
            "status": "success",
            "message": f"Migrated {result['migrated']} files, skipped {result['skipped']}"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/governance/archives/{proposal_id}")
async def get_governance_archives(proposal_id: str):
    """Return artifact history for a proposal."""
    try:
        vault = HandoffVault()
        history = vault.get_history(proposal_id)
        if not history:
            raise HTTPException(status_code=404, detail=f"No archives found for proposal_id='{proposal_id}'")
        
        return {
            "status": "success",
            "proposal_id": proposal_id,
            "artifacts": [
                {
                    "proposal_id": a.proposal_id,
                    "phase": a.phase.value,
                    "timestamp": a.timestamp.isoformat() if a.timestamp else None,
                    "sha256": a.sha256,
                    "prior_hash": a.prior_hash,
                    "snapshot_path": a.snapshot_path
                }
                for a in history
            ]
        }
    except VaultIntegrityError as e:
        raise HTTPException(status_code=500, detail=f"Integrity check failed: {e.reason}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Mount the static directory for the dashboard AFTER all other API routes
app.mount("/", StaticFiles(directory=DASHBOARD_DIR, html=True), name="static")


if __name__ == "__main__":
    # Launched via `python -m src.api` from start_services.bat. Port 5000
    # matches the dashboard's API_BASE convention.
    uvicorn.run(app, host="0.0.0.0", port=5000)
