@echo off
echo Starting DockWise AI...
echo.

:: ── 1. Kill any stale process on port 8004 ────────────────────────────────
echo [1/4] Clearing port 8004...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8004 "') do (
    taskkill /PID %%a /F >nul 2>&1
)

:: ── 2. Wipe Python bytecode cache (prevents stale .pyc issues) ────────────
echo [2/4] Clearing Python cache...
if exist "%~dp0venv2\backend\__pycache__" (
    rmdir /s /q "%~dp0venv2\backend\__pycache__"
)

:: ── 3. Start backend using venv2 Python explicitly ────────────────────────
echo [3/4] Starting backend...
start "DockWise Backend" cmd /k "cd /d %~dp0venv2\backend && %~dp0venv2\Scripts\python.exe -m uvicorn api:app --port 8004 --reload"

:: Wait for backend to be ready
timeout /t 6 /nobreak >nul

:: ── 4. Start frontend ──────────────────────────────────────────────────────
echo [4/4] Starting frontend...
start "DockWise Frontend" cmd /k "cd /d %~dp0venv2\frontend && npm start"

echo.
echo  Backend  ^>  http://localhost:8004
echo  Frontend ^>  http://localhost:3000
echo  API docs ^>  http://localhost:8004/docs
echo.
echo Both windows are running. Close them to stop the servers.
echo.
pause
