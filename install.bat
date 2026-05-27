@echo off
chcp 65001 > nul
echo === 치근단 방사선 사진 수집 도구 설치 (Windows) ===
echo.

:: Python 설치 확인
python --version > nul 2>&1
if errorlevel 1 (
    echo [오류] Python이 설치되어 있지 않습니다.
    echo https://www.python.org/downloads/ 에서 Python 3.10 이상을 설치하세요.
    pause
    exit /b 1
)
python --version

:: 가상환경 생성
if not exist "venv" (
    echo 가상환경 생성 중...
    python -m venv venv
)

:: 가상환경 활성화 및 패키지 설치
echo 패키지 설치 중...
call venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt

:: Playwright Chromium 브라우저 설치
echo Playwright Chromium 설치 중...
playwright install chromium

echo.
echo === 설치 완료 ===
echo.
echo 다음 단계:
echo 1. config.yaml 에서 PACS 접속 정보를 설정하세요
echo    pacs.url, pacs.username, pacs.password
echo.
echo 2. PACS UI 탐색 (셀렉터 확인용):
echo    run.bat --inspect
echo.
echo 3. 소량 테스트 (5건):
echo    run.bat --limit 5
echo.
echo 4. 전체 수집:
echo    run.bat
echo.
pause
