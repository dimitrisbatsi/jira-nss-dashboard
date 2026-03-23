import os
import zipfile
import glob
import shutil
import logging
from datetime import datetime, timedelta

# --- 0. Ρύθμιση Logging (Ημερήσια Logs) ---
# 1. Δημιουργία του φακέλου "logs" αν δεν υπάρχει ήδη
log_dir = "logs"
os.makedirs(log_dir, exist_ok=True)

# 2. Φτιάχνουμε δυναμικό όνομα αρχείου με τη σημερινή ημερομηνία (π.χ. sync_2026-03-23.log)
current_date = datetime.now().strftime("%Y-%m-%d")
log_filename = os.path.join(log_dir, f"backup_{current_date}.log")

# 3. Ρύθμιση του logger για να γράφει στο σημερινό αρχείο και στην οθόνη
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.FileHandler(log_filename, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)

def run_backup():
    logging.info("📦 Ξεκινάει η διαδικασία Backup...")
    
    # --- ΡΥΘΜΙΣΕΙΣ ---
    local_backup_folder = "Backups"
    # Βάλε εδώ το μονοπάτι για το Cloud / Network Drive (π.χ. r"\\192.168.1.50\IT_Share\Timesheet_Backups")
    # Αν το αφήσεις κενό (""), θα κρατάει μόνο τοπικά backups
    remote_backup_folder = r"" 
    retention_days = 14
    
    # 1. Δημιουργία τοπικού φακέλου
    if not os.path.exists(local_backup_folder):
        os.makedirs(local_backup_folder)
        
    # 2. Ονομασία του νέου αρχείου
    date_str = datetime.now().strftime("%Y-%m-%d_%H-%M")
    zip_filename = os.path.join(local_backup_folder, f"Timesheet_Backup_{date_str}.zip")
    
    files_to_backup = [
        "timesheet.db", "timesheet.py", "sync_db.py", "backup.py", 
        "sync_db.log", "backup.log", 
        ".streamlit/config.toml", ".streamlit/secrets.toml"
    ]
    
    # 3. Συμπίεση σε ZIP
    try:
        with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for file in files_to_backup:
                if os.path.exists(file):
                    zipf.write(file)
        logging.info(f"✅ Το Backup δημιουργήθηκε επιτυχώς τοπικά: {zip_filename}")
    except Exception as e:
        logging.error(f"❌ Σφάλμα κατά τη δημιουργία του ZIP: {e}")
        return
        
    # 3Β. Αντιγραφή στο Remote / Cloud Folder (Αν έχει οριστεί)
    if remote_backup_folder and os.path.exists(remote_backup_folder):
        try:
            shutil.copy2(zip_filename, remote_backup_folder)
            logging.info(f"☁️ Το Backup αντιγράφηκε επιτυχώς στο Network/Cloud: {remote_backup_folder}")
        except Exception as e:
            logging.error(f"❌ Αποτυχία αντιγραφής στο Network/Cloud: {e}")
            
    # 4. Αυτόματη Εκκαθάριση Τοπικών Backups (Retention Policy)
    cutoff_date = datetime.now() - timedelta(days=retention_days)
    existing_backups = glob.glob(os.path.join(local_backup_folder, "*.zip"))
    deleted_count = 0
    
    for backup_file in existing_backups:
        file_time = datetime.fromtimestamp(os.path.getctime(backup_file))
        if file_time < cutoff_date:
            try:
                os.remove(backup_file)
                deleted_count += 1
                logging.info(f"🗑️ Διαγράφηκε παλιό backup: {backup_file}")
            except Exception as e:
                logging.warning(f"⚠️ Δεν ήταν δυνατή η διαγραφή του {backup_file}: {e}")
                
    if deleted_count > 0:
        logging.info(f"🧹 Η εκκαθάριση ολοκληρώθηκε. Διαγράφηκαν {deleted_count} παλιά αρχεία.")
        
    logging.info("🏁 Η διαδικασία Backup ολοκληρώθηκε.\n")

if __name__ == "__main__":
    run_backup()