from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import alyeska

# The page with its scripts, styles, drawings and comments taken out; the reader gives the same on the whole page.
PAGE = (Path(__file__).parent / "fixtures" / "alyeska.html").read_text()
NOW = datetime(2026, 11, 26, 14, 0, tzinfo=timezone.utc)
CLOSED_TRAM = "● <b>CLOSED</b> </span><br><br> <span style=\"font-size: 14.4px;letter-spacing: 0.35px;color:black\">"


def changed(old: str, new: str, count: int | None = None) -> str:
    assert old in PAGE and (count is None or PAGE.count(old) == count)
    return PAGE.replace(old, new)


def test_the_closed_mountain_reads_its_lifts_and_no_trails():
    # Alyeska's page on 2026-11-26, two days before it opens: seven lifts, all closed.
    feed = alyeska.parse(PAGE, NOW)
    assert feed["Name"] == "Alyeska" and feed["LastUpdate"] == "2026-11-26T14:00:00Z"
    assert len(feed["MountainAreas"]) == 1 and feed["MountainAreas"][0]["Name"] == "Alyeska"
    # "Glacier Bowl <br> Express" is written over two lines, and the box of terrain parks is not a lift.
    assert [lift["Name"] for lift in feed["MountainAreas"][0]["Lifts"]] == [
        "Aerial Tram", "Chair 7", "Glacier Bowl Express", "Ted's Express", "Bear Cub Quad", "Finnland", "Wade's Way"]
    assert feed["MountainAreas"][0]["Lifts"][0] == {"Name": "Aerial Tram", "Status": "Closed",
                                                    "StatusEnglish": "closed", "Difficulty": None}
    assert {lift["StatusEnglish"] for lift in feed["MountainAreas"][0]["Lifts"]} == {"closed"}
    # The page names no trails, and its "58 / 76 Trails Open" is left from the season before.
    assert feed["MountainAreas"][0]["Trails"] == []


def test_the_snow_report_gives_the_three_stakes_and_when_it_was_written():
    snow = alyeska.parse(PAGE, NOW)["SnowReport"]
    # "November 24, 2026" and "10:00am", nine hours behind UTC in November.
    assert snow["LastUpdate"] == "2026-11-24T19:00:00Z" and snow["Resortwide"] is False
    assert snow["BaseArea"] == {"Name": "Base", "BaseIn": 7, "Last12HoursIn": 0}
    assert snow["MidMountainArea"] == {"Name": "Middle", "BaseIn": 33, "Last12HoursIn": 0}
    assert snow["SummitArea"] == {"Name": "Top", "BaseIn": 70, "Last12HoursIn": 0, "Last24HoursIn": 0}
    assert snow["SeasonTotalIn"] == 154 and snow["BaseConditions"] is None


def test_a_report_with_no_time_is_taken_as_written_at_the_start_of_its_day():
    snow = alyeska.parse(changed("<strong>10:00am</strong>", "<strong>Good morning</strong>", 1), NOW)["SnowReport"]
    assert snow["LastUpdate"] == "2026-11-24T09:00:00Z"
    afternoon = alyeska.parse(changed("<strong>10:00am</strong>", "<strong>12:30 PM</strong>", 1), NOW)["SnowReport"]
    assert afternoon["LastUpdate"] == "2026-11-24T21:30:00Z"


def lifts_with(old: str, new: str) -> list:
    return alyeska.parse(changed(old, new, 1), NOW)["MountainAreas"][0]["Lifts"]


def test_a_lift_s_status_is_carried_in_the_page_s_words():
    lifts = lifts_with(CLOSED_TRAM, CLOSED_TRAM.replace("CLOSED", "OPEN"))
    assert [(lift["Name"], lift["StatusEnglish"]) for lift in lifts][:2] == [("Aerial Tram", "open"),
                                                                             ("Chair 7", "closed")]
    lifts = lifts_with(CLOSED_TRAM, CLOSED_TRAM.replace("CLOSED", "WIND HOLD"))
    assert (lifts[0]["Status"], lifts[0]["StatusEnglish"]) == ("Wind hold", "wind hold")
    # A lift with no hours after its status reads the same.
    lifts = lifts_with(" 10:30am - 5:00pm</span> </p>", "</span> </p>")
    assert lifts[0] == {"Name": "Aerial Tram", "Status": "Closed", "StatusEnglish": "closed", "Difficulty": None}


def test_a_page_that_has_changed_is_refused():
    with pytest.raises(ValueError, match="'Lift Status Report and Hours' was not found"):
        alyeska.parse(changed("Lift Status Report and Hours</h2>", "Summer Lift Hours</h2>"), NOW)
    with pytest.raises(ValueError, match="'Aerial Tram' reads '10:30am - 5:00pm', not a dot, a status and hours"):
        alyeska.parse(changed(CLOSED_TRAM, CLOSED_TRAM.replace("● <b>CLOSED</b>", ""), 1), NOW)
    with pytest.raises(ValueError, match="'Parks' reads"):
        alyeska.parse(changed("Terrain Parks </span>", "Parks </span>", 1), NOW)
    with pytest.raises(ValueError, match="lists no lifts"):
        alyeska.parse(changed("elementor-icon-box-title", "elementor-box-title"), NOW)
    with pytest.raises(ValueError, match="lists a lift twice"):
        alyeska.parse(changed("Chair 7 </span>", "Aerial Tram </span>", 1), NOW)


def test_a_snow_report_that_cannot_be_read_costs_only_the_snow_report():
    feed = alyeska.parse(changed(">33\"</h2>", ">deep</h2>"), NOW)
    assert "SnowReport" not in feed and len(feed["MountainAreas"][0]["Lifts"]) == 7
    # The page draws the stakes twice, and a depth changed in only one of the two is not believed.
    once = PAGE.replace(">70\"</h2>", ">71\"</h2>", 1)
    assert once != PAGE and "SnowReport" not in alyeska.parse(once, NOW)
    assert "SnowReport" not in alyeska.parse(changed(">November 24, 2026</h2>", ">Today</h2>", 1), NOW)
    assert "SnowReport" not in alyeska.parse(changed(">Snow Totals</h2>", ">Snow</h2>", 1), NOW)
    assert "SnowReport" not in alyeska.parse(changed(">*Snow Depth</h2>", ">Depth</h2>"), NOW)
    assert "SnowReport" not in alyeska.parse(changed(">154\"</h2>", ">a lot</h2>", 1), NOW)
