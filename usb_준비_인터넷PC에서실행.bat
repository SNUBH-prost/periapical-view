@echo off
chcp 949 > nul

echo ================================================================
echo  [STEP 1] USB Package Preparation  (Internet PC)
echo ================================================================
echo.
echo  Prepares everything needed to install on the internal-network PC.
echo  Run this from the USB drive root folder.
echo.

set USB_ROOT=%~dp0

:: ── 1. Python 설치 파일 다운로드 ─────────────────────────────────
echo [1/3] Downloading Python 3.11 installer...
if not exist "%USB_ROOT%python_installer" mkdir "%USB_ROOT%python_installer"
set PY_EXE=%USB_ROOT%python_installer\python-3.11.9-amd64.exe

if not exist "%PY_EXE%" (
    curl -L --progress-bar "https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe" ^
        -o "%PY_EXE%"
) else (
    echo   Already downloaded. Skipping.
)

if not exist "%PY_EXE%" (
    echo [ERROR] Could not download Python installer.
    echo   Please download manually:
    echo   https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe
    echo   and place it in: %USB_ROOT%python_installer\
    pause
    exit /b 1
)
echo   OK.
echo.

:: ── 2. Python 설치 (아직 없으면 자동 설치) ────────────────────────
echo [2/3] Checking Python...
python --version > nul 2>&1
if errorlevel 1 (
    echo   Python not found. Installing silently...
    "%PY_EXE%" /quiet InstallAllUsers=0 PrependPath=1 Include_test=0
    echo   Done. Refreshing PATH...

    :: 설치 후 PATH 반영을 위해 새 cmd 세션에서 pip 실행
    set PY_PATH=%LOCALAPPDATA%\Programs\Python\Python311
    if not exist "%PY_PATH%\python.exe" (
        set PY_PATH=%ProgramFiles%\Python311
    )
    set PATH=%PY_PATH%;%PY_PATH%\Scripts;%PATH%
) else (
    echo   Python already installed. OK.
)

python --version > nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python install did not add to PATH.
    echo   Open a NEW command prompt and re-run this script.
    pause
    exit /b 1
)
python --version
echo.

:: ── 3. pip 패키지 다운로드 ────────────────────────────────────────
echo [3/3] Downloading pip packages...
if not exist "%USB_ROOT%packages" mkdir "%USB_ROOT%packages"

pip download -r "%USB_ROOT%requirements.txt" ^
    -d "%USB_ROOT%packages" ^
    --platform win_amd64 ^
    --python-version 3.11 ^
    --only-binary=:all:

if errorlevel 1 (
    echo   Retrying without platform restriction...
    pip download -r "%USB_ROOT%requirements.txt" -d "%USB_ROOT%packages"
    if errorlevel 1 (
        echo [ERROR] Package download failed.
        echo   Check internet connection and try again.
        pause
        exit /b 1
    )
)
echo   OK.
echo.

:: ── 완료 ──────────────────────────────────────────────────────────
echo ================================================================
echo  Done! USB is ready. Check these folders exist:
echo    %USB_ROOT%packages\           .whl files
echo    %USB_ROOT%python_installer\   Python .exe
echo    %USB_ROOT%src\                source code
echo    %USB_ROOT%requirements.txt
echo.
echo  Plug USB into the internal-network PC and run:
echo    usb_설치_내부망PC에서실행.bat
echo ================================================================
pause
