import re

with open('src/etl/migrator.py', 'rb') as f:
    content = f.read()

# Find the start of render_migration_tab()
idx = content.find(b'def render_migration_tab():')
if idx == -1:
    raise Exception("Could not find start of render_migration_tab()")

base_content = content[:idx]

new_func = """def render_migration_tab():
    import streamlit as st
    import pandas as pd
    from src.api.gemini_client import GeminiAPIClient, GeminiSearchCriteria
    from src.api.jira_client import JiraAPIClient
    from src.etl.migrator import process_migration, GeminiLookupCache
    from datetime import datetime, time as dt_time
    from dateutil.relativedelta import relativedelta
    
    st.subheader("🔄 Countersoft Gemini ➔ Jira Migration Tool")
    st.markdown("Μεταφορά θεμάτων από το Gemini στο Jira Cloud (`PYLMIG`) με βάση τις καθορισμένες στρατηγικές και mappings.")
    
    # Recreate clients on every render to prevent Streamlit hot-reload cache issue
    st.session_state.gemini_client = GeminiAPIClient()
    st.session_state.jira_client = JiraAPIClient()
    if "lookup_cache" not in st.session_state or not hasattr(st.session_state.lookup_cache, "user_id_to_email"):
        with st.spinner("Φόρτωση custom field definitions από το Gemini..."):
            cache = GeminiLookupCache(st.session_state.gemini_client)
            cache.preload()
            st.session_state.lookup_cache = cache
        
    gemini_client = st.session_state.gemini_client
    jira_client = st.session_state.jira_client
    lookup_cache = st.session_state.lookup_cache
    
    # Left and Right layouts
    col_filters, col_actions = st.columns([1, 1])
    
    with col_filters:
        st.markdown("### 🔍 Φίλτρα & Παράμετροι")
        
        migration_mode = st.radio("Τρόπος Μεταφοράς:", ["Μεμονωμένο Issue ID (Single)", "Μαζική Μεταφορά βάσει Φίλτρων (Batch)"])
        
        single_id = ""
        selected_project_id = None
        batch_project = "SRV"
        batch_search = ""
        start_date = None
        end_date = None
        
        # Advanced filters variables init
        filter_statuses = ""
        filter_statuses_not = False
        filter_types = ""
        filter_types_not = False
        filter_resources = ""
        filter_resources_not = False
        filter_components = ""
        filter_components_not = False
        filter_versions = ""
        filter_versions_not = False
        filter_max_items = 1000
        
        if migration_mode == "Μεμονωμένο Issue ID (Single)":
            single_id = st.text_input("Gemini Issue ID (π.χ. 316859):", value="")
        else:
            # Load project options dynamically
            project_mapping = {}  # display_label -> (id, code)
            try:
                projects = gemini_client.get_projects()
                for p in projects:
                    entity = p.get("BaseEntity", p.get("Entity", {}))
                    code = entity.get("Code") or ""
                    name = entity.get("Name") or ""
                    p_id = entity.get("Id") or p.get("Id")
                    if code and p_id:
                        label = f"{code} - {name}" if name else code
                        project_mapping[label] = (p_id, code)
            except Exception as e:
                print(f"Error loading projects: {e}")
                
            # If empty, fall back to standard project codes
            if not project_mapping:
                for code in ["SRV", "SHERC", "DHERC", "SGLX", "DGLX", "CUSTDGLX", "SMARTD"]:
                    project_mapping[code] = (None, code)
                    
            project_labels = sorted(list(project_mapping.keys()))
            # Find default selection index (SRV)
            default_index = 0
            for i, label in enumerate(project_labels):
                if label.startswith("SRV"):
                    default_index = i
                    break
                    
            selected_project_label = st.selectbox("Gemini Project:", project_labels, index=default_index)
            selected_project_id, batch_project = project_mapping[selected_project_label]
            
            batch_search = st.text_input("Κείμενο Αναζήτησης (Search Term):", value="")
            
            # Date filter range
            date_col1, date_col2 = st.columns(2)
            with date_col1:
                start_date = st.date_input("Από ημερομηνία:", value=None)
            with date_col2:
                end_date = st.date_input("Έως ημερομηνία:", value=None)
                
            # Advanced filters collapsible expander
            with st.expander("🛠️ Προηγμένα Φίλτρα (Advanced Filters)"):
                col_st, col_st_not = st.columns([3, 1])
                filter_statuses = col_st.text_input("Statuses (Καταστάσεις με κόμμα):", value="", help="π.χ. Open, In Progress, Closed")
                st.write("<div style='height: 12px;'></div>", unsafe_allow_html=True)
                filter_statuses_not = col_st_not.checkbox("NOT Statuses", value=False)
                
                col_tp, col_tp_not = st.columns([3, 1])
                filter_types = col_tp.text_input("Types (Τύποι με κόμμα):", value="", help="π.χ. Bug, Enhancement, Task")
                st.write("<div style='height: 12px;'></div>", unsafe_allow_html=True)
                filter_types_not = col_tp_not.checkbox("NOT Types", value=False)
                
                col_res, col_res_not = st.columns([3, 1])
                filter_resources = col_res.text_input("Resources (Αναθέσεις με κόμμα):", value="", help="π.χ. Δημήτρης Μπατσίλης")
                st.write("<div style='height: 12px;'></div>", unsafe_allow_html=True)
                filter_resources_not = col_res_not.checkbox("NOT Resources", value=False)
                
                col_comp, col_comp_not = st.columns([3, 1])
                filter_components = col_comp.text_input("Components (Εξαρτήματα με κόμμα):", value="", help="π.χ. UI, Core")
                st.write("<div style='height: 12px;'></div>", unsafe_allow_html=True)
                filter_components_not = col_comp_not.checkbox("NOT Components", value=False)
                
                col_ver, col_ver_not = st.columns([3, 1])
                filter_versions = col_ver.text_input("Versions (Εκδόσεις με κόμμα):", value="", help="π.χ. 1.0, 2.0")
                st.write("<div style='height: 12px;'></div>", unsafe_allow_html=True)
                filter_versions_not = col_ver_not.checkbox("NOT Versions", value=False)
                
                filter_max_items = st.number_input("Μέγιστο πλήθος (Max Items):", min_value=10, max_value=5000, value=1000, step=50)
                
        # Locked target Jira project
        st.text_input("Jira Target Project Key (Locked):", value="PYLMIG", disabled=True)
        
        # Action Options
        unfiltered = st.checkbox("Παράκαμψη ελέγχων αλυσίδας (Force / Unfiltered Mode)", value=False, help="Αγνοεί τους ελέγχους αν το DHERC/SHERC issue ανήκει σε άλλη αλυσίδα και το μεταφέρει αυτόνομα.")
        migrate_time_flag = st.checkbox("Μεταφορά Time Tracking (Worklogs)", value=True)
        
    with col_actions:
        st.markdown("### ⚙️ Ενέργειες Migration")
        
        # Preview/Search issues
        if st.button("🔍 Αναζήτηση / Προεπισκόπηση", use_container_width=True):
            with st.spinner("Αναζήτηση στο Gemini..."):
                found_issues = []
                if migration_mode == "Μεμονωμένο Issue ID (Single)":
                    if single_id.strip().isdigit():
                        raw_issue = gemini_client.get_single_issue(int(single_id))
                        if raw_issue:
                            found_issues.append(raw_issue)
                    else:
                        st.error("Παρακαλώ εισάγετε ένα έγκυρο αριθμητικό ID.")
                else:
                    try:
                        # If selected_project_id is None, try to find it
                        if not selected_project_id:
                            projects = gemini_client.get_projects()
                            for p in projects:
                                entity = p.get("BaseEntity", p.get("Entity", {}))
                                if entity.get("Code", "").upper() == batch_project.upper():
                                    selected_project_id = entity.get("Id") or p.get("Id")
                                    break
                    except Exception as e:
                        selected_project_id = None
                        st.error(f"Error fetching projects: {e}")
                        
                    if selected_project_id:
                        # Safety: default start_date to 3 months ago if not specified
                        actual_start_date = start_date
                        if not actual_start_date:
                            actual_start_date = (datetime.now() - relativedelta(months=3)).date()
                            st.info("ℹ️ Η αναζήτηση περιορίστηκε αυτόματα στους τελευταίους 3 μήνες για αποφυγή Timeout.")
                            
                        s_date = datetime.combine(actual_start_date, datetime.min.time())
                        e_date = datetime.combine(end_date, datetime.max.time()) if end_date else datetime.now()
                        
                        raw_issues = []
                        current_start = s_date
                        
                        # Loop and fetch in 3-month slices to avoid timeouts
                        while current_start < e_date:
                            current_end = current_start + relativedelta(months=3)
                            if current_end > e_date:
                                current_end = e_date
                                
                            criteria = GeminiSearchCriteria(
                                project_id=str(selected_project_id),
                                max_items=int(filter_max_items)
                            )
                            criteria.created_after = current_start
                            criteria.created_before = current_end
                            
                            try:
                                chunk_issues = gemini_client.get_issues_advanced(criteria)
                                if chunk_issues:
                                    raw_issues.extend(chunk_issues)
                            except Exception as e:
                                st.warning(f"⚠️ Σφάλμα λήψης πακέτου {current_start.strftime('%d/%m/%Y')} - {current_end.strftime('%d/%m/%Y')}: {e}")
                                
                            current_start = current_end
                            
                        try:
                            # Filter by search term
                            if batch_search:
                                raw_issues = [
                                    i for i in raw_issues 
                                    if batch_search.lower() in (i.get("Entity", {}).get("Title", "") or "").lower()
                                    or batch_search.lower() in (i.get("Entity", {}).get("Description", "") or "").lower()
                                ]
                                
                            # Filter by advanced statuses
                            if filter_statuses:
                                target_statuses = [s.strip().lower() for s in filter_statuses.split(",") if s.strip()]
                                if target_statuses:
                                    if filter_statuses_not:
                                        raw_issues = [x for x in raw_issues if (x.get("Status") or "").lower() not in target_statuses]
                                    else:
                                        raw_issues = [x for x in raw_issues if (x.get("Status") or "").lower() in target_statuses]
                                    
                            # Filter by advanced types
                            if filter_types:
                                target_types = [t.strip().lower() for t in filter_types.split(",") if t.strip()]
                                if target_types:
                                    if filter_types_not:
                                        raw_issues = [x for x in raw_issues if (x.get("Type") or "").lower() not in target_types]
                                    else:
                                        raw_issues = [x for x in raw_issues if (x.get("Type") or "").lower() in target_types]
                                    
                            # Filter by advanced resources
                            if filter_resources:
                                target_resources = [r.strip().lower() for r in filter_resources.split(",") if r.strip()]
                                if target_resources:
                                    filtered_by_resources = []
                                    for x in raw_issues:
                                        res_names = [r.get("Entity", {}).get("Fullname", "").lower() for r in x.get("Resources", [])]
                                        has_match = any(any(tr in rn for rn in res_names) for tr in target_resources)
                                        if filter_resources_not:
                                            if not has_match:
                                                filtered_by_resources.append(x)
                                        else:
                                            if has_match:
                                                filtered_by_resources.append(x)
                                    raw_issues = filtered_by_resources
                                    
                            # Filter by advanced components
                            if filter_components:
                                target_components = [c.strip().lower() for c in filter_components.split(",") if c.strip()]
                                if target_components:
                                    filtered_by_components = []
                                    for x in raw_issues:
                                        comp_names = [c.strip().lower() for c in (x.get("ComponentNames") or "").split(",") if c.strip()]
                                        has_match = any(any(tc in cn for cn in comp_names) for tc in target_components)
                                        if filter_components_not:
                                            if not has_match:
                                                filtered_by_components.append(x)
                                        else:
                                            if has_match:
                                                filtered_by_components.append(x)
                                    raw_issues = filtered_by_components
                                    
                            # Filter by advanced versions
                            if filter_versions:
                                target_versions = [v.strip().lower() for v in filter_versions.split(",") if v.strip()]
                                if target_versions:
                                    if filter_versions_not:
                                        raw_issues = [x for x in raw_issues if (x.get("FixedInVersion") or "").lower() not in target_versions]
                                    else:
                                        raw_issues = [x for x in raw_issues if (x.get("FixedInVersion") or "").lower() in target_versions]
                                    
                            # Remove duplicates
                            unique_issues = []
                            seen_ids = set()
                            for item in raw_issues:
                                entity = item.get("Entity", item.get("BaseEntity", {}))
                                item_id = entity.get("Id")
                                if item_id and item_id not in seen_ids:
                                    seen_ids.add(item_id)
                                    unique_issues.append(item)
                                    
                            found_issues = unique_issues
                        except Exception as e:
                            st.error(f"Error filtering issues: {e}")
                    else:
                        st.error(f"Το Project Code {batch_project} δεν βρέθηκε στο Gemini.")
                        
                if found_issues:
                    st.session_state.found_issues_to_migrate = found_issues
                    st.success(f"Βρέθηκαν {len(found_issues)} θέματα προς μεταφορά!")
                else:
                    st.session_state.found_issues_to_migrate = []
                    st.warning("Δεν βρέθηκαν θέματα με τα συγκεκριμένα κριτήρια.")
                    
        # Preview table and selection
        if "found_issues_to_migrate" in st.session_state and st.session_state.found_issues_to_migrate:
            st.markdown("**Επιλέξτε τα θέματα που θέλετε να μεταφέρετε:**")
            
            preview_data = []
            for issue in st.session_state.found_issues_to_migrate:
                entity = issue.get("Entity", issue.get("BaseEntity", issue))
                preview_data.append({
                    "ID": entity.get("Id"),
                    "Project": issue.get("ProjectCode", ""),
                    "Τίτλος": entity.get("Title", "")[:80],
                    "Τύπος": issue.get("Type", ""),
                    "Κατάσταση": issue.get("Status", ""),
                    "Ημ. Δημιουργίας": entity.get("Created", "")[:10] if entity.get("Created") else ""
                })
            
            df_preview = pd.DataFrame(preview_data)
            df_preview.insert(0, "Επιλογή", True)
            
            edited_df = st.data_editor(
                df_preview,
                column_config={"Επιλογή": st.column_config.CheckboxColumn(required=True)},
                disabled=["ID", "Project", "Τίτλος", "Τύπος", "Κατάσταση", "Ημ. Δημιουργίας"],
                hide_index=True,
                use_container_width=True
            )
            
            selected_ids = edited_df[edited_df["Επιλογή"] == True]["ID"].tolist()
            st.write(f"Επιλεγμένα για Migration: **{len(selected_ids)}** θέματα.")
            
            if st.button("🚀 Εκκίνηση Migration", type="primary", use_container_width=True):
                log_placeholder = st.empty()
                progress_bar = st.progress(0)
                status_logs = []
                
                def ui_logger(msg):
                    status_logs.append(msg)
                    log_placeholder.text_area("Migration Logs", value="\\n".join(status_logs), height=250)
                    
                ui_logger(f"Ξεκινάει το Migration για {len(selected_ids)} θέματα στο Jira Project 'PYLMIG'...")
                
                success_count = 0
                for index, issue_id in enumerate(selected_ids):
                    try:
                        ui_logger(f"\\n[{index+1}/{len(selected_ids)}] Επεξεργασία Gemini ID: {issue_id}...")
                        
                        s_dt = datetime.combine(start_date, datetime.min.time()) if start_date else None
                        e_dt = datetime.combine(end_date, datetime.max.time()) if end_date else None
                        
                        res = process_migration(
                            issue_id=issue_id,
                            target_project_key="PYLMIG",
                            gemini_client=gemini_client,
                            jira_client=jira_client,
                            lookup_cache=lookup_cache,
                            unfiltered=unfiltered,
                            migrate_time_flag=migrate_time_flag,
                            start_date=s_dt,
                            end_date=e_dt,
                            logger_fn=ui_logger
                        )
                        
                        if res["success"]:
                            success_count += 1
                            ui_logger(f"✅ Επιτυχές Migration! Jira Key: {res['jira_key']} (Στρατηγική: {res['strategy']})")
                        else:
                            ui_logger(f"⚠️ Το Migration ολοκληρώθηκε χωρίς να δημιουργηθεί νέο Jira ticket.")
                            
                    except Exception as e:
                        ui_logger(f"❌ Σφάλμα στο issue {issue_id}: {e}")
                        
                    progress_bar.progress((index + 1) / len(selected_ids))
                    
                ui_logger(f"\\n🏁 Το Migration ολοκληρώθηκε! Επιτυχείς μεταφορές: {success_count}/{len(selected_ids)}.")
                st.balloons()
"""

with open('src/etl/migrator.py', 'wb') as f:
    f.write(base_content + new_func.encode('utf-8'))

print("File src/etl/migrator.py repaired with advanced NOT filters, BaseEntity project parser, and dynamic date chunking successfully!")
