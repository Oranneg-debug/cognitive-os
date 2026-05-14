@echo off
:: Navigate to the project directory
cd /d "E:\Antigravity\cognitive-os"

:: Start a background task to load the embedder and a default LLM after a short delay (gives the server time to start)
start /B "" cmd /c "timeout /t 10 /nobreak >nul && echo Loading embedder... && lms load text-embedding-bge-m3 -y && echo Loading default LLM... && lms load ministral-3-3b-instruct-2512 -c 8192 -y"

:: Start all services in a single Windows Terminal window with 3 tabs.
wt -d "E:\Antigravity\cognitive-os" cmd /k "title LM Studio Server && lms server start --cors --bind 0.0.0.0" ; new-tab -d "E:\Antigravity\cognitive-os" cmd /k "title FastAPI Server && set PYTHONIOENCODING=utf-8 && python -m src.api" ; new-tab -d "E:\Antigravity\cognitive-os" cmd /k "title Telegram Server && set PYTHONIOENCODING=utf-8 && python -m src.telegram_bot"
