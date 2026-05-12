@echo off
:: Navigate to the project directory
cd /d "E:\Antigravity\cognitive-os"

:: Force Python to use UTF-8 for console output so emoji prints don't crash the background process
set PYTHONIOENCODING=utf-8

:: Start the FastAPI Server in the background (-m ensures the src module is found correctly)
start /B "" python -m src.api > api.log 2>&1

:: Start the Telegram Bot in the background
start /B "" python -m src.telegram_bot > telegram.log 2>&1

:: Start the LM Studio Server headlessly
start /B "" lms server start --cors > lms.log 2>&1
