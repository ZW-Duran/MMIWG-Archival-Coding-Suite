#!/bin/bash
cd "$(dirname "$0")"

# 颜色与样式定义
BOLD='\033[1m'
CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

clear
echo -e "${CYAN}${BOLD}"
echo "=========================================================="
echo "          OCRmyPDF Batch Processor (macOS)               "
echo "=========================================================="
echo -e "${NC}"

# ----------------- 1. 依赖自动化检查与安装 -----------------
echo -e "${BOLD}[1/3] Checking system dependencies...${NC}"

if ! command -v brew &> /dev/null; then
    echo -e "${YELLOW}⚠️ Homebrew package manager is missing.${NC}"
    echo "Installing Homebrew via official curl installer..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    eval "$(/opt/homebrew/bin/brew shellenv 2>/dev/null || /usr/local/bin/brew shellenv 2>/dev/null)"
fi

MISSING_DEPS=()
for dep in gs tesseract ocrmypdf parallel; do
    if ! command -v "$dep" &> /dev/null; then
        MISSING_DEPS+=("$dep")
    fi
done

if [ ${#MISSING_DEPS[@]} -gt 0 ]; then
    echo -e "${YELLOW}📦 Missing components: ${MISSING_DEPS[*]}${NC}"
    echo "Installing required dependencies via brew..."
    brew install ghostscript tesseract ocrmypdf parallel
fi

echo -e "${GREEN}✅ All core components verified.${NC}\n"

# ----------------- 2. CLI 交互界面配置 -----------------
echo -e "${BOLD}[2/3] Configuration Settings (Press ENTER to accept defaults)${NC}"

# 处理用户输入的路径（自动去除单双引号与末尾斜杠）
clean_path() {
    local p="$1"
    p=$(echo "$p" | sed "s/^['\"]//;s/['\"]$//")
    echo "$p"
}

# 1. Input directory
read -p "$(echo -e "${CYAN}Original PDF Directory [Default: ./original]: ${NC}")" INPUT_ORIGINAL
INPUT_ORIGINAL=$(clean_path "$INPUT_ORIGINAL")
UPLOAD_DIR="${INPUT_ORIGINAL:-./original}"

# 2. Output directory
read -p "$(echo -e "${CYAN}Output OCRed Directory [Default: ./ocred]: ${NC}")" INPUT_OCRED
INPUT_OCRED=$(clean_path "$INPUT_OCRED")
OCRED_DIR="${INPUT_OCRED:-./ocred}"

# 3. Threads
read -p "$(echo -e "${CYAN}Parallel Worker Threads [Default: 2]: ${NC}")" INPUT_THREADS
THREADS="${INPUT_THREADS:-2}"

# 确认参数
echo -e "\n${BOLD}Current Configuration:${NC}"
echo " ├── Original Path : $UPLOAD_DIR"
echo " ├── Output Path   : $OCRED_DIR"
echo " └── Concurrency   : $THREADS threads"
echo "----------------------------------------------------------"

mkdir -p "$UPLOAD_DIR" "$OCRED_DIR"

# ----------------- 3. 核心并发批处理 -----------------
echo -e "${BOLD}[3/3] Scanning tasks...${NC}"
export MAX_IMAGE_PIXELS=1000000000

find "$UPLOAD_DIR" -maxdepth 1 -name "*.pdf" -exec basename {} \; | sort > all_list.txt
find "$OCRED_DIR" -maxdepth 1 -name "*.pdf" ! -name "temp_*" -exec basename {} \; | sort > done_list.txt
comm -23 all_list.txt done_list.txt > pending_tasks.txt

TOTAL=$(wc -l < all_list.txt | tr -d ' ')
DONE_COUNT=$(wc -l < done_list.txt | tr -d ' ')
PENDING=$(wc -l < pending_tasks.txt | tr -d ' ')

echo "Original files in batch:  $TOTAL"
echo "Already completed:        $DONE_COUNT"
echo "Pending tasks to process: $PENDING"
echo "----------------------------------------------------------"

if [ "$PENDING" -eq 0 ]; then
    echo -e "${GREEN}✨ No pending files found. Everything is up to date!${NC}"
    rm -f all_list.txt done_list.txt pending_tasks.txt
    read -p "Press Enter to exit..."
    exit 0
fi

echo -e "${GREEN}🚀 Running parallel OCR processing...${NC}"

cat pending_tasks.txt | parallel --jobs "$THREADS" --keep-order --progress '
    file="'"$UPLOAD_DIR"'/{}"
    output_file="'"$OCRED_DIR"'/{}"
    temp_file="'"$OCRED_DIR"'/temp_{}"

    # Compress / standardize PDF prior to OCR
    gs -sDEVICE=pdfwrite -dCompatibilityLevel=1.4 -dPDFSETTINGS=/printer \
       -dColorImageResolution=300 -dGrayImageResolution=300 -dMonoImageResolution=300 \
       -dNOPAUSE -dBATCH -sOutputFile="$temp_file" "$file" > /dev/null 2>&1

    # Apply OCR
    ocrmypdf --force-ocr --clean "$temp_file" "$output_file" > /dev/null 2>&1
    rm -f "$temp_file"
    echo "Completed: {}"
'

# 校验结果
find "$OCRED_DIR" -maxdepth 1 -name "*.pdf" ! -name "temp_*" -exec basename {} \; | sort > done_list.txt
comm -23 all_list.txt done_list.txt > missing_files.txt
MISSING_COUNT=$(wc -l < missing_files.txt | tr -d ' ')

echo "----------------------------------------------------------"
if [ "$MISSING_COUNT" -gt 0 ]; then
    echo -e "${YELLOW}⚠️ Warning: $MISSING_COUNT file(s) failed to generate:${NC}"
    cat missing_files.txt
else
    echo -e "${GREEN}✅ All files processed and verified successfully!${NC}"
fi

# 清理元数据缓存
rm -f all_list.txt done_list.txt pending_tasks.txt missing_files.txt
echo -e "\n🎉 Finished! Files saved to: $OCRED_DIR"
read -p "Press Enter to close window..."