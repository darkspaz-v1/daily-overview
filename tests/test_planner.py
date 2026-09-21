"""planner.md parsing and editing in overview_app.Planner, against a FAKE planner."""


def test_categorized_scheduled_today_and_upcoming(planner):
    c = planner.categorized()
    assert c["scheduledToday"] == ["09:30 - Team standup", "Dentist (all day)"]
    # upcoming = within the next 7 days after today; excludes today, past, and >7 days out
    assert c["upcoming"] == ["2026-03-14 18:00 Pickleball"]


def test_categorized_ignores_invalid_dates(planner):
    c = planner.categorized()
    assert not any("Impossible" in s for s in c["scheduledToday"] + c["upcoming"])


def test_categorized_task_due_buckets(planner):
    c = planner.categorized()
    assert c["dueToday"] == ["Write lab report"]
    assert c["overdue"] == ["File taxes (was due 2026-03-01)"]
    assert "Book flights (due 2026-04-01)" in c["open"]
    assert "Buy milk" in c["open"]
    assert "Finished thing" not in " ".join(c["open"] + c["dueToday"])


def test_categorized_open_count(planner):
    c = planner.categorized()
    assert c["openCount"] == len(c["overdue"]) + len(c["dueToday"]) + len(c["open"])
    assert c["openCount"] == 5  # taxes, lab report, flights, milk, bad-date task


def test_categorized_bad_due_date_stays_open(planner):
    c = planner.categorized()
    # an unparseable due date is neither overdue nor due today, but is still listed
    assert any("Bad date task" in t for t in c["open"])


def test_categorized_recurring(planner):
    assert planner.categorized()["recurring"] == ["Take vitamins", "Stretch for 5 minutes"]


def test_missing_planner_is_empty(overview, tmp_path, monkeypatch):
    monkeypatch.setattr(overview, "PLANNER", str(tmp_path / "nope.md"))
    c = overview.Planner().categorized()
    assert c["openCount"] == 0 and c["scheduledToday"] == []


def test_list_open_only_unchecked_tasks(planner):
    open_tasks = planner.list_open()
    assert "Buy milk" in open_tasks
    assert not any("Finished thing" in t for t in open_tasks)
    assert not any("Take vitamins" in t for t in open_tasks)  # recurring is not the Tasks section


def test_add_task_with_due_appends_inside_tasks_section(planner, overview):
    r = planner.add_task("Call mom", "2026-03-12")
    assert r == {"ok": True, "added": "Call mom", "due": "2026-03-12"}
    assert "Call mom (due 2026-03-12)" in planner.categorized()["open"]
    lines = overview.planner_path.read_text(encoding="utf-8").splitlines()
    assert lines[-1] == "- [ ] Call mom (due: 2026-03-12)"


def test_add_task_rejects_empty(planner):
    assert planner.add_task("   ")["ok"] is False
    assert planner.add_task(None)["ok"] is False


def test_add_task_creates_section_when_missing(overview, tmp_path, monkeypatch):
    p = tmp_path / "empty.md"
    p.write_text("# Planner\n", encoding="utf-8")
    monkeypatch.setattr(overview, "PLANNER", str(p))
    overview.Planner().add_task("First")
    assert p.read_text(encoding="utf-8").splitlines()[-2:] == ["## Tasks", "- [ ] First"]


def test_add_event_lands_in_scheduled_section(planner, overview):
    planner.add_event("2026-03-12", "Office hours", "14:00")
    text = overview.planner_path.read_text(encoding="utf-8")
    scheduled_block = text.split("## Scheduled")[1].split("## Tasks")[0]
    assert "- 2026-03-12 14:00 Office hours" in scheduled_block
    assert planner.add_event(None, "x")["ok"] is False


def test_complete_task_checks_first_match(planner, overview):
    r = planner.complete_task("milk")
    assert r["ok"] and r["completed"] == "Buy milk"
    assert "- [x] Buy milk" in overview.planner_path.read_text(encoding="utf-8")
    assert "Buy milk" not in planner.list_open()


def test_complete_task_no_match(planner):
    r = planner.complete_task("zzz nothing")
    assert r["ok"] is False and "zzz nothing" in r["error"]


def test_complete_task_is_case_insensitive_and_skips_done(planner):
    assert planner.complete_task("FINISHED THING")["ok"] is False  # already [x]
    assert planner.complete_task("BUY MILK")["ok"] is True


def test_remove_task_deletes_line(planner, overview):
    assert planner.remove_task("milk")["ok"]
    assert "Buy milk" not in overview.planner_path.read_text(encoding="utf-8")


def test_remove_any_finds_scheduled_items_too(planner, overview):
    r = planner.remove_any("pickleball")
    assert r["ok"] and "Pickleball" in r["removed"]
    assert "Pickleball" not in overview.planner_path.read_text(encoding="utf-8")


def test_remove_any_empty_query(planner):
    assert planner.remove_any("")["ok"] is False


def test_section_bounds_is_case_insensitive_and_exclusive_end(planner):
    lines = planner._read()
    s, e = planner._section_bounds(lines, "scheduled")
    assert lines[s].strip() == "## Scheduled"
    assert lines[e].strip() == "## Tasks"
    assert planner._section_bounds(lines, "nonexistent") == (None, None)


def test_api_task_buttons_round_trip(overview):
    api = overview.Api()
    out = api.task_add("Water plants", None)
    assert out["ok"] and "Water plants" in out["tasks"]["open"]
    out = api.task_complete("water plants")
    assert out["ok"] and "Water plants" not in out["tasks"]["open"]
