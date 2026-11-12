import os
import csv
import json
import fitz  # PyMuPDF
import ollama
import re
from concurrent.futures import ThreadPoolExecutor

# --- 1. 路径与本地 Ollama 配置 ---
CSV_PATH = "/Users/wangzhiyuan/Documents/SOC499A_TribeNews/program/program/GoogleSheetCoding/WA/list.csv"
OUTPUT_CSV_PATH = "/Users/wangzhiyuan/Documents/SOC499A_TribeNews/program/program/GoogleSheetCoding/WA/list_coded.csv"  # 实时更新与续传的目标文件
OCRED_DIR = "/Users/wangzhiyuan/Documents/SOC499A_TribeNews/program/program/GoogleSheetCoding/WA/ocred"
LOCAL_MODEL_NAME = "9bc" 

# --- 2. 强约束 Prompt 与期望的 JSON 结构 ---
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
  "mmiwg_mentioned": {"value": 0, "evidence": ""},
  "mmiwg_movement": {"value": 0, "evidence": ""},
  "specific_case": {"value": 0, "evidence": ""},
  "multiple_cases": {"value": 0, "evidence": ""},
  "legal_protection": {"value": 0, "evidence": ""},
  "family_friends_referenced": {"value": 0, "evidence": ""},
  "details_victim_life": {"value": 0, "evidence": ""},
  "details_perpetrator": {"value": 0, "evidence": ""}
}
"""

def locate_pdf_by_row_index(row_idx, directory):
    """
    根据 CSV 的绝对行号，去文件夹中寻找形如 '023.pdf' (带前导零的 3 位数字) 的文件
    """
    if not os.path.exists(directory): 
        return None
    
    # ──── 🛠️ 核心修复：使用 zfill(3) 将行号转化为固定 3 位的纯数字文件名 ────
    # 例如: 行号 4 -> '004.pdf', 行号 23 -> '023.pdf', 行号 105 -> '105.pdf'
    target_filename = f"{str(row_idx).zfill(3)}.pdf"
    
    # 拼接物理路径
    full_path = os.path.join(directory, target_filename)
    
    # 直接验证文件是否存在（比遍历整个文件夹速度更快、更稳定）
    if os.path.exists(full_path):
        return full_path
        
    return None

def analyze_text_with_ollama(text):
    prompt = f"{SYSTEM_INSTRUCTION}\n\nArticle Text:\n{text}"
    try:
        response = ollama.generate(
            model=LOCAL_MODEL_NAME,
            prompt=prompt,
            format="json", 
            options={
                "temperature": 0.0,  
                "num_ctx": 16384     
            }
        )
        raw_response = response['response'].strip()
        if not raw_response: return None
            
        try:
            return json.loads(raw_response)
        except json.JSONDecodeError:
            try:
                def clean_evidence(match):
                    content = match.group(1)
                    fixed_content = content.replace('"', "'")
                    return f'"evidence": "{fixed_content}"'
                repaired_response = re.sub(r'"evidence"\s*:\s*"(.*?)"', clean_evidence, raw_response, flags=re.DOTALL)
                return json.loads(repaired_response)
            except:
                fallback_dict = {}
                keys = ["mmiwg_mentioned", "mmiwg_movement", "specific_case", "multiple_cases", 
                        "legal_protection", "family_friends_referenced", "details_victim_life", "details_perpetrator"]
                for k in keys:
                    match = re.search(r'"' + k + r'"\s*:\s*\{\s*"value"\s*:\s*([01])', raw_response, re.IGNORECASE)
                    if match:
                        fallback_dict[k] = {"value": int(match.group(1)), "evidence": "Extracted via regex fallback"}
                    else:
                        fallback_dict[k] = {"value": 0, "evidence": ""}
                return fallback_dict
    except Exception as e:
        print(f"   ⚠️ 本地 Ollama 异步通道报错: {e}")
        return None

# --- 3. 核心异步线程工作函数 ---
def process_single_row(task):
    """单行任务的执行核，由线程池异步调用"""
    idx, row = task
    pdf_path = locate_pdf_by_row_index(idx, OCRED_DIR)
    
    if not pdf_path:
        print(f"⏭️ 行号 [{idx}]: 未找到对应的 OCR 文件，跳过。")
        return idx, row, False

    print(f"🚀 [双线并发中] 行号 [{idx}] ──> 正在分析: {os.path.basename(pdf_path)}")

    # 提取 PDF 文本
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
        print(f"   ❌ 行号 [{idx}] 读取 PDF 文本失败: {e}")
        return idx, row, False

    if not full_text.strip():
        print(f"   ⚠️ 行号 [{idx}] 警告：该 PDF 提取文本为空，跳过。")
        return idx, row, False

    # 投喂本地模型进行推理
    analysis = analyze_text_with_ollama(full_text)
    if not analysis:
        print(f"   ❌ 行号 [{idx}] 获取本地模型分析结果失败。")
        return idx, row, False

    # 原地解析字典并回填
    try:
        analysis_lower = {k.lower(): v for k, v in analysis.items()}
        
        def safe_get_value(key_name):
            data_block = analysis_lower.get(key_name.lower())
            if isinstance(data_block, dict):
                try: return int(data_block.get("value", 0))
                except: return 0
            elif isinstance(data_block, (int, str)):
                try: return int(data_block)
                except: return 0
            return 0

        row[13] = safe_get_value("mmiwg_mentioned")          # N 列
        row[14] = safe_get_value("mmiwg_movement")           # O 列
        row[15] = safe_get_value("specific_case")            # P 列
        row[16] = safe_get_value("multiple_cases")           # Q 列
        row[17] = safe_get_value("legal_protection")         # R 列
        row[23] = safe_get_value("family_friends_referenced") # X 列
        row[24] = safe_get_value("details_victim_life")       # Y 列
        row[25] = safe_get_value("details_perpetrator")       # Z 列
        
        print(f"   └─ ✅ 行号 [{idx}] 双线处理完成，已存入内存缓冲区。")
        return idx, row, True
        
    except Exception as e:
        print(f"   ❌ 行号 [{idx}] 回填发生错误: {e}")
        return idx, row, False

# --- 4. 主控制流 ---
def main():
    if os.path.exists(OUTPUT_CSV_PATH):
        current_csv_source = OUTPUT_CSV_PATH
        print(f"🔄 检测到历史数据，自动加载续传表: {current_csv_source}")
    else:
        current_csv_source = CSV_PATH
        print(f"📖 未检测到历史缓存，加载初始基础表: {current_csv_source}")

    with open(current_csv_source, mode='r', encoding='utf-8', newline='') as f:
        rows = list(csv.reader(f))

    total_rows = len(rows)
    print(f"📊 探测到大盘物理总行数: {total_rows} 行（含表头）")

    # 筛选出当前所有符合“断点续传”条件、急需处理的任务行
    todo_tasks = []
    for idx, row in enumerate(rows, start=1):
        if idx == 1 or len(row) < 14:
            continue
        d_col_val = row[3].strip()
        n_col_val = row[13].strip()
        
        if d_col_val and not n_col_val:
            todo_tasks.append((idx, row))

    print(f"⚡️ [任务分流] 过滤完毕，当前共有 {len(todo_tasks)} 行数据需要处理。")

    success_count = 0
    
    # 【核心重构：多线程双工流水线】
    # max_workers=2 强行锁定两个对话框并发，完美平摊给底层单实例 Ollama
    with ThreadPoolExecutor(max_workers=2) as executor:
        # 使用 executor.map 异步并发执行，返回的结果是有序的
        results = executor.map(process_single_row, todo_tasks)
        
        for idx, updated_row, is_success in results:
            if is_success:
                success_count += 1
                # rows 列表中的对象是引用，process_single_row 内部已经完成了 row[...] 的原地修改
                # 每一个线程处理完毕后，主线程立刻将其落盘，绝对防崩
                with open(OUTPUT_CSV_PATH, mode='w', encoding='utf-8', newline='') as f_write:
                    writer = csv.writer(f_write)
                    writer.writerows(rows)

    print("\n" + "="*40)
    print("🎉 本地双线并发自动化编码全部结束！")
    print(f"   - 本次运行成功原地编码: {success_count} 行数据")
    print(f"💾 所有的安全最终结果已实存在: {OUTPUT_CSV_PATH}")
    print("="*40)

if __name__ == "__main__":
    main()