@echo off
:: Navigate to the project directory
cd /d "E:\Antigravity\cognitive-os"

:: Use Windows Terminal to group everything into a single window with multiple tabs.
wt new-tab --title "LM Studio Server" -d . cmd /k "lms server start" ; new-tab --title "Cognitive OS API" -d . cmd /k "python -m src.api" ; new-tab --title "Cognitive OS Telegram" -d . cmd /k "python -m src.telegram_bot"
