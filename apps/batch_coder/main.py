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
import json
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor

import fitz  # PyMuPDF
import flet as ft
import google.generativeai as genai

from core.pdf_utils import clean_path, read_source_file_content
from core.prompts import BATCH_PROMPTS as PROMPTS


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
# 3. AI Analysis & Row Coding Logic
# ==============================================================================
def analyze_text_with_gemini(
    text: str,
    row_idx: int,
    system_instruction: str,
    model_name: str,
    api_key_1: str,
    api_key_2: str,
) -> dict:
    prompt = f"{system_instruction}\n\nArticle Text:\n{text}"

    if not api_key_2 or not api_key_2.strip():
        current_api_key = api_key_1.strip()
    else:
        current_api_key = api_key_1.strip() if row_idx % 2 != 0 else api_key_2.strip()

    raw_response = ""
    try:
        genai.configure(api_key=current_api_key)
        model = genai.GenerativeModel(model_name)

        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(temperature=0.0),
        )

        raw_response = response.text.strip() if response and response.text else ""
        if not raw_response:
            return None

        clean_text = re.sub(r"```json\s*|\s*```", "", raw_response).strip()
        start_idx = clean_text.find("{")
        end_idx = clean_text.rfind("}")

        if start_idx != -1 and end_idx != -1 and end_idx >= start_idx:
            json_str = clean_text[start_idx : end_idx + 1]
            return json.loads(json_str)
        return None
    except Exception:
        try:
            if "mmiwg_mentioned" in system_instruction:
                fallback = {}
                keys = [
                    "mmiwg_mentioned",
                    "mmiwg_movement",
                    "specific_case",
                    "multiple_cases",
                    "legal_protection",
                    "family_friends_referenced",
                    "details_victim_life",
                    "details_perpetrator",
                ]
                for k in keys:
                    m = re.search(rf'"{k}"\s*:\s*([01])', raw_response, re.IGNORECASE)
                    fallback[k] = int(m.group(1)) if m else 0
                return fallback
        except Exception:
            pass
        return None


def process_single_row(task):
    idx, row, part, model_name, ocred_dir, key1, key2, stop_event = task
    if stop_event.is_set():
        return idx, row, False, f"⏹️ Row [{idx}]: Cancelled by user."

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
            while len(row) <= 24:
                row.append("")
            row[15] = safe_get_val("mmiwg_mentioned")
            row[16] = safe_get_val("mmiwg_movement")
            row[17] = safe_get_val("specific_case")
            row[18] = safe_get_val("multiple_cases")
            row[19] = safe_get_val("legal_protection")
            row[22] = safe_get_val("family_friends_referenced")
            row[23] = safe_get_val("details_victim_life")
            row[24] = safe_get_val("details_perpetrator")

        elif part == "Part 2":
            while len(row) <= 33:
                row.append("")
            row[29] = safe_get_val("tribe_gov_officials")
            row[30] = safe_get_val("state_local_gov_officials")
            row[31] = safe_get_val("federal_gov_officials")
            row[32] = safe_get_val("law_enforcement")
            row[33] = safe_get_val("legal_professionals")

        elif part == "Part 3":
            while len(row) <= 39:
                row.append("")
            row[34] = safe_get_val("academics")
            row[35] = safe_get_val("other_experts")
            row[38] = safe_get_val("family_friends_referenced")
            row[39] = safe_get_val("other_ordinary_people")

        elif part == "Part 4":
            counts = analysis.get("counts", {})
            victims = analysis.get("victims", [])
            suspect_info = analysis.get("suspect_info", {})

            while len(row) <= 47:
                row.append("")

            try:
                p_count = int(suspect_info.get("perpetrators_count", 0))
            except Exception:
                p_count = 0
            row[36] = p_count
            row[37] = "" if p_count == 0 else str(suspect_info.get("perpetrators_race", ""))

            def safe_get_count(c_key, alt_key=""):
                c_val = counts.get(c_key, counts.get(alt_key, 0))
                try:
                    return int(c_val)
                except Exception:
                    return 0

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
                while len(row) < v_start + 6:
                    row.append("")
                row[v_start] = str(v.get("name", ""))
                row[v_start + 1] = str(v.get("race", ""))
                row[v_start + 2] = str(v.get("tribal_affiliation", ""))
                row[v_start + 3] = str(v.get("age", ""))
                row[v_start + 4] = str(v.get("gender", ""))
                row[v_start + 5] = str(v.get("status", ""))

        return idx, row, True, f"✅ Row [{idx}] [{ext_name}]: Analysis complete and encoded."
    except Exception as e:
        return idx, row, False, f"❌ Row [{idx}] Backfill error: {e}"


# ==============================================================================
# 4. Flet Desktop UI
# ==============================================================================
def main(page: ft.Page):
    page.title = "MMIWG News Text Quantitative Batch Coder"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.padding = 20
    page.scroll = ft.ScrollMode.AUTO
    page.window.width = 1040
    page.window.height = 860

    state = {
        "running": False,
        "stop_event": threading.Event(),
        "log_lock": threading.Lock(),
    }

    # --- Section 1: File & Directory Paths ---
    csv_input = ft.TextField(
        label="Input CSV Path",
        value="./list.csv",
        expand=True,
        dense=True,
    )
    out_csv_input = ft.TextField(
        label="Output CSV Path",
        value="./list_coded.csv",
        expand=True,
        dense=True,
    )
    ocred_dir_input = ft.TextField(
        label="OCR Source Folder",
        value="./ocred",
        expand=True,
        dense=True,
    )

    def on_csv_picked(e: ft.FilePickerResultEvent):
        if e.files and len(e.files) > 0 and e.files[0].path:
            csv_input.value = clean_path(e.files[0].path)
            page.update()

    def on_out_csv_picked(e: ft.FilePickerResultEvent):
        if e.path:
            out_csv_input.value = clean_path(e.path)
            page.update()

    def on_dir_picked(e: ft.FilePickerResultEvent):
        if e.path:
            ocred_dir_input.value = clean_path(e.path)
            page.update()

    csv_picker = ft.FilePicker(on_result=on_csv_picked)
    out_csv_picker = ft.FilePicker(on_result=on_out_csv_picked)
    dir_picker = ft.FilePicker(on_result=on_dir_picked)
    page.overlay.extend([csv_picker, out_csv_picker, dir_picker])

    browse_csv_btn = ft.OutlinedButton(
        "Browse",
        icon=ft.Icons.FILE_OPEN,
        on_click=lambda _: csv_picker.pick_files(
            dialog_title="Select Input CSV",
            allow_multiple=False,
            allowed_extensions=["csv"],
        ),
    )
    browse_out_csv_btn = ft.OutlinedButton(
        "Browse",
        icon=ft.Icons.SAVE_AS,
        on_click=lambda _: out_csv_picker.save_file(
            dialog_title="Select Output CSV",
            file_name="list_coded.csv",
            allowed_extensions=["csv"],
        ),
    )
    browse_dir_btn = ft.OutlinedButton(
        "Browse",
        icon=ft.Icons.FOLDER_OPEN,
        on_click=lambda _: dir_picker.get_directory_path(
            dialog_title="Select OCR Source Folder",
        ),
    )

    # --- Section 2: Coding & Model Configuration (fixed widths inside wrap=True Rows) ---
    task_dropdown = ft.Dropdown(
        label="Coding Part",
        options=[ft.dropdown.Option(k) for k in PROMPTS.keys()],
        value="Part 1",
        width=200,
    )
    model_dropdown = ft.Dropdown(
        label="Model",
        options=[ft.dropdown.Option(m) for m in MODEL_OPTIONS_PER_PART["Part 1"]],
        value=DEFAULT_MODEL_PER_PART["Part 1"],
        width=260,
    )
    start_row_input = ft.TextField(
        label="Start Row (0 or 1 = row 1)",
        value="0",
        width=200,
        dense=True,
    )

    def on_part_changed(e):
        part = task_dropdown.value
        allowed = MODEL_OPTIONS_PER_PART.get(part, [])
        model_dropdown.options = [ft.dropdown.Option(m) for m in allowed]
        model_dropdown.value = DEFAULT_MODEL_PER_PART.get(part, allowed[0] if allowed else "")
        page.update()

    task_dropdown.on_change = on_part_changed

    key1_input = ft.TextField(
        label="API Key 1 (Primary)",
        password=True,
        can_reveal_password=True,
        hint_text="Required Google AI Studio API Key",
        width=380,
        dense=True,
    )
    key2_input = ft.TextField(
        label="API Key 2 (Backup / Optional)",
        password=True,
        can_reveal_password=True,
        hint_text="Optional: Alternate requests on even rows",
        width=380,
        dense=True,
    )

    # --- Section 3: Execution, Progress & Logs ---
    start_btn = ft.ElevatedButton(
        "Start Batch Analysis",
        icon=ft.Icons.PLAY_ARROW,
        bgcolor=ft.Colors.GREEN_700,
        color=ft.Colors.WHITE,
    )
    stop_btn = ft.OutlinedButton(
        "Stop",
        icon=ft.Icons.STOP,
        disabled=True,
    )
    status_text = ft.Text("Ready to run.", size=13, color=ft.Colors.BLUE_700, weight=ft.FontWeight.BOLD)
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
        out_csv_input.disabled = is_running
        ocred_dir_input.disabled = is_running
        browse_csv_btn.disabled = is_running
        browse_out_csv_btn.disabled = is_running
        browse_dir_btn.disabled = is_running
        task_dropdown.disabled = is_running
        model_dropdown.disabled = is_running
        start_row_input.disabled = is_running
        key1_input.disabled = is_running
        key2_input.disabled = is_running
        progress_bar.visible = is_running
        page.update()

    def on_stop_click(e):
        state["stop_event"].set()
        stop_btn.disabled = True
        append_log("[INFO] Stop requested — waiting for active worker(s) to finish...")
        page.update()

    stop_btn.on_click = on_stop_click

    def on_start_click(e):
        csv_p = clean_path(csv_input.value or "")
        out_csv_p = clean_path(out_csv_input.value or "")
        ocred_dir_p = clean_path(ocred_dir_input.value or "")

        csv_input.value = csv_p
        out_csv_input.value = out_csv_p
        ocred_dir_input.value = ocred_dir_p

        key1 = (key1_input.value or "").strip()
        key2 = (key2_input.value or "").strip()
        part = task_dropdown.value
        model_name = model_dropdown.value

        try:
            start_r_val = max(1, int((start_row_input.value or "0").strip()))
        except Exception:
            start_r_val = 1

        if not key1:
            status_text.value = "❌ Error: Please input API Key 1 before starting."
            status_text.color = ft.Colors.RED_700
            page.update()
            return

        if not csv_p or not os.path.exists(csv_p):
            status_text.value = f"❌ Error: CSV file not found: {csv_p}"
            status_text.color = ft.Colors.RED_700
            page.update()
            return

        with state["log_lock"]:
            log_list.controls.clear()
        progress_bar.value = 0
        state["stop_event"].clear()
        set_running_ui(True)
        status_text.value = "Running batch analysis..."
        status_text.color = ft.Colors.BLUE_700
        page.update()

        def worker():
            try:
                append_log(f"🚀 Initializing Batch Process for [{part}] using [{model_name}]...")
                append_log(f"📖 CSV Input: {csv_p}")
                append_log(f"💾 CSV Output: {out_csv_p}")
                append_log(f"📂 Source Folder: {ocred_dir_p} (TXT Preferred over PDF, All Depths)")
                append_log(f"📍 Start Row Index: {start_r_val}")

                source_csv = out_csv_p if os.path.exists(out_csv_p) else csv_p
                try:
                    with open(source_csv, mode="r", encoding="utf-8", newline="") as f:
                        rows = list(csv.reader(f))
                except UnicodeDecodeError:
                    with open(source_csv, mode="r", encoding="gbk", errors="ignore", newline="") as f:
                        rows = list(csv.reader(f))

                todo_tasks = []
                for idx, row in enumerate(rows, start=1):
                    if idx < start_r_val or idx == 1 or len(row) < 4:
                        continue

                    e_col_val = row[4].strip() if len(row) > 4 else ""

                    check_val = ""
                    if part == "Part 1":
                        check_val = row[15].strip() if len(row) > 15 else ""
                    elif part == "Part 2":
                        check_val = row[29].strip() if len(row) > 29 else ""
                    elif part == "Part 3":
                        check_val = row[34].strip() if len(row) > 34 else ""
                    elif part == "Part 4":
                        check_val = row[40].strip() if len(row) > 40 else ""

                    if e_col_val and check_val == "":
                        todo_tasks.append(
                            (idx, row, part, model_name, ocred_dir_p, key1, key2, state["stop_event"])
                        )

                total_tasks = len(todo_tasks)
                append_log(f"⚡️ [Task Filtering] Found {total_tasks} rows requiring coding analysis.")

                if total_tasks == 0:
                    append_log("🎉 No pending tasks found! All rows are already encoded or skipped.")
                    status_text.value = "🎉 No pending tasks found."
                    status_text.color = ft.Colors.GREEN_700
                    return

                completed_count = 0
                success_count = 0

                with ThreadPoolExecutor(max_workers=2) as executor:
                    results = executor.map(process_single_row, todo_tasks)
                    for idx, updated_row, is_ok, msg in results:
                        completed_count += 1
                        if is_ok:
                            success_count += 1
                            with open(out_csv_p, mode="w", encoding="utf-8", newline="") as f_write:
                                writer = csv.writer(f_write, quoting=csv.QUOTE_MINIMAL)
                                writer.writerows(rows)

                        progress_bar.value = completed_count / total_tasks
                        status_text.value = f"Processing: {completed_count}/{total_tasks} rows..."
                        status_text.color = ft.Colors.BLUE_700
                        append_log(msg)

                append_log("=" * 45)
                if state["stop_event"].is_set():
                    append_log(f"⏹️ Batch Processing Stopped. Saved {success_count} rows to: {out_csv_p}")
                    status_text.value = f"Stopped. Processed {success_count} rows."
                    status_text.color = ft.Colors.ORANGE_700
                else:
                    append_log(
                        f"🎉 Batch Processing Complete! Successfully saved {success_count} rows to: {out_csv_p}"
                    )
                    status_text.value = f"🎉 Complete! Processed {success_count} rows."
                    status_text.color = ft.Colors.GREEN_700
            except Exception as ex:
                status_text.value = f"❌ Error: {ex}"
                status_text.color = ft.Colors.RED_700
                append_log(f"❌ Batch error: {ex}")
            finally:
                set_running_ui(False)

        threading.Thread(target=worker, daemon=True).start()

    start_btn.on_click = on_start_click

    # --- Assemble Layout ---
    notice_banner = ft.Card(
        content=ft.Container(
            bgcolor=ft.Colors.RED_50,
            border=ft.border.all(1.5, ft.Colors.RED_400),
            border_radius=8,
            padding=14,
            content=ft.Column(
                [
                    ft.Text(
                        "⚠️ BEFORE YOU RUN, PLEASE CONFIRM",
                        size=15,
                        weight=ft.FontWeight.BOLD,
                        color=ft.Colors.RED_800,
                    ),
                    ft.Text(
                        "1. Please ensure that the column structure of your input CSV (list.csv) is perfectly aligned with the selected Part's backfill column specifications!\n"
                        "2. The program relies on specific column indexes (Part 1: P~Y columns, Part 2: AD~AH columns, Part 3: AI/AJ/AM/AN columns, Part 4: AK/AL/AO~AV and AW+ victim details columns).\n"
                        "3. Source file priority reading mechanism: If both .txt and .pdf files exist at the same row number (e.g., 007.txt and 007.pdf), the program will prioritize reading the .txt file.",
                        size=12,
                        color=ft.Colors.RED_900,
                    ),
                ],
                spacing=6,
            ),
        )
    )

    page.add(
        ft.Text("MMIWG News Text Quantitative Batch Coder", size=22, weight=ft.FontWeight.BOLD),
        ft.Text(
            "Batch process archival documents across all directory depths (TXT preferred over PDF).",
            size=13,
            color=ft.Colors.GREY_700,
        ),
        notice_banner,
        ft.Card(
            content=ft.Container(
                padding=15,
                content=ft.Column(
                    [
                        ft.Text("1. File & Directory Paths", size=15, weight=ft.FontWeight.BOLD),
                        ft.Row([csv_input, browse_csv_btn]),
                        ft.Row([out_csv_input, browse_out_csv_btn]),
                        ft.Row([ocred_dir_input, browse_dir_btn]),
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
                        ft.Text("2. Coding & Model Configuration", size=15, weight=ft.FontWeight.BOLD),
                        ft.Row(
                            [task_dropdown, model_dropdown, start_row_input],
                            spacing=14,
                            wrap=True,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        ft.Row(
                            [key1_input, key2_input],
                            spacing=14,
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
