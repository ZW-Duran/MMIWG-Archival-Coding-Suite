import fitz  # PyMuPDF
import os
import re
from multiprocessing import Pool, cpu_count

SOURCE_DIR = "./original"
OUTPUT_DIR = "./relevant"

KEYWORDS_RE = re.compile(
    r"\b(women|woman|girl|female|violence|murder|victim|abuse|abusive|abused|Violence|native|indigenous|indian|MMIW|MMIWG|Missing and Murdered Indigenous Women|Missing and Murdered Indigenous Women and Girls)\b", 
    re.I
)

def process_single_pdf(rel_path):
    source_file_path = os.path.join(SOURCE_DIR, rel_path)
    output_file_path = os.path.join(OUTPUT_DIR, rel_path)
    
    output_subdir = os.path.dirname(output_file_path)
    os.makedirs(output_subdir, exist_ok=True)

    try:
        with fitz.open(source_file_path) as doc:
            matched_any = False
            
            for page in doc:
                page_text = page.get_text()
                matches = KEYWORDS_RE.findall(page_text)
                if matches:
                    matched_any = True
                    unique_matches = set(matches)
                    for word in unique_matches:
                        insts = page.search_for(word)
                        for inst in insts:
                            annot = page.add_highlight_annot(inst)
                            annot.set_colors(stroke=(0, 1, 1))
                            annot.update()

            if matched_any:
                doc.save(output_file_path, garbage=4, deflate=True, clean=True)
                return f"[*] Match & Saved: {rel_path}"
            else:
                return f"[ ] Irrelevant: {rel_path}"

    except Exception as e:
        return f"[!] Error {rel_path}: {str(e)}"

def main():
    all_files = []
    if not os.path.exists(SOURCE_DIR):
        print(f"Error: {SOURCE_DIR} Not Found.")
        return

    for root, _, files in os.walk(SOURCE_DIR):
        for f in files:
            if f.endswith(".pdf"):
                rel_path = os.path.relpath(os.path.join(root, f), SOURCE_DIR)
                all_files.append(rel_path)
    
    if not all_files:
        print("No PDF files found.")
        return

    cores = max(1, cpu_count() - 1)
    print(f"--- Filter Processing | Cores: {cores} | Tasks: {len(all_files)} ---")

    with Pool(processes=cores) as pool:
        for result in pool.imap_unordered(process_single_pdf, all_files):
            print(result)

    print("--- All tasks completed ---")

if __name__ == "__main__":
    main()