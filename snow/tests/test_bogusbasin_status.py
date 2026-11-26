import html
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import bogusbasin

FIXTURES = Path(__file__).parent / "fixtures"
# Both pages with their scripts, styles, drawings and menus taken out; the reader gives the same on the whole pages.
PAGES = {name: (FIXTURES / f"bogusbasin_{name}.html").read_text() for name in bogusbasin.URLS}
NOW = datetime(2026, 11, 26, 16, 0, tzinfo=timezone.utc)


def lifts_page(old: str, new: str) -> dict:
    assert old in PAGES["lifts"]
    return {**PAGES, "lifts": PAGES["lifts"].replace(old, new)}


def snow_page(old: str, new: str) -> dict:
    assert old in PAGES["snow"]
    return {**PAGES, "snow": PAGES["snow"].replace(old, new)}


def changed(change) -> dict:
    """The pages with one change made to the detailed report."""
    found = bogusbasin.REPORT.search(PAGES["lifts"])
    report = json.loads(html.unescape(found.group(1)))
    change(report)
    said = html.escape(json.dumps(report), quote=True)
    return {**PAGES, "lifts": PAGES["lifts"].replace(found.group(1), said)}


def test_the_early_season_mountain_reads_each_lift_with_the_trails_under_it():
    # Bogus Basin's pages on 2026-11-26, early season: ten lifts with five open, 97 trails.
    feed = bogusbasin.parse(PAGES, NOW)
    assert feed["Name"] == "Bogus Basin" and feed["LastUpdate"] == "2026-11-26T16:00:00Z"
    assert [(area["Name"], area["Lifts"][0]["Status"], len(area["Trails"])) for area in feed["MountainAreas"]] == [
        ("Deer Point Express", "Open", 21), ("Morning Star Express", "Open", 9), ("Superior Express", "Closed", 32),
        ("Showcase Chair", "Closed", 0), ("Bitterroot Chair", "Closed", 12), ("Pine Creek Express", "Closed", 21),
        ("Coach Chairlift", "Open", 2), ("Easy Rider Carpet", "Open", 0), ("Discovery Carpet", "Open", 0),
        ("Explorer Carpet", "Closed", 0)]
    assert all(len(area["Lifts"]) == 1 for area in feed["MountainAreas"])
    assert feed["MountainAreas"][0]["Lifts"] == [{"Name": "Deer Point Express", "Status": "Open",
                                                  "StatusEnglish": "open", "Difficulty": None}]
    trails = [trail for area in feed["MountainAreas"] for trail in area["Trails"]]
    # A trail listed under a second lift is read once, and the two routes for walking up are not trails.
    assert len(trails) == 97 == len({trail["Name"] for trail in trails})
    assert not any("Uphill" in trail["Name"] for trail in trails)
    assert sum(trail["StatusEnglish"] == "open" for trail in trails) == 31
    assert trails[0] == {"Name": "Claim Jumper", "Status": "Open", "StatusEnglish": "open", "Difficulty": "Blue",
                         "Grooming": "No"}
    assert {trail["Difficulty"] for trail in trails} == {"Green", "Blue", "Black", "Double black", ""}
    # The five terrain parks have no level, and a trail whose grooming the report leaves unsaid carries none.
    assert len([trail for trail in trails if trail["Difficulty"] == ""]) == 5
    assert sum(trail.get("Grooming") == "Yes" for trail in trails) == 13
    assert sum("Grooming" not in trail for trail in trails) == 65


def test_the_snow_report_gives_the_depth_and_when_it_was_updated():
    snow = bogusbasin.parse(PAGES, NOW)["SnowReport"]
    # "November 26th, 5:58 AM", seven hours behind UTC in November, in the year of the reading.
    assert snow["LastUpdate"] == "2026-11-26T12:58:00Z" and snow["Resortwide"] is True
    assert snow["BaseArea"] == {"Name": "Mountain", "BaseIn": 21, "Last12HoursIn": 0, "Last24HoursIn": 0,
                                "Last48HoursIn": 0, "Last7DaysIn": 11}
    assert snow["SeasonTotalIn"] == 37 and snow["BaseConditions"] is None


def test_a_date_that_would_be_ahead_of_the_reading_is_last_year_s():
    snow = bogusbasin.parse(PAGES, datetime(2027, 1, 2, 16, 0, tzinfo=timezone.utc))["SnowReport"]
    assert snow["LastUpdate"] == "2026-11-26T12:58:00Z"


def test_a_code_is_said_in_plain_words_and_an_unknown_one_is_carried():
    def held(report):
        report["lifts"][2]["openingStatus"] = "STOPPED_WIND"
        report["lifts"][3]["openingStatus"] = "FORECAST"
        report["lifts"][4]["openingStatus"] = "SOMETHING_NEW"

    feed = bogusbasin.parse(changed(held), NOW)
    assert [feed["MountainAreas"][at]["Lifts"][0]["StatusEnglish"] for at in (2, 3, 4)] == [
        "on hold wind", "expected", "something_new"]


def test_a_page_that_has_changed_is_refused():
    with pytest.raises(ValueError, match="detailed report was not found"):
        bogusbasin.parse(lifts_page("<x-filterable-lift-trail-status", "<x-lift-trail-status"), NOW)
    with pytest.raises(ValueError, match="does not read as JSON"):
        bogusbasin.parse(lifts_page("data-data='{", "data-data='"), NOW)
    with pytest.raises(ValueError, match="counts 6 of 10 lifts open but 5 of 10"):
        bogusbasin.parse(lifts_page("<p>5/10 Open</p>", "<p>6/10 Open</p>"), NOW)
    with pytest.raises(ValueError, match="count of lifts was not found"):
        bogusbasin.parse(lifts_page("<p>5/10 Open</p>", "<p>5 Open</p>"), NOW)
    with pytest.raises(ValueError, match="level the reader does not know: TRIPLE_BLACK"):
        bogusbasin.parse(changed(lambda report: report["lifts"][0]["trails"][0].update(trailLevel="TRIPLE_BLACK")), NOW)
    with pytest.raises(ValueError, match="Deer Point Express has no status"):
        bogusbasin.parse(changed(lambda report: report["lifts"][0].update(openingStatus="UNDEF")), NOW)
    with pytest.raises(ValueError, match="not in the shape expected"):
        bogusbasin.parse(changed(lambda report: report["lifts"][0].pop("liftType")), NOW)
    with pytest.raises(ValueError, match="no list of lifts"):
        bogusbasin.parse(changed(lambda report: report.update(lifts=None)), NOW)


def test_a_snow_report_that_cannot_be_read_costs_only_the_snow_report():
    feed = bogusbasin.parse(snow_page("site-post-snowzone-blocks-snow-totals", "snow-totals"), NOW)
    assert "SnowReport" not in feed and len(feed["MountainAreas"]) == 10
    assert "SnowReport" not in bogusbasin.parse(snow_page("Total Depth", "Depth At The Top"), NOW)
    assert "SnowReport" not in bogusbasin.parse(snow_page("November 26th, 5:58 AM", "this morning"), NOW)
    assert "SnowReport" not in bogusbasin.parse(
        snow_page(re.search(r"Total Depth</dt>\s*<dd>\s*<span class=\"value\">21", PAGES["snow"]).group(0),
                  "Total Depth</dt><dd><span class=\"value\">deep"), NOW)
