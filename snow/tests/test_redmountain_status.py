import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import redmountain

FIXTURES = Path(__file__).parent / "fixtures"
# The lift report as it came, and the mountain report without its tables of each month's snowfall.
PAGES = {name: (FIXTURES / f"redmountain_{name}.json").read_text() for name in redmountain.URLS}
NOW = datetime(2026, 11, 25, 1, 0, tzinfo=timezone.utc)


def page(name: str, old: str, new: str, count: int = -1) -> dict:
    assert old in PAGES[name]
    return {**PAGES, name: PAGES[name].replace(old, new, count)}


def test_the_lift_report_is_asked_for_as_a_plain_request():
    assert redmountain.URLS["lifts"] == ("https://api.redresort.com/graphql/query?query=%7Blifts%7Bname%20status%20"
                                         "runs%7BsortOrder%20run%7Bname%20difficulty%20status%20grooming%7D%7D%7D%7D")


def test_the_closed_mountain_reads_each_lift_with_the_runs_it_serves():
    # RED's reports on 2026-11-24, before it opens: 9 lifts, all closed, and 107 runs, 45 of them still given as
    # open from the end of last season.
    feed = redmountain.parse(PAGES, NOW)
    assert feed["Name"] == "RED Mountain" and feed["LastUpdate"] == "2026-11-25T01:00:00Z"
    assert [(area["Name"], len(area["Lifts"]), len(area["Trails"])) for area in feed["MountainAreas"]] == [
        ("Magic Carpet", 1, 1), ("T-Bar", 1, 2), ("Red Chair (double)", 1, 12), ("Silverlode Chair (quad)", 1, 10),
        ("Topping Creek Chair (triple)", 1, 7), ("Motherlode Chair (triple)", 1, 41),
        ("Paradise Chair (triple)", 1, 16), ("Grey Chair (quad)", 1, 15), ("Kirkup Cat (Fri - Sun)", 1, 3)]
    lifts = [lift for area in feed["MountainAreas"] for lift in area["Lifts"]]
    assert lifts[2] == {"Name": "Red Chair (double)", "Status": "Closed", "StatusEnglish": "closed", "Difficulty": None}
    assert {lift["StatusEnglish"] for lift in lifts} == {"closed"}
    trails = [trail for area in feed["MountainAreas"] for trail in area["Trails"]]
    # 111 listings of 107 runs: T-Bar Slope, Boardwalk, Jumbo Traverse and Ledges are each under two lifts.
    assert len(trails) == 107 and len({trail["Name"] for trail in trails}) == 107
    assert feed["MountainAreas"][2]["Trails"][0] == {"Name": "Back Trail", "Status": "Open", "StatusEnglish": "open",
                                                     "Difficulty": "Blue", "Grooming": "Yes"}
    assert sum(trail["StatusEnglish"] == "open" for trail in trails) == 45
    assert sum(trail["Grooming"] == "Yes" for trail in trails) == 20
    assert {trail["Difficulty"] for trail in trails} == {"Green", "Blue", "Black", "Double black", ""}
    assert [trail["Name"] for trail in trails if trail["Difficulty"] == ""] == ["Terrain Park"]


def test_the_snow_report_is_in_inches_from_the_report_s_centimetres():
    snow = redmountain.parse(PAGES, NOW)["SnowReport"]
    # "2026-11-22T21:11:31-08:00".
    assert snow["LastUpdate"] == "2026-11-23T05:11:31Z" and snow["Resortwide"] is True
    # 18 cm at the alpine plot and no new snow.
    assert snow["BaseArea"] == {"Name": "Alpine weather plot", "BaseIn": 7.1, "Last24HoursIn": 0.0,
                                "Last48HoursIn": 0.0, "Last72HoursIn": 0.0, "Last7DaysIn": 0.0, "OvernightIn": 0.0}
    assert snow["SeasonTotalIn"] == 0.0 and snow["BaseConditions"] is None
    assert snow["Report"].startswith("Daily snow report updates will begin") and "<" not in snow["Report"]
    fallen = redmountain.parse(page("snow", "\"Metric24hours\": 0,", "\"Metric24hours\": 12.5,"), NOW)["SnowReport"]
    assert fallen["BaseArea"]["Last24HoursIn"] == 4.9


def test_a_lift_on_hold_and_a_run_in_marginal_conditions_are_read():
    pages = page("lifts", "\"name\":\"T-Bar\",\"status\":\"CLOSED\"", "\"name\":\"T-Bar\",\"status\":\"ON_HOLD\"")
    pages["lifts"] = (pages["lifts"]
                      .replace("\"name\":\"Magic Carpet\",\"status\":\"CLOSED\"", "\"name\":\"Magic Carpet\",\"status\":\"OPEN\"")
                      .replace("\"name\":\"T-Bar Slope\",\"difficulty\":\"BLUE\",\"status\":\"OPEN\"",
                               "\"name\":\"T-Bar Slope\",\"difficulty\":\"BLUE\",\"status\":\"MARGINAL_CONDITIONS\"", 1))
    areas = redmountain.parse(pages, NOW)["MountainAreas"]
    assert [(area["Lifts"][0]["Status"], area["Lifts"][0]["StatusEnglish"]) for area in areas[:3]] == [
        ("Open", "open"), ("On hold", "on hold"), ("Closed", "closed")]
    assert areas[1]["Trails"][1] == {"Name": "T-Bar Slope", "Status": "Marginal conditions", "StatusEnglish": "open",
                                     "Difficulty": "Blue", "Grooming": "Yes"}


def test_a_report_that_has_changed_is_refused():
    with pytest.raises(ValueError, match="Magic Carpet has a status the reader does not know: 'WIND_HOLD'"):
        redmountain.parse(page("lifts", "\"name\":\"Magic Carpet\",\"status\":\"CLOSED\"",
                               "\"name\":\"Magic Carpet\",\"status\":\"WIND_HOLD\""), NOW)
    with pytest.raises(ValueError, match="Magic Carpet Slope has a status the reader does not know: 'PATROL'"):
        redmountain.parse(page("lifts", "\"difficulty\":\"GREEN\",\"status\":\"OPEN\"",
                               "\"difficulty\":\"GREEN\",\"status\":\"PATROL\"", 1), NOW)
    with pytest.raises(ValueError, match="difficulty the reader does not know: 'TRIPLE_BLACK'"):
        redmountain.parse(page("lifts", "\"DOUBLE_BLACK\"", "\"TRIPLE_BLACK\"", 1), NOW)
    with pytest.raises(ValueError, match="grooming the reader does not know: 'WINCHED'"):
        redmountain.parse(page("lifts", "\"NOT_GROOMED\"", "\"WINCHED\"", 1), NOW)
    with pytest.raises(ValueError, match="not in the shape expected"):
        redmountain.parse(page("lifts", "\"lifts\"", "\"chairs\""), NOW)
    with pytest.raises(ValueError, match="does not read as JSON"):
        redmountain.parse({**PAGES, "lifts": "<html>Bad gateway</html>"}, NOW)
    with pytest.raises(ValueError, match="no lifts or no runs"):
        redmountain.parse({**PAGES, "lifts": json.dumps({"data": {"lifts": []}})}, NOW)


def test_a_snow_report_that_cannot_be_read_costs_only_the_snow_report():
    for old, new in (("\"MetricAlpineSnowDepth\": 18", "\"MetricAlpineSnowDepth\": \"\""),
                     ("\"DateTime\": \"2026-11-22T21:11:31-08:00\"", "\"DateTime\": \"2026-11-22T21:11:31\""),
                     ("\"MountainReport\"", "\"Report\""), ("\"Metric7days\"", "\"MetricWeek\"")):
        feed = redmountain.parse(page("snow", old, new), NOW)
        assert "SnowReport" not in feed and len(feed["MountainAreas"]) == 9
    assert "SnowReport" not in redmountain.parse({**PAGES, "snow": "unavailable"}, NOW)
