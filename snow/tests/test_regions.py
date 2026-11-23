import pandas as pd

from tahoe_snow import config, pipeline, usage, season


def test_every_resort_belongs_to_a_configured_region():
    assert {r.region for r in config.RESORTS.values()} <= set(config.REGIONS)


def test_the_configured_regions_fit_the_daily_allowance():
    assert usage.planned() <= usage.PLAN_LIMIT


def test_the_home_regions_cost_what_the_ledger_measured():
    # 21 mountains, 4 runs a day, 1,089 calls a run
    home = {key: config.REGIONS[key] for key in ("tahoe", "mammoth")}
    assert round(usage.planned(home)) == round(21 * 4 * 51.9)


def test_avalanche_centers_come_from_the_regions_without_repeats():
    assert config.avalanche_centers() == ("SAC", "ESAC", "BAC", "MWAC")


def test_a_day_is_the_mountains_own_day():
    hours = pd.date_range("2026-12-01 03:00", periods=4, freq="h")       # UTC
    assert list(pipeline.local_days(hours, "America/Los_Angeles").strftime("%Y-%m-%d")) == ["2026-11-30"] * 4
    assert list(pipeline.local_days(hours, "America/New_York").strftime("%Y-%m-%d")) == ["2026-11-30", "2026-11-30", "2026-12-01", "2026-12-01"]


def test_a_regions_run_reads_only_its_own_sensors(monkeypatch):
    monkeypatch.setattr(season, "station_normal", lambda station, day: {"water": {"curve": {}}})
    own = {r.station for r in config.resorts_in("mammoth") if r.station}
    found = season.normals(pd.Timestamp("2026-11-21T16:00:00Z"), [r.key for r in config.resorts_in("mammoth")])
    assert set(found) == own and own


def test_a_sensor_network_that_is_down_is_asked_once(monkeypatch):
    asked = []

    def down(station, day):
        asked.append(station.name)
        raise RuntimeError("fetch failed: https://example.invalid None: timed out")

    monkeypatch.setattr(season, "station_normal", down)
    keys = [r.key for r in config.resorts_in("tahoe")]
    found = season.normals(pd.Timestamp("2026-11-21T16:00:00Z"), keys)
    assert len(asked) == len({config.ALL_STATIONS[r.station].source for r in config.resorts_in("tahoe") if r.station})
    assert found and not any(found.values())


def test_the_new_england_mountains_are_where_they_should_be():
    found = config.resorts_in("newengland")
    assert len(found) == 14
    for r in found:
        assert r.base_m < r.summit_m, r.key
        assert 42.7 < r.lat < 45.3 and -73.3 < r.lon < -69.9, r.key
        assert r.station is None, r.key


def test_the_last_season_figures_stand_in_while_the_sensors_cannot_be_reached(monkeypatch):
    resort = next(r for r in config.resorts_in("tahoe") if r.station)
    name = config.ALL_STATIONS[resort.station].name
    monkeypatch.setattr(season, "normals", lambda now, keys: {resort.station: {}})
    last = {"resorts": [{"key": resort.key, "season": {"water": {"pct": 80}}}], "season_curves": {name: {"water": [1, 2]}}}
    payload = {"key": resort.key, "observed": None}
    curves = pipeline.add_season([payload], pd.Timestamp("2026-11-21T16:00:00"), last)
    assert payload["season"] == {"water": {"pct": 80}} and curves == {name: {"water": [1, 2]}}
    fresh = {"key": resort.key, "observed": None}
    assert pipeline.add_season([fresh], pd.Timestamp("2026-11-21T16:00:00")) == {} and fresh["season"] is None
