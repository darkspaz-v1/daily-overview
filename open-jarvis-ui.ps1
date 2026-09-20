<#
  open-jarvis-ui.ps1  --  Opens the Jarvis UI (the Daily Overview desktop app).

  Used by the Shortcut Pad entry "Jarvis UI" and its Ctrl+Alt+J hotkey.

  overview_app.py has no single-instance guard of its own, so launching it blindly
  would stack a new pywebview window every time. This checks for a running instance
  first and just brings that window forward; only when none is found does it start
  a fresh one via run-app.ps1.
#>
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path

$existing = Get-CimInstance Win32_Process -Filter "Name='pythonw.exe' or Name='python.exe'" |
    Where-Object { $_.CommandLine -like '*overview_app*' } |
    Select-Object -First 1

if ($existing) {
    $proc = Get-Process -Id $existing.ProcessId -ErrorAction SilentlyContinue
    $hwnd = if ($proc) { $proc.MainWindowHandle } else { [IntPtr]::Zero }
    if ($hwnd -and $hwnd -ne [IntPtr]::Zero) {
        Add-Type -Namespace Win -Name Fg -MemberDefinition @'
[DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
[DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
[DllImport("user32.dll")] public static extern bool IsIconic(IntPtr hWnd);
'@
        # SW_RESTORE only if minimised - restoring a normal window would un-maximise it.
        if ([Win.Fg]::IsIconic($hwnd)) { [void][Win.Fg]::ShowWindow($hwnd, 9) }
        [void][Win.Fg]::SetForegroundWindow($hwnd)
        return
    }
    # Running but no window handle yet (still starting up) - leave it alone rather
    # than racing it with a second instance.
    return
}

Start-Process -FilePath 'powershell.exe' `
    -ArgumentList @('-NoProfile', '-WindowStyle', 'Hidden', '-ExecutionPolicy', 'Bypass',
                    '-File', "`"$(Join-Path $Root 'run-app.ps1')`"") `
    -WorkingDirectory $Root -WindowStyle Hidden
