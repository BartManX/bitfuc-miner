@echo off
cd /d "%~dp0"
if exist bitfuc-miner.exe (
  start "" bitfuc-miner.exe
) else if exist mine_gui.py (
  pythonw mine_gui.py 2>nul || python mine_gui.py
) else if exist mine_fuc.exe (
  echo No GUI found. CLI: set STRATUM_USER=yourwallet.worker1
  mine_fuc.exe
) else (
  echo missing bitfuc-miner.exe
  pause
  exit /b 1
)
