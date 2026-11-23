import json
from datetime import datetime, timedelta, timezone

import pytest

from tahoe_snow import __main__ as cli, config, pipeline, usage

NOW = datetime(2026, 12, 1, 12, tzinfo=timezone.utc)


def raising(error):
    def fail(*args, **kwargs):
        raise error
    return fail


@pytest.fixture
def stubbed(tmp_path, monkeypatch):
    def forecast(resort, snow_model, correction, now, weights=None):
        payload = {"key": resort.key, "name": resort.name, "region": resort.region, "tz": "America/Los_Angeles",
                   "lat": resort.lat, "lon": resort.lon, "kind": resort.kind, "pass": resort.pass_group,
                   "station": None, "weak_station_match": resort.weak_match, "observed": None,
                   "elevations": {"summit": {"windows": {"next72": {}}}}}
        return payload, []

    monkeypatch.setattr(config, "DATA", tmp_path)
    monkeypatch.setattr(pipeline, "DATA", tmp_path)
    monkeypatch.setattr(pipeline, "resort_forecast", forecast)
    monkeypatch.setattr(pipeline, "add_season", lambda resorts, now, last=None: {})
    return tmp_path


def test_a_run_writes_only_its_own_region(tmp_path, stubbed):
    pipeline.run("mammoth", NOW)
    assert sorted(p.name for p in (tmp_path / "forecast").iterdir()) == ["mammoth.json"]
    resorts = json.loads((tmp_path / "forecast/mammoth.json").read_text())["resorts"]
    assert {r["region"] for r in resorts} == {"mammoth"}


def test_a_run_archives_under_its_region_and_records_its_own_usage(tmp_path, stubbed):
    pipeline.run("mammoth", NOW)
    assert (tmp_path / "archive/2026/12/01_12z_mammoth.json").exists()
    assert [row["region"] for row in json.loads((tmp_path / "archive/usage.json").read_text())] == ["mammoth"]


def test_the_index_lists_every_mountain_and_when_each_region_was_built(tmp_path, stubbed):
    pipeline.run("tahoe", NOW)
    index = json.loads((tmp_path / "index.json").read_text())
    assert len(index["resorts"]) == len(config.RESORTS)
    assert index["regions"]["tahoe"]["published_utc"] and index["regions"]["mammoth"]["published_utc"] is None


def test_the_old_single_file_is_still_written_once_both_home_regions_exist(tmp_path, stubbed):
    pipeline.run("tahoe", NOW)
    assert not (tmp_path / "forecast.json").exists()
    pipeline.run("mammoth", NOW)
    home = len(config.resorts_in("tahoe")) + len(config.resorts_in("mammoth"))
    assert len(json.loads((tmp_path / "forecast.json").read_text())["resorts"]) == home


def test_the_most_overdue_region_is_due_first(tmp_path, stubbed):
    assert pipeline.due(NOW) in config.REGIONS
    for key in config.REGIONS:
        pipeline.run(key, NOW)
    assert pipeline.due(NOW + timedelta(hours=5)) is None
    assert pipeline.due(NOW + timedelta(hours=6, minutes=1)) in config.REGIONS


def test_a_region_where_every_mountain_fails_keeps_its_last_file(tmp_path, stubbed, monkeypatch):
    pipeline.run("mammoth", NOW)
    before = (tmp_path / "forecast/mammoth.json").read_text()
    monkeypatch.setattr(pipeline, "resort_forecast", raising(RuntimeError("refused")))
    with pytest.raises(SystemExit):
        pipeline.run("mammoth", NOW)
    assert (tmp_path / "forecast/mammoth.json").read_text() == before
    assert [row["region"] for row in json.loads((tmp_path / "archive/usage.json").read_text())] == ["mammoth"] * 2


def test_the_season_refresh_rewrites_each_region_file_and_the_merged_one(tmp_path, stubbed, monkeypatch):
    for key in ("tahoe", "mammoth"):
        pipeline.run(key, NOW)
    monkeypatch.setattr(pipeline, "add_season", lambda resorts, now, last=None: {"Sensor": {"swe": [1]}})
    pipeline.refresh_season(NOW)
    assert json.loads((tmp_path / "forecast/tahoe.json").read_text())["season_curves"] == {"Sensor": {"swe": [1]}}
    assert json.loads((tmp_path / "forecast.json").read_text())["season_curves"] == {"Sensor": {"swe": [1]}}


def test_prune_removes_old_archives_of_both_name_shapes(tmp_path, stubbed, monkeypatch):
    monkeypatch.setattr(cli, "DATA", tmp_path)
    folder = tmp_path / "archive/2020/01"
    folder.mkdir(parents=True)
    for name in ("05_06z.json", "05_06z_tahoe.json"):
        (folder / name).write_text("{}")
    (tmp_path / "archive/usage.json").write_text("[]")
    assert cli.prune(21) == 2
    assert not list(folder.iterdir())


def test_a_run_is_budgeted_by_the_region_about_to_run():
    big = max(config.REGIONS, key=lambda key: len(config.resorts_in(key)))
    ledger = []
    now = datetime(2026, 12, 1, 12, tzinfo=timezone.utc)
    assert usage.estimate(ledger, big) == round(len(config.resorts_in(big)) * usage.CALLS_PER_RESORT_RUN, 1)
    ledger = [{"utc": (now - timedelta(hours=1)).strftime(usage.STAMP), "calls": 300.0, "rate_limited": 0,
               "region": "tahoe"}]
    assert usage.estimate(ledger, "tahoe") == 300.0


def test_a_damaged_region_file_counts_as_not_built(tmp_path, stubbed):
    for key in config.REGIONS:
        pipeline.run(key, NOW)
    path = tmp_path / "forecast/mammoth.json"
    path.write_text(path.read_text()[:50])
    assert pipeline.due(NOW) == "mammoth"
    assert pipeline.write_index()["regions"]["mammoth"]["published_utc"] is None
