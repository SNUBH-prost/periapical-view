@echo off
chcp 65001 > nul
echo ================================================================
echo  USB 패키지 준비 스크립트 - 인터넷 되는 PC에서만 실행하세요
echo ================================================================
echo.
echo 이 스크립트를 USB 드라이브 루트에 복사한 후 실행하면
echo USB 안에 필요한 모든 파일이 준비됩니다.
echo.

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
python --version
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
    echo [재시도] --only-binary 없이 다시 시도합니다...
    pip download -r "%USB_ROOT%requirements.txt" -d "%USB_ROOT%packages"
)
echo pip 패키지 다운로드 완료.
echo.

:: ── 2. Python 설치 파일 다운로드 ────────────────────────────────
echo [2/3] Python 3.11 설치 파일 다운로드 중...
if not exist "%USB_ROOT%python_installer" mkdir "%USB_ROOT%python_installer"

curl -L "https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe" ^
    -o "%USB_ROOT%python_installer\python-3.11.9-amd64.exe" 2>nul

if exist "%USB_ROOT%python_installer\python-3.11.9-amd64.exe" (
    echo Python 설치 파일 다운로드 완료.
) else (
    echo [주의] 수동으로 python.org 에서 python-3.11.x-amd64.exe 를
    echo        받아 python_installer\ 폴더에 넣으세요.
)
echo.

:: ── 3. 완료 안내 ─────────────────────────────────────────────────
echo ================================================================
echo  준비 완료!
echo.
echo  USB에 아래 항목이 있는지 확인하세요:
echo    packages\          pip 패키지 (.whl 파일들)
echo    python_installer\  Python 설치 파일
echo    src\               소스 코드
echo    config.yaml        설정 파일
echo    usb_설치_내부망PC에서실행.bat
echo.
echo  USB를 내부망 PC에 꽂고
echo  usb_설치_내부망PC에서실행.bat 을 실행하세요.
echo ================================================================
pause
