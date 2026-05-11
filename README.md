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

**Method 1: Windows Startup (Recommended)**
Double-click `start_services.bat` to launch both the API and Telegram listener simultaneously. 
*(To make this run invisibly on boot, place `StartCognitiveOS.vbs` in your Windows `shell:startup` folder).*

**Method 2: Manual Terminal**
Terminal 1 (Obsidian API):
```bash
python src/api.py
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
1. Install the `obsidian-lmstudio-agent` plugin.
2. Highlight text in any note.
3. Open the Command Palette (`Ctrl+P`) -> **"Consult Cognitive OS Council"**.
4. A background POST request is sent to `localhost:5000`. Minutes later, the master document appears in your vault.
