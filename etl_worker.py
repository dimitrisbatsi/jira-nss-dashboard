import os
import sys
import time
import tomllib
import urllib.parse
import traceback
import subprocess
from datetime import datetime, timezone
from sqlalchemy import create_engine, text

# --- Reconfigure console output encoding to UTF-8 for Greek/Emoji console display on Windows ---
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

def get_db_engine():
    # Read secrets.toml
    secrets_path = os.path.join(".streamlit", "secrets.toml")
    if not os.path.exists(secrets_path):
        print(f"[ERROR] Secrets file not found at: {secrets_path}")
        return None
        
    try:
        with open(secrets_path, "rb") as f:
            secrets = tomllib.load(f)
        conn_str = secrets.get("CONNECTION_STRING", "")
    except Exception as e:
        print(f"[ERROR] Failed to load secrets: {e}")
        return None
        
    if not conn_str:
        print("[ERROR] CONNECTION_STRING is missing in secrets.toml")
        return None

    parts = {}
    for part in conn_str.split(";"):
        if "=" in part:
            k, v = part.split("=", 1)
            parts[k.strip().lower()] = v.strip()
            
    server = parts.get("data source", parts.get("server", ""))
    database = parts.get("database", "")
    uid = parts.get("user id", parts.get("uid", ""))
    pwd = parts.get("password", parts.get("pwd", ""))
    
    if not server or not database:
        print("[ERROR] Database server or database name is missing in connection string.")
        return None
        
    drivers = ["ODBC Driver 17 for SQL Server", "SQL Server Native Client 11.0", "SQL Server"]
    for driver in drivers:
        try:
            pyodbc_conn_str = f"DRIVER={{{driver}}};SERVER={server};DATABASE={database};"
            if uid and pwd:
                pyodbc_conn_str += f"UID={uid};PWD={pwd};"
            else:
                pyodbc_conn_str += "Trusted_Connection=yes;"
                
            params = urllib.parse.quote_plus(pyodbc_conn_str)
            engine = create_engine(f"mssql+pyodbc:///?odbc_connect={params}")
            # Quick connection test
            with engine.connect() as conn:
                pass
            return engine
        except Exception:
            continue
            
    print("[ERROR] All SQL Server ODBC drivers failed to connect.")
    return None

def main():
    print("==================================================")
    print(f"🚀 ETL Background Worker Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("==================================================")
    
    engine = get_db_engine()
    if not engine:
        sys.exit(1)
        
    # Ensure logs directory exists
    os.makedirs("logs", exist_ok=True)
    
    # Cleanup zombie 'Running' jobs from previous crashes/restarts
    try:
        from sqlalchemy import text
        with engine.begin() as conn:
            zombies = conn.execute(
                text("SELECT JobID FROM ETL_Queue WHERE Status = 'Running'")
            ).fetchall()
            if zombies:
                zombie_ids = [z[0] for z in zombies]
                print(f"[*] Found {len(zombie_ids)} zombie running jobs from previous session: {zombie_ids}")
                print("[*] Marking them as 'Failed' (Interrupted) and setting FinishedAt...")
                conn.execute(
                    text("UPDATE ETL_Queue SET Status = 'Failed', FinishedAt = :now WHERE Status = 'Running'"),
                    {"now": datetime.now()}
                )
                for zid in zombie_ids:
                    zlog = f"logs/etl_job_{zid}.log"
                    if os.path.exists(zlog):
                        with open(zlog, "a", encoding="utf-8") as lf:
                            lf.write("\n==================================================\n")
                            lf.write(f"⚠️ Job interrupted due to worker shutdown/restart at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}.\n")
                            lf.write("==================================================\n")
    except Exception as ex:
        print(f"[WARNING] Failed to clean up zombie jobs: {ex}")
        
    while True:
        try:
            # 1. Check if any job is currently 'Running'
            # This ensures only one job runs at a time to prevent conflicts/locks
            with engine.begin() as conn:
                running_job = conn.execute(
                    text("SELECT JobID, StartedAt FROM ETL_Queue WHERE Status = 'Running'")
                ).fetchone()
                
            if running_job:
                # Check for stale/zombie running job
                run_id, started_at = running_job
                if not started_at:
                    print(f"[!] Job #{run_id} is marked 'Running' but has no StartedAt timestamp. Marking as Failed (Corrupted).")
                    with engine.begin() as conn:
                        conn.execute(
                            text("UPDATE ETL_Queue SET Status = 'Failed', FinishedAt = :now WHERE JobID = :id"),
                            {"now": datetime.now(), "id": run_id}
                        )
                    continue
                else:
                    # Strip timezone if present to prevent naive/aware TypeError
                    if hasattr(started_at, 'tzinfo') and started_at.tzinfo is not None:
                        started_at = started_at.replace(tzinfo=None)
                    now_naive = datetime.now()
                    elapsed_hours = (now_naive - started_at).total_seconds() / 3600.0
                    if elapsed_hours > 6:
                        print(f"[!] Job #{run_id} has been 'Running' for {elapsed_hours:.1f} hours. Marking as Failed (Stale/Timeout).")
                        with engine.begin() as conn:
                            conn.execute(
                                text("UPDATE ETL_Queue SET Status = 'Failed', FinishedAt = :now WHERE JobID = :id"),
                                {"now": datetime.now(), "id": run_id}
                            )
                        continue

                # A job is legitimately running; wait for it
                time.sleep(3)
                continue
                
            # 2. Get the oldest 'Pending' job
            with engine.begin() as conn:
                job = conn.execute(
                    text("SELECT JobID, JobType, IssueKey, StartDate, EndDate, DateFilterType FROM ETL_Queue WHERE Status = 'Pending' ORDER BY JobID ASC")
                ).fetchone()
                
            if not job:
                # No pending jobs; sleep and poll again
                time.sleep(3)
                continue
                
            job_id, job_type, issue_key, start_date, end_date, date_type = job
            log_path = f"logs/etl_job_{job_id}.log"
            
            print(f"\n[JOB #{job_id}] Picking up pending job: {job_type} at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            
            # 3. Mark job as 'Running'
            with engine.begin() as conn:
                conn.execute(
                    text("UPDATE ETL_Queue SET Status = 'Running', StartedAt = :now, LogFilePath = :log WHERE JobID = :id"),
                    {"now": datetime.now(), "log": log_path, "id": job_id}
                )
                
            # 4. Construct Python command statement
            statement = ""
            if job_type == 'SYNC_PROJECTS':
                statement = (
                    "from modules.test_projects_etl import run_real_projects_etl, run_jira_projects_etl; "
                    "run_real_projects_etl(); run_jira_projects_etl()"
                )
            elif job_type == 'SYNC_USERS':
                statement = (
                    "from modules.test_users_etl import run_users_etl, run_jira_users_etl; "
                    "run_users_etl(); run_jira_users_etl()"
                )
            elif job_type == 'SYNC_COMPONENTS':
                statement = (
                    "from modules.test_components_etl import run_components_etl, run_jira_components_etl; "
                    "run_components_etl(); run_jira_components_etl()"
                )
            elif job_type == 'SYNC_ISSUES_INCREMENTAL':
                statement = (
                    "from modules.test_issues_etl import run_incremental_issues_and_children_etl, run_incremental_jira_etl; "
                    "run_incremental_issues_and_children_etl(); run_incremental_jira_etl(ignore_last_sync=False)"
                )
            elif job_type == 'FULL_SYNC':
                statement = (
                    "from modules.test_projects_etl import run_real_projects_etl, run_jira_projects_etl; "
                    "from modules.test_users_etl import run_users_etl, run_jira_users_etl; "
                    "from modules.test_components_etl import run_components_etl, run_jira_components_etl; "
                    "from modules.test_issues_etl import run_incremental_issues_and_children_etl, run_incremental_jira_etl; "
                    "print('[1/4] Syncing Projects...'); run_real_projects_etl(); run_jira_projects_etl(); "
                    "print('[2/4] Syncing Users...'); run_users_etl(); run_jira_users_etl(); "
                    "print('[3/4] Syncing Components...'); run_components_etl(); run_jira_components_etl(); "
                    "print('[4/4] Syncing Issues...'); run_incremental_issues_and_children_etl(); run_incremental_jira_etl()"
                )
            elif job_type == 'JIRA_FULL_SYNC':
                statement = (
                    "from modules.test_issues_etl import run_incremental_jira_etl; "
                    "run_incremental_jira_etl(ignore_last_sync=True)"
                )
            elif job_type == 'SINGLE_ISSUE_SYNC':
                statement = (
                    "from modules.test_issues_etl import run_single_jira_issue_sync; "
                    f"success = run_single_jira_issue_sync('{issue_key}'); "
                    "import sys; sys.exit(0 if success else 1)"
                )
            elif job_type == 'DATE_RANGE_SYNC':
                statement = (
                    "from modules.test_issues_etl import run_jira_date_range_sync; "
                    f"success = run_jira_date_range_sync('{start_date}', '{end_date}', '{date_type}'); "
                    "import sys; sys.exit(0 if success else 1)"
                )
            elif job_type == 'CLASSMARKER_QUESTIONS_SYNC':
                statement = (
                    "from modules.classmarker_questions_etl import main as run_questions_sync; "
                    "run_questions_sync()"
                )
            elif job_type == 'CLASSMARKER_RESULTS_SYNC':
                statement = (
                    "from modules.classmarker_results_etl import main as run_results_sync; "
                    "run_results_sync()"
                )
            else:
                # Unknown job type
                print(f"[JOB #{job_id}] Unknown job type: {job_type}. Failing job.")
                with engine.begin() as conn:
                    conn.execute(
                        text("UPDATE ETL_Queue SET Status = 'Failed', FinishedAt = :now WHERE JobID = :id"),
                        {"now": datetime.now(), "id": job_id}
                    )
                continue
                
            # 5. Open log file and run subprocess
            # Force unbuffered output and UTF-8 output encoding in the subprocess
            env = os.environ.copy()
            env["PYTHONIOENCODING"] = "utf-8"
            
            exit_code = -1
            try:
                with open(log_path, "w", encoding="utf-8") as log_file:
                    log_file.write(f"=== ETL Job #{job_id} ({job_type}) ===\n")
                    log_file.write(f"Started At: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                    log_file.write("==================================================\n\n")
                    log_file.flush()
                    
                    try:
                        process = subprocess.Popen(
                            [sys.executable, "-u", "-c", statement],
                            stdout=log_file,
                            stderr=subprocess.STDOUT,
                            env=env
                        )
                        process.wait()
                        exit_code = process.returncode
                    except Exception as proc_ex:
                        log_file.write(f"\n[CRITICAL ERROR] Failed to start subprocess: {proc_ex}\n")
                        log_file.write(traceback.format_exc())
                        exit_code = -1
                        
                    log_file.write("\n==================================================\n")
                    log_file.write(f"Finished At: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} with Exit Code: {exit_code}\n")
                    log_file.write("==================================================\n")
            except Exception as log_ex:
                print(f"[!] Log writing error for Job #{job_id}: {log_ex}")
            finally:
                # 6. Update database status based on execution result (ALWAYS executed)
                final_status = 'Success' if exit_code == 0 else 'Failed'
                print(f"[JOB #{job_id}] Finished with Status: {final_status}")
                
                # Retry loop for updating DB status
                for attempt in range(5):
                    try:
                        with engine.begin() as conn:
                            conn.execute(
                                text("UPDATE ETL_Queue SET Status = :status, FinishedAt = :now WHERE JobID = :id"),
                                {"status": final_status, "now": datetime.now(), "id": job_id}
                            )
                        break
                    except Exception as update_ex:
                        print(f"[!] Retry {attempt+1}/5 updating job status for #{job_id}: {update_ex}")
                        time.sleep(2)

        except Exception as e:
            print(f"[ERROR] Exception in polling loop: {e}")
            traceback.print_exc()
            time.sleep(5)

if __name__ == "__main__":
    main()
