@echo off
chcp 949 > nul

echo ================================================================
echo  [STEP 2] Offline Install  (Internal Network PC)
echo ================================================================
echo.

set USB_ROOT=%~dp0
set INSTALL_DIR=%USERPROFILE%\Desktop\periapical-view

:: 1. Python check / install
python --version > nul 2>&1
if errorlevel 1 (
    echo Python not found. Installing from USB...
    if exist "%USB_ROOT%python_installer\python-3.11.9-amd64.exe" (
        echo.
        echo [IMPORTANT] Check "Add python.exe to PATH" during installation!
        echo.
        "%USB_ROOT%python_installer\python-3.11.9-amd64.exe"
        echo.
        echo After install: close this window, open a new cmd, run this script again.
    ) else (
        echo [ERROR] python_installer\ folder is missing the .exe file.
    )
    pause
    exit /b 1
)
echo [OK] Python:
python --version
echo.

:: 2. Copy project files
echo [1/3] Copying project files to Desktop...
if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"
xcopy "%USB_ROOT%src"              "%INSTALL_DIR%\src\"  /E /I /Y /Q > nul
copy  "%USB_ROOT%config.yaml"      "%INSTALL_DIR%\config.yaml"       /Y > nul
copy  "%USB_ROOT%requirements.txt" "%INSTALL_DIR%\requirements.txt"  /Y > nul
copy  "%USB_ROOT%run.bat"          "%INSTALL_DIR%\run.bat"           /Y > nul
echo Done: %INSTALL_DIR%
echo.

:: 3. Create virtual environment
echo [2/3] Creating virtual environment...
if not exist "%INSTALL_DIR%\venv" (
    python -m venv "%INSTALL_DIR%\venv"
    echo Virtual environment created.
) else (
    echo Virtual environment already exists. Skipping.
)
echo.

:: 4. Offline package install
echo [3/3] Installing packages (offline)...
call "%INSTALL_DIR%\venv\Scripts\activate.bat"

set PKG_DIR=%USB_ROOT%packages

:: 먼저 packages 폴더와 .whl 파일이 실제로 있는지 진단
if not exist "%PKG_DIR%" (
    echo.
    echo [ERROR] packages folder NOT found:
    echo   %PKG_DIR%
    echo.
    echo   The download step did not run on the internet PC/VM.
    echo   Go back to the internet PC and run:
    echo     usb_준비_인터넷PC에서실행.bat
    echo   Wait until you see "Done! USB is ready", then bring USB back.
    pause
    exit /b 1
)

dir /b "%PKG_DIR%\*.whl" > nul 2>&1
if errorlevel 1 (
    echo.
    echo [ERROR] packages folder exists but has NO .whl files:
    echo   %PKG_DIR%
    echo.
    echo   The download on the internet PC/VM failed or was incomplete.
    echo   Re-run usb_준비_인터넷PC에서실행.bat on the internet PC and
    echo   watch for any error messages during download.
    pause
    exit /b 1
)

echo   Found packages in: %PKG_DIR%
pip install --no-index --find-links "%PKG_DIR%" -r "%INSTALL_DIR%\requirements.txt"

if errorlevel 1 (
    echo.
    echo [ERROR] Package install failed even though .whl files exist.
    echo   Packages folder: %PKG_DIR%
    echo   The .whl files may be for a different Python version.
    echo   On the internet PC, make sure Python 3.11 is used for download.
    pause
    exit /b 1
)
echo.

echo ================================================================
echo  Install complete!
echo.
echo  Location: %INSTALL_DIR%
echo.
echo  Next steps (open cmd and cd to that folder):
echo    run.bat --setup            Record Infinitt UI positions (once)
echo    run.bat --excel list.xlsx  Run batch collection
echo    run.bat                    F9 hotkey mode
echo.
echo  Output saved to: %INSTALL_DIR%\output\
echo ================================================================
pause
