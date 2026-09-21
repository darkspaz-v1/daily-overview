"""plan-day.py logic against FAKE class-schedule / class-deadlines / effort / planner files."""
import datetime as dt
import types

import pytest

SCHEDULE = """\
# fake schedule
## Weekly
M W F | 09:00-09:50 | MATH100 | Lecture | Bldg A
Tu Th | 14:00-15:15 | CHEM200 | Lecture | Bldg B
this is prose | and not a row

## Exceptions
2026-03-16 | ALL | no-class   # spring break
2026-03-18 | MATH100 | no-class
2026-03-17 | CHEM200:Lecture | starts

## Day defaults
wake | 08:00
sleep | 23:00   # late
commute | 20
passing | 10
"""

EFFORT = """\
## Rules
MATH100 | homework | 3 | 2
* | exam | 8 | 5
* | | 1 | 1
"""

DEADLINES = """\
# due dates
2026-03-13 | 23:59 | MATH100 | Homework 4
2026-03-13 | 09:00 | CHEM200 | Quiz prep exam
bad line here
"""

PLANNER = """\
## Scheduled
- 2026-03-12 13:00 Advising appointment
- 2026-03-12 all day thing without time

<!-- CLASS-SYNC:START -->
- 2026-03-12 15:00 Generated from deadlines
<!-- CLASS-SYNC:END -->

## Tasks
- [ ] Email professor (est: 0.25h) (due: 2026-03-14)
- [ ] Laundry
- [x] Done already (est: 2h)
"""


@pytest.fixture
def files(tmp_path):
    (tmp_path / "class-schedule.md").write_text(SCHEDULE, encoding="utf-8")
    (tmp_path / "effort.md").write_text(EFFORT, encoding="utf-8")
    (tmp_path / "class-deadlines.md").write_text(DEADLINES, encoding="utf-8")
    (tmp_path / "planner.md").write_text(PLANNER, encoding="utf-8")
    return tmp_path


def test_time_helpers(plan_day):
    assert plan_day.to_min("09:30") == 570
    assert plan_day.to_hhmm(570) == "09:30"
    assert plan_day.fmt_dur(90) == "1h 30m"
    assert plan_day.fmt_dur(120) == "2h"
    assert plan_day.fmt_dur(25) == "25m"


def test_parse_days(plan_day):
    assert plan_day.parse_days("M W F") == [0, 2, 4]
    assert plan_day.parse_days("MWF") == [0, 2, 4]
    assert plan_day.parse_days("Tu Th") == [1, 3]
    assert plan_day.parse_days("this is prose") == []


def test_strip_comment(plan_day):
    assert plan_day.strip_comment("23:00   # late") == "23:00"
    assert plan_day.strip_comment("# whole line") == "# whole line"


def test_load_schedule(plan_day, files):
    s = plan_day.load_schedule()
    assert len(s.blocks) == 2                      # prose row skipped
    assert s.opt_int("commute", 0) == 20 and s.opt("sleep", "") == "23:00"
    assert s.opt_int("missing", 7) == 7


def test_class_meets_rules(plan_day, files):
    s = plan_day.load_schedule()
    math, chem = s.blocks
    assert s.meets(math, dt.date(2026, 3, 11))      # Wednesday
    assert not s.meets(math, dt.date(2026, 3, 16))  # ALL no-class
    assert not s.meets(math, dt.date(2026, 3, 18))  # MATH100 no-class
    assert not s.meets(chem, dt.date(2026, 3, 12))  # Thursday, but before the 03-17 start
    assert s.meets(chem, dt.date(2026, 3, 19))
    assert [b.klass for b in s.on(dt.date(2026, 3, 13))] == ["MATH100"]


def test_effort_rules_first_match_wins(plan_day, files):
    rules = plan_day.load_effort()
    assert plan_day.effort_for("MATH100", "Homework 4", rules) == (3.0, 2)
    assert plan_day.effort_for("BIO1", "Final exam", rules) == (8.0, 5)
    assert plan_day.effort_for("BIO1", "reading", rules) == (1.0, 1)
    assert plan_day.effort_for("BIO1", "reading", []) == (1.5, 2)  # built-in default


def test_load_deadlines_sorted_and_skips_junk(plan_day, files):
    ds = plan_day.load_deadlines(plan_day.load_effort())
    assert [d.klass for d in ds] == ["CHEM200", "MATH100"]  # 09:00 before 23:59
    assert ds[1].hours == 3.0 and ds[1].lead == 2


def test_load_planner_skips_done_and_class_sync(plan_day, files):
    tasks, scheduled = plan_day.load_planner()
    assert [t.text for t in tasks] == ["Email professor", "Laundry"]
    assert tasks[0].hours == 0.25 and tasks[0].due == dt.date(2026, 3, 14)
    assert tasks[1].hours == 0.5 and tasks[1].due is None
    # timed events only; the CLASS-SYNC-generated line is excluded to avoid double booking
    assert scheduled == [(dt.date(2026, 3, 12), "13:00", "Advising appointment")]


def test_daily_target_spreads_over_lead_window(plan_day):
    d = plan_day.Deadline(dt.date(2026, 3, 13), "23:59", "X", "hw", hours=3.0, lead=2)
    assert plan_day.daily_target(d, dt.date(2026, 3, 11)) == pytest.approx(1.0)
    assert plan_day.daily_target(d, dt.date(2026, 3, 13)) == pytest.approx(3.0)
    assert plan_day.daily_target(d, dt.date(2026, 3, 10)) == 0.0   # before window
    assert plan_day.daily_target(d, dt.date(2026, 3, 14)) == 0.0   # after due


def test_daily_target_morning_deadline_ends_day_before(plan_day):
    d = plan_day.Deadline(dt.date(2026, 3, 13), "09:00", "X", "quiz", hours=2.0, lead=2)
    assert plan_day.daily_target(d, dt.date(2026, 3, 13)) == 0.0
    assert plan_day.daily_target(d, dt.date(2026, 3, 12)) == pytest.approx(2.0)  # last usable day
    assert plan_day.daily_target(d, dt.date(2026, 3, 11)) == pytest.approx(1.0)  # 2 days left


def test_free_gaps_carves_commute_and_passing(plan_day):
    B = plan_day.Busy
    busy = [B(600, 650, "A"), B(700, 750, "B")]  # two classes
    gaps = plan_day.free_gaps(480, 1080, busy, commute=20, passing=10)
    # first class: 20 commute before, 10 passing after; last class: 10 passing before, 20 commute after
    assert gaps == [(480, 580), (660, 690), (770, 1080)]


def test_free_gaps_events_are_not_padded(plan_day):
    B = plan_day.Busy
    gaps = plan_day.free_gaps(480, 720, [B(600, 660, "call", kind="event")], commute=20, passing=10)
    assert gaps == [(480, 600), (660, 720)]


def test_free_gaps_merges_overlaps(plan_day):
    B = plan_day.Busy
    busy = [B(500, 600, "a", kind="event"), B(550, 650, "b", kind="event")]
    assert plan_day.free_gaps(480, 720, busy, 0, 0) == [(480, 500), (650, 720)]


def test_fill_splits_long_work_and_reports_unplaced(plan_day):
    W = plan_day.WorkItem
    sessions, unplaced = plan_day.fill([(0, 200)], [(W("big", "d"), 120), (W("huge", "d"), 600)],
                                       min_session=25, max_session=50, break_len=10)
    # max_session is 50, but a tail shorter than min_session is folded into the last chunk
    assert all(s.end - s.start < 50 + 25 for s in sessions)
    assert sessions[0].label == "big"                       # deadline order preserved
    assert sum(s.end - s.start for s in sessions if s.label == "big") == 120
    assert unplaced and unplaced[0][0].label == "huge"      # what doesn't fit is reported
    spans = [(s.start, s.end) for s in sessions]
    assert all(a[1] <= b[0] for a, b in zip(spans, spans[1:], strict=False))  # sessions never overlap


def test_fill_drops_gaps_smaller_than_min_session(plan_day):
    W = plan_day.WorkItem
    sessions, unplaced = plan_day.fill([(0, 20)], [(W("x", "d"), 30)], 25, 50, 10)
    assert sessions == [] and unplaced[0][1] == 30


def test_build_busy_combines_classes_events_and_extra(plan_day, files):
    s = plan_day.load_schedule()
    _, scheduled = plan_day.load_planner()
    busy = plan_day.build_busy(dt.date(2026, 3, 12), s, scheduled, ["18:00-19:30 gym"])
    assert [b.label for b in busy] == ["Advising appointment", "gym"]  # Thu: CHEM200 hasn't started
    assert busy[0].end - busy[0].start == 60                          # events default to one hour


def test_build_busy_rejects_bad_extra(plan_day, files):
    with pytest.raises(SystemExit):
        plan_day.build_busy(dt.date(2026, 3, 12), plan_day.load_schedule(), [], ["nonsense"])


def test_resolve_date(plan_day):
    today = dt.date.today()
    assert plan_day.resolve_date(None) == today
    assert plan_day.resolve_date("tomorrow") == today + dt.timedelta(days=1)
    assert plan_day.resolve_date("2026-03-11") == dt.date(2026, 3, 11)
    with pytest.raises(SystemExit):
        plan_day.resolve_date("someday")


def test_full_plan_renders(plan_day, files):
    args = types.SimpleNamespace(start="08:00", end="22:00", busy=[], horizon=14, md=True)
    out = plan_day.plan(dt.date(2026, 3, 12), args)
    assert "Advising appointment" in out and "MATH100: Homework 4" in out
    assert "due tomorrow" in out


def test_missing_config_file_exits_with_message(plan_day):
    with pytest.raises(SystemExit) as e:
        plan_day.load_schedule()
    assert "class-schedule.md" in str(e.value)


def test_load_report_runs(plan_day, files):
    args = types.SimpleNamespace(start=None, end=None)
    out = plan_day.load_report(dt.date(2026, 3, 11), 3, args)
    assert "Daily load" in out
