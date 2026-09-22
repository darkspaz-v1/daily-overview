#!/usr/bin/env python3
"""
plan-day.py - build a time-blocked plan for one day.

Reads four files that live beside it:
  class-schedule.md   fixed weekly class blocks + exceptions + day defaults
  class-deadlines.md  every dated class deliverable (the source of truth)
  effort.md           how long each kind of deliverable takes, and lead time
  planner.md          your own Scheduled items and Tasks

Works out which hours are already spoken for, what work is live today (spread
backward from each due date across its lead window), and fits the work into the
gaps in deadline order.

Usage
  python plan-day.py                          plan today
  python plan-day.py 2026-09-04               plan a specific date
  python plan-day.py tomorrow                 plan tomorrow
  python plan-day.py --from 09:30 --to 22:00  override the day's bounds
  python plan-day.py --busy "18:00-19:30 gym" --busy "20:00-20:30 call home"
  python plan-day.py --horizon 21             look this far ahead for deadlines
  python plan-day.py --load                   show the next 14 days' daily load
  python plan-day.py --md                     emit markdown instead of a table
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DAY_TOKENS = ["M", "Tu", "W", "Th", "F"]          # index == weekday() for Mon..Fri


# --------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------

def read_lines(path: Path) -> list[str]:
    if not path.exists():
        sys.exit(f"missing {path.name} - expected beside plan-day.py in {ROOT}")
    return path.read_text(encoding="utf-8").splitlines()


def strip_comment(s: str) -> str:
    """Drop a trailing ' # comment', but keep '#' that starts a line."""
    return re.sub(r"\s+#.*$", "", s).strip()


def to_min(hhmm: str) -> int:
    h, m = hhmm.strip().split(":")
    return int(h) * 60 + int(m)


def to_hhmm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def fmt_dur(minutes: int) -> str:
    h, m = divmod(int(round(minutes)), 60)
    if h and m:
        return f"{h}h {m}m"
    if h:
        return f"{h}h"
    return f"{m}m"


# --------------------------------------------------------------------------
# config: class-schedule.md
# --------------------------------------------------------------------------

@dataclass
class ClassBlock:
    days: list[int]          # weekday indices, Mon=0
    start: int               # minutes from midnight
    end: int
    klass: str               # "CHEM135"
    kind: str                # "Lecture" / "Discussion"
    where: str

    @property
    def key(self) -> str:
        return f"{self.klass}:{self.kind}"

    @property
    def label(self) -> str:
        return f"{self.klass} {self.kind}"


@dataclass
class Schedule:
    blocks: list[ClassBlock] = field(default_factory=list)
    no_class: list[tuple[dt.date, str]] = field(default_factory=list)   # (date, target)
    starts: dict[str, dt.date] = field(default_factory=dict)           # target -> first meeting
    defaults: dict[str, str] = field(default_factory=dict)

    def opt(self, key: str, fallback: str) -> str:
        return self.defaults.get(key, fallback)

    def opt_int(self, key: str, fallback: int) -> int:
        try:
            return int(self.defaults.get(key, fallback))
        except ValueError:
            return fallback

    def meets(self, block: ClassBlock, day: dt.date) -> bool:
        if day.weekday() not in block.days:
            return False
        first = self.starts.get(block.key)
        if first and day < first:
            return False
        for when, target in self.no_class:
            if when != day:
                continue
            if target == "ALL" or target == block.klass or target == block.key:
                return False
        return True

    def on(self, day: dt.date) -> list[ClassBlock]:
        found = [b for b in self.blocks if self.meets(b, day)]
        return sorted(found, key=lambda b: b.start)


def parse_days(token_field: str) -> list[int]:
    """'M W F' or 'MWF' or 'Tu Th' -> weekday indices. [] if anything else is present,
    so prose lines in the config are not mistaken for schedule rows."""
    compact = token_field.replace(" ", "")
    out, i = [], 0
    while i < len(compact):
        two = compact[i:i + 2]
        if two in ("Tu", "Th"):
            out.append(DAY_TOKENS.index(two))
            i += 2
            continue
        one = compact[i:i + 1]
        if one not in ("M", "W", "F"):
            return []
        out.append(DAY_TOKENS.index(one))
        i += 1
    return sorted(set(out))


def load_schedule() -> Schedule:
    sched = Schedule()
    section = None
    for raw in read_lines(ROOT / "class-schedule.md"):
        line = raw.strip()
        if line.startswith("## "):
            section = line[3:].strip().lower()
            continue
        if not line or line.startswith("#"):
            continue

        if section == "weekly":
            parts = [p.strip() for p in line.split("|")]
            if len(parts) < 4:
                continue
            days = parse_days(parts[0])
            if not days or "-" not in parts[1]:
                continue
            lo, hi = parts[1].split("-")
            sched.blocks.append(ClassBlock(
                days=days, start=to_min(lo), end=to_min(hi),
                klass=parts[2], kind=parts[3],
                where=parts[4] if len(parts) > 4 else "",
            ))

        elif section == "exceptions":
            parts = [strip_comment(p) for p in line.split("|")]
            if len(parts) < 3:
                continue
            try:
                when = dt.date.fromisoformat(parts[0])
            except ValueError:
                continue
            target, what = parts[1], parts[2].lower()
            if what == "no-class":
                sched.no_class.append((when, target))
            elif what == "starts":
                sched.starts[target] = when

        elif section == "day defaults":
            parts = [p.strip() for p in line.split("|")]
            if len(parts) >= 2:
                sched.defaults[parts[0]] = strip_comment(parts[1])
    return sched


# --------------------------------------------------------------------------
# config: effort.md
# --------------------------------------------------------------------------

@dataclass
class EffortRule:
    klass: str
    match: str
    hours: float
    lead: int


def load_effort() -> list[EffortRule]:
    rules, section = [], None
    for raw in read_lines(ROOT / "effort.md"):
        line = raw.strip()
        if line.startswith("## "):
            section = line[3:].strip().lower()
            continue
        if section != "rules" or not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 4:
            continue
        try:
            rules.append(EffortRule(parts[0], parts[1], float(parts[2]), int(parts[3])))
        except ValueError:
            continue
    return rules


def effort_for(klass: str, text: str, rules: list[EffortRule]) -> tuple[float, int]:
    for r in rules:
        if r.klass not in ("*", klass):
            continue
        if r.match and r.match.lower() not in text.lower():
            continue
        return r.hours, r.lead
    return 1.5, 2


# --------------------------------------------------------------------------
# deadlines + tasks
# --------------------------------------------------------------------------

@dataclass
class Deadline:
    due: dt.date
    time: str            # "" for all-day
    klass: str
    what: str
    hours: float
    lead: int

    @property
    def label(self) -> str:
        return f"{self.klass}: {self.what}"


DEADLINE_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2})\s*\|\s*([0-9:]*)\s*\|\s*([^|]+?)\s*\|\s*(.+)$"
)


def load_deadlines(rules: list[EffortRule]) -> list[Deadline]:
    out = []
    for raw in read_lines(ROOT / "class-deadlines.md"):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = DEADLINE_RE.match(line)
        if not m:
            continue
        due = dt.date.fromisoformat(m.group(1))
        klass, what = m.group(3).strip(), m.group(4).strip()
        hours, lead = effort_for(klass, what, rules)
        out.append(Deadline(due, m.group(2).strip(), klass, what, hours, lead))
    return sorted(out, key=lambda d: (d.due, d.time or "99:99"))


@dataclass
class Task:
    text: str
    hours: float
    due: dt.date | None


TASK_EST_RE = re.compile(r"\(est:\s*([0-9.]+)\s*h\)", re.I)
TASK_DUE_RE = re.compile(r"\(due:\s*(\d{4}-\d{2}-\d{2})\)")


def load_planner() -> tuple[list[Task], list[tuple[dt.date, str, str]]]:
    """Return (open tasks, dated scheduled items with a time)."""
    tasks: list[Task] = []
    scheduled: list[tuple[dt.date, str, str]] = []
    section = None
    in_class_sync = False
    for raw in read_lines(ROOT / "planner.md"):
        line = raw.strip()
        # Items inside the CLASS-SYNC block are generated from class-deadlines.md,
        # which we read directly. Treating them as events too would double-book the
        # day - a deadline is a moment, not an hour of committed time.
        if "CLASS-SYNC:START" in line:
            in_class_sync = True
            continue
        if "CLASS-SYNC:END" in line:
            in_class_sync = False
            continue
        if line.startswith("## "):
            section = line[3:].strip().lower()
            continue
        if in_class_sync or not line.startswith("- "):
            continue
        body = line[2:].strip()

        if section == "tasks":
            if body.startswith("[x]") or body.startswith("[X]"):
                continue
            body = re.sub(r"^\[\s?\]\s*", "", body)
            est = TASK_EST_RE.search(body)
            due = TASK_DUE_RE.search(body)
            text = TASK_EST_RE.sub("", TASK_DUE_RE.sub("", body)).strip(" -")
            tasks.append(Task(
                text=text,
                hours=float(est.group(1)) if est else 0.5,
                due=dt.date.fromisoformat(due.group(1)) if due else None,
            ))

        elif section == "scheduled":
            m = re.match(r"^(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2})\s+(.+)$", body)
            if m:
                scheduled.append((dt.date.fromisoformat(m.group(1)), m.group(2), m.group(3)))
    return tasks, scheduled


# --------------------------------------------------------------------------
# the plan
# --------------------------------------------------------------------------

@dataclass
class Busy:
    start: int
    end: int
    label: str
    where: str = ""
    kind: str = "class"


@dataclass
class Session:
    start: int
    end: int
    label: str
    detail: str


def daily_target(d: Deadline, day: dt.date) -> float:
    """Hours of this item that belong to `day`, spreading effort over the lead window."""
    if d.hours <= 0:
        return 0.0
    window_start = d.due - dt.timedelta(days=d.lead)
    if day < window_start or day > d.due:
        return 0.0
    # Days still available, counting today. Due-date work only counts if it is due
    # late enough in the day to be worth a morning session.
    last_day = d.due if (not d.time or to_min(d.time) >= 12 * 60) else d.due - dt.timedelta(days=1)
    if day > last_day:
        return 0.0
    remaining = (last_day - day).days + 1
    return d.hours / max(remaining, 1)


def build_busy(day: dt.date, sched: Schedule, scheduled, extra) -> list[Busy]:
    busy = [
        Busy(b.start, b.end, b.label, b.where)
        for b in sched.on(day)
    ]
    for when, hhmm, text in scheduled:
        if when == day:
            busy.append(Busy(to_min(hhmm), to_min(hhmm) + 60, text, kind="event"))
    for spec in extra:
        m = re.match(r"^(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})\s*(.*)$", spec.strip())
        if not m:
            sys.exit(f'--busy needs "HH:MM-HH:MM label", got: {spec}')
        busy.append(Busy(to_min(m.group(1)), to_min(m.group(2)),
                         m.group(3) or "busy", kind="event"))
    return sorted(busy, key=lambda b: b.start)


def free_gaps(day_start: int, day_end: int, busy: list[Busy],
              commute: int, passing: int) -> list[tuple[int, int]]:
    """Free intervals, with commute carved out around the class day and a passing
    buffer around every class."""
    blocked: list[tuple[int, int]] = []
    classes = [b for b in busy if b.kind == "class"]
    for b in busy:
        lo, hi = b.start, b.end
        if b.kind == "class":
            first = classes and b is classes[0]
            last = classes and b is classes[-1]
            lo -= commute if first else passing
            hi += commute if last else passing
        blocked.append((lo, hi))

    merged: list[list[int]] = []
    for lo, hi in sorted(blocked):
        if merged and lo <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], hi)
        else:
            merged.append([lo, hi])

    gaps, cursor = [], day_start
    for lo, hi in merged:
        if lo > cursor:
            gaps.append((cursor, min(lo, day_end)))
        cursor = max(cursor, hi)
    if cursor < day_end:
        gaps.append((cursor, day_end))
    return [(a, b) for a, b in gaps if b - a > 0]


def fill(gaps, queue, min_session, max_session, break_len) -> tuple[list[Session], list]:
    """Lay the work queue into the gaps. Returns (sessions, unplaced)."""
    sessions: list[Session] = []
    remaining = [[item, mins] for item, mins in queue if mins >= 1]

    for lo, hi in gaps:
        cursor = lo
        while cursor < hi and remaining:
            avail = hi - cursor
            if avail < min_session:
                break
            item, left = remaining[0]
            chunk = min(max_session, left, avail)
            # Don't leave a useless tail: if finishing the item would only overrun
            # this chunk by less than a session, take the whole remainder now.
            if left - chunk < min_session and left <= avail:
                chunk = left
            if chunk < min_session and left > chunk:
                break
            if chunk < 10:
                # Rounding residue, not real work. Drop it rather than putting a
                # five-minute block on the schedule.
                remaining.pop(0)
                continue
            sessions.append(Session(cursor, cursor + chunk, item.label, item.detail))
            cursor += chunk
            remaining[0][1] -= chunk
            if remaining[0][1] < 1:
                remaining.pop(0)
            if cursor + break_len <= hi and remaining:
                cursor += break_len
    return sessions, [(item, mins) for item, mins in remaining if mins >= 1]


@dataclass
class WorkItem:
    label: str
    detail: str


def plan(day: dt.date, args) -> str:
    sched = load_schedule()
    rules = load_effort()
    deadlines = load_deadlines(rules)
    tasks, scheduled = load_planner()

    commute = sched.opt_int("commute", 20)
    passing = sched.opt_int("passing", 10)
    min_session = sched.opt_int("min_session", 25)
    max_session = sched.opt_int("max_session", 50)
    break_len = sched.opt_int("break_len", 10)

    day_start = to_min(args.start or sched.opt("wake", "08:00"))
    day_end = to_min(args.end or sched.opt("sleep", "23:00"))

    # Planning today at 3pm should not offer you a 9am study block. Unless the day
    # bounds were given explicitly, start from now, rounded up to the next 5 minutes.
    started_late = False
    if day == dt.date.today() and not args.start:
        now = dt.datetime.now()
        now_min = ((now.hour * 60 + now.minute + 4) // 5) * 5
        if now_min > day_start:
            day_start = min(now_min, day_end)
            started_late = True

    busy = build_busy(day, sched, scheduled, args.busy)
    gaps = free_gaps(day_start, day_end, busy, commute, passing)
    free_total = sum(b - a for a, b in gaps)

    # --- what is live today -------------------------------------------------
    horizon = day + dt.timedelta(days=args.horizon)
    live: list[tuple[Deadline, float]] = []
    for d in deadlines:
        if d.due < day or d.due > horizon:
            continue
        hours = daily_target(d, day)
        if hours > 0:
            live.append((d, hours))
    live.sort(key=lambda pair: (pair[0].due, pair[0].time or "99:99"))

    due_today = [d for d in deadlines if d.due == day]

    queue: list[tuple[WorkItem, int]] = []
    for d, hours in live:
        days_left = (d.due - day).days
        when = f"due {d.due.strftime('%a %b %d').replace(' 0', ' ')}"
        if days_left == 0:
            when = "DUE TODAY"
        elif days_left == 1:
            when = "due tomorrow"
        detail = f"{when} - {fmt_dur(d.hours * 60)} total"
        queue.append((WorkItem(d.label, detail), int(round(hours * 60))))

    for t in tasks:
        detail = f"due {t.due}" if t.due else "no deadline"
        queue.append((WorkItem(t.text, detail), int(round(t.hours * 60))))

    sessions, unplaced = fill(gaps, queue, min_session, max_session, break_len)

    # --- render -------------------------------------------------------------
    rows: list[tuple[int, int, str, str]] = []
    for b in busy:
        if started_late and b.end <= day_start:
            continue          # already over; planning the rest of the day
        rows.append((b.start, b.end, b.label, b.where))
    for s in sessions:
        rows.append((s.start, s.end, s.label, s.detail))
    rows.sort(key=lambda r: r[0])

    out: list[str] = []
    heading = day.strftime("%A, %B %d, %Y").replace(" 0", " ")
    committed = sum(b.end - b.start for b in busy)
    work_placed = sum(s.end - s.start for s in sessions)

    if args.md:
        out.append(f"# Plan — {heading}\n")
        if due_today:
            out.append("**Due today**")
            for d in due_today:
                stamp = f"{d.time} " if d.time else ""
                out.append(f"- {stamp}{d.label}")
            out.append("")
        out.append("| Time | What | Detail |")
        out.append("|---|---|---|")
        for lo, hi, label, detail in rows:
            out.append(f"| {to_hhmm(lo)}–{to_hhmm(hi)} | {label} | {detail} |")
        out.append("")
        out.append(f"Class/committed {fmt_dur(committed)} · free {fmt_dur(free_total)} · "
                   f"work scheduled {fmt_dur(work_placed)}")
        if unplaced:
            out.append("\n**Did not fit**")
            for item, mins in unplaced:
                out.append(f"- {item.label} — {fmt_dur(mins)} ({item.detail})")
        return "\n".join(out)

    bar = "-" * 74
    out.append(bar)
    out.append(f" {heading}")
    if started_late:
        out.append(f" planning from {to_hhmm(day_start)} - the rest of the day")
    out.append(bar)

    if due_today:
        out.append("")
        out.append(" DUE TODAY")
        for d in due_today:
            stamp = f"{d.time} " if d.time else "      "
            out.append(f"   ! {stamp} {d.label}")

    out.append("")
    if not rows:
        out.append("  (nothing scheduled and nothing to work on)")
    for lo, hi, label, detail in rows:
        span = f"{to_hhmm(lo)}-{to_hhmm(hi)}"
        short = label if len(label) <= 44 else label[:41] + "..."
        out.append(f"  {span:<12} {short:<44} {detail}")

    out.append("")
    out.append(bar)
    out.append(f" committed {fmt_dur(committed):<10} free {fmt_dur(free_total):<10} "
               f"work placed {fmt_dur(work_placed)}")
    if unplaced:
        out.append("")
        out.append(" DID NOT FIT")
        for item, mins in unplaced:
            out.append(f"   . {item.label:<40} {fmt_dur(mins):<8} {item.detail}")
        out.append("")
        out.append(" Options: start earlier (--from), stay up later (--to), or trim an")
        out.append(" estimate in effort.md. If it keeps not fitting, the semester is")
        out.append(" telling you something.")
    out.append(bar)
    return "\n".join(out)


def load_report(start: dt.date, days: int, args) -> str:
    """Daily required-hours load over the next N days - where the crunch is."""
    sched = load_schedule()
    rules = load_effort()
    deadlines = load_deadlines(rules)
    _, scheduled = load_planner()

    commute = sched.opt_int("commute", 20)
    passing = sched.opt_int("passing", 10)
    day_start = to_min(args.start or sched.opt("wake", "08:00"))
    day_end = to_min(args.end or sched.opt("sleep", "23:00"))

    out = ["-" * 74, " Daily load", "-" * 74, ""]
    out.append(f"  {'Date':<18}{'Need':<9}{'Free':<9}  Load")
    for i in range(days):
        day = start + dt.timedelta(days=i)
        need = sum(daily_target(d, day) for d in deadlines) * 60
        busy = build_busy(day, sched, scheduled, [])
        free = sum(b - a for a, b in free_gaps(day_start, day_end, busy, commute, passing))
        ratio = need / free if free else 0
        width = min(int(ratio * 30), 40)
        flag = "!" if ratio > 0.75 else ""
        label = day.strftime("%a %b %d").replace(" 0", " ")
        out.append(f"  {label:<18}{fmt_dur(need):<9}{fmt_dur(free):<9}  "
                   f"{'#' * width}{flag}")
    out.append("")
    out.append("  Need = hours of assignment work that day, spread back from due dates.")
    out.append("  Free = hours actually available after classes and walking.")
    out.append("-" * 74)
    return "\n".join(out)


def resolve_date(token: str | None) -> dt.date:
    today = dt.date.today()
    if not token or token == "today":
        return today
    if token == "tomorrow":
        return today + dt.timedelta(days=1)
    if token == "yesterday":
        return today - dt.timedelta(days=1)
    try:
        return dt.date.fromisoformat(token)
    except ValueError:
        sys.exit(f"can't read '{token}' as a date - use YYYY-MM-DD, today, or tomorrow")


def main() -> None:
    p = argparse.ArgumentParser(description="Plan one day around your classes and deadlines.")
    p.add_argument("date", nargs="?", help="YYYY-MM-DD, 'today', or 'tomorrow'")
    p.add_argument("--from", dest="start", help="day starts at HH:MM")
    p.add_argument("--to", dest="end", help="day ends at HH:MM")
    p.add_argument("--busy", action="append", default=[],
                   help='block out time: "18:00-19:30 gym" (repeatable)')
    p.add_argument("--horizon", type=int, default=14, help="days ahead to pull work from")
    p.add_argument("--load", action="store_true", help="show the next 14 days' load instead")
    p.add_argument("--md", action="store_true", help="markdown output")
    args = p.parse_args()

    day = resolve_date(args.date)
    print(load_report(day, 14, args) if args.load else plan(day, args))


if __name__ == "__main__":
    main()
