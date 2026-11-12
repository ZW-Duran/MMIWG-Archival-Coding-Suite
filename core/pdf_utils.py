"""Shared PDF reading, path sanitization, and NewsBank metadata extraction utilities."""

import os
import re
import fitz  # PyMuPDF


def clean_path(raw_path: str) -> str:
    """Clean quotes, whitespace, and PowerShell `&` prefixes from pasted file paths."""
    if not raw_path:
        return ""
    p = raw_path.strip()
    if p.startswith("&"):
        p = p[1:].strip()
    while len(p) >= 2 and ((p[0] == '"' and p[-1] == '"') or (p[0] == "'" and p[-1] == "'")):
        p = p[1:-1].strip()
    return os.path.normpath(p)


def read_source_file_content(file_path: str) -> str:
    """Read text content from a .txt or .pdf file."""
    if not file_path or not os.path.exists(file_path):
        return ""

    ext = os.path.splitext(file_path)[1].lower()

    if ext == ".txt":
        for enc in ("utf-8", "gbk", "gb2312", "latin-1"):
            try:
                with open(file_path, "r", encoding=enc) as f:
                    return f.read()
            except UnicodeDecodeError:
                continue
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()

    if ext == ".pdf":
        doc = fitz.open(file_path)
        text_blocks = []
        for page in doc:
            for b in page.get_text("blocks"):
                if b[4].strip():
                    text_blocks.append(b[4].strip())
        doc.close()
        return "\n\n".join(text_blocks)

    return ""


def extract_newsbank_metadata(doc) -> dict:
    """Extract first-line NewsBank article metadata from page 0 using month-anchor regex."""
    page = doc[0]
    rect = fitz.Rect(0, 0, page.rect.width, 100)
    lines = page.get_textbox(rect).strip().split("\n")

    first_line = ""
    for line in lines:
        if line.strip():
            first_line = line.strip()
            break

    data = {
        "Author last": "N/A",
        "Author First": "N/A",
        "Other Authors (if any)": "",
        "Newspaper/Publisher": "",
        "Publication Year": "",
        "Article Title": "",
        "Publication Location": "",
        "Contextual Location": "",
        "News Source": "NewsBank",
        "Date of publication": "",
        "page (if any)": "",
    }

    months = (
        r"(?:Jan(?:uary|\.)?|Feb(?:ruary|\.)?|Mar(?:ch|\.)?|Apr(?:il|\.)?|May|"
        r"Jun(?:e|\.)?|Jul(?:y|\.)?|Aug(?:ust|\.)?|Sep(?:tember|t|\.)?|"
        r"Oct(?:ober|\.)?|Nov(?:ember|\.)?|Dec(?:ember|\.)?)"
    )
    pattern = re.compile(
        rf"^(?:(?P<last>[^,]+?),\s*(?P<first>[^:]+?)\s*:\s*)?(?P<title>.+?)\s*-\s*(?P<publisher>.+?)\s*-\s*(?P<date>{months}\b.*?)\s*-\s*(?P<page>.*)$",
        re.IGNORECASE,
    )

    match = pattern.match(first_line)
    if match:
        gd = match.groupdict()
        data["Author last"] = gd.get("last", "N/A").strip() if gd.get("last") else "N/A"
        data["Author First"] = gd.get("first", "N/A").strip() if gd.get("first") else "N/A"
        data["Article Title"] = gd.get("title", "").strip()
        data["Newspaper/Publisher"] = gd.get("publisher", "").strip()
        data["Date of publication"] = gd.get("date", "").strip()
        data["page (if any)"] = gd.get("page", "").strip()
        year_match = re.search(r"\d{4}", data["Date of publication"])
        if year_match:
            data["Publication Year"] = year_match.group(0)
    else:
        data["Article Title"] = first_line

    return data
