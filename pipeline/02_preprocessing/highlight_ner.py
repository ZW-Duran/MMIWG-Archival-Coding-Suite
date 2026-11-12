import os
import glob
import fitz
import spacy
from multiprocessing import Pool, cpu_count
from tqdm import tqdm

# --- 配置 ---
INPUT_DIR = "./ocred"
OUTPUT_DIR = "./highlighted"
PROCESSES = 2

if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR)

def worker_task(file_path):
    """
    此函数仅在确认需要处理后才调用。
    """
    # 模型加载在判断任务有效性之后执行
    nlp = spacy.load("en_core_web_trf")
    file_name = os.path.basename(file_path)
    output_path = os.path.join(OUTPUT_DIR, file_name)

    try:
        doc = fitz.open(file_path)
        for page in doc:
            text = page.get_text()
            if not text.strip(): continue
            spacy_doc = nlp(text)
            for ent in spacy_doc.ents:
                if ent.label_ in ["GPE", "LOC", "PERSON"]:
                    color = (0, 1, 0) if ent.label_ in ["GPE", "LOC"] else (1, 1, 0)
                    insts = page.search_for(ent.text, quads=False)
                    for inst in insts:
                        if page.get_textbox(inst).strip() == ent.text:
                            annot = page.add_highlight_annot(inst)
                            annot.set_colors(stroke=color)
                            annot.update()
        doc.save(output_path, garbage=3, deflate=True)
        doc.close()
        return (file_name, "success")
    except Exception as e:
        return (file_name, f"error: {str(e)}")

def main():
    all_files = glob.glob(os.path.join(INPUT_DIR, "*.pdf"))
    
    # --- 关键逻辑：预先过滤任务 ---
    tasks_to_do = []
    skipped_count = 0
    
    for f in all_files:
        if os.path.exists(os.path.join(OUTPUT_DIR, os.path.basename(f))):
            skipped_count += 1
        else:
            tasks_to_do.append(f)

    if skipped_count > 0:
        print(f"已跳过 {skipped_count} 个已存在的文件。")
    
    if not tasks_to_do:
        print("没有需要处理的新任务。")
        return

    print(f"检测到 {len(tasks_to_do)} 个新任务，启动 {PROCESSES} 个进程处理...")
    
    results = {"success": 0, "error": 0}
    with Pool(processes=PROCESSES) as pool:
        for result_name, status in tqdm(pool.imap_unordered(worker_task, tasks_to_do), total=len(tasks_to_do)):
            results[status.split(":")[0]] += 1
            if status.startswith("error"):
                tqdm.write(f"❌ 失败 {result_name}: {status}")

    print(f"\n任务完成：成功 {results['success']}，失败 {results['error']}，已跳过 {skipped_count}。")

if __name__ == "__main__":
    main()