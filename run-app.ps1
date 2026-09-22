<#
  run-app.ps1  --  Launches the Daily Overview desktop app.

  Starts overview_app.py in a native window (pywebview) with the embedded local-AI
  assistant. The app itself refreshes the data on launch, so this just starts it.
  Uses pythonw.exe so there is no console window.

  Fires automatically at logon via the "Daily Overview" Startup shortcut, or
  double-click "Daily Overview.cmd".
#>
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$app  = Join-Path $Root 'overview_app.py'
. (Join-Path $Root 'paths.ps1')
$pyInfo = Resolve-PythonExe
$exe    = if ($pyInfo.Pythonw) { $pyInfo.Pythonw } else { $pyInfo.Python }
if (-not $exe) { throw 'Python 3 not found. Install it, or set DAILY_OVERVIEW_PYTHON to the full path of python.exe.' }
Start-Process -FilePath $exe -ArgumentList @("`"$app`"") -WorkingDirectory $Root

# Kick off the daily money-opportunities research in the background (hidden).
# It self-guards to once per day, so extra logons in the same day are no-ops.
try {
  $money = Join-Path $Root 'run-money-research.ps1'
  if (Test-Path $money) {
    Start-Process -FilePath 'powershell.exe' `
      -ArgumentList @('-NoProfile','-WindowStyle','Hidden','-ExecutionPolicy','Bypass','-File',"`"$money`"") `
      -WorkingDirectory $Root -WindowStyle Hidden
  }
} catch { Write-Verbose "Could not start background money research: $($_.Exception.Message)" }

# Kick off the weekly AI research in the background (hidden).
# It self-guards to once per week (week-of-Monday stamped, regardless of which
# day the scheduled task itself fires on), so extra logons the same week are
# no-ops. Also fires from the "Weekly AI Research" scheduled task (Fridays).
try {
  $aiResearch = Join-Path $Root 'run-ai-research.ps1'
  if (Test-Path $aiResearch) {
    Start-Process -FilePath 'powershell.exe' `
      -ArgumentList @('-NoProfile','-WindowStyle','Hidden','-ExecutionPolicy','Bypass','-File',"`"$aiResearch`"") `
      -WorkingDirectory $Root -WindowStyle Hidden
  }
} catch { Write-Verbose "Could not start background AI research: $($_.Exception.Message)" }
