@echo off
REM ============================================================
REM  Andor SDK3 NDSP controller launcher  (Windows acquisition PC)
REM
REM  One-time setup (from this folder):
REM    py -3.13 -m venv .venv
REM    .venv\Scripts\pip install -r requirements.txt
REM
REM  Run:
REM    run_andor.bat                 -> real camera (needs Andor SDK3 runtime)
REM    run_andor.bat --simulation    -> synthetic frames, no camera/SDK
REM
REM  Auto-restarts if the controller exits. Logs to logs\andor.log.
REM  Close this window (or Ctrl-C) to stop.
REM ============================================================
setlocal

set "HERE=%~dp0"
set "PY=%HERE%.venv\Scripts\python.exe"
set "PORT=3287"
set "LOGDIR=%HERE%logs"

if not exist "%PY%" (
    echo [run_andor] Python venv not found at %HERE%.venv
    echo [run_andor] Create it first:
    echo     py -3.13 -m venv .venv
    echo     .venv\Scripts\pip install -r requirements.txt
    pause
    exit /b 1
)

if not exist "%LOGDIR%" mkdir "%LOGDIR%"

:loop
echo [run_andor] Starting Andor NDSP on port %PORT% (bind *) ... logging to %LOGDIR%\andor.log
echo ===== start %date% %time% ===== >> "%LOGDIR%\andor.log"
"%PY%" "%HERE%aqctl_andor.py" -p %PORT% --bind "*" -v %* >> "%LOGDIR%\andor.log" 2>&1
echo [run_andor] Controller exited (code %errorlevel%). Restarting in 5s; close window or Ctrl-C to stop.
timeout /t 5 >nul
goto loop
