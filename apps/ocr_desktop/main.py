import multiprocessing
import sys
from pathlib import Path

if __name__ == "__main__":
    multiprocessing.freeze_support()

if not getattr(sys, "frozen", False):
    _REPO_ROOT = str(Path(__file__).resolve().parents[2])
    if _REPO_ROOT not in sys.path:
        sys.path.insert(0, _REPO_ROOT)

from concurrent.futures import ThreadPoolExecutor, as_completed
import os
import threading
import flet as ft

try:
    from apps.ocr_desktop.ocr_engine import (
        ENGINE_MODES,
        check_system_deps,
        get_augmented_env,
        install_system_deps,
        ocr_single_pdf,
        resolve_auto_mode,
    )
except ImportError:
    from ocr_engine import (
        ENGINE_MODES,
        check_system_deps,
        get_augmented_env,
        install_system_deps,
        ocr_single_pdf,
        resolve_auto_mode,
    )


def main(page: ft.Page):
    page.title = "MMIWG Batch OCR Processor"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.padding = 20
    page.scroll = ft.ScrollMode.AUTO
    page.window.width = 1040
    page.window.height = 840

    state = {
        "running": False,
        "stop_event": threading.Event(),
        "log_lock": threading.Lock(),
    }

    # --- Section 1: OCR Engine & System Dependencies ---
    mode_dropdown = ft.Dropdown(
        label="OCR Engine Mode",
        options=[ft.dropdown.Option(key=k, text=v) for k, v in ENGINE_MODES.items()],
        value="auto",
        width=560,
    )
    deps_status_text = ft.Text("Checking dependencies...", size=13)
    active_backend_text = ft.Text("", size=12, color=ft.Colors.GREY_700)

    check_deps_btn = ft.OutlinedButton(
        "Check Status",
        icon=ft.Icons.REFRESH,
    )
    install_deps_btn = ft.ElevatedButton(
        "Install System OCR Tools (brew / winget)",
        icon=ft.Icons.DOWNLOAD,
        bgcolor=ft.Colors.BLUE_700,
        color=ft.Colors.WHITE,
    )

    # --- Section 2: Folder Configuration ---
    input_dir_tf = ft.TextField(
        label="Input Folder (Folder A — Original PDFs)",
        hint_text="Select folder containing downloaded PDFs...",
        expand=True,
        dense=True,
    )
    output_dir_tf = ft.TextField(
        label="Output Folder (Folder B — Searchable OCR PDFs)",
        hint_text="Select destination folder for OCRed PDFs...",
        expand=True,
        dense=True,
    )
    threads_dropdown = ft.Dropdown(
        label="Parallel Worker Threads",
        options=[ft.dropdown.Option(key=str(n), text=f"{n} thread{'s' if n > 1 else ''}") for n in (1, 2, 4, 6, 8)],
        value="2",
        width=200,
    )
    resume_checkbox = ft.Checkbox(
        label="Skip files already present in Output Folder (Resume Mode)",
        value=True,
    )

    def on_input_dir_picked(e: ft.FilePickerResultEvent):
        if e.path:
            input_dir_tf.value = e.path
            page.update()

    def on_output_dir_picked(e: ft.FilePickerResultEvent):
        if e.path:
            output_dir_tf.value = e.path
            page.update()

    input_picker = ft.FilePicker(on_result=on_input_dir_picked)
    output_picker = ft.FilePicker(on_result=on_output_dir_picked)
    page.overlay.extend([input_picker, output_picker])

    browse_input_btn = ft.OutlinedButton(
        "Browse",
        icon=ft.Icons.FOLDER_OPEN,
        on_click=lambda _: input_picker.get_directory_path(dialog_title="Select Input Folder (Folder A)"),
    )
    browse_output_btn = ft.OutlinedButton(
        "Browse",
        icon=ft.Icons.FOLDER_OPEN,
        on_click=lambda _: output_picker.get_directory_path(dialog_title="Select Output Folder (Folder B)"),
    )

    # --- Section 3: Execution, Counters & Logs ---
    start_btn = ft.ElevatedButton(
        "Start Batch OCR",
        icon=ft.Icons.PLAY_ARROW,
        bgcolor=ft.Colors.GREEN_700,
        color=ft.Colors.WHITE,
    )
    stop_btn = ft.OutlinedButton(
        "Stop",
        icon=ft.Icons.STOP,
        disabled=True,
    )

    total_stat = ft.Text("Total PDFs in Input: 0", size=13, weight=ft.FontWeight.W_500)
    completed_stat = ft.Text("Already Completed: 0", size=13, weight=ft.FontWeight.W_500)
    pending_stat = ft.Text("Pending: 0", size=13, weight=ft.FontWeight.W_500)
    succeeded_stat = ft.Text("Succeeded: 0", size=13, color=ft.Colors.GREEN_700, weight=ft.FontWeight.W_500)
    failed_stat = ft.Text("Failed: 0", size=13, color=ft.Colors.RED_700, weight=ft.FontWeight.W_500)

    progress_bar = ft.ProgressBar(value=0, visible=False)
    log_list = ft.ListView(expand=True, spacing=4, auto_scroll=True, height=260)

    def append_log(message: str):
        with state["log_lock"]:
            log_list.controls.append(ft.Text(message, size=12, font_family="monospace", selectable=True))
            if len(log_list.controls) > 500:
                log_list.controls.pop(0)
        page.update()

    def refresh_deps(e=None):
        deps = check_system_deps()
        rapid_ok = "Available" if deps["rapidocr"] else "Missing"
        tess_ok = "Available" if deps["tesseract"] else "Not Found"
        gs_ok = "Available" if deps["ghostscript"] else "Not Found"
        ocr_ok = "Available" if deps["ocrmypdf"] else "Not Found"

        deps_status_text.value = (
            f"Built-in RapidOCR: {rapid_ok}  |  "
            f"Tesseract: {tess_ok}  |  "
            f"Ghostscript: {gs_ok}  |  "
            f"OCRmyPDF: {ocr_ok}"
        )
        try:
            resolved = resolve_auto_mode(deps)
            active_backend_text.value = f"Auto mode will currently use: {resolved}"
            active_backend_text.color = ft.Colors.GREEN_700
        except Exception as ex:
            active_backend_text.value = f"No OCR backend ready: {ex}"
            active_backend_text.color = ft.Colors.RED_700
        page.update()

    check_deps_btn.on_click = refresh_deps

    def on_install_deps(e):
        install_deps_btn.disabled = True
        check_deps_btn.disabled = True
        append_log("--- Starting System OCR Tools Installation ---")
        page.update()

        def worker():
            try:
                install_system_deps(log_callback=append_log)
            except Exception as ex:
                append_log(f"[ERROR] Installation error: {ex}")
            finally:
                install_deps_btn.disabled = False
                check_deps_btn.disabled = False
                refresh_deps()

        threading.Thread(target=worker, daemon=True).start()

    install_deps_btn.on_click = on_install_deps

    def set_running_ui(is_running: bool):
        state["running"] = is_running
        start_btn.disabled = is_running
        stop_btn.disabled = not is_running
        input_dir_tf.disabled = is_running
        output_dir_tf.disabled = is_running
        browse_input_btn.disabled = is_running
        browse_output_btn.disabled = is_running
        mode_dropdown.disabled = is_running
        threads_dropdown.disabled = is_running
        resume_checkbox.disabled = is_running
        install_deps_btn.disabled = is_running
        progress_bar.visible = is_running
        page.update()

    def on_stop_click(e):
        state["stop_event"].set()
        stop_btn.disabled = True
        append_log("[INFO] Stop requested — waiting for active worker(s) to finish...")
        page.update()

    stop_btn.on_click = on_stop_click

    def on_start_click(e):
        src_dir = (input_dir_tf.value or "").strip().strip('"').strip("'")
        dst_dir = (output_dir_tf.value or "").strip().strip('"').strip("'")

        if not src_dir or not os.path.isdir(src_dir):
            append_log("[ERROR] Please select a valid Input Folder (Folder A).")
            return
        if not dst_dir:
            append_log("[ERROR] Please select an Output Folder (Folder B).")
            return
        if os.path.abspath(src_dir) == os.path.abspath(dst_dir):
            append_log("[ERROR] Input Folder and Output Folder must be different directories.")
            return

        os.makedirs(dst_dir, exist_ok=True)
        all_pdfs = sorted(
            f for f in os.listdir(src_dir)
            if f.lower().endswith(".pdf") and os.path.isfile(os.path.join(src_dir, f))
        )
        done_pdfs = {
            f for f in os.listdir(dst_dir)
            if f.lower().endswith(".pdf") and not f.startswith("temp_")
        }

        if resume_checkbox.value:
            pending = [f for f in all_pdfs if f not in done_pdfs]
        else:
            pending = list(all_pdfs)

        total_count = len(all_pdfs)
        completed_count = len([f for f in all_pdfs if f in done_pdfs]) if resume_checkbox.value else 0
        pending_count = len(pending)

        total_stat.value = f"Total PDFs in Input: {total_count}"
        completed_stat.value = f"Already Completed: {completed_count}"
        pending_stat.value = f"Pending: {pending_count}"
        succeeded_stat.value = "Succeeded: 0"
        failed_stat.value = "Failed: 0"
        progress_bar.value = 0

        if not pending:
            append_log("[INFO] No pending PDF files found. Everything in Output Folder is up to date.")
            return

        state["stop_event"].clear()
        set_running_ui(True)

        selected_mode = mode_dropdown.value or "auto"
        workers = int(threads_dropdown.value or "2")
        env = get_augmented_env()

        append_log(
            f"=== Starting Batch OCR ({pending_count} pending, {workers} workers, mode={selected_mode}) ==="
        )

        def batch_worker():
            succeeded = 0
            failed = 0
            processed = 0
            counter_lock = threading.Lock()

            def process_one(filename: str):
                if state["stop_event"].is_set():
                    return filename, False, "Cancelled"
                src_path = os.path.join(src_dir, filename)
                dst_path = os.path.join(dst_dir, filename)
                used_mode = ocr_single_pdf(src_path, dst_path, mode=selected_mode, env=env)
                return filename, True, used_mode

            try:
                with ThreadPoolExecutor(max_workers=workers) as executor:
                    futures = {executor.submit(process_one, fname): fname for fname in pending}
                    for fut in as_completed(futures):
                        fname = futures[fut]
                        try:
                            _, ok, detail = fut.result()
                            with counter_lock:
                                processed += 1
                                if ok:
                                    succeeded += 1
                                    msg = f"[OK] {fname} (engine: {detail})"
                                else:
                                    msg = f"[SKIPPED] {fname}: {detail}"
                        except Exception as ex:
                            with counter_lock:
                                processed += 1
                                failed += 1
                                msg = f"[FAIL] {fname}: {ex}"

                        with counter_lock:
                            succeeded_stat.value = f"Succeeded: {succeeded}"
                            failed_stat.value = f"Failed: {failed}"
                            progress_bar.value = processed / pending_count
                        append_log(msg)

                # Post-run verification (equivalent to comm -23 check)
                final_done = {
                    f for f in os.listdir(dst_dir)
                    if f.lower().endswith(".pdf") and not f.startswith("temp_")
                }
                missing = [f for f in all_pdfs if f not in final_done]
                append_log("-" * 58)
                if missing:
                    append_log(f"[WARNING] {len(missing)} file(s) from Input Folder are still missing in Output Folder:")
                    for m in missing[:30]:
                        append_log(f"  - {m}")
                    if len(missing) > 30:
                        append_log(f"  ... and {len(missing) - 30} more")
                else:
                    append_log(f"[VERIFIED] All {len(all_pdfs)} PDF(s) from Input Folder exist in Output Folder.")
            finally:
                set_running_ui(False)

        threading.Thread(target=batch_worker, daemon=True).start()

    start_btn.on_click = on_start_click

    # --- Assemble Layout ---
    page.add(
        ft.Text("MMIWG Batch OCR Processor", size=22, weight=ft.FontWeight.BOLD),
        ft.Text(
            "Batch convert scanned PDFs from Folder A into searchable OCR PDFs in Folder B.",
            size=13,
            color=ft.Colors.GREY_700,
        ),
        ft.Card(
            content=ft.Container(
                padding=15,
                content=ft.Column(
                    [
                        ft.Text("1. OCR Engine & System Dependencies", size=15, weight=ft.FontWeight.BOLD),
                        ft.Row([mode_dropdown, check_deps_btn, install_deps_btn], wrap=True),
                        deps_status_text,
                        active_backend_text,
                    ],
                    spacing=8,
                ),
            )
        ),
        ft.Card(
            content=ft.Container(
                padding=15,
                content=ft.Column(
                    [
                        ft.Text("2. Folder Configuration (Folder A -> Folder B)", size=15, weight=ft.FontWeight.BOLD),
                        ft.Row([input_dir_tf, browse_input_btn]),
                        ft.Row([output_dir_tf, browse_output_btn]),
                        ft.Row([threads_dropdown, resume_checkbox], wrap=True, vertical_alignment=ft.CrossAxisAlignment.CENTER),
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
                        ft.Row([start_btn, stop_btn]),
                        ft.Row(
                            [total_stat, completed_stat, pending_stat, succeeded_stat, failed_stat],
                            spacing=18,
                            wrap=True,
                        ),
                        progress_bar,
                        ft.Container(
                            content=log_list,
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

    refresh_deps()


if __name__ == "__main__":
    ft.app(target=main)
