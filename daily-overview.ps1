<#
  daily-overview.ps1  --  Daily Overview engine

  Produces:
    * overviews\YYYY-MM-DD.md + latest.md   (human-readable briefing)
    * latest.json                            (structured data for the app + a spoken summary)

    Sections: weather (location auto-detected from public IP), today's tasks/schedule
    (from planner.md), and ShortsForge (AI Agents) project status.

  Usage:
    powershell -ExecutionPolicy Bypass -File daily-overview.ps1 [-Notify] [-Open] [-Quiet]

  Source is intentionally ASCII-only so Windows PowerShell 5.1 runs it verbatim;
  emoji / symbols are built at runtime.
#>
param(
  [switch]$Notify,
  [switch]$Open,
  [switch]$Quiet
)

$ErrorActionPreference = 'Stop'
try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch {}

$Root        = Split-Path -Parent $MyInvocation.MyCommand.Path
$PlannerPath = Join-Path $Root 'planner.md'
$OutDir      = Join-Path $Root 'overviews'
$ProjectDir  = 'C:\Users\anshu\AI Agents'
$Now         = Get-Date
$TodayIso    = $Now.ToString('yyyy-MM-dd')
New-Item -ItemType Directory -Force $OutDir | Out-Null

# ---------- helpers ----------
function U([int]$cp) { [char]::ConvertFromUtf32($cp) }   # emoji from code point (keeps source ASCII)
$deg = [char]0x00B0
function Rnd($n) { [math]::Round([double]$n) }
function Clean($s) { ($s -replace '\*','' -replace '_','').Trim() }

function Weather-Desc([int]$c) {
  switch ($c) {
    0 {'Clear sky'} 1 {'Mainly clear'} 2 {'Partly cloudy'} 3 {'Overcast'}
    45 {'Fog'} 48 {'Depositing rime fog'}
    51 {'Light drizzle'} 53 {'Drizzle'} 55 {'Dense drizzle'}
    56 {'Freezing drizzle'} 57 {'Dense freezing drizzle'}
    61 {'Light rain'} 63 {'Rain'} 65 {'Heavy rain'}
    66 {'Freezing rain'} 67 {'Heavy freezing rain'}
    71 {'Light snow'} 73 {'Snow'} 75 {'Heavy snow'} 77 {'Snow grains'}
    80 {'Light showers'} 81 {'Showers'} 82 {'Violent showers'}
    85 {'Snow showers'} 86 {'Heavy snow showers'}
    95 {'Thunderstorm'} 96 {'Thunderstorm w/ light hail'} 99 {'Thunderstorm w/ heavy hail'}
    default {"Weather code $c"}
  }
}
function Weather-Kind([int]$c) {
  if     ($c -eq 0)                 { 'clear' }
  elseif ($c -le 2)                 { 'partly' }
  elseif ($c -eq 3)                 { 'cloudy' }
  elseif ($c -eq 45 -or $c -eq 48)  { 'fog' }
  elseif ($c -ge 51 -and $c -le 67) { 'rain' }
  elseif ($c -ge 71 -and $c -le 77) { 'snow' }
  elseif ($c -ge 80 -and $c -le 82) { 'rain' }
  elseif ($c -ge 85 -and $c -le 86) { 'snow' }
  elseif ($c -ge 95)                { 'storm' }
  else                              { 'clear' }
}
function Weather-Emoji([string]$kind) {
  switch ($kind) {
    'clear'  { U 0x2600 } 'partly' { U 0x26C5 } 'cloudy' { U 0x2601 }
    'fog'    { U 0x1F32B } 'rain'  { U 0x1F327 } 'snow'   { U 0x2744 }
    'storm'  { U 0x26C8 } default  { U 0x1F321 }
  }
}

# ================= WEATHER =================
$Wx = [ordered]@{ ok = $false }
$weatherBlock = ''
try {
  $lat = $null; $lon = $null; $place = $null
  try {
    $geo = Invoke-RestMethod 'https://ipinfo.io/json' -TimeoutSec 15
    if ($geo.loc) { $lat,$lon = $geo.loc -split ','; $place = (@($geo.city,$geo.region,$geo.country) | Where-Object { $_ }) -join ', ' }
  } catch {}
  if (-not $lat) {
    $g2 = Invoke-RestMethod 'http://ip-api.com/json/' -TimeoutSec 15
    $lat = $g2.lat; $lon = $g2.lon
    $place = (@($g2.city,$g2.regionName,$g2.country) | Where-Object { $_ }) -join ', '
  }
  $url = "https://api.open-meteo.com/v1/forecast?latitude=$lat&longitude=$lon&current=temperature_2m,apparent_temperature,weather_code,wind_speed_10m,relative_humidity_2m&hourly=temperature_2m,apparent_temperature,precipitation_probability,precipitation,weather_code&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code,sunrise,sunset&timezone=auto&forecast_days=7"
  $w = Invoke-RestMethod $url -TimeoutSec 15
  $c = $w.current; $d = $w.daily
  $code = [int]$c.weather_code
  $kind = Weather-Kind $code
  $desc = Weather-Desc $code
  $sr = ([datetime]$d.sunrise[0]).ToString('HH:mm')
  $ss = ([datetime]$d.sunset[0]).ToString('HH:mm')
  $Wx = [ordered]@{
    ok = $true; place = $place; desc = $desc; kind = $kind; code = $code
    temp = (Rnd $c.temperature_2m); feels = (Rnd $c.apparent_temperature)
    hi = (Rnd $d.temperature_2m_max[0]); lo = (Rnd $d.temperature_2m_min[0])
    rain = [int]$d.precipitation_probability_max[0]; wind = (Rnd $c.wind_speed_10m)
    humidity = [int]$c.relative_humidity_2m; sunrise = $sr; sunset = $ss
  }
  # ---- 7-day daily forecast (for "what's it like on Friday") ----
  $fc = New-Object System.Collections.ArrayList
  for ($i = 0; $i -lt @($d.time).Count; $i++) {
    $fdt = [datetime]$d.time[$i]; $fcode = [int]$d.weather_code[$i]
    [void]$fc.Add([ordered]@{
      date = $fdt.ToString('yyyy-MM-dd'); dow = $fdt.ToString('ddd')
      hi = (Rnd $d.temperature_2m_max[$i]); lo = (Rnd $d.temperature_2m_min[$i])
      rain = [int]$d.precipitation_probability_max[$i]; code = $fcode; desc = (Weather-Desc $fcode)
      sunrise = ([datetime]$d.sunrise[$i]).ToString('HH:mm'); sunset = ([datetime]$d.sunset[$i]).ToString('HH:mm')
    })
  }
  $Wx.forecast = $fc

  # ---- hourly forecast, 7 days (for "at 3pm" and "when will it rain") ----
  $hr = New-Object System.Collections.ArrayList
  $hh = $w.hourly
  if ($hh -and $hh.time) {
    for ($i = 0; $i -lt @($hh.time).Count; $i++) {
      [void]$hr.Add([ordered]@{
        t = ([datetime]$hh.time[$i]).ToString('yyyy-MM-ddTHH:mm')
        temp = (Rnd $hh.temperature_2m[$i]); feels = (Rnd $hh.apparent_temperature[$i])
        rain = [int]$hh.precipitation_probability[$i]; precip = [double]$hh.precipitation[$i]
        code = [int]$hh.weather_code[$i]
      })
    }
  }
  $Wx.hourly = $hr

  $emoji = Weather-Emoji $kind
  $weatherBlock = @"
$emoji **$place** - $desc, **$($Wx.temp)$deg C** (feels $($Wx.feels)$deg C)
- High $($Wx.hi)$deg / Low $($Wx.lo)$deg C  -  Rain chance $($Wx.rain)%
- Wind $($Wx.wind) km/h  -  Humidity $($Wx.humidity)%  -  Sunrise $sr / Sunset $ss
"@
} catch {
  $Wx = [ordered]@{ ok = $false }
  $weatherBlock = "_Weather unavailable right now ($($_.Exception.Message))_"
}

# ================= TASKS / SCHEDULE =================
$recurring     = New-Object System.Collections.ArrayList
$schedToday    = New-Object System.Collections.ArrayList
$schedUpcoming = New-Object System.Collections.ArrayList
$tasksDueToday = New-Object System.Collections.ArrayList
$tasksOverdue  = New-Object System.Collections.ArrayList
$tasksOpen     = New-Object System.Collections.ArrayList

if (Test-Path $PlannerPath) {
  $section = ''
  foreach ($raw in (Get-Content $PlannerPath -Encoding UTF8)) {
    if ($raw -match '^\s*##\s*(.+?)\s*$') { $section = $Matches[1]; continue }
    $t = $raw.Trim()
    if ($t -eq '' -or $t.StartsWith('#')) { continue }

    if ($section -match 'Recurring') {
      if ($t -match '^-\s*\[( )\]\s*(.+)$')      { [void]$recurring.Add($Matches[2].Trim()) }
      elseif ($t -match '^-\s*\[[xX]\]')          { }
      elseif ($t -match '^-\s*(.+)$')             { [void]$recurring.Add($Matches[1].Trim()) }
    }
    elseif ($section -match 'Scheduled') {
      if ($t -match '^-\s*(\d{4}-\d{2}-\d{2})(?:\s+(\d{1,2}:\d{2}))?\s+(.+)$') {
        $date = $Matches[1]; $time = $Matches[2]; $what = $Matches[3].Trim()
        if ($date -eq $TodayIso) {
          [void]$schedToday.Add( ($(if ($time) { "$time - " } else { '' }) + $what) )
        } elseif (([datetime]$date).Date -gt $Now.Date -and (([datetime]$date).Date - $Now.Date).Days -le 7) {
          [void]$schedUpcoming.Add( ("$date " + $(if ($time) { "$time " } else { '' }) + $what).Trim() )
        }
      }
    }
    elseif ($section -match 'Task') {
      if ($t -match '^-\s*\[( )\]\s*(.+)$') {
        $body = $Matches[2].Trim(); $due = $null
        if ($body -match '\(due:\s*(\d{4}-\d{2}-\d{2})\)') { $due = $Matches[1]; $body = ($body -replace '\s*\(due:\s*\d{4}-\d{2}-\d{2}\)','').Trim() }
        if ($due) {
          if ($due -eq $TodayIso)                      { [void]$tasksDueToday.Add($body) }
          elseif (([datetime]$due).Date -lt $Now.Date) { [void]$tasksOverdue.Add("$body (was due $due)") }
          else                                         { [void]$tasksOpen.Add("$body (due $due)") }
        } else { [void]$tasksOpen.Add($body) }
      }
    }
  }
}
$openTaskCount = $tasksOverdue.Count + $tasksDueToday.Count + $tasksOpen.Count

# markdown for tasks
$sb = New-Object System.Text.StringBuilder
function Add-Line($s) { [void]$sb.AppendLine($s) }
function Add-List($items) { foreach ($i in $items) { [void]$sb.AppendLine("- $i") } }
if (-not (Test-Path $PlannerPath)) {
  Add-Line "_No planner.md found next to the script - create one to track tasks._"
} else {
  $any = $false
  if ($tasksOverdue.Count)  { Add-Line "**$(U 0x1F534) Overdue**";        Add-List $tasksOverdue;  Add-Line ''; $any = $true }
  if ($schedToday.Count)    { Add-Line "**$(U 0x1F4C5) Scheduled today**"; Add-List $schedToday;    Add-Line ''; $any = $true }
  if ($tasksDueToday.Count) { Add-Line "**$(U 0x2757) Due today**";        Add-List $tasksDueToday; Add-Line ''; $any = $true }
  if ($recurring.Count)     { Add-Line "**$(U 0x1F501) Daily routine**";   Add-List $recurring;     Add-Line ''; $any = $true }
  if ($tasksOpen.Count)     { Add-Line "**$(U 0x1F4CB) Open tasks**";      Add-List $tasksOpen;     Add-Line ''; $any = $true }
  if ($schedUpcoming.Count) { Add-Line "**$(U 0x1F52D) Next 7 days**";     Add-List $schedUpcoming; Add-Line ''; $any = $true }
  if (-not $any) { Add-Line "_Nothing on the planner for today. Enjoy the clear deck._" }
}
$tasksBlock = $sb.ToString().TrimEnd()

# ================= PROJECT STATUS: ShortsForge =================
$Pj = $null
$projBlock = ''
try {
  if (Test-Path $ProjectDir) {
    $outputDir = Join-Path $ProjectDir 'output'
    $projects = @()
    if (Test-Path $outputDir) { $projects = @(Get-ChildItem $outputDir -Directory -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending) }
    $skip = '\\(\.venv|__pycache__|\.pytest_cache|\.git|models|node_modules)\\'
    $recent = @(Get-ChildItem $ProjectDir -Recurse -File -ErrorAction SilentlyContinue |
      Where-Object { $_.LastWriteTime -gt $Now.AddDays(-3) -and $_.FullName -notmatch $skip } |
      Sort-Object LastWriteTime -Descending)
    $ollamaUp = $false
    try { $null = Invoke-RestMethod 'http://localhost:11434/api/tags' -TimeoutSec 3; $ollamaUp = $true } catch {}

    $recentList = @()
    foreach ($p in ($projects | Select-Object -First 3)) {
      $files  = @(Get-ChildItem $p.FullName -Recurse -File -ErrorAction SilentlyContinue)
      $hasMp4 = [bool]($files | Where-Object { $_.Extension -eq '.mp4' })
      $hasVo  = [bool]($files | Where-Object { $_.Name -match 'voiceover' -or $_.Extension -eq '.mp3' })
      $stage  = if ($hasMp4) { 'rendered video' } elseif ($hasVo) { 'voiceover done' } elseif ($files | Where-Object { $_.Name -eq 'scenes.json' }) { 'scenes planned' } elseif ($files | Where-Object { $_.Name -eq 'script.json' }) { 'script only' } else { 'started' }
      $recentList += ,([ordered]@{ name = $p.Name; stage = $stage; updated = $p.LastWriteTime.ToString('MMM d, HH:mm') })
    }
    $activityList = @()
    foreach ($f in ($recent | Select-Object -First 6)) {
      $rel = $f.FullName.Substring($ProjectDir.Length).TrimStart('\')
      $activityList += ,([ordered]@{ path = $rel; when = $f.LastWriteTime.ToString('MMM d, HH:mm') })
    }
    $Pj = [ordered]@{ projectCount = $projects.Count; recentCount = $recent.Count; ollamaUp = $ollamaUp; recent = $recentList; activity = $activityList }

    $pb = New-Object System.Text.StringBuilder
    [void]$pb.AppendLine("**$($projects.Count)** video project(s) in output/  -  **$($recent.Count)** file(s) touched in the last 3 days  -  Ollama: $(if ($ollamaUp) { 'up' } else { 'DOWN' })")
    if ($recentList.Count) {
      [void]$pb.AppendLine(''); [void]$pb.AppendLine('Most recent projects:')
      foreach ($r in $recentList) { [void]$pb.AppendLine("- **$($r.name)** - $($r.stage)  _(updated $($r.updated))_") }
    }
    if ($activityList.Count) {
      [void]$pb.AppendLine(''); [void]$pb.AppendLine('Recent activity:')
      foreach ($a in $activityList) { [void]$pb.AppendLine("- $($a.path)  _($($a.when))_") }
    }
    $projBlock = $pb.ToString().TrimEnd()
  } else {
    $projBlock = "_Project folder not found at $ProjectDir_"
  }
} catch {
  $projBlock = "_Could not read project status ($($_.Exception.Message))_"
}

# ================= MONEY OPPORTUNITIES (from money-research.ps1) =================
$Opp = $null
try {
  $oppPath = Join-Path $Root 'opportunities.json'
  if (Test-Path $oppPath) {
    $Opp = Get-Content $oppPath -Raw -Encoding UTF8 | ConvertFrom-Json
  }
} catch { $Opp = $null }

# ================= AI RESEARCH (from run-ai-research.ps1, weekly) =================
$AiR = $null
try {
  $airPath = Join-Path $Root 'ai-research\latest.json'
  if (Test-Path $airPath) {
    $AiR = Get-Content $airPath -Raw -Encoding UTF8 | ConvertFrom-Json
  }
} catch { $AiR = $null }

# ================= SPOKEN SUMMARY =================
$hour = $Now.Hour
$tod  = if ($hour -lt 12) { 'morning' } elseif ($hour -lt 17) { 'afternoon' } else { 'evening' }
$parts = New-Object System.Collections.ArrayList
[void]$parts.Add("Good $tod. Here's your overview for $($Now.ToString('dddd, MMMM d')).")
if ($Wx.ok) {
  $imp = switch ($Wx.kind) {
    'rain'  { ' Rain is likely, so it might be a good day to record indoors.' }
    'storm' { ' Thunderstorms are expected, best to stay in.' }
    'snow'  { ' Snow is expected, so bundle up.' }
    'clear' { ' Clear skies, a nice day to get outside.' }
    default { '' }
  }
  [void]$parts.Add("The weather in $($Wx.place) is $($Wx.desc.ToLower()), $($Wx.temp) degrees, feeling like $($Wx.feels), with a high of $($Wx.hi) and a low of $($Wx.lo).$imp")
} else {
  [void]$parts.Add("Weather data isn't available right now.")
}
if ($openTaskCount -eq 0 -and $schedToday.Count -eq 0) {
  [void]$parts.Add("Your task list is clear today.")
} else {
  $bits = New-Object System.Collections.ArrayList
  if ($tasksOverdue.Count)  { [void]$bits.Add("$($tasksOverdue.Count) overdue") }
  if ($tasksDueToday.Count) { [void]$bits.Add("$($tasksDueToday.Count) due today") }
  if ($schedToday.Count)    { [void]$bits.Add("$($schedToday.Count) scheduled") }
  if ($tasksOpen.Count)     { [void]$bits.Add("$($tasksOpen.Count) open") }
  if ($bits.Count) { [void]$parts.Add("On tasks, you have " + ($bits -join ', ') + ".") }
  if ($tasksOverdue.Count)      { [void]$parts.Add("Most urgent is the overdue item: $(Clean $tasksOverdue[0]).") }
  elseif ($schedToday.Count)    { [void]$parts.Add("First on your schedule: $(Clean $schedToday[0]).") }
  elseif ($tasksDueToday.Count) { [void]$parts.Add("Due today: $(Clean $tasksDueToday[0]).") }
}
if ($Pj) {
  $health = if ($Pj.ollamaUp) { 'and Ollama is running' } else { 'but Ollama is down, which the pipeline needs' }
  if ($Pj.recent.Count) {
    $r0 = @($Pj.recent)[0]
    [void]$parts.Add("On your ShortsForge project, the latest video is $($r0.name), currently at $($r0.stage), $health.")
  } else {
    [void]$parts.Add("Your ShortsForge project has no videos in progress yet, $health.")
  }
}
if ($Opp -and $Opp.count -gt 0) {
  $fc = @($Opp.freelance).Count
  if ($fc -gt 0) {
    $top = @($Opp.freelance)[0]
    [void]$parts.Add("On the money front, I found $($Opp.count) opportunities to look at, including a role: $(Clean $top.title) at $(Clean $top.org).")
  } else {
    [void]$parts.Add("On the money front, I put together $($Opp.count) ideas and signals for you to review.")
  }
}
if ($AiR -and $AiR.headline) {
  $airAgeDays = 999
  try { $airAgeDays = [int]((New-TimeSpan -Start ([datetime]$AiR.generatedAt) -End $Now).TotalDays) } catch {}
  if ($airAgeDays -le 8) {
    [void]$parts.Add("This week's AI research: $(Clean $AiR.headline)")
  }
}
if ($openTaskCount -gt 0 -or $schedToday.Count -gt 0) {
  [void]$parts.Add("You've a few things on today, so I'm standing by. Just say the word if you need a hand.")
} else {
  [void]$parts.Add("Your day looks clear. At your service whenever you need me.")
}
$summary = ($parts -join ' ')

# ================= ASSEMBLE MARKDOWN =================
$hdr = $Now.ToString('dddd, MMMM d, yyyy')
$md = @"
# $(U 0x2600) Daily Overview - $hdr

## $(U 0x1F324) Weather
$weatherBlock

## $(U 0x2705) Today's Tasks & Schedule
$tasksBlock

## $(U 0x1F3AC) ShortsForge Project
$projBlock

## $(U 0x1F4B0) Money Opportunities
$(if ($Opp -and $Opp.count -gt 0) {
  $ob = New-Object System.Text.StringBuilder
  [void]$ob.AppendLine("_$($Opp.count) items - brain: $($Opp.brain). Research only; you decide and act. Full list in [opportunities.md](opportunities.md)._")
  if (@($Opp.freelance).Count) {
    [void]$ob.AppendLine(''); [void]$ob.AppendLine('**Top gigs matched to you:**')
    foreach ($f in @($Opp.freelance | Select-Object -First 4)) { [void]$ob.AppendLine("- $($f.title) @ $($f.org)") }
  }
  $ob.ToString().TrimEnd()
} else { "_No opportunities yet - run money-research.ps1 (or wait for the daily task)._" })

## $(U 0x1F9E0) AI Research (weekly)
$(if ($AiR -and $AiR.headline) {
  $ab = New-Object System.Text.StringBuilder
  [void]$ab.AppendLine("_Generated $($AiR.generatedAt). $($AiR.headline)_")
  if (@($AiR.highlights).Count) {
    [void]$ab.AppendLine(''); [void]$ab.AppendLine('**This week:**')
    foreach ($h in @($AiR.highlights)) { [void]$ab.AppendLine("- **$($h.title)** - $($h.summary)") }
  }
  if ($AiR.reportFile) { [void]$ab.AppendLine(''); [void]$ab.AppendLine("Full report: [ai-research/$($AiR.reportFile)](ai-research/$($AiR.reportFile))") }
  $ab.ToString().TrimEnd()
} else { "_No AI research yet - run run-ai-research.ps1 (or wait for Monday's task)._" })

---
_Generated $($Now.ToString('yyyy-MM-dd HH:mm')) by daily-overview.ps1. Edit tasks in [planner.md](planner.md)._
"@

$todayFile = Join-Path $OutDir "$TodayIso.md"
$latestMd  = Join-Path $Root 'latest.md'
$md | Out-File -FilePath $todayFile -Encoding utf8
$md | Out-File -FilePath $latestMd  -Encoding utf8

# ================= CHANNEL PERFORMANCE =================
$Ch = [ordered]@{ ok = $false; count = 0; videos = @(); pending = @() }
try {
  $agRoot = 'C:\Users\anshu\AI Agents'
  $perfFile = Join-Path $agRoot 'performance\videos.json'
  $vids = @()
  if (Test-Path $perfFile) {
    $obj = Get-Content $perfFile -Raw -Encoding UTF8 | ConvertFrom-Json
    foreach ($p in $obj.PSObject.Properties) {
      $v = $p.Value
      $pct = 0.0; if ($null -ne $v.avg_pct) { $pct = [double]$v.avg_pct }
      $vids += ,([ordered]@{
        slug    = $p.Name
        title   = [string]$v.title
        views   = [int]$v.views
        avgPct  = $pct
        likePct = $v.like_pct
        runtime = $v.runtime
        scenes  = $v.scenes
      })
    }
  }
  # Shorts that were produced but never logged (the 48h rule)
  $pending = @()
  $shortsDir = Join-Path $agRoot 'shorts'
  if (Test-Path $shortsDir) {
    foreach ($f in (Get-ChildItem $shortsDir -Directory -ErrorAction SilentlyContinue)) {
      $already = $false
      foreach ($vv in $vids) { if ($vv.slug -eq $f.Name) { $already = $true; break } }
      if (-not $already -and (Test-Path (Join-Path $f.FullName 'metadata.txt'))) {
        $pending += ,([ordered]@{
          slug = $f.Name
          age  = [int]((New-TimeSpan -Start $f.LastWriteTime -End $Now).TotalDays)
        })
      }
    }
  }
  $sorted = @($vids | Sort-Object -Property avgPct -Descending)
  $avgPct = 0; $totalViews = 0
  if ($vids.Count -gt 0) {
    $avgPct = [math]::Round((($vids | Measure-Object -Property avgPct -Average).Average), 1)
    $totalViews = [int](($vids | Measure-Object -Property views -Sum).Sum)
  }
  $Ch = [ordered]@{
    ok = $true; count = $vids.Count; avgPct = $avgPct
    totalViews = $totalViews; videos = $sorted; pending = @($pending)
  }
} catch { $Ch = [ordered]@{ ok = $false; count = 0; videos = @(); pending = @() } }

# ================= WRITE JSON (for the app) =================
$data = [ordered]@{
  generatedAt = $Now.ToString('yyyy-MM-dd HH:mm')
  dateHeading = $hdr
  greeting    = "Good $tod"
  weather     = $Wx
  tasks       = [ordered]@{
    overdue        = @($tasksOverdue  | ForEach-Object { Clean $_ })
    scheduledToday = @($schedToday    | ForEach-Object { Clean $_ })
    dueToday       = @($tasksDueToday | ForEach-Object { Clean $_ })
    recurring      = @($recurring     | ForEach-Object { Clean $_ })
    open           = @($tasksOpen     | ForEach-Object { Clean $_ })
    upcoming       = @($schedUpcoming | ForEach-Object { Clean $_ })
    openCount      = $openTaskCount
  }
  project = $Pj
  opportunities = $Opp
  aiResearch = $AiR
  channel = $Ch
  summary = $summary
}
$json = $data | ConvertTo-Json -Depth 10
$json | Out-File -FilePath (Join-Path $Root 'latest.json') -Encoding utf8
# Also emit as JS so dashboard.html can load it from file:// without a web server.
"window.DAILY_DATA = $json;" | Out-File -FilePath (Join-Path $Root 'latest.js') -Encoding utf8

if (-not $Quiet) { Write-Output $md }

if ($Notify) {
  try {
    Add-Type -AssemblyName System.Windows.Forms
    $balloon = New-Object System.Windows.Forms.NotifyIcon
    $balloon.Icon = [System.Drawing.SystemIcons]::Information
    $balloon.BalloonTipTitle = "Daily Overview - $openTaskCount open task(s)"
    $balloon.BalloonTipText  = if ($Wx.ok) { "$($Wx.place): $($Wx.desc) $($Wx.temp)$deg C" } else { "Tap to view your day" }
    $balloon.Visible = $true
    $balloon.ShowBalloonTip(10000)
    Start-Sleep -Seconds 8
    $balloon.Dispose()
  } catch {}
}
if ($Open) { try { Invoke-Item $todayFile } catch {} }
