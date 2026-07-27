@echo off
chcp 65001 >nul
REM ── 차트 추출기 실행 ──────────────────────────────
REM   사용법:  run.bat "C:\경로\환자목록.xlsx"
REM   점검만:  run.bat "C:\경로\환자목록.xlsx" --check

cd /d "%~dp0"

if "%~1"=="" (
  echo 엑셀 파일을 끌어다 놓거나 경로를 적어주세요.
  echo   예:  run.bat "C:\Users\me\Desktop\환자목록.xlsx"
  pause
  exit /b 1
)

python -m src.main --excel %*
echo.
pause
