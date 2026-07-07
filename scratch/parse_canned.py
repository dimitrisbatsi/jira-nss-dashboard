import re
import json

def parse_canned_responses(txt_path):
    with open(txt_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    titles_list = []
    # TOC lines
    for line in lines[1:41]:
        # Strip number and page number
        match = re.match(r'^\d+\.\s*(.*?)\s*\d*$', line.strip())
        if match:
            titles_list.append(match.group(1).strip())
        else:
            match = re.match(r'^\d+\.\s*(.*)$', line.strip())
            if match:
                titles_list.append(match.group(1).strip())

    print(f"Loaded {len(titles_list)} titles from TOC.")
    
    sections = []
    current_title = None
    current_body = []
    
    def clean_string(s):
        # Remove leading number if any (e.g. "36. Title" -> "Title")
        s = re.sub(r'^\d+\.\s*', '', s)
        s = s.replace('→', '->')
        s = re.sub(r'\s+', ' ', s)
        return s.strip().lower()

    cleaned_titles_map = {}
    for t in titles_list:
        cleaned_titles_map[clean_string(t)] = t
        parts = t.split('→') if '→' in t else t.split('->')
        if len(parts) > 1:
            cleaned_titles_map[clean_string(parts[0])] = t
            cleaned_titles_map[clean_string(parts[1])] = t

    for line in lines[42:]:
        line_str = line.strip()
        if not line_str:
            if current_title:
                current_body.append("")
            continue
        
        line_clean = clean_string(line_str)
        matched_title = None
        
        for c_t, orig_t in cleaned_titles_map.items():
            # If line is longer, check if it starts with the title, or if title starts with the line
            if len(c_t) >= 15:
                if line_clean.startswith(c_t[:15]) or c_t.startswith(line_clean[:15]):
                    matched_title = orig_t
                    break
            else:
                if line_clean == c_t:
                    matched_title = orig_t
                    break
        
        if matched_title:
            if current_title:
                sections.append({
                    "title": current_title,
                    "body": "\n".join(current_body).strip()
                })
            current_title = matched_title
            current_body = []
        else:
            if current_title:
                current_body.append(line.rstrip('\n'))

    if current_title:
        sections.append({
            "title": current_title,
            "body": "\n".join(current_body).strip()
        })

    print(f"Extracted {len(sections)} sections successfully.")
    return sections

if __name__ == "__main__":
    txt_path = r"c:\Users\d.batsilis\OneDrive - Epsilon Net S.A\Development\NSSTimesheetApp\scratch\extracted_canned.txt"
    sections = parse_canned_responses(txt_path)
    
    # Save as JSON
    output_path = r"c:\Users\d.batsilis\OneDrive - Epsilon Net S.A\Development\NSSTimesheetApp\scratch\canned_responses.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(sections, f, ensure_ascii=False, indent=2)
    print(f"JSON saved to {output_path}")
