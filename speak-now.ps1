<#
  speak-now.ps1  --  "Hear Jarvis now" on demand.

  Reads today's briefing (latest.json -> summary) and speaks it immediately,
  independent of whether the Daily Overview app window is open. Same voice
  engine as overview_app.py's Api.speak(): edge-tts first, offline Windows
  SAPI as a fallback. No console window (launched via speak-now.vbs).

  Triggered by: the "Speak Jarvis Briefing" entry in the Shortcut Pad, or its
  own global hotkey (Ctrl+Alt+J, see launcher\config.json / launcher\app.py).
#>
$ErrorActionPreference = 'Continue'
$Root    = $PSScriptRoot
if (-not $Root) { $Root = 'C:\Users\anshu\Desktop\Claude\daily-overview' }
$Latest  = Join-Path $Root 'latest.json'
$Layout  = Join-Path $Root 'layout.json'
$Mp3     = Join-Path $Root '_speaknow.mp3'
$PyDir   = 'C:\Users\anshu\AppData\Local\Programs\Python\Python313'
$Edge    = Join-Path $PyDir 'Scripts\edge-tts.exe'
$DefaultVoice = 'en-GB-RyanNeural'

if (-not (Test-Path $Latest)) {
  # No briefing generated yet -- refresh it once so there's something to say.
  try { & powershell -ExecutionPolicy Bypass -File (Join-Path $Root 'daily-overview.ps1') -Quiet | Out-Null } catch {}
}
if (-not (Test-Path $Latest)) { exit }

$text = ''
try {
  $data = Get-Content $Latest -Raw -Encoding UTF8 | ConvertFrom-Json
  $text = [string]$data.summary
} catch {}
if (-not $text) { $text = 'Systems online. No briefing available right now.' }

$voice = $DefaultVoice
if (Test-Path $Layout) {
  try {
    $st = Get-Content $Layout -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($st.voice) { $voice = [string]$st.voice }
  } catch {}
}

function Play-Mp3Blocking([string]$path) {
  Add-Type -AssemblyName PresentationCore
  $player = New-Object System.Windows.Media.MediaPlayer
  $player.Open([uri]$path)
  # MediaPlayer loads/plays async; poll for a resolved duration, then sleep it out.
  $waited = 0
  while (-not $player.NaturalDuration.HasTimeSpan -and $waited -lt 5000) { Start-Sleep -Milliseconds 100; $waited += 100 }
  $player.Play()
  if ($player.NaturalDuration.HasTimeSpan) {
    Start-Sleep -Milliseconds ([int]$player.NaturalDuration.TimeSpan.TotalMilliseconds + 300)
  } else {
    Start-Sleep -Seconds 8   # duration never resolved -- best-effort wait
  }
  $player.Close()
}

$spoke = $false
try {
  if (Test-Path $Edge) {
    if (Test-Path $Mp3) { Remove-Item $Mp3 -Force -ErrorAction SilentlyContinue }
    & $Edge --voice $voice --rate=+6% --text $text --write-media $Mp3 2>$null | Out-Null
    if ((Test-Path $Mp3) -and (Get-Item $Mp3).Length -gt 0) {
      Play-Mp3Blocking $Mp3
      $spoke = $true
    }
  }
} catch {}

if (-not $spoke) {
  # Offline fallback: native Windows SAPI voice, blocking.
  try {
    Add-Type -AssemblyName System.Speech
    $synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
    $synth.Speak($text)
  } catch {}
}
