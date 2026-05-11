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
Open `src/orchestrator.py` and map your downloaded LM Studio models to their specific boardroom roles in the `MODEL_ROLES` dictionary.
```python
MODEL_ROLES = {
    "strategist": "your-model-identifier-here",
    "specialist": "your-model-identifier-here",
    # ...
}
```
*Tip: You can adjust the `temperature` and `max_tokens` for each role in the `MODEL_CONFIG` dictionary right below it.*

**B. Environment Variables**
Create a `.env` file in the root directory:
```env
TELEGRAM_BOT_TOKEN=your_botfather_token_here
ALLOWED_TELEGRAM_USER_ID=your_telegram_user_id
```

**C. Obsidian Vault Path**
Open `src/obsidian_writer.py` and update the `self.vault_path` to point to your actual Obsidian vault directory.

### 4. Running the OS

**Method 1: Windows Terminal & Auto-Start (Recommended)**
Double-click `start_services.bat`. This utilizes **Windows Terminal** to cleanly launch the entire stack in a single window with 3 separate tabs:
1. LM Studio Local Server
2. Cognitive OS FastAPI Server
3. Telegram Bot Listener

*(To make the stack run automatically every time you boot your PC, simply create a shortcut to `start_services.bat` and place it in your Windows Startup folder: `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup`).*

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
