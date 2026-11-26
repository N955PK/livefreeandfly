from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import mountainhigh

FIXTURES = Path(__file__).parent / "fixtures"
# Both pages with their scripts, styles, comments and menus taken out; the reader gives the same on the whole pages.
PAGES = {name: (FIXTURES / f"mountainhigh_{name}.html").read_text() for name in mountainhigh.URLS}
NOW = datetime(2026, 11, 26, 17, 0, tzinfo=timezone.utc)
CLOSED = "<span class=\"ir i-status-closed\">closed</span>"
OPEN = "<span class=\"ir i-status-open\">open</span>"


def lifts_page(old: str, new: str, count: int = -1) -> dict:
    assert old in PAGES["lifts"]
    return {**PAGES, "lifts": PAGES["lifts"].replace(old, new, count)}


def snow_page(old: str, new: str) -> dict:
    assert old in PAGES["snow"]
    return {**PAGES, "snow": PAGES["snow"].replace(old, new)}


def test_the_early_season_resort_reads_its_two_mountains_with_their_lifts_and_trails():
    # Mountain High's pages early on 2026-11-26, its third day open: thirteen lifts, two expected and one on hold,
    # and 50 trails with five open.
    feed = mountainhigh.parse(PAGES, NOW)
    assert feed["Name"] == "Mountain High" and feed["LastUpdate"] == "2026-11-26T17:00:00Z"
    assert [(area["Name"], len(area["Lifts"]), len(area["Trails"])) for area in feed["MountainAreas"]] == [
        ("West Resort", 8, 34), ("East Resort", 5, 16)]
    west, east = feed["MountainAreas"]
    # "Blue Ridge Express 9:00 am - 4:00 pm" is read without its hours, and Roadrunner's note is not a lift.
    assert [(lift["Name"], lift["Status"]) for lift in west["Lifts"]] == [
        ("Blue Ridge Express", "Expected"), ("Conquest", "Closed"), ("Coyote", "Expected"), ("Exhibition", "Closed"),
        ("Moving Carpet West Long", "Closed"), ("Moving Carpet West Short", "Closed"), ("Roadrunner", "On hold"),
        ("Snowflake", "Closed")]
    assert west["Lifts"][0] == {"Name": "Blue Ridge Express", "Status": "Expected", "StatusEnglish": "expected",
                                "Difficulty": None}
    assert west["Lifts"][6]["StatusEnglish"] == "on hold"
    assert {lift["StatusEnglish"] for lift in east["Lifts"]} == {"closed"}
    trails = west["Trails"] + east["Trails"]
    assert len({trail["Name"] for trail in trails}) == 50
    # No trail is marked groomed, so none carries grooming.
    assert trails[0] == {"Name": "4Runner", "Status": "Closed", "StatusEnglish": "closed", "Difficulty": "Black"}
    assert [trail["Name"] for trail in trails if trail["StatusEnglish"] == "open"] == [
        "Creekside", "Cruiser", "Lower Chisolm", "Sunnyside", "Upper Chisolm"]
    assert east["Trails"][8]["Name"] == "Olympic Bowl" and east["Trails"][8]["Difficulty"] == "Double black"
    assert [sum(trail["Difficulty"] == level for trail in trails)
            for level in ("Green", "Blue", "Black", "Double black")] == [9, 19, 20, 2]


def test_the_snow_report_gives_the_base_and_the_top_and_when_it_was_updated():
    snow = mountainhigh.parse(PAGES, NOW)["SnowReport"]
    # "Updated: Thursday, November 26, 2026 05:37 AM", eight hours behind UTC in November.
    assert snow["LastUpdate"] == "2026-11-26T13:37:00Z" and snow["Resortwide"] is True
    assert snow["BaseArea"] == {"Name": "Base", "BaseIn": 12, "Last24HoursIn": 0, "Last48HoursIn": 0, "Last7DaysIn": 0}
    assert snow["SummitArea"] == {"Name": "Top", "BaseIn": 24}
    assert snow["SeasonTotalIn"] == 0 and snow["BaseConditions"] == "Machine Made"


def test_a_groomed_trail_is_open_and_groomed_and_a_race_is_carried():
    pages = lifts_page(OPEN, OPEN.replace("open", "groomed"), 1)
    pages = {**pages, "lifts": pages["lifts"].replace(OPEN, OPEN.replace("open", "race"), 1)}
    trails = {trail["Name"]: trail for area in mountainhigh.parse(pages, NOW)["MountainAreas"]
              for trail in area["Trails"]}
    assert trails["Creekside"] == {"Name": "Creekside", "Status": "Open", "StatusEnglish": "open",
                                   "Difficulty": "Green", "Grooming": "Yes"}
    assert (trails["Cruiser"]["Status"], trails["Cruiser"]["StatusEnglish"], trails["Cruiser"]["Grooming"]) == (
        "Race", "race", "No")
    assert (trails["Sunnyside"]["StatusEnglish"], trails["Sunnyside"]["Grooming"]) == ("open", "No")


def test_a_page_that_has_changed_is_refused():
    with pytest.raises(ValueError, match="63 lift and trail rows but 0 were read"):
        mountainhigh.parse(lifts_page("<table class=\"StatusReport StatusReport--", "<table class=\"Report Report--"),
                           NOW)
    with pytest.raises(ValueError, match="Conquest's status icon is closed and reads 'open'"):
        mountainhigh.parse(lifts_page(CLOSED, "<span class=\"ir i-status-closed\">open</span>", 1), NOW)
    with pytest.raises(ValueError, match="Conquest's status icon is shut and reads 'shut'"):
        mountainhigh.parse(lifts_page(CLOSED, "<span class=\"ir i-status-shut\">shut</span>", 1), NOW)
    with pytest.raises(ValueError, match="4Runner has a difficulty the reader does not know: extreme"):
        mountainhigh.parse(lifts_page("<span class=\"ir i-skill-advanced\">", "<span class=\"ir i-skill-extreme\">", 1),
                           NOW)
    with pytest.raises(ValueError, match="not a kind, a name and a status"):
        mountainhigh.parse(lifts_page("<td class=\"StatusReport-status\">", "<td class=\"StatusReport-state\">", 1),
                           NOW)
    with pytest.raises(ValueError, match="63 lift and trail rows but 13 were read"):
        mountainhigh.parse(lifts_page("StatusReport StatusReport--trails", "StatusReport StatusReport--runs"), NOW)


def test_a_snow_report_that_cannot_be_read_costs_only_the_snow_report():
    feed = mountainhigh.parse(snow_page("Updated: Thursday, November 26, 2026 05:37 AM", "Updated this morning"), NOW)
    assert "SnowReport" not in feed and len(feed["MountainAreas"]) == 2
    assert "SnowReport" not in mountainhigh.parse(snow_page("Base Snow Depth", "Lower Snow Depth"), NOW)
    assert "SnowReport" not in mountainhigh.parse(snow_page("<div class=\"t-digit-lg\">12<",
                                                            "<div class=\"t-digit-lg\">deep<"), NOW)
    # A report with no word for the surface still reads.
    snow = mountainhigh.parse(snow_page("<p>Machine Made</p>", "<p></p>"), NOW)["SnowReport"]
    assert snow["BaseConditions"] is None and snow["BaseArea"]["BaseIn"] == 12
