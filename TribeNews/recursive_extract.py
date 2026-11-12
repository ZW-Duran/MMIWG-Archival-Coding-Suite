import requests
import re
import time
import os

domain_url = "https://www.chehalistribe.org"
base_url = "https://www.chehalistribe.org/newsletters/newsletters-for-{}/#gsc.tab=0"

all_pdf_links = set()

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

save_dir = "original"
if not os.path.exists(save_dir):
    os.makedirs(save_dir)

for page_num in range(2008, 2027):
    target_url = base_url.format(page_num)
    print(f"Scanning page {page_num}...")
    
    try:
        response = requests.get(target_url, headers=headers, timeout=15)
        response.raise_for_status()

        links = re.findall(r'href="([^"]+\.pdf)"', response.text)
      
        for link in links:
            if link.startswith('/'):
                full_url = domain_url + link
            elif link.startswith('http'):
                full_url = link
            else:
                full_url = domain_url + "/" + link
                
            all_pdf_links.add(full_url)
            
    except Exception as e:
        print(f"Fail to load {target_url}: {e}")
    
    time.sleep(0.2)

file_path = os.path.join(save_dir, "pdf_links.txt")
sorted_links = sorted(list(all_pdf_links))

with open(file_path, "w", encoding="utf-8") as f:
    for link in sorted_links:
        f.write(link + "\n")

print(f"\nFinished! Total unique PDFs found: {len(all_pdf_links)}")
print(f"Links saved to: {file_path}")