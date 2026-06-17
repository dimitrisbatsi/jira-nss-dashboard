import streamlit as st
import pandas as pd
import requests
import plotly.express as px
import io
import os
import re
import hashlib
from datetime import datetime

APP_VERSION = "26.3.0 (2026-06-16)"

# --- 1. Ρυθμίσεις Σελίδας ---
st.set_page_config(layout="wide", page_title="NSS Timesheet Dashboard", page_icon="📊")

# Initialize Session State Variables
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = None
    st.session_state.user_id = None
    st.session_state.user_role = None
    st.session_state.display_name = None
    st.session_state.default_project = None

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
    
    /* 4. Μικρότερο κενό ανάμεσα στα elements του Sidebar */
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
                "SELECT u.UserID, u.Username, u.Email, u.RoleID, u.DefaultProject, u.DisplayName, r.RoleName "
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
                    "RoleName": res[6]
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
                "SELECT u.UserID, u.Username, u.Email, u.RoleID, u.DefaultProject, u.DisplayName, r.RoleName "
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
                    "RoleName": res[6]
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

def get_user_default_preset(user_id):
    engine = get_db_engine()
    if not engine:
        return None
    from sqlalchemy import text
    try:
        with engine.connect() as conn:
            query = text("SELECT PresetName, FiltersJSON FROM User_Presets WHERE UserID = :user_id AND IsDefault = 1")
            res = conn.execute(query, {"user_id": user_id}).fetchone()
            if res:
                return {"PresetName": res[0], "FiltersJSON": res[1]}
    except Exception:
        pass
    return None

def set_preset_as_default(user_id, preset_name):
    engine = get_db_engine()
    if not engine:
        return False
    from sqlalchemy import text
    try:
        with engine.begin() as conn:
            # 1. Clear IsDefault for all presets of this user
            conn.execute(
                text("UPDATE User_Presets SET IsDefault = 0 WHERE UserID = :user_id"),
                {"user_id": user_id}
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
        if st.button("Είσοδος", type="primary", use_container_width=True):
            user = verify_user_credentials(login_username, login_password)
            if user:
                st.session_state.logged_in = True
                st.session_state.user_id = user["UserID"]
                st.session_state.username = user["Username"]
                st.session_state.user_role = user["RoleName"]
                st.session_state.display_name = user["DisplayName"]
                st.session_state.default_project = user["DefaultProject"]
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
    
    if st.sidebar.button("Αποσύνδεση", type="secondary", use_container_width=True):
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
        if "filters_init" in st.session_state:
            del st.session_state["filters_init"]
        st.toast("👋 Αποσυνδεθήκατε με επιτυχία.")

st.sidebar.write("---")
st.sidebar.markdown('<h1 class="stHeadingSidebar">🎛️ Φίλτρα Αναζήτησης</h1>', unsafe_allow_html=True)

if not st.session_state.logged_in:
    st.sidebar.info("💡 Συνδεθείτε για να αποθηκεύετε τα φίλτρα σας σε Previews!")

# --- Κουμπί Reset Filters ---
if st.sidebar.button("🔄 Καθαρισμός Φίλτρων", type="primary", use_container_width=True):
    # Reset filter keys from session state
    filter_keys = ['proj_key', 'auth_key', 'charge_key', 'time_key', 'partner_key', 'lsp_key', 'comp_key', 'dates_key', 'group_key', 'filters_init']
    for k in filter_keys:
        if k in st.session_state:
            del st.session_state[k]
            
    # Also clear active preset name
    if "active_preset_name" in st.session_state:
        del st.session_state["active_preset_name"]
    if "active_preset_json" in st.session_state:
        del st.session_state["active_preset_json"]
        
    st.rerun()

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
        st.session_state['dates_key'] = [pd.to_datetime(df['Date']).min(), pd.to_datetime(df['Date']).max()]
        st.session_state['group_key'] = ["Assignee"]
    
    st.session_state["filters_init"] = True

# --- 👥 Ομάδες Χρηστών Filter ---
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

sel_group_name = st.sidebar.selectbox(
    "👥 Ομάδα Χρηστών", 
    options=group_names, 
    index=0, 
    key="group_filter_selectbox_key",
    on_change=on_group_filter_change
)

# Limit assignee options if a group is selected
assignee_options = sorted([str(x) for x in df["Assignee"].dropna().unique()])
if sel_group_name != "Όλες οι Ομάδες":
    selected_group_id = next(g["GroupID"] for g in groups if g["GroupName"] == sel_group_name)
    group_members = load_group_members(selected_group_id)
    if group_members:
        assignee_options = sorted([m for m in group_members if m in assignee_options])

# 2. WIDGETS
date_range = st.sidebar.date_input("📅 Ημερομηνίες", key="dates_key")
sel_proj = st.sidebar.multiselect("📁 Project", options=sorted([str(x) for x in df["Project"].dropna().unique()]), key="proj_key")

if st.session_state.logged_in:
    user_name_to_select = st.session_state.display_name or st.session_state.username
    if st.sidebar.button("👤 Επιλογή: Μόνο Εγώ", type="secondary", use_container_width=True):
        all_auth = sorted([str(x) for x in df["Assignee"].dropna().unique()])
        if user_name_to_select in all_auth:
            st.session_state["auth_key"] = [user_name_to_select]
            st.rerun()

sel_auth = st.sidebar.multiselect("👤 Assignee", options=assignee_options, key="auth_key")
sel_charge = st.sidebar.multiselect("💰 Charge Type", options=sorted([str(x) for x in df["Charge Type"].dropna().unique()]), key="charge_key")
sel_time = st.sidebar.multiselect("⏱️ Time Type", options=sorted([str(x) for x in df["Time Type"].dropna().unique()]), key="time_key")

if "Partner Name" in df.columns:
    sel_partner = st.sidebar.multiselect("🤝 Partner Name", options=sorted([str(x) for x in df["Partner Name"].dropna().unique()]), key="partner_key")
else:
    sel_partner = []

if "LSP Customer Name" in df.columns:
    sel_lsp = st.sidebar.multiselect("🏢 LSP Customer", options=sorted([str(x) for x in df["LSP Customer Name"].dropna().unique()]), key="lsp_key")
else:
    sel_lsp = []

if "Parent Category" in df.columns:
    sel_comp = st.sidebar.multiselect("🧩 Κατηγορίες (Components)", options=sorted([str(x) for x in df["Parent Category"].dropna().unique()]), key="comp_key")
else:
    sel_comp = []

# --- 💾 Saved Previews Section ---
if st.session_state.logged_in:
    st.sidebar.write("---")
    with st.sidebar.expander("💾 Saved Previews (Presets)"):
        presets = load_user_presets(st.session_state.user_id)
        
        def on_preset_change():
            val = st.session_state.selected_preset_name_widget
            if val and val != "-- Επιλέξτε Preview --":
                clean_val = val
                if " (⭐ Προεπιλογή)" in clean_val:
                    clean_val = clean_val.replace(" (⭐ Προεπιλογή)", "")
                selected_preset = next((p for p in presets if p["PresetName"] == clean_val), None)
                if selected_preset:
                    import json
                    try:
                        filters = json.loads(selected_preset["FiltersJSON"])
                        # Set new params from preset directly in session state (bypassing URL parameters)
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
                            
                        # Store active preset information in session state
                        st.session_state.active_preset_name = selected_preset["PresetName"]
                        st.session_state.active_preset_json = selected_preset["FiltersJSON"]
                        
                        st.toast("✅ Το Preview φορτώθηκε επιτυχώς!")
                    except Exception as e:
                        st.error(f"Σφάλμα κατά τη φόρτωση του preview: {e}")
            # Reset selectbox state so it doesn't loop
            st.session_state.selected_preset_name_widget = "-- Επιλέξτε Preview --"

        preset_names = ["-- Επιλέξτε Preview --"] + [
            f"{p['PresetName']} (⭐ Προεπιλογή)" if p.get("IsDefault") else p["PresetName"]
            for p in presets
        ]
        selected_preset_name = st.selectbox(
            "Φόρτωση Preview", 
            options=preset_names, 
            key="selected_preset_name_widget",
            on_change=on_preset_change
        )
            
        st.markdown("---")
        new_preset_name = st.text_input("Όνομα νέου Preview", placeholder="π.χ. My Support Group")
        if st.button("Αποθήκευση Τρέχοντος Φίλτρου", type="primary", use_container_width=True):
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
                
        # Show sharing panel and active preset status if a preset is active
        active_preset_name = st.session_state.get("active_preset_name")
        if active_preset_name:
            st.markdown("---")
            st.markdown(f"📂 **Ενεργό Preview:** `{active_preset_name}`")
            
            # Check if it is the default one
            active_preset = next((p for p in presets if p["PresetName"] == active_preset_name), None)
            is_default_active = active_preset.get("IsDefault", False) if active_preset else False
            
            if is_default_active:
                st.markdown("⭐ **Προεπιλεγμένο Preview (αυτόματο)**")
            else:
                if st.button("⭐ Ορισμός ως Προεπιλογή", type="secondary", use_container_width=True):
                    if set_preset_as_default(st.session_state.user_id, active_preset_name):
                        st.toast("✅ Ορίστηκε ως προεπιλεγμένο preview!")
                        st.rerun()
            
            col_update, col_reload, col_close = st.columns(3)
            with col_update:
                if st.button("💾 Ενημέρωση", type="primary", use_container_width=True):
                    # Build current filters dictionary
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
                if st.button("🔄 Επαναφορά", type="secondary", use_container_width=True, help="Επαναφορά στα αρχικά αποθηκευμένα φίλτρα"):
                    if "active_preset_json" in st.session_state:
                        apply_preset_filters(st.session_state.active_preset_json)
                        st.toast("🔄 Τα αρχικά φίλτρα του Preview επαναφέρθηκαν!")
                        st.rerun()
            with col_close:
                if st.button("❌ Κλείσιμο", type="secondary", use_container_width=True):
                    if "active_preset_name" in st.session_state:
                        del st.session_state["active_preset_name"]
                    if "active_preset_json" in st.session_state:
                        del st.session_state["active_preset_json"]
                    st.rerun()
                
            st.markdown("---")
            all_users = load_all_active_users()
            other_users = [u for u in all_users if u["UserID"] != st.session_state.user_id]
            other_user_names = [u["Username"] for u in other_users]
            
            st.markdown("**Κοινοποίηση σε άλλον χρήστη:**")
            share_with = st.selectbox("Επιλέξτε Χρήστη", options=["-- Επιλογή --"] + other_user_names, key="preset_share_user_select")
            if st.button("Κοινοποίηση", type="secondary", use_container_width=True):
                if share_with != "-- Επιλογή --":
                    target_user = next(u for u in other_users if u["Username"] == share_with)
                    shared_name = f"{active_preset_name} (Shared by {st.session_state.username})"
                    if save_user_preset(target_user["UserID"], shared_name, st.session_state.active_preset_json):
                        st.success(f"Κοινοποιήθηκε στον χρήστη {share_with}!")

st.sidebar.write("")
st.sidebar.caption(f"**App Version:** {APP_VERSION}")



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

# --- 5. Rendering Functions ---

def render_dashboard_content(df, last_updated, start, end, sel_proj, sel_auth, sel_charge, sel_time, sel_partner, sel_lsp, sel_comp, filtered_df):
    col_title, col_time = st.columns([3, 1])
    
    with col_title:
        st.title("📊 NSS Support Dashboard")
        
    with col_time:
        st.write("") 
        st.write("")
        st.caption(f"🔄 **Τελευταία Ενημέρωση Δεδομένων:** {last_updated}")
    
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
    
    if st.button("Αποθήκευση Προτιμήσεων", type="primary"):
        val = None if new_default_proj == "-- Κανένα --" else new_default_proj
        if update_user_default_project(st.session_state.user_id, val):
            st.session_state.default_project = val
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
            
            st.dataframe(df_users, use_container_width=True, hide_index=True)
            
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
                                    st.success("✅ Η κατάσταση του χρήστη ενημε렀θηκε!")
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
            if st.button("Αποθήκευση Αλλαγών", type="primary", use_container_width=True):
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
                if st.button("🗑️ Διαγραφή Ομάδας", type="secondary", use_container_width=True):
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

def render_manual_content():
    st.subheader("📖 Οδηγίες Χρήσης NSS Timesheet Dashboard", divider="blue")
    
    st.write(
        "Καλώς ορίσατε στον οδηγό χρήσης της εφαρμογής **NSS Timesheet Dashboard**. "
        "Εδώ θα βρείτε αναλυτικές οδηγίες για τη χρήση των φίλτρων, των Previews (αποθηκευμένων φίλτρων), "
        "της αυτόματης σύνδεσης, καθώς και των λειτουργιών διαχείρισης ομάδων."
    )
    
    # expander 1: Filters & Search
    with st.expander("🔍 1. Φιλτράρισμα & Αναζήτηση"):
        st.markdown("""
        Η εφαρμογή σάς επιτρέπει να φιλτράρετε τα Worklogs της βάσης δεδομένων χρησιμοποιώντας το **Sidebar (αριστερό μενού)**:
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
           - Μπορείτε να μοιραστείτε το ενεργό Preview σας με έναν άλλον ενεργό χρήστη, επιλέγοντας το όνομά του και πατώντας **Κοινοποίηση**. Το Preview θα εμφανιστεί αυτόματα στη δική του λίστα!
        5. **🗂️ Ομαδοποίηση (Group By)**:
           - Μαζί με τα φίλτρα αναζήτησης, το Preview αποθηκεύει και την τρέχουσα επιλογή ομαδοποίησης (Group By), ώστε ο πίνακας να εμφανίζεται ακριβώς όπως τον διαμορφώσατε.
        6. **⭐ Ορισμός ως Προεπιλογή**:
           - Μπορείτε να ορίσετε ένα Preview ως προεπιλεγμένο πατώντας **⭐ Ορισμός ως Προεπιλογή**. Το συγκεκριμένο Preview θα φορτώνει αυτόματα κάθε φορά που ανοίγετε την εφαρμογή.
        """)
        
    # expander 3: Authentication & Connection Persistence
    with st.expander("🔑 3. Σύνδεση Χρήστη & Cookies"):
        st.markdown("""
        * **Soft Login**: Παρέχει πρόσβαση στις προηγμένες δυνατότητες (Previews, Προφίλ, Διαχείριση Ομάδων). Η εφαρμογή παραμένει δημόσια για ανάγνωση (read-only) για επισκέπτες που δεν επιθυμούν να συνδεθούν.
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
        * **Ορίσετε Προεπιλεγμένο Project (Default Project)**: Επιλέξτε το project που δουλεύετε συχνότερα. Κάθε φορά που ανοίγετε την εφαρμογή, αυτό το project θα είναι προεπιλεγμένο αυτόματα.
        * **Αλλάξετε Κωδικό Πρόσβαση (Change Password)**: Εισάγετε τον τρέχοντα κωδικό σας και τον νέο κωδικό για να τον ενημερώσετε με ασφάλεια.
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

# --- Render Tab Layout ---
if st.session_state.logged_in:
    tab_list = ["📊 Timesheet", "👤 Το Προφίλ μου"]
    if st.session_state.user_role in ["Administrator", "Team Leader"]:
        tab_list.append("👥 Διαχείριση Ομάδων")
    tab_list.append("📖 Οδηγίες Χρήσης")
        
    main_tabs = st.tabs(tab_list)
    
    with main_tabs[0]:
        render_dashboard_content(df, last_updated, start, end, sel_proj, sel_auth, sel_charge, sel_time, sel_partner, sel_lsp, sel_comp, filtered_df)
        
    with main_tabs[1]:
        render_profile_content()
        
    idx = 2
    if st.session_state.user_role in ["Administrator", "Team Leader"]:
        with main_tabs[idx]:
            render_management_content()
        idx += 1
        
    with main_tabs[idx]:
        render_manual_content()
else:
    tab_list = ["📊 Timesheet", "📖 Οδηγίες Χρήσης"]
    main_tabs = st.tabs(tab_list)
    
    with main_tabs[0]:
        render_dashboard_content(df, last_updated, start, end, sel_proj, sel_auth, sel_charge, sel_time, sel_partner, sel_lsp, sel_comp, filtered_df)
    with main_tabs[1]:
        render_manual_content()