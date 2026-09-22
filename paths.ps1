<#
  paths.ps1  --  shared path resolution (dot-source me: `. (Join-Path $PSScriptRoot 'paths.ps1')`).

  Every lookup follows the same order: environment variable -> found on PATH / next to
  the script -> a %USERPROFILE%-based default. Nothing here is specific to one PC.

    DAILY_OVERVIEW_PYTHON   full path to python.exe or pythonw.exe to use for the app
    CLAUDE_CLI              full path to claude.cmd for the weekly AI research
    SHORTSFORGE_DIR         the ShortsForge / "AI Agents" project folder
#>

function Resolve-PythonExe {
  # Returns @{ Python = <python.exe or $null>; Pythonw = <pythonw.exe or $null> }.
  $py = $null; $pyw = $null
  $envPy = $env:DAILY_OVERVIEW_PYTHON
  if ($envPy -and (Test-Path -LiteralPath $envPy)) {
    $dir = Split-Path -Parent $envPy
    $py  = Join-Path $dir 'python.exe'
    $pyw = Join-Path $dir 'pythonw.exe'
  } else {
    $c = Get-Command pythonw.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($c) { $pyw = $c.Source; $py = Join-Path (Split-Path -Parent $c.Source) 'python.exe' }
    else {
      # Fall back to the py launcher and ask it where Python 3 lives.
      $launcher = Get-Command py.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
      if ($launcher) {
        try {
          $exe = (& $launcher.Source -3 -c 'import sys; print(sys.executable)' 2>$null | Select-Object -First 1)
          if ($exe -and (Test-Path -LiteralPath $exe)) {
            $py  = $exe
            $pyw = Join-Path (Split-Path -Parent $exe) 'pythonw.exe'
          }
        } catch { Write-Verbose "py launcher could not resolve Python 3: $($_.Exception.Message)" }
      }
    }
    if (-not $py) {
      $c = Get-Command python.exe -CommandType Application -ErrorAction SilentlyContinue |
           Where-Object { $_.Source -notlike '*\WindowsApps\*' } | Select-Object -First 1
      if ($c) { $py = $c.Source; $pyw = Join-Path (Split-Path -Parent $c.Source) 'pythonw.exe' }
    }
  }
  if ($py  -and -not (Test-Path -LiteralPath $py))  { $py  = $null }
  if ($pyw -and -not (Test-Path -LiteralPath $pyw)) { $pyw = $null }
  return @{ Python = $py; Pythonw = $pyw }
}

function Resolve-ShortsForgeDir {
  if ($env:SHORTSFORGE_DIR) { return $env:SHORTSFORGE_DIR }
  return (Join-Path $env:USERPROFILE 'AI Agents')
}

function Resolve-ClaudeCli {
  # Returns the path to claude.cmd, or $null when the CLI can't be found.
  if ($env:CLAUDE_CLI -and (Test-Path -LiteralPath $env:CLAUDE_CLI)) { return $env:CLAUDE_CLI }
  $c = Get-Command claude.cmd -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($c) { return $c.Source }
  $fallback = Join-Path $env:APPDATA 'npm\claude.cmd'
  if (Test-Path -LiteralPath $fallback) { return $fallback }
  return $null
}
