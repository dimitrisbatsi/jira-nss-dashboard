# 📊 NSS Support Timesheet Dashboard

Αυτή η εφαρμογή παρέχει μια διαδραστική απεικόνιση των Worklogs από το Jira Cloud για την ομάδα NSS Support.

## 🏗️ Αρχιτεκτονική (ETL / Database)

Για λόγους ταχύτητας και αξιοπιστίας, το dashboard **ΔΕΝ** επικοινωνεί απευθείας με το Jira API όταν το ανοίγει ο χρήστης. Η αρχιτεκτονική ακολουθεί το μοντέλο **ETL (Extract, Transform, Load)**:

1. **Background Worker (`sync_db.py`):** Ένα ανεξάρτητο Python script αναλαμβάνει να συνδεθεί στο Jira (μέσω Atlassian API Gateway), να κατεβάσει τα Worklogs χρησιμοποιώντας Cursor-based pagination, να υπολογίσει δυναμικά τις κατηγορίες και να αποθηκεύσει τα καθαρά δεδομένα σε μια τοπική βάση **SQLite** (`timesheet.db`).
2. **Frontend (`timesheet.py`):** Το Streamlit διαβάζει αποκλειστικά την SQLite βάση, προσφέροντας χρόνους φόρτωσης <0.1 δευτερολέπτων για χιλιάδες εγγραφές.

---

## 🔐 Διαχείριση Ασφάλειας (Secrets) & Authentication

Η εφαρμογή χρησιμοποιεί τη σύγχρονη αρχιτεκτονική ασφαλείας της Atlassian, κάνοντας χρήση **Scoped API Tokens (OAuth 2.0 / Bearer)** για Service Accounts, τα οποία δρομολογούνται μέσω του κεντρικού Atlassian Gateway χρησιμοποιώντας το Cloud ID του οργανισμού.

Τα ευαίσθητα δεδομένα **δεν** περιλαμβάνονται στον κώδικα της εφαρμογής. Αποθηκεύονται στο αρχείο:
`./.streamlit/secrets.toml`

Η μορφή του αρχείου πρέπει να είναι η εξής:
```toml
JIRA_EMAIL = "email_του_service_account@domain.com"
JIRA_JWT_TOKEN = "το_bearer_token_απο_την_κονσολα"
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
Για να ανανεώνονται τα δεδομένα αυτόματα, το `sync_db.py` ρυθμίζεται ως Scheduled Task στον Windows Server:

1. Ανοίξτε το **Task Scheduler** στα Windows.
2. Πατήστε **Create Task...** (όχι Basic).
3. **General:** Δώστε όνομα (π.χ. `JiraTimesheetSync`) και επιλέξτε "Run whether user is logged on or not".
4. **Triggers:** Επιλέξτε "Daily" και στο Advanced settings επιλέξτε "Repeat task every: **30 minutes**" για διάρκεια "Indefinitely".
5. **Actions:** * **Action:** `Start a program`
   * **Program/script:** Βάλτε το path της Python (π.χ. `C:\Python314\pythonw.exe`).
   * **Add arguments:** `sync_db.py`
   * **Start in:** Το path του φακέλου της εφαρμογής (π.χ. `C:\inetpub\wwwroot\TimesheetApp`).
6. Αποθηκεύστε το task. (Τα logs της εκτέλεσης γράφονται αυτόματα στο αρχείο `sync_db.log`).

---

### 🛠️ Τεχνικές Πληροφορίες
* **Γλώσσα:** Python 3.x
* **Framework:** Streamlit
* **Host:** Windows Server (μέσω NSSM)
* **Πρόσβαση:** Απαιτεί σύνδεση στο εταιρικό VPN.