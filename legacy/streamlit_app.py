import streamlit as st
import spacy
import json
import re
import os
import subprocess
import tempfile
import fitz  # PyMuPDF
import pandas as pd
import google.generativeai as genai

# --- 1. 初始化配置与页面设置 ---
st.set_page_config(page_title="Text Semantic Coder & Highlighter", layout="wide")

# 优化为惰性加载：只有当用户开启高亮开关时，该函数才会被触发调用
@st.cache_resource
def load_spacy_model():
    with st.spinner("Initializing spaCy Transformer Model (First-time loading may take a while)..."):
        return spacy.load("en_core_web_trf")

CLOUD_MODEL_NAME = "gemma-4-31b-it"  

# --- 2. 强约束 Prompt ---
SYSTEM_INSTRUCTION = """
You are an expert sociological research assistant reading newspaper archives. Your task is to perform qualitative text coding to identify specific semantic themes within the provided article.

CRITICAL INSTRUCTIONS:
1. For every variable you code as 1, you MUST provide the exact, verbatim sentence (evidence) from the text that justifies your choice.
2. If the text does not implicitly or explicitly discuss the theme based on the strict definitions below, set the value to 0 and leave the evidence string completely empty ("").
3. Keep the "evidence" string as short as possible—a single, precise verbatim sentence is preferred.

--- CODEBOOK & BOUNDARY DEFINITIONS ---
1. "mmiwg_mentioned": 1 if the text addresses the topic of Missing and Murdered Indigenous Women and Girls. This does NOT require a literal acronym match; if the article is clearly validating or discussing the crisis/phenomenon of missing/murdered Native individuals, it counts as 1.

2. "mmiwg_movement": 1 if the text references activism, community awareness, protests, marches, healing circles, policy advocacy, task forces, or red dress campaigns dedicated to addressing this crisis.

3. "specific_case": 1 if the text discusses a particular individual's disappearance or murder case. This includes anytime a specific victim is named, or specific incident details (like search efforts, police reporting, or crime scenes) are described.

4. "multiple_cases": 1 if the text acts as an empirical aggregator of the crisis—meaning it provides specific aggregated numbers/statistics, references database counts, or transitions into detailing/contrasting distinct, separate case histories.
   - Core Intent: This captures factual density about more than one case. Do NOT code as 1 for purely rhetorical, commemorative, or emotional expressions of collective grief (e.g., "so many loved ones who have been victims"). It must contain empirical or informational grouping, not just poetic or general acknowledgment of a widespread issue.
5. "legal_protection": 1 if the text references specific, concrete institutional mechanisms—such as passed or proposed statutes (e.g., "Senate Resolution 60", "Savanna's Act"), tribal sovereignty protocols, specific budgetary allocations for policing, jurisdictional rules, or active policy reform measures.
   - STRUCTURAL REQUIREMENT: The evidence must point to a tangible legal instrument, legislative bill, or a specific regulatory action taken/proposed by a government or tribal body.
   - CRITICAL EXCLUSION (HOPE VS. FACT): Do NOT code as 1 for statements expressing how the system *should* behave, personal hopes, future expectations, or moral calls to action (e.g., "I hope it will inform the criminal justice system's response..."). General quotes about the failure, needed awareness, or desired attitude of the justice system do NOT constitute concrete legal protection.
6. "family_friends_referenced": 1 if the text quotes, mentions, or references the victim's family members, relatives, loved ones, or close friends speaking out or being affected.
   - CRITICAL EXCLUSION: Do NOT code as 1 if an individual is described ONLY by their professional, political, or activist title (e.g., "event organizer", "advocate", "chief", "police spokesperson") without the text explicitly stating they have a personal, familial, or friendship bond with a victim. Do not infer personal relationships from social or activist roles.

7. "details_victim_life": 1 if the text provides a humanizing look into who the victim was as a living person *beyond* basic identification markers—such as their personal character, hobbies, career achievements, educational background, personal dreams, or roles within their family/community before the tragedy.
   - STRUCTURAL THRESHOLD: The text must detail their personality or life story. 
   - CRITICAL EXCLUSION: Do NOT code as 1 if the text only mentions basic demographic labels, standard identification markers, or chronological data necessary to describe the crime or a holiday (e.g., mentioning a victim's age, tribal affiliation, or their "birthday" to explain why a commemorative date was selected does NOT count as details of the victim's life).

8. "details_perpetrator": 1 if the text provides substantive information or updates about a specific suspect, person of interest, or perpetrator. This includes physical descriptions, concrete identities, arrest records, investigation progress targeting a specific suspect, trial updates, or court proceedings.
   - CRITICAL EXCLUSION: Do NOT code as 1 for generic, empty statements about the police simply looking for an unknown perpetrator (e.g., "police still finding perpetrator" or "no suspects have been named"). It must contain actual details or updates about a suspect/perpetrator's status or identity.

CONTEXTUAL ALIGNMENT TEST: When evaluating a sentence for a variable, you must ensure the *contextual meaning* of the sentence matches the variable's theme, not just the individual words. Ask yourself: "Is this sentence actually talking about the sociological theme defined, or is it just using a similar word in a completely different context (e.g., an election context vs. a criminal justice context)?" If it's a different context, you MUST code it as 0.

--- TWO-STEP VERIFICATION FILTER (COMPULSORY) ---
Before confirming any variable as 1, you must run this strict linguistic check:
- Step 1 (Noun/Verb Check): Does the sentence physically contain the mandatory nouns/actions required by the category (e.g., kinship nouns for variable 6, legal instruments for variable 5, empirical numbers for variable 4, human character traits for variable 7)?
- Step 2 (Context Check): Is the sentence free of the REJECTION CRITERIA listed under that category?
If the sentence fails either check, you MUST force the value to 0.

You must return your response PRECISELY in the following JSON format:
{
  "mmiwg_mentioned": {"value": 0, "evidence": ""},
  "mmiwg_movement": {"value": 0, "evidence": ""},
  "specific_case": {"value": 0, "evidence": ""},
  "multiple_cases": {"value": 0, "evidence": ""},
  "legal_protection": {"value": 0, "evidence": ""},
  "family_friends_referenced": {"value": 0, "evidence": ""},
  "details_victim_life": {"value": 0, "evidence": ""},
  "details_perpetrator": {"value": 0, "evidence": ""}
}
"""

# --- 3. 核心大模型分析与流修复函数 (用户输入 API Key 版) ---
def analyze_text_with_gemini(text, api_key):
    prompt = f"{SYSTEM_INSTRUCTION}\n\nArticle Text:\n{text}"
    try:
        # 动态配置用户输入的 API Key
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(CLOUD_MODEL_NAME)
        
        # ─── 🛠️ 核心机制：强制开启 API 的 JSON 响应模式 ───
        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.0,
                response_mime_type="application/json"  # 逼迫云端必须返回合法的 JSON 字典
            )
        )
        
        raw_response = response.text.strip()
        if not raw_response: return None
            
        try:
            # ─── 🛠️ 强力定位机制：直接斩断前置的 Thinking 文本 ───
            start_idx = min([raw_response.find(x) for x in ['[', '{'] if raw_response.find(x) != -1], default=0)
            clean_text = raw_response[start_idx:]
            
            # 反向切除尾部可能存在的垃圾字符
            end_idx = max([clean_text.rfind(x) for x in [']', '}'] if clean_text.rfind(x) != -1], default=len(clean_text))
            clean_text = clean_text[:end_idx + 1]
            
            parsed_json = json.loads(clean_text)
            if isinstance(parsed_json, list) and len(parsed_json) > 0:
                parsed_json = parsed_json[0]
            return parsed_json

        except json.JSONDecodeError:
            # 第二层级：尝试清洗 evidence 中未转义的破坏性引号
            try:
                def clean_evidence(match):
                    content = match.group(1).replace('"', "'").replace('\n', ' ')
                    return f'"evidence": "{content}"'
                repaired_response = re.sub(r'"evidence"\s*:\s*"(.*?)(?<!\\)"', clean_evidence, raw_response, flags=re.DOTALL)
                return json.loads(repaired_response)
            
            # 第三层级：模糊正则提取（全面放宽空格与括号限制，防止漏网）
            except:
                fallback_dict = {}
                keys = ["mmiwg_mentioned", "mmiwg_movement", "specific_case", "multiple_cases", 
                        "legal_protection", "family_friends_referenced", "details_victim_life", "details_perpetrator"]
                for k in keys:
                    val_pattern = rf'"{k}"\s*:\s*\{{[^}}]*?"value"\s*:\s*["\']?([01])["\']?'
                    val_match = re.search(val_pattern, raw_response, re.IGNORECASE | re.DOTALL)
                    val = int(val_match.group(1)) if val_match else 0
                    
                    ev_pattern = rf'"{k}"\s*:\s*\{{[^}}]*?"evidence"\s*:\s*"(.*?)"'
                    ev_match = re.search(ev_pattern, raw_response, re.IGNORECASE | re.DOTALL)
                    if ev_match:
                        ev = ev_match.group(1).replace('\\"', "'").replace('"', "'").replace('\n', ' ').strip()
                    else:
                        ev = ""
                    fallback_dict[k] = {"value": val, "evidence": ev}
                return fallback_dict
    except Exception as e:
        st.error(f"Gemini API Call Error: {e}")
        return None

# --- 4. 纯文本 HTML 高亮渲染核心引擎 ---
def generate_html_highlighter(text, rules):
    nlp = load_spacy_model()
    doc = nlp(text)
    
    active_rules = {}
    for r in rules:
        if r['label'].strip():
            active_rules[r['label'].strip().upper()] = r['color']

    spans_to_highlight = []
    for ent in doc.ents:
        if ent.label_ in active_rules:
            spans_to_highlight.append((ent.start_char, ent.end_char, ent.label_, ent.text))
            
    spans_to_highlight = sorted(spans_to_highlight, key=lambda x: x[0], reverse=True)
    
    html_text = text
    for start, end, label, ent_text in spans_to_highlight:
        color_rgb = active_rules[label]
        try:
            rgb_tuple = eval(color_rgb)
            css_color = f"rgba({int(rgb_tuple[0]*255)}, {int(rgb_tuple[1]*255)}, {int(rgb_tuple[2]*255)}, 0.3)"
            border_color = f"rgb({int(rgb_tuple[0]*255)}, {int(rgb_tuple[1]*255)}, {int(rgb_tuple[2]*255)})"
        except:
            css_color = "rgba(255, 255, 0, 0.3)" 
            border_color = "rgb(255, 255, 0)"

        highlighted_node = (
            f'<mark style="background-color: {css_color}; '
            f'border-bottom: 2px solid {border_color}; '
            f'padding: 2px 4px; margin: 0 2px; border-radius: 4px; cursor: help;" '
            f'title="{label}">'
            f'{html_text[start:end]}<span style="font-size: 0.7em; color: gray; margin-left: 4px;">[{label}]</span>'
            f'</mark>'
        )
        html_text = html_text[:start] + highlighted_node + html_text[end:]
        
    html_text = html_text.replace("\n", "<br>")
    return f'<div style="font-family: sans-serif; line-height: 1.6; padding: 15px; border: 1px solid #ddd; border-radius: 5px; background-color: #f0f0f0; color: #333;">{html_text}</div>'

# --- 5. PDF 提取核心逻辑 (含 PyMuPDF & ocrmypdf 兜底) ---
def extract_text_from_pdf(uploaded_file):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_in:
        temp_in.write(uploaded_file.read())
        temp_in_path = temp_in.name

    extracted_text = ""
    try:
        # 1. 尝试直接提取电子文本
        doc = fitz.open(temp_in_path)
        text_blocks = []
        for page in doc:
            blocks = page.get_text("blocks")
            for b in blocks:
                if b[4].strip():
                    text_blocks.append(b[4].strip())
        extracted_text = "\n\n".join(text_blocks).strip()
        doc.close()
    except Exception as e:
        st.warning(f"PyMuPDF native extraction failed: {e}. Retrying with OCR...")

    # 2. 若无文本，调用本地 ocrmypdf
    if not extracted_text:
        st.info("No selectable text detected. Launching 'ocrmypdf' for optical character recognition...")
        temp_out_path = temp_in_path.replace(".pdf", "_ocred.pdf")
        try:
            subprocess.run(
                ["ocrmypdf", "--skip-text", temp_in_path, temp_out_path],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            if os.path.exists(temp_out_path):
                doc_ocr = fitz.open(temp_out_path)
                ocr_blocks = []
                for page in doc_ocr:
                    blocks = page.get_text("blocks")
                    for b in blocks:
                        if b[4].strip():
                            ocr_blocks.append(b[4].strip())
                extracted_text = "\n\n".join(ocr_blocks).strip()
                doc_ocr.close()
                os.remove(temp_out_path)
        except FileNotFoundError:
            st.error("❌ 'ocrmypdf' is not installed on the server. Cannot perform OCR.")
        except subprocess.CalledProcessError as e:
            st.error(f"❌ OCR execution failed: {e.stderr.decode('utf-8', errors='ignore')}")
        except Exception as e:
            st.error(f"❌ OCR processing error: {e}")

    if os.path.exists(temp_in_path):
        os.remove(temp_in_path)

    return extracted_text

# --- 6. 侧边栏交互配置 ---
with st.sidebar:
    access_code = st.text_input("Access Code", type="password")
    if access_code != "":
        st.warning("Please Provide Correct Password")
        st.stop()

    # ─── 🔑 改回用户自主输入 API Key 模式 ───
    st.header("🔑 API Authentication")
    api_key = st.text_input("Gemini API Key", type="password", placeholder="AIzaSy...")

    st.header("⚡ Performance Settings")
    enable_highlighting = st.checkbox("Enable spaCy NLP Highlighting", value=False, 
                                      help="Turning this off bypasses the heavy Transformer model and processes text instantly.")

    if enable_highlighting:
        st.markdown("---")
        st.header("Custom Highlighting Rules")
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

# --- 7. 主控制流程区 ---
st.title("Semantic Text Coder & NLP Enhancer")

if 'session_analysis_data' not in st.session_state:
    st.session_state.session_analysis_data = None

tab_text, tab_file = st.tabs(["✍️ Paste Plain Text", "📁 Upload PDF Document"])
input_text = ""

with tab_text:
    pasted_text = st.text_area("Paste your article plain text here:", height=250, 
                               placeholder="Type or paste the news contents here for automatic qualitative coding...")

with tab_file:
    uploaded_pdf = st.file_uploader("Upload a PDF file (supports scanned PDF auto-OCR):", type=["pdf"])

with st.form("text_processor_form"):
    submitted = st.form_submit_button("🚀 Run Analysis & Coding")

if submitted:
    # ─── 🛡️ 安全防御：阻断未提供 Key 的请求 ───
    if not api_key:
        st.error("Please enter your Gemini API Key in the sidebar first!")
        st.stop()

    if uploaded_pdf is not None:
        with st.spinner("Extracting text from PDF (performing OCR if scanned)..."):
            input_text = extract_text_from_pdf(uploaded_pdf)
    else:
        input_text = pasted_text

    if not input_text.strip():
        st.warning("Please paste some text or upload a valid PDF document before processing.")
    else:
        spinner_msg = "Running Gemini Cloud Coding Analysis..." if not enable_highlighting else "Processing NLP Highlighting & Gemini Cloud Coding..."
        
        with st.spinner(spinner_msg):
            word_count = len(input_text.split())
            
            # 传入用户前端填入的 api_key
            analysis = analyze_text_with_gemini(input_text, api_key)
            
            highlighted_html = None
            if enable_highlighting:
                highlighted_html = generate_html_highlighter(input_text, st.session_state.rules)
            
            if analysis:
                analysis_lower = {k.lower(): v for k, v in analysis.items()}
                
                def parse_block(key):
                    block = analysis_lower.get(key.lower(), {})
                    val = block.get("value", 0) if isinstance(block, dict) else 0
                    evid = block.get("evidence", "") if isinstance(block, dict) else ""
                    return val, evid

                mmiwg_m, mmiwg_m_ev = parse_block("mmiwg_mentioned")
                mmiwg_mv, mmiwg_mv_ev = parse_block("mmiwg_movement")
                spec_c, spec_c_ev = parse_block("specific_case")
                mult_c, mult_c_ev = parse_block("multiple_cases")
                legal_p, legal_p_ev = parse_block("legal_protection")
                fam_r, fam_r_ev = parse_block("family_friends_referenced")
                vic_l, vic_l_ev = parse_block("details_victim_life")
                perp, perp_ev = parse_block("details_perpetrator")

                coding_row = {
                    "Word Count": word_count,
                    "mmiwg_mentioned": mmiwg_m, "mmiwg_mentioned_evidence": mmiwg_m_ev,
                    "mmiwg_movement": mmiwg_mv, "mmiwg_movement_evidence": mmiwg_mv_ev,
                    "specific_case": spec_c, "specific_case_evidence": spec_c_ev,
                    "multiple_cases": mult_c, "multiple_cases_evidence": mult_c_ev,
                    "legal_protection": legal_p, "legal_protection_evidence": legal_p_ev,
                    "family_friends_referenced": fam_r, "family_friends_referenced_evidence": fam_r_ev,
                    "details_victim_life": vic_l, "details_victim_life_evidence": vic_l_ev,
                    "details_perpetrator": perp, "details_perpetrator_evidence": perp_ev,
                }
                
                st.session_state.session_analysis_data = {
                    "dataframe": pd.DataFrame([coding_row]),
                    "html": highlighted_html
                }
            else:
                st.error("Failed to generate qualitative coding from Gemini Cloud API.")

# --- 8. 结果可视化与编辑/复制回填区 ---
if st.session_state.session_analysis_data:
    res = st.session_state.session_analysis_data
    
    st.divider()
    
    st.subheader("📊 Automated Qualitative Coding Results (Editable Table)")
    edited_df = st.data_editor(res["dataframe"], hide_index=True, use_container_width=True)
    
    
    col_dl, col_copy = st.columns([1, 4])
    with col_dl:
        csv_buffer = edited_df.to_csv(index=False, encoding="utf-8-sig")
        st.download_button(
            label="📥 Export to CSV File",
            data=csv_buffer,
            file_name="coded_text_output.csv",
            mime="text/csv"
        )
    
    if res["html"]:
        st.subheader("🔍 Entity Semantic Enhancement View")
        st.markdown(res["html"], unsafe_allow_html=True)