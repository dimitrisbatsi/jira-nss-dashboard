import streamlit as st
import pandas as pd
import requests
import plotly.express as px
import io
import sqlite3
import os
from datetime import datetime

APP_VERSION = "26.1.2 (2026-03-31)"

# --- 1. Ρυθμίσεις Σελίδας ---
st.set_page_config(layout="wide", page_title="NSS Timesheet Dashboard", page_icon="📊")

# Ένεση Custom CSS για σμίκρυνση των στοιχείων
st.markdown("""
    <style>
    /* 1. Μείωση του τεράστιου κενού στην κορυφή και στα πλάγια της σελίδας */
    .block-container {
        padding-top: 1.5rem !important;
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

# --- 2. Φόρτωση από Βάση Δεδομένων ---
@st.cache_data(ttl=60) # Cache για 1 λεπτό μόνο, αφού η DB είναι αστραπιαία
def load_data_from_db():
    db_path = "timesheet.db"
    if not os.path.exists(db_path):
        return pd.DataFrame(), "Ποτέ"
    
    # Ανάγνωση από SQLite
    conn = sqlite3.connect(db_path)
    df = pd.read_sql("SELECT * FROM worklogs", conn)
    conn.close()
    
    # Διαβάζουμε την ώρα που τροποποιήθηκε το αρχείο DB
    mtime = os.path.getmtime(db_path)
    last_updated = datetime.fromtimestamp(mtime).strftime("%d/%m/%Y %H:%M")
    
    return df, last_updated

df, last_updated = load_data_from_db()

if df.empty:
    st.warning("⚠️ Η Βάση Δεδομένων είναι άδεια ή δεν έχει δημιουργηθεί. Παρακαλώ τρέξτε το sync_db.py")
    st.stop()

# --- 4. SIDEBAR (Μόνο Φίλτρα Αναζήτησης) ---
# st.sidebar.title("🎛️ Φίλτρα Αναζήτησης")
st.sidebar.markdown('<h1 class="stHeadingSidebar">🎛️ Φίλτρα Αναζήτησης</h1>', unsafe_allow_html=True)

# --- Κουμπί Reset Filters ---
if st.sidebar.button("🔄 Καθαρισμός Φίλτρων", type="primary", width='stretch'):
    st.query_params.clear()
    st.session_state.clear() # Καθαρίζει την εσωτερική μνήμη
    st.rerun()

# 1. INITIALIZATION: Διαβάζουμε το URL ΜΟΝΟ την πρώτη φορά που ανοίγει η εφαρμογή
if "filters_init" not in st.session_state:
    url_params = st.query_params
    
    # Φτιάχνουμε καθαρές, αλφαβητικά ταξινομημένες λίστες για όλα τα πεδία
    all_proj = sorted([str(x) for x in df["Project"].dropna().unique()])
    all_auth = sorted([str(x) for x in df["Assignee"].dropna().unique()])
    all_charge = sorted([str(x) for x in df["Charge Type"].dropna().unique()])
    all_time = sorted([str(x) for x in df["Time Type"].dropna().unique()])
    
    # Αποθηκεύουμε τα defaults στα keys. 
    # Αν το URL έχει τιμές, τις παίρνουμε (ταξινομημένες), αλλιώς βάζουμε τα πάντα (ήδη ταξινομημένα).
    st.session_state['proj_key'] = sorted(url_params.get_all("project")) if url_params.get_all("project") else all_proj
    st.session_state['auth_key'] = sorted(url_params.get_all("Assignee")) if url_params.get_all("Assignee") else all_auth
    st.session_state['charge_key'] = sorted(url_params.get_all("charge")) if url_params.get_all("charge") else all_charge
    st.session_state['time_key'] = sorted(url_params.get_all("time")) if url_params.get_all("time") else all_time
    
    raw_dates = url_params.get_all("dateRange")
    if raw_dates:
        st.session_state['dates_key'] = [pd.to_datetime(d).date() for d in raw_dates]
    else:
        st.session_state['dates_key'] = [pd.to_datetime(df['Date']).min(), pd.to_datetime(df['Date']).max()]
        
    group_options = ["Assignee", "Parent Key", "Issue Key", "Project", "Time Type", "Charge Type"]
    url_group = url_params.get_all("groupBy")
    valid_group = [g for g in url_group if g in group_options]
    st.session_state['group_key'] = valid_group if valid_group else ["Assignee"]
    
    st.session_state["filters_init"] = True

# 2. WIDGETS: Χρησιμοποιούμε τις ταξινομημένες λίστες στα options
date_range = st.sidebar.date_input("📅 Ημερομηνίες", key="dates_key")
sel_proj = st.sidebar.multiselect("📁 Project", options=sorted([str(x) for x in df["Project"].dropna().unique()]), key="proj_key")
sel_auth = st.sidebar.multiselect("👤 Assignee", options=sorted([str(x) for x in df["Assignee"].dropna().unique()]), key="auth_key")
sel_charge = st.sidebar.multiselect("💰 Charge Type", options=sorted([str(x) for x in df["Charge Type"].dropna().unique()]), key="charge_key")
sel_time = st.sidebar.multiselect("⏱️ Time Type", options=sorted([str(x) for x in df["Time Type"].dropna().unique()]), key="time_key")

st.sidebar.write("")
st.sidebar.caption(f"**App Version:** {APP_VERSION}")

# 3. ΕΝΗΜΕΡΩΣΗ URL: Γράφουμε τις επιλογές στο URL για να μπορείς να τις κάνεις Share
st.query_params["dateRange"] = [str(d) for d in date_range] 
st.query_params["project"] = sel_proj
st.query_params["Assignee"] = sel_auth
st.query_params["charge"] = sel_charge
st.query_params["time"] = sel_time

# Φιλτράρισμα Δεδομένων
start = date_range[0].strftime('%Y-%m-%d')
end = date_range[1].strftime('%Y-%m-%d') if len(date_range) > 1 else start

mask = (df["Date"] >= start) & (df["Date"] <= end) & \
       df["Project"].isin(sel_proj) & df["Assignee"].isin(sel_auth) & \
       df["Charge Type"].isin(sel_charge) & df["Time Type"].isin(sel_time)

filtered_df = df[mask]

# --- 5. ΚΕΝΤΡΙΚΗ ΟΘΟΝΗ (Main Layout) ---
col_title, col_time = st.columns([3, 1])

with col_title:
    st.title("📊 NSS Support Dashboard")
    
with col_time:
    st.write("") 
    st.write("")
    st.caption(f"🔄 **Τελευταία Ενημέρωση:** {last_updated}")

st.subheader("📌 Σύνοψη", divider="blue")
m1, m2, m3, m4 = st.columns(4)
total_mins = filtered_df["Minutes"].sum()
m1.metric("Συνολικός Χρόνος", format_to_hhmm(total_mins))
m2.metric("Ενεργά Projects", filtered_df["Project"].nunique())
m3.metric("Σύμβουλοι (Assignees)", filtered_df["Assignee"].nunique())
m4.metric("Μοναδικά Tickets", filtered_df["Issue Key"].nunique())

# --- Ενότητα Β: Pivot Table & Export ---
st.subheader("📅 Αναλυτικό Timesheet", divider="gray")

group_options = ["Assignee", "Parent Key", "Issue Key", "Project", "Time Type", "Charge Type"]
sel_group = st.multiselect("🗂️ Ομαδοποίηση (Group By) ανά:", options=group_options, key="group_key")
st.query_params["groupBy"] = sel_group

if not sel_group:
    st.error("Επιλέξτε τουλάχιστον ένα πεδίο ομαδοποίησης.")
    st.stop()

if not filtered_df.empty:
    pivot = filtered_df.pivot_table(
        index=sel_group, 
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
    if "Issue Key" in pivot_fmt.columns:
        col_config["Issue Key"] = None 

    if "Parent Key" in sel_group:
        jira_base = f"https://{JIRA_DOMAIN}/browse/"
        pivot_fmt["🔗 Link"] = pivot_fmt["Parent Key"].apply(
            lambda x: f"{jira_base}{x}" if x and x != "Σύνολο" else None
        )
        cols = list(pivot_fmt.columns)
        cols.remove("🔗 Link")
        pk_index = cols.index("Parent Key")
        cols.insert(pk_index + 1, "🔗 Link")
        pivot_fmt = pivot_fmt[cols]
        col_config["🔗 Link"] = st.column_config.LinkColumn("Άνοιγμα", display_text="Issue URL")

    def highlight_cells(row):
        styles = [''] * len(row)
        is_total_row = row[sel_group[0]] == 'Σύνολο'
        for i, col in enumerate(row.index):
            val = row[col]
            cell_style = ''
            if is_total_row or col == 'Σύνολο':
                cell_style = 'font-weight: bold; background-color: #E2E8F0; color: #1E293B;' 
            elif col in sel_group:
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

    # --- ΒΕΛΤΙΩΣΗ 1 & 2: Έλεγχος μεγέθους ΠΡΙΝ το styling ---
    total_cells = pivot_fmt.size 
    max_allowed_cells = 200000 

    if total_cells > max_allowed_cells:
        st.warning("⚠️ **Πάρα πολλά δεδομένα για προβολή!**\n\nΟ πίνακας περιέχει πάνω από τον επιτρεπτό αριθμό εγγραφών, κάτι που μπορεί να καθυστερήσει την εφαρμογή. Παρακαλώ χρησιμοποιήστε τα **Φίλτρα** για να δείτε τα αποτελέσματα.")
    else:
        # Κάνουμε styling ΜΟΝΟ αν πρόκειται να το δείξουμε
        styled_pivot = pivot_fmt.style.apply(highlight_cells, axis=1)
        st.dataframe(
            styled_pivot,
            width='stretch',
            height=500, 
            column_config=col_config,
            hide_index=True
        )
    
    # --- Καθαρό Export (χωρίς styles) για ταχύτητα και συμβατότητα ---
    def convert_df_to_excel(df_to_export):
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df_to_export.to_excel(writer, sheet_name='Timesheet', index=False)
        return output.getvalue()

    col_empty, col_btn = st.columns([5, 1])
    with col_btn:
        st.download_button(
            label="📥 Λήψη σε Excel",
            data=convert_df_to_excel(pivot_fmt), # Εξάγουμε το καθαρό dataframe
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

# --- ΒΕΛΤΙΩΣΗ 3: Μετατροπή σε Ώρες για τα Γραφήματα ---
c1, c2 = st.columns(2)

with c1:
    chart_time = filtered_df.groupby("Time Type")["Minutes"].sum().reset_index()
    chart_time["Ώρες"] = (chart_time["Minutes"] / 60).round(1) # Υπολογισμός σε ώρες
    
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