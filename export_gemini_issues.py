import pandas as pd
from src.api.gemini_client import GeminiAPIClient, GeminiSearchCriteria

def export_filtered_and_linked_issues_to_excel():
    client = GeminiAPIClient()
    
    # 1. Στήσιμο των κριτηρίων
    criteria = GeminiSearchCriteria(
        project_id="81", # Project SRV
        include_closed=True
    )
    
    print("Λήψη βασικών αιτημάτων...")
    base_issues = client.get_issues_advanced(criteria)
    print(f"Βρέθηκαν {len(base_issues)} βασικά αιτήματα.")
    
    # Εδώ θα μαζεύουμε όλα τα δεδομένα για το Excel
    export_data = []

    # 2. Επεξεργασία κάθε βασικού αιτήματος
    for issue in base_issues:
        issue_id = issue['Id']
        issue_key = issue.get('IssueKey')
        
        # Καταγραφή του βασικού (Parent) αιτήματος στο Excel
        export_data.append({
            "Main Issue ID": issue_id,
            "Main Issue Key": issue_key,
            "Main Title": issue.get('Title'),
            "Linked Issue ID": None,
            "Linked Project Code": None,
            "Linked Title": None,
            "Relationship": "Parent" # Απλά για να ξεχωρίζει
        })

        # --- 3. ΛΗΨΗ ΚΑΙ ΕΠΕΞΕΡΓΑΣΙΑ LINKS (Η λογική σου από .NET) ---
        links_data = client.get_issue_links(issue_id)
        
        # Λεξικό για να κάνουμε το Distinct (GroupBy ID -> First)
        unique_links = {}

        for link in links_data:
            # Διαβάζουμε τους κόμβους. Χρησιμοποιούμε .get() με κενό dict για ασφάλεια
            issue_node = link.get('Issue', {})
            other_issue_node = link.get('OtherIssue', {})
            
            target_id = None
            target_project_code = None
            target_title = None

            # Περίπτωση Α: Το Link ξεκινάει από εμάς
            if issue_node.get('Id') == issue_id:
                target_id = other_issue_node.get('Id')
                target_project_code = other_issue_node.get('ProjectCode')
                target_title = other_issue_node.get('Title')
            
            # Περίπτωση Β: Το Link καταλήγει σε εμάς
            elif other_issue_node.get('Id') == issue_id:
                target_id = issue_node.get('Id')
                target_project_code = issue_node.get('ProjectCode')
                target_title = issue_node.get('Title')
            else:
                # Safety Fallback
                continue

            # Προσθήκη στο Dictionary (αυτό αντικαθιστά το Distinct/GroupBy της C#)
            if target_id and target_id not in unique_links:
                unique_links[target_id] = {
                    "Id": target_id,
                    "ProjectCode": target_project_code,
                    "Title": target_title
                }

        # 4. Προσθήκη των Unique Links στα δεδομένα εξαγωγής
        for _, target in unique_links.items():
            export_data.append({
                "Main Issue ID": issue_id,
                "Main Issue Key": issue_key,
                "Main Title": issue.get('Title'),
                "Linked Issue ID": target["Id"],
                "Linked Project Code": target["ProjectCode"],
                "Linked Title": target["Title"],
                "Relationship": "Linked"
            })
            
    # 5. Εξαγωγή σε Excel
    if export_data:
        df = pd.DataFrame(export_data)
        df.to_excel("Gemini_Issues_With_Links.xlsx", index=False)
        print("Επιτυχία! Το Excel δημιουργήθηκε.")
    else:
        print("Δεν βρέθηκαν δεδομένα.")

if __name__ == "__main__":
    export_filtered_and_linked_issues_to_excel()