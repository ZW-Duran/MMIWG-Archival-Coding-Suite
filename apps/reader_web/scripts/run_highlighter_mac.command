#!/bin/bash
cd "$(dirname "$0")/.."

echo "Starting Semantic Enhancement Reader (Highlighter)..."

if [ ! -d ".venv" ]; then
    echo "[ERROR] Virtual environment not found! Please run 'scripts/install_mac.command' first."
    read -p "Press Enter to exit..."
    exit 1
fi

source .venv/bin/activate
streamlit run semantic_highlighter.py
