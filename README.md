# 🧠 Cognitive OS

Cognitive OS is an offline-first AI Orchestrator that transforms your local hardware (via LM Studio) into a fully automated **Sequential Boardroom**. 

It accepts prompts from your phone (Telegram) or your notes (Obsidian), automatically determines the task complexity, and dynamically unloads/loads specific local LLMs into VRAM to act as a council of experts before synthesizing a final answer into your vault.

## 🚀 Features

- **Zero-VRAM Sentry Router**: Instantly classifies prompt complexity using Python heuristics.
- **JIT Model Loading**: Maximizes hardware limits by automatically ejecting active models (`/api/v1/models/unload`) and hot-swapping specialized models into VRAM one by one.
- **The Boardroom**: Uses a 6-model pipeline: Strategist, Specialist, Critic, Creative, Logical, and Overseer.
- **Obsidian Auto-Writer**: Final documents are formatted with YAML metadata and injected directly into your local Markdown vault.
- **Telegram Mobile Interface**: Whitelisted bot access provides real-time progress callbacks to your phone while the local rig processes complex tasks.
- **FastAPI Endpoint**: Exposes the orchestrator to local network plugins.

---

## 🛠️ Setup Guide

### 1. Prerequisites
- **Python 3.10+**
- **LM Studio**: Must be running on your local network (e.g., `http://localhost:1234/v1`).
  - *Critical Setting*: You must enable **"Just-In-Time Model Loading"** (or "Evict model when VRAM is needed") in the LM Studio Local Server settings.
- **Hardware**: Sufficient RAM/VRAM to hold your largest individual model. (The orchestrator handles eviction, so you only need enough memory for *one* model at a time).

### 2. Installation
```bash
git clone https://github.com/Oranneg-debug/cognitive-os.git
cd cognitive-os
pip install -r requirements.txt
```

### 3. Configuration

**A. Models & Roles**
Open `src/orchestrator.py` and configure your models in the `ROLES_CONFIG` dictionary. This is where you set the system prompts, temperatures, and define your **default boot LLM** (under the `simple` and `standard` roles).

```python
ROLES_CONFIG = {
    "simple": {
        "model": "qwen3.5-9b-claude-4.6-highiq-instruct-heretic-uncensored", # Default Boot LLM
        "system_prompt": "You are a fast, precise assistant. Be concise.",
        "temperature": 0.3,
        # ...
    },
    "strategist": {
        "model": "hermes-4-70b",
        # ...
    }
}
```
*Tip: You control the **temperature**, **system prompt**, and **top_k/top_p** for EVERY model directly in this dictionary. The Python Orchestrator dynamically injects these parameters into LM Studio per-request!*

> [!NOTE]
> **Applying Role Changes**
> Cognitive OS is built in Python, so there is **no compilation step**. If you modify your role prompts (for example, in external Markdown files), simply copy the updated prompts into the `ROLES_CONFIG` dictionary in `src/orchestrator.py` and save the file. 
> To apply the changes, close the terminal windows running your services and run `start_services.bat` again to reboot the servers with the updated configuration.

**B. Environment Variables**
Create a `.env` file in the root directory:
```env
TELEGRAM_BOT_TOKEN=your_botfather_token_here
ALLOWED_TELEGRAM_USER_ID=your_telegram_user_id
SOVEREIGN_COMPASS_PATH="E:/path/to/your/obsidian/vault/Sovereign_Compass.md"
```
*Tip: The `SOVEREIGN_COMPASS_PATH` can point anywhere on your system. We recommend pointing it directly to a markdown file inside your Obsidian vault so you can edit your system's core values seamlessly within Obsidian!*

**C. Obsidian Vault Path**
Open `src/obsidian_writer.py` and update the `self.vault_path` to point to your actual Obsidian vault directory.

### 4. Running the OS

**Method 1: Windows Terminal Auto-Boot (Recommended)**
Double-click `start_services.bat`. This will instantly launch a **Windows Terminal (`wt`)** window with 3 live tabs so you can monitor the stack:
1. **LM Studio Server**: Runs headlessly and binds to `0.0.0.0` for local network access.
2. **FastAPI Server**: Handles routing.
3. **Telegram Bot**: Handles mobile interfaces.

*Auto-Loader*: Exactly 10 seconds after booting, a background script will automatically inject your standard RAG Embedder (`text-embedding-bge-m3`) and your Default Boot LLM (`ministral-3-3b-instruct-2512`) into VRAM so the system is instantly ready to answer simple requests.

*(To make the stack run automatically every time you boot your PC, we use a hidden VBS wrapper. Place `StartCognitiveOS.vbs` in your Windows Startup folder: `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup`).*

⚠️ **Important Warning: LM Studio GUI**
**Do NOT** open the LM Studio desktop application while the Cognitive OS background server is running.
1. **Port Conflicts**: The GUI will attempt to bind to port 1234, colliding with your headless server.
2. **VRAM Hijacking**: The GUI forces its own internal presets, which will instantly eject your Auto-Loaded models (Embedder & Default LLM) out of your VRAM.

*If you need to monitor VRAM or see what models are actively loaded, do not use the GUI. Instead, open a normal command prompt and type `lms ps`. To view live logs, simply check the LM Studio Server tab in your Windows Terminal.*

**Method 2: Manual Terminal**
Terminal 1 (Obsidian API):
```bash
python -m src.api
```
Terminal 2 (Telegram Bot):
```bash
python -m src.telegram_bot
```

---

## 📱 Interfaces

### Using from Telegram
1. Message your configured bot.
2. If unauthorized, it will reject you. If authorized, it begins the analysis.
3. You will receive live updates (e.g., `🧠 CRITIC is deliberating...`) as LM Studio hot-swaps the models on your PC.
4. The final markdown is sent back to the chat and saved to Obsidian.

### Using from Obsidian
1. **Ensure the API is Running**: You must have the FastAPI server running (`python -m src.api` or by double-clicking `start_services.bat`). By default, it runs on port 5000.
2. **Install the Plugin**: Build and install the local `obsidian-lmstudio-agent` plugin into your Obsidian vault.
3. **Configure the Plugin**: Open Obsidian Settings -> **LM Studio Agent** -> Expand the **🧠 Cognitive OS** section. Ensure the API endpoint matches your FastAPI server (default: `http://127.0.0.1:5000/process`).
4. **Select Text**: Highlight text in any note.
5. **Route to Council**: Open the Command Palette (`Ctrl+P`) and search for `Cognitive OS`. You will see 4 options:
   - `Cognitive OS: Auto-Route Council` (Relies on the Python heuristic router)
   - `Cognitive OS: Design Council` (Forces the Creative Council via `/design`)
   - `Cognitive OS: Technical Council` (Forces the Technical Council via `/technical`)
   - `Cognitive OS: Boardroom` (Forces the full Sequential Boardroom via `/boardroom`)
6. A background POST request is sent to your FastAPI server. Minutes later, the synthesized master document appears in your vault's memory folder.
