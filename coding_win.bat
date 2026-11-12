@echo off
CHCP 65001 >nul
echo Starting News Coding Suite...

if not exist ".venv" (
    echo [ERROR] Virtual environment not found! Please run 'install_windows.bat' first.
    pause
    exit /b
)

call .venv\Scripts\activate
streamlit run coding.py
pause