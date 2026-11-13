"""
Template: Yearly Archive PDF Scraper

Use this template when a target site organizes newsletter/archive PDFs on
dedicated per-year pages (e.g., https://example.org/newsletters/year-2024/).

Customize `DOMAIN_URL`, `BASE_URL_TEMPLATE`, `START_YEAR`, and `END_YEAR`
for your target archive.
"""

import os
import re
import time
from urllib.parse import urljoin
import requests

DOMAIN_URL = "https://example.org"
BASE_URL_TEMPLATE = "https://example.org/newsletters/year-{}/"
START_YEAR = 2008
END_YEAR = 2026

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}


def scrape_yearly_archives():
    all_pdf_links = set()
    save_dir = "original"
    os.makedirs(save_dir, exist_ok=True)

    for year in range(START_YEAR, END_YEAR + 1):
        target_url = BASE_URL_TEMPLATE.format(year)
        print(f"Scanning year {year}: {target_url} ...")

        try:
            response = requests.get(target_url, headers=HEADERS, timeout=15)
            response.raise_for_status()

            links = re.findall(r'href=["\']([^"\']+\.pdf[^"\']*)["\']', response.text, re.IGNORECASE)
            for link in links:
                full_url = urljoin(DOMAIN_URL, link).split("#")[0]
                all_pdf_links.add(full_url)

        except Exception as e:
            print(f"Failed to load {target_url}: {e}")

        time.sleep(0.2)

    file_path = os.path.join(save_dir, "pdf_links.txt")
    with open(file_path, "w", encoding="utf-8") as f:
        for link in sorted(all_pdf_links):
            f.write(link + "\n")

    print(f"\nFinished! Total unique PDFs found: {len(all_pdf_links)}")
    print(f"Links saved to: {file_path}")


if __name__ == "__main__":
    scrape_yearly_archives()
