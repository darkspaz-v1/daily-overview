# Daily Overview

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

## Running it

```
run-app.ps1        # desktop app
Daily Overview.cmd # dashboard
```

Windows only — PowerShell, Win32 APIs, and SAPI voices.

## Note on contents

`class-deadlines.md`, `class-schedule.md` and `effort.md` are this author's real Fall 2026 coursework
data, kept in-repo because the scripts read them. They are schedule information, not credentials.
`planner.md` and all generated `latest.*` output are gitignored.

## License

MIT — see [LICENSE](LICENSE).
