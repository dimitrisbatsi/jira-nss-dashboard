import sys
import time

# --- IMPORTS ΤΩΝ ETL ΣΥΝΑΡΤΗΣΕΩΝ ---
# 1. Projects
from modules.test_projects_etl import run_real_projects_etl, run_jira_projects_etl
# 2. Users
from modules.test_users_etl import run_users_etl, run_jira_users_etl
# 3. Components
from modules.test_components_etl import run_components_etl, run_jira_components_etl
# 4. Issues
from modules.test_issues_etl import run_incremental_jira_etl, run_incremental_issues_and_children_etl


def print_menu():
    print("\n" + "="*45)
    print(" 🚀 DATA WAREHOUSE ETL MANAGER (v1.0) 🚀")
    print("="*45)
    print("Επιλέξτε ενέργεια συγχρονισμού:")
    print("  1. Συγχρονισμός Projects (Gemini & Jira)")
    print("  2. Συγχρονισμός Users (Gemini & Jira)")
    print("  3. Συγχρονισμός Components (Gemini & Jira)")
    print("  4. Συγχρονισμός Issues & Worklogs (Gemini & Jira)")
    print("-" * 45)
    print("  5. ⚡ ΠΛΗΡΗΣ ΣΥΓΧΡΟΝΙΣΜΟΣ (ΟΛΑ - Προτεινόμενη Σειρά)")
    print("  0. Έξοδος")
    print("="*45)

def sync_projects():
    print("\n[>>>] Ξεκινάει ο συγχρονισμός των Projects...")
    run_real_projects_etl() # Gemini
    run_jira_projects_etl() # Jira

def sync_users():
    print("\n[>>>] Ξεκινάει ο συγχρονισμός των Users...")
    run_users_etl() # Gemini
    run_jira_users_etl() # Jira

def sync_components():
    print("\n[>>>] Ξεκινάει ο συγχρονισμός των Components...")
    run_components_etl() # Gemini
    run_jira_components_etl() # Jira

def sync_issues():
    print("\n[>>>] Ξεκινάει ο συγχρονισμός των Issues...")
    run_incremental_issues_and_children_etl() # Gemini
    run_incremental_jira_etl() # Jira

def run_all():
    print("\n" + "*"*50)
    print(" ΕΚΚΙΝΗΣΗ ΠΛΗΡΟΥΣ ΣΥΓΧΡΟΝΙΣΜΟΥ ".center(50, "*"))
    print("*"*50)
    
    start_time = time.time()
    
    try:
        sync_projects()
        sync_users()
        sync_components()
        sync_issues()
        
        end_time = time.time()
        mins, secs = divmod(int(end_time - start_time), 60)
        print("\n" + "*"*50)
        print(f" [ΕΠΙΤΥΧΙΑ] Το Full Sync ολοκληρώθηκε σε {mins} λεπτά και {secs} δευτερόλεπτα! ".center(50))
        print("*"*50)
        
    except Exception as e:
        print(f"\n[ΚΡΙΣΙΜΟ ΣΦΑΛΜΑ] Το Full Sync διεκόπη. Λεπτομέρειες: {e}")

def main():
    while True:
        print_menu()
        choice = input("\nΕπιλογή (0-5): ").strip()
        
        if choice == '1':
            sync_projects()
        elif choice == '2':
            sync_users()
        elif choice == '3':
            sync_components()
        elif choice == '4':
            sync_issues()
        elif choice == '5':
            run_all()
        elif choice == '0':
            print("\nΚλείσιμο ETL Manager. Καλή συνέχεια!")
            sys.exit(0)
        else:
            print("\n[!] Μη έγκυρη επιλογή. Παρακαλώ εισάγετε αριθμό από το 0 έως το 5.")

if __name__ == "__main__":
    # Αυτό αποτρέπει το να σπάνε χαρακτήρες αν τρέχεις σε Windows CMD
    sys.stdout.reconfigure(encoding='utf-8')
    main()