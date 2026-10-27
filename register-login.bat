@echo off
setlocal EnableExtensions
cd /d "%~dp0"

REM Register a 5-minute delayed start after this Windows user signs in.
REM The Startup folder runs at sign-in, which is the session that follows power-on.
REM   register-login.bat         install
REM   register-login.bat remove  uninstall

set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "VBS=%STARTUP%\devto-scraper-delayed.vbs"
set "APP=%~dp0start.bat"

if /i "%~1"=="remove" goto :remove

if not exist "%STARTUP%" mkdir "%STARTUP%"
> "%VBS%" (
  echo ' Wait 5 minutes after sign-in, then start the Dev.to mail app.
  echo WScript.Sleep 300000
  echo CreateObject("Wscript.Shell"^).Run """%APP%""", 1, False
)
echo Registered. start.bat runs 5 minutes after this Windows user signs in.
echo   %VBS%
echo To remove: register-login.bat remove
exit /b 0

:remove
if exist "%VBS%" (
  del "%VBS%"
  echo Removed autostart.
) else (
  echo Nothing to remove ^(no Startup script found^).
)
exit /b 0
