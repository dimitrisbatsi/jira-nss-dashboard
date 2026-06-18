from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional

class ProjectSchema(BaseModel):
    """Το κοινό σχήμα για Projects, ανεξαρτήτως αν έρχονται από Jira ή Gemini"""
    ProjectID: int
    SourceApp: str = "Gemini" # Προστέθηκε
    ProjectCode: str = Field(..., max_length=50)
    ProjectName: str
    TemplateID: int = 0  
    CreationDate: datetime

class UserSchema(BaseModel):
    """Το Pydantic Schema για τον StagingUser"""
    UserID: str # ΑΛΛΑΓΗ σε String (για να χωράει τα Jira accountIds)
    SourceApp: str = "Gemini" # Προστέθηκε
    Username: str = ""
    Firstname: str = ""
    Surname: Optional[str] = None
    Fullname: str = ""
    Email: str = ""
    APIKey: str = ""
    Active: bool = True
    CreationDate: datetime

class IssueSchema(BaseModel):
    """Το Pydantic Schema για τον πίνακα GIssues"""
    IssueID: int
    SourceApp: str = "Gemini" # Προστέθηκε
    IssueKey: Optional[str] = None # Προστέθηκε το Business Key
    ProjectID: int
    VersionID: Optional[int] = None
    Reporter: Optional[str] = ""
    Title: str = Field(..., max_length=255)
    Type: Optional[str] = ""
    Priority: Optional[str] = ""
    Severity: Optional[str] = ""
    Resolution: Optional[str] = ""
    Status: Optional[str] = ""
    CreationDate: datetime
    RevisedDate: Optional[datetime] = None
    ClosedDate: Optional[datetime] = None
    AffectedVersions: Optional[str] = Field(None, max_length=255)
    Resources: Optional[str] = Field(None, max_length=255)
    Components: Optional[str] = Field(None, max_length=255)
    ImportedAt: datetime

class ComponentSchema(BaseModel):
    """Το Pydantic Schema για τον πίνακα GComponents"""
    ComponentID: int
    SourceApp: str = "Gemini" # Προστέθηκε
    ProjectID: int
    ComponentName: str
    ComponentDesc: Optional[str] = None
    ParentID: Optional[int] = None
    CreationDate: datetime

class CommentSchema(BaseModel):
    """Το Pydantic Schema για τα GComments"""
    CommentID: int
    SourceApp: str = "Gemini" # Προστέθηκε
    IssueID: int
    ProjectID: int
    UserID: str # ΑΛΛΑΓΗ σε String
    Fullname: Optional[str] = ""
    Comment: Optional[str] = ""
    Created: datetime

class AuditSchema(BaseModel):
    """Το Pydantic Schema για τα GAudits"""
    AuditID: int
    SourceApp: str = "Gemini" # Προστέθηκε
    IssueID: int
    ProjectID: int
    UserID: Optional[str] = None # ΑΛΛΑΓΗ σε String
    Fullname: Optional[str] = ""
    Created: datetime
    FieldName: Optional[str] = ""
    OldValue: Optional[str] = ""
    NewValue: Optional[str] = ""

class CustomFieldSchema(BaseModel):
    """Το Pydantic Schema για τα GIssueCustomFields"""
    IssueID: int
    CustomFieldID: int
    SourceApp: str = "Gemini" # Προστέθηκε
    CustomFieldName: Optional[str] = ""
    ProjectID: int
    FieldValue: Optional[str] = ""

class TimeTrackingSchema(BaseModel):
    """Το Pydantic Schema για το GTimeTracking"""
    TimeEntryID: int
    SourceApp: str = "Gemini"
    IssueID: int
    ProjectID: int
    TimeEntryDate: datetime
    TimeCreationDate: datetime
    TimeResourceID: str # <--- ΑΛΛΑΓΗ σε str για να χωράει το accountId του Jira!
    TimeHours: int
    TimeMinutes: int
    TimeComment: Optional[str] = None
    TimeTypeID: Optional[int] = None
    TimeTypeName: Optional[str] = None
    IssueComponent: Optional[str] = None