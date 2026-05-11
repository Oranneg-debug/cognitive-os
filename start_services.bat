@echo off
:: Navigate to the project directory
cd /d "E:\Antigravity\cognitive-os"

:: Set models directory explicitly
set LMSTUDIO_MODELS_DIR=E:\AI Models\models

:: Use Windows Terminal to group everything into a single window with multiple tabs.
:: Tab 1: LM Studio Server (bound to local network 0.0.0.0)
:: Tab 2: Cognitive OS API
:: Tab 3: Cognitive OS Telegram
:: Tab 4: Pre-loader & VRAM Monitor (nvidia-smi)
wt new-tab --title "LM Studio Server" -d . cmd /k "lms server start --bind 0.0.0.0 --cors" ; new-tab --title "Cognitive OS API" -d . cmd /k "python -m src.api" ; new-tab --title "Cognitive OS Telegram" -d . cmd /k "python -m src.telegram_bot" ; new-tab --title "Resource Monitor" -d . cmd /k "echo Waiting for server to boot... && timeout /t 5 && echo Loading Embedder... && lms load text-embedding-bge-m3 --gpu max -y && echo Loading Ministral... && lms load ministral-3-3b-instruct-2512 --gpu max -c 8192 -y && echo Models loaded! Starting live VRAM monitor... && timeout /t 2 && nvidia-smi -l 2"
