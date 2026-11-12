@echo off
setlocal enabledelayedexpansion
title OCRmyPDF Batch Processor (Windows)

echo ==========================================================
echo          OCRmyPDF Batch Processor (Windows)               
echo ==========================================================
echo.

:: 1. 检查 Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] Python is missing. Installing Python via winget...
    winget install Python.Python.3.11 --silent --accept-package-agreements --accept-source-agreements
    echo Please restart this script after Python installation completes.
    pause
    exit /b
)

:: 2. 检查 ocrmypdf
python -m ocrmypdf --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [*] Installing ocrmypdf python package...
    pip install ocrmypdf
)

:: 3. 检查 tesseract
where tesseract >nul 2>&1
if %errorlevel% neq 0 (
    echo [*] Tesseract OCR is missing. Installing via winget...
    winget install UB-Mannheim.TesseractOCR --silent --accept-package-agreements --accept-source-agreements
    set "PATH=%PATH%;C:\Program Files\Tesseract-OCR"
)

:: 4. 检查 ghostscript
where gswin64c >nul 2>&1
if %errorlevel% neq 0 (
    echo [*] Ghostscript is missing. Installing via winget...
    winget install ArtifexSoftware.Ghostscript --silent --accept-package-agreements --accept-source-agreements
    set "PATH=%PATH%;C:\Program Files\gs\gs10.03.0\bin"
)

echo [OK] Dependencies checked.
echo.
echo ----------------------------------------------------------
echo Configuration Settings (Press ENTER to accept defaults)
echo ----------------------------------------------------------

:: 用户交互输入
set "UPLOAD_DIR=./original"
set /p "INPUT_ORIGINAL=Original PDF Directory [Default: ./original]: "
if not "!INPUT_ORIGINAL!"=="" set "UPLOAD_DIR=!INPUT_ORIGINAL!"

set "OCRED_DIR=./ocred"
set /p "INPUT_OCRED=Output OCRed Directory [Default: ./ocred]: "
if not "!INPUT_OCRED!"=="" set "OCRED_DIR=!INPUT_OCRED!"

set "THREADS=2"
set /p "INPUT_THREADS=Parallel Worker Threads [Default: 2]: "
if not "!INPUT_THREADS!"=="" set "THREADS=!INPUT_THREADS!"

:: 去除用户复制路径时可能夹带的引号
set "UPLOAD_DIR=%UPLOAD_DIR:"=%"
set "OCRED_DIR=%OCRED_DIR:"=%"

echo.
echo Current Configuration:
echo  ├── Original Path : %UPLOAD_DIR%
echo  ├── Output Path   : %OCRED_DIR%
echo  └── Concurrency   : %THREADS% threads
echo ----------------------------------------------------------

:: 调用内置的并发执行逻辑
python -c "
import os, sys, subprocess
from concurrent.futures import ThreadPoolExecutor

upload_dir = r'''%UPLOAD_DIR%'''
ocred_dir = r'''%OCRED_DIR%'''
threads = int('%THREADS%')

os.makedirs(upload_dir, exist_ok=True)
os.makedirs(ocred_dir, exist_ok=True)

all_files = sorted([f for f in os.listdir(upload_dir) if f.lower().endswith('.pdf')])
done_files = set(os.listdir(ocred_dir))
pending = [f for f in all_files if f not in done_files]

print(f'Original files in batch:  {len(all_files)}')
print(f'Already completed:        {len(done_files)}')
print(f'Pending tasks to process: {len(pending)}')
print('-' * 58)

if not pending:
    print('✨ No pending files found. Everything is up to date!')
    sys.exit(0)

def process_file(filename):
    src = os.path.join(upload_dir, filename)
    dst = os.path.join(ocred_dir, filename)
    temp = os.path.join(ocred_dir, f'temp_{filename}')
    
    # 1. gs 压缩/预处理
    gs_cmd = ['gswin64c', '-sDEVICE=pdfwrite', '-dCompatibilityLevel=1.4', '-dPDFSETTINGS=/printer',
              '-dColorImageResolution=300', '-dGrayImageResolution=300', '-dMonoImageResolution=300',
              '-dNOPAUSE', '-dBATCH', f'-sOutputFile={temp}', src]
    subprocess.run(gs_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    # 2. ocrmypdf
    ocr_cmd = ['ocrmypdf', '--force-ocr', '--clean', temp, dst]
    res = subprocess.run(ocr_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    if os.path.exists(temp):
        os.remove(temp)
    
    if res.returncode == 0:
        print(f'Completed: {filename}')
    else:
        print(f'❌ Failed: {filename}')

with ThreadPoolExecutor(max_workers=threads) as executor:
    list(executor.map(process_file, pending))

print('\n🎉 Finished! Files saved to: ' + ocred_dir)
"

echo.
pause