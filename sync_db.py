import tomllib
import requests
import sqlite3
import pandas as pd
import logging
import sys
import os  # <-- Προσθέσαμε το os για διαχείριση φακέλων
from datetime import datetime

# --- 0. Ρύθμιση Logging (Ημερήσια Logs) ---
# 1. Δημιουργία του φακέλου "logs" αν δεν υπάρχει ήδη
log_dir = "logs"
os.makedirs(log_dir, exist_ok=True)

# 2. Φτιάχνουμε δυναμικό όνομα αρχείου με τη σημερινή ημερομηνία (π.χ. sync_2026-03-23.log)
current_date = datetime.now().strftime("%Y-%m-%d")
log_filename = os.path.join(log_dir, f"sync_{current_date}.log")

# 3. Ρύθμιση του logger για να γράφει στο σημερινό αρχείο και στην οθόνη
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.FileHandler(log_filename, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)

logging.info("🚀 Ξεκινάει ο κύκλος συγχρονισμού με το Jira...")

# --- 1. Ανάγνωση Secrets & Καθαρισμός ---
try:
    with open(".streamlit/secrets.toml", "rb") as f:
        secrets = tomllib.load(f)
    API_TOKEN = secrets["JIRA_JWT_TOKEN"].strip() 
except Exception as e:
    logging.error(f"❌ Σφάλμα ανάγνωσης secrets: {e}")
    sys.exit(1)

# --- 2. Στήσιμο URL ---
JIRA_CLOUD_ID = "58c421e1-1855-4c95-8c07-df2d79817fdd"
BASE_URL = f"https://api.atlassian.com/ex/jira/{JIRA_CLOUD_ID}/rest/api/3/search/jql"

headers = {
    "Accept": "application/json",
    "Authorization": f"Bearer {API_TOKEN}"
}

# --- 3. Λήψη Δεδομένων από Jira ---
all_issues = []
page_token = ""
max_results = 100
total_issues = 0

jql = 'project IN (PYLCOM, PYLFLE, GLXENT, ESLKAS, PYLACC, PYLHOS, ESLLEG) AND issuetype = "Time Type" AND status = "Time Entered" ORDER BY created DESC'
fields = "worklog,assignee,summary,project,components,customfield_10553,customfield_10193,parent"

try:
    while True:
        params = {"jql": jql, "fields": fields, "maxResults": max_results}
        
        if page_token:
            params["nextPageToken"] = page_token
            
        response = requests.get(BASE_URL, params=params, headers=headers, timeout=30)
        
        if not response.ok:
            logging.error(f"❌ Σφάλμα API {response.status_code}: {response.text}")
            response.raise_for_status() 
            
        data = response.json()
        
        # Ενημέρωση Log στην πρώτη κλήση
        if not page_token:
            total_issues = data.get("total", 0)
            if total_issues > 0:
                logging.info(f"📊 Το Jira βρήκε συνολικά {total_issues} tickets.")
            else:
                logging.info("📊 Το Jira ξεκίνησε την αποστολή (άγνωστο το τελικό σύνολο)...")
        # Ενημέρωση Log κάθε 1000 εγγραφές (δεν τυπώνουμε το 0 πλέον)
        elif len(all_issues) % 1000 == 0:
            if total_issues > 0:
                logging.info(f"⏳ Έχουν κατέβει {len(all_issues)} / {total_issues} tickets...")
            else:
                logging.info(f"⏳ Έχουν κατέβει {len(all_issues)} tickets...")

        batch = data.get("issues", [])
        if not batch: 
            break
            
        all_issues.extend(batch)
        
        page_token = data.get("nextPageToken")
        
        if not page_token or data.get("isLast") == True:
            break

    logging.info(f"📥 Λήφθηκαν επιτυχώς {len(all_issues)} tickets. Προετοιμασία μετασχηματισμού...")

except Exception as e:
    logging.error(f"❌ Αποτυχία κλήσης στο Jira API: {e}\n")
    sys.exit(1)

# --- 4. Μετασχηματισμός (Transform) ---
def safe_get(data, key, subkey="value", default="N/A"):
    item = data.get(key)
    return item.get(subkey, default) if item else default

rows = []
for issue in all_issues:
    f = issue.get("fields", {})
    project = f.get("project", {}).get("name", "N/A")
    time_type = safe_get(f, "customfield_10553")
    charge_type = safe_get(f, "customfield_10193")
    parent_key = f.get("parent", {}).get("key", "N/A")
    
    jira_components = f.get("components", [])
    parent_category = "No Component"
    if jira_components:
        c = jira_components[0]
        name = c["name"]
        desc = c.get("description", "").strip()
        parent_category = desc if desc else name

    worklogs = f.get("worklog", {}).get("worklogs", [])
    for wl in worklogs:
        rows.append({
            "Issue Key": issue["key"],
            "Parent Key": parent_key,
            "Project": project,
            "Assignee": wl.get("author", {}).get("displayName", "Unknown"),
            "Time Type": time_type,
            "Charge Type": charge_type,
            "Minutes": wl["timeSpentSeconds"] / 60,
            "Date": wl["started"][:10],
            "Parent Category": parent_category
        })

df = pd.DataFrame(rows)

# --- 5. Εγγραφή στη Βάση Δεδομένων (Load) ---
try:
    if not df.empty:
        conn = sqlite3.connect('timesheet.db')
        df.to_sql('worklogs', conn, if_exists='replace', index=False)
        conn.close()
        logging.info(f"✅ Ο συγχρονισμός ολοκληρώθηκε! Αποθηκεύτηκαν {len(df)} εγγραφές.\n")
    else:
        logging.warning("⚠️ Δεν βρέθηκαν δεδομένα (worklogs) στα tickets που κατέβηκαν.\n")
except Exception as e:
    logging.error(f"❌ Σφάλμα κατά την εγγραφή στην SQLite: {e}\n")
    sys.exit(1)