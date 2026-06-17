with open("setup_scheduler.ps1", "r", encoding="utf-8") as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    line_num = i + 1
    quotes_count = line.count('"')
    if quotes_count % 2 != 0:
        print(f"Line {line_num} has odd number of double quotes ({quotes_count}): {repr(line)}")
