import google.generativeai as genai
import streamlit as st

# --- 1. Page Configuration ---
st.set_page_config(
    page_title="One-Touch News Text Quantitative Coding Tool", page_icon="📝", layout="wide"
)

# --- 2. Define Prompts for Each Part ---
PROMPTS = {
    "Part 1:": """
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
    """,
    "Part 2:": """
    You are an expert sociological research assistant reading US newspaper archives. Your task is to perform quantitative coding by COUNTING the number of distinct government officials, law enforcement personnel, and legal professionals referenced in the text.

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
  "tribe_gov_officials": {
    "count": 0,
    "evidence": ""
  },
  "state_local_gov_officials": {
    "count": 0,
    "evidence": ""
  },
  "federal_gov_officials": {
    "count": 0,
    "evidence": ""
  },
  "law_enforcement": {
    "count": 0,
    "evidence": ""
  },
  "legal_professionals": {
    "count": 0,
    "evidence": ""
  }
}
    """,
    "Part 3:": """
    You are an expert sociological research assistant reading US newspaper archives. Your task is to perform quantitative coding by COUNTING the number of distinct academics, subject matter experts, victim relatives/friends, and other ordinary people referenced or quoted in the text.

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
  "academics": {"value": 0, "evidence": ""},
  "other_experts": {"value": 0, "evidence": ""},
  "family_friends_referenced": {"value": 0, "evidence": ""},
  "other_ordinary_people": {"value": 0, "evidence": ""}
}
    """,
    "Part 4:": """
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
}
    """,
}


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