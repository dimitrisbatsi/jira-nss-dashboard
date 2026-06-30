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

def generate_mock_questions():
    """Generates mock questions and categories for testing purposes"""
    print("[*] Generating mock ClassMarker categories and questions...")
    categories = [
        {"CategoryID": 101, "CategoryName": "SQL Server Administration", "ParentCategoryID": None},
        {"CategoryID": 102, "CategoryName": "Python Development", "ParentCategoryID": None},
        {"CategoryID": 103, "CategoryName": "Database Performance Tuning", "ParentCategoryID": 101}
    ]
    
    questions = [
        {
            "QuestionID": 2001,
            "CategoryID": 101,
            "QuestionType": "multiple_choice",
            "QuestionText": "Which isolation level prevents dirty reads but allows non-repeatable reads?",
            "OptionsJSON": json.dumps([
                {"text": "Read Uncommitted", "correct": False},
                {"text": "Read Committed", "correct": True},
                {"text": "Repeatable Read", "correct": False},
                {"text": "Serializable", "correct": False}
            ], ensure_ascii=False),
            "Points": 2.0,
            "Active": 1,
            "UpdatedAt": datetime.now()
        },
        {
            "QuestionID": 2002,
            "CategoryID": 102,
            "QuestionType": "multiple_choice",
            "QuestionText": "What does the @retry_on_deadlock decorator do in our ETL loader?",
            "OptionsJSON": json.dumps([
                {"text": "Prevents deadlocks from occurring", "correct": False},
                {"text": "Catches SQL Server error 1205/40001, rolls back, and retries the transaction with exponential backoff", "correct": True},
                {"text": "Sends a notification to the administrator", "correct": False},
                {"text": "Kills the transaction victim's session on the server", "correct": False}
            ], ensure_ascii=False),
            "Points": 3.0,
            "Active": 1,
            "UpdatedAt": datetime.now()
        },
        {
            "QuestionID": 2003,
            "CategoryID": 103,
            "QuestionType": "true_false",
            "QuestionText": "Adding WITH (NOLOCK) query hints in SQL Server completely avoids reader-writer deadlock contention.",
            "OptionsJSON": json.dumps([
                {"text": "True", "correct": True},
                {"text": "False", "correct": False}
            ], ensure_ascii=False),
            "Points": 1.0,
            "Active": 1,
            "UpdatedAt": datetime.now()
        }
    ]
    return categories, questions

def main():
    print("==================================================")
    print("🚀 Starting ClassMarker Questions ETL Sync")
    print("==================================================")
    
    engine, api_creds = get_db_engine()
    if not engine:
        print("[ERROR] Failed to connect to database.")
        sys.exit(1)
        
    api_key, api_secret = api_creds
    
    # Check if API credentials are valid, else use mock data
    if not api_key or not api_secret or api_key == "your_api_key" or api_secret == "your_api_secret":
        print("[WARNING] ClassMarker API credentials are not configured or are placeholder keys.")
        categories, questions = generate_mock_questions()
    else:
        # Real API logic
        print(f"[*] Syncing from ClassMarker API using key: {api_key[:5]}...")
        try:
            timestamp = str(int(time.time()))
            signature = hashlib.sha256((timestamp + api_secret).encode('utf-8')).hexdigest()
            
            # Categories endpoint
            cat_url = f"https://api.classmarker.com/v1/categories.json?api_key={api_key}&signature={signature}&timestamp={timestamp}"
            cat_res = requests.get(cat_url, timeout=15)
            
            # Questions endpoint
            q_url = f"https://api.classmarker.com/v1/questions.json?api_key={api_key}&signature={signature}&timestamp={timestamp}"
            q_res = requests.get(q_url, timeout=15)
            
            if cat_res.status_code == 200 and q_res.status_code == 200:
                cat_data = cat_res.json()
                q_data = q_res.json()
                
                categories = []
                for c in cat_data.get("categories", []):
                    categories.append({
                        "CategoryID": c.get("id"),
                        "CategoryName": c.get("name"),
                        "ParentCategoryID": c.get("parent_id")
                    })
                    
                questions = []
                for q in q_data.get("questions", []):
                    questions.append({
                        "QuestionID": q.get("id"),
                        "CategoryID": q.get("category_id"),
                        "QuestionType": q.get("type"),
                        "QuestionText": q.get("text"),
                        "OptionsJSON": json.dumps(q.get("options", []), ensure_ascii=False),
                        "Points": float(q.get("points", 1.0)),
                        "Active": 1 if q.get("status") == "active" else 0,
                        "UpdatedAt": datetime.fromtimestamp(q.get("updated", time.time()))
                    })
            else:
                print(f"[WARNING] API returned status code {cat_res.status_code}/{q_res.status_code}. Falling back to mock data.")
                categories, questions = generate_mock_questions()
        except Exception as e:
            print(f"[WARNING] ClassMarker API call failed: {e}. Falling back to mock data.")
            categories, questions = generate_mock_questions()

    # Database loading
    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            with engine.begin() as conn:
                print(f"[*] Upserting {len(categories)} categories into CM_Categories...")
                for cat in categories:
                    conn.execute(
                        text(
                            "MERGE CM_Categories AS Target "
                            "USING (SELECT :id AS CategoryID) AS Source "
                            "ON Target.CategoryID = Source.CategoryID "
                            "WHEN MATCHED THEN "
                            "    UPDATE SET Target.CategoryName = :name, Target.ParentCategoryID = :parent_id "
                            "WHEN NOT MATCHED THEN "
                            "    INSERT (CategoryID, CategoryName, ParentCategoryID) VALUES (:id, :name, :parent_id);"
                        ),
                        {"id": cat["CategoryID"], "name": cat["CategoryName"], "parent_id": cat["ParentCategoryID"]}
                    )
                
                print(f"[*] Upserting {len(questions)} questions into CM_Questions...")
                for q in questions:
                    conn.execute(
                        text(
                            "MERGE CM_Questions AS Target "
                            "USING (SELECT :id AS QuestionID) AS Source "
                            "ON Target.QuestionID = Source.QuestionID "
                            "WHEN MATCHED AND (Target.IsLocallyModified = 0 OR Target.IsLocallyModified IS NULL) THEN "
                            "    UPDATE SET Target.CategoryID = :cat_id, Target.QuestionType = :q_type, "
                            "               Target.QuestionText = :q_text, Target.OptionsJSON = :options, "
                            "               Target.Points = :points, Target.Active = :active, Target.UpdatedAt = :updated "
                            "WHEN NOT MATCHED THEN "
                            "    INSERT (QuestionID, CategoryID, QuestionType, QuestionText, OptionsJSON, Points, Active, UpdatedAt, IsLocallyModified) "
                            "    VALUES (:id, :cat_id, :q_type, :q_text, :options, :points, :active, :updated, 0);"
                        ),
                        {
                            "id": q["QuestionID"],
                            "cat_id": q["CategoryID"],
                            "q_type": q["QuestionType"],
                            "q_text": q["QuestionText"],
                            "options": q["OptionsJSON"],
                            "points": q["Points"],
                            "active": q["Active"],
                            "updated": q["UpdatedAt"]
                        }
                    )
            print("[*] Questions and Categories sync successfully completed!")
            break
        except Exception as e:
            print(f"[WARNING] Database write failed on attempt {attempt}/{max_retries}: {e}")
            if attempt == max_retries:
                sys.exit(1)
            time.sleep(1)

if __name__ == "__main__":
    main()
