import os

file_path = "requirements.txt"
with open(file_path, "r", encoding="utf-16") as f:
    content = f.read()

# Add holidays to content if not present
if "holidays" not in content:
    if not content.endswith("\n"):
        content += "\n"
    content += "holidays\n"
    with open(file_path, "w", encoding="utf-16") as f:
        f.write(content)
    print("Added holidays to requirements.txt")
else:
    print("holidays already in requirements.txt")
