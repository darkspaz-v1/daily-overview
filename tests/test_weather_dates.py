"""Pure date/time resolution helpers behind the assistant's get_weather tool, plus Api file helpers."""
import pytest


@pytest.fixture
def api(overview):
    return overview.Api()


# frozen today is Wednesday 2026-03-11
@pytest.mark.parametrize("word,expected", [
    (None, "2026-03-11"), ("today", "2026-03-11"), ("tonight", "2026-03-11"),
    ("tomorrow", "2026-03-12"), ("Friday", "2026-03-13"), ("mon", "2026-03-16"),
    ("wednesday", "2026-03-11"), ("2026-03-20", "2026-03-20"),
    ("on 2026-04-02 please", "2026-04-02"), ("gibberish", "2026-03-11"),
])
def test_resolve_date(api, word, expected):
    assert api._resolve_date(word).isoformat() == expected


@pytest.mark.parametrize("word,expected", [
    (None, None), ("", None), ("noon", 12), ("midnight", 0), ("morning", 9),
    ("evening", 19), ("3pm", 15), ("12am", 0), ("12pm", 12), ("15:00", 15),
    ("7:30 am", 7), ("99", 23), ("whenever", None),
])
def test_resolve_hour(api, word, expected):
    assert api._resolve_hour(word) == expected


def test_weather_lookup_without_data(api, monkeypatch):
    monkeypatch.setattr(api, "get_data", lambda: {})
    assert api._weather_lookup("today")["ok"] is False


def test_weather_lookup_outside_forecast(api, monkeypatch):
    monkeypatch.setattr(api, "get_data", lambda: {"weather": {"ok": True, "forecast": [], "hourly": []}})
    r = api._weather_lookup("2026-05-01")
    assert r["ok"] is False and "only the next 7 days" in r["error"]


def test_weather_lookup_picks_closest_hour(api, monkeypatch):
    weather = {"ok": True, "place": "Testville",
               "forecast": [{"date": "2026-03-12", "hi": 10, "lo": 2, "rain": 20, "desc": "Cloudy"}],
               "hourly": [{"t": "2026-03-12T09:00", "temp": 4, "feels": 2, "rain": 5, "code": 0},
                          {"t": "2026-03-12T15:00", "temp": 9, "feels": 8, "rain": 70, "code": 63}]}
    monkeypatch.setattr(api, "get_data", lambda: {"weather": weather})
    r = api._weather_lookup("tomorrow", "3pm")
    assert r["at"]["time"] == "15:00" and r["at"]["conditions"] == "Rain"
    assert r["high_c"] == 10
    assert r["rain_hours"] == [{"time": "15:00", "chance_pct": 70}]


def test_exec_tool_dispatch(api):
    assert api._exec_tool("nope", {})["ok"] is False
    assert api._exec_tool("add_task", '{"text": "via json string"}')["ok"] is True
    assert "via json string" in api._exec_tool("list_tasks", {})["tasks"]
    # a non-JSON string argument falls back to {"text": <string>}
    assert api._exec_tool("add_task", "plain words")["added"] == "plain words"


def test_state_round_trip(api, overview, tmp_path, monkeypatch):
    monkeypatch.setattr(overview, "STATE", str(tmp_path / "layout.json"))
    assert api.load_state() == {}
    assert api.save_state('{"theme": "amber"}')["ok"] is True
    assert api.load_state() == {"theme": "amber"}


def test_get_data_reports_error_instead_of_raising(api, overview, tmp_path, monkeypatch):
    monkeypatch.setattr(overview, "LATEST", str(tmp_path / "missing.json"))
    assert "error" in api.get_data()


def test_get_data_reads_bom_json(api, overview, tmp_path, monkeypatch):
    p = tmp_path / "latest.json"
    p.write_bytes(b"\xef\xbb\xbf" + b'{"summary": "hi"}')  # PowerShell writes a UTF-8 BOM
    monkeypatch.setattr(overview, "LATEST", str(p))
    assert api.get_data() == {"summary": "hi"}
