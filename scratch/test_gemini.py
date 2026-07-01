import os
from dotenv import load_dotenv
from src.api.gemini_client import GeminiAPIClient

load_dotenv()

client = GeminiAPIClient()
try:
    # 1. Test connection and get projects
    projects = client.get_projects()
    print(f"Projects fetched successfully! Total: {len(projects)}")
    
    # 2. Get users and search for apiUser
    users = client.get_users()
    print(f"Users fetched successfully! Total: {len(users)}")
    
    # Let's test updating custom field for issue 418609
    issue_id = 418609
    issue = client.get_single_issue(issue_id)
    if not issue:
        print(f"Issue {issue_id} not found.")
    else:
        print("Issue flat keys:", list(issue.keys()))
        entity = issue.get("Entity", issue.get("BaseEntity", {}))
        print("Entity keys:", list(entity.keys()))
        print("Project field value:", issue.get("Project") or entity.get("Project"))
        
        # find custom field JiraKey
        cf_id = None
        project_id = issue.get("ProjectId") or entity.get("ProjectId") or issue.get("Project", {}).get("Id") or entity.get("Project", {}).get("Id")
        for cf in issue.get("CustomFields", []):
            if cf.get("Name", "").lower() == "jirakey":
                cf_id = cf.get("CustomFieldId") or cf.get("BaseEntity", {}).get("CustomFieldId")
                break


                
        if not cf_id:
            print("JiraKey custom field not found on issue.")
        else:
            print(f"Found JiraKey CF ID: {cf_id}, Project ID: {project_id}")
            payload_camel = {
                "customFieldId": int(cf_id),
                "data": "PYLMIG-1062",
                "issueId": issue_id,
                "projectId": int(project_id),
                "userId": 5031
            }
            payload_pascal = {
                "CustomFieldId": int(cf_id),
                "Data": "PYLMIG-1062",
                "IssueId": issue_id,
                "ProjectId": int(project_id),
                "UserId": 5031
            }
            
            import requests
            
            # Let's test the intercepted PUT /api/items/{issue_id}/customfield/data endpoint
            url = f"{client.base_url}/api/items/{issue_id}/customfield/data"
            print(f"\nTrying PUT {url} with PascalCase payload...")
            try:
                r = requests.put(url, json=payload_pascal, auth=client.auth, headers=client.headers)
                print(f"  Response ({r.status_code}): {r.text[:300]}")
            except Exception as e:
                print(f"  Failed: {e}")







except Exception as e:
    print(f"Error during test: {e}")
