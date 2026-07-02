import os
import tomllib
import urllib.parse
from sqlalchemy import create_engine, text
import pandas as pd

def get_db_engine():
    secrets_path = os.path.join(".streamlit", "secrets.toml")
    with open(secrets_path, "rb") as f:
        secrets = tomllib.load(f)
    conn_str = secrets.get("CONNECTION_STRING", "")
    
    parts = {}
    for part in conn_str.split(";"):
        if "=" in part:
            k, v = part.split("=", 1)
            parts[k.strip().lower()] = v.strip()
            
    server = parts.get("data source", parts.get("server", ""))
    database = parts.get("database", "")
    uid = parts.get("user id", parts.get("uid", ""))
    pwd = parts.get("password", parts.get("pwd", ""))
    
    pyodbc_conn_str = f"DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={server};DATABASE={database};"
    if uid and pwd:
        pyodbc_conn_str += f"UID={uid};PWD={pwd};"
    else:
        pyodbc_conn_str += "Trusted_Connection=yes;"
        
    params = urllib.parse.quote_plus(pyodbc_conn_str)
    return create_engine(f"mssql+pyodbc:///?odbc_connect={params}")

engine = get_db_engine()
with engine.connect() as conn:
    df = pd.read_sql("SELECT TOP 5 QuestionID, IsLocallyModified FROM CM_Questions", conn)
    print("DataFrame Types:")
    print(df.dtypes)
    print("\nDataFrame Values:")
    print(df)
    
    # Test map mapping
    df["Mapped_1"] = df["IsLocallyModified"].map({1: "⚠️ Local Edits", 0: "✅ Synced"})
    df["Mapped_Bool"] = df["IsLocallyModified"].map({True: "⚠️ Local Edits", False: "✅ Synced"})
    df["Mapped_Apply"] = df["IsLocallyModified"].apply(lambda x: "⚠️ Local Edits" if x in (1, True) else "✅ Synced")
    print("\nMapping results:")
    print(df)
