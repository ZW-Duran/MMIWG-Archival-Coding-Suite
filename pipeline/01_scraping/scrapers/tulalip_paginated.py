import requests
import re
import time
import os
from urllib.parse import urljoin

domain_url = "https://tulalipnews.com"
# Base URL template for pagination, {} will be replaced by page number
base_url = "https://tulalipnews.com/category/tulalip-news/see-yaht-sub-pdfs/page/{}/"

all_pdf_links = set()

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

save_dir = "original"
if not os.path.exists(save_dir):
    os.makedirs(save_dir)

# Loop through pages 
for page_num in range(1, 63):
    target_url = base_url.format(page_num)
    print(f"Scanning Page {page_num}: {target_url} ...")
    
    try:
        response = requests.get(target_url, headers=headers, timeout=20)
        response.raise_for_status()
        links = re.findall(r'href=["\']([^"\']+\.pdf)["\']', response.text)
      
        page_count = 0
        for link in links:
            full_url = urljoin(domain_url, link)
            
            if full_url not in all_pdf_links:
                all_pdf_links.add(full_url)
                page_count += 1
        
        print(f"  -> Found {page_count} new PDFs")
            
    except Exception as e:
        print(f"Couldn't load {target_url}: {e}")
    
    # Be polite and avoid overwhelming the server
    time.sleep(0.5)

file_path = os.path.join(save_dir, "tulalip_pdf_links.txt")
sorted_links = sorted(list(all_pdf_links))

with open(file_path, "w", encoding="utf-8") as f:
    for link in sorted_links:
        f.write(link + "\n")

print("-" * 30)
print(f"Scan complete!")
print(f"Total unique PDF links found: {len(all_pdf_links)}")
print(f"Results saved to: {file_path}")