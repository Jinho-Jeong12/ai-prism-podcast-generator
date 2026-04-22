@echo off
chcp 65001 > nul
title FFmpeg 설치 중...

echo.
echo ┌─────────────────────────────────────────────────────┐
echo │         AI Prism 팟캐스트 생성기 - 초기 설치          │
echo └─────────────────────────────────────────────────────┘
echo.
echo  FFmpeg 를 설치합니다. 잠시만 기다려 주세요...
echo.

:: 현재 폴더 기준으로 설치
set "SCRIPT_DIR=%~dp0"
set "FFMPEG_DIR=%SCRIPT_DIR%ffmpeg"
set "FFMPEG_ZIP=%SCRIPT_DIR%ffmpeg_temp.zip"
set "FFMPEG_EXE=%FFMPEG_DIR%\bin\ffmpeg.exe"

if exist "%FFMPEG_EXE%" (
    echo  ✅ FFmpeg 가 이미 설치되어 있습니다!
    echo.
    goto :done
)

:: ffmpeg 다운로드 (GitHub 공식 릴리즈)
echo  📥 FFmpeg 다운로드 중...
powershell -Command "& {
    $url = 'https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip'
    $out = '%FFMPEG_ZIP%'
    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        Invoke-WebRequest -Uri $url -OutFile $out -UseBasicParsing
        Write-Host '  다운로드 완료!'
    } catch {
        Write-Host '  오류: ' + $_.Exception.Message
        exit 1
    }
}"

if not exist "%FFMPEG_ZIP%" (
    echo.
    echo  ❌ 다운로드에 실패했습니다.
    echo     인터넷 연결을 확인하고 다시 시도해 주세요.
    pause
    exit /b 1
)

echo  📦 압축 해제 중...
if not exist "%FFMPEG_DIR%" mkdir "%FFMPEG_DIR%"

powershell -Command "& {
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip = [System.IO.Compression.ZipFile]::OpenRead('%FFMPEG_ZIP%')
    $target = '%FFMPEG_DIR%'
    foreach ($entry in $zip.Entries) {
        $entryPath = $entry.FullName -replace '^[^/]+/', ''
        if ($entryPath -eq '') { continue }
        $destPath = Join-Path $target $entryPath
        $destDir = Split-Path $destPath -Parent
        if (-not (Test-Path $destDir)) { New-Item -ItemType Directory -Path $destDir | Out-Null }
        if (-not $entry.FullName.EndsWith('/')) {
            [System.IO.Compression.ZipFileExtensions]::ExtractToFile($entry, $destPath, $true)
        }
    }
    $zip.Dispose()
}"

del "%FFMPEG_ZIP%" 2>nul

if exist "%FFMPEG_EXE%" (
    echo.
    echo  ✅ FFmpeg 설치 완료!
) else (
    echo.
    echo  ❌ 압축 해제에 실패했습니다. 수동으로 설치해 주세요.
    pause
    exit /b 1
)

:done
echo.
echo  🚀 이제 '팟캐스트 생성기 실행.bat' 를 실행하세요!
echo.
pause
