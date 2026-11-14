@echo off
cd /d "%~dp0"

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

powershell -command "Get-Clipboard | Out-File -FilePath 'program\TribeNews\temp_source.html' -Encoding utf8"

call ".\venv\Scripts\activate"
cd "program"

python simple_extract.py --file "temp_source.html"

del "temp_source.html"
pause