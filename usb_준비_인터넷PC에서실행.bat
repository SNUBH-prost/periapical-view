@echo off
chcp 949 > nul
setlocal enabledelayedexpansion

echo ================================================================
echo  [STEP 1] USB Package Preparation  (Internet PC)
echo ================================================================
echo.
echo  Prepares everything needed to install on the internal-network PC.
echo  Run this from the USB drive root folder.
echo.

set "USB_ROOT=%~dp0"

:: ── 1. Python 설치 파일 다운로드 ─────────────────────────────────
echo [1/3] Downloading Python 3.11 installer...
if not exist "%USB_ROOT%python_installer" mkdir "%USB_ROOT%python_installer"
set "PY_EXE=%USB_ROOT%python_installer\python-3.11.9-amd64.exe"

if not exist "%PY_EXE%" (
    curl -L --progress-bar "https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe" -o "%PY_EXE%"
) else (
    echo   Already downloaded. Skipping.
)
if not exist "%PY_EXE%" (
    echo [ERROR] Could not download Python installer.
    echo   Download manually and place in: %USB_ROOT%python_installer\
    pause
    exit /b 1
)
echo   OK.
echo.

:: ── 2. Python 찾기 (없으면 설치) ─────────────────────────────────
echo [2/3] Locating Python...

set "PYTHON="
:: 이미 PATH에 있으면 사용
python --version > nul 2>&1
if not errorlevel 1 (
    set "PYTHON=python"
    echo   Found Python on PATH.
)

:: PATH에 없으면 잘 알려진 설치 위치들을 직접 탐색
if not defined PYTHON (
    for %%P in (
        "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
        "%ProgramFiles%\Python311\python.exe"
        "%ProgramFiles(x86)%\Python311\python.exe"
        "C:\Python311\python.exe"
    ) do (
        if exist "%%~P" set "PYTHON=%%~P"
    )
)

:: 그래도 없으면 silent 설치 후 다시 탐색
if not defined PYTHON (
    echo   Python not found. Installing silently ^(please wait^)...
    "%PY_EXE%" /quiet InstallAllUsers=0 PrependPath=1 Include_test=0
    echo   Install finished. Locating python.exe...
    for %%P in (
        "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
        "%ProgramFiles%\Python311\python.exe"
        "%ProgramFiles(x86)%\Python311\python.exe"
        "C:\Python311\python.exe"
    ) do (
        if exist "%%~P" set "PYTHON=%%~P"
    )
)

if not defined PYTHON (
    echo.
    echo [ERROR] Python was installed but python.exe could not be located.
    echo   Close this window, open a NEW command prompt, and run this script again.
    pause
    exit /b 1
)

echo   Using: !PYTHON!
"!PYTHON!" --version
echo.

:: ── 3. pip 패키지를 wheel로 빌드/다운로드 ─────────────────────────
:: pip wheel 을 쓰면 .tar.gz(소스)도 이 PC에서 .whl 로 만들어 둠
:: → 내부망에서는 빌드(setuptools) 필요 없이 바로 설치 가능
echo [3/3] Building wheels for all packages...
if not exist "%USB_ROOT%packages" mkdir "%USB_ROOT%packages"

:: 최신 빌드 도구 먼저 확보
"!PYTHON!" -m pip install --upgrade pip setuptools wheel

:: setuptools/wheel 자체도 오프라인 설치에 대비해 packages 에 담아둠
"!PYTHON!" -m pip download pip setuptools wheel -d "%USB_ROOT%packages"

:: 모든 의존성을 wheel 로 빌드해서 packages 에 저장
"!PYTHON!" -m pip wheel -r "%USB_ROOT%requirements.txt" -w "%USB_ROOT%packages"

if errorlevel 1 (
    echo [ERROR] Wheel build failed. Check internet connection and retry.
    pause
    exit /b 1
)
echo   OK.
echo.

:: ── 다운로드 결과 확인 ────────────────────────────────────────────
dir /b "%USB_ROOT%packages\*.whl" > nul 2>&1
if errorlevel 1 (
    echo [WARNING] No .whl files in packages folder. Something went wrong.
    pause
    exit /b 1
)

echo ================================================================
echo  Done! USB is ready.
echo    packages\          downloaded .whl files
echo    python_installer\  Python .exe
echo    src\               source code
echo.
echo  Plug USB into the internal-network PC and run:
echo    usb_설치_내부망PC에서실행.bat
echo ================================================================
pause
