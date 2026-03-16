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
except KeyError:
    st.error("❌ Δεν βρέθηκαν τα απαραίτητα Secrets (EMAIL/TOKEN). Ελέγξτε το αρχείο .streamlit/secrets.toml")
    st.stop()

BASE_URL = f"https://{JIRA_DOMAIN}/rest/api/3/search/jql"

# --- 2. Συναρτήσεις Διαμόρφωσης & Ασφάλειας ---
def safe_get(data, key, subkey="value", default="N/A"):
    """Αποφεύγει το AttributeError αν το πεδίο είναι None"""
    item = data.get(key)
    if item is None:
        return default
    return item.get(subkey, default)

def format_to_hhmm(minutes):
    """Μετατρέπει λεπτά σε ΩΩ:ΛΛ"""
    if pd.isna(minutes) or minutes <= 0: return "00:00"
    hours = int(minutes // 60)
    mins = int(minutes % 60)
    return f"{hours:02d}:{mins:02d}"

@st.cache_data(ttl=600)
def get_jira_data():
    # 1. Αποθηκεύουμε την ακριβή ώρα που ξεκινάει το "τράβηγμα"
    fetch_time = datetime.now().strftime("%d/%m/%Y %H:%M")
    all_issues = []
    page_token = ""
    jql = 'project IN (PYLCOM, PYLFLE, GLXENT, ESLKAS, PYLACC, PYLHOS) AND issuetype = "Time Type" AND status = "Time Entered" ORDER BY created DESC'
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
                "Author": wl["author"]["displayName"],
                "Time Type": time_type,
                "Charge Type": charge_type,
                "Minutes": wl["timeSpentSeconds"] / 60,
                "Date": wl["started"][:10],
                "Components": components
            })
    return pd.DataFrame(rows), fetch_time

# --- 3. Φόρτωση Δεδομένων ---
# Πιάνουμε και το df και το last_updated
df, last_updated = get_jira_data()

if df.empty:
    st.warning("Δεν βρέθηκαν δεδομένα.")
    st.stop()

# --- 4. SIDEBAR (Φίλτρα & Bookmarks) ---
st.sidebar.title("🎛️ Φίλτρα Αναζήτησης")
st.sidebar.markdown("---")

# Ανάγνωση αποθηκευμένων φίλτρων από το URL (αν υπάρχουν)
url_params = st.query_params

def_proj = url_params.get_all("project") or df["Project"].unique().tolist()
def_auth = url_params.get_all("author") or df["Author"].unique().tolist()
def_charge = url_params.get_all("charge") or df["Charge Type"].unique().tolist()
def_time = url_params.get_all("time") or df["Time Type"].unique().tolist()

# Ειδική διαχείριση για τις ημερομηνίες (μετατροπή string σε date)
raw_dates = url_params.get_all("dateRange")
if raw_dates:
    # Αν υπάρχουν στο URL, τα κάνουμε parse
    def_range = [pd.to_datetime(d).date() for d in raw_dates]
else:
    # Αλλιώς παίρνουμε το min/max από το dataframe
    def_range = [pd.to_datetime(df['Date']).min(), pd.to_datetime(df['Date']).max()]

# --- Δημιουργία των Widgets & Ταυτόχρονη Αποθήκευση στο URL ---

# Προσοχή: στο date_input χρησιμοποιούμε το 'value=' αντί για 'default='
date_range = st.sidebar.date_input("📅 Ημερομηνίες", value=def_range)
# Το γράφουμε πίσω στο URL ως string
st.query_params["dateRange"] = [str(d) for d in date_range] 

sel_proj = st.sidebar.multiselect("📁 Project", options=sorted(df["Project"].unique()), default=def_proj)
st.query_params["project"] = sel_proj

sel_auth = st.sidebar.multiselect("👤 Author", options=sorted(df["Author"].unique()), default=def_auth)
st.query_params["author"] = sel_auth

sel_charge = st.sidebar.multiselect("💰 Charge Type", options=sorted(df["Charge Type"].unique()), default=def_charge)
st.query_params["charge"] = sel_charge

sel_time = st.sidebar.multiselect("⏱️ Time Type", options=sorted(df["Time Type"].unique()), default=def_time)
st.query_params["time"] = sel_time

st.sidebar.markdown("---")
st.sidebar.subheader("🗂️ Προβολή Δεδομένων")

# Επιλογές για το τι μπορεί να γίνει Group By
group_options = ["Author", "Parent Key", "Project", "Time Type", "Charge Type"]
def_group = url_params.get_all("groupBy") or ["Author", "Parent Key"]

sel_group = st.sidebar.multiselect("Ομαδοποίηση (Group By) ανά:", options=group_options, default=def_group)
st.query_params["groupBy"] = sel_group # Αποθήκευση της επιλογής στο URL

if not sel_group:
    st.sidebar.error("Επιλέξτε τουλάχιστον ένα πεδίο ομαδοποίησης.")
    st.stop()

# --- Φιλτράρισμα Δεδομένων ---
start = date_range[0].strftime('%Y-%m-%d')
end = date_range[1].strftime('%Y-%m-%d') if len(date_range) > 1 else start

mask = (df["Date"] >= start) & (df["Date"] <= end) & \
       df["Project"].isin(sel_proj) & df["Author"].isin(sel_auth) & \
       df["Charge Type"].isin(sel_charge) & df["Time Type"].isin(sel_time)

filtered_df = df[mask]

# --- 5. ΚΕΝΤΡΙΚΗ ΟΘΟΝΗ (Main Layout) ---
# Χωρίζουμε την κορυφή σε 2 στήλες: μία μεγάλη για τον τίτλο, μία μικρή δεξιά για την ώρα
col_title, col_time = st.columns([3, 1])

with col_title:
    st.title("📊 NSS Support Dashboard")
    
with col_time:
    # Προσθέτουμε λίγο κενό για να ευθυγραμμιστεί κάθετα με τον τίτλο
    st.write("") 
    st.write("")
    # Εμφανίζουμε την ώρα με διακριτικό (caption) κείμενο
    st.caption(f"🔄 **Τελευταία Ενημέρωση:** {last_updated}")

# Ενότητα Α: KPI Metrics
st.subheader("📌 Σύνοψη", divider="blue")
m1, m2, m3, m4 = st.columns(4)
total_mins = filtered_df["Minutes"].sum()
m1.metric("Συνολικός Χρόνος", format_to_hhmm(total_mins))
m2.metric("Ενεργά Projects", filtered_df["Project"].nunique())
m3.metric("Σύμβουλοι (Authors)", filtered_df["Author"].nunique())
m4.metric("Μοναδικά Tickets", filtered_df["Issue Key"].nunique())

# Ενότητα Β: Γραφήματα
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

# --- Ενότητα Γ: Pivot Table & Export ---
st.subheader("📅 Αναλυτικό Timesheet", divider="gray")

if not filtered_df.empty:
    # 1. Δημιουργία Pivot με βάση τις επιλογές του χρήστη (sel_group)
    pivot = filtered_df.pivot_table(
        index=sel_group, 
        columns="Date",
        values="Minutes",
        aggfunc="sum",
        fill_value=0,
        margins=True,          
        margins_name="Σύνολο"  
    )
    
    # 2. Μορφοποίηση σε HH:MM (πριν το reset_index για να πιάσει μόνο τους χρόνους)
    # Αν χρησιμοποιείς Pandas < 2.1 βάλε applymap. Αν >= 2.1 βάλε map
    pivot_fmt = pivot.map(format_to_hhmm)
    
    # 3. Επαναφορά του Index για να γίνουν τα Groups κανονικές στήλες
    pivot_fmt = pivot_fmt.reset_index()
    
    # 4. Προσθήκη Clickable Link (Μόνο αν ο χρήστης έχει επιλέξει το 'Parent Key')
    col_config = {}
    if "Parent Key" in sel_group:
        jira_base = f"https://{JIRA_DOMAIN}/browse/"
        # Δημιουργία του URL (εξαιρούμε τη γραμμή "Σύνολο")
        pivot_fmt["🔗 Link"] = pivot_fmt["Parent Key"].apply(
            lambda x: f"{jira_base}{x}" if x and x != "Σύνολο" else None
        )
        
        # Φέρνουμε τη στήλη Link δίπλα στο Parent Key
        cols = list(pivot_fmt.columns)
        cols.remove("🔗 Link")
        pk_index = cols.index("Parent Key")
        cols.insert(pk_index + 1, "🔗 Link")
        pivot_fmt = pivot_fmt[cols]
        
        # Ρύθμιση του Streamlit για να το εμφανίσει ως όμορφο link και όχι σαν ωμό κείμενο
        col_config["🔗 Link"] = st.column_config.LinkColumn("Άνοιγμα", display_text="Issue URL")

    # 5. Το νέο, πιο πλούσιο Conditional Formatting (με έλεγχο 8ώρου)
    def highlight_cells(row):
        styles = [''] * len(row)
        # Βρίσκουμε αν είναι η γραμμή του Γενικού Συνόλου
        is_total_row = row[sel_group[0]] == 'Σύνολο'
        
        for i, col in enumerate(row.index):
            val = row[col]
            cell_style = ''
            
            # --- Α. Βασικά Χρώματα Ομαδοποίησης & Συνόλων ---
            if is_total_row or col == 'Σύνολο':
                cell_style = 'font-weight: bold; color: #E65100; background-color: #FFEBCC;' # Πορτοκαλί default
            elif col in sel_group:
                cell_style = 'background-color: #F0F2F6; font-weight: 500;' # Γκρι για τα groups
                
            # --- Β. Έλεγχος Επίτευξης 8ώρου (>= 08:00) ---
            # Ελέγχουμε αν η τιμή είναι κείμενο που περιέχει ':' (δηλαδή είναι ώρα)
            if isinstance(val, str) and ':' in val:
                try:
                    hours, minutes = map(int, val.split(':'))
                    if hours >= 8:
                        # Αν είναι ήδη πορτοκαλί (Σύνολο), το κάνουμε πράσινο
                        if 'color: #E65100;' in cell_style:
                            cell_style = cell_style.replace('color: #E65100;', 'color: #0B8043;')
                        # Αλλιώς, αν είναι απλό κελί, του δίνουμε πράσινο χρώμα και έντονη γραφή
                        else:
                            cell_style += 'color: #0B8043; font-weight: bold;'
                except ValueError:
                    pass # Αν γίνει κάποιο λάθος στη μετατροπή, το αγνοούμε
            
            styles[i] = cell_style
        return styles

    styled_pivot = pivot_fmt.style.apply(highlight_cells, axis=1)
    
    # 6. Εμφάνιση πίνακα (κρύβουμε το default αριθμητικό index αριστερά)
    st.dataframe(
        styled_pivot, 
        width='stretch', 
        height=500, 
        column_config=col_config, 
        hide_index=True
    )
    
    # --- Export to Excel ---
    def convert_df_to_excel(df_styled):
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df_styled.to_excel(writer, sheet_name='Timesheet', index=False)
        return output.getvalue()

    st.download_button(
        label="📥 Λήψη Timesheet σε Excel",
        data=convert_df_to_excel(styled_pivot),
        file_name=f"NSS_Timesheet_{start}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary"
    )
else:
    st.info("Δεν υπάρχουν δεδομένα για τα επιλεγμένα φίλτρα.")