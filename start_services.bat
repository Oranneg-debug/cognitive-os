@echo off
:: Navigate to the project directory
cd /d "E:\Antigravity\cognitive-os"

:: Start a background task to load the embedder and a default LLM after a short delay (gives the server time to start).
::
:: ministral-3-3b is used as moderator AND scribe AND brand-guard companion in the
:: boardroom council. The scribe receives the full deliberation transcript (~10-14K
:: tokens for typical proposals). Loading with -c 8192 caused 4 consecutive boardroom
:: failures (2026-05-22 / 23) — every council with a real-sized proposal blew up at
:: the scribe with n_keep > n_ctx, and the orchestrator wrote the error string as
:: the "synthesis". See dev/decisions/_bootstrap_approvals_2026-05-22.md.
::
:: -c 32768  : fits any realistic council transcript with headroom (3B model on CPU,
::             trivial RAM cost)
:: --gpu off : pin to CPU per the VRAM-policy agreement (moderator/scribe/brand-guards
::             must not eat VRAM that 70B reviewers need)
start /B "" cmd /c "timeout /t 10 /nobreak >nul && echo Loading embedder on CPU... && lms load text-embedding-bge-m3 --gpu off -y && echo Loading default LLM at 32K ctx on CPU... && lms load ministral-3-3b-instruct-2512 -c 32768 --gpu off -y"

:: Start all services in a single Windows Terminal window.
::
:: Services that USED to be in this list and are now removed:
::   - Kanban Watcher (python -m src.kanban_processor --watch)
::     Deprecated by ARCH-DA5B0A2D (2026-05-25). The dashboard's
::     Kanban tab + /api/workflow/transition own card movements now.
::     Re-enabling the watcher would race the renderer and corrupt the
::     vault mirror.
::
:: The Ollama Bridge translates Ollama protocol -> LM Studio OpenAI server so
:: VS Code's BYOK "Ollama" provider can target the local model catalog.
:: It must start AFTER lms server (which it proxies to), so it's last in the chain.
wt -d "E:\Antigravity\cognitive-os" cmd /k "title LM Studio Server && lms server start --cors --bind 0.0.0.0" ; new-tab -d "E:\Antigravity\cognitive-os" cmd /k "title FastAPI Server && set PYTHONIOENCODING=utf-8 && python -m src.api" ; new-tab -d "E:\Antigravity\cognitive-os" cmd /k "title Telegram Server && set PYTHONIOENCODING=utf-8 && python -m src.telegram_bot" ; new-tab -d "E:\Antigravity\obsidian-lmstudio-agent" cmd /k "title Obsidian Plugin Watcher (esbuild) && npm run dev" ; new-tab -d "E:\Antigravity\obsidian-lmstudio-agent" cmd /k "title Obsidian Plugin Deployer && node scripts/watch-and-deploy.js" ; new-tab -d "E:\Antigravity\cognitive-os" cmd /k "title Ollama Bridge (LM Studio -> VS Code BYOK) && set PYTHONIOENCODING=utf-8 && timeout /t 8 /nobreak >nul && python scratch/lms_ollama_bridge.py"
