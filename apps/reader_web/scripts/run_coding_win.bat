@echo off
CHCP 65001 >nul
cd /d "%~dp0\.."
echo Starting News Coding Suite...

if not exist ".venv" (
    echo [ERROR] Virtual environment not found! Please run 'scripts\install_win.bat' first.
    pause
    exit /b
)

call .venv\Scripts\activate
streamlit run coding_web.py
pause