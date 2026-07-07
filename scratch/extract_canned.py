import zipfile
import xml.etree.ElementTree as ET
import os

def extract_docx_text(docx_path):
    if not os.path.exists(docx_path):
        print(f"File not found: {docx_path}")
        return ""
    
    try:
        with zipfile.ZipFile(docx_path) as z:
            doc_xml = z.read('word/document.xml')
            root = ET.fromstring(doc_xml)
            
            # Find all paragraph elements
            paragraphs = []
            for paragraph in root.iter('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p'):
                texts = [node.text for node in paragraph.iter('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t') if node.text]
                if texts:
                    paragraphs.append("".join(texts))
                else:
                    paragraphs.append("")
            return "\n".join(paragraphs)
    except Exception as e:
        print(f"Error reading docx: {e}")
        return ""

if __name__ == "__main__":
    docx_path = r"c:\Users\d.batsilis\OneDrive - Epsilon Net S.A\Development\NSSTimesheetApp\Πρότυπες απαντήσεις_V1 5 (2).docx"
    text = extract_docx_text(docx_path)
    print(f"Extracted {len(text)} characters.")
    
    txt_output_path = r"c:\Users\d.batsilis\OneDrive - Epsilon Net S.A\Development\NSSTimesheetApp\scratch\extracted_canned.txt"
    with open(txt_output_path, 'w', encoding='utf-8') as f:
        f.write(text)
    print(f"Saved to {txt_output_path}")
