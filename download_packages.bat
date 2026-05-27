@echo off
chcp 65001 > nul
echo === 패키지 다운로드 (인터넷 되는 PC에서 실행) ===
echo.
echo 다운로드한 파일을 내부망 PC로 옮겨서 install_offline.bat 을 실행하세요.
echo.

python --version > nul 2>&1
if errorlevel 1 (
    echo [오류] Python이 설치되어 있지 않습니다.
    pause
    exit /b 1
)

:: pip 패키지 다운로드
echo pip 패키지 다운로드 중...
pip download -r requirements.txt -d packages --platform win_amd64 --python-version 3.11 --only-binary=:all:

:: Playwright Chromium 다운로드 위치 안내
echo.
echo ─────────────────────────────────────────────
echo Playwright Chromium 브라우저 복사 방법:
echo.
echo 1. 이 PC에서 아래 명령 실행:
echo    pip install playwright
echo    playwright install chromium
echo.
echo 2. 브라우저 파일 위치:
echo    %%USERPROFILE%%\AppData\Local\ms-playwright
echo.
echo 3. ms-playwright 폴더를 내부망 PC로 복사 후
echo    폴더명을 'chromium' 으로 변경하세요.
echo ─────────────────────────────────────────────
echo.
echo 다운로드 완료. packages\ 폴더를 내부망 PC로 복사하세요.
pause
