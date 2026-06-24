import enum
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, LargeBinary, Enum, Text, Boolean
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.schema import FetchedValue

Base = declarative_base()

class SyncLogTypeEnum(enum.IntEnum):
    Info = 0
    Error = 1
    Summary = 2
    Detail = 3

class SyncMetadata(Base):
    __tablename__ = 'SyncMetadata' 

    Id = Column(Integer, primary_key=True, autoincrement=True)
    EntityName = Column(String, nullable=False, default="")
    LastSyncAt = Column(DateTime, nullable=False)

class SyncLog(Base):
    __tablename__ = 'SyncLog'

    ID = Column(Integer, primary_key=True, autoincrement=True)
    EntityName = Column(String, nullable=False)
    StartedAt = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    FinishedAt = Column(DateTime, nullable=True)
    Inserted = Column(Integer, nullable=True)
    Updated = Column(Integer, nullable=True)
    Failed = Column(Integer, nullable=True)
    Total = Column(Integer, nullable=True)
    Status = Column(String, nullable=True)
    LogFilePath = Column(String, nullable=True)
    
    RowVersion = Column(LargeBinary, server_default=FetchedValue(), server_onupdate=FetchedValue())
    Details = relationship("SyncLogDetail", back_populates="SyncLog", cascade="all, delete-orphan")

class SyncLogDetail(Base):
    __tablename__ = 'SyncLogDetails'

    ID = Column(Integer, primary_key=True, autoincrement=True)
    SyncLogID = Column(Integer, ForeignKey('SyncLog.ID'), nullable=False)
    RecordID = Column(String, nullable=False)
    ErrorMessage = Column(Text, nullable=True)
    Message = Column(Text, nullable=True)
    StackTrace = Column(Text, nullable=True)
    
    LogType = Column(Enum(SyncLogTypeEnum), nullable=False, default=SyncLogTypeEnum.Info)
    OccuredAt = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    
    RowVersion = Column(LargeBinary, server_default=FetchedValue(), server_onupdate=FetchedValue())
    SyncLog = relationship("SyncLog", back_populates="Details")

# --- STAGING/BUSINESS ΠΙΝΑΚΕΣ ---

class StagingProject(Base):
    __tablename__ = 'GProjects'

    ProjectID = Column(Integer, primary_key=True, autoincrement=False)
    SourceApp = Column(String(50), primary_key=True, nullable=False, default="Gemini")
    
    ProjectCode = Column(String, nullable=True)
    ProjectName = Column(String, nullable=True)
    TemplateID = Column(Integer, nullable=False, default=0)
    CreationDate = Column(DateTime, nullable=False)
    RowVersion = Column(LargeBinary, server_default=FetchedValue(), server_onupdate=FetchedValue())

class StagingUser(Base):
    __tablename__ = 'GUsers'

    # Το UserID γίνεται String για να χωράει το Jira accountId
    UserID = Column(String(100), primary_key=True)
    SourceApp = Column(String(50), primary_key=True, nullable=False, default="Gemini")
    
    Username = Column(String(150), nullable=True)
    Firstname = Column(String(150), nullable=True)
    Surname = Column(String(150), nullable=True)
    Fullname = Column(String(300), nullable=True)
    Email = Column(String(255), nullable=True)
    APIKey = Column(String(255), nullable=True)
    Active = Column(Boolean, nullable=False, default=True)
    CreationDate = Column(DateTime, nullable=False)
    RowVersion = Column(LargeBinary, server_default=FetchedValue(), server_onupdate=FetchedValue())

class StagingIssue(Base):
    __tablename__ = 'GIssues'

    IssueID = Column(Integer, primary_key=True, autoincrement=False)
    SourceApp = Column(String(50), primary_key=True, nullable=False, default="Gemini")
    
    # Νέο πεδίο: Το κοινό Business Key (π.χ. PROJ-123)
    IssueKey = Column(String(50), nullable=True)
    
    ProjectID = Column(Integer, nullable=False)
    VersionID = Column(Integer, nullable=True)
    Reporter = Column(String(255), nullable=True)
    Title = Column(String(255), nullable=False)
    Type = Column(String(100), nullable=True)
    Priority = Column(String(100), nullable=True)
    Severity = Column(String(100), nullable=True)
    Resolution = Column(String(100), nullable=True)
    Status = Column(String(100), nullable=True)
    Assignee = Column(String(100), nullable=True)
    CreationDate = Column(DateTime, nullable=False)
    RevisedDate = Column(DateTime, nullable=True)
    ClosedDate = Column(DateTime, nullable=True)
    RowVersion = Column(LargeBinary, server_default=FetchedValue(), server_onupdate=FetchedValue())
    AffectedVersions = Column(String(255), nullable=True)
    Resources = Column(String(255), nullable=True)
    Components = Column(String(255), nullable=True)
    ImportedAt = Column(DateTime, nullable=True, default=lambda: datetime.now(timezone.utc))

class StagingComponent(Base):
    __tablename__ = 'GComponents'

    ComponentID = Column(Integer, primary_key=True, autoincrement=False)
    SourceApp = Column(String(50), primary_key=True, nullable=False, default="Gemini")
    
    ProjectID = Column(Integer, nullable=False)
    ComponentName = Column(String(255), nullable=False)
    ComponentDesc = Column(String(None), nullable=True) 
    ParentID = Column(Integer, nullable=True)
    CreationDate = Column(DateTime, nullable=False)
    RowVersion = Column(LargeBinary, server_default=FetchedValue(), server_onupdate=FetchedValue())

class StagingComment(Base):
    __tablename__ = 'GComments'

    ID = Column(Integer, primary_key=True, autoincrement=True) 
    CommentID = Column(Integer, nullable=False)
    SourceApp = Column(String(50), nullable=False, default="Gemini")
    
    IssueID = Column(Integer, nullable=False)
    ProjectID = Column(Integer, nullable=False)
    
    # Γίνεται String(100) για να συμβαδίζει με τον πίνακα GUsers
    UserID = Column(String(100), nullable=False)
    
    Fullname = Column(String(255), nullable=True)
    Comment = Column(String(None), nullable=True) 
    Created = Column(DateTime, nullable=False)

class StagingAudit(Base):
    __tablename__ = 'GAudit'

    ID = Column(Integer, primary_key=True, autoincrement=True) 
    AuditID = Column(Integer, nullable=False)
    SourceApp = Column(String(50), nullable=False, default="Gemini")
    
    IssueID = Column(Integer, nullable=False)
    ProjectID = Column(Integer, nullable=False)
    
    # Γίνεται String(100) για να συμβαδίζει με τον πίνακα GUsers
    UserID = Column(String(100), nullable=True)
    
    Fullname = Column(String(255), nullable=True)
    Created = Column(DateTime, nullable=False)
    FieldName = Column(String(255), nullable=True)
    OldValue = Column(String(None), nullable=True) 
    NewValue = Column(String(None), nullable=True)

class StagingCustomField(Base):
    __tablename__ = 'GIssueCustomFields'

    IssueID = Column(Integer, primary_key=True, autoincrement=False)
    CustomFieldID = Column(Integer, primary_key=True, autoincrement=False)
    SourceApp = Column(String(50), primary_key=True, nullable=False, default="Gemini")
    
    CustomFieldName = Column(String(255), nullable=True)
    ProjectID = Column(Integer, nullable=False)
    FieldValue = Column(String(None), nullable=True) 

class StagingTracking(Base):
    __tablename__ = 'GTimeTracking'

    TimeEntryID = Column(Integer, primary_key=True, autoincrement=False)
    SourceApp = Column(String(50), primary_key=True, nullable=False, default="Gemini")
    
    IssueID = Column(Integer, nullable=False)
    ProjectID = Column(Integer, nullable=False)
    TimeEntryDate = Column(DateTime, nullable=False)
    TimeCreationDate = Column(DateTime, nullable=False)
    TimeResourceID = Column(Integer, nullable=False)
    TimeHours = Column(Integer, nullable=False, default=0)
    TimeMinutes = Column(Integer, nullable=False, default=0)
    TimeComment = Column(String(None), nullable=True) 
    TimeTypeID = Column(Integer, nullable=True)
    TimeTypeName = Column(String(255), nullable=True)
    IssueComponent = Column(String(None), nullable=True)