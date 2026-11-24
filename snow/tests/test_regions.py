import pandas as pd

from tahoe_snow import config, pipeline, usage, season


def test_every_resort_belongs_to_a_configured_region():
    assert {r.region for r in config.RESORTS.values()} <= set(config.REGIONS)


def test_the_configured_regions_fit_the_daily_allowance():
    assert usage.planned() <= usage.PLAN_LIMIT


def test_the_home_regions_cost_what_the_ledger_measured():
    # 21 mountains cost 1,089 calls a run when each asked for its own weather; 14 ask now, 3 runs a day
    home = {key: config.REGIONS[key] for key in ("tahoe", "mammoth")}
    assert round(usage.planned(home)) == round(14 * 3 * 51.9)


def test_avalanche_centers_come_from_the_regions_without_repeats():
    assert config.avalanche_centers() == ("SAC", "ESAC", "BAC", "MWAC", "NWAC")


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
    assert len(found) == 29
    for r in found:
        assert r.base_m < r.summit_m, r.key
        assert 42.7 < r.lat < 45.3 and -73.3 < r.lon < -69.9, r.key
        # Tuckerman Ravine is shown the Mt. Washington summit's readings, which correct nothing.
        assert pipeline.correcting_station(r) is None, r.key
        assert r.station is None or r.key == "tuckerman", r.key


def test_the_seattle_mountains_are_where_they_should_be():
    found = config.resorts_in("seattle")
    assert len(found) == 13
    for r in found:
        assert r.base_m < r.summit_m, r.key
        # From Mt. Baker in the north to Mt. Adams and Mt. St. Helens in the south, Hurricane Ridge in the west.
        assert 46.1 < r.lat < 48.9 and -123.6 < r.lon < -120.3, r.key
        assert r.station is None or r.station in config.ALL_STATIONS, r.key
    volcanoes = {"rainier", "mtbaker", "glacierpeak", "adams", "sthelens"}
    assert {r.key for r in found if r.kind == "backcountry"} == volcanoes
    assert all(r.pass_group == "Backcountry" for r in found if r.kind == "backcountry")
    # Mid on Mt. Rainier is about Camp Muir, 10,188 ft, the top of the Muir Snowfield.
    assert abs(config.RESORTS["rainier"].mid_m - 3105) < 100


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


def test_every_region_is_built_at_its_own_hours_as_often_as_its_interval_says():
    for region in config.REGIONS.values():
        assert region.at and len(region.at) * region.every_h == 24, region.key
        assert list(region.at) == sorted(region.at), region.key


def test_the_latest_build_hour_is_told_on_the_regions_own_clock():
    now = pd.Timestamp("2026-12-01 12:30")                                        # 4:30 am Pacific, 7:30 am Eastern
    assert pipeline.last_slot(config.REGIONS["tahoe"], now) == pd.Timestamp("2026-12-01 05:00")        # 9 pm Pacific
    assert pipeline.last_slot(config.REGIONS["newengland"], now) == pd.Timestamp("2026-12-01 09:00")   # 4 am Eastern
    assert pipeline.last_slot(config.REGIONS["seattle"], pd.Timestamp("2026-12-01 13:00")) == pd.Timestamp("2026-12-01 13:00")
