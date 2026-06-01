@echo off
chcp 949 > nul
echo ============================================================
echo   Periapical View Collector  -  Install
echo ============================================================
echo.

python --version > nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found.
    echo.
    echo   Download Python 3.10+ from https://www.python.org/downloads/
    echo   Check "Add Python to PATH" during installation.
    echo.
    pause
    exit /b 1
)
echo [OK] Python:
python --version
echo.

if not exist "venv" (
    echo Creating virtual environment...
    python -m venv venv
)

echo Installing packages...
call venv\Scripts\activate.bat
python -m pip install --upgrade pip --quiet
pip install -r requirements.txt

echo.
echo ============================================================
echo   Install complete!
echo.
echo   Next steps:
echo     1. run.bat --setup          Record Infinitt UI positions
echo     2. run.bat --excel list.xlsx  Start batch collection
echo ============================================================
pause
