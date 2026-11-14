import multiprocessing
import sys
from pathlib import Path

if __name__ == "__main__":
    multiprocessing.freeze_support()

if not getattr(sys, "frozen", False):
    _REPO_ROOT = str(Path(__file__).resolve().parents[2])
    if _REPO_ROOT not in sys.path:
        sys.path.insert(0, _REPO_ROOT)

import json
import os
import re
import threading
import fitz  # PyMuPDF
import flet as ft
import google.generativeai as genai

from core.prompts import BATCH_PROMPTS, WEB_PROMPTS

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

key_toggle_counter = 0


def clean_and_parse_output(raw_text):
    """Extract the JSON block from raw LLM output."""
    if not raw_text:
        return ""
    try:
        clean_text = re.sub(r"```json\s*|\s*```", "", raw_text).strip()
        start_idx = clean_text.find("{")
        end_idx = clean_text.rfind("}")
        if start_idx != -1 and end_idx != -1 and end_idx >= start_idx:
            return clean_text[start_idx : end_idx + 1]
        return clean_text
    except Exception:
        return raw_text


def _normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip().lower()


def extract_evidence_rows(parsed_json: dict, source_text: str) -> list:
    """Build cross-reference verification rows from Part 1-4 JSON output."""
    if not isinstance(parsed_json, dict):
        return []

    norm_source = _normalize_ws(source_text)
    rows = []

    def check_quote(quote: str):
        q = str(quote or "").strip()
        if not q:
            return "—", ft.Colors.GREY_600
        if _normalize_ws(q) in norm_source:
            return "Verified in text", ft.Colors.GREEN_700
        return "Quote check / paraphrased", ft.Colors.ORANGE_700

    # Handle Part 4 structure (victims list + suspect_info + counts)
    if "victims" in parsed_json or "suspect_info" in parsed_json:
        for idx, victim in enumerate(parsed_json.get("victims", []), start=1):
            if not isinstance(victim, dict):
                continue
            label = f"Victim #{idx} ({victim.get('name', 'Unknown')})"
            val = f"{victim.get('status', 'unknown')} | {victim.get('gender', 'unknown')} | {victim.get('race', 'Unknown')}"
            ev = str(victim.get("evidence", "") or "").strip()
            status, color = check_quote(ev)
            rows.append({"variable": label, "value": val, "evidence": ev, "status": status, "color": color})

        suspect = parsed_json.get("suspect_info")
        if isinstance(suspect, dict):
            ev = str(suspect.get("evidence", "") or "").strip()
            status, color = check_quote(ev)
            val = f"count={suspect.get('perpetrators_count', 0)}, race={suspect.get('perpetrators_race', '') or 'N/A'}"
            rows.append({"variable": "suspect_info", "value": val, "evidence": ev, "status": status, "color": color})
        return rows

    # Handle Part 1, Part 2, Part 3 structures
    for key, item in parsed_json.items():
        if isinstance(item, dict):
            val = item.get("value", item.get("count", ""))
            ev = str(item.get("evidence", "") or "").strip()
            status, color = check_quote(ev)
            rows.append({"variable": key, "value": str(val), "evidence": ev, "status": status, "color": color})
        else:
            rows.append({"variable": key, "value": str(item), "evidence": "", "status": "—", "color": ft.Colors.GREY_600})

    return rows


def run_single_document_analysis(text, selected_prompt, model_name, api_key_1, api_key_2):
    """Execute single-document Gemini coding with optional dual-key round-robin."""
    global key_toggle_counter
    prompt = f"{selected_prompt}\n\nArticle Text:\n{text}"

    if not api_key_2 or not api_key_2.strip():
        current_api_key = api_key_1.strip()
        key_label = "Key 1 (Single)"
    else:
        if key_toggle_counter % 2 == 0:
            current_api_key = api_key_1.strip()
            key_label = "Key 1 (Dual Alternate)"
        else:
            current_api_key = api_key_2.strip()
            key_label = "Key 2 (Dual Alternate)"
        key_toggle_counter += 1

    try:
        genai.configure(api_key=current_api_key)
        model = genai.GenerativeModel(model_name)

        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(temperature=0.0),
        )
        return response.text, key_label, None
    except Exception as e:
        return None, key_label, str(e)


def main(page: ft.Page):
    page.title = "MMIWG Single-Article Quantitative Coder (Desktop)"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.padding = 20
    page.scroll = ft.ScrollMode.AUTO

    # --- UI Controls ---
    task_dropdown = ft.Dropdown(
        label="Select Coding Part:",
        options=[ft.dropdown.Option(k) for k in BATCH_PROMPTS.keys()],
        value="Part 1",
        width=220,
    )

    model_dropdown = ft.Dropdown(
        label="Select Model:",
        options=[ft.dropdown.Option(m) for m in MODEL_OPTIONS_PER_PART["Part 1"]],
        value=DEFAULT_MODEL_PER_PART["Part 1"],
        width=240,
    )

    evidence_checkbox = ft.Checkbox(
        label="Include Verbatim Evidence for Cross-Referencing",
        value=True,
    )

    api_key_1_input = ft.TextField(
        label="API Key 1 (Primary):",
        password=True,
        can_reveal_password=True,
        hint_text="Required Google AI Studio API Key",
        expand=True,
    )

    api_key_2_input = ft.TextField(
        label="API Key 2 (Backup / Optional):",
        password=True,
        can_reveal_password=True,
        hint_text="Optional: Alternate requests to bypass quota limits",
        expand=True,
    )

    article_text_input = ft.TextField(
        label="Article Content (Paste text or pick a PDF file):",
        multiline=True,
        min_lines=10,
        max_lines=18,
        hint_text="Enter or paste article text here...",
    )

    status_text = ft.Text("", size=14, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_700)
    progress_ring = ft.ProgressRing(visible=False, width=24, height=24)

    # Cross-reference evidence verification table
    evidence_table = ft.DataTable(
        columns=[
            ft.DataColumn(ft.Text("Variable", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("Coded Value", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("Cross-Ref Status", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("Verbatim Evidence Quote", weight=ft.FontWeight.BOLD)),
        ],
        rows=[],
        column_spacing=20,
        data_row_min_height=40,
        data_row_max_height=140,
        heading_row_color=ft.Colors.GREY_100,
    )

    evidence_card = ft.Card(
        visible=False,
        content=ft.Container(
            padding=15,
            content=ft.Column(
                [
                    ft.Text(
                        "Cross-Reference Evidence Verification",
                        size=16,
                        weight=ft.FontWeight.BOLD,
                    ),
                    ft.Text(
                        "Automatically checks each returned verbatim quote against the source article text.",
                        size=12,
                        color=ft.Colors.GREY_700,
                    ),
                    ft.Row([evidence_table], scroll=ft.ScrollMode.AUTO),
                ],
                spacing=8,
            ),
        ),
    )

    output_code_field = ft.TextField(
        label="Structured JSON Result:",
        multiline=True,
        read_only=True,
        min_lines=8,
        max_lines=15,
        value="",
    )

    raw_log_field = ft.TextField(
        label="Raw Model Output Log:",
        multiline=True,
        read_only=True,
        min_lines=4,
        max_lines=10,
        value="",
        visible=False,
    )

    def populate_evidence_table(clean_json: str, source_text: str):
        evidence_table.rows.clear()
        try:
            parsed = json.loads(clean_json)
            rows = extract_evidence_rows(parsed, source_text)
            for r in rows:
                evidence_table.rows.append(
                    ft.DataRow(
                        cells=[
                            ft.DataCell(ft.Text(r["variable"], size=12, weight=ft.FontWeight.W_500)),
                            ft.DataCell(ft.Text(r["value"], size=12)),
                            ft.DataCell(ft.Text(r["status"], size=12, color=r["color"], weight=ft.FontWeight.W_500)),
                            ft.DataCell(
                                ft.Container(
                                    width=460,
                                    content=ft.Text(r["evidence"] or "—", size=12, selectable=True),
                                )
                            ),
                        ]
                    )
                )
            evidence_card.visible = len(rows) > 0
        except Exception:
            evidence_card.visible = False

    toggle_log_btn = ft.ElevatedButton("Show Raw Output Log", icon=ft.Icons.SUBTITLES)

    def on_toggle_raw_log(e):
        raw_log_field.visible = not raw_log_field.visible
        toggle_log_btn.text = "Hide Raw Output Log" if raw_log_field.visible else "Show Raw Output Log"
        page.update()

    toggle_log_btn.on_click = on_toggle_raw_log

    def on_copy_json(e):
        if output_code_field.value:
            page.set_clipboard(output_code_field.value)
            status_text.value = "Structured JSON copied to clipboard."
            status_text.color = ft.Colors.GREEN_700
            page.update()

    copy_json_btn = ft.OutlinedButton("Copy JSON", icon=ft.Icons.COPY, on_click=on_copy_json)

    def on_save_json_picked(e: ft.FilePickerResultEvent):
        if e.path and output_code_field.value:
            with open(e.path, "w", encoding="utf-8") as f:
                f.write(output_code_field.value)
            status_text.value = f"Saved JSON results to: {e.path}"
            status_text.color = ft.Colors.GREEN_700
            page.update()

    save_json_picker = ft.FilePicker(on_result=on_save_json_picked)
    page.overlay.append(save_json_picker)

    save_json_btn = ft.OutlinedButton(
        "Save JSON",
        icon=ft.Icons.SAVE,
        on_click=lambda _: save_json_picker.save_file(
            dialog_title="Save Coding Output JSON",
            file_name="coding_output.json",
            allowed_extensions=["json"],
        ),
    )

    def on_task_changed(e):
        part = task_dropdown.value
        allowed_models = MODEL_OPTIONS_PER_PART.get(part, [])
        model_dropdown.options = [ft.dropdown.Option(m) for m in allowed_models]
        model_dropdown.value = DEFAULT_MODEL_PER_PART.get(part, allowed_models[0] if allowed_models else "")
        page.update()

    task_dropdown.on_change = on_task_changed

    # --- FilePicker (PDF Extraction) ---
    def on_file_picked(e: ft.FilePickerResultEvent):
        if e.files and len(e.files) > 0:
            picked_path = e.files[0].path
            if picked_path and picked_path.lower().endswith(".pdf"):
                try:
                    doc = fitz.open(picked_path)
                    blocks_text = []
                    for p in doc:
                        for b in p.get_text("blocks"):
                            if b[4].strip():
                                blocks_text.append(b[4].strip())
                    doc.close()
                    extracted_text = "\n\n".join(blocks_text)
                    if extracted_text.strip():
                        article_text_input.value = extracted_text
                        status_text.value = f"Loaded PDF text: {os.path.basename(picked_path)}"
                        status_text.color = ft.Colors.GREEN_700
                    else:
                        status_text.value = f"Warning: No readable text found in PDF: {os.path.basename(picked_path)}"
                        status_text.color = ft.Colors.ORANGE_700
                except Exception as err:
                    status_text.value = f"Failed to read PDF: {err}"
                    status_text.color = ft.Colors.RED_700
                page.update()

    file_picker = ft.FilePicker(on_result=on_file_picked)
    page.overlay.append(file_picker)

    btn_pick_pdf = ft.ElevatedButton(
        "Upload/Select Local PDF File",
        icon=ft.Icons.PICTURE_AS_PDF,
        on_click=lambda _: file_picker.pick_files(allow_multiple=False, allowed_extensions=["pdf"]),
    )

    def on_start_analysis(e):
        key1 = api_key_1_input.value or ""
        key2 = api_key_2_input.value or ""
        text = article_text_input.value or ""
        part = task_dropdown.value
        selected_model = model_dropdown.value
        include_evidence = bool(evidence_checkbox.value)

        if not key1.strip():
            status_text.value = "Error: Please provide API Key 1 in the configuration panel."
            status_text.color = ft.Colors.RED_700
            page.update()
            return

        if not text.strip():
            status_text.value = "Error: Article text is empty. Please paste text or select a PDF file."
            status_text.color = ft.Colors.RED_700
            page.update()
            return

        btn_run.disabled = True
        status_text.value = f"Analyzing using [{selected_model}] on [{part}]..."
        status_text.color = ft.Colors.BLUE_700
        progress_ring.visible = True
        page.update()

        prompt_map = WEB_PROMPTS if include_evidence else BATCH_PROMPTS
        active_prompt = prompt_map.get(part, BATCH_PROMPTS[part])

        def worker():
            try:
                raw_res, channel, err = run_single_document_analysis(
                    text, active_prompt, selected_model, key1, key2
                )
                if err:
                    status_text.value = f"API Error via [{channel}]: {err}"
                    status_text.color = ft.Colors.RED_700
                    evidence_card.visible = False
                else:
                    status_text.value = f"Analysis Complete! (Channel: {channel})"
                    status_text.color = ft.Colors.GREEN_700
                    clean_json = clean_and_parse_output(raw_res)
                    output_code_field.value = clean_json
                    raw_log_field.value = raw_res or ""
                    populate_evidence_table(clean_json, text)
            finally:
                progress_ring.visible = False
                btn_run.disabled = False
                page.update()

        threading.Thread(target=worker, daemon=True).start()

    btn_run = ft.ElevatedButton(
        "Start Analysis",
        icon=ft.Icons.PLAY_ARROW,
        on_click=on_start_analysis,
        style=ft.ButtonStyle(color=ft.Colors.WHITE, bgcolor=ft.Colors.BLUE_700),
    )

    header_card = ft.Card(
        content=ft.Container(
            content=ft.Column(
                [
                    ft.Text("One-Touch News Text Quantitative Coding Tool", size=22, weight=ft.FontWeight.BOLD),
                    ft.Text(
                        "Fast-track single-article coding with verbatim evidence cross-referencing.",
                        color=ft.Colors.GREY_700,
                    ),
                ]
            ),
            padding=15,
        )
    )

    config_row = ft.Row(
        [task_dropdown, model_dropdown, btn_pick_pdf, evidence_checkbox],
        alignment=ft.MainAxisAlignment.START,
        wrap=True,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )
    keys_row = ft.Row([api_key_1_input, api_key_2_input], alignment=ft.MainAxisAlignment.START, wrap=True)
    action_row = ft.Row([btn_run, progress_ring, status_text], alignment=ft.MainAxisAlignment.START)

    page.add(
        header_card,
        ft.Divider(),
        config_row,
        keys_row,
        ft.Divider(),
        article_text_input,
        action_row,
        ft.Divider(),
        evidence_card,
        output_code_field,
        ft.Row([copy_json_btn, save_json_btn, toggle_log_btn], wrap=True),
        raw_log_field,
    )


if __name__ == "__main__":
    ft.app(target=main)
