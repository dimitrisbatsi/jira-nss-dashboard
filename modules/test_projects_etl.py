import pandas as pd
import os
import traceback
from datetime import datetime, timezone
from dotenv import load_dotenv

# Φόρτωση ρυθμίσεων
load_dotenv()

from src.database.connection import engine, get_db_session

from src.etl.transformers import transform_gemini_project
from src.api.gemini_client import GeminiAPIClient

from src.api.jira_client import JiraAPIClient
from src.etl.transformers import transform_jira_project

from src.etl.loaders import upsert_projects
from src.database.core_queries import update_last_sync_date
from src.utils.logger import create_sync_session_log, log_error, close_sync_session_log

def get_target_project_ids():
    """Διαβάζει τα επιθυμητά IDs από το .env και τα κάνει λίστα με integers."""
    env_ids = os.getenv("GEMINI_TARGET_PROJECT_IDS", "")
    if not env_ids:
        return []
    # Χωρίζει με το κόμμα, καθαρίζει τα κενά, και τα κάνει integers
    return [int(pid.strip()) for pid in env_ids.split(",") if pid.strip().isdigit()]

def run_real_projects_etl():
    entity_name = "Gemini_Projects"
    target_ids = get_target_project_ids()
    
    if not target_ids:
        print("Προσοχή: Δεν έχουν οριστεί TARGET_PROJECT_IDS στο .env αρχείο. Διακοπή.")
        return

    client = GeminiAPIClient()
    current_sync_start = datetime.now(timezone.utc)

    with get_db_session() as session:
        sync_log = create_sync_session_log(session, entity_name=entity_name)
        sync_has_errors = False

        print("1. Λήψη δεδομένων από το Countersoft Gemini API...")
        try:
            raw_projects = client.get_projects()
            print(f"Βρέθηκαν συνολικά {len(raw_projects)} projects στο API.")
        except Exception as e:
            print(f"Αποτυχία λήψης: {e}")
            log_error(session, sync_log.ID, "GeminiAPI", f"Failed to fetch projects: {e}", traceback.format_exc())
            sync_log.Status = "Failed"
            sync_log.FinishedAt = datetime.utcnow()
            session.commit()
            return

        print(f"2. Transformation & Φιλτράρισμα (Κρατάμε μόνο τα {len(target_ids)} επιθυμητά: {target_ids})...")
        valid_projects = []
        
        for item in raw_projects:
            project_id = item.get("Id", item.get("id", "Unknown"))
            try:
                project_obj = transform_gemini_project(item)
                
                # ΦΙΛΤΡΟ με τη δυναμική λίστα
                if project_obj.ProjectID in target_ids:
                    valid_projects.append(project_obj.model_dump())
                    
            except Exception as e:
                log_error(session, sync_log.ID, str(project_id), f"Gemini Project Transform Error: {e}", traceback.format_exc())
                sync_has_errors = True

        if valid_projects:
            print("3. Μετατροπή σε Pandas DataFrame...")
            df = pd.DataFrame(valid_projects)
            # Καλό είναι να βεβαιωθούμε ότι δεν υπάρχουν διπλότυπα πριν το upsert
            df.drop_duplicates(subset=['ProjectID', 'SourceApp'], keep='last', inplace=True)
            
            print(f"\n4. Bulk Uploading (Upsert) {len(df)} εγγραφών στον SQL Server...")
            try:
                upsert_projects(df, engine)
            except Exception as e:
                print(f"Σφάλμα κατά την εγγραφή στη βάση: {e}")
                log_error(session, sync_log.ID, "BatchUpsert-Gemini", f"Upsert Error: {e}", traceback.format_exc())
                sync_has_errors = True
        else:
            print("Δεν βρέθηκε κανένα από τα Target Projects στο API για Upsert.")

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

def run_jira_projects_etl():
    client = JiraAPIClient()
    current_sync_start = datetime.now(timezone.utc)
    entity_name = "Jira_Projects"
    print("\n--- JIRA PROJECTS ETL ---")
    
    with get_db_session() as session:
        sync_log = create_sync_session_log(session, entity_name=entity_name)
        sync_has_errors = False
        
        try:
            raw_projects = client.get_projects()
            valid_projects = []
            target_keys = ["PYLCOM", "PYLFLE", "PLINTS", "PYFLDR", "ESLKAS", "GLXENT"] 
            
            for item in raw_projects:
                project_key = item.get("key", "Unknown")
                try:
                    if project_key in target_keys:
                        p_obj = transform_jira_project(item)
                        valid_projects.append(p_obj.model_dump())
                except Exception as e:
                    log_error(session, sync_log.ID, str(project_key), f"Jira Project Transform Error: {e}", traceback.format_exc())
                    sync_has_errors = True
                    
            if valid_projects:
                df = pd.DataFrame(valid_projects)
                df.drop_duplicates(subset=['ProjectID', 'SourceApp'], keep='last', inplace=True)
                try:
                    upsert_projects(df, engine)
                    print(f"[ΕΠΙΤΥΧΙΑ] Ανέβηκαν {len(df)} Jira Projects.")
                except Exception as e:
                    print(f"Σφάλμα κατά την εγγραφή στη βάση (Jira Projects): {e}")
                    log_error(session, sync_log.ID, "BatchUpsert-Jira", f"Jira Upsert Error: {e}", traceback.format_exc())
                    sync_has_errors = True
                    
        except Exception as e:
            print(f"Σφάλμα Jira Projects API: {e}")
            log_error(session, sync_log.ID, "JiraAPI", f"Failed to fetch Jira projects: {e}", traceback.format_exc())
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

if __name__ == "__main__":
    print("--- Ξεκινάει το Gemini ETL ---")
    run_real_projects_etl() # Gemini
    print("--- Ξεκινάει το Jira ETL ---")
    run_jira_projects_etl() # Jira