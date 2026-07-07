import os
import sys

def inspect_requirements():
    req_path = r"c:\Users\d.batsilis\OneDrive - Epsilon Net S.A\Development\NSSTimesheetApp\requirements.txt"
    encodings = ['utf-16', 'utf-16-le', 'utf-16-be', 'utf-8', 'cp1253', 'latin1']
    for enc in encodings:
        try:
            with open(req_path, 'r', encoding=enc) as f:
                content = f.read()
                if len(content.strip()) > 0:
                    print(f"--- Requirements ({enc}) ---")
                    print(content[:1000])
                    return
        except Exception as e:
            pass
    print("Could not read requirements.txt")

if __name__ == "__main__":
    inspect_requirements()
