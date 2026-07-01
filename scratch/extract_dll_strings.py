import re

dll_path = r"C:\Users\d.batsilis\source\repos\dimitrisbatsi\GeminiBridge\GeminiBridge\libs\Countersoft.Gemini.Api.dll"

try:
    with open(dll_path, "rb") as f:
        data = f.read()
        
    # Search for ASCII strings
    ascii_strings = re.findall(b"[a-zA-Z0-9_/.-]{4,}", data)
    print("=== ASCII Strings matching patterns ===")
    for s in ascii_strings:
        s_str = s.decode("ascii", errors="ignore")
        if "items" in s_str.lower() or "customfield" in s_str.lower():
            print("  ", s_str)
            
    # Search for UTF-16 strings
    utf16_strings = re.findall(b"(?:[a-zA-Z0-9_/.-]\x00){4,}", data)
    print("\n=== UTF-16 Strings matching patterns ===")
    for s in utf16_strings:
        # replace null bytes
        s_str = s.replace(b"\x00", b"").decode("ascii", errors="ignore")
        if "items" in s_str.lower() or "customfield" in s_str.lower():
            print("  ", s_str)
            
except Exception as e:
    print(f"Error: {e}")
