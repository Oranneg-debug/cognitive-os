import asyncio
import json
import uvicorn
import os
import re
import yaml
from typing import Optional
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
    gpu_offload_ratio: Optional[float] = None
    gpu: Optional[str] = None  # e.g. "max", "auto"


class LoadRequest(BaseModel):
    model_key: str
    identifier: Optional[str] = None
    config: Optional[LoadConfigIn] = None
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


@app.post("/api/load")
async def load_model(req: LoadRequest):
    """Load (or reload) a model under the loader. Honours full config schema."""
    loader = _shared_loader()
    cfg = (req.config.model_dump(exclude_none=True) if req.config else {})

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

    return {
        "status": "ok",
        "action": result.action,
        "identifier": result.identifier,
        "model_key": result.model_key,
        "duration_s": result.duration_seconds,
        "config_applied": result.config_applied,
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
