from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import grouse

FIXTURES = Path(__file__).parent / "fixtures"
# The page on 2026-11-24, before the lifts opened, as it came.
PAGE = (FIXTURES / "grouse.html").read_text()
# The page on 2026-02-10 (from the Internet Archive): three of six lifts open.
MIDSEASON = (FIXTURES / "grouse_midseason.html").read_text()
NOW = datetime(2026, 11, 25, 0, 30, tzinfo=timezone.utc)


def midseason(old: str, new: str) -> str:
    assert old in MIDSEASON
    return MIDSEASON.replace(old, new)


def test_before_the_season_no_lifts_are_posted_and_none_are_made_up():
    feed = grouse.parse(PAGE, NOW)
    assert feed["Name"] == "Grouse Mountain" and feed["LastUpdate"] == "2026-11-25T00:30:00Z"
    assert feed["MountainAreas"] == [{"Name": "Grouse Mountain", "Lifts": [], "Trails": []}]
    snow = feed["SnowReport"]
    # 16 cm on the Plateau and 20 cm at the Peak; 9 cm in 24 hours.
    assert snow["BaseArea"] == {"Name": "Plateau", "BaseIn": 6.3, "OvernightIn": 0.4, "Last24HoursIn": 3.5,
                                "Last48HoursIn": 6.3, "Last7DaysIn": 6.3}
    assert snow["SummitArea"] == {"Name": "Peak", "BaseIn": 7.9} and snow["SeasonTotalIn"] == 6.3
    # "3:00 PM Report": a time of day and no date.
    assert snow["LastUpdate"] is None and snow["ReportTime"] == "3:00 PM"


def test_the_open_mountain_reads_its_lifts_and_runs():
    feed = grouse.parse(MIDSEASON, NOW)
    (area,) = feed["MountainAreas"]
    assert [(lift["Name"], lift["Status"]) for lift in area["Lifts"]] == [
        ("Olympic Express High-Speed Quad Chair", "Closed"), ("Peak Quad Chair", "Open"),
        ("Screaming Eagle High-Speed Quad Chair", "Closed"), ("Greenway Quad Chair", "Open"),
        ("Magic Carpet", "Open"), ("Short Cut Handle Tow", "Closed")]
    assert area["Lifts"][1] == {"Name": "Peak Quad Chair", "Status": "Open", "StatusEnglish": "open",
                                "Difficulty": None}
    assert len(area["Trails"]) == 34
    assert [trail["Name"] for trail in area["Trails"] if trail["StatusEnglish"] == "open"] == [
        "Paradise", "Ski Wee", "Heaven's Sake", "Lower Peak", "Peak", "Purgatory", "No Man's Land"]
    # A run's details ("To Heaven's Sake" under Purgatory) are not part of its name.
    assert area["Trails"][0] == {"Name": "Chalet Road", "Status": "Closed", "StatusEnglish": "closed",
                                 "Difficulty": "Green"}
    assert [sum(trail["Difficulty"] == level for trail in area["Trails"])
            for level in ("Green", "Blue", "Black", "Double black")] == [4, 19, 8, 3]
    snow = feed["SnowReport"]
    # 90 cm on the Plateau, 100 cm at the Peak, 14 cm in 24 hours, 306 cm this season.
    assert snow["BaseArea"]["BaseIn"] == 35.4 and snow["SummitArea"]["BaseIn"] == 39.4
    assert snow["BaseArea"]["Last24HoursIn"] == 5.5 and snow["SeasonTotalIn"] == 120.5
    assert snow["ReportTime"] == "10:00 AM"


def test_a_lift_s_other_status_is_carried_in_the_page_s_words():
    feed = grouse.parse(midseason("<span class='open'>\n<span class='legend__night'></span>\nOpen\n</span>\n</li>\n"
                                  "<li>\n<span>\nScreaming Eagle",
                                  "<span class='standby'>\n<span class='legend__night'></span>\nOn Standby\n</span>\n"
                                  "</li>\n<li>\n<span>\nScreaming Eagle"), NOW)
    lift = feed["MountainAreas"][0]["Lifts"][1]
    assert (lift["Name"], lift["Status"], lift["StatusEnglish"]) == ("Peak Quad Chair", "On standby", "on standby")


def test_a_page_that_has_changed_is_refused():
    with pytest.raises(ValueError, match="tabs were not found"):
        grouse.parse(PAGE.replace("class='conditions_tabs'", "class='conditions'"), NOW)
    with pytest.raises(ValueError, match="tabs were not found"):
        grouse.parse("<html>Just a moment...</html>", NOW)
    with pytest.raises(ValueError, match="difficulty symbols"):
        grouse.parse(midseason("<span class='runs-double-diamond'>", "<span class='runs-triple-diamond'>"), NOW)
    with pytest.raises(ValueError, match="but not both"):
        grouse.parse(midseason("<div class='tab' id='runs'", "<div class='tab' id='trails'"), NOW)
    with pytest.raises(ValueError, match="not a name, a note and a status"):
        grouse.parse(midseason("<div class='note'>", "<div class='remark'>"), NOW)


def test_a_snow_report_that_cannot_be_read_costs_only_the_snow_report():
    feed = grouse.parse(midseason("<h3 class='metric'>\n90cm\n</h3>", "<h3 class='metric'>\ndeep\n</h3>"), NOW)
    assert "SnowReport" not in feed and len(feed["MountainAreas"][0]["Lifts"]) == 6
    assert "SnowReport" not in grouse.parse(midseason("<p>Depth Plateau</p>", "<p>Depth Chalet</p>"), NOW)
