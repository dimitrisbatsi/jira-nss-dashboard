import html
import re
from typing import Dict, Any
from datetime import datetime, timezone
from src.models.schemas import ProjectSchema, UserSchema, IssueSchema, ComponentSchema, CommentSchema, AuditSchema, CustomFieldSchema, TimeTrackingSchema

TIME_TYPE_MAP = {
    102: "External", 103: "Internal", 121: "Demo", 146: "Billable Development",
    147: "Non-Billable Development", 148: "Billable Presales - Demo", 149: "Billable Analysis",
    150: "Billable Implementation", 151: "Billable Test", 152: "Billable Documentation",
    153: "Billable Training", 154: "Non-Billable Presales - Demo", 155: "Non-Billable Analysis",
    156: "Non-Billable Implementation", 157: "Non-Billable Test", 158: "Non-Billable Documentation",
    159: "Non-Billable Training", 160: "Personal", 164: "Billable Support", 165: "Non-Billable Support",
    191: "Billable Coding", 192: "Non-Billable Coding", 201: "Billable Prototype", 202: "Non-Billable Prototype",
    260: "Billable Presales - Demo", 261: "Billable Analysis", 262: "Billable Implementation",
    263: "Billable Development", 264: "Billable Test", 265: "Billable Documentation",
    266: "Billable Training", 267: "Billable Support", 268: "Billable Coding",
    269: "Non-Billable Presales - Demo", 270: "Non-Billable Analysis", 271: "Non-Billable Implementation",
    272: "Non-Billable Development", 273: "Non-Billable Test", 274: "Non-Billable Documentation",
    275: "Non-Billable Training", 276: "Non-Billable Support", 277: "Non-Billable Coding",
    278: "Personal", 279: "Internal", 280: "External", 281: "Demo", 282: "Billable Prototype",
    283: "Non – Billable Prototype", 313: "Billable Presales - Demo", 314: "Billable Analysis",
    315: "Billable Implementation", 316: "Billable Development", 317: "Billable Test",
    318: "Billable Documentation", 319: "Billable Training", 320: "Billable Support",
    321: "Billable Coding", 322: "Non-Billable Presales - Demo", 323: "Non-Billable Analysis",
    324: "Non-Billable Implementation", 325: "Non-Billable Development", 326: "Non-Billable Test",
    327: "Non-Billable Documentation", 328: "Non-Billable Training", 329: "Non-Billable Support",
    330: "Non-Billable Coding", 331: "Personal", 332: "Internal", 333: "External", 334: "Demo",
    335: "Billable Prototype", 336: "Non – Billable Prototype", 337: "Billable Presales - Demo",
    338: "Billable Analysis", 339: "Billable Implementation", 340: "Billable Development",
    341: "Billable Test", 342: "Billable Documentation", 343: "Billable Training",
    344: "Billable Support", 345: "Billable Coding", 346: "Non-Billable Presales - Demo",
    347: "Non-Billable Analysis", 348: "Non-Billable Implementation", 349: "Non-Billable Development",
    350: "Non-Billable Test", 351: "Non-Billable Documentation", 352: "Non-Billable Training",
    353: "Non-Billable Support", 354: "Non-Billable Coding", 355: "Personal", 356: "Internal",
    357: "External", 358: "Demo", 359: "Billable Prototype", 360: "Non – Billable Prototype",
    426: "-", 427: "Complain", 677: "Resource Absence", 678: "-", 679: "Analysis",
    680: "Support", 681: "Documentation", 682: "Test", 683: "Training", 684: "Implementation",
    685: "Development", 686: "Coding", 689: "Complain", 690: "Personal", 691: "Resource Absence",
    692: "Internal", 693: "External"
}

def get_json_val(data: Dict[str, Any], keys: list, default: Any = None) -> Any:
    """Βοηθητική συνάρτηση που ψάχνει πολλαπλά πιθανά keys (π.χ. 'Id', 'id', 'projectId')"""
    for k in keys:
        if k in data and data[k] is not None:
            return data[k]
    return default

# ===============================================================================
# ========================== GEMINI TRANSFORMERS ================================
# ===============================================================================


def transform_gemini_project(raw_gemini: Dict[str, Any]) -> ProjectSchema:
    """Μετατρέπει το JSON του Countersoft Gemini στο δικό μας Schema"""
    entity_data = raw_gemini.get("BaseEntity", raw_gemini)
    
    return ProjectSchema(
        ProjectID=get_json_val(entity_data, ["Id", "id", "projectId"]),
        SourceApp="Gemini", # <--- ΠΡΟΣΤΕΘΗΚΕ
        ProjectCode=get_json_val(entity_data, ["Code", "code", "projectCode"], "N/A"),
        ProjectName=get_json_val(entity_data, ["Name", "name", "projectName"], "Unnamed"),
        TemplateID=get_json_val(entity_data, ["TemplateId", "templateId"], 0),
        CreationDate=get_json_val(entity_data, ["Created", "created", "DateCreated"], datetime.now(timezone.utc)) 
    )

def transform_gemini_user(raw_gemini: Dict[str, Any]) -> UserSchema:
    """Μετατρέπει το JSON του Countersoft Gemini στο UserSchema"""
    entity_data = raw_gemini.get("BaseEntity", raw_gemini)
    
    fname = get_json_val(entity_data, ["Firstname", "firstname"], "")
    sname = get_json_val(entity_data, ["Surname", "surname"], "")
    fullname = f"{fname} {sname}".strip()
    
    if not fullname:
        fullname = get_json_val(entity_data, ["Username", "username"], "Unknown User")
        
    return UserSchema(
        UserID=str(get_json_val(entity_data, ["Id", "id", "userId"], "")), # <--- ΕΓΙΝΕ STRING
        SourceApp="Gemini", # <--- ΠΡΟΣΤΕΘΗΚΕ
        Username=get_json_val(entity_data, ["Username", "username"], ""),
        Firstname=fname,
        Surname=sname if sname else None,
        Fullname=fullname,
        Email=get_json_val(entity_data, ["Email", "email"], ""),
        APIKey=get_json_val(entity_data, ["ApiKey", "apiKey", "APIKey"], ""),
        Active=get_json_val(entity_data, ["Active", "active"], True),
        CreationDate=get_json_val(entity_data, ["Created", "created", "DateCreated"], datetime.now(timezone.utc))
    )

def transform_gemini_issue(raw_gemini: Dict[str, Any], project_id: int) -> IssueSchema:
    """Μετατρέπει το JSON του Gemini Issue στο δικό μας IssueSchema"""
    entity_data = raw_gemini.get("Entity", raw_gemini.get("BaseEntity", raw_gemini))
    
    affected_versions = get_json_val(raw_gemini, ["AffectedVersionNumbers"], "")[:255]
    resources = get_json_val(raw_gemini, ["ResourceNames"], "")[:255]
    components = get_json_val(raw_gemini, ["ComponentNames"], "")[:255]
    title = get_json_val(entity_data, ["Title", "title"], "Untitled")[:255]

    return IssueSchema(
        IssueID=get_json_val(entity_data, ["Id", "id", "issueId"]),
        SourceApp="Gemini", # <--- ΠΡΟΣΤΕΘΗΚΕ
        ProjectID=project_id, 
        VersionID=None, 
        Reporter=str(get_json_val(raw_gemini, ["Reporter", "reporter"], "")), # Ασφάλεια
        Title=title,
        Type=get_json_val(raw_gemini, ["Type", "type"], ""),
        Priority=get_json_val(raw_gemini, ["Priority", "priority"], ""),
        Severity=get_json_val(raw_gemini, ["Severity", "severity"], ""),
        Resolution=get_json_val(raw_gemini, ["Resolution", "resolution"], ""),
        Status=get_json_val(raw_gemini, ["Status", "status"], ""),
        CreationDate=get_json_val(entity_data, ["Created", "created"], datetime.now(timezone.utc)),
        RevisedDate=get_json_val(entity_data, ["Revised", "revised"], None),
        ClosedDate=get_json_val(entity_data, ["ClosedDate", "closedDate"], None),
        AffectedVersions=affected_versions if affected_versions else None,
        Resources=resources if resources else None,
        Components=components if components else None,
        ImportedAt=datetime.now(timezone.utc)
    )

def transform_gemini_component(raw_gemini: Dict[str, Any], project_id: int) -> ComponentSchema:
    entity_data = raw_gemini.get("Entity", raw_gemini.get("BaseEntity", raw_gemini))
    
    return ComponentSchema(
        ComponentID=get_json_val(entity_data, ["Id", "id", "componentId"]),
        SourceApp="Gemini", # <--- ΠΡΟΣΤΕΘΗΚΕ
        ProjectID=project_id,
        ComponentName=get_json_val(entity_data, ["Name", "name", "componentName"], "Unknown"),
        ComponentDesc=get_json_val(entity_data, ["Description", "description"], None),
        ParentID=get_json_val(entity_data, ["ParentId", "parentId"], 0), # Fallback σε 0
        CreationDate=get_json_val(entity_data, ["Created", "created"], datetime.now(timezone.utc))
    )

def transform_gemini_comment(raw_comment: Dict[str, Any], issue_id: int, project_id: int) -> CommentSchema:
    entity_data = raw_comment.get("Entity", raw_comment.get("BaseEntity", raw_comment))
    fullname = get_json_val(raw_comment, ["Fullname", "fullname", "Creator", "creator"], "Unknown")
    
    return CommentSchema(
        CommentID=get_json_val(entity_data, ["Id", "id", "commentId"]),
        SourceApp="Gemini", # <--- ΠΡΟΣΤΕΘΗΚΕ
        IssueID=issue_id,
        ProjectID=project_id,
        UserID=str(get_json_val(entity_data, ["UserId", "userId"], "")), # <--- ΕΓΙΝΕ STRING
        Fullname=fullname[:255] if fullname else "",
        Comment=get_json_val(entity_data, ["Comment", "comment"], ""),
        Created=get_json_val(entity_data, ["Created", "created"], datetime.now(timezone.utc))
    ) 

def transform_gemini_audit(raw_audit: Dict[str, Any], issue_id: int, project_id: int) -> AuditSchema:
    entity_data = raw_audit.get("Entity", raw_audit.get("BaseEntity", raw_audit))
    fullname = get_json_val(raw_audit, ["Fullname", "fullname", "Creator", "creator", "Author", "author", "CreatedBy", "createdBy", "Reporter", "reporter"], "Unknown")
    
    return AuditSchema(
        AuditID=get_json_val(entity_data, ["Id", "id", "auditId"]),
        SourceApp="Gemini", # <--- ΠΡΟΣΤΕΘΗΚΕ
        IssueID=issue_id,
        ProjectID=project_id,
        UserID=str(get_json_val(entity_data, ["UserId", "userId"], "")), # <--- ΕΓΙΝΕ STRING
        Fullname=fullname[:255] if fullname else "",
        Created=get_json_val(entity_data, ["Created", "created"], datetime.now(timezone.utc)),
        FieldName=get_json_val(entity_data, ["Field", "field", "FieldName", "fieldName"], "")[:255],
        OldValue=get_json_val(entity_data, ["OldValue", "oldValue"], ""),
        NewValue=get_json_val(entity_data, ["NewValue", "newValue"], "")
    )

def transform_gemini_custom_field(raw_cf: Dict[str, Any], issue_id: int, project_id: int) -> CustomFieldSchema:
    base_entity = raw_cf.get("BaseEntity", {})
    custom_field_id = base_entity.get("CustomFieldId") or raw_cf.get("CustomFieldId", 0)
    name = raw_cf.get("Name") or raw_cf.get("Title") or ""
    lookup_fields = ["PartnerName", "CustomerName", "PylonFlexDirect"]
    
    if name in lookup_fields:
        field_value = base_entity.get("Data", "")
    else:
        field_value = raw_cf.get("FormattedData")
        if not field_value: 
            field_value = base_entity.get("Data", "")

    clean_value = html.unescape(str(field_value)) if field_value else ""
    
    return CustomFieldSchema(
        IssueID=issue_id,
        CustomFieldID=custom_field_id,
        SourceApp="Gemini", # <--- ΠΡΟΣΤΕΘΗΚΕ
        CustomFieldName=str(name)[:255],
        ProjectID=project_id,
        FieldValue=clean_value
    )

def transform_gemini_time_tracking(raw_time: Dict[str, Any], issue_id: int, project_id: int, issue_components: str) -> TimeTrackingSchema:
    entity = raw_time.get("Entity", raw_time.get("BaseEntity", raw_time))
    
    hours = get_json_val(entity, ["Hours", "hours"], 0)
    minutes = get_json_val(entity, ["Minutes", "minutes"], 0)
    time_type_id = get_json_val(entity, ["TimeTypeId", "timeTypeId"], 0) # Fallback σε 0
    time_type_name = TIME_TYPE_MAP.get(time_type_id, "Unknown") if time_type_id else "Unknown"
    
    return TimeTrackingSchema(
        TimeEntryID=get_json_val(entity, ["Id", "id", "timeEntryId"], 0),
        SourceApp="Gemini", # <--- ΠΡΟΣΤΕΘΗΚΕ
        IssueID=issue_id,
        ProjectID=project_id,
        TimeEntryDate=get_json_val(entity, ["EntryDate", "entryDate", "StartDate", "startDate"], datetime.now(timezone.utc)),
        TimeCreationDate=get_json_val(entity, ["Created", "created"], datetime.now(timezone.utc)),
        TimeResourceID=str(get_json_val(entity, ["UserId", "userId", "ResourceId", "resourceId"], "")), # <--- ΕΓΙΝΕ STRING
        TimeHours=int(hours) if hours else 0,
        TimeMinutes=int(minutes) if minutes else 0,
        TimeComment=get_json_val(entity, ["Comment", "comment"], ""),
        TimeTypeID=time_type_id,
        TimeTypeName=time_type_name,
        IssueComponent=issue_components if issue_components else None
    )

# =============================================================================
# ========================== JIRA TRANSFORMERS ================================
# =============================================================================

def extract_jira_value(field_data: Any) -> Optional[str]:
    """
    Αναγνωρίζει και εξάγει την καθαρή τιμή από τα πολύπλοκα πεδία/custom fields του Jira.
    """
    if not field_data:
        return None
        
    # Αν είναι απλό κείμενο (π.χ. Text Field)
    if isinstance(field_data, str):
        return field_data
        
    # Αν είναι Λεξικό (π.χ. Dropdown, Component, Version, Single User)
    if isinstance(field_data, dict):
        # Δοκιμάζουμε με σειρά προτεραιότητας: value, name, emailAddress, displayName
        return field_data.get("value") or field_data.get("name") or field_data.get("emailAddress") or field_data.get("displayName") or str(field_data)
        
    # Αν είναι Λίστα (π.χ. Multiple Components, Multiple Versions)
    if isinstance(field_data, list):
        # Τρέχουμε την ίδια συνάρτηση αναδρομικά για κάθε στοιχείο της λίστας
        extracted = [extract_jira_value(item) for item in field_data]
        # Κρατάμε μόνο όσα δεν είναι κενά
        valid_extracted = [str(x) for x in extracted if x]
        return ", ".join(valid_extracted) if valid_extracted else None
        
    return str(field_data)

def transform_jira_project(raw_jira: Dict[str, Any]) -> ProjectSchema:
    """Μετατρέπει το JSON του Jira (Project) στο δικό μας Schema"""
    return ProjectSchema(
        ProjectID=int(raw_jira.get("id", 0)), # Το Jira το στέλνει ως "10000"
        SourceApp="Jira",
        ProjectCode=raw_jira.get("key", "N/A"), # Το Jira ονομάζει τον κωδικό "key"
        ProjectName=raw_jira.get("name", "Unnamed"),
        TemplateID=0, # Δεν υπάρχει αντίστοιχο TemplateID στο βασικό Jira API
        CreationDate=datetime.now(timezone.utc) # Ή προσπάθησε να το βρεις αν έρχεται στο JSON
    )

def transform_jira_issue(raw_issue: Dict[str, Any]) -> IssueSchema:
    """Μετατρέπει το JSON του Jira (Issue) σε IssueSchema με τα σωστά Custom Fields."""
    fields = raw_issue.get("fields", {})
    
    project_dict = fields.get("project") or {}
    reporter_dict = fields.get("reporter") or {}
    issuetype_dict = fields.get("issuetype") or {}
    priority_dict = fields.get("priority") or {}
    status_dict = fields.get("status") or {}
    
    # Προσπαθούμε να πάρουμε το Email. Αν δεν υπάρχει, παίρνουμε το Display Name.
    reporter_identity = reporter_dict.get("emailAddress") or reporter_dict.get("displayName", "")
    
    # --- ΥΠΟΛΟΓΙΣΜΟΣ RESOURCES (Assignee + Specific Assignees) ---
    resource_list = []
    
    # 1. Προσθήκη Assignee
    assignee_dict = fields.get("assignee") or {}
    assignee_identity = assignee_dict.get("emailAddress") or assignee_dict.get("displayName")
    if assignee_identity:
        resource_list.append(assignee_identity)
        
    # 2. Προσθήκη Specific Assignees (customfield_10860) - Λίστα από Users
    specific_assignees = fields.get("customfield_10860") or []
    if isinstance(specific_assignees, list):
        for u in specific_assignees:
            if isinstance(u, dict):
                u_identity = u.get("emailAddress") or u.get("displayName")
                # Το βάζουμε στη λίστα ΜΟΝΟ αν δεν το έχουμε ξαναβάλει (deduplication)
                if u_identity and u_identity not in resource_list:
                    resource_list.append(u_identity)
                    
    # Ενώνουμε τα Resources με κόμμα και κόβουμε στους 255 χαρακτήρες για ασφάλεια στη βάση
    resources_str = ", ".join(resource_list)[:255] if resource_list else None
    # -------------------------------------------------------------

    return IssueSchema(
        IssueID=int(raw_issue.get("id", 0)),
        SourceApp="Jira",
        IssueKey=raw_issue.get("key"),
        ProjectID=int(project_dict.get("id", 0)) if project_dict.get("id") else 0,
        VersionID=None, 
        Reporter=reporter_identity[:255] or "",
        Title=(fields.get("summary") or "No Title")[:255], 
        
        # Προσθέτουμε "or ''" για να αποφύγουμε τα NULL στη βάση
        Type=issuetype_dict.get("name") or "",
        Priority=priority_dict.get("name") or "",
        Severity=extract_jira_value(fields.get("customfield_10194")) or "", 
        Resolution=extract_jira_value(fields.get("customfield_10662")) or "", 
        AffectedVersions=(extract_jira_value(fields.get("customfield_11182")) or "")[:255],
        Components=(extract_jira_value(fields.get("components")) or "")[:255],
        Resources=resources_str or "",
        Status=status_dict.get("name") or "",
        
        CreationDate=fields.get("created") or datetime.now(timezone.utc),
        RevisedDate=fields.get("updated"), 
        ClosedDate=fields.get("resolutiondate"), 
        ImportedAt=datetime.now(timezone.utc)
    )

def transform_jira_audits(raw_issue: Dict[str, Any]) -> List[AuditSchema]:
    """Εξάγει το Changelog ενός Jira Issue δίνοντας προτεραιότητα στο Email."""
    audits_list = []
    
    issue_id = int(raw_issue.get("id", 0))
    project_id = int(raw_issue.get("fields", {}).get("project", {}).get("id", 0))
    
    changelog = raw_issue.get("changelog", {})
    histories = changelog.get("histories", [])
    
    for history in histories:
        author_dict = history.get("author", {})
        created_at = history.get("created") or datetime.now(timezone.utc)
        
        # Προσπαθούμε να πάρουμε το Email.
        author_identity = author_dict.get("emailAddress") or author_dict.get("displayName", "")
        
        for item in history.get("items", []):
            try:
                audit = AuditSchema(
                    AuditID=int(history.get("id", 0)), 
                    SourceApp="Jira",
                    IssueID=issue_id,
                    ProjectID=project_id,
                    UserID=author_dict.get("accountId"), 
                    Fullname=author_identity[:255], # <--- ΕΔΩ μπαίνει το Email!
                    Created=created_at,
                    FieldName=item.get("field", "")[:255],
                    OldValue=str(item.get("fromString", "")) if item.get("fromString") else "",
                    NewValue=str(item.get("toString", "")) if item.get("toString") else ""
                )
                audits_list.append(audit)
            except Exception as e:
                print(f"[!] Σφάλμα κατά τη δημιουργία AuditSchema (History ID: {history.get('id')}): {e}")
                
    return audits_list

def transform_jira_custom_fields(raw_issue: Dict[str, Any], cf_mapping: Dict[str, str] = None) -> List[CustomFieldSchema]:
    """
    Σαρώνει το Jira Issue και εξάγει ΟΛΑ τα custom fields στον πίνακα GIssueCustomFields.
    Χρησιμοποιεί το cf_mapping για να βάλει το πραγματικό όνομα του πεδίου στη βάση.
    """
    if cf_mapping is None:
        cf_mapping = {}
        
    custom_fields_list = []
    
    issue_id = int(raw_issue.get("id", 0))
    fields = raw_issue.get("fields", {})
    project_id = int(fields.get("project", {}).get("id", 0))
    
    mapped_to_core = ["customfield_10194", "customfield_10662", "customfield_11182", "customfield_10860", "customfield_10553"]
    
    for key, raw_value in fields.items():
        if key.startswith("customfield_") and key not in mapped_to_core:
            clean_value = extract_jira_value(raw_value)
            
            if clean_value:
                match = re.search(r'\d+', key)
                cf_id = int(match.group()) if match else 0
                
                # ΕΔΩ Η ΜΑΓΕΙΑ: Βρίσκουμε το όνομα! 
                # Αν δεν το βρει στο CSV, κρατάει το "customfield_XXXX" ως ασφάλεια.
                real_name = cf_mapping.get(key, key)
                
                try:
                    cf_obj = CustomFieldSchema(
                        IssueID=issue_id,
                        CustomFieldID=cf_id,
                        SourceApp="Jira",
                        CustomFieldName=real_name[:255], # Χρησιμοποιούμε το πραγματικό όνομα!
                        ProjectID=project_id,
                        FieldValue=str(clean_value)[:1000]
                    )
                    custom_fields_list.append(cf_obj)
                except Exception as e:
                    print(f"[!] Σφάλμα στο Custom Field {key} (Issue {issue_id}): {e}")
                    
    return custom_fields_list

def extract_adf_text(adf_node: Any) -> str:
    """Εξάγει καθαρό κείμενο από το Atlassian Document Format (ADF) του Jira v3."""
    if not adf_node:
        return ""
    # Αν για κάποιο λόγο είναι ήδη string (π.χ. παλιό ticket ή Jira v2 endpoint), το επιστρέφουμε
    if isinstance(adf_node, str):
        return adf_node

    text_content = []
    if isinstance(adf_node, dict):
        if adf_node.get("type") == "text":
            text_content.append(adf_node.get("text", ""))
        if "content" in adf_node:
            for child in adf_node["content"]:
                text_content.append(extract_adf_text(child))
    elif isinstance(adf_node, list):
        for item in adf_node:
            text_content.append(extract_adf_text(item))

    return "".join(text_content)

def transform_jira_comments(raw_issue: Dict[str, Any]) -> List[CommentSchema]:
    """Εξάγει τα σχόλια από το JSON του Jira."""
    comments_list = []
    fields = raw_issue.get("fields", {})
    issue_id = int(raw_issue.get("id", 0))
    project_id = int(fields.get("project", {}).get("id", 0))

    comments_data = fields.get("comment", {}).get("comments", [])
    
    for c in comments_data:
        try:
            author_dict = c.get("author", {})
            author_identity = author_dict.get("emailAddress") or author_dict.get("displayName", "")
            
            c_obj = CommentSchema(
                CommentID=int(c.get("id", 0)),
                SourceApp="Jira",
                IssueID=issue_id,
                ProjectID=project_id,
                UserID=author_dict.get("accountId", ""),
                Fullname=author_identity[:255] or "",
                Comment=extract_adf_text(c.get("body")), # To σχόλιο έρχεται στο 'body'
                Created=c.get("created") or datetime.now(timezone.utc)
            )
            comments_list.append(c_obj)
        except Exception as e:
            print(f"[!] Σφάλμα στο Comment του Issue {raw_issue.get('key')}: {e}")
            
    return comments_list

def transform_jira_time_trackings(raw_issue: Dict[str, Any]) -> List[TimeTrackingSchema]:
    """Εξάγει τα Worklogs από το JSON του Jira."""
    time_trackings = []
    fields = raw_issue.get("fields", {})
    issue_id = int(raw_issue.get("id", 0))
    project_id = int(fields.get("project", {}).get("id", 0))

    # To Time Type & Component τα παίρνουμε από το Issue (όπως τα είχαμε κάνει map)
    time_type_obj = fields.get("customfield_10553")
    time_type_name = extract_jira_value(time_type_obj)

    # Ασφαλής μετατροπή του ID (Αν δεν υπάρχει, βάζουμε 0 αντί για None)
    time_type_id = 0
    if isinstance(time_type_obj, dict) and time_type_obj.get("id"):
        time_type_id = int(time_type_obj.get("id"))
    elif isinstance(time_type_obj, str) and time_type_obj.isdigit():
        time_type_id = int(time_type_obj)

    issue_components = extract_jira_value(fields.get("components"))
    issue_components = issue_components[:255] if issue_components else ""

    worklogs_data = fields.get("worklog", {}).get("worklogs", [])

    for wl in worklogs_data:
        try:
            total_seconds = wl.get("timeSpentSeconds", 0)
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60

            author_dict = wl.get("author", {})

            tt_obj = TimeTrackingSchema(
                TimeEntryID=int(wl.get("id", 0)),
                SourceApp="Jira",
                IssueID=issue_id,
                ProjectID=project_id,
                TimeEntryDate=wl.get("started") or datetime.now(timezone.utc),
                TimeCreationDate=wl.get("created") or datetime.now(timezone.utc),
                TimeResourceID=author_dict.get("accountId", ""),
                TimeHours=hours,
                TimeMinutes=minutes,
                TimeComment=extract_adf_text(wl.get("comment")),
                TimeTypeID=time_type_id,
                TimeTypeName=time_type_name[:255] if time_type_name else "Unknown",
                IssueComponent=issue_components
            )
            time_trackings.append(tt_obj)
        except Exception as e:
            print(f"[!] Σφάλμα στο Worklog του Issue {raw_issue.get('key')}: {e}")

    return time_trackings

def transform_jira_project(raw_project: Dict[str, Any]) -> ProjectSchema:
    return ProjectSchema(
        ProjectID=int(raw_project.get("id", 0)),
        SourceApp="Jira",
        ProjectCode=raw_project.get("key", "")[:50],
        ProjectName=raw_project.get("name", "")[:255],
        TemplateID=0, # Δεν έχει άμεσο αντίστοιχο το Jira
        CreationDate=datetime.now(timezone.utc) # Το search endpoint δεν φέρνει creation date πάντα
    )

def transform_jira_user(raw_user: Dict[str, Any]) -> UserSchema:
    # Το Jira χρησιμοποιεί accountId (π.χ. "712020:dcffc871...") το οποίο το κάναμε String στη βάση
    return UserSchema(
        UserID=raw_user.get("accountId", ""),
        SourceApp="Jira",
        Username=raw_user.get("emailAddress", raw_user.get("displayName", ""))[:150],
        Firstname="", # Δεν τα χωρίζει το Jira by default
        Surname="",
        Fullname=raw_user.get("displayName", "")[:300],
        Email=raw_user.get("emailAddress", "")[:255],
        APIKey="",
        Active=raw_user.get("active", False),
        CreationDate=datetime.now(timezone.utc)
    )

def transform_jira_component(raw_comp: Dict[str, Any], project_id: int) -> ComponentSchema:
    return ComponentSchema(
        ComponentID=int(raw_comp.get("id", 0)),
        SourceApp="Jira",
        ProjectID=project_id,
        ComponentName=raw_comp.get("name", "")[:255],
        ComponentDesc=raw_comp.get("description", ""),
        ParentID=0, # Δεν υποστηρίζει hierarchy στα components το Jira με τον ίδιο τρόπο
        CreationDate=datetime.now(timezone.utc)
    )