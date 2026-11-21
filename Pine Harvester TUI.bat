@echo off
setlocal
cd /d "%~dp0"

set "PY=%TV_TUI_PYTHON%"
if not defined PY if exist "%~dp0.venv\Scripts\python.exe" set "PY=%~dp0.venv\Scripts\python.exe"
if not defined PY if exist "%~dp0venv\Scripts\python.exe" set "PY=%~dp0venv\Scripts\python.exe"
if not defined PY if exist "%~dp0..\tools\py-tui\Scripts\python.exe" set "PY=%~dp0..\tools\py-tui\Scripts\python.exe"
if not defined PY if exist "%~dp0..\..\tools\py-tui\Scripts\python.exe" set "PY=%~dp0..\..\tools\py-tui\Scripts\python.exe"
if not defined PY (
    where python >nul 2>nul
    if not errorlevel 1 set "PY=python"
)
if not defined PY (
    echo Python 3.12+ was not found.
    echo Install Python, then run: pip install -r requirements.txt
    pause
    exit /b 1
)

"%PY%" -c "import textual" >nul 2>nul
if errorlevel 1 (
    echo The TUI requires Textual.
    echo Run: "%PY%" -m pip install -r requirements.txt
    pause
    exit /b 1
)

"%PY%" "code files\tui\harvester_tui.py"
if errorlevel 1 pause
endlocal
