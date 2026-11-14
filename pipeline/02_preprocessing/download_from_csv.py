import os
import re
import csv
import requests

# --- 1. Path and Configuration Initialization ---
CSV_PATH = "./list.csv"
OUTPUT_DIR = "./original"

if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR)

# Simulated browser User-Agent to avoid Google Drive blocking automated requests
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def col_to_index(col_str: str) -> int:
    """Converts Excel-style column letters (e.g., A, E, M, AA) into 0-based Python indices."""
    col_str = col_str.strip().upper()
    idx = 0
    for char in col_str:
        if not ('A' <= char <= 'Z'):
            raise ValueError(f"Invalid column letter: {col_str}")
        idx = idx * 26 + (ord(char) - ord('A') + 1)
    return idx - 1

def prompt_input(prompt_text: str, default_val: str, validator=None):
    """Interactive command-line prompt supporting default values (via Enter) and input validation."""
    while True:
        user_val = input(f"{prompt_text} [Default: {default_val}]: ").strip()
        if not user_val:
            user_val = default_val
        
        if validator:
            try:
                return validator(user_val)
            except Exception as e:
                print(f"⚠️ Invalid input: {e}. Please try again.")
        else:
            return user_val

def download_file_from_google_drive(drive_url: str, save_path: str):
    """Streams and downloads a file via the Google Drive open export endpoint."""
    # Extract the File ID from the Drive link
    match = re.search(r'/d/([^/]+)', drive_url)
    if not match:
        return False, "Unsupported Google Drive URL format"
    
    file_id = match.group(1)
    download_url = f"https://docs.google.com/uc?export=download&id={file_id}"
    
    try:
        # Use stream=True to avoid filling memory when downloading large files
        with requests.get(download_url, headers=HEADERS, stream=True, timeout=30) as r:
            if r.status_code == 200:
                with open(save_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                return True, "Success"
            elif r.status_code == 403:
                return False, "403 Forbidden (Google Drive rate limit reached; please retry later)"
            else:
                return False, f"HTTP status code: {r.status_code}"
    except Exception as e:
        return False, str(e)

# --- 2. Main Batch Processing Pipeline ---
def main():
    print("=" * 50)
    print("📥 Google Drive Batch Streaming Downloader")
    print("=" * 50)

    # 1. Interactive parameter setup
    check_col_name = prompt_input(
        "Enter column letter to check for non-empty status (e.g., E)",
        default_val="E",
        validator=lambda x: x.strip().upper() if x.strip().isalpha() else (_ for _ in ()).throw(ValueError("Must be alphabetic letters only"))
    )
    check_col_idx = col_to_index(check_col_name)

    link_col_name = prompt_input(
        "Enter column letter containing Google Drive links (e.g., M)",
        default_val="M",
        validator=lambda x: x.strip().upper() if x.strip().isalpha() else (_ for _ in ()).throw(ValueError("Must be alphabetic letters only"))
    )
    link_col_idx = col_to_index(link_col_name)

    def validate_start_row(val: str) -> int:
        n = int(val)
        if n < 0:
            raise ValueError("Starting row index cannot be negative")
        return n

    # Row indices follow standard Excel 1-based numbering; entering 0 or 1 starts from the beginning
    start_row = prompt_input(
        "Enter starting row number (0 or 1 starts from row 1)",
        default_val="1",
        validator=validate_start_row
    )
    effective_start_row = 1 if start_row <= 0 else start_row

    print("\n⚙️ Execution Configuration:")
    print(f"  - Validation column: {check_col_name} (index {check_col_idx})")
    print(f"  - Link column:       {link_col_name} (index {link_col_idx})")
    print(f"  - Starting from row: {effective_start_row}\n")

    # 2. Read and parse local CSV
    print(f"📖 Reading CSV file: {CSV_PATH}")
    if not os.path.exists(CSV_PATH):
        print(f"❌ Error: {CSV_PATH} not found in the current directory.")
        return

    download_count = 0
    skip_count = 0
    fail_count = 0

    with open(CSV_PATH, mode='r', encoding='utf-8') as f:
        rows = list(csv.reader(f))

    required_min_cols = max(check_col_idx, link_col_idx) + 1

    for idx, row in enumerate(rows, start=1):
        # Skip rows before the specified starting row
        if idx < effective_start_row:
            continue

        # Filter out empty rows
        if not row or "".join(row).strip() == "":
            print(f"👻 Row [{idx}]: Empty row detected, skipped.")
            continue

        # Identify and skip header rows
        if "Author Last Name" in row or "Newspaper/Publisher" in row:
            print(f"📋 Row [{idx}]: Header row detected, skipped.")
            continue

        # Boundary check: ensure the row has enough columns
        if len(row) < required_min_cols:
            print(f"⚠️ Row [{idx}]: Insufficient columns ({len(row)} < {required_min_cols}), skipped.")
            continue

        check_val = row[check_col_idx].strip()
        drive_link = row[link_col_idx].strip()

        # Core download condition: check column is non-empty
        if check_val:
            if not drive_link:
                print(f"⚠️ Row [{idx}]: Column {check_col_name} is valid, but Column {link_col_name} link is empty. Skipped.")
                continue

            # Naming format: 001.pdf, 002.pdf, etc. (:03d format preserved)
            new_filename = f"{idx:03d}.pdf"
            file_save_path = os.path.join(OUTPUT_DIR, new_filename)

            # Check if file already exists locally (resume capability)
            if os.path.exists(file_save_path):
                print(f"⏭️ Row [{idx}]: {new_filename} already exists locally. Skipped.")
                skip_count += 1
                continue

            # Execute streaming download
            print(f"🚀 Downloading Row [{idx}] ──> Saving as: {new_filename}...")
            success, message = download_file_from_google_drive(drive_link, file_save_path)
            
            if success:
                download_count += 1
                print(f"   └─ ✅ Download completed.")
            else:
                fail_count += 1
                print(f"   └─ ❌ Download failed: {message}")

    print("\n" + "=" * 40)
    print("🎉 Batch download task completed!")
    print(f"   - Successfully downloaded: {download_count} file(s)")
    print(f"   - Skipped (already exist): {skip_count} file(s)")
    print(f"   - Failed downloads:         {fail_count} file(s)")
    print(f"📂 Output directory: {OUTPUT_DIR}")
    print("=" * 40)

if __name__ == "__main__":
    main()