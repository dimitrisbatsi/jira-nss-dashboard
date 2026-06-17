import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text

# Reuse the DB connection logic
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

import urllib.parse
pyodbc_conn_str = f"DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={server};DATABASE={database};"
if uid and pwd:
    pyodbc_conn_str += f"UID={uid};PWD={pwd};"
else:
    pyodbc_conn_str += "Trusted_Connection=yes;"
    
params = urllib.parse.quote_plus(pyodbc_conn_str)
engine = create_engine(f"mssql+pyodbc:///?odbc_connect={params}")

with engine.connect() as conn:
    res = conn.execute(text("SELECT * FROM User_Sessions")).fetchall()
    print("User Sessions in Database:")
    for row in res:
        print(row)
