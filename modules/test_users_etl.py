import pandas as pd
import traceback
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

from src.database.connection import engine, get_db_session
from src.etl.transformers import transform_gemini_user
from src.api.gemini_client import GeminiAPIClient
from src.api.jira_client import JiraAPIClient
from src.etl.transformers import transform_jira_user
from src.etl.loaders import upsert_users
from src.database.core_queries import update_last_sync_date
from src.utils.logger import create_sync_session_log, log_error, close_sync_session_log

def run_users_etl():
    client = GeminiAPIClient()
    entity_name = "Gemini_Users"
    
    with get_db_session() as session:
        sync_log = create_sync_session_log(session, entity_name=entity_name)
        sync_has_errors = False
        current_sync_start = datetime.now(timezone.utc)

        print("1. Λήψη χρηστών από το API...")
        try:
            raw_users = client.get_users()
            print(f"Βρέθηκαν συνολικά {len(raw_users)} χρήστες στο API.")
        except Exception as e:
            print(f"Αποτυχία λήψης: {e}")
            log_error(session, sync_log.ID, "GeminiAPI", f"Failed to fetch users: {e}", traceback.format_exc())
            sync_log.Status = "Failed"
            sync_log.FinishedAt = datetime.utcnow()
            session.commit()
            return

        print("2. Transformation & Validation (Pydantic)...")
        valid_users = []
        for item in raw_users:
            user_id = item.get("Id", item.get("id", "Unknown"))
            try:
                user_obj = transform_gemini_user(item)
                valid_users.append(user_obj.model_dump())
            except Exception as e:
                log_error(session, sync_log.ID, str(user_id), f"Gemini User Transform Error: {e}", traceback.format_exc())
                sync_has_errors = True

        if valid_users:
            print("3. Μετατροπή σε Pandas DataFrame...")
            df = pd.DataFrame(valid_users)
            print(f"\n4. Bulk Uploading (Upsert) {len(df)} χρηστών στον SQL Server...")
            try:
                upsert_users(df, engine)
            except Exception as e:
                print(f"Σφάλμα κατά την εγγραφή στη βάση: {e}")
                log_error(session, sync_log.ID, "BatchUpsert-Gemini", f"Upsert Error: {e}", traceback.format_exc())
                sync_has_errors = True
        else:
            print("Δεν βρέθηκαν έγκυροι χρήστες.")

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

def run_jira_users_etl():
    client = JiraAPIClient()
    current_sync_start = datetime.now(timezone.utc)
    entity_name = "Jira_Users"
    print("\n--- JIRA USERS ETL ---")
    
    with get_db_session() as session:
        sync_log = create_sync_session_log(session, entity_name=entity_name)
        sync_has_errors = False
        
        try:
            raw_users = client.get_users()
            valid_users = []
            
            for item in raw_users:
                user_id = item.get("accountId", "Unknown")
                try:
                    if item.get("accountType") == "atlassian": 
                        u_obj = transform_jira_user(item)
                        valid_users.append(u_obj.model_dump())
                except Exception as e:
                    log_error(session, sync_log.ID, str(user_id), f"Jira User Transform Error: {e}", traceback.format_exc())
                    sync_has_errors = True
                    
            if valid_users:
                df = pd.DataFrame(valid_users)
                try:
                    upsert_users(df, engine)
                    print(f"[ΕΠΙΤΥΧΙΑ] Ανέβηκαν {len(df)} Jira Users.")
                except Exception as e:
                    print(f"Σφάλμα κατά την εγγραφή στη βάση: {e}")
                    log_error(session, sync_log.ID, "BatchUpsert-Jira", f"Jira Upsert Error: {e}", traceback.format_exc())
                    sync_has_errors = True
                    
        except Exception as e:
            print(f"Σφάλμα Jira Users API: {e}")
            log_error(session, sync_log.ID, "JiraAPI", f"Failed to fetch Jira users: {e}", traceback.format_exc())
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
    run_users_etl()
    print("--- Ξεκινάει το Jira ETL ---")
    run_jira_users_etl()