@echo off
CHCP 65001 >nul
echo ========================================================
echo   News Coding Suite - Windows Environment Installer
echo ========================================================
echo.

echo [1/3] Creating virtual environment (.venv)...
python -m venv .venv
if %errorlevel% neq 0 (
    echo.
    echo [!] ERROR: Failed to create virtual environment.
    echo Please make sure Python is installed and added to PATH.
    pause
    exit /b
)

echo [2/3] Upgrading pip...
call .venv\Scripts\activate
python -m pip install --upgrade pip

echo [3/3] Installing required packages...
pip install -r requirements.txt

echo.
echo ========================================================
echo   [SUCCESS] Setup complete! You can now run coding_win.bat
echo ========================================================
pause