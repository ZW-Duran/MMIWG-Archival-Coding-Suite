#!/bin/bash

# Ensure the script runs in the directory where it's located
cd "$(dirname "$0")"

# Self-elevation: Ask for sudo password
if [ "$EUID" -ne 0 ]; then
  echo "This setup requires administrative privileges."
  echo "Please enter your computer password when prompted:"
  sudo -v
fi

echo "[1/4] Checking Python environment..."
if ! command -v python3 &> /dev/null; then
    echo "Python3 not found. Installing via Homebrew..."
    if ! command -v brew &> /dev/null; then
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    fi
    brew install python
else
    echo "Python3 is already installed."
fi

echo "[2/4] Installing Git and aria2..."
if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    sudo apt-get update && sudo apt-get install -y git aria2
elif [[ "$OSTYPE" == "darwin"* ]]; then
    brew install git aria2
fi

echo "[3/4] Setting up Virtual Environment..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source "./venv/bin/activate"
pip install --upgrade pip
pip install pymupdf requests

echo "[4/4] Cloning repository into 'program' folder..."
mkdir -p "program"
cd "program"

if [ ! -d ".git" ]; then
    echo "Cloning fresh repository..."
    git clone https://github.com/ZW-Duran/Tribe_News_Extractor-Filter.git .
else
    echo "Repository exists. Pulling latest updates..."
    git pull
fi

echo ""
echo "Setup Complete! Code is located in the 'program' folder."