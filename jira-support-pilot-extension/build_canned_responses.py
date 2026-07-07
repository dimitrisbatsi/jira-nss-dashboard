import os
import json
import re

def compile_markdown_responses():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    md_dir = os.path.join(current_dir, "canned_responses")
    output_json = os.path.join(current_dir, "canned_responses.json")
    
    if not os.path.exists(md_dir):
        print(f"Error: Directory {md_dir} does not exist.")
        return
        
    compiled_responses = []
    
    # Read all files in canned_responses folder ending with .md
    files = [f for f in os.listdir(md_dir) if f.lower().endswith('.md')]
    # Sort files naturally
    files.sort()
    
    for filename in files:
        filepath = os.path.join(md_dir, filename)
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
                
            # Parse Title and Body
            # Check if it starts with # Title
            lines = content.split('\n')
            title = ""
            body_lines = []
            
            if lines and lines[0].startswith('# '):
                title = lines[0][2:].strip()
                body_lines = lines[1:]
            else:
                # Fallback to filename (strip extension and leading numbers)
                name_without_ext = os.path.splitext(filename)[0]
                # Strip leading number prefix (e.g. "01_")
                title = re.sub(r'^\d+[_.-]\s*', '', name_without_ext).replace('_', ' ')
                body_lines = lines
                
            body = '\n'.join(body_lines).strip()
            
            compiled_responses.append({
                "title": title,
                "body": body
            })
            
        except Exception as e:
            print(f"Error reading file {filename}: {e}")
            
    # Write to canned_responses.json
    with open(output_json, 'w', encoding='utf-8') as f:
        json.dump(compiled_responses, f, ensure_ascii=False, indent=2)
        
    print(f"Successfully compiled {len(compiled_responses)} markdown canned responses into {output_json}!")

if __name__ == "__main__":
    compile_markdown_responses()
