-- 1. Ρόλοι Χρηστών (1 χρήστης = 1 ρόλος, π.χ. Admin ή User)
CREATE TABLE User_Roles (
    RoleID INT IDENTITY(1,1) PRIMARY KEY,
    RoleName NVARCHAR(50) NOT NULL UNIQUE
);

-- 2. Ομάδες Χρηστών
CREATE TABLE User_Groups (
    GroupID INT IDENTITY(1,1) PRIMARY KEY,
    GroupName NVARCHAR(100) NOT NULL UNIQUE
);

-- 3. Πίνακας Χρηστών (σύνδεση με GroupID)
CREATE TABLE Users (
    UserID INT IDENTITY(1,1) PRIMARY KEY,
    Username NVARCHAR(100) NOT NULL UNIQUE,
    PasswordHash NVARCHAR(255) NOT NULL,
	Email NVARCHAR(100) NOT NULL UNIQUE,
    RoleID INT NOT NULL,
    DefaultProject NVARCHAR(100) NULL,
    DisplayName NVARCHAR(255) NULL,
    IsActive BIT DEFAULT 1,
    CreatedAt DATETIME DEFAULT GETDATE(),
    
    CONSTRAINT FK_Users_Roles FOREIGN KEY (RoleID) REFERENCES User_Roles(RoleID)
);

-- 4. Πίνακας μελών ομάδων (συσχέτιση χρηστών και ομάδων)
CREATE TABLE User_Group_Memberships (
    UserID INT NOT NULL,
    GroupID INT NOT NULL,
    AssignedAt DATETIME DEFAULT GETDATE(),
    
    -- Composite Primary Key: διασφαλίζει ότι ένας χρήστης δεν θα μπει στο ίδιο group πάνω από μία φορά
    PRIMARY KEY (UserID, GroupID), 
    CONSTRAINT FK_Membership_User FOREIGN KEY (UserID) REFERENCES Users(UserID) ON DELETE CASCADE,
    CONSTRAINT FK_Membership_Group FOREIGN KEY (GroupID) REFERENCES User_Groups(GroupID) ON DELETE CASCADE
);

-- 5. Presets Φίλτρων ανά Χρήστη
CREATE TABLE User_Presets (
    PresetID INT IDENTITY(1,1) PRIMARY KEY,
    UserID INT NOT NULL,
    PresetName NVARCHAR(150) NOT NULL,
    FiltersJSON NVARCHAR(MAX) NOT NULL,
    CreatedAt DATETIME DEFAULT GETDATE(),
    
    CONSTRAINT FK_Presets_Users FOREIGN KEY (UserID) REFERENCES Users(UserID) ON DELETE CASCADE
);

-- 6. Συνεδρίες Χρηστών (Sessions για Remember Me)
CREATE TABLE User_Sessions (
    SessionID NVARCHAR(100) PRIMARY KEY,
    UserID INT NOT NULL,
    ExpiresAt DATETIME NOT NULL,
    CONSTRAINT FK_Sessions_Users FOREIGN KEY (UserID) REFERENCES Users(UserID) ON DELETE CASCADE
);

-- 7. Πίνακας Καταγραφής Χρόνων (WorkLogs)
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

-- 8. Μεταδεδομένα Συγχρονισμού (Sync Metadata)
CREATE TABLE Sync_Metadata (
    LastSyncDateTime DATETIME
);

-- 9. Ενιαίος πίνακας για Ανακοινώσεις και Pro Tips
CREATE TABLE ContentHub (
    ContentID INT IDENTITY(1,1) PRIMARY KEY,
    Title NVARCHAR(255) NOT NULL,
    Body NVARCHAR(MAX) NOT NULL,          -- Markdown κείμενο
    ContentType NVARCHAR(50) NOT NULL,   -- 'Announcement' ή 'ProTip'
    IsActive BIT NOT NULL DEFAULT 1,
    UserID INT NOT NULL,                  -- Ο δημιουργός (Admin/Team Leader)
    CreatedAt DATETIME DEFAULT GETDATE(),
    CONSTRAINT FK_ContentHub_Users FOREIGN KEY (UserID) REFERENCES Users(UserID)
);

-- 10. Πίνακας για τη Βάση Γνώσης (Εσωτερικές Διαδικασίες)
CREATE TABLE KBArticles (
    ArticleID INT IDENTITY(1,1) PRIMARY KEY,
    Title NVARCHAR(255) NOT NULL,
    Category NVARCHAR(100) NOT NULL,     -- π.χ. Διαδικασίες Jira, Onboarding, Υποστήριξη
    Content NVARCHAR(MAX) NOT NULL,      -- Markdown κείμενο
    IsActive BIT NOT NULL DEFAULT 1,
    UserID INT NOT NULL,
    CreatedAt DATETIME DEFAULT GETDATE(),
    CONSTRAINT FK_KBArticles_Users FOREIGN KEY (UserID) REFERENCES Users(UserID)
);
