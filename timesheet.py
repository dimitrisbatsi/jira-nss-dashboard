import streamlit as st
import pandas as pd
import requests
import plotly.express as px
import io
import os
import re
import hashlib
import pyodbc
import time
import json
from datetime import datetime
from sqlalchemy import text
import time

# --- ETL Modules Imports ---
from modules.test_projects_etl import run_real_projects_etl, run_jira_projects_etl
from modules.test_users_etl import run_users_etl, run_jira_users_etl
from modules.test_components_etl import run_components_etl, run_jira_components_etl
from modules.test_issues_etl import run_incremental_issues_and_children_etl, run_incremental_jira_etl

APP_VERSION = "26.7.1a (2026-07-02)"

# --- Helper functions for state updates ---
def on_only_me_click(username):
    st.session_state["auth_key"] = [username]

def clear_keys_and_rerun(keys_to_clear):
    for k in keys_to_clear:
        if k in st.session_state:
            del st.session_state[k]
        if "widget_backup" in st.session_state and k in st.session_state["widget_backup"]:
            st.session_state["widget_backup"][k] = None
    st.rerun()

def get_business_days(start_ts, end_ts):
    s = pd.to_datetime(start_ts, errors='coerce')
    e = pd.to_datetime(end_ts, errors='coerce')
    
    def calculate_seconds(row):
        start = row['start']
        end = row['end']
        if pd.isna(start) or pd.isna(end) or start >= end:
            return 0.0
        
        # Support hours 09:00 - 17:00 (in seconds of the day)
        day_start = 9 * 3600  # 09:00
        day_end = 17 * 3600   # 17:00
        
        # Calculate for each day in range
        dates = pd.date_range(start=start.normalize(), end=end.normalize())
        total_seconds = 0
        
        for date in dates:
            # Exclude weekends (Saturday and Sunday)
            if date.weekday() >= 5: 
                continue
            
            # Start/end bounds for business hours on this day
            s_limit = max(start, date + pd.Timedelta(seconds=day_start))
            e_limit = min(end, date + pd.Timedelta(seconds=day_end))
            
            if s_limit < e_limit:
                total_seconds += (e_limit - s_limit).total_seconds()
        
        return total_seconds / 28800.0  # Divide by 8-hour workday (8 * 3600 seconds)
        
    temp_df = pd.DataFrame({'start': s, 'end': e})
    return temp_df.apply(calculate_seconds, axis=1)

def is_content_visible(target_apps_str):
    active_apps = st.session_state.get("active_app_view", ["Galaxy", "Pylon"])
    if not active_apps:
        return False
    if len(active_apps) >= 2:
        return True
    if not target_apps_str:
        return True
    target_apps = [a.strip() for a in target_apps_str.split(",") if a.strip()]
    if not target_apps:
        return True
    return any(app in active_apps for app in target_apps)

# --- 1. Ρυθμίσεις Σελίδας ---
st.set_page_config(layout="wide", page_title="NSS Support Hub", page_icon="📊")

# Initialize Session State Variables
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = None
    st.session_state.user_id = None
    st.session_state.user_role = None
    st.session_state.display_name = None
    st.session_state.default_project = None
    st.session_state.app_preferences = None

# Restore keys if they went missing due to an early rerun
if "widget_backup" in st.session_state:
    for k, v in st.session_state["widget_backup"].items():
        if k not in st.session_state and v is not None:
            st.session_state[k] = v

# Ένεση Custom CSS για σμίκρυνση των στοιχείων
st.markdown("""
    <style>
    /* 1. Μείωση του τεράστιου κενού στην κορυφή και στα πλάγια της σελίδας */
    .block-container {
        padding-top: 4.0rem !important;
        padding-bottom: 1.5rem !important;
        max-width: 95% !important;
    }
    
    /* 2. Σμίκρυνση των γραμματοσειρών στα Labels των φίλτρων (Selectboxes, Date inputs κλπ) */
    .stSelectbox label, .stMultiselect label, .stDateInput label {
        font-size: 0.85rem !important;
        font-weight: 500 !important;
        color: #475569 !important;
    }
    
    /* 3. Μείωση του ύψους στα ίδια τα input boxes (πολύ σημαντικό για compact look) */
    div[data-baseweb="select"] > div, div[data-baseweb="input"] > div {
        min-height: 2.2rem !important;
        font-size: 0.9rem !important;
    }
    
    /* 4. Μικρότερο κενό ανάμεσα στα elements του Sidebar και ορισμός width */
    [data-testid="stSidebar"] {
        min-width: 260px !important;
        max-width: 260px !important;
        width: 260px !important;
    }
    [data-testid="stSidebar"] .st-emotion-cache-16txtl3 {
        gap: 0.5rem !important;
    }
            
    /* Σμίκρυνση γραμματοσειράς σε ΟΛΑ τα στοιχεία ΜΟΝΟ μέσα στο sidebar */
    [data-testid="stSidebar"] * {
        font-size: 0.85rem !important;
    }
            
    /* Κρατάμε το Heading του sidebar σε μεγαλύτερο μέγεθος με τη λογική της επικεφαλίδας */
    .stHeadingSidebar {
        font-size: 1.3rem !important;        
    }
    
    /* Ειδικά για τα Labels (τίτλους) των φίλτρων στο Sidebar για να είναι πιο compact */
    [data-testid="stSidebar"] .stSelectbox label, 
    [data-testid="stSidebar"] .stMultiselect label, 
    [data-testid="stSidebar"] .stDateInput label {
        font-size: 0.8rem !important;
        font-weight: 500 !important;
    }

    /* 5. Navigation Menu Section Headers */
    .menu-section-header {
        font-size: 0.75rem !important;
        font-weight: 700 !important;
        color: #64748b !important; /* slate-500 */
        text-transform: uppercase !important;
        letter-spacing: 0.05em !important;
        margin-top: 1.0rem !important;
        margin-bottom: 0.3rem !important;
        padding-left: 0.4rem !important;
        border-bottom: 1px solid #e2e8f0 !important;
        padding-bottom: 2px !important;
    }
    
    /* 6. Premium Sidebar Navigation Buttons */
    div[data-testid="stSidebar"] div[data-testid="stButton"] > button {
        display: flex !important;
        align-items: center !important;
        justify-content: flex-start !important;
        text-align: left !important;
        width: 100% !important;
        padding: 8px 12px !important;
        border-radius: 6px !important;
        font-size: 0.85rem !important;
        font-weight: 500 !important;
        transition: all 0.2s ease !important;
        margin-bottom: 2px !important;
        min-height: 2.2rem !important;
    }

    /* Inactive (Secondary) Navigation Button */
    div[data-testid="stSidebar"] div[data-testid="stButton"] > button[data-testid="baseButton-secondary"] {
        background-color: transparent !important;
        color: #475569 !important; /* slate-600 */
        border: 1px solid transparent !important;
    }

    /* Active (Primary) Navigation Button */
    div[data-testid="stSidebar"] div[data-testid="stButton"] > button[data-testid="baseButton-primary"] {
        background-color: #2563eb !important; /* Premium blue */
        color: #ffffff !important;
        font-weight: 600 !important;
        border: 1px solid #2563eb !important;
        box-shadow: 0 4px 6px -1px rgba(37, 99, 235, 0.15) !important;
    }

    /* Hover for Inactive (Secondary) Navigation Button */
    div[data-testid="stSidebar"] div[data-testid="stButton"] > button[data-testid="baseButton-secondary"]:hover {
        background-color: #f1f5f9 !important; /* slate-100 */
        color: #1e293b !important; /* slate-800 */
        border-color: #e2e8f0 !important;
    }

    /* Hover for Active Navigation Button */
    div[data-testid="stSidebar"] div[data-testid="stButton"] > button[data-testid="baseButton-primary"]:hover {
        background-color: #1d4ed8 !important;
        border-color: #1d4ed8 !important;
        color: #ffffff !important;
    }

    /* Reset button styles inside expanders (like Login form) to look standard */
    div[data-testid="stSidebar"] [data-testid="stExpander"] div[data-testid="stButton"] > button {
        justify-content: center !important;
        text-align: center !important;
    }

    /* Style open expander dropdown panel with darker soft grey bg */
    details[data-testid="stExpander"][open],
    div[data-testid="stExpander"]:has(details[open]) {
        background-color: #f1f5f9 !important; /* Soft premium grey */
        border: 1px solid #cbd5e1 !important;
        border-radius: 8px !important;
    }

    /* White background for input fields inside expander panels */
    div[data-testid="stExpander"] div[data-baseweb="select"] > div,
    div[data-testid="stExpander"] div[data-baseweb="input"] > div,
    div[data-testid="stExpander"] div[role="combobox"] {
        background-color: #ffffff !important;
    }
    </style>
""", unsafe_allow_html=True)

JIRA_DOMAIN = "epsilon-singularlogic.atlassian.net"

def format_to_hhmm(minutes):
    if pd.isna(minutes) or minutes <= 0: return "00:00"
    hours = int(minutes // 60)
    mins = int(minutes % 60)
    return f"{hours:02d}:{mins:02d}"

# --- 2. SQL Server Connection & Helper Functions ---

def get_db_engine():
    if "CONNECTION_STRING" not in st.secrets:
        return None
    conn_str = st.secrets["CONNECTION_STRING"]
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
        return None
        
    import urllib.parse
    from sqlalchemy import create_engine
    
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
            with engine.connect() as conn:
                pass
                
            # Ensure IsDefault column exists in User_Presets table
            try:
                with engine.begin() as conn:
                    conn.exec_driver_sql(
                        "IF COL_LENGTH('User_Presets', 'IsDefault') IS NULL "
                        "ALTER TABLE User_Presets ADD IsDefault BIT NOT NULL DEFAULT 0;"
                    )
            except Exception:
                pass
                
            # Ensure TargetApps column exists in ContentHub table
            try:
                with engine.begin() as conn:
                    conn.exec_driver_sql(
                        "IF COL_LENGTH('ContentHub', 'TargetApps') IS NULL "
                        "ALTER TABLE ContentHub ADD TargetApps NVARCHAR(255) NULL;"
                    )
            except Exception:
                pass

            # Ensure TargetApps column exists in KBArticles table
            try:
                with engine.begin() as conn:
                    conn.exec_driver_sql(
                        "IF COL_LENGTH('KBArticles', 'TargetApps') IS NULL "
                        "ALTER TABLE KBArticles ADD TargetApps NVARCHAR(255) NULL;"
                    )
            except Exception:
                pass

            # Ensure AppPreferences column exists in Users table
            try:
                with engine.begin() as conn:
                    conn.exec_driver_sql(
                        "IF COL_LENGTH('Users', 'AppPreferences') IS NULL "
                        "ALTER TABLE Users ADD AppPreferences NVARCHAR(255) NULL;"
                    )
            except Exception:
                pass
                
            # Ensure ETL_Queue table exists in database
            try:
                with engine.begin() as conn:
                    conn.exec_driver_sql(
                        "IF OBJECT_ID('ETL_Queue', 'U') IS NULL "
                        "BEGIN "
                        "    CREATE TABLE ETL_Queue ( "
                        "        JobID INT IDENTITY(1,1) PRIMARY KEY, "
                        "        JobType VARCHAR(50) NOT NULL, "
                        "        IssueKey VARCHAR(50) NULL, "
                        "        StartDate VARCHAR(50) NULL, "
                        "        EndDate VARCHAR(50) NULL, "
                        "        DateFilterType VARCHAR(20) NULL, "
                        "        Status VARCHAR(20) NOT NULL, "
                        "        CreatedBy VARCHAR(100) NOT NULL, "
                        "        CreatedAt DATETIME DEFAULT GETDATE(), "
                        "        StartedAt DATETIME NULL, "
                        "        FinishedAt DATETIME NULL, "
                        "        LogFilePath NVARCHAR(255) NULL "
                        "    ); "
                        "END"
                    )
            except Exception:
                pass
            # Ensure System_Logs table exists
            try:
                with engine.begin() as conn:
                    conn.exec_driver_sql(
                        "IF OBJECT_ID('System_Logs', 'U') IS NULL "
                        "CREATE TABLE System_Logs ("
                        "   LogID INT IDENTITY(1,1) PRIMARY KEY,"
                        "   UserID INT NOT NULL,"
                        "   Action NVARCHAR(100) NOT NULL,"
                        "   Details NVARCHAR(MAX) NOT NULL,"
                        "   CreatedAt DATETIME DEFAULT GETDATE(),"
                        "   CONSTRAINT FK_SystemLogs_Users FOREIGN KEY (UserID) REFERENCES Users(UserID)"
                        ");"
                    )
            except Exception:
                pass
                
            return engine
        except Exception:
            pass
    return None

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()

def verify_user_credentials(username: str, password_plain: str):
    engine = get_db_engine()
    if not engine:
        return None
    pwd_hash = hash_password(password_plain)
    from sqlalchemy import text
    try:
        with engine.connect() as conn:
            query = text(
                "SELECT u.UserID, u.Username, u.Email, u.RoleID, u.DefaultProject, u.DisplayName, r.RoleName, u.AppPreferences "
                "FROM Users u "
                "JOIN User_Roles r ON u.RoleID = r.RoleID "
                "WHERE u.Username = :username AND u.PasswordHash = :pwd_hash AND u.IsActive = 1"
            )
            res = conn.execute(query, {"username": username, "pwd_hash": pwd_hash}).fetchone()
            if res:
                return {
                    "UserID": res[0],
                    "Username": res[1],
                    "Email": res[2],
                    "RoleID": res[3],
                    "DefaultProject": res[4],
                    "DisplayName": res[5],
                    "RoleName": res[6],
                    "AppPreferences": res[7]
                }
    except Exception as e:
        st.error(f"Σφάλμα κατά την ταυτοποίηση: {e}")
    return None

def create_user_session(user_id: int) -> str:
    engine = get_db_engine()
    if not engine:
        return ""
    import uuid
    from datetime import timedelta
    session_token = str(uuid.uuid4())
    expires_at = datetime.now() + timedelta(days=30)
    from sqlalchemy import text
    try:
        with engine.begin() as conn:
            conn.execute(
                text("INSERT INTO User_Sessions (SessionID, UserID, ExpiresAt) VALUES (:token, :user_id, :expires)"),
                {"token": session_token, "user_id": user_id, "expires": expires_at}
            )
        return session_token
    except Exception as e:
        st.error(f"Σφάλμα κατά τη δημιουργία συνεδρίας: {e}")
        return ""

def verify_user_session(session_token: str):
    engine = get_db_engine()
    if not engine:
        return None
    from sqlalchemy import text
    try:
        with engine.connect() as conn:
            query = text(
                "SELECT u.UserID, u.Username, u.Email, u.RoleID, u.DefaultProject, u.DisplayName, r.RoleName, u.AppPreferences "
                "FROM User_Sessions s "
                "JOIN Users u ON s.UserID = u.UserID "
                "JOIN User_Roles r ON u.RoleID = r.RoleID "
                "WHERE s.SessionID = :token AND s.ExpiresAt > :now AND u.IsActive = 1"
            )
            res = conn.execute(query, {"token": session_token, "now": datetime.now()}).fetchone()
            if res:
                return {
                    "UserID": res[0],
                    "Username": res[1],
                    "Email": res[2],
                    "RoleID": res[3],
                    "DefaultProject": res[4],
                    "DisplayName": res[5],
                    "RoleName": res[6],
                    "AppPreferences": res[7]
                }
    except Exception:
        pass
    return None

def delete_user_session(session_token: str):
    engine = get_db_engine()
    if not engine:
        return
    from sqlalchemy import text
    try:
        with engine.begin() as conn:
            conn.execute(
                text("DELETE FROM User_Sessions WHERE SessionID = :token"),
                {"token": session_token}
            )
    except Exception:
        pass

def load_user_presets(user_id):
    engine = get_db_engine()
    if not engine:
        return []
    from sqlalchemy import text
    try:
        with engine.connect() as conn:
            query = text("SELECT PresetID, PresetName, FiltersJSON, IsDefault FROM User_Presets WHERE UserID = :user_id ORDER BY CreatedAt DESC")
            res = conn.execute(query, {"user_id": user_id}).fetchall()
            return [{"PresetID": r[0], "PresetName": r[1], "FiltersJSON": r[2], "IsDefault": r[3]} for r in res]
    except Exception:
        return []

def save_user_preset(user_id, preset_name, filters_json):
    engine = get_db_engine()
    if not engine:
        return False
    from sqlalchemy import text
    try:
        with engine.begin() as conn:
            conn.execute(
                text("INSERT INTO User_Presets (UserID, PresetName, FiltersJSON) VALUES (:user_id, :name, :json)"),
                {"user_id": user_id, "name": preset_name, "json": filters_json}
            )
        return True
    except Exception as e:
        st.error(f"Σφάλμα αποθήκευσης preview: {e}")
        return False

def update_user_preset(user_id, preset_name, filters_json):
    engine = get_db_engine()
    if not engine:
        return False
    from sqlalchemy import text
    try:
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE User_Presets SET FiltersJSON = :json WHERE UserID = :user_id AND PresetName = :name"),
                {"user_id": user_id, "name": preset_name, "json": filters_json}
            )
        return True
    except Exception as e:
        st.error(f"Σφάλμα ενημέρωσης preview: {e}")
        return False

def get_user_default_preset(user_id, type_keyword="proj_key"):
    engine = get_db_engine()
    if not engine:
        return None
    from sqlalchemy import text
    try:
        with engine.connect() as conn:
            query = text("SELECT PresetName, FiltersJSON FROM User_Presets WHERE UserID = :user_id AND IsDefault = 1 AND FiltersJSON LIKE :keyword")
            res = conn.execute(query, {"user_id": user_id, "keyword": f"%{type_keyword}%"}).fetchone()
            if res:
                return {"PresetName": res[0], "FiltersJSON": res[1]}
    except Exception:
        pass
    return None

def set_preset_as_default(user_id, preset_name, type_keyword="proj_key"):
    engine = get_db_engine()
    if not engine:
        return False
    from sqlalchemy import text
    try:
        with engine.begin() as conn:
            # 1. Clear IsDefault for presets of the same type for this user
            conn.execute(
                text("UPDATE User_Presets SET IsDefault = 0 WHERE UserID = :user_id AND FiltersJSON LIKE :keyword"),
                {"user_id": user_id, "keyword": f"%{type_keyword}%"}
            )
            # 2. Set IsDefault = 1 for the selected preset
            conn.execute(
                text("UPDATE User_Presets SET IsDefault = 1 WHERE UserID = :user_id AND PresetName = :name"),
                {"user_id": user_id, "name": preset_name}
            )
        return True
    except Exception as e:
        st.error(f"Σφάλμα ορισμού προεπιλογής: {e}")
        return False

def load_all_active_users():
    engine = get_db_engine()
    if not engine:
        return []
    from sqlalchemy import text
    try:
        with engine.connect() as conn:
            query = text("SELECT UserID, Username, Email, DisplayName FROM Users WHERE IsActive = 1 ORDER BY Username")
            res = conn.execute(query).fetchall()
            return [{"UserID": r[0], "Username": r[1], "Email": r[2], "DisplayName": r[3]} for r in res]
    except Exception:
        return []

def apply_preset_filters(filters_json):
    import json
    try:
        filters = json.loads(filters_json)
        if "proj_key" in filters:
            st.session_state["proj_key"] = filters["proj_key"]
        if "auth_key" in filters:
            st.session_state["auth_key"] = filters["auth_key"]
        if "charge_key" in filters:
            st.session_state["charge_key"] = filters["charge_key"]
        if "time_key" in filters:
            st.session_state["time_key"] = filters["time_key"]
        if "partner_key" in filters:
            st.session_state["partner_key"] = filters["partner_key"]
        if "lsp_key" in filters:
            st.session_state["lsp_key"] = filters["lsp_key"]
        if "comp_key" in filters:
            st.session_state["comp_key"] = filters["comp_key"]
        if "dates_key" in filters:
            st.session_state["dates_key"] = [pd.to_datetime(d).date() for d in filters["dates_key"]]
        if "group_key" in filters:
            st.session_state["group_key"] = filters["group_key"]
        st.session_state["filters_init"] = True
        
        # Keep the backup in sync
        st.session_state["widget_backup"] = {
            "proj_key": st.session_state.get("proj_key"),
            "auth_key": st.session_state.get("auth_key"),
            "charge_key": st.session_state.get("charge_key"),
            "time_key": st.session_state.get("time_key"),
            "partner_key": st.session_state.get("partner_key"),
            "lsp_key": st.session_state.get("lsp_key"),
            "comp_key": st.session_state.get("comp_key"),
            "dates_key": st.session_state.get("dates_key"),
            "group_key": st.session_state.get("group_key"),
            "group_filter_selectbox_key": st.session_state.get("group_filter_selectbox_key"),
        }
    except Exception as e:
        st.error(f"Σφάλμα εφαρμογής preview: {e}")

def get_cookie_signature(session_token: str) -> str:
    import hmac
    secret_key = hashlib.sha256(st.secrets.get("CONNECTION_STRING", "fallback-secret").encode("utf-8")).hexdigest()
    return hmac.new(secret_key.encode("utf-8"), session_token.encode("utf-8"), hashlib.sha256).hexdigest()

def set_cookie(name: str, value: str, ttl_days: int = 30, trigger_reload: bool = False):
    import streamlit.components.v1 as components
    reload_js = "window.parent.location.reload();" if trigger_reload else ""
    components.html(
        f"""
        <script>
            var date = new Date();
            date.setTime(date.getTime() + ({ttl_days}*24*60*60*1000));
            var expires = "; expires=" + date.toUTCString();
            document.cookie = "{name}=" + encodeURIComponent("{value}") + expires + "; path=/; SameSite=Lax";
            {reload_js}
        </script>
        """,
        height=0,
    )

def erase_cookie(name: str, trigger_reload: bool = False):
    import streamlit.components.v1 as components
    reload_js = "window.parent.location.reload();" if trigger_reload else ""
    components.html(
        f"""
        <script>
            document.cookie = "{name}=; Max-Age=0; path=/; SameSite=Lax";
            {reload_js}
        </script>
        """,
        height=0,
    )


def load_groups_from_db():
    engine = get_db_engine()
    if not engine:
        return []
    from sqlalchemy import text
    try:
        with engine.connect() as conn:
            res = conn.execute(text("SELECT GroupID, GroupName FROM User_Groups ORDER BY GroupName")).fetchall()
            return [{"GroupID": r[0], "GroupName": r[1]} for r in res]
    except Exception:
        return []

def load_group_members(group_id):
    engine = get_db_engine()
    if not engine:
        return []
    from sqlalchemy import text
    try:
        with engine.connect() as conn:
            query = text(
                "SELECT u.DisplayName FROM User_Group_Memberships m "
                "JOIN Users u ON m.UserID = u.UserID "
                "WHERE m.GroupID = :group_id AND u.IsActive = 1"
            )
            res = conn.execute(query, {"group_id": group_id}).fetchall()
            return [r[0] for r in res if r[0]]
    except Exception:
        return []

def update_user_default_project(user_id, project_name):
    engine = get_db_engine()
    if not engine:
        return False
    from sqlalchemy import text
    try:
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE Users SET DefaultProject = :proj WHERE UserID = :user_id"),
                {"proj": project_name, "user_id": user_id}
            )
        return True
    except Exception as e:
        st.error(f"Σφάλμα: {e}")
        return False

def update_user_app_preferences(user_id, app_preferences_str):
    engine = get_db_engine()
    if not engine:
        return False
    from sqlalchemy import text
    try:
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE Users SET AppPreferences = :prefs WHERE UserID = :user_id"),
                {"prefs": app_preferences_str, "user_id": user_id}
            )
        return True
    except Exception as e:
        st.error(f"Σφάλμα: {e}")
        return False

def update_user_password(user_id, new_password_plain):
    engine = get_db_engine()
    if not engine:
        return False
    from sqlalchemy import text
    try:
        pwd_hash = hash_password(new_password_plain)
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE Users SET PasswordHash = :hash WHERE UserID = :user_id"),
                {"hash": pwd_hash, "user_id": user_id}
            )
        return True
    except Exception as e:
        st.error(f"Σφάλμα: {e}")
        return False

def search_jira_user_by_email(email):
    if "JIRA_JWT_TOKEN" not in st.secrets:
        return ""
    api_token = st.secrets["JIRA_JWT_TOKEN"]
    jira_cloud_id = "58c421e1-1855-4c95-8c07-df2d79817fdd"
    url = f"https://api.atlassian.com/ex/jira/{jira_cloud_id}/rest/api/3/user/search"
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {api_token}"
    }
    params = {
        "query": email
    }
    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        if response.ok:
            users = response.json()
            if users:
                return users[0].get("displayName", "")
    except Exception:
        pass
    return ""

def register_new_user(username, password_plain, email, role_id, display_name=None):
    engine = get_db_engine()
    if not engine:
        return False
    from sqlalchemy import text
    try:
        pwd_hash = hash_password(password_plain)
        with engine.begin() as conn:
            conn.execute(
                text("INSERT INTO Users (Username, PasswordHash, Email, RoleID, IsActive, DisplayName) "
                     "VALUES (:username, :pwd_hash, :email, :role_id, 1, :disp_name)"),
                {
                    "username": username,
                    "pwd_hash": pwd_hash,
                    "email": email,
                    "role_id": role_id,
                    "disp_name": display_name
                }
            )
        return True
    except Exception as e:
        st.error(f"Σφάλμα: {e}")
        return False

def load_all_users_admin():
    engine = get_db_engine()
    if not engine:
        return []
    from sqlalchemy import text
    try:
        with engine.connect() as conn:
            query = text(
                "SELECT u.UserID, u.Username, u.Email, u.RoleID, u.DisplayName, u.IsActive, u.CreatedAt, r.RoleName "
                "FROM Users u "
                "JOIN User_Roles r ON u.RoleID = r.RoleID "
                "ORDER BY u.Username"
            )
            res = conn.execute(query).fetchall()
            return [{
                "UserID": r[0],
                "Username": r[1],
                "Email": r[2],
                "RoleID": r[3],
                "DisplayName": r[4],
                "IsActive": bool(r[5]),
                "CreatedAt": r[6],
                "RoleName": r[7]
            } for r in res]
    except Exception:
        return []

def admin_update_user_status(user_id, is_active):
    engine = get_db_engine()
    if not engine:
        return False
    from sqlalchemy import text
    try:
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE Users SET IsActive = :active WHERE UserID = :user_id"),
                {"active": 1 if is_active else 0, "user_id": user_id}
            )
        return True
    except Exception as e:
        st.error(f"Σφάλμα κατά την ενημέρωση κατάστασης χρήστη: {e}")
        return False

def admin_update_user_role(user_id, role_id):
    engine = get_db_engine()
    if not engine:
        return False
    from sqlalchemy import text
    try:
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE Users SET RoleID = :role_id WHERE UserID = :user_id"),
                {"role_id": role_id, "user_id": user_id}
            )
        return True
    except Exception as e:
        st.error(f"Σφάλμα κατά την ενημέρωση ρόλου χρήστη: {e}")
        return False


def admin_reset_user_password(user_id, default_password_plain):
    engine = get_db_engine()
    if not engine:
        return False
    from sqlalchemy import text
    try:
        pwd_hash = hash_password(default_password_plain)
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE Users SET PasswordHash = :hash WHERE UserID = :user_id"),
                {"hash": pwd_hash, "user_id": user_id}
            )
        return True
    except Exception as e:
        st.error(f"Σφάλμα κατά την επαναφορά κωδικού: {e}")
        return False

def delete_all_user_sessions(user_id):
    engine = get_db_engine()
    if not engine:
        return
    from sqlalchemy import text
    try:
        with engine.begin() as conn:
            conn.execute(
                text("DELETE FROM User_Sessions WHERE UserID = :user_id"),
                {"user_id": user_id}
            )
    except Exception:
        pass

def write_system_log(user_id, action, details):
    engine = get_db_engine()
    if not engine:
        return
    from sqlalchemy import text
    try:
        with engine.begin() as conn:
            conn.execute(
                text("INSERT INTO System_Logs (UserID, Action, Details) VALUES (:user_id, :action, :details)"),
                {"user_id": user_id, "action": action, "details": details}
            )
    except Exception:
        pass

def create_new_group_with_members(group_name, member_ids):
    engine = get_db_engine()
    if not engine:
        return False
    from sqlalchemy import text
    try:
        with engine.begin() as conn:
            conn.execute(
                text("INSERT INTO User_Groups (GroupName) VALUES (:name)"),
                {"name": group_name}
            )
            res = conn.execute(text("SELECT GroupID FROM User_Groups WHERE GroupName = :name"), {"name": group_name}).fetchone()
            if res:
                group_id = res[0]
                for user_id in member_ids:
                    conn.execute(
                        text("INSERT INTO User_Group_Memberships (UserID, GroupID) VALUES (:uid, :gid)"),
                        {"uid": user_id, "gid": group_id}
                    )
        return True
    except Exception as e:
        st.error(f"Σφάλμα: {e}")
        return False

def update_group_with_members(group_id, group_name, member_ids):
    engine = get_db_engine()
    if not engine:
        return False
    from sqlalchemy import text
    try:
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE User_Groups SET GroupName = :name WHERE GroupID = :group_id"),
                {"name": group_name, "group_id": group_id}
            )
            conn.execute(
                text("DELETE FROM User_Group_Memberships WHERE GroupID = :group_id"),
                {"group_id": group_id}
            )
            for user_id in member_ids:
                conn.execute(
                    text("INSERT INTO User_Group_Memberships (UserID, GroupID) VALUES (:uid, :gid)"),
                    {"uid": user_id, "gid": group_id}
                )
        return True
    except Exception as e:
        st.error(f"Σφάλμα: {e}")
        return False

def delete_group(group_id):
    engine = get_db_engine()
    if not engine:
        return False
    from sqlalchemy import text
    try:
        with engine.begin() as conn:
            conn.execute(
                text("DELETE FROM User_Group_Memberships WHERE GroupID = :group_id"),
                {"group_id": group_id}
            )
            conn.execute(
                text("DELETE FROM User_Groups WHERE GroupID = :group_id"),
                {"group_id": group_id}
            )
        return True
    except Exception as e:
        st.error(f"Σφάλμα: {e}")
        return False
    
# --- ContentHub Helpers (Announcements & Pro Tips) ---
def load_latest_content(content_type):
    engine = get_db_engine()
    if not engine: return None
    from sqlalchemy import text
    try:
        with engine.connect() as conn:
            query = text("""
                SELECT c.Title, c.Body, c.CreatedAt, c.TargetApps, COALESCE(u.DisplayName, u.Username, 'Άγνωστος') AS Author 
                FROM ContentHub c
                LEFT JOIN Users u ON c.UserID = u.UserID
                WHERE c.ContentType = :ctype AND c.IsActive = 1 ORDER BY c.CreatedAt DESC
            """)
            res = conn.execute(query, {"ctype": content_type}).fetchall()
            for r in res:
                if is_content_visible(r[3]):
                    return {"Title": r[0], "Body": r[1], "CreatedAt": r[2], "Author": r[4]}
            return None
    except Exception: return None

def load_all_content_admin():
    engine = get_db_engine()
    if not engine: return []
    from sqlalchemy import text
    try:
        with engine.connect() as conn:
            query = text("""
                SELECT c.ContentID, c.Title, c.Body, c.ContentType, c.IsActive, c.TargetApps, COALESCE(u.DisplayName, u.Username, 'Άγνωστος') AS Author
                FROM ContentHub c
                LEFT JOIN Users u ON c.UserID = u.UserID
                ORDER BY c.CreatedAt DESC
            """)
            res = conn.execute(query).fetchall()
            return [{"ContentID": r[0], "Title": r[1], "Body": r[2], "ContentType": r[3], "IsActive": bool(r[4]), "TargetApps": r[5], "Author": r[6]} for r in res]
    except Exception: return []

def save_content_item(title, body, content_type, user_id, target_apps=None):
    engine = get_db_engine()
    if not engine: return False
    from sqlalchemy import text
    try:
        with engine.begin() as conn:
            conn.execute(
                text("INSERT INTO ContentHub (Title, Body, ContentType, UserID, TargetApps) VALUES (:title, :body, :ctype, :uid, :tapps)"),
                {"title": title, "body": body, "ctype": content_type, "uid": user_id, "tapps": target_apps}
            )
        return True
    except Exception: return False

def update_content_item(content_id, title, body, content_type, is_active, target_apps=None):
    engine = get_db_engine()
    if not engine: return False
    from sqlalchemy import text
    try:
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE ContentHub SET Title = :title, Body = :body, ContentType = :ctype, IsActive = :active, TargetApps = :tapps WHERE ContentID = :cid"),
                {"title": title, "body": body, "ctype": content_type, "active": 1 if is_active else 0, "tapps": target_apps, "cid": content_id}
            )
        return True
    except Exception: return False

def delete_content_item(content_id):
    engine = get_db_engine()
    if not engine: return False
    from sqlalchemy import text
    try:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM ContentHub WHERE ContentID = :cid"), {"cid": content_id})
        return True
    except Exception: return False


# --- Knowledge Base Helpers ---
def load_kb_articles(only_active=True):
    engine = get_db_engine()
    if not engine: return []
    from sqlalchemy import text
    try:
        with engine.connect() as conn:
            sql = """
                SELECT k.ArticleID, k.Title, k.Category, k.Content, k.IsActive, k.TargetApps, COALESCE(u.DisplayName, u.Username, 'Άγνωστος') AS Author
                FROM KBArticles k
                LEFT JOIN Users u ON k.UserID = u.UserID
            """
            if only_active: sql += " WHERE k.IsActive = 1"
            sql += " ORDER BY k.Category, k.CreatedAt DESC"
            res = conn.execute(text(sql)).fetchall()
            return [{"ArticleID": r[0], "Title": r[1], "Category": r[2], "Content": r[3], "IsActive": bool(r[4]), "TargetApps": r[5], "Author": r[6]} for r in res]
    except Exception: return []

def save_kb_article(title, category, content, user_id, target_apps=None):
    engine = get_db_engine()
    if not engine: return False
    from sqlalchemy import text
    try:
        with engine.begin() as conn:
            conn.execute(
                text("INSERT INTO KBArticles (Title, Category, Content, UserID, TargetApps) VALUES (:title, :cat, :content, :uid, :tapps)"),
                {"title": title, "cat": category, "content": content, "uid": user_id, "tapps": target_apps}
            )
        return True
    except Exception: return False

def update_kb_article(article_id, title, category, content, is_active, target_apps=None):
    engine = get_db_engine()
    if not engine: return False
    from sqlalchemy import text
    try:
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE KBArticles SET Title = :title, Category = :cat, Content = :content, IsActive = :active, TargetApps = :tapps WHERE ArticleID = :aid"),
                {"title": title, "cat": category, "content": content, "active": 1 if is_active else 0, "tapps": target_apps, "aid": article_id}
            )
        return True
    except Exception: return False

def delete_kb_article(article_id):
    engine = get_db_engine()
    if not engine: return False
    from sqlalchemy import text
    try:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM KBArticles WHERE ArticleID = :aid"), {"aid": article_id})
        return True
    except Exception: return False

# --- Response Times DB Configuration & Helpers ---
RT_DB_SERVER = os.getenv("DB_SERVER", "dev-gemini")
RT_DB_NAME = os.getenv("DB_NAME", "GeminiMetricsDemo")
RT_DB_USER = os.getenv("DB_USER", "supportappl")
RT_DB_PASSWORD = os.getenv("DB_PASSWORD", "Meq4HAR%")
RT_DB_DRIVER = os.getenv("DB_DRIVER", "ODBC Driver 17 for SQL Server")

def rt_get_connection():
    conn_str = (
        f"DRIVER={{{RT_DB_DRIVER}}};"
        f"SERVER={RT_DB_SERVER};"
        f"DATABASE={RT_DB_NAME};"
        f"UID={RT_DB_USER};"
        f"PWD={RT_DB_PASSWORD};"
        "TrustServerCertificate=yes;"
    )
    return pyodbc.connect(conn_str)

def rt_load_from_db():
    conn = rt_get_connection()
    query = """
    SELECT 
        i.ProjectId,
        i.IssueId,
        i.IssueKey,
        i.CreationDate,
        i.Status,
        i.ClosedDate,
        i.Type,
        i.Components,
        i.Resources,
        u.Fullname AS [AssigneeName],
        cf_cat.FieldValue AS [SubCategory],
        cf_part.FieldValue AS [PartnerName],    -- Join 1 για Partner
        cf_cust.FieldValue AS [CustomerName]     -- Join 2 για Customer
    FROM dbo.GIssues i WITH (NOLOCK)
    
    -- Join για το όνομα του Assignee
    LEFT JOIN dbo.GUsers u WITH (NOLOCK) ON i.Assignee = u.UserID AND i.SourceApp = u.SourceApp
        
    -- Join για το SubCategory
    LEFT JOIN dbo.GIssueCustomFields cf_cat WITH (NOLOCK)
        ON i.IssueID = cf_cat.IssueID 
        AND cf_cat.CustomFieldName LIKE '%category%'
        AND cf_cat.SourceApp = i.SourceApp
        
    -- Join για το Partner Name
    LEFT JOIN dbo.GIssueCustomFields cf_part WITH (NOLOCK)
        ON i.IssueID = cf_part.IssueID 
        AND cf_part.CustomFieldName = 'Partner Name'
        AND cf_part.SourceApp = i.SourceApp
        
    -- Join για το Customer Name
    LEFT JOIN dbo.GIssueCustomFields cf_cust WITH (NOLOCK)
        ON i.IssueID = cf_cust.IssueID 
        AND cf_cust.CustomFieldName = 'LSP Customer Name'
        AND cf_cust.SourceApp = i.SourceApp
        
    WHERE i.Type = 'Epic' AND i.SourceApp = 'Jira'
    """
    try:
        df_res = pd.read_sql(query, conn)
        return df_res
    finally:
        conn.close()

def rt_load_first_response():
    conn = rt_get_connection()
    query = """
    SELECT 
        IssueID,
        -- Πρώτη απάντηση από τον External Account
        MIN(CASE WHEN Fullname = 'ExternalCommunicationAccount' THEN Created ELSE NULL END) AS FirstExternalResponseDate,
        
        -- Πρώτη απάντηση από οποιονδήποτε άλλον
        MIN(CASE WHEN Fullname <> 'ExternalCommunicationAccount' THEN Created ELSE NULL END) AS FirstInternalResponseDate
    FROM dbo.GComments WITH (NOLOCK)
    WHERE SourceApp = 'Jira'
    GROUP BY IssueID
    """
    try:
        df_res = pd.read_sql(query, conn)
        return df_res
    finally:
        conn.close()

def rt_load_first_assigned():
    conn = rt_get_connection()
    query = """
    SELECT
        IssueID,
        MIN(Created) AS FirstAssignedDate
    FROM dbo.GAudit WITH (NOLOCK)
    WHERE fieldname = 'Assignee'
      AND newvalue IS NOT NULL
      AND SourceApp = 'Jira'
    GROUP BY IssueID
    """
    try:
        df_res = pd.read_sql(query, conn)
        return df_res
    finally:
        conn.close()

def rt_load_status_change_date():
    conn = rt_get_connection()
    query = """
    SELECT 
        IssueID,
        MIN(Created) AS FirstInProgressDate
    FROM dbo.GAudit WITH (NOLOCK)
    WHERE FieldName = 'status' 
      AND (NewValue = 'In Progress' OR NewValue = 'In progress' OR NewValue = 'IN PROGRESS')
      AND SourceApp = 'Jira'
    GROUP BY IssueID
    """
    try:
        df_res = pd.read_sql(query, conn)
        return df_res
    finally:
        conn.close()

def rt_load_awaiting_customer_end_date():
    conn = rt_get_connection()
    query = """
    WITH RawTransitions AS (
        SELECT 
            IssueID,
            Created AS EventDate,
            NewValue AS Status,
            ROW_NUMBER() OVER (PARTITION BY IssueID ORDER BY Created) AS rn
        FROM dbo.GAudit WITH (NOLOCK)
        WHERE FieldName = 'status' AND SourceApp = 'Jira'
    ),
    AwaitingPairs AS (
        SELECT 
            curr.IssueID,
            curr.EventDate AS StartTime,
            next.EventDate AS EndTime,
            ROW_NUMBER() OVER (PARTITION BY curr.IssueID ORDER BY curr.EventDate) AS PeriodNum
        FROM RawTransitions curr WITH (NOLOCK)
        JOIN RawTransitions next WITH (NOLOCK) ON curr.IssueID = next.IssueID AND next.rn = curr.rn + 1
        WHERE curr.Status = 'AWAITING CUSTOMER'
    )
    SELECT 
        IssueID,
        MAX(CASE WHEN PeriodNum = 1 THEN StartTime END) AS Start1,
        MAX(CASE WHEN PeriodNum = 1 THEN EndTime END) AS End1,
        MAX(CASE WHEN PeriodNum = 2 THEN StartTime END) AS Start2,
        MAX(CASE WHEN PeriodNum = 2 THEN EndTime END) AS End2,
        MAX(CASE WHEN PeriodNum = 3 THEN StartTime END) AS Start3,
        MAX(CASE WHEN PeriodNum = 3 THEN EndTime END) AS End3,
        MAX(CASE WHEN PeriodNum = 4 THEN StartTime END) AS Start4,
        MAX(CASE WHEN PeriodNum = 4 THEN EndTime END) AS End4,
        MAX(CASE WHEN PeriodNum = 5 THEN StartTime END) AS Start5,
        MAX(CASE WHEN PeriodNum = 5 THEN EndTime END) AS End5,
        MAX(CASE WHEN PeriodNum = 6 THEN StartTime END) AS Start6,
        MAX(CASE WHEN PeriodNum = 6 THEN EndTime END) AS End6
    FROM AwaitingPairs WITH (NOLOCK)
    GROUP BY IssueID
    """
    try:
        df_res = pd.read_sql(query, conn)
        return df_res
    finally:
        conn.close()

def rt_convert_df_to_excel(df_res):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df_res.to_excel(writer, index=False, sheet_name="KPIs")
    return output.getvalue()

def rt_safe_mean(series):
    return round(series.mean(), 2) if not series.dropna().empty else 0

# --- 3. Φόρτωση από Βάση Δεδομένων ---

@st.cache_data(ttl=60) # Cache για 1 λεπτό
def load_data_from_db():
    try:
        engine = get_db_engine()
        if engine is None:
            st.error("❌ Αποτυχία σύνδεσης στον SQL Server.")
            return pd.DataFrame(), "Ποτέ"
            
        # Φόρτωση από τον SQL Server
        df = pd.read_sql("SELECT * FROM WorkLogs", engine)
        
        
# �Μετονομασία στηλών πίσω στη μορφή με κενά που περιμένει το UI
        df = df.rename(columns={
            "IssueKey": "Issue Key",
            "ParentKey": "Parent Key",
            "ParentTitle": "Parent Title",
            "Project": "Project",
            "Assignee": "Assignee",
            "TimeType": "Time Type",
            "ChargeType": "Charge Type",
            "Minutes": "Minutes",
            "WorkDate": "Date",
            "ParentCategory": "Parent Category",
            "Components": "Components",
            "PartnerName": "Partner Name",
            "LSPCustomerName": "LSP Customer Name"
        })
        
        # Μετατροπή της στήλης Date σε string μορφής YYYY-MM-DD
        if "Date" in df.columns:
            df["Date"] = pd.to_datetime(df["Date"]).dt.strftime('%Y-%m-%d')
            
        # Λήψη τελευταίας ημερομηνίας συγχρονισμού από Sync_Metadata
        last_updated = "Άγνωστο"
        try:
            with engine.connect() as conn:
                from sqlalchemy import text
                res = conn.execute(text("SELECT TOP 1 LastSyncDateTime FROM Sync_Metadata")).fetchone()
                if res and res[0]:
                    last_updated = res[0].strftime("%d/%m/%Y %H:%M")
                else:
                    last_updated = datetime.now().strftime("%d/%m/%Y %H:%M")
        except Exception:
            last_updated = datetime.now().strftime("%d/%m/%Y %H:%M")
            
        return df, last_updated
        
    except Exception as e:
        st.error(f"❌ Σφάλμα κατά τη φόρτωση των δεδομένων: {e}")
        return pd.DataFrame(), "Ποτέ"

df, last_updated = load_data_from_db()

if df.empty:
    st.warning("⚠️ Η Βάση Δεδομένων είναι άδεια ή δεν έχει δημιουργηθεί. Παρακαλώ τρέξτε το sync_db.py")
    st.stop()

# --- 4. SIDEBAR ---
        
        
# # --- Soft Login Section ---
# Auto-login check if not already logged in (reads signed cookie nss_session)
if not st.session_state.logged_in:
    cookie_val = st.context.cookies.get("nss_session")
    if cookie_val:
        import urllib.parse
        cookie_val = urllib.parse.unquote(cookie_val)
        try:
            if ":" in cookie_val:
                cookie_token, cookie_sig = cookie_val.split(":", 1)
                expected_sig = get_cookie_signature(cookie_token)
                import hmac
                if hmac.compare_digest(expected_sig, cookie_sig):
                    user = verify_user_session(cookie_token)
                    if user:
                        st.session_state.logged_in = True
                        st.session_state.user_id = user["UserID"]
                        st.session_state.username = user["Username"]
                        st.session_state.user_role = user["RoleName"]
                        st.session_state.display_name = user["DisplayName"]
                        st.session_state.default_project = user["DefaultProject"]
                        st.session_state.app_preferences = user.get("AppPreferences")
                        if "filters_init" in st.session_state:
                            del st.session_state["filters_init"]
                    else:
                        erase_cookie("nss_session", trigger_reload=False)
                else:
                    erase_cookie("nss_session", trigger_reload=False)
        except Exception:
            pass

st.sidebar.markdown('<h1 class="stHeadingSidebar">👤 Λογαριασμός</h1>', unsafe_allow_html=True)
if not st.session_state.logged_in:
    with st.sidebar.expander("🔑 Σύνδεση Χρήστη"):
        login_username = st.text_input("Username", key="sidebar_login_username")
        login_password = st.text_input("Password", type="password", key="sidebar_login_password")
        remember_me = st.checkbox("Να με θυμάσαι", key="login_remember_me")
        if st.button("Είσοδος", type="primary", width='stretch'):
            user = verify_user_credentials(login_username, login_password)
            if user:
                st.session_state.logged_in = True
                st.session_state.user_id = user["UserID"]
                st.session_state.username = user["Username"]
                st.session_state.user_role = user["RoleName"]
                st.session_state.display_name = user["DisplayName"]
                st.session_state.default_project = user["DefaultProject"]
                st.session_state.app_preferences = user.get("AppPreferences")
                if "filters_init" in st.session_state:
                    del st.session_state["filters_init"]
                
                # If remember_me is checked, generate token and set signed cookie
                if remember_me:
                    session_token = create_user_session(user["UserID"])
                    if session_token:
                        sig = get_cookie_signature(session_token)
                        set_cookie("nss_session", f"{session_token}:{sig}", trigger_reload=True)
                else:
                    st.toast(f"✅ Καλώς ήρθες, {user['Username']}!")
                    st.rerun()
            else:
                st.error("❌ Λάθος στοιχεία σύνδεσης")
else:
    st.sidebar.write(f"Συνδεδεμένος: **{st.session_state.display_name or st.session_state.username}**")
    st.sidebar.write(f"Ρόλος: `{st.session_state.user_role}`")
    
    if st.sidebar.button("Αποσύνδεση", type="secondary", width='stretch'):
        cookie_val = st.context.cookies.get("nss_session")
        if cookie_val:
            import urllib.parse
            cookie_val = urllib.parse.unquote(cookie_val)
            if ":" in cookie_val:
                cookie_token, _ = cookie_val.split(":", 1)
                delete_user_session(cookie_token)
        erase_cookie("nss_session", trigger_reload=True)
        
        st.session_state.logged_in = False
        st.session_state.username = None
        st.session_state.user_id = None
        st.session_state.user_role = None
        st.session_state.display_name = None
        st.session_state.default_project = None
        st.session_state.app_preferences = None
        if "active_app_view" in st.session_state:
            del st.session_state["active_app_view"]
        if "active_app_view_widget" in st.session_state:
            del st.session_state["active_app_view_widget"]
        if "filters_init" in st.session_state:
            del st.session_state["filters_init"]
        if "widget_backup" in st.session_state:
            del st.session_state["widget_backup"]
        st.toast("👋 Αποσυνδεθήκατε με επιτυχία.")

# --- Navigation Section in Sidebar ---
# Determine active selected page
if "selected_page" not in st.session_state:
    st.session_state.selected_page = "📊 Timesheet"

selected_page = st.session_state.selected_page

# Validate selection for role permissions
valid_pages = ["📊 Timesheet", "💡 Knowledge Base", "📢 Ανακοινώσεις & Tips", "📖 Οδηγίες Χρήσης"]
if st.session_state.logged_in:
    valid_pages.extend(["👤 Το Προφίλ μου"])
    if st.session_state.user_role in ["Administrator", "Team Leader", "ContentManager"]:
        valid_pages.extend(["👥 Διαχείριση Ομάδων", "⏱️ Χρόνοι Απόκρισης"])
    if st.session_state.user_role == "Administrator":
        valid_pages.append("🚀 ETL Manager")
    if st.session_state.user_role in ["Administrator", "ContentManager", "ContentCreator"]:
        valid_pages.append("🎓 ClassMarker")

if selected_page not in valid_pages:
    selected_page = "📊 Timesheet"
    st.session_state.selected_page = "📊 Timesheet"

# Helper function to render styled navigation buttons
def draw_nav_button(label, page_name):
    is_active = (selected_page == page_name)
    btn_type = "primary" if is_active else "secondary"
    if st.sidebar.button(label, key=f"nav_btn_{page_name}", type=btn_type, width='stretch'):
        st.session_state.selected_page = page_name
        st.rerun()

# 1. User Guide / Manual at the very top
st.sidebar.markdown('<div class="menu-section-header">📖 Οδηγός</div>', unsafe_allow_html=True)
draw_nav_button("📖 Οδηγίες Χρήσης", "📖 Οδηγίες Χρήσης")

# 2. Group: Χρόνοι & Metrics
st.sidebar.markdown('<div class="menu-section-header">⏱️ Χρόνοι & Metrics</div>', unsafe_allow_html=True)
draw_nav_button("📊 Timesheet", "📊 Timesheet")
if st.session_state.logged_in and st.session_state.user_role in ["Administrator", "Team Leader", "ContentManager"]:
    draw_nav_button("⏱️ Χρόνοι Απόκρισης", "⏱️ Χρόνοι Απόκρισης")

# 3. Group: Πιστοποιήσεις
if st.session_state.logged_in and st.session_state.user_role in ["Administrator", "ContentManager", "ContentCreator"]:
    st.sidebar.markdown('<div class="menu-section-header">🎓 Πιστοποιήσεις</div>', unsafe_allow_html=True)
    draw_nav_button("🎓 ClassMarker", "🎓 ClassMarker")

# 4. Group: Διαδικασίες & Ανακοινώσεις
st.sidebar.markdown('<div class="menu-section-header">📢 Διαδικασίες & Ανακοινώσεις</div>', unsafe_allow_html=True)
draw_nav_button("💡 Knowledge Base", "💡 Knowledge Base")
draw_nav_button("📢 Ανακοινώσεις & Tips", "📢 Ανακοινώσεις & Tips")

# 5. Group: Διαχείριση Λογαριασμού και Ομάδων
if st.session_state.logged_in:
    st.sidebar.markdown('<div class="menu-section-header">👤 Διαχείριση Λογαριασμού και Ομάδων</div>', unsafe_allow_html=True)
    draw_nav_button("👤 Το Προφίλ μου", "👤 Το Προφίλ μου")
    if st.session_state.user_role in ["Administrator", "Team Leader", "ContentManager"]:
        draw_nav_button("👥 Διαχείριση Ομάδων", "👥 Διαχείριση Ομάδων")
    if st.session_state.user_role == "Administrator":
        draw_nav_button("🚀 ETL Manager", "🚀 ETL Manager")
st.sidebar.write("---")
st.sidebar.markdown('<div class="menu-section-header">🖥️ Φιλτράρισμα Εφαρμογών</div>', unsafe_allow_html=True)

if "active_app_view" not in st.session_state:
    if st.session_state.logged_in:
        user_pref = st.session_state.get("app_preferences")
        if user_pref:
            st.session_state["active_app_view"] = [x.strip() for x in user_pref.split(",") if x.strip()]
        else:
            st.session_state["active_app_view"] = ["Galaxy", "Pylon"]
    else:
        st.session_state["active_app_view"] = ["Galaxy", "Pylon"]

st.sidebar.multiselect(
    "Εμφάνιση Περιεχομένου για:",
    options=["Galaxy", "Pylon"],
    key="active_app_view"
)

st.sidebar.write("---")
st.sidebar.caption(f"**App Version:** {APP_VERSION}")

# 1. INITIALIZATION: Θέτουμε τις αρχικές τιμές στα φίλτρα απευθείας στη μνήμη (παρακάμπτοντας το URL)
if "filters_init" not in st.session_state:
    all_proj = sorted([str(x) for x in df["Project"].dropna().unique()])
    all_auth = sorted([str(x) for x in df["Assignee"].dropna().unique()])
    all_charge = sorted([str(x) for x in df["Charge Type"].dropna().unique()])
    all_time = sorted([str(x) for x in df["Time Type"].dropna().unique()])
    all_partner = sorted([str(x) for x in df["Partner Name"].dropna().unique()]) if "Partner Name" in df.columns else []
    all_lsp = sorted([str(x) for x in df["LSP Customer Name"].dropna().unique()]) if "LSP Customer Name" in df.columns else []

    if "Parent Category" in df.columns:
        nested_comps = df["Parent Category"].dropna().apply(lambda x: [c.strip() for c in x.split(",")])
        all_comps_flat = set([item for sublist in nested_comps for item in sublist])
        all_comp = sorted(list(all_comps_flat))
    else:
        all_comp = []

    # Check for default preset first if user is logged in
    has_loaded_default_preset = False
    if st.session_state.logged_in:
        default_preset = get_user_default_preset(st.session_state.user_id)
        if default_preset:
            import json
            try:
                filters = json.loads(default_preset["FiltersJSON"])
                if "proj_key" in filters:
                    st.session_state["proj_key"] = filters["proj_key"]
                if "auth_key" in filters:
                    st.session_state["auth_key"] = filters["auth_key"]
                if "charge_key" in filters:
                    st.session_state["charge_key"] = filters["charge_key"]
                if "time_key" in filters:
                    st.session_state["time_key"] = filters["time_key"]
                if "partner_key" in filters:
                    st.session_state["partner_key"] = filters["partner_key"]
                if "lsp_key" in filters:
                    st.session_state["lsp_key"] = filters["lsp_key"]
                if "comp_key" in filters:
                    st.session_state["comp_key"] = filters["comp_key"]
                if "dates_key" in filters:
                    st.session_state["dates_key"] = [pd.to_datetime(d).date() for d in filters["dates_key"]]
                if "group_key" in filters:
                    st.session_state["group_key"] = filters["group_key"]
                
                st.session_state.active_preset_name = default_preset["PresetName"]
                st.session_state.active_preset_json = default_preset["FiltersJSON"]
                has_loaded_default_preset = True
            except Exception:
                pass

    if not has_loaded_default_preset:
        # Default project preselection from Profile
        default_proj_preselect = all_proj
        if st.session_state.logged_in and st.session_state.default_project:
            dp = st.session_state.default_project
            if dp in all_proj:
                default_proj_preselect = [dp]
        
        # Default assignee preselection:
        # If logged in, pre-select ONLY the logged-in user if their name matches any assignee
        default_auth_preselect = all_auth
        if st.session_state.logged_in:
            user_name_to_select = st.session_state.display_name or st.session_state.username
            if user_name_to_select in all_auth:
                default_auth_preselect = [user_name_to_select]

        st.session_state['proj_key'] = default_proj_preselect
        st.session_state['auth_key'] = default_auth_preselect
        st.session_state['charge_key'] = all_charge
        st.session_state['time_key'] = all_time
        st.session_state['partner_key'] = all_partner
        st.session_state['lsp_key'] = all_lsp
        st.session_state['comp_key'] = all_comp
        import calendar
        today = datetime.now().date()
        start_of_month = today.replace(day=1)
        last_day = calendar.monthrange(today.year, today.month)[1]
        end_of_month = today.replace(day=last_day)
        st.session_state['dates_key'] = [start_of_month, end_of_month]
        st.session_state['group_key'] = ["Assignee"]
    
    st.session_state["filters_init"] = True

# Global variables for layout fallback
start = datetime.now().date().strftime('%Y-%m-%d')
end = start
filtered_df = df.copy()

# --- 5. Rendering Functions ---

def render_dashboard_content(df, last_updated):
    # --- Top Title & Last Updated ---
    col_title, col_time = st.columns([3, 1])
    with col_title:
        st.title("📊 NSS Support Hub")
    with col_time:
        st.write("") 
        st.write("")
        st.caption(f"🔄 **Τελευταία Ενημέρωση Δεδομένων:** {last_updated}")

    # --- Top Banner: Latest Announcement & Pro Tip (Shown directly) ---
    latest_announcement = load_latest_content("Announcement")
    latest_protip = load_latest_content("ProTip")
    
    if latest_announcement or latest_protip:
        col_ann, col_tip = st.columns(2)
        
        with col_ann:
            if latest_announcement:
                author_str = f"\n\n✍️ *Συντάκτης: {latest_announcement['Author']}*" if latest_announcement.get('Author') else ""
                st.info(f"📢 **Πρόσφατη Ανακοίνωση: {latest_announcement['Title']}**\n\n{latest_announcement['Body']}{author_str}")
                
        with col_tip:
            if latest_protip:
                author_str = f"\n\n✍️ *Συντάκτης: {latest_protip['Author']}*" if latest_protip.get('Author') else ""
                st.success(f"💡 **Weekly Pro Tip: {latest_protip['Title']}**\n\n{latest_protip['Body']}{author_str}")
        st.write("<br>", unsafe_allow_html=True)

    # --- 💾 Saved Previews Section ---
    if st.session_state.logged_in:
        active_preset_name = st.session_state.get("active_preset_name")
        expander_title = "💾 Saved Previews (Presets) - Timesheet"
        if active_preset_name:
            expander_title += f" (Ενεργό: {active_preset_name})"
            
        with st.expander(expander_title, expanded=False):
            presets = load_user_presets(st.session_state.user_id)
            ts_presets = [p for p in presets if "proj_key" in p["FiltersJSON"]]
            
            def on_ts_preset_change():
                val = st.session_state.ts_preset_select_widget
                if val and val != "-- Επιλέξτε Preview --":
                    clean_val = val.replace(" (⭐ Προεπιλογή)", "")
                    selected_preset = next((p for p in ts_presets if p["PresetName"] == clean_val), None)
                    if selected_preset:
                        import json
                        try:
                            filters = json.loads(selected_preset["FiltersJSON"])
                            if "proj_key" in filters:
                                st.session_state["proj_key"] = filters["proj_key"]
                            if "auth_key" in filters:
                                st.session_state["auth_key"] = filters["auth_key"]
                            if "charge_key" in filters:
                                st.session_state["charge_key"] = filters["charge_key"]
                            if "time_key" in filters:
                                st.session_state["time_key"] = filters["time_key"]
                            if "partner_key" in filters:
                                st.session_state["partner_key"] = filters["partner_key"]
                            if "lsp_key" in filters:
                                st.session_state["lsp_key"] = filters["lsp_key"]
                            if "comp_key" in filters:
                                st.session_state["comp_key"] = filters["comp_key"]
                            if "dates_key" in filters:
                                st.session_state["dates_key"] = [pd.to_datetime(d).date() for d in filters["dates_key"]]
                            if "group_key" in filters:
                                st.session_state["group_key"] = filters["group_key"]
                            
                            st.session_state.active_preset_name = selected_preset["PresetName"]
                            st.session_state.active_preset_json = selected_preset["FiltersJSON"]
                            st.toast("✅ Το Preview φορτώθηκε επιτυχώς!")
                        except Exception as e:
                            st.error(f"Σφάλμα κατά τη φόρτωση του preview: {e}")
                st.session_state.ts_preset_select_widget = "-- Επιλέξτε Preview --"

            preset_names = ["-- Επιλέξτε Preview --"] + [
                f"{p['PresetName']} (⭐ Προεπιλογή)" if p.get("IsDefault") else p["PresetName"]
                for p in ts_presets
            ]
            st.selectbox(
                "Φόρτωση Preview", 
                options=preset_names, 
                key="ts_preset_select_widget",
                on_change=on_ts_preset_change
            )
            
            st.markdown("---")
            new_preset_name = st.text_input("Όνομα νέου Preview", placeholder="π.χ. My Support Group", key="ts_new_preset_name")
            if st.button("Αποθήκευση Τρέχοντος Φίλτρου", type="primary", width='stretch', key="ts_save_preset_btn"):
                if new_preset_name.strip():
                    filters_dict = {
                        "proj_key": st.session_state.get("proj_key", []),
                        "auth_key": st.session_state.get("auth_key", []),
                        "charge_key": st.session_state.get("charge_key", []),
                        "time_key": st.session_state.get("time_key", []),
                        "partner_key": st.session_state.get("partner_key", []),
                        "lsp_key": st.session_state.get("lsp_key", []),
                        "comp_key": st.session_state.get("comp_key", []),
                        "dates_key": [str(d) for d in st.session_state.get("dates_key", [])],
                        "group_key": st.session_state.get("group_key", ["Assignee"])
                    }
                    import json
                    if save_user_preset(st.session_state.user_id, new_preset_name.strip(), json.dumps(filters_dict)):
                        st.toast("✅ Το Preview αποθηκεύτηκε!")
                        st.rerun()
                else:
                    st.error("Εισάγετε ένα έγκυρο όνομα")
                    
            active_preset_name = st.session_state.get("active_preset_name")
            if active_preset_name:
                st.markdown("---")
                st.markdown(f"📂 **Ενεργό Preview:** `{active_preset_name}`")
                
                active_preset = next((p for p in ts_presets if p["PresetName"] == active_preset_name), None)
                is_default_active = active_preset.get("IsDefault", False) if active_preset else False
                
                if is_default_active:
                    st.markdown("⭐ **Προεπιλεγμένο Preview (αυτόματο)**")
                else:
                    if st.button("⭐ Ορισμός ως Προεπιλογή", type="secondary", width='stretch', key="ts_set_default_preset_btn"):
                        if set_preset_as_default(st.session_state.user_id, active_preset_name, "proj_key"):
                            st.toast("✅ Ορίστηκε ως προεπιλεγμένο preview!")
                            st.rerun()
                
                col_update, col_reload, col_close = st.columns(3)
                with col_update:
                    if st.button("💾 Ενημέρωση", type="primary", width='stretch', key="ts_update_preset_btn"):
                        filters_dict = {
                            "proj_key": st.session_state.get("proj_key", []),
                            "auth_key": st.session_state.get("auth_key", []),
                            "charge_key": st.session_state.get("charge_key", []),
                            "time_key": st.session_state.get("time_key", []),
                            "partner_key": st.session_state.get("partner_key", []),
                            "lsp_key": st.session_state.get("lsp_key", []),
                            "comp_key": st.session_state.get("comp_key", []),
                            "dates_key": [str(d) for d in st.session_state.get("dates_key", [])],
                            "group_key": st.session_state.get("group_key", ["Assignee"])
                        }
                        import json
                        new_json = json.dumps(filters_dict)
                        if update_user_preset(st.session_state.user_id, active_preset_name, new_json):
                            st.session_state.active_preset_json = new_json
                            st.toast("✅ Το Preview ενημερώθηκε επιτυχώς!")
                with col_reload:
                    if st.button("🔄 Επαναφορά", type="secondary", width='stretch', key="ts_reload_preset_btn"):
                        if "active_preset_json" in st.session_state:
                            apply_preset_filters(st.session_state.active_preset_json)
                            st.toast("🔄 Τα αρχικά φίλτρα του Preview επαναφέρθηκαν!")
                            st.rerun()
                with col_close:
                    if st.button("❌ Κλείσιμο", type="secondary", width='stretch', key="ts_close_preset_btn"):
                        clear_keys_and_rerun(["active_preset_name", "active_preset_json"])
                    
                st.markdown("---")
                all_users = load_all_active_users()
                other_users = [u for u in all_users if u["UserID"] != st.session_state.user_id]
                other_user_names = [u["Username"] for u in other_users]
                
                st.markdown("**Κοινοποίηση σε χρήστες:**")
                share_with = st.multiselect("Επιλέξτε Χρήστες", options=other_user_names, key="ts_preset_share_users_select")
                if st.button("Κοινοποίηση", type="secondary", width='stretch', key="ts_preset_share_btn"):
                    if share_with:
                        shared_name = f"{active_preset_name} (Shared by {st.session_state.username})"
                        success_users = []
                        for username in share_with:
                            target_user = next((u for u in other_users if u["Username"] == username), None)
                            if target_user:
                                if save_user_preset(target_user["UserID"], shared_name, st.session_state.active_preset_json):
                                    success_users.append(username)
                        if success_users:
                            st.success(f"Κοινοποιήθηκε επιτυχώς στους χρήστες: {', '.join(success_users)}!")

    # --- 🔍 Φίλτρα Αναζήτησης Timesheet Grid ---
    with st.expander("🔍 Φίλτρα Αναζήτησης Timesheet", expanded=False):
        # Row 1 (4 columns)
        tcol1, tcol2, tcol3, tcol4 = st.columns(4)
        # Row 2 (4 columns)
        tcol5, tcol6, tcol7, tcol8 = st.columns(4)
        # Row 3 (2 columns)
        tcol9, tcol10 = st.columns([3, 1])

        with tcol1:
            date_range = st.date_input("📅 Ημερομηνίες", key="dates_key")

        with tcol2:
            groups = load_groups_from_db()
            group_names = ["Όλες οι Ομάδες"] + [g["GroupName"] for g in groups]
            
            def on_group_filter_change():
                val = st.session_state.group_filter_selectbox_key
                all_auth = sorted([str(x) for x in df["Assignee"].dropna().unique()])
                if val and val != "Όλες οι Ομάδες":
                    selected_group = next((g for g in groups if g["GroupName"] == val), None)
                    if selected_group:
                        group_members = load_group_members(selected_group["GroupID"])
                        if group_members:
                            st.session_state["auth_key"] = sorted([m for m in group_members if m in all_auth])
                else:
                    st.session_state["auth_key"] = all_auth

            sel_group_name = st.selectbox(
                "👥 Ομάδα Χρηστών", 
                options=group_names, 
                key="group_filter_selectbox_key",
                on_change=on_group_filter_change
            )

        with tcol3:
            sel_proj = st.multiselect("📁 Project", options=sorted([str(x) for x in df["Project"].dropna().unique()]), key="proj_key")

        with tcol4:
            assignee_options = sorted([str(x) for x in df["Assignee"].dropna().unique()])
            if sel_group_name != "Όλες οι Ομάδες":
                selected_group_id = next(g["GroupID"] for g in groups if g["GroupName"] == sel_group_name)
                group_members = load_group_members(selected_group_id)
                if group_members:
                    assignee_options = sorted([m for m in group_members if m in assignee_options])

            sel_auth = st.multiselect("👤 Assignee", options=assignee_options, key="auth_key")
            
            if st.session_state.logged_in:
                user_name_to_select = st.session_state.display_name or st.session_state.username
                all_auth = sorted([str(x) for x in df["Assignee"].dropna().unique()])
                if user_name_to_select in all_auth:
                    st.button("👤 Μόνο Εγώ", type="secondary", width='stretch', key="ts_only_me_btn", on_click=on_only_me_click, args=(user_name_to_select,))

        with tcol5:
            sel_charge = st.multiselect("💰 Charge Type", options=sorted([str(x) for x in df["Charge Type"].dropna().unique()]), key="charge_key")

        with tcol6:
            sel_time = st.multiselect("⏱️ Time Type", options=sorted([str(x) for x in df["Time Type"].dropna().unique()]), key="time_key")

        with tcol7:
            if "Partner Name" in df.columns:
                sel_partner = st.multiselect("🤝 Partner Name", options=sorted([str(x) for x in df["Partner Name"].dropna().unique()]), key="partner_key")
            else:
                sel_partner = []

        with tcol8:
            if "LSP Customer Name" in df.columns:
                sel_lsp = st.multiselect("🏢 LSP Customer", options=sorted([str(x) for x in df["LSP Customer Name"].dropna().unique()]), key="lsp_key")
            else:
                sel_lsp = []

        with tcol9:
            if "Parent Category" in df.columns:
                sel_comp = st.multiselect("🧩 Κατηγορίες (Components)", options=sorted([str(x) for x in df["Parent Category"].dropna().unique()]), key="comp_key")
            else:
                sel_comp = []

        with tcol10:
            st.write("<div style='height: 24px;'></div>", unsafe_allow_html=True)
            if st.button("🔄 Καθαρισμός Φίλτρων", type="primary", width='stretch', key="ts_clear_filters_btn"):
                filter_keys = [
                    'proj_key', 'auth_key', 'charge_key', 'time_key', 'partner_key', 'lsp_key', 'comp_key', 
                    'dates_key', 'group_key', 'filters_init', 'group_filter_selectbox_key', 
                    'active_preset_name', 'active_preset_json'
                ]
                st.toast("🔄 Τα φίλτρα καθαρίστηκαν!")
                clear_keys_and_rerun(filter_keys)

    # Φιλτράρισμα Δεδομένων
    start = date_range[0].strftime('%Y-%m-%d')
    end = date_range[1].strftime('%Y-%m-%d') if len(date_range) > 1 else start

    mask = (df["Date"] >= start) & (df["Date"] <= end) & \
           df["Project"].isin(sel_proj) & df["Assignee"].isin(sel_auth) & \
           df["Charge Type"].isin(sel_charge) & df["Time Type"].isin(sel_time)

    if "Partner Name" in df.columns:
        mask = mask & df["Partner Name"].isin(sel_partner)
    if "LSP Customer Name" in df.columns:
        mask = mask & df["LSP Customer Name"].isin(sel_lsp)

    if "Parent Category" in df.columns and sel_comp:
        pattern = '|'.join([re.escape(c) for c in sel_comp])
        mask = mask & df["Parent Category"].str.contains(pattern, case=False, na=False)

    filtered_df = df[mask]
    
    st.subheader("📌 Σύνοψη", divider="blue")
    m1, m2, m3, m4 = st.columns(4)
    total_mins = filtered_df["Minutes"].sum()
    m1.metric("Συνολικός Χρόνος", format_to_hhmm(total_mins))
    m2.metric("Ενεργά Projects", filtered_df["Project"].nunique())
    m3.metric("Σύμβουλοι (Assignees)", filtered_df["Assignee"].nunique())
    m4.metric("Μοναδικά Tickets", filtered_df["Issue Key"].nunique())
    
    # --- Ενότητα Β: Pivot Table & Export ---
    st.subheader("📅 Αναλυτικό Timesheet", divider="gray")
    
    group_options = ["Assignee", "Parent Key", "Parent Title", "Issue Key", "Project", "Time Type", "Charge Type", "Partner Name", "LSP Customer Name"]
    sel_group = st.multiselect("🗂️ Ομαδοποίηση (Group By) ανά:", options=group_options, key="group_key")
    
    if not sel_group:
        st.error("Επιλέξτε τουλάχιστον ένα πεδίο ομαδοποίησης.")
        st.stop()
    
    if not filtered_df.empty:
        pivot_groups = sel_group.copy()
        if "Parent Key" in sel_group and "Parent Title" in filtered_df.columns and "Parent Title" not in sel_group:
            pivot_groups.append("Parent Title")
    
        pivot = filtered_df.pivot_table(
            index=pivot_groups,
            columns="Date",
            values="Minutes",
            aggfunc="sum",
            fill_value=0,
            margins=True,          
            margins_name="Σύνολο"  
        )
        
        pivot_fmt = pivot.map(format_to_hhmm)
        pivot_fmt = pivot_fmt.reset_index()
        
        col_config = {}
    
        # Διαχείριση Issue Key Link
        if "Issue Key" in pivot_fmt.columns:
            jira_base = f"https://{JIRA_DOMAIN}/browse/"
            pivot_fmt["🔗 Link"] = pivot_fmt["Issue Key"].apply(
                lambda x: f"{jira_base}{x}" if x and x != "Σύνολο" else None
            )
            cols = list(pivot_fmt.columns)
            cols.remove("🔗 Link")
            idx = cols.index("Issue Key")
            cols.insert(idx + 1, "🔗 Link")
            pivot_fmt = pivot_fmt[cols]
            col_config["🔗 Link"] = st.column_config.LinkColumn("Άνοιγμα", display_text="Issue URL") 
    
        # Διαχείριση Parent Key & Title
        if "Parent Key" in pivot_fmt.columns:
            jira_base = f"https://{JIRA_DOMAIN}/browse/"
            
            if "Parent Title" in pivot_fmt.columns:
                cols = list(pivot_fmt.columns)
                cols.remove("Parent Title")
                pk_idx = cols.index("Parent Key")
                cols.insert(pk_idx + 1, "Parent Title")
                pivot_fmt = pivot_fmt[cols]
                col_config["Parent Title"] = st.column_config.TextColumn("Τίτλος Parent", width="medium")
    
            link_col_name = "🔗 Parent Link" 
            pivot_fmt[link_col_name] = pivot_fmt["Parent Key"].apply(
                lambda x: f"{jira_base}{x}" if x and x != "Σύνολο" and x != "N/A" else None
            )
            
            cols = list(pivot_fmt.columns)
            cols.remove(link_col_name)
            ref_col = "Parent Title" if "Parent Title" in pivot_fmt.columns else "Parent Key"
            target_idx = cols.index(ref_col)
            cols.insert(target_idx + 1, link_col_name)
            pivot_fmt = pivot_fmt[cols]
            
            col_config[link_col_name] = st.column_config.LinkColumn("Parent", display_text="Open")
    
        def highlight_cells(row):
            styles = [''] * len(row)
            is_total_row = row[sel_group[0]] == 'Σύνολο'
            for i, col in enumerate(row.index):
                val = row[col]
                cell_style = ''
                if is_total_row or col == 'Σύνολο':
                    cell_style = 'font-weight: bold; background-color: #E2E8F0; color: #1E293B;' 
                elif col in pivot_groups:
                    cell_style = 'background-color: #F8FAFC; font-weight: 500;'
                else:
                    if isinstance(val, str) and ':' in val:
                        try:
                            hours, minutes = map(int, val.split(':'))
                            if hours >= 8:
                                cell_style = 'font-weight: bold; color: #0B8043; background-color: #E8F5E9;'
                        except ValueError:
                            pass
                styles[i] = cell_style
            return styles
    
        # --- Έλεγχος μεγέθους και Εμφάνιση ---
        total_cells = pivot_fmt.size 
        max_allowed_cells = 200000 
    
        if total_cells > max_allowed_cells:
            st.warning("⚠️ **Πάρα πολλά δεδομένα για προβολή!**")
        else:
            styled_pivot = pivot_fmt.style.apply(highlight_cells, axis=1)
            st.dataframe(
                styled_pivot,
                width='stretch',
                height=600,
                column_config=col_config,
                hide_index=True
            )
        
        # --- Καθαρό Export ---
        def convert_df_to_excel(df_to_export):
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df_to_export.to_excel(writer, sheet_name='Timesheet', index=False)
            return output.getvalue()
    
        col_empty, col_btn = st.columns([5, 1])
        with col_btn:
            st.download_button(
                label="📥 Λήψη σε Excel",
                data=convert_df_to_excel(pivot_fmt),
                file_name=f"NSS_Timesheet_{start}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary",
                width='stretch'
            )
    else:
        st.info("Δεν υπάρχουν δεδομένα για τα επιλεγμένα φίλτρα.")
    
    # --- Ενότητα Γ: Γραφήματα ---
    st.write("---")
    st.subheader("📈 Γραφήματα Ανάλυσης", divider="gray")
    
    c1, c2 = st.columns(2)
    
    with c1:
        chart_time = filtered_df.groupby("Time Type")["Minutes"].sum().reset_index()
        chart_time["Ώρες"] = (chart_time["Minutes"] / 60).round(1)
        
        fig_time = px.pie(chart_time, 
                          values="Ώρες", 
                          names="Time Type", 
                          hole=0.4, 
                          title="⏳ Αναλογία ανά Time Type",
                          color_discrete_sequence=px.colors.sequential.Oranges_r)
        fig_time.update_traces(textposition='inside', textinfo='percent+label', hovertemplate="%{label}: %{value} Ώρες")
        fig_time.update_layout(height=400, showlegend=False) 
        st.plotly_chart(fig_time, width='stretch')
    
    with c2:
        chart_charge = filtered_df.groupby("Charge Type")["Minutes"].sum().reset_index()
        chart_charge["Ώρες"] = (chart_charge["Minutes"] / 60).round(1)
        
        fig_charge = px.pie(chart_charge, 
                            values="Ώρες", 
                            names="Charge Type", 
                            hole=0.4, 
                            title="💰 Αναλογία ανά Charge Type",
                            color_discrete_sequence=px.colors.sequential.Greens_r) 
        fig_charge.update_traces(textposition='inside', textinfo='percent+label', hovertemplate="%{label}: %{value} Ώρες")
        fig_charge.update_layout(height=400, showlegend=False)
        st.plotly_chart(fig_charge, width='stretch')
    
    st.write("<br>", unsafe_allow_html=True) 
    
    chart_parent = filtered_df.groupby("Parent Category")["Minutes"].sum().reset_index().sort_values("Minutes")
    chart_parent["Ώρες"] = (chart_parent["Minutes"] / 60).round(1)
    
    fig_comp = px.bar(chart_parent, 
                      x="Ώρες", 
                      y="Parent Category", 
                      orientation='h', 
                      title="⏱️ Time Distribution per Main Category", 
                      color_discrete_sequence=['#0078D4'],
                      labels={"Parent Category": "Κατηγορία", "Ώρες": "Συνολικές Ώρες"}
                     )
    
    fig_comp.update_layout(height=800) 
    st.plotly_chart(fig_comp, width='stretch')

def render_announcements_and_tips():
    st.subheader("📢 Ανακοινώσεις & Pro Tips", divider="blue")
    
    is_management = st.session_state.user_role in ["Administrator", "Team Leader"]
    
    # Χτίζουμε τα sub-tabs δυναμικά βάσει δικαιωμάτων
    tabs_to_show = ["📢 Ανακοινώσεις", "💡 Pro Tips"]
    if is_management:
        tabs_to_show.append("⚙️ Διαχείριση (CRUD)")
        
    sub_tabs = st.tabs(tabs_to_show)
    
    # Βοηθητική συνάρτηση για rendering λίστας χωρίς expander
    def show_content_list(ctype):
        items = load_all_content_admin()
        # Φιλτράρισμα: κρατάμε μόνο όσα είναι ενεργά, ανήκουν στη σωστή κατηγορία, και είναι ορατά βάσει preferences
        filtered_items = [i for i in items if i['ContentType'] == ctype and i['IsActive'] and is_content_visible(i.get('TargetApps'))]
        
        if not filtered_items:
            st.info(f"Δεν υπάρχουν ενεργές εγγραφές για {ctype}.")
        else:
            for item in filtered_items:
                with st.container(border=True):
                    st.markdown(f"#### {item['Title']}")
                    st.caption(f"✍️ **Συντάκτης:** {item.get('Author', 'Άγνωστος')}")
                    st.markdown("---")
                    st.markdown(item['Body'])
    
    # Tab 1: Ανακοινώσεις
    with sub_tabs[0]:
        show_content_list("Announcement")
        
    # Tab 2: Pro Tips
    with sub_tabs[1]:
        show_content_list("ProTip")
        
    # Tab 3: Διαχείριση (Μόνο για Ηγεσία)
    if is_management:
        with sub_tabs[2]:
            mode = st.radio("Ενέργεια", ["➕ Προσθήκη Νέου", "✏️ Επεξεργασία / Διαγραφή"], horizontal=True)
            
            if mode == "➕ Προσθήκη Νέου":
                with st.form("add_content_form", clear_on_submit=True):
                    c_type = st.selectbox("Τύπος Περιεχομένου", ["Announcement", "ProTip"])
                    title = st.text_input("Τίτλος")
                    body = st.text_area("Περιεχόμενο (Markdown)", height=200)
                    c_apps = st.multiselect("Εφαρμογές Στόχοι (Αφήστε κενό για όλες)", options=["Galaxy", "Pylon"], default=["Galaxy", "Pylon"], key="add_content_apps_multiselect")
                    if st.form_submit_button("Δημοσίευση", type="primary"):
                        if title.strip() and body.strip():
                            app_str = ",".join(c_apps) if c_apps else None
                            if save_content_item(title.strip(), body.strip(), c_type, st.session_state.user_id, app_str):
                                write_system_log(st.session_state.user_id, f"CREATE_{c_type.upper()}", f"Τίτλος: {title}")
                                st.toast("✅ Επιτυχής δημοσίευση!")
                                st.rerun()
                        else: st.error("Συμπληρώστε όλα τα πεδία.")
                        
            else:
                items = load_all_content_admin()
                if not items:
                    st.info("Δεν υπάρχει περιεχόμενο.")
                else:
                    item_options = {f"[{i['ContentType']}] {i['Title']}": i for i in items}
                    selected_option = st.selectbox("Επιλέξτε στοιχείο προς διαχείριση", ["-- Επιλογή --"] + list(item_options.keys()))
                    
                    if selected_option != "-- Επιλογή --":
                        item = item_options[selected_option]
                        with st.container(border=True):
                            edit_title = st.text_input("Τίτλος", value=item['Title'])
                            edit_type = st.selectbox("Τύπος", ["Announcement", "ProTip"], index=0 if item['ContentType'] == "Announcement" else 1)
                            edit_body = st.text_area("Περιεχόμενο (Markdown)", value=item['Body'], height=200)
                            edit_active = st.checkbox("Ενεργό (Προβάλλεται)", value=item['IsActive'])
                            existing_apps = [x.strip() for x in item.get('TargetApps').split(",") if x.strip()] if item.get('TargetApps') else ["Galaxy", "Pylon"]
                            edit_apps = st.multiselect("Εφαρμογές Στόχοι (Αφήστε κενό για όλες)", options=["Galaxy", "Pylon"], default=existing_apps, key=f"edit_content_apps_{item['ContentID']}")
                            
                            col_up, col_del = st.columns(2)
                            with col_up:
                                if st.button("💾 Αποθήκευση Αλλαγών", type="primary", width='stretch'):
                                    edit_app_str = ",".join(edit_apps) if edit_apps else None
                                    if update_content_item(item['ContentID'], edit_title, edit_body, edit_type, edit_active, edit_app_str):
                                        write_system_log(st.session_state.user_id, "UPDATE_CONTENT", f"ID: {item['ContentID']}")
                                        st.toast("✅ Οι αλλαγές αποθηκεύτηκαν!")
                                        st.rerun()
                            with col_del:
                                if st.button("🗑️ Μόνιμη Διαγραφή", type="secondary", width='stretch'):
                                    if delete_content_item(item['ContentID']):
                                        write_system_log(st.session_state.user_id, "DELETE_CONTENT", f"ID: {item['ContentID']}")
                                        st.toast("🗑️ Το στοιχείο διαγράφηκε!")
                                        st.rerun()

# Η συνάρτηση που δημιουργεί το popup παράθυρο για τα άρθρα
@st.dialog("📖 Ανάγνωση Άρθρου", width="large")
def open_article_modal(title, content, author=None):
    st.subheader(title)
    if author:
        st.caption(f"✍️ **Συντάκτης:** {author}")
    st.markdown("---")
    st.markdown(content)

def render_knowledge_base_content():
    st.subheader("💡 Εσωτερική Βάση Γνώσης (Knowledge Base)", divider="blue")
    
    is_management = st.session_state.user_role in ["Administrator", "Team Leader"]
    
    def show_articles():
        articles = load_kb_articles(only_active=True)
        articles = [art for art in articles if is_content_visible(art.get("TargetApps"))]
        if not articles:
            st.info("Δεν υπάρχουν ακόμη διαθέσιμα άρθρα διαδικασιών.")
        else:
            categories = sorted(list(set([a['Category'] for a in articles])))
            
            # Search & Category layout row
            col_search, col_cat = st.columns([2, 1])
            with col_search:
                search_query = st.text_input("🔍 Αναζήτηση στα άρθρα (Τίτλος, Κατηγορία, Περιεχόμενο)", placeholder="π.χ. Jira, άδεια...", key="kb_search_input")
            with col_cat:
                selected_cat = st.selectbox("📂 Φιλτράρισμα ανά Κατηγορία", ["Όλες οι Κατηγορίες"] + categories)
            
            visible_articles = []
            for art in articles:
                # 1. Category check
                if selected_cat != "Όλες οι Κατηγορίες" and art['Category'] != selected_cat:
                    continue
                # 2. Text Search check (case-insensitive)
                if search_query.strip():
                    q = search_query.lower().strip()
                    in_title = q in art['Title'].lower()
                    in_content = q in art['Content'].lower()
                    in_cat = q in art['Category'].lower()
                    if not (in_title or in_content or in_cat):
                        continue
                visible_articles.append(art)
                
            if not visible_articles:
                st.info("Δεν βρέθηκαν άρθρα με τα συγκεκριμένα κριτήρια φιλτραρίσματος.")
            else:
                for art in visible_articles:
                    # Αντί για expander, φτιάχνουμε μια "κάρτα" με κουμπί
                    with st.container(border=True):
                        col_title, col_btn = st.columns([4, 1])
                        with col_title:
                            st.markdown(f"**{art['Title']}**")
                            st.caption(f"📁 Κατηγορία: {art['Category']} | ✍️ Συντάκτης: {art.get('Author', 'Άγνωστος')}")
                        with col_btn:
                            # Με το πάτημα καλούμε το modal
                            if st.button("📖 Διάβασμα", key=f"read_kb_{art['ArticleID']}", width='stretch'):
                                open_article_modal(art['Title'], art['Content'], art.get('Author'))

    if is_management:
        tab_view, tab_manage = st.tabs(["📖 Ανάγνωση Άρθρων", "⚙️ Διαχείριση Άρθρων (CRUD)"])
        with tab_view:
            show_articles()
            
        with tab_manage:
            kb_mode = st.radio("Λειτουργία KB", ["➕ Νέο Άρθρο", "✏️ Επεξεργασία Υπάρχοντος"], horizontal=True)
            if kb_mode == "➕ Νέο Άρθρο":
                with st.form("new_kb_form", clear_on_submit=True):
                    cat = st.text_input("Κατηγορία (π.χ. Διαδικασίες Jira, Πολιτική Αδειών)")
                    title = st.text_input("Τίτλος Άρθρου")
                    content = st.text_area("Περιεχόμενο (Markdown)", height=300)
                    kb_apps = st.multiselect("Εφαρμογές Στόχοι (Αφήστε κενό για όλες)", options=["Galaxy", "Pylon"], default=["Galaxy", "Pylon"], key="add_kb_apps_multiselect")
                    if st.form_submit_button("Αποθήκευση Άρθρου", type="primary"):
                        if title.strip() and cat.strip() and content.strip():
                            kb_app_str = ",".join(kb_apps) if kb_apps else None
                            if save_kb_article(title.strip(), cat.strip(), content.strip(), st.session_state.user_id, kb_app_str):
                                write_system_log(st.session_state.user_id, "CREATE_KB_ARTICLE", title)
                                st.toast("✅ Το άρθρο αποθηκεύτηκε!")
                                st.rerun()
                        else: 
                            st.error("Συμπληρώστε όλα τα πεδία.")
            else:
                all_articles = load_kb_articles(only_active=False)
                if not all_articles:
                    st.info("Δεν υπάρχουν άρθρα.")
                else:
                    art_options = {f"[{a['Category']}] {a['Title']}": a for a in all_articles}
                    sel_art_opt = st.selectbox("Επιλέξτε άρθρο", ["-- Επιλογή --"] + list(art_options.keys()))
                    
                    if sel_art_opt != "-- Επιλογή --":
                        art = art_options[sel_art_opt]
                        edit_cat = st.text_input("Κατηγορία", value=art['Category'])
                        edit_title = st.text_input("Τίτλος", value=art['Title'])
                        edit_content = st.text_area("Περιεχόμενο (Markdown)", value=art['Content'], height=300)
                        edit_active = st.checkbox("Ενεργό", value=art['IsActive'])
                        existing_kb_apps = [x.strip() for x in art.get('TargetApps').split(",") if x.strip()] if art.get('TargetApps') else ["Galaxy", "Pylon"]
                        edit_kb_apps = st.multiselect("Εφαρμογές Στόχοι (Αφήστε κενό για όλες)", options=["Galaxy", "Pylon"], default=existing_kb_apps, key=f"edit_kb_apps_{art['ArticleID']}")
                        
                        c_up, c_del = st.columns(2)
                        with c_up:
                            if st.button("💾 Ενημέρωση Άρθρου", type="primary", width='stretch'):
                                edit_kb_app_str = ",".join(edit_kb_apps) if edit_kb_apps else None
                                if update_kb_article(art['ArticleID'], edit_title, edit_cat, edit_content, edit_active, edit_kb_app_str):
                                    st.toast("✅ Το άρθρο ενημερώθηκε!")
                                    st.rerun()
                        with c_del:
                            if st.button("🗑️ Διαγραφή Άρθρου", type="secondary", width='stretch'):
                                if delete_kb_article(art['ArticleID']):
                                    st.toast("🗑️ Το άρθρο διαγράφηκε!")
                                    st.rerun()
    else:
        show_articles()

def render_profile_content():
    st.subheader("👤 Διαχείριση Προφίλ", divider="blue")
    
    st.write(f"Όνομα Χρήστη: **{st.session_state.username}**")
    st.write(f"Ρόλος: `{st.session_state.user_role}`")
    st.write(f"Όνομα στο Jira (DisplayName): **{st.session_state.display_name or 'N/A'}**")
    
    st.markdown("---")
    st.subheader("⚙️ Προτιμήσεις")
    
    # Load available projects from WorkLogs table
    engine = get_db_engine()
    all_projects = []
    if engine:
        try:
            df_proj = pd.read_sql("SELECT DISTINCT Project FROM WorkLogs WHERE Project IS NOT NULL", engine)
            all_projects = sorted(df_proj["Project"].tolist())
        except Exception:
            pass
            
    default_proj_options = ["-- Κανένα --"] + all_projects
    current_default_idx = 0
    if st.session_state.default_project in default_proj_options:
        current_default_idx = default_proj_options.index(st.session_state.default_project)
        
    new_default_proj = st.selectbox("Προεπιλεγμένο Project", options=default_proj_options, index=current_default_idx)
    
    st.markdown("##### Προτιμήσεις Εφαρμογών (Ανακοινώσεις, Tips & Knowledge Base)")
    user_pref = st.session_state.get("app_preferences")
    default_selected = [x.strip() for x in user_pref.split(",") if x.strip()] if user_pref else ["Galaxy", "Pylon"]
    
    new_app_prefs = st.multiselect(
        "Επιλέξτε τις εφαρμογές που σας ενδιαφέρουν:",
        options=["Galaxy", "Pylon"],
        default=default_selected,
        key="profile_app_prefs_multiselect"
    )
    
    if st.button("Αποθήκευση Προτιμήσεων", type="primary"):
        val = None if new_default_proj == "-- Κανένα --" else new_default_proj
        app_pref_str = ",".join(new_app_prefs)
        
        proj_ok = update_user_default_project(st.session_state.user_id, val)
        app_ok = update_user_app_preferences(st.session_state.user_id, app_pref_str)
        
        if proj_ok and app_ok:
            st.session_state.default_project = val
            st.session_state.app_preferences = app_pref_str
            st.session_state["active_app_view"] = new_app_prefs
            if "active_app_view_widget" in st.session_state:
                st.session_state["active_app_view_widget"] = new_app_prefs
            if "filters_init" in st.session_state:
                del st.session_state["filters_init"]
            st.success("✅ Οι προτιμήσεις αποθηκεύτηκαν!")
            st.rerun()
            
    st.markdown("---")
    st.subheader("🔒 Αλλαγή Κωδικού Πρόσβασης")
    old_pwd = st.text_input("Τρέχων Κωδικός", type="password", key="profile_old_pwd")
    new_pwd = st.text_input("Νέος Κωδικός", type="password", key="profile_new_pwd")
    confirm_pwd = st.text_input("Επιβεβαίωση Νέου Κωδικού", type="password", key="profile_confirm_pwd")
    
    if st.button("Ενημέρωση Κωδικού", type="secondary"):
        if not old_pwd or not new_pwd or not confirm_pwd:
            st.error("Παρακαλώ συμπληρώστε όλα τα πεδία.")
        elif new_pwd != confirm_pwd:
            st.error("Ο νέος κωδικός και η επιβεβαίωση δεν ταιριάζουν.")
        else:
            verified_user = verify_user_credentials(st.session_state.username, old_pwd)
            if verified_user:
                if update_user_password(st.session_state.user_id, new_pwd):
                    st.success("✅ Ο κωδικός άλλαξε επιτυχώς!")
                else:
                    st.error("Αποτυχία ενημέρωσης κωδικού.")
            else:
                st.error("Ο τρέχων κωδικός πρόσβασης είναι λανθασμένος.")

def render_management_content():
    st.subheader("👥 Διαχείριση Ομάδων & Χρηστών", divider="blue")
    
    # User List and Administration (Visible to Admins & Team Leaders, editing ONLY for Admins)
    with st.expander("📋 Λίστα & Διαχείριση Χρηστών"):
        users_list = load_all_users_admin()
        if users_list:
            df_users = pd.DataFrame([{
                "Username": u["Username"],
                "Όνομα (Jira)": u["DisplayName"] or "N/A",
                "Email": u["Email"],
                "Ρόλος": u["RoleName"],
                "Ενεργός": "✅ Ναι" if u["IsActive"] else "❌ Όχι",
                "Ημ. Δημιουργίας": u["CreatedAt"].strftime("%d/%m/%Y %H:%M") if u["CreatedAt"] else "N/A"
            } for u in users_list])
            
            st.dataframe(df_users, width='stretch', hide_index=True)
            
            # Editing functions for Admins only
            if st.session_state.user_role == "Administrator":
                st.markdown("---")
                st.markdown("#### ⚙️ Επεξεργασία & Επαναφορά Χρήστη")
                
                user_options_edit = {u["Username"]: u for u in users_list}
                sel_edit_username = st.selectbox(
                    "Επιλέξτε χρήστη για επεξεργασία", 
                    options=["-- Επιλέξτε Χρήστη --"] + list(user_options_edit.keys()),
                    key="admin_user_edit_selectbox"
                )
                
                if sel_edit_username != "-- Επιλέξτε Χρήστη --":
                    selected_user = user_options_edit[sel_edit_username]
                    is_admin_user = selected_user["RoleName"] == "Administrator"
                    
                    st.write(f"Επεξεργασία χρήστη: **{selected_user['Username']}** (Ρόλος: `{selected_user['RoleName']}`)")
                    
                    if is_admin_user:
                        st.warning("🔒 Δεν επιτρέπεται η ενεργοποίηση/απενεργοποίηση χρηστών με ρόλο Administrator.")
                        new_active = st.checkbox("Ενεργός Λογαριασμός", value=selected_user["IsActive"], disabled=True, key="admin_user_active_checkbox_disabled")
                    else:
                        new_active = st.checkbox("Ενεργός Λογαριασμός", value=selected_user["IsActive"], key="admin_user_active_checkbox")
                        if new_active != selected_user["IsActive"]:
                            if st.button("Αποθήκευση Κατάστασης", type="primary", key="admin_save_user_active_btn"):
                                if admin_update_user_status(selected_user["UserID"], new_active):
                                    if not new_active:
                                        delete_all_user_sessions(selected_user["UserID"])
                                    write_system_log(
                                        st.session_state.user_id,
                                        "UPDATE_USER_STATUS",
                                        f"Αλλαγή κατάστασης χρήστη {selected_user['Username']} σε: {'Ενεργός' if new_active else 'Ανενεργός'}"
                                    )
                                    st.success("✅ Η κατάσταση του χρήστη ενημερώθηκε!")
                                    st.rerun()
                                    
                    st.markdown("**Αλλαγή Ρόλου Χρήστη**")
                    if is_admin_user:
                        st.info("🔒 Οι ρόλοι των Administrators μπορούν να αλλαχθούν μόνο απευθείας στη βάση δεδομένων.")
                        st.selectbox("Ρόλος Χρήστη", options=["Administrator"], index=0, disabled=True, key=f"role_edit_disabled_{selected_user['Username']}")
                    else:
                        role_options = {
                            "Team Leader": 2,
                            "Consultant": 3,
                            "ContentCreator": 4,
                            "ContentManager": 5
                        }
                        current_role_name = selected_user["RoleName"]
                        roles_list = list(role_options.keys())
                        if current_role_name in roles_list:
                            current_index = roles_list.index(current_role_name)
                        else:
                            roles_list = [current_role_name] + roles_list
                            role_options[current_role_name] = selected_user["RoleID"]
                            current_index = 0
                            
                        new_role_name = st.selectbox(
                            "Επιλέξτε νέο ρόλο",
                            options=roles_list,
                            index=current_index,
                            key=f"role_edit_select_{selected_user['Username']}"
                        )
                        
                        if new_role_name != current_role_name:
                            if st.button("Αποθήκευση Ρόλου", type="primary", key=f"btn_save_role_{selected_user['Username']}"):
                                new_role_id = role_options[new_role_name]
                                if admin_update_user_role(selected_user["UserID"], new_role_id):
                                    delete_all_user_sessions(selected_user["UserID"])
                                    write_system_log(
                                        st.session_state.user_id,
                                        "UPDATE_USER_ROLE",
                                        f"Αλλαγή ρόλου χρήστη {selected_user['Username']} από {current_role_name} σε: {new_role_name}"
                                    )
                                    st.success(f"✅ Ο ρόλος του χρήστη ενημερώθηκε σε {new_role_name}!")
                                    st.rerun()
                                    
                    st.markdown("**Επαναφορά Κωδικού σε Default**")
                    st.write("Ο προεπιλεγμένος κωδικός επαναφοράς είναι: `nss12345`")
                    if st.button("🔄 Επαναφορά Κωδικού", type="secondary", key="admin_reset_pwd_btn"):
                        if admin_reset_user_password(selected_user["UserID"], "nss12345"):
                            delete_all_user_sessions(selected_user["UserID"])
                            write_system_log(
                                st.session_state.user_id,
                                "RESET_PASSWORD",
                                f"Επαναφορά κωδικού για τον χρήστη {selected_user['Username']} στον προεπιλεγμένο (nss12345)"
                            )
                            st.success(f"✅ Ο κωδικός για τον χρήστη '{selected_user['Username']}' επαναφέρθηκε σε `nss12345`!")
        else:
            st.info("Δεν βρέθηκαν χρήστες στη βάση δεδομένων.")
            
    st.markdown("---")
    
    # 1. User Registration Form (ONLY for Administrator role)
    if st.session_state.user_role == "Administrator":
        with st.expander("➕ Εγγραφή Νέου Χρήστη (Μόνο Διαχειριστές)"):
            reg_email = st.text_input("Email Χρήστη", placeholder="e.g. user@epsilon-singularlogic.eu")
            
            # Fetch Display Name button
            if reg_email:
                if st.button("Αναζήτηση Display Name στο Jira API"):
                    fetched_name = search_jira_user_by_email(reg_email)
                    if fetched_name:
                        st.success(f"Βρέθηκε Display Name: **{fetched_name}**")
                        st.session_state["fetched_display_name"] = fetched_name
                    else:
                        st.warning("Δεν βρέθηκε χρήστης στο Jira με αυτό το email.")
                        st.session_state["fetched_display_name"] = ""

            reg_display_name = st.text_input(
                "Display Name (από Jira)", 
                value=st.session_state.get("fetched_display_name", "")
            )
            reg_username = st.text_input("Username (για Login)")
            reg_password = st.text_input("Password", type="password")
            
            # Load available roles
            engine = get_db_engine()
            available_roles = []
            if engine:
                from sqlalchemy import text
                with engine.connect() as conn:
                    res_roles = conn.execute(text("SELECT RoleID, RoleName FROM User_Roles")).fetchall()
                    available_roles = [{"RoleID": r[0], "RoleName": r[1]} for r in res_roles]
            
            role_options = [r["RoleName"] for r in available_roles]
            reg_role = st.selectbox("Ρόλος", options=role_options)
            
            if st.button("Δημιουργία Χρήστη", type="primary"):
                if not reg_username or not reg_password or not reg_email:
                    st.error("Παρακαλώ συμπληρώστε όλα τα πεδία (Username, Password, Email).")
                else:
                    selected_role = next(r for r in available_roles if r["RoleName"] == reg_role)
                    if register_new_user(reg_username, reg_password, reg_email, selected_role["RoleID"], reg_display_name):
                        write_system_log(
                            st.session_state.user_id,
                            "CREATE_USER",
                            f"Δημιουργία χρήστη: {reg_username} (Email: {reg_email}, Ρόλος: {reg_role}, Jira Name: {reg_display_name})"
                        )
                        st.success(f"✅ Ο χρήστης '{reg_username}' δημιουργήθηκε με επιτυχία!")
                        st.session_state["fetched_display_name"] = ""
                        st.rerun()
                    else:
                        st.error("Αποτυχία εγγραφής χρήστη (ίσως το Username ή το Email υπάρχει ήδη).")

    # 2. Group Management (Visible to Administrator & Team Leader)
    st.markdown("---")
    st.subheader("👥 Διαχείριση Ομάδων")
    
    groups = load_groups_from_db()
    group_options = ["-- Επιλέξτε Ομάδα --", "➕ Δημιουργία Νέας Ομάδας"] + [g["GroupName"] for g in groups]
    selected_group_opt = st.selectbox("Επιλογή Ομάδας για Επεξεργασία", options=group_options)
    
    # Load all active users to assign them as members
    all_users = load_all_active_users()
    user_options = {u["DisplayName"] or u["Username"]: u["UserID"] for u in all_users}
    
    if selected_group_opt == "➕ Δημιουργία Νέας Ομάδας":
        st.markdown("#### Νέα Ομάδα")
        new_group_name = st.text_input("Όνομα Ομάδας")
        members = st.multiselect("Μέλη Ομάδας", options=list(user_options.keys()))
        
        if st.button("Δημιουργία Ομάδας", type="primary"):
            if new_group_name.strip():
                member_ids = [user_options[m] for m in members]
                if create_new_group_with_members(new_group_name.strip(), member_ids):
                    write_system_log(
                        st.session_state.user_id,
                        "CREATE_GROUP",
                        f"Δημιουργία ομάδας '{new_group_name.strip()}' με μέλη: {', '.join(members)}"
                    )
                    st.success("✅ Η ομάδα δημιουργήθηκε με επιτυχία!")
                    st.rerun()
                else:
                    st.error("Σφάλμα κατά τη δημιουργία της ομάδας.")
            else:
                st.error("Παρακαλώ δώστε ένα όνομα για την ομάδα.")
                
    elif selected_group_opt != "-- Επιλέξτε Ομάδα --" and selected_group_opt is not None:
        selected_group = next(g for g in groups if g["GroupName"] == selected_group_opt)
        group_id = selected_group["GroupID"]
        
        st.markdown(f"#### Επεξεργασία Ομάδας: {selected_group_opt}")
        edit_group_name = st.text_input("Όνομα Ομάδας", value=selected_group["GroupName"])
        
        # Load current members
        engine = get_db_engine()
        current_member_ids = []
        if engine:
            from sqlalchemy import text
            with engine.connect() as conn:
                res_mem = conn.execute(
                    text("SELECT UserID FROM User_Group_Memberships WHERE GroupID = :group_id"),
                    {"group_id": group_id}
                ).fetchall()
                current_member_ids = [r[0] for r in res_mem]
                
        current_member_names = [
            k for k, v in user_options.items() if v in current_member_ids
        ]
        
        edit_members = st.multiselect("Μέλη Ομάδας", options=list(user_options.keys()), default=current_member_names)
        
        col_save, col_del = st.columns(2)
        with col_save:
            if st.button("Αποθήκευση Αλλαγών", type="primary", width='stretch'):
                if edit_group_name.strip():
                    new_member_ids = [user_options[m] for m in edit_members]
                    if update_group_with_members(group_id, edit_group_name.strip(), new_member_ids):
                        write_system_log(
                            st.session_state.user_id,
                            "UPDATE_GROUP",
                            f"Ενημέρωση ομάδας '{selected_group_opt}' σε '{edit_group_name.strip()}' με μέλη: {', '.join(edit_members)}"
                        )
                        st.success("✅ Οι αλλαγές αποθηκεύτηκαν!")
                        st.rerun()
                    else:
                        st.error("Σφάλμα κατά την ενημέρωση της ομάδας.")
                else:
                    st.error("Το όνομα της ομάδας δεν μπορεί να είναι κενό.")
                    
        with col_del:
            if st.session_state.user_role == "Administrator":
                if st.button("🗑️ Διαγραφή Ομάδας", type="secondary", width='stretch'):
                    if delete_group(group_id):
                        write_system_log(
                            st.session_state.user_id,
                            "DELETE_GROUP",
                            f"Διαγραφή ομάδας '{selected_group_opt}'"
                        )
                        st.success("✅ Η ομάδα διαγράφηκε!")
                        st.rerun()
                    else:
                        st.error("Σφάλμα κατά τη διαγραφή της ομάδας.")
            else:
                st.caption("🔒 Μόνο οι Administrators μπορούν να διαγράψουν ομάδες.")

def render_response_times_content():
    # Header with title and load button side-by-side
    col_title, col_btn = st.columns([4, 1])
    with col_title:
        st.subheader("⏱️ Χρόνοι Απόκρισης & KPIs (Jira Epic Tickets)", divider="blue")
    with col_btn:
        st.write("") # Spacing
        load_clicked = st.button("🔄 Φόρτωση / Ανανέωση", type="primary", width='stretch')

    # Custom CSS for multiselect and metrics label spacing
    st.markdown("""
        <style>
            div[data-testid="stMetricLabel"] > div {
                white-space: normal !important;
                word-break: break-word !important;
                display: block !important;
                text-overflow: unset !important;
                overflow: visible !important;
                min-height: 40px;
            }
            [data-testid="stMetricLabel"] {
                white-space: normal !important;
                min-height: 40px;
            }
        </style>
    """, unsafe_allow_html=True)

    if "rt_df" not in st.session_state:
        st.session_state.rt_df = None

    if load_clicked:
        with st.spinner("Φόρτωση δεδομένων από τη βάση... (αναλόγως τον όγκο δεδομένων μπορεί να πάρει 1-3 λεπτά)"):
            try:
                df_issues = rt_load_from_db().rename(columns={"IssueId": "IssueID"})
                df_comments = rt_load_first_response()
                df_assigned = rt_load_first_assigned()
                df_status = rt_load_status_change_date()
                df_awaiting = rt_load_awaiting_customer_end_date()

                # Convert Dates
                df_issues["CreationDate"] = pd.to_datetime(df_issues["CreationDate"])
                df_issues["ClosedDate"] = pd.to_datetime(df_issues["ClosedDate"])
                df_comments["FirstInternalResponseDate"] = pd.to_datetime(df_comments["FirstInternalResponseDate"])
                df_comments["FirstExternalResponseDate"] = pd.to_datetime(df_comments["FirstExternalResponseDate"])
                df_assigned["FirstAssignedDate"] = pd.to_datetime(df_assigned["FirstAssignedDate"])
                df_status["FirstInProgressDate"] = pd.to_datetime(df_status["FirstInProgressDate"])
                for col in ["Start1", "End1", "Start2", "End2", "Start3", "End3", "Start4", "End4", "Start5", "End5", "Start6", "End6"]:
                    if col in df_awaiting.columns:
                        df_awaiting[col] = pd.to_datetime(df_awaiting[col])

                # Merge All
                rt_df = (
                    df_issues
                    .merge(df_assigned, on="IssueID", how="left")
                    .merge(df_comments, on="IssueID", how="left")
                    .merge(df_status, on="IssueID", how="left")
                    .merge(df_awaiting, on="IssueID", how="left")
                )

                rt_df["Project"] = rt_df["IssueKey"].astype(str).str.split("-").str[0]
                BASE_URL = "https://epsilon-singularlogic.atlassian.net/browse/"
                rt_df["JiraLink"] = BASE_URL + rt_df["IssueKey"].astype(str)

                # Fillna for filters
                for col in ["PartnerName", "CustomerName", "Components", "SubCategory"]:
                    rt_df[col] = rt_df[col].fillna("None")
                rt_df["AssigneeName"] = rt_df["AssigneeName"].fillna("Unassigned").astype(str).str.strip()

                # KPI Calculation
                # (Old stats kept computed in DataFrame so we don't lose them - now kept commented out for reference)
                # rt_df["Creation->Assigned"] = (
                #     rt_df["FirstAssignedDate"] - rt_df["CreationDate"]
                # ).dt.total_seconds() / 86400
                rt_df["Creation->Assigned"] = get_business_days(rt_df["CreationDate"], rt_df["FirstAssignedDate"])

                # rt_df["Assigned->Closed"] = (
                #     rt_df["ClosedDate"] - rt_df["FirstAssignedDate"]
                # ).dt.total_seconds() / 86400
                rt_df["Assigned->Closed"] = get_business_days(rt_df["FirstAssignedDate"], rt_df["ClosedDate"])

                # rt_df["Creation->Closed"] = (
                #     rt_df["ClosedDate"] - rt_df["CreationDate"]
                # ).dt.total_seconds() / 86400
                rt_df["Creation->Closed"] = get_business_days(rt_df["CreationDate"], rt_df["ClosedDate"])

                # rt_df["Creation->InProgress"] = (
                #     rt_df["FirstInProgressDate"] - rt_df["CreationDate"]
                # ).dt.total_seconds() / 86400
                rt_df["Creation->InProgress"] = get_business_days(rt_df["CreationDate"], rt_df["FirstInProgressDate"])

                # rt_df["InProgress->Closed"] = (
                #     rt_df["ClosedDate"] - rt_df["FirstInProgressDate"]
                # ).dt.total_seconds() / 86400
                rt_df["InProgress->Closed"] = get_business_days(rt_df["FirstInProgressDate"], rt_df["ClosedDate"])

                # Dynamic overall FirstResponseDate (backward compatibility)
                rt_df["FirstResponseDate"] = rt_df[["FirstInternalResponseDate", "FirstExternalResponseDate"]].min(axis=1)
                
                # rt_df["Creation->FirstResponse"] = (
                #     rt_df["FirstResponseDate"] - rt_df["CreationDate"]
                # ).dt.total_seconds() / 86400
                rt_df["Creation->FirstResponse"] = get_business_days(rt_df["CreationDate"], rt_df["FirstResponseDate"])

                # rt_df["Assigned->FirstResponse"] = (
                #     rt_df["FirstResponseDate"] - rt_df["FirstAssignedDate"]
                # ).dt.total_seconds() / 86400
                rt_df["Assigned->FirstResponse"] = get_business_days(rt_df["FirstAssignedDate"], rt_df["FirstResponseDate"])

                # New split stats (Colleague's additions)
                # rt_df["Creation->FirstInternalResponse"] = (
                #     rt_df["FirstInternalResponseDate"] - rt_df["CreationDate"]
                # ).dt.total_seconds() / 86400
                rt_df["Creation->FirstInternalResponse"] = get_business_days(rt_df["CreationDate"], rt_df["FirstInternalResponseDate"])

                # rt_df["Creation->FirstExternalResponse"] = (
                #     rt_df["FirstExternalResponseDate"] - rt_df["CreationDate"]
                # ).dt.total_seconds() / 86400
                rt_df["Creation->FirstExternalResponse"] = get_business_days(rt_df["CreationDate"], rt_df["FirstExternalResponseDate"])

                # rt_df["Assigned->FirstInternalResponse"] = (
                #     rt_df["FirstInternalResponseDate"] - rt_df["FirstAssignedDate"]
                # ).dt.total_seconds() / 86400
                rt_df["Assigned->FirstInternalResponse"] = get_business_days(rt_df["FirstAssignedDate"], rt_df["FirstInternalResponseDate"])

                # rt_df["FirstInternalResponse->Closed"] = (
                #     rt_df["ClosedDate"] - rt_df["FirstInternalResponseDate"]
                # ).dt.total_seconds() / 86400
                rt_df["FirstInternalResponse->Closed"] = get_business_days(rt_df["FirstInternalResponseDate"], rt_df["ClosedDate"])

                # rt_df["FirstExternalResponse->Closed"] = (
                #     rt_df["ClosedDate"] - rt_df["FirstExternalResponseDate"]
                # ).dt.total_seconds() / 86400
                rt_df["FirstExternalResponse->Closed"] = get_business_days(rt_df["FirstExternalResponseDate"], rt_df["ClosedDate"])

                # --- Awaiting Customer & Net calculations ---
                def sum_awaiting_time(row):
                    total_days = 0.0
                    creation = pd.to_datetime(row['CreationDate'])
                    closed = pd.to_datetime(row['ClosedDate'])
                    limit_end = closed if pd.notnull(closed) else pd.Timestamp.now()
                    
                    periods = [
                        (row['Start1'], row['End1']), (row['Start2'], row['End2']),
                        (row['Start3'], row['End3']), (row['Start4'], row['End4']),
                        (row['Start5'], row['End5']), (row['Start6'], row['End6'])
                    ]
                    
                    for start, end in periods:
                        if pd.notnull(start) and not pd.isna(start):
                            s = pd.to_datetime(start)
                            e = pd.to_datetime(end) if (pd.notnull(end) and not pd.isna(end)) else limit_end
                            
                            s_clipped = max(s, creation)
                            e_clipped = min(e, limit_end)
                            
                            if s_clipped < e_clipped:
                                val = get_business_days(pd.Series([s_clipped]), pd.Series([e_clipped])).iloc[0]
                                total_days += val
                    return total_days

                rt_df['TotalAwaitingDays'] = rt_df.apply(sum_awaiting_time, axis=1)

                rt_df["Net_Creation->Closed"] = None
                closed_mask = rt_df["ClosedDate"].notna()
                rt_df.loc[closed_mask, "Net_Creation->Closed"] = (
                    rt_df.loc[closed_mask, "Creation->Closed"] - rt_df.loc[closed_mask, "TotalAwaitingDays"]
                )
                rt_df.loc[closed_mask, "Net_Creation->Closed"] = rt_df.loc[closed_mask, "Net_Creation->Closed"].clip(lower=0)
                rt_df["Net_Creation->Closed"] = pd.to_numeric(rt_df["Net_Creation->Closed"], errors='coerce')

                st.session_state.rt_df = rt_df
                if "rt_filters_initialized" in st.session_state:
                    del st.session_state["rt_filters_initialized"]
                st.toast("✅ Επιτυχής φόρτωση δεδομένων KPIs!")
            except Exception as e:
                st.error(f"❌ Σφάλμα κατά τη σύνδεση ή τη φόρτωση από τη βάση: {e}")

    if st.session_state.rt_df is not None:
        rt_df = st.session_state.rt_df.copy()

        # Initialize filter session states if not already done
        if "rt_filters_initialized" not in st.session_state:
            has_loaded_default_preset = False
            if st.session_state.logged_in:
                default_preset = get_user_default_preset(st.session_state.user_id, "rt_filter_project")
                if default_preset:
                    import json
                    try:
                        filters = json.loads(default_preset["FiltersJSON"])
                        for k, v in filters.items():
                            if k in ["rt_filter_date", "rt_filter_closed_date"]:
                                st.session_state[k] = [pd.to_datetime(d).date() for d in v] if len(v) > 1 else pd.to_datetime(v[0]).date() if len(v) == 1 else datetime.now().date()
                            else:
                                st.session_state[k] = v
                        st.session_state.rt_active_preset_name = default_preset["PresetName"]
                        st.session_state.rt_active_preset_json = default_preset["FiltersJSON"]
                        has_loaded_default_preset = True
                    except Exception:
                        pass
            
            if not has_loaded_default_preset:
                st.session_state["rt_filter_project"] = sorted(rt_df["Project"].dropna().unique().tolist())
                st.session_state["rt_filter_status"] = sorted(rt_df["Status"].dropna().unique().tolist())
                st.session_state["rt_filter_subcategory"] = sorted(rt_df["SubCategory"].dropna().unique().tolist())
                import calendar
                today = datetime.now().date()
                start_of_month = today.replace(day=1)
                last_day = calendar.monthrange(today.year, today.month)[1]
                end_of_month = today.replace(day=last_day)
                st.session_state["rt_filter_date"] = [start_of_month, end_of_month]
                st.session_state["rt_use_closed_date"] = False
                st.session_state["rt_filter_closed_date"] = [start_of_month, end_of_month]
                st.session_state["rt_filter_assignee"] = sorted(rt_df["AssigneeName"].dropna().unique().tolist())
                st.session_state["rt_filter_components"] = sorted(rt_df["Components"].dropna().unique().tolist())
                st.session_state["rt_filter_partners"] = sorted(rt_df["PartnerName"].dropna().unique().tolist())
                st.session_state["rt_filter_customers"] = sorted(rt_df["CustomerName"].dropna().unique().tolist())
            
            st.session_state["rt_filters_initialized"] = True

        # Saved Previews section (only visible if logged in)
        if st.session_state.logged_in:
            rt_active_preset_name = st.session_state.get("rt_active_preset_name")
            rt_expander_title = "💾 Saved Previews (Presets) - Χρόνοι Απόκρισης"
            if rt_active_preset_name:
                rt_expander_title += f" (Ενεργό: {rt_active_preset_name})"
                
            with st.expander(rt_expander_title, expanded=False):
                presets = load_user_presets(st.session_state.user_id)
                rt_presets = [p for p in presets if "rt_filter_project" in p["FiltersJSON"]]
                
                def on_rt_preset_change():
                    val = st.session_state.rt_preset_select_widget
                    if val and val != "-- Επιλέξτε Preview --":
                        clean_name = val.replace(" (⭐ Προεπιλογή)", "")
                        selected_preset = next((p for p in rt_presets if p["PresetName"] == clean_name), None)
                        if selected_preset:
                            import json
                            try:
                                filters = json.loads(selected_preset["FiltersJSON"])
                                for k, v in filters.items():
                                    if k in ["rt_filter_date", "rt_filter_closed_date"]:
                                        st.session_state[k] = [pd.to_datetime(d).date() for d in v] if len(v) > 1 else pd.to_datetime(v[0]).date() if len(v) == 1 else datetime.now().date()
                                    else:
                                        st.session_state[k] = v
                                st.session_state.rt_active_preset_name = selected_preset["PresetName"]
                                st.session_state.rt_active_preset_json = selected_preset["FiltersJSON"]
                                st.toast("✅ Το Preview φορτώθηκε επιτυχώς!")
                            except Exception as e:
                                st.error(f"Σφάλμα κατά τη φόρτωση του preview: {e}")
                    st.session_state.rt_preset_select_widget = "-- Επιλέξτε Preview --"

                preset_names = ["-- Επιλέξτε Preview --"] + [
                    f"{p['PresetName']} (⭐ Προεπιλογή)" if p.get("IsDefault") else p["PresetName"]
                    for p in rt_presets
                ]
                
                selected_preset_name = st.selectbox(
                    "Φόρτωση Preview", 
                    options=preset_names, 
                    key="rt_preset_select_widget",
                    on_change=on_rt_preset_change
                )
                
                st.markdown("---")
                new_preset_name = st.text_input("Όνομα νέου Preview (Χρόνοι Απόκρισης)", placeholder="π.χ. Epic Support KPIs", key="rt_new_preset_name")
                if st.button("Αποθήκευση Τρέχοντος Φίλτρου", type="primary", width='stretch', key="rt_save_preset_btn"):
                    if new_preset_name.strip():
                        filters_dict = {
                            "rt_filter_project": st.session_state.get("rt_filter_project", []),
                            "rt_filter_status": st.session_state.get("rt_filter_status", []),
                            "rt_filter_subcategory": st.session_state.get("rt_filter_subcategory", []),
                            "rt_filter_date": [str(d) for d in st.session_state.get("rt_filter_date", [])] if isinstance(st.session_state.get("rt_filter_date"), (list, tuple)) else [str(st.session_state.get("rt_filter_date"))] if st.session_state.get("rt_filter_date") else [],
                            "rt_use_closed_date": st.session_state.get("rt_use_closed_date", False),
                            "rt_filter_closed_date": [str(d) for d in st.session_state.get("rt_filter_closed_date", [])] if isinstance(st.session_state.get("rt_filter_closed_date"), (list, tuple)) else [str(st.session_state.get("rt_filter_closed_date"))] if st.session_state.get("rt_filter_closed_date") else [],
                            "rt_filter_assignee": st.session_state.get("rt_filter_assignee", []),
                            "rt_filter_components": st.session_state.get("rt_filter_components", []),
                            "rt_filter_partners": st.session_state.get("rt_filter_partners", []),
                            "rt_filter_customers": st.session_state.get("rt_filter_customers", [])
                        }
                        import json
                        if save_user_preset(st.session_state.user_id, new_preset_name.strip(), json.dumps(filters_dict)):
                            st.toast("✅ Το Preview αποθηκεύτηκε!")
                            st.rerun()
                    else:
                        st.error("Εισάγετε ένα έγκυρο όνομα")
                        
                rt_active_preset_name = st.session_state.get("rt_active_preset_name")
                if rt_active_preset_name:
                    st.markdown("---")
                    st.markdown(f"📂 **Ενεργό Preview:** `{rt_active_preset_name}`")
                    
                    active_preset = next((p for p in rt_presets if p["PresetName"] == rt_active_preset_name), None)
                    is_default_active = active_preset.get("IsDefault", False) if active_preset else False
                    
                    if is_default_active:
                        st.markdown("⭐ **Προεπιλεγμένο Preview (αυτόματο)**")
                    else:
                        if st.button("⭐ Ορισμός ως Προεπιλογή", type="secondary", width='stretch', key="rt_set_default_preset_btn"):
                            if set_preset_as_default(st.session_state.user_id, rt_active_preset_name, "rt_filter_project"):
                                st.toast("✅ Ορίστηκε ως προεπιλεγμένο preview!")
                                st.rerun()
                                
                    col_update, col_reload, col_close = st.columns(3)
                    with col_update:
                        if st.button("💾 Ενημέρωση", type="primary", width='stretch', key="rt_update_preset_btn"):
                            filters_dict = {
                                "rt_filter_project": st.session_state.get("rt_filter_project", []),
                                "rt_filter_status": st.session_state.get("rt_filter_status", []),
                                "rt_filter_subcategory": st.session_state.get("rt_filter_subcategory", []),
                                "rt_filter_date": [str(d) for d in st.session_state.get("rt_filter_date", [])] if isinstance(st.session_state.get("rt_filter_date"), (list, tuple)) else [str(st.session_state.get("rt_filter_date"))] if st.session_state.get("rt_filter_date") else [],
                                "rt_use_closed_date": st.session_state.get("rt_use_closed_date", False),
                                "rt_filter_closed_date": [str(d) for d in st.session_state.get("rt_filter_closed_date", [])] if isinstance(st.session_state.get("rt_filter_closed_date"), (list, tuple)) else [str(st.session_state.get("rt_filter_closed_date"))] if st.session_state.get("rt_filter_closed_date") else [],
                                "rt_filter_assignee": st.session_state.get("rt_filter_assignee", []),
                                "rt_filter_components": st.session_state.get("rt_filter_components", []),
                                "rt_filter_partners": st.session_state.get("rt_filter_partners", []),
                                "rt_filter_customers": st.session_state.get("rt_filter_customers", [])
                            }
                            import json
                            new_json = json.dumps(filters_dict)
                            if update_user_preset(st.session_state.user_id, rt_active_preset_name, new_json):
                                st.session_state.rt_active_preset_json = new_json
                                st.toast("✅ Το Preview ενημερώθηκε επιτυχώς!")
                    with col_reload:
                        if st.button("🔄 Επαναφορά", type="secondary", width='stretch', key="rt_reload_preset_btn"):
                            if "rt_active_preset_json" in st.session_state:
                                import json
                                filters = json.loads(st.session_state.rt_active_preset_json)
                                for k, v in filters.items():
                                    if k in ["rt_filter_date", "rt_filter_closed_date"]:
                                        st.session_state[k] = [pd.to_datetime(d).date() for d in v] if len(v) > 1 else pd.to_datetime(v[0]).date() if len(v) == 1 else datetime.now().date()
                                    else:
                                        st.session_state[k] = v
                                st.toast("🔄 Τα αρχικά φίλτρα του Preview επαναφέρθηκαν!")
                                st.rerun()
                    with col_close:
                        if st.button("❌ Κλείσιμο", type="secondary", width='stretch', key="rt_close_preset_btn"):
                            clear_keys_and_rerun(["rt_active_preset_name", "rt_active_preset_json"])

                    st.markdown("---")
                    all_users = load_all_active_users()
                    other_users = [u for u in all_users if u["UserID"] != st.session_state.user_id]
                    other_user_names = [u["Username"] for u in other_users]
                    
                    st.markdown("**Κοινοποίηση σε χρήστες:**")
                    share_with = st.multiselect("Επιλέξτε Χρήστες", options=other_user_names, key="rt_preset_share_users_select")
                    if st.button("Κοινοποίηση", type="secondary", width='stretch', key="rt_preset_share_btn"):
                        if share_with:
                            shared_name = f"{rt_active_preset_name} (Shared by {st.session_state.username})"
                            success_users = []
                            for username in share_with:
                                target_user = next((u for u in other_users if u["Username"] == username), None)
                                if target_user:
                                    if save_user_preset(target_user["UserID"], shared_name, st.session_state.rt_active_preset_json):
                                        success_users.append(username)
                            if success_users:
                                st.success(f"Κοινοποιήθηκε επιτυχώς στους χρήστες: {', '.join(success_users)}!")

        # 1. Filters Grid
        with st.expander("🔍 Φίλτρα Αναζήτησης KPIs", expanded=False):
            # Clear button row (Commented out per user request)
            # col_btn_space, col_reset = st.columns([3, 1])
            # with col_reset:
            #     if st.button("🔄 Καθαρισμός Φίλτρων KPIs", type="secondary", width='stretch', key="rt_clear_filters_btn"):
            #         rt_filter_keys = [
            #             "rt_filter_project",
            #             "rt_filter_status",
            #             "rt_filter_subcategory",
            #             "rt_filter_date",
            #             "rt_filter_assignee",
            #             "rt_filter_components",
            #             "rt_filter_partners",
            #             "rt_filter_customers",
            #             "rt_active_preset_name",
            #             "rt_active_preset_json",
            #             "rt_group_key"
            #         ]
            #         for k in rt_filter_keys:
            #             if k in st.session_state:
            #                 del st.session_state[k]
            #         st.toast("🔄 Τα φίλτρα KPIs καθαρίστηκαν!")
            #         st.rerun()

            # Row 1 (4 columns)
            fcol1, fcol2, fcol3, fcol4 = st.columns(4)
            # Row 2 (4 columns)
            fcol5, fcol6, fcol7, fcol8 = st.columns(4)

            with fcol1:
                all_projects = sorted(rt_df["Project"].dropna().unique().tolist())
                selected_projects = st.multiselect("Ανά Project:", options=all_projects, key="rt_filter_project")
                if not selected_projects: selected_projects = all_projects

            with fcol2:
                all_statuses = sorted(rt_df["Status"].dropna().unique().tolist())
                selected_statuses = st.multiselect("Ανά Status:", options=all_statuses, key="rt_filter_status")
                if not selected_statuses: selected_statuses = all_statuses

            with fcol3:
                all_subcategories = sorted(rt_df["SubCategory"].dropna().unique().tolist())
                selected_subcategories = st.multiselect("Ανά Sub Category:", options=all_subcategories, key="rt_filter_subcategory")
                if not selected_subcategories: selected_subcategories = all_subcategories

            with fcol4:
                import calendar
                today_dt = datetime.now().date()
                start_of_month_dt = today_dt.replace(day=1)
                last_day_dt = calendar.monthrange(today_dt.year, today_dt.month)[1]
                end_of_month_dt = today_dt.replace(day=last_day_dt)

                default_creation = st.session_state.get("rt_filter_date")
                if not isinstance(default_creation, (list, tuple)) or not default_creation:
                    st.session_state["rt_filter_date"] = [start_of_month_dt, end_of_month_dt]

                date_range = st.date_input(
                    "Εύρος Ημερολογίου (Creation):",
                    key="rt_filter_date"
                )
                use_closed_date = st.checkbox("Φίλτρο Ημ. Κλεισίματος", key="rt_use_closed_date")
                if use_closed_date:
                    default_closed = st.session_state.get("rt_filter_closed_date")
                    if not isinstance(default_closed, (list, tuple)) or not default_closed:
                        st.session_state["rt_filter_closed_date"] = [start_of_month_dt, end_of_month_dt]
                    closed_date_range = st.date_input(
                        "Εύρος Ημερολογίου (Closure):",
                        key="rt_filter_closed_date"
                    )
                else:
                    closed_date_range = None

            with fcol5:
                all_assignees = sorted(rt_df["AssigneeName"].dropna().unique().tolist())
                selected_assignees = st.multiselect("Ανά Assignee:", options=all_assignees, key="rt_filter_assignee")
                if not selected_assignees: selected_assignees = all_assignees

            with fcol6:
                all_components = sorted(rt_df["Components"].dropna().unique().tolist())
                selected_components = st.multiselect("Ανά Components:", options=all_components, key="rt_filter_components")
                if not selected_components: selected_components = all_components

            with fcol7:
                all_partners = sorted(rt_df["PartnerName"].dropna().unique().tolist())
                selected_partners = st.multiselect("Ανά Partner Name:", options=all_partners, key="rt_filter_partners")
                if not selected_partners: selected_partners = all_partners

            with fcol8:
                all_customers = sorted(rt_df["CustomerName"].dropna().unique().tolist())
                selected_customers = st.multiselect("Ανά LSP Customer:", options=all_customers, key="rt_filter_customers")
                if not selected_customers: selected_customers = all_customers

        # Parse Date Range
        if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
            start_date, end_date = date_range
        elif isinstance(date_range, (list, tuple)) and len(date_range) == 1:
            start_date = date_range[0]
            end_date = start_date
        elif isinstance(date_range, (list, tuple)) and len(date_range) == 0:
            start_date = datetime.now().date()
            end_date = start_date
        else:
            start_date = date_range
            end_date = start_date

        # Parse Closed Date Range
        use_closed_date = st.session_state.get("rt_use_closed_date", False)
        closed_start, closed_end = None, None
        if use_closed_date and closed_date_range:
            if isinstance(closed_date_range, (list, tuple)) and len(closed_date_range) == 2:
                closed_start, closed_end = closed_date_range
            elif isinstance(closed_date_range, (list, tuple)) and len(closed_date_range) == 1:
                closed_start = closed_date_range[0]
                closed_end = closed_start
            elif isinstance(closed_date_range, (list, tuple)) and len(closed_date_range) == 0:
                closed_start = datetime.now().date()
                closed_end = closed_start
            else:
                closed_start = closed_date_range
                closed_end = closed_date_range

        # Apply Date-Only Filters
        date_filtered_rt_df = rt_df[
            (rt_df["CreationDate"].dt.date >= start_date) &
            (rt_df["CreationDate"].dt.date <= end_date)
        ]
        if use_closed_date and closed_start and closed_end:
            date_filtered_rt_df = date_filtered_rt_df[
                date_filtered_rt_df["ClosedDate"].notna() &
                (date_filtered_rt_df["ClosedDate"].dt.date >= closed_start) &
                (date_filtered_rt_df["ClosedDate"].dt.date <= closed_end)
            ]

        # Apply Attribute Filters on top of Date-Only Filtered DataFrame
        filtered_rt_df = date_filtered_rt_df[
            (date_filtered_rt_df["Status"].isin(selected_statuses)) &
            (date_filtered_rt_df["Project"].isin(selected_projects)) &
            (date_filtered_rt_df["SubCategory"].isin(selected_subcategories)) &
            (date_filtered_rt_df["Components"].isin(selected_components)) &
            (date_filtered_rt_df["PartnerName"].isin(selected_partners)) &
            (date_filtered_rt_df["CustomerName"].isin(selected_customers)) &
            (date_filtered_rt_df["AssigneeName"].isin(selected_assignees))
        ].copy()

        # Check for empty dataframe
        if filtered_rt_df.empty:
            st.warning("Δεν βρέθηκαν αποτελέσματα με τα τρέχοντα φίλτρα.")
        else:
            # 2. KPI Summary
            st.write("<br>", unsafe_allow_html=True)
            st.subheader("📊 KPI Summary")
            st.caption("ℹ️ **Σημείωση**: Ο δείκτης **Net Creation → Closed** λειτουργεί ορθά μόνο με τελικά statuses αιτημάτων (Closed).")
            col1, col2, col3, col4, col5, col6, col7, col8, col9 = st.columns(9)
            col1.metric("Filtered Tickets", len(filtered_rt_df), help="Αιτήματα που ικανοποιούν όλα τα ενεργά φίλτρα.")
            col2.metric("Creation → Assigned", rt_safe_mean(filtered_rt_df["Creation->Assigned"]))
            col3.metric("Creation → InProgress", rt_safe_mean(filtered_rt_df["Creation->InProgress"]))
            col4.metric("Creation->FirstExternalResponse", rt_safe_mean(filtered_rt_df["Creation->FirstExternalResponse"]))
            col5.metric("InProgress → Closed", rt_safe_mean(filtered_rt_df["InProgress->Closed"]))
            col6.metric("External Resp → Closed", rt_safe_mean(filtered_rt_df["FirstExternalResponse->Closed"]))
            col7.metric("Creation → Closed", rt_safe_mean(filtered_rt_df["Creation->Closed"]))
            col8.metric("Total Awaiting", rt_safe_mean(filtered_rt_df["TotalAwaitingDays"]), help="Συνολικός χρόνος αναμονής (Awaiting Customer) σε εργάσιμες ημέρες.")
            col9.metric("Net Creation → Closed", rt_safe_mean(filtered_rt_df["Net_Creation->Closed"]), help="Καθαρός κύκλος κλεισίματος. Λειτουργεί ορθά μόνο με τελικά statuses αιτημάτων (Closed).")            

            # Old / Hidden metrics kept in comments as requested:
            # col_hidden1.metric("Total Tickets", len(date_filtered_rt_df), help="Συνολικά αιτήματα στο επιλεγμένο ημερολογιακό εύρος (Created & Closed).")
            # col_hidden2.metric("Creation → Assigned (days)", rt_safe_mean(filtered_rt_df["Creation->Assigned"]))
            # col_hidden3.metric("Creation → First Response (days)", rt_safe_mean(filtered_rt_df["Creation->FirstResponse"]))
            # col_hidden4.metric("Assigned → First Response (days)", rt_safe_mean(filtered_rt_df["Assigned->FirstResponse"]))
            # col_hidden5.metric("Assigned → Closed (days)", rt_safe_mean(filtered_rt_df["Assigned->Closed"]))
            # col_hidden6.metric("Creation->FirstInternalResponse", rt_safe_mean(filtered_rt_df["Creation->FirstInternalResponse"]))
            # col_hidden7.metric("Internal Resp → Closed", rt_safe_mean(filtered_rt_df["FirstInternalResponse->Closed"]))

            st.markdown("---")
            st.info("ℹ️ **Σημείωση SLA**: Οι χρόνοι υπολογίζονται αυτόματα με βάση εργάσιμο SLA 8ώρου (Δευτέρα - Παρασκευή 9πμ - 5μμ), εξαιρώντας τα Σαββατοκύριακα.")

            # 3. Group By Selection
            group_options = ["Project", "AssigneeName", "Status", "SubCategory", "PartnerName", "CustomerName", "Components"]
            sel_group = st.multiselect("🗂️ Ομαδοποίηση (Group By) ανά:", options=group_options, key="rt_group_key")

            if sel_group:
                # Aggregation mapping
                agg_dict = {
                    "IssueKey": "count",
                    "Creation->Assigned": "mean",
                    # "Creation->FirstResponse": "mean",
                    # "Assigned->FirstResponse": "mean",
                    # "Assigned->Closed": "mean",
                    # "Creation->FirstInternalResponse": "mean",
                    "Creation->InProgress": "mean",
                    "Creation->FirstExternalResponse": "mean",
                    "InProgress->Closed": "mean",
                    # "FirstInternalResponse->Closed": "mean",
                    "FirstExternalResponse->Closed": "mean",
                    "Creation->Closed": "mean",
                    "TotalAwaitingDays": "mean",
                    "Net_Creation->Closed": "mean"
                }
                # Group by and aggregate
                grouped_df = filtered_rt_df.groupby(sel_group).agg(agg_dict).reset_index()
                # Rename columns
                grouped_df = grouped_df.rename(columns={"IssueKey": "Filtered Tickets"})

                # Total count (only date filtered)
                total_counts_df = date_filtered_rt_df.groupby(sel_group)["IssueKey"].count().reset_index()
                total_counts_df = total_counts_df.rename(columns={"IssueKey": "Total Tickets"})

                # Merge
                grouped_df = pd.merge(grouped_df, total_counts_df, on=sel_group, how="left").fillna(0)
                grouped_df["Total Tickets"] = grouped_df["Total Tickets"].astype(int)

                grouped_df = grouped_df.rename(columns={
                    "Creation->Assigned": "Creation → Assigned (Mean Days)",
                    # "Creation->FirstResponse": "Creation → First Response (Mean Days)",
                    # "Assigned->FirstResponse": "Assigned → First Response (Mean Days)",
                    # "Assigned->Closed": "Assigned → Closed (Mean Days)",
                    # "Creation->FirstInternalResponse": "Creation->FirstInternalResponse (Mean Days)",
                    "Creation->InProgress": "Creation → InProgress (Mean Days)",
                    "Creation->FirstExternalResponse": "Creation->FirstExternalResponse (Mean Days)",
                    "InProgress->Closed": "InProgress → Closed (Mean Days)",
                    # "FirstInternalResponse->Closed": "Internal Resp → Closed (Mean Days)",
                    "FirstExternalResponse->Closed": "External Resp → Closed (Mean Days)",
                    "Creation->Closed": "Creation → Closed (Mean Days)",
                    "TotalAwaitingDays": "Total Awaiting (Mean Days)",
                    "Net_Creation->Closed": "Net Creation → Closed (Mean Days)"
                })

                # Reorder columns
                kpi_cols = [
                    "Creation → Assigned (Mean Days)",
                    "Creation → InProgress (Mean Days)",
                    "Creation->FirstExternalResponse (Mean Days)",
                    "InProgress → Closed (Mean Days)",
                    "External Resp → Closed (Mean Days)",
                    "Creation → Closed (Mean Days)",
                    "Total Awaiting (Mean Days)",
                    "Net Creation → Closed (Mean Days)"
                ]
                existing_kpi_cols = [c for c in kpi_cols if c in grouped_df.columns]
                grouped_df = grouped_df[sel_group + ["Filtered Tickets", "Total Tickets"] + existing_kpi_cols]
                
                st.subheader("📊 KPIs Grouped Summary")
                st.dataframe(
                    grouped_df,
                    width='stretch',
                    height=400,
                    column_config={
                        "Filtered Tickets": st.column_config.NumberColumn("Filtered Tickets", format="%d", help="Αιτήματα που ικανοποιούν όλα τα ενεργά φίλτρα."),
                        "Total Tickets": st.column_config.NumberColumn("Total Tickets", format="%d", help="Συνολικά αιτήματα στο επιλεγμένο ημερολογιακό εύρος (Created & Closed), αγνοώντας τα άλλα φίλτρα."),
                        "Creation → Assigned (Mean Days)": st.column_config.NumberColumn("Creation → Assigned (Avg Days)", format="%.2f"),
                        # "Creation → First Response (Mean Days)": st.column_config.NumberColumn("Creation → First Response (Avg Days)", format="%.2f"),
                        # "Assigned → First Response (Mean Days)": st.column_config.NumberColumn("Assigned → First Response (Avg Days)", format="%.2f"),
                        # "Assigned → Closed (Mean Days)": st.column_config.NumberColumn("Assigned → Closed (Avg Days)", format="%.2f"),
                        # "Creation->FirstInternalResponse (Mean Days)": st.column_config.NumberColumn("Creation->FirstInternalResponse (Avg Days)", format="%.2f"),
                        "Creation → InProgress (Mean Days)": st.column_config.NumberColumn("Creation → InProgress (Avg Days)", format="%.2f"),
                        "Creation->FirstExternalResponse (Mean Days)": st.column_config.NumberColumn("Creation->FirstExternalResponse (Avg Days)", format="%.2f"),
                        "InProgress → Closed (Mean Days)": st.column_config.NumberColumn("InProgress → Closed (Avg Days)", format="%.2f"),
                        # "Internal Resp → Closed (Mean Days)": st.column_config.NumberColumn("Internal Resp → Closed (Avg Days)", format="%.2f"),
                        "External Resp → Closed (Mean Days)": st.column_config.NumberColumn("External Resp → Closed (Avg Days)", format="%.2f"),
                        "Creation → Closed (Mean Days)": st.column_config.NumberColumn("Creation → Closed (Avg Days)", format="%.2f"),
                        "Total Awaiting (Mean Days)": st.column_config.NumberColumn("Total Awaiting (Avg Days)", format="%.2f"),
                        "Net Creation → Closed (Mean Days)": st.column_config.NumberColumn("Net Creation → Closed (Avg Days)", format="%.2f", help="Καθαρός κύκλος κλεισίματος. Λειτουργεί ορθά μόνο με τελικά statuses αιτημάτων (Closed)."),
                    }
                )
                
                # Download button
                excel_data = rt_convert_df_to_excel(grouped_df)
                st.download_button(
                    label="📥 Λήψη σε Excel",
                    data=excel_data,
                    file_name="jira_kpi_grouped.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    type="primary",
                    key="rt_download_btn_grouped"
                )
            else:
                # 3. Column Ordering & Config (Detailed view)
                column_order = [
                    "ProjectId", "IssueKey", "Project", "Type", "JiraLink", "AssigneeName", "Components", 
                    "PartnerName", "CustomerName", "Status", "SubCategory", "CreationDate", 
                    "FirstAssignedDate", 
                    "FirstInProgressDate",
                    # "FirstResponseDate",
                    # "FirstInternalResponseDate",
                    "FirstExternalResponseDate",
                    "ClosedDate",
                    "Creation->Assigned",
                    # "Creation->FirstResponse",
                    # "Assigned->FirstResponse",
                    # "Assigned->Closed",
                    # "Creation->FirstInternalResponse",
                    "Creation->InProgress",
                    "Creation->FirstExternalResponse",
                    "InProgress->Closed",
                    # "FirstInternalResponse->Closed",
                    "FirstExternalResponse->Closed",
                    "Creation->Closed",
                    "TotalAwaitingDays",
                    "Net_Creation->Closed"
                ]
                existing_cols = [c for c in column_order if c in filtered_rt_df.columns]
                display_df = filtered_rt_df[existing_cols]

                st.subheader("📊 KPIs by Issue")
                st.dataframe(
                    display_df,
                    width='stretch',
                    height=500,
                    column_config={
                        "ProjectId": st.column_config.NumberColumn("Project ID", width=90, format="%d"),
                        "IssueKey": st.column_config.TextColumn("Ticket Key", width=110),
                        "Project": st.column_config.TextColumn("Project", width=100),
                        "Type": st.column_config.TextColumn("Type", width=90),
                        "JiraLink": st.column_config.LinkColumn("Jira", width=90, display_text="Open"),
                        "AssigneeName": st.column_config.TextColumn("Assignee", width=150),
                        "Components": st.column_config.TextColumn("Components", width=150),
                        "PartnerName": st.column_config.TextColumn("Partner Name", width=200),
                        "CustomerName": st.column_config.TextColumn("Customer Name", width=200),
                        "Status": st.column_config.TextColumn("Status", width=110),
                        "SubCategory": st.column_config.TextColumn("Sub Category", width=180),
                        "CreationDate": st.column_config.DatetimeColumn("Creation Date", width=160, format="DD/MM/YYYY HH:mm"),
                        "FirstAssignedDate": st.column_config.DatetimeColumn("First Assigned Date", width=160, format="DD/MM/YYYY HH:mm"),
                        "FirstInProgressDate": st.column_config.DatetimeColumn("First In Progress Date", width=160, format="DD/MM/YYYY HH:mm"),
                        # "FirstResponseDate": st.column_config.DatetimeColumn("First Response Date", width=160, format="DD/MM/YYYY HH:mm"),
                        # "FirstInternalResponseDate": st.column_config.DatetimeColumn("First Internal Response", width=160, format="DD/MM/YYYY HH:mm"),
                        "FirstExternalResponseDate": st.column_config.DatetimeColumn("First External Response", width=160, format="DD/MM/YYYY HH:mm"),
                        "ClosedDate": st.column_config.DatetimeColumn("Closed Date", width=160, format="DD/MM/YYYY HH:mm"),
                        "Creation->Assigned": st.column_config.NumberColumn("Creation → Assigned (Days)", width=240, format="%.2f"),
                        # "Creation->FirstResponse": st.column_config.NumberColumn("Creation → First Response (Days)", width=240, format="%.2f"),
                        # "Assigned->FirstResponse": st.column_config.NumberColumn("Assigned → First Response (Days)", width=240, format="%.2f"),
                        # "Assigned->Closed": st.column_config.NumberColumn("Assigned → Closed (Days)", width=240, format="%.2f"),
                        # "Creation->FirstInternalResponse": st.column_config.NumberColumn("Creation->FirstInternalResponse (Days)", width=220, format="%.2f"),
                        "Creation->InProgress": st.column_config.NumberColumn("Creation → InProgress (Days)", width=220, format="%.2f"),
                        "Creation->FirstExternalResponse": st.column_config.NumberColumn("Creation->FirstExternalResponse (Days)", width=220, format="%.2f"),
                        "InProgress->Closed": st.column_config.NumberColumn("InProgress → Closed (Days)", width=220, format="%.2f"),
                        # "FirstInternalResponse->Closed": st.column_config.NumberColumn("Internal Resp → Closed (Days)", width=220, format="%.2f"),
                        "FirstExternalResponse->Closed": st.column_config.NumberColumn("External Resp → Closed (Days)", width=220, format="%.2f"),
                        "Creation->Closed": st.column_config.NumberColumn("Creation → Closed (Days)", width=220, format="%.2f"),
                        "TotalAwaitingDays": st.column_config.NumberColumn("Total Awaiting (Days)", width=220, format="%.2f", help="Συνολικός χρόνος αναμονής (Awaiting Customer) σε εργάσιμες ημέρες."),
                        "Net_Creation->Closed": st.column_config.NumberColumn("Net Creation → Closed (Days)", width=220, format="%.2f", help="Καθαρός κύκλος κλεισίματος. Λειτουργεί ορθά μόνο με τελικά statuses αιτημάτων (Closed)."),
                    }
                )

                # Download Button
                excel_data = rt_convert_df_to_excel(display_df)
                st.download_button(
                    label="📥 Λήψη σε Excel",
                    data=excel_data,
                    file_name="jira_kpi_filtered.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    type="primary",
                    key="rt_download_btn_detailed"
                )

        st.markdown("---")

        # 4. Data Errors Expander
        errors_df = rt_df[
            (rt_df["Creation->Assigned"] < 0) |
            (rt_df["Creation->FirstInternalResponse"] < 0) |
            (rt_df["Creation->FirstExternalResponse"] < 0) |
            (rt_df["Creation->InProgress"] < 0) |
            (rt_df["InProgress->Closed"] < 0) |
            (rt_df["FirstInternalResponse->Closed"] < 0) |
            (rt_df["FirstExternalResponse->Closed"] < 0) |
            (rt_df["Creation->Closed"] < 0)
        ][["IssueKey", "JiraLink", "Status", "CreationDate", "FirstAssignedDate", 
           "FirstInProgressDate",
           # "FirstInternalResponseDate", 
           "FirstExternalResponseDate", "ClosedDate"]].copy()

        with st.expander("⚠️ Πίνακας Ελέγχου Δεδομένων (Λάθη Χρηστών)", expanded=False):
            st.warning(f"Βρέθηκαν {len(errors_df)} tickets με αρνητικούς χρόνους λόγω λάθος καταχώρησης ημερομηνιών στο Jira.")
            if not errors_df.empty:
                st.dataframe(
                    errors_df,
                    width='stretch',
                    column_config={
                        "IssueKey": st.column_config.TextColumn("Ticket Key", width=110),
                        "JiraLink": st.column_config.LinkColumn("Jira", width=110, display_text="Open Ticket"),
                        "Status": st.column_config.TextColumn("Status", width=110),
                        "CreationDate": st.column_config.DatetimeColumn("Creation Date", width=160, format="DD/MM/YYYY HH:mm"),
                        "FirstAssignedDate": st.column_config.DatetimeColumn("First Assigned Date", width=160, format="DD/MM/YYYY HH:mm"),
                        "FirstInProgressDate": st.column_config.DatetimeColumn("First In Progress Date", width=160, format="DD/MM/YYYY HH:mm"),
                        # "FirstInternalResponseDate": st.column_config.DatetimeColumn("First Internal Response", width=160, format="DD/MM/YYYY HH:mm"),
                        "FirstExternalResponseDate": st.column_config.DatetimeColumn("First External Response", width=160, format="DD/MM/YYYY HH:mm"),
                        "ClosedDate": st.column_config.DatetimeColumn("Closed Date", width=160, format="DD/MM/YYYY HH:mm")
                    }
                )
            else:
                st.success("Όλα καθαρά! Δεν βρέθηκαν λάθη στις ημερομηνίες.")

def render_markdown_with_mermaid(file_path):
    if os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            import streamlit.components.v1 as components
            
            # Split content into markdown parts and mermaid diagram parts
            pattern = r"```mermaid\s*\n(.*?)\n```"
            parts = re.split(pattern, content, flags=re.DOTALL)
            
            for i, part in enumerate(parts):
                if i % 2 == 0:
                    # Markdown part
                    if part.strip():
                        st.markdown(part, unsafe_allow_html=True)
                else:
                    # Mermaid part
                    mermaid_code = part.strip()
                    num_lines = len(mermaid_code.splitlines())
                    height = max(150, num_lines * 45)
                    
                    html_code = f"""
                    <div class="mermaid" style="display: flex; justify-content: center; align-items: center;">
                    {mermaid_code}
                    </div>
                    <script type="module">
                        import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs';
                        mermaid.initialize({{ 
                            startOnLoad: true,
                            theme: 'default',
                            securityLevel: 'loose'
                        }});
                    </script>
                    """
                    components.html(html_code, height=height, scrolling=True)
        except Exception as e:
            st.error(f"Σφάλμα κατά την ανάγνωση ή εμφάνιση του αρχείου {file_path}: {str(e)}")
    else:
        st.error(f"Το αρχείο {file_path} δεν βρέθηκε.")

def run_etl_subprocess_statement(statement_str, description):
    import subprocess
    import sys
    import os
    
    st.write(f"### 🖥️ Κονσόλα: {description}")
    console_placeholder = st.empty()
    log_lines = []
    
    # Force Python subprocess to output in UTF-8 to prevent charmap/encoding crashes on Windows
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    
    # Run the Python interpreter as a subprocess with unbuffered output (-u)
    # Read binary (text=False) to handle multi-encoding safe fallbacks on Windows
    process = subprocess.Popen(
        [sys.executable, "-u", "-c", statement_str],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=False,
        env=env,
        bufsize=1
    )
    
    # Stream output line-by-line
    for raw_line in iter(process.stdout.readline, b""):
        try:
            line = raw_line.decode("utf-8")
        except UnicodeDecodeError:
            try:
                line = raw_line.decode("cp1253")  # Greek Windows encoding fallback
            except UnicodeDecodeError:
                line = raw_line.decode("cp1252", errors="replace")  # ANSI fallback with replacement chars
                
        log_lines.append(line)
        # Keep last 150 lines to prevent UI lag
        console_placeholder.code("".join(log_lines[-150:]))
        
    process.wait()
    return process.returncode == 0

def queue_etl_job(job_type, issue_key=None, start_date=None, end_date=None, date_type=None, created_by=None):
    engine = get_db_engine()
    if not engine:
        return None
    from sqlalchemy import text
    try:
        with engine.begin() as conn:
            query = text("""
                INSERT INTO ETL_Queue (JobType, IssueKey, StartDate, EndDate, DateFilterType, Status, CreatedBy)
                OUTPUT INSERTED.JobID
                VALUES (:job_type, :issue_key, :start_date, :end_date, :date_type, 'Pending', :created_by)
            """)
            row = conn.execute(query, {
                "job_type": job_type,
                "issue_key": issue_key,
                "start_date": start_date,
                "end_date": end_date,
                "date_type": date_type,
                "created_by": created_by or "System"
            }).fetchone()
            if row:
                return row[0]
    except Exception as e:
        st.error(f"Σφάλμα κατά την καταχώρηση της εργασίας στην ουρά: {e}")
        return None

def render_etl_manager_content():
    st.subheader("🚀 Data Warehouse ETL Manager", divider="blue")
    st.markdown("Διαχειριστικό περιβάλλον για τον συγχρονισμό δεδομένων από Gemini και Jira στο SQL Server.")

    # Δημιουργία Tabs (Καρτέλες) μέσα στο κυρίως Tab του μενού
    tab_actions, tab_full_sync, tab_jira_full_sync, tab_debugger, tab_queue_monitor, tab_dev_docs, tab_migration = st.tabs([
        "⚡ Μεμονωμένες Ενέργειες", 
        "📦 Μαζικός Συγχρονισμός", 
        "🎫 Jira Full Sync (Από Μηδέν)",
        "🔍 ETL Debugger & Sync",
        "🖥️ ETL Job Monitor",
        "📖 Dev Docs",
        "🔄 Gemini ➔ Jira Migration"
    ])

    with tab_actions:
        st.write("Συγχρονισμός ανά Οντότητα (Dimensions & Facts)")
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            if st.button("🏢 Sync Projects", width='stretch'):
                job_id = queue_etl_job('SYNC_PROJECTS', created_by=st.session_state.user_id)
                if job_id:
                    write_system_log(
                        st.session_state.user_id, 
                        "ETL_QUEUE_PROJECTS", 
                        f"Καταχώρηση στην ουρά εργασίας συγχρονισμού Projects (Job ID: #{job_id})"
                    )
                    st.success(f"🎉 Η εργασία συγχρονισμού Projects καταχωρήθηκε στην ουρά (Job ID: #{job_id}).")
                    st.rerun()
                else:
                    st.error("Αποτυχία καταχώρησης της εργασίας στην ουρά.")

        with col2:
            if st.button("👥 Sync Users", width='stretch'):
                job_id = queue_etl_job('SYNC_USERS', created_by=st.session_state.user_id)
                if job_id:
                    write_system_log(
                        st.session_state.user_id, 
                        "ETL_QUEUE_USERS", 
                        f"Καταχώρηση στην ουρά εργασίας συγχρονισμού Users (Job ID: #{job_id})"
                    )
                    st.success(f"🎉 Η εργασία συγχρονισμού Users καταχωρήθηκε στην ουρά (Job ID: #{job_id}).")
                    st.rerun()
                else:
                    st.error("Αποτυχία καταχώρησης της εργασίας στην ουρά.")

        with col3:
            if st.button("🧩 Sync Components", width='stretch'):
                job_id = queue_etl_job('SYNC_COMPONENTS', created_by=st.session_state.user_id)
                if job_id:
                    write_system_log(
                        st.session_state.user_id, 
                        "ETL_QUEUE_COMPONENTS", 
                        f"Καταχώρηση στην ουρά εργασίας συγχρονισμού Components (Job ID: #{job_id})"
                    )
                    st.success(f"🎉 Η εργασία συγχρονισμού Components καταχωρήθηκε στην ουρά (Job ID: #{job_id}).")
                    st.rerun()
                else:
                    st.error("Αποτυχία καταχώρησης της εργασίας στην ουρά.")

        with col4:
            if st.button("🎫 Sync Issues", width='stretch', type="primary"):
                job_id = queue_etl_job('SYNC_ISSUES_INCREMENTAL', created_by=st.session_state.user_id)
                if job_id:
                    write_system_log(
                        st.session_state.user_id, 
                        "ETL_QUEUE_ISSUES", 
                        f"Καταχώρηση στην ουρά εργασίας incremental συγχρονισμού Issues & Children (Job ID: #{job_id})"
                    )
                    st.success(f"🎉 Η εργασία incremental συγχρονισμού Issues καταχωρήθηκε στην ουρά (Job ID: #{job_id}).")
                    st.rerun()
                else:
                    st.error("Αποτυχία καταχώρησης της εργασίας στην ουρά.")

    with tab_full_sync:
        st.write("Πλήρης Συγχρονισμός (Full Pipeline)")
        st.info("Εκτελείται με την ασφαλή σειρά: Projects ➔ Users ➔ Components ➔ Issues")
        
        if st.button("🚀 ΕΚΚΙΝΗΣΗ FULL SYNC", type="primary"):
            job_id = queue_etl_job('FULL_SYNC', created_by=st.session_state.user_id)
            if job_id:
                write_system_log(
                    st.session_state.user_id, 
                    "ETL_QUEUE_FULL_SYNC", 
                    f"Καταχώρηση στην ουρά εργασίας Full Sync Pipeline (Job ID: #{job_id})"
                )
                st.success(f"🎉 Η εργασία Full Sync Pipeline καταχωρήθηκε στην ουρά (Job ID: #{job_id}).")
                st.rerun()
            else:
                st.error("Αποτυχία καταχώρησης της εργασίας στην ουρά.")

    with tab_jira_full_sync:
        st.write("Πλήρης Συγχρονισμός Jira (Από Μηδέν)")
        st.info("Συγχρονίζει μόνο τις Jira οντότητες (Projects ➔ Users ➔ Components ➔ Issues) από το μηδέν, αγνοώντας την ημερομηνία τελευταίου συγχρονισμού.")
        
        if st.button("🚀 ΕΚΚΙΝΗΣΗ JIRA FULL SYNC", type="primary", key="jira_full_sync_btn"):
            job_id = queue_etl_job('JIRA_FULL_SYNC', created_by=st.session_state.user_id)
            if job_id:
                write_system_log(
                    st.session_state.user_id, 
                    "ETL_QUEUE_JIRA_FULL_SYNC", 
                    f"Καταχώρηση στην ουρά εργασίας Jira Full Sync Pipeline (Job ID: #{job_id})"
                )
                st.success(f"🎉 Η εργασία Jira Full Sync Pipeline καταχωρήθηκε στην ουρά (Job ID: #{job_id}).")
                st.rerun()
            else:
                st.error("Αποτυχία καταχώρησης της εργασίας στην ουρά.")

    with tab_debugger:
        col_debug1, col_debug2 = st.columns(2)
        
        with col_debug1:
            st.write("🔍 Διάγνωση & Συγχρονισμός Μεμονωμένου Issue")
            st.info(
                "Χρησιμοποιήστε αυτή την ενότητα για να ελέγξετε αν κάποιο συγκεκριμένο Jira Issue συγχρονίζεται σωστά. "
                "Η κονσόλα στον Job Monitor θα εμφανίσει αναλυτικές πληροφορίες μετασχηματισμού και τυχόν σφάλματα (stack traces)."
            )
            
            # Πεδίο κειμένου για την εισαγωγή του Key
            debug_issue_key = st.text_input(
                "Jira Issue Key (π.χ. PYLCOM-536):", 
                placeholder="Εισάγετε το Key του εισιτηρίου...",
                key="etl_debug_issue_key"
            ).strip()
            
            if st.button("🔄 Συγχρονισμός & Debugging Issue", type="primary", key="etl_debug_sync_btn"):
                if not debug_issue_key:
                    st.warning("Παρακαλώ εισάγετε ένα έγκυρο Issue Key (π.χ. PYLCOM-536) πριν ξεκινήσετε.")
                else:
                    job_id = queue_etl_job('SINGLE_ISSUE_SYNC', issue_key=debug_issue_key, created_by=st.session_state.user_id)
                    if job_id:
                        write_system_log(
                            st.session_state.user_id, 
                            "ETL_QUEUE_DEBUG_ISSUE", 
                            f"Καταχώρηση στην ουρά εργασίας συγχρονισμού μεμονωμένου Issue '{debug_issue_key}' (Job ID: #{job_id})"
                        )
                        st.success(f"🎉 Η εργασία συγχρονισμού του Issue '{debug_issue_key}' καταχωρήθηκε στην ουρά (Job ID: #{job_id}).")
                        st.rerun()
                    else:
                        st.error("Αποτυχία καταχώρησης της εργασίας στην ουρά.")

        with col_debug2:
            st.write("📅 Συγχρονισμός Jira Issues βάσει Ημερομηνιών")
            st.info(
                "Συγχρονίζει όλα τα Jira Issues που είχαν δραστηριότητα ή δημιουργήθηκαν κατά το επιλεγμένο διάστημα. "
                "Η ενέργεια θα προστεθεί στην ουρά και θα εκτελεστεί αυτόματα από τον Background Worker."
            )
            
            # Date pickers
            col_start, col_end = st.columns(2)
            with col_start:
                range_start_date = st.date_input("Ημερομηνία Έναρξης (Start Date):", key="etl_range_start_date")
            with col_end:
                range_end_date = st.date_input("Ημερομηνία Λήξης (End Date):", key="etl_range_end_date")
                
            # Date filter type radio
            range_date_type = st.radio(
                "Φιλτράρισμα βάσει ημερομηνίας:",
                ["Τελευταίας Ενημέρωσης (Updated - Προτείνεται)", "Δημιουργίας (Created)"],
                key="etl_range_date_type",
                horizontal=True
            )
            
            date_type_val = "updated" if "Updated" in range_date_type or "Ενημέρωσης" in range_date_type else "created"
            
            if st.button("📅 Ουρά συγχρονισμού εύρους ημερομηνιών", type="primary", key="etl_range_sync_btn"):
                if range_start_date > range_end_date:
                    st.error("Η ημερομηνία έναρξης δεν μπορεί να είναι μεταγενέστερη της ημερομηνίας λήξης.")
                else:
                    start_str = f"{range_start_date} 00:00"
                    end_str = f"{range_end_date} 23:59"
                    
                    job_id = queue_etl_job(
                        job_type='DATE_RANGE_SYNC',
                        start_date=start_str,
                        end_date=end_str,
                        date_type=date_type_val,
                        created_by=st.session_state.user_id
                    )
                    if job_id:
                        write_system_log(
                            st.session_state.user_id, 
                            "ETL_QUEUE_DATE_RANGE_SYNC", 
                            f"Καταχώρηση στην ουρά εργασίας συγχρονισμού Jira Issues εύρους ημερομηνιών ({start_str} - {end_str}) (Job ID: #{job_id})"
                        )
                        st.success(f"🎉 Η εργασία συγχρονισμού εύρους ημερομηνιών καταχωρήθηκε στην ουρά (Job ID: #{job_id}).")
                        st.rerun()
                    else:
                        st.error("Αποτυχία καταχώρησης της εργασίας στην ουρά.")

    with tab_queue_monitor:
        st.write("🖥️ ETL Job Queue Monitor")
        st.markdown("Παρακολουθήστε την κατάσταση των εργασιών συγχρονισμού που εκτελούνται ασύγχρονα στον server.")
        
        # Load jobs from database
        engine = get_db_engine()
        jobs_df = pd.DataFrame()
        if engine:
            try:
                from sqlalchemy import text
                with engine.connect() as conn:
                    query = text("""
                        SELECT 
                            JobID, 
                            JobType, 
                            COALESCE(IssueKey, '-') as IssueKey,
                            COALESCE(StartDate + ' έως ' + EndDate + ' (' + DateFilterType + ')', '-') as [DateRange],
                            Status, 
                            CreatedBy, 
                            CreatedAt, 
                            StartedAt, 
                            FinishedAt, 
                            LogFilePath
                        FROM ETL_Queue 
                        ORDER BY JobID DESC
                    """)
                    jobs_df = pd.read_sql(query, conn)
            except Exception as e:
                st.error(f"Σφάλμα κατά τη φόρτωση της ουράς εργασιών: {e}")
                
        if not jobs_df.empty:
            st.dataframe(
                jobs_df.drop(columns=['LogFilePath']),
                column_config={
                    "JobID": st.column_config.NumberColumn("Job ID", format="%d"),
                    "JobType": "Τύπος Εργασίας",
                    "IssueKey": "Issue Key",
                    "DateRange": "Ημερομηνίες / Φίλτρο",
                    "Status": "Κατάσταση",
                    "CreatedBy": "Χρήστης",
                    "CreatedAt": "Δημιουργήθηκε",
                    "StartedAt": "Ξεκίνησε",
                    "FinishedAt": "Ολοκληρώθηκε"
                },
                use_container_width=True,
                hide_index=True
            )
            
            # Section to Cancel/Reset active or pending jobs
            active_jobs = jobs_df[jobs_df['Status'].isin(['Running', 'Pending'])]
            if not active_jobs.empty:
                st.markdown("---")
                with st.expander("🛑 Διαχείριση & Ακύρωση Ενεργών / Κολλημένων Εργασιών"):
                    st.warning(
                        "Εάν μια εργασία έχει κολλήσει σε κατάσταση 'Running' (π.χ. επειδή διακόπηκε ο worker), "
                        "μπορείτε να την ακυρώσετε από εδώ για να ξεμπλοκάρετε την ουρά."
                    )
                    
                    cancel_options = {
                        f"Job #{row['JobID']} - {row['JobType']} ({row['Status']})": row['JobID']
                        for _, row in active_jobs.iterrows()
                    }
                    
                    job_to_cancel = st.selectbox(
                        "Επιλέξτε εργασία για ακύρωση:",
                        options=list(cancel_options.keys()),
                        key="etl_monitor_cancel_job_select"
                    )
                    
                    if st.button("🛑 Ακύρωση Επιλεγμένης Εργασίας", key="etl_monitor_cancel_job_btn", type="primary"):
                        target_job_id = cancel_options[job_to_cancel]
                        try:
                            from sqlalchemy import text
                            with engine.begin() as conn:
                                # Mark as Failed
                                conn.execute(
                                    text("UPDATE ETL_Queue SET Status = 'Failed', FinishedAt = :now WHERE JobID = :id"),
                                    {"now": datetime.now(), "id": target_job_id}
                                )
                                # Write to log file if exists
                                log_path = f"logs/etl_job_{target_job_id}.log"
                                os.makedirs("logs", exist_ok=True)
                                with open(log_path, "a", encoding="utf-8") as lf:
                                    lf.write("\n==================================================\n")
                                    lf.write(f"🛑 Job manually cancelled/reset via Admin UI at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}.\n")
                                    lf.write("==================================================\n")
                            st.success(f"🎉 Η εργασία #{target_job_id} ακυρώθηκε επιτυχώς! Η ουρά έχει ξεμπλοκάρει.")
                            st.rerun()
                        except Exception as ex:
                            st.error(f"Σφάλμα κατά την ακύρωση της εργασίας: {ex}")

            st.markdown("---")
            st.write("📂 Προβολή Logs Εργασίας")
            
            job_options = {
                f"Job #{row['JobID']} - {row['JobType']} ({row['Status']})": (row['JobID'], row['LogFilePath'])
                for _, row in jobs_df.iterrows()
            }
            
            selected_option = st.selectbox(
                "Επιλέξτε Job για προβολή logs:",
                options=list(job_options.keys()),
                key="etl_monitor_selected_job"
            )
            
            if selected_option:
                job_id, log_file_path = job_options[selected_option]
                
                col_btn, col_info = st.columns([1, 4])
                with col_btn:
                    st.button("🔄 Ανανέωση Logs", key="etl_monitor_refresh_logs")
                with col_info:
                    st.caption("Τα logs ανανεώνονται χειροκίνητα πατώντας το κουμπί ή κάνοντας refresh στη σελίδα.")
                    
                if log_file_path and os.path.exists(log_file_path):
                    try:
                        with open(log_file_path, "r", encoding="utf-8", errors="replace") as f:
                            logs_text = f.read()
                        st.code(logs_text, language="text")
                    except Exception as e:
                        st.error(f"Σφάλμα κατά την ανάγνωση των logs: {e}")
                else:
                    st.info("Δεν έχουν δημιουργηθεί logs ακόμα για αυτή την εργασία (εκκρεμεί η έναρξη της εκτέλεσης).")
                    
        else:
            st.info("Δεν βρέθηκαν καταχωρημένες εργασίες στην ουρά.")

    with tab_dev_docs:
        doc_choice = st.radio(
            "Επιλογή Εγγράφου Τεκμηρίωσης:", 
            ["📊 Dashboard & ETL Pipeline", "⚙️ Database Sync (sync_db.py)"], 
            horizontal=True
        )
        st.markdown("---")
        
        if doc_choice == "📊 Dashboard & ETL Pipeline":
            render_markdown_with_mermaid("DEVELOPER_DOCS.md")
        else:
            render_markdown_with_mermaid("sync_db_docs.md")

    with tab_migration:
        from src.etl.migrator import render_migration_tab
        render_migration_tab()



def render_manual_content():
    st.subheader("📖 Οδηγίες Χρήσης NSS Timesheet Dashboard", divider="blue")
    
    st.write(
        "Καλώς ορίσατε στον οδηγό χρήσης της εφαρμογής **NSS Timesheet Dashboard**. "
        "Εδώ θα βρείτε αναλυτικές οδηγίες για τη χρήση των φίλτρων, των Previews (αποθηκευμένων φίλτρων), "
        "της αυτόματης σύνδεσης, καθώς και των λειτουργιών διαχείρισης ομάδων και εσωτερικού περιεχομένου."
    )
    
    # expander 1: Filters & Search
    with st.expander("🔍 1. Φιλτράρισμα & Αναζήτηση"):
        st.markdown("""
        Η εφαρμογή σάς επιτρέπει να φιλτράρετε τα Worklogs της βάσης δεδομένων χρησιμοποιώντας το **Sidebar (αριστερό μενού)**:
        * **Φιλτράρισμα Εφαρμογής (Active Apps)**: Επιλέξτε ποιες εφαρμογές επιθυμείτε να προβάλλετε (π.χ. *Galaxy*, *Pylon* ή και τα δύο). Αυτό επηρεάζει τις ανακοινώσεις, τα Pro Tips και τα άρθρα της Βάσης Γνώσης.
        * **Ημερομηνίες (Date Range)**: Επιλέξτε το εύρος ημερομηνιών για την ανάλυση των ωρών.
        * **Project**: Φιλτράρισμα με βάση ένα ή περισσότερα Projects (π.χ. *NSS Timesheet*).
        * **Assignee (Σύμβουλοι)**: Φιλτράρισμα με βάση τους συμβούλους.
        * **👥 Ομάδα Χρηστών (User Group)**: Αν επιλέξετε μια ομάδα (π.χ. *NSS Support Team*), η λίστα των **Assignees** θα φιλτραριστεί αυτόματα ώστε να δείχνει μόνο τα μέλη της συγκεκριμένης ομάδας.
        * **Charge Type / Time Type**: Φιλτράρισμα ανάλογα με τη χρέωση (π.χ. *Chargeable*, *Non-Chargeable*) και τον τύπο χρόνου (π.χ. *Support*, *Development*).
        * **🤝 Partner Name / LSP Customer**: Φιλτράρισμα με βάση τον Συνεργάτη ή τον Πελάτη.
        * **Κατηγορίες (Components)**: Φιλτράρισμα με βάση τα Jira Components.
        * **🔄 Καθαρισμός Φίλτρων**: Επαναφέρει όλα τα φίλτρα στις αρχικές τους τιμές με ένα κλικ.
        """)

    # expander 2: Saved Previews
    with st.expander("💾 2. Αποθηκευμένα Previews (Φίλτρα)"):
        st.markdown("""
        **Σημαντικό:** Για να χρησιμοποιήσετε τα **Previews (Presets)**, πρέπει να είστε **συνδεδεμένος χρήστης** (Soft Login).
        
        Τα Previews σάς επιτρέπουν να αποθηκεύετε σύνθετους συνδυασμούς φίλτρων στη βάση δεδομένων για να τους φορτώνετε άμεσα χωρίς να τους επιλέγετε χειροκίνητα κάθε φορά:
        1. **Αποθήκευση νέου Preview**:
           - Επιλέξτε τα φίλτρα που επιθυμείτε στο Sidebar.
           - Στην ενότητα **Saved Previews**, πληκτρολογήστε ένα όνομα (π.χ. *My Support Group*) και πατήστε **Αποθήκευση Τρέχοντος Φίλτρου**.
        2. **Φόρτωση Preview**:
           - Επιλέξτε το Preview από τη λίστα **Φόρτωση Preview**. Τα φίλτρα θα εφαρμοστούν αμέσως στην οθόνη.
        3. **💾 Ενημέρωση (Update)**:
           - Όταν ένα Preview είναι ενεργό, μπορείτε να αλλάξετε τα φίλτρα στο Sidebar και να πατήσετε **Ενημέρωση** για να αποθηκεύσετε τις νέες επιλογές στο ίδιο όνομα.
        4. **Κοινοποίηση (Share)**:
           - Μπορείτε να μοιραστείτε το ενεργό Preview σας με έναν ή περισσότερους ενεργούς χρήστες ταυτόχρονα, επιλέγοντάς τους στο dropdown και πατώντας **Κοινοποίηση**. Το Preview θα εμφανιστεί αυτόματα στη δική τους λίστα!
        5. **🗂️ Ομαδοποίηση (Group By)**:
           - Μαζί με τα φίλτρα αναζήτησης, το Preview αποθηκεύει και την τρέχουσα επιλογή ομαδοποίησης (Group By), ώστε ο πίνακας να εμφανίζεται ακριβώς όπως τον διαμορφώσατε.
        6. **⭐ Ορισμός ως Προεπιλογή**:
           - Μπορείτε να ορίσετε ένα Preview ως προεπιλεγμένο πατώντας **⭐ Ορισμός ως Προεπιλογή**. Το συγκεκριμένο Preview θα φορτώνει αυτόματα κάθε φορά που ανοίγετε την εφαρμογή.
        """)
        
    # expander 3: Authentication & Connection Persistence
    with st.expander("🔑 3. Σύνδεση Χρήστη & Cookies"):
        st.markdown("""
        * **Soft Login**: Παρέχει πρόσβαση στις προηγμένες δυνατότητες (Previews, Προφίλ, Διαχείριση Ομάδων, Knowledge Base). Η εφαρμογή παραμένει δημόσια για ανάγνωση (read-only) για επισκέπτες που δεν επιθυμούν να συνδεθούν.
        * **Να με θυμάσαι (Remember Me)**:
           - Αν επιλέξετε το **"Να με θυμάσαι"** κατά την είσοδο, η εφαρμογή θα αποθηκεύσει ένα ασφαλές ψηφιακά υπογεγραμμένο cookie (`nss_session`) στον browser σας.
           - Την επόμενη φορά που θα ανοίξετε το URL, η εφαρμογή θα σας συνδέσει **αυτόματα** χωρίς να χρειάζεται να πληκτρολογήσετε ξανά κωδικό.
           - Η σύνδεση αυτή είναι stateless και ασφαλής (δεν γεμίζει τη βάση δεδομένων με περιττά sessions).
        * **Αποσύνδεση**:
           - Πατώντας **Αποσύνδεση**, το cookie διαγράφεται από τον browser σας και το session ακυρώνεται στη βάση.
        """)

    # expander 4: User Profile settings
    with st.expander("⚙️ 4. Προφίλ & Προτιμήσεις"):
        st.markdown("""
        Στην καρτέλα **`👤 Το Προφίλ μου`** (διαθέσιμη μόνο μετά τη σύνδεση) μπορείτε να:
        * **Ορίσετε Προτιμήσεις Εφαρμογής (Active Apps)**: Επιλέξτε ποιες εφαρμογές θέλετε να βλέπετε προεπιλεγμένα (Galaxy, Pylon ή both).
        * **Ορίσετε Προεπιλεγμένο Project (Default Project)**: Επιλέξτε το project που δουλεύετε συχνότερα. Κάθε φορά που ανοίγετε την εφαρμογή, αυτό το project θα είναι προεπιλεγμένο αυτόματα.
        * **Αλλάξετε Κωδικό Πρόσβασης (Change Password)**: Εισάγετε τον τρέχοντα κωδικό σας και τον νέο κωδικό για να τον ενημερώσετε με ασφάλεια.
        """)
        
    # expander 5: Administration & Group Management
    with st.expander("👥 5. Διαχείριση Ομάδων & Χρηστών (Admins / Team Leaders)"):
        st.markdown("""
        Η καρτέλα **`👥 Διαχείριση Ομάδων`** (ορατή μόνο σε Administrators και Team Leaders) επιτρέπει:
        1. **📋 Λίστα & Διαχείριση Χρηστών**:
           - **Προβολή Λίστας**: Εμφανίζεται αναλυτικός πίνακας με όλους τους εγγεγραμμένους χρήστες (ενεργούς και ανενεργούς), τον ρόλο τους, το email τους και την ημερομηνία δημιουργίας τους.
           - **Ενεργοποίηση / Απενεργοποίηση** (Μόνο για Administrators): Οι διαχειριστές μπορούν να ενεργοποιούν ή να απενεργοποιούν λογαριασμούς (εξαιρούνται οι λογαριασμοί Administrators για λόγους ασφαλείας).
           - **Επαναφορά Κωδικού (Reset Password)** (Μόνο για Administrators): Δυνατότητα άμεσης επαναφοράς του κωδικού ενός χρήστη στον προεπιλεγμένο κωδικό `nss12345`.
        2. **Διαχείριση Ομάδων**:
           - **Δημιουργία Ομάδας**: Δώστε ένα όνομα και επιλέξτε ποιοι Σύμβουλοι (Assignees) ανήκουν σε αυτή.
           - **Επεξεργασία/Διαγραφή**: Αλλάξτε τα μέλη ή το όνομα μιας υπάρχουσας ομάδας ή διαγράψτε την (η διαγραφή ομάδων επιτρέπεται μόνο σε Administrators).
        3. **Εγγραφή Νέου Χρήστη** (Μόνο για Administrators):
           - Εισάγετε το Email του νέου χρήστη.
           - Πατήστε **Αναζήτηση Display Name στο Jira API**. Η εφαρμογή θα τραβήξει αυτόματα το ονοματεπώνυμο του χρήστη από το Jira για να το συνδέσει άμεσα με τα worklogs του.
           - Ορίστε Username, Password και Ρόλο (Administrator, Team Leader, Consultant) για να ολοκληρώσετε την εγγραφή.
        """)

    # expander 6: Response Times & KPIs
    with st.expander("⏱️ 6. Χρόνοι Απόκρισης & KPIs (Admins / Team Leaders)"):
        st.markdown("""
        Η καρτέλα **`⏱️ Χρόνοι Απόκρισης`** (ορατή μόνο σε Administrators και Team Leaders) παρέχει εργαλεία ανάλυσης των χρόνων απόκρισης των Epic tickets:
        1. **Φόρτωση Δεδομένων**: Πατήστε το κουμπί **`🔄 Φόρτωση Δεδομένων & KPIs από τη Βάση`**.
        2. **KPI Metrics & Summary**: Εμφανίζονται οι μέσοι χρόνοι (σε ημέρες) για τις μεταβάσεις (π.χ. Creation → InProgress, InProgress → Closed, Creation → First External Response, External Resp → Closed, Creation → Closed).
        3. **Φίλτρα Αναζήτησης KPIs**: Μπορείτε να φιλτράρετε τον πίνακα με βάση το Status, το Project, το Sub Category, τον Assignee, τον Partner, τον Customer, καθώς και τα ημερομηνιακά εύρη δημιουργίας (Creation) και κλεισίματος (Closure).
        4. **Λήψη σε Excel**: Πατώντας **`📥 Λήψη σε Excel`** μπορείτε να κάνετε λήψη των φιλτραρισμένων KPIs σε μορφή Excel.
        5. **Πίνακας Ελέγχου Λαθών**: Στο κάτω μέρος υπάρχει πίνακας που εντοπίζει τυχόν σφάλματα καταχωρήσεων στο Jira (π.χ. αρνητικούς χρόνους).
        6. **Υπολογισμός SLA**: Οι χρόνοι υπολογίζονται αυτόματα με βάση εργάσιμο SLA 8ώρου (Δευτέρα - Παρασκευή 9πμ - 5μμ), εξαιρώντας τα Σαββατοκύριακα. Οι επίσημες αργίες μετρούν κανονικά ως εργάσιμες ημέρες καθώς υφίσταται προσωπικό ασφαλείας.
        7. **Διαχωρισμός Εισιτηρίων**:
           * **Filtered Tickets**: Εισιτήρια που ικανοποιούν όλα τα επιλεγμένα φίλτρα.
           * **Total Tickets**: Συνολικά εισιτήρια που ικανοποιούν μόνο τα ημερομηνιακά φίλτρα (Created & Closed), επιτρέποντας τη σύγκριση των φιλτραρισμένων με τον συνολικό όγκο της περιόδου.
        """)

    # expander 7 - Knowledge Hub (Public)
    with st.expander("💡 7. Ανακοινώσεις, Pro Tips & Βάση Γνώσης"):
        st.markdown("""
        Η εφαρμογή λειτουργεί πλέον και ως κεντρικός κόμβος ενημέρωσης και εκπαίδευσης της ομάδας:
        * **Άμεση Ενημέρωση**: Στο πάνω μέρος της αρχικής καρτέλας (`Timesheet`) προβάλλονται αυτόματα η πιο πρόσφατη ενεργή ανακοίνωση και το πιο πρόσφατο Pro Tip.
        * **Συντάκτης (Author)**: Σε κάθε ανακοίνωση, Pro Tip και άρθρο εμφανίζεται το όνομα του συντάκτη που το δημιούργησε.
        * **📢 Ανακοινώσεις & Tips**: Σε αυτή την καρτέλα βρίσκονται συγκεντρωμένες και κατηγοριοποιημένες όλες οι ανακοινώσεις και οι καλές πρακτικές.
        * **💡 Knowledge Base**: Αποτελεί την εσωτερική βιβλιοθήκη διαδικασιών.
          - **🔍 Αναζήτηση**: Χρησιμοποιήστε το πλαίσιο αναζήτησης για να φιλτράρετε άρθρα με βάση λέξεις-κλειδιά στον τίτλο, την κατηγορία ή το κείμενο του άρθρου.
          - **Κατηγορίες**: Φιλτράρετε τα άρθρα ανά κατηγορία (π.χ. *Διαδικασίες Jira*).
          - Πατώντας **📖 Διάβασμα**, το άρθρο ανοίγει σε ένα αναδυόμενο παράθυρο (modal) για ευκολότερη μελέτη.
        """)

    # expander 8 - Content Management (Admins/TLs)
    with st.expander("📝 8. Διαχείριση Περιεχομένου (Admins / Team Leaders)"):
        st.markdown("""
        Μόνο οι Team Leaders και οι Administrators έχουν τη δυνατότητα προσθήκης, επεξεργασίας και διαγραφής του ενημερωτικού περιεχομένου:
        1. **Ανακοινώσεις & Pro Tips**: Μέσα στην καρτέλα `📢 Ανακοινώσεις & Tips` εμφανίζεται στους διαχειριστές ένα επιπλέον υπο-μενού **`⚙️ Διαχείριση (CRUD)`**. Από εκεί μπορούν να δημοσιεύουν ή να επεξεργάζονται εγγραφές, επιλέγοντας την εφαρμογή-στόχο (Galaxy, Pylon ή both).
        2. **Άρθρα Knowledge Base**: Αντίστοιχα, στην καρτέλα `💡 Knowledge Base` εμφανίζεται η επιλογή **`⚙️ Διαχείριση Άρθρων`** για τη δημιουργία, κατηγοριοποίηση και αντιστοίχιση νέων εσωτερικών εγχειριδίων με εφαρμογές.
        """)

    # expander 9 - ETL Manager & Dev Docs
    with st.expander("🚀 9. ETL Manager & Τεχνική Τεκμηρίωση (Admins)"):
        st.markdown("""
        Η καρτέλα **`🚀 ETL Manager`** (ορατή μόνο σε Administrators) προσφέρει εργαλεία για τη διαχείριση της ροής δεδομένων και της τεχνικής δομής:
        1. **Ασύγχρονη Ουρά Διεργασιών (Asynchronous ETL Queue)**: Όλες οι εργασίες συγχρονισμού εκτελούνται πλέον ασύγχρονα στο παρασκήνιο (background) μέσω ενός συστήματος ουράς (`ETL_Queue`). Όταν πατάτε ένα κουμπί συγχρονισμού, η εργασία μπαίνει σε κατάσταση `Pending` και εκτελείται αυτόματα από τον background worker χωρίς να παγώνει ο browser ή η εφαρμογή.
        2. **🖥️ ETL Job Monitor**: Μια νέα ενσωματωμένη καρτέλα που επιτρέπει στους Administrators:
           - Να παρακολουθούν την κατάσταση όλων των εργασιών στην ουρά (`Pending`, `Running`, `Success`, `Failed`).
           - Να βλέπουν ποιος χρήστης ξεκίνησε την εργασία, πότε ξεκίνησε και πότε ολοκληρώθηκε.
           - Να επιλέγουν οποιαδήποτε εργασία και να παρακολουθούν **live** τα logs εκτέλεσής της σε πραγματικό χρόνο (Log Terminal).
        3. **📅 Συγχρονισμός βάσει Ημερομηνιών (Date Range Sync)**: Δυνατότητα συγχρονισμού Jira Issues εντός συγκεκριμένου ημερομηνιακού διαστήματος.
           - Ο συγχρονισμός μπορεί να φιλτραριστεί με βάση την **Ημερομηνία Ενημέρωσης** (Updated Date - προτείνεται για να συμπεριλάβει αλλαγές σε worklogs/σχόλια) ή την **Ημερομηνία Δημιουργίας** (Created Date).
        4. **Μεμονωμένες Ενέργειες / Μαζικός Συγχρονισμός**: Χειροκίνητη εκτέλεση του ETL Pipeline για Projects, Users, Components, Issues.
        5. **Jira Full Sync (Από Μηδέν)**: Πλήρης συγχρονισμός των Jira οντοτήτων από το μηδέν (αγνοώντας την ημερομηνία τελευταίου συγχρονισμού) για περιπτώσεις συντήρησης.
        6. **🚀 Gemini to Jira Migration**: Μηχανισμός μεταφοράς αιτημάτων (Gemini → Jira) με υποστήριξη φίλτρων (Gemini Project Code, Ημερομηνίες, Κείμενο Αναζήτησης, Advanced Exclusion NOT filters) και αυτόματη μεταφόρτωση συνημμένων (attachments) και αντιστοίχιση χρηστών (resources mapping). Η αναζήτηση τεμαχίζεται αυτόματα (auto-chunking) σε διαστήματα 3 μηνών για την αποφυγή timeouts του Gemini API.
        7. **📖 Dev Docs**: Πρόσβαση στην τεχνική τεκμηρίωση του συστήματος απευθείας εντός της εφαρμογής. Επιτρέπεται η εναλλαγή μεταξύ της αρχιτεκτονικής του Dashboard & ETL Pipeline (`DEVELOPER_DOCS.md`) και του συγχρονισμού της βάσης (`sync_db_docs.md`), με πλήρη υποστήριξη οπτικοποίησης διαγραμμάτων ροής Mermaid.
        """)

    # expander 10 - ClassMarker Integration (v26.7.1a)
    with st.expander("🎓 10. Πιστοποιήσεις ClassMarker (v26.7.1a)"):
        st.markdown("""
        Η ενότητα **`🎓 ClassMarker`** (διαθέσιμη σε Administrators, ContentManagers, ContentCreators) παρέχει εργαλεία διαχείρισης της τράπεζας ερωτήσεων, των αποτελεσμάτων των εξετάσεων και των proctoring logs:
        1. **📝 Διαχείριση Ερωτήσεων**:
           - **Πίνακας Ερωτήσεων**: Προβάλλει όλες τις ερωτήσεις, τη Γονική Κατηγορία, την Κατηγορία, τον τύπο τους, τους βαθμούς, την κατάσταση τοπικής τροποποίησης, το τρέχον στάδιο review και τον χρήστη στον οποίο έχουν ανατεθεί για έλεγχο.
           - **📂 Nested Φίλτρα**: Επιλογή Γονικής Κατηγορίας η οποία φιλτράρει αυτόματα τις διαθέσιμες child κατηγορίες στο διπλανό dropdown.
           - **🛠️ Επεξεργασία (Αναδυόμενο Παράθυρο)**: Ανοίγει modal popup (`st.dialog`) για επεξεργασία του κειμένου, της κατηγορίας, των βαθμών και των απαντήσεων. Ο επεξεργαστής απαντήσεων χρησιμοποιεί widget επιλογής πλήθους (2-6) για την αποφυγή ακούσιου κλεισίματος.
           - **👀 Σύγκριση Αλλαγών (Diff)**: Αν μια ερώτηση έχει τροποποιηθεί τοπικά, εμφανίζεται side-by-side προβολή της αρχικής έκδοσης (από τον πίνακα `CM_Questions_Original`) σε σχέση με την τροποποιημένη.
           - **📋 Ανάθεση Ελέγχου (Workflow)**: Επιλέξτε έναν εγγεγραμμένο reviewer και το στάδιο ελέγχου (Στάδιο 1: Αρχικός Έλεγχος, Στάδιο 2: Peer Review, Στάδιο 3: Τελική Έγκριση) για να του αναθέσετε την ερώτηση.
        2. **📥 Εκκρεμότητες Ελέγχου**:
           - Κάθε reviewer βλέπει στην ουρά του τις ερωτήσεις που του έχουν ανατεθεί. 
           - Μπορεί να επεξεργαστεί απευθείας την ερώτηση με το κουμπί **🛠️ Επεξεργασία**, να γράψει σημειώσεις ελέγχου, να **προωθήσει** την ερώτηση στο επόμενο στάδιο ή να την **εγκρίνει οριστικά** (Στάδιο 5).
           - **Draft Reset**: Στο Στάδιο 1, υπάρχει δυνατότητα επαναφοράς της ερώτησης σε draft status (ReviewStage = 1) και αφαίρεσης του Assignee.
           - **Αποστολή στο ClassMarker**: Κουμπί άμεσου συγχρονισμού των εγκεκριμένων αλλαγών στο ClassMarker API απευθείας από την ουρά ελέγχου.
        3. **🛡️ Αποτελέσματα & Proctoring**:
           - **Infraction Timeline**: Στις λεπτομέρειες των αποτελεσμάτων εξετάσεων, η εφαρμογή αναλύει αυτόματα το JSON των proctoring events (`ProctoringEventsJSON`) και σχεδιάζει το χρονολόγιο των ύποπτων ενεργειών (π.χ. αλλαγή tab, αντιγραφή/επικόλληση) του υποψηφίου.
           - **Μαζικές Ενέργειες**: Επιλογή πολλαπλών αποτελεσμάτων και μαζική έγκριση, απόρριψη ή επαναφορά σε εκκρεμότητα.
        """)

    # expander - Changelog
    with st.expander("📋 Ιστορικό Εκδόσεων (Changelog)"):
        st.markdown("""
        ### Έκδοση 26.7.1a (2026-07-02)
        * **Νέο (Gemini to Jira Migration):** Πλήρης ενσωμάτωση του μηχανισμού μεταφοράς αιτημάτων (Gemini → Jira) με υποστήριξη φίλτρων (Gemini Project Code, Ημερομηνίες, Κείμενο Αναζήτησης, Advanced Exclusion NOT filters) και αυτόματη μεταφόρτωση συνημμένων (attachments) και αντιστοίχιση χρηστών (resources mapping).
        * **Νέο (Gemini API Timeout Mitigation):** Αυτόματος τεμαχισμός αναζήτησης (auto-chunking) σε διαστήματα 3 μηνών για την αποφυγή timeouts του Gemini API.
        * **Νέο (ClassMarker Parent Categories):** Προσθήκη ιεραρχικής προβολής γονικών κατηγοριών ("Γονική Κατηγορία") και δυναμικών nested dropdowns φιλτραρίσματος.
        * **Νέο (ClassMarker Snapshots):** Αυτόματο save-state της αρχικής ερώτησης στον πίνακα `CM_Questions_Original` προτού τροποποιηθεί τοπικά, και side-by-side Diff προβολή της αρχικής vs τροποποιημένης ερώτησης στη Διαχείριση και την Ουρά Ελέγχου.
        * **Νέο (Workflow):** Προσθήκη κουμπιού επεξεργασίας (`st.dialog`) απευθείας στην Ουρά Αξιολόγησης και κουμπιού επαναφοράς σε Draft status για ερωτήσεις στο Στάδιο 1.
        * **Fix (Dialog UX):** Αντικατάσταση των κουμπιών προσθήκης/διαγραφής επιλογών με widget `st.number_input` για την αποφυγή ακούσιου κλεισίματος του dialog λόγω rerun.
        * **Fix (pyodbc Dtype):** Ρητό casting όλων των παραμέτρων της βάσης σε native python types για την αποφυγή numpy `int64` binding errors (`HY105`).

        ### Έκδοση 26.6.2a (2026-06-30)
        * **Νέο (ClassMarker integration):** Προσθήκη **Τράπεζας Ερωτήσεων ClassMarker** (Questions Bank) με προβολή κατηγοριών, βαθμών, και επιλογών, καθώς και αυτόματης σήμανσης τοπικά τροποποιημένων εγγραφών (`IsLocallyModified = 1`) για αποφυγή ETL overwrite.
        * **Νέο (ClassMarker integration):** Προσθήκη **Αποτελεσμάτων & Proctoring** (Test Results Dashboard) για την παρακολούθηση των εξετάσεων και των proctoring logs.
        * **Νέο (Review Workflow):** Προσθήκη **Συστήματος 3 Σταδίων Ελέγχου Ερωτήσεων** (Workflow Stages 1, 2, 3) με ουρά αξιολόγησης (`📥 Εκκρεμότητες Ελέγχου`) και στήλη υπευθύνου ανάθεσης ("Ανάθεση Σε") στον κεντρικό πίνακα.
        * **Νέο (Dialog Editor):** Αναδυόμενο παράθυρο επεξεργασίας ερωτήσεων (`st.dialog`) με δυναμική εμφάνιση/επεξεργασία επιλογών απαντήσεων βάσει του τύπου της ερώτησης.
        * **Νέο (API Sync):** Αυτόματος συγχρονισμός τοπικά εγκεκριμένων αλλαγών ερωτήσεων στο ClassMarker API (`push_question_to_classmarker`) με υποστήριξη mock fallback.
        * **Νέο (Proctoring logs):** Προβολή proctoring infraction timeline με αυτόματη αποκωδικοποίηση JSON (από `ProctoringEventsJSON`) χωρίς ανάγκη εξωτερικού πίνακα.
        * **Νέο (User Management):** Επεξεργασία ρόλων χρηστών από τον Administrator (εκτός Administrators που αλλάζουν μόνο μέσω βάσης).
        * **Νέο (Roles):** Προσθήκη υποστήριξης ρόλων `ContentCreator` ( Consultant + ClassMarker ερωτήσεις χωρίς ETL) και `ContentManager` ( TeamLeader + πλήρης διαχείριση ClassMarker).
        * **Νέο (ETL Pipelines):** Νέα ETL Jobs συγχρονισμού ερωτήσεων (`CLASSMARKER_QUESTIONS_SYNC`) και αποτελεσμάτων (`CLASSMARKER_RESULTS_SYNC`) στην ασύγχρονη ουρά.

        ### Έκδοση 26.5.6a (2026-06-25)
        * **Νέο:** Μετάβαση σε **Ασύγχρονο Μηχανισμό ETL (Asynchronous Queue & Worker)**. Οι συγχρονισμοί εκτελούνται πλέον στο παρασκήνιο (background) μέσω της ουράς `ETL_Queue`, αποτρέποντας το πάγωμα της Streamlit εφαρμογής και επιτρέποντας την ασφαλή εκτέλεση διεργασιών μεγάλης διάρκειας.
        * **Νέο:** Προσθήκη καρτέλας **`🖥️ ETL Job Monitor`** με δυνατότητα ζωντανής παρακολούθησης της ροής των logs (live stream terminal logs) για οποιαδήποτε ενεργή ή παρελθούσα διεργασία.
        * **Νέο:** Προσθήκη μεθόδου **`📅 Συγχρονισμός βάσει Ημερομηνιών (Date Range Sync)`** στον ETL Manager, με επιλογή φιλτραρίσματος βάσει Ημερομηνίας Ενημέρωσης (`Updated`) ή Δημιουργίας (`Created`) στο Jira API.
        * **Νέο:** Υλοποίηση background daemon `etl_worker.py` για τη διαδοχική εκτέλεση των pending εργασιών της ουράς με απομονωμένα python subprocesses και καταγραφή logs σε UTF-8.

        ### Έκδοση 26.5.5c (2026-06-24)
        * **Νέο:** Προσθήκη καρτέλας `🔍 ETL Debugger` στον ETL Manager για τη δοκιμαστική εκτέλεση και αποσφαλμάτωση συγχρονισμού μεμονωμένων Jira Issues (βάσει IssueKey).
        * **Fix:** Επίλυση `UnicodeEncodeError` κατά την εκτέλεση του debugger σε Windows συστήματα με ελληνικό locale (κωδικοποίηση `CP1253`), μέσω αυτόματης αναδιάρθρωσης των `stdout` & `stderr` σε UTF-8.
        * **Fix:** Επίλυση SQL Server merge exception στον πίνακα `GAudit` (διπλότυπες εγγραφές ανά AuditID κατά την επεξεργασία πολλαπλών πεδίων στο ίδιο changelog history event) με προσθήκη του `FieldName` στα merge keys.
        
        ### Έκδοση 26.5.5 (2026-06-24)
        * **Νέο:** Αυτόματος υπολογισμός χρόνων με βάση εργάσιμο SLA 8ώρου (Δευτέρα-Παρασκευή 9πμ-5μμ, εξαιρώντας ΣΚ).
        * **Νέο:** Προσθήκη SLA μετρήσεων για τη φάση In Progress (`Creation → InProgress` και `InProgress → Closed`).
        * **Νέο:** Προσθήκη φίλτρου ημερομηνίας κλεισίματος αιτημάτων (Closed Date range filter).
        * **Νέο:** Διαχωρισμός όγκου εισιτηρίων σε `Filtered Tickets` (επηρεάζεται από όλα τα φίλτρα) και `Total Tickets` (επηρεάζεται μόνο από τις ημερομηνίες) στις κάρτες KPIs και την ομαδοποίηση.
        * **Fix:** Επίλυση Streamlit API exception προειδοποίησης για τα default date input πεδία και διόρθωση της συμπεριφοράς επιλογής εύρους ημερομηνιών.
        
        ### Έκδοση 26.5.4 (2026-06-23)
        * **Νέο:** Προσθήκη καρτέλας `📖 Dev Docs` στον ETL Manager με αυτόνομη απόδοση Mermaid.js διαγραμμάτων (εναλλαγή μεταξύ `DEVELOPER_DOCS.md` και `sync_db_docs.md`).
        * **Νέο:** Προσθήκη επιλογής `🎫 Jira Full Sync (Από Μηδέν)` στον ETL Manager.
        * **Νέο:** Μηχανισμός ελεύθερης αναζήτησης άρθρων στη Βάση Γνώσης (`💡 Knowledge Base`).
        * **Νέο:** Εμφάνιση συντάκτη (`Author`) σε ανακοινώσεις, tips και KB άρθρα.
        * **Βελτίωση:** Πλήρης αναδιοργάνωση και ομαδοποίηση του μενού πλοήγησης (Sidebar).
        * **Fix:** Επίλυση Streamlit Deprecation Warnings (`use_container_width`) και Pandas `UserWarning` για τις συνδέσεις στη βάση.
        
        ### Έκδοση 26.5.0 (2026-06-19)
        * **Βελτίωση:** Επανασχεδιασμός Sidebar με premium left-aligned flat buttons.
        * **Βελτίωση:** Πτυσσόμενα panels φίλτρων (Expander Blocks) για εξοικονόμηση χώρου.
        * **Νέο:** Δυναμική ομαδοποίηση (Group By) και εξαγωγή σε Excel στους Χρόνους Απόκρισης (KPIs).
        """)

# --- ClassMarker UI Helper Functions & Pages ---

def queue_classmarker_job(job_type, username):
    engine = get_db_engine()
    if not engine:
        st.error("❌ Αδυναμία σύνδεσης στη βάση δεδομένων.")
        return False
    try:
        with engine.begin() as conn:
            existing = conn.execute(
                text("SELECT JobID FROM ETL_Queue WHERE JobType = :job_type AND Status IN ('Pending', 'Running')"),
                {"job_type": job_type}
            ).fetchone()
            if existing:
                st.warning(f"⚠️ Υπάρχει ήδη μια εκκρεμής ή ενεργή διεργασία συγχρονισμού '{job_type}' (Job #{existing[0]}). Παρακαλώ περιμένετε να ολοκληρωθεί.")
                return False
            
            conn.execute(
                text(
                    "INSERT INTO ETL_Queue (JobType, Status, CreatedBy, CreatedAt) "
                    "VALUES (:job_type, 'Pending', :user, :now)"
                ),
                {"job_type": job_type, "user": username, "now": datetime.now()}
            )
        return True
    except Exception as e:
        st.error(f"❌ Σφάλμα κατά την καταχώρηση της διεργασίας: {e}")
        return False

def update_local_question(question_id, category_id, text_content, options_json, points, active):
    engine = get_db_engine()
    if not engine:
        return False
    try:
        with engine.begin() as conn:
            # Check if original question is already saved
            orig_check = conn.execute(
                text("SELECT 1 FROM CM_Questions_Original WHERE QuestionID = :id"),
                {"id": question_id}
            ).fetchone()
            
            if not orig_check:
                # Retrieve current state from CM_Questions to keep as original
                current_q = conn.execute(
                    text("SELECT CategoryID, QuestionType, QuestionText, OptionsJSON, Points, Active FROM CM_Questions WHERE QuestionID = :id"),
                    {"id": question_id}
                ).fetchone()
                
                if current_q:
                    conn.execute(
                        text(
                            "INSERT INTO CM_Questions_Original (QuestionID, CategoryID, QuestionType, QuestionText, OptionsJSON, Points, Active, SavedAt) "
                            "VALUES (:id, :cat_id, :q_type, :q_text, :options, :points, :active, :now)"
                        ),
                        {
                            "id": question_id,
                            "cat_id": current_q[0],
                            "q_type": current_q[1],
                            "q_text": current_q[2],
                            "options": current_q[3],
                            "points": current_q[4],
                            "active": current_q[5],
                            "now": datetime.now()
                        }
                    )
            
            # Apply local modifications
            conn.execute(
                text(
                    "UPDATE CM_Questions "
                    "SET CategoryID = :cat_id, QuestionText = :q_text, OptionsJSON = :options, "
                    "    Points = :points, Active = :active, IsLocallyModified = 1 "
                    "WHERE QuestionID = :id"
                ),
                {
                    "cat_id": category_id,
                    "q_text": text_content,
                    "options": options_json,
                    "points": points,
                    "active": 1 if active else 0,
                    "id": question_id
                }
            )
        return True
    except Exception as e:
        st.error(f"❌ Σφάλμα κατά την αποθήκευση της ερώτησης: {e}")
        return False

def assign_question_reviewer(question_id, reviewer_id, current_user_id, target_stage):
    engine = get_db_engine()
    if not engine:
        return False
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE CM_Questions "
                    "SET AssignedToUserID = :rev_id, AssignedByUserID = :curr_id, "
                    "    PreviousAssigneeID = :curr_id, "
                    "    ReviewStage = :stage, IsLocallyModified = 1 "
                    "WHERE QuestionID = :id"
                ),
                {
                    "rev_id": reviewer_id,
                    "curr_id": current_user_id,
                    "stage": target_stage,
                    "id": question_id
                }
            )
        return True
    except Exception as e:
        st.error(f"❌ Σφάλμα κατά την ανάθεση ελέγχου: {e}")
        return False

def push_question_to_classmarker(question_id):
    engine = get_db_engine()
    if not engine:
        st.error("❌ Αδυναμία σύνδεσης στη βάση δεδομένων.")
        return False
        
    try:
        with engine.connect() as conn:
            q = conn.execute(
                text("SELECT CategoryID, QuestionType, QuestionText, OptionsJSON, Points, Active FROM CM_Questions WHERE QuestionID = :id"),
                {"id": question_id}
            ).fetchone()
    except Exception as e:
        st.error(f"❌ Σφάλμα κατά την ανάγνωση της ερώτησης: {e}")
        return False
        
    if not q:
        st.error("❌ Η ερώτηση δεν βρέθηκε στη βάση δεδομένων.")
        return False
        
    category_id, q_type, q_text, options_json, points, active = q
    
    api_key = st.secrets.get("CLASSMARKER_API_KEY", "")
    api_secret = st.secrets.get("CLASSMARKER_API_SECRET", "")
    
    if not api_key or api_key == "your_api_key" or not api_secret or api_secret == "your_api_secret":
        # Check env variables or .env file
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
        if not api_key or api_key == "your_api_key":
            api_key = os.environ.get("CLASSMARKER_API_KEY") or env_vars.get("CLASSMARKER_API_KEY", "")
        if not api_secret or api_secret == "your_api_secret":
            api_secret = os.environ.get("CLASSMARKER_API_SECRET") or env_vars.get("CLASSMARKER_API_SECRET", "")
            
    if not api_key or not api_secret or api_key == "your_api_key" or api_secret == "your_api_secret":
        st.warning(f"⚠️ [MOCK] Mock Sync: Αποστολή ερώτησης ID {question_id} στο ClassMarker επιτυχής!")
        try:
            with engine.begin() as conn:
                conn.execute(
                    text("UPDATE CM_Questions SET IsLocallyModified = 0, SyncedAt = :now WHERE QuestionID = :id"),
                    {"now": datetime.now(), "id": question_id}
                )
                conn.execute(
                    text("DELETE FROM CM_Questions_Original WHERE QuestionID = :id"),
                    {"id": question_id}
                )
            return True
        except Exception as e:
            st.error(f"❌ Σφάλμα: {e}")
            return False
            
    try:
        timestamp = str(int(time.time()))
        signature = hashlib.sha256((api_key + api_secret + timestamp).encode('utf-8')).hexdigest()
        
        # Real API request
        # Real API request using PUT for updates
        url = f"https://api.classmarker.com/v1/questions/{question_id}.json?api_key={api_key}&signature={signature}&timestamp={timestamp}"
        
        opts_dict = {}
        correct_list = []
        try:
            raw_opts = json.loads(options_json)
            alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
            for o_idx, o in enumerate(raw_opts):
                label = o.get("option_label") or alphabet[o_idx]
                opts_dict[label] = {"content": o.get("text", "")}
                if o.get("correct", False):
                    correct_list.append(label)
        except Exception:
            opts_dict = {}
            correct_list = []
            
        payload = {
            "question": q_text,
            "category_id": int(category_id),
            "points": float(points)
        }
        
        if q_type in ["multiple_choice", "true_false", "multiplechoice", "truefalse", "multipleresponse"]:
            payload["options"] = opts_dict
            payload["correct_options"] = correct_list
            
        res = requests.put(url, json=payload, timeout=15)
        if res.status_code in [200, 201]:
            with engine.begin() as conn:
                conn.execute(
                    text("UPDATE CM_Questions SET IsLocallyModified = 0, SyncedAt = :now WHERE QuestionID = :id"),
                    {"now": datetime.now(), "id": question_id}
                )
                conn.execute(
                    text("DELETE FROM CM_Questions_Original WHERE QuestionID = :id"),
                    {"id": question_id}
                )
            return True
        else:
            st.error(f"❌ Το ClassMarker API επέστρεψε σφάλμα {res.status_code}: {res.text}")
            return False
    except Exception as e:
        st.error(f"❌ Σφάλμα κατά τη σύνδεση με το API: {e}")
        return False

def show_reviewer_queue(current_user_id):
    st.markdown("### 📥 Ερωτήσεις προς Έλεγχο (Review Queue)")
    
    engine = get_db_engine()
    if not engine:
        st.error("❌ Αδυναμία σύνδεσης στη βάση δεδομένων.")
        return
        
    try:
        with engine.connect() as conn:
            # Load active users for forwarding
            users_res = conn.execute(
                text("SELECT UserID, DisplayName, Username FROM Users WHERE IsActive = 1 ORDER BY DisplayName")
            ).fetchall()
            users_map = {f"{r[1]} ({r[2]})": r[0] for r in users_res}
            
            categories_df = pd.read_sql(
                "SELECT c.CategoryID, c.CategoryName, p.CategoryName AS ParentCategoryName "
                "FROM CM_Categories c "
                "LEFT JOIN CM_Categories p ON c.ParentCategoryID = p.CategoryID "
                "ORDER BY c.CategoryName", 
                conn
            )
            
            # Fetch assigned questions
            query = text(
                "SELECT q.QuestionID, q.CategoryID, c.CategoryName, p.CategoryName AS ParentCategoryName, "
                "       q.QuestionType, q.QuestionText, q.OptionsJSON, q.Points, q.Active, q.ReviewStage, "
                "       q.ReviewNotes, q.PreviousAssigneeID, q.IsLocallyModified, "
                "       u.DisplayName AS AssignedByName "
                "FROM CM_Questions q "
                "JOIN CM_Categories c ON q.CategoryID = c.CategoryID "
                "LEFT JOIN CM_Categories p ON c.ParentCategoryID = p.CategoryID "
                "LEFT JOIN Users u ON q.AssignedByUserID = u.UserID "
                "WHERE q.AssignedToUserID = :user_id AND q.ReviewStage IN (2, 3, 4)"
            )
            df_reviews = pd.read_sql(query, conn, params={"user_id": current_user_id})
    except Exception as e:
        st.error(f"❌ Σφάλμα κατά τη φόρτωση της ουράς ελέγχου: {e}")
        return
        
    if df_reviews.empty:
        st.info("✅ Δεν έχετε εκκρεμείς ερωτήσεις για έλεγχο.")
        return
        
    st.markdown(f"Έχετε **{len(df_reviews)}** ερωτήσεις προς αξιολόγηση.")
    
    # Simple Stage display mapper
    stage_names = {
        2: "Στάδιο 1: Αρχικός Έλεγχος",
        3: "Στάδιο 2: Peer Review",
        4: "Στάδιο 3: Τελική Έγκριση"
    }
    
    df_display = df_reviews.copy()
    df_display["Στάδιο"] = df_display["ReviewStage"].map(stage_names)
    
    st.dataframe(
        df_display[["QuestionID", "ParentCategoryName", "CategoryName", "QuestionType", "QuestionText", "Στάδιο", "AssignedByName"]],
        use_container_width=True,
        hide_index=True,
        column_config={
            "QuestionID": st.column_config.NumberColumn("ID", format="%d"),
            "ParentCategoryName": "Γονική Κατηγορία",
            "CategoryName": "Κατηγορία",
            "QuestionType": "Τύπος",
            "QuestionText": "Κείμενο Ερώτησης",
            "Στάδιο": "Στάδιο Ελέγχου",
            "AssignedByName": "Ανατέθηκε Από"
        }
    )
    
    st.markdown("#### 🔍 Αναλυτική Αξιολόγηση Ερώτησης")
    sel_rev_id = st.selectbox(
        "Επιλέξτε ID ερώτησης για αξιολόγηση:",
        options=df_reviews["QuestionID"].tolist(),
        format_func=lambda x: f"ID: {x} - {df_reviews[df_reviews['QuestionID'] == x]['QuestionText'].values[0][:80]}...",
        key="sel_rev_id_box"
    )
    
    if sel_rev_id:
        q_row = df_reviews[df_reviews["QuestionID"] == sel_rev_id].iloc[0]
        st.info(f"**Ερώτηση (ID {q_row['QuestionID']}):** {q_row['QuestionText']}")
        st.markdown(
            f"**Γονική Κατηγορία:** {q_row['ParentCategoryName'] or 'N/A'} | "
            f"**Κατηγορία:** {q_row['CategoryName']} | "
            f"**Τύπος:** {q_row['QuestionType']} | "
            f"**Στάδιο:** {stage_names.get(q_row['ReviewStage'])}"
        )
        
        # Original Question Compare Section
        orig_row = None
        if q_row["IsLocallyModified"] in (1, True, "1"):
            try:
                with engine.connect() as conn:
                    orig_row = conn.execute(
                        text("SELECT CategoryID, QuestionType, QuestionText, OptionsJSON, Points, Active FROM CM_Questions_Original WHERE QuestionID = :id"),
                        {"id": sel_rev_id}
                    ).fetchone()
            except Exception:
                pass
                
        if orig_row:
            with st.expander("👀 Σύγκριση Αλλαγών με την Αρχική Ερώτηση (Diff)"):
                col_orig, col_mod = st.columns(2)
                with col_orig:
                    st.markdown("**📜 Αρχική Έκδοση (ClassMarker)**")
                    st.write(orig_row[2])
                    st.caption(f"**Βαθμοί:** {orig_row[4]} | **Κατάσταση:** {'Ενεργή' if orig_row[5] else 'Ανενεργή'}")
                    try:
                        orig_opts = json.loads(orig_row[3])
                        if orig_opts:
                            for o_idx, o in enumerate(orig_opts, 1):
                                txt = o.get("text", "")
                                is_corr = o.get("correct", False)
                                lbl = o.get("option_label") or str(o_idx)
                                st.markdown(f"{'✅' if is_corr else '❌'} **{lbl}**. {txt}")
                    except Exception:
                        pass
                with col_mod:
                    st.markdown("**✏️ Τροποποιημένη Έκδοση (Support Hub)**")
                    st.write(q_row['QuestionText'])
                    st.caption(f"**Βαθμοί:** {q_row['Points']} | **Κατάσταση:** {'Ενεργή' if q_row['Active'] else 'Ανενεργή'}")
                    try:
                        mod_opts = json.loads(q_row["OptionsJSON"])
                        if mod_opts:
                            for o_idx, o in enumerate(mod_opts, 1):
                                txt = o.get("text", "")
                                is_corr = o.get("correct", False)
                                lbl = o.get("option_label") or str(o_idx)
                                st.markdown(f"{'✅' if is_corr else '❌'} **{lbl}**. {txt}")
                    except Exception:
                        pass
        st.markdown(f"**Βαθμοί:** {q_row['Points']} | **Ανατέθηκε από:** {q_row['AssignedByName'] or 'N/A'}")
        
        # Display Options
        try:
            options = json.loads(q_row["OptionsJSON"])
            if options:
                st.markdown("**Επιλογές Απαντήσεων (Read-Only):**")
                normalized_options = []
                if isinstance(options, dict):
                    for key in sorted(options.keys()):
                        opt = options[key]
                        content = opt.get("content") or opt.get("text") or ""
                        correct = opt.get("correct") or False
                        normalized_options.append({"text": content, "correct": correct, "option_label": key})
                elif isinstance(options, list):
                    normalized_options = options
                
                for idx, opt in enumerate(normalized_options, 1):
                    is_correct = opt.get("correct", False)
                    opt_text = opt.get("text", "")
                    label = opt.get("option_label") or str(idx)
                    if is_correct:
                        st.markdown(f"✅ **{label}**. **{opt_text} (Σωστό)**")
                    else:
                        st.markdown(f"❌ **{label}**. {opt_text}")
        except Exception:
            pass
            
        st.markdown("---")
        st.markdown("**✍️ Σημειώσεις & Ενέργειες Αξιολόγησης**")
        rev_notes = st.text_area("Σημειώσεις / Σχόλια Ελέγχου", value=q_row["ReviewNotes"] or "", key=f"rev_notes_input_{sel_rev_id}")
        
        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            current_stage = int(q_row["ReviewStage"])
            if current_stage == 2:
                # Stage 1 (ReviewStage 2) cannot be returned to previous, but can be reset to Draft
                if st.button("↩️ Επαναφορά σε Draft Status", use_container_width=True, type="secondary", key=f"btn_reset_draft_{sel_rev_id}"):
                    try:
                        with engine.begin() as conn:
                            conn.execute(
                                text(
                                    "UPDATE CM_Questions "
                                    "SET AssignedToUserID = NULL, AssignedByUserID = NULL, PreviousAssigneeID = NULL, "
                                    "    ReviewStage = 1, ReviewNotes = :notes, IsLocallyModified = 1 "
                                    "WHERE QuestionID = :id"
                                ),
                                {
                                    "notes": rev_notes if rev_notes else None,
                                    "id": int(sel_rev_id)
                                }
                            )
                        st.info("🔄 Η ερώτηση επαναφέρθηκε σε Draft status και αφαιρέθηκε ο υπεύθυνος.")
                        time.sleep(1)
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Σφάλμα: {e}")
            else:
                if st.button("↩️ Επιστροφή στον Προηγούμενο", use_container_width=True, type="secondary", key=f"btn_return_{sel_rev_id}"):
                    prev_id = q_row["PreviousAssigneeID"] or q_row["AssignedByUserID"] or current_user_id
                    new_stage = int(max(1, int(q_row["ReviewStage"]) - 1))
                    
                    # Convert to native types
                    db_prev_id = int(prev_id) if pd.notna(prev_id) else None
                    db_curr_id = int(current_user_id) if pd.notna(current_user_id) else None
                    
                    try:
                        with engine.begin() as conn:
                            conn.execute(
                                text(
                                    "UPDATE CM_Questions "
                                    "SET AssignedToUserID = :prev_id, AssignedByUserID = :curr_id, "
                                    "    ReviewStage = :stage, ReviewNotes = :notes, IsLocallyModified = 1 "
                                    "WHERE QuestionID = :id"
                                ),
                                {
                                    "prev_id": db_prev_id,
                                    "curr_id": db_curr_id,
                                    "stage": int(new_stage),
                                    "notes": rev_notes if rev_notes else None,
                                    "id": int(sel_rev_id)
                                }
                            )
                        st.warning("🔄 Η ερώτηση επιστράφηκε στον προηγούμενο υπεύθυνο.")
                        time.sleep(1)
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Σφάλμα: {e}")
                        
        with col_btn2:
            current_stage = int(q_row["ReviewStage"])
            if current_stage == 4:
                # Stage 3 review, i.e., final approval promotes to stage 5 (verified) and clears assignment
                btn_label = "✅ Οριστική Έγκριση ερώτησης (Στάδιο 5)"
                if st.button(btn_label, use_container_width=True, type="primary", key=f"btn_promote_{sel_rev_id}"):
                    # Convert to native types
                    db_curr_id = int(current_user_id) if pd.notna(current_user_id) else None
                    try:
                        with engine.begin() as conn:
                            conn.execute(
                                text(
                                    "UPDATE CM_Questions "
                                    "SET AssignedToUserID = NULL, AssignedByUserID = NULL, PreviousAssigneeID = :curr_id, "
                                    "    ReviewStage = 5, ReviewNotes = :notes, IsLocallyModified = 1 "
                                    "WHERE QuestionID = :id"
                                ),
                                {
                                    "curr_id": db_curr_id,
                                    "notes": rev_notes if rev_notes else None,
                                    "id": int(sel_rev_id)
                                }
                            )
                        st.success("✅ Η ερώτηση εγκρίθηκε οριστικά και σημειώθηκε ως verified (Στάδιο 5)!")
                        time.sleep(1)
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Σφάλμα: {e}")
            else:
                next_stage = int(current_stage + 1)
                st.write(f"**Προώθηση στο επόμενο στάδιο: {stage_names.get(next_stage)}**")
                sel_next_reviewer = st.selectbox(
                    "Επιλέξτε επόμενο υπεύθυνο ελέγχου:",
                    options=["-- Επιλογή Χρήστη --"] + list(users_map.keys()),
                    key=f"sel_next_reviewer_{sel_rev_id}"
                )
                
                if st.button("▶️ Προώθηση / Έγκριση", use_container_width=True, type="primary", key=f"btn_promote_{sel_rev_id}"):
                    if sel_next_reviewer == "-- Επιλογή Χρήστη --":
                        st.warning("⚠️ Παρακαλώ επιλέξτε τον επόμενο χρήστη για την ανάθεση.")
                    else:
                        next_user_id = users_map[sel_next_reviewer]
                        # Convert to native types
                        db_next_uid = int(next_user_id) if pd.notna(next_user_id) else None
                        db_curr_id = int(current_user_id) if pd.notna(current_user_id) else None
                        try:
                            with engine.begin() as conn:
                                conn.execute(
                                    text(
                                        "UPDATE CM_Questions "
                                        "SET AssignedToUserID = :next_uid, AssignedByUserID = :curr_id, "
                                        "    PreviousAssigneeID = :curr_id, "
                                        "    ReviewStage = :stage, ReviewNotes = :notes, IsLocallyModified = 1 "
                                        "WHERE QuestionID = :id"
                                    ),
                                    {
                                        "next_uid": db_next_uid,
                                        "curr_id": db_curr_id,
                                        "stage": int(next_stage),
                                        "notes": rev_notes if rev_notes else None,
                                        "id": int(sel_rev_id)
                                    }
                                )
                            st.success(f"▶️ Η ερώτηση προωθήθηκε στον/στην {sel_next_reviewer}.")
                            time.sleep(1)
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ Σφάλμα: {e}")

        # Send to ClassMarker button in review queue if user has manager rights (can_manage)
        role = st.session_state.user_role
        can_manage_cm = role in ["Administrator", "ContentManager"]
        can_edit_cm = role in ["Administrator", "ContentManager", "ContentCreator"]
        if can_manage_cm:
            st.markdown("---")
            is_mod = q_row["IsLocallyModified"] in (1, True, "1")
            btn_disabled = not is_mod
            if st.button("📤 Αποστολή στο ClassMarker", use_container_width=True, disabled=btn_disabled, key=f"rev_btn_push_{sel_rev_id}"):
                with st.spinner("Αποστολή στο ClassMarker API..."):
                    if push_question_to_classmarker(sel_rev_id):
                        st.success("✅ Οι αλλαγές συγχρονίστηκαν στο ClassMarker!")
                        time.sleep(1)
                        st.rerun()
                        
        if can_edit_cm:
            st.markdown("---")
            if st.button("🛠️ Επεξεργασία Ερώτησης (Αναδυόμενο Παράθυρο)", use_container_width=True, type="primary", key=f"btn_trigger_edit_rev_{sel_rev_id}"):
                edit_question_dialog(q_row, categories_df, users_map, can_manage_cm)

@st.dialog("🛠️ Επεξεργασία Ερώτησης", width="large")
def edit_question_dialog(q_row, categories_df, users_map, can_manage):
    question_id = int(q_row["QuestionID"])
    st.markdown(f"### Επεξεργασία Ερώτησης (ID: {question_id})")
    
    edit_q_text = st.text_area("Κείμενο Ερώτησης", value=q_row["QuestionText"], key=f"dialog_edit_text_{question_id}", height=120)
    
    cat_options_map = dict(zip(categories_df["CategoryName"], categories_df["CategoryID"]))
    current_cat_name = q_row["CategoryName"]
    cat_list = list(cat_options_map.keys())
    cat_idx = cat_list.index(current_cat_name) if current_cat_name in cat_list else 0
    
    edit_cat_name = st.selectbox("Κατηγορία", options=cat_list, index=cat_idx, key=f"dialog_edit_cat_{question_id}")
    edit_cat_id = cat_options_map[edit_cat_name]
    
    col1, col2 = st.columns(2)
    with col1:
        edit_points = st.number_input("Βαθμοί", min_value=0.0, max_value=100.0, value=float(q_row["Points"]), step=0.5, key=f"dialog_edit_pts_{question_id}")
    with col2:
        st.write(" ") # align
        st.write(" ")
        edit_active = st.checkbox("Ενεργή", value=bool(q_row["Active"]), key=f"dialog_edit_act_{question_id}")
        
    # Edit choices/options based on type
    options = []
    try:
        options = json.loads(q_row["OptionsJSON"])
    except Exception:
        pass
        
    edited_options = []
    q_type = q_row["QuestionType"]
    
    # We display choices if the question type is multiple choice or true/false or multi response
    if q_type in ["multiple_choice", "true_false", "multiplechoice", "truefalse", "multipleresponse"]:
        st.write("---")
        st.markdown("**👉 Επιλογές Απαντήσεων:**")
        
        normalized_options = []
        if isinstance(options, dict):
            for key in sorted(options.keys()):
                opt = options[key]
                content = opt.get("content") or opt.get("text") or ""
                correct = opt.get("correct") or False
                normalized_options.append({"text": content, "correct": correct, "option_label": key})
        elif isinstance(options, list):
            normalized_options = options
            
        session_key = f"edit_opts_list_{question_id}"
        if session_key not in st.session_state:
            st.session_state[session_key] = normalized_options
            
        alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        
        if q_type in ["true_false", "truefalse"]:
            num_options = 2
        else:
            num_options = st.number_input(
                "Πλήθος Επιλογών Απαντήσεων (2-6):", 
                min_value=2, 
                max_value=6, 
                value=int(len(st.session_state[session_key])),
                key=f"dialog_num_opts_{question_id}"
            )
            
        # Adjust session state list length dynamically
        while len(st.session_state[session_key]) < num_options:
            next_label = alphabet[len(st.session_state[session_key])]
            st.session_state[session_key].append({"text": "", "correct": False, "option_label": next_label})
            
        while len(st.session_state[session_key]) > num_options:
            st.session_state[session_key].pop()
            
        edited_options = []
        for o_idx, opt in enumerate(st.session_state[session_key]):
            col_o1, col_o2 = st.columns([4, 1])
            label = opt.get("option_label") or alphabet[o_idx]
            with col_o1:
                opt_t = st.text_input(f"Επιλογή {label}", value=opt.get("text", ""), key=f"dialog_opt_t_{question_id}_{o_idx}")
            with col_o2:
                opt_c = st.checkbox("Σωστή", value=opt.get("correct", False), key=f"dialog_opt_c_{question_id}_{o_idx}")
            edited_options.append({"text": opt_t, "correct": opt_c, "option_label": label})
            
        st.session_state[session_key] = edited_options
            
    st.write("---")
    col_save, col_push = st.columns(2)
    with col_save:
        if st.button("💾 Αποθήκευση στο Support Hub", use_container_width=True, type="primary", key=f"dialog_btn_save_{question_id}"):
            opt_json_str = json.dumps(edited_options, ensure_ascii=False) if edited_options else q_row["OptionsJSON"]
            if update_local_question(int(question_id), int(edit_cat_id), edit_q_text, opt_json_str, float(edit_points), bool(edit_active)):
                st.success("✅ Η ερώτηση αποθηκεύτηκε τοπικά!")
                time.sleep(1)
                st.rerun()
                
    with col_push:
        if can_manage:
            is_mod = q_row["IsLocallyModified"] in (1, True, "1")
            btn_disabled = not is_mod
            if st.button("📤 Αποστολή στο ClassMarker", use_container_width=True, disabled=btn_disabled, key=f"dialog_btn_push_{question_id}"):
                with st.spinner("Αποστολή στο ClassMarker API..."):
                    if push_question_to_classmarker(question_id):
                        st.success("✅ Οι αλλαγές συγχρονίστηκαν στο ClassMarker!")
                        time.sleep(1)
                        st.rerun()
        else:
            st.button("📤 Αποστολή στο ClassMarker", use_container_width=True, disabled=True, help="Μόνο Administrators και ContentManagers μπορούν να στείλουν αλλαγές.")

def show_classmarker_questions(can_edit, can_manage):
    st.markdown("### 📝 Τράπεζα Ερωτήσεων ClassMarker")
    
    engine = get_db_engine()
    if not engine:
        st.error("❌ Αδυναμία σύνδεσης στη βάση δεδομένων.")
        return
        
    col_title, col_sync = st.columns([3, 1])
    with col_title:
        st.caption("Προβολή των συγχρονισμένων ερωτήσεων και κατηγοριών από το ClassMarker API.")
    with col_sync:
        if can_manage:
            if st.button("🔄 Συγχρονισμός Ερωτήσεων", use_container_width=True, type="primary"):
                if queue_classmarker_job('CLASSMARKER_QUESTIONS_SYNC', st.session_state.username):
                    st.success("✅ Η διεργασία συγχρονισμού ερωτήσεων προστέθηκε στην ουρά (ETL Queue).")
        else:
            st.button("🔄 Συγχρονισμός Ερωτήσεων", use_container_width=True, disabled=True, help="Δεν έχετε δικαιώματα εκτέλεσης ETL.")
            
    try:
        with engine.connect() as conn:
            categories_df = pd.read_sql(
                "SELECT c.CategoryID, c.CategoryName, p.CategoryName AS ParentCategoryName "
                "FROM CM_Categories c "
                "LEFT JOIN CM_Categories p ON c.ParentCategoryID = p.CategoryID "
                "ORDER BY c.CategoryName", 
                conn
            )
            questions_df = pd.read_sql(
                "SELECT q.QuestionID, q.CategoryID, c.CategoryName, p.CategoryName AS ParentCategoryName, "
                "       q.QuestionType, q.QuestionText, q.OptionsJSON, q.Points, q.Active, "
                "       q.IsLocallyModified, q.ReviewStage, u.DisplayName AS AssigneeName "
                "FROM CM_Questions q "
                "JOIN CM_Categories c ON q.CategoryID = c.CategoryID "
                "LEFT JOIN CM_Categories p ON c.ParentCategoryID = p.CategoryID "
                "LEFT JOIN Users u ON q.AssignedToUserID = u.UserID", 
                conn
            )
            # Load active users list for assignment
            users_res = conn.execute(
                text("SELECT UserID, DisplayName, Username FROM Users WHERE IsActive = 1 ORDER BY DisplayName")
            ).fetchall()
            users_map = {f"{r[1]} ({r[2]})": r[0] for r in users_res}
    except Exception as e:
        st.error(f"❌ Σφάλμα κατά τη φόρτωση δεδομένων: {e}")
        return
        
    if questions_df.empty:
        st.info("Δεν βρέθηκαν συγχρονισμένες ερωτήσεις στη βάση δεδομένων. Παρακαλώ ξεκινήστε συγχρονισμό.")
        return
        
    col_filter1, col_filter2, col_filter3, col_filter4 = st.columns([1, 1, 1, 1.5])
    with col_filter1:
        parent_options = ["Όλες οι Γονικές Κατηγορίες"] + sorted(list(categories_df["ParentCategoryName"].dropna().unique()))
        selected_parent = st.selectbox("📂 Γονική Κατηγορία", parent_options, key="select_parent_cat_filter")
    with col_filter2:
        if selected_parent != "Όλες οι Γονικές Κατηγορίες":
            child_cats = categories_df[categories_df["ParentCategoryName"] == selected_parent]["CategoryName"].unique()
        else:
            child_cats = categories_df["CategoryName"].unique()
        cat_options = ["Όλες οι Κατηγορίες"] + sorted(list(child_cats))
        selected_cat = st.selectbox("📂 Κατηγορία", cat_options, key="select_cat_filter")
    with col_filter3:
        type_options = ["Όλοι οι Τύποι"] + sorted(list(questions_df["QuestionType"].unique()))
        selected_type = st.selectbox("❓ Τύπος Ερώτησης", type_options, key="select_type_filter")
    with col_filter4:
        search_query = st.text_input("🔍 Αναζήτηση στο κείμενο της ερώτησης", placeholder="Πληκτρολογήστε λέξεις κλειδιά...", key="search_query_input")
        
    filtered_qs = questions_df.copy()
    if selected_parent != "Όλες οι Γονικές Κατηγορίες":
        filtered_qs = filtered_qs[filtered_qs["ParentCategoryName"] == selected_parent]
    if selected_cat != "Όλες οι Κατηγορίες":
        filtered_qs = filtered_qs[filtered_qs["CategoryName"] == selected_cat]
    if selected_type != "Όλοι οι Τύποι":
        filtered_qs = filtered_qs[filtered_qs["QuestionType"] == selected_type]
    if search_query:
        filtered_qs = filtered_qs[filtered_qs["QuestionText"].str.contains(search_query, case=False, na=False)]
        
    st.markdown(f"Βρέθηκαν **{len(filtered_qs)}** ερωτήσεις.")
    
    # Display table showing status indicators
    df_display = filtered_qs.copy()
    df_display["Κατάσταση Αλλαγών"] = df_display["IsLocallyModified"].apply(
        lambda x: "⚠️ Local Edits" if x in (1, True, "1") else "✅ Synced"
    )
    stage_labels = {1: "Draft", 2: "Stage 1", 3: "Stage 2", 4: "Stage 3", 5: "Verified"}
    df_display["Στάδιο Review"] = df_display["ReviewStage"].map(stage_labels)
    
    st.dataframe(
        df_display[["QuestionID", "ParentCategoryName", "CategoryName", "QuestionType", "QuestionText", "Points", "Active", "Κατάσταση Αλλαγών", "Στάδιο Review", "AssigneeName"]],
        use_container_width=True,
        hide_index=True,
        column_config={
            "QuestionID": st.column_config.NumberColumn("ID", format="%d"),
            "ParentCategoryName": "Γονική Κατηγορία",
            "CategoryName": "Κατηγορία",
            "QuestionType": "Τύπος",
            "QuestionText": "Κείμενο Ερώτησης",
            "Points": st.column_config.NumberColumn("Βαθμοί", format="%.1f"),
            "Active": st.column_config.CheckboxColumn("Ενεργή"),
            "Κατάσταση Αλλαγών": "Status",
            "Στάδιο Review": "Στάδιο",
            "AssigneeName": "Ανάθεση Σε"
        }
    )
    
    st.markdown("#### 🔍 Λεπτομέρειες & Επεξεργασία Ερώτησης")
    selected_q_id = st.selectbox(
        "Επιλογή Ερώτησης για προβολή/επεξεργασία:",
        options=filtered_qs["QuestionID"].tolist(),
        format_func=lambda x: f"ID: {x} - {filtered_qs[filtered_qs['QuestionID'] == x]['QuestionText'].values[0][:80]}...",
        key="select_q_id_details"
    )
    
    if selected_q_id:
        q_row = filtered_qs[filtered_qs["QuestionID"] == selected_q_id].iloc[0]
        st.info(f"**Ερώτηση (ID {q_row['QuestionID']}):** {q_row['QuestionText']}")
        st.markdown(
            f"**Γονική Κατηγορία:** {q_row['ParentCategoryName'] or 'N/A'} | "
            f"**Κατηγορία:** {q_row['CategoryName']} | "
            f"**Τύπος:** {q_row['QuestionType']} | "
            f"**Βαθμοί:** {q_row['Points']} | "
            f"**Κατάσταση:** {'Ενεργή' if q_row['Active'] else 'Ανενεργή'}"
        )
        
        # Original Question Compare Section
        orig_row = None
        if q_row["IsLocallyModified"] in (1, True, "1"):
            try:
                with engine.connect() as conn:
                    orig_row = conn.execute(
                        text("SELECT CategoryID, QuestionType, QuestionText, OptionsJSON, Points, Active FROM CM_Questions_Original WHERE QuestionID = :id"),
                        {"id": selected_q_id}
                    ).fetchone()
            except Exception:
                pass
                
        if orig_row:
            with st.expander("👀 Σύγκριση Αλλαγών με την Αρχική Ερώτηση (Diff)"):
                col_orig, col_mod = st.columns(2)
                with col_orig:
                    st.markdown("**📜 Αρχική Έκδοση (ClassMarker)**")
                    st.write(orig_row[2])
                    st.caption(f"**Βαθμοί:** {orig_row[4]} | **Κατάσταση:** {'Ενεργή' if orig_row[5] else 'Ανενεργή'}")
                    try:
                        orig_opts = json.loads(orig_row[3])
                        if orig_opts:
                            for o_idx, o in enumerate(orig_opts, 1):
                                txt = o.get("text", "")
                                is_corr = o.get("correct", False)
                                lbl = o.get("option_label") or str(o_idx)
                                st.markdown(f"{'✅' if is_corr else '❌'} **{lbl}**. {txt}")
                    except Exception:
                        pass
                with col_mod:
                    st.markdown("**✏️ Τροποποιημένη Έκδοση (Support Hub)**")
                    st.write(q_row['QuestionText'])
                    st.caption(f"**Βαθμοί:** {q_row['Points']} | **Κατάσταση:** {'Ενεργή' if q_row['Active'] else 'Ανενεργή'}")
                    try:
                        mod_opts = json.loads(q_row["OptionsJSON"])
                        if mod_opts:
                            for o_idx, o in enumerate(mod_opts, 1):
                                txt = o.get("text", "")
                                is_corr = o.get("correct", False)
                                lbl = o.get("option_label") or str(o_idx)
                                st.markdown(f"{'✅' if is_corr else '❌'} **{lbl}**. {txt}")
                    except Exception:
                        pass
        
        # Display current options
        options = []
        try:
            options = json.loads(q_row["OptionsJSON"])
            if options:
                st.markdown("**Επιλογές Απαντήσεων:**")
                normalized_options = []
                if isinstance(options, dict):
                    for key in sorted(options.keys()):
                        opt = options[key]
                        content = opt.get("content") or opt.get("text") or ""
                        correct = opt.get("correct") or False
                        normalized_options.append({"text": content, "correct": correct, "option_label": key})
                elif isinstance(options, list):
                    normalized_options = options
                
                for idx, opt in enumerate(normalized_options, 1):
                    is_correct = opt.get("correct", False)
                    opt_text = opt.get("text", "")
                    label = opt.get("option_label") or str(idx)
                    if is_correct:
                        st.markdown(f"✅ **{label}**. **{opt_text} (Σωστό)**")
                    else:
                        st.markdown(f"❌ **{label}**. {opt_text}")
        except Exception as e:
            st.caption(f"Δεν υπάρχουν δομημένες επιλογές (Σφάλμα: {e}).")

                # Edit Section (visible to Admin, ContentManager, ContentCreator)
        if can_edit:
            st.markdown("---")
            if st.button("🛠️ Επεξεργασία Ερώτησης (Αναδυόμενο Παράθυρο)", use_container_width=True, type="primary", key=f"btn_trigger_edit_{selected_q_id}"):
                edit_question_dialog(q_row, categories_df, users_map, can_manage)

            # Assignment Section
            with st.expander("📋 Ανάθεση Ελέγχου (Workflow)", expanded=False):
                sel_assignee = st.selectbox(
                    "Επιλέξτε χρήστη για τον έλεγχο:",
                    options=["-- Επιλογή Χρήστη --"] + list(users_map.keys()),
                    key=f"sel_assignee_{selected_q_id}"
                )
                stage_mapping = {
                    "Στάδιο 1: Αρχικός Έλεγχος (Peer Review Stage 1)": 2,
                    "Στάδιο 2: Peer Review (Peer Review Stage 2)": 3,
                    "Στάδιο 3: Τελική Έγκριση (Final Stage 3)": 4
                }
                sel_stage_label = st.selectbox(
                    "Στάδιο Ελέγχου:",
                    options=list(stage_mapping.keys()),
                    key=f"sel_stage_{selected_q_id}"
                )
                target_stage = stage_mapping[sel_stage_label]
                
                if st.button("🚀 Ανάθεση & Προώθηση", use_container_width=True, type="secondary", key=f"btn_assign_{selected_q_id}"):
                    if sel_assignee == "-- Επιλογή Χρήστη --":
                        st.warning("⚠️ Παρακαλώ επιλέξτε έναν έγκυρο χρήστη.")
                    else:
                        reviewer_user_id = users_map[sel_assignee]
                        if assign_question_reviewer(selected_q_id, reviewer_user_id, st.session_state.user_id, target_stage):
                            st.success(f"🚀 Η ερώτηση ανατέθηκε στον/στην {sel_assignee} στο {sel_stage_label}!")
                            time.sleep(1)
                            st.rerun()

def show_classmarker_results(can_manage):
    st.markdown("### 🛡️ Αποτελέσματα & Έλεγχος Proctoring")
    
    engine = get_db_engine()
    if not engine:
        st.error("❌ Αδυναμία σύνδεσης στη βάση δεδομένων.")
        return
        
    col_title, col_sync = st.columns([3, 1])
    with col_title:
        st.caption("Προβολή των συγχρονισμένων αποτελεσμάτων εξετάσεων και των συμβάντων Proctoring.")
    with col_sync:
        if can_manage:
            if st.button("🔄 Συγχρονισμός Αποτελεσμάτων", use_container_width=True, type="primary"):
                if queue_classmarker_job('CLASSMARKER_RESULTS_SYNC', st.session_state.username):
                    st.success("✅ Η διεργασία συγχρονισμού αποτελεσμάτων προστέθηκε στην ουρά (ETL Queue).")
        else:
            st.button("🔄 Συγχρονισμός Αποτελεσμάτων", use_container_width=True, disabled=True)
            
    try:
        with engine.connect() as conn:
            results_df = pd.read_sql(
                "SELECT ResultID, CandidateName, Score, "
                "       (DurationSeconds / 60) AS DurationMinutes, "
                "       ProctoringEventsCount AS InfractionCount, "
                "       ReviewStatus, ReviewedBy, ReviewedAt, CompanyCandidateID, CompanyPartnerID, "
                "       FinishedAt "
                "FROM CM_TestResults "
                "ORDER BY FinishedAt DESC", 
                conn
            )
    except Exception as e:
        st.error(f"❌ Σφάλμα κατά τη φόρτωση δεδομένων: {e}")
        return
        
    if results_df.empty:
        st.info("Δεν βρέθηκαν συγχρονισμένες αποτελέσματα στη βάση δεδομένων. Παρακαλώ ξεκινήστε συγχρονισμό.")
        return
        
    # Multi-select mass action controls
    st.markdown("#### ⚡ Μαζικές Ενέργειες Αξιολόγησης (Mass Actions)")
    col_mass_status, col_mass_notes, col_mass_btn = st.columns([1, 2, 1])
    with col_mass_status:
        mass_status = st.selectbox("Αλλαγή Κατάστασης", ["Approved", "Rejected", "Pending"], key="mass_status_select")
    with col_mass_notes:
        mass_notes = st.text_input("Κοινό Σχόλιο / Σημειώσεις", placeholder="Συμπληρώστε αν θέλετε...", key="mass_notes_input")
    with col_mass_btn:
        st.write(" ") # alignment
        st.write(" ")
        run_mass_action = st.button("⚡ Εκτέλεση", use_container_width=True, key="mass_action_run_btn")
        
    st.markdown("---")
    
    # Render interactive grid with selection
    # Using row selections via dataframe configurations
    selected_rows = []
    
    # We will use st.data_editor to get row selection status
    df_for_edit = results_df.copy()
    df_for_edit.insert(0, "Επιλογή", False)
    
    edited_df = st.data_editor(
        df_for_edit[["Επιλογή", "ResultID", "CandidateName", "Score", "DurationMinutes", "InfractionCount", "ReviewStatus", "FinishedAt"]],
        use_container_width=True,
        hide_index=True,
        column_config={
            "Επιλογή": st.column_config.CheckboxColumn("Επιλογή", default=False),
            "ResultID": st.column_config.NumberColumn("ID", format="%d"),
            "CandidateName": "Candidate",
            "Score": st.column_config.NumberColumn("Score (%)", format="%d"),
            "DurationMinutes": st.column_config.NumberColumn("Duration (min)", format="%d"),
            "InfractionCount": st.column_config.NumberColumn("Proctor Flags", format="%d"),
            "ReviewStatus": "Status",
            "FinishedAt": "Finished At"
        },
        disabled=["ResultID", "CandidateName", "Score", "DurationMinutes", "InfractionCount", "ReviewStatus", "FinishedAt"],
        key="data_editor_results_sync"
    )
    
    # Filter selected results
    selected_res_ids = edited_df[edited_df["Επιλογή"] == True]["ResultID"].tolist()
    
    if run_mass_action:
        if not selected_res_ids:
            st.warning("⚠️ Δεν έχετε επιλέξει κανένα αποτέλεσμα για μαζική επεξεργασία.")
        else:
            try:
                with engine.begin() as conn:
                    # Run bulk updates
                    conn.execute(
                        text(
                            "UPDATE CM_TestResults "
                            "SET ReviewStatus = :status, ReviewerNotes = :notes, "
                            "    ReviewedBy = :reviewer, ReviewedAt = :now "
                            "WHERE ResultID IN (" + ",".join([str(x) for x in selected_res_ids]) + ")"
                        ),
                        {
                            "status": mass_status,
                            "notes": mass_notes if mass_notes else None,
                            "reviewer": st.session_state.username,
                            "now": datetime.now()
                        }
                    )
                st.success(f"✅ Ενημερώθηκαν {len(selected_res_ids)} αποτελέσματα με επιτυχία.")
                time.sleep(1)
                st.rerun()
            except Exception as e:
                st.error(f"❌ Σφάλμα: {e}")
                
    st.markdown("#### 🔍 Λεπτομέρειες Αποτελέσματος & Timeline Proctoring")
    selected_res_id = st.selectbox(
        "Επιλογή Αποτελέσματος για προβολή λεπτομερειών:",
        options=results_df["ResultID"].tolist(),
        format_func=lambda x: f"ID: {x} - Candidate: {results_df[results_df['ResultID'] == x]['CandidateName'].values[0]} (Score: {results_df[results_df['ResultID'] == x]['Score'].values[0]}%)",
        key="selectbox_selected_res_id"
    )
    
    if selected_res_id:
        res_row = results_df[results_df["ResultID"] == selected_res_id].iloc[0]
        
        try:
            with engine.connect() as conn:
                res_details = conn.execute(
                    text("SELECT ReviewerNotes, CompanyCandidateID, CompanyPartnerID, ProctoringEventsJSON FROM CM_TestResults WHERE ResultID = :id"),
                    {"id": selected_res_id}
                ).fetchone()
        except Exception as e:
            st.error(f"❌ Σφάλμα: {e}")
            return
            
        rev_notes = res_details[0] if res_details else ""
        comp_cand_id = res_details[1] if res_details else ""
        comp_part_id = res_details[2] if res_details else ""
        raw_events = res_details[3] if res_details and len(res_details) > 3 else None
        
        infractions_list = []
        if raw_events:
            try:
                infractions_list = json.loads(raw_events)
            except Exception:
                pass
                
        col_res1, col_res2 = st.columns([1, 1])
        with col_res1:
            st.markdown(f"**Candidate:** {res_row['CandidateName']}")
            st.markdown(f"**Score:** {res_row['Score']}% | **Duration:** {res_row['DurationMinutes']} minutes")
            st.markdown(f"**Finished At:** {res_row['FinishedAt']}")
            st.markdown(f"**Infractions / Flag Count:** `{res_row['InfractionCount']}`")
            
        with col_res2:
            st.markdown(f"**Current Status:** `{res_row['ReviewStatus']}`")
            st.markdown(f"**Reviewed By:** {res_row['ReviewedBy'] or 'N/A'}")
            st.markdown(f"**Reviewed At:** {res_row['ReviewedAt'] or 'N/A'}")
            
        # Display Proctoring Infraction Timeline
        if infractions_list:
            st.warning(f"🚨 Ανιχνεύτηκαν {len(infractions_list)} συμβάντα proctoring (Flagged Events)!")
            with st.expander("👁️ Προβολή Infraction Timeline", expanded=True):
                for idx, log in enumerate(infractions_list, 1):
                    log_type = log.get("LogType", log.get("type", "Infraction"))
                    log_time = log.get("LogTime", log.get("time", ""))
                    log_details = log.get("LogDetails", log.get("detail", log.get("details", "")))
                    st.markdown(
                        f"**{idx}. [{log_type}] ({log_time})** - {log_details}"
                    )
        else:
            st.success("✅ Δεν καταγράφηκαν ύποπτα συμβάντα κατά την εξέταση (Proctoring Log clear).")
            
        st.markdown("---")
        st.markdown("**✍️ Διαχείριση & Αντιστοίχιση Αποτελέσματος**")
        
        col_id1, col_id2 = st.columns(2)
        with col_id1:
            company_cand_id = st.text_input("Company Candidate ID (π.χ. ΑΜ/Κωδικός)", value=comp_cand_id if comp_cand_id else "", key=f"comp_cand_id_field_{selected_res_id}")
        with col_id2:
            company_part_id = st.text_input("Company Partner ID (Συνεργάτης)", value=comp_part_id if comp_part_id else "", key=f"comp_part_id_field_{selected_res_id}")
            
        single_notes = st.text_area("Σχόλια / Σημειώσεις Διαχειριστή", value=rev_notes if rev_notes else "", key=f"reviewer_notes_field_{selected_res_id}")
        
        col_btn1, col_btn2, col_btn3 = st.columns(3)
        with col_btn1:
            if st.button("✅ Έγκριση Αποτελέσματος", use_container_width=True, type="primary", key=f"approve_{selected_res_id}"):
                try:
                    with engine.begin() as conn:
                        conn.execute(
                            text(
                                "UPDATE CM_TestResults "
                                "SET ReviewStatus = 'Approved', ReviewerNotes = :notes, "
                                "    ReviewedBy = :reviewer, ReviewedAt = :now, "
                                "    CompanyCandidateID = :cand_id, CompanyPartnerID = :part_id "
                                "WHERE ResultID = :id"
                            ),
                            {
                                "notes": single_notes if single_notes else None,
                                "reviewer": st.session_state.username,
                                "now": datetime.now(),
                                "cand_id": company_cand_id if company_cand_id else None,
                                "part_id": company_part_id if company_part_id else None,
                                "id": selected_res_id
                            }
                        )
                    st.success("✅ Το αποτέλεσμα εγκρίθηκε με επιτυχία.")
                    time.sleep(1)
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Σφάλμα: {e}")
        with col_btn2:
            if st.button("❌ Απόρριψη / Ακύρωση", use_container_width=True, key=f"reject_{selected_res_id}"):
                try:
                    with engine.begin() as conn:
                        conn.execute(
                            text(
                                "UPDATE CM_TestResults "
                                "SET ReviewStatus = 'Rejected', ReviewerNotes = :notes, "
                                "    ReviewedBy = :reviewer, ReviewedAt = :now, "
                                "    CompanyCandidateID = :cand_id, CompanyPartnerID = :part_id "
                                "WHERE ResultID = :id"
                            ),
                            {
                                "notes": single_notes if single_notes else None,
                                "reviewer": st.session_state.username,
                                "now": datetime.now(),
                                "cand_id": company_cand_id if company_cand_id else None,
                                "part_id": company_part_id if company_part_id else None,
                                "id": selected_res_id
                            }
                        )
                    st.warning("❌ Το τεστ απορρίφθηκε / ακυρώθηκε.")
                    time.sleep(1)
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Σφάλμα: {e}")
        with col_btn3:
            if st.button("🔄 Επαναφορά σε Εκκρεμότητα", use_container_width=True, key=f"reset_{selected_res_id}"):
                try:
                    with engine.begin() as conn:
                        conn.execute(
                            text(
                                "UPDATE CM_TestResults "
                                "SET ReviewStatus = 'Pending', ReviewerNotes = :notes, "
                                "    ReviewedBy = :reviewer, ReviewedAt = :now, "
                                "    CompanyCandidateID = :cand_id, CompanyPartnerID = :part_id "
                                "WHERE ResultID = :id"
                            ),
                            {
                                "notes": single_notes if single_notes else None,
                                "reviewer": st.session_state.username,
                                "now": datetime.now(),
                                "cand_id": company_cand_id if company_cand_id else None,
                                "part_id": company_part_id if company_part_id else None,
                                "id": selected_res_id
                            }
                        )
                    st.info("🔄 Η κατάσταση επαναφέρθηκε σε Pending.")
                    time.sleep(1)
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Σφάλμα: {e}")

def render_classmarker_content():
    st.subheader("🎓 Πιστοποιήσεις ClassMarker", divider="blue")
    
    # Ensure CM_Questions_Original exists
    try:
        engine = get_db_engine()
        if engine:
            with engine.begin() as conn:
                conn.execute(text("""
                    IF OBJECT_ID('CM_Questions_Original', 'U') IS NULL
                    BEGIN
                        CREATE TABLE CM_Questions_Original (
                            QuestionID INT PRIMARY KEY,
                            CategoryID INT NOT NULL,
                            QuestionType NVARCHAR(50) NOT NULL,
                            QuestionText NVARCHAR(MAX) NOT NULL,
                            OptionsJSON NVARCHAR(MAX) NULL,
                            Points DECIMAL(5,2) DEFAULT 1.0,
                            Active BIT DEFAULT 1,
                            SavedAt DATETIME DEFAULT GETDATE()
                        );
                    END
                """))
    except Exception as e:
        print(f"Error ensuring CM_Questions_Original exists: {e}")
        
    role = st.session_state.user_role
    can_manage = role in ["Administrator", "ContentManager"]
    can_edit = role in ["Administrator", "ContentManager", "ContentCreator"]
    
    tab_titles = []
    tab_callbacks = []
    
    # Tab 1: Questions Management (Admins, ContentManagers, ContentCreators)
    if can_edit:
        tab_titles.append("📝 Διαχείριση Ερωτήσεων")
        tab_callbacks.append(lambda: show_classmarker_questions(can_edit, can_manage))
        
    # Tab 2: Test Results & Proctoring (Admins, ContentManagers)
    if can_manage:
        tab_titles.append("🛡️ Αποτελέσματα & Proctoring")
        tab_callbacks.append(lambda: show_classmarker_results(can_manage))
        
    # Tab 3: Review / Approval Queue (All logged-in roles)
    tab_titles.append("📥 Εκκρεμότητες Ελέγχου")
    tab_callbacks.append(lambda: show_reviewer_queue(st.session_state.user_id))
    
    if tab_titles:
        tabs = st.tabs(tab_titles)
        for idx, tab in enumerate(tabs):
            with tab:
                tab_callbacks[idx]()
    else:
        st.warning("⚠️ Δεν έχετε δικαιώματα πρόσβασης στις λειτουργίες ClassMarker.")

# --- Render Layout based on Sidebar Selection ---
if "selected_page" in st.session_state:
    selected_page = st.session_state.selected_page
else:
    selected_page = "📊 Timesheet"

if selected_page == "📊 Timesheet":
    render_dashboard_content(df, last_updated)
elif selected_page == "💡 Knowledge Base":
    render_knowledge_base_content()
elif selected_page == "📢 Ανακοινώσεις & Tips":
    render_announcements_and_tips()
elif selected_page == "👤 Το Προφίλ μου":
    render_profile_content()
elif selected_page == "👥 Διαχείριση Ομάδων":
    render_management_content()
elif selected_page == "⏱️ Χρόνοι Απόκρισης":
    render_response_times_content()
elif selected_page == "🚀 ETL Manager":
    render_etl_manager_content()
elif selected_page == "🎓 ClassMarker":
    render_classmarker_content()
elif selected_page == "📖 Οδηγίες Χρήσης":
    render_manual_content()

# Backup current widget keys to prevent state loss on early reruns
st.session_state["widget_backup"] = {
    "proj_key": st.session_state.get("proj_key"),
    "auth_key": st.session_state.get("auth_key"),
    "charge_key": st.session_state.get("charge_key"),
    "time_key": st.session_state.get("time_key"),
    "partner_key": st.session_state.get("partner_key"),
    "lsp_key": st.session_state.get("lsp_key"),
    "comp_key": st.session_state.get("comp_key"),
    "dates_key": st.session_state.get("dates_key"),
    "group_key": st.session_state.get("group_key"),
    "group_filter_selectbox_key": st.session_state.get("group_filter_selectbox_key"),
    
    # Response Times page keys backup
    "rt_filter_project": st.session_state.get("rt_filter_project"),
    "rt_filter_status": st.session_state.get("rt_filter_status"),
    "rt_filter_subcategory": st.session_state.get("rt_filter_subcategory"),
    "rt_filter_date": st.session_state.get("rt_filter_date"),
    "rt_use_closed_date": st.session_state.get("rt_use_closed_date"),
    "rt_filter_closed_date": st.session_state.get("rt_filter_closed_date"),
    "rt_filter_assignee": st.session_state.get("rt_filter_assignee"),
    "rt_filter_components": st.session_state.get("rt_filter_components"),
    "rt_filter_partners": st.session_state.get("rt_filter_partners"),
    "rt_filter_customers": st.session_state.get("rt_filter_customers"),
    "rt_active_preset_name": st.session_state.get("rt_active_preset_name"),
    "rt_active_preset_json": st.session_state.get("rt_active_preset_json"),
    "rt_group_key": st.session_state.get("rt_group_key"),
    "active_app_view": st.session_state.get("active_app_view"),
}