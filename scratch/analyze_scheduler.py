with open("setup_scheduler.ps1", "r", encoding="utf-8") as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    line_num = i + 1
    # Check if line ends with a backtick (ignoring newline)
    stripped = line.rstrip("\r\n")
    if stripped.endswith("`"):
        # Check if there was trailing whitespace before the backtick
        # (Wait, if stripped ends with ` then there is no trailing whitespace in the stripped string,
        # but let's check the original line before stripping \r\n)
        original_no_newline = line.replace("\r", "").replace("\n", "")
        if original_no_newline.endswith(" "):
            print(f"Line {line_num} has trailing space after backtick: {repr(original_no_newline)}")
        elif original_no_newline.endswith("`"):
            # This is correct
            pass
        else:
            # There is some whitespace after the backtick
            backtick_idx = original_no_newline.find("`")
            after_backtick = original_no_newline[backtick_idx+1:]
            print(f"Line {line_num} has characters/spaces after backtick: {repr(original_no_newline)}")
    else:
        # Check if it has a backtick with spaces after it
        if "` " in line:
            print(f"Line {line_num} has backtick followed by space: {repr(line)}")
