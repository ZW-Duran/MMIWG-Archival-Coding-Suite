import sys
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parents[2])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import streamlit as st
import fitz  # PyMuPDF
import spacy
import os
import tempfile
import base64
import time
import pandas as pd

from core.pdf_utils import extract_newsbank_metadata as extract_metadata
from core.ner_highlighter import highlight_pdf_entities

# --- 1. 初始化配置 ---
CACHE_DIR = "output_cache"
if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR)

st.set_page_config(page_title="Indigenous News Semantic Highlighter", layout="wide")

@st.cache_resource
def load_model():
    return spacy.load("en_core_web_trf")

nlp = load_model()

# --- 2. 逻辑函数 ---
def display_pdf(file_path):
    with open(file_path, "rb") as f:
        base64_pdf = base64.b64encode(f.read()).decode('utf-8')
    pdf_display = f'<iframe src="data:application/pdf;base64,{base64_pdf}" width="100%" height="1000" type="application/pdf"></iframe>'
    st.markdown(pdf_display, unsafe_allow_html=True)

# --- 3. 页面布局 ---
st.title("Semantic Enhancement Reader")

# 初始化 session_state，用于存储“已处理完成”的状态
if 'processed_data' not in st.session_state:
    st.session_state.processed_data = None

# --- 4. 侧边栏 ---
with st.sidebar:
    access_code = st.text_input("Access Code", type="password")
    if access_code != "MMIWG":
        st.warning("Please Provide Correct Password")
        st.stop()

    st.header("Custom Highlighting Rules")
    st.markdown("""
    **Instructions:**
    * **Label:** e.g., `PERSON`, `GPE`, `ORG`.
    * **RGB:** `(0-1, 0-1, 0-1)`
    """)
    
    if 'rules' not in st.session_state:
        st.session_state.rules = [{"label": "GPE", "color": "(0, 1, 1)"}, {"label": "PERSON", "color": "(1, 0, 0)"}]

    updated_rules = []
    for i, rule in enumerate(st.session_state.rules):
        with st.expander(f"Rule {i+1}", expanded=True):
            col_l, col_c = st.columns([1.5, 1])
            new_l = col_l.text_input("Label", value=rule['label'], key=f"l_{i}")
            new_c = col_c.text_input("RGB", value=rule['color'], key=f"c_{i}")
            if st.button(f"🗑️ Remove", key=f"del_{i}"):
                st.session_state.rules.pop(i)
                st.rerun()
            updated_rules.append({"label": new_l, "color": new_c})
    st.session_state.rules = updated_rules

    if st.button("➕ Add New Rule"):
        st.session_state.rules.append({"label": "", "color": "(0, 0, 1)"})
        st.rerun()

# --- 5. 主处理表单 ---
# 使用 form 确保用户选好文件、设好规则后点击一次 Run 才开始计算
with st.form("processor_form"):
    uploaded_file = st.file_uploader("Upload your PDF", type=["pdf"])
    submitted = st.form_submit_button("🚀 Run Analysis")

if submitted and uploaded_file:
    # 只有点击 Run 且有文件时，才执行耗时操作
    timestamp = int(time.time())
    output_filename = f"processed_{timestamp}_{uploaded_file.name}"
    output_path = os.path.join(CACHE_DIR, output_filename)

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
        tmp_file.write(uploaded_file.getbuffer())
        tmp_path = tmp_file.name 

    try:
        doc = fitz.open(tmp_path)
        metadata = extract_metadata(doc)
        
        progress_bar = st.progress(0)

        with st.spinner('Model Processing... This may take a while.'):
            highlight_pdf_entities(
                doc,
                nlp,
                st.session_state.rules,
                progress_callback=progress_bar.progress,
            )

            doc.save(output_path)
            doc.close()

        # 将结果存入 session_state
        st.session_state.processed_data = {
            "metadata": metadata,
            "output_path": output_path,
            "filename": output_filename
        }
    except Exception as e:
        st.error(f"Error: {e}")
    finally:
        if os.path.exists(tmp_path): os.remove(tmp_path)

# --- 6. 展示结果（独立于表单外） ---
if st.session_state.processed_data:
    res = st.session_state.processed_data
    
    st.divider()
    st.subheader("1. Extracted Metadata (Editable)")
    # 用户在这里编辑表格时，由于上面的处理逻辑在 if submitted 块内，不会重新触发 PDF 扫描
    df = pd.DataFrame([res["metadata"]])
    edited_df = st.data_editor(df, hide_index=True, use_container_width=True)

    st.subheader("2. Result & Preview")
    with open(res["output_path"], "rb") as pdf_file:
        st.download_button(
            label="Download Highlighted PDF",
            data=pdf_file,
            file_name=res["filename"], 
            mime="application/pdf"
        )
    
    display_pdf(res["output_path"])
