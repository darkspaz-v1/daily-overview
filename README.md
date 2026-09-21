# Daily Overview

[![CI](https://github.com/darkspaz-v1/daily-overview/actions/workflows/ci.yml/badge.svg)](https://github.com/darkspaz-v1/daily-overview/actions/workflows/ci.yml)

A desktop dashboard and voice briefing for the day — weather, tasks, and class deadlines, from one
markdown planner.

## Pieces

| File | Role |
|---|---|
| `daily-overview.ps1` | The engine. Pulls IP-geolocated weather (ipinfo.io + open-meteo), reads `planner.md`, emits `latest.md` / `latest.json` / `latest.js` |
| `dashboard.html` | GridStack drag/resize board with six themes and a floating chat popup |
| `overview_app.py` | pywebview desktop app around the same data |
| `sync-classes.ps1` | Rewrites a marked block in `planner.md` from `class-deadlines.md` |
| `plan-day.py` | Builds a day plan using per-deliverable estimates in `effort.md` |
| `speak-now.ps1` | Speaks the current briefing (edge-tts, falling back to SAPI) |
| `open-jarvis-ui.ps1` | Raises an existing app window instead of starting a second one |

## Two design decisions worth stating

**The engine writes three formats, not one.** `latest.json` for programs, `latest.md` for reading, and
`latest.js` so `dashboard.html` can load data with no server and no fetch — the dashboard opens from
the filesystem.

**`open-jarvis-ui.ps1` is a hand-rolled single-instance guard** because `overview_app.py` has none.
Launching blindly stacks a new pywebview window every time. It queries `Win32_Process` for an existing
instance and, if found, calls `SetForegroundWindow` — with `ShowWindow(SW_RESTORE)` **only** when
`IsIconic` is true, since unconditionally restoring an unfocused window would un-maximise it. If the
process exists but has no window handle yet it is still starting, so the script does nothing rather
than racing it with a second instance.

**"Is it running" and "does it have a window yet" are different questions.** Treating a zero window
handle as "not running" is what produces duplicate windows.

## Sync marker contract

`sync-classes.ps1` only rewrites content **between its markers** inside the `## Scheduled` section of
`planner.md`. Hand-written items outside the markers are never touched, which is what makes it safe to
re-run.

## Install and run

```
pip install -r requirements.txt        # pywebview, requests, sounddevice, SpeechRecognition, edge-tts
run-app.ps1        # desktop app
Daily Overview.cmd # dashboard
```

Windows only: PowerShell, Win32 APIs, and SAPI voices. Nothing is tied to one machine. Paths resolve in
this order: environment variable, then PATH or next to the script, then a `%USERPROFILE%` default.

| Variable | Meaning | Default |
|---|---|---|
| `DAILY_OVERVIEW_PYTHON` | full path to the `python.exe` used by `run-app.ps1` and `speak-now.ps1` | `pythonw` on PATH, then `py -3` |
| `CLAUDE_CLI` | full path to `claude.cmd` for the weekly AI research | `claude.cmd` on PATH, then `%APPDATA%\npm\claude.cmd` |
| `SHORTSFORGE_DIR` | the ShortsForge project folder shown in the briefing | `%USERPROFILE%\AI Agents` |

The `.vbs` launchers find their `.ps1` next to themselves, so the folder can live anywhere.

## Tests

```
pip install -r requirements-dev.txt
python -m pytest
```

Tests run against fake planner and schedule fixtures written to a temp folder. They never touch a real
`planner.md`.

## Troubleshooting

The desktop app runs under `pythonw`, so errors do not appear in a console. They are written to
`logs/daily-overview.log` (rotating, next to `overview_app.py`). The scheduled research scripts log to
`money\run.log` and `ai-research\run.log`.

## Note on contents

`planner.md`, `class-deadlines.md`, `class-schedule.md`, `effort.md` and all generated `latest.*`
output are personal, gitignored files you create yourself (`plan-day.py` and `sync-classes.ps1` expect
the three class files beside them). A minimal `planner.md` has `## Recurring`, `## Scheduled`
(`- 2026-01-31 09:30 Team standup`) and `## Tasks` (`- [ ] Buy milk (due: 2026-02-01)`) sections.

## License

MIT — see [LICENSE](LICENSE).
