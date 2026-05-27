@echo off
chcp 65001 > nul
echo ================================================================
echo  USB 패키지 준비 스크립트 - 인터넷 되는 PC에서만 실행하세요
echo ================================================================
echo.
echo 이 스크립트를 USB 드라이브 루트에 복사한 후 실행하면
echo USB 안에 필요한 모든 파일이 준비됩니다.
echo.

:: 현재 경로 저장 (USB 드라이브 경로)
set USB_ROOT=%~dp0
echo USB/작업 경로: %USB_ROOT%
echo.

:: Python 확인
python --version > nul 2>&1
if errorlevel 1 (
    echo [오류] 이 PC에 Python이 없습니다.
    echo python.org 에서 Python 3.11 설치 후 다시 실행하세요.
    pause
    exit /b 1
)

for /f "tokens=2" %%v in ('python --version') do set PYVER=%%v
echo 사용 Python: %PYVER%
echo.

:: ── 1. pip 패키지 다운로드 ──────────────────────────────────────
echo [1/3] pip 패키지 다운로드 중...
if not exist "%USB_ROOT%packages" mkdir "%USB_ROOT%packages"

pip download -r "%USB_ROOT%requirements.txt" ^
    -d "%USB_ROOT%packages" ^
    --platform win_amd64 ^
    --python-version 3.11 ^
    --only-binary=:all:

if errorlevel 1 (
    echo.
    echo [재시도] --only-binary 없이 다시 시도합니다...
    pip download -r "%USB_ROOT%requirements.txt" -d "%USB_ROOT%packages"
)
echo pip 패키지 다운로드 완료.
echo.

:: ── 2. Playwright 설치 및 Chromium 다운로드 ─────────────────────
echo [2/3] Playwright 및 Chromium 브라우저 다운로드 중...
pip install playwright --target "%USB_ROOT%packages\playwright_tmp" -q

:: playwright 실행파일로 chromium 다운로드
set PLAYWRIGHT_BROWSERS_PATH=%USB_ROOT%ms-playwright
python -m playwright install chromium 2>nul
if errorlevel 1 (
    pip install playwright -q
    set PLAYWRIGHT_BROWSERS_PATH=%USB_ROOT%ms-playwright
    playwright install chromium
)

if exist "%USB_ROOT%ms-playwright" (
    echo Chromium 다운로드 완료: %USB_ROOT%ms-playwright
) else (
    echo.
    echo [주의] 자동 다운로드 실패. 수동으로 복사하세요:
    echo   1. 명령 프롬프트에서 실행:
    echo      playwright install chromium
    echo   2. 브라우저 파일 위치:
    echo      %USERPROFILE%\AppData\Local\ms-playwright
    echo   3. 해당 폴더를 USB의 ms-playwright 폴더로 복사
)
echo.

:: ── 3. Python 설치 파일 다운로드 ────────────────────────────────
echo [3/3] Python 3.11 설치 파일 다운로드 중 (내부망 PC에 Python 없을 경우 대비)...
if not exist "%USB_ROOT%python_installer" mkdir "%USB_ROOT%python_installer"

:: winget 또는 curl로 Python 설치파일 받기
curl -L "https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe" ^
    -o "%USB_ROOT%python_installer\python-3.11.9-amd64.exe" 2>nul

if exist "%USB_ROOT%python_installer\python-3.11.9-amd64.exe" (
    echo Python 설치 파일 다운로드 완료.
) else (
    echo [주의] Python 설치 파일 자동 다운로드 실패.
    echo 수동으로 https://www.python.org/downloads/ 에서
    echo python-3.11.x-amd64.exe 를 받아 python_installer\ 폴더에 넣으세요.
)
echo.

:: ── 완료 안내 ─────────────────────────────────────────────────────
echo ================================================================
echo  준비 완료! USB에 다음 파일들이 생성되었습니다:
echo.
echo  USB\
echo  ├── packages\          (pip 패키지들)
echo  ├── ms-playwright\     (Chromium 브라우저)
echo  ├── python_installer\  (Python 설치 파일)
echo  ├── src\               (소스 코드)
echo  ├── config.yaml        (설정 파일)
echo  └── usb_설치_내부망PC에서실행.bat
echo.
echo  이제 USB를 내부망 PC에 꽂고
echo  usb_설치_내부망PC에서실행.bat 을 실행하세요.
echo ================================================================
pause
