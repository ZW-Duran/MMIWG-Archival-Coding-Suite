"""
Template: Paginated Category/Archive PDF Scraper

Use this template when a target site lists PDFs across numbered pagination
pages (e.g., https://example.org/category/newsletters/page/1/).

Customize `DOMAIN_URL`, `BASE_URL_TEMPLATE`, `START_PAGE`, and `END_PAGE`
for your target archive.
"""

import os
import re
import time
from urllib.parse import urljoin
import requests

DOMAIN_URL = "https://example.org"
BASE_URL_TEMPLATE = "https://example.org/category/newsletters/page/{}/"
START_PAGE = 1
END_PAGE = 60

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}


def scrape_paginated_archives():
    all_pdf_links = set()
    save_dir = "original"
    os.makedirs(save_dir, exist_ok=True)

    for page_num in range(START_PAGE, END_PAGE + 1):
        target_url = BASE_URL_TEMPLATE.format(page_num)
        print(f"Scanning Page {page_num}: {target_url} ...")

        try:
            response = requests.get(target_url, headers=HEADERS, timeout=20)
            response.raise_for_status()
            links = re.findall(r'href=["\']([^"\']+\.pdf)["\']', response.text, re.IGNORECASE)

            page_count = 0
            for link in links:
                full_url = urljoin(DOMAIN_URL, link)
                if full_url not in all_pdf_links:
                    all_pdf_links.add(full_url)
                    page_count += 1

            print(f"  -> Found {page_count} new PDFs")

        except Exception as e:
            print(f"Couldn't load {target_url}: {e}")

        # Be polite and avoid overwhelming the server
        time.sleep(0.5)

    file_path = os.path.join(save_dir, "pdf_links.txt")
    with open(file_path, "w", encoding="utf-8") as f:
        for link in sorted(all_pdf_links):
            f.write(link + "\n")

    print("-" * 30)
    print("Scan complete!")
    print(f"Total unique PDF links found: {len(all_pdf_links)}")
    print(f"Results saved to: {file_path}")


if __name__ == "__main__":
    scrape_paginated_archives()
