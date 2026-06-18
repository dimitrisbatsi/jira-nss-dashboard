import os
import urllib.parse
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from contextlib import contextmanager

# Ιδανικά αυτά θα έρχονται από το config/settings.py (το οποίο διαβάζει το .env)
# Για το παράδειγμα, τα διαβάζουμε κατευθείαν από το περιβάλλον
DB_SERVER = os.getenv("DB_SERVER", "dev-gemini")
DB_NAME = os.getenv("DB_NAME", "GeminiMetrics")
DB_USER = os.getenv("DB_USER", "supportappl")
DB_PASSWORD = os.getenv("DB_PASSWORD", "Meq4HAR%")
# Προσοχή: Ο Driver πρέπει να είναι εγκατεστημένος στο μηχάνημα που τρέχει η Python
DB_DRIVER = os.getenv("DB_DRIVER", "ODBC Driver 17 for SQL Server")

# Κρίσιμο: Κάνουμε url-encode το password γιατί αν έχει σύμβολα (π.χ. @, !) θα σπάσει το connection string
encoded_password = urllib.parse.quote_plus(DB_PASSWORD)

# Το connection string για SQLAlchemy + pyodbc
connection_string = (
    f"mssql+pyodbc://{DB_USER}:{encoded_password}@{DB_SERVER}/{DB_NAME}"
    f"?driver={DB_DRIVER}"
)

# Δημιουργία του Engine με Enterprise ρυθμίσεις
engine = create_engine(
    connection_string,
    fast_executemany=True,  # Το πιο σημαντικό flag για ETL στον SQL Server!
    pool_size=5,            # Πόσες συνδέσεις θα κρατάει ανοιχτές στο pool
    max_overflow=10,        # Πόσες επιπλέον μπορεί να ανοίξει αν υπάρχει φόρτος
    pool_timeout=30,        # Πόσα δευτερόλεπτα να περιμένει για ελεύθερη σύνδεση
    pool_pre_ping=True      # Ελέγχει αν έπεσε η σύνδεση (π.χ. restart του SQL) πριν στείλει query
)

# Το εργοστάσιο που παράγει Sessions
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@contextmanager
def get_db_session():
    """
    Context manager για την ασφαλή διαχείριση των Database Sessions.
    Χρήση: 
        with get_db_session() as session:
            session.add(new_log)
    """
    session = SessionLocal()
    try:
        yield session
        # Αν όλα πάνε καλά και το script κάνει commit() μόνο του, τέλεια.
        # Αν ξεχάσουμε το commit(), δεν θα σωθεί τίποτα (safety first).
    except Exception as e:
        session.rollback() # Αν "σκάσει" το Python code, κάνουμε rollback το transaction
        raise e            # Και πετάμε το error πιο πάνω για να καταγραφεί
    finally:
        session.close()    # Επιστροφή της σύνδεσης στο Pool