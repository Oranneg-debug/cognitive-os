@echo off
:: Navigate to the project directory
cd /d "E:\Antigravity\cognitive-os"

:: Start the FastAPI Server in the background
start "Cognitive OS API" python src\api.py

:: Start the Telegram Bot in the background
start "Cognitive OS Telegram" python -m src.telegram_bot
