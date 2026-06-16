import streamlit as st
import pandas as pd
import requests
import plotly.express as px
import io
import os
import re
from datetime import datetime

APP_VERSION = "26.3.0 (2026-06-16)"

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

# --- 2. Φόρτωση από Βάση Δεδομένων (SQL Server) ---
@st.cache_data(ttl=60) # Cache για 1 λεπτό
def load_data_from_db():
    try:
        # Έλεγχος αν υπάρχει το CONNECTION_STRING στα secrets
        if "CONNECTION_STRING" not in st.secrets:
            st.error("❌ Το CONNECTION_STRING λείπει από τα secrets.toml!")
            return pd.DataFrame(), "Ποτέ"
            
        conn_str = st.secrets["CONNECTION_STRING"]
        
        # Ανάλυση connection string
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
            st.error("❌ Τα πεδία Server και Database είναι υποχρεωτικά στο connection string!")
            return pd.DataFrame(), "Ποτέ"
            
        import urllib.parse
        from sqlalchemy import create_engine
        
        drivers = ["ODBC Driver 17 for SQL Server", "SQL Server Native Client 11.0", "SQL Server"]
        engine = None
        last_error = None
        
        for driver in drivers:
            try:
                pyodbc_conn_str = f"DRIVER={{{driver}}};SERVER={server};DATABASE={database};"
                if uid and pwd:
                    pyodbc_conn_str += f"UID={uid};PWD={pwd};"
                else:
                    pyodbc_conn_str += "Trusted_Connection=yes;"
                    
                params = urllib.parse.quote_plus(pyodbc_conn_str)
                temp_engine = create_engine(f"mssql+pyodbc:///?odbc_connect={params}")
                
                # Δοκιμή σύνδεσης
                with temp_engine.connect() as conn:
                    pass
                engine = temp_engine
                break
            except Exception as ex:
                last_error = ex
                
        if engine is None:
            st.error(f"❌ Αποτυχία σύνδεσης στον SQL Server. Τελευταίο σφάλμα: {last_error}")
            return pd.DataFrame(), "Ποτέ"
            
        # Φόρτωση από τον SQL Server
        df = pd.read_sql("SELECT * FROM WorkLogs", engine)
        
        # Μετονομασία στηλών πίσω στη μορφή με κενά που περιμένει το UI
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
            
        last_updated = datetime.now().strftime("%d/%m/%Y %H:%M")
        return df, last_updated
        
    except Exception as e:
        st.error(f"❌ Σφάλμα κατά τη φόρτωση των δεδομένων: {e}")
        return pd.DataFrame(), "Ποτέ"

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
    # ΝΕΑ ΠΕΔΙΑ:
    all_partner = sorted([str(x) for x in df["Partner Name"].dropna().unique()]) if "Partner Name" in df.columns else []
    all_lsp = sorted([str(x) for x in df["LSP Customer Name"].dropna().unique()]) if "LSP Customer Name" in df.columns else []

    if "Parent Category" in df.columns:
        nested_comps = df["Parent Category"].dropna().apply(lambda x: [c.strip() for c in x.split(",")])
        all_comps_flat = set([item for sublist in nested_comps for item in sublist])
        all_comp = sorted(list(all_comps_flat))
    else:
        all_comp = []

    
    # Αποθηκεύουμε τα defaults στα keys. 
    st.session_state['proj_key'] = sorted(url_params.get_all("project")) if url_params.get_all("project") else all_proj
    st.session_state['auth_key'] = sorted(url_params.get_all("Assignee")) if url_params.get_all("Assignee") else all_auth
    st.session_state['charge_key'] = sorted(url_params.get_all("charge")) if url_params.get_all("charge") else all_charge
    st.session_state['time_key'] = sorted(url_params.get_all("time")) if url_params.get_all("time") else all_time
    # ΝΕΑ ΠΕΔΙΑ:
    st.session_state['partner_key'] = sorted(url_params.get_all("partner")) if url_params.get_all("partner") else all_partner
    st.session_state['lsp_key'] = sorted(url_params.get_all("lsp")) if url_params.get_all("lsp") else all_lsp
        
    st.session_state['comp_key'] = sorted(url_params.get_all("category")) if url_params.get_all("category") else all_comp
    
    raw_dates = url_params.get_all("dateRange")
    if raw_dates:
        st.session_state['dates_key'] = [pd.to_datetime(d).date() for d in raw_dates]
    else:
        st.session_state['dates_key'] = [pd.to_datetime(df['Date']).min(), pd.to_datetime(df['Date']).max()]
        
    # Προσθέσαμε τα νέα πεδία στις επιλογές ομαδοποίησης!
    group_options = ["Assignee", "Parent Key", "Issue Key", "Project", "Time Type", "Charge Type", "Partner Name", "LSP Customer Name"]
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

# ΝΕΑ WIDGETS:
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

st.sidebar.write("")
st.sidebar.caption(f"**App Version:** {APP_VERSION}")

# 3. ΕΝΗΜΕΡΩΣΗ URL: Γράφουμε τις επιλογές στο URL για να μπορείς να τις κάνεις Share
st.query_params["dateRange"] = [str(d) for d in date_range] 
st.query_params["project"] = sel_proj
st.query_params["Assignee"] = sel_auth
st.query_params["charge"] = sel_charge
st.query_params["time"] = sel_time
# st.query_params["partner"] = sel_partner
# st.query_params["lsp"] = sel_lsp
# st.query_params["category"] = sel_comp

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
# Φτιάχνει ένα pattern τύπου: "Frontend|Backend" (Δηλαδή ψάχνει είτε το ένα είτε το άλλο)
    pattern = '|'.join([re.escape(c) for c in sel_comp])
    mask = mask & df["Parent Category"].str.contains(pattern, case=False, na=False)

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

# 1. Προσθέτουμε το Parent Title στις επιλογές (αν θέλει ο χρήστης να το επιλέξει μόνο του)
group_options = ["Assignee", "Parent Key", "Parent Title", "Issue Key", "Project", "Time Type", "Charge Type", "Partner Name", "LSP Customer Name"]
sel_group = st.multiselect("🗂️ Ομαδοποίηση (Group By) ανά:", options=group_options, key="group_key")
st.query_params["groupBy"] = sel_group

if not sel_group:
    st.error("Επιλέξτε τουλάχιστον ένα πεδίο ομαδοποίησης.")
    st.stop()

if not filtered_df.empty:
    # ΑΥΤΟΜΑΤΙΣΜΟΣ: Αν επιλεγεί το Parent Key, προσθέτουμε το Parent Title στην ομαδοποίηση 
    # αν δεν το έχει επιλέξει ήδη ο χρήστης, για να έχουμε την πληροφορία διαθέσιμη.
    pivot_groups = sel_group.copy()
    if "Parent Key" in sel_group and "Parent Title" in filtered_df.columns and "Parent Title" not in sel_group:
        pivot_groups.append("Parent Title")

    pivot = filtered_df.pivot_table(
        index=pivot_groups, # Χρησιμοποιούμε τη διευρυμένη λίστα
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
        
        # Αν υπάρχει το Parent Title, το μεταφέρουμε δίπλα στο Parent Key
        if "Parent Title" in pivot_fmt.columns:
            cols = list(pivot_fmt.columns)
            cols.remove("Parent Title")
            pk_idx = cols.index("Parent Key")
            cols.insert(pk_idx + 1, "Parent Title") # Το βάζουμε αμέσως μετά το Key
            pivot_fmt = pivot_fmt[cols]
            # Μπορούμε να ορίσουμε και πλάτος για να μην πιάνει πολύ χώρο αν είναι μεγάλο το title
            col_config["Parent Title"] = st.column_config.TextColumn("Τίτλος Parent", width="medium")

        # Δημιουργία Link για το Parent
        # Χρησιμοποιούμε ένα μοναδικό όνομα για το link αν υπάρχει ήδη το Issue Link
        link_col_name = "🔗 Parent Link" 
        pivot_fmt[link_col_name] = pivot_fmt["Parent Key"].apply(
            lambda x: f"{jira_base}{x}" if x and x != "Σύνολο" and x != "N/A" else None
        )
        
        cols = list(pivot_fmt.columns)
        cols.remove(link_col_name)
        # Τοποθέτηση του Link μετά το Title (ή μετά το Key αν δεν υπάρχει Title)
        ref_col = "Parent Title" if "Parent Title" in pivot_fmt.columns else "Parent Key"
        target_idx = cols.index(ref_col)
        cols.insert(target_idx + 1, link_col_name)
        pivot_fmt = pivot_fmt[cols]
        
        col_config[link_col_name] = st.column_config.LinkColumn("Parent", display_text="Open")

    def highlight_cells(row):
        styles = [''] * len(row)
        # Προσοχή: Το sel_group[0] παραμένει το κριτήριο για τη γραμμή "Σύνολο"
        is_total_row = row[sel_group[0]] == 'Σύνολο'
        for i, col in enumerate(row.index):
            val = row[col]
            cell_style = ''
            if is_total_row or col == 'Σύνολο':
                cell_style = 'font-weight: bold; background-color: #E2E8F0; color: #1E293B;' 
            # Χρωματίζουμε ως headers όλες τις στήλες που ανήκουν στην ομαδοποίηση (συμπεριλαμβανομένου του Title)
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
            height=600, # Αυξάνω λίγο το ύψος καθώς οι γραμμές μπορεί να μεγαλώσουν λόγω τίτλων
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