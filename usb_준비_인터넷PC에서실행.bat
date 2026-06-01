@echo off
chcp 949 > nul

echo ================================================================
echo  [STEP 1] USB Package Preparation  (Internet PC)
echo ================================================================
echo.

set USB_ROOT=%~dp0

python --version > nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found.
    echo   Install Python 3.11 from https://www.python.org/downloads/
    pause
    exit /b 1
)
python --version
echo.

echo [1/2] Downloading pip packages...
if not exist "%USB_ROOT%packages" mkdir "%USB_ROOT%packages"

pip download -r "%USB_ROOT%requirements.txt" ^
    -d "%USB_ROOT%packages" ^
    --platform win_amd64 ^
    --python-version 3.11 ^
    --only-binary=:all:

if errorlevel 1 (
    echo Retrying without binary restriction...
    pip download -r "%USB_ROOT%requirements.txt" -d "%USB_ROOT%packages"
)
echo.

echo [2/2] Downloading Python 3.11 installer...
if not exist "%USB_ROOT%python_installer" mkdir "%USB_ROOT%python_installer"

curl -L "https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe" ^
    -o "%USB_ROOT%python_installer\python-3.11.9-amd64.exe"

if exist "%USB_ROOT%python_installer\python-3.11.9-amd64.exe" (
    echo [OK] Python installer downloaded.
) else (
    echo [WARN] Download failed. Manually place python-3.11.9-amd64.exe
    echo        inside the python_installer\ folder.
)
echo.

echo ================================================================
echo  Done! Check USB contains:
echo    packages\              .whl files
echo    python_installer\      Python .exe installer
echo    src\                   source code
echo    config.yaml
echo    requirements.txt
echo    usb_install_on_internal_pc.bat
echo.
echo  Plug USB into the internal-network PC and run:
echo    usb_설치_내부망PC에서실행.bat
echo ================================================================
pause
