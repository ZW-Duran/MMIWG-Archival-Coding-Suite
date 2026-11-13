"""
Template: WordPress Monthly Uploads Directory Prober

Use this template when a WordPress site stores monthly PDFs under
`/wp-content/uploads/YYYY/MM/` using predictable month/year filenames
(e.g., `April2025NewsletterWEB.pdf`).

Customize `BASE_URL`, `START_YEAR`, `END_YEAR`, and the filename `variants`
list for your target archive.
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
START_YEAR = 2020
END_YEAR = 2026

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
}


def ensure_file_exists():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    if not os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, "w", encoding="utf-8"):
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
        response = requests.head(
            url, headers=HEADERS, verify=False, timeout=15, allow_redirects=True
        )
        if response.status_code == 200:
            return True
        if response.status_code == 429:
            print("[WARNING] Rate limit triggered (429). Sleeping for 30 seconds...")
            time.sleep(30)
            return check_url(url)
        return False
    except Exception as e:
        print(f"[ERROR] Unable to connect: {url}. Reason: {e}")
        return False


def find_monthly_newsletters():
    ensure_file_exists()
    print(f"--- Start, will store files in: {OUTPUT_FILE} ---")

    current_date = datetime.now()

    for year in range(START_YEAR, END_YEAR + 1):
        for month_idx in range(1, 13):
            if year == current_date.year and month_idx > current_date.month:
                break

            d = datetime(year, month_idx, 1)
            path_year = d.strftime("%Y")
            path_month = d.strftime("%m")
            file_month = d.strftime("%B")

            variants = [
                f"{path_year}/{path_month}/{file_month}{path_year}NewsletterWEB.pdf",
                f"{path_year}/{path_month}/{file_month}-{path_year}-NewsletterWEB.pdf",
                f"{path_year}/{path_month}/{file_month}{path_year}Newsletter.pdf",
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
    find_monthly_newsletters()
