@echo off
set SOURCE=E:\Antigravity\cognitive-os\dev\proposals\
set VAULT=E:\Oranneg\CloudStation\Documents\Obsidian\Grand Nexus\.obsidian\plugins\dev\

if not exist "%VAULT%" mkdir "%VAULT%"
robocopy /ZB /R:1 /W:2 "%SOURCE%" "%VAULT%proposals\" 2>nul
echo Sync complete!