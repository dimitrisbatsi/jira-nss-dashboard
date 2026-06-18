import os
import pandas as pd
import traceback
from datetime import datetime, timezone
from dotenv import load_dotenv
from sqlalchemy import text

load_dotenv()

from src.database.connection import engine, get_db_session
from src.etl.transformers import transform_gemini_component
from src.api.gemini_client import GeminiAPIClient
from src.api.jira_client import JiraAPIClient
from src.etl.transformers import transform_jira_component
from src.etl.loaders import upsert_components
from src.database.core_queries import update_last_sync_date
from src.utils.logger import create_sync_session_log, log_error, close_sync_session_log

def get_target_project_ids():
    env_ids = os.getenv("GEMINI_TARGET_PROJECT_IDS", "")
    if not env_ids:
        return []
    return [int(pid.strip()) for pid in env_ids.split(",") if pid.strip().isdigit()]

def run_components_etl():
    entity_name = "Gemini_Components"
    target_ids = get_target_project_ids()
    
    if not target_ids:
        print("Δεν βρέθηκαν TARGET_PROJECT_IDS στο .env.")
        return

    client = GeminiAPIClient()
    current_sync_start = datetime.now(timezone.utc)
    all_valid_components = []
    
    print(f"[*] Ξεκινάει η λήψη Components για {len(target_ids)} Projects (Full Sync)...")
    
    with get_db_session() as session:
        sync_log = create_sync_session_log(session, entity_name=entity_name)
        sync_has_errors = False

        for project_id in target_ids:
            try:
                raw_components = client.get_components(project_id)
                for item in raw_components:
                    comp_id = item.get("Id", "Unknown")
                    try:
                        comp_obj = transform_gemini_component(item, project_id)
                        all_valid_components.append(comp_obj.model_dump())
                    except Exception as e:
                        log_error(session, sync_log.ID, str(comp_id), f"Gemini Component Transform Error: {e}", traceback.format_exc())
                        sync_has_errors = True
            except Exception as e:
                print(f"  -> Σφάλμα στο Project {project_id}: {e}")
                log_error(session, sync_log.ID, f"Project-{project_id}", f"API Error: {e}", traceback.format_exc())
                sync_has_errors = True

        if all_valid_components:
            df = pd.DataFrame(all_valid_components)
            df.drop_duplicates(subset=['ComponentID', 'SourceApp'], keep='last', inplace=True) 
            
            print(f"\n[*] Προετοιμασία DataFrame για {len(df)} εγγραφές...")
            print(f"[*] Εκκίνηση Bulk Upsert...")
            try:
                upsert_components(df, engine)
            except Exception as e:
                print(f"\n[ΣΦΑΛΜΑ] Αποτυχία εγγραφής στη βάση. \nΛεπτομέρειες: {e}")
                log_error(session, sync_log.ID, "BatchUpsert-Gemini", f"Upsert Error: {e}", traceback.format_exc())
                sync_has_errors = True
        else:
            print("\n[*] Δεν βρέθηκαν Components.")

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

def run_jira_components_etl():
    client = JiraAPIClient()
    current_sync_start = datetime.now(timezone.utc)
    entity_name = "Jira_Components"
    print("\n--- JIRA COMPONENTS ETL (Dynamic) ---")
    
    with get_db_session() as session:
        sync_log = create_sync_session_log(session, entity_name=entity_name)
        sync_has_errors = False

        query = text("SELECT ProjectID, ProjectCode FROM GProjects WHERE SourceApp = 'Jira'")
        jira_projects = []
        try:
            with engine.connect() as conn:
                result = conn.execute(query)
                jira_projects = [(row[0], row[1]) for row in result]
            print(f"[*] Βρέθηκαν {len(jira_projects)} Jira Projects στη βάση για συγχρονισμό.")
        except Exception as e:
            print(f"[ΣΦΑΛΜΑ] Αποτυχία ανάγνωσης Projects από τη βάση: {e}")
            log_error(session, sync_log.ID, "DBRead", f"Failed to read Jira Projects: {e}", traceback.format_exc())
            sync_log.Status = "Failed"
            sync_log.FinishedAt = datetime.utcnow()
            session.commit()
            return

        all_components = []
        
        for pid, pcode in jira_projects:
            try:
                print(f"[*] Λήψη Components για το Project: {pcode} (ID: {pid})...")
                raw_comps = client.get_components(pcode)
                
                for item in raw_comps:
                    comp_id = item.get("id", "Unknown")
                    try:
                        c_obj = transform_jira_component(item, pid)
                        all_components.append(c_obj.model_dump())
                    except Exception as e:
                        log_error(session, sync_log.ID, str(comp_id), f"Jira Component Transform Error: {e}", traceback.format_exc())
                        sync_has_errors = True
                    
            except Exception as e:
                print(f"  -> Σφάλμα στο Project {pcode}: {e}")
                log_error(session, sync_log.ID, str(pcode), f"Jira API Error: {e}", traceback.format_exc())
                sync_has_errors = True
                
        if all_components:
            df = pd.DataFrame(all_components)
            df.drop_duplicates(subset=['ComponentID', 'SourceApp'], keep='last', inplace=True)
            try:
                upsert_components(df, engine)
                print(f"[ΕΠΙΤΥΧΙΑ] Ολοκληρώθηκε ο συγχρονισμός {len(df)} Components.")
            except Exception as e:
                print(f"[ΣΦΑΛΜΑ] Αποτυχία εγγραφής Components: {e}")
                log_error(session, sync_log.ID, "BatchUpsert-Jira", f"Jira Upsert Error: {e}", traceback.format_exc())
                sync_has_errors = True
        else:
            print("[*] Δεν βρέθηκαν νέα Components για συγχρονισμό.")

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
    run_components_etl()
    print("--- Ξεκινάει το Jira ETL ---")
    run_jira_components_etl()