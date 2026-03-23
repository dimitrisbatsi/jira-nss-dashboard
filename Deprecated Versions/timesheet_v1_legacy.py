import streamlit as st
import pandas as pd
import requests
import plotly.express as px
import io
from datetime import datetime

# --- 1. Ρυθμίσεις Σελίδας & Σύνδεσης ---
st.set_page_config(layout="wide", page_title="NSS Timesheet Dashboard", page_icon="📊")

# ΣΤΟΙΧΕΙΑ ΣΥΝΔΕΣΗΣ
JIRA_DOMAIN = "epsilon-singularlogic.atlassian.net"

try:
    EMAIL = st.secrets["JIRA_EMAIL"]
    API_TOKEN = st.secrets["JIRA_TOKEN"]
    # JWT_TOKEN = st.secrets["JIRA_JWT_TOKEN"]
except KeyError:
    st.error("❌ Δεν βρέθηκαν τα απαραίτητα Secrets (EMAIL/TOKEN ή JWT). Ελέγξτε το αρχείο .streamlit/secrets.toml")
    st.stop()

BASE_URL = f"https://{JIRA_DOMAIN}/rest/api/3/search/jql"

# --- 2. Συναρτήσεις Διαμόρφωσης & Ασφάλειας ---
def safe_get(data, key, subkey="value", default="N/A"):
    item = data.get(key)
    if item is None:
        return default
    return item.get(subkey, default)

def format_to_hhmm(minutes):
    if pd.isna(minutes) or minutes <= 0: return "00:00"
    hours = int(minutes // 60)
    mins = int(minutes % 60)
    return f"{hours:02d}:{mins:02d}"

@st.cache_data(ttl=600)
def get_jira_data():
    fetch_time = datetime.now().strftime("%d/%m/%Y %H:%M")
    all_issues = []
    page_token = ""
    jql = 'project IN (PYLCOM, PYLFLE, GLXENT, ESLKAS, PYLACC, PYLHOS, ESLLEG) AND issuetype = "Time Type" AND status = "Time Entered" ORDER BY created DESC'
    fields = "worklog,assignee,summary,project,components,customfield_10553,customfield_10193,parent"

    while True:
        params = {"jql": jql, "fields": fields, "maxResults": 100, "nextPageToken": page_token}
        response = requests.get(BASE_URL, params=params, auth=(EMAIL, API_TOKEN)).json()
        
        batch = response.get("issues", [])
        if not batch: break
        all_issues.extend(batch)
        page_token = response.get("nextPageToken")
        if not page_token or response.get("isLast"): break

    rows = []
    for issue in all_issues:
        f = issue.get("fields", {})
        project = f.get("project", {}).get("name", "N/A")
        
        time_type = safe_get(f, "customfield_10553")
        charge_type = safe_get(f, "customfield_10193")
        parent_key = f.get("parent", {}).get("key", "N/A")
        components = [c["name"] for c in f.get("components", [])] if f.get("components") else ["No Component"]
        
        worklogs = f.get("worklog", {}).get("worklogs", [])
        for wl in worklogs:
            rows.append({
                "Issue Key": issue["key"],
                "Parent Key": parent_key,
                "Project": project,
                "Assignee": wl.get("author", {}).get("displayName", "Unknown"),
                "Time Type": time_type,
                "Charge Type": charge_type,
                "Minutes": wl["timeSpentSeconds"] / 60,
                "Date": wl["started"][:10],
                "Components": components
            })
    return pd.DataFrame(rows), fetch_time

# --- 3. Φόρτωση Δεδομένων ---
df, last_updated = get_jira_data()

if df.empty:
    st.warning("Δεν βρέθηκαν δεδομένα.")
    st.stop()

# --- 4. SIDEBAR (Μόνο Φίλτρα Αναζήτησης) ---
st.sidebar.title("🎛️ Φίλτρα Αναζήτησης")

# --- ΝΕΟ: Κουμπί Reset Filters (Τώρα καθαρίζει ΚΑΙ τη μνήμη) ---
if st.sidebar.button("🔄 Καθαρισμός Φίλτρων", type="primary", use_container_width=True):
    st.query_params.clear()
    st.session_state.clear() # <--- ΠΟΛΥ ΣΗΜΑΝΤΙΚΟ
    st.rerun()

# 1. Διαβάζουμε το URL ΜΟΝΟ την πρώτη φορά (Initialization)
if "filters_initialized" not in st.session_state:
    url_params = st.query_params
    
    st.session_state['proj'] = url_params.get_all("project") or df["Project"].unique().tolist()
    st.session_state['auth'] = url_params.get_all("Assignee") or df["Assignee"].unique().tolist()
    st.session_state['charge'] = url_params.get_all("charge") or df["Charge Type"].unique().tolist()
    st.session_state['time'] = url_params.get_all("time") or df["Time Type"].unique().tolist()
    
    raw_dates = url_params.get_all("dateRange")
    if raw_dates:
        st.session_state['dates'] = [pd.to_datetime(d).date() for d in raw_dates]
    else:
        st.session_state['dates'] = [pd.to_datetime(df['Date']).min(), pd.to_datetime(df['Date']).max()]
        
    st.session_state["filters_initialized"] = True

# 2. Σχεδιάζουμε τα widgets δίνοντας ως default τη μνήμη (session_state)
date_range = st.sidebar.date_input("📅 Ημερομηνίες", value=st.session_state['dates'])
sel_proj = st.sidebar.multiselect("📁 Project", options=sorted(df["Project"].unique()), default=st.session_state['proj'])
sel_auth = st.sidebar.multiselect("👤 Assignee", options=sorted(df["Assignee"].unique()), default=st.session_state['auth'])
sel_charge = st.sidebar.multiselect("💰 Charge Type", options=sorted(df["Charge Type"].unique()), default=st.session_state['charge'])
sel_time = st.sidebar.multiselect("⏱️ Time Type", options=sorted(df["Time Type"].unique()), default=st.session_state['time'])

# 3. Αποθηκεύουμε τις νέες επιλογές πίσω στη Μνήμη & στο URL
st.session_state['dates'] = date_range
st.session_state['proj'] = sel_proj
st.session_state['auth'] = sel_auth
st.session_state['charge'] = sel_charge
st.session_state['time'] = sel_time

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

# Εφαρμόζουμε την ίδια λογική (Session State) ΚΑΙ στο Group By
group_options = ["Assignee", "Parent Key", "Issue Key", "Project", "Time Type", "Charge Type"]

if "group_initialized" not in st.session_state:
    url_group = st.query_params.get_all("groupBy")
    valid_group = [g for g in url_group if g in group_options]
    st.session_state['group_by'] = valid_group if valid_group else ["Assignee", "Parent Key"]

sel_group = st.multiselect("🗂️ Ομαδοποίηση (Group By) ανά:", options=group_options, default=st.session_state['group_by'])

# Αποθήκευση σε Μνήμη & URL
st.session_state['group_by'] = sel_group
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
    
    st.dataframe(
        styled_pivot, 
        width='stretch', 
        height=500, 
        column_config=col_config, 
        hide_index=True
    )
    
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

# Ενότητα Γ: Γραφήματα
st.write("---")
st.subheader("📈 Γραφήματα Ανάλυσης", divider="gray")
c1, c2 = st.columns(2)

with c1:
    comp_df = filtered_df.explode("Components")
    chart_comp = comp_df.groupby("Components")["Minutes"].sum().reset_index().sort_values("Minutes")
    fig_comp = px.bar(chart_comp, x="Minutes", y="Components", orientation='h', 
                      title="Time Distribution per Component", color_discrete_sequence=['#0078D4'])
    st.plotly_chart(fig_comp, width='stretch')

with c2:
    chart_time = filtered_df.groupby("Time Type")["Minutes"].sum().reset_index().sort_values("Minutes")
    fig_time = px.bar(chart_time, x="Minutes", y="Time Type", orientation='h', 
                      title="Minutes per Time Type", color_discrete_sequence=['#D83B01'])
    st.plotly_chart(fig_time, width='stretch')