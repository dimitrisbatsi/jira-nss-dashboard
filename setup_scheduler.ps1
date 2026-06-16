# NSS Timesheet App Task Scheduler Setup
# ----------------------------------------------------
# Αυτό το script δημιουργεί αυτόματα τα 3 Scheduled Tasks στα Windows Task Scheduler
# για το υβριδικό μοντέλο συγχρονισμού των Jira Worklogs με τον SQL Server.
#
# ΣΗΜΑΝΤΙΚΟ: Τρέξτε αυτό το script σε ένα PowerShell παράθυρο ως Administrator!

# Έλεγχος αν εκτελείται ως Administrator
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Warning "⚠️ Παρακαλώ τρέξτε το PowerShell ως Administrator για να καταχωρηθούν τα tasks!"
    Exit
}

$workingDir = "c:\Users\d.batsilis\OneDrive - Epsilon Net S.A\Development\NSSTimesheetApp"

# Εύρεση της διαδρομής του python.exe
$pythonPath = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $pythonPath) {
    $pythonPath = "python.exe"
    Write-Host "⚠️ Το python.exe δεν βρέθηκε στο PATH, χρησιμοποιείται το fallback 'python.exe'." -ForegroundColor Yellow
} else {
    Write-Host "✅ Βρέθηκε το Python: $pythonPath" -ForegroundColor Green
}

# 1. Ορισμός των Actions
Write-Host "⚙️ Δημιουργία Actions..." -ForegroundColor Cyan
$actionIncremental = New-ScheduledTaskAction -Execute $pythonPath -Argument "--mode incremental --days 7" -WorkingDirectory $workingDir
$actionFull        = New-ScheduledTaskAction -Execute $pythonPath -Argument "--mode full" -WorkingDirectory $workingDir

# 2. Ορισμός των Triggers
Write-Host "⚙️ Δημιουργία Triggers..." -ForegroundColor Cyan

# Trigger 1: Καθημερινές (Δευτέρα-Παρασκευή), 9:00 πμ έως 6:00 μμ, κάθε 15 λεπτά
$trigger1 = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At 9:00am
$trigger1.RepetitionInterval = (New-TimeSpan -Minutes 15)
$trigger1.RepetitionDuration = (New-TimeSpan -Hours 9)

# Trigger 2: Καθημερινές (Δευτέρα-Παρασκευή), 6:00 μμ έως 12:00 πμ, κάθε 1 ώρα
$trigger2 = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At 6:00pm
$trigger2.RepetitionInterval = (New-TimeSpan -Hours 1)
$trigger2.RepetitionDuration = (New-TimeSpan -Hours 6)

# Trigger 3: Σαββατοκύριακο (Σάββατο-Κυριακή), 6:00 πμ, μία φορά τη μέρα (Full Sync)
$trigger3 = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Saturday,Sunday -At 6:00am

# 3. Ορισμός Task Settings (Όριο χρόνου εκτέλεσης 1 ώρα, εκτέλεση και σε μπαταρία)
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Hours 1) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

# 4. Καταχώρηση των Tasks
Write-Host "💾 Καταχώρηση Tasks στο σύστημα..." -ForegroundColor Cyan

# Task 1: Incremental Business Hours
Register-ScheduledTask -TaskName "NSS_Timesheet_Sync_Incremental_BusinessHours" `
                       -Trigger $trigger1 `
                       -Action $actionIncremental `
                       -Settings $settings `
                       -Description "Runs incremental sync from Jira to SQL Server every 15 minutes between 9 AM and 6 PM on weekdays." `
                       -Force | Out-Null
Write-Host "  -> Task 1 καταχωρήθηκε: NSS_Timesheet_Sync_Incremental_BusinessHours" -ForegroundColor Green

# Task 2: Incremental Evening Hours
Register-ScheduledTask -TaskName "NSS_Timesheet_Sync_Incremental_EveningHours" `
                       -Trigger $trigger2 `
                       -Action $actionIncremental `
                       -Settings $settings `
                       -Description "Runs incremental sync from Jira to SQL Server every hour between 6 PM and 12 AM on weekdays." `
                       -Force | Out-Null
Write-Host "  -> Task 2 καταχωρήθηκε: NSS_Timesheet_Sync_Incremental_EveningHours" -ForegroundColor Green

# Task 3: Weekend Full Sync
Register-ScheduledTask -TaskName "NSS_Timesheet_Sync_Full_Weekend" `
                       -Trigger $trigger3 `
                       -Action $actionFull `
                       -Settings $settings `
                       -Description "Runs full sync (Truncate & Reload) from Jira to SQL Server at 6 AM on Saturdays and Sundays." `
                       -Force | Out-Null
Write-Host "  -> Task 3 καταχωρήθηκε: NSS_Timesheet_Sync_Full_Weekend" -ForegroundColor Green

Write-Host "🏁 Η δημιουργία των Tasks ολοκληρώθηκε επιτυχώς!" -ForegroundColor Green
