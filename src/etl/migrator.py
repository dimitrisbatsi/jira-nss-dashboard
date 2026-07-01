import re
import html
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

# --- Configuration & Mappings from C# MigrationManager ---

SUPPORT_PROJECTS = {"SHERC", "SGLX"}
DEV_PROJECTS = {"DHERC", "DGLX", "CUSTDGLX", "SMARTD"}
PROJECT_SRV = "SRV"

JIRA_TYPE_SERVICES = "Services (Αίτημα Υπηρεσιών)"
JIRA_TYPE_PREPROD = "Pre-Production"
JIRA_TYPE_PROD = "Production"

_subCategoryMapping = {
    # SRV Types
    "Incident (Περιστατικό/Αίτημα)": "Request for Information (Αίτημα Πληροφόρησης)",
    "Service Request (Αίτημα Υπηρεσιών)": "Service Request (Αίτημα Υπηρεσιών)",
    "Internal Request": "Internal Request (Εσωτερικό Αίτημα)",
    "Custom Request (Αίτημα Custom Λύσης)": "Custom Request (Αίτημα Custom Λύσης)",
    "Request for Information": "Request for Information (Αίτημα Πληροφόρησης)",
    "Request for Prototype (Αίτημα Βελτίωσης Πρότυπης)": "Request for Prototype (Αίτημα Βελτίωσης Πρότυπης)",
    "Request for Solution Design (Αίτημα Σχεδίασης Λύσης)": "Request for Solution Design (Αίτημα Σχεδίασης Λύσης)",
    "Bug (Σφάλμα)": "Bug (Σφάλμα)",
    "Disruption (Ανακόλουθη Λειτουργία)": "Disruption (Ανακόλουθη Λειτουργία)",
    "Enhancement (Αίτημα Βελτίωσης)": "Enhancement (Βελτίωση)",
    "Task": "Task (Εργασία)",
    "Presales (Παρουσίαση Πώλησης)": "Presales (Παρουσίαση Πώλησης)",
    "Training": "Training (Εκπαίδευση)",
    "Testing": "Testing (Δοκιμή)",
    "Azure/HW Failure": "Request for Information (Αίτημα Πληροφόρησης)",
    "Complaint": "Complaint (Παράπονο)",
    "Research": "Research (Έρευνα)",
    "Old Incidents": "Request for Information (Αίτημα Πληροφόρησης)",
    # SHERC Types
    "Customer Request": "Enhancement (Βελτίωση)",
    "Dealer Request": "Enhancement (Βελτίωση)",
    "Support Request": "Enhancement (Βελτίωση)",
    "Εργασία": "Task (Εργασία)",
    "Έρευνα": "Research (Έρευνα)",
    # DHERC Types
    "Bug": "Bug (Σφάλμα)",
    "Βελτίωση": "Enhancement (Βελτίωση)",
    "Νέα Δυνατότητα": "New Feature (Νέα Δυνατότητα)",
    "Ενέργεια": "Task (Εργασία)",
    "Objective": "Objective (Στόχος)",
    "Έλεγχος Ποιότητας": "Quality Check (Έλεγχος Ποιότητας)",
    "Εκκρεμότητα": "Task (Εργασία)",
    "Παρακολούθηση έργου": "Task (Εργασία)",
    "Σημείωση": "Task (Εργασία)",
    "Παραμετροποίηση": "Configuration (Παραμετροποίηση)",
    "Administrative": "Task (Εργασία)"
}

_severityMapping = {
    "High": "High",
    "Normal": "Medium",
    "Low": "Low"
}

_priorityMapping = {
    "Show Stopper": "Highest",
    "Major": "High",
    "Minor": "Medium",
    "Low": "Low"
}

# --- Helpers ---

def convert_html_to_text(html_content: str) -> str:
    """Μετατρέπει το HTML κείμενο σε καθαρό κείμενο όπως το HtmlToTextHelper του C#."""
    if not html_content:
        return ""
    # Αντικατάσταση block tags με αλλαγή γραμμής
    s = re.sub(r'<(div|p|br|li|h[1-6]|tr)[^>]*>', '\n', html_content)
    # Αφαίρεση όλων των υπόλοιπων tags
    s = re.sub(r'<[^>]+>', '', s)
    # Decode HTML entities
    s = html.unescape(s)
    # Normalize spaces/newlines
    lines = [line.strip() for line in s.split('\n')]
    return '\n'.join([line for line in lines if line])

def create_jira_doc_payload(text: str) -> dict:
    """Παράγει το ADF payload για κείμενο (Description/Details)."""
    return {
        "type": "doc",
        "version": 1,
        "content": [
            {
                "type": "paragraph",
                "content": [
                    {
                        "type": "text",
                        "text": text or ""
                    }
                ]
            }
        ]
    }

class GeminiLookupCache:
    """Φορτώνει και κρατάει σε cache τα Lookup Custom Fields από το Gemini."""
    def __init__(self, client):
        self.client = client
        self.cache = {}
        self.user_id_to_email = {}
        self.fullname_to_email = {}

    def preload(self):
        try:
            definitions = self.client.get_custom_fields()
            target_fields = {"partnername", "customername", "pylonflexdirect"}
            for cf_def in definitions:
                entity = cf_def.get("Entity", {})
                name = entity.get("Name", "")
                if name.lower() in target_fields:
                    cf_id = entity.get("CustomFieldId") or entity.get("Id")
                    lookup_list = entity.get("LookupData")
                    
                    if not lookup_list and cf_id:
                          cf_detail = self.client.get_custom_field(cf_id)
                          lookup_list = cf_detail.get("Entity", {}).get("LookupData", [])
                    
                    if lookup_list:
                        dict_data = {}
                        for item in lookup_list:
                            key = str(item.get("Key", "")).strip()
                            val = str(item.get("Value", "")).strip()
                            if key:
                                dict_data[key] = val or key
                        self.cache[name.lower()] = dict_data
        except Exception as e:
            print(f"Error preloading Gemini lookup cache: {e}")

        try:
            # Preload users mapping: ID -> Email, Fullname -> Email
            users = self.client.get_users()
            for u in users:
                entity = u.get("BaseEntity", u.get("Entity", {}))
                u_id = entity.get("Id")
                email = entity.get("Email")
                fullname = entity.get("Fullname")
                
                if email:
                    if u_id:
                        self.user_id_to_email[u_id] = email.strip()
                    if fullname:
                        self.fullname_to_email[fullname.strip().lower()] = email.strip()
        except Exception as e:
            print(f"Error preloading Gemini users mapping: {e}")

    def get_label(self, field_name: str, key: str) -> str:
        if not key:
            return ""
        field_cache = self.cache.get(field_name.lower())
        if field_cache:
            return field_cache.get(str(key).strip(), str(key))
        return str(key)

# --- Field Mapping ---

def resolve_resources_to_jira_accounts(resources: list, lookup_cache: GeminiLookupCache, jira_client: Any) -> list:
    """Μετατρέπει τη λίστα Resources του Gemini σε λίστα με Jira Account IDs."""
    jira_accounts = []
    for r in resources:
        entity = r.get("Entity", r.get("BaseEntity", {}))
        u_id = entity.get("Id") or entity.get("UserId")
        fullname = entity.get("Fullname", "")
        
        email = None
        # 1. Lookup by User ID
        if u_id and hasattr(lookup_cache, "user_id_to_email"):
            email = lookup_cache.user_id_to_email.get(u_id)
            
        # 2. Fallback to lookup by Fullname
        if not email and fullname and hasattr(lookup_cache, "fullname_to_email"):
            email = lookup_cache.fullname_to_email.get(fullname.strip().lower())
            
        # 3. Fallback to direct Email field if present
        if not email:
            email = entity.get("Email")
            
        if email:
            acc_id = jira_client.get_cached_account_id(email)
            if acc_id:
                jira_accounts.append(acc_id)
                
    return jira_accounts

def map_gemini_issue_to_jira_fields(raw_issue: dict, project_key: str, lookup_cache: GeminiLookupCache, jira_client: Any) -> dict:
    """Μετατρέπει το Gemini issue JSON σε Jira fields dictionary (MapToJiraDto)."""
    entity = raw_issue.get("Entity", raw_issue.get("BaseEntity", raw_issue))
    project_code = raw_issue.get("ProjectCode") or ""
    issue_id = entity.get("Id")
    
    title = entity.get("Title", "")
    description = convert_html_to_text(entity.get("Description", ""))
    status = raw_issue.get("Status", "")
    resolution = raw_issue.get("Resolution", "")
    issue_type = raw_issue.get("Type", "")
    severity = raw_issue.get("Severity", "")
    priority = raw_issue.get("Priority", "")
    reporter = raw_issue.get("Reporter", "")
    assignees = ", ".join([r.get("Entity", {}).get("Fullname", "") for r in raw_issue.get("Resources", [])])
    components = raw_issue.get("ComponentNames", "")
    fixed_in_version = raw_issue.get("FixedInVersion", "")
    has_attachments = bool(raw_issue.get("Attachments"))
    
    # Custom fields mapping
    partner_name = ""
    customer_name_lsp = ""
    customer = ""
    serial_number = ""
    pylon_pack = ""
    flex_direct = ""
    billable_hours = ""
    approved_hours = ""
    
    def get_cf_raw(field_name):
        for cf in raw_issue.get("CustomFields", []):
            name = cf.get("Name") or cf.get("Title") or ""
            if name.lower() == field_name.lower():
                formatted = cf.get("FormattedData")
                if formatted:
                    return formatted.strip()
                base_entity = cf.get("BaseEntity", {})
                if base_entity:
                    return str(base_entity.get("Data") or "").strip()
        return ""

    if project_code == "SRV":
        partner_name = lookup_cache.get_label("PartnerName", get_cf_raw("PartnerName"))
        customer_name_lsp = lookup_cache.get_label("CustomerName", get_cf_raw("CustomerName"))
        customer = get_cf_raw("Επωνυμία Πελάτη")
        serial_number = get_cf_raw("SerialNumber")
        pylon_pack = get_cf_raw("PYLON Pack")
        flex_direct = lookup_cache.get_label("PylonFlexDirect", get_cf_raw("PylonFlexDirect"))
        billable_hours = get_cf_raw("Requested Billable Time")
        approved_hours = get_cf_raw("Approved Billable Time")
    elif project_code in SUPPORT_PROJECTS:
        partner_name = lookup_cache.get_label("PartnerName", get_cf_raw("Επωνυμία Dealer"))
        customer = get_cf_raw("Επωνυμία Πελάτη")
        pylon_pack = get_cf_raw("PYLON Pack")
    elif project_code in DEV_PROJECTS:
        partner_name = lookup_cache.get_label("PartnerName", get_cf_raw("Επωνυμία Dealer"))
        customer = get_cf_raw("Επωνυμία Πελάτη")
        pylon_pack = get_cf_raw("PYLON Pack")
        
    sub_category = _subCategoryMapping.get(issue_type, issue_type)
    
    # Severity & Priority matching C# MapToJiraDto logic
    jira_priority = ""
    jira_severity = ""
    jira_partner_tier = ""
    
    if project_code == "SRV":
        jira_priority = severity
        jira_partner_tier = priority
    else:
        jira_priority = _priorityMapping.get(priority, "Medium")
        jira_severity = _severityMapping.get(severity, "Medium")
        
    gemini_key = f"{project_code}-{issue_id}"
    
    fields = {
        "project": {"key": project_key},
        "summary": title,
        "description": create_jira_doc_payload(description)
    }
    
    if jira_priority:
        fields["priority"] = {"name": jira_priority}
    if jira_severity:
        fields["customfield_10194"] = {"value": jira_severity}  # Severity
    if jira_partner_tier:
        fields["customfield_11322"] = {"value": jira_partner_tier}  # Partner Tier
        
    fields["labels"] = ["FromGemini", f"Project-{project_code.replace(' ', '-')}"]
    
    if sub_category:
        fields["customfield_10092"] = {"value": sub_category}  # Sub Category
        
    fields["customfield_11962"] = gemini_key  # Gemini ID
    fields["customfield_11355"] = f"https://gemini.epsilonnet.gr/workspace/0/item/{issue_id}"  # Gemini URL
    
    if serial_number:
        fields["customfield_10124"] = serial_number
    if fixed_in_version:
        fields["customfield_11182"] = fixed_in_version
    if customer:
        fields["customfield_11250"] = customer
        
    # Gemini Details field payload construction
    gemini_details = f"--- Migration Info ---\nOriginal Gemini Status: {status}"
    if reporter:
        gemini_details += f"\n\nOriginal ReportedBy: {reporter}"
    if assignees:
        gemini_details += f"\n\nOriginal Assignees: {assignees}"
    if resolution:
        gemini_details += f"\n\nOriginal Resolution: {resolution}"
    if partner_name:
        gemini_details += f"\n\nOriginal Partner Name: {partner_name}"
    if customer_name_lsp:
        gemini_details += f"\n\nOriginal Customer Name LSP: {customer_name_lsp}"
    if flex_direct:
        gemini_details += f"\n\nOriginal Flex Direct Customer: {flex_direct}"
    if pylon_pack:
        gemini_details += f"\n\nOriginal PYLON Pack: {pylon_pack}"
    if components:
        gemini_details += f"\n\nOriginal Components: {components}"
    gemini_details += f"\n\nHas Attachments? -> {has_attachments}"
    
    fields["customfield_11692"] = create_jira_doc_payload(gemini_details)
    
    try:
        if billable_hours:
            fields["customfield_11389"] = float(billable_hours)
    except:
        pass
    try:
        if approved_hours:
            fields["customfield_11390"] = float(approved_hours)
    except:
        pass
        
    # Resolve assignees
    jira_accounts = []
    raw_resources = raw_issue.get("Resources", [])
    if raw_resources:
        jira_accounts = resolve_resources_to_jira_accounts(raw_resources, lookup_cache, jira_client)
        
    if jira_accounts:
        fields["assignee"] = {"id": jira_accounts[0]}
        if len(jira_accounts) > 1:
            fields["customfield_10860"] = [{"id": acc_id} for acc_id in jira_accounts[1:]]
            
    return fields

def find_jira_key_cf_id(raw_issue: dict) -> Optional[int]:
    """Επιστρέφει το ID του custom field 'JiraKey' στο Gemini."""
    for cf in raw_issue.get("CustomFields", []):
        if cf.get("Name", "").lower() == "jirakey":
            return cf.get("CustomFieldId") or cf.get("BaseEntity", {}).get("CustomFieldId")
    return None

# --- Migration Strategies ---

def migrate_comments(jira_key: str, raw_issue: dict, jira_client: Any, logger_fn: Any):
    comments = raw_issue.get("Comments", [])
    if not comments:
        return
    
    # Sort comments by creation date ascending
    sorted_comments = sorted(
        comments,
        key=lambda c: c.get("Entity", {}).get("Created", "") or c.get("Created", "")
    )
    
    for c in sorted_comments:
        entity = c.get("Entity", c.get("BaseEntity", c))
        author = c.get("Fullname") or c.get("Creator") or entity.get("Fullname", "Unknown")
        body = convert_html_to_text(entity.get("Comment", ""))
        created = entity.get("Created", "")
        
        # Max ADF length safety limit (28000 characters)
        if len(body) > 28000:
            body = body[:28000] + "\n\n... [TRUNCATED]\n⚠️ Το σχόλιο ξεπερνάει το όριο χαρακτήρων του Jira."
            
        success = jira_client.add_comment(jira_key, body, author, created)
        if success:
            logger_fn(f"   └─ Comment by {author} added to {jira_key}.")
        else:
            logger_fn(f"   ⚠️ Failed to add comment by {author} to {jira_key}.")

def write_jira_key_back_to_gemini(issue_id: int, project_id: int, jira_key: str, raw_issue: dict, gemini_client: Any, logger_fn: Any):
    cf_id = find_jira_key_cf_id(raw_issue)
    if not cf_id:
        logger_fn(f"   ⚠️ No Custom Field 'JiraKey' found in Gemini issue {issue_id}.")
        return False
    success = gemini_client.update_issue_jira_key(issue_id, project_id, cf_id, jira_key)
    if success:
        logger_fn(f"   ✅ Updated Gemini issue {issue_id} with Jira Key: {jira_key}.")
        return True
    else:
        logger_fn(f"   ⚠️ Failed to write Jira Key {jira_key} back to Gemini issue {issue_id}.")
        return False

# 1. Standard Strategy
def migrate_standard_strategy(raw_issue: dict, project_key: str, gemini_client: Any, jira_client: Any, lookup_cache: GeminiLookupCache, logger_fn: Any) -> str:
    entity = raw_issue.get("Entity", raw_issue.get("BaseEntity", raw_issue))
    issue_id = entity.get("Id")
    project_id = entity.get("ProjectId")
    project_code = raw_issue.get("ProjectCode") or ""
    
    logger_fn(f"🚀 [STRATEGY: STANDARD] Migrating {project_code}-{issue_id} as standalone issue.")
    
    fields = map_gemini_issue_to_jira_fields(raw_issue, project_key, lookup_cache, jira_client)
    jira_key = jira_client.create_single_issue(fields, raw_issue.get("Type", "Task"))
    
    migrate_comments(jira_key, raw_issue, jira_client, logger_fn)
    write_jira_key_back_to_gemini(issue_id, project_id, jira_key, raw_issue, gemini_client, logger_fn)
    
    return jira_key

# 2. SRV Tree Strategy
def migrate_srv_tree_strategy(raw_issue: dict, project_key: str, gemini_client: Any, jira_client: Any, lookup_cache: GeminiLookupCache, logger_fn: Any) -> str:
    entity = raw_issue.get("Entity", raw_issue.get("BaseEntity", raw_issue))
    issue_id = entity.get("Id")
    project_id = entity.get("ProjectId")
    project_code = raw_issue.get("ProjectCode") or ""
    
    logger_fn(f"🚀 [STRATEGY: SRV TREE] Processing Chain for SRV-{issue_id}...")
    
    # STEP 1: Create Epic
    epic_fields = map_gemini_issue_to_jira_fields(raw_issue, project_key, lookup_cache, jira_client)
    epic_key = jira_client.create_epic(epic_fields)
    logger_fn(f"   ✅ Created Epic: {epic_key}")
    
    # STEP 2: Create Child Services Issue under Epic
    services_fields = map_gemini_issue_to_jira_fields(raw_issue, project_key, lookup_cache, jira_client)
    services_key = jira_client.create_child_issue(services_fields, epic_key, JIRA_TYPE_SERVICES)
    logger_fn(f"   └─ Created 'Services' Child: {services_key}")
    
    # Transition Epic to In Progress since it now has a child
    jira_client.transition_issue(epic_key, "In Progress")
    
    # Migrate comments & update Gemini status for the SRV Parent issue onto the Services Child issue
    migrate_comments(services_key, raw_issue, jira_client, logger_fn)
    write_jira_key_back_to_gemini(issue_id, project_id, services_key, raw_issue, gemini_client, logger_fn)
    
    # STEP 3: Check linked Support/Dev issues (SHERC & DHERC)
    links = gemini_client.get_issue_links(issue_id)
    
    # Find SHERC project links (Support Projects)
    sherc_link = None
    for link in links:
        other_proj = link.get("OtherIssue", {}).get("ProjectCode") or link.get("Issue", {}).get("ProjectCode") or ""
        other_id = link.get("OtherIssue", {}).get("Id") or link.get("Issue", {}).get("Id")
        if other_id != issue_id and other_proj in SUPPORT_PROJECTS:
            sherc_link = link
            break
            
    if sherc_link:
        other_id = sherc_link.get("OtherIssue", {}).get("Id") or sherc_link.get("Issue", {}).get("Id")
        raw_sherc = gemini_client.get_single_issue(other_id)
        if raw_sherc:
            sherc_entity = raw_sherc.get("Entity", raw_sherc.get("BaseEntity", raw_sherc))
            sherc_proj_id = sherc_entity.get("ProjectId")
            
            preprod_fields = map_gemini_issue_to_jira_fields(raw_sherc, project_key, lookup_cache, jira_client)
            preprod_key = jira_client.create_child_issue(preprod_fields, epic_key, JIRA_TYPE_PREPROD)
            logger_fn(f"   └─ Created 'Pre-Production' Child: {preprod_key} (from SHERC-{other_id})")
            
            migrate_comments(preprod_key, raw_sherc, jira_client, logger_fn)
            write_jira_key_back_to_gemini(other_id, sherc_proj_id, preprod_key, raw_sherc, gemini_client, logger_fn)
            
            # STEP 4: Check links of SHERC for DHERC (Dev Projects)
            sherc_links = gemini_client.get_issue_links(other_id)
            dherc_link = None
            for link in sherc_links:
                other_proj = link.get("OtherIssue", {}).get("ProjectCode") or link.get("Issue", {}).get("ProjectCode") or ""
                other_dev_id = link.get("OtherIssue", {}).get("Id") or link.get("Issue", {}).get("Id")
                if other_dev_id != other_id and other_proj in DEV_PROJECTS:
                    dherc_link = link
                    break
                    
            if dherc_link:
                other_dev_id = dherc_link.get("OtherIssue", {}).get("Id") or dherc_link.get("Issue", {}).get("Id")
                raw_dherc = gemini_client.get_single_issue(other_dev_id)
                if raw_dherc:
                    dherc_entity = raw_dherc.get("Entity", raw_dherc.get("BaseEntity", raw_dherc))
                    dherc_proj_id = dherc_entity.get("ProjectId")
                    
                    prod_fields = map_gemini_issue_to_jira_fields(raw_dherc, project_key, lookup_cache, jira_client)
                    prod_key = jira_client.create_child_issue(prod_fields, epic_key, JIRA_TYPE_PROD)
                    logger_fn(f"      └─ Created 'Production' Child: {prod_key} (from DHERC-{other_dev_id})")
                    
                    migrate_comments(prod_key, raw_dherc, jira_client, logger_fn)
                    write_jira_key_back_to_gemini(other_dev_id, dherc_proj_id, prod_key, raw_dherc, gemini_client, logger_fn)
                    
    logger_fn(f"🏁 [DONE] Chain migration completed for SRV-{issue_id}.")
    return epic_key

# 3. Support Orphan Strategy
def migrate_support_orphan_strategy(raw_issue: dict, project_key: str, gemini_client: Any, jira_client: Any, lookup_cache: GeminiLookupCache, logger_fn: Any, unfiltered: bool) -> str:
    entity = raw_issue.get("Entity", raw_issue.get("BaseEntity", raw_issue))
    issue_id = entity.get("Id")
    project_id = entity.get("ProjectId")
    project_code = raw_issue.get("ProjectCode") or ""
    
    if not unfiltered:
        logger_fn(f"Checking if support issue {project_code}-{issue_id} is orphan...")
        links = gemini_client.get_issue_links(issue_id)
        belongs_to_chain = False
        for link in links:
            other_proj = link.get("OtherIssue", {}).get("ProjectCode") or link.get("Issue", {}).get("ProjectCode") or ""
            other_id = link.get("OtherIssue", {}).get("Id") or link.get("Issue", {}).get("Id")
            if other_id != issue_id and other_proj != project_code:
                belongs_to_chain = True
                logger_fn(f"⏭️ SKIP: {project_code}-{issue_id} is NOT orphan. Linked to {other_proj}-{other_id}.")
                return ""
                
    logger_fn(f"🚀 [STRATEGY: SUPPORT EPIC+CHILD] Migrating orphan support issue {project_code}-{issue_id}.")
    
    # Create Epic Container
    epic_fields = map_gemini_issue_to_jira_fields(raw_issue, project_key, lookup_cache, jira_client)
    epic_fields["summary"] = f"[{project_code}-{issue_id}] {epic_fields['summary']}"
    if not unfiltered:
        epic_fields["labels"].append("Migrated_Escalation")
    else:
        epic_fields["labels"].append("Raw_Issue")
        
    epic_key = jira_client.create_epic(epic_fields)
    logger_fn(f"   ✅ Created Epic Container: {epic_key}")
    
    # Create Child preprod ticket under Epic
    child_fields = map_gemini_issue_to_jira_fields(raw_issue, project_key, lookup_cache, jira_client)
    child_fields["summary"] = f"[{project_code}-{issue_id}] {child_fields['summary']}"
    child_key = jira_client.create_child_issue(child_fields, epic_key, JIRA_TYPE_PREPROD)
    logger_fn(f"   └─ Created Pre-Production Child: {child_key}")
    
    # Transition Epic to In Progress since it has a child
    jira_client.transition_issue(epic_key, "In Progress")
    
    migrate_comments(child_key, raw_issue, jira_client, logger_fn)
    write_jira_key_back_to_gemini(issue_id, project_id, child_key, raw_issue, gemini_client, logger_fn)
    
    return child_key

# 4. Dev Orphan Strategy
def migrate_dev_orphan_strategy(raw_issue: dict, project_key: str, gemini_client: Any, jira_client: Any, lookup_cache: GeminiLookupCache, logger_fn: Any, unfiltered: bool) -> str:
    entity = raw_issue.get("Entity", raw_issue.get("BaseEntity", raw_issue))
    issue_id = entity.get("Id")
    project_id = entity.get("ProjectId")
    project_code = raw_issue.get("ProjectCode") or ""
    
    if not unfiltered:
        logger_fn(f"Checking if dev issue {project_code}-{issue_id} is orphan...")
        links = gemini_client.get_issue_links(issue_id)
        belongs_to_chain = False
        for link in links:
            other_proj = link.get("OtherIssue", {}).get("ProjectCode") or link.get("Issue", {}).get("ProjectCode") or ""
            other_id = link.get("OtherIssue", {}).get("Id") or link.get("Issue", {}).get("Id")
            if other_id != issue_id and other_proj != project_code:
                belongs_to_chain = True
                logger_fn(f"⏭️ SKIP: {project_code}-{issue_id} is NOT orphan. Linked to {other_proj}-{other_id}.")
                return ""
                
    logger_fn(f"🚀 [STRATEGY: DEV ORPHAN] Migrating dev issue {project_code}-{issue_id} as standalone.")
    
    fields = map_gemini_issue_to_jira_fields(raw_issue, project_key, lookup_cache, jira_client)
    fields["summary"] = f"[{project_code}-{issue_id}] {fields['summary']}"
    
    # Lock type to Production for Dev issues
    jira_key = jira_client.create_single_issue(fields, JIRA_TYPE_PROD)
    logger_fn(f"   ✅ Created Standalone Production ticket: {jira_key}")
    
    migrate_comments(jira_key, raw_issue, jira_client, logger_fn)
    write_jira_key_back_to_gemini(issue_id, project_id, jira_key, raw_issue, gemini_client, logger_fn)
    
    return jira_key

# --- Worklog Migration ---

def migrate_time_tracking(gemini_id: int, jira_key: str, start_date: Optional[datetime], end_date: Optional[datetime], gemini_client: Any, jira_client: Any, logger_fn: Any):
    logger_fn(f"⏳ Starting worklog migration from Gemini #{gemini_id} to Jira {jira_key}...")
    
    raw_time_entries = gemini_client.get_issue_time_entries(gemini_id)
    if not raw_time_entries:
        logger_fn("ℹ️ No time entries found for this issue in Gemini.")
        return
        
    # Get all users for mapping User ID to email
    raw_users = gemini_client.get_users()
    user_map = {}
    for u in raw_users:
        u_entity = u.get("Entity", u.get("BaseEntity", u))
        u_id = u_entity.get("Id")
        u_email = u_entity.get("Email")
        if u_id and u_email:
            user_map[u_id] = u_email
            
    # Load all Jira users for email lookup
    jira_client.load_all_users()
    
    # Filter entries by date range if provided
    filtered_entries = []
    for entry in raw_time_entries:
        entity = entry.get("Entity", entry.get("BaseEntity", entry))
        entry_date_str = entity.get("EntryDate") or entity.get("StartDate") or ""
        if not entry_date_str:
            continue
            
        try:
            # Parse datetime string from Gemini
            entry_date = datetime.fromisoformat(entry_date_str.replace("Z", "+00:00"))
        except Exception:
            try:
                # fallback parse simple format
                entry_date = datetime.strptime(entry_date_str[:19], "%Y-%m-%dT%H:%M:%S")
            except Exception:
                entry_date = datetime.now()
                
        if start_date and entry_date.date() < start_date.date():
            continue
        if end_date and entry_date.date() > end_date.date():
            continue
            
        filtered_entries.append((entry, entry_date))
        
    if not filtered_entries:
        logger_fn("ℹ️ No time entries found in the specified date range.")
        return
        
    logger_fn(f"🔍 Found {len(filtered_entries)} time entries to migrate. Processing...")
    
    for entry, entry_date in filtered_entries:
        entity = entry.get("Entity", entry.get("BaseEntity", entry))
        user_id = entity.get("UserId")
        hours = entity.get("Hours", 0)
        minutes = entity.get("Minutes", 0)
        comment = entity.get("Comment", "Gemini Migration Worklog")
        
        email = user_map.get(user_id, "")
        assignee_id = jira_client.get_cached_account_id(email) if email else None
        
        if not assignee_id:
            logger_fn(f"   ⚠️ No Jira user account ID found for email '{email}'. Subtask will be unassigned.")
            
        time_spent_mins = (hours or 0) * 60 + (minutes or 0)
        if time_spent_mins <= 0:
            continue
            
        time_spent_str = f"{time_spent_mins}m"
        summary = f"Time logged by {email or 'Unknown'}"
        
        try:
            # 1. Create Jira subtask of type "Time Type"
            subtask_key = jira_client.create_time_entry(
                parent_issue_key=jira_key,
                summary=summary,
                assignee_id=assignee_id,
                time_type="Normal Time",  # Default or placeholder
                charge_type="Billable"    # Default or placeholder
            )
            # 2. Add worklog directly to the subtask
            formatted_date = entry_date.strftime("%Y-%m-%dT%H:%M:%S.000+0000")
            jira_client.add_worklog(subtask_key, time_spent_str, formatted_date, comment)
            logger_fn(f"   ✅ Logged {time_spent_str} to subtask {subtask_key} for {email}.")
        except Exception as e:
            logger_fn(f"   ❌ Failed to log time entry: {e}")

# --- Dispatcher ---

def process_migration(
    issue_id: int, 
    target_project_key: str, 
    gemini_client: Any, 
    jira_client: Any, 
    lookup_cache: GeminiLookupCache, 
    unfiltered: bool, 
    migrate_time_flag: bool, 
    start_date: Optional[datetime] = None, 
    end_date: Optional[datetime] = None, 
    logger_fn: Any = print
) -> Dict[str, Any]:
    """Κύριος διανομέας (Dispatcher) που επιλέγει στρατηγική βάσει του Project του issue."""
    raw_issue = gemini_client.get_single_issue(issue_id)
    if not raw_issue:
        raise ValueError(f"Gemini issue {issue_id} not found.")
        
    entity = raw_issue.get("Entity", raw_issue.get("BaseEntity", raw_issue))
    project_code = (raw_issue.get("ProjectCode") or "").upper()
    
    jira_key = ""
    strategy_used = ""
    
    if project_code == PROJECT_SRV:
        strategy_used = "SRV Tree Strategy"
        jira_key = migrate_srv_tree_strategy(raw_issue, target_project_key, gemini_client, jira_client, lookup_cache, logger_fn)
    elif project_code in SUPPORT_PROJECTS:
        strategy_used = "Support Orphan Strategy"
        jira_key = migrate_support_orphan_strategy(raw_issue, target_project_key, gemini_client, jira_client, lookup_cache, logger_fn, unfiltered)
    elif project_code in DEV_PROJECTS:
        strategy_used = "Dev Orphan Strategy"
        jira_key = migrate_dev_orphan_strategy(raw_issue, target_project_key, gemini_client, jira_client, lookup_cache, logger_fn, unfiltered)
    else:
        strategy_used = "Standard Strategy"
        jira_key = migrate_standard_strategy(raw_issue, target_project_key, gemini_client, jira_client, lookup_cache, logger_fn)
        
    # Migrate worklogs/time tracking if requested and we have a valid migrated key
    if jira_key and migrate_time_flag:
        migrate_time_tracking(issue_id, jira_key, start_date, end_date, gemini_client, jira_client, logger_fn)
        
    return {
        "success": bool(jira_key),
        "jira_key": jira_key,
        "strategy": strategy_used
    }

def render_migration_tab():
    import streamlit as st
    import pandas as pd
    from src.api.gemini_client import GeminiAPIClient, GeminiSearchCriteria
    from src.api.jira_client import JiraAPIClient
    from src.etl.migrator import process_migration, GeminiLookupCache
    from datetime import datetime, time as dt_time
    from dateutil.relativedelta import relativedelta
    
    st.subheader("🔄 Countersoft Gemini ➔ Jira Migration Tool")
    st.markdown("Μεταφορά θεμάτων από το Gemini στο Jira Cloud (`PYLMIG`) με βάση τις καθορισμένες στρατηγικές και mappings.")
    
    # Recreate clients on every render to prevent Streamlit hot-reload cache issue
    st.session_state.gemini_client = GeminiAPIClient()
    st.session_state.jira_client = JiraAPIClient()
    if "lookup_cache" not in st.session_state or not hasattr(st.session_state.lookup_cache, "user_id_to_email"):
        with st.spinner("Φόρτωση custom field definitions από το Gemini..."):
            cache = GeminiLookupCache(st.session_state.gemini_client)
            cache.preload()
            st.session_state.lookup_cache = cache
        
    gemini_client = st.session_state.gemini_client
    jira_client = st.session_state.jira_client
    lookup_cache = st.session_state.lookup_cache
    
    # Left and Right layouts
    col_filters, col_actions = st.columns([1, 1])
    
    with col_filters:
        st.markdown("### 🔍 Φίλτρα & Παράμετροι")
        
        migration_mode = st.radio("Τρόπος Μεταφοράς:", ["Μεμονωμένο Issue ID (Single)", "Μαζική Μεταφορά βάσει Φίλτρων (Batch)"])
        
        single_id = ""
        selected_project_id = None
        batch_project = "SRV"
        batch_search = ""
        start_date = None
        end_date = None
        
        # Advanced filters variables init
        filter_statuses = ""
        filter_statuses_not = False
        filter_types = ""
        filter_types_not = False
        filter_resources = ""
        filter_resources_not = False
        filter_components = ""
        filter_components_not = False
        filter_versions = ""
        filter_versions_not = False
        filter_max_items = 1000
        
        if migration_mode == "Μεμονωμένο Issue ID (Single)":
            single_id = st.text_input("Gemini Issue ID (π.χ. 316859):", value="")
        else:
            # Load project options dynamically
            project_mapping = {}  # display_label -> (id, code)
            try:
                projects = gemini_client.get_projects()
                for p in projects:
                    entity = p.get("BaseEntity", p.get("Entity", {}))
                    code = entity.get("Code") or ""
                    name = entity.get("Name") or ""
                    p_id = entity.get("Id") or p.get("Id")
                    if code and p_id:
                        label = f"{code} - {name}" if name else code
                        project_mapping[label] = (p_id, code)
            except Exception as e:
                print(f"Error loading projects: {e}")
                
            # If empty, fall back to standard project codes
            if not project_mapping:
                for code in ["SRV", "SHERC", "DHERC", "SGLX", "DGLX", "CUSTDGLX", "SMARTD"]:
                    project_mapping[code] = (None, code)
                    
            project_labels = sorted(list(project_mapping.keys()))
            # Find default selection index (SRV)
            default_index = 0
            for i, label in enumerate(project_labels):
                if label.startswith("SRV"):
                    default_index = i
                    break
                    
            selected_project_label = st.selectbox("Gemini Project:", project_labels, index=default_index)
            selected_project_id, batch_project = project_mapping[selected_project_label]
            
            batch_search = st.text_input("Κείμενο Αναζήτησης (Search Term):", value="")
            
            # Date filter range
            date_col1, date_col2 = st.columns(2)
            with date_col1:
                start_date = st.date_input("Από ημερομηνία:", value=None)
            with date_col2:
                end_date = st.date_input("Έως ημερομηνία:", value=None)
                
            # Advanced filters collapsible expander
            with st.expander("🛠️ Προηγμένα Φίλτρα (Advanced Filters)"):
                col_st, col_st_not = st.columns([3, 1])
                filter_statuses = col_st.text_input("Statuses (Καταστάσεις με κόμμα):", value="", help="π.χ. Open, In Progress, Closed")
                st.write("<div style='height: 12px;'></div>", unsafe_allow_html=True)
                filter_statuses_not = col_st_not.checkbox("NOT Statuses", value=False)
                
                col_tp, col_tp_not = st.columns([3, 1])
                filter_types = col_tp.text_input("Types (Τύποι με κόμμα):", value="", help="π.χ. Bug, Enhancement, Task")
                st.write("<div style='height: 12px;'></div>", unsafe_allow_html=True)
                filter_types_not = col_tp_not.checkbox("NOT Types", value=False)
                
                col_res, col_res_not = st.columns([3, 1])
                filter_resources = col_res.text_input("Resources (Αναθέσεις με κόμμα):", value="", help="π.χ. Δημήτρης Μπατσίλης")
                st.write("<div style='height: 12px;'></div>", unsafe_allow_html=True)
                filter_resources_not = col_res_not.checkbox("NOT Resources", value=False)
                
                col_comp, col_comp_not = st.columns([3, 1])
                filter_components = col_comp.text_input("Components (Εξαρτήματα με κόμμα):", value="", help="π.χ. UI, Core")
                st.write("<div style='height: 12px;'></div>", unsafe_allow_html=True)
                filter_components_not = col_comp_not.checkbox("NOT Components", value=False)
                
                col_ver, col_ver_not = st.columns([3, 1])
                filter_versions = col_ver.text_input("Versions (Εκδόσεις με κόμμα):", value="", help="π.χ. 1.0, 2.0")
                st.write("<div style='height: 12px;'></div>", unsafe_allow_html=True)
                filter_versions_not = col_ver_not.checkbox("NOT Versions", value=False)
                
                filter_max_items = st.number_input("Μέγιστο πλήθος (Max Items):", min_value=10, max_value=5000, value=1000, step=50)
                
        # Locked target Jira project
        st.text_input("Jira Target Project Key (Locked):", value="PYLMIG", disabled=True)
        
        # Action Options
        unfiltered = st.checkbox("Παράκαμψη ελέγχων αλυσίδας (Force / Unfiltered Mode)", value=False, help="Αγνοεί τους ελέγχους αν το DHERC/SHERC issue ανήκει σε άλλη αλυσίδα και το μεταφέρει αυτόνομα.")
        migrate_time_flag = st.checkbox("Μεταφορά Time Tracking (Worklogs)", value=True)
        
    with col_actions:
        st.markdown("### ⚙️ Ενέργειες Migration")
        
        # Preview/Search issues
        if st.button("🔍 Αναζήτηση / Προεπισκόπηση", use_container_width=True):
            with st.spinner("Αναζήτηση στο Gemini..."):
                found_issues = []
                if migration_mode == "Μεμονωμένο Issue ID (Single)":
                    if single_id.strip().isdigit():
                        raw_issue = gemini_client.get_single_issue(int(single_id))
                        if raw_issue:
                            found_issues.append(raw_issue)
                    else:
                        st.error("Παρακαλώ εισάγετε ένα έγκυρο αριθμητικό ID.")
                else:
                    try:
                        # If selected_project_id is None, try to find it
                        if not selected_project_id:
                            projects = gemini_client.get_projects()
                            for p in projects:
                                entity = p.get("BaseEntity", p.get("Entity", {}))
                                if entity.get("Code", "").upper() == batch_project.upper():
                                    selected_project_id = entity.get("Id") or p.get("Id")
                                    break
                    except Exception as e:
                        selected_project_id = None
                        st.error(f"Error fetching projects: {e}")
                        
                    if selected_project_id:
                        # Safety: default start_date to 3 months ago if not specified
                        actual_start_date = start_date
                        if not actual_start_date:
                            actual_start_date = (datetime.now() - relativedelta(months=3)).date()
                            st.info("ℹ️ Η αναζήτηση περιορίστηκε αυτόματα στους τελευταίους 3 μήνες για αποφυγή Timeout.")
                            
                        s_date = datetime.combine(actual_start_date, datetime.min.time())
                        e_date = datetime.combine(end_date, datetime.max.time()) if end_date else datetime.now()
                        
                        raw_issues = []
                        current_start = s_date
                        
                        # Loop and fetch in 3-month slices to avoid timeouts
                        while current_start < e_date:
                            current_end = current_start + relativedelta(months=3)
                            if current_end > e_date:
                                current_end = e_date
                                
                            criteria = GeminiSearchCriteria(
                                project_id=str(selected_project_id),
                                max_items=int(filter_max_items)
                            )
                            criteria.created_after = current_start
                            criteria.created_before = current_end
                            
                            try:
                                chunk_issues = gemini_client.get_issues_advanced(criteria)
                                if chunk_issues:
                                    raw_issues.extend(chunk_issues)
                            except Exception as e:
                                st.warning(f"⚠️ Σφάλμα λήψης πακέτου {current_start.strftime('%d/%m/%Y')} - {current_end.strftime('%d/%m/%Y')}: {e}")
                                
                            current_start = current_end
                            
                        try:
                            # Filter by search term
                            if batch_search:
                                raw_issues = [
                                    i for i in raw_issues 
                                    if batch_search.lower() in (i.get("Entity", {}).get("Title", "") or "").lower()
                                    or batch_search.lower() in (i.get("Entity", {}).get("Description", "") or "").lower()
                                ]
                                
                            # Filter by advanced statuses
                            if filter_statuses:
                                target_statuses = [s.strip().lower() for s in filter_statuses.split(",") if s.strip()]
                                if target_statuses:
                                    if filter_statuses_not:
                                        raw_issues = [x for x in raw_issues if (x.get("Status") or "").lower() not in target_statuses]
                                    else:
                                        raw_issues = [x for x in raw_issues if (x.get("Status") or "").lower() in target_statuses]
                                    
                            # Filter by advanced types
                            if filter_types:
                                target_types = [t.strip().lower() for t in filter_types.split(",") if t.strip()]
                                if target_types:
                                    if filter_types_not:
                                        raw_issues = [x for x in raw_issues if (x.get("Type") or "").lower() not in target_types]
                                    else:
                                        raw_issues = [x for x in raw_issues if (x.get("Type") or "").lower() in target_types]
                                    
                            # Filter by advanced resources
                            if filter_resources:
                                target_resources = [r.strip().lower() for r in filter_resources.split(",") if r.strip()]
                                if target_resources:
                                    filtered_by_resources = []
                                    for x in raw_issues:
                                        res_names = [r.get("Entity", {}).get("Fullname", "").lower() for r in x.get("Resources", [])]
                                        has_match = any(any(tr in rn for rn in res_names) for tr in target_resources)
                                        if filter_resources_not:
                                            if not has_match:
                                                filtered_by_resources.append(x)
                                        else:
                                            if has_match:
                                                filtered_by_resources.append(x)
                                    raw_issues = filtered_by_resources
                                    
                            # Filter by advanced components
                            if filter_components:
                                target_components = [c.strip().lower() for c in filter_components.split(",") if c.strip()]
                                if target_components:
                                    filtered_by_components = []
                                    for x in raw_issues:
                                        comp_names = [c.strip().lower() for c in (x.get("ComponentNames") or "").split(",") if c.strip()]
                                        has_match = any(any(tc in cn for cn in comp_names) for tc in target_components)
                                        if filter_components_not:
                                            if not has_match:
                                                filtered_by_components.append(x)
                                        else:
                                            if has_match:
                                                filtered_by_components.append(x)
                                    raw_issues = filtered_by_components
                                    
                            # Filter by advanced versions
                            if filter_versions:
                                target_versions = [v.strip().lower() for v in filter_versions.split(",") if v.strip()]
                                if target_versions:
                                    if filter_versions_not:
                                        raw_issues = [x for x in raw_issues if (x.get("FixedInVersion") or "").lower() not in target_versions]
                                    else:
                                        raw_issues = [x for x in raw_issues if (x.get("FixedInVersion") or "").lower() in target_versions]
                                    
                            # Remove duplicates
                            unique_issues = []
                            seen_ids = set()
                            for item in raw_issues:
                                entity = item.get("Entity", item.get("BaseEntity", {}))
                                item_id = entity.get("Id")
                                if item_id and item_id not in seen_ids:
                                    seen_ids.add(item_id)
                                    unique_issues.append(item)
                                    
                            found_issues = unique_issues
                        except Exception as e:
                            st.error(f"Error filtering issues: {e}")
                    else:
                        st.error(f"Το Project Code {batch_project} δεν βρέθηκε στο Gemini.")
                        
                if found_issues:
                    st.session_state.found_issues_to_migrate = found_issues
                    st.success(f"Βρέθηκαν {len(found_issues)} θέματα προς μεταφορά!")
                else:
                    st.session_state.found_issues_to_migrate = []
                    st.warning("Δεν βρέθηκαν θέματα με τα συγκεκριμένα κριτήρια.")
                    
        # Preview table and selection
        if "found_issues_to_migrate" in st.session_state and st.session_state.found_issues_to_migrate:
            st.markdown("**Επιλέξτε τα θέματα που θέλετε να μεταφέρετε:**")
            
            preview_data = []
            for issue in st.session_state.found_issues_to_migrate:
                entity = issue.get("Entity", issue.get("BaseEntity", issue))
                preview_data.append({
                    "ID": entity.get("Id"),
                    "Project": issue.get("ProjectCode", ""),
                    "Τίτλος": entity.get("Title", "")[:80],
                    "Τύπος": issue.get("Type", ""),
                    "Κατάσταση": issue.get("Status", ""),
                    "Ημ. Δημιουργίας": entity.get("Created", "")[:10] if entity.get("Created") else ""
                })
            
            df_preview = pd.DataFrame(preview_data)
            df_preview.insert(0, "Επιλογή", True)
            
            edited_df = st.data_editor(
                df_preview,
                column_config={"Επιλογή": st.column_config.CheckboxColumn(required=True)},
                disabled=["ID", "Project", "Τίτλος", "Τύπος", "Κατάσταση", "Ημ. Δημιουργίας"],
                hide_index=True,
                use_container_width=True
            )
            
            selected_ids = edited_df[edited_df["Επιλογή"] == True]["ID"].tolist()
            st.write(f"Επιλεγμένα για Migration: **{len(selected_ids)}** θέματα.")
            
            if st.button("🚀 Εκκίνηση Migration", type="primary", use_container_width=True):
                log_placeholder = st.empty()
                progress_bar = st.progress(0)
                status_logs = []
                
                def ui_logger(msg):
                    status_logs.append(msg)
                    log_placeholder.text_area("Migration Logs", value="\n".join(status_logs), height=250)
                    
                ui_logger(f"Ξεκινάει το Migration για {len(selected_ids)} θέματα στο Jira Project 'PYLMIG'...")
                
                success_count = 0
                for index, issue_id in enumerate(selected_ids):
                    try:
                        ui_logger(f"\n[{index+1}/{len(selected_ids)}] Επεξεργασία Gemini ID: {issue_id}...")
                        
                        s_dt = datetime.combine(start_date, datetime.min.time()) if start_date else None
                        e_dt = datetime.combine(end_date, datetime.max.time()) if end_date else None
                        
                        res = process_migration(
                            issue_id=issue_id,
                            target_project_key="PYLMIG",
                            gemini_client=gemini_client,
                            jira_client=jira_client,
                            lookup_cache=lookup_cache,
                            unfiltered=unfiltered,
                            migrate_time_flag=migrate_time_flag,
                            start_date=s_dt,
                            end_date=e_dt,
                            logger_fn=ui_logger
                        )
                        
                        if res["success"]:
                            success_count += 1
                            ui_logger(f"✅ Επιτυχές Migration! Jira Key: {res['jira_key']} (Στρατηγική: {res['strategy']})")
                        else:
                            ui_logger(f"⚠️ Το Migration ολοκληρώθηκε χωρίς να δημιουργηθεί νέο Jira ticket.")
                            
                    except Exception as e:
                        ui_logger(f"❌ Σφάλμα στο issue {issue_id}: {e}")
                        
                    progress_bar.progress((index + 1) / len(selected_ids))
                    
                ui_logger(f"\n🏁 Το Migration ολοκληρώθηκε! Επιτυχείς μεταφορές: {success_count}/{len(selected_ids)}.")
                st.balloons()
