import multiprocessing
import os
import re
import csv
import sys

if __name__ == "__main__":
    multiprocessing.freeze_support()

import requests
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
    QLabel, QLineEdit, QPushButton, QProgressBar, QTextEdit, QFileDialog
)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def clean_path(raw_path: str) -> str:
    """清理用户粘贴路径中的引号、多余空格和特殊前缀"""
    if not raw_path:
        return ""
    p = raw_path.strip()
    # 剥除 PowerShell 常见的 `& '...'` 或 `& "..."` 前缀
    if p.startswith('&'):
        p = p[1:].strip()
    # 循环剥除外层包裹的所有单双引号
    while len(p) >= 2 and ((p[0] == '"' and p[-1] == '"') or (p[0] == "'" and p[-1] == "'")):
        p = p[1:-1].strip()
    return os.path.normpath(p)

def col_to_index(col_str: str) -> int:
    col_str = col_str.strip().upper()
    idx = 0
    for char in col_str:
        if not ('A' <= char <= 'Z'):
            raise ValueError(f"Invalid column letter: {col_str}")
        idx = idx * 26 + (ord(char) - ord('A') + 1)
    return idx - 1

def download_file_from_google_drive(drive_url: str, save_path: str):
    match = re.search(r'/d/([^/]+)', drive_url)
    if not match:
        return False, "Invalid Google Drive URL format"
    
    file_id = match.group(1)
    download_url = f"https://docs.google.com/uc?export=download&id={file_id}"
    
    try:
        with requests.get(download_url, headers=HEADERS, stream=True, timeout=30) as r:
            if r.status_code == 200:
                with open(save_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                return True, "Success"
            elif r.status_code == 403:
                return False, "403 Forbidden (Traffic limit reached)"
            else:
                return False, f"HTTP {r.status_code}"
    except Exception as e:
        return False, str(e)

class DownloadWorker(QThread):
    progress = Signal(int, int)
    log_signal = Signal(str)
    finished = Signal()

    def __init__(self, csv_path, output_dir, check_col, link_col, start_row):
        super().__init__()
        self.csv_path = clean_path(csv_path)
        self.output_dir = clean_path(output_dir)
        self.check_col = check_col
        self.link_col = link_col
        self.start_row = start_row

    def run(self):
        try:
            check_idx = col_to_index(self.check_col)
            link_idx = col_to_index(self.link_col)
            start_r = max(1, int(self.start_row.strip()))
        except Exception as e:
            self.log_signal.emit(f"❌ Configuration error: {e}")
            self.finished.emit()
            return

        if not os.path.exists(self.csv_path):
            self.log_signal.emit(f"❌ File not found: {self.csv_path}")
            self.finished.emit()
            return

        try:
            os.makedirs(self.output_dir, exist_ok=True)
        except Exception as e:
            self.log_signal.emit(f"❌ Failed to create output directory: {e}")
            self.finished.emit()
            return

        try:
            with open(self.csv_path, mode='r', encoding='utf-8') as f:
                rows = list(csv.reader(f))
        except UnicodeDecodeError:
            with open(self.csv_path, mode='r', encoding='gbk', errors='ignore') as f:
                rows = list(csv.reader(f))

        total_rows = len(rows)
        required_cols = max(check_idx, link_idx) + 1
        downloaded = 0
        skipped = 0
        failed = 0

        self.log_signal.emit(f"📖 Loaded {total_rows} rows from: {self.csv_path}")
        self.log_signal.emit(f"🚀 Processing rows starting from row {start_r}...")

        for idx, row in enumerate(rows, start=1):
            if idx < start_r:
                continue

            self.progress.emit(idx, total_rows)

            if not row or "".join(row).strip() == "":
                continue

            if "Author Last Name" in row or "Newspaper/Publisher" in row:
                continue

            if len(row) < required_cols:
                continue

            check_val = row[check_idx].strip()
            link = row[link_idx].strip()

            if check_val:
                if not link:
                    self.log_signal.emit(f"⚠️ Row [{idx}]: Marked for download but link is empty. Skipped.")
                    continue

                filename = f"{idx:03d}.pdf"
                dest_path = os.path.join(self.output_dir, filename)

                if os.path.exists(dest_path):
                    skipped += 1
                    continue

                self.log_signal.emit(f"🚀 Downloading Row [{idx}] ──> {filename}...")
                ok, msg = download_file_from_google_drive(link, dest_path)
                if ok:
                    downloaded += 1
                else:
                    failed += 1
                    self.log_signal.emit(f"   └─ ❌ Failed: {msg}")

        self.progress.emit(total_rows, total_rows)
        self.log_signal.emit("=" * 40)
        self.log_signal.emit(f"🎉 Complete! Downloaded: {downloaded}, Skipped: {skipped}, Failed: {failed}")
        self.log_signal.emit(f"📂 Output location: {os.path.abspath(self.output_dir)}")
        self.finished.emit()

class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Google Drive Batch Downloader")
        self.resize(700, 520)

        layout = QVBoxLayout()

        # CSV File Row
        csv_row = QHBoxLayout()
        csv_row.addWidget(QLabel("CSV File:"))
        self.csv_input = QLineEdit("./list.csv")
        csv_row.addWidget(self.csv_input)
        self.btn_browse_csv = QPushButton("Browse...")
        self.btn_browse_csv.clicked.connect(self.browse_csv)
        csv_row.addWidget(self.btn_browse_csv)
        layout.addLayout(csv_row)

        # Output Dir Row
        out_row = QHBoxLayout()
        out_row.addWidget(QLabel("Output Dir:"))
        self.out_input = QLineEdit("./original")
        out_row.addWidget(self.out_input)
        self.btn_browse_out = QPushButton("Browse...")
        self.btn_browse_out.clicked.connect(self.browse_output)
        out_row.addWidget(self.btn_browse_out)
        layout.addLayout(out_row)

        # Parameter Row
        param_row = QHBoxLayout()
        self.check_input = QLineEdit("E")
        self.link_input = QLineEdit("M")
        self.start_input = QLineEdit("1")
        param_row.addWidget(QLabel("Check Col:"))
        param_row.addWidget(self.check_input)
        param_row.addWidget(QLabel("Drive Link Col:"))
        param_row.addWidget(self.link_input)
        param_row.addWidget(QLabel("Start Row:"))
        param_row.addWidget(self.start_input)
        layout.addLayout(param_row)

        # Start Button
        self.btn_start = QPushButton("Start Batch Download")
        self.btn_start.setFixedHeight(35)
        self.btn_start.clicked.connect(self.start_task)
        layout.addWidget(self.btn_start)

        # Progress Bar
        self.pbar = QProgressBar()
        self.pbar.setValue(0)
        layout.addWidget(self.pbar)

        # Log View
        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        layout.addWidget(self.log_box)

        self.setLayout(layout)

    def browse_csv(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select CSV File", "", "CSV Files (*.csv);;All Files (*.*)"
        )
        if file_path:
            self.csv_input.setText(clean_path(file_path))

    def browse_output(self):
        dir_path = QFileDialog.getExistingDirectory(
            self, "Select Output Directory", ""
        )
        if dir_path:
            self.out_input.setText(clean_path(dir_path))

    def start_task(self):
        self.btn_start.setEnabled(False)
        self.log_box.clear()
        self.pbar.setValue(0)

        # 启动时自动规范化一次输入框里的路径文本
        self.csv_input.setText(clean_path(self.csv_input.text()))
        self.out_input.setText(clean_path(self.out_input.text()))

        self.thread = DownloadWorker(
            self.csv_input.text(),
            self.out_input.text(),
            self.check_input.text(),
            self.link_input.text(),
            self.start_input.text()
        )
        self.thread.progress.connect(self.update_progress)
        self.thread.log_signal.connect(self.log_box.append)
        self.thread.finished.connect(lambda: self.btn_start.setEnabled(True))
        self.thread.start()

    def update_progress(self, current, total):
        self.pbar.setMaximum(total)
        self.pbar.setValue(current)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())