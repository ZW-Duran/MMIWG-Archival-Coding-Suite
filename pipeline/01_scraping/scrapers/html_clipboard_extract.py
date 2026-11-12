import re
import os
import sys

html_snippet = ""
if "--file" in sys.argv:
    try:
        file_index = sys.argv.index("--file") + 1
        file_path = sys.argv[file_index]
        with open(file_path, "r", encoding="utf-8") as f:
            html_snippet = f.read()
        print(f"Read HTML from: {file_path}")
    except (IndexError, FileNotFoundError) as e:
        print(f"Error reading file: {e}")
        sys.exit(1)
else:
    print("Please enter the HTML source code (input 'EOF' and press Enter when done, or press Ctrl+D to finish):")
    lines = []
    while True:
        try:
            line = input()
            if line.strip() == "EOF":
                break
            lines.append(line)
        except EOFError:
            break
    html_snippet = "\n".join(lines)


links = re.findall(r'href=["\']?([^"\'>]+\.pdf[^\s"\'?>]*)', html_snippet, re.I)
base_url = "https://snoqualmietribe.us"


unique_full_links = set()
for l in links:
    full_url = base_url + l if l.startswith('/') else l
    unique_full_links.add(full_url)


sorted_links = sorted(list(unique_full_links))

print("\n--- PDF Links (Unique) ---")

if sorted_links:
    output_content = "\n".join(sorted_links)
    print(output_content)
    
    save_dir = "./original"
    if not os.path.exists(save_dir):
        os.makedirs(save_dir)
        
    file_path = os.path.join(save_dir, "pdf_links.txt")
    with open(file_path, "a", encoding="utf-8") as f:
        f.write(output_content +"\n")
    
    print(f"\nSaved in: {file_path}")
else:
    print("No PDF links found.")