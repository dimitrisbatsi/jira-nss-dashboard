import json
import requests
from src.api.jira_client import JiraAPIClient

def export_jira_first_page():
    print("[*] Ξεκινάει το Debugging...")
    client = JiraAPIClient()
    
    # Χρησιμοποιούμε το JQL που σου έβγαζε το πρόβλημα
    jql_query = 'project IN (PYLCOM, PYLFLE) ORDER BY created DESC'
    
    # Ζητάμε μόνο 5 issues για να είναι το JSON ευανάγνωστο (και όχι 50.000 γραμμές)
    params = {
        "jql": jql_query,
        "startAt": 0,
        "maxResults": 5, 
        "expand": "changelog"
    }
    
    endpoint = f"{client.base_url}/rest/api/3/search/jql"
    
    print(f"[*] Κλήση στο API: {endpoint}")
    response = requests.get(endpoint, headers=client.headers, params=params, timeout=30)
    
    if response.status_code == 200:
        data = response.json()
        
        # Αποθήκευση σε αρχείο
        filename = "jira_debug_page1.json"
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
            
        print(f"\n[ΕΠΙΤΥΧΙΑ] Τα δεδομένα αποθηκεύτηκαν στο αρχείο: {filename}")
        print(f"Συνολικά Issues (βάσει API): {data.get('total')}")
        print(f"Επεστράφησαν: {len(data.get('issues', []))} issues.")
        
        # Κάνουμε και έναν γρήγορο έλεγχο αν υπάρχει το αντικείμενο 'fields' στο πρώτο issue
        if data.get('issues'):
            first_issue = data['issues'][0]
            fields_count = len(first_issue.get('fields', {}))
            print(f"\n[ΓΡΗΓΟΡΟΣ ΕΛΕΓΧΟΣ] Το Issue {first_issue.get('key')} περιέχει {fields_count} πεδία στο αντικείμενο 'fields'.")
            if fields_count == 0:
                print(" ⚠️ ΠΡΟΣΟΧΗ: Το αντικείμενο 'fields' είναι ΕΝΤΕΛΩΣ ΑΔΕΙΟ!")
            else:
                print(" ✅ Το αντικείμενο 'fields' φαίνεται γεμάτο!")
                
    else:
        print(f"[ΣΦΑΛΜΑ] {response.status_code}: {response.text}")

if __name__ == "__main__":
    export_jira_first_page()