@echo off
chcp 65001 > nul

if not exist "venv" (
    echo [오류] 먼저 install.bat 을 실행하세요.
    pause
    exit /b 1
)

call venv\Scripts\activate.bat

REM ────────────────────────────────────────────────────────
REM  사용법:
REM    run.bat                         → F9 단축키 모드 (이미지 위 커서 → F9 → 저장)
REM    run.bat --setup                 → UI 좌표 기록 (배치 전 최초 1회)
REM    run.bat --excel 환자목록.xlsx   → 배치: 280명 자동 수집
REM    run.bat --excel 목록.xlsx --resume 50  → 50번째 환자부터 이어서
REM    run.bat --find-pacs             → PACS 서버 설정 자동 탐색
REM    run.bat --convert-only 폴더명   → 기존 파일 이미지 변환
REM ────────────────────────────────────────────────────────

python src\main.py %*
