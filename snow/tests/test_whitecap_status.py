from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import whitecap

# The page with its scripts, styles, menus and footer taken out; the reader gives the same on the whole page.
PAGE = (Path(__file__).parent / "fixtures" / "whitecap.html").read_text()
# The saved page is the last report of the 2025-26 season, still up in November: it is read as of its own day.
NOW = datetime(2026, 3, 29, 17, 0, tzinfo=timezone.utc)


def page(old: str, new: str, count: int = -1) -> str:
    assert old in PAGE
    return PAGE.replace(old, new, count)


def test_the_last_day_of_the_season_reads_its_lifts_and_the_trails_of_each_difficulty():
    feed = whitecap.parse(PAGE, NOW)
    assert feed["Name"] == "Whitecap" and feed["LastUpdate"] == "2026-03-29T17:00:00Z"
    assert [(area["Name"], len(area["Lifts"]), len(area["Trails"])) for area in feed["MountainAreas"]] == [
        ("Whitecap", 5, 0), ("Easier", 0, 15), ("More Difficult", 0, 13), ("Most Difficult", 0, 12),
        ("Expert Only", 0, 5)]
    lifts = feed["MountainAreas"][0]["Lifts"]
    assert [(lift["Name"], lift["StatusEnglish"]) for lift in lifts] == [
        ("Long Chair", "closed"), ("Midway Chair", "open"), ("Main Chair", "open"), ("Triple Chair", "open"),
        ("Magic Carpet", "open")]
    assert lifts[0] == {"Name": "Long Chair", "Status": "Closed", "StatusEnglish": "closed", "Difficulty": None}
    trails = {trail["Name"]: trail for area in feed["MountainAreas"] for trail in area["Trails"]}
    # The page's own "Total Trails Open" is 21.
    assert len(trails) == 45 and sum(trail["StatusEnglish"] == "open" for trail in trails.values()) == 21
    # The page writes "SUD BOWL" and "MARY'S MISTAKE".
    assert trails["Sud Bowl"] == {"Name": "Sud Bowl", "Status": "Open", "StatusEnglish": "open", "Difficulty": "Green",
                                  "Grooming": "Yes"}
    assert trails["Mary's Mistake"] == {"Name": "Mary's Mistake", "Status": "Open", "StatusEnglish": "open",
                                        "Difficulty": "Black", "Grooming": "No"}
    assert (trails["St. Moritz"]["Difficulty"], trails["Dragon"]["Difficulty"]) == ("Blue", "Double black")
    # A note that is not about grooming ("VAriable", an unfilled blank of the form) or no note reads as not groomed.
    assert {trails[name]["Grooming"] for name in ("Hintertux", "Schatzys", "Grenoble")} == {"No"}


def test_the_snow_report_gives_the_depth_as_a_range_and_the_day_it_was_written():
    snow = whitecap.parse(PAGE, NOW)["SnowReport"]
    # "Mar 29, 2026 - 6:00 AM" in Central time, five hours behind UTC in late March.
    assert snow["LastUpdate"] == "2026-03-29T11:00:00Z" and snow["Resortwide"] is True
    # "0-34+".
    assert snow["BaseArea"] == {"Name": "Mountain", "BaseMinIn": 0, "BaseMaxIn": 34, "Last24HoursIn": 0,
                                "Last7DaysIn": 0}
    assert snow["SeasonTotalIn"] == 180 and snow["BaseConditions"] == "Variable"
    single = whitecap.parse(page("<td>0-34+</td>", "<td>28\"</td>"), NOW)["SnowReport"]["BaseArea"]
    assert single["BaseIn"] == 28 and "BaseMinIn" not in single


def test_last_season_s_report_left_up_with_its_lifts_open_is_refused():
    with pytest.raises(ValueError, match="written 2026-03-29 and has lifts or trails open: it is last season's"):
        whitecap.parse(PAGE, datetime(2026, 11, 26, 18, 0, tzinfo=timezone.utc))
    # An old report with everything closed says nothing wrong, and is read.
    shut = page("<td>OPEN</td>", "<td>CLOSED</td>").replace(">OPEN</td>", ">CLOSED</td>")
    shut = shut.replace("<td>21</td>", "<td>0</td>").replace("<td>4</td>", "<td>0</td>")
    feed = whitecap.parse(shut, datetime(2026, 11, 26, 18, 0, tzinfo=timezone.utc))
    assert {row["StatusEnglish"] for area in feed["MountainAreas"] for row in area["Lifts"] + area["Trails"]} == {
        "closed"}


def test_a_lift_s_other_status_is_carried_in_the_page_s_words():
    held = whitecap.parse(page("<td>Long Chair</td>\n<td>CLOSED</td>", "<td>Long Chair</td>\n<td>WIND HOLD</td>"), NOW)
    lift = held["MountainAreas"][0]["Lifts"][0]
    assert (lift["Name"], lift["Status"], lift["StatusEnglish"]) == ("Long Chair", "Wind hold", "wind hold")


def test_a_page_that_has_changed_is_refused():
    with pytest.raises(ValueError, match="total lifts open is '4' but 3 were read"):
        whitecap.parse(page("<td>Midway Chair</td>\n<td>OPEN</td>", "<td>Midway Chair</td>\n<td>CLOSED</td>"), NOW)
    with pytest.raises(ValueError, match="total trails open is '22' but 21 were read"):
        whitecap.parse(page("<td>21</td>", "<td>22</td>"), NOW)
    with pytest.raises(ValueError, match="Long Chair has the status '', not a word"):
        whitecap.parse(page("<td>Long Chair</td>\n<td>CLOSED</td>", "<td>Long Chair</td>\n<td></td>"), NOW)
    with pytest.raises(ValueError, match="a trails table the reader does not know, or has it twice: Glades"):
        whitecap.parse(page(">Expert Only</th>", ">Glades</th>"), NOW)
    with pytest.raises(ValueError, match="the report's date reads 'this morning'"):
        whitecap.parse(page("Mar 29, 2026 - 6:00 AM", "this morning"), NOW)
    with pytest.raises(ValueError, match="the conditions, the lifts or the trails were not found"):
        whitecap.parse(page("<table class=\"lifts printleft\">", "<table class=\"printleft\">"), NOW)
    with pytest.raises(ValueError, match="were not found"):
        whitecap.parse("<html><body>Page not found</body></html>", NOW)


def test_a_snow_report_that_cannot_be_read_costs_only_the_snow_report():
    feed = whitecap.parse(page("<td>0-34+</td>", "<td>plenty</td>"), NOW)
    assert "SnowReport" not in feed and len(feed["MountainAreas"]) == 5
