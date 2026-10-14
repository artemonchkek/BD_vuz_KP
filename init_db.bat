@echo off
cd /d "%~dp0"
set "PY="
py --version >nul 2>&1 && set "PY=py"
if not defined PY python --version >nul 2>&1 && set "PY=python"
if not defined PY goto nopython
echo [1/3] Python: %PY%
if exist .venv\Scripts\python.exe goto venvok
echo [2/3] Creating virtual environment and installing packages...
%PY% -m venv .venv
if errorlevel 1 goto fail
.venv\Scripts\python -m pip install -r requirements.txt
if errorlevel 1 goto fail
:venvok
echo [3/3] Re-creating database...
.venv\Scripts\python init_db.py
pause
exit /b 0
:nopython
echo Python not found. Install Python 3.10+ from python.org
pause
exit /b 1
:fail
echo.
echo ERROR. See messages above.
pause
exit /b 1
