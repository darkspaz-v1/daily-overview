<#
  run-money-research.ps1  --  daily wrapper

  1. Runs money-research.ps1  (fetch + rank + enrich -> opportunities.json)
  2. Runs daily-overview.ps1  (folds opportunities into latest.js for the dashboard)

  Runs once a day. Fires from two places (whichever happens first wins; the
  once-per-day stamp stops the other from repeating the work):
    * the "Daily Money Research" scheduled task (8:00 AM), and
    * at logon, launched in the background by run-app.ps1.
  Logs to money\run.log. Use -Force to run again the same day.
#>
param([switch]$Force)
$ErrorActionPreference = 'Continue'
# Resolve our own folder robustly: $PSScriptRoot works under Task Scheduler (-File);
# fall back to the known install path if anything is odd.
$Root = $PSScriptRoot
if (-not $Root -and $MyInvocation.MyCommand.Path) { $Root = Split-Path -Parent $MyInvocation.MyCommand.Path }
if (-not $Root -or -not (Test-Path (Join-Path $Root 'money-research.ps1'))) { $Root = 'C:\Users\anshu\Desktop\Claude\daily-overview' }
$Log  = Join-Path $Root 'money\run.log'
New-Item -ItemType Directory -Force (Join-Path $Root 'money') | Out-Null

function Note($m) { "$([DateTime]::Now.ToString('yyyy-MM-dd HH:mm:ss'))  $m" | Out-File -FilePath $Log -Append -Encoding utf8 }

# ---- once-per-day guard ----
$Stamp = Join-Path $Root 'money\last-run.txt'
$Today = [DateTime]::Now.ToString('yyyy-MM-dd')
if (-not $Force -and (Test-Path $Stamp) -and ((Get-Content $Stamp -Raw).Trim() -eq $Today)) {
  Note "skip: already ran today ($Today). Use -Force to override."
  return
}

Note '=== run-money-research start ==='
try {
  & powershell -ExecutionPolicy Bypass -File (Join-Path $Root 'money-research.ps1') -Quiet
  Note "money-research.ps1 exit=$LASTEXITCODE"
} catch { Note "money-research ERROR: $($_.Exception.Message)" }

try {
  & powershell -ExecutionPolicy Bypass -File (Join-Path $Root 'daily-overview.ps1') -Quiet
  Note "daily-overview.ps1 exit=$LASTEXITCODE"
} catch { Note "daily-overview ERROR: $($_.Exception.Message)" }

$Today | Out-File -FilePath $Stamp -Encoding utf8
Note '=== run-money-research done ==='
