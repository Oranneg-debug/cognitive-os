@echo off
echo Starting Cognitive OS API Server with Sync Bridge...
echo ================================================
cd /d E:\Antigravity\cognitive-os
python -c "import sys; sys.path.insert(0, '.'); from src.api import app; import uvicorn; uvicorn.run(app, host='0.0.0.0', port=8000)"
pause