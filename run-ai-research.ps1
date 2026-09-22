<#
  run-ai-research.ps1  --  weekly wrapper

  1. Runs the Claude Code CLI headlessly (claude -p) with WebSearch/WebFetch/Write
     to research new AI developments and write a report + dashboard summary into
     ai-research\.
  2. Runs daily-overview.ps1 (folds ai-research\latest.json into latest.js for the
     dashboard, same as money-research does for opportunities.json).

  Runs once a week. Fires from two places (whichever happens first wins; the
  once-per-week stamp stops the other from repeating the work):
    * the "Weekly AI Research" scheduled task (Friday 8:15 AM), and
    * at logon, launched in the background by run-app.ps1.
  Logs to ai-research\run.log. Use -Force to run again the same week.

  Uses the user's existing Claude Code login (Pro/Max subscription) - this is
  the same auth as interactive `claude` sessions, not a separate API key. Each
  run draws on the normal Claude Code usage limits.
#>
param([switch]$Force)
$ErrorActionPreference = 'Continue'
$Root = $PSScriptRoot
if (-not $Root -and $MyInvocation.MyCommand.Path) { $Root = Split-Path -Parent $MyInvocation.MyCommand.Path }
if (-not $Root -or -not (Test-Path (Join-Path $Root 'daily-overview.ps1'))) { $Root = (Get-Location).Path }

$AiDir      = Join-Path $Root 'ai-research'
$ReportsDir = Join-Path $AiDir 'reports'
$Log        = Join-Path $AiDir 'run.log'
New-Item -ItemType Directory -Force $ReportsDir | Out-Null

function Note($m) { "$([DateTime]::Now.ToString('yyyy-MM-dd HH:mm:ss'))  $m" | Out-File -FilePath $Log -Append -Encoding utf8 }

# ---- once-per-week guard (stamp = Monday of the current week) ----
$Now = Get-Date
$dow = [int]$Now.DayOfWeek                      # Sunday=0 .. Saturday=6
$daysSinceMonday = ($dow + 6) % 7
$WeekStart = $Now.Date.AddDays(-$daysSinceMonday).ToString('yyyy-MM-dd')
$Stamp = Join-Path $AiDir 'last-run-week.txt'
if (-not $Force -and (Test-Path $Stamp) -and ((Get-Content $Stamp -Raw).Trim() -eq $WeekStart)) {
  Note "skip: already ran this week (week of $WeekStart). Use -Force to override."
  return
}

. (Join-Path $Root 'paths.ps1')
$claudeExe = Resolve-ClaudeCli
if (-not $claudeExe) {
  Note "ERROR: claude CLI not found (set CLAUDE_CLI, or put claude.cmd on PATH) -- skipping this run."
  return
}

$TodayIso  = $Now.ToString('yyyy-MM-dd')
$ReportRel = "reports/$TodayIso.md"

$Prompt = @"
Do deep research on new AI developments from roughly the last 7-10 days: new models and
features from Anthropic/Claude, OpenAI, Google Gemini, and other major labs; AI video/image/
voice generation tools; local/open-source models runnable on a consumer GPU (RTX 5070,
12GB VRAM); AI coding agents and Claude Code specifically; AI agent/automation platforms;
and any policy or platform changes affecting YouTube creators or small web-agency businesses.

Bias the report toward what is actually actionable for a solo creator/developer who runs a
faceless AI 'stickman' YouTube channel (a ShortsForge pipeline, local ComfyUI, Kokoro TTS),
a small web-design agency for local businesses using Stripe for payments, and Claude Code
daily for automation. Tag every claim as VERIFIED (primary source: vendor blog, official
changelog, or major outlet) or UNVERIFIED (SEO aggregator blog only, single low-quality
source, or speculation) - never present an unverified claim as settled fact.

Write exactly two files using the Write tool, both as paths relative to the current
directory (do not write anywhere else):

1. '$ReportRel' -- a full markdown report: top 5 things that matter this week, model
   updates by vendor, video/image/voice generation landscape, local/self-hosted model
   landscape, agent and coding-tool landscape, business/commerce developments, and a
   'what to actually do' action list. Mark every factual claim VERIFIED or UNVERIFIED.

2. 'latest.json' -- a compact JSON summary for a dashboard widget, with EXACTLY this
   shape and nothing else (no markdown code fences, must be valid JSON):
{
  "generatedAt": "$($Now.ToString('yyyy-MM-dd HH:mm'))",
  "headline": "<one sentence: the single most important development this week>",
  "count": <number of items in highlights>,
  "reportFile": "$ReportRel",
  "highlights": [
    {"title": "<short title>", "category": "<model|video|local|agent|business|policy>", "summary": "<one plain-language sentence>", "action": "<one concrete next step, or empty string if none>"}
  ]
}
Include 5 to 8 highlights, ranked by relevance to this specific user. Do not fabricate
URLs, prices, or figures -- only include what your research actually found, and note
in the report where sources disagreed or were weak.

After writing both files, append one line to 'index.md' (create it with a top-level
heading if it does not exist yet) in the form:
- ${TodayIso}: <headline text> ([full report]($ReportRel))
"@

$PromptFile = Join-Path $AiDir 'prompt.txt'
$Prompt | Out-File -FilePath $PromptFile -Encoding utf8 -NoNewline

$StdOutFile = Join-Path $AiDir 'claude-stdout.log'
$StdErrFile = Join-Path $AiDir 'claude-stderr.log'
$ArgList = @('-p','--allowedTools','WebSearch,WebFetch,Write','--permission-mode','acceptEdits','--output-format','text')

Note '=== run-ai-research start ==='
Note "claude args: $($ArgList -join ' ')"
try {
  $proc = Start-Process -FilePath $claudeExe -ArgumentList $ArgList -WorkingDirectory $AiDir `
    -RedirectStandardInput $PromptFile -RedirectStandardOutput $StdOutFile -RedirectStandardError $StdErrFile `
    -NoNewWindow -PassThru

  $finished = $proc.WaitForExit(1200000)   # 20 minute cap
  if (-not $finished) {
    Note 'TIMEOUT: claude did not finish within 20 minutes -- killing process.'
    try { $proc.Kill() } catch { Note "Could not kill timed-out claude process: $($_.Exception.Message)" }
  } else {
    Note "claude exit code = $($proc.ExitCode)"
  }
} catch {
  Note "ERROR launching claude: $($_.Exception.Message)"
}

if (Test-Path $StdErrFile) {
  $errText = (Get-Content $StdErrFile -Raw -ErrorAction SilentlyContinue)
  if ($errText -and $errText.Trim()) { Note "stderr: $($errText.Trim())" }
}

$latestPath = Join-Path $AiDir 'latest.json'
if (Test-Path $latestPath) {
  Note "OK: latest.json written."
} else {
  Note "WARNING: latest.json was not created -- dashboard will show no AI research data this run."
}

try {
  & powershell -ExecutionPolicy Bypass -File (Join-Path $Root 'daily-overview.ps1') -Quiet
  Note "daily-overview.ps1 exit=$LASTEXITCODE"
} catch { Note "daily-overview ERROR: $($_.Exception.Message)" }

$WeekStart | Out-File -FilePath $Stamp -Encoding utf8
Note '=== run-ai-research done ==='
