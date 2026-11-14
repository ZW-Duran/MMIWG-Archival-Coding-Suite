import multiprocessing
import sys
from pathlib import Path

if __name__ == "__main__":
    multiprocessing.freeze_support()

if not getattr(sys, "frozen", False):
    _REPO_ROOT = str(Path(__file__).resolve().parents[2])
    if _REPO_ROOT not in sys.path:
        sys.path.insert(0, _REPO_ROOT)

import csv
import os
import re
import threading

import flet as ft
import requests

try:
    from core.pdf_utils import clean_path
except ImportError:
    def clean_path(raw_path: str) -> str:
        """Clean quotes, whitespace, and PowerShell `&` prefixes from pasted file paths."""
        if not raw_path:
            return ""
        p = raw_path.strip()
        if p.startswith("&"):
            p = p[1:].strip()
        while len(p) >= 2 and ((p[0] == '"' and p[-1] == '"') or (p[0] == "'" and p[-1] == "'")):
            p = p[1:-1].strip()
        return os.path.normpath(p)


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}


def col_to_index(col_str: str) -> int:
    col_str = col_str.strip().upper()
    if not col_str:
        raise ValueError("Column letter cannot be empty")
    idx = 0
    for char in col_str:
        if not ("A" <= char <= "Z"):
            raise ValueError(f"Invalid column letter: {col_str}")
        idx = idx * 26 + (ord(char) - ord("A") + 1)
    return idx - 1


def download_file_from_google_drive(drive_url: str, save_path: str):
    match = re.search(r"/d/([^/]+)", drive_url)
    if not match:
        return False, "Invalid Google Drive URL format"

    file_id = match.group(1)
    download_url = f"https://docs.google.com/uc?export=download&id={file_id}"

    try:
        with requests.get(download_url, headers=HEADERS, stream=True, timeout=30) as r:
            if r.status_code == 200:
                with open(save_path, "wb") as f:
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


def main(page: ft.Page):
    page.title = "MMIWG Google Drive Batch Downloader"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.padding = 20
    page.scroll = ft.ScrollMode.AUTO
    page.window.width = 960
    page.window.height = 760

    state = {
        "running": False,
        "stop_event": threading.Event(),
        "log_lock": threading.Lock(),
    }

    # --- Section 1: CSV & Output Folder Selection ---
    csv_input = ft.TextField(
        label="CSV File Path",
        value="./list.csv",
        hint_text="Select exported Google Sheet CSV file...",
        expand=True,
        dense=True,
    )
    out_input = ft.TextField(
        label="Output Folder",
        value="./original",
        hint_text="Select destination folder for downloaded PDFs...",
        expand=True,
        dense=True,
    )

    def on_csv_picked(e: ft.FilePickerResultEvent):
        if e.files and len(e.files) > 0 and e.files[0].path:
            csv_input.value = clean_path(e.files[0].path)
            page.update()

    def on_out_dir_picked(e: ft.FilePickerResultEvent):
        if e.path:
            out_input.value = clean_path(e.path)
            page.update()

    csv_picker = ft.FilePicker(on_result=on_csv_picked)
    out_picker = ft.FilePicker(on_result=on_out_dir_picked)
    page.overlay.extend([csv_picker, out_picker])

    browse_csv_btn = ft.OutlinedButton(
        "Browse",
        icon=ft.Icons.FILE_OPEN,
        on_click=lambda _: csv_picker.pick_files(
            dialog_title="Select CSV File",
            allow_multiple=False,
            allowed_extensions=["csv"],
        ),
    )
    browse_out_btn = ft.OutlinedButton(
        "Browse",
        icon=ft.Icons.FOLDER_OPEN,
        on_click=lambda _: out_picker.get_directory_path(
            dialog_title="Select Output Directory",
        ),
    )

    # --- Section 2: Column & Row Parameters (fixed widths inside wrap=True Row) ---
    check_input = ft.TextField(
        label="Check Column",
        value="E",
        hint_text="e.g. E or C",
        width=180,
        dense=True,
    )
    link_input = ft.TextField(
        label="Drive Link Column",
        value="M",
        hint_text="e.g. M or F",
        width=180,
        dense=True,
    )
    start_input = ft.TextField(
        label="Start Row",
        value="1",
        hint_text="1 = scan from top",
        width=160,
        dense=True,
    )

    # --- Section 3: Execution, Counters & Live Log ---
    start_btn = ft.ElevatedButton(
        "Start Batch Download",
        icon=ft.Icons.DOWNLOAD,
        bgcolor=ft.Colors.GREEN_700,
        color=ft.Colors.WHITE,
    )
    stop_btn = ft.OutlinedButton(
        "Stop",
        icon=ft.Icons.STOP,
        disabled=True,
    )

    downloaded_stat = ft.Text("Downloaded: 0", size=13, color=ft.Colors.GREEN_700, weight=ft.FontWeight.W_500)
    skipped_stat = ft.Text("Skipped: 0", size=13, color=ft.Colors.GREY_700, weight=ft.FontWeight.W_500)
    failed_stat = ft.Text("Failed: 0", size=13, color=ft.Colors.RED_700, weight=ft.FontWeight.W_500)
    status_text = ft.Text("Ready to download.", size=13, color=ft.Colors.BLUE_700, weight=ft.FontWeight.W_500)

    progress_bar = ft.ProgressBar(value=0, visible=False)
    log_list = ft.ListView(expand=True, spacing=4, auto_scroll=True)

    def append_log(message: str):
        with state["log_lock"]:
            log_list.controls.append(ft.Text(message, size=12, font_family="monospace", selectable=True))
            if len(log_list.controls) > 500:
                log_list.controls.pop(0)
        page.update()

    def set_running_ui(is_running: bool):
        state["running"] = is_running
        start_btn.disabled = is_running
        stop_btn.disabled = not is_running
        csv_input.disabled = is_running
        out_input.disabled = is_running
        browse_csv_btn.disabled = is_running
        browse_out_btn.disabled = is_running
        check_input.disabled = is_running
        link_input.disabled = is_running
        start_input.disabled = is_running
        progress_bar.visible = is_running
        page.update()

    def on_stop_click(e):
        state["stop_event"].set()
        stop_btn.disabled = True
        append_log("[INFO] Stop requested — stopping after current file...")
        page.update()

    stop_btn.on_click = on_stop_click

    def on_start_click(e):
        csv_path = clean_path(csv_input.value or "")
        output_dir = clean_path(out_input.value or "")
        csv_input.value = csv_path
        out_input.value = output_dir

        check_col = (check_input.value or "").strip()
        link_col = (link_input.value or "").strip()
        start_row_str = (start_input.value or "1").strip()

        with state["log_lock"]:
            log_list.controls.clear()
        downloaded_stat.value = "Downloaded: 0"
        skipped_stat.value = "Skipped: 0"
        failed_stat.value = "Failed: 0"
        progress_bar.value = 0

        try:
            check_idx = col_to_index(check_col)
            link_idx = col_to_index(link_col)
            start_r = max(1, int(start_row_str))
        except Exception as ex:
            status_text.value = f"❌ Configuration error: {ex}"
            status_text.color = ft.Colors.RED_700
            append_log(f"❌ Configuration error: {ex}")
            return

        if not csv_path or not os.path.exists(csv_path):
            status_text.value = f"❌ File not found: {csv_path}"
            status_text.color = ft.Colors.RED_700
            append_log(f"❌ File not found: {csv_path}")
            return

        try:
            os.makedirs(output_dir, exist_ok=True)
        except Exception as ex:
            status_text.value = f"❌ Failed to create output directory: {ex}"
            status_text.color = ft.Colors.RED_700
            append_log(f"❌ Failed to create output directory: {ex}")
            return

        state["stop_event"].clear()
        set_running_ui(True)
        status_text.value = "Reading CSV and starting downloads..."
        status_text.color = ft.Colors.BLUE_700
        page.update()

        def worker():
            try:
                try:
                    with open(csv_path, mode="r", encoding="utf-8") as f:
                        rows = list(csv.reader(f))
                except UnicodeDecodeError:
                    with open(csv_path, mode="r", encoding="gbk", errors="ignore") as f:
                        rows = list(csv.reader(f))

                total_rows = len(rows)
                required_cols = max(check_idx, link_idx) + 1
                downloaded = 0
                skipped = 0
                failed = 0

                append_log(f"📖 Loaded {total_rows} rows from: {csv_path}")
                append_log(f"🚀 Processing rows starting from row {start_r}...")

                for idx, row in enumerate(rows, start=1):
                    if state["stop_event"].is_set():
                        append_log("⏹️ Download stopped by user.")
                        break

                    if idx < start_r:
                        continue

                    if total_rows > 0:
                        progress_bar.value = idx / total_rows

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
                            append_log(f"⚠️ Row [{idx}]: Marked for download but link is empty. Skipped.")
                            continue

                        filename = f"{idx:03d}.pdf"
                        dest_path = os.path.join(output_dir, filename)

                        if os.path.exists(dest_path):
                            skipped += 1
                            skipped_stat.value = f"Skipped: {skipped}"
                            page.update()
                            continue

                        status_text.value = f"Downloading Row [{idx}/{total_rows}] -> {filename}..."
                        append_log(f"🚀 Downloading Row [{idx}] ──> {filename}...")
                        ok, msg = download_file_from_google_drive(link, dest_path)
                        if ok:
                            downloaded += 1
                            downloaded_stat.value = f"Downloaded: {downloaded}"
                            page.update()
                        else:
                            failed += 1
                            failed_stat.value = f"Failed: {failed}"
                            append_log(f"   └─ ❌ Failed: {msg}")

                if not state["stop_event"].is_set() and total_rows > 0:
                    progress_bar.value = 1.0

                append_log("=" * 40)
                append_log(f"🎉 Complete! Downloaded: {downloaded}, Skipped: {skipped}, Failed: {failed}")
                append_log(f"📂 Output location: {os.path.abspath(output_dir)}")
                if state["stop_event"].is_set():
                    status_text.value = f"Stopped. Downloaded {downloaded}, Skipped {skipped}, Failed {failed}."
                    status_text.color = ft.Colors.ORANGE_700
                else:
                    status_text.value = f"🎉 Complete! Downloaded {downloaded}, Skipped {skipped}, Failed {failed}."
                    status_text.color = ft.Colors.GREEN_700
            except Exception as ex:
                status_text.value = f"❌ Error: {ex}"
                status_text.color = ft.Colors.RED_700
                append_log(f"❌ Unexpected error: {ex}")
            finally:
                set_running_ui(False)

        threading.Thread(target=worker, daemon=True).start()

    start_btn.on_click = on_start_click

    # --- Assemble Layout ---
    page.add(
        ft.Text("MMIWG Google Drive Batch Downloader", size=22, weight=ft.FontWeight.BOLD),
        ft.Text(
            "Batch download approved PDF files from exported Google Sheets CSVs into zero-padded 001.pdf names.",
            size=13,
            color=ft.Colors.GREY_700,
        ),
        ft.Card(
            content=ft.Container(
                padding=15,
                content=ft.Column(
                    [
                        ft.Text("1. CSV & Output Folder Selection", size=15, weight=ft.FontWeight.BOLD),
                        ft.Row([csv_input, browse_csv_btn]),
                        ft.Row([out_input, browse_out_btn]),
                    ],
                    spacing=10,
                ),
            )
        ),
        ft.Card(
            content=ft.Container(
                padding=15,
                content=ft.Column(
                    [
                        ft.Text("2. Column & Row Parameters", size=15, weight=ft.FontWeight.BOLD),
                        ft.Row(
                            [check_input, link_input, start_input],
                            spacing=16,
                            wrap=True,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                    ],
                    spacing=10,
                ),
            )
        ),
        ft.Card(
            content=ft.Container(
                padding=15,
                content=ft.Column(
                    [
                        ft.Text("3. Batch Execution & Live Progress", size=15, weight=ft.FontWeight.BOLD),
                        ft.Row([start_btn, stop_btn], spacing=12),
                        ft.Row([downloaded_stat, skipped_stat, failed_stat], spacing=18, wrap=True),
                        status_text,
                        progress_bar,
                        ft.Container(
                            content=log_list,
                            height=240,
                            border=ft.border.all(1, ft.Colors.GREY_300),
                            border_radius=6,
                            padding=8,
                            bgcolor=ft.Colors.GREY_50,
                        ),
                    ],
                    spacing=10,
                ),
            )
        ),
    )


if __name__ == "__main__":
    ft.app(target=main)
