#!/bin/bash

# 获取脚本所在的当前目录
cd "$(dirname "$0")"

TARGET_DIR="pdf"

echo "--- Starting Extraction (macOS/Linux) ---"

# 创建目标文件夹
mkdir -p "$TARGET_DIR"

# 使用 find 命令查找所有 pdf (排除目标文件夹本身)
# -iname 忽略大小写，-not -path 排除目标文件夹，-exec 执行复制
find . -type f -iname "*.pdf" -not -path "./$TARGET_DIR/*" -exec cp {} "./$TARGET_DIR/" \;

echo "--- Done! All PDFs are in ./$TARGET_DIR ---"