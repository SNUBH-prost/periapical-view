@echo off
chcp 949 > nul

cd /d "%~dp0"

if not exist "venv" (
    echo [ERROR] venv not found. Run install.bat first.
    pause
    exit /b 1
)

call venv\Scripts\activate.bat

REM Usage:
REM   run.bat --check                  Validate setup without Infinitt
REM   run.bat --setup                  Record Infinitt UI positions (run once)
REM   run.bat --excel patients.xlsx    Batch collect patients
REM   run.bat --excel list.xlsx --resume 50   Resume from patient #50
REM   run.bat                          F9 hotkey mode

python src\main.py %*

if errorlevel 1 (
    echo.
    echo [The program exited with an error. See the message above.]
    pause
)
