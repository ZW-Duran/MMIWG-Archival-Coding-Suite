import os
import csv
import json
import time
import fitz  # PyMuPDF
import re
import google.generativeai as genai
from concurrent.futures import ThreadPoolExecutor

# --- 1. 路径与 API 配置 ---
CSV_PATH = "./list.csv"
OUTPUT_CSV_PATH = "./list_coded.csv"  
OCRED_DIR = "./ocred"

API_KEY_ODD = ""   # 负责奇数行
API_KEY_EVEN = "" # 负责偶数行
CLOUD_MODEL_NAME = "gemma-4-31b-it" 
# CLOUD_MODEL_NAME = "gemini-3.1-flash-lite"

# --- 2. 程序 2 专属 System Prompt ---
SYSTEM_INSTRUCTION = """
You are an expert sociological research assistant reading US newspaper archives. Your task is to perform quantitative coding by COUNTING the number of distinct academics, subject matter experts, victim relatives/friends, and other ordinary people referenced or quoted in the text.

CRITICAL INSTRUCTIONS:
1. GEOGRAPHIC BOUNDARY: Count ONLY individuals located within or representing organizations within the USA. STRICTLY EXCLUDE any individuals outside of the USA.
2. COUNTING RULE: Return an integer count >= 0 for each category. Count distinct individual persons, NOT mentions/occurrences. If an individual is mentioned multiple times, count them ONCE.
3. MUTUAL EXCLUSIVITY: Each referenced individual must be assigned to EXACTLY ONE best-fitting category based on the priority rules below.

--- CATEGORY DEFINITIONS & HIERARCHY ---

1. "family_friends_referenced":
   - Definition: Count of surviving third-party individuals who are EXPLICITLY NAMED and identified as a direct family member, relative, partner, or close personal friend OF A SPECIFIC NAMED VICTIM/MISSING PERSON in the article.
   - MANDATORY ANCHOR: There MUST be a clear, named link connecting this person to a SPECIFIC named victim (e.g., "Jane Doe, mother of missing victim John Doe").
   - STRICT EXCLUSION 1 (THE VICTIM THEMSELVES):
     * DO NOT count the victim or missing/murdered person themselves (e.g., Webster George is a missing VICTIM, NOT a family/friend).
   - STRICT EXCLUSION 2 (GENERAL/RHOETORICAL STATEMENTS):
     * DO NOT count general speakers, activists, or event organizers who merely mention having "family losses" or "personal grief" in a vague or collective sense WITHOUT naming the specific victim they are related to (e.g., Paul Frank speaking generally about family losses belongs in "other_ordinary_people" or "other_experts", NOT here).

2. "academics":
   - Count of academic professionals affiliated with universities, colleges, or research institutions (e.g., professors, university scholars, researchers, deans, academic experts).

3. "other_experts":
   - Count of non-academic, professional subject-matter experts or service providers (e.g., MMIP task force members, victim services directors, social workers, professional advocates, policy analysts, independent researchers).
   - EXCLUSION: Do NOT count government officials, law enforcement officers, or legal professionals/attorneys here.

4. "other_ordinary_people":
   - Definition: Count of named or quoted everyday individuals who DO NOT fit into government, law enforcement, legal, academic, expert, or family/friend categories (e.g., eye-witnesses, rally attendees, local residents, community members expressing personal views).
   - STRICT EXCLUSION (PERPETRATORS / SUSPECTS):
     * DO NOT count perpetrators, suspects, persons of interest, or individuals who are arrested, charged, indicted, or convicted of crimes (e.g., individuals indicted for murder, accomplices, accessories). These belong to the perpetrator/suspect category in Step 3.
   - STRICT EXCLUSION (METADATA & BYLINES):
     * DO NOT count the author, writer, or reporter who WROTE THIS NEWSPAPER ARTICLE (e.g., "By John Smith", "Staff Writer John Smith").
     * DO NOT count newspaper editors, publishers, or staff listed in newspaper headers, mastheads, or footers.
     * DO NOT count generic unnamed crowds (e.g., "the crowd cheered").
   - INCLUSION (CONTEXTUAL SUBJECTS):
     * DO include authors, writers, or editors who are explicitly MENTIONED IN THE TEXT AS SUBJECTS of the article (e.g., a book author being interviewed or quoted about an event).

--- OUTPUT FORMAT ---
1. First, step-by-step list the named people/titles identified for each category and verify their eligibility and priority.
2. At the VERY END of your response, output EXACTLY ONE final JSON object containing the definitive counts. Do not output multiple JSON blocks.

Final JSON format:
{
  "academics": 0,
  "other_experts": 0,
  "family_friends_referenced": 0,
  "other_ordinary_people": 0
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
        
        # 🛠️ 严格配置 temperature=0.0 保证输出确定性
        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.0
            )
        )
        
        raw_response = response.text.strip()
        if not raw_response: 
            return None
        
        # 🛠️ 更加健壮的 JSON 抓取：清洗 Markdown 标记并定位末尾大括号
        try:
            clean_text = re.sub(r'```json\s*|\s*```', '', raw_response).strip()
            start_idx = clean_text.rfind('{')
            end_idx = clean_text.rfind('}')
            
            if start_idx != -1 and end_idx != -1:
                json_str = clean_text[start_idx:end_idx + 1]
                return json.loads(json_str)
            else:
                raise ValueError("No JSON braces found")
                
        except Exception as parse_e:
            print(f"   ⚠️ 行号 [{row_idx}] JSON 解析失败，启动正则抢救模式...")
            fallback_dict = {}
            keys = ["academics", "other_experts", "family_friends_referenced", "other_ordinary_people"]
            for k in keys:
                val_pattern = rf'"{k}"\s*:\s*([0-9]+)'
                matches = re.findall(val_pattern, raw_response, re.IGNORECASE)
                val = int(matches[-1]) if matches else 0
                fallback_dict[k] = val
            return fallback_dict
                
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

    print(f"🚀 行号 [{idx}] ──> 正在提取专家/亲友/普通人计数: {os.path.basename(pdf_path)}")

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
        analysis_lower = {k.lower(): v for k, v in analysis.items()}
        
        # 动态扩展列数，确保能够写入到 AN 列 (索引 39)
        while len(row) <= 39:
            row.append("")
            
        def safe_get_count(key_name):
            val = analysis_lower.get(key_name.lower(), 0)
            try:
                if isinstance(val, dict): 
                    val = val.get("count", 0)
                return int(val)
            except:
                return 0

        # 按精准列索引回填数据 (AI, AJ, AM, AN)
        row[34] = safe_get_count("academics")                 # AI 列 (34)
        row[35] = safe_get_count("other_experts")             # AJ 列 (35)
        row[38] = safe_get_count("family_friends_referenced") # AM 列 (38)
        row[39] = safe_get_count("other_ordinary_people")     # AN 列 (39)
        
        print(f"   └─ ✅ 行号 [{idx}] 数据已成功填入 AI, AJ, AM, AN 列。")
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
        
        # 以 AI 列 (索引 34) 是否填有数据作为断点续传判断依据
        ai_col_val = row[34].strip() if len(row) > 34 else ""
        
        if e_col_val and ai_col_val == "":
            todo_tasks.append((idx, row))

    print(f"⚡️ [程序2] 过滤完毕，当前共有 {len(todo_tasks)} 行数据待处理。")

    success_count = 0
    with ThreadPoolExecutor(max_workers=1) as executor:
        results = executor.map(process_single_row, todo_tasks)
        
        for idx, updated_row, is_success in results:
            if is_success:
                success_count += 1
                with open(OUTPUT_CSV_PATH, mode='w', encoding='utf-8', newline='') as f_write:
                    writer = csv.writer(f_write, quoting=csv.QUOTE_MINIMAL)
                    writer.writerows(rows)

    print("\n" + "="*40)
    print("🎉 程序 2 (学者/专家/亲友/普通人计数) 运行结束！")
    print(f"   - 本次成功提取并落盘: {success_count} 行")
    print("="*40)

if __name__ == "__main__":
    main()