"""Tuckerman Ravine and the Mt. Washington summit's record: read and shown, never used to correct the forecast."""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from tahoe_snow import biascorrect, cache, config, pipeline, season
from tahoe_snow.config import ALL_STATIONS, MODELS, RESORTS
from tahoe_snow.sources import acis, nws

FIXTURES = Path(__file__).parent / "fixtures"
SUMMIT = "USW00014755:ACIS"
NOW = pd.Timestamp("2026-11-23T20:00:00")


def fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def fetch_fails(*args, **kwargs):
    raise RuntimeError("fetch failed: https://example.invalid None: timed out")


@pytest.fixture
def feeds(monkeypatch):
    monkeypatch.setattr(acis, "get_json", lambda *a, **k: fixture("acis_mtwashington_2026-11-23.json"))
    monkeypatch.setattr(nws, "get_json", lambda *a, **k: fixture("nws_kmwn_2026-11-23.json"))


def test_missing_is_missing_and_a_trace_is_nothing_but_flagged():
    frame = acis.parse(fixture("acis_mtwashington_traces.json"))
    day = lambda d: frame.loc[pd.Timestamp(d)]
    assert np.isnan(day("2025-10-13")["snowfall_cm"]) and not day("2025-10-13")["snowfall_trace"]
    assert day("2025-10-15")["snowfall_cm"] == 0.0 and day("2025-10-15")["snowfall_trace"]
    assert day("2025-10-14")["snowfall_cm"] == 0.0 and not day("2025-10-14")["snowfall_trace"]
    assert day("2025-10-17")["prec_mm"] == 0.0 and day("2025-10-17")["prec_trace"]
    assert day("2025-10-16")["snowfall_cm"] == pytest.approx(0.4 * 2.54) and day("2025-10-16")["depth_cm"] == 0.0
    assert day("2025-10-20")["prec_mm"] == pytest.approx(2.37 * 25.4)


def test_the_latest_day_is_found_behind_the_missing_days_and_dated():
    frame = acis.parse(fixture("acis_mtwashington_2026-11-23.json"))
    assert frame.index[-1] == pd.Timestamp("2026-11-23")          # asked through today, the last three missing
    assert acis.latest_day(frame) == pd.Timestamp("2026-11-20")
    latest = pipeline.latest_daily(frame)
    assert latest == {"date": "2026-11-20", "depth_in": 6.0, "snowfall_in": 0.0, "snowfall_3d_in": 0.0,
                      "water_in": 0.0, "water_3d_in": 0.0}
    storm = pipeline.latest_daily(frame.loc[:"2026-11-16"])
    assert storm["date"] == "2026-11-16" and storm["snowfall_3d_in"] == pytest.approx(0.2 + 2.9 + 0.7)
    assert storm["water_3d_in"] == pytest.approx(0.02 + 0.18 + 0.63) and storm["depth_in"] == 7.0


def test_a_three_day_total_needs_all_three_days():
    latest = pipeline.latest_daily(acis.parse(fixture("acis_mtwashington_traces.json")))
    assert latest["date"] == "2025-10-20" and latest["snowfall_in"] == 0.0
    assert latest["snowfall_3d_in"] is None and latest["water_3d_in"] is None and latest["depth_in"] is None


def test_the_hourly_feed_reads_each_value_on_its_own():
    frame = nws.parse(fixture("nws_kmwn_2026-11-23.json"))
    assert frame.index[-1] == pd.Timestamp("2026-11-23T19:54:00") and frame["temp_c"].iloc[-1] == 1
    assert frame["wind_kmh"].isna().any() and frame["wind_kmh"].notna().any()


def test_tuckerman_gets_the_summits_dated_record_and_nothing_as_a_current_reading(feeds):
    found = pipeline.observed(RESORTS["tuckerman"], NOW, None)
    assert found["station"] == "Mt. Washington summit" and found["elevation_ft"] == 6270
    assert found["above_top_ft"] == 1100
    assert found["daily"]["date"] == "2026-11-20" and found["daily"]["depth_in"] == 6.0
    # Everything the page reads as now, or as the night just past, stays empty: the record is three days behind.
    for field in ("depth_in", "water_in", "depth_gain_24h_in", "depth_gain_72h_in", "water_gain_24h_in",
                  "water_gain_72h_in", "depth_in_hourly"):
        assert found[field] is None, field
    assert found["temp_f"] == 34 and found["as_of_utc"] == "2026-11-23T19:54:00Z"


def test_an_old_hourly_temperature_is_not_shown(feeds):
    found = pipeline.observed(RESORTS["tuckerman"], NOW + pd.Timedelta(hours=6), None)
    assert found["temp_f"] is None and found["as_of_utc"] is None and found["daily"]


def test_a_failed_feed_costs_only_its_own_figures(monkeypatch, feeds):
    monkeypatch.setattr(nws, "get_json", fetch_fails)
    found = pipeline.observed(RESORTS["tuckerman"], NOW, None)
    assert found["daily"]["date"] == "2026-11-20" and found["temp_f"] is None
    monkeypatch.setattr(acis, "get_json", fetch_fails)
    assert pipeline.observed(RESORTS["tuckerman"], NOW, None) is None


def test_the_summit_record_failing_leaves_tuckerman_without_season_figures_and_raises_nothing(monkeypatch):
    monkeypatch.setattr(acis, "get_json", fetch_fails)
    found = season.normals(NOW, ["tuckerman", "sugarloaf"])
    assert found == {SUMMIT: {}}
    payload = {"key": "tuckerman", "observed": None}
    assert pipeline.add_season([payload], NOW) == {} and payload["season"] is None
    last = {"resorts": [{"key": "tuckerman", "season": {"snowfall": {"now_in": 9.0}}}],
            "season_curves": {"Mt. Washington summit": {"snowfall": {"normal": []}}}}
    curves = pipeline.add_season([payload], NOW, last)
    assert payload["season"] == {"snowfall": {"now_in": 9.0}} and "Mt. Washington summit" in curves


def _winters(through: str) -> pd.DataFrame:
    """Forty winters with an inch of snow a day from November through March, a foot on the ground then, and the
    record's last three days missing."""
    days = pd.date_range("1985-10-01", "2026-11-23", freq="D")
    snowy = days.month.isin([11, 12, 1, 2, 3])
    frame = pd.DataFrame({"snowfall_cm": np.where(snowy, 2.54, 0.0), "depth_cm": np.where(snowy, 30.48, 0.0),
                          "prec_mm": 2.0, "tmax_c": 0.0, "tmin_c": -5.0, "snowfall_trace": False,
                          "prec_trace": False}, index=days)
    frame.loc[frame.index > pd.Timestamp(through), ["snowfall_cm", "depth_cm", "prec_mm"]] = np.nan
    return frame


def test_season_to_date_is_the_measured_snowfall_since_october_as_of_the_latest_day(monkeypatch):
    monkeypatch.setattr(acis, "daily", lambda *a, **k: _winters("2026-11-20"))
    normal = season.station_normal(ALL_STATIONS[SUMMIT], pd.Timestamp("2026-11-23"))
    assert set(normal) == {"depth", "snowfall"}                       # no snow pillow, so no water
    snowfall = normal["snowfall"]
    assert snowfall["as_of_date"] == "2026-11-20" and snowfall["latest_in"] == 20.0
    assert snowfall["normal_in"] == pytest.approx(20.0, abs=0.5)      # a usual November 20, not November 23
    assert snowfall["peak_in"] == pytest.approx(151.0, abs=1.0)       # November through March
    assert normal["depth"]["latest_in"] == 12.0 and normal["depth"]["as_of_date"] == "2026-11-20"
    told = season.summary({"daily": {"depth_in": 12.0}}, normal)
    assert told["snowfall"] == {"now_in": 20.0, "normal_in": 20.0, "pct_normal": 100, "peak_in": snowfall["peak_in"],
                                "pct_peak": round(100 * 20.0 / snowfall["peak_in"]), "peak_date": snowfall["peak_date"],
                                "as_of_date": "2026-11-20"}
    assert told["depth"]["now_in"] == 12.0 and told["depth"]["as_of_date"] == "2026-11-20"


class Sentinel(Exception):
    pass


def _liquid_station(resort, monkeypatch) -> str | None:
    """The station the forecast's water would be corrected against, caught as ``model_snow`` hands it over."""
    seen = []

    def spy(precip, model, station, today, correction, tz):
        seen.append(station)
        raise Sentinel

    hours = pd.date_range("2026-11-23", periods=3, freq="h")
    frame = pd.DataFrame({"precipitation": 1.0, "temperature_700hPa": -5.0, "temperature_2m": 0.0}, index=hours)
    with monkeypatch.context() as patch:
        patch.setattr(pipeline, "corrected_liquid", spy)
        with pytest.raises(Sentinel):
            pipeline.model_snow(frame, "gfs_seamless", resort, None, NOW.normalize(), object())
    return seen[0]


def test_the_summit_never_corrects_tuckermans_forecast(monkeypatch):
    tuckerman = RESORTS["tuckerman"]
    assert tuckerman.station == SUMMIT and not ALL_STATIONS[SUMMIT].corrects
    assert pipeline.correcting_station(tuckerman) is None
    assert _liquid_station(tuckerman, monkeypatch) is None
    # Even with a fitted correction to hand, a station it was not fitted to would get the pooled curve; Tuckerman's
    # water goes through untouched and it is not said to be corrected.
    correction = biascorrect.from_json(json.loads((MODELS / "bias.json").read_text()))
    precip = pd.Series([0.0, 4.0, 9.0, 2.0, 0.5], index=pd.date_range("2026-11-24T10:00", periods=5, freq="5h"))
    today = pd.Timestamp("2026-11-23")
    model = next(model for model, _ in correction.maps)
    kept = pipeline.corrected_liquid(precip, model, pipeline.correcting_station(tuckerman), today, correction,
                                     "America/New_York")
    assert kept.equals(precip)
    assert not pipeline.corrected_liquid(precip, model, SUMMIT, today, correction, "America/New_York").equals(precip)
    assert pipeline.water_correction(tuckerman, correction) is None


def test_every_other_mountain_is_corrected_as_before(monkeypatch):
    for resort in RESORTS.values():
        if resort.key == "tuckerman":
            continue
        assert pipeline.correcting_station(resort) == resort.station, resort.key
        if resort.region == "newengland":
            assert resort.station is None, resort.key
    palisades = RESORTS["palisades"]
    assert _liquid_station(palisades, monkeypatch) == palisades.station
    assert {s.source for s in [*config.STATIONS.values(), *config.MAMMOTH_STATIONS.values()]} <= {"snotel", "cdec"}
    assert all(s.corrects for key, s in ALL_STATIONS.items() if key != SUMMIT)


def test_the_index_says_which_station_corrects(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "DATA", tmp_path)
    resorts = {r["key"]: r for r in pipeline.write_index()["resorts"]}
    assert resorts["tuckerman"]["station"] == "Mt. Washington summit" and not resorts["tuckerman"]["station_corrects"]
    assert resorts["palisades"]["station_corrects"] and not resorts["june"]["station_corrects"]


def test_the_index_says_a_sensor_with_no_fitted_correction_corrects_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "DATA", tmp_path)
    resorts = {r["key"]: r for r in pipeline.write_index()["resorts"]}
    assert resorts["palisades"]["water_corrected"] and resorts["mammoth"]["water_corrected"]
    assert resorts["crystal"]["station_corrects"] and not resorts["crystal"]["water_corrected"]
    assert not resorts["june"]["water_corrected"] and not resorts["tuckerman"]["water_corrected"]


def test_a_posted_body_is_part_of_what_the_copy_is_kept_under():
    url = "https://data.rcc-acis.org/StnData"
    one = cache._path("acis", url, None, ".json", {"sid": "a", "edate": "2026-11-22"})
    two = cache._path("acis", url, None, ".json", {"sid": "a", "edate": "2026-11-23"})
    assert one != two and cache._path("x", url, {"a": 1}, ".json") == cache._path("x", url, {"a": 1}, ".json", None)
