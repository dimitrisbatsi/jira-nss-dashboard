# 📊 NSS Support Timesheet Dashboard

Αυτή η εφαρμογή παρέχει μια διαδραστική απεικόνιση των Worklogs από το Jira Cloud για την ομάδα NSS Support.

---

## 🏗️ Αρχιτεκτονική (ETL / Database)

Για λόγους ταχύτητας και αξιοπιστίας, το dashboard **ΔΕΝ** επικοινωνεί απευθείας με το Jira API όταν το ανοίγει ο χρήστης. Η αρχιτεκτονική ακολουθεί το μοντέλο **ETL (Extract, Transform, Load)**:

1. **Background Worker (`sync_db.py`):** Ένα ανεξάρτητο Python script αναλαμβάνει να συνδεθεί στο Jira (μέσω Atlassian API Gateway), να κατεβάσει τα Worklogs χρησιμοποιώντας Cursor-based pagination, να υπολογίσει δυναμικά τις κατηγορίες και να αποθηκεύσει τα δεδομένα σε μια βάση **Microsoft SQL Server**.
2. **Frontend (`timesheet.py`):** Το Streamlit διαβάζει απευθείας από τον SQL Server, προσφέροντας χρόνους φόρτωσης <0.1 δευτερολέπτων για δεκάδες χιλιάδες εγγραφές χρησιμοποιώντας st.cache μηχανισμό.

> [!NOTE]
> Για περισσότερες τεχνικές λεπτομέρειες σχετικά με τη λειτουργία του Background Worker, δείτε το [sync_db_docs.md](file:///c:/Users/d.batsilis/OneDrive%20-%20Epsilon%20Net%20S.A/Development/NSSTimesheetApp/sync_db_docs.md).

---

## 🔐 Διαχείριση Ασφάλειας (Secrets) & Authentication

Η εφαρμογή χρησιμοποιεί Scoped API Tokens (OAuth 2.0 / Bearer) για Service Accounts, τα οποία δρομολογούνται μέσω του Atlassian Gateway.

Τα ευαίσθητα δεδομένα **δεν** περιλαμβάνονται στον κώδικα της εφαρμογής. Αποθηκεύονται στο αρχείο:
`./.streamlit/secrets.toml`

Η μορφή του αρχείου πρέπει να είναι η εξής:
```toml
# Scoped API Token για Jira API
JIRA_JWT_TOKEN = "το_bearer_token_απο_την_κονσολα"

# Connection String για SQL Server (Χρησιμοποιήστε μονά εισαγωγικά για literal string)
CONNECTION_STRING = 'Data Source=Όνομα_Server\Όνομα_Instance;Database=NSSTimesheetApp;User ID=sa;Password=κωδικός;'
```

---

### 🔑 Οδηγίες Δημιουργίας Νέου Scoped API Token
Σε περίπτωση που το Token λήξει, ακολουθήστε τα παρακάτω βήματα για να εκδώσετε νέο:

1. Συνδεθείτε στο **Atlassian Admin Panel**: [admin.atlassian.com](https://admin.atlassian.com/).
2. Επιλέξτε την εφαρμογή/Service Account (π.χ. `NSS_Pylon_Apps_API`) και προχωρήστε σε Revoke.
3. Επιλέξτε **Create Credentials** επάνω δεξιά από το μπλε κουμπί.
4. Στο αναδυόμενο παράθυρο, επιλέξτε API Token και πατήστε Next.
5. Διαλέξτε όλα τα απαραίτητα Scopes (θα βρείτε τη λίστα στο τελευταίο commit στο αρχείο `NSS_Pylon_Apps_API_Scopes_032026`), επιλέξτε Next, επιβεβαιώστε και Create.
6. **Αντιγράψτε αμέσως το Token** (δεν θα εμφανιστεί ξανά).
7. Ανοίξτε το αρχείο `.streamlit/secrets.toml` στον server.
8. Αντικαταστήστε την τιμή του `JIRA_JWT_TOKEN` με το νέο κλειδί και αποθηκεύστε.
9. Ο επόμενος κύκλος του `sync_db.py` θα χρησιμοποιήσει αυτόματα τα νέα διαπιστευτήρια.

---

### ⚙️ Ρύθμιση Αυτόματου Συγχρονισμού (Windows Task Scheduler)
Η εφαρμογή χρησιμοποιεί ένα **υβριδικό μοντέλο** συγχρονισμού (Incremental Sync κατά τη διάρκεια της ημέρας και Full Sync τα Σαββατοκύριακα).

Για να ρυθμίσετε αυτόματα τα Scheduled Tasks στον Windows Server:
1. Ανοίξτε ένα παράθυρο **PowerShell ως Administrator**.
2. Μεταβείτε στον φάκελο της εφαρμογής.
3. Εκτελέστε το script:
   ```powershell
   Set-ExecutionPolicy Bypass -Scope Process -Force
   .\setup_scheduler.ps1
   ```
Αυτό θα δημιουργήσει αυτόματα τα εξής tasks:
* **Incremental Sync**: Τρέχει κάθε 15 λεπτά τις καθημερινές (09:00-18:00) και κάθε 1 ώρα τις βραδινές ώρες (18:00-00:00).
* **Full Sync**: Τρέχει κάθε Σάββατο και Κυριακή στις 06:00 πμ (πλήρης ανανέωση βάσης).

---

### 🛠️ Τεχνικές Πληροφορίες
* **Γλώσσα:** Python 3.x (με pyodbc & SQLAlchemy)
* **Framework:** Streamlit (v1.55+)
* **Βάση:** Microsoft SQL Server
* **Host:** Windows Server
* **Πρόσβαση:** Απαιτεί σύνδεση στο εταιρικό VPN.