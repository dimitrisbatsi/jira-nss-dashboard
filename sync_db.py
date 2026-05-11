import tomllib
import requests
import sqlite3
import pandas as pd
import logging
import sys
import os 
import pprint
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
max_results = 100 # Το επαναφέρουμε στο 100 (όχι 2) για ταχύτητα!
total_issues = 0

jql = 'project IN (PYLCOM, PYLFLE, GLXENT, ESLKAS, PYLACC, PYLHOS, ESLLEG, CLCNTR) AND issuetype = "Time Type" AND (status = "Time Entered" OR status = "Time-Entered") ORDER BY created DESC'
fields = "worklog,assignee,summary,project,components,customfield_10553,customfield_10193,parent"

try:
    while True:
        params = {"jql": jql, "fields": fields, "maxResults": max_results}
        if page_token:
            params["nextPageToken"] = page_token
            
        response = requests.get(BASE_URL, params=params, headers=headers, timeout=60)
        
        if not response.ok:
            logging.error(f"❌ Σφάλμα API {response.status_code}: {response.text}")
            response.raise_for_status() 
            
        data = response.json()
        
        if not page_token:
            total_issues = data.get("total", 0)
            if total_issues > 0:
                logging.info(f"📊 Το Jira βρήκε συνολικά {total_issues} tickets.")
            else:
                logging.info("📊 Το Jira ξεκίνησε την αποστολή (άγνωστο το τελικό σύνολο)...")
        elif len(all_issues) % 1000 == 0:
            if total_issues > 0:
                logging.info(f"⏳ Έχουν κατέβει {len(all_issues)} / {total_issues} tickets...")
            else:
                logging.info(f"⏳ Έχουν κατέβει {len(all_issues)} tickets...")

        batch = data.get("issues", [])
        if not batch: 
            break
            
        all_issues.extend(batch)
        
        # ΒΓΑΛΑΜΕ ΤΟ COMMENT: Είναι απαραίτητο για να κατέβουν όλα τα δεδομένα!
        page_token = data.get("nextPageToken")
        
        if not page_token or data.get("isLast") == True:
            break

    logging.info(f"📥 Λήφθηκαν {len(all_issues)} tickets χρόνου.")

except Exception as e:
    logging.error(f"❌ Αποτυχία κλήσης στο Jira API: {e}\n")
    sys.exit(1)


# --- 3.5 Λήψη Δεδομένων Parent Issues (Bulk Fetching) ---
try:
    unique_parents = set()
    for issue in all_issues:
        pk = issue.get("fields", {}).get("parent", {}).get("key")
        if pk:
            unique_parents.add(pk)

    parent_fields_dict = {}
    if unique_parents:
        logging.info(f"🔍 Εντοπίστηκαν {len(unique_parents)} μοναδικά Parent Issues. Λήψη των Custom Fields...")
        unique_parents_list = list(unique_parents)
        
        # Μείωση σε 50 για να μην "σκάει" το API με Timeout ή "URI Too Long"
        chunk_size = 50 
        for i in range(0, len(unique_parents_list), chunk_size):
            chunk = unique_parents_list[i:i + chunk_size]
            
            # Βάζουμε διπλά εισαγωγικά σε κάθε Key για ασφάλεια (π.χ. "PROJ-1", "PROJ-2")
            safe_keys = ",".join([f'"{c}"' for c in chunk])
            jql_parents = f'key IN ({safe_keys})'
            
            params_parents = {
                "jql": jql_parents, 
                "fields": "summary,customfield_11180,customfield_11183", 
                "maxResults": chunk_size
            }
            
            resp_parents = requests.get(BASE_URL, params=params_parents, headers=headers, timeout=60)
            if resp_parents.ok:
                parents_data = resp_parents.json().get("issues", [])
                for p in parents_data:
                    parent_fields_dict[p["key"]] = p.get("fields", {})
            else:
                logging.warning(f"⚠️ Αποτυχία λήψης Parent chunk: {resp_parents.text}")
                
    logging.info("✅ Η λήψη των Parent Custom Fields ολοκληρώθηκε.")

except Exception as e:
    # Το exc_info=True θα τυπώσει στο log ΟΛΟ το traceback (ποια γραμμή έσκασε)
    logging.error(f"❌ Κρίσιμο σφάλμα κατά τη λήψη των Parent Issues: {e}", exc_info=True)
    sys.exit(1)


# --- 4. Μετασχηματισμός (Transform) ---
try:
    logging.info("⚙️ Ξεκινάει ο μετασχηματισμός των δεδομένων...")
    
    def safe_get(data, key, subkey="value", default="N/A"):
        item = data.get(key)
        if isinstance(item, dict):
            return item.get(subkey, default)
        elif item is not None:
            return str(item)
        return default

    rows = []
    for issue in all_issues:
        f = issue.get("fields", {})
        project = f.get("project", {}).get("name", "N/A")
        time_type = safe_get(f, "customfield_10553")
        charge_type = safe_get(f, "customfield_10193")
        parent_key = f.get("parent", {}).get("key", "N/A")

        cf_11180_val = "N/A"
        cf_11183_val = "N/A"
        if parent_key in parent_fields_dict:
            p_fields = parent_fields_dict[parent_key]
            parent_title = p_fields.get("summary", {})
            cf_11180_val = safe_get(p_fields, "customfield_11180")
            cf_11183_val = safe_get(p_fields, "customfield_11183")

        jira_components = f.get("components", [])
        
        # Η νέα λογική για τα πολλαπλά components με κόμμα
        comp_names = [c.get("name").strip() for c in jira_components if c.get("name")]
        components_str = ", ".join(comp_names) if comp_names else "No Component"
        
        parent_category = "No Component"
        if jira_components:
            c = jira_components[0]
            parent_category = c.get("description", "").strip() or c.get("name")

        worklogs = f.get("worklog", {}).get("worklogs", [])
        for wl in worklogs:
            rows.append({
                "Issue Key": issue["key"],
                "Parent Key": parent_key,
                "Parent Title": parent_title,
                "Project": project,
                "Assignee": wl.get("author", {}).get("displayName", "Unknown"),
                "Time Type": time_type,
                "Charge Type": charge_type,
                "Minutes": wl["timeSpentSeconds"] / 60,
                "Date": wl["started"][:10],
                "Parent Category": parent_category,
                "Components": components_str,
                "Partner Name": cf_11180_val,
                "LSP Customer Name": cf_11183_val
            })

    df = pd.DataFrame(rows)
    logging.info(f"✅ Ο μετασχηματισμός ολοκληρώθηκε. Προετοιμασία εγγραφής στη βάση...")

except Exception as e:
    logging.error(f"❌ Κρίσιμο σφάλμα κατά τον μετασχηματισμό: {e}", exc_info=True)
    sys.exit(1)

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