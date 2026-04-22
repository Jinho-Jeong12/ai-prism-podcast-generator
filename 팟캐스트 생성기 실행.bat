@echo off
chcp 65001 > nul
title AI Prism 팟캐스트 생성기

set "SCRIPT_DIR=%~dp0"
set "PYTHON_EXE="

:: Python 설치 경로 탐색 (일반적인 위치들)
for %%P in (
    "C:\Users\novaj\AppData\Local\Programs\Python\Python313\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python310\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python39\python.exe"
    "C:\Python313\python.exe"
    "C:\Python312\python.exe"
    "C:\Python311\python.exe"
    "C:\Python310\python.exe"
) do (
    if exist %%P (
        set "PYTHON_EXE=%%~P"
        goto :found_python
    )
)

:: winget으로 설치된 Python
for /f "delims=" %%i in ('where python 2^>nul') do (
    set "PYTHON_EXE=%%i"
    goto :found_python
)

:: Python 없음 → 설치 안내
echo.
echo ┌─────────────────────────────────────────────────────┐
echo │            Python 이 설치되어 있지 않습니다             │
echo └─────────────────────────────────────────────────────┘
echo.
echo  Python 을 설치해야 합니다.
echo.
echo  방법 1) 자동 설치 (권장):
echo    아래 명령을 복사해서 PowerShell 에 붙여넣기 해주세요.
echo.
echo    winget install Python.Python.3.13
echo.
echo  방법 2) 직접 다운로드:
echo    https://www.python.org/downloads/
echo    (설치 시 "Add Python to PATH" 체크 필수!)
echo.
echo  설치 후 이 파일을 다시 실행해 주세요.
echo.
pause
exit /b 1

:found_python
echo  ✅ Python 발견: %PYTHON_EXE%

:: ffmpeg 확인
if not exist "%SCRIPT_DIR%ffmpeg\bin\ffmpeg.exe" (
    echo.
    echo  ⚠️  FFmpeg 가 설치되어 있지 않습니다.
    echo     'ffmpeg 설치하기.bat' 를 먼저 실행해 주세요!
    echo.
    pause
    exit /b 1
)

echo  ✅ FFmpeg 확인됨
echo.
echo  🎙 팟캐스트 생성기를 시작합니다...
echo.

"%PYTHON_EXE%" "%SCRIPT_DIR%팟캐스트_생성기.py"

if %errorlevel% neq 0 (
    echo.
    echo  ❌ 프로그램 실행 중 오류가 발생했습니다.
    pause
)
