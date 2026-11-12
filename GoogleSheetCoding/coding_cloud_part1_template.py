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
# CLOUD_MODEL_NAME = "gemini-3.1-flash-lite" 

# --- 2. 强约束 Prompt ---
SYSTEM_INSTRUCTION = """
You are an expert sociological research assistant reading newspaper archives. Your task is to perform qualitative text coding to identify specific semantic themes within the provided article.

CRITICAL INSTRUCTIONS:
1. For every variable you code as 1, you MUST provide the exact, verbatim sentence (evidence) from the text that justifies your choice.
2. If the text does not implicitly or explicitly discuss the theme based on the strict definitions below, set the value to 0 and leave the evidence string completely empty ("").
3. Keep the "evidence" string as short as possible—a single, precise verbatim sentence is preferred.

--- CODEBOOK & BOUNDARY DEFINITIONS ---
1. "mmiwg_mentioned": 1 if the text addresses the topic of Missing and Murdered Indigenous Women and Girls. This does NOT require a literal acronym match; if the article is clearly validating or discussing the crisis/phenomenon of missing/murdered Native individuals, it counts as 1.

2. "mmiwg_movement": 1 if the text references activism, community awareness, protests, marches, healing circles, policy advocacy, task forces, or red dress campaigns dedicated to addressing this crisis.

3. "specific_case": 1 if the text discusses a particular individual's disappearance or murder case. This includes anytime a specific victim is named, or specific incident details (like search efforts, police reporting, or crime scenes) are described.

4. "multiple_cases": 1 if the text acts as an empirical aggregator of the crisis—meaning it provides specific aggregated numbers/statistics, references database counts, or transitions into detailing/contrasting distinct, separate case histories.
   - Core Intent: This captures factual density about more than one case. Do NOT code as 1 for purely rhetorical, commemorative, or emotional expressions of collective grief (e.g., "so many loved ones who have been victims"). It must contain empirical or informational grouping, not just poetic or general acknowledgment of a widespread issue.
5. "legal_protection": 1 if the text references specific, concrete institutional mechanisms—such as passed or proposed statutes (e.g., "Senate Resolution 60", "Savanna's Act"), tribal sovereignty protocols, specific budgetary allocations for policing, jurisdictional rules, or active policy reform measures.
   - STRUCTURAL REQUIREMENT: The evidence must point to a tangible legal instrument, legislative bill, or a specific regulatory action taken/proposed by a government or tribal body.
   - CRITICAL EXCLUSION (HOPE VS. FACT): Do NOT code as 1 for statements expressing how the system *should* behave, personal hopes, future expectations, or moral calls to action (e.g., "I hope it will inform the criminal justice system's response..."). General quotes about the failure, needed awareness, or desired attitude of the justice system do NOT constitute concrete legal protection.
6. "family_friends_referenced": 1 if the text quotes, mentions, or references the victim's family members, relatives, loved ones, or close friends speaking out or being affected.
   - CRITICAL EXCLUSION: Do NOT code as 1 if an individual is described ONLY by their professional, political, or activist title (e.g., "event organizer", "advocate", "chief", "police spokesperson") without the text explicitly stating they have a personal, familial, or friendship bond with a victim. Do not infer personal relationships from social or activist roles.

7. "details_victim_life": 1 if the text provides a humanizing look into who the victim was as a living person *beyond* basic identification markers—such as their personal character, hobbies, career achievements, educational background, personal dreams, or roles within their family/community before the tragedy.
   - STRUCTURAL THRESHOLD: The text must detail their personality or life story. 
   - CRITICAL EXCLUSION: Do NOT code as 1 if the text only mentions basic demographic labels, standard identification markers, or chronological data necessary to describe the crime or a holiday (e.g., mentioning a victim's age, tribal affiliation, or their "birthday" to explain why a commemorative date was selected does NOT count as details of the victim's life).

8. "details_perpetrator": 1 if the text provides substantive information or updates about a specific suspect, person of interest, or perpetrator. This includes physical descriptions, concrete identities, arrest records, investigation progress targeting a specific suspect, trial updates, or court proceedings.
   - CRITICAL EXCLUSION: Do NOT code as 1 for generic, empty statements about the police simply looking for an unknown perpetrator (e.g., "police still finding perpetrator" or "no suspects have been named"). It must contain actual details or updates about a suspect/perpetrator's status or identity.

CONTEXTUAL ALIGNMENT TEST: When evaluating a sentence for a variable, you must ensure the *contextual meaning* of the sentence matches the variable's theme, not just the individual words. Ask yourself: "Is this sentence actually talking about the sociological theme defined, or is it just using a similar word in a completely different context (e.g., an election context vs. a criminal justice context)?" If it's a different context, you MUST code it as 0.

--- TWO-STEP VERIFICATION FILTER (COMPULSORY) ---
Before confirming any variable as 1, you must run this strict linguistic check:
- Step 1 (Noun/Verb Check): Does the sentence physically contain the mandatory nouns/actions required by the category (e.g., kinship nouns for variable 6, legal instruments for variable 5, empirical numbers for variable 4, human character traits for variable 7)?
- Step 2 (Context Check): Is the sentence free of the REJECTION CRITERIA listed under that category?
If the sentence fails either check, you MUST force the value to 0.

You must return your response PRECISELY in the following JSON format:
{
  "mmiwg_mentioned": 0,
  "mmiwg_movement": 0,
  "specific_case": 0,
  "multiple_cases": 0,
  "legal_protection": 0,
  "family_friends_referenced": 0,
  "details_victim_life": 0,
  "details_perpetrator": 0
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
        
        time.sleep(0)
        
        raw_response = response.text.strip()
        if not raw_response: return None
        
        try:
            start_idx = min([raw_response.find(x) for x in ['[', '{'] if raw_response.find(x) != -1], default=0)
            clean_text = raw_response[start_idx:]
            
            end_idx = max([clean_text.rfind(x) for x in [']', '}'] if clean_text.rfind(x) != -1], default=len(clean_text))
            clean_text = clean_text[:end_idx + 1]
            
            parsed_json = json.loads(clean_text)
            
            if isinstance(parsed_json, list) and len(parsed_json) > 0:
                parsed_json = parsed_json[0]
                
            return parsed_json
            
        except json.JSONDecodeError:
            print(f"   ⚠️ 行号 [{row_idx}] 遭遇 JSON 解析阻碍，启用精准正则抢救数据...")
            fallback_dict = {}
            keys = [
                "mmiwg_mentioned", "mmiwg_movement", "specific_case", "multiple_cases", 
                "legal_protection", "family_friends_referenced", "details_victim_life", "details_perpetrator"
            ]
            for k in keys:
                # 重写正则：针对扁平 JSON 提取数字 0 或 1
                val_pattern = rf'"{k}"\s*:\s*([01])'
                val_match = re.search(val_pattern, raw_response, re.IGNORECASE)
                val = int(val_match.group(1)) if val_match else 0
                fallback_dict[k] = val
            return fallback_dict
                
    except Exception as e:
        print(f"   ⚠️ Cloud API 异步通道报错 (行号 {row_idx}): {e}")
        time.sleep(0) 
        return None

# --- 3. 核心异步线程工作函数 ---
def process_single_row(task):
    idx, row = task
    pdf_path = locate_pdf_by_row_index(idx, OCRED_DIR)
    
    if not pdf_path:
        print(f"⏭️ 行号 [{idx}]: 未找到对应的 OCR 文件，跳过。")
        return idx, row, False

    print(f"🚀 [双线并发] 行号 [{idx}] ──> 分析中: {os.path.basename(pdf_path)}")

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
        
        # 动态确保行列表长度足够覆盖到 Y 列 (至少 25 个元素，即索引 0 到 24)
        while len(row) <= 24:
            row.append("")
            
        def safe_get_val(key_name):
            """安全提取单个整数 0 或 1"""
            val = analysis_lower.get(key_name.lower(), 0)
            try:
                return int(val)
            except:
                return 0

        # 按目标列索引精准填入：
        row[15] = safe_get_val("mmiwg_mentioned")           # P 列 (15)
        row[16] = safe_get_val("mmiwg_movement")            # Q 列 (16)
        row[17] = safe_get_val("specific_case")             # R 列 (17)
        row[18] = safe_get_val("multiple_cases")            # S 列 (18)
        row[19] = safe_get_val("legal_protection")          # T 列 (19)
        # row[20] (U列) 与 row[21] (V列) 保持原样，不作覆盖
        row[22] = safe_get_val("family_friends_referenced")  # W 列 (22)
        row[23] = safe_get_val("details_victim_life")        # X 列 (23)
        row[24] = safe_get_val("details_perpetrator")        # Y 列 (24)
        
        print(f"   └─ ✅ 行号 [{idx}] 数据结构化完成，已存入缓冲区。")
        return idx, row, True
        
    except Exception as e:
        print(f"   ❌ 行号 [{idx}] 回填发生错误: {e}")
        return idx, row, False

# --- 4. 主控制流 ---
def main():
    try:
        genai.configure(api_key=API_KEY_ODD)
    except Exception as e:
        print(f"❌ SDK 全局配置失败，请检查 API_KEY_ODD 是否正确: {e}")
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
        # 跳过表头或空行
        if idx == 1 or len(row) < 5:
            continue
            
        # 以 E 列 (索引 4) 是否有数据作为判别基础
        e_col_val = row[4].strip() if len(row) > 4 else ""
        
        # 以 P 列 (索引 15) 是否为空作为续传依据
        p_col_val = row[15].strip() if len(row) > 15 else ""
        
        if e_col_val and not p_col_val:
            todo_tasks.append((idx, row))

    print(f"⚡️ [任务分流] 过滤完毕，当前共有 {len(todo_tasks)} 行数据需要处理。")

    success_count = 0
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = executor.map(process_single_row, todo_tasks)
        
        for idx, updated_row, is_success in results:
            if is_success:
                success_count += 1
                # 实时落盘
                with open(OUTPUT_CSV_PATH, mode='w', encoding='utf-8', newline='') as f_write:
                    writer = csv.writer(f_write, quoting=csv.QUOTE_MINIMAL)
                    writer.writerows(rows)

    print("\n" + "="*40)
    print("🎉 Cloud API 编码结束！")
    print(f"   - 本次运行成功提取并写入: {success_count} 行")
    print("="*40)

if __name__ == "__main__":
    main()