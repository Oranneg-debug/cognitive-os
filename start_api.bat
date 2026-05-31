@echo off
echo Starting Cognitive OS API Server with Sync Bridge...
echo ================================================
cd /d E:\Antigravity\cognitive-os

REM Set COS_VAULT_PATH environment variable (system-side Obsidian vault)
set "COS_VAULT_PATH=E:\Oranneg\CloudStation\Documents\Obsidian\Cognitive OS"

echo Environment:
echo   COS_VAULT_PATH=%COS_VAULT_PATH%
echo.

python -c "import sys; sys.path.insert(0, '.'); from src.api import app; import uvicorn; uvicorn.run(app, host='0.0.0.0', port=8000)"
pause