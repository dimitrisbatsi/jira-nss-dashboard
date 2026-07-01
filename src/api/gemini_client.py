import os
import requests
from typing import List, Dict, Any, Optional
from requests.auth import HTTPBasicAuth
from datetime import datetime, timezone
from dateutil.relativedelta import relativedelta
from dotenv import load_dotenv

from dataclasses import dataclass, field

# Φόρτωση του .env αρχείου για τα Gemini credentials
load_dotenv()
from typing import List, Dict, Optional


# Βοηθητική κλάση για χρήση Input Search Criteria για λήψη αιτημάτων Gemini
@dataclass
class GeminiSearchCriteria:
    project_id: str
    
    versions: Optional[List[str]] = None
    versions_not: bool = False
    
    components: Optional[List[str]] = None
    components_not: bool = False
    
    statuses: Optional[List[str]] = None
    statuses_not: bool = False
    
    resolutions: Optional[List[str]] = None
    resolutions_not: bool = False
    
    types: Optional[List[str]] = None
    types_not: bool = False
    
    resources: Optional[List[str]] = None
    resources_not: bool = False
    single_resource: bool = False
    
    reporter: Optional[List[str]] = None
    reporter_not: bool = False
    
    custom_fields: Optional[Dict[str, str]] = field(default_factory=dict)
    
    include_closed: bool = True
    max_items: int = 1000
    
    created_after: Optional[datetime] = None
    created_before: Optional[datetime] = None
    updated_after: Optional[datetime] = None
    updated_before: Optional[datetime] = None

class GeminiAPIClient:
    def __init__(self):
        # Διαβάζουμε τα credentials από το .env
        self.base_url = os.getenv("GEMINI_BASE_URL", "").rstrip("/")
        self.username = os.getenv("GEMINI_USERNAME")
        self.api_key = os.getenv("GEMINI_API_KEY")
        
        # Το Gemini API συνήθως δέχεται Basic Auth
        self.auth = HTTPBasicAuth(self.username, self.api_key)
        self.headers = {
            "Accept": "application/json",
            "Content-Type": "application/json"
        }

    def get_projects(self) -> List[Dict[str, Any]]:
        """Φέρνει όλα τα projects από το API του Gemini"""
        endpoint = f"{self.base_url}/api/projects"
        print(f"Κλήση στο API: GET {endpoint}")
        
        response = requests.get(endpoint, auth=self.auth, headers=self.headers)
        
        # Αν χτυπήσει λάθος (π.χ. 401 Unauthorized, 404 Not Found), πετάει exception
        response.raise_for_status() 
        
        return response.json()
    
    def get_users(self) -> List[Dict[str, Any]]:
        """Φέρνει όλους τους χρήστες από το API του Gemini"""
        endpoint = f"{self.base_url}/api/users"
        print(f"Κλήση στο API: GET {endpoint}")
        
        response = requests.get(endpoint, auth=self.auth, headers=self.headers)
        response.raise_for_status() 
        return response.json()
    
    def get_issues_filtered(self, project_id: int, revised_after: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """Φέρνει Issues για ένα Project, προαιρετικά φιλτραρισμένα από μια ημερομηνία και μετά (Incremental)."""
        endpoint = f"{self.base_url}/api/items/filtered"
        
        # Χτίζουμε το JSON body όπως το IssuesFilter της C#
        payload = {
            "Projects": str(project_id),
            "IncludeClosed": True,  # Θέλουμε να ενημερώνουμε και τα κλειστά (π.χ. αν άλλαξε το resolution)
            "MaxItemsToReturn": 999999 # Ζητάμε όσα περισσότερα γίνεται
        }
        
        # Αν έχουμε ημερομηνία, προσθέτουμε το RevisedAfter (Incremental Sync!)
        if revised_after:
            # Το Gemini περιμένει YYYY-MM-DD
            payload["RevisedAfter"] = revised_after.strftime("%Y-%m-%d")
            print(f"Κλήση στο API: POST {endpoint} (Project: {project_id}, RevisedAfter: {payload['RevisedAfter']})")
        else:
            print(f"Κλήση στο API: POST {endpoint} (Project: {project_id}, Full Sync)")

        response = requests.post(endpoint, json=payload, auth=self.auth, headers=self.headers)
        response.raise_for_status()
        
        return response.json()
    
    def get_issues_time_chunked(self, project_id: int, revised_after: datetime):
        """Φέρνει Issues σε μικρά χρονικά πακέτα (μήνας-μήνας) για να αποφύγει Timeouts."""
        endpoint = f"{self.base_url}/api/items/filtered"
        
        # Ημερομηνία λήξης = Σήμερα
        end_date = datetime.now(timezone.utc)
        
        # Ορίζουμε το "παράθυρο" του χρόνου που θα τραβάμε (π.χ. 1 μήνας)
        current_start = revised_after
        
        while current_start < end_date:
            # Προσθέτουμε 1 μήνα για να βρούμε το τέλος του παραθύρου
            current_end = current_start + relativedelta(months=1)
            
            # Αν περάσαμε το σήμερα, κόβουμε το παράθυρο στο σήμερα
            if current_end > end_date:
                current_end = end_date
                
            payload = {
                "Projects": str(project_id),
                "IncludeClosed": True,
                "MaxItemsToReturn": 999999, # Ζητάμε όσα περισσότερα, αφού το παράθυρο είναι μικρό
                "RevisedAfter": current_start.strftime("%Y-%m-%d"),
                "RevisedBefore": current_end.strftime("%Y-%m-%d")
            }
            
            print(f"    [API] Λήψη παραθύρου: {payload['RevisedAfter']} ΕΩΣ {payload['RevisedBefore']}...")
            
            response = requests.post(endpoint, json=payload, auth=self.auth, headers=self.headers)
            response.raise_for_status()
            
            data = response.json()
            
            # Επιστρέφουμε τα data του συγκεκριμένου μήνα στο κύριο loop!
            if data:
                yield data
                
            # Προχωράμε τον χρόνο (Η νέα αρχή είναι το προηγούμενο τέλος)
            current_start = current_end

    def get_components(self, project_id: int) -> List[Dict[str, Any]]:
        """Φέρνει όλα τα Components για ένα συγκεκριμένο Project."""
        endpoint = f"{self.base_url}/api/projects/{project_id}/components"
        print(f"    [API] Λήψη Components για Project {project_id}...")
        
        response = requests.get(endpoint, auth=self.auth, headers=self.headers)
        response.raise_for_status()
        
        return response.json()
    
    def get_issue_history(self, issue_id: int) -> List[Dict[str, Any]]:
        """Φέρνει το ιστορικό αλλαγών (Audits) για ένα συγκεκριμένο Issue."""
        endpoint = f"{self.base_url}/api/items/{issue_id}/history"
        
        response = requests.get(endpoint, auth=self.auth, headers=self.headers)
        
        # Αν επιστρέψει 404 ή κάτι άλλο, απλά επιστρέφουμε κενή λίστα για να μην σκάσει όλο το pipeline
        if response.status_code != 200:
            return []
            
        return response.json()

    
    # Βοηθητικές μέθοδοι για εξαγωγή συγκεκριμένων δεδομένων σε Excel
    def get_issues_advanced(self, criteria: GeminiSearchCriteria) -> List[Dict[str, Any]]:
        """Φέρνει Issues με βάση το προηγμένο Search Criteria."""
        endpoint = f"{self.base_url}/api/items/filtered"
        
        payload = {
            "Projects": criteria.project_id,
            "IncludeClosed": criteria.include_closed,
            "MaxItemsToReturn": criteria.max_items
        }

        # --- Προσθήκη των Φίλτρων και των "NOT" Flags ---
        if criteria.statuses:
            payload["Statuses"] = "|".join(criteria.statuses)
            if criteria.statuses_not: payload["StatusesNot"] = True
            
        if criteria.types:
            payload["Types"] = "|".join(criteria.types)
            if criteria.types_not: payload["TypesNot"] = True
            
        if criteria.components:
            payload["Components"] = "|".join(criteria.components)
            if criteria.components_not: payload["ComponentsNot"] = True
            
        if criteria.versions:
            payload["Versions"] = "|".join(criteria.versions)
            if criteria.versions_not: payload["VersionsNot"] = True
            
        if criteria.resolutions:
            payload["Resolutions"] = "|".join(criteria.resolutions)
            if criteria.resolutions_not: payload["ResolutionsNot"] = True
            
        if criteria.resources:
            payload["Resources"] = "|".join(criteria.resources)
            if criteria.resources_not: payload["ResourcesNot"] = True
            if criteria.single_resource: payload["SingleResource"] = True
            
        if criteria.reporter:
            payload["Reporter"] = "|".join(criteria.reporter)
            if criteria.reporter_not: payload["ReporterNot"] = True

        if criteria.created_after:
            payload["CreatedAfter"] = criteria.created_after.strftime("%Y-%m-%d")
        if criteria.created_before:
            payload["CreatedBefore"] = criteria.created_before.strftime("%Y-%m-%d")
        if criteria.updated_after:
            payload["RevisedAfter"] = criteria.updated_after.strftime("%Y-%m-%d")
        if criteria.updated_before:
            payload["RevisedBefore"] = criteria.updated_before.strftime("%Y-%m-%d")

        if criteria.custom_fields:
            payload["CustomFields"] = criteria.custom_fields

        print(f"Κλήση Advanced API: POST {endpoint}")
        response = requests.post(endpoint, json=payload, auth=self.auth, headers=self.headers)
        response.raise_for_status()
        
        return response.json()

    def get_single_issue(self, issue_id: int) -> Optional[Dict[str, Any]]:
        """Φέρνει ένα μεμονωμένο Issue από το ID του."""
        endpoint = f"{self.base_url}/api/items/{issue_id}"
        response = requests.get(endpoint, auth=self.auth, headers=self.headers)
        
        if response.status_code == 200:
            return response.json()
        return None

    def get_issue_links(self, issue_id: int) -> List[Dict[str, Any]]:
        """Φέρνει τα links ενός issue."""
        endpoint = f"{self.base_url}/api/items/{issue_id}/links"
        try:
            response = requests.get(endpoint, auth=self.auth, headers=self.headers)
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            print(f"Error fetching links for Gemini issue {issue_id}: {e}")
        return []

    def get_custom_fields(self) -> List[Dict[str, Any]]:
        """Φέρνει όλους τους ορισμούς custom fields από το Gemini."""
        endpoint = f"{self.base_url}/api/customfields"
        response = requests.get(endpoint, auth=self.auth, headers=self.headers)
        response.raise_for_status()
        return response.json()

    def get_custom_field(self, cf_id: int) -> Dict[str, Any]:
        """Φέρνει τις λεπτομέρειες ενός συγκεκριμένου custom field."""
        endpoint = f"{self.base_url}/api/customfields/{cf_id}"
        response = requests.get(endpoint, auth=self.auth, headers=self.headers)
        response.raise_for_status()
        return response.json()

    def update_issue_jira_key(self, issue_id: int, project_id: int, custom_field_id: int, jira_key: str) -> bool:
        """Ενημερώνει το custom field JiraKey του Gemini με το κλειδί του Jira."""
        endpoint = f"{self.base_url}/api/items/{issue_id}/customfield/data"
        payload = {
            "CustomFieldId": custom_field_id,
            "Data": jira_key,
            "IssueId": issue_id,
            "ProjectId": project_id,
            "UserId": 5031  # static user id used in C#
        }
        try:
            response = requests.put(endpoint, json=payload, auth=self.auth, headers=self.headers)
            if response.status_code in [200, 201, 204]:
                return True
            print(f"Failed to update JiraKey custom field: {response.status_code} - {response.text}")
        except Exception as e:
            print(f"Error updating JiraKey in Gemini issue {issue_id}: {e}")
        return False

    def get_issue_time_entries(self, issue_id: int) -> List[Dict[str, Any]]:
        """Φέρνει τις καταγραφές χρόνου (time entries) ενός issue."""
        endpoint = f"{self.base_url}/api/items/{issue_id}/time"
        try:
            response = requests.get(endpoint, auth=self.auth, headers=self.headers)
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            print(f"Error fetching time entries for Gemini issue {issue_id}: {e}")
        return []
