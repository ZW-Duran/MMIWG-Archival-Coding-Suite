"""
Template: Seasonal Archive PDF Scraper

Use this template when a target site organizes issues by year and season
slugs (e.g., https://example.org/2024-spring-newsletter).

Customize `BASE_DOMAIN`, `BASE_URL_TEMPLATE`, `YEARS`, and `SEASONS`
for your target archive.
"""

import os
import re
import time
from urllib.parse import urljoin
import requests

BASE_DOMAIN = "https://example.org"
BASE_URL_TEMPLATE = "https://example.org/{year}-{season}-newsletter"
YEARS = range(2021, 2026)
SEASONS = ["winter", "spring", "summer", "fall"]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}


def scrape_seasonal_archives():
    all_pdf_links = set()
    save_dir = "original"
    os.makedirs(save_dir, exist_ok=True)

    pdf_pattern = re.compile(r'(?:href|src)=["\']([^"\']+\.pdf[^"\']*)["\']', re.IGNORECASE)

    for year in YEARS:
        for season in SEASONS:
            target_url = BASE_URL_TEMPLATE.format(year=year, season=season)
            print(f"Scanning: {target_url} ...")

            try:
                response = requests.get(target_url, headers=HEADERS, timeout=15)
                response.raise_for_status()

                links = pdf_pattern.findall(response.text)
                for link in links:
                    full_url = urljoin(BASE_DOMAIN, link)
                    clean_url = full_url.split("#")[0].split("?")[0]
                    all_pdf_links.add(clean_url)

            except Exception:
                print(f"Skip or fail to load {target_url}")

            time.sleep(0.5)

    file_path = os.path.join(save_dir, "pdf_links.txt")
    with open(file_path, "w", encoding="utf-8") as f:
        for link in sorted(all_pdf_links):
            f.write(link + "\n")

    print(f"\nFinished! Total unique PDFs: {len(all_pdf_links)}")
    print(f"Links saved to: {file_path}")


if __name__ == "__main__":
    scrape_seasonal_archives()
