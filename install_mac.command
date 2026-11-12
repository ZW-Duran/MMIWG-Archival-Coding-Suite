#!/bin/bash
# Navigate to the script's directory
cd "$(dirname "$0")"

echo "========================================================"
echo "  News Coding Suite - macOS Environment Installer"
echo "========================================================"
echo ""

# Check if Python 3 is installed
if ! command -v python3 &> /dev/null; then
    echo "[!] ERROR: Python 3 is not detected on your system."
    echo ""
    echo "Please install Python 3 using Homebrew:"
    echo "  brew install python"
    echo "Or download directly from python.org."
    echo ""
    read -p "Press Enter to exit..."
    exit 1
fi

echo "[√] Python 3 detected. Checking version..."
python3 --version

echo ""
echo "[1/3] Creating an isolated local virtual environment (.venv)..."
python3 -m venv .venv

echo "[2/3] Activating sandbox and upgrading pip..."
source .venv/bin/activate
python -m pip install --upgrade pip

echo "[3/3] Installing required packages (Streamlit, Google GenAI, etc.)..."
pip install -r ./requirements.txt

echo ""
echo "========================================================"
echo "  [SUCCESS] Environment setup complete!"
echo "  You can now close this window and double-click"
echo "  'run_mac.command' to launch the suite."
echo "========================================================"
read -p "Press Return to close this window..."