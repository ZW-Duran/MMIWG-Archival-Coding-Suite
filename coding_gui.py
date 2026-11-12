import os
import re
import json
import fitz  # PyMuPDF
import google.generativeai as genai
import flet as ft

PROMPTS = {
    "Part 1": """You are an expert sociological research assistant reading newspaper archives. Your task is to perform qualitative text coding to identify specific semantic themes within the provided article.

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
  "mmiwg_mentioned": 0,
  "mmiwg_movement": 0,
  "specific_case": 0,
  "multiple_cases": 0,
  "legal_protection": 0,
  "family_friends_referenced": 0,
  "details_victim_life": 0,
  "details_perpetrator": 0
}""",

    "Part 2": """You are an expert sociological research assistant reading US newspaper archives. Your task is to perform quantitative coding by COUNTING the number of distinct government officials, law enforcement personnel, and legal professionals referenced in the text.

CRITICAL INSTRUCTIONS:
1. GEOGRAPHIC BOUNDARY: Count ONLY individuals located within or representing official bodies within the USA. STRICTLY EXCLUDE any officials, law enforcement, or legal personnel outside of the USA.
2. COUNTING RULE: Return an integer count >= 0 for each category. Count individual persons referenced, NOT mentions/occurrences. If an official is mentioned multiple times, count them ONCE.
3. MUTUAL EXCLUSIVITY: Each referenced individual must be assigned to EXACTLY ONE best-fitting category. Do not double-count the same person in two categories.

--- CATEGORY DEFINITIONS ---

1. "tribe_gov_officials":
   - Count of official leaders, council members, or legislative directors of Native American/Tribal governments (e.g., tribal councilmember, tribal chairman/chairwoman, tribal legislative director).
   - EXCLUSION: Do NOT count tribal police (put in law enforcement) or tribal judges/prosecutors (put in legal professionals).

2. "state_local_gov_officials":
   - Count of state, county, or municipal officials (e.g., state representative, governor, mayor, city councilor, state legislative director, county commissioner).

3. "federal_gov_officials":
   - Count of US Federal Government officials (e.g., Secretary of the Interior, US President, Congressional Representative, US Senator, federal agency heads).

4. "law_enforcement":
   - Count of police officers, sheriffs, deputies, state troopers, federal agents (FBI/BIA law enforcement), including Tribal law enforcement officers/officials.

5. "legal_professionals":
   - Count of judges, magistrates, prosecutors, district attorneys, public defenders, and lawyers/attorneys, including Tribal legal professionals and judges.

--- OUTPUT FORMAT ---
You MUST return your response strictly as a JSON object formatted as follows:

{
  "tribe_gov_officials": 0,
  "state_local_gov_officials": 0,
  "federal_gov_officials": 0,
  "law_enforcement": 0,
  "legal_professionals": 0
}""",

    "Part 3": """You are an expert sociological research assistant reading US newspaper archives. Your task is to perform quantitative coding by COUNTING the number of distinct academics, subject matter experts, victim relatives/friends, and other ordinary people referenced or quoted in the text.

CRITICAL INSTRUCTIONS:
1. GEOGRAPHIC BOUNDARY: Count ONLY individuals located within or representing organizations within the USA. STRICTLY EXCLUDE any individuals outside of the USA.
2. COUNTING RULE: Return an integer count >= 0 for each category. Count distinct individual persons, NOT mentions/occurrences. If an individual is mentioned multiple times, count them ONCE.
3. MUTUAL EXCLUSIVITY: Each referenced individual must be assigned to EXACTLY ONE best-fitting category based on the priority rules below.

--- CATEGORY DEFINITIONS & HIERARCHY ---

1. "family_friends_referenced":
   - Definition: Count of surviving third-party individuals who are EXPLICITLY NAMED and identified as a direct family member, relative, partner, or close personal friend OF A SPECIFIC NAMED VICTIM/MISSING PERSON in the article.
   - MANDATORY ANCHOR: There MUST be a clear, named link connecting this person to a SPECIFIC named victim (e.g., "Jane Doe, mother of missing victim John Doe").
   - STRICT EXCLUSION 1 (THE VICTIM THEMSELVES):
     * DO NOT count the victim or missing/murdered person themselves (e.g., Webster George is a missing VICTIM, NOT a family/friend).
   - STRICT EXCLUSION 2 (GENERAL/RHOETORICAL STATEMENTS):
     * DO NOT count general speakers, activists, or event organizers who merely mention having "family losses" or "personal grief" in a vague or collective sense WITHOUT naming the specific victim they are related to (e.g., Paul Frank speaking generally about family losses belongs in "other_ordinary_people" or "other_experts", NOT here).

2. "academics":
   - Count of academic professionals affiliated with universities, colleges, or research institutions (e.g., professors, university scholars, researchers, deans, academic experts).

3. "other_experts":
   - Count of non-academic, professional subject-matter experts or service providers (e.g., MMIP task force members, victim services directors, social workers, professional advocates, policy analysts, independent researchers).
   - EXCLUSION: Do NOT count government officials, law enforcement officers, or legal professionals/attorneys here.

4. "other_ordinary_people":
   - Definition: Count of named or quoted everyday individuals who DO NOT fit into government, law enforcement, legal, academic, expert, or family/friend categories (e.g., eye-witnesses, rally attendees, local residents, community members expressing personal views).
   - STRICT EXCLUSION (PERPETRATORS / SUSPECTS):
     * DO NOT count perpetrators, suspects, persons of interest, or individuals who are arrested, charged, indicted, or convicted of crimes (e.g., individuals indicted for murder, accomplices, accessories). These belong to the perpetrator/suspect category in Step 3.
   - STRICT EXCLUSION (METADATA & BYLINES):
     * DO NOT count the author, writer, or reporter who WROTE THIS NEWSPAPER ARTICLE (e.g., "By John Smith", "Staff Writer John Smith").
     * DO NOT count newspaper editors, publishers, or staff listed in newspaper headers, mastheads, or footers.
     * DO NOT count generic unnamed crowds (e.g., "the crowd cheered").
   - INCLUSION (CONTEXTUAL SUBJECTS):
     * DO include authors, writers, or editors who are explicitly MENTIONED IN THE TEXT AS SUBJECTS of the article (e.g., a book author being interviewed or quoted about an event).

--- OUTPUT FORMAT ---
1. First, step-by-step list the named people/titles identified for each category and verify their eligibility and priority.
2. At the VERY END of your response, output EXACTLY ONE final JSON object containing the definitive counts. Do not output multiple JSON blocks.

Final JSON format:
{
  "academics": 0,
  "other_experts": 0,
  "family_friends_referenced": 0,
  "other_ordinary_people": 0
}""",

    "Part 4": """Victim Status (Missing, Murdered, General Victim)
You are an expert sociological research assistant reading US newspaper archives. Your task is to perform qualitative and quantitative coding for ALL VICTIMS and SUSPECTS/PERPETRATORS referenced in the text.

CRITICAL INSTRUCTIONS:
1. GEOGRAPHIC BOUNDARY: Process ONLY victims and suspects within the USA. EXCLUDE any outside of the USA.
2. INDIVIDUALIZATION: Extract every distinct victim mentioned.
3. STATUS CATEGORIES (Strictly Choose One of Three):
- "murdered": Victim was killed, found deceased as a result of homicide, or confirmed murdered.
- "missing": Victim disappeared, is unaccounted for, or is currently missing (fate/death unconfirmed).
- "general_victim": Victim suffered non-fatal violence (e.g., physical assault, domestic violence, sexual assault, survived abduction, abuse) and is neither murdered nor missing.
4. GENDER CATEGORIES: "male", "female", "nonbinary", "unknown".
5. RACE / TRIBAL AFFILIATION: Extract exact race/ethnicity and tribal affiliation if mentioned (e.g., "Navajo Nation", "Cherokee"). Use "Unknown" if not mentioned.
6. SUSPECTS / PERPETRATORS: 
- Count the total number of distinct suspects, persons of interest, or perpetrators referenced in the text (e.g., 0, 1, 2...).
- Extract the race/ethnicity of the suspect(s). If count is 0, leave race completely empty (""). If there are multiple suspects with different races, list all of them clearly separated by commas within the same string (e.g., "White, Native American").

--- OUTPUT FORMAT ---
1. Step-by-step list each victim identified, verifying their status ("murdered", "missing", or "general_victim"), gender, race, tribal affiliation, and age.
2. At the VERY END, output EXACTLY ONE final JSON object containing the list of victims, the summary count matrix, and the suspect information.

Final JSON format:
{
  "victims": [
    {
      "name": "Victim Name or 'Unknown'",
      "race": "Victim Race or 'Unknown'",
      "tribal_affiliation": "Tribal Affiliation or 'Unknown'",
      "age": "Age or 'Unknown'",
      "gender": "female", 
      "status": "murdered" 
    }
  ],
  "suspect_info": {
    "perpetrators_count": 0,
    "perpetrators_race": ""
  },
  "counts": {
    "murdered_id_male": 0,
    "murdered_id_female": 0,
    "murdered_id_nonbinary": 0,
    "murdered_gender_unknown": 0,
    "missing_id_male": 0,
    "missing_id_female": 0,
    "missing_id_nonbinary": 0,
    "missing_gender_unknown": 0,
    "gv_id_male": 0,
    "gv_id_female": 0,
    "gv_id_nonbinary": 0,
    "gv_gender_unknown": 0
  }
}"""
}

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