import json
from datetime import datetime, timezone

from tahoe_snow import holdfit, reports

NOW = datetime(2026, 11, 22, 19, 0, tzinfo=timezone.utc)


def feed(**report) -> dict:
    stake = {"BaseIn": "32", "Last24HoursIn": "6", "Last48HoursIn": "--", "Last72HoursIn": "14", "SinceLiftsClosedIn": "4"}
    return {"OperatingStatus": "Open",
            "SnowReport": {"LastUpdate": "2026-11-22T07:15:58-0800", "BaseConditions": "Powder", "SeasonTotalIn": "71",
                           "StormTotalIn": "--", "TotalOpenLifts": 11, "TotalLifts": 39, "TotalOpenTrails": 71,
                           "TotalTrails": 296, "GroomedTrails": 17, "BaseArea": stake,
                           "MidMountainArea": {**stake, "BaseIn": "37"},
                           "SummitArea": {name: "--" for name in stake},
                           "Report": "<div>Summit Express is on <b>wind hold</b>; patrol is doing avalanche mitigation.</div>",
                           "Alert": "--", **report}}


FORECAST = {"published_utc": "2026-11-22T17:52:11Z", "resorts": [{"key": "palisades", "elevations": {"summit": {"days": [
    {"date": "2026-11-22", "snow_in": 5.5, "powder": {"night_in": 4.0, "day_in": 1.5, "wind_mph": 21, "gust_mph": 29, "temp_f": 23}}]}}}]}


def test_a_report_becomes_one_line_of_measurements_beside_the_forecast():
    line = reports.row("palisades", feed(), FORECAST, NOW)
    assert line["day"] == "2026-11-22" and line["surface"] == "Powder" and line["status"] == "Open"
    assert line["stakes"]["base"] == {"base_in": 32.0, "last24_in": 6.0, "last72_in": 14.0, "since_close_in": 4.0}
    assert line["stakes"]["mid"]["base_in"] == 37.0
    assert line["season_in"] == 71.0 and line["storm_in"] is None and line["open_lifts"] == 11.0
    assert line["forecast"]["summit"] == {"snow_in": 5.5, "night_in": 4.0, "day_in": 1.5, "wind_mph": 21, "gust_mph": 29, "temp_f": 23}


def test_a_stake_that_reports_nothing_is_left_out():
    assert "summit" not in reports.row("palisades", feed(), FORECAST, NOW)["stakes"]


def test_the_report_keeps_its_subjects_and_not_its_words():
    line = reports.row("palisades", feed(), FORECAST, NOW)
    assert line["subjects"] == ["wind", "wind_hold", "avalanche_work"]
    assert "Summit Express" not in json.dumps(line)


def test_a_feed_with_no_dated_report_is_no_line():
    assert reports.row("palisades", {"SnowReport": {}}, FORECAST, NOW) is None


def test_a_report_already_recorded_is_not_recorded_again(tmp_path):
    path = tmp_path / "reports.jsonl"
    line = reports.row("palisades", feed(), FORECAST, NOW)
    path.write_text(json.dumps(line) + "\n")
    assert ("palisades", line["report"]) in reports.seen(str(path))
    assert reports.seen(str(tmp_path / "missing.jsonl")) == set()


def hold_row(day: int, gust: float, held: dict, running: int = 10) -> dict:
    return {"utc": f"2026-12-{day:02d}T18:00:00Z", "resort": "palisades", "open": running - len(held), "hold": len(held),
            "soon": 0, "closed": 5, "held": held, "gust_mph": gust, "live_gust_mph": gust - 5}


def test_only_holds_the_resort_blames_on_wind_count():
    assert holdfit.wind_held(hold_row(1, 50, {"KT-22": "Wind Hold", "Siberia": "Delayed", "Granite": "Patrol Hold"})) == 1


def test_a_windy_band_with_holds_on_enough_days_proposes_a_level():
    rows = [hold_row(day, 45, {"KT-22": "Wind Hold"}) for day in (1, 2, 3) for _ in range(3)]
    found = holdfit.summary(rows)["palisades"]
    assert found["bands"]["40-50"]["enough"] and found["bands"]["40-50"]["any_hold"] == 1.0
    assert found["propose"] == {"possible": 40, "likely": None, "shut": None}


def test_one_windy_afternoon_proposes_nothing():
    rows = [hold_row(1, 55, {"KT-22": "Wind Hold", "Siberia": "Wind Hold"}) for _ in range(12)]
    assert holdfit.summary(rows)["palisades"]["propose"] == {"possible": None, "likely": None, "shut": None}


def test_calm_morning_delays_are_not_wind_holds():
    rows = [hold_row(day, 12, {"Chair 14": "Delayed"}) for day in (1, 2, 3) for _ in range(3)]
    found = holdfit.summary(rows)["palisades"]
    assert found["wind_hold_rows"] == 0 and found["other_hold_rows"] == 9
    assert found["propose"]["possible"] is None
