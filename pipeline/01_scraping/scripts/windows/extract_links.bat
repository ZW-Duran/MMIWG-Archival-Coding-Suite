@echo off
setlocal enabledelayedexpansion

:: 1. Force navigate to the script's directory
cd /d "%~dp0"

:: 2. Show the reminder to the user
echo ============================================================
echo IMPORTANT: PLEASE CHECK THE URL
echo ============================================================
echo 1. Open "program\TribeNews\simple_extract.py" in Notepad or any editor.
echo 2. Go to Line 18.
echo 3. Ensure the URL matches the target website (e.g., https://ctsi.nsn.us).
echo.
echo Once you have verified the URL, press any key to start the extraction.
echo ============================================================
pause

:: 3. Activate venv and run the script
if exist "venv\Scripts\activate" (
    call "venv\Scripts\activate"
    cd program
    python simple_extract.py
) else (
    echo [ERROR] Virtual environment not found. Please run install.bat first.
    pause
)