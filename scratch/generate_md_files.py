import json
import os

extension_dir = r"c:\Users\d.batsilis\OneDrive - Epsilon Net S.A\Development\NSSTimesheetApp\jira-support-pilot-extension"
md_dir = os.path.join(extension_dir, "canned_responses")
os.makedirs(md_dir, exist_ok=True)

json_path = os.path.join(extension_dir, "canned_responses.json")
with open(json_path, 'r', encoding='utf-8') as f:
    canned = json.load(f)

def make_safe_filename(s):
    for c in '<>:"/\\|?*→':
        s = s.replace(c, '_')
    return s.strip()

for idx, item in enumerate(canned, 1):
    title = item["title"]
    body = item["body"]
    
    # Create safe filename
    safe_title = make_safe_filename(title)
    safe_title = safe_title[:50]
    filename = f"{idx:02d}_{safe_title}.md"
    file_path = os.path.join(md_dir, filename)
    
    with open(file_path, 'w', encoding='utf-8') as f_out:
        f_out.write(f"# {title}\n\n{body}\n")

print(f"Generated {len(canned)} markdown files in {md_dir}")
