@echo off
chcp 65001 > nul
echo === 오프라인 설치 (인터넷 없는 내부망용) ===
echo.
echo 이 스크립트를 실행하기 전에:
echo 1. 인터넷 되는 PC에서 download_packages.bat 을 먼저 실행해 packages\ 폴더를 만드세요.
echo 2. packages\ 폴더와 chromium\ 폴더를 이 PC로 복사하세요.
echo.

if not exist "packages" (
    echo [오류] packages\ 폴더가 없습니다.
    echo 인터넷 되는 PC에서 download_packages.bat 을 먼저 실행하세요.
    pause
    exit /b 1
)

python --version > nul 2>&1
if errorlevel 1 (
    echo [오류] Python이 설치되어 있지 않습니다.
    pause
    exit /b 1
)

if not exist "venv" (
    python -m venv venv
)

call venv\Scripts\activate.bat
python -m pip install --upgrade pip --no-index --find-links=packages
pip install --no-index --find-links=packages -r requirements.txt

:: Playwright 브라우저를 로컬 경로로 지정
if exist "chromium" (
    echo Playwright 브라우저 경로 설정 중...
    setx PLAYWRIGHT_BROWSERS_PATH "%CD%\chromium"
    echo 브라우저 경로: %CD%\chromium
) else (
    echo [주의] chromium\ 폴더가 없습니다. 브라우저를 수동으로 복사하세요.
    echo 인터넷 PC에서: playwright install chromium
    echo 브라우저 폴더 위치: %%USERPROFILE%%\AppData\Local\ms-playwright
)

echo.
echo === 오프라인 설치 완료 ===
pause
