#!/bin/bash
cd "$(dirname "$0")"

echo "Starting News Coding Suite..."

if [ ! -d ".venv" ]; then
    echo "[ERROR] Virtual environment not found! Please run 'install_mac.command' first."
    read -p "Press Enter to exit..."
    exit 1
fi

source .venv/bin/activate
streamlit run coding.py