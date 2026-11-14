import multiprocessing
import sys
from pathlib import Path

if __name__ == "__main__":
    multiprocessing.freeze_support()

if not getattr(sys, "frozen", False):
    _REPO_ROOT = str(Path(__file__).resolve().parents[2])
    if _REPO_ROOT not in sys.path:
        sys.path.insert(0, _REPO_ROOT)

import base64
import os
import platform
import shutil
import subprocess
import tempfile
import threading
import time
import fitz  # PyMuPDF
import flet as ft

from core.ner_highlighter import highlight_pdf_entities
from core.pdf_utils import extract_newsbank_metadata

try:
    from apps.highlighter_desktop.model_manager import (
        MODEL_CATALOG,
        download_and_install_model,
        is_model_installed,
        load_models_dir,
        load_spacy_model,
        save_models_dir,
    )
except ImportError:
    from model_manager import (
        MODEL_CATALOG,
        download_and_install_model,
        is_model_installed,
        load_models_dir,
        load_spacy_model,
        save_models_dir,
    )


def open_file_externally(file_path: str) -> None:
    """Open a file using the operating system's default application."""
    system = platform.system()
    if system == "Windows":
        os.startfile(file_path)  # type: ignore[attr-defined]
    elif system == "Darwin":
        subprocess.Popen(["open", file_path])
    else:
        subprocess.Popen(["xdg-open", file_path])


def main(page: ft.Page):
    page.title = "MMIWG Semantic Highlighter (Desktop)"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.padding = 20
    page.scroll = ft.ScrollMode.AUTO
    page.window.width = 1080
    page.window.height = 860

    state = {
        "models_dir": load_models_dir(),
        "loaded_model_name": None,
        "nlp": None,
        "pdf_path": None,
        "output_pdf_path": None,
        "preview_pages": [],  # list of base64 PNG strings
        "current_page_idx": 0,
        "rules": [
            {"label": "GPE", "color": "(0, 1, 1)"},
            {"label": "PERSON", "color": "(1, 0, 0)"},
        ],
    }

    # --- Model Controls ---
    model_dropdown = ft.Dropdown(
        label="spaCy Model",
        options=[ft.dropdown.Option(key=k, text=v) for k, v in MODEL_CATALOG.items()],
        value="en_core_web_sm",
        width=320,
    )
    model_status_text = ft.Text("", size=13, weight=ft.FontWeight.W_500)
    models_dir_text = ft.Text(
        f"Model Folder: {state['models_dir']}",
        size=12,
        color=ft.Colors.GREY_700,
        selectable=True,
    )
    model_progress = ft.ProgressBar(value=0, visible=False, width=400)
    download_btn = ft.ElevatedButton(
        "Download & Load Model",
        icon=ft.Icons.DOWNLOAD,
        bgcolor=ft.Colors.BLUE_700,
        color=ft.Colors.WHITE,
    )
    change_dir_btn = ft.OutlinedButton(
        "Change Folder",
        icon=ft.Icons.FOLDER_OPEN,
    )

    def refresh_model_status():
        model_name = model_dropdown.value
        installed = is_model_installed(model_name, state["models_dir"])
        if state["loaded_model_name"] == model_name and state["nlp"] is not None:
            model_status_text.value = f"Ready in memory ({model_name})"
            model_status_text.color = ft.Colors.GREEN_700
            download_btn.text = "Reload Model"
        elif installed:
            model_status_text.value = f"Installed locally ({model_name}) — click to load"
            model_status_text.color = ft.Colors.BLUE_700
            download_btn.text = "Load Model"
        else:
            model_status_text.value = f"Not downloaded ({model_name})"
            model_status_text.color = ft.Colors.ORANGE_700
            download_btn.text = "Download & Load Model"
        models_dir_text.value = f"Model Folder: {state['models_dir']}"
        page.update()

    def on_model_dropdown_change(e):
        refresh_model_status()

    model_dropdown.on_change = on_model_dropdown_change

    def on_folder_picked(e: ft.FilePickerResultEvent):
        if e.path:
            state["models_dir"] = Path(e.path)
            save_models_dir(state["models_dir"])
            state["nlp"] = None
            state["loaded_model_name"] = None
            refresh_model_status()

    folder_picker = ft.FilePicker(on_result=on_folder_picked)
    page.overlay.append(folder_picker)
    change_dir_btn.on_click = lambda _: folder_picker.get_directory_path(
        dialog_title="Select Folder to Store spaCy Models"
    )

    def on_download_or_load(e):
        model_name = model_dropdown.value
        download_btn.disabled = True
        change_dir_btn.disabled = True
        model_dropdown.disabled = True
        model_progress.visible = True
        model_progress.value = None  # indeterminate initially
        page.update()

        def worker():
            try:
                if not is_model_installed(model_name, state["models_dir"]):
                    def update_prog(frac):
                        model_progress.value = frac
                        page.update()

                    def update_status(msg):
                        model_status_text.value = msg
                        model_status_text.color = ft.Colors.BLUE_700
                        page.update()

                    download_and_install_model(
                        model_name,
                        state["models_dir"],
                        progress_callback=update_prog,
                        status_callback=update_status,
                    )

                model_status_text.value = f"Loading {model_name} into memory..."
                model_status_text.color = ft.Colors.BLUE_700
                model_progress.value = None
                page.update()

                state["nlp"] = load_spacy_model(model_name, state["models_dir"])
                state["loaded_model_name"] = model_name
            except Exception as ex:
                model_status_text.value = f"Error: {ex}"
                model_status_text.color = ft.Colors.RED_700
            finally:
                download_btn.disabled = False
                change_dir_btn.disabled = False
                model_dropdown.disabled = False
                model_progress.visible = False
                refresh_model_status()

        threading.Thread(target=worker, daemon=True).start()

    download_btn.on_click = on_download_or_load

    # --- NER Rules Controls ---
    rules_column = ft.Column(spacing=8)

    def rebuild_rules_ui():
        rules_column.controls.clear()
        for idx, rule in enumerate(state["rules"]):
            label_tf = ft.TextField(
                label="Entity Label (e.g., PERSON, GPE, ORG)",
                value=rule["label"],
                width=260,
                dense=True,
                on_change=lambda ev, i=idx: state["rules"][i].__setitem__("label", ev.control.value),
            )
            color_tf = ft.TextField(
                label="RGB (0-1, 0-1, 0-1)",
                value=rule["color"],
                width=180,
                dense=True,
                on_change=lambda ev, i=idx: state["rules"][i].__setitem__("color", ev.control.value),
            )
            del_btn = ft.IconButton(
                icon=ft.Icons.DELETE_OUTLINE,
                tooltip="Remove rule",
                on_click=lambda ev, i=idx: remove_rule(i),
            )
            rules_column.controls.append(
                ft.Row([label_tf, color_tf, del_btn], vertical_alignment=ft.CrossAxisAlignment.CENTER)
            )
        page.update()

    def remove_rule(idx: int):
        if len(state["rules"]) > 1:
            state["rules"].pop(idx)
            rebuild_rules_ui()

    def add_rule(e):
        state["rules"].append({"label": "ORG", "color": "(0, 0, 1)"})
        rebuild_rules_ui()

    add_rule_btn = ft.TextButton("Add Highlight Rule", icon=ft.Icons.ADD, on_click=add_rule)

    # --- PDF Selection & Processing ---
    selected_pdf_text = ft.Text("No PDF selected.", size=13, color=ft.Colors.GREY_700)
    run_status_text = ft.Text("", size=13)
    run_progress = ft.ProgressBar(value=0, visible=False, width=450)

    def on_pdf_picked(e: ft.FilePickerResultEvent):
        if e.files:
            state["pdf_path"] = e.files[0].path
            selected_pdf_text.value = f"Selected: {e.files[0].name} ({state['pdf_path']})"
            selected_pdf_text.color = ft.Colors.BLACK87
            page.update()

    pdf_picker = ft.FilePicker(on_result=on_pdf_picked)
    page.overlay.append(pdf_picker)

    select_pdf_btn = ft.ElevatedButton(
        "Select PDF",
        icon=ft.Icons.UPLOAD_FILE,
        on_click=lambda _: pdf_picker.pick_files(
            allow_multiple=False,
            allowed_extensions=["pdf"],
            dialog_title="Select PDF to Highlight",
        ),
    )

    run_btn = ft.ElevatedButton(
        "Run NER Highlighting",
        icon=ft.Icons.AUTO_FIX_HIGH,
        bgcolor=ft.Colors.GREEN_700,
        color=ft.Colors.WHITE,
    )

    # --- Metadata & Preview Controls ---
    METADATA_KEYS = [
        "Author last",
        "Author First",
        "Other Authors (if any)",
        "Newspaper/Publisher",
        "Publication Year",
        "Article Title",
        "Publication Location",
        "Contextual Location",
        "News Source",
        "Date of publication",
        "page (if any)",
    ]
    meta_fields = {
        key: ft.TextField(
            label=key,
            width=260 if key in ("Article Title", "Newspaper/Publisher", "Other Authors (if any)") else 180,
            dense=True,
        )
        for key in METADATA_KEYS
    }

    def copy_metadata_tsv(e):
        tsv = "\t".join((meta_fields[k].value or "").replace("\t", " ") for k in METADATA_KEYS)
        page.set_clipboard(tsv)
        run_status_text.value = "All 11 metadata columns copied to clipboard (TSV for Google Sheets / Excel)."
        run_status_text.color = ft.Colors.GREEN_700
        page.update()

    copy_meta_btn = ft.OutlinedButton(
        "Copy Metadata (TSV)",
        icon=ft.Icons.COPY,
        on_click=copy_metadata_tsv,
    )

    def on_save_picked(e: ft.FilePickerResultEvent):
        if e.path and state["output_pdf_path"] and os.path.exists(state["output_pdf_path"]):
            shutil.copyfile(state["output_pdf_path"], e.path)
            run_status_text.value = f"Saved highlighted PDF to: {e.path}"
            run_status_text.color = ft.Colors.GREEN_700
            page.update()

    save_picker = ft.FilePicker(on_result=on_save_picked)
    page.overlay.append(save_picker)

    save_pdf_btn = ft.ElevatedButton(
        "Save Highlighted PDF",
        icon=ft.Icons.SAVE,
        disabled=True,
        on_click=lambda _: save_picker.save_file(
            dialog_title="Save Highlighted PDF",
            file_name=f"highlighted_{Path(state['pdf_path']).name}" if state["pdf_path"] else "highlighted.pdf",
            allowed_extensions=["pdf"],
        ),
    )

    open_external_btn = ft.OutlinedButton(
        "Open in Default PDF Viewer",
        icon=ft.Icons.OPEN_IN_NEW,
        disabled=True,
        on_click=lambda _: open_file_externally(state["output_pdf_path"]) if state["output_pdf_path"] else None,
    )

    preview_image = ft.Image(src_base64="", visible=False, fit=ft.ImageFit.CONTAIN, width=820)
    page_indicator = ft.Text("", size=13)
    prev_page_btn = ft.IconButton(icon=ft.Icons.CHEVRON_LEFT, disabled=True)
    next_page_btn = ft.IconButton(icon=ft.Icons.CHEVRON_RIGHT, disabled=True)

    def update_preview():
        pages = state["preview_pages"]
        idx = state["current_page_idx"]
        if not pages:
            preview_image.visible = False
            page_indicator.value = ""
            prev_page_btn.disabled = True
            next_page_btn.disabled = True
        else:
            preview_image.src_base64 = pages[idx]
            preview_image.visible = True
            page_indicator.value = f"Page {idx + 1} of {len(pages)}"
            prev_page_btn.disabled = idx <= 0
            next_page_btn.disabled = idx >= len(pages) - 1
        page.update()

    def go_prev_page(e):
        if state["current_page_idx"] > 0:
            state["current_page_idx"] -= 1
            update_preview()

    def go_next_page(e):
        if state["current_page_idx"] < len(state["preview_pages"]) - 1:
            state["current_page_idx"] += 1
            update_preview()

    prev_page_btn.on_click = go_prev_page
    next_page_btn.on_click = go_next_page

    results_section = ft.Column(visible=False, spacing=12)

    def on_run_highlighting(e):
        if state["nlp"] is None:
            run_status_text.value = "Please download and load a spaCy model first."
            run_status_text.color = ft.Colors.RED_700
            page.update()
            return
        if not state["pdf_path"] or not os.path.exists(state["pdf_path"]):
            run_status_text.value = "Please select a valid PDF file first."
            run_status_text.color = ft.Colors.RED_700
            page.update()
            return

        run_btn.disabled = True
        run_progress.visible = True
        run_progress.value = 0
        run_status_text.value = "Extracting metadata and highlighting entities..."
        run_status_text.color = ft.Colors.BLUE_700
        page.update()

        def worker():
            try:
                doc = fitz.open(state["pdf_path"])
                metadata = extract_newsbank_metadata(doc)

                def on_prog(frac):
                    run_progress.value = frac
                    page.update()

                highlight_pdf_entities(
                    doc,
                    state["nlp"],
                    state["rules"],
                    progress_callback=on_prog,
                )

                out_dir = Path(tempfile.gettempdir()) / "mmiwg_highlighter_cache"
                out_dir.mkdir(parents=True, exist_ok=True)
                out_path = out_dir / f"highlighted_{int(time.time())}_{Path(state['pdf_path']).name}"
                doc.save(str(out_path))

                rendered_pages = []
                for p in doc:
                    pix = p.get_pixmap(dpi=150)
                    rendered_pages.append(base64.b64encode(pix.tobytes("png")).decode("utf-8"))
                doc.close()

                state["output_pdf_path"] = str(out_path)
                state["preview_pages"] = rendered_pages
                state["current_page_idx"] = 0

                for key in METADATA_KEYS:
                    meta_fields[key].value = str(metadata.get(key, "") or "")

                save_pdf_btn.disabled = False
                open_external_btn.disabled = False
                results_section.visible = True
                run_status_text.value = "Highlighting complete!"
                run_status_text.color = ft.Colors.GREEN_700
                update_preview()
            except Exception as ex:
                run_status_text.value = f"Error: {ex}"
                run_status_text.color = ft.Colors.RED_700
            finally:
                run_btn.disabled = False
                run_progress.visible = False
                page.update()

        threading.Thread(target=worker, daemon=True).start()

    run_btn.on_click = on_run_highlighting

    results_section.controls = [
        ft.Divider(),
        ft.Text("Extracted NewsBank Metadata (Editable)", size=16, weight=ft.FontWeight.BOLD),
        ft.Row([*meta_fields.values(), copy_meta_btn], wrap=True),
        ft.Row([save_pdf_btn, open_external_btn]),
        ft.Row([prev_page_btn, page_indicator, next_page_btn], alignment=ft.MainAxisAlignment.CENTER),
        ft.Container(
            content=preview_image,
            alignment=ft.alignment.center,
            border=ft.border.all(1, ft.Colors.GREY_300),
            border_radius=6,
            padding=8,
        ),
    ]

    # --- Assemble Layout ---
    page.add(
        ft.Text("MMIWG Semantic Highlighter (Desktop)", size=22, weight=ft.FontWeight.BOLD),
        ft.Text(
            "Manual screening assistant: highlight NER entities in PDFs and extract NewsBank metadata.",
            size=13,
            color=ft.Colors.GREY_700,
        ),
        ft.Card(
            content=ft.Container(
                padding=15,
                content=ft.Column(
                    [
                        ft.Text("1. spaCy Model Setup (On-Demand Download)", size=15, weight=ft.FontWeight.BOLD),
                        ft.Row([model_dropdown, download_btn, change_dir_btn], wrap=True),
                        models_dir_text,
                        model_status_text,
                        model_progress,
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
                        ft.Text("2. Custom Entity Highlighting Rules", size=15, weight=ft.FontWeight.BOLD),
                        rules_column,
                        add_rule_btn,
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
                        ft.Text("3. Select PDF & Run", size=15, weight=ft.FontWeight.BOLD),
                        ft.Row([select_pdf_btn, run_btn], wrap=True),
                        selected_pdf_text,
                        run_progress,
                        run_status_text,
                    ],
                    spacing=8,
                ),
            )
        ),
        results_section,
    )

    rebuild_rules_ui()
    refresh_model_status()


if __name__ == "__main__":
    ft.app(target=main)
