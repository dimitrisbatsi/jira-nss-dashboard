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

        # Create ClassMarker CM_Categories table if not exists
        try:
            conn.execute(text("""
                IF OBJECT_ID('CM_Categories', 'U') IS NULL
                BEGIN
                    CREATE TABLE CM_Categories (
                        CategoryID INT PRIMARY KEY,
                        CategoryName NVARCHAR(255) NOT NULL,
                        ParentCategoryID INT NULL,
                        SyncedAt DATETIME DEFAULT GETDATE(),
                        CONSTRAINT FK_CM_Categories_Parent FOREIGN KEY (ParentCategoryID) REFERENCES CM_Categories(CategoryID)
                    );
                END
            """))
            print("  -> Table 'CM_Categories' created or verified.")
        except Exception as e:
            print(f"  -> Warning creating CM_Categories table: {e}")

        # Create ClassMarker CM_Questions table if not exists
        try:
            conn.execute(text("""
                IF OBJECT_ID('CM_Questions', 'U') IS NULL
                BEGIN
                    CREATE TABLE CM_Questions (
                        QuestionID INT PRIMARY KEY,
                        CategoryID INT NOT NULL,
                        QuestionType NVARCHAR(50) NOT NULL,
                        QuestionText NVARCHAR(MAX) NOT NULL,
                        OptionsJSON NVARCHAR(MAX) NULL,
                        Points DECIMAL(5,2) DEFAULT 1.0,
                        Active BIT DEFAULT 1,
                        UpdatedAt DATETIME NOT NULL,
                        SyncedAt DATETIME DEFAULT GETDATE(),
                        CONSTRAINT FK_CM_Questions_Category FOREIGN KEY (CategoryID) REFERENCES CM_Categories(CategoryID)
                    );
                END
            """))
            # Run column modifications if columns don't exist
            conn.execute(text("""
                IF COL_LENGTH('CM_Questions', 'ReviewStage') IS NULL
                    ALTER TABLE CM_Questions ADD ReviewStage INT DEFAULT 1;
                IF COL_LENGTH('CM_Questions', 'AssignedToUserID') IS NULL
                    ALTER TABLE CM_Questions ADD AssignedToUserID INT NULL CONSTRAINT FK_CM_Questions_AssignedTo FOREIGN KEY (AssignedToUserID) REFERENCES Users(UserID);
                IF COL_LENGTH('CM_Questions', 'AssignedByUserID') IS NULL
                    ALTER TABLE CM_Questions ADD AssignedByUserID INT NULL CONSTRAINT FK_CM_Questions_AssignedBy FOREIGN KEY (AssignedByUserID) REFERENCES Users(UserID);
                IF COL_LENGTH('CM_Questions', 'ReviewNotes') IS NULL
                    ALTER TABLE CM_Questions ADD ReviewNotes NVARCHAR(MAX) NULL;
                IF COL_LENGTH('CM_Questions', 'PreviousAssigneeID') IS NULL
                    ALTER TABLE CM_Questions ADD PreviousAssigneeID INT NULL CONSTRAINT FK_CM_Questions_Prev FOREIGN KEY (PreviousAssigneeID) REFERENCES Users(UserID);
                IF COL_LENGTH('CM_Questions', 'IsLocallyModified') IS NULL
                    ALTER TABLE CM_Questions ADD IsLocallyModified BIT DEFAULT 0;
            """))
            print("  -> Table 'CM_Questions' created or verified with review columns.")
        except Exception as e:
            print(f"  -> Warning creating/altering CM_Questions table: {e}")

        # Create ClassMarker CM_Questions_Original table if not exists
        try:
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
            print("  -> Table 'CM_Questions_Original' created or verified.")
        except Exception as e:
            print(f"  -> Warning creating CM_Questions_Original table: {e}")

        # Create ClassMarker CM_TestResults table if not exists
        try:
            conn.execute(text("""
                IF OBJECT_ID('CM_TestResults', 'U') IS NULL
                BEGIN
                    CREATE TABLE CM_TestResults (
                        ResultID BIGINT PRIMARY KEY,
                        TestID INT NOT NULL,
                        TestName NVARCHAR(255) NOT NULL,
                        UserID NVARCHAR(100) NOT NULL,
                        CandidateName NVARCHAR(255) NOT NULL,
                        CandidateEmail NVARCHAR(255) NOT NULL,
                        Score DECIMAL(5,2) NOT NULL,
                        Percentage DECIMAL(5,2) NOT NULL,
                        DurationSeconds INT NOT NULL,
                        FinishedAt DATETIME NOT NULL,
                        ProctoringFlag BIT DEFAULT 0,
                        ProctoringEventsCount INT DEFAULT 0,
                        ProctoringEventsJSON NVARCHAR(MAX) NULL,
                        ReviewStatus NVARCHAR(50) DEFAULT 'Pending',
                        ReviewerNotes NVARCHAR(MAX) NULL,
                        ReviewedBy NVARCHAR(100) NULL,
                        ReviewedAt DATETIME NULL,
                        CompanyCandidateID NVARCHAR(100) NULL,
                        CompanyPartnerID NVARCHAR(100) NULL,
                        SyncedAt DATETIME DEFAULT GETDATE()
                    );
                    CREATE INDEX IX_CM_TestResults_ReviewStatus ON CM_TestResults(ReviewStatus);
                    CREATE INDEX IX_CM_TestResults_ProctoringFlag ON CM_TestResults(ProctoringFlag);
                    CREATE INDEX IX_CM_TestResults_ProctoringCount ON CM_TestResults(ProctoringEventsCount);
                END
            """))
            print("  -> Table 'CM_TestResults' created or verified.")
        except Exception as e:
            print(f"  -> Warning creating CM_TestResults table: {e}")

        # Seed User Roles
        print("🛠️ Seeding User_Roles...")
        roles = [
            (1, "Administrator"),
            (2, "Team Leader"),
            (3, "Consultant"),
            (4, "ContentCreator"),
            (5, "ContentManager")
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
