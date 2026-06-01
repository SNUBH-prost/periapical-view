@echo off
chcp 65001 > nul
echo ================================================================
echo  [STEP 1] USB 준비  -  인터넷 되는 PC에서 실행하세요
echo ================================================================
echo.
echo  이 스크립트를 USB 루트에 복사한 뒤 실행하면
echo  내부망 설치에 필요한 파일이 모두 USB 안에 준비됩니다.
echo.

set USB_ROOT=%~dp0

:: Python 확인
python --version > nul 2>&1
if errorlevel 1 (
    echo [오류] 이 PC에 Python이 없습니다.
    echo   https://www.python.org/downloads/ 에서 3.11 설치 후 다시 실행하세요.
    pause
    exit /b 1
)
echo [OK] 인터넷 PC Python 버전:
python --version
echo.

:: ── 1. pip 패키지 다운로드 ────────────────────────────────────────
echo [1/2] pip 패키지 다운로드 중...
if not exist "%USB_ROOT%packages" mkdir "%USB_ROOT%packages"

pip download -r "%USB_ROOT%requirements.txt" ^
    -d "%USB_ROOT%packages" ^
    --platform win_amd64 ^
    --python-version 3.11 ^
    --only-binary=:all:

if errorlevel 1 (
    echo [재시도] 바이너리 제한 없이 다시 다운로드합니다...
    pip download -r "%USB_ROOT%requirements.txt" -d "%USB_ROOT%packages"
)
echo.

:: ── 2. Python 설치 파일 다운로드 ─────────────────────────────────
echo [2/2] Python 3.11 설치 파일 다운로드 중...
if not exist "%USB_ROOT%python_installer" mkdir "%USB_ROOT%python_installer"

curl -L "https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe" ^
    -o "%USB_ROOT%python_installer\python-3.11.9-amd64.exe"

if exist "%USB_ROOT%python_installer\python-3.11.9-amd64.exe" (
    echo [OK] Python 설치 파일 다운로드 완료.
) else (
    echo [주의] 자동 다운로드 실패.
    echo   https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe
    echo   위 주소에서 직접 받아 python_installer\ 폴더에 넣으세요.
)
echo.

:: ── 완료 ──────────────────────────────────────────────────────────
echo ================================================================
echo  준비 완료!  USB 안에 다음 항목이 있는지 확인하세요:
echo.
echo    packages\                  pip 패키지 (.whl 파일들)
echo    python_installer\          Python 설치 파일 (.exe)
echo    src\                       소스 코드
echo    config.yaml                설정 파일
echo    requirements.txt
echo    usb_설치_내부망PC에서실행.bat
echo.
echo  이제 USB를 내부망 PC에 꽂고
echo  usb_설치_내부망PC에서실행.bat 을 실행하세요.
echo ================================================================
pause
