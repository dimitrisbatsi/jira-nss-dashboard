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
            signature = hashlib.sha256((api_key + api_secret + timestamp).encode('utf-8')).hexdigest()
            
            # Categories endpoint
            cat_url = f"https://api.classmarker.com/v1/categories.json?api_key={api_key}&signature={signature}&timestamp={timestamp}"
            cat_res = requests.get(cat_url, timeout=15)
            
            # Questions endpoint (fetched paginated)
            if cat_res.status_code == 200:
                cat_data = cat_res.json()
                print(f"[DEBUG] Categories API raw response: {cat_data}")
                
                # Check for ClassMarker internal errors (returned with HTTP 200)
                if cat_data.get("status") == "error":
                    err = cat_data.get("error", {})
                    print(f"[ERROR] Categories API error: {err.get('error_code')} - {err.get('error_message')}")
                    sys.exit(1)
                
                categories = []
                for pc in cat_data.get("parent_categories", []):
                    p_id = pc.get("parent_category_id") if pc.get("parent_category_id") is not None else pc.get("id")
                    p_name = pc.get("parent_category_name") or pc.get("name")
                    child_list = pc.get("categories") or []
                    
                    if p_id is not None:
                        if len(child_list) > 0:
                            # This is a parent category with subcategories, offset its ID to avoid collisions
                            categories.append({
                                "CategoryID": p_id + 100000,
                                "CategoryName": p_name or f"Parent Category {p_id}",
                                "ParentCategoryID": None
                            })
                            for c in child_list:
                                c_id = c.get("category_id") if c.get("category_id") is not None else c.get("id")
                                c_name = c.get("category_name") or c.get("name")
                                if c_id is not None:
                                    categories.append({
                                        "CategoryID": c_id,
                                        "CategoryName": c_name or f"Category {c_id}",
                                        "ParentCategoryID": p_id + 100000 # Point to offset parent
                                    })
                        else:
                            # This is a flat category with no subcategories, keep its ID clean
                            categories.append({
                                "CategoryID": p_id,
                                "CategoryName": p_name or f"Category {p_id}",
                                "ParentCategoryID": None
                            })
                    
                questions = []
                page = 1
                while True:
                    q_url = f"https://api.classmarker.com/v1/questions.json?api_key={api_key}&signature={signature}&timestamp={timestamp}&page={page}"
                    print(f"[*] Fetching questions page {page}...")
                    q_res = requests.get(q_url, timeout=15)
                    if q_res.status_code != 200:
                        print(f"[ERROR] Questions API HTTP error on page {page}: {q_res.status_code}")
                        sys.exit(1)
                        
                    q_data = q_res.json()
                    if q_data.get("status") == "error":
                        err = q_data.get("error", {})
                        print(f"[ERROR] Questions API error on page {page}: {err.get('error_code')} - {err.get('error_message')}")
                        sys.exit(1)
                        
                    page_questions = q_data.get("questions", [])
                    if not page_questions:
                        break
                        

                        
                    for q in page_questions:
                        q_id = q.get("question_id") if q.get("question_id") is not None else q.get("id")
                        q_cat_id = q.get("category_id")
                        
                        # Format options list combining options dict and correct_options list
                        opts_dict = q.get("options")
                        correct_list = q.get("correct_options") or []
                        if not isinstance(correct_list, list):
                            if correct_list:
                                correct_list = [correct_list]
                            else:
                                correct_list = []
                                
                        formatted_options = []
                        if isinstance(opts_dict, dict):
                            for key in sorted(opts_dict.keys()):
                                val = opts_dict[key]
                                content = val.get("content") or ""
                                is_correct = key in correct_list
                                formatted_options.append({
                                    "text": content,
                                    "correct": is_correct,
                                    "option_label": key
                                })
                        elif isinstance(opts_dict, list):
                            for o_idx, o in enumerate(opts_dict):
                                is_correct = o.get("correct", False)
                                content = o.get("text") or ""
                                formatted_options.append({
                                    "text": content,
                                    "correct": is_correct
                                })
                                
                        questions.append({
                            "QuestionID": q_id,
                            "CategoryID": q_cat_id,
                            "QuestionType": q.get("question_type") or q.get("type"),
                            "QuestionText": q.get("question") or q.get("text"),
                            "OptionsJSON": json.dumps(formatted_options, ensure_ascii=False),
                            "Points": float(q.get("points", 1.0)),
                            "Active": 1 if q.get("status") == "active" else 0,
                            "UpdatedAt": datetime.fromtimestamp(q.get("updated", time.time()))
                        })
                        
                    if len(page_questions) < 200:
                        break
                    page += 1
            else:
                print(f"[ERROR] HTTP status error: categories={cat_res.status_code}")
                sys.exit(1)
        except Exception as e:
            print(f"[ERROR] ClassMarker API call failed: {e}")
            sys.exit(1)

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
