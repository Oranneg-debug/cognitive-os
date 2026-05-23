# PowerShell script to start the API server
Write-Host "Starting Cognitive OS API Server with Sync Bridge..." -ForegroundColor Green
Write-Host "=" * 50 -ForegroundColor Green

Set-Location -Path "E:\Antigravity\cognitive-os"
python -c @"
import sys
sys.path.insert(0, '.')
from src.api import app
import uvicorn
print('API Server starting on http://localhost:8000')
print('Sync endpoints available at /api/sync/*')
uvicorn.run(app, host='0.0.0.0', port=8000)
"@