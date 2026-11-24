from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import waterville

FIXTURES = Path(__file__).parent / "fixtures"
PAGE = (FIXTURES / "waterville.html").read_text()
MIDSEASON = (FIXTURES / "waterville_midseason.html").read_text()
NOW = datetime(2026, 11, 24, 17, 30, tzinfo=timezone.utc)


def test_the_closed_mountain_reads_as_every_lift_and_trail_closed():
    # Waterville Valley's report on 2026-11-23, before it opened: ten lifts, 62 trails and five parks, all closed.
    feed = waterville.parse(PAGE, NOW)
    assert feed["Name"] == "Waterville Valley" and feed["LastUpdate"] == "2026-11-24T17:30:00Z"
    assert [(area["Name"], len(area["Lifts"]), len(area["Trails"])) for area in feed["MountainAreas"]] == [
        ("Waterville Valley", 10, 62), ("Terrain Parks", 0, 5)]
    rows = [row for area in feed["MountainAreas"] for row in area["Lifts"] + area["Trails"]]
    assert {row["StatusEnglish"] for row in rows} == {"closed"} and all(row["Name"] for row in rows)
    lifts = {lift["Name"]: lift for lift in feed["MountainAreas"][0]["Lifts"]}
    assert lifts["Tecumseh Express"] == {"Name": "Tecumseh Express", "Status": "Closed", "StatusEnglish": "closed",
                                         "Difficulty": None}
    assert lifts["Valley Run Quad"]["Status"] == "Closed"
    trails = {trail["Name"]: trail for trail in feed["MountainAreas"][0]["Trails"]}
    assert trails["Chandler's Way"] == {"Name": "Chandler's Way", "Status": "Closed", "StatusEnglish": "closed",
                                        "Difficulty": "Green", "Grooming": "No"}
    assert (trails["Tippecanoe"]["Difficulty"], trails["Gema"]["Difficulty"], trails["True Grit"]["Difficulty"]) == (
        "Blue", "Black", "Double black")
    assert feed["MountainAreas"][1]["Trails"][0]["Difficulty"] == ""


def test_before_the_season_the_snow_report_has_no_depth_and_the_parts_switched_off_are_not_read():
    snow = waterville.parse(PAGE, NOW)["SnowReport"]
    # "11:12am, November 23, 2026" in the mountain's own time.
    assert snow["LastUpdate"] == "2026-11-23T16:12:00Z" and snow["Resortwide"] is True
    assert snow["BaseArea"] == {"Name": "Mountain", "BaseIn": None, "BaseMinIn": None, "BaseMaxIn": None,
                                "Last24HoursIn": None, "Last24HoursMinIn": None, "Last24HoursMaxIn": None,
                                "Last48HoursIn": None}
    # The surface is left in the page as a comment, empty.
    assert snow["BaseConditions"] is None and snow["SeasonTotalIn"] == 173
    assert "Anticipated Opening Day" in snow["Report"]


def test_the_open_mountain_reads_open_lifts_groomed_runs_and_the_base_depth_as_a_range():
    # The report on 2024-02-02 (from the Internet Archive), which counts 7 lifts and 58 trails open.
    feed = waterville.parse(MIDSEASON, NOW)
    lifts = {lift["Name"]: lift["StatusEnglish"] for lift in feed["MountainAreas"][0]["Lifts"]}
    assert len(lifts) == 11 and sum(status == "open" for status in lifts.values()) == 7
    assert lifts["Tecumseh Express"] == "open" and lifts["Northside"] == "closed"
    trails = feed["MountainAreas"][0]["Trails"]
    assert len(trails) == 62 and sum(trail["StatusEnglish"] == "open" for trail in trails) == 58
    # Groomed and partly groomed runs are both groomed; a closed run is not.
    assert sum(trail["Grooming"] == "Yes" for trail in trails) == 50
    assert all(trail["Grooming"] == "No" for trail in trails if trail["StatusEnglish"] == "closed")
    assert len(feed["MountainAreas"][1]["Trails"]) == 6
    snow = feed["SnowReport"]
    assert snow["BaseArea"] == {"Name": "Mountain", "BaseIn": 25, "BaseMinIn": 20, "BaseMaxIn": 30, "Last24HoursIn": 0,
                                "Last24HoursMinIn": 0, "Last24HoursMaxIn": 0, "Last48HoursIn": 0}
    assert snow["SeasonTotalIn"] == 75 and snow["LastUpdate"] == "2024-02-02T12:10:00Z"


def test_a_held_lift_takes_the_report_s_words():
    start = PAGE.index("Exhibition T-Bar")
    page = PAGE[:start] + PAGE[start:].replace("pti-closed", "pti-hold", 1).replace(">Closed<", ">Wind Delay<", 1)
    lifts = waterville.parse(page, NOW)["MountainAreas"][0]["Lifts"]
    assert lifts[0] == {"Name": "Exhibition T-Bar", "Status": "Wind delay", "StatusEnglish": "wind delay", "Difficulty": None}


def test_depths_read_as_one_figure_or_a_range_and_other_words_are_refused():
    assert waterville.span(" - in.", "Base") == {"BaseIn": None, "BaseMinIn": None, "BaseMaxIn": None}
    assert waterville.span("in.", "Base")["BaseIn"] is None
    assert waterville.span("2 - 5 in.", "Last24Hours") == {"Last24HoursIn": 3.5, "Last24HoursMinIn": 2, "Last24HoursMaxIn": 5}
    assert waterville.span("173 in.", "SeasonTotal")["SeasonTotalIn"] == 173
    with pytest.raises(ValueError, match="not a depth"):
        waterville.span("a few in.", "Base")


def test_a_page_whose_lifts_and_trails_do_not_all_read_is_refused():
    with pytest.raises(ValueError, match="no name or no status"):
        waterville.parse(PAGE.replace('<h3 class="SnowReport-feature-title">Baseway</h3>', "<h4>Baseway</h4>", 1), NOW)
    with pytest.raises(ValueError, match="lists 77 lifts and trails but 67"):
        waterville.parse(PAGE.replace('<section class="SnowReport-section SnowReport-section--trails">',
                                      '<section class="SnowReport-section SnowReport-section--runs">', 1), NOW)
    with pytest.raises(ValueError, match="no lifts or no trails"):
        waterville.parse("<html></html>", NOW)
    with pytest.raises(ValueError, match="posted"):
        waterville.parse(PAGE.replace("11:12am, November 23, 2026", "this morning"), NOW)
