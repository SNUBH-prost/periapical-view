@echo off
chcp 65001 > nul
echo ================================================================
echo  오프라인 설치 스크립트 - 내부망 PC에서 실행하세요
echo ================================================================
echo.

set USB_ROOT=%~dp0
echo 설치 원본 경로: %USB_ROOT%
echo.

:: ── 1. Python 설치 확인 ──────────────────────────────────────────
python --version > nul 2>&1
if errorlevel 1 (
    echo Python이 설치되어 있지 않습니다.
    if exist "%USB_ROOT%python_installer\python-3.11.9-amd64.exe" (
        echo USB에서 Python 3.11 설치를 시작합니다...
        echo [중요] 설치 시 "Add python.exe to PATH" 체크박스를 반드시 선택하세요!
        "%USB_ROOT%python_installer\python-3.11.9-amd64.exe"
        echo.
        echo 설치 완료 후 이 창을 닫고 새 명령 프롬프트에서 다시 실행하세요.
    ) else (
        echo [오류] python_installer\ 폴더에 Python 설치 파일이 없습니다.
        echo USB_준비_인터넷PC에서실행.bat 을 먼저 인터넷 PC에서 실행했는지 확인하세요.
    )
    pause
    exit /b 1
)

python --version
echo.

:: ── 2. 설치 대상 폴더 설정 ───────────────────────────────────────
:: 현재 사용자 바탕화면에 설치
set INSTALL_DIR=%USERPROFILE%\Desktop\periapical-view

echo 설치 위치: %INSTALL_DIR%
if not exist "%INSTALL_DIR%" (
    xcopy "%USB_ROOT%." "%INSTALL_DIR%\" /E /I /H /Y /EXCLUDE:%USB_ROOT%xcopy_exclude.txt > nul 2>&1
    :: xcopy_exclude가 없으면 그냥 복사
    if errorlevel 1 (
        xcopy "%USB_ROOT%." "%INSTALL_DIR%\" /E /I /H /Y > nul
    )
    echo 소스 파일 복사 완료.
) else (
    echo 이미 설치된 폴더가 있습니다. 건너뜁니다.
)
echo.

:: ── 3. 가상환경 생성 ─────────────────────────────────────────────
echo [1/3] 가상환경 생성 중...
if not exist "%INSTALL_DIR%\venv" (
    python -m venv "%INSTALL_DIR%\venv"
    echo 가상환경 생성 완료.
) else (
    echo 가상환경이 이미 존재합니다.
)
echo.

:: ── 4. pip 패키지 오프라인 설치 ─────────────────────────────────
echo [2/3] pip 패키지 설치 중 (오프라인)...
call "%INSTALL_DIR%\venv\Scripts\activate.bat"

pip install --no-index --find-links="%USB_ROOT%packages" -r "%INSTALL_DIR%\requirements.txt"
if errorlevel 1 (
    echo [오류] 패키지 설치 실패. packages\ 폴더를 확인하세요.
    pause
    exit /b 1
)
echo 패키지 설치 완료.
echo.

:: ── 5. Playwright 브라우저 경로 설정 ────────────────────────────
echo [3/3] Playwright 브라우저 경로 설정 중...
if exist "%USB_ROOT%ms-playwright" (
    :: 브라우저 파일을 설치 폴더로 복사
    if not exist "%INSTALL_DIR%\ms-playwright" (
        xcopy "%USB_ROOT%ms-playwright" "%INSTALL_DIR%\ms-playwright\" /E /I /H /Y > nul
        echo 브라우저 파일 복사 완료.
    )
    :: 환경변수 설정 (현재 세션 + 영구)
    set PLAYWRIGHT_BROWSERS_PATH=%INSTALL_DIR%\ms-playwright
    setx PLAYWRIGHT_BROWSERS_PATH "%INSTALL_DIR%\ms-playwright" > nul
    echo Playwright 브라우저 경로 설정 완료.
) else (
    echo [주의] ms-playwright\ 폴더가 USB에 없습니다.
    echo 인터넷 PC에서 usb_준비_인터넷PC에서실행.bat 을 다시 실행하세요.
)
echo.

:: ── run.bat 생성 ─────────────────────────────────────────────────
(
echo @echo off
echo chcp 65001 ^> nul
echo set PLAYWRIGHT_BROWSERS_PATH=%INSTALL_DIR%\ms-playwright
echo call "%INSTALL_DIR%\venv\Scripts\activate.bat"
echo python "%INSTALL_DIR%\src\main.py" %%*
) > "%INSTALL_DIR%\run.bat"

:: ── 완료 ─────────────────────────────────────────────────────────
echo ================================================================
echo  설치 완료!
echo.
echo  1. 설치 위치: %INSTALL_DIR%
echo.
echo  2. config.yaml 설정:
echo     메모장으로 %INSTALL_DIR%\config.yaml 을 열어
echo     pacs.url, pacs.username, pacs.password 를 입력하세요.
echo.
echo  3. 실행 방법:
echo     %INSTALL_DIR%\run.bat --inspect     (UI 탐색/디버깅)
echo     %INSTALL_DIR%\run.bat --limit 5     (5건 테스트)
echo     %INSTALL_DIR%\run.bat               (전체 수집)
echo.
echo  4. 결과물 위치:
echo     %INSTALL_DIR%\output\
echo ================================================================
pause
