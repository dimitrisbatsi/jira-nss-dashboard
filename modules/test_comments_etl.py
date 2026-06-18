import os
import pandas as pd
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

from src.database.connection import engine
from src.etl.transformers import transform_gemini_comment
from src.api.gemini_client import GeminiAPIClient
from src.etl.loaders import upsert_comments
from src.database.core_queries import get_last_sync_date, update_last_sync_date

def get_target_project_ids():
    env_ids = os.getenv("GEMINI_TARGET_PROJECT_IDS", "")
    if not env_ids:
        return []
    return [int(pid.strip()) for pid in env_ids.split(",") if pid.strip().isdigit()]

def run_incremental_comments_etl():
    # Αυτό πρέπει να είναι ακριβώς όπως το όνομα στον πίνακα SyncMetadata σου!
    entity_name = "Comments" 
    
    target_ids = get_target_project_ids()
    if not target_ids:
        print("Δεν βρέθηκαν TARGET_PROJECT_IDS στο .env.")
        return

    client = GeminiAPIClient()
    last_sync = get_last_sync_date(engine, entity_name)
    print(f"[*] Τελευταίος συγχρονισμός για {entity_name}: {last_sync.strftime('%Y-%m-%d %H:%M:%S')} (UTC)")

    current_sync_start = datetime.now(timezone.utc)
    all_valid_comments = []
    sync_has_errors = False 
    
    print(f"[*] Ξεκινάει η λήψη Issues (για εξαγωγή Comments) σε {len(target_ids)} Projects...")
    
    for project_id in target_ids:
        print(f"\n  -> Αναζήτηση στα τροποποιημένα Issues του Project {project_id}...")
        try:
            # Χρησιμοποιούμε το Time Chunking των Issues!
            for chunk_of_issues in client.get_issues_time_chunked(project_id, revised_after=last_sync):
                for issue in chunk_of_issues:
                    # Εξάγουμε τα IDs του Issue 
                    issue_id = issue.get("Id", issue.get("Entity", {}).get("Id", 0))
                    
                    # Ψάχνουμε τη λίστα των σχολίων μέσα στο Issue
                    issue_comments = issue.get("Comments", [])
                    
                    for raw_comment in issue_comments:
                        try:
                            comment_obj = transform_gemini_comment(raw_comment, issue_id, project_id)
                            all_valid_comments.append(comment_obj.model_dump())
                        except Exception:
                            pass 
        except Exception as e:
            print(f"  -> Σφάλμα στο Project {project_id}: {e}")
            sync_has_errors = True

    if sync_has_errors:
        print("\n[ΣΦΑΛΜΑ] Διακοπή λόγω σφαλμάτων. Το Timestamp ΔΕΝ θα ενημερωθεί.")
        return

    if not all_valid_comments:
        print("\n[*] Δεν υπάρχουν νέα ή τροποποιημένα Comments. Πλήρως συγχρονισμένο!")
        update_last_sync_date(engine, entity_name, current_sync_start)
        return

    print(f"\n[*] Προετοιμασία DataFrame για {len(all_valid_comments)} εγγραφές...")
    df = pd.DataFrame(all_valid_comments)
    
    # Deduplication (Μόνο στο CommentID)
    initial_count = len(df)
    df.drop_duplicates(subset=['CommentID'], keep='last', inplace=True) 
    if initial_count - len(df) > 0:
        print(f"[*] Αφαιρέθηκαν {initial_count - len(df)} διπλότυπα.")

    print(f"[*] Εκκίνηση Bulk Upsert...")
    try:
        upsert_comments(df, engine)
        update_last_sync_date(engine, entity_name, current_sync_start)
        print(f"\n[ΕΠΙΤΥΧΙΑ] Το Metadata Timestamp ενημερώθηκε σε {current_sync_start.strftime('%Y-%m-%d %H:%M:%S')}!")
    except Exception as e:
        print(f"\n[ΣΦΑΛΜΑ] Αποτυχία εγγραφής στη βάση.\nΛεπτομέρειες: {e}")

if __name__ == "__main__":
    run_incremental_comments_etl()