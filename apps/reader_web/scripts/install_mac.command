#!/bin/bash
# Navigate to apps/reader_web directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$APP_DIR" || exit 1

if [ ! -f "./requirements.txt" ]; then
    echo "[!] ERROR: requirements.txt not found in $APP_DIR"
    echo "Please make sure you downloaded/cloned the full repository."
    read -p "Press Return to exit..."
    exit 1
fi

echo "========================================================"
echo "  News Coding Suite - macOS Environment Installer"
echo "========================================================"
echo "Working directory: $APP_DIR"
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
echo "[1/4] Creating an isolated local virtual environment (.venv)..."
python3 -m venv .venv || { read -p "Failed to create .venv. Press Return to exit..."; exit 1; }

echo "[2/4] Activating sandbox and upgrading pip..."
source .venv/bin/activate || { read -p "Failed to activate .venv. Press Return to exit..."; exit 1; }
python -m pip install --upgrade pip || { read -p "Failed to upgrade pip. Press Return to exit..."; exit 1; }

echo "[3/4] Installing required packages (Streamlit, PyMuPDF, spaCy, etc.)..."
pip install -r ./requirements.txt || { read -p "Failed to install requirements. Press Return to exit..."; exit 1; }

echo "[4/4] Downloading spaCy transformer model (en_core_web_trf)..."
python -m spacy download en_core_web_trf || { read -p "Failed to download en_core_web_trf. Press Return to exit..."; exit 1; }

echo ""
echo "========================================================"
echo "  [SUCCESS] Environment setup complete!"
echo "  You can now close this window and double-click"
echo "  'run_highlighter_mac.command'."
echo "========================================================"
read -p "Press Return to close this window..."
