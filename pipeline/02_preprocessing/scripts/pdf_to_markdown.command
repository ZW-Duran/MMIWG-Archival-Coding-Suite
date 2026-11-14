#!/bin/bash

# 确保脚本运行时以脚本所在的文件夹为当前工作目录
cd "$(dirname "$0")"

# 1. 定义输入和输出文件夹路径
INPUT_DIR="./ocred"
OUTPUT_DIR="./md"

# 2. 自动创建输出文件夹（如果不存在的话）
mkdir -p "$OUTPUT_DIR"

# 3. 环境变量设置：抑制 PyTorch MPS 警告并优化回退机制
export PYTORCH_ENABLE_MPS_FALLBACK=1

echo "=================================================="
echo "🚀 开始批量转换 PDF -> MD （支持断电续传模式）"
echo "=================================================="

# 4. 循环遍历 ./ocred 目录下的所有 pdf 文件
for pdf_path in "$INPUT_DIR"/*.pdf; do
    # 检查是否有匹配的 pdf 文件，防止空循环
    [ -e "$pdf_path" ] || continue
    
    # 提取纯文件名（不含路径和扩展名），例如 "4_document"
    filename=$(basename "$pdf_path" .pdf)
    
    # 检查最终的目标 .md 文件是否已经在 ./md 文件夹中存在
    if [ -f "$OUTPUT_DIR/${filename}.md" ]; then
        echo "⏭️  跳过: ${filename}.md 已存在，无需重复转换。"
        echo "--------------------------------------------------"
        continue
    fi
    
    echo "📄 正在处理: ${filename}.pdf ..."
    
    # 执行 marker_single 转换
    # --disable_image_extraction 彻底禁用图片截取，加快速度
    marker_single "$pdf_path" --output_dir "$OUTPUT_DIR" --disable_image_extraction
    
    # 5. 后期清理（只抽取出 .md 文件，扔掉整个多余的文件夹与 json）
    target_subfolder="$OUTPUT_DIR/$filename"
    
    if [ -d "$target_subfolder" ]; then
        # 如果生成了子文件夹，把里面的 .md 文件提取到外层根目录下
        if [ -f "$target_subfolder/${filename}.md" ]; then
            mv "$target_subfolder/${filename}.md" "$OUTPUT_DIR/"
        fi
        # 彻底移除子文件夹（从而一并清除了 json 文件、坐标元数据等无用内容）
        rm -rf "$target_subfolder"
    fi
    
    echo "✅ 完成: ${filename}.md 已移动至 ${OUTPUT_DIR}/"
    echo "--------------------------------------------------"
done

echo "🎉 批量转换已全部完成！"
# 保持终端窗口打开，方便查看运行结果
bash