import os
import json
import zipfile
from datetime import datetime
from pathlib import Path

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent
EXTENSION_DIR = BASE_DIR / "jira-support-pilot-extension"
STATIC_DIR = BASE_DIR / "static"
ZIP_FILE_PATH = STATIC_DIR / "jira-support-pilot-extension.zip"
VERSION_JSON_PATH = STATIC_DIR / "version.json"
MANIFEST_PATH = EXTENSION_DIR / "manifest.json"

def get_extension_manifest():
    """Reads manifest.json from the extension directory."""
    if not MANIFEST_PATH.exists():
        return None
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def package_extension():
    """
    Zips the jira-support-pilot-extension folder into static/jira-support-pilot-extension.zip
    and creates static/version.json for endpoint consumption.
    """
    if not EXTENSION_DIR.exists() or not MANIFEST_PATH.exists():
        print(f"Extension directory or manifest not found at {EXTENSION_DIR}")
        return None

    manifest = get_extension_manifest()
    version = manifest.get("version", "1.0")

    # Ensure static directory exists
    STATIC_DIR.mkdir(parents=True, exist_ok=True)

    # Exclude files/folders during zipping
    ignore_names = {"__pycache__", ".git", ".DS_Store", "Thumbs.db"}
    ignore_exts = {".pyc", ".pyo", ".zip"}

    # Zip the extension directory
    with zipfile.ZipFile(ZIP_FILE_PATH, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for root, dirs, files in os.walk(EXTENSION_DIR):
            # Exclude unwanted directories
            dirs[:] = [d for d in dirs if d not in ignore_names]
            
            for file in files:
                if file in ignore_names or any(file.endswith(ext) for ext in ignore_exts):
                    continue
                file_path = Path(root) / file
                archive_name = file_path.relative_to(EXTENSION_DIR)
                zip_file.write(file_path, archive_name)

    # Create version.json
    version_info = {
        "name": manifest.get("name", "Jira Support Pilot"),
        "version": version,
        "description": manifest.get("description", ""),
        "download_url": "/app/static/jira-support-pilot-extension.zip",
        "filename": "jira-support-pilot-extension.zip",
        "updated_at": datetime.now().isoformat(),
        "release_notes": f"Jira Support Pilot v{version}"
    }

    with open(VERSION_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(version_info, f, ensure_ascii=False, indent=2)

    return version_info

def should_repackage():
    """Checks if any file in EXTENSION_DIR is newer than ZIP_FILE_PATH or if version changed."""
    if not ZIP_FILE_PATH.exists() or not VERSION_JSON_PATH.exists():
        return True

    try:
        zip_mtime = ZIP_FILE_PATH.stat().st_mtime
        manifest = get_extension_manifest()
        if manifest:
            with open(VERSION_JSON_PATH, "r", encoding="utf-8") as f:
                cached_info = json.load(f)
            if cached_info.get("version") != manifest.get("version"):
                return True
                
        # Check if any file in extension directory has been modified after zip creation
        for root, dirs, files in os.walk(EXTENSION_DIR):
            for file in files:
                file_path = Path(root) / file
                if file_path.stat().st_mtime > zip_mtime:
                    return True
    except Exception:
        return True

    return False

def get_latest_extension_info(force_repack=False):
    """
    Returns latest version info and zip bytes.
    Automatically repackages if files inside extension directory or version in manifest.json changed.
    """
    if force_repack or should_repackage():
        package_extension()

    if not VERSION_JSON_PATH.exists():
        return None, None

    with open(VERSION_JSON_PATH, "r", encoding="utf-8") as f:
        version_info = json.load(f)

    zip_bytes = None
    if ZIP_FILE_PATH.exists():
        with open(ZIP_FILE_PATH, "rb") as f:
            zip_bytes = f.read()

    return version_info, zip_bytes

if __name__ == "__main__":
    info = package_extension()
    print("Extension packaged successfully:", info)
