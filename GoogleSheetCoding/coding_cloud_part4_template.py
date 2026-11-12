import os
import csv
import json
import fitz  # PyMuPDF
import re
import time
import google.generativeai as genai
from concurrent.futures import ThreadPoolExecutor

# --- 1. 路径与 API 配置 ---
CSV_PATH = "./list.csv"
OUTPUT_CSV_PATH = "./list_coded.csv"  
OCRED_DIR = "./ocred"

API_KEY_ODD = ""   # 负责奇数行
API_KEY_EVEN = "" # 负责偶数行
CLOUD_MODEL_NAME = "gemma-4-31b-it" 
# CLOUD_MODEL_NAME = "gemini-3.5-flash-lite"

# --- 2. 程序 4 专属 System Prompt (受害者明细、嫌疑人信息与交叉汇总) ---
SYSTEM_INSTRUCTION = """
Victim Status (Missing, Murdered, General Victim)
You are an expert sociological research assistant reading US newspaper archives. Your task is to perform qualitative and quantitative coding for ALL VICTIMS and SUSPECTS/PERPETRATORS referenced in the text.

CRITICAL INSTRUCTIONS:
1. GEOGRAPHIC BOUNDARY: Process ONLY victims and suspects within the USA. EXCLUDE any outside of the USA.
2. INDIVIDUALIZATION: Extract every distinct victim mentioned.
3. STATUS CATEGORIES (Strictly Choose One of Three):
- "murdered": Victim was killed, found deceased as a result of homicide, or confirmed murdered.
- "missing": Victim disappeared, is unaccounted for, or is currently missing (fate/death unconfirmed).
- "general_victim": Victim suffered non-fatal violence (e.g., physical assault, domestic violence, sexual assault, survived abduction, abuse) and is neither murdered nor missing.
4. GENDER CATEGORIES: "male", "female", "nonbinary", "unknown".
5. RACE / TRIBAL AFFILIATION: Extract exact race/ethnicity and tribal affiliation if mentioned (e.g., "Navajo Nation", "Cherokee"). Use "Unknown" if not mentioned.
6. SUSPECTS / PERPETRATORS: 
- Count the total number of distinct suspects, persons of interest, or perpetrators referenced in the text (e.g., 0, 1, 2...).
- Extract the race/ethnicity of the suspect(s). If count is 0, leave race completely empty (""). If there are multiple suspects with different races, list all of them clearly separated by commas within the same string (e.g., "White, Native American").

--- OUTPUT FORMAT ---
1. Step-by-step list each victim identified, verifying their status ("murdered", "missing", or "general_victim"), gender, race, tribal affiliation, and age.
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
      "status": "murdered" 
    }
  ],
  "suspect_info": {
    "perpetrators_count": 0,
    "perpetrators_race": ""
  },
  "counts": {
    "murdered_id_male": 0,
    "murdered_id_female": 0,
    "murdered_id_nonbinary": 0,
    "murdered_gender_unknown": 0,
    "missing_id_male": 0,
    "missing_id_female": 0,
    "missing_id_nonbinary": 0,
    "missing_gender_unknown": 0,
    "gv_id_male": 0,
    "gv_id_female": 0,
    "gv_id_nonbinary": 0,
    "gv_gender_unknown": 0
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
            print(f"   ⚠️ 行号 [{row_idx}] 受害者 JSON 解析报错: {parse_e}")
            return None
                
    except Exception as e:
        print(f"   ⚠️ Cloud API 通道报错 (行号 {row_idx}): {e}")
        return None

# --- 3. 核心异步线程工作函数 ---
def process_single_row(task):
    idx, row = task
    pdf_path = locate_pdf_by_row_index(idx, OCRED_DIR)
    
    if not pdf_path:
        print(f"⏭️ 行号 [{idx}]: 未找到对应的 OCR 文件，跳过。")
        return idx, row, False

    print(f"🚀 行号 [{idx}] ──> 正在提取受害者、嫌疑人及交叉统计: {os.path.basename(pdf_path)}")

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
        counts = analysis.get("counts", {})
        victims = analysis.get("victims", [])
        suspect_info = analysis.get("suspect_info", {})
        
        # 确保行数组长度至少覆盖到 AV 列 (47) 以及明细列
        while len(row) <= 47:
            row.append("")

        # 1. 填入 AK 列 (索引 36) 和 AL 列 (索引 37) 的嫌疑人信息
        try:
            p_count = int(suspect_info.get("perpetrators_count", 0))
        except:
            p_count = 0
            
        row[36] = p_count # AK
        
        # 规则：如果人数为 0，race 强制留空；否则提取种族（多个会组合在同一个单元格）
        if p_count == 0:
            row[37] = "" # AL
        else:
            row[37] = str(suspect_info.get("perpetrators_race", "")) # AL

        # 2. 填入 AO ~ AV 列 (索引 40 到 47) 的汇总计数
        def safe_get(c_key):
            try: return int(counts.get(c_key, 0))
            except: return 0

        row[40] = safe_get("mm_id_male")          # AO (40)
        row[41] = safe_get("mm_id_female")        # AP (41)
        row[42] = safe_get("mm_id_nonbinary")     # AQ (42)
        row[43] = safe_get("mm_gender_non_id")    # AR (43)
        row[44] = safe_get("gv_id_male")          # AS (44)
        row[45] = safe_get("gv_id_female")        # AT (45)
        row[46] = safe_get("gv_id_nonbinary")     # AU (46)
        row[47] = safe_get("gv_gender_non_id")    # AV (47)

        # 3. 从 AW 列 (索引 48) 开始，每 6 列循环填入受害者明细
        base_offset = 48
        
        for i, v in enumerate(victims):
            v_start = base_offset + (i * 6)
            
            while len(row) < v_start + 6:
                row.append("")
                
            row[v_start]     = str(v.get("name", ""))
            row[v_start + 1] = str(v.get("race", ""))
            row[v_start + 2] = str(v.get("tribal_affiliation", ""))
            row[v_start + 3] = str(v.get("age", ""))
            row[v_start + 4] = str(v.get("gender", ""))
            row[v_start + 5] = str(v.get("status", ""))

        print(f"   └─ ✅ 行号 [{idx}] 已写入嫌疑人数据及 {len(victims)} 名受害者明细。")
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

    if os.path.exists(OUTPUT_CSV_PATH):
        current_csv_source = OUTPUT_CSV_PATH
        print(f"🔄 检测到历史数据，自动加载续传表: {current_csv_source}")
    else:
        current_csv_source = CSV_PATH
        print(f"📖 未检测到历史缓存，加载初始基础表: {current_csv_source}")

    with open(current_csv_source, mode='r', encoding='utf-8', newline='') as f:
        rows = list(csv.reader(f))

    todo_tasks = []
    for idx, row in enumerate(rows, start=1):
        if idx == 1 or len(row) < 5:
            continue
            
        e_col_val = row[4].strip() if len(row) > 4 else ""
        
        # 以 AO 列 (索引 40) 是否填有数据作为断点续传判断依据
        ao_col_val = row[40].strip() if len(row) > 40 else ""
        
        if e_col_val and ao_col_val == "":
            todo_tasks.append((idx, row))

    print(f"⚡️ [程序4] 过滤完毕，当前共有 {len(todo_tasks)} 行数据待处理。")

    success_count = 0
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = executor.map(process_single_row, todo_tasks)
        
        for idx, updated_row, is_success in results:
            if is_success:
                success_count += 1
                with open(OUTPUT_CSV_PATH, mode='w', encoding='utf-8', newline='') as f_write:
                    writer = csv.writer(f_write, quoting=csv.QUOTE_MINIMAL)
                    writer.writerows(rows)

    print("\n" + "="*40)
    print("🎉 程序 4 (受害者明细与交叉汇总) 运行结束！")
    print(f"   - 本次成功提取并落盘: {success_count} 行")
    print("="*40)

if __name__ == "__main__":
    main()