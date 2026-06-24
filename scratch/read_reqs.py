import os

file_path = "requirements.txt"
encodings = ["utf-16le", "utf-16", "utf-8", "latin-1"]
for enc in encodings:
    try:
        with open(file_path, "r", encoding=enc) as f:
            content = f.read()
        print(f"SUCCESS with {enc}:")
        print(content)
        break
    except Exception as e:
        print(f"FAILED with {enc}: {e}")
