import multiprocessing
import sys
from pathlib import Path

if __name__ == "__main__":
    multiprocessing.freeze_support()

if not getattr(sys, "frozen", False):
    _REPO_ROOT = str(Path(__file__).resolve().parents[2])
    if _REPO_ROOT not in sys.path:
        sys.path.insert(0, _REPO_ROOT)

import os
import re
import csv
import json
import fitz  # PyMuPDF
import google.generativeai as genai
from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QProgressBar, QTextEdit,
    QFileDialog, QComboBox, QGroupBox, QFrame
)

from core.pdf_utils import clean_path, read_source_file_content

def locate_source_file_by_row_index(row_idx: int, directory: str) -> str:
    if not directory or not os.path.exists(directory):
        return None
    target_prefix = str(row_idx).zfill(3).lower()
    target_txt = f"{target_prefix}.txt"
    target_pdf = f"{target_prefix}.pdf"

    found_pdf = None
    for root, _, files in os.walk(directory):
        files_lower = {f.lower(): f for f in files}
        if target_txt in files_lower:
            return os.path.join(root, files_lower[target_txt])
        if target_pdf in files_lower and not found_pdf:
            found_pdf = os.path.join(root, files_lower[target_pdf])

    return found_pdf

# ==============================================================================
# 2. System Instructions & Model Config
# ==============================================================================
from core.prompts import BATCH_PROMPTS as PROMPTS

MODEL_OPTIONS_PER_PART = {
    "Part 1": ["gemma-4-31b-it", "gemini-3.1-flash-lite", "gemini-3.5-flash-lite", "gemma-4-26b-it"],
    "Part 2": ["gemma-4-31b-it", "gemini-3.1-flash-lite", "gemini-3.5-flash-lite"],
    "Part 3": ["gemma-4-31b-it", "gemini-3.1-flash-lite", "gemini-3.5-flash-lite"],
    "Part 4": ["gemini-3.5-flash-lite", "gemma-4-31b-it", "gemini-3.1-flash-lite"],
}

DEFAULT_MODEL_PER_PART = {
    "Part 1": "gemma-4-31b-it",
    "Part 2": "gemma-4-31b-it",
    "Part 3": "gemma-4-31b-it",
    "Part 4": "gemini-3.5-flash-lite",
}

# ==============================================================================
# 3. AI 分析与逻辑处理
# ==============================================================================
def analyze_text_with_gemini(text: str, row_idx: int, system_instruction: str, model_name: str, api_key_1: str, api_key_2: str) -> dict:
    prompt = f"{system_instruction}\n\nArticle Text:\n{text}"

    if not api_key_2 or not api_key_2.strip():
        current_api_key = api_key_1.strip()
    else:
        current_api_key = api_key_1.strip() if row_idx % 2 != 0 else api_key_2.strip()

    try:
        genai.configure(api_key=current_api_key)
        model = genai.GenerativeModel(model_name)

        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(temperature=0.0)
        )

        raw_response = response.text.strip() if response and response.text else ""
        if not raw_response:
            return None

        clean_text = re.sub(r'```json\s*|\s*```', '', raw_response).strip()
        start_idx = clean_text.find('{')
        end_idx = clean_text.rfind('}')

        if start_idx != -1 and end_idx != -1 and end_idx >= start_idx:
            json_str = clean_text[start_idx:end_idx + 1]
            return json.loads(json_str)
        return None
    except Exception:
        try:
            if "mmiwg_mentioned" in system_instruction:
                fallback = {}
                keys = ["mmiwg_mentioned", "mmiwg_movement", "specific_case", "multiple_cases",
                        "legal_protection", "family_friends_referenced", "details_victim_life", "details_perpetrator"]
                for k in keys:
                    m = re.search(rf'"{k}"\s*:\s*([01])', raw_response, re.IGNORECASE)
                    fallback[k] = int(m.group(1)) if m else 0
                return fallback
        except Exception:
            pass
        return None

def process_single_row(task):
    idx, row, part, model_name, ocred_dir, key1, key2 = task
    source_path = locate_source_file_by_row_index(idx, ocred_dir)

    if not source_path:
        return idx, row, False, f"⏭️ Row [{idx}]: No matching TXT or PDF file found ({idx:03d}.txt / {idx:03d}.pdf), skipped."

    ext_name = os.path.splitext(source_path)[1].upper()
    try:
        full_text = read_source_file_content(source_path)
    except Exception as e:
        return idx, row, False, f"❌ Row [{idx}] Failed to read file [{ext_name}]: {e}"

    if not full_text.strip():
        return idx, row, False, f"⚠️ Row [{idx}] Empty text in [{ext_name}], skipped."

    system_instruction = PROMPTS[part]
    analysis = analyze_text_with_gemini(full_text, idx, system_instruction, model_name, key1, key2)
    if not analysis:
        return idx, row, False, f"⚠️ Row [{idx}] AI analysis failed or returned non-JSON format."

    try:
        analysis_lower = {k.lower(): v for k, v in analysis.items()}

        def safe_get_val(key_name, default=0):
            val = analysis_lower.get(key_name.lower(), default)
            try:
                if isinstance(val, dict):
                    val = val.get("count", val.get("value", default))
                return int(val)
            except Exception:
                return default

        if part == "Part 1":
            while len(row) <= 24: row.append("")
            row[15] = safe_get_val("mmiwg_mentioned")
            row[16] = safe_get_val("mmiwg_movement")
            row[17] = safe_get_val("specific_case")
            row[18] = safe_get_val("multiple_cases")
            row[19] = safe_get_val("legal_protection")
            row[22] = safe_get_val("family_friends_referenced")
            row[23] = safe_get_val("details_victim_life")
            row[24] = safe_get_val("details_perpetrator")

        elif part == "Part 2":
            while len(row) <= 33: row.append("")
            row[29] = safe_get_val("tribe_gov_officials")
            row[30] = safe_get_val("state_local_gov_officials")
            row[31] = safe_get_val("federal_gov_officials")
            row[32] = safe_get_val("law_enforcement")
            row[33] = safe_get_val("legal_professionals")

        elif part == "Part 3":
            while len(row) <= 39: row.append("")
            row[34] = safe_get_val("academics")
            row[35] = safe_get_val("other_experts")
            row[38] = safe_get_val("family_friends_referenced")
            row[39] = safe_get_val("other_ordinary_people")

        elif part == "Part 4":
            counts = analysis.get("counts", {})
            victims = analysis.get("victims", [])
            suspect_info = analysis.get("suspect_info", {})

            while len(row) <= 47: row.append("")

            try: p_count = int(suspect_info.get("perpetrators_count", 0))
            except Exception: p_count = 0
            row[36] = p_count
            row[37] = "" if p_count == 0 else str(suspect_info.get("perpetrators_race", ""))

            def safe_get_count(c_key, alt_key=""):
                c_val = counts.get(c_key, counts.get(alt_key, 0))
                try: return int(c_val)
                except Exception: return 0

            row[40] = safe_get_count("murdered_id_male", "mm_id_male")
            row[41] = safe_get_count("murdered_id_female", "mm_id_female")
            row[42] = safe_get_count("murdered_id_nonbinary", "mm_id_nonbinary")
            row[43] = safe_get_count("murdered_gender_unknown", "mm_gender_non_id")
            row[44] = safe_get_count("missing_id_male", "gv_id_male")
            row[45] = safe_get_count("missing_id_female", "gv_id_female")
            row[46] = safe_get_count("missing_id_nonbinary", "gv_id_nonbinary")
            row[47] = safe_get_count("missing_gender_unknown", "gv_gender_non_id")

            base_offset = 48
            for i, v in enumerate(victims):
                v_start = base_offset + (i * 6)
                while len(row) < v_start + 6: row.append("")
                row[v_start]     = str(v.get("name", ""))
                row[v_start + 1] = str(v.get("race", ""))
                row[v_start + 2] = str(v.get("tribal_affiliation", ""))
                row[v_start + 3] = str(v.get("age", ""))
                row[v_start + 4] = str(v.get("gender", ""))
                row[v_start + 5] = str(v.get("status", ""))

        return idx, row, True, f"✅ Row [{idx}] [{ext_name}]: Analysis complete and encoded."
    except Exception as e:
        return idx, row, False, f"❌ Row [{idx}] Backfill error: {e}"

class BatchCodingWorker(QThread):
    progress = Signal(int, int)
    log_signal = Signal(str)
    status_signal = Signal(str, str)  # text, color
    finished = Signal()

    def __init__(self, csv_p, out_csv_p, ocred_dir_p, part, model_name, start_r_val, key1, key2):
        super().__init__()
        self.csv_p = csv_p
        self.out_csv_p = out_csv_p
        self.ocred_dir_p = ocred_dir_p
        self.part = part
        self.model_name = model_name
        self.start_r_val = start_r_val
        self.key1 = key1
        self.key2 = key2

    def run(self):
        self.log_signal.emit(f"🚀 Initializing Batch Process for [{self.part}] using [{self.model_name}]...")
        self.log_signal.emit(f"📖 CSV Input: {self.csv_p}")
        self.log_signal.emit(f"💾 CSV Output: {self.out_csv_p}")
        self.log_signal.emit(f"📂 Source Folder: {self.ocred_dir_p} (TXT Preferred over PDF, All Depths)")
        self.log_signal.emit(f"📍 Start Row Index: {self.start_r_val}")

        source_csv = self.out_csv_p if os.path.exists(self.out_csv_p) else self.csv_p
        try:
            with open(source_csv, mode='r', encoding='utf-8', newline='') as f:
                rows = list(csv.reader(f))
        except UnicodeDecodeError:
            with open(source_csv, mode='r', encoding='gbk', errors='ignore', newline='') as f:
                rows = list(csv.reader(f))

        todo_tasks = []
        for idx, row in enumerate(rows, start=1):
            if idx < self.start_r_val or idx == 1 or len(row) < 4:
                continue

            e_col_val = row[4].strip() if len(row) > 4 else ""

            check_val = ""
            if self.part == "Part 1":
                check_val = row[15].strip() if len(row) > 15 else ""
            elif self.part == "Part 2":
                check_val = row[29].strip() if len(row) > 29 else ""
            elif self.part == "Part 3":
                check_val = row[34].strip() if len(row) > 34 else ""
            elif self.part == "Part 4":
                check_val = row[40].strip() if len(row) > 40 else ""

            if e_col_val and check_val == "":
                todo_tasks.append((idx, row, self.part, self.model_name, self.ocred_dir_p, self.key1, self.key2))

        total_tasks = len(todo_tasks)
        self.log_signal.emit(f"⚡️ [Task Filtering] Found {total_tasks} rows requiring coding analysis.")

        if total_tasks == 0:
            self.log_signal.emit("🎉 No pending tasks found! All rows are already encoded or skipped.")
            self.status_signal.emit("🎉 No pending tasks found.", "green")
            self.finished.emit()
            return

        completed_count = 0
        success_count = 0

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = executor.map(process_single_row, todo_tasks)
            for idx, updated_row, is_ok, msg in results:
                completed_count += 1
                if is_ok:
                    success_count += 1
                    with open(self.out_csv_p, mode='w', encoding='utf-8', newline='') as f_write:
                        writer = csv.writer(f_write, quoting=csv.QUOTE_MINIMAL)
                        writer.writerows(rows)

                self.log_signal.emit(msg)
                self.progress.emit(completed_count, total_tasks)
                self.status_signal.emit(f"Processing: {completed_count}/{total_tasks} rows...", "blue")

        self.log_signal.emit("=" * 45)
        self.log_signal.emit(f"🎉 Batch Processing Complete! Successfully saved {success_count} rows to: {self.out_csv_p}")
        self.status_signal.emit(f"🎉 Complete! Processed {success_count} rows.", "green")
        self.finished.emit()

class BatchCodingWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("📰 News Text Quantitative Batch Coding Tool")
        self.resize(820, 740)

        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(12)

        # Header
        title_lbl = QLabel("📰 News Text Quantitative Batch Coding Tool")
        title_lbl.setStyleSheet("font-size: 20px; font-weight: bold;")
        sub_lbl = QLabel("Batch process archival documents across all directory depths (TXT preferred over PDF).")
        sub_lbl.setStyleSheet("color: #666666;")
        main_layout.addWidget(title_lbl)
        main_layout.addWidget(sub_lbl)

        # Notice Banner
        banner = QFrame()
        banner.setStyleSheet("""
            QFrame {
                background-color: #FFEBEE;
                border: 2px solid #EF5350;
                border-radius: 6px;
                padding: 10px;
            }
            QLabel {
                color: #B71C1C;
                border: none;
            }
        """)
        banner_layout = QVBoxLayout(banner)
        banner_title = QLabel("⚠️ BEFORE YOU RUN, PLEASE CONFIRM")
        banner_title.setStyleSheet("font-size: 15px; font-weight: bold; color: #D32F2F;")
        banner_text = QLabel(
            "1. Please ensure that the column structure of your input CSV (list.csv) is perfectly aligned with the selected Part's backfill column specifications! \n"
            "2. The program relies on specific column indexes (Part 1: P~Y columns, Part 2: AD~AH columns, Part 3: AI/AJ/AM/AN columns, Part 4: AK/AL/AO~AV and AW+ victim details columns).\n"
            "3. Source file priority reading mechanism: If both .txt and .pdf files exist at the same row number (e.g., 007.txt and 007.pdf), the program will **prioritize reading the .txt file"
        )
        banner_text.setWordWrap(True)
        banner_layout.addWidget(banner_title)
        banner_layout.addWidget(banner_text)
        main_layout.addWidget(banner)

        # Group 1: File & Directory Paths
        path_group = QGroupBox("📁 File & Directory Paths")
        path_layout = QGridLayout(path_group)

        self.csv_input = QLineEdit("./list.csv")
        btn_csv = QPushButton("Browse...")
        btn_csv.clicked.connect(self.pick_csv)

        self.out_csv_input = QLineEdit("./list_coded.csv")
        btn_out_csv = QPushButton("Browse...")
        btn_out_csv.clicked.connect(self.pick_out_csv)

        self.ocred_dir_input = QLineEdit("./ocred")
        btn_dir = QPushButton("Browse...")
        btn_dir.clicked.connect(self.pick_dir)

        path_layout.addWidget(QLabel("Input CSV Path:"), 0, 0)
        path_layout.addWidget(self.csv_input, 0, 1)
        path_layout.addWidget(btn_csv, 0, 2)

        path_layout.addWidget(QLabel("Output CSV Path:"), 1, 0)
        path_layout.addWidget(self.out_csv_input, 1, 1)
        path_layout.addWidget(btn_out_csv, 1, 2)

        path_layout.addWidget(QLabel("OCR Source Folder:"), 2, 0)
        path_layout.addWidget(self.ocred_dir_input, 2, 1)
        path_layout.addWidget(btn_dir, 2, 2)
        main_layout.addWidget(path_group)

        # Group 2: Coding & Model Configuration
        cfg_group = QGroupBox("⚙️ Coding & Model Configuration")
        cfg_layout = QVBoxLayout(cfg_group)

        row_params = QHBoxLayout()
        self.task_combo = QComboBox()
        self.task_combo.addItems(list(PROMPTS.keys()))
        self.task_combo.currentTextChanged.connect(self.on_part_changed)

        self.model_combo = QComboBox()
        self.model_combo.addItems(MODEL_OPTIONS_PER_PART["Part 1"])
        self.model_combo.setCurrentText(DEFAULT_MODEL_PER_PART["Part 1"])

        self.start_row_input = QLineEdit("0")
        self.start_row_input.setFixedWidth(80)
        self.start_row_input.setToolTip("0 or 1 = start from row 1")

        row_params.addWidget(QLabel("Coding Part:"))
        row_params.addWidget(self.task_combo)
        row_params.addSpacing(15)
        row_params.addWidget(QLabel("Model:"))
        row_params.addWidget(self.model_combo)
        row_params.addSpacing(15)
        row_params.addWidget(QLabel("Start Row:"))
        row_params.addWidget(self.start_row_input)
        row_params.addStretch()
        cfg_layout.addLayout(row_params)

        row_keys = QHBoxLayout()
        self.key1_input = QLineEdit()
        self.key1_input.setEchoMode(QLineEdit.Password)
        self.key1_input.setPlaceholderText("Required Primary API Key")

        self.key2_input = QLineEdit()
        self.key2_input.setEchoMode(QLineEdit.Password)
        self.key2_input.setPlaceholderText("Optional Backup Key (Even Rows)")

        row_keys.addWidget(QLabel("API Key 1:"))
        row_keys.addWidget(self.key1_input)
        row_keys.addSpacing(15)
        row_keys.addWidget(QLabel("API Key 2:"))
        row_keys.addWidget(self.key2_input)
        cfg_layout.addLayout(row_keys)

        main_layout.addWidget(cfg_group)

        # Action & Progress
        self.btn_start = QPushButton("🚀 Start Batch Analysis")
        self.btn_start.setFixedHeight(40)
        self.btn_start.setStyleSheet("background-color: #2E7D32; color: white; font-weight: bold; font-size: 14px;")
        self.btn_start.clicked.connect(self.start_task)
        main_layout.addWidget(self.btn_start)

        self.pbar = QProgressBar()
        self.pbar.setValue(0)
        self.pbar.setVisible(False)
        main_layout.addWidget(self.pbar)

        self.status_lbl = QLabel("Ready to run.")
        self.status_lbl.setStyleSheet("font-weight: bold; color: #1976D2;")
        main_layout.addWidget(self.status_lbl)

        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        main_layout.addWidget(self.log_box)

    def on_part_changed(self, part):
        allowed = MODEL_OPTIONS_PER_PART.get(part, [])
        self.model_combo.clear()
        self.model_combo.addItems(allowed)
        default_m = DEFAULT_MODEL_PER_PART.get(part, allowed[0] if allowed else "")
        self.model_combo.setCurrentText(default_m)

    def pick_csv(self):
        p, _ = QFileDialog.getOpenFileName(self, "Select Input CSV", "", "CSV Files (*.csv);;All Files (*.*)")
        if p:
            self.csv_input.setText(clean_path(p))

    def pick_out_csv(self):
        p, _ = QFileDialog.getSaveFileName(self, "Select Output CSV", "list_coded.csv", "CSV Files (*.csv);;All Files (*.*)")
        if p:
            self.out_csv_input.setText(clean_path(p))

    def pick_dir(self):
        p = QFileDialog.getExistingDirectory(self, "Select OCR Source Folder", "")
        if p:
            self.ocred_dir_input.setText(clean_path(p))

    def set_status(self, text, color):
        self.status_lbl.setText(text)
        self.status_lbl.setStyleSheet(f"font-weight: bold; color: {color};")

    def start_task(self):
        csv_p = clean_path(self.csv_input.text())
        out_csv_p = clean_path(self.out_csv_input.text())
        ocred_dir_p = clean_path(self.ocred_dir_input.text())

        self.csv_input.setText(csv_p)
        self.out_csv_input.setText(out_csv_p)
        self.ocred_dir_input.setText(ocred_dir_p)

        key1 = self.key1_input.text().strip()
        key2 = self.key2_input.text().strip()
        part = self.task_combo.currentText()
        model_name = self.model_combo.currentText()

        try:
            start_r_val = max(1, int(self.start_row_input.text().strip()))
        except Exception:
            start_r_val = 1

        if not key1:
            self.set_status("❌ Error: Please input API Key 1 before starting.", "red")
            return

        if not os.path.exists(csv_p):
            self.set_status(f"❌ Error: CSV file not found: {csv_p}", "red")
            return

        self.btn_start.setEnabled(False)
        self.log_box.clear()
        self.pbar.setValue(0)
        self.pbar.setVisible(True)
        self.set_status("Running batch analysis...", "#1976D2")

        self.worker = BatchCodingWorker(
            csv_p, out_csv_p, ocred_dir_p, part, model_name, start_r_val, key1, key2
        )
        self.worker.progress.connect(self.update_progress)
        self.worker.log_signal.connect(self.log_box.append)
        self.worker.status_signal.connect(self.set_status)
        self.worker.finished.connect(self.on_finished)
        self.worker.start()

    def update_progress(self, curr, total):
        self.pbar.setMaximum(total)
        self.pbar.setValue(curr)

    def on_finished(self):
        self.btn_start.setEnabled(True)
        self.pbar.setVisible(False)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = BatchCodingWindow()
    window.show()
    sys.exit(app.exec())