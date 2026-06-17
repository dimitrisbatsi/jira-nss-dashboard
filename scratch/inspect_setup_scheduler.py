with open("setup_scheduler.ps1", "rb") as f:
    lines = f.readlines()
    line_76 = lines[75] # line 76 is index 75
    print("Raw Bytes of line 76:")
    print(line_76)
    print("Decoded (utf-8):")
    print(line_76.decode("utf-8", errors="replace"))
    for char in line_76.decode("utf-8", errors="replace"):
        print(f"Char: {repr(char)}, Ord: {ord(char)}")
