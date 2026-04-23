@echo off
chcp 65001 > nul
title AI Prism 팟캐스트 생성기

set "SCRIPT_DIR=%~dp0"
set "PYTHON_EXE="

echo.
echo  ┌─────────────────────────────────────────────────────┐
echo  │          AI Prism 팟캐스트 생성기                   │
echo  │              Seoul Economic Daily                   │
echo  └─────────────────────────────────────────────────────┘
echo.

:: ── Python 탐색 ──────────────────────────────────────────
for %%P in (
    "%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python310\python.exe"
    "C:\Python313\python.exe"
    "C:\Python312\python.exe"
    "C:\Python311\python.exe"
) do (
    if exist %%P (
        set "PYTHON_EXE=%%~P"
        goto :found_python
    )
)
for /f "delims=" %%i in ('where python 2^>nul') do (
    set "PYTHON_EXE=%%i"
    goto :found_python
)

echo  ❌ Python 이 설치되어 있지 않습니다.
echo     PowerShell 에 아래 명령을 붙여넣고 설치 후 다시 실행하세요:
echo     winget install Python.Python.3.13
echo.
pause
exit /b 1

:found_python
echo  ✅ Python: %PYTHON_EXE%

:: ── FFmpeg 탐색 (이미 설치된 경우) ──────────────────────
set "FFMPEG_OK=0"

:: 1) 로컬 폴더
if exist "%SCRIPT_DIR%ffmpeg\bin\ffmpeg.exe" (
    set "FFMPEG_OK=1"
    echo  ✅ FFmpeg: 로컬 폴더
    goto :ffmpeg_ready
)

:: 2) 시스템 PATH
where ffmpeg >nul 2>&1
if %errorlevel% == 0 (
    set "FFMPEG_OK=1"
    echo  ✅ FFmpeg: 시스템 PATH
    goto :ffmpeg_ready
)

:: ── FFmpeg 없음 → winget 으로 설치 시도 ─────────────────
echo.
echo  ℹ️  FFmpeg 가 없습니다. winget 으로 설치를 시도합니다.
echo     ^(Microsoft 공식 패키지 — 보안 정책 허용 가능성 높음^)
echo.

winget install Gyan.FFmpeg --accept-source-agreements --accept-package-agreements --silent
if %errorlevel% == 0 (
    :: winget 설치 후 PATH 재확인
    where ffmpeg >nul 2>&1
    if %errorlevel% == 0 (
        set "FFMPEG_OK=1"
        echo  ✅ FFmpeg: winget 설치 완료
        goto :ffmpeg_ready
    )
    :: winget 이 설치했지만 PATH 갱신 필요 → 새 세션에서 실행
    echo.
    echo  ✅ FFmpeg 설치 완료!
    echo     PATH 적용을 위해 이 창을 닫고 다시 실행해 주세요.
    echo.
    pause
    exit /b 0
)

:: ── winget 도 실패 → 안내 메시지 ────────────────────────
echo.
echo  ┌─────────────────────────────────────────────────────────────┐
echo  │  ⛔ 보안 정책으로 인해 FFmpeg 자동 설치에 실패했습니다.    │
echo  │                                                             │
echo  │  아래 방법 중 하나를 시도해 주세요:                        │
echo  │                                                             │
echo  │  방법 1) IT 팀에 FFmpeg 화이트리스트 요청                  │
echo  │    - 요청 문구: "Gyan.dev FFmpeg 서명된 빌드 허용 요청"    │
echo  │    - 다운로드: https://www.gyan.dev/ffmpeg/builds/         │
echo  │                                                             │
echo  │  방법 2) 관리자 계정으로 winget 설치 재시도                │
echo  │    PowerShell (관리자) 에서:                               │
echo  │    winget install Gyan.FFmpeg                              │
echo  │                                                             │
echo  │  방법 3) 이미 FFmpeg 가 있는 경우                          │
echo  │    ffmpeg.exe 를 아래 경로에 복사:                         │
echo  │    [이 폴더]\ffmpeg\bin\ffmpeg.exe                         │
echo  └─────────────────────────────────────────────────────────────┘
echo.
pause
exit /b 1

:ffmpeg_ready
echo.
echo  🎙 팟캐스트 생성기를 시작합니다...
echo.

"%PYTHON_EXE%" "%SCRIPT_DIR%팟캐스트_생성기.py"

if %errorlevel% neq 0 (
    echo.
    echo  ❌ 프로그램 실행 중 오류가 발생했습니다.
    pause
)
