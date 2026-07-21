@echo off
setlocal EnableExtensions
cd /d "%~dp0.."

set "LOGDIR=%CD%\data\logs"
if not exist "%LOGDIR%" mkdir "%LOGDIR%"

for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set "STAMP=%%i"
set "LOGFILE=%LOGDIR%\factory_%STAMP%.log"

if exist ".venv\Scripts\python.exe" (
    set "PYTHON=.venv\Scripts\python.exe"
) else (
    set "PYTHON=python"
)

set "EXTRA=%~1"

echo [%date% %time%] Starting pipeline %EXTRA%>> "%LOGFILE%"
"%PYTHON%" main.py %EXTRA% >> "%LOGFILE%" 2>&1
set "EXITCODE=%ERRORLEVEL%"
echo [%date% %time%] Exit code: %EXITCODE%>> "%LOGFILE%"
exit /b %EXITCODE%
