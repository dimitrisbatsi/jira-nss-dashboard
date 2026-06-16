import tomllib
import urllib.parse
import hashlib
import sys

# Reconfigure console output encoding to UTF-8 for Greek/Emoji console display on Windows
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

from sqlalchemy import create_engine, text

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()

secrets_path = ".streamlit/secrets.toml"
try:
    with open(secrets_path, "rb") as f:
        secrets = tomllib.load(f)
    conn_str = secrets.get("CONNECTION_STRING", "").strip()
    if not conn_str:
        raise ValueError("CONNECTION_STRING parameter is missing in secrets.toml")
except Exception as e:
    print(f"❌ Error reading secrets: {e}")
    sys.exit(1)

# Parse connection string
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
    print("❌ Server and Database are required connection parameters.")
    sys.exit(1)

drivers = ["ODBC Driver 17 for SQL Server", "SQL Server Native Client 11.0", "SQL Server"]
engine = None
last_error = None

for driver in drivers:
    try:
        pyodbc_conn_str = f"DRIVER={{{driver}}};SERVER={server};DATABASE={database};UID={uid};PWD={pwd};"
        params = urllib.parse.quote_plus(pyodbc_conn_str)
        engine = create_engine(f"mssql+pyodbc:///?odbc_connect={params}")
        with engine.connect() as conn:
            pass
        print(f"✅ Successfully connected to SQL Server using driver: {driver}")
        break
    except Exception as ex:
        last_error = ex

if engine is None:
    print(f"❌ Failed to connect to SQL Server: {last_error}")
    sys.exit(1)

# Run migrations and seed data
try:
    with engine.begin() as conn:
        print("🛠️ Running database alterations...")
        
        # Add DefaultProject to Users if not exists
        try:
            conn.execute(text("ALTER TABLE Users ADD DefaultProject NVARCHAR(100) NULL"))
            print("  -> Column 'DefaultProject' added to Users table.")
        except Exception as e:
            if "already" in str(e).lower() or "Duplicate column name" in str(e) or "Column names in each table must be unique" in str(e):
                print("  -> Column 'DefaultProject' already exists.")
            else:
                print(f"  -> Warning adding DefaultProject: {e}")

        # Add DisplayName to Users if not exists
        try:
            conn.execute(text("ALTER TABLE Users ADD DisplayName NVARCHAR(255) NULL"))
            print("  -> Column 'DisplayName' added to Users table.")
        except Exception as e:
            if "already" in str(e).lower() or "Duplicate column name" in str(e) or "Column names in each table must be unique" in str(e):
                print("  -> Column 'DisplayName' already exists.")
            else:
                print(f"  -> Warning adding DisplayName: {e}")

        # Create User_Sessions table if not exists
        try:
            conn.execute(text("""
                IF OBJECT_ID(N'[dbo].[User_Sessions]', N'U') IS NULL
                BEGIN
                    CREATE TABLE User_Sessions (
                        SessionID NVARCHAR(100) PRIMARY KEY,
                        UserID INT NOT NULL,
                        ExpiresAt DATETIME NOT NULL,
                        CONSTRAINT FK_Sessions_Users FOREIGN KEY (UserID) REFERENCES Users(UserID) ON DELETE CASCADE
                    );
                END
            """))
            print("  -> Table 'User_Sessions' created or verified.")
        except Exception as e:
            print(f"  -> Warning creating User_Sessions table: {e}")

        # Seed User Roles
        print("🛠️ Seeding User_Roles...")
        roles = [
            (1, "Administrator"),
            (2, "Team Leader"),
            (3, "Consultant")
        ]
        for role_id, role_name in roles:
            # Check if role exists
            res = conn.execute(text("SELECT 1 FROM User_Roles WHERE RoleID = :id"), {"id": role_id}).fetchone()
            if not res:
                # Use IDENTITY_INSERT to insert specific primary key
                conn.execute(text("SET IDENTITY_INSERT User_Roles ON"))
                conn.execute(text("INSERT INTO User_Roles (RoleID, RoleName) VALUES (:id, :name)"), {"id": role_id, "name": role_name})
                conn.execute(text("SET IDENTITY_INSERT User_Roles OFF"))
                print(f"  -> Inserted role: {role_name}")
            else:
                print(f"  -> Role already exists: {role_name}")

        # Seed Default Admin User
        print("🛠️ Seeding default administrator account...")
        admin_username = "d.batsilis"
        admin_email = "d.batsilis@epsilon-singularlogic.eu"
        admin_password_hash = hash_password("admin123")
        admin_role_id = 1 # Administrator
        
        res_user = conn.execute(text("SELECT 1 FROM Users WHERE Username = :username"), {"username": admin_username}).fetchone()
        if not res_user:
            conn.execute(
                text("INSERT INTO Users (Username, PasswordHash, Email, RoleID, IsActive, DisplayName) "
                     "VALUES (:username, :pwd_hash, :email, :role_id, 1, :disp_name)"),
                {
                    "username": admin_username,
                    "pwd_hash": admin_password_hash,
                    "email": admin_email,
                    "role_id": admin_role_id,
                    "disp_name": "Dimitrios Batsilis"
                }
            )
            print(f"  -> Seeded administrator user '{admin_username}' with email '{admin_email}'.")
        else:
            print(f"  -> Administrator user '{admin_username}' already exists.")
            
    print("🏁 Seeding completed successfully!")
except Exception as e:
    print(f"❌ Error during database seeding: {e}")
