@echo off
REM Optional: live-reload UI while editing frontend/.
REM Daily use / after Python or template changes: start.bat
cd /d "%~dp0"
call "%~dp0start.bat" watch
exit /b %ERRORLEVEL%
