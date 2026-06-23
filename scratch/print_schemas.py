import sys
import os
import toml
import urllib.parse
from sqlalchemy import create_engine, text

# Load secrets directly
secrets_path = r'c:\Users\d.batsilis\OneDrive - Epsilon Net S.A\Development\NSSTimesheetApp\.streamlit\secrets.toml'
if not os.path.exists(secrets_path):
    print("secrets.toml not found")
    sys.exit(1)

secrets = toml.load(secrets_path)
conn_str = secrets['CONNECTION_STRING']

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

engine = None
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
            # Try a simple select to test connection
            conn.execute(text("SELECT 1")).fetchone()
        print(f"Successfully connected with driver: {driver}")
        break
    except Exception as e:
        engine = None
        continue

if not engine:
    print("Could not connect to database with any driver.")
    sys.exit(1)

with engine.connect() as conn:
    for table in ['ContentHub', 'KBArticles', 'Users', 'User_Roles']:
        print(f'=== TABLE: {table} ===')
        try:
            res = conn.execute(text(f"""
                SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH, IS_NULLABLE
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_NAME = '{table}'
            """)).fetchall()
            for row in res:
                print(f"  {row[0]} ({row[1]} {row[2] if row[2] else ''}) - Nullable: {row[3]}")
        except Exception as e:
            print(f'Error: {e}')
