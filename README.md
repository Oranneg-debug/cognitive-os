# 🧠 Cognitive OS — v1.1.1

> An offline-first, multi-agent AI orchestrator that transforms your local hardware into an automated **Sequential Boardroom**, a **visual Kanban development pipeline**, and a **browser-based Control Panel** — all powered by LM Studio.

It accepts prompts from your phone (Telegram), your notes (Obsidian), or a browser (Control Panel). It automatically determines task complexity, dynamically loads/unloads specific local LLMs into VRAM to act as a council of experts, and synthesizes a final answer directly into your Obsidian vault.

---

## ✨ What's New in v1.1.1
| Feature | Description |
|---|---|
| 🎛️ **Web Control Panel** | Browser-based GUI to edit all roles/models live — no JSON editing, no restart |
| 📋 **Kanban Automation** | Drag a card in Obsidian → LLM auto-triggers the next lifecycle phase |
| 🔌 **Kanban Status Plugin** | New Obsidian plugin syncs card status to YAML frontmatter in real-time |
| 🔧 **Robust Phase Handoffs** | Regex-based transitions that survive any LLM output formatting |
| 📦 **Version Manager** | Automated SemVer bumping across all project files |
| 🔄 **Proposal Sync Bridge** | Backend ↔ Vault sync with health monitoring and conflict detection |

---

## 🚀 Features

- **Zero-VRAM Sentry Router** — Instantly classifies prompt complexity using Python heuristics, no model loaded
- **JIT Model Loading** — Auto-ejects active models and hot-swaps specialized models into VRAM one by one
- **The Boardroom** — 6-model sequential pipeline: Strategist → Specialist → Critic → Creative → Logical → Chairman
- **Kanban Lifecycle** — Drag cards in Obsidian Kanban to progress proposals through 5 automated LLM phases
- **Web Control Panel** — Live editing of all role configs, system prompts, and model parameters in the browser
- **Obsidian Auto-Writer** — Final documents formatted with YAML metadata, injected into your vault
- **Telegram Mobile Interface** — Whitelisted bot with real-time progress callbacks, voice transcription, image analysis
- **FastAPI Endpoint** — Exposes the orchestrator to local network plugins
- **9 Execution Patterns** — SIMPLE, STANDARD, BOARDROOM, TECHNICAL, DESIGN, ORACLE, NFT, DEV LIFECYCLE, ONLINE

---

## 🛠️ Setup Guide

### 1. Prerequisites
- **Python 3.10+**
- **LM Studio**: Must be running on `http://localhost:1234/v1`
  - *Critical Setting*: Enable **"Just-In-Time Model Loading"** in LM Studio Server settings
- **Hardware**: Sufficient RAM/VRAM for your largest individual model (orchestrator handles eviction — only one model loaded at a time)

### 2. Installation
```bash
git clone https://github.com/Oranneg-debug/Antigravity.git
cd Antigravity/cognitive-os
pip install -r requirements.txt
```

### 3. Configuration

#### A. Models & Roles — Centralized Config

All model settings are defined in **one source of truth**: `cognitive-os/dev/master_config.md` (YAML inside a markdown file).

```yaml
models:
  ministral-3-3b-instruct-2512:
    temperature: 0.4
    top_p: 0.9
    context_window: 131072
    gpu_layers: -1
roles:
  simple:
    model: ministral-3-3b-instruct-2512
    temperature: 0.4
    system_prompt: "You are..."
```

**To change a model setting — 3 options:**

**Option 1: Web Control Panel (Recommended)**
1. Start services (see below)
2. Open `http://localhost:5000` in your browser
3. Select any role from the sidebar → adjust sliders/inputs → click **Save Configuration**
4. Changes apply instantly — **no restart required**

**Option 2: Edit YAML directly**
1. Open `cognitive-os/dev/master_config.md`
2. Modify the desired field inside the ```yaml ... ``` block
3. Save — the orchestrator reloads automatically on mtime change (no restart needed)

**Option 3: Python API**
```python
from cognitive_os.src.orchestrator import update_role_config, get_model_config

config = get_model_config("hermes-4-70b")
update_role_config("simple", {"temperature": 0.5})
```

#### B. Environment Variables

Create a `.env` file in `cognitive-os/`:
```env
TELEGRAM_BOT_TOKEN=your_botfather_token_here
ALLOWED_TELEGRAM_USER_ID=your_telegram_user_id
SOVEREIGN_COMPASS_PATH="E:/path/to/your/obsidian/vault/Sovereign_Compass.md"
```

#### C. Obsidian Vault Path

Open `src/obsidian_writer.py` and update `self.vault_path` to point to your actual Obsidian vault directory.

---

### 4. Running the OS

**Method 1: Windows Terminal Auto-Boot (Recommended)**

```bash
start_services.bat
```

This opens a **Windows Terminal** with **4 live tabs**:

| Tab | Service | Purpose |
|---|---|---|
| 1 | **LM Studio Server** | Local inference, bound to `0.0.0.0` for network access |
| 2 | **FastAPI Server** | REST API + Web Control Panel on port 5000 |
| 3 | **Telegram Bot** | Mobile interface |
| 4 | **Kanban Watcher** ⭐ | Monitors `Dev-KanBan.md`, triggers LLM on card moves |

*Auto-Loader*: 10 seconds after booting, a background script injects the RAG Embedder (`text-embedding-bge-m3`) and Default Boot LLM (`ministral-3-3b-instruct-2512`) into VRAM.

**⚠️ Important: Do NOT open the LM Studio GUI** while the background server is running:
- The GUI will bind to port 1234, causing port conflicts
- The GUI will hijack VRAM, ejecting your auto-loaded models

To check loaded models: open a terminal and run `lms ps`.

**Method 2: Manual Terminals**

```bash
# Terminal 1 — FastAPI + Dashboard
python -m src.api

# Terminal 2 — Telegram Bot
python -m src.telegram_bot

# Terminal 3 — Kanban Watcher
python -m src.kanban_processor --watch
```

---

## 🎛️ Web Control Panel Dashboard

Open `http://localhost:5000` after starting services.

### Tabs

| Tab | What You Can Do |
|---|---|
| **Configuration** | Select any role or model from the grouped sidebar. Edit all parameters live. |
| **System Structure** | View the full component map as an interactive Mermaid diagram |
| **Request Flow** | View the request lifecycle as a sequence diagram |
| **Kanban Workflow** | View the Kanban automation state machine |

### Sidebar Groups

Roles are organized into collapsible groups:
- **Dev Lifecycle** — `dev_*` roles
- **Boardroom** — `board_*` roles  
- **Technical Meeting** — `technical_*` roles
- **Design Meeting** — `design_*` roles
- **System & Base** — `simple`, `standard`, `vision`, `nft_specialist`
- **Core Flow Control** — `moderator`, `brand_guard`, `scribe`

### Test Panel

Type any prompt and click **Run Test** to send it to the `simple` role directly — useful for verifying model configs.

---

## 📋 Kanban Board Integration

Drag cards in your Obsidian Kanban board to automatically trigger LLM lifecycle phases.

### How It Works

```
Drag card in Obsidian → Watcher detects change (1s poll) →
Wait 2s debounce → Parse board → Detect movement →
Update proposal YAML frontmatter → Trigger LLM phase → Done ✅
```

### The Flow

```
Backlog → Proposal → Beta Testing → Alpha Polish → Finalized → Deployed
```

| Move | LLM Triggered |
|---|---|
| Backlog → Proposal | DeepSeek-Coder-V2-Lite formalizes the idea |
| Proposal → Beta Testing | Qwen3.6-35B reviews + creates implementation plan |
| Beta Testing → Alpha Polish | qwen3-coder-next optimizes GUI/performance |
| Alpha Polish → Finalized | deepseek-r1-70b performs compliance audit |

### Manual Testing

```bash
# Standalone watcher (for testing)
scripts\watch-kanban.bat

# Force-reprocess all cards
python -m cognitive-os.src.kanban_processor --force

# One-time sync
python -m cognitive-os.src.kanban_processor --sync
```

See [dev/KANBAN_INTEGRATION.md](../dev/KANBAN_INTEGRATION.md) for full documentation.

---

## � Proposal Sync Bridge

The **Proposal Sync Bridge** ensures that development proposals remain in sync between the backend (`cognitive-os/dev/proposals/`) and the Obsidian vault mirror (`1. P - Seedlings/dev/proposals/`).

### Features

- **One-way Sync**: Backend → Vault (backend is source of truth)
- **Health Monitoring**: Green/Yellow/Red status indicators
- **Conflict Detection**: Identifies files with different content in backend vs vault
- **Content-Addressable Hashing**: SHA256-based change detection
- **Sync History**: Tracks all sync operations for auditing

### API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/api/sync/status` | GET | Current sync status with health indicator |
| `/api/sync/proposals` | GET | List all proposals with sync status |
| `/api/sync/missing` | GET | Proposals missing in vault |
| `/api/sync/conflicts` | GET | Files with content conflicts |
| `/api/sync/force-sync` | POST | Trigger manual sync |
| `/api/sync/history` | GET | Sync operation history |

### Usage

**Check sync status:**
```bash
curl http://localhost:5000/api/sync/status
```

**Force sync:**
```bash
curl -X POST http://localhost:5000/api/sync/force-sync
```

**Python API:**
```python
from src.proposal_sync import ProposalSyncManager

sync_manager = ProposalSyncManager()
status = sync_manager.check_sync_status()

if status.health == "red":
    result = sync_manager.sync_backend_to_vault()
    print(f"Synced {result.files_synced} files")
```

### Health Status

- 🟢 **Green**: All proposals in sync
- 🟡 **Yellow**: Some proposals missing in vault
- 🔴 **Red**: Conflicts detected or other issues

See [src/proposal_sync.py](../src/proposal_sync.py) for full API documentation.

---

## �📱 Interfaces

### Telegram

1. Message your configured bot
2. Unauthorized users are rejected; authorized users receive live updates
3. You'll see messages like `🧠 CRITIC is deliberating...` as models hot-swap
4. Final markdown is sent back and saved to Obsidian

**Commands:**
- `/start` — Show your user ID (needed for whitelist)
- `/dev <proposal>` — Create a development lifecycle proposal
- `/search [term]` — Search vault content

### Obsidian Plugin

1. Ensure FastAPI is running on port 5000
2. Build and install `obsidian-lmstudio-agent` into your vault
3. Open Settings → **LM Studio Agent** → verify API endpoint: `http://127.0.0.1:5000/process`
4. Select text → Command Palette (`Ctrl+P`) → search `Cognitive OS`:

| Command | Description |
|---|---|
| **Auto-Route Council** | Sentry Router picks the best pattern automatically |
| **Design Council** | Forces DESIGN_MEETING pattern |
| **Technical Council** | Forces TECHNICAL_MEETING pattern |
| **Boardroom** | Forces SEQUENTIAL_BOARDROOM pattern |

---

## 🧠 Documentation

| Document | Contents |
|---|---|
| [docs/SYSTEM_ARCHITECTURE.md](../docs/SYSTEM_ARCHITECTURE.md) | Full system diagrams — components, flows, Kanban, Dashboard |
| [docs/MODEL_ORCHESTRATION.md](../docs/MODEL_ORCHESTRATION.md) | Model tiers, VRAM strategy, role system, lifecycle approval |
| [docs/CHANGELOG.md](../docs/CHANGELOG.md) | Version history — what changed in each release |
| [docs/PROPOSAL_SYNC_BRIDGE.md](../docs/PROPOSAL_SYNC_BRIDGE.md) | Backend ↔ Vault sync with health monitoring and conflict detection |
| [dev/KANBAN_INTEGRATION.md](../dev/KANBAN_INTEGRATION.md) | Kanban automation deep-dive |
| [QUICK_START_KANBAN.md](../QUICK_START_KANBAN.md) | Quick onboarding for Kanban workflow |

---

## 📊 Model Inventory (Quick Reference)

| Layer | Model | Temp | Purpose |
|---|---|---|---|
| Reflex | `ministral-3-3b-instruct-2512` | 0.4 | Fast responses, moderation, scribing |
| Vision | `qwen3-vl-4b-thinking` | 0.2 | Image analysis |
| Specialist | `qwen3.6-27b-heretic-…` | 0.2 | Technical tasks, code generation |
| Creative | `hermes-4.3-36b` | 1.1 | Brainstorming, creative expansion |
| God-Tier | `hermes-4-70b` | 0.4 | Final synthesis, chairman |
| Critic | `deepseek-r1-distill-qwen-32b` | 0.1 | Rigorous critique, validation |
| Logical | `gemma-4-31b-it` | 0.1 | Formal reasoning, structure |
| Overseer | `qwen3.5-35b-a3b-…` | 0.4 | Technical oversight |
| Brand | `gemma-4-e4b-uncensored` | 0.1 | Sovereign Compass enforcement |

See [docs/MODEL_ORCHESTRATION.md](../docs/MODEL_ORCHESTRATION.md) for the complete table with all parameters.

---

## 🔧 Pattern Types

| Pattern | Description |
|---|---|
| SIMPLE | Single fast model pass (Reflex Layer) |
| STANDARD | Single standard model + preset |
| SEQUENTIAL_BOARDROOM | 6-agent strategic meeting + Chairman synthesis |
| ONLINE_BOARDROOM | Same as above, routed to cloud/frontier models |
| DESIGN_MEETING | Design team: Junior → Creative → Critic → Senior |
| TECHNICAL_MEETING | Tech team: Specialist → Creative → Critic → Overseer |
| ORACLE_COUNCIL | Strategist → Critic → Logical → Chairman |
| NFT_CREATION | NFT metadata generation pipeline |
| DEVELOPMENT_LIFECYCLE | 4-phase dev route (Proposal → Beta → Alpha → Release) |

See [docs/SYSTEM_ARCHITECTURE.md](../docs/SYSTEM_ARCHITECTURE.md) for flow diagrams of each pattern.

---

*Cognitive OS v1.1.1 — Antigravity Development Team*
