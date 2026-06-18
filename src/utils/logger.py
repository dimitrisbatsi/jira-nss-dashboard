from sqlalchemy.orm import Session
from sqlalchemy import text
from src.models.db_models import SyncLog, SyncLogDetail, SyncLogTypeEnum
from datetime import datetime, timezone

def create_sync_session_log(db_session: Session, entity_name: str) -> SyncLog:
    """Ξεκινάει την καταγραφή ενός νέου Sync."""
    new_log = SyncLog(
        EntityName=entity_name,
        StartedAt=datetime.utcnow(),
        Status="Running"
    )
    db_session.add(new_log)
    db_session.commit() # Το κάνουμε commit για να πάρουμε πίσω το ID από τον SQL Server
    return new_log

def log_error(db_session: Session, sync_log_id: int, record_id: str, error_msg: str, stack_trace: str):
    """Καταγράφει ένα σφάλμα για μια συγκεκριμένη εγγραφή."""
    detail = SyncLogDetail(
        SyncLogID=sync_log_id,
        RecordID=record_id,
        ErrorMessage=error_msg,
        StackTrace=stack_trace,
        LogType=SyncLogTypeEnum.Error,
        OccuredAt=datetime.utcnow()
    )
    db_session.add(detail)
    db_session.commit()

def close_sync_session_log(db_session, sync_log_id: int, status: str):
    """
    Κλείνει το Sync Session με Raw SQL (παρακάμπτοντας το ORM) 
    για να αποφύγουμε τα StaleDataErrors του SQL Server.
    """
    # Χρησιμοποιούμε GETUTCDATE() του SQL Server ή περνάμε την ώρα από την Python
    current_time = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    
    update_query = text("""
        UPDATE SyncLog 
        SET FinishedAt = :time_now, Status = :status 
        WHERE ID = :log_id
    """)
    
    db_session.execute(update_query, {
        "time_now": current_time,
        "status": status, 
        "log_id": sync_log_id
    })
    
    db_session.commit()