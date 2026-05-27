@echo off
chcp 65001 > nul

if not exist "venv" (
    echo [오류] 먼저 install.bat 을 실행하세요.
    pause
    exit /b 1
)

call venv\Scripts\activate.bat
python src\main.py %*
