import requests
import re
import time
import os
from urllib.parse import urljoin

base_domain = "https://www.cowlitz.org"
base_url_template = "https://www.cowlitz.org/{year}-{season}-yooyoolah"
all_pdf_links = set()

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

save_dir = "original"
os.makedirs(save_dir, exist_ok=True)

years = range(2021, 2026) 
seasons = ["winter", "spring", "fall"]

pdf_pattern = re.compile(r'(?:href|src)="([^"]+\.pdf[^"]*)"', re.IGNORECASE)

for year in years:
    for season in seasons:
        if year == 2025 and season == "winter":
            break
            
        target_url = base_url_template.format(year=year, season=season)
        print(f"Scanning: {target_url} ...")
        
        try:
            response = requests.get(target_url, headers=headers, timeout=15)
            response.raise_for_status()

            links = pdf_pattern.findall(response.text)
        
            for link in links:
                full_url = urljoin(base_domain, link)
                clean_url = full_url.split('#')[0].split('?')[0]
                
                all_pdf_links.add(clean_url)
                
        except Exception as e:
            print(f"Skip or Fail to load {target_url}")
        
        time.sleep(0.5)

file_path = os.path.join(save_dir, "pdf_links.txt")
sorted_links = sorted(list(all_pdf_links))

with open(file_path, "w", encoding="utf-8") as f:
    for link in sorted_links:
        f.write(link + "\n")

print(f"\nFinished! Total unique PDFs: {len(all_pdf_links)}")
print(f"Links saved to: {file_path}")