#!/bin/bash

# 进入脚本所在目录
cd "$(dirname "$0")"

UPLOAD_DIR="./upload"
OCRED_DIR="./OCRed"
ORIGINAL_DIR="./original"
THREADS=8

mkdir -p "$OCRED_DIR" "$ORIGINAL_DIR"

# --- 1. OCR 核心逻辑 ---
process_file() {
    local file="$1"
    local UPLOAD_DIR="./upload"
    local OCRED_DIR="./OCRed"
    rel_path="${file#$UPLOAD_DIR/}"
    rel_dir=$(dirname "$rel_path")
    mkdir -p "$OCRED_DIR/$rel_dir"
    output_file="$OCRED_DIR/$rel_path"
    
    if [ ! -f "$output_file" ]; then
        echo "Processing: $rel_path"
        ocrmypdf --force-ocr --clean --deskew --jobs 1 "$file" "$output_file" > /dev/null 2>&1
    fi
}
export -f process_file

echo "正在进行 OCR (跳过已完成文件)..."
find "$UPLOAD_DIR" -type f -name "*.pdf" -print0 | xargs -0 -n 1 -P "$THREADS" -I {} bash -c 'process_file "{}"'

echo "---------------------------------------"
echo "开始按照目录结构合并 PDF..."

# --- 2. 改进后的合并逻辑 ---
# 遍历 OCRed 文件夹中的所有子文件夹
find "$OCRED_DIR" -type d -print0 | while IFS= read -r -d '' dir; do
    # 统计当前目录下 pdf 数量（不含子目录，不含已合并文件）
    count=$(find "$dir" -maxdepth 1 -type f -name "*.pdf" ! -name "* Press.pdf" | wc -l)
    
    if [ "$count" -gt 0 ]; then
        folder_name=$(basename "$dir")
        
        # 排除根目录 OCRed
        if [ "$folder_name" != "OCRed" ]; then
            
            # --- 改进点：计算目标 original 路径 ---
            # 获取相对于 OCRed 的路径，例如 "test/subfolder/target"
            rel_dir_path="${dir#$OCRED_DIR/}"
            # 提取第一层目录名，例如 "test"
            top_parent=$(echo "$rel_dir_path" | cut -d'/' -f1)
            
            # 定义该文件最终应该去的路径：./original/test/
            target_original_path="$ORIGINAL_DIR/$top_parent"
            mkdir -p "$target_original_path"
            
            combined_name="${folder_name} Press.pdf"
            echo "正在合并目录: $folder_name -> $target_original_path/"
            
            (
                cd "$dir" || exit
                # 使用 pdfunite 合并
                pdfunite *.pdf tmp_combined.pdf 2>/dev/null
                
                if [ -f "tmp_combined.pdf" ]; then
                    mv "tmp_combined.pdf" "$combined_name"
                    # 将合并后的文件复制到对应的 original 子文件夹中
                    # 注意这里用了绝对路径的逻辑，或者根据层级调整
                fi
            )
            
            # 最终移动并清理
            if [ -f "$dir/$combined_name" ]; then
                cp "$dir/$combined_name" "$target_original_path/"
                echo "✅ 已存至: $target_original_path/$combined_name"
            else
                echo "❌ 失败: $folder_name"
            fi
        fi
    fi
done

echo "所有任务已完成！"