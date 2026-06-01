@echo off
chcp 65001 > nul
echo ================================================================
echo  [STEP 2] 오프라인 설치  -  내부망 PC에서 실행하세요
echo ================================================================
echo.

set USB_ROOT=%~dp0
set INSTALL_DIR=%USERPROFILE%\Desktop\periapical-view

:: ── 1. Python 설치 ────────────────────────────────────────────────
python --version > nul 2>&1
if errorlevel 1 (
    echo Python이 설치되어 있지 않습니다. USB에서 설치합니다...
    if exist "%USB_ROOT%python_installer\python-3.11.9-amd64.exe" (
        echo.
        echo [중요] 설치 창에서 "Add python.exe to PATH" 를 반드시 체크하세요!
        echo.
        "%USB_ROOT%python_installer\python-3.11.9-amd64.exe"
        echo.
        echo 설치 완료 후 이 창을 닫고, 새 명령 프롬프트를 열어 다시 실행하세요.
    ) else (
        echo [오류] python_installer\ 폴더에 설치 파일이 없습니다.
        echo   인터넷 PC에서 usb_준비_인터넷PC에서실행.bat 을 먼저 실행하세요.
    )
    pause
    exit /b 1
)
echo [OK] Python 버전:
python --version
echo.

:: ── 2. 프로젝트 파일 복사 ─────────────────────────────────────────
echo [1/3] 프로젝트 파일 복사 중...
if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"
xcopy "%USB_ROOT%src"          "%INSTALL_DIR%\src\"  /E /I /Y /Q > nul
copy  "%USB_ROOT%config.yaml"  "%INSTALL_DIR%\config.yaml"  /Y > nul
copy  "%USB_ROOT%requirements.txt" "%INSTALL_DIR%\requirements.txt" /Y > nul
copy  "%USB_ROOT%run.bat"      "%INSTALL_DIR%\run.bat" /Y > nul
echo 복사 완료: %INSTALL_DIR%
echo.

:: ── 3. 가상환경 생성 ──────────────────────────────────────────────
echo [2/3] 가상환경 생성 중...
if not exist "%INSTALL_DIR%\venv" (
    python -m venv "%INSTALL_DIR%\venv"
    echo 가상환경 생성 완료.
) else (
    echo 가상환경이 이미 있습니다. 건너뜁니다.
)
echo.

:: ── 4. 패키지 오프라인 설치 ───────────────────────────────────────
echo [3/3] Python 패키지 설치 중 (인터넷 없이)...
call "%INSTALL_DIR%\venv\Scripts\activate.bat"

pip install ^
    --no-index ^
    --find-links="%USB_ROOT%packages" ^
    -r "%INSTALL_DIR%\requirements.txt"

if errorlevel 1 (
    echo.
    echo [오류] 패키지 설치 실패.
    echo   packages\ 폴더에 .whl 파일이 있는지 확인하세요.
    echo   인터넷 PC에서 usb_준비_인터넷PC에서실행.bat 을 다시 실행하세요.
    pause
    exit /b 1
)
echo 패키지 설치 완료.
echo.

:: ── 완료 ──────────────────────────────────────────────────────────
echo ================================================================
echo  설치 완료!
echo.
echo  설치 위치: %INSTALL_DIR%
echo.
echo  실행 방법 (명령 프롬프트에서):
echo    cd %INSTALL_DIR%
echo.
echo    run.bat --setup           Infinitt UI 좌표 기록 (최초 1회)
echo    run.bat --excel 목록.xlsx 배치 수집 시작
echo    run.bat                   F9 단축키 모드
echo.
echo  결과물 위치: %INSTALL_DIR%\output\
echo ================================================================
pause
