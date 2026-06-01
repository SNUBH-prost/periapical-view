@echo off
chcp 65001 > nul
echo ============================================================
echo   치근단 방사선 사진 수집 도구  -  설치
echo ============================================================
echo.

:: Python 설치 확인
python --version > nul 2>&1
if errorlevel 1 (
    echo [오류] Python이 설치되어 있지 않습니다.
    echo.
    echo   https://www.python.org/downloads/
    echo   위 주소에서 Python 3.10 이상을 설치한 뒤 다시 실행하세요.
    echo   설치 시 "Add Python to PATH" 옵션을 반드시 체크하세요.
    echo.
    pause
    exit /b 1
)
echo [OK] Python 버전:
python --version

:: 가상환경 생성
if not exist "venv" (
    echo.
    echo 가상환경 생성 중...
    python -m venv venv
)

:: 패키지 설치
echo.
echo Python 패키지 설치 중... (수 분 소요)
call venv\Scripts\activate.bat
python -m pip install --upgrade pip --quiet
pip install -r requirements.txt

echo.
echo ============================================================
echo   설치 완료!
echo ============================================================
echo.
echo   다음 단계:
echo.
echo   [1단계] UI 좌표 기록  (Infinitt 켜놓고 실행)
echo           run.bat --setup
echo.
echo   [2단계] 배치 수집 실행
echo           run.bat --excel 환자목록.xlsx
echo.
pause
