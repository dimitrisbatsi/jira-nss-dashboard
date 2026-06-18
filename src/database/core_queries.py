from sqlalchemy import text
from datetime import datetime, timezone

def get_last_sync_date(engine, entity_name: str) -> datetime:
    """Διαβάζει το τελευταίο επιτυχές Timestamp από τον πίνακα SyncMetadata."""
    query = text("SELECT LastSyncAt FROM SyncMetadata WHERE EntityName = :entity")
    with engine.connect() as conn:
        result = conn.execute(query, {"entity": entity_name}).fetchone()
        
        if result and result[0]:
            dt = result[0]
            # Αν η ημερομηνία από τη βάση δεν έχει timezone (naive), της βάζουμε UTC!
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
            
        # Αν δεν υπάρχει εγγραφή (1η φορά που τρέχει), επιστρέφουμε μια πολύ παλιά ημερομηνία (aware)
        return datetime(2000, 1, 1, tzinfo=timezone.utc)

def update_last_sync_date(engine, entity_name: str, sync_date: datetime):
    """Ενημερώνει ή εισάγει το Timestamp μετά από ΕΠΙΤΥΧΗΜΕΝΟ sync."""
    query = text("""
        MERGE SyncMetadata AS Target
        USING (SELECT :entity AS EntityName, :sync_date AS LastSyncAt) AS Source
        ON Target.EntityName = Source.EntityName
        WHEN MATCHED THEN
            UPDATE SET Target.LastSyncAt = Source.LastSyncAt
        WHEN NOT MATCHED BY TARGET THEN
            INSERT (EntityName, LastSyncAt)
            VALUES (Source.EntityName, Source.LastSyncAt);
    """)
    with engine.begin() as conn:
        conn.execute(query, {"entity": entity_name, "sync_date": sync_date})