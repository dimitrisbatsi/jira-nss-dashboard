# Jira Support Pilot - Chrome/Edge Extension (Manifest V3)

Ο **Jira Support Pilot** είναι ένα τοπικό Browser Extension (συμβατό με Chrome, Edge, Opera) σχεδιασμένο ειδικά για την ομάδα υποστήριξης της NSS. Σκοπός του είναι η απλοποίηση της καθημερινής καταγραφής χρόνου και η αυτοματοποίηση της επικοινωνίας με πελάτες απευθείας μέσα από το Jira Cloud.

---

## 🚀 Κύριες Λειτουργίες

1. **Γρήγορη Καταγραφή Χρόνου (Time Log Tab):**
   * Ανίχνευση του τρέχοντος Epic.
   * Αυτόματη εύρεση των παιδιών-θεμάτων τύπου `Services (Αίτημα Υπηρεσιών)` ή `Task`.
   * Επιλογή του επιθυμητού child issue (με dropdown αν υπάρχουν πολλά, αυτόματη επιλογή αν υπάρχει ένα, ή κουμπί γρήγορης δημιουργίας αν δεν υπάρχει κανένα).
   * Επιλογή του **Time Type** (Analysis, Support, Implementation, κλπ.) και του **Charge Type** (Billable, Non Billable) με dropdowns (με προεπιλεγμένες τιμές `Support` και `Non Billable`).
   * Αυτόματη δημιουργία sub-task τύπου `Time Type` με κληρονόμηση του **Component**, του **Partner Name** και του **LSP Customer Name** από το Epic.
   * Αυτόματη ανάθεση (assignee) του sub-task στον συνδεδεμένο χρήστη και μετάβαση status σε **Time Entered**.
   * Καταγραφή του χρόνου (worklog).

2. **Πρότυπες Απαντήσεις (Canned Messages Tab):**
   * dropdown επιλογή από τις **40 επίσημες πρότυπες απαντήσεις** της NSS.
   * Αυτόματη δυναμική αντικατάσταση placeholders όπως `[Όνομα Συνεργάτη]`, `[Όνομα Πελάτη]`, `[Product]`, `[Έκδοση Fix]` και `[Ονομα Συμβούλου]` από τα metadata του Epic.
   * Δυνατότητα επεξεργασίας του μηνύματος πριν την αποστολή.
   * **Έξυπνη Αποστολή Σχολίου:**
     * **Σε Epic:** Το σχόλιο δημοσιεύεται αυτόματα ως **External Comment** (προσθέτοντας τις comment properties `IsPublished = true`, `AuthorEmail` και `AuthorNickname` στην κλήση JIRA API) ώστε να εμφανίζεται στο εξωτερικό portal του συνεργάτη.
     * **Σε child/standard issue:** Το σχόλιο δημοσιεύεται αυτόματα ως απλό σχόλιο (**Standard Comment**) εσωτερικά στο Jira.

3. **Αυτόνομη Διαχείριση (Settings Tab & Refresh):**
   * Αποθήκευση Email και Jira API Token τοπικά στον browser (`chrome.storage.local`).
   * Κουμπί **🔄 Refresh** στο header για άμεση χειροκίνητη ανανέωση των δεδομένων χωρίς F5 στην καρτέλα.

---

## 🛠️ Λογική Ανάπτυξης & Αρχιτεκτονική (Zero Infrastructure)

Η επιλογή ανάπτυξης browser extension (αντί για ξεχωριστό backend server) έγινε για τους εξής λόγους:
* **Μηδενικό Κόστος Υποδομής (Zero-Host):** Το extension εκτελείται εξ ολοκλήρου στον browser του χρήστη. Δεν απαιτείται server, βάση δεδομένων ή API gateway.
* **Ασφάλεια Δεδομένων:** Τα API Tokens αποθηκεύονται τοπικά στον browser του χρήστη (`chrome.storage.local`).
* **Αυτόματος Συγχρονισμός SQL Server:** Επειδή το extension γράφει απευθείας στο Jira API χρησιμοποιώντας το token του χρήστη, οι καταγραφές συγχρονίζονται αυτόματα στην SQL Server staging βάση της εταιρείας μέσω του ήδη υπάρχοντος background ETL worker (`sync_db.py`), χωρίς να χρειάζεται να γράψουμε κώδικα βάσης στο extension.

---

## 📂 Δομή Αρχείων & Ευθύνες

* **[manifest.json](manifest.json):** Ορίζει τα μεταδεδομένα της επέκτασης, τις απαραίτητες άδειες (storage) και τους κανόνες πρόσβασης (host permissions για το `https://epsilon-singularlogic.atlassian.net/*`).
* **[background.js](background.js):**
  * Εκτελείται ως background service worker.
  * Αναλαμβάνει όλες τις κλήσεις fetch προς το Jira REST API (GET, POST, PUT) χρησιμοποιώντας Basic Authentication (Base64).
  * **Παράκαμψη CORS/CSP:** Επειδή εκτελείται στο context του extension, παρακάμπτει τους περιορισμούς CORS και τις πολιτικές CSP (Content Security Policy) που επιβάλλει η σελίδα του Jira.
  * Φορτώνει τοπικά το JSON των κονσερβών και το επιστρέφει στο content script.
* **[content.js](content.js):**
  * Το κύριο script που εκτελείται στη σελίδα του Jira.
  * Ανιχνεύει αλλαγές στο URL (υποστηρίζει SPA transitions).
  * Εισάγει ένα Shadow DOM στο body και inject-αρει το Sidebar.
  * Διαχειρίζεται όλη τη λογική ελέγχου, συμπλήρωσης στοιχείων και επικοινωνίας με το background script.
* **[sidebar.html](sidebar.html):** Η δομή HTML του sidebar (Tabs, Form fields, Inputs).
* **[sidebar.css](sidebar.css):** Premium Styling (Glassmorphic design, dark mode, smooth slide transitions, rotating reload animations).
* **[canned_responses.json](canned_responses.json):** Αρχείο JSON με τις 40 προδιαμορφωμένες απαντήσεις.

---

## ⚙️ Τεχνικές Λύσεις σε Advanced Προκλήσεις

### 1. Παράκαμψη Keyboard Shortcuts & Focus Trap του Jira
Το Jira χρησιμοποιεί global event listeners για συντομεύσεις πληκτρολογίου (shortcuts όπως `c` για create, `s` για share, `/` για search) και focus trap βιβλιοθήκες.
* **Πρόβλημα:** Όταν ο χρήστης πληκτρολογούσε στα πεδία του extension, το Jira «έκλεβε» τα πατήματα των πλήκτρων ή το focus.
* **Λύση:**
  * Χρησιμοποιούμε **Shadow DOM** για την πλήρη απομόνωση του CSS και του DOM.
  * Προσθέσαμε bubbling event listeners στο container του Shadow DOM για `keydown`, `keyup`, `keypress`, `mousedown`, `mouseup`, `click`, `focusin`, και `focusout` τα οποία καλούν **`e.stopPropagation()`**.
  * Αυτό επιτρέπει στα συμβάντα να εκτελούνται κανονικά στα inputs του extension (έτσι ο χρήστης μπορεί να γράψει και να επιλέξει), αλλά εμποδίζει τη διάδοσή τους προς το κεντρικό DOM του Jira, αποτρέποντας την ενεργοποίηση των συντομεύσεων του Jira.
  * Προσθέσαμε χειροκίνητο `.focus()` στο event `mousedown` των inputs για να παρακάμψουμε τυχόν focus interceptors.

### 2. Ανίχνευση dynamic SPA URL & Popover Modals
Το Jira Cloud είναι Single Page Application (SPA), που σημαίνει ότι η σελίδα δεν ξαναφορτώνει όταν πλοηγείσαι. Επίσης, τα boards ανοίγουν θέματα σε popover modal overlays.
* **Πρόβλημα:** Το extension έπρεπε να καταλαβαίνει πότε αλλάζει το εισιτήριο στην οθόνη χωρίς full page reload.
* **Λύση:**
  * Ορίσαμε έναν interval timer (1000ms) που ελέγχει συνεχώς το `location.href`.
  * Στη συνάρτηση `handleUrlChange`, ελέγχουμε τόσο το pathname του URL (`/browse/PYLCOM-XXXX`) όσο και την παράμετρο αναζήτησης **`selectedIssue`** (`?selectedIssue=PYLCOM-XXXX`), η οποία χρησιμοποιείται από το Jira όταν ανοίγει κάρτες σε popover modals πάνω από boards.

### 3. Διπλή Στρατηγική Εύρεσης Παιδιών (parent / Epic Link)
* **Πρόβλημα:** Ορισμένα projects στο Jira Cloud έχουν μεταβεί πλήρως στο νέο ενοποιημένο πεδίο `parent`, ενώ άλλα εξακολουθούν να χρησιμοποιούν το παλαιότερο `Epic Link`.
* **Λύση:**
  * Το extension εκτελεί πρώτα αναζήτηση με `parent = PYLCOM-XXXX`.
  * Αν δεν επιστραφεί κανένα αποτέλεσμα, εκτελεί αυτόματα fallback ερώτημα με `"Epic Link" = PYLCOM-XXXX`.
  * Τα αποτελέσματα φιλτράρονται **τοπικά στη Javascript** (`.filter()`) ελέγχοντας αν ο τύπος περιέχει τις λέξεις `service` ή `task` (case-insensitive), εξασφαλίζοντας συμβατότητα με ονόματα όπως `Services (Αίτημα Υπηρεσιών)` ή `Task` χωρίς σφάλματα JQL.

---

## 📥 Οδηγίες Εγκατάστασης (Developer Mode)

1. Κατεβάστε ή εντοπίστε τον φάκελο `jira-support-pilot-extension`.
2. Ανοίξτε τον Chrome ή τον Edge και μεταβείτε στις Επεκτάσεις (`chrome://extensions/` ή `edge://extensions/`).
3. Ενεργοποιήστε το **Developer Mode (Λειτουργία προγραμματιστή)** από τον διακόπτη επάνω δεξιά.
4. Κάντε κλικ στο **Load Unpacked (Φόρτωση αποσυμπιεσμένης επέκτασης)** επάνω αριστερά.
5. Επιλέξτε τον φάκελο `jira-support-pilot-extension`.
6. Ανοίξτε/Ανανεώστε (F5) τη σελίδα του Jira και κάντε κλικ στο 🚀 για να ξεκινήσετε!
