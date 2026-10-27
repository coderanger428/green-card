@echo off
cd /d "%~dp0"
call "%~dp0start.bat" stop
exit /b %ERRORLEVEL%
