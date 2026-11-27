"""The three forecasts are read from their pages as a visitor sees them, and scored against the sensors."""
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from tahoe_snow import compare
from tahoe_snow.config import ALL_RESORTS, ALL_STATIONS

FIXTURES = Path(__file__).parent / "fixtures"
SF = (FIXTURES / "compare_snow_forecast.html").read_text()
OS = (FIXTURES / "compare_open_snow.html").read_text()


def test_snow_forecasts_days_are_summed_from_its_parts_and_turned_to_inches():
    # Palisades, top, read the evening of November 26: 1 and 7 cm on the 29th, 12 cm on the 30th.
    read = compare.snow_forecast(SF)
    assert list(read["days"]) == ["2026-11-26", "2026-11-27", "2026-11-28", "2026-11-29", "2026-11-30", "2026-12-01"]
    assert read["days"]["2026-11-29"] == 3.1 and read["days"]["2026-11-30"] == 4.7 and read["days"]["2026-11-27"] == 0
    # The evening's page has two parts of today left: today is not a whole day, the five after it are.
    assert read["whole"] == ["2026-11-27", "2026-11-28", "2026-11-29", "2026-11-30", "2026-12-01"]


def test_a_snow_forecast_page_that_has_changed_is_refused():
    with pytest.raises(ValueError):
        compare.snow_forecast("<html>no table</html>")
    with pytest.raises(ValueError):
        compare.snow_forecast(SF.replace('class="snowu">cm', 'class="snowu">mm'))
    with pytest.raises(ValueError):
        compare.snow_forecast(SF.replace('colspan="3"', 'colspan="4"', 1))


def test_open_snows_five_day_totals_start_on_the_mountains_own_day():
    read = compare.open_snow(OS, "America/Los_Angeles")
    assert read == {"from": "2026-11-26", "elevation_ft": 7546, "d1_5": 14.0, "d6_10": 12.0, "d11_15": 10.0}
    with pytest.raises(ValueError):
        compare.open_snow("<html></html>", "America/Los_Angeles")
    with pytest.raises(ValueError):
        compare.open_snow(OS.replace("Next 1-5 Days", "This week"), "America/Los_Angeles")


def test_every_listed_mountain_is_a_resort_corrected_to_a_sensor_with_a_page_on_one_site_at_least():
    assert compare.SITES
    for key, site in compare.SITES.items():
        resort = ALL_RESORTS[key]
        assert resort.kind == "resort" and resort.station in ALL_STATIONS, key
        assert site.get("sf") or site.get("os"), key
        assert not site.get("sf") or site["sf_level"] in ("top", "mid", "bot"), key
        assert compare.level_near(resort, ALL_STATIONS[resort.station]) in resort.elevations(), key


def test_our_own_days_are_read_from_the_published_forecast_from_today_on():
    forecast = {"published_utc": "2026-11-26T21:00:00Z", "resorts": [{"key": "palisades", "elevations": {"mid": {"days": [
        {"date": "2026-11-25", "lead_day": -1, "snow_in": 3.0}, {"date": "2026-11-26", "lead_day": 0, "snow_in": 0.0},
        {"date": "2026-11-27", "lead_day": 1, "snow_in": 2.5}, {"date": "2026-11-28", "lead_day": 2, "snow_in": None}]}}}]}
    assert compare.ours(forecast, "palisades", "mid") == {"published_utc": "2026-11-26T21:00:00Z",
                                                          "days": {"2026-11-26": 0.0, "2026-11-27": 2.5}}
    assert compare.ours(forecast, "alta", "mid") is None and compare.ours({}, "palisades", "mid") is None


def snap(today: str, mine: dict, theirs: dict, whole: list, five: dict | None) -> dict:
    return {"read_utc": f"{today}T15:00:00Z", "mountains": {"palisades": {
        "level": "mid", "today": today, "ours": {"days": mine}, "snow_forecast": {"days": theirs, "whole": whole},
        "open_snow": five}}}


def test_each_source_is_scored_by_days_ahead_against_what_fell():
    days = [f"2026-11-{d}" for d in range(26, 31)]
    fell = dict(zip(days, [0.0, 2.0, 6.0, 0.0, 1.0]))
    mine = dict(zip(days, [0.0, 3.0, 4.0, 0.0, 1.0]))
    theirs = dict(zip(days, [0.0, 0.0, 9.0, 0.0, 0.0]))
    card = compare.score([snap("2026-11-26", mine, theirs, days[1:], {"from": "2026-11-26", "d1_5": 12.0, "d6_10": None})],
                         {"palisades": fell})
    # Tomorrow: we said 3 and 2 fell; they said 0.
    assert card["by_day"]["ours"]["1"] == {"n": 1, "mean_error_in": 1.0, "bias_in": 1.0}
    assert card["by_day"]["snow_forecast"]["1"] == {"n": 1, "mean_error_in": 2.0, "bias_in": -2.0}
    assert card["same_days"]["ours"]["2"]["bias_in"] == -2.0 and card["same_days"]["snow_forecast"]["2"]["bias_in"] == 3.0
    # Five days: 9 fell; we said 8, OpenSnow 12, Snow-Forecast 9.
    five = card["five_days"]["d1_5"]
    assert (five["ours"]["bias_in"], five["open_snow"]["bias_in"], five["snow_forecast"]["bias_in"]) == (-1.0, 3.0, 0.0)
    assert card["five_days"]["d6_10"]["open_snow"] is None
    assert "| 1 | 1.0 (+1.0, 1) | 2.0 (-2.0, 1) |" in compare.report(card)


def test_a_day_the_sensor_has_not_reported_or_a_part_day_is_not_scored():
    days = ["2026-11-26", "2026-11-27", "2026-11-28"]
    mine, theirs = dict(zip(days, [1.0, 1.0, 1.0])), dict(zip(days, [1.0, 1.0, 1.0]))
    card = compare.score([snap("2026-11-26", mine, theirs, ["2026-11-28"], None)], {"palisades": {"2026-11-27": 0.0}})
    # The 27th fell on a part-day of theirs; the 28th is not measured yet.
    assert card["by_day"]["ours"] == {"1": {"n": 1, "mean_error_in": 1.0, "bias_in": 1.0}}
    assert card["by_day"]["snow_forecast"] == {} and card["same_days"]["ours"] == {}
    # OpenSnow's totals that start before the snapshot's own day cover a day we have no forecast for: left out.
    late = snap("2026-11-26", mine, theirs, days, {"from": "2026-11-25", "d1_5": 3.0, "d6_10": 0.0})
    assert compare.score([late], {"palisades": dict(zip(days, [0.0] * 3))})["five_days"]["d1_5"]["open_snow"] is None


def test_open_snows_five_days_are_counted_from_the_day_its_page_starts_on():
    # Read in the evening, its page has already turned to tomorrow: the five days are the 27th to December 1.
    days = ["2026-11-26", "2026-11-27", "2026-11-28", "2026-11-29", "2026-11-30", "2026-12-01"]
    mine, fell = dict(zip(days, [9.0, 1.0, 1.0, 1.0, 1.0, 1.0])), dict(zip(days, [9.0, 0.0, 0.0, 0.0, 0.0, 0.0]))
    card = compare.score([snap("2026-11-26", mine, {}, [], {"from": "2026-11-27", "d1_5": 2.0, "d6_10": None})],
                         {"palisades": fell})
    five = card["five_days"]["d1_5"]
    assert five["ours"]["bias_in"] == 5.0 and five["open_snow"]["bias_in"] == 2.0 and five["snow_forecast"] is None


def test_a_run_writes_the_snapshot_once_and_keeps_the_sensors_days(tmp_path, monkeypatch):
    now = datetime(2026, 11, 27, 15, 0, tzinfo=timezone.utc)
    taken = []
    monkeypatch.setattr(compare, "snapshot", lambda at: taken.append(at) or snap("2026-11-27", {}, {}, [], None))
    monkeypatch.setattr(compare, "observed", lambda at: {"palisades": {"2026-11-26": 1.5}})
    compare.run(str(tmp_path), now)
    monkeypatch.setattr(compare, "observed", lambda at: {"palisades": {"2026-11-27": 0.0}})
    card = compare.run(str(tmp_path), now)
    assert len(taken) == 1 and card["snapshots"] == 1
    assert json.loads((tmp_path / "observed.json").read_text()) == {"palisades": {"2026-11-26": 1.5, "2026-11-27": 0.0}}
    assert (tmp_path / "score.md").read_text().startswith("# Snow forecasts against the sensors")


def test_a_snapshot_reads_one_page_of_each_site_and_survives_a_refusal(monkeypatch):
    monkeypatch.setattr(compare, "SITES", {"palisades": {"sf": "Squaw-Valley-USA", "sf_level": "mid", "os": "palisadestahoe"}})
    asked = []

    def fetch(url):
        asked.append(url)
        if "opensnow" in url:
            raise OSError("HTTP Error 403: Forbidden")
        if "snow-forecast" in url:
            return SF
        return json.dumps({"published_utc": "x", "resorts": []})

    taken = compare.snapshot(datetime(2026, 11, 27, 3, 0, tzinfo=timezone.utc), fetch=fetch, pause_s=0)
    entry = taken["mountains"]["palisades"]
    assert entry["today"] == "2026-11-26" and entry["open_snow"] is None and entry["ours"] is None
    assert entry["snow_forecast"]["days"]["2026-11-30"] == 4.7
    assert asked == ["https://raw.githubusercontent.com/N955PK/livefreeandfly/snow-data/forecast/tahoe.json",
                     "https://www.snow-forecast.com/resorts/Squaw-Valley-USA/6day/mid",
                     "https://opensnow.com/location/palisadestahoe/snow-summary"]


def test_the_sensors_snowfall_is_read_day_by_day(monkeypatch):
    monkeypatch.setattr(compare, "SITES", {"palisades": {"sf": "x", "sf_level": "mid"}})
    days = pd.date_range("2026-11-20", periods=6, freq="D")
    frame = pd.DataFrame({"swe_mm": [100.0, 100.0, 125.4, 125.4, 125.4, 125.4], "tavg_c": [-5.0] * 6}, index=days)
    seen = compare.observed(datetime(2026, 11, 27, 15, 0, tzinfo=timezone.utc), history=lambda station, day, start: frame)
    assert seen["palisades"]["2026-11-21"] == 0.0 and sum(seen["palisades"].values()) == pytest.approx(11.0, abs=0.3)
