import gzip
import json
from datetime import datetime, timezone

from tahoe_snow import collect

NOW = datetime(2026, 11, 22, 19, 0, tzinfo=timezone.utc)


def test_lifts_and_trails_are_kept_by_area_with_grooming_marked():
    areas = [{"Name": "Summit", "Lifts": [{"Name": "Chair 1", "Status": "Wind Hold"}],
              "Trails": [{"Name": "Bowl", "Status": "Open", "Grooming": "Yes"}, {"Name": "Chute", "Status": "Closed", "Grooming": "No"}]},
             {"Name": "Empty", "Lifts": [], "Trails": []}]
    parts = collect.areas_parts("alpine", areas)
    assert parts["alpine.lifts"] == {"Summit": {"Chair 1": "Wind Hold"}}
    assert parts["alpine.trails"] == {"Summit": {"Bowl": "Open *", "Chute": "Closed"}}


def test_a_part_that_reads_the_same_is_written_once(tmp_path, monkeypatch):
    lifts = tmp_path / "lifts"
    lifts.mkdir()
    feed = {"MountainAreas": [{"Name": "All", "Lifts": [{"Name": "Gondola", "Status": "Open"}], "Trails": []}]}
    (lifts / "homewood.json").write_text(json.dumps({"updated": "2026-11-22T19:00:00Z", "resorts": {"homewood": feed}}))

    def offline(url):
        raise OSError("offline")
    monkeypatch.setattr(collect, "fetch", offline)
    history = tmp_path / "history"
    first = collect.collect(str(history), str(lifts), None, NOW)
    second = collect.collect(str(history), str(lifts), None, NOW)
    assert "homewood.lifts" in first["changed"] and second["changed"] == [] and "homewood.lifts" in second["read"]
    assert "ikon61" in first["failed"] and "forecast" in first["failed"]
    day = history / "2026-11-22"
    assert len((day / "homewood.lifts.jsonl").read_text().splitlines()) == 1
    assert len((day / "runs.jsonl").read_text().splitlines()) == 2


def test_the_new_england_lift_files_are_kept_like_the_others(tmp_path, monkeypatch):
    lifts = tmp_path / "lifts"
    lifts.mkdir()
    feed = lambda lift, trail: {"MountainAreas": [{"Name": "Main", "Lifts": [{"Name": lift, "Status": "Closed"}],
                                                   "Trails": [{"Name": trail, "Status": "Open", "Grooming": "Yes"}]}]}
    (lifts / "boyne.json").write_text(json.dumps({"updated": "2026-11-22T19:00:00Z", "resorts": {"loon": feed("Gondola", "Bucksaw")}}))
    (lifts / "killington.json").write_text(json.dumps({"updated": "2026-11-22T19:00:00Z", "resorts": {"pico": feed("Summit Express", "49er")}}))
    monkeypatch.setattr(collect, "fetch", lambda url: (_ for _ in ()).throw(OSError("offline")))
    history = tmp_path / "history"
    run = collect.collect(str(history), str(lifts), None, NOW)
    assert {"loon.lifts", "loon.trails", "pico.lifts", "pico.trails"} <= set(run["changed"])
    assert "boyne" not in run["failed"] and "killington" not in run["failed"]
    day = history / "2026-11-22"
    assert json.loads((day / "loon.lifts.jsonl").read_text())["data"] == {"Main": {"Gondola": "Closed"}}
    assert json.loads((day / "pico.trails.jsonl").read_text())["data"] == {"Main": {"49er": "Open *"}}


def test_the_seattle_lift_files_are_kept_like_the_others(tmp_path, monkeypatch):
    lifts = tmp_path / "lifts"
    lifts.mkdir()
    feed = lambda lift: {"MountainAreas": [{"Name": "Main", "Lifts": [{"Name": lift, "Status": "Closed"}], "Trails": []}]}
    (lifts / "missionridge.json").write_text(json.dumps({"updated": "2026-11-22T19:00:00Z", "resorts": {"missionridge": feed("Chair 2")}}))
    (lifts / "boyne.json").write_text(json.dumps({"updated": "2026-11-22T19:00:00Z", "resorts": {"alpental": feed("Armstrong Express")}}))
    monkeypatch.setattr(collect, "fetch", lambda url: (_ for _ in ()).throw(OSError("offline")))
    run = collect.collect(str(tmp_path / "history"), str(lifts), None, NOW)
    assert {"missionridge.lifts", "alpental.lifts"} <= set(run["changed"]) and "missionridge" not in run["failed"]


def test_a_new_forecast_is_kept_once_cut_to_the_hours_around_now(tmp_path, monkeypatch):
    hours = [f"2026-11-{day:02d}T{hour:02d}:00:00Z" for day in range(15, 30) for hour in range(24)]
    forecast = {"published_utc": "2026-11-22T17:52:11Z", "season_curves": {"big": 1},
                "resorts": [{"key": "palisades", "hours_utc": hours,
                             "elevations": {"summit": {"days": [{"date": "2026-11-22"}], "hourly": {"wind_mph": list(range(len(hours)))}}}}]}
    monkeypatch.setattr(collect, "fetch", lambda url: json.dumps(forecast).encode() if url == collect.FORECAST else (_ for _ in ()).throw(OSError("offline")))
    history = tmp_path / "history"
    assert "forecast" in collect.collect(str(history), None, None, NOW)["changed"]
    assert "forecast" not in collect.collect(str(history), None, None, NOW)["changed"]
    kept = json.load(gzip.open(history / "forecast" / "2026-11-22T17-52-11Z.json.gz", "rt"))
    resort = kept["resorts"][0]
    assert "season_curves" not in kept and resort["elevations"]["summit"]["days"] == [{"date": "2026-11-22"}]
    assert resort["hours_utc"][0] == "2026-11-22T07:00:00Z" and resort["hours_utc"][-1] == "2026-11-25T19:00:00Z"
    assert len(resort["elevations"]["summit"]["hourly"]["wind_mph"]) == len(resort["hours_utc"]) == 85
