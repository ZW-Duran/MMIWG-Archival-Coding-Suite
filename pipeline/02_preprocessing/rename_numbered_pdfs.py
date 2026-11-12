import os
import re

# 修改为你存放 PDF 的实际文件夹路径
target_dir = "/Users/wangzhiyuan/Documents/SOC499A_TribeNews/program/program/GoogleSheetCoding/NATIVE-NOTTRIBAL/OR/ocred"

def rename_pdfs(directory):
    # 遍历文件夹中的所有文件
    for filename in os.listdir(directory):
        # 匹配格式 highlighted_数字_document.pdf
        match = re.search(r'(\d+)_document\.pdf', filename)
        
        if match:
            num = int(match.group(1))
            # 补齐三位数字，格式化为 001.pdf
            new_name = f"{num:03d}.pdf"
            
            old_file = os.path.join(directory, filename)
            new_file = os.path.join(directory, new_name)
            
            # 执行重命名
            os.rename(old_file, new_file)
            print(f"Renamed: {filename} -> {new_name}")

if __name__ == "__main__":
    rename_pdfs(target_dir)