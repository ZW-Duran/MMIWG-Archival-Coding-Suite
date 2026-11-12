import requests
import time
import random
import os
from datetime import datetime
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE_URL = "https://skokomish.org/wp-content/uploads/"
OUTPUT_DIR = "./skokomish_data"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "sounder_links.txt")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}

def ensure_file_exists():
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
        print(f"[INFO] Create: {OUTPUT_DIR}")
    
    if not os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            pass
        print(f"[INFO] File Created: {OUTPUT_FILE}")

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
    time.sleep(random.uniform(0.5, 1.5))
    
    try:
        response = requests.head(url, headers=HEADERS, verify=False, timeout=15, allow_redirects=True)
        
        if response.status_code == 200:
            return True
        elif response.status_code == 429:
            print(f"[WARNING] Frequency limit triggered (429). Sleeping for 30 seconds...")
            time.sleep(30)
            return check_url(url)
        return False
    except Exception as e:
        print(f"[ERROR] Unable to connect: {url}. Reason: {e}")
        return False

def find_sounder_newsletters():
    ensure_file_exists()
    
    print(f"--- Start, will store files in: {OUTPUT_FILE} ---")

    start_year = 2020
    end_year = 2026
    current_date = datetime.now()

    for year in range(start_year, end_year + 1):
        for month_idx in range(1, 13):
            if year == current_date.year and month_idx > current_date.month:
                break
                
            d = datetime(year, month_idx, 1)
            
            path_year = d.strftime('%Y')       # 2026
            path_month = d.strftime('%m')      # 04
            file_month = d.strftime('%B')      # April
      
            variants = [
                f"{path_year}/{path_month}/{file_month}{path_year}SounderWEB.pdf",
                f"{path_year}/{path_month}/{file_month}-{path_year}-SounderWEB.pdf", #backup format
                f"{path_year}/{path_month}/{file_month}{path_year}Sounder.pdf"      #backup format
            ]
            
            for suffix in variants:
                url = f"{BASE_URL}{suffix}"
                print(f"[CHECKING] {path_year}-{path_month}...", end="\r")
                
                if check_url(url):
                    if save_link(url):
                        print(f"[FOUND] Found new link: {url}")
                    else:
                        print(f"[EXISTS] Already exists: {url}")

    print("\n--- Task complete ---")

if __name__ == "__main__":
    find_sounder_newsletters()