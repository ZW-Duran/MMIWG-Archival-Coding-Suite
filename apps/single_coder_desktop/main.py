import sys
from pathlib import Path
_REPO_ROOT = str(Path(__file__).resolve().parents[2])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import os
import re
import json
import fitz  # PyMuPDF
import google.generativeai as genai
import flet as ft

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

key_toggle_counter = 0

def clean_and_parse_output(raw_text):
    """清洗 Raw Output，精准切割出 JSON 数据块"""
    if not raw_text:
        return ""
    try:
        clean_text = re.sub(r'```json\s*|\s*```', '', raw_text).strip()
        start_idx = clean_text.find('{')
        end_idx = clean_text.rfind('}')
        if start_idx != -1 and end_idx != -1 and end_idx >= start_idx:
            return clean_text[start_idx : end_idx + 1]
        return clean_text
    except Exception:
        return raw_text

def run_single_document_analysis(text, selected_prompt, model_name, api_key_1, api_key_2):
    """执行 AI 模型单文档编码分析 (支持双 API Key 轮询)"""
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
            generation_config=genai.types.GenerationConfig(
                temperature=0.0
            )
        )
        return response.text, key_label, None
    except Exception as e:
        return None, key_label, str(e)

# ==============================================================================
# 3. Flet 主界面 (GUI Layout)
# ==============================================================================
def main(page: ft.Page):
    page.title = "📰 News Text Quantitative Coding Tool (Flet Single Doc)"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.padding = 20
    page.scroll = ft.ScrollMode.AUTO

    # --- UI 控件定义 ---
    task_dropdown = ft.Dropdown(
        label="Select Coding Part:",
        options=[ft.dropdown.Option(k) for k in PROMPTS.keys()],
        value="Part 1",
        width=250,
    )

    model_dropdown = ft.Dropdown(
        label="Select Model:",
        options=[ft.dropdown.Option(m) for m in MODEL_OPTIONS_PER_PART["Part 1"]],
        value=DEFAULT_MODEL_PER_PART["Part 1"],
        width=250,
    )

    api_key_1_input = ft.TextField(
        label="API Key 1 (Primary):",
        password=True,
        can_reveal_password=True,
        hint_text="Required Google AI Studio API Key",
    )

    api_key_2_input = ft.TextField(
        label="API Key 2 (Backup / Optional):",
        password=True,
        can_reveal_password=True,
        hint_text="Optional: Alternate requests to bypass quota limits",
    )

    article_text_input = ft.TextField(
        label="Article Content (Paste text or pick a PDF file):",
        multiline=True,
        min_lines=12,
        max_lines=20,
        hint_text="Enter or paste article text here...",
    )

    status_text = ft.Text("", size=14, weight=ft.FontWeight.BOLD, color="blue")
    progress_ring = ft.ProgressRing(visible=False, width=24, height=24)

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

    toggle_log_btn = ft.ElevatedButton("Show Raw Output Log", icon=ft.Icons.SUBTITLES)

    def on_toggle_raw_log(e):
        raw_log_field.visible = not raw_log_field.visible
        toggle_log_btn.text = "Hide Raw Output Log" if raw_log_field.visible else "Show Raw Output Log"
        page.update()

    toggle_log_btn.on_click = on_toggle_raw_log

    # --- 任务切换时动态联动更新模型选项 ---
    def on_task_changed(e):
        part = task_dropdown.value
        allowed_models = MODEL_OPTIONS_PER_PART.get(part, [])
        model_dropdown.options = [ft.dropdown.Option(m) for m in allowed_models]
        model_dropdown.value = DEFAULT_MODEL_PER_PART.get(part, allowed_models[0] if allowed_models else "")
        page.update()

    task_dropdown.on_change = on_task_changed

    # --- FilePicker (PDF 读取支持) ---
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
                        status_text.value = f"✅ Successfully loaded PDF text: {os.path.basename(picked_path)}"
                        status_text.color = "green"
                    else:
                        status_text.value = f"⚠️ Warning: No readable text found in PDF: {os.path.basename(picked_path)}"
                        status_text.color = "orange"
                except Exception as err:
                    status_text.value = f"❌ Failed to read PDF: {err}"
                    status_text.color = "red"
                page.update()

    file_picker = ft.FilePicker(on_result=on_file_picked)
    page.overlay.append(file_picker)

    btn_pick_pdf = ft.ElevatedButton(
        "Upload/Select Local PDF File",
        icon=ft.Icons.PICTURE_AS_PDF,
        on_click=lambda _: file_picker.pick_files(allow_multiple=False, allowed_extensions=["pdf"]),
    )

    # --- 执行分析按钮逻辑 ---
    def on_start_analysis(e):
        key1 = api_key_1_input.value or ""
        key2 = api_key_2_input.value or ""
        text = article_text_input.value or ""
        part = task_dropdown.value
        selected_model = model_dropdown.value

        if not key1.strip():
            status_text.value = "⚠️ Error: Please provide API Key 1 in the configuration panel."
            status_text.color = "red"
            page.update()
            return

        if not text.strip():
            status_text.value = "⚠️ Error: Article text is empty. Please paste text or select a PDF file."
            status_text.color = "red"
            page.update()
            return

        status_text.value = f"🚀 Analyzing using [{selected_model}] on [{part}]..."
        status_text.color = "blue"
        progress_ring.visible = True
        page.update()

        # 运行 LLM 分析
        active_prompt = PROMPTS[part]
        raw_res, channel, err = run_single_document_analysis(
            text, active_prompt, selected_model, key1, key2
        )

        progress_ring.visible = False

        if err:
            status_text.value = f"❌ API Error via [{channel}]: {err}"
            status_text.color = "red"
        else:
            status_text.value = f"🎉 Analysis Complete! (Channel: {channel})"
            status_text.color = "green"
            clean_json = clean_and_parse_output(raw_res)
            output_code_field.value = clean_json
            raw_log_field.value = raw_res or ""

        page.update()

    btn_run = ft.ElevatedButton(
        "🚀 Start Analysis",
        icon=ft.Icons.PLAY_ARROW,
        on_click=on_start_analysis,
        style=ft.ButtonStyle(color="white", bgcolor="blue"),
    )

    # --- 布局结构 ---
    header_card = ft.Card(
        content=ft.Container(
            content=ft.Column(
                [
                    ft.Text("📰 One-Touch News Text Quantitative Coding Tool", size=22, weight=ft.FontWeight.BOLD),
                    ft.Text("Select task part and model, input API keys, upload a PDF or paste article text to analyze.", color="gray"),
                ]
            ),
            padding=15,
        )
    )

    config_row = ft.Row([task_dropdown, model_dropdown, btn_pick_pdf], alignment=ft.MainAxisAlignment.START, wrap=True)
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
        output_code_field,
        ft.Row([toggle_log_btn]),
        raw_log_field,
    )

if __name__ == "__main__":
    ft.app(target=main)