"""Shared fixtures. Every test uses FAKE planner data written to tmp_path -- never the real planner.md."""
import datetime
import importlib.util
import sys
import types
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

FIXED_TODAY = datetime.date(2026, 3, 11)  # a Wednesday

FAKE_PLANNER = """\
# Planner

## Recurring
- [ ] Take vitamins
- Stretch for 5 minutes
- [x] Already done recurring

## Scheduled
- 2026-03-11 09:30 Team standup
- 2026-03-11 Dentist (all day)
- 2026-03-14 18:00 Pickleball
- 2026-03-30 10:00 Too far away
- 2026-03-10 08:00 Yesterday event
- 2026-99-99 09:00 Impossible date

## Tasks
- [ ] Write lab report (due: 2026-03-11)
- [ ] File taxes (due: 2026-03-01)
- [ ] Book flights (due: 2026-04-01)
- [ ] Buy milk
- [x] Finished thing (due: 2026-03-11)
- [ ] Bad date task (due: 2026-13-45)
"""


class _FrozenDate(datetime.date):
    @classmethod
    def today(cls):
        return cls(FIXED_TODAY.year, FIXED_TODAY.month, FIXED_TODAY.day)


@pytest.fixture
def overview(tmp_path, monkeypatch):
    """overview_app imported with PLANNER pointed at a fake file and 'today' frozen."""
    import overview_app

    planner = tmp_path / "planner.md"
    planner.write_text(FAKE_PLANNER, encoding="utf-8")
    monkeypatch.setattr(overview_app, "PLANNER", str(planner))
    frozen = types.SimpleNamespace(
        date=_FrozenDate, timedelta=datetime.timedelta, datetime=datetime.datetime,
    )
    monkeypatch.setattr(overview_app, "datetime", frozen)
    overview_app.planner_path = planner
    return overview_app


@pytest.fixture
def planner(overview):
    return overview.Planner()


@pytest.fixture
def plan_day(tmp_path, monkeypatch):
    """plan-day.py (hyphenated name, so loaded via importlib) with ROOT pointed at tmp_path."""
    spec = importlib.util.spec_from_file_location("plan_day", REPO / "plan-day.py")
    mod = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "plan_day", mod)  # dataclasses needs the module registered
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "ROOT", tmp_path)
    return mod
