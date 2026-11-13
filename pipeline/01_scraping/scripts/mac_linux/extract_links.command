#!/bin/bash
cd "$(dirname "$0")"

echo "============================================================"
echo "IMPORTANT: PLEASE CHECK THE URL"
echo "============================================================"
echo "1. Open 'program/simple_extract.py' in a text editor."
echo "2. Go to Line 18."
echo "3. Ensure the URL matches the target website (e.g., https://ctsi.nsn.us)."
echo ""
echo "Once you have verified the URL, press [ENTER] to start."
echo "============================================================"
read -p ""

pbpaste > "./program/TribeNews/temp_source.html"

source "./venv/bin/activate"
cd "program"


python3 simple_extract.py --file "temp_source.html"


rm "temp_source.html"