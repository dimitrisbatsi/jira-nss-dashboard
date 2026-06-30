import os
import sys
import time
import tomllib
import urllib.parse
import hashlib
import json
import requests
from datetime import datetime
from sqlalchemy import create_engine, text

# --- Reconfigure console output encoding to UTF-8 for Greek/Emoji console display on Windows ---
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

def load_env_file():
    env_vars = {}
    if os.path.exists(".env"):
        try:
            with open(".env", "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        v = v.strip().strip('"').strip("'")
                        env_vars[k.strip()] = v
        except Exception:
            pass
    return env_vars

def get_db_engine():
    secrets_path = os.path.join(".streamlit", "secrets.toml")
    if not os.path.exists(secrets_path):
        print(f"[ERROR] Secrets file not found at: {secrets_path}")
        return None, None
        
    try:
        with open(secrets_path, "rb") as f:
            secrets = tomllib.load(f)
        conn_str = secrets.get("CONNECTION_STRING", "")
        api_key = secrets.get("CLASSMARKER_API_KEY", "")
        api_secret = secrets.get("CLASSMARKER_API_SECRET", "")
    except Exception as e:
        print(f"[ERROR] Failed to load secrets: {e}")
        return None, None

    # Fallback to env / .env
    env_vars = load_env_file()
    if not api_key or api_key == "your_api_key":
        api_key = os.environ.get("CLASSMARKER_API_KEY") or env_vars.get("CLASSMARKER_API_KEY", "")
    if not api_secret or api_secret == "your_api_secret":
        api_secret = os.environ.get("CLASSMARKER_API_SECRET") or env_vars.get("CLASSMARKER_API_SECRET", "")
        
    if not conn_str:
        print("[ERROR] CONNECTION_STRING is missing in secrets.toml")
        return None, None

    # Parse CONNECTION_STRING
    parts = {}
    for part in conn_str.split(";"):
        if "=" in part:
            k, v = part.split("=", 1)
            parts[k.strip().lower()] = v.strip()
            
    server = parts.get("data source", parts.get("server", ""))
    database = parts.get("database", "")
    uid = parts.get("user id", parts.get("uid", ""))
    pwd = parts.get("password", parts.get("pwd", ""))
    
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
            # Test connection
            with engine.connect() as conn:
                pass
            return engine, (api_key, api_secret)
        except Exception:
            continue
    return None, (api_key, api_secret)

def generate_mock_results():
    """Generates mock test results with proctoring violations for testing"""
    print("[*] Generating mock ClassMarker test results...")
    
    proctoring_events_1 = [
        {"event_type": "tab_switch", "timestamp": "2026-06-26 14:02:15", "details": "User switched tab / browser focus lost"},
        {"event_type": "copy_paste", "timestamp": "2026-06-26 14:05:30", "details": "Clipboard copy/paste attempt detected"},
        {"event_type": "tab_switch", "timestamp": "2026-06-26 14:12:45", "details": "User switched tab / browser focus lost"}
    ]
    
    proctoring_events_2 = [
        {"event_type": "unauthorized_device", "timestamp": "2026-06-26 15:20:10", "details": "Secondary display connection detected"}
    ]
    
    results = [
        {
            "ResultID": 90001,
            "TestID": 1001,
            "TestName": "SQL Server Advanced Certification",
            "UserID": "cm_user_871",
            "CandidateName": "Γιώργος Παπαδόπουλος",
            "CandidateEmail": "g.papadopoulos@example.com",
            "Score": 85.0,
            "Percentage": 85.0,
            "DurationSeconds": 1800,
            "FinishedAt": datetime.now(),
            "ProctoringFlag": 1,
            "ProctoringEventsCount": 3,
            "ProctoringEventsJSON": json.dumps(proctoring_events_1, ensure_ascii=False),
            "ReviewStatus": "Pending",
            "ReviewerNotes": None,
            "ReviewedBy": None,
            "ReviewedAt": None,
            "CompanyCandidateID": None,
            "CompanyPartnerID": None
        },
        {
            "ResultID": 90002,
            "TestID": 1001,
            "TestName": "SQL Server Advanced Certification",
            "UserID": "cm_user_992",
            "CandidateName": "Μαρία Κωνσταντίνου",
            "CandidateEmail": "m.konstantinou@example.com",
            "Score": 92.5,
            "Percentage": 92.5,
            "DurationSeconds": 1550,
            "FinishedAt": datetime.now(),
            "ProctoringFlag": 0,
            "ProctoringEventsCount": 0,
            "ProctoringEventsJSON": json.dumps([], ensure_ascii=False),
            "ReviewStatus": "Approved",
            "ReviewerNotes": "Εξαιρετικό score χωρίς παραβάσεις",
            "ReviewedBy": "d.batsilis",
            "ReviewedAt": datetime.now(),
            "CompanyCandidateID": "EMP-9481",
            "CompanyPartnerID": "PARTNER-501"
        },
        {
            "ResultID": 90003,
            "TestID": 1002,
            "TestName": "Python & ETL Development Assessment",
            "UserID": "cm_user_551",
            "CandidateName": "Νικόλαος Γεωργίου",
            "CandidateEmail": "n.georgiou@example.com",
            "Score": 45.0,
            "Percentage": 45.0,
            "DurationSeconds": 2400,
            "FinishedAt": datetime.now(),
            "ProctoringFlag": 1,
            "ProctoringEventsCount": 1,
            "ProctoringEventsJSON": json.dumps(proctoring_events_2, ensure_ascii=False),
            "ReviewStatus": "Pending",
            "ReviewerNotes": None,
            "ReviewedBy": None,
            "ReviewedAt": None,
            "CompanyCandidateID": None,
            "CompanyPartnerID": None
        },
        {
            "ResultID": 90004,
            "TestID": 1002,
            "TestName": "Python & ETL Development Assessment",
            "UserID": "cm_user_228",
            "CandidateName": "Ελένη Δημητρίου",
            "CandidateEmail": "e.dimitriou@example.com",
            "Score": 78.0,
            "Percentage": 78.0,
            "DurationSeconds": 2100,
            "FinishedAt": datetime.now(),
            "ProctoringFlag": 0,
            "ProctoringEventsCount": 0,
            "ProctoringEventsJSON": json.dumps([], ensure_ascii=False),
            "ReviewStatus": "Pending",
            "ReviewerNotes": None,
            "ReviewedBy": None,
            "ReviewedAt": None,
            "CompanyCandidateID": None,
            "CompanyPartnerID": None
        }
    ]
    return results

def main():
    print("==================================================")
    print("🚀 Starting ClassMarker Test Results ETL Sync")
    print("==================================================")
    
    engine, api_creds = get_db_engine()
    if not engine:
        print("[ERROR] Failed to connect to database.")
        sys.exit(1)
        
    api_key, api_secret = api_creds
    
    results = []
    
    # Check API keys
    if not api_key or not api_secret or api_key == "your_api_key" or api_secret == "your_api_secret":
        print("[WARNING] ClassMarker API credentials are not configured. Using mock data.")
        results = generate_mock_results()
    else:
        print(f"[*] Syncing from ClassMarker API using key: {api_key[:5]}...")
        
        endpoints = [
            "https://api.classmarker.com/v1/links/recent_results.json",
            "https://api.classmarker.com/v1/groups/recent_results.json"
        ]
        
        for endpoint in endpoints:
            print(f"[*] Pulling results from: {endpoint}...")
            try:
                timestamp = str(int(time.time()))
                signature = hashlib.sha256((api_key + api_secret + timestamp).encode('utf-8')).hexdigest()
                
                url = f"{endpoint}?api_key={api_key}&signature={signature}&timestamp={timestamp}"
                res = requests.get(url, timeout=15)
                
                if res.status_code == 200:
                    data = res.json()
                    
                    # Check for ClassMarker internal errors (returned with HTTP 200)
                    if data.get("status") == "error":
                        err = data.get("error", {})
                        print(f"[WARNING] Endpoint {endpoint} returned error: {err.get('error_code')} - {err.get('error_message')}")
                        continue
                    
                    for r in data.get("results", []):
                        # Extract test details
                        test_obj = r.get("test") or {}
                        test_id = test_obj.get("test_id") or r.get("test_id") or 0
                        test_name = test_obj.get("test_name") or r.get("test_name") or "Unknown Test"
                        
                        # Extract user details
                        user_obj = r.get("user") or {}
                        user_id = user_obj.get("user_id") or r.get("user_id") or ""
                        first_name = user_obj.get("first_name") or r.get("first_name") or ""
                        last_name = user_obj.get("last_name") or r.get("last_name") or ""
                        candidate_name = f"{first_name} {last_name}".strip() or "Unknown Candidate"
                        candidate_email = user_obj.get("email") or r.get("email") or ""
                        
                        # Proctoring details
                        proctor_obj = r.get("proctoring") or r
                        events = proctor_obj.get("events") or []
                        proctoring_flag = 1 if (proctor_obj.get("flag", False) or len(events) > 0) else 0
                        events_count = len(events)
                        
                        # Format events array to store in JSON format
                        formatted_events = []
                        for ev in events:
                            ts_val = ev.get("timestamp", time.time())
                            # If timestamp is float/int, parse it
                            try:
                                dt_obj = datetime.fromtimestamp(float(ts_val))
                            except Exception:
                                dt_obj = datetime.now()
                            event_type = ev.get("event") or ev.get("event_type") or "unknown"
                            details = ev.get("details") or ev.get("seconds_away") or ""
                            if details and not isinstance(details, str):
                                details = str(details)
                            formatted_events.append({
                                "event_type": event_type,
                                "timestamp": dt_obj.strftime("%Y-%m-%d %H:%M:%S"),
                                "details": details
                            })
                        
                        finished_ts = r.get("finished") or r.get("date_completed") or r.get("date_finished") or time.time()
                        try:
                            dt_finished = datetime.fromtimestamp(float(finished_ts))
                        except Exception:
                            dt_finished = datetime.now()
                        
                        results.append({
                            "ResultID": r.get("result_id"),
                            "TestID": test_id,
                            "TestName": test_name,
                            "UserID": user_id,
                            "CandidateName": candidate_name,
                            "CandidateEmail": candidate_email,
                            "Score": float(r.get("score", 0.0)),
                            "Percentage": float(r.get("percentage", 0.0)),
                            "DurationSeconds": int(r.get("duration", 0)),
                            "FinishedAt": dt_finished,
                            "ProctoringFlag": proctoring_flag,
                            "ProctoringEventsCount": events_count,
                            "ProctoringEventsJSON": json.dumps(formatted_events, ensure_ascii=False)
                        })
                else:
                    print(f"[WARNING] Endpoint {endpoint} returned HTTP status {res.status_code}")
            except Exception as e:
                print(f"[WARNING] ClassMarker Results API call failed for {endpoint}: {e}")

    # Load results to database
    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            with engine.begin() as conn:
                print(f"[*] Upserting {len(results)} test results into CM_TestResults...")
                for r in results:
                    conn.execute(
                        text(
                            "MERGE CM_TestResults AS Target "
                            "USING (SELECT :id AS ResultID) AS Source "
                            "ON Target.ResultID = Source.ResultID "
                            "WHEN MATCHED THEN "
                            "    UPDATE SET Target.TestID = :test_id, Target.TestName = :test_name, "
                            "               Target.UserID = :user_id, Target.CandidateName = :candidate_name, "
                            "               Target.CandidateEmail = :candidate_email, Target.Score = :score, "
                            "               Target.Percentage = :percentage, Target.DurationSeconds = :duration_seconds, "
                            "               Target.FinishedAt = :finished_at, Target.ProctoringFlag = :proctoring_flag, "
                            "               Target.ProctoringEventsCount = :proctoring_events_count, "
                            "               Target.ProctoringEventsJSON = :proctoring_events_json "
                            "WHEN NOT MATCHED THEN "
                            "    INSERT (ResultID, TestID, TestName, UserID, CandidateName, CandidateEmail, "
                            "            Score, Percentage, DurationSeconds, FinishedAt, ProctoringFlag, "
                            "            ProctoringEventsCount, ProctoringEventsJSON, ReviewStatus) "
                            "    VALUES (:id, :test_id, :test_name, :user_id, :candidate_name, :candidate_email, "
                            "            :score, :percentage, :duration_seconds, :finished_at, :proctoring_flag, "
                            "            :proctoring_events_count, :proctoring_events_json, 'Pending');"
                        ),
                        {
                            "id": r["ResultID"],
                            "test_id": r["TestID"],
                            "test_name": r["TestName"],
                            "user_id": r["UserID"],
                            "candidate_name": r["CandidateName"],
                            "candidate_email": r["CandidateEmail"],
                            "score": r["Score"],
                            "percentage": r["Percentage"],
                            "duration_seconds": r["DurationSeconds"],
                            "finished_at": r["FinishedAt"],
                            "proctoring_flag": r["ProctoringFlag"],
                            "proctoring_events_count": r["ProctoringEventsCount"],
                            "proctoring_events_json": r["ProctoringEventsJSON"]
                        }
                    )
            print("[*] Test results sync successfully completed!")
            break
        except Exception as e:
            print(f"[WARNING] Database write failed on attempt {attempt}/{max_retries}: {e}")
            if attempt == max_retries:
                sys.exit(1)
            time.sleep(1)

if __name__ == "__main__":
    main()
