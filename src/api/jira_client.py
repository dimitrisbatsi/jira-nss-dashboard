import os
import requests
from dotenv import load_dotenv

# Αν το αρχείο τρέχει αυτόνομα, πρέπει να φορτώσουμε το .env
load_dotenv()

class JiraAPIClient:
    def __init__(self):
        self.cloud_id = os.getenv("JIRA_CLOUD_ID", "").strip()
        self.api_token = os.getenv("JIRA_API_TOKEN", "").strip()

        if not all([self.cloud_id, self.api_token]):
            raise ValueError("Λείπουν τα credentials του Jira (JIRA_CLOUD_ID ή JIRA_API_TOKEN) από το .env αρχείο.")

        # Το base URL για Service Accounts / OAuth 2.0 μέσω Atlassian API
        self.base_url = f"https://api.atlassian.com/ex/jira/{self.cloud_id}"
        
        # Bearer Token Authentication
        self.headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_token}"
        }

    def test_connection(self) -> bool:
        """
        Δοκιμάζει τη σύνδεση χτυπώντας το /myself endpoint.
        Επιστρέφει True αν πετύχει, αλλιώς τυπώνει το λάθος και επιστρέφει False.
        """
        endpoint = f"{self.base_url}/rest/api/3/myself"
        
        print(f"[*] Δοκιμή σύνδεσης στο Atlassian API (Cloud ID: {self.cloud_id[:8]}...) ...")
        try:
            # Βάζουμε timeout 15 δευτερόλεπτα
            response = requests.get(endpoint, headers=self.headers, timeout=15)
            
            if response.status_code == 200:
                user_data = response.json()
                name = user_data.get('displayName', 'Unknown Bot/Service Account')
                print(f"[ΕΠΙΤΥΧΙΑ] Το API απάντησε! Συνδεθήκατε ως: {name}")
                return True
            
            elif response.status_code == 401:
                print("[ΣΦΑΛΜΑ 401] Unauthorized. Το Bearer Token είναι άκυρο ή έληξε.")
            elif response.status_code == 403:
                print("[ΣΦΑΛΜΑ 403] Forbidden. Το token είναι σωστό, αλλά το Service Account δεν έχει τα απαραίτητα scopes.")
            else:
                print(f"[ΣΦΑΛΜΑ {response.status_code}] Απροσδόκητη απάντηση: {response.text}")
            
            return False
            
        except requests.exceptions.RequestException as e:
            print(f"[ΣΦΑΛΜΑ ΔΙΚΤΥΟΥ] Δεν ήταν δυνατή η επικοινωνία με τον server: {e}")
            return False
        
    def get_issues_chunked(self, jql_query: str, expand: str = "changelog", chunk_size: int = 50, requested_fields: str = "*all"):
        """
        Επιστρέφει τα issues από το Jira χρησιμοποιώντας Cursor-Based Pagination (nextPageToken).
        Από προεπιλογή (requested_fields="*all") φέρνει ΟΛΑ τα Standard και Custom Fields.
        """
        # Σιγουρέψου ότι το endpoint καταλήγει σε /search/jql 
        endpoint = f"{self.base_url}/rest/api/3/search/jql"
        page_token = ""
        total_fetched = 0

        print(f"\n[*] Εκκίνηση JQL Search: '{jql_query}'")

        while True:
            params = {
                "jql": jql_query,
                "maxResults": chunk_size,
                "expand": expand,
                "fields": requested_fields # Εδώ ζητάμε τα πάντα!
            }
            
            # Αν έχουμε token από την προηγούμενη σελίδα, το προσθέτουμε στο request
            if page_token:
                params["nextPageToken"] = page_token

            try:
                response = requests.get(endpoint, headers=self.headers, params=params, timeout=30)
                response.raise_for_status()
                data = response.json()
                
                issues_batch = data.get("issues", [])
                
                if not issues_batch:
                    print("[*] Τέλος δεδομένων (δεν βρέθηκαν άλλα issues).")
                    break

                total_fetched += len(issues_batch)
                print(f"--- Λήφθηκαν {total_fetched} tickets... ---")

                yield issues_batch

                # Διαβάζουμε το Token για την επόμενη σελίδα
                page_token = data.get("nextPageToken")
                is_last = data.get("isLast", True)

                # Αν το API μας πει ότι είναι η τελευταία σελίδα ή δεν μας δώσει token, σταματάμε!
                if not page_token or is_last:
                    print("[*] Λήφθηκε η τελευταία σελίδα.")
                    break

            except Exception as e:
                print(f"[ΣΦΑΛΜΑ API] Διακοπή: {e}")
                if response is not None:
                    print(response.text)
                raise
            
    def get_projects(self):
        """Φέρνει ΟΛΑ τα projects του Jira χρησιμοποιώντας Pagination."""
        endpoint = f"{self.base_url}/rest/api/3/project/search"
        all_projects = []
        start_at = 0
        
        print("\n[*] Λήψη Projects από το Jira API...")
        
        while True:
            params = {
                "startAt": start_at,
                "maxResults": 50 # Το Jira φέρνει μέχρι 50 ανά κλήση
            }
            
            response = requests.get(endpoint, headers=self.headers, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            batch = data.get("values", [])
            all_projects.extend(batch)
            
            # Αν το API μας πει ότι φτάσαμε στην τελευταία σελίδα, σταματάμε
            if data.get("isLast", True):
                break
                
            # Διαφορετικά, προχωράμε στην επόμενη "50άδα"
            start_at += 50
            
        print(f"[*] Βρέθηκαν συνολικά {len(all_projects)} Projects στο Jira.")
        return all_projects

    def get_users(self):
        """Φέρνει όλους τους ενεργούς (και ανενεργούς) χρήστες του Jira."""
        # Το Jira Cloud επιστρέφει users μέσω αυτού του endpoint (με μέγιστο όριο 1000 ανά κλήση)
        endpoint = f"{self.base_url}/rest/api/3/users/search"
        params = {"maxResults": 1000}
        response = requests.get(endpoint, headers=self.headers, params=params, timeout=30)
        response.raise_for_status()
        return response.json()

    def get_components(self, project_key: str):
        """Φέρνει τα components για ένα συγκεκριμένο Project (με βάση το Key του, π.χ. PYLCOM)."""
        endpoint = f"{self.base_url}/rest/api/3/project/{project_key}/components"
        response = requests.get(endpoint, headers=self.headers, timeout=30)
        response.raise_for_status()
        return response.json()
            
    def smoke_test_single_issue(self):
        client = JiraAPIClient()
        
        # JQL για το πιο πρόσφατο issue
        jql = "project = 'PYLCOM' order by created desc"
        
        # Επιλεγμένα πεδία για να μην φορτώνουμε άχρηστη πληροφορία
        # selected_fields = "summary,project,issuetype,priority,status,created,reporter,assignee" #---- Δε χρειάζονται. Η κλήση θα φέρει όλα τα πεδία που υπάρχουν σε ένα issue.
        
        print("[*] Εκτέλεση Smoke Test για 1 issue...")
        
        # Καλούμε τη μέθοδο με maxResults=1
        generator = client.get_issues_chunked(jql_query=jql, expand="changelog", chunk_size=1)
        
        try:
            first_chunk = next(generator)
            if first_chunk:
                issue = first_chunk[0]
                print(f"\n[ΕΠΙΤΥΧΙΑ] Λήφθηκε το Issue: {issue.get('key')}")
                print(f"Τίτλος: {issue.get('fields', {}).get('summary')}")
                
                # Έλεγχος αν ήρθε το changelog
                changelog = issue.get('changelog', {}).get('histories', [])
                print(f"Εγγραφές Ιστορικού (Audits): {len(changelog)}")
                
                # Εκτύπωση του JSON για μελέτη (προαιρετικά)
                import json
                print(json.dumps(issue, indent=2))
            else:
                print("[!] Δεν βρέθηκαν issues.")
        except StopIteration:
            print("[!] Το API δεν επέστρεψε δεδομένα.")

# Αυτό μας επιτρέπει να τρέξουμε το αρχείο απευθείας για γρήγορο test από το τερματικό
if __name__ == "__main__":
    client = JiraAPIClient()
    # client.test_connection()
    client.smoke_test_single_issue()