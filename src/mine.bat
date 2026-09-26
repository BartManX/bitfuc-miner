@echo off
cd /d "%~dp0"
REM Edit STRATUM_USER to your fuc1... wallet
set STRATUM_HOST=pool.miningcrypto.online
set STRATUM_PORT=3073
set STRATUM_USER=fuc1qnt4kydw9hdlkpe243fxja4tuehhfvnyalxq0wc.worker1
set STRATUM_PASS=x
set THREADS=1
if exist mine_fuc.exe (
  mine_fuc.exe
) else if exist mine_fuc.py (
  python mine_fuc.py
) else (
  echo missing mine_fuc.exe / mine_fuc.py
  pause
  exit /b 1
)
if errorlevel 1 pause
pause
