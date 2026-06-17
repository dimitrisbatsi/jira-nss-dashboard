# ⚙️ Documentation: sync_db.py

Το script `sync_db.py` αποτελεί τον μηχανισμό συγχρονισμού (ETL background worker) της εφαρμογής **NSS Support Timesheet Dashboard**. Συνδέεται στο Jira Cloud API, συλλέγει τους χρόνους εργασίας (worklogs) της ομάδας, κάνει τους απαραίτητους μετασχηματισμούς και τους καταχωρεί σε μια βάση Microsoft SQL Server.

---

## 📋 Βασικά Χαρακτηριστικά
* **Υβριδικό Μοντέλο Συγχρονισμού**: Υποστηρίζει γρήγορο incremental συγχρονισμό (για καθημερινή συχνή εκτέλεση) και πλήρη συγχρονισμό (full reload) για συντήρηση.
* **Διαχείριση Διπλοτύπων**: Στο incremental mode, διαγράφει τις προηγούμενες καταγραφές των επηρεαζόμενων tickets πριν εισάγει τις νέες, εμποδίζοντας τη διπλή καταχώρηση χρόνων.
* **Αυτόματη Επιλογή Driver**: Αναλύει το connection string και δοκιμάζει αυτόματα τους διαθέσιμους ODBC Drivers των Windows (`ODBC Driver 17 for SQL Server`, `SQL Server Native Client 11.0`, `SQL Server`).
* **UTF-8 Logging**: Καταγράφει καθημερινά logs στον φάκελο `logs/` και υποστηρίζει σωστή απεικόνιση ελληνικών χαρακτήρων και emoji στην κονσόλα.

---

## 🛠️ Ρυθμίσεις & Παράμετροι Εκτέλεσης (CLI Arguments)

Μπορείτε να εκτελέσετε το script από τη γραμμή εντολών περνώντας τις ακόλουθες παραμέτρους:

```bash
python sync_db.py [--mode {incremental,full}] [--days DAYS]
```

### Παράμετροι:
1. **`--mode`** (Επιλογές: `incremental` / `full`, default: `incremental`):
   * **`incremental`**: Φέρνει μόνο tickets που έχουν υποστεί τροποποίηση ή δημιουργία πρόσφατα.
   * **`full`**: Φέρνει όλα τα tickets από καταβολής κόσμου.
2. **`--days`** (Default: `7`):
   * Ορίζει το «παράθυρο» ημερών προς έλεγχο για το incremental mode. Αγνοείται στο full mode.

---

## 🔄 Λογική ETL (Data Flow)

### 1. Extract (Λήψη Δεδομένων)
* **API Authentication**: Χρησιμοποιεί το Bearer token `JIRA_JWT_TOKEN` από το αρχείο `.streamlit/secrets.toml`.
* **JQL Query**: 
  * incremental: `project IN (...) AND issuetype = "Time Type" AND (status = "Time Entered" OR status = "Time-Entered") AND updated >= -{days}d`
  * full: `project IN (...) AND issuetype = "Time Type" AND (status = "Time Entered" OR status = "Time-Entered")`
* **Cursor-based Pagination**: Κατεβάζει τα tickets σε batches των 100 εγγραφών χρησιμοποιώντας το `nextPageToken` της Atlassian.
* **Parent Bulk Fetch**: Για να μειώσει τα API requests, απομονώνει τα parent keys και κατεβάζει τα custom fields (`Partner Name`, `LSP Customer Name`) σε bulk chunks των 50.

### 2. Transform (Μετασχηματισμός)
* Υπολογίζει τα components και τις κατηγορίες (Parent Category).
* Μετατρέπει τα seconds σε minutes.
* Φιλτράρει και αντιστοιχίζει τις στήλες του Pandas DataFrame με τα CamelCase πεδία του SQL Server:
  * `"Issue Key"` ➡️ `IssueKey`
  * `"Parent Key"` ➡️ `ParentKey`
  * `"Parent Title"` ➡️ `ParentTitle`
  * `"Date"` ➡️ `WorkDate`
  * ...κλπ.

### 3. Load (Αποθήκευση στη Βάση)
* **Σύνδεση**: Χρησιμοποιεί το `CONNECTION_STRING` από το `.streamlit/secrets.toml`.
* **Αποθήκευση (Full Mode)**: 
  * Εκτελεί `TRUNCATE TABLE WorkLogs` για να καθαρίσει όλο τον πίνακα.
  * Κάνει bulk insert (`to_sql` με `if_exists='append'`).
* **Αποθήκευση (Incremental Mode)**:
  * Απομονώνει τα μοναδικά `IssueKey` των tickets που κατέβηκαν.
  * Εκτελεί `DELETE FROM WorkLogs WHERE IssueKey IN (...)` σε chunks των 1000 κλειδιών για να διαγράψει τα παλιά logs αυτών των tickets.
  * Κάνει bulk insert των νέων εγγραφών.

---

## 🗂️ Αρχείο Σχήματος Βάσης (Files/DB_INIT.sql)

Ο πίνακας στον SQL Server πρέπει να έχει την παρακάτω δομή:

```sql
CREATE TABLE WorkLogs (
    LogID BIGINT IDENTITY(1,1) PRIMARY KEY,
    IssueKey NVARCHAR(50) NOT NULL,
    ParentKey NVARCHAR(50) NULL,
    ParentTitle NVARCHAR(255) NULL,
    Project NVARCHAR(100) NULL,
    Assignee NVARCHAR(100) NULL,
    TimeType NVARCHAR(100) NULL,
    ChargeType NVARCHAR(100) NULL,
    Minutes INT NOT NULL DEFAULT 0,
    WorkDate DATE NOT NULL,
    ParentCategory NVARCHAR(255) NULL,
    Components NVARCHAR(500) NULL,
    PartnerName NVARCHAR(255) NULL,
    LSPCustomerName NVARCHAR(255) NULL
);
```

---

## 📊 Μεταδεδομένα Συγχρονισμού (Sync_Metadata)

Για την καταγραφή της τελευταίας ενημέρωσης των δεδομένων στη βάση (ώστε το UI να μην δείχνει την ώρα refresh της σελίδας αλλά την πραγματική ημερομηνία συγχρονισμού):
* Το script `sync_db.py` στο τέλος κάθε επιτυχούς εκτέλεσης (Incremental ή Full) αδειάζει τον πίνακα `Sync_Metadata` και εισάγει την τρέχουσα ημερομηνία και ώρα (`GETDATE()`).
* Ο πίνακας `Sync_Metadata` δημιουργείται αυτόματα αν δεν υπάρχει στη βάση.

---

## 📅 Αυτοματοποίηση (Task Scheduler)

Για την αυτοματοποίηση των εκτελέσεων χρησιμοποιείται το Powershell script `setup_scheduler.ps1` το οποίο ρυθμίζει τις εργασίες στα Windows:
* **Καθημερινές (9πμ - 6μμ)**: `python sync_db.py --mode incremental --days 7` (κάθε 15 λεπτά).
* **Καθημερινές (6μμ - 12πμ)**: `python sync_db.py --mode incremental --days 7` (κάθε 1 ώρα).
* **Σαββατοκύριακο (6πμ)**: `python sync_db.py --mode full` (μία φορά τη μέρα).
