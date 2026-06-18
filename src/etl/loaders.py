import pandas as pd
from sqlalchemy import text
from sqlalchemy.types import String, Integer, DateTime, Boolean

def upsert_projects(df: pd.DataFrame, engine):
    """Κάνει Upsert (MERGE) τα δεδομένα και επιστρέφει τα (inserted, updated) counts"""
    temp_table = "GProjects_StagingTemp"

    dtypes = {
        'ProjectID': Integer(),
        'SourceApp': String(50), # <--- Προστέθηκε
        'ProjectCode': String(50),
        'ProjectName': String(255),
        'TemplateID': Integer(),
        'CreationDate': DateTime()
    }

    print(f"  -> Ανέβασμα {len(df)} εγγραφών σε προσωρινό πίνακα ({temp_table})...")
    
    with engine.begin() as conn:
        df.to_sql(name=temp_table, con=conn, if_exists='replace', index=False, dtype=dtypes)

        print("  -> Εκτέλεση SQL MERGE (Upsert)...")
        
        merge_query = f"""
        SET NOCOUNT ON;
        DECLARE @MergeOutput TABLE (ActionType NVARCHAR(10));
        
        MERGE GProjects AS Target
        USING {temp_table} AS Source
        ON Target.ProjectID = Source.ProjectID AND Target.SourceApp = Source.SourceApp -- <--- COMPOSITE KEY
        WHEN MATCHED THEN
            UPDATE SET 
                Target.ProjectCode = Source.ProjectCode,
                Target.ProjectName = Source.ProjectName,
                Target.TemplateID = Source.TemplateID,
                Target.CreationDate = Source.CreationDate
        WHEN NOT MATCHED BY TARGET THEN
            INSERT (ProjectID, SourceApp, ProjectCode, ProjectName, TemplateID, CreationDate)
            VALUES (Source.ProjectID, Source.SourceApp, Source.ProjectCode, Source.ProjectName, Source.TemplateID, Source.CreationDate)
        OUTPUT $action INTO @MergeOutput;
        
        SELECT 
            SUM(CASE WHEN ActionType = 'INSERT' THEN 1 ELSE 0 END) AS InsertedCount,
            SUM(CASE WHEN ActionType = 'UPDATE' THEN 1 ELSE 0 END) AS UpdatedCount
        FROM @MergeOutput;
        """
        
        result = conn.execute(text(merge_query)).fetchone()
        inserted_count = result[0] or 0
        updated_count = result[1] or 0
        conn.execute(text(f"DROP TABLE {temp_table}"))
        
    print(f"  -> Η εγγραφή ολοκληρώθηκε! Νέες εγγραφές (Inserted): {inserted_count} | Ενημερώθηκαν (Updated): {updated_count}")
    return inserted_count, updated_count

def upsert_users(df: pd.DataFrame, engine):
    temp_table = "GUsers_StagingTemp"

    dtypes = {
        'UserID': String(100),   # <--- ΑΛΛΑΓΗ ΣΕ STRING
        'SourceApp': String(50), # <--- Προστέθηκε
        'Username': String(150),
        'Firstname': String(150),
        'Surname': String(150),
        'Fullname': String(300),
        'Email': String(255),
        'APIKey': String(255),
        'Active': Boolean(),
        'CreationDate': DateTime()
    }

    print(f"  -> Ανέβασμα {len(df)} χρηστών σε προσωρινό πίνακα ({temp_table})...")
    
    with engine.begin() as conn:
        df.to_sql(name=temp_table, con=conn, if_exists='replace', index=False, dtype=dtypes)

        merge_query = f"""
        SET NOCOUNT ON;
        DECLARE @MergeOutput TABLE (ActionType NVARCHAR(10));
        
        MERGE GUsers AS Target
        USING {temp_table} AS Source
        ON Target.UserID = Source.UserID AND Target.SourceApp = Source.SourceApp -- <--- COMPOSITE KEY
        WHEN MATCHED THEN
            UPDATE SET 
                Target.Username = Source.Username,
                Target.Firstname = Source.Firstname,
                Target.Surname = Source.Surname,
                Target.Fullname = Source.Fullname,
                Target.Email = Source.Email,
                Target.APIKey = Source.APIKey,
                Target.Active = Source.Active,
                Target.CreationDate = Source.CreationDate
        WHEN NOT MATCHED BY TARGET THEN
            INSERT (UserID, SourceApp, Username, Firstname, Surname, Fullname, Email, APIKey, Active, CreationDate)
            VALUES (Source.UserID, Source.SourceApp, Source.Username, Source.Firstname, Source.Surname, Source.Fullname, Source.Email, Source.APIKey, Source.Active, Source.CreationDate)
        OUTPUT $action INTO @MergeOutput;
        
        SELECT 
            SUM(CASE WHEN ActionType = 'INSERT' THEN 1 ELSE 0 END) AS InsertedCount,
            SUM(CASE WHEN ActionType = 'UPDATE' THEN 1 ELSE 0 END) AS UpdatedCount
        FROM @MergeOutput;
        """
        
        result = conn.execute(text(merge_query)).fetchone()
        inserted_count = result[0] or 0
        updated_count = result[1] or 0
        conn.execute(text(f"DROP TABLE {temp_table}"))
        
    print(f"  -> Η εγγραφή (Users) ολοκληρώθηκε! Inserted: {inserted_count} | Updated: {updated_count}")
    return inserted_count, updated_count

def upsert_issues(df: pd.DataFrame, engine):
    temp_table = "GIssues_StagingTemp"

    dtypes = {
        'IssueID': Integer(),
        'SourceApp': String(50), # <--- Προστέθηκε
        'IssueKey': String(50),  # <--- Προστέθηκε
        'ProjectID': Integer(),
        'VersionID': Integer(),
        'Reporter': String(255),
        'Title': String(255),
        'Type': String(100),
        'Priority': String(100),
        'Severity': String(100),
        'Resolution': String(100),
        'Status': String(100),
        'CreationDate': DateTime(),
        'RevisedDate': DateTime(),
        'ClosedDate': DateTime(),
        'AffectedVersions': String(255),
        'Resources': String(255),
        'Components': String(255),
        'ImportedAt': DateTime()
    }

    print(f"  -> Ανέβασμα {len(df)} Issues σε προσωρινό πίνακα...")
    
    with engine.begin() as conn:
        df.to_sql(name=temp_table, con=conn, if_exists='replace', index=False, dtype=dtypes)

        merge_query = f"""
        SET NOCOUNT ON;
        DECLARE @MergeOutput TABLE (ActionType NVARCHAR(10));
        
        MERGE GIssues AS Target
        USING {temp_table} AS Source
        ON Target.IssueID = Source.IssueID AND Target.SourceApp = Source.SourceApp -- <--- COMPOSITE KEY
        WHEN MATCHED THEN
            UPDATE SET 
                Target.IssueKey = Source.IssueKey,
                Target.ProjectID = Source.ProjectID,
                Target.VersionID = Source.VersionID,
                Target.Reporter = Source.Reporter,
                Target.Title = Source.Title,
                Target.Type = Source.Type,
                Target.Priority = Source.Priority,
                Target.Severity = Source.Severity,
                Target.Resolution = Source.Resolution,
                Target.Status = Source.Status,
                Target.CreationDate = Source.CreationDate,
                Target.RevisedDate = Source.RevisedDate,
                Target.ClosedDate = Source.ClosedDate,
                Target.AffectedVersions = Source.AffectedVersions,
                Target.Resources = Source.Resources,
                Target.Components = Source.Components,
                Target.ImportedAt = Source.ImportedAt
        WHEN NOT MATCHED BY TARGET THEN
            INSERT (IssueID, SourceApp, IssueKey, ProjectID, VersionID, Reporter, Title, Type, Priority, Severity, Resolution, Status, CreationDate, RevisedDate, ClosedDate, AffectedVersions, Resources, Components, ImportedAt)
            VALUES (Source.IssueID, Source.SourceApp, Source.IssueKey, Source.ProjectID, Source.VersionID, Source.Reporter, Source.Title, Source.Type, Source.Priority, Source.Severity, Source.Resolution, Source.Status, Source.CreationDate, Source.RevisedDate, Source.ClosedDate, Source.AffectedVersions, Source.Resources, Source.Components, Source.ImportedAt)
        OUTPUT $action INTO @MergeOutput;
        
        SELECT 
            SUM(CASE WHEN ActionType = 'INSERT' THEN 1 ELSE 0 END) AS InsertedCount,
            SUM(CASE WHEN ActionType = 'UPDATE' THEN 1 ELSE 0 END) AS UpdatedCount
        FROM @MergeOutput;
        """
        
        result = conn.execute(text(merge_query)).fetchone()
        inserted_count = result[0] or 0
        updated_count = result[1] or 0
        conn.execute(text(f"DROP TABLE {temp_table}"))
        
    print(f"  -> Upsert Issues ολοκληρώθηκε! Inserted: {inserted_count} | Updated: {updated_count}")
    return inserted_count, updated_count

def upsert_components(df: pd.DataFrame, engine):
    temp_table = "GComponents_StagingTemp"

    dtypes = {
        'ComponentID': Integer(),
        'SourceApp': String(50), # <--- Προστέθηκε
        'ProjectID': Integer(),
        'ComponentName': String(255),
        'ComponentDesc': String(),
        'ParentID': Integer(),
        'CreationDate': DateTime()
    }

    print(f"  -> Ανέβασμα {len(df)} Components σε προσωρινό πίνακα...")
    with engine.begin() as conn:
        df.to_sql(name=temp_table, con=conn, if_exists='replace', index=False, dtype=dtypes)

        merge_query = f"""
        SET NOCOUNT ON;
        DECLARE @MergeOutput TABLE (ActionType NVARCHAR(10));
        
        MERGE GComponents AS Target
        USING {temp_table} AS Source
        ON Target.ComponentID = Source.ComponentID AND Target.SourceApp = Source.SourceApp -- <--- COMPOSITE KEY
        WHEN MATCHED THEN
            UPDATE SET 
                Target.ProjectID = Source.ProjectID,
                Target.ComponentName = Source.ComponentName,
                Target.ComponentDesc = Source.ComponentDesc,
                Target.ParentID = Source.ParentID,
                Target.CreationDate = Source.CreationDate
        WHEN NOT MATCHED BY TARGET THEN
            INSERT (ComponentID, SourceApp, ProjectID, ComponentName, ComponentDesc, ParentID, CreationDate)
            VALUES (Source.ComponentID, Source.SourceApp, Source.ProjectID, Source.ComponentName, Source.ComponentDesc, Source.ParentID, Source.CreationDate)
        OUTPUT $action INTO @MergeOutput;
        
        SELECT 
            SUM(CASE WHEN ActionType = 'INSERT' THEN 1 ELSE 0 END) AS InsertedCount,
            SUM(CASE WHEN ActionType = 'UPDATE' THEN 1 ELSE 0 END) AS UpdatedCount
        FROM @MergeOutput;
        """
        
        result = conn.execute(text(merge_query)).fetchone()
        inserted = result[0] or 0
        updated = result[1] or 0
        conn.execute(text(f"DROP TABLE {temp_table}"))
        
    print(f"  -> Upsert Components ολοκληρώθηκε! Inserted: {inserted} | Updated: {updated}")
    return inserted, updated

def upsert_comments(df: pd.DataFrame, engine):
    temp_table = "GComments_StagingTemp"

    dtypes = {
        'CommentID': Integer(),
        'SourceApp': String(50), # <--- Προστέθηκε
        'IssueID': Integer(),
        'ProjectID': Integer(),
        'UserID': String(100),   # <--- ΑΛΛΑΓΗ ΣΕ STRING
        'Fullname': String(255),
        'Comment': String(),
        'Created': DateTime()
    }

    print(f"  -> Ανέβασμα {len(df)} Comments σε προσωρινό πίνακα...")
    with engine.begin() as conn:
        df.to_sql(name=temp_table, con=conn, if_exists='replace', index=False, dtype=dtypes)

        merge_query = f"""
        SET NOCOUNT ON;
        DECLARE @MergeOutput TABLE (ActionType NVARCHAR(10));
        
        MERGE GComments AS Target
        USING {temp_table} AS Source
        ON Target.CommentID = Source.CommentID AND Target.SourceApp = Source.SourceApp -- <--- COMPOSITE KEY
        WHEN MATCHED THEN
            UPDATE SET 
                Target.IssueID = Source.IssueID,
                Target.ProjectID = Source.ProjectID,
                Target.UserID = Source.UserID,
                Target.Fullname = Source.Fullname,
                Target.Comment = Source.Comment,
                Target.Created = Source.Created
        WHEN NOT MATCHED BY TARGET THEN
            INSERT (CommentID, SourceApp, IssueID, ProjectID, UserID, Fullname, Comment, Created)
            VALUES (Source.CommentID, Source.SourceApp, Source.IssueID, Source.ProjectID, Source.UserID, Source.Fullname, Source.Comment, Source.Created)
        OUTPUT $action INTO @MergeOutput;
        
        SELECT 
            SUM(CASE WHEN ActionType = 'INSERT' THEN 1 ELSE 0 END) AS InsertedCount,
            SUM(CASE WHEN ActionType = 'UPDATE' THEN 1 ELSE 0 END) AS UpdatedCount
        FROM @MergeOutput;
        """
        
        result = conn.execute(text(merge_query)).fetchone()
        inserted = result[0] or 0
        updated = result[1] or 0
        conn.execute(text(f"DROP TABLE {temp_table}"))
        
    print(f"  -> Upsert Comments ολοκληρώθηκε! Inserted: {inserted} | Updated: {updated}")
    return inserted, updated

def upsert_audits(df: pd.DataFrame, engine):
    temp_table = "GAudit_StagingTemp"

    dtypes = {
        'AuditID': Integer(),
        'SourceApp': String(50), # <--- Προστέθηκε
        'IssueID': Integer(),
        'ProjectID': Integer(),
        'UserID': String(100),   # <--- ΑΛΛΑΓΗ ΣΕ STRING
        'Fullname': String(255),
        'Created': DateTime(),
        'FieldName': String(255),
        'OldValue': String(),
        'NewValue': String()
    }

    print(f"  -> Ανέβασμα {len(df)} Audits σε προσωρινό πίνακα...")
    with engine.begin() as conn:
        df.to_sql(name=temp_table, con=conn, if_exists='replace', index=False, dtype=dtypes)

        # To AuditID συχνά δεν είναι μοναδικό για SourceApp="Jira" (πολλαπλά items ανά history ID).
        # Αν το AuditID δεν είναι το PK, θα μπορούσαμε απλά να κάνουμε INSERT.
        # Εδώ το αφήνουμε ως έχει αν θεωρούμε ότι το (AuditID, SourceApp) ελέγχει τα conflicts.
        merge_query = f"""
        SET NOCOUNT ON;
        DECLARE @MergeOutput TABLE (ActionType NVARCHAR(10));
        
        MERGE GAudit AS Target
        USING {temp_table} AS Source
        ON Target.AuditID = Source.AuditID AND Target.SourceApp = Source.SourceApp -- <--- COMPOSITE KEY
        WHEN MATCHED THEN
            UPDATE SET 
                Target.IssueID = Source.IssueID,
                Target.ProjectID = Source.ProjectID,
                Target.UserID = Source.UserID,
                Target.Fullname = Source.Fullname,
                Target.Created = Source.Created,
                Target.FieldName = Source.FieldName,
                Target.OldValue = Source.OldValue,
                Target.NewValue = Source.NewValue
        WHEN NOT MATCHED BY TARGET THEN
            INSERT (AuditID, SourceApp, IssueID, ProjectID, UserID, Fullname, Created, FieldName, OldValue, NewValue)
            VALUES (Source.AuditID, Source.SourceApp, Source.IssueID, Source.ProjectID, Source.UserID, Source.Fullname, Source.Created, Source.FieldName, Source.OldValue, Source.NewValue)
        OUTPUT $action INTO @MergeOutput;
        
        SELECT 
            SUM(CASE WHEN ActionType = 'INSERT' THEN 1 ELSE 0 END) AS InsertedCount,
            SUM(CASE WHEN ActionType = 'UPDATE' THEN 1 ELSE 0 END) AS UpdatedCount
        FROM @MergeOutput;
        """
        
        result = conn.execute(text(merge_query)).fetchone()
        inserted = result[0] or 0
        updated = result[1] or 0
        conn.execute(text(f"DROP TABLE {temp_table}"))
        
    print(f"  -> Upsert Audits ολοκληρώθηκε! Inserted: {inserted} | Updated: {updated}")
    return inserted, updated

def upsert_custom_fields(df: pd.DataFrame, engine):
    temp_table = "GIssueCustomFields_StagingTemp"

    dtypes = {
        'IssueID': Integer(),
        'CustomFieldID': Integer(),
        'SourceApp': String(50), # <--- Προστέθηκε
        'CustomFieldName': String(255),
        'ProjectID': Integer(),
        'FieldValue': String()
    }

    print(f"  -> Ανέβασμα {len(df)} Custom Fields σε προσωρινό πίνακα...")
    with engine.begin() as conn:
        df.to_sql(name=temp_table, con=conn, if_exists='replace', index=False, dtype=dtypes)

        merge_query = f"""
        SET NOCOUNT ON;
        DECLARE @MergeOutput TABLE (ActionType NVARCHAR(10));
        
        MERGE GIssueCustomFields AS Target
        USING {temp_table} AS Source
        ON Target.IssueID = Source.IssueID AND Target.CustomFieldID = Source.CustomFieldID AND Target.SourceApp = Source.SourceApp -- <--- COMPOSITE KEY
        WHEN MATCHED THEN
            UPDATE SET 
                Target.CustomFieldName = Source.CustomFieldName,
                Target.ProjectID = Source.ProjectID,
                Target.FieldValue = Source.FieldValue
        WHEN NOT MATCHED BY TARGET THEN
            INSERT (IssueID, CustomFieldID, SourceApp, CustomFieldName, ProjectID, FieldValue)
            VALUES (Source.IssueID, Source.CustomFieldID, Source.SourceApp, Source.CustomFieldName, Source.ProjectID, Source.FieldValue)
        OUTPUT $action INTO @MergeOutput;
        
        SELECT 
            SUM(CASE WHEN ActionType = 'INSERT' THEN 1 ELSE 0 END) AS InsertedCount,
            SUM(CASE WHEN ActionType = 'UPDATE' THEN 1 ELSE 0 END) AS UpdatedCount
        FROM @MergeOutput;
        """
        
        result = conn.execute(text(merge_query)).fetchone()
        inserted = result[0] or 0
        updated = result[1] or 0
        conn.execute(text(f"DROP TABLE {temp_table}"))
        
    print(f"  -> Upsert Custom Fields ολοκληρώθηκε! Inserted: {inserted} | Updated: {updated}")
    return inserted, updated

def upsert_time_tracking(df: pd.DataFrame, engine):
    temp_table = "GTimeTracking_StagingTemp"

    dtypes = {
        'TimeEntryID': Integer(),
        'SourceApp': String(50), # <--- Προστέθηκε
        'IssueID': Integer(),
        'ProjectID': Integer(),
        'TimeEntryDate': DateTime(),
        'TimeCreationDate': DateTime(),
        'TimeResourceID': String(100),   # <--- ΑΛΛΑΓΗ ΣΕ STRING
        'TimeHours': Integer(),
        'TimeMinutes': Integer(),
        'TimeComment': String(),
        'TimeTypeID': Integer(),
        'TimeTypeName': String(255),
        'IssueComponent': String()
    }

    print(f"  -> Ανέβασμα {len(df)} Time Entries σε προσωρινό πίνακα...")
    with engine.begin() as conn:
        df.to_sql(name=temp_table, con=conn, if_exists='replace', index=False, dtype=dtypes)

        merge_query = f"""
        SET NOCOUNT ON;
        DECLARE @MergeOutput TABLE (ActionType NVARCHAR(10));
        
        MERGE GTimeTracking AS Target
        USING {temp_table} AS Source
        ON Target.TimeEntryID = Source.TimeEntryID AND Target.SourceApp = Source.SourceApp -- <--- COMPOSITE KEY
        WHEN MATCHED THEN
            UPDATE SET 
                Target.IssueID = Source.IssueID,
                Target.ProjectID = Source.ProjectID,
                Target.TimeEntryDate = Source.TimeEntryDate,
                Target.TimeCreationDate = Source.TimeCreationDate,
                Target.TimeResourceID = Source.TimeResourceID,
                Target.TimeHours = Source.TimeHours,
                Target.TimeMinutes = Source.TimeMinutes,
                Target.TimeComment = Source.TimeComment,
                Target.TimeTypeID = Source.TimeTypeID,
                Target.TimeTypeName = Source.TimeTypeName,
                Target.IssueComponent = Source.IssueComponent
        WHEN NOT MATCHED BY TARGET THEN
            INSERT (TimeEntryID, SourceApp, IssueID, ProjectID, TimeEntryDate, TimeCreationDate, TimeResourceID, TimeHours, TimeMinutes, TimeComment, TimeTypeID, TimeTypeName, IssueComponent)
            VALUES (Source.TimeEntryID, Source.SourceApp, Source.IssueID, Source.ProjectID, Source.TimeEntryDate, Source.TimeCreationDate, Source.TimeResourceID, Source.TimeHours, Source.TimeMinutes, Source.TimeComment, Source.TimeTypeID, Source.TimeTypeName, Source.IssueComponent)
        OUTPUT $action INTO @MergeOutput;
        
        SELECT 
            SUM(CASE WHEN ActionType = 'INSERT' THEN 1 ELSE 0 END) AS InsertedCount,
            SUM(CASE WHEN ActionType = 'UPDATE' THEN 1 ELSE 0 END) AS UpdatedCount
        FROM @MergeOutput;
        """
        
        result = conn.execute(text(merge_query)).fetchone()
        inserted = result[0] or 0
        updated = result[1] or 0
        conn.execute(text(f"DROP TABLE {temp_table}"))
        
    print(f"  -> Upsert Time Tracking ολοκληρώθηκε! Inserted: {inserted} | Updated: {updated}")
    return inserted, updated