@echo off
setlocal EnableExtensions
cd /d "%~dp0"

REM The launcher to open. Default = run the app.
REM   start.bat          scraper + dashboard  ->  http://127.0.0.1:8007
REM   start.bat watch    live UI reload       ->  http://127.0.0.1:5173
REM   start.bat stop     shut everything down

set "PY=%~dp0.venv\Scripts\python.exe"
"%PY%" -c "import sys" >nul 2>&1
if errorlevel 1 (
  echo Project .venv is missing or its Python is gone.
  echo Recreate it with this machine's Python, then re-run start.bat:
  echo   python -m venv .venv
  echo   .venv\Scripts\python.exe -m pip install -r requirements.txt
  pause
  exit /b 1
)

"%PY%" "%~dp0launch.py" %*
set "ERR=%ERRORLEVEL%"
if not "%ERR%"=="0" pause
exit /b %ERR%
