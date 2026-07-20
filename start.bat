@echo off
if exist .venv\Scripts\python.exe goto :RUN
if exist .venv\bin\python goto :RUN

echo [ERROR] Virtual environment (.venv) not found.
echo Please run install.ps1 to setup the project first.
pause
exit /b 1

:RUN
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
if errorlevel 1 (
    echo [ERROR] Failed to start CiscoToolsV2.
    pause
    exit /b 1
)
