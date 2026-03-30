import streamlit as st
import pandas as pd
import requests
import plotly.express as px
import io
import sqlite3
import os
from datetime import datetime

# --- 1. Ρυθμίσεις Σελίδας ---
st.set_page_config(layout="wide", page_title="NSS Timesheet Dashboard", page_icon="📊")
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
st.sidebar.title("🎛️ Φίλτρα Αναζήτησης")

# --- Κουμπί Reset Filters ---
if st.sidebar.button("🔄 Καθαρισμός Φίλτρων", type="primary", use_container_width=True):
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
    st.session_state['group_key'] = valid_group if valid_group else ["Assignee", "Parent Key"]
    
    st.session_state["filters_init"] = True

# 2. WIDGETS: Χρησιμοποιούμε τις ταξινομημένες λίστες στα options
date_range = st.sidebar.date_input("📅 Ημερομηνίες", key="dates_key")
sel_proj = st.sidebar.multiselect("📁 Project", options=sorted([str(x) for x in df["Project"].dropna().unique()]), key="proj_key")
sel_auth = st.sidebar.multiselect("👤 Assignee", options=sorted([str(x) for x in df["Assignee"].dropna().unique()]), key="auth_key")
sel_charge = st.sidebar.multiselect("💰 Charge Type", options=sorted([str(x) for x in df["Charge Type"].dropna().unique()]), key="charge_key")
sel_time = st.sidebar.multiselect("⏱️ Time Type", options=sorted([str(x) for x in df["Time Type"].dropna().unique()]), key="time_key")

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

# 1. Φίλτρο Ομαδοποίησης (Με τη χρήση του key="group_key" και χωρίς default)
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
    
    # Απόκρυψη του Issue Key από το UI αν έχει επιλεχθεί στο Group By
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

    # Νέο Χρωματικό Στυλ (Ομοιόμορφο Απαλό Λαχανί)
    # 5. Το νέο Conditional Formatting (Γκρι Σύνολα, Λαχανί μόνο οι ημέρες >= 8h)
    def highlight_cells(row):
        styles = [''] * len(row)
        is_total_row = row[sel_group[0]] == 'Σύνολο'
        
        for i, col in enumerate(row.index):
            val = row[col]
            cell_style = ''
            
            # --- Α. ΣΥΝΟΛΑ (Γραμμές & Στήλες) ---
            if is_total_row or col == 'Σύνολο':
                # Ένα σταθερό, επαγγελματικό γκρι για τα σύνολα
                cell_style = 'font-weight: bold; background-color: #E2E8F0; color: #1E293B;' 
            
            # --- Β. ΣΤΗΛΕΣ ΟΜΑΔΟΠΟΙΗΣΗΣ (Assignee, Project κλπ) ---
            elif col in sel_group:
                # Ένα πολύ αχνό γκρι για να ξεχωρίζουν ελαφρώς από τα δεδομένα
                cell_style = 'background-color: #F8FAFC; font-weight: 500;'
                
            # --- Γ. ΗΜΕΡΕΣ (Κανονικά Κελιά Δεδομένων) ---
            else:
                # Ελέγχουμε αν είναι ώρα (έχει το ':') και αν ξεπερνάει τις 8 ώρες
                if isinstance(val, str) and ':' in val:
                    try:
                        hours, minutes = map(int, val.split(':'))
                        if hours >= 8:
                            # Λαχανί φόντο και πράσινα γράμματα ΜΟΝΟ για τις ημέρες στόχου
                            cell_style = 'font-weight: bold; color: #0B8043; background-color: #E8F5E9;'
                    except ValueError:
                        pass
            
            styles[i] = cell_style
        return styles

    styled_pivot = pivot_fmt.style.apply(highlight_cells, axis=1)

    total_cells = pivot_fmt.size 
    max_allowed_cells = 200000 

    if total_cells > max_allowed_cells:
        st.warning("⚠️ **Πάρα πολλά δεδομένα για προβολή!**\n\nΟ πίνακας περιέχει πάνω από τον επιτρεπτό αριθμό εγγραφών, κάτι που μπορεί να καθυστερήσει την εφαρμογή. Παρακαλώ χρησιμοποιήστε τα **Φίλτρα** (π.χ. επιλέξτε συγκεκριμένα Projects, Assignees ή ένα μικρότερο εύρος Ημερομηνιών) για να δείτε τα αποτελέσματα.")
    else:
        # Αν τα κελιά είναι σε φυσιολογικά πλαίσια, εμφανίζουμε κανονικά τον πίνακα
        st.dataframe(
            styled_pivot,
            width='stretch',
            height=500, 
            column_config=col_config,
            hide_index=True
        )
    
    # st.dataframe(
    #     styled_pivot, 
    #     width='stretch', 
    #     height=500, 
    #     column_config=col_config, 
    #     hide_index=True
    # )
    
    # 2. Τοποθέτηση του Download Button στα Δεξιά
    def convert_df_to_excel(df_styled):
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df_styled.to_excel(writer, sheet_name='Timesheet', index=False)
        return output.getvalue()

    col_empty, col_btn = st.columns([5, 1]) # Το 5:1 "σπρώχνει" το κουμπί δεξιά
    with col_btn:
        st.download_button(
            label="📥 Λήψη σε Excel",
            data=convert_df_to_excel(styled_pivot),
            file_name=f"NSS_Timesheet_{start}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
            use_container_width=True # Το αναγκάζει να γεμίσει τη δεξιά στήλη
        )
else:
    st.info("Δεν υπάρχουν δεδομένα για τα επιλεγμένα φίλτρα.")

# --- Ενότητα Γ: Γραφήματα ---
st.write("---")
st.subheader("📈 Γραφήματα Ανάλυσης", divider="gray")

# --- 1. Γραφήματα Πίτας (Side-by-Side) ---
c1, c2 = st.columns(2)

with c1:
    chart_time = filtered_df.groupby("Time Type")["Minutes"].sum().reset_index()
    fig_time = px.pie(chart_time, 
                      values="Minutes", 
                      names="Time Type", 
                      hole=0.4, 
                      title="⏳ Αναλογία ανά Time Type",
                      color_discrete_sequence=px.colors.sequential.Oranges_r)
    fig_time.update_traces(textposition='inside', textinfo='percent+label')
    fig_time.update_layout(height=400, showlegend=False) # Κρύβουμε το legend για εξοικονόμηση χώρου
    st.plotly_chart(fig_time, use_container_width=True)

with c2:
    chart_charge = filtered_df.groupby("Charge Type")["Minutes"].sum().reset_index()
    fig_charge = px.pie(chart_charge, 
                        values="Minutes", 
                        names="Charge Type", 
                        hole=0.4, 
                        title="💰 Αναλογία ανά Charge Type",
                        color_discrete_sequence=px.colors.sequential.Greens_r) # Πράσινο theme
    fig_charge.update_traces(textposition='inside', textinfo='percent+label')
    fig_charge.update_layout(height=400, showlegend=False)
    st.plotly_chart(fig_charge, use_container_width=True)

# --- 2. Γράφημα Κατηγοριών (Full Width - Οριζόντιες Μπάρες) ---
st.write("<br>", unsafe_allow_html=True) 

# Η στήλη 'Parent Category' έρχεται πλέον ΕΤΟΙΜΗ από τη βάση δεδομένων!
# Οπότε κάνουμε απλά ένα groupby, όπως ακριβώς κάνουμε και στα Time Types.
chart_parent = filtered_df.groupby("Parent Category")["Minutes"].sum().reset_index().sort_values("Minutes")

fig_comp = px.bar(chart_parent, 
                  x="Minutes", 
                  y="Parent Category", 
                  orientation='h', 
                  title="⏱️ Time Distribution per Main Category", 
                  color_discrete_sequence=['#0078D4'],
                  labels={"Parent Category": "Κατηγορία", "Minutes": "Λεπτά"}
                 )

fig_comp.update_layout(height=800) 
st.plotly_chart(fig_comp, use_container_width=True)