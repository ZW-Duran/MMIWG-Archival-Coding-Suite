import requests
import time
import random
import os
from datetime import datetime
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE_URL = "https://www.puyalluptribe-nsn.gov/wp-content/uploads/"
OUTPUT_DIR = "./original"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "pdf_links.txt")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}

def ensure_file_exists():
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
        print(f"[INFO] Created directory: {OUTPUT_DIR}")
    
    if not os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            pass
        print(f"[INFO] Created file: {OUTPUT_FILE}")

def save_link(url):
    existing_links = set()
    if os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
            existing_links = {line.strip() for line in f}

    if url not in existing_links:
        with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
            f.write(url + "\n")
        return True
    return False

def check_url(url):
    time.sleep(random.uniform(1.0, 3.0))
    
    try:
        response = requests.get(url, headers=HEADERS, stream=True, verify=False, timeout=20)
        
        if response.status_code == 200:
            return True
        elif response.status_code == 429:
            print(f"[WARNING] Rate limited (429). Sleeping for 30s...")
            time.sleep(30)
            return check_url(url)
        return False
    except Exception as e:
        print(f"[ERROR] Connection failed: {url}. Reason: {e}")
        return False

def find_newsletters():
    ensure_file_exists()
    
    print(f"--- Task started, writing to: {OUTPUT_FILE} ---")

    # 1. Old Format (IssueXXX.pdf)
    print("--- Searching: Old Format ---")
    current_issue = 364
    fail_count = 0
    
    while fail_count < 2: 
        url = f"{BASE_URL}Issue{current_issue}.pdf"
        if check_url(url):
            print(f"[FOUND] {url}")
            save_link(url)
            current_issue += 1
            fail_count = 0 
        else:
            print(f"[NOT FOUND/TIMEOUT] Issue{current_issue}")
            fail_count += 1
            current_issue += 1

    # 2. New Format (PTN_Mon_Year_online.pdf)
    print("\n--- Searching: New Format ---")
    for year in range(2021, 2027):
        for month_idx in range(1, 13):
            d = datetime(year, month_idx, 1)
            variants = [
                f"PTN_{d.strftime('%b')}_{year}_online.pdf",     # e.g. Oct
                f"PTN_{d.strftime('%B')}_{year}_online.pdf"      # e.g. October
            ]
            
            for file_name in variants:
                url = f"{BASE_URL}{file_name}"
                if check_url(url):
                    if save_link(url):
                        print(f"[FOUND] {url}")

    print("\n--- Task completed ---")

if __name__ == "__main__":
    find_newsletters()