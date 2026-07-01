import streamlit as st
import time

# Εισαγωγή των συναρτήσεων
from modules.test_projects_etl import run_real_projects_etl, run_jira_projects_etl
from modules.test_users_etl import run_users_etl, run_jira_users_etl
from modules.test_components_etl import run_components_etl, run_jira_components_etl
from modules.test_issues_etl import run_incremental_issues_and_children_etl, run_incremental_jira_etl

st.set_page_config(page_title="Data Warehouse ETL Manager", page_icon="⚙️", layout="wide")

st.title("🚀 Data Warehouse ETL Manager")
st.markdown("Διαχειριστικό περιβάλλον για τον συγχρονισμό δεδομένων από Gemini και Jira στο SQL Server.")

# Δημιουργία Tabs (Καρτέλες)
tab1, tab2, tab3 = st.tabs(["⚡ Μεμονωμένες Ενέργειες", "📦 Μαζικός Συγχρονισμός", "🔄 Gemini ➔ Jira Migration"])

with tab1:
    st.subheader("Συγχρονισμός ανά Οντότητα (Dimensions & Facts)")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        if st.button("🏢 Sync Projects", use_container_width=True):
            with st.spinner("Συγχρονισμός Projects σε εξέλιξη..."):
                run_real_projects_etl()
                run_jira_projects_etl()
            st.success("Τα Projects συγχρονίστηκαν επιτυχώς!")

    with col2:
        if st.button("👥 Sync Users", use_container_width=True):
            with st.spinner("Συγχρονισμός Users σε εξέλιξη..."):
                run_users_etl()
                run_jira_users_etl()
            st.success("Οι Users συγχρονίστηκαν επιτυχώς!")

    with col3:
        if st.button("🧩 Sync Components", use_container_width=True):
            with st.spinner("Συγχρονισμός Components σε εξέλιξη..."):
                run_components_etl()
                run_jira_components_etl()
            st.success("Τα Components συγχρονίστηκαν επιτυχώς!")

    with col4:
        if st.button("🎫 Sync Issues (Incremental)", use_container_width=True, type="primary"):
            with st.spinner("Incremental Sync (Issues, Comments, Worklogs) σε εξέλιξη..."):
                run_incremental_issues_and_children_etl()
                run_incremental_jira_etl()
            st.success("Το Incremental Sync ολοκληρώθηκε!")

with tab2:
    st.subheader("Πλήρης Συγχρονισμός (Full Pipeline)")
    st.info("Εκτελείται με την ασφαλή σειρά: Projects ➔ Users ➔ Components ➔ Issues")
    
    if st.button("🚀 ΕΚΚΙΝΗΣΗ FULL SYNC", type="primary"):
        start_time = time.time()
        
        with st.status("Εκτέλεση Full Sync Pipeline...", expanded=True) as status:
            st.write("Συγχρονισμός Projects...")
            run_real_projects_etl()
            run_jira_projects_etl()
            
            st.write("Συγχρονισμός Users...")
            run_users_etl()
            run_jira_users_etl()
            
            st.write("Συγχρονισμός Components...")
            run_components_etl()
            run_jira_components_etl()
            
            st.write("Συγχρονισμός Issues...")
            run_incremental_issues_and_children_etl()
            run_incremental_jira_etl()
            
            status.update(label="Το Full Sync Ολοκληρώθηκε!", state="complete", expanded=False)
            
        end_time = time.time()
        mins, secs = divmod(int(end_time - start_time), 60)
        st.success(f"🎉 Όλα τα δεδομένα συγχρονίστηκαν επιτυχώς σε {mins} λεπτά και {secs} δευτερόλεπτα!")

with tab3:
    from src.etl.migrator import render_migration_tab
    render_migration_tab()