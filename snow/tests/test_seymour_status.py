from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import seymour

FIXTURES = Path(__file__).parent / "fixtures"
# Both pages with their scripts, styles, drawings and comments taken out; the reader gives the same on the whole pages.
PAGE = (FIXTURES / "seymour.html").read_text()
MIDSEASON = (FIXTURES / "seymour_midseason.html").read_text()
NOW = datetime(2026, 11, 25, 0, 30, tzinfo=timezone.utc)
# 8:30 in the evening of Saturday 2026-02-14 in Vancouver, half an hour after the archived page was updated.
THAT_EVENING = datetime(2026, 2, 15, 4, 30, tzinfo=timezone.utc)


def page(old: str, new: str, whole: str = PAGE) -> str:
    assert old in whole
    return whole.replace(old, new)


def test_the_closed_mountain_reads_each_lift_with_the_runs_under_it():
    # Mt Seymour's page on 2026-11-24, before it opened: four lifts and 42 runs, all closed.
    feed = seymour.parse(PAGE, NOW)
    assert feed["Name"] == "Mt Seymour" and feed["LastUpdate"] == "2026-11-25T00:30:00Z"
    assert [(area["Name"], area["Lifts"][0]["Status"], len(area["Trails"])) for area in feed["MountainAreas"]] == [
        ("Lodge Chair", "Closed", 9), ("Mystery Peak Express", "Closed", 20), ("Brockton Chair", "Closed", 10),
        ("Goldie Magic Carpet", "Closed", 3)]
    assert all(len(area["Lifts"]) == 1 for area in feed["MountainAreas"])
    assert feed["MountainAreas"][1]["Lifts"] == [{"Name": "Mystery Peak Express", "Status": "Closed",
                                                  "StatusEnglish": "closed", "Difficulty": None}]
    trails = [trail for area in feed["MountainAreas"] for trail in area["Trails"]]
    assert len(trails) == 42 and {trail["StatusEnglish"] for trail in trails} == {"closed"}
    assert trails[0] == {"Name": "Lodge Connector", "Status": "Closed", "StatusEnglish": "closed",
                         "Difficulty": "Green", "NightStatus": "Closed"}
    assert {trail["Difficulty"] for trail in trails} == {"Green", "Blue", "Black"}
    assert "Devil's Drop" in {trail["Name"] for trail in trails}


def test_the_snow_report_gives_the_depths_in_inches_and_when_it_was_updated():
    snow = seymour.parse(PAGE, NOW)["SnowReport"]
    # "Last Updated: Tue Nov 24 @ 03:24pm" in Vancouver, seven hours behind UTC since British Columbia stopped
    # changing its clocks in 2026.
    assert snow["LastUpdate"] == "2026-11-24T22:24:00Z" and snow["Resortwide"] is False
    # 10 cm at the base and 25 cm at the summit; 10 cm in 24 hours.
    assert snow["BaseArea"] == {"Name": "Base", "BaseIn": 3.9, "Last24HoursIn": 3.9, "Last48HoursIn": 9.8,
                                "Last7DaysIn": 9.8}
    assert snow["SummitArea"] == {"Name": "Summit", "BaseIn": 9.8}
    assert snow["SeasonTotalIn"] == 9.8 and snow["BaseConditions"] is None


def test_the_open_mountain_reads_a_lift_s_hours_against_the_clock():
    # The page on 2026-02-14 (from the Internet Archive): every lift with its hours, 24 runs open by day.
    feed = seymour.parse(MIDSEASON, THAT_EVENING)
    lifts = [area["Lifts"][0] for area in feed["MountainAreas"]]
    assert lifts[0] == {"Name": "Lodge Chair", "Status": "Open", "StatusEnglish": "open", "Difficulty": None,
                        "Hours": "8:30 AM - 9:30 PM"}
    # The Brockton Chair's hours ended at 4:00 PM.
    assert [(lift["Name"], lift["StatusEnglish"]) for lift in lifts] == [
        ("Lodge Chair", "open"), ("Mystery Peak Express", "open"), ("Brockton Chair", "closed"),
        ("Goldie Magic Carpet", "open")]
    morning = seymour.parse(MIDSEASON, datetime(2026, 2, 14, 15, 0, tzinfo=timezone.utc))
    assert {area["Lifts"][0]["StatusEnglish"] for area in morning["MountainAreas"]} == {"scheduled"}
    trails = [trail for area in feed["MountainAreas"] for trail in area["Trails"]]
    assert len(trails) == 42 and sum(trail["StatusEnglish"] == "open" for trail in trails) == 24
    assert sum(trail["NightStatus"] == "Open" for trail in trails) == 15
    snow = feed["SnowReport"]
    # "Sat Feb 14 @ 08:01pm", eight hours behind UTC that February; read in November it is still that year's.
    assert snow["LastUpdate"] == "2026-02-15T04:01:00Z"
    assert seymour.parse(MIDSEASON, NOW)["SnowReport"]["LastUpdate"] == "2026-02-15T04:01:00Z"
    # 100 cm at the base, 160 cm at the summit, 8 cm in 24 hours, 367 cm this season.
    assert snow["BaseArea"]["BaseIn"] == 39.4 and snow["SummitArea"]["BaseIn"] == 63.0
    assert snow["BaseArea"]["Last24HoursIn"] == 3.1 and snow["SeasonTotalIn"] == 144.5
    assert snow["BaseConditions"] == "Soft Packed"


def test_a_lift_s_other_status_is_carried_in_the_page_s_words():
    feed = seymour.parse(page("8:30 AM - 9:00 PM", "Stand By", MIDSEASON), THAT_EVENING)
    lift = feed["MountainAreas"][3]["Lifts"][0]
    assert (lift["Name"], lift["Status"], lift["StatusEnglish"]) == ("Goldie Magic Carpet", "Stand by", "stand by")


def test_a_page_that_has_changed_is_refused():
    with pytest.raises(ValueError, match="table of lifts was not found"):
        seymour.parse(page(">Lifts</caption>", ">Chairs</caption>"), NOW)
    with pytest.raises(ValueError, match="table of lifts was not found"):
        seymour.parse("<html>Just a moment...</html>", NOW)
    with pytest.raises(ValueError, match="status symbols"):
        seymour.parse(page("icon status status-closed", "icon status status-shut"), NOW)
    with pytest.raises(ValueError, match="difficulty symbols"):
        seymour.parse(page("icon level level-advanced", "icon level level-hardest"), NOW)
    with pytest.raises(ValueError, match="counts 3 day runs open but 0"):
        seymour.parse(page("            0\n", "            3\n"), NOW)
    with pytest.raises(ValueError, match="end before they start"):
        seymour.parse(page("9:30 AM - 4:00 PM", "9:30 AM - 4:00 AM", MIDSEASON), THAT_EVENING)
    with pytest.raises(ValueError, match="not a word or its hours"):
        seymour.parse(page("9:30 AM - 4:00 PM", "9:30 - 16:00", MIDSEASON), THAT_EVENING)


def test_a_snow_report_that_cannot_be_read_costs_only_the_snow_report():
    feed = seymour.parse(page("Last Updated: Tue Nov", "Last Updated: Wed Nov"), NOW)
    assert "SnowReport" not in feed and len(feed["MountainAreas"]) == 4
    assert "SnowReport" not in seymour.parse(page("At The Base", "At The Lodge"), NOW)
    assert "SnowReport" not in seymour.parse(page("snow-data", "snow-figures"), NOW)
