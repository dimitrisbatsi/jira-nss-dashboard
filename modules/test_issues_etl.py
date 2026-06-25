import os
import sys
import pandas as pd
import traceback
from datetime import datetime, timezone
from tqdm import tqdm
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor, as_completed
from sqlalchemy import text

# --- Reconfigure console output encoding to UTF-8 for Greek/Emoji console display on Windows ---
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

load_dotenv()

from src.database.connection import engine, get_db_session
# -- GEMINI IMPORTS --
from src.etl.transformers import transform_gemini_issue, transform_gemini_comment, transform_gemini_audit, transform_gemini_custom_field, transform_gemini_time_tracking
from src.api.gemini_client import GeminiAPIClient
# -- JIRA IMPORTS --
from src.etl.transformers import transform_jira_issue, transform_jira_audits, transform_jira_comments, transform_jira_custom_fields, transform_jira_project, transform_jira_time_trackings
from src.api.jira_client import JiraAPIClient
# -- LOADERS & QUERIES --
from src.etl.loaders import upsert_issues, upsert_comments, upsert_audits, upsert_custom_fields, upsert_time_tracking
from src.database.core_queries import get_last_sync_date, update_last_sync_date
# -- LOGGER IMPORTS --
from src.utils.logger import create_sync_session_log, log_error, close_sync_session_log

def get_target_project_ids():
    env_ids = os.getenv("GEMINI_TARGET_PROJECT_IDS", "")
    if not env_ids:
        return []
    return [int(pid.strip()) for pid in env_ids.split(",") if pid.strip().isdigit()]

def run_incremental_issues_and_children_etl():
    entity_name = "Gemini_Issues"
    target_ids = get_target_project_ids()
    if not target_ids:
        return

    client = GeminiAPIClient()
    last_sync = get_last_sync_date(engine, entity_name)
    print(f"[*] Τελευταίος συγχρονισμός: {last_sync.strftime('%Y-%m-%d %H:%M:%S')} (UTC)")
    current_sync_start = datetime.now(timezone.utc)
    
    print(f"[*] Ξεκινάει η λήψη Issues, Comments & Audits για {len(target_ids)} Projects...")
    
    # Ανοίγουμε Session για τον Logger
    with get_db_session() as session:
        sync_log = create_sync_session_log(session, entity_name=entity_name)
        sync_has_errors = False 
        
        for project_id in target_ids:
            try:
                for chunk_of_issues in client.get_issues_time_chunked(project_id, revised_after=last_sync):
                    
                    chunk_issues, chunk_comments, chunk_audits, chunk_custom_fields, chunk_time_trackings = [], [], [], [], []
                    chunk_issue_ids = [item.get("Id") for item in chunk_of_issues if item.get("Id")]
                    history_dict = {}
                    
                    def fetch_history_for_thread(i_id):
                        try:
                            return i_id, client.get_issue_history(i_id)
                        except Exception:
                            return i_id, []

                    print(f"\n[*] Παράλληλη λήψη History για {len(chunk_issue_ids)} Issues...")
                    with ThreadPoolExecutor(max_workers=15) as executor:
                        future_to_id = {executor.submit(fetch_history_for_thread, i_id): i_id for i_id in chunk_issue_ids}
                        for future in tqdm(as_completed(future_to_id), total=len(chunk_issue_ids), desc="Λήψη History (Threads)"):
                            i_id, audits = future.result()
                            history_dict[i_id] = audits
                    
                    for item in tqdm(chunk_of_issues, desc=f"Project {project_id} - Processing Chunk"):
                        issue_id = item.get("Id", "Unknown")
                        try:
                            # ISSUE
                            issue_obj = transform_gemini_issue(item, project_id)
                            chunk_issues.append(issue_obj.model_dump())
                            
                            # COMMENTS
                            for raw_comment in item.get("Comments", []):
                                try:
                                    comment_obj = transform_gemini_comment(raw_comment, issue_obj.IssueID, project_id)
                                    chunk_comments.append(comment_obj.model_dump())
                                except Exception as e:
                                    log_error(session, sync_log.ID, str(issue_id), f"Comment Transform Error: {e}", traceback.format_exc())
                                    
                            # AUDITS
                            issue_audits = history_dict.get(issue_obj.IssueID, [])
                            for raw_audit in issue_audits: 
                                try:
                                    audit_obj = transform_gemini_audit(raw_audit, issue_obj.IssueID, project_id)
                                    chunk_audits.append(audit_obj.model_dump())
                                except Exception as e:
                                    log_error(session, sync_log.ID, str(issue_id), f"Audit Transform Error: {e}", traceback.format_exc())
                                    
                            # CUSTOM FIELDS
                            issue_custom_fields = item.get("CustomFields", [])
                            for raw_cf in issue_custom_fields: 
                                try:
                                    cf_obj = transform_gemini_custom_field(raw_cf, issue_obj.IssueID, project_id)
                                    if cf_obj.CustomFieldID != 0: 
                                        chunk_custom_fields.append(cf_obj.model_dump())
                                except Exception as e:
                                    log_error(session, sync_log.ID, str(issue_id), f"CF Transform Error: {e}", traceback.format_exc())
                                    
                            # TIME TRACKING
                            issue_components = issue_obj.Components 
                            issue_time_entries = item.get("TimeEntries", item.get("Worklogs", []))
                            for raw_time in issue_time_entries: 
                                try:
                                    time_obj = transform_gemini_time_tracking(raw_time, issue_obj.IssueID, project_id, issue_components)
                                    if time_obj.TimeEntryID != 0:
                                        chunk_time_trackings.append(time_obj.model_dump())
                                except Exception as e:
                                    log_error(session, sync_log.ID, str(issue_id), f"Time Transform Error: {e}", traceback.format_exc())
                                    
                        except Exception as e:
                            log_error(session, sync_log.ID, str(issue_id), f"Main Issue Transform Error: {e}", traceback.format_exc())
                            sync_has_errors = True
                    
                    # UPSERTS
                    try:
                        if chunk_issues:
                            upsert_issues(pd.DataFrame(chunk_issues).drop_duplicates(subset=['IssueID', 'SourceApp'], keep='last'), engine)
                        if chunk_comments:
                            upsert_comments(pd.DataFrame(chunk_comments).drop_duplicates(subset=['CommentID', 'SourceApp'], keep='last'), engine)
                        if chunk_audits:
                            upsert_audits(pd.DataFrame(chunk_audits).drop_duplicates(subset=['AuditID', 'SourceApp'], keep='last'), engine)
                        if chunk_custom_fields:
                            upsert_custom_fields(pd.DataFrame(chunk_custom_fields).drop_duplicates(subset=['IssueID', 'CustomFieldID', 'SourceApp'], keep='last'), engine)
                        if chunk_time_trackings:
                            upsert_time_tracking(pd.DataFrame(chunk_time_trackings).drop_duplicates(subset=['TimeEntryID', 'SourceApp'], keep='last'), engine)
                    except Exception as e:
                        log_error(session, sync_log.ID, f"BatchUpsert-Project{project_id}", f"Upsert Error: {e}", traceback.format_exc())
                        sync_has_errors = True

            except Exception as e:
                print(f"  -> Σφάλμα στο Project {project_id}: {e}")
                log_error(session, sync_log.ID, f"Project-{project_id}", f"Project Loop Error: {e}", traceback.format_exc())
                sync_has_errors = True

        # --- ΚΛΕΙΣΙΜΟ SYNC LOG (Αποκλειστικά με Raw SQL) ---
        final_status = "Completed with Errors" if sync_has_errors else "Completed"
        
        # Καλούμε τον logger μας που εκτελεί raw SQL
        close_sync_session_log(session, sync_log.ID, final_status)

        if not sync_has_errors:
            # Το update του Last Sync Date είναι ανεξάρτητο, δουλεύει τέλεια
            update_last_sync_date(engine, entity_name, current_sync_start)
            print(f"\n[ΕΠΙΤΥΧΙΑ] Το Metadata Timestamp ενημερώθηκε σε {current_sync_start.strftime('%Y-%m-%d %H:%M:%S')}!")
        else:
            print("\n[ΠΡΟΕΙΔΟΠΟΙΗΣΗ] Το Sync ολοκληρώθηκε με σφάλματα (δείτε πίνακα SyncLogDetails).")

def run_incremental_jira_etl(ignore_last_sync=False):
    entity_name = "Jira_Issues"
    current_sync_start = datetime.now(timezone.utc)
    client = JiraAPIClient()
    print("\n--- Ξεκινάει το Jira Issues ETL ---")

    with get_db_session() as session:
        sync_log = create_sync_session_log(session, entity_name=entity_name)
        sync_has_errors = False 

        query = text("SELECT ProjectCode FROM GProjects WHERE SourceApp = 'Jira'")
        jira_projects = []
        try:
            with engine.connect() as conn:
                result = conn.execute(query)
                jira_projects = [row[0] for row in result if row[0]]
        except Exception as e:
            log_error(session, sync_log.ID, "DBRead", f"Failed to read Jira Projects: {e}", traceback.format_exc())
            sync_log.Status = "Failed"
            sync_log.FinishedAt = datetime.utcnow()
            session.commit()
            return

        if not jira_projects:
            sync_log.Status = "Skipped"
            sync_log.FinishedAt = datetime.utcnow()
            session.commit()
            return

        projects_jql_str = ", ".join(jira_projects)
        if ignore_last_sync:
            last_sync_str = "2000-01-01 00:00"
            print("[*] Running Jira Sync from scratch (ignore_last_sync = True)")
        else:
            last_sync = get_last_sync_date(engine, entity_name)
            last_sync_str = last_sync.strftime('%Y-%m-%d %H:%M')
        current_sync_start = datetime.now(timezone.utc)
        
        jql_query = (
            f'project IN ({projects_jql_str}) '
            f'AND updated >= "{last_sync_str}" '
            f'AND ("product name[dropdown]" IN ("PYLON COMMERCIAL", "PYLON ERP", "PYLON FLEX", "Galaxy Enterprise") OR "product name[dropdown]" IS EMPTY) '
            f'ORDER BY updated ASC'
        )

        my_fields, custom_fields_mapping = get_dynamic_jira_fields("jira_custom_fields.csv")

        try:
            generator = client.get_issues_chunked(jql_query=jql_query, expand="changelog", chunk_size=50, requested_fields=my_fields)
            
            for chunk_of_issues in generator:
                chunk_issues, chunk_audits, chunk_custom_fields, chunk_comments, chunk_time_trackings = [], [], [], [], []
                
                for raw_issue in tqdm(chunk_of_issues, desc="Processing Jira Chunk"):
                    issue_key = raw_issue.get('key', 'Unknown')
                    try:
                        # ISSUE
                        issue_obj = transform_jira_issue(raw_issue)
                        chunk_issues.append(issue_obj.model_dump())
                        
                        # AUDITS
                        for audit_obj in transform_jira_audits(raw_issue):
                            chunk_audits.append(audit_obj.model_dump())

                        # CUSTOM FIELDS
                        for cf_obj in transform_jira_custom_fields(raw_issue, custom_fields_mapping):
                            if cf_obj.CustomFieldID != 0: 
                                chunk_custom_fields.append(cf_obj.model_dump())
                            
                        # COMMENTS
                        for comment_obj in transform_jira_comments(raw_issue):
                            chunk_comments.append(comment_obj.model_dump())

                        # TIME TRACKINGS
                        for time_obj in transform_jira_time_trackings(raw_issue):
                            chunk_time_trackings.append(time_obj.model_dump())
                        
                    except Exception as e:
                        log_error(session, sync_log.ID, issue_key, f"Jira Transform Error: {e}", traceback.format_exc())
                        sync_has_errors = True
                
                # UPSERTS
                try:
                    if chunk_issues:
                        upsert_issues(pd.DataFrame(chunk_issues).drop_duplicates(subset=['IssueID', 'SourceApp'], keep='last'), engine)
                    if chunk_audits:
                        upsert_audits(pd.DataFrame(chunk_audits).drop_duplicates(subset=['AuditID', 'SourceApp'], keep='last'), engine)
                    if chunk_custom_fields:
                        upsert_custom_fields(pd.DataFrame(chunk_custom_fields).drop_duplicates(subset=['IssueID', 'CustomFieldID', 'SourceApp'], keep='last'), engine)
                    if chunk_comments:
                        upsert_comments(pd.DataFrame(chunk_comments).drop_duplicates(subset=['CommentID', 'SourceApp'], keep='last'), engine)
                    if chunk_time_trackings:
                        upsert_time_tracking(pd.DataFrame(chunk_time_trackings).drop_duplicates(subset=['TimeEntryID', 'SourceApp'], keep='last'), engine)
                except Exception as e:
                    log_error(session, sync_log.ID, "BatchUpsert-Jira", f"Jira Upsert Error: {e}", traceback.format_exc())
                    sync_has_errors = True

        except Exception as e:
            log_error(session, sync_log.ID, "General-Jira", f"Critical Jira API Error: {e}", traceback.format_exc())
            sync_has_errors = True

        # --- ΚΛΕΙΣΙΜΟ SYNC LOG (Αποκλειστικά με Raw SQL) ---
        final_status = "Completed with Errors" if sync_has_errors else "Completed"
        
        # Καλούμε τον logger μας που εκτελεί raw SQL
        close_sync_session_log(session, sync_log.ID, final_status)

        if not sync_has_errors:
            # Το update του Last Sync Date είναι ανεξάρτητο, δουλεύει τέλεια
            update_last_sync_date(engine, entity_name, current_sync_start)
            print(f"\n[ΕΠΙΤΥΧΙΑ] Το Metadata Timestamp ενημερώθηκε σε {current_sync_start.strftime('%Y-%m-%d %H:%M:%S')}!")
        else:
            print("\n[ΠΡΟΕΙΔΟΠΟΙΗΣΗ] Το Sync ολοκληρώθηκε με σφάλματα (δείτε πίνακα SyncLogDetails).")

# [Ο υπόλοιπος κώδικας του get_dynamic_jira_fields παραμένει ίδιος...]
def get_dynamic_jira_fields(csv_filename: str = "jira_custom_fields.csv"):
    """
    Διαβάζει το CSV ανεξάρτητα από το αν έχει διαχωριστικό κόμμα (,) ή ερωτηματικό (;).
    Υποστηρίζει 2 στήλες (Όνομα, ID) ή και 1 στήλη (σκέτα IDs).
    """
    base_fields = [
        "summary", "project", "issuetype", "priority", "status", "created", 
        "updated", "resolutiondate", "reporter", "assignee", "components", 
        "worklog", "comment", "customfield_10194", "customfield_10662", 
        "customfield_11182", "customfield_10860", "customfield_10553"
    ]
    
    cf_list = []
    cf_mapping = {}
    
    if os.path.exists(csv_filename):
        try:
            # Το sep=None και engine='python' αφήνει την Pandas να μαντέψει αν είναι , ή ;
            df_cf = pd.read_csv(csv_filename, header=None, sep=None, engine='python')
            
            # Ελέγχουμε πόσες στήλες βρήκε
            has_two_columns = df_cf.shape[1] >= 2
            
            for index, row in df_cf.iterrows():
                # Αν έχει μόνο μία στήλη, το Όνομα και το ID είναι το ίδιο
                if not has_two_columns:
                    cf_name = str(row[0]).strip()
                    cf_val = str(row[0]).strip().lower()
                else:
                    cf_name = str(row[0]).strip()
                    cf_val = str(row[1]).strip().lower()
                    
                # Αν είναι κενή γραμμή, προσπερνάμε
                if pd.isna(cf_val) or cf_val == 'nan' or not cf_val:
                    continue 
                    
                # Φτιάχνουμε το σωστό κλειδί (π.χ. customfield_10014)
                if cf_val.startswith('customfield_'):
                    cf_id_str = cf_val
                elif cf_val.isdigit():
                    cf_id_str = f"customfield_{cf_val}"
                else:
                    continue
                    
                cf_list.append(cf_id_str)
                cf_mapping[cf_id_str] = cf_name # Σώζουμε το όνομα στο λεξικό
                
            print(f"[*] [Config] Φορτώθηκαν {len(cf_list)} έξτρα Custom Fields επιτυχώς!")
        except Exception as e:
            print(f"[!] Σφάλμα ανάγνωσης του '{csv_filename}': {e}. Θα χρησιμοποιηθούν τα βασικά.")
    else:
        print(f"[*] [Config] Δεν βρέθηκε το '{csv_filename}'. Θα χρησιμοποιηθούν μόνο τα βασικά πεδία.")
        
    final_fields = list(set(base_fields + cf_list))
    return ",".join(final_fields), cf_mapping

def run_jira_date_range_sync(start_date_str: str, end_date_str: str, date_type: str = 'updated'):
    """
    Συγχρονίζει Jira Issues που δημιουργήθηκαν ή ενημερώθηκαν σε ένα συγκεκριμένο ημερομηνιακό διάστημα.
    JQL: project IN (...) AND <date_type> >= "start_date" AND <date_type> <= "end_date"
    """
    entity_name = f"Jira_DateRange_{date_type.capitalize()}"
    client = JiraAPIClient()
    print(f"\n--- Ξεκινάει ο Συγχρονισμός Jira Issues βάσει Ημερομηνιών ({date_type}) ---")
    print(f"[*] Διάστημα: {start_date_str} έως {end_date_str}")

    with get_db_session() as session:
        sync_log = create_sync_session_log(session, entity_name=entity_name)
        sync_has_errors = False 

        query = text("SELECT ProjectCode FROM GProjects WHERE SourceApp = 'Jira'")
        jira_projects = []
        try:
            with engine.connect() as conn:
                result = conn.execute(query)
                jira_projects = [row[0] for row in result if row[0]]
        except Exception as e:
            log_error(session, sync_log.ID, "DBRead", f"Failed to read Jira Projects: {e}", traceback.format_exc())
            sync_log.Status = "Failed"
            sync_log.FinishedAt = datetime.utcnow()
            session.commit()
            return False

        if not jira_projects:
            sync_log.Status = "Skipped"
            sync_log.FinishedAt = datetime.utcnow()
            session.commit()
            print("[*] Δεν βρέθηκαν Jira Projects στη βάση.")
            return False

        projects_jql_str = ", ".join(jira_projects)
        
        jql_query = (
            f'project IN ({projects_jql_str}) '
            f'AND {date_type} >= "{start_date_str}" '
            f'AND {date_type} <= "{end_date_str}" '
            f'AND ("product name[dropdown]" IN ("PYLON COMMERCIAL", "PYLON ERP", "PYLON FLEX", "Galaxy Enterprise") OR "product name[dropdown]" IS EMPTY) '
            f'ORDER BY {date_type} ASC'
        )

        print(f"[*] JQL Query: {jql_query}")
        my_fields, custom_fields_mapping = get_dynamic_jira_fields("jira_custom_fields.csv")

        try:
            generator = client.get_issues_chunked(jql_query=jql_query, expand="changelog", chunk_size=50, requested_fields=my_fields)
            
            total_fetched = 0
            for chunk_of_issues in generator:
                chunk_issues, chunk_audits, chunk_custom_fields, chunk_comments, chunk_time_trackings = [], [], [], [], []
                
                for raw_issue in tqdm(chunk_of_issues, desc="Processing Jira Date Range Chunk"):
                    issue_key = raw_issue.get('key', 'Unknown')
                    try:
                        # ISSUE
                        issue_obj = transform_jira_issue(raw_issue)
                        chunk_issues.append(issue_obj.model_dump())
                        
                        # AUDITS
                        for audit_obj in transform_jira_audits(raw_issue):
                            chunk_audits.append(audit_obj.model_dump())

                        # CUSTOM FIELDS
                        for cf_obj in transform_jira_custom_fields(raw_issue, custom_fields_mapping):
                            if cf_obj.CustomFieldID != 0: 
                                chunk_custom_fields.append(cf_obj.model_dump())
                            
                        # COMMENTS
                        for comment_obj in transform_jira_comments(raw_issue):
                            chunk_comments.append(comment_obj.model_dump())

                        # TIME TRACKINGS
                        for time_obj in transform_jira_time_trackings(raw_issue):
                            chunk_time_trackings.append(time_obj.model_dump())
                        
                    except Exception as e:
                        log_error(session, sync_log.ID, issue_key, f"Jira Transform Error: {e}", traceback.format_exc())
                        sync_has_errors = True
                
                # UPSERTS
                try:
                    if chunk_issues:
                        upsert_issues(pd.DataFrame(chunk_issues).drop_duplicates(subset=['IssueID', 'SourceApp'], keep='last'), engine)
                    if chunk_audits:
                        upsert_audits(pd.DataFrame(chunk_audits).drop_duplicates(subset=['AuditID', 'SourceApp'], keep='last'), engine)
                    if chunk_custom_fields:
                        upsert_custom_fields(pd.DataFrame(chunk_custom_fields).drop_duplicates(subset=['IssueID', 'CustomFieldID', 'SourceApp'], keep='last'), engine)
                    if chunk_comments:
                        upsert_comments(pd.DataFrame(chunk_comments).drop_duplicates(subset=['CommentID', 'SourceApp'], keep='last'), engine)
                    if chunk_time_trackings:
                        upsert_time_tracking(pd.DataFrame(chunk_time_trackings).drop_duplicates(subset=['TimeEntryID', 'SourceApp'], keep='last'), engine)
                    total_fetched += len(chunk_issues)
                except Exception as e:
                    log_error(session, sync_log.ID, "BatchUpsert-JiraRange", f"Jira Upsert Error: {e}", traceback.format_exc())
                    sync_has_errors = True

            print(f"[*] Ολοκληρώθηκε ο συγχρονισμός! Συνολικά ενημερώθηκαν {total_fetched} issues.")

        except Exception as e:
            log_error(session, sync_log.ID, "General-JiraRange", f"Critical Jira Date Range Sync Error: {e}", traceback.format_exc())
            sync_has_errors = True

        # --- ΚΛΕΙΣΙΜΟ SYNC LOG (Αποκλειστικά με Raw SQL) ---
        final_status = "Completed with Errors" if sync_has_errors else "Completed"
        close_sync_session_log(session, sync_log.ID, final_status)
        
        return not sync_has_errors

def run_single_jira_issue_sync(issue_key: str):
    """
    Συγχρονίζει ένα συγκεκριμένο Jira Issue με βάση το IssueKey (π.χ. PYLCOM-536).
    Εκτυπώνει αναλυτικά βήματα και σφάλματα για σκοπούς debugging.
    """
    print(f"\n[DEBUGGER] Έναρξη συγχρονισμού για το μεμονωμένο Issue: {issue_key}")
    client = JiraAPIClient()
    
    # 1. Έλεγχος Σύνδεσης
    if not client.test_connection():
        print("[ΣΦΑΛΜΑ] Αποτυχία σύνδεσης στο Jira API.")
        return False
        
    jql_query = f'key = "{issue_key}"'
    my_fields, custom_fields_mapping = get_dynamic_jira_fields("jira_custom_fields.csv")
    
    print(f"[*] Εκτέλεση ερωτήματος JQL: {jql_query}")
    try:
        generator = client.get_issues_chunked(jql_query=jql_query, expand="changelog", chunk_size=1, requested_fields=my_fields)
        chunk_of_issues = next(generator)
    except StopIteration:
        print(f"[ΠΡΟΕΙΔΟΠΟΙΗΣΗ] Δεν βρέθηκε κανένα Issue με Key '{issue_key}' στο Jira.")
        return False
    except Exception as e:
        print(f"[ΣΦΑΛΜΑ API] Σφάλμα κατά τη λήψη του Issue: {e}")
        traceback.print_exc()
        return False
        
    if not chunk_of_issues:
        print(f"[ΠΡΟΕΙΔΟΠΟΙΗΣΗ] Το API επέστρεψε άδεια λίστα για το Key '{issue_key}'.")
        return False
        
    raw_issue = chunk_of_issues[0]
    print(f"[OK] Λήφθηκαν επιτυχώς raw δεδομένα για το issue {issue_key}.")
    
    # 2. Μετασχηματισμός & Debugging
    try:
        print("[*] Βήμα 1: Μετασχηματισμός Issue...")
        issue_obj = transform_jira_issue(raw_issue)
        print(f"  -> Δεδομένα Issue Schema: {issue_obj.model_dump()}")
        
        print("[*] Βήμα 2: Μετασχηματισμός Audits (Changelog)...")
        audits = transform_jira_audits(raw_issue)
        print(f"  -> Βρέθηκαν {len(audits)} εγγραφές ιστορικού (Audits).")
        
        print("[*] Βήμα 3: Μετασχηματισμός Custom Fields...")
        custom_fields = transform_jira_custom_fields(raw_issue, custom_fields_mapping)
        print(f"  -> Βρέθηκαν {len(custom_fields)} custom fields.")
        
        print("[*] Βήμα 4: Μετασχηματισμός Comments...")
        comments = transform_jira_comments(raw_issue)
        print(f"  -> Βρέθηκαν {len(comments)} σχόλια.")
        
        print("[*] Βήμα 5: Μετασχηματισμός Worklogs (Time Trackings)...")
        time_trackings = transform_jira_time_trackings(raw_issue)
        print(f"  -> Βρέθηκαν {len(time_trackings)} καταγραφές χρόνου.")
        
    except Exception as e:
        print(f"[ΣΦΑΛΜΑ TRANSFORMATION] Αποτυχία μετασχηματισμού: {e}")
        traceback.print_exc()
        return False
        
    # 3. Αποθήκευση στη Βάση (Upserts)
    print("\n[*] Βήμα 6: Αποθήκευση στη Βάση Δεδομένων...")
    try:
        df_issue = pd.DataFrame([issue_obj.model_dump()])
        print("  -> Upserting Issue...")
        ins, upd = upsert_issues(df_issue, engine)
        print(f"  -> Issue Upserted: Inserted {ins} | Updated {upd}")
        
        if audits:
            df_audits = pd.DataFrame([a.model_dump() for a in audits])
            print("  -> Upserting Audits...")
            upsert_audits(df_audits, engine)
            
        if custom_fields:
            df_cf = pd.DataFrame([cf.model_dump() for cf in custom_fields])
            print("  -> Upserting Custom Fields...")
            upsert_custom_fields(df_cf, engine)
            
        if comments:
            df_comments = pd.DataFrame([c.model_dump() for c in comments])
            print("  -> Upserting Comments...")
            upsert_comments(df_comments, engine)
            
        if time_trackings:
            df_tt = pd.DataFrame([t.model_dump() for t in time_trackings])
            print("  -> Upserting Time Trackings...")
            upsert_time_tracking(df_tt, engine)
            
        print(f"\n[SUCCESS] Ο συγχρονισμός και η αποθήκευση του Issue '{issue_key}' ολοκληρώθηκε επιτυχώς!")
        return True
    except Exception as e:
        print(f"[ΣΦΑΛΜΑ DATABASE] Αποτυχία αποθήκευσης στη βάση: {e}")
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("--- Ξεκινάει το Gemini ETL ---")
    run_incremental_issues_and_children_etl()
    
    print("--- Ξεκινάει το Jira ETL ---")
    run_incremental_jira_etl()