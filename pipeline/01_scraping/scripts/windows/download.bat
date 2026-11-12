@echo off
setlocal enabledelayedexpansion

cd /d "%~dp0"

set "INPUT_FILE=%~dp0program\TribeNews\original\pdf_links.txt"
set "DOWNLOAD_DIR=%~dp0program\TribeNews\original"
set "RELEVANT_DIR=%~dp0program\relevant"
set "USER_AGENT=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

echo Cleaning up old files (preserving pdf_links.txt)...

:: 1. 处理 original 文件夹
if exist "%INPUT_FILE%" (
    attrib +r "%INPUT_FILE%"
)
:: del /Q 不会删除具有只读属性的文件
if exist "%DOWNLOAD_DIR%" del /Q /F "%DOWNLOAD_DIR%\*.*" 2>nul
:: 恢复属性
if exist "%INPUT_FILE%" (
    attrib -r "%INPUT_FILE%"
)

:: 2. 处理 relevant 文件夹
if exist "%RELEVANT_DIR%" del /Q /F "%RELEVANT_DIR%\*.*" 2>nul

echo Starting download process...

if not exist "%INPUT_FILE%" (
    echo [ERROR] File not found: %INPUT_FILE%
    echo Please ensure the links file is generated first.
    pause
    exit /b
)

aria2c -i "%INPUT_FILE%" ^
--dir="%DOWNLOAD_DIR%" ^
--user-agent="%USER_AGENT%" ^
--max-connection-per-server=5 ^
--split=5 ^
--continue=true

echo.
echo Process completed. You can close this window.
pause