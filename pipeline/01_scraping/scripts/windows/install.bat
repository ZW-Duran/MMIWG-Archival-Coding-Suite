@echo off
setlocal enabledelayedexpansion

:: Force navigate to the script's directory
cd /d "%~dp0"

echo [1/4] Checking Python environment...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Python not found. Downloading installer...
    curl -L -o python_installer.exe https://www.python.org/ftp/python/3.10.11/python-3.10.11-amd64.exe
    echo Installing Python (Please wait)...
    start /wait python_installer.exe /quiet InstallAllUsers=1 PrependPath=1
    del python_installer.exe
) else (
    echo Python is already installed.
)

echo [2/4] Installing Git and aria2 via winget...
winget install --id Git.Git -e --source winget
winget install --id qjk.aria2 -e --source winget

echo [3/4] Setting up Virtual Environment...
if not exist "venv" (
    python -m venv venv
)
call ".\venv\Scripts\activate"
python -m pip install --upgrade pip
pip install pymupdf requests

echo [4/4] Cloning repository into 'program' folder...
:: Create the folder if it doesn't exist
if not exist "program" mkdir "program"

:: Move into the folder to clone/pull
cd "program"
if not exist ".git" (
    echo Cloning fresh repository...
    git clone https://github.com/ZW-Duran/Tribe_News_Extractor-Filter.git .
) else (
    echo Repository exists. Pulling latest updates...
    git pull
)
:: Return to root
cd ..

echo.
echo Setup Complete! Code is located in the 'program' folder.
pause