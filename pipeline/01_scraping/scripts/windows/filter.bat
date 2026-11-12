@echo off
setlocal enabledelayedexpansion

:: 1. Force navigate to the script's directory
cd /d "%~dp0"

echo [STEP 3] Starting the Filtering Process...

:: 2. Check and Activate venv
if exist "venv\Scripts\activate" (
    call "venv\Scripts\activate"
    cd program\TribeNews
    python filter.py
) else (
    echo [ERROR] Virtual environment not found. Please run install.bat first.
    pause
    exit /b
)

echo.
echo Filtering process finished.
pause