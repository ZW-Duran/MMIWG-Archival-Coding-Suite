"""
Template: WordPress Uploads Sequential/Pattern Prober

Use this template when a WordPress site hosts PDFs directly under
`/wp-content/uploads/` with predictable issue numbers (`Issue364.pdf`) or
month/year naming conventions (`NEWS_Oct_2024_online.pdf`), without a
public index page.

Customize `BASE_URL`, `START_ISSUE`, `START_YEAR`, `END_YEAR`, and the
filename `variants` list for your target archive.
"""

from datetime import datetime
import os
import random
import time
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE_URL = "https://example.org/wp-content/uploads/"
OUTPUT_DIR = "./original"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "pdf_links.txt")
START_ISSUE = 1
START_YEAR = 2021
END_YEAR = 2026

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
}


def ensure_file_exists():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    if not os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, "w", encoding="utf-8"):
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
        if response.status_code == 429:
            print("[WARNING] Rate limited (429). Sleeping for 30s...")
            time.sleep(30)
            return check_url(url)
        return False
    except Exception as e:
        print(f"[ERROR] Connection failed: {url}. Reason: {e}")
        return False


def find_newsletters():
    ensure_file_exists()
    print(f"--- Task started, writing to: {OUTPUT_FILE} ---")

    # 1. Sequential Issue Format (e.g., Issue001.pdf)
    print("--- Searching: Sequential Issue Format ---")
    current_issue = START_ISSUE
    fail_count = 0

    while fail_count < 2:
        url = f"{BASE_URL}Issue{current_issue}.pdf"
        if check_url(url):
            print(f"[FOUND] {url}")
            save_link(url)
            fail_count = 0
        else:
            print(f"[NOT FOUND/TIMEOUT] Issue{current_issue}")
            fail_count += 1
        current_issue += 1

    # 2. Month/Year Filename Format (e.g., NEWS_Oct_2024_online.pdf)
    print("\n--- Searching: Month/Year Format ---")
    for year in range(START_YEAR, END_YEAR + 1):
        for month_idx in range(1, 13):
            d = datetime(year, month_idx, 1)
            variants = [
                f"NEWS_{d.strftime('%b')}_{year}_online.pdf",
                f"NEWS_{d.strftime('%B')}_{year}_online.pdf",
            ]

            for file_name in variants:
                url = f"{BASE_URL}{file_name}"
                if check_url(url) and save_link(url):
                    print(f"[FOUND] {url}")

    print("\n--- Task completed ---")


if __name__ == "__main__":
    find_newsletters()
