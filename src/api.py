import asyncio
import json
import uvicorn
import os
import re
import yaml
from typing import Optional, Union
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from src.orchestrator import Orchestrator
from src.obsidian_writer import ObsidianWriter

from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Cognitive OS API")

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
        "src": ["api.py", "orchestrator.py", "sentry_router.py", "kanban_processor.py", "llm_client.py"],
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
    """Analyzes kanban_processor to map the automated workflow."""
    diagram = [
        "graph TD",
        "    A[Card moved: Backlog → Proposal] --> B{Kanban Processor};",
        "    B --> C[Call dev_proposal_refiner];",
        "    C --> D[Rewrite Proposal MD];",
        "    E[Card moved: Proposal → Beta Testing] --> F{Kanban Processor};",
        "    F --> G[Call Orchestrator: continue_development_lifecycle];",
        "    G --> H(Execute dev_beta_council);",
        "    I[Card moved: Beta → Alpha] --> J{Kanban Processor};",
        "    J --> K[Call Orchestrator];",
        "    K --> L[Flush Embedder];",
        "    L --> M(Execute dev_alpha_polish);",
        "    N[Card moved: Alpha → Finalized] --> O{Kanban Processor};",
        "    O --> P[Call Orchestrator];",
        "    P --> Q[Flush Embedder];",
        "    Q --> R(Execute dev_final_audit);",
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
    """Snapshot of currently loaded + downloaded models from the loader."""
    loader = _shared_loader()

    def _snapshot():
        loaded = []
        for inst in loader.list_loaded():
            entry = {
                "identifier": inst.identifier,
                "model_key": inst.model_key,
            }
            # Best-effort introspection of context_length from SDK handle info
            try:
                eff = loader.get_effective_config(inst.identifier)
                if isinstance(eff, dict):
                    entry["context_length"] = eff.get("contextLength") or eff.get("context_length")
                    entry["path"] = eff.get("path")
            except Exception:
                pass
            loaded.append(entry)
        downloaded = sorted(d.model_key for d in loader.list_downloaded())
        return {"loaded": loaded, "downloaded": downloaded}

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


@app.post("/api/catalog/refresh")
async def refresh_catalog():
    """Force the loader to re-scan the LM Studio catalog (after new download)."""
    loader = _shared_loader()

    def _refresh():
        cache = loader.refresh_catalog()  # returns dict[model_key, raw]
        return sorted(cache.keys())

    keys = await asyncio.to_thread(_refresh)
    return {"count": len(keys), "model_keys": keys}


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


# Initialize Core Services Globally
orchestrator = Orchestrator()
obsidian = ObsidianWriter()

class PromptRequest(BaseModel):
    prompt: str
    image_base64: Optional[str] = None
    compass_weight: Optional[str] = None
    model_presets: Optional[list] = None
    document_base64: Optional[str] = None
    is_pdf: Optional[bool] = None
    source_file_path: Optional[str] = None

@app.post("/process")
def process_prompt(request: PromptRequest):
    """
    Receives a prompt from Obsidian or other interfaces,
    runs the Cognitive OS, and saves the result.
    """
    print(f"\n🌐 API Request Received: {request.prompt[:50]}...")
    
    try:
        # 1. Run Council
        result = orchestrator.process_request(
            request.prompt, 
            image_base64=request.image_base64,
            compass_weight=request.compass_weight,
            model_presets=request.model_presets,
            document_base64=request.document_base64,
            is_pdf=request.is_pdf,
            source_file_path=request.source_file_path
        )
        
        # 2. Save to mock Obsidian vault
        pattern = orchestrator.sentry.classify_request(request.prompt)["pattern"]
        task_id = orchestrator.memory.generate_task_id(request.prompt)

        if pattern == "DEVELOPMENT_LIFECYCLE":
            file_path = None
            report_name = "dev_proposal"
            task_data = {}
            absolute_file_path = None
        else:
            keywords = "_".join(re.findall(r'\w+', request.prompt)[:5])
            file_path = obsidian.write_note(
                title=f"OLM_R_{keywords}",
                content=result,
                pattern_used=pattern,
                task_id=task_id,
                source_file_path=request.source_file_path
            )
            absolute_file_path = file_path # Renamed for clarity, assuming file_path from write_note is absolute
            report_name = os.path.basename(absolute_file_path).replace('.md', '') if absolute_file_path else f"OLM_R_{keywords}"
            task_data = orchestrator.memory.get_task_data(task_id)
            obsidian.save_memory_log(task_id, task_data, report_name)

        # --- IMPORTANT FIX: Calculate vault-relative path correctly ---
        # Assume the Obsidian vault root is 'E:/Oranneg/CloudStation/Documents/Obsidian/Grand Nexus/'
        # This needs to be configured accurately to your actual Obsidian vault root.
        OBSIDIAN_VAULT_ROOT = "E:/Oranneg/CloudStation/Documents/Obsidian/Grand Nexus/"
        
        relative_path_for_obsidian_plugin = None
        if absolute_file_path:
            try:
                # Calculate path relative to the defined Obsidian vault root
                relative_path_for_obsidian_plugin = os.path.relpath(absolute_file_path, OBSIDIAN_VAULT_ROOT).replace("\\", "/")
            except ValueError:
                print(f"⚠️ Could not calculate relative path for {absolute_file_path}. Sending absolute path.")
                relative_path_for_obsidian_plugin = absolute_file_path
            
        # The old way that was causing issues:
        # relative_path = file_path.split("Grand Nexus/")[-1].replace("\\", "/") if file_path and "Grand Nexus" in file_path else file_path

        return {
            "status": "success",
            "pattern": pattern,
            "task_id": task_id,
            "saved_path": absolute_file_path, # Keep absolute path for logging/debugging
            "relative_path": relative_path_for_obsidian_plugin, # This is what the plugin should use
            "response": result,
            "opinions": task_data.get("models_participated", []),
            "oversight": task_data.get("oversight_analysis", {}).get("raw_analysis", "")
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

# Mount the static directory for the dashboard AFTER all other API routes
app.mount("/", StaticFiles(directory=DASHBOARD_DIR, html=True), name="static")

def main():
    print("🌐 Starting FastAPI Server on port 5000...")
    uvicorn.run("src.api:app", host="0.0.0.0", port=5000, reload=True)

if __name__ == "__main__":
    uvicorn.run("src.api:app", host="0.0.0.0", port=5000)
