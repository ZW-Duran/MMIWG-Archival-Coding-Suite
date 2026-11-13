import sys
from pathlib import Path
_REPO_ROOT = str(Path(__file__).resolve().parents[2])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import google.generativeai as genai
import streamlit as st

# --- 1. Page Configuration ---
st.set_page_config(
    page_title="One-Touch News Text Quantitative Coding Tool", page_icon="📝", layout="wide"
)

# --- 2. Define Prompts for Each Part ---
from core.prompts import WEB_PROMPTS as PROMPTS


# --- 3. Output Sanitizer (Strips Thinking/Thoughts text) ---
def clean_and_parse_output(raw_text):
  if not raw_text:
    return ""
  try:
    start_idx = raw_text.find("{")
    if start_idx == -1:
      return raw_text

    end_idx = raw_text.rfind("}")
    if end_idx == -1 or end_idx < start_idx:
      return raw_text[start_idx:]

    return raw_text[start_idx : end_idx + 1]
  except Exception:
    return raw_text


# --- 4. Core API Execution Function (Dual-Key Round-Robin) ---
def run_model_analysis(text, selected_prompt, api_key_1, api_key_2):
  prompt = f"{selected_prompt}\n\nArticle Text:\n{text}"

  # Dual-key load balancing / fallback logic
  if not api_key_2 or not api_key_2.strip():
    current_api_key = api_key_1
    key_label = "Key 1 (Single Channel)"
  else:
    if "key_toggle" not in st.session_state:
      st.session_state.key_toggle = 0

    if st.session_state.key_toggle % 2 == 0:
      current_api_key = api_key_1
      key_label = "Key 1 (Dual Channel Alternate)"
    else:
      current_api_key = api_key_2
      key_label = "Key 2 (Dual Channel Alternate)"

    st.session_state.key_toggle += 1

  try:
    genai.configure(api_key=current_api_key)
    model = genai.GenerativeModel("gemma-4-31b-it")

    with st.spinner(f"Analyzing via [{key_label}]..."):
      response = model.generate_content(
          prompt,
          generation_config=genai.types.GenerationConfig(
              temperature=0.0,  # Zero temperature for maximum stability
          ),
      )

    return response.text, key_label

  except Exception as e:
    st.error(f"API Error: {e}")
    return None, key_label


# --- 5. Streamlit Frontend Layout ---
def main():
  st.title("📰 One-Touch News Text Quantitative Coding Tool")
  st.markdown(
      "Select your coding part in the sidebar, input your API keys, and paste"
      " the article text below."
  )

  # Sidebar Configuration
  st.sidebar.header("⚙️ Configuration")

  # Task Part Selector
  selected_task = st.sidebar.selectbox(
      "Select Coding Part:",
      options=list(PROMPTS.keys()),
      help="Choose which part of the coding task to execute.",
  )

  st.sidebar.markdown("---")
  st.sidebar.header("🔑 API Key Setup")
  api_key_1 = st.sidebar.text_input(
      "API Key 1 (Primary)", type="password", placeholder="Required: Google AI Studio Key"
  )
  api_key_2 = st.sidebar.text_input(
      "API Key 2 (Backup / Optional)",
      type="password",
      placeholder="Optional: Enables load-balancing",
  )

  st.sidebar.markdown("---")
  st.sidebar.info(
      "Tip: Entering two keys automatically alternates requests to distribute"
      " rate limits safely."
  )

  # Main Interface: Display current task info
  st.info(f"📍 Current Active Task: **{selected_task}**")

  article_text = st.text_area(
      "Paste Article Text Here:", height=300, placeholder="Enter article content..."
  )

  if st.button("🚀 Start Analysis", type="primary"):
    if not api_key_1:
      st.warning("⚠️ Please provide **API Key 1** in the sidebar to proceed.")
      return

    if not article_text.strip():
      st.warning("⚠️ Please enter article text before running analysis.")
      return

    # Execute Model Analysis with the selected prompt
    active_prompt = PROMPTS[selected_task]
    raw_result_text, channel_used = run_model_analysis(
        article_text, active_prompt, api_key_1, api_key_2
    )

    if raw_result_text:
      st.success(f"🎉 Analysis Complete! (Channel: {channel_used})")

      # Sanitize and truncate raw output
      clean_json_output = clean_and_parse_output(raw_result_text)

      # Display clean JSON block
      st.markdown("### 📊 Structured Coding Output:")
      st.code(clean_json_output, language="json")

      # Expandable raw logs
      with st.expander("🔍 View Raw Model Output & Reasoning Log"):
        st.text(raw_result_text)

      # Download button
      st.download_button(
          label="📥 Download JSON Results",
          data=clean_json_output,
          file_name="coding_output.json",
          mime="application/json",
      )


if __name__ == "__main__":
  main()