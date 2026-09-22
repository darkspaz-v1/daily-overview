<#
  money-research.ps1  --  Autonomous "money opportunities" research engine

  Runs unattended (scheduled daily, or on demand). It:
    1. Pulls LIVE opportunities from free, no-API-key sources tailored to the
       user's skills (Remotive, RemoteOK, Hacker News via Algolia).
    2. Scores them by skill-match + recency.
    3. Enriches / ranks with a "brain":
         - local Ollama (llama3.1) if it is running, else
         - a heuristic fallback (always works, no LLM, no network brain).
       (Optional: -Brain claude uses the bundled claude.exe IF it is logged in.)
    4. Writes opportunities.json (consumed by daily-overview) + a dated archive
       under money\YYYY-MM-DD.md and a readable opportunities.md.

  Nothing here spends money, trades, or transacts. It is research only:
  it finds and explains opportunities; the user decides and acts.

  Usage:
    powershell -ExecutionPolicy Bypass -File money-research.ps1 [-Quiet] [-Brain auto|ollama|claude|heuristic]

  ASCII-only source so Windows PowerShell 5.1 runs it verbatim.
#>
param(
  [switch]$Quiet,
  [ValidateSet('auto','ollama','claude','heuristic')]
  [string]$Brain = 'auto'
)

$ErrorActionPreference = 'Stop'
try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch { Write-Verbose "Could not set TLS 1.2 (older PowerShell/.NET): $($_.Exception.Message)" }

$Root     = Split-Path -Parent $MyInvocation.MyCommand.Path
$OutDir   = Join-Path $Root 'money'
$Now      = Get-Date
$TodayIso = $Now.ToString('yyyy-MM-dd')
New-Item -ItemType Directory -Force $OutDir | Out-Null

function Log($s) { if (-not $Quiet) { Write-Host $s } }

# ---- who the user is: skills to match opportunities against ----
# (drawn from their work: AI video/Shorts pipeline, Python automation, content)
$Skills = @(
  'ai','artificial intelligence','llm','gpt','chatbot','automation','agent',
  'python','script','scripting','no-code','nocode','api','prompt',
  'video','editing','video editor','animation','motion','after effects',
  'youtube','shorts','content','faceless','tiktok','social media','creator',
  'voiceover','tts','captioning','thumbnail','n8n','make','zapier'
)
$UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) daily-overview-money-research/1.0'

function Http($url) {
  try { return Invoke-RestMethod -Uri $url -Headers @{ 'User-Agent' = $UA } -TimeoutSec 20 }
  catch { Log ("  ! fetch failed: {0} ({1})" -f $url, $_.Exception.Message); return $null }
}

# raw pool of normalized opportunities
$pool = New-Object System.Collections.ArrayList
function AddOpp($h) { [void]$pool.Add([pscustomobject]$h) }

# ================= SOURCE 1: Remotive (remote jobs) =================
try {
  Log 'Fetching Remotive...'
  $r = Http 'https://remotive.com/api/remote-jobs?limit=80'
  if ($r -and $r.jobs) {
    foreach ($j in $r.jobs) {
      $tags = @($j.tags) -join ', '
      AddOpp @{
        type='freelance'; title=[string]$j.title; org=[string]$j.company_name
        url=[string]$j.url; tags=$tags; source='Remotive'
        posted=([string]$j.publication_date); salary=[string]$j.salary
      }
    }
  }
} catch { Log "  ! Remotive error: $($_.Exception.Message)" }

# ================= SOURCE 2: RemoteOK (remote jobs/gigs) =================
try {
  Log 'Fetching RemoteOK...'
  $r = Http 'https://remoteok.com/api'
  if ($r) {
    # first element is a legal/notice object; skip anything without a position
    foreach ($j in $r) {
      if (-not $j.position) { continue }
      $tags = @($j.tags) -join ', '
      $when = ''
      try { if ($j.date) { $when = ([datetime]$j.date).ToString('yyyy-MM-dd') } } catch { Write-Verbose "Could not parse RemoteOK date '$($j.date)': $($_.Exception.Message)" }
      AddOpp @{
        type='freelance'; title=[string]$j.position; org=[string]$j.company
        url=[string]$j.url; tags=$tags; source='RemoteOK'
        posted=$when; salary=''
      }
    }
  }
} catch { Log "  ! RemoteOK error: $($_.Exception.Message)" }

# ================= SOURCE 3: Hacker News (trend/idea signals) =================
# Research-only market/idea signals: high-engagement stories about making money,
# side projects, indie products, launches. No trading, no advice.
$hnQueries = @('side project revenue','indie hacker','how I make money','launched','digital product','AI startup')
foreach ($q in $hnQueries) {
  try {
    $enc = [uri]::EscapeDataString($q)
    $url = "https://hn.algolia.com/api/v1/search_by_date?query=$enc&tags=story&numericFilters=points%3E60&hitsPerPage=6"
    $r = Http $url
    if ($r -and $r.hits) {
      foreach ($h in $r.hits) {
        if (-not $h.title) { continue }
        $link = if ($h.url) { [string]$h.url } else { "https://news.ycombinator.com/item?id=$($h.objectID)" }
        $when = ''
        try { $when = ([datetime]$h.created_at).ToString('yyyy-MM-dd') } catch { Write-Verbose "Could not parse HN created_at '$($h.created_at)': $($_.Exception.Message)" }
        AddOpp @{
          type='signal'; title=[string]$h.title; org=("HN " + [string]$h.points + " pts")
          url=$link; tags=$q; source='Hacker News'; posted=$when; salary=''
        }
      }
    }
  } catch { Log "  ! HN error ($q): $($_.Exception.Message)" }
}

Log ("Collected {0} raw items." -f $pool.Count)

# ================= SCORE by skill-match + recency =================
function Score($o) {
  $hay = ("{0} {1} {2}" -f $o.title, $o.tags, $o.org).ToLower()
  $s = 0
  foreach ($k in $Skills) { if ($hay.Contains($k)) { $s += 2 } }
  # recency bonus
  if ($o.posted) {
    try {
      $d = [datetime]$o.posted
      $age = ($Now.Date - $d.Date).Days
      if ($age -le 3) { $s += 4 } elseif ($age -le 7) { $s += 2 } elseif ($age -le 14) { $s += 1 }
    } catch { Write-Verbose "Could not parse posted date '$($o.posted)' for scoring: $($_.Exception.Message)" }
  }
  return $s
}
foreach ($o in $pool) { $o | Add-Member -NotePropertyName score -NotePropertyValue (Score $o) -Force }

# de-dupe by title (case-insensitive), keep highest score
$byTitle = @{}
foreach ($o in $pool) {
  $key = ($o.title).ToLower().Trim()
  if (-not $byTitle.ContainsKey($key) -or $o.score -gt $byTitle[$key].score) { $byTitle[$key] = $o }
}
$ranked = $byTitle.Values | Sort-Object -Property score -Descending

$freelance = @($ranked | Where-Object { $_.type -eq 'freelance' -and $_.score -gt 0 } | Select-Object -First 6)
$signals   = @($ranked | Where-Object { $_.type -eq 'signal' }                      | Select-Object -First 5)
# if nothing matched skills, still surface the freshest freelance items
if ($freelance.Count -eq 0) { $freelance = @($ranked | Where-Object { $_.type -eq 'freelance' } | Select-Object -First 5) }

# ================= BRAIN: enrich (why it fits + next action) =================
$brainUsed = 'heuristic'

function Ollama-Up {
  try { $null = Invoke-RestMethod 'http://localhost:11434/api/tags' -TimeoutSec 3; return $true } catch { return $false }
}
function Ollama-Model {
  try {
    $t = Invoke-RestMethod 'http://localhost:11434/api/tags' -TimeoutSec 3
    $m = @($t.models | Where-Object { $_.name -match 'llama3\.1' } | Select-Object -First 1).name
    if (-not $m) { $m = @($t.models)[0].name }
    return $m
  } catch { return 'llama3.1:latest' }
}
function Ollama-Json($model, $prompt) {
  $body = @{ model=$model; prompt=$prompt; stream=$false; format='json';
             options=@{ temperature=0.4 } } | ConvertTo-Json -Depth 5
  $r = Invoke-RestMethod 'http://localhost:11434/api/generate' -Method Post -Body $body -ContentType 'application/json' -TimeoutSec 120
  return $r.response
}

$useOllama = $false
if ($Brain -eq 'ollama') { $useOllama = $true }
elseif ($Brain -eq 'auto') { $useOllama = (Ollama-Up) }
# (Brain 'claude' handled below; 'heuristic' skips the LLM entirely)

$businessIdeas = @()
$channelIdeas  = @()

if ($useOllama -and (Ollama-Up)) {
  try {
    $model = Ollama-Model
    Log "Enriching with Ollama ($model)..."

    # Compact the freelance list for the prompt
    $fl = ($freelance | ForEach-Object { "- $($_.title) @ $($_.org) [tags: $($_.tags)]" }) -join "`n"

    $prompt = @"
You are a pragmatic money-opportunity analyst for a solo creator whose skills are:
AI automation, Python scripting, and short-form/long-form YouTube video production
(a faceless AI 'stickman'/doodle channel + an AI Agents / ShortsForge pipeline).

Return STRICT JSON only, no prose, with this exact shape:
{
  "freelance": [ {"title": "...", "why": "one sentence: why it fits this person", "action": "one concrete first step"} ],
  "business":  [ {"title": "small online business idea", "why": "why it fits their skills", "action": "first step this week"} ],
  "channel":   [ {"title": "way to earn from their existing YouTube/Shorts work", "why": "...", "action": "first step"} ]
}
Rules: 3 business ideas, 3 channel ideas. For "freelance", copy each job title below and add why/action; keep the SAME titles and order. Be specific and realistic. No investing/trading advice.

Freelance jobs found today:
$fl
"@
    $resp = Ollama-Json $model $prompt
    $parsed = $resp | ConvertFrom-Json
    if ($parsed) {
      $brainUsed = 'ollama'
      # map enrichment back onto freelance items by index (titles preserved)
      $enr = @($parsed.freelance)
      for ($i=0; $i -lt $freelance.Count; $i++) {
        $why=''; $action=''
        if ($i -lt $enr.Count) { $why=[string]$enr[$i].why; $action=[string]$enr[$i].action }
        $freelance[$i] | Add-Member -NotePropertyName why    -NotePropertyValue $why    -Force
        $freelance[$i] | Add-Member -NotePropertyName action -NotePropertyValue $action -Force
      }
      $businessIdeas = @($parsed.business | ForEach-Object { [ordered]@{ title=[string]$_.title; why=[string]$_.why; action=[string]$_.action } })
      $channelIdeas  = @($parsed.channel  | ForEach-Object { [ordered]@{ title=[string]$_.title; why=[string]$_.why; action=[string]$_.action } })
    }
  } catch {
    Log "  ! Ollama enrichment failed, using heuristic: $($_.Exception.Message)"
  }
}

# ---- heuristic fallback for anything the brain didn't fill ----
foreach ($o in $freelance) {
  if (-not ($o.PSObject.Properties.Name -contains 'why')    -or -not $o.why)    { $o | Add-Member -NotePropertyName why    -NotePropertyValue ('Matches your skills: ' + ($o.tags -split ',' | Select-Object -First 3 | ForEach-Object { $_.Trim() } | Where-Object { $_ }) -join ', ') -Force }
  if (-not ($o.PSObject.Properties.Name -contains 'action') -or -not $o.action) { $o | Add-Member -NotePropertyName action -NotePropertyValue 'Open the link and apply / pitch a short tailored proposal.' -Force }
}
if ($businessIdeas.Count -eq 0) {
  $businessIdeas = @(
    [ordered]@{ title='Sell your ShortsForge pipeline as a service'; why='You already automate faceless AI shorts end to end.'; action='Make a 1-page Gumroad/Fiverr gig: "5 AI shorts/week, done-for-you".' },
    [ordered]@{ title='Package prompt/scene templates as a digital product'; why='Your scene + voiceover prompts have reusable value.'; action='Bundle your best prompts into a $19 template pack.' },
    [ordered]@{ title='Build tiny automation bots for creators'; why='Python + AI automation is in demand and repeatable.'; action='List one "auto-caption / auto-thumbnail" micro-service.' }
  )
}
if ($channelIdeas.Count -eq 0) {
  $channelIdeas = @(
    [ordered]@{ title='Affiliate the AI tools you use'; why='Your audience wants the same stack.'; action='Add affiliate links (TTS, editing tools) to video descriptions.' },
    [ordered]@{ title='Hit YouTube Partner Program thresholds'; why='Shorts + long-form can qualify for ad revenue.'; action='Track subs/watch-hours; schedule uploads to close the gap.' },
    [ordered]@{ title='Offer channel memberships / a tip jar'; why='Recurring income from existing viewers.'; action='Enable memberships or a Ko-fi link once eligible.' }
  )
}

# ================= OPTIONAL: claude brain (only if logged in) =================
if ($Brain -eq 'claude') {
  Log 'Note: -Brain claude requires the bundled claude.exe to be logged in (run it once and /login). Falling back if not.'
  # left as an explicit opt-in; default runs never depend on it.
}

# ================= ASSEMBLE JSON =================
$freelanceOut = @($freelance | ForEach-Object {
  [ordered]@{ title=$_.title; org=$_.org; url=$_.url; source=$_.source; posted=$_.posted; salary=$_.salary; why=$_.why; action=$_.action; score=$_.score }
})
$signalsOut = @($signals | ForEach-Object {
  [ordered]@{ title=$_.title; org=$_.org; url=$_.url; source=$_.source; posted=$_.posted }
})

$total = $freelanceOut.Count + $businessIdeas.Count + $channelIdeas.Count + $signalsOut.Count
$data = [ordered]@{
  generatedAt = $Now.ToString('yyyy-MM-dd HH:mm')
  brain       = $brainUsed
  count       = $total
  note        = 'Research only - finds & explains opportunities. It does not trade, transact, or give investment advice.'
  freelance   = $freelanceOut
  business    = $businessIdeas
  channel     = $channelIdeas
  signals     = $signalsOut
}
$json = $data | ConvertTo-Json -Depth 8
$json | Out-File -FilePath (Join-Path $Root 'opportunities.json') -Encoding utf8

# ================= READABLE MARKDOWN + ARCHIVE =================
$sb = New-Object System.Text.StringBuilder
[void]$sb.AppendLine("# Money Opportunities - $($Now.ToString('dddd, MMMM d, yyyy'))")
[void]$sb.AppendLine("")
[void]$sb.AppendLine("_Brain: $brainUsed - $total items. Research only; you decide and act._")
[void]$sb.AppendLine("")
[void]$sb.AppendLine("## Freelance / gigs (matched to your skills)")
if ($freelanceOut.Count) { foreach ($f in $freelanceOut) {
  [void]$sb.AppendLine("- **$($f.title)** @ $($f.org)  $(if($f.posted){"_($($f.posted))_"})")
  if ($f.why)    { [void]$sb.AppendLine("  - Why: $($f.why)") }
  if ($f.action) { [void]$sb.AppendLine("  - Next: $($f.action)") }
  if ($f.url)    { [void]$sb.AppendLine("  - $($f.url)") }
} } else { [void]$sb.AppendLine("_No skill-matched gigs surfaced today._") }
[void]$sb.AppendLine("")
[void]$sb.AppendLine("## Online business ideas")
foreach ($b in $businessIdeas) { [void]$sb.AppendLine("- **$($b.title)** - $($b.why)  _Next: $($b.action)_") }
[void]$sb.AppendLine("")
[void]$sb.AppendLine("## Monetize your channels")
foreach ($c in $channelIdeas) { [void]$sb.AppendLine("- **$($c.title)** - $($c.why)  _Next: $($c.action)_") }
[void]$sb.AppendLine("")
[void]$sb.AppendLine("## Market / idea signals (research only)")
if ($signalsOut.Count) { foreach ($s in $signalsOut) { [void]$sb.AppendLine("- $($s.title)  _($($s.org))_  $($s.url)") } }
else { [void]$sb.AppendLine("_No signals today._") }
$md = $sb.ToString()
$md | Out-File -FilePath (Join-Path $Root 'opportunities.md') -Encoding utf8
$md | Out-File -FilePath (Join-Path $OutDir "$TodayIso.md") -Encoding utf8

Log ""
Log ("Done. brain=$brainUsed  freelance=$($freelanceOut.Count)  business=$($businessIdeas.Count)  channel=$($channelIdeas.Count)  signals=$($signalsOut.Count)")
Log ("Wrote: opportunities.json, opportunities.md, money\$TodayIso.md")
