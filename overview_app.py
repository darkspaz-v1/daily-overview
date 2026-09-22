"""
Daily Overview — desktop app with a local AI assistant.

A native window (pywebview) that renders the sci-fi HUD dashboard and embeds an
assistant powered by your local Ollama (llama3.1). The assistant can chat, speak
its replies (edge-tts, offline SAPI fallback), listen to your voice, and add /
remove / complete tasks and events by editing planner.md.

Run:  pythonw overview_app.py     (no console)
The Api class is import-safe (no window) so the logic can be tested headlessly.
"""
import os, sys, json, base64, subprocess, datetime, re
import logging
from logging.handlers import RotatingFileHandler

ROOT   = os.path.dirname(os.path.abspath(__file__))
PLANNER = os.path.join(ROOT, "planner.md")
ENGINE  = os.path.join(ROOT, "daily-overview.ps1")
LATEST  = os.path.join(ROOT, "latest.json")
STATE   = os.path.join(ROOT, "layout.json")
PYDIR   = os.path.dirname(sys.executable)
EDGE    = os.path.join(PYDIR, "Scripts", "edge-tts.exe")
OLLAMA  = "http://localhost:11434"
MODEL   = "llama3.1"
VOICE   = "en-GB-RyanNeural"
NOWIN   = 0x08000000  # CREATE_NO_WINDOW

import requests  # noqa: E402  (kept beside the constants it configures)

LOG_DIR = os.path.join(ROOT, "logs")
log = logging.getLogger("daily_overview")
log.addHandler(logging.NullHandler())  # importing this module stays silent; run_app() attaches the file


def setup_logging():
    """Send log records to logs/daily-overview.log (rotating, 3 x 512 KB). The app runs under
    pythonw, where stderr goes nowhere, so this file is the only place errors show up."""
    if any(isinstance(h, RotatingFileHandler) for h in log.handlers):
        return
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        handler = RotatingFileHandler(os.path.join(LOG_DIR, "daily-overview.log"),
                                      maxBytes=512 * 1024, backupCount=3, encoding="utf-8")
    except OSError:
        return  # read-only folder: run without a log file rather than fail to start
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    log.addHandler(handler)
    log.setLevel(logging.INFO)

# ---------------------------------------------------------------- planner store
class Planner:
    """Reads/writes planner.md. Sections: Recurring / Scheduled / Tasks."""
    def _read(self):
        if not os.path.exists(PLANNER):
            return []
        with open(PLANNER, encoding="utf-8") as f:
            return f.read().splitlines()

    def _write(self, lines):
        with open(PLANNER, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

    def _section_bounds(self, lines, name):
        """Return (header_idx, end_idx) for '## name' section; end is exclusive."""
        start = None
        for i, ln in enumerate(lines):
            m = re.match(r"^\s*##\s*(.+?)\s*$", ln)
            if m and name.lower() in m.group(1).lower():
                start = i
                break
        if start is None:
            return None, None
        end = len(lines)
        for j in range(start + 1, len(lines)):
            if re.match(r"^\s*##\s+", lines[j]):
                end = j
                break
        return start, end

    def add_task(self, text, due=None):
        text = (text or "").strip()
        if not text:
            return {"ok": False, "error": "empty task"}
        lines = self._read()
        s, e = self._section_bounds(lines, "Task")
        entry = "- [ ] " + text + (f" (due: {due})" if due else "")
        if s is None:                      # no Tasks section: create it
            if lines and lines[-1].strip() != "":
                lines.append("")
            lines += ["## Tasks", entry]
        else:
            ins = e
            while ins - 1 > s and lines[ins - 1].strip() == "":
                ins -= 1                   # insert before trailing blanks
            lines.insert(ins, entry)
        self._write(lines)
        return {"ok": True, "added": text, "due": due}

    def add_event(self, date, text, time=None):
        text = (text or "").strip()
        if not (date and text):
            return {"ok": False, "error": "need date and text"}
        lines = self._read()
        s, e = self._section_bounds(lines, "Scheduled")
        entry = f"- {date} " + (f"{time} " if time else "") + text
        if s is None:
            if lines and lines[-1].strip() != "":
                lines.append("")
            lines += ["## Scheduled", entry]
        else:
            ins = e
            while ins - 1 > s and lines[ins - 1].strip() == "":
                ins -= 1
            lines.insert(ins, entry)
        self._write(lines)
        return {"ok": True, "added": text, "date": date}

    def _match_task(self, lines, s, e, query):
        q = (query or "").lower().strip()
        for i in range(s + 1, e):
            m = re.match(r"^-\s*\[( )\]\s*(.+)$", lines[i].strip())
            if m and (q in m.group(2).lower() or not q):
                return i, m.group(2)
        return None, None

    def complete_task(self, query):
        lines = self._read()
        s, e = self._section_bounds(lines, "Task")
        if s is None:
            return {"ok": False, "error": "no tasks"}
        i, body = self._match_task(lines, s, e, query)
        if i is None:
            return {"ok": False, "error": f"no open task matching '{query}'"}
        lines[i] = lines[i].replace("[ ]", "[x]", 1)
        self._write(lines)
        return {"ok": True, "completed": body}

    def remove_task(self, query):
        lines = self._read()
        s, e = self._section_bounds(lines, "Task")
        if s is None:
            return {"ok": False, "error": "no tasks"}
        i, body = self._match_task(lines, s, e, query)
        if i is None:
            return {"ok": False, "error": f"no task matching '{query}'"}
        del lines[i]
        self._write(lines)
        return {"ok": True, "removed": body}

    def remove_any(self, query):
        """Remove the first list item matching query from Tasks, Scheduled, or Recurring."""
        q = (query or "").lower().strip()
        if not q:
            return {"ok": False, "error": "empty query"}
        lines = self._read()
        for i, ln in enumerate(lines):
            t = ln.strip()
            m = re.match(r"^-\s*(?:\[[ xX]\]\s*)?(.+)$", t)
            if m and q in m.group(1).lower():
                del lines[i]
                self._write(lines)
                return {"ok": True, "removed": m.group(1).strip()}
        return {"ok": False, "error": f"nothing matching '{query}'"}

    def list_open(self):
        lines = self._read()
        s, e = self._section_bounds(lines, "Task")
        out = []
        if s is not None:
            for i in range(s + 1, e):
                m = re.match(r"^-\s*\[( )\]\s*(.+)$", lines[i].strip())
                if m:
                    out.append(m.group(2).strip())
        return out

    def categorized(self):
        """Parse the whole planner into the same shape the dashboard renders (fast, no weather)."""
        today = datetime.date.today()
        recurring, schedToday, upcoming = [], [], []
        dueToday, overdue, opent = [], [], []
        section = ""
        for raw in self._read():
            m = re.match(r"^\s*##\s*(.+?)\s*$", raw)
            if m:
                section = m.group(1).lower(); continue
            t = raw.strip()
            if not t or t.startswith("#"):
                continue
            if "recurring" in section:
                mm = re.match(r"^-\s*\[( )\]\s*(.+)$", t)
                if mm: recurring.append(mm.group(2).strip())
                elif re.match(r"^-\s*\[[xX]\]", t): pass
                elif re.match(r"^-\s*(.+)$", t): recurring.append(re.match(r"^-\s*(.+)$", t).group(1).strip())
            elif "scheduled" in section:
                mm = re.match(r"^-\s*(\d{4}-\d{2}-\d{2})(?:\s+(\d{1,2}:\d{2}))?\s+(.+)$", t)
                if mm:
                    try: dd = datetime.date.fromisoformat(mm.group(1))
                    except ValueError:
                        log.warning("planner.md: ignoring scheduled item with invalid date %r", mm.group(1))
                        continue
                    tm, what = mm.group(2), mm.group(3).strip()
                    if dd == today: schedToday.append((tm + " - " if tm else "") + what)
                    elif today < dd <= today + datetime.timedelta(days=7):
                        upcoming.append((mm.group(1) + " " + (tm + " " if tm else "") + what).strip())
            elif "task" in section:
                mm = re.match(r"^-\s*\[( )\]\s*(.+)$", t)
                if mm:
                    body, due = mm.group(2).strip(), None
                    dm = re.search(r"\(due:\s*(\d{4}-\d{2}-\d{2})\)", body)
                    if dm:
                        due = dm.group(1); body = re.sub(r"\s*\(due:\s*\d{4}-\d{2}-\d{2}\)", "", body).strip()
                    if due:
                        try: dd = datetime.date.fromisoformat(due)
                        except ValueError:
                            log.warning("planner.md: invalid due date %r on task %r", due, body)
                            dd = None
                        if dd == today: dueToday.append(body)
                        elif dd and dd < today: overdue.append(body + " (was due " + due + ")")
                        else: opent.append(body + " (due " + due + ")")
                    else:
                        opent.append(body)
        return {"overdue": overdue, "scheduledToday": schedToday, "dueToday": dueToday,
                "recurring": recurring, "open": opent, "upcoming": upcoming,
                "openCount": len(overdue) + len(dueToday) + len(opent)}


# WMO weather codes -> text (mirrors Weather-Desc in daily-overview.ps1)
WCODE = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Rime fog", 51: "Light drizzle", 53: "Drizzle", 55: "Dense drizzle",
    56: "Freezing drizzle", 57: "Dense freezing drizzle", 61: "Light rain", 63: "Rain",
    65: "Heavy rain", 66: "Freezing rain", 67: "Heavy freezing rain", 71: "Light snow",
    73: "Snow", 75: "Heavy snow", 77: "Snow grains", 80: "Light showers", 81: "Showers",
    82: "Violent showers", 85: "Snow showers", 86: "Heavy snow showers", 95: "Thunderstorm",
    96: "Thunderstorm w/ hail", 99: "Thunderstorm w/ heavy hail",
}


# ---------------------------------------------------------------- assistant tools
TOOLS = [
    {"type": "function", "function": {
        "name": "add_task", "description": "Add a new to-do task to the planner.",
        "parameters": {"type": "object", "properties": {
            "text": {"type": "string", "description": "the task description"},
            "due": {"type": "string", "description": "optional due date in YYYY-MM-DD"}},
            "required": ["text"]}}},
    {"type": "function", "function": {
        "name": "add_event", "description": "Add a dated scheduled event to the planner.",
        "parameters": {"type": "object", "properties": {
            "date": {"type": "string", "description": "date YYYY-MM-DD"},
            "text": {"type": "string", "description": "what the event is"},
            "time": {"type": "string", "description": "optional time HH:MM"}},
            "required": ["date", "text"]}}},
    {"type": "function", "function": {
        "name": "complete_task", "description": "Mark an existing open task as done (checks it off).",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "words that identify the task"}},
            "required": ["query"]}}},
    {"type": "function", "function": {
        "name": "remove_task", "description": "Delete a task from the planner entirely.",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "words that identify the task"}},
            "required": ["query"]}}},
    {"type": "function", "function": {
        "name": "list_tasks", "description": "List the user's current open tasks.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "get_weather",
        "description": ("Look up the weather forecast for a specific day and/or time, or find WHEN it will rain. "
                        "Use this for ANY weather question that isn't about right-this-moment: a later time today, "
                        "another day (tomorrow, a weekday like Friday, or a YYYY-MM-DD date within the next 7 days), "
                        "or whether/when it will rain. Returns real forecast numbers — never guess weather yourself."),
        "parameters": {"type": "object", "properties": {
            "day": {"type": "string", "description": "'today', 'tomorrow', a weekday name like 'Friday', or a date YYYY-MM-DD. Defaults to today."},
            "time": {"type": "string", "description": "Optional time of day, e.g. '3pm', '15:00', 'noon', 'morning', 'evening'. Omit for a whole-day summary."}}}}},
]


# ---------------------------------------------------------------- the JS API
class Api:
    def __init__(self):
        self.planner = Planner()
        self._sapi = None
        self._window = None

    # ---- data / engine ----
    def get_data(self):
        try:
            with open(LATEST, encoding="utf-8-sig") as f:  # PowerShell writes a UTF-8 BOM
                return json.load(f)
        except (OSError, ValueError) as ex:  # missing/unreadable file or bad JSON
            log.warning("could not read %s: %s", LATEST, ex)
            return {"error": str(ex)}

    def refresh(self):
        try:
            subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", ENGINE, "-Quiet"],
                cwd=ROOT, timeout=90, creationflags=NOWIN,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except (OSError, subprocess.SubprocessError) as ex:  # includes TimeoutExpired
            log.warning("engine refresh failed, showing the last data: %s", ex)
        return self.get_data()

    # ---- direct task actions (for the in-app buttons) ----
    def task_add(self, text, due=None):
        r = self.planner.add_task(text, due or None)
        return {"ok": r.get("ok", True), "result": r, "tasks": self.planner.categorized()}

    def event_add(self, date, text, time=None):
        r = self.planner.add_event(date, text, time or None)
        return {"ok": r.get("ok", True), "result": r, "tasks": self.planner.categorized()}

    def task_complete(self, query):
        r = self.planner.complete_task(query)
        return {"ok": r.get("ok", False), "result": r, "tasks": self.planner.categorized()}

    def task_remove(self, query):
        r = self.planner.remove_any(query)
        return {"ok": r.get("ok", False), "result": r, "tasks": self.planner.categorized()}

    # ---- tools dispatch ----
    def _exec_tool(self, name, args):
        args = args or {}
        if isinstance(args, str):
            try: args = json.loads(args)
            except ValueError: args = {"text": args}  # model sent plain text instead of JSON
        if name == "add_task":      return self.planner.add_task(args.get("text"), args.get("due"))
        if name == "add_event":     return self.planner.add_event(args.get("date"), args.get("text"), args.get("time"))
        if name == "complete_task": return self.planner.complete_task(args.get("query"))
        if name == "remove_task":   return self.planner.remove_task(args.get("query"))
        if name == "list_tasks":    return {"tasks": self.planner.list_open()}
        if name == "get_weather":   return self._weather_lookup(args.get("day"), args.get("time"))
        return {"ok": False, "error": f"unknown tool {name}"}

    # ---- weather forecast lookup (backs the get_weather tool) ----
    def _resolve_date(self, day):
        today = datetime.date.today()
        if not day:
            return today
        s = str(day).strip().lower()
        if s in ("today", "tonight", "now", ""):
            return today
        if s.startswith("tomorrow"):
            return today + datetime.timedelta(days=1)
        names = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        for i, wd in enumerate(names):
            if s.startswith(wd[:3]):                     # mon, tue, fri, ...
                return today + datetime.timedelta(days=(i - today.weekday()) % 7)
        m = re.search(r"(\d{4}-\d{2}-\d{2})", s)
        if m:
            try: return datetime.date.fromisoformat(m.group(1))
            except ValueError:
                log.debug("get_weather: %r is not a real date, using today", m.group(1))
        return today

    def _resolve_hour(self, time):
        if time is None:
            return None
        s = str(time).strip().lower()
        if not s:
            return None
        if "noon" in s or "midday" in s: return 12
        if "midnight" in s:              return 0
        if "morning" in s:               return 9
        if "afternoon" in s:             return 15
        if "evening" in s:               return 19
        if "night" in s:                 return 21
        m = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", s)
        if m:
            h, ap = int(m.group(1)), m.group(3)
            if ap == "pm" and h != 12: h += 12
            if ap == "am" and h == 12: h = 0
            return max(0, min(23, h))
        return None

    def _weather_lookup(self, day=None, time=None):
        w = (self.get_data().get("weather") or {})
        if not w.get("ok"):
            return {"ok": False, "error": "weather data is unavailable right now"}
        date = self._resolve_date(day)
        diso = date.isoformat()
        forecast = w.get("forecast") or []
        hourly = w.get("hourly") or []
        dayrec = next((f for f in forecast if f.get("date") == diso), None)
        dayhours = [h for h in hourly if str(h.get("t", "")).startswith(diso)]
        if not dayrec and not dayhours:
            return {"ok": False,
                    "error": f"no forecast for {date.strftime('%A %Y-%m-%d')} — only the next 7 days are available"}
        res = {"ok": True, "day": date.strftime("%A"), "date": diso, "place": w.get("place")}
        if dayrec:
            res.update({"high_c": dayrec.get("hi"), "low_c": dayrec.get("lo"),
                        "rain_chance_pct": dayrec.get("rain"), "summary": dayrec.get("desc"),
                        "sunrise": dayrec.get("sunrise"), "sunset": dayrec.get("sunset")})
        hour = self._resolve_hour(time)
        if hour is not None and dayhours:
            pick = min(dayhours, key=lambda h: abs(int(h["t"][11:13]) - hour))
            res["at"] = {"time": pick["t"][11:16], "temp_c": pick.get("temp"), "feels_c": pick.get("feels"),
                         "rain_chance_pct": pick.get("rain"), "conditions": WCODE.get(pick.get("code"), "?")}
        # rain timing — for today, only hours from now onward
        now_h = datetime.datetime.now().hour
        is_today = (date == datetime.date.today())
        future = [h for h in dayhours if (not is_today or int(h["t"][11:13]) >= now_h)]
        rainy = [h for h in future if (h.get("rain") or 0) >= 40 or (h.get("precip") or 0) > 0.1]
        if rainy:
            res["rain_hours"] = [{"time": h["t"][11:16], "chance_pct": h.get("rain")} for h in rainy]
        elif future:
            res["rain_hours"] = "no meaningful rain expected"
        return res

    def _system_prompt(self):
        today = datetime.date.today()
        d = self.get_data()
        w = (d.get("weather") or {})
        fc0 = (w.get("forecast") or [{}])[0]
        if w.get("ok"):
            wx = (f"{w.get('desc','?')}, {w.get('temp','?')}C (feels {w.get('feels','?')}) in {w.get('place','?')}; "
                  f"today high {fc0.get('hi','?')} / low {fc0.get('lo','?')}C, rain chance {fc0.get('rain','?')}%")
        else:
            wx = "unavailable"
        tasks = self.planner.list_open()
        return (
            "You are Jarvis, the user's personal assistant inside their Daily Overview desktop app. "
            "You are warm, concise, and practical — keep replies to a sentence or two unless asked for more. "
            "If asked your name, you are Jarvis.\n"
            f"Today is {today.strftime('%A, %B %d, %Y')} ({today.isoformat()}). "
            "Compute relative dates (tomorrow, next Friday) from this.\n"
            f"Weather right now: {wx}.\n"
            "For weather at a specific later time, on another day (tomorrow, Friday, a date), or about WHEN it will "
            "rain, ALWAYS call get_weather and answer from its numbers — never guess or use the 'right now' value. "
            "A 7-day hourly + daily forecast is available through that tool.\n"
            f"The user's current open tasks: {tasks if tasks else 'none'}.\n"
            "When the user asks to add, remove, schedule, or complete a task or event, ALWAYS use the tools — "
            "never just say you did it. After a tool runs, confirm briefly in plain language. "
            "If a request is ambiguous, ask one short clarifying question instead of guessing."
        )

    def chat(self, history):
        """history: list of {role: 'user'|'assistant', content: str}. Returns reply + actions."""
        msgs = [{"role": "system", "content": self._system_prompt()}] + (history or [])
        actions = []
        try:
            for _ in range(6):
                r = requests.post(f"{OLLAMA}/api/chat",
                                  json={"model": MODEL, "stream": False, "messages": msgs, "tools": TOOLS},
                                  timeout=180).json()
                m = r.get("message", {})
                tcs = m.get("tool_calls")
                if tcs:
                    msgs.append(m)
                    for tc in tcs:
                        fn = tc.get("function", {})
                        res = self._exec_tool(fn.get("name"), fn.get("arguments"))
                        actions.append({"name": fn.get("name"), "args": fn.get("arguments"), "result": res})
                        msgs.append({"role": "tool", "content": json.dumps(res)})
                    continue
                return {"reply": (m.get("content") or "").strip(),
                        "actions": actions, "tasks": self.planner.categorized()}
            return {"reply": "I got a bit tangled up — could you rephrase that?",
                    "actions": actions, "tasks": self.planner.categorized()}
        except Exception as ex:  # noqa: BLE001 - UI boundary: network, bad JSON or a tool bug must become a chat reply, not a crash
            log.exception("chat failed")
            return {"reply": f"(Could not reach the local AI: {ex}. Is Ollama running?)",
                    "actions": actions, "tasks": self.planner.categorized()}

    # ---- voice out ----
    def speak(self, text, voice=None):
        text = (text or "").strip()
        if not text:
            return {"audio": None}
        mp3 = os.path.join(ROOT, "_reply.mp3")
        try:
            if os.path.exists(EDGE):
                if os.path.exists(mp3):
                    os.remove(mp3)
                subprocess.run([EDGE, "--voice", (voice or VOICE), "--rate=+6%", "--text", text, "--write-media", mp3],
                               timeout=60, creationflags=NOWIN,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                if os.path.exists(mp3) and os.path.getsize(mp3) > 0:
                    with open(mp3, "rb") as f:
                        b64 = base64.b64encode(f.read()).decode()
                    return {"audio": "data:audio/mp3;base64," + b64}
        except (OSError, subprocess.SubprocessError) as ex:
            log.warning("edge-tts failed, falling back to Windows speech: %s", ex)
        # offline fallback: speak natively via Windows SAPI (killable via stop_speak)
        try:
            ps = ("Add-Type -AssemblyName System.Speech;"
                  "(New-Object System.Speech.Synthesis.SpeechSynthesizer).Speak([Console]::In.ReadToEnd())")
            self._sapi = subprocess.Popen(["powershell", "-NoProfile", "-Command", ps],
                                          stdin=subprocess.PIPE, text=True, creationflags=NOWIN)
            try:
                self._sapi.communicate(text, timeout=60)
            except (subprocess.TimeoutExpired, OSError, ValueError) as ex:
                log.warning("Windows speech did not finish cleanly: %s", ex)
        except OSError as ex:
            log.warning("could not start Windows speech: %s", ex)
        return {"audio": None}

    def stop_speak(self):
        """Stop native (SAPI) speech immediately. Browser audio is stopped client-side."""
        try:
            if self._sapi and self._sapi.poll() is None:
                self._sapi.terminate()
        except OSError as ex:
            log.debug("stop_speak: %s", ex)  # process already gone; nothing to stop
        return {"ok": True}

    def toggle_fullscreen(self):
        try:
            if self._window:
                self._window.toggle_fullscreen()
        except Exception as ex:  # noqa: BLE001 - pywebview backends raise assorted types; cosmetic feature, never fatal
            log.debug("toggle_fullscreen failed: %s", ex)
        return {"ok": True}

    # ---- layout / theme persistence ----
    def save_state(self, state):
        try:
            if isinstance(state, str):
                state = json.loads(state)
            with open(STATE, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2)
            return {"ok": True}
        except (OSError, ValueError, TypeError) as ex:  # write failure, bad JSON, unserialisable value
            log.warning("could not save %s: %s", STATE, ex)
            return {"ok": False, "error": str(ex)}

    def load_state(self):
        try:
            if os.path.exists(STATE):
                with open(STATE, encoding="utf-8") as f:
                    return json.load(f)
        except (OSError, ValueError) as ex:
            log.warning("could not read %s, using defaults: %s", STATE, ex)
        return {}

    # ---- voice in ----
    def listen(self, seconds=6):
        try:
            import sounddevice as sd
            import speech_recognition as sr
            fs = 16000
            rec = sd.rec(int(seconds * fs), samplerate=fs, channels=1, dtype="int16")
            sd.wait()
            audio = sr.AudioData(rec.tobytes(), fs, 2)
            text = sr.Recognizer().recognize_google(audio)
            return {"text": text}
        except Exception as ex:  # noqa: BLE001 - audio device, SpeechRecognition and network errors all mean "no text"
            log.warning("voice input failed: %s", ex)
            return {"text": "", "error": str(ex)}


def run_app():
    setup_logging()
    import webview
    api = Api()
    api.refresh()  # generate fresh latest.js/json before the window loads
    window = webview.create_window(
        "Daily Overview", url=os.path.join(ROOT, "dashboard.html"),
        js_api=api, width=1240, height=900, min_size=(900, 680),
        fullscreen=True, background_color="#04060c")
    api._window = window
    webview.start()


if __name__ == "__main__":
    run_app()
