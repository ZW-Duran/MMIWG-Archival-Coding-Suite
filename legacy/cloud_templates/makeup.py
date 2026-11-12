import os
import csv
import json
import fitz  # PyMuPDF
import re
import time
import google.generativeai as genai
from concurrent.futures import ThreadPoolExecutor

# --- 1. 路径与 API 配置 ---
OUTPUT_CSV_PATH = "./list_coded.csv"  # 补救脚本直接对最终输出表进行补充
OCRED_DIR = "./ocred"

API_KEY_ODD = ""   # 负责奇数行
API_KEY_EVEN = "" # 负责偶数行
CLOUD_MODEL_NAME = "gemma-4-31b-it" 

# --- 2. 保持完全一致的 System Prompt ---
SYSTEM_INSTRUCTION = """
You are an expert sociological research assistant reading US newspaper archives. Your task is to perform qualitative and quantitative coding for ALL VICTIMS and SUSPECTS/PERPETRATORS referenced in the text.

CRITICAL INSTRUCTIONS:
1. GEOGRAPHIC BOUNDARY: Process ONLY victims and suspects within the USA. EXCLUDE any outside of the USA.
2. INDIVIDUALIZATION: Extract every distinct victim mentioned.
3. STATUS CATEGORIES:
- "murdered_or_missing": Victim was murdered, killed, disappeared, or is currently missing.
- "general_violence": Victim suffered non-fatal violence (e.g., physical assault, domestic violence, abuse, kidnapping survivor) but is NOT murdered or missing.
4. GENDER CATEGORIES: "male", "female", "nonbinary", "unknown".
5. RACE / TRIBAL AFFILIATION: Extract exact race/ethnicity and tribal affiliation if mentioned (e.g., "Navajo Nation", "Cherokee"). Use "Unknown" if not mentioned.
6. SUSPECTS / PERPETRATORS: 
- Count the total number of distinct suspects, persons of interest, or perpetrators referenced in the text (e.g., 0, 1, 2...).
- Extract the race/ethnicity of the suspect(s). If count is 0, leave race completely empty (""). If there are multiple suspects with different races, list all of them clearly separated by commas within the same string (e.g., "White, Native American").

--- OUTPUT FORMAT ---
1. Step-by-step list each victim identified, verifying their status, gender, race, tribal affiliation, and age.
2. At the VERY END, output EXACTLY ONE final JSON object containing the list of victims, the summary count matrix, and the suspect information.

Final JSON format:
{
  "victims": [
    {
      "name": "Victim Name or 'Unknown'",
      "race": "Victim Race or 'Unknown'",
      "tribal_affiliation": "Tribal Affiliation or 'Unknown'",
      "age": "Age or 'Unknown'",
      "gender": "female", 
      "status": "murdered_or_missing" 
    }
  ],
  "suspect_info": {
    "perpetrators_count": 0,
    "perpetrators_race": ""
  },
  "counts": {
    "mm_id_male": 0,
    "mm_id_female": 0,
    "mm_id_nonbinary": 0,
    "mm_gender_non_id": 0,
    "gv_id_male": 0,
    "gv_id_female": 0,
    "gv_id_nonbinary": 0,
    "gv_gender_non_id": 0
  }
}
"""

def locate_pdf_by_row_index(row_idx, directory):
    if not os.path.exists(directory): 
        return None
    target_filename = f"{str(row_idx).zfill(3)}.pdf"
    full_path = os.path.join(directory, target_filename)
    if os.path.exists(full_path):
        return full_path
    return None

def analyze_text_with_gemini(text, row_idx):
    prompt = f"{SYSTEM_INSTRUCTION}\n\nArticle Text:\n{text}"
    current_api_key = API_KEY_ODD if row_idx % 2 != 0 else API_KEY_EVEN
    
    try:
        genai.configure(api_key=current_api_key)
        model = genai.GenerativeModel(CLOUD_MODEL_NAME)
        
        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.0
            )
        )
        raw_response = response.text.strip()
        if not raw_response: 
            return None
        
        try:
            clean_text = re.sub(r'```json\s*|\s*```', '', raw_response).strip()
            start_idx = clean_text.find('{')
            end_idx = clean_text.rfind('}')
            
            if start_idx != -1 and end_idx != -1:
                json_str = clean_text[start_idx:end_idx + 1]
                return json.loads(json_str)
            else:
                return None
                
        except Exception as parse_e:
            print(f"   ⚠️ 行号 [{row_idx}] JSON 解析报错: {parse_e}")
            return None
                
    except Exception as e:
        print(f"   ⚠️ Cloud API 通道报错 (行号 {row_idx}): {e}")
        return None

# --- 3. 专属补救工作函数 (只填充 AK 和 AL) ---
def process_single_row_repair(task):
    idx, row = task
    pdf_path = locate_pdf_by_row_index(idx, OCRED_DIR)
    
    if not pdf_path:
        print(f"⏭️ 行号 [{idx}]: 未找到对应的 OCR 文件，跳过。")
        return idx, row, False

    print(f"🔍 [补救模式] 行号 [{idx}] ──> 正在补充提取嫌疑人信息 (AK/AL): {os.path.basename(pdf_path)}")

    try:
        doc = fitz.open(pdf_path)
        text_blocks = []
        for page in doc:
            blocks = page.get_text("blocks")
            for b in blocks:
                if b[4].strip():
                    text_blocks.append(b[4].strip())
        full_text = "\n\n".join(text_blocks)
        doc.close()
    except Exception as e:
        print(f"   ❌ 行号 [{idx}] 读取 PDF 失败: {e}")
        return idx, row, False

    if not full_text.strip():
        return idx, row, False

    analysis = analyze_text_with_gemini(full_text, idx)
    if not analysis:
        return idx, row, False

    try:
        suspect_info = analysis.get("suspect_info", {})
        
        # 确保行数组长度至少覆盖到 AL 列 (索引 37)
        while len(row) <= 37:
            row.append("")

        # 提取数量
        try:
            p_count = int(suspect_info.get("perpetrators_count", 0))
        except:
            p_count = 0
            
        row[36] = p_count # AK (索引 36)
        
        # 规则：如果人数为 0，race 强制留空；否则提取种族
        if p_count == 0:
            row[37] = "" # AL (索引 37)
        else:
            row[37] = str(suspect_info.get("perpetrators_race", "")) # AL

        print(f"   └─ ✅ 行号 [{idx}] 补救成功: 嫌疑人数={p_count}, 种族={row[37]}")
        time.sleep(2)
        return idx, row, True
        
    except Exception as e:
        print(f"   ❌ 行号 [{idx}] 数据回填错误: {e}")
        return idx, row, False

# --- 4. 主控制流 ---
def main():
    try:
        genai.configure(api_key=API_KEY_ODD)
    except Exception as e:
        print(f"❌ SDK 初始化失败，请检查 API_KEY_ODD: {e}")
        return

    if not os.path.exists(OUTPUT_CSV_PATH):
        print(f"❌ 未找到目标文件 {OUTPUT_CSV_PATH}，请确保主程序已经至少运行过一次并生成了结果表！")
        return

    print(f"🔄 正在加载已存在的结果表进行补救检查: {OUTPUT_CSV_PATH}")
    with open(OUTPUT_CSV_PATH, mode='r', encoding='utf-8', newline='') as f:
        rows = list(csv.reader(f))

    todo_tasks = []
    for idx, row in enumerate(rows, start=1):
        if idx == 1 or len(row) < 5:
            continue
            
        e_col_val = row[4].strip() if len(row) > 4 else ""
        
        # 核心检查条件：如果 E 列有文章，但 AK 列 (索引 36) 为空，则加入补救队列
        ak_col_val = row[36].strip() if len(row) > 36 else ""
        
        if e_col_val and ak_col_val == "":
            todo_tasks.append((idx, row))

    print(f"⚡️ [补救程序] 检查完毕，当前共有 {len(todo_tasks)} 行数据的 AK/AL 列需要补充填充。")

    if len(todo_tasks) == 0:
        print("🎉 太棒了，所有行的 AK/AL 列均已填满，无需补救！")
        return

    success_count = 0
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = executor.map(process_single_row_repair, todo_tasks)
        
        for idx, updated_row, is_success in results:
            if is_success:
                success_count += 1
                # 实时落盘，只更新对应的行
                with open(OUTPUT_CSV_PATH, mode='w', encoding='utf-8', newline='') as f_write:
                    writer = csv.writer(f_write, quoting=csv.QUOTE_MINIMAL)
                    writer.writerows(rows)

    print("\n" + "="*40)
    print("🎉 嫌疑人信息补救程序运行结束！")
    print(f"   - 本次成功补充填充: {success_count} 行")
    print("="*40)

if __name__ == "__main__":
    main()