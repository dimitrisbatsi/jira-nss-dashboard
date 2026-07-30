import os
import json
import re

def compile_markdown_responses():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    canned_dir = os.path.join(current_dir, "canned_responses")
    output_json = os.path.join(current_dir, "canned_responses.json")
    
    if not os.path.exists(canned_dir):
        print(f"Error: Directory {canned_dir} does not exist.")
        return
        
    compiled_responses = []
    
    # We will search in two subdirectories: 'system' and 'custom'
    categories = [("system", "System"), ("custom", "Custom")]
    
    for subfolder, cat_name in categories:
        subfolder_path = os.path.join(canned_dir, subfolder)
        if not os.path.exists(subfolder_path):
            os.makedirs(subfolder_path, exist_ok=True)
            continue
            
        files = [f for f in os.listdir(subfolder_path) if f.lower().endswith('.md')]
        files.sort()
        
        for filename in files:
            filepath = os.path.join(subfolder_path, filename)
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                    
                lines = content.split('\n')
                title = ""
                body_lines = []
                
                if lines and lines[0].startswith('# '):
                    title = lines[0][2:].strip()
                    body_lines = lines[1:]
                else:
                    name_without_ext = os.path.splitext(filename)[0]
                    title = re.sub(r'^\d+[_.-]\s*', '', name_without_ext).replace('_', ' ')
                    body_lines = lines
                    
                body = '\n'.join(body_lines).strip()
                
                compiled_responses.append({
                    "title": title,
                    "body": body,
                    "category": cat_name
                })
                
            except Exception as e:
                print(f"Error reading file {subfolder}/{filename}: {e}")
                
    # Write to canned_responses.json
    with open(output_json, 'w', encoding='utf-8') as f:
        json.dump(compiled_responses, f, ensure_ascii=False, indent=2)
        
    print(f"Successfully compiled {len(compiled_responses)} markdown canned responses into {output_json}!")

if __name__ == "__main__":
    compile_markdown_responses()
