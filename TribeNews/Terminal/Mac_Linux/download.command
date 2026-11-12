#!/bin/bash

cd "$(dirname "$0")"

BASE_PATH="$(pwd)"
INPUT_FILE="$BASE_PATH/program/TribeNews/original/pdf_links.txt"
DOWNLOAD_DIR="$BASE_PATH/program/TribeNews/original"
RELEVANT_DIR="$BASE_PATH/program/TribeNews/relevant"
USER_AGENT="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

echo "Cleaning up old files (preserving pdf_links.txt)..."

# 1. 在 original 文件夹中：删除所有文件，但排除 pdf_links.txt
if [ -d "$DOWNLOAD_DIR" ]; then
    find "$DOWNLOAD_DIR" -type f ! -name 'pdf_links.txt' -delete
fi

# 2. 在 relevant 文件夹中：直接清空所有文件
if [ -d "$RELEVANT_DIR" ]; then
    rm -f "$RELEVANT_DIR"/*
fi

echo "Starting download process..."

# File check
if [ ! -f "$INPUT_FILE" ]; then
    echo "[ERROR] File not found: $INPUT_FILE"
    echo "Please ensure the links file is generated first."
    exit 1
fi

aria2c -i "$INPUT_FILE" \
--dir="$DOWNLOAD_DIR" \
--user-agent="$USER_AGENT" \
--max-connection-per-server=5 \
--split=5 \
--continue=true

echo ""
echo "Process completed. You can close this window."