@echo off
chcp 949 > nul

if not exist "venv" (
    echo [ERROR] Run install.bat first.
    pause
    exit /b 1
)

call venv\Scripts\activate.bat

REM Usage:
REM   run.bat                          F9 hotkey mode
REM   run.bat --setup                  Record Infinitt UI positions (run once)
REM   run.bat --excel patients.xlsx    Batch collect 280 patients
REM   run.bat --excel list.xlsx --resume 50   Resume from patient #50
REM   run.bat --find-pacs              Auto-detect PACS server settings
REM   run.bat --convert-only FOLDER    Convert existing files to images

python src\main.py %*
