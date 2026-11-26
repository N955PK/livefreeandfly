from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import holidayvalley

# The page with its scripts, styles, drawings and comments taken out; the reader gives the same on the whole page.
PAGE = (Path(__file__).parent / "fixtures" / "holidayvalley.html").read_text()
NOW = datetime(2026, 11, 26, 18, 0, tzinfo=timezone.utc)
CLOSED = "<img class=\"status-icon\" src=\"/Icons/sr-icons/Closed.png\" />"
OPEN = "<img class=\"status-icon\" src=\"/Icons/sr-icons/Open.png\" />"


def page(old: str, new: str, count: int = -1) -> str:
    assert old in PAGE
    return PAGE.replace(old, new, count)


def test_the_closed_mountain_reads_its_lifts_and_each_kind_of_trail():
    # Holiday Valley's page on 2026-11-26, before it opened: 13 lifts and 71 trails, all closed.
    feed = holidayvalley.parse(PAGE, NOW)
    assert feed["Name"] == "Holiday Valley" and feed["LastUpdate"] == "2026-11-26T18:00:00Z"
    # The uphill routes, listed again among the easiest trails, and the cross country and walking trails are left out.
    assert [(area["Name"], len(area["Lifts"]), len(area["Trails"])) for area in feed["MountainAreas"]] == [
        ("Holiday Valley", 13, 0), ("Easiest", 0, 28), ("More Difficult", 0, 14), ("Most Difficult", 0, 21),
        ("Expert", 0, 1), ("Gladed", 0, 4), ("Terrain Park", 0, 3)]
    lifts = feed["MountainAreas"][0]["Lifts"]
    assert lifts[1] == {"Name": "Chute Quad", "Status": "Closed", "StatusEnglish": "closed", "Difficulty": None}
    assert lifts[2]["Name"] == "Cindy's Quad" and lifts[-1]["Name"] == "Yodeler Express Quad"
    trails = [trail for area in feed["MountainAreas"] for trail in area["Trails"]]
    assert trails[0] == {"Name": "Bear Cub", "Status": "Closed", "StatusEnglish": "closed", "Difficulty": "Green",
                         "Grooming": "No"}
    assert {trail["StatusEnglish"] for trail in trails + lifts} == {"closed"}
    names = {trail["Name"] for trail in trails}
    assert not names & {"Punch Bowl/Tannenbaum/Northwind", "Cross Country Golf Course", "Happy Wanderer Walking Trail"}
    assert {area["Name"]: area["Trails"][0]["Difficulty"] for area in feed["MountainAreas"][1:]} == {
        "Easiest": "Green", "More Difficult": "Blue", "Most Difficult": "Black", "Expert": "Double black",
        "Gladed": "", "Terrain Park": ""}


def test_the_snow_report_gives_the_base_depth_as_a_range_and_is_undated():
    snow = holidayvalley.parse(PAGE, NOW)["SnowReport"]
    assert snow["LastUpdate"] is None and snow["Resortwide"] is True and snow["SeasonTotalIn"] == 0
    assert snow["BaseArea"] == {"Name": "Mountain", "BaseMinIn": 0, "BaseMaxIn": 0, "Last24HoursIn": 0}
    deep = page("0\" - 0\"\n </span>\n </div>\n <div class=\"w-30 border-left border-right\">",
                "12\" - 30\"\n </span>\n </div>\n <div class=\"w-30 border-left border-right\">")
    assert holidayvalley.parse(deep, NOW)["SnowReport"]["BaseArea"]["BaseMaxIn"] == 30


def test_open_held_and_groomed_rows_are_read_from_their_pictures():
    # The first of these pictures on the page is the one in its key.
    opened = page(CLOSED, OPEN, 3).replace("0 of 13 OPEN LIFTS", "2 of 13 OPEN LIFTS")
    lifts = holidayvalley.parse(opened, NOW)["MountainAreas"][0]["Lifts"]
    assert [lift["StatusEnglish"] for lift in lifts[:3]] == ["open", "open", "closed"]
    held = page(CLOSED + "\n Boardwalk", CLOSED.replace("Closed.png", "Hold.png") + "\n Boardwalk", 1)
    lift = holidayvalley.parse(held, NOW)["MountainAreas"][0]["Lifts"][0]
    assert (lift["Name"], lift["Status"], lift["StatusEnglish"]) == ("Boardwalk", "On hold", "on hold")
    groomed = page(CLOSED + "\n Bear Cub", OPEN + "<img class=\"status-icon\" src=\"/Icons/sr-icons/Groomed.png\" />"
                   "\n Bear Cub")
    trail = holidayvalley.parse(groomed, NOW)["MountainAreas"][1]["Trails"][0]
    assert (trail["Name"], trail["StatusEnglish"], trail["Grooming"]) == ("Bear Cub", "open", "Yes")


def test_a_page_that_has_changed_is_refused():
    with pytest.raises(ValueError, match="counts 1 of 13 lifts open but 0 of 13"):
        holidayvalley.parse(page("0 of 13 OPEN LIFTS", "1 of 13 OPEN LIFTS"), NOW)
    with pytest.raises(ValueError, match="not a status the reader knows"):
        holidayvalley.parse(page("sr-icons/Closed.png\" />\n Chute Quad", "sr-icons/Shut.png\" />\n Chute Quad"), NOW)
    with pytest.raises(ValueError, match="ones the reader does not know: \\['Extreme'\\]"):
        holidayvalley.parse(page("<span class=\"label-accord\">Expert</span>",
                                 "<span class=\"label-accord\">Extreme</span>"), NOW)
    with pytest.raises(ValueError, match="no lifts or no trails"):
        holidayvalley.parse(page("class=\"label-accord\"", "class=\"label\""), NOW)
    with pytest.raises(ValueError, match="no lifts or no trails"):
        holidayvalley.parse("<html><body>Page not found</body></html>", NOW)


def test_a_snow_report_that_cannot_be_read_costs_only_the_snow_report():
    feed = holidayvalley.parse(page("<span>BASE</span> <span>DEPTH</span>", "<span>SNOW</span> <span>DEPTH</span>"),
                               NOW)
    assert "SnowReport" not in feed and len(feed["MountainAreas"]) == 7
