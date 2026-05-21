@echo off
:: Navigate to the project directory
cd /d "E:\Antigravity\cognitive-os"

:: Start a background task to load the embedder and a default LLM after a short delay (gives the server time to start)
start /B "" cmd /c "timeout /t 10 /nobreak >nul && echo Loading embedder... && lms load text-embedding-bge-m3 -y && echo Loading default LLM... && lms load ministral-3-3b-instruct-2512 -c 8192 -y"

:: Start all services in a single Windows Terminal window.
:: The Ollama Bridge translates Ollama protocol -> LM Studio OpenAI server so
:: VS Code's BYOK "Ollama" provider can target the local model catalog.
:: It must start AFTER lms server (which it proxies to), so it's last in the chain.
wt -d "E:\Antigravity\cognitive-os" cmd /k "title LM Studio Server && lms server start --cors --bind 0.0.0.0" ; new-tab -d "E:\Antigravity\cognitive-os" cmd /k "title FastAPI Server && set PYTHONIOENCODING=utf-8 && python -m src.api" ; new-tab -d "E:\Antigravity\cognitive-os" cmd /k "title Telegram Server && set PYTHONIOENCODING=utf-8 && python -m src.telegram_bot" ; new-tab -d "E:\Antigravity\cognitive-os" cmd /k "title Kanban Watcher && set PYTHONIOENCODING=utf-8 && python -m src.kanban_processor --watch" ; new-tab -d "E:\Antigravity\obsidian-lmstudio-agent" cmd /k "title Obsidian Plugin Watcher (esbuild) && npm run dev" ; new-tab -d "E:\Antigravity\obsidian-lmstudio-agent" cmd /k "title Obsidian Plugin Deployer && node scripts/watch-and-deploy.js" ; new-tab -d "E:\Antigravity\cognitive-os" cmd /k "title Ollama Bridge (LM Studio -> VS Code BYOK) && set PYTHONIOENCODING=utf-8 && timeout /t 8 /nobreak >nul && python scratch/lms_ollama_bridge.py"
